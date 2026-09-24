# tests/api/test_disclosure_isolation.py
"""directive §7, verbatim: "Create two test buyer accounts: BUYER A, BUYER B. Seller approves
BUYER A. Expected: BUYER A receives the approved confidential information; BUYER B continues
receiving the redacted/public information. This test MUST pass." Exercised over the SAME three
surfaces the directive names -- the listing detail (name/location/revenue), the photograph variant
(unredacted images) and the document route (financial packet) -- because "the confidential
information" is not one field, and a fix that only closed one surface would still fail this test's
own spirit even while passing a narrower version of it. Per-buyer disclosure plan Task 11.

And the case most likely to be got wrong (this task's own brief): a test that only checks B's OWN
responses has not tested an attacker. `test_buyer_b_is_refused_even_holding_buyer_as_own_identifiers`
hands B three things Buyer A actually holds -- A's request id, A's document asset id and the
document's own storage key, read straight out of the database, never a value this file invents --
and proves knowing them changes nothing about what B is authorized to do.

Two corrections to the plan's own literal Step 1 fixture, each found by reading the CURRENT
implementation (both landed in this branch on 2026-09-19, the day this task was written) before
writing a single assertion, never discovered by a false pass:

1. **The public tier is not `None` for location** -- **SUPERSEDED BY RULING D-C66 (John,
   2026-09-24), and kept here because what replaced it is the reason this file's fixture moved.**
   As written on 2026-09-19 this read: `app/api/listings.py::_point`'s own docstring, "Ceiling, no
   grant -> rounded to 2 decimal places ... a coarser approximate map representation", so a
   published listing with `location_disclosed = true` and no grant served a ROUNDED point rather
   than a null one, and every location assertion below read that rounded value back from the exact
   one the response had already returned.

   D-C66 makes the ceiling the PUBLIC DEFAULT rather than a second lock: *ceiling OR grant*. That
   retires the rounded tier (an open ceiling now publishes the street itself, so a pin 1.1 km from
   it would be one question answered twice) and, much more to the point for THIS file, it means an
   open ceiling is no longer a confidential state at all. `_seller_listing_with_everything_
   confidential` therefore sets all four ceilings SHUT, which is what its own name has always
   claimed and what §7 requires to mean anything: on a ceiling-open listing Buyer B is not
   "redacted", they are a member of the public the seller published to on purpose. Buyer B's point
   below is consequently `None` rather than a rounded pair -- a sharper divergence than before, not
   a weaker one.
2. **`identifiable_content_visibility` must be `NOT_SHOW`, not `SHOW`, for the photo surface to
   prove anything.** `app/privacy/delivery.py::buyer_variant`'s own test names it directly:
   "SHOW discloses the display derivative regardless of authorization." Under the global SHOW
   switch every signed-in buyer already receives the identical display derivative whether or not
   they hold a personal grant -- a photo check against a SHOW listing would pass trivially with or
   without per-buyer image authorization ever having been built, which is exactly "a test that
   passes the moment you write it" this task's own brief warns against. `NOT_SHOW` -- the safe
   DEFAULT every new listing already carries (Task P11, A20) -- is the one state where
   UNREDACTED_IMAGES is a real, load-bearing per-buyer grant rather than a global switch every
   buyer already clears.

And one behaviour this file deliberately does NOT test as a defect, because it is a ruled, correct
one: `_documents`'s own docstring (controller ruling, 2026-09-19, correcting Task 9's own brief) --
a document's TITLE is public to every buyer ("Buyers see the document titles and can ask for
access", step 7's approved copy, directive §17), and only the BYTES route is gated on the per-buyer
grant. Under D-C66 that is true whether the seller has locked the documents or not: the ceiling
used to suppress the whole list, which left a buyer with nothing to ask about on exactly the
listings where asking is the point. Buyer B is therefore expected to
see the financial document's title in `documents` throughout this test -- asserting otherwise would
be asserting a regression against the ruling, not a security property.

Task 12 (directive §21, the full acceptance matrix) is appended below, in this same file, per the
plan's own reasoning for keeping Tasks 11-13 together: they share the same fixtures. The matrix
test drives every row of the directive's own five-row table as a CONTINUOUS story on ONE listing
and ONE buyer pair -- never five independent fixtures, which is what the plan's own literal Step 1
parametrized cases would have been, and which cannot catch a defect that only shows up ACROSS a
transition. The three extra rows directive §21 names beyond the table -- an unauthenticated caller,
a partial grant, and a seller managing their own listing -- follow as their own tests below it.

Task 13 (directive §22, IDOR) is a SEPARATE file, `tests/api/test_disclosure_idor.py`, importing
`_seller_listing_with_everything_confidential` from here rather than declaring a second copy of it.
One of directive §22's four named attacks, Buyer A reading Buyer B's access record, is deliberately
NOT re-tested there: `test_buyer_b_is_refused_even_holding_buyer_as_own_identifiers` above already
proves it in both directions (B guessing A's request id and the reverse), plus the storage-key and
document-id angles -- repeating it would be the exact duplication this task's own brief warns
against."""
from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

