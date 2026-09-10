# Neighbourhood shading — real Census boundary polygons — Design

**Status:** requested by John Dean 2026-09-10, on the Browse screen's "Market data" map. Sub-project 3 (Census data layer), promoted out of Phase C by controller amendment **A-C33** and governed by his four rulings **D-C34**–**D-C37** of the same afternoon (`docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md:4629`, `:4640`). Those rulings are settled; this spec implements them and does not revisit them. New decisions below are numbered `D-NS1`…`D-NS18`; the design-bundle amendments this needs are the new family **A24**.

---

## 1. Purpose — the problem and the target

John's finding, verbatim:

> "the data is not to the granular level required at neighborhood level — right now it's just a blob over the whole city and misses the entire point of what is required and the required level of detail and data per neighborhood required to make a decision to buy a practice."

He then attached a screenshot and, correcting himself against it, said "it is SUPPOSE to look like this". **The screenshot is the target, not the defect** (A-C33). The picture the approved design draws is right; the geometry underneath it is not real.

What is underneath it today is a grid. `frontend/src/map/mosaic.js` says so in its own header, which was ported verbatim from the prototype's `MarketMapV3.jsx:1-9`:

> "the prototype has no ZCTA boundary file, so community areas are approximated as the cells nearest each community's centroid, clipped to the metro bounding box. Cells are contiguous and non-overlapping, which is what area shading requires, but they are NOT real Census boundaries … Production loads tiger_cb ZCTA polygons per the Census Data Source Specification (Sub-project 3) and drops this approximation."

The Census Data Source Specification says the same thing from the other side, in its §2b "Prototype deviation — must be replaced": the cells' "edges are grid artefacts rather than real neighbourhood lines — which is why the prototype reads blockier than the target design. … Production must load real polygons; the map component is structured so this is a data swap, not a redesign."

**This spec is that data swap.** The mosaic is deleted; the three fill layers draw real `geo_area` polygons, each at its own honest geography, each carrying its own value, margin of error and suppression verdict.

It is also, measured, a performance improvement rather than a cost. A-C33 measured the mosaic at **3,070 rectangles for two listings and 7,989 for five**; `frontend/src/components/MarketMapView.vue:154` records **12,560** for the design's own nine Austin communities. Real polygons are one to two orders of magnitude fewer objects — the Austin metro is about **130 ZCTAs** (D-C34). The blob is a listing-count artefact: it grows with how many practices are on the map, not with the data.

**In scope:** a per-geography metric table and its licence gate; a writer that fills it from the datasets already loaded; one member-gated endpoint that serves geometry joined to values; the Leaflet layer that draws it; the legend naming the geography; the hover tip carrying the margin of error; the design amendment that puts all of it in the reference so the zero-pixel gate can pass.

**Out of scope:** §12, which is D-C34–D-C37's own "what is deliberately NOT in the first slice" list, enumerated.

---

## 2. What is true today

**2.1 Three of the nine layers shade, and only those three change.** `frontend/src/logic.js:118` — `const FILL_KEYS = ["income", "growth", "econ"];`. `:121` — `const SYMBOL_KEYS = ["pets", "households", "competition"];`. The comment above them is the design's own rule: "Rates and medians belong to the area → choropleth fill (one at a time: two translucent fills mix into a third colour that means nothing)" and "Counts → graduated symbols, sized by value." D-C35 keeps the three symbol layers exactly where they are, and `logic.js:111`'s households breaks (`stops: [10000, 25000, 45000]`, first bucket `"< 10K"`) are the reason: city-scale class breaks on small areas would put essentially every polygon in the first bucket.

`FILL_KEYS` is declared and read by nothing (verified: the only occurrence under `frontend/src` is the declaration). It becomes load-bearing in §9.

**2.2 The colour is computed in `logic.js`, not in the map.** `logic.js:400-407`'s `bucket(metric, v)` walks `VALUE_LAYERS[metric].stops` right-open (`while (i < cfg.stops.length && v >= cfg.stops[i]) i++`) and returns `{color, t}` from `PALETTES[layerPalette][metric]`. `logic.js:409-414`'s `fmtMetric` formats it. `logic.js:511-524` attaches `{t, color, label}` per metric to each community, and `MarketMapView.vue:97` reads `site.values[props.activeLayer]`. The map component never sees a ramp. **Any new geometry has to enter through the same door, or the legend and the fill can disagree.**

The three fill layers' published bands, verbatim from `logic.js:108`, `:110`, `:112`:

| Key | `VALUE_LAYERS` label | Buckets | Stops |
|---|---|---|---|
| `income` | `Median Household Income (ACS)` | `< $50K`, `$50–75K`, `$75–100K`, `$100–150K`, `> $150K` | `[50000, 75000, 100000, 150000]` |
| `growth` | `Population Growth (ACS)` | `< 10%`, `10–20%`, `20–35%`, `> 35%` | `[10, 20, 35]` |
| `econ` | `Average Practice Payroll (CBP)` | `< $450K`, `$450–650K`, `$650–900K`, `> $900K` | `[450000, 650000, 900000]` |

D-C36 keeps every one of these values.

**2.3 The geometry is already loaded; some of the values are not.** `migrations/018_census_geo.sql` creates `geo_area (geo_id text, summary_level char(3), vintage text, name text, state_fips, county_fips, parent_geo_id, land_area_m2, geom geometry(MultiPolygon, 4269), centroid geometry(Point, 4269))`, primary key `(geo_id, summary_level, vintage)`, with `CREATE INDEX geo_area_geom_gix ON geo_area USING gist (geom);` and `geo_area_level_idx ON geo_area (summary_level, vintage)`. It holds **30,748 tracts, 6,885 places, 3,235 counties and 935 CBSAs** (measured against the live QA database). *The loaded ZCTA count is unverified here — this session could not query QA. `app/census/tiger.py:98` loads summary level `'860'`, so ZCTA geometry is expected to be present; the implementer must confirm the count before starting, and D-C34's "about 130 ZCTAs across the Austin metro" is the figure the plan measured.*

**Values are a different story, and this is the finding that sizes the work.** `app/census/acs.py:53-64`'s `GEOGRAPHIES()` loads ACS at summary levels `140` (tract), `160` (place), `050` (county), `040` (state), `310` (CBSA) and `010` (nation). **It does not load `860`.** `acs.py:67-86`'s `geoid()` raises `ValueError(summary_level)` for anything else. So `acs_measure` carries no ZCTA row today, and `B19013_001E` — the median household income D-C34 wants shaded at ZCTA — does not exist at that geography. §4 and D-NS3 address it.

The other two fills are already loaded at their ruled geographies: `acs5` and `acs5_prior` both carry `B01003_001E` at `160` (place growth), and `cbp_industry` carries NAICS `541940` at `050` (county payroll per establishment).

**2.4 The read path returns no geometry at all.** `app/api/market.py` mounts four routes, every one of them `dependencies=[Depends(REQUIRE_MARKET_READ)]` where `REQUIRE_MARKET_READ = require("market.read")` is a module-level constant resolved once at import (`market.py:87`) — deliberately, because `tests/auth/test_permissions.py` resolves a route's guard **by object identity** and a fresh `require(...)` per route reads as unguarded. `geo_area.geom` is read only inside SQL predicates (`ST_Intersects`, `ST_Contains`, `ST_Intersection`); the only geometry that ever reaches a client is a scalar `ST_Y`/`ST_X` of a centroid (`market.py:207`, `:219`). There is **no bbox bound and no size bound anywhere in `app/`**, and `app/main.py` adds exactly two middlewares — `CORSMiddleware` (conditional) and `SecurityHeadersMiddleware` — with **no `GZipMiddleware`**.

**2.5 The legend is entirely hard-coded and `/api/layers` has never been called.** Swatch colours come from `PALETTES`, labels from `VALUE_LAYERS[key].buckets`, source and vintage lines from `LAYER_META` (`logic.js:533-552`), rendered at `App.vue:392-408` (desktop) and `App.vue:1416-1430` (the phone frame). The only `fetch(` sites under `frontend/src` are `auth/api.ts:42`, `listings/seller.ts:325`, `admin/listings.ts:245` and `listings/load.ts:280`. Nothing has ever requested `/api/layers`, which has existed and been guarded since Phase B.

**2.6 The map has one shading primitive and it is a rectangle.** `MarketMapView.vue:88-103`'s `drawOverlay()` calls `engine.rectangle(bounds, {fillColor: v.color, fillOpacity: 0.5, stroke: false, interactive: true}, 'overlay', {html: tipHtml(site, v), sticky: true, className: 'rf-tip'}, () => props.onArea(site.name))` once per cell. `engines/leaflet.ts:85-92` passes every one through **one shared `L.canvas({padding: 0.3})` renderer** created at mount (`:51`) — load-bearing, and asserted in three test files. There is no `L.geoJSON` and no `L.polygon` anywhere in the tree.

**2.7 What the gates pin.** 49 approved states (`frontend/tests/screens.ts`), 13 of which mount a map (§9.3). `frontend/tests/baseline-manifest.json` freezes thirteen hashes, **none of them a Browse state and none of them a screen that mounts a map** — `mobile-detail` passes through `waitMap` on its way to the detail screen but captures the detail, where the map is unmounted. `frontend/tests/visual.spec.ts:44-79`'s `expectMosaicShading` samples `{x: 400, y: 200, width: 500, height: 600}` for the five `distinct.income` ramp colours composited at `fillOpacity 0.5` over Leaflet's `#ddd` ground, and runs on `browse` only, after the comparison. The basemap tiles are stubbed with a transparent GIF (`harness.ts:93`), which is why the ground is `#ddd` and why the capture is deterministic.

