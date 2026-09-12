"""Materialise `market_metric` rows per (listing, band, metric, vintage) -- spec §7, §8, §14;
plan D9-D12; Task B4b. The only writer of `market_metric`. Bands: `place` (the design's city
figures) and `drive_10`/`drive_20` (catchments, `app.census.catchment`).

Calls `app.census.metrics` (Task B4a, merged into the trunk): its eleven signatures are fixed and
are not changed here.

Two corrections carried from B4a's review (A-C17 (1)) live HERE rather than in `metrics.py`,
because they are about how a raw ACS estimate is COMBINED, not about a formula: `_suppression`
below treats a present estimate with a missing margin of error as unmeasured -- suppressed with
its own reason (`no_moe`), never silently read as certain the way a missing MOE would otherwise
be (`metrics.cv`/`metrics.high_moe` both return "not high" for a `None` moe, which is correct for
THEM -- they cannot invent a number that was never reported -- but wrong for a caller that treats
their "not high" as "safe to show").

Two corrections carried from the Phase B pre-flight (A-C19): the module deletes a band's existing
`market_metric` rows before rewriting it (`_DELETE_BAND`, called once per band actually
recomputed), so a change of active vintage cannot leave two generations of one metric in one band
-- `ON CONFLICT` alone only replaces a row whose (listing, band, metric, vintage) key already
matches, and a new vintage is a new key. And the Redis cache-version stamp uses
`time.time_ns()`, not a whole-second `int(time.time())`: two materialisations of the same listing
inside one wall-clock second must not collide on the same version and leave a client reading
stale figures.

`active_geo_vintage()` exists so `app.tasks.census.backfill_listing` can reach the active
`tiger_cb` vintage WITHOUT importing `app.census.vintage` itself: a committed AST guard
(`tests/test_tasks_never_activates_vintage.py`) walks every module under `app/tasks/` and fails
on any import of `app.census.vintage`, however indirect the need -- `app/tasks/census.py` calls
this module's own wrapper instead."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from typing import cast

import psycopg2.extensions
import redis as redis_sync

from app.census import metrics as M
from app.census.registry import load as load_registry
from app.census.vintage import active

BANDS: tuple[str, ...] = ("place", "drive_10", "drive_20")

_MetricRow = tuple[str, str, str, str, float | None, str, bool, str | None, float | None, bool, str | None, str, str | None]

_UPSERT = """
INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived, formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at, inputs)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
ON CONFLICT (listing_id, band, metric_key, vintage) DO UPDATE SET value_num = EXCLUDED.value_num, unit = EXCLUDED.unit, is_derived = EXCLUDED.is_derived,
  formula_version = EXCLUDED.formula_version, moe = EXCLUDED.moe, suppressed = EXCLUDED.suppressed, suppress_reason = EXCLUDED.suppress_reason,
  source_dataset = EXCLUDED.source_dataset, computed_at = now(), inputs = EXCLUDED.inputs
