"""GET /api/admin/settings and POST /api/admin/vintages/{key}/activate (spec §2, decisions D1-D3).

Driven over HTTP against a real database and a real session, the posture
`tests/api/test_admin_users.py` and `tests/census/test_admin_api.py` share — one client fixture per
principal (`tests/api/conftest.py`), because these two routes are reached by eight distinct ones.
"""
from __future__ import annotations

import pytest

from app.auth import permissions as PM
from app.config import settings


def active_vintage_by(conn, dataset_key: str) -> str:
    """`active_vintage.activated_by` for one dataset. The column is `NOT NULL` and the activation
    answer does not carry it, so the two callers below read the row the route actually wrote."""
    with conn.cursor() as cur:
        cur.execute("SELECT activated_by FROM active_vintage WHERE dataset_key = %s", (dataset_key,))
        return cur.fetchone()[0]


async def test_the_settings_read_reports_the_flag_as_read_only_and_names_where_it_is_set(staff_client):
    body = (await staff_client.get("/api/admin/settings")).json()
    assert body["market_data_public"]["writable"] is False
    assert body["market_data_public"]["set_in"] == "Railway environment variable MARKET_DATA_PUBLIC"
    assert isinstance(body["market_data_public"]["value"], bool)
    # The row names the ENVIRONMENT the flag is set in, read off the app's own config rather than
    # typed: the field is the one thing on this row that varies between QA and production, and a
    # neighbouring setting served here by mistake would read as an environment name to the tab.
    assert body["market_data_public"]["environment"] == settings.environment


async def test_the_settings_read_reports_every_registered_dataset_s_vintage(staff_client, registry_with_a_newer_load):
    rows = {v["dataset_key"]: v for v in (await staff_client.get("/api/admin/settings")).json()["vintages"]}
    row = rows[registry_with_a_newer_load.dataset_key]
    assert row["active_vintage"] == registry_with_a_newer_load.active
    assert row["loaded_vintage"] == registry_with_a_newer_load.loaded
    assert row["activatable"] is True


async def test_a_dataset_whose_newest_succeeded_load_is_already_active_is_not_activatable(staff_client, registry_already_active):
    rows = {v["dataset_key"]: v for v in (await staff_client.get("/api/admin/settings")).json()["vintages"]}
    assert rows[registry_already_active.dataset_key]["activatable"] is False


async def test_a_dataset_with_an_active_vintage_and_no_succeeded_load_is_not_activatable(staff_client, registry_active_with_no_load):
    """`activatable`'s own `loaded is not None` term, and `_iso(None)`.

    Without the term the row reads `None != "2022"` and the tab draws an Activate button for a
    vintage nothing has ever finished loading; without `_iso`'s null arm the two absent timestamps
    come back as something other than JSON null. Neither is caught by the three fixtures above,
    every one of which seeds a succeeded run — proved by mutation, not assumed (report §RED-2)."""
    row = {v["dataset_key"]: v for v in (await staff_client.get("/api/admin/settings")).json()["vintages"]}[
        registry_active_with_no_load.dataset_key]
    assert row["active_vintage"] == registry_active_with_no_load.active
    assert row["loaded_vintage"] is None and row["last_load_finished_at"] is None
    assert row["activatable"] is False


async def test_the_settings_read_reports_the_sign_up_counts_and_the_last_send(staff_client, two_signups_one_mailed):
    signups = (await staff_client.get("/api/admin/settings")).json()["signups"]
    assert (signups["total"], signups["launch_mailed"], signups["not_mailed"]) == (2, 1, 1)
    assert signups["last_mailed_at"] is not None
    # `sendable` is `SITE_MODE == "app"`, and this router is MOUNTED only in that mode
    # (`app/main.py`), so on any reachable route it can be nothing else. Pinned as the constant it
    # structurally is rather than left as an unread key; the honest limit is recorded in the task
    # report rather than dressed up as a tested branch.
    assert signups["sendable"] is True


async def test_a_buyer_cannot_read_the_settings(buyer_client):
    assert (await buyer_client.get("/api/admin/settings")).status_code == 403


