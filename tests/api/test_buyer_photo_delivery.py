"""Directive 20's security matrix, and directive 21's standing rule for every NOT_SHOW test:
"ASSERT buyer receives REDACTED representation. ASSERT buyer cannot access ORIGINAL
representation." One helper asserts both, in one place, so a scenario cannot forget half of it.

Every scenario reads its expectations from the DATABASE and the BUCKET rather than from a value
the test computed, so a test cannot agree with a bug it caused.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from PIL import Image

from app.config import settings
from app.disclosure.levels import covers
from app.privacy import redacted_key
from tests.api.conftest import _draft, auth_headers

ROOT = Path(__file__).resolve().parent.parent.parent

# The three modules that may name the original object's key at all. Derived by running the grep in
# `test_the_original_key_is_read_only_where_the_spec_says` against the tree, never assumed.
ORIGINAL_KEY_MODULES = {
    # The row's own SELECT and INSERT. `delivery_row` builds a PrivacyRow here, for the same
    # reason: the list route must never name this identifier.
    "app/privacy/record.py",
    # The ONE handler body that can return original.* -- the owner route, mounted twice. The
    # admin router reuses this body rather than repeating it, so app/api/admin_listings.py is
    # NOT in this set; if an implementer writes a second body there, that is a fourth entry and
    # a deliberate edit to this literal whose review asks "why two?".
    "app/api/seller_listings.py",
    # The barcode pass reads the original once: a fill cannot hide under an OCR region, and a
    # symbol in the source that the display encode softened must still be found (spec C.5 2b).
    # Task P8 is what creates this file; the existence term below is what lets ONE literal serve
    # this branch and the merged tree without either editing the other's pin.
    "app/tasks/media.py",
}

# What a buyer, a seller and a reviewer can reach on the listing surface. A LITERAL, because what a
# route can return is not derivable by walking `create_app().routes`: the walk tells you a path
# exists, and this says which paths are allowed to.
LISTING_ROUTES = {
    ("GET", "/api/listings"), ("GET", "/api/listings/{listing_id}"),
    # `app/api/market.py`'s own route, on this prefix: the Census figures for one listing. It
    # returns no photograph and is listed here because this pin is over the PREFIX, not over one
    # module -- a new route on the listing surface has to be declared whatever file it lives in.
    ("GET", "/api/listings/{listing_id}/market"),
    # Both methods, because the buyer bytes route declares both. FastAPI's APIRoute does not add
    # HEAD beside GET the way Starlette's Route does, so this row exists only when the handler says
    # `methods=["GET", "HEAD"]` -- which spec F's "HEAD mirrors GET" requires it to.
    ("GET", "/api/listings/{listing_id}/photos/{n}"),
    ("HEAD", "/api/listings/{listing_id}/photos/{n}"),
    ("GET", "/api/seller/listings"), ("POST", "/api/seller/listings"),
    ("GET", "/api/seller/listings/{listing_id}"), ("PATCH", "/api/seller/listings/{listing_id}"),
    ("POST", "/api/seller/listings/{listing_id}/photos"),
    ("PATCH", "/api/seller/listings/{listing_id}/photos"),
    ("GET", "/api/seller/listings/{listing_id}/photos/{asset_id}"),
    # Task P12 adds these four; the rows are written here from the start and are commented out
    # until that task uncomments them, so the pin is edited twice on purpose rather than written
    # to match whatever exists.
    # ("POST", "/api/seller/listings/{listing_id}/photos/{asset_id}/confirm"),
    # ("POST", "/api/seller/listings/{listing_id}/photos/{asset_id}/masks"),
    # ("DELETE", "/api/seller/listings/{listing_id}/photos/{asset_id}/masks/{mask_id}"),
    # ("POST", "/api/seller/listings/{listing_id}/photos/{asset_id}/reprocess"),
    ("PATCH", "/api/seller/listings/{listing_id}/photos/{n}"),
    ("PATCH", "/api/seller/listings/{listing_id}/assets/{asset_id}"),
    ("DELETE", "/api/seller/listings/{listing_id}/assets/{asset_id}"),
    ("POST", "/api/seller/listings/{listing_id}/documents"),
    ("GET", "/api/seller/listings/{listing_id}/documents/{asset_id}"),
    ("POST", "/api/seller/listings/{listing_id}/submit"),
    ("POST", "/api/seller/listings/{listing_id}/status"),
    ("GET", "/api/admin/listings"), ("GET", "/api/admin/listings/{listing_id}"),
    ("GET", "/api/admin/listings/{listing_id}/photos/{asset_id}"),
    ("POST", "/api/admin/listings/{listing_id}/decide"),
}


def _jpeg(colour: tuple[int, int, int] = (120, 30, 30), size: tuple[int, int] = (240, 180)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, "JPEG")
    return buffer.getvalue()


def _webp(colour: tuple[int, int, int] = (10, 200, 90), size: tuple[int, int] = (240, 180)) -> bytes:
    """A REAL WebP, distinct from the display derivative the upload route produced -- so "the buyer
    got the redacted bytes" is a byte comparison and never a hash the test chose."""
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, "WEBP", lossless=True)
    return buffer.getvalue()


def _privacy_of(conn: Any, listing_id: str, n: int) -> Any:
    """The `PrivacyRow` behind the nth entry of a listing's photographs -- what the helper below
    compares the delivered bytes against.

    Synchronous, because `conn` is psycopg2 and always has been; only the CLIENT is async."""
    from app.privacy import record

    with conn.cursor() as cur:
        cur.execute("SELECT photos ->> %s FROM listing WHERE id = %s", (n - 1, listing_id))
        entry = cur.fetchone()[0]
    return record.read(conn, UUID(entry))


