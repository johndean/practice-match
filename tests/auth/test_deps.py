from typing import ClassVar
from uuid import uuid4

import httpx
import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport

from app import db
from app.auth import deps
from app.auth import sessions as S
from app.auth.deps import require
from app.config import settings


def _member(conn, roles, state="active"):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'h',%s) RETURNING id", (f"{'-'.join(roles) or 'none'}@x.io", state)); aid = cur.fetchone()[0]
        for r in roles:
            cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,%s,%s)", (aid, r, aid))
    return aid


@pytest.fixture
def app():
    a = FastAPI()
    deps.install(a)   # ruling (a): the A5 body comes from ONE handler this app registers, not from a global patch
    @a.get("/read", dependencies=[Depends(require("market.read"))])
    async def read(): return {"ok": True}
    @a.post("/decide", dependencies=[Depends(require("users.decide"))])
    async def decide(): return {"ok": True}
    @a.post("/activate", dependencies=[Depends(require("engine.activate"))])
    async def activate(): return {"ok": True}
    return a


@pytest.fixture
async def client(app, conn, redis):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="https://qa.foundation.vin") as c:
        yield c


def _as(c, **cookies):
    """Sets `pm_session`/`pm_csrf` on the CLIENT and returns it. Fix round 1, ruling (b): the
    brief's tests originally passed `cookies=` per request, which httpx deprecates — under the
    gate's `-W error` that is a failure, and the first implementation silenced it with an autouse
    warning filter over the whole suite. Fixed at source instead: the jar is cleared each time, so
    a case that means "no cookie" really sends none."""
    c.cookies.clear()
    for name, value in cookies.items():
        c.cookies.set(name, value)
    return c


async def test_anonymous_gets_401_and_applicant_403(client, conn, redis):
    assert (await client.get("/read")).status_code == 401
    aid = _member(conn, [], state="pending"); raw = S.create(conn, redis, aid, None, None)
    r = await _as(client, pm_session=raw).get("/read")
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


async def test_buyer_reads_but_cannot_decide_and_revocation_is_next_request(client, conn, redis):
    aid = _member(conn, ["buyer"]); raw = S.create(conn, redis, aid, None, None)
    assert (await _as(client, pm_session=raw).get("/read")).status_code == 200
    hdr = {"X-CSRF-Token": "t", "Origin": "https://qa.foundation.vin"}
    assert (await _as(client, pm_session=raw, pm_csrf="t").post("/decide", headers=hdr)).status_code == 403
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET state='revoked' WHERE id=%s", (aid,))
    S.invalidate_account(redis, aid)
    assert (await _as(client, pm_session=raw).get("/read")).status_code == 403


