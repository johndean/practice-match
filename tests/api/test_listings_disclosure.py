"""Per-buyer disclosure plan Task 8 (spec 2026-09-18): `serialise` applies the CALLING BUYER's own
capabilities to name, exact location and revenue on the two routes that already exist -- the
paginated list and the single-listing read. Directive §11 (exact location), §1's FINANCIALS
example, and the AND-with-the-ceiling rule (§8, §24) are the field-level unit proof here; Task 11
owns the full end-to-end approve/see-it/revoke/lose-it acceptance matrix and Task 13 owns IDOR --
this file is deliberately narrower: does `serialise` itself gate correctly, on BOTH routes,
including the LIST route's bulk path (directive §23) and its shared response cache, which Task 8
turns from a buyer-blind optimisation into a second place the whole feature could leak from if its
key does not also change (the risk is named in `app/api/listings.py`'s own pre-Task-8 comment:
"if a later task adds a per-account field to this payload, this key must gain the account id or
the cache must go" -- this task is that later task)."""
from __future__ import annotations

from typing import Any

import psycopg2.extensions
import pytest

from tests.api.conftest import auth_headers


async def _published_seller_listing(conn: Any, client: Any, headers: dict[str, str], **overrides: Any) -> str:
    """A REAL, published, seller-OWNED listing. `authorized_capabilities`/`_bulk` (Task 3) key their
    self-authorization guard off the listing's own `seller_id`, and `app.disclosure.requests.create`
    refuses a request against a listing with none (`NO_SELLER`) -- so every test below needs a
    listing created through the actual wizard-create route (`POST /api/seller/listings`), never
    `tests/api/test_listings.py::_insert`'s fixture, which writes no seller at all.

    Two deviations from the plan's own literal Step-1 helper, found by RUNNING it (both raised
    `psycopg2.errors.CheckViolation` before a single capability assertion ever ran, on a fresh
    seller draft that has NONE of these columns filled in):

    1. `migrations/030`'s `listing_submittable_ck` requires `name`, `city`, `zip`, `type`, `est`
       and `price` non-null once `status` leaves `draft`/`withdrawn` -- the plan's draft set every
       one of the first five but never `type`, which the RED run's own `CheckViolation` names.
    2. `migrations/034`'s `listing_publishable_ck` additionally requires `state`, `market`, `area`
       and `sqft` non-null for `status = 'published'` specifically -- the plan's draft set
       `state`/`sqft` but never `market`/`area`.

    All four missing columns are added here; nothing else about the plan's shape changes."""
    listing = await client.post("/api/seller/listings", headers=headers)
    listing_id = listing.json()["id"]
    fields = {
        "status": "published", "name": "Real Practice Name", "city": "Austin", "state": "TX",
        "zip": "78701", "street": "123 Main St", "phone": "5125551234", "est": 2010,
        "price": 1000000, "rev": 500000, "sqft": 3000, "area": "Austin", "market": "Austin, TX",
        "type": "Small animal",
        "location_disclosed": False, "name_disclosed": False, "rev_disclosed": False,
        **overrides,
    }
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE listing SET {set_clause} WHERE id = %s", (*fields.values(), listing_id))
    return listing_id


async def _approve(client: Any, seller_headers: dict[str, str], buyer_headers: dict[str, str],
                   listing_id: str, level: str = "FULL_CONFIDENTIAL") -> str:
    """The REAL request/decide dance (Tasks 5-6's own routes, not a hand-inserted row): this file's
    whole point is proving `serialise` reads what those routes actually write, end to end."""
    created = await client.post("/api/requests", headers=buyer_headers,
                                json={"listing_id": listing_id, "disclosure_level": level})
    assert created.status_code == 201, created.text
    decided = await client.post(f"/api/seller/requests/{created.json()['id']}/decide",
                                headers=seller_headers, json={"action": "approve"})
    assert decided.status_code == 200, decided.text
    return str(created.json()["id"])


class _QueryCounter:
    def __init__(self) -> None:
        self.count = 0