import pytest

from app.privacy import record
from tests.api.conftest import auth_headers
from tests.api.test_buyer_photo_delivery import _process, _upload

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"

#: The exact (lng, lat) pair `_seller_listing_with_everything_confidential` geocodes the fixture
#: to -- Dallas, matching this branch's own Highland Park Veterinary story elsewhere in the plan.
#: Four decimal places on each axis, so `round(x, 2)` visibly differs from the exact value (directive
#: §11's own distinction between the two tiers), rather than a coincidence of the coordinates chosen.
_LNG, _LAT = -96.8067, 32.8140


async def _seller_listing_with_everything_confidential(
    conn: Any, client: Any, store: Any, seller_headers: dict[str, str],
) -> tuple[str, str, str]:
    """A published listing with every confidential surface this branch built reachable at once: a
    real name/address/point/revenue, one real, PIPELINE-PROCESSED photograph under `NOT_SHOW`
    (module docstring, deviation 2), and one real uploaded financial document. Returns
    `(listing_id, photo_asset_id, document_asset_id)`.

    Uploads happen WHILE THE LISTING IS STILL A DRAFT and the listing is moved to `published` in
    ONE direct SQL statement LAST -- `tests/api/test_documents_disclosure.py`'s own module
    docstring names the trap this order avoids: `EDIT_REENTERS_REVIEW`
    (`app/api/seller_listings.py`) re-enters review on an edit to an already-`published`/`paused`
    listing, so uploading a photo or a document AFTER publish would silently flip `status` back to
    `in_review` and take the listing off the one route (`_published`, `status = 'published'` only)
    every read in this file goes through. `_published_seller_listing`
    (`tests/api/test_listings_disclosure.py`) publishes FIRST and cannot be reused here for exactly
    this reason; its own required-column list (`type`/`market`/`area`/`sqft`, found there by
    running the plan's own draft into `listing_submittable_ck`/`listing_publishable_ck`) is reused
    below rather than re-derived."""
    listing = await client.post("/api/seller/listings", headers=seller_headers)
    assert listing.status_code == 201, listing.text
    listing_id = listing.json()["id"]

    photo_asset_id = await _upload(client, listing_id, seller_headers)
    _process(conn, store, listing_id, photo_asset_id, status="SELLER_CONFIRMED")

    upload = await client.post(
        f"/api/seller/listings/{listing_id}/documents", headers=seller_headers,
        files={"file": ("packet.pdf", PDF, "application/pdf")}, data={"kind": "financials"},
    )
    assert upload.status_code == 201, upload.text
    document_asset_id = upload.json()["id"]

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing SET status = 'published', name = 'Highland Park Veterinary',"
            " city = 'Dallas', state = 'TX', zip = '75205', street = '4200 Preston Rd',"
            " phone = '2145551234', est = 2005, price = 2000000, rev = 900000, sqft = 4000,"
            " type = 'Small animal', market = 'Dallas, TX', area = 'Dallas',"
            # D-C66 (2026-09-24): all four ceilings SHUT, which is what "everything confidential"
            # means once an OPEN ceiling is a publication. `documents_disclosed` is now read by
            # nothing on either document surface -- the titles list whatever it says and the bytes
            # need a capability-matched grant whatever it says -- and is set false here for the
            # same reason as its three siblings: this fixture is the confidential listing.
            " location_disclosed = false, name_disclosed = false, rev_disclosed = false,"
            " documents_disclosed = false, identifiable_content_visibility = 'NOT_SHOW',"
            " geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography"
            " WHERE id = %s",
            (_LNG, _LAT, listing_id),
        )
    return listing_id, photo_asset_id, document_asset_id


