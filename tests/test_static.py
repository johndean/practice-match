from pathlib import Path

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
        assert (await c.get("/assets/vin-foundation-logo.png")).headers["cache-control"] == "public, max-age=3600"
        r = await c.get("/api/nope")
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
        assert (await c.get("/api/healthz")).json()["site_mode"] == "coming_soon"


async def test_app_mode_never_serves_the_coming_soon_shell(client):
    r = await client.get("/")
    assert "Coming Soon" not in r.text
    assert (await client.get("/api/healthz")).json()["site_mode"] == "app"


def test_mount_spa_mounts_nothing_when_the_built_site_is_missing(tmp_path):
    from fastapi import FastAPI

    from app.static import mount_spa
    app = FastAPI()
    before = len(app.routes)
    mount_spa(app, tmp_path / "no-such-dist")
    assert len(app.routes) == before  # nothing served, nothing crashes; the health probe still answers


async def test_head_answers_like_get_without_a_body(client):
    """Uptime monitors and link checkers send HEAD; it must mirror GET (status and headers), body empty (Task 13a)."""
    for path in ("/", "/browse", "/_app/index-abc123.js", "/assets/icons/pad-lock.svg", "/robots.txt"):
        get = await client.get(path)
        head = await client.head(path)
        assert head.status_code == get.status_code == 200, path
        assert head.headers.get("cache-control") == get.headers.get("cache-control"), path
        assert head.headers.get("content-type") == get.headers.get("content-type"), path
        assert head.content == b"", path


# --- Task P9: the ONE public, unauthenticated path that can return image bytes -------------------
#
# `mount_spa` serves everything under the built site to anybody — no session, no permission, no
# resolver. That is right for the bundle, the design-system CSS and the fonts, and it is why what
# lives there has to be pinned: a seller's photograph copied into `frontend/public` would be served
# to the whole internet with `buyer_variant` never asked.

_ROOT = Path(__file__).resolve().parent.parent
_PUBLIC = _ROOT / "frontend" / "public"


def test_public_photos_are_exactly_the_three_design_fixtures() -> None:
    """The design's own Round Rock fixtures (amendment A19's lightbox states photograph these),
    committed to the repository and shipped in the bundle. NOTHING else: no seller upload, no seed
    hospital, no derivative of either."""
    photos = sorted(f.name for f in (_PUBLIC / "assets" / "photos").iterdir() if f.is_file())
    assert photos == ["round-rock-exterior-parking.jpeg", "round-rock-exterior-side.webp",
                      "round-rock-exterior-street.webp"]
    # …and no image anywhere else under the public tree but the VIN Foundation's own logo.
    elsewhere = sorted(str(f.relative_to(_PUBLIC)) for f in _PUBLIC.rglob("*")
                       if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")
                       and f.parent != _PUBLIC / "assets" / "photos")
    assert elsewhere == ["assets/vin-foundation-logo.png"]


def test_index_html_carries_no_share_image_no_preload_and_no_manifest() -> None:
    """Three ways a photograph reaches a viewer with no request of its own: an `og:image` (which a
    link unfurler fetches server-side, with no session at all), a `<link rel=preload>` and a web
    app manifest's icon list. The approved design asks for none of them, and this is what keeps
    that true — spec F's "social preview" row."""
    head = (_ROOT / "frontend" / "index.html").read_text().lower()
    for forbidden in ("og:image", "twitter:image", "rel=\"preload\"", "rel='preload'",
                      "manifest", "apple-touch-icon", "photos/"):
        assert forbidden not in head, forbidden


def test_nothing_under_app_or_scripts_writes_into_the_public_tree() -> None:
    """The other half of the pin above: the list is only worth pinning if nothing can add to it at
    runtime. No module under `app/` or `scripts/` names that directory at all."""
    named = sorted(str(f.relative_to(_ROOT)) for directory in ("app", "scripts")
                   for f in (_ROOT / directory).rglob("*.py")
                   if "frontend/public" in f.read_text())
    assert named == [], named
