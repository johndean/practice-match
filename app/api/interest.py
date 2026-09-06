"""POST /api/interest — the Coming Soon page's launch-notification sign-up (spec 2026-09-06).

Failure policy (11c fix round 1): FAIL CLOSED. When Redis (the rate limiter) or Postgres is unreachable the
request is answered 503 {"error": "unavailable"} and nothing is stored; the page shows its generic retry copy.
Failures are logged by exception type only — an address never reaches a log line."""
from __future__ import annotations

import json
import logging
import re
import unicodedata

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.requests import ClientDisconnect

from app.auth.limits import client_ip as _client_ip
from app.checks import async_dsn
from app.config import settings
from app.db import get_engine, get_redis
from app.ratelimit import hit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
CONSENT_VERSION = "coming-soon-v1"  # the page's promise: one message when it launches, never shared
# Conservative on purpose: one @, a dot and an alphabetic TLD in the domain, no whitespace, no ASCII control
# characters (U+0000 cannot be stored in Postgres text; U+0001-U+001F and U+007F would be stored verbatim),
# no Unicode bidi controls (U+200E/F, U+202A-E, U+2066-9). Quoting, brackets and emoji are left to the consumer
# to escape (Wave 2a) — rejecting them would reject valid addresses.
_FORBIDDEN = r"\s@\x00-\x1f\x7f\u200b-\u200d\u200e\u200f\u202a-\u202e\u2066-\u2069"  # + zero-width space/joiners U+200B-D (N10)
EMAIL_RE = re.compile(rf"^[^{_FORBIDDEN}]+@[^{_FORBIDDEN}]+\.[A-Za-z]{{2,}}$")
MAX_EMAIL_LEN = 254
MAX_BODY_BYTES = 4096  # a JSON object holding one address; anything larger is not this form (F9)
LIMITS: dict[str, tuple[int, int]] = {"ip_minute": (5, 60), "ip_day": (30, 86_400), "email_day": (3, 86_400)}
INSERT = text(
    "INSERT INTO interest_signup (email, email_normalised, consent_version, source) "
    "VALUES (:email, :norm, :consent, 'coming-soon') ON CONFLICT (email_normalised) DO NOTHING"
)


def normalise(email: str) -> tuple[str, str] | None:
    """(address as typed, trimmed; normalised key) or None when invalid. NFKC first, so composed and
    decomposed spellings of one address cannot occupy two rows (M2); the length check runs before the regex."""
    e = unicodedata.normalize("NFKC", email).strip()
    if len(e) > MAX_EMAIL_LEN or not EMAIL_RE.match(e):
        return None
    return e, e.lower()


def client_ip(request: Request) -> str:
    """The client as Railway's edge saw it, computed exactly as uvicorn does under `--forwarded-allow-ips='*'`:
    repeated X-Forwarded-For lines are joined, the FIRST field is the client, a port on it is stripped, and an
    empty first field (or no header) means the peer address. Verified live on QA (2026-09-06, Task 11f Step 4b):
    Railway writes the accepted client first and leaves caller-supplied values after it — six spoofed sign-ups
    were limited on the sixth, with one header line and with two. DEPLOY.md carries the probe.

    The rule itself now lives in `app.auth.limits.client_ip` (Task I3), so `require`/`audit.write` share the
    exact same implementation instead of a second copy; this wrapper only keeps this module's own public name
    and its never-None ("unknown" peer) return type, so every existing caller/test here is unaffected."""
    ip = _client_ip(request)
    return ip if ip is not None else "unknown"


def declared_length(request: Request) -> int | None:
    """Content-Length as an int (0 when absent — chunked bodies are capped while streaming); None when the
    header is not a plain decimal number. isdecimal(), not isdigit(): "²".isdigit() is True but int("²") raises (N4)."""
    value = request.headers.get("content-length", "0").strip()
    return int(value) if value.isdecimal() else None


async def _read_capped(request: Request) -> bytes | None:
    """The body, or None once more than MAX_BODY_BYTES have arrived. Chunked requests declare no length, so the
    cap is enforced while streaming rather than after buffering the whole body (N3)."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status)


def _email_from(raw: bytes) -> str | None:
    """The `email` string from a JSON object body, or None for anything else — one 422 body for every
    malformed request instead of FastAPI's echoing `detail` envelope (F4)."""
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    email = payload.get("email") if isinstance(payload, dict) else None
    return email if isinstance(email, str) else None


@router.post("/interest", status_code=202)
async def interest(request: Request) -> JSONResponse:
    declared = declared_length(request)
    if declared is None or declared > MAX_BODY_BYTES:
        return _error("too_large", 413)
    try:
        raw = await _read_capped(request)
    except ClientDisconnect:
        return _error("invalid_email", 422)  # the caller went away mid-body: not an error, not a 500 (O2)
    if raw is None:
        return _error("too_large", 413)
    email = _email_from(raw)
    parsed = normalise(email) if email is not None else None
    if parsed is None:
        return _error("invalid_email", 422)
    as_typed, norm = parsed
    ip = client_ip(request)
    try:
        redis_ = get_redis(settings.redis_url)
        for scope, subject in (("ip_minute", ip), ("ip_day", ip), ("email_day", norm)):
            limit, window = LIMITS[scope]
            if not await hit(redis_, scope, subject, limit, window):
                return _error("rate_limited", 429)
        engine = get_engine(async_dsn(settings.database_url))
        async with engine.begin() as conn:
            await conn.execute(INSERT, {"email": as_typed, "norm": norm, "consent": CONSENT_VERSION})
    except Exception as exc:  # noqa: BLE001 — fail closed: any limiter or store failure is a 503, logged by type only (never the address)
        logger.warning("interest sign-up unavailable: %s.%s", type(exc).__module__, type(exc).__name__)
        return _error("unavailable", 503)
    return JSONResponse({"status": "ok"}, status_code=202)
