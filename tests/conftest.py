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

# Imported at module level, before any test runs: app.db calls psycopg2.extras.register_uuid()
# at import (Task I2 ruling), and the `conn` fixture below connects with psycopg2 directly, so
# without this the FIRST test of a fresh process reads uuid columns as str. The registration is
# global and applies at fetch time, so this one import covers every direct psycopg2.connect() in
# the suite. `_dispose_pools` uses the same module for dispose_all().
import app.db


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
    (d / "assets").mkdir()
    (d / "index.html").write_text('<!doctype html><title>VIN Foundation — Coming Soon</title><div id="app"></div>')
    (d / "_app" / "index-cs1.js").write_text("console.log(2)")
    (d / "ds" / "colors_and_type.css").write_text(":root{}")
    (d / "assets" / "vin-foundation-logo.png").write_bytes(b"\x89PNG")
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
    await app.db.dispose_all()


import uuid

import fakeredis


def _normalized_base(migrate, dsn: str) -> str:
    """The DSN's scheme/dialect normalised through `migrate.normalize_dsn()` (as
    `db.sync_conn()` also does), with any query string stripped, then split down to
    everything before the database name — M9, fix round 1: a raw `rsplit` on an
    asyncpg-style or query-stringed DSN breaks outright or bakes the query string
    into a database name."""
    return migrate.normalize_dsn(dsn).split("?", 1)[0].rsplit("/", 1)[0]


def _maintenance(migrate, dsn: str) -> str:
    return _normalized_base(migrate, dsn) + "/postgres"


@pytest.fixture
def scratch_dsn():
    """Fresh database with every migration applied; dropped afterwards. Loads
    scripts/migrate.py via a normal `import scripts.migrate` (scripts/ is a namespace
    package, no __init__.py needed) rather than a fresh throwaway module object per
    call, so a test can reach the exact `run` function this fixture calls through, by
    patching `scripts.migrate.run` directly (I5 fix round 1's failure-injection test
    does this)."""
    from app.config import settings
    from scripts import migrate

    name = f"pm_test_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(_maintenance(migrate, settings.database_url))
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{name}"')
        dsn = _normalized_base(migrate, settings.database_url) + f"/{name}"
        try:
            # I5, fix round 1: migrate.run must run INSIDE this try — previously it ran
            # before the try/finally, so a failing migration left the just-created
            # database (and this admin connection) leaked on the shared compose Postgres.
            migrate.run(dsn)
            yield dsn
        finally:
            with admin.cursor() as cur:
                cur.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    finally:
        admin.close()


@pytest.fixture
def conn(scratch_dsn, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "database_url", scratch_dsn)
    c = psycopg2.connect(scratch_dsn)
    c.autocommit = True
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def redis(monkeypatch):
    server = fakeredis.FakeServer()
    sync = fakeredis.FakeRedis(server=server)
    aio = fakeredis.aioredis.FakeRedis(server=server)
    from app import cache

    # Patch the factories, not sync_redis/async_redis themselves (fix round 1, C1):
    # a `from app.cache import sync_redis` consumer binds the function object once,
    # but that function still resolves `_make_sync`/`_make_async` from `app.cache`'s
    # own globals on every call, so patching those two intercepts every caller.
    monkeypatch.setattr(cache, "_make_sync", lambda: sync)
    monkeypatch.setattr(cache, "_make_async", lambda: aio)
    # `sync_redis()` memoises one client per process (I3 fix round 1, C3): reset on both sides of
    # the yield so an earlier test's client cannot shadow this fake, and this fake cannot outlive
    # the test that asked for it.
    cache.reset()
    yield sync
    cache.reset()
