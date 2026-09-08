"""`scripts/census_load.py` -- the operator CLI (Task A4's `--tiger`; task A5 adds `acs`).

Runs inside the worker image (`railway run --service worker -- python scripts/census_load.py
tiger`) or locally against docker-compose; every subcommand is idempotent. This file tests the
CLI's OWN wiring -- argument parsing, the `market_state` query, the fail-closed key/contact
gates, the User-Agent/redirect settings the HTTP client is built with, and every error arm -- not
`app.census.tiger.load_boundaries`'s or `app.census.acs.load`'s own behaviour, which
`tests/census/test_tiger.py` and `tests/census/test_acs.py` already cover at 100 % branch.
Both are monkeypatched throughout so this suite never needs a real shapefile or a live Census
API response.

`acs`'s exit codes (A-C4 ¶2, as `tiger`'s already do): 0 done; 2 refused before anything is
opened (no `CENSUS_API_KEY`/`CENSUS_CONTACT_EMAIL`, or no `DATABASE_URL`); 3 database
unreachable; 4 a download/fetch failed (`CensusHTTPError`); 5 validation failed
(`VariableMissing` -- a response missing an expected variable, spec §4/¶12)."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from app.census import acs as census_acs
from app.census import tiger as census_tiger
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


# --- acs subcommand (Task A5) ---------------------------------------------------------------

def test_cmd_acs_queries_market_state_and_prints_measure_counts(scratch_dsn, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states):
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
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states):
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
    monkeypatch.setenv("CENSUS_API_KEY", "distinctive-key-123")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "distinctive-contact@vinfoundation.example.org")
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states):
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
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(settings, "s3_endpoint_url", None)
    monkeypatch.setattr(settings, "s3_bucket", None)
    monkeypatch.setattr(settings, "s3_access_key_id", None)
    monkeypatch.setattr(settings, "s3_secret_access_key", None)
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states):
        captured["archive"] = client_factory(object()).archive
        return 0

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 0

    assert captured["archive"] is None


def test_cmd_acs_passes_a_real_archive_once_s3_settings_are_configured(scratch_dsn, monkeypatch):
    from app.config import settings
    from app.storage import ObjectStore

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setattr(settings, "s3_endpoint_url", "http://s3.example.internal")
    monkeypatch.setattr(settings, "s3_bucket", "practice-match-data")
    monkeypatch.setattr(settings, "s3_access_key_id", "AKIDEXAMPLE")
    monkeypatch.setattr(settings, "s3_secret_access_key", "secretkey")
    captured: dict = {}

    def fake_load(conn, client_factory, dataset_key, states):
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
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.delenv("CENSUS_CONTACT_EMAIL", raising=False)
    with pytest.raises(SystemExit) as exc:
        census_load.main(["acs"])
    assert exc.value.code == 2
    assert "CENSUS_CONTACT_EMAIL" in capsys.readouterr().err


def test_cmd_acs_returns_two_without_a_database_url(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert census_load.main(["acs"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cmd_acs_returns_three_when_the_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

    assert census_load.main(["acs"]) == 3
    assert "database unreachable" in capsys.readouterr().err


def test_cmd_acs_returns_four_when_a_dataset_download_fails(scratch_dsn, monkeypatch, capsys):
    from app.census.client import CensusHTTPError

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, dataset_key, states):
        raise CensusHTTPError(500, "https://api.census.gov/data/2023/acs/acs5?key=SECRET")

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 4
    err = capsys.readouterr().err
    assert "acs5 download failed" in err and "SECRET" not in err


def test_cmd_acs_returns_five_when_a_dataset_fails_validation(scratch_dsn, monkeypatch, capsys):
    from app.census.client import VariableMissing

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, dataset_key, states):
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
    monkeypatch.setenv("CENSUS_API_KEY", "the-key")
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", "tech@vinfoundation.example.org")

    def fake_load(conn, client_factory, dataset_key, states):
        raise PermissionError(f"{dataset_key} is blocked; loads are refused (spec §1 licensing gate)")

    monkeypatch.setattr(census_acs, "load", fake_load)

    assert census_load.main(["acs", "--dataset", "acs5"]) == 2
    err = capsys.readouterr().err
    assert "acs5" in err and "refused" in err


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
