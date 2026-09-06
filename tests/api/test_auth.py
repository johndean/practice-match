import base64
import json
import statistics
import time
import uuid
from datetime import timedelta

import httpx
import pytest
from httpx import ASGITransport

from app.api import auth as A
from app.auth import passwords as P
from app.auth import sessions as S
from app.auth import tokens as T
from app.cache import sync_redis as redis_of
from app.config import settings
from app.mail.outbox import enqueue
from app.main import create_app
from tests.api.conftest import ORIGIN, PW, auth_headers


async def _outbox(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_email, template, params, status FROM email_outbox ORDER BY id"); return cur.fetchall()


async def test_signup_is_uniform_and_queues_one_verify_email(client, conn):
    r1 = await client.post("/api/auth/signup", json={"email": "New.Person@Gmail.com", "password": PW})
    r2 = await client.post("/api/auth/signup", json={"email": "new.person@gmail.com", "password": PW})    # existing → same answer
    assert r1.status_code == r2.status_code == 202 and r1.json() == r2.json() == {"status": "check_email"}
    rows = await _outbox(conn)
    # TWO rows since fix round 1's Critical 1: the new address gets its verify link, and the second
    # (already registered) attempt tells the address's owner somebody tried to sign up as them — the
    # equal commit-level work that closes the registration-timing leak.
    assert [row[1] for row in rows] == ["verify_email", "account_exists"]
    assert rows[0][0] == "New.Person@Gmail.com" and rows[0][2]["link"].startswith("https://qa.foundation.vin/verify?token=")
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
    """One warm-up request, then FIVE samples per case compared as medians (fix round 2, NEW-5).

    The brief compared the single-shot min and max of four samples, and the first sample is always
    the outlier — a warm-up cost, not unequal work, so widening the tolerance would only hide it.
    Six concurrent runs of the old shape failed six times, every one with the same signature: first
    ~230-280 ms, the other three within ~17 ms of each other. The tolerance is unchanged."""
    member(("buyer",), state="suspended", email="s@example.org"); member(("buyer",), state="revoked", email="r@example.org")
    await client.post("/api/auth/signin", json={"email": "warm-up@example.org", "password": PW})   # discarded
    bodies, medians = set(), []
    for email, pw in [("buyer-active@example.org", "wrong-password-xx"), ("nobody@example.org", PW), ("s@example.org", PW), ("r@example.org", PW)]:
        samples = []
        for _ in range(5):
            t0 = time.perf_counter(); r = await client.post("/api/auth/signin", json={"email": email, "password": pw})
            samples.append(time.perf_counter() - t0)
            assert r.status_code == 401; bodies.add(r.text)
        medians.append(statistics.median(samples))
    assert len(bodies) == 1 and "Email or password is incorrect" in bodies.pop()
    assert max(medians) - min(medians) < 0.02 * 5    # equal hash work; pairwise, so this is every pair


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
    aid, cookies, _hdr = member()
    other = S.create(conn, redis_of(), aid, "203.0.113.6", "pytest")
    assert (await client.post("/api/auth/signout", headers=auth_headers(cookies, {"X-CSRF-Token": "csrf-1", "Origin": ORIGIN}))).status_code == 200
    assert (await client.get("/api/me", headers=auth_headers(cookies))).status_code == 401
    assert (await client.get("/api/me", headers=auth_headers({"pm_session": other}))).status_code == 200


async def test_signout_with_a_credential_that_carries_no_session_is_refused(client, conn):
    """The legacy operator bearer passes `account.self` but presents no `pm_session` cookie. It used
    to be answered 200 (and, before that, a 500 from indexing the absent cookie); since fix round
    1's Important 2 the four session-only routes refuse every non-session credential."""
    r = await client.post("/api/auth/signout", headers=LEGACY)
    assert r.status_code == 401 and r.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}


async def test_a_credential_with_no_account_row_is_refused_everywhere_it_would_read_one(client, conn):
    """`deps.LEGACY_ADMIN` is the synthetic `00000000-…-0001` the `API_SECRET_KEY` bearer resolves
    to, and it has no `account` row. `GET /api/me` read `[0]` off that missing row and answered 500
    with a stack trace and no security headers — on the one credential the plan keeps alive until
    I9, doing the obvious thing an operator does with it (fix round 1, Important 4). The two
    password routes are refused one step earlier, by the session-only guard."""
    generic = {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}
    assert (await client.get("/api/me", headers=LEGACY)).status_code == 401
    assert (await client.get("/api/me", headers=LEGACY)).json() == generic
    for path, body in (("/api/auth/password/change", {"current": PW, "new": NEW_PW}), ("/api/auth/reauth", {"password": PW})):
        r = await client.post(path, headers=LEGACY, json=body)
        assert (r.status_code, r.json()) == (401, generic), path


