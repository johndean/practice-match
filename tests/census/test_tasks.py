"""Task A8: Celery entry points for the market-data layer, and the beat schedule that runs the
quarterly loads. This file tests the TASKS' own wiring -- state resolution, key/contact handling,
User-Agent/redirect settings, archive plumbing, and the "never crash the worker" gate on a
missing `CENSUS_API_KEY`/`CENSUS_CONTACT_EMAIL` -- not the loaders' own behaviour
(`app.census.acs/cbp/bds/qwi/tiger`), which `tests/census/test_acs.py`,
`tests/census/test_industry.py` and `tests/census/test_tiger.py` already cover at 100 % branch.
Every loader is monkeypatched throughout so this suite never needs a real Census API response or
shapefile.

Importing `app.tasks.census` is what registers its tasks on `celery_app` -- `include=[...]` on
the `Celery(...)` constructor only makes `celery worker`/`celery beat` import it at start-up
(`celery.loader.import_default_modules()`, called from `celery/bin/*`, never from a bare
`.tasks` access), and nothing about running pytest ever does that. This is exactly why
`tests/test_celery.py`'s own mail-pipeline test re-imports `app.mail.tasks` before checking
`celery_app.tasks` -- this file does the same for `app.tasks.census`."""
from __future__ import annotations

import httpx
import psycopg2
import pytest

from app.census import acs as census_acs
from app.census import bds as census_bds
from app.census import cbp as census_cbp
from app.census import license as census_license
from app.census import qwi as census_qwi
from app.census import tiger as census_tiger
from app.census import zbp as census_zbp
from app.census.registry import load as load_registry
from app.tasks import census as CT
from app.tasks.celery_app import celery_app

CONTACT = "tech@vinfoundation.example.org"


def test_census_tasks_are_registered():
    for name in ["census.load_tiger", "census.load_acs", "census.load_cbp", "census.load_zbp",
                 "census.load_qwi", "census.load_bds", "census.license_audit"]:
        assert name in celery_app.tasks, name


def test_census_task_functions_are_registered_under_their_stable_names():
    assert (
        CT.load_tiger_task.name, CT.load_acs_task.name, CT.load_cbp_task.name, CT.load_zbp_task.name,
        CT.load_qwi_task.name, CT.load_bds_task.name, CT.license_audit_task.name,
    ) == (
        "census.load_tiger", "census.load_acs", "census.load_cbp", "census.load_zbp",
        "census.load_qwi", "census.load_bds", "census.license_audit",
    )


def test_beat_schedules_only_the_automatic_cadences():
    beat = celery_app.conf.beat_schedule
    assert beat["qwi-quarterly"]["task"] == "census.load_qwi"
    assert beat["license-audit-quarterly"]["task"] == "census.license_audit"
    scheduled_tasks = {v["task"] for v in beat.values()}
    # manual approval (spec §9); census.load_zbp is a manual-trigger-only task too (A-C8 (8) / i1:
    # ZBP is annual and John-approved per load, exactly like acs/cbp/bds -- no beat entry is due).
    assert "census.load_acs" not in scheduled_tasks
    assert "census.load_cbp" not in scheduled_tasks
    assert "census.load_zbp" not in scheduled_tasks
    assert "census.load_bds" not in scheduled_tasks


def test_beat_merged_the_mail_pipelines_own_entries_survive():
    """A-C0 ¶2: A8 MERGES into `beat_schedule`, never replaces it."""
    beat = celery_app.conf.beat_schedule
    assert beat["mail-send-minutely"] == {"task": "mail.send", "schedule": 60.0}
    for name in ("sessions-purge-nightly", "outbox-purge-nightly"):
        assert name in beat


def test_qwi_quarterly_runs_the_15th_of_feb_may_aug_nov_at_0600_utc():
    sched = celery_app.conf.beat_schedule["qwi-quarterly"]["schedule"]
    assert sched.hour == {6} and sched.minute == {0}
    assert sched.day_of_month == {15}
    assert sched.month_of_year == {2, 5, 8, 11}


