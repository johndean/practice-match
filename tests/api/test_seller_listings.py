"""The seller wizard's own surface (spec 2026-09-08 D7-D13, D16, D17).

Fixtures are `tests/api/conftest.py`'s: `client` (base URL https://qa.foundation.vin, so the Origin
check passes), `member(roles=..., state=..., email=...) -> (account_id, cookies, headers)`, and the
root `conn`/`redis`. There is no migrated `scratch_db` fixture — `conn` is the scratch database with
every migration applied and `settings.database_url` pointed at it.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg2
import pytest

from tests.api.conftest import auth_headers, padded_json

ROOT = Path(__file__).resolve().parents[2]


def _seller(member: Any) -> tuple[Any, dict[str, str], dict[str, str]]:
    return member(roles=("buyer", "seller"), email="sl-seller@example.org")


async def _create(client: Any, cookies: dict[str, str], headers: dict[str, str]) -> str:
    response = await client.post("/api/seller/listings", headers=auth_headers(cookies, headers))
    assert response.status_code == 201, response.text
    listing_id: str = response.json()["id"]
    return listing_id


async def test_a_seller_creates_a_draft_owned_by_themselves_with_every_flag_off(client: Any, conn: Any, member: Any) -> None:
    """D9's POST: one call, when *Create a listing* is first clicked. D11: `source='seller'` and all
    four disclosure flags false — the table's own defaults, so a seller hides by default."""
    account_id, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        cur.execute("SELECT seller_id, source, status, slug, location_disclosed, name_disclosed,"
                    " rev_disclosed, documents_disclosed FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (account_id, "seller", "draft", f"listing-{listing_id}", False, False, False, False)


async def test_a_buyer_may_not_create_a_listing(client: Any, conn: Any, member: Any) -> None:
    """`listing.manage_own` is the `seller` role's alone (permissions.py:24) — the matrix does this,
    not the handler, and this is the test that says so."""
    _, cookies, headers = member(roles=("buyer",), email="sl-buyer@example.org")
    response = await client.post("/api/seller/listings", headers=auth_headers(cookies, headers))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_an_anonymous_caller_gets_the_generic_401(client: Any, conn: Any) -> None:
    response = await client.post("/api/seller/listings", headers={"Origin": "https://qa.foundation.vin"})
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}


async def test_the_seller_prefix_does_not_collide_with_the_buyer_detail_route(client: Any, conn: Any, dist: Any) -> None:
    """D9's whole reason. `/api/listings/mine` would have been swallowed by
    `/api/listings/{listing_id}`; `/api/seller/listings` cannot be.

    The walk is `tests/conftest.py::walk_routes`, not `{r.path for r in create_app().routes}`
    (controller ruling on SL3 concern 2): FastAPI 0.141 keeps an included router as a
    `_IncludedRouter` WRAPPER, so the top-level set on this tree is `{"", "/robots.txt"}` and every
    `/api/*` path reads as absent — the assertion would fail against a perfectly correct router."""
    from app.main import create_app
    from tests.conftest import walk_routes

    paths = {path for _method, path, _route in walk_routes(create_app(dist=dist).routes)}
    assert "/api/seller/listings" in paths
    assert not any(path.startswith("/api/listings/") and path.endswith("/mine") for path in paths)


async def test_the_dashboard_lists_only_this_sellers_listings_in_every_status(client: Any, conn: Any, member: Any) -> None:
    """D9's GET. Every status, newest-touched first — `listing_owner_idx`'s own order."""
    mine, cookies, headers = _seller(member)
    other, other_cookies, other_headers = member(roles=("buyer", "seller"), email="sl-other@example.org")
    first = await _create(client, cookies, headers)
    second = await _create(client, cookies, headers)
    await _create(client, other_cookies, other_headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='withdrawn' WHERE id=%s", (first,))
    response = await client.get("/api/seller/listings", headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [second, first]
    assert {item["status"] for item in body["items"]} == {"draft", "withdrawn"}
    assert body["next_cursor"] is None
    assert other is not mine


async def test_a_non_owner_gets_404_on_every_single_listing_route(client: Any, conn: Any, member: Any) -> None:
    """D7: 404, never 403 — a listing that is not yours should not be confirmed to exist."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    _, thief_cookies, thief_headers = member(roles=("buyer", "seller"), email="sl-thief@example.org")
    signed = auth_headers(thief_cookies, thief_headers)
    for response in (
        await client.get(f"/api/seller/listings/{listing_id}", headers=signed),
        await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "Theirs"}, headers=signed),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_a_listing_id_that_is_not_a_uuid_is_a_404_not_a_422(client: Any, conn: Any, member: Any) -> None:
    _, cookies, headers = _seller(member)
    response = await client.get("/api/seller/listings/not-a-uuid", headers=auth_headers(cookies, headers))
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


async def test_the_seller_route_carries_one_guard_and_staff_read_elsewhere(client: Any, conn: Any, member: Any) -> None:
    """Controller amendment A-SL8: the staff read is a SEPARATE `GET /api/admin/listings/{id}`
    guarded by `listing.review`, not a second permission inside this handler — one guard per route
    is what `tests/auth/test_permissions.py` models.

    So a staff-only member is refused HERE by the matrix (`listing.manage_own` is the seller role's
    alone), with the same 403 for every id — no existence oracle — and reads the draft through the
    admin route instead (`tests/api/test_admin_listings.py`)."""
    from app.api import seller_listings as SL

    assert not hasattr(SL, "REQUIRE_REVIEW"), "A-SL8: this module enforces one permission only"
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    _, staff_cookies, staff_headers = member(roles=("staff",), email="sl-staff@example.org")
    signed = auth_headers(staff_cookies, staff_headers)
    refused = await client.get(f"/api/seller/listings/{listing_id}", headers=signed)
    absent = await client.get("/api/seller/listings/11111111-1111-1111-1111-111111111111", headers=signed)
    assert refused.status_code == absent.status_code == 403
    assert refused.json() == absent.json()


async def test_each_step_writes_its_own_fields_and_the_four_forced_mappings(client: Any, conn: Any, member: Any) -> None:
    """D10, the whole table. `desc` is the `services` column, `bldg` takes a value map, `type`
    accepts 'Other', and `facilityType` lands in the new `facility_type`."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)

    async def patch(step: int, fields: dict[str, Any]) -> Any:
        return await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json=fields, headers=signed)

    assert (await patch(1, {"name": "Hill Country Animal Hospital", "type": "Other", "est": "1998", "ownership": "Multi-doctor LLC"})).status_code == 200
    assert (await patch(2, {"city": "Cedar Park", "zip": "78613", "anon": True})).status_code == 200
    assert (await patch(3, {"price": "1,450,000", "rev": "$2,100,000", "revBand": True})).status_code == 200
    assert (await patch(4, {"docs": "3", "rooms": "5", "sqft": "4,200", "hours": "Mon-Fri 7:30-6", "desc": "Wellness, dentistry"})).status_code == 200
    assert (await patch(5, {"bldg": "Available separately", "facilityType": "Medical park", "facility": "Corner lot"})).status_code == 200

    with conn.cursor() as cur:
        cur.execute("SELECT name, type, est, ownership, city, zip, area, name_disclosed, location_disclosed,"
                    " price, rev, rev_disclosed, docs, rooms, sqft, hours, services, bldg, facility_type, facility"
                    " FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (
            "Hill Country Animal Hospital", "Other", 1998, "Multi-doctor LLC", "Cedar Park", "78613", "Cedar Park",
            False, False, 1_450_000, 2_100_000, False, 3, 5, 4200, "Mon-Fri 7:30-6", "Wellness, dentistry",
            "Separate", "Medical park", "Corner lot",
        )


async def test_step_seven_writes_the_four_disclosure_columns_inverted(client: Any, conn: Any, member: Any) -> None:
    """D20. The design's three switches are all "hide this"; the columns are all "show this"."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=7",
                                  json={"anon": False, "revBand": False, "docsLocked": False},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT name_disclosed, location_disclosed, rev_disclosed, documents_disclosed FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (True, True, True, True)


async def test_a_field_from_another_step_is_refused(client: Any, conn: Any, member: Any) -> None:
    """D10: a `PATCH` accepts only the step's own fields; anything else is `400 BAD_REQUEST`."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A", "price": "10"},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
    assert "price" in response.json()["error"]["message"]


@pytest.mark.parametrize("step", ["6", "8", "0", "9", "one", ""])
async def test_only_the_six_field_steps_accept_a_patch(client: Any, conn: Any, member: Any, step: str) -> None:
    """Step 6 is uploads and step 8 is the preview; neither has a field set, and a typo'd `?step=`
    must not silently write nothing and answer 200."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json={},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.parametrize(("raw", "stored"), [("1,450,000", 1_450_000), ("$2,100,000", 2_100_000), (" 900000 ", 900_000), ("0", 0)])
async def test_money_arrives_as_the_string_the_design_produces(client: Any, conn: Any, member: Any, raw: str, stored: int) -> None:
    """D10's last paragraph. The wizard's own `previewRows` prefixes "$", so the stored value is the
    bare number and the API strips `,`, `$` and spaces."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": raw},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT price FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (stored,)


@pytest.mark.parametrize("raw", ["1.45m", "twelve", "-5", "1,4x0", "", "1e6"])
async def test_a_number_that_is_not_one_is_refused_in_the_envelope(client: Any, conn: Any, member: Any, raw: str) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": raw},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert set(response.json()) == {"error"}, "never FastAPI's {'detail': ...}"


@pytest.mark.parametrize(("field", "value"), [("type", "Aquatic"), ("ownership", "Cooperative")])
async def test_a_select_value_the_design_does_not_offer_is_refused(client: Any, conn: Any, member: Any, field: str, value: str) -> None:
    """The enum is the approved design's own option list (logic.js:1174), checked before the
    database sees it, so a CheckViolation can never become a 500."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={field: value},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_REQUEST"


async def test_saving_a_published_listing_takes_it_off_the_market_at_once(client: Any, conn: Any, member: Any) -> None:
    """D3, John's ruling. The first PATCH that changes a field of a published listing moves it to
    in_review, stamps nothing else, and the existing published-only read filter does the removing."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A", "type": "Small animal", "est": "1998"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=2", json={"city": "Cedar Park", "zip": "78613"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": "1000000"}, headers=signed)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', state='TX', market='Austin, TX', area='Cedar Park',"
                    " sqft=3000 WHERE id=%s", (listing_id,))
    assert (await client.get(f"/api/listings/{listing_id}", headers=signed)).status_code == 200

    assert (await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"rooms": "6"}, headers=signed)).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT status, submitted_at IS NOT NULL FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == ("in_review", True)
    assert (await client.get(f"/api/listings/{listing_id}", headers=signed)).status_code == 404

    # ...and a second PATCH in the same review cycle does not re-transition or re-stamp (D3).
    with conn.cursor() as cur:
        cur.execute("SELECT submitted_at FROM listing WHERE id=%s", (listing_id,))
        stamped = cur.fetchone()[0]
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"rooms": "7"}, headers=signed)
    with conn.cursor() as cur:
        cur.execute("SELECT status, submitted_at FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == ("in_review", stamped)


async def test_a_published_edit_writes_one_audit_row_naming_no_permission(client: Any, conn: Any, member: Any) -> None:
    """D4/D8: seller transitions are audited too, and they name no permission by design — exactly
    like `applications.submit`. `tests/auth/test_permissions.py` cannot see them (the route is
    guarded by `listing.manage_own`, which is not in AUDITED), so this asserts it on purpose."""
    from app.api import seller_listings as SL
    from app.auth import permissions as PM

    assert SL.EDIT_ACTION == "listing.edit" and SL.EDIT_ACTION not in PM.MATRIX
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', name='A', city='C', zip='7', type='Small animal',"
                    " est=1998, price=1, sqft=3000, state='TX', market='Austin, TX', area='C' WHERE id=%s", (listing_id,))
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"rooms": "6"}, headers=auth_headers(cookies, headers))
    with conn.cursor() as cur:
        cur.execute("SELECT action, before, after FROM audit_log WHERE target_type='listing' AND target_id=%s", (str(listing_id),))
        assert cur.fetchall() == [("listing.edit", {"status": "published"}, {"status": "in_review"})]


