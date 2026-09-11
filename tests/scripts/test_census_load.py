"""`scripts/census_load.py` -- the operator CLI (Task A4's `--tiger`; task A5 adds `acs`; task A6
adds `cbp`/`zbp`/`qwi`/`bds`; task A7 adds `activate`, the only path that flips `active_vintage`
-- never automatic, never from a Celery task).

Runs inside the worker image (`railway run --service worker -- python scripts/census_load.py
tiger`) or locally against docker-compose; every subcommand is idempotent. This file tests the
CLI's OWN wiring -- argument parsing, the `market_state` query, the fail-closed key/contact
gates, the User-Agent/redirect settings the HTTP client is built with, and every error arm -- not
`app.census.tiger.load_boundaries`'s, `app.census.acs.load`'s or the industry loaders' own
behaviour, which `tests/census/test_tiger.py`, `tests/census/test_acs.py` and
`tests/census/test_industry.py` already cover at 100 % branch. Every loader is monkeypatched
throughout so this suite never needs a real shapefile or a live Census API response.

Every subcommand's exit codes (A-C4 ¶2, as `tiger`'s already do): 0 done; 2 refused before
anything is opened (no `CENSUS_API_KEY`/`CENSUS_CONTACT_EMAIL`, no `DATABASE_URL`, or a
licence-gated dataset -- `PermissionError`, spec §1); 3 database unreachable, OR (A-C7 (7) / I12)
a `psycopg2.Error` raised AFTER connect -- every `cmd_*` closes its connection in `try`/`finally`
and prints only the exception's type name, never its text; 4 a download/fetch
failed (`CensusHTTPError`); 5 validation failed (`VariableMissing` -- a response missing an
expected variable, spec §4/¶12). `cbp`/`zbp`/`bds` skip dedicated "missing key"/"missing contact"
tests below -- `require_key`/`require_contact` are the same functions `tiger`'s and `acs`'s tests
already exercise at 100 % branch in `app/census/client.py`, and there is no additional
conditional in THIS file for a missing key/contact to reach (the call sites are plain statements,
not branches) -- the six arms that ARE new per subcommand (dsn-missing, db-unreachable, success,
and the three `except` arms) are what each subcommand's tests below cover; the post-connect
database-error arm and the connection close are covered once, for every subcommand, by the single
parametrised test near the end of this file."""
from __future__ import annotations

import runpy
import sys
import zipfile
from pathlib import Path

import psycopg2
import pytest
import shapefile  # pyshp

from app.census import acs as census_acs
from app.census import bds as census_bds
from app.census import cbp as census_cbp
from app.census import qwi as census_qwi
from app.census import tiger as census_tiger
from app.census import vintage as census_vintage
from app.census import zbp as census_zbp
from scripts import census_load

ROOT = Path(__file__).resolve().parent.parent.parent


def _fake_load_boundaries(captured: dict):
    def fake(conn, http, states, vintage, archive=None):
        captured["conn"] = conn
        captured["http"] = http
        captured["states"] = list(states)
        captured["vintage"] = vintage
        captured["archive"] = archive
        return {"140:cb_2023_48_tract_500k.zip": 2, "160:cb_2023_48_place_500k.zip": 1}
    return fake


def test_cmd_tiger_queries_market_state_and_prints_row_counts(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}
    monkeypatch.setattr(census_tiger, "load_boundaries", _fake_load_boundaries(captured))

    assert census_load.main(["tiger"]) == 0

    # market_state seeds six states (017_census_registry.sql; A-C0 P10 / A-C1 (5)).
    assert captured["states"] == ["06", "08", "12", "13", "36", "48"]
    assert captured["vintage"] == "2023"
    out = capsys.readouterr().out
    assert "140:cb_2023_48_tract_500k.zip: 2 rows" in out
    assert "160:cb_2023_48_place_500k.zip: 1 rows" in out


def test_cmd_tiger_accepts_a_vintage_override(scratch_dsn, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}
    monkeypatch.setattr(census_tiger, "load_boundaries", _fake_load_boundaries(captured))

    assert census_load.main(["tiger", "--vintage", "2022"]) == 0

    assert captured["vintage"] == "2022"


def test_cmd_tiger_builds_the_user_agent_from_require_contact_never_a_default(scratch_dsn, monkeypatch):
    """A-C1 (4) / A-C3 (2): the contact is always `CENSUS_CONTACT_EMAIL`'s value, never a
    hard-coded address -- the brief's own draft CLI snippet used a bare "PracticeMatch (VIN
    Foundation)" User-Agent, which this corrects."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "distinctive-contact@vinfoundation.example.org")
    captured: dict = {}
    monkeypatch.setattr(census_tiger, "load_boundaries", _fake_load_boundaries(captured))

    assert census_load.main(["tiger"]) == 0

    ua = captured["http"].headers["User-Agent"]
    assert "distinctive-contact@vinfoundation.example.org" in ua
    assert ua.startswith("PracticeMatch/")


def test_cmd_tiger_pins_follow_redirects_false(scratch_dsn, monkeypatch):
    """Controller correction (2026-09-09): a 3xx from www2.census.gov must never be silently
    followed into a body that gets parsed and archived without this script seeing the redirect."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}
    monkeypatch.setattr(census_tiger, "load_boundaries", _fake_load_boundaries(captured))

    assert census_load.main(["tiger"]) == 0

    assert captured["http"].follow_redirects is False


def test_cmd_tiger_leaves_the_archive_disabled_without_s3_settings(scratch_dsn, monkeypatch):
    from app.config import settings

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(settings, "s3_endpoint_url", None)
    monkeypatch.setattr(settings, "s3_bucket", None)
    monkeypatch.setattr(settings, "s3_access_key_id", None)
    monkeypatch.setattr(settings, "s3_secret_access_key", None)
    captured: dict = {}
    monkeypatch.setattr(census_tiger, "load_boundaries", _fake_load_boundaries(captured))

    assert census_load.main(["tiger"]) == 0

    assert captured["archive"] is None


def test_cmd_tiger_passes_a_real_archive_once_s3_settings_are_configured(scratch_dsn, monkeypatch):
    from app.config import settings
    from app.storage import ObjectStore

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(settings, "s3_endpoint_url", "http://s3.example.internal")
    monkeypatch.setattr(settings, "s3_bucket", "practice-match-data")
    monkeypatch.setattr(settings, "s3_access_key_id", "AKIDEXAMPLE")
    monkeypatch.setattr(settings, "s3_secret_access_key", "secretkey")
    captured: dict = {}
    monkeypatch.setattr(census_tiger, "load_boundaries", _fake_load_boundaries(captured))

    assert census_load.main(["tiger"]) == 0

    assert isinstance(captured["archive"], ObjectStore)


def test_main_requires_a_subcommand(capsys):
    with pytest.raises(SystemExit) as exc:
        census_load.main([])
    assert exc.value.code == 2


def test_cmd_tiger_exits_two_naming_the_missing_contact_email(monkeypatch, capsys):
    """A-C4 ¶2 / M-1 (A3 and A4 reviews): a missing CENSUS_CONTACT_EMAIL is "refused before
    anything was opened" -- exit 2, not 3, which the shared scheme reserves for "database
    unreachable" so the two failures cannot collide on one code."""
    monkeypatch.delenv("CENSUS_CONTACT_EMAIL", raising=False)
    with pytest.raises(SystemExit) as exc:
        census_load.main(["tiger"])
    assert exc.value.code == 2
    assert "CENSUS_CONTACT_EMAIL" in capsys.readouterr().err


