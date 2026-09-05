"""Per-(event loop, URL) cache for the async Postgres engine and Redis client shared by
the health probes (Task 5 fix round 3 — the Identity plan's Task I1 module pulled
forward; that plan now extends this module instead of creating it).

A fresh async engine and a fresh Redis client per health check cost ~100ms once
Postgres/Redis were actually reachable (Task 6), blowing the /api/healthz p95 budget —
it only held in Task 5 because a refused connection fails instantly. One instance per
running event loop fixes that without ever sharing a connection across loops (asyncpg
and redis-py connections are bound to the loop that opened them).

Entries live in a WeakKeyDictionary keyed by event loop. The long-lived case (the real
app under uvicorn, one loop for the process) is cleaned up by `dispose_all()`, called
from `app.main`'s lifespan on shutdown. Short-lived loops (pytest-asyncio hands each
test its own, closed at teardown) never call that — so the first `get_engine`/
`get_redis` on a given loop also hooks that loop's own `close()` to dispose this
module's entries for it synchronously, the moment something closes it. Without that
hook, a closed loop's still-open asyncpg/redis connections would only be reclaimed by
a later, unrelated garbage-collection pass — raising ResourceWarning attributed to
whatever test happened to be running at the time.
"""
from __future__ import annotations

import asyncio
import weakref

import redis.asyncio as aioredis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_engines: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, AsyncEngine]] = weakref.WeakKeyDictionary()
_redis_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, Redis]] = weakref.WeakKeyDictionary()
_hooked_loops: weakref.WeakSet[asyncio.AbstractEventLoop] = weakref.WeakSet()


def _dispose_loop_entries(loop: asyncio.AbstractEventLoop) -> None:
    """Synchronously disposes whatever `loop` has cached. Only called on a loop that
    is not (yet) closed, so `run_until_complete` is safe here."""
    engines = _engines.pop(loop, {})
    clients = _redis_clients.pop(loop, {})
    if not engines and not clients:
        return

    async def _cleanup() -> None:
        for engine in engines.values():
            await engine.dispose()
        for client in clients.values():
            await client.aclose()

    loop.run_until_complete(_cleanup())


def _hook_loop_close(loop: asyncio.AbstractEventLoop) -> None:
    """Wraps `loop.close` (once per loop) so this module's cache for it is disposed
    synchronously right before the loop actually closes."""
    if loop in _hooked_loops:
        return
    _hooked_loops.add(loop)
    original_close = loop.close

    def close_and_dispose() -> None:
        if not loop.is_closed():
            _dispose_loop_entries(loop)
        original_close()

    loop.close = close_and_dispose  # type: ignore[method-assign]


def get_engine(url: str) -> AsyncEngine:
    """One AsyncEngine per (running loop, url), created lazily on first use."""
    loop = asyncio.get_running_loop()
    _hook_loop_close(loop)
    engines = _engines.setdefault(loop, {})
    engine = engines.get(url)
    if engine is None:
        engine = create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
        engines[url] = engine
    return engine


def get_redis(url: str) -> Redis:
    """One Redis client per (running loop, url), created lazily on first use."""
    loop = asyncio.get_running_loop()
    _hook_loop_close(loop)
    clients = _redis_clients.setdefault(loop, {})
    client = clients.get(url)
    if client is None:
        client = aioredis.from_url(url)  # type: ignore[no-untyped-call]  # redis-py's from_url has no annotations upstream
        clients[url] = client
    return client


async def dispose_all() -> None:
    """Disposes every engine/client cached for the CURRENT running loop (this is what
    a real app's shutdown calls). Entries for other loops cannot be safely awaited from
    here — that loop may already be closed — so they are dropped from the cache
    instead; in practice `_hook_loop_close` has already disposed them by the time their
    loop closed."""
    current = asyncio.get_running_loop()
    for loop in list(_engines.keys()):
        engines = _engines.pop(loop, {})
        if loop is current:
            for engine in engines.values():
                await engine.dispose()
    for loop in list(_redis_clients.keys()):
        clients = _redis_clients.pop(loop, {})
        if loop is current:
            for client in clients.values():
                await client.aclose()