async def _upload(client: Any, listing_id: str, headers: dict[str, str], data: bytes | None = None) -> str:
    response = await client.post(
        f"/api/seller/listings/{listing_id}/photos",
        files={"file": ("front.jpg", data if data is not None else _jpeg(), "image/jpeg")},
        headers=headers)
    assert response.status_code == 201, response.text
    asset_id: str = response.json()["id"]
    return asset_id


def _process(conn: Any, store: Any, listing_id: str, asset_id: str, *, status: str,
             visible: bool = True, body: bytes | None = None) -> bytes:
    """The pipeline's OUTCOME, planted: a real redacted object in the bucket and the privacy row
    that names it. Task P8 owns the pipeline; this suite owns what delivery does with its result.

    Every CHECK migration 041 carries is satisfied for the state asked for -- `lap_confirmed_ck`'s
    `confirmed_sha256 = redacted_sha256`, `lap_status_confirmed_ck`, `lap_visible_ready_ck` and
    `lap_ready_has_derivative_ck`."""
    data = _webp() if body is None else body
    key = redacted_key(listing_id, asset_id)
    store.put(key, data, "image/webp")
    digest = hashlib.sha256(data).hexdigest()
    confirmed = status in ("SELLER_CONFIRMED", "PUBLISHED")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = %s, redacted_storage_key = %s,"
            " redacted_sha256 = %s, confirmed_sha256 = %s, seller_confirmed = %s,"
            " seller_confirmed_at = CASE WHEN %s THEN now() END,"
            " final_privacy_state = CASE WHEN %s THEN 'NOT_SHOW' END, buyer_visible = %s"
            " WHERE asset_id = %s",
            (status, key, digest, digest if confirmed else None, confirmed, confirmed, confirmed,
             visible, asset_id))
    return data


def _publish(conn: Any, listing_id: str, *, visibility: str) -> None:
    """The columns 030's two CHECKs want, the visibility this scenario is about, and the status
    change migration 042's trigger guards."""
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET name='Hill Country Animal Hospital', city='Cedar Park',"
                    " zip='78613', type='Small animal', est=1998, price=1450000, sqft=3000,"
                    " state='TX', market='Austin, TX', area='Cedar Park',"
                    " identifiable_content_visibility=%s WHERE id=%s", (visibility, listing_id))
        cur.execute("UPDATE listing SET status='published' WHERE id=%s", (listing_id,))


async def _listing_with_a_processed_photograph(
    client: Any, conn: Any, store: Any, seller: dict[str, str], *, visibility: str,
    status: str = "SELLER_CONFIRMED",
) -> tuple[str, Any]:
    listing_id = await _draft(client, seller)
    asset_id = await _upload(client, listing_id, seller)
    _process(conn, store, listing_id, asset_id, status=status)
    _publish(conn, listing_id, visibility=visibility)
    return listing_id, _privacy_of(conn, listing_id, 1)


@pytest.fixture
async def published_not_show_listing(client: Any, conn: Any, redis: Any, store: Any,
                                     seller: dict[str, str]) -> tuple[str, Any]:
    return await _listing_with_a_processed_photograph(client, conn, store, seller, visibility="NOT_SHOW")


@pytest.fixture
async def published_show_listing(client: Any, conn: Any, redis: Any, store: Any,
                                 seller: dict[str, str]) -> tuple[str, Any]:
    """A published listing with `identifiable_content_visibility = 'SHOW'` and one processed
    photograph. It exists for the helper's own self-test and for the SHOW arms below."""
    return await _listing_with_a_processed_photograph(client, conn, store, seller, visibility="SHOW")


async def assert_buyer_sees_only_redacted(client: Any, buyer: dict[str, str], seller: dict[str, str],
                                          admin: dict[str, str], store: Any, listing_id: str, n: int,
                                          row: Any) -> None:
    """(1) the bytes are the redacted derivative and neither display nor the original; (2) no query
    parameter changes that; (3) the owner and reviewer routes refuse this caller; (4) neither
    payload names a hidden photograph; (5) an anonymous caller is refused.

    `async def`, and every call awaited: the suite's client is `httpx.AsyncClient` over
    `ASGITransport` (`tests/api/conftest.py`), so an un-awaited call returns a coroutine and asserts
    nothing at all -- and `-W error` turns the "coroutine was never awaited" warning into the
    failure that catches it. Every caller writes `await assert_buyer_sees_only_redacted(...)`."""
    url = f"/api/listings/{listing_id}/photos/{n}"
    body = (await client.get(url, headers=buyer)).content
    display = store.get(row.display_storage_key)
    original = store.get(row.original_storage_key)
    assert hashlib.sha256(body).hexdigest() == row.redacted_sha256
    assert body != display and body != original

    for query in ("?variant=original", "?variant=display", f"?v={hashlib.sha256(display).hexdigest()[:12]}",
                  "?v=deadbeef", "?variant=original&v=deadbeef"):
        assert (await client.get(url + query, headers=buyer)).content == body
    # HEAD is 200 with the same validators and no body -- which is true only because the route
    # DECLARES `methods=["GET", "HEAD"]`. A `@router.get` route answers HEAD with 405 (FastAPI's
    # APIRoute does not add HEAD the way Starlette's Route does), and asserting 200 here is what
    # would catch a future edit that dropped the method.
    head = await client.head(url, headers=buyer)
    assert head.status_code == 200 and head.content == b""
    assert head.headers["etag"] == f'"{row.redacted_sha256}"'
    assert head.headers["cache-control"] == "private, no-cache"

    owner = f"/api/seller/listings/{listing_id}/photos/{row.asset_id}"
    assert (await client.get(owner + "?variant=original", headers=buyer)).status_code in (403, 404)
    assert (await client.get(owner + "?variant=display", headers=buyer)).status_code in (403, 404)
    assert (await client.get(owner + "?variant=original", headers=seller)).status_code == 200
    reviewer = f"/api/admin/listings/{listing_id}/photos/{row.asset_id}"
    assert (await client.get(reviewer, headers=buyer)).status_code == 403
    # The same request, by the principal whose permission opens it: the refusal above is about the
    # CALLER and not about a route that answers nobody.
    assert (await client.get(reviewer + "?variant=original", headers=admin)).status_code == 200

    for payload in ((await client.get("/api/listings", headers=buyer)).text,
                    (await client.get(f"/api/listings/{listing_id}", headers=buyer)).text):
        for forbidden in (row.display_sha256[:12], hashlib.sha256(original).hexdigest()[:12],
                          "storage_key", "original", "ocr", "identity_matches", "redaction_regions"):
            assert forbidden not in payload, forbidden

    assert (await client.get(url)).status_code == 401


