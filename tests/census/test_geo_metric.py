"""app/census/geo_metric.py — the only writer of `geo_metric` (D-NS5 through D-NS9).

`app/census/materialize.py` stays the only writer of `market_metric` and is not edited by this
sub-project at all, except that `_suppression` gains a second importer.

Three departures from the plan's own draft of this file, each measured before it was written:

1. **`acs_measure` and `cbp_industry` carry `ingest_run_id bigint NOT NULL REFERENCES
   ingest_run(id)`** (`migrations/019_census_measures.sql:9`, `:23`). The plan's draft helpers
   omit it and every insert fails on the NOT NULL. `_run()` below creates the one `ingest_run`
   row the whole fixture hangs off, exactly as `tests/census/test_materialize.py::_seed_world`
   already does.
2. **The plan's rollback case never reaches `_rewrite`'s own `except` arm**: it monkeypatches
   `_rewrite` itself, so the real function's rollback is never entered. It is kept (it pins the
   per-triple boundary, which is what D-NS7 is about) and
   `test_the_licence_gate_is_the_last_line_of_defence_and_the_write_rolls_back` reaches the arm
   through the trigger the table actually carries.
3. **The `world` fixture has no absent figures**, so `_as_float`'s null arm and the design's own
   "no data" polygon (D-NS16) are unreachable from it. Rather than widen `world` and re-type
   every count in every other case, the three null cases add their own rows.
"""
from __future__ import annotations

import ast
from pathlib import Path

import fakeredis
import psycopg2
import psycopg2.extensions
import pytest

from app.census import geo_metric, materialize

STATE_TX, STATE_IL = "48", "17"
# En dashes as escapes, not literals: ruff's RUF001 refuses an ambiguous U+2013 in source, and
# `migrations/062`/`063` and `tests/census/test_migration_064.py` already write them this way.
ACS_NOW, ACS_PRIOR, CBP_V, TIGER_V = "2019\u20132023", "2014\u20132018", "2022", "2023"

ROOT = Path(__file__).resolve().parent.parent.parent


def _geo(conn: psycopg2.extensions.connection, geo_id: str, level: str, name: str, state: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES "
            "(%s, %s, %s, %s, %s, ST_Multi(ST_GeomFromText('POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))',4269)), "
            "ST_Point(-97.75,30.31,4269))",
            (geo_id, level, TIGER_V, name, state),
        )