def test_the_three_permissions_the_aggregate_read_serves_have_the_same_holders():
    """Decision D3. `GET /api/admin/settings` is guarded by `data_sources.read` alone and serves
    facts that belong to `signups.read` and to the screen's own `page.admin`. Today all three are
    staff|admin. The day one of them moves, this fails — rather than one row's facts leaking to
    the holder of another row's permission."""
    assert PM.MATRIX["data_sources.read"] == PM.MATRIX["signups.read"] == PM.MATRIX["page.admin"]


async def test_activating_a_vintage_writes_active_vintage_and_one_audit_row(admin_reauthed_client, registry_with_a_newer_load, audit_rows, conn):
    r = await admin_reauthed_client.post(
        f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
        json={"vintage": registry_with_a_newer_load.loaded},
    )
    assert r.status_code == 200, r.text
    assert r.json()["vintage"] == registry_with_a_newer_load.loaded
    assert r.json()["prior_vintage"] == registry_with_a_newer_load.active
    written = [a for a in audit_rows() if a["action"] == "engine.activate"]
    assert len(written) == 1 and written[0]["target_id"] == registry_with_a_newer_load.dataset_key
    # `active_vintage.activated_by` names the CALLER, read back from the table `V.activate` wrote
    # rather than from the answer, which does not carry it.
    assert active_vintage_by(conn, registry_with_a_newer_load.dataset_key) == "admin-fresh@example.org"


async def test_an_unknown_dataset_key_is_refused_before_anything_is_read(admin_reauthed_client):
    r = await admin_reauthed_client.post("/api/admin/vintages/not-a-dataset/activate", json={"vintage": "2023"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_DATASET"


async def test_a_forced_activation_without_a_note_is_refused(admin_reauthed_client, registry_with_a_newer_load):
    r = await admin_reauthed_client.post(
        f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
        json={"vintage": registry_with_a_newer_load.loaded, "force": True},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "NOTE_REQUIRED"


async def test_an_activation_the_qa_gate_refuses_is_a_409_naming_the_reason(admin_reauthed_client, registry_with_a_failed_load):
    r = await admin_reauthed_client.post(
        f"/api/admin/vintages/{registry_with_a_failed_load.dataset_key}/activate",
        json={"vintage": registry_with_a_failed_load.loaded},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACTIVATION_REFUSED"
    assert "succeeded" in r.json()["error"]["message"]


async def test_an_admin_without_a_fresh_password_is_refused(admin_client, registry_with_a_newer_load):
    r = await admin_client.post(
        f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
        json={"vintage": registry_with_a_newer_load.loaded},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_REQUIRED"


async def test_an_api_token_can_never_activate_a_vintage(admin_token_client, registry_with_a_newer_load):
    r = await admin_token_client.post(
        f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
        json={"vintage": registry_with_a_newer_load.loaded},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_TOKEN"


@pytest.mark.parametrize("client_name", ["staff_reauthed_client", "buyer_client"])
async def test_only_an_admin_may_activate(client_name, staff_reauthed_client, buyer_client, registry_with_a_newer_load):
    """Both clients are ASKED FOR by name rather than resolved with `request.getfixturevalue`:
    these are async fixtures, and pytest-asyncio can only set one up from inside an already-running
    event loop by calling `asyncio.Runner.run()` there, which raises. Measured, not assumed — the
    `getfixturevalue` form fails with `RuntimeError: Runner.run() cannot be called from a running
    event loop` on both parameters."""
    client = {"staff_reauthed_client": staff_reauthed_client, "buyer_client": buyer_client}[client_name]
    r = await client.post(f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
                          json={"vintage": registry_with_a_newer_load.loaded})
    assert r.status_code == 403


async def test_a_legacy_operator_activation_records_the_operator_rather_than_an_account(legacy_client, registry_with_a_newer_load, audit_rows, conn):
    """`deps.require` exempts `kind == "legacy"` from the re-auth window and the operator secret
    names no `account` row, so `by` falls back to the literal "operator" — the one branch in this
    handler that is not an account email."""
    r = await legacy_client.post(f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
                                 json={"vintage": registry_with_a_newer_load.loaded})
    assert r.status_code == 200
    assert next(a for a in audit_rows() if a["action"] == "engine.activate")["actor_role"] == "legacy:operator"
    assert active_vintage_by(conn, registry_with_a_newer_load.dataset_key) == "operator"
