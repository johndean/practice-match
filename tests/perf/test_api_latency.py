import statistics
import time
import uuid

import psycopg2
import pytest

from app import db
from app.config import settings

# --- Task I4 budgets ---------------------------------------------------------------------------
# The brief's numbers, RESTORED in fix round 1 (Important 5). They were relaxed to 150/500 ms on the
# argument that an un-pooled `psycopg2.connect()` made them physically unreachable; the connect was
# 59 % of `GET /api/me` and `app.db` now pools it, so the argument no longer holds. Measured on the
# dev stack (Apple Silicon, Docker Desktop, the PostGIS image pinned to linux/amd64 and therefore
# EMULATED) — before -> after the pool:
#
#     /api/me, signed in ..............  58-62 ms  ->  see the report      (budget 20)
#     GET /api/me, well-formed bearer .  77-96 ms  ->  see the report
#     POST /api/auth/signin ...........  215-254   ->  see the report      (budget 300)
#     POST /api/auth/signup ...........  202-213   ->  see the report      (budget 300, John's default)
#
# Only signup keeps a relaxed number, and it is John's ruling rather than an implementer's: one
# Argon2id hash at the spec's 64 MiB / t=3 is ~97 ms on its own, so the brief's 100 ms leaves
# nothing for the request around it. The CI-runner measurement the ruling asks for is in the report.
BEARER_BUDGET_MS = 60
SIGNUP_BUDGET_MS = 300   # brief: 100 — John's default in fix round 1; one Argon2id hash is ~97 ms
SIGNIN_BUDGET_MS = 300   # the brief's number
COLD_ME_BUDGET_MS = 60   # the review's ⚠️: /api/me with the principal cache MISSED (Redis -> Postgres)
BUDGET_MS = {"/api/healthz": 20, "/": 15, "/api/me": 20}   # Census B5 and Map engines M3/M4 extend this dict
# Paths BUDGET_MS measures through the SIGNED-IN client rather than the anonymous one (Task I4):
# `/api/me` answered anonymously is a 401 that never opens a connection, which is not the path the
# app serves. Everything else here is public and is measured as a visitor sees it.
SIGNED_IN_PATHS = frozenset({"/api/me"})
PERF_PW = "orbit-lantern-quiet-42"


def _fresh_ip() -> str:
    """A client address nothing else has used, so a fixed-window rate limit can never make a
    latency sample into a 429 — the same trick test_interest.py uses, for the same reason."""
    n = uuid.uuid4().int
    return "10." + ".".join(str((n >> s) & 255) for s in (16, 8, 0))


def _sql(statement: str, params: tuple = ()) -> list[tuple]:
    with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall() if cur.description else []


@pytest.fixture
async def signed_in(dist, db_ready):
    """A real account with a live session, and a client that presents its cookie on every request.

    The session id goes in a literal `Cookie` header rather than httpx's per-request `cookies=`
    argument, which httpx 0.28 deprecates and `-W error` therefore turns into a failure."""
    from httpx import ASGITransport, AsyncClient

    from app.auth import passwords as P
    from app.auth import sessions as S
    from app.cache import sync_redis
    from app.db import sync_conn
    from app.main import create_app

    email = f"perf-{uuid.uuid4().hex[:10]}@example.org"
    conn = sync_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO account (email, password_hash, state, display_name) VALUES (%s,%s,'active','Perf Tester') RETURNING id",
                        (email, P.hash_password(PERF_PW)))
            account_id = cur.fetchone()[0]
        raw = S.create(conn, sync_redis(), account_id, "203.0.113.9", "pytest-perf")
        try:
            async with AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url="https://qa.foundation.vin",
                                   headers={"Cookie": f"pm_session={raw}"}) as c:
                yield c
        finally:
            S.revoke_all(conn, sync_redis(), account_id)   # drops the cached principals too, so the shared dev Redis is left clean
            with conn.cursor() as cur:
                cur.execute("DELETE FROM account WHERE id=%s", (account_id,))
    finally:
        conn.close()


def p95_of(samples: list[float]) -> float:
    """The 95th percentile, `method="inclusive"` — never above the largest observed sample.

    The default (exclusive) method EXTRAPOLATES past the data, which on the ten samples the sign-in
    gate takes made the assertion `1.2 x max(10) <= budget` rather than `p95 <= budget`: a measured
    max of 213.1 ms came out as a "p95" of 255.3 ms (fix round 2, NEW-2). Every gate in this file
    goes through here, so none of them can report a latency nothing actually took."""
    return statistics.quantiles(samples, n=20, method="inclusive")[18]


async def p95(client, path: str, n: int = 50) -> float:
    await client.get(path)  # warm-up
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = await client.get(path)
        samples.append((time.perf_counter() - t0) * 1000)
        assert r.status_code < 500, path
    return p95_of(samples)


