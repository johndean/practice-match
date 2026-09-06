"""Who is calling and what may they do (spec §3-§4). Session cookie -> `api_token` -> legacy
operator bearer (until Task I9 deletes the legacy path)."""
from __future__ import annotations

import inspect
import ipaddress
import secrets
import weakref
from collections.abc import Callable, Mapping
from contextlib import closing
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlparse
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.responses import JSONResponse

from app.auth import permissions as PM
from app.auth import sessions as S
from app.auth import tokens as T
from app.cache import sync_redis
from app.config import settings
from app.db import sync_conn

__all__ = [
    "AuthError",
    "CsrfFailed",
    "OriginRefused",
    "PermissionDenied",
    "RateLimited",
    "ReauthRequired",
    "Unauthenticated",
    "check_origin_and_csrf",
    "client_ip",
    "current_principal",
    "install",
    "permission_of",
    "require",
]

REAUTH_WINDOW = timedelta(minutes=10)
LEGACY_ADMIN = UUID("00000000-0000-0000-0000-000000000001")


class AuthError(HTTPException):
    """Every refusal this module raises, carrying decision A5's `code` and `message`.

    Fix round 1, ruling (a) / Important 6: the first implementation reshaped the response by
    replacing FastAPI's own module-level default handler at import time, which only reached apps
    constructed AFTER `app.auth.deps` was first imported — a process that touched `app.main` first
    served the wrong body with a green test suite. There is now one exception type and one handler,
    registered on the app by `install()`; an `HTTPException` raised anywhere else in the app keeps
    FastAPI's ordinary `{"detail": ...}` body, which is the point of a dedicated class.
    """

    status = 403
    code = "FORBIDDEN"
    message = "Your account cannot do this."

    def __init__(self, headers: Mapping[str, str] | None = None) -> None:
        super().__init__(self.status, detail={"error": {"code": self.code, "message": self.message}}, headers=dict(headers) if headers else None)


class Unauthenticated(AuthError):
    """No usable credential at all — the generic 401 (spec §3: identical for missing and invalid)."""

    status = 401
    code = "UNAUTHORIZED"
    message = "Sign in to continue."


class PermissionDenied(AuthError):
    """A known principal whose effective roles do not carry the permission (spec §4)."""


class CsrfFailed(AuthError):
    """A cookie-authenticated state change without a matching `X-CSRF-Token` double-submit."""

    code = "CSRF"
    message = "Missing or mismatched X-CSRF-Token."


class OriginRefused(AuthError):
    """A cookie-authenticated state change whose `Origin`/`Referer` is not the site."""

    code = "ORIGIN"
    message = "Cross-origin request refused."


class ReauthRequired(AuthError):
    """A `permissions.REAUTH` action without a fresh password confirmation (spec §3)."""

    code = "REAUTH_REQUIRED"
    message = "Confirm your password to continue."


class RateLimited(AuthError):
    """A fixed-window counter in `app.auth.limits` said no. Defined here, with the rest of the
    hierarchy, so `install()`'s single handler renders its A5 body and its `Retry-After` too."""

    status = 429
    code = "RATE_LIMITED"
    message = "Too many attempts. Try again later."

    def __init__(self, retry_after: int) -> None:
        super().__init__(headers={"Retry-After": str(retry_after)})


async def _auth_error_handler(request: Request, exc: Exception) -> Response:
    """Renders `AuthError` as decision A5's body. `exc` is typed `Exception` because that is what
    Starlette's handler protocol declares; `install()` registers this for `AuthError` alone, so the
    cast is what the registration already guarantees (and costs no branch that could go uncovered).
    `exc.headers` is passed through so `Retry-After` (429) and any `WWW-Authenticate` survive."""
    err = cast("AuthError", exc)
    return JSONResponse(err.detail, status_code=err.status_code, headers=err.headers)


INVALID_REQUEST = {"error": {"code": "INVALID_REQUEST", "message": "The request could not be understood. Check the fields and try again."}}


async def _validation_error_handler(request: Request, exc: Exception) -> Response:
    """Decision A5's envelope for a request FastAPI itself refused — a field of the wrong type, a
    string past its `max_length`, a body that is not JSON.

    FastAPI's own handler renders `{"detail": [...]}` and echoes the submitted value straight back,
    which was a second error envelope beside A5's (I4 fix round 1, Minor 1) and a defect of its own:
    a body carrying a lone surrogate made the ECHO unencodable, so the 422 became a 500 out of
    `ServerErrorMiddleware` carrying none of the four security headers (Critical 2). Nothing about
    the input is reflected here — not its value, not its length, not its type."""
    return JSONResponse(INVALID_REQUEST, status_code=422)


def install(app: FastAPI) -> None:
    """Registers the handlers that render decision A5's body: `AuthError` for every refusal this
    module raises, and `RequestValidationError` for the ones FastAPI raises before a handler is
    reached (`app.main.create_app()` calls this; so does every test that mounts a `require`-guarded
    route). Idempotent — re-registering the same exception class replaces the entry."""
    app.add_exception_handler(AuthError, _auth_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)