def _privacy_row_of(conn: Any, listing_id: str) -> Any:
    """The one photograph's `PrivacyRow` -- `tests/api/test_buyer_photo_delivery.py::_privacy_of`'s
    own shape, not imported directly because that helper is private to a module this file already
    imports two OTHER names from and duplicating a four-line query reads more plainly here than a
    third cross-module import would."""
    with conn.cursor() as cur:
        cur.execute("SELECT photos ->> 0 FROM listing WHERE id = %s", (listing_id,))
        entry = cur.fetchone()[0]
    return record.read(conn, UUID(entry))


@pytest.mark.asyncio
async def test_buyer_a_approved_buyer_b_is_not_receives_the_confidential_information_only_a_gets(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """The literal reproduction of directive §7. Every assertion checks the RESPONSE BODY (or a
    real object-store byte comparison), never a status code alone, and every "must not see X"
    assertion is `is None`/an exact non-match against the real confidential value -- never
    `"X" not in body`, which a differently-shaped leak could still slip past."""
    _sid, s_cookies, s_hdr = member(("seller",), email="dallas-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, _photo_asset_id, document_asset_id = await _seller_listing_with_everything_confidential(
        conn, client, store, seller_headers
    )
    privacy_row = _privacy_row_of(conn, listing_id)

    _aid, a_cookies, a_hdr = member(("buyer",), email="buyer-a@x.org")
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-b@x.org")
    a_headers, b_headers = auth_headers(a_cookies, a_hdr), auth_headers(b_cookies, b_hdr)

    # BEFORE any decision, both buyers see the SAME public/redacted listing -- the baseline the
    # rest of this test's isolation claims are measured against.
    before_a = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    before_b = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert before_a["name"] != "Highland Park Veterinary"
    assert before_b["name"] != "Highland Park Veterinary"
    assert before_a["street"] is None and before_b["street"] is None
    assert before_a["rev"] is None and before_b["rev"] is None
    # D-C66 (deviation 1 above): the ceiling is SHUT, so the public tier has no point at all --
    # and both buyers already agree on that before either is granted anything.
    assert (before_a["lat"], before_a["lng"]) == (None, None)
    assert (before_a["lat"], before_a["lng"]) == (before_b["lat"], before_b["lng"])

    request_a = await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})
    request_b = await client.post("/api/requests", headers=b_headers, json={"listing_id": listing_id})
    assert request_a.status_code == 201, request_a.text
    assert request_b.status_code == 201, request_b.text

    # SELLER APPROVES BUYER A ONLY. Buyer B's own request is left PENDING, never decided.
    approve = await client.post(
        f"/api/seller/requests/{request_a.json()['id']}/decide", headers=seller_headers, json={"action": "approve"}
    )
    assert approve.status_code == 200 and approve.json()["status"] == "APPROVED"

    # BUYER A receives the approved confidential information -- every surface directive §7 names.
    after_a = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    assert after_a["name"] == "Highland Park Veterinary"
    assert after_a["street"] == "4200 Preston Rd"
    assert after_a["zip"] == "75205"
    assert after_a["phone"] == "2145551234"
    assert after_a["rev"] == 900000
    assert after_a["lat"] == _LAT and after_a["lng"] == _LNG, "Buyer A must receive the EXACT point, not the coarsened one"

    photo_a = await client.get(f"/api/listings/{listing_id}/photos/1", headers=a_headers)
    assert photo_a.status_code == 200
    assert hashlib.sha256(photo_a.content).hexdigest() == privacy_row.display_sha256, (
        "Buyer A must receive the DISPLAY (unredacted) derivative"
    )

    document_a = await client.get(f"/api/seller/listings/{listing_id}/documents/{document_asset_id}", headers=a_headers)
    assert document_a.status_code == 200
    assert document_a.content == PDF
    assert any(d["id"] == document_asset_id for d in after_a["documents"])

    # BUYER B -- request B is still PENDING -- continues receiving the redacted/public information
    # on every one of the same surfaces.
    after_b = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert after_b["name"] != "Highland Park Veterinary", "BUYER B must not see the real name after BUYER A alone is approved"
    assert after_b["street"] is None, "BUYER B must not see the exact address after BUYER A alone is approved"
    assert after_b["zip"] is None
    assert after_b["phone"] is None
    assert after_b["rev"] is None, "BUYER B must not see the exact revenue after BUYER A alone is approved"
    # No point at all on a shut ceiling (D-C66; it was the coarsened pair until 2026-09-24) -- and
    # whatever it is, it must NOT equal Buyer A's exact one.
    assert (after_b["lat"], after_b["lng"]) == (None, None)
    assert (after_b["lat"], after_b["lng"]) != (after_a["lat"], after_a["lng"])

    # The document's TITLE is public (module docstring) -- B seeing it is the ruled behaviour, not
    # a leak, and under D-C66 it is public whether the seller locked the documents or not, because
    # a buyer cannot ask for access to a document they cannot see exists. The BYTES are what must
    # stay locked.
    assert any(d["id"] == document_asset_id for d in after_b["documents"]), (
        "the document's existence is public to every buyer, locked listing or not"
    )
    document_b = await client.get(f"/api/seller/listings/{listing_id}/documents/{document_asset_id}", headers=b_headers)
    assert document_b.status_code == 403, "BUYER B must not be able to fetch the financial document after BUYER A alone is approved"
    assert document_b.json() == {
        "error": {"code": "LOCKED", "message": "This document is locked until the seller approves access."}
    }

    photo_b = await client.get(f"/api/listings/{listing_id}/photos/1", headers=b_headers)
    assert photo_b.status_code == 200
    assert hashlib.sha256(photo_b.content).hexdigest() == privacy_row.redacted_sha256, (
        "BUYER B must receive the REDACTED derivative after BUYER A alone is approved"
    )
    assert photo_b.content != photo_a.content

    # SELLER REVOKES BUYER A -- directive §15: A must IMMEDIATELY lose every one of the same
    # surfaces, through the same protected routes, no session refresh and no separate flag to clear.
    revoke = await client.post(f"/api/seller/requests/{request_a.json()['id']}/revoke", headers=seller_headers)
    assert revoke.status_code == 200 and revoke.json()["status"] == "REVOKED"

    after_revoke = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    assert after_revoke["name"] != "Highland Park Veterinary", "BUYER A must lose access immediately on revoke"
    assert after_revoke["street"] is None
    assert after_revoke["rev"] is None
    assert (after_revoke["lat"], after_revoke["lng"]) == (None, None)

    photo_a_after_revoke = await client.get(f"/api/listings/{listing_id}/photos/1", headers=a_headers)
    assert hashlib.sha256(photo_a_after_revoke.content).hexdigest() == privacy_row.redacted_sha256

    document_a_after_revoke = await client.get(
        f"/api/seller/listings/{listing_id}/documents/{document_asset_id}", headers=a_headers
    )
    assert document_a_after_revoke.status_code == 403
    assert document_a_after_revoke.json()["error"]["code"] == "LOCKED"


