"""Sliding-window rate limits in Redis — ONE atomic check-and-reserve per attempt.

A subject's attempts in one scope live in ONE sorted set, each scored by the moment it happened, and every
decision is the same question: are there already `limit` of them inside the last `window_s` seconds. Nothing is
bucketed by calendar time. Spec §3's endpoint row states each limit as a RATE ("Lockout 10 failures/email/15
min and 30/IP/15 min"), and a fixed window could only honour that inside one calendar quarter-hour — nine
failures at 14:59:59 and one at 15:00:01 are ten failures two seconds apart and left the live bucket at ONE
(Task RATE-LIMIT-WINDOW; the flake was CI 34757098782).

**The whole attempt is one script** (amendment A-RL2, 2026-09-14), and that is the second half of the same
contract. Counting in one MULTI made the WRITE atomic; the DECISION was still check-then-act — `limits.check`
read the count and `limits.count_failure` wrote it ~100 ms later, behind the Argon2id hop, which is the sign-in
handler's only yield. Every request that arrived while the count was below the limit read the same pre-write
number, so twenty simultaneous wrong passwords against an address with nine failures were ALL evaluated: thirty
guesses per IP from cold, and 30k per address with k source IPs, against a contract of ten. `reserve()` prunes,
tests and writes in one server-side step, so the slot is taken BEFORE the password is looked at and exactly one
caller can be the tenth.

**A refused attempt is never recorded.** The script returns without ZADD when the window is already full, so
knocking cannot hold a lockout open: `docs/RUNBOOK-identity.md` §9's promise that a lockout "expires 15 minutes
after the OLDEST of the ten failures" is a property of this branch and not a hope. What the set holds is
therefore "attempts admitted to the credential check", and since a SUCCESSFUL sign-in clears it
(`app/auth/limits.clear`), what survives in it is failures.

**The clock is REDIS's** (`TIME`, read inside the script), not any api process's. Scores, the prune bound and
the TTL then come from one clock however many replicas are running, so no process's skew can widen a window —
the ahead replica used to release a lockout early and prune the other's entries with it. A caller may pass its
own `now` instead; nothing in the app does, and the tests are the only callers that do.

Subjects (client IP, normalised address) enter the key as a truncated SHA-256: a pseudonym that keeps raw
addresses out of Redis, NOT an anonymisation (a dictionary attack reverses it)."""
from __future__ import annotations

import hashlib
import secrets
from collections.abc import Awaitable
from typing import Any, NamedTuple, cast

from redis.asyncio import Redis


def subject_key(scope: str, subject: str) -> str:
    """The one key `subject`'s attempts in `scope` live under.

    It carries no clock term — that term is exactly what made it a bucket, and what let an attempt fall out of
    a count that should still have held it. `scripts/reset_rate_limits.py` still finds every counter under the
    same `rl:` prefix it always scanned, and `app.auth.limits.clear` needs nothing but the subject."""
    return f"rl:{scope}:{hashlib.sha256(subject.encode()).hexdigest()[:16]}"


class Reservation(NamedTuple):
    """What one attempt costs and what it learned.

    `in_window` is how many attempts are inside the window INCLUDING this one when it was admitted, and how
    many are inside it when it was not — so a caller acting on a threshold (the sign-in endpoint's audit row at
    the fifth failure) reads one number from one round trip. `retry_after` is meaningful only on a refusal.

    Not spelled `count`: a `NamedTuple` is a `tuple`, and `tuple.count` is a method."""

    admitted: bool
    in_window: int
    retry_after: int


#: `ARGV[3]` when the caller has no opinion about the time: the script reads Redis's own `TIME`.
SERVER_CLOCK = -1.0

#: One attempt. Prune what has left the window, refuse if it is already full WITHOUT recording the attempt,
#: otherwise record it and answer how many are inside.
#:
#: The rank trim keeps the newest `limit`, which is what the set holds anyway once the refusal arm exists — it
#: earns its line only when a limit is REDUCED while keys are live, where it brings an over-long set down to
#: the new limit at once instead of refusing off the old one for a window.
#:
#: `retry_after` is the exact wait, not the whole window: the oldest attempt inside the window leaves it at
#: `score + window`, and the set has always known that number. Clamped into `[1, window]` so it can never
#: promise a caller an earlier answer than the window allows, nor tell them to come back in zero seconds.
_RESERVE = """
local key, limit, window = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2])
local now = tonumber(ARGV[3])
if now < 0 then
  local t = redis.call('TIME')
  now = tonumber(t[1]) + tonumber(t[2]) / 1000000
end
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local wait = window
  if oldest[2] then wait = math.ceil(tonumber(oldest[2]) + window - now) end
  if wait < 1 then wait = 1 end
  if wait > window then wait = window end
  return {0, count, wait}
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('ZREMRANGEBYRANK', key, 0, -(limit + 1))
redis.call('EXPIRE', key, window)
return {1, redis.call('ZCARD', key), 0}
"""


def _args(scope: str, subject: str, limit: int, window_s: int, now: float | None) -> list[Any]:
    """`EVAL`'s arguments, built once for both flavours so the sync and async paths cannot drift apart.

    The member is random rather than the timestamp: two attempts in the same microsecond would otherwise be one
    ZADD, and a sorted set counts members."""
    return [1, subject_key(scope, subject), limit, window_s,
            SERVER_CLOCK if now is None else now, secrets.token_hex(8)]


def reserve(r: Any, scope: str, subject: str, limit: int, window_s: int, now: float | None = None) -> Reservation:
    """Takes one slot for `subject` in `scope` if the window has room, in one server-side step.

    `EVAL` rather than `EVALSHA`: the script is under a kilobyte on a connection that is already making a round
    trip, so caching its digest would buy nothing and would add a NOSCRIPT arm to every limit in the app."""
    admitted, in_window, retry_after = r.eval(_RESERVE, *_args(scope, subject, limit, window_s, now))
    return Reservation(bool(admitted), int(in_window), int(retry_after))


async def hit(client: Redis, scope: str, subject: str, limit: int, window_s: int, now: float | None = None) -> bool:
    """`reserve` for an asynchronous client; True when the attempt was admitted.

    The `cast` is redis-py's own typing: `Redis.eval` is declared `ResponseT`, `Awaitable[str] | str`, which
    covers every command's answer rather than this script's own three integers."""
    answer = cast("Awaitable[list[int]]", client.eval(_RESERVE, *_args(scope, subject, limit, window_s, now)))
    admitted, _in_window, _retry_after = await answer
    return bool(admitted)