def test_cmd_tiger_returns_two_without_a_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    assert census_load.main(["tiger"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cmd_tiger_returns_three_when_the_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    assert census_load.main(["tiger"]) == 3
    assert "database unreachable" in capsys.readouterr().err


def test_cmd_tiger_returns_four_when_the_boundary_download_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import CensusHTTPError

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake(conn, http, states, vintage, archive=None):
        raise CensusHTTPError(500, "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_nation_5m.zip")

    monkeypatch.setattr(census_tiger, "load_boundaries", fake)

    assert census_load.main(["tiger"]) == 4
    assert "boundary download failed" in capsys.readouterr().err


def test_cmd_tiger_returns_two_when_tiger_cb_is_not_cleared(scratch_dsn, monkeypatch, capsys):
    """m1 (controller amendment A-C11 (2)): `cmd_tiger` is the one loader entry point that never
    checked the registry itself -- `load_boundaries` has no internal `cleared` check (unlike
    every other loader's `load()`), and the Celery task already gates this (A-C8 (9)/i2); the CLI
    did not, so an admin moving `tiger_cb` to `blocked` would stop the quarterly task while an
    operator running this command by hand could still ingest it."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    conn = census_load._conn(scratch_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'tiger_cb'")
    finally:
        conn.close()
    monkeypatch.setattr(census_tiger, "load_boundaries", lambda *a, **kw: pytest.fail("tiger.load_boundaries must not run for a blocked dataset"))

    assert census_load.main(["tiger"]) == 2
    err = capsys.readouterr().err
    assert "tiger" in err and "refused" in err and "blocked" in err


def test_cmd_tiger_returns_five_when_the_boundary_file_is_corrupt_or_unreadable(scratch_dsn, monkeypatch, capsys):
    """m2 (controller amendment A-C11 (3)): `parse_shapefile` can raise `zipfile.BadZipFile` (a
    truncated or corrupt download -- a fixture zip of garbage bytes, below) or a pyshp
    `shapefile.ShapefileException` on a malformed shapefile inside an otherwise-valid zip;
    `cmd_tiger` only mapped `CensusHTTPError`, so either escaped as an uncaught traceback (exit 1)
    instead of the A-C4 scheme's 5 ("validation failed")."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake(conn, http, states, vintage, archive=None):
        raise zipfile.BadZipFile("File is not a zip file")

    monkeypatch.setattr(census_tiger, "load_boundaries", fake)

    assert census_load.main(["tiger"]) == 5
    err = capsys.readouterr().err
    assert "boundary file corrupt or unreadable" in err


def test_cmd_tiger_returns_five_for_a_pyshp_shapefile_exception_too(scratch_dsn, monkeypatch, capsys):
    """The other documented arm of the same m2 fix -- a zip that opens fine but whose shapefile
    contents pyshp itself refuses to parse."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake(conn, http, states, vintage, archive=None):
        raise shapefile.ShapefileException("Unable to determine shape type")

    monkeypatch.setattr(census_tiger, "load_boundaries", fake)

    assert census_load.main(["tiger"]) == 5
    err = capsys.readouterr().err
    assert "boundary file corrupt or unreadable" in err


# --- the raw archive is required once a live load is possible (controller amendment A-C11 (10)) -
# `require_archive` itself is exercised at 100% branch by `tests/census/test_client.py`; these
# pin that each CLI entry point actually CALLS it, right where `archive = ObjectStore.from_
# settings(settings)` is computed. The signal is `settings.census_api_key` -- the already-loaded
# `Settings` singleton's attribute, never `os.environ` -- so every OTHER test in this file, which
# only ever does `monkeypatch.setenv("CENSUS_API_KEY", ...)`, never trips this and needs no
# changes: only a test that does `monkeypatch.setattr(settings, "census_api_key", ...)`, as the
# two below do, reaches this refusal.

def test_cmd_tiger_refuses_when_a_key_is_present_but_the_archive_is_not_configured(scratch_dsn, monkeypatch, capsys):
    """Tiger itself never needs `CENSUS_API_KEY` -- but on the real worker the same process also
    runs acs/cbp/zbp/bds/qwi, which do, so `settings.census_api_key` being set is exactly the
    "a live load is possible" signal A-C1 ¶7 cares about, even for the one loader that does not
    consume the key itself."""
    from app.config import settings

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(settings, "census_api_key", "the-key")
    monkeypatch.setattr(settings, "s3_endpoint_url", None)
    monkeypatch.setattr(settings, "s3_bucket", None)
    monkeypatch.setattr(settings, "s3_access_key_id", None)
    monkeypatch.setattr(settings, "s3_secret_access_key", None)
    monkeypatch.setattr(census_tiger, "load_boundaries", lambda *a, **kw: pytest.fail("must not run without the required archive"))

    with pytest.raises(SystemExit) as exc:
        census_load.main(["tiger"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "S3_ENDPOINT_URL" in err and "S3_BUCKET" in err and "S3_ACCESS_KEY_ID" in err and "S3_SECRET_ACCESS_KEY" in err


def test_cmd_acs_refuses_when_a_key_is_present_but_the_archive_is_not_configured(scratch_dsn, monkeypatch, capsys):
    from app.config import settings

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(settings, "census_api_key", "the-key")
    monkeypatch.setattr(settings, "s3_endpoint_url", None)
    monkeypatch.setattr(settings, "s3_bucket", None)
    monkeypatch.setattr(settings, "s3_access_key_id", None)
    monkeypatch.setattr(settings, "s3_secret_access_key", None)
    monkeypatch.setattr(census_acs, "load", lambda *a, **kw: pytest.fail("must not run without the required archive"))

    with pytest.raises(SystemExit) as exc:
        census_load.main(["acs", "--dataset", "acs5"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "S3_ENDPOINT_URL" in err and "S3_SECRET_ACCESS_KEY" in err


# --- acs subcommand (Task A5) ---------------------------------------------------------------

def test_cmd_acs_queries_market_state_and_prints_measure_counts(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states, levels=None):
        captured.setdefault("dataset_keys", []).append(dataset_key)
        captured["states"] = list(states)
        return {"acs5": 100, "acs5_subject": 10, "acs5_prior": 50}[dataset_key]

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs"]) == 0

    # market_state seeds six states (017_census_registry.sql; A-C0 P10 / A-C1 (5)).
    assert captured["states"] == ["06", "08", "12", "13", "36", "48"]
    # the default `--dataset` list is all three ACS datasets, in order.
    assert captured["dataset_keys"] == ["acs5", "acs5_subject", "acs5_prior"]
    out = capsys.readouterr().out
    assert "acs5: 100 measures" in out and "acs5_subject: 10 measures" in out and "acs5_prior: 50 measures" in out


def test_cmd_acs_accepts_a_dataset_override(scratch_dsn, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states, levels=None):
        captured.setdefault("dataset_keys", []).append(dataset_key)
        return 1

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 0

    assert captured["dataset_keys"] == ["acs5"]


def test_cmd_acs_dataset_choices_reject_an_unknown_dataset_key(capsys):
    """A5's review of itself: `acs.load`'s `VARIABLES[dataset_key]` lookup raises a raw
    `KeyError` for a dataset that is not one of the three ACS datasets (e.g. an industry
    dataset key such as `cbp`) -- argparse's own `choices=sorted(acs.VARIABLES)` on `--dataset`
    turns that into the same "refused before anything is opened" shape as a missing
    `CENSUS_API_KEY`, exit 2, before the database or the network is ever touched."""
    with pytest.raises(SystemExit) as exc:
        census_load.main(["acs", "--dataset", "cbp"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_cmd_acs_builds_the_client_factory_from_the_required_key_and_contact_never_a_default(scratch_dsn, monkeypatch):
    """The brief's own draft CLI snippet built the client from `settings.census_contact_email`
    directly, which is `None` by default and would surface as a bare `ValueError` deep inside
    `acs.load` instead of this script's own exit-2 gate (A-C3b M3; A-C1 (4)) -- `require_key`/
    `require_contact` must be the source for both, exactly as `cmd_tiger` already does for the
    contact alone."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "distinctive-key-123")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "distinctive-contact@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states, levels=None):
        client = client_factory(object())  # CensusClient's constructor never inspects `ds`
        captured["api_key"] = client.api_key
        captured["contact"] = client.contact
        captured["ua"] = client._http.headers["user-agent"]
        client.close()
        return 0

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 0

    assert captured["api_key"] == "distinctive-key-123"
    assert captured["contact"] == "distinctive-contact@vinfoundation.example.org"
    assert captured["ua"].startswith("PracticeMatch/") and "distinctive-contact@vinfoundation.example.org" in captured["ua"]


def test_cmd_acs_leaves_the_archive_disabled_without_s3_settings(scratch_dsn, monkeypatch):
    from app.config import settings

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(settings, "s3_endpoint_url", None)
    monkeypatch.setattr(settings, "s3_bucket", None)
    monkeypatch.setattr(settings, "s3_access_key_id", None)
    monkeypatch.setattr(settings, "s3_secret_access_key", None)
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states, levels=None):
        captured["archive"] = client_factory(object()).archive
        return 0

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 0

    assert captured["archive"] is None


