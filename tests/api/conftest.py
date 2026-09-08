"""Fixtures for the API-level tests (Task I4). `client` SHADOWS the root conftest's `client` for
`tests/api/*` only: it speaks to the app over the site's real origin (`https://qa.foundation.vin`),
which is what `app.auth.deps.check_origin_and_csrf` compares an `Origin` header against.

It deliberately does NOT depend on `conn`: `tests/api/test_interest.py` asks for `client` in 58 of its
60 tests, and `conn` (via `scratch_dsn`) clones, checks and drops a database per test (P-TDB — it
created and fully migrated one, at ~2 s each, until the session template landed), so shadowing with
a `conn`-bound fixture would still add a database per test to a 3.5 s file for no benefit. Tests
that need a scratch database ask for `conn` (or `member`, which does) themselves.
"""
import sys

import httpx
import pytest
from httpx import ASGITransport

from app import db
from app.auth import passwords as P
from app.auth import sessions as S
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
