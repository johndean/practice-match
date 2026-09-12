"""Request-time Redis access for application code (rate limiting, session cache,
outbox locks) — distinct from `app.db`'s per-(event loop, url) pooled clients used by
the health probes.

`sync_redis()` hands out ONE client per process, built on first use and dropped by
`reset()` (I3 fix round 1, Critical 3): `app.auth.deps.current_principal` calls it on
every authenticated request, and a fresh client per call meant a fresh TCP connection on
the very path the 60 s session cache exists to keep cheap. `async_redis()` still builds a
fresh client per call by design (decision A2) — a redis-py asyncio client binds its
connections to the event loop that opened them, which is the problem `app.db`'s per-loop
caches exist to avoid.

Both resolve the actual client through `_make_sync`/`_make_async` at CALL time, looked up
via this module's own globals, so the test suite has one seam it can patch that every
caller sees regardless of how that caller imported the name. A consumer that does
`from app.cache import sync_redis` (as tests/auth/test_db_cache.py and the identity briefs
I3/I4 do, at their own module's top level) binds the `sync_redis` FUNCTION OBJECT once,
but that function's body still resolves `_make_sync` fresh on every call from
`app.cache`'s namespace — so patching `cache._make_sync`/`cache._make_async` (not
`cache.sync_redis`/`cache.async_redis` themselves, which the old `redis` fixture patched
and which a from-import bypasses) intercepts every caller. The `redis` fixture pairs that
patch with `reset()` on both sides of its yield.
"""
from __future__ import annotations

import threading
from typing import Any

import redis as redis_sync
import redis.asyncio as aioredis

from app.config import settings

#: The key prefix `GET /api/listings` caches a page under. It lives HERE, beside the client, and
#: not in the route module, because two very different callers have to agree on it: the API, which
#: writes and drops it, and the WORKER — `app.tasks.census.geocode_listing` — which drops it when
#: a listing's pin lands. Nothing under `app/tasks/census.py`'s own imports may reach a route
#: module, so a shared constant in a module both already depend on is the only place one
#: implementation can live.
LIST_CACHE_PREFIX = "listings:v1:"


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
_sync_lock = threading.Lock()


def sync_redis() -> redis_sync.Redis:
    """One client per process, built through the module factory on first use so tests (and
    `from app.cache import sync_redis` consumers) all see one patch point: the `redis` fixture
    replaces `_make_sync`/`_make_async` and calls `reset()`. redis-py's sync client is itself
    thread-safe (each command takes a connection from its own pool), which is what makes one
    shared instance safe under FastAPI's `def`-dependency threadpool.

    The lock is taken on every call rather than guarding a double-checked read the way
    `app.auth.passwords._client()` does (fix round 2 observation). Both are correct; this shape
    was chosen because an uncontended `threading.Lock` costs tens of nanoseconds against a Redis
    round trip of tens of microseconds, and because the double-checked form has a branch that can
    only be taken by a genuine race — coverable only by a timing-dependent test, on a suite that
    must hold 100 % of branches on every run."""
    global _sync_client
    with _sync_lock:
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
    with _sync_lock:
        _sync_client = None


def drop_list_cache(cache: Any) -> int:
    """Every `listings:v1:*` key, dropped; the number removed.

    Spec 2026-09-08 D16, which is `app/api/listings.py`'s own review-round-2 M4 requirement made
    real: a disclosure flag turned OFF must stop reaching buyers AT ONCE, not within the 60 s TTL.
    Every writer in `app/api/seller_listings.py` and `app/api/admin_listings.py` calls this AFTER
    its transaction commits — the ordering `admin_users.py` learned in I5c fix round 1 — because
    dropping the key while the write is uncommitted leaves a window in which a concurrent read
    re-caches the pre-write payload for the full TTL.

    The geocode chain calls it too. The publish drops the cache when the reviewer decides, which
    is BEFORE the worker has resolved the point, so a buyer who loaded Browse in between would
    have been served a pinless card for the rest of the TTL; it is dropped again when the pin
    actually lands. Its two callers there are `app.tasks.census.geocode_listing`, AFTER its
    backfill enqueue and last, and `scripts/census_load.py geocode`, once per batch in a
    `finally`. NOT `app.census.geocode.resolve`, which is where fix round 1 put it and fix round 2
    took it out again: a network call between two committed point columns and the backfill that
    turns them into figures is a place where a Redis blip cost a listing its market card
    permanently. `resolve` is a PostGIS write and nothing else.

    `scan_iter`, not `keys`: the cache is small but a blocking KEYS on a shared Railway Redis is a
    stall every other consumer pays for. The prefix is the key shape's own, so a v2 key scheme
    cannot be silently missed — it would not match, and the test that plants two keys would fail.
    """
    removed = 0
    for key in cache.scan_iter(match=f"{LIST_CACHE_PREFIX}*"):
        cache.delete(key)
        removed += 1
    return removed
