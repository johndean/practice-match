"""Materialise `geo_metric` -- one row per (geography, metric, vintage), at the geography each
metric is honest at (spec 2026-09-10; D-C35, D-NS5 through D-NS9). The ONLY writer of this table.

`app/census/materialize.py` stays the only writer of `market_metric` and is not edited by this
sub-project at all, except that `_suppression` gains a second importer here. A listing's docked
panel keeps reading `market_metric`; the map reads `geo_metric`;
`tests/census/test_boundaries.py::test_the_endpoint_and_community_rows_agree_on_suppression`
(Task 9) is the test that makes the two agree.

Nothing here reimplements a formula or a suppression rule: `metrics.population_growth_pct` and
`metrics.revenue_per_establishment` are called unmodified, and `_suppression` is IMPORTED, with
its underscore kept -- renaming it would touch `materialize.py`'s three call sites for no
behavioural reason, and "surgical diffs" outranks the naming convention here (D-NS6).

Never on the request path (D-NS9, Census spec §10). The only door is `app/tasks/census.py`'s
`materialize_geo_metrics`, on the `geo-metric-nightly` beat entry at 03:30 UTC, and
`tests/census/test_geo_metric.py::
test_the_writer_is_reached_from_the_nightly_task_alone_and_never_from_the_request_path` walks
every module under `app/` at the AST level and fails on a second caller. Task 9's boundary
endpoint imports this module for `GEO_VERSION_KEY` alone; reading a constant is not calling the
writer, and that scan is written to keep telling the two apart."""
from __future__ import annotations

import json
import time
from decimal import Decimal

import psycopg2.extensions
import redis as redis_sync

from app.census import metrics as M
from app.census.materialize import _cbp_suppression, _suppression
from app.census.registry import load as load_registry
from app.census.vintage import active

# (metric_key, summary_level, source_dataset, also gated on). D-C35's assignment and nothing
# wider: `pets`, `households` and `competition` stay graduated symbols at the listing point.
# `population_growth_pct` folds acs5_prior but can only be STAMPED with one dataset key, which is
# exactly the hole A-C23 (1) closed for `vets_per_10k_households` -- hence the fourth element.
LAYERS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("median_hh_income", "140", "acs5", ()),
    ("population_growth_pct", "160", "acs5", ("acs5_prior",)),
    ("revenue_per_establishment", "050", "cbp", ()),
)

# Bumped on every run, and carried in the boundary endpoint's cache key. Without it a nightly
# rewrite that changes values but not the vintage would be invisible for up to the 24 h TTL --
# `materialize_listing`'s own `listing:{id}:market:version` idiom, one table wider.
GEO_VERSION_KEY = "market:geo:version"

_UPSERT = """
INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, is_derived, formula_version, moe, suppressed, suppress_reason, inputs, source_dataset, computed_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
ON CONFLICT (geo_id, summary_level, vintage, metric_key) DO UPDATE SET value_num = EXCLUDED.value_num, unit = EXCLUDED.unit,
  is_derived = EXCLUDED.is_derived, formula_version = EXCLUDED.formula_version, moe = EXCLUDED.moe, suppressed = EXCLUDED.suppressed,
  suppress_reason = EXCLUDED.suppress_reason, inputs = EXCLUDED.inputs, source_dataset = EXCLUDED.source_dataset, computed_at = now()
"""

# A-C19's reason, one table wider: `ON CONFLICT` alone only replaces a row whose key already
# matches, so a geography that has LEFT the boundary vintage would keep its stale figure forever.
_DELETE = "DELETE FROM geo_metric WHERE summary_level = %s AND metric_key = %s AND vintage = %s"