class _CountingCursor(psycopg2.extensions.cursor):
    """A real `psycopg2.extensions.cursor` that also counts its own `execute()` calls, via a
    class-level target `_count_queries` points at each test.

    `psycopg2.extensions.cursor` itself is an immutable C type -- `monkeypatch.setattr
    (psycopg2.extensions.cursor, "execute", ...)` raises `TypeError: cannot set 'execute' attribute
    of immutable type`, and an INSTANCE returned by `conn.cursor()` refuses attribute assignment
    too ("attribute 'execute' is read-only"), both confirmed by running them (this file's own RED).
    A plain Python SUBCLASS has neither restriction, so counting happens by routing every
    `conn.cursor()` call through this class instead (`_count_queries`, below) rather than by
    patching the immutable base."""
    counter: _QueryCounter | None = None

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        if _CountingCursor.counter is not None:
            _CountingCursor.counter.count += 1
        return super().execute(*args, **kwargs)


def _count_queries(monkeypatch: Any) -> _QueryCounter:
    """Every `cursor.execute()` call psycopg2 makes through the APP's OWN pooled connections, from
    the moment this is called -- real SQL round trips against the real database, not a proxy like
    "was my bulk function called once." `app/db.py::PooledConnection` is the class EVERY
    `app.db.sync_conn()` connection the FastAPI handler opens (barring pool exhaustion, which a
    single sequential test never reaches); this test's OWN `conn` fixture is a bare
    `psycopg2.connect(...)` (`tests/conftest.py`), never a `PooledConnection`, so its own setup
    queries (creating accounts, approving grants) are never counted -- only what the ROUTE itself
    asks the database is."""
    from app.db import PooledConnection

    counter = _QueryCounter()
    monkeypatch.setattr(_CountingCursor, "counter", counter)
    original_cursor_method = PooledConnection.cursor

    def _cursor_with_counter(self: Any, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("cursor_factory", _CountingCursor)
        return original_cursor_method(self, *args, **kwargs)

    monkeypatch.setattr(PooledConnection, "cursor", _cursor_with_counter)
    return counter


@pytest.mark.asyncio
async def test_an_unapproved_buyer_sees_the_anonymised_name_even_when_the_ceiling_is_open(client: Any, conn: Any, member: Any) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s1@x.org")
    listing_id = await _published_seller_listing(conn, client, auth_headers(s_cookies, s_hdr), name_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b1@x.org")
    response = await client.get(f"/api/listings/{listing_id}", headers=auth_headers(b_cookies, b_hdr))
    assert response.json()["name"] != "Real Practice Name"
    assert response.json()["name_disclosed"] is False, "no grant means the OUTPUT flag reflects what THIS buyer actually got, not the seller's raw ceiling"


@pytest.mark.asyncio
async def test_a_signed_in_buyer_with_no_grant_is_identical_to_the_public_shape(client: Any, conn: Any, member: Any) -> None:
    """Directive §11's own last line: exact coordinates never reach an unauthenticated -- in this
    product's vocabulary, un-GRANTED -- response body, even with every ceiling wide open. One
    listing, all three ceilings open, no request ever created against it."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s1b@x.org")
    listing_id = await _published_seller_listing(
        conn, client, auth_headers(s_cookies, s_hdr),
        name_disclosed=True, location_disclosed=True, rev_disclosed=True,
    )
    _bid, b_cookies, b_hdr = member(("buyer",), email="b1b@x.org")
    body = (await client.get(f"/api/listings/{listing_id}", headers=auth_headers(b_cookies, b_hdr))).json()
    assert body["name"] != "Real Practice Name" and body["name_disclosed"] is False
    assert body["street"] is None and body["zip"] is None and body["phone"] is None
    assert body["lat"] is None and body["lng"] is None and body["location_disclosed"] is False
    assert body["rev"] is None
    # Directive §12's own words, checked over the RAW body: no exact coordinate leaks through any
    # OTHER key either, not just the ones this test already named.
    text = (await client.get(f"/api/listings/{listing_id}", headers=auth_headers(b_cookies, b_hdr))).text
    assert "123 Main St" not in text and "5125551234" not in text and "Real Practice Name" not in text


@pytest.mark.asyncio
async def test_an_approved_identity_grant_reveals_the_real_name(client: Any, conn: Any, member: Any) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s2@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, name_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b2@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_id, level="IDENTITY")
    response = await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)
    assert response.json()["name"] == "Real Practice Name"
    assert response.json()["name_disclosed"] is True


@pytest.mark.asyncio
async def test_an_identity_grant_does_not_also_reveal_location_or_revenue(client: Any, conn: Any, member: Any) -> None:
    """Each capability follows its OWN name (directive §16) -- a grant of ONE must not confer
    another, even though every ceiling in this listing is wide open."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s3@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers,
                                                  name_disclosed=True, location_disclosed=True, rev_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b3@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_id, level="IDENTITY")
    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["name"] == "Real Practice Name"
    assert body["street"] is None and body["lat"] is None and body["lng"] is None
    assert body["rev"] is None


@pytest.mark.asyncio
async def test_a_financials_grant_reveals_only_revenue(client: Any, conn: Any, member: Any) -> None:
    """The mirror of the IDENTITY test above -- directive §1's own FINANCIALS example -- so no
    single capability is accidentally standing in for "all of them.\""""
    _sid, s_cookies, s_hdr = member(("seller",), email="s3b@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers,
                                                  name_disclosed=True, location_disclosed=True, rev_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b3c@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_id, level="FINANCIALS")
    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["rev"] == 500000
    assert body["name"] != "Real Practice Name"
    assert body["street"] is None and body["lat"] is None and body["lng"] is None


@pytest.mark.asyncio
async def test_a_full_confidential_grant_with_the_ceiling_closed_still_withholds_the_field(client: Any, conn: Any, member: Any) -> None:
    """Directive §8/§24: the ceiling flag ANDs with the grant, in BOTH directions -- a grant this
    broad cannot override a ceiling the seller has left shut."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s4@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, location_disclosed=False)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b4@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_id)
    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["street"] is None  # location_disclosed is still false; FULL_CONFIDENTIAL cannot override it
    assert body["location_disclosed"] is False


@pytest.mark.asyncio
async def test_buyer_a_with_exact_location_and_buyer_b_without_diverge_at_the_same_moment(client: Any, conn: Any, member: Any) -> None:
    """Directive §7's own critical security test, applied to EXACT_LOCATION on the detail route:
    two buyers, one seller-approved, reading the SAME listing in the SAME test run must not agree."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s5b@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, location_disclosed=True)
    # `_published_seller_listing` sets `street`/`city`/`zip` but no `geom` -- the helper's other
    # callers never need a point. This test's own subject IS the exact coordinate, so it geocodes
    # the listing directly (`serialise`'s `disclosed and lat is not None` guard is the null-safety
    # arm `test_serialise_omits_a_point_a_disclosed_listing_never_had` already covers; this test is
    # about the DISCLOSED arm).
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET geom = ST_SetSRID(ST_MakePoint(-97.7431, 30.2672), 4326)::geography WHERE id = %s", (listing_id,))
    _aid, a_cookies, a_hdr = member(("buyer",), email="a5b@x.org")
    a_headers = auth_headers(a_cookies, a_hdr)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b5b@x.org")
    b_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, a_headers, listing_id, level="EXACT_LOCATION")

    a_body = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    b_body = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert a_body["street"] == "123 Main St" and a_body["lat"] is not None and a_body["lng"] is not None
    # Buyer B keeps the PUBLIC tier: no street, and the point coarsened to ~1.1 km rather than
    # withheld (directive §2/§11). The isolation that matters is that B's point is NOT A's.
    assert b_body["street"] is None
    assert (b_body["lat"], b_body["lng"]) == (round(a_body["lat"], 2), round(a_body["lng"], 2))
    assert (b_body["lat"], b_body["lng"]) != (a_body["lat"], a_body["lng"]), \
        "an approximate point must not equal the exact one this fixture grants Buyer A"