async def test_a_withdrawn_listing_refuses_every_write(client: Any, conn: Any, member: Any) -> None:
    """The lifecycle table's last row: withdrawn is terminal, and the seller may do nothing."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='withdrawn' WHERE id=%s", (listing_id,))
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A"},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 409 and response.json()["error"]["code"] == "STATE"


async def test_the_draft_serialiser_returns_the_owners_unblanked_truth(client: Any, conn: Any, member: Any) -> None:
    """D11. `serialise` is the buyer contract and is untouched; this one keeps nulls, applies no
    disclosure blanking, maps `bldg` back to the design's own wording and carries `assets`."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "Hill Country", "type": "Small animal", "est": "1998"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=5", json={"bldg": "Available separately"}, headers=signed)
    body = (await client.get(f"/api/seller/listings/{listing_id}", headers=signed)).json()
    assert body["name"] == "Hill Country"       # not blanked, though name_disclosed is false
    assert body["bldg"] == "Available separately"   # the design's wording, not the column's 'Separate'
    assert body["city"] is None and body["price"] is None    # nulls preserved, never "" or 0
    assert body["assets"] == []
    assert body["anon"] is True and body["revBand"] is True and body["docsLocked"] is True


async def test_a_patch_drops_every_listings_cache_key_after_the_commit(client: Any, conn: Any, redis: Any, member: Any) -> None:
    """D16, and the ordering `admin_users.py` learned in I5c fix round 1: the drop happens AFTER the
    transaction commits, never before, or a concurrent read re-caches the pre-write payload.

    On a PUBLISHED listing, which is D16's own scope — "every write that can change a published
    payload" (A-SL13 L6). The draft arm is the test below."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', name='A', city='C', zip='7',"
                    " type='Small animal', est=1998, price=1, sqft=3000, state='TX', market='Austin, TX',"
                    " area='C' WHERE id=%s", (listing_id,))
    redis.set("listings:v1:::50", b'{"items": []}')
    redis.set("listings:v1:Austin, TX::50", b'{"items": []}')
    redis.set("session:keep-me", b"x")
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"rooms": "6"}, headers=auth_headers(cookies, headers))
    assert redis.get("listings:v1:::50") is None
    assert redis.get("listings:v1:Austin, TX::50") is None
    assert redis.get("session:keep-me") == b"x"


async def test_a_drafts_autosave_leaves_the_browse_cache_alone(client: Any, conn: Any, redis: Any, member: Any) -> None:
    """A-SL13 L6. A draft is in no published payload, and the autosave fires once per step: a SCAN
    plus a DELETE per key on each of 240 patches an hour flushed Browse for every reader."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    redis.set("listings:v1:::50", b'{"items": []}')

    assert (await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A"},
                               headers=auth_headers(cookies, headers))).status_code == 200
    assert redis.get("listings:v1:::50") == b'{"items": []}'


async def test_the_patch_rate_limit_is_per_account_and_refuses_in_the_envelope(client: Any, conn: Any, redis: Any, member: Any, monkeypatch: Any) -> None:
    """D17. Generous enough that a seller working through eight steps never meets it; the test
    lowers it rather than sending 241 requests."""
    from app.api import seller_listings as SL

    monkeypatch.setattr(SL, "LISTING_PATCH", (2, 3600))
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    for _ in range(2):
        assert (await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A"}, headers=signed)).status_code == 200
    refused = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A"}, headers=signed)
    assert refused.status_code == 429 and refused.json()["error"]["code"] == "RATE_LIMITED"


async def test_serialise_blanks_rev_when_the_flag_is_off_and_keeps_it_when_it_is_on(conn: Any) -> None:
    """D22, on the BUYER serialiser — the one behavioural change this plan makes to it. `money()`
    renders a null as "—" already (logic.js:251), so no screen moves; every seed sets the flag true
    (030's backfill), so nothing John sees on QA changes."""
    from datetime import UTC, datetime

    from app.api.listings import serialise

    row = {
        "id": "11111111-1111-1111-1111-111111111111", "slug": "s", "name": "N", "street": None, "city": "C",
        "state": "TX", "zip": None, "phone": None, "hours": None, "status": "published",
        "location_disclosed": True, "name_disclosed": True, "lat": None, "lng": None, "area": "C",
        "type": "Small animal", "market": "Austin, TX", "price": 1, "rev": 2_100_000, "docs": None,
        "rooms": None, "sqft": None, "bldg": None, "est": None, "listed_at": datetime.now(UTC),
        "note": None, "staff": None, "services": None, "facility": None, "ownership": None, "photos": [],
        "rev_disclosed": False,
        # `_SELECT` selects them (A-L11 `main`, and A-SL23 (0)): a row "as `_rows()` builds one"
        # carries every column the query names, and `serialise` reads both unconditionally.
        "photo_captions": [], "asset_captions": {},
    }
    assert serialise(row, datetime.now(UTC))["rev"] is None
    assert serialise({**row, "rev_disclosed": True}, datetime.now(UTC))["rev"] == 2_100_000


# --- supplemental (not in the brief's Step 1 — added for 100 % branch coverage and for the
# contract SL4 reads back) -----------------------------------------------------------------------


async def test_the_dashboard_pages_on_its_own_cursor(client: Any, conn: Any, member: Any) -> None:
    """The keyset half of D9's GET, in `/api/admin/users`'s shape: `updated_at|id`, most recently
    touched first. Two listings and `?limit=1` rather than fifty-one rows and the default."""
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    first = await _create(client, cookies, headers)
    second = await _create(client, cookies, headers)

    page_one = (await client.get("/api/seller/listings?limit=1", headers=signed)).json()
    assert [item["id"] for item in page_one["items"]] == [second]
    assert page_one["next_cursor"] is not None

    page_two = (await client.get(f"/api/seller/listings?limit=1&cursor={page_one['next_cursor']}", headers=signed)).json()
    assert [item["id"] for item in page_two["items"]] == [first]
    assert page_two["next_cursor"] is None


async def test_a_limit_below_one_is_clamped_rather_than_refused(client: Any, conn: Any, member: Any) -> None:
    """`min(max(…, 1), MAX_LIST)`: a limit is a page size, and 0 rows is not an answer anyone asked
    for. A limit that is not a NUMBER is a different thing and is refused below."""
    _, cookies, headers = _seller(member)
    await _create(client, cookies, headers)
    await _create(client, cookies, headers)
    body = (await client.get("/api/seller/listings?limit=0", headers=auth_headers(cookies, headers))).json()
    assert len(body["items"]) == 1 and body["next_cursor"] is not None


async def test_a_limit_that_is_not_a_number_is_refused_in_the_envelope(client: Any, conn: Any, member: Any) -> None:
    """A-SL19 (7): the same code the admin queue and `/api/admin/users` use for the same mistake.
    It was `400 BAD_REQUEST` until the SL5 review (Minor-4) made this the only list route on the
    listing surface answering a bad parameter differently from its neighbours."""
    _, cookies, headers = _seller(member)
    response = await client.get("/api/seller/listings?limit=lots", headers=auth_headers(cookies, headers))
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "BAD_FILTER", "message": "limit must be a number."}}


@pytest.mark.parametrize("cursor", ["no-separator", "notadate|11111111-1111-1111-1111-111111111111",
                                    "2026-01-01T00:00:00Z|not-a-uuid"])
async def test_a_cursor_that_is_not_one_is_refused_in_the_envelope(client: Any, conn: Any, member: Any, cursor: str) -> None:
    """Three shapes, three arms: no `|` at all, a left half that is not a timestamp, a right half
    that is not a uuid. All three are the same refusal — a cursor is opaque to its holder."""
    _, cookies, headers = _seller(member)
    response = await client.get(f"/api/seller/listings?cursor={cursor}", headers=auth_headers(cookies, headers))
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "BAD_CURSOR", "message": "cursor must be a `<timestamp>|<id>`"
                                                                          " value from a previous page's next_cursor."}}


async def test_a_patch_with_no_body_at_all_touches_the_row_and_changes_nothing(client: Any, conn: Any, member: Any) -> None:
    """The autosave's empty case: `sets` is empty and only `updated_at` moves. It has to answer 200
    — the wizard fires a save per step whether or not the seller edited anything on it."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "Kept"}, headers=signed)
    with conn.cursor() as cur:
        cur.execute("SELECT updated_at FROM listing WHERE id=%s", (listing_id,))
        before = cur.fetchone()[0]

    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", headers=signed)
    assert response.status_code == 200 and response.json()["name"] == "Kept"
    with conn.cursor() as cur:
        cur.execute("SELECT name, updated_at FROM listing WHERE id=%s", (listing_id,))
        name, after = cur.fetchone()
    assert name == "Kept" and after > before


async def test_a_body_that_is_not_an_object_is_refused(client: Any, conn: Any, member: Any) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json=["name", "A"],
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert response.json() == {"error": {"code": "BAD_REQUEST", "message": "Body must be an object."}}


@pytest.mark.parametrize(("field", "value", "message"), [
    ("name", 12, "name must be text."),
    ("name", "x" * 4_001, "name is too long."),
    ("price", None, "price must be a number."),
    ("price", True, "price must be a number."),
    ("anon", "yes", "anon must be true or false."),
    ("type", None, "type must be one of Small animal, Mixed, Large animal, Emergency, Specialty, Other."),
])
async def test_a_field_of_the_wrong_type_is_refused_by_name(client: Any, conn: Any, member: Any, field: str, value: Any, message: str) -> None:
    """One arm each of `_text`, `_number`, `_flag` and `_one_of`. A seller who typed something the
    column cannot hold is told which field and why, in the envelope — never a 500 from psycopg2 and
    never FastAPI's `{"detail": [...]}`."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    step = {"name": 1, "type": 1, "price": 3, "anon": 2}[field]
    response = await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json={field: value},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert response.json() == {"error": {"code": "BAD_REQUEST", "message": message}}


async def test_an_integer_field_accepts_the_number_json_already_decoded(client: Any, conn: Any, member: Any) -> None:
    """The design's inputs produce strings, but `est` is a `<input type=number>` in Rev 3's own
    markup and JSON decodes it as an int — accepted, and still not a bool."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"est": 1998},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT est FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (1998,)


async def test_a_blank_text_field_is_stored_as_null_not_as_an_empty_string(client: Any, conn: Any, member: Any) -> None:
    """`raw.strip() or None`: the wizard clears a field by sending "", and a column that holds ""
    would make `serialise`'s "is it set?" question ambiguous for every later reader."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"hours": "   "},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT hours FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (None,)


async def test_step_two_without_a_city_leaves_the_area_alone(client: Any, conn: Any, member: Any) -> None:
    """`area` is derived FROM the city, so a step-2 save that only flips the switch must not blank
    it — the other arm of `if step == 2 and "city" in out`."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    await client.patch(f"/api/seller/listings/{listing_id}?step=2", json={"city": "Cedar Park"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=2", json={"anon": False}, headers=signed)
    with conn.cursor() as cur:
        cur.execute("SELECT city, area, name_disclosed FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == ("Cedar Park", "Cedar Park", True)


async def test_the_draft_carries_its_assets_in_upload_order(client: Any, conn: Any, member: Any) -> None:
    """The `assets[]` half of D11's serialiser, which SL4 fills through the upload route and the
    wizard's step-6 tiles read. Rows are planted directly here — SL3 has no upload route yet."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        for name, kind, content_type, size in (("1.webp", "photo", "image/webp", 2048),
                                               ("accounts.pdf", "other", "application/pdf", 91_000)):
            cur.execute("INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
                        " VALUES (%s,%s,%s,%s,%s,'sha',%s)",
                        (listing_id, kind, name, content_type, size, f"listings/{listing_id}/{name}"))
    body = (await client.get(f"/api/seller/listings/{listing_id}", headers=auth_headers(cookies, headers))).json()
    assert [(asset["name"], asset["kind"], asset["content_type"], asset["byte_size"]) for asset in body["assets"]] == [
        ("1.webp", "photo", "image/webp", 2048),
        ("accounts.pdf", "other", "application/pdf", 91_000),
    ]
    assert all(asset["id"] for asset in body["assets"])