def test_the_password_hash_lookup_is_none_for_an_account_that_is_not_there(conn):
    """The helper's contract, which the session-only guard now keeps the endpoints from ever
    reaching: a principal whose account row has gone must not read `[0]` off `None`."""
    assert A._password_hash_of(conn, uuid.uuid4()) is None


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
    aid, _cookies, _hdr = member(email="burst@example.org")
    for _ in range(6):
        assert (await client.post("/api/auth/signin", json={"email": "burst@example.org", "password": "wrong-wrong-wrong"})).status_code == 401
    with conn.cursor() as cur:
        cur.execute("SELECT action, target_id, before, after, reason FROM audit_log")
        # `target_id` is the real account id since fix round 1's Minor 5 (it was the raw address).
        assert cur.fetchall() == [("signin.failure_burst", str(aid), None, None, None)]


def test_enqueue_is_idempotent_on_its_key(conn):
    """The contract Task I6's sender relies on: the same key writes exactly one row, whichever
    request path re-derives it."""
    assert enqueue(conn, to="a@example.org", template="verify_email", params={"link": "x"}, idempotency_key="k1") is True
    assert enqueue(conn, to="a@example.org", template="verify_email", params={"link": "x"}, idempotency_key="k1") is False
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox"); assert cur.fetchone()[0] == 1


# --- fix round 1 -------------------------------------------------------------------------------


def _ip() -> str:
    """A client address nothing else has used, so a fixed-window limiter never turns a sample into
    a 429 (the trick tests/api/test_interest.py uses)."""
    n = uuid.uuid4().int
    return "10." + ".".join(str((n >> s) & 255) for s in (16, 8, 0))


def _rows(conn, statement, params=()):
    with conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall()


def _password_hash(conn, account_id):
    return _rows(conn, "SELECT password_hash FROM account WHERE id=%s", (account_id,))[0][0]


async def test_signup_does_the_same_work_for_a_new_and_an_existing_address(client, conn):
    """C1. A registered address answered ~29 ms faster than an unregistered one, in
    non-overlapping distributions: only the new branch wrote rows, and only a transaction that has
    written needs a WAL flush at COMMIT. Both branches now write one outbox row, so the commit costs
    the same — and the existing-address branch tells its owner somebody tried to sign up as them."""
    existing = [f"c1-old-{i}@example.org" for i in range(10)]
    with conn.cursor() as cur:
        for email in existing:
            cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,%s,'active')", (email, P.hash_password(PW)))
    new_s, old_s = [], []
    for i in range(10):
        for samples, email in ((new_s, f"c1-new-{i}@example.org"), (old_s, existing[i])):
            t0 = time.perf_counter()
            r = await client.post("/api/auth/signup", json={"email": email, "password": PW}, headers={"x-forwarded-for": _ip()})
            samples.append(time.perf_counter() - t0)
            assert r.status_code == 202 and r.json() == {"status": "check_email"}, email
    templates = sorted(row[1] for row in await _outbox(conn))
    assert templates == ["account_exists"] * 10 + ["verify_email"] * 10
    # 20 ms, not the sign-in test's 100 ms (fix round 2, O-1): what separates the two branches is a
    # WAL flush, which is single-digit milliseconds, so the ruling's borrowed tolerance made this
    # assertion inert — it passed with the `account_exists` enqueue removed (delta 2.8 ms).
    assert abs(statistics.median(new_s) - statistics.median(old_s)) < 0.020, (statistics.median(new_s), statistics.median(old_s))


