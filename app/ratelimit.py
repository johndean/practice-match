"""Sliding-window counters in Redis — the only state the rate-limited endpoints share across api instances.

One subject's attempts in one scope live in ONE sorted set, each scored by the moment it happened, and every
decision is the same question: how many of them are inside the last `window_s` seconds. Nothing is bucketed by
calendar time any more. Spec §3's endpoint row states each limit as a RATE — "Lockout 10 failures/email/15 min
and 30/IP/15 min" — and a fixed window can only honour that inside one calendar quarter-hour: nine failures at
14:59:59 and one at 15:00:01 are ten failures two seconds apart, and they left the live bucket at ONE, so the
account stayed open and the correct password came back 200. `tests/api/test_auth.py` then passed or failed on
where in the quarter-hour the run happened to start, which is what CI 34757098782 attempt 1 hit (Task
RATE-LIMIT-WINDOW). The limits themselves are untouched — every constant in `app/auth/limits.py` is the value
it was — and a sliding window only ever refuses MORE than a fixed one did.

Each attempt is one MULTI, so a key always carries a TTL even if the process dies mid-sequence, and the TTL is
the window itself, re-issued on every attempt: a key outlives its last attempt by exactly one window and no
longer. Subjects (client IP, normalised address) enter the key as a truncated SHA-256: a pseudonym that keeps
raw addresses out of Redis, NOT an anonymisation (a dictionary attack reverses it)."""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any

from redis.asyncio import Redis


def subject_key(scope: str, subject: str) -> str:
    """The one key `subject`'s attempts in `scope` live under.

    It carries no clock term — that term is exactly what made it a bucket, and what let an attempt fall out of
    a count that should still have held it. `scripts/reset_rate_limits.py` still finds every counter under the
    same `rl:` prefix it always scanned, and `app.auth.limits.clear` now needs nothing but the subject."""
    return f"rl:{scope}:{hashlib.sha256(subject.encode()).hexdigest()[:16]}"


def _at(now: float | None) -> float:
    """The one clock every limit in the app reads.

    Every other function here takes its `now` from this, so a test that needs an attempt on a particular side
    of a window edge replaces this module's `time` attribute (`tests/conftest.py`'s `rate_limit_clock`) and
    leaves the real `time.time` — and so psycopg2, Argon2id and the logger — alone."""
    return time.time() if now is None else now


def _record(pipe: Any, key: str, limit: int, window_s: int, now: float) -> None:
    """Queues the one attempt `key` costs. Sync and async pipelines queue identically (redis-py's async
    `Pipeline` returns itself from every command rather than a coroutine), so this is the single command
    sequence behind every limit the app serves — the async `hit` below, and all four helpers in
    `app/auth/limits.py`.

    The rank trim is what keeps a flood from turning a counter into a list of every request it sent: only the
    newest `limit + 1` attempts can ever change an answer, so the rest are dropped and the set is bounded at
    `limit + 1` members however hard a caller hammers it. It is decision-preserving now and later, because the
    attempts it drops are the OLDEST ones — every one of them would have left the window before any attempt
    that was kept, so no future count that they could have contributed to is one that was not already
    saturated. The only thing that changes is `record`'s returned number, which saturates at `limit + 1`."""
    pipe.zremrangebyscore(key, "-inf", now - window_s)
    pipe.zadd(key, {secrets.token_hex(8): now})
    pipe.zremrangebyrank(key, 0, -(limit + 2))
    pipe.zcard(key)
    pipe.expire(key, window_s)


def count_in_window(r: Any, scope: str, subject: str, window_s: int) -> int:
    """How many of `subject`'s attempts in `scope` are inside the last `window_s` seconds, WITHOUT counting
    this call — one read-only ZCOUNT, which is what a lockout CHECK needs (`app.auth.limits.check`).

    The lower bound is exclusive and `_record`'s prune is inclusive, so an attempt exactly `window_s` old
    belongs to neither: it has left the window, by the same rule on both sides."""
    return int(r.zcount(subject_key(scope, subject), f"({_at(None) - window_s}", "+inf"))


def record(r: Any, scope: str, subject: str, limit: int, window_s: int) -> int:
    """Counts one attempt for `subject` and answers how many are inside the window, this one included
    (saturating at `limit + 1` — see `_record`). The synchronous half of `hit`, for the auth endpoints."""
    key = subject_key(scope, subject)
    with r.pipeline(transaction=True) as pipe:
        _record(pipe, key, limit, window_s, _at(None))
        results = pipe.execute()
    return int(results[-2])


async def hit(client: Redis, scope: str, subject: str, limit: int, window_s: int, now: float | None = None) -> bool:
    """Counts one hit for `subject` in the last `window_s` seconds; True while within `limit`."""
    key = subject_key(scope, subject)
    async with client.pipeline(transaction=True) as pipe:
        _record(pipe, key, limit, window_s, _at(now))
        results = await pipe.execute()
    return int(results[-2]) <= limit
