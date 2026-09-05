import logging

import httpx
import pytest
from httpx import ASGITransport

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


import re


async def test_healthz_reports_postgis_and_redis_up(client, db_ready):
    body = (await client.get("/api/healthz")).json()
    assert body["db"]["ok"] is True, body["db"]
    assert re.match(r"^3\.\d+", body["db"]["postgis_version"])
    assert body["redis"]["ok"] is True, body["redis"]
    r = await client.get("/api/healthz/deep")
    assert r.status_code == 200
