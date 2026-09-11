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

import json
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from app.auth.deps import require
from app.cache import sync_redis
from app.census import gate
from app.census import metrics as M
from app.census.serve import _active, _extra_cleared, _registry
from app.db import engine
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/api")

# Hoisted to a module-level constant, never wrapped (Global Constraint (g); correction 4 above).
REQUIRE_MARKET_READ = require("market.read")

PANEL_TTL = 86400
BACKFILL_DEDUPE_TTL = 600
BANDS: tuple[str, ...] = ("place", "drive_10", "drive_20")
DEFAULT_BLOCKED_REASON = "Licence not cleared."

# The three-valued state B6's contract settled on, keyed off `dataset_registry.license_status`
# (migration 017's own CHECK constraint admits exactly these three strings).
_STATE_FOR = {"cleared": "enabled", "unresolved": "disabled", "blocked": "blocked"}

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
     "caveat": "Establishment counts (NAICS 541940) include corporate-owned and specialty locations; a proxy for competitive density, not a count of independent practices. ZIP-code counts aggregated to the community."},
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


def short_market_name(cbsa_name: str) -> str:
    """`"Austin-Round Rock-San Marcos, TX Metro Area"` -> `"Austin, TX"` — the design's own short
    form: the first hyphen-joined city and the state abbreviation."""
    city_part, _, rest = cbsa_name.partition(",")
    return f"{city_part.split('-')[0].strip()}, {rest.strip().split(' ')[0]}"


def _resolve_band(band: str | None, default: str) -> str | None:
    """The requested band, or the default when none was given; `None` when the caller asked for
    something that is not one of `BANDS` at all, which the route turns into decision A5's 422."""
    b = band or default
    return b if b in BANDS else None


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
            "state": state, "is_derived": layer["is_derived"], "caveat": layer["caveat"],
        }
        if blocked_reason is not None:
            entry["blocked_reason"] = blocked_reason
        out.append(entry)
    return JSONResponse(out)


@router.get("/markets", dependencies=[Depends(REQUIRE_MARKET_READ)])
async def markets() -> Response:
    async with engine().connect() as conn:
        act = await _active(conn)
        rows = (await conn.execute(text("""
            SELECT DISTINCT pl.cbsa_geoid, ga.name, ST_Y(ga.centroid) AS lat, ST_X(ga.centroid) AS lng
            FROM practice_location pl JOIN listing l ON l.id = pl.listing_id AND l.status = 'published'
            JOIN geo_area ga ON ga.geo_id = pl.cbsa_geoid AND ga.summary_level = '310' AND ga.vintage = :gv
            ORDER BY ga.name"""), {"gv": act.get("tiger_cb")})).mappings().all()
    return JSONResponse([
        {"cbsa_geoid": r["cbsa_geoid"], "name": short_market_name(r["name"]), "center": [round(r["lat"], 2), round(r["lng"], 2)], "zoom": 10}
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
