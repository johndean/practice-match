"""Task A9: the admin Data Sources API — `GET /api/admin/data-sources` (staff/admin) and
`POST /api/admin/data-sources/{key}/license` (admin, re-authenticated, audited).

Driven over HTTP against a real database and a real session, exactly as
`tests/api/test_admin_users.py` drives the Users surface: the `member` factory (re-exported into
this directory by `tests/census/conftest.py`) makes a real `account` row with the roles asked for,
`auth_headers` presents its cookies and CSRF double-submit, and the base URL is the site's own
origin because `deps.check_origin_and_csrf` compares an `Origin` header against it on every
cookie-authenticated state change.
"""
from datetime import datetime

import httpx
import pytest
from httpx import ASGITransport

from app.auth import deps
from app.census import gate, license
from app.config import settings
from app.main import create_app
from tests.api.conftest import ORIGIN, PW, auth_headers
from tests.conftest import walk_routes

PATH = "/api/admin/data-sources"


@pytest.fixture
async def client(conn, redis, dist):
    # `conn` first, so `settings.database_url` already points at this test's scratch database when
    # the app is constructed; `dist` (the root fixture's tmp_path skeleton) rather than the real
    # `frontend/dist`, so nothing here depends on whether `npm run build` has been run.
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url=ORIGIN) as c:
        yield c


async def _rows(client, headers):
    r = await client.get(PATH, headers=headers)
    assert r.status_code == 200, r.text
    return {row["dataset_key"]: row for row in r.json()}


async def _admin(client, member):
    """An admin whose password was confirmed a moment ago — what `licence.decide` (in
    `permissions.REAUTH`) requires."""
    account_id, cookies, hdr = member(("admin",))
    headers = auth_headers(cookies, hdr)
    assert (await client.post("/api/auth/reauth", headers=headers, json={"password": PW})).status_code == 200
    return account_id, headers


def _terms(body):
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body["text"])))


# --- the read surface -------------------------------------------------------------------------


async def test_requires_a_credential(client):
    assert (await client.get(PATH)).status_code == 401


async def test_a_member_who_does_not_hold_data_sources_read_is_refused(client, member):
    """`data_sources.read` is staff/admin (`app.auth.permissions`). A buyer is a known principal
    without it, so the answer is the A5 envelope's 403, not the generic 401."""
    _aid, cookies, hdr = member(("buyer",))
    r = await client.get(PATH, headers=auth_headers(cookies, hdr))
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


async def test_lists_registry_with_status_and_active_vintage(client, member):
    _aid, cookies, _hdrs = member(("admin",))
    r = await client.get(PATH, headers=auth_headers(cookies))
    assert r.status_code == 200
    rows = {x["dataset_key"]: x for x in r.json()}
    assert rows["pet_ownership"]["license_status"] == "blocked"
    assert rows["acs5"]["license_status"] == "cleared" and rows["acs5"]["active_vintage"] is None
    assert set(rows["acs5"]) >= {"dataset_key", "display_name", "license_status", "license_name", "vintage",
                                 "refresh_cadence", "last_verified_at", "active_vintage", "drift_flagged",
                                 "last_run", "notes"}


async def test_staff_may_read_it_too_and_the_list_is_ordered_by_key(client, member):
    _aid, cookies, hdr = member(("staff",))
    r = await client.get(PATH, headers=auth_headers(cookies, hdr))
    assert r.status_code == 200
    keys = [row["dataset_key"] for row in r.json()]
    assert keys == sorted(keys) and len(keys) == 17


async def test_every_row_carries_its_attribution_and_agrees_with_the_licence_gate(client, conn, redis, member):
    """Attribution is legally load-bearing (spec §12): the string comes from
    `dataset_registry.attribution_text` and is never composed here or in the browser.

    And the blocked/unresolved rows are LISTED — the admin console's whole job is to show the gate
    — but nothing in the payload marks them usable: the answer `app.census.gate` gives for each row
    is exactly `license_status == 'cleared'`, checked here row by row so the console and the gate
    can never tell an operator two different stories."""
    _aid, cookies, hdr = member(("admin",))
    rows = await _rows(client, auth_headers(cookies, hdr))

    assert rows["acs5"]["attribution_text"] == "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019\u20132023"
    assert {rows[k]["license_status"] for k in ("pet_ownership", "practice_locations")} == {"blocked"}
    assert rows["imagery"]["license_status"] == "unresolved"

    for key, row in rows.items():
        assert row["attribution_text"], f"{key} has no attribution string"
        assert gate.layer_enabled(redis, lambda: conn, key) is (row["license_status"] == "cleared"), key


