"""Per-(event loop, URL) cache for the async Postgres engine and Redis client shared by
the health probes (Task 5 fix round 3 — the Identity plan's Task I1 module pulled
forward; that plan now extends this module instead of creating it).

A fresh async engine and a fresh Redis client per health check cost ~100ms once
Postgres/Redis were actually reachable (Task 6), blowing the /api/healthz p95 budget —
it only held in Task 5 because a refused connection fails instantly. One instance per
running event loop fixes that without ever sharing a connection across loops (asyncpg
and redis-py connections are bound to the loop that opened them).

Entries live in a WeakKeyDictionary keyed by event loop. Disposal is `dispose_all()`
only — called from `app.main`'s lifespan on shutdown in production, and from the test
suite's `_dispose_pools` autouse fixture (tests/conftest.py) after every test. Round 3
had this module monkeypatch a loop's own `close()` to dispose its entries the moment
the loop closed; John's round-4 ruling removed that — production code does not
monkeypatch `loop.close`. A loop that is garbage collected without `dispose_all()`
ever having run against it simply drops its entries (nothing here can safely await a
dispose/close call against a connection tied to a different, possibly already-closed,
loop).

`TIMEOUT_S` bounds connection establishment here (`connect_args`/socket timeouts,
belt-and-braces alongside the outer `asyncio.wait_for` in `app.checks`) — round 3 lost
these when engine/client construction moved into this module; a black-holed host would
otherwise hang a probe for asyncpg's 60s default.

Task I1 (Identity plan) extends this module rather than replacing it: `engine()` and
`sync_conn()` below are additions, `get_engine`/`get_redis`/`dispose_all`/`TIMEOUT_S`
keep their Task 5 names and semantics unchanged. `engine()` imports `app.checks.async_dsn`
lazily (inside the function) because `app.checks` imports `get_engine`/`get_redis`/
`TIMEOUT_S` from this module at its own top level — a module-level import here would be
circular.
"""
from __future__ import annotations

import asyncio
import weakref

import psycopg2
import redis.asyncio as aioredis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings

TIMEOUT_S = 3.0

_engines: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, AsyncEngine]] = weakref.WeakKeyDictionary()
_redis_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, Redis]] = weakref.WeakKeyDictionary()


def get_engine(url: str) -> AsyncEngine:
    """One AsyncEngine per (running loop, url), created lazily on first use."""
    loop = asyncio.get_running_loop()
    engines = _engines.setdefault(loop, {})
    engine = engines.get(url)
    if engine is None:
        # hide_parameters: a failed statement's log line never carries bound values (sign-up addresses) — 11c fix round 1
        engine = create_async_engine(
            url, pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args={"timeout": TIMEOUT_S}, hide_parameters=True
        )
        engines[url] = engine
    return engine


def get_redis(url: str) -> Redis:
    """One Redis client per (running loop, url), created lazily on first use."""
    loop = asyncio.get_running_loop()
    clients = _redis_clients.setdefault(loop, {})
    client = clients.get(url)
    if client is None:
        client = aioredis.from_url(  # type: ignore[no-untyped-call]  # redis-py's from_url has no annotations upstream
            url, socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S
        )
        clients[url] = client
    return client


async def dispose_all() -> None:
    """Disposes every engine/client cached for the CURRENT running loop. This is the
    only disposal path: the app lifespan calls it on shutdown; the test suite's
    `_dispose_pools` autouse fixture calls it after every test. Entries for other loops
    cannot be safely awaited from here — that loop may already be closed — so they are
    simply dropped from the cache instead."""
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


def sync_conn() -> psycopg2.extensions.connection:
    """psycopg2 connection for migrations, Celery tasks and tests. Autocommit;
    callers manage explicit transactions with `with conn:`."""
    c = psycopg2.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    c.autocommit = True
    return c


def engine() -> AsyncEngine:
    """`get_engine` bound to `settings.database_url` — the pooled async engine for
    ordinary request-time DB access outside the health probes. Imports
    `app.checks.async_dsn` lazily: `app.checks` imports `get_engine`/`get_redis`/
    `TIMEOUT_S` from this module at its own top level, so a module-level import here
    would be circular."""
    from app.checks import async_dsn

    return get_engine(async_dsn(settings.database_url))