"""

# A-C19: deletes a band's rows before rewriting it, so a vintage change cannot leave a stale
# generation behind that no longer matches ON CONFLICT's key.
_DELETE_BAND = "DELETE FROM market_metric WHERE listing_id = %s AND band = %s"

_PLACE_ZCTA_SQL = """
SELECT z.geo_id, LEAST(1.0, ST_Area(ST_Intersection(ST_Transform(z.geom,4326)::geography, ST_Transform(p.geom,4326)::geography)) / NULLIF(ST_Area(ST_Transform(z.geom,4326)::geography),0))
FROM geo_area p JOIN geo_area z ON z.summary_level='860' AND z.vintage=p.vintage AND ST_Intersects(z.geom, p.geom)
WHERE p.summary_level='160' AND p.vintage=%s AND p.geo_id=%s
"""

BandInputs = tuple[float | None, float | None, float | None, float | None, float | None, float | None, bool, dict[str, float]]
Competition = tuple[float, str, bool, str, dict[str, object]]


def active_geo_vintage(conn: psycopg2.extensions.connection) -> str:
    """The active `tiger_cb` vintage, reached through this module rather than
    `app.census.vintage` directly -- see the module docstring. Raises `RuntimeError` (never a
    bare `KeyError`/`None`) when nobody has activated a TIGER boundary vintage yet: there is no
    catchment to build without one."""
    vintage = active(conn).get("tiger_cb")
    if vintage is None:
        raise RuntimeError("tiger_cb has no active vintage yet; run `census_load.py tiger` then `activate` before backfilling a listing")
    return vintage


def _acs(cur: psycopg2.extensions.cursor, level: str, geo_ids: Iterable[str], vintage: str, variable: str) -> dict[str, tuple[float | None, float | None]]:
    cur.execute(
        "SELECT geo_id, estimate, moe FROM acs_measure WHERE summary_level=%s AND vintage=%s AND variable=%s AND geo_id = ANY(%s)",
        (level, vintage, variable, list(geo_ids)),
    )
    return {g: (float(e) if e is not None else None, float(mo) if mo is not None else None) for g, e, mo in cur.fetchall()}


def _one(cur: psycopg2.extensions.cursor, level: str, geo_id: str, vintage: str, variable: str) -> tuple[float | None, float | None]:
    return _acs(cur, level, [geo_id], vintage, variable).get(geo_id, (None, None))


def _zbp(cur: psycopg2.extensions.cursor, zctas: Iterable[str], vintage: str) -> dict[str, int]:
    cur.execute(
        "SELECT geo_id, establishments FROM zbp_industry WHERE summary_level='860' AND vintage=%s AND naics_code='541940' AND geo_id = ANY(%s)",
        (vintage, list(zctas)),
    )
    return dict(cur.fetchall())


def _suppression(value: float | None, moe: float | None) -> tuple[bool, str | None]:
    """A-C17 (1): a present VALUE with a missing MOE is unmeasured, not certain -- suppressed with
    its own reason (`no_moe`), distinct from `high_moe` (a MOE that IS present but too wide). A
    missing value has nothing to suppress: there is no row content to falsely read as certain."""
    if value is None:
        return False, None
    if moe is None:
        return True, "no_moe"
    if M.high_moe(value, moe):
        return True, "high_moe"
    return False, None


#: CBP's `EMP_N`/`PAYANN_N` noise LEVELS, as `app/census/cbp.py` asks for them and `_flags`
#: joins them: 0 none, 1 low, 2 medium, 3 high. None of the four withholds anything.
_CBP_NOISE_LEVELS = frozenset("0123")


def _cbp_suppression(flag: str | None) -> tuple[bool, str | None]:
    """Whether a `cbp_industry.flag` string means the Census WITHHELD the cell (D-L1, 2026-09-12).

    The one decision both writers make about one column, so `market_metric` and `geo_metric`
    cannot disagree about the same county the way they did until this function existed: the map's
    writer suppressed on the flag's TRUTHINESS and hid all 392 counties in the country, while the
    docked panel served the same row as "$819K".

    CBP's disclosure avoidance has been NOISE INFUSION rather than cell suppression since the 2018
    release, which is why `app/census/cbp.py` asks for `EMP_N`/`PAYANN_N` ("Noise range for ...")
    and there is no `_F` withholding variable in `2022/cbp` to ask for; `_flags` joins whatever
    came back as `KEY=VALUE[;KEY=VALUE]`, so the string a real county carries is
    `EMP_N=0;PAYANN_N=0` -- noise level ZERO on both fields, published cleanly.

    So: **noise never suppresses, at any level.** A noise range is a statement about PRECISION,
    not about availability, and greying a county whose payroll the Census published is the mirror
    image of fabricating one -- the Census spec's §21 forbids both directions ("never render
    unknown when the value is known"). At the payroll layer's own class breaks ($450K / $650K /
    $900K) even the highest published noise level, 3, cannot move a county more than a fraction of
    a band, so there is nothing for a `band_ambiguous`-style caveat to warn about either; the
    level itself is carried into `inputs` by both writers, so a later ruling can surface it
    without a second read of the source.

    Anything the loader could not have produced as a noise pair -- a withholding code (`D`, `S`),
    an unknown key, a level outside 0-3 -- FAILS CLOSED and suppresses as `source_flag`, because
    an unrecognised flag is not evidence that a cell may be shown."""
    if not flag:
        return False, None
    for part in flag.split(";"):
        key, sep, value = part.partition("=")
        if not (sep and key.endswith("_N") and value in _CBP_NOISE_LEVELS):
            return True, "source_flag"
    return False, None


def _row(
    lid: str, band: str, key: str, vintage: str, value: float | None, unit: str, *,
    derived: bool = False, moe: float | None = None, suppressed: bool = False, reason: str | None = None,
    source: str = "acs5", inputs: dict[str, object] | None = None,
) -> _MetricRow:
    return (
        lid, band, key, vintage, value, unit, derived, M.FORMULA_VERSION if derived else None, moe,
        suppressed, reason, source, json.dumps(inputs) if inputs else None,
    )


class _Ctx:
    def __init__(self, conn: psycopg2.extensions.connection, listing_id: str) -> None:
        reg = load_registry(conn)
        act = active(conn)
        acs_v = act.get("acs5")
        geo_v = act.get("tiger_cb")
        if not (acs_v and geo_v):
            raise RuntimeError("acs5 and tiger_cb must have active vintages before materialising")
        self.acs_v: str = acs_v
        self.geo_v: str = geo_v
        self.prior_v: str | None = act.get("acs5_prior")
        self.cbp_v: str | None = act.get("cbp")
        self.zbp_v: str | None = act.get("zbp")
        self.use_cbp: bool = bool(self.cbp_v) and reg["cbp"].cleared
        self.use_zbp: bool = bool(self.zbp_v) and reg["zbp"].cleared
        self.use_prior: bool = bool(self.prior_v) and reg["acs5_prior"].cleared
        with conn.cursor() as cur:
            cur.execute("SELECT county_geoid, place_geoid FROM practice_location WHERE listing_id = %s", (listing_id,))
            row = cast("tuple[str | None, str | None] | None", cur.fetchone())
            self.county, self.place = row if row else (None, None)
            self.us_income: float | None = _one(cur, "010", "1", self.acs_v, "B19013_001E")[0]
            self.cbp: tuple[int | None, int | None, str | None] | None = None
            if self.use_cbp and self.county:
                cur.execute(
                    "SELECT establishments, annual_payroll_k, flag FROM cbp_industry WHERE geo_id=%s AND summary_level='050' AND vintage=%s AND naics_code='541940'",
                    (self.county, self.cbp_v),
                )
                self.cbp = cast("tuple[int | None, int | None, str | None] | None", cur.fetchone())
            self.county_hh: float | None = _one(cur, "050", self.county, self.acs_v, "B11001_001E")[0] if self.county else None
            self.growth: float | None = None
            self.growth_inputs: dict[str, object] | None = None
            if self.use_prior and self.prior_v:
                for level, gid in (("160", self.place), ("050", self.county)):
                    if not gid:
                        continue
                    now, prior = _one(cur, level, gid, self.acs_v, "B01003_001E")[0], _one(cur, level, gid, self.prior_v, "B01003_001E")[0]
                    g = M.population_growth_pct(now, prior)
                    if g is not None:
                        self.growth = g
                        self.growth_inputs = {"acs5": self.acs_v, "acs5_prior": self.prior_v, "geo_level": "place" if level == "160" else "county"}
                        break


def _competition(cur: psycopg2.extensions.cursor, ctx: _Ctx, zcta_weights: dict[str, float], hh_e: float | None) -> Competition | None:
    """Returns `(establishments, source, derived, vintage, inputs)` or `None`. ZBP over ZCTAs
    first; county apportionment (CBP) fallback."""
    if ctx.use_zbp and zcta_weights and ctx.zbp_v:
        counts = _zbp(cur, zcta_weights.keys(), ctx.zbp_v)
        parts: list[tuple[float | None, float | None, float | None]] = [(float(counts[z]) if z in counts else None, None, w) for z, w in zcta_weights.items()]
        est, _, _ = M.weighted_count(parts)
        if est is not None:
            return est, "zbp", False, ctx.zbp_v, {"zbp": ctx.zbp_v, "geo_level": "zcta", "zctas": len(zcta_weights), "naics": "541940"}
    if ctx.cbp and ctx.county_hh and hh_e and ctx.cbp_v:
        estab = ctx.cbp[0]
        if estab is not None:
            est = float(estab) * (hh_e / ctx.county_hh)
            return est, "cbp", True, ctx.cbp_v, {"cbp": ctx.cbp_v, "acs5": ctx.acs_v, "geo_level": "county", "method": "county_apportioned", "naics": "541940"}
    return None


def _band_inputs(cur: psycopg2.extensions.cursor, ctx: _Ctx, listing_id: str, band: str) -> BandInputs | None:
    """Returns `(pop, pop_moe, hh, hh_moe, income, income_moe, income_is_approx, zcta_weights)`."""
    if band == "place":
        if not ctx.place:
            return None
        pop = _one(cur, "160", ctx.place, ctx.acs_v, "B01003_001E")
        hh = _one(cur, "160", ctx.place, ctx.acs_v, "B11001_001E")
        inc = _one(cur, "160", ctx.place, ctx.acs_v, "B19013_001E")
        cur.execute(_PLACE_ZCTA_SQL, (ctx.geo_v, ctx.place))
        zw = {g: float(w) for g, w in cur.fetchall()}
        return pop[0], pop[1], hh[0], hh[1], inc[0], inc[1], False, zw
    cur.execute("SELECT summary_level, geo_id, overlap_frac FROM practice_catchment WHERE listing_id=%s AND band=%s AND vintage=%s", (listing_id, band, ctx.geo_v))
    tw: dict[str, float] = {}
    zw = {}
    for level, g, w in cur.fetchall():
        (tw if level == "140" else zw)[g] = float(w)
    if not tw:
        return None
    pop_by_geo = _acs(cur, "140", tw, ctx.acs_v, "B01003_001E")
    hh_by_geo = _acs(cur, "140", tw, ctx.acs_v, "B11001_001E")
    inc_by_geo = _acs(cur, "140", tw, ctx.acs_v, "B19013_001E")
    pop_e, pop_m, _ = M.weighted_count([(*pop_by_geo.get(g, (None, None)), w) for g, w in tw.items()])
    hh_e, hh_m, _ = M.weighted_count([(*hh_by_geo.get(g, (None, None)), w) for g, w in tw.items()])
    inc_e = M.weighted_median([(inc_by_geo.get(g, (None, None))[0], (hh_by_geo.get(g, (None, None))[0] or 0) * w) for g, w in tw.items()])
    return pop_e, pop_m, hh_e, hh_m, inc_e, None, True, zw


def materialize_listing(conn: psycopg2.extensions.connection, redis: redis_sync.Redis, listing_id: str) -> int:
    """Rebuilds every `market_metric` row for `listing_id` across all three bands, from the
    currently active vintages. Deletes a band's own rows before rewriting it (A-C19). Bumps the
    listing's Redis cache-version key on every call, even one that writes zero rows -- a caller
    that just changed the licence gate or the active vintage still needs stale panels to expire.
    Returns the number of rows written.

    A-C21 (2): the whole rewrite is one transaction, the same guard `app.census.catchment.build`
    already uses for the same reason -- production connections come from `app.db`'s pool with
    `autocommit=True` (each statement commits the instant it runs), so a failure between one
    band's DELETE and the final INSERT would otherwise leave a listing with only part of its
    figures. `conn.autocommit` is toggled off for the duration and restored afterwards, so this
    is safe to call regardless of the caller's own autocommit state."""
    ctx = _Ctx(conn, listing_id)
    rows: list[_MetricRow] = []
    previous_autocommit = conn.autocommit
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            for band in BANDS:
                got = _band_inputs(cur, ctx, listing_id, band)
                if got is None:
                    continue
                cur.execute(_DELETE_BAND, (listing_id, band))
                pop_e, pop_m, hh_e, hh_m, inc_e, inc_m, inc_approx, zw = got
                geo_level = "place" if band == "place" else "catchment"
                pop_sup, pop_reason = _suppression(pop_e, pop_m)
                hh_sup, hh_reason = _suppression(hh_e, hh_m)
                inc_sup, inc_reason = (False, None) if inc_approx else _suppression(inc_e, inc_m)
                base: dict[str, object] = {"acs5": ctx.acs_v, "geo_level": geo_level}
                rows.append(_row(listing_id, band, "population", ctx.acs_v, pop_e, "count", moe=pop_m, suppressed=pop_sup, reason=pop_reason, inputs=base))
                rows.append(_row(listing_id, band, "households", ctx.acs_v, hh_e, "count", moe=hh_m, suppressed=hh_sup, reason=hh_reason, inputs=base))
                rows.append(_row(
                    listing_id, band, "median_hh_income", ctx.acs_v, inc_e, "usd", derived=inc_approx, moe=inc_m,
                    suppressed=inc_sup, reason=inc_reason,
                    inputs={**base, "note": "household-weighted average of tract medians"} if inc_approx else base,
                ))
                rows.append(_row(
                    listing_id, band, "pet_households_est", ctx.acs_v, M.pet_households_est(hh_e), "count", derived=True,
                    suppressed=hh_sup, reason="input_suppressed" if hh_sup else None, inputs={**base, "pet_incidence_rate": M.PET_RATE},
                ))
                rows.append(_row(listing_id, band, "income_index_vs_us", ctx.acs_v, M.income_index_vs_us(inc_e, ctx.us_income), "pct", derived=True, inputs=base))
                if ctx.growth is not None and ctx.growth_inputs is not None:
                    rows.append(_row(listing_id, band, "population_growth_pct", ctx.acs_v, ctx.growth, "pct", derived=True, inputs=ctx.growth_inputs))
                comp = _competition(cur, ctx, zw, hh_e)
                if comp is not None:
                    est, source, derived, comp_vintage, comp_inputs = comp
                    per10k = M.vets_per_10k(est, hh_e)
                    rows.append(_row(listing_id, band, "establishments", comp_vintage, est, "count", derived=derived, source=source, inputs=comp_inputs))
                    rows.append(_row(
                        listing_id, band, "vets_per_10k_households", ctx.acs_v, per10k, "ratio", derived=True, source=source,
                        suppressed=hh_sup, reason="input_suppressed" if hh_sup else None, inputs={**comp_inputs, "acs5": ctx.acs_v},
                    ))
                    if ctx.cbp and ctx.cbp_v:
                        # D-L1: the flag's CONTENT, through the one function `geo_metric._econ`
                        # also calls. Until 2026-09-12 this row read the column and ignored it
                        # while the map's writer suppressed on its truthiness.
                        cbp_sup, cbp_reason = _cbp_suppression(ctx.cbp[2])
                        rows.append(_row(
                            listing_id, band, "revenue_per_establishment", ctx.cbp_v, M.revenue_per_establishment(ctx.cbp[1], ctx.cbp[0]), "usd",
                            derived=True, source="cbp", suppressed=cbp_sup, reason=cbp_reason,
                            inputs={"cbp": ctx.cbp_v, "geo_level": "county", "note": "payroll per establishment, not revenue", "cbp_noise": ctx.cbp[2]},
                        ))
                    score = M.opportunity_score(inc_e, ctx.growth, per10k)
                    if score is not None:
                        # A-C21 (1): the score is built from income and per10k (itself
                        # households-driven) -- if either of those inputs is unmeasured, the
                        # composite built on top of them is too, not a confident-looking number
                        # with nothing to show it.
                        score_sup = hh_sup or inc_sup
                        rows.append(_row(
                            listing_id, band, "opportunity_score", ctx.acs_v, float(score), "score", derived=True, source="acs5",
                            suppressed=score_sup, reason="input_suppressed" if score_sup else None,
                            inputs={**comp_inputs, "acs5": ctx.acs_v, "acs5_prior": ctx.prior_v, "components": {"income": inc_e, "growth": ctx.growth, "vets_per_10k": per10k}},
                        ))
            cur.executemany(_UPSERT, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = previous_autocommit
    # A-C19: nanosecond resolution -- `int(time.time())` truncates to whole seconds, and two
    # materialisations of the same listing inside one second would otherwise stamp the same
    # version and leave a client's cache reading stale figures.
    redis.set(f"listing:{listing_id}:market:version", time.time_ns())
    return len(rows)


def materialize_all(conn: psycopg2.extensions.connection, redis: redis_sync.Redis) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT listing_id FROM practice_location")
        ids = [str(r[0]) for r in cur.fetchall()]
    return {lid: materialize_listing(conn, redis, lid) for lid in ids}