@pytest.mark.asyncio
async def test_buyer_b_is_refused_even_holding_buyer_as_own_identifiers(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """directive §22's IDOR discipline, exercised INSIDE the two-buyer story (rather than deferred
    whole to Task 13's own file, out of this task's own scope): this task's brief, verbatim, "a
    test that only checks B's own responses has not tested an attacker." B is handed three things
    Buyer A actually holds: A's own request id, A's own document asset id (already public by
    title -- the point is that KNOWING it changes nothing about B's OWN authorization) and the
    document's own storage key, read straight out of the database, never a value this file
    invents."""
    _sid, s_cookies, s_hdr = member(("seller",), email="idor11-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, _photo_asset_id, document_asset_id = await _seller_listing_with_everything_confidential(
        conn, client, store, seller_headers
    )
    _aid, a_cookies, a_hdr = member(("buyer",), email="idor11-a@x.org")
    _bid, b_cookies, b_hdr = member(("buyer",), email="idor11-b@x.org")
    a_headers, b_headers = auth_headers(a_cookies, a_hdr), auth_headers(b_cookies, b_hdr)

    request_a = await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})
    assert request_a.status_code == 201, request_a.text
    request_a_id = request_a.json()["id"]
    approve = await client.post(
        f"/api/seller/requests/{request_a_id}/decide", headers=seller_headers, json={"action": "approve"}
    )
    assert approve.status_code == 200, approve.text

    # B GUESSES A's REQUEST ID: never confirmed to exist, and never distinguished by status code
    # from one that is not there at all (directive §22 -- `app/disclosure/requests.py::get_one`'s
    # own rule, "a request that is not yours is 404, never a 403 that would confirm something is
    # there").
    guessed_request = await client.get(f"/api/requests/{request_a_id}", headers=b_headers)
    assert guessed_request.status_code == 404
    assert guessed_request.json() == {"error": {"code": "NOT_FOUND", "message": "No such request."}}

    # B GUESSES A's DOCUMENT ASSET ID: not a secret at all (the title is public once the ceiling is
    # open, module docstring) -- the point is that HOLDING it does not change B's own refusal.
    guessed_document = await client.get(
        f"/api/seller/listings/{listing_id}/documents/{document_asset_id}", headers=b_headers
    )
    assert guessed_document.status_code == 403
    assert guessed_document.json() == {
        "error": {"code": "LOCKED", "message": "This document is locked until the seller approves access."}
    }

    # B GUESSES THE STORAGE KEY: the one identifier this system never discloses to ANY buyer, A
    # included (directive §9/§20, "do not expose the original storage path"). Read here straight
    # from the database -- never a value this test invented -- and proved absent from every
    # response body either buyer can see, A's own successful fetch included.
    with conn.cursor() as cur:
        cur.execute("SELECT storage_key FROM listing_asset WHERE id = %s", (document_asset_id,))
        storage_key = cur.fetchone()[0]
    assert storage_key, "the fixture's own document must have a real storage key to guess"
    document_a = await client.get(f"/api/seller/listings/{listing_id}/documents/{document_asset_id}", headers=a_headers)
    assert document_a.status_code == 200
    for label, response in (
        ("B's refused document fetch", guessed_document),
        ("A's OWN successful document fetch", document_a),
        ("A's listing detail", await client.get(f"/api/listings/{listing_id}", headers=a_headers)),
        ("B's listing detail", await client.get(f"/api/listings/{listing_id}", headers=b_headers)),
    ):
        assert storage_key not in response.text, f"the storage key {storage_key!r} leaked into {label}"

    # And the reverse direction, so the isolation is not a one-way accident of who requested first:
    # B's own (still-pending) request is equally invisible to A.
    request_b = await client.post("/api/requests", headers=b_headers, json={"listing_id": listing_id})
    assert request_b.status_code == 201, request_b.text
    guessed_by_a = await client.get(f"/api/requests/{request_b.json()['id']}", headers=a_headers)
    assert guessed_by_a.status_code == 404
    assert guessed_by_a.json() == {"error": {"code": "NOT_FOUND", "message": "No such request."}}


