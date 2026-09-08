"""GET /api/listings, /api/listings/{id} and /api/listings/{id}/photos/{n} (spec D8/D9, A-L5)."""
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.api.listings import (
    LIST_TTL_S,
    REQUIRE_LISTING_READ,
    anonymised_name,
    decode_cursor,
    encode_cursor,
    photo_file,
    photo_list,
    relative_listed,
    serialise,
)
from tests.api.conftest import auth_headers

INSERT = (
    "INSERT INTO listing (slug, name, street, city, state, zip, phone, hours, status,"
    " location_disclosed, name_disclosed, geom, area, type, market, price, rev, docs, rooms, sqft,"
    " bldg, est, listed_at, note, staff, services, facility, ownership, photos, source)"
    " VALUES (%(slug)s,%(name)s,%(street)s,%(city)s,%(state)s,%(zip)s,%(phone)s,%(hours)s,"
    " %(status)s,%(disclosed)s,%(name_disclosed)s,"
    " ST_SetSRID(ST_MakePoint(%(lng)s,%(lat)s),4326)::geography,"
    " %(area)s,'Small animal',%(market)s,1000000,1500000,2,4,3000,'Included',2001,"
    " now() - make_interval(days => %(days)s),'n','s','sv','f','o',%(photos)s::jsonb,'seed')"
    " RETURNING id"
)


def _insert(conn: Any, **over: Any) -> str:
    params: dict[str, Any] = {
        "slug": f"s-{uuid4().hex[:8]}", "name": "Demo Hospital", "street": "1 Main St",
        "city": "Austin", "state": "TX", "zip": "78701", "phone": "(512) 555-0100",
        "hours": "24/7", "status": "published", "disclosed": True, "name_disclosed": True,
        "lat": 30.2672, "lng": -97.7431, "area": "Austin", "market": "Austin, TX", "days": 3,
        "photos": json.dumps([]),
    }
    params.update(over)
    with conn.cursor() as cur:
        cur.execute(INSERT, params)
        return str(cur.fetchone()[0])


