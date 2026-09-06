import time

from app.auth import passwords as P
from app.auth import sessions as S
from app.cache import sync_redis as redis_of
from app.config import settings
from app.mail.outbox import enqueue
from tests.api.conftest import PW, auth_headers


async def _outbox(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_email, template, params, status FROM email_outbox ORDER BY id"); return cur.fetchall()


async def test_signup_is_uniform_and_queues_one_verify_email(client, conn):
    r1 = await client.post("/api/auth/signup", json={"email": "New.Person@Gmail.com", "password": PW})
    r2 = await client.post("/api/auth/signup", json={"email": "new.person@gmail.com", "password": PW})    # existing → same answer
    assert r1.status_code == r2.status_code == 202 and r1.json() == r2.json() == {"status": "check_email"}
    rows = await _outbox(conn)
    assert len(rows) == 1 and rows[0][0] == "New.Person@Gmail.com" and rows[0][1] == "verify_email" and rows[0][2]["link"].startswith("https://qa.foundation.vin/verify?token=")
    with conn.cursor() as cur:
        cur.execute("SELECT state FROM account WHERE email='new.person@gmail.com'"); assert cur.fetchone() == ("unverified",)


async def test_signup_rejects_weak_passwords_with_the_policy_message(client):
    r = await client.post("/api/auth/signup", json={"email": "a@b.co", "password": "password12345"})
    assert r.status_code == 422 and "stronger" in r.json()["error"]["message"]


async def test_verify_is_single_use_and_moves_state(client, conn):
    await client.post("/api/auth/signup", json={"email": "v@b.co", "password": PW})
    with conn.cursor() as cur:
        cur.execute("SELECT params->>'link' FROM email_outbox"); token = cur.fetchone()[0].split("token=")[1]
    assert (await client.post("/api/auth/verify", json={"token": token})).status_code == 200
    assert (await client.post("/api/auth/verify", json={"token": token})).status_code == 400
    with conn.cursor() as cur:
        cur.execute("SELECT state FROM account WHERE email='v@b.co'"); assert cur.fetchone() == ("verified",)


async def test_signin_sets_cookies_and_me_returns_the_design_shape(client, member):
    aid, _cookies, _hdr = member(("buyer",), affiliation="StartUp Club")
    r = await client.post("/api/auth/signin", json={"email": "buyer-active@example.org", "password": PW})
    assert r.status_code == 200
    sc = r.headers.get_list("set-cookie")
    # `"samesite=lax"`, not the brief's `"SameSite=lax" in c.lower()`: that needle keeps its capitals
    # while the haystack is lowered, so it can never match ANY implementation. Starlette writes
    # `pm_session=...; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax; Secure` (probed 2026-09-06).
    assert any(c.startswith("pm_session=") and "HttpOnly" in c and "Secure" in c and "samesite=lax" in c.lower() for c in sc)
    assert any(c.startswith("pm_csrf=") and "HttpOnly" not in c for c in sc)
    me = (await client.get("/api/me")).json()
    assert me == {"id": str(aid), "email": "buyer-active@example.org", "name": "Dr. Rachel Mendes", "role": "Approved buyer · StartUp Club", "initials": "RM",
                  "state": "active", "roles": ["buyer"], "affiliation_label": "StartUp Club"}


async def test_signin_failures_are_generic_for_wrong_unknown_suspended_and_revoked(client, member):
    member(("buyer",), state="suspended", email="s@example.org"); member(("buyer",), state="revoked", email="r@example.org")
    bodies = set(); times = []
    for email, pw in [("buyer-active@example.org", "wrong-password-xx"), ("nobody@example.org", PW), ("s@example.org", PW), ("r@example.org", PW)]:
        t0 = time.perf_counter(); r = await client.post("/api/auth/signin", json={"email": email, "password": pw}); times.append(time.perf_counter() - t0)
        assert r.status_code == 401; bodies.add(r.text)
    assert len(bodies) == 1 and "Email or password is incorrect" in bodies.pop()
    assert max(times) - min(times) < 0.02 * 5    # equal hash work (generous factor for CI jitter)


async def test_lockout_after_ten_failures_per_email(client, member):
    member(("buyer",), email="lock@example.org")
    for _ in range(10):
        assert (await client.post("/api/auth/signin", json={"email": "lock@example.org", "password": "bad-bad-bad-bad"})).status_code == 401
    r = await client.post("/api/auth/signin", json={"email": "lock@example.org", "password": PW})
    assert r.status_code == 429 and "retry-after" in r.headers


async def test_signout_all_revokes_on_next_request(client, member):
    _aid, cookies, hdr = member()
    assert (await client.get("/api/me", headers=auth_headers(cookies))).status_code == 200
    assert (await client.post("/api/auth/signout-all", headers=auth_headers(cookies, hdr))).status_code == 200
    assert (await client.get("/api/me", headers=auth_headers(cookies))).status_code == 401


async def test_forgot_and_reset_are_uniform_single_use_and_revoke_sessions(client, conn, member):
    _aid, cookies, _hdr = member(email="f@example.org")
    a = await client.post("/api/auth/password/forgot", json={"email": "f@example.org"})
    b = await client.post("/api/auth/password/forgot", json={"email": "unknown@example.org"})
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    rows = await _outbox(conn); assert [r[1] for r in rows] == ["password_reset"]
    token = rows[0][2]["link"].split("token=")[1]
    assert (await client.post("/api/auth/password/reset", json={"token": token, "password": "another-quiet-lantern-77"})).status_code == 200
    assert (await client.get("/api/me", headers=auth_headers(cookies))).status_code == 401
    assert (await client.post("/api/auth/signin", json={"email": "f@example.org", "password": "another-quiet-lantern-77"})).status_code == 200


async def test_change_password_requires_current_and_reauth_endpoint_marks_session(client, conn, member):
    aid, cookies, hdr = member()
    assert (await client.post("/api/auth/password/change", headers=auth_headers(cookies, hdr), json={"current": "nope-nope-nope-1", "new": "another-quiet-lantern-77"})).status_code == 401
    assert (await client.post("/api/auth/reauth", headers=auth_headers(cookies, hdr), json={"password": PW})).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM session WHERE account_id=%s AND reauth_at IS NOT NULL", (aid,)); assert cur.fetchone()[0] == 1


async def test_security_headers_on_every_response_and_no_state_change_on_get(client):
    r = await client.get("/api/healthz")
    assert r.headers["strict-transport-security"].startswith("max-age=31536000") and r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["x-frame-options"] == "DENY"
    from app.main import app
    for route in app.routes:
        methods = getattr(route, "methods", set()) or set()
        if "GET" in methods:
            assert not getattr(route, "path", "").endswith(("/signin", "/signout", "/decide", "/activate", "/license", "/reset", "/verify"))


# --- supplemental (not in the brief's Step 1 — added for 100 % branch coverage of app/api/auth.py,
# and for the contracts Task I6 will build on) ---

BREACHED = "011151zangetsu"   # in the bundled NCSC top-100k list AND long/strong enough to clear the policy
NEW_PW = "another-quiet-lantern-77"
LEGACY = {"Authorization": f"Bearer {settings.api_secret_key}"}


async def test_signup_refuses_an_address_that_is_not_one(client):
    r = await client.post("/api/auth/signup", json={"email": "not-an-address", "password": PW})
    assert r.status_code == 422 and r.json() == {"error": {"code": "EMAIL_INVALID", "message": "Enter a valid email address."}}


async def test_signup_refuses_a_password_that_has_appeared_in_a_breach(client):
    """The screen is real with the network off: `hibp_enabled=False` falls back to the bundled
    offline list, and this password clears the length and zxcvbn floors, so only the breach check
    can be what refuses it."""
    r = await client.post("/api/auth/signup", json={"email": "breach@example.org", "password": BREACHED})
    assert r.status_code == 422 and "data breach" in r.json()["error"]["message"]


async def test_a_new_account_can_verify_sign_in_and_read_its_own_profile(client, conn):
    """Sign-up leaves `display_name` and `affiliation_label` unset until the application is filled
    in, so `/api/me` answers with the design's fallbacks — an empty name, "?" initials, "Applicant"."""
    await client.post("/api/auth/signup", json={"email": "fresh@example.org", "password": PW})
    with conn.cursor() as cur:
        cur.execute("SELECT params->>'link' FROM email_outbox"); token = cur.fetchone()[0].split("token=")[1]
    assert (await client.post("/api/auth/verify", json={"token": token})).status_code == 200
    assert (await client.post("/api/auth/signin", json={"email": "fresh@example.org", "password": PW})).status_code == 200
    me = (await client.get("/api/me")).json()
    assert me["email"] == "fresh@example.org" and me["name"] == "" and me["initials"] == "?"
    assert me["role"] == "Applicant" and me["state"] == "verified" and me["roles"] == [] and me["affiliation_label"] is None


async def test_signin_rehashes_a_password_stored_with_weaker_parameters(client, conn, redis):
    """Argon2id parameters are read back out of the stored hash, so a password hashed under older,
    cheaper settings still verifies — and must be upgraded in place on the one request that has the
    plaintext to do it with."""
    from argon2 import PasswordHasher

    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1, hash_len=32, salt_len=16).hash(PW)
    assert P.needs_rehash(weak)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('old@example.org',%s,'active')", (weak,))
    assert (await client.post("/api/auth/signin", json={"email": "old@example.org", "password": PW})).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM account WHERE email='old@example.org'"); stored = cur.fetchone()[0]
    assert stored != weak and not P.needs_rehash(stored)


