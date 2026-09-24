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
async def test_an_unapproved_buyer_sees_the_anonymised_name_when_the_ceiling_is_shut(client: Any, conn: Any, member: Any) -> None:
    """**RE-KEYED UNDER D-C66 (2026-09-24), and what it used to prove is why.** This case was
    written as "...even when the ceiling is OPEN": under ceiling-AND-grant an open `name_disclosed`
    redacted the name all the same, because the buyer held no grant. Under ceiling-OR-grant an open
    ceiling IS the seller publishing the name, so the same fixture would now prove the opposite of
    what it was written for -- that inversion is its own case,
    `test_a_signed_in_buyer_with_no_grant_receives_everything_an_open_ceiling_publishes` below.

    The claim survives the move unchanged and is the one this case exists for: the OUTPUT flag
    reports what THIS buyer actually received, never the seller's raw column."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s1@x.org")
    listing_id = await _published_seller_listing(conn, client, auth_headers(s_cookies, s_hdr), name_disclosed=False)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b1@x.org")
    response = await client.get(f"/api/listings/{listing_id}", headers=auth_headers(b_cookies, b_hdr))
    assert response.json()["name"] != "Real Practice Name"
    assert response.json()["name_disclosed"] is False, "no grant means the OUTPUT flag reflects what THIS buyer actually got, not the seller's raw ceiling"


@pytest.mark.asyncio
async def test_a_signed_in_buyer_with_no_grant_receives_everything_an_open_ceiling_publishes(client: Any, conn: Any, member: Any) -> None:
    """**INVERTED UNDER D-C66 (2026-09-24), deliberately, and this is the ruling's other half.**

    Until this ruling this case read "...is identical to the public shape" and asserted that a
    listing with all three ceilings OPEN served a signed-in buyer with no grant NOTHING: no name,
    no address, no point, no revenue. That was directive §11's own last line read as
    ceiling-AND-grant, and it is what made approving a buyer release nothing on a listing whose
    seller had shut a ceiling -- `False and anything`.

    Under ceiling-OR-grant an open ceiling is the seller PUBLISHING that field, exactly as this
    product behaved before the 2026-09-18 directive ANDed a grant in front of it and exactly as the
    toggle's own off position reads. No request exists against this listing and none is needed. The
    redacted shape has not gone anywhere -- it is what a SHUT ceiling serves, which
    `test_every_shut_ceiling_still_hides_everything_from_a_buyer_with_no_grant` proves field by
    field."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s1b@x.org")
    listing_id = await _published_seller_listing(
        conn, client, auth_headers(s_cookies, s_hdr),
        name_disclosed=True, location_disclosed=True, rev_disclosed=True,
    )
    lat, lng = await _with_a_point(conn, listing_id)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b1b@x.org")
    body = (await client.get(f"/api/listings/{listing_id}", headers=auth_headers(b_cookies, b_hdr))).json()
    assert body["name"] == "Real Practice Name" and body["name_disclosed"] is True
    assert (body["street"], body["zip"], body["phone"]) == ("123 Main St", "78701", "5125551234")
    assert body["location_disclosed"] is True
    assert body["rev"] == 500000
    # THE POINT IS THE ONE FIELD AN OPEN CEILING DOES *NOT* PUBLISH IN FULL, and D-C66 fix round 1
    # (controller, 2026-09-24) is what kept it that way. The first pass of this task read the
    # brief's "the `ceiling` argument must take the same OR" literally, which makes `_point`'s two
    # arguments one expression and deletes directive §11's middle tier by construction -- so an
    # ungranted buyer began receiving a finer point than before, which D-C66 never asked for. The
    # tier is restored: the ADDRESS is released by the ceiling, the PRECISION by the grant alone.
    assert (body["lat"], body["lng"]) == (round(lat, 2), round(lng, 2))
    assert (body["lat"], body["lng"]) != (pytest.approx(lat), pytest.approx(lng)), (
        "an open ceiling publishes the address; it does not publish the exact coordinate")

    # ...and the SAME buyer, once granted, gets the exact pair on the same listing -- the third
    # tier, so all three are named in one place rather than inferred from two files.
    _sid2, s2_cookies, s2_hdr = _sid, s_cookies, s_hdr  # the same seller decides
    granted = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr),
                                json={"listing_id": listing_id, "disclosure_level": "EXACT_LOCATION"})
    assert granted.status_code == 201, granted.text
    decided = await client.post(f"/api/seller/requests/{granted.json()['id']}/decide",
                                headers=auth_headers(s2_cookies, s2_hdr), json={"action": "approve"})
    assert decided.status_code == 200, decided.text
    after = (await client.get(f"/api/listings/{listing_id}", headers=auth_headers(b_cookies, b_hdr))).json()
    assert (after["lat"], after["lng"]) == (pytest.approx(lat), pytest.approx(lng))