async def test_last_run_is_the_newest_ingest_run_and_absent_when_there_is_none(client, conn, member):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO ingest_run (dataset_key, vintage, started_at, finished_at, status, rows_written)
                       VALUES ('acs5','2019\u20132023', now(), now(), 'failed', 0),
                              ('acs5','2019\u20132023', now(), now(), 'succeeded', 4200)""")
    _aid, cookies, hdr = member(("admin",))
    rows = await _rows(client, auth_headers(cookies, hdr))
    assert rows["acs5"]["last_run"]["status"] == "succeeded"
    assert rows["acs5"]["last_run"]["rows_written"] == 4200
    assert rows["acs5"]["last_run"]["finished_at"] is not None
    assert rows["cbp"]["last_run"] is None


async def test_the_active_vintage_and_the_operators_note_are_reported(client, conn, member):
    """A-C7 (6) persisted the WHY of an activation in `active_vintage.note`; this is its only
    reader — the Data Sources tab is where a staff member sees which vintage is live and on what
    grounds it was flipped."""
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by, note)
                       VALUES ('acs5','2019\u20132023', now(), 'john', 'QA diff reviewed: 24,318 tracts, ratio 1.00')""")
    _aid, cookies, hdr = member(("admin",))
    rows = await _rows(client, auth_headers(cookies, hdr))
    assert rows["acs5"]["active_vintage"] == "2019\u20132023"
    assert rows["acs5"]["active_vintage_note"] == "QA diff reviewed: 24,318 tracts, ratio 1.00"
    assert rows["cbp"]["active_vintage"] is None and rows["cbp"]["active_vintage_note"] is None


# --- A-C8 (11): "never verified" is null, and drift is its own field -----------------------------


async def test_a_dataset_that_was_never_verified_reads_null_not_a_stale_date(client, conn, member):
    """A-C8 (11) / the A8 review's i3. `last_verified_at` answers "when did a check last SUCCEED",
    and a dataset that has never been checked — or whose only check failed — has no such time. A
    console that filled it in with the attempt's date would tell an operator a licence had been
    verified when nothing was ever read."""
    _aid, cookies, hdr = member(("staff",))
    headers = auth_headers(cookies, hdr)

    rows = await _rows(client, headers)
    assert all(row["last_verified_at"] is None for row in rows.values()), "nothing has been verified yet"

    def refuse(request):
        raise httpx.ConnectError("boom", request=request)

    license.audit(conn, httpx.Client(transport=httpx.MockTransport(refuse)))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM license_audit_log WHERE dataset_key = 'acs5'")
        assert cur.fetchone()[0] == 1, "the failed check IS in the ledger"

    rows = await _rows(client, headers)
    assert rows["acs5"]["last_verified_at"] is None, "a check that failed is not a verification"
    assert rows["acs5"]["drift_flagged"] is False


async def test_drift_survives_a_later_unchanged_sweep_and_only_a_decision_clears_it(client, conn, member):
    """A-C8 (11) / the A8 review's i4. `drift_flagged` and `last_verified_at` move independently:
    the quarterly sweep refreshes the TIME on every check whose hash still matches, so a console
    that inferred "verified" from a recent date would clear a drift nobody has looked at. The flag
    comes down when an admin decides, and at no other moment."""
    _account_id, headers = await _admin(client, member)
    body = {"text": "terms v0"}
    http = _terms(body)

    license.audit(conn, http)                    # baseline hash recorded
    body["text"] = "terms v1"
    license.audit(conn, http)                    # the terms changed: drift

    rows = await _rows(client, headers)
    assert rows["acs5"]["drift_flagged"] is True
    verified_at = rows["acs5"]["last_verified_at"]
    assert verified_at is not None, "the baseline sweep DID verify it once"

    license.audit(conn, http)                    # a later sweep, nothing changed since the drift
    rows = await _rows(client, headers)
    assert datetime.fromisoformat(rows["acs5"]["last_verified_at"]) > datetime.fromisoformat(verified_at)
    assert rows["acs5"]["drift_flagged"] is True, "an unchanged sweep is not a review"

    r = await client.post(f"{PATH}/acs5/license", headers=headers,
                          json={"status": "cleared", "notes": "terms re-read 2026-09-09, no material change"})
    assert r.status_code == 200
    rows = await _rows(client, headers)
    assert rows["acs5"]["drift_flagged"] is False, "the admin decision is what clears it"