async def test_signout_ends_this_session_only(client, conn, member):
    aid, cookies, hdr = member()
    other = S.create(conn, redis_of(), aid, "203.0.113.6", "pytest")
    assert (await client.post("/api/auth/signout", headers=auth_headers(cookies, hdr))).status_code == 200
    assert (await client.get("/api/me", headers=auth_headers(cookies))).status_code == 401
    assert (await client.get("/api/me", headers=auth_headers({"pm_session": other}))).status_code == 200


async def test_signout_with_a_credential_that_carries_no_session_still_answers(client, conn):
    """The legacy operator bearer passes `account.self` but presents no `pm_session` cookie: there is
    nothing to revoke, and indexing the cookie (as the brief's Step 3 code did) was a 500."""
    r = await client.post("/api/auth/signout", headers=LEGACY)
    assert r.status_code == 200 and r.json() == {"status": "signed_out"}


async def test_a_credential_with_no_account_row_can_neither_change_nor_confirm_a_password(client, conn):
    """`deps.LEGACY_ADMIN` is a synthetic id with no `account` row. Both credential paths must answer
    the generic 401 rather than reading `[0]` off a missing row."""
    for path, body in (("/api/auth/password/change", {"current": PW, "new": NEW_PW}), ("/api/auth/reauth", {"password": PW})):
        r = await client.post(path, headers=LEGACY, json=body)
        assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS", path


