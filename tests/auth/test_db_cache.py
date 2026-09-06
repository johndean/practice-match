"""Coverage for the app.db/app.cache pieces Task I1 adds that tests/auth/test_schema.py
does not exercise (it drives `conn`/`scratch_dsn`, which call psycopg2 directly, not
`db.sync_conn`/`db.engine`; and the `redis` fixture monkeypatches `cache._make_sync`/
`cache._make_async` rather than calling their real bodies). Added per John's 2026-09-06
100%-coverage ruling. The tests that talk to the real compose Postgres/Redis request
`db_ready` (M8, fix round 1) so a down service fails with its deliberate message
instead of a raw psycopg2/redis-py exception."""
from __future__ import annotations

from sqlalchemy import text

from app.cache import async_redis, sync_redis
from app.checks import async_dsn
from app.config import settings
from app.db import engine, get_engine, sync_conn


def test_sync_conn_is_an_autocommit_psycopg2_connection(db_ready):
    conn = sync_conn()
    try:
        assert conn.autocommit is True
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        conn.close()


async def test_engine_accessor_returns_the_pooled_engine_for_settings_database_url(db_ready):
    eng = engine()
    assert eng is get_engine(async_dsn(settings.database_url))
    async with eng.connect() as c:
        result = await c.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


def test_sync_redis_returns_a_working_client(db_ready):
    r = sync_redis()
    try:
        assert r.ping() is True
    finally:
        r.close()


async def test_async_redis_returns_a_working_client(db_ready):
    r = async_redis()
    try:
        assert await r.ping() is True
    finally:
        await r.aclose()


async def test_redis_fixture_intercepts_both_import_styles(redis, monkeypatch):
    """C1 fix round 1: `from app.cache import sync_redis` (used verbatim by this
    module's own top-of-file import above, and by later identity briefs I3/I4) binds
    the function object at import time; the old `redis` fixture patched the
    `cache.sync_redis`/`cache.async_redis` attributes directly, which has no effect on
    an already-bound name. `sync_redis`/`async_redis` now resolve `_make_sync`/
    `_make_async` from the module's own globals at CALL time, so patching those two
    factories intercepts every caller regardless of import style.
    `settings.redis_url` is pointed at a closed TCP port so a leak to a real client
    fails loudly (ConnectionError) instead of silently reaching the compose Redis."""
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    from app import cache

    redis.set("k", "v")
    assert cache.sync_redis().get("k") == b"v"
    assert sync_redis().get("k") == b"v"  # from-imported at this module's top
    assert await cache.async_redis().ping() is True
    assert await async_redis().ping() is True