@pytest.mark.parametrize(("step", "fields", "column"), [
    (4, {"docs": ""}, "docs"), (4, {"rooms": "  "}, "rooms"), (4, {"sqft": ""}, "sqft"),
    (3, {"rev": ""}, "rev"),
])
async def test_an_optional_numeric_field_is_cleared_by_an_empty_string(
    client: Any, conn: Any, member: Any, step: int, fields: dict[str, Any], column: str
) -> None:
    """A-SL13 M1. D10's "refuse anything else" means garbage, not blanks. `state.w` initialises
    every numeric to `""` (logic.js:204), step 4 validates nothing and step 3 lets `rev` be blank
    whenever the range option is on (logic.js:1217) — so the resting value the adapter PATCHes IS
    the empty string, and a seller must be able to CLEAR a number once set."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json={column: "7"}, headers=signed)

    response = await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json=fields, headers=signed)
    assert response.status_code == 200, response.text
    with conn.cursor() as cur:
        cur.execute(f"SELECT {column} FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (None,)


async def test_step_three_saves_with_the_range_option_and_no_revenue(client: Any, conn: Any, member: Any) -> None:
    """The whole of M1's worked example: the design's own step-3 shape when the seller picks the
    range option, which used to be a 400 the wizard could never get past."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=3",
                                  json={"price": "1,450,000", "rev": "", "revBand": True},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 200, response.text
    with conn.cursor() as cur:
        cur.execute("SELECT price, rev, rev_disclosed FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (1450000, None, False)


@pytest.mark.parametrize(("step", "field"), [(1, "est"), (3, "price")])
async def test_a_required_numeric_field_still_refuses_a_blank(client: Any, conn: Any, member: Any, step: int, field: str) -> None:
    """The other half of M1's ruling: `est` and `price` are what `listing_submittable_ck` demands
    and what the design's own step validation guarantees before it PATCHes, so a blank one is the
    adapter disagreeing with the design — a 400 to see, not a null to absorb."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json={field: ""},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert response.json() == {"error": {"code": "BAD_REQUEST", "message": f"{field} must be a number."}}


@pytest.mark.parametrize(("step", "field"), [(1, "est"), (3, "price")])
async def test_a_required_numeric_field_still_refuses_a_json_null(
    client: Any, conn: Any, member: Any, step: int, field: str
) -> None:
    """The `null` counterpart of `test_a_required_numeric_field_still_refuses_a_blank` (A-SL18 (5),
    Info-2): only an OPTIONAL numeric treats a JSON `null` as a clear."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json={field: None},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert response.json() == {"error": {"code": "BAD_REQUEST", "message": f"{field} must be a number."}}


@pytest.mark.parametrize(("step", "fields", "column"), [
    (4, {"docs": None}, "docs"), (4, {"rooms": None}, "rooms"), (4, {"sqft": None}, "sqft"),
    (3, {"rev": None}, "rev"),
])
async def test_an_optional_numeric_field_is_cleared_by_a_json_null(
    client: Any, conn: Any, member: Any, step: int, fields: dict[str, Any], column: str
) -> None:
    """A-SL18 (5), Info-2: the SL3 fix round answered only ONE of the two clearing idioms an
    adapter might send. `{"rev": ""}` cleared the column; `{"rev": null}` was a 400. Null and blank
    are the same seller intent — `state.w`'s `""` and a `JSON.stringify` of an adapter field an
    autosave never populated are both "nothing to save here", and the wizard's PATCH must treat them
    alike."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json={column: "7"}, headers=signed)

    response = await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json=fields, headers=signed)
    assert response.status_code == 200, response.text
    with conn.cursor() as cur:
        cur.execute(f"SELECT {column} FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (None,)


@pytest.mark.parametrize("status", ["in_review", "paused", "declined", "published"])
async def test_blanking_a_required_field_on_a_submitted_listing_is_refused_not_a_500(
    client: Any, conn: Any, member: Any, status: str
) -> None:
    """A-SL13 M2. `listing_submittable_ck` forbids it, and the design invites it — the seller "may
    keep editing" an in-review listing. A CHECK the request can reach must be validated before the
    statement, or psycopg2's CheckViolation escapes as a 500."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET name='A', city='C', zip='7', type='Small animal', est=1998,"
                    " price=1, sqft=3000, state='TX', market='Austin, TX', area='C', status=%s WHERE id=%s",
                    (status, listing_id))

    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "   "},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 409, response.text
    assert response.json() == {"error": {"code": "NOT_SUBMITTABLE",
                                         "message": "A submitted listing cannot have name cleared."}}
    with conn.cursor() as cur:
        cur.execute("SELECT name, status FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == ("A", status)


async def test_a_draft_may_still_be_blanked(client: Any, conn: Any, member: Any) -> None:
    """M2's other arm: a draft is exempt from the CHECK, so clearing a field there is a save."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "A"}, headers=signed)

    assert (await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": ""},
                               headers=signed)).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (None,)


async def test_a_body_that_is_not_json_at_all_is_refused_in_the_envelope(client: Any, conn: Any, member: Any) -> None:
    """A-SL13 M3: `json.JSONDecodeError` used to escape `request.json()` as a 500."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(
        f"/api/seller/listings/{listing_id}?step=1", content=b"{not json",
        headers={**auth_headers(cookies, headers), "Content-Type": "application/json"},
    )
    assert response.status_code == 400, response.text
    assert response.json() == {"error": {"code": "BAD_JSON", "message": "Body must be JSON."}}


async def test_a_patch_body_at_exactly_the_json_limit_is_accepted(client: Any, conn: Any, member: Any) -> None:
    """A-SL18 (3), Minor-2: H1 bounded every upload's body; a chunked, length-less JSON body on this
    same authenticated PATCH surface was still read whole into memory by `request.body()` — the
    identical failure mode, on the identical threat model. `MAX_JSON_BYTES` is 64 KB and the
    boundary is EXACT (no `MULTIPART_OVERHEAD` slack, unlike the upload routes): the padding here
    is spaces before the closing brace, which `json.loads` ignores, so the body is genuinely valid
    and the PATCH genuinely applies."""
    from app.api import seller_listings as SL

    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    body = padded_json(SL.MAX_JSON_BYTES, b'{"docs": "7"}')
    assert len(body) == SL.MAX_JSON_BYTES
    response = await client.patch(
        f"/api/seller/listings/{listing_id}?step=4", content=body,
        headers={**auth_headers(cookies, headers), "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    with conn.cursor() as cur:
        cur.execute("SELECT docs FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (7,)


async def test_a_patch_body_one_byte_over_the_json_limit_is_refused(client: Any, conn: Any, member: Any) -> None:
    """The other half of the boundary: one byte past `MAX_JSON_BYTES` is a 413, not a 200."""
    from app.api import seller_listings as SL

    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    body = padded_json(SL.MAX_JSON_BYTES + 1, b'{"docs": "7"}')
    assert len(body) == SL.MAX_JSON_BYTES + 1
    response = await client.patch(
        f"/api/seller/listings/{listing_id}?step=4", content=body,
        headers={**auth_headers(cookies, headers), "Content-Type": "application/json"},
    )
    assert response.status_code == 413, response.text
    assert response.json() == {"error": {"code": "TOO_LARGE", "message": "Body must be no larger than 64 KB."}}
    with conn.cursor() as cur:
        cur.execute("SELECT docs FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == (None,)


@pytest.mark.parametrize(("step", "field", "value"), [
    (1, "est", "99999999999"), (4, "rooms", "2147483648"), (3, "price", "9" * 20),
])
async def test_a_number_beyond_its_columns_range_is_refused_in_the_envelope(
    client: Any, conn: Any, member: Any, step: int, field: str, value: str
) -> None:
    """A-SL13 L3: `integer` and `bigint` have ends, and psycopg2's NumericValueOutOfRange was a 500."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json={field: value},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "OUT_OF_RANGE"


async def test_text_carrying_a_null_character_is_refused_in_the_envelope(client: Any, conn: Any, member: Any) -> None:
    """L3's other half: psycopg2 raises "A string literal cannot contain NUL" as a plain ValueError,
    which reached the client as a 500."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "a\x00b"},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 422, response.text
    assert response.json() == {"error": {"code": "BAD_TEXT", "message": "name must not contain a null character."}}


def test_every_write_to_the_listing_table_is_owner_scoped_in_the_sql() -> None:
    """A-SL13 L1, as a drift guard rather than a request: ownership belongs in the statement, not
    only in the SELECT that preceded it in the same transaction. No exploit exists today — nothing
    reassigns `seller_id` at request time — but SL5 will copy these statements, and a write scoped
    by id alone is one refactor away from being reachable."""
    import re
    from pathlib import Path

    from app.api import seller_listings as SL

    source = " ".join(Path(SL.__file__).read_text().split())
    statements = re.findall(r"UPDATE listing SET.{0,400}?WHERE[^\"]*", source)
    assert statements, "the module must still contain the writes this test guards"
    for statement in statements:
        assert "seller_id = %" in statement, statement


async def test_the_unowned_404_is_byte_identical_to_the_missing_404(client: Any, conn: Any, member: Any) -> None:
    """A-SL13 L2. The existing test asserted only the code, so an SL4 route that invented "You do
    not own this listing." would have passed it — and that sentence is an existence oracle."""
    from uuid import uuid4

    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    _, thief_cookies, thief_headers = member(roles=("buyer", "seller"), email="sl-thief2@example.org")
    signed = auth_headers(thief_cookies, thief_headers)

    unowned = await client.get(f"/api/seller/listings/{listing_id}", headers=signed)
    missing = await client.get(f"/api/seller/listings/{uuid4()}", headers=signed)
    not_a_uuid = await client.get("/api/seller/listings/nope", headers=signed)
    assert unowned.status_code == missing.status_code == not_a_uuid.status_code == 404
    assert unowned.json() == missing.json() == not_a_uuid.json() == {
        "error": {"code": "NOT_FOUND", "message": "No such listing."}}


async def test_the_dashboard_reads_every_listings_assets_in_one_query(
    client: Any, conn: Any, member: Any, monkeypatch: Any
) -> None:
    """A-SL13 L5: `assets_of` inside the page comprehension was 201 round trips at `limit=200`."""
    from app.api import seller_listings as SL

    calls: list[list[Any]] = []
    original = SL.assets_for

    def _spy(conn_: Any, listing_ids: list[Any]) -> Any:
        calls.append(list(listing_ids))
        return original(conn_, listing_ids)

    _, cookies, headers = _seller(member)
    ids = [await _create(client, cookies, headers) for _ in range(3)]
    with conn.cursor() as cur:
        for listing_id in ids:
            cur.execute("INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256,"
                        " storage_key) VALUES (%s,'photo','1.webp','image/webp',2048,'sha',%s)",
                        (listing_id, f"listings/{listing_id}/photos/1.webp"))
    monkeypatch.setattr(SL, "assets_for", _spy)

    body = (await client.get("/api/seller/listings", headers=auth_headers(cookies, headers))).json()
    assert [len(item["assets"]) for item in body["items"]] == [1, 1, 1]
    assert len(calls) == 1 and len(calls[0]) == 3


async def test_a_seller_with_no_listings_sees_an_empty_page(client: Any, conn: Any, member: Any) -> None:
    """`assets_for`'s empty arm, and the first thing a new seller's dashboard asks for."""
    _, cookies, headers = _seller(member)
    response = await client.get("/api/seller/listings", headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


async def test_the_create_rate_limit_is_per_account(client: Any, conn: Any, redis: Any, member: Any, monkeypatch: Any) -> None:
    """A-SL13 L4: D17 named three buckets and left `create` out, so an authenticated seller could
    mint unbounded rows."""
    from app.api import seller_listings as SL

    monkeypatch.setattr(SL, "LISTING_CREATE", (1, 3600))
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    assert (await client.post("/api/seller/listings", headers=signed)).status_code == 201

    refused = await client.post("/api/seller/listings", headers=signed)
    assert refused.status_code == 429 and refused.json()["error"]["code"] == "RATE_LIMITED"


# --- Task SL5: submit, and the dashboard's own three transitions (spec 2026-09-08 D2/D4) -------


async def _submittable(client: Any, signed: dict[str, str], listing_id: str) -> None:
    """The three steps the design's own client-side validation guards (logic.js:1215-1217), plus
    the fourth `listing_submittable_ck`/`REQUIRED_TO_SUBMIT` now names (A-SL33 (1)) — the least a
    listing can carry and still be submitted."""
    await client.patch(f"/api/seller/listings/{listing_id}?step=1",
                       json={"name": "Hill Country Animal Hospital", "type": "Small animal", "est": "1998"},
                       headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=2", json={"city": "Cedar Park", "zip": "78613"},
                       headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": "1,450,000"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"sqft": "3000"}, headers=signed)


async def _ready(client: Any, member: Any) -> tuple[str, dict[str, str]]:
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    listing_id = await _create(client, cookies, headers)
    await _submittable(client, signed, listing_id)
    return listing_id, signed


def _status(conn: Any, listing_id: str) -> tuple[Any, ...]:
    with conn.cursor() as cur:
        cur.execute("SELECT status, submitted_at FROM listing WHERE id=%s", (listing_id,))
        row: tuple[Any, ...] = cur.fetchone()
    return row


def _actions(conn: Any, listing_id: str) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute("SELECT action, before, after FROM audit_log WHERE target_type='listing' AND target_id=%s"
                    " ORDER BY id", (str(listing_id),))
        rows: list[tuple[Any, ...]] = cur.fetchall()
    return rows


def _outbox(conn: Any) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute("SELECT template, to_email, idempotency_key FROM email_outbox ORDER BY id")
        rows: list[tuple[Any, ...]] = cur.fetchall()
    return rows


async def test_submit_moves_a_draft_into_review_and_stamps_it(client: Any, conn: Any, member: Any) -> None:
    """The wizard's Submit (logic.js:1236), persisted: `in_review`, stamped, audited, and the
    seller told — the design's submitted card is the mail's own copy."""
    listing_id, signed = await _ready(client, member)
    response = await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "in_review"
    status, stamped = _status(conn, listing_id)
    assert status == "in_review" and stamped is not None
    assert _actions(conn, listing_id) == [("listing.submit", {"status": "draft"}, {"status": "in_review"})]
    assert [(template, to) for template, to, _key in _outbox(conn)] == [
        ("listing_submitted", "sl-seller@example.org")]


async def test_submit_re_validates_the_three_rules_the_design_enforces_client_side(
    client: Any, conn: Any, member: Any
) -> None:
    """logic.js:1215-1217, server-side. A client check is a courtesy, and this one guards
    `listing_submittable_ck` — an unvalidated submit meets the CHECK as a 500."""
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    listing_id = await _create(client, cookies, headers)

    async def _refusal() -> tuple[int, str, str]:
        r = await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)
        return r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]

    assert await _refusal() == (422, "INCOMPLETE", "A practice name is needed before this listing can be submitted.")
    await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "Hill Country"}, headers=signed)
    assert await _refusal() == (422, "INCOMPLETE", "A year established is needed before this listing can be submitted.")
    await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"est": "1998", "type": "Small animal"}, headers=signed)
    assert await _refusal() == (422, "INCOMPLETE", "A city is needed before this listing can be submitted.")
    await client.patch(f"/api/seller/listings/{listing_id}?step=2", json={"city": "Cedar Park"}, headers=signed)
    assert await _refusal() == (422, "INCOMPLETE", "A ZIP code is needed before this listing can be submitted.")
    await client.patch(f"/api/seller/listings/{listing_id}?step=2", json={"zip": "78613"}, headers=signed)
    assert await _refusal() == (422, "INCOMPLETE", "An asking price is needed before this listing can be submitted.")
    await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": "1450000", "revBand": False}, headers=signed)
    # The design's third rule is the compound one: an asking price AND either a revenue figure or
    # the range option. `revBand` off means `rev_disclosed` true, so a blank `rev` is the state the
    # wizard refuses to advance from.
    assert await _refusal() == (
        422, "INCOMPLETE",
        "An exact revenue figure — or the range option — is needed before this listing can be submitted.")
    await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"rev": "2100000"}, headers=signed)
    # A-SL33 (1): sqft joins the design's own three rules — not one of them, but the fourth
    # `listing_publishable_ck` (034) now demands, named here rather than met as a database error
    # once a reviewer tries to publish.
    assert await _refusal() == (422, "INCOMPLETE", "Approximate square feet is needed before this listing can be submitted.")
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"sqft": "3000"}, headers=signed)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)).status_code == 200


