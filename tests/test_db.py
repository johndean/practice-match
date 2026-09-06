"""Task 5 fix round 3/4: app/db.py caches one async engine and one Redis client per
(running event loop, url) so the health probes stop paying full connection setup on
every call (that cost ~100ms once Postgres/Redis were reachable — see
tests/perf/test_api_latency.py). Disposal is the test suite's `_dispose_pools` autouse
fixture (tests/conftest.py) and the app's own lifespan (app/main.py) — never a
monkeypatched `loop.close` (round 4: production code must not do that)."""
from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import db
from app.checks import async_dsn, check_db, check_redis
from app.config import settings
from app.db import get_engine

DSN = async_dsn(settings.database_url)
OTHER_DSN = "postgresql+asyncpg://x:x@127.0.0.1:1/x"
REDIS_URL = settings.redis_url


async def test_get_engine_is_cached_per_url_and_distinct_across_urls():
    first = db.get_engine(DSN)
    second = db.get_engine(DSN)
    other = db.get_engine(OTHER_DSN)
    assert first is second
    assert first is not other


async def test_dispose_all_clears_the_cache_so_the_next_call_is_fresh():
    first = db.get_engine(DSN)
    await db.dispose_all()
    second = db.get_engine(DSN)
    assert first is not second


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


async def test_get_engine_does_not_monkeypatch_the_loops_close():
    """Round 4: John's ruling — production code must not monkeypatch `loop.close`.
    Pool disposal is the `_dispose_pools` autouse fixture (tests) and the app lifespan
    (production), never an event-loop close hook."""
    loop = asyncio.get_running_loop()
    original_close = loop.close
    db.get_engine(DSN)
    assert loop.close == original_close  # bound methods aren't `is`-stable across attribute reads; `==` compares __self__/__func__


async def test_get_engine_passes_a_connect_timeout(monkeypatch):
    captured = {}
    original_create = db.create_async_engine

    def spy(url, **kwargs):
        captured.update(kwargs)
        return original_create(url, **kwargs)

    monkeypatch.setattr(db, "create_async_engine", spy)
    db.get_engine(DSN)
    assert captured.get("connect_args") == {"timeout": db.TIMEOUT_S}


async def test_get_redis_passes_socket_timeouts(monkeypatch):
    captured = {}
    original_from_url = db.aioredis.from_url

    def spy(url, **kwargs):
        captured.update(kwargs)
        return original_from_url(url, **kwargs)

    monkeypatch.setattr(db.aioredis, "from_url", spy)
    db.get_redis(REDIS_URL)
    assert captured.get("socket_connect_timeout") == db.TIMEOUT_S
    assert captured.get("socket_timeout") == db.TIMEOUT_S


async def test_check_db_and_check_redis_time_out_against_a_black_hole():
    """A host that accepts the TCP connection but never replies must not hang a probe
    toward asyncpg's/redis-py's driver defaults (60s / no timeout) — belt-and-braces:
    app.db's connect_args/socket timeouts AND app.checks' outer wait_for."""
    never = asyncio.Event()
    writers: list[asyncio.StreamWriter] = []

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writers.append(writer)
        try:
            await never.wait()
        except asyncio.CancelledError:
            pass

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    before_tasks = asyncio.all_tasks()
    try:
        t0 = time.perf_counter()
        db_result = await check_db(f"postgresql+asyncpg://x:x@127.0.0.1:{port}/x")
        db_elapsed = time.perf_counter() - t0

        t0 = time.perf_counter()
        redis_result = await check_redis(f"redis://127.0.0.1:{port}/0")
        redis_elapsed = time.perf_counter() - t0
    finally:
        never.set()
        leftover = asyncio.all_tasks() - before_tasks
        for task in leftover:
            task.cancel()
        if leftover:
            await asyncio.gather(*leftover, return_exceptions=True)
        for writer in writers:
            writer.close()
        server.close()
        await server.wait_closed()

    budget = db.TIMEOUT_S + 2
    print(f"\ncheck_db against black hole: {db_result} in {db_elapsed:.2f}s")
    print(f"check_redis against black hole: {redis_result} in {redis_elapsed:.2f}s")

    assert db_result["ok"] is False
    assert db_elapsed < budget, f"check_db took {db_elapsed:.2f}s against a black hole"
    assert redis_result["ok"] is False
    assert redis_elapsed < budget, f"check_redis took {redis_elapsed:.2f}s against a black hole"


async def test_engine_errors_never_carry_bound_parameters(db_ready):
    """11c review F3: SQLAlchemy's own `[parameters: ...]` echo is suppressed (hide_parameters), so a failed
    statement's text never carries a bound value. The statement's driver message must not itself embed the
    value (asyncpg's DataError messages do — that channel is guarded at the endpoint, which logs exception
    types only; see tests/api/test_interest.py), so the assertion discriminates on the echo alone."""
    engine = get_engine(async_dsn(settings.database_url))
    with pytest.raises(DBAPIError) as info:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1 FROM no_such_table WHERE x = :p"), {"p": "victim-address@example.org"})
    assert "no_such_table" in str(info.value)
    assert "victim-address@example.org" not in str(info.value)
