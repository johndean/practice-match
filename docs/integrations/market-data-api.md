# Market data API — integration contract

**Audience:** Sub-project 2 (the buyer/seller frontend) wiring the map and Community Context
cards to real data, and whoever builds the admin **Data Sources** tab. **Status:** Census Phase B
is closed as of this document (Task B6); it describes what the phase actually shipped, not what
the plan first sketched. Two sections below say plainly what the phase left open — read those
before assuming a field exists.

This document is generated from, and kept honest against, the running code: `tests/api/
test_contract_doc.py` fails if a route below stops matching `app.api.market`/`app.api.
admin_data_sources`, or if this document stops naming the fixture field names the frontend reads.
It does not fail if the *prose* goes stale, so treat the route list and JSON shapes as the source
of truth and the surrounding sentences as commentary.

## Routes

| Method | Path | Guard |
|---|---|---|
| GET | `/api/layers` | `market.read` |
| GET | `/api/markets` | `market.read` |
| GET | `/api/markets/{cbsa}/communities` | `market.read` |
| GET | `/api/markets/{cbsa}/boundaries` | `market.read` |
| GET | `/api/markets/{cbsa}/summary` | `market.read` |
| GET | `/api/listings/{listing_id}/market` | `market.read` |
| GET | `/api/admin/data-sources` | `data_sources.read` (staff/admin) |
| POST | `/api/admin/data-sources/{dataset_key}/license` | `licence.decide` (admin, re-authenticated within 10 minutes) |