def _host_only(field: str) -> str:
    """uvicorn's `_parse_host_port` rule: `[v6]:port` and `v4:port` lose the port; a bare
    IPv6 address (more than one colon, no brackets) is returned as is."""
    if field.startswith("["):
        end = field.find("]")
        return field[1:end] if end != -1 else field
    if field.count(":") == 1:
        return field.rsplit(":", 1)[0]
    return field


def _valid_ip(value: str) -> str | None:
    """`value` if it is an IP address, else None (Minor 3). `X-Forwarded-For` is attacker-supplied
    on any request that does not pass through the edge, and the value ends up in `audit_log.ip`,
    an `inet` column: `X-Forwarded-For: unknown` used to raise InvalidTextRepresentation, losing
    the audit row and returning a 500 on the one write path that must never fail."""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return None
    return value


def client_ip(request: Any) -> str | None:
    """The shared client-IP rule — the FIRST non-empty X-Forwarded-For hop across every
    X-Forwarded-For header line, port stripped, else the peer — verified live on Railway for
    `/api/interest` (see DEPLOY.md). `app.api.interest` re-exports it so there is exactly one
    implementation: its own extensive parametrised tests drive real Starlette `Request` objects,
    whose `Headers.getlist` sees every repeated header line, while `deps`/`audit` sometimes pass a
    minimal stand-in (headers as a plain mapping); the function is duck-typed so both land on the
    same rule. It lived in `app.auth.limits` until fix round 1 and is back where the brief's
    interface list puts it, now that `limits` imports `RateLimited` from here."""
    headers = request.headers
    getlist = getattr(headers, "getlist", None)
    raw = ",".join(getlist("x-forwarded-for")) if getlist is not None else (headers.get("x-forwarded-for") or "")
    first = raw.split(",")[0].strip()
    if first:
        return _valid_ip(_host_only(first))
    client = getattr(request, "client", None)
    return _valid_ip(client.host) if client else None


def current_principal(request: Request) -> S.Principal | None:
    """Session cookie -> `api_token` -> legacy operator bearer, in that order (Important 9). The
    brief's prose and the plan both give this order; its Step 3 code had `Authorization` first,
    which logged a signed-in user out whenever any `Bearer` header rode along on their request — a
    stale SDK default, a proxy, a browser extension. A cookie that resolves to nothing still falls
    through to the bearer, so a machine caller is never blocked by a dead cookie."""
    session_raw = request.cookies.get("pm_session")
    if session_raw:
        p = _session_principal(session_raw)
        if p:
            return p
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() != "bearer ":  # RFC 7235: the auth-scheme token is case-insensitive (Minor 1)
        return None
    raw = auth[7:]
    # Shape first, Postgres second (fix round 2): only a `pm_<uuid>.<secret>` can be an api token,
    # so anything else — including the legacy operator secret, which is a constant-time compare —
    # is decided without a connection. Otherwise every anonymous request carrying any Bearer
    # header cost one un-pooled connect on every guarded route.
    if T.parse(raw) is not None:
        with closing(sync_conn()) as conn, conn:
            ap = T.verify_api_token(conn, raw)
        if ap:
            # `ap.created_by`, not `ap.token_id` (Important 10): the actor an audit row must name
            # is the account that minted the token, and `verify_api_token` has already refused it
            # if that account is suspended or revoked.
            return S.Principal(ap.created_by, "active", frozenset({ap.role}), None, "token")
    if _matches(raw, settings.api_secret_key):
        return S.Principal(LEGACY_ADMIN, "active", frozenset({"admin"}), datetime.now(UTC), "legacy")
    return None


def _session_principal(session_raw: str) -> S.Principal | None:
    """Redis first, Postgres only on a miss (Critical 3). A warm cache costs one GET (~25 us); the
    old code opened, authenticated and tore down a Postgres connection (~34 ms) before asking the
    cache whether it needed one. `closing(...)` is what actually returns the socket — psycopg2's
    own `with conn:` is the TRANSACTION manager and commits without closing (ruling (c)) — so both
    are used: `conn` commits the `touch`, `closing` closes the connection.

    Skipping `S.touch` on a cache hit costs nothing: the cache lives 60 s (`S.CACHE_TTL`) and
    `touch` only writes when `last_seen_at` is older than 5 minutes (`S.TOUCH_EVERY`), so a session
    in continuous use still passes through the miss half far more often than it could go stale."""
    r = sync_redis()
    cached = S.resolve_cached(r, session_raw)
    if cached:
        return cached
    with closing(sync_conn()) as conn, conn:
        p = S.resolve(conn, r, session_raw)
        if p:
            S.touch(conn, p)
    return p


