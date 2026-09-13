"""scripts/measure_boundary_caps.py — the tool the boundary caps were set from (Task CAP).

A reporting script: it reads `geo_area`/`geo_metric` through the ROUTE's own `_BOUNDARY_SQL`, runs
nowhere on the request path and builds nothing. What is worth testing is not the byte figures (they
are whatever the geometry is) but that the two modes AGREE, that the tool reuses the route's SQL
rather than a copy of it, and that every arm of the CLI is reachable.

A handful of small rectangles is enough for all of that, and is what a fixture can honestly hold.
"""
import runpy
import sys
from pathlib import Path

import psycopg2
import pytest

from app.api.market import SIMPLIFY_TIERS
from scripts import measure_boundary_caps as MC

ROOT = Path(__file__).resolve().parents[2]
#: Inside `ny-default-padded`, so the fixture answers the box the caps were measured against.
INSIDE = (-75.0, 40.0, -74.9, 40.1)


@pytest.fixture
def tracts(conn: psycopg2.extensions.connection) -> psycopg2.extensions.connection:
    """Four tracts in the New York default view, two of them carrying a median and a margin.

    Deliberately NOT all alike: `measure_tier`'s length arithmetic has a separate term for a null
    value, a null margin and a suppressed row, and a fixture where every row looked the same would
    let three of those terms be wrong without anything noticing.
    """
    w, s, _e, n = INSIDE
    with conn.cursor() as cur:
        for key, vintage in (("tiger_cb", "2023"), ("acs5", "2019\u20132023")):
            cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) "
                        "VALUES (%s,%s,now(),'test')", (key, vintage))
        for i in range(4):
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES "
                "(%s,'140','2023',%s,'36', ST_Multi(ST_MakeEnvelope(%s,%s,%s,%s,4269)), ST_Point(%s,%s,4269))",
                (f"3600000000{i}", f"Census Tract {i}", w + i * 0.01, s, w + i * 0.01 + 0.008, n, w, s),
            )
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
            "('36000000000','140','2019\u20132023','median_hh_income',92150,'usd',6420,false,NULL,'acs5',now()), "
            "('36000000001','140','2019\u20132023','median_hh_income',41000,'usd',NULL,true,'high_moe','acs5',now())"
        )
    return conn


def test_the_tool_runs_the_routes_own_sql_rather_than_a_copy_of_it() -> None:
    """The whole claim of this tool is that its numbers are the ROUTE's. That holds only while the
    SQL is the route's, so the substitution is asserted rather than trusted: every SQLAlchemy bind
    marker is rewritten and none is left behind to be sent to psycopg2 as literal text."""
    from app.api.market import _BOUNDARY_SQL

    assert "ST_SimplifyPreserveTopology" in MC._ROUTE_SQL
    assert "%(tol)s" in MC._ROUTE_SQL and "%(w)s" in MC._ROUTE_SQL
    assert ":tol" not in MC._ROUTE_SQL and ":geo_vintage" not in MC._ROUTE_SQL
    # …and it is a rewrite of the route's string, not a second copy that could drift from it.
    rewritten = _BOUNDARY_SQL
    for name in ("tol", "metric", "value_vintage", "level", "geo_vintage", "w", "s", "e", "n"):
        rewritten = rewritten.replace(f":{name}", f"%({name})s")
    assert MC._ROUTE_SQL == rewritten


def test_the_two_modes_agree_on_the_byte_total(tracts: psycopg2.extensions.connection) -> None:
    """`length` exists so a remote database is measured without pulling the geometry, and it is
    only worth having while it answers what `exact` answers. Tier 0 must agree EXACTLY — there is
    no simplification to be non-deterministic about — which is the check that caught the
    float-rendering term while the tool was being written."""
    p = MC.params(MC.BOXES["ny-default-padded"], 0.0, "140", "2023", "2019\u20132023", "median_hh_income")
    exact_features, exact_bytes, packed = MC.measure_tier(tracts, p, "exact")
    length_features, length_bytes, no_gzip = MC.measure_tier(tracts, p, "length")
    assert exact_features == length_features == 4
    assert exact_bytes == length_bytes
    assert packed is not None and 0 < packed < exact_bytes
    assert no_gzip is None, "length mode cannot know a compressed size and must not invent one"


