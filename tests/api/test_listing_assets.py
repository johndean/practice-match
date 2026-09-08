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
from typing import Any
from uuid import uuid4

import boto3
import pytest
from moto import mock_aws
from PIL import Image

from app.config import settings
from app.storage import ObjectStore
from tests.api.conftest import auth_headers

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


@pytest.fixture
def store(monkeypatch: Any) -> Any:
    """A moto bucket, reached through the real `ObjectStore.from_settings`."""
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        for name, value in (("s3_endpoint_url", ENDPOINT), ("s3_bucket", BUCKET),
                            ("s3_access_key_id", "AKIA"), ("s3_secret_access_key", "secret")):
            monkeypatch.setattr(settings, name, value)
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


def _seed_listing(conn: Any, photos: list[str]) -> str:
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


async def test_the_fifth_photograph_is_refused_with_the_photo_limit_code(client: Any, conn: Any, redis: Any, member: Any, store: Any) -> None:
    """John's ruling, restated in D18: "Keep the existing 4-photo seller-upload cap." Nothing is
    orphaned by the refusal — the fifth object is never written."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    for _ in range(4):
        assert (await _upload_photo(client, listing_id, signed)).status_code == 201

    refused = await _upload_photo(client, listing_id, signed)
    assert refused.status_code == 409
    assert refused.json() == {"error": {"code": "PHOTO_LIMIT", "message": "A listing may carry 4 photographs."}}
    assert len(_photos(conn, listing_id)) == 4
    assert len(_asset_rows(conn, listing_id)) == 4
    assert len(store.list(f"listings/{listing_id}/photos/")) == 4


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
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """D16, four writers. `session:*` is left alone — the drop is a prefix scan, not a flush."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)

    def _plant() -> None:
        redis.set("listings:v1:Austin, TX::50", b"stale")
        redis.set("session:keep", b"kept")

    _plant()
    photo = (await _upload_photo(client, listing_id, signed)).json()["id"]
    assert redis.get("listings:v1:Austin, TX::50") is None
    assert redis.get("session:keep") == b"kept"

    _plant()
    assert (await _upload_document(client, listing_id, signed)).status_code == 201
    assert redis.get("listings:v1:Austin, TX::50") is None

    _plant()
    assert (await client.patch(f"/api/seller/listings/{listing_id}/photos", json={"ids": [photo]},
                               headers=signed)).status_code == 200
    assert redis.get("listings:v1:Austin, TX::50") is None

    _plant()
    assert (await client.delete(f"/api/seller/listings/{listing_id}/assets/{photo}", headers=signed)).status_code == 204
    assert redis.get("listings:v1:Austin, TX::50") is None
    assert redis.get("session:keep") == b"kept"


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
    assert response.json() == {"error": {"code": "BAD_REQUEST", "message": "Body must be JSON."}}


async def test_the_draft_read_carries_its_photographs_in_order_and_its_documents(
    client: Any, conn: Any, redis: Any, member: Any, store: Any
) -> None:
    """D26: step 6's tiles are `listing.photos`' own order, named by the uploaded filename, and the
    documents come back with the route that reads them back. `assets` is unchanged (SL3's contract);
    these two are the ordered views of it the wizard renders."""
    _, cookies, headers = _seller(member)
    listing_id = await _create(client, cookies, headers)
    signed = auth_headers(cookies, headers)
    first = (await _upload_photo(client, listing_id, signed, filename="front.jpg")).json()["id"]
    second = (await _upload_photo(client, listing_id, signed, filename="waiting-room.jpg")).json()["id"]
    document = (await _upload_document(client, listing_id, signed, filename="accounts.pdf")).json()["id"]
    assert (await client.patch(f"/api/seller/listings/{listing_id}/photos",
                               json={"ids": [second, first]}, headers=signed)).status_code == 200

    body = (await client.get(f"/api/seller/listings/{listing_id}", headers=signed)).json()
    assert body["photos"] == [{"id": second, "name": "waiting-room.jpg"},
                              {"id": first, "name": "front.jpg"}]
    assert body["documents"] == [{"id": document, "kind": "other", "name": "accounts.pdf",
                                  "content_type": "application/pdf", "byte_size": len(PDF),
                                  "url": f"/api/seller/listings/{listing_id}/documents/{document}"}]
    assert [asset["id"] for asset in body["assets"]] == [first, second, document]


async def test_a_seed_listings_tiles_are_named_by_the_seed_caption(client: Any, conn: Any, redis: Any, member: Any) -> None:
    """The other arm of D26's "the seed caption or the uploaded filename". A seed row belongs to
    the demo seller on QA (D25), so Edit on one reads through this serialiser too — and its
    `listing.photos` entries are relative paths that name no `listing_asset` row."""
    account_id, cookies, headers = _seller(member)
    listing_id = _seed_listing(conn, ["1111_pet_hospital/1.webp", "1111_pet_hospital/nope.webp"])
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET seller_id=%s WHERE id=%s", (account_id, listing_id))

    body = (await client.get(f"/api/seller/listings/{listing_id}", headers=auth_headers(cookies, headers))).json()
    assert body["photos"] == [{"id": "1111_pet_hospital/1.webp", "name": "Exterior — front view"},
                              {"id": "1111_pet_hospital/nope.webp", "name": "nope.webp"}]
    assert body["documents"] == []


def test_the_seed_captions_are_read_from_the_committed_index() -> None:
    from app.api import seller_listings as SL

    captions = SL.seed_captions()
    assert captions["1111_pet_hospital/1.webp"] == "Exterior — front view"
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
        await client.delete(f"/api/seller/listings/not-a-uuid/assets/{uuid4()}", headers=signed),
    ):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "NOT_FOUND"
