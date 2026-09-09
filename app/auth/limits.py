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
# I4 fix round 1, Minor 6: `password/forgot` had no per-IP ceiling and `verify`/`reset` had none at
# all — 60 consecutive token attempts were unthrottled. The tokens are 256-bit, so guessing is not
# the risk; the connection is, which is why these are additions to the spec's per-address limits
# rather than replacements for them.
FORGOT_IP, TOKEN_IP = (10, 3600), (30, 3600)
# Seller listing lifecycle (spec 2026-09-08 D17), all keyed on the ACCOUNT id: generous enough that
# a seller working through eight steps and four photographs never meets one, tight enough that a
# script cannot fill a bucket. `LISTING_PATCH` is the autosave — the design's own "Saved
# automatically" fires once per step, not per keystroke, so 240/hour is four hours of continuous work.
LISTING_PATCH, LISTING_UPLOAD, LISTING_SUBMIT = (240, 3600), (40, 3600), (20, 3600)
# The three D17 left out, added by the SL3/SL4 reviews (A-SL13 L4, A-SL16 M3): `create` mints a
# row (and a unique slug) per call, `reorder` is a PATCH like any other, and `delete` makes a bucket
# round trip per call. Same shape, same per-account key, generous enough that nobody working through
# the wizard meets one.
LISTING_CREATE, LISTING_REORDER, LISTING_DELETE = (60, 3600), (240, 3600), (40, 3600)


def check(r: Any, scope: str, subject: str, limit: int, window_s: int) -> None:
    """Refuses when `subject` is ALREADY at `limit` in this window, WITHOUT counting this call.

    Paired with `count_failure` and `clear`, this is spec §3's "N failures per window" lockout.
    `hit` counts every call, which is right for a request-rate ceiling and wrong for a lockout: the
    sign-in endpoint used it, so ten SUCCESSFUL sign-ins in fifteen minutes locked a member out of
    their own account (fix round 1, Important 1)."""
    count = r.get(bucket_key(scope, subject, window_s))
    if count is not None and int(count) >= limit:
        raise RateLimited(window_s)


def count_failure(r: Any, scope: str, subject: str, window_s: int) -> int:
    """Counts one failure in the current window and returns the new count, so the caller can act on
    a threshold (the sign-in endpoint writes an audit row at the fifth). Same key, same MULTI(INCR,
    EXPIRE) as `hit` — only the decision to count belongs to the caller."""
    key = bucket_key(scope, subject, window_s)
    with r.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window_s)
        count, _ = pipe.execute()
    return int(count)


def clear(r: Any, scope: str, subject: str, window_s: int) -> None:
    """Forgets `subject`'s failures — what a successful credential check earns."""
    r.delete(bucket_key(scope, subject, window_s))


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