@pytest.mark.parametrize("bad", ["a\x00b@example.org", "a\x01b@example.org", "a\u202eb@example.org", "a\ud800b@example.org"])
async def test_an_unencodable_address_gets_the_uniform_answer_not_a_500(client, conn, bad):
    """C2. `str.strip()` does not remove NUL and a lone surrogate survives every character class
    `normalise` forbids, so both reached psycopg2, which raises before any SQL is sent — a 500 out
    of `ServerErrorMiddleware`, carrying none of the four security headers, on the two endpoints
    whose whole purpose is that every input gets the same answer."""
    async def post(path, body):
        # `content=`, not `json=`: httpx serialises with ensure_ascii=False and so cannot itself
        # encode a lone surrogate. A caller sends the JSON ESCAPE, which is plain ASCII on the wire
        # and which the server's parser turns back into the surrogate — the actual attack shape.
        return await client.post(path, content=json.dumps(body).encode(), headers={"x-forwarded-for": _ip(), "content-type": "application/json"})

    for path, body_of in (("/api/auth/signin", lambda e: {"email": e, "password": PW}),
                          ("/api/auth/password/forgot", lambda e: {"email": e})):
        unknown = await post(path, body_of(f"nobody-{uuid.uuid4().hex[:8]}@example.org"))
        got = await post(path, body_of(bad))
        assert (got.status_code, got.text) == (unknown.status_code, unknown.text), path
        assert got.headers["strict-transport-security"] == unknown.headers["strict-transport-security"]
    # ...and sign-up, which STORES the address, refuses it — in the A5 envelope, without echoing
    # the input back, rather than as a 500. (Which of the two 422 codes it is depends on whether
    # pydantic or `_address` gets there first; both are A5-shaped and neither reflects the value.)
    r = await post("/api/auth/signup", {"email": bad, "password": PW})
    assert r.status_code == 422 and r.json()["error"]["code"] in ("EMAIL_INVALID", "INVALID_REQUEST")
    assert bad not in r.text and r.headers["x-frame-options"] == "DENY"
    assert await _outbox(conn) == []


async def test_eleven_correct_sign_ins_in_a_window_are_never_locked_out(client, member):
    """I1. The lockout counted ATTEMPTS: a member with a phone, a laptop and a tab that
    re-authenticates reached ten sign-ins in fifteen minutes and was locked out of their own
    account. Spec §3 says ten FAILURES."""
    member(email="ok11@example.org")
    for i in range(11):
        r = await client.post("/api/auth/signin", json={"email": "ok11@example.org", "password": PW})
        assert r.status_code == 200, f"attempt {i} answered {r.status_code}"


async def test_a_success_forgets_earlier_failures(client, member):
    """The other half of I1: nine failures then a success then two failures must not lock out."""
    member(email="mix@example.org")
    for _ in range(9):
        assert (await client.post("/api/auth/signin", json={"email": "mix@example.org", "password": "wrong-wrong-wrong"})).status_code == 401
    assert (await client.post("/api/auth/signin", json={"email": "mix@example.org", "password": PW})).status_code == 200
    for _ in range(2):
        assert (await client.post("/api/auth/signin", json={"email": "mix@example.org", "password": "wrong-wrong-wrong"})).status_code == 401


async def test_an_api_token_cannot_use_the_session_only_routes(client, conn, member):
    """I2. Spec §3's Auth column for these four is "session + CSRF"; `account.self` is granted to
    every non-anonymous role, so any api token passed — and `check_origin_and_csrf` returns early
    for a non-session principal, so neither the double-submit nor the Origin check applied. A leaked
    `k6-qa` token could hold its creating admin signed out of every device indefinitely."""
    aid, cookies, _hdr = member()
    token = T.issue_api_token(conn, name="ci", role="buyer", created_by=aid, ttl=timedelta(days=1)).raw
    auth = {"Authorization": f"Bearer {token}"}
    before = _password_hash(conn, aid)
    generic = {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}
    for path, body in (("/api/auth/signout", None), ("/api/auth/signout-all", None),
                       ("/api/auth/reauth", {"password": PW}), ("/api/auth/password/change", {"current": PW, "new": NEW_PW})):
        r = await client.post(path, headers=auth, json=body)
        assert (r.status_code, r.json()) == (401, generic), path
    assert (await client.get("/api/me", headers=auth)).status_code == 200          # spec allows a token here
    assert (await client.get("/api/me", headers=auth_headers(cookies))).status_code == 200   # the session survived
    assert _rows(conn, "SELECT count(*) FROM session WHERE account_id=%s AND reauth_at IS NOT NULL", (aid,))[0][0] == 0
    assert _password_hash(conn, aid) == before


