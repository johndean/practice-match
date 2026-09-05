"""Component probes for the health endpoints. They never raise: any failure becomes
{"ok": False, "error": "..."} so /api/healthz stays 200 while Railway provisions."""
from __future__ import annotations

import asyncio

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TIMEOUT_S = 3.0


def async_dsn(url: str) -> str:
    """Railway hands out postgresql://…; SQLAlchemy's asyncpg dialect wants postgresql+asyncpg://…"""
    return url if url.startswith("postgresql+asyncpg://") else url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _err(exc: BaseException) -> dict:
    return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


async def check_db(url: str) -> dict:
    engine = create_async_engine(async_dsn(url), connect_args={"timeout": TIMEOUT_S})
    try:
        async with engine.connect() as conn:
            result = await asyncio.wait_for(conn.execute(text("SELECT postgis_version()")), TIMEOUT_S)
            return {"ok": True, "postgis_version": str(result.scalar_one())}
    except Exception as exc:  # noqa: BLE001 — reported, never raised
        return _err(exc)
    finally:
        await engine.dispose()


async def check_redis(url: str) -> dict:
    client = aioredis.from_url(url, socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S)
    try:
        await asyncio.wait_for(client.ping(), TIMEOUT_S)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    finally:
        await client.aclose()