**Mounted only while `SITE_MODE=app`.** All eight routes live inside `app/main.py`'s `if
settings.site_mode == "app":` block, the same gate `admin_users_router`/`listings_router` sit
behind. Production runs `coming_soon` until launch (`CLAUDE.md`), so on production today every one
of these paths 404s through `not_found_router`, exactly like every other member or admin surface —
this is not a bug to route around, it is the same launch gate the rest of the app uses.

**The permission model widens rather than bypasses.** `market.read` is granted to an `active`
account holding `buyer`/`seller`/`staff`/`admin`, or an `api_token` carrying one of those roles.
`MARKET_DATA_PUBLIC=true` does **not** remove the `Depends(require("market.read"))` on any route —
it widens who satisfies it: `app.auth.permissions.allowed` additionally grants `market.read` to
`anonymous` while the flag is set (spec §15; Task I9a). The six `market.py` routes resolve this
dependency **once, at import time**, into a module-level constant (`REQUIRE_MARKET_READ`) rather
than re-wrapping it per route — `tests/auth/test_permissions.py` walks every mounted route and
resolves its guard by object identity, so a fresh `require(...)` call per route would read as
unguarded. `MARKET_DATA_PUBLIC` stays `false` in every environment today (John's ruling, A-C13
(3)); `GET /api/config` publishes the flag's current value unconditionally so the frontend's own
`can('market.read', …)` check can honour the same rule without a second, drifting copy of it.

`/api/admin/*` above uses `data_sources.read` (staff or admin) for both routes, plus
`licence.decide` (admin only, and in `permissions.REAUTH` — an `api_token` can never satisfy it)
on `/license` alone.

## `GET /api/layers`

Every layer, in a fixed order, regardless of licence status — a blocked or disabled layer is
still LISTED (so the UI can render it as unavailable), just never carries data:

```json
[
  { "key": "income", "label": "Median Household Income", "dataset_key": "acs5",
    "source_label": "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023",
    "vintage": "2019–2023", "geo_level": "place|catchment",
    "shading": { "summary_level": "140", "label": "Census tract" },
    "state": "enabled", "is_derived": false, "caveat": null },
  { "key": "pets", "label": "Pet Ownership (est.)", "dataset_key": "acs5",
    "shading": { "summary_level": "140", "label": "Census tract" }, "state": "enabled",
    "is_derived": true, "caveat": "Derived estimate: households × 0.57 (national placeholder rate until a licensed regional rate is cleared)." },
  { "key": "growth", "label": "Population Growth", "dataset_key": "acs5_prior",
    "vintage": "2014–2018 → 2019–2023", "geo_level": "place",
    "shading": { "summary_level": "160", "label": "Place (city/town)" },
    "state": "enabled", "is_derived": true,
    "caveat": "Change between two ACS 5-year periods, measured for the listing's city/CDP." },
  { "key": "households", "label": "Households", "dataset_key": "acs5",
    "shading": { "summary_level": "140", "label": "Census tract" },
    "state": "enabled", "is_derived": false, "caveat": null },
  { "key": "econ", "label": "Average Practice Payroll", "dataset_key": "cbp", "geo_level": "county",
    "shading": { "summary_level": "050", "label": "County" },
    "state": "enabled", "is_derived": true,
    "caveat": "Payroll per establishment (NAICS 541940), not revenue; county level." },
  { "key": "competition", "label": "Veterinary Competition", "dataset_key": "zbp", "geo_level": "zcta",
    "shading": { "summary_level": "860", "label": "ZIP Code Tabulation Area" },
    "state": "enabled", "is_derived": false,
    "caveat": "Establishment counts (NAICS 541940) include corporate-owned and specialty locations; a proxy for competitive density, not a count of independent practices. Published per ZIP code by ZIP Code Business Patterns, and shaded at the ZIP Code Tabulation Area, which is that dataset's own authoritative geography." },
  { "key": "practices", "label": "Practice Listings", "dataset_key": null, "shading": null, "state": "enabled", "is_derived": false, "caveat": null },
  { "key": "drive_10", "label": "5–10 min drive time", "dataset_key": null, "shading": null, "state": "enabled", "is_derived": true, "caveat": "Straight-line 8 km approximation of drive time." },
  { "key": "drive_20", "label": "10–20 min drive time", "dataset_key": null, "shading": null, "state": "enabled", "is_derived": true, "caveat": "Straight-line 16 km approximation of drive time." }
]
```

**`state` is three-valued, never a bare boolean** (`enabled` / `disabled` / `blocked`, plus
`blocked_reason` only when `blocked`, which no layer in the sample above is — `zbp` is seeded
`cleared` by `migrations/017_census_registry.sql`) — `dataset_registry.license_status`'s `cleared` /
`unresolved` / `blocked` (migration `017`'s own CHECK constraint), mapped straight across. "Off
because a member turned a layer off" and "off because the licence is not cleared" are different
facts the frontend and the admin surface both need to tell apart (A-C14 (4)); "off because it is
not yet cleared" (`disabled`) is not the same as "off because the licence was refused"
(`blocked`) — the first can still change, the second is a standing decision until an admin revisits
it. `practices`/`drive_10`/`drive_20` carry no `dataset_key` at all and are always `enabled`.

**`shading` is the geography the MAP paints this layer at, and is never the same field as
`geo_level`** (D-NS15). `geo_level` describes the docked PANEL's geography — `income`'s is
`"place|catchment"` — and the panel and the map answer different questions about the same layer.
Only the three fill layers carry a `shading` object; the three graduated-symbol layers, `practices`
and the two drive rings carry `"shading": null`. `GET /api/markets/{cbsa}/boundaries` below serves
the polygons at exactly the `summary_level` named here.

A licence decision on `/api/admin/data-sources/{key}/license` is reflected here within 60 seconds
(spec §11): `app.census.gate`'s Redis counter is bumped on every decision and rides inside the
market-payload cache key below, so a stale answer cannot outlive the decision by more than the
gate's own TTL.

## `GET /api/markets/{cbsa}/boundaries?layer=income|growth|econ|households|pets|competition[&bbox=minLng,minLat,maxLng,maxLat]`

The shaded map layer: real Census boundary polygons joined to `geo_metric`, one geography per
layer (John's rulings D-C34–D-C37, 2026-09-10). `income`, `households` and `pets` draw Census
tracts (`"summary_level": "140"`), `growth` draws Place (city/town) (`"summary_level": "160"`),
`econ` draws County (`"summary_level": "050"`), and `competition` draws the ZIP Code Tabulation
Area (`"summary_level": "860"`). Income moved from the ZIP Code Tabulation Area to the
Census tract on 2026-09-12 (controller ruling): the tract is the canonical granular unit,
nationwide. `growth` **cannot** follow it -- the 2010→2020 tract boundary change means a
tract-level growth figure is not computable from the data we hold (plan D12, a registered Phase C
deferral) -- so it keeps Place, `econ` keeps County, and each layer's own `geo_label` is what the
legend prints, which is how a coarser figure is never presented as a tract-level one. **No layer is ever painted at a geography finer than its
figure is honest at** — spec §6's standing rule, "Never silently promote a county figure into a
tract-labeled slot", applied to the map. `/api/layers` names each layer's own geography in its
`shading` member, or `null` where it has none — the three overlays that shade nothing
(`practices`, `drive_10`, `drive_20`).

**Why `competition` is served at the ZIP Code Tabulation Area.** Spec §6 forbids treating a ZIP
code as a neighbourhood or any other Census geography, **unless the ZIP area is the dataset's own
authoritative geography and the response says so.** For ZIP Code Business Patterns it literally
is: the product is published per ZIP code and exists at no other geography, so serving it at the
ZCTA is reporting it where it was measured rather than approximating it anywhere. The response
carries `"geo_label": "ZIP Code Tabulation Area"` and the client prints that name on the legend
and in every tooltip, so a count is never read as a neighbourhood figure. The approximation the
same spec does forbid — apportioning ZIP counts into some finer or differently-shaped area — is
not done anywhere on this route.

**`households` and `pets` shade at the tract, and `pets` is modelled.** `households` is
`B11001_001E`, a published ACS estimate with a published margin, served where the ACS publishes
it. `pets` is `households × 0.57`, a national placeholder incidence rate: its `/api/layers` entry
carries `"is_derived": true` and a caveat naming the rate, its `geo_metric` rows carry
`is_derived` and `formula_version`, and it is never presented as an observed count (spec §9).

One GeoJSON `FeatureCollection` with foreign members (RFC 7946 permits them; `L.geoJSON` ignores
what it does not know):

```json
{
  "type": "FeatureCollection",
  "cbsa_geoid": "12420", "layer": "income", "metric_key": "median_hh_income",
  "summary_level": "140", "geo_label": "Census tract", "unit": "usd",
  "state": "enabled", "boundary_vintage": "2023", "value_vintage": "2019–2023",
  "source_dataset": "acs5",
  "attribution": ["Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023",
                  "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023"],
  "values_without_geometry": 0,
  "simplified_deg": 0.0,
  "features": [
    { "type": "Feature", "id": "48453001100", "properties": { "geo_id": "48453001100", "name": "Census Tract 11",
                      "value": 92150, "moe": 6420,
                      "suppressed": false, "suppress_reason": null, "band_ambiguous": false },
      "geometry": { "type": "MultiPolygon", "coordinates": [] } }
  ]
}
```

**`simplified_deg` is the delivery tolerance, in degrees, and it describes the GEOMETRY only.**
`0.0` is the exact outline and is what every request that fits `MAX_BODY_BYTES` receives. A body
over the cap is SERVED at a coarser geometry rather than refused -- polygons are never dropped to
make room, because a missing polygon leaves a hole that reads as a boundary -- and this member
states the tolerance that was used, so a client can say "outlines generalised for display" instead
of presenting a coarsened outline as an exact one. It never describes the FIGURES: a coarsened
answer carries the same values as an exact one. Measured live: Austin (`12420`) income at whole
metro is 577 tracts at `0.0`; Dallas (`19100`) is 1,791 tracts at `0.00055`.

Every feature's `properties` carries exactly those seven keys — `geo_id`, `name`, `value`, `moe`,
`suppressed`, `suppress_reason`, `band_ambiguous` — on every polygon, whatever its state. Nothing
is omitted to signal an absence; an absence is a value.

**Two vintages, named separately.** `tiger_cb` is a bare year and `acs5` is an en-dashed range;
they advance on different calendars and are not interchangeable. A geography present in one and
not the other is handled in both directions: **geometry with no value** is returned with
`"value": null, "suppressed": false, "suppress_reason": null` and drawn in the no-data class —
never omitted, because a hole in a choropleth reads as a boundary; **a value with no geometry** is
dropped from `features` (there is nothing to draw) and counted in `values_without_geometry`, which
is logged on every cache miss. That counter is deliberately NOT narrowed by `bbox` — it counts
values with no `geo_area` row at that level and vintage AT ALL, since "values whose geography is
not in this viewport" would be non-zero on every zoomed request and would mean nothing. A non-zero
count on a metro that has previously reported zero means a boundary vintage has moved out from
under the values.

**`value` is `null` in two different cases and the client must tell them apart.** A geography with
no row at all is `value: null` with `suppressed: false` and `suppress_reason: null`; a suppressed
one is `value: null` with `suppressed: true` and a `suppress_reason` of `no_moe`, `high_moe`,
`input_suppressed`, `source_flag` or `source_threshold`. Both are drawn in the same neutral class;
they say different things, and a client that guards on `suppressed` alone paints the first as
measured. `band_ambiguous` is `true` when the margin of error spans a legend stop — that polygon
keeps its value and takes a caveat, and is **never** greyed.

**Which layers can carry which state.** `income` and `households` are published ACS estimates with
published margins, so both can be `suppressed` (`no_moe`, `high_moe`) and both can be
`band_ambiguous`, each judged against its OWN legend stops. `pets` is derived from `households`
and inherits its verdict as `input_suppressed`; it carries no margin of its own, so it is never
`band_ambiguous`. `econ` can be `source_flag` (the Census withheld the county cell — a CBP NOISE
level never suppresses; see "Average practice payroll" below). `competition` can be
`source_threshold`. `growth` can be neither: it is a difference of two ACS 5-year periods and is
published with no combined margin at all, so `suppressed` and `band_ambiguous` are both `false` on
it by construction rather than by omission.

**`source_threshold` — the Census's own ZIP publication rule.** ZIP Code Business Patterns
publishes industry detail only where a category has three or more establishments: a category under
three is not reported at ZIP level, though it IS counted in the dataset's all-industry total. A
ZCTA the dataset covers whose veterinary count was withheld that way is therefore `value: null,
suppressed: true, suppress_reason: "source_threshold"` — a real figure the Census chose not to
publish — while a ZCTA ZIP Code Business Patterns does not cover at all is `value: null,
suppressed: false`. The two are told apart by loading the all-industry total (`NAICS 00`) beside
the industry codes, which `app/census/zbp.py` does in the same pass; without it both states are
served as an absence. The served distribution therefore has a FLOOR of three, which is why the
`competition` legend's first class is labelled `3` and not `1–3`.

**Bounds.** `bbox` is optional and defaults to the metro's own envelope at summary level `310`.
`MAX_BBOX_DEG = 4.0` degrees on either axis, `MAX_FEATURES = 12000`, `MAX_BODY_BYTES = 6_000_000`
uncompressed; a breach is `422` with `{"error": {"code": "BBOX_TOO_LARGE" | "AREA_TOO_LARGE",
"message": …}}`. A bbox that is not four ordered numbers is `422 BAD_BBOX`; a layer that is not one
of the shaded layers is `422 BAD_LAYER`; an unknown metro is `404 NOT_FOUND`.

The two size caps were re-measured for Census tracts on 2026-09-12 (they had been sized for the
ZCTA era: `MAX_FEATURES` was 4000 and `MAX_BODY_BYTES` 2_000_000, which refused New York's own
first view). `MAX_BBOX_DEG` is unchanged and is what refuses a state — a whole-Texas box is about
13 degrees on a side and is refused on span before a row is counted. For scale, measured on real
TIGER tract geometry: a New York first view at 1460 x 1228 px carries **7,470 tracts**, and the
densest 4-degree box anywhere in the country — the largest this route accepts — carries **9,767**;
both are served, the first at a delivery tolerance of 0.78 CSS px. A client should still send the
viewport `bbox` rather than rely on the metro default: the metro envelope is a larger answer than
any one screen needs.

**The `bbox` is what selects rows; the `{cbsa}` is not.** The query filters on summary level,
vintage and `ST_Intersects(geom, bbox)` and never on the CBSA — the path segment chooses the
whole-metro box a request with no `bbox` falls back to, the cache key, and the `404` for a metro
that does not exist, and nothing else. So a box is answered for the ground it names even when that
ground is outside the metro it was asked under: a client whose map has panned off the selected
metro keeps receiving real polygons under the view, and **a client must not decline to send a box
on the grounds that it lies outside the metro** — doing so blanks exactly that case.

**Licence.** A layer whose dataset is not `cleared` answers `200` with `"features": []` and
`"state": "disabled"` or `"blocked"` (+ `blocked_reason`) — never a `403`, because `/api/layers`
already lists a blocked layer so the UI can render it as unavailable, and a map that 403s cannot
draw that state. No figure from an uncleared dataset reaches the wire in any of those states. The
gate is checked twice over: against the layer catalogue's own `dataset_key`, and against the
dataset the rows are STAMPED with — which differ for `growth`, whose catalogue entry names
`acs5_prior` while its rows carry `acs5`, so either licence moving turns the layer off (see the
licence-gates table below). The response is cached for `BOUNDARY_TTL = 86400` seconds under a key
carrying `gate.version()`, so a licence decision makes every cached body unreachable in the same
instant (§11's one-minute ceiling), and the nightly writer's own version counter, so a rewrite
that changes values without moving a vintage does too. The key also carries the `bbox`, so two
viewports of one metro cannot collide.

**Compression is applied by the handler**, not by a global middleware, and the compressed bytes
are what the cache holds: `Content-Encoding: gzip` with `Vary: Accept-Encoding` when the request
accepted it, the same JSON otherwise. Every answer carries `x-cache: hit|miss`. **Geometry is
never simplified on the request path** — `ST_SimplifyPreserveTopology` measured five to eight
times the cost of the query itself; if a future geography needs it, the simplified geometry is
materialised by the nightly job, once per vintage.

## `GET /api/markets/{cbsa}/summary`

The METRO-WIDE distribution of every shaded layer — the figures the Browse "Market snapshot"
strip prints in its AREA mode (Task SNAP; ruling D-C50 as revised by the stakeholder,
2026-09-12). It is the boundary route's population, summarised: same `geo_area`/`geo_metric`
join, same summary level per layer, same metro envelope, no geometry on the wire.

Until this route existed the strip computed a "metro median" from
`/api/markets/{cbsa}/communities` — one row per **listing**, each practice's own five-mile ring —
while the map beside it painted Census geography. On Dallas that read Households **162K** over
tracts that hold 0–5,988 and Competition **41** over ZIP areas that hold 3–16: two numbers about
two different things under one caption. A client must not compute this from the boundary route
either: that route answers for a **viewport**, deliberately, so a median over whatever is on
screen is a different number every time the member pans.

```json
{
  "cbsa_geoid": "12420",
  "boundary_vintage": "2023",
  "attribution": ["Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023",
                  "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023"],
  "layers": [
    { "layer": "income", "summary_level": "140", "geo_label": "Census tract", "unit": "usd",
      "state": "enabled",
      "count": 577, "with_value": 561, "suppressed": 12, "no_data": 4,
      "median": 92150.0, "quantiles": [48200.0, 67400.0, 92150.0, 121300.0, 158900.0],
      "value_vintage": "2019–2023", "source_dataset": "acs5" }
  ]
}
```

**One body, all six shaded layers, in `SHADING`'s own order.** The strip shows them together, so
six requests would buy nothing but six chances to render half a card set.

**`quantiles` is `[p10, p25, p50, p75, p90]`** over the non-null, unsuppressed values, computed by
`percentile_cont` — an *interpolating* quantile, which describes a distribution rather than naming
five of its members — and **`median` is that array's own middle element**, read out rather than
measured a second time, so a card's value can never disagree with the bars drawn beside it. Both
are `null` when `with_value` is `0`. The extremes are deliberately p10/p90 and not min/max: one
outlying tract is not a class a summary should draw.

**The three counts partition the polygons**, and `count == with_value + suppressed + no_data`
always: `count` is every polygon of that layer's `summary_level` whose geometry intersects the
metro's envelope, `with_value` those carrying a published, unsuppressed figure, `suppressed` those
the margin rules or the Census's own publication rules hide (`high_moe`, `no_moe`,
`input_suppressed`, `source_flag`, `source_threshold` — the same verdicts the boundary route
serves per polygon), and `no_data` those with no `geo_metric` row at all. A suppressed polygon is
**counted and never summarised**: "eleven tracts, nine of them summarisable" is the honest
statement and "nine tracts" is not.

**Licence.** Identical to the boundary route's, checked the same way twice over — against the
layer catalogue's own `dataset_key` and against the dataset the rows are stamped with, which
differ for `growth` (`acs5_prior` against `acs5`), so either licence moving turns the layer off. A
layer that is not `cleared` answers with its `layer`, `summary_level`, `geo_label`, `unit`, its
`state` (`disabled` / `blocked` + `blocked_reason`) and **zeros and nulls for every figure and
every count** — never a `403`, because a client has to be able to draw "unavailable". Its dataset
drops out of `attribution` with it: nothing of that dataset is on the wire to attribute.

**Bounds and caching.** No `bbox` and no `layer` parameter — this is the metro, which is the
geography the card's caption names ("median of 503 Census tracts"; the word "metro" left that
caption in Task SNAP fix round 1, because the Census publishes a metro median of its own at
summary level 310 and this figure is not it). An unknown metro is `404 NOT_FOUND` in decision A5's
envelope. The answer is cached for `SUMMARY_TTL = 86400` seconds under a key carrying the boundary
vintage, **every value dataset's active vintage** (one body carries four of them, so a key naming
only the ACS vintage would serve a stale ZIP Business Patterns card for a day), `gate.version()`
and the nightly writer's own `GEO_VERSION_KEY` — so a licence decision or a rewrite makes every
cached body unreachable within the same minute (§11). Every answer carries `x-cache: hit|miss`.

## `GET /api/markets`

```json
[ { "cbsa_geoid": "12420", "name": "Austin, TX", "center": [30.31, -97.75], "zoom": 10 } ]
```

One row per **listing market key** (`listing.market`, the design's dropdown key, e.g. `"Austin,
TX"`) per CBSA that holds at least one **published** listing with a geocoded point
(`practice_location.cbsa_geoid`, found by the practice's own coordinates — never a name heuristic
over the CBSA's official name). Two listing market keys inside one CBSA are two rows (example:
`"Sacramento, CA"` and `"South Lake Tahoe, CA"`, both CBSA `40900`). A published listing whose
point lies outside every CBSA has no row here, and therefore no shading.

The reverse case — **one market key spanning two CBSAs**, which happens where a metro boundary runs
through a market key's own listings — is also two rows, with the same `name`. A client that resolves
a metro by name takes one of them, so the rows are ordered by `(name, cbsa_geoid)`: the choice is
arbitrary but **stable**, and the same catalogue will not shade a different CBSA between two
requests. A client that needs a particular one of the two must select on `cbsa_geoid`, not on `name`.

## `GET /api/markets/{cbsa}/communities?band=place|drive_10|drive_20` (default `place`)

```json
{
  "band": "place", "vintage": "2019–2023",
  "attribution": ["Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023", "…"],
  "communities": [
    { "listing_id": "…", "name": "Cedar Park city", "geo_precision": "rooftop",
      "location": "place_centroid", "lat": 30.55, "lng": -97.80,
      "pop": 81900, "hh": 27600, "income": 118400, "growth": 14.2, "pets": 15732, "econ": 685000, "vets": 7,
      "competition": { "count": 7, "geo_level": "zcta", "zctas": 2, "per_10k_households": 2.54, "level": "High" },
      "suppressed": [] }
  ]
}
```

Restricted to **published** listings only (`WHERE l.status = 'published'` in the query itself, not
a post-filter). `location` is `"disclosed_point"` (the listing's own geocoded point) only when the
seller has disclosed location AND a point exists; otherwise `"place_centroid"`, and `lat`/`lng`
follow whichever one is used.

**Fixture field names, numeric and un-formatted** — see the mapping table below for where each one
comes from. A field is simply **absent** from a community object, rather than `null`, whenever its
underlying dataset is not licence-cleared, its `market_metric` row does not exist yet, or (Phase C
only) the layer has been turned off. A field whose `market_metric` row is `suppressed` (too
imprecise at this geography — a data-quality decision, independent of licensing) instead has its
NAME listed in `suppressed` and carries no numeric key at all: `"hh" not in community` and `"hh" in
community["suppressed"]`, never a fabricated value and never a bare `null`.

`competition` is assembled from **two separate** `market_metric` rows (`establishments` and
`vets_per_10k_households`) after the fact, because either can be suppressed independently of the
other; a community always carries `count`/`geo_level`/`zctas` when the establishment count exists,
and only carries `per_10k_households`/`level` when the ratio row is *also* present and unsuppressed.
`level` (`Low` / `Moderate` / `High`, thresholds `< 1.4` / `< 2.2` / else) is computed here at
serialisation time from `metrics.competition_level`, never stored — it is a presentation band on a
measurement, not a measurement itself (A-C15 (7)).

## `GET /api/listings/{listing_id}/market?band=drive_10|drive_20|place` (default `drive_10`)

```json
{
  "listing_id": "…", "band": "drive_10", "geo_precision": "tract", "vintage": "2019–2023",
  "computed_at": "2026-09-10T02:00:00+00:00",
  "metrics": {
    "population":                { "value": 44800, "unit": "count", "is_derived": false, "formula_version": null, "moe": 2140, "suppressed": false, "suppress_reason": null, "source_dataset": "acs5", "vintage": "2019–2023", "geo_level": "catchment", "inputs": {"acs5": "2019–2023"} },
    "households":                { "…": "…" },
    "median_hh_income":          { "…": "…", "unit": "usd", "is_derived": true, "approximate": true },
    "population_growth_pct":     { "…": "…", "unit": "pct", "is_derived": true, "geo_level": "place", "inputs": {"acs5": "2019–2023", "acs5_prior": "2014–2018", "geo_level": "place"} },
    "pet_households_est":        { "…": "…", "is_derived": true, "assumed_rate": 0.57 },
    "establishments":            { "value": 7, "unit": "count", "source_dataset": "zbp", "vintage": "2022", "geo_level": "zcta" },
    "vets_per_10k_households":   { "…": "…", "unit": "ratio", "inputs": {"zbp": "2022", "geo_level": "zcta", "zctas": 2, "acs5": "2019–2023"} },
    "revenue_per_establishment": { "…": "…", "unit": "usd", "is_derived": true, "label": "Avg. payroll per practice", "source_dataset": "cbp", "geo_level": "county" },
    "income_index_vs_us":        { "…": "…", "unit": "pct", "is_derived": true }
  },
  "attribution": ["…"]
}
```

**The top-level `vintage` names the ACS vintage, deliberately** — the same field, computed the
same way (`act.get("acs5")`, the currently active `acs5` vintage) as `GET /api/markets/{cbsa}/
communities`'s own top-level `vintage`. It is not the vintage of an arbitrary row: `metrics` mixes
rows from two vintage families (`acs5`'s, and whichever `zbp`/`cbp` vintage produced
`establishments`/`revenue_per_establishment`), and every individual entry under `metrics` still
carries its OWN `vintage` and `source_dataset` for the figure it describes. Before A-C24 (1) this
field was read from the first row an unordered query happened to return — correct only because of
how two vintage strings happened to sort, and silently wrong the day a future pair sorts the other
way; it is direct now, not incidental.

**`opportunity_score` never appears — not null, not a flag, absent from `metrics` entirely.** It
is computed and stored by the materialisation and stays there, unpublished, until the VIN
Foundation signs off on its weights (A-C1 (9), A-C14 (5)); every serialiser in `app/api/market.py`
skips the row outright. Do not build a frontend that reads for the key's presence as a "is the
score ready" check — it is not a readiness signal, it is a standing decision.

**`suppressed` and `approximate` are never the same fact and are never both true on one entry.**
`suppressed: true` means the value is too imprecise to show at all — `value` is `null` and
`suppress_reason` names why (`no_moe`: the estimate arrived with no margin of error and is treated
as unmeasured, never as certain; `high_moe`: a margin that IS present but too wide;
`input_suppressed`: a derived figure whose own input was suppressed). `approximate: true` (present
only on `median_hh_income` at a catchment band) means the value SHOWN is itself an approximation
(a household-weighted median of tract medians, interpolated, which has no combined margin of
error by construction, A-C21 (5); it was a household-weighted AVERAGE of those medians until
2026-09-12 — Census plan §14, Task INCOME-MEDIAN) — it is never suppressed, because there is a real value to show, just one
carrying its own caveat. The same metric can be suppressed at one band and approximate at another.

**Cache.** A hit returns the identical payload with header `x-cache: hit`; a miss computes it,
writes it, and returns it with `x-cache: miss`. The key is

```
listing:{listing_id}:market:{band}:v{listing_version}:g{gate_version}
```

TTL 86400 s (24 h). **The `{band}` segment is a correction beyond the plan's original sketch**
(which wrote the key as `listing:{id}:market:v{n}` with no band in it, A-C23 (3)) — `band` is a
query parameter this same route answers, and without it in the key a member requesting one band
would be served whichever band happened to be cached first. `{listing_version}` is
`listing:{id}:market:version`, bumped on every `materialize_listing` call (nanosecond resolution,
so two materialisations inside one wall-clock second cannot collide on the same key). `{gate_version}`
is `app.census.gate`'s global counter, bumped by any admin licence decision — this is what makes a
just-blocked layer disappear from an already-cached panel within the 60 s the licence gate promises,
without a per-dataset cache-busting scheme.

**404 semantics — two different codes, and they mean different things:**

* `NOT_FOUND` — the id is not a valid UUID, names no listing at all, **or names a listing that
  exists but is not `published`**. The last case is deliberate: a market panel is never served for
  an unpublished listing, whether or not it happens to still carry `market_metric` rows from
  before it was withdrawn — the same posture `GET /api/markets/{cbsa}/communities` already takes
  in its own SQL (`WHERE l.status = 'published'`). Nothing is enqueued.
* `NO_MARKET_DATA` — the listing exists, IS published, and has no `market_metric` rows for the
  requested band yet. One `census.backfill_listing` task is enqueued for it, deduplicated for 10
  minutes by a `backfill:{listing_id}` Redis key (`SET NX`) so repeated polling from a buyer's
  browser cannot flood the queue.

(A-C23 (2): earlier, the publication check and the backfill-dedupe check were compounded into one
`if`, which only ever gated whether to enqueue a backfill — it never gated whether to SERVE a
panel that already had rows, so an existing, unpublished, previously-materialised listing would
have had its panel served in full. The two checks are now separate, and the publication check
happens before `market_metric` is even queried.)

## Licence gates — every one of them, including the two this task closed

A `market_metric` row's `source_dataset` names the ONE dataset it is stamped with, and the generic
rule is simple: hidden unless that dataset's `license_status` is `cleared`. Three figures fold in a
SECOND dataset the generic rule cannot see, and each needs its own explicit check:

| Figure | Stamped `source_dataset` | Also gated on | Why |
|---|---|---|---|
| `population_growth_pct` (`growth`) | `acs5` | `acs5_prior` | The formula diffs two ACS vintages; the row can only carry one dataset key, and it is not the baseline's. |
| `vets_per_10k_households` | `zbp` or `cbp` (whichever produced the establishment count) | `acs5` | The ratio always divides by a household estimate, regardless of which dataset produced the count. |
| `establishments` (`vets`), **only when its own `source_dataset` is `cbp`** | `cbp` | `acs5` | The `cbp` fallback (no usable ZBP data) apportions the county establishment count by household share; the primary `zbp` path counts ZIP-code establishments alone and folds in no household data, so it needs no extra gate. |

The last two rows are this task's own fix (A-C23 (1)): before it, withdrawing the household
dataset's (`acs5`) licence left the vets-per-household ratio and the CBP-apportioned fallback
count visible, while growth correctly vanished under the equivalent check that already existed for
it — a licence hole of exactly growth's shape, on a rule this programme treats as legally
load-bearing. Both are implemented as one shared check (`_extra_cleared` in `app/api/market.py`),
used by `GET /api/markets/{cbsa}/communities` and `GET /api/listings/{id}/market` alike.

## `GET /api/admin/data-sources` and `POST /api/admin/data-sources/{dataset_key}/license`

```json
[
  { "dataset_key": "zbp", "display_name": "ZIP Code Business Patterns",
    "api_dataset_id": "2022/cbp", "vintage": "2022", "refresh_cadence": "Annual (Apr)",
    "license_status": "cleared", "license_name": "Public domain",
    "license_url": "https://www.census.gov/data/developers/about/terms-of-service.html",
    "attribution_text": "Source: U.S. Census Bureau, ZIP Code Business Patterns, 2022",
    "last_verified_at": "2026-09-01T00:00:00+00:00", "drift_flagged": false, "notes": null,
    "active_vintage": "2022", "active_vintage_note": "…",
    "last_run": { "status": "succeeded", "finished_at": "2026-09-01T00:05:00+00:00", "rows_written": 41200 } }
]
```

Every registered dataset, blocked and unresolved ones included and marked as such — this is the
console behind `CLAUDE.md`'s "Blocked datasets never ship." Reading it is not a decision and
writes no audit row.

```
POST /api/admin/data-sources/{dataset_key}/license
{ "status": "cleared" | "unresolved" | "blocked", "name"?: string, "url"?: "https://…", "notes"?: string }
→ { "dataset_key": "…", "license_status": "…" }
```

Only `status` is required — every other field `COALESCE`s onto what is already recorded, so
blocking a source does not mean retyping its licence name and URL. `url`, if given, must be
`https://` (`422 BAD_FIELD` otherwise — the drift sweep re-fetches it quarterly and hashes what
comes back, and clear text lets anything on the path rewrite the page that comparison relies on).
Unknown `dataset_key` is `404 NOT_FOUND`.

**Two ledgers, and they record different things.** `audit_log` (`app.auth.audit`) records WHO
changed the gate, from what to what, for the standing "who did this" trail every admin action
gets. `license_audit_log` is the LICENCE ledger the quarterly drift sweep also writes into
(`app.census.license`); a human decision lands a row there too, with `changed = false` (a decision
is not evidence that the published terms moved) and `url` set to the literal string `"operator
decision"` when none was supplied, since the column is `NOT NULL` and a decision made without a
fetch still has to say what it was.

**`last_verified_at` has two authors and `drift_flagged` is never derived from it.** The quarterly
sweep sets `last_verified_at` only on a check that actually read a body — a dataset with no
`license_audit_log` row, or whose only check failed or 404ed, reads `null`. A human decision here
is the second author: an admin who has just read the terms is treated as a verification event too,
without fetching anything, and the two are told apart afterward only in the ledger (a decision row
carries no `content_sha256` and no `http_status`). `drift_flagged` is a completely separate column:
a later sweep that finds the terms unchanged since a flagged drift REFRESHES `last_verified_at` and
leaves the flag standing; only a decision made here clears it. Do not build a UI that infers
"verified, no drift" from a recent `last_verified_at` alone.

`attribution_text` is returned verbatim and composed nowhere in the frontend — it is legally
load-bearing (spec §12), and the point of holding it in the database is that a terms change is one
`UPDATE`, not a redeploy.

## Fixture → field mapping (`logic.js` → this API)

The seven field names the design's own fixtures (`communities()`, `VETS`, `ECON_K`) already use,
carried straight across as plain numerics — Sub-project 2 does not need to invent new field names,
only a new source for the same seven:

| Field | Comes from | Notes |
|---|---|---|
| `pop` | `communities[].pop` | ACS population estimate. The catchment band where that band has figures, the `place` band where it has none — see "Which band a listing's figures come from" below. |
| `hh` | `communities[].hh` | ACS households. |
| `income` | `communities[].income` | ACS median household income. |
| `growth` | `communities[].growth` | Derived: two ACS vintages compared. Vintage statement: `ACS 2014–2018 → 2019–2023`. Gated on `acs5_prior` (see the licence-gates table above), not merely on the `acs5` stamp the row carries. |
| `pets` | `communities[].pets` | Derived: households × 0.57, a national placeholder rate — not a licensed pet-ownership figure (that dataset is `blocked`; see `CLAUDE.md`). |
| `econ` | `communities[].econ` | Payroll per establishment in thousands of dollars (`CBP payroll ÷ establishments`), **county** level. The database column is historically named `revenue_per_establishment`, but the name is wrong; the figure is payroll, not revenue. |
| `vets` | `communities[].vets` | The `establishments` figure: ZBP ZIP-code count aggregated to the community, or the labelled county-CBP fallback when ZBP has nothing usable. |

`GET /api/listings/{id}/market`'s `metrics.*.value` carries the same underlying numbers,
unformatted, for the detail page's market report; `metrics.income_index_vs_us`,
`metrics.vets_per_10k_households` and the still-unpublished `opportunity_score` (with its
`components`) are the three figures the design's `marketPanel()` fixture (`incomeNat = 75149`,
`per10k`, `score`) sketched without a real source.

### Which band a listing's figures come from (`community_label`, Task B10 / D-C32, D-C38, D-C39)

`app/census/serve.py::community_rows` serves **each figure at its own honest geography, and the
card names it, per tile** (D-C38, John, 2026-09-11). This supersedes the whole-row rule D-C32
shipped: that rule built the row from the `place` band first and consulted `drive_10` only when
all six figures came out null. It was written for one condition — the Orlando listing below — and
was never asked what it does to a listing INSIDE a large city. All twelve Dallas listings sit in
one Census place, so all twelve were served the City of Dallas: one median household income,
$67,760, on twelve cards headed with twelve different neighbourhoods, while each practice's own
catchment figures sat materialised in `market_metric` and unreachable by any screen.

The rule now, figure by figure:

| Figure | Geography served | Why |
|---|---|---|
| `pop`, `hh`, `income`, `vets` | the catchment band **only when `geo_precision` is `"rooftop"`**, otherwise `place` | These vary by band, and the catchment is the finer reading — *when the point it is drawn around is the practice*. They move as **one group**: one `community_label` describes all of them, so a group drawn half from the ring and half from the city would put a city figure under a ring caption — the defect being fixed. A figure the chosen band does not have is `null`; it is never backfilled from the other band. See "When the ring is offered at all" below. |
| `growth` | `place`, or `county` where the listing has no place | `population_growth_pct` **cannot vary by band at all.** `app/census/materialize.py` computes it once per listing, outside the band loop, and writes that one value into all three bands (plan D12). Its resolution below place-or-county waits on the 2010→2020 tract crosswalk, a registered Phase C deferral. |
| `econ` (`econ_k`) | `county`, always | `materialize.py` always writes the county CBP row, identically in all three bands. |

**The choice of band for the area group is decided on FIGURES, not on row presence** — a place
band that yields nothing (no rows, every row `suppressed`, or every row stamped with a dataset
the VIN Foundation has not cleared) is indistinguishable from no place at all to the buyer.
`drive_20` is never a fallback: a wider area served under a narrower heading would be a reading
the data does not support.

`GET /api/listings` and `GET /api/listings/{id}` therefore carry three more fields:

| Field | Value | Meaning |
|---|---|---|
| `community_label` | `null` | The area figures came from the listing's own community (the `place` band), or there are no figures at all. The design names that community from the listing's own `area`, and its wording stands unchanged. |
| `community_label` | `"Within about 5 miles of the practice"` | The area figures came from the catchment band. The frontend MUST render this label wherever it names the area — a buyer is never shown a catchment disguised as a named city. |
| `growth_scope` | e.g. `"Dallas"`, `"Orange County"` | The geography the GROWTH figure was measured at, which `community_label` does not describe. The frontend renders it on the Growth tile's own sub-line, so the figure stops implying it describes the ring beside it. `null` where the geography has no name to give. |
| `income_note` | e.g. `"Within about 5 miles of the practice · approximate"`, or `"Approximate"` | Replaces the median-income tile's sub-line when that median is an approximation — a catchment median is a household-weighted median of the tract medians inside the ring rather than a published Census figure, and can never be suppressed. The guard is the SERVED ROW's own `is_derived`, never the band the area group came from, so an approximate PLACE median carries the qualifier too; with no `community_label` there is no area to name and the note is the bare word `"Approximate"`. `null` for a published median, and the design's own sub-line then stands. Known limit, ruled and accepted: because the tile has ONE sub-line, a note replaces the vintage rather than joining it — a tile carrying a note does not show its year. |

**When the ring is offered at all (controller ruling, GEO-WIRE fix round 1).** `practice_catchment`
is an 8 km buffer around `practice_location.point`, and `community_label` tells the buyer it is
"Within about 5 miles of the practice". That sentence is true of a rooftop match and of nothing
else. The seller wizard collects a city and a ZIP and no street, so the §11 fallback ladder
resolves a real seller's listing at `zcta` — **a ZIP-code centroid**, which in a large ZIP is miles
from the practice. Wiring the geocode onto publish (Task GEO-WIRE) made that the ordinary case
rather than a rarity.

So the area group is **served the `place` band** — the listing's own Census place — whenever
`geo_precision` is anything but `"rooftop"`. That is the path the design already renders: **no
`community_label`**, the design's own sub-lines, `growth_scope` and `income_note` exactly as they
behave for a place band today. **No new string is introduced anywhere.** A rooftop listing is
unchanged, and **a listing with no `practice_location` row is unaffected** — the rule has to KNOW
the point is approximate, and "never geocoded" says nothing about where it is. All twenty-nine QA
demo hospitals carry a street and resolve at rooftop, so none of them moves.

**What "its place" means, exactly, and when there is not one.** The §11 ladder fills every
geography the point it resolved can be joined to, so a ZCTA-precision listing carries the place its
ZIP centroid lies inside. So the rule reads: such a listing is served **its city where the ZIP
centroid lies in one; otherwise `place_geoid` is `null`, the county carries growth and payroll and
the area figures are unavailable** — `pop`, `hh`, `income` and `vets` are all `null` and the
frontend reaches the design's own "Community data unavailable" card, exactly as it does for a
listing with no figures at all. That is the unincorporated case (D-C32's Orlando condition, one
rung lower), and it is a real state, not a defect: the alternative is reaching for a place whose
boundary does not contain the practice, which is the class of false statement this whole rule
exists to remove.

**The ring is described by DISTANCE, not by time** (D-C39). The band is an 8 km straight-line
buffer from the practice point (spec §8: "straight-line buffers of 8 km (≈10 min) and 16 km
(≈20 min) from the practice point, labeled as approximations"), not a routed drive time, and spec
§15 still lists true drive-time isochrones as **open** for V1. "About 5 miles" is what the
geometry supports; "10 minutes" was a reading of it.

`growth_scope` needs a geoid lookup, and the lookup is deliberate: this document used to say
"There is no geoid lookup and none is wanted", which D-C38 supersedes. The name comes from
`practice_location.place_geoid` joined to `geo_area.name` at summary level `160`, or
`county_geoid` at `050`, on the active `tiger_cb` vintage — one batched query for a whole page,
never one per row. TIGER's place `NAME` drops the legal descriptor ("Dallas") while its county
`NAMELSAD` keeps it ("Orange County"). The API serves each name EXACTLY as TIGER gives it and
composes no prefix of its own: summary level 160 covers Census designated places as well as
incorporated ones, so a composed "City of " would have rendered "City of Florin" — a CDP that is
not a city — on the tile whose whole purpose is to say truthfully where its number came from
(the controller's ruling on the implementer's own concern, 2026-09-11). A consumer must not
synthesise a descriptor in front of one either.

The listing D-C32 was written for is the Orlando specialist centre. It geocoded ROOFTOP like every
other seeded hospital and its address is not wrong in any way, but it sits in unincorporated
Orange County where the Census has no `place`, so it has no `place`-band row — and complete
`drive_10` figures that describe its market perfectly well. It is also the one listing whose
growth figure is county-level rather than place-level, which `growth_scope` now says out loud
instead of pooling it in silence.

Where neither band has figures every field is `null`, including all three above, and the frontend
reaches the design's own "Community data unavailable" card. A per-figure rule makes that row
RARER; it does not make it unreachable. **A figure the database does not have is `null` in the
payload — never `0`, never `""`** (D-C31: a missing figure is omitted, never zeroed), because
`null` is the only value the frontend's own guards read as absence.

## When a listing gets its geography (the per-listing lifecycle, Task GEO-WIRE)

Every endpoint above answers out of `practice_location` and `market_metric`, and both are written
by the per-listing chain — `census.geocode_listing` → `census.backfill_listing` → `market_metric`.
Phase B built that chain; Task B9 put the publish trigger on it, and Task GEO-WIRE closed what
that left: the enqueue had no dedupe, an address change did not invalidate a resolved geography,
and the geocode did not write the pin at all — so a seller's published listing reached Browse with
no pin however well it geocoded. This is the whole of what triggers it, and what invalidates it.

| Event | Route | What happens |
|---|---|---|
| A reviewer publishes a listing | `POST /api/admin/listings/{listing_id}/decide` (`action: "publish"`) | If the listing has no `practice_location` row, `census.geocode_listing` is enqueued **by name** after the transaction commits |
| A seller puts a paused listing back on the market | `POST /api/seller/listings/{listing_id}/status` (`action: "republish"`) | The same, on the same condition |
| A seller changes the address | `PATCH /api/seller/listings/{listing_id}?step=2` | **a changed `city` or `zip`** deletes the listing's `practice_location` row in the same transaction and forgets the dedupe below, so the next publish resolves the new address |

The enqueue is **deduped on the listing id for 600 seconds** (`app/api/market.py`'s own
`BACKFILL_DEDUPE_TTL` shape). `practice_location` alone cannot dedupe it: that row is written by
the WORKER, so every publish inside the window between the enqueue and the write saw no row.
An address edit is the one event that re-opens the window early, for the obvious reason — a
correction arrives immediately after the publish that revealed the mistake.

The request path **never imports a Census write** (spec §10): the task is asked for by name
through `celery_app.send_task`, exactly as `app/tasks/census.py` asks for the backfill.

`census.geocode_listing` writes **both** point columns from the one resolved coordinate:
`practice_location.point` (NAD83, the geography every figure above is computed against) and
`listing.geom` (WGS84, the pin `GET /api/listings` serves as `lat`/`lng`, still blanked for a
listing whose seller has not disclosed its location). Before this, `listing.geom` was written by
`scripts/seed_listings.py` alone.

**The twenty-nine demo hospitals are unaffected and still take the operator path.**
`scripts/census_load.py geocode` resolves every listing that has no `practice_location` row;
`--force` re-resolves one that has, and `--listing <id>` re-resolves the listing it names whether
or not it already has a location — **both** are doors to a re-resolve, and a re-resolve of a seed
replaces its curated pin with the Census geocoder's own match. `DEPLOY.md` carries the runbook.
Nothing above changes that command or the rows it has already written.

**What precision a seller's address can reach, and why it is now on every listing payload.** The
approved wizard's step 2 collects a city and a ZIP and nothing else — **the wizard collects a city
and a ZIP and no street**, and inventing a field is out of scope (spec Q2, D12) — so the Census
geocoder cannot match a street address and the §11 ladder resolves the listing at `zcta`: a
ZIP-code centroid, not the practice. `GET /api/listings` and `GET /api/listings/{id}` therefore
carry **`geo_precision`** (`"rooftop" | "tract" | "zcta" | "place" | "county"`, or `null` for a
listing that has never been geocoded) beside the community fields, the same value
`GET /api/markets/{cbsa}/communities` and `GET /api/listings/{listing_id}/market` have carried
since Task B5. The copy rule below — `geo_precision != "rooftop"` → "approximate community data" —
has always applied to it; until now the listing payload gave the card no way to honour it. It is
NOT gated on `location_disclosed`: it says how well the point is known, never where it is.

Such a listing is ALSO served the `place` band for its area figures rather than the catchment ring
— "When the ring is offered at all" above — so the figures on its card describe a real Census
place, and `community_label` is `null`.

## Copy rules (spec §8/§12/§14) the frontend must honour when wiring this up

* Every figure shown carries its dataset and vintage — `attribution[]` at the response level,
  `metrics[].vintage`/`source_dataset` per figure.
* `is_derived: true` → render as "derived estimate", never presented as a raw Census number.
* `median_hh_income.approximate: true` → render "approximate" beside the value. On the listing
  card this arrives pre-composed as `income_note` (D-C38), because the card's tile has one
  sub-line and it has to carry the area and the qualifier together.
* `suppressed: true` → render "Estimate too imprecise to show at this geography", never a blank or
  a zero.
* `geo_precision != "rooftop"` → render "approximate community data" near the map pin. Note that
  such a listing is also served the `place` band for its area figures rather than the ring (see
  "When the ring is offered at all" above), so the caption near the pin is the only place the
  approximation is stated — the figures themselves are a real Census geography, not an estimate.
* On the map, `value: null` with `suppressed: false` is the no-data class with "No data for this
  area"; `suppressed: true` is the same class with the suppression wording above; `band_ambiguous`
  `true` renders the value plus "this margin spans two legend bands" — never grey, because greying
  a measured figure is its own false statement.
* `opportunity_score`, on the day it is approved for publication, always renders with its three
  `components` and never immediately beside the asking price (spec §14) — there is nothing to wire
  today, since the key never arrives.

## Design-vs-spec copy conflicts

John's ruling (A-C1 (11)): the four conflicts the plan's pre-flight found between the approved V3
design's hard-coded copy and the Census spec's wording **resolve to the spec's wording** — "Growth
since 2015" becomes the vintage statement above; "5–10 min drive time" / "10–20 min drive time"
keep their labels but the caveat carries the "straight-line approximation" language (already in
`GET /api/layers`'s `caveat` above); the competition card's caveat carries the proxy sentence
(also already in `/api/layers`); and the econ layer is "Average Practice Payroll" /
"Avg. payroll per practice" (`revenue_per_establishment`'s `label`). **The API supplies all three
strings already** (`/api/layers`, `/api/listings/{id}/market`'s `label`); updating the rendered
design template itself is a separate, John-ruled task with its own screenshots (plan Task B6 note,
A-C0 paragraph 12) — this document is not that task, and no such change is in this release.

## Where this differs from the plan's original sketch

The plan's illustrative JSON (the "API contract" section written before any of Phase B was built)
is superseded in four ways the phase settled on while building it, all recorded above and none of
them cosmetic:

1. **`enabled: true` (boolean) → `state: "enabled" | "disabled" | "blocked"` (+ `blocked_reason`).**
   A boolean cannot distinguish "off because a member turned it off" from "off because the licence
   is not cleared" — the admin surface and the licence gate both need that distinction (A-C14 (4)).
2. **`opportunity_score` was sketched inline in the panel payload; it never ships.** A-C1 (9) /
   A-C14 (5): computed and stored, withheld from every response until the VIN Foundation signs off
   on its weights.
3. **The cache key gained a `{band}` segment** the sketch never had (A-C23 (3), above).
4. **The panel's top-level `vintage` is now computed, not read off a row.** The sketch showed a
   plain `"vintage": "2019–2023"` beside `computed_at` without saying where it came from; the
   phase-review found the shipped code took it from an unordered query's first row, correct only
   by accident of how two vintage strings sorted (A-C24 (1), above). It is `act.get("acs5")` now,
   deliberately, matching `communities()`'s own top-level `vintage`.

**Schema hardening (A-C24 (2)):** `market_metric.band` now carries `CHECK (band IN ('place',
'drive_10', 'drive_20'))` (migration `063`), matching the constraint its sibling
`practice_catchment.band` already had. Not an API shape change — no valid caller was ever affected
— but a table that could previously accept any string in that column now cannot.

## Verification (QA) — corrected, and not yet run under this task

The plan's own Phase B exit checklist named the wrong dataset for one of its two licence-flip
checks: it said to flip `cbp` and expect **both** `vets` and `econ` to vanish, but `vets`
(`establishments`) gates primarily on **`zbp`** (the ZIP-code business dataset) — `cbp` only
matters to it on the county-apportioned fallback path. Flipping `cbp` alone correctly hides `econ`
and, on its own, should leave `vets` untouched (proof the fallback did not silently activate).
Corrected checklist, to be run on QA once real listings exist there (Sub-project 2) and only on
John's word, per A-C13 (1) — **this task did not execute it; nothing below has been run live**:

1. Geocode a real listing (`census.geocode_listing`); confirm `practice_location`,
   `practice_catchment` and `market_metric` rows exist.
2. `GET /api/listings/{id}/market` returns the panel with `attribution`; `GET /api/markets/12420/
   communities` returns the listing's community with the seven fixture field names.
3. Flip `zbp` to `unresolved`; confirm `vets` and the `competition` object vanish from both
   endpoints within 60 s, and reappear when `zbp` is cleared again.
4. Flip `cbp` to `unresolved`; confirm `econ` (`revenue_per_establishment`) vanishes and
   reappears, and that `vets`/`competition` are unaffected (the ZBP path is untouched by this
   flip).
5. Flip `acs5` to `unresolved` (this task's own fix): confirm `pop`/`hh`/`income`/`growth`/`pets`
   vanish (the generic gate), **and** that `vets_per_10k_households`
   (`competition.per_10k_households`/`level`) also vanishes even though `zbp`/`cbp` remain
   cleared — the licence hole this task closed.

`DEPLOY.md`'s "Census Phase A exit (QA)" section already documents loading and activating the
reference datasets themselves (TIGER, ACS, CBP, ZBP, QWI, BDS) on the worker over `railway ssh`;
that runbook was written in Phase A and is not repeated here.

## Known gaps — stated plainly, not glossed over

Phase B is closed, but two things it was meant to reach are not done, and one publication decision
is still pending:

* **The Browse map's own fixture feed is unfixed.** `frontend/src/logic.js`'s `VETS` and `ECON_K`
  are keyed by design-fixture ids (`p1`…`g4`), so every one of the eighteen seeded QA listings
  still shades bottom-bucket on all six Browse market layers (A-C0 paragraph 18). Closing this
  needs a change to `logic.js`'s byte-locked footer export, which is queued for John as **D-C14**
  (A-C14 (6)): may Phase B's successor change that export and re-pin `app-generated.test.ts`, or
  does the feed become its own task? Unanswered as of this document — no Phase B task touched it.
* **Task B7 implements `GET /api/listings`'s Community Context strings.** John ruled (2026-09-08,
  Q2 / A-C1 (2)) that `app/api/listings.py::serialise` would format `pop`/`growth`/`income`/`hh`
  from `market_metric`, in the design's existing string spelling (`"81,900"`,
  `"+14.2% since 2015"`, …), plus two additional numeric fields `vets` and `econ_k` for Browse use.
  Task B7 implements this: the listing list (`GET /api/listings`) and detail (`GET /api/listings/{id}`)
  routes now carry all six fields populated when data is available, null when unavailable (dataset
  not cleared, value suppressed, or no `market_metric` rows for the listing). Task B10 adds the
  band fallback and the seventh field, `community_label`, that says which band answered — see
  "Which band a listing's figures come from" above.
* **`opportunity_score` is computed, stored, and withheld** until the VIN Foundation signs off on
  its weights (A-C1 (9)) — not a defect, a standing decision this document is not the place to
  revisit.
* **The basemap licence (Esri vs. CARTO) is one open decision**, recorded in the Census plan
  (`docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md`, "Basemap licence — one
  decision record") and referenced, not restated, here.
* **Phase C is entirely deferred by design**, each item with its own stated trigger in the plan's
  "Phase C — Deferred by design" table: tract-level choropleth tiles, true routing-engine
  isochrones, a satellite basemap, a licensed pet-ownership rate, an AIES revenue benchmark,
  block-group geography, auto-extending `market_state` to new listing states, individual
  competitor locations (Overture/Foursquare/VIN's own directory), the Google Places Aggregate
  freshness signal (Task C1), tract-level growth, and population-weighted catchment apportionment.
  None of it is in this release; none of the routes above hint at it beyond the fields the plan
  already reserved (e.g. `competition.freshness`, which this API does not emit).