def _run(conn: psycopg2.extensions.connection) -> int:
    """The `ingest_run` row `acs_measure.ingest_run_id` and `cbp_industry.ingest_run_id` point at.
    One row is enough: nothing in this module reads `ingest_run` — `vintage.qa` does, and nothing
    here activates a vintage."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingest_run (dataset_key, vintage, started_at, status) VALUES ('acs5', %s, now(), 'succeeded') RETURNING id",
            (ACS_NOW,),
        )
        return int(cur.fetchone()[0])


def _acs(conn: psycopg2.extensions.connection, run: int, geo_id: str, level: str, vintage: str,
         variable: str, estimate: int | None, moe: int | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO acs_measure (geo_id, summary_level, vintage, variable, estimate, moe, ingest_run_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (geo_id, level, vintage, variable, estimate, moe, run),
        )


def _cbp(conn: psycopg2.extensions.connection, run: int, geo_id: str, payroll_k: int | None,
         establishments: int | None, flag: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO cbp_industry (geo_id, summary_level, vintage, naics_code, establishments, annual_payroll_k, flag, ingest_run_id) "
            "VALUES (%s, '050', %s, '541940', %s, %s, %s, %s)",
            (geo_id, CBP_V, establishments, payroll_k, flag, run),
        )


def _activate(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        for key, vintage in (("tiger_cb", TIGER_V), ("acs5", ACS_NOW), ("acs5_prior", ACS_PRIOR), ("cbp", CBP_V)):
            cur.execute(
                "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s,%s,now(),'test') "
                "ON CONFLICT (dataset_key) DO UPDATE SET vintage = EXCLUDED.vintage",
                (key, vintage),
            )


@pytest.fixture
def run_id(conn: psycopg2.extensions.connection) -> int:
    return _run(conn)


@pytest.fixture
def world(conn: psycopg2.extensions.connection, run_id: int) -> psycopg2.extensions.connection:
    _activate(conn)
    # ZCTA rows carry no state_fips (tiger.py's BoundarySpec for '860' has none — `app/census/
    # tiger.py:98`), and they do not need one: `load_boundaries` keeps only the ZCTAs whose
    # centroid falls inside a market state (`tiger.py:244-246`), so joining geo_area IS the scope
    # at that level. Place and county rows carry one, and are filtered on it.
    _geo(conn, "78704", "860", "ZCTA5 78704", None)
    _geo(conn, "78745", "860", "ZCTA5 78745", None)
    _geo(conn, "4805000", "160", "Austin", STATE_TX)
    _geo(conn, "1600000", "160", "Elsewhere", STATE_IL)      # Illinois: not a market_state
    _geo(conn, "48453", "050", "Travis County", STATE_TX)
    _acs(conn, run_id, "78704", "860", ACS_NOW, "B19013_001E", 92150, 6420)   # measured
    _acs(conn, run_id, "78745", "860", ACS_NOW, "B19013_001E", 41000, 40000)  # CV over 0.30 -> high_moe
    _acs(conn, run_id, "4805000", "160", ACS_NOW, "B01003_001E", 1_100_000)
    _acs(conn, run_id, "4805000", "160", ACS_PRIOR, "B01003_001E", 1_000_000)
    _acs(conn, run_id, "1600000", "160", ACS_NOW, "B01003_001E", 500_000)
    _acs(conn, run_id, "1600000", "160", ACS_PRIOR, "B01003_001E", 400_000)
    _cbp(conn, run_id, "48453", 32_000, 40)
    return conn


def _rows(conn: psycopg2.extensions.connection) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT metric_key, summary_level, geo_id, value_num, moe, unit, is_derived, formula_version, "
            "suppressed, suppress_reason, source_dataset, vintage, inputs FROM geo_metric ORDER BY metric_key, geo_id"
        )
        return list(cur.fetchall())


# ---- the three ruled metrics at the three ruled levels ----------------------------------------

def test_the_three_ruled_metrics_land_at_the_three_ruled_levels(world: psycopg2.extensions.connection) -> None:
    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts == {"median_hh_income": 2, "population_growth_pct": 1, "revenue_per_establishment": 1}
    by = {(r[0], r[2]): r for r in _rows(world)}

    inc = by[("median_hh_income", "78704")]
    assert inc[1] == "860" and float(inc[3]) == 92150 and float(inc[4]) == 6420
    assert inc[5] == "usd" and inc[6] is False and inc[7] is None, "a published ACS estimate is not derived"
    assert inc[8] is False and inc[9] is None
    assert inc[10] == "acs5" and inc[11] == ACS_NOW
    assert inc[12] == {"acs5": ACS_NOW, "geo_level": "zcta"}

    growth = by[("population_growth_pct", "4805000")]
    assert growth[1] == "160" and round(float(growth[3]), 4) == 10.0 and growth[4] is None
    assert growth[5] == "pct" and growth[6] is True and growth[7] == "v1"
    assert growth[10] == "acs5" and growth[11] == ACS_NOW
    assert growth[12] == {"acs5": ACS_NOW, "acs5_prior": ACS_PRIOR, "geo_level": "place"}

    econ = by[("revenue_per_establishment", "48453")]
    assert econ[1] == "050" and float(econ[3]) == 800_000 and econ[4] is None
    assert econ[5] == "usd" and econ[6] is True and econ[7] == "v1"
    assert econ[10] == "cbp" and econ[11] == CBP_V
    assert econ[12] == {"cbp": CBP_V, "geo_level": "county", "note": "payroll per establishment, not revenue"}


def test_the_layer_table_is_d_c35s_assignment_and_nothing_wider() -> None:
    """`pets`, `households` and `competition` stay graduated symbols at the listing point
    (constraint (k)); no layer is ever promoted into a finer slot."""
    assert [(key, level) for key, level, _, _ in geo_metric.LAYERS] == [
        ("median_hh_income", "860"), ("population_growth_pct", "160"), ("revenue_per_establishment", "050"),
    ]


def test_scope_is_the_six_market_state_states(world: psycopg2.extensions.connection) -> None:
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT geo_id FROM geo_metric WHERE metric_key = 'population_growth_pct'")
        assert [r[0] for r in cur.fetchall()] == ["4805000"], "an Illinois place was materialised"


def test_a_declining_place_keeps_its_minus_sign(world: psycopg2.extensions.connection, run_id: int) -> None:
    """`frontend/src/logic.js:202`'s `num()` strips every character but digits and a dot, so
    `num(-5.1)` is `5.1` and a decline reads as growth. Nothing on this side is shaped like that —
    `_as_float` is `float(Decimal("-10"))` — and this is the case that would catch it if it were."""
    _geo(world, "4819000", "160", "Shrinking", STATE_TX)
    _acs(world, run_id, "4819000", "160", ACS_NOW, "B01003_001E", 900_000)
    _acs(world, run_id, "4819000", "160", ACS_PRIOR, "B01003_001E", 1_000_000)
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT value_num FROM geo_metric WHERE geo_id = '4819000' AND metric_key = 'population_growth_pct'")
        assert float(cur.fetchone()[0]) == -10.0


# ---- suppression and honesty (§6) --------------------------------------------------------------

def test_suppression_is_applied_to_income_only_and_through_the_one_function(world: psycopg2.extensions.connection) -> None:
    """D-NS17: feeding growth or econ through `_suppression` with `moe = None` would return
    `(True, 'no_moe')` and grey out EVERY growth and payroll polygon in the country, which is the
    opposite of honest — neither has a published margin, and both say so in the tip instead."""
    assert geo_metric._suppression is materialize._suppression, "a second CV/Z90 implementation"
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    rows = [(r[0], r[2], r[8], r[9]) for r in _rows(world)]
    assert ("median_hh_income", "78745", True, "high_moe") in rows
    assert ("median_hh_income", "78704", False, None) in rows
    assert all(not r[2] for r in rows if r[0] != "median_hh_income"), "growth or econ was greyed"


def test_an_income_estimate_with_no_margin_is_unmeasured_and_an_absent_one_is_not_suppressed(
    world: psycopg2.extensions.connection, run_id: int,
) -> None:
    """Global Constraint (c), measured rather than assumed — `_suppression(None, None)` is
    `(False, None)` and `_suppression(72400, None)` is `(True, 'no_moe')`. So "no data" is
    `value is None` and is a DIFFERENT state from `suppressed is True`: D-NS16's grey polygon is
    reached by both, and only the tip distinguishes them."""
    _geo(world, "78702", "860", "ZCTA5 78702", None)
    _acs(world, run_id, "78702", "860", ACS_NOW, "B19013_001E", None, None)   # loaded, but the cell is empty
    _geo(world, "78703", "860", "ZCTA5 78703", None)
    _acs(world, run_id, "78703", "860", ACS_NOW, "B19013_001E", 72400, None)  # an estimate with no published margin

    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts["median_hh_income"] == 4, "a geography with no figure is still written, never omitted"
    by = {(r[0], r[2]): r for r in _rows(world)}
    assert (by[("median_hh_income", "78702")][3], by[("median_hh_income", "78702")][4]) == (None, None)
    assert (by[("median_hh_income", "78702")][8], by[("median_hh_income", "78702")][9]) == (False, None)
    assert (by[("median_hh_income", "78703")][8], by[("median_hh_income", "78703")][9]) == (True, "no_moe")


def test_a_growth_or_payroll_geography_with_no_figure_is_written_with_a_null_value(
    world: psycopg2.extensions.connection, run_id: int,
) -> None:
    """D-NS16: "Where a geography has no value, render it as an explicit 'no data' class … never
    as zero." A row with `value_num IS NULL` is how the endpoint is told that; dropping the row
    would leave a hole in the choropleth, and a hole reads as a boundary."""
    _geo(world, "4827000", "160", "Unmeasured", STATE_TX)
    _acs(world, run_id, "4827000", "160", ACS_NOW, "B01003_001E", None)
    _acs(world, run_id, "4827000", "160", ACS_PRIOR, "B01003_001E", 1_000_000)
    _geo(world, "48001", "050", "Anderson County", STATE_TX)
    _cbp(world, run_id, "48001", None, None)

    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts == {"median_hh_income": 2, "population_growth_pct": 2, "revenue_per_establishment": 2}
    by = {(r[0], r[2]): r for r in _rows(world)}
    assert by[("population_growth_pct", "4827000")][3] is None
    assert by[("population_growth_pct", "4827000")][8] is False, "an absent figure is not a suppressed one"
    assert by[("revenue_per_establishment", "48001")][3] is None
    assert by[("revenue_per_establishment", "48001")][8] is False


def test_a_cbp_flag_suppresses_the_county_as_source_flag(world: psycopg2.extensions.connection) -> None:
    """§6: CBP withheld or noise-flagged the county cell. The figure is not shown and the tip says
    which of the four reasons it is."""
    with world.cursor() as cur:
        cur.execute("UPDATE cbp_industry SET flag = 'D' WHERE geo_id = '48453'")
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT suppressed, suppress_reason FROM geo_metric WHERE metric_key = 'revenue_per_establishment'")
        assert cur.fetchone() == (True, "source_flag")


# ---- the write itself (D-NS7) ------------------------------------------------------------------

def test_the_write_is_idempotent_and_rewrites_rather_than_accumulating(world: psycopg2.extensions.connection) -> None:
    first = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    second = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert first == second
    with world.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_metric")
        assert cur.fetchone()[0] == 4


def test_the_rewrite_deletes_the_triples_old_rows_rather_than_only_upserting(world: psycopg2.extensions.connection) -> None:
    """`ON CONFLICT` alone replaces a row whose key already matches; a geography that has LEFT the
    boundary vintage keeps its stale figure forever (A-C19, on `market_metric`). The DELETE is
    scoped to the triple, so the other two layers are untouched by it."""
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("DELETE FROM geo_area WHERE geo_id = '78745'")
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT geo_id FROM geo_metric WHERE metric_key = 'median_hh_income'")
        assert [r[0] for r in cur.fetchall()] == ["78704"], "a geography no longer in the boundary vintage kept its row"
        cur.execute("SELECT count(*) FROM geo_metric WHERE metric_key <> 'median_hh_income'")
        assert cur.fetchone()[0] == 2, "the DELETE reached outside its own (level, metric, vintage)"


def test_a_failed_triple_rolls_back_and_leaves_the_earlier_rows_standing(
    world: psycopg2.extensions.connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-NS7: one transaction per (level, metric, vintage). A failure inside one leaves the
    previous vintage's rows in place — Census spec §11's 'keep the prior vintage active'."""
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    real = geo_metric._rewrite

    def boom(conn: psycopg2.extensions.connection, level: str, metric_key: str, vintage: str, rows: list) -> int:
        if metric_key == "revenue_per_establishment":
            raise RuntimeError("the third triple failed")
        return real(conn, level, metric_key, vintage, rows)

    monkeypatch.setattr(geo_metric, "_rewrite", boom)
    with pytest.raises(RuntimeError):
        geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_metric WHERE metric_key = 'revenue_per_establishment'")
        assert cur.fetchone()[0] == 1, "the earlier generation was lost"
    assert world.autocommit is True, "the caller's autocommit was not restored"