# --- the decision -------------------------------------------------------------------------------


async def test_license_decision_updates_registry_and_logs(client, member):
    # `licence.decide` is in `permissions.REAUTH`, so the session needs a password confirmation
    # from the last 10 minutes or the answer is `403 REAUTH_REQUIRED`.
    _account_id, headers = await _admin(client, member)
    r = await client.post(f"{PATH}/imagery/license", headers=headers,
                          json={"status": "cleared", "name": "Esri Imagery — commercial web display",
                                "url": "https://example.test/terms", "notes": "signed 2026-09-05"})
    assert r.status_code == 200 and r.json()["license_status"] == "cleared"
    r2 = await client.post(f"{PATH}/imagery/license", headers=headers, json={"status": "maybe"})
    assert r2.status_code == 422


async def test_the_decision_records_the_operators_url_and_note_in_the_licence_ledger(client, conn, member):
    """`license_audit_log` is the licence LEDGER (distinct from the security audit trail): a human
    decision goes in beside the quarterly machine checks, with `changed = false` — a decision is
    not evidence that the terms moved."""
    _account_id, headers = await _admin(client, member)
    r = await client.post(f"{PATH}/imagery/license", headers=headers,
                          json={"status": "cleared", "name": "Esri Imagery — commercial web display",
                                "url": "https://example.test/terms", "notes": "signed 2026-09-05"})
    assert r.status_code == 200
    with conn.cursor() as cur:
        cur.execute("""SELECT license_status, license_name, license_url, notes, drift_flagged, last_verified_at IS NOT NULL
                         FROM dataset_registry WHERE dataset_key = 'imagery'""")
        assert cur.fetchone() == ("cleared", "Esri Imagery — commercial web display", "https://example.test/terms",
                                  "signed 2026-09-05", False, True)
        cur.execute("SELECT url, content_sha256, http_status, changed FROM license_audit_log WHERE dataset_key = 'imagery'")
        assert cur.fetchall() == [("https://example.test/terms", None, None, False)]


async def test_a_decision_without_a_url_keeps_the_recorded_one_and_says_who_decided(client, conn, member):
    """Every field but `status` is optional and COALESCEs onto what is already there, so an admin
    blocking a source does not have to retype its licence name and URL to do it. The ledger row
    still needs a `url` (the column is NOT NULL), and for a human decision that is what it was."""
    _account_id, headers = await _admin(client, member)
    r = await client.post(f"{PATH}/acs5/license", headers=headers, json={"status": "blocked"})
    assert r.status_code == 200 and r.json() == {"dataset_key": "acs5", "license_status": "blocked"}
    with conn.cursor() as cur:
        cur.execute("SELECT license_status, license_name, license_url FROM dataset_registry WHERE dataset_key = 'acs5'")
        assert cur.fetchone() == ("blocked", "Public domain",
                                  "https://www.census.gov/data/developers/about/terms-of-service.html")
        cur.execute("SELECT url FROM license_audit_log WHERE dataset_key = 'acs5'")
        assert cur.fetchall() == [("operator decision",)]


async def test_the_decision_writes_the_security_audit_row_named_after_its_permission(client, conn, member):
    """A-C0 ¶3. `licence.decide` is in `permissions.AUDITED`, and
    `tests/auth/test_permissions.py` reads the ENDPOINT's own source for `audit.write(` — so the
    row is written here, in this handler, and its action is the permission's own name. It is a
    different record from the `license_audit_log` row above: this one says which named human
    changed the gate, from what, to what."""
    account_id, headers = await _admin(client, member)
    r = await client.post(f"{PATH}/pet_ownership/license", headers=headers,
                          json={"status": "cleared", "notes": "AVMA licence countersigned"})
    assert r.status_code == 200
    with conn.cursor() as cur:
        cur.execute("""SELECT actor_id, actor_role, action, target_type, target_id, before, after, reason
                         FROM audit_log WHERE action = 'licence.decide'""")
        rows = cur.fetchall()
    assert len(rows) == 1
    actor_id, actor_role, action, target_type, target_id, before, after, reason = rows[0]
    assert (actor_id, actor_role, action) == (account_id, "admin", "licence.decide")
    assert (target_type, target_id) == ("dataset_registry", "pet_ownership")
    assert before == {"license_status": "blocked", "drift_flagged": False}
    assert after == {"license_status": "cleared", "drift_flagged": False}
    assert reason == "cleared: AVMA licence countersigned"