async def test_a_listing_with_no_type_is_refused_rather_than_meeting_the_check(
    client: Any, conn: Any, member: Any
) -> None:
    """A-SL13 M2's rule applied to submit: `listing_submittable_ck` demands `type` too, and the
    per-step PATCH takes step 1's fields one at a time — so a listing can reach Submit with a name,
    a year, a city, a ZIP and a price and no type at all. The design's select always has a value,
    so no wizard user meets this; an adapter sending one field at a time does."""
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    listing_id = await _create(client, cookies, headers)
    await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "Hill Country", "est": "1998"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=2", json={"city": "Cedar Park", "zip": "78613"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": "1450000"}, headers=signed)
    response = await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "INCOMPLETE", "message": "A practice type is needed before this listing can be submitted."}
    assert _status(conn, listing_id) == ("draft", None)


# --- A-SL33 (1): the Browse-rendering crash on a published listing with no floor area -------------
#
# The SL8 review's Critical finding: `logic.js` calls `p.sqft.toLocaleString()` unconditionally at
# six sites reachable from a published listing (desktop and mobile Browse, the detail screen), and
# nothing anywhere required `sqft` before a listing could be published — not `listing_submittable_ck`
# (030, submit's own guard), not `listing_publishable_ck` (030, the buyer-surface guard), and no
# admin decide branch. Migration 034 widens `listing_publishable_ck`; this is the SUBMIT half of
# the two-layer fix (`app/api/admin_listings.py::test_publish_also_requires_square_footage_...`
# is the decide half) — a seller is told which field is missing, never left to meet a database
# error when a reviewer later tries to publish.


async def test_submit_also_requires_square_footage_named_in_the_envelope(client: Any, conn: Any, member: Any) -> None:
    """`_ready()` now makes a genuinely submittable listing (A-SL33's fixture fix), so this proves
    the refusal by CLEARING sqft first — `sqft` is in `OPTIONAL_NUMERIC`, exactly the same clearing
    idiom a seller's own blank step-4 field uses."""
    listing_id, signed = await _ready(client, member)
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"sqft": ""}, headers=signed)
    refused = await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)
    assert refused.status_code == 422
    assert refused.json()["error"] == {
        "code": "INCOMPLETE", "message": "Approximate square feet is needed before this listing can be submitted."}
    assert _status(conn, listing_id) == ("draft", None)
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"sqft": "3000"}, headers=signed)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)).status_code == 200


@pytest.mark.parametrize("status", ["paused", "published", "withdrawn"])
async def test_submit_is_legal_from_draft_declined_and_in_review_and_from_nothing_else(
    client: Any, conn: Any, member: Any, status: str
) -> None:
    """The lifecycle table (D2). A paused or published listing is already through review, and a
    withdrawn one is terminal."""
    listing_id, signed = await _ready(client, member)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status=%s, state='TX', market='Austin, TX', area='Cedar Park'"
                    " WHERE id=%s", (status, listing_id))
    response = await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)
    assert response.status_code == 409 and response.json()["error"]["code"] == "STATE"
    assert _status(conn, listing_id)[0] == status


@pytest.mark.parametrize("status", ["draft", "declined", "in_review"])
async def test_submit_is_legal_from_each_of_the_three_states_that_allow_it(
    client: Any, conn: Any, member: Any, status: str
) -> None:
    listing_id, signed = await _ready(client, member)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status=%s WHERE id=%s", (status, listing_id))
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)).status_code == 200
    assert _status(conn, listing_id)[0] == "in_review"


async def test_submit_is_idempotent_within_one_review_cycle(client: Any, conn: Any, member: Any) -> None:
    """The seller "may keep editing while it waits" (the submitted card), so pressing Submit twice
    is an ordinary thing to do. The stamp is what the outbox key is built from, so not re-stamping
    is what makes the second press write no second email."""
    listing_id, signed = await _ready(client, member)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)).status_code == 200
    first = _status(conn, listing_id)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)).status_code == 200
    assert _status(conn, listing_id) == first
    assert [template for template, _to, _key in _outbox(conn)] == ["listing_submitted"]
    assert _outbox(conn)[0][2] == f"{listing_id}:listing_submitted:{first[1].isoformat()}"


async def test_pause_republish_and_withdraw_are_the_dashboards_own_three(
    client: Any, conn: Any, member: Any
) -> None:
    """logic.js:958's `setListingStatus`, persisted. Republish needs no re-review — the design's
    admin footnote calls unpublishing "immediate and reversible" — so it goes straight back to
    `published` rather than into the queue."""
    listing_id, signed = await _ready(client, member)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', state='TX', market='Austin, TX',"
                    " area='Cedar Park' WHERE id=%s", (listing_id,))
    for action, after in (("pause", "paused"), ("republish", "published"), ("withdraw", "withdrawn")):
        response = await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": action},
                                     headers=signed)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == after
        assert _status(conn, listing_id)[0] == after
    assert _actions(conn, listing_id) == [
        ("listing.pause", {"status": "published"}, {"status": "paused"}),
        ("listing.republish", {"status": "paused"}, {"status": "published"}),
        ("listing.withdraw", {"status": "published"}, {"status": "withdrawn"}),
    ]


async def test_a_transition_from_an_illegal_state_is_409_and_changes_nothing(
    client: Any, conn: Any, member: Any
) -> None:
    """A draft is not on the market to pause, a published listing is not paused to republish, and
    a withdrawn one accepts nothing at all."""
    listing_id, signed = await _ready(client, member)
    refused = await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "pause"}, headers=signed)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "STATE"
    assert _status(conn, listing_id)[0] == "draft"

    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', state='TX', market='Austin, TX',"
                    " area='Cedar Park' WHERE id=%s", (listing_id,))
    refused = await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "republish"}, headers=signed)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "STATE"
    assert _status(conn, listing_id)[0] == "published"

    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='withdrawn' WHERE id=%s", (listing_id,))
    for action in ("pause", "republish", "withdraw"):
        refused = await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": action}, headers=signed)
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "STATE", action
    assert _actions(conn, listing_id) == []


async def test_an_action_the_dashboard_does_not_offer_is_refused_in_the_envelope(
    client: Any, conn: Any, member: Any
) -> None:
    listing_id, signed = await _ready(client, member)
    for body in ({"action": "publish"}, {"action": ""}, {"action": 3}, {}):
        response = await client.post(f"/api/seller/listings/{listing_id}/status", json=body, headers=signed)
        assert response.status_code == 400, body
        assert response.json()["error"]["code"] == "BAD_REQUEST"
        assert "pause" in response.json()["error"]["message"]


async def test_withdraw_is_terminal(client: Any, conn: Any, member: Any) -> None:
    """"Withdrawn listings keep their history for reporting but no longer appear in search"
    (logic.js:1061): the row SURVIVES, and every write refuses."""
    listing_id, signed = await _ready(client, member)
    assert (await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "withdraw"},
                              headers=signed)).status_code == 200
    for response in (
        await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "Renamed"}, headers=signed),
        await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed),
        await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "republish"}, headers=signed),
        await client.patch(f"/api/seller/listings/{listing_id}/photos", json={"ids": []}, headers=signed),
    ):
        assert response.status_code == 409 and response.json()["error"]["code"] == "STATE", response.text
    assert (await client.get(f"/api/seller/listings/{listing_id}", headers=signed)).status_code == 200
    assert _status(conn, listing_id)[0] == "withdrawn"


async def test_the_seller_transition_actions_name_no_permission_and_are_not_watched(
    client: Any, conn: Any, dist: Any
) -> None:
    """D8. The four actions name no permission BY DESIGN — exactly like `applications.submit` —
    because `listing.manage_own` is not in `AUDITED` and the wizard's autosave rides on it. The
    drift test therefore never sees these routes, and there is no list to add them to; this says so
    on purpose. "Not watched", not "not there": the route IS mounted and IS guarded."""
    from app.api import seller_listings as SL
    from app.auth import permissions as PM
    from app.main import create_app
    from tests.auth.test_permissions import _permissions_of
    from tests.conftest import walk_routes

    four = (SL.SUBMIT_ACTION, SL.PAUSE_ACTION, SL.REPUBLISH_ACTION, SL.WITHDRAW_ACTION)
    assert four == ("listing.submit", "listing.pause", "listing.republish", "listing.withdraw")
    assert not set(four) & set(PM.MATRIX)
    assert "listing.manage_own" not in PM.AUDITED
    routes = list(walk_routes(create_app(dist=dist).routes))
    watched = {(method, path) for method, path, route in routes
               if any(perm in PM.AUDITED for perm in _permissions_of(route))}
    guarded = {(method, path) for method, path, route in routes
               if "listing.manage_own" in _permissions_of(route)}
    for route in (("POST", "/api/seller/listings/{listing_id}/submit"),
                  ("POST", "/api/seller/listings/{listing_id}/status")):
        assert route not in watched, route
        assert route in guarded, route


