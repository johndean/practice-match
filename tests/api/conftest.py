"""Fixtures for the API-level tests (Task I4). `client` SHADOWS the root conftest's `client` for
`tests/api/*` only: it speaks to the app over the site's real origin (`https://qa.foundation.vin`),
which is what `app.auth.deps.check_origin_and_csrf` compares an `Origin` header against.

It deliberately does NOT depend on `conn`: `tests/api/test_interest.py` asks for `client` in 58 of its
60 tests, and `conn` (via `scratch_dsn`) clones, checks and drops a database per test (P-TDB — it
created and fully migrated one, at ~2 s each, until the session template landed), so shadowing with
a `conn`-bound fixture would still add a database per test to a 3.5 s file for no benefit. Tests
that need a scratch database ask for `conn` (or `member`, which does) themselves.
"""
import io
import sys
from dataclasses import dataclass
from datetime import timedelta

import httpx
import pytest
from httpx import ASGITransport
from PIL import Image

from app import db
from app.auth import passwords as P
from app.auth import sessions as S
from app.auth import tokens as T
from app.census import ingest
from app.config import settings
from app.main import create_app

ORIGIN = "https://qa.foundation.vin"
PW = "orbit-lantern-quiet-42"


def auth_headers(cookies, headers=None):
    """`cookies` as a literal `Cookie` request header, merged with `headers`.

    Not httpx's per-request `cookies=` argument: httpx 0.28 emits a DeprecationWarning for it
    ("the expected behaviour on cookie persistence is ambiguous"), which the suite's `-W error`
    gate turns into a failure. A literal header is also what these tests actually mean — it
    bypasses the client's cookie jar, so a session cookie the app has just CLEARED is still
    presented on the next request, which is the whole point of
    `test_signout_all_revokes_on_next_request` (the 401 must come from the revoked session, not
    from an absent cookie).
    """
    return {**(headers or {}), "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}


def padded_json(total: int, minimal: bytes) -> bytes:
    """`minimal` (a JSON object literal ending in `}`) padded with spaces before the closing brace
    to reach exactly `total` bytes. JSON tolerates whitespace between tokens, so the padding never
    changes what `json.loads` sees — only the byte count a bounded reader counts on the wire
    (A-SL18 (3), the exact `MAX_JSON_BYTES` boundary)."""
    assert minimal.endswith(b"}"), minimal
    pad = total - len(minimal)
    assert pad >= 0, f"{minimal!r} is already {len(minimal)} bytes, more than {total}"
    return minimal[:-1] + b" " * pad + b"}"


@pytest.fixture(autouse=True)
def _no_database_without_the_conn_fixture(request, monkeypatch):
    """A test that takes `client` but not `conn` must never open a synchronous connection: without
    `conn` the app is still pointed at the shared dev database (Minor 11). Every module that
    imported `sync_conn` by name is patched, found by identity rather than by a hand-kept list, so
    a new consumer cannot slip past this."""
    if "client" not in request.fixturenames or "conn" in request.fixturenames:
        return

    def _refuse():
        raise RuntimeError("test used the database without the conn fixture")

    original = db.sync_conn
    for module in list(sys.modules.values()):
        if getattr(module, "sync_conn", None) is original:
            monkeypatch.setattr(module, "sync_conn", _refuse)


@pytest.fixture
async def client(dist, redis, monkeypatch):
    # `dist` (the root fixture's tmp_path skeleton), not the real `frontend/dist`: the fixture every
    # later task reuses must not depend on whether `npm run build` has been run (Minor 10).
    #
    # The suite makes no network calls: with the HIBP screen off, `passwords.is_pwned` falls back to
    # the bundled offline list, which is a real screen (tests/api/test_auth.py exercises a hit on it).
    monkeypatch.setattr(settings, "hibp_enabled", False)
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url=ORIGIN) as c:
        yield c


@pytest.fixture
def member(conn, redis):
    def make(roles=("buyer",), state="active", email=None, affiliation=None):
        email = email or f"{'-'.join(roles) or 'none'}-{state}@example.org"
        with conn.cursor() as cur:
            cur.execute("INSERT INTO account (email, password_hash, state, display_name, affiliation_label) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                        (email, P.hash_password(PW), state, "Dr. Rachel Mendes", affiliation)); aid = cur.fetchone()[0]
            for r in roles:
                cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,%s,%s)", (aid, r, aid))
        raw = S.create(conn, redis, aid, "203.0.113.5", "pytest")
        return aid, {"pm_session": raw, "pm_csrf": "csrf-1"}, {"X-CSRF-Token": "csrf-1", "Origin": ORIGIN}
    return make


