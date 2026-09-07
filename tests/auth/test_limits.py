"""app/auth/limits.py has no Step 1 test file in the brief's task-I3 — these close the coverage
gap for it (100% lines and branches, John's standing ruling). `client_ip`/`_host_only` moved to
`app.auth.deps` in fix round 1 (the brief's own interface list calls it `deps.client_ip`, and the
dependency direction has to be limits -> deps once `hit` raises `deps.RateLimited`); they are
exercised by `tests/api/test_interest.py` (real Starlette Request, every X-Forwarded-For shape),
`tests/auth/test_deps.py` (the plain-mapping stand-in) and `tests/auth/test_audit.py` (the forged
header) — one implementation, imported, not duplicated."""
import hashlib

import pytest

from app.auth import limits
from app.auth.deps import RateLimited
from app.ratelimit import bucket_key


def test_limit_constants_are_the_spec_values():
    assert limits.SIGNIN_EMAIL == (10, 900)
    assert limits.SIGNIN_IP == (30, 900)
    assert limits.SIGNUP_IP == (5, 3600)
    assert limits.SIGNUP_EMAIL == (3, 86400)
    assert limits.FORGOT_EMAIL == (3, 3600)


def test_hit_counts_through_the_shared_bucket_and_429s_on_the_next_call(redis):
    """Important 5: `limits.hit` was a SECOND counter — it neither imported nor called
    `app.ratelimit`, so the interest endpoint and the auth endpoints would have rate-limited the
    same IP under two different key schemes, with two windowing semantics to reason about. One
    key builder now, one MULTI(INCR, EXPIRE) shape."""
    limit, window = 3, 3600
    for _ in range(limit):
        limits.hit(redis, "signin_ip", "198.51.100.7", limit, window)
    with pytest.raises(RateLimited) as exc:
        limits.hit(redis, "signin_ip", "198.51.100.7", limit, window)
    assert exc.value.status_code == 429
    assert exc.value.detail == {"error": {"code": "RATE_LIMITED", "message": "Too many attempts. Try again later."}}
    assert 0 < int(exc.value.headers["Retry-After"]) <= window
    assert redis.get(bucket_key("signin_ip", "198.51.100.7", window)) == b"4"
    # A different subject is a different bucket; a different scope is too.
    limits.hit(redis, "signin_ip", "203.0.113.9", limit, window)
    limits.hit(redis, "signup_ip", "198.51.100.7", limit, window)


def test_hit_pseudonymises_its_subject_so_no_raw_address_reaches_redis(redis):
    """`app.ratelimit.bucket_key` hashes the subject on purpose — "a pseudonym that keeps raw
    addresses out of Redis". `limits.hit` took a pre-built key and its own documented example was
    `f"rl:signin:ip:{ip}"`, so following it would have put raw client IPs and raw EMAIL ADDRESSES
    (SIGNIN_EMAIL/SIGNUP_EMAIL/FORGOT_EMAIL are keyed by address) into Redis in plaintext."""
    email = "dr.mendes@practice.example"
    limits.hit(redis, "signin_email", email, *limits.SIGNIN_EMAIL)
    keys = [k.decode() for k in redis.keys("*")]
    assert len(keys) == 1
    assert email not in keys[0] and "practice.example" not in keys[0]
    assert keys[0].startswith("rl:signin_email:")
    assert hashlib.sha256(email.encode()).hexdigest()[:16] in keys[0]
    assert keys[0] == bucket_key("signin_email", email, limits.SIGNIN_EMAIL[1])


def test_every_hit_re_issues_the_expiry(redis):
    """Minor 8: EXPIRE was only issued when INCR returned exactly 1, so a key that somehow existed
    without a TTL never acquired one and every later hit on it 429'd forever. The shared MULTI
    shape sets the expiry on every hit."""
    key = bucket_key("signin_ip", "198.51.100.7", 900)
    redis.set(key, 1)  # no TTL at all
    assert redis.ttl(key) == -1
    limits.hit(redis, "signin_ip", "198.51.100.7", 30, 900)
    assert 0 < redis.ttl(key) <= 900
