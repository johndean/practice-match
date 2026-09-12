"""`app.cache.drop_list_cache_quietly` (Task CACHE-DROP-GUARD, 2026-09-12).

GEO-WIRE guarded its own two `drop_list_cache(sync_redis())` call sites (`app/tasks/census.py`,
`scripts/census_load.py`) inline; its reviewer found the same bare shape at ten pre-existing sites
in `app/api/seller_listings.py` and `app/api/admin_listings.py`, every one AFTER its own
transaction had already committed (D16) — so a Redis blip there turned a successful publish /
republish / photo upload / decision into a 500 for a caller whose row had already changed. This
file is the unit coverage for the one helper that now guards every one of those ten call sites (the
route-level RED/GREEN proof — that a route still answers its success status and the row stays
committed when the drop itself raises — lives beside each route's own tests:
`tests/api/test_admin_listings.py` for the publish path, `tests/api/test_listing_assets.py` for a
photo-upload path)."""
from __future__ import annotations

import logging

import pytest
import redis as redis_sync

from app import cache as cache_module


def test_drop_list_cache_quietly_returns_true_and_really_drops_a_planted_key(redis: object) -> None:
    """The ordinary path, against the real (fake) client the `redis` fixture wires up: the default
    `redis_factory` is `sync_redis` itself, so calling the helper with no arguments reaches the
    same client `drop_list_cache(sync_redis())` always did."""
    redis.set("listings:v1:::50", b"stale page")  # type: ignore[attr-defined]
    assert cache_module.drop_list_cache_quietly() is True
    assert redis.get("listings:v1:::50") is None  # type: ignore[attr-defined]


def test_a_connection_error_is_swallowed_logged_once_and_returns_false(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The failure this helper exists to bound. Only the exception's TYPE is logged, never its
    text, which can carry a host and port — `app/tasks/census.py`'s own rule for its twin guard at
    `geocode_listing`, and `app/api/admin_data_sources.py`'s for a different cache entirely."""

    def _boom(cache: object) -> int:
        raise redis_sync.exceptions.ConnectionError("redis://someone:6379 is having a moment")

    monkeypatch.setattr(cache_module, "drop_list_cache", _boom)

    with caplog.at_level(logging.WARNING, logger="app.cache"):
        assert cache_module.drop_list_cache_quietly(redis_factory=lambda: object()) is False

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "ConnectionError" in warnings[0].getMessage()
    assert "6379" not in warnings[0].getMessage(), "the type, never the text: it can carry a host"


def test_a_non_redis_error_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other side of the narrow `except`: a `TypeError` (or anything else that is not a
    `redis.RedisError`) is this codebase's own defect, not an infrastructure blip, and swallowing
    it would hide it for as long as nobody reads the logs."""

    def _boom(cache: object) -> int:
        raise TypeError("drop_list_cache() got an unexpected keyword argument")

    monkeypatch.setattr(cache_module, "drop_list_cache", _boom)

    with pytest.raises(TypeError):
        cache_module.drop_list_cache_quietly(redis_factory=lambda: object())


def test_the_redis_factory_itself_failing_is_swallowed_the_same_way(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """"Obtains the client, calls the drop" (the brief's own words): a failure building the client
    is inside the same try as a failure running the drop, so a connection refused before a single
    command is sent is guarded exactly like one that fails mid-`SCAN`."""

    def _refused() -> redis_sync.Redis:
        raise redis_sync.exceptions.ConnectionError("redis://someone:6379 refused the connection")

    with caplog.at_level(logging.WARNING, logger="app.cache"):
        assert cache_module.drop_list_cache_quietly(redis_factory=_refused) is False

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "ConnectionError" in warnings[0].getMessage()
    assert "6379" not in warnings[0].getMessage()
