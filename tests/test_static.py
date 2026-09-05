import httpx
from httpx import ASGITransport

from app.main import create_app

# `dist` and `client` are shared fixtures in tests/conftest.py (amended 2026-09-05); drop any import this module no longer uses.


async def test_root_serves_index_with_no_cache(client):
    r = await client.get("/")
    assert r.status_code == 200 and 'id="app"' in r.text
    assert r.headers["cache-control"] == "no-cache"


async def test_deep_link_falls_back_to_index(client):
    r = await client.get("/browse?tab=market")
    assert r.status_code == 200 and 'id="app"' in r.text


async def test_fingerprinted_bundle_is_immutable(client):
    r = await client.get("/_app/index-abc123.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


async def test_design_assets_are_short_cached_not_immutable(client):
    r = await client.get("/assets/icons/pad-lock.svg")
    assert r.status_code == 200 and r.text == "<svg/>"
    assert r.headers["cache-control"] == "public, max-age=3600"


async def test_api_404_wins_over_spa_fallback(client):
    r = await client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


async def test_noindex_until_public_indexing_is_enabled(client):
    r = await client.get("/")
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    robots = await client.get("/robots.txt")
    assert robots.status_code == 200 and robots.text == "User-agent: *\nDisallow: /\n"


async def test_indexing_allowed_when_flag_is_set(dist, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "public_indexing", True)
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url="http://test") as c:
        assert "x-robots-tag" not in (await c.get("/")).headers
        assert (await c.get("/robots.txt")).text == "User-agent: *\nAllow: /\n"


async def test_path_traversal_never_escapes_dist(client):
    r = await client.get("/..%2F..%2Fpyproject.toml")
    assert r.status_code == 200 and 'id="app"' in r.text  # falls back to index, not the file


def test_dist_for_selects_the_directory_by_mode():
    from app.static import COMING_SOON_DIST, DIST, dist_for
    assert dist_for("app") == DIST
    assert dist_for("coming_soon") == COMING_SOON_DIST


async def test_coming_soon_mode_serves_the_coming_soon_shell_everywhere_but_the_api(coming_dist, monkeypatch):
    import app.static
    from app.config import settings
    monkeypatch.setattr(settings, "site_mode", "coming_soon")
    monkeypatch.setattr(app.static, "COMING_SOON_DIST", coming_dist)
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        for path in ("/", "/browse", "/practices/p1", "/..%2F..%2Fpyproject.toml"):
            r = await c.get(path)
            assert r.status_code == 200 and "VIN Foundation — Coming Soon" in r.text, path
            assert r.headers["cache-control"] == "no-cache"
        assert (await c.get("/_app/index-cs1.js")).headers["cache-control"] == "public, max-age=31536000, immutable"
        assert (await c.get("/ds/colors_and_type.css")).headers["cache-control"] == "public, max-age=3600"
        r = await c.get("/api/nope")
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
        assert (await c.get("/api/healthz")).json()["site_mode"] == "coming_soon"


async def test_app_mode_never_serves_the_coming_soon_shell(client):
    r = await client.get("/")
    assert "Coming Soon" not in r.text
    assert (await client.get("/api/healthz")).json()["site_mode"] == "app"
