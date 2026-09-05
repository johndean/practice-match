"""Task 5 fix round 3: app/db.py caches one async engine and one Redis client per
(running event loop, url) so the health probes stop paying full connection setup on
every call (that cost ~100ms once Postgres/Redis were reachable — see
tests/perf/test_api_latency.py)."""
from __future__ import annotations

from app import db
from app.checks import async_dsn, check_db
from app.config import settings

DSN = async_dsn(settings.database_url)
OTHER_DSN = "postgresql+asyncpg://x:x@127.0.0.1:1/x"


async def test_get_engine_is_cached_per_url_and_distinct_across_urls():
    first = db.get_engine(DSN)
    second = db.get_engine(DSN)
    other = db.get_engine(OTHER_DSN)
    assert first is second
    assert first is not other
    await db.dispose_all()


async def test_dispose_all_clears_the_cache_so_the_next_call_is_fresh():
    first = db.get_engine(DSN)
    await db.dispose_all()
    second = db.get_engine(DSN)
    assert first is not second
    await db.dispose_all()


async def test_check_db_reuses_one_engine_across_calls(monkeypatch):
    calls = []
    original_create = db.create_async_engine

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return original_create(*args, **kwargs)

    monkeypatch.setattr(db, "create_async_engine", spy)
    await check_db(settings.database_url)
    await check_db(settings.database_url)
    assert len(calls) == 1
    await db.dispose_all()