def test_cmd_acs_passes_a_real_archive_once_s3_settings_are_configured(scratch_dsn, monkeypatch):
    from app.config import settings
    from app.storage import ObjectStore

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(settings, "s3_endpoint_url", "http://s3.example.internal")
    monkeypatch.setattr(settings, "s3_bucket", "practice-match-data")
    monkeypatch.setattr(settings, "s3_access_key_id", "AKIDEXAMPLE")
    monkeypatch.setattr(settings, "s3_secret_access_key", "secretkey")
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states, levels=None):
        captured["archive"] = client_factory(object()).archive
        return 0

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 0

    assert isinstance(captured["archive"], ObjectStore)


def test_cmd_acs_exits_two_naming_the_missing_api_key(monkeypatch, capsys):
    """A-C4 ¶2: refused before anything is opened -- exit 2, checked before `CENSUS_CONTACT_EMAIL`
    and before `DATABASE_URL`."""
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    with pytest.raises(SystemExit) as exc:
        census_load.main(["acs"])
    assert exc.value.code == 2
    assert "CENSUS_API_KEY" in capsys.readouterr().err


def test_cmd_acs_exits_two_naming_the_missing_contact_email(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.delenv("CENSUS_CONTACT_EMAIL", raising=False)
    with pytest.raises(SystemExit) as exc:
        census_load.main(["acs"])
    assert exc.value.code == 2
    assert "CENSUS_CONTACT_EMAIL" in capsys.readouterr().err


def test_cmd_acs_returns_two_without_a_database_url(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert census_load.main(["acs"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cmd_acs_returns_three_when_the_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

    assert census_load.main(["acs"]) == 3
    assert "database unreachable" in capsys.readouterr().err


def test_cmd_acs_returns_four_when_a_dataset_download_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import CensusHTTPError

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, dataset_key, states, levels=None):
        raise CensusHTTPError(500, "https://api.census.gov/data/2023/acs/acs5?key=SECRET")

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 4
    err = capsys.readouterr().err
    assert "acs5 download failed" in err and "SECRET" not in err


def test_cmd_acs_returns_five_when_a_dataset_fails_validation(scratch_dsn, monkeypatch, capsys):
    from app.census.client import VariableMissing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, dataset_key, states, levels=None):
        raise VariableMissing(["B19013_001E"])

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 5
    err = capsys.readouterr().err
    assert "acs5 failed validation" in err and "B19013_001E" in err


def test_cmd_acs_returns_two_when_a_dataset_is_licence_gated(scratch_dsn, monkeypatch, capsys):
    """A5's review of itself (A-C5 record): `acs.load` raises `PermissionError` for a dataset
    that is `unresolved`/`blocked` (spec §1 licensing gate, exercised by
    `tests/census/test_acs.py::test_load_refuses_a_dataset_that_is_not_cleared`) -- that is a
    refusal, not a download failure, so it must map to exit 2 ("refused before anything is
    opened", A-C4 ¶2), never surface as an uncaught exception out of `main()`."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, dataset_key, states, levels=None):
        raise PermissionError(f"{dataset_key} is blocked; loads are refused (spec §1 licensing gate)")

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 2
    err = capsys.readouterr().err
    assert "acs5" in err and "refused" in err


# --- acs --levels (Task 6, D-NS4) -------------------------------------------------------------

def test_cmd_acs_passes_a_levels_filter_through(scratch_dsn, monkeypatch):
    """The CLI's own half of D-NS4: `census_load.py acs --levels 860` loads the one level, so the
    ZCTA pull can be run on its own instead of re-running six geographies for six states."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states, levels=None):
        captured["levels"] = levels
        return 1

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5", "--levels", "860"]) == 0

    assert captured["levels"] == ["860"]


def test_cmd_acs_accepts_more_than_one_level(scratch_dsn, monkeypatch):
    """`nargs="+"`: the flag is a list, so an operator can reload two geographies together."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states, levels=None):
        captured["levels"] = levels
        return 1

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5", "--levels", "860", "160"]) == 0

    assert captured["levels"] == ["860", "160"]


def test_cmd_acs_defaults_to_every_level(scratch_dsn, monkeypatch):
    """Omitting the flag must leave the existing load exactly as it was: `levels=None`, which is
    `acs.load`'s "every geography" arm (`tests/census/test_acs.py
    ::test_load_without_a_levels_filter_still_fetches_every_geography` proves what that arm does)."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}

    # `**kwargs`, not `levels=None`: a fake with its own default would report `None` whether or
    # not `cmd_acs` passed the argument at all, which is a gate that cannot fail. This one sees
    # exactly what was handed over.
    def fake_load(conn, client_factory, dataset_key, states, **kwargs):
        captured["kwargs"] = kwargs
        return 1

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 0

    assert captured["kwargs"] == {"levels": None}


# --- cbp/zbp/bds subcommands (Task A6) --------------------------------------------------------
# The three plain industry loaders share one shape with `acs`'s single-dataset call (no
# `--dataset` list): success, `DATABASE_URL` missing, the database unreachable, and the loader's
# three exception arms (`PermissionError` -> 2, `CensusHTTPError` -> 4, `VariableMissing` -> 5).

def test_cmd_cbp_queries_market_state_and_prints_row_count(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, states):
        captured["states"] = list(states)
        return 42

    monkeypatch.setattr(census_cbp, "load", fake_load)

    assert census_load.main(["cbp"]) == 0

    # market_state seeds six states (017_census_registry.sql; A-C0 P10 / A-C1 (5)).
    assert captured["states"] == ["06", "08", "12", "13", "36", "48"]
    assert "cbp: 42 rows" in capsys.readouterr().out


def test_cmd_cbp_returns_two_without_a_database_url(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert census_load.main(["cbp"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cmd_cbp_returns_three_when_the_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

    assert census_load.main(["cbp"]) == 3
    assert "database unreachable" in capsys.readouterr().err


def test_cmd_cbp_builds_the_client_factory_from_the_required_key_and_contact(scratch_dsn, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "distinctive-key-123")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "distinctive-contact@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, states):
        client = client_factory(object())  # CensusClient's constructor never inspects `ds`
        captured["api_key"] = client.api_key
        captured["contact"] = client.contact
        client.close()
        return 0

    monkeypatch.setattr(census_cbp, "load", fake_load)

    assert census_load.main(["cbp"]) == 0

    assert captured["api_key"] == "distinctive-key-123"
    assert captured["contact"] == "distinctive-contact@vinfoundation.example.org"


def test_cmd_cbp_returns_two_when_licence_gated(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states):
        raise PermissionError("cbp is blocked; loads are refused (spec §1 licensing gate)")

    monkeypatch.setattr(census_cbp, "load", fake_load)

    assert census_load.main(["cbp"]) == 2
    assert "cbp refused" in capsys.readouterr().err


def test_cmd_cbp_returns_four_when_the_download_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import CensusHTTPError

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states):
        raise CensusHTTPError(500, "https://api.census.gov/data/2022/cbp?key=SECRET")

    monkeypatch.setattr(census_cbp, "load", fake_load)

    assert census_load.main(["cbp"]) == 4
    err = capsys.readouterr().err
    assert "cbp download failed" in err and "SECRET" not in err


def test_cmd_cbp_returns_five_when_validation_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import VariableMissing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states):
        raise VariableMissing(["ESTAB"])

    monkeypatch.setattr(census_cbp, "load", fake_load)

    assert census_load.main(["cbp"]) == 5
    err = capsys.readouterr().err
    assert "cbp failed validation" in err and "ESTAB" in err


def test_cmd_zbp_queries_market_state_and_prints_row_count(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, states):
        captured["states"] = list(states)
        return 18

    monkeypatch.setattr(census_zbp, "load", fake_load)

    assert census_load.main(["zbp"]) == 0

    assert captured["states"] == ["06", "08", "12", "13", "36", "48"]
    assert "zbp: 18 rows" in capsys.readouterr().out


def test_cmd_zbp_returns_two_without_a_database_url(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert census_load.main(["zbp"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cmd_zbp_returns_three_when_the_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

    assert census_load.main(["zbp"]) == 3
    assert "database unreachable" in capsys.readouterr().err


def test_cmd_zbp_builds_the_client_factory_from_the_required_key_and_contact(scratch_dsn, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "distinctive-key-123")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "distinctive-contact@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, states):
        client = client_factory(object())
        captured["api_key"] = client.api_key
        captured["contact"] = client.contact
        client.close()
        return 0

    monkeypatch.setattr(census_zbp, "load", fake_load)

    assert census_load.main(["zbp"]) == 0

    assert captured["api_key"] == "distinctive-key-123"
    assert captured["contact"] == "distinctive-contact@vinfoundation.example.org"


def test_cmd_zbp_returns_two_when_licence_gated(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states):
        raise PermissionError("zbp is blocked; loads are refused (spec §1 licensing gate)")

    monkeypatch.setattr(census_zbp, "load", fake_load)

    assert census_load.main(["zbp"]) == 2
    assert "zbp refused" in capsys.readouterr().err


def test_cmd_zbp_returns_four_when_the_download_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import CensusHTTPError

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states):
        raise CensusHTTPError(500, "https://api.census.gov/data/2022/cbp?key=SECRET")

    monkeypatch.setattr(census_zbp, "load", fake_load)

    assert census_load.main(["zbp"]) == 4
    err = capsys.readouterr().err
    assert "zbp download failed" in err and "SECRET" not in err


def test_cmd_zbp_returns_five_when_validation_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import VariableMissing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states):
        raise VariableMissing(["ESTAB"])

    monkeypatch.setattr(census_zbp, "load", fake_load)

    assert census_load.main(["zbp"]) == 5
    err = capsys.readouterr().err
    assert "zbp failed validation" in err and "ESTAB" in err


def test_cmd_zbp_returns_two_when_geo_area_has_no_zctas_yet(scratch_dsn, monkeypatch, capsys):
    """A-C6: `zbp` cannot run before A4's TIGER load has bounded the market states' ZCTAs --
    `zbp.MissingBoundaries` is a refusal (exit 2), naming the prerequisite, like a licence gate."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states):
        raise census_zbp.MissingBoundaries("zbp needs the market states' ZCTAs in geo_area — run 'census_load.py tiger' first")

    monkeypatch.setattr(census_zbp, "load", fake_load)

    assert census_load.main(["zbp"]) == 2
    err = capsys.readouterr().err
    assert "zbp refused" in err and "census_load.py tiger" in err


def test_cmd_bds_requires_a_year_and_prints_row_count(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, states, *, year):
        captured["states"] = list(states)
        captured["year"] = year
        return 6

    monkeypatch.setattr(census_bds, "load", fake_load)

    assert census_load.main(["bds", "--year", "2022"]) == 0

    assert captured["states"] == ["06", "08", "12", "13", "36", "48"]
    assert captured["year"] == 2022
    assert "bds 2022: 6 rows" in capsys.readouterr().out


def test_cmd_bds_returns_two_without_a_database_url(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert census_load.main(["bds", "--year", "2022"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cmd_bds_returns_three_when_the_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

    assert census_load.main(["bds", "--year", "2022"]) == 3
    assert "database unreachable" in capsys.readouterr().err


def test_cmd_bds_builds_the_client_factory_from_the_required_key_and_contact(scratch_dsn, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "distinctive-key-123")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "distinctive-contact@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, states, *, year):
        client = client_factory(object())
        captured["api_key"] = client.api_key
        captured["contact"] = client.contact
        client.close()
        return 0

    monkeypatch.setattr(census_bds, "load", fake_load)

    assert census_load.main(["bds", "--year", "2022"]) == 0

    assert captured["api_key"] == "distinctive-key-123"
    assert captured["contact"] == "distinctive-contact@vinfoundation.example.org"


def test_cmd_bds_returns_two_when_licence_gated(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states, *, year):
        raise PermissionError("bds is blocked; loads are refused (spec §1 licensing gate)")

    monkeypatch.setattr(census_bds, "load", fake_load)

    assert census_load.main(["bds", "--year", "2022"]) == 2
    assert "bds refused" in capsys.readouterr().err


def test_cmd_bds_returns_four_when_the_download_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import CensusHTTPError

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states, *, year):
        raise CensusHTTPError(500, "https://api.census.gov/data/timeseries/bds?key=SECRET")

    monkeypatch.setattr(census_bds, "load", fake_load)

    assert census_load.main(["bds", "--year", "2022"]) == 4
    err = capsys.readouterr().err
    assert "bds download failed" in err and "SECRET" not in err


def test_cmd_bds_returns_five_when_validation_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import VariableMissing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states, *, year):
        raise VariableMissing(["FIRM"])

    monkeypatch.setattr(census_bds, "load", fake_load)

    assert census_load.main(["bds", "--year", "2022"]) == 5
    err = capsys.readouterr().err
    assert "bds failed validation" in err and "FIRM" in err


# --- qwi subcommand (Task A6) -------------------------------------------------------------------
# qwi differs from the other three: `--year`/`--quarter` are optional and, when either is
# omitted, resolved through `qwi.latest_available` before `qwi.load` runs; the licence gate is
# checked directly against the registry (not through `qwi.load`'s own identical check) so a
# blocked dataset is refused before `latest_available`'s probe, not after; and a successful load
# always calls `qwi.trim`.

def test_cmd_qwi_loads_a_given_quarter_without_resolving_latest(scratch_dsn, monkeypatch, capsys):
    captured: dict = {}

    def fake_load(conn, client_factory, states, *, year, quarter):
        captured["states"] = list(states)
        captured["year"], captured["quarter"] = year, quarter
        return 6

    def fake_trim(conn, keep=20):
        captured["trimmed_keep_default"] = keep
        return 3

    def fake_latest_available(client, state, *, today):
        raise AssertionError("latest_available must not run when --year/--quarter are both given")

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(census_qwi, "load", fake_load)
    monkeypatch.setattr(census_qwi, "trim", fake_trim)
    monkeypatch.setattr(census_qwi, "latest_available", fake_latest_available)

    assert census_load.main(["qwi", "--year", "2024", "--quarter", "4"]) == 0

    assert captured["states"] == ["06", "08", "12", "13", "36", "48"]
    assert captured["year"] == 2024 and captured["quarter"] == 4
    assert captured["trimmed_keep_default"] == 20
    out = capsys.readouterr().out
    assert "qwi 2024Q4: 6 rows (3 trimmed)" in out


def test_cmd_qwi_resolves_the_latest_available_quarter_when_omitted(scratch_dsn, monkeypatch, capsys):
    captured: dict = {}

    def fake_latest_available(client, state, *, today):
        captured["state"] = state
        captured["today"] = today
        return (2024, 4)

    def fake_load(conn, client_factory, states, *, year, quarter):
        captured["year"], captured["quarter"] = year, quarter
        return 6

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(census_qwi, "latest_available", fake_latest_available)
    monkeypatch.setattr(census_qwi, "load", fake_load)
    monkeypatch.setattr(census_qwi, "trim", lambda conn, keep=20: 0)

    assert census_load.main(["qwi"]) == 0

    assert captured["state"] == "06"  # states[0], market_state's first row
    assert captured["year"] == 2024 and captured["quarter"] == 4
    assert "qwi 2024Q4: 6 rows (0 trimmed)" in capsys.readouterr().out


def test_cmd_qwi_returns_two_without_a_database_url(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert census_load.main(["qwi", "--year", "2024", "--quarter", "4"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cmd_qwi_returns_three_when_the_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

    assert census_load.main(["qwi", "--year", "2024", "--quarter", "4"]) == 3
    assert "database unreachable" in capsys.readouterr().err


def test_cmd_qwi_returns_two_when_licence_gated_before_any_probe(scratch_dsn, monkeypatch, capsys):
    """The gate is checked directly, before `latest_available` -- neither it nor `load` may run
    for a blocked dataset (spec §1), including on the auto-resolve path (`--year`/`--quarter`
    both omitted here)."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    conn = census_load._conn(scratch_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'qwi'")
    finally:
        conn.close()

    def fail(*a, **k):
        raise AssertionError("a blocked dataset must never be probed or loaded")

    monkeypatch.setattr(census_qwi, "latest_available", fail)
    monkeypatch.setattr(census_qwi, "load", fail)

    assert census_load.main(["qwi"]) == 2
    err = capsys.readouterr().err
    assert "qwi refused" in err and "blocked" in err


def test_cmd_qwi_returns_four_when_resolving_the_latest_quarter_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import CensusHTTPError

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_latest_available(client, state, *, today):
        raise CensusHTTPError(500, "https://api.census.gov/data/timeseries/qwi/sa?key=SECRET")

    monkeypatch.setattr(census_qwi, "latest_available", fake_latest_available)

    assert census_load.main(["qwi"]) == 4
    err = capsys.readouterr().err
    assert "qwi download failed" in err and "SECRET" not in err


def test_cmd_qwi_returns_five_when_resolving_the_latest_quarter_fails_validation(scratch_dsn, monkeypatch, capsys):
    """Mi1 (A6 review): `latest_available` raises `VariableMissing` (not `CensusHTTPError`) when
    a 200 response is missing the `Emp` column -- a narrow but real schema-drift case that must
    map to exit 5, not propagate as an uncaught exception."""
    from app.census.client import VariableMissing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_latest_available(client, state, *, today):
        raise VariableMissing(["Emp"])

    monkeypatch.setattr(census_qwi, "latest_available", fake_latest_available)

    assert census_load.main(["qwi"]) == 5
    err = capsys.readouterr().err
    assert "qwi validation failed" in err and "Emp" in err


def test_cmd_qwi_returns_two_when_the_load_itself_is_licence_gated(scratch_dsn, monkeypatch, capsys):
    """I1 (A6 review): defense-in-depth for a live TOCTOU window -- an admin flips
    `license_status` mid-run via a separate connection while a long, six-state QWI load is in
    flight -- `qwi.load`'s own `PermissionError` must map to exit 2 here too, not propagate."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states, *, year, quarter):
        raise PermissionError("qwi is blocked; loads are refused (spec §1 licensing gate)")

    monkeypatch.setattr(census_qwi, "load", fake_load)

    assert census_load.main(["qwi", "--year", "2024", "--quarter", "4"]) == 2
    assert "qwi refused" in capsys.readouterr().err


def test_cmd_qwi_returns_four_when_the_load_itself_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import CensusHTTPError

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states, *, year, quarter):
        raise CensusHTTPError(500, "https://api.census.gov/data/timeseries/qwi/sa?key=SECRET")

    monkeypatch.setattr(census_qwi, "load", fake_load)

    assert census_load.main(["qwi", "--year", "2024", "--quarter", "4"]) == 4
    err = capsys.readouterr().err
    assert "qwi download failed" in err and "SECRET" not in err


def test_cmd_qwi_returns_five_when_validation_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import VariableMissing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, states, *, year, quarter):
        raise VariableMissing(["Emp"])

    monkeypatch.setattr(census_qwi, "load", fake_load)

    assert census_load.main(["qwi", "--year", "2024", "--quarter", "4"]) == 5
    err = capsys.readouterr().err
    assert "qwi failed validation" in err and "Emp" in err


def test_cmd_qwi_refuses_with_a_named_prerequisite_when_market_state_is_empty(scratch_dsn, monkeypatch, capsys):
    """m5 (controller amendment A-C11 (6)): resolving the latest published quarter indexes
    `states[0]` -- an empty `market_state` (unreachable today; `017_census_registry.sql` seeds six
    rows and nothing deletes them, but the CLI must not depend on that forever) gave a bare
    `IndexError` and exit 1 instead of a named refusal."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")  # gitleaks:allow — synthetic fixture, not a credential
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    conn = census_load._conn(scratch_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM market_state")
    finally:
        conn.close()
    monkeypatch.setattr(census_qwi, "latest_available", lambda *a, **kw: pytest.fail("must not resolve a quarter with no states"))

    assert census_load.main(["qwi"]) == 2
    err = capsys.readouterr().err
    assert "qwi refused" in err and "market_state" in err


def test_normalize_dsn_handles_the_legacy_postgres_scheme_and_asyncpg():
    assert census_load.normalize_dsn("postgres://u:p@h/db") == "postgresql://u:p@h/db"
    assert census_load.normalize_dsn("postgresql+asyncpg://u:p@h/db") == "postgresql://u:p@h/db"
    assert census_load.normalize_dsn("postgresql://u:p@h/db") == "postgresql://u:p@h/db"


def test_conn_normalises_a_legacy_postgres_scheme_dsn(scratch_dsn):
    """`_conn()` must accept the same `postgres://` scheme Railway's PostGIS template hands
    out (scripts/migrate.py's own normalize_dsn docstring), not just `postgresql://`."""
    legacy = "postgres://" + scratch_dsn.split("://", 1)[1]
    conn = census_load._conn(legacy)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        conn.close()


def test_the_main_guard_is_covered(monkeypatch):
    """runpy re-executes the file in THIS process with __name__ == "__main__", so pytest-cov
    sees the guard (the pattern tests/scripts/test_seed_listings.py already uses)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(sys, "argv", ["census_load.py", "tiger"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "census_load.py"), run_name="__main__")
    assert exc.value.code == 2


# --- activate subcommand (Task A7) ------------------------------------------------------------
# `activate` never touches the Census API -- no `CENSUS_API_KEY`/`CENSUS_CONTACT_EMAIL` gate, no
# `market_state` query, no HTTP client -- so it shares only two arms with the load subcommands
# above (DATABASE_URL missing, database unreachable) plus its own success and refusal arms.
# `app.census.vintage.activate` itself is exercised at 100 % branch by `tests/census/test_vintage
# .py` against a real database; this file, per its own docstring, tests only the CLI's wiring, so
# `vintage.activate` is monkeypatched throughout exactly as every other loader above is.

def test_cmd_activate_calls_vintage_activate_and_prints_the_report(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    captured: dict = {}

    def fake_activate(conn, dataset_key, vint, by, *, force=False, note=None):
        captured["dataset_key"] = dataset_key
        captured["vint"] = vint
        captured["by"] = by
        captured["force"] = force
        captured["note"] = note
        return census_vintage.Report(dataset_key, vint, None, 10, 0, None, "succeeded", note)

    monkeypatch.setattr(census_vintage, "activate", fake_activate)

    assert census_load.main(["activate", "acs5", "2019\u20132023", "--by", "john"]) == 0

    assert captured == {"dataset_key": "acs5", "vint": "2019\u20132023", "by": "john", "force": False, "note": None}
    out = capsys.readouterr().out
    assert "acs5" in out and "2019\u20132023" in out and "now active" in out


def test_cmd_activate_passes_a_given_note_through_without_force(scratch_dsn, monkeypatch):
    """`--note` is optional without `--force` (A-C7 concern 1) -- an operator can still record a
    routine activation's reason even when nothing forced it."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    captured: dict = {}

    def fake_activate(conn, dataset_key, vint, by, *, force=False, note=None):
        captured["note"] = note
        return census_vintage.Report(dataset_key, vint, None, 10, 0, None, "succeeded", note)

    monkeypatch.setattr(census_vintage, "activate", fake_activate)

    assert census_load.main(["activate", "acs5", "2019\u20132023", "--by", "john", "--note", "routine refresh"]) == 0

    assert captured["note"] == "routine refresh"


def test_cmd_activate_passes_the_force_flag_and_required_note_through(scratch_dsn, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    captured: dict = {}

    def fake_activate(conn, dataset_key, vint, by, *, force=False, note=None):
        captured["force"] = force
        captured["note"] = note
        return census_vintage.Report(dataset_key, vint, "2018\u20132022", 40, 100, 0.4, "succeeded", note)

    monkeypatch.setattr(census_vintage, "activate", fake_activate)

    assert census_load.main(
        ["activate", "acs5", "2019\u20132023", "--by", "john", "--force", "--note", "reviewed override"]
    ) == 0

    assert captured["force"] is True
    assert captured["note"] == "reviewed override"


def test_cmd_activate_requires_note_when_forced(capsys):
    """A-C7 concern 1: `--note` is REQUIRED when `--force` is given -- argparse's own error
    (exit 2), before the database or `vintage.activate` is ever touched."""
    with pytest.raises(SystemExit) as exc:
        census_load.main(["activate", "acs5", "2019\u20132023", "--by", "john", "--force"])
    assert exc.value.code == 2
    assert "--note" in capsys.readouterr().err


def test_cmd_activate_marks_a_forced_activation_in_the_confirmation_line(scratch_dsn, monkeypatch, capsys):
    """m2 (A7 review Minor 2): the confirmation line itself must say a forced override happened,
    not just the dataclass repr printed above it."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)

    def fake_activate(conn, dataset_key, vint, by, *, force=False, note=None):
        return census_vintage.Report(dataset_key, vint, "2018\u20132022", 40, 100, 0.4, "succeeded", note)

    monkeypatch.setattr(census_vintage, "activate", fake_activate)

    assert census_load.main(
        ["activate", "acs5", "2019\u20132023", "--by", "john", "--force", "--note", "reviewed override"]
    ) == 0

    out = capsys.readouterr().out
    assert "(forced)" in out


def test_cmd_activate_does_not_mark_an_unforced_activation(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)

    def fake_activate(conn, dataset_key, vint, by, *, force=False, note=None):
        return census_vintage.Report(dataset_key, vint, None, 10, 0, None, "succeeded", note)

    monkeypatch.setattr(census_vintage, "activate", fake_activate)

    assert census_load.main(["activate", "acs5", "2019\u20132023", "--by", "john"]) == 0

    out = capsys.readouterr().out
    assert "(forced)" not in out


def test_cmd_activate_returns_two_without_a_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert census_load.main(["activate", "acs5", "2019\u20132023", "--by", "john"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cmd_activate_returns_three_when_the_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

    assert census_load.main(["activate", "acs5", "2019\u20132023", "--by", "john"]) == 3
    assert "database unreachable" in capsys.readouterr().err


def test_cmd_activate_returns_five_when_refused(scratch_dsn, monkeypatch, capsys):
    def fake_activate(conn, dataset_key, vint, by, *, force=False, note=None):
        raise census_vintage.ActivationRefused(
            "row count ratio 0.40 vs active vintage 2018\u20132022 is outside [0.8, 1.25]; pass force=True after review"
        )

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(census_vintage, "activate", fake_activate)

    assert census_load.main(["activate", "acs5", "2019\u20132023", "--by", "john"]) == 5
    err = capsys.readouterr().err
    assert "activation refused" in err and "ratio" in err


def test_cmd_activate_rejects_an_unknown_dataset_key(capsys):
    """`dataset_key` is drawn from `vintage.TABLE_FOR`, the same closed set `qa()`/`activate()`
    index into -- an unknown key is refused by argparse itself (exit 2, "refused before anything
    is opened") rather than reaching a bare `KeyError` inside `vintage.qa`."""
    with pytest.raises(SystemExit) as exc:
        census_load.main(["activate", "not_a_real_dataset", "2019\u20132023", "--by", "john"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_cmd_activate_requires_by(capsys):
    with pytest.raises(SystemExit) as exc:
        census_load.main(["activate", "acs5", "2019\u20132023"])
    assert exc.value.code == 2


# --- materialize subcommand (Task B4b) -----------------------------------------------------------
# `materialize` never touches the Census API either -- like `activate`, it shares only the
# DATABASE_URL/unreachable/post-connect-database-error arms with the keyed loaders above. Unlike
# `activate`, it DOES need Redis (the listing cache-version bump), so these tests use the `redis`
# fixture (tests/conftest.py) -- the fakeredis double that already patches `app.cache`'s
# factories -- rather than reaching a real Redis.

def test_cmd_materialize_with_a_listing_id_calls_materialize_listing_and_prints_the_row_count(scratch_dsn, redis, monkeypatch, capsys):
    from app.census import materialize as census_materialize

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    captured: dict = {}

    def fake(conn, r, listing_id):
        captured["listing_id"] = listing_id
        captured["redis"] = r
        return 18

    monkeypatch.setattr(census_materialize, "materialize_listing", fake)

    assert census_load.main(["materialize", "--listing", "some-listing-id"]) == 0

    assert captured["listing_id"] == "some-listing-id"
    assert captured["redis"] is redis
    assert "some-listing-id: 18 rows" in capsys.readouterr().out


def test_cmd_materialize_without_a_listing_materialises_every_geocoded_listing(scratch_dsn, redis, monkeypatch, capsys):
    from app.census import materialize as census_materialize

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(census_materialize, "materialize_all", lambda conn, r: {"a": 3, "b": 5})

    assert census_load.main(["materialize"]) == 0

    out = capsys.readouterr().out
    assert "a: 3 rows" in out and "b: 5 rows" in out
    assert "2 listing(s) materialised" in out


def test_cmd_materialize_returns_two_when_no_active_vintage_is_ready(scratch_dsn, redis, monkeypatch, capsys):
    """A missing active acs5/tiger_cb vintage (`app.census.materialize._Ctx`'s own
    `RuntimeError`) is "refused before anything is opened" in spirit -- an operator has not
    activated a required dataset yet -- so it maps to exit 2, the same code every other
    licence-gate/missing-prerequisite refusal in this file already uses."""
    from app.census import materialize as census_materialize

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)

    def fake(conn, r):
        raise RuntimeError("acs5 and tiger_cb must have active vintages before materialising")

    monkeypatch.setattr(census_materialize, "materialize_all", fake)

    assert census_load.main(["materialize"]) == 2
    assert "materialize refused" in capsys.readouterr().err


def test_cmd_materialize_returns_two_without_a_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert census_load.main(["materialize"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cmd_materialize_returns_three_when_the_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

    assert census_load.main(["materialize"]) == 3
    assert "database unreachable" in capsys.readouterr().err


# --- every cmd_* closes its connection and maps a post-connect database error (A-C7 (7)) --------
# I12 / an A-C4 addendum: a `psycopg2.Error` raised AFTER `_conn()` succeeds (the realistic case
# is `UndefinedTable`, an unmigrated database) used to escape as an uncaught traceback (exit 1)
# and never closed the connection. `app.census.vintage.activate` (exercised at 100% branch by
# `tests/census/test_vintage.py` against a real database) is the only subcommand whose OWN body
# never issues a `conn.cursor()` call directly -- it delegates to `vintage.qa`/`vintage.activate`,
# which do -- so monkeypatching `census_load._conn` to hand back a connection whose cursor always
# raises reaches every subcommand's first database statement uniformly, real or delegated.

# --- geocode subcommand (Task B9) ---------------------------------------------------------------

def test_cmd_geocode_resolves_listing_with_no_practice_location_row(scratch_dsn, monkeypatch, capsys):
    """Task B9, case (a): a listing with no practice_location row is resolved, its catchment
    built and its market_metric rows written. Assert all three exist afterwards with row counts."""
    from tests.census.listing_fixtures import make_listing


    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    conn = census_load._conn(scratch_dsn)
    try:
        lid = make_listing(conn)
        # Seed geo_area and active_vintage
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid) VALUES
                     ('48491020355','140','2023','Census Tract 203.55','48','491','48491',
                      ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)),
                      ST_SetSRID(ST_MakePoint(-97.8,30.55),4269)),
                     ('78613','860','2023','ZCTA5 78613',NULL,NULL,NULL,
                      ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)),
                      ST_SetSRID(ST_MakePoint(-97.8,30.55),4269)),
                     ('4813552','160','2023','Cedar Park city','48',NULL,'48',
                      ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)),
                      ST_SetSRID(ST_MakePoint(-97.8,30.55),4269))"""
            )
            cur.execute(
                "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)",
                ("tiger_cb", "2023", "test"),
            )
            cur.execute(
                "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)",
                ("acs5", "2019\u20132023", "test"),
            )
    finally:
        conn.close()

    # Skip the network call by mocking geocode.resolve to write to DB directly
    from app.census import geocode as census_geocode

    def mock_resolve(conn, gc, listing_id):
        # Return Location as if geocode succeeded; resolve will write to DB
        loc = census_geocode.Location(listing_id, "rooftop", 30.55, -97.8, "48491020355", "48491", "4813552", "78613", "12420")
        # Write to practice_location directly
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO practice_location
                     (listing_id, address_hash, point, tract_geoid, county_geoid, place_geoid, zcta_geoid, cbsa_geoid,
                      geo_precision, geocoded_at, geocoder_vintage)
                   VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4269), %s, %s, %s, %s, %s, %s, now(), %s)
                   ON CONFLICT (listing_id) DO UPDATE SET
                     point = EXCLUDED.point, tract_geoid = EXCLUDED.tract_geoid, county_geoid = EXCLUDED.county_geoid,
                     place_geoid = EXCLUDED.place_geoid, zcta_geoid = EXCLUDED.zcta_geoid, cbsa_geoid = EXCLUDED.cbsa_geoid,
                     geo_precision = EXCLUDED.geo_precision, geocoded_at = now(), geocoder_vintage = EXCLUDED.geocoder_vintage""",
                (listing_id, "hash1", loc.lng, loc.lat, loc.tract_geoid, loc.county_geoid, loc.place_geoid, loc.zcta_geoid, loc.cbsa_geoid, "rooftop", "Current_Current"),
            )
        return loc

    monkeypatch.setattr(census_geocode, "resolve", mock_resolve)

    assert census_load.main(["geocode", "--listing", lid]) == 0

    # Verify practice_location, catchment, and market_metric rows exist
    conn = census_load._conn(scratch_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT geo_precision FROM practice_location WHERE listing_id=%s", (lid,))
            assert cur.fetchone() is not None
            cur.execute("SELECT COUNT(*) FROM practice_catchment WHERE listing_id=%s", (lid,))
            catchment_count = cur.fetchone()[0]
            assert catchment_count > 0
            cur.execute("SELECT COUNT(*) FROM market_metric WHERE listing_id=%s", (lid,))
            metric_count = cur.fetchone()[0]
            assert metric_count > 0
    finally:
        conn.close()

    out = capsys.readouterr().out
    assert lid in out
    assert "1 listing(s) geocoded" in out


def test_cmd_geocode_skips_listing_with_practice_location_row(scratch_dsn, monkeypatch, capsys):
    """Task B9, case (b): a listing that already has a practice_location row is SKIPPED and
    the output says so."""
    from tests.census.listing_fixtures import make_listing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    conn = census_load._conn(scratch_dsn)
    try:
        lid = make_listing(conn)
        with conn.cursor() as cur:
            # Add a practice_location row
            cur.execute(
                "INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoder_vintage, geocoded_at) "
                "VALUES (%s, %s, %s, %s, now())",
                (lid, "hash1", "rooftop", "Current_Current"),
            )
    finally:
        conn.close()

    # Run with no argument - should skip this one
    assert census_load.main(["geocode"]) == 0

    out = capsys.readouterr().out
    assert "0 listing(s) geocoded" in out


def test_cmd_geocode_force_re_geocodes_existing_listing(scratch_dsn, monkeypatch, capsys):
    """Task B9, case (c): --force re-resolves one that already has a practice_location row."""
    from app.census import geocode as census_geocode
    from tests.census.listing_fixtures import make_listing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    conn = census_load._conn(scratch_dsn)
    try:
        lid = make_listing(conn)
        with conn.cursor() as cur:
            # Seed geo_area and active_vintage
            cur.execute(
                """INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid) VALUES
                     ('48491020355','140','2023','Census Tract 203.55','48','491','48491',
                      ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)),
                      ST_SetSRID(ST_MakePoint(-97.8,30.55),4269))"""
            )
            cur.execute(
                "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)",
                ("tiger_cb", "2023", "test"),
            )
            cur.execute(
                "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)",
                ("acs5", "2019\u20132023", "test"),
            )
            # Add an existing practice_location row
            cur.execute(
                "INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoder_vintage, geocoded_at) "
                "VALUES (%s, %s, %s, %s, now())",
                (lid, "old_hash", "rooftop", "Current_Current"),
            )
    finally:
        conn.close()

    # Mock geocode.resolve to skip HTTP and write directly
    def mock_resolve(conn, gc, listing_id):
        loc = census_geocode.Location(listing_id, "rooftop", 30.55, -97.8, "48491020355", "48491", None, None, None)
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE practice_location SET point = ST_SetSRID(ST_MakePoint(%s, %s), 4269),
                     tract_geoid = %s, county_geoid = %s, geo_precision = %s, geocoded_at = now()
                   WHERE listing_id = %s""",
                (loc.lng, loc.lat, loc.tract_geoid, loc.county_geoid, "rooftop", listing_id),
            )
        return loc

    monkeypatch.setattr(census_geocode, "resolve", mock_resolve)

    # Run with --force
    assert census_load.main(["geocode", "--force"]) == 0

    out = capsys.readouterr().out
    assert "1 listing(s) geocoded" in out


def test_cmd_geocode_refuses_when_tiger_cb_vintage_missing(scratch_dsn, monkeypatch, capsys):
    """Task B9, case (d): tiger_cb has no active vintage → exit 2 with named reason and
    nothing written."""
    from tests.census.listing_fixtures import make_listing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    conn = census_load._conn(scratch_dsn)
    try:
        lid = make_listing(conn)
    finally:
        conn.close()

    assert census_load.main(["geocode", "--listing", lid]) == 2
    err = capsys.readouterr().err
    assert "tiger_cb" in err
    assert "refused" in err


def test_cmd_geocode_nothing_to_geocode_exits_zero(scratch_dsn, monkeypatch, capsys):
    """Task B9: when geocode runs with no argument and every listing already has a
    practice_location row (nothing to do), it exits 0, not 2. Success means 'nothing happened
    that needed doing', not 'I refused to start'."""
    from tests.census.listing_fixtures import make_listing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    conn = census_load._conn(scratch_dsn)
    try:
        lid = make_listing(conn)
        with conn.cursor() as cur:
            # Add practice_location so there's nothing to geocode
            cur.execute(
                "INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoder_vintage, geocoded_at) "
                "VALUES (%s, %s, %s, %s, now())",
                (lid, "hash1", "rooftop", "Current_Current"),
            )
    finally:
        conn.close()

    # Run with no argument when everything is done
    assert census_load.main(["geocode"]) == 0

    out = capsys.readouterr().out
    assert "0 listing(s) geocoded" in out


def test_cmd_geocode_missing_listing_exits_two(scratch_dsn, monkeypatch, capsys):
    """Task B9: a non-existent listing with --listing is exit 2, not a 404."""
    from uuid import uuid4

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)

    listing_id = str(uuid4())
    assert census_load.main(["geocode", "--listing", listing_id]) == 2
    err = capsys.readouterr().err
    assert "refused" in err or "no such listing" in err


