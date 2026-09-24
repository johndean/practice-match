# tests/api/test_disclosure_idor.py
"""directive §22, IDOR / adversarial authorization testing, per-buyer disclosure plan Task 13.

Its own four named attempts, each PROVEN denied rather than assumed denied because the code "looks
right" -- every defense here is already built somewhere in Tasks 1-9 (the partial unique index on
`request(listing_id, buyer_user_id)`, `app/api/seller_listings.py:18`'s "not yours, not found" rule
applied to this table, the per-listing-scoped `authorized_capabilities` query), and this file's job
is to prove each one actually holds against the SPECIFIC attack directive §22 names, not to
re-derive them:

1. "Buyer A requesting Buyer B's access record" is DELIBERATELY NOT re-tested here.
   `tests/api/test_disclosure_isolation.py::test_buyer_b_is_refused_even_holding_buyer_as_own_identifiers`
   already proves it in both directions -- B guessing A's own request id, and the reverse -- plus
   the storage-key and document-id angles, an hour before this file was written. Repeating it would
   be the exact duplication this task's own brief warns against ("do not duplicate them ... the
   parts of §21 and §22 [Tasks 10/11] does NOT cover").
2. "Buyer A requesting another listing's confidential resource" --
   `test_a_grant_on_one_listing_reveals_nothing_on_a_second_confidential_listing` below.
3. "Buyer A modifying another buyer's request" -- this product has NO buyer-facing route that
   modifies a request at all (`app/api/requests.py` is create/list/read-one only; `decide`/`revoke`
   are the seller's alone, `app/api/seller_requests.py`). The literal attack is therefore: a buyer,
   holding no seller role, calling the SELLER'S OWN decide/revoke routes against another buyer's
   real request -- `test_a_buyer_cannot_modify_another_buyers_request_through_the_seller_routes`
   below, which is also this task's own brief, verbatim, "attempt the seller routes as a buyer."
4. "Buyer A changing listing_id in a confidential-resource request" --
   `test_a_documents_listing_id_cannot_be_swapped_to_borrow_a_different_listings_grant` below,
   against the one confidential-resource route whose URL names TWO ids at once
   (`app/api/seller_listings.py::read_document`, `/api/seller/listings/{listing_id}/documents/{asset_id}`).

Two more attempts, beyond the literal four, because the task brief says to go where the same idea
applies: `test_a_second_seller_cannot_decide_on_or_revoke_a_request_against_a_listing_they_do_not_own`
("decide a request on a listing you do not own", "revoke someone else's grant") and
`test_a_sellers_inbox_never_lists_another_sellers_requests` ("attempt another seller's inbox").

Every test here reuses `_seller_listing_with_everything_confidential` from
`tests.api.test_disclosure_isolation` rather than declaring a second copy of it -- the plan's own
Task 13 file list says so explicitly, and it is also the ONLY reason this file needs no entry of
its own in `tests/test_docs.py::LISTING_WRITERS`: every write to the `listing` table happens
through that already-declared helper (an HTTP call it makes, never a raw SQL statement this file's
own source text contains), and `LISTING_WRITERS`'s own regex is a literal text search over the
FILE, not a call-graph trace."""
from __future__ import annotations

from typing import Any

import pytest

from tests.api.conftest import auth_headers
from tests.api.test_disclosure_isolation import (
    _LAT,
    _LNG,
    _seller_listing_with_everything_confidential,
)