def _squashed(value: object) -> str:
    """`value` with everything but its letters and digits removed, lower-cased.

    The grep A-L5 asks for has to survive the shapes a stored name can be smuggled in: a slug
    (`northside_animal_hospital`), a title (`Northside Animal Hospital`), a photograph path.
    Comparing the squashed forms catches every one of them; comparing the literal strings would
    catch only the last."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


async def test_anonymous_gets_the_generic_401_body(client: Any, conn: Any, redis: Any) -> None:
    r = await client.get("/api/listings")
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}


async def test_a_member_sees_the_published_listings(client: Any, conn: Any, redis: Any, member: Any) -> None:
    listing_id = _insert(conn)
    _, cookies, headers = member()
    r = await client.get("/api/listings", headers=auth_headers(cookies, headers))
    assert r.status_code == 200
    body = r.json()
    assert [item["id"] for item in body["items"]] == [listing_id]
    assert body["next_cursor"] is None


async def test_unpublished_listings_are_hidden_from_both_endpoints(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    draft = _insert(conn, status="draft")
    _, cookies, headers = member()
    listed = await client.get("/api/listings", headers=auth_headers(cookies, headers))
    assert [item["id"] for item in listed.json()["items"]] == []
    one = await client.get(f"/api/listings/{draft}", headers=auth_headers(cookies, headers))
    assert one.status_code == 404
    assert one.json() == {"error": {"code": "NOT_FOUND", "message": "No such listing."}}


async def test_the_market_filter_narrows_the_list(client: Any, conn: Any, redis: Any, member: Any) -> None:
    austin = _insert(conn, market="Austin, TX")
    _insert(conn, market="Dallas, TX")
    _, cookies, headers = member()
    r = await client.get("/api/listings?market=Austin%2C+TX", headers=auth_headers(cookies, headers))
    assert [item["id"] for item in r.json()["items"]] == [austin]


async def test_pagination_walks_every_row_exactly_once(client: Any, conn: Any, redis: Any, member: Any) -> None:
    ids = {_insert(conn, days=n) for n in range(5)}
    _, cookies, headers = member()
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):
        url = "/api/listings?limit=2" + (f"&cursor={cursor}" if cursor else "")
        body = (await client.get(url, headers=auth_headers(cookies, headers))).json()
        seen += [item["id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == sorted(ids) and len(seen) == len(set(seen))
    assert cursor is None


async def test_a_malformed_cursor_is_a_400_in_the_a5_shape(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    _, cookies, headers = member()
    r = await client.get("/api/listings?cursor=not-a-cursor", headers=auth_headers(cookies, headers))
    assert r.status_code == 400
    assert r.json() == {"error": {"code": "BAD_REQUEST", "message": "Invalid cursor."}}


@pytest.mark.parametrize("bad", ["limit=0", "limit=201", "limit=abc"])
async def test_a_bad_limit_is_a_400_in_the_a5_shape(
    client: Any, conn: Any, redis: Any, member: Any, bad: str
) -> None:
    _, cookies, headers = member()
    r = await client.get(f"/api/listings?{bad}", headers=auth_headers(cookies, headers))
    assert r.status_code == 400
    assert r.json() == {"error": {"code": "BAD_REQUEST", "message": "Invalid limit."}}


async def test_an_undisclosed_listing_returns_no_address_and_no_point(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    listing_id = _insert(conn, disclosed=False)
    _, cookies, headers = member()
    item = (await client.get(f"/api/listings/{listing_id}", headers=auth_headers(cookies, headers))).json()
    assert item["street"] is None and item["zip"] is None
    assert item["lat"] is None and item["lng"] is None
    assert item["city"] == "Austin" and item["state"] == "TX" and item["area"] == "Austin"
    assert item["location_disclosed"] is False


async def test_an_undisclosed_location_hides_the_phone_number(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """A-L5.1: a phone number identifies the practice as surely as its street, so it follows
    `location_disclosed`. `hours` is not identifying and stays."""
    stored = "(512) 555-0187"
    listing_id = _insert(conn, disclosed=False, phone=stored)
    _, cookies, headers = member()
    auth = auth_headers(cookies, headers)
    item = (await client.get(f"/api/listings/{listing_id}", headers=auth)).json()
    assert item["phone"] is None
    assert item["hours"] == "24/7", "hours is not identifying and stays"
    for path in ("/api/listings", f"/api/listings/{listing_id}"):
        text = (await client.get(path, headers=auth)).text
        assert _squashed(stored) not in _squashed(text), path


async def test_a_disclosed_location_returns_the_phone_number(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """The other half of A-L5.1 — every seeded hospital is this row."""
    stored = "(512) 555-0187"
    listing_id = _insert(conn, disclosed=True, phone=stored)
    _, cookies, headers = member()
    auth = auth_headers(cookies, headers)
    assert (await client.get(f"/api/listings/{listing_id}", headers=auth)).json()["phone"] == stored
    assert (await client.get("/api/listings", headers=auth)).json()["items"][0]["phone"] == stored


async def test_a_disclosed_name_is_returned_verbatim_on_both_endpoints(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """A-L5: `name_disclosed` true is John's eighteen demo hospitals — the stored name, as stored."""
    listing_id = _insert(conn, name="Northside Animal Hospital", slug="northside_animal_hospital")
    _, cookies, headers = member()
    auth = auth_headers(cookies, headers)
    one = (await client.get(f"/api/listings/{listing_id}", headers=auth)).json()
    assert one["name"] == "Northside Animal Hospital"
    assert one["name_disclosed"] is True
    assert one["slug"] == "northside_animal_hospital"
    listed = (await client.get("/api/listings", headers=auth)).json()["items"][0]
    assert listed["name"] == "Northside Animal Hospital" and listed["name_disclosed"] is True


