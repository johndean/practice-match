"""Task I5, Step 1 — staff decisions, role grants, api tokens and the Admin read endpoints.

Same two adaptations as `tests/api/test_applications.py`: `auth_headers(...)` instead of httpx's
deprecated per-request `cookies=` (the suite runs `-W error`), and decision A5's `{"error": ...}`
envelope, which means the endpoints raise `app.auth.deps.AuthError` subclasses.

One assertion of the brief's is deliberately NOT reproduced: its line

    assert (await client.get("/api/me", headers=Bearer(token))).status_code == 403  # a token has no account

was written before I3 fix round 1's Important 10 gave an api-token principal the account id of the
person who MINTED it (`ApiPrincipal.created_by`), so that an audit row can name a real actor. I4
then shipped and reviewed the opposite assertion —
`tests/api/test_auth.py::test_an_api_token_cannot_use_the_session_only_routes` ends with
`assert (await client.get("/api/me", headers=auth)).status_code == 200  # spec allows a token here`
— so reproducing the brief's line here would need a change to `app/auth/deps.py`, which this task
does not own. The token's real boundary (it may read; it may not use the session-only routes) is
asserted below instead, and the divergence is recorded in the task report for John.
"""
from __future__ import annotations

import contextlib
import io
import runpy
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from tests.api.conftest import ORIGIN, PW, auth_headers

ROOT = Path(__file__).resolve().parents[2]
FIELDS = {"name": "Priya Raghavan, DVM", "vin_member_id": "", "school_year": "Texas A&M, 2016", "license_state": "TX",
          "employer": "Associate", "intent": "Buy in Central Texas.", "affirm": True}
SELLER_FIELDS = {"practice_name": "Cedar Park Animal Hospital", "license_state": "TX", "ownership_attestation": True}
INVITE_PW = "cedar-lantern-orbit-quiet-93"          # 28 chars, zxcvbn 4 — clears the privileged floor
SHORT_PW = "cedar-orbit-9"                          # 13 chars, zxcvbn 4 — clears MIN_LEN, fails MIN_LEN_PRIVILEGED


async def _applicant(client, member, email="p@example.org"):
    aid, cookies, hdr = member((), state="verified", email=email)
    await client.post("/api/applications", headers=auth_headers(cookies, hdr), json={"kind": "buyer", "fields": FIELDS})
    return aid, cookies


async def test_staff_lists_pending_and_views_are_audited(client, conn, member):
    aid, _ = await _applicant(client, member)
    sid, scookies, _shdr = member(("staff",), email="staff@example.org")
    r = await client.get("/api/admin/users?state=pending", headers=auth_headers(scookies))
    assert r.status_code == 200 and r.json()["items"][0]["account_id"] == str(aid) and r.json()["items"][0]["kind"] == "buyer"
    assert (await client.get(f"/api/admin/users/{aid}", headers=auth_headers(scookies))).status_code == 200
    with conn.cursor() as cur:
        # The action is named after the permission that guards the route (`users.view_detail`),
        # not after a shortened form of it: an auditor greps `audit_log` for the permission.
        cur.execute("SELECT action, actor_id::text, target_id FROM audit_log WHERE action='users.view_detail'")
        assert cur.fetchone() == ("users.view_detail", str(sid), str(aid))
        cur.execute("SELECT count(*) FROM audit_log WHERE action='users.view'"); assert cur.fetchone()[0] == 0
    _bid, bcookies, _ = member(("buyer",), email="b@example.org")
    assert (await client.get("/api/admin/users", headers=auth_headers(bcookies))).status_code == 403


async def test_approve_grants_buyer_and_emails(client, conn, member):
    aid, acookies = await _applicant(client, member)
    _sid, scookies, shdr = member(("staff",), email="staff@example.org")
    r = await client.post(f"/api/admin/users/{aid}/decide", headers=auth_headers(scookies, shdr), json={"action": "approve", "note": ""})
    assert r.status_code == 200 and r.json() == {"state": "active", "roles": ["buyer"]}
    with conn.cursor() as cur:
        cur.execute("SELECT template FROM email_outbox ORDER BY id")
        assert [x[0] for x in cur.fetchall()] == ["application_received", "application_approved"]
        cur.execute("SELECT action, reason FROM audit_log WHERE action='users.decide'")
        assert cur.fetchone() == ("users.decide", "approve")
    assert (await client.get("/api/me", headers=auth_headers(acookies))).json()["role"] == "Approved buyer"


async def test_decline_and_request_info_require_a_note(client, conn, member):
    aid, _ = await _applicant(client, member)
    _sid, scookies, shdr = member(("staff",), email="staff@example.org")
    assert (await client.post(f"/api/admin/users/{aid}/decide", headers=auth_headers(scookies, shdr),
                              json={"action": "decline", "note": ""})).status_code == 422
    r = await client.post(f"/api/admin/users/{aid}/decide", headers=auth_headers(scookies, shdr),
                          json={"action": "request_info", "note": "Which practice do you work at now?"})
    assert r.status_code == 200 and r.json()["state"] == "needs_review"


async def test_suspend_takes_effect_on_next_request_and_revoke_needs_reauth(client, conn, redis, member):
    mid, mcookies, _ = member(("buyer",), email="m@example.org")
    _sid, scookies, shdr = member(("staff",), email="staff@example.org")
    assert (await client.get("/api/me", headers=auth_headers(mcookies))).status_code == 200
    assert (await client.post(f"/api/admin/users/{mid}/decide", headers=auth_headers(scookies, shdr),
                              json={"action": "suspend", "note": "Complaint under review"})).status_code == 200
    assert (await client.get("/api/me", headers=auth_headers(mcookies))).status_code == 401
    r = await client.post(f"/api/admin/users/{mid}/decide", headers=auth_headers(scookies, shdr),
                          json={"action": "revoke", "note": "Consolidator"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_REQUIRED"
    await client.post("/api/auth/reauth", headers=auth_headers(scookies, shdr), json={"password": PW})
    assert (await client.post(f"/api/admin/users/{mid}/decide", headers=auth_headers(scookies, shdr),
                              json={"action": "revoke", "note": "Consolidator"})).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM role_grant WHERE account_id=%s AND revoked_at IS NULL", (mid,))
        assert cur.fetchone()[0] == 0


async def test_admin_grants_roles_and_issues_tokens_with_reauth(client, conn, member):
    _aid, acookies, ahdr = member(("admin",), email="admin@example.org")
    mid, _, _ = member(("buyer",), email="m@example.org")
    await client.post("/api/auth/reauth", headers=auth_headers(acookies, ahdr), json={"password": PW})
    r = await client.post(f"/api/admin/users/{mid}/grants", headers=auth_headers(acookies, ahdr),
                          json={"role": "staff", "grant": True, "reason": "New reviewer"})
    assert r.status_code == 200 and r.json()["roles"] == ["buyer", "staff"]
    t = await client.post("/api/admin/tokens", headers=auth_headers(acookies, ahdr), json={"name": "k6-qa", "role": "buyer", "days": 30})
    assert t.status_code == 201 and t.json()["token"].startswith("pm_")
    bearer = {"Authorization": f"Bearer {t.json()['token']}"}
    # `market.read` is granted to the token's `buyer` role; /api/layers does not exist until Census
    # lands, so the JSON 404 catch-all answers. The point is that it is not a 401 or a 403.
    assert (await client.get("/api/layers", headers=bearer)).status_code in (200, 404)
    # ...and a token still cannot use the session-only routes, whatever `account.self` grants it (I4).
    assert (await client.post("/api/auth/signout-all", headers=bearer)).status_code == 401
    p = (await client.get("/api/admin/permissions", headers=auth_headers(acookies))).json()
    assert p["matrix"]["engine.activate"] == ["admin"] and "roles" in p


def test_bootstrap_admin_prints_an_invite_and_refuses_production(scratch_dsn):
    env = {"DATABASE_URL": scratch_dsn, "REDIS_URL": "redis://localhost:6380/9", "ENVIRONMENT": "test",
           "API_SECRET_KEY": "x", "LINK_BASE_URL": "https://qa.foundation.vin"}
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "bootstrap_admin.py"), "--email", "john@example.org"],
                         env={**env, "PATH": ""}, capture_output=True, text=True, check=True).stdout
    assert "https://qa.foundation.vin/accept-invite?token=" in out
    seed = subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_persona.py")],
                          env={**env, "ENVIRONMENT": "production", "PATH": ""}, capture_output=True, text=True, check=False)
    assert seed.returncode != 0 and "production" in seed.stderr


