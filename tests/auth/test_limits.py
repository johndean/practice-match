"""app/auth/limits.py has no Step 1 test file in the brief's task-I3 — these close the coverage
gap for it (100% lines and branches, John's standing ruling). `client_ip`/`_host_only` moved to
`app.auth.deps` in fix round 1 (the brief's own interface list calls it `deps.client_ip`, and the
dependency direction has to be limits -> deps once `hit` raises `deps.RateLimited`); they are
exercised by `tests/api/test_interest.py` (real Starlette Request, every X-Forwarded-For shape),
`tests/auth/test_deps.py` (the plain-mapping stand-in) and `tests/auth/test_audit.py` (the forged
header) — one implementation, imported, not duplicated."""
import hashlib

import pytest

from app import ratelimit
from app.auth import limits
from app.auth.deps import RateLimited
from app.ratelimit import subject_key
from tests.conftest import WINDOW_EDGE


def test_limit_constants_are_the_spec_values():
    """EVERY pair, not the five the spec names (fix round 1, Minor 1). `FORGOT_IP` and `TOKEN_IP`
    were pinned NOWHERE, so tightening `TOKEN_IP` 30 -> 3 passed the whole suite — a member locked
    out after three token attempts against a runbook saying thirty, gate green. The six
    `LISTING_*` pairs (spec D17 and the SL3/SL4 reviews) had the same gap."""
    assert limits.SIGNIN_EMAIL == (10, 900)
    assert limits.SIGNIN_IP == (30, 900)
    assert limits.SIGNUP_IP == (5, 3600)
    assert limits.SIGNUP_EMAIL == (3, 86400)
    assert limits.FORGOT_EMAIL == (3, 3600)
    assert limits.FORGOT_IP == (10, 3600)
    assert limits.TOKEN_IP == (30, 3600)
    assert limits.LISTING_PATCH == (240, 3600)
    assert limits.LISTING_UPLOAD == (40, 3600)
    assert limits.LISTING_SUBMIT == (20, 3600)
    assert limits.LISTING_CREATE == (60, 3600)
    assert limits.LISTING_REORDER == (240, 3600)
    assert limits.LISTING_DELETE == (40, 3600)


def test_hit_counts_through_the_shared_counter_and_429s_on_the_next_call(redis):
    """Important 5: `limits.hit` was a SECOND counter — it neither imported nor called
    `app.ratelimit`, so the interest endpoint and the auth endpoints would have rate-limited the
    same IP under two different key schemes, with two windowing semantics to reason about. One
    key builder now, one MULTI shape."""
    limit, window = 3, 3600
    for _ in range(limit):
        limits.hit(redis, "signin_ip", "198.51.100.7", limit, window)
    with pytest.raises(RateLimited) as exc:
        limits.hit(redis, "signin_ip", "198.51.100.7", limit, window)
    assert exc.value.status_code == 429
    assert exc.value.detail == {"error": {"code": "RATE_LIMITED", "message": "Too many attempts. Try again later."}}
    assert 0 < int(exc.value.headers["Retry-After"]) <= window
    # THREE, not four: the refused attempt is not recorded (A-RL2), so knocking cannot extend it.
    assert redis.zcard(subject_key("signin_ip", "198.51.100.7")) == limit
    # A different subject is a different counter; a different scope is too.
    limits.hit(redis, "signin_ip", "203.0.113.9", limit, window)
    limits.hit(redis, "signup_ip", "198.51.100.7", limit, window)


