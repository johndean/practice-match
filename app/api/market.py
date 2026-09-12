"""Read-only market-data endpoints (Census spec §7/§10/§12; plan Task B5; controller amendments
A-C13 through A-C22). Reads `market_metric` + `geo_area` + `dataset_registry` only: never a Census
call on the request path, and a miss for a real published listing enqueues one backfill and returns
the empty state.

**Amended 2026-09-07 (Wave 2a Task I9a): there is no `app/api/access.py`.** `app/config.py`'s
`market_data_public` (Task I3) means exactly what `app.auth.permissions.allowed` already decides: it
grants `market.read` to `anonymous` while the flag is set, so every route below carries nothing but
`Depends(require("market.read"))`, resolved ONCE at import time into the module-level
`REQUIRE_MARKET_READ` constant (Global Constraint (g); the route-guard and audit drift tests in
`tests/auth/test_permissions.py` resolve a guard by its object IDENTITY, so a wrapper — or a fresh
`require(...)` call per router — reads as unguarded). A second `access.py` deciding the same rule a
second way is exactly the drift this avoided. `A-C13 (11)`: this router's own routes must not trip
the committed guard `tests/api/test_listings.py::test_the_listings_routes_are_guarded_not_public`
runs over every mounted path under the `/api/listings` prefix — `/api/listings/{id}/market` is
guarded by `market.read`, not `listing.read`, and that test names it explicitly rather than
asserting a single blanket permission for the whole prefix.

**Corrections applied here, each found by pre-flight or review before this task started (see the
task brief's own "Corrections to the brief" list); the point is to not rediscover them:**

1. `app.db.engine` is a FUNCTION — `engine()` — not a ready-built object. Every handler below opens
   its async connection with `engine().connect()`.
2. A layer's state is three-valued: `dataset_registry.license_status` is `cleared` / `unresolved` /
   `blocked` (migration `017`'s own CHECK constraint), and `/api/layers` carries that as `state`:
   `enabled` / `disabled` / `blocked` (+ `blocked_reason` when blocked) — never a boolean. "Off
   because it is not yet cleared" (`disabled`, a licence still pending a decision) and "off because
   the licence was refused" (`blocked`, permanently) are different facts the admin surface and a
   member both need distinguishable (A-C14 (4), B6's own contract).
3. **The opportunity score never appears in a payload.** It is computed and stored by the
   materialisation (Task B4b); every serialiser here skips the `market_metric` row entirely (not
   null, not a flag — absent) until the VIN Foundation signs off on its weights (A-C1 (9), A-C14
   (5)).
4. `market.read` is the ONLY dependency, and it is resolved once, at import — no per-request
   wrapping, no `access.py` indirection (see above).
5. Neither `/api/layers` nor `/api/markets/{cbsa}/communities` nor `/api/listings/{id}/market` calls
   `app.census.gate.layer_enabled`: every one of them already reads `dataset_registry` LIVE, through
   the same async connection it uses for attribution/vintage — a second, Redis-cached read of the
   same fact through a SEPARATE synchronous connection would be pure waste, and worse, doing it the
   way the brief's own illustrative code did (`gate.layer_enabled(r, sync_conn, ds)`, passing the
   bare pooled-connection FACTORY rather than a closed-over already-open connection) leaks one pooled
   connection into `app.db`'s reuse pool on every cache miss — `app.census.gate`'s own docstring
   says a caller must pass `lambda: conn` from inside its own `closing(sync_conn()) as conn` block,
   never the factory itself. `gate.version()` (the 60 s licence-gate counter) is still exactly what
   keys the listing panel's 24 h cache — a decision on ANY dataset must still bust it — and
   `gate.invalidate()` is still what the admin console calls; this module just never needs the
   per-dataset cached boolean, because it is never more than one query away from the live answer.
6. **Growth's own gate is `acs5_prior cleared`,** not `acs5` — even though the `market_metric` row
   `app.census.materialize` writes for `population_growth_pct` is stamped `source_dataset='acs5'`
   (its formula combines two ACS vintages and a row carries exactly one dataset key). The generic
   per-`source_dataset` gate below cannot see an `acs5_prior` licence change for this one field, so
   both serialisers check it explicitly.
7. `communities()`/`listing_market()` never assert a literal Redis queue length: the effect this
   module is responsible for is "exactly one backfill enqueued, by name, for a REAL published
   listing with no metrics yet" — `celery_app.send_task` is called for exactly that, and it is what
   a test should watch (as `tests/census/test_geocode.py` already does for the same task), not a
   raw broker length a fake Redis client can never observe (`app.cache.sync_redis()` and celery's own
   kombu broker connection are two entirely different clients).
8. **The listing-panel cache key carries a `{band}` segment the plan's own illustrative text
   omits** (`listing:{id}:market:v{n}` there; `listing:{listing_id}:market:{band}:v{n}:g{gate.version()}`
   here, in `listing_market` below) — `band` is a query parameter this same route answers
   (`place`/`drive_10`/`drive_20`), and without it in the key a member requesting one band would be
   served whichever band's panel happened to be cached first (A-C23 (3)).
"""
from __future__ import annotations

import gzip
import json
import logging
import time
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from app.auth.deps import require
from app.cache import sync_redis
from app.census import gate
from app.census import metrics as M
from app.census.bands import HOUSEHOLDS_STOPS, INCOME_STOPS, band_ambiguous
from app.census.geo_metric import GEO_VERSION_KEY
from app.census.serve import _active, _extra_cleared, _registry
from app.db import engine
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Hoisted to a module-level constant, never wrapped (Global Constraint (g); correction 4 above).
REQUIRE_MARKET_READ = require("market.read")

PANEL_TTL = 86400
BACKFILL_DEDUPE_TTL = 600
BANDS: tuple[str, ...] = ("place", "drive_10", "drive_20")
DEFAULT_BLOCKED_REASON = "Licence not cleared."