async def test_a_decision_invalidates_the_gate_at_once_rather_than_within_the_minute(client, conn, redis, member):
    """Red-team C5 / spec §11's "within 60 s" ceiling, met from the other direction: the decision
    drops the cached answer AND bumps `market:gate:v`, so the layer is gone on the very next read
    instead of on the next TTL expiry — and every market payload cached under the old counter is
    unreachable with it."""
    _account_id, headers = await _admin(client, member)
    assert gate.layer_enabled(redis, lambda: conn, "acs5") is True      # warm the cache
    before = gate.version(redis)

    r = await client.post(f"{PATH}/acs5/license", headers=headers, json={"status": "blocked", "notes": "terms withdrawn"})
    assert r.status_code == 200

    assert gate.layer_enabled(redis, lambda: conn, "acs5") is False
    assert gate.version(redis) == before + 1


async def test_an_unknown_dataset_key_is_a_404_in_the_a5_envelope(client, conn, redis, member):
    """A-C0 ¶4: no bare `HTTPException` — a refusal from this module carries
    `{"error": {"code", "message"}}`, and it changes nothing and invalidates nothing."""
    _account_id, headers = await _admin(client, member)
    before = gate.version(redis)
    r = await client.post(f"{PATH}/no_such_dataset/license", headers=headers, json={"status": "blocked"})
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "NOT_FOUND", "message": "No such data source."}}
    assert gate.version(redis) == before
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log WHERE action = 'licence.decide'")
        assert cur.fetchone()[0] == 0


async def test_a_decision_is_admin_only_and_needs_a_fresh_password(client, conn, member):
    """Two refusals, each with its own code, and neither of them changes the registry: staff hold
    `data_sources.read` but not `licence.decide`, and an admin who has not re-authenticated in the
    last ten minutes is asked to."""
    _aid, scookies, shdr = member(("staff",))
    r = await client.post(f"{PATH}/acs5/license", headers=auth_headers(scookies, shdr), json={"status": "blocked"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"

    _aid2, acookies, ahdr = member(("admin",))
    r2 = await client.post(f"{PATH}/acs5/license", headers=auth_headers(acookies, ahdr), json={"status": "blocked"})
    assert r2.status_code == 403 and r2.json()["error"]["code"] == "REAUTH_REQUIRED"

    with conn.cursor() as cur:
        cur.execute("SELECT license_status FROM dataset_registry WHERE dataset_key = 'acs5'")
        assert cur.fetchone()[0] == "cleared", "neither refusal touched the registry"


# --- wiring -------------------------------------------------------------------------------------


async def test_the_routes_are_guarded_and_mounted_only_in_app_mode(dist, monkeypatch):
    """A-C0 ¶5: both routes sit inside `app/main.py`'s `site_mode == "app"` block, before
    `not_found_router`, and each guard is a module-level constant whose permission
    `deps.permission_of` can read back."""
    mounted = {(method, path): route for method, path, route in walk_routes(create_app(dist=dist).routes)
               if path.startswith(PATH)}
    assert sorted(mounted) == [("GET", PATH), ("POST", PATH + "/{dataset_key}/license")]
    assert [deps.permission_of(d.call) for d in mounted[("GET", PATH)].dependant.dependencies] == ["data_sources.read"]
    assert sorted(p for d in mounted[("POST", PATH + "/{dataset_key}/license")].dependant.dependencies
                  if (p := deps.permission_of(d.call))) == ["data_sources.read", "licence.decide"]

    monkeypatch.setattr(settings, "site_mode", "coming_soon")
    coming = create_app(dist=dist)
    assert [p for _m, p, _r in walk_routes(coming.routes) if p.startswith(PATH)] == []
    async with httpx.AsyncClient(transport=ASGITransport(app=coming), base_url=ORIGIN) as c:
        r = await c.get(PATH)
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
        assert r.json()["ok"] is False, "the catch-all's body, not this module's"
