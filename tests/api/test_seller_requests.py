"""GET /api/seller/requests, POST .../decide, POST .../revoke (directive §5, §14, §15, §22).

This is Task 5's sibling. `app/disclosure/requests.py` (Task 4) already proved the lifecycle's own
rules (`decide`/`revoke`/`list_inbox`) at the module boundary; this file proves the HTTP surface
around it — the guard is `request.answer_own` through `Depends` (never wrapped), every refusal
renders the `{"error": {"code", "message"}}` envelope, and, per this task's own brief, the three
IDOR cases: a seller deciding another seller's request, a buyer reaching a seller route, and a
malformed request id — each refused, none reaching a 500.

`app/api/seller_requests.py` reuses `app/api/requests.py`'s already-proved guards (`_valid_uuid`,
`_serialisable`, `_json_body`, `MAX_JSON_BYTES`) rather than declaring a second copy of them — see
that module's own docstring and `.superpowers/sdd/2026-09-18-per-buyer-disclosure/task-06-report.md`
for the full account of why `request_id`, `disclosure_level` and `reason` each need the identical
guard Task 5 already proved necessary for `listing_id`/`disclosure_level`/`message`.

`_pair` below reuses `tests.api.test_requests._seller_listing` (the ALREADY-FIXED helper —
`listing_publishable_ck`/`listing_submittable_ck`, see that module's own docstring) rather than
re-deriving which columns a `published` listing needs a second time in a second file.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.api.conftest import auth_headers
from tests.api.test_requests import _seller_listing


async def _pair(conn, client, member, seller_email: str, buyer_email: str) -> tuple[dict, dict, str, str, str]:
    """A seller with a published listing, a buyer with a PENDING request against it.

    Returns `(seller_headers, buyer_headers, listing_id, request_id, buyer_account_id)` — the
    buyer's own account id (as `str`) is the plan's own `_pair` tuple widened by one element, so a
    test can assert the audit row names THIS buyer rather than merely "some buyer"."""
    _sid, s_cookies, s_hdr = member(("seller",), email=seller_email)
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _seller_listing(conn, client, seller_headers)
    bid, b_cookies, b_hdr = member(("buyer",), email=buyer_email)
    buyer_headers = auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    assert created.status_code == 201, created.text
    return seller_headers, buyer_headers, listing_id, created.json()["id"], str(bid)


# --- the inbox, scoped to the calling seller ----------------------------------------------------


@pytest.mark.asyncio
async def test_a_seller_sees_requests_against_their_own_listings(client, conn, member) -> None:
    seller_headers, _buyer_headers, listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s1@x.org", "b1@x.org")
    response = await client.get("/api/seller/requests", headers=seller_headers)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["id"] == request_id and rows[0]["listing_id"] == listing_id


@pytest.mark.asyncio
async def test_a_different_seller_does_not_see_it(client, conn, member) -> None:
    _seller_headers, _buyer_headers, _listing_id, _request_id, _buyer_id = await _pair(conn, client, member, "s2@x.org", "b2@x.org")
    _oid, o_cookies, o_hdr = member(("seller",), email="other2@x.org")
    response = await client.get("/api/seller/requests", headers=auth_headers(o_cookies, o_hdr))
    assert response.status_code == 200 and response.json() == []


@pytest.mark.asyncio
async def test_a_buyer_role_alone_cannot_reach_the_inbox(client, member) -> None:
    """IDOR case 2 (this task's brief): a buyer reaching a seller route. `request.answer_own` is
    seller-only (`app/auth/permissions.py`), so the route GUARD refuses before any row is ever
    read — a 403, not a filtered-to-empty 200."""
    _bid, b_cookies, b_hdr = member(("buyer",), email="b8@x.org")
    response = await client.get("/api/seller/requests", headers=auth_headers(b_cookies, b_hdr))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_is_refused_on_the_inbox(client) -> None:
    response = await client.get("/api/seller/requests")
    assert response.status_code == 401


# --- the inbox: buyer identity (directive §5's own gap this task closes) -----------------------


@pytest.mark.asyncio
async def test_the_inbox_carries_the_requesting_buyers_identity(client, conn, member) -> None:
    """Directive §5, verbatim: "For each request show: buyer identity." Before this, the inbox
    served `buyer_user_id` alone — an opaque uuid, where the design's own fixture row reads
    `buyer: "Dr. Rachel Mendes"` (`frontend/src/logic.js:275`) — so a seller was asked to approve
    or deny disclosure of confidential financials to a UUID. `app.disclosure.requests.list_inbox`
    now joins the requesting buyer's own account row for it, `app/api/admin_users.py`'s
    `decided_by_name`/`granted_by_name` precedent, one table over."""
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s-bname1@x.org", "b-bname1@x.org")
    response = await client.get("/api/seller/requests", headers=seller_headers)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1 and rows[0]["id"] == request_id
    # "Dr. Rachel Mendes" is the `member` fixture's own literal `display_name` (`tests/api/conftest.py`).
    assert rows[0]["buyer_name"] == "Dr. Rachel Mendes"
    assert rows[0]["buyer_user_id"], "the id itself stays -- buyer_name is additive, not a replacement"


@pytest.mark.asyncio
async def test_a_second_sellers_inbox_never_carries_another_sellers_buyers_identity(client, conn, member) -> None:
    """The leak this task's own new join could introduce, proved with two DISTINCT names so a leak
    reads as literal cross-contamination in the response body rather than a coincidence of the
    `member` fixture's own shared "Dr. Rachel Mendes" default — every account the fixture makes
    carries that same literal, so a same-named check here would pass whether or not the join is
    genuinely scoped to the calling seller's own rows. Seller Y's own request (a real buyer, a real
    name) proves the join still WORKS; the absence of seller X's buyer's name proves it is scoped,
    the property `test_a_sellers_inbox_never_lists_another_sellers_requests`
    (`tests/api/test_disclosure_idor.py`) already proves for the ROW and this test proves again for
    the NAME the new join reads off it."""
    _sx_headers, _bx_headers, _listing_x, _request_x, buyer_x_id = await _pair(
        conn, client, member, "leak-seller-x@x.org", "leak-buyer-x@x.org",
    )
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET display_name = %s WHERE id = %s", ("Dr. Xavier Ortiz", buyer_x_id))

    seller_y_headers, _by_headers, listing_y, request_y, buyer_y_id = await _pair(
        conn, client, member, "leak-seller-y@x.org", "leak-buyer-y@x.org",
    )
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET display_name = %s WHERE id = %s", ("Dr. Yolanda Ives", buyer_y_id))

    response = await client.get("/api/seller/requests", headers=seller_y_headers)
    assert response.status_code == 200
    assert "Dr. Xavier Ortiz" not in response.text, "seller Y's inbox must never carry seller X's buyer's identity"
    rows = response.json()
    assert len(rows) == 1 and rows[0]["id"] == request_y and rows[0]["listing_id"] == listing_y
    assert rows[0]["buyer_name"] == "Dr. Yolanda Ives"


@pytest.mark.asyncio
async def test_an_unnamed_buyer_renders_the_honest_email_fallback(client, conn, member) -> None:
    """"Do not fabricate a placeholder person" (this task's own brief): a buyer who has signed up
    and never yet submitted an application has no `display_name` at all
    (`app/api/applications.py`'s own `COALESCE(display_name, ...)` is the only writer of that
    column), and `list_inbox` falls back to that same account's own `email` — a real identity
    already on file — rather than showing the seller `None`, an empty string, or a name nobody
    gave."""
    seller_headers, _buyer_headers, _listing_id, request_id, buyer_id = await _pair(conn, client, member, "s-bname2@x.org", "b-bname2@x.org")
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET display_name = NULL WHERE id = %s", (buyer_id,))
    response = await client.get("/api/seller/requests", headers=seller_headers)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1 and rows[0]["id"] == request_id
    assert rows[0]["buyer_name"] == "b-bname2@x.org"
    assert rows[0]["buyer_name"] not in (None, ""), "never None, empty, or a fabricated name"


@pytest.mark.asyncio
async def test_a_buyers_own_view_never_carries_a_buyer_name_field_either(client, conn, member) -> None:
    """The mirror of this task's own rule ("do not add seller identity to the buyer's payload"):
    `req.list_mine`/`req.get_one` are UNTOUCHED — only `list_inbox` was given the join — so a
    buyer's own reads carry no `buyer_name` at all, not even their own, exactly as they already
    carry no `seller_user_id`
    (`test_a_buyer_never_receives_the_sellers_internal_account_id`, `tests/api/test_requests.py`,
    predating and unedited by this task)."""
    _seller_headers, buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s-bname3@x.org", "b-bname3@x.org")
    mine = (await client.get("/api/requests/mine", headers=buyer_headers)).json()
    assert mine and all("buyer_name" not in row for row in mine)
    one = (await client.get(f"/api/requests/{request_id}", headers=buyer_headers)).json()
    assert "buyer_name" not in one


# --- decide: approve --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_grants_the_requested_level_by_default(client, conn, member, audit_rows) -> None:
    seller_headers, _buyer_headers, listing_id, request_id, buyer_id = await _pair(conn, client, member, "s3@x.org", "b3@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "APPROVED" and body["approved_disclosure_level"] == "FULL_CONFIDENTIAL"
    # Deviation 2's own proof, inherited from Task 5: `reviewed_at` is a real `datetime.datetime`
    # on the model side and must survive `_serialisable` as a string here too.
    assert isinstance(body["reviewed_at"], str) and body["reviewed_at"]
    rows = [r for r in audit_rows() if r["action"] == "access.approved"]
    assert len(rows) == 1
    row = rows[0]
    assert row["target_type"] == "request" and row["target_id"] == request_id
    # Directive §14 / this task's brief: "for which buyer and listing" — not merely the request id.
    assert row["after"]["listing_id"] == listing_id
    assert row["after"]["buyer_user_id"] == buyer_id
    assert row["after"]["status"] == "APPROVED" and row["after"]["level"] == "FULL_CONFIDENTIAL"


@pytest.mark.asyncio
async def test_approve_can_override_the_level_below_what_was_requested(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s3b@x.org", "b3b@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers,
                                 json={"action": "approve", "disclosure_level": "IDENTITY"})
    assert response.status_code == 200 and response.json()["approved_disclosure_level"] == "IDENTITY"


@pytest.mark.asyncio
async def test_approve_refused_once_already_decided(client, conn, member) -> None:
    """The task brief's own required case: "approve refused on an already-decided request.\""""
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s3c@x.org", "b3c@x.org")
    first = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert first.status_code == 200
    second = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert second.status_code == 409 and second.json()["error"]["code"] == "STATE"


# --- decide: deny -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deny_records_the_sellers_reason(client, conn, member, audit_rows) -> None:
    seller_headers, _buyer_headers, listing_id, request_id, buyer_id = await _pair(conn, client, member, "s4@x.org", "b4@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers,
                                 json={"action": "deny", "reason": "Not a good fit"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DENIED" and response.json()["denial_reason"] == "Not a good fit"
    rows = [r for r in audit_rows() if r["action"] == "access.denied"]
    assert len(rows) == 1
    row = rows[0]
    assert row["after"]["listing_id"] == listing_id and row["after"]["buyer_user_id"] == buyer_id
    assert row["after"]["status"] == "DENIED" and row["after"]["level"] is None
    # The seller's own free-text words, on `audit_log.reason` — `app/api/admin_listings.py`'s own
    # shape for a decision's rationale, not duplicated a second time inside `after`.
    assert row["reason"] == "Not a good fit"


@pytest.mark.asyncio
async def test_deny_is_final_until_a_new_request_is_made(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s4b@x.org", "b4b@x.org")
    await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "deny", "reason": "no"})
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "STATE"


@pytest.mark.asyncio
async def test_deny_with_no_reason_writes_no_reason_on_the_audit_row(client, conn, member, audit_rows) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s4c@x.org", "b4c@x.org")
    await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "deny"})
    rows = [r for r in audit_rows() if r["action"] == "access.denied"]
    assert len(rows) == 1 and rows[0]["reason"] is None


# --- decide: IDOR (this task's brief — the three cases) --------------------------------------


@pytest.mark.asyncio
async def test_a_different_seller_cannot_decide_on_it(client, conn, member) -> None:
    """IDOR case 1 (this task's brief, verbatim): a seller deciding another seller's request."""
    _seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s5@x.org", "b5@x.org")
    _oid, o_cookies, o_hdr = member(("seller",), email="other5@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=auth_headers(o_cookies, o_hdr),
                                 json={"action": "approve"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_different_seller_cannot_revoke_it_either(client, conn, member) -> None:
    """The same ownership check, applied to revoke — Task 4's own report named this ("my brief
    said 'every seller action,' plural") at the module boundary; proved again at the route."""
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s5b@x.org", "b5b@x.org")
    await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    _oid, o_cookies, o_hdr = member(("seller",), email="other5b@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=auth_headers(o_cookies, o_hdr))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_buyer_cannot_decide_on_a_request_even_knowing_its_real_id(client, conn, member) -> None:
    """IDOR case 2 at the decide door specifically (not only the inbox listing): the route GUARD
    (`request.answer_own`, seller-only) refuses before `req.decide` is ever called."""
    _seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s5c@x.org", "b5c@x.org")
    _bid, b_cookies, b_hdr = member(("buyer",), email="stray5c@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=auth_headers(b_cookies, b_hdr),
                                 json={"action": "approve"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_buyer_cannot_revoke_a_request_even_knowing_its_real_id(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s5d@x.org", "b5d@x.org")
    await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    _bid, b_cookies, b_hdr = member(("buyer",), email="stray5d@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=auth_headers(b_cookies, b_hdr))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_decide_refuses_a_malformed_request_id(client, member) -> None:
    """IDOR case 3 (this task's brief, verbatim): a malformed request id, refused, never a 500."""
    _sid, s_cookies, s_hdr = member(("seller",), email="s5e@x.org")
    response = await client.post("/api/seller/requests/not-a-uuid/decide", headers=auth_headers(s_cookies, s_hdr),
                                 json={"action": "approve"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_revoke_refuses_a_malformed_request_id(client, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s5f@x.org")
    response = await client.post("/api/seller/requests/not-a-uuid/revoke", headers=auth_headers(s_cookies, s_hdr))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_decide_refuses_a_well_formed_but_absent_request_id(client, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="s5g@x.org")
    response = await client.post(f"/api/seller/requests/{uuid4()}/decide", headers=auth_headers(s_cookies, s_hdr),
                                 json={"action": "approve"})
    assert response.status_code == 404


# --- decide: input validation (the same guard classes Task 5 proved for its own inputs) --------


@pytest.mark.asyncio
async def test_decide_requires_an_action(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s6@x.org", "b6@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers)
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_ACTION"


@pytest.mark.asyncio
async def test_decide_refuses_a_non_string_disclosure_level(client, conn, member) -> None:
    """Fail closed (directive §19), the identical class Task 5 proved for `create`'s
    `disclosure_level`: `level not in REQUESTABLE_LEVELS` raises `TypeError` for an unhashable
    value rather than answering `False`, so a list/object must never reach it unchecked."""
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s6b@x.org", "b6b@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers,
                                 json={"action": "approve", "disclosure_level": ["FULL_CONFIDENTIAL"]})
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_LEVEL"


@pytest.mark.asyncio
async def test_decide_refuses_a_non_string_reason(client, conn, member) -> None:
    """The same gap one field over: `req.decide`'s deny branch sends `reason` straight into
    `UPDATE request SET denial_reason = %s`, and a non-string value either fails psycopg2's own
    adapter (a dict) or mismatches the `text` column at the database (a list, adapted to an
    ARRAY literal) — both raw 500s absent this guard."""
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s6c@x.org", "b6c@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers,
                                 json={"action": "deny", "reason": {"not": "a string"}})
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_decide_refuses_malformed_json(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s6d@x.org", "b6d@x.org")
    headers = {**seller_headers, "Content-Type": "application/json"}
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=headers, content=b"{not valid json")
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_JSON"


@pytest.mark.asyncio
async def test_decide_refuses_a_non_object_json_body(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s6e@x.org", "b6e@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json=["approve"])
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_decide_refuses_a_body_over_the_size_cap(client, conn, member) -> None:
    from app.api.requests import MAX_JSON_BYTES

    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s6f@x.org", "b6f@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers,
                                 json={"action": "deny", "reason": "x" * (MAX_JSON_BYTES + 1)})
    assert response.status_code == 413 and response.json()["error"]["code"] == "TOO_LARGE"


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_is_refused_on_decide(client) -> None:
    response = await client.post(f"/api/seller/requests/{uuid4()}/decide", json={"action": "approve"})
    assert response.status_code == 401


# --- revoke ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_requires_a_prior_approval(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s7@x.org", "b7@x.org")
    response = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    assert response.status_code == 409 and response.json()["error"]["code"] == "STATE"


@pytest.mark.asyncio
async def test_revoke_after_approval_writes_an_audit_row(client, conn, member, audit_rows) -> None:
    seller_headers, _buyer_headers, listing_id, request_id, buyer_id = await _pair(conn, client, member, "s8@x.org", "b8@x.org")
    await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    response = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REVOKED"
    rows = [r for r in audit_rows() if r["action"] == "access.revoked"]
    assert len(rows) == 1
    row = rows[0]
    assert row["target_type"] == "request" and row["target_id"] == request_id
    assert row["after"]["listing_id"] == listing_id and row["after"]["buyer_user_id"] == buyer_id
    assert row["after"]["status"] == "REVOKED"
    # migration 096's own comment: a REVOKED row keeps its `approved_disclosure_level` for
    # history — the audit row names what was revoked, not merely that something was.
    assert row["after"]["level"] == "FULL_CONFIDENTIAL"


@pytest.mark.asyncio
async def test_revoke_is_final_a_second_revoke_is_refused(client, conn, member) -> None:
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s8b@x.org", "b8b@x.org")
    await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    second = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    assert second.status_code == 409 and second.json()["error"]["code"] == "STATE"


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_is_refused_on_revoke(client) -> None:
    response = await client.post(f"/api/seller/requests/{uuid4()}/revoke")
    assert response.status_code == 401


# --- rate limiting (directive §6/§23; `app/api/seller_listings.py`'s own convention that every
# mutating seller route is throttled — see this module's own Deviations) ------------------------


@pytest.mark.asyncio
async def test_the_decide_rate_limit_is_per_seller(client, conn, member, monkeypatch) -> None:
    from app.api import seller_requests as SR

    monkeypatch.setattr(SR, "ACCESS_REQUEST_DECIDE", (1, 3600))
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s9@x.org", "b9@x.org")
    first = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert first.status_code == 200, first.text
    # The second call reuses the SAME `request:decide` bucket (Task 6, keyed on the account id
    # alone, not on the request being decided), so it is refused before `req.decide` is even
    # reached — proved by requesting the SAME already-approved id, which would otherwise 409.
    refused = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert refused.status_code == 429 and refused.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_the_revoke_rate_limit_is_per_seller(client, conn, member, monkeypatch) -> None:
    """Proves the guard this task ADDS beyond the plan's own literal Step 3 code (see Deviations):
    `revoke` shares `ACCESS_REQUEST_DECIDE`'s budget too, matching every mutating route in
    `app/api/seller_listings.py`. Perturbing this call out of `revoke_request` is what turns this
    test red — the property this codebase's own memory note asks to be proved, not merely
    asserted."""
    from app.api import seller_requests as SR

    monkeypatch.setattr(SR, "ACCESS_REQUEST_DECIDE", (1, 3600))
    seller_headers, _buyer_headers, _listing_id, request_id, _buyer_id = await _pair(conn, client, member, "s9b@x.org", "b9b@x.org")
    await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    # The decide call above already spent the one-per-hour reservation, so the revoke call below
    # is refused by the SAME bucket before `req.revoke` is ever reached.
    refused = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    assert refused.status_code == 429 and refused.json()["error"]["code"] == "RATE_LIMITED"


# --- the property that matters (this task's own brief, verbatim) -------------------------------


@pytest.mark.asyncio
async def test_after_revoke_authorized_capabilities_is_empty_for_that_buyer(client, conn, member) -> None:
    """"After revoke, `app.disclosure.access.authorized_capabilities` returns the empty set for
    that buyer" — asserted against the REAL function, never against this route's own HTTP
    response, and asserted non-empty first (Task 4's own precedent) so this test would fail loudly
    if the setup itself were broken rather than passing vacuously."""
    from app.disclosure import access

    seller_headers, _buyer_headers, listing_id, request_id, buyer_id = await _pair(conn, client, member, "s10@x.org", "b10@x.org")
    with conn.cursor() as cur:
        cur.execute("SELECT seller_id FROM listing WHERE id = %s", (listing_id,))
        seller_id = str(cur.fetchone()[0])
    approve = await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers, json={"action": "approve"})
    assert approve.status_code == 200
    granted = access.authorized_capabilities(conn, listing_id=listing_id, seller_id=seller_id, buyer_account_id=buyer_id)
    assert granted, "setup is broken: the buyer should already hold a capability before revoke"
    revoke = await client.post(f"/api/seller/requests/{request_id}/revoke", headers=seller_headers)
    assert revoke.status_code == 200
    assert access.authorized_capabilities(conn, listing_id=listing_id, seller_id=seller_id, buyer_account_id=buyer_id) == frozenset()