def test_cmd_geocode_returns_two_without_a_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert census_load.main(["geocode"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cmd_geocode_returns_five_when_the_geocoder_cannot_resolve_a_listing(scratch_dsn, monkeypatch, capsys):
    """Task B9: a listing the ladder cannot place at all stops the run with exit 5, naming the
    listing, rather than leaving a half-geocoded inventory behind without saying so."""
    from app.census import geocode as census_geocode
    from tests.census.listing_fixtures import make_listing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    conn = census_load._conn(scratch_dsn)
    try:
        lid = make_listing(conn)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by)"
                " VALUES (%s, %s, now(), %s) ON CONFLICT (dataset_key) DO NOTHING",
                ("tiger_cb", "2023", "test"),
            )
    finally:
        conn.close()

    def refuse(conn, gc, listing_id):
        raise census_geocode.GeocodeFailed("every rung of the ladder missed")

    monkeypatch.setattr(census_geocode, "resolve", refuse)
    assert census_load.main(["geocode", "--listing", lid]) == 5
    err = capsys.readouterr().err
    assert lid in err and "geocoding failed" in err


def test_cmd_geocode_returns_two_when_the_active_vintage_lookup_raises(scratch_dsn, monkeypatch, capsys):
    """Task B9: `materialize.active_geo_vintage` raises RuntimeError when no boundary vintage is
    active. That is a refusal (exit 2) naming what to do, never an unhandled crash."""
    from app.census import geocode as census_geocode
    from app.census import materialize as census_materialize
    from tests.census.listing_fixtures import make_listing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    conn = census_load._conn(scratch_dsn)
    try:
        lid = make_listing(conn)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by)"
                " VALUES (%s, %s, now(), %s) ON CONFLICT (dataset_key) DO NOTHING",
                ("tiger_cb", "2023", "test"),
            )
    finally:
        conn.close()

    def resolve_ok(conn, gc, listing_id):
        loc = census_geocode.Location(listing_id, "rooftop", 30.55, -97.8, "48491020355", "48491", "4813552", "78613", "12420")
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO practice_location (listing_id, address_hash, point, geo_precision, geocoded_at, geocoder_vintage)"
                " VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4269), %s, now(), %s)"
                " ON CONFLICT (listing_id) DO NOTHING",
                (listing_id, "hash-vintage", loc.lng, loc.lat, "rooftop", "Current_Current"),
            )
        return loc

    def no_vintage(conn):
        raise RuntimeError("no active tiger_cb vintage")

    monkeypatch.setattr(census_geocode, "resolve", resolve_ok)
    monkeypatch.setattr(census_materialize, "active_geo_vintage", no_vintage)
    assert census_load.main(["geocode", "--listing", lid]) == 2
    assert "geocode refused" in capsys.readouterr().err