BOUNDARY_TTL = 86400
# D-NS12, RE-MEASURED FOR CENSUS TRACTS (Task CAP, 2026-09-12). The caps are chosen against the
# GEOGRAPHY, not against a load test -- that part of D-NS12 stands. What did not stand is the
# number: `MAX_FEATURES = 4000` was sized when the granular layer was the ZCTA ("sits above the
# largest plausible single-metro ZCTA count"), and it was never re-measured when A24.19 made the
# Census TRACT the unit. On the stakeholder's own 1460 x 1228 screen that left New York's DEFAULT
# view -- the first request the app makes when the metro is chosen -- refused, and still refused a
# zoom level in.
#
# THE OLD ORDERING ARGUMENT IS RETIRED, not merely outgrown. It read "below the 6,884 tracts a
# whole-Texas box returns", which made the COUNT cap the thing that refuses a state. It is not:
# a whole-Texas box is about 13 degrees on a side and `MAX_BBOX_DEG` refuses it on SPAN before a
# single row is counted (`test_a_state_sized_box_is_still_refused_on_span_before_any_count`). The
# count cap is therefore free to be measured against what the map actually asks for -- and it has
# to be, since the largest first view is now 7,530, which is above 6,884.
#
# Measured on QA's own PostGIS, read-only, through this module's own `_BOUNDARY_SQL` and the byte
# arithmetic `compose()` performs (2026-09-12; the full table is in `tests/census/test_boundaries`
# above `NY_DEFAULT_VIEW`). Bytes at delivery tier 0 / 1-4000 / 1-2000 / 1-1000 of the box's span:
#
#   view (1460 x 1228 px)                    tracts   raw bytes at each tier
#   New York default, padded (what is sent)   7,470   6,538,264 / 4,254,031 / 3,662,228 / 3,267,466
#   New York default, bare (the one retry)    5,262   4,268,451 / 3,058,406 / 2,667,225 / 2,356,180
#   Manhattan-centred z10, padded             7,530   6,587,141 / 4,269,628 / 3,670,796 / 3,271,014
#   Manhattan-centred z11, padded             4,709   3,660,966 / 2,717,359 / 2,419,824 / 2,137,523
#   densest 4 x 4 deg box in the country      9,767   9,705,776 / 5,824,182 / 4,911,729 / 4,315,325
#
# `MAX_BBOX_DEG` is UNCHANGED at 4.0 and is what refuses a state.
#
# `MAX_FEATURES` is measured against the densest box the SPAN cap admits: 9,767 tracts, found by
# sweeping 4-degree windows on a half-degree lattice over the lower 48 (the New York-Philadelphia
# corridor, near 40.5N 75.0W). 12,000 clears it by 23 %, which also covers the coarseness of that
# lattice -- a finer sweep would find a slightly denser window. So the count cap no longer stands
# in front of the byte cap for anything this route can legally be asked for; it is the guard
# against a geography denser than today's, and the refusal below still names it when it is hit.
#
# `MAX_BODY_BYTES` is measured against the largest FIRST VIEW, Manhattan-centred at zoom 10:
# 4,269,628 bytes at a tolerance of 1/4000 of the box's span, which at zoom 10 is 0.59 CSS px of
# longitude and 0.78 px of latitude -- a generalisation no member can see. 6,000,000 clears that by
# 40 %, and clears the densest legal box at the same tier (5,824,182) as well, so every box the
# route accepts is served rather than refused. It is not set high enough to serve those views at
# tier 0 (6.5 MB), deliberately: the ladder exists so that the wire pays for pixels a member can
# see and nothing more. The wire itself is gzip -- the New York first view is 652,848 bytes
# compressed at the tier it is served at, against 1,105,917 at tier 0.
MAX_BBOX_DEG = 4.0
MAX_FEATURES = 12000
MAX_BODY_BYTES = 6_000_000

# Delivery generalisation, as a fraction of the request's own longest span, tried in order until
# the body fits `MAX_BODY_BYTES`. MEASURED on real TIGER tract geometry, not chosen by feel:
#
#   * 0.0 -- serve the exact outline. Every metro-zoom viewport measured fits here (Austin 568
#     tracts / 0.949 MB, Dallas 1,410 / 1.303 MB, Atlanta 1,037 / 1.100 MB, SF 1,093 / 1.043 MB)
#     and every one of them is 0.0000 % uncovered, so neighbours share edges exactly and the
#     shading has no slivers. This is the stakeholder's target view and it pays nothing here.
#   * the three coarser rungs exist for the zoomed-out and the very dense: New York's whole-CBSA
#     envelope is 5,935 tracts / 5.079 MB and Atlanta's 2.912 MB, both of which were answered 422
#     before this ladder existed -- a blank map in three of six markets at tract scale.
#
# span/2000 is sub-pixel at a ~1200 px viewport, so a rung is invisible at the zoom it is served
# for; the coarsest rung costs 0.89 % of covered area at a whole-CBSA span, against the 2.29 % the
# fixture's 0.010 deg simplification lost. `ST_CoverageSimplify` would hold shared edges exactly,
# but the runtime image's GEOS is 3.9.0 and that function needs 3.12+, so it is not available here.
SIMPLIFY_TIERS: tuple[float, ...] = (0.0, 1 / 4000, 1 / 2000, 1 / 1000)

# D-C35's three geographies, and the label the legend prints. `income` moved 860 -> 140 on
# 2026-09-12 (controller ruling): the canonical granular unit is the Census TRACT, nationwide --
# tracts are designed as neighbourhood approximations and ACS publishes the variable at tract
# level, while calling a ZIP area a neighbourhood is a named prohibition. `growth` CANNOT follow:
# the 2010->2020 tract boundary change means a tract-level growth figure is not computable from
# what we hold (plan D12, a registered Phase C deferral), so it keeps place and `econ` keeps
# county -- and each carries its own label, which is how a coarse figure is never shown as
# granular. A NEW member on /api/layers rather
# than a change to `geo_level`: `income`'s geo_level is "place|catchment" and describes the
# PANEL's geography — the docked panel and the map answer different questions about the same
# layer (D-NS15).
SHADING: dict[str, dict[str, str]] = {
    "income": {"summary_level": "140", "label": "Census tract"},
    "growth": {"summary_level": "160", "label": "Place (city/town)"},
    "econ": {"summary_level": "050", "label": "County"},
    "households": {"summary_level": "140", "label": "Census tract"},
    "pets": {"summary_level": "140", "label": "Census tract"},
    "competition": {"summary_level": "860", "label": "ZIP Code Tabulation Area"},
}
# layer -> (metric_key, the dataset its geo_metric rows are STAMPED with, whose active vintage is
# therefore the value vintage).
BOUNDARY_METRIC: dict[str, tuple[str, str]] = {
    "income": ("median_hh_income", "acs5"),
    "growth": ("population_growth_pct", "acs5"),
    "econ": ("revenue_per_establishment", "cbp"),
    "households": ("households", "acs5"),
    "pets": ("pet_households_est", "acs5"),
    "competition": ("establishments", "zbp"),
}
# The layer's own unit, from `geo_metric.unit`. A count served as `usd` or `pct` is a wrong
# reading of the number, not a cosmetic slip -- it was `"usd" if layer in ("income", "econ") else
# "pct"` while only three layers shaded and every one of them was one or the other.
UNIT: dict[str, str] = {"income": "usd", "econ": "usd", "growth": "pct",
                        "households": "count", "pets": "count", "competition": "count"}
# The legend stops each layer's own `band_ambiguous` is judged against (`app.census.bands`).
# A layer absent here has no published margin at all, so the question cannot arise -- and asking
# it against the WRONG layer's stops is the failure this dict exists to make impossible.
BAND_STOPS: dict[str, tuple[int, ...]] = {"income": INCOME_STOPS, "households": HOUSEHOLDS_STOPS}

