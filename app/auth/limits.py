"""Sliding-window rate limits for the synchronous auth endpoints (signin/signup/forgot-password,
Task I4) and the seller-listing lifecycle (D17).

`hit()` is `app.ratelimit.reserve` for a SYNCHRONOUS Redis client: the same key from the same
`subject_key()` (so subjects — client IPs, normalised email addresses, account ids — enter Redis
only as a truncated SHA-256 pseudonym), the same one atomic script. The only differences are the
client and that a refusal raises `deps.RateLimited` (decision A5's 429 body plus `Retry-After`)
instead of returning a bool.

ONE function per attempt since amendment A-RL2: `check`/`count_failure` are gone. They were a
lockout composed of a read and a later write, and everything that arrived between them read the
same pre-write count — see `app/ratelimit.py`. Their two jobs are now one call: `hit` RESERVES the
slot and RETURNS how many are inside the window, so the sign-in endpoint refuses and writes its
audit row from one number that no other request can have seen.

Fix round 1, Important 5: this module used to carry its OWN counter — a plain key handed in by the
caller, INCR-then-EXPIRE-only-on-1 — so the interest endpoint and the auth endpoints would have
limited the same IP under two different key schemes, and the pre-built key in its own documented
example (`f"rl:signin:ip:{ip}"`) would have put raw addresses into Redis."""
from __future__ import annotations

from typing import Any

from app import ratelimit
from app.auth.deps import RateLimited

SIGNIN_EMAIL, SIGNIN_IP, SIGNUP_IP, SIGNUP_EMAIL, FORGOT_EMAIL = (10, 900), (30, 900), (5, 3600), (3, 86400), (3, 3600)
# I4 fix round 1, Minor 6: `password/forgot` had no per-IP ceiling and `verify`/`reset` had none at
# all — 60 consecutive token attempts were unthrottled. The tokens are 256-bit, so guessing is not
# the risk; the connection is, which is why these are additions to the spec's per-address limits
# rather than replacements for them.
FORGOT_IP, TOKEN_IP = (10, 3600), (30, 3600)
# Seller listing lifecycle (spec 2026-09-08 D17), all keyed on the ACCOUNT id: generous enough that
# a seller working through eight steps and four photographs never meets one, tight enough that a
# script cannot fill one. `LISTING_PATCH` is the autosave — the design's own "Saved
# automatically" fires once per step, not per keystroke, so 240/hour is four hours of continuous work.
LISTING_PATCH, LISTING_UPLOAD, LISTING_SUBMIT = (240, 3600), (40, 3600), (20, 3600)
# The three D17 left out, added by the SL3/SL4 reviews (A-SL13 L4, A-SL16 M3): `create` mints a
# row (and a unique slug) per call, `reorder` is a PATCH like any other, and `delete` makes a bucket
# round trip per call. Same shape, same per-account key, generous enough that nobody working through
# the wizard meets one.
LISTING_CREATE, LISTING_REORDER, LISTING_DELETE = (60, 3600), (240, 3600), (40, 3600)


def clear(r: Any, scope: str, subject: str) -> None:
    """Forgets `subject`'s attempts — what a successful credential check earns, and what makes the
    sign-in set hold failures rather than attempts. One key holds them all, so this needs no window."""
    r.delete(ratelimit.subject_key(scope, subject))


def hit(r: Any, scope: str, subject: str, limit: int, window_s: int) -> int:
    """Reserves one slot for `subject` in the last `window_s` seconds and answers how many are
    inside it, this one included; raises `RateLimited` when there is no room.

    The reservation is taken BEFORE the caller does the work it gates — for sign-in, before the
    Argon2id verify — which is the whole point: the decision and the record are one server-side
    step, so two simultaneous callers cannot both be the last one admitted (A-RL2).

    `Retry-After` is the exact wait the oldest attempt in the window leaves, computed by the same
    script from the same set, never more than the window itself. A refused attempt is not recorded,
    so knocking cannot push that answer further away."""
    reservation = ratelimit.reserve(r, scope, subject, limit, window_s)
    if not reservation.admitted:
        raise RateLimited(reservation.retry_after)
    return reservation.in_window
