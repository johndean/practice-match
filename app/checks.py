"""Component probes for the health endpoints. They never raise: any failure becomes
{"ok": False, "error": "..."} so /api/healthz stays 200 while Railway provisions."""
from __future__ import annotations

import asyncio
import logging
from typing import TypedDict

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

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
    # A fresh engine per call is deliberate for now; the Identity plan's app/db.py (Task I1) will own the pooled engine and this probe will use it then.
    engine = None
    try:
        engine = create_async_engine(async_dsn(url), connect_args={"timeout": TIMEOUT_S})
        async with engine.connect() as conn:
            result = await asyncio.wait_for(conn.execute(text("SELECT postgis_version()")), TIMEOUT_S)
            return {"ok": True, "postgis_version": str(result.scalar_one())}
    except Exception as exc:  # noqa: BLE001 — reported, never raised (a malformed DSN raises here too, before any connection is attempted)
        return _err(exc)
    finally:
        if engine is not None:
            await engine.dispose()


async def check_redis(url: str) -> ComponentStatus:
    client = None
    try:
        client = aioredis.from_url(  # type: ignore[no-untyped-call]  # redis-py's from_url has no annotations upstream
            url, socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S
        )
        await asyncio.wait_for(client.ping(), TIMEOUT_S)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 — a malformed URL raises here too, before any connection is attempted
        return _err(exc)
    finally:
        if client is not None:
            await client.aclose()
