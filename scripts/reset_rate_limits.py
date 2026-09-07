#!/usr/bin/env python3
"""Clear the LOCAL test environment's rate-limit counters, so consecutive suite runs are
independent (controller amendment A-S5.1; John's ruling, 2026-09-08).

The limits themselves do not move. `app/auth/limits.py` still says `SIGNIN_IP = (30, 900)`,
`FORGOT_IP = (10, 3600)`, `SIGNUP_IP = (5, 3600)`; `app/ratelimit.py` still counts in fixed
windows; `tests/api/test_auth.py` still proves each refusal. They are security controls and are
not loosened for a test suite. What this removes is the CONSEQUENCE the Playwright harness had
inherited from them — that a developer could run the local suite about three times an hour before
`FORGOT_IP` started answering 429 in the middle of a screenshot — by clearing the counters the
LOCAL environment accumulated, before the API starts serving.

`frontend/tests/targets.ts` runs it in the `api` web server's command, between `migrate.py` and
`seed_persona.py`; `frontend/tests/targets.test.ts` pins that. In CI it runs too and deletes
nothing: each job gets a fresh Redis service.

TWO conditions, both checked here rather than trusted to the caller — a script whose only safety
is where it happens to be invoked from is one edit away from running somewhere else:

  * `ENVIRONMENT` must be exactly `test` (not a prefix, not case-folded), and
  * the Redis host must be loopback (`localhost` / `127.0.0.1` / `::1`).

QA and production fail both, and either one alone is enough to refuse. The refusal is a non-zero
exit and ONE line on stderr; nothing but the deleted count is ever printed, because a bucket key
carries its subject as a truncated SHA-256 pseudonym — which `app/ratelimit.py` is careful to say
is not an anonymisation — and a URL may carry a credential.

SCAN + DEL over `rl:*` — `app.ratelimit.bucket_key`'s own prefix — and never `FLUSHDB`: the 60 s
session cache and the outbox's idempotency locks live in the same database, and dropping a live
session mid-run would fail tests a long way from the cause.

    ENVIRONMENT=test poetry run python scripts/reset_rate_limits.py

The `app.*` imports are inside `main()` for the reason `scripts/bootstrap_admin.py` records:
`python scripts/reset_rate_limits.py` puts `scripts/` on `sys.path`, not the repository root.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

# Unconditionally, before the `app.*` imports inside `main()` — see `scripts/seed_persona.py`.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: The prefix `app.ratelimit.bucket_key` builds every counter key under. Nothing else is touched.
RATE_LIMIT_PREFIX = "rl:"
#: The only environment this may run in, compared exactly.
ALLOWED_ENVIRONMENT = "test"
#: The only hosts this may run against.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_local_redis(url: str) -> bool:
    """Whether `url` names a Redis on this machine. `urlsplit().hostname` is the parsed host — it
    lower-cases, strips any `user:password@` and any `:port`, and yields `None` when there is no
    authority at all — so `redis://localhost.evil.example` and `redis://:pw@host` are both simply
    not in the set, and a URL with no host is `None`, which is not in it either."""
    return (urlsplit(url).hostname or "") in LOCAL_HOSTS


def main(argv: Sequence[str] | None = None) -> int:
    from app.cache import sync_redis
    from app.config import settings

    argparse.ArgumentParser(description="Clear the local test environment's rate-limit counters.").parse_args(argv)

    if settings.environment != ALLOWED_ENVIRONMENT:
        print(
            f"[reset_rate_limits] refusing: ENVIRONMENT is {settings.environment!r}, and this only runs on {ALLOWED_ENVIRONMENT!r}",
            file=sys.stderr,
        )
        return 2
    if not is_local_redis(settings.redis_url):
        # The parsed hostname, never the URL: a URL may carry a password.
        host = urlsplit(settings.redis_url).hostname or "(none)"
        print(f"[reset_rate_limits] refusing: Redis host is {host!r}, and this only runs against a local one", file=sys.stderr)
        return 2

    r = sync_redis()
    deleted = 0
    # SCAN, not KEYS: it does not block the server, and `scan_iter` pages for us. Deleting inside
    # the iteration is safe — a key already returned cannot be returned again, and one deleted
    # before its page simply never appears.
    for key in r.scan_iter(match=f"{RATE_LIMIT_PREFIX}*", count=500):
        # `cast`, for the reason `app/api/auth.py` casts its own cursor reads: redis-py types every
        # command as `Awaitable[Any] | Any` so one stub can serve the sync and async clients both.
        # This is the SYNC client (`app.cache.sync_redis`), so the value is the int it says it is.
        deleted += cast("int", r.delete(key))
    print(f"[reset_rate_limits] cleared {deleted} rate-limit bucket(s) on {settings.environment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