@pytest.fixture
def seller(member):
    """A signed-in seller's request headers: the Cookie header plus the CSRF pair, ready to pass as
    `headers=seller`. Three personas rather than one `member(...)` call per test, because every
    suite from Task P2 on needs the same three and a per-test call would mint a new account (and a
    new rate-limit bucket) each time.

    `roles=("seller",)`, not `("buyer", "seller")` — ruling D-C59 (2026-09-20) makes that pair
    impossible to grant one account (`migrations/100_role_exclusivity.sql`'s trigger refuses it),
    and no consumer of this fixture ever exercised the buyer half: every one of them is testing
    SELLER-side behaviour (listing ownership, photo delivery, admin review), never a buyer act."""
    _account_id, cookies, headers = member(roles=("seller",), email="idp-seller@example.org")
    return auth_headers(cookies, headers)


@pytest.fixture
def buyer(member):
    _account_id, cookies, headers = member(roles=("buyer",), email="idp-buyer@example.org")
    return auth_headers(cookies, headers)


@pytest.fixture
def admin(member):
    _account_id, cookies, headers = member(roles=("buyer", "admin"), email="idp-admin@example.org")
    return auth_headers(cookies, headers)


def _jpeg_bytes(width: int = 240, height: int = 180) -> bytes:
    """`test_listing_assets.py::_jpeg`'s bytes, reachable from every suite. Deterministic: the
    upload tests compare `store.get(original)` to this value byte for byte."""
    image = Image.new("RGB", (width, height), (120, 30, 30))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


def _png_bytes(width: int = 240, height: int = 180) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (30, 120, 30)).save(buffer, "PNG")
    return buffer.getvalue()


async def _draft(client, headers) -> str:
    """A fresh draft listing, as `test_listing_assets.py::_create` makes one."""
    response = await client.post("/api/seller/listings", headers=headers)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


# --- Task 1 of the admin control surface (A41): the per-role clients an admin API test drives ----
#
# `tests/api/test_admin_users.py` and `tests/census/test_admin_api.py` build these inline, one
# `member(...)` + `auth_headers(...)` pair per test; `tests/api/test_admin_settings.py` drives EIGHT
# distinct principals over two routes, so the pair is hoisted into a fixture per principal and the
# credential is baked in as the client's DEFAULT HEADERS. Every one of them speaks to ONE app over
# the site's real origin, which is what `deps.check_origin_and_csrf` compares an `Origin` header
# against on every cookie-authenticated state change.


@pytest.fixture
async def api_client(conn, redis, dist):
    """Factory: an httpx client over ONE ASGI app, with `headers` as its defaults.

    `conn` first, so `settings.database_url` already names this test's scratch database when the
    app is constructed (`tests/census/test_admin_api.py`'s own rule); `dist` (the root fixture's
    tmp_path skeleton) rather than the real `frontend/dist`, so nothing here depends on whether
    `npm run build` has been run. Every client the factory hands out is closed at teardown."""
    app = create_app(dist=dist)
    opened: list[httpx.AsyncClient] = []

    def make(headers: dict[str, str]) -> httpx.AsyncClient:
        c = httpx.AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN, headers=headers)
        opened.append(c)
        return c

    yield make
    for c in opened:
        await c.aclose()


async def signed_in(api_client, member, roles, *, reauth=False, email=None):
    """A client carrying a real account's session cookie and CSRF double-submit — and, when
    `reauth`, a password confirmed a moment ago, which is what every `permissions.REAUTH` action
    requires."""
    _aid, cookies, hdr = member(roles, email=email)
    client = api_client(auth_headers(cookies, hdr))
    if reauth:
        r = await client.post("/api/auth/reauth", json={"password": PW})
        assert r.status_code == 200, r.text
    return client


@pytest.fixture
async def staff_client(api_client, member):
    return await signed_in(api_client, member, ("staff",), email="staff@example.org")


@pytest.fixture
async def staff_reauthed_client(api_client, member):
    return await signed_in(api_client, member, ("staff",), reauth=True, email="staff-fresh@example.org")


@pytest.fixture
async def buyer_client(api_client, member):
    return await signed_in(api_client, member, ("buyer",), email="buyer@example.org")


@pytest.fixture
async def admin_client(api_client, member):
    """An admin whose password was NOT confirmed recently — everything but the `REAUTH` six."""
    return await signed_in(api_client, member, ("admin",), email="admin@example.org")


@pytest.fixture
async def admin_reauthed_client(api_client, member):
    return await signed_in(api_client, member, ("admin",), reauth=True, email="admin-fresh@example.org")


@pytest.fixture
async def admin_token_client(api_client, conn, member):
    """An `api_token` carrying `admin`. It can never satisfy a re-auth gate (`deps.TokenCannotReauth`),
    which is the containment that lets a standing admin bearer exist at all."""
    account_id, _cookies, _hdr = member(("admin",), email="token-minter@example.org")
    issued = T.issue_api_token(conn, name="a41-settings", role="admin", created_by=account_id, ttl=timedelta(days=1))
    return api_client({"Authorization": f"Bearer {issued.raw}"})