async def test_assert_helper_fails_on_a_display_body(
    client: Any, buyer: dict[str, str], seller: dict[str, str], admin: dict[str, str], store: Any,
    published_show_listing: Any
) -> None:
    """The helper is itself tested: a SHOW listing serves display, so the helper must refuse it.
    Without this the suite could pass by asserting nothing."""
    listing_id, row = published_show_listing
    with pytest.raises(AssertionError):
        await assert_buyer_sees_only_redacted(client, buyer, seller, admin, store, listing_id, 1, row)


async def test_a_not_show_listing_serves_the_redacted_derivative_and_nothing_else(
    client: Any, buyer: dict[str, str], seller: dict[str, str], admin: dict[str, str], store: Any,
    published_not_show_listing: Any
) -> None:
    """Directive 9 and 21, the whole matrix in one call."""
    listing_id, row = published_not_show_listing
    await assert_buyer_sees_only_redacted(client, buyer, seller, admin, store, listing_id, 1, row)


async def test_a_buyer_cannot_obtain_the_original_by_any_query_parameter(
    client: Any, buyer: dict[str, str], store: Any, published_not_show_listing: Any
) -> None:
    """Directive 20, "unauthorised original-image access" and "alternate image endpoints". The
    resolver reads no query parameter at all, so every spelling a caller can invent answers the one
    variant the policy allows."""
    listing_id, row = published_not_show_listing
    original = store.get(row.original_storage_key)
    url = f"/api/listings/{listing_id}/photos/1"
    for query in ("", "?variant=original", "?variant=ORIGINAL", "?variant=original.jpg",
                  "?format=original", "?size=full", "?raw=1", "?variant=display",
                  "?key=" + row.original_storage_key):
        response = await client.get(url + query, headers=buyer)
        assert response.status_code == 200, query
        assert response.content != original, query
        assert hashlib.sha256(response.content).hexdigest() == row.redacted_sha256, query


def test_the_original_key_is_read_only_where_the_spec_says() -> None:
    """Directive 20, "unauthorised original-image access". The identifier is the thing to count:
    three modules name it, and `app/privacy/delivery.py` -- the resolver every buyer request goes
    through -- is deliberately not one of them, because the resolver has no arm that could return
    it."""
    found = {path for path in sorted(str(f.relative_to(ROOT)) for f in (ROOT / "app").rglob("*.py"))
             if "original_storage_key" in (ROOT / path).read_text()}
    assert found == {path for path in ORIGINAL_KEY_MODULES if (ROOT / path).exists()}
    assert "original_storage_key" not in (ROOT / "app/privacy/delivery.py").read_text()


async def test_the_v_parameter_selects_nothing(
    client: Any, buyer: dict[str, str], conn: Any, store: Any, published_not_show_listing: Any
) -> None:
    """Spec F, "predictable asset URLs": `?v=` is a CACHE KEY. A stale one, a forged one and the
    display derivative's own hash all resolve to the variant the server decided on."""
    listing_id, row = published_not_show_listing
    url = f"/api/listings/{listing_id}/photos/1"
    served = (await client.get(url, headers=buyer)).content
    for spelling in ("", f"?v={row.display_sha256[:12]}", "?v=" + "0" * 12, "?v=", "?v=nonsense"):
        assert (await client.get(url + spelling, headers=buyer)).content == served, spelling


async def test_photo_responses_are_private_and_uncacheable_by_intermediaries(
    client: Any, buyer: dict[str, str], published_not_show_listing: Any
) -> None:
    """D-IDP-11, replacing `private, max-age=86400`: a flip changes the ETag, so no shared cache and
    no browser can serve a variant the policy has replaced."""
    listing_id, row = published_not_show_listing
    response = await client.get(f"/api/listings/{listing_id}/photos/1", headers=buyer)
    assert response.headers["cache-control"] == "private, no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["etag"] == f'"{row.redacted_sha256}"'
    assert response.headers["content-type"] == "image/webp"


async def test_a_stale_url_after_a_flip_serves_the_redacted_bytes_not_a_304_of_the_original(
    client: Any, buyer: dict[str, str], conn: Any, store: Any, seller: dict[str, str]
) -> None:
    """Directive 14, "cached browser response". A buyer who holds the SHOW listing's ETag and
    re-validates after the seller flips to NOT_SHOW must be given the redacted bytes, never a 304
    that would let the browser paint what it already has."""
    listing_id, _row = await _listing_with_a_processed_photograph(client, conn, store, seller,
                                                                  visibility="SHOW")
    url = f"/api/listings/{listing_id}/photos/1"
    before = await client.get(url, headers=buyer)
    assert before.status_code == 200
    stale_etag = before.headers["etag"]

    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET identifiable_content_visibility='NOT_SHOW' WHERE id=%s",
                    (listing_id,))
    row = _privacy_of(conn, listing_id, 1)

    after = await client.get(url, headers={**buyer, "If-None-Match": stale_etag})
    assert after.status_code == 200
    assert hashlib.sha256(after.content).hexdigest() == row.redacted_sha256
    assert after.content != before.content
    # ...and the CURRENT validator is what a 304 needs, which is the other half of the rule.
    fresh = await client.get(url, headers={**buyer, "If-None-Match": after.headers["etag"]})
    assert fresh.status_code == 304 and fresh.content == b""


