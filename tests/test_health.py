import logging
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from app.api import health
from app.checks import async_dsn, check_db, check_redis
from app.config import settings
from app.main import app
from app.version import VERSION

KEYS = {"status", "version", "environment", "commit_sha", "db", "redis", "site_mode"}


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def components_down(monkeypatch):
    # Real connection failures (closed port), not mocks.
    monkeypatch.setattr(settings, "database_url", "postgresql://x:x@127.0.0.1:1/x")
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")


async def test_healthz_has_the_contract_keys(client):
    r = await client.get("/api/healthz")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == KEYS
    assert body["status"] == "ok"
    assert body["version"] == VERSION
    assert body["environment"] == "test"
    assert "ok" in body["db"] and "ok" in body["redis"]


async def test_healthz_stays_200_with_components_down(client, components_down):
    r = await client.get("/api/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["db"]["ok"] is False and "error" in body["db"]
    assert body["redis"]["ok"] is False and "error" in body["redis"]


async def test_healthz_error_text_is_generic_and_detail_is_logged(client, components_down, caplog):
    caplog.set_level(logging.WARNING, logger="app.checks")
    r = await client.get("/api/healthz")
    body = r.json()
    db_error = body["db"]["error"]
    redis_error = body["redis"]["error"]
    assert db_error.isidentifier() and " " not in db_error
    assert redis_error.isidentifier() and " " not in redis_error
    assert "health check failed" in caplog.text


async def test_deep_healthz_is_503_with_components_down(client, components_down):
    r = await client.get("/api/healthz/deep")
    assert r.status_code == 503
    assert r.json()["db"]["ok"] is False


def test_async_dsn_accepts_the_legacy_postgres_scheme():
    """Railway's PostGIS template emits postgres://, not postgresql:// (fix round 5)."""
    assert async_dsn("postgres://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"
    assert async_dsn("postgresql://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"
    assert async_dsn("postgresql+asyncpg://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"


def test_async_dsn_rewrite_is_anchored_to_the_scheme_prefix():
    """The dialect-suffix rewrite must only ever touch the DSN's own leading scheme,
    never a substring found elsewhere in the URL (Task 9 fix round 1, folded in from
    the Task 5 round-5 re-review: the inherited `str.replace(..., 1)` fallback was
    unanchored)."""
    already_asyncpg = "postgresql+asyncpg://u:p@h/db?x=postgresql://y"
    assert async_dsn(already_asyncpg) == already_asyncpg
    assert async_dsn("postgresql://u:p@h/db?x=postgresql://y") == "postgresql+asyncpg://u:p@h/db?x=postgresql://y"
    # Proves the anchoring actually matters: an unanchored `.replace("postgresql://",
    # ..., 1)` would leave this DSN's own (non-postgres) scheme alone but still find
    # and mangle the embedded "postgresql://" inside the query value, since it's the
    # first (and only) match in the string.
    assert async_dsn("mysql://u:p@h/db?x=postgresql://y") == "mysql://u:p@h/db?x=postgresql://y"


async def test_check_db_degrades_on_malformed_dsn_instead_of_raising():
    result = await check_db("not-a-dsn")
    assert result == {"ok": False, "error": "ArgumentError"}


async def test_check_redis_degrades_on_malformed_url_instead_of_raising():
    result = await check_redis("not-a-url")
    assert result == {"ok": False, "error": "ValueError"}


async def test_unknown_api_route_is_json_404_not_index(client):
    r = await client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["error"]["code"] == "NOT_FOUND"


async def test_head_on_health_endpoints_is_200_with_no_body(client):
    for path in ("/api/healthz", "/api/healthz/deep"):
        head = await client.head(path)
        assert head.status_code in (200, 503), path  # deep may be 503 when a component is down; never 405
        assert head.content == b"", path


async def test_head_on_an_unknown_api_route_is_the_json_404_status(client):
    head = await client.head("/api/does-not-exist")
    assert head.status_code == 404 and head.content == b""


import re


async def test_healthz_reports_postgis_and_redis_up(client, db_ready):
    body = (await client.get("/api/healthz")).json()
    assert body["db"]["ok"] is True, body["db"]
    assert re.match(r"^3\.\d+", body["db"]["postgis_version"])
    assert body["redis"]["ok"] is True, body["redis"]
    r = await client.get("/api/healthz/deep")
    assert r.status_code == 200


# --- P14: commit_sha proves the ARTEFACT, not a service variable ----------------
# healthz reported the COMMIT_SHA variable scripts/deploy.sh sets immediately before each
# upload, so on 2026-09-07 it agreed with a deploy whose uploaded tree was a different
# one. BUILD_SHA is written into the `git archive` deploy.sh uploads and copied into the
# image, so it cannot drift from the code that is serving.


@pytest.fixture
def stamp_cache_cleared():
    """L8: build_sha() is cached — the stamp cannot change inside a running image, and
    /api/healthz is Railway's healthcheck and the nightly k6 target, so it must not do a
    file read per request. A test that moves BUILD_SHA_FILE has to clear the cache either
    side of itself."""
    health.build_sha.cache_clear()
    yield
    health.build_sha.cache_clear()


async def test_commit_sha_is_read_once_not_on_every_request(client, monkeypatch, tmp_path, stamp_cache_cleared):
    """The stamp is baked into the image; re-reading it per request buys nothing and puts a
    blocking file read on the healthcheck path."""
    stamp = tmp_path / "BUILD_SHA"
    stamp.write_text("17f40c3\n")
    reads = 0
    real_read_text = type(stamp).read_text

    def counting_read_text(self, *args, **kwargs):
        nonlocal reads
        reads += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(health, "BUILD_SHA_FILE", stamp)
    monkeypatch.setattr(type(stamp), "read_text", counting_read_text)
    for _ in range(3):
        assert (await client.get("/api/healthz")).json()["commit_sha"] == "17f40c3"
    assert reads == 1, f"the stamp must be read once, not once per request (read {reads} times)"


async def test_commit_sha_falls_back_when_the_stamp_is_not_valid_utf8(client, monkeypatch, tmp_path, stamp_cache_cleared):
    """UnicodeDecodeError is not an OSError, so a non-UTF-8 stamp turned the deliberately
    always-200 healthz into a 500 — and Railway's healthcheck with it. This module must
    never be the thing that breaks."""
    stamp = tmp_path / "BUILD_SHA"
    stamp.write_bytes(b"\xff\xfe not utf-8 \x00")
    monkeypatch.setattr(health, "BUILD_SHA_FILE", stamp)
    monkeypatch.setattr(settings, "commit_sha", "fallback9")
    r = await client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json()["commit_sha"] == "fallback9"


async def test_commit_sha_comes_from_the_build_sha_file_when_the_image_carries_one(client, monkeypatch, tmp_path, stamp_cache_cleared):
    stamp = tmp_path / "BUILD_SHA"
    stamp.write_text("17f40c3\n")  # trailing newline: deploy.sh writes one
    monkeypatch.setattr(health, "BUILD_SHA_FILE", stamp)
    monkeypatch.setattr(settings, "commit_sha", "variable-only")
    body = (await client.get("/api/healthz")).json()
    assert body["commit_sha"] == "17f40c3"


async def test_commit_sha_falls_back_to_the_setting_when_the_file_is_absent(client, monkeypatch, tmp_path, stamp_cache_cleared):
    """A git-connected Railway build, or a local `docker build`, carries no BUILD_SHA."""
    monkeypatch.setattr(health, "BUILD_SHA_FILE", tmp_path / "no-such-dir" / "BUILD_SHA")
    monkeypatch.setattr(settings, "commit_sha", "fallback9")
    body = (await client.get("/api/healthz")).json()
    assert body["commit_sha"] == "fallback9"


async def test_commit_sha_falls_back_when_the_build_sha_file_is_blank(client, monkeypatch, tmp_path, stamp_cache_cleared):
    """An empty stamp is no evidence; it must not shadow COMMIT_SHA with an empty string."""
    stamp = tmp_path / "BUILD_SHA"
    stamp.write_text("  \n")
    monkeypatch.setattr(health, "BUILD_SHA_FILE", stamp)
    monkeypatch.setattr(settings, "commit_sha", "fallback9")
    body = (await client.get("/api/healthz")).json()
    assert body["commit_sha"] == "fallback9"


def test_build_sha_file_sits_at_the_app_root_beside_pyproject():
    """WORKDIR /app in the image, code at /app/app/api/health.py: the stamp is /app/BUILD_SHA,
    the same root app/version.py reads pyproject.toml from."""
    root = Path(__file__).resolve().parent.parent
    assert health.BUILD_SHA_FILE == root / "BUILD_SHA"
    assert (root / "pyproject.toml").exists()
