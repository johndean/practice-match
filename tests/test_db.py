"""Task 5 fix round 3/4: app/db.py caches one async engine and one Redis client per
(running event loop, url) so the health probes stop paying full connection setup on
every call (that cost ~100ms once Postgres/Redis were reachable — see
tests/perf/test_api_latency.py). Disposal is the test suite's `_dispose_pools` autouse
fixture (tests/conftest.py) and the app's own lifespan (app/main.py) — never a
monkeypatched `loop.close` (round 4: production code must not do that)."""
from __future__ import annotations

import asyncio
import threading
import time

import psycopg2.extensions
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
    # The seam is `Redis.from_url`, the annotated classmethod, since I3 fix round 1's follow-up:
    # `get_redis` no longer goes through redis-py's unannotated module-level `from_url` shim (which
    # only forwards to this very classmethod), so no `# type: ignore[no-untyped-call]` is needed.
    original_from_url = db.aioredis.Redis.from_url

    def spy(url, **kwargs):
        captured.update(kwargs)
        return original_from_url(url, **kwargs)

    monkeypatch.setattr(db.aioredis.Redis, "from_url", spy)
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


# --- I4 fix round 1, Important 5: `sync_conn()` is pooled -------------------------------------
# An un-pooled `psycopg2.connect()` measured 32.8 ms on the dev stack and EVERY guarded endpoint
# opened one, which is 59 % of `GET /api/me`. These pin the pool that removes it.


def test_sync_conn_reuses_one_underlying_connection_across_sequential_uses(db_ready):
    first = db.sync_conn()
    backend = first.get_backend_pid()
    first.close()                      # "close" now means "return to the pool"
    second = db.sync_conn()
    try:
        assert second.get_backend_pid() == backend, "the second use opened a new Postgres backend"
    finally:
        second.close()


def test_a_returned_connection_is_no_longer_checked_out(db_ready):
    conn = db.sync_conn()
    assert db.sync_pool_in_use() == 1
    conn.close()
    assert db.sync_pool_in_use() == 0


def test_a_broken_connection_is_discarded_rather_than_returned(db_ready):
    """psycopg2's pool refuses to re-pool a connection whose socket has gone; the next caller must
    get a live one, not the corpse."""
    conn = db.sync_conn()
    psycopg2.extensions.connection.close(conn)   # close the REAL socket, bypassing the return-to-pool override
    assert conn.closed != 0
    conn.close()                              # release the (dead) connection
    fresh = db.sync_conn()
    try:
        assert fresh is not conn and fresh.closed == 0
        with fresh.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        fresh.close()


async def test_dispose_all_closes_the_sync_pools(db_ready):
    conn = db.sync_conn()
    conn.close()
    assert db.sync_pool_in_use() == 0
    await db.dispose_all()
    assert db._sync_pools == {}
    again = db.sync_conn()
    try:
        assert again.closed == 0
    finally:
        again.close()


def test_pools_are_keyed_by_dsn_so_a_scratch_database_gets_its_own(conn, db_ready, monkeypatch):
    """The `conn` fixture patches `settings.database_url` to a scratch database; the pool must
    follow it, or a test would be handed a connection to the shared dev database."""
    scratch = db.sync_conn()
    try:
        with scratch.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == settings.database_url.rsplit("/", 1)[1]
    finally:
        scratch.close()
    assert settings.database_url in db._sync_pools


def test_the_pool_overflows_to_a_direct_connection_rather_than_refusing(db_ready, monkeypatch):
    """`maxconn` exhaustion used to be impossible (there was no pool); it must not become a 500.
    Beyond the cap a caller gets an ordinary un-pooled connection whose `close()` really closes —
    the behaviour that shipped before the pool, as the overflow path rather than the normal one."""
    monkeypatch.setattr(settings, "db_pool_max", 1)
    db.dispose_sync_pools()
    held = db.sync_conn()
    try:
        overflow = db.sync_conn()
        try:
            with overflow.cursor() as cur:
                cur.execute("SELECT 1")
                assert cur.fetchone() == (1,)
        finally:
            overflow.close()
            assert overflow.closed != 0, "an overflow connection must really close, not linger"
    finally:
        held.close()


# --- I4 fix round 2, NEW-1: disposal must not re-enter the pool --------------------------------
# `_SyncPool.release()` calls `pool.putconn()`, which takes ThreadedConnectionPool's own
# non-reentrant lock — and `closeall()` holds that lock while calling `conn.close()` on every
# connection it knows about. A CHECKED-OUT connection still carried its `_holder`, so its `close()`
# re-entered `putconn()` and blocked on the lock its own caller was holding. `_closeall` wraps that
# call in `try/except Exception`, which cannot catch a deadlock.
#
# Both tests run the disposal on a DAEMON thread with a bounded join: a regression has to FAIL here,
# not hang the run. That matters more than it sounds — `dispose_all()` is an autouse teardown after
# every test, so before this fix any pool regression that left a connection checked out turned a
# one-line assertion failure into a CI job that burned to its wall-clock limit with no diagnosis.


def _dispose_on_a_watchdog_thread(timeout: float = 2.0) -> bool:
    done = threading.Event()

    def _run() -> None:
        db.dispose_sync_pools()
        done.set()

    threading.Thread(target=_run, daemon=True).start()
    return done.wait(timeout)


def test_dispose_returns_while_a_connection_is_still_checked_out(db_ready):
    conn = db.sync_conn()
    assert db.sync_pool_in_use() == 1
    assert _dispose_on_a_watchdog_thread(), "dispose_sync_pools() deadlocked with a connection checked out"
    conn.close()


def test_a_release_after_dispose_closes_the_connection_instead_of_raising(db_ready):
    """The secondary path: `putconn()` on a closed pool raises `PoolError`, which on a request path
    would be a 500 raised while merely cleaning up — and would leak the `in_use` count with it."""
    conn = db.sync_conn()
    holder = db._sync_pools[db.sync_dsn()]
    assert _dispose_on_a_watchdog_thread()
    conn.close()                      # must not raise
    assert conn.closed != 0
    assert holder.in_use == 0


async def test_dispose_all_returns_while_a_connection_is_still_checked_out(db_ready):
    """The production path: `app/main.py`'s lifespan calls `dispose_all()` on shutdown, and a
    `force_exit` (a second SIGTERM) reaches it with requests still in flight. A hang there is a
    container Railway has to SIGKILL, with the async engine and the Redis client never disposed."""
    conn = db.sync_conn()
    await asyncio.wait_for(db.dispose_all(), timeout=5)
    conn.close()
    assert db.sync_pool_in_use() == 0
