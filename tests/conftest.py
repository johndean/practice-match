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


@pytest.fixture(scope="session", autouse=True)
def _no_stray_network():
    """No test in the whole suite may open a real socket to anything but this machine (A-SL18 (5),
    review Info-4).

    `_intercepted_by_moto` below (this file's own since Task P2 Step 0) guards the `store`
    fixture's OWN endpoint alone — it says nothing about a test that repoints `settings.s3_*` after
    `store` yields, or builds an `ObjectStore` directly, so it stays (it also asserts something this guard
    cannot: that the CONFIGURED endpoint string looks like an AWS host, independent of whether any
    request is ever made). This fixture is the suite-wide backstop the review's Info-4 asked for:
    session-scoped and autouse, so every test is covered without asking for it by name.

    Patching `socket.socket.connect` is safe to do UNCONDITIONALLY rather than only while a `store`
    fixture is active, because nothing in this suite needs a real non-local connection: moto mocks
    botocore's own `before-send` event (`moto.core.botocore_stubber.BotocoreStubber`), which answers
    the request before botocore ever asks urllib3 for a socket — proved by the `store` fixture's own
    tests passing under this guard — Postgres goes through libpq's C sockets, never Python's
    `socket` module, and every test that touches Redis for real reaches it at `localhost`/
    `127.0.0.1`, while the rate-limit and cache tests that care about the DISTINCTION between a
    local and a non-local Redis URL (`tests/test_reset_rate_limits.py`) test a pure string parser,
    never an actual connection. Loopback stays open for exactly those real, local connections."""
    import socket

    allowed_hosts = {"127.0.0.1", "::1", "localhost"}
    original_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: object) -> object:
        host = address[0] if isinstance(address, tuple) else address
        if host not in allowed_hosts:
            raise AssertionError(f"test suite attempted a real network connection to {address!r}")
        return original_connect(self, address)

    patch = pytest.MonkeyPatch()
    patch.setattr(socket.socket, "connect", guarded_connect)
    yield
    patch.undo()


import boto3
from moto import mock_aws

from app.config import settings as _settings
from app.storage import ObjectStore

#: The fake bucket every suite in this repository shares (Task P2 Step 0). Moved here VERBATIM
#: from `tests/api/test_listing_assets.py`, which owned it alone until the image-identifiability
#: pipeline gave `tests/tasks/`, `tests/media/` and `tests/privacy/` a bucket of their own to need.
BUCKET = "pm-test"
ENDPOINT = "https://s3.amazonaws.com"


def _intercepted_by_moto(endpoint: str) -> bool:
    """Whether moto 5 will intercept a request to `endpoint`, asserting rather than reporting.

    A-SL16 M4: moto matches the request URL, so a bucket endpoint from the fleet ESCAPES `mock_aws`
    and makes a real HTTPS call — which is what happened the first time this fixture was written.
    The credentials are dummies, so such a call would fail rather than reach a real bucket; a test
    suite that can talk to the internet is still not a test suite."""
    assert endpoint.endswith(".amazonaws.com"), (
        f"{endpoint} escapes moto's interceptor; the fake bucket must be an AWS-shaped host")
    return True


@pytest.fixture
def store(monkeypatch):
    """A moto bucket, reached through the real `ObjectStore.from_settings`."""
    _intercepted_by_moto(ENDPOINT)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        for name, value in (("s3_endpoint_url", ENDPOINT), ("s3_bucket", BUCKET),
                            ("s3_access_key_id", "AKIA"), ("s3_secret_access_key", "secret")):
            monkeypatch.setattr(_settings, name, value)
        _intercepted_by_moto(str(_settings.s3_endpoint_url))
        yield ObjectStore.from_settings(_settings)


@pytest.fixture(autouse=True)
def published_tasks(monkeypatch):
    """Every Celery message the suite publishes, recorded instead of sent — and the list, so a test
    can assert on it by asking for this fixture by name.

    Task P2 made `celery_app.send_task` UNCONDITIONAL on the photograph upload path (one
    `media.process_photo` per upload, after the commit), where the three publishes that existed
    before it were all conditional and reached by a handful of tests that each patched `send_task`
    themselves. Without this, some thirty upload tests would publish to a REAL broker — celery's
    redis transport spends twenty seconds retrying when none is listening, and when one IS
    listening the suite quietly fills a queue nothing drains. `_no_stray_network` above cannot see
    it: the broker is `localhost`, which that guard allows on purpose.

    A recorder rather than a refusal: a publish is legitimate behaviour and several tests assert it
    happens. A test that wants to observe one patches `send_task` itself, as this suite already
    does in five places, and its own patch wins for the length of that test."""
    from app.tasks.celery_app import celery_app

    published: list[tuple[str, object]] = []
    monkeypatch.setattr(celery_app, "send_task",
                        lambda name, args=None, **kwargs: published.append((name, args)))
    return published


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
import warnings

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


