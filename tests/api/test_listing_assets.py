"""Seller uploads on object storage (spec 2026-09-08 D14, D15, D18, D19), against moto.

The `store` fixture points `settings`' four `S3_*` fields at a moto-backed bucket for the length of
one test, so the routes reach object storage through their OWN `store_for_request()` — no test
needs credentials and none reaches the network. (The brief proposed monkeypatching
`store_for_request` itself; pointing the settings instead leaves the real function on the path, so
its configured arm is exercised rather than replaced, and `app/api/listings.py::_asset_bytes`,
which builds its own store from the same settings, is reached by the same fixture.)

`ENDPOINT` is an AWS-shaped host on purpose: moto 5's interceptor matches the request URL, so a
Railway bucket endpoint would ESCAPE the mock and make a real HTTPS call (proved by trying it).
Never put a fleet endpoint in this file.

Every refusal is asserted as an `{"error": {...}}` body, never `{"detail": ...}`.
"""
from __future__ import annotations

import io
import json
from contextlib import closing
from typing import Any
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from PIL import Image

from app.config import settings
from app.storage import ObjectStore
from tests.api.conftest import auth_headers, padded_json

BUCKET = "pm-test"
ENDPOINT = "https://s3.amazonaws.com"

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
XLSX = b"PK\x03\x04" + b"\x00" * 40
CSV = b"month,revenue\n2026-01,84000\n2026-02,91250\n"

_SEED_INSERT = """
INSERT INTO listing (slug, name, street, city, state, zip, hours, status, location_disclosed,
                     name_disclosed, area, type, market, est, price, source, photos)
VALUES (%(slug)s, 'Demo Hospital', '1 Main St', 'Austin', 'TX', '78701', '24/7', 'published',
        true, true, 'Austin', 'Small animal', 'Austin, TX', 1998, 1450000, 'seed', %(photos)s::jsonb)
RETURNING id
"""


def _intercepted_by_moto(endpoint: str) -> bool:
    """Whether moto 5 will intercept a request to `endpoint`, asserting rather than reporting.

    A-SL16 M4: moto matches the request URL, so a bucket endpoint from the fleet ESCAPES `mock_aws`
    and makes a real HTTPS call — which is what happened the first time this fixture was written.
    The credentials are dummies, so such a call would fail rather than reach a real bucket; a test
    suite that can talk to the internet is still not a test suite."""
    assert endpoint.endswith(".amazonaws.com"), (
        f"{endpoint} escapes moto's interceptor; the fake bucket must be an AWS-shaped host")
    return True


@pytest.fixture
def store(monkeypatch: Any) -> Any:
    """A moto bucket, reached through the real `ObjectStore.from_settings`."""
    _intercepted_by_moto(ENDPOINT)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        for name, value in (("s3_endpoint_url", ENDPOINT), ("s3_bucket", BUCKET),
                            ("s3_access_key_id", "AKIA"), ("s3_secret_access_key", "secret")):
            monkeypatch.setattr(settings, name, value)
        _intercepted_by_moto(str(settings.s3_endpoint_url))
        yield ObjectStore.from_settings(settings)


def _seller(member: Any, email: str = "sl4-seller@example.org") -> tuple[Any, dict[str, str], dict[str, str]]:
    return member(roles=("buyer", "seller"), email=email)


async def _create(client: Any, cookies: dict[str, str], headers: dict[str, str]) -> str:
    response = await client.post("/api/seller/listings", headers=auth_headers(cookies, headers))
    assert response.status_code == 201, response.text
    listing_id: str = response.json()["id"]
    return listing_id


def _jpeg(width: int = 240, height: int = 180, *, gps: bool = False) -> bytes:
    """A small JPEG, optionally carrying the GPS IFD a phone photograph really does."""
    image = Image.new("RGB", (width, height), (120, 30, 30))
    buffer = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[0x8825] = {1: "N", 2: (30.0, 16.0, 0.0), 3: "W", 4: (97.0, 44.0, 0.0)}
        image.save(buffer, "JPEG", exif=exif.tobytes())
    else:
        image.save(buffer, "JPEG")
    return buffer.getvalue()


async def _upload_photo(client: Any, listing_id: str, signed: dict[str, str], data: bytes | None = None,
                        *, filename: str = "front.jpg", content_type: str = "image/jpeg") -> Any:
    return await client.post(
        f"/api/seller/listings/{listing_id}/photos",
        files={"file": (filename, data if data is not None else _jpeg(), content_type)},
        headers=signed,
    )


async def _upload_document(client: Any, listing_id: str, signed: dict[str, str], data: bytes = PDF,
                           *, filename: str = "accounts.pdf", content_type: str = "application/pdf",
                           kind: str | None = None) -> Any:
    return await client.post(
        f"/api/seller/listings/{listing_id}/documents",
        files={"file": (filename, data, content_type)},
        data={"kind": kind} if kind is not None else None,
        headers=signed,
    )


def _photos(conn: Any, listing_id: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT photos FROM listing WHERE id=%s", (listing_id,))
        return list(cur.fetchone()[0])


def _asset_rows(conn: Any, listing_id: str) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, kind, name, content_type, byte_size, sha256, storage_key, created_at"
                    " FROM listing_asset WHERE listing_id=%s ORDER BY created_at, id", (listing_id,))
        return list(cur.fetchall())


def _publish(conn: Any, listing_id: str) -> None:
    """The draft, made publishable: 030's two CHECKs want the wizard's own fields plus the three
    the reviewer supplies at the first publish (D12)."""
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET name='Hill Country Animal Hospital', city='Cedar Park', zip='78613',"
                    " type='Small animal', est=1998, price=1450000, state='TX', market='Austin, TX',"
                    " area='Cedar Park', status='published' WHERE id=%s", (listing_id,))


def _seed_listing(conn: Any, photos: list[str | None]) -> str:
    with conn.cursor() as cur:
        cur.execute(_SEED_INSERT, {"slug": f"s-{uuid4().hex[:8]}", "photos": json.dumps(photos)})
        return str(cur.fetchone()[0])