async def test_every_transition_drops_the_listings_cache_after_the_commit(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """D16. Unlike the autosave (A-SL13 L6), unconditionally: a transition is a deliberate act
    bounded by `LISTING_SUBMIT`, three of the four move a row onto or off the market, and a SCAN
    that finds nothing costs nothing."""
    listing_id, signed = await _ready(client, member)

    async def _drops(call: Any) -> bool:
        redis.set("listings:v1:::50", b'{"items": []}')
        redis.set("session:keep-me", b"x")
        assert (await call).status_code == 200
        assert redis.get("session:keep-me") == b"x"
        return redis.get("listings:v1:::50") is None

    assert await _drops(client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed))
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', state='TX', market='Austin, TX',"
                    " area='Cedar Park' WHERE id=%s", (listing_id,))
    for action in ("pause", "republish", "withdraw"):
        assert await _drops(
            client.post(f"/api/seller/listings/{listing_id}/status", json={"action": action}, headers=signed)), action


async def test_a_non_owner_cannot_submit_or_transition_another_sellers_listing(
    client: Any, conn: Any, member: Any
) -> None:
    """D7, on the two new routes: 404, never 403."""
    listing_id, _signed = await _ready(client, member)
    _, thief_cookies, thief_headers = member(roles=("buyer", "seller"), email="sl-thief@example.org")
    stolen = auth_headers(thief_cookies, thief_headers)
    for response in (
        await client.post(f"/api/seller/listings/{listing_id}/submit", headers=stolen),
        await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "withdraw"}, headers=stolen),
        await client.post("/api/seller/listings/not-a-uuid/submit", headers=stolen),
    ):
        assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


async def test_the_transition_rate_limit_is_per_account(
    client: Any, conn: Any, redis: Any, member: Any, monkeypatch: Any
) -> None:
    """D17/A-SL16 M3: every write is rate-limited, the two transitions included."""
    from app.api import seller_listings as SL

    monkeypatch.setattr(SL, "LISTING_SUBMIT", (1, 3600))
    listing_id, signed = await _ready(client, member)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)).status_code == 200
    refused = await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)
    assert refused.status_code == 429 and refused.json()["error"]["code"] == "RATE_LIMITED"
    # A separate bucket from `submit`, so a seller who pauses a listing has not spent their
    # submissions — the first `status` call still lands.
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', state='TX', market='Austin, TX',"
                    " area='Cedar Park' WHERE id=%s", (listing_id,))
    assert (await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "pause"},
                              headers=signed)).status_code == 200


# --- Fix round 1 (A-SL19): paused is published-but-hidden ---------------------------------------


async def test_an_edit_to_a_paused_listing_re_enters_review_and_republish_is_then_refused(
    client: Any, conn: Any, member: Any
) -> None:
    """A-SL19 (1), Major-1. Pause → edit → republish put unreviewed content back on the market: the
    D3 arm fired on `published` only, so an edit to a paused listing changed the row, wrote NO
    audit trail, and `republish` returned it to `published` without a reviewer ever seeing it.

    A paused listing is published-but-hidden, so an edit to one re-enters review exactly as an edit
    to a published one does — and `republish` is then refused, because the row is no longer paused.
    An untouched pause/republish stays "immediate and reversible", which is all the design's
    footnote promises."""
    listing_id, signed = await _ready(client, member)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', state='TX', market='Austin, TX',"
                    " area='Cedar Park' WHERE id=%s", (listing_id,))
    assert (await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "pause"},
                              headers=signed)).status_code == 200

    assert (await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "Renamed"},
                               headers=signed)).status_code == 200
    assert _status(conn, listing_id)[0] == "in_review"
    assert _actions(conn, listing_id)[-1] == ("listing.edit", {"status": "paused"}, {"status": "in_review"})

    refused = await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "republish"},
                                headers=signed)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "STATE"
    assert _status(conn, listing_id)[0] == "in_review"


async def test_an_asset_write_to_a_paused_listing_re_enters_review(client: Any, conn: Any, member: Any) -> None:
    """A-SL19 (1) on the asset arm — A-SL15 (1)'s "assets are edits" reaches `paused` too. The
    reorder route needs no object store, so it is the cheapest of the four asset writes to prove
    `take_off_market`'s widened guard with."""
    listing_id, signed = await _ready(client, member)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='paused', state='TX', market='Austin, TX',"
                    " area='Cedar Park' WHERE id=%s", (listing_id,))
    assert (await client.patch(f"/api/seller/listings/{listing_id}/photos", json={"ids": []},
                               headers=signed)).status_code == 200
    assert _status(conn, listing_id)[0] == "in_review"
    assert _actions(conn, listing_id) == [("listing.edit", {"status": "paused"}, {"status": "in_review"})]


async def test_an_edit_to_a_paused_listing_leaves_the_browse_cache_alone(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """A paused listing is in no published payload, so there is nothing to invalidate — the cache
    drop stays keyed on `published` (A-SL19 (1); A-SL13 L6's rule, unchanged)."""
    listing_id, signed = await _ready(client, member)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='paused', state='TX', market='Austin, TX',"
                    " area='Cedar Park' WHERE id=%s", (listing_id,))
    redis.set("listings:v1:::50", b'{"items": []}')
    assert (await client.patch(f"/api/seller/listings/{listing_id}?step=1", json={"name": "Renamed"},
                               headers=signed)).status_code == 200
    assert redis.get("listings:v1:::50") == b'{"items": []}'


# --- Controller amendment A-SL21 (2026-09-09; ruling on SL6's NEEDS_CONTEXT) ---------------------
# "A seeded listing becomes the seller's own the moment the seller writes to it: the first seller
# write of any kind ... flips `listing.source` from 'seed' to 'seller' in the same transaction, so
# the seeder's existing `WHERE source = 'seed'` scope never overwrites a seller-edited row, `status`
# can never be reset to `published` without review, and `--reset` never deletes it."

_SEED_INSERT = """
INSERT INTO listing (slug, name, street, city, state, zip, hours, status, location_disclosed,
                     name_disclosed, area, type, market, est, price, sqft, source, seller_id,
                     photos, photo_captions)
VALUES (%(slug)s, 'Demo Hospital', '1 Main St', 'Austin', 'TX', '78701', '24/7', %(status)s,
        true, true, 'Austin', 'Small animal', 'Austin, TX', 1998, 1450000, 3000, 'seed', %(seller)s,
        %(photos)s::jsonb, %(photo_captions)s::jsonb)
RETURNING id
"""


def _seed_listing(conn: Any, seller_id: Any, status: str = "published",
                  photos: list[str | None] | None = None,
                  photo_captions: list[str | None] | None = None) -> str:
    """One of the eighteen as `scripts/seed_listings.py` writes them and as D25 now owns them:
    `source='seed'` with a real `seller_id`. The same row shape as
    `tests/api/test_listing_assets.py::_SEED_INSERT`, with the owner and the status as arguments,
    plus the two positional arrays SL7b's click-to-caption route reads and writes (A-SL25 (10)):
    `photos` (the seeder's own paths) and `photo_captions` (the seeder's own inventory captions,
    A-L11) — both empty unless a test names its own, so every existing caller is unaffected."""
    with conn.cursor() as cur:
        cur.execute(_SEED_INSERT, {
            "slug": f"seed-{uuid4().hex[:8]}", "status": status, "seller": seller_id,
            "photos": json.dumps(photos or []), "photo_captions": json.dumps(photo_captions or []),
        })
        return str(cur.fetchone()[0])


def _source(conn: Any, listing_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT source FROM listing WHERE id=%s", (listing_id,))
        return str(cur.fetchone()[0])


@pytest.mark.parametrize(("write", "status"), [
    ("patch", "published"),
    ("submit", "draft"),
    ("pause", "published"),
    ("republish", "paused"),
    ("withdraw", "published"),
])
async def test_a_seller_write_claims_a_seeded_listing_as_their_own(
    client: Any, conn: Any, redis: Any, member: Any, write: str, status: str
) -> None:
    """A-SL21, the wizard and the three transitions. Parametrised over the write KINDS rather than
    written once for the PATCH, because the seeder's guarantee is only as good as the write path
    that forgot to claim the row."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, status=status)
    signed = auth_headers(cookies, headers)
    assert _source(conn, listing_id) == "seed"

    if write == "patch":
        response = await client.patch(f"/api/seller/listings/{listing_id}?step=1",
                                      json={"name": "Renamed by its seller"}, headers=signed)
    elif write == "submit":
        response = await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)
    else:
        response = await client.post(f"/api/seller/listings/{listing_id}/status",
                                     json={"action": write}, headers=signed)
    assert response.status_code == 200, response.text
    assert _source(conn, listing_id) == "seller"


async def test_a_refused_write_leaves_a_seeded_listing_a_seed(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """The claim is in the write's own transaction, so a write that refuses claims nothing: a
    `pause` of a listing that is not published rolls back with the row exactly as it was."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, status="paused")
    response = await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "pause"},
                                 headers=auth_headers(cookies, headers))
    assert response.status_code == 409, response.text
    assert _source(conn, listing_id) == "seed"


async def test_claiming_is_idempotent_and_never_reaches_another_sellers_row(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """Twice is once: the second write finds `source='seller'` already and changes nothing. And the
    claim carries the owner predicate every other write in this module carries, so it can only ever
    touch the row the request already proved is the caller's."""
    account_id, cookies, headers = _seller(member)
    other, _other_cookies, _other_headers = member(roles=("buyer", "seller"), email="sl-a-sl21-other@example.org")
    mine = _seed_listing(conn, account_id)
    theirs = _seed_listing(conn, other)
    signed = auth_headers(cookies, headers)

    for name in ("First edit", "Second edit"):
        response = await client.patch(f"/api/seller/listings/{mine}?step=1", json={"name": name}, headers=signed)
        assert response.status_code == 200, response.text
    assert _source(conn, mine) == "seller"
    assert _source(conn, theirs) == "seed", "another seller's seeded listing is untouched"


def test_the_source_predicate_is_what_makes_claiming_a_no_op(conn: Any, member: Any) -> None:
    """SL9 hardening (A-SL34 (2); SL6 re-review's own ⚠️): every test above proves a SECOND write to
    a seed-sourced row changes nothing, but that is idempotency, not the predicate — they would
    pass identically if `claim_from_seed`'s UPDATE read `WHERE id = %s AND seller_id = %s` with no
    `source` guard at all, because by the second call `source` is already `'seller'`. This isolates
    `AND source = 'seed'` directly, on a row that was NEVER seeded (`source='seller'` from its own
    `create()`, the ordinary case): Postgres writes a fresh tuple version — and so a fresh `xmin` —
    for every UPDATE statement that MATCHES a row, even one that sets a column to the value it
    already holds. An unchanged `xmin` after the call is proof the predicate excluded the row from
    the statement entirely; a genuinely seeded sibling, called the same way, changes it."""
    from app.api.seller_listings import claim_from_seed
    from app.auth import sessions as S

    account_id, _cookies, _headers = _seller(member)
    principal = S.Principal(account_id, "active", frozenset({"seller"}), None, "session", "h")

    def _xmin(listing_id: Any) -> str:
        with conn.cursor() as cur:
            cur.execute("SELECT xmin::text FROM listing WHERE id = %s", (listing_id,))
            return str(cur.fetchone()[0])

    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status, seller_id) VALUES (%s, 'seller', 'draft', %s)"
                    " RETURNING id", (f"listing-{uuid4().hex[:8]}", account_id))
        never_seeded = cur.fetchone()[0]

    before = _xmin(never_seeded)
    claim_from_seed(conn, {"id": never_seeded}, principal)
    assert _source(conn, str(never_seeded)) == "seller"
    assert _xmin(never_seeded) == before, "a row whose source was never 'seed' must not be touched by the UPDATE"

    seeded = _seed_listing(conn, account_id)
    seeded_before = _xmin(seeded)
    claim_from_seed(conn, {"id": seeded}, principal)
    assert _xmin(seeded) != seeded_before, "the same call, in the same shape, DOES touch a genuinely seeded row"


# --- A-SL25 (10) / SL7b: click-to-caption for an EXISTING photograph, seeded ones included --------
# `PATCH /api/seller/listings/{id}/photos/{n}` — POSITIONAL, `n` 1-based (the buyer's own
# `GET .../photos/{n}` and `photo_file`'s convention) — writes `listing.photo_captions[n]` for a
# SEED entry (a path in `listing.photos`, not an asset id): the caption route by asset id has
# nothing to match one against, so until this a seeded photograph could never be re-described. A
# seed entry and an asset entry are told apart by the VALUE ITSELF, `app/api/listings.py::
# get_listing_photo`'s own rule ("a seed entry always contains a '/'... told apart by the value
# itself rather than by a second query") — an asset id is a bare uuid and never contains one.