async def test_head_on_the_photo_route_leaks_nothing(
    client: Any, buyer: dict[str, str], store: Any, published_not_show_listing: Any
) -> None:
    """Spec F: HEAD mirrors GET and returns the same headers and no body."""
    listing_id, row = published_not_show_listing
    url = f"/api/listings/{listing_id}/photos/1"
    head = await client.head(url, headers=buyer)
    get = await client.get(url, headers=buyer)
    assert head.status_code == 200 and head.content == b""
    for header in ("etag", "cache-control", "content-type", "x-content-type-options"):
        assert head.headers[header] == get.headers[header], header
    assert row.original_storage_key not in str(head.headers)


def test_the_listing_route_table_is_exactly_the_pinned_literal(dist: Any) -> None:
    """Every path that can return a listing's bytes or payload, pinned. A new route on this surface
    is a deliberate edit here, whose review asks what it serves and to whom."""
    from app.main import create_app
    from tests.conftest import walk_routes

    found = {(method, path) for method, path, _route in walk_routes(create_app(dist=dist).routes)
             if path.startswith(("/api/listings", "/api/seller/listings", "/api/admin/listings"))}
    assert found == LISTING_ROUTES


async def test_buyer_payloads_carry_no_key_no_ocr_no_region(
    client: Any, buyer: dict[str, str], published_not_show_listing: Any
) -> None:
    """Spec F's "API response leakage" row: the list and the detail carry a positional URL and a
    caption, and nothing about how the photograph was processed."""
    listing_id, row = published_not_show_listing
    detail = (await client.get(f"/api/listings/{listing_id}", headers=buyer)).json()
    assert detail["photos"] == [f"/api/listings/{listing_id}/photos/1?v={row.redacted_sha256[:12]}"]
    text = json.dumps(detail)
    for forbidden in ("storage_key", "original", "redacted", "display", "ocr", "identity_matches",
                      "detected_regions", "redaction_regions", "processing_status", "buyer_visible",
                      "seller_confirmed", row.display_sha256[:12]):
        assert forbidden not in text, forbidden


async def test_anonymous_gets_401_on_the_photo_route_on_a_production_shaped_config(
    client: Any, published_not_show_listing: Any, monkeypatch: Any
) -> None:
    """`listing.read` is members-only, and neither of the two settings that widen anything for an
    anonymous visitor reaches it."""
    monkeypatch.setattr(settings, "market_data_public", True)
    monkeypatch.setattr(settings, "public_indexing", True)
    listing_id, _row = published_not_show_listing
    for path in (f"/api/listings/{listing_id}/photos/1", f"/api/listings/{listing_id}", "/api/listings"):
        assert (await client.get(path)).status_code == 401, path


async def test_an_unprocessed_photograph_is_a_null_slot_and_a_404(
    client: Any, conn: Any, redis: Any, store: Any, buyer: dict[str, str], seller: dict[str, str]
) -> None:
    """The standing rule: every listing is NOT_SHOW by default, and a photograph that has never
    been through the pipeline is not served to a buyer on the grounds that nothing was detected.

    The second photograph is added AFTER the publish, through `tests/privacy/conftest.py`'s own
    builder: migration 042's trigger is `BEFORE UPDATE OF status`, so appending to `listing.photos`
    never asks it -- which is exactly the shape a real published listing reaches when a photograph
    is sent back through the pipeline, and the delivery rule is the only thing protecting it."""
    from tests.privacy.conftest import make_row

    listing_id, first = await _listing_with_a_processed_photograph(
        client, conn, store, seller, visibility="NOT_SHOW")
    make_row(conn, listing_id=UUID(listing_id), processing_status="UPLOADED")

    assert (await client.get(f"/api/listings/{listing_id}/photos/2", headers=buyer)).status_code == 404
    detail = (await client.get(f"/api/listings/{listing_id}", headers=buyer)).json()
    assert detail["photos"] == [
        f"/api/listings/{listing_id}/photos/1?v={first.redacted_sha256[:12]}", None]
    # A-L11's parallel array: a caption is not delivered beside a null slot either.
    assert detail["photo_captions"][1] == ""


async def test_a_seed_path_entry_is_hidden_under_not_show_and_served_under_show(
    client: Any, conn: Any, redis: Any, buyer: dict[str, str]
) -> None:
    """A-IDP-4 (4): a seed photograph has no asset row and no derivative, so NOT_SHOW has nothing
    it could honestly serve -- which is the state all twenty-nine demo hospitals are in until they
    are ingested, processed and confirmed."""
    from app.api.listings import PHOTOS_ROOT

    entry = "abc_animal_hospital/1.webp"
    listing_id = _seed_listing(conn, [entry])
    url = f"/api/listings/{listing_id}/photos/1"
    assert (await client.get(url, headers=buyer)).status_code == 404
    assert (await client.get(f"/api/listings/{listing_id}", headers=buyer)).json()["photos"] == [None]

    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET identifiable_content_visibility='SHOW' WHERE id=%s", (listing_id,))
    shown = await client.get(url, headers=buyer)
    assert shown.status_code == 200
    on_disk = (PHOTOS_ROOT / "abc_animal_hospital" / "1.webp").read_bytes()
    assert shown.content == on_disk
    assert shown.headers["etag"] == f'"{hashlib.sha256(on_disk).hexdigest()}"'
    detail = (await client.get(f"/api/listings/{listing_id}", headers=buyer)).json()
    assert detail["photos"] == [f"/api/listings/{listing_id}/photos/1?v={hashlib.sha256(on_disk).hexdigest()[:12]}"]