# --- Task 12: the full acceptance matrix (directive §21) ------------------------------------------


@pytest.mark.asyncio
async def test_the_full_acceptance_matrix_as_state_transitions_on_one_listing_and_one_buyer_pair(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """directive §21's own table, driven literally as a sequence of STATE TRANSITIONS on ONE
    listing and ONE buyer pair -- never as five independent fixtures. The plan's own literal Step 1
    reached for `@pytest.mark.parametrize` with a fresh `member(...)` pair per row, which is five
    unrelated tests wearing one table's clothes and cannot catch a defect that only shows up ACROSS
    a transition: a revoke that half-clears something, a capability set cached from an earlier
    read, a second row an UPDATE forgot to touch. The row order below is chosen so each
    precondition is the previous row's postcondition, which is what makes it one continuous story
    rather than five:

        No approval -> A approved -> A revoked -> B approved -> Both approved

    "A revoked" and "No approval" both read REDACTED for buyer A, which is
    `app/disclosure/access.py`'s own soundness statement (Task 10's own report: a capability is
    granted IFF `status == APPROVED`) -- a REVOKED row must be indistinguishable, at this boundary,
    from one that was never approved. Reaching "Both approved" from there needs a SECOND request
    for buyer A: migration 096's partial unique index (`request_one_active_per_buyer_listing_uq`)
    covers only PENDING/APPROVED, so a REVOKED row does not block a fresh one for the same
    (listing, buyer) pair -- a revoked buyer may ask again, and the seller may approve again.

    Two independent capabilities are read at every step, `name` (IDENTITY) and `rev` (FINANCIALS),
    never one alone -- a bug that grants one but not the other under FULL_CONFIDENTIAL cannot hide
    behind a single-field check."""
    _sid, s_cookies, s_hdr = member(("seller",), email="matrix-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, _photo_asset_id, _document_asset_id = await _seller_listing_with_everything_confidential(
        conn, client, store, seller_headers
    )
    _aid, a_cookies, a_hdr = member(("buyer",), email="matrix-a@x.org")
    _bid, b_cookies, b_hdr = member(("buyer",), email="matrix-b@x.org")
    a_headers, b_headers = auth_headers(a_cookies, a_hdr), auth_headers(b_cookies, b_hdr)

    request_a = await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})
    request_b = await client.post("/api/requests", headers=b_headers, json={"listing_id": listing_id})
    assert request_a.status_code == 201, request_a.text
    assert request_b.status_code == 201, request_b.text
    request_a_id, request_b_id = request_a.json()["id"], request_b.json()["id"]

    # Row 1 -- "No approval": both requests are freshly PENDING.
    body_a = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    body_b = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert body_a["name"] != "Highland Park Veterinary" and body_a["rev"] is None, "row 1: A REDACTED"
    assert body_b["name"] != "Highland Park Veterinary" and body_b["rev"] is None, "row 1: B REDACTED"

    # Row 2 -- "A approved".
    approve_a = await client.post(f"/api/seller/requests/{request_a_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert approve_a.status_code == 200 and approve_a.json()["status"] == "APPROVED"
    body_a = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    body_b = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert body_a["name"] == "Highland Park Veterinary" and body_a["rev"] == 900000, "row 2: A APPROVED"
    assert body_b["name"] != "Highland Park Veterinary" and body_b["rev"] is None, "row 2: B REDACTED"

    # Row 3 -- "A revoked".
    revoke_a = await client.post(f"/api/seller/requests/{request_a_id}/revoke", headers=seller_headers)
    assert revoke_a.status_code == 200 and revoke_a.json()["status"] == "REVOKED"
    body_a = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    body_b = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert body_a["name"] != "Highland Park Veterinary" and body_a["rev"] is None, "row 3: A REDACTED again"
    assert body_b["name"] != "Highland Park Veterinary" and body_b["rev"] is None, "row 3: B still REDACTED"

    # Row 4 -- "B approved". A's own earlier revocation must not have touched B's separate row, and
    # B's approval must not have reopened A's.
    approve_b = await client.post(f"/api/seller/requests/{request_b_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert approve_b.status_code == 200 and approve_b.json()["status"] == "APPROVED"
    body_a = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    body_b = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert body_a["name"] != "Highland Park Veterinary" and body_a["rev"] is None, "row 4: A still REDACTED"
    assert body_b["name"] == "Highland Park Veterinary" and body_b["rev"] == 900000, "row 4: B APPROVED"

    # Row 5 -- "Both approved". A's REVOKED row stays revoked forever (Task 4's own history
    # guarantee, `app/disclosure/requests.py::revoke`'s docstring); A regains access through a
    # fresh, SECOND request instead, which the partial index's own WHERE clause permits.
    second_request_a = await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})
    assert second_request_a.status_code == 201, second_request_a.text
    approve_a_again = await client.post(
        f"/api/seller/requests/{second_request_a.json()['id']}/decide", headers=seller_headers, json={"action": "approve"}
    )
    assert approve_a_again.status_code == 200 and approve_a_again.json()["status"] == "APPROVED"
    body_a = (await client.get(f"/api/listings/{listing_id}", headers=a_headers)).json()
    body_b = (await client.get(f"/api/listings/{listing_id}", headers=b_headers)).json()
    assert body_a["name"] == "Highland Park Veterinary" and body_a["rev"] == 900000, "row 5: A APPROVED"
    assert body_b["name"] == "Highland Park Veterinary" and body_b["rev"] == 900000, "row 5: B still APPROVED"


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_receives_no_confidential_information(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """directive §21: "unauthenticated user -> public information only." `listing.read` is
    `_MEMBERS`-only (`app/auth/permissions.py:19`) with no anonymous carve-out, unlike
    `market.read` -- a decision this plan does not revisit (the plan's own Task 12 note). "Public
    information only" is therefore the 401 refusal ITSELF, not a redacted-but-served 200 body:
    there is no tier below the signed-in buyer's redacted view in this product for an anonymous
    caller to receive."""
    _sid, s_cookies, s_hdr = member(("seller",), email="unauth-seller@x.org")
    listing_id, _photo_asset_id, _document_asset_id = await _seller_listing_with_everything_confidential(
        conn, client, store, auth_headers(s_cookies, s_hdr)
    )
    response = await client.get(f"/api/listings/{listing_id}")
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}


