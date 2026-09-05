"""Component probes for the health endpoints. They never raise: any failure becomes
{"ok": False, "error": "..."} so /api/healthz stays 200 while Railway provisions."""
from __future__ import annotations

import asyncio
import logging
from typing import TypedDict

from sqlalchemy import text

from app.db import TIMEOUT_S, get_engine, get_redis

logger = logging.getLogger(__name__)


class ComponentStatus(TypedDict, total=False):
    ok: bool
    postgis_version: str
    error: str


def async_dsn(url: str) -> str:
    """SQLAlchemy's asyncpg dialect wants postgresql+asyncpg://…. Railway's PostGIS
    template hands out the legacy postgres:// scheme (not postgresql://, despite what
    this docstring used to claim) — libpq/psycopg2 accept both, SQLAlchemy 2.x's
    `postgres` dialect alias does not exist, so it must be rewritten before the
    dialect-suffix rewrite below (fix round 5)."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url if url.startswith("postgresql+asyncpg://") else url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _err(exc: Exception) -> ComponentStatus:
    logger.warning("health check failed: %s", exc)
    return {"ok": False, "error": type(exc).__name__}


async def check_db(url: str) -> ComponentStatus:
    # The engine is pooled per (event loop, url) in app.db (Task 5 fix round 3); no
    # per-call dispose() — the pooled engine lives for the loop. The whole probe —
    # connection establishment AND the query — is bounded by one wait_for (round 4);
    # app.db's connect_args timeout is belt-and-braces against asyncpg's 60s default.
    try:
        engine = get_engine(async_dsn(url))

        async def _probe() -> str:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT postgis_version()"))
                return str(result.scalar_one())

        version = await asyncio.wait_for(_probe(), TIMEOUT_S)
        return {"ok": True, "postgis_version": version}
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