def _seed_listing(conn: Any, photos: list[str | None]) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, street, city, state, zip, hours, status,"
            " location_disclosed, name_disclosed, area, type, market, est, price, sqft, source, photos)"
            " VALUES (%s,'Demo Hospital','1 Main St','Austin','TX','78701','24/7','published',"
            " true,true,'Austin','Small animal','Austin, TX',1998,1450000,3000,'seed',%s::jsonb)"
            " RETURNING id", (f"s-{uuid4().hex[:8]}", json.dumps(photos)))
        return str(cur.fetchone()[0])


async def test_a_seed_entry_the_index_still_knows_but_the_disk_has_lost_is_a_404(
    client: Any, conn: Any, redis: Any, buyer: dict[str, str], monkeypatch: Any, tmp_path: Any
) -> None:
    """Directive 19's fail-closed rule, one door over from the bucket
    (`test_a_missing_derivative_object_is_a_404_and_never_a_fallback`, below): `seed_digests()` is
    `@lru_cache`d for the process and does not re-read once warm, so an entry the digest map still
    knows is no promise the FILE is still under `PHOTOS_ROOT` -- `photo_file` checks the disk
    itself, fresh, on every call, and the seed arm has to answer its own refusal exactly as the
    object-storage arm already does."""
    import app.api.listings as listings_module

    entry = "abc_animal_hospital/1.webp"
    listing_id = _seed_listing(conn, [entry])
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET identifiable_content_visibility='SHOW' WHERE id=%s", (listing_id,))

    # Warm the cache against the REAL inventory before pulling the floor out from under `photo_file`:
    # the entry really is a key the committed index knows, sanity-checked rather than assumed.
    listings_module.seed_digests.cache_clear()
    assert entry in listings_module.seed_digests()
    monkeypatch.setattr(listings_module, "PHOTOS_ROOT", tmp_path)   # the file the index knows is "gone"
    try:
        response = await client.get(f"/api/listings/{listing_id}/photos/1", headers=buyer)
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "NOT_FOUND", "message": "No such photograph."}}
    finally:
        # Cleared, not repopulated: the next caller recomputes against the real (monkeypatch-
        # restored) root rather than reusing this test's empty one or this test's `{}`.
        listings_module.seed_digests.cache_clear()


async def test_a_missing_derivative_object_is_a_404_and_never_a_fallback(
    client: Any, buyer: dict[str, str], store: Any, published_not_show_listing: Any
) -> None:
    """Directive 19, fail closed: a bucket that has lost the redacted object answers a missing
    photograph, never the display derivative that is still sitting beside it."""
    listing_id, row = published_not_show_listing
    store.delete(row.redacted_storage_key)
    assert store.get(row.display_storage_key) is not None
    assert (await client.get(f"/api/listings/{listing_id}/photos/1", headers=buyer)).status_code == 404


async def test_a_photograph_of_another_listing_is_a_404_on_this_listings_route(
    client: Any, conn: Any, redis: Any, store: Any, buyer: dict[str, str], seller: dict[str, str]
) -> None:
    """The IDOR check is in SQL: the entry must be in THIS listing's own `photos` and its privacy
    row must name this listing."""
    first, _row = await _listing_with_a_processed_photograph(client, conn, store, seller, visibility="SHOW")
    second, other = await _listing_with_a_processed_photograph(client, conn, store, seller, visibility="SHOW")
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET photos = %s::jsonb WHERE id = %s",
                    (json.dumps([str(other.asset_id)]), first))
    assert (await client.get(f"/api/listings/{first}/photos/1", headers=buyer)).status_code == 404
    assert (await client.get(f"/api/listings/{second}/photos/1", headers=buyer)).status_code == 200


async def test_a_show_listing_serves_display_and_never_the_original(
    client: Any, buyer: dict[str, str], store: Any, published_show_listing: Any
) -> None:
    """The other half of the resolver, end to end: SHOW serves the normalised display derivative --
    the metadata-free WebP -- and the original is unreachable on this route under either setting."""
    listing_id, row = published_show_listing
    response = await client.get(f"/api/listings/{listing_id}/photos/1", headers=buyer)
    assert response.status_code == 200
    assert response.content == store.get(row.display_storage_key)
    assert response.content != store.get(row.original_storage_key)
    assert response.headers["etag"] == f'"{row.display_sha256}"'


async def test_a_photograph_the_pipeline_has_not_finished_is_hidden_under_show_too(
    client: Any, conn: Any, redis: Any, store: Any, buyer: dict[str, str], seller: dict[str, str]
) -> None:
    """SHOW's floor is READY_FOR_REVIEW (directive 11 (1)): "completed processing", not "uploaded"."""
    listing_id, row = await _listing_with_a_processed_photograph(client, conn, store, seller,
                                                                 visibility="SHOW")
    url = f"/api/listings/{listing_id}/photos/1"
    assert (await client.get(url, headers=buyer)).status_code == 200
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET buyer_visible = false,"
                    " processing_status = 'REPROCESS_REQUIRED' WHERE asset_id = %s", (row.asset_id,))
    assert (await client.get(url, headers=buyer)).status_code == 404
    assert (await client.get(f"/api/listings/{listing_id}", headers=buyer)).json()["photos"] == [None]


# --- per-buyer disclosure plan (2026-09-18), Task 7: buyer_variant grows a buyer dimension -------
#
# Everything above this line is the pre-Task-7 security matrix, unmodified, and every one of those
# tests still passes with no `request` row ever created -- which is itself the regression proof:
# `has_capability` returns False for a buyer with no grant, `authorized=False` is byte-for-byte the
# function this whole file already pinned, and nothing above this line creates a grant.