# --- supplemental (not in the brief's Step 1): John's 2026-09-06 binding condition on the Admin
# Users list, and his 100 % line-AND-branch coverage ruling ---


async def test_admin_users_lists_every_account_in_every_state_and_role_including_the_caller(client, conn, member):
    """John's condition, 2026-09-06: **every account and every role is surfaced in the admin
    controls, admins included.** A listing contains the staff account, the OTHER admin and the
    caller's own admin account, each with its `roles[]` and, per grant, `granted_by`/`granted_at`;
    `role=` filters alongside `state=`/`kind=`, and `role=admin` returns exactly the admins. No
    role is hidden from the list, and there is no separate "SuperAdmin": Admin is the top role."""
    applicant, _ = await _applicant(client, member, email="applicant@example.org")
    suspended, _c1, _h1 = member(("seller",), state="suspended", email="suspended@example.org")
    staff, _c2, _h2 = member(("staff",), email="staff@example.org")
    other_admin, _c3, _h3 = member(("admin",), email="other-admin@example.org")
    caller, cookies, _hdr = member(("admin",), email="caller@example.org")

    body = (await client.get("/api/admin/users?limit=200", headers=auth_headers(cookies))).json()
    listed = {item["account_id"]: item for item in body["items"]}
    assert {str(applicant), str(suspended), str(staff), str(other_admin), str(caller)} <= set(listed)
    assert listed[str(staff)]["roles"] == ["staff"] and listed[str(staff)]["state"] == "active"
    assert listed[str(other_admin)]["roles"] == ["admin"]
    assert listed[str(caller)]["roles"] == ["admin"], "the caller's own account is in the list"
    assert listed[str(suspended)]["state"] == "suspended" and listed[str(suspended)]["roles"] == ["seller"]
    assert listed[str(applicant)]["roles"] == [] and listed[str(applicant)]["kind"] == "buyer"
    grant = listed[str(staff)]["grants"][0]
    assert grant["role"] == "staff" and grant["granted_by"] == str(staff) and grant["granted_at"]

    admins = (await client.get("/api/admin/users?role=admin", headers=auth_headers(cookies))).json()["items"]
    assert sorted(i["account_id"] for i in admins) == sorted([str(other_admin), str(caller)])
    only_staff = (await client.get("/api/admin/users?role=staff", headers=auth_headers(cookies))).json()["items"]
    assert [i["account_id"] for i in only_staff] == [str(staff)]
    # C2 (John, 2026-09-07): spec §4 audits "viewing an application DETAIL", not the list. Listing
    # the queue is guarded by `users.review`, which is no longer in `AUDITED`, so three page reads
    # leave no rows — one per poll of the I7 Users tab, into an append-only table, was a slow leak
    # with no spec mandate behind it.
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log WHERE action IN ('users.list','users.review')")
        assert cur.fetchone()[0] == 0


async def test_admin_users_paginates_by_cursor_and_filters_by_kind(client, conn, member):
    _one, _ = await _applicant(client, member, email="one@example.org")
    _two, _ = await _applicant(client, member, email="two@example.org")
    seller, scookies, shdr = member(("buyer",), email="seller-app@example.org")
    await client.post("/api/applications", headers=auth_headers(scookies, shdr), json={"kind": "seller", "fields": SELLER_FIELDS})
    _admin, cookies, _hdr = member(("admin",), email="pager@example.org")

    first = (await client.get("/api/admin/users?limit=1", headers=auth_headers(cookies))).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = (await client.get(f"/api/admin/users?limit=1&cursor={first['next_cursor']}", headers=auth_headers(cookies))).json()
    assert second["items"][0]["account_id"] != first["items"][0]["account_id"]
    last = (await client.get("/api/admin/users?limit=500", headers=auth_headers(cookies))).json()
    assert last["next_cursor"] is None and len(last["items"]) == 4
    by_kind = (await client.get("/api/admin/users?kind=seller", headers=auth_headers(cookies))).json()["items"]
    assert [i["account_id"] for i in by_kind] == [str(seller)]
    # A cursor that is not a timestamp is a 422, not the DataError-shaped 500 an unchecked
    # `%s::timestamptz` would give an attacker-supplied query string.
    bad = await client.get("/api/admin/users?cursor=yesterday", headers=auth_headers(cookies))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "BAD_CURSOR"


async def test_the_detail_view_carries_applications_grants_and_refuses_an_unknown_account(client, conn, member):
    aid, _ = await _applicant(client, member, email="detail@example.org")
    _admin, cookies, _hdr = member(("admin",), email="detail-admin@example.org")
    body = (await client.get(f"/api/admin/users/{aid}", headers=auth_headers(cookies))).json()
    assert body["account"]["email"] == "detail@example.org" and body["account"]["state"] == "pending"
    assert body["applications"][0]["kind"] == "buyer" and body["applications"][0]["fields"]["license_state"] == "TX"
    assert body["applications"][0]["submitted_at"] and body["applications"][0]["decided_at"] is None
    assert body["roles"] == [] and body["grants"] == []
    missing = await client.get(f"/api/admin/users/{uuid4()}", headers=auth_headers(cookies))
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND"


async def test_every_decision_transition_and_its_refusals(client, conn, member):
    """The transition table end to end: the refusals (`reinstate` from `pending`, an unknown
    action, an unknown account) and the rows the brief's own tests never reach — `reinstate`, and a
    seller decision, which leaves the account `active` and mails the seller template."""
    _sid, scookies, shdr = member(("staff",), email="staff@example.org")

    def decide(target, action, note=""):
        return client.post(f"/api/admin/users/{target}/decide", headers=auth_headers(scookies, shdr), json={"action": action, "note": note})

    aid, _ = await _applicant(client, member, email="transitions@example.org")
    assert (await decide(aid, "reinstate")).status_code == 409
    assert (await decide(aid, "elevate")).status_code == 422
    assert (await decide(uuid4(), "approve")).status_code == 404
    assert (await decide(aid, "decline", "Not eligible")).json()["state"] == "declined"
    assert (await decide(aid, "approve")).status_code == 409          # `declined` is not an approvable state

    bid, bcookies, bhdr = member(("buyer",), email="both@example.org")
    await client.post("/api/applications", headers=auth_headers(bcookies, bhdr), json={"kind": "seller", "fields": SELLER_FIELDS})
    assert (await decide(bid, "approve")).json() == {"state": "active", "roles": ["buyer", "seller"]}
    assert (await decide(bid, "suspend", "Complaint")).json()["state"] == "suspended"
    assert (await decide(bid, "reinstate")).json() == {"state": "active", "roles": ["buyer", "seller"]}
    with conn.cursor() as cur:
        cur.execute("SELECT template FROM email_outbox ORDER BY id")
        assert [x[0] for x in cur.fetchall()] == ["application_received", "application_declined",
                                                  "seller_application_received", "seller_application_approved", "account_suspended"]