def test_cmd_geocode_returns_three_when_the_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

    assert census_load.main(["geocode"]) == 3
    assert "database unreachable" in capsys.readouterr().err


class _RaisingCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, *a, **k):
        raise psycopg2.errors.UndefinedTable('relation "market_state" does not exist\n')


class _RaisingConn:
    def __init__(self):
        self.close_calls = 0

    def cursor(self):
        return _RaisingCursor()

    def close(self):
        self.close_calls += 1


@pytest.mark.parametrize(
    "argv, env",
    [
        (["tiger"], {"CENSUS_CONTACT_EMAIL": "tech@vinfoundation.example.org"}),
        (["acs"], {"CENSUS_API_KEY": "the-key", "CENSUS_CONTACT_EMAIL": "tech@vinfoundation.example.org"}),
        (["cbp"], {"CENSUS_API_KEY": "the-key", "CENSUS_CONTACT_EMAIL": "tech@vinfoundation.example.org"}),
        (["zbp"], {"CENSUS_API_KEY": "the-key", "CENSUS_CONTACT_EMAIL": "tech@vinfoundation.example.org"}),
        (["bds", "--year", "2022"], {"CENSUS_API_KEY": "the-key", "CENSUS_CONTACT_EMAIL": "tech@vinfoundation.example.org"}),
        (["qwi", "--year", "2024", "--quarter", "4"], {"CENSUS_API_KEY": "the-key", "CENSUS_CONTACT_EMAIL": "tech@vinfoundation.example.org"}),
        (["activate", "acs5", "2019\u20132023", "--by", "john"], {}),
        (["geocode"], {}),
        (["materialize"], {}),
    ],
    ids=["tiger", "acs", "cbp", "zbp", "bds", "qwi", "activate", "geocode", "materialize"],
)
def test_every_subcommand_closes_its_connection_and_returns_three_on_a_post_connect_database_error(argv, env, redis, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder/placeholder")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    fake_conn = _RaisingConn()
    monkeypatch.setattr(census_load, "_conn", lambda dsn: fake_conn)

    assert census_load.main(argv) == 3

    err = capsys.readouterr().err
    assert "UndefinedTable" in err
    assert "market_state" not in err, "only the exception's TYPE may be printed, never its text (it can carry a DSN)"
    assert fake_conn.close_calls == 1