def _seller_id_of(conn: Any, listing_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT seller_id FROM listing WHERE id = %s", (listing_id,))
        return str(cur.fetchone()[0])


def _grant(conn: Any, listing_id: str, buyer_id: str, seller_id: str, *, level: str = "UNREDACTED_IMAGES") -> str:
    """A directly-INSERTed APPROVED `request` row, in `tests/disclosure/test_access.py::_request`'s
    own shape -- Task 7's own authorization boundary (`app.disclosure.access`) is what this suite
    proves the bytes route actually CONSULTS, so this helper writes the grant at the table Tasks
    1-6 already built and unit-tested on their own, rather than re-driving the seller's real decide
    route (Task 6) here too."""
    with conn.cursor() as cur:
        cur.execute(
            # `approved_capabilities` (migration 097, D-C67): the grant is a SET now, and this
            # helper keeps its own single-`level` parameter -- every caller reads the same and means
            # the same -- by expanding it through the one door that always did,
            # `app.disclosure.levels.covers`.
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id, status,"
            " approved_capabilities, reviewed_at, reviewed_by)"
            " VALUES (%s,%s,%s,'APPROVED',%s,now(),%s) RETURNING id",
            (listing_id, buyer_id, seller_id, sorted(covers(level)), seller_id),
        )
        return str(cur.fetchone()[0])


async def test_a_buyer_holding_the_grant_sees_display_while_every_other_buyer_stays_redacted(
    client: Any, conn: Any, redis: Any, member: Any, seller: dict[str, str], admin: dict[str, str],
    store: Any, published_not_show_listing: Any,
) -> None:
    """Directive §7's own critical security test, and §9: "If a seller authorizes unredacted
    images for Buyer A: Buyer A may receive the authorized version; Buyer B must continue receiving
    only the permitted redacted version" -- both halves, one listing, one moment, one test.

    Buyer B's half is the WHOLE pre-existing security matrix (`assert_buyer_sees_only_redacted`):
    the redacted bytes, no query-parameter bypass, the owner/reviewer routes still refusing a
    buyer, no leak in the JSON payloads, and an anonymous caller still 401 -- none of which Task 7
    may have moved for a buyer who holds no grant. Buyer A's half is the NEW capability, proved
    against the REAL object the bucket holds, never a value this test computed."""
    listing_id, row = published_not_show_listing
    seller_id = _seller_id_of(conn, listing_id)

    buyer_a_id, a_cookies, a_headers = member(roles=("buyer",), email="grant-a@example.org")
    buyer_a = auth_headers(a_cookies, a_headers)
    _grant(conn, listing_id, buyer_a_id, seller_id)

    _, b_cookies, b_headers = member(roles=("buyer",), email="grant-b@example.org")
    buyer_b = auth_headers(b_cookies, b_headers)
    await assert_buyer_sees_only_redacted(client, buyer_b, seller, admin, store, listing_id, 1, row)

    url = f"/api/listings/{listing_id}/photos/1"
    body = (await client.get(url, headers=buyer_a)).content
    assert body == store.get(row.display_storage_key)
    assert body != store.get(row.redacted_storage_key)
    assert hashlib.sha256(body).hexdigest() == row.display_sha256

    head = await client.head(url, headers=buyer_a)
    assert head.status_code == 200 and head.content == b""
    assert head.headers["etag"] == f'"{row.display_sha256}"'


async def test_an_unauthorized_buyer_never_receives_the_bytes_behind_the_display_storage_key(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, published_not_show_listing: Any
) -> None:
    """Directive §9's last line, its own test rather than folded into the matrix above: "Direct
    access to the original asset URL must NOT bypass authorization." The bytes route takes no
    storage key at all -- only a POSITION (`n`, spec F) -- so the strongest thing an unauthorized
    caller can do is ask by the EXACT SAME route and the EXACT SAME `n` an authorized buyer would
    use, and the object AT THAT KEY (read straight from the bucket, never a value this test
    computed) must never be what comes back."""
    listing_id, row = published_not_show_listing
    _, cookies, headers = member(roles=("buyer",), email="no-grant-at-all@example.org")
    buyer = auth_headers(cookies, headers)
    display_bytes = store.get(row.display_storage_key)
    assert display_bytes is not None  # the object genuinely exists; this is a real bypass attempt

    response = await client.get(f"/api/listings/{listing_id}/photos/1", headers=buyer)
    assert response.status_code == 200
    assert response.content != display_bytes
    assert hashlib.sha256(response.content).hexdigest() != row.display_sha256
    assert hashlib.sha256(response.content).hexdigest() == row.redacted_sha256


async def test_a_grant_of_a_different_capability_still_serves_the_redacted_derivative(
    client: Any, conn: Any, redis: Any, member: Any, published_not_show_listing: Any
) -> None:
    """Directive §16: SIX named capabilities, never one boolean. A buyer holding a real, ACTIVE
    grant on THIS listing -- just not for UNREDACTED_IMAGES -- has never been approved for images
    at all, and `has_capability`'s own single-capability check (Task 3) is what keeps the two
    apart: a broader "does this buyer hold ANY grant" would leak images to a FINANCIALS-only
    buyer."""
    listing_id, row = published_not_show_listing
    seller_id = _seller_id_of(conn, listing_id)
    buyer_id, cookies, headers = member(roles=("buyer",), email="financials-only@example.org")
    buyer = auth_headers(cookies, headers)
    _grant(conn, listing_id, buyer_id, seller_id, level="FINANCIALS")

    response = await client.get(f"/api/listings/{listing_id}/photos/1", headers=buyer)
    assert response.status_code == 200
    assert hashlib.sha256(response.content).hexdigest() == row.redacted_sha256


async def test_revocation_returns_the_buyer_to_the_redacted_derivative(
    client: Any, conn: Any, redis: Any, member: Any, published_not_show_listing: Any
) -> None:
    """Directive §15: "After revocation, Buyer A must immediately lose authorization to retrieve
    the confidential resource through protected APIs." `app.disclosure.requests.revoke` (Task 4) is
    the one production writer of a REVOKED row; this proves Task 7's route re-reads the grant on
    every request rather than caching an earlier answer -- the SAME buyer, the SAME listing, before
    and after, through the real bytes route both times."""
    from app.disclosure.requests import revoke

    listing_id, row = published_not_show_listing
    seller_id = _seller_id_of(conn, listing_id)
    buyer_id, cookies, headers = member(roles=("buyer",), email="revoke-me@example.org")
    buyer = auth_headers(cookies, headers)
    request_id = _grant(conn, listing_id, buyer_id, seller_id)

    url = f"/api/listings/{listing_id}/photos/1"
    before = (await client.get(url, headers=buyer)).content
    assert hashlib.sha256(before).hexdigest() == row.display_sha256

    revoke(conn, request_id=request_id, seller_account_id=seller_id)

    after = (await client.get(url, headers=buyer)).content
    assert hashlib.sha256(after).hexdigest() == row.redacted_sha256
    assert after != before


async def test_the_json_list_and_detail_routes_now_reflect_a_grant(
    client: Any, conn: Any, redis: Any, member: Any, published_not_show_listing: Any,
) -> None:
    """Task 7's own honest boundary, RETIRED by Task 8 of the per-buyer disclosure plan
    (2026-09-18) exactly as its own docstring predicted: `serialise` -> `_photo_urls` passed
    `authorized=False` UNCONDITIONALLY until Task 8 wired `has_capability`/
    `authorized_capabilities_bulk` into the list and detail routes -- this is that wiring, proved
    from the OTHER side of the seam Task 7 left. A grant that already unlocked the BYTES route
    (proved above) now ALSO changes the URL the JSON payload names for the same photograph: both
    carry the DISPLAY derivative's hash, not the redacted one. This is still not a leak in the
    other direction either: the JSON's `?v=` is a cache key and never a selector (spec F,
    `test_the_v_parameter_selects_nothing`), so it is the capability threaded through `serialise`
    -- never the `?v=` value itself -- that decided which derivative the URL resolves to."""
    listing_id, row = published_not_show_listing
    seller_id = _seller_id_of(conn, listing_id)
    buyer_id, cookies, headers = member(roles=("buyer",), email="grant-json-boundary@example.org")
    buyer = auth_headers(cookies, headers)
    _grant(conn, listing_id, buyer_id, seller_id)

    detail = (await client.get(f"/api/listings/{listing_id}", headers=buyer)).json()
    assert detail["photos"] == [f"/api/listings/{listing_id}/photos/1?v={row.display_sha256[:12]}"]

    # The SAME buyer, the SAME photograph, the BYTES route: authorized, unaffected by the JSON's
    # own `?v=` (spec F: `?v=` is never read for resolution, proved for real above) -- and now the
    # TWO routes agree about which derivative this buyer gets, rather than disagreeing by design.
    bytes_response = await client.get(f"/api/listings/{listing_id}/photos/1", headers=buyer)
    assert hashlib.sha256(bytes_response.content).hexdigest() == row.display_sha256

    # A second buyer, same listing, same moment, NO grant: the two routes must still agree with
    # EACH OTHER on the redacted derivative, exactly as the granted buyer's own pair agrees on the
    # display one -- directive §7's isolation, restated at the JSON/bytes-route boundary Task 7
    # could not reach yet.
    _other_id, other_cookies, other_headers = member(roles=("buyer",), email="grant-json-boundary-b@example.org")
    other = auth_headers(other_cookies, other_headers)
    other_detail = (await client.get(f"/api/listings/{listing_id}", headers=other)).json()
    assert other_detail["photos"] == [f"/api/listings/{listing_id}/photos/1?v={row.redacted_sha256[:12]}"]
    other_bytes = await client.get(f"/api/listings/{listing_id}/photos/1", headers=other)
    assert hashlib.sha256(other_bytes.content).hexdigest() == row.redacted_sha256


# --- the owner's and the reviewer's own bytes routes (spec C.6) ----------------------------------


async def test_the_owner_sees_what_they_uploaded(
    client: Any, seller: dict[str, str], store: Any, published_not_show_listing: Any
) -> None:
    """"The owner sees their own truth": the redaction is about what BUYERS see. `?variant=original`
    is the uploaded file, byte for byte, and it is reachable by this route and by no other."""
    listing_id, row = published_not_show_listing
    url = f"/api/seller/listings/{listing_id}/photos/{row.asset_id}"
    original = await client.get(url + "?variant=original", headers=seller)
    assert original.status_code == 200
    assert original.content == store.get(row.original_storage_key)
    assert original.headers["content-type"] == "image/jpeg"
    assert original.headers["cache-control"] == "private, no-store"
    assert original.headers["content-disposition"] == "inline"
    assert original.headers["x-content-type-options"] == "nosniff"
    for variant, key in (("display", row.display_storage_key), ("redacted", row.redacted_storage_key)):
        response = await client.get(f"{url}?variant={variant}", headers=seller)
        assert response.status_code == 200, variant
        assert response.content == store.get(key), variant


async def test_the_owners_default_variant_is_what_a_buyer_would_see(
    client: Any, conn: Any, redis: Any, store: Any, seller: dict[str, str]
) -> None:
    """No `?variant=` is the LISTING's own buyer-facing representation, so the step-6 tile and the
    review dialog show what a buyer would get rather than what the seller uploaded."""
    hidden, hidden_row = await _listing_with_a_processed_photograph(
        client, conn, store, seller, visibility="NOT_SHOW")
    shown, shown_row = await _listing_with_a_processed_photograph(
        client, conn, store, seller, visibility="SHOW")
    for listing_id, row, key in ((hidden, hidden_row, hidden_row.redacted_storage_key),
                                 (shown, shown_row, shown_row.display_storage_key)):
        response = await client.get(
            f"/api/seller/listings/{listing_id}/photos/{row.asset_id}", headers=seller)
        assert response.status_code == 200
        assert response.content == store.get(key)
        assert response.headers["content-type"] == "image/webp"


async def test_another_sellers_photograph_is_a_404_and_never_a_403(
    client: Any, conn: Any, redis: Any, store: Any, member: Any, seller: dict[str, str]
) -> None:
    """D7: ownership is in the SQL, so another seller's listing is a 404 byte-identical to a missing
    one -- a listing that is not yours should not be confirmed to exist."""
    listing_id, row = await _listing_with_a_processed_photograph(
        client, conn, store, seller, visibility="NOT_SHOW")
    _aid, cookies, headers = member(roles=("seller",), email="p9-other-seller@example.org")
    other = auth_headers(cookies, headers)
    refused = await client.get(
        f"/api/seller/listings/{listing_id}/photos/{row.asset_id}?variant=original", headers=other)
    assert refused.status_code == 404
    assert refused.json()["error"]["code"] == "NOT_FOUND"


async def test_the_reviewer_reads_any_sellers_photograph_and_a_buyer_reads_none(
    client: Any, store: Any, admin: dict[str, str], buyer: dict[str, str],
    published_not_show_listing: Any
) -> None:
    """Spec A.4 row 6, closed: before this the reviewer decided blind. One handler body, two mount
    points -- the reviewer's has no ownership scope, because `listing.review` IS the permission to
    look at anybody's listing."""
    listing_id, row = published_not_show_listing
    url = f"/api/admin/listings/{listing_id}/photos/{row.asset_id}"
    original = await client.get(url + "?variant=original", headers=admin)
    assert original.status_code == 200 and original.content == store.get(row.original_storage_key)
    default = await client.get(url, headers=admin)
    assert default.status_code == 200 and default.content == store.get(row.redacted_storage_key)
    assert (await client.get(url, headers=buyer)).status_code == 403
    assert (await client.get(url)).status_code == 401


async def test_the_reviewers_photo_route_answers_a_missing_listing_with_404(
    client: Any, admin: dict[str, str]
) -> None:
    """The reviewer's mount reads the listing through `_row` before it ever asks
    `photo_variant_response` about the photograph (spec C.6) -- the same `_row` and the same
    envelope `test_admin_listings.py::test_a_listing_that_does_not_exist_is_a_404_in_the_envelope`
    already proves for the read-one route, one door over."""
    url = "/api/admin/listings/11111111-1111-1111-1111-111111111111/photos/22222222-2222-2222-2222-222222222222"
    response = await client.get(url, headers=admin)
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "No such listing."}}


