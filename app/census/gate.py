"""Spec §11: when a dataset's `license_status` leaves 'cleared', its layer disappears within one
minute — a 60-second cache over `dataset_registry`, invalidated on any admin decision.

Why Redis and not a process-local TTL cache: the api runs as several containers behind Railway's
router, and `POST /api/admin/data-sources/{key}/license` lands on exactly one of them. A per-process
cache would leave every OTHER container serving a blocked layer for its own full minute, with no
way for the deciding container to reach them — the 60 s ceiling would hold per process and not for
the system, which is the thing spec §11 actually promises. `app.cache.sync_redis()` is the shared
client the rest of the app already authenticates through, so this adds no new dependency.

Two keys, and they do different jobs (red-team C5):

* `gate:{dataset_key}` — the cached answer to "may this layer be shown at all", `"1"`/`"0"` with a
  60 s TTL. `invalidate()` DELETES it, so the next read is fresh.
* `market:gate:v` — a global counter every cached market payload (panel, communities) includes in
  its own cache key. Deleting the per-dataset answer is not enough on its own: a community payload
  cached three minutes ago still holds the metrics of a layer that has just been blocked, and
  bumping this counter is what makes every one of those keys unreachable in the same instant.
  `invalidate()` bumps it for ANY decision, including one that CLEARS a dataset — a payload
  assembled while the layer was hidden is just as stale as one assembled while it was shown.

`conn_factory` is a factory rather than a connection because a cache hit must open nothing at all:
this is asked once per layer per request, and the whole point of the cache is that the common
answer costs one Redis GET. The connection it returns belongs to the CALLER — the gate never
closes it — so a request handler passes `lambda: conn` from inside its own
`closing(sync_conn()) as conn` block.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import cast

import psycopg2.extensions
import redis as redis_sync

TTL = 60


def layer_enabled(r: redis_sync.Redis, conn_factory: Callable[[], psycopg2.extensions.connection], dataset_key: str) -> bool:
    """Whether `dataset_key` is cleared for display, through the 60 s cache.

    Fails closed: a key with no `dataset_registry` row is refused (and the refusal cached), exactly
    as a `blocked` one is. A layer nobody has cleared is not a layer awaiting a decision."""
    key = f"gate:{dataset_key}"
    # redis-py's sync/async command mixins share one ResponseT stub (Awaitable[Any] | Any); this
    # client is sync — the same cast `app.auth.sessions` makes for the same reason.
    cached = cast("bytes | str | None", r.get(key))
    if cached is not None:
        return cached in (b"1", "1")
    conn = conn_factory()
    with conn.cursor() as cur:
        cur.execute("SELECT license_status = 'cleared' FROM dataset_registry WHERE dataset_key = %s", (dataset_key,))
        row = cur.fetchone()
    enabled = bool(row and row[0])
    r.set(key, "1" if enabled else "0", ex=TTL)
    return enabled


def invalidate(r: redis_sync.Redis, dataset_key: str) -> None:
    """Drop the cached status AND bump the global gate version so every cached market payload
    (panel, communities) is keyed away within the same minute (red-team C5)."""
    r.delete(f"gate:{dataset_key}")
    r.incr("market:gate:v")


def version(r: redis_sync.Redis) -> int:
    """The counter cached market payloads carry in their key; 0 before any decision has been made."""
    v = cast("bytes | str | None", r.get("market:gate:v"))
    return int(v) if v else 0
