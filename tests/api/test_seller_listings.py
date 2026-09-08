"""The seller wizard's own surface (spec 2026-09-08 D7-D13, D16, D17).

Fixtures are `tests/api/conftest.py`'s: `client` (base URL https://qa.foundation.vin, so the Origin
check passes), `member(roles=..., state=..., email=...) -> (account_id, cookies, headers)`, and the
root `conn`/`redis`. There is no migrated `scratch_db` fixture — `conn` is the scratch database with
every migration applied and `settings.database_url` pointed at it.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.api.conftest import auth_headers, padded_json


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
        cur.execute("UPDATE listing SET status='published', state='TX', market='Austin, TX', area='Cedar Park' WHERE id=%s", (listing_id,))
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
                    " est=1998, price=1, state='TX', market='Austin, TX', area='C' WHERE id=%s", (listing_id,))
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
                    " type='Small animal', est=1998, price=1, state='TX', market='Austin, TX',"
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
    _, cookies, headers = _seller(member)
    response = await client.get("/api/seller/listings?limit=lots", headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert response.json() == {"error": {"code": "BAD_REQUEST", "message": "Invalid limit."}}


@pytest.mark.parametrize("cursor", ["no-separator", "notadate|11111111-1111-1111-1111-111111111111",
                                    "2026-01-01T00:00:00Z|not-a-uuid"])
async def test_a_cursor_that_is_not_one_is_refused_in_the_envelope(client: Any, conn: Any, member: Any, cursor: str) -> None:
    """Three shapes, three arms: no `|` at all, a left half that is not a timestamp, a right half
    that is not a uuid. All three are the same refusal — a cursor is opaque to its holder."""
    _, cookies, headers = _seller(member)
    response = await client.get(f"/api/seller/listings?cursor={cursor}", headers=auth_headers(cookies, headers))
    assert response.status_code == 400
    assert response.json() == {"error": {"code": "BAD_REQUEST", "message": "Invalid cursor."}}


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
                    " price=1, state='TX', market='Austin, TX', area='C', status=%s WHERE id=%s",
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