def _clone_database(admin, name: str, template: str) -> bool:
    """`CREATE DATABASE <name> TEMPLATE <template>` on an autocommit maintenance connection.
    Returns True when the copy happened.

    Postgres refuses to copy a database any session is connected to ("source database ... is
    being accessed by other users"). Nothing in this suite holds one — `template_dsn` lets
    `migrate.run` close its connection before it yields — but another process on the shared
    compose Postgres, or a test that opens one deliberately, can make it happen, and that is
    not worth failing a run over. The fallback is exactly the pre-template path: create the
    database empty and let the caller's `migrate.run` apply the whole ladder, slower but
    identical in outcome. Returns False so the caller (and the test that provokes it) can tell
    the two apart.

    The notice is a real `warnings.warn` under an explicit `always` filter: the suite runs
    `-W error`, which would otherwise turn the slow-but-correct fallback into the failure it
    exists to avoid, while pytest's own recorder still logs it into the warnings summary."""
    with admin.cursor() as cur:
        try:
            cur.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
            return True
        except psycopg2.Error as exc:
            if "being accessed by other users" not in str(exc):
                raise
            refusal = " ".join(str(exc).split())
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.warn(f"{refusal} — {name} falls back to create-then-migrate", stacklevel=2)
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    return False


@pytest.fixture(scope="session")
def template_dsn(db_ready):
    """The one already-migrated database every `scratch_dsn` is cloned from (platform task
    P-TDB, the A-C0 ¶9 remedy). Yields its NAME, because `CREATE DATABASE ... TEMPLATE` names
    a database rather than taking a DSN.

    Running the whole migration ladder into a fresh database per test — `CREATE EXTENSION
    postgis` included — was the backend gate's wall-clock bottleneck. It runs ONCE here
    instead, and each test gets a copy.

    Depends on `db_ready` so the existing session setup (the "is Postgres up" probe and the
    shared dev database's own migration) still happens first and in the same order. Holds no
    connection to the template while it lives: `migrate.run` opens and closes its own, and the
    admin connection kept here is to the maintenance database — a template with a session
    attached cannot be copied at all (see `_clone_database`)."""
    from app.config import settings
    from scripts import migrate

    name = f"pm_tmpl_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(_maintenance(migrate, settings.database_url))
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{name}"')
        try:
            migrate.run(_normalized_base(migrate, settings.database_url) + f"/{name}")
            yield name
        finally:
            with admin.cursor() as cur:
                cur.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    finally:
        admin.close()


@pytest.fixture
def scratch_dsn(template_dsn):
    """Fresh database with every migration applied; dropped afterwards. Loads
    scripts/migrate.py via a normal `import scripts.migrate` (scripts/ is a namespace
    package, no __init__.py needed) rather than a fresh throwaway module object per
    call, so a test can reach the exact `run` function this fixture calls through, by
    patching `scripts.migrate.run` directly (I5 fix round 1's failure-injection test
    does this).

    P-TDB: the database is a COPY of `template_dsn` rather than an empty database the whole
    ladder is applied to — same end state, schema and ledger rows alike, at a fraction of the
    cost. `migrate.run` still runs against it, deliberately: on a copy it applies nothing and
    re-runs `refuse_changed_files`, so a tree that disagrees with the migrations already in the
    template is still refused per test, and the failure-injection test above still has the seam
    it patches."""
    from app.config import settings
    from scripts import migrate

    name = f"pm_test_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(_maintenance(migrate, settings.database_url))
    admin.autocommit = True
    try:
        _clone_database(admin, name, template_dsn)
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


def walk_routes(routes, prefix=""):
    """(method, path, route) for everything mounted on an app, spelled the way
    `permissions.PUBLIC_ROUTES` spells it — the raw path template (`/{path:path}`), not the compiled
    `path_format` (`/{path}`).

    FastAPI 0.141 keeps an included router as a WRAPPER object rather than flattening its routes
    into `app.routes`, so a plain `{r.path for r in app.routes}` sees `/robots.txt`, `/`, the
    `/_app` mount and the SPA catch-all — and no `/api/*` path at all. The walk recurses through
    `original_router` and carries the include prefix, which is the only way to see them.

    A `Mount` is recursed into when the mounted app exposes routes of its own (I3 fix round 2
    observation): `Mount.routes` is `getattr(self.app, "routes", [])`, so a StaticFiles mount
    yields nothing and falls through to the GET-only line — while a mounted sub-application's
    write routes are SEEN by the route-guard test instead of being invisible to it.

    Lives here rather than inside `tests/auth/test_permissions.py` (I9a review, Minor 4): it has two
    consumers now — that file's route-guard and audit drift tests, and
    `tests/test_docs.py::test_identity_runbook_endpoints_exist` — and a helper reached through
    another test module's namespace makes a reorganisation of `tests/auth/` break an unrelated docs
    test. Not a fixture: it is a plain generator, called at module level in places."""
    from starlette.routing import Mount

    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from walk_routes(included.routes, prefix + route.include_context.prefix)
        elif isinstance(route, Mount):
            if route.routes:
                yield from walk_routes(route.routes, prefix + route.path)
            else:
                yield "GET", prefix + route.path + "/{path:path}", None
        else:
            for method in sorted(route.methods):
                yield method, prefix + route.path, route