async def test_the_reviewers_photo_route_converts_the_resolvers_refusal_into_its_own_404(
    client: Any, seller: dict[str, str], admin: dict[str, str]
) -> None:
    """`photo_variant_response` is IMPORTED and not re-implemented (spec C.6): the reviewer's own
    mount wraps it in a try/except `Refusal`, and that except has to answer the same envelope the
    seller's mount already proves below in `test_an_unknown_variant_is_refused_and_names_the_three`
    -- a bad photograph id is the simplest `Refusal` either mount can raise."""
    listing_id = await _draft(client, seller)
    response = await client.get(f"/api/admin/listings/{listing_id}/photos/not-a-uuid", headers=admin)
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "No such photograph."}}


async def test_an_unknown_variant_is_refused_and_names_the_three(
    client: Any, seller: dict[str, str], published_not_show_listing: Any
) -> None:
    listing_id, row = published_not_show_listing
    url = f"/api/seller/listings/{listing_id}/photos/{row.asset_id}"
    for spelling in ("?variant=ORIGINAL", "?variant=raw", "?variant=", "?variant=original.jpg"):
        refused = await client.get(url + spelling, headers=seller)
        assert refused.status_code == 400, spelling
        assert refused.json()["error"]["code"] == "BAD_REQUEST", spelling
        assert "display, redacted, original" in refused.json()["error"]["message"], spelling


