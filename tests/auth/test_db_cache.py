"""Coverage for the app.db/app.cache pieces Task I1 adds that tests/auth/test_schema.py
does not exercise (it drives `conn`/`scratch_dsn`, which call psycopg2 directly, not
`db.sync_conn`/`db.engine`; and the `redis` fixture monkeypatches `cache.sync_redis`/
`cache.async_redis` rather than calling their real bodies). Added per John's 2026-09-06
100%-coverage ruling."""
from __future__ import annotations

from sqlalchemy import text

from app.cache import async_redis, sync_redis
from app.checks import async_dsn
from app.config import settings
from app.db import engine, get_engine, sync_conn


def test_sync_conn_is_an_autocommit_psycopg2_connection():
    conn = sync_conn()
    try:
        assert conn.autocommit is True
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        conn.close()


async def test_engine_accessor_returns_the_pooled_engine_for_settings_database_url():
    eng = engine()
    assert eng is get_engine(async_dsn(settings.database_url))
    async with eng.connect() as c:
        result = await c.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


def test_sync_redis_returns_a_working_client():
    r = sync_redis()
    try:
        assert r.ping() is True
    finally:
        r.close()


async def test_async_redis_returns_a_working_client():
    r = async_redis()
    try:
        assert await r.ping() is True
    finally:
        await r.aclose()
