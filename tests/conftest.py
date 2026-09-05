import os

os.environ.setdefault("DATABASE_URL", "postgresql://pm:pm_dev_pw@localhost:5433/practice_match")
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("API_SECRET_KEY", "test_only_secret_change_me")

# Env defaults above must precede any app.* import (E402 no longer enforced by ruff's
# config here, but the ordering itself still matters — see the module docstring intent).
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    d = tmp_path / "dist"
    (d / "_app").mkdir(parents=True)
    (d / "assets" / "icons").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><div id=\"app\"></div>")
    (d / "_app" / "index-abc123.js").write_text("console.log(1)")
    (d / "assets" / "icons" / "pad-lock.svg").write_text("<svg/>")
    return d


@pytest.fixture
def coming_dist(tmp_path: Path) -> Path:
    d = tmp_path / "coming-soon-dist"
    (d / "_app").mkdir(parents=True)
    (d / "ds").mkdir()
    (d / "index.html").write_text('<!doctype html><title>VIN Foundation — Coming Soon</title><div id="app"></div>')
    (d / "_app" / "index-cs1.js").write_text("console.log(2)")
    (d / "ds" / "colors_and_type.css").write_text(":root{}")
    return d


@pytest.fixture
async def client(dist):
    from app.main import create_app  # imported here so this conftest loads before app.main exists (Steps 2-3)

    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url="http://test") as c:
        yield c


import psycopg2


@pytest.fixture(scope="session")
def db_ready():
    """Fails loudly (never skips) when the local services are down."""
    try:
        psycopg2.connect(os.environ["DATABASE_URL"]).close()
    except psycopg2.Error as exc:  # pragma: no cover
        pytest.fail(f"Postgres not reachable at {os.environ['DATABASE_URL']}: {exc}\n"
                    "Start it: docker compose -f docker-compose.dev.yml up -d")
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("migrate", Path(__file__).resolve().parent.parent / "scripts" / "migrate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    mod.run(os.environ["DATABASE_URL"])


@pytest.fixture(autouse=True)
async def _dispose_pools():
    """Disposes app.db's pooled engine/redis-client cache for the current test's
    event loop before that loop closes at teardown (round 4: production code no
    longer monkeypatches loop.close to do this — see app/db.py)."""
    yield
    from app.db import dispose_all  # imported lazily, as `client` does

    await dispose_all()