# D-NS11. The CASTs on `:tol` are load-bearing, not decoration: an UNTYPED bound parameter inside
# a `CASE WHEN` silently takes the ELSE branch under asyncpg. Measured on this database --
# `CASE WHEN 0.01 > 0 THEN ST_SimplifyPreserveTopology(geom, 0.01) ELSE geom END` gives 17 points,
# the same expression with `:tol` bound to 0.01 gives 460 (the unsimplified count), and the same
# call WITHOUT the CASE gives 17. No error is raised either way, so the failure mode is a response
# that is silently never generalised; `test_the_delivery_tolerance_actually_reaches_postgis` is
# the case that catches it, and it asserts vertex counts rather than body bytes for that reason.
# Three further things about it are deliberate. `ST_Transform(g.geom, 4326)` is required, not
# decorative: geo_area.geom is geometry(MultiPolygon, 4269) and GeoJSON is WGS84. The `6` is
# measured to be a NO-OP -- cb_500k already carries six or fewer decimals -- and is kept as an
# explicit ceiling. And the envelope is transformed INTO 4269 rather than the geometry column out
# of it, so the geo_area_geom_gix GiST index is usable on the predicate (an Austin z11 tract
# viewport: 49.8 ms).
_BOUNDARY_SQL = """
SELECT g.geo_id, g.name, m.value_num, m.moe, m.suppressed, m.suppress_reason,
       ST_AsGeoJSON(ST_Transform(CASE WHEN CAST(:tol AS double precision) > 0
            THEN ST_SimplifyPreserveTopology(g.geom, CAST(:tol AS double precision)) ELSE g.geom END, 4326), 6) AS geometry
  FROM geo_area g
  LEFT JOIN geo_metric m
    ON m.geo_id = g.geo_id AND m.summary_level = g.summary_level
   AND m.metric_key = :metric AND m.vintage = :value_vintage
 WHERE g.summary_level = :level AND g.vintage = :geo_vintage
   AND ST_Intersects(g.geom, ST_Transform(ST_MakeEnvelope(:w, :s, :e, :n, 4326), 4269))
 ORDER BY g.geo_id
"""

# Task SNAP (D-C50 as revised by the stakeholder, 2026-09-12): the METRO-WIDE distribution of one
# layer, over exactly the population `_BOUNDARY_SQL` would serve with no bbox -- same FROM, same
# WHERE, no geometry on the wire. The Browse snapshot strip's AREA mode reads it, so "the median
# the strip prints" and "the polygons the map shades" are the same set of rows by construction
# rather than by two pieces of code agreeing.
#
# Three things about it are deliberate:
#
#   * `percentile_cont`, not `percentile_disc` or a hand-rolled nearest rank -- the five fractions
#     are what the five bars draw, and an interpolating quantile is the one that describes a
#     distribution rather than naming five of its members. The MEDIAN is read out of the same
#     array (index 2) rather than computed a second time, so the value and the bars beside it can
#     never disagree.
#   * `::double precision` on both sides, explicitly: `geo_metric.value_num` is `numeric` and
#     `percentile_cont` takes `double precision`. Postgres would find the cast, and stating it
#     keeps the answer's type the same one the JSON carries.
#   * the FILTER clause, rather than trusting the ordered-set aggregate to skip nulls: a SUPPRESSED
#     row has a real `value_num` the publication rules hide, so it has to be excluded by its
#     verdict and not by its nullness -- and it is still COUNTED, because "eleven tracts, nine of
#     them summarisable" is the honest statement and "nine tracts" is not.
_SUMMARY_SQL = """
SELECT count(*) AS n,
       count(*) FILTER (WHERE m.value_num IS NOT NULL AND NOT m.suppressed) AS with_value,
       count(*) FILTER (WHERE m.suppressed) AS suppressed,
       percentile_cont(CAST(:fractions AS double precision[]))
           WITHIN GROUP (ORDER BY CAST(m.value_num AS double precision))
           FILTER (WHERE m.value_num IS NOT NULL AND NOT m.suppressed) AS quantiles
  FROM geo_area g
  LEFT JOIN geo_metric m
    ON m.geo_id = g.geo_id AND m.summary_level = g.summary_level
   AND m.metric_key = :metric AND m.vintage = :value_vintage
 WHERE g.summary_level = :level AND g.vintage = :geo_vintage
   AND ST_Intersects(g.geom, ST_Transform(ST_MakeEnvelope(:w, :s, :e, :n, 4326), 4269))
"""

#: The five fractions the snapshot's five bars are, in order. p10 and p90 rather than the extremes
#: because a single outlying tract is not a class the card should draw (the shape of the metro is
#: what the bars are for), and five rather than seven because five is what the endpoint publishes
#: and the card's bar row is `flex: 1` per bar -- it divides whatever space it has, so neither
#: count changes the card's approved layout.
SUMMARY_FRACTIONS: tuple[float, ...] = (0.1, 0.25, 0.5, 0.75, 0.9)
#: Which of them IS the median, read out of the same array rather than measured again.
SUMMARY_MEDIAN_AT = 2
SUMMARY_TTL = 86400
#: Every dataset whose ACTIVE VINTAGE the summary's cache key has to span. One body carries six
#: layers stamped with four datasets, so a key naming only the ACS vintage would go on serving a
#: stale ZIP Business Patterns card for a day after that dataset's own vintage was activated.
#: Derived from `BOUNDARY_METRIC` rather than typed, plus `acs5_prior` — growth's rows are stamped
#: `acs5` and its figure is a difference of two ACS periods (correction 6).
SUMMARY_DATASETS: tuple[str, ...] = tuple(sorted({s for _, s in BOUNDARY_METRIC.values()} | {"acs5_prior"}))

# §7, the other direction: a value whose geography the boundary vintage no longer carries. The
# writer never invents a shape and the endpoint never silently loses a row. Deliberately NOT
# narrowed by the bbox: "values whose geography is not in this viewport" would be non-zero on
# every zoomed request and would mean nothing. This counts values with no `geo_area` row at that
# level and vintage AT ALL, which is what §7's "a boundary vintage that has moved out from under
# the values" actually describes.
_ORPHAN_SQL = """
SELECT count(*) FROM geo_metric m
 WHERE m.summary_level = :level AND m.metric_key = :metric AND m.vintage = :value_vintage
   AND NOT EXISTS (SELECT 1 FROM geo_area g WHERE g.geo_id = m.geo_id AND g.summary_level = :level AND g.vintage = :geo_vintage)
"""

# The three-valued state B6's contract settled on, keyed off `dataset_registry.license_status`
# (migration 017's own CHECK constraint admits exactly these three strings).
_STATE_FOR = {"cleared": "enabled", "unresolved": "disabled", "blocked": "blocked"}

# The Census's OWN publication rule for ZIP-level industry detail, stated once and read in two
# places: this catalogue's `competition` caveat, and -- word for word -- the design's tooltip for a
# polygon `geo_metric` marked `source_threshold` (`tests/census/test_design_shading_labels.py`
# pins the two). A category under three establishments is not reported at the ZIP level but IS
# counted in the sum total, which is why `app/census/zbp.py` loads that total: it is the only way
# to tell a withheld count from a ZIP the dataset does not cover (review round 1, Important 3).
THRESHOLD_RULE = (
    "The Census does not publish a ZIP-level count for a category with fewer than three "
    "establishments, though they are counted in its all-industry total."
)

