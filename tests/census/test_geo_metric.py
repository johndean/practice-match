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
from typing import Self

import fakeredis
import psycopg2
import psycopg2.extensions
import pytest

from app.census import geo_metric, materialize
from app.census import metrics as M

STATE_TX, STATE_IL = "48", "17"
# En dashes as escapes, not literals: ruff's RUF001 refuses an ambiguous U+2013 in source, and
# `migrations/062`/`063` and `tests/census/test_migration_064.py` already write them this way.
ACS_NOW, ACS_PRIOR, CBP_V, ZBP_V, TIGER_V = "2019\u20132023", "2014\u20132018", "2022", "2022", "2023"

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


def _zbp(conn: psycopg2.extensions.connection, run: int, geo_id: str, establishments: int | None,
         naics: str = "541940") -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO zbp_industry (geo_id, summary_level, vintage, naics_code, establishments, ingest_run_id) "
            "VALUES (%s, '860', %s, %s, %s, %s)",
            (geo_id, ZBP_V, naics, establishments, run),
        )


def _activate(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        for key, vintage in (("tiger_cb", TIGER_V), ("acs5", ACS_NOW), ("acs5_prior", ACS_PRIOR), ("cbp", CBP_V), ("zbp", ZBP_V)):
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
    # Tract rows DO carry state_fips; income is nationwide so nothing filters on it (`app/census/
    # tiger.py:98`), and they do not need one: `load_boundaries` keeps only the ZCTAs whose
    # centroid falls inside a market state (`tiger.py:244-246`), so joining geo_area IS the scope
    # at that level. Place and county rows carry one, and are filtered on it.
    _geo(conn, "48453001100", "140", "Census Tract 11", "48")
    _geo(conn, "48453001200", "140", "Census Tract 12", "48")
    _geo(conn, "4805000", "160", "Austin", STATE_TX)
    _geo(conn, "1600000", "160", "Elsewhere", STATE_IL)      # Illinois: never a DEMO market, in scope since 065
    _geo(conn, "48453", "050", "Travis County", STATE_TX)
    _acs(conn, run_id, "48453001100", "140", ACS_NOW, "B19013_001E", 92150, 6420)   # measured
    _acs(conn, run_id, "48453001200", "140", ACS_NOW, "B19013_001E", 41000, 40000)  # CV over 0.30 -> high_moe
    _acs(conn, run_id, "4805000", "160", ACS_NOW, "B01003_001E", 1_100_000)
    _acs(conn, run_id, "4805000", "160", ACS_PRIOR, "B01003_001E", 1_000_000)
    _acs(conn, run_id, "1600000", "160", ACS_NOW, "B01003_001E", 500_000)
    _acs(conn, run_id, "1600000", "160", ACS_PRIOR, "B01003_001E", 400_000)
    _cbp(conn, run_id, "48453", 32_000, 40)
    # Households (and therefore pets) shade at the TRACT, off the variable `market_metric` has
    # always read; competition shades at the ZCTA, which is ZIP Business Patterns' own geography.
    _acs(conn, run_id, "48453001100", "140", ACS_NOW, "B11001_001E", 1_480, 95)
    _acs(conn, run_id, "48453001200", "140", ACS_NOW, "B11001_001E", 900, 850)   # CV over 0.30 -> high_moe
    _geo(conn, "78704", "860", "ZCTA5 78704", None)   # a ZCTA carries no state_fips: it crosses state lines
    _zbp(conn, run_id, "78704", 7)
    _zbp(conn, run_id, "78704", 1904, naics="00")    # the all-industry total: this ZIP is in ZBP
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
    # growth is 2, not 1: the Illinois place the fixture seeds is materialised now that every
    # state is a market state. It was the negative control for the six-state scope until 065.
    assert counts == {"median_hh_income": 2, "population_growth_pct": 2, "revenue_per_establishment": 1,
                      "households": 2, "pet_households_est": 2, "establishments": 1}
    by = {(r[0], r[2]): r for r in _rows(world)}

    inc = by[("median_hh_income", "48453001100")]
    assert inc[1] == "140" and float(inc[3]) == 92150 and float(inc[4]) == 6420
    assert inc[5] == "usd" and inc[6] is False and inc[7] is None, "a published ACS estimate is not derived"
    assert inc[8] is False and inc[9] is None
    assert inc[10] == "acs5" and inc[11] == ACS_NOW
    assert inc[12] == {"acs5": ACS_NOW, "geo_level": "tract"}

    growth = by[("population_growth_pct", "4805000")]
    assert growth[1] == "160" and round(float(growth[3]), 4) == 10.0 and growth[4] is None
    assert growth[5] == "pct" and growth[6] is True and growth[7] == "v1"
    assert growth[10] == "acs5" and growth[11] == ACS_NOW
    assert growth[12] == {"acs5": ACS_NOW, "acs5_prior": ACS_PRIOR, "geo_level": "place"}

    econ = by[("revenue_per_establishment", "48453")]
    assert econ[1] == "050" and float(econ[3]) == 800_000 and econ[4] is None
    assert econ[5] == "usd" and econ[6] is True and econ[7] == "v1"
    assert econ[10] == "cbp" and econ[11] == CBP_V
    assert econ[12] == {"cbp": CBP_V, "geo_level": "county", "note": "payroll per establishment, not revenue", "cbp_noise": None}


def test_every_shaded_layer_is_written_at_the_geography_its_figure_is_honest_at() -> None:
    """D-C35's rule, and the six layers it now governs. No layer is ever promoted into a finer
    slot: growth stays at the PLACE (the 2010->2020 tract boundary change makes a tract-level
    growth figure uncomputable from what we hold, plan D12), payroll stays at the COUNTY (CBP is
    published there and nowhere finer), and competition is written at the ZCTA because ZIP
    Business Patterns is ZIP-native -- the stakeholder's §6 forbids approximating a ZIP to
    anything else UNLESS the ZIP area IS the dataset's authoritative geography, which for this one
    dataset it literally is.

    `households` and `pet_households_est` join income at the tract on 2026-09-12: they were
    graduated symbols at the listing point until then ("city-scale class breaks on small areas
    produce a picture with no information"), which was true of the CLASS BREAKS and not of the
    geography -- the ACS publishes `B11001_001E` at the tract, 84,400 of them are loaded, and the
    breaks were re-cut against that distribution in the same change."""
    assert [(key, level) for key, level, _, _ in geo_metric.LAYERS] == [
        ("median_hh_income", "140"), ("population_growth_pct", "160"), ("revenue_per_establishment", "050"),
        ("households", "140"), ("pet_households_est", "140"), ("establishments", "860"),
    ]


def test_scope_is_every_state_so_a_place_outside_the_demo_markets_is_materialised(
    world: psycopg2.extensions.connection,
) -> None:
    """The INVERSE of what this asserted until 2026-09-12, and the clearest single proof of the
    ruling. The fixture seeds an Illinois place precisely BECAUSE Illinois was never one of the
    six demo markets; this test used to assert it was skipped ("an Illinois place was
    materialised" was the failure message). `market_state` now carries every state, so the same
    place must be written -- with no code change, which is the requirement."""
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT geo_id FROM geo_metric WHERE metric_key = 'population_growth_pct' ORDER BY geo_id")
        assert [r[0] for r in cur.fetchall()] == ["1600000", "4805000"], "a place outside the demo markets was skipped"


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

def test_suppression_reaches_the_margin_layers_only_and_through_the_one_function(world: psycopg2.extensions.connection) -> None:
    """D-NS17: feeding growth, payroll or competition through `_suppression` with `moe = None`
    would return `(True, 'no_moe')` and grey out EVERY one of those polygons in the country, which
    is the opposite of honest — none of the three has a published margin (a difference of two ACS
    periods; a census of establishments rather than a sample), and each says so in the tip
    instead. The two ACS COUNT layers do have one and do go through it: households carries
    `B11001_001E`'s own margin, and pets inherits households' verdict as `input_suppressed`."""
    assert geo_metric._suppression is materialize._suppression, "a second CV/Z90 implementation"
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    rows = [(r[0], r[2], r[8], r[9]) for r in _rows(world)]
    assert ("median_hh_income", "48453001200", True, "high_moe") in rows
    assert ("median_hh_income", "48453001100", False, None) in rows
    assert ("households", "48453001200", True, "high_moe") in rows
    assert ("pet_households_est", "48453001200", True, "input_suppressed") in rows
    no_margin = ("population_growth_pct", "revenue_per_establishment", "establishments")
    assert all(not r[2] for r in rows if r[0] in no_margin), "a layer with no published margin was greyed"


def test_an_income_estimate_with_no_margin_is_unmeasured_and_an_absent_one_is_not_suppressed(
    world: psycopg2.extensions.connection, run_id: int,
) -> None:
    """Global Constraint (c), measured rather than assumed — `_suppression(None, None)` is
    `(False, None)` and `_suppression(72400, None)` is `(True, 'no_moe')`. So "no data" is
    `value is None` and is a DIFFERENT state from `suppressed is True`: D-NS16's grey polygon is
    reached by both, and only the tip distinguishes them."""
    _geo(world, "48453001300", "140", "Census Tract 13", "48")
    _acs(world, run_id, "48453001300", "140", ACS_NOW, "B19013_001E", None, None)   # loaded, but the cell is empty
    _geo(world, "48453001400", "140", "Census Tract 14", "48")
    _acs(world, run_id, "48453001400", "140", ACS_NOW, "B19013_001E", 72400, None)  # an estimate with no published margin

    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts["median_hh_income"] == 4, "a geography with no figure is still written, never omitted"
    by = {(r[0], r[2]): r for r in _rows(world)}
    assert (by[("median_hh_income", "48453001300")][3], by[("median_hh_income", "48453001300")][4]) == (None, None)
    assert (by[("median_hh_income", "48453001300")][8], by[("median_hh_income", "48453001300")][9]) == (False, None)
    assert (by[("median_hh_income", "48453001400")][8], by[("median_hh_income", "48453001400")][9]) == (True, "no_moe")


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
    assert counts == {"median_hh_income": 2, "population_growth_pct": 3, "revenue_per_establishment": 2,
                      "households": 2, "pet_households_est": 2, "establishments": 1}
    by = {(r[0], r[2]): r for r in _rows(world)}
    assert by[("population_growth_pct", "4827000")][3] is None
    assert by[("population_growth_pct", "4827000")][8] is False, "an absent figure is not a suppressed one"
    assert by[("revenue_per_establishment", "48001")][3] is None
    assert by[("revenue_per_establishment", "48001")][8] is False


@pytest.mark.parametrize(("flag", "verdict"), [
    ("D", (True, "source_flag")),                      # a withheld cell: nothing to show
    ("EMP_N=0;PAYANN_N=0", (False, None)),             # what live QA holds for Dallas County 48113
    ("EMP_N=3;PAYANN_N=3", (False, None)),             # the HIGHEST published noise level is still published
    ("PAYANN_N=9", (True, "source_flag")),             # not a level CBP publishes -- fail closed
    ("ESTAB_F=D", (True, "source_flag")),              # a withholding variable, not a noise one
])
def test_a_withheld_cbp_cell_is_suppressed_and_a_noise_level_is_not(
    world: psycopg2.extensions.connection, flag: str, verdict: tuple[bool, str | None],
) -> None:
    """§6 and D-L1 (2026-09-12): the one thing that hides a county is the Census Bureau's own
    WITHHOLDING, and CBP's `EMP_N`/`PAYANN_N` are noise RANGES, not withholding. Reading the flag's
    truthiness suppressed all 392 county rows in the country over `EMP_N=0;PAYANN_N=0` -- noise
    level zero on both fields -- while the docked panel served the very same row as "$819K"."""
    with world.cursor() as cur:
        cur.execute("UPDATE cbp_industry SET flag = %s WHERE geo_id = '48453'", (flag,))
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT suppressed, suppress_reason FROM geo_metric WHERE metric_key = 'revenue_per_establishment'")
        assert cur.fetchone() == verdict
        cur.execute("SELECT inputs->>'cbp_noise' FROM geo_metric WHERE metric_key = 'revenue_per_establishment'")
        assert cur.fetchone()[0] == flag, "the flag itself is carried, so a later ruling needs no second read"


def test_both_writers_decide_a_cbp_flag_through_the_same_function() -> None:
    """The sibling of `test_suppression_is_applied_to_income_only_and_through_the_one_function`,
    and the reason the payroll layer went dark: two spellings of one decision about one column."""
    assert geo_metric._cbp_suppression is materialize._cbp_suppression, "a second CBP flag rule"
    assert materialize._cbp_suppression("") == (False, None), "an empty flag withholds nothing"


def test_households_are_written_at_the_tract_with_their_own_published_margin(
    world: psycopg2.extensions.connection,
) -> None:
    """`B11001_001E` is a published ACS estimate with a published margin, so it is NOT derived and
    it goes through the same `_suppression` income does -- a tract whose count is too imprecise to
    show is greyed rather than shaded, at the same CV threshold."""
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    by = {(r[0], r[2]): r for r in _rows(world)}
    hh = by[("households", "48453001100")]
    assert hh[1] == "140" and float(hh[3]) == 1480 and float(hh[4]) == 95
    assert hh[5] == "count" and hh[6] is False and hh[7] is None, "a published ACS count is not derived"
    assert (hh[8], hh[9]) == (False, None)
    assert hh[10] == "acs5" and hh[11] == ACS_NOW
    assert hh[12] == {"acs5": ACS_NOW, "geo_level": "tract"}
    assert (by[("households", "48453001200")][8], by[("households", "48453001200")][9]) == (True, "high_moe")


def test_pet_households_are_derived_from_the_same_tract_and_say_so(world: psycopg2.extensions.connection) -> None:
    """§9: a modelled estimate is identified as one. `is_derived` is true, `formula_version` is
    stamped, the assumed rate is in `inputs` where the layer catalogue's own caveat can be checked
    against it, and the formula is `metrics.pet_households_est` -- the design's own households x
    0.57, never a second implementation of it.

    It inherits the households row's suppression as `input_suppressed`, exactly as
    `materialize.py`'s own pets row does: an estimate built on a figure too imprecise to show is
    not itself showable, and a confident-looking number with nothing to say why would be worse
    than a grey polygon."""
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    by = {(r[0], r[2]): r for r in _rows(world)}
    pets = by[("pet_households_est", "48453001100")]
    assert pets[1] == "140" and float(pets[3]) == M.pet_households_est(1480)
    assert pets[4] is None, "a rounded model output carries no published margin"
    assert pets[5] == "count" and pets[6] is True and pets[7] == "v1"
    assert (pets[8], pets[9]) == (False, None)
    assert pets[12] == {"acs5": ACS_NOW, "geo_level": "tract", "pet_incidence_rate": M.PET_RATE}
    assert (by[("pet_households_est", "48453001200")][8], by[("pet_households_est", "48453001200")][9]) == (True, "input_suppressed")


class _CountingCursor:
    """Everything `geo_metric` asks of a cursor, plus a note of the statements it ran. psycopg2's
    own `cursor` is an immutable C type, so it cannot be monkeypatched -- a proxy is the only way
    to count from outside the module under test."""

    def __init__(self, inner: psycopg2.extensions.cursor, seen: list[str]) -> None:
        self._inner, self._seen = inner, seen

    def execute(self, sql: str, *a: object, **kw: object) -> None:
        self._seen.append(str(sql))
        self._inner.execute(sql, *a, **kw)   # type: ignore[arg-type]

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def __enter__(self) -> Self:
        self._inner.__enter__()
        return self

    def __exit__(self, *exc: object) -> None:
        self._inner.__exit__(*exc)   # type: ignore[arg-type]


class _Counting:
    """The connection `materialize_geo` is handed: real in every respect but its cursors."""

    def __init__(self, inner: psycopg2.extensions.connection, seen: list[str]) -> None:
        self._inner, self._seen = inner, seen

    def cursor(self) -> _CountingCursor:
        return _CountingCursor(self._inner.cursor(), self._seen)

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def __setattr__(self, name: str, value: object) -> None:
        if name in ("_inner", "_seen"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._inner, name, value)


def test_the_tract_household_scan_runs_once_for_both_layers_that_read_it(
    world: psycopg2.extensions.connection,
) -> None:
    """Review round 1, Minor 2. `households` and `pet_households_est` are the same ACS variable at
    the same geography -- pets is `round(households x 0.57)` and has no source of its own -- and
    each builder ran the whole `_HOUSEHOLDS_SQL` scan, so a nightly did two full passes over
    ~84,000 tract rows for a deterministic multiple of figures it had already read.

    One pass, shared through the run's own cache. Asserted by counting the executions rather than
    by timing: a cache that silently stopped being consulted is exactly the kind of regression a
    stopwatch would never catch, and the ROWS must still be identical either way."""
    both = [r for r in _rows(world) if r[0] in ("households", "pet_households_est")]
    assert both == [], "the fixture starts with no rows, so the comparison below means something"

    scans: list[str] = []
    geo_metric.materialize_geo(_Counting(world, scans), fakeredis.FakeRedis())   # type: ignore[arg-type]
    households_scans = [q for q in scans if "B11001_001E" in q]
    assert len(households_scans) == 1, f"the tract household scan ran {len(households_scans)} times, not once"

    by = {(r[0], r[2]): r for r in _rows(world)}
    assert float(by[("households", "48453001100")][3]) == 1480
    assert float(by[("pet_households_est", "48453001100")][3]) == M.pet_households_est(1480)


def test_competition_is_written_at_the_zcta_which_is_zbps_own_geography(world: psycopg2.extensions.connection) -> None:
    """ZIP Business Patterns is ZIP-native: its rows ARE ZIP areas, and `zbp_industry` stores them
    under summary level 860 with no state term, because a ZCTA can cross a state line. An
    establishment count is observed, not modelled, and CBP/ZBP is a census of establishments
    rather than a sample -- there is no margin to test and nothing to grey."""
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    by = {(r[0], r[2]): r for r in _rows(world)}
    comp = by[("establishments", "78704")]
    assert comp[1] == "860" and float(comp[3]) == 7 and comp[4] is None
    assert comp[5] == "count" and comp[6] is False and comp[7] is None
    assert (comp[8], comp[9]) == (False, None)
    assert comp[10] == "zbp" and comp[11] == ZBP_V
    assert comp[12] == {"zbp": ZBP_V, "geo_level": "zcta", "naics": "541940"}


def test_a_zcta_with_no_zbp_row_yet_is_written_with_a_null_value_rather_than_a_zero(
    world: psycopg2.extensions.connection,
) -> None:
    """The national `zbp` load was still running when this layer was built, so the code must not
    assume it has finished -- and D-NS16 governs the answer: a ZCTA the load has not reached yet
    is an ABSENCE, drawn in the no-data class, never a zero. "No veterinary practices here" and
    "we have not loaded this ZIP yet" are different sentences, and a 0 tells the wrong one."""
    _geo(world, "79901", "860", "ZCTA5 79901", None)
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    by = {(r[0], r[2]): r for r in _rows(world)}
    assert by[("establishments", "79901")][3] is None
    assert by[("establishments", "79901")][8] is False, "an absent figure is not a suppressed one"


def test_a_zip_the_census_withheld_a_count_for_is_suppressed_and_one_it_does_not_cover_is_not(
    world: psycopg2.extensions.connection, run_id: int,
) -> None:
    """Review round 1, Important 3 (2026-09-12). The Census publishes ZIP-level INDUSTRY detail
    only where a category has three or more establishments -- "if a given NAICS category has less
    than three business establishments, the number of establishments won't be reported for that
    category, but they will be included in the sum total" -- which is why `zbp_industry` held a
    minimum of 3 nationally on QA and not one row below it.

    So there are THREE states at a ZCTA, not two, and the first two were served identically until
    this case existed: a published count; a ZIP area ZIP Code Business Patterns COVERS whose
    veterinary count the Census withheld under its own rule (`suppressed`, `source_threshold`);
    and a ZIP area the dataset does not cover at all (`value: null, suppressed: false`). 393 of
    Dallas's 535 ZCTAs -- 73 % of that map -- were the middle state saying it was the third, which
    is the mirror image of the CBP over-suppression this same branch fixed."""
    _geo(world, "78702", "860", "ZCTA5 78702", None)   # covered, veterinary count withheld
    _zbp(world, run_id, "78702", 812, naics="00")
    _geo(world, "79901", "860", "ZCTA5 79901", None)   # not covered by ZBP at all
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    by = {(r[0], r[2]): r for r in _rows(world)}

    withheld = by[("establishments", "78702")]
    assert withheld[3] is None, "a withheld count is never invented, and never a zero"
    assert (withheld[8], withheld[9]) == (True, "source_threshold")
    assert withheld[12] == {"zbp": ZBP_V, "geo_level": "zcta", "naics": "541940"}

    uncovered = by[("establishments", "79901")]
    assert (uncovered[3], uncovered[8], uncovered[9]) == (None, False, None)

    published = by[("establishments", "78704")]
    assert (float(published[3]), published[8]) == (7.0, False)


def test_a_layer_whose_own_dataset_is_not_cleared_writes_nothing_and_the_others_still_write(
    world: psycopg2.extensions.connection,
) -> None:
    """Competition is the first layer whose dataset is neither `acs5` nor `cbp`, so it is the first
    that can be withdrawn on its own. The nightly run must not fail, and the five layers the VIN
    Foundation still holds a licence for must still be written."""
    with world.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'zbp'")
    counts = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert counts["establishments"] == 0
    assert counts["households"] == 2 and counts["median_hh_income"] == 2


# ---- the write itself (D-NS7) ------------------------------------------------------------------

def test_the_rows_are_written_in_batches_and_the_result_is_row_for_row_identical(
    world: psycopg2.extensions.connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The nightly went from three layers to six on 2026-09-12, ~93,000 rows to ~285,000, so the
    per-row round trip `executemany` makes became the dominant cost of a job that must finish
    before anyone reads it (R7 measured the same swap at 2.9x on this database).

    A speed change must not be a behaviour change, so this asserts the two directly: the batch
    path IS taken (`execute_batch` is called, once per layer that wrote anything), and every row
    it leaves behind is identical to the one the per-row path leaves."""
    batched = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    rows_batched = _rows(world)

    calls: list[int] = []
    real = geo_metric.execute_batch

    def counted(cur: object, sql: str, argslist: list[object], **kw: object) -> None:
        calls.append(len(argslist))
        cur.executemany(sql, argslist)   # type: ignore[attr-defined]

    monkeypatch.setattr(geo_metric, "execute_batch", counted)
    one_by_one = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert real is not counted
    assert calls == [2, 2, 1, 2, 2, 1], "one batch per layer, carrying that layer's whole write"
    assert one_by_one == batched
    assert _rows(world) == rows_batched, "the batched write and the per-row write disagree"


def test_the_write_is_idempotent_and_rewrites_rather_than_accumulating(world: psycopg2.extensions.connection) -> None:
    first = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    second = geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    assert first == second
    with world.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_metric")
        # 10 = two tracts x three tract layers (income, households, pets) + two places (growth:
        # Austin AND the Illinois one, in scope since migration 065) + one county (payroll) + one
        # ZCTA (competition). It was 5 before the three blank layers were built, 4 before 065.
        assert cur.fetchone()[0] == 10


def test_the_rewrite_deletes_the_triples_old_rows_rather_than_only_upserting(world: psycopg2.extensions.connection) -> None:
    """`ON CONFLICT` alone replaces a row whose key already matches; a geography that has LEFT the
    boundary vintage keeps its stale figure forever (A-C19, on `market_metric`). The DELETE is
    scoped to the triple, so the other two layers are untouched by it."""
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("DELETE FROM geo_area WHERE geo_id = '48453001200'")
    geo_metric.materialize_geo(world, fakeredis.FakeRedis())
    with world.cursor() as cur:
        cur.execute("SELECT geo_id FROM geo_metric WHERE metric_key = 'median_hh_income'")
        assert [r[0] for r in cur.fetchall()] == ["48453001100"], "a geography no longer in the boundary vintage kept its row"
        cur.execute("SELECT count(*) FROM geo_metric WHERE metric_key <> 'median_hh_income'")
        # 6 = two growth places (Austin + Illinois), one payroll county, one ZCTA (competition)
        # and ONE tract each for households and pets — those two share income's own (level,
        # vintage) and lose the deleted geography too, which is the point: the DELETE is scoped
        # to the triple, so it takes its own metric's stale row and no other metric's.
        assert cur.fetchone()[0] == 6, "the DELETE reached outside its own (level, metric, vintage)"


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
    row = ("48453001100", "140", ACS_NOW, "median_hh_income", 92150.0, "usd", False, None, None, False, None, "{}", "pet_ownership")
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
        "median_hh_income": 0, "population_growth_pct": 0, "revenue_per_establishment": 0,
        "households": 0, "pet_households_est": 0, "establishments": 0,
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
