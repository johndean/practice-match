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


def _make_sync() -> redis_sync.Redis:
    client: redis_sync.Redis = redis_sync.from_url(  # type: ignore[no-untyped-call]  # redis-py's from_url has no annotations upstream
        settings.redis_url, socket_connect_timeout=3, socket_timeout=3
    )
    return client


def _make_async() -> aioredis.Redis:
    client: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]  # redis-py's from_url has no annotations upstream
        settings.redis_url, socket_connect_timeout=3, socket_timeout=3
    )
    return client


def sync_redis() -> redis_sync.Redis:
    """Resolved through the module factory at call time so tests (and `from app.cache
    import sync_redis` consumers) all see one patch point: the `redis` fixture
    replaces `_make_sync`/`_make_async`."""
    return _make_sync()


def async_redis() -> aioredis.Redis:
    return _make_async()