# Income shades at the CENSUS TRACT (140) since 2026-09-12, nationwide. There is deliberately NO
# `state_fips = ANY(%(states)s)` term here, unlike `_GROWTH_SQL` and `_ECON_SQL`: joining
# `geo_area` IS the scope, and `geo_area` is now loaded for every state rather than for the six
# `market_state` named, so a tract in any state gets its figure with no code change. The two
# coarser builders keep their state term because their geographies are still loaded per state.
_INCOME_SQL = """
SELECT g.geo_id, a.estimate, a.moe
  FROM geo_area g
  JOIN acs_measure a ON a.geo_id = g.geo_id AND a.summary_level = '140' AND a.vintage = %(av)s AND a.variable = 'B19013_001E'
 WHERE g.summary_level = '140' AND g.vintage = %(gv)s
"""

_GROWTH_SQL = """
SELECT g.geo_id, now_.estimate, prior.estimate
  FROM geo_area g
  JOIN acs_measure now_ ON now_.geo_id = g.geo_id AND now_.summary_level = '160' AND now_.vintage = %(av)s AND now_.variable = 'B01003_001E'
  JOIN acs_measure prior ON prior.geo_id = g.geo_id AND prior.summary_level = '160' AND prior.vintage = %(pv)s AND prior.variable = 'B01003_001E'
 WHERE g.summary_level = '160' AND g.vintage = %(gv)s AND g.state_fips = ANY(%(states)s)
"""

_ECON_SQL = """
SELECT g.geo_id, c.annual_payroll_k, c.establishments, c.flag
  FROM geo_area g
  JOIN cbp_industry c ON c.geo_id = g.geo_id AND c.summary_level = '050' AND c.vintage = %(cv)s AND c.naics_code = '541940'
 WHERE g.summary_level = '050' AND g.vintage = %(gv)s AND g.state_fips = ANY(%(states)s)
"""

_Row = tuple[str, str, str, str, float | None, str, bool, str | None, float | None, bool, str | None, str, str]


def _as_float(x: Decimal | float | None) -> float | None:
    """psycopg2 hands back a `Decimal` for a numeric column, an `int` for an integer one and
    `None` for a NULL, and `float(None)` raises -- so the widening happens once, here, rather than
    at six call sites.

    It is NOT `frontend/src/logic.js:202`'s `num()`, which strips every character but digits and a
    dot and therefore turns `-5.1` into `5.1`: a decline would read as growth.
    `float(Decimal("-10"))` is `-10.0`, and
    `tests/census/test_geo_metric.py::test_a_declining_place_keeps_its_minus_sign` is the case
    that catches it if that ever stops being true."""
    return None if x is None else float(x)


def _row(geo_id: str, level: str, vintage: str, key: str, value: float | None, unit: str, *,
         derived: bool = False, moe: float | None = None, suppressed: bool = False,
         reason: str | None = None, source: str = "acs5", inputs: dict[str, object]) -> _Row:
    return (
        geo_id, level, vintage, key, value, unit, derived, M.FORMULA_VERSION if derived else None,
        moe, suppressed, reason, json.dumps(inputs), source,
    )


def _income(cur: psycopg2.extensions.cursor, act: dict[str, str], states: list[str]) -> list[_Row]:
    """Median household income at the CENSUS TRACT, as loaded -- `is_derived = False`, because at
    '140' it is a published ACS estimate with its own published margin, not a weighted average
    (D-NS4). The uniform `(cur, act, states)` signature is what `_BUILDERS` dispatches on; `states`
    is unused here for the reason in `_INCOME_SQL`'s comment."""
    cur.execute(_INCOME_SQL, {"av": act["acs5"], "gv": act["tiger_cb"]})
    out: list[_Row] = []
    for geo_id, estimate, moe in cur.fetchall():
        value, margin = _as_float(estimate), _as_float(moe)
        suppressed, reason = _suppression(value, margin)
        out.append(_row(geo_id, "140", act["acs5"], "median_hh_income", value, "usd", moe=margin,
                        suppressed=suppressed, reason=reason, source="acs5",
                        inputs={"acs5": act["acs5"], "geo_level": "tract"}))
    return out


