"""`GET /api/config` — the runtime source of MARKET_DATA_PUBLIC (A-I7.2, review Important 4).

`can('market.read', me, { marketDataPublic })` had no way to learn the flag: it lives only in
`app/config.py` and `app/auth/permissions.allowed`, and neither `/api/me` nor
`/api/admin/permissions` publishes it. This endpoint does, to anybody — an anonymous visitor is
exactly who the flag is about.
"""
import httpx
import pytest
from httpx import ASGITransport

from app.auth.permissions import PUBLIC_ROUTES
from app.config import settings
from app.main import create_app


@pytest.mark.parametrize("flag", [False, True])
async def test_config_publishes_the_market_data_flag_to_an_anonymous_visitor(client, monkeypatch, flag):
    monkeypatch.setattr(settings, "market_data_public", flag)
    response = await client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"market_data_public": flag}


def test_config_is_declared_public():
    """The route carries no `require(...)`, so `test_every_route_is_guarded_or_public` only passes
    while it is listed here. Asserted directly too, so the reason is written down beside it."""
    assert ("GET", "/api/config") in PUBLIC_ROUTES


async def test_config_is_served_in_coming_soon_mode_too(dist, redis, monkeypatch):
    """Included in `create_app` UNCONDITIONALLY, unlike the auth surface: the flag says whether an
    anonymous visitor may see market data, which is a question the Coming Soon site can be asked
    about the app it fronts, and the answer reveals nothing and writes nothing."""
    monkeypatch.setattr(settings, "site_mode", "coming_soon")
    monkeypatch.setattr(settings, "market_data_public", True)
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url="http://test") as c:
        assert (await c.get("/api/auth/signin")).status_code == 404      # the auth surface really is gated off
        assert (await c.get("/api/config")).json() == {"market_data_public": True}
