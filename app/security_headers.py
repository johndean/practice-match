"""The four response headers every answer carries (spec §3). `setdefault`, not assignment: a route
that has deliberately set one of these for itself keeps its own value."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Added LAST in `create_app()` so it is the OUTERMOST user middleware: Starlette's
    `add_middleware` prepends, so anything added after it wraps it — which is how CORS ended up
    outside and preflight responses shipped with no HSTS at all (I4 fix round 1, Minor 2)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for k, v in HEADERS.items():
            response.headers.setdefault(k, v)
        return response


async def server_error(request: Request, exc: Exception) -> Response:
    """The 500 body, carrying the four headers.

    `ServerErrorMiddleware` sits OUTSIDE every user middleware, so the response it generates for an
    unhandled exception never passes through the middleware above — it shipped `text/plain
    "Internal Server Error"` with no security headers (Minor 2, second half). Registering this as
    the handler for `Exception` is what puts them back; Starlette still re-raises afterwards, so
    the traceback still reaches the logs."""
    return JSONResponse({"error": {"code": "INTERNAL", "message": "Something went wrong."}}, status_code=500, headers=dict(HEADERS))