async def test_a_sign_in_refused_for_account_state_is_audited(client, conn, member):
    """I3. Spec §3: "Suspended/revoked accounts receive the generic 401 **and an audit row**" — the
    compensating control the spec pairs with a deliberately uninformative refusal. A single attempt
    against a suspended account used to leave no trace at all."""
    suspended, _c, _h = member(state="suspended", email="s3@example.org")
    revoked, _c2, _h2 = member(state="revoked", email="r3@example.org")
    for email in ("s3@example.org", "r3@example.org"):
        assert (await client.post("/api/auth/signin", json={"email": email, "password": PW})).status_code == 401
    assert _rows(conn, "SELECT action, target_id, reason FROM audit_log ORDER BY id") == [
        ("signin.refused_state", str(suspended), "suspended"),
        ("signin.refused_state", str(revoked), "revoked"),
    ]


async def test_a_failure_burst_never_stores_the_attempted_address(client, conn, member):
    """M5. The raw address went verbatim into `audit_log.target_id`, a table whose triggers refuse
    UPDATE and DELETE — attacker-controlled text, possibly nobody's address, on a project whose
    Redis keys are pseudonymised for exactly this reason. A REAL account id is stored when there is
    one; otherwise the same truncated-SHA-256 pseudonym `app/ratelimit.py` uses."""
    known, _c, _h = member(email="known-burst@example.org")
    for _ in range(5):
        await client.post("/api/auth/signin", json={"email": "known-burst@example.org", "password": "wrong-wrong-wrong"})
    for _ in range(5):
        await client.post("/api/auth/signin", json={"email": "ghost-burst@example.org", "password": "wrong-wrong-wrong"})
    rows = _rows(conn, "SELECT action, target_id FROM audit_log ORDER BY id")
    assert [r[0] for r in rows] == ["signin.failure_burst", "signin.failure_burst"]
    assert rows[0][1] == str(known)
    assert rows[1][1] != "ghost-burst@example.org" and len(rows[1][1]) == 16
    assert "ghost-burst" not in str(rows)


@pytest.mark.parametrize("state, tokens_expected", [("unverified", 0), ("verified", 1), ("active", 1), ("suspended", 0), ("revoked", 0)])
async def test_forgot_issues_a_reset_link_only_for_verified_and_active_accounts(client, conn, member, state, tokens_expected):
    """M7. Spec §3 says "verified+"; the code said `state NOT IN ('unverified','revoked')`, which
    handed a suspended account a way back in."""
    member(state=state, email="m7@example.org")
    r = await client.post("/api/auth/password/forgot", json={"email": "m7@example.org"})
    assert r.status_code == 202 and r.json() == {"status": "check_email"}
    assert _rows(conn, "SELECT count(*) FROM email_token WHERE purpose='reset'")[0][0] == tokens_expected


async def test_a_new_reset_link_invalidates_the_previous_one(client, conn, member):
    """M7, second half: five `forgot` requests left five simultaneously valid reset tokens."""
    member(email="m7b@example.org")
    for _ in range(3):
        assert (await client.post("/api/auth/password/forgot", json={"email": "m7b@example.org"})).status_code == 202
    live = _rows(conn, "SELECT count(*) FROM email_token WHERE purpose='reset' AND used_at IS NULL AND expires_at > now()")
    assert live[0][0] == 1
    # the newest link still works
    token = _rows(conn, "SELECT params->>'link' FROM email_outbox ORDER BY id DESC")[0][0].split("token=")[1]
    assert (await client.post("/api/auth/password/reset", json={"token": token, "password": NEW_PW})).status_code == 200


async def test_no_outbox_key_carries_a_prefix_of_a_live_secret(client, conn, member):
    """M3. The keys embedded `token[:8]` of a live verify/reset token and `raw[:8]` of a
    NEWLY ISSUED session id, in a table the I6 sender and any future admin outbox screen read."""
    member(email="m3@example.org")
    await client.post("/api/auth/signup", json={"email": "m3-new@example.org", "password": PW}, headers={"x-forwarded-for": _ip()})
    await client.post("/api/auth/password/forgot", json={"email": "m3@example.org"})
    keys = [row[0] for row in _rows(conn, "SELECT idempotency_key FROM email_outbox")]
    secrets_seen = [row[0].split("token=")[1] for row in _rows(conn, "SELECT params->>'link' FROM email_outbox WHERE params ? 'link'")]
    assert len(keys) == 2 and len(secrets_seen) == 2
    for key in keys:
        for secret in secrets_seen:
            assert secret[:8] not in key, f"{key} carries a prefix of a live token"


