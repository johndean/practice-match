"""Fixed-window rate-limit helpers for the synchronous auth endpoints (signin/signup/
forgot-password, Task I4).

`hit()` is `app.ratelimit.hit` for a SYNCHRONOUS Redis client: the same key from the same
`bucket_key()` (so subjects — client IPs, normalised email addresses — enter Redis only as a
truncated SHA-256 pseudonym, and one bucket index owns one window), the same MULTI(INCR, EXPIRE)
so a key always carries a TTL even if the process dies between the two commands. The only
differences are the client and that going over the limit raises `deps.RateLimited` (decision A5's
429 body plus `Retry-After`) instead of returning a bool.

Fix round 1, Important 5: this module used to carry its OWN counter — a plain key handed in by the
caller, INCR-then-EXPIRE-only-on-1 — so the interest endpoint and the auth endpoints would have
limited the same IP under two different key schemes, and the pre-built key in its own documented
example (`f"rl:signin:ip:{ip}"`) would have put raw addresses into Redis."""
from __future__ import annotations

from typing import Any

from app.auth.deps import RateLimited
from app.ratelimit import bucket_key

SIGNIN_EMAIL, SIGNIN_IP, SIGNUP_IP, SIGNUP_EMAIL, FORGOT_EMAIL = (10, 900), (30, 900), (5, 3600), (3, 86400), (3, 3600)


def hit(r: Any, scope: str, subject: str, limit: int, window_s: int) -> None:
    """Counts one hit for `subject` in the current `window_s`-second window; raises `RateLimited`
    once the count is past `limit`. `Retry-After` is the whole window: the bucket rolls over at
    most one window from now, so it is an upper bound that never tells a caller to come back while
    it would still be refused."""
    key = bucket_key(scope, subject, window_s)
    with r.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window_s)
        count, _ = pipe.execute()
    if int(count) > limit:
        raise RateLimited(window_s)
