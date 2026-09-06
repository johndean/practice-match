"""Who is calling and what may they do (spec §3-§4). Session cookie -> `api_token` -> legacy
operator bearer (until Task I9 deletes the legacy path)."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

import fastapi.applications
from fastapi import HTTPException, Request
from fastapi.exception_handlers import http_exception_handler as _default_http_exception_handler
from fastapi.responses import Response
from starlette.responses import JSONResponse

from app.auth import permissions as PM
from app.auth import sessions as S
from app.auth import tokens as T
from app.auth.limits import client_ip
from app.cache import sync_redis
from app.config import settings
from app.db import sync_conn

__all__ = ["check_origin_and_csrf", "client_ip", "current_principal", "require"]

REAUTH_WINDOW = timedelta(minutes=10)
LEGACY_ADMIN = UUID("00000000-0000-0000-0000-000000000001")


async def _shaped_or_default_http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """`_err()` below raises `HTTPException(status, detail={"error": {"code": ..., "message": ...}})`
    and every caller of `require()` (this file's own tests included, which build a bare `FastAPI()`
    with no exception handler of their own) expects that `detail` dict verbatim as the WHOLE response
    body — FastAPI's own default handler always wraps it as `{"detail": ...}` instead, and a
    `require()`-guarded route's dependency has no reference to whichever `FastAPI()` instance
    eventually mounts it, so there is no per-app hook here to register a handler on. Replacing
    FastAPI's own default (used by every `FastAPI()` constructed after this module is imported,
    `app.main.create_app()`'s included) is the one place this can be done once; it only changes
    the response for OUR shape (a dict `detail` carrying an "error" key) — anything else (FastAPI's
    own 404s and validation errors, a plain string detail, a third-party router) falls straight
    through to FastAPI's ordinary handling, unchanged."""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(exc.detail, status_code=exc.status_code, headers=exc.headers)
    return await _default_http_exception_handler(request, exc)


# Replacing FastAPI's own module-level default on purpose, see the docstring above; mypy correctly
# flags both that fastapi.applications doesn't export this name and that our handler's exact
# exception type (fastapi's own HTTPException subclass) differs from the declared one (Starlette's).
fastapi.applications.http_exception_handler = _shaped_or_default_http_exception_handler  # type: ignore[attr-defined,assignment]


def current_principal(request: Request) -> S.Principal | None:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        raw = auth[7:]
        if settings.api_secret_key and raw == settings.api_secret_key:
            return S.Principal(LEGACY_ADMIN, "active", frozenset({"admin"}), datetime.now(UTC), "legacy")
        with sync_conn() as conn:
            ap = T.verify_api_token(conn, raw)
        return S.Principal(ap.token_id, "active", frozenset({ap.role}), None, "token") if ap else None
    session_raw = request.cookies.get("pm_session")
    if not session_raw:
        return None
    r = sync_redis()
    with sync_conn() as conn:
        p = S.resolve(conn, r, session_raw)
        if p:
            S.touch(conn, p)
    return p


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error": {"code": code, "message": message}})


def check_origin_and_csrf(request: Request, principal: S.Principal | None) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS") or principal is None or principal.kind != "session":
        return
    token = request.headers.get("x-csrf-token")
    if not token or token != request.cookies.get("pm_csrf"):
        raise _err(403, "CSRF", "Missing or mismatched X-CSRF-Token.")
    origin = request.headers.get("origin") or request.headers.get("referer")
    host = urlparse(origin).hostname if origin else None
    allowed_hosts = {urlparse(o).hostname for o in settings.origins} | {request.url.hostname}
    if host not in allowed_hosts:
        raise _err(403, "ORIGIN", "Cross-origin request refused.")


def require(perm: str) -> Callable[[Request], S.Principal | None]:
    if perm not in PM.MATRIX:
        raise KeyError(f"unknown permission {perm!r}")

    def dependency(request: Request) -> S.Principal | None:
        principal = current_principal(request)
        check_origin_and_csrf(request, principal)
        if not PM.allowed(perm, principal):
            if principal is None:
                raise _err(401, "UNAUTHORIZED", "Sign in to continue.")
            raise _err(403, "FORBIDDEN", "Your account cannot do this.")
        if (
            perm in PM.REAUTH
            and principal is not None
            and principal.kind == "session"
            and (not principal.reauth_at or datetime.now(UTC) - principal.reauth_at > REAUTH_WINDOW)
        ):
            raise _err(403, "REAUTH_REQUIRED", "Confirm your password to continue.")
        request.state.principal = principal
        return principal

    return dependency