# The nine approved layers (Census spec §2 table + the layer-rendering contract). Labels are the
# design's; sources/vintages/state come from the registry at request time, never hard-coded.
LAYERS: list[dict[str, Any]] = [
    {"key": "income", "label": "Median Household Income", "dataset_key": "acs5", "metric": "median_hh_income", "is_derived": False, "caveat": None},
    {"key": "pets", "label": "Pet Ownership (est.)", "dataset_key": "acs5", "metric": "pet_households_est", "is_derived": True,
     "caveat": f"Derived estimate: households \u00d7 {M.PET_RATE} (national placeholder rate until a licensed regional rate is cleared)."},
    {"key": "growth", "label": "Population Growth", "dataset_key": "acs5_prior", "metric": "population_growth_pct", "is_derived": True, "geo_level": "place",
     "caveat": "Change between two ACS 5-year periods, measured for the listing's city/CDP."},
    {"key": "households", "label": "Households", "dataset_key": "acs5", "metric": "households", "is_derived": False, "caveat": None},
    {"key": "econ", "label": "Average Practice Payroll", "dataset_key": "cbp", "metric": "revenue_per_establishment", "is_derived": True, "geo_level": "county",
     "caveat": "Payroll per establishment (NAICS 541940), not revenue; county level."},
    {"key": "competition", "label": "Veterinary Competition", "dataset_key": "zbp", "metric": "establishments", "is_derived": False, "geo_level": "zcta",
     "caveat": "Establishment counts (NAICS 541940) include corporate-owned and specialty locations; a proxy for competitive density, not a count of independent practices. Published per ZIP code by ZIP Code Business Patterns, and shaded at the ZIP Code Tabulation Area, which is that dataset's own authoritative geography. " + THRESHOLD_RULE},
    {"key": "practices", "label": "Practice Listings", "dataset_key": None, "metric": None, "is_derived": False, "caveat": None},
    {"key": "drive_10", "label": "5\u201310 min drive time", "dataset_key": None, "metric": None, "is_derived": True, "caveat": "Straight-line 8 km approximation of drive time."},
    {"key": "drive_20", "label": "10\u201320 min drive time", "dataset_key": None, "metric": None, "is_derived": True, "caveat": "Straight-line 16 km approximation of drive time."},
]
FIELD_FOR = {"pop": "population", "hh": "households", "income": "median_hh_income", "growth": "population_growth_pct",
             "pets": "pet_households_est", "econ": "revenue_per_establishment", "vets": "establishments"}
LABELS = {"revenue_per_establishment": "Avg. payroll per practice"}
# Correction 3: `opportunity_score` is never emitted, by any serialiser in this module.
_NEVER_PUBLISHED = frozenset({"opportunity_score"})


def _error(code: str, message: str, status: int) -> JSONResponse:
    """Decision A5's body for the refusals this module raises itself (never a bare `HTTPException`,
    whose body would be `{"detail": ...}` — the same convention `app.api.listings`/
    `app.api.admin_data_sources` follow)."""
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _resolve_band(band: str | None, default: str) -> str | None:
    """The requested band, or the default when none was given; `None` when the caller asked for
    something that is not one of `BANDS` at all, which the route turns into decision A5's 422."""
    b = band or default
    return b if b in BANDS else None


def _parse_bbox(raw: str) -> tuple[float, float, float, float] | None:
    """`minLng,minLat,maxLng,maxLat`, or `None` when it is not four numbers in that order. Parsed
    by hand rather than through `Query(ge=…)` so a bad value gets decision A5's envelope, which is
    the shape `_resolve_band` already uses for BAD_BAND."""
    parts = raw.split(",")
    if len(parts) != 4:
        return None
    try:
        w, s, e, n = (float(p) for p in parts)
    except ValueError:
        return None
    if e <= w or n <= s:
        return None
    return w, s, e, n


def _is_uuid(value: str) -> bool:
    """`listing.id` is a `uuid` column (migration `016`); a path segment that is not one names no
    listing, so the route answers its own 404 rather than letting asyncpg refuse to bind the
    parameter at all (`DataError: invalid input for query argument`) -- the same posture
    `app.api.listings._parsed_uuid` already takes for the same column."""
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _layer_state(reg: dict[str, dict[str, Any]], dataset_key: str | None) -> tuple[str, str | None]:
    """`(state, blocked_reason)` for one layer — correction 2. A layer with no dataset at all
    (`practices`, the two drive-time rings) is always enabled. Every dataset `LAYERS` names (acs5,
    acs5_prior, cbp, zbp) is one of the rows migration `017` seeds and nothing ever deletes, and
    `license_status` carries that migration's own CHECK constraint — so `reg[dataset_key]` and
    `_STATE_FOR[...]` below are never a lookup on data that is not there; indexing directly is what
    keeps that guarantee visible instead of a defensive fallback quietly standing in for it (a
    branch nothing can reach is one no test can close)."""
    if dataset_key is None:
        return "enabled", None
    row = reg[dataset_key]
    state = _STATE_FOR[row["license_status"]]
    if state != "blocked":
        return state, None
    return state, row["notes"] or DEFAULT_BLOCKED_REASON


def _cleared(reg: dict[str, dict[str, Any]], dataset_key: str) -> bool:
    """Whether `dataset_key` is currently licence-cleared. Every caller reads `dataset_key` off a
    `market_metric.source_dataset` column (`NOT NULL REFERENCES dataset_registry`, migration `061`)
    or passes one of the literals `_extra_cleared` below names — never a value the registry does
    not carry — so `reg[dataset_key]` is indexed directly rather than defended against a `KeyError`
    the schema's own foreign key already rules out."""
    return bool(reg[dataset_key]["license_status"] == "cleared")


@router.get("/layers", dependencies=[Depends(REQUIRE_MARKET_READ)])
async def layers() -> Response:
    async with engine().connect() as conn:
        reg, act = await _registry(conn), await _active(conn)
    out = []
    for layer in LAYERS:
        ds = layer["dataset_key"]
        state, blocked_reason = _layer_state(reg, ds)
        vintage = (f"{act.get('acs5_prior')} → {act.get('acs5')}" if ds == "acs5_prior" else act.get(ds)) if ds else None
        entry: dict[str, Any] = {
            "key": layer["key"], "label": layer["label"], "dataset_key": ds,
            "source_label": reg[ds]["attribution_text"] if ds else None,
            "vintage": vintage, "geo_level": layer.get("geo_level", "place|catchment" if ds else None),
            # D-NS15: the geography the MAP shades this layer at, or null where it is not shaded at
            # all (the three graduated-symbol layers, `practices` and the two drive rings). A new
            # member, never a change to `geo_level` above, which describes the docked PANEL.
            "shading": SHADING.get(layer["key"]),
            "state": state, "is_derived": layer["is_derived"], "caveat": layer["caveat"],
        }
        if blocked_reason is not None:
            entry["blocked_reason"] = blocked_reason
        out.append(entry)
    return JSONResponse(out)


@router.get("/markets", dependencies=[Depends(REQUIRE_MARKET_READ)])
async def markets() -> Response:
    # Task CK: one row per (listing market key, CBSA), found by the practice's own COORDINATES --
    # never a name heuristic over the CBSA's official name (`short_market_name`, deleted). `name`
    # is the listing's own `market` column verbatim, the exact string `logic.js`'s metro dropdown
    # lists and `boundaries()` joins against; two market keys sharing one CBSA (e.g. "Sacramento,
    # CA" and "South Lake Tahoe, CA", both CBSA 40900) are two rows, and a published listing whose
    # point falls in no CBSA (`practice_location.cbsa_geoid IS NULL`) has no row at all.
    #
    # THE REVERSE CASE -- one market key spanning two CBSAs -- is the one this ORDER BY settles.
    # It is not hypothetical: a key like "Kansas City, MO" can hold listings on both sides of a
    # metro boundary, and the client resolves a metro with `rows.find(m => m.name === marketName)`,
    # which takes the FIRST match. Ordering on `l.market` alone left Postgres free to return either
    # row first, so the same catalogue could shade a different half of the country between two
    # requests, with nothing anywhere to notice. `pl.cbsa_geoid` is the tie-break: an arbitrary
    # choice made DETERMINISTIC, which is all that is available until a market key is allowed to
    # name its own CBSA.
    async with engine().connect() as conn:
        act = await _active(conn)
        rows = (await conn.execute(text("""
            SELECT l.market AS name, pl.cbsa_geoid, ST_Y(ga.centroid) AS lat, ST_X(ga.centroid) AS lng
            FROM listing l
            JOIN practice_location pl ON pl.listing_id = l.id AND pl.cbsa_geoid IS NOT NULL
            JOIN geo_area ga ON ga.geo_id = pl.cbsa_geoid AND ga.summary_level = '310' AND ga.vintage = :gv
            WHERE l.status = 'published'
            GROUP BY l.market, pl.cbsa_geoid, ga.centroid
            ORDER BY l.market, pl.cbsa_geoid"""), {"gv": act.get("tiger_cb")})).mappings().all()
    return JSONResponse([
        {"cbsa_geoid": r["cbsa_geoid"], "name": r["name"], "center": [round(r["lat"], 2), round(r["lng"], 2)], "zoom": 10}
        for r in rows
    ])