async def test_a_seller_decision_never_moves_the_account_out_of_active(client, conn, member):
    """A seller applies from an account that is ALREADY `active`, so the account state is not the
    application's state machine: `request_info` and `decline` move the APPLICATION and leave the
    account (and its buyer role) exactly where they were."""
    _sid, scookies, shdr = member(("staff",), email="staff@example.org")
    bid, bcookies, bhdr = member(("buyer",), email="seller-decline@example.org")
    await client.post("/api/applications", headers=auth_headers(bcookies, bhdr), json={"kind": "seller", "fields": SELLER_FIELDS})
    info = await client.post(f"/api/admin/users/{bid}/decide", headers=auth_headers(scookies, shdr),
                             json={"action": "request_info", "note": "Send the deed"})
    assert info.json() == {"state": "active", "roles": ["buyer"]}
    r = await client.post(f"/api/admin/users/{bid}/decide", headers=auth_headers(scookies, shdr),
                          json={"action": "decline", "note": "Ownership unclear"})
    assert r.json() == {"state": "active", "roles": ["buyer"]}
    with conn.cursor() as cur:
        cur.execute("SELECT status, decision_note, info_request FROM application WHERE kind='seller'")
        assert cur.fetchone() == ("declined", "Ownership unclear", None)
        cur.execute("SELECT template FROM email_outbox ORDER BY id")
        assert [x[0] for x in cur.fetchall()] == ["seller_application_received", "application_info_requested", "seller_application_declined"]


async def test_a_decision_on_an_account_with_no_application_still_moves_the_state(client, conn, member):
    """Suspend and revoke are ACCOUNT actions, not application ones: there need be no application
    row at all, and `revoke` takes every grant with it."""
    _sid, scookies, shdr = member(("staff",), email="staff@example.org")
    mid, _c, _h = member(("buyer", "seller"), email="noapp@example.org")
    await client.post("/api/auth/reauth", headers=auth_headers(scookies, shdr), json={"password": PW})
    r = await client.post(f"/api/admin/users/{mid}/decide", headers=auth_headers(scookies, shdr),
                          json={"action": "revoke", "note": "Left the profession"})
    assert r.json() == {"state": "revoked", "roles": []}
    with conn.cursor() as cur:
        cur.execute("SELECT template FROM email_outbox"); assert [x[0] for x in cur.fetchall()] == ["account_revoked"]
        cur.execute("SELECT action, target_id, before, after FROM audit_log WHERE action='users.revoke'")
        action, target, before, after = cur.fetchone()
    assert (action, target, before, after) == ("users.revoke", str(mid), {"state": "active"}, {"state": "revoked", "roles": []})