@pytest.mark.asyncio
async def test_an_approved_identity_grant_reveals_the_real_name(client: Any, conn: Any, member: Any) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s2@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    # RE-KEYED UNDER D-C66: `name_disclosed=False`. With the ceiling open the name is published to
    # everyone now, so an open-ceiling fixture could no longer prove the GRANT released anything.
    listing_id = await _published_seller_listing(conn, client, seller_headers, name_disclosed=False)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b2@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_id, level="IDENTITY")
    response = await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)
    assert response.json()["name"] == "Real Practice Name"
    assert response.json()["name_disclosed"] is True


@pytest.mark.asyncio
async def test_an_identity_grant_does_not_also_reveal_location_or_revenue(client: Any, conn: Any, member: Any) -> None:
    """Each capability follows its OWN name (directive §16) -- a grant of ONE must not confer
    another.

    **RE-KEYED UNDER D-C66 (2026-09-24): every ceiling in this fixture was wide OPEN and is now
    SHUT.** The old fixture made the point that an open ceiling was not enough; under
    ceiling-OR-grant an open ceiling is enough by itself, so the isolation this case is actually
    about -- one capability must not stand in for the other four -- can only be seen where the
    grant is the whole answer. The assertions below are unchanged."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s3@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers,
                                                  name_disclosed=False, location_disclosed=False, rev_disclosed=False)
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
    single capability is accidentally standing in for "all of them."

    RE-KEYED UNDER D-C66 for the same reason as the case above: the three ceilings this fixture
    opened are shut, because an open one now discloses on its own."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s3b@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers,
                                                  name_disclosed=False, location_disclosed=False, rev_disclosed=False)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b3c@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_id, level="FINANCIALS")
    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["rev"] == 500000
    assert body["name"] != "Real Practice Name"
    assert body["street"] is None and body["lat"] is None and body["lng"] is None


@pytest.mark.asyncio
async def test_a_full_confidential_grant_opens_a_ceiling_the_seller_shut(client: Any, conn: Any, member: Any) -> None:
    """**INVERTED UNDER D-C66 (2026-09-24). This case is the defect the ruling is made of.**

    It used to be called `test_a_full_confidential_grant_with_the_ceiling_closed_still_withholds_
    the_field`, and it asserted -- correctly, for the implementation as it then stood -- that
    "a grant this broad cannot override a ceiling the seller has left shut" (directive §8/§24).
    Read from the seller's side that is: the seller ticks "Keep practice name and address hidden
    UNTIL I APPROVE A BUYER", the buyer asks, the seller approves the broadest level there is, and
    the buyer receives nothing whatsoever. John ruled the behaviour wrong rather than the copy
    (D-C66), so the ceiling is now the PUBLIC DEFAULT and the grant RELEASES on top of it.

    What has NOT changed, and is asserted here beside the release: a shut ceiling still discloses
    nothing to a buyer with no grant (the case below it), and the bytes of a document still need a
    capability-matched grant whatever the ceiling says
    (`tests/api/test_documents_disclosure.py`)."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s4@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, location_disclosed=False)
    _bid, b_cookies, b_hdr = member(("buyer",), email="b4@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)

    before = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert before["street"] is None and before["location_disclosed"] is False

    await _approve(client, seller_headers, buyer_headers, listing_id)
    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["street"] == "123 Main St"
    assert body["location_disclosed"] is True


@pytest.mark.asyncio
async def test_buyer_a_with_exact_location_and_buyer_b_without_diverge_at_the_same_moment(client: Any, conn: Any, member: Any) -> None:
    """Directive §7's own critical security test, applied to EXACT_LOCATION on the detail route:
    two buyers, one seller-approved, reading the SAME listing in the SAME test run must not agree.

    **RE-KEYED UNDER D-C66 (2026-09-24): `location_disclosed` moves true -> false.** §7 is a
    requirement about a CONFIDENTIAL field, and under ceiling-OR-grant a listing whose ceiling the
    seller left open has no confidential location to diverge about -- both buyers would correctly
    receive the street the seller published. A shut ceiling is where §7 now lives, and the
    divergence it asks for is sharper there than it was: Buyer B gets no address and no pin at all,
    rather than the 1.1-km-rounded point the middle tier used to hand them."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s5b@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, location_disclosed=False)
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
    # Buyer B keeps what the seller published, which on a shut ceiling is no location at all. A25's
    # "no point, no pin" and D-C66 agree here: the listing stays off B's map.
    assert b_body["street"] is None and b_body["zip"] is None and b_body["phone"] is None
    assert (b_body["lat"], b_body["lng"]) == (None, None)
    assert (b_body["lat"], b_body["lng"]) != (a_body["lat"], a_body["lng"]), \
        "Buyer B must not receive the point this fixture grants Buyer A"


@pytest.mark.asyncio
async def test_after_revocation_the_buyer_returns_to_the_public_shape(client: Any, conn: Any, member: Any) -> None:
    """Directive §15: revocation must be IMMEDIATE, through the same protected route the grant
    unlocked -- no session refresh, no separate flag to clear."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s6b@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    # RE-KEYED UNDER D-C66: the ceiling is SHUT, so the grant is the only thing holding the name
    # open and revocation is the only thing that can close it again. With the ceiling open the name
    # is published to everybody and a revoked buyer would correctly go on seeing it.
    listing_id = await _published_seller_listing(conn, client, seller_headers, name_disclosed=False)
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
    # RE-KEYED UNDER D-C66: both ceilings SHUT, because an open one is now a publication and there
    # would be nothing for either route to withhold.
    listing_id = await _published_seller_listing(conn, client, seller_headers,
                                                  name_disclosed=False, rev_disclosed=False)
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
    # RE-KEYED UNDER D-C66: both ceilings SHUT, so the only difference between X and Y is the grant
    # this buyer holds against one of them -- which is what "per listing" means.
    listing_x = await _published_seller_listing(conn, client, seller_headers, name_disclosed=False)
    listing_y = await _published_seller_listing(conn, client, seller_headers, name_disclosed=False)
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
    # RE-KEYED UNDER D-C66: the ceiling is SHUT, so Buyer A's disclosed name exists only because of
    # A's own grant -- which is the only way this cache can leak anything at all.
    listing_id = await _published_seller_listing(conn, client, seller_headers, name_disclosed=False)
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


# --- Task 8 of the seller-wizard repair (ruling D-C66, 2026-09-24) -------------------------------
#
# **The ceilings became PER-BUYER RELEASABLE.** Every term above this line read *ceiling AND grant*,
# so a seller who shut a ceiling -- which is what all four step-7 toggles do, and what every label
# on them promises ("Keep practice name and address hidden UNTIL I APPROVE A BUYER",
# `frontend/src/logic.js`) -- could approve a buyer and release NOTHING: `False and anything` is
# False, whatever the seller decided afterwards. Three of the four toggles behaved that way;
# `showIdentifiable` (`app/privacy/delivery.py::buyer_variant`) was the one that already worked, and
# is the shape these now follow.
#
# John ruled the BEHAVIOUR wrong rather than the copy (D-C66), so each term is now *ceiling OR
# grant*: the ceiling is the PUBLIC DEFAULT and the grant RELEASES on top of it. The 2026-09-18
# directive's own ceiling-AND-grant sentences (§3, §8, §11, §18) are superseded IN PLACE in
# `docs/superpowers/specs/2026-09-18-per-buyer-disclosure-directive.md`, never deleted.
#
# WHAT THAT DOES TO THE TESTS ABOVE, stated rather than quietly applied: a ceiling left OPEN is now
# sufficient on its own, so a ceiling-open fixture can no longer prove anything about a grant. Every
# case above that opened a ceiling to isolate the grant now SHUTS it to isolate the same thing, and
# each carries its own note saying what it used to prove and why that changed -- the inversion idiom
# this branch used for `reorder_photos`' own characterisation test one task earlier.
#
# The cases below are the new behaviour's own proof, per toggle and -- for `anon`, which is one
# switch over five served facts -- per FIELD. The pin is asserted separately from the street on
# purpose: `_point` took the ceiling as its OWN argument, so a release that reached the street,
# the postcode and the telephone number and left the pin at None would be three quarters of a row
# and would read as done.


async def _with_a_point(conn: Any, listing_id: str) -> tuple[float, float]:
    """`_published_seller_listing` writes no `geom` -- its other callers never need one. Austin's
    own coordinate, the pair `test_buyer_a_with_exact_location_and_buyer_b_without_diverge_at_the_
    same_moment` already uses."""
    lng, lat = -97.7431, 30.2672
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography"
                    " WHERE id = %s", (lng, lat, listing_id))
    return lat, lng


