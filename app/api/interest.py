"""POST /api/interest — the Coming Soon page's launch-notification sign-up (spec 2026-09-06)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.checks import async_dsn
from app.config import settings
from app.db import get_engine, get_redis
from app.ratelimit import hit

router = APIRouter(prefix="/api")
CONSENT_VERSION = "coming-soon-v1"  # the page's promise: one message when it launches, never shared
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$")
LIMITS: dict[str, tuple[int, int]] = {"ip_minute": (5, 60), "ip_day": (30, 86_400), "email_day": (3, 86_400)}


class InterestIn(BaseModel):
    email: str


def normalise(email: str) -> str | None:
    e = email.strip()
    if len(e) > 254 or not EMAIL_RE.match(e):
        return None
    return e.lower()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/interest", status_code=202)
async def interest(body: InterestIn, request: Request) -> JSONResponse:
    norm = normalise(body.email)
    if norm is None:
        return JSONResponse({"error": "invalid_email"}, status_code=422)
    redis_ = get_redis(settings.redis_url)
    ip = client_ip(request)
    for scope, subject in (("ip_minute", ip), ("ip_day", ip), ("email_day", norm)):
        limit, window = LIMITS[scope]
        if not await hit(redis_, scope, subject, limit, window):
            return JSONResponse({"error": "rate_limited"}, status_code=429)
    engine = get_engine(async_dsn(settings.database_url))
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO interest_signup (email, email_normalised, consent_version, source) "
                "VALUES (:email, :norm, :consent, 'coming-soon') ON CONFLICT (email_normalised) DO NOTHING"
            ),
            {"email": body.email.strip(), "norm": norm, "consent": CONSENT_VERSION},
        )
    return JSONResponse({"status": "ok"}, status_code=202)