@pytest.mark.asyncio
async def test_after_revocation_the_buyer_returns_to_the_public_shape(client: Any, conn: Any, member: Any) -> None:
    """Directive §15: revocation must be IMMEDIATE, through the same protected route the grant
    unlocked -- no session refresh, no separate flag to clear."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s6b@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, name_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b6b@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    request_id = await _approve(client, seller_headers, buyer_headers, listing_id, level="IDENTITY")
    granted = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert granted["name"] == "Real Practice Name"

    revoked = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    assert revoked.status_code == 200, revoked.text
    after = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert after["name"] != "Real Practice Name"
    assert after["name_disclosed"] is False


@pytest.mark.asyncio
async def test_a_buyer_denied_on_the_detail_page_cannot_read_the_same_field_out_of_the_list(client: Any, conn: Any, member: Any) -> None:
    """The two routes must agree: whatever a buyer cannot see on `GET /api/listings/{id}` they must
    not be able to read on `GET /api/listings` either."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s7@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers,
                                                  name_disclosed=True, rev_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b7@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)

    detail = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert detail["name"] != "Real Practice Name" and detail["rev"] is None

    listed = {item["id"]: item for item in (await client.get("/api/listings", headers=buyer_headers)).json()["items"]}
    assert listed[listing_id]["name"] != "Real Practice Name"
    assert listed[listing_id]["rev"] is None
    assert listed[listing_id]["name"] == detail["name"], "the two routes must agree on the SAME redacted value"