async def test_a_staff_sign_in_from_a_new_device_is_notified_and_a_familiar_one_is_not(client, conn, member):
    """M12. Spec §3 lists `signin_new_device` among the compensating controls for passwords-only
    staff/admin, and nothing in any brief enqueued it. The pair `(ip, user_agent)` is compared
    against the account's sessions of the last 90 days — `session` stores both columns."""
    member(("staff",), email="m12@example.org")
    device = {"x-forwarded-for": "203.0.113.77", "user-agent": "Firefox/1"}
    assert (await client.post("/api/auth/signin", json={"email": "m12@example.org", "password": PW}, headers=device)).status_code == 200
    assert [r[1] for r in await _outbox(conn)] == ["signin_new_device"]
    assert (await client.post("/api/auth/signin", json={"email": "m12@example.org", "password": PW}, headers=device)).status_code == 200
    assert [r[1] for r in await _outbox(conn)] == ["signin_new_device"], "the same device must not notify twice"


async def test_a_buyer_sign_in_from_a_new_device_is_not_notified(client, conn, member):
    """M12's other branch: the control is for staff/admin, who have no second factor."""
    member(("buyer",), email="m12b@example.org")
    assert (await client.post("/api/auth/signin", json={"email": "m12b@example.org", "password": PW},
                              headers={"x-forwarded-for": "203.0.113.78", "user-agent": "Firefox/2"})).status_code == 200
    assert await _outbox(conn) == []


# --- fix round 1, Important 7 / Minor 6: the constraints the mutation run found undefended ------
# Each of these fails for a one-line mutation of the constant or the call it pins; the mutation and
# the line it broke are recorded in the task report.


async def test_signup_is_limited_per_ip(client):
    """`limits.hit(… "signup:ip" …)` could be deleted outright with a green suite. A weak password
    keeps every sample off Postgres and still proves the limiter runs BEFORE the policy."""
    ip = _ip()
    for i in range(5):
        r = await client.post("/api/auth/signup", json={"email": f"ip-{i}@example.org", "password": "password12345"}, headers={"x-forwarded-for": ip})
        assert r.status_code == 422, i
    r = await client.post("/api/auth/signup", json={"email": "ip-5@example.org", "password": "password12345"}, headers={"x-forwarded-for": ip})
    assert r.status_code == 429 and r.headers["retry-after"] == "3600"