async def test_a_hidden_name_becomes_the_designs_anonymised_label(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """A-L5: `name_disclosed` false returns `<area> Veterinary` — `practiceName`'s own fallback in
    frontend/src/logic.js — and the slug, which is the name in slug form, goes with it."""
    listing_id = _insert(
        conn, name="Northside Animal Hospital", slug="northside_animal_hospital",
        name_disclosed=False, area="Cedar Park",
    )
    _, cookies, headers = member()
    auth = auth_headers(cookies, headers)
    one = (await client.get(f"/api/listings/{listing_id}", headers=auth)).json()
    assert one["name"] == "Cedar Park Veterinary"
    assert one["name_disclosed"] is False
    assert one["slug"] is None
    listed = (await client.get("/api/listings", headers=auth)).json()["items"][0]
    assert listed["name"] == "Cedar Park Veterinary" and listed["name_disclosed"] is False
    assert listed["slug"] is None


async def test_a_hidden_name_appears_nowhere_in_any_response_body(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """A-L5's grep, both endpoints, over the RAW response text rather than a chosen field: a hidden
    value must never reach a buyer's browser, in any spelling."""
    hidden = "Northside Animal Hospital"
    listing_id = _insert(
        conn, name=hidden, slug="northside_animal_hospital", name_disclosed=False,
        area="Cedar Park", photos=json.dumps(["abc_animal_hospital/1.webp"]),
    )
    _, cookies, headers = member()
    auth = auth_headers(cookies, headers)
    for path in ("/api/listings", f"/api/listings/{listing_id}"):
        text = (await client.get(path, headers=auth)).text
        assert _squashed(hidden) not in _squashed(text), path


async def test_photos_are_served_as_webp_with_a_private_cache_header(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    listing_id = _insert(conn, photos=json.dumps(["abc_animal_hospital/1.webp"]))
    _, cookies, headers = member()
    r = await client.get(f"/api/listings/{listing_id}/photos/1", headers=auth_headers(cookies, headers))
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert r.headers["cache-control"] == "private, max-age=86400"
    assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WEBP"


async def test_a_missing_photo_index_is_a_404(client: Any, conn: Any, redis: Any, member: Any) -> None:
    listing_id = _insert(conn, photos=json.dumps(["abc_animal_hospital/1.webp"]))
    _, cookies, headers = member()
    for n in ("0", "2", "99"):
        r = await client.get(f"/api/listings/{listing_id}/photos/{n}", headers=auth_headers(cookies, headers))
        assert r.status_code == 404, n
        assert r.json() == {"error": {"code": "NOT_FOUND", "message": "No such photograph."}}


async def test_photos_are_refused_to_an_anonymous_caller(client: Any, conn: Any, redis: Any) -> None:
    listing_id = _insert(conn, photos=json.dumps(["abc_animal_hospital/1.webp"]))
    r = await client.get(f"/api/listings/{listing_id}/photos/1")
    assert r.status_code == 401


async def test_an_unknown_listing_id_is_a_404_not_a_500(client: Any, conn: Any, redis: Any, member: Any) -> None:
    _, cookies, headers = member()
    for path in (f"/api/listings/{uuid4()}", f"/api/listings/{uuid4()}/photos/1"):
        r = await client.get(path, headers=auth_headers(cookies, headers))
        assert r.status_code == 404, path


async def test_a_non_uuid_listing_id_is_a_404_not_a_500(client: Any, conn: Any, redis: Any, member: Any) -> None:
    _, cookies, headers = member()
    r = await client.get("/api/listings/not-a-uuid", headers=auth_headers(cookies, headers))
    assert r.status_code == 404


async def test_the_list_is_cached_for_sixty_seconds(client: Any, conn: Any, redis: Any, member: Any) -> None:
    _insert(conn)
    _, cookies, headers = member()
    first = await client.get("/api/listings", headers=auth_headers(cookies, headers))
    keys = list(redis.keys("listings:v1:*"))
    assert len(keys) == 1
    assert 0 < redis.ttl(keys[0]) <= LIST_TTL_S
    _insert(conn)  # a row the cached answer cannot know about
    second = await client.get("/api/listings", headers=auth_headers(cookies, headers))
    assert second.json() == first.json(), "the second read must come from the cache"


async def test_the_cache_key_separates_market_cursor_and_limit(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """One key per (market, cursor, limit): a `?market=` answer must never be served to a caller
    who asked for the whole list, nor a page-2 answer to a caller asking for page 1."""
    _insert(conn, market="Austin, TX", days=1)
    _insert(conn, market="Dallas, TX", days=2)
    _, cookies, headers = member()
    auth = auth_headers(cookies, headers)
    everything = (await client.get("/api/listings?limit=1", headers=auth)).json()
    dallas = (await client.get("/api/listings?limit=1&market=Dallas%2C+TX", headers=auth)).json()
    page_two = (await client.get(
        f"/api/listings?limit=1&cursor={everything['next_cursor']}", headers=auth)).json()
    assert len(set(redis.keys("listings:v1:*"))) == 3
    assert everything["items"][0]["market"] == "Austin, TX"
    assert dallas["items"][0]["market"] == "Dallas, TX"
    assert page_two["items"][0]["market"] == "Dallas, TX"


async def test_a_photo_path_can_never_escape_the_photo_root(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    listing_id = _insert(conn, photos=json.dumps(["../../../../etc/passwd"]))
    _, cookies, headers = member()
    r = await client.get(f"/api/listings/{listing_id}/photos/1", headers=auth_headers(cookies, headers))
    assert r.status_code == 404


async def test_an_over_long_market_is_a_400_in_the_a5_shape(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """The `len(market) > 64` refusal — no other test sends a long market (pre-flight C2)."""
    _, cookies, headers = member()
    r = await client.get(f"/api/listings?market={'x' * 65}", headers=auth_headers(cookies, headers))
    assert r.status_code == 400
    assert r.json() == {"error": {"code": "BAD_REQUEST", "message": "Invalid market."}}


def _row(**over: Any) -> dict[str, Any]:
    """A `listing` row as `_rows()` builds one, for the direct `serialise` unit tests below."""
    base: dict[str, Any] = {
        "id": uuid4(), "slug": "s", "name": "N", "street": "1 Main St", "city": "Austin",
        "state": "TX", "zip": "78701", "phone": "(512) 555-0100", "hours": "24/7",
        "status": "published", "location_disclosed": True, "name_disclosed": True,
        "lat": 30.2672, "lng": -97.7431,
        "area": "Austin", "type": "Small animal", "market": "Austin, TX", "price": 1,
        "rev": 2, "docs": 3, "rooms": 4, "sqft": 5, "bldg": "Included", "est": 2001,
        "listed_at": datetime(2026, 9, 3, tzinfo=UTC), "note": "n", "staff": "s",
        "services": "sv", "facility": "f", "ownership": "o", "photos": [],
    }
    base.update(over)
    return base


def test_photo_list_accepts_both_a_list_and_a_json_string() -> None:
    """psycopg2 hands `jsonb` back as a list, so the string arm is unreachable from a request
    and must be covered directly (pre-flight C2)."""
    assert photo_list(["a/1.webp"]) == ["a/1.webp"]
    assert photo_list('["a/1.webp", "a/2.webp"]') == ["a/1.webp", "a/2.webp"]
    assert photo_list([]) == []
    assert photo_list(None) == []


def test_serialise_handles_photos_arriving_as_a_json_string() -> None:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    body = serialise(_row(photos='["abc_animal_hospital/1.webp"]'), now)
    assert body["photos"] == [f"/api/listings/{body['id']}/photos/1"]


def test_serialise_omits_a_point_a_disclosed_listing_never_had() -> None:
    """`disclosed and lat is not None` — the combination `disclosed=True, geom NULL`. Every
    inserted row in this file has a point, so this arm is only reachable directly. A seller's
    listing in Wave 2b will be exactly this shape before it is geocoded (pre-flight C2)."""
    body = serialise(_row(lat=None, lng=None), datetime(2026, 9, 6, tzinfo=UTC))
    assert body["lat"] is None and body["lng"] is None
    assert body["location_disclosed"] is True
    assert body["street"] == "1 Main St"


def test_serialise_blanks_the_address_of_an_undisclosed_listing() -> None:
    body = serialise(_row(location_disclosed=False), datetime(2026, 9, 6, tzinfo=UTC))
    assert (body["street"], body["zip"], body["lat"], body["lng"]) == (None, None, None, None)
    assert body["phone"] is None, "A-L5.1: the phone number follows the location"
    assert (body["city"], body["state"], body["area"]) == ("Austin", "TX", "Austin")
    assert body["hours"] == "24/7"


def test_serialise_hides_a_name_the_seller_has_not_disclosed() -> None:
    """A-L5, the unit half: name and slug both go, the area-derived label takes their place."""
    body = serialise(_row(name="Northside Animal Hospital", slug="northside_animal_hospital",
                          name_disclosed=False), datetime(2026, 9, 6, tzinfo=UTC))
    assert body["name"] == "Austin Veterinary"
    assert body["slug"] is None
    assert body["name_disclosed"] is False
    assert _squashed("Northside Animal Hospital") not in _squashed(json.dumps(body))


def test_anonymised_name_is_the_frontends_own_practice_name_fallback() -> None:
    """`practiceName(p)` in frontend/src/logic.js ends `|| p.area + " Veterinary"` (A-L5/A12)."""
    assert anonymised_name("Cedar Park") == "Cedar Park Veterinary"


def test_photo_file_refuses_an_escaping_path() -> None:
    assert photo_file(["../../etc/passwd"], 1) is None
    assert photo_file([], 1) is None
    assert photo_file(["abc_animal_hospital/1.webp"], 0) is None
    assert photo_file(["abc_animal_hospital/1.webp"], 2) is None
    assert photo_file(["abc_animal_hospital/nope.webp"], 1) is None
    assert photo_file(["abc_animal_hospital/1.webp"], 1) is not None


@pytest.mark.parametrize(
    "days, expected",
    [(0, "today"), (1, "1 day ago"), (2, "2 days ago"), (6, "6 days ago"), (7, "1 week ago"),
     (13, "1 week ago"), (14, "2 weeks ago"), (20, "2 weeks ago"), (21, "3 weeks ago"),
     (27, "3 weeks ago"), (28, "1 month ago"), (59, "1 month ago"), (60, "2 months ago"),
     (120, "4 months ago")],
)
def test_relative_listed_matches_the_designs_vocabulary(days: int, expected: str) -> None:
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    assert relative_listed(now - timedelta(days=days, hours=1), now) == expected


def test_cursors_round_trip_and_reject_rubbish() -> None:
    at = datetime(2026, 9, 1, 8, 30, tzinfo=UTC)
    listing_id = uuid4()
    assert decode_cursor(encode_cursor(at, listing_id)) == (at, listing_id)
    # "a" is one data character past a multiple of four (binascii.Error) and "_w" decodes to the
    # lone byte 0xff (UnicodeDecodeError): between them they reach BOTH arms of the base64 guard,
    # which the brief's four values do not — "!!!" is silently discarded by b64decode and lands on
    # the ValueError below instead (measured, 2026-09-08).
    for rubbish in ("", "!!!", "YWJj", "MjAyNi0wOS0wMXxub3QtYS11dWlk", "a", "_w"):
        with pytest.raises(ValueError):
            decode_cursor(rubbish)


def test_the_listings_routes_are_guarded_not_public(dist: Any) -> None:
    """Global Constraint (e): three new routes, GET only, each guarded by `listing.read`, and
    nothing added to PUBLIC_ROUTES.

    Enumerated with `tests.conftest.walk_routes`, not `app.routes`: FastAPI 0.141 keeps an included
    router as a WRAPPER object rather than flattening it, so `{r.path for r in app.routes}` sees
    only `/`, `/robots.txt`, the `/_app` mount and the SPA catch-all — no `/api/*` path at all
    (the brief's own sketch of this test asserted against that set and could never pass)."""
    from fastapi import Depends

    from app.auth import deps
    from app.auth import permissions as PM
    from app.main import create_app
    from tests.conftest import walk_routes

    paths = {p for _, p in PM.PUBLIC_ROUTES}
    assert not any(p.startswith("/api/listings") for p in paths)
    mounted = {
        (method, path): route for method, path, route in walk_routes(create_app(dist=dist).routes)
        if path.startswith("/api/listings")
    }
    assert sorted(mounted) == [
        ("GET", "/api/listings"),
        ("GET", "/api/listings/{listing_id}"),
        ("GET", "/api/listings/{listing_id}/photos/{n}"),
    ]
    for (method, path), route in mounted.items():
        guards = [deps.permission_of(d.call) for d in route.dependant.dependencies
                  if isinstance(d.call, type(REQUIRE_LISTING_READ))]
        assert "listing.read" in guards, (method, path)
    # (g): one hoisted constant, shared by all three, never wrapped.
    assert deps.permission_of(REQUIRE_LISTING_READ) == "listing.read"
    assert Depends(REQUIRE_LISTING_READ).dependency is REQUIRE_LISTING_READ


async def test_a_seeded_database_serves_all_eighteen(client: Any, conn: Any, redis: Any, member: Any) -> None:
    """The end-to-end shape: the real seeder, the real endpoint, the real photograph files.

    `conn` monkeypatches `settings.database_url` to the scratch database, so the seeder writes
    to the same database this request reads."""
    from app.config import settings
    from scripts import seed_listings as SL

    SL.seed(settings.database_url, reset=True)
    _, cookies, headers = member()
    r = await client.get("/api/listings?limit=200", headers=auth_headers(cookies, headers))
    items = r.json()["items"]
    assert len(items) == 18
    assert all(item["photos"] for item in items)
    assert all(item["lat"] is not None and item["lng"] is not None for item in items)
    assert {item["market"] for item in items} >= {"Dallas, TX", "Austin, TX", "Atlanta, GA"}
    # A-L5: John's demo hospitals show their names on QA.
    assert all(item["name_disclosed"] is True for item in items)
    assert "6666 Dallas Veterinary Specialist Hospital" in {item["name"] for item in items}


async def test_a_photograph_of_a_seeded_hospital_is_really_served(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    from app.config import settings
    from scripts import seed_listings as SL

    SL.seed(settings.database_url, reset=True)
    _, cookies, headers = member()
    auth = auth_headers(cookies, headers)
    items = (await client.get("/api/listings?limit=200", headers=auth)).json()["items"]
    first = items[0]
    photo = await client.get(first["photos"][0], headers=auth)
    assert photo.status_code == 200 and photo.content[:4] == b"RIFF"


async def test_the_listings_routes_exist_only_in_app_mode(dist: Any, redis: Any, monkeypatch: Any) -> None:
    """A-L5.1: the three routes are MEMBER endpoints, so they follow the auth, applications and
    admin routers into `create_app()`'s `site_mode == "app"` block rather than being mounted
    unconditionally — `scripts/verify-deploy.sh production` asserts "member endpoints absent" and
    that claim has to be true of these too.

    In `coming_soon` nothing is registered and `not_found_router`'s catch-all answers the same JSON
    404 it gives any unknown /api path; in `app` the three are registered and guarded."""
    import httpx
    from httpx import ASGITransport

    from app.config import settings
    from app.main import create_app
    from tests.api.conftest import ORIGIN
    from tests.conftest import walk_routes

    monkeypatch.setattr(settings, "site_mode", "coming_soon")
    coming = create_app(dist=dist)
    assert [p for _, p, _ in walk_routes(coming.routes) if p.startswith("/api/listings")] == []
    async with httpx.AsyncClient(transport=ASGITransport(app=coming), base_url=ORIGIN) as c:
        for path in ("/api/listings", f"/api/listings/{uuid4()}", f"/api/listings/{uuid4()}/photos/1"):
            r = await c.get(path)
            assert r.status_code == 404, path
            assert r.json()["error"]["code"] == "NOT_FOUND"
            assert r.json()["ok"] is False, "the catch-all's body, not this module's"

    monkeypatch.setattr(settings, "site_mode", "app")
    live = create_app(dist=dist)
    assert sorted(p for _, p, _ in walk_routes(live.routes) if p.startswith("/api/listings")) == [
        "/api/listings", "/api/listings/{listing_id}", "/api/listings/{listing_id}/photos/{n}",
    ]
    async with httpx.AsyncClient(transport=ASGITransport(app=live), base_url=ORIGIN) as c:
        for path in ("/api/listings", f"/api/listings/{uuid4()}", f"/api/listings/{uuid4()}/photos/1"):
            r = await c.get(path)
            assert r.status_code == 401, path
            assert r.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}