@pytest.mark.asyncio
async def test_a_partial_approval_reveals_only_the_approved_disclosure_level(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """directive §21: "Buyer with partial approval -> only approved disclosure level." A buyer who
    requests, and is granted, EXACT_LOCATION alone must receive the exact address and NOTHING
    else -- neither the name (IDENTITY) nor the revenue (FINANCIALS) nor the financial document --
    even though the listing's own ceilings for all three are wide open (the same fixture Task 11
    and the matrix above use)."""
    _sid, s_cookies, s_hdr = member(("seller",), email="partial-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, _photo_asset_id, document_asset_id = await _seller_listing_with_everything_confidential(
        conn, client, store, seller_headers
    )
    _bid, b_cookies, b_hdr = member(("buyer",), email="partial-buyer@x.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    created = await client.post(
        "/api/requests", headers=buyer_headers, json={"listing_id": listing_id, "disclosure_level": "EXACT_LOCATION"}
    )
    assert created.status_code == 201, created.text
    decided = await client.post(
        f"/api/seller/requests/{created.json()['id']}/decide", headers=seller_headers, json={"action": "approve"}
    )
    assert decided.status_code == 200 and decided.json()["approved_disclosure_level"] == "EXACT_LOCATION"

    body = (await client.get(f"/api/listings/{listing_id}", headers=buyer_headers)).json()
    assert body["street"] == "4200 Preston Rd", "the ONE granted capability must be delivered"
    assert body["name"] != "Highland Park Veterinary", "IDENTITY was never granted"
    assert body["rev"] is None, "FINANCIALS was never granted"
    document = await client.get(f"/api/seller/listings/{listing_id}/documents/{document_asset_id}", headers=buyer_headers)
    assert document.status_code == 403, "a document needs FINANCIALS or FLOOR_PLANS, neither of which this grant covers"
    assert document.json()["error"]["code"] == "LOCKED"


@pytest.mark.asyncio
async def test_a_seller_can_manage_access_for_their_own_listings(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """directive §21: "Seller -> may manage access for their own listings." The POSITIVE half of
    the ownership boundary -- `tests/api/test_disclosure_idor.py` proves the negative half (nobody
    ELSE may); together the two files fully specify it. No attacker appears here at all: the
    request's own owning seller must be able to both approve and revoke, and see the result in
    their own inbox, without tripping any guard meant for somebody else."""
    _sid, s_cookies, s_hdr = member(("seller",), email="owner-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, _photo_asset_id, _document_asset_id = await _seller_listing_with_everything_confidential(
        conn, client, store, seller_headers
    )
    _bid, b_cookies, b_hdr = member(("buyer",), email="owner-buyer@x.org")
    created = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": listing_id})
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    decided = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert decided.status_code == 200 and decided.json()["status"] == "APPROVED"
    revoked = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    assert revoked.status_code == 200 and revoked.json()["status"] == "REVOKED"

    inbox = await client.get("/api/seller/requests", headers=seller_headers)
    assert inbox.status_code == 200
    assert any(row["id"] == request_id and row["status"] == "REVOKED" for row in inbox.json())