_COMMUNITIES_SQL = """
    SELECT l.id AS listing_id, pl.geo_precision, COALESCE(pg.name, l.city) AS name, l.location_disclosed,
           ST_Y(pl.point) AS pt_lat, ST_X(pl.point) AS pt_lng, ST_Y(pg.centroid) AS pl_lat, ST_X(pg.centroid) AS pl_lng,
           mm.metric_key, mm.value_num, mm.suppressed, mm.source_dataset, mm.inputs
    FROM listing l JOIN practice_location pl ON pl.listing_id = l.id AND pl.cbsa_geoid = :cbsa
    LEFT JOIN geo_area pg ON pg.geo_id = pl.place_geoid AND pg.summary_level = '160' AND pg.vintage = :gv
    LEFT JOIN market_metric mm ON mm.listing_id = l.id AND mm.band = :band
    WHERE l.status = 'published'
"""


def _new_community(row: RowMapping) -> dict[str, Any]:
    return {
        "listing_id": str(row["listing_id"]), "name": row["name"], "geo_precision": row["geo_precision"], "suppressed": [],
        "location": "disclosed_point" if (row["location_disclosed"] and row["pt_lat"] is not None) else "place_centroid",
        "lat": row["pt_lat"] if row["location_disclosed"] else row["pl_lat"],
        "lng": row["pt_lng"] if row["location_disclosed"] else row["pl_lng"],
    }


@router.get("/markets/{cbsa}/communities", dependencies=[Depends(REQUIRE_MARKET_READ)])
async def communities(cbsa: str, band: str | None = Query(None)) -> Response:
    b = _resolve_band(band, "place")
    if b is None:
        return _error("BAD_BAND", f"band must be one of {BANDS}", 422)
    async with engine().connect() as conn:
        act, reg = await _active(conn), await _registry(conn)
        rows = (await conn.execute(text(_COMMUNITIES_SQL), {"cbsa": cbsa, "gv": act.get("tiger_cb"), "band": b})).mappings().all()
    by: dict[str, dict[str, Any]] = {}
    used = {"acs5"}
    # `establishments` and `vets_per_10k_households` are two SEPARATE `market_metric` rows for the
    # same community, and SQL makes no promise about which one this query returns first — so the
    # two are combined into one `competition` object AFTER the loop, keyed by listing id, rather
    # than inline in one pass (which would silently drop `per_10k_households`/`level` whenever the
    # database happened to hand back the density row before the count row).
    comp_count: dict[str, dict[str, Any]] = {}
    comp_per10k: dict[str, float | None] = {}
    for row in rows:
        lid = str(row["listing_id"])
        c = by.setdefault(lid, _new_community(row))
        if not row["metric_key"] or not _cleared(reg, row["source_dataset"]):
            continue
        # Correction 6, widened by A-C23 (1): growth, the vets-per-household ratio and the
        # establishment count's own CBP fallback each fold in a SECOND dataset that
        # `row["source_dataset"]` alone cannot name.
        if not _extra_cleared(reg, row["metric_key"], row["source_dataset"]):
            continue
        for field, metric in FIELD_FOR.items():
            if row["metric_key"] == metric:
                used.add(row["source_dataset"])
                if row["metric_key"] == "population_growth_pct":
                    used.add("acs5_prior")
                if row["suppressed"]:
                    c["suppressed"].append(field)
                else:
                    c[field] = float(row["value_num"]) if row["value_num"] is not None else None
        # `value_num is not None` belongs here as much as on the two branches either side of it
        # (whole-branch re-review, 2026-09-11): the column is nullable and `suppressed` is
        # NOT NULL DEFAULT false, so "the source did not answer" reaches this line as a null on an
        # UNSUPPRESSED row and `float(None)` took the whole communities route down with a 500.
        # D-C31's rule decides the answer: an absent figure is absent — the community keeps every
        # figure that IS servable and simply carries no competition count, exactly as a suppressed
        # row does. This was the last unguarded `float()` in the module.
        if row["metric_key"] == "establishments" and not row["suppressed"] and row["value_num"] is not None:
            inputs = row["inputs"] or {}
            comp_count[lid] = {"count": float(row["value_num"]), "geo_level": inputs.get("geo_level"), "zctas": inputs.get("zctas")}
        if row["metric_key"] == "vets_per_10k_households" and not row["suppressed"]:
            comp_per10k[lid] = float(row["value_num"]) if row["value_num"] is not None else None
    for lid, count in comp_count.items():
        competition = dict(count)
        if lid in comp_per10k:
            per = comp_per10k[lid]
            competition["per_10k_households"] = per
            competition["level"] = M.competition_level(per)
        by[lid]["competition"] = competition
    return JSONResponse({
        "band": b, "vintage": act.get("acs5"), "attribution": [reg[k]["attribution_text"] for k in sorted(used)],
        "communities": list(by.values()),
    })