async def test_grants_are_revocable_refuse_an_unknown_role_and_an_unknown_account(client, conn, member):
    _admin, cookies, hdr = member(("admin",), email="grants@example.org")
    mid, _c, _h = member(("buyer",), email="grantee@example.org")
    await client.post("/api/auth/reauth", headers=auth_headers(cookies, hdr), json={"password": PW})
    bad = await client.post(f"/api/admin/users/{mid}/grants", headers=auth_headers(cookies, hdr),
                            json={"role": "superadmin", "grant": True, "reason": "no such thing"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "BAD_ROLE"
    assert (await client.post(f"/api/admin/users/{uuid4()}/grants", headers=auth_headers(cookies, hdr),
                              json={"role": "staff", "grant": True, "reason": "nobody"})).status_code == 404
    granted = await client.post(f"/api/admin/users/{mid}/grants", headers=auth_headers(cookies, hdr),
                                json={"role": "staff", "grant": True, "reason": "New reviewer"})
    assert granted.json()["roles"] == ["buyer", "staff"]
    again = await client.post(f"/api/admin/users/{mid}/grants", headers=auth_headers(cookies, hdr),
                              json={"role": "staff", "grant": True, "reason": "New reviewer"})
    assert again.json()["roles"] == ["buyer", "staff"], "granting twice is idempotent"
    removed = await client.post(f"/api/admin/users/{mid}/grants", headers=auth_headers(cookies, hdr),
                                json={"role": "staff", "grant": False, "reason": "Moved teams"})
    assert removed.json()["roles"] == ["buyer"]
    with conn.cursor() as cur:
        cur.execute("SELECT before, after, reason FROM audit_log WHERE action='roles.grant' ORDER BY id")
        rows = cur.fetchall()
    assert rows[0] == ({"roles": ["buyer"]}, {"roles": ["buyer", "staff"]}, "New reviewer")
    assert rows[-1][1] == {"roles": ["buyer"]}


async def test_a_token_is_shown_once_bounded_in_days_revocable_and_audited(client, conn, member):
    _admin, cookies, hdr = member(("admin",), email="tokens@example.org")
    await client.post("/api/auth/reauth", headers=auth_headers(cookies, hdr), json={"password": PW})
    bad = await client.post("/api/admin/tokens", headers=auth_headers(cookies, hdr), json={"name": "x", "role": "root", "days": 30})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "BAD_ROLE"
    long = (await client.post("/api/admin/tokens", headers=auth_headers(cookies, hdr),
                              json={"name": "k6", "role": "buyer", "days": 4000})).json()["token"]
    short = (await client.post("/api/admin/tokens", headers=auth_headers(cookies, hdr),
                               json={"name": "k6", "role": "buyer", "days": -3})).json()["token"]
    long_id, short_id = long.split(".")[0][3:], short.split(".")[0][3:]
    with conn.cursor() as cur:
        cur.execute("SELECT id::text, expires_at < now() + interval '91 days', expires_at > now() FROM api_token")
        clamped = {row[0]: row[1:] for row in cur.fetchall()}
    assert clamped == {long_id: (True, True), short_id: (True, True)}, "days is clamped into 1..90"
    with conn.cursor() as cur:
        cur.execute("SELECT target_id, after FROM audit_log WHERE action='tokens.create' ORDER BY id")
        created = cur.fetchall()
        # The SECRET half of a minted token never reaches a table whose triggers refuse DELETE.
        secret = long.split(".", 1)[1]
        cur.execute("SELECT count(*) FROM audit_log WHERE coalesce(before::text,'') LIKE %s OR coalesce(after::text,'') LIKE %s OR coalesce(reason,'') LIKE %s",
                    (f"%{secret}%",) * 3)
        assert cur.fetchone()[0] == 0
    assert created[0] == (long_id, {"name": "k6", "role": "buyer", "days": 90})
    assert created[1][1]["days"] == 1
    assert (await client.post(f"/api/admin/tokens/{long_id}/revoke", headers=auth_headers(cookies, hdr))).status_code == 200
    assert (await client.post(f"/api/admin/tokens/{long_id}/revoke", headers=auth_headers(cookies, hdr))).status_code == 404
    assert (await client.post(f"/api/admin/tokens/{uuid4()}/revoke", headers=auth_headers(cookies, hdr))).status_code == 404
    assert (await client.get("/api/me", headers={"Authorization": f"Bearer {long}"})).status_code == 401


async def test_the_audit_endpoint_reads_the_trail_newest_first_and_bounds_its_limit(client, conn, member):
    aid, _ = await _applicant(client, member, email="audited@example.org")
    sid, scookies, _shdr = member(("staff",), email="staff@example.org")
    await client.get(f"/api/admin/users/{aid}", headers=auth_headers(scookies))
    rows = (await client.get("/api/admin/audit?limit=5000", headers=auth_headers(scookies))).json()
    assert rows[0]["action"] == "users.view_detail" and rows[0]["actor_id"] == str(sid) and rows[0]["target_id"] == str(aid)
    assert rows[0]["actor_role"] == "staff" and rows[0]["at"]
    assert len((await client.get("/api/admin/audit?limit=0", headers=auth_headers(scookies))).json()) == 1


async def test_the_legacy_operator_bearer_cannot_act_where_the_actor_must_name_an_account(client, conn, member):
    """`deps.LEGACY_ADMIN` is a synthetic id with no `account` row (the `API_SECRET_KEY` bearer,
    alive until Task I9), and `role_grant.granted_by`/`api_token.created_by` are foreign keys — so
    without a check its grant would be a 500 rather than a refusal. The legacy principal is `admin`
    and exempt from re-auth, so it really does reach these handlers."""
    from app.config import settings

    mid, _c, _h = member(("buyer",), email="legacy-target@example.org")
    bearer = {"Authorization": f"Bearer {settings.api_secret_key}"}
    r = await client.post(f"/api/admin/users/{mid}/grants", headers=bearer, json={"role": "staff", "grant": True, "reason": "x"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
    assert (await client.post("/api/admin/tokens", headers=bearer, json={"name": "k6", "role": "buyer", "days": 30})).status_code == 401
    aid, _ = await _applicant(client, member, email="legacy-approve@example.org")
    assert (await client.post(f"/api/admin/users/{aid}/decide", headers=bearer, json={"action": "approve", "note": ""})).status_code == 401
    # ...and it can still READ: the operator bearer is how an on-call engineer inspects the queue.
    assert (await client.get("/api/admin/users", headers=bearer)).status_code == 200


async def test_the_permissions_endpoint_publishes_the_matrix_reauth_and_audited_lists(client, conn, member):
    from app.auth import permissions as PM

    _sid, scookies, _shdr = member(("staff",), email="staff@example.org")
    body = (await client.get("/api/admin/permissions", headers=auth_headers(scookies))).json()
    assert body["roles"] == list(PM.ROLES)
    assert body["matrix"]["users.revoke"] == ["admin", "staff"]
    assert body["reauth"] == sorted(PM.REAUTH) and body["audited"] == sorted(PM.AUDITED)
    assert "users.revoke" in body["reauth"] and "users.revoke" in body["audited"]


# --- the CLIs ---


def _run_cli(module, argv):
    """`main(argv)` in THIS process, so pytest-cov sees the script's own lines — a subprocess's
    coverage is never reported back (the pattern `tests/auth/test_permissions.py` uses). Returns
    stdout."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main(argv)
    assert code == 0, out.getvalue()
    return out.getvalue()


async def test_bootstrap_admin_invite_sets_a_password_and_is_single_use(client, conn):
    """The other half of `scripts/bootstrap_admin.py`: `POST /api/auth/accept-invite` consumes the
    `invite` token, applies the PRIVILEGED password floor (the account already holds `admin`), and
    the account can then sign in. A second use of the same link fails."""
    from scripts import bootstrap_admin

    token = _run_cli(bootstrap_admin, ["--email", "founder@example.org"]).strip().split("token=")[1]
    weak = await client.post("/api/auth/accept-invite", json={"token": token, "password": SHORT_PW})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "PASSWORD_POLICY"
    r = await client.post("/api/auth/accept-invite", json={"token": token, "password": INVITE_PW})
    assert r.status_code == 200 and r.json() == {"status": "accepted"}
    signin = await client.post("/api/auth/signin", json={"email": "founder@example.org", "password": INVITE_PW})
    assert signin.status_code == 200 and signin.json()["role"] == "VIN Foundation admin"
    again = await client.post("/api/auth/accept-invite", json={"token": token, "password": INVITE_PW})
    assert again.status_code == 400 and again.json()["error"]["code"] == "TOKEN_INVALID"
    with conn.cursor() as cur:
        cur.execute("SELECT action, reason FROM audit_log WHERE action='admin.bootstrap'")
        assert cur.fetchone() == ("admin.bootstrap", "bootstrap_admin.py")
        cur.execute("SELECT count(*) FROM audit_log WHERE action='invite.accept'"); assert cur.fetchone()[0] == 1


async def test_an_expired_invite_link_is_refused(client, conn):
    from scripts import bootstrap_admin

    token = _run_cli(bootstrap_admin, ["--email", "expired@example.org"]).strip().split("token=")[1]
    with conn.cursor() as cur:
        cur.execute("UPDATE email_token SET expires_at = now() - interval '1 minute'")
    r = await client.post("/api/auth/accept-invite", json={"token": token, "password": INVITE_PW})
    assert r.status_code == 400 and r.json()["error"]["code"] == "TOKEN_INVALID"


def test_bootstrap_admin_is_idempotent_refuses_production_without_the_flag_and_is_audited(conn, capsys, monkeypatch):
    from app.config import settings
    from scripts import bootstrap_admin

    assert bootstrap_admin.INVITE_TTL == timedelta(hours=24)
    first = _run_cli(bootstrap_admin, ["--email", "Founder@Example.org"])
    second = _run_cli(bootstrap_admin, ["--email", "founder@example.org"])
    assert first != second and all("/accept-invite?token=" in link for link in (first, second))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM account WHERE email='founder@example.org'"); assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM role_grant WHERE role='admin' AND revoked_at IS NULL"); assert cur.fetchone()[0] == 1
        # F4: two rows, but only the newest is LIVE — issuing an invite retires the ones before it,
        # exactly as `POST /api/auth/password/forgot` retires an unused reset link.
        cur.execute("SELECT count(*) FROM email_token WHERE purpose='invite'"); assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM email_token WHERE purpose='invite' AND used_at IS NULL"); assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM audit_log WHERE action='admin.bootstrap'"); assert cur.fetchone()[0] == 2
        cur.execute("SELECT password_hash FROM account WHERE email='founder@example.org'")
        assert cur.fetchone() == (bootstrap_admin.NO_PASSWORD,), "never a default password — the invite link is the only way in"

    monkeypatch.setattr(settings, "environment", "production")
    assert bootstrap_admin.main(["--email", "founder@example.org"]) == 2
    assert "production" in capsys.readouterr().err
    assert _run_cli(bootstrap_admin, ["--email", "founder@example.org", "--production"]).startswith(settings.link_base_url)


def test_seed_persona_upserts_the_design_account_and_never_prints_its_password(conn, capsys, monkeypatch):
    from app.auth import passwords as P
    from app.config import settings
    from scripts import seed_persona

    monkeypatch.setenv("PERSONA_PASSWORD", INVITE_PW)
    printed = _run_cli(seed_persona, []) + _run_cli(seed_persona, [])          # idempotent
    assert INVITE_PW not in printed and seed_persona.DEFAULT_PASSWORD not in printed
    with conn.cursor() as cur:
        cur.execute("SELECT id, password_hash, display_name, affiliation_label, state FROM account WHERE email=%s", (seed_persona.PERSONA_EMAIL,))
        aid, hashed, name, affiliation, state = cur.fetchone()
        cur.execute("SELECT role FROM role_grant WHERE account_id=%s AND revoked_at IS NULL ORDER BY role", (aid,))
        assert [r[0] for r in cur.fetchall()] == ["admin", "buyer", "seller", "staff"]
        cur.execute("SELECT count(*), max(status) FROM application WHERE account_id=%s", (aid,))
        assert cur.fetchone() == (1, "approved")
    assert (name, affiliation, state) == ("Dr. Rachel Mendes", "StartUp Club", "active")
    assert P.verify(INVITE_PW, hashed)

    monkeypatch.delenv("PERSONA_PASSWORD")
    _run_cli(seed_persona, [])                                                 # falls back to the documented default
    with conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM account WHERE email=%s", (seed_persona.PERSONA_EMAIL,))
        assert P.verify(seed_persona.DEFAULT_PASSWORD, cur.fetchone()[0])
    monkeypatch.setattr(settings, "environment", "PRODUCTION")
    assert seed_persona.main([]) == 2
    assert "production" in capsys.readouterr().err


@pytest.mark.parametrize(("script", "argv"), [("bootstrap_admin", ["--email", "cli@example.org"]), ("seed_persona", [])])
def test_the_cli_entry_points_run_as___main__(conn, monkeypatch, script, argv):
    """`if __name__ == "__main__": raise SystemExit(main())` never executes on import, and a
    subprocess's coverage is not reported back to this process — the pattern
    `tests/auth/test_permissions.py` already uses for `python -m app.auth.permissions`."""
    monkeypatch.setattr(sys, "argv", [script, *argv])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / f"{script}.py"), run_name="__main__")
    assert exc.value.code == 0


# ============================ fix round 1 ============================


async def _reauth(client, cookies, hdr):
    assert (await client.post("/api/auth/reauth", headers=auth_headers(cookies, hdr), json={"password": PW})).status_code == 200


async def test_staff_cannot_decide_against_a_staff_or_admin_target_or_against_itself(client, conn, member):
    """F1 + F2. `users.decide`/`users.revoke` are both `{staff, admin}`, so before this guard any
    staff account could revoke every Admin in a loop — and `revoke` is terminal in the API, so
    recovery meant `bootstrap_admin.py` with production database credentials. Staff is the LEAST
    privileged administrative role; it must not be able to unseat the most privileged one."""
    sid, scookies, shdr = member(("staff",), email="staff@example.org")
    staff2, _c1, _h1 = member(("staff",), email="staff2@example.org")
    admin, acookies, ahdr = member(("admin",), email="admin@example.org")
    await _reauth(client, scookies, shdr)                    # so the refusals below are NOT REAUTH_REQUIRED

    async def staff_decides(target, action, note="because"):
        return await client.post(f"/api/admin/users/{target}/decide", headers=auth_headers(scookies, shdr),
                                 json={"action": action, "note": note})

    revoked = await staff_decides(admin, "revoke")
    assert (revoked.status_code, revoked.json()["error"]["code"]) == (403, "PRIVILEGED_TARGET")
    assert (await staff_decides(admin, "suspend")).status_code == 403
    assert (await staff_decides(staff2, "suspend")).status_code == 403
    mine = await staff_decides(sid, "suspend")
    assert (mine.status_code, mine.json()["error"]["code"]) == (403, "SELF_ACTION")
    assert (await staff_decides(sid, "revoke")).status_code == 403
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT state FROM account WHERE id IN (%s,%s,%s)", (admin, staff2, sid))
        assert cur.fetchall() == [("active",)], "no target row was touched"
        cur.execute("SELECT count(*) FROM role_grant WHERE revoked_at IS NULL"); assert cur.fetchone()[0] == 3
    # ...and the legitimate path stays open: an ADMIN may still suspend a staff member and revoke
    # another admin. The guard is about the actor's role, not about protecting a row for ever.
    await _reauth(client, acookies, ahdr)
    ok = await client.post(f"/api/admin/users/{staff2}/decide", headers=auth_headers(acookies, ahdr),
                           json={"action": "suspend", "note": "n"})
    assert ok.json()["state"] == "suspended"
    other, _c2, _h2 = member(("admin",), email="admin2@example.org")
    assert (await client.post(f"/api/admin/users/{other}/decide", headers=auth_headers(acookies, ahdr),
                              json={"action": "revoke", "note": "left"})).json() == {"state": "revoked", "roles": []}


async def test_an_admin_grant_is_never_removed_from_its_holder_or_from_the_last_admin(client, conn, member):
    """F5. Probed before the fix: a single admin could `grant=false` their own `admin` row and was
    then locked out of `roles.grant` for ever — zero admins, no in-app way back."""
    first, cookies, hdr = member(("admin",), email="first-admin@example.org")
    await _reauth(client, cookies, hdr)

    async def ungrant(target, role="admin"):
        return await client.post(f"/api/admin/users/{target}/grants", headers=auth_headers(cookies, hdr),
                                 json={"role": role, "grant": False, "reason": "fix round 1"})

    own = await ungrant(first)
    assert (own.status_code, own.json()["error"]["code"]) == (403, "LAST_ADMIN")
    second, _c, _h = member(("admin",), email="second-admin@example.org")
    own_again = await ungrant(first)
    assert own_again.status_code == 403, "your own admin grant is yours to keep even when another admin exists"
    assert (await ungrant(second)).json()["roles"] == [], "a SECOND admin may be ungranted by another admin"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM role_grant WHERE role='admin' AND revoked_at IS NULL")
        assert cur.fetchone()[0] == 1, "exactly one admin survives every refusal above"


def test_the_last_admin_guard_does_not_depend_on_the_actor_being_the_admin_removed(conn):
    """The other arm of the same rule, reached directly because it cannot be reached over HTTP
    today: `roles.grant` is admin-only, so an actor able to call it always holds a live admin grant
    of their own and the count can never be 1 for a target that is not them. The guard is defensive
    — it is what keeps the invariant true if `roles.grant` is ever widened — so it is tested where
    it lives rather than left as an unexercised claim."""
    from uuid import uuid4

    from app.api import admin_users as A
    from app.auth import passwords as P
    from app.auth import sessions as S

    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('only@example.org', %s, 'active') RETURNING id", (P.hash_password(PW),))
        only_admin = cur.fetchone()[0]
        cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'admin',%s)", (only_admin, only_admin))
        actor = S.Principal(uuid4(), "active", frozenset({"admin"}), None, "session", "h")
        with pytest.raises(A.LastAdmin):
            A._refuse_unsafe_target(cur, actor=actor, actor_account=actor.account_id, account_id=only_admin,
                                    self_forbidden=False, removing_admin=True)


async def test_the_cursor_walk_returns_every_account_when_created_at_ties(client, conn, member):
    """F3. `ORDER BY (created_at DESC, id DESC)` with a cursor carrying only `created_at` and the
    predicate `created_at < cursor` DROPPED every row sharing the last row's timestamp, and then
    reported `next_cursor: null` — the caller was told the list was complete. Probed before the
    fix: 3 of 6 accounts returned. That is a direct contradiction of John's binding condition, so
    the cursor is now the keyset `"<created_at>|<id>"`."""
    _admin, cookies, _hdr = member(("admin",), email="pager@example.org")
    with conn.cursor() as cur:
        # ONE statement, so `now()` — which is TRANSACTION time — is a single instant for all five.
        # (The `conn` fixture is autocommit, so a Python loop would give five distinct timestamps
        # and prove nothing.) A bulk import or a fixture loader produces exactly this shape.
        cur.execute("""INSERT INTO account (email, password_hash, state)
                       SELECT 'tie' || g || '@example.org', 'x', 'active' FROM generate_series(0, 4) AS g""")
        cur.execute("SELECT count(DISTINCT created_at) FROM account WHERE email LIKE 'tie%%'")
        assert cur.fetchone()[0] == 1, "the fixture must really produce tied timestamps"
        cur.execute("SELECT count(*) FROM account"); total = cur.fetchone()[0]

    seen, cursor, pages = [], None, 0
    while pages <= total + 1:
        query = "/api/admin/users?limit=1" + (f"&cursor={cursor}" if cursor else "")
        body = (await client.get(query, headers=auth_headers(cookies))).json()
        seen += [i["account_id"] for i in body["items"]]
        cursor, pages = body["next_cursor"], pages + 1
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == total == 6, f"the walk must yield every account exactly once, got {seen}"
    assert "|" in (await client.get("/api/admin/users?limit=1", headers=auth_headers(cookies))).json()["next_cursor"]


async def test_a_malformed_keyset_cursor_is_refused(client, conn, member):
    _admin, cookies, _hdr = member(("admin",), email="cursor@example.org")
    for bad in ("yesterday", "yesterday|nope", "2026-09-07T00:00:00Z", "2026-09-07T00:00:00Z|not-a-uuid", "|", "a|b|c"):
        r = await client.get(f"/api/admin/users?cursor={bad}", headers=auth_headers(cookies))
        assert (r.status_code, r.json()["error"]["code"]) == (422, "BAD_CURSOR"), bad


async def test_filters_outside_their_enums_are_refused_rather_than_answered_empty(client, conn, member):
    """F10. `?role=superadmin` used to return `200 {"items": []}` — a typo in the Admin Users tab
    read as "no such users" rather than "no such filter", and inconsistently with the same
    handler's `cursor=` and with `grants`/`tokens`."""
    _admin, cookies, _hdr = member(("admin",), email="filters@example.org")
    for query in ("role=superadmin", "state=nonsense", "kind=whatever", "role=admin'--", "state=", "role=anonymous"):
        r = await client.get(f"/api/admin/users?{query}", headers=auth_headers(cookies))
        assert (r.status_code, r.json()["error"]["code"]) == (422, "BAD_FILTER"), query
    for query in ("role=admin", "state=active", "kind=buyer", "state=pending&kind=buyer&role=staff"):
        assert (await client.get(f"/api/admin/users?{query}", headers=auth_headers(cookies))).status_code == 200, query


# ============================ Task I5b (John's ruling, 2026-09-07) ============================
#
# "i asked several times, Admin and Staff must be handled in wave 2a … must include Staff/Admin
# tokens." This reverses I5 fix round 1's F6, which had restricted `TOKEN_ROLES` to the member
# roles. What replaces that restriction is three safeguards, one test each below: the minter must
# already hold a privileged role to mint one, a token principal never satisfies a re-auth gate, and
# a token principal never holds `tokens.manage`.


@pytest.mark.parametrize("role", ["buyer", "seller", "staff", "admin"])
async def test_a_minted_token_may_carry_any_of_the_four_roles(client, conn, member, role):
    """Spec §Automation tokens, amended: an `api_token` carries "any one of the four roles"."""
    _admin, cookies, hdr = member(("admin", "staff"), email="tokens@example.org")
    await _reauth(client, cookies, hdr)
    r = await client.post("/api/admin/tokens", headers=auth_headers(cookies, hdr), json={"name": f"e2e-{role}", "role": role, "days": 30})
    assert r.status_code == 201 and r.json()["token"].startswith("pm_"), role
    with conn.cursor() as cur:
        cur.execute("SELECT role FROM api_token WHERE name=%s", (f"e2e-{role}",))
        assert cur.fetchone()[0] == role
        # The audit row records the ROLE, which is the whole point of allowing privileged ones.
        cur.execute("SELECT after FROM audit_log WHERE action='tokens.create' ORDER BY id DESC LIMIT 1")
        assert cur.fetchone()[0] == {"name": f"e2e-{role}", "role": role, "days": 30}
    bad = await client.post("/api/admin/tokens", headers=auth_headers(cookies, hdr), json={"name": "k6", "role": "superadmin", "days": 30})
    assert (bad.status_code, bad.json()["error"]["code"]) == (422, "BAD_ROLE")


async def test_a_privileged_token_is_minted_only_by_an_account_that_holds_that_role(client, conn, member):
    """No escalation (spec §Automation tokens): `tokens.manage` is admin-only, and an admin who
    does NOT hold `staff` cannot mint a `staff` token — `permissions.py` has no role lattice, only
    per-permission role sets, so holding admin is not holding staff. `buyer`/`seller` stay
    mintable by any token manager: they are automation roles strictly below the minter's own, and
    that is the behaviour every deploy/CI token has relied on since I5."""
    _admin, cookies, hdr = member(("admin",), email="admin-only@example.org")
    await _reauth(client, cookies, hdr)

    async def mint(role, name="e2e"):
        return await client.post("/api/admin/tokens", headers=auth_headers(cookies, hdr), json={"name": name, "role": role, "days": 30})

    refused = await mint("staff", name="e2e-staff")
    assert (refused.status_code, refused.json()["error"]["message"]) == (403, "you can only mint a token for a role you hold")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM api_token WHERE role='staff'"); assert cur.fetchone()[0] == 0
    assert (await mint("buyer")).status_code == 201
    assert (await mint("seller")).status_code == 201
    assert (await mint("admin")).status_code == 201, "the minter holds admin"
    # ...and the grant is what unlocks it, read from the grants table rather than from the session.
    assert (await client.post(f"/api/admin/users/{_admin}/grants", headers=auth_headers(cookies, hdr),
                              json={"role": "staff", "grant": True, "reason": "reviews the queue too"})).status_code == 200
    assert (await mint("staff", name="e2e-staff")).status_code == 201


async def test_an_api_token_never_manages_tokens_whatever_role_it_carries(client, conn, member):
    """The first of the two token exceptions: a token principal's permissions are its role's minus
    `tokens.manage`, so a leaked admin token cannot mint another token or revoke one — and it says
    so, rather than answering the generic "your account cannot do this"."""
    _admin, cookies, hdr = member(("admin",), email="tokens-mgr@example.org")
    await _reauth(client, cookies, hdr)
    minted = await client.post("/api/admin/tokens", headers=auth_headers(cookies, hdr), json={"name": "e2e-admin", "role": "admin", "days": 30})
    raw = minted.json()["token"]
    bearer = {"Authorization": f"Bearer {raw}"}
    # Everything else the role carries is intact...
    assert (await client.get("/api/admin/users", headers=bearer)).status_code == 200
    r = await client.post("/api/admin/tokens", headers=bearer, json={"name": "second", "role": "buyer", "days": 30})
    assert (r.status_code, r.json()["error"]["message"]) == (403, "api tokens cannot manage tokens")
    revoke = await client.post(f"/api/admin/tokens/{raw.split('.')[0][3:]}/revoke", headers=bearer)
    assert (revoke.status_code, revoke.json()["error"]["message"]) == (403, "api tokens cannot manage tokens")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM api_token WHERE name='second'"); assert cur.fetchone()[0] == 0


async def test_an_api_token_never_satisfies_a_reauth_gate(client, conn, member):
    """The second exception, and the one that makes a standing staff/admin bearer survivable: a
    token has no password to confirm, so every REAUTH action — Revoke, role grants, licence
    decisions, engine activation, token creation — is out of its reach, with a message an
    automation author can act on instead of the ordinary "Confirm your password to continue."
    """
    _admin, cookies, hdr = member(("admin", "staff"), email="tokens-reauth@example.org")
    await _reauth(client, cookies, hdr)

    async def mint(role):
        r = await client.post("/api/admin/tokens", headers=auth_headers(cookies, hdr), json={"name": f"e2e-{role}", "role": role, "days": 30})
        return {"Authorization": f"Bearer {r.json()['token']}"}

    staff_bearer, admin_bearer = await mint("staff"), await mint("admin")
    target, _cookies = await _applicant(client, member, email="reauth-target@example.org")
    # A staff decision that is NOT in REAUTH still works from a token — the exception is narrow.
    assert (await client.post(f"/api/admin/users/{target}/decide", headers=staff_bearer,
                              json={"action": "request_info", "note": "which practice?"})).status_code == 200
    revoke = await client.post(f"/api/admin/users/{target}/decide", headers=staff_bearer, json={"action": "revoke", "note": "no"})
    assert (revoke.status_code, revoke.json()["error"]["message"]) == (
        403, "this action needs a re-authenticated session — api tokens cannot re-authenticate")
    grant = await client.post(f"/api/admin/users/{target}/grants", headers=admin_bearer, json={"role": "staff", "grant": True, "reason": "no"})
    assert (grant.status_code, grant.json()["error"]["message"]) == (
        403, "this action needs a re-authenticated session — api tokens cannot re-authenticate")
    with conn.cursor() as cur:
        cur.execute("SELECT state FROM account WHERE id=%s", (target,)); assert cur.fetchone()[0] == "needs_review"
        cur.execute("SELECT count(*) FROM role_grant WHERE account_id=%s AND role='staff'", (target,)); assert cur.fetchone()[0] == 0


async def test_accept_invite_sets_the_password_without_creating_a_session(client, conn):
    """F7 (John, 2026-09-07): `accept-invite` keeps `password/reset`'s shape — it sets the password
    and the new admin then signs in. No `Set-Cookie`, so a link forwarded through a chat window
    cannot hand somebody a live session by being opened."""
    from scripts import bootstrap_admin

    token = _run_cli(bootstrap_admin, ["--email", "nosession@example.org"]).strip().split("token=")[1]
    r = await client.post("/api/auth/accept-invite", json={"token": token, "password": INVITE_PW})
    assert r.status_code == 200 and r.headers.get_list("set-cookie") == [] and len(r.cookies) == 0
    assert (await client.post("/api/auth/signin", json={"email": "nosession@example.org", "password": INVITE_PW})).status_code == 200


async def test_issuing_an_invite_retires_the_ones_before_it(client, conn):
    """F4. `POST /api/auth/password/forgot` sets the precedent three files away: one live link per
    account. Probed before the fix: invite #1 was accepted and a password set, and invite #2 — a
    link printed to a terminal or a CI log 23 hours earlier — then reset that password again."""
    from scripts import bootstrap_admin

    first = _run_cli(bootstrap_admin, ["--email", "retire@example.org"]).strip().split("token=")[1]
    second = _run_cli(bootstrap_admin, ["--email", "retire@example.org"]).strip().split("token=")[1]
    assert first != second
    stale = await client.post("/api/auth/accept-invite", json={"token": first, "password": INVITE_PW})
    assert (stale.status_code, stale.json()["error"]["code"]) == (400, "TOKEN_INVALID")
    assert (await client.post("/api/auth/accept-invite", json={"token": second, "password": INVITE_PW})).status_code == 200


def test_bootstrap_admin_refuses_a_declined_suspended_or_revoked_account_without_reactivate(conn, capsys):
    """F8. `ON CONFLICT (email) DO UPDATE SET state='active'` applies to ANY existing address, so
    the script would silently undo a staff decision that has an audit trail behind it — and print a
    link that sets that account's password. Both outcomes are audited.

    `declined` is in the list for the same reason `suspended` and `revoked` are (re-review
    observation 1, 2026-09-07): all three are the recorded outcome of a staff decision, and a
    declined applicant's address bootstrapped to `active` with an `admin` grant is the loudest
    version of exactly that. Every state in `BLOCKED_STATES` is covered here, so adding one
    without a test is not possible."""
    from scripts import bootstrap_admin

    assert bootstrap_admin.BLOCKED_STATES == ("declined", "suspended", "revoked")
    for state in bootstrap_admin.BLOCKED_STATES:
        email = f"{state}@example.org"
        with conn.cursor() as cur:
            cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'x',%s) RETURNING id", (email, state))
            aid = cur.fetchone()[0]
        assert bootstrap_admin.main(["--email", email]) == 3
        err = capsys.readouterr().err
        assert state in err and "--reactivate" in err
        with conn.cursor() as cur:
            cur.execute("SELECT state FROM account WHERE id=%s", (aid,)); assert cur.fetchone() == (state,)
            cur.execute("SELECT count(*) FROM email_token WHERE account_id=%s", (aid,)); assert cur.fetchone()[0] == 0
            cur.execute("SELECT reason FROM audit_log WHERE action='admin.bootstrap.refused' AND target_id=%s", (str(aid),))
            assert state in cur.fetchone()[0]

        assert _run_cli(bootstrap_admin, ["--email", email, "--reactivate"]).startswith("https://")
        with conn.cursor() as cur:
            cur.execute("SELECT state FROM account WHERE id=%s", (aid,)); assert cur.fetchone() == ("active",)
            cur.execute("SELECT reason FROM audit_log WHERE action='admin.bootstrap' AND target_id=%s", (str(aid),))
            assert "--reactivate" in cur.fetchone()[0]


def test_issue_api_token_returns_the_id_beside_the_raw_value(conn):
    """N5. `create_token` derived the audit `target_id` with `raw.split(".", 1)[0][3:]`, hard-coding
    the `pm_` prefix length in a second place."""
    from datetime import timedelta

    from app.auth import tokens as T

    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('n5@example.org','x','active') RETURNING id")
        aid = cur.fetchone()[0]
    issued = T.issue_api_token(conn, name="k6", role="buyer", created_by=aid, ttl=timedelta(days=1))
    assert issued.raw == f"pm_{issued.token_id}.{issued.raw.split('.', 1)[1]}"
    assert T.parse(issued.raw) == (issued.token_id, issued.raw.split(".", 1)[1])
    assert T.verify_api_token(conn, issued.raw).token_id == issued.token_id


# ============================ fix round 2 ============================


def _admin_pair(conn, suffix=""):
    """Two accounts, each holding a live `admin` grant."""
    from app.auth import passwords as P

    ids = []
    for name in ("alpha", "beta"):
        with conn.cursor() as cur:
            cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,%s,'active') RETURNING id",
                        (f"{name}{suffix}@example.org", P.hash_password(PW)))
            aid = cur.fetchone()[0]
            cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'admin',%s)", (aid, aid))
        ids.append(aid)
    return ids


