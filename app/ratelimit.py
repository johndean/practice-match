"""Fixed-window counters in Redis (INCR + EXPIRE) — the only state the sign-up endpoint shares
across api instances. Subjects (client IP, normalised address) are hashed into the key."""
from __future__ import annotations

import hashlib
import time

from redis.asyncio import Redis


async def hit(client: Redis, scope: str, subject: str, limit: int, window_s: int) -> bool:
    """Counts one hit for `subject` in the current `window_s`-second window; True while within `limit`."""
    bucket = int(time.time()) // window_s
    key = f"rl:{scope}:{bucket}:{hashlib.sha256(subject.encode()).hexdigest()[:16]}"
    count = int(await client.incr(key))
    if count == 1:
        await client.expire(key, window_s)
    return count <= limit