def _growth(cur: psycopg2.extensions.cursor, act: dict[str, str], states: list[str]) -> list[_Row]:
    cur.execute(_GROWTH_SQL, {"av": act["acs5"], "pv": act["acs5_prior"], "gv": act["tiger_cb"], "states": states})
    out: list[_Row] = []
    for geo_id, now_, prior in cur.fetchall():
        value = M.population_growth_pct(_as_float(now_), _as_float(prior))
        # No `moe`, and no `_suppression`: a difference of two ACS 5-year estimates has no
        # published combined margin, and running it through `_suppression` with `moe = None` would
        # return `(True, 'no_moe')` and grey out every growth polygon in the country (D-NS17).
        out.append(_row(geo_id, "160", act["acs5"], "population_growth_pct", value, "pct", derived=True,
                        source="acs5",
                        inputs={"acs5": act["acs5"], "acs5_prior": act["acs5_prior"], "geo_level": "place"}))
    return out


def _econ(cur: psycopg2.extensions.cursor, act: dict[str, str], states: list[str]) -> list[_Row]:
    cur.execute(_ECON_SQL, {"cv": act["cbp"], "gv": act["tiger_cb"], "states": states})
    out: list[_Row] = []
    for geo_id, payroll_k, establishments, flag in cur.fetchall():
        value = M.revenue_per_establishment(_as_float(payroll_k), _as_float(establishments))
        # CBP is a census of establishments, not a sample, so there is no margin to test -- the one
        # thing that hides a county is the Census Bureau's own WITHHOLDING flag (§6), which is not
        # the same fact as its noise level. `_cbp_suppression` is IMPORTED, like `_suppression`
        # beside it: this line read `bool(flag)` until 2026-09-12 and greyed every county in the
        # country over `EMP_N=0;PAYANN_N=0`, a cell the Census published cleanly and the docked
        # panel has been showing all along (D-L1).
        suppressed, reason = _cbp_suppression(flag)
        out.append(_row(geo_id, "050", act["cbp"], "revenue_per_establishment", value, "usd", derived=True,
                        suppressed=suppressed, reason=reason, source="cbp",
                        inputs={"cbp": act["cbp"], "geo_level": "county",
                                "note": "payroll per establishment, not revenue", "cbp_noise": flag}))
    return out


_BUILDERS = {"median_hh_income": _income, "population_growth_pct": _growth, "revenue_per_establishment": _econ}


def _rewrite(conn: psycopg2.extensions.connection, level: str, metric_key: str, vintage: str, rows: list[_Row]) -> int:
    """One transaction per (level, metric, vintage) -- D-NS7. Production connections come from
    `app.db`'s pool with `autocommit=True`, so without this a failure between the DELETE and the
    INSERT would leave a layer half-written; `materialize_listing`'s own shape, restored in a
    `finally` so this is safe whatever the caller's autocommit state."""
    previous_autocommit = conn.autocommit
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(_DELETE, (level, metric_key, vintage))
            cur.executemany(_UPSERT, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = previous_autocommit
    return len(rows)


def materialize_geo(conn: psycopg2.extensions.connection, redis: redis_sync.Redis) -> dict[str, int]:
    """Rebuild `geo_metric` for every geography in a `market_state` state, at the three ruled
    levels. Returns `{metric_key: rows_written}`.

    A layer whose dataset (or whose SECOND dataset) is not licence-cleared, or which has no active
    vintage, writes nothing and reports 0: the trigger would refuse the write anyway (D-NS3), and a
    nightly run must not fail because the VIN Foundation withdrew a licence."""
    reg = load_registry(conn)
    act = active(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
        states = [r[0] for r in cur.fetchall()]
    written: dict[str, int] = {}
    for metric_key, level, dataset, extra in LAYERS:
        needed = ("tiger_cb", dataset, *extra)
        if any(act.get(k) is None for k in needed) or not all(reg[k].cleared for k in (dataset, *extra)):
            written[metric_key] = 0
            continue
        with conn.cursor() as cur:
            rows = _BUILDERS[metric_key](cur, act, states)
        written[metric_key] = _rewrite(conn, level, metric_key, act[dataset], rows)
    redis.set(GEO_VERSION_KEY, time.time_ns())
    return written
