"""Branch-coverage edges exposed once `pyproject.toml`'s `[tool.coverage.run]` gained
`branch = true` (Task I1b, John's ruling 2026-09-06: every line AND branch). New tests
for a partial branch land here rather than in the file's usual test module, unless the
edge belongs to a file whose tests are under a concurrent fix round.
"""
from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.checks import async_dsn
from app.config import settings
from app.db import _engines, _redis_clients, dispose_all, get_engine, get_redis


def _start_foreign_loop() -> tuple[asyncio.AbstractEventLoop, threading.Thread]:
    """A second event loop, alive on its own thread, so it is never the loop
    `dispose_all()` sees as `asyncio.get_running_loop()` when called from the test's
    own (pytest-asyncio) loop."""
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def _runner() -> None:
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    ready.wait()
    return loop, thread


def _run_on[T](loop: asyncio.AbstractEventLoop, coro: Coroutine[Any, Any, T]) -> T:
    """Runs `coro` on `loop` from this (different) thread and blocks for the result —
    `loop.run_until_complete` cannot be called here directly: this thread already has
    the pytest-asyncio loop running, and asyncio refuses to nest two running loops on
    one thread."""
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=5)


async def _register(url: str, redis_url: str) -> tuple[AsyncEngine, Redis]:
    return get_engine(url), get_redis(redis_url)


async def test_dispose_all_drops_foreign_loop_entries_without_disposing_them(db_ready, monkeypatch):
    """`dispose_all()`'s `if loop is current` check (app/db.py) has two untaken edges
    whenever the whole suite only ever calls it from the loop that registered the
    entries: engines/clients registered under a loop that is NOT the one calling
    `dispose_all()`. Round 4's ruling is that such entries are never awaited from the
    wrong loop (it may already be closed) — they are simply dropped from the cache.
    This registers a real engine and a real Redis client on a second, live event loop,
    then calls `dispose_all()` from this test's own loop and proves: the foreign-loop
    engine/client are popped from the cache but never disposed, while this loop's own
    engine/client are both popped AND disposed."""
    url = async_dsn(settings.database_url)
    redis_url = settings.redis_url

    foreign_loop, foreign_thread = _start_foreign_loop()
    foreign_engine: AsyncEngine | None = None
    foreign_client: Redis | None = None
    try:
        foreign_engine, foreign_client = _run_on(foreign_loop, _register(url, redis_url))
        current_engine = get_engine(url)
        current_client = get_redis(redis_url)
        assert foreign_engine is not current_engine
        assert foreign_client is not current_client

        disposed_engines: list[AsyncEngine] = []
        orig_engine_dispose = AsyncEngine.dispose

        async def _spy_engine_dispose(self: AsyncEngine) -> None:
            disposed_engines.append(self)
            await orig_engine_dispose(self)

        closed_clients: list[Redis] = []
        orig_client_aclose = Redis.aclose

        async def _spy_client_aclose(self: Redis) -> None:
            closed_clients.append(self)
            await orig_client_aclose(self)

        monkeypatch.setattr(AsyncEngine, "dispose", _spy_engine_dispose)
        monkeypatch.setattr(Redis, "aclose", _spy_client_aclose)

        current_loop = asyncio.get_running_loop()
        assert foreign_loop in _engines and current_loop in _engines
        assert foreign_loop in _redis_clients and current_loop in _redis_clients

        await dispose_all()

        assert current_engine in disposed_engines
        assert foreign_engine not in disposed_engines
        assert current_client in closed_clients
        assert foreign_client not in closed_clients
        assert foreign_loop not in _engines and current_loop not in _engines
        assert foreign_loop not in _redis_clients and current_loop not in _redis_clients
    finally:
        # Real cleanup of the foreign-loop resources dispose_all() deliberately left
        # alone — must run on the loop that opened them (asyncpg/redis-py connections
        # are bound to their creating loop).
        if foreign_engine is not None:
            _run_on(foreign_loop, foreign_engine.dispose())
        if foreign_client is not None:
            _run_on(foreign_loop, foreign_client.aclose())
        foreign_loop.call_soon_threadsafe(foreign_loop.stop)
        foreign_thread.join(timeout=5)
        foreign_loop.close()