def test_the_licence_gate_is_the_last_line_of_defence_and_the_write_rolls_back(
    world: psycopg2.extensions.connection,
) -> None:
    """`materialize_geo` declines to write an uncleared dataset (below), so the only way to reach
    `geo_metric_license_gate` is to call `_rewrite` directly — which is exactly what a fourth
    layer added without its gate would do. The refusal asserted is the TRIGGER's own
    (`psycopg2.errors.RaiseException`, SQLSTATE P0001) and its own message: the trigger is BEFORE
    and fires ahead of the foreign key's AFTER-row check, so a tolerant
    `raises((RaiseException, ForeignKeyViolation))` would pass with the gate deleted (Task 5's
    measurement). This is also the one case that enters `_rewrite`'s own rollback arm."""
    row = ("78704", "860", ACS_NOW, "median_hh_income", 92150.0, "usd", False, None, None, False, None, "{}", "pet_ownership")
    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        geo_metric._rewrite(world, "860", "median_hh_income", ACS_NOW, [row])
    assert "geo_metric write refused: dataset pet_ownership is not licence-cleared" in str(exc.value)
    assert world.autocommit is True, "the caller's autocommit was not restored after a failure"
    with world.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_metric")
        assert cur.fetchone()[0] == 0, "the failed triple was not rolled back"