def _live_admins(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM role_grant WHERE role='admin' AND revoked_at IS NULL")
        return cur.fetchone()[0]


def _concurrent_removal(dsn, actor_account, target, barrier, results, *, via):
    """One admin-grant mutation in its own READ COMMITTED transaction on its own connection,
    replaying the statement sequence of the endpoint named by `via` around the SHARED guard:

    * `grants` — lock the target account row, guard, revoke that one `admin` grant;
    * `decide`  — lock the target account row, guard (with the self-check `revoke` carries),
                  revoke EVERY grant and move the account to `revoked`.
    """
    import psycopg2

    from app.api import admin_users as A
    from app.auth import sessions as S

    actor = S.Principal(actor_account, "active", frozenset({"admin"}), None, "session", "h")
    connection = psycopg2.connect(dsn)   # NOT autocommit: `with connection:` is one real transaction
    try:
        with connection, connection.cursor() as cur:
            cur.execute("SELECT 1 FROM account WHERE id=%s FOR UPDATE", (target,))
            barrier.wait(timeout=30)     # both transactions are open before either reaches the guard
            A._refuse_unsafe_target(cur, actor=actor, actor_account=actor_account, account_id=target,
                                    self_forbidden=via == "decide", removing_admin=True)
            if via == "decide":
                cur.execute("UPDATE role_grant SET revoked_at=now() WHERE account_id=%s AND revoked_at IS NULL", (target,))
                cur.execute("UPDATE account SET state='revoked' WHERE id=%s", (target,))
            else:
                cur.execute("UPDATE role_grant SET revoked_at=now() WHERE account_id=%s AND role='admin' AND revoked_at IS NULL",
                            (target,))
        results.append("removed")
    except A.LastAdmin:
        results.append("refused")
    finally:
        connection.close()


def _race(conn, scratch_dsn, via):
    """Three rounds with a fresh pair of admins each: under the bug the outcome is timing-dependent
    and one round could pass by luck.

    Every round starts from a deployment whose ONLY admins are the pair — the scenario NEW-1
    describes. Without that reset, a survivor from the previous round makes both removals
    legitimate (three admins, two go, one remains), and the test would fail for a reason that is
    not the bug."""
    import threading

    for round_number in range(3):
        with conn.cursor() as cur:
            cur.execute("UPDATE role_grant SET revoked_at=now() WHERE role='admin' AND revoked_at IS NULL")
        alpha, beta = _admin_pair(conn, suffix=f"-{via}-{round_number}")
        assert _live_admins(conn) == 2, "the pair must be the whole admin population for this round"
        barrier, results = threading.Barrier(2), []
        threads = [threading.Thread(target=_concurrent_removal, args=(scratch_dsn, alpha, beta, barrier, results), kwargs={"via": via}),
                   threading.Thread(target=_concurrent_removal, args=(scratch_dsn, beta, alpha, barrier, results), kwargs={"via": via})]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            assert not thread.is_alive(), "a thread never finished — the serialisation must not deadlock"
        assert sorted(results) == ["refused", "removed"], f"{via} round {round_number}: exactly one may win, got {results}"
        assert _live_admins(conn) == 1, f"{via} round {round_number}: one admin of the pair must survive"


def test_two_admins_ungranting_each_other_concurrently_cannot_reach_zero(conn, scratch_dsn):
    """NEW-1. Rule 3 counted live admin grants with no lock over `role_grant`, and `grants()`'s only
    lock is `FOR UPDATE` on the TARGET account row — so two admins ungranting *each other* lock
    different rows, nothing serialises them, both see `count = 2`, and both commit. Demonstrated in
    the re-review on a scratch database: **0 live admin grants afterwards** — precisely the state
    rule 3 exists to prevent, with recovery meaning `bootstrap_admin.py` and production database
    credentials again.

    One event loop cannot produce this on its own (these handlers do blocking psycopg2 work, so two
    in-process requests serialise), but Railway runs replicas: two containers, two admins, one
    instant. So the race is driven here the way it happens in production — two connections, two
    threads, each replaying the endpoint's own statement sequence through the real shared guard."""
    _race(conn, scratch_dsn, via="grants")


def test_two_admins_revoking_each_other_concurrently_cannot_reach_zero(conn, scratch_dsn):
    """NEW-1's other half, named in the same paragraph of the re-review: "The same shape reaches
    `decide`'s `revoke`, which strips grants and has no count at all." `revoke` passed
    `removing_admin=False`, so two admins revoking each other raced to zero by exactly the route
    above with nothing to serialise and no count to lose. Revoking an account that holds `admin`
    now goes through rule 3 like any other removal of an admin grant."""
    _race(conn, scratch_dsn, via="decide")


def _decide_in_its_own_loop(dist, cookies, hdr, target, result):
    """One `POST /api/admin/users/<target>/decide {"revoke"}` on its OWN event loop, in this
    thread, against the real app. A separate loop because these handlers do blocking psycopg2 work:
    a request that waits on a Postgres lock blocks the whole loop it runs on, so it cannot share
    one with the test that is holding that lock."""
    import asyncio

    import httpx
    from httpx import ASGITransport

    from app.main import create_app

    async def go():
        async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url=ORIGIN) as c:
            return await c.post(f"/api/admin/users/{target}/decide", headers=auth_headers(cookies, hdr),
                                json={"action": "revoke", "note": "fix round 2"})

    result["response"] = asyncio.run(go())