async def test_state_changes_need_csrf_and_matching_origin(client, conn, redis):
    aid = _member(conn, ["staff"]); raw = S.create(conn, redis, aid, None, None)
    ok = _as(client, pm_session=raw, pm_csrf="t")
    assert (await ok.post("/decide", headers={"X-CSRF-Token": "t", "Origin": "https://qa.foundation.vin"})).status_code == 200
    r = await ok.post("/decide", headers={"X-CSRF-Token": "wrong", "Origin": "https://qa.foundation.vin"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF"
    r = await ok.post("/decide", headers={"X-CSRF-Token": "t", "Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ORIGIN"


async def test_reauth_required_for_destructive_admin_actions(client, conn, redis):
    aid = _member(conn, ["admin"]); raw = S.create(conn, redis, aid, None, None)
    ok = _as(client, pm_session=raw, pm_csrf="t"); hdr = {"X-CSRF-Token": "t", "Origin": "https://qa.foundation.vin"}
    r = await ok.post("/activate", headers=hdr)
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_REQUIRED"
    S.set_reauth(conn, redis, S.resolve(conn, redis, raw))
    assert (await ok.post("/activate", headers=hdr)).status_code == 200


async def test_api_token_and_legacy_operator_token(client, conn, redis, monkeypatch):
    from datetime import timedelta

    from app.auth import tokens as T
    admin = _member(conn, ["admin"])
    raw = T.issue_api_token(conn, name="e2e", role="buyer", created_by=admin, ttl=timedelta(days=1))
    assert (await client.get("/read", headers={"Authorization": f"Bearer {raw}"})).status_code == 200
    assert (await client.post("/decide", headers={"Authorization": f"Bearer {raw}"})).status_code == 403   # buyer token, no CSRF needed
    legacy = {"Authorization": f"Bearer {settings.api_secret_key}"}
    assert (await client.post("/activate", headers=legacy)).status_code == 200                              # legacy operator = admin, exempt from re-auth until I9 deletes it


def test_client_ip_uses_only_the_first_forwarded_hop():
    class R:  # minimal request stand-in
        headers: ClassVar[dict[str, str]] = {"x-forwarded-for": "198.51.100.7, 10.0.0.1"}
        client = type("c", (), {"host": "10.0.0.9"})
    assert deps.client_ip(R()) == "198.51.100.7"
    R.headers = {}
    assert deps.client_ip(R()) == "10.0.0.9"


# --- supplemental (not in the brief's Step 1 — added for 100% branch coverage) ---


def test_client_ip_with_no_header_and_no_client_is_none():
    class R:
        headers: ClassVar[dict[str, str]] = {}
        client = None
    assert deps.client_ip(R()) is None


def test_require_rejects_an_unknown_permission_at_wiring_time():
    with pytest.raises(KeyError):
        require("no.such.permission")


async def test_garbage_session_cookie_resolves_to_anonymous(client, conn, redis):
    """A cookie is present but matches no session (never cached, never in Postgres, or already
    expired) — `S.resolve` returns None, so `current_principal` must fall through to anonymous
    (401) rather than crash or wrongly authenticate (deps.py:65's `if p:` false branch)."""
    r = await _as(client, pm_session="not-a-real-session-token").get("/read")
    assert r.status_code == 401


# --- fix round 1: the A5 error body is an explicit, app-scoped handler (rulings (a), (d); Important 6) ---


@pytest.fixture
def served_app(dist):
    """The REAL application object — `create_app()`, handlers and middleware and all — with one
    `require`-guarded route and one ordinary-`HTTPException` route grafted on. Task I3 wires no
    router of its own (I4 does), so without this graft there is nothing on the served app to prove
    the A5 body against; Important 6 is precisely that the mechanism was only ever tested on a bare
    `FastAPI()` built inside this file. The graft is moved to the FRONT of the route list because
    `create_app()` ends with `mount_spa`'s `/{path:path}` catch-all, which would otherwise match
    first."""
    from fastapi import APIRouter, HTTPException

    from app.main import create_app

    a = create_app(dist=dist)
    router = APIRouter()

    @router.post("/probe/decide", dependencies=[Depends(require("users.decide"))])
    async def probe_decide(): return {"ok": True}

    @router.get("/probe/plain")
    async def probe_plain(): raise HTTPException(404, detail="no such thing")

    @router.get("/probe/limited")
    async def probe_limited():
        from app.auth import limits
        from app.cache import sync_redis
        limits.hit(sync_redis(), "probe", "one-subject", 0, 60)   # limit 0: the first hit is already over
        return {"ok": True}

    a.include_router(router)
    a.router.routes.insert(0, a.router.routes.pop())
    return a


@pytest.fixture
async def served_client(served_app, conn, redis):
    async with httpx.AsyncClient(transport=ASGITransport(app=served_app), base_url="https://qa.foundation.vin") as c:
        yield c


async def test_the_served_app_renders_the_a5_body_for_require(served_client, conn, redis):
    """(a)/Important 6: `create_app()` calls `deps.install(app)`, so a refusal from `require` on the
    REAL app carries decision A5's body — no import-order luck, no monkeypatch of FastAPI's own
    module-level default."""
    anon = await served_client.post("/probe/decide")
    assert anon.status_code == 401 and anon.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}
    aid = _member(conn, ["buyer"])
    raw = S.create(conn, redis, aid, None, None)
    served_client.cookies.set("pm_session", raw)
    served_client.cookies.set("pm_csrf", "t")
    denied = await served_client.post("/probe/decide", headers={"X-CSRF-Token": "t", "Origin": "https://qa.foundation.vin"})
    assert denied.status_code == 403 and denied.json() == {"error": {"code": "FORBIDDEN", "message": "Your account cannot do this."}}


async def test_the_served_app_renders_the_a5_body_for_a_rate_limit(served_client):
    """The 429 half of the same ruling: `limits.hit` raises `deps.RateLimited`, an `AuthError`, so
    the one installed handler shapes it AND passes its `Retry-After` through."""
    r = await served_client.get("/probe/limited")
    assert r.status_code == 429
    assert r.json() == {"error": {"code": "RATE_LIMITED", "message": "Too many attempts. Try again later."}}
    assert r.headers["Retry-After"] == "60"


async def test_an_ordinary_http_exception_keeps_fastapis_own_body(served_client):
    """The other half of the same ruling: the handler is registered for `AuthError` ONLY, so every
    other HTTPException in the app still renders FastAPI's `{"detail": ...}`."""
    r = await served_client.get("/probe/plain")
    assert r.status_code == 404 and r.json() == {"detail": "no such thing"}


def _bare_request(method: str = "POST") -> Request:
    return Request({"type": "http", "method": method, "path": "/probe", "raw_path": b"/probe", "query_string": b"", "root_path": "",
                    "scheme": "https", "server": ("qa.foundation.vin", 443), "client": ("198.51.100.7", 1),
                    "headers": [(b"host", b"qa.foundation.vin")]})


def test_permission_denied_and_unauthenticated_are_real_classes(monkeypatch):
    """Ruling (d): `deps.PermissionDenied` is named by the brief's own interface list and by the
    plan I5/I6 will read, so it exists and is what `require` raises — checkable by a direct
    `pytest.raises`, not only through an HTTP body."""
    assert issubclass(deps.PermissionDenied, deps.AuthError)
    assert issubclass(deps.Unauthenticated, deps.AuthError)
    with pytest.raises(deps.Unauthenticated) as anon:
        deps.require("users.decide")(_bare_request())
    assert anon.value.status_code == 401 and anon.value.code == "UNAUTHORIZED"
    monkeypatch.setattr(deps, "current_principal", lambda request: S.Principal(uuid4(), "active", frozenset({"buyer"}), None, "session", "h"))
    with pytest.raises(deps.PermissionDenied) as denied:
        deps.require("users.decide")(_bare_request("GET"))
    assert denied.value.status_code == 403 and denied.value.code == "FORBIDDEN"
    assert denied.value.message == "Your account cannot do this."
    assert denied.value.detail == {"error": {"code": "FORBIDDEN", "message": "Your account cannot do this."}}


# --- fix round 1: the hot path costs one Redis GET, and every connection it does open is closed
# (ruling (c); Critical 3) ---


async def test_a_cache_hit_opens_no_postgres_connection(client, conn, redis, monkeypatch):
    """Critical 3(i): `current_principal` opened `sync_conn()` unconditionally — ~34 ms of connect
    per authenticated request — BEFORE asking Redis whether it needed Postgres at all, against spec
    §8's ≤ 2 ms auth budget. `S.create` leaves the principal cached, so this request must resolve
    from Redis alone; `sync_conn` is replaced by something that explodes if it is called."""
    aid = _member(conn, ["buyer"]); raw = S.create(conn, redis, aid, None, None)

    def _no_postgres():
        raise AssertionError("current_principal opened a Postgres connection on a cache hit")

    monkeypatch.setattr(deps, "sync_conn", _no_postgres)
    assert (await _as(client, pm_session=raw).get("/read")).status_code == 200


async def test_a_cache_miss_opens_one_connection_and_closes_it(client, conn, redis, monkeypatch):
    """Ruling (c): `with sync_conn() as conn:` is psycopg2's TRANSACTION context manager — it
    commits, it does not close — so the socket only went away when CPython happened to collect the
    local. Every connection this dependency opens is now released explicitly.

    I4 fix round 1 pooled `sync_conn()`, so "released" no longer means `conn.closed`: a returned
    connection is still open, waiting in the pool. `db.sync_pool_in_use()` is what says it is not
    still checked out, which is the property this test always meant."""
    aid = _member(conn, ["buyer"]); raw = S.create(conn, redis, aid, None, None)
    redis.delete(f"session:{S.hash_id(raw)}")  # force the miss half
    opened = []
    real = deps.sync_conn

    def _tracked():
        c = real()
        opened.append(c)
        return c

    monkeypatch.setattr(deps, "sync_conn", _tracked)
    assert (await _as(client, pm_session=raw).get("/read")).status_code == 200
    assert len(opened) == 1
    assert db.sync_pool_in_use() == 0, "the per-request Postgres connection was left checked out"


def test_current_principal_is_a_plain_def_so_fastapi_threadpools_it():
    """psycopg2 is blocking: as an `async def` dependency this would block the event loop for every
    request. FastAPI runs a plain `def` dependency in the anyio worker threadpool (ruling (c))."""
    import inspect

    assert inspect.iscoroutinefunction(deps.current_principal) is False
    assert inspect.iscoroutinefunction(deps.require("market.read")) is False


async def test_an_admin_api_token_can_never_satisfy_re_authentication(client, conn, redis):
    """Critical 2: the re-auth gate was conditioned on `principal.kind == "session"`, so a token
    principal — which has no password to confirm and so can never satisfy it — sailed through. An
    exfiltrated CI token with `role='admin'` (the api_token CHECK constraint allows it) could
    activate map engines, decide licences, grant roles and mint further tokens with one request.
    Fail closed: REAUTH permissions are unreachable for every non-session principal except the
    legacy operator secret, which the brief exempts explicitly until I9 deletes it."""
    from datetime import timedelta

    from app.auth import tokens as T
    admin = _member(conn, ["admin"])
    raw = T.issue_api_token(conn, name="e2e-qa", role="admin", created_by=admin, ttl=timedelta(days=90))
    hdr = {"Authorization": f"Bearer {raw}"}
    r = await client.post("/activate", headers=hdr)
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_REQUIRED"
    assert (await client.get("/read", headers=hdr)).status_code == 200          # non-REAUTH permissions still work
    assert (await client.post("/decide", headers=hdr)).status_code == 200       # ...including staff ones


async def test_the_reauth_window_is_ten_minutes_wide(client, conn, redis):
    """Important 3: `REAUTH_WINDOW` was pinned by nothing — widening it to 3650 days left all nine
    given tests passing, because they only ever covered "no reauth_at at all" and "confirmed a
    moment ago". The staleness boundary IS the control, so it is tested on both sides of ten
    minutes. The 60 s principal cache is deleted between the two cases: without that, the second
    request would be answered from the reauth_at the first one cached."""
    aid = _member(conn, ["admin"]); raw = S.create(conn, redis, aid, None, None)
    ok = _as(client, pm_session=raw, pm_csrf="t"); hdr = {"X-CSRF-Token": "t", "Origin": "https://qa.foundation.vin"}
    h = S.hash_id(raw)

    def _confirmed(minutes_ago):
        with conn.cursor() as cur:
            cur.execute(f"UPDATE session SET reauth_at = now() - interval '{minutes_ago} minutes' WHERE id_hash = %s", (h,))
        redis.delete(f"session:{h}")

    _confirmed(11)
    stale = await ok.post("/activate", headers=hdr)
    assert stale.status_code == 403 and stale.json()["error"]["code"] == "REAUTH_REQUIRED"
    _confirmed(9)
    assert (await ok.post("/activate", headers=hdr)).status_code == 200


async def test_the_allowed_origins_setting_is_the_other_half_of_the_origin_allowlist(app, conn, redis, monkeypatch):
    """Important 4: `settings.origins` contributed nothing that any test could see — in the test
    environment ALLOWED_ORIGINS is empty, so the only reason `https://qa.foundation.vin` was
    accepted is that it equalled the client's own base_url (the `| {request.url.hostname}` term).
    Deleting the settings term left all nine given tests passing. Here the request arrives at a
    DIFFERENT host from the configured site, so only the settings term can accept it."""
    monkeypatch.setattr(settings, "allowed_origins", "https://foundation.vin")
    aid = _member(conn, ["staff"]); raw = S.create(conn, redis, aid, None, None)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="https://internal.railway.app") as c:
        ok = _as(c, pm_session=raw, pm_csrf="t")
        assert (await ok.post("/decide", headers={"X-CSRF-Token": "t", "Origin": "https://foundation.vin"})).status_code == 200
        r = await ok.post("/decide", headers={"X-CSRF-Token": "t", "Origin": "https://evil.example"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "ORIGIN"


async def test_origin_is_compared_as_scheme_host_and_port_not_hostname_alone(client, conn, redis):
    """Minor 2: the comparison discarded scheme and port, so `http://qa.foundation.vin` — a
    plaintext page on the very host the site runs on, exactly what an SSL-stripping or
    mixed-content attacker gets — passed the check on an https request. RFC 6454's origin is the
    (scheme, host, port) triple; a default port is dropped on both sides so `https://host:443`
    still matches `https://host`."""
    aid = _member(conn, ["staff"]); raw = S.create(conn, redis, aid, None, None)
    ok = _as(client, pm_session=raw, pm_csrf="t")

    async def _decide(origin=None):
        headers = {"X-CSRF-Token": "t"} | ({"Origin": origin} if origin else {})
        return await ok.post("/decide", headers=headers)

    assert (await _decide("https://qa.foundation.vin")).status_code == 200
    assert (await _decide("https://qa.foundation.vin:443")).status_code == 200      # the default port is not a different origin
    assert (await _decide("http://qa.foundation.vin")).status_code == 403           # scheme matters
    assert (await _decide("https://qa.foundation.vin:8443")).status_code == 403     # so does the port
    assert (await _decide("https://qa.foundation.vin:notaport")).status_code == 403  # never a 500 on a forged header
    assert (await _decide("null")).status_code == 403                                # a sandboxed iframe's opaque origin
    assert (await _decide("https://")).status_code == 403                            # scheme with no host
    assert (await _decide()).status_code == 403                                      # no Origin and no Referer at all


async def test_a_valid_session_cookie_wins_over_any_authorization_header(client, conn, redis):
    """Important 9: the brief's PROSE and the plan both say "session cookie -> api token -> legacy
    bearer"; the brief's Step 3 CODE checked `Authorization` first and the implementer followed the
    code. A signed-in user therefore got a 401 whenever some `Bearer` header they may not control
    (a stale SDK default, a proxy, a browser extension) rode along. Prose governs."""
    from datetime import timedelta

    from app.auth import tokens as T
    aid = _member(conn, ["staff"]); raw = S.create(conn, redis, aid, None, None)
    ok = _as(client, pm_session=raw, pm_csrf="t")
    assert (await ok.get("/read", headers={"Authorization": "Bearer garbage"})).status_code == 200
    # ...and the session principal, not some token's, is what `require` evaluated: only a session
    # is asked for CSRF, and only this account carries `staff`.
    hdr = {"Authorization": "Bearer garbage", "X-CSRF-Token": "t", "Origin": "https://qa.foundation.vin"}
    assert (await ok.post("/decide", headers=hdr)).status_code == 200
    # With no VALID cookie the bearer is still tried, in the brief's order: api token, then legacy.
    token = T.issue_api_token(conn, name="e2e", role="buyer", created_by=_member(conn, ["admin"]), ttl=timedelta(days=1))
    stale = _as(client, pm_session="no-longer-a-session")
    assert (await stale.get("/read", headers={"Authorization": f"Bearer {token}"})).status_code == 200
    assert (await stale.post("/activate", headers={"Authorization": f"Bearer {settings.api_secret_key}"})).status_code == 200
    assert (await stale.get("/read", headers={"Authorization": "Bearer garbage"})).status_code == 401


async def test_the_bearer_scheme_is_matched_case_insensitively(client, conn, redis):
    """Minor 1: RFC 7235 makes the auth-scheme token case-insensitive, and real clients send
    `bearer`. `auth.startswith("Bearer ")` rejected them with the generic 401."""
    from datetime import timedelta

    from app.auth import tokens as T
    token = T.issue_api_token(conn, name="e2e", role="buyer", created_by=_member(conn, ["admin"]), ttl=timedelta(days=1))
    for scheme in ("Bearer", "bearer", "BEARER", "BeArEr"):
        assert (await client.get("/read", headers={"Authorization": f"{scheme} {token}"})).status_code == 200
    assert (await client.get("/read", headers={"Authorization": f"Basic {token}"})).status_code == 401


async def test_the_operator_secret_and_the_csrf_token_are_compared_in_constant_time(client, conn, redis, monkeypatch):
    """Important 7: `raw == settings.api_secret_key` and `token != request.cookies.get("pm_csrf")`
    are `str.__eq__`, which short-circuits on the first differing byte. This is the one place in
    the codebase where a long-lived shared admin secret meets attacker-supplied input directly
    (every other secret in `app/auth/` is compared as a SHA-256 digest inside SQL). The comparison
    is the thing under test, so the test watches the comparison."""
    calls: list[tuple[bytes, bytes]] = []
    real = deps.secrets.compare_digest

    def _spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(deps.secrets, "compare_digest", _spy)
    aid = _member(conn, ["staff"]); raw = S.create(conn, redis, aid, None, None)
    ok = _as(client, pm_session=raw, pm_csrf="t")
    assert (await ok.post("/decide", headers={"X-CSRF-Token": "t", "Origin": "https://qa.foundation.vin"})).status_code == 200
    assert (b"t", b"t") in calls, "the CSRF double-submit is not compared in constant time"
    # A forged header decodes as latin-1, and `compare_digest` raises TypeError on a non-ASCII
    # str — so the comparison is done on encoded bytes: a refusal, never a 500. httpx refuses to
    # SEND a non-ASCII header value, so this one is driven at the ASGI scope directly.
    forged = Request({"type": "http", "method": "POST", "path": "/decide", "raw_path": b"/decide", "query_string": b"", "root_path": "",
                      "scheme": "https", "server": ("qa.foundation.vin", 443), "client": ("198.51.100.7", 1),
                      "headers": [(b"host", b"qa.foundation.vin"), (b"x-csrf-token", b"caf\xe9"), (b"cookie", b"pm_csrf=t")]})
    with pytest.raises(deps.CsrfFailed):
        deps.check_origin_and_csrf(forged, S.Principal(aid, "active", frozenset({"staff"}), None, "session", "h"))
    calls.clear()
    secret = settings.api_secret_key
    assert (await _as(client).post("/activate", headers={"Authorization": f"Bearer {secret}"})).status_code == 200
    assert (secret.encode(), secret.encode()) in calls, "the operator secret is not compared in constant time"


def test_a_token_principal_carries_its_creators_account_id_not_the_token_id(conn, redis):
    """Important 10: the principal was built as `S.Principal(ap.token_id, ...)`, so `audit.write`
    (which stores `actor.account_id` into `audit_log.actor_id`, a column with no FK) recorded token
    UUIDs indistinguishable from account UUIDs. The actor is the account that minted the token."""
    from datetime import timedelta

    from app.auth import tokens as T
    creator = _member(conn, ["admin"])
    raw = T.issue_api_token(conn, name="e2e-qa", role="buyer", created_by=creator, ttl=timedelta(days=1))
    request = Request({"type": "http", "method": "GET", "path": "/read", "raw_path": b"/read", "query_string": b"", "root_path": "",
                       "scheme": "https", "server": ("qa.foundation.vin", 443), "client": ("198.51.100.7", 1),
                       "headers": [(b"host", b"qa.foundation.vin"), (b"authorization", f"Bearer {raw}".encode())]})
    p = deps.current_principal(request)
    assert p is not None
    assert p.account_id == creator and p.kind == "token" and p.roles == frozenset({"buyer"})
    assert p.state == "active" and p.reauth_at is None and p.session_hash is None


def test_require_returns_none_for_an_anonymous_caller_on_an_anonymous_permission(conn, redis):
    """Minor 4: `require` is described in the brief and the plan as "returning the `Principal`",
    but `page.gate` (and `market.read` while MARKET_DATA_PUBLIC) are granted to `anonymous`, so it
    legitimately returns None — and `Depends()` types as `Any`, so an I4 handler annotating
    `principal: Principal` would get None with no mypy complaint. The widened return type is
    deliberate; this pins it so nobody "fixes" it into a 401 and breaks the public gate screen."""
    gate = deps.require("page.gate")
    assert gate(_bare_request("GET")) is None
    aid = _member(conn, ["buyer"]); raw = S.create(conn, redis, aid, None, None)
    signed_in = Request({"type": "http", "method": "GET", "path": "/gate", "raw_path": b"/gate", "query_string": b"", "root_path": "",
                         "scheme": "https", "server": ("qa.foundation.vin", 443), "client": ("198.51.100.7", 1),
                         "headers": [(b"host", b"qa.foundation.vin"), (b"cookie", f"pm_session={raw}".encode())]})
    principal = gate(signed_in)
    assert isinstance(principal, S.Principal) and principal.account_id == aid


async def test_a_state_change_with_no_csrf_header_or_no_csrf_cookie_is_refused(client, conn, redis):
    """The double-submit needs BOTH halves: the review confirmed by probe that a missing header
    and a missing cookie are each refused, but the given tests only ever pinned the mismatch."""
    aid = _member(conn, ["staff"]); raw = S.create(conn, redis, aid, None, None)
    origin = {"Origin": "https://qa.foundation.vin"}
    no_header = await _as(client, pm_session=raw, pm_csrf="t").post("/decide", headers=origin)
    assert no_header.status_code == 403 and no_header.json()["error"]["code"] == "CSRF"
    no_cookie = await _as(client, pm_session=raw).post("/decide", headers={"X-CSRF-Token": "t", **origin})
    assert no_cookie.status_code == 403 and no_cookie.json()["error"]["code"] == "CSRF"


async def test_a_malformed_bearer_is_refused_without_opening_a_postgres_connection(client, conn, redis, monkeypatch):
    """Fix round 2 observation: any anonymous request carrying an `Authorization: Bearer …` header
    opened one un-pooled Postgres connection before deciding the token was gibberish — from I4 an
    unauthenticated lever on every guarded route, with no pool and no negative cache. The bearer's
    SHAPE (`pm_<uuid>.<secret>`, `tokens.parse`) is checked first now. The legacy operator secret
    never needed a connection either: it is a constant-time compare."""
    def _no_postgres():
        raise AssertionError("a malformed bearer opened a Postgres connection")

    monkeypatch.setattr(deps, "sync_conn", _no_postgres)
    generic = {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}
    for bad in ("not-even-a-token", "pm_", "pm_nodot", "pm_not-a-uuid.secret", "pm_.secret", ""):
        r = await client.get("/read", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401 and r.json() == generic, f"{bad!r} was not the generic 401"
    assert (await client.post("/activate", headers={"Authorization": f"Bearer {settings.api_secret_key}"})).status_code == 200


async def test_a_well_formed_but_unknown_token_still_asks_postgres(client, conn, redis, monkeypatch):
    """The other side of the same lever: a token that looks real must still be looked up, once.
    (Rate-limiting that path is I4's perf work, not this task's.)"""
    from uuid import uuid4

    opened = []
    real = deps.sync_conn

    def _tracked():
        c = real()
        opened.append(c)
        return c

    monkeypatch.setattr(deps, "sync_conn", _tracked)
    r = await client.get("/read", headers={"Authorization": f"Bearer pm_{uuid4()}.no-such-secret"})
    assert r.status_code == 401
    assert len(opened) == 1 and db.sync_pool_in_use() == 0


async def test_revoking_an_accounts_sessions_makes_the_next_request_the_generic_401(client, conn, redis):
    """The carried 403-vs-401 question, pinned (fix round 2 ruling). A LIVE session whose account
    has been suspended or revoked gets `403 FORBIDDEN`, not the generic 401 — the brief's own given
    test asserts that, and nothing new leaks by saying so, because the caller already holds that
    account's session cookie. The generic body arrives one step later: I5 revokes the account's
    sessions as part of the same decision (`S.revoke_all`, which is `invalidate_account` plus the
    `revoked_at` write — note that `invalidate_account` ALONE only drops the principal cache, so
    the cookie still resolves and the answer is still 403). After `revoke_all` the cookie resolves
    to nothing at all and the response is byte-identical to one carrying no credential."""
    aid = _member(conn, ["buyer"]); raw = S.create(conn, redis, aid, None, None)
    assert (await _as(client, pm_session=raw).get("/read")).status_code == 200
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET state='suspended' WHERE id=%s", (aid,))
    S.invalidate_account(redis, aid)
    dead_account = await _as(client, pm_session=raw).get("/read")
    assert dead_account.status_code == 403 and dead_account.json()["error"]["code"] == "FORBIDDEN"

    S.revoke_all(conn, redis, aid)
    revoked = await _as(client, pm_session=raw).get("/read")
    anonymous = await _as(client).get("/read")
    assert revoked.status_code == anonymous.status_code == 401
    assert revoked.json() == anonymous.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}
    assert revoked.headers.get("www-authenticate") == anonymous.headers.get("www-authenticate")