@router.get("/markets/{cbsa}/boundaries", dependencies=[Depends(REQUIRE_MARKET_READ)])
async def boundaries(cbsa: str, request: Request, layer: str | None = Query(None), bbox: str | None = Query(None)) -> Response:
    """Real Census boundary polygons for one metro and one shaded layer (D-C34 through D-C37).

    Served as a member-gated ENDPOINT rather than CDN tiles: `MARKET_DATA_PUBLIC` is false so
    tiles would have to be member-gated anyway, and spec §10's "30 days, immutable" CDN row
    directly contradicts §11's "the layer disappears within one minute" the moment a tile carries
    values rather than only geometry. One route inside the existing `market:gate:v` cache key
    honours both."""
    # The clock starts before the cache is even read, because what the line at the end of this
    # function reports is the cost of a MISS end to end -- the number the caps' re-measurement
    # (2026-09-12) makes worth watching, and which nobody could see from outside.
    started = time.perf_counter()
    sql_ms = 0.0
    tiers_tried = 0

    def cost(outcome: str, features: int, raw_bytes: int, gz_bytes: int) -> None:
        """ONE line per cache MISS, whatever the miss cost and however it ended.

        Every miss is logged, not only the ones that were served: a refusal spends the same SQL
        and, on the byte arm, the same serialisations, so a measurement that saw only the successes
        would be reading a survivor's sample and drawing the wrong conclusion about what a far
        zoom costs. `outcome` is what tells them apart -- `served`, `refused_count` (the feature
        cap, which breaks the ladder on its first tier because simplification never drops a
        polygon) or `refused_bytes` (the byte cap at the coarsest tier, the one place the ladder
        gives up). A cache HIT stays silent: a line per request would drown the thing this exists
        to make visible.

        `bytes_raw` is 0 on the count arm because no body was ever composed there, and `bytes_gz`
        is 0 on BOTH refusals because a refused body is never compressed -- one gzip of several
        megabytes on the path that is already failing is a cost nobody asked for. `outcome` is
        what says why the zeros are there; a number invented for them would be read as a
        measurement.

        Identifiers and sizes only: `cbsa` is a Census geoid, `layer` is one of three literals,
        and no figure the payload carries appears. `log.warning` below is the module's own idiom;
        this is its INFO sibling.
        """
        log.info(
            "boundaries miss outcome=%s cbsa=%s layer=%s features=%d tiers_tried=%d "
            "bytes_raw=%d bytes_gz=%d ms_sql=%.1f ms_total=%.1f",
            outcome, cbsa, layer, features, tiers_tried, raw_bytes, gz_bytes,
            sql_ms, (time.perf_counter() - started) * 1000,
        )

    if layer not in SHADING:
        return _error("BAD_LAYER", f"layer must be one of {tuple(SHADING)}", 422)
    box: tuple[float, float, float, float] | None = None
    if bbox is not None:
        box = _parse_bbox(bbox)
        if box is None:
            return _error("BAD_BBOX", "bbox must be minLng,minLat,maxLng,maxLat with maxima above minima", 422)
        if box[2] - box[0] > MAX_BBOX_DEG or box[3] - box[1] > MAX_BBOX_DEG:
            return _error("BBOX_TOO_LARGE", f"bbox spans {box[2] - box[0]:.2f} x {box[3] - box[1]:.2f} degrees; the cap is {MAX_BBOX_DEG} on either axis", 422)

    metric_key, source = BOUNDARY_METRIC[layer]
    r = sync_redis()
    geo_version = cast("bytes | str | None", r.get(GEO_VERSION_KEY))
    async with engine().connect() as conn:
        act, reg = await _active(conn), await _registry(conn)
        geo_vintage, value_vintage = act.get("tiger_cb"), act.get(source)
        key = (f"boundaries:{cbsa}:{layer}:{geo_vintage}:{value_vintage}:g{gate.version(r)}"
               f":m{int(geo_version) if geo_version else 0}:b{bbox or 'metro'}")
        cached = cast("bytes | None", r.get(key))
        if cached is not None:
            return _geojson(cached, request, "hit")
        metro = (await conn.execute(text(
            "SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) FROM geo_area "
            "WHERE geo_id = :cbsa AND summary_level = '310' AND vintage = :gv"), {"cbsa": cbsa, "gv": geo_vintage})).first()
        if metro is None:
            return _error("NOT_FOUND", "No such metro.", 404)
        if box is None:
            box = (float(metro[0]), float(metro[1]), float(metro[2]), float(metro[3]))
        entry = next(l for l in LAYERS if l["key"] == layer)
        state, blocked_reason = _layer_state(reg, entry["dataset_key"])
        # Belt as well as braces, and legally load-bearing: `_layer_state` reads the layer
        # CATALOGUE's dataset (growth's is `acs5_prior`), while the rows themselves are stamped
        # with `source` — so a withdrawn `acs5` licence would otherwise leave growth enabled.
        if state == "enabled" and not (_cleared(reg, source) and _extra_cleared(reg, metric_key, source)):
            state = "disabled"
        used = sorted({source} | ({"acs5_prior"} if metric_key == "population_growth_pct" else set()))

        def compose(rows: list[RowMapping], orphans: int, simplified: float) -> dict[str, Any]:
            body: dict[str, Any] = {
                "type": "FeatureCollection", "cbsa_geoid": cbsa, "layer": layer, "metric_key": metric_key,
                "summary_level": SHADING[layer]["summary_level"], "geo_label": SHADING[layer]["label"],
                "unit": UNIT[layer], "state": state,
                "boundary_vintage": geo_vintage, "value_vintage": value_vintage, "source_dataset": source,
                # Read from dataset_registry, never composed here: attribution is legally load-bearing
                # and a terms change must be one UPDATE rather than a redeploy. Boundaries first — the
                # map carries the geometry's attribution beside the values' (Census spec §2b).
                "attribution": [reg["tiger_cb"]["attribution_text"]] + [reg[k]["attribution_text"] for k in used],
                "values_without_geometry": orphans,
                # The delivery tolerance in degrees, 0.0 when the exact outline was served. Stated
                # rather than hidden: it describes the GEOMETRY only and never the figures, and a
                # client that wants to say "outlines generalised for display" can read it here.
                "simplified_deg": simplified,
                "features": [_boundary_feature(row, layer) for row in rows],
            }
            if blocked_reason is not None:
                body["blocked_reason"] = blocked_reason
            return body

        rows: list[RowMapping] = []
        orphans = 0
        simplified = 0.0
        raw = json.dumps(compose(rows, orphans, simplified)).encode("utf-8")
        if state == "enabled":
            params = {"metric": metric_key, "value_vintage": value_vintage, "level": SHADING[layer]["summary_level"],
                      "geo_vintage": geo_vintage, "w": box[0], "s": box[1], "e": box[2], "n": box[3]}
            sql_at = time.perf_counter()
            orphans = int((await conn.execute(text(_ORPHAN_SQL), params)).scalar_one())
            sql_ms += (time.perf_counter() - sql_at) * 1000
            span = max(box[2] - box[0], box[3] - box[1])
            # Coarsen until it fits. A polygon is NEVER dropped to make room — a missing polygon
            # leaves a hole that reads as a boundary — so the feature cap is a refusal, not a rung.
            for frac in SIMPLIFY_TIERS:
                simplified = span * frac
                tiers_tried += 1
                sql_at = time.perf_counter()
                rows = list((await conn.execute(text(_BOUNDARY_SQL), {**params, "tol": simplified})).mappings().all())
                sql_ms += (time.perf_counter() - sql_at) * 1000
                if len(rows) > MAX_FEATURES:
                    break
                raw = json.dumps(compose(rows, orphans, simplified)).encode("utf-8")
                if len(raw) <= MAX_BODY_BYTES:
                    break
    if len(rows) > MAX_FEATURES:
        cost("refused_count", len(rows), 0, 0)
        return _error("AREA_TOO_LARGE", f"{len(rows)} features in this area; the cap is {MAX_FEATURES}. Zoom in or pass a smaller bbox.", 422)
    if orphans:
        # A non-zero count on a metro that has previously reported zero is how a boundary vintage
        # that has moved out from under the values announces itself (R4).
        log.warning("boundaries: %d %s values at level %s have no %s geometry", orphans, value_vintage, SHADING[layer]["summary_level"], geo_vintage)
    if len(raw) > MAX_BODY_BYTES:
        cost("refused_bytes", len(rows), len(raw), 0)
        return _error("AREA_TOO_LARGE", f"{len(raw)} bytes in this area even at the coarsest delivery tolerance; the cap is {MAX_BODY_BYTES}. Zoom in or pass a smaller bbox.", 422)
    packed = gzip.compress(raw)
    r.set(key, packed, ex=BOUNDARY_TTL)
    cost("served", len(rows), len(raw), len(packed))
    return _geojson(packed, request, "miss")