async def test_signup_is_limited_per_email(client):
    for i in range(3):
        r = await client.post("/api/auth/signup", json={"email": "same@example.org", "password": "password12345"}, headers={"x-forwarded-for": _ip()})
        assert r.status_code == 422, i
    r = await client.post("/api/auth/signup", json={"email": "same@example.org", "password": "password12345"}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 429 and r.headers["retry-after"] == "86400"


async def test_forgot_is_limited_per_email_and_per_ip(client, conn):
    """The per-email ceiling is the spec's; the per-IP one is fix round 1's Minor 6 — an
    unthrottled endpoint that opens a Postgres connection per call is a connection-exhaustion
    lever whatever the tokens are worth."""
    for i in range(3):
        assert (await client.post("/api/auth/password/forgot", json={"email": "f-lim@example.org"}, headers={"x-forwarded-for": _ip()})).status_code == 202, i
    r = await client.post("/api/auth/password/forgot", json={"email": "f-lim@example.org"}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 429 and r.headers["retry-after"] == "3600"

    ip = _ip()
    for i in range(10):
        assert (await client.post("/api/auth/password/forgot", json={"email": f"f-ip-{i}@example.org"}, headers={"x-forwarded-for": ip})).status_code == 202, i
    r = await client.post("/api/auth/password/forgot", json={"email": "f-ip-last@example.org"}, headers={"x-forwarded-for": ip})
    assert r.status_code == 429 and r.headers["retry-after"] == "3600"


@pytest.mark.parametrize("path", ["/api/auth/verify", "/api/auth/password/reset"])
async def test_token_endpoints_are_limited_per_ip(client, conn, path):
    """Minor 6: sixty consecutive attempts at either were unthrottled — all 400, and each one an
    un-pooled Postgres connection at the time."""
    ip = _ip()
    body = {"token": "no-such-token", "password": NEW_PW}
    for i in range(30):
        assert (await client.post(path, json=body, headers={"x-forwarded-for": ip})).status_code == 400, i
    r = await client.post(path, json=body, headers={"x-forwarded-for": ip})
    assert r.status_code == 429 and r.headers["retry-after"] == "3600"


async def test_signin_is_limited_per_ip(client, conn):
    """A fresh address per attempt, so only the per-IP bucket accumulates — the per-address lockout
    would otherwise stop the run at ten."""
    ip = _ip()
    for i in range(30):
        r = await client.post("/api/auth/signin", json={"email": f"ip-{i}@example.org", "password": PW}, headers={"x-forwarded-for": ip})
        assert r.status_code == 401, i
    r = await client.post("/api/auth/signin", json={"email": "ip-last@example.org", "password": PW}, headers={"x-forwarded-for": ip})
    assert r.status_code == 429 and r.headers["retry-after"] == "900"


async def test_the_csrf_cookie_carries_128_bits(client, member):
    """Spec §3: "`pm_csrf` readable, 128-bit". `CSRF_BYTES` could be cut from 16 to 2 with a green
    suite — the cookie is compared constant-time, so a short one fails no other assertion."""
    member(email="csrf@example.org")
    r = await client.post("/api/auth/signin", json={"email": "csrf@example.org", "password": PW})
    value = next(c.split("=", 1)[1].split(";")[0] for c in r.headers.get_list("set-cookie") if c.startswith("pm_csrf="))
    assert len(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))) >= 16


async def test_the_verify_link_lasts_a_day_and_the_reset_link_an_hour(client, conn, member):
    """Spec §3: "verify_email (24 h)", "password_reset (1 h)". Both TTLs could be stretched tenfold
    with a green suite. `expires_at` is set by the DATABASE clock (`now() + interval`), so this
    reads the interval back rather than trusting the app's."""
    await client.post("/api/auth/signup", json={"email": "ttl@example.org", "password": PW}, headers={"x-forwarded-for": _ip()})
    member(email="ttl2@example.org")
    await client.post("/api/auth/password/forgot", json={"email": "ttl2@example.org"}, headers={"x-forwarded-for": _ip()})
    ttl = dict(_rows(conn, "SELECT purpose, expires_at - now() FROM email_token"))
    assert timedelta(hours=23, minutes=59) < ttl["verify"] <= timedelta(hours=24)
    assert timedelta(minutes=59) < ttl["reset"] <= timedelta(hours=1)


# --- fix round 1, Minor 2: the four headers on the two responses that most need them ------------


async def test_a_cors_preflight_carries_the_security_headers(dist, monkeypatch):
    """`add_middleware` PREPENDS, so `SecurityHeadersMiddleware` added before CORS ended up INSIDE
    it and a preflight — answered by CORSMiddleware itself, which never calls through — shipped
    `access-control-*` and no HSTS at all."""
    monkeypatch.setattr(settings, "allowed_origins", ORIGIN)
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url=ORIGIN) as c:
        r = await c.options("/api/auth/signin", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"})
    assert r.status_code == 200 and "access-control-allow-origin" in r.headers
    assert r.headers["strict-transport-security"].startswith("max-age=31536000")
    assert r.headers["x-frame-options"] == "DENY" and r.headers["referrer-policy"] == "no-referrer"


async def test_a_500_carries_the_security_headers_and_the_a5_envelope(tmp_path):
    """`ServerErrorMiddleware` sits outside every user middleware, so the 500 it generates never
    passed through them: `text/plain "Internal Server Error"`, zero security headers."""
    app = create_app(dist=tmp_path / "no-such-dist")   # no dist: no SPA catch-all to shadow /boom

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError("boom")

    async with httpx.AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url=ORIGIN) as c:
        r = await c.get("/boom")
    assert r.status_code == 500 and r.json() == {"error": {"code": "INTERNAL", "message": "Something went wrong."}}
    assert r.headers["strict-transport-security"].startswith("max-age=31536000")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("body", [{"email": "a@e.co", "password": "x" * 2000}, {"email": 12345, "password": PW}])
