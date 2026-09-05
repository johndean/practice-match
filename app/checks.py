"""Component probes for the health endpoints. They never raise: any failure becomes
{"ok": False, "error": "..."} so /api/healthz stays 200 while Railway provisions."""
from __future__ import annotations

import asyncio
import logging
from typing import TypedDict

from sqlalchemy import text

from app.db import get_engine, get_redis

TIMEOUT_S = 3.0

logger = logging.getLogger(__name__)


class ComponentStatus(TypedDict, total=False):
    ok: bool
    postgis_version: str
    error: str


def async_dsn(url: str) -> str:
    """Railway hands out postgresql://…; SQLAlchemy's asyncpg dialect wants postgresql+asyncpg://…"""
    return url if url.startswith("postgresql+asyncpg://") else url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _err(exc: Exception) -> ComponentStatus:
    logger.warning("health check failed: %s", exc)
    return {"ok": False, "error": type(exc).__name__}


async def check_db(url: str) -> ComponentStatus:
    # The engine is pooled per (event loop, url) in app.db (Task 5 fix round 3); no
    # per-call dispose() — the pooled engine lives for the loop.
    try:
        engine = get_engine(async_dsn(url))
        async with engine.connect() as conn:
            result = await asyncio.wait_for(conn.execute(text("SELECT postgis_version()")), TIMEOUT_S)
            return {"ok": True, "postgis_version": str(result.scalar_one())}
    except Exception as exc:  # noqa: BLE001 — reported, never raised (a malformed DSN raises here too, before any connection is attempted)
        return _err(exc)


async def check_redis(url: str) -> ComponentStatus:
    # The client is pooled per (event loop, url) in app.db (Task 5 fix round 3); no
    # per-call aclose() — the pooled client lives for the loop.
    try:
        client = get_redis(url)
        await asyncio.wait_for(client.ping(), TIMEOUT_S)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 — a malformed URL raises here too, before any connection is attempted
        return _err(exc)