@pytest.mark.asyncio
async def test_the_list_route_applies_capabilities_per_listing(client: Any, conn: Any, member: Any) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s5@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_x = await _published_seller_listing(conn, client, seller_headers, name_disclosed=True)
    listing_y = await _published_seller_listing(conn, client, seller_headers, name_disclosed=True)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b5@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_x, level="IDENTITY")
    items = {row["id"]: row for row in (await client.get("/api/listings", headers=buyer_headers)).json()["items"]}
    assert items[listing_x]["name"] == "Real Practice Name"
    assert items[listing_y]["name"] != "Real Practice Name"


@pytest.mark.asyncio
async def test_the_bulk_capability_lookup_costs_the_same_single_extra_query_regardless_of_page_size(
    client: Any, conn: Any, member: Any, monkeypatch: Any,
) -> None:
    """Directive §23: "do not introduce a database query explosion." `authorized_capabilities_bulk`
    is built for exactly one extra, indexed `= ANY(...)` query for a WHOLE page (Task 3); a per-row
    lookup is a defect, not an optimisation to do later, so the real proof is that a five-listing
    page costs the database EXACTLY what a one-listing page does -- never four more round trips.

    ONE `_count_queries(monkeypatch)` call for BOTH reads, the counter reset (never re-patched)
    between them: patching `PooledConnection.cursor` twice in one test through `monkeypatch.undo()`
    -> a fresh `_count_queries()` measured 7 queries for `limit=1` and then a GENUINE 0-ROW answer
    (`ROWCOUNT: 0` on the main SELECT itself, `cur.query` confirmed byte-for-byte correct SQL and
    `LIMIT 6`) for `limit=5` even though 5 published listings exist and the identical request
    succeeds correctly as the FIRST (only) call in an otherwise-identical test -- a real, reproduced
    interaction between `monkeypatch.undo()`'s class-attribute restore and this connection pool's
    reuse, not a defect in `list_listings` (confirmed: the unpatched route always answers
    correctly, in isolation and back-to-back, regardless of call order). One patch, `counter.count`
    zeroed between reads, is both simpler and avoids it entirely."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s5c@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    ids = [await _published_seller_listing(conn, client, seller_headers, name_disclosed=True) for _ in range(5)]
    _bid, b_cookies, b_hdr = member(("buyer",), email="b5c@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, ids[0], level="IDENTITY")

    counter = _count_queries(monkeypatch)
    counts: dict[int, int] = {}
    items_seen: dict[int, int] = {}
    for limit in (1, 5):
        counter.count = 0
        response = await client.get(f"/api/listings?limit={limit}", headers=buyer_headers)
        assert response.status_code == 200
        items_seen[limit] = len(response.json()["items"])
        counts[limit] = counter.count

    assert items_seen == {1: 1, 5: 5}, items_seen  # both reads actually saw the real page, not a cache/empty artifact
    assert counts[1] == counts[5], (
        f"a 5-row page cost {counts[5]} queries against a 1-row page's {counts[1]} -- "
        "the capability lookup must be O(1) in page size, never one query per listing"
    )
    # Literal count, verified by running this test against the real route (not eyeballed): the main
    # SELECT (1) + active_vintage/dataset_registry (2) + community_rows' own three batched queries
    # (3) + ONE bulk capability lookup (1) = 7, whatever the page size.
    assert counts[1] == 7


@pytest.mark.asyncio
async def test_the_list_routes_shared_cache_never_leaks_one_buyers_grant_to_another(client: Any, conn: Any, member: Any) -> None:
    """The vulnerability this task's own risk section names first: "leave a field unguarded and it
    leaks to every buyer." Pre-Task-8 the list route's 60-second response cache was keyed on
    `(market, limit)` alone because the payload carried "no per-account field" -- true until THIS
    task made it one. Buyer A's disclosed name must never be handed to Buyer B through that cache,
    even though both ask for the exact same page within the same TTL window."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s8@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, name_disclosed=True)
    _aid, a_cookies, a_hdr = member(("buyer",), email="a8@x.org")
    a_headers = auth_headers(a_cookies, a_hdr)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b8@x.org")
    b_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, a_headers, listing_id, level="IDENTITY")

    # Buyer A goes FIRST, on the exact (market=unset, limit=default) key the shared cache used to
    # index by alone -- if the fix were missing, THIS call is the one that would poison it.
    a_items = {row["id"]: row for row in (await client.get("/api/listings", headers=a_headers)).json()["items"]}
    assert a_items[listing_id]["name"] == "Real Practice Name"

    # Buyer B, same market, same limit, well inside the 60-second TTL.
    b_items = {row["id"]: row for row in (await client.get("/api/listings", headers=b_headers)).json()["items"]}
    assert b_items[listing_id]["name"] != "Real Practice Name", (
        "Buyer B received Buyer A's disclosed name through the shared list cache"
    )

    # And the reverse order, so this is not a one-directional accident of which buyer asks first.
    b_items_2 = {row["id"]: row for row in (await client.get("/api/listings", headers=b_headers)).json()["items"]}
    assert b_items_2[listing_id]["name"] != "Real Practice Name"
    a_items_2 = {row["id"]: row for row in (await client.get("/api/listings", headers=a_headers)).json()["items"]}
    assert a_items_2[listing_id]["name"] == "Real Practice Name"


