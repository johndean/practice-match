import httpx
from httpx import ASGITransport

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
