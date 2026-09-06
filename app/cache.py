"""Request-time Redis access for application code (rate limiting, session cache,
outbox locks) — distinct from `app.db`'s per-(event loop, url) pooled clients used by
the health probes. `sync_redis`/`async_redis` build a fresh client per call by design
(decision A2): the test suite's `redis` fixture (tests/conftest.py) needs one seam it
can patch that every caller sees, regardless of how that caller imported the name.

Fix round 1 (Critical 1): `sync_redis`/`async_redis` resolve the actual client through
`_make_sync`/`_make_async` at CALL time, looked up via this module's own globals. A
consumer that does `from app.cache import sync_redis` (as tests/auth/test_db_cache.py
and later identity briefs I3/I4 do, at their own module's top level) binds the
`sync_redis` FUNCTION OBJECT once, but that function's body still resolves
`_make_sync` fresh on every call from `app.cache`'s namespace — so patching
`cache._make_sync`/`cache._make_async` (not `cache.sync_redis`/`cache.async_redis`
themselves, which the old `redis` fixture patched and which a from-import bypasses)
intercepts every caller, whichever way they imported the name."""
from __future__ import annotations

import redis as redis_sync
import redis.asyncio as aioredis

from app.config import settings


# `Redis.from_url`, not the module-level `redis.from_url`/`redis.asyncio.from_url`: those two are
# entirely unannotated one-line shims that do nothing but call this same classmethod
# (redis/utils.py, redis/asyncio/utils.py), so under mypy --strict every call through them needed a
# `# type: ignore[no-untyped-call]`. The classmethod itself is annotated. Same object, same
# arguments, no suppression (I3 fix round 1 follow-up); `app.db.get_redis` does the same.
def _make_sync() -> redis_sync.Redis:
    client: redis_sync.Redis = redis_sync.Redis.from_url(
        settings.redis_url, socket_connect_timeout=3, socket_timeout=3
    )
    return client


def _make_async() -> aioredis.Redis:
    client: aioredis.Redis = aioredis.Redis.from_url(
        settings.redis_url, socket_connect_timeout=3, socket_timeout=3
    )
    return client


_sync_client: redis_sync.Redis | None = None


def sync_redis() -> redis_sync.Redis:
    """One client per process, built through the module factory on first use so tests (and
    `from app.cache import sync_redis` consumers) all see one patch point: the `redis` fixture
    replaces `_make_sync`/`_make_async` and calls `reset()`.

    Memoised in I3 fix round 1 (Critical 3): `app.auth.deps.current_principal` calls this on
    every authenticated request, and a fresh client per call means a fresh TCP connection per
    call — a second connect on the hot path the session cache exists to keep cheap. redis-py's
    sync client is thread-safe (it hands each command a connection from its own pool), which is
    what makes one shared instance safe under FastAPI's `def`-dependency threadpool.

    `async_redis` is deliberately NOT memoised: a redis-py asyncio client binds its connections
    to the event loop that opened them, so one shared instance would break exactly the way
    `app.db`'s per-loop caches exist to avoid."""
    global _sync_client
    if _sync_client is None:
        _sync_client = _make_sync()
    return _sync_client


def async_redis() -> aioredis.Redis:
    return _make_async()


def reset() -> None:
    """Drops the memoised sync client so the next `sync_redis()` rebuilds it through `_make_sync`.
    The test suite's `redis` fixture calls this on both sides of its yield, so a fakeredis instance
    can neither be shadowed by an earlier client nor outlive its own test (Critical 3(ii)); nothing
    in production calls it (a process keeps one client for its life)."""
    global _sync_client
    _sync_client = None