def test_hit_pseudonymises_its_subject_so_no_raw_address_reaches_redis(redis):
    """`app.ratelimit.subject_key` hashes the subject on purpose — "a pseudonym that keeps raw
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
    assert keys[0] == subject_key("signin_email", email)


def test_every_hit_re_issues_the_expiry(redis):
    """Minor 8: EXPIRE was only issued when INCR returned exactly 1, so a key that somehow existed
    without a TTL never acquired one and every later hit on it 429'd forever. The shared MULTI
    shape sets the expiry on every hit."""
    key = subject_key("signin_ip", "198.51.100.7")
    redis.zadd(key, {"an-earlier-attempt": 1})  # no TTL at all
    assert redis.ttl(key) == -1
    limits.hit(redis, "signin_ip", "198.51.100.7", 30, 900)
    assert 0 < redis.ttl(key) <= 900


def test_ten_failures_that_straddle_a_window_edge_lock_the_address(redis, rate_limit_clock):
    """Task RATE-LIMIT-WINDOW at the helper the sign-in endpoint composes its lockout from.

    `bucket_key` divided the clock by the window, so the nine failures before a quarter-hour
    boundary and the one after it were counted in two different keys and the read — which saw only
    the LIVE one — reported a count of one. Ten failures two seconds apart, and the account open."""
    limit, window = limits.SIGNIN_EMAIL

    rate_limit_clock.move_to(WINDOW_EDGE - 1)
    for _ in range(limit - 1):
        limits.hit(redis, "signin:email", "lock@example.org", limit, window)
    rate_limit_clock.move_to(WINDOW_EDGE + 1)
    assert limits.hit(redis, "signin:email", "lock@example.org", limit, window) == limit

    with pytest.raises(RateLimited):
        limits.hit(redis, "signin:email", "lock@example.org", limit, window)


def test_an_attempt_a_full_window_old_has_left_the_window(redis, rate_limit_clock):
    """The boundary the other way, stated once for the one place that decides it: `_RESERVE`'s
    prune drops everything at or below `now - window`, so an attempt whose age is EXACTLY the
    window is gone and one a second younger is still counted."""
    limit, window = 3, 900

    rate_limit_clock.move_to(WINDOW_EDGE)
    for _ in range(limit):
        limits.hit(redis, "probe", "198.51.100.7", limit, window)

    rate_limit_clock.move_to(WINDOW_EDGE + window - 1)
    assert ratelimit.reserve(redis, "probe", "198.51.100.7", limit, window).admitted is False
    rate_limit_clock.move_to(WINDOW_EDGE + window)
    assert ratelimit.reserve(redis, "probe", "198.51.100.7", limit, window) == (True, 1, 0)


def test_the_stored_set_is_bounded_however_hard_a_subject_hammers_it(redis, rate_limit_clock):
    """A sorted set of attempt times is a list a flood could grow where a counter could not, and
    the refusal arm is what bounds it: an attempt that finds the window full is never recorded, so
    the set never holds more than `limit`, whatever a caller sends. (A-RL2's rank trim is belt and
    braces for one case this cannot reach — a limit REDUCED while keys are live.)"""
    limit, window = 3, 900
    rate_limit_clock.move_to(WINDOW_EDGE)
    for _ in range(limit):
        limits.hit(redis, "probe", "198.51.100.7", limit, window)
    for _ in range(200):
        with pytest.raises(RateLimited):
            limits.hit(redis, "probe", "198.51.100.7", limit, window)
    assert redis.zcard(subject_key("probe", "198.51.100.7")) == limit


def test_a_reduced_limit_trims_a_set_that_was_filled_under_the_old_one(redis, rate_limit_clock):
    """The rank trim's one live case. A deploy that TIGHTENS a limit meets keys holding more
    attempts than the new limit allows; the trim brings such a set down to the new limit on the
    next admitted attempt, so it behaves like a fresh key rather than refusing off a number nobody
    configures any more."""
    window = 900
    rate_limit_clock.move_to(WINDOW_EDGE)
    for _ in range(10):
        limits.hit(redis, "probe", "198.51.100.7", 10, window)
    assert redis.zcard(subject_key("probe", "198.51.100.7")) == 10

    # The limit is cut to three while those ten are still inside the window: refused, correctly.
    with pytest.raises(RateLimited):
        limits.hit(redis, "probe", "198.51.100.7", 3, window)
    # Once they age out, the first attempt under the new limit leaves the set at the new size.
    rate_limit_clock.move_to(WINDOW_EDGE + window)
    assert limits.hit(redis, "probe", "198.51.100.7", 3, window) == 1
    assert redis.zcard(subject_key("probe", "198.51.100.7")) == 1


def test_retry_after_is_the_wait_the_oldest_attempt_leaves(redis, rate_limit_clock):
    """Minor 4. `Retry-After` was the whole window on every refusal — an honest upper bound and
    wrong by up to a whole window. The script reads the oldest score it has just pruned against
    and answers the real figure, clamped into `[1, window]` so it can never promise an earlier
    answer than the window allows nor say "come back in zero seconds"."""
    limit, window = 3, 900
    rate_limit_clock.move_to(WINDOW_EDGE)
    for _ in range(limit):
        limits.hit(redis, "probe", "198.51.100.7", limit, window)

    rate_limit_clock.move_to(WINDOW_EDGE + 800)
    with pytest.raises(RateLimited) as exc:
        limits.hit(redis, "probe", "198.51.100.7", limit, window)
    assert exc.value.headers["Retry-After"] == "100"

    # One second before the oldest leaves, the floor holds rather than a zero.
    rate_limit_clock.move_to(WINDOW_EDGE + window - 0.5)
    with pytest.raises(RateLimited) as exc:
        limits.hit(redis, "probe", "198.51.100.7", limit, window)
    assert exc.value.headers["Retry-After"] == "1"


def test_the_clock_is_the_servers_own_not_the_callers(redis, rate_limit_clock):
    """Minor 6 — the skew the review measured. Every score, prune bound and TTL used to come from
    the API PROCESS's clock, so a replica five seconds ahead released a lockout early AND pruned
    the other replica's entries on its way past. The script reads `TIME` inside Redis, which is one
    clock for every replica there will ever be; a caller may still pass its own `now`, and nothing
    in the app does."""
    limit, window = 2, 60
    rate_limit_clock.move_to(WINDOW_EDGE)
    for _ in range(limit):
        limits.hit(redis, "probe", "one-subject", limit, window)

    # A caller whose own clock is a whole window ahead cannot talk its way past the server's.
    assert ratelimit.reserve(redis, "probe", "one-subject", limit, window).admitted is False
    # ...and the explicit-`now` door still works, which is what the async tests drive.
    assert ratelimit.reserve(redis, "probe", "one-subject", limit, window, now=WINDOW_EDGE + window).admitted


def test_clear_forgets_every_attempt_the_address_has(redis, rate_limit_clock):
    """What a correct password earns, and what makes the sign-in set hold FAILURES rather than
    attempts. One key holds the address's whole history, so `clear` needs no window and cannot
    leave a neighbouring bucket's failures behind."""
    limit, window = limits.SIGNIN_EMAIL
    rate_limit_clock.move_to(WINDOW_EDGE - 1)
    for _ in range(limit - 1):
        limits.hit(redis, "signin:email", "lock@example.org", limit, window)
    rate_limit_clock.move_to(WINDOW_EDGE + 1)
    limits.hit(redis, "signin:email", "lock@example.org", limit, window)

    limits.clear(redis, "signin:email", "lock@example.org")

    assert redis.keys("rl:signin:email:*") == []
    assert limits.hit(redis, "signin:email", "lock@example.org", limit, window) == 1
