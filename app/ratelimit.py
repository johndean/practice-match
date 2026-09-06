"""Fixed-window counters in Redis — the only state the sign-up endpoint shares across api instances.

Each hit is one MULTI (INCR + EXPIRE), so every key carries a TTL even if the process dies between the two
commands; the bucket index is part of the key, so a key is never consulted after its window even though late
hits refresh its TTL by up to one more window. Subjects (client IP, normalised address) enter the key as a
truncated SHA-256: a pseudonym that keeps raw addresses out of Redis, NOT an anonymisation (a dictionary attack
reverses it). Fixed windows allow up to twice the limit across one window boundary; spec §3 accepts that."""
from __future__ import annotations

import hashlib
import time

from redis.asyncio import Redis


def bucket_key(scope: str, subject: str, window_s: int, now: float | None = None) -> str:
    bucket = int(time.time() if now is None else now) // window_s
    return f"rl:{scope}:{bucket}:{hashlib.sha256(subject.encode()).hexdigest()[:16]}"


async def hit(client: Redis, scope: str, subject: str, limit: int, window_s: int, now: float | None = None) -> bool:
    """Counts one hit for `subject` in the current `window_s`-second window; True while within `limit`."""
    key = bucket_key(scope, subject, window_s, now)
    async with client.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window_s)
        count, _ = await pipe.execute()
    return int(count) <= limit