@pytest.fixture
async def legacy_client(api_client):
    """The legacy operator bearer (`API_SECRET_KEY`). `deps.require` exempts it from the re-auth
    window and its principal (`deps.LEGACY_ADMIN`) names no `account` row at all."""
    return api_client({"Authorization": f"Bearer {settings.api_secret_key}"})


@pytest.fixture
def audit_rows(conn):
    """Every `audit_log` row as a dict, oldest first. `audit_log`'s triggers refuse UPDATE and
    DELETE, so a test never has to clean up after itself — the scratch database is dropped."""
    def read() -> list[dict[str, object]]:
        with conn.cursor() as cur:
            cur.execute("SELECT action, actor_id::text, actor_role, target_type, target_id, before, after, reason FROM audit_log ORDER BY id")
            names = [d[0] for d in cur.description]
            return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]
    return read


# --- the registry states the Settings row's "Activate <vintage>" button exists for ---------------


@dataclass(frozen=True)
class RegistryState:
    dataset_key: str
    active: str | None
    loaded: str | None


def _seed_vintage(conn, dataset_key: str, vint: str, status: str, rows: int = 10) -> None:
    """One `ingest_run` at `status` with `finished_at = now()`, and — on a run that SUCCEEDED — the
    measure rows `vintage._count` counts.

    `ingest.start`/`ingest.finish` rather than the `ingest.run` context manager: that manager
    signals a failed load by RE-RAISING out of its own `except`, so seeding a failed run through it
    means raising and catching a sentinel in a fixture. A failed run writes no measure rows, which
    is what its rollback does for real."""
    run_id = ingest.start(conn, dataset_key, vint)
    if status == "succeeded":
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO acs_measure VALUES (%s,'140',%s,'B01003_001E',1,0,%s)",
                            [(f"g{i}", vint, run_id) for i in range(rows)])
    ingest.finish(conn, run_id, status, rows=rows if status == "succeeded" else 0)


def _seed_registry(conn, dataset_key: str, *, active: str, loaded: str, status: str) -> RegistryState:
    """`dataset_key` active on `active`, with a load of `loaded` at `status`.

    The registry row itself is already there — `migrations/017_census_registry.sql` seeds all
    seventeen datasets, `acs5` among them — so this writes the two things that vary: the runs and
    the `active_vintage` row. Row counts are seeded EQUAL, so `vintage.qa`'s `[0.8, 1.25]` ratio
    gate passes without `force`."""
    _seed_vintage(conn, dataset_key, active, "succeeded")
    if loaded != active:
        _seed_vintage(conn, dataset_key, loaded, status)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s,%s,now(),%s)
                       ON CONFLICT (dataset_key) DO UPDATE SET vintage = EXCLUDED.vintage, activated_at = now()""",
                    (dataset_key, active, "seed@example.org"))
    return RegistryState(dataset_key, active, loaded)


@pytest.fixture
def registry_with_a_newer_load(conn) -> RegistryState:
    """`acs5` active on one vintage with a SUCCEEDED load of a newer one — the state the Settings
    row's "Activate <vintage>" button exists for."""
    return _seed_registry(conn, "acs5", active="2018\u20132022", loaded="2019\u20132023", status="succeeded")


@pytest.fixture
def registry_already_active(conn) -> RegistryState:
    return _seed_registry(conn, "acs5", active="2019\u20132023", loaded="2019\u20132023", status="succeeded")


@pytest.fixture
def registry_with_a_failed_load(conn) -> RegistryState:
    return _seed_registry(conn, "acs5", active="2018\u20132022", loaded="2019\u20132023", status="failed")


@pytest.fixture
def registry_active_with_no_load(conn) -> RegistryState:
    """A dataset whose `active_vintage` row names a vintage no SUCCEEDED `ingest_run` carries.

    Reachable for real — `scripts/census_load.py activate` writes `active_vintage` and nothing ever
    deletes that row, so a dataset activated before its runs were pruned (or whose only later run
    failed) sits here — and it is the one state in which `activatable`'s `loaded is not None` term
    does any work: without it the row would read `None != "2022"` and offer an Activate button for
    a vintage that has never finished loading. `cbp` rather than `acs5` because the three ACS keys
    share `acs_measure` and this fixture is about a dataset with NO runs at all."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s,%s,now(),%s)",
                    ("cbp", "2022", "seed@example.org"))
    return RegistryState("cbp", "2022", None)


@pytest.fixture
def two_signups_one_mailed(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version, source)"
                    " VALUES ('a@example.org','a@example.org','coming-soon-v1','coming-soon'),"
                    "        ('b@example.org','b@example.org','coming-soon-v1','coming-soon')")
        cur.execute("UPDATE interest_signup SET launch_mailed_at = now() WHERE email_normalised = 'a@example.org'")