@pytest.mark.asyncio
async def test_a_grant_on_one_listing_reveals_nothing_on_a_second_confidential_listing(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """directive §22, attempt 2: "Buyer A requesting another listing's confidential resource."

    Buyer A is fully approved (FULL_CONFIDENTIAL) on listing X; listing Y is a SEPARATE, equally
    confidential listing under the SAME seller that A never requested access to at all. The fixture
    gives X and Y the IDENTICAL confidential name/revenue/point on purpose (both come from
    `_seller_listing_with_everything_confidential`'s own fixed literals) -- so the assertion below
    is not "Y's values differ from X's", which a coincidence of fixture data could satisfy by
    accident, but "Y's values are NOT the confidential ones", which holds only if the grant is
    genuinely scoped to `listing_id` and not merely to the buyer."""
    _sid, s_cookies, s_hdr = member(("seller",), email="idor-x-listing-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_x, _photo_x, _doc_x = await _seller_listing_with_everything_confidential(conn, client, store, seller_headers)
    listing_y, _photo_y, _doc_y = await _seller_listing_with_everything_confidential(conn, client, store, seller_headers)
    assert listing_x != listing_y

    _aid, a_cookies, a_hdr = member(("buyer",), email="idor-x-listing-buyer@x.org")
    buyer_headers = auth_headers(a_cookies, a_hdr)
    request_x = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_x})
    assert request_x.status_code == 201, request_x.text
    approve_x = await client.post(
        f"/api/seller/requests/{request_x.json()['id']}/decide", headers=seller_headers, json={"action": "approve"}
    )
    assert approve_x.status_code == 200 and approve_x.json()["status"] == "APPROVED"

    # Confirm the grant genuinely works on X first -- a false pass below would prove nothing.
    body_x = (await client.get(f"/api/listings/{listing_x}", headers=buyer_headers)).json()
    assert body_x["name"] == "Highland Park Veterinary" and body_x["rev"] == 900000
    assert (body_x["lat"], body_x["lng"]) == (_LAT, _LNG)

    body_y = (await client.get(f"/api/listings/{listing_y}", headers=buyer_headers)).json()
    assert body_y["name"] != "Highland Park Veterinary", "a grant on X must not reach Y's name"
    assert body_y["rev"] is None, "a grant on X must not reach Y's revenue"
    # D-C66 (2026-09-24): the shared fixture's ceilings are SHUT, so an ungranted listing has no
    # point at all. This read `(round(_LAT, 2), round(_LNG, 2))` -- "Y must stay at the coarsened
    # point" -- while an open ceiling served every buyer a 1.1-km-rounded pair.
    assert (body_y["lat"], body_y["lng"]) == (None, None), "Y must give this buyer no point at all"
    assert (body_y["lat"], body_y["lng"]) != (body_x["lat"], body_x["lng"])


@pytest.mark.asyncio
async def test_a_documents_listing_id_cannot_be_swapped_to_borrow_a_different_listings_grant(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """directive §22, attempt 4: "Buyer A changing listing_id in a confidential-resource request."

    `read_document`'s route takes BOTH `listing_id` and `asset_id` from the URL
    (`app/api/seller_listings.py::read_document`); the two sub-cases below are the two ways a
    caller could try to move one id without the other:

    1. Keep buyer A's OWN GRANT listing (X) in the path, but name an asset id that genuinely
       belongs to Y, a listing A holds NO grant on at all -- the honest, matched pair FOR Y,
       fetched through X's own URL. Refused as 404 ("No such document"), never 403 ("locked"): the
       lookup is `WHERE a.id = %s AND a.listing_id = %s`, so an asset that does not belong to the
       NAMED listing does not exist as far as that listing is concerned -- the same "not yours, not
       found" rule `app/api/seller_listings.py:18` states for listing ownership, one table over,
       proved here for the first time against a buyer who holds a real, unrelated grant rather than
       against an owner or an anonymous caller.
    2. The mirror: Y's own listing_id, paired with Y's own genuine asset -- the honest pair, which
       DOES exist, but which A's X-only grant does not cover. Refused as 403 ("locked"), the
       ordinary "no capability" answer -- proving the first refusal above is really the id-pairing
       guard and not authorization refusing everything indiscriminately."""
    _sid, s_cookies, s_hdr = member(("seller",), email="idor-doc-listing-id-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_x, _photo_x, _doc_x = await _seller_listing_with_everything_confidential(conn, client, store, seller_headers)
    listing_y, _photo_y, doc_y = await _seller_listing_with_everything_confidential(conn, client, store, seller_headers)

    _aid, a_cookies, a_hdr = member(("buyer",), email="idor-doc-listing-id-buyer@x.org")
    buyer_headers = auth_headers(a_cookies, a_hdr)
    request_x = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_x})
    assert request_x.status_code == 201, request_x.text
    approve_x = await client.post(
        f"/api/seller/requests/{request_x.json()['id']}/decide", headers=seller_headers, json={"action": "approve"}
    )
    assert approve_x.status_code == 200 and approve_x.json()["status"] == "APPROVED"

    mismatched = await client.get(f"/api/seller/listings/{listing_x}/documents/{doc_y}", headers=buyer_headers)
    assert mismatched.status_code == 404, "an asset that does not belong to the NAMED listing must not exist for it"
    assert mismatched.json() == {"error": {"code": "NOT_FOUND", "message": "No such document."}}

    matched_but_ungranted = await client.get(f"/api/seller/listings/{listing_y}/documents/{doc_y}", headers=buyer_headers)
    assert matched_but_ungranted.status_code == 403, "the honest pair for Y is real, but A holds no grant on Y"
    assert matched_but_ungranted.json()["error"]["code"] == "LOCKED"