def test_revoking_an_admin_waits_on_the_admin_grant_lock_and_an_ordinary_member_does_not(
    conn, scratch_dsn, dist, member,
):
    """`decide`'s call site, pinned where it is observable. No single request can reach rule 3's
    refusal through `revoke` (rule 2 stops self-revoke, rule 1 stops a staff actor reaching an
    admin), so what the call site changes is whether the request SERIALISES — and that is visible
    by holding the lock from another connection and watching the request wait for it.

    Both requests run in their own thread, on their own event loop. Not for symmetry: these
    handlers do blocking psycopg2 work, so a request that waits on a Postgres lock blocks the whole
    loop it is on, and `asyncio.wait_for` cannot time it out — the timer never gets to run. A
    regression that took the lock for EVERY revoke would deadlock the suite outright if the
    ordinary-member request shared this thread; in its own thread it is a `join(timeout=...)` and a
    plain assertion instead."""
    import threading

    import psycopg2

    from app.api import admin_users as A

    _admin, cookies, hdr = member(("admin",), email="locker@example.org")
    victim, _cv, _hv = member(("admin",), email="victim-admin@example.org")
    ordinary, _co, _ho = member(("buyer",), email="plain-member@example.org")
    with conn.cursor() as cur:   # the acting admin has re-authenticated (`users.revoke` is in REAUTH)
        cur.execute("UPDATE session SET reauth_at = now() WHERE account_id = %s", (_admin,))
    from app.cache import sync_redis
    sync_redis().flushall()      # ...so the cached principal is re-read with that stamp

    plain_result: dict[str, Any] = {}
    admin_result: dict[str, Any] = {}
    plain_thread = threading.Thread(target=_decide_in_its_own_loop, args=(dist, cookies, hdr, ordinary, plain_result))
    admin_thread = threading.Thread(target=_decide_in_its_own_loop, args=(dist, cookies, hdr, victim, admin_result))
    blocker = psycopg2.connect(scratch_dsn)          # NOT autocommit: the lock is held until commit
    try:
        with blocker, blocker.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (A.ADMIN_GRANT_LOCK,))
            # An ordinary member is revoked straight through: that path never asks for the lock.
            plain_thread.start()
            plain_thread.join(timeout=30)
            assert not plain_thread.is_alive(), "revoking an account with no admin grant must not queue behind the lock"
            assert plain_result["response"].json() == {"state": "revoked", "roles": []}
            # An ADMIN target must wait.
            admin_thread.start()
            admin_thread.join(timeout=2)
            assert admin_thread.is_alive(), "revoking an admin must wait on the admin-grant lock"
            assert "response" not in admin_result
        # ...and completes as soon as the lock is released by the commit above.
        admin_thread.join(timeout=60)
        assert not admin_thread.is_alive(), "the revoke must proceed once the lock is free"
    finally:
        blocker.close()
        for thread in (plain_thread, admin_thread):
            if thread.is_alive():
                thread.join(timeout=60)
    assert admin_result["response"].json() == {"state": "revoked", "roles": []}
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM role_grant WHERE role='admin' AND revoked_at IS NULL")
        assert cur.fetchone()[0] == 1, "the acting admin survives; the victim's grant is gone"