async def test_a_seed_photograph_shows_the_inventorys_caption_until_the_seller_describes_it(
    client: Any, conn: Any, member: Any
) -> None:
    """The wizard tile's default is the seed inventory's own caption.
    `abc_animal_hospital/1.webp` is the committed index's own fixture entry (`test_listing_assets.py
    ::test_the_seed_captions_are_read_from_the_committed_index`), captioned "Exterior — front"."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=["abc_animal_hospital/1.webp"])
    read = await client.get(f"/api/seller/listings/{listing_id}", headers=auth_headers(cookies, headers))
    assert read.json()["photos"] == [
        {"id": "abc_animal_hospital/1.webp", "name": "Exterior — front", "source": "seed", "position": 1}
    ]


async def test_the_listings_own_caption_wins_over_the_seed_inventory(client: Any, conn: Any, member: Any) -> None:
    """A-SL25 (10)'s pre-flight fact, the RED this fixes: `photo_tiles()` named a seed photograph
    from the seed INVENTORY alone, never from the listing's own `photo_captions` column — so a
    positional write would reach Browse (`serialise` reads that column) but never the wizard tile.
    The listing's own words win, exactly as an uploaded asset's own caption already does."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=["abc_animal_hospital/1.webp"],
                               photo_captions=["The reception desk at sunrise"])
    read = await client.get(f"/api/seller/listings/{listing_id}", headers=auth_headers(cookies, headers))
    assert read.json()["photos"] == [
        {"id": "abc_animal_hospital/1.webp", "name": "The reception desk at sunrise", "source": "seed", "position": 1}
    ]