@pytest.mark.asyncio
async def test_a_buyer_cannot_modify_another_buyers_request_through_the_seller_routes(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """directive §22, attempt 3: "Buyer A modifying another buyer's request" -- and this task's own
    brief, "attempt the seller routes as a buyer"; the SAME attempt answers both, because the only
    routes that modify a request row at all are the seller's own decide/revoke.

    The refusal here is 403, not 404, which is a MEANINGFUL difference from
    `test_a_second_seller_cannot_decide_on_or_revoke_a_request_against_a_listing_they_do_not_own`
    below: a buyer is stopped at the PERMISSION layer (`request.answer_own` is seller-only,
    `app/auth/permissions.py:24`) before `app.disclosure.requests` -- the module that would answer
    "not yours" with a 404 -- is ever reached at all. Proving the outer gate holds is not the same
    fact as proving the inner ownership check holds, and this test is what proves the outer one."""
    _sid, s_cookies, s_hdr = member(("seller",), email="idor-buyer-as-seller-seller@x.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id, _photo_id, _doc_id = await _seller_listing_with_everything_confidential(conn, client, store, seller_headers)
    _aid, a_cookies, a_hdr = member(("buyer",), email="idor-buyer-as-seller-a@x.org")
    _bid, b_cookies, b_hdr = member(("buyer",), email="idor-buyer-as-seller-b@x.org")
    attacker_headers = auth_headers(a_cookies, a_hdr)
    request_b = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": listing_id})
    assert request_b.status_code == 201, request_b.text
    request_b_id = request_b.json()["id"]

    decide = await client.post(f"/api/seller/requests/{request_b_id}/decide", headers=attacker_headers, json={"action": "approve"})
    assert decide.status_code == 403
    assert decide.json() == {"error": {"code": "FORBIDDEN", "message": "Your account cannot do this."}}

    revoke = await client.post(f"/api/seller/requests/{request_b_id}/revoke", headers=attacker_headers)
    assert revoke.status_code == 403
    assert revoke.json() == {"error": {"code": "FORBIDDEN", "message": "Your account cannot do this."}}

    # B's own request is untouched by either attempt -- still the real seller's alone to decide.
    still_theirs = await client.post(f"/api/seller/requests/{request_b_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert still_theirs.status_code == 200 and still_theirs.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_a_second_seller_cannot_decide_on_or_revoke_a_request_against_a_listing_they_do_not_own(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """This task's own brief, beyond the literal four: "decide a request on a listing you do not
    own" and "revoke someone else's grant." The attacker here IS a real seller -- unlike the buyer
    above, they hold `request.answer_own` and pass the permission gate cleanly -- so this is the
    OWNERSHIP check itself under test, `app.disclosure.requests._owned_pending_or_approved`'s own
    rule: a request against a listing that is not the caller's own is 404, never 403, because a 403
    would confirm a request row is there at all (`app/api/seller_listings.py:18`'s rule, restated
    for this table)."""
    _sid, s_cookies, s_hdr = member(("seller",), email="idor-wrong-seller-owner@x.org")
    owner_headers = auth_headers(s_cookies, s_hdr)
    listing_id, _photo_id, _doc_id = await _seller_listing_with_everything_confidential(conn, client, store, owner_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="idor-wrong-seller-buyer@x.org")
    request_row = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": listing_id})
    assert request_row.status_code == 201, request_row.text
    request_id = request_row.json()["id"]

    _oid, o_cookies, o_hdr = member(("seller",), email="idor-wrong-seller-attacker@x.org")
    attacker_headers = auth_headers(o_cookies, o_hdr)

    decide = await client.post(f"/api/seller/requests/{request_id}/decide", headers=attacker_headers, json={"action": "approve"})
    assert decide.status_code == 404
    assert decide.json() == {"error": {"code": "NOT_FOUND", "message": "No such request."}}

    # The REAL owner approves, so there is something live for the attacker's revoke to target.
    approved = await client.post(f"/api/seller/requests/{request_id}/decide", headers=owner_headers, json={"action": "approve"})
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"

    revoke = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=attacker_headers)
    assert revoke.status_code == 404
    assert revoke.json() == {"error": {"code": "NOT_FOUND", "message": "No such request."}}

    # The buyer's real grant survives the attacker's failed revoke attempt untouched.
    body = (await client.get(f"/api/listings/{listing_id}", headers=auth_headers(b_cookies, b_hdr))).json()
    assert body["name"] == "Highland Park Veterinary", "the attacker's failed revoke must not have touched the real grant"


@pytest.mark.asyncio
async def test_a_sellers_inbox_never_lists_another_sellers_requests(
    client: Any, conn: Any, member: Any, store: Any,
) -> None:
    """This task's own brief, beyond the literal four: "attempt another seller's inbox."
    `GET /api/seller/requests` takes no parameter that could name a different seller at all
    (`app/api/seller_requests.py::list_inbox`'s own docstring: "no parameter exists that could let
    a caller name a different seller") -- so there is no id to guess here, and the only thing left
    to prove is that the SCOPE itself holds: a second seller's own inbox, with a request of its own
    already in it, must never contain a row that belongs to the first seller's listing, whatever
    request ids exist in the database."""
    _sid, s_cookies, s_hdr = member(("seller",), email="idor-inbox-seller-x@x.org")
    seller_x_headers = auth_headers(s_cookies, s_hdr)
    listing_x, _photo_x, _doc_x = await _seller_listing_with_everything_confidential(conn, client, store, seller_x_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="idor-inbox-buyer@x.org")
    request_x = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": listing_x})
    assert request_x.status_code == 201, request_x.text
    request_x_id = request_x.json()["id"]

    _oid, o_cookies, o_hdr = member(("seller",), email="idor-inbox-seller-y@x.org")
    seller_y_headers = auth_headers(o_cookies, o_hdr)
    listing_y, _photo_y, _doc_y = await _seller_listing_with_everything_confidential(conn, client, store, seller_y_headers)
    request_y = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": listing_y})
    assert request_y.status_code == 201, request_y.text

    inbox_y = await client.get("/api/seller/requests", headers=seller_y_headers)
    assert inbox_y.status_code == 200
    rows_y = inbox_y.json()
    assert request_x_id not in {row["id"] for row in rows_y}, "seller Y's inbox must never contain seller X's request"
    assert all(row["listing_id"] == listing_y for row in rows_y), "every row in Y's inbox must be against Y's own listing"