---

## 3. Data model — `migrations/064_geo_metric.sql`

**D-NS1 — one new table, `geo_metric`, and it is `market_metric`'s sibling, not its replacement.** `market_metric` is per (listing, band, metric, vintage): it answers "what is the market around *this practice*". `geo_metric` is per (geography, metric, vintage): it answers "what is true of *this ZIP code*". A polygon has no listing, and shading a metro's ZCTAs off `market_metric` would mean one row per listing per polygon, recomputed whenever a listing moved. The two tables share a shape, a suppression function (§6) and a licence trigger, and nothing else.

**D-NS2 — it is `064`, not `091`.** The highest number in `migrations/` today is `090_listing_photo_captions.sql`, but numbering here is range-partitioned, not sequential: D14 of the Census plan assigns **SP3-B `060`+** to this sub-project (`060_geocode_cache`, `061_census_listing_tables`, `062_census_listing_fixups`, `063_market_metric_band_check` are already taken), reserves `030`–`039` for the seller lifecycle (A-SL5), `040`–`049` for image identifiability, and `090`–`099` for main's platform and hotfix migrations (A-C10). `064` is the next free number in this sub-project's own range. The ledger runner applies each file **exactly once** and refuses only files whose bytes no longer match a recorded checksum (`scripts/migrate.py`'s `refuse_changed_files`), so a file that sorts before an already-applied `090` is applied on the next run without incident. `064` depends on `dataset_registry` (`017`) and nothing later.

```sql
-- Neighbourhood shading (spec 2026-09-10; D-C34, D-C35). One row per geography per metric per
-- vintage, at the geography the metric is honest at -- ZCTA '860' for income, place '160' for
-- growth, county '050' for payroll per establishment. `market_metric`'s sibling: same column
-- vocabulary, same licence gate, a different subject.
CREATE TABLE geo_metric (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,          -- '860' zcta | '160' place | '050' county (018's own comment)
  vintage text NOT NULL,                   -- the VALUE's vintage: '2019–2023' (acs5, en dash) | '2022' (cbp)
  metric_key text NOT NULL,                -- 'median_hh_income' | 'population_growth_pct' | 'revenue_per_establishment'
  value_num numeric,
  unit text NOT NULL,                      -- 'usd' | 'pct' -- market_metric's own vocabulary
  is_derived boolean NOT NULL DEFAULT false,
  formula_version text,
  moe numeric,
  suppressed boolean NOT NULL DEFAULT false,
  suppress_reason text,                    -- 'no_moe' | 'high_moe' | 'input_suppressed' | 'source_flag'
  inputs jsonb,                            -- D9's shape: {"acs5":"2019–2023","geo_level":"zcta"}
  source_dataset text NOT NULL REFERENCES dataset_registry(dataset_key),
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (geo_id, summary_level, vintage, metric_key)
);
-- The read path's only access pattern: one layer, one geography level, one vintage, joined to
-- geo_area by geo_id. Without this it is a sequential scan of every geography in six states.
CREATE INDEX geo_metric_layer_idx ON geo_metric (summary_level, metric_key, vintage);
```

The primary key is the proposal's, unchanged. Four columns are added beyond the proposal — `unit`, `is_derived`, `formula_version` and `inputs` — for one reason each: `unit` so the hover tip formats from the row rather than from a second table keyed by metric name; `is_derived` because two of the three metrics are derived and the copy rules (`docs/integrations/market-data-api.md`, "Copy rules") require "derived estimate" wording wherever it is true; `formula_version` because `metrics.FORMULA_VERSION` is `"v1"` and a formula change must leave historical values explicable (Census spec §8); `inputs` because `growth` folds **two** vintages and the row can only be stamped with one `source_dataset`, which is exactly the trap the licence-gates table in the contract document already documents.

**D-NS3 — the licence gate is a trigger on this table too, twinning `market_metric_license_gate`.**

```sql
-- The twin of market_metric_license_gate (migrations/061:59-68, body replaced at 062:22-28).
-- Same reason: a table that will accept a blocked dataset's values is one code path away from
-- shading them. The read path filters live (§5) and gate.py expires a cached answer inside 60 s,
-- but neither of those stops a nightly writer from filling the table with figures nobody may show
-- -- and a polygon layer is exactly where that would go unnoticed, because a map has no per-figure
-- attribution line to look wrong. IS DISTINCT FROM also catches a missing registry row (NULL).
CREATE OR REPLACE FUNCTION geo_metric_license_gate() RETURNS trigger AS $$
BEGIN
  IF (SELECT license_status FROM dataset_registry WHERE dataset_key = NEW.source_dataset) IS DISTINCT FROM 'cleared' THEN
    RAISE EXCEPTION 'geo_metric write refused: dataset % is not licence-cleared (licence gate)', NEW.source_dataset;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER geo_metric_license_gate BEFORE INSERT OR UPDATE ON geo_metric
  FOR EACH ROW EXECUTE FUNCTION geo_metric_license_gate();
```

The message names only the dataset key, following `062`'s own correction: `061`'s original read `license_status` twice — once in the `IF`, once in a `COALESCE` inside the message — so a concurrent registry update between the two reads could name a stale status. The function declares no `DECLARE` section, deliberately: `tests/test_migrate.py::test_migration_files_never_manage_their_own_transaction` treats `; BEGIN` as a self-managed transaction, and `061:53-58` and `062:16-21` both carry that note.

**D-NS4 — `acs5` gains summary level `860`, and this is a real ingest, not a join.** A-C33's "no new ingest is required to start" is true of *geometry* and only of geometry; §2.3 shows there are no ZCTA ACS values. Two ways to get them, and one of them is wrong:

- **Aggregate tracts into ZCTAs** using `materialize.py:61-65`'s own `ST_Intersection` overlap pattern. Rejected: a median cannot be aggregated. `metrics.weighted_median` (`metrics.py:71`) already does a household-weighted average of tract medians for the drive-time bands, and the contract document is explicit about the consequence — that figure carries `approximate: true`, "has no combined margin of error by construction", and is therefore **never suppressed**. Shading ~130 ZCTAs with medians that can never fail the CV test would hollow out D-C36, whose entire point is that the margin of error is shown and measured.
- **Load ACS at ZCTA.** `app/census/acs.py` gains `Geo("860", "zip code tabulation area:*", None)` in `GEOGRAPHIES()` and a `if summary_level == "860": return field("zip code tabulation area")` branch in `geoid()`. *The exact `for=`/`in=` clause is unverified in this session — the implementer must check it against the Census API's own geography list for the active `acs5` vintage before the load. ZCTAs have not been nested inside states in the ACS 5-year API since the 2019 vintage, so the query is expected to be national and to return roughly 33,700 rows per variable, which is well inside `client.py`'s size cap per request but is the largest single ACS page this pipeline has issued.*

`load_acs` gains an optional `levels: list[str] | None` filter so `860` can be loaded on its own rather than re-running all six geographies for six states; the run is recorded in `ingest_run` exactly as any other. `vintage.TABLE_FOR` already maps `acs5 → acs_measure` and needs no change; `active_vintage` is untouched, because the vintage string does not move.

---

## 4. The writer — `app/census/geo_metric.py`

**D-NS5 — one new module, one public function, and it computes nothing that already has an implementation.**

```python
def materialize_geo(conn, redis) -> dict[str, int]:
    """Rebuild geo_metric for every geography in a market_state state, at the three ruled
    levels. Returns {metric_key: rows_written}."""
```

What it computes, layer by layer, is exactly D-C35's assignment and nothing wider:

| Layer | Metric key | Level | Source | Value | MOE |
|---|---|---|---|---|---|
| `income` | `median_hh_income` | `'860'` ZCTA | `acs_measure` `B19013_001E` / `B19013_001M` at `860` (D-NS4) | the estimate as loaded | `B19013_001M`, as loaded |
| `growth` | `population_growth_pct` | `'160'` place | `acs_measure` `B01003_001E` at `160` for `acs5` and for `acs5_prior` | `metrics.population_growth_pct(now, prior)` | **none** — see §6 |
| `econ` | `revenue_per_establishment` | `'050'` county | `cbp_industry` NAICS `'541940'` at `050` | `metrics.revenue_per_establishment(annual_payroll_k, establishments)` | **none** — CBP is a census, not a sample |

**D-NS6 — it calls `app/census/metrics.py` and `materialize._suppression`; it reimplements neither.** D-C36 is explicit: "`materialize._suppression` is reused verbatim — no second implementation of the CV/Z90 test, because two suppression code paths that disagree would put '$72,400' in the docked panel over a grey polygon." Concretely, `geo_metric.py` does `from app.census.materialize import _suppression` and calls it on the income rows only, with the same `(value, moe)` argument order and the same three outcomes (`(False, None)`, `(True, "no_moe")`, `(True, "high_moe")`). The underscore is retained rather than the function renamed: a rename would touch `materialize.py`'s three call sites for no behavioural reason, and the "surgical diffs" rule outranks the naming convention here. The import is asserted to resolve to the same object in §10.

The derived figures go through `metrics.py` unmodified — `population_growth_pct` (`metrics.py:91`) and `revenue_per_establishment` (`metrics.py:116`) — and each row is stamped `formula_version = metrics.FORMULA_VERSION` (`"v1"`) and `is_derived = True`. `median_hh_income` is `is_derived = False`: at ZCTA it is a published ACS estimate, not a weighted average, which is the whole point of D-NS4.

**D-NS7 — the write is per (level, metric, vintage), transactional and idempotent.** `DELETE FROM geo_metric WHERE summary_level = %s AND metric_key = %s AND vintage = %s` then one `executemany` upsert, inside one transaction per triple, following `materialize_listing`'s own `conn.autocommit = False` / `finally: restore` shape (`materialize.py:229`, `:289`). A failed triple rolls back and leaves the previous vintage's rows in place, which is Census spec §11's "keep the prior vintage active".

**D-NS8 — scope is the six `market_state` states, not the nation.** `migrations/017_census_registry.sql:47-52` seeds `market_state` with `'48'`, `'06'`, `'12'`, `'13'`, `'36'`, `'08'`. The writer reads that table and restricts every query by `geo_area.state_fips`, which is why the job is minutes rather than hours and why the table does not grow to 30,748 tract-scale rows it has no use for. National coverage is out of scope (§12) and is one of D-C37's two triggers.

**D-NS9 — it runs nightly, beside the materialisation, and never on the request path.** A new beat entry in `app/tasks/celery_app.py`, in the shape of the existing `materialize-nightly`:

```python
    "geo-metric-nightly": {"task": "census.materialize_geo_metrics", "schedule": crontab(minute=30, hour=3)},
```

03:30 UTC, half an hour after `materialize-nightly`'s 03:00. The two jobs are independent — neither reads the other's table — and the stagger exists so two heavy read-only passes over `acs_measure` do not overlap on one database. The task body follows `app/tasks/census.py:354-371`'s `materialize_metrics` exactly, returning `{"metrics": materialize_geo(conn, sync_redis())}`. Census spec §10's hard rule holds unchanged: "the request path never calls a Census endpoint."

Relationship to `app/census/materialize.py`, stated so nobody merges them: `materialize.py` stays the **only** writer of `market_metric` and is not edited by this sub-project at all, except that `_suppression` gains a second importer. `geo_metric.py` is the only writer of `geo_metric`. A listing's docked panel keeps reading `market_metric`; the map reads `geo_metric`; §6 is the test that makes the two agree.

---

## 5. The read path — one route

**D-NS10 — one endpoint, in `app/api/market.py`, in the existing family's own shape.**

```
GET /api/markets/{cbsa}/boundaries?layer=income|growth|econ[&bbox=minLng,minLat,maxLng,maxLat]
```

The metro is the unit because the Browse map is metro-scoped (`MARKETS` in `logic.js` carries a centre and `zoom: 10` per market, and `frontend/src/listings/load.ts:10` mirrors it as `MARKET_ZOOM = 10`), and because a whole Austin metro at ZCTA is about 130 polygons. `bbox` narrows it and is optional. Registered on the same router (`APIRouter(prefix="/api")`), so it is mounted only inside `app/main.py`'s `if settings.site_mode == "app":` block and 404s on production while `SITE_MODE=coming_soon`.

**The guard is the module constant, not a fresh call:**

```python
@router.get("/markets/{cbsa}/boundaries", dependencies=[Depends(REQUIRE_MARKET_READ)])
async def boundaries(cbsa: str, layer: str | None = Query(None), bbox: str | None = Query(None)) -> Response:
```

`REQUIRE_MARKET_READ = require("market.read")` (`market.py:87`) is resolved once at import for the identity reason recorded at `market.py:6-13`. `MARKET_DATA_PUBLIC` widens who satisfies it and never removes it, exactly as for the other four routes.

**The response is one GeoJSON `FeatureCollection` with foreign members** (RFC 7946 permits them; Leaflet's `L.geoJSON` ignores what it does not know):

```json
{
  "type": "FeatureCollection",
  "cbsa_geoid": "12420",
  "layer": "income",
  "metric_key": "median_hh_income",
  "summary_level": "860",
  "geo_label": "ZIP Code Tabulation Area",
  "unit": "usd",
  "state": "enabled",
  "boundary_vintage": "2023",
  "value_vintage": "2019–2023",
  "source_dataset": "acs5",
  "attribution": ["Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023",
                  "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023"],
  "values_without_geometry": 0,
  "features": [
    { "type": "Feature", "id": "78704",
      "properties": { "geo_id": "78704", "name": "ZCTA5 78704",
                      "value": 92150, "moe": 6420,
                      "suppressed": false, "suppress_reason": null, "band_ambiguous": true },
      "geometry": { "type": "MultiPolygon", "coordinates": [] } }
  ]
}
```

**D-NS11 — the SQL, and where simplification does not belong.**

```sql
SELECT g.geo_id, g.name, m.value_num, m.moe, m.suppressed, m.suppress_reason,
       ST_AsGeoJSON(ST_Transform(g.geom, 4326), 6) AS geometry
  FROM geo_area g
  LEFT JOIN geo_metric m
    ON m.geo_id = g.geo_id AND m.summary_level = g.summary_level
   AND m.metric_key = %(metric)s AND m.vintage = %(value_vintage)s
 WHERE g.summary_level = %(level)s AND g.vintage = %(geo_vintage)s
   AND ST_Intersects(g.geom, ST_Transform(ST_MakeEnvelope(%(w)s, %(s)s, %(e)s, %(n)s, 4326), 4269))
```

Three things about it are deliberate.

`ST_Transform(g.geom, 4326)` is required, not decorative: `geo_area.geom` is `geometry(MultiPolygon, 4269)` (NAD83) and GeoJSON is WGS84. The transform is what the rest of the pipeline already does (`materialize.py:61-65`, `catchment.py:55`). The `6` is measured to be a **no-op** — the `cb_500k` source already carries six or fewer decimals — and is kept as an explicit ceiling rather than a change.

The envelope is transformed **into** 4269 rather than the geometry column out of it, so the `geo_area_geom_gix` GiST index is usable on the predicate. The planner does choose it: an Austin z11 tract viewport runs in **49.8 ms** at full precision. A partial index restricted to one summary level brings that to **25.0 ms**; it is not in `064` because at ~130 ZCTAs the 25 ms is not the cost that matters, and a partial index per level is three indexes to keep in step with a table that has one access pattern. It is recorded as the first thing to add if the query ever appears in a slow log.

**`ST_SimplifyPreserveTopology` is not on this path.** It was measured at **five to eight times the cost of the query itself**, which makes it the dominant term of every request for a saving the response does not need. The conclusion is that simplification belongs at **write time or not at all**: if a future geography (tracts, national coverage) needs it, the simplified geometry is materialised into its own column or its own table by the nightly job, computed once per vintage rather than once per request. Census spec §2b's "Douglas–Peucker, ~0.0005° tolerance" recommendation is therefore a *write-time* instruction here, and at ZCTA/place/county for four metros nothing needs it.

**D-NS12 — the bounds, and what happens at them.**

| Bound | Value | On breach |
|---|---|---|
| `bbox` side length | `MAX_BBOX_DEG = 4.0` degrees on either axis | `422 BBOX_TOO_LARGE`, message naming the requested span and the cap |
| feature count | `MAX_FEATURES = 4000` | `422 AREA_TOO_LARGE`, message naming the count and the cap |
| uncompressed body | `MAX_BODY_BYTES = 2_000_000` | `422 AREA_TOO_LARGE`, same envelope |
| missing `bbox` | falls back to the CBSA's own `geo_area` envelope at level `'310'` | — |
| unknown `layer`, or a layer not in `FILL_KEYS` | — | `422 BAD_LAYER`, message naming `income`, `growth`, `econ` |
| unknown `cbsa` | — | `404 NOT_FOUND` |

Every refusal goes through `market.py:122-126`'s `_error(code, message, status)` and its `{"error": {"code", "message"}}` envelope, never a bare `HTTPException`, and query parameters are parsed by hand rather than through `Query(ge=…)` so a bad value gets the same envelope — the shape `_resolve_band` (`market.py:136-140`) already uses for `BAD_BAND`.

The caps exist because of one measurement: **a whole-Texas bounding box returns 6,884 tracts and 9.2 MB**, and there is no bound today. `MAX_BBOX_DEG = 4.0` is chosen against the geography rather than against the bytes — the Austin metro's own envelope is roughly 1.0° × 0.9°, and 4° on a side covers any single CBSA in the six states with room to spare, while refusing a state. `MAX_FEATURES = 4000` sits above the largest plausible single-metro ZCTA count and below the 6,884 the Texas box returns.

**D-NS13 — the cache key carries the gate version, so a licence withdrawal is unreachable at once.**

```
boundaries:{cbsa}:{layer}:{geo_vintage}:{value_vintage}:g{gate_version}
```

`{gate_version}` is `app.census.gate.version(r)` — the value of the Redis counter `market:gate:v`, which `gate.invalidate()` `INCR`s on **every** admin licence decision, including one that clears a dataset (`gate.py:60-64`). Incrementing it changes the `g{n}` segment of every cached boundary payload in the same instant, so the old bodies are orphaned rather than served; they expire on their own TTL. This is the identical mechanism the panel key already uses (`market.py:327`), and it is why D-C37 says "one route inside the existing `market:gate:v` cache key honours both" — §10's CDN row ("30 days, immutable") and §11's "the layer disappears within one minute" cannot both be true of a tile that carries values, and are both true of this.

`BOUNDARY_TTL = 86400` (24 h), matching `PANEL_TTL`. The worst case if the Redis `INCR` itself fails is the 60 s TTL on `gate:{dataset_key}` (`gate.py:36`), which is the ceiling spec §11 promises.

**Belt as well as braces:** on a cache miss the handler re-checks the dataset live against `dataset_registry`, through `serve._cleared` / `serve._extra_cleared`, exactly as the other market routes do (`market.py` never calls `gate.layer_enabled`; it re-filters on every miss). A layer whose dataset is not `cleared` returns `200` with `"features": []` and `"state": "disabled"` or `"blocked"` — never a 403, because `/api/layers` already lists a blocked layer so the UI can render it as unavailable, and a map that 403s cannot draw that state.

**D-NS14 — gzip is applied in the handler, not globally.** `app/main.py` has no `GZipMiddleware`, and this spec does not add one: adding compression to every response in the application, including the ones that carry `x-cache` and the security headers `SecurityHeadersMiddleware` puts on "EVERY answer", is a change far wider than the ask, and the "surgical diffs" rule outranks the convenience. Instead the handler compresses the one body it owns, once per cache key, and stores the **compressed bytes** in Redis:

- if the request's `Accept-Encoding` contains `gzip`: `Response(gz, media_type="application/geo+json", headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding", "x-cache": …})`
- otherwise the plain JSON body, decompressed from the same cached bytes.

The measurement that makes this worth doing: the GeoJSON for an Austin z11 tract viewport is **434 KB, 112 KB gzipped**, rising to about **800 KB at z10**. At ZCTA the payload is an order of magnitude smaller again, but the same code path serves whatever geography a future ruling puts on it. D-C37's escalation trigger is stated in the same units — "a metro whose polygon count makes a viewport response exceed 500 KB gzipped" — so the response must be measured gzipped for the trigger to mean anything.

**D-NS15 — `/api/layers` gains one member per layer, and the contract document gains a section.** Each of the three fill layers gains `"shading": {"summary_level": "860", "label": "ZIP Code Tabulation Area"}` (and `160`/`Place`, `050`/`County`); the six others carry `"shading": null`. This is a *new* member rather than a change to the existing `geo_level`, because `income`'s `geo_level` is `"place|catchment"` and describes the **panel's** geography — the docked panel and the map answer different questions about the same layer, and collapsing them is precisely the "silently promote a coarse figure into a fine slot" failure D-C35 forbids.

`tests/api/test_contract_doc.py::test_contract_doc_names_every_market_and_admin_route` asserts every mounted path appears in `docs/integrations/market-data-api.md`, so the new route **must** be documented in the same change or the backend gate goes red. That is the intended forcing function, not an obstacle.

---

## 6. Suppression and honesty

**D-NS16 — a polygon with no value is drawn, in a "no data" class, and never omitted.** Omitting it leaves a hole, and a hole on a choropleth reads as a boundary — a reader takes the un-shaded gap for a park, a lake, or the edge of the market, and none of those is what happened. Census spec §2b says the same in its own words: "Where a geography has no value, render it as an explicit 'no data' class — hatched or neutral grey — never as zero." The no-data fill is the design's own `--border-subtle` value `#e6e6e6` at the same `fillOpacity: 0.5` the design paints every other class at, so the change introduces no new style vocabulary. The legend gains a matching row (§9, and Q1 in §14).

Four different facts reach that class, and the hover tip says which:

| `suppress_reason` | Means | Tip |
|---|---|---|
| `no_moe` | An estimate arrived with no margin of error and is treated as unmeasured, never as certain (`_suppression`'s own docstring, A-C17 (1)) | "Estimate too imprecise to show at this geography" |
| `high_moe` | A margin that is present but wider than `metrics.CV_THRESHOLD = 0.30` at `Z90 = 1.645` | the same string |
| `source_flag` | CBP withheld or noise-flagged the county cell (`cbp_industry.flag`) | "Not published for this county" |
| no row at all | the geography exists in the boundary vintage and has no value in the value vintage (§7) | "No data for this area" |

The first two strings are the wording the contract document's copy rules already mandate ("`suppressed: true` → render 'Estimate too imprecise to show at this geography', never a blank or a zero"), so the map says what the panel says.

**D-NS17 — only `income` can be suppressed or band-ambiguous, and the tip says why the other two cannot.** This is the one place D-C36 under-determines the design, and it is worth stating plainly rather than papering over. `materialize.py:239-241` runs `_suppression` on `population`, `households` and `median_hh_income` and on nothing else. `population_growth_pct` is written with no `moe` (`materialize.py:255`) because it is a difference of two ACS 5-year estimates and no combined margin is published for it; `revenue_per_establishment` is written with no `moe` (`:266-270`) because County Business Patterns is a census of establishments, not a sample. Feeding either through `_suppression` with `moe = None` would return `(True, "no_moe")` and grey out **every** growth and payroll polygon in the country, which is the opposite of honest.

So: `_suppression` is applied to `median_hh_income` only. `growth` and `econ` are written unsuppressed and carry their honesty in the tip instead —

> Derived from two ACS 5-year periods (2014–2018 → 2019–2023). No combined margin of error is published.

> Payroll per establishment (NAICS 541940), county level. County Business Patterns is a census of establishments, not a sample; no margin of error applies.

— which is the same posture the layer catalogue already takes (`/api/layers`'s `caveat` for `econ` is "Payroll per establishment (NAICS 541940), not revenue; county level.", and A21/A-C29 already ruled that the label is payroll, not revenue).

**The ambiguity caveat.** For `income`, the polygon's value is band-ambiguous when the margin of error crosses a legend stop:

```
lo = value - moe ; hi = value + moe
ambiguous = band_index(lo) != band_index(hi)
```

where `band_index` is the design's own right-open rule, `while i < len(stops) and v >= stops[i]: i += 1` (`logic.js:404`). It is computed **server-side**, in `app/census/bands.py`, so that the figure the tip shows and the measurement that gates D-C34's tract toggle come from one implementation:

```python
INCOME_STOPS: tuple[int, ...] = (50000, 75000, 100000, 150000)   # logic.js:108 VALUE_LAYERS.income.stops
```

and pinned two-way by pytest against the amended design file itself — `tests/api/test_boundaries.py::test_the_design_income_stops_equal_the_band_constants` parses `VALUE_LAYERS` out of `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` and asserts equality, in the shape `tests/api/test_seller_listings.py::test_the_design_ownership_options_equal_ownerships_tuple` (A22, Task SL10 step 1) already established. A polygon whose margin spans a stop is **shown with its value and the caveat, never greyed** (D-C36, verbatim: "greying a measured figure is its own false statement"):

> $92,150 ± $6,420 — this margin spans two legend bands.

The share of polygons carrying `band_ambiguous: true` at level `140` is the measurement D-C34 makes the trigger for the tract toggle. `scripts/measure_band_ambiguity.py` produces it from `geo_metric` and `bands.py`, reporting the share per level; it is a reporting script, runs nowhere on the request path, and builds nothing.

**D-NS18 — the two suppression paths must be proved to agree, by test, not by inspection.** `tests/api/test_boundaries.py::test_the_endpoint_and_community_rows_agree_on_suppression` takes a published listing whose `practice_location.place_geoid` is `G`, and asserts, for the same metric and the same `acs5` vintage:

- `app.census.serve.community_rows(...)` returns `income` as `None` **if and only if** `geo_metric`'s row for `(G, '160', vintage, 'median_hh_income')` has `suppressed = true`; and
- the same holds through the endpoint's own JSON for the polygon whose `geo_id` is `G`.

A second, cheaper assertion pins the mechanism rather than the outcome: `app.census.geo_metric._suppression is app.census.materialize._suppression`. The two together are what stops the failure D-C36 names — a dollar figure in the docked panel over a grey polygon. *One caveat the implementer must handle: the parity case has to be run at the **place** level, because `community_rows` reads `market_metric` at the hard-coded `place` band (`serve.py:98`) and only `growth` shades at place. The income parity is therefore asserted against a place-level `geo_metric` row written for the test, not against the ZCTA row the map draws; the shared-function assertion is what covers the ZCTA path.*

---

## 7. Vintage

Boundaries come from `tiger_cb` and values from `acs5` (or `cbp`), and those vintages advance on different schedules and are not even the same *shape* of string: `tiger_cb` is a bare year, `'2023'`; `acs5` is an en-dashed range, `'2019–2023'` (U+2013, verified byte-wise, not a hyphen-minus); `cbp` and `zbp` are bare years, `'2022'`. `app/census/tiger.py:233` is the only place a vintage is cast to `int`, and an ACS vintage passed there would raise. They are not interchangeable and the payload must not pretend they are.

**The payload carries both, named separately.** `"boundary_vintage": "2023"` and `"value_vintage": "2019–2023"`, plus `attribution[]` read verbatim from `dataset_registry.attribution_text` — never composed in the frontend, because it is legally load-bearing and a terms change must be one `UPDATE` rather than a redeploy. The `tiger_cb` attribution string is `"Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023"` and the map's attribution control keeps carrying `"Tiles © Esri"` beside it. This is Census spec §2b's own last implementation note: "Attribute the geometry vintage alongside the value vintage; TIGER boundaries and ACS releases do not always share a year."

**A geography in one vintage and not the other, both directions:**

- **Geometry, no value** — the polygon is returned with `"value": null, "suppressed": false, "suppress_reason": null` and drawn in the no-data class (D-NS16). This is the common case at a vintage flip and after a new ZCTA is created.
- **Value, no geometry** — the row is dropped from `features` (there is nothing to draw) and counted in the top-level `"values_without_geometry": N`. The writer never invents a shape, and the endpoint never silently loses a row: a non-zero count is logged with the level and vintage on every cache miss, so a boundary vintage that has moved out from under the values announces itself instead of quietly shrinking the map.

The query joins geometry at `active_vintage['tiger_cb']` and values at `active_vintage[dataset]`, both read live, exactly as `materialize.py:130-131` and `market.py:210` already do. Nothing here reads a vintage off a row: A-C24 (1) is the recorded case of that going wrong, where a panel took `rows[0]["vintage"]` from an unordered query and was correct only by accident of how two vintage strings sorted.

---

## 8. The frontend

**8.1 Drawing.** `frontend/src/map/engine.ts` gains one primitive beside `rectangle`:

```ts
geoJson(fc: FeatureCollection, styleFor: (f: Feature) => AreaStyle, group: string,
        tooltipFor?: (f: Feature) => TooltipSpec, onClick?: (f: Feature) => void): Handle;
```

`frontend/src/map/engines/leaflet.ts` implements it as one `L.geoJSON(fc, { renderer: this.canvas, style, onEachFeature })` added to the named group. **The shared canvas renderer is passed through**, as it is for every rectangle today (`leaflet.ts:51`, `:87`): `leaflet.ts:49-50`'s note — "ONE canvas renderer per mount, shared by every mosaic cell. A renderer per rectangle is what makes a mosaic this dense unusable" — survives the mosaic and is asserted in `leaflet.test.ts:396-408` and `MarketMapView.test.ts:589`. Census spec §2b asks for exactly this: "Render as a Leaflet GeoJSON layer on a canvas renderer, classed on the same breaks the legend publishes. Classed fills, never a continuous gradient."

Three supporting changes fall out of it: `frontend/src/map/testing/leaflet-stub.ts` gains a `geoJSON` factory beside the existing `FakeLayer` family (`:26-37`); `frontend/src/map/boundary.test.ts:15`'s regex gains `geoJSON` to its `L.(map|tileLayer|marker|divIcon|circle|rectangle|canvas|layerGroup|control)\(` alternation, so a stray `L.geoJSON(` outside `map/engines/*` is caught the way every other Leaflet call is; and the polygon layer rides Leaflet's default `overlayPane` (z-index 400) with the pins above it in `markerPane`, unchanged — the Esri label tiles stay in `shadowPane` (`leaflet.ts:47`), which is the arrangement `harness.ts:24-34` and `visual.spec.ts:28` both already document.

**8.2 What the mosaic leaves behind.** Enumerated by reading the tree, because the estimate depends on it being complete.

**Deleted outright:**
- `frontend/src/map/mosaic.js` — `MOSAIC_STEP = 0.0055`, `BBOX_PAD_LAT = 0.13`, `BBOX_PAD_LNG = 0.15`, `mosaicBbox`, `mosaicCells`.
- `frontend/src/map/mosaic.test.ts` — all nine cases (the three constants, bbox padding, square tiling, nearest-centroid assignment, the `cos(lat)` longitude scaling, measuring from the cell centre, the far-community case, both sides of the `0.016` cutoff, and the empty input).

**Changed because they import it:**
- `frontend/src/components/MarketMapView.vue` — the import at `:44`; `drawOverlay()` at `:88-103`; `tipHtml()` at `:105-114`; the merged-watcher rationale at `:136-155`, whose closing sentence names "12,560 rectangles".
- `frontend/src/components/MarketMapView.test.ts` — `:28`'s import, `:58-62`'s `cellCount`, `:64-83`'s `drawOrder`/`roleOf` (which classify a layer as overlay by `l.bounds !== undefined`, a rectangle-shaped test), and every assertion keyed on a cell count: `:159`, `:191`, `:229`, `:244-276`, `:299`, `:420-443`, `:581-599`, `:601-609`, `:611-619`, `:621-641` (the whole-string `rf-tip` assertion), `:643-653`, `:790`.

**Changed because they describe it:**
- `frontend/src/map/engine.ts:5`, `:8` — the `AreaStyle` and `rf-tip` comments.
- `frontend/src/map/engines/leaflet.ts:49-50` and `frontend/src/map/engines/leaflet.test.ts:392-394` and its rectangle cases at `:396`, `:410`, `:421`, `:431`, `:444`, `:525`, `:539`, `:559`.
- `frontend/tests/smoke.spec.ts:230-244` (`'the Map tab shows community mosaic shading'`, which reads pixels off `.leaflet-overlay-pane canvas`) and `:395-407` (the repaint-budget test, whose stated rationale is the mosaic rebuild).
- `frontend/tests/visual.spec.ts:27`, `:40-79`, `:92` — `expectMosaicShading` becomes `expectBoundaryShading`, keeping its method exactly: sample the map region, decode in the page, match the five `distinct.income` ramp colours composited over `GROUND = 221`. Its purpose is unchanged and is worth restating, because it is the one guard the pixel gate cannot replace — "anything that blinds both targets at once is invisible to it", which is how an opaque tile stub once hid the whole mosaic while all 27 states passed at `maxDiffPixels: 0`.
- `frontend/tests/cross-plan-deltas.test.ts:87`, `:96`, `:221`, `:306` — documentation assertions that the plans still say "community mosaic shading". They read the plan files, so the plan text moves in the same change.

**8.3 How the data arrives.** `frontend/src/market/boundaries.ts` is a new adapter in the shape of `frontend/src/listings/seller.ts` and `frontend/src/admin/listings.ts`: one `fetch` against `/api/markets/{cbsa}/boundaries`, `credentials: 'same-origin'`, `AbortSignal.timeout`, a rejection arm on every path. It is passed into the app as a **`market` adapter prop**, which is the seam A16 and A17 already established — `this.props.listings` and `this.props.adminListings` are app-only props the reference never receives. The design's own script then branches on adapter presence, not on data (A16.1's exact shape, A-SL23 (2)): with the adapter present the map draws the polygons the API answered **or none at all**, whatever it answered, and never the design's fixture; with no adapter — the reference, and the Claude Design preview — the design's fixture path is untouched.

The fetch hangs off `frontend/src/main.ts:41-44`'s existing `Promise.all`, as a third arm with the same `.catch(() => null)` as its neighbours, and is reinstalled in the `makeAuthAdapter(...)` call at `:49-58` for the reason its comment already gives: an interactive sign-in re-reads the catalogue, and anything not reinstalled there is stale afterwards.

**8.4 The legend reads `/api/layers`.** D-C35: "it makes the legend the first thing in the product to read `/api/layers`." Nothing in the frontend has ever called it (§2.5). Scope here is deliberately one line: `md.active` gains a **geography line** — "ZIP Code Tabulation Area", "Place (city/town)", "County" — taken from the layer's new `shading.label` (D-NS15) when the adapter is present, and from the design's own `LAYER_META` when it is not. The legend's existing `sourceLine` and `updatedLine` keep coming from `LAYER_META` and are **not** switched to the API's `source_label`/`vintage` in this release: that swap is the four design-vs-spec copy conflicts A-C1 (11) already ruled on, and the plan's own Task B6 note records that updating the rendered template is "a separate, John-ruled task with its own screenshots". Doing it here would move copy John has not seen in this context.

The legend also gains the no-data row (D-NS16), and Q1 in §14 is whether that row's treatment is right.

**8.5 The hover tip** keeps the `rf-tip` sticky tooltip mechanism exactly — `sticky: true`, `className: 'rf-tip'`, the skin at `frontend/src/styles/global.css:53-54` — and changes what it contains. Per polygon: the geography's own name (`geo_area.name`, e.g. "ZCTA5 78704"), the layer's title, the formatted value through the design's own `fmtMetric`, and then the honesty line — the margin of error and, where it applies, the band caveat or the suppression reason from the table in §6, followed by the source note. Clicking a polygon keeps calling `onArea` with the geography's name, which is `logic.js:708`'s `selectArea` unchanged.

---

## 9. The design amendment — family **A24**

This is the part that makes or breaks the estimate, and it is the reason the backend is the smaller half of this spec.

**9.1 Why it cannot be skipped.** The visual baselines are generated **from the reference** in the same run (`npm run test:visual:baselines`, the `reference` Playwright project) and compared at `maxDiffPixels: 0` beside `threshold: 0.1`. The reference is the approved design bundle served by `frontend/tests/reference-server.mjs`, and it draws the mosaic itself — `Practice Match V3.dc.html:438` and `:1479` are two `<x-import component="MarketMapV3" from="./MarketMapV3.jsx" …>` elements, and `MarketMapV3.jsx` is where `mosaicCells` lives. If the app draws polygons and the reference draws a grid, every Browse state fails and no tolerance can be relaxed to make it pass. **The change must reach the design.**

**9.2 Two files must be amended, and the engine only covers one today.** `frontend/tests/design-amendments.ts` exports exactly one pristine/amended pair — `PRISTINE = Practice Match V3.rev2.dc.html`, `AMENDED = Practice Match V3.dc.html` — and `applyAmendments(html, list)` applies `{find, replace, count}` to that one string. `MarketMapV3.jsx` has **no** pristine twin: `frontend/tests/reference-bundle.test.ts:25` asserts only that the file exists, never that its bytes are anything in particular, and the file has not been touched since the bundle landed.

So the engine is extended, minimally and in its own idiom:

- `Amendment` gains an optional `file?: 'dc' | 'jsx'`, defaulting to `'dc'`, so all 151 existing entries are unchanged.
- `design-amendments.ts` exports a second pair: `PRISTINE_JSX = MarketMapV3.rev2.jsx` (a byte copy of today's file, frozen and never edited) and `AMENDED_JSX = MarketMapV3.jsx`.
- `frontend/scripts/apply-amendments.ts` (`npm run gen:design`) writes both outputs, partitioning the list by `file`.
- `frontend/tests/design-amendments.test.ts` proves **both** equalities — pristine + amendments == amended, byte for byte, per file — and keeps pinning `LOCAL_AMENDMENTS.md`'s row set both ways (count and ids).
- `frontend/tests/reference-bundle.test.ts:25`'s required-file list gains `MarketMapV3.rev2.jsx`.

This is a change to the amendment machinery itself and is called out as such in §14, Q3: it is the first amendment in the programme's history to touch a bundle file other than the `.dc.html`, and the alternative — editing `MarketMapV3.jsx` by hand — is exactly the failure mode spec D15 was written to remove.

**9.3 The amendment's own contents, by family member.** The next free family is **A24**: `LOCAL_AMENDMENTS.md` carries A1–A19, A21, A22 and A23 today; A20 is reserved by the image-identifiability plan, which is in flight, and **A23 was taken on 2026-09-10 by the Market data card collapse fix (Task MD1)**, which merged to `main` while this spec was being written. As that plan's own instruction puts it, "the ledger, not this document, is the authority" — the implementer re-derives the next free id from `LOCAL_AMENDMENTS.md` before writing a line.

| Member | File | What changes |
|---|---|---|
| A24.1 | `.dc.html` script | The design's own boundary fixture, added to the state literal as `areas` — a `FeatureCollection` per fill layer, real `geo_area` shapes for the design's own Austin metro. §9.4. |
| A24.2 | `.dc.html` script | `marketVals()` gains `areas`, in A16.1's exact ternary shape: `this.props.market ? (s.mdAreas || EMPTY) : s.areas`, each feature coloured by the design's own `bucket()` and labelled by `fmtMetric()`, so the fill and the legend cannot disagree. |
| A24.3 | `.dc.html` script | The no-data class: one entry beside the ramp, `#e6e6e6` at the same `fillOpacity`, used when a feature's `value` is null or `suppressed`. |
| A24.4 | `.dc.html` script | `md.active` gains the geography line (§8.4) and the legend gains its no-data row. |
| A24.5 | `.dc.html` template | Both `<x-import component="MarketMapV3">` elements (V3:438, V3:1479) gain `areas="{{ md.areas }}"`. `frontend/scripts/convert-dc.mjs` maps `MarketMapV3 → MarketMapView` generically, so `:areas="v.md?.areas"` falls out with no converter change. |
| A24.6 | `.dc.html` template | The snapshot strip's footnote (`App.vue:802`, inside `v.md?.stripOpen`) today reads "Community areas on the map are approximate — production draws Census ZCTA boundaries." That sentence becomes false the moment this ships, and a false disclaimer on a data product is worse than none. Replaced with the geography and vintage the map is actually drawing. Exact wording is Q2 in §14. |
| A24.7 | `MarketMapV3.jsx` | `mosaicCells` and the bbox helper are deleted (the bundle's own dead-code rule, spec D8/D12, as A2.3–A2.5 and A13.6–A13.7 applied it), and the area effect draws `props.areas` through `L.geoJSON` on the same shared canvas renderer. |
| A24.8 | `MarketMapV3.jsx` | The header's GEOMETRY NOTE — the paragraph quoted in §1 — is replaced by what the file now does. Leaving it would leave the reference asserting in its own comments that it approximates. |

**9.4 How the reference is handed the same polygons — the established idiom, named.** `frontend/tests/design-seller-listings.mjs` is the pattern, and its own comment states the rule: the fixture is "**DERIVED** from `logic.js`'s own array rather than hand-copied, exactly as `design-listings.mjs` is derived from `P`, so it can never drift from the design", and it reaches it through the exported class's own state — `new Component({}).state.sellerListings` — rather than through a new module export.

Applied here:

- A24.1 puts the fixture in the **design's state literal**, as `state.areas`, beside `sellerListings`, `requests` and `me`. That is deliberate: it makes the fixture reachable as `new Component({}).state.areas` and therefore requires **no change to `logic.js`'s trailing export**, which `frontend/tests/app-generated.test.ts` pins as a hard-coded `FOOTER` string and which is the subject of the plan's still-open D-C14. This spec does not touch that question.
- `frontend/tests/design-boundaries.mjs` (new) reads that fixture and emits it in the endpoint's own shape — `designBoundariesBody(layer)` — exactly as `design-seller-listings.mjs`'s `designSellerPageBody()` does.
- `frontend/tests/harness.ts`'s `prepare()` gains one `page.route` for `/api/markets/*/boundaries*`, answering from that module, registered beside the `collectionStubUrls()` block and **disarmed on a remote target** for the reason recorded there: with `PW_APP_URL` set, the real seeded API answers, and stubbing it would hide the very thing the QA parity run exists to check.

So both targets draw byte-identically the same polygons, from one source, with no `?props=` prop and no ninth prototype prop. The reference draws them because the design's fixture is what it has; the app draws them because the harness answered its adapter with the design's fixture.

**The fixture's own geometry** is generated once, by a committed script (`scripts/export_design_boundaries.py`) reading `geo_area` for the design's own Austin metro at the three levels, and pasted into A24.1 as a literal. Two constraints on it, both enforced by test: it is simplified at **0.005°** (ten times coarser than the production write-time tolerance Census spec §2b recommends) and the whole fixture is **≤ 120 KB**, because it is embedded in a design file that is 306 KB today and is string-searched once per amendment by `applyAmendments`. A coarse fixture is correct and not a compromise: it is a fixture, in the same class as `design-listings.mjs`'s `name: null` and `photos: []` — "a value the real endpoint never sends, carried so that the DESIGN's own words stand in the oracle". Pixels only ever compare the reference against an app fed the same fixture; production geometry is proved by pytest, not by pixels.

**9.5 Which approved states re-base — thirteen, and the invariant.** A state re-bases if and only if it mounts a map, and `MarketMapView` is mounted in exactly two places: `App.vue:367` (the desktop Browse column) and `App.vue:1404` (the phone frame's map tab, `v.mob?.isMap`).

| Re-basing | Why |
|---|---|
| `browse`, `browse-layer-menu`, `browse-compare-open`, `browse-legend-collapsed`, `browse-layers-open`, `browse-market-panel`, `browse-metro-menu`, `header-give-menu`, `browse-panel-lightbox`, `header-1100`, `header-1000` | the desktop Browse map (11) |
| `mobile-map`, `mobile-sheet` | the phone frame's map (2) |

`interest-modal`, `detail-lightbox` and `detail-lightbox-next` pass **through** Browse on their way but capture the detail screen, where the map is not mounted; they must not move. `mobile-detail` calls `waitMap` on its way to the detail screen for the same reason and must not move either — which makes it the sharpest single check in the set, because it is both frozen and map-adjacent.

**The invariant, stated as the gate:** `frontend/tests/baseline-manifest.json`'s **thirteen frozen hashes must not move** — `mobile-list`, `mobile-detail`, `detail`, `requests`, `seller-dash`, the four `wizard-*`, the four `admin-*`. Not one of them mounts a map. **A moved hash means the change leaked outside Browse**, and the implementer stops with NEEDS_CONTEXT rather than re-pinning — the posture A22 took for `wizard-step-1` and A19 took when it checked the manifest after A18's one-row re-pin. The only two mechanisms that have ever legitimately moved a frozen hash are a ruled removal from every screen (A6's launch removal) and a ruled change to the shared header (A14's Give button). Nothing here is either.

---

## 10. Tests and gates

Test-first, no exceptions (standing rule).

**Backend — 100 % lines and branches, `-W error`, as CI runs it.**
- `tests/test_geo_metric_schema.py`: `064`'s table, its primary key, its index, and the `geo_metric_license_gate` trigger — including the negative case, that an insert naming an `unresolved` or `blocked` dataset raises, and that a missing registry row raises too (the `IS DISTINCT FROM` NULL arm).
- `tests/census/test_geo_metric.py`: the three metrics at their three levels; the `market_state` scoping; the per-triple delete-and-rewrite; idempotency across two runs; a failed triple leaving the prior rows intact; and `geo_metric._suppression is materialize._suppression`.
- `tests/census/test_acs_zcta.py`: `GEOGRAPHIES()` carries `860`, `geoid()` builds a ZCTA id from the API's own column name, and the `--levels` filter loads that level alone while recording an `ingest_run`.
- `tests/api/test_boundaries.py`: the route's guard resolved by identity; each of the six refusals in §5 asserted as an `{"error": {...}}` body, never `{"detail": ...}`; the bbox and feature caps at and either side of their thresholds; a `blocked` dataset answering `200` with empty features rather than `403`; the cache key including `gate.version` and a `gate.invalidate()` making the previous body unreachable; the gzip branch and the identity branch both; the two vintage-divergence cases of §7; the band-stop pin against the design file; and the two suppression-parity assertions of D-NS18.
- `tests/api/test_contract_doc.py` needs no edit and must stay green, which it will only if `docs/integrations/market-data-api.md` gains the new route.

**Frontend — 100 %, vitest.**
- `frontend/src/market/boundaries.test.ts` for the adapter (every method, every failure path).
- `frontend/src/map/engines/leaflet.test.ts` extended for `geoJson`: the shared canvas renderer is passed, the layer joins the named group, the tooltip and click handlers bind per feature, and `Handle.remove()` removes it.
- `frontend/src/components/MarketMapView.test.ts` rewritten off `cellCount` and onto feature counts, keeping `drawOrder`/`roleOf`'s purpose (the overlay is re-added before the pins on every trigger) and re-expressing `roleOf`'s `l.bounds !== undefined` test for a GeoJSON layer.
- `frontend/src/map/boundary.test.ts` with `geoJSON` in its alternation.
- `frontend/tests/design-amendments.test.ts` proving A24 applies cleanly **on both files**, and `LOCAL_AMENDMENTS.md` carrying one row per amendment with the count and ids pinned both ways.
- `frontend/tests/app-generated.test.ts` unchanged and green: `logic.js` still byte-identical to the amended design's script block — header, asset rewrite, trailing export and trailing-newline normalisation aside — and `app.setup.js` still declaring every prop the design declares.

**Oracles.** `npm run test:visual:baselines` regenerates from the amended V3, then `npm run test:e2e` (visual + DOM oracle + smoke) at `maxDiffPixels: 0`. Thirteen states re-base under the ruling; `baseline-manifest.json`'s thirteen hashes do not move. `visual.spec.ts`'s renamed `expectBoundaryShading` still runs on `browse`, after the comparison. A new `frontend/tests/boundary-flows.spec.ts` — value assertions, not pixels, in `listing-flows.spec.ts`'s shape — drives the **real** API with no stub: sign in, open Browse, assert the polygon layer carries more than one distinct fill class, switch to `growth` and assert the geography line reads "Place (city/town)", hover a polygon and assert the tip carries a margin of error, and flip `acs5` to `unresolved` as an admin and assert the income layer empties inside 60 s.

**The gate before production is CLAUDE.md's four, all of them**, and the hand-back is a forwardable summary plus screenshots of the live screens plus the one-line engineer's note.

---

## 11. Risks

Each with the measurement that confirms or kills it. The order is by what would cost most to discover late.

**R1 — the zero-pixel gate is the largest single line item, and the amendment engine has to grow to let it pass.** Roughly ten to thirteen approved Browse states carry a map (§9.5, thirteen exactly), the reference draws the fill itself, and the fill lives in a bundle file the amendment engine has never touched. *Confirmed or killed by:* running `npm run gen:design && npm run gen:app && npm run test:visual:baselines && npm run test:e2e` on a branch carrying only A24.7's `MarketMapV3.jsx` edit and the two-file engine change, before any backend work. If `design-amendments.test.ts` cannot prove pristine + amendments == amended for the `.jsx`, the shape in §9.2 is wrong and the whole estimate moves. *Kill condition:* the engine change is rejected on review — in which case the fallback is a `.dc.html`-only design in which `MarketMapV3.jsx` is replaced wholesale by a new sibling and the `x-import from=` attribute is repointed, which is one amendment to the `.dc.html` and no engine change, at the cost of shipping two map components in the bundle.

**R2 — the two suppression paths disagree.** D-C36 names it: "$72,400" in the docked panel over a grey polygon. It is not hypothetical — `community_rows` and the new endpoint read different tables, written by different jobs, at different geographies. *Confirmed or killed by:* D-NS18's parity test, which must exist before the endpoint does. *Residual, stated:* the parity case runs at the place level (§6's caveat); the ZCTA path is covered only by the shared-function assertion, so a divergence introduced in `geo_metric.py`'s **inputs** rather than in its suppression call would pass both. The mitigation is that the income row's `(value, moe)` pair comes straight from `acs_measure` with no arithmetic between the table and `_suppression`.

**R3 — the licence gate silently does not apply to the map.** The map is the one surface with no per-figure attribution line, so a layer that should have vanished can keep shading for a long time without anybody noticing. Three independent mechanisms have to hold: the `geo_metric_license_gate` trigger on writes (D-NS3), the live `_cleared`/`_extra_cleared` re-filter on every cache miss, and `market:gate:v` in the cache key (D-NS13). *Confirmed or killed by:* the QA click-through step the contract document already specifies for the other endpoints — flip `acs5` to `unresolved` and confirm the income layer empties within 60 s and returns when it is cleared again — plus the `gate.invalidate()` unit case. *The specific hole to look for:* `growth` is stamped `source_dataset = 'acs5'` but folds `acs5_prior`, and `_extra_cleared` is the shared check that covers exactly that; a `geo_metric` read path that calls `_cleared` alone reproduces the licence hole A-C23 (1) closed for `vets_per_10k_households`.

**R4 — the boundary and value vintages diverge.** `tiger_cb` advances annually in the autumn and `acs5` in the winter, on different calendars and in different string shapes. A flip on one side alone silently shrinks the map. *Confirmed or killed by:* the `values_without_geometry` counter (§7), logged on every cache miss with the level and vintage, plus the two vintage-divergence test cases. *The measurement that would show it in production:* a non-zero counter on a metro that has previously reported zero.

**R5 — ZCTA ACS values do not exist and the load is larger than the sub-project has issued before.** §2.3 and D-NS4. A national ZCTA query returns roughly 33,700 rows per variable in one page. *Confirmed or killed by:* running the ZCTA load against QA and reading the `ingest_run` row's `rows_written` and `request_count`, before anything downstream is built. *Kill condition:* `client.py`'s size cap refuses the page, or the ACS API does not publish `B19013` at ZCTA for the active vintage — in which case D-C34's ZCTA ruling has to go back to John with the tract alternative and the aggregation alternative D-NS4 rejects, rather than being quietly satisfied with a weighted average.

**R6 — an unbounded request costs 9.2 MB.** Measured: a whole-Texas bounding box returns 6,884 tracts and 9.2 MB, and there is no bound today anywhere in `app/`. *Confirmed or killed by:* the cap tests at and either side of `MAX_BBOX_DEG` and `MAX_FEATURES`. *Residual:* the caps are chosen against geography, not against a load test; a metro whose ZCTA count approaches 4,000 would be refused rather than served slowly, which is the intended failure but should be checked against the six states' actual counts before shipping.

**R7 — simplification creeps back onto the request path.** It is the obvious fix the first time a payload looks large, and it was measured at five to eight times the cost of the query. *Confirmed or killed by:* a grep gate in the endpoint test asserting `ST_Simplify` appears in no SQL string in `app/api/market.py`, with the measurement in the comment above it.

**R8 — the harness stub and the reference fixture drift apart.** If `design-boundaries.mjs` is ever hand-copied rather than derived, the two targets diverge and the pixel gate reports it as a regression in code that did not change. *Confirmed or killed by:* the module importing the fixture through `new Component({}).state.areas`, and a vitest case asserting the emitted body's feature ids equal the fixture's — the check `design-listings.mjs` earns through `load.test.ts`'s round-trip proof on all twenty-one fixtures.

---

## 12. Out of scope

D-C34–D-C37's own "what is deliberately NOT in the first slice", enumerated so nobody reads this spec wider than it is:

- **Tract polygons and the geography toggle.** D-C34 defers the tract layer and gates it on a measurement, not a date: the share of tract polygons whose margin of error spans more than one legend band (§6). The geography selector this implies — in the API, in the legend and in the layer menu — does not exist in the approved design and will be a ruled amendment when the toggle is built.
- **Vector tiles, the CDN path and a vector-tile client.** D-C37 records the tile pipeline as the scaling answer, measured and real (412 tiles and 591 KiB for the whole Austin metro at z9–z12 per metric per vintage; a z11 viewport at 34 KB against 424 KB of GeoJSON), with its own trigger: national coverage, or a metro whose polygon count makes a viewport response exceed 500 KB gzipped.
- **Any change to the three graduated-symbol layers** — `pets`, `households`, `competition` stay symbols at the listing point (D-C35).
- **Tract-level growth**, which needs the 2010→2020 tract crosswalk and is its own deferred Phase C row (red-team C2, D12).
- **The Esri-vs-CARTO basemap decision.** One open decision record, owned by John and the VIN Foundation; boundaries do not force it and this spec does not touch it.
- **The Satellite tab.**
- **National coverage** beyond the four markets and the six `market_state` states.
- **Any exposure of `opportunity_score`**, which stays computed, stored and withheld until the VIN Foundation signs off on its weights.

And four more this spec's own boundaries require:

- **`market_metric` and the docked panel.** Not edited. `materialize.py` gains a second importer of `_suppression` and nothing else.
- **The legend's source and vintage lines.** They stay `LAYER_META`'s; swapping them for the API's strings is A-C1 (11)'s separate, John-ruled task with its own screenshots (§8.4).
- **A global `GZipMiddleware`.** Rejected in D-NS14 with its reason.
- **`logic.js`'s trailing export and D-C14.** The fixture goes in the design's state literal precisely so this spec does not have to answer that question (§9.4).

---

## 13. Decisions

| Id | Decision |
|---|---|
| D-NS1 | One new table, `geo_metric`, per (geography, metric, vintage). `market_metric`'s sibling, not its replacement; neither writer touches the other's table. |
| D-NS2 | `migrations/064_geo_metric.sql` — the next free number in D14's SP3-B `060`+ range, not `091`; the ledger runner applies it once regardless of sort order. |
| D-NS3 | `geo_metric_license_gate`, the twin of `market_metric_license_gate`, `BEFORE INSERT OR UPDATE … FOR EACH ROW`, message naming only the dataset key (062's own correction). |
| D-NS4 | `acs5` gains summary level `860`; ZCTA income is **loaded**, never aggregated from tracts, because an aggregated median has no combined margin of error and could never be suppression-tested. |
| D-NS5 | One new module, `app/census/geo_metric.py`, one public entry point, three metrics at three levels — `income`/`860`, `growth`/`160`, `econ`/`050`. |
| D-NS6 | It imports `materialize._suppression` and calls `metrics.py`; it reimplements neither, and a test asserts the function identity. |
| D-NS7 | Writes are per (level, metric, vintage), delete-then-upsert in one transaction, idempotent, prior vintage survives a failure. |
| D-NS8 | Scope is the six `market_state` states and the three ruled levels. |
| D-NS9 | Nightly beat entry `geo-metric-nightly` at 03:30 UTC, half an hour after `materialize-nightly`; never on the request path. |
| D-NS10 | One route, `GET /api/markets/{cbsa}/boundaries?layer=&bbox=`, on `market.router`, guarded by the existing `REQUIRE_MARKET_READ` module constant, mounted in `site_mode == "app"` only. |
| D-NS11 | `ST_AsGeoJSON(ST_Transform(geom, 4326), 6)`; the bbox is transformed into 4269 so the GiST index is usable; `ST_SimplifyPreserveTopology` is not on the request path. |
| D-NS12 | Bounds: `MAX_BBOX_DEG = 4.0`, `MAX_FEATURES = 4000`, `MAX_BODY_BYTES = 2_000_000`; every breach is a `422` in `_error`'s envelope. |
| D-NS13 | Cache key `boundaries:{cbsa}:{layer}:{geo_vintage}:{value_vintage}:g{gate_version}`, TTL 86400 s, plus a live `_cleared`/`_extra_cleared` re-filter on every miss. |
| D-NS14 | Gzip in the handler, compressed bytes cached; no global `GZipMiddleware`. |
| D-NS15 | `/api/layers` gains a `shading` member per fill layer, separate from `geo_level`; the contract document gains the route or the backend gate fails. |
| D-NS16 | A polygon with no value is drawn in a no-data class (`#e6e6e6`, the design's own `--border-subtle`), never omitted; four reasons, each named in the tip. |
| D-NS17 | `_suppression` applies to `income` only; `growth` and `econ` carry no published margin and say so in the tip rather than being greyed. Band ambiguity is computed server-side from `app/census/bands.py`, pinned two-way against the design's own stops. |
| D-NS18 | A test asserts the endpoint and `serve.community_rows` return the same suppression verdict for the same geography, metric and vintage, and that both paths call one function object. |
| — | Frontend wiring is amendment family **A24** plus `gen:design`/`gen:app`, with an app-only `market` adapter prop; the design's own fixture stays the oracle's data, derived through `design-boundaries.mjs`, so the thirteen frozen hashes do not move. |

---

## 14. Open questions — ALL THREE ANSWERED, 2026-09-10

**None remain.** John ruled the two that were his on the evening of 2026-09-10; the controller ruled the third. The three paragraphs that follow record what was asked and what was decided, because a spec that quietly absorbs an answer loses the reasoning with it.

**1. The no-data treatment — RULED (John): neutral grey, WITH a legend row.** A polygon with no usable figure is filled at the design's own `#e6e6e6` at the same `fillOpacity: 0.5` every other class uses, and the legend gains one row reading "No data". The polygon is always drawn and never omitted: a hole in the map reads as a boundary, not as an absence. Hatching was offered and not taken — it is the Census spec §2b's own alternative, but it would be new style vocabulary on a screen whose pixels are otherwise frozen, and the shared canvas renderer draws flat fills. Note the boundary this preserves: D-C36 still forbids greying a figure that WAS measured but whose margin is wide; grey means unmeasured, and only that.

**2. The snapshot strip's footnote (A24.6) — RULED (John): name the boundary and its vintage.** The sentence becomes, verbatim: *"Community areas are Census ZIP Code Tabulation Areas (2023 boundaries); figures describe the area, not the practice."* It replaces "Community areas on the map are approximate — production draws Census ZCTA boundaries", which becomes false the day this ships. The vintage is in the copy deliberately, so a reader knows how current the boundaries are; the cost is that the sentence needs an edit when `tiger_cb` advances, and §6's vintage handling is where that edit is triggered from. The two rejected alternatives — dropping the vintage, and naming the geography per layer — are recorded because the second is not wrong, only redundant: the legend already names each layer's geography under D-C35.

**3. Extending the amendment engine to a second bundle file (§9.2) — RULED (controller): extend it.** This is the first amendment that has to reach `MarketMapV3.jsx`, and the engine has only ever known the `.dc.html`. Add `file?: 'dc' | 'jsx'` to `Amendment`, add a frozen pristine twin `MarketMapV3.rev2.jsx`, and prove both files the way the one file is proved today — pristine plus amendments equals the amended file, byte for byte. The alternative was hand-editing an approved bundle file, which is the exact failure spec D15 exists to remove, and no argument for it survives that sentence. The recorded fallback, if the engine change is ever refused, stays as written: a new sibling component with the `x-import from=` attribute repointed by a `.dc.html` amendment.

---

## 14b. The questions as they were put (superseded, kept for the reasoning)

Three remained after the four rulings. None of them is manufactured — each is a place where the four rulings settle the behaviour and not the appearance, and each has a default that applies until John says otherwise.

1. **The no-data class's treatment, and whether the legend gains a row for it.** D-C36 rules that a *measured* figure is never greyed; it does not say how an *unmeasured* one looks, and the approved design has never drawn a no-data swatch. Census spec §2b says "hatched or neutral grey". *Default:* neutral grey at the design's own `#e6e6e6`, at the same `fillOpacity: 0.5` every other class uses, with one extra legend row labelled "No data". Hatching is not proposed: the shared canvas renderer draws flat fills, and a pattern fill would be new style vocabulary on a screen whose pixels are otherwise frozen.

2. **The wording of the snapshot strip's footnote** (A24.6). The present sentence — "Community areas on the map are approximate — production draws Census ZCTA boundaries" — becomes false on the day this ships, so it must change; what it should say is a copy decision on an approved screen. *Default:* "Community areas are Census ZIP Code Tabulation Areas (2023 boundaries); figures describe the area, not the practice."

3. **Extending the amendment engine to a second bundle file** (§9.2). This is the first amendment that has to reach `MarketMapV3.jsx`, and the engine has only ever known the `.dc.html`. *Default:* extend it — add `file?: 'dc' | 'jsx'` and a second frozen pristine twin — because the alternative is hand-editing an approved bundle file, which is the exact failure spec D15 removed. The recorded alternative, if the engine change is refused, is a new sibling component file with the `x-import from=` attribute repointed by a `.dc.html` amendment.

---

## 15. Estimate

One release, one spec → plan → implementer → review rounds → four-part gate → QA deploy → click-through loop. The four slices below are the *work*, not four releases; days are working days for one implementer plus the review loop.

| Slice | Contents | Days |
|---|---|---|
| **(a) The amendment engine and the reference** | The two-file amendment engine (§9.2), `MarketMapV3.rev2.jsx`, A24.7/A24.8, and the first re-base of the thirteen map states with the mosaic swapped for a hard-coded fixture. Run first, because R1 is the risk that would move every other number. | **3–4** |
| **(b) Values at their own geographies** | The ZCTA ACS load (D-NS4) and its QA run; `064_geo_metric.sql` with its trigger; `app/census/geo_metric.py`; the beat entry; `bands.py` and its two-way pin; schema and writer tests at 100 % branches. | **4–5** |
| **(c) The read path** | The route, its six refusals, the caps, the gzip branch, the cache key and the live re-filter; `/api/layers`'s `shading` member; the contract document; the suppression-parity test; `tests/api/test_boundaries.py`. | **3–4** |
| **(d) The map, the legend and the tip** | The `geoJson` engine primitive and its stub, `boundary.test.ts`'s regex, `MarketMapView` and its test suite off `cellCount`, `mosaic.js`/`mosaic.test.ts` deleted, the `market` adapter and its boot wiring, A24.1–A24.6, `design-boundaries.mjs` and the harness route, `expectBoundaryShading`, `boundary-flows.spec.ts`, the full gate, QA deploy and click-through. | **5–7** |

**Total 15–20 working days**, shipped as one release. Slice (a) leads deliberately: it is the only slice that can invalidate the others, it needs no backend at all, and it converts R1 from an estimate into a measurement in the first three days.

---

**Controller note (2026-09-10, before John's review).** Three defaults proposed above (§14) and one correction recorded: D-C35 as put to John names place as "150/160"; summary level **150 is block group and 160 is place** (`migrations/018_census_geo.sql:4`, and the Census spec's own §6 table), and `app/census/acs.py:59` loads `Geo("160", "place:*", …)`. Block group is loaded nowhere and appears in no Python or SQL in the tree. This spec draws `growth` at **160**, which is what the ruling means and what the data supports. One finding is material enough to flag before the plan is cut: **A-C33's "no new ingest is required to start" holds for geometry and not for values** — there are no ACS rows at ZCTA today, so D-C34's ruled geography needs the load in D-NS4 before anything downstream can be true. This spec awaits John's review before the plan is written (brainstorming gate).
