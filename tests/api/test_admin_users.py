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
from uuid import uuid4

import pytest

from tests.api.conftest import PW, auth_headers

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
        cur.execute("SELECT action, actor_id::text, target_id FROM audit_log WHERE action='users.view'")
        assert cur.fetchone() == ("users.view", str(sid), str(aid))
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
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log WHERE action='users.list'"); assert cur.fetchone()[0] == 3


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
    assert rows[0]["action"] == "users.view" and rows[0]["actor_id"] == str(sid) and rows[0]["target_id"] == str(aid)
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
        cur.execute("SELECT count(*) FROM email_token WHERE purpose='invite'"); assert cur.fetchone()[0] == 2
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
