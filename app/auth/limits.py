"""Fixed-window rate-limit helpers for the synchronous auth endpoints (signin/signup/
forgot-password, Task I4), and the shared client-IP rule.

`hit()` is the same fixed-window shape as `app.ratelimit.hit` (INCR then EXPIRE only on
the very first hit, so a key always carries a TTL even if the process dies between the
two commands) — adapted here for a synchronous Redis client (`app.cache.sync_redis()`,
which is what a `require`/session-cookie request holds) and raising the shared 429
response instead of returning a bool. It is not a second, differently-shaped counter:
the auth endpoints call it with a single, already-scoped key (e.g. `f"rl:signin:ip:{ip}"`)
the same way `app.ratelimit.bucket_key` scopes its own keys.

`client_ip` implements the spec's client-IP rule — FIRST non-empty X-Forwarded-For hop
across every X-Forwarded-For header line, port stripped, else the peer — verified live
on Railway for `/api/interest` (see DEPLOY.md). `app.api.interest` re-exports this same
function (Task I3) so there is exactly one implementation; its own extensive parametrised
tests (`tests/api/test_interest.py`) exercise it against real Starlette `Request` objects,
whose `Headers.getlist` sees every repeated header line. The `deps`/`audit` callers here
sometimes pass a minimal request stand-in instead (headers as a plain mapping) — the
function is duck-typed so both land on the same first-hop rule."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

SIGNIN_EMAIL, SIGNIN_IP, SIGNUP_IP, SIGNUP_EMAIL, FORGOT_EMAIL = (10, 900), (30, 900), (5, 3600), (3, 86400), (3, 3600)


def hit(r: Any, key: str, limit: int, window_s: int) -> None:
    n = r.incr(key)
    if n == 1:
        r.expire(key, window_s)
    if n > limit:
        ttl = r.ttl(key)
        raise HTTPException(
            429,
            detail={"error": {"code": "RATE_LIMITED", "message": "Too many attempts. Try again later."}},
            headers={"Retry-After": str(ttl if ttl and ttl > 0 else window_s)},
        )


def _host_only(field: str) -> str:
    """uvicorn's `_parse_host_port` rule: `[v6]:port` and `v4:port` lose the port; a bare
    IPv6 address (more than one colon, no brackets) is returned as is."""
    if field.startswith("["):
        end = field.find("]")
        return field[1:end] if end != -1 else field
    if field.count(":") == 1:
        return field.rsplit(":", 1)[0]
    return field


def client_ip(request: Any) -> str | None:
    headers = request.headers
    getlist = getattr(headers, "getlist", None)
    raw = ",".join(getlist("x-forwarded-for")) if getlist is not None else (headers.get("x-forwarded-for") or "")
    first = raw.split(",")[0].strip()
    if first:
        return _host_only(first)
    client = getattr(request, "client", None)
    return client.host if client else None