def test_license_audit_quarterly_runs_the_1st_of_jan_apr_jul_oct_at_0700_utc():
    sched = celery_app.conf.beat_schedule["license-audit-quarterly"]["schedule"]
    assert sched.hour == {7} and sched.minute == {0}
    assert sched.day_of_month == {1}
    assert sched.month_of_year == {1, 4, 7, 10}


# ---- load_tiger -------------------------------------------------------------------------------

def _fake_load_boundaries(captured):
    def fake(conn, http, states, vintage, archive=None):
        captured["conn"] = conn
        captured["http"] = http
        captured["states"] = list(states)
        captured["vintage"] = vintage
        captured["archive"] = archive
        return {"140:cb_2023_48_tract_500k.zip": 2}
    return fake


def test_load_tiger_builds_a_redirect_safe_client_and_delegates_to_load_boundaries(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    captured: dict = {}
    monkeypatch.setattr(census_tiger, "load_boundaries", _fake_load_boundaries(captured))

    result = CT.load_tiger()

    assert result == {"dataset": "tiger_cb", "counts": {"140:cb_2023_48_tract_500k.zip": 2}}
    assert captured["states"] == ["06", "08", "12", "13", "36", "48"]
    assert captured["vintage"] == "2023"
    assert captured["archive"] is None  # no S3_* settings configured in this suite
    ua = captured["http"].headers["User-Agent"]
    assert ua == f"PracticeMatch/{CT.VERSION} ({CONTACT})"  # A-C3 (2): never "VIN Foundation; " (spec's literal text, superseded)
    assert captured["http"].follow_redirects is False


def test_load_tiger_accepts_a_vintage_override(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    captured: dict = {}
    monkeypatch.setattr(census_tiger, "load_boundaries", _fake_load_boundaries(captured))

    CT.load_tiger(vintage="2022")

    assert captured["vintage"] == "2022"


def test_load_tiger_without_a_contact_records_a_failed_ingest_run_and_does_not_raise(conn, monkeypatch):
    """The worker also runs the mail pipeline: `require_contact()`'s `SystemExit(2)` (correct at
    a CLI entry point) must never propagate out of a Celery task and take it down."""
    monkeypatch.delenv("CENSUS_CONTACT_EMAIL", raising=False)
    called = []
    monkeypatch.setattr(census_tiger, "load_boundaries", lambda *a, **kw: called.append(1))

    result = CT.load_tiger(vintage="2023")

    assert called == []  # the loader's own ingest.run() never even opens
    assert result["dataset"] == "tiger_cb"
    assert "CENSUS_CONTACT_EMAIL" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage, error_detail FROM ingest_run WHERE dataset_key = 'tiger_cb' ORDER BY id DESC LIMIT 1")
        status, vintage, error = cur.fetchone()
    assert status == "failed" and vintage == "2023" and "CENSUS_CONTACT_EMAIL" in error


def test_load_tiger_records_a_failed_ingest_run_when_a_key_is_present_but_the_archive_is_not(conn, monkeypatch):
    """Controller amendment A-C11 (10): even though `load_tiger` itself needs no
    `CENSUS_API_KEY`, the SAME worker process runs the keyed loaders too -- once
    `settings.census_api_key` is set (the "a live load is possible" signal A-C1 ¶7 cares about),
    the raw archive coming back `None` must refuse, not silently disable archiving."""
    from app.config import settings

    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.setattr(settings, "census_api_key", "the-key")
    monkeypatch.setattr(census_tiger, "load_boundaries", lambda *a, **kw: pytest.fail("must not run without the required archive"))

    result = CT.load_tiger()

    assert result["dataset"] == "tiger_cb"
    assert "S3_ENDPOINT_URL" in result["error"] and "A-C1" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM ingest_run WHERE dataset_key = 'tiger_cb' ORDER BY id DESC LIMIT 1")
        (status,) = cur.fetchone()
    assert status == "failed"


def test_load_tiger_refuses_a_dataset_that_is_not_cleared(conn, monkeypatch):
    """A-C8 (9) / i2: unlike acs/cbp/bds/qwi/zbp's own `load()` functions, `tiger.load_boundaries`
    has no internal `cleared` check at all, so the task adds one -- exactly like its siblings."""
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'tiger_cb'")
    monkeypatch.setattr(census_tiger, "load_boundaries", lambda *a, **kw: pytest.fail("tiger.load_boundaries must not run for a blocked dataset"))

    result = CT.load_tiger()

    assert result["dataset"] == "tiger_cb"
    assert "blocked" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM ingest_run WHERE dataset_key = 'tiger_cb' ORDER BY id DESC LIMIT 1")
        (status,) = cur.fetchone()
    assert status == "failed"


# ---- load_acs -----------------------------------------------------------------------------------

def _fake_acs_load(captured):
    def fake(conn, factory, dataset_key, states):
        captured["dataset_key"] = dataset_key
        captured["states"] = list(states)
        ds = load_registry(conn)[dataset_key]
        client = factory(ds)
        captured["client"] = (client.api_key, client.contact)
        client.close()
        return 42
    return fake


def test_load_acs_builds_a_keyed_client_and_delegates_to_acs_load(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    captured: dict = {}
    monkeypatch.setattr(census_acs, "load", _fake_acs_load(captured))

    result = CT.load_acs("acs5")

    assert result == {"dataset": "acs5", "rows": 42}
    assert captured["dataset_key"] == "acs5"
    assert captured["states"] == ["06", "08", "12", "13", "36", "48"]
    assert captured["client"] == ("the-key", CONTACT)


def test_load_acs_defaults_to_acs5(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    captured: dict = {}
    monkeypatch.setattr(census_acs, "load", _fake_acs_load(captured))

    CT.load_acs()

    assert captured["dataset_key"] == "acs5"


def test_load_acs_without_a_key_records_a_failed_ingest_run_for_that_datasets_own_vintage(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    called = []
    monkeypatch.setattr(census_acs, "load", lambda *a, **kw: called.append(1))

    result = CT.load_acs("acs5_prior")

    assert called == []
    assert result == {"dataset": "acs5_prior", "error": "CENSUS_API_KEY is not set; refused before any Census request"}
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'acs5_prior' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "2014\u20132018"  # the registry's own seeded vintage for acs5_prior


def test_load_acs_records_a_failed_ingest_run_when_a_key_is_present_but_the_archive_is_not(conn, monkeypatch):
    """Controller amendment A-C11 (10): `require_archive`'s own branch logic is exercised at 100%
    branch in `tests/census/test_client.py`; this pins that `load_acs` actually calls it, at the
    registry's OWN vintage for the dataset key given, the same shape every `_refuse` call already
    uses for a missing key/contact."""
    from app.config import settings

    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.setattr(settings, "census_api_key", "the-key")
    monkeypatch.setattr(census_acs, "load", lambda *a, **kw: pytest.fail("must not run without the required archive"))

    result = CT.load_acs("acs5_prior")

    assert result["dataset"] == "acs5_prior"
    assert "S3_BUCKET" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'acs5_prior' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "2014\u20132018"  # the registry's own seeded vintage for acs5_prior


def test_load_acs_without_a_contact_refuses_before_checking_the_key(conn, monkeypatch):
    monkeypatch.delenv("CENSUS_CONTACT_EMAIL", raising=False)
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)

    result = CT.load_acs("acs5")

    assert "CENSUS_CONTACT_EMAIL" in result["error"]


# ---- load_cbp -----------------------------------------------------------------------------------

def test_load_cbp_builds_a_keyed_client_and_delegates_to_cbp_load(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    captured: dict = {}

    def fake(conn, factory, states):
        captured["states"] = list(states)
        ds = load_registry(conn)["cbp"]
        client = factory(ds)
        captured["client"] = (client.api_key, client.contact)
        client.close()
        return 7
    monkeypatch.setattr(census_cbp, "load", fake)

    result = CT.load_cbp()

    assert result == {"rows": 7}
    assert captured["client"] == ("the-key", CONTACT)


def test_load_cbp_without_a_key_records_a_failed_ingest_run(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    monkeypatch.setattr(census_cbp, "load", lambda *a, **kw: pytest.fail("cbp.load must not run without a key"))

    result = CT.load_cbp()

    assert result["dataset"] == "cbp" and "CENSUS_API_KEY" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'cbp' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "2022"


def test_load_cbp_records_a_failed_ingest_run_when_a_key_is_present_but_the_archive_is_not(conn, monkeypatch):
    """Controller amendment A-C11 (10), the same `_resolve_archive` shape `load_tiger`/`load_acs`
    already prove -- pinned here too since `_resolve_archive`'s call site is a distinct line in
    every task."""
    from app.config import settings

    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.setattr(settings, "census_api_key", "the-key")
    monkeypatch.setattr(census_cbp, "load", lambda *a, **kw: pytest.fail("must not run without the required archive"))

    result = CT.load_cbp()

    assert result["dataset"] == "cbp"
    assert "S3_ACCESS_KEY_ID" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'cbp' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "2022"


# ---- load_bds -----------------------------------------------------------------------------------

def test_load_bds_builds_a_keyed_client_and_delegates_to_bds_load(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    captured: dict = {}

    def fake(conn, factory, states, *, year):
        captured["year"] = year
        captured["states"] = list(states)
        ds = load_registry(conn)["bds"]
        client = factory(ds)
        captured["client"] = (client.api_key, client.contact)
        client.close()
        return 3
    monkeypatch.setattr(census_bds, "load", fake)

    result = CT.load_bds(2022)

    assert result == {"year": 2022, "rows": 3}
    assert captured["year"] == 2022
    assert captured["client"] == ("the-key", CONTACT)


def test_load_bds_without_a_key_records_a_failed_ingest_run_at_the_given_year(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    monkeypatch.setattr(census_bds, "load", lambda *a, **kw: pytest.fail("bds.load must not run without a key"))

    result = CT.load_bds(2021)

    assert result["dataset"] == "bds" and "CENSUS_API_KEY" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'bds' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "2021"


def test_load_bds_records_a_failed_ingest_run_when_a_key_is_present_but_the_archive_is_not(conn, monkeypatch):
    """Controller amendment A-C11 (10) -- `load_bds` refuses using the given year as the vintage,
    the same as its own missing-key arm above."""
    from app.config import settings

    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.setattr(settings, "census_api_key", "the-key")
    monkeypatch.setattr(census_bds, "load", lambda *a, **kw: pytest.fail("must not run without the required archive"))

    result = CT.load_bds(2021)

    assert result["dataset"] == "bds"
    assert "S3_SECRET_ACCESS_KEY" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'bds' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "2021"


# ---- load_qwi -----------------------------------------------------------------------------------

def test_load_qwi_uses_the_given_year_and_quarter_without_resolving(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    captured: dict = {}

    def fake_load(conn, factory, states, *, year, quarter):
        captured["year"], captured["quarter"] = year, quarter
        captured["states"] = list(states)
        ds = load_registry(conn)["qwi"]
        client = factory(ds)
        captured["client"] = (client.api_key, client.contact)
        client.close()
        return 9
    monkeypatch.setattr(census_qwi, "load", fake_load)
    monkeypatch.setattr(census_qwi, "trim", lambda conn, keep=20: 5)
    monkeypatch.setattr(census_qwi, "latest_available", lambda *a, **kw: pytest.fail("must not resolve when year/quarter are given"))

    result = CT.load_qwi(2025, 2)

    assert result == {"year": 2025, "quarter": 2, "rows": 9, "trimmed": 5}
    assert captured["client"] == ("the-key", CONTACT)


def test_load_qwi_resolves_the_latest_quarter_when_omitted(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    resolve_calls: list = []

    def fake_latest_available(client, state, *, today):
        resolve_calls.append((state, today))
        return (2025, 1)

    def fake_load(conn, factory, states, *, year, quarter):
        assert (year, quarter) == (2025, 1)
        return 4
    monkeypatch.setattr(census_qwi, "latest_available", fake_latest_available)
    monkeypatch.setattr(census_qwi, "load", fake_load)
    monkeypatch.setattr(census_qwi, "trim", lambda conn, keep=20: 0)

    result = CT.load_qwi()

    assert result == {"year": 2025, "quarter": 1, "rows": 4, "trimmed": 0}
    assert len(resolve_calls) == 1
    assert resolve_calls[0][0] == "06"  # states[0] -- market_state's alphabetically-first state_fips


def test_load_qwi_trims_to_20_quarters(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    trim_calls: list = []
    monkeypatch.setattr(census_qwi, "load", lambda *a, **kw: 1)
    monkeypatch.setattr(census_qwi, "trim", lambda conn, keep=20: trim_calls.append(keep) or 1)

    CT.load_qwi(2025, 1)

    assert trim_calls == [20]


def test_load_qwi_without_a_key_records_a_failed_ingest_run_at_the_registrys_vintage(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    monkeypatch.setattr(census_qwi, "load", lambda *a, **kw: pytest.fail("qwi.load must not run without a key"))
    monkeypatch.setattr(census_qwi, "latest_available", lambda *a, **kw: pytest.fail("must not resolve without a key"))

    result = CT.load_qwi()

    assert result["dataset"] == "qwi" and "CENSUS_API_KEY" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'qwi' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "latest quarter"  # 017_census_registry.sql's seeded qwi vintage


def test_load_qwi_records_a_failed_ingest_run_when_a_key_is_present_but_the_archive_is_not(conn, monkeypatch):
    """Controller amendment A-C11 (10) -- checked after the licence gate, before the resolve
    branch, so neither `latest_available` nor `load` ever runs without the required archive."""
    from app.config import settings

    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.setattr(settings, "census_api_key", "the-key")
    monkeypatch.setattr(census_qwi, "latest_available", lambda *a, **kw: pytest.fail("must not resolve without the required archive"))
    monkeypatch.setattr(census_qwi, "load", lambda *a, **kw: pytest.fail("must not run without the required archive"))

    result = CT.load_qwi()

    assert result["dataset"] == "qwi"
    assert "S3_ENDPOINT_URL" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'qwi' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "latest quarter"


def test_load_qwi_refuses_a_blocked_dataset_before_probing_the_latest_quarter(conn, monkeypatch):
    """A-C8 (1) / M1: `qwi.load`'s own `cleared` check runs only AFTER `latest_available` has
    already probed Census up to twelve times and `CensusClient.fetch_table` has already archived
    each successful body -- exactly `scripts/census_load.py::cmd_qwi`'s own documented hazard.
    Called with year/quarter omitted (precisely the shape `qwi-quarterly`'s beat entry publishes)
    so the resolve branch would otherwise run; `latest_available` and `load` both `pytest.fail` if
    reached, proving neither a request nor an archive write happens."""
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'qwi'")
    monkeypatch.setattr(census_qwi, "latest_available", lambda *a, **kw: pytest.fail("must not probe Census for a blocked dataset"))
    monkeypatch.setattr(census_qwi, "load", lambda *a, **kw: pytest.fail("qwi.load must not run for a blocked dataset"))

    result = CT.load_qwi()

    assert result["dataset"] == "qwi"
    assert "blocked" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'qwi' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "latest quarter"


def test_load_qwi_records_a_failed_ingest_run_when_market_state_is_empty(conn, monkeypatch):
    """m5 (controller amendment A-C11 (6)): resolving the latest published quarter indexes
    `states[0]` -- an empty `market_state` used to raise a bare `IndexError` and crash the task
    instead of recording a named, failed `ingest_run`. Unreachable today (017_census_registry.sql
    seeds six rows and nothing deletes them), but the task must not depend on that forever."""
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM market_state")
    monkeypatch.setattr(census_qwi, "latest_available", lambda *a, **kw: pytest.fail("must not resolve a quarter with no states"))

    result = CT.load_qwi()

    assert result["dataset"] == "qwi"
    assert "market_state" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM ingest_run WHERE dataset_key = 'qwi' ORDER BY id DESC LIMIT 1")
        (status,) = cur.fetchone()
    assert status == "failed"


# ---- load_zbp -----------------------------------------------------------------------------------

def test_load_zbp_builds_a_keyed_client_and_delegates_to_zbp_load(conn, monkeypatch):
    """A-C8 (8) / i1: `census.load_zbp` exists for parity with its siblings -- manual trigger
    only (`test_beat_schedules_only_the_automatic_cadences` pins that no beat entry names it)."""
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    captured: dict = {}

    def fake(conn, factory, states):
        captured["states"] = list(states)
        ds = load_registry(conn)["zbp"]
        client = factory(ds)
        captured["client"] = (client.api_key, client.contact)
        client.close()
        return 12
    monkeypatch.setattr(census_zbp, "load", fake)

    result = CT.load_zbp()

    assert result == {"rows": 12}
    assert captured["client"] == ("the-key", CONTACT)


def test_load_zbp_without_a_key_records_a_failed_ingest_run(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    monkeypatch.setattr(census_zbp, "load", lambda *a, **kw: pytest.fail("zbp.load must not run without a key"))

    result = CT.load_zbp()

    assert result["dataset"] == "zbp" and "CENSUS_API_KEY" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'zbp' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "2022"


def test_load_zbp_records_a_failed_ingest_run_when_a_key_is_present_but_the_archive_is_not(conn, monkeypatch):
    """Controller amendment A-C11 (10) -- the same `_resolve_archive` shape as its siblings."""
    from app.config import settings

    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.setattr(settings, "census_api_key", "the-key")
    monkeypatch.setattr(census_zbp, "load", lambda *a, **kw: pytest.fail("must not run without the required archive"))

    result = CT.load_zbp()

    assert result["dataset"] == "zbp"
    assert "S3_BUCKET" in result["error"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, vintage FROM ingest_run WHERE dataset_key = 'zbp' ORDER BY id DESC LIMIT 1")
        status, vintage = cur.fetchone()
    assert status == "failed" and vintage == "2022"


# ---- license_audit ------------------------------------------------------------------------------

def test_license_audit_builds_a_client_and_delegates_to_license_audit(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    captured: dict = {}

    def fake(conn, http):
        captured["http"] = http
        return [
            census_license.AuditResult("acs5", False, "abc", 200),
            census_license.AuditResult("cbp", True, "def", 200),
        ]
    monkeypatch.setattr(census_license, "audit", fake)

    result = CT.license_audit()

    assert result == {"checked": 2, "drift": ["cbp"]}
    assert isinstance(captured["http"], httpx.Client)
    assert CONTACT in captured["http"].headers["User-Agent"]


def test_license_audit_reports_no_drift_when_nothing_changed(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.setattr(census_license, "audit", lambda conn, http: [census_license.AuditResult("acs5", False, "abc", 200)])

    result = CT.license_audit()

    assert result == {"checked": 1, "drift": []}


def test_license_audit_without_a_contact_does_not_crash_and_never_calls_audit(conn, monkeypatch):
    monkeypatch.delenv("CENSUS_CONTACT_EMAIL", raising=False)
    monkeypatch.setattr(census_license, "audit", lambda conn, http: pytest.fail("license.audit must not run without a contact"))

    result = CT.license_audit()

    assert result["checked"] == 0 and result["drift"] == []
    assert "CENSUS_CONTACT_EMAIL" in result["error"]


# ---- _conn (A-C8 m5) ------------------------------------------------------------------------------

def test_conn_uses_the_canonical_dsn_helper_not_a_reimplementation(monkeypatch):
    """A-C8 (6) / m5: `_conn()` used to inline `.replace("postgresql+asyncpg://",
    "postgresql://", 1)` -- byte-for-byte what `app.db.sync_dsn()` already is. Proven here by
    patching the name `census.py` actually calls (`from app.db import sync_dsn` binds it into
    this module's own namespace, so the fake must go there, not onto `app.db` itself) and
    watching `_conn()` call through it (a deliberately bad, fast-failing DSN -- a closed local
    port -- so this stays a unit test, not a network probe)."""
    calls: list = []

    def fake_sync_dsn(*args, **kwargs):
        calls.append((args, kwargs))
        return "postgresql://127.0.0.1:1/nonexistent"

    monkeypatch.setattr(CT, "sync_dsn", fake_sync_dsn)

    with pytest.raises(psycopg2.OperationalError):
        CT._conn()

    assert calls == [((), {})]
