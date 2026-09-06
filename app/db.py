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

Task I2 (Identity plan) registers `psycopg2.extras.register_uuid()` once at import,
process-wide: without it psycopg2 returns `uuid` columns as plain `str`, not
`uuid.UUID`, which silently breaks any interface that types a database-sourced id as
`UUID` (`app.auth.sessions.Principal.account_id`, `app.auth.tokens.ApiPrincipal.token_id`,
…). Registering here — rather than per-connection in `sync_conn()` — is deliberate: it
also covers connections opened directly with `psycopg2.connect()` (the test suite's
`conn` fixture in `tests/conftest.py` included), not only ones that go through this
module.

Task I4 fix round 1 (Important 5) POOLS `sync_conn()`. An un-pooled `psycopg2.connect()`
measured 32.8 ms against the dev stack and every guarded endpoint opened one, which was
59 % of `GET /api/me`'s 56.7 ms and the reason its 20 ms budget was (wrongly) relaxed;
the same getconn + `with conn:` + SELECT behind a pool measures 1.04 ms median. Pools are
keyed by DSN, so the test suite's `conn`/`scratch_dsn` fixtures — which patch
`settings.database_url` to a fresh database per test — get their own pool and keep their
isolation, and `dispose_all()` closes every pool.

Two properties of psycopg2's own pool are worth stating rather than discovering:
`ThreadedConnectionPool` keeps at most `minconn` connections IDLE (`_putconn` closes the
rest), so with the ruling's `minconn=1` reuse is guaranteed for serial work and degrades
to today's behaviour — never worse — under concurrency; and `maxconn` exhaustion raises
`PoolError`, which would turn a burst into 500s where there was no cap before, so beyond
the cap `sync_conn()` hands out an ordinary un-pooled connection instead (the overflow
path SQLAlchemy spells `max_overflow`).
"""
from __future__ import annotations

import asyncio
import threading
import weakref
from dataclasses import dataclass, field
from typing import cast

import psycopg2
import psycopg2.extras
import psycopg2.pool
import redis.asyncio as aioredis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings

psycopg2.extras.register_uuid()  # type: ignore[no-untyped-call]  # psycopg2's stubs leave register_uuid untyped upstream

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
        # `aioredis.Redis.from_url`, not the module-level `aioredis.from_url`: the latter is a
        # one-line, entirely unannotated shim around exactly this classmethod (redis/asyncio/utils.py),
        # so calling it needed a `# type: ignore[no-untyped-call]`. Same object, same arguments,
        # no suppression (I3 fix round 1 follow-up).
        client = aioredis.Redis.from_url(
            url, socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S
        )
        clients[url] = client
    return client


async def dispose_all() -> None:
    """Disposes every engine/client cached for the CURRENT running loop, and every sync
    connection pool (those are not loop-bound). This is the only disposal path: the app lifespan calls it on shutdown; the test suite's
    `_dispose_pools` autouse fixture calls it after every test. Entries for other loops
    cannot be safely awaited from here — that loop may already be closed — so they are
    simply dropped from the cache instead."""
    dispose_sync_pools()
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


class PooledConnection(psycopg2.extensions.connection):
    """A psycopg2 connection whose `close()` RETURNS it to its pool.

    A subclass rather than a wrapper object because `close()` is the only thing that changes and
    every consumer — `app.auth.sessions`, `tokens`, `audit` — is annotated
    `psycopg2.extensions.connection`; a proxy would have meant editing modules this task does not
    own. psycopg2 builds it through the pool's `connection_factory`, the same extension point
    `psycopg2.extras.DictConnection` uses.

    The existing call sites (`closing(sync_conn()) as conn, conn`) therefore keep working unchanged:
    `with conn:` still commits or rolls the transaction back, and `closing` still releases — it just
    releases into the pool instead of onto the floor."""

    _holder: _SyncPool | None = None

    def close(self) -> None:
        # Cleared FIRST: `AbstractConnectionPool._putconn` calls `conn.close()` itself when the idle
        # pool is full or the socket has gone, and that re-entrant call must reach psycopg2's real
        # close rather than bouncing back into the pool.
        holder, self._holder = self._holder, None
        if holder is None:
            super().close()
        else:
            holder.release(self)


@dataclass
class _SyncPool:
    """One `ThreadedConnectionPool` plus the checked-out count `sync_pool_in_use()` reports.

    The count is kept here rather than read off `pool._used` so nothing depends on psycopg2's
    private attributes; the lock guards it because FastAPI runs `def` dependencies (and therefore
    `sync_conn`) in the anyio worker threadpool."""

    pool: psycopg2.pool.ThreadedConnectionPool
    in_use: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def acquire(self) -> psycopg2.extensions.connection | None:
        """A pooled connection, or None when the pool is at `maxconn` (the caller overflows)."""
        try:
            # `cast`, not an isinstance narrowing: the pool is constructed with
            # `connection_factory=PooledConnection`, so this is what it always hands back — and a
            # branch that can never be taken is one the coverage gate can never close.
            conn = cast("PooledConnection", self.pool.getconn())
        except psycopg2.pool.PoolError:
            return None
        with self.lock:
            self.in_use += 1
        conn._holder = self
        conn.autocommit = True
        return conn

    def release(self, conn: psycopg2.extensions.connection) -> None:
        self.pool.putconn(conn)
        with self.lock:
            self.in_use -= 1


_sync_pools: dict[str, _SyncPool] = {}
_sync_pools_lock = threading.Lock()


def sync_dsn(url: str | None = None) -> str:
    """`settings.database_url` (or `url`) as psycopg2 spells it — the async dialect prefix removed."""
    return (url if url is not None else settings.database_url).replace("postgresql+asyncpg://", "postgresql://", 1)


def _sync_pool(dsn: str) -> _SyncPool:
    with _sync_pools_lock:
        holder = _sync_pools.get(dsn)
        if holder is None:
            # minconn=1: one connection is opened eagerly and one is kept idle (psycopg2 caps the
            # idle set at minconn), which is what removes the per-request connect.
            holder = _SyncPool(psycopg2.pool.ThreadedConnectionPool(1, settings.db_pool_max, dsn, connection_factory=PooledConnection))
            _sync_pools[dsn] = holder
        return holder


def sync_conn() -> psycopg2.extensions.connection:
    """psycopg2 connection for request handlers, migrations, Celery tasks and tests. Autocommit;
    callers manage explicit transactions with `with conn:`, and `close()` returns it to the pool."""
    dsn = sync_dsn()
    conn = _sync_pool(dsn).acquire()
    if conn is not None:
        return conn
    # Past `maxconn`: an ordinary connection whose `close()` really closes. Refusing here would
    # turn a burst of concurrent requests into 500s, which is worse than the un-pooled behaviour
    # this pool replaced.
    direct = psycopg2.connect(dsn)
    direct.autocommit = True
    return direct


def sync_pool_in_use(dsn: str | None = None) -> int:
    """How many connections the pool for `dsn` has checked out. With pooling, "the request closed
    its connection" means "returned it", so a connection's own `closed` flag can no longer say so;
    this is what the tests (and, one day, an ops probe) ask instead."""
    holder = _sync_pools.get(sync_dsn(dsn))
    return holder.in_use if holder else 0


def dispose_sync_pools() -> None:
    """Closes every sync pool. Called by `dispose_all()` — the app lifespan on shutdown, and the
    test suite's `_dispose_pools` autouse fixture after every test, which is what stops a pool
    outliving the scratch database it points at."""
    with _sync_pools_lock:
        pools = list(_sync_pools.values())
        _sync_pools.clear()
    for holder in pools:
        holder.pool.closeall()


def engine() -> AsyncEngine:
    """`get_engine` bound to `settings.database_url` — the pooled async engine for
    ordinary request-time DB access outside the health probes. Imports
    `app.checks.async_dsn` lazily: `app.checks` imports `get_engine`/`get_redis`/
    `TIMEOUT_S` from this module at its own top level, so a module-level import here
    would be circular."""
    from app.checks import async_dsn

    return get_engine(async_dsn(settings.database_url))