@pytest.mark.asyncio
async def test_the_sellers_own_dashboard_view_is_unaffected_by_any_buyers_capability(client: Any, conn: Any, member: Any) -> None:
    """"The seller's own view of their own listing must not regress. They see their own data by
    ownership, not by grant." `GET /api/seller/listings/{id}` (`app/api/seller_listings.py`) is a
    SEPARATE route this task does not modify and does not import `serialise` from at all (confirmed
    by reading `seller_listings.py`'s own imports) -- this proves the boundary holds rather than
    only asserting it by file inspection.

    `serialise_draft` (`app/api/seller_listings.py:501`) is a DIFFERENT contract from the buyer's
    `serialise` -- "every column unblanked, nulls preserved" (D11), in the WIZARD's own field names
    (`state.w` in `logic.js`) rather than the buyer payload's -- and, discovered by running this
    test (its own RED, before this fix): it carries no `street`/`phone`/`lat`/`lng` at all (the
    wizard collects a city and a ZIP and no street, `tests/api/test_listings.py`'s own comment on
    `STEP_FIELDS[2]`), so there is no address field here to prove unblanked. `name` and `rev` ARE
    in both contracts and are exactly the two fields directive §1/§11 name as confidential, so they
    are what this test checks."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s9@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers,
                                                  name_disclosed=False, location_disclosed=False, rev_disclosed=False)
    own = await client.get(f"/api/seller/listings/{listing_id}", headers=seller_headers)
    assert own.status_code == 200, own.text
    body = own.json()
    assert body["name"] == "Real Practice Name"
    assert body["rev"] == 500000
    # D11's own polarity: `anon`/`revBand` mirror the RAW ceiling flags this test set to False,
    # never a buyer's capability -- this route has no concept of one at all.
    assert body["anon"] is True and body["revBand"] is True