async def test_an_empty_seed_slot_carries_no_tile_and_does_not_shift_position(
    client: Any, conn: Any, member: Any
) -> None:
    """A-L10's empty slot (a JSON `null`) is still no tile; the photograph after it keeps ITS OWN
    position, 2, not 1 — the wizard tile's position must match `photo_captions`' own index."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=[None, "abc_animal_hospital/1.webp"])
    read = await client.get(f"/api/seller/listings/{listing_id}", headers=auth_headers(cookies, headers))
    assert read.json()["photos"] == [
        {"id": "abc_animal_hospital/1.webp", "name": "Exterior — front", "source": "seed", "position": 2}
    ]


async def test_the_owner_can_describe_a_seeded_photograph_positionally(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=["abc_animal_hospital/1.webp"])
    signed = auth_headers(cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}/photos/1",
                                  json={"caption": "  The lobby, freshly painted  "}, headers=signed)
    assert response.status_code == 200, response.text
    assert response.json()["photos"] == [
        {"id": "abc_animal_hospital/1.webp", "name": "The lobby, freshly painted", "source": "seed", "position": 1}
    ]
    with conn.cursor() as cur:
        cur.execute("SELECT photo_captions FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone()[0] == ["The lobby, freshly painted"]


async def test_describing_pads_photo_captions_to_the_length_of_photos(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """A-SL25 (7)'s one-caption-per-photograph contract, on the WRITE side: describing the SECOND
    of two photographs when the column has never been written pads the first with "" rather than
    shifting the new caption onto the wrong photograph."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=["a/1.webp", "a/2.webp"])
    signed = auth_headers(cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}/photos/2",
                                  json={"caption": "The exam room"}, headers=signed)
    assert response.status_code == 200, response.text
    with conn.cursor() as cur:
        cur.execute("SELECT photo_captions FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone()[0] == ["", "The exam room"]


async def test_a_blank_caption_clears_a_seed_photographs_own_description(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """Blank and null are one intent (A-SL18, Info), exactly as `PATCH .../assets/{id}` already
    treats them: the seller is taking the description back, and the tile returns to the seed
    inventory's own caption."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=["abc_animal_hospital/1.webp"],
                               photo_captions=["Something the seller wrote"])
    signed = auth_headers(cookies, headers)
    for blank in ("", None):
        response = await client.patch(f"/api/seller/listings/{listing_id}/photos/1",
                                      json={"caption": blank}, headers=signed)
        assert response.status_code == 200, response.text
        assert response.json()["photos"][0]["name"] == "Exterior — front"


async def test_the_positional_route_refuses_a_position_out_of_range(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=["a/1.webp"])
    signed = auth_headers(cookies, headers)
    for n in (0, 2, 99):
        response = await client.patch(f"/api/seller/listings/{listing_id}/photos/{n}",
                                      json={"caption": "x"}, headers=signed)
        assert response.status_code == 404, (n, response.text)
        assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_the_positional_route_refuses_an_empty_slot(client: Any, conn: Any, redis: Any, member: Any) -> None:
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=[None, "a/2.webp"])
    signed = auth_headers(cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}/photos/1",
                                  json={"caption": "x"}, headers=signed)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_the_positional_route_refuses_an_asset_backed_entry(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """A photograph the seller has already uploaded has its own caption route, `PATCH
    .../assets/{id}`; the positional one is for a seed PATH and refuses an asset id — told apart by
    the value itself (D15's own rule, `app/api/listings.py::get_listing_photo`), never by a second
    query. 409, not 404: the photograph at that position is real, just not this route's to name."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=["11111111-1111-1111-1111-111111111111"])
    signed = auth_headers(cookies, headers)
    response = await client.patch(f"/api/seller/listings/{listing_id}/photos/1",
                                  json={"caption": "x"}, headers=signed)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "STATE"


async def test_a_non_owner_gets_404_on_the_positional_caption_route(client: Any, conn: Any, member: Any) -> None:
    """D7: 404, never 403."""
    account_id, _cookies, _headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=["a/1.webp"])
    _, thief_cookies, thief_headers = member(roles=("buyer", "seller"), email="sl-sl7b-thief@example.org")
    response = await client.patch(f"/api/seller/listings/{listing_id}/photos/1", json={"caption": "x"},
                                  headers=auth_headers(thief_cookies, thief_headers))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_the_positional_route_claims_a_seeded_listing(client: Any, conn: Any, redis: Any, member: Any) -> None:
    """A-SL21: the first seller write of any kind claims the row."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=["a/1.webp"])
    assert _source(conn, listing_id) == "seed"
    response = await client.patch(f"/api/seller/listings/{listing_id}/photos/1", json={"caption": "x"},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 200, response.text
    assert _source(conn, listing_id) == "seller"


async def test_the_positional_route_takes_a_published_listing_off_market_and_drops_the_cache(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """D3/D16: describing a photograph is an EDIT, exactly as the asset caption route is (A-SL15
    (1)); a published listing re-enters review and the Browse cache is dropped."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, status="published", photos=["a/1.webp"])
    redis.set("listings:v1:::50", b'{"items": []}')
    response = await client.patch(f"/api/seller/listings/{listing_id}/photos/1", json={"caption": "x"},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "in_review"
    assert redis.get("listings:v1:::50") is None


async def test_a_withdrawn_listings_photograph_may_not_be_described(client: Any, conn: Any, member: Any) -> None:
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, status="withdrawn", photos=["a/1.webp"])
    response = await client.patch(f"/api/seller/listings/{listing_id}/photos/1", json={"caption": "x"},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE"


async def test_the_positional_caption_is_refused_when_it_is_not_text(client: Any, conn: Any, member: Any) -> None:
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, account_id, photos=["a/1.webp"])
    response = await client.patch(f"/api/seller/listings/{listing_id}/photos/1", json={"caption": 123},
                                  headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "caption must be text."


async def test_serialise_draft_never_emits_a_presentational_field(client: Any, conn: Any, member: Any) -> None:
    """A-SL25 (4), on the SL7 re-review's Minor-A.

    `frontend/src/listings/seller.ts`'s `toDashboardRow` has a `DesignRow` arm: a row that already
    carries `title`, `meta` and `note` is taken as it stands, and every other row has all three
    DERIVED from the columns (`money()`, the `NOTE` map, `decline_reason` under the Declined pill).
    That arm exists for the oracle alone — `frontend/tests/design-seller-listings.mjs` serves the
    design's own four dashboard fixtures, whose prose no column can produce (A-SL2) — and it is
    inert in production only because this endpoint never sends any of the three.

    Nothing pinned that. The day a `title` column reaches the seller serialiser, every dashboard
    row would silently switch to the design arm and lose `decline_reason`, the state notes and the
    money formatting, with no test failing anywhere. This is that test: if you add one of these
    three to `serialise_draft`, delete the `DesignRow` arm in the same commit."""
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    listing_id = (await client.post("/api/seller/listings", headers=signed)).json()["id"]
    draft = (await client.get(f"/api/seller/listings/{listing_id}", headers=signed)).json()

    assert {"title", "meta", "note"}.isdisjoint(draft), (
        "serialise_draft now emits a field toDashboardRow's DesignRow arm branches on; that arm is"
        " for the oracle's stub only and must go with this change"
    )
    # Not vacuous: the payload really is the draft, with the keys the dashboard mapping reads.
    assert {"id", "status", "city", "type", "price", "docs", "sqft", "decline_reason"} <= set(draft)


# --- A-SL26 (1) / A-SL27: the adapter's step→fields map and this module's are ONE table ----------
# CRITICAL-B, round-2 re-review: `columns_for`'s whitelist is one-directional and total by ruling
# D10 — "a mis-sent field is a 400 rather than a silent no-op, because ... a mis-sent field means
# the adapter and this table disagree — which is a bug to see, not to absorb". Nothing made that
# disagreement visible. The design's Continue hands the adapter the whole of `state.w` and the
# adapter forwarded it, so every Continue was `400 step 1 does not accept anon, bldg, city, …` and
# not one field a seller typed was ever written — invisible to pytest (which calls the endpoint
# with correct bodies), to vitest (which stubbed a pre-filtered body) and to the pixel and DOM
# oracles (whose wizard captures move by the design's step rail, which patches nothing).
#
# The adapter's half of the table lives in ONE data file, `frontend/src/listings/step-fields.json`,
# which `frontend/src/listings/seller.ts` imports as `STEP_FIELDS` and `REQUIRED_NUMERIC` and this
# module reads with `json.load` — no regex over TypeScript, so a reformatted literal cannot fail
# the pin and a renamed constant cannot make it vacuous (round-3 re-review INFO-K, fixed at source
# by the A-SL27 addendum). The cases below are the pin: one compares the two step tables step by
# step and through `columns_for`'s own key→column mapping, one spends a real request per step with
# exactly the payload the adapter would send, and one derives the partial-mode omission list from
# this module's own numeric tables so neither side hand-types it (A-SL27 (2)).

STEP_FIELDS_JSON = ROOT / "frontend" / "src" / "listings" / "step-fields.json"

#: A design-shaped value per wizard field — what `state.w` (logic.js:204) actually holds after a
#: seller has filled the wizard in, so the payloads below are the ones the adapter really sends.
DESIGN_W: dict[str, Any] = {
    "name": "ABC Animal Hospital", "type": "Small animal", "est": "1998",
    "ownership": "Sole proprietor", "city": "Bastrop", "zip": "78602", "anon": True,
    "price": "860,000", "rev": "700,000", "revBand": False,
    "docs": "2", "rooms": "4", "sqft": "3,000", "hours": "Mon-Fri 8-6", "desc": "Dentistry",
    "bldg": "Included", "facilityType": "Standalone", "facility": "Two surgical suites",
    "docsLocked": True,
}


def adapter_tables() -> dict[str, Any]:
    """`frontend/src/listings/step-fields.json`, exactly as the adapter imports it.

    Read off disk rather than duplicated here, for `tests/test_docs.py`'s own reason: a copy is a
    third table to keep in step, and the whole point of this pin is that there are two."""
    with STEP_FIELDS_JSON.open(encoding="utf-8") as handle:
        tables: dict[str, Any] = json.load(handle)
    return tables


def adapter_step_fields() -> dict[int, list[str]]:
    """The adapter's `STEP_FIELDS`: the data file's `steps`, keyed by the step as an integer."""
    return {int(step): list(keys) for step, keys in adapter_tables()["steps"].items()}


#: The design's own initial `state.w` (logic.js:204), the four enum defaults `toWizardState`
#: leaves standing once it has left every null column alone (A-SL27 (1)) — a plain literal, not
#: read from the design at all (A-SL30 (1), on the round-5 re-review's MINOR-4: the CROSS-RUNTIME
#: coupling this pin used to buy with a Node subprocess is not this module's to hold — the design
#: side of "these four strings really are the design's own" is `logic.test.ts`'s (it already
#: evaluates `new Component({}).state.w` directly), and this module's own job is only the OTHER
#: half: that a payload built from them is a 200 through `columns_for`. By NAME, as the design
#: names them, so the two by-name assertions below stand unchanged.
DESIGN_INITIAL_W: dict[str, Any] = {
    "name": "", "type": "Small animal", "est": "", "ownership": "Sole proprietor",
    "bldg": "Included", "facilityType": "Standalone", "facility": "",
}


def test_the_adapter_and_the_api_agree_on_every_step_s_fields() -> None:
    from app.api.seller_listings import STEP_FIELDS, columns_for

    adapter = adapter_step_fields()
    assert sorted(adapter) == sorted(STEP_FIELDS), (
        "the two tables name different steps; a step the adapter has and this module does not is a"
        " 400 on every Continue, and the other way round is a field that can never be saved"
    )
    for step, keys in sorted(adapter.items()):
        assert sorted(keys) == sorted(STEP_FIELDS[step]), f"step {step}"
        # Not a name comparison alone: the payload the adapter would send is put through the very
        # mapping `serialise_draft`/`toWizardState` invert — `desc` → `services`, `facilityType` →
        # `facility_type`, `anon` → the two disclosure columns, `bldg` → its own value map — so a
        # key that no longer maps to a column fails here rather than at a seller's Continue.
        columns = columns_for(step, {key: DESIGN_W[key] for key in keys})
        assert columns, f"step {step} mapped to no columns at all"
    # `photos` is the design's own fake photograph counter and `state` is the reviewer's, supplied
    # at the first publish (spec Q2). Both live in `w`; neither belongs to any step, and `photos`
    # sent on step 1 is one of the seventeen strays CRITICAL-B was made of.
    every = [key for keys in adapter.values() for key in keys]
    assert "photos" not in every
    assert "state" not in every


def test_the_adapter_omits_in_partial_mode_exactly_the_numerics_this_module_requires() -> None:
    """A-SL27 (2), on MAJOR-D: a draft is incomplete by nature, so Save-and-exit and the step rail
    save in a PARTIAL mode that leaves out a blank required number instead of sending `""` for it.
    The list of those numbers is this module's — every money or integer field that is not in
    `OPTIONAL_NUMERIC` — and the data file's `requiredNumeric` must be exactly that list, so
    neither side hand-types it. The probes prove the list is the right one: `columns_for` refuses
    `""` for each required number and clears the column for each optional one."""
    from app.api.seller_listings import INT_FIELDS, MONEY_FIELDS, OPTIONAL_NUMERIC, STEP_FIELDS, Refusal, columns_for

    required = sorted(set(MONEY_FIELDS + INT_FIELDS) - set(OPTIONAL_NUMERIC))
    assert sorted(adapter_tables()["requiredNumeric"]) == required, (
        "step-fields.json's requiredNumeric is not this module's own (MONEY_FIELDS + INT_FIELDS)"
        " - OPTIONAL_NUMERIC; a field missing from it is a 400 on every Save-and-exit that leaves"
        " it blank, and a field wrongly in it is a blank the seller can never clear"
    )
    step_of = {key: step for step, keys in STEP_FIELDS.items() for key in keys}
    for key in required:
        with pytest.raises(Refusal, match=f"{key} must be a number"):
            columns_for(step_of[key], {key: ""})
    for key in OPTIONAL_NUMERIC:
        assert columns_for(step_of[key], {key: ""}) == {key: None}, key


@pytest.mark.parametrize("step", [1, 2, 3, 4, 5, 7])
async def test_every_step_accepts_exactly_what_the_adapter_sends_it(
    client: Any, conn: Any, redis: Any, member: Any, step: int
) -> None:
    """The other direction, spending a real request: the payload `patch(id, step, w)` builds is a
    200 with the draft, on every step the wizard has."""
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    listing_id = await _create(client, cookies, headers)

    keys = adapter_step_fields()[step]
    saved = await client.patch(f"/api/seller/listings/{listing_id}?step={step}",
                               json={key: DESIGN_W[key] for key in keys}, headers=signed)
    assert saved.status_code == 200, saved.text
    assert saved.json()["id"] == listing_id


# --- A-SL27 (1): a listing the seller has just created, exactly as the API answers it ------------
# CRITICAL-C, round-3 re-review: `create` inserts four columns and no more, so a fresh row holds
# NULL in `type`, `ownership`, `bldg` and `facility_type`; `toWizardState` turned each null into
# `""`, `openDraft` laid that over the design's own defaults, and the first Continue of the first
# listing was `400 type must be one of Small animal, …`. Every fixture in the tree hid it by
# answering the created listing with the DESIGN's defaults instead of the nulls this endpoint really
# sends. The adapter now leaves a null column alone, so the design's literal supplies the default —
# and these pins make the fixtures tell the truth: this is the null set `frontend/tests/
# design-wizard-draft.mjs` must carry (its own pin is in `frontend/tests/harness.test.ts`), and the
# design's defaults are a 200 on the two enum steps.

#: Every key `serialise_draft` answers `null` for on a listing `create` has just made. The four
#: enums are among them, which is the whole of CRITICAL-C.
BARE_DRAFT_NULLS = frozenset({
    "name", "type", "est", "ownership", "city", "zip", "price", "rev", "docs", "rooms", "sqft",
    "hours", "desc", "bldg", "facilityType", "facility", "state", "market", "area",
    "decline_reason", "submitted_at",
})


async def test_a_bare_create_answers_null_for_exactly_these_columns(client: Any, conn: Any, member: Any) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    draft = (await client.get(f"/api/seller/listings/{listing_id}", headers=auth_headers(cookies, headers))).json()

    assert {key for key, value in draft.items() if value is None} == BARE_DRAFT_NULLS
    assert {"type", "ownership", "bldg", "facilityType"} <= BARE_DRAFT_NULLS
    # The rest of the payload is not null: the id, the slug `create` writes, the status, the three
    # switches at the table's own defaults (hide by default, D11) and the three empty lists.
    assert draft["status"] == "draft"
    assert draft["slug"] == f"listing-{listing_id}"
    assert (draft["anon"], draft["revBand"], draft["docsLocked"]) == (True, True, True)
    assert (draft["assets"], draft["photos"], draft["documents"]) == ([], [], [])


@pytest.mark.parametrize("step", [1, 5])
async def test_the_design_s_own_defaults_are_a_200_on_both_enum_steps(
    client: Any, conn: Any, redis: Any, member: Any, step: int
) -> None:
    """The first Continue of a created listing, as the adapter now builds it: the design's own
    `state.w` projected to the step, with the two fields the design's step-1 guard makes the seller
    type before it will advance. `type`/`ownership` and `bldg`/`facilityType` go as the design's
    literal holds them — never as `""` — and the row comes back holding them."""
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    listing_id = await _create(client, cookies, headers)

    design = DESIGN_INITIAL_W
    payload = {key: design[key] for key in adapter_step_fields()[step]}
    if step == 1:
        payload.update(name="ABC Animal Hospital", est="1998")
    saved = await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json=payload, headers=signed)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    if step == 1:
        assert (body["type"], body["ownership"], body["est"]) == (design["type"], design["ownership"], 1998)
        assert (design["type"], design["ownership"]) == ("Small animal", "Sole proprietor")
    else:
        assert (body["bldg"], body["facilityType"], body["facility"]) == (design["bldg"], design["facilityType"], None)
        assert (design["bldg"], design["facilityType"]) == ("Included", "Standalone")


async def test_a_partial_step_one_save_without_the_year_is_a_200(client: Any, conn: Any, redis: Any, member: Any) -> None:
    """A-SL27 (2), on MAJOR-D: the payload Save-and-exit builds on a step 1 whose year is still
    blank — the step's fields minus the blank required number — is accepted, and the year stays
    unset rather than refused. Until this the seller who pressed the button labelled *Save* on a
    half-filled step was held in the wizard by `est must be a number`."""
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    listing_id = await _create(client, cookies, headers)

    keys = [key for key in adapter_step_fields()[1] if key not in adapter_tables()["requiredNumeric"]]
    assert keys == ["name", "type", "ownership"]
    saved = await client.patch(f"/api/seller/listings/{listing_id}?step=1",
                               json={key: DESIGN_W[key] for key in keys}, headers=signed)
    assert saved.status_code == 200, saved.text
    assert (saved.json()["name"], saved.json()["est"]) == ("ABC Animal Hospital", None)


# --- A-SL31 / A-SL32 (2): an enum the seller did NOT change is not re-validated --------------------
#
# `OWNERSHIPS` is the design's four-option select vocabulary while fifteen of the eighteen seeded
# hospitals carry the design's own richer prose ("Three-doctor LLC", the same register as the
# design's own fixture value "Four-doctor LLC" in `logic.js`) directly in the `ownership` column,
# which has no database CHECK — so a seller who opened Edit on one of those and pressed Continue on
# step 1 was refused for a value they never typed. The ruling: a value the seller did not change is
# not re-validated. `columns_for` now takes the row it is validating and skips `_one_of` when the
# incoming value equals the row's OWN stored value; the seed data is not rewritten and the design's
# select is not widened (D-SL31 is John's, still open).
#
# `type` and `bldg` both carry a database CHECK (migrations 030, 016) restricting them to the exact
# vocabulary already, so neither can ever hold a real out-of-vocabulary value the way `ownership`
# does — there is no seeded row to reproduce the defect with. The rule still covers all four alike
# (A-SL31 (1): "derived from the row, never a per-field allowlist"), so the four cases below call
# `columns_for` directly, the same unit-level pattern `test_the_adapter_omits_in_partial_mode_...`
# above already uses, with a hand-built row standing in for one the CHECK could never let exist.


async def test_a_seeded_listings_out_of_vocabulary_ownership_round_trips_unchanged(
    client: Any, conn: Any, member: Any
) -> None:
    """A-SL31 (1)'s own complaint, end to end: `ownership` has no CHECK, so this is the one enum
    whose real seed prose can be reproduced at the row level, exactly as `scripts/seed_listings.py`
    writes it."""
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET ownership = 'Three-doctor LLC' WHERE id = %s", (listing_id,))

    unchanged = await client.patch(f"/api/seller/listings/{listing_id}?step=1",
                                   json={"ownership": "Three-doctor LLC"}, headers=signed)
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["ownership"] == "Three-doctor LLC"
    with conn.cursor() as cur:
        cur.execute("SELECT ownership FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == ("Three-doctor LLC",)

    # A DIFFERENT out-of-vocabulary value is still refused, with the field's existing envelope code.
    refused = await client.patch(f"/api/seller/listings/{listing_id}?step=1",
                                 json={"ownership": "Co-operative"}, headers=signed)
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "BAD_REQUEST"
    # The error message should now list all ten options
    assert "Co-operative" not in refused.json()["error"]["message"]
    with conn.cursor() as cur:
        cur.execute("SELECT ownership FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == ("Three-doctor LLC",), "the refused write must not have touched the row"

    # ...and a different IN-vocabulary value succeeds, exactly as before this ruling.
    changed = await client.patch(f"/api/seller/listings/{listing_id}?step=1",
                                 json={"ownership": "Sole proprietor"}, headers=signed)
    assert changed.status_code == 200
    assert changed.json()["ownership"] == "Sole proprietor"


async def test_an_out_of_vocabulary_facility_type_round_trips_unchanged_too(
    client: Any, conn: Any, member: Any
) -> None:
    """A-SL33 (4), fix round 1 on the SL8 review's Minor finding: `facility_type` (030) carries no
    CHECK either, exactly like `ownership` — structurally exposed to the same real out-of-vocabulary
    risk, not merely by the same direct-call unit test `ownership` already has. None of the eighteen
    seeded hospitals populate it today (it is absent from `seeds/hospitals.json`'s schema), so this
    is a hand-built row rather than a real seed's own prose — the absence is incidental, not
    structural, and this proves the SAME three-way distinction ownership's own end-to-end test
    proves, at the row level, not only through a synthetic `columns_for` call."""
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    listing_id = await _create(client, cookies, headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET facility_type = 'Converted residence' WHERE id = %s", (listing_id,))

    unchanged = await client.patch(f"/api/seller/listings/{listing_id}?step=5",
                                   json={"facilityType": "Converted residence"}, headers=signed)
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["facilityType"] == "Converted residence"
    with conn.cursor() as cur:
        cur.execute("SELECT facility_type FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == ("Converted residence",)

    # A DIFFERENT out-of-vocabulary value is still refused, with the field's existing envelope code.
    refused = await client.patch(f"/api/seller/listings/{listing_id}?step=5",
                                 json={"facilityType": "Owner-occupied duplex"}, headers=signed)
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "BAD_REQUEST"
    assert refused.json()["error"]["message"] == "facilityType must be one of Standalone, Strip or plaza, Medical park, Other."
    with conn.cursor() as cur:
        cur.execute("SELECT facility_type FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone() == ("Converted residence",), "the refused write must not have touched the row"

    # ...and a different IN-vocabulary value succeeds, exactly as before this ruling.
    changed = await client.patch(f"/api/seller/listings/{listing_id}?step=5",
                                 json={"facilityType": "Standalone"}, headers=signed)
    assert changed.status_code == 200
    assert changed.json()["facilityType"] == "Standalone"


@pytest.mark.parametrize(("field", "column", "step", "allowed"), [
    ("ownership", "ownership", 1, ("Sole proprietor", "Two-doctor partnership", "Multi-doctor LLC", "Other")),
    ("type", "type", 1, ("Small animal", "Mixed", "Large animal", "Emergency", "Specialty", "Other")),
    ("facilityType", "facility_type", 5, ("Standalone", "Strip or plaza", "Medical park", "Other")),
])
def test_columns_for_skips_the_vocabulary_check_for_an_unchanged_value(
    field: str, column: str, step: int, allowed: tuple[str, ...]
) -> None:
    """The three cases A-SL31/A-SL32 (2) name, for `ownership` and `type` alike (plus
    `facilityType`, the other enum column with no CHECK) — as a direct call, `type`'s own CHECK
    meaning no row could ever really hold the out-of-vocabulary value this proves the FUNCTION
    treats the same way `ownership`'s does."""
    from app.api.seller_listings import Refusal, columns_for

    stored = "Some out-of-vocabulary prose nobody picked from a menu"
    row = {column: stored}

    # Unchanged: the out-of-vocabulary value round-trips without `_one_of` ever seeing it.
    assert columns_for(step, {field: stored}, row) == {column: stored}

    # A DIFFERENT out-of-vocabulary value is still refused, with the field's existing code.
    with pytest.raises(Refusal, match=f"{field} must be one of"):
        columns_for(step, {field: "Also not one of the options"}, row)

    # ...and a different IN-vocabulary value succeeds.
    assert columns_for(step, {field: allowed[0]}, row) == {column: allowed[0]}

    # A column with no stored value yet (a bare create) is never treated as "unchanged" by a null
    # comparison: the very value that round-tripped above is refused when there is nothing stored
    # for it to match.
    with pytest.raises(Refusal, match=f"{field} must be one of"):
        columns_for(step, {field: stored}, {column: None})


def test_columns_for_skips_the_vocabulary_check_for_an_unchanged_bldg_through_its_own_value_map() -> None:
    """`bldg`'s twin: the column CHECK (`migrations/016_listing.sql`) keeps it in
    `{'Included', 'Leased', 'Separate'}`, but the WIZARD's own word for one of those three
    ("Available separately") is not spelled the same as the column's ("Separate") — so "unchanged"
    has to be asked in the wizard's vocabulary, through `BLDG_OUT`, not by comparing the two
    strings directly."""
    from app.api.seller_listings import Refusal, columns_for

    row = {"bldg": "Separate"}
    # Unchanged, translated: the wizard sent its own word for the very value already stored.
    assert columns_for(5, {"bldg": "Available separately"}, row) == {"bldg": "Separate"}
    # A different, in-vocabulary word still succeeds.
    assert columns_for(5, {"bldg": "Included"}, row) == {"bldg": "Included"}
    # A word that is not one of the three at all is still refused.
    with pytest.raises(Refusal, match="bldg must be one of"):
        columns_for(5, {"bldg": "Owned outright"}, row)


# --- SL9 hardening (A-SL34 (2); SL5 re-review (a)): `patch_step` takes the lock its own -----------
# precondition read needs, exactly as `locked_row` does.


async def _wait_for_a_backend_queued_on_a_lock(conn: Any, timeout: float = 10.0) -> None:
    """Block until some backend on this database is waiting on a lock, so the race below is a race
    and not a sleep — `tests/census/test_admin_api.py`'s own helper, the established shape for
    proving a `SELECT` actually took a row lock rather than merely reading past it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await asyncio.sleep(0.02)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'")
            if cur.fetchone()[0]:
                return
    raise AssertionError("no backend ever queued on the listing row lock")


async def test_a_concurrent_patch_cannot_slip_between_the_precondition_read_and_the_write(
    conn: Any, dist: Any, member: Any
) -> None:
    """SL5 re-review (a): `patch_step` read its precondition row through `owned_row` — the one
    write route in this module with no `FOR UPDATE` — while every asset write and every transition
    (`upload_photo`, `reorder_photos`, `submit_listing`, `set_status`, ...) reads through
    `locked_row` first. Raced the way `tests/census/test_admin_api.py::
    test_two_racing_decisions_cannot_both_record_the_same_before` proves the Census admin API's own
    read is serialised: a holder takes `FOR UPDATE` on the row first. The PATCH request can only
    queue behind it (visible in `pg_stat_activity` as a backend waiting on a lock) if `patch_step`'s
    own precondition read takes a lock of the same kind — a plain `SELECT` never appears there. The
    holder then WITHDRAWS the listing, a TERMINAL state (`patch_step`'s own guard, one line below
    the read this fixes), and commits.

    A precondition read that is not serialised has already read `status='draft'` — before the
    holder's write — and goes on, once the holder's commit releases the row, to write
    `status='in_review'` (or whatever the step's own fields ask for) over a listing that is, by
    then, withdrawn: `WHERE id = %(id)s AND seller_id = %(seller)s` names no status, so nothing
    stops it. A read that IS serialised sees the holder's committed `withdrawn` the moment it can
    read at all, and refuses with the same `409 STATE` every other route in this module answers for
    a withdrawn listing — leaving the row exactly as the holder left it.

    `patch_step` is `async def` and, unlike the Census admin routes (plain `def`, dispatched to
    Starlette's own threadpool), runs its blocking psycopg2 calls directly on its caller's event
    loop — so driving the request through the SAME loop as the holder (`asyncio.create_task` against
    the shared in-process `client` fixture) never yields the loop back to the polling helper above
    and the test deadlocks against itself, fixed or not. A REAL OS thread, with its own event loop
    and its own `httpx.AsyncClient` against a fresh `create_app`, is what makes this an actual race
    between two backends rather than one coroutine blocking another on the same thread."""
    from httpx import ASGITransport

    from app.db import sync_dsn
    from app.main import create_app
    from tests.api.conftest import ORIGIN

    account_id, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status, seller_id) VALUES (%s, 'seller', 'draft', %s)"
                    " RETURNING id", (f"listing-{uuid4().hex[:8]}", account_id))
        listing_id = str(cur.fetchone()[0])

    def _send_patch_from_its_own_thread() -> Any:
        async def _once() -> Any:
            async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url=ORIGIN) as c:
                return await c.patch(f"/api/seller/listings/{listing_id}?step=1",
                                     json={"name": "Raced", "type": "Small animal", "est": "1998"},
                                     headers=signed)
        return asyncio.run(_once())

    holder = psycopg2.connect(sync_dsn())
    try:
        with holder.cursor() as cur:
            cur.execute("SELECT status FROM listing WHERE id = %s FOR UPDATE", (listing_id,))
            assert cur.fetchone()[0] == "draft"
        future = asyncio.get_running_loop().run_in_executor(None, _send_patch_from_its_own_thread)
        await _wait_for_a_backend_queued_on_a_lock(conn)
        with holder.cursor() as cur:
            cur.execute("UPDATE listing SET status = 'withdrawn' WHERE id = %s", (listing_id,))
        holder.commit()
    finally:
        holder.close()

    response = await future
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "STATE"
    with conn.cursor() as cur:
        cur.execute("SELECT status, name FROM listing WHERE id = %s", (listing_id,))
        assert cur.fetchone() == ("withdrawn", None), "a race must not resurrect a withdrawn listing"


# --- Task B9: republish enqueues geocoding when there is no practice_location row -----------
async def test_republish_enqueues_geocode_task_when_listing_has_no_practice_location(
    client: Any, conn: Any, member: Any, monkeypatch: Any
) -> None:
    """Task B9: when a listing is republished and has no practice_location row, the geocode
    task is enqueued."""
    listing_id, signed = await _ready(client, member)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', state='TX', market='Austin, TX',"
                    " area='Cedar Park' WHERE id=%s", (listing_id,))

    enqueued = []
    def fake_send_task(name, args=None, **kw):
        enqueued.append((name, args))

    from app.tasks.celery_app import celery_app
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    # Pause the listing first
    response = await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "pause"},
                                headers=signed)
    assert response.status_code == 200

    # Republish should enqueue geocode
    response = await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "republish"},
                                headers=signed)
    assert response.status_code == 200

    # Check that geocode_listing was enqueued
    assert ("census.geocode_listing", [listing_id]) in enqueued


async def test_republish_does_not_enqueue_geocode_when_practice_location_exists(
    client: Any, conn: Any, member: Any, monkeypatch: Any
) -> None:
    """Task B9: when a listing is republished and already has a practice_location row,
    the geocode task is NOT enqueued."""
    listing_id, signed = await _ready(client, member)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', state='TX', market='Austin, TX',"
                    " area='Cedar Park' WHERE id=%s", (listing_id,))
        # Add a practice_location row
        cur.execute("INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoder_vintage, geocoded_at) "
                        "VALUES (%s, %s, %s, %s, now()),",
                    (listing_id, "hash1", "rooftop", "Current_Current"))

    enqueued = []
    def fake_send_task(name, args=None, **kw):
        enqueued.append((name, args))

    from app.tasks.celery_app import celery_app
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    # Pause the listing first
    response = await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "pause"},
                                headers=signed)
    assert response.status_code == 200

    # Republish should NOT enqueue geocode
    response = await client.post(f"/api/seller/listings/{listing_id}/status", json={"action": "republish"},
                                headers=signed)
    assert response.status_code == 200

    # Check that geocode_listing was NOT enqueued
    assert ("census.geocode_listing", [listing_id]) not in enqueued


# --- Task SL10: the ownership vocabulary widens to the seeds' own wording ----------------------
# Step 1: RED — the two sides agree
def test_the_design_ownership_options_equal_ownerships_tuple() -> None:
    """Task SL10 Step 1: a pytest case that reads frontend/src/logic.js, extracts the
    sel("ownership", "Current ownership", [...]) option array with a regex, and asserts it
    equals list(OWNERSHIPS). Run: FAIL (four vs ten)."""
    import re

    from app.api.seller_listings import OWNERSHIPS

    logic_path = ROOT / "frontend" / "src" / "logic.js"
    logic_content = logic_path.read_text()
    
    # Extract the ownership select options array
    match = re.search(r'sel\("ownership",\s*"Current ownership",\s*\[(.*?)\]\)', logic_content, re.DOTALL)
    assert match, "Could not find ownership select in logic.js"
    
    # Extract the quoted strings from the array
    array_str = f"[{match.group(1)}]"
    options = re.findall(r'"([^"]*)"', array_str)
    
    assert options == list(OWNERSHIPS), f"Design options {options} != OWNERSHIPS {list(OWNERSHIPS)}"


# Step 2: RED — the seeds fit
def test_all_seeded_hospitals_have_ownership_in_ownerships() -> None:
    """Task SL10 Step 2: a case that loads seeds/hospitals.json and asserts every hospital's
    ownership is in OWNERSHIPS. Run: FAIL (fifteen of eighteen outside)."""
    import json

    from app.api.seller_listings import OWNERSHIPS

    hospitals_path = ROOT / "seeds" / "hospitals.json"
    data = json.loads(hospitals_path.read_text())
    hospitals = data.get("hospitals", [])

    for i, hospital in enumerate(hospitals):
        ownership = hospital.get("ownership")
        assert ownership in OWNERSHIPS, f"Hospital {i} ({hospital.get('name')}) has ownership " \
            f"'{ownership}' not in OWNERSHIPS: {OWNERSHIPS}"
