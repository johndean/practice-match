import asyncio

import httpx
from httpx import ASGITransport

from app import db
from app.checks import async_dsn
from app.config import settings
from app.main import create_app

PREFLIGHT_HEADERS = {
    "Origin": "https://qa.foundation.vin",
    "Access-Control-Request-Method": "GET",
}


async def test_cors_preflight_allows_configured_origin(monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", "https://qa.foundation.vin")
    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.options("/api/healthz", headers=PREFLIGHT_HEADERS)
        assert r.headers.get("access-control-allow-origin") == "https://qa.foundation.vin"


async def test_cors_header_absent_without_configured_origins(monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", "")
    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.options("/api/healthz", headers=PREFLIGHT_HEADERS)
        assert "access-control-allow-origin" not in r.headers


async def test_lifespan_disposes_the_pool_on_shutdown():
    """Round 4: dispose_all() is wired into the app's own lifespan (not a
    loop-close hook) — production's one long-lived loop is cleaned up on shutdown."""
    dsn = async_dsn(settings.database_url)
    loop = asyncio.get_running_loop()
    app = create_app()
    db.get_engine(dsn)
    assert dsn in db._engines.get(loop, {})
    async with app.router.lifespan_context(app):
        pass
    assert dsn not in db._engines.get(loop, {})