def test_measure_box_walks_every_delivery_tier_in_the_routes_own_order(tracts: psycopg2.extensions.connection) -> None:
    rows = MC.measure_box(tracts, MC.BOXES["ny-default-padded"], "length", "140", "median_hh_income",
                          ("2023", "2019\u20132023"))
    assert [r["frac"] for r in rows] == list(SIMPLIFY_TIERS)
    # The tolerance is a fraction of the box's own longer span, which is what makes a tier mean the
    # same number of PIXELS at the zoom the box belongs to.
    span = max(MC.BOXES["ny-default-padded"][2] - MC.BOXES["ny-default-padded"][0],
               MC.BOXES["ny-default-padded"][3] - MC.BOXES["ny-default-padded"][1])
    assert rows[0]["tol"] == 0.0
    assert rows[-1]["tol"] == pytest.approx(span * SIMPLIFY_TIERS[-1])
    assert all(r["features"] == 4 for r in rows), "a tier must never drop a polygon to save bytes"


def test_a_box_with_nothing_in_it_reports_zero_features_and_only_the_envelope(tracts: psycopg2.extensions.connection) -> None:
    """The `COALESCE(SUM(...), 0)` arm: a box over open ocean is a legal question with an empty
    answer, and the tool must report the envelope's own bytes rather than crash on a null sum."""
    p = MC.params((-40.0, 20.0, -39.0, 21.0), 0.0, "140", "2023", "2019\u20132023", "median_hh_income")
    features, raw, _ = MC.measure_tier(tracts, p, "length")
    assert features == 0
    assert raw == MC.envelope_bytes(0) > 0


def test_the_sweep_reports_the_densest_window_first(tracts: psycopg2.extensions.connection) -> None:
    """`--sweep` is how the densest box `MAX_BBOX_DEG` admits was found. Ordering is the whole
    point of it, so it is asserted rather than the counts."""
    rows = MC.sweep(tracts, "140", "2023", step=4.0, top=3)
    assert rows, "the sweep found no window at all over a fixture that has tracts in it"
    assert [n for _lon, _lat, n in rows] == sorted((n for _lon, _lat, n in rows), reverse=True)
    assert rows[0][2] == 4


def test_active_vintages_reads_the_same_table_the_route_does(tracts: psycopg2.extensions.connection) -> None:
    assert MC.active_vintages(tracts) == {"tiger_cb": "2023", "acs5": "2019\u20132023"}


def test_main_prints_one_line_per_tier_for_the_box_it_was_asked_for(
    tracts: psycopg2.extensions.connection, scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert MC.main(["--box", "ny-default-padded", "--mode", "exact"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("# level=140 tiger_cb='2023'")
    assert out[1] == "box|tier_frac|tol_deg|features|raw_bytes|gzip_bytes"
    body = [line for line in out if line.startswith("ny-default-padded|")]
    assert len(body) == len(SIMPLIFY_TIERS)
    assert all(line.split("|")[-1] != "" for line in body), "exact mode must report a gzipped size"


def test_main_defaults_to_every_box_and_length_mode_leaves_the_gzip_column_empty(
    tracts: psycopg2.extensions.connection, scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert MC.main([]) == 0
    out = capsys.readouterr().out
    for name in MC.BOXES:
        assert f"{name}|" in out
    assert out.rstrip().endswith("|"), "length mode reports no compressed size"


def test_main_sweeps_when_asked(
    tracts: psycopg2.extensions.connection, scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert MC.main(["--sweep", "--step", "4.0", "--top", "2"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[1] == "lon|lat|tracts"
    assert len(out) == 4                       # the header comment, the column line, two windows


def test_main_refuses_without_a_database_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert MC.main(["--box", "ny-default-padded"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_the_main_guard_is_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["measure_boundary_caps.py"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "measure_boundary_caps.py"), run_name="__main__")
    assert exc.value.code == 2