@pytest.mark.parametrize("path, budget", sorted(BUDGET_MS.items()))
async def test_p95_within_budget(client, signed_in, path, budget):
    # `signed_in` is taken as an ordinary parameter, not resolved lazily through
    # `request.getfixturevalue`: pytest-asyncio cannot set an ASYNC fixture up from inside a running
    # event loop ("Runner.run() cannot be called from a running event loop").
    measured = signed_in if path in SIGNED_IN_PATHS else client
    got = await p95(measured, path)
    assert got <= budget, f"{path} p95 {got:.1f} ms over {budget} ms"


async def test_anonymous_well_formed_bearer_p95_within_budget(client, db_ready):
    """I3 fix round 2 refuses a MALFORMED bearer on shape alone, before Postgres. A WELL-FORMED one
    (`pm_<uuid>.<secret>`) that names no token still costs one un-pooled psycopg2 connect per
    request on every guarded route — `app.db.sync_conn()` opens a fresh connection, there is no
    sync pool — and this is what pins that cost. The answer is the generic 401."""
    bearer = {"Authorization": f"Bearer pm_{uuid.uuid4()}.{'x' * 43}"}
    await client.get("/api/me", headers=bearer)   # warm-up, as `p95` does: the FIRST connect is the slow one
    samples = []
    for _ in range(50):
        t0 = time.perf_counter()
        r = await client.get("/api/me", headers=bearer)
        samples.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 401, r.text
    got = p95_of(samples)
    assert got <= BEARER_BUDGET_MS, f"anonymous well-formed bearer p95 {got:.1f} ms over {BEARER_BUDGET_MS} ms"


async def test_signin_p95_under_300ms(client, db_ready):
    """Spec §3. One Argon2id verify (64 MiB, t=3) dominates; the session write and the principal
    cache are the rest.

    ELEVEN samples, the first discarded, through `p95_of` (fix round 2's NEW-2, actually applied in
    round 3 — see the report). Two things were wrong with the old shape, and both are visible in a
    single passing run of it:

      signin p95 261.2 ms  samples [223, 115, 137, 114, 110, 109, 113, 110, 111, 112]

    The first sample is ~2x the rest, because the autouse `_dispose_pools` teardown closed the pool
    after the previous test, so it pays the pool's own connect and a cold anyio threadpool. And the
    reported "p95" is ABOVE every sample ever taken (261.2 > 223), because `statistics.quantiles`'s
    default method extrapolates past ten data points — so the assertion was really
    `1.2 x max(10) <= 300 ms`, and it tripped whenever the warm-up sample reached ~250 ms.

    The old docstring justified taking no warm-up by saying ten was the most `limits.SIGNIN_EMAIL`
    allowed on one address. That stopped being true in fix round 1, when the lockout began counting
    FAILURES only: successful sign-ins no longer touch that bucket at all."""
    email = f"perf-{uuid.uuid4().hex[:10]}@example.org"
    ip, samples = _fresh_ip(), []
    from app.auth import passwords as P

    _sql("INSERT INTO account (email, password_hash, state) VALUES (%s,%s,'active')", (email, P.hash_password(PERF_PW)))
    try:
        for _ in range(11):
            t0 = time.perf_counter()
            r = await client.post("/api/auth/signin", json={"email": email, "password": PERF_PW}, headers={"x-forwarded-for": ip})
            samples.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200, r.text
        got = p95_of(samples[1:])
        # Captured by pytest unless -s: invisible in a normal run, and the numbers are right there
        # when the gate trips or when somebody needs to see what it is actually measuring.
        print(f"\nsignin p95 {got:.1f} ms  samples {[round(x) for x in samples]} (first discarded)")
        assert got <= SIGNIN_BUDGET_MS, f"/api/auth/signin p95 {got:.1f} ms over {SIGNIN_BUDGET_MS} ms; samples {[round(x) for x in samples]}"
    finally:
        _sql("DELETE FROM account WHERE email=%s", (email,))


async def test_signup_p95_within_budget(client, db_ready, monkeypatch):
    """One Argon2id hash, one INSERT, one token row, one outbox row. Every request carries a fresh
    client address and a fresh email so neither `limits.SIGNUP_IP` (5/hour) nor `SIGNUP_EMAIL`
    (3/day) can turn a sample into a 429. The HIBP screen is switched to its bundled offline list:
    a 2 s-timeout call to a third party is not a budget this suite can hold, and what is being
    measured is the app's own work."""
    monkeypatch.setattr(settings, "hibp_enabled", False)
    tag, samples = uuid.uuid4().hex[:8], []
    try:
        await client.post("/api/auth/signup", json={"email": f"perf-{tag}-warm@example.org", "password": PERF_PW}, headers={"x-forwarded-for": _fresh_ip()})
        for i in range(20):
            t0 = time.perf_counter()
            r = await client.post("/api/auth/signup", json={"email": f"perf-{tag}-{i}@example.org", "password": PERF_PW},
                                  headers={"x-forwarded-for": _fresh_ip()})
            samples.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 202, r.text
        got = p95_of(samples)
        assert got <= SIGNUP_BUDGET_MS, f"/api/auth/signup p95 {got:.1f} ms over {SIGNUP_BUDGET_MS} ms"
    finally:
        _sql("DELETE FROM email_outbox WHERE to_email LIKE %s", (f"perf-{tag}-%",))
        _sql("DELETE FROM account WHERE email LIKE %s", (f"perf-{tag}-%",))


