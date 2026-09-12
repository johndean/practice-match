"""scripts/measure_area_breaks.py — the choropleth's class breaks as a measurement.

Review round 1, Minor 6: `AREA_LAYERS` (amendment A24.25) cuts the three COUNT layers at the scale
the map paints, and nothing committed could re-derive those cuts. The precedent is
`scripts/measure_band_ambiguity.py`: a reporting script that reads `geo_metric`, runs nowhere on
the request path and builds nothing."""
import runpy
import sys
from pathlib import Path

import psycopg2
import pytest

from scripts import measure_area_breaks as MB

ROOT = Path(__file__).resolve().parents[2]


def _metric(conn: psycopg2.extensions.connection, geo_id: str, value: float | None, *,
            level: str = "860", metric: str = "establishments", suppressed: bool = False,
            vintage: str = "2022") -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, suppressed, "
            "suppress_reason, source_dataset, computed_at) VALUES (%s, %s, %s, %s, %s, 'count', %s, %s, 'zbp', now())",
            (geo_id, level, vintage, metric, value, suppressed, "source_threshold" if suppressed else None),
        )


def test_served_is_what_the_route_would_put_on_the_wire_and_nothing_else(conn: psycopg2.extensions.connection) -> None:
    """A SUPPRESSED row is `value: null` on the wire whatever `value_num` holds
    (`app/api/market.py::_boundary_feature`), so it is not part of the distribution a legend
    describes — and for `competition` that is the whole point: a ZIP area the Census withheld a
    count for must not be counted into the class that claims to hold small counts."""
    _metric(conn, "78704", 7)
    _metric(conn, "78745", 3)
    _metric(conn, "78702", 99, suppressed=True)   # withheld: never served, never classed
    _metric(conn, "78701", None)                  # not covered by ZBP at all
    assert MB.served(conn, "establishments", "2022") == [3.0, 7.0]


def test_served_reads_only_the_metric_and_vintage_it_was_asked_for(conn: psycopg2.extensions.connection) -> None:
    _metric(conn, "78704", 7)
    _metric(conn, "48453001100", 1480, level="140", metric="households", vintage="2019\u20132023")
    _metric(conn, "78745", 5, vintage="2021")
    assert MB.served(conn, "establishments", "2022") == [7.0]
    assert MB.served(conn, "households", "2019\u20132023") == [1480.0]


def test_quantile_reads_a_value_that_exists_rather_than_interpolating_one() -> None:
    """A break is compared against a value, so the marks printed beside it are values. An
    interpolated p50 of `[3, 4]` is 3.5, which no ZIP area holds and no class boundary can sit
    honestly beside."""
    assert MB.quantile([3.0, 4.0, 5.0, 6.0], 0.5) == 4.0
    assert MB.quantile([3.0, 4.0], 0.5) == 3.0
    assert MB.quantile([], 0.5) is None


def test_shares_use_the_designs_own_right_open_rule() -> None:
    """`logic.js`'s `bucket`: a value exactly ON a stop belongs to the class above it. A script
    that rounded the other way would print a distribution the map does not draw."""
    assert MB.shares([3.0, 4.0, 6.0, 10.0], [4, 6, 10]) == [25.0, 25.0, 25.0, 25.0]
    assert MB.shares([], [4, 6, 10]) == [0.0, 0.0, 0.0, 0.0]
    # The floor the competition breaks turn on: nothing below 3 exists, so a first class of
    # "1-3" can only ever hold the 3s — which is why A24.37 labels it "3".
    assert MB.shares([3.0, 3.0, 3.0], [4, 6, 10]) == [100.0, 0.0, 0.0, 0.0]


def test_main_prints_the_distribution_and_the_shares(conn: psycopg2.extensions.connection, scratch_dsn: str,
                                                     monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    for z, v in (("78704", 7), ("78745", 3), ("78702", 4), ("78701", 12)):
        _metric(conn, z, v)
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert MB.main(["--metric", "establishments", "--vintage", "2022", "--stops", "4,6,10"]) == 0
    out = capsys.readouterr().out
    assert "4 served, min 3, max 12" in out
    assert "25.0 / 25.0 / 25.0 / 25.0 %  on [4.0, 6.0, 10.0]" in out


def test_main_refuses_without_a_dsn_and_reports_an_empty_metric(conn: psycopg2.extensions.connection, scratch_dsn: str,
                                                                monkeypatch: pytest.MonkeyPatch,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    """Both non-zero exits, because a reporting script that prints nothing and exits 0 is how a
    break table comes to be 'measured' against an empty table."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert MB.main(["--metric", "establishments", "--vintage", "2022", "--stops", "4"]) == 2
    assert "DATABASE_URL is not set" in capsys.readouterr().err

    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert MB.main(["--metric", "establishments", "--vintage", "2022", "--stops", "4"]) == 1
    assert "nothing served" in capsys.readouterr().err


def test_the_main_guard_is_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    """`scripts/` is inside the 100 % gate, and the `if __name__` line is reachable only by
    running the file AS a script — `test_measure_band_ambiguity.py`'s own shape, for the same
    reason."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["measure_area_breaks.py", "--metric", "establishments",
                                      "--vintage", "2022", "--stops", "4"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "measure_area_breaks.py"), run_name="__main__")
    assert exc.value.code == 2
