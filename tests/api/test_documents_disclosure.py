"""GET /api/seller/listings/{id}/documents/{asset_id}'s buyer-with-an-accepted-request arm, and the
listing payload's real `documents` array (per-buyer disclosure plan Task 9, 2026-09-18; directive
§10, §12, §16, §19). `app/api/seller_listings.py::read_document`'s own prior comment named this
exact location as the arm `documents_disclosed`/`status` were read off the row and left unused for
-- this file proves it closed. `app/api/listings.py::_documents` (closing finding 9, the
wizard-step audit's own name for the buyer document list being 100% fixture data before this task)
is the minimum needed to make the byte route's own acceptance criterion reachable end to end through
the real API at all: an authorized buyer needs a real way to discover which asset ids exist before
"GET authorized documents" (directive §13) is testable through anything but a hand-picked id.

Every document is uploaded through the REAL multipart route (`tests.api.test_listing_assets`'s own
idiom, against the `store` fixture's moto bucket) while the listing is still a DRAFT --
`EDIT_REENTERS_REVIEW` (`app/api/seller_listings.py`) re-enters review on an edit to a
`published`/`paused` listing, so uploading AFTER publish would flip the listing back to `in_review`
and take it off the very route (`_published`, `status = 'published'` only) every test here reads
through -- and the listing is then moved straight to `published` by one direct SQL UPDATE,
`tests/api/test_requests.py::_seller_listing`'s own shape (the columns `migrations/030`'s
`listing_submittable_ck` and `034`'s `listing_publishable_ck` require once `status` leaves
`draft`/`withdrawn`), plus `documents_disclosed = true`, Task 9's own ceiling.

Two deviations from the plan's own literal Step 1 test sketch, found by reading the schema and the
route before writing a single line, not guessed once things failed:

1. `listing_asset`'s byte-count column is `byte_size` (`migrations/031_listing_asset.sql:24`), never
   `size_bytes` as the plan's own commented-out INSERT named it -- and that sketch's own comment
   already flagged itself as illustrative ("the real test file writes `_listing_with_a_financial_
   document` using a direct SQL insert as shown, rather than the commented-out multipart upload
   sketch above").
2. This file does not use a bare `INSERT INTO listing_asset` at all, for a reason the plan's own
   sketch could not have hit without running an APPROVED-grant case: `read_document`'s success path
   calls `_fetch(store, key)` against whatever object storage really holds at `key`, and a hand-typed
   `storage_key` naming an object nobody ever `PUT` would make even a correctly-authorized read
   answer 404 rather than 200 -- proved by writing the sketch's INSERT first and watching
   `test_an_approved_financials_grant_can_fetch_the_financial_document`'s own RED read "No such
   document" instead of a refusal, before switching to the real upload route below.

`documents_disclosed` (the listing's own ceiling, directive §8/§24) is left `true` throughout: that
flag's OWN gate is Task 8's territory, proved there: this file's job is the capability/grant
dimension `has_capability` adds beside it, so every fixture here opens the ceiling and only the
per-buyer grant varies.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.api.conftest import auth_headers
from tests.api.test_listings_disclosure import _approve

#: `%PDF-` is the whole of `_sniffed`'s own check for this content type (`app/api/seller_
#: listings.py::_sniffed`) -- `tests/api/test_listing_assets.py`'s own `PDF` constant, matched
#: rather than imported, since that module does not export it for reuse.
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"


async def _listing_with_documents(
    conn: Any, client: Any, seller_headers: dict[str, str], *, kinds: tuple[str, ...] = ("financials",),
) -> tuple[str, list[str]]:
    """A published, `documents_disclosed = true` listing owned by whoever `seller_headers` signs in
    as, carrying one REAL uploaded document per entry in `kinds` (module docstring: why the upload
    happens before the SQL publish, and why publish is one direct UPDATE rather than the real submit
    /decide flow -- this file is about document authorization, not the review lifecycle Task 11
    already owns end to end).

    Returns `(listing_id, asset_ids)`, `asset_ids` parallel to `kinds` positionally."""
    listing = await client.post("/api/seller/listings", headers=seller_headers)
    assert listing.status_code == 201, listing.text
    listing_id = listing.json()["id"]
    asset_ids = []
    for i, kind in enumerate(kinds):
        uploaded = await client.post(
            f"/api/seller/listings/{listing_id}/documents", headers=seller_headers,
            files={"file": (f"doc-{i}.pdf", PDF, "application/pdf")}, data={"kind": kind},
        )
        assert uploaded.status_code == 201, uploaded.text
        asset_ids.append(uploaded.json()["id"])
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing SET status = 'published', documents_disclosed = true, name = 'Test Practice',"
            " city = 'Austin', state = 'TX', zip = '78701', area = 'Austin', market = 'Austin, TX',"
            " type = 'Small animal', est = 2010, price = 1000000, sqft = 3000 WHERE id = %s",
            (listing_id,),
        )
    return listing_id, asset_ids


# --- `read_document`: owner/staff unchanged, everyone else refused, even by the exact id ----------


@pytest.mark.asyncio
async def test_the_owner_and_staff_arms_are_unchanged_and_everyone_else_is_refused(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """Owner and staff, exactly as before this task; an anonymous caller refused; and a SIGNED-IN
    buyer with no grant refused even asking by the document's OWN, correct asset id -- never a
    guessed one. Directive §10's "knowing the URL must not be enough": the bytes route is the door
    that matters, so this proves the DOOR itself refuses a buyer who knows precisely which id
    exists, rather than merely that some OTHER list omits it."""
    _sid, s_cookies, s_hdr = member(("seller",), email="d1-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, (asset_id,) = await _listing_with_documents(conn, client, seller_headers)
    path = f"/api/seller/listings/{listing_id}/documents/{asset_id}"

    _tid, t_cookies, t_hdr = member(("staff",), email="d1-staff@x.org")
    _bid, b_cookies, b_hdr = member(("buyer",), email="d1-buyer@x.org")

    owner = await client.get(path, headers=seller_headers)
    staff = await client.get(path, headers=auth_headers(t_cookies, t_hdr))
    unapproved = await client.get(path, headers=auth_headers(b_cookies, b_hdr))
    anonymous = await client.get(path, headers={"Origin": "https://qa.foundation.vin"})

    assert owner.status_code == 200 and owner.content == PDF
    assert staff.status_code == 200 and staff.content == PDF
    assert unapproved.status_code == 403
    assert unapproved.json() == {
        "error": {"code": "LOCKED", "message": "This document is locked until the seller approves access."}
    }
    assert anonymous.status_code == 401
    assert anonymous.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}


@pytest.mark.asyncio
async def test_an_approved_financials_grant_can_fetch_the_financial_document(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="d2-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, (asset_id,) = await _listing_with_documents(conn, client, seller_headers, kinds=("financials",))
    _bid, b_cookies, b_hdr = member(("buyer",), email="d2-buyer@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_id, level="FINANCIALS")

    response = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=buyer_headers)
    assert response.status_code == 200
    assert response.content == PDF


@pytest.mark.asyncio
async def test_a_floor_plans_grant_does_not_unlock_a_financial_document(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """Directive §16: each capability follows its OWN name. `FLOOR_PLANS` and `FINANCIALS` are
    SIBLING capabilities -- neither is broader than the other -- so this is a stronger proof than an
    unrelated capability (say, `IDENTITY`) would be: the two a seller is likeliest to confuse."""
    _sid, s_cookies, s_hdr = member(("seller",), email="d3-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, (asset_id,) = await _listing_with_documents(conn, client, seller_headers, kinds=("financials",))
    _bid, b_cookies, b_hdr = member(("buyer",), email="d3-buyer@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_id, level="FLOOR_PLANS")

    response = await client.get(f"/api/seller/listings/{listing_id}/documents/{asset_id}", headers=buyer_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOCKED"


@pytest.mark.asyncio
async def test_buyer_a_approved_and_buyer_b_unapproved_diverge_on_the_same_document_at_once(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """Directive §7's own critical security test, applied to the document bytes route specifically
    -- Task 11 owns the general acceptance matrix end to end; this is the document surface's own
    proof that two buyers reading the SAME asset in the SAME test run do not agree."""
    _sid, s_cookies, s_hdr = member(("seller",), email="d4-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, (asset_id,) = await _listing_with_documents(conn, client, seller_headers)
    _aid, a_cookies, a_hdr = member(("buyer",), email="d4-a@x.org")
    a_headers = auth_headers(a_cookies, a_hdr)
    _bid, b_cookies, b_hdr = member(("buyer",), email="d4-b@x.org")
    b_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, a_headers, listing_id, level="FINANCIALS")

    path = f"/api/seller/listings/{listing_id}/documents/{asset_id}"
    a_response = await client.get(path, headers=a_headers)
    b_response = await client.get(path, headers=b_headers)
    assert a_response.status_code == 200 and a_response.content == PDF
    assert b_response.status_code == 403


@pytest.mark.asyncio
async def test_after_revocation_the_document_is_refused_again(client: Any, conn: Any, member: Any, store: Any) -> None:
    """Directive §15: revocation is IMMEDIATE, through the SAME protected route the grant unlocked
    -- no session refresh, no separate flag to clear."""
    _sid, s_cookies, s_hdr = member(("seller",), email="d5-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, (asset_id,) = await _listing_with_documents(conn, client, seller_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="d5-buyer@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    request_id = await _approve(client, seller_headers, buyer_headers, listing_id, level="FINANCIALS")

    path = f"/api/seller/listings/{listing_id}/documents/{asset_id}"
    granted = await client.get(path, headers=buyer_headers)
    assert granted.status_code == 200

    revoked = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    assert revoked.status_code == 200, revoked.text
    after = await client.get(path, headers=buyer_headers)
    assert after.status_code == 403
    assert after.json()["error"]["code"] == "LOCKED"


# --- the listing payload's real `documents` array --------------------------------------------------


@pytest.mark.asyncio
async def test_an_unapproved_buyer_sees_the_titles_and_cannot_fetch_them(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """Finding 9 closed for real: the array is the listing's OWN documents, not fixture data.

    The titles are VISIBLE to a buyer with no grant, and that is the product's promise rather than a
    leak -- step 7's approved copy, which directive §17 declares correct, reads "Buyers see the
    document titles and can ask for access." A buyer cannot request access to a document they cannot
    see exists, so a filtered list would leave the request flow this subsystem exists to serve with
    nothing to point at (controller ruling, 2026-09-19, correcting this task's own brief).

    What the grant gates is the BYTES, proved here in the same test: the titles list, and every one
    of them refuses to open."""
    _sid, s_cookies, s_hdr = member(("seller",), email="d6-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, _asset_ids = await _listing_with_documents(conn, client, seller_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="d6-buyer@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert [d["name"] for d in body["documents"]], "the titles must be visible so a buyer can ask"
    # ...and not one of them opens without a grant.
    for doc in body["documents"]:
        refused = await client.get(
            f"/api/seller/listings/{listing_id}/documents/{doc['id']}", headers=buyer_headers)
        assert refused.status_code in (403, 404), refused.text


@pytest.mark.asyncio
async def test_a_fully_approved_buyer_on_a_listing_with_no_documents_gets_an_empty_array(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """The ceiling open, the broadest possible grant, and NOTHING to list -- `_documents`'s own
    query returns zero rows and the filter has nothing to iterate, which must still answer `[]`
    rather than `None` or a crash."""
    _sid, s_cookies, s_hdr = member(("seller",), email="d6b-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, asset_ids = await _listing_with_documents(conn, client, seller_headers, kinds=())
    assert asset_ids == []
    _bid, b_cookies, b_hdr = member(("buyer",), email="d6b-buyer@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_id, level="FULL_CONFIDENTIAL")

    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["documents"] == []


@pytest.mark.asyncio
async def test_the_documents_array_shows_a_buyer_only_what_their_grant_covers(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """Two documents of two DIFFERENT kinds and a grant covering only one of them.

    The LIST shows both -- existence is public once the seller opens the ceiling -- while the ROUTE
    opens exactly one. That split is the point: a buyer learns a financial packet exists so they can
    ask for it, and still cannot read it until the seller says yes."""
    _sid, s_cookies, s_hdr = member(("seller",), email="d7-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, (financial_id, floor_plan_id) = await _listing_with_documents(
        conn, client, seller_headers, kinds=("financials", "floor_plan"))
    _bid, b_cookies, b_hdr = member(("buyer",), email="d7-buyer@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await _approve(client, seller_headers, buyer_headers, listing_id, level="FLOOR_PLANS")

    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    # BOTH are listed: the buyer must be able to see the financial packet exists to request it.
    assert {d["id"] for d in body["documents"]} == {floor_plan_id, financial_id}
    assert {d["kind"] for d in body["documents"]} == {"floor_plan", "financials"}

    # And what the ROUTE would actually do agrees with what the LIST just promised (the two must
    # never diverge, which is the whole reason this list exists rather than staying fixture data):
    # the listed document opens, and the one the list withheld still refuses.
    floor_plan_read = await client.get(
        f"/api/seller/listings/{listing_id}/documents/{floor_plan_id}", headers=buyer_headers)
    financial_read = await client.get(
        f"/api/seller/listings/{listing_id}/documents/{financial_id}", headers=buyer_headers)
    assert floor_plan_read.status_code == 200
    assert financial_read.status_code == 403