def _boundary_feature(row: RowMapping, layer: str) -> dict[str, Any]:
    """One polygon. `value` is `None` both when the geography has no row at all and when its row
    is suppressed, and the two are told apart by `suppressed`/`suppress_reason` — the client draws
    both in the no-data class but says something different about each (§6)."""
    value = None if row["value_num"] is None else float(row["value_num"])
    moe = None if row["moe"] is None else float(row["moe"])
    return {
        "type": "Feature", "id": row["geo_id"],
        "properties": {
            "geo_id": row["geo_id"], "name": row["name"],
            "value": None if row["suppressed"] else value, "moe": moe,
            "suppressed": bool(row["suppressed"]), "suppress_reason": row["suppress_reason"],
            # Judged against THIS layer's own legend stops, never another's. Growth, payroll
            # and competition carry no published margin at all (D-NS17) and pets is a rounded
            # model output, so `band_ambiguous` is False for those four by construction rather
            # than by omission -- `BAND_STOPS` does not name them and `band_ambiguous` is False
            # for a missing margin anyway.
            "band_ambiguous": layer in BAND_STOPS and band_ambiguous(value, moe, BAND_STOPS[layer]),
        },
        "geometry": json.loads(row["geometry"]),
    }


def _geojson(packed: bytes, request: Request, cache: str) -> Response:
    """D-NS14: gzip in the HANDLER, and the COMPRESSED bytes are what Redis holds, so a cache hit
    costs no second compression. No global `GZipMiddleware`: that would change every response in
    the application, including the ones carrying `x-cache` and the four security headers
    `SecurityHeadersMiddleware` puts on EVERY answer, which is far wider than the ask."""
    headers = {"x-cache": cache, "Vary": "Accept-Encoding"}
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(packed, media_type="application/geo+json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(gzip.decompress(packed), media_type="application/geo+json", headers=headers)


@router.get("/markets/{cbsa}/summary", dependencies=[Depends(REQUIRE_MARKET_READ)])
async def summary(cbsa: str) -> Response:
    """The metro-wide distribution of every shaded layer — what the Browse "Market snapshot" strip
    prints in AREA mode (Task SNAP; ruling D-C50 as revised by the stakeholder, 2026-09-12).

    Until this existed the strip computed a "metro median" from `/api/markets/{cbsa}/communities`
    — one row per LISTING, each hospital's own five-mile ring — while the map beside it painted
    Census geography per layer. On Dallas the strip read Households **162K** over tracts that hold
    0\u20135,988 and Competition **41** over ZIP areas that hold 3\u201316: two numbers about two different
    things, one caption. The stakeholder ruled the map correct and the snapshot wrong, so the
    strip now describes the polygons the map shades — and it reads them from here rather than
    deriving them client-side, because the client never holds the whole metro (the boundary route
    is answered for a VIEWPORT, deliberately, and a median over whatever is on screen is a
    different number every time the member pans).

    One body for all six layers, not one request per layer: the strip shows them together, so six
    round trips would buy nothing but six chances to render half a card set. The whole answer is
    cached for `SUMMARY_TTL` under a key carrying the licence-gate counter and the writer's own
    version, exactly as the boundary route's is, so a licence decision or a nightly rewrite makes
    every cached body unreachable within the same minute (§11).

    There is no `bbox` and no `layer` parameter, and that is the point: this is the METRO, which
    is the geography the card's caption names.
    """
    # Fix round 1: the clock starts before the cache is read, because what the line at the end of
    # this function reports is the cost of a MISS end to end -- six runs of `_SUMMARY_SQL` over
    # the metro's WHOLE envelope, each with a `percentile_cont` over every valued polygon of that
    # layer's level. `boundaries` has carried its own such line since A24's fix round 2, for the
    # same reason and in the same shape; a HIT stays silent, because a line per request would
    # drown the thing this exists to make visible.
    started = time.perf_counter()
    r = sync_redis()
    geo_version = cast("bytes | str | None", r.get(GEO_VERSION_KEY))
    async with engine().connect() as conn:
        act, reg = await _active(conn), await _registry(conn)
        geo_vintage = act.get("tiger_cb")
        # EVERY value vintage in the body, not only the ACS one: one answer carries six layers
        # stamped with four datasets, so a key naming one of them would serve a stale ZIP Business
        # Patterns card for a day after that dataset's vintage was activated.
        values = ",".join(f"{k}={act.get(k)}" for k in SUMMARY_DATASETS)
        key = (f"summary:{cbsa}:{geo_vintage}:{values}:g{gate.version(r)}"
               f":m{int(geo_version) if geo_version else 0}")
        cached = cast("bytes | str | None", r.get(key))
        if cached is not None:
            return JSONResponse(json.loads(cached), headers={"x-cache": "hit"})
        metro = (await conn.execute(text(
            "SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) FROM geo_area "
            "WHERE geo_id = :cbsa AND summary_level = '310' AND vintage = :gv"), {"cbsa": cbsa, "gv": geo_vintage})).first()
        if metro is None:
            return _error("NOT_FOUND", "No such metro.", 404)
        used: set[str] = set()
        layers: list[dict[str, Any]] = []
        for layer, shading in SHADING.items():
            metric_key, source = BOUNDARY_METRIC[layer]
            entry = next(l for l in LAYERS if l["key"] == layer)
            state, blocked_reason = _layer_state(reg, entry["dataset_key"])
            # Belt as well as braces, exactly as `boundaries` does it: `_layer_state` reads the
            # layer CATALOGUE's dataset (growth's is `acs5_prior`) while the rows themselves are
            # stamped with `source`, so either licence moving has to turn the layer off.
            if state == "enabled" and not (_cleared(reg, source) and _extra_cleared(reg, metric_key, source)):
                state = "disabled"
            row: dict[str, Any] = {
                "layer": layer, "summary_level": shading["summary_level"], "geo_label": shading["label"],
                "unit": UNIT[layer], "state": state,
                # A layer that is off answers with its geography, its state and NO figures — never
                # a 403, because the client has to be able to draw "unavailable" (the boundary
                # route's own rule, for the same reason).
                "count": 0, "with_value": 0, "suppressed": 0, "no_data": 0,
                "median": None, "quantiles": None,
                "value_vintage": act.get(source), "source_dataset": source,
            }
            if blocked_reason is not None:
                row["blocked_reason"] = blocked_reason
            if state == "enabled":
                used.add(source)
                if metric_key == "population_growth_pct":
                    used.add("acs5_prior")
                stat = (await conn.execute(text(_SUMMARY_SQL), {
                    "metric": metric_key, "value_vintage": act.get(source),
                    "level": shading["summary_level"], "geo_vintage": geo_vintage,
                    "fractions": list(SUMMARY_FRACTIONS),
                    "w": float(metro[0]), "s": float(metro[1]), "e": float(metro[2]), "n": float(metro[3]),
                })).mappings().one()
                quantiles = None if stat["quantiles"] is None else [float(q) for q in stat["quantiles"]]
                n, with_value, suppressed = int(stat["n"]), int(stat["with_value"]), int(stat["suppressed"])
                row.update({
                    "count": n, "with_value": with_value, "suppressed": suppressed,
                    # Never queried separately: the three counts have to add up to the population,
                    # and subtracting is the only way to say so rather than to hope so.
                    "no_data": n - with_value - suppressed,
                    "median": None if quantiles is None else quantiles[SUMMARY_MEDIAN_AT],
                    "quantiles": quantiles,
                })
            layers.append(row)
    body = {
        "cbsa_geoid": cbsa, "boundary_vintage": geo_vintage,
        # From `dataset_registry`, never composed here (Census spec §2b). Boundaries first, then
        # one line per value dataset that actually answered — a withdrawn licence takes its
        # attribution with it, because nothing of that dataset is on the wire to attribute.
        "attribution": [reg["tiger_cb"]["attribution_text"]] + [reg[k]["attribution_text"] for k in sorted(used)],
        "layers": layers,
    }
    r.set(key, json.dumps(body), ex=SUMMARY_TTL)
    # Identifiers and sizes only, as `boundaries`' own line is: `cbsa` is a Census geoid, `layers`
    # is how many rows the body carries and `rows` how many polygons were counted across them --
    # no median, no quantile, no geography NAME, nothing the payload shows a member.
    log.info(
        "summary miss cbsa=%s layers=%d rows=%d ms=%.1f",
        cbsa, len(layers), sum(int(row["count"]) for row in layers),
        (time.perf_counter() - started) * 1000,
    )
    return JSONResponse(body, headers={"x-cache": "miss"})


_PANEL_SQL = """
    SELECT mm.*, pl.geo_precision FROM market_metric mm JOIN practice_location pl ON pl.listing_id = mm.listing_id
    WHERE mm.listing_id = :id AND mm.band = :band
"""


def _panel_entry(m: RowMapping) -> dict[str, Any]:
    inputs = m["inputs"] or {}
    entry: dict[str, Any] = {
        "value": None if m["suppressed"] else (float(m["value_num"]) if m["value_num"] is not None else None),
        "unit": m["unit"], "is_derived": m["is_derived"], "formula_version": m["formula_version"],
        "moe": float(m["moe"]) if m["moe"] is not None else None,
        "suppressed": m["suppressed"], "suppress_reason": m["suppress_reason"],
        "source_dataset": m["source_dataset"], "vintage": m["vintage"], "geo_level": inputs.get("geo_level"),
        "inputs": {k: v for k, v in inputs.items() if k in ("acs5", "acs5_prior", "cbp", "zbp")} or None,
    }
    if "pet_incidence_rate" in inputs:
        entry["assumed_rate"] = inputs["pet_incidence_rate"]
    if m["metric_key"] == "median_hh_income" and m["is_derived"]:
        entry["approximate"] = True
    if m["metric_key"] in LABELS:
        entry["label"] = LABELS[m["metric_key"]]
    return entry


@router.get("/listings/{listing_id}/market", dependencies=[Depends(REQUIRE_MARKET_READ)])
async def listing_market(listing_id: str, band: str | None = Query(None)) -> Response:
    b = _resolve_band(band, "drive_10")
    if b is None:
        return _error("BAD_BAND", f"band must be one of {BANDS}", 422)
    if not _is_uuid(listing_id):
        return _error("NOT_FOUND", "No such listing.", 404)
    r = sync_redis()
    # redis-py's sync/async command mixins share one ResponseT stub (Awaitable[Any] | Any); this
    # client is sync — the same cast `app.census.gate`/`app.auth.sessions` make for the same reason.
    version = cast("bytes | str | None", r.get(f"listing:{listing_id}:market:version"))
    key = f"listing:{listing_id}:market:{b}:v{int(version) if version else 0}:g{gate.version(r)}"
    cached = cast("bytes | str | None", r.get(key))
    if cached is not None:
        return JSONResponse(json.loads(cached), headers={"x-cache": "hit"})
    async with engine().connect() as conn:
        exists = (await conn.execute(text("SELECT status FROM listing WHERE id = :id"), {"id": listing_id})).first()
        # A-C23 (2): a bare "does the id exist" check is not enough -- the panel spec (and
        # `communities()`'s own `l.status = 'published'` join) only ever promise NO_MARKET_DATA for
        # an EXISTING PUBLISHED listing with no rows yet; anything else (unknown, or an existing
        # listing that is not published) reads as NOT_FOUND, checked here BEFORE `rows` is even
        # queried -- an unpublished listing must never reach a served panel, whether or not it
        # happens to still carry stale `market_metric` rows from before it was withdrawn.
        if exists is None or exists[0] != "published":
            return _error("NOT_FOUND", "No such listing.", 404)
        rows = (await conn.execute(text(_PANEL_SQL), {"id": listing_id, "band": b})).mappings().all()
        if not rows:
            # The cache-dedupe check is its own condition, no longer compounded with the
            # publication check above (A-C23 (2)): this line is reached only for a listing already
            # known to be published, so a passing test here can no longer hide a deleted
            # publication guard.
            if r.set(f"backfill:{listing_id}", "1", ex=BACKFILL_DEDUPE_TTL, nx=True):
                celery_app.send_task("census.backfill_listing", args=[listing_id])
            return _error("NO_MARKET_DATA", "Community data is being prepared for this listing.", 404)
        reg = await _registry(conn)
        act = await _active(conn)
    metrics: dict[str, dict[str, Any]] = {}
    used = {"acs5"}
    for m in rows:
        if m["metric_key"] in _NEVER_PUBLISHED:
            continue
        if not _cleared(reg, m["source_dataset"]):
            continue
        if not _extra_cleared(reg, m["metric_key"], m["source_dataset"]):
            continue
        used.add(m["source_dataset"])
        if m["metric_key"] == "population_growth_pct":
            used.add("acs5_prior")
        metrics[m["metric_key"]] = _panel_entry(m)
    body = {
        "listing_id": listing_id, "band": b, "geo_precision": rows[0]["geo_precision"],
        # A-C24 (1): the ACS vintage, chosen deliberately -- never `rows[0]["vintage"]`. `_PANEL_SQL`
        # carries no ORDER BY, and its rows are stamped with TWO vintage families (`acs5`'s, and
        # whichever `zbp`/`cbp` vintage produced `establishments`/`revenue_per_establishment`);
        # `market_metric_lookup_idx (listing_id, band, vintage)` is the index Postgres reaches for
        # on exactly this (listing_id, band) lookup (Task B5's own EXPLAIN), which makes "whichever
        # row comes first" a fact about how those two vintage STRINGS happen to sort, not a fact
        # this code may rely on -- correct today only because "2019-2023" sorts before "2022", and
        # silently wrong the day a future vintage pair sorts the other way. `act.get("acs5")` names
        # the ACS vintage on purpose, the same way `communities()`'s own top-level `vintage` already
        # does; every individual metric under `metrics` still carries its OWN `vintage` and
        # `source_dataset` for the figures stamped with a different dataset.
        "vintage": act.get("acs5"),
        "computed_at": max(m["computed_at"] for m in rows).isoformat(), "metrics": metrics,
        "attribution": [reg[k]["attribution_text"] for k in sorted(used)],
    }
    r.set(key, json.dumps(body), ex=PANEL_TTL)
    return JSONResponse(body, headers={"x-cache": "miss"})
