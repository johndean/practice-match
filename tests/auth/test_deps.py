from typing import ClassVar

import httpx
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport

from app.auth import deps
from app.auth import sessions as S
from app.auth.deps import require
from app.config import settings


def _member(conn, roles, state="active"):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'h',%s) RETURNING id", (f"{'-'.join(roles) or 'none'}@x.io", state)); aid = cur.fetchone()[0]
        for r in roles:
            cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,%s,%s)", (aid, r, aid))
    return aid


@pytest.fixture
def app():
    a = FastAPI()
    @a.get("/read", dependencies=[Depends(require("market.read"))])
    async def read(): return {"ok": True}
    @a.post("/decide", dependencies=[Depends(require("users.decide"))])
    async def decide(): return {"ok": True}
    @a.post("/activate", dependencies=[Depends(require("engine.activate"))])
    async def activate(): return {"ok": True}
    return a


@pytest.fixture
async def client(app, conn, redis):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="https://qa.foundation.vin") as c:
        yield c


async def test_anonymous_gets_401_and_applicant_403(client, conn, redis):
    assert (await client.get("/read")).status_code == 401
    aid = _member(conn, [], state="pending"); raw = S.create(conn, redis, aid, None, None)
    r = await client.get("/read", cookies={"pm_session": raw})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


async def test_buyer_reads_but_cannot_decide_and_revocation_is_next_request(client, conn, redis):
    aid = _member(conn, ["buyer"]); raw = S.create(conn, redis, aid, None, None)
    assert (await client.get("/read", cookies={"pm_session": raw})).status_code == 200
    csrf = {"pm_session": raw, "pm_csrf": "t"}; hdr = {"X-CSRF-Token": "t", "Origin": "https://qa.foundation.vin"}
    assert (await client.post("/decide", cookies=csrf, headers=hdr)).status_code == 403
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET state='revoked' WHERE id=%s", (aid,))
    S.invalidate_account(redis, aid)
    assert (await client.get("/read", cookies={"pm_session": raw})).status_code == 403


async def test_state_changes_need_csrf_and_matching_origin(client, conn, redis):
    aid = _member(conn, ["staff"]); raw = S.create(conn, redis, aid, None, None)
    ok = {"pm_session": raw, "pm_csrf": "t"}
    assert (await client.post("/decide", cookies=ok, headers={"X-CSRF-Token": "t", "Origin": "https://qa.foundation.vin"})).status_code == 200
    r = await client.post("/decide", cookies=ok, headers={"X-CSRF-Token": "wrong", "Origin": "https://qa.foundation.vin"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF"
    r = await client.post("/decide", cookies=ok, headers={"X-CSRF-Token": "t", "Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ORIGIN"


async def test_reauth_required_for_destructive_admin_actions(client, conn, redis):
    aid = _member(conn, ["admin"]); raw = S.create(conn, redis, aid, None, None)
    ok = {"pm_session": raw, "pm_csrf": "t"}; hdr = {"X-CSRF-Token": "t", "Origin": "https://qa.foundation.vin"}
    r = await client.post("/activate", cookies=ok, headers=hdr)
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_REQUIRED"
    S.set_reauth(conn, redis, S.resolve(conn, redis, raw))
    assert (await client.post("/activate", cookies=ok, headers=hdr)).status_code == 200


async def test_api_token_and_legacy_operator_token(client, conn, redis, monkeypatch):
    from datetime import timedelta

    from app.auth import tokens as T
    admin = _member(conn, ["admin"])
    raw = T.issue_api_token(conn, name="e2e", role="buyer", created_by=admin, ttl=timedelta(days=1))
    assert (await client.get("/read", headers={"Authorization": f"Bearer {raw}"})).status_code == 200
    assert (await client.post("/decide", headers={"Authorization": f"Bearer {raw}"})).status_code == 403   # buyer token, no CSRF needed
    legacy = {"Authorization": f"Bearer {settings.api_secret_key}"}
    assert (await client.post("/activate", headers=legacy)).status_code == 200                              # legacy operator = admin, exempt from re-auth until I9 deletes it


def test_client_ip_uses_only_the_first_forwarded_hop():
    class R:  # minimal request stand-in
        headers: ClassVar[dict[str, str]] = {"x-forwarded-for": "198.51.100.7, 10.0.0.1"}
        client = type("c", (), {"host": "10.0.0.9"})
    assert deps.client_ip(R()) == "198.51.100.7"
    R.headers = {}
    assert deps.client_ip(R()) == "10.0.0.9"


# --- supplemental (not in the brief's Step 1 — added for 100% branch coverage) ---


def test_client_ip_with_no_header_and_no_client_is_none():
    class R:
        headers: ClassVar[dict[str, str]] = {}
        client = None
    assert deps.client_ip(R()) is None


def test_require_rejects_an_unknown_permission_at_wiring_time():
    with pytest.raises(KeyError):
        require("no.such.permission")


async def test_garbage_session_cookie_resolves_to_anonymous(client, conn, redis):
    """A cookie is present but matches no session (never cached, never in Postgres, or already
    expired) — `S.resolve` returns None, so `current_principal` must fall through to anonymous
    (401) rather than crash or wrongly authenticate (deps.py:65's `if p:` false branch)."""
    r = await client.get("/read", cookies={"pm_session": "not-a-real-session-token"})
    assert r.status_code == 401