# ---- the licence and vintage gates -------------------------------------------------------------

def test_a_layer_whose_licence_is_not_cleared_writes_nothing(world: psycopg2.extensions.connection) -> None:
    """The trigger would refuse the write anyway (D-NS3); this is the writer declining to try, so
    a nightly run does not fail on a dataset the VIN Foundation has withdrawn."""
    with world.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'cbp'")
    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts["revenue_per_establishment"] == 0
    assert counts["median_hh_income"] == 2


def test_growth_is_gated_on_acs5_prior_as_well_as_acs5(world: psycopg2.extensions.connection) -> None:
    """R3's specific hole: growth is stamped `source_dataset = 'acs5'` but folds `acs5_prior`, and
    a gate that reads only the stamped key reproduces the licence hole A-C23 (1) closed."""
    with world.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'unresolved' WHERE dataset_key = 'acs5_prior'")
    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts["population_growth_pct"] == 0
    assert counts["median_hh_income"] == 2


def test_growth_is_gated_on_acs5_priors_active_vintage_as_well(world: psycopg2.extensions.connection) -> None:
    """The other half of the same hole: a licence-cleared second dataset that has never been
    activated has no vintage to read the baseline at, and `act['acs5_prior']` would raise."""
    with world.cursor() as cur:
        cur.execute("DELETE FROM active_vintage WHERE dataset_key = 'acs5_prior'")
    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts["population_growth_pct"] == 0
    assert counts["median_hh_income"] == 2