async def test_a_photograph_is_re_encoded_to_webp_and_recorded(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """D14/D15. The row says which object, whose, what kind and how big; `listing.photos` gains the
    asset id as its LAST entry, because that array is the single home of photo order."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)

    first = await _upload_photo(client, listing_id, signed, filename="front.jpg")
    assert first.status_code == 201, first.text
    body = first.json()
    assert (body["kind"], body["name"], body["content_type"]) == ("photo", "front.jpg", "image/webp")
    second = await _upload_photo(client, listing_id, signed, filename="waiting-room.jpg")
    assert second.status_code == 201, second.text

    rows = _asset_rows(conn, listing_id)
    assert [str(row[0]) for row in rows] == [body["id"], second.json()["id"]]
    asset_id, kind, name, content_type, byte_size, digest, key, _created = rows[0]
    assert (kind, name, content_type) == ("photo", "front.jpg", "image/webp")
    assert len(digest) == 64
    assert key == f"listings/{listing_id}/photos/{asset_id}.webp"
    stored = store.get(key)
    assert stored[:4] == b"RIFF" and stored[8:12] == b"WEBP"
    assert byte_size == len(stored) == body["byte_size"]
    assert _photos(conn, listing_id) == [body["id"], second.json()["id"]]


async def test_an_uploaded_photograph_loses_its_gps(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """D15's load-bearing promise, restated by A10.2: a phone photograph's coordinates must not
    reach a buyer of a listing whose location is undisclosed. The first assertion is what stops
    this passing vacuously."""
    source = _jpeg(gps=True)
    assert Image.open(io.BytesIO(source)).getexif().get_ifd(0x8825), "the fixture must really carry GPS EXIF"

    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await _upload_photo(client, listing_id, auth_headers(cookies, headers), source)
    assert response.status_code == 201, response.text

    stored = Image.open(io.BytesIO(store.get(_asset_rows(conn, listing_id)[0][6])))
    assert not stored.getexif()
    assert stored.info.get("exif") is None
    assert stored.info.get("icc_profile") is None


async def test_there_is_no_photograph_cap_and_the_seventh_is_stored_like_the_first(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """A-SL20 (John, 2026-09-09): "render ALL images". D18's four-photograph cap is withdrawn —
    the design's six slots are what it can CAPTION, not what a listing may hold — so the seventh
    upload is a 201 with a row, an object and an entry in `listing.photos` like every other."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    for _ in range(7):
        assert (await _upload_photo(client, listing_id, signed)).status_code == 201

    assert len(_photos(conn, listing_id)) == 7
    assert len(_asset_rows(conn, listing_id)) == 7
    assert len(store.list(f"listings/{listing_id}/photos/")) == 7


async def test_a_caption_is_the_sellers_own_words_for_one_photograph(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """A-SL20/A-SL22 (2): "have the user articulate what it is". The caption is stored on the
    photograph's own row and comes back as the step-6 tile's name, in `listing.photos`' order."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_photo(client, listing_id, signed)).json()["id"]

    response = await client.patch(f"/api/seller/listings/{listing_id}/assets/{asset_id}",
                                  json={"caption": "  Reception, looking in  "}, headers=signed)
    assert response.status_code == 200, response.text
    assert response.json()["photos"] == [{"id": asset_id, "name": "Reception, looking in"}]
    assert [a["caption"] for a in response.json()["assets"]] == ["Reception, looking in"]


async def test_an_undescribed_photograph_is_named_by_nothing_at_all(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """A-SL22 (2): "never a filename". `DSC_0431.jpg` says nothing about what a buyer is looking
    at, so the tile's name is empty and the DESIGN's own slot caption at that position is what the
    wizard renders (amendment A16.4)."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_photo(client, listing_id, signed, filename="DSC_0431.jpg")).json()["id"]

    read = await client.get(f"/api/seller/listings/{listing_id}", headers=signed)
    assert read.json()["photos"] == [{"id": asset_id, "name": ""}]


async def test_a_blank_caption_clears_the_one_that_was_there(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """The seller can take a description back: blank and null are the same intent, exactly as they
    are for every OPTIONAL wizard field (A-SL18, Info)."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_photo(client, listing_id, signed)).json()["id"]
    await client.patch(f"/api/seller/listings/{listing_id}/assets/{asset_id}",
                       json={"caption": "Reception"}, headers=signed)

    for blank in ("", None):
        response = await client.patch(f"/api/seller/listings/{listing_id}/assets/{asset_id}",
                                      json={"caption": blank}, headers=signed)
        assert response.status_code == 200, response.text
        assert response.json()["photos"] == [{"id": asset_id, "name": ""}]


async def test_a_caption_is_refused_when_it_is_not_text_and_when_the_asset_is_not_this_listings(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    other_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_photo(client, listing_id, signed)).json()["id"]

    refused = await client.patch(f"/api/seller/listings/{listing_id}/assets/{asset_id}",
                                 json={"caption": 7}, headers=signed)
    assert refused.status_code == 400
    assert refused.json() == {"error": {"code": "BAD_REQUEST", "message": "caption must be text."}}

    for path in (f"/api/seller/listings/{other_id}/assets/{asset_id}",
                 f"/api/seller/listings/{listing_id}/assets/not-a-uuid",
                 f"/api/seller/listings/{listing_id}/assets/{uuid4()}"):
        missing = await client.patch(path, json={"caption": "x"}, headers=signed)
        assert missing.status_code == 404, path
        assert missing.json() == {"error": {"code": "NOT_FOUND", "message": "No such asset."}}


async def test_captioning_a_document_is_refused_because_only_a_photograph_carries_one(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """The caption is what the design's photo slot would otherwise have said; a document row is
    named by its own filename on the design's own tile and has no slot to stand in for."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    doc_id = (await _upload_document(client, listing_id, signed)).json()["id"]

    refused = await client.patch(f"/api/seller/listings/{listing_id}/assets/{doc_id}",
                                 json={"caption": "x"}, headers=signed)
    assert refused.status_code == 404
    assert refused.json() == {"error": {"code": "NOT_FOUND", "message": "No such asset."}}


async def test_a_photograph_that_is_not_an_image_is_refused(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """The declared type is a claim the uploader controls: a `.jpg` announced as `image/jpeg` and
    carrying a zip's magic number is the encoder's `None`, which is this route's 422."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    refused = await _upload_photo(client, listing_id, auth_headers(cookies, headers), b"PK\x03\x04not-an-image")
    assert refused.status_code == 422
    assert refused.json() == {"error": {"code": "BAD_IMAGE", "message": "That file could not be read as a photograph."}}
    assert _asset_rows(conn, listing_id) == []
    assert store.list(f"listings/{listing_id}/") == []
    assert _photos(conn, listing_id) == []


async def test_a_photograph_of_an_unsupported_type_is_refused(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    refused = await _upload_photo(client, listing_id, auth_headers(cookies, headers),
                                  b"GIF89a", filename="p.gif", content_type="image/gif")
    assert refused.status_code == 415
    assert refused.json()["error"]["code"] == "UNSUPPORTED_TYPE"
    assert _asset_rows(conn, listing_id) == []


async def test_a_photograph_over_fifteen_megabytes_is_refused_before_it_is_decoded(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, monkeypatch: Any
) -> None:
    """The ceiling is read off `Content-Length` BEFORE the body is parsed, so a 40 MB "photograph"
    is never spooled and never handed to Pillow. `encode_webp` is replaced by something that raises
    — reaching it at all fails this test."""
    from app.api import seller_listings as SL

    def _never(_data: bytes) -> None:
        raise AssertionError("the encoder must not be reached")

    monkeypatch.setattr(SL, "encode_webp", _never)
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    refused = await _upload_photo(client, listing_id, auth_headers(cookies, headers),
                                  b"\x00" * (SL.MAX_PHOTO_BYTES + 8192))
    assert refused.status_code == 413
    assert refused.json() == {"error": {"code": "TOO_LARGE", "message": "The file is larger than 15 MB."}}
    assert _asset_rows(conn, listing_id) == []


async def test_reorder_rewrites_listing_photos_and_nothing_else(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """D15 reason 3: order lives in `listing.photos` and nowhere else, so a reorder touches no
    `listing_asset` row at all."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    ids = [(await _upload_photo(client, listing_id, signed)).json()["id"] for _ in range(3)]
    before = _asset_rows(conn, listing_id)

    response = await client.patch(f"/api/seller/listings/{listing_id}/photos",
                                  json={"ids": list(reversed(ids))}, headers=signed)
    assert response.status_code == 200, response.text
    assert _photos(conn, listing_id) == list(reversed(ids))
    assert _asset_rows(conn, listing_id) == before


@pytest.mark.parametrize("shape", ["missing", "extra", "duplicate", "foreign"])
async def test_reorder_refuses_a_list_that_is_not_exactly_this_listings_photos(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, shape: str
) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    other_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    ids = [(await _upload_photo(client, listing_id, signed)).json()["id"] for _ in range(2)]
    foreign = (await _upload_photo(client, other_id, signed)).json()["id"]
    sent = {"missing": ids[:1], "extra": [*ids, str(uuid4())],
            "duplicate": [ids[0], ids[0]], "foreign": [ids[0], foreign]}[shape]

    refused = await client.patch(f"/api/seller/listings/{listing_id}/photos", json={"ids": sent}, headers=signed)
    assert refused.status_code == 400, refused.text
    assert refused.json()["error"]["code"] == "BAD_REQUEST"
    assert _photos(conn, listing_id) == ids


@pytest.mark.parametrize("body", [["a", "b"], {"ids": "abc"}, {"ids": [1, 2]}, {}])
async def test_reorder_refuses_a_body_that_is_not_a_list_of_ids(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, body: Any
) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    refused = await client.patch(f"/api/seller/listings/{listing_id}/photos", json=body,
                                 headers=auth_headers(cookies, headers))
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "BAD_REQUEST"


async def test_delete_removes_the_row_the_object_and_the_photos_entry_in_one_transaction(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    ids = [(await _upload_photo(client, listing_id, signed)).json()["id"] for _ in range(3)]
    key = f"listings/{listing_id}/photos/{ids[1]}.webp"
    assert store.exists(key) is True

    response = await client.delete(f"/api/seller/listings/{listing_id}/assets/{ids[1]}", headers=signed)
    assert response.status_code == 204, response.text
    assert response.content == b""
    assert [str(row[0]) for row in _asset_rows(conn, listing_id)] == [ids[0], ids[2]]
    assert store.exists(key) is False
    assert _photos(conn, listing_id) == [ids[0], ids[2]]


async def test_deleting_a_document_leaves_listing_photos_alone(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """The other arm of the delete's one `if`: a document was never in `listing.photos`."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    photo = (await _upload_photo(client, listing_id, signed)).json()["id"]
    document = (await _upload_document(client, listing_id, signed)).json()["id"]

    assert (await client.delete(f"/api/seller/listings/{listing_id}/assets/{document}", headers=signed)).status_code == 204
    assert _photos(conn, listing_id) == [photo]
    assert [str(row[0]) for row in _asset_rows(conn, listing_id)] == [photo]


@pytest.mark.parametrize("asset", ["foreign", "unknown", "not-a-uuid"])
async def test_delete_of_another_listings_asset_is_a_404(client: Any, conn: Any, redis: Any, member: Any, store: Any, asset: str) -> None:
    """Scoped by `listing_id`, not by asset id alone — an asset id is not a capability."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    other_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    foreign = (await _upload_photo(client, other_id, signed)).json()["id"]
    target = {"foreign": foreign, "unknown": str(uuid4()), "not-a-uuid": "not-a-uuid"}[asset]

    refused = await client.delete(f"/api/seller/listings/{listing_id}/assets/{target}", headers=signed)
    assert refused.status_code == 404
    assert refused.json() == {"error": {"code": "NOT_FOUND", "message": "No such asset."}}
    assert [str(row[0]) for row in _asset_rows(conn, other_id)] == [foreign]
    assert store.exists(f"listings/{other_id}/photos/{foreign}.webp") is True


async def test_a_document_is_stored_as_uploaded_with_its_kind(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """D18: the approved step 6 has no kind picker, so the wizard sends nothing and the row reads
    `other`; the API takes `kind` today so Rev 3's picker needs no API change."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)

    defaulted = await _upload_document(client, listing_id, signed)
    assert defaulted.status_code == 201, defaulted.text
    assert defaulted.json()["kind"] == "other"
    named = await _upload_document(client, listing_id, signed, filename="plan.pdf", kind="floor_plan")
    assert named.status_code == 201 and named.json()["kind"] == "floor_plan"
    # A blank optional field CLEARS rather than refuses (controller ruling on D10's wording), so an
    # adapter that always sends the field reads exactly like one that omits it.
    blank = await _upload_document(client, listing_id, signed, filename="notes.pdf", kind="")
    assert blank.status_code == 201 and blank.json()["kind"] == "other"

    row = _asset_rows(conn, listing_id)[0]
    asset_id, kind, name, content_type, byte_size, _digest, key, _created = row
    assert (kind, name, content_type, byte_size) == ("other", "accounts.pdf", "application/pdf", len(PDF))
    assert key == f"listings/{listing_id}/documents/{asset_id}.pdf"
    assert store.get(key) == PDF


@pytest.mark.parametrize(("data", "content_type", "filename", "suffix"), [
    (PDF, "application/pdf", "accounts.pdf", ".pdf"),
    (XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "equipment.xlsx", ".xlsx"),
    (CSV, "text/csv", "revenue.csv", ".csv"),
])
async def test_the_three_document_types_are_accepted_and_sniffed(
    client: Any, conn: Any, redis: Any, member: Any, store: Any,
    data: bytes, content_type: str, filename: str, suffix: str
) -> None:
    """Q3, John's ruled default: PDF, CSV and XLSX, and no fourth."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await _upload_document(client, listing_id, auth_headers(cookies, headers), data,
                                      filename=filename, content_type=content_type)
    assert response.status_code == 201, response.text
    key = _asset_rows(conn, listing_id)[0][6]
    assert key.endswith(suffix)
    assert store.get(key) == data


@pytest.mark.parametrize(("data", "content_type", "filename"), [
    (b"MZ\x90\x00this is an executable", "application/pdf", "accounts.pdf"),
    (b"\xff\xfe\x00\x01undecodable", "text/csv", "revenue.csv"),
])
async def test_a_document_whose_bytes_contradict_its_content_type_is_refused(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, data: bytes, content_type: str, filename: str
) -> None:
    """Content sniffed from the bytes, never trusted from the declared type or the extension."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    refused = await _upload_document(client, listing_id, auth_headers(cookies, headers), data,
                                     filename=filename, content_type=content_type)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "BAD_DOCUMENT"
    assert _asset_rows(conn, listing_id) == []
    assert store.list(f"listings/{listing_id}/") == []


@pytest.mark.parametrize("content_type", ["image/svg+xml", "application/zip", "text/html"])
async def test_a_document_type_outside_the_allow_list_is_refused(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, content_type: str
) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    refused = await _upload_document(client, listing_id, auth_headers(cookies, headers), b"<svg/>",
                                     filename="x", content_type=content_type)
    assert refused.status_code == 415
    assert refused.json()["error"]["code"] == "UNSUPPORTED_TYPE"
    assert _asset_rows(conn, listing_id) == []


async def test_a_document_of_an_unknown_kind_is_refused(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    refused = await _upload_document(client, listing_id, auth_headers(cookies, headers), kind="photo")
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "BAD_REQUEST"
    assert _asset_rows(conn, listing_id) == []


async def test_a_document_over_twenty_five_megabytes_is_refused(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """One byte over, so `Content-Length` is inside the multipart allowance and the ceiling is the
    one applied to what actually ARRIVED — the other arm of the size check."""
    from app.api import seller_listings as SL

    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    refused = await _upload_document(client, listing_id, auth_headers(cookies, headers),
                                     PDF + b"\x00" * (SL.MAX_DOCUMENT_BYTES + 1 - len(PDF)))
    assert refused.status_code == 413
    assert refused.json() == {"error": {"code": "TOO_LARGE", "message": "The file is larger than 25 MB."}}
    assert _asset_rows(conn, listing_id) == []


async def test_the_seventh_document_is_refused(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    for _ in range(6):
        assert (await _upload_document(client, listing_id, signed)).status_code == 201

    refused = await _upload_document(client, listing_id, signed)
    assert refused.status_code == 409
    assert refused.json() == {"error": {"code": "DOCUMENT_LIMIT", "message": "A listing may carry 6 documents."}}
    assert len(_asset_rows(conn, listing_id)) == 6


async def test_a_document_reads_to_its_owner_and_to_staff_and_to_nobody_else(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """D19's "Locked — seller approval", exactly as the design draws it, with no new approval
    workflow (John's ruling). The buyer-with-an-accepted-request arm is the requests sub-project's
    and is not invented here."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_document(client, listing_id, signed)).json()["id"]
    path = f"/api/seller/listings/{listing_id}/documents/{asset_id}"

    _, staff_cookies, staff_headers = member(roles=("staff",), email="sl4-staff@example.org")
    _, buyer_cookies, buyer_headers = member(roles=("buyer",), email="sl4-buyer@example.org")

    owner = await client.get(path, headers=signed)
    staff = await client.get(path, headers=auth_headers(staff_cookies, staff_headers))
    other = await client.get(path, headers=auth_headers(buyer_cookies, buyer_headers))
    anonymous = await client.get(path, headers={"Origin": "https://qa.foundation.vin"})

    assert owner.status_code == 200 and owner.content == PDF
    assert staff.status_code == 200 and staff.content == PDF
    assert other.status_code == 403
    assert other.json() == {"error": {"code": "LOCKED", "message": "This document is locked until the seller approves access."}}
    assert anonymous.status_code == 401
    assert anonymous.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}


async def test_a_document_read_carries_the_download_headers(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_document(client, listing_id, signed)).json()["id"]

    response = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=signed)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == "attachment"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("asset", ["photo", "unknown", "not-a-uuid"])
async def test_a_document_read_of_something_that_is_not_this_listings_document_is_a_404(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, asset: str
) -> None:
    """A photograph is not a document, an unknown id is not a document, and neither is a string
    that is not a uuid — all three are the same 404."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    photo = (await _upload_photo(client, listing_id, signed)).json()["id"]
    target = {"photo": photo, "unknown": str(uuid4()), "not-a-uuid": "not-a-uuid"}[asset]

    refused = await client.get(f"/api/seller/listings/{listing_id}/documents/{target}", headers=signed)
    assert refused.status_code == 404
    assert refused.json() == {"error": {"code": "NOT_FOUND", "message": "No such document."}}


async def test_a_document_read_of_a_listing_that_does_not_exist_is_a_404(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    _, cookies, headers = _seller(member)
    for listing_id in (str(uuid4()), "not-a-uuid"):
        refused = await client.get(f"/api/seller/listings/{listing_id}/documents/{uuid4()}",
                                   headers=auth_headers(cookies, headers))
        assert refused.status_code == 404, listing_id


async def test_a_document_whose_object_has_vanished_is_a_404_not_a_500(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_document(client, listing_id, signed)).json()["id"]
    store.delete(f"listings/{listing_id}/documents/{asset_id}.pdf")

    refused = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=signed)
    assert refused.status_code == 404
    assert refused.json()["error"]["code"] == "NOT_FOUND"


async def test_a_sellers_photograph_is_served_through_the_unchanged_buyer_route(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """D15 reason 2: `serialise` emits `/api/listings/{id}/photos/{n}` and that route does not
    change, so the frontend, the design and the pixel oracles see nothing at all."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_photo(client, listing_id, signed)).json()["id"]
    _publish(conn, listing_id)
    _, buyer_cookies, buyer_headers = member(roles=("buyer",), email="sl4-buyer@example.org")
    buyer = auth_headers(buyer_cookies, buyer_headers)

    response = await client.get(f"/api/listings/{listing_id}/photos/1", headers=buyer)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "private, max-age=86400"
    assert response.content == store.get(f"listings/{listing_id}/photos/{asset_id}.webp")
    assert response.content[:4] == b"RIFF"
    detail = (await client.get(f"/api/listings/{listing_id}", headers=buyer)).json()
    assert detail["photos"] == [f"/api/listings/{listing_id}/photos/1"]
    assert (await client.get(f"/api/listings/{listing_id}/photos/2", headers=buyer)).status_code == 404


async def test_a_seed_listings_photograph_still_comes_off_disk(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """The other arm of D15 reason 3's single `if`: an entry with a `/` in it is a relative path
    under PHOTOS_ROOT, resolved by `photo_file` and read from the repository, bucket or no bucket."""
    from app.api.listings import PHOTOS_ROOT

    listing_id = _seed_listing(conn, ["abc_animal_hospital/1.webp"])
    _, cookies, headers = member(roles=("buyer",), email="sl4-buyer@example.org")
    response = await client.get(f"/api/listings/{listing_id}/photos/1", headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    assert response.content == (PHOTOS_ROOT / "abc_animal_hospital" / "1.webp").read_bytes()


@pytest.mark.parametrize("entry", ["not-a-uuid", "11111111-1111-1111-1111-111111111111"])
async def test_a_photo_entry_that_names_no_asset_is_a_404_not_a_500(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, entry: str
) -> None:
    """Both arms of `_asset_bytes`'s two refusals: an entry that is not a uuid at all, and a uuid
    that names no row of this listing."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    _publish(conn, listing_id)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET photos=%s::jsonb WHERE id=%s", (json.dumps([entry]), listing_id))
    _, buyer_cookies, buyer_headers = member(roles=("buyer",), email="sl4-buyer@example.org")

    response = await client.get(f"/api/listings/{listing_id}/photos/1",
                                headers=auth_headers(buyer_cookies, buyer_headers))
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "No such photograph."}}


async def test_uploads_are_refused_with_a_clear_message_when_storage_is_unconfigured(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """`from_settings` returning None is a legitimate state — a developer's machine, a fresh test
    database. Only the WRITES stop, and they say which setting; every read that needs no bucket
    keeps working, including the eighteen seed hospitals' photographs."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)

    for refused in (await _upload_photo(client, listing_id, signed),
                    await _upload_document(client, listing_id, signed)):
        assert refused.status_code == 503
        assert refused.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
        assert "S3_BUCKET" in refused.json()["error"]["message"]

    seed_id = _seed_listing(conn, ["abc_animal_hospital/1.webp"])
    _, buyer_cookies, buyer_headers = member(roles=("buyer",), email="sl4-buyer@example.org")
    buyer = auth_headers(buyer_cookies, buyer_headers)
    assert (await client.get(f"/api/listings/{seed_id}/photos/1", headers=buyer)).status_code == 200

    # A seller entry with no bucket to read it from is a 404, not a 500 — `_asset_bytes`'s
    # `store is None` arm.
    asset_id = uuid4()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing_asset (id, listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
                    " VALUES (%s,%s,'photo','front.jpg','image/webp',2048,'sha',%s)",
                    (asset_id, listing_id, f"listings/{listing_id}/photos/{asset_id}.webp"))
        cur.execute("UPDATE listing SET photos=%s::jsonb WHERE id=%s", (json.dumps([str(asset_id)]), listing_id))
    _publish(conn, listing_id)
    assert (await client.get(f"/api/listings/{listing_id}/photos/1", headers=buyer)).status_code == 404


async def test_the_upload_rate_limit_is_per_account(client: Any, conn: Any, redis: Any, member: Any, store: Any, monkeypatch: Any) -> None:
    """D17. Generous enough that a seller uploading four photographs and a document never meets it;
    the test lowers it rather than sending forty-one requests."""
    from app.api import seller_listings as SL

    monkeypatch.setattr(SL, "LISTING_UPLOAD", (1, 3600))
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    assert (await _upload_photo(client, listing_id, signed)).status_code == 201

    refused = await _upload_photo(client, listing_id, signed)
    assert refused.status_code == 429 and refused.json()["error"]["code"] == "RATE_LIMITED"
    other_id, other_cookies, other_headers = _seller(member, email="sl4-second@example.org")
    second = await _upload_photo(client, await _create(client, other_cookies, other_headers),
                                 auth_headers(other_cookies, other_headers))
    assert second.status_code == 201 and other_id is not None


async def test_every_asset_write_drops_the_listings_cache_after_the_commit(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, scratch_dsn: Any, monkeypatch: Any
) -> None:
    """D16, four writers, and the ORDERING the name claims (A-SL16 L7).

    The drop is spied on with a SECOND connection: whatever it can see at the moment
    `drop_list_cache` runs is what a concurrent reader could see, so a spy that finds the new
    `photos` value proves the transaction had already committed. Dropping the key while the write
    was still uncommitted would leave a window in which a concurrent read re-cached the pre-write
    payload for the full TTL."""
    import psycopg2

    from app.api import seller_listings as SL

    seen: list[Any] = []
    original = SL.drop_list_cache

    def _spy(cache: Any) -> int:
        with closing(psycopg2.connect(scratch_dsn)) as probe, probe.cursor() as cur:
            cur.execute("SELECT photos, status FROM listing WHERE id = %s", (listing_id,))
            seen.append(cur.fetchone())
        removed: int = original(cache)
        return removed

    monkeypatch.setattr(SL, "drop_list_cache", _spy)
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    _publish(conn, listing_id)

    def _plant() -> None:
        redis.set("listings:v1:Austin, TX::50", b"stale")
        redis.set("session:keep", b"kept")

    _plant()
    photo = (await _upload_photo(client, listing_id, signed)).json()["id"]
    assert redis.get("listings:v1:Austin, TX::50") is None
    assert redis.get("session:keep") == b"kept"
    # The committed row, seen from outside the request's own transaction.
    assert seen[-1] == ([photo], "in_review")

    _republish(conn, listing_id)
    _plant()
    assert (await _upload_document(client, listing_id, signed)).status_code == 201
    assert redis.get("listings:v1:Austin, TX::50") is None

    _republish(conn, listing_id)
    _plant()
    assert (await client.patch(f"/api/seller/listings/{listing_id}/photos", json={"ids": [photo]},
                               headers=signed)).status_code == 200
    assert redis.get("listings:v1:Austin, TX::50") is None

    _republish(conn, listing_id)
    _plant()
    assert (await client.delete(f"/api/seller/listings/{listing_id}/assets/{photo}", headers=signed)).status_code == 204
    assert redis.get("listings:v1:Austin, TX::50") is None
    assert redis.get("session:keep") == b"kept"
    assert seen[-1] == ([], "in_review")


async def test_an_asset_write_on_a_draft_leaves_the_browse_cache_alone(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """D16's own words are "every write that CAN change a published payload" (review L6). A draft's
    photographs are in no published payload, and a `SCAN` plus a `DELETE` per key on every upload
    flushes Browse for everyone who is reading it."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    redis.set("listings:v1:Austin, TX::50", b"fresh")

    assert (await _upload_photo(client, listing_id, auth_headers(cookies, headers))).status_code == 201
    assert redis.get("listings:v1:Austin, TX::50") == b"fresh"


async def test_a_non_owner_gets_404_on_every_asset_route(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """D7 again, on the five new routes: 404, never 403 — a listing that is not yours should not be
    confirmed to exist, and its assets should not be touchable."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    asset_id = (await _upload_photo(client, listing_id, auth_headers(cookies, headers))).json()["id"]
    _, thief_cookies, thief_headers = _seller(member, email="sl4-thief@example.org")
    thief = auth_headers(thief_cookies, thief_headers)

    for response in (
        await _upload_photo(client, listing_id, thief),
        await _upload_document(client, listing_id, thief),
        await client.patch(f"/api/seller/listings/{listing_id}/photos", json={"ids": [asset_id]}, headers=thief),
        await client.delete(f"/api/seller/listings/{listing_id}/assets/{asset_id}", headers=thief),
        await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=thief),
    ):
        assert response.status_code == 404, response.text
    assert [str(row[0]) for row in _asset_rows(conn, listing_id)] == [asset_id]


async def test_an_upload_to_a_withdrawn_listing_is_refused(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """The same rule the per-step PATCH applies: withdrawn is terminal."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='withdrawn' WHERE id=%s", (listing_id,))

    for refused in (await _upload_photo(client, listing_id, signed),
                    await _upload_document(client, listing_id, signed)):
        assert refused.status_code == 409
        assert refused.json() == {"error": {"code": "STATE", "message": "A withdrawn listing can no longer be edited."}}
    assert _asset_rows(conn, listing_id) == []


@pytest.mark.parametrize("path", ["photos", "documents"])
async def test_an_upload_with_no_file_part_is_refused(client: Any, conn: Any, redis: Any, member: Any, store: Any, path: str) -> None:
    """A JSON body, or a form with the field misnamed: both are the same 400, not a 500."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)

    empty = await client.post(f"/api/seller/listings/{listing_id}/{path}", json={"file": "front.jpg"}, headers=signed)
    misnamed = await client.post(f"/api/seller/listings/{listing_id}/{path}",
                                 files={"photo": ("front.jpg", _jpeg(), "image/jpeg")}, headers=signed)
    for refused in (empty, misnamed):
        assert refused.status_code == 400, refused.text
        assert refused.json() == {"error": {"code": "BAD_REQUEST", "message": "A single `file` part is required."}}


async def test_a_malformed_multipart_body_is_refused_rather_than_a_500(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """A body that announces a boundary and then is not a multipart form at all: the parser raises,
    and the route answers the envelope's 400 rather than an unhandled exception."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.post(
        f"/api/seller/listings/{listing_id}/photos",
        content=b"--x\r\nnot a multipart body at all\r\n",
        headers={**auth_headers(cookies, headers), "Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "BAD_REQUEST"


async def test_a_malformed_json_body_on_reorder_is_a_400_in_the_envelope(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """SL3 review: a body that is not JSON at all must never surface as a raw `JSONDecodeError`."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.patch(
        f"/api/seller/listings/{listing_id}/photos", content=b"{not json",
        headers={**auth_headers(cookies, headers), "Content-Type": "application/json"},
    )
    assert response.status_code == 400, response.text
    assert response.json() == {"error": {"code": "BAD_JSON", "message": "Body must be JSON."}}


async def test_a_reorder_body_at_exactly_the_json_limit_is_accepted(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """A-SL18 (3), Minor-2, the reorder route's own boundary: a fresh listing has no photographs,
    so `{"ids": []}` is a valid reorder of nothing, padded with spaces to exactly `MAX_JSON_BYTES`."""
    from app.api import seller_listings as SL

    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    body = padded_json(SL.MAX_JSON_BYTES, b'{"ids": []}')
    assert len(body) == SL.MAX_JSON_BYTES
    response = await client.patch(
        f"/api/seller/listings/{listing_id}/photos", content=body,
        headers={**auth_headers(cookies, headers), "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text


async def test_a_reorder_body_one_byte_over_the_json_limit_is_refused(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    from app.api import seller_listings as SL

    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    body = padded_json(SL.MAX_JSON_BYTES + 1, b'{"ids": []}')
    assert len(body) == SL.MAX_JSON_BYTES + 1
    response = await client.patch(
        f"/api/seller/listings/{listing_id}/photos", content=body,
        headers={**auth_headers(cookies, headers), "Content-Type": "application/json"},
    )
    assert response.status_code == 413, response.text
    assert response.json() == {"error": {"code": "TOO_LARGE", "message": "Body must be no larger than 64 KB."}}


async def test_the_draft_read_carries_its_photographs_in_order_and_its_documents(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """Step 6's tiles are `listing.photos`' own order, named by the seller's own caption (A-SL20)
    and by NOTHING until they write one (A-SL22 (2): never a filename), and the documents come back
    with the route that reads them back — a document IS named by its filename, which is a true name
    for a document. `assets` is unchanged (SL3's contract) but for the caption column; these two are
    the ordered views of it the wizard renders."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    first = (await _upload_photo(client, listing_id, signed, filename="front.jpg")).json()["id"]
    second = (await _upload_photo(client, listing_id, signed, filename="waiting-room.jpg")).json()["id"]
    document = (await _upload_document(client, listing_id, signed, filename="accounts.pdf")).json()["id"]
    assert (await client.patch(f"/api/seller/listings/{listing_id}/assets/{second}",
                               json={"caption": "Reception, looking in"}, headers=signed)).status_code == 200
    assert (await client.patch(f"/api/seller/listings/{listing_id}/photos",
                               json={"ids": [second, first]}, headers=signed)).status_code == 200

    body = (await client.get(f"/api/seller/listings/{listing_id}", headers=signed)).json()
    assert body["photos"] == [{"id": second, "name": "Reception, looking in"},
                              {"id": first, "name": ""}]
    assert body["documents"] == [{"id": document, "kind": "other", "name": "accounts.pdf",
                                  "content_type": "application/pdf", "byte_size": len(PDF),
                                  "caption": None,
                                  "url": f"/api/seller/listings/{listing_id}/documents/{document}"}]
    assert [asset["id"] for asset in body["assets"]] == [first, second, document]
    assert [asset["caption"] for asset in body["assets"]] == [None, "Reception, looking in", None]


async def test_a_seed_listings_tiles_are_named_by_the_seed_caption(client: Any, conn: Any, redis: Any, member: Any) -> None:
    """The other arm of the tile's name. A seed row belongs to the demo seller on QA (D25), so Edit
    on one reads through this serialiser too — and its `listing.photos` entries are relative paths
    that name no `listing_asset` row, so the committed inventory's caption is what says what the
    picture shows."""
    account_id, cookies, headers = _seller(member)
    photos = [f"abc_animal_hospital/{n}.webp" for n in (1, 2, 3)]
    listing_id = _seed_listing(conn, [*photos, "abc_animal_hospital/nope.webp"])
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET seller_id=%s WHERE id=%s", (account_id, listing_id))

    body = (await client.get(f"/api/seller/listings/{listing_id}", headers=auth_headers(cookies, headers))).json()
    # The committed inventory's own captions, curated slot by slot against the photographs
    # themselves (A-L10, merged from `main`).
    assert body["photos"] == [
        {"id": "abc_animal_hospital/1.webp", "name": "Exterior — front"},
        {"id": "abc_animal_hospital/2.webp", "name": "Interior — reception"},
        {"id": "abc_animal_hospital/3.webp", "name": "Interior — exam room 1"},
        # An entry the inventory does not name is named by NOTHING (A-SL22 (2)): a file name is
        # not a description, and the design's own slot caption at that position is what the
        # wizard renders in its place (amendment A16.4).
        {"id": "abc_animal_hospital/nope.webp", "name": ""},
    ]
    assert body["documents"] == []


async def test_a_seed_slot_the_curation_left_empty_is_no_tile_at_all(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """A-L10 (merged from `main`) stores a JSON `null` for a slot no photograph truthfully fills.
    There is nothing to show for it, so step 6 lists the photographs that exist and no blank tile.

    A-SL23 (6) m2: such a row REORDERS. The id list names the photographs — an empty slot has no
    id to be named by — so the comparison is against the non-null entries and the empty slots stay
    at the positions they were left at. Refusing the whole row instead (SL7 review, Minor-2) said
    "this hospital's photographs can never be reordered", which is not what an empty slot means."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, ["abc_animal_hospital/1.webp", None, "abc_animal_hospital/3.webp"])
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET seller_id=%s WHERE id=%s", (account_id, listing_id))
    signed = auth_headers(cookies, headers)

    body = (await client.get(f"/api/seller/listings/{listing_id}", headers=signed)).json()
    assert body["photos"] == [
        {"id": "abc_animal_hospital/1.webp", "name": "Exterior — front"},
        {"id": "abc_animal_hospital/3.webp", "name": "Interior — exam room 1"},
    ]

    moved = await client.patch(f"/api/seller/listings/{listing_id}/photos",
                               json={"ids": ["abc_animal_hospital/3.webp", "abc_animal_hospital/1.webp"]},
                               headers=signed)
    assert moved.status_code == 200
    assert [tile["id"] for tile in moved.json()["photos"]] == [
        "abc_animal_hospital/3.webp", "abc_animal_hospital/1.webp"]
    with conn.cursor() as cur:
        cur.execute("SELECT photos FROM listing WHERE id = %s", (listing_id,))
        assert cur.fetchone()[0] == ["abc_animal_hospital/3.webp", None, "abc_animal_hospital/1.webp"], \
            "the empty slot stayed where it was; only the photographs moved"

    # A list that is not a permutation of the photographs is still refused — the empty slot is not
    # a photograph a seller may name, and a partial list would silently delete one.
    for bad in (["abc_animal_hospital/3.webp"],
                ["abc_animal_hospital/3.webp", "", "abc_animal_hospital/1.webp"]):
        refused = await client.patch(f"/api/seller/listings/{listing_id}/photos",
                                     json={"ids": bad}, headers=signed)
        assert refused.status_code == 400
        assert refused.json()["error"]["message"] == "ids must be exactly this listing's photographs, in the new order."


def test_the_seed_captions_are_read_from_the_committed_index() -> None:
    from app.api import seller_listings as SL

    captions = SL.seed_captions()
    assert captions["abc_animal_hospital/1.webp"] == "Exterior — front"
    # A-L11 (main, John 2026-09-09: "render ALL images") re-cut the inventory: every photograph is
    # rendered and every one carries its OWN caption, so there is a key per FILE rather than per
    # filled slot. `1111_pet_hospital` was the A-L10 curation's starkest case — one exterior and
    # five empty slots — and now carries ten photographs, each with a caption of its own.
    index = json.loads(SL.PHOTO_INDEX.read_text(encoding="utf-8"))
    for slug, photos in index["hospitals"].items():
        assert [k for k in captions if k.startswith(f"{slug}/")] == [f"{slug}/{photo['file']}" for photo in photos]
    assert len([k for k in captions if k.startswith("1111_pet_hospital/")]) == 10
    assert captions["1111_pet_hospital/1.webp"] == "Exterior — entrance view"
    assert SL.seed_captions() is captions, "read once per process, not once per draft"


def test_an_absent_photo_index_leaves_every_tile_named_by_its_file(tmp_path: Any, monkeypatch: Any) -> None:
    """The tiles must not 500 in an environment whose `seeds/` was not copied — the image does copy
    it (Dockerfile), which is exactly why this arm is proved here rather than left to chance."""
    from app.api import seller_listings as SL

    monkeypatch.setattr(SL, "PHOTO_INDEX", tmp_path / "index.json")
    assert SL.seed_captions.__wrapped__() == {}


async def test_a_listing_id_that_is_not_a_uuid_is_a_404_on_every_asset_write(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """A path segment that names no listing is this module's 404, never FastAPI's 422 on a `UUID`
    path parameter — whose body would be `{"detail": [...]}` rather than the envelope."""
    _, cookies, headers = _seller(member)
    signed = auth_headers(cookies, headers)
    for response in (
        await _upload_photo(client, "not-a-uuid", signed),
        await _upload_document(client, "not-a-uuid", signed),
        await client.patch("/api/seller/listings/not-a-uuid/photos", json={"ids": []}, headers=signed),
        await client.patch(f"/api/seller/listings/not-a-uuid/assets/{uuid4()}", json={"caption": "x"}, headers=signed),
        await client.delete(f"/api/seller/listings/not-a-uuid/assets/{uuid4()}", headers=signed),
    ):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "NOT_FOUND"


def _republish(conn: Any, listing_id: str) -> None:
    """Back on the market, and its review stamp cleared, so the next write's transition is visible."""
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status='published', submitted_at=NULL WHERE id=%s", (listing_id,))


def _status(conn: Any, listing_id: str) -> tuple[Any, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT status, submitted_at FROM listing WHERE id=%s", (listing_id,))
        return tuple(cur.fetchone())


def _audit(conn: Any, listing_id: str) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute("SELECT action, before, after FROM audit_log WHERE target_type='listing' AND target_id=%s",
                    (str(listing_id),))
        return list(cur.fetchall())


async def test_every_asset_write_on_a_published_listing_re_enters_review(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """A-SL15 (1): assets are edits. John's ruling — "editing a published listing re-enters review
    and removes it from the market until approved again" — covers adding, reordering, CAPTIONING
    and deleting a photograph or a document, so each of the five writes applies D3 exactly as
    `patch_step` does, in the same transaction, and writes the same audit row. Captioning is an
    edit for the plainest reason: the caption is what a buyer reads under the photograph."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    _publish(conn, listing_id)

    photo = (await _upload_photo(client, listing_id, signed)).json()["id"]
    status, submitted_at = _status(conn, listing_id)
    assert (status, submitted_at is not None) == ("in_review", True)

    _republish(conn, listing_id)
    assert (await _upload_document(client, listing_id, signed)).status_code == 201
    assert _status(conn, listing_id)[0] == "in_review"

    _republish(conn, listing_id)
    assert (await client.patch(f"/api/seller/listings/{listing_id}/photos", json={"ids": [photo]},
                               headers=signed)).status_code == 200
    assert _status(conn, listing_id)[0] == "in_review"

    _republish(conn, listing_id)
    assert (await client.patch(f"/api/seller/listings/{listing_id}/assets/{photo}",
                               json={"caption": "Reception, looking in"}, headers=signed)).status_code == 200
    assert _status(conn, listing_id)[0] == "in_review"

    _republish(conn, listing_id)
    assert (await client.delete(f"/api/seller/listings/{listing_id}/assets/{photo}", headers=signed)).status_code == 204
    assert _status(conn, listing_id)[0] == "in_review"

    assert _audit(conn, listing_id) == [("listing.edit", {"status": "published"}, {"status": "in_review"})] * 5


async def test_an_asset_write_on_a_draft_leaves_the_lifecycle_alone(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """The other arm of A-SL15 (1): a draft is not on the market, so there is nothing to take off
    it — no transition, no `submitted_at`, no audit row for a review that never happened."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)

    photo = (await _upload_photo(client, listing_id, signed)).json()["id"]
    assert (await _upload_document(client, listing_id, signed)).status_code == 201
    assert (await client.patch(f"/api/seller/listings/{listing_id}/photos", json={"ids": [photo]},
                               headers=signed)).status_code == 200
    assert (await client.delete(f"/api/seller/listings/{listing_id}/assets/{photo}", headers=signed)).status_code == 204

    assert _status(conn, listing_id) == ("draft", None)
    assert _audit(conn, listing_id) == []


BOUNDARY = "----pmtest-boundary"


def _multipart(data: bytes, *, filename: str = "front.jpg", content_type: str = "image/jpeg") -> bytes:
    """One file part, built by hand so the test can hand it to httpx as a STREAM — which is the
    only way to get a request with no `Content-Length` (A-SL16 H1)."""
    head = (f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n").encode()
    return head + data + f"\r\n--{BOUNDARY}--\r\n".encode()


CHUNK = 64 * 1024


async def _chunked(body: bytes, sent: list[int] | None = None) -> Any:
    """`body` as a stream, counting what the SERVER actually pulled: httpx sends an async iterator
    with `Transfer-Encoding: chunked` and no `Content-Length`, and its ASGI transport pulls lazily,
    so a route that stops reading stops this generator."""
    for start in range(0, len(body), CHUNK):
        chunk = body[start:start + CHUNK]
        if sent is not None:
            sent.append(len(chunk))
        yield chunk


@pytest.mark.parametrize(("path", "limit_name", "content_type"), [
    ("photos", "MAX_PHOTO_BYTES", "image/jpeg"),
    ("documents", "MAX_DOCUMENT_BYTES", "application/pdf"),
])
async def test_the_size_ceiling_holds_on_a_body_that_declares_no_length(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, monkeypatch: Any,
    path: str, limit_name: str, content_type: str
) -> None:
    """A-SL16 H1. `Transfer-Encoding: chunked` carries no `Content-Length`, and Starlette caps a
    FILE part at nothing — `max_part_size` guards data parts only (formparsers.py:181-187) — so a
    ceiling read off the header alone was no ceiling at all: one authenticated request could stream
    without bound onto the container's disk and then be read whole into memory.

    The parser is fed a bounded stream now, so the refusal arrives while the body is still coming."""
    from app.api import seller_listings as SL

    def _never(_data: bytes) -> None:
        raise AssertionError("nothing may be decoded from a body that is already too large")

    monkeypatch.setattr(SL, "encode_webp", _never)
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    limit = getattr(SL, limit_name)
    body = _multipart(b"\x00" * (limit + 4 * 1024 * 1024), content_type=content_type)
    sent: list[int] = []

    response = await client.post(
        f"/api/seller/listings/{listing_id}/{path}", content=_chunked(body, sent),
        headers={**auth_headers(cookies, headers), "Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
    )
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "TOO_LARGE"
    # The refusal is the easy half. THIS is the defect: the route must stop pulling the moment the
    # running total passes the ceiling, rather than spooling four more megabytes to disk first.
    assert sum(sent) < len(body)
    assert sum(sent) <= limit + SL.MULTIPART_OVERHEAD + CHUNK
    assert _asset_rows(conn, listing_id) == []
    assert store.list(f"listings/{listing_id}/") == []


async def test_a_streamed_upload_within_the_ceiling_is_accepted(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """The other arm of the bound: a chunked body that fits is a perfectly good upload."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await client.post(
        f"/api/seller/listings/{listing_id}/photos", content=_chunked(_multipart(_jpeg())),
        headers={**auth_headers(cookies, headers), "Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "front.jpg"


def test_an_asset_row_is_written_once_with_its_final_storage_key() -> None:
    """A-SL16 M1, as a drift guard. A placeholder `storage_key` holds an entry in a table-wide
    UNIQUE index for the length of the whole transaction — and that transaction contains a bucket
    PUT — so two sellers uploading to two DIFFERENT listings would block on each other for the
    duration of a network round trip."""
    from pathlib import Path

    from app.api import seller_listings as SL

    source = Path(SL.__file__).read_text()
    assert "UPDATE listing_asset SET storage_key" not in source
    # Info-1 (A-SL18 (5)): the second half of this guard used to be
    # `"storage_key)\n" not in source or "VALUES" in source` — the right operand is true of any
    # version of this module (it has other `VALUES` clauses), so the `or` made the whole assertion
    # a tautology that could never fail. This one actually names the shape M1 requires: the column
    # is closed and its `VALUES` clause opens on the SAME line, which is only true of a single
    # INSERT that carries the final key inline.
    assert "storage_key) VALUES" in source


async def test_a_storage_failure_on_upload_is_a_503_in_the_envelope_and_writes_no_row(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, monkeypatch: Any
) -> None:
    """A-SL16 M2. `app/storage.py` re-raises every ClientError that is not a 404, so a bucket
    outage, a rejected credential or a throttle used to leave an unhandled exception and FastAPI's
    `{"detail": "Internal Server Error"}` — not decision A5's envelope, and not the
    STORAGE_UNAVAILABLE code that describes exactly this."""
    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise ClientError({"Error": {"Code": "ServiceUnavailable", "Message": "no"}}, "PutObject")

    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    monkeypatch.setattr(ObjectStore, "put", _boom)

    for refused in (await _upload_photo(client, listing_id, signed),
                    await _upload_document(client, listing_id, signed)):
        assert refused.status_code == 503, refused.text
        assert refused.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert _asset_rows(conn, listing_id) == []


async def test_a_storage_failure_on_delete_keeps_the_row_and_refuses(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, monkeypatch: Any
) -> None:
    """A-SL16 M2's sharp end: the object goes FIRST, inside the transaction, so a delete that could
    not remove the object leaves the row exactly where it was. The alternative — the row gone and
    the object still there — answers 500 for work that was done and 404 on the retry."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_photo(client, listing_id, signed)).json()["id"]

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise ClientError({"Error": {"Code": "ServiceUnavailable", "Message": "no"}}, "DeleteObject")

    monkeypatch.setattr(ObjectStore, "delete", _boom)
    refused = await client.delete(f"/api/seller/listings/{listing_id}/assets/{asset_id}", headers=signed)
    assert refused.status_code == 503, refused.text
    assert refused.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert [str(row[0]) for row in _asset_rows(conn, listing_id)] == [asset_id]
    assert _photos(conn, listing_id) == [asset_id]


async def test_a_storage_failure_on_a_document_read_is_a_503_in_the_envelope(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, monkeypatch: Any
) -> None:
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_document(client, listing_id, signed)).json()["id"]

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise ClientError({"Error": {"Code": "ServiceUnavailable", "Message": "no"}}, "GetObject")

    monkeypatch.setattr(ObjectStore, "get", _boom)
    refused = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=signed)
    assert refused.status_code == 503, refused.text
    assert refused.json()["error"]["code"] == "STORAGE_UNAVAILABLE"


async def test_a_storage_failure_on_the_buyer_photo_route_is_a_404_not_a_500(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, monkeypatch: Any
) -> None:
    """`_asset_bytes`'s own docstring promises "every 'no' is the same None … never a 500"."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    await _upload_photo(client, listing_id, auth_headers(cookies, headers))
    _publish(conn, listing_id)
    _, buyer_cookies, buyer_headers = member(roles=("buyer",), email="sl4-buyer@example.org")

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise ClientError({"Error": {"Code": "ServiceUnavailable", "Message": "no"}}, "GetObject")

    monkeypatch.setattr(ObjectStore, "get", _boom)
    response = await client.get(f"/api/listings/{listing_id}/photos/1",
                                headers=auth_headers(buyer_cookies, buyer_headers))
    assert response.status_code == 404, response.text
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "No such photograph."}}


async def test_a_content_type_with_a_charset_parameter_is_accepted(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """A-SL16 L2: some clients send `text/csv; charset=utf-8`, and an exact comparison called it
    unsupported."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await _upload_document(client, listing_id, auth_headers(cookies, headers), CSV,
                                      filename="revenue.csv", content_type="text/csv; charset=utf-8")
    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == "text/csv"
    assert _asset_rows(conn, listing_id)[0][6].endswith(".csv")


async def test_a_windows_path_is_stripped_from_the_display_name(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """A-SL16 L4: display-only, but a local path has no business in the row or the payload."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    response = await _upload_document(client, listing_id, auth_headers(cookies, headers),
                                      filename=r"C:\Users\jane\Documents\accounts.pdf")
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "accounts.pdf"


async def test_a_spreadsheet_whose_bytes_are_not_a_zip_is_refused(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """A-SL16 L6: the XLSX arm of `_sniffed` had no negative case — not a coverage hole (one
    statement, no branch), which is exactly why the gate could not catch it."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    refused = await _upload_document(
        client, listing_id, auth_headers(cookies, headers), b"month,revenue\n", filename="equipment.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "BAD_DOCUMENT"


def test_the_store_fixture_only_ever_talks_to_a_host_moto_intercepts() -> None:
    """A-SL16 M4. The rule was prose in a docstring, and prose is enforced by nothing: moto 5
    matches the request URL, so a Railway-shaped endpoint escapes `mock_aws` and makes a real HTTPS
    call (it did, once). The fixture asserts through this function, and this proves it bites."""
    from tests.api.test_listing_assets import _intercepted_by_moto

    assert _intercepted_by_moto(ENDPOINT) is True
    with pytest.raises(AssertionError):
        _intercepted_by_moto("https://bucket.up.railway.app")


def test_no_test_in_the_suite_can_reach_a_real_non_local_host() -> None:
    """A-SL18 (5), review Info-4: `_intercepted_by_moto` above guards the `store` fixture's OWN
    endpoint alone — a test that repointed `settings.s3_*` after `store` yields, or built an
    `ObjectStore` directly, was unguarded. `tests/conftest.py::_no_stray_network` is session-scoped
    and autouse, so it is already active for every test in the suite without being asked for by
    name; this proves it actually bites, the same way the test above proves `_intercepted_by_moto`
    does."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock, pytest.raises(AssertionError):
        sock.connect(("example.com", 80))


@pytest.mark.parametrize(("disclosed", "status"), [
    (True, "published"), (False, "published"), (True, "draft"), (False, "draft"),
])
async def test_a_non_owner_member_cannot_read_a_document_however_disclosure_and_status_are_set(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, disclosed: bool, status: str
) -> None:
    """Major-1, A-SL18 (1). The round this pins replaces served `documents_disclosed` and
    `status = 'published'` as SUFFICIENT on their own — any signed-in member could then download a
    seller's financial packet the moment the seller turned off "Keep floor plans and financial
    packet locked" on a published listing, with no request and no accept. Spec D19 and §5's route
    table allow only the owner and staff (`listing.review`) until the requests sub-project adds the
    buyer-with-an-accepted-request arm, so a non-owner, non-staff member is refused exactly as it
    was refused before that branch existed — the same 403 `LOCKED` body
    `test_a_document_reads_to_its_owner_and_to_staff_and_to_nobody_else` pins for its own
    (undisclosed, draft) case, now proved across every combination of the two flags.

    `documents_disclosed` and `status` are still read off the row in `read_document` (as `_disclosed`
    and `_status`) so the requests sub-project's buyer arm has somewhere to AND them in — neither
    unlocks the document on its own."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    asset_id = (await _upload_document(client, listing_id, signed)).json()["id"]
    if status == "published":
        _publish(conn, listing_id)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET documents_disclosed = %s WHERE id = %s", (disclosed, listing_id))
    _, buyer_cookies, buyer_headers = member(roles=("buyer",), email="sl4-buyer@example.org")

    response = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}",
                                headers=auth_headers(buyer_cookies, buyer_headers))
    assert response.status_code == 403, response.text
    assert response.json() == {"error": {"code": "LOCKED", "message": "This document is locked until the seller approves access."}}
    assert (await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}",
                             headers=signed)).status_code == 200


async def test_the_seller_photo_arm_opens_one_connection(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, monkeypatch: Any
) -> None:
    """A-SL16 L8: the route used to close its first connection and open a second to resolve the
    asset, doubling the pool cost of the hottest read on the buyer surface."""
    from app.api import listings as L

    opened: list[int] = []
    original = L.sync_conn
    monkeypatch.setattr(L, "sync_conn", lambda: (opened.append(1), original())[1])

    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    await _upload_photo(client, listing_id, auth_headers(cookies, headers))
    _publish(conn, listing_id)
    _, buyer_cookies, buyer_headers = member(roles=("buyer",), email="sl4-buyer@example.org")
    opened.clear()

    response = await client.get(f"/api/listings/{listing_id}/photos/1",
                                headers=auth_headers(buyer_cookies, buyer_headers))
    assert response.status_code == 200
    assert len(opened) == 1


@pytest.mark.parametrize("content", ["{not json", '{"hospitals": {"a": [{"file": "1.webp"}]}}', '{"nope": {}}'])
def test_a_broken_photo_inventory_leaves_every_tile_named_by_its_file(tmp_path: Any, monkeypatch: Any, content: str) -> None:
    """A-SL16 L10: the docstring promises a fallback, and it only had one for a MISSING file — a
    malformed or restructured `index.json` raised `JSONDecodeError` or `KeyError` straight out of a
    draft read, which is a 500 on Edit."""
    from app.api import seller_listings as SL

    index = tmp_path / "index.json"
    index.write_text(content)
    monkeypatch.setattr(SL, "PHOTO_INDEX", index)
    assert SL.seed_captions.__wrapped__() == {}


@pytest.mark.parametrize(("route", "constant"), [("reorder", "LISTING_REORDER"), ("delete", "LISTING_DELETE")])
async def test_the_reorder_and_delete_rate_limits_are_per_account(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, monkeypatch: Any, route: str, constant: str
) -> None:
    """A-SL16 M3: two authenticated write routes had no ceiling at all, and `delete_asset` makes an
    unbounded number of bucket round trips."""
    from app.api import seller_listings as SL

    monkeypatch.setattr(SL, constant, (1, 3600))
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    first = (await _upload_photo(client, listing_id, signed)).json()["id"]
    second = (await _upload_photo(client, listing_id, signed)).json()["id"]

    async def _call(asset_id: str) -> Any:
        if route == "reorder":
            return await client.patch(f"/api/seller/listings/{listing_id}/photos",
                                      json={"ids": [first, second]}, headers=signed)
        return await client.delete(f"/api/seller/listings/{listing_id}/assets/{asset_id}", headers=signed)

    assert (await _call(first)).status_code in (200, 204)
    refused = await _call(second)
    assert refused.status_code == 429, refused.text
    assert refused.json()["error"]["code"] == "RATE_LIMITED"


# --- Controller amendment A-SL21: an asset write claims a seeded listing too ---------------------


def _owned_seed_listing(conn: Any, seller_id: Any, photos: list[str]) -> str:
    listing_id = _seed_listing(conn, photos)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET seller_id=%s WHERE id=%s", (seller_id, listing_id))
    return listing_id


def _reseed_source(conn: Any, listing_id: str) -> None:
    """Put the row back to `source='seed'` after a set-up write has claimed it, so the write under
    test is the FIRST one — the only way to prove that `delete_asset` claims the row itself rather
    than inheriting the claim its own fixture made."""
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET source='seed' WHERE id=%s", (listing_id,))


def _listing_source(conn: Any, listing_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT source FROM listing WHERE id=%s", (listing_id,))
        return str(cur.fetchone()[0])


@pytest.mark.parametrize("write", ["photo", "document", "reorder", "delete"])
async def test_an_asset_write_claims_a_seeded_listing_as_the_sellers_own(
    client: Any, conn: Any, redis: Any, member: Any, store: Any, write: str
) -> None:
    """A-SL21 for the four asset writes. A-SL15 (1) already made these edits; this is the other half
    of being an edit — the row stops being the seeder's the moment the seller changes a photograph
    or a document on it, so the next `scripts/seed_listings.py` run leaves it alone."""
    account_id, cookies, headers = _seller(member)
    photos = ["abc_animal_hospital/1.webp", "abc_animal_hospital/2.webp"]
    listing_id = _owned_seed_listing(conn, account_id, photos)
    signed = auth_headers(cookies, headers)

    if write == "photo":
        response = await _upload_photo(client, listing_id, signed)
        assert response.status_code == 201, response.text
    elif write == "document":
        response = await _upload_document(client, listing_id, signed)
        assert response.status_code == 201, response.text
    elif write == "reorder":
        response = await client.patch(f"/api/seller/listings/{listing_id}/photos",
                                      json={"ids": list(reversed(photos))}, headers=signed)
        assert response.status_code == 200, response.text
    else:
        uploaded = await _upload_photo(client, listing_id, signed)
        assert uploaded.status_code == 201, uploaded.text
        _reseed_source(conn, listing_id)
        assert _listing_source(conn, listing_id) == "seed"
        response = await client.delete(
            f"/api/seller/listings/{listing_id}/assets/{uploaded.json()['id']}", headers=signed)
        assert response.status_code == 204, response.text
    assert _listing_source(conn, listing_id) == "seller"
