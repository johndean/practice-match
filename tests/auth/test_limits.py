"""app/auth/limits.py has no Step 1 test file in the brief's task-I3 — these close the coverage
gap for it (100% lines and branches, John's standing ruling). `client_ip`/`_host_only` are already
exercised thoroughly elsewhere: `tests/api/test_interest.py` (real Starlette Request, every
X-Forwarded-For shape) and `tests/auth/test_deps.py` (the plain-mapping stand-in) both call
through `app.auth.limits.client_ip` — one implementation, re-exported/imported, not duplicated —
so only `hit()` and the module's rate-limit constants need tests here."""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import limits


def test_limit_constants_are_the_spec_values():
    assert limits.SIGNIN_EMAIL == (10, 900)
    assert limits.SIGNIN_IP == (30, 900)
    assert limits.SIGNUP_IP == (5, 3600)
    assert limits.SIGNUP_EMAIL == (3, 86400)
    assert limits.FORGOT_EMAIL == (3, 3600)


def test_hit_allows_up_to_the_limit_then_429s_with_retry_after(redis):
    key = f"rl:test:{uuid4()}"
    for _ in range(3):
        limits.hit(redis, key, 3, 60)  # within the limit: no raise, first hit also sets the TTL
    with pytest.raises(HTTPException) as exc:
        limits.hit(redis, key, 3, 60)
    assert exc.value.status_code == 429
    assert exc.value.detail == {"error": {"code": "RATE_LIMITED", "message": "Too many attempts. Try again later."}}
    assert 0 < int(exc.value.headers["Retry-After"]) <= 60


class _FakeCounter:
    """A minimal (incr, expire, ttl) stand-in whose ttl() is scripted independently of a real
    Redis TTL, to exercise `hit`'s Retry-After fallback — no real client would ever report a
    missing/negative TTL for a key it just EXPIRE'd itself, but the fallback exists for exactly
    that (a process restart between INCR and EXPIRE)."""

    def __init__(self, start: int, ttl_value: int):
        self._n = start
        self._ttl = ttl_value

    def incr(self, key: str) -> int:
        self._n += 1
        return self._n

    def expire(self, key: str, seconds: int) -> None:
        pass

    def ttl(self, key: str) -> int:
        return self._ttl


def test_hit_retry_after_falls_back_to_the_window_when_ttl_is_unavailable():
    fake = _FakeCounter(start=5, ttl_value=-1)  # already over any limit; ttl() reports "no expiry"
    with pytest.raises(HTTPException) as exc:
        limits.hit(fake, "k", limit=1, window_s=30)
    assert exc.value.headers["Retry-After"] == "30"