async def test_the_admin_floor_does_not_fire_when_the_revoked_account_holds_no_admin(client, conn, member):
    """The other side of that change, and what stops it being over-broad: rule 3 is about ADMIN
    grants, not about `revoke`. An ordinary member is revoked exactly as before — including when
    the acting staff member is the only administrative account in the deployment, where a naive
    `removing_admin=True` for every revoke would have refused with `LAST_ADMIN`."""
    _sid, scookies, shdr = member(("staff",), email="lone-staff@example.org")
    ordinary, _c, _h = member(("buyer", "seller"), email="ordinary@example.org")
    await _reauth(client, scookies, shdr)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM role_grant WHERE role='admin' AND revoked_at IS NULL")
        assert cur.fetchone()[0] == 0, "there is no admin at all: the floor must not read as 'the last one'"
    r = await client.post(f"/api/admin/users/{ordinary}/decide", headers=auth_headers(scookies, shdr),
                          json={"action": "revoke", "note": "fix round 2"})
    assert r.json() == {"state": "revoked", "roles": []}


def test_no_dead_dependency_aliases_remain(client):
    """NEW-2. `Reviewer` outlived its only consumer when C2 moved `list_users` to a route-level
    `dependencies=[...]`, and ruff does not flag an unused module-level assignment — so it read as
    though a route still used it. Every alias this module exports must be reachable from a route."""
    import inspect

    from app.api import admin_users as A

    aliases = [name for name, value in vars(A).items()
               if name[0].isupper() and getattr(value, "__module__", "") == "typing" and "Depends" in repr(value)]
    source = inspect.getsource(A)
    for alias in aliases:
        assert source.count(f": {alias}") >= 1, f"{alias} is defined but no route parameter uses it"
    assert "Reviewer" not in aliases and "DetailViewer" in aliases