def _matches(presented: str | None, secret: str | None) -> bool:
    """Constant-time equality for the two secrets this module compares directly: the legacy
    operator key and the CSRF double-submit (Important 7 — `str.__eq__` short-circuits on the
    first differing byte). Encoded first, because `secrets.compare_digest` raises TypeError on a
    non-ASCII str and a forged header arrives latin-1-decoded: a refusal, never a 500. An
    absent/empty value on either side is a refusal before any comparison — its length is not a
    secret."""
    if not presented or not secret:
        return False
    return secrets.compare_digest(presented.encode(), secret.encode())


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin_key(url: str) -> str | None:
    """An origin's comparable identity, RFC 6454's (scheme, host, port) written as
    `scheme://host[:port]` with a default port dropped; None for anything that is not one (an
    opaque `null`, a bare scheme, a port that is not a number).

    Minor 2: the first implementation compared `urlparse(...).hostname` only, so scheme and port
    were discarded and `http://qa.foundation.vin` was accepted on an https request. None is never
    put in the allowlist, so an unparseable Origin can never match an unparseable allowed origin."""
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:  # urlparse defers the port to attribute access; a forged header must not 500
        return None
    if not parsed.scheme or not parsed.hostname:
        return None
    suffix = "" if port is None or port == _DEFAULT_PORTS.get(parsed.scheme) else f":{port}"
    return f"{parsed.scheme}://{parsed.hostname}{suffix}"


def check_origin_and_csrf(request: Request, principal: S.Principal | None) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS") or principal is None or principal.kind != "session":
        return
    if not _matches(request.headers.get("x-csrf-token"), request.cookies.get("pm_csrf")):
        raise CsrfFailed
    origin = request.headers.get("origin") or request.headers.get("referer")
    presented = _origin_key(origin) if origin else None
    allowed = {_origin_key(o) for o in (*settings.origins, str(request.url))} - {None}
    if presented is None or presented not in allowed:
        raise OriginRefused


_PERMISSION_OF: weakref.WeakKeyDictionary[Any, str] = weakref.WeakKeyDictionary()


def permission_of(dependency: Any) -> str | None:
    """The permission a `require(...)` dependency enforces, or None for anything that is not one.

    Fix round 1, Important 8: a route's guard has to be readable from its dependant tree for
    `tests/auth/test_permissions.py`'s route-guard and audit drift tests to mean anything (and
    I5's `GET /api/admin/permissions` can read it the same way). A registry rather than an
    attribute on the closure because both spellings of that are barred here — ruff's B010 rejects
    `setattr` with a constant name, mypy --strict rejects assigning an attribute a function does
    not declare, and neither `noqa` nor `type: ignore` is allowed. One entry per guarded route,
    written once at wiring time, and weakly held so a discarded route's closure still goes away.

    Fix round 2, NEW-5: `inspect.unwrap` first, because the registry is keyed by object IDENTITY.
    A `functools.wraps` wrapper around a guard — the obvious way to decorate one — would otherwise
    resolve to None, and the audit drift test only watches routes whose permission it can read, so
    the wrapped route would silently stop being watched. Unwrapping keeps it readable; a wrapper
    that breaks the chain is caught by that test failing closed."""
    return _PERMISSION_OF.get(inspect.unwrap(dependency))


def require(perm: str) -> Callable[[Request], S.Principal | None]:
    """A FastAPI dependency that resolves the caller, enforces Origin/CSRF on state changes, checks
    `perm` against the matrix and enforces re-authentication for `permissions.REAUTH`.

    Returns `Principal | None`, not `Principal` (Minor 4): `page.gate` is granted to `anonymous`,
    and so is `market.read` while MARKET_DATA_PUBLIC, so an anonymous caller passes the check and
    there is no principal to hand back. Only those permissions can yield None — for every other
    permission an anonymous caller has already been refused with a 401 — but `Depends()` types as
    `Any`, so a handler annotating `principal: Principal` gets None with no complaint from mypy.
    Annotate `Principal | None` on an anonymous-allowed route.

    Unknown permissions raise `KeyError` at wiring time (import time), not at request time."""
    if perm not in PM.MATRIX:
        raise KeyError(f"unknown permission {perm!r}")

    def dependency(request: Request) -> S.Principal | None:
        principal = current_principal(request)
        check_origin_and_csrf(request, principal)
        if not PM.allowed(perm, principal):
            if principal is None:
                raise Unauthenticated
            raise PermissionDenied
        # Fail CLOSED for every kind that cannot re-authenticate (Critical 2). A `token` principal
        # has no password to confirm, so "not a session" is a refusal, not an exemption; the
        # `legacy` operator secret is the one exemption and the brief time-boxes it to I9.
        if (
            perm in PM.REAUTH
            and principal is not None
            and principal.kind != "legacy"
            and (principal.kind != "session" or not principal.reauth_at or datetime.now(UTC) - principal.reauth_at > REAUTH_WINDOW)
        ):
            raise ReauthRequired
        request.state.principal = principal
        return principal

    _PERMISSION_OF[dependency] = perm
    return dependency
