"""Request-time Redis access for application code (rate limiting, session cache,
outbox locks) — distinct from `app.db`'s per-(event loop, url) pooled clients used by
the health probes. `sync_redis`/`async_redis` are called fresh each time by design: the
test suite's `redis` fixture (tests/conftest.py) monkeypatches these two names to
fixed fakeredis instances, so callers must look the client up through this module
(`cache.sync_redis()`) rather than caching it themselves at import time."""
from __future__ import annotations

import redis as redis_sync
import redis.asyncio as aioredis

from app.config import settings


def sync_redis() -> redis_sync.Redis:
    client: redis_sync.Redis = redis_sync.from_url(  # type: ignore[no-untyped-call]  # redis-py's from_url has no annotations upstream
        settings.redis_url, socket_connect_timeout=3, socket_timeout=3
    )
    return client


def async_redis() -> aioredis.Redis:
    client: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]  # redis-py's from_url has no annotations upstream
        settings.redis_url, socket_connect_timeout=3, socket_timeout=3
    )
    return client