@pytest.mark.asyncio
async def test_a_shut_name_ceiling_releases_the_name_and_slug_to_an_identity_grant(client: Any, conn: Any, member: Any) -> None:
    """D-C66, the `anon` toggle's identity half. `name_disclosed = false` is what the wizard writes
    when the seller ticks "Keep practice name and address hidden until I approve a buyer", and until
    this ruling approving that buyer changed nothing at all."""
    _sid, s_cookies, s_hdr = member(("seller",), email="c66-name-s@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, name_disclosed=False)
    _bid, b_cookies, b_hdr = member(("buyer",), email="c66-name-b@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)

    before = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert before["name"] != "Real Practice Name" and before["slug"] is None

    await _approve(client, seller_headers, buyer_headers, listing_id, level="IDENTITY")
    after = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert after["name"] == "Real Practice Name"
    assert after["name_disclosed"] is True
    assert after["slug"] is not None, "the slug spells the name, so it is released with it (A-L5.1)"


@pytest.mark.asyncio
async def test_a_shut_location_ceiling_releases_the_street_the_zip_the_telephone_and_the_pin(
    client: Any, conn: Any, member: Any,
) -> None:
    """D-C66, the `anon` toggle's location half -- FIVE served facts behind one switch, asserted one
    at a time because `serialise` reaches them through TWO different expressions (`disclosed` for
    the three strings, `_point`'s own arguments for the pair of coordinates) and a fix that moved
    only the first would leave the map empty for the buyer the seller just approved."""
    _sid, s_cookies, s_hdr = member(("seller",), email="c66-loc-s@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, location_disclosed=False)
    lat, lng = await _with_a_point(conn, listing_id)
    _bid, b_cookies, b_hdr = member(("buyer",), email="c66-loc-b@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)

    before = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert (before["street"], before["zip"], before["phone"]) == (None, None, None)
    assert (before["lat"], before["lng"]) == (None, None)

    await _approve(client, seller_headers, buyer_headers, listing_id, level="EXACT_LOCATION")
    after = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert after["street"] == "123 Main St"
    assert after["zip"] == "78701"
    assert after["phone"] == "5125551234"
    assert after["lat"] == pytest.approx(lat)
    assert after["lng"] == pytest.approx(lng)
    assert after["location_disclosed"] is True


@pytest.mark.asyncio
async def test_a_shut_revenue_ceiling_releases_the_exact_figure_to_a_financials_grant(client: Any, conn: Any, member: Any) -> None:
    """D-C66, the `revBand` toggle. Step 7's own label: "Release revenue as a range until I approve
    a buyer" -- the release half is what this proves; the range half is a separate, pre-existing
    copy defect (no band is computed anywhere in the product) and is reported, not fixed here."""
    _sid, s_cookies, s_hdr = member(("seller",), email="c66-rev-s@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers, rev_disclosed=False)
    _bid, b_cookies, b_hdr = member(("buyer",), email="c66-rev-b@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)

    assert (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()["rev"] is None
    await _approve(client, seller_headers, buyer_headers, listing_id, level="FINANCIALS")
    assert (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()["rev"] == 500000


@pytest.mark.asyncio
async def test_every_shut_ceiling_still_hides_everything_from_a_buyer_with_no_grant(client: Any, conn: Any, member: Any) -> None:
    """THE FAIL-CLOSED PROOF, and the one case this ruling could most easily have broken. Under AND
    a bug that wrongly handed a buyer a capability still met a shut ceiling; under OR the capability
    set is the ONLY thing left between a listing and disclosure, so the no-grant answer is re-proved
    here rather than inherited -- every field of every toggle, on a listing whose seller shut all
    four, for a signed-in buyer who has never asked for anything."""
    _sid, s_cookies, s_hdr = member(("seller",), email="c66-closed-s@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers)
    await _with_a_point(conn, listing_id)
    _bid, b_cookies, b_hdr = member(("buyer",), email="c66-closed-b@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)

    response = await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)
    body = response.json()
    assert body["name"] != "Real Practice Name" and body["name_disclosed"] is False and body["slug"] is None
    assert (body["street"], body["zip"], body["phone"]) == (None, None, None)
    assert (body["lat"], body["lng"]) == (None, None)
    assert body["location_disclosed"] is False
    assert body["rev"] is None
    # Directive §12 over the RAW body: no confidential value reaches this buyer through any other
    # key either, not only the ones named above.
    assert "123 Main St" not in response.text
    assert "5125551234" not in response.text
    assert "Real Practice Name" not in response.text
    assert "500000" not in response.text


# --- D-C67 (John, 2026-09-24): the SELLER chooses which capabilities one buyer receives ---------


@pytest.mark.asyncio
async def test_a_seller_releasing_only_financials_on_a_full_request_gives_the_revenue_and_not_the_address(
    client: Any, conn: Any, member: Any,
) -> None:
    """**THE POINT WHERE D-C66 AND D-C67 MEET, and the case the task brief names as the proof.**

    Every request defaults to `FULL_CONFIDENTIAL` (`app/api/requests.py`), and under D-C66 the
    grant alone decides for a listing whose ceilings are shut — so before D-C67 one click of
    Accept released the practice name, the street, the postcode, the telephone, the exact map pin,
    the unredacted photographs, the financial packet and the floor plans together, and the seller
    could not release less. Here the buyer asks for all of it and the seller releases ONE.

    Both directions are asserted separately, and neither can pass on the other's behalf: what was
    released IS there, and every field that was not released is NOT."""
    _sid, s_cookies, s_hdr = member(("seller",), email="dc67-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers,
                                                  name_disclosed=False, location_disclosed=False, rev_disclosed=False)
    _bid, b_cookies, b_hdr = member(("buyer",), email="dc67-buyer@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)

    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    assert created.status_code == 201, created.text
    assert created.json()["requested_disclosure_level"] == "FULL_CONFIDENTIAL"
    decided = await client.post(f"/api/seller/requests/{created.json()['id']}/decide", headers=seller_headers,
                                json={"action": "approve", "disclosure_capabilities": ["FINANCIALS"]})
    assert decided.status_code == 200, decided.text

    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["rev"] == 500000                                   # released
    assert body["name"] != "Real Practice Name"                    # withheld — IDENTITY
    assert body["street"] is None                                  # withheld — EXACT_LOCATION
    assert body["lat"] is None and body["lng"] is None             # withheld — EXACT_LOCATION


@pytest.mark.asyncio
async def test_a_narrowed_grant_takes_back_the_field_it_dropped_and_keeps_the_field_it_did_not(
    client: Any, conn: Any, member: Any,
) -> None:
    """D-C67's second half, through the real routes: the seller sees what the buyer holds and
    narrows it, without withdrawing their access entirely.

    Each direction is a separate assertion, because a two-sided change masks itself when only the
    half that happens to pass is checked (Task 8's fix rounds 1 and 2, twice in a row)."""
    _sid, s_cookies, s_hdr = member(("seller",), email="dc67n-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _published_seller_listing(conn, client, seller_headers,
                                                  name_disclosed=False, location_disclosed=False, rev_disclosed=False)
    _bid, b_cookies, b_hdr = member(("buyer",), email="dc67n-buyer@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)

    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    request_id = created.json()["id"]
    wide = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers,
                             json={"action": "approve", "disclosure_capabilities": ["IDENTITY", "FINANCIALS"]})
    assert wide.status_code == 200, wide.text
    before = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert before["name"] == "Real Practice Name" and before["rev"] == 500000

    narrow = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers,
                               json={"action": "approve", "disclosure_capabilities": ["FINANCIALS"]})
    assert narrow.status_code == 200, narrow.text
    after = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert after["name"] != "Real Practice Name"   # taken back
    assert after["rev"] == 500000                  # kept