def test_a_dataset_with_no_active_vintage_writes_nothing(conn: psycopg2.extensions.connection) -> None:
    """No `active_vintage` row at all: nothing to read and nothing to stamp."""
    assert geo_metric.materialize_geo(conn, fakeredis.FakeRedis()) == {
        "median_hh_income": 0, "population_growth_pct": 0, "revenue_per_establishment": 0
    }


def test_the_geo_version_is_bumped_on_every_run_so_cached_payloads_expire(world: psycopg2.extensions.connection) -> None:
    """The endpoint's cache key carries this. Without it a nightly rewrite that changes values but
    not the vintage would be invisible for up to the 24 h TTL."""
    r = fakeredis.FakeRedis()
    geo_metric.materialize_geo(world, r)
    first = int(r.get(geo_metric.GEO_VERSION_KEY))
    geo_metric.materialize_geo(world, r)
    assert int(r.get(geo_metric.GEO_VERSION_KEY)) > first


def test_the_version_is_bumped_even_by_a_run_that_writes_nothing(conn: psycopg2.extensions.connection) -> None:
    """A run that wrote nothing because a licence was withdrawn still has to expire the answers
    that were cached while it was cleared — `materialize_listing`'s own reason for stamping on
    every call, A-C19."""
    r = fakeredis.FakeRedis()
    geo_metric.materialize_geo(conn, r)
    assert r.get(geo_metric.GEO_VERSION_KEY) is not None


# ---- never on the request path (D-NS9, spec §10) -----------------------------------------------

def _writer_touches(tree: ast.AST) -> bool:
    """True if the module CALLS `materialize_geo(...)` — by attribute or by bare name — or imports
    the name at all. The import arm is what closes the alias hole: `from app.census.geo_metric
    import materialize_geo as go` followed by `go(...)` is a bare `ast.Name` the caller scan alone
    would not recognise. Importing the MODULE is deliberately allowed, because Task 9's boundary
    endpoint reads `geo_metric.GEO_VERSION_KEY` for its cache key and must keep being able to."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "materialize_geo" for alias in node.names):
            return True
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "materialize_geo":
                return True
            if isinstance(func, ast.Name) and func.id == "materialize_geo":
                return True
    return False


def test_the_writer_is_reached_from_the_nightly_task_alone_and_never_from_the_request_path() -> None:
    """D-NS9 is a requirement, not a description. `app/tasks/census.py` is the Celery module —
    nothing under `app/api/`, and no module `app/main.py` mounts, imports or calls it — so the
    single name in this set IS the proof that the only door to the writer is the 03:30 beat entry
    (`test_geo_metric_nightly_runs_at_0330_utc`). A new caller anywhere under `app/` fails here
    until somebody widens this set deliberately.

    Scanned at the AST level, not by grep: this module's own docstring and `app/api/market.py`'s
    (Task 9) both name `materialize_geo` in prose, and a substring search would match the very
    sentences that state the rule."""
    callers = {
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "app").rglob("*.py"))
        if _writer_touches(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    }
    assert callers == {"app/tasks/census.py"}


def test_the_request_path_scan_actually_detects_a_violation() -> None:
    """Proves the helper above is not vacuously false — without this, a scan that always returned
    `False` would pass the real-files test for the wrong reason."""
    assert _writer_touches(ast.parse("from app.census import geo_metric\ngeo_metric.materialize_geo(conn, r)\n")) is True
    assert _writer_touches(ast.parse("from app.census.geo_metric import materialize_geo\nmaterialize_geo(conn, r)\n")) is True
    assert _writer_touches(ast.parse("from app.census.geo_metric import materialize_geo as go\n")) is True
    assert _writer_touches(ast.parse("materialize_geo(conn, r)\n")) is True
    # Task 9's endpoint: importing the module, or the cache-key constant by name, and reading it,
    # stays legal -- both forms, because the plan's own draft of `app/api/market.py` uses the
    # second (`from app.census.geo_metric import GEO_VERSION_KEY`).
    assert _writer_touches(ast.parse("from app.census import geo_metric\nkey = geo_metric.GEO_VERSION_KEY\n")) is False
    assert _writer_touches(ast.parse("from app.census.geo_metric import GEO_VERSION_KEY\nkey = GEO_VERSION_KEY\n")) is False
    assert _writer_touches(ast.parse("x = 1\ndef f():\n    return x\n")) is False