# POST budgets live here as their own tests; BUDGET_MS (GET) is what Census B5 / Map M3-M4 extend (M7 ruling).
async def test_interest_stored_path_p95_within_budget(client, db_ready):
    """Spec 2026-09-06 §3: the full path — validation, three Redis counters, one INSERT — at p95 ≤ 100 ms.
    Every request carries a fresh client IP and a fresh address so no rate limit trips; rows are removed after.

    THREE warm-up requests, none of them measured (2026-09-07). One was not enough, and for the same
    reason the sign-in gate needed the same correction in fix round 3: the autouse `_dispose_pools`
    teardown closes the sync pool after EVERY test, so the first request here pays a fresh psycopg2
    connect, the next pays a cold anyio worker thread, and the Redis client is built on the way
    through as well — three distinct one-off costs, and the first sample is reproducibly the slowest
    of the fifty (6.0-7.3 ms against a 4.2-4.8 ms median, ten runs on the dev stack).

    The measured numbers are printed — captured by pytest unless `-s`, and repeated in the assertion
    message — because this gate failed once on a shared GitHub runner at p95 110.3 ms while the same
    commit passed everywhere else. That is twenty times this machine's steady state (p95 4.7-6.8 ms
    over ten runs; 6.3-7.3 ms with three suites racing each other), so it was the box and not the
    endpoint — but "over 100 ms" on its own could not say so. The next failure will arrive with its
    samples attached: a warm-up artefact shows as one outlier, a stalled runner as a whole block.
    """
    tag = uuid.uuid4().hex[:8]
    samples: list[float] = []
    try:
        for w in range(3):   # warm-ups (M6, N8: a fresh address each, so no rate limit sees them twice)
            await client.post("/api/interest", json={"email": f"perf-{tag}-warm{w}@example.org"}, headers={"x-forwarded-for": _fresh_ip()})
        for i in range(50):
            n = uuid.uuid4().int
            ip = "10." + ".".join(str((n >> s) & 255) for s in (16, 8, 0))
            t0 = time.perf_counter()
            r = await client.post("/api/interest", json={"email": f"perf-{tag}-{i}@example.org"}, headers={"x-forwarded-for": ip})
            samples.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 202, r.text
        got = p95_of(samples)
        print(f"\ninterest p95 {got:.1f} ms  samples {[round(x) for x in samples]} (3 warm-ups discarded)")
        assert got <= 100, f"/api/interest p95 {got:.1f} ms over 100 ms; samples {[round(x) for x in samples]}"
    finally:
        with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM interest_signup WHERE email_normalised LIKE %s", (f"perf-{tag}-%",))


async def test_cold_principal_cache_me_p95_within_budget(signed_in, db_ready):
    """The review's ⚠️: every other probe ran with a WARM principal cache. On a miss
    `deps._session_principal` falls through to Postgres and opens a connection of its own, on top of
    the one `/api/me` opens — so this is the two-connection path, and the one that says whether the
    pool actually removed the cost."""
    from app.auth import sessions as S
    from app.cache import sync_redis

    raw = signed_in.headers["Cookie"].split("pm_session=", 1)[1].split(";")[0]
    key = f"session:{S.hash_id(raw)}"
    samples = []
    await signed_in.get("/api/me")
    for _ in range(30):
        sync_redis().delete(key)           # force the miss half on every sample
        t0 = time.perf_counter()
        r = await signed_in.get("/api/me")
        samples.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200, r.text
    got = p95_of(samples)
    assert got <= COLD_ME_BUDGET_MS, f"/api/me with a cold principal cache p95 {got:.1f} ms over {COLD_ME_BUDGET_MS} ms"


async def test_no_connection_is_held_across_the_argon2id_hop(client, db_ready, monkeypatch):
    """Important 5's other half. `with conn:` opens a real transaction even on an autocommit
    connection, so `signin` used to hold a Postgres backend idle-in-transaction across the ~97 ms
    Argon2id verify — and `password/reset` across the HIBP screen's 2 s timeout. A burst of sign-ins
    parks that many backends. The credential work now happens between two short connections."""
    from app.auth import passwords as P

    real, checked_out = P.verify_async, []

    async def watched(pw, hashed):
        checked_out.append(db.sync_pool_in_use())
        return await real(pw, hashed)

    monkeypatch.setattr(P, "verify_async", watched)
    r = await client.post("/api/auth/signin", json={"email": f"perf-{uuid.uuid4().hex[:8]}@example.org", "password": PERF_PW},
                          headers={"x-forwarded-for": _fresh_ip()})
    assert r.status_code == 401
    assert checked_out == [0], f"a connection was checked out across the Argon2id hop: {checked_out}"