async def test_password_reset_refuses_an_unknown_token(client, conn):
    r = await client.post("/api/auth/password/reset", json={"token": "not-a-token", "password": NEW_PW})
    assert r.status_code == 400 and r.json() == {"error": {"code": "TOKEN_INVALID", "message": "This link is invalid or has expired."}}


async def test_reauth_refuses_a_wrong_password(client, conn, member):
    aid, cookies, hdr = member()
    r = await client.post("/api/auth/reauth", headers=auth_headers(cookies, hdr), json={"password": "not-the-one-42"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM session WHERE account_id=%s AND reauth_at IS NOT NULL", (aid,)); assert cur.fetchone()[0] == 0


async def test_password_change_rotates_the_session_notifies_and_logs_nothing_about_the_password(client, conn, member):
    aid, cookies, hdr = member()
    r = await client.post("/api/auth/password/change", headers=auth_headers(cookies, hdr), json={"current": PW, "new": NEW_PW})
    assert r.status_code == 200 and r.json() == {"status": "changed"}
    assert any(c.startswith("pm_session=") for c in r.headers.get_list("set-cookie"))   # this session is re-issued...
    assert (await client.get("/api/me", headers=auth_headers(cookies))).status_code == 401   # ...and the old one is gone
    assert (await client.post("/api/auth/signin", json={"email": "buyer-active@example.org", "password": NEW_PW})).status_code == 200
    assert [row[1] for row in await _outbox(conn)] == ["password_changed"]
    with conn.cursor() as cur:
        cur.execute("SELECT action, actor_id, before, after, reason FROM audit_log"); rows = cur.fetchall()
    assert rows == [("password.change", aid, None, None, None)]


async def test_a_failure_burst_is_audited_once_without_the_attempted_password(client, conn, member):
    member(email="burst@example.org")
    for _ in range(6):
        assert (await client.post("/api/auth/signin", json={"email": "burst@example.org", "password": "wrong-wrong-wrong"})).status_code == 401
    with conn.cursor() as cur:
        cur.execute("SELECT action, target_id, before, after, reason FROM audit_log")
        assert cur.fetchall() == [("signin.failure_burst", "burst@example.org", None, None, None)]


def test_enqueue_is_idempotent_on_its_key(conn):
    """The contract Task I6's sender relies on: the same key writes exactly one row, whichever
    request path re-derives it."""
    assert enqueue(conn, to="a@example.org", template="verify_email", params={"link": "x"}, idempotency_key="k1") is True
    assert enqueue(conn, to="a@example.org", template="verify_email", params={"link": "x"}, idempotency_key="k1") is False
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox"); assert cur.fetchone()[0] == 1