async def test_a_request_fastapi_itself_refuses_gets_the_a5_envelope_without_an_echo(client, body):
    """Minor 1: FastAPI's own 422 shipped `{"detail":[…]}` with the submitted value echoed back —
    a second error envelope beside A5's, and a reflection of attacker-supplied input."""
    r = await client.post("/api/auth/signup", json=body)
    assert r.status_code == 422
    assert r.json() == {"error": {"code": "INVALID_REQUEST", "message": "The request could not be understood. Check the fields and try again."}}
    assert "12345" not in r.text and "xxxx" not in r.text


# --- fix round 1, Important 6: /api/auth/* is not mounted behind the Coming Soon page -----------


@pytest.mark.parametrize("mode, signup_status", [("app", 422), ("coming_soon", 404)])
async def test_the_auth_router_is_mounted_only_in_app_mode(dist, redis, monkeypatch, mode, signup_status):
    """CLAUDE.md: production runs `coming_soon` until launch. Mounted unconditionally, `/api/auth/*`
    was live on foundation.vin from the moment I4 shipped — anyone who guessed the path could create
    real `account` rows behind the Coming Soon page, and nothing emails them until I6 lands, so the
    only visible effect would have been unexplained rows.

    Takes `redis` so the sign-up limiter counts into this test's own fakeredis: a client built by
    hand does not get the `client` fixture's isolation, and the shared dev Redis remembers the
    per-IP bucket across runs."""
    monkeypatch.setattr(settings, "site_mode", mode)
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url=ORIGIN) as c:
        r = await c.post("/api/auth/signup", json={"email": "gate@example.org", "password": "password12345"})
        assert r.status_code == signup_status
        assert (await c.get("/api/me")).status_code == (401 if mode == "app" else 404)
    assert r.json()["error"]["code"] == ("PASSWORD_POLICY" if mode == "app" else "NOT_FOUND")


def test_enqueue_refuses_a_template_that_does_not_exist(conn):
    """The allowed-key list `app/mail/outbox.py` gained in fix round 1: a typo'd template would
    otherwise sit in the outbox forever, undeliverable and invisible until Task I6's sender reached
    it."""
    with pytest.raises(KeyError, match="unknown email template"):
        enqueue(conn, to="a@example.org", template="verify_emial", params={}, idempotency_key="typo")
    assert _rows(conn, "SELECT count(*) FROM email_outbox")[0][0] == 0


def test_the_conn_fixture_guard_refuses_the_database(client):
    """M11's guard, tested rather than trusted: this test takes `client` and not `conn`, so every
    `sync_conn` in the process is the refusal."""
    with pytest.raises(RuntimeError, match="without the conn fixture"):
        A.sync_conn()


async def test_malformed_addresses_do_not_share_one_rate_limit_bucket(client, conn):
    """NEW-3. Everything `_normalised` rejects maps to `NO_MATCH`, so every malformed address shared
    ONE `signin:email` / `forgot:email` subject process-wide (`sha256("")[:16]`). Three requests an
    hour therefore pinned `password/forgot` at "Too many attempts" for every caller who submitted a
    malformed address, from any source IP — a pasted non-breaking space or a stray control character
    out of a PDF is enough to spend the budget. C2's "same answer as an unknown address" held only
    for the first three (forgot) or ten (signin) per window, globally.

    The per-address limiters are skipped for `NO_MATCH`; the per-IP ones still bound the caller, and
    nothing is disclosed by it — malformedness is knowable client-side without asking the server."""
    for i in range(4):
        r = await client.post("/api/auth/password/forgot", json={"email": f"malformed-{i}"}, headers={"x-forwarded-for": _ip()})
        assert r.status_code == 202, i
    fresh = await client.post("/api/auth/password/forgot", json={"email": "unknown-but-well-formed@example.org"}, headers={"x-forwarded-for": _ip()})
    assert fresh.status_code == 202, "a well-formed unknown address was spent by the malformed ones"
    for i in range(11):
        r = await client.post("/api/auth/signin", json={"email": f"malformed-s-{i}", "password": PW}, headers={"x-forwarded-for": _ip()})
        assert r.status_code == 401, i
    # ...and the burst row that used to identify nothing but the constant pseudonym of "" is gone.
    assert _rows(conn, "SELECT count(*) FROM audit_log WHERE action='signin.failure_burst'")[0][0] == 0
