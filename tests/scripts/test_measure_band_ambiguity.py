"""scripts/measure_band_ambiguity.py — D-C34's trigger for the tract toggle, as a number.

A reporting script: it reads `geo_metric` and `bands.py`, runs nowhere on the request path and
builds nothing."""
import runpy
import sys
from pathlib import Path

import psycopg2
import pytest

from scripts import measure_band_ambiguity as MB

ROOT = Path(__file__).resolve().parents[2]


def _metric(conn: psycopg2.extensions.connection, geo_id: str, level: str, value: float | None, moe: float | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, source_dataset, computed_at) "
            "VALUES (%s, %s, '2019\u20132023', 'median_hh_income', %s, 'usd', %s, 'acs5', now())",
            (geo_id, level, value, moe),
        )


def test_measure_reports_the_share_per_summary_level(conn: psycopg2.extensions.connection) -> None:
    _metric(conn, "78704", "860", 92150, 6420)    # measured, not ambiguous
    _metric(conn, "78745", "860", 92150, 9000)    # measured, ambiguous
    _metric(conn, "78702", "860", 92150, None)    # no margin — counted, never ambiguous
    _metric(conn, "78701", "860", None, None)     # no value at all
    _metric(conn, "48453000", "140", 92150, 9000)
    out = MB.measure(conn, "median_hh_income", "2019\u20132023")
    assert out["860"] == {"polygons": 4, "with_value": 3, "with_moe": 2, "ambiguous": 1}
    assert out["140"] == {"polygons": 1, "with_value": 1, "with_moe": 1, "ambiguous": 1}


def test_measure_reads_only_the_metric_and_vintage_it_was_asked_for(conn: psycopg2.extensions.connection) -> None:
    """The WHERE clause, not decoration: `geo_metric` holds three metrics at three levels and two
    vintages of `growth`'s inputs, and a share taken over all of them would mix a layer that can
    never be ambiguous (no published margin, D-NS17) into the denominator of one that can."""
    _metric(conn, "78704", "860", 92150, 9000)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, source_dataset, computed_at) "
            "VALUES ('4805000', '160', '2019\u20132023', 'population_growth_pct', 11.6, 'pct', NULL, 'acs5', now()), "
            "       ('78704', '860', '2014\u20132018', 'median_hh_income', 92150, 'usd', 9000, 'acs5_prior', now())"
        )
    assert MB.measure(conn, "median_hh_income", "2019\u20132023") == {
        "860": {"polygons": 1, "with_value": 1, "with_moe": 1, "ambiguous": 1}
    }


def test_measure_returns_nothing_when_the_table_is_empty(conn: psycopg2.extensions.connection) -> None:
    assert MB.measure(conn, "median_hh_income", "2019\u20132023") == {}


def test_main_prints_one_line_per_level(conn: psycopg2.extensions.connection, scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Both arms of the share: a level with margins reports a percentage of them, and a level
    where nothing carries a margin reports 0.0 % rather than dividing by zero. The second is not
    hypothetical — `growth` and `econ` carry no published margin at all (D-NS17), so a run asking
    for either sees exactly this shape."""
    _metric(conn, "78704", "860", 92150, 9000)
    _metric(conn, "48453000", "140", 92150, None)
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert MB.main(["--vintage", "2019\u20132023"]) == 0
    out = capsys.readouterr().out
    assert "860" in out and "100.0%" in out
    assert "140: 1 polygons, 1 with a value, 0 with a margin, 0 ambiguous (0.0% of those with a margin)" in out


def test_main_refuses_without_a_database_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert MB.main(["--vintage", "2019\u20132023"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_the_main_guard_is_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["measure_band_ambiguity.py", "--vintage", "2019\u20132023"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "measure_band_ambiguity.py"), run_name="__main__")
    assert exc.value.code == 2