async def test_a_variant_that_does_not_exist_yet_is_a_404_on_the_owner_route(
    client: Any, conn: Any, redis: Any, store: Any, seller: dict[str, str]
) -> None:
    """An unprocessed photograph has no redacted derivative, and the owner route says so rather
    than substituting the one it does have."""
    listing_id = await _draft(client, seller)
    asset_id = await _upload(client, listing_id, seller)
    url = f"/api/seller/listings/{listing_id}/photos/{asset_id}"
    assert (await client.get(url + "?variant=redacted", headers=seller)).status_code == 404
    assert (await client.get(url + "?variant=display", headers=seller)).status_code == 200
    for bad in (str(uuid4()), "not-a-uuid"):
        assert (await client.get(f"/api/seller/listings/{listing_id}/photos/{bad}",
                                 headers=seller)).status_code == 404


async def test_the_owner_route_revalidates_on_the_content_hash(
    client: Any, seller: dict[str, str], published_not_show_listing: Any
) -> None:
    listing_id, row = published_not_show_listing
    url = f"/api/seller/listings/{listing_id}/photos/{row.asset_id}"
    first = await client.get(url, headers=seller)
    assert first.headers["etag"] == f'"{row.redacted_sha256}"'
    again = await client.get(url, headers={**seller, "If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    # The ORIGINAL carries no stored hash, so its validator is computed from the bytes served.
    original = await client.get(url + "?variant=original", headers=seller)
    repeat = await client.get(url + "?variant=original",
                              headers={**seller, "If-None-Match": original.headers["etag"]})
    assert repeat.status_code == 304


async def test_a_bucket_that_has_lost_the_object_is_a_404_on_the_owner_route(
    client: Any, seller: dict[str, str], store: Any, published_not_show_listing: Any
) -> None:
    """The same rule the buyer route follows: every "no" is one 404, never a 500 and never another
    object."""
    listing_id, row = published_not_show_listing
    store.delete(row.original_storage_key)
    url = f"/api/seller/listings/{listing_id}/photos/{row.asset_id}"
    assert (await client.get(url + "?variant=original", headers=seller)).status_code == 404
    assert (await client.get(url, headers=seller)).status_code == 200
