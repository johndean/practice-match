"""`scripts/reset_rate_limits.py` — controller amendment A-S5.1 (John's ruling, 2026-09-08).

The rate limits are security controls and are not moved for tests: `SIGNIN_IP` stays 30 per fixed
15-minute window, `FORGOT_IP` 10 per hour, `SIGNUP_IP` 5 per hour, and `tests/api/test_auth.py`
still proves each of them refuses. What John refused is the CONSEQUENCE the harness had inherited —
"three local suite runs an hour" — so the local test environment's counter state is cleared before
the API serves, and consecutive runs are independent.

Everything the script may do is fenced by two conditions it checks itself, because a script whose
only safety is where it happens to be called from is one edit away from running somewhere else:
`ENVIRONMENT` must be exactly `test`, and the Redis host must be loopback. It deletes only keys
under `app.ratelimit.bucket_key`'s own `rl:` prefix, by SCAN + DEL — never `FLUSHDB`, which would
also take the session cache and the outbox locks that share the database.
"""
from __future__ import annotations

import pytest

from app import cache
from app.ratelimit import bucket_key
from scripts import reset_rate_limits


def _limits(r) -> None:
    """A handful of real rate-limit buckets, keyed exactly as the app keys them."""
    r.set(bucket_key("signin:ip", "203.0.113.7", 900), 3)
    r.set(bucket_key("forgot:email", "someone@example.org", 3600), 2)
    r.set(bucket_key("signup:ip", "203.0.113.7", 3600), 1)


def test_it_deletes_every_rate_limit_bucket_and_prints_how_many(redis, monkeypatch, capsys):
    monkeypatch.setattr(cache.settings, "environment", "test")
    monkeypatch.setattr(cache.settings, "redis_url", "redis://localhost:6380/0")
    _limits(redis)
    assert len(redis.keys("rl:*")) == 3

    assert reset_rate_limits.main([]) == 0

    assert redis.keys("rl:*") == []
    out = capsys.readouterr().out
    assert "3" in out, out
    # Only the count. A subject enters a bucket key as a truncated SHA-256 pseudonym, which is not
    # an anonymisation (app/ratelimit.py says so), and a CI log is not the place for either.
    assert "203.0.113.7" not in out
    assert "someone@example.org" not in out


def test_it_leaves_every_other_key_in_the_database_alone(redis, monkeypatch):
    """SCAN + DEL over `rl:*`, never FLUSHDB: the 60 s session cache and the outbox's idempotency
    locks live in the same database, and dropping a live session mid-run would fail tests far from
    the cause."""
    monkeypatch.setattr(cache.settings, "environment", "test")
    monkeypatch.setattr(cache.settings, "redis_url", "redis://127.0.0.1:6380/0")
    _limits(redis)
    redis.set("sess:abc", "a live session")
    redis.set("outbox:lock:1", "held")

    assert reset_rate_limits.main([]) == 0

    assert redis.keys("rl:*") == []
    assert redis.get("sess:abc") == b"a live session"
    assert redis.get("outbox:lock:1") == b"held"


def test_an_empty_database_is_not_an_error(redis, monkeypatch, capsys):
    monkeypatch.setattr(cache.settings, "environment", "test")
    monkeypatch.setattr(cache.settings, "redis_url", "redis://localhost:6380/0")

    assert reset_rate_limits.main([]) == 0
    assert "0" in capsys.readouterr().out


@pytest.mark.parametrize("environment", ["production", "qa", "QA", "Test", "development", ""])
def test_it_refuses_anywhere_but_the_test_environment(redis, monkeypatch, capsys, environment):
    """Fails CLOSED. `test` exactly — not a prefix, not case-insensitively — so a value nobody
    anticipated is a refusal rather than a match."""
    monkeypatch.setattr(cache.settings, "environment", environment)
    monkeypatch.setattr(cache.settings, "redis_url", "redis://localhost:6380/0")
    _limits(redis)

    assert reset_rate_limits.main([]) != 0
    assert len(redis.keys("rl:*")) == 3, "a refusal must delete nothing"
    assert capsys.readouterr().err.strip().count("\n") == 0, "one line to stderr"


@pytest.mark.parametrize(
    "url",
    [
        "redis://qa-redis.railway.internal:6379/0",
        "redis://:pw@some-host:6379/0",
        "redis://localhost.evil.example:6379/0",
        "rediss://127.0.0.1.evil.example:6379/0",
    ],
)
def test_it_refuses_a_redis_that_is_not_on_this_machine(redis, monkeypatch, capsys, url):
    monkeypatch.setattr(cache.settings, "environment", "test")
    monkeypatch.setattr(cache.settings, "redis_url", url)
    _limits(redis)

    assert reset_rate_limits.main([]) != 0
    assert len(redis.keys("rl:*")) == 3
    err = capsys.readouterr().err
    assert err.strip().count("\n") == 0
    # The refusal names the host, never the credential the URL may carry.
    assert "pw@" not in err


@pytest.mark.parametrize("url", ["redis://localhost:6380/0", "redis://127.0.0.1:6380/1", "rediss://localhost:6380/0"])
def test_loopback_in_its_documented_spellings_is_accepted(redis, monkeypatch, url):
    monkeypatch.setattr(cache.settings, "environment", "test")
    monkeypatch.setattr(cache.settings, "redis_url", url)
    _limits(redis)

    assert reset_rate_limits.main([]) == 0
    assert redis.keys("rl:*") == []


def test_a_url_with_no_host_at_all_is_refused(redis, monkeypatch):
    """`urlsplit` yields `None` for a hostname it cannot find; the guard must treat that as "not
    local" rather than compare `None` against the allowed set and fall through."""
    monkeypatch.setattr(cache.settings, "environment", "test")
    monkeypatch.setattr(cache.settings, "redis_url", "redis:///0")
    _limits(redis)

    assert reset_rate_limits.main([]) != 0
    assert len(redis.keys("rl:*")) == 3


def test_the_cli_entry_point_runs_as___main__(redis, monkeypatch):
    """`if __name__ == "__main__": raise SystemExit(main())` never executes on import, and a
    subprocess's coverage is not reported back to this process — the pattern
    `tests/api/test_admin_users.py` already uses for the other two scripts."""
    import runpy
    import sys
    from pathlib import Path

    monkeypatch.setattr(cache.settings, "environment", "test")
    monkeypatch.setattr(cache.settings, "redis_url", "redis://localhost:6380/0")
    monkeypatch.setattr(sys, "argv", ["reset_rate_limits"])
    root = Path(__file__).resolve().parent.parent
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(root / "scripts" / "reset_rate_limits.py"), run_name="__main__")
    assert exc.value.code == 0
