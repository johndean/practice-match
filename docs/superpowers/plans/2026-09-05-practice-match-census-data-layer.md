# Practice Match Market-Data Layer (Census) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved *Census & Market Data Source Specification v1.0* — the public-data layer that answers "what is the community around this practice like, and who else already serves it?" — as PostGIS tables, Celery ingest jobs, derived metrics with provenance, and read-only API endpoints that serve exactly the values the approved UI renders.

**Architecture:** Scheduled Celery tasks on the `worker` service call the Census Data API (ACS, CBP, QWI, BDS), the Census Geocoder and TIGER cartographic boundary files; every raw response is archived immutably in a Railway bucket; parsed rows land in long-format PostGIS tables keyed by `(geo_id, summary_level, vintage)`. A nightly materialisation joins each listing's drive-time catchment to tract data and writes one row per `(listing, band, metric, vintage)` into `market_metric` — the **only** table the API reads for market figures. FastAPI serves the market panel and the per-market community layer from `market_metric` (Redis-cached, 24 h) and never calls a Census endpoint on the request path. Licensing is a database gate: nothing from a dataset whose `license_status` is not `cleared` can be written or displayed.

**Tech Stack:** Python 3.12 · FastAPI · Celery 5 (beat on the worker) · PostgreSQL 16 + PostGIS 3.5 · SQLAlchemy 2 async (API reads) · psycopg2 (ingest writes) · httpx (sync client for tasks) · boto3 → Railway Buckets (S3-compatible) · pyshp + shapely (boundary files, no GDAL) · redis-py · pytest + moto (S3 mock) + httpx `MockTransport`.

**Spec:** `docs/design-reference/design_handoff_practice_match_v2/Census Data Source Specification.dc.html` (§ references below are to it). Foundation spec: `docs/superpowers/specs/2026-09-05-practice-match-foundation-design.md`.

**Depends on:** Sub-project 1 complete (`worker` service, PostGIS, Redis, `scripts/migrate.py`, `app/tasks/celery_app.py`). Phase B additionally depends on Sub-project 2 providing `listing(id uuid PRIMARY KEY, status text, address fields)`; Phase A has no listing dependency and can start immediately.

## Global Constraints (from the spec — exact values)

- **Pinned vintages, in `dataset_registry`:** `acs5` = `2023/acs/acs5` (2019–2023) · `acs5_subject` = `2023/acs/acs5/subject` · `acs5_prior` = `2018/acs/acs5` (2014–2018, static) · `cbp` = `2022/cbp` (NAICS parameter `NAICS2017`) · `qwi` = `timeseries/qwi/sa` · `bds` = `timeseries/bds` · `geocoder` = `geocoding.geo.census.gov`, benchmark `Public_AR_Current`, vintage `Current_Current` · `tiger_cb` = `TIGER2023/cb_2023_*`. No request is made without a vintage; vintages advance only by migration + `active_vintage` flip.
- **Pre-aggregate, never call at request time.** The request path reads our tables only. A page that finds no materialised metric renders the layer's empty state and enqueues a backfill.
- **Derived is labelled derived:** `is_derived = true` + `formula_version`; UI copy carries "derived estimate" / "approximate".
- **Licensing gates production:** rows with `license_status` `unresolved` or `blocked` are never ingested, cached or displayed. Enforced in the database (trigger on `market_metric`) and in the API (layer hidden within 60 s of a status change).
- **Degrade, never block:** a failed layer hides itself and logs; listings, search and messaging keep working.
- **HTTP rules (§3):** connect timeout 15 s, read timeout 45 s; 3 retries with exponential backoff + jitter on **5xx and 429 only**, never on other 4xx; `User-Agent: PracticeMatch/<version> (VIN Foundation; <contact email>)`; at most 4 concurrent requests per dataset; a missing `CENSUS_API_KEY` is a **hard startup failure of the ingest worker** (never a silent unkeyed fallback). On 429: halve concurrency and resume from the last completed geography page.
- **Sentinels** `-666666666`, `-999999999`, `null` → SQL `NULL` at parse time.
- **Variable map (§4)** is the only variable list requested; every `_E` requested with its `_M` for population, households, median income at minimum. A response missing an expected variable aborts the load (no partial vintage ever goes active).
- **NAICS (§5):** `541940` competition count (CBP, 6-digit); `5419` for QWI; `54` sector denominator (BDS); `812910`, `459910` optional adjacent-demand layers. The CBP NAICS parameter name comes from `dataset_registry.naics_param`, never hard-coded.
- **Geography (§6):** summary levels `140` tract (11-digit), `150` block group (off by default), `160` place (7), `860` ZCTA (5), `050` county (5), `310` CBSA (5), `040` state (2), plus `010` nation (`us:1`) for benchmarks. Resolution order: address → geocoder (tract, county, place) → tract ACS; else ZCTA centroid → containing tract; else place; else county; `geo_precision` recorded and never silently promoted.
- **Derived formulas (§8), `formula_version = 'v1'`:** `pet_households_est = households × 0.57` (documented national placeholder) · `population_growth_pct = (pop_2023 − pop_2018) / pop_2018 × 100` · `vets_per_10k_households = establishments / (households / 10000)` · `income_index_vs_us = (local_median − us_median) / us_median × 100` · `revenue_per_establishment = payroll_k × 1000 / establishments` (labelled payroll-per-establishment) · `drive_catchment` V1 = straight-line buffers 8 km (`drive_10`) and 16 km (`drive_20`), method `euclidean_buffer_v1` · `opportunity_score = 40·min(income/140000, 1) + 35·min(growth/40, 1) + 25·max(0, 1 − vets_per_10k/3)`, clamped 0–100, rounded, always rendered with its three components, never in a price context.
- **Data quality (§14):** suppress any ACS value with CV `(moe / 1.645) / estimate > 0.30` → `suppressed = true, suppress_reason = 'high_moe'` (row kept). Summed counts: combined MOE `sqrt(Σ moe²)`, same CV test. Medians never sum: household-weighted average, flagged approximate. CBP noise flags stored verbatim; noise-flagged counts are estimates; suppress employment/payroll where Census suppressed. Every rendered figure shows dataset + vintage; two vintages never appear in one ratio.
- **Caching (§10):** raw API response → bucket key `raw/{dataset_key}/{vintage}/{sha256(url)}.json`, immutable · geocode result → `geocode_cache` keyed `sha256(normalized_address)`, 365 d · `market_metric` until vintage flip · panel payload → Redis `listing:{id}:market:v{n}` 24 h · basemap tiles never proxied.
- **Refresh (§9):** `acs_annual_load` yearly Dec, manual approval · `cbp_annual_load` yearly Apr, manual · `qwi_quarterly_load` scheduled quarterly, keeps 20 quarters · `geocode_on_write` per listing create/address edit · `metric_materialize` nightly + on new listing · `license_audit` quarterly.
- **Attribution (§12):** strings live in `dataset_registry.attribution_text` and are returned by the API; "Source: U.S. Census Bureau, [dataset], [vintage]" on every surface; never the Bureau's seal/logo. Basemap attribution is the map component's concern (Foundation spec §9 open item).
- **Schema (§13):** the DDL is applied verbatim as numbered migrations, in the order the spec gives (`ingest_run` → `dataset_registry` → FK back-fill → `geo_area` → measures → listing-dependent tables → `active_vintage`).
- **Competition geography (red-team C1):** community-level competition comes from **ZIP Code Business Patterns** (`zbp`, same Census program, public domain) aggregated over the ZCTAs a catchment/place intersects; county CBP remains the county benchmark. `vets_per_10k_households` always divides establishments and households measured over the **same** geography. The UI must say the count is a proxy for competitive density (spec §5).
- **Growth geography (red-team C2):** `population_growth_pct` is computed at **place** level (stable GEOIDs across the 2020 tract redefinition), county fallback; tract-level growth waits for the 2010→2020 tract crosswalk (Phase C).
- **Google Maps Platform content (audit 2026-09-05, D15–D17):** no Google Places content is stored, analysed or rendered in V1. Google Maps Platform Terms §3.2.3(a)(iii) forbid saving "business names, addresses, or user reviews"; §3.2.3(c)(iv) forbids using "latitude/longitude values from the Places API as an input for point-in-polygon analysis"; Service Specific Terms §14.2 forbid Places content "in conjunction with a non-Google map" (the approved design is Leaflet). Only `place_id` may be kept indefinitely (SST §3) and latitude/longitude for 30 days (SST §14.3). Places Aggregate API POI counts may be cached 30 days solely to compute non-substitutable "Customer Values" (SST §13.1–13.2). The 2017 export `Report_Hospital_Competitor_All_US_ZipCode_FULL.csv` is a blocked source: never copied into the repository, the bucket or the database.
- **Bands:** `market_metric.band ∈ {'place', 'drive_10', 'drive_20'}`. Community bubbles and the "community label" figures default to `place` (the approved design's numbers are city-level); the practice panel's drive-time context defaults to `drive_10`; every response names its band.
- **Access (red-team C4):** every market endpoint requires an approved member session (Sub-project 2's `require_member`) unless `MARKET_DATA_PUBLIC=true` (VIN Foundation decision, spec §15). Coordinates returned are the **place centroid** unless the seller disclosed the location (`listing.location_disclosed`), never the geocoded point otherwise.
- **Cache gate (red-team C5):** panel and community payloads are cached under a key that includes a global `market:gate:v` counter bumped on any licence decision, and metrics are re-filtered through the gate on read — a blocked layer disappears within 60 s even from cached payloads.
- **Secrets in errors (red-team C6):** the API key never appears in exceptions, logs or archive keys (`CensusClient.redact(url)`).
- **Migration numbering:** Sub-project 3 Phase A uses `002`–`009`; Sub-project 2 owns `010`–`059`; Sub-project 3 Phase B (listing-dependent) uses `060`+.
- Every commit: conventional message, `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, pushed to `origin` and `production`. Work on `feat/census-data-layer` in a worktree.

## Decisions recorded in this plan (confirm on review)

| # | Decision | Why |
|---|---|---|
| D1 | **Object store = Railway Buckets** (S3-compatible; `railway bucket create practice-match-data`), one bucket per environment; boto3 with `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` on `worker` (and `api` for future tile reads). | Same vendor as everything else; credentials via `railway bucket credentials`; no GCS service-account plumbing. |
| D2 | **Boundary files parsed with pyshp + shapely**, geometry inserted as WKB via `ST_GeomFromWKB(…, 4269)`; no GDAL/`shp2pgsql` in the image. | Keeps the image small and pure-Python; cartographic boundary files are simple polygons. |
| D3 | **Choropleth vector tiles deferred to Phase C.** The approved design draws per-community bubbles (`dot()` at each listing's community with a bucketed value), not tract polygons; the tile pipeline in spec §7/§10 has no consumer yet. | YAGNI; flagged for the VIN Foundation with the basemap licence question. |
| D4 | **Markets loaded in V1:** the four design markets — Austin–Round Rock–San Marcos `12420` (TX `48`), Sacramento–Roseville–Folsom `40900` (CA `06`), Orlando–Kissimmee–Sanford `36740` (FL `12`), Atlanta–Sandy Springs–Roswell `12060` (GA `13`) — tract/place/county/CBSA data for those four **states** in full, plus the national row. New listings outside them auto-extend `market_state` and trigger a state load. | Matches the fixture markets; whole-state loads are ~24 k tracts total, well under limits. |
| D5 | **Ingest writes use psycopg2 (sync) inside Celery tasks; API reads use SQLAlchemy async.** | Celery tasks are synchronous; one connection per task, executemany batches. |
| D6 | **API contract mirrors the fixture field names** the approved UI already reads (`pop`, `hh`, `income`, `growth`, `pets`, `econ`, `vets`) so Sub-project 2's "replace fixtures with API calls" is a field-for-field swap. | The handoff README: "Keep the field names — the UI reads them directly." |
| D7 | **National benchmark** `us_median` comes from the same `acs5` vintage at geography `us:1` (stored `geo_id='1'`, `summary_level='010'`), never a hard-coded constant (the prototype's `75149` is replaced). | §14: two vintages never in one ratio. |
| D8 | **Community location shown on the map** = the listing's place centroid; the geocoded point is returned only when `listing.location_disclosed` is true **and** the caller is an approved member. `geo_precision` is always returned. | Sellers control disclosure (design principle 2); an anonymized listing must not be locatable from the API (red-team C4). |
| D10 | **Three bands.** `place` (the listing's city/CDP), `drive_10` (8 km), `drive_20` (16 km). Community bubbles and community-label figures use `place` by default; the panel's drive-time tiles use `drive_10`; `?band=` selects. | The approved design's community numbers are city-level (Cedar Park 81,900 = the city); the spec's catchments answer the drive-time question. Both are real needs; the band is explicit (red-team C3). |
| D11 | **ZIP Code Business Patterns (`zbp`, `2022/zbp`, NAICS2017) is the community-level competition source**, aggregated over ZCTAs by area overlap; county CBP is the benchmark. Register it as a new cleared public-domain dataset (VIN Foundation to approve the addition to the spec's §2 table). | County CBP cannot render per-community competition and produced incoherent ratios (red-team C1). ZIPs ≈ ZCTAs; the approximation is labelled. |
| D12 | **Population growth at place level** (2014–2018 → 2019–2023 place rows), county fallback; tract growth deferred until the 2010→2020 tract relationship file is loaded. | 2010 and 2020 tract GEOIDs differ; joining prior-vintage tracts on 2020 GEOIDs is wrong (red-team C2). |
| D13 | **Market endpoints are member-gated** via SP2's `require_member`, with `MARKET_DATA_PUBLIC` as the only way to open them (default false). | Spec §15 leaves public teaser vs gated to the VIN Foundation; default closed. |
| D14 | **Migration ranges:** SP3-A `002`–`009`, SP2 `010`–`059`, SP3-B `060`+. | Phase B tables reference `listing(id)`, which SP2 creates; numbered ordering must guarantee it exists first. |
| D15 | **The 2017 Google Places export is not a source.** `Report_Hospital_Competitor_All_US_ZipCode_FULL.csv` (audited 2026-09-05 — appendix below) stays out of the repository, bucket and database. The only content Google's terms let us keep is its 10,166 `place_id` values, and even those are not loaded until a Google-based mechanism (D17) is approved. The registry's `practice_locations` row names the file as blocked. | A 16-day snapshot (24 May–8 Jun 2017) covering 8,320 of ~41,700 ZIPs, Austin absent, 29.7 % individual-practitioner duplicates, ≈ 5 % non-veterinary rows; and Google Maps Platform Terms §3.2.3(a)/(c)(iv) + SST §14.2 forbid storing it, analysing it or drawing it on the Leaflet map. |
| D16 | **Competitor points (Phase C) come from a permissively licensed, provenance-documented POI dataset, ranked:** (1) **Overture Maps Places** (CDLA-Permissive-2.0; Foursquare-sourced rows Apache-2.0; monthly GeoParquet on S3/Azure; per-feature `sources[]` and `confidence`; taxonomy entry `veterinarian`), (2) **Foursquare OS Places** (Apache-2.0; also an Overture source), (3) **VIN's member practice directory** (VIN-owned; consent review). OpenStreetMap `amenity=veterinary` (ODbL share-alike) is a coverage cross-check only, pending counsel. Google Places points are lawful only on a Google map (SST §14.1–14.2), which the approved Leaflet design excludes — not pursued. All candidate rows start `unresolved`. | Spec §12 excludes practice-location lists for undocumented provenance; these publish provenance and licence per record. They are storable, renderable on Leaflet and refreshable monthly — the three properties every Google route lacks. |
| D17 | **Google's only role is a freshness signal through the Places Aggregate API** (Task C1, gated): `INSIGHT_COUNT` of `veterinary_care` places (Places type Table A) that are `OPERATIONAL`, per listing band; the count lives only in memory, is bucketed with the design thresholds into `level_live` (Low/Moderate/High) and compared with the ZBP level (`diverges`); those two values are the persisted "Customer Values" (SST §13.1). No count, ratio or place list is stored, returned or drawn. Registry row `google_places_aggregate` stays `unresolved` until VIN Foundation counsel accepts SST §13 and a Google Cloud billing account exists. | It is the one Google mechanism built for market counts whose terms permit derived metrics; Nearby/Text Search (20 results, no pagination, $32/1k) and Place Details refreshes return content we may not keep. V1 volume (4 markets × ~60 communities × 3 bands ≈ 720 requests/month) sits inside the 5,000 free requests; $10 per further 1,000. |

## API contract (consumed by Sub-project 2's frontend wiring)

All routes below except `/api/admin/*` use `Depends(require_member)` from Sub-project 2 (approved buyer/seller/admin session). `MARKET_DATA_PUBLIC=true` removes the dependency (VIN Foundation decision, spec §15). Until SP2 lands, the dependency is the A9 operator token.

```
GET /api/layers
→ [{ "key": "income",      "label": "Median Household Income",  "source_label": "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023",
     "dataset_key": "acs5", "vintage": "2019–2023", "geo_level": "place|catchment", "enabled": true, "is_derived": false, "caveat": null },
   { "key": "pets",        "label": "Pet Ownership (est.)",      "dataset_key": "acs5", "is_derived": true,  "caveat": "Derived estimate: households × 0.57 (national placeholder rate)." , … },
   { "key": "competition", "label": "Veterinary Competition",    "dataset_key": "zbp",  "vintage": "2022", "geo_level": "zcta",
     "caveat": "Establishment counts (NAICS 541940) include corporate-owned and specialty locations; a proxy for competitive density, not a count of independent practices." , … },
   { "key": "growth",      "label": "Population Growth",         "dataset_key": "acs5_prior", "vintage": "2014–2018 → 2019–2023", "geo_level": "place", … },
   { "key": "households",  … }, { "key": "econ", "label": "Economic Profile", "dataset_key": "cbp", "vintage": "2022", "geo_level": "county",
     "caveat": "Payroll per establishment, not revenue." , … },
   { "key": "drive_10", "label": "5–10 min drive time", "dataset_key": null, "caveat": "Straight-line 8 km approximation of drive time." },
   { "key": "drive_20", "label": "10–20 min drive time", "dataset_key": null, "caveat": "Straight-line 16 km approximation of drive time." },
   { "key": "practices", "label": "Practice Listings", "dataset_key": null } ]
    # The UI renders labels, "Source:" lines, legend caveats and card `on` states from this — never hard-coded copy (spec §12).
    # `enabled` is the licence gate; a disabled layer is also absent from every community object below.

GET /api/markets
→ [{ "cbsa_geoid": "12420", "name": "Austin, TX", "center": [30.31, -97.75], "zoom": 10 }, …]

GET /api/markets/{cbsa_geoid}/communities?band=place|drive_10   (default place)
→ { "band": "place", "vintage": "2019–2023", "attribution": [ … ],
    "communities": [
      { "listing_id": "…", "name": "Cedar Park", "lat": 30.5052, "lng": -97.8203, "location": "place_centroid|disclosed_point", "geo_precision": "rooftop",
        "pop": 81900, "hh": 27600, "income": 118400, "growth": 14.2, "pets": 15732, "econ": 685000, "vets": 7,
        "competition": { "count": 7, "geo_level": "zcta", "zctas": 3, "per_10k_households": 2.54, "level": "High",
                         "freshness": { "level_live": "High", "diverges": false, "as_of": "2026-09-02" } },   // `freshness` appears only in Phase C (D17) while `google_places_aggregate` is cleared — a bucket and a flag, never a count; selecting a listing whose signal is > 7 days old enqueues a background refresh
        "suppressed": [] } ] }
    # fixture field names (D6); numeric raw values; `level` uses the design's thresholds (<1.4 Low, <2.2 Moderate, else High).

GET /api/listings/{listing_id}/market?band=drive_10|drive_20|place   (default drive_10)
→ { "listing_id": "…", "band": "drive_10", "geo_precision": "tract", "vintage": "2019–2023", "computed_at": "…",
    "metrics": {
      "population":               { "value": 44800, "unit": "count", "is_derived": false, "moe": 2140, "suppressed": false, "source_dataset": "acs5", "vintage": "2019–2023" },
      "households":               { … },
      "median_hh_income":         { … "unit": "usd", "is_derived": true, "approximate": true … },
      "population_growth_pct":    { … "unit": "pct", "is_derived": true, "geo_level": "place", "inputs": {"acs5": "2019–2023", "acs5_prior": "2014–2018"} },
      "pet_households_est":       { … "is_derived": true, "assumed_rate": 0.57 },
      "establishments":           { "value": 7, "unit": "count", "source_dataset": "zbp", "vintage": "2022", "geo_level": "zcta" },
      "vets_per_10k_households":  { … "unit": "ratio", "is_derived": true, "inputs": {"acs5": "2019–2023", "zbp": "2022"} },
      "revenue_per_establishment":{ … "unit": "usd", "is_derived": true, "label": "Payroll per establishment", "source_dataset": "cbp", "geo_level": "county" },
      "income_index_vs_us":       { … "unit": "pct", "is_derived": true },
      "opportunity_score":        { "value": 50, "unit": "score", "is_derived": true, "formula_version": "v1", "components": { "income": 118400, "growth": 14.2, "vets_per_10k": 2.54 } } },
    "attribution": [ … ] }
    # suppressed → value null + suppress_reason; 404 {"error":{"code":"NO_MARKET_DATA"}} only for an existing published listing (and enqueues one backfill per 10 min);
    # unknown listing → 404 {"error":{"code":"NOT_FOUND"}} with nothing enqueued.

GET /api/admin/data-sources · POST /api/admin/data-sources/{key}/license   (operator/admin only — see A9)
```

## File map

| Path | Responsibility |
|---|---|
| `migrations/002_census_registry.sql` | `ingest_run`, `dataset_registry`, FK back-fill, `active_vintage`, `market_state`; registry seed (§2 + attribution) |
| `migrations/003_census_geo.sql` | `geo_area` + indexes |
| `migrations/004_census_measures.sql` | `acs_measure`, `cbp_industry`, `qwi_measure`, `bds_measure` |
| `migrations/008_zbp.sql` | `zbp_industry` (ZIP-level establishments, D11) |
| `migrations/060_geocode_cache.sql` | `geocode_cache`, `geocode_review` (365-day cache, §10; staff flags §11) — Phase B, after SP2's `010`–`059` |
| `migrations/061_census_listing_tables.sql` | `practice_location`, `practice_catchment`, `market_metric` (+`inputs`), licence-gate trigger (Phase B) |
| `app/census/__init__.py` | package |
| `app/census/registry.py` | `Dataset` records read from `dataset_registry`; `is_cleared(key)`; `attribution(keys)` |
| `app/census/client.py` | `CensusClient` — URL building, key check, timeouts, retry policy, UA, per-dataset concurrency, raw archive, sentinel normalisation, variable validation |
| `app/census/storage.py` | `ObjectStore` — boto3 to the Railway bucket; `put_immutable`, `get`, `exists` |
| `app/census/tiger.py` | boundary-file download + pyshp/shapely parse → `geo_area` upsert |
| `app/census/acs.py` | ACS detailed + subject + prior-vintage loads → `acs_measure` |
| `app/census/cbp.py`, `zbp.py`, `qwi.py`, `bds.py` | industry loads (county CBP, ZIP ZBP, QWI, BDS) |
| `app/census/ingest.py` | `IngestRun` lifecycle (`start/succeed/fail/abort`), row counting |
| `app/census/vintage.py` | QA diff + `activate()` |
| `app/census/geocode.py` | Census Geocoder client, normalisation + cache, fallback ladder → `practice_location` |
| `app/census/catchment.py` | buffer + tract intersection → `practice_catchment` |
| `app/census/metrics.py` | pure formulas (§8), MOE/CV rules (§14), aggregation |
| `app/census/materialize.py` | joins + writes `market_metric` with provenance |
| `app/tasks/census.py` | Celery tasks + beat schedule |
| `app/api/market.py` | `/api/layers`, `/api/markets*`, `/api/listings/{id}/market` |
| `app/api/admin_data_sources.py` | `/api/admin/data-sources` |
| `app/cache.py` | Redis helpers (`get_json`, `set_json`, TTLs) |
| `scripts/census_load.py` | operator CLI: `--acs 2023 --states 48,06,12,13`, `--cbp`, `--qwi`, `--tiger`, `--activate acs5 2019–2023 --by john` |
| `tests/census/…` | pytest per module; fixtures in `tests/census/fixtures/` (recorded Census JSON shapes) |

---

## Phase A — Reference data (no listing dependency)

### Task A1: Registry, ingest-run ledger, geography and measure tables (migrations 002–004)

**Files:**
- Create: `migrations/002_census_registry.sql`, `migrations/003_census_geo.sql`, `migrations/004_census_measures.sql`, `app/census/__init__.py`, `app/census/registry.py`, `tests/census/__init__.py`, `tests/census/conftest.py`, `tests/census/test_schema.py`, `tests/census/test_registry.py`

**Interfaces:**
- Produces: tables above; `registry.load(conn) -> dict[str, Dataset]`; `registry.is_cleared(conn, key) -> bool`; `registry.attribution(conn, keys) -> list[str]`; `Dataset(dataset_key, display_name, api_dataset_id, base_url, vintage, naics_param, refresh_cadence, license_status, license_name, license_url, attribution_text, last_verified_at, notes)`.

- [ ] **Step 1: Failing schema tests**

`tests/census/conftest.py`:
```python
import os
import uuid

import psycopg2
import pytest

from app.config import settings


def _maintenance(dsn: str) -> str:
    return dsn.rsplit("/", 1)[0] + "/postgres"


@pytest.fixture
def scratch_dsn():
    """Fresh database with all migrations applied; dropped afterwards."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("migrate", Path(__file__).resolve().parents[2] / "scripts" / "migrate.py")
    migrate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migrate)  # type: ignore[union-attr]
    name = f"pm_census_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(_maintenance(settings.database_url))
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    dsn = settings.database_url.rsplit("/", 1)[0] + f"/{name}"
    migrate.run(dsn)
    try:
        yield dsn
    finally:
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.close()


@pytest.fixture
def conn(scratch_dsn):
    c = psycopg2.connect(scratch_dsn)
    c.autocommit = True
    try:
        yield c
    finally:
        c.close()
```

`tests/census/test_schema.py`:
```python
def _cols(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position", (table,))
    return [r[0] for r in cur.fetchall()]


def test_registry_and_ledger_tables_match_spec_13(conn):
    with conn.cursor() as cur:
        assert _cols(cur, "ingest_run") == ["id", "dataset_key", "vintage", "started_at", "finished_at", "status",
                                            "rows_written", "request_count", "raw_payload_uri", "error_detail"]
        assert _cols(cur, "dataset_registry") == ["dataset_key", "display_name", "api_dataset_id", "base_url", "vintage",
                                                  "naics_param", "refresh_cadence", "license_status", "license_name",
                                                  "license_url", "attribution_text", "last_verified_at", "notes"]
        assert _cols(cur, "active_vintage") == ["dataset_key", "vintage", "activated_at", "activated_by"]
        cur.execute("SELECT conname FROM pg_constraint WHERE conname = 'ingest_run_dataset_fk'")
        assert cur.fetchone(), "spec §13 adds the ingest_run → dataset_registry FK after the registry exists"


def test_geo_area_has_geometry_and_gist_index(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT type, srid FROM geometry_columns WHERE f_table_name='geo_area' AND f_geometry_column='geom'")
        assert cur.fetchone() == ("MULTIPOLYGON", 4269)
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename='geo_area'")
        names = {r[0] for r in cur.fetchall()}
        assert {"geo_area_geom_gix", "geo_area_level_idx"} <= names


def test_measure_tables_have_spec_primary_keys(conn):
    with conn.cursor() as cur:
        for table, pk in [
            ("acs_measure", ["geo_id", "summary_level", "vintage", "variable"]),
            ("cbp_industry", ["geo_id", "summary_level", "vintage", "naics_code"]),
            ("qwi_measure", ["geo_id", "summary_level", "naics_code", "year", "quarter"]),
            ("bds_measure", ["geo_id", "summary_level", "vintage", "naics_code"]),
        ]:
            cur.execute("""
                SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass AND i.indisprimary ORDER BY array_position(i.indkey, a.attnum)""", (table,))
            assert [r[0] for r in cur.fetchall()] == pk, table


def test_license_status_is_constrained(conn):
    import psycopg2
    with conn.cursor() as cur, pytest_raises(psycopg2.errors.CheckViolation):
        cur.execute("""INSERT INTO dataset_registry (dataset_key, display_name, base_url, vintage, refresh_cadence,
                       license_status, attribution_text) VALUES ('x','x','x','x','x','maybe','x')""")


from contextlib import contextmanager
import pytest


@contextmanager
def pytest_raises(exc):
    with pytest.raises(exc):
        yield
```

`tests/census/test_registry.py`:
```python
from app.census.registry import attribution, is_cleared, load

SPEC_KEYS = {"acs5", "acs5_subject", "acs5_prior", "cbp", "zbp", "qwi", "bds", "geocoder", "tiger_cb", "aies", "osm_tiles", "imagery", "pet_ownership", "practice_locations",
             "google_places_aggregate", "overture_places", "fsq_os_places"}  # last three: D16/D17 candidates, never ingested until cleared


def test_seed_matches_the_spec_dataset_register(conn):
    reg = load(conn)
    assert set(reg) == SPEC_KEYS
    assert reg["acs5"].api_dataset_id == "2023/acs/acs5" and reg["acs5"].vintage == "2019–2023"
    assert reg["acs5_prior"].api_dataset_id == "2018/acs/acs5"
    assert reg["cbp"].api_dataset_id == "2022/cbp" and reg["cbp"].naics_param == "NAICS2017"
    assert reg["qwi"].api_dataset_id == "timeseries/qwi/sa"
    assert reg["imagery"].license_status == "unresolved"
    assert reg["pet_ownership"].license_status == "blocked"
    assert reg["aies"].license_status == "unresolved"  # "Verify ID" in the spec → not cleared until confirmed
    assert reg["zbp"].api_dataset_id == "2022/zbp" and reg["zbp"].naics_param == "NAICS2017" and reg["zbp"].license_status == "cleared"
    assert reg["practice_locations"].license_status == "blocked"  # spec §12: third-party practice-location data is out of scope for V1
    for k in ("google_places_aggregate", "overture_places", "fsq_os_places"):
        assert reg[k].license_status == "unresolved"  # D16/D17: candidates only; the gate keeps them out of every table and payload
    for k in ("acs5", "acs5_subject", "acs5_prior", "cbp", "qwi", "bds", "geocoder", "tiger_cb"):
        assert reg[k].license_status == "cleared" and reg[k].license_name == "Public domain"


def test_is_cleared_and_attribution(conn):
    assert is_cleared(conn, "acs5") is True
    assert is_cleared(conn, "pet_ownership") is False
    assert is_cleared(conn, "nope") is False
    assert attribution(conn, ["acs5", "cbp"]) == [
        "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023",
        "Source: U.S. Census Bureau, County Business Patterns, 2022",
    ]
```

Run: `poetry run pytest tests/census -q` → FAIL (tables and module missing).

- [ ] **Step 2: Migrations (spec §13 DDL verbatim, plus seed)**

`migrations/002_census_registry.sql`:
```sql
-- Census & Market Data Source Specification v1.0 §13 — provenance and registry.
-- Created first: other tables reference ingest_run.
CREATE TABLE ingest_run (
  id bigserial PRIMARY KEY,
  dataset_key text NOT NULL,
  vintage text NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  status text NOT NULL CHECK (status IN ('running','succeeded','failed','aborted')),
  rows_written bigint DEFAULT 0,
  request_count integer DEFAULT 0,
  raw_payload_uri text,
  error_detail text
);

-- Every external source, and whether it may be used at all.
CREATE TABLE dataset_registry (
  dataset_key text PRIMARY KEY,
  display_name text NOT NULL,
  api_dataset_id text,
  base_url text NOT NULL,
  vintage text NOT NULL,
  naics_param text,
  refresh_cadence text NOT NULL,
  license_status text NOT NULL CHECK (license_status IN ('cleared','unresolved','blocked')),
  license_name text,
  license_url text,
  attribution_text text NOT NULL,
  last_verified_at timestamptz,
  notes text
);

ALTER TABLE ingest_run
  ADD CONSTRAINT ingest_run_dataset_fk
  FOREIGN KEY (dataset_key) REFERENCES dataset_registry(dataset_key);

-- Which vintage the app is allowed to read. Flipped only after QA.
CREATE TABLE active_vintage (
  dataset_key text PRIMARY KEY REFERENCES dataset_registry(dataset_key),
  vintage text NOT NULL,
  activated_at timestamptz NOT NULL,
  activated_by text NOT NULL
);

-- States whose geographies and ACS rows we load (plan decision D4; auto-extended by geocoding).
CREATE TABLE market_state (
  state_fips char(2) PRIMARY KEY,
  name text NOT NULL,
  added_at timestamptz NOT NULL DEFAULT now(),
  reason text NOT NULL
);
INSERT INTO market_state (state_fips, name, reason) VALUES
  ('48','Texas','design market Austin–Round Rock–San Marcos (12420)'),
  ('06','California','design market Sacramento–Roseville–Folsom (40900)'),
  ('12','Florida','design market Orlando–Kissimmee–Sanford (36740)'),
  ('13','Georgia','design market Atlanta–Sandy Springs–Roswell (12060)');

-- §2 dataset register, verbatim. Rows marked unresolved/blocked must not ship (§2, §12).
INSERT INTO dataset_registry
  (dataset_key, display_name, api_dataset_id, base_url, vintage, naics_param, refresh_cadence, license_status, license_name, license_url, attribution_text, notes) VALUES
  ('acs5','ACS 5-Year Detailed Tables','2023/acs/acs5','https://api.census.gov/data','2019–2023',NULL,'Annual (Dec)','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023',NULL),
  ('acs5_subject','ACS 5-Year Subject Tables','2023/acs/acs5/subject','https://api.census.gov/data','2019–2023',NULL,'Annual (Dec)','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, American Community Survey 5-Year Subject Tables, 2019–2023',NULL),
  ('acs5_prior','ACS 5-Year, baseline for growth','2018/acs/acs5','https://api.census.gov/data','2014–2018',NULL,'Static','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2014–2018','Growth baseline only'),
  ('cbp','County Business Patterns','2022/cbp','https://api.census.gov/data','2022','NAICS2017','Annual (Apr)','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, County Business Patterns, 2022','Parameter renames to NAICS2022 with the 2023+ releases'),
  ('zbp','ZIP Code Business Patterns','2022/zbp','https://api.census.gov/data','2022','NAICS2017','Annual (Apr)','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, ZIP Code Business Patterns, 2022','Plan decision D11 — community-level competition counts; ZIP codes treated as ZCTAs (approximation labelled in the UI). Confirm 2022/zbp exists at api.census.gov/data.html; fall back to 2021/zbp.'),
  ('qwi','Quarterly Workforce Indicators','timeseries/qwi/sa','https://api.census.gov/data','latest quarter',NULL,'Quarterly','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, Quarterly Workforce Indicators',NULL),
  ('bds','Business Dynamics Statistics','timeseries/bds','https://api.census.gov/data','latest',NULL,'Annual','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, Business Dynamics Statistics',NULL),
  ('geocoder','Census Geocoder (geographies)',NULL,'https://geocoding.geo.census.gov/geocoder','Current_Current',NULL,'On write','cleared','Public domain','https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html','Geocoding: U.S. Census Bureau Geocoder',NULL),
  ('tiger_cb','TIGER Cartographic Boundary files','TIGER2023/cb_2023_*','https://www2.census.gov/geo/tiger/GENZ2023/shp','2023',NULL,'Annual','cleared','Public domain','https://www.census.gov/programs-surveys/geography/technical-documentation/naming-convention/cartographic-boundary-file.html','Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023',NULL),
  ('aies','Annual Integrated Economic Survey',NULL,'https://api.census.gov/data','TBD',NULL,'Annual','unresolved','Verify ID',NULL,'Source: U.S. Census Bureau, Annual Integrated Economic Survey','Confirm dataset identifier and geography availability before any revenue-benchmark layer is promised (§15)'),
  ('osm_tiles','Street basemap tiles (CARTO, OSM data)',NULL,'https://basemaps.cartocdn.com/light_all','live',NULL,'live','cleared','ODbL 1.0','https://www.openstreetmap.org/copyright','© OpenStreetMap contributors © CARTO','Registered by the spec; the approved design ships Esri tiles — VIN Foundation decision pending (Foundation spec §9)'),
  ('imagery','Satellite basemap',NULL,'vendor TBD','live',NULL,'live','unresolved',NULL,NULL,'Imagery attribution pending licence','Satellite toggle stays behind a feature flag until a written licence names commercial web display'),
  ('pet_ownership','Pet ownership incidence (commercial)',NULL,'licensed feed','n/a',NULL,'n/a','blocked',NULL,NULL,'Pet-ownership incidence (licensed) — not in use','Ship only the ACS-derived estimate (rate 0.57) until a licence is signed'),
  ('practice_locations','Third-party practice location data',NULL,'n/a','n/a',NULL,'n/a','blocked',NULL,NULL,'Practice locations (third party) — not in use','Spec §12: purchased or scraped veterinary location lists are out of scope for V1 (undocumented provenance). Includes the 2017 Google Places export Report_Hospital_Competitor_All_US_ZipCode_FULL.csv (D15): Google Maps Platform Terms §3.2.3 and SST §14 forbid storing or rendering its content. Competition counts come from Census establishment totals only.'),
  ('google_places_aggregate','Google Places Aggregate API (competition freshness signal)',NULL,'https://areainsights.googleapis.com/v1','live',NULL,'Monthly','unresolved','Google Maps Platform Terms + Service Specific Terms §13','https://cloud.google.com/maps-platform/terms/maps-service-terms','Competition freshness derived from Google Places counts (Google)','D17 / Task C1. The POI count is held in memory only (SST §13.2, 30-day ceiling); persisted values are level_live and diverges (SST §13.1 Customer Values). Clear only after VIN Foundation counsel accepts SST §13 and a Google Cloud billing account exists. Key GOOGLE_MAPS_API_KEY on the worker service only.'),
  ('overture_places','Overture Maps Places (competitor points)',NULL,'s3://overturemaps-us-west-2/release','monthly release',NULL,'Monthly','unresolved','CDLA-Permissive-2.0 (Foursquare-sourced rows: Apache-2.0)','https://docs.overturemaps.org/attribution/','Practice locations: © Overture Maps Foundation contributors (CDLA-Permissive-2.0); portions © Foursquare (Apache-2.0)','D16 rank 1. Taxonomy entry veterinarian; per-feature sources[] and confidence retained. Clear after the VIN Foundation approves a competitor-points layer (Task C2).'),
  ('fsq_os_places','Foursquare OS Places (competitor points, alternate)',NULL,'https://huggingface.co/datasets/foursquare/fsq-os-places','monthly release',NULL,'Monthly','unresolved','Apache-2.0','https://opensource.foursquare.com/os-places/','Practice locations: Foursquare OS Places (Apache-2.0)','D16 rank 2; category label Veterinarian. Redundant with overture_places unless Overture stops carrying Foursquare rows.');
```

`migrations/003_census_geo.sql`:
```sql
-- §13 geo_area: Census geographies with geometry, one row per GEOID per vintage.
CREATE TABLE geo_area (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL, -- 140 tract, 150 bg, 160 place, 860 zcta, 050 county, 310 cbsa, 040 state, 010 nation
  vintage text NOT NULL,
  name text NOT NULL,
  state_fips char(2),
  county_fips char(3),
  parent_geo_id text,
  land_area_m2 bigint,
  geom geometry(MultiPolygon, 4269),
  centroid geometry(Point, 4269),
  PRIMARY KEY (geo_id, summary_level, vintage)
);
CREATE INDEX geo_area_geom_gix ON geo_area USING gist (geom);
CREATE INDEX geo_area_level_idx ON geo_area (summary_level, vintage);
```

`migrations/004_census_measures.sql`:
```sql
-- §13 measure tables, long format.
CREATE TABLE acs_measure (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,
  vintage text NOT NULL,
  variable text NOT NULL, -- e.g. B19013_001E
  estimate numeric,
  moe numeric,
  ingest_run_id bigint NOT NULL REFERENCES ingest_run(id),
  PRIMARY KEY (geo_id, summary_level, vintage, variable)
);
CREATE INDEX acs_measure_var_idx ON acs_measure (variable, vintage);

CREATE TABLE cbp_industry (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,
  vintage text NOT NULL,
  naics_code text NOT NULL, -- '541940'
  establishments integer,
  employment integer,
  annual_payroll_k bigint,
  flag text, -- Census noise/suppression flag, verbatim
  ingest_run_id bigint NOT NULL REFERENCES ingest_run(id),
  PRIMARY KEY (geo_id, summary_level, vintage, naics_code)
);

CREATE TABLE qwi_measure (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,
  naics_code text NOT NULL, -- '5419'
  year smallint NOT NULL,
  quarter smallint NOT NULL,
  avg_monthly_earnings integer,
  sector_employment integer,
  sector_hires integer,
  ingest_run_id bigint NOT NULL REFERENCES ingest_run(id),
  PRIMARY KEY (geo_id, summary_level, naics_code, year, quarter)
);

-- BDS is not in the spec's DDL but is in its dataset register and variable map (FIRM, ESTAB_ENTRY).
CREATE TABLE bds_measure (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,
  vintage text NOT NULL, -- BDS year, e.g. '2022'
  naics_code text NOT NULL, -- '54'
  firms integer,
  estab_entry integer,
  ingest_run_id bigint NOT NULL REFERENCES ingest_run(id),
  PRIMARY KEY (geo_id, summary_level, vintage, naics_code)
);
```

- [ ] **Step 3: Registry module**

`app/census/registry.py`:
```python
"""Read side of dataset_registry. Attribution strings and licence status come from
the database (spec §12) so a terms change propagates in one UPDATE."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

COLUMNS = ("dataset_key", "display_name", "api_dataset_id", "base_url", "vintage", "naics_param", "refresh_cadence",
           "license_status", "license_name", "license_url", "attribution_text", "last_verified_at", "notes")


@dataclass(frozen=True)
class Dataset:
    dataset_key: str
    display_name: str
    api_dataset_id: str | None
    base_url: str
    vintage: str
    naics_param: str | None
    refresh_cadence: str
    license_status: str
    license_name: str | None
    license_url: str | None
    attribution_text: str
    last_verified_at: datetime | None
    notes: str | None

    @property
    def cleared(self) -> bool:
        return self.license_status == "cleared"


def load(conn) -> dict[str, Dataset]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(COLUMNS)} FROM dataset_registry ORDER BY dataset_key")
        return {row[0]: Dataset(*row) for row in cur.fetchall()}


def is_cleared(conn, dataset_key: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT license_status = 'cleared' FROM dataset_registry WHERE dataset_key = %s", (dataset_key,))
        row = cur.fetchone()
        return bool(row and row[0])


def attribution(conn, dataset_keys: list[str]) -> list[str]:
    """Attribution lines in the order requested; unknown keys are skipped, not invented."""
    if not dataset_keys:
        return []
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, attribution_text FROM dataset_registry WHERE dataset_key = ANY(%s)", (dataset_keys,))
        by_key = dict(cur.fetchall())
    return [by_key[k] for k in dataset_keys if k in by_key]
```

Run: `poetry run pytest tests/census -q` → all pass. Also `poetry run pytest -q` (whole suite, Foundation tests still green — `001_init.sql` is untouched).

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(census): registry, ingest ledger, geography and measure tables (spec §13) with the §2 dataset seed

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/census-data-layer && git push production feat/census-data-layer
```

---

### Task A2: Object store adapter (Railway bucket) and settings

**Files:**
- Create: `app/census/storage.py`, `tests/census/test_storage.py`
- Modify: `app/config.py` (optional census/S3 fields), `pyproject.toml` (deps), `.env.example`, `DEPLOY.md` (variables table)

**Interfaces:**
- Produces: `ObjectStore(endpoint_url, bucket, access_key, secret_key, region='auto')` with `put_immutable(key: str, data: bytes, content_type: str) -> bool` (False when the key already exists — never overwrites), `get(key) -> bytes | None`, `exists(key) -> bool`; `ObjectStore.from_settings(settings) -> ObjectStore | None` (None when unconfigured → archive disabled with a logged warning, never a crash of the API).
- Settings added (all optional, default `None`): `census_api_key`, `census_contact_email`, `s3_endpoint_url`, `s3_bucket`, `s3_access_key_id`, `s3_secret_access_key`.

- [ ] **Step 1: Dependencies**

```bash
poetry add boto3 pyshp shapely
poetry add --group dev "moto[s3]"
```

- [ ] **Step 2: Failing tests**

`tests/census/test_storage.py`:
```python
import boto3
import pytest
from moto import mock_aws

from app.census.storage import ObjectStore


@pytest.fixture
def store():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="pm-test")
        yield ObjectStore(endpoint_url=None, bucket="pm-test", access_key="x", secret_key="y", region="us-east-1")


def test_put_immutable_writes_once_and_never_overwrites(store):
    assert store.put_immutable("raw/acs5/2019-2023/abc.json", b'{"a":1}', "application/json") is True
    assert store.put_immutable("raw/acs5/2019-2023/abc.json", b'{"a":2}', "application/json") is False
    assert store.get("raw/acs5/2019-2023/abc.json") == b'{"a":1}'


def test_get_missing_returns_none(store):
    assert store.get("nope") is None
    assert store.exists("nope") is False


def test_from_settings_is_none_when_unconfigured():
    from app.config import Settings
    s = Settings(database_url="postgresql://x", redis_url="redis://x", environment="test", api_secret_key="x")
    assert ObjectStore.from_settings(s) is None
```

Run: `poetry run pytest tests/census/test_storage.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement**

Add to `Settings` in `app/config.py` (after `commit_sha`):
```python
    # Sub-project 3 — market-data layer. All optional so the API boots without them;
    # the ingest worker enforces CENSUS_API_KEY at startup (app/census/client.py).
    census_api_key: str | None = None
    census_contact_email: str | None = None
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
```

`app/census/storage.py`:
```python
"""Immutable raw-payload archive on a Railway bucket (S3-compatible). Spec §10:
raw API responses are kept permanently as the audit record of what we received."""
from __future__ import annotations

import logging

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)


class ObjectStore:
    def __init__(self, endpoint_url: str | None, bucket: str, access_key: str, secret_key: str, region: str = "auto"):
        self.bucket = bucket
        self._s3 = boto3.client(
            "s3", endpoint_url=endpoint_url, region_name=region,
            aws_access_key_id=access_key, aws_secret_access_key=secret_key,
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )

    @classmethod
    def from_settings(cls, settings) -> "ObjectStore | None":
        if not (settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key):
            log.warning("[storage] S3 bucket not configured — raw payload archive disabled")
            return None
        return cls(settings.s3_endpoint_url, settings.s3_bucket, settings.s3_access_key_id, settings.s3_secret_access_key)

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put_immutable(self, key: str, data: bytes, content_type: str) -> bool:
        if self.exists(key):
            return False
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return True

    def get(self, key: str) -> bytes | None:
        try:
            return self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
```

Run: `poetry run pytest tests/census/test_storage.py -q` → 3 passed.

- [ ] **Step 4: Provision the buckets (one per environment) and document variables**

```bash
railway status --json | python3 -c 'import sys,json; assert json.load(sys.stdin)["name"]=="Practice Match"'
railway bucket create practice-match-data-qa --environment QA --json
railway bucket create practice-match-data-prod --environment production --json
railway bucket credentials --bucket practice-match-data-qa --environment QA --json      # do not paste the output anywhere
```
Set on `worker` (and `api`) per environment, values from the credentials output: `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`; also `CENSUS_API_KEY` (John's key, worker only) and `CENSUS_CONTACT_EMAIL=john@vetvision.org`. Add the six rows to `DEPLOY.md`'s variables table and commented placeholders to `.env.example`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(census): immutable object-store archive on Railway buckets; census/S3 settings

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/census-data-layer && git push production feat/census-data-layer
```

---

### Task A3: Census Data API client — key, timeouts, retry policy, concurrency, archive, sentinels, variable validation

**Files:**
- Create: `app/census/client.py`, `tests/census/test_client.py`

**Interfaces:**
- Produces: `require_key(env=os.environ) -> str` (SystemExit(3) naming `CENSUS_API_KEY` when absent); `CensusClient(api_key, dataset: Dataset, archive: ObjectStore | None, *, transport=None, sleep=time.sleep, version=VERSION, contact=None)`; `build_url(get: list[str], for_: str, in_: str | None = None, extra: dict[str, str] | None = None) -> str` (key **excluded** from the archive key: `archive_key(url_without_key)`); `fetch_table(url) -> list[dict[str, str | None]]` (header row → dicts, sentinels → `None`, archived); `validate_variables(rows, expected: list[str]) -> None` (raises `VariableMissing`); attributes `concurrency` (starts 4, halves on 429, floor 1), `request_count`; exceptions `CensusHTTPError(status, url)`, `VariableMissing(missing: list[str])`.

- [ ] **Step 1: Failing tests**

`tests/census/test_client.py`:
```python
import hashlib
import json

import httpx
import pytest

from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_key
from app.census.registry import Dataset

ACS = Dataset("acs5", "ACS", "2023/acs/acs5", "https://api.census.gov/data", "2019–2023", None, "Annual (Dec)",
              "cleared", "Public domain", None, "Source: …", None, None)
TABLE = [["NAME", "B01003_001E", "B01003_001M", "state", "county", "tract"],
         ["Tract 1", "4321", "-555555555", "48", "453", "000101"],
         ["Tract 2", "-666666666", "120", "48", "453", "000102"]]


class Archive:
    def __init__(self): self.puts = []
    def put_immutable(self, key, data, content_type): self.puts.append((key, data, content_type)); return True


def make(handler, archive=None, sleeps=None):
    return CensusClient("KEY123", ACS, archive, transport=httpx.MockTransport(handler),
                        sleep=(sleeps.append if sleeps is not None else (lambda s: None)), version="0.1.0", contact="john@vetvision.org")


def test_require_key_exits_naming_the_variable(capsys):
    with pytest.raises(SystemExit) as e:
        require_key(env={})
    assert e.value.code == 3 and "CENSUS_API_KEY" in capsys.readouterr().err
    assert require_key(env={"CENSUS_API_KEY": "k"}) == "k"


def test_build_url_matches_spec_shape():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    url = c.build_url(["NAME", "B01003_001E", "B01003_001M"], "tract:*", "state:48+county:453")
    assert url == "https://api.census.gov/data/2023/acs/acs5?get=NAME,B01003_001E,B01003_001M&for=tract:*&in=state:48+county:453&key=KEY123"
    assert c.archive_key(url) == "raw/acs5/2019–2023/" + hashlib.sha256(url.replace("&key=KEY123", "").encode()).hexdigest() + ".json"


def test_fetch_normalises_sentinels_and_archives_the_raw_body():
    seen = {}
    def handler(r):
        seen["ua"] = r.headers["user-agent"]
        return httpx.Response(200, json=TABLE)
    archive = Archive()
    c = make(handler, archive)
    rows = c.fetch_table(c.build_url(["NAME", "B01003_001E", "B01003_001M"], "tract:*", "state:48"))
    assert rows[0] == {"NAME": "Tract 1", "B01003_001E": "4321", "B01003_001M": None, "state": "48", "county": "453", "tract": "000101"}
    assert rows[1]["B01003_001E"] is None and rows[1]["B01003_001M"] == "120"
    assert seen["ua"] == "PracticeMatch/0.1.0 (VIN Foundation; john@vetvision.org)"
    assert len(archive.puts) == 1 and json.loads(archive.puts[0][1]) == TABLE and archive.puts[0][2] == "application/json"
    assert "KEY123" not in archive.puts[0][0]


def test_retries_5xx_three_times_with_backoff_then_raises():
    calls = []
    def handler(r): calls.append(1); return httpx.Response(503)
    sleeps = []
    c = make(handler, sleeps=sleeps)
    with pytest.raises(CensusHTTPError) as e:
        c.fetch_table("https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=KEY123")
    assert len(calls) == 4 and e.value.status == 503
    assert "KEY123" not in str(e.value) and "KEY123" not in e.value.url     # red-team C6: key never in errors/logs
    assert len(sleeps) == 3 and sleeps[0] < sleeps[1] < sleeps[2]


def test_recovers_after_transient_500():
    calls = []
    def handler(r):
        calls.append(1)
        return httpx.Response(500) if len(calls) < 3 else httpx.Response(200, json=TABLE)
    rows = make(handler).fetch_table("https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=KEY123")
    assert len(calls) == 3 and len(rows) == 2


def test_does_not_retry_4xx():
    calls = []
    def handler(r): calls.append(1); return httpx.Response(400, text="unknown variable")
    with pytest.raises(CensusHTTPError) as e:
        make(handler).fetch_table("https://api.census.gov/data/2023/acs/acs5?get=NOPE&for=us:1&key=KEY123")
    assert len(calls) == 1 and e.value.status == 400


def test_429_halves_concurrency_and_retries():
    calls = []
    def handler(r):
        calls.append(1)
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, json=TABLE)
    c = make(handler)
    assert c.concurrency == 4
    c.fetch_table("https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=KEY123")
    assert c.concurrency == 2 and len(calls) == 2


def test_validate_variables_aborts_on_missing_column():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    rows = c.fetch_table(c.build_url(["NAME", "B01003_001E", "B01003_001M"], "tract:*", "state:48"))
    c.validate_variables(rows, ["B01003_001E", "B01003_001M"])
    with pytest.raises(VariableMissing) as e:
        c.validate_variables(rows, ["B01003_001E", "B19013_001E"])
    assert e.value.missing == ["B19013_001E"]


def test_timeouts_are_the_spec_values():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    assert c.timeout.connect == 15.0 and c.timeout.read == 45.0
```

Run: `poetry run pytest tests/census/test_client.py -q` → FAIL (module missing).

- [ ] **Step 2: Implement**

`app/census/client.py`:
```python
"""Census Data API client (spec §3). Synchronous — it runs inside Celery tasks.

Rules encoded here: explicit vintage in every URL (the dataset's api_dataset_id),
key required, 15 s connect / 45 s read, three retries with exponential backoff
and jitter on 5xx and 429 only, descriptive User-Agent, at most four concurrent
requests per dataset (halved on 429), every raw body archived immutably, Census
sentinels normalised to None at parse time.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from urllib.parse import urlencode

import httpx

from app.census.registry import Dataset

SENTINELS = {"-666666666", "-999999999", "-555555555", "-333333333", "-222222222", "-888888888", "", "null"}
RETRY_STATUSES = {429, *range(500, 600)}
MAX_RETRIES = 3


def require_key(env=os.environ) -> str:
    key = env.get("CENSUS_API_KEY")
    if not key:
        print("[census] CENSUS_API_KEY is not set — the ingest worker cannot start (spec §3: never fall back to unkeyed calls)", file=sys.stderr)
        raise SystemExit(3)
    return key


class CensusHTTPError(Exception):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} from {redact(url)}")   # never leak the key into logs (red-team C6)
        self.status, self.url = status, redact(url)


class VariableMissing(Exception):
    def __init__(self, missing: list[str]):
        super().__init__(f"response lacks expected variables: {missing}")
        self.missing = missing


def redact(url: str) -> str:
    return re.sub(r"([?&]key=)[^&]+", r"\1<redacted>", url)


def normalise(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return None if s in SENTINELS else s


class CensusClient:
    def __init__(self, api_key: str, dataset: Dataset, archive=None, *, transport=None, sleep=time.sleep,
                 version: str = "dev", contact: str | None = None, concurrency: int = 4):
        self.api_key, self.dataset, self.archive, self._sleep = api_key, dataset, archive, sleep
        self.timeout = httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=15.0)
        ua = f"PracticeMatch/{version} (VIN Foundation; {contact or 'unspecified contact'})"
        self._http = httpx.Client(timeout=self.timeout, headers={"User-Agent": ua}, transport=transport)
        self.concurrency = concurrency
        self._gate = threading.BoundedSemaphore(concurrency)
        self.request_count = 0

    # ---- URLs -------------------------------------------------------------
    def build_url(self, get: list[str], for_: str, in_: str | None = None, extra: dict[str, str] | None = None) -> str:
        params = [("get", ",".join(get)), ("for", for_)]
        if in_:
            params.append(("in", in_))
        for k, v in (extra or {}).items():
            params.append((k, v))
        params.append(("key", self.api_key))
        # Census expects ':' '*' '+' and ',' unescaped in these parameters.
        query = urlencode(params, safe=":*+,")
        return f"{self.dataset.base_url}/{self.dataset.api_dataset_id}?{query}"

    def archive_key(self, url: str) -> str:
        public = re.sub(r"[?&]key=[^&]+", "", url)
        return f"raw/{self.dataset.dataset_key}/{self.dataset.vintage}/{hashlib.sha256(public.encode()).hexdigest()}.json"

    # ---- fetching -----------------------------------------------------------
    def _get(self, url: str) -> httpx.Response:
        for attempt in range(MAX_RETRIES + 1):
            with self._gate:
                self.request_count += 1
                resp = self._http.get(url)
            if resp.status_code < 400:
                return resp
            if resp.status_code == 429:
                self.concurrency = max(1, self.concurrency // 2)
                self._gate = threading.BoundedSemaphore(self.concurrency)
            if resp.status_code not in RETRY_STATUSES or attempt == MAX_RETRIES:
                raise CensusHTTPError(resp.status_code, url)
            self._sleep((2 ** attempt) + random.uniform(0, 0.5))
        raise AssertionError("unreachable")

    def fetch_table(self, url: str) -> list[dict[str, str | None]]:
        resp = self._get(url)
        body = resp.content
        if self.archive is not None:
            self.archive.put_immutable(self.archive_key(url), body, "application/json")
        table = json.loads(body)
        if not table or not isinstance(table[0], list):
            raise ValueError(f"unexpected Census response shape from {url}")
        header = table[0]
        return [{h: normalise(v) for h, v in zip(header, row)} for row in table[1:]]

    @staticmethod
    def validate_variables(rows: list[dict], expected: list[str]) -> None:
        present = set(rows[0].keys()) if rows else set()
        missing = [v for v in expected if v not in present]
        if missing:
            raise VariableMissing(missing)
```

Run: `poetry run pytest tests/census/test_client.py -q` → 9 passed.

- [ ] **Step 3: Worker startup enforces the key**

In `scripts/start.sh`, inside `worker)` before the `celery … &` line:
```bash
    python -c "from app.census.client import require_key; require_key()"   # exits 3 with the variable named (spec §3)
```
Re-run `scripts/verify-image.sh` with `-e CENSUS_API_KEY=dummy` added to `COMMON` → still passes; run the worker container once **without** it and confirm `docker logs` shows the `[census] CENSUS_API_KEY is not set` line and the container exits.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(census): Census Data API client — key gate, spec timeouts, 5xx/429 retry with backoff, concurrency, archive, sentinels

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/census-data-layer && git push production feat/census-data-layer
```

---

### Task A4: Geographies — TIGER cartographic boundary files into `geo_area`

**Files:**
- Create: `app/census/tiger.py`, `tests/census/test_tiger.py`
- Modify: `scripts/census_load.py` (created here with `--tiger`)

**Interfaces:**
- Produces: `BOUNDARY_FILES(vintage_year: int, state_fips: list[str]) -> list[BoundarySpec]`; `BoundarySpec(summary_level, url, geoid_field, name_field, state_field, county_field, land_field, parent)`; `parse_shapefile(zip_bytes, spec) -> list[GeoRow]`; `GeoRow(geo_id, summary_level, name, state_fips, county_fips, parent_geo_id, land_area_m2, wkb: bytes)`; `upsert_geo(conn, rows, vintage) -> int`; `load_boundaries(conn, http: httpx.Client, states, vintage='2023') -> dict[str, int]`.

- [ ] **Step 1: Failing tests (in-memory shapefile via pyshp)**

`tests/census/test_tiger.py`:
```python
import io
import zipfile

import shapefile  # pyshp
import pytest

from app.census.tiger import BOUNDARY_FILES, BoundarySpec, parse_shapefile, upsert_geo

TRACT = BoundarySpec(summary_level="140", url="mem://tract", geoid_field="GEOID", name_field="NAMELSAD",
                     state_field="STATEFP", county_field="COUNTYFP", land_field="ALAND", parent="county")


def _zip_with_shapefile(records):
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    w.field("GEOID", "C", 11); w.field("NAMELSAD", "C", 40); w.field("STATEFP", "C", 2); w.field("COUNTYFP", "C", 3); w.field("ALAND", "N", 14, 0)
    for geoid, name, st, co, aland, ring in records:
        w.poly([ring]); w.record(geoid, name, st, co, aland)
    w.close()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cb_2023_48_tract_500k.shp", shp.getvalue()); z.writestr("cb_2023_48_tract_500k.shx", shx.getvalue()); z.writestr("cb_2023_48_tract_500k.dbf", dbf.getvalue())
    return buf.getvalue()


SQUARE = [(-97.9, 30.5), (-97.8, 30.5), (-97.8, 30.6), (-97.9, 30.6), (-97.9, 30.5)]
RECORDS = [("48453000101", "Census Tract 1.01", "48", "453", 1234567, SQUARE),
           ("48453000102", "Census Tract 1.02", "48", "453", 2345678, [(x + 0.2, y) for x, y in SQUARE])]


def test_parse_shapefile_yields_multipolygon_rows_with_parent_geoid():
    rows = parse_shapefile(_zip_with_shapefile(RECORDS), TRACT)
    assert [r.geo_id for r in rows] == ["48453000101", "48453000102"]
    r = rows[0]
    assert (r.summary_level, r.name, r.state_fips, r.county_fips, r.parent_geo_id, r.land_area_m2) == ("140", "Census Tract 1.01", "48", "453", "48453", 1234567)
    from shapely import wkb
    g = wkb.loads(r.wkb)
    assert g.geom_type == "MultiPolygon" and abs(g.area - 0.01) < 1e-6


def test_upsert_is_idempotent_and_computes_centroid(conn):
    rows = parse_shapefile(_zip_with_shapefile(RECORDS), TRACT)
    assert upsert_geo(conn, rows, "2023") == 2
    assert upsert_geo(conn, rows, "2023") == 2  # same rows again → still 2, no duplicates
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), max(ST_SRID(geom)) FROM geo_area WHERE summary_level='140' AND vintage='2023'")
        assert cur.fetchone() == (2, 4269)
        cur.execute("SELECT ST_X(centroid), ST_Y(centroid) FROM geo_area WHERE geo_id='48453000101'")
        x, y = cur.fetchone()
        assert abs(x + 97.85) < 1e-6 and abs(y - 30.55) < 1e-6
        cur.execute("SELECT ST_Contains(geom, centroid) FROM geo_area WHERE geo_id='48453000101'")
        assert cur.fetchone()[0] is True


def test_boundary_files_cover_every_spec_level_for_the_market_states():
    specs = BOUNDARY_FILES(2023, ["48", "06"])
    levels = sorted({s.summary_level for s in specs})
    assert levels == ["010", "040", "050", "140", "160", "310", "860"]
    urls = {s.url for s in specs}
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_48_tract_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_06_place_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_cbsa_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_zcta520_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_nation_5m.zip" in urls
```

Run: `poetry run pytest tests/census/test_tiger.py -q` → FAIL (module missing).

- [ ] **Step 2: Implement**

`app/census/tiger.py`:
```python
"""TIGER cartographic boundary files → geo_area (spec §2 tiger_cb, §6 levels, §13).
Pure Python: pyshp reads the shapefile inside the zip, shapely normalises to
MultiPolygon WKB, PostGIS computes the centroid. No GDAL in the image (plan D2)."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import httpx
import shapefile
from shapely.geometry import MultiPolygon, shape

BASE = "https://www2.census.gov/geo/tiger/GENZ{y}/shp"


@dataclass(frozen=True)
class BoundarySpec:
    summary_level: str
    url: str
    geoid_field: str
    name_field: str
    state_field: str | None
    county_field: str | None
    land_field: str | None
    parent: str | None  # 'county' | 'state' | 'nation' | None


@dataclass(frozen=True)
class GeoRow:
    geo_id: str
    summary_level: str
    name: str
    state_fips: str | None
    county_fips: str | None
    parent_geo_id: str | None
    land_area_m2: int | None
    wkb: bytes


def BOUNDARY_FILES(vintage_year: int, state_fips: list[str]) -> list[BoundarySpec]:
    b = BASE.format(y=vintage_year)
    y = vintage_year
    specs = [
        BoundarySpec("010", f"{b}/cb_{y}_us_nation_5m.zip", "GEOID", "NAME", None, None, "ALAND", None),
        BoundarySpec("040", f"{b}/cb_{y}_us_state_500k.zip", "GEOID", "NAME", "STATEFP", None, "ALAND", "nation"),
        BoundarySpec("050", f"{b}/cb_{y}_us_county_500k.zip", "GEOID", "NAMELSAD", "STATEFP", "COUNTYFP", "ALAND", "state"),
        BoundarySpec("310", f"{b}/cb_{y}_us_cbsa_500k.zip", "GEOID", "NAME", None, None, "ALAND", None),
        # ZCTAs are 2020-based; the GENZ{y} folder may not republish them — load_boundaries falls back to GENZ2020.
        BoundarySpec("860", f"{b}/cb_{y}_us_zcta520_500k.zip", "GEOID20", "NAME20", None, None, "ALAND20", None),
    ]
    for st in state_fips:
        specs.append(BoundarySpec("140", f"{b}/cb_{y}_{st}_tract_500k.zip", "GEOID", "NAMELSAD", "STATEFP", "COUNTYFP", "ALAND", "county"))
        specs.append(BoundarySpec("160", f"{b}/cb_{y}_{st}_place_500k.zip", "GEOID", "NAME", "STATEFP", None, "ALAND", "state"))
    return specs


def _parent(spec: BoundarySpec, state: str | None, county: str | None) -> str | None:
    if spec.parent == "county" and state and county:
        return state + county
    if spec.parent == "state":
        return state
    if spec.parent == "nation":
        return "1"
    return None


def parse_shapefile(zip_bytes: bytes, spec: BoundarySpec) -> list[GeoRow]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = {n.rsplit(".", 1)[1].lower(): n for n in z.namelist() if n.lower().endswith((".shp", ".shx", ".dbf"))}
        reader = shapefile.Reader(shp=io.BytesIO(z.read(names["shp"])), shx=io.BytesIO(z.read(names["shx"])), dbf=io.BytesIO(z.read(names["dbf"])))
    rows: list[GeoRow] = []
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        geom = shape(sr.shape.__geo_interface__)
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])
        state = str(rec[spec.state_field]) if spec.state_field else None
        county = str(rec[spec.county_field]) if spec.county_field else None
        land = rec.get(spec.land_field) if spec.land_field else None
        rows.append(GeoRow(
            geo_id=str(rec[spec.geoid_field]), summary_level=spec.summary_level, name=str(rec[spec.name_field]),
            state_fips=state, county_fips=county, parent_geo_id=_parent(spec, state, county),
            land_area_m2=int(land) if land not in (None, "") else None, wkb=geom.wkb,
        ))
    return rows


UPSERT = """
INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, land_area_m2, geom, centroid)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, ST_Multi(ST_GeomFromWKB(%s, 4269)), ST_Centroid(ST_GeomFromWKB(%s, 4269)))
ON CONFLICT (geo_id, summary_level, vintage) DO UPDATE SET
  name = EXCLUDED.name, state_fips = EXCLUDED.state_fips, county_fips = EXCLUDED.county_fips,
  parent_geo_id = EXCLUDED.parent_geo_id, land_area_m2 = EXCLUDED.land_area_m2, geom = EXCLUDED.geom, centroid = EXCLUDED.centroid
"""


def upsert_geo(conn, rows: list[GeoRow], vintage: str) -> int:
    import psycopg2
    with conn.cursor() as cur:
        cur.executemany(UPSERT, [(r.geo_id, r.summary_level, vintage, r.name, r.state_fips, r.county_fips, r.parent_geo_id,
                                  r.land_area_m2, psycopg2.Binary(r.wkb), psycopg2.Binary(r.wkb)) for r in rows])
    return len(rows)


def load_boundaries(conn, http: httpx.Client, states: list[str], vintage: str = "2023") -> dict[str, int]:
    """Downloads and upserts every boundary file. ZCTAs (national file) are kept only
    when their centroid falls inside a market state, to bound table size."""
    counts: dict[str, int] = {}
    state_geoms = None
    for spec in BOUNDARY_FILES(int(vintage), states):
        resp = http.get(spec.url, timeout=httpx.Timeout(connect=15.0, read=300.0, write=15.0, pool=15.0))
        if resp.status_code == 404 and spec.summary_level == "860":
            resp = http.get(spec.url.replace(f"GENZ{vintage}", "GENZ2020").replace(f"cb_{vintage}_", "cb_2020_"), timeout=httpx.Timeout(connect=15.0, read=300.0, write=15.0, pool=15.0))
        body = resp.raise_for_status().content
        rows = parse_shapefile(body, spec)
        if spec.summary_level == "040":
            from shapely import wkb as _wkb
            state_geoms = [_wkb.loads(r.wkb) for r in rows if r.geo_id in states]
        if spec.summary_level == "860" and state_geoms:
            from shapely import wkb as _wkb
            from shapely.ops import unary_union
            market = unary_union(state_geoms)
            rows = [r for r in rows if market.contains(_wkb.loads(r.wkb).centroid)]
        counts[f"{spec.summary_level}:{spec.url.rsplit('/', 1)[1]}"] = upsert_geo(conn, rows, vintage)
    return counts
```

Run: `poetry run pytest tests/census/test_tiger.py -q` → 3 passed.

- [ ] **Step 3: Operator CLI** — `scripts/census_load.py` (extended by later tasks)

```python
#!/usr/bin/env python3
"""Operator entry points for the market-data layer. Runs inside the worker image
(`railway run --service worker -- python scripts/census_load.py …`) or locally
against docker-compose. Every subcommand is idempotent."""
from __future__ import annotations

import argparse
import os
import sys

import httpx
import psycopg2


def _conn():
    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    c = psycopg2.connect(dsn)
    c.autocommit = True
    return c


def cmd_tiger(args) -> int:
    from app.census.tiger import load_boundaries
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
        states = [r[0] for r in cur.fetchall()]
    with httpx.Client(headers={"User-Agent": "PracticeMatch (VIN Foundation)"}) as http:
        counts = load_boundaries(conn, http, states, args.vintage)
    for k, n in counts.items():
        print(f"  {k}: {n} rows")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="census_load")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tiger", help="load boundary files for market_state states")
    t.add_argument("--vintage", default="2023")
    t.set_defaults(fn=cmd_tiger)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
```

Smoke it against local compose (downloads ~150 MB once): `poetry run python scripts/census_load.py tiger` → prints row counts per file; then `psql "$DATABASE_URL" -c "SELECT summary_level, count(*) FROM geo_area GROUP BY 1 ORDER BY 1"` → `010:1, 040:56, 050:3235, 140:≈24000, 160:≈4000, 310:≈930, 860:≈4500`.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(census): TIGER boundary ingest into geo_area (pyshp + shapely, no GDAL) and census_load CLI

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/census-data-layer && git push production feat/census-data-layer
```

---

### Task A5: ACS loads (detailed, subject, prior baseline) with the ingest-run ledger

**Files:**
- Create: `app/census/ingest.py`, `app/census/acs.py`, `tests/census/test_ingest.py`, `tests/census/test_acs.py`, `tests/census/fixtures/acs_tract_48.json`
- Modify: `scripts/census_load.py` (`acs` subcommand)

**Interfaces:**
- Produces: `ingest.start(conn, dataset_key, vintage) -> int`; `ingest.finish(conn, run_id, status, *, rows=0, requests=0, raw_uri=None, error=None)`; context manager `ingest.run(conn, dataset_key, vintage)` yielding `Run(id, rows, requests, raw_uri)` — commits data on success, rolls back and records `failed` (any exception) or `aborted` (`VariableMissing`) otherwise.
- `acs.VARIABLES: dict[str, list[str]]` (per dataset key, spec §4); `acs.GEOGRAPHIES(states) -> list[Geo(summary_level, for_, in_)]`; `acs.geoid(row, summary_level) -> str`; `acs.to_measures(rows, variables, summary_level) -> list[Measure(geo_id, summary_level, variable, estimate, moe)]`; `acs.load(conn, client_factory, dataset_key, states) -> int` (rows written).

- [ ] **Step 1: Failing tests**

`tests/census/test_ingest.py`:
```python
import pytest

from app.census import ingest
from app.census.client import VariableMissing


def _run_row(conn, run_id):
    with conn.cursor() as cur:
        cur.execute("SELECT status, rows_written, request_count, error_detail, finished_at IS NOT NULL FROM ingest_run WHERE id=%s", (run_id,))
        return cur.fetchone()


def test_success_commits_and_records_counts(conn):
    with ingest.run(conn, "acs5", "2019–2023") as run:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO acs_measure VALUES ('1','010','2019–2023','B01003_001E', 331000000, 0, %s)", (run.id,))
        run.rows += 1
        run.requests = 1
    assert _run_row(conn, run.id) == ("succeeded", 1, 1, None, True)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM acs_measure"); assert cur.fetchone()[0] == 1


def test_failure_rolls_back_data_and_records_error(conn):
    with pytest.raises(RuntimeError):
        with ingest.run(conn, "acs5", "2019–2023") as run:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO acs_measure VALUES ('1','010','2019–2023','B01003_001E', 1, 0, %s)", (run.id,))
            raise RuntimeError("boom")
    status, rows, _, err, _ = _run_row(conn, run.id)
    assert status == "failed" and "boom" in err
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM acs_measure"); assert cur.fetchone()[0] == 0


def test_variable_drift_is_recorded_as_aborted(conn):
    with pytest.raises(VariableMissing):
        with ingest.run(conn, "acs5", "2019–2023"):
            raise VariableMissing(["B19013_001E"])
    with conn.cursor() as cur:
        cur.execute("SELECT status, error_detail FROM ingest_run ORDER BY id DESC LIMIT 1")
        status, err = cur.fetchone()
    assert status == "aborted" and "B19013_001E" in err
```

`tests/census/fixtures/acs_tract_48.json` (Census table shape, two tracts, one sentinel):
```json
[["NAME","B01003_001E","B01003_001M","B11001_001E","B11001_001M","B19013_001E","B19013_001M","B19301_001E","B01002_001E","B25003_002E","B25001_001E","state","county","tract"],
 ["Census Tract 1.01; Travis County; Texas","4321","210","1500","95","118400","9100","52000","36.2","900","1600","48","453","000101"],
 ["Census Tract 1.02; Travis County; Texas","-666666666","-555555555","1200","80","98000","12000","44000","41.0","700","1300","48","453","000102"]]
```

`tests/census/test_acs.py`:
```python
import json
from pathlib import Path

import httpx

from app.census import acs
from app.census.client import CensusClient
from app.census.registry import load as load_registry

FIX = json.loads((Path(__file__).parent / "fixtures" / "acs_tract_48.json").read_text())


def test_variable_lists_are_the_spec_map():
    assert acs.VARIABLES["acs5"] == ["B01003_001E", "B01003_001M", "B11001_001E", "B11001_001M", "B19013_001E", "B19013_001M",
                                     "B19301_001E", "B01002_001E", "B25003_002E", "B25001_001E"]
    assert acs.VARIABLES["acs5_subject"] == ["S1501_C02_015E"]
    assert acs.VARIABLES["acs5_prior"] == ["B01003_001E", "B01003_001M"]


def test_geographies_cover_spec_levels_for_each_state_plus_cbsa_and_nation():
    g = acs.GEOGRAPHIES(["48", "06"])
    levels = [(x.summary_level, x.for_, x.in_) for x in g]
    assert ("140", "tract:*", "state:48") in levels and ("140", "tract:*", "state:06") in levels
    assert ("160", "place:*", "state:48") in levels
    assert ("050", "county:*", "state:48") in levels
    assert ("040", "state:48", None) in levels
    assert ("310", "metropolitan statistical area/micropolitan statistical area:*", None) in levels
    assert ("010", "us:1", None) in levels
    assert levels.count(("310", "metropolitan statistical area/micropolitan statistical area:*", None)) == 1


def test_geoid_assembly_per_level():
    assert acs.geoid({"state": "48", "county": "453", "tract": "000101"}, "140") == "48453000101"
    assert acs.geoid({"state": "48", "place": "05000"}, "160") == "4805000"
    assert acs.geoid({"state": "48", "county": "453"}, "050") == "48453"
    assert acs.geoid({"state": "48"}, "040") == "48"
    assert acs.geoid({"metropolitan statistical area/micropolitan statistical area": "12420"}, "310") == "12420"
    assert acs.geoid({"us": "1"}, "010") == "1"


def test_to_measures_pairs_estimates_with_moe_and_keeps_nulls():
    header, *rows = FIX
    dicts = [dict(zip(header, r)) for r in rows]
    dicts[1]["B01003_001E"] = None; dicts[1]["B01003_001M"] = None  # what the client's sentinel pass produces
    ms = {(m.geo_id, m.variable): m for m in acs.to_measures(dicts, acs.VARIABLES["acs5"], "140")}
    assert ms[("48453000101", "B01003_001E")].estimate == 4321 and ms[("48453000101", "B01003_001E")].moe == 210
    assert ms[("48453000101", "B19013_001E")].moe == 9100
    assert ms[("48453000101", "B19301_001E")].moe is None          # no MOE requested for per-capita income
    assert ms[("48453000102", "B01003_001E")].estimate is None and ms[("48453000102", "B01003_001E")].moe is None
    assert ("48453000101", "B01003_001M") not in ms                 # MOE columns are folded, not stored as variables


def test_load_writes_rows_and_a_succeeded_run(conn):
    def handler(r: httpx.Request):
        if "for=tract" in str(r.url):
            return httpx.Response(200, json=FIX)
        # every other geography: one row with the same columns, minimal
        hdr = FIX[0][:-3] + (["state", "county"] if "county:*" in str(r.url) else ["state", "place"] if "place" in str(r.url)
                              else ["state"] if "for=state" in str(r.url) else ["metropolitan statistical area/micropolitan statistical area"] if "metropolitan" in str(r.url) else ["us"])
        vals = ["X", "10", "1", "5", "1", "50000", "100", "30000", "40.0", "3", "6"] + (["48", "001"] if len(hdr) == 13 and hdr[-1] == "county" else ["48", "00001"] if hdr[-1] == "place" else ["48"] if hdr[-1] == "state" else ["12420"] if "metropolitan" in hdr[-1] else ["1"])
        return httpx.Response(200, json=[hdr, vals])
    reg = load_registry(conn)
    factory = lambda ds: CensusClient("K", ds, None, transport=httpx.MockTransport(handler))
    written = acs.load(conn, factory, "acs5", ["48"])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM acs_measure WHERE summary_level='140' AND vintage=%s", (reg["acs5"].vintage,))
        assert cur.fetchone()[0] == 2 * 8  # two tracts × eight estimate variables
        cur.execute("SELECT estimate, moe FROM acs_measure WHERE geo_id='48453000102' AND variable='B01003_001E'")
        assert cur.fetchone() == (None, None)
        cur.execute("SELECT status, rows_written FROM ingest_run WHERE dataset_key='acs5' ORDER BY id DESC LIMIT 1")
        status, rows = cur.fetchone()
    assert status == "succeeded" and rows == written > 16
```

Run: `poetry run pytest tests/census/test_ingest.py tests/census/test_acs.py -q` → FAIL (modules missing).

- [ ] **Step 2: Implement `ingest.py`**

```python
"""ingest_run lifecycle (spec §13). Data written inside `run()` is one transaction:
committed on success, rolled back on any failure, and the run row records the
outcome. VariableMissing is recorded as 'aborted' — a schema drift, not an outage."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

from app.census.client import VariableMissing


@dataclass
class Run:
    id: int
    rows: int = 0
    requests: int = 0
    raw_uri: str | None = None
    notes: list[str] = field(default_factory=list)


def start(conn, dataset_key: str, vintage: str) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO ingest_run (dataset_key, vintage, started_at, status) VALUES (%s, %s, now(), 'running') RETURNING id",
                    (dataset_key, vintage))
        return cur.fetchone()[0]


def finish(conn, run_id: int, status: str, *, rows: int = 0, requests: int = 0, raw_uri: str | None = None, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute("""UPDATE ingest_run SET finished_at = now(), status = %s, rows_written = %s, request_count = %s,
                       raw_payload_uri = %s, error_detail = %s WHERE id = %s""",
                    (status, rows, requests, raw_uri, error, run_id))


@contextmanager
def run(conn, dataset_key: str, vintage: str):
    was_autocommit = conn.autocommit
    conn.autocommit = True
    run_id = start(conn, dataset_key, vintage)          # visible immediately as 'running'
    r = Run(id=run_id)
    conn.autocommit = False                              # data writes below are one transaction
    try:
        yield r
        conn.commit()
        conn.autocommit = True
        finish(conn, run_id, "succeeded", rows=r.rows, requests=r.requests, raw_uri=r.raw_uri)
    except BaseException as exc:
        conn.rollback()
        conn.autocommit = True
        status = "aborted" if isinstance(exc, VariableMissing) else "failed"
        finish(conn, run_id, status, rows=0, requests=r.requests, raw_uri=r.raw_uri, error=f"{type(exc).__name__}: {exc}"[:2000])
        raise
    finally:
        conn.autocommit = was_autocommit
```

- [ ] **Step 3: Implement `acs.py`**

```python
"""ACS 5-year loads (spec §2 acs5 / acs5_subject / acs5_prior, §4 variables, §6 levels).
Long format: one acs_measure row per (geo, variable); each _E carries its _M as moe."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.census import ingest
from app.census.registry import load as load_registry

VARIABLES: dict[str, list[str]] = {
    "acs5": ["B01003_001E", "B01003_001M", "B11001_001E", "B11001_001M", "B19013_001E", "B19013_001M",
             "B19301_001E", "B01002_001E", "B25003_002E", "B25001_001E"],
    "acs5_subject": ["S1501_C02_015E"],
    "acs5_prior": ["B01003_001E", "B01003_001M"],
}

CBSA_COL = "metropolitan statistical area/micropolitan statistical area"


@dataclass(frozen=True)
class Geo:
    summary_level: str
    for_: str
    in_: str | None


@dataclass(frozen=True)
class Measure:
    geo_id: str
    summary_level: str
    variable: str
    estimate: Decimal | None
    moe: Decimal | None


def GEOGRAPHIES(states: list[str]) -> list[Geo]:
    geos: list[Geo] = []
    for st in states:
        geos += [Geo("140", "tract:*", f"state:{st}"), Geo("160", "place:*", f"state:{st}"),
                 Geo("050", "county:*", f"state:{st}"), Geo("040", f"state:{st}", None)]
    geos += [Geo("310", f"{CBSA_COL}:*", None), Geo("010", "us:1", None)]
    return geos


def geoid(row: dict, summary_level: str) -> str:
    match summary_level:
        case "140": return row["state"] + row["county"] + row["tract"]
        case "160": return row["state"] + row["place"]
        case "050": return row["state"] + row["county"]
        case "040": return row["state"]
        case "310": return row[CBSA_COL]
        case "010": return row["us"]
    raise ValueError(summary_level)


def _num(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def to_measures(rows: list[dict], variables: list[str], summary_level: str) -> list[Measure]:
    estimates = [v for v in variables if v.endswith("E")]
    out: list[Measure] = []
    for row in rows:
        gid = geoid(row, summary_level)
        for var in estimates:
            moe_var = var[:-1] + "M"
            out.append(Measure(gid, summary_level, var, _num(row.get(var)),
                               _num(row.get(moe_var)) if moe_var in variables else None))
    return out


UPSERT = """
INSERT INTO acs_measure (geo_id, summary_level, vintage, variable, estimate, moe, ingest_run_id)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (geo_id, summary_level, vintage, variable) DO UPDATE
SET estimate = EXCLUDED.estimate, moe = EXCLUDED.moe, ingest_run_id = EXCLUDED.ingest_run_id
"""


def load(conn, client_factory, dataset_key: str, states: list[str]) -> int:
    ds = load_registry(conn)[dataset_key]
    if not ds.cleared:
        raise PermissionError(f"{dataset_key} is {ds.license_status}; loads are refused (spec §1 licensing gate)")
    client = client_factory(ds)
    variables = VARIABLES[dataset_key]
    with ingest.run(conn, dataset_key, ds.vintage) as run:
        for geo in GEOGRAPHIES(states):
            rows = client.fetch_table(client.build_url(["NAME", *variables], geo.for_, geo.in_))
            client.validate_variables(rows, variables)
            measures = to_measures(rows, variables, geo.summary_level)
            with conn.cursor() as cur:
                cur.executemany(UPSERT, [(m.geo_id, m.summary_level, ds.vintage, m.variable, m.estimate, m.moe, run.id) for m in measures])
            run.rows += len(measures)
            run.requests = client.request_count
        return run.rows
```

Run: `poetry run pytest tests/census -q` → all pass.

- [ ] **Step 4: CLI** — add to `scripts/census_load.py`:

```python
def cmd_acs(args) -> int:
    from app.census import acs
    from app.census.client import CensusClient, require_key
    from app.census.storage import ObjectStore
    from app.config import settings
    from app.version import VERSION
    key = require_key()
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips FROM market_state ORDER BY 1"); states = [r[0] for r in cur.fetchall()]
    archive = ObjectStore.from_settings(settings)
    factory = lambda ds: CensusClient(key, ds, archive, version=VERSION, contact=settings.census_contact_email)
    for ds_key in args.dataset:
        n = acs.load(conn, factory, ds_key, states)
        print(f"  {ds_key}: {n} measures")
    return 0
# in main():
a = sub.add_parser("acs", help="load ACS datasets for market_state states")
a.add_argument("--dataset", nargs="+", default=["acs5", "acs5_subject", "acs5_prior"])
a.set_defaults(fn=cmd_acs)
```

Smoke against local compose with the real key exported in your shell only (`CENSUS_API_KEY=… poetry run python scripts/census_load.py acs`) → three `succeeded` runs; `SELECT dataset_key, status, rows_written FROM ingest_run` shows counts (acs5 ≈ 24 k tracts × 8 + places + counties + states + CBSAs + 1).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(census): ACS detailed/subject/prior loads with transactional ingest_run ledger and drift abort

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/census-data-layer && git push production feat/census-data-layer
```

---

### Task A6: Industry loads — CBP (541940 + adjacent), ZBP (ZIP-level competition, D11), QWI (5419, 20 quarters), BDS (54)

**Files:**
- Create: `migrations/008_zbp.sql`, `app/census/cbp.py`, `app/census/zbp.py`, `app/census/qwi.py`, `app/census/bds.py`, `tests/census/test_industry.py`
- Modify: `scripts/census_load.py` (`cbp`, `qwi`, `bds` subcommands)

**Interfaces:**
- `cbp.NAICS = ["541940", "812910", "459910"]`; `cbp.NAICS_ALIASES = {("NAICS2017", "459910"): "453910"}` (NAICS 2022's Pet & Pet Supplies Retailers was 453910 under NAICS 2017 — the 2022 CBP release still uses NAICS2017); `cbp.load(conn, client_factory, states) -> int`.
- `qwi.load(conn, client_factory, states, *, year, quarter) -> int` and `qwi.latest_available(client, state) -> tuple[int, int]`; `qwi.trim(conn, keep=20)`.
- `bds.load(conn, client_factory, states, *, year) -> int`.

- [ ] **Step 1: Failing tests**

`tests/census/test_industry.py`:
```python
import httpx

from app.census import bds, cbp, qwi
from app.census.client import CensusClient


def factory_for(handler):
    return lambda ds: CensusClient("K", ds, None, transport=httpx.MockTransport(handler))


def test_cbp_uses_registry_naics_param_and_alias_and_stores_flags_verbatim(conn):
    urls = []
    def handler(r):
        urls.append(str(r.url))
        code = r.url.params["NAICS2017"]
        return httpx.Response(200, json=[["NAME", "ESTAB", "EMP", "PAYANN", "EMP_F", "PAYANN_F", "state", "county", "NAICS2017"],
                                         ["Travis County, Texas", "12", "410", "38500", None, None, "48", "453", code],
                                         ["Hays County, Texas", "3", "0", "0", "D", "D", "48", "209", code]])
    written = cbp.load(conn, factory_for(handler), ["48"])
    assert written == 6  # 2 counties × 3 NAICS codes
    assert all("NAICS2017=" in u for u in urls) and any("NAICS2017=453910" in u for u in urls) and not any("459910" in u for u in urls)
    with conn.cursor() as cur:
        cur.execute("SELECT naics_code, establishments, employment, annual_payroll_k, flag FROM cbp_industry WHERE geo_id='48209' ORDER BY naics_code")
        rows = cur.fetchall()
    # stored under the spec's code (459910) even though requested as the 2017 alias
    assert [r[0] for r in rows] == ["459910", "541940", "812910"]
    assert rows[1] == ("541940", 3, None, None, "EMP_F=D;PAYANN_F=D")   # Census suppressed → NULL, flag kept verbatim (§14)
    with conn.cursor() as cur:
        cur.execute("SELECT establishments, employment, annual_payroll_k, flag FROM cbp_industry WHERE geo_id='48453' AND naics_code='541940'")
        assert cur.fetchone() == (12, 410, 38500, None)


def test_qwi_loads_a_quarter_and_trims_to_twenty(conn):
    def handler(r):
        y, q = r.url.params["year"], r.url.params["quarter"]
        return httpx.Response(200, json=[["EarnBeg", "Emp", "HirA", "state", "county", "year", "quarter", "industry"],
                                         ["6120", "4200", "310", "48", "453", y, q, "5419"]])
    f = factory_for(handler)
    for i in range(22):  # 22 quarters back from 2024Q4
        y, q = divmod((2024 * 4 + 3) - i, 4)
        qwi.load(conn, f, ["48"], year=y, quarter=q + 1)
    qwi.trim(conn, keep=20)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), min(year*10+quarter), max(year*10+quarter) FROM qwi_measure WHERE geo_id='48453'")
        n, lo, hi = cur.fetchone()
    assert n == 20 and hi == 20244 and lo == 20201


def test_qwi_latest_available_walks_back_from_404s():
    def handler(r):
        y, q = int(r.url.params["year"]), int(r.url.params["quarter"])
        return httpx.Response(200, json=[["Emp", "state"], ["1", "48"]]) if (y, q) <= (2024, 4) else httpx.Response(404)
    from app.census.registry import Dataset
    ds = Dataset("qwi", "QWI", "timeseries/qwi/sa", "https://api.census.gov/data", "latest quarter", None, "Quarterly", "cleared", "Public domain", None, "x", None, None)
    client = CensusClient("K", ds, None, transport=httpx.MockTransport(handler))
    assert qwi.latest_available(client, "48", today=(2026, 3)) == (2024, 4)


def test_bds_state_rows(conn):
    def handler(r):
        return httpx.Response(200, json=[["FIRM", "ESTAB_ENTRY", "state", "YEAR", "NAICS"], ["18300", "2100", "48", "2022", "54"]])
    assert bds.load(conn, factory_for(handler), ["48"], year=2022) == 1
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id, summary_level, vintage, naics_code, firms, estab_entry FROM bds_measure")
        assert cur.fetchone() == ("48", "040", "2022", "54", 18300, 2100)
```

Run → FAIL (modules missing).

- [ ] **Step 2: Implement**

`app/census/cbp.py`:
```python
"""County Business Patterns (spec §2 cbp, §5 NAICS). County granularity only.
The NAICS parameter name comes from the registry; NAICS-2017 releases need an
alias for the spec's 2022-vintage code 459910."""
from __future__ import annotations

from app.census import ingest
from app.census.registry import load as load_registry

NAICS = ["541940", "812910", "459910"]
NAICS_ALIASES = {("NAICS2017", "459910"): "453910"}
VARS = ["ESTAB", "EMP", "PAYANN", "EMP_F", "PAYANN_F"]

UPSERT = """
INSERT INTO cbp_industry (geo_id, summary_level, vintage, naics_code, establishments, employment, annual_payroll_k, flag, ingest_run_id)
VALUES (%s, '050', %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (geo_id, summary_level, vintage, naics_code) DO UPDATE SET establishments = EXCLUDED.establishments,
  employment = EXCLUDED.employment, annual_payroll_k = EXCLUDED.annual_payroll_k, flag = EXCLUDED.flag, ingest_run_id = EXCLUDED.ingest_run_id
"""


def _int(v):
    return int(v) if v not in (None, "") else None


def _flags(row) -> str | None:
    parts = [f"{k}={row[k]}" for k in ("EMP_F", "PAYANN_F") if row.get(k)]
    return ";".join(parts) or None


def load(conn, client_factory, states: list[str]) -> int:
    ds = load_registry(conn)["cbp"]
    if not ds.cleared:
        raise PermissionError("cbp is not cleared")
    param = ds.naics_param or "NAICS2017"
    client = client_factory(ds)
    with ingest.run(conn, "cbp", ds.vintage) as run:
        for code in NAICS:
            requested = NAICS_ALIASES.get((param, code), code)
            for st in states:
                rows = client.fetch_table(client.build_url(["NAME", *VARS], "county:*", f"state:{st}", {param: requested}))
                client.validate_variables(rows, ["ESTAB", "EMP", "PAYANN"])
                payload = []
                for r in rows:
                    flags = _flags(r)
                    # Census suppression flag 'D' means the cell was withheld → NULL, never 0 (spec §14).
                    emp = None if (r.get("EMP_F") == "D") else _int(r.get("EMP"))
                    pay = None if (r.get("PAYANN_F") == "D") else _int(r.get("PAYANN"))
                    payload.append((r["state"] + r["county"], ds.vintage, code, _int(r.get("ESTAB")), emp, pay, flags, run.id))
                with conn.cursor() as cur:
                    cur.executemany(UPSERT, payload)
                run.rows += len(payload)
                run.requests = client.request_count
        return run.rows
```

`migrations/008_zbp.sql` (D11):
```sql
-- ZIP Code Business Patterns — the community-level competition source. ZIP codes are stored as
-- summary_level '860' (ZCTA) geo_ids; the ZIP≈ZCTA approximation is labelled in the UI.
CREATE TABLE zbp_industry (
  geo_id text NOT NULL,            -- 5-digit ZIP
  summary_level char(3) NOT NULL DEFAULT '860',
  vintage text NOT NULL,
  naics_code text NOT NULL,        -- '541940' | '812910' | '459910'
  establishments integer,
  flag text,
  ingest_run_id bigint NOT NULL REFERENCES ingest_run(id),
  PRIMARY KEY (geo_id, summary_level, vintage, naics_code)
);
```

`app/census/zbp.py`:
```python
"""ZIP Code Business Patterns (plan D11). Establishment counts per ZIP for the spec's NAICS codes;
the same NAICS-2017 alias as CBP applies. Employment/payroll are mostly suppressed at ZIP level and
are not requested — ESTAB is what the competition layer needs."""
from __future__ import annotations

from app.census import ingest
from app.census.cbp import NAICS, NAICS_ALIASES
from app.census.registry import load as load_registry

VARS = ["ESTAB"]

UPSERT = """
INSERT INTO zbp_industry (geo_id, summary_level, vintage, naics_code, establishments, flag, ingest_run_id)
VALUES (%s, '860', %s, %s, %s, %s, %s)
ON CONFLICT (geo_id, summary_level, vintage, naics_code) DO UPDATE SET establishments = EXCLUDED.establishments, flag = EXCLUDED.flag, ingest_run_id = EXCLUDED.ingest_run_id
"""


def load(conn, client_factory, states: list[str]) -> int:
    ds = load_registry(conn)["zbp"]
    if not ds.cleared:
        raise PermissionError("zbp is not cleared")
    param = ds.naics_param or "NAICS2017"
    client = client_factory(ds)
    with ingest.run(conn, "zbp", ds.vintage) as run:
        for code in NAICS:
            requested = NAICS_ALIASES.get((param, code), code)
            for st in states:
                # ZBP geography is zipcode; 'in=state' is supported for filtering to a state's ZIPs.
                rows = client.fetch_table(client.build_url(VARS, "zipcode:*", f"state:{st}", {param: requested}))
                client.validate_variables(rows, VARS)
                with conn.cursor() as cur:
                    cur.executemany(UPSERT, [(r["zipcode"], ds.vintage, code, int(r["ESTAB"]) if r.get("ESTAB") not in (None, "") else None, r.get("ESTAB_F"), run.id) for r in rows])
                run.rows += len(rows)
                run.requests = client.request_count
        return run.rows
```

Test (append to `tests/census/test_industry.py`):
```python
def test_zbp_loads_zip_establishments_with_alias(conn):
    from app.census import zbp
    urls = []
    def handler(r):
        urls.append(str(r.url))
        code = r.url.params["NAICS2017"]
        return httpx.Response(200, json=[["ESTAB", "state", "zipcode", "NAICS2017"], ["7", "48", "78613", code], ["2", "48", "78664", code]])
    assert zbp.load(conn, factory_for(handler), ["48"]) == 6
    assert any("for=zipcode:*" in u and "NAICS2017=453910" in u for u in urls)
    with conn.cursor() as cur:
        cur.execute("SELECT establishments FROM zbp_industry WHERE geo_id='78613' AND naics_code='541940'")
        assert cur.fetchone() == (7,)
```
If `2022/zbp` returns 404 for the `zipcode:*` + `in=state` form, use `for=zipcode:*` without `in` and filter rows by the ZIP→state map in `geo_area` (860 rows carry no state; use ZCTA centroid containment) — record which form worked in the registry `notes`.

`app/census/qwi.py`:
```python
"""Quarterly Workforce Indicators (spec §2 qwi, §5 industry 5419, §9 keep 20 quarters)."""
from __future__ import annotations

from app.census import ingest
from app.census.client import CensusHTTPError
from app.census.registry import load as load_registry

VARS = ["EarnBeg", "Emp", "HirA"]
EXTRA = {"industry": "5419", "ownercode": "A05", "seasonadj": "U"}

UPSERT = """
INSERT INTO qwi_measure (geo_id, summary_level, naics_code, year, quarter, avg_monthly_earnings, sector_employment, sector_hires, ingest_run_id)
VALUES (%s, '050', '5419', %s, %s, %s, %s, %s, %s)
ON CONFLICT (geo_id, summary_level, naics_code, year, quarter) DO UPDATE SET avg_monthly_earnings = EXCLUDED.avg_monthly_earnings,
  sector_employment = EXCLUDED.sector_employment, sector_hires = EXCLUDED.sector_hires, ingest_run_id = EXCLUDED.ingest_run_id
"""


def _int(v):
    return int(float(v)) if v not in (None, "") else None


def latest_available(client, state: str, *, today: tuple[int, int]) -> tuple[int, int]:
    """QWI lags ~3 quarters; walk back from the current quarter until a table exists."""
    y, q = today
    for _ in range(12):
        try:
            client.fetch_table(client.build_url(["Emp"], f"state:{state}", None, {"year": str(y), "quarter": str(q), **EXTRA}))
            return (y, q)
        except CensusHTTPError as exc:
            if exc.status not in (404, 400):
                raise
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    raise RuntimeError("no QWI quarter available in the last 12")


def load(conn, client_factory, states: list[str], *, year: int, quarter: int) -> int:
    ds = load_registry(conn)["qwi"]
    if not ds.cleared:
        raise PermissionError("qwi is not cleared")
    client = client_factory(ds)
    with ingest.run(conn, "qwi", f"{year}Q{quarter}") as run:
        for st in states:
            rows = client.fetch_table(client.build_url(VARS, "county:*", f"state:{st}", {"year": str(year), "quarter": str(quarter), **EXTRA}))
            client.validate_variables(rows, VARS)
            with conn.cursor() as cur:
                cur.executemany(UPSERT, [(r["state"] + r["county"], year, quarter, _int(r.get("EarnBeg")), _int(r.get("Emp")), _int(r.get("HirA")), run.id) for r in rows])
            run.rows += len(rows)
            run.requests = client.request_count
        return run.rows


def trim(conn, keep: int = 20) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM qwi_measure q USING (
              SELECT geo_id, summary_level, naics_code, year, quarter,
                     row_number() OVER (PARTITION BY geo_id, summary_level, naics_code ORDER BY year DESC, quarter DESC) AS rn
              FROM qwi_measure) x
            WHERE q.geo_id = x.geo_id AND q.summary_level = x.summary_level AND q.naics_code = x.naics_code
              AND q.year = x.year AND q.quarter = x.quarter AND x.rn > %s""", (keep,))
        return cur.rowcount
```

`app/census/bds.py`:
```python
"""Business Dynamics Statistics (spec §2 bds, §4 FIRM/ESTAB_ENTRY, §5 sector 54). State level."""
from __future__ import annotations

from app.census import ingest
from app.census.registry import load as load_registry

VARS = ["FIRM", "ESTAB_ENTRY"]

UPSERT = """
INSERT INTO bds_measure (geo_id, summary_level, vintage, naics_code, firms, estab_entry, ingest_run_id)
VALUES (%s, '040', %s, '54', %s, %s, %s)
ON CONFLICT (geo_id, summary_level, vintage, naics_code) DO UPDATE SET firms = EXCLUDED.firms, estab_entry = EXCLUDED.estab_entry, ingest_run_id = EXCLUDED.ingest_run_id
"""


def _int(v):
    return int(v) if v not in (None, "") else None


def load(conn, client_factory, states: list[str], *, year: int) -> int:
    ds = load_registry(conn)["bds"]
    if not ds.cleared:
        raise PermissionError("bds is not cleared")
    client = client_factory(ds)
    with ingest.run(conn, "bds", str(year)) as run:
        for st in states:
            rows = client.fetch_table(client.build_url(VARS, f"state:{st}", None, {"YEAR": str(year), "NAICS": "54"}))
            client.validate_variables(rows, VARS)
            with conn.cursor() as cur:
                cur.executemany(UPSERT, [(r["state"], str(year), _int(r.get("FIRM")), _int(r.get("ESTAB_ENTRY")), run.id) for r in rows])
            run.rows += len(rows)
            run.requests = client.request_count
        return run.rows
```

Run: `poetry run pytest tests/census -q` → all pass.

- [ ] **Step 3: CLI subcommands** (same pattern as `cmd_acs`; add `zbp`; `qwi` resolves `latest_available(client, states[0], today=(now.year, (now.month-1)//3+1))` when `--year/--quarter` are omitted, then calls `trim`; `bds --year 2022`). Smoke locally with the real key; expect `succeeded` rows in `ingest_run` for `cbp`, `qwi`, `bds`.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(census): CBP (with NAICS-2017 alias), ZBP zip-level competition, QWI (20-quarter window), BDS loads

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/census-data-layer && git push production feat/census-data-layer
```

---

### Task A7: Vintage QA diff and activation

**Files:**
- Create: `app/census/vintage.py`, `tests/census/test_vintage.py`
- Modify: `scripts/census_load.py` (`activate` subcommand)

**Interfaces:**
- `vintage.Report(dataset_key, vintage, prior_vintage, rows_new, rows_prior, ratio, last_run_status)`; `vintage.qa(conn, dataset_key, vintage) -> Report`; `vintage.activate(conn, dataset_key, vintage, by, *, force=False) -> Report` (raises `ActivationRefused` unless the latest run for that vintage `succeeded` and `0.8 <= ratio <= 1.25` when a prior vintage exists); `vintage.active(conn) -> dict[str, str]`.

- [ ] **Step 1: Failing tests**

```python
import pytest

from app.census import ingest, vintage


def _seed(conn, ds, vint, n, status="succeeded"):
    with ingest.run(conn, ds, vint) as run:
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO acs_measure VALUES (%s,'140',%s,'B01003_001E',1,0,%s)", [(f"g{i}", vint, run.id) for i in range(n)])
        run.rows = n
        if status == "failed":
            raise RuntimeError("seeded failure")


def test_activation_requires_a_succeeded_run(conn):
    with pytest.raises(RuntimeError):
        _seed(conn, "acs5", "2019–2023", 5, status="failed")
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5", "2019–2023", by="john")


def test_first_vintage_activates_and_is_readable(conn):
    _seed(conn, "acs5", "2019–2023", 10)
    rep = vintage.activate(conn, "acs5", "2019–2023", by="john")
    assert rep.rows_new == 10 and rep.prior_vintage is None
    assert vintage.active(conn)["acs5"] == "2019–2023"


def test_large_row_swing_is_refused_unless_forced(conn):
    _seed(conn, "acs5", "2019–2023", 100)
    vintage.activate(conn, "acs5", "2019–2023", by="john")
    _seed(conn, "acs5", "2020–2024", 40)   # 60% drop → refused
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5", "2020–2024", by="john")
    assert vintage.active(conn)["acs5"] == "2019–2023"
    rep = vintage.activate(conn, "acs5", "2020–2024", by="john", force=True)
    assert rep.ratio == 0.4 and vintage.active(conn)["acs5"] == "2020–2024"
```

- [ ] **Step 2: Implement**

```python
"""Vintage QA + activation (spec §1 'vintages advance only through a migration',
§9 'loads to a new vintage, runs QA diffs, then flips the active vintage flag')."""
from __future__ import annotations

from dataclasses import dataclass

TABLE_FOR = {"acs5": "acs_measure", "acs5_subject": "acs_measure", "acs5_prior": "acs_measure",
             "cbp": "cbp_industry", "zbp": "zbp_industry", "bds": "bds_measure", "tiger_cb": "geo_area"}
LOW, HIGH = 0.8, 1.25


class ActivationRefused(Exception):
    pass


@dataclass(frozen=True)
class Report:
    dataset_key: str
    vintage: str
    prior_vintage: str | None
    rows_new: int
    rows_prior: int
    ratio: float | None
    last_run_status: str | None


def active(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, vintage FROM active_vintage")
        return dict(cur.fetchall())


def qa(conn, dataset_key: str, vint: str) -> Report:
    table = TABLE_FOR[dataset_key]
    prior = active(conn).get(dataset_key)
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table} WHERE vintage = %s", (vint,))
        rows_new = cur.fetchone()[0]
        rows_prior = 0
        if prior and prior != vint:
            cur.execute(f"SELECT count(*) FROM {table} WHERE vintage = %s", (prior,))
            rows_prior = cur.fetchone()[0]
        cur.execute("SELECT status FROM ingest_run WHERE dataset_key = %s AND vintage = %s ORDER BY id DESC LIMIT 1", (dataset_key, vint))
        row = cur.fetchone()
    ratio = (rows_new / rows_prior) if rows_prior else None
    return Report(dataset_key, vint, prior if prior != vint else None, rows_new, rows_prior, ratio, row[0] if row else None)


def activate(conn, dataset_key: str, vint: str, by: str, *, force: bool = False) -> Report:
    rep = qa(conn, dataset_key, vint)
    if rep.last_run_status != "succeeded":
        raise ActivationRefused(f"latest ingest_run for {dataset_key} {vint} is {rep.last_run_status!r}, not 'succeeded'")
    if rep.ratio is not None and not (LOW <= rep.ratio <= HIGH) and not force:
        raise ActivationRefused(f"row count ratio {rep.ratio:.2f} vs active vintage {rep.prior_vintage} is outside [{LOW}, {HIGH}]; pass force=True after review")
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)
                       ON CONFLICT (dataset_key) DO UPDATE SET vintage = EXCLUDED.vintage, activated_at = now(), activated_by = EXCLUDED.activated_by""",
                    (dataset_key, vint, by))
    return rep
```

CLI: `activate <dataset_key> <vintage> --by <name> [--force]` printing the report. Run tests → pass. Commit: `feat(census): vintage QA diff and guarded activation`.

---

### Task A8: Celery tasks, beat schedule, licence audit

**Files:**
- Create: `app/tasks/census.py`, `migrations/007_license_audit.sql`, `app/census/license.py`, `tests/census/test_tasks.py`, `tests/census/test_license.py`
- Modify: `app/tasks/celery_app.py` (import the task module; beat schedule)

**Interfaces:**
- Tasks (names): `census.load_tiger`, `census.load_acs(dataset_key)`, `census.load_cbp`, `census.load_qwi`, `census.load_bds(year)`, `census.license_audit`. (Phase B adds `census.geocode_listing`, `census.materialize_metrics`, `census.backfill_listing`.)
- Beat: `qwi-quarterly` (15th of Feb/May/Aug/Nov, 06:00 UTC), `license-audit-quarterly` (1st of Jan/Apr/Jul/Oct, 07:00 UTC). Annual ACS/CBP loads are **not** scheduled (spec §9: manual approval) — run via `census_load.py` then `activate`.
- `license.audit(conn, http) -> list[AuditResult(dataset_key, changed, sha256)]`; table `license_audit_log`.

- [ ] **Step 1: Failing tests**

`tests/census/test_tasks.py`:
```python
from app.tasks.celery_app import celery_app


def test_census_tasks_are_registered():
    for name in ["census.load_tiger", "census.load_acs", "census.load_cbp", "census.load_qwi", "census.load_bds", "census.license_audit"]:
        assert name in celery_app.tasks, name


def test_beat_schedules_only_the_automatic_cadences():
    beat = celery_app.conf.beat_schedule
    assert beat["qwi-quarterly"]["task"] == "census.load_qwi"
    assert beat["license-audit-quarterly"]["task"] == "census.license_audit"
    scheduled_tasks = {v["task"] for v in beat.values()}
    assert "census.load_acs" not in scheduled_tasks and "census.load_cbp" not in scheduled_tasks  # manual approval (spec §9)
```

`tests/census/test_license.py`:
```python
import httpx

from app.census import license


def test_audit_records_hash_then_flags_drift(conn):
    body = {"n": 0}
    def handler(r):
        return httpx.Response(200, text=f"terms v{body['n']}")
    http = httpx.Client(transport=httpx.MockTransport(handler))
    first = {r.dataset_key: r for r in license.audit(conn, http)}
    assert first["acs5"].changed is False                     # first observation is the baseline
    second = {r.dataset_key: r for r in license.audit(conn, http)}
    assert second["acs5"].changed is False
    body["n"] = 1
    third = {r.dataset_key: r for r in license.audit(conn, http)}
    assert third["acs5"].changed is True
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM license_audit_log WHERE dataset_key='acs5' AND changed")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT drift_flagged FROM dataset_registry WHERE dataset_key='acs5'")
        assert cur.fetchone()[0] is True
        cur.execute("SELECT last_verified_at IS NOT NULL FROM dataset_registry WHERE dataset_key='acs5'")
        assert cur.fetchone()[0] is True


def test_datasets_without_a_terms_url_are_skipped(conn):
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x")))
    keys = {r.dataset_key for r in license.audit(conn, http)}
    assert "imagery" not in keys and "pet_ownership" not in keys
```

- [ ] **Step 2: Migration and licence module**

`migrations/007_license_audit.sql`:
```sql
-- §9 license_audit: re-read each source's terms URL quarterly; flag drift for staff review.
ALTER TABLE dataset_registry ADD COLUMN drift_flagged boolean NOT NULL DEFAULT false;
CREATE TABLE license_audit_log (
  id bigserial PRIMARY KEY,
  dataset_key text NOT NULL REFERENCES dataset_registry(dataset_key),
  checked_at timestamptz NOT NULL DEFAULT now(),
  url text NOT NULL,
  content_sha256 text,
  http_status integer,
  changed boolean NOT NULL DEFAULT false
);
CREATE INDEX license_audit_log_ds_idx ON license_audit_log (dataset_key, checked_at DESC);
```

`app/census/license.py`:
```python
"""Quarterly licence audit (spec §9, §12). Fetches each registered terms URL, hashes
the body, and flags the dataset when the hash changes. Never changes license_status —
that is a human decision recorded in the admin console."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class AuditResult:
    dataset_key: str
    changed: bool
    sha256: str | None
    status: int | None


def audit(conn, http: httpx.Client) -> list[AuditResult]:
    out: list[AuditResult] = []
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, license_url FROM dataset_registry WHERE license_url IS NOT NULL ORDER BY dataset_key")
        targets = cur.fetchall()
    for key, url in targets:
        try:
            resp = http.get(url, timeout=httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=15.0), follow_redirects=True)
            status, digest = resp.status_code, hashlib.sha256(resp.content).hexdigest() if resp.status_code < 400 else None
        except httpx.HTTPError:
            status, digest = None, None
        with conn.cursor() as cur:
            cur.execute("SELECT content_sha256 FROM license_audit_log WHERE dataset_key = %s AND content_sha256 IS NOT NULL ORDER BY checked_at DESC LIMIT 1", (key,))
            prev = cur.fetchone()
            changed = bool(prev and digest and prev[0] != digest)
            cur.execute("INSERT INTO license_audit_log (dataset_key, url, content_sha256, http_status, changed) VALUES (%s, %s, %s, %s, %s)",
                        (key, url, digest, status, changed))
            if changed:
                cur.execute("UPDATE dataset_registry SET drift_flagged = true WHERE dataset_key = %s", (key,))
            elif digest:
                cur.execute("UPDATE dataset_registry SET last_verified_at = now() WHERE dataset_key = %s", (key,))
        out.append(AuditResult(key, changed, digest, status))
    return out
```

- [ ] **Step 3: Tasks and beat**

`app/tasks/census.py`:
```python
"""Celery entry points for the market-data layer. Each task opens its own psycopg2
connection, builds a keyed CensusClient with the archive, and returns a small summary
dict that Flower/logs can read."""
from __future__ import annotations

import os

import httpx
import psycopg2

from app.census import acs, bds, cbp, license, qwi, tiger
from app.census.client import CensusClient, require_key
from app.census.storage import ObjectStore
from app.config import settings
from app.tasks.celery_app import celery_app
from app.version import VERSION


def _conn():
    c = psycopg2.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    c.autocommit = True
    return c


def _states(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
        return [r[0] for r in cur.fetchall()]


def _factory():
    key = require_key(os.environ)
    archive = ObjectStore.from_settings(settings)
    return lambda ds: CensusClient(key, ds, archive, version=VERSION, contact=settings.census_contact_email)


@celery_app.task(name="census.load_tiger")
def load_tiger(vintage: str = "2023") -> dict:
    conn = _conn()
    with httpx.Client(headers={"User-Agent": f"PracticeMatch/{VERSION} (VIN Foundation; {settings.census_contact_email})"}) as http:
        return tiger.load_boundaries(conn, http, _states(conn), vintage)


@celery_app.task(name="census.load_acs")
def load_acs(dataset_key: str = "acs5") -> dict:
    conn = _conn()
    return {"dataset": dataset_key, "rows": acs.load(conn, _factory(), dataset_key, _states(conn))}


@celery_app.task(name="census.load_cbp")
def load_cbp() -> dict:
    conn = _conn()
    return {"rows": cbp.load(conn, _factory(), _states(conn))}


@celery_app.task(name="census.load_qwi")
def load_qwi(year: int | None = None, quarter: int | None = None) -> dict:
    import datetime as dt
    conn = _conn()
    states = _states(conn)
    factory = _factory()
    if year is None or quarter is None:
        from app.census.registry import load as load_registry
        now = dt.datetime.utcnow()
        year, quarter = qwi.latest_available(factory(load_registry(conn)["qwi"]), states[0], today=(now.year, (now.month - 1) // 3 + 1))
    rows = qwi.load(conn, factory, states, year=year, quarter=quarter)
    trimmed = qwi.trim(conn, keep=20)
    return {"year": year, "quarter": quarter, "rows": rows, "trimmed": trimmed}


@celery_app.task(name="census.load_bds")
def load_bds(year: int) -> dict:
    conn = _conn()
    return {"year": year, "rows": bds.load(conn, _factory(), _states(conn), year=year)}


@celery_app.task(name="census.license_audit")
def license_audit() -> dict:
    conn = _conn()
    with httpx.Client(headers={"User-Agent": f"PracticeMatch/{VERSION} (VIN Foundation; {settings.census_contact_email})"}) as http:
        results = license.audit(conn, http)
    return {"checked": len(results), "drift": [r.dataset_key for r in results if r.changed]}
```

In `app/tasks/celery_app.py`, after `celery_app.conf.update(...)`:
```python
from celery.schedules import crontab  # noqa: E402

celery_app.conf.beat_schedule = {
    # Spec §9: QWI is the only Census load that runs on a schedule; ACS/CBP annual loads
    # need manual approval and are run through scripts/census_load.py + activate.
    "qwi-quarterly": {"task": "census.load_qwi", "schedule": crontab(minute=0, hour=6, day_of_month="15", month_of_year="2,5,8,11")},
    "license-audit-quarterly": {"task": "census.license_audit", "schedule": crontab(minute=0, hour=7, day_of_month="1", month_of_year="1,4,7,10")},
}
celery_app.conf.imports = ("app.tasks.census",)
```

Run: `poetry run pytest -q` → all pass (including Foundation's `test_celery.py`). Commit: `feat(census): Celery tasks, quarterly beat, licence audit with drift flag`.

---

### Task A9: Admin Data Sources endpoint and the 60-second layer gate

**Files:**
- Create: `app/api/admin_data_sources.py`, `app/cache.py`, `app/census/gate.py`, `app/api/auth_stub.py`, `tests/census/test_admin_api.py`, `tests/census/test_gate.py`
- Modify: `app/main.py` (include router before the `/api` catch-all)

**Interfaces:**
- `gate.layer_enabled(redis, conn_factory, dataset_key) -> bool` — reads `dataset_registry.license_status == 'cleared'` through a 60 s Redis cache (`gate:{dataset_key}`); `gate.invalidate(redis, dataset_key)`.
- `auth_stub.require_operator(request)` — until Sub-project 2's real auth: `Authorization: Bearer <API_SECRET_KEY>` else 401. Replaced, not extended, in SP2.
- `GET /api/admin/data-sources` → list per the API contract; `POST /api/admin/data-sources/{key}/license` `{status, name, url, notes}` → updates the registry (human decision, audited in `license_audit_log` with `url` and `changed=false`), invalidates the gate.

- [ ] **Step 1: Failing tests**

`tests/census/test_gate.py`:
```python
import fakeredis  # poetry add --group dev fakeredis

from app.census import gate


def test_gate_reads_registry_and_caches_for_60s(conn):
    r = fakeredis.FakeRedis()
    assert gate.layer_enabled(r, lambda: conn, "acs5") is True
    assert gate.layer_enabled(r, lambda: conn, "pet_ownership") is False
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='blocked' WHERE dataset_key='acs5'")
    assert gate.layer_enabled(r, lambda: conn, "acs5") is True          # cached
    assert 0 < r.ttl("gate:acs5") <= 60
    before = gate.version(r)
    gate.invalidate(r, "acs5")
    assert gate.layer_enabled(r, lambda: conn, "acs5") is False         # fresh read
    assert gate.version(r) == before + 1                                # cached payloads are keyed away
```

`tests/census/test_admin_api.py`:
```python
import httpx
import pytest
from httpx import ASGITransport

from app.config import settings
from app.main import create_app


@pytest.fixture
async def client(scratch_dsn, monkeypatch):
    monkeypatch.setattr(settings, "database_url", scratch_dsn)
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c


async def test_requires_operator_token(client):
    assert (await client.get("/api/admin/data-sources")).status_code == 401


async def test_lists_registry_with_status_and_active_vintage(client):
    r = await client.get("/api/admin/data-sources", headers={"Authorization": f"Bearer {settings.api_secret_key}"})
    assert r.status_code == 200
    rows = {x["dataset_key"]: x for x in r.json()}
    assert rows["pet_ownership"]["license_status"] == "blocked"
    assert rows["acs5"]["license_status"] == "cleared" and rows["acs5"]["active_vintage"] is None
    assert set(rows["acs5"]) >= {"dataset_key", "display_name", "license_status", "license_name", "vintage", "refresh_cadence", "last_verified_at", "active_vintage", "drift_flagged", "last_run", "notes"}


async def test_license_decision_updates_registry_and_logs(client):
    h = {"Authorization": f"Bearer {settings.api_secret_key}"}
    r = await client.post("/api/admin/data-sources/imagery/license", headers=h,
                          json={"status": "cleared", "name": "Esri Imagery — commercial web display", "url": "https://example.test/terms", "notes": "signed 2026-09-05"})
    assert r.status_code == 200 and r.json()["license_status"] == "cleared"
    r2 = await client.post("/api/admin/data-sources/imagery/license", headers=h, json={"status": "maybe"})
    assert r2.status_code == 422
```

- [ ] **Step 2: Implement**

`app/cache.py`:
```python
import redis.asyncio as aioredis
import redis as redis_sync

from app.config import settings


def sync_redis() -> redis_sync.Redis:
    return redis_sync.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)


def async_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
```

`app/census/gate.py`:
```python
"""Spec §11: when a dataset's license_status leaves 'cleared', its layer disappears
within one minute — a 60-second cache over the registry, invalidated on any admin decision."""
TTL = 60


def layer_enabled(r, conn_factory, dataset_key: str) -> bool:
    key = f"gate:{dataset_key}"
    cached = r.get(key)
    if cached is not None:
        return cached in (b"1", "1")
    conn = conn_factory()
    with conn.cursor() as cur:
        cur.execute("SELECT license_status = 'cleared' FROM dataset_registry WHERE dataset_key = %s", (dataset_key,))
        row = cur.fetchone()
    enabled = bool(row and row[0])
    r.set(key, "1" if enabled else "0", ex=TTL)
    return enabled


def invalidate(r, dataset_key: str) -> None:
    """Drop the cached status AND bump the global gate version so every cached market payload
    (panel, communities) is keyed away within the same minute (red-team C5)."""
    r.delete(f"gate:{dataset_key}")
    r.incr("market:gate:v")


def version(r) -> int:
    v = r.get("market:gate:v")
    return int(v) if v else 0
```

`app/api/auth_stub.py`:
```python
"""Temporary operator gate for admin routes until Sub-project 2 ships real auth.
Bearer token = API_SECRET_KEY of the environment. Delete this file in SP2."""
from fastapi import HTTPException, Request

from app.config import settings


def require_operator(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {settings.api_secret_key}":
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "operator token required"})
```

`app/api/admin_data_sources.py`:
```python
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, HttpUrl
from sqlalchemy import text

from app.api.auth_stub import require_operator
from app.cache import sync_redis
from app.census import gate
from app.db import engine  # created in this task: app/db.py exposes `engine = create_async_engine(async_dsn(settings.database_url))`

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_operator)])

LIST_SQL = text("""
SELECT r.dataset_key, r.display_name, r.api_dataset_id, r.vintage, r.refresh_cadence, r.license_status, r.license_name, r.license_url,
       r.attribution_text, r.last_verified_at, r.notes, r.drift_flagged, a.vintage AS active_vintage,
       (SELECT json_build_object('status', i.status, 'finished_at', i.finished_at, 'rows_written', i.rows_written)
          FROM ingest_run i WHERE i.dataset_key = r.dataset_key ORDER BY i.id DESC LIMIT 1) AS last_run
FROM dataset_registry r LEFT JOIN active_vintage a USING (dataset_key) ORDER BY r.dataset_key""")


@router.get("/data-sources")
async def list_data_sources() -> list[dict]:
    async with engine.connect() as conn:
        rows = (await conn.execute(LIST_SQL)).mappings().all()
    return [dict(r) for r in rows]


class LicenseDecision(BaseModel):
    status: Literal["cleared", "unresolved", "blocked"]
    name: str | None = None
    url: HttpUrl | None = None
    notes: str | None = None


@router.post("/data-sources/{dataset_key}/license")
async def decide_license(dataset_key: str, body: LicenseDecision) -> dict:
    async with engine.begin() as conn:
        res = await conn.execute(text("""UPDATE dataset_registry SET license_status = :s, license_name = COALESCE(:n, license_name),
                                         license_url = COALESCE(:u, license_url), notes = COALESCE(:o, notes), drift_flagged = false,
                                         last_verified_at = now() WHERE dataset_key = :k RETURNING dataset_key, license_status"""),
                                 {"s": body.status, "n": body.name, "u": str(body.url) if body.url else None, "o": body.notes, "k": dataset_key})
        row = res.mappings().first()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": dataset_key})
        await conn.execute(text("INSERT INTO license_audit_log (dataset_key, url, changed) VALUES (:k, :u, false)"),
                           {"k": dataset_key, "u": str(body.url) if body.url else "operator decision"})
    gate.invalidate(sync_redis(), dataset_key)
    return dict(row)
```

Wire in `app/main.py` before `not_found_router`: `app.include_router(admin_data_sources.router)`. Run: `poetry run pytest -q` → all pass.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat(census): admin Data Sources API, licence decisions, 60s layer gate

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/census-data-layer && git push production feat/census-data-layer
```

**Phase A exit:** deploy to QA (`scripts/deploy.sh QA`), then from the worker: `railway run --service worker --environment QA -- python scripts/census_load.py tiger`, `… acs`, `… cbp`, `… zbp`, `… qwi`, `… bds --year 2022`, then `… activate acs5 "2019–2023" --by john` (and `acs5_subject`, `acs5_prior`, `cbp`, `zbp`, `tiger_cb`). `GET /api/admin/data-sources` on qa.foundation.vin shows every dataset with its status, last run and active vintage.

---

## Phase B — Listing-dependent (requires Sub-project 2's `listing` table)

> **Precondition check before B1:** `psql "$DATABASE_URL" -c '\d listing'` must show `id uuid PRIMARY KEY`, address columns (`street`, `city`, `state`, `zip`), `status`, and `location_disclosed boolean` (SP2's seller disclosure toggle — the design's step-7 "generalized location" control). If it does not, STOP — Sub-project 2 has not landed; report BLOCKED rather than inventing a `listing` table here. Phase B migrations are numbered `060`+ so they always sort after SP2's `010`–`059` (D14).

### Task B1: Listing-dependent tables, geocode cache, licence-gate trigger (migrations 060–061)

**Files:**
- Create: `migrations/060_geocode_cache.sql`, `migrations/061_census_listing_tables.sql`, `tests/census/test_listing_schema.py`, `tests/census/listing_fixtures.py`

**Interfaces:**
- Tables `geocode_cache`, `geocode_review`, `practice_location`, `practice_catchment`, `market_metric` (+ `inputs jsonb`, decision D9 below), trigger `market_metric_license_gate`.
- `listing_fixtures.make_listing(conn, *, id=None, city="Cedar Park", state="TX", zip="78613", street="1 Main St", status="published") -> uuid` — inserts into SP2's `listing` with the minimum columns; adapt the column list to SP2's schema in this one helper only.

**Decision D9 (added here):** `market_metric` gains `inputs jsonb` — `{"acs5": "2019–2023", "cbp": "2022"}` — so a cross-dataset ratio (vets per 10k households = CBP 2022 ÷ ACS 2019–2023) carries both vintages explicitly; §14's "two vintages never in one ratio" is enforced *within* a dataset family (no 2023 local ÷ 2018 national income) and *labelled* across families.

- [ ] **Step 1: Failing tests**

`tests/census/test_listing_schema.py`:
```python
import psycopg2
import pytest

from tests.census.listing_fixtures import make_listing


def test_market_metric_refuses_datasets_that_are_not_cleared(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)
                       VALUES (%s, 'drive_10', 'population', '2019–2023', 1, 'count', 'acs5', now())""", (lid,))
        with pytest.raises(psycopg2.errors.RaiseException) as e:
            cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)
                           VALUES (%s, 'drive_10', 'pet_households_licensed', 'n/a', 1, 'count', 'pet_ownership', now())""", (lid,))
        assert "pet_ownership" in str(e.value) and "blocked" in str(e.value)


def test_status_flip_blocks_future_writes_but_keeps_rows(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)
                       VALUES (%s, 'drive_10', 'population', '2019–2023', 1, 'count', 'acs5', now())""", (lid,))
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5'")
        with pytest.raises(psycopg2.errors.RaiseException):
            cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)
                           VALUES (%s, 'drive_20', 'population', '2019–2023', 1, 'count', 'acs5', now())""", (lid,))
        cur.execute("SELECT count(*) FROM market_metric WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 1  # existing rows stay; the API hides them via the gate (A9)


def test_practice_location_precision_is_constrained_and_cascades(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("""INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoded_at, geocoder_vintage)
                           VALUES (%s, 'h', 'approximate', now(), 'Current_Current')""", (lid,))
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoded_at, geocoder_vintage)
                       VALUES (%s, 'h', 'rooftop', now(), 'Current_Current')""", (lid,))
        cur.execute("DELETE FROM listing WHERE id=%s", (lid,))
        cur.execute("SELECT count(*) FROM practice_location WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 0


def test_catchment_overlap_bounds(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("""INSERT INTO practice_catchment (listing_id, band, geo_id, vintage, overlap_frac, method)
                       VALUES (%s, 'drive_10', '48453000101', '2023', 1.5, 'euclidean_buffer_v1')""", (lid,))
```

`tests/census/listing_fixtures.py`:
```python
import uuid


def make_listing(conn, *, id=None, city="Cedar Park", state="TX", zip="78613", street="1 Main St", status="published"):
    """Minimal listing row. The column list must match Sub-project 2's listing schema —
    update THIS function only if SP2 names them differently."""
    lid = str(id or uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing (id, street, city, state, zip, status) VALUES (%s, %s, %s, %s, %s, %s)", (lid, street, city, state, zip, status))
    return lid
```

Run → FAIL (relations missing).

- [ ] **Step 2: Migrations**

`migrations/060_geocode_cache.sql`:
```sql
-- §10 geocode result cache: sha256(normalized_address) → payload, 365 days.
CREATE TABLE geocode_cache (
  address_hash text PRIMARY KEY,
  normalized_address text NOT NULL,
  payload jsonb NOT NULL,
  geocoded_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL DEFAULT now() + interval '365 days'
);
-- §11 "flag for staff": listings whose location fell back below rooftop precision.
CREATE TABLE geocode_review (
  id bigserial PRIMARY KEY,
  listing_id uuid NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);
```

`migrations/061_census_listing_tables.sql`:
```sql
-- §13 listing-dependent tables, verbatim, plus the licence-gate trigger (§1) and
-- market_metric.inputs (plan decision D9).
CREATE TABLE practice_location (
  listing_id uuid PRIMARY KEY REFERENCES listing(id) ON DELETE CASCADE,
  address_hash text NOT NULL,
  point geometry(Point, 4269),
  tract_geoid text,
  county_geoid text,
  place_geoid text,
  zcta_geoid text,
  cbsa_geoid text,
  geo_precision text NOT NULL CHECK (geo_precision IN ('rooftop','tract','zcta','place','county')),
  geocoded_at timestamptz NOT NULL,
  geocoder_vintage text NOT NULL
);
CREATE INDEX practice_location_point_gix ON practice_location USING gist (point);

CREATE TABLE practice_catchment (
  listing_id uuid NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  band text NOT NULL CHECK (band IN ('drive_10','drive_20')),
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL DEFAULT '140',
  vintage text NOT NULL,
  overlap_frac numeric(6,5) NOT NULL CHECK (overlap_frac > 0 AND overlap_frac <= 1),
  method text NOT NULL, -- 'euclidean_buffer_v1' | 'isochrone_v2'
  PRIMARY KEY (listing_id, band, geo_id, vintage)
);

CREATE TABLE market_metric (
  listing_id uuid NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  band text NOT NULL,
  metric_key text NOT NULL,
  vintage text NOT NULL,
  value_num numeric,
  value_text text,
  unit text NOT NULL, -- 'count' | 'usd' | 'pct' | 'ratio' | 'score'
  is_derived boolean NOT NULL DEFAULT false,
  formula_version text,
  moe numeric,
  suppressed boolean NOT NULL DEFAULT false,
  suppress_reason text,
  source_dataset text NOT NULL REFERENCES dataset_registry(dataset_key),
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (listing_id, band, metric_key, vintage)
);
CREATE INDEX market_metric_lookup_idx ON market_metric (listing_id, band, vintage);
ALTER TABLE market_metric ADD COLUMN inputs jsonb;  -- D9: {"acs5":"2019–2023","cbp":"2022"}

-- §1 "Licensing gates production … enforced by a foreign key to license_status = 'cleared'":
-- a plain FK cannot express the predicate, so the gate is a trigger. Existing rows survive a
-- status flip (the API hides them within 60 s via app/census/gate.py); new writes are refused.
CREATE OR REPLACE FUNCTION market_metric_license_gate() RETURNS trigger AS $$
DECLARE st text;
BEGIN
  SELECT license_status INTO st FROM dataset_registry WHERE dataset_key = NEW.source_dataset;
  IF st IS DISTINCT FROM 'cleared' THEN
    RAISE EXCEPTION 'market_metric write refused: dataset % is % (licence gate)', NEW.source_dataset, COALESCE(st, 'unknown');
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER market_metric_license_gate BEFORE INSERT OR UPDATE ON market_metric
  FOR EACH ROW EXECUTE FUNCTION market_metric_license_gate();
```

Run: `poetry run pytest tests/census/test_listing_schema.py -q` → 4 passed. Commit: `feat(census): listing-dependent tables, geocode cache, licence-gate trigger (spec §13)`.

---

### Task B2: Geocoder client, address cache, fallback ladder, `geocode_listing` task

**Files:**
- Create: `app/census/geocode.py`, `tests/census/test_geocode.py`, `tests/census/fixtures/geocoder_match.json`, `tests/census/fixtures/geocoder_nomatch.json`
- Modify: `app/tasks/census.py` (`census.geocode_listing`)

**Interfaces:**
- `geocode.normalize(street, city, state, zip) -> str` and `address_hash(normalized) -> str` (sha256 hex).
- `geocode.Geocoder(http: httpx.Client, base_url, user_agent)` with `lookup(street, city, state, zip) -> Match | None`; `Match(lat, lng, matched_address, tract_geoid, county_geoid, place_geoid | None, zcta_geoid | None, cbsa_geoid | None)`.
- `geocode.resolve(conn, geocoder, listing_id) -> Location` — cache → geocoder → fallback ladder → writes `practice_location` (+ `geocode_review` when precision ≠ rooftop); raises `GeocodeFailed` when nothing resolves (listing stays draft — SP2 reads this exception's message into the seller's draft status).
- Task `census.geocode_listing(listing_id)` → `{"precision": …}`; on success enqueues `census.backfill_listing(listing_id)` (B5).

- [ ] **Step 1: Fixtures (recorded response shapes) and failing tests**

`tests/census/fixtures/geocoder_match.json`:
```json
{"result":{"input":{"address":{"street":"1 Main St","city":"Cedar Park","state":"TX","zip":"78613"},"benchmark":{"benchmarkName":"Public_AR_Current"},"vintage":{"vintageName":"Current_Current"}},
 "addressMatches":[{"matchedAddress":"1 MAIN ST, CEDAR PARK, TX, 78613","coordinates":{"x":-97.8203,"y":30.5052},
  "geographies":{
   "Census Tracts":[{"GEOID":"48491020304","NAME":"Census Tract 203.04","STATE":"48","COUNTY":"491","TRACT":"020304"}],
   "Counties":[{"GEOID":"48491","NAME":"Williamson County","STATE":"48","COUNTY":"491"}],
   "Incorporated Places":[{"GEOID":"4813552","NAME":"Cedar Park city","STATE":"48","PLACE":"13552"}],
   "2020 Census ZIP Code Tabulation Areas":[{"GEOID":"78613","ZCTA5":"78613"}],
   "Metropolitan Statistical Areas":[{"GEOID":"12420","NAME":"Austin-Round Rock-San Marcos, TX Metro Area"}]}}]}}
```
`tests/census/fixtures/geocoder_nomatch.json`: `{"result":{"input":{},"addressMatches":[]}}`

`tests/census/test_geocode.py`:
```python
import json
from pathlib import Path

import httpx
import pytest

from app.census import geocode
from tests.census.listing_fixtures import make_listing

FIX = Path(__file__).parent / "fixtures"
MATCH = json.loads((FIX / "geocoder_match.json").read_text())
NOMATCH = json.loads((FIX / "geocoder_nomatch.json").read_text())


def _geocoder(payload, seen=None):
    def handler(r):
        if seen is not None: seen.append(str(r.url))
        return httpx.Response(200, json=payload)
    return geocode.Geocoder(httpx.Client(transport=httpx.MockTransport(handler)), "https://geocoding.geo.census.gov/geocoder", "PracticeMatch (test)")


def test_normalize_is_case_and_punctuation_insensitive():
    a = geocode.normalize("1 Main St.", "Cedar Park", "tx", "78613")
    b = geocode.normalize("1  MAIN ST", " cedar park ", "TX", "78613-1234")
    assert a == b == "1 main st|cedar park|tx|78613"
    assert len(geocode.address_hash(a)) == 64


def test_lookup_parses_geographies_and_uses_spec_benchmark_and_vintage():
    seen = []
    m = _geocoder(MATCH, seen).lookup("1 Main St", "Cedar Park", "TX", "78613")
    assert (m.lat, m.lng) == (30.5052, -97.8203)
    assert (m.tract_geoid, m.county_geoid, m.place_geoid, m.zcta_geoid, m.cbsa_geoid) == ("48491020304", "48491", "4813552", "78613", "12420")
    url = seen[0]
    assert "geocoder/geographies/address?" in url and "benchmark=Public_AR_Current" in url and "vintage=Current_Current" in url and "format=json" in url


def test_lookup_returns_none_on_no_match():
    assert _geocoder(NOMATCH).lookup("999 Nowhere", "Nope", "TX", "00000") is None


def _seed_geo(conn):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid) VALUES
          ('48491020304','140','2023','Tract 203.04','48','491','48491', ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)), ST_Point(-97.8,30.55,4269)),
          ('78613','860','2023','ZCTA5 78613',NULL,NULL,NULL, ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)), ST_Point(-97.8,30.55,4269)),
          ('4813552','160','2023','Cedar Park city','48',NULL,'48', ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)), ST_Point(-97.8,30.55,4269))""")
        cur.execute("INSERT INTO active_vintage VALUES ('tiger_cb','2023',now(),'test')")


def test_resolve_rooftop_writes_location_and_caches(conn):
    _seed_geo(conn)
    lid = make_listing(conn)
    seen = []
    loc = geocode.resolve(conn, _geocoder(MATCH, seen), lid)
    assert loc.geo_precision == "rooftop" and loc.tract_geoid == "48491020304" and loc.cbsa_geoid == "12420"
    with conn.cursor() as cur:
        cur.execute("SELECT geo_precision, ST_X(point), county_geoid FROM practice_location WHERE listing_id=%s", (lid,))
        assert cur.fetchone() == ("rooftop", -97.8203, "48491")
        cur.execute("SELECT count(*) FROM geocode_cache"); assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM geocode_review WHERE listing_id=%s", (lid,)); assert cur.fetchone()[0] == 0
    # second listing at the same address → served from cache, no HTTP call
    lid2 = make_listing(conn)
    geocode.resolve(conn, _geocoder(MATCH, seen), lid2)
    assert len(seen) == 1


def test_resolve_falls_back_to_zcta_centroid_and_flags_for_staff(conn):
    _seed_geo(conn)
    lid = make_listing(conn, zip="78613")
    loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)
    assert loc.geo_precision == "zcta" and loc.tract_geoid == "48491020304" and loc.zcta_geoid == "78613"
    with conn.cursor() as cur:
        cur.execute("SELECT reason FROM geocode_review WHERE listing_id=%s", (lid,))
        assert "zcta" in cur.fetchone()[0]


def test_resolve_falls_back_to_place_then_fails(conn):
    _seed_geo(conn)
    lid = make_listing(conn, zip="00000", city="Cedar Park")
    loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)
    assert loc.geo_precision == "place" and loc.place_geoid == "4813552"
    lid2 = make_listing(conn, zip="00000", city="Nowhereville")
    with pytest.raises(geocode.GeocodeFailed):
        geocode.resolve(conn, _geocoder(NOMATCH), lid2)
```

Run → FAIL (module missing).

- [ ] **Step 2: Implement**

`app/census/geocode.py`:
```python
"""Census Geocoder (spec §2 geocoder, §6 resolution order, §10 365-day cache, §11 fallbacks).
Address → geocoder → tract/county/place; else ZCTA centroid → containing tract; else place;
else county (only when a county is known); else GeocodeFailed — the listing stays in draft."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import httpx


class GeocodeFailed(Exception):
    pass


@dataclass(frozen=True)
class Match:
    lat: float
    lng: float
    matched_address: str
    tract_geoid: str | None
    county_geoid: str | None
    place_geoid: str | None
    zcta_geoid: str | None
    cbsa_geoid: str | None


@dataclass(frozen=True)
class Location:
    listing_id: str
    geo_precision: str
    lat: float | None
    lng: float | None
    tract_geoid: str | None
    county_geoid: str | None
    place_geoid: str | None
    zcta_geoid: str | None
    cbsa_geoid: str | None


def normalize(street: str, city: str, state: str, zip_: str) -> str:
    def clean(s: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (s or "").lower())).strip()
    return "|".join([clean(street), clean(city), clean(state), (zip_ or "").strip()[:5]])


def address_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode()).hexdigest()


def _first_geoid(geos: dict, *needles: str) -> str | None:
    for key, rows in geos.items():
        if any(n in key for n in needles) and rows:
            return rows[0].get("GEOID")
    return None


class Geocoder:
    def __init__(self, http: httpx.Client, base_url: str, user_agent: str):
        self.http, self.base_url, self.ua = http, base_url.rstrip("/"), user_agent

    def lookup(self, street: str, city: str, state: str, zip_: str) -> Match | None:
        params = {"street": street, "city": city, "state": state, "zip": zip_, "benchmark": "Public_AR_Current",
                  "vintage": "Current_Current", "layers": "all", "format": "json"}
        resp = self.http.get(f"{self.base_url}/geographies/address", params=params, headers={"User-Agent": self.ua},
                             timeout=httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=15.0))
        resp.raise_for_status()
        matches = resp.json().get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        m = matches[0]
        g = m.get("geographies", {})
        return Match(lat=float(m["coordinates"]["y"]), lng=float(m["coordinates"]["x"]), matched_address=m.get("matchedAddress", ""),
                     tract_geoid=_first_geoid(g, "Census Tracts"), county_geoid=_first_geoid(g, "Counties"),
                     place_geoid=_first_geoid(g, "Incorporated Places", "Census Designated Places"),
                     zcta_geoid=_first_geoid(g, "ZIP Code Tabulation Areas"), cbsa_geoid=_first_geoid(g, "Metropolitan Statistical Areas"))


def _cached(conn, h: str) -> Match | None:
    with conn.cursor() as cur:
        cur.execute("SELECT payload FROM geocode_cache WHERE address_hash = %s AND expires_at > now()", (h,))
        row = cur.fetchone()
    if not row:
        return None
    p = row[0]
    return None if p.get("nomatch") else Match(**p)


def _cache(conn, h: str, normalized: str, m: Match | None) -> None:
    payload = {"nomatch": True} if m is None else m.__dict__
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO geocode_cache (address_hash, normalized_address, payload) VALUES (%s, %s, %s)
                       ON CONFLICT (address_hash) DO UPDATE SET payload = EXCLUDED.payload, geocoded_at = now(), expires_at = now() + interval '365 days'""",
                    (h, normalized, json.dumps(payload)))


def _tiger_vintage(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT vintage FROM active_vintage WHERE dataset_key = 'tiger_cb'")
        row = cur.fetchone()
    if not row:
        raise GeocodeFailed("no active tiger_cb vintage — run census_load.py tiger and activate it")
    return row[0]


def _fallback(conn, city: str, state_abbr: str, zip_: str, vintage: str) -> tuple[str, dict]:
    """Returns (precision, fields) following §6: ZCTA centroid → containing tract; else place."""
    with conn.cursor() as cur:
        cur.execute("""SELECT z.geo_id, ST_X(z.centroid), ST_Y(z.centroid), t.geo_id, t.parent_geo_id
                       FROM geo_area z LEFT JOIN geo_area t ON t.summary_level = '140' AND t.vintage = z.vintage AND ST_Contains(t.geom, z.centroid)
                       WHERE z.summary_level = '860' AND z.vintage = %s AND z.geo_id = %s""", (vintage, (zip_ or "")[:5]))
        row = cur.fetchone()
        if row and row[3]:
            return "zcta", {"zcta_geoid": row[0], "lng": row[1], "lat": row[2], "tract_geoid": row[3], "county_geoid": row[4]}
        cur.execute("""SELECT p.geo_id, ST_X(p.centroid), ST_Y(p.centroid), p.state_fips FROM geo_area p
                       WHERE p.summary_level = '160' AND p.vintage = %s AND lower(p.name) LIKE lower(%s) || ' %%'
                         AND p.state_fips = (SELECT geo_id FROM geo_area WHERE summary_level='040' AND vintage=%s AND upper(name)=upper(%s) LIMIT 1)
                       LIMIT 1""", (vintage, city, vintage, STATE_NAMES.get(state_abbr.upper(), state_abbr)))
        row = cur.fetchone()
        if row:
            return "place", {"place_geoid": row[0], "lng": row[1], "lat": row[2]}
    raise GeocodeFailed(f"no geocoder match and no ZCTA/place fallback for {city!r} {zip_!r}")


STATE_NAMES = {"TX": "Texas", "CA": "California", "FL": "Florida", "GA": "Georgia"}  # extended by market_state; see D4


def resolve(conn, geocoder: Geocoder, listing_id: str) -> Location:
    with conn.cursor() as cur:
        cur.execute("SELECT street, city, state, zip FROM listing WHERE id = %s", (listing_id,))
        street, city, state, zip_ = cur.fetchone()
    normalized = normalize(street, city, state, zip_)
    h = address_hash(normalized)
    vintage = _tiger_vintage(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM geocode_cache WHERE address_hash = %s AND expires_at > now()", (h,))
        hit = cur.fetchone() is not None
    m = _cached(conn, h) if hit else geocoder.lookup(street, city, state, zip_)
    if not hit:
        _cache(conn, h, normalized, m)
    if m:
        precision, f = ("rooftop" if m.tract_geoid else "tract"), {"lat": m.lat, "lng": m.lng, "tract_geoid": m.tract_geoid, "county_geoid": m.county_geoid,
                                                                     "place_geoid": m.place_geoid, "zcta_geoid": m.zcta_geoid, "cbsa_geoid": m.cbsa_geoid}
    else:
        precision, f = _fallback(conn, city, state, zip_, vintage)
    loc = Location(listing_id, precision, f.get("lat"), f.get("lng"), f.get("tract_geoid"), f.get("county_geoid"), f.get("place_geoid"), f.get("zcta_geoid"), f.get("cbsa_geoid"))
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, point, tract_geoid, county_geoid, place_geoid, zcta_geoid, cbsa_geoid, geo_precision, geocoded_at, geocoder_vintage)
                       VALUES (%s, %s, CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_Point(%s, %s), 4269) END, %s, %s, %s, %s, %s, %s, now(), 'Current_Current')
                       ON CONFLICT (listing_id) DO UPDATE SET address_hash = EXCLUDED.address_hash, point = EXCLUDED.point, tract_geoid = EXCLUDED.tract_geoid,
                         county_geoid = EXCLUDED.county_geoid, place_geoid = EXCLUDED.place_geoid, zcta_geoid = EXCLUDED.zcta_geoid, cbsa_geoid = EXCLUDED.cbsa_geoid,
                         geo_precision = EXCLUDED.geo_precision, geocoded_at = now()""",
                    (listing_id, h, loc.lng, loc.lng, loc.lat, loc.tract_geoid, loc.county_geoid, loc.place_geoid, loc.zcta_geoid, loc.cbsa_geoid, precision))
        if precision != "rooftop":
            cur.execute("INSERT INTO geocode_review (listing_id, reason) VALUES (%s, %s)", (listing_id, f"geocoder fell back to {precision}; market panel shows 'approximate community data'"))
    return loc
```

Add to `app/tasks/census.py`:
```python
@celery_app.task(name="census.geocode_listing")
def geocode_listing(listing_id: str) -> dict:
    from app.census import geocode
    conn = _conn()
    with httpx.Client() as http:
        gc = geocode.Geocoder(http, "https://geocoding.geo.census.gov/geocoder", f"PracticeMatch/{VERSION} (VIN Foundation; {settings.census_contact_email})")
        loc = geocode.resolve(conn, gc, listing_id)
    celery_app.send_task("census.backfill_listing", args=[listing_id])
    return {"listing_id": listing_id, "precision": loc.geo_precision}
```

Run: `poetry run pytest tests/census/test_geocode.py -q` → 6 passed. Commit: `feat(census): geocoder with 365-day cache, §6 fallback ladder, staff review flags`.

---

### Task B3: Drive-time catchments (V1 straight-line buffers) — tracts and ZCTAs

**Files:**
- Create: `app/census/catchment.py`, `tests/census/test_catchment.py`

**Interfaces:**
- `catchment.BANDS = {"drive_10": 8000, "drive_20": 16000}` (metres, spec §8) · `catchment.METHOD = "euclidean_buffer_v1"` · `catchment.build(conn, listing_id, geo_vintage) -> dict[str, dict[str, int]]` — rows written per band per summary level, e.g. `{"drive_10": {"140": 2, "860": 1}, …}`; replaces existing rows for the listing/vintage. Tract rows (`140`) feed ACS aggregation; ZCTA rows (`860`) feed ZBP competition counts (D11).

- [ ] **Step 1: Failing test**

```python
from app.census import catchment
from tests.census.listing_fixtures import make_listing


def _seed(conn, lid):
    with conn.cursor() as cur:
        # three 0.1°×0.1° tracts west→east; the practice sits in the middle of the first.
        for i, gid in enumerate(["48000000001", "48000000002", "48000000003"]):
            x0 = -97.90 + 0.1 * i
            cur.execute("""INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom) VALUES (%s,'140','2023',%s,
                           ST_Multi(ST_GeomFromText(%s, 4269)))""",
                        (gid, gid, f"POLYGON(({x0} 30.50,{x0+0.1} 30.50,{x0+0.1} 30.60,{x0} 30.60,{x0} 30.50))"))
        # one ZCTA covering the first two tracts, one far away
        cur.execute("""INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom) VALUES
            ('78613','860','2023','ZCTA5 78613', ST_Multi(ST_GeomFromText('POLYGON((-97.90 30.50,-97.70 30.50,-97.70 30.60,-97.90 30.60,-97.90 30.50))',4269))),
            ('79999','860','2023','ZCTA5 79999', ST_Multi(ST_GeomFromText('POLYGON((-99.0 31.0,-98.9 31.0,-98.9 31.1,-99.0 31.1,-99.0 31.0))',4269)))""")
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, point, geo_precision, geocoded_at, geocoder_vintage)
                       VALUES (%s, 'h', ST_SetSRID(ST_Point(-97.85, 30.55), 4269), 'rooftop', now(), 'Current_Current')""", (lid,))


def test_buffers_intersect_tracts_and_zctas_with_overlap_fractions(conn):
    lid = make_listing(conn)
    _seed(conn, lid)
    counts = catchment.build(conn, lid, "2023")
    assert counts == {"drive_10": {"140": 2, "860": 1}, "drive_20": {"140": 3, "860": 1}}
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id, overlap_frac::float, method FROM practice_catchment WHERE listing_id=%s AND band='drive_10' AND summary_level='140' ORDER BY geo_id", (lid,))
        rows = cur.fetchall()
    assert rows[0][0] == "48000000001" and 0.9 < rows[0][1] <= 1.0 and rows[0][2] == "euclidean_buffer_v1"
    assert rows[1][0] == "48000000002" and 0.0 < rows[1][1] < 0.5
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id, overlap_frac::float FROM practice_catchment WHERE listing_id=%s AND band='drive_10' AND summary_level='860'", (lid,))
        (zcta, frac), = cur.fetchall()
    assert zcta == "78613" and 0.4 < frac < 0.8


def test_rebuild_replaces_rows(conn):
    lid = make_listing(conn)
    _seed(conn, lid)
    catchment.build(conn, lid, "2023")
    catchment.build(conn, lid, "2023")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM practice_catchment WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 7
```

- [ ] **Step 2: Implement**

```python
"""Drive-time catchments, V1 (spec §7 'Catchment build', §8 drive_catchment): straight-line
buffers of 8 km (≈10 min) and 16 km (≈20 min) in geography space, intersected with tracts
(ACS inputs) and ZCTAs (ZBP competition inputs, D11); overlap_frac = intersected area / unit area.
Geometry is NAD83 (4269); geography maths is done after ST_Transform to 4326 (red-team C6)."""
BANDS = {"drive_10": 8000, "drive_20": 16000}
METHOD = "euclidean_buffer_v1"
LEVELS = ("140", "860")

SQL = """
INSERT INTO practice_catchment (listing_id, band, geo_id, summary_level, vintage, overlap_frac, method)
SELECT p.listing_id, %(band)s, g.geo_id, %(level)s, %(vintage)s,
       LEAST(1.0, GREATEST(0.00001,
         ST_Area(ST_Intersection(ST_Transform(g.geom, 4326)::geography, b.buf)) / NULLIF(ST_Area(ST_Transform(g.geom, 4326)::geography), 0))),
       %(method)s
FROM practice_location p
CROSS JOIN LATERAL (SELECT ST_Buffer(ST_Transform(p.point, 4326)::geography, %(radius)s) AS buf) b
JOIN geo_area g ON g.summary_level = %(level)s AND g.vintage = %(vintage)s AND ST_Intersects(ST_Transform(g.geom, 4326)::geography, b.buf)
WHERE p.listing_id = %(listing_id)s AND p.point IS NOT NULL
"""


def build(conn, listing_id: str, geo_vintage: str) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    with conn.cursor() as cur:
        cur.execute("DELETE FROM practice_catchment WHERE listing_id = %s AND vintage = %s", (listing_id, geo_vintage))
        for band, radius in BANDS.items():
            counts[band] = {}
            for level in LEVELS:
                cur.execute(SQL, {"band": band, "level": level, "vintage": geo_vintage, "method": METHOD, "radius": radius, "listing_id": listing_id})
                counts[band][level] = cur.rowcount
    return counts
```

Run → 2 passed. Commit: `feat(census): euclidean_buffer_v1 catchments over tracts and ZCTAs`.

---

### Task B4: Metric formulas (§8), data-quality rules (§14), materialisation into `market_metric` — three bands

**Files:**
- Create: `app/census/metrics.py`, `app/census/materialize.py`, `tests/census/test_metrics.py`, `tests/census/test_materialize.py`
- Modify: `app/tasks/census.py` (`census.materialize_metrics` nightly, `census.backfill_listing`), `app/tasks/celery_app.py` (beat entry), `scripts/census_load.py` (`materialize` subcommand)

**Interfaces:**
- `metrics`: `Z90 = 1.645`, `CV_THRESHOLD = 0.30`, `PET_RATE = 0.57`, `FORMULA_VERSION = "v1"`, `COMPETITION_LEVELS = ((1.4, "Low"), (2.2, "Moderate"))` (design thresholds; else `"High"`); `cv`, `high_moe`, `weighted_count`, `weighted_median`, `pet_households_est`, `population_growth_pct`, `vets_per_10k`, `income_index_vs_us`, `revenue_per_establishment`, `opportunity_score`, `competition_level(per10k) -> str`.
- `materialize.BANDS = ("place", "drive_10", "drive_20")`; `materialize.materialize_listing(conn, redis, listing_id) -> int`; `materialize.materialize_all(conn, redis) -> dict[str, int]`; Redis `listing:{id}:market:version` bumped on every write.
- Every derived row's `inputs` carries `{"geo_level": …}` plus the vintages of each input dataset.

- [ ] **Step 1: Failing formula tests**

`tests/census/test_metrics.py`:
```python
import math

import pytest

from app.census import metrics as m


def test_cv_and_high_moe_threshold():
    assert m.cv(1000, 500) == pytest.approx(0.30395, abs=1e-4)
    assert m.high_moe(1000, 500) is True            # CV 0.304 > 0.30
    assert m.high_moe(1000, 490) is False           # CV 0.298
    assert m.cv(0, 10) is None and m.cv(None, 10) is None and m.cv(100, None) is None
    assert m.high_moe(0, 10) is False


def test_weighted_count_sums_with_weights_and_combines_moe_in_quadrature():
    est, moe, excluded = m.weighted_count([(100, 10, 1.0), (200, 20, 0.5), (None, 5, 1.0)])
    assert est == 200 and moe == pytest.approx(math.sqrt(10 ** 2 + 10 ** 2)) and excluded == 1


def test_weighted_median_is_household_weighted_average():
    assert m.weighted_median([(100000, 1000), (50000, 3000), (None, 500)]) == 62500
    assert m.weighted_median([(None, 1)]) is None


def test_derived_formulas_match_spec_8():
    assert m.pet_households_est(27600) == 15732
    assert m.population_growth_pct(81900, 71716) == pytest.approx(14.2, abs=0.01)
    assert m.population_growth_pct(100, 0) is None
    assert m.vets_per_10k(7, 27600) == pytest.approx(2.536, abs=1e-3)
    assert m.income_index_vs_us(118400, 75149) == pytest.approx(57.55, abs=0.01)
    assert m.revenue_per_establishment(4795, 7) == pytest.approx(685000, abs=1)
    assert m.revenue_per_establishment(4795, 0) is None


def test_opportunity_score_is_clamped_rounded_and_needs_all_inputs():
    # 40·(118400/140000) + 35·(14.2/40) + 25·(1 − 2.54/3) = 33.83 + 12.43 + 3.83 = 50.09 → 50
    assert m.opportunity_score(118400, 14.2, 2.54) == 50
    assert m.opportunity_score(200000, 60, 4.0) == 75       # income and growth capped, competition floor 0
    assert m.opportunity_score(0, 0, 0) == 25
    assert m.opportunity_score(None, 14.2, 2.54) is None


def test_competition_level_uses_the_design_thresholds():
    assert m.competition_level(1.39) == "Low" and m.competition_level(1.4) == "Moderate" and m.competition_level(2.2) == "High"
    assert m.competition_level(None) is None
```

- [ ] **Step 2: Implement `metrics.py`**

```python
"""Pure market-metric maths. Spec §8 (formulas, formula_version v1) and §14 (MOE/CV rules).
No I/O here so every rule is unit-testable with the spec's own numbers."""
from __future__ import annotations

import math

Z90 = 1.645
CV_THRESHOLD = 0.30
PET_RATE = 0.57  # documented national placeholder until a licensed regional rate is cleared (§8)
FORMULA_VERSION = "v1"
COMPETITION_LEVELS = ((1.4, "Low"), (2.2, "Moderate"))  # per 10k households; else "High" — the approved design's thresholds


def cv(estimate, moe) -> float | None:
    if estimate in (None, 0) or moe is None:
        return None
    return (float(moe) / Z90) / abs(float(estimate))


def high_moe(estimate, moe) -> bool:
    c = cv(estimate, moe)
    return c is not None and c > CV_THRESHOLD


def weighted_count(parts):
    """Σ w·est over parts with an estimate; MOE = sqrt(Σ (w·moe)²); returns (est, moe, excluded)."""
    est, var, excluded, used = 0.0, 0.0, 0, False
    for e, mo, w in parts:
        if e is None:
            excluded += 1
            continue
        used = True
        est += float(w) * float(e)
        var += (float(w) * float(mo or 0)) ** 2
    return (est if used else None, math.sqrt(var) if used else None, excluded)


def weighted_median(parts):
    num, den = 0.0, 0.0
    for v, w in parts:
        if v is None or w in (None, 0):
            continue
        num += float(v) * float(w)
        den += float(w)
    return num / den if den else None


def pet_households_est(hh):
    return None if hh is None else round(float(hh) * PET_RATE)


def population_growth_pct(now, prior):
    if now is None or prior in (None, 0):
        return None
    return (float(now) - float(prior)) / float(prior) * 100


def vets_per_10k(estab, hh):
    if estab is None or hh in (None, 0):
        return None
    return float(estab) / (float(hh) / 10000)


def income_index_vs_us(local, us):
    if local is None or us in (None, 0):
        return None
    return (float(local) - float(us)) / float(us) * 100


def revenue_per_establishment(payroll_k, estab):
    if payroll_k is None or estab in (None, 0):
        return None
    return float(payroll_k) * 1000 / float(estab)


def opportunity_score(income, growth, per10k):
    if income is None or growth is None or per10k is None:
        return None
    raw = 40 * min(float(income) / 140000, 1) + 35 * min(float(growth) / 40, 1) + 25 * max(0.0, 1 - float(per10k) / 3)
    return int(round(max(0.0, min(100.0, raw))))


def competition_level(per10k):
    if per10k is None:
        return None
    for threshold, label in COMPETITION_LEVELS:
        if float(per10k) < threshold:
            return label
    return "High"
```

Run: `poetry run pytest tests/census/test_metrics.py -q` → 6 passed.

- [ ] **Step 3: Failing materialisation test**

`tests/census/test_materialize.py`:
```python
import fakeredis
import pytest

from app.census import catchment, materialize
from tests.census.listing_fixtures import make_listing

PLACE = "POLYGON((-97.90 30.50,-97.70 30.50,-97.70 30.60,-97.90 30.60,-97.90 30.50))"  # covers both tracts and both ZCTAs


@pytest.fixture
def world(conn):
    """Two tracts, two ZCTAs, a place, a county, the nation; both ACS vintages; CBP; ZBP; active vintages; one geocoded listing."""
    lid = make_listing(conn)
    with conn.cursor() as cur:
        for i, gid in enumerate(["48491000001", "48491000002"]):
            x0 = -97.90 + 0.1 * i
            cur.execute("INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom) VALUES (%s,'140','2023',%s,'48','491','48491', ST_Multi(ST_GeomFromText(%s,4269)))",
                        (gid, gid, f"POLYGON(({x0} 30.50,{x0+0.1} 30.50,{x0+0.1} 30.60,{x0} 30.60,{x0} 30.50))"))
        for i, z in enumerate(["78613", "78664"]):
            x0 = -97.90 + 0.1 * i
            cur.execute("INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom) VALUES (%s,'860','2023',%s, ST_Multi(ST_GeomFromText(%s,4269)))",
                        (z, z, f"POLYGON(({x0} 30.50,{x0+0.1} 30.50,{x0+0.1} 30.60,{x0} 30.60,{x0} 30.50))"))
        cur.execute("INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES ('4813552','160','2023','Cedar Park city','48', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.80,30.55,4269))", (PLACE,))
        cur.execute("INSERT INTO ingest_run (dataset_key, vintage, started_at, status) VALUES ('acs5','2019–2023',now(),'succeeded'),('acs5_prior','2014–2018',now(),'succeeded'),('cbp','2022',now(),'succeeded'),('zbp','2022',now(),'succeeded')")
        cur.execute("SELECT id FROM ingest_run ORDER BY id"); r1, r2, r3, r4 = [x[0] for x in cur.fetchall()]
        tracts = [("48491000001", "B01003_001E", 4000, 200), ("48491000001", "B11001_001E", 1500, 95), ("48491000001", "B19013_001E", 118400, 9100),
                  ("48491000002", "B01003_001E", 3000, 300), ("48491000002", "B11001_001E", 1200, 80), ("48491000002", "B19013_001E", 98000, 12000)]
        cur.executemany("INSERT INTO acs_measure VALUES (%s,'140','2019–2023',%s,%s,%s,%s)", [(g, v, e, mo, r1) for g, v, e, mo in tracts])
        cur.executemany("INSERT INTO acs_measure VALUES ('4813552','160','2019–2023',%s,%s,%s,%s)", [("B01003_001E", 81900, 900, r1), ("B11001_001E", 27600, 600, r1), ("B19013_001E", 118400, 4100, r1)])
        cur.execute("INSERT INTO acs_measure VALUES ('4813552','160','2014–2018','B01003_001E',71716,850,%s)", (r2,))
        cur.execute("INSERT INTO acs_measure VALUES ('1','010','2019–2023','B19013_001E',75149,120,%s)", (r1,))
        cur.execute("INSERT INTO cbp_industry VALUES ('48491','050','2022','541940',210,3400,143850,NULL,%s)", (r3,))      # county benchmark: 210 practices
        cur.execute("INSERT INTO acs_measure VALUES ('48491','050','2019–2023','B11001_001E',230000,1200,%s)", (r1,))         # county households for the apportionment fallback
        cur.executemany("INSERT INTO zbp_industry (geo_id, vintage, naics_code, establishments, ingest_run_id) VALUES (%s,'2022','541940',%s,%s)", [("78613", 5, r4), ("78664", 2, r4)])
        cur.executemany("INSERT INTO active_vintage VALUES (%s,%s,now(),'test')", [("acs5", "2019–2023"), ("acs5_prior", "2014–2018"), ("cbp", "2022"), ("zbp", "2022"), ("tiger_cb", "2023")])
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, point, tract_geoid, county_geoid, place_geoid, geo_precision, geocoded_at, geocoder_vintage)
                       VALUES (%s,'h', ST_SetSRID(ST_Point(-97.85,30.55),4269), '48491000001','48491','4813552','rooftop',now(),'Current_Current')""", (lid,))
    catchment.build(conn, lid, "2023")
    return lid


def _metric(conn, lid, key, band="drive_10"):
    with conn.cursor() as cur:
        cur.execute("SELECT value_num::float, unit, is_derived, formula_version, moe::float, suppressed, suppress_reason, source_dataset, vintage, inputs FROM market_metric WHERE listing_id=%s AND band=%s AND metric_key=%s", (lid, band, key))
        return cur.fetchone()


def _weights(conn, lid, band, level):
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id, overlap_frac::float FROM practice_catchment WHERE listing_id=%s AND band=%s AND summary_level=%s", (lid, band, level))
        return dict(cur.fetchall())


def test_place_band_reproduces_the_design_style_city_figures(conn, world):
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    assert _metric(conn, world, "population", "place")[0] == 81900
    assert _metric(conn, world, "households", "place")[0] == 27600
    assert _metric(conn, world, "median_hh_income", "place")[0] == 118400 and _metric(conn, world, "median_hh_income", "place")[2] is False  # a real median, not approximate
    g = _metric(conn, world, "population_growth_pct", "place")
    assert g[0] == pytest.approx(14.2, abs=0.01) and g[9]["geo_level"] == "place" and g[9]["acs5_prior"] == "2014–2018"
    est = _metric(conn, world, "establishments", "place")
    assert est[0] == 7 and est[7] == "zbp" and est[9]["geo_level"] == "zcta" and est[9]["zctas"] == 2   # both ZCTAs lie fully inside the place
    assert _metric(conn, world, "vets_per_10k_households", "place")[0] == pytest.approx(7 / 2.76, rel=1e-6)
    assert _metric(conn, world, "opportunity_score", "place")[0] == 50


def test_catchment_bands_aggregate_tracts_and_zctas_coherently(conn, world):
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    wt = _weights(conn, world, "drive_10", "140"); wz = _weights(conn, world, "drive_10", "860")
    exp_pop = 4000 * wt["48491000001"] + 3000 * wt["48491000002"]
    exp_hh = 1500 * wt["48491000001"] + 1200 * wt["48491000002"]
    exp_estab = 5 * wz["78613"] + 2 * wz.get("78664", 0)
    assert _metric(conn, world, "population")[0] == pytest.approx(exp_pop, rel=1e-6)
    inc = _metric(conn, world, "median_hh_income")
    assert inc[2] is True and inc[3] == "v1"                                  # catchment median is an approximation → labelled derived
    est = _metric(conn, world, "establishments")
    assert est[0] == pytest.approx(exp_estab, rel=1e-6) and est[9]["geo_level"] == "zcta"
    assert _metric(conn, world, "vets_per_10k_households")[0] == pytest.approx(exp_estab / (exp_hh / 10000), rel=1e-6)   # same geography top and bottom (C1)
    g = _metric(conn, world, "population_growth_pct")
    assert g[0] == pytest.approx(14.2, abs=0.01) and g[9]["geo_level"] == "place"   # growth is place-level for every band (D12)
    rev = _metric(conn, world, "revenue_per_establishment")
    assert rev[0] == pytest.approx(143850 * 1000 / 210) and rev[7] == "cbp" and rev[9]["geo_level"] == "county"
    assert _metric(conn, world, "opportunity_score")[9]["components"].keys() == {"income", "growth", "vets_per_10k"}


def test_high_moe_suppresses_the_value_and_its_derivatives(conn, world):
    with conn.cursor() as cur:
        cur.execute("UPDATE acs_measure SET moe = 900 WHERE variable='B11001_001E' AND summary_level='140'")  # CV ≈ 0.36 on catchment households
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    hh = _metric(conn, world, "households")
    assert hh[5] is True and hh[6] == "high_moe" and hh[0] is not None   # row kept, flagged (§14)
    pets = _metric(conn, world, "pet_households_est")
    assert pets[5] is True and pets[6] == "input_suppressed"


def test_without_zbp_competition_falls_back_to_labelled_county_apportionment(conn, world):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='zbp'")
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    est = _metric(conn, world, "establishments", "place")
    assert est[7] == "cbp" and est[2] is True and est[9]["method"] == "county_apportioned"
    assert est[0] == pytest.approx(210 * 27600 / 230000)   # county establishments × place households ÷ county households


def test_uncleared_cbp_and_zbp_leave_no_competition_rows(conn, world):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key IN ('cbp','zbp')")
    n = materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    assert n == 3 * 6   # per band: population, households, median income, growth, pets, income index — no establishments/per10k/payroll/score
    assert _metric(conn, world, "establishments") is None and _metric(conn, world, "opportunity_score") is None
```
- [ ] **Step 4: Implement `materialize.py`**

```python
"""Materialise market_metric rows per (listing, band, metric, vintage) — spec §7, §8, §14; plan D10–D12.
The only writer of market_metric. Bands: place (city figures), drive_10, drive_20 (catchments)."""
from __future__ import annotations

import json
import time

from app.census import metrics as M
from app.census.registry import load as load_registry
from app.census.vintage import active

BANDS = ("place", "drive_10", "drive_20")

UPSERT = """
INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived, formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at, inputs)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
ON CONFLICT (listing_id, band, metric_key, vintage) DO UPDATE SET value_num = EXCLUDED.value_num, unit = EXCLUDED.unit, is_derived = EXCLUDED.is_derived,
  formula_version = EXCLUDED.formula_version, moe = EXCLUDED.moe, suppressed = EXCLUDED.suppressed, suppress_reason = EXCLUDED.suppress_reason,
  source_dataset = EXCLUDED.source_dataset, computed_at = now(), inputs = EXCLUDED.inputs
"""

PLACE_ZCTA_SQL = """
SELECT z.geo_id, LEAST(1.0, ST_Area(ST_Intersection(ST_Transform(z.geom,4326)::geography, ST_Transform(p.geom,4326)::geography)) / NULLIF(ST_Area(ST_Transform(z.geom,4326)::geography),0))
FROM geo_area p JOIN geo_area z ON z.summary_level='860' AND z.vintage=p.vintage AND ST_Intersects(z.geom, p.geom)
WHERE p.summary_level='160' AND p.vintage=%s AND p.geo_id=%s
"""


def _acs(cur, level, geo_ids, vintage, variable):
    cur.execute("SELECT geo_id, estimate, moe FROM acs_measure WHERE summary_level=%s AND vintage=%s AND variable=%s AND geo_id = ANY(%s)", (level, vintage, variable, list(geo_ids)))
    return {g: (float(e) if e is not None else None, float(m) if m is not None else None) for g, e, m in cur.fetchall()}


def _one(cur, level, geo_id, vintage, variable):
    return _acs(cur, level, [geo_id], vintage, variable).get(geo_id, (None, None))


def _zbp(cur, zctas, vintage):
    cur.execute("SELECT geo_id, establishments FROM zbp_industry WHERE summary_level='860' AND vintage=%s AND naics_code='541940' AND geo_id = ANY(%s)", (vintage, list(zctas)))
    return {g: e for g, e in cur.fetchall()}


def _row(lid, band, key, vintage, value, unit, *, derived=False, moe=None, suppressed=False, reason=None, source="acs5", inputs=None):
    return (lid, band, key, vintage, value, unit, derived, M.FORMULA_VERSION if derived else None, moe, suppressed, reason, source, json.dumps(inputs) if inputs else None)


class _Ctx:
    def __init__(self, conn, listing_id):
        reg = load_registry(conn)
        act = active(conn)
        self.acs_v, self.prior_v, self.cbp_v, self.zbp_v, self.geo_v = act.get("acs5"), act.get("acs5_prior"), act.get("cbp"), act.get("zbp"), act.get("tiger_cb")
        if not (self.acs_v and self.geo_v):
            raise RuntimeError("acs5 and tiger_cb must have active vintages before materialising")
        self.use_cbp = bool(self.cbp_v) and reg["cbp"].cleared
        self.use_zbp = bool(self.zbp_v) and reg["zbp"].cleared
        self.use_prior = bool(self.prior_v) and reg["acs5_prior"].cleared
        with conn.cursor() as cur:
            cur.execute("SELECT county_geoid, place_geoid FROM practice_location WHERE listing_id = %s", (listing_id,))
            row = cur.fetchone()
            self.county, self.place = row if row else (None, None)
            self.us_income = _one(cur, "010", "1", self.acs_v, "B19013_001E")[0]
            self.cbp = None
            if self.use_cbp and self.county:
                cur.execute("SELECT establishments, annual_payroll_k, flag FROM cbp_industry WHERE geo_id=%s AND summary_level='050' AND vintage=%s AND naics_code='541940'", (self.county, self.cbp_v))
                self.cbp = cur.fetchone()
            self.county_hh = _one(cur, "050", self.county, self.acs_v, "B11001_001E")[0] if self.county else None
            # Growth is place-level (D12); county fallback; None when neither exists.
            self.growth, self.growth_inputs = None, None
            if self.use_prior:
                for level, gid in (("160", self.place), ("050", self.county)):
                    if not gid:
                        continue
                    now, prior = _one(cur, level, gid, self.acs_v, "B01003_001E")[0], _one(cur, level, gid, self.prior_v, "B01003_001E")[0]
                    g = M.population_growth_pct(now, prior)
                    if g is not None:
                        self.growth, self.growth_inputs = g, {"acs5": self.acs_v, "acs5_prior": self.prior_v, "geo_level": "place" if level == "160" else "county"}
                        break


def _competition(cur, ctx, zcta_weights, hh_e):
    """Returns (establishments, source, derived, inputs) or None. ZBP over ZCTAs first; county apportionment fallback."""
    if ctx.use_zbp and zcta_weights:
        counts = _zbp(cur, zcta_weights.keys(), ctx.zbp_v)
        parts = [(counts.get(z), 0, w) for z, w in zcta_weights.items()]
        est, _, _ = M.weighted_count(parts)
        if est is not None:
            return est, "zbp", False, {"zbp": ctx.zbp_v, "geo_level": "zcta", "zctas": len(zcta_weights), "naics": "541940"}
    if ctx.cbp and ctx.county_hh and hh_e:
        est = ctx.cbp[0] * (hh_e / ctx.county_hh) if ctx.cbp[0] is not None else None
        if est is not None:
            return est, "cbp", True, {"cbp": ctx.cbp_v, "acs5": ctx.acs_v, "geo_level": "county", "method": "county_apportioned", "naics": "541940"}
    return None


def _band_inputs(cur, ctx, listing_id, band):
    """Returns (pop, pop_moe, hh, hh_moe, income, income_is_approx, zcta_weights)."""
    if band == "place":
        if not ctx.place:
            return None
        pop = _one(cur, "160", ctx.place, ctx.acs_v, "B01003_001E"); hh = _one(cur, "160", ctx.place, ctx.acs_v, "B11001_001E"); inc = _one(cur, "160", ctx.place, ctx.acs_v, "B19013_001E")
        cur.execute(PLACE_ZCTA_SQL, (ctx.geo_v, ctx.place))
        zw = {g: float(w) for g, w in cur.fetchall()}
        return pop[0], pop[1], hh[0], hh[1], inc[0], inc[1], False, zw
    cur.execute("SELECT summary_level, geo_id, overlap_frac FROM practice_catchment WHERE listing_id=%s AND band=%s AND vintage=%s", (listing_id, band, ctx.geo_v))
    tw, zw = {}, {}
    for level, g, w in cur.fetchall():
        (tw if level == "140" else zw)[g] = float(w)
    if not tw:
        return None
    pop, hh, inc = _acs(cur, "140", tw, ctx.acs_v, "B01003_001E"), _acs(cur, "140", tw, ctx.acs_v, "B11001_001E"), _acs(cur, "140", tw, ctx.acs_v, "B19013_001E")
    pop_e, pop_m, _ = M.weighted_count([(*pop.get(g, (None, None)), w) for g, w in tw.items()])
    hh_e, hh_m, _ = M.weighted_count([(*hh.get(g, (None, None)), w) for g, w in tw.items()])
    inc_e = M.weighted_median([(inc.get(g, (None, None))[0], (hh.get(g, (None, None))[0] or 0) * w) for g, w in tw.items()])
    return pop_e, pop_m, hh_e, hh_m, inc_e, None, True, zw


def materialize_listing(conn, redis, listing_id: str) -> int:
    ctx = _Ctx(conn, listing_id)
    rows = []
    with conn.cursor() as cur:
        for band in BANDS:
            got = _band_inputs(cur, ctx, listing_id, band)
            if not got:
                continue
            pop_e, pop_m, hh_e, hh_m, inc_e, inc_m, inc_approx, zw = got
            geo_level = "place" if band == "place" else "catchment"
            pop_sup, hh_sup = M.high_moe(pop_e, pop_m), M.high_moe(hh_e, hh_m)
            base = {"acs5": ctx.acs_v, "geo_level": geo_level}
            rows.append(_row(listing_id, band, "population", ctx.acs_v, pop_e, "count", moe=pop_m, suppressed=pop_sup, reason="high_moe" if pop_sup else None, inputs=base))
            rows.append(_row(listing_id, band, "households", ctx.acs_v, hh_e, "count", moe=hh_m, suppressed=hh_sup, reason="high_moe" if hh_sup else None, inputs=base))
            rows.append(_row(listing_id, band, "median_hh_income", ctx.acs_v, inc_e, "usd", derived=inc_approx, moe=inc_m,
                             inputs={**base, "note": "household-weighted average of tract medians"} if inc_approx else base))
            rows.append(_row(listing_id, band, "pet_households_est", ctx.acs_v, M.pet_households_est(hh_e), "count", derived=True,
                             suppressed=hh_sup, reason="input_suppressed" if hh_sup else None, inputs={**base, "pet_incidence_rate": M.PET_RATE}))
            rows.append(_row(listing_id, band, "income_index_vs_us", ctx.acs_v, M.income_index_vs_us(inc_e, ctx.us_income), "pct", derived=True, inputs=base))
            if ctx.growth is not None:
                rows.append(_row(listing_id, band, "population_growth_pct", ctx.acs_v, ctx.growth, "pct", derived=True, inputs=ctx.growth_inputs))
            comp = _competition(cur, ctx, zw, hh_e)
            if comp:
                est, source, derived, inputs = comp
                per10k = M.vets_per_10k(est, hh_e)
                rows.append(_row(listing_id, band, "establishments", inputs.get("zbp") or inputs.get("cbp"), est, "count", derived=derived, source=source, inputs=inputs))
                rows.append(_row(listing_id, band, "vets_per_10k_households", ctx.acs_v, per10k, "ratio", derived=True, source=source,
                                 suppressed=hh_sup, reason="input_suppressed" if hh_sup else None, inputs={**inputs, "acs5": ctx.acs_v}))
                if ctx.cbp:
                    rows.append(_row(listing_id, band, "revenue_per_establishment", ctx.cbp_v, M.revenue_per_establishment(ctx.cbp[1], ctx.cbp[0]), "usd", derived=True, source="cbp",
                                     inputs={"cbp": ctx.cbp_v, "geo_level": "county", "note": "payroll per establishment, not revenue"}))
                score = M.opportunity_score(inc_e, ctx.growth, per10k)
                if score is not None:
                    rows.append(_row(listing_id, band, "opportunity_score", ctx.acs_v, score, "score", derived=True, source="acs5",
                                     inputs={**inputs, "acs5": ctx.acs_v, "acs5_prior": ctx.prior_v, "components": {"income": inc_e, "growth": ctx.growth, "vets_per_10k": per10k}}))
        cur.executemany(UPSERT, rows)
    redis.set(f"listing:{listing_id}:market:version", int(time.time()))
    return len(rows)


def materialize_all(conn, redis) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT listing_id FROM practice_location")
        ids = [str(r[0]) for r in cur.fetchall()]
    return {lid: materialize_listing(conn, redis, lid) for lid in ids}
```

Run: `poetry run pytest tests/census -q` → all pass (`poetry add --group dev fakeredis` if not yet). Note the count in `test_uncleared_cbp_and_zbp_leave_no_competition_rows` is 3 bands × 6 metrics.

- [ ] **Step 5: Tasks and beat**

Add to `app/tasks/census.py`:
```python
@celery_app.task(name="census.materialize_metrics")
def materialize_metrics() -> dict:
    from app.cache import sync_redis
    from app.census import materialize
    return {"listings": len(materialize.materialize_all(_conn(), sync_redis()))}


@celery_app.task(name="census.backfill_listing")
def backfill_listing(listing_id: str) -> dict:
    from app.cache import sync_redis
    from app.census import catchment, materialize
    from app.census.vintage import active
    conn = _conn()
    geo_v = active(conn)["tiger_cb"]
    bands = catchment.build(conn, listing_id, geo_v)
    rows = materialize.materialize_listing(conn, sync_redis(), listing_id)
    return {"listing_id": listing_id, "catchment": bands, "rows": rows}
```
Beat: `"materialize-nightly": {"task": "census.materialize_metrics", "schedule": crontab(minute=0, hour=3)}` (03:00 UTC). CLI: `materialize [--listing ID]`. Tests: extend `test_tasks.py` for the two names and the nightly entry. Commit: `feat(census): §8 formulas, §14 suppression, three-band materialisation with ZBP competition and place-level growth`.

---

### Task B5: Market API — layers, markets, communities, listing panel; member gate; gate-versioned cache; backfill-on-miss

**Files:**
- Create: `app/api/market.py`, `app/api/access.py`, `app/db.py` (if not created in A9), `tests/census/test_market_api.py`
- Modify: `app/main.py` (include router before the `/api` catch-all), `app/config.py` (`market_data_public: bool = False`)

**Interfaces:** the endpoints in the API contract section. `access.market_access(request)` — no-op when `settings.market_data_public`, else `require_member(request)` (SP2; until SP2 lands, `require_member = auth_stub.require_operator`). `market.short_market_name(...)`. Cache keys `listing:{id}:market:v{version}:g{gate_version}` (TTL 86400 s); dedupe `backfill:{id}` (TTL 600 s).

- [ ] **Step 1: Failing tests**

`tests/census/test_market_api.py`:
```python
import httpx
import pytest
from httpx import ASGITransport

from app.cache import sync_redis
from app.census import gate, materialize
from app.config import settings
from app.main import create_app
from tests.census.test_materialize import world  # noqa: F401 — reuse the seeded listing fixture

H = {"Authorization": f"Bearer {settings.api_secret_key}"}   # SP2 replaces this with a member session


@pytest.fixture
async def client(scratch_dsn, monkeypatch):
    monkeypatch.setattr(settings, "database_url", scratch_dsn)
    r = sync_redis()
    for pat in ("listing:*", "backfill:*", "gate:*", "market:*"):
        for k in r.scan_iter(pat): r.delete(k)
    r.delete("celery")
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c


@pytest.fixture
def materialized(conn, world):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES ('12420','310','2023','Austin-Round Rock-San Marcos, TX Metro Area', ST_Multi(ST_GeomFromText('POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))',4269)), ST_Point(-97.75,30.31,4269))")
        cur.execute("UPDATE practice_location SET cbsa_geoid='12420' WHERE listing_id=%s", (world,))
    materialize.materialize_listing(conn, sync_redis(), world)
    return world


def test_short_market_name():
    from app.api.market import short_market_name
    assert short_market_name("Austin-Round Rock-San Marcos, TX Metro Area") == "Austin, TX"
    assert short_market_name("Sacramento-Roseville-Folsom, CA Metro Area") == "Sacramento, CA"


async def test_market_endpoints_require_a_member_unless_public(client, materialized, monkeypatch):
    for path in ("/api/layers", "/api/markets", "/api/markets/12420/communities", f"/api/listings/{materialized}/market"):
        assert (await client.get(path)).status_code == 401, path
    monkeypatch.setattr(settings, "market_data_public", True)
    assert (await client.get("/api/markets")).status_code == 200


async def test_layers_come_from_the_registry_with_gating_and_caveats(client, materialized, conn):
    layers = {l["key"]: l for l in (await client.get("/api/layers", headers=H)).json()}
    assert set(layers) == {"income", "pets", "growth", "households", "econ", "competition", "practices", "drive_10", "drive_20"}
    assert layers["income"]["source_label"].startswith("Source: U.S. Census Bureau, American Community Survey") and layers["income"]["enabled"] is True
    assert layers["competition"]["dataset_key"] == "zbp" and "proxy" in layers["competition"]["caveat"] and layers["competition"]["geo_level"] == "zcta"
    assert layers["pets"]["is_derived"] is True and "0.57" in layers["pets"]["caveat"]
    assert layers["growth"]["vintage"] == "2014–2018 → 2019–2023" and layers["growth"]["geo_level"] == "place"
    assert "approximation" in layers["drive_10"]["caveat"]
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='zbp'")
    gate.invalidate(sync_redis(), "zbp")
    layers = {l["key"]: l for l in (await client.get("/api/layers", headers=H)).json()}
    assert layers["competition"]["enabled"] is False


async def test_markets_lists_cbsas_with_published_listings(client, materialized):
    r = await client.get("/api/markets", headers=H)
    assert r.json() == [{"cbsa_geoid": "12420", "name": "Austin, TX", "center": [30.31, -97.75], "zoom": 10}]


async def test_communities_default_to_place_band_with_fixture_fields_and_competition(client, materialized):
    body = (await client.get("/api/markets/12420/communities", headers=H)).json()
    assert body["band"] == "place" and body["vintage"] == "2019–2023"
    c = body["communities"][0]
    assert c["name"] == "Cedar Park city" and c["pop"] == 81900 and c["hh"] == 27600 and c["income"] == 118400
    assert c["growth"] == pytest.approx(14.2, abs=0.01) and c["pets"] == 15732 and c["vets"] == 7 and c["econ"] == pytest.approx(143850 * 1000 / 210)
    assert c["competition"] == {"count": 7, "geo_level": "zcta", "zctas": 2, "per_10k_households": pytest.approx(7 / 2.76, rel=1e-6), "level": "High"}  # 2.54/10k ≥ 2.2 → High (design thresholds)
    assert c["location"] == "place_centroid" and (c["lat"], c["lng"]) == (30.55, -97.8)     # never the geocoded point unless disclosed
    drive = (await client.get("/api/markets/12420/communities?band=drive_10", headers=H)).json()
    assert drive["band"] == "drive_10" and drive["communities"][0]["pop"] < 81900


async def test_disclosed_location_returns_the_point_for_members(client, materialized, conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET location_disclosed = true WHERE id=%s", (materialized,))
    c = (await client.get("/api/markets/12420/communities", headers=H)).json()["communities"][0]
    assert c["location"] == "disclosed_point" and (c["lat"], c["lng"]) == (30.55, -97.85)


async def test_uncleared_layer_is_absent_within_60s(client, materialized, conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key IN ('zbp','cbp')")
    gate.invalidate(sync_redis(), "zbp"); gate.invalidate(sync_redis(), "cbp")
    c = (await client.get("/api/markets/12420/communities", headers=H)).json()["communities"][0]
    assert "vets" not in c and "econ" not in c and "competition" not in c and "pop" in c


async def test_listing_panel_is_cached_and_re_gated_on_read(client, materialized, conn):
    r = await client.get(f"/api/listings/{materialized}/market", headers=H)
    assert r.status_code == 200 and r.headers["x-cache"] == "miss"
    m = r.json()["metrics"]
    assert m["population"]["unit"] == "count" and m["establishments"]["source_dataset"] == "zbp"
    assert m["opportunity_score"]["components"].keys() == {"income", "growth", "vets_per_10k"}
    assert m["revenue_per_establishment"]["label"] == "Payroll per establishment"
    assert (await client.get(f"/api/listings/{materialized}/market", headers=H)).headers["x-cache"] == "hit"
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='blocked' WHERE dataset_key='zbp'")
    gate.invalidate(sync_redis(), "zbp")
    m2 = (await client.get(f"/api/listings/{materialized}/market", headers=H)).json()["metrics"]
    assert "establishments" not in m2 and "population" in m2          # gate version changed the key; blocked layer gone


async def test_place_band_panel_on_request(client, materialized):
    body = (await client.get(f"/api/listings/{materialized}/market?band=place", headers=H)).json()
    assert body["band"] == "place" and body["metrics"]["population"]["value"] == 81900


async def test_suppressed_metric_hides_value_but_keeps_reason(client, materialized, conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE market_metric SET suppressed=true, suppress_reason='high_moe' WHERE listing_id=%s AND metric_key='households'", (materialized,))
    sync_redis().incr(f"listing:{materialized}:market:version")
    hh = (await client.get(f"/api/listings/{materialized}/market", headers=H)).json()["metrics"]["households"]
    assert hh["value"] is None and hh["suppressed"] is True and hh["suppress_reason"] == "high_moe"


async def test_missing_metrics_404_and_enqueue_backfill_once_for_real_listings_only(client, conn):
    from tests.census.listing_fixtures import make_listing
    lid = make_listing(conn)
    r1 = await client.get(f"/api/listings/{lid}/market", headers=H)
    r2 = await client.get(f"/api/listings/{lid}/market", headers=H)
    assert r1.status_code == r2.status_code == 404 and r1.json()["error"]["code"] == "NO_MARKET_DATA"
    assert sync_redis().llen("celery") == 1          # one real message on the broker, deduped by backfill:{id}
    r3 = await client.get("/api/listings/00000000-0000-0000-0000-000000000000/market", headers=H)
    assert r3.status_code == 404 and r3.json()["error"]["code"] == "NOT_FOUND"
    assert sync_redis().llen("celery") == 1          # unknown ids never enqueue (red-team C4)
```

- [ ] **Step 2: Implement**

`app/api/access.py`:
```python
"""Market-data access rule (plan D13). Sub-project 2 provides require_member; until then the
operator token stands in. MARKET_DATA_PUBLIC=true is the VIN Foundation's 'public teaser' switch."""
from fastapi import Request

from app.config import settings

try:  # Sub-project 2
    from app.api.auth import require_member  # type: ignore
except ImportError:  # pragma: no cover — before SP2 lands
    from app.api.auth_stub import require_operator as require_member


def market_access(request: Request) -> None:
    if settings.market_data_public:
        return
    require_member(request)
```

`app/api/market.py`:
```python
"""Read-only market-data endpoints. Reads market_metric + geo_area + dataset_registry only
(spec §7, §10 hard rule): never a Census call on the request path; a miss for a real published
listing enqueues one backfill and returns the empty state."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text

from app.api.access import market_access
from app.cache import sync_redis
from app.census import gate
from app.census import metrics as M
from app.db import engine, sync_conn
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/api", dependencies=[Depends(market_access)])
PANEL_TTL = 86400
BACKFILL_DEDUPE_TTL = 600
BANDS = ("place", "drive_10", "drive_20")

# The nine approved layers. Labels are the design's; sources/vintages come from the registry at request time.
LAYERS = [
    {"key": "income", "label": "Median Household Income", "dataset_key": "acs5", "metric": "median_hh_income", "is_derived": False, "caveat": None},
    {"key": "pets", "label": "Pet Ownership (est.)", "dataset_key": "acs5", "metric": "pet_households_est", "is_derived": True,
     "caveat": f"Derived estimate: households × {M.PET_RATE} (national placeholder rate until a licensed regional rate is cleared)."},
    {"key": "growth", "label": "Population Growth", "dataset_key": "acs5_prior", "metric": "population_growth_pct", "is_derived": True, "geo_level": "place",
     "caveat": "Change between two ACS 5-year periods, measured for the listing's city/CDP."},
    {"key": "households", "label": "Households", "dataset_key": "acs5", "metric": "households", "is_derived": False, "caveat": None},
    {"key": "econ", "label": "Economic Profile", "dataset_key": "cbp", "metric": "revenue_per_establishment", "is_derived": True, "geo_level": "county",
     "caveat": "Payroll per establishment (NAICS 541940), not revenue; county level."},
    {"key": "competition", "label": "Veterinary Competition", "dataset_key": "zbp", "metric": "establishments", "is_derived": False, "geo_level": "zcta",
     "caveat": "Establishment counts (NAICS 541940) include corporate-owned and specialty locations; a proxy for competitive density, not a count of independent practices. ZIP-code counts aggregated to the community."},
    {"key": "practices", "label": "Practice Listings", "dataset_key": None, "metric": None, "is_derived": False, "caveat": None},
    {"key": "drive_10", "label": "5–10 min drive time", "dataset_key": None, "metric": None, "is_derived": True, "caveat": "Straight-line 8 km approximation of drive time."},
    {"key": "drive_20", "label": "10–20 min drive time", "dataset_key": None, "metric": None, "is_derived": True, "caveat": "Straight-line 16 km approximation of drive time."},
]
FIELD_FOR = {"pop": "population", "hh": "households", "income": "median_hh_income", "growth": "population_growth_pct",
             "pets": "pet_households_est", "econ": "revenue_per_establishment", "vets": "establishments"}
LABELS = {"revenue_per_establishment": "Payroll per establishment"}


def short_market_name(cbsa_name: str) -> str:
    city_part, _, rest = cbsa_name.partition(",")
    return f"{city_part.split('-')[0].strip()}, {rest.strip().split(' ')[0]}"


def _band(band: str | None, default: str) -> str:
    b = band or default
    if b not in BANDS:
        raise HTTPException(422, detail={"code": "BAD_BAND", "message": f"band must be one of {BANDS}"})
    return b


async def _active(conn) -> dict[str, str]:
    return dict((await conn.execute(text("SELECT dataset_key, vintage FROM active_vintage"))).all())


async def _registry(conn) -> dict[str, dict]:
    rows = (await conn.execute(text("SELECT dataset_key, attribution_text, vintage, license_status FROM dataset_registry"))).mappings().all()
    return {r["dataset_key"]: dict(r) for r in rows}


@router.get("/layers")
async def layers() -> list[dict]:
    r = sync_redis()
    async with engine.connect() as conn:
        reg, act = await _registry(conn), await _active(conn)
    out = []
    for l in LAYERS:
        ds = l["dataset_key"]
        enabled = gate.layer_enabled(r, sync_conn, ds) if ds else True
        vintage = (f"{act.get('acs5_prior')} → {act.get('acs5')}" if ds == "acs5_prior" else act.get(ds)) if ds else None
        out.append({"key": l["key"], "label": l["label"], "dataset_key": ds, "source_label": reg[ds]["attribution_text"] if ds else None,
                    "vintage": vintage, "geo_level": l.get("geo_level", "place|catchment" if ds else None), "enabled": enabled,
                    "is_derived": l["is_derived"], "caveat": l["caveat"]})
    return out


@router.get("/markets")
async def markets() -> list[dict]:
    async with engine.connect() as conn:
        act = await _active(conn)
        rows = (await conn.execute(text("""
            SELECT DISTINCT pl.cbsa_geoid, ga.name, ST_Y(ga.centroid) AS lat, ST_X(ga.centroid) AS lng
            FROM practice_location pl JOIN listing l ON l.id = pl.listing_id AND l.status = 'published'
            JOIN geo_area ga ON ga.geo_id = pl.cbsa_geoid AND ga.summary_level = '310' AND ga.vintage = :gv ORDER BY ga.name"""), {"gv": act.get("tiger_cb")})).mappings().all()
    return [{"cbsa_geoid": r["cbsa_geoid"], "name": short_market_name(r["name"]), "center": [round(r["lat"], 2), round(r["lng"], 2)], "zoom": 10} for r in rows]


@router.get("/markets/{cbsa}/communities")
async def communities(cbsa: str, band: str | None = Query(None)) -> dict:
    b = _band(band, "place")
    r = sync_redis()
    enabled = {ds: gate.layer_enabled(r, sync_conn, ds) for ds in ("acs5", "acs5_prior", "cbp", "zbp")}
    async with engine.connect() as conn:
        act, reg = await _active(conn), await _registry(conn)
        rows = (await conn.execute(text("""
            SELECT l.id AS listing_id, pl.geo_precision, COALESCE(pg.name, l.city) AS name, l.location_disclosed,
                   ST_Y(pl.point) AS pt_lat, ST_X(pl.point) AS pt_lng, ST_Y(pg.centroid) AS pl_lat, ST_X(pg.centroid) AS pl_lng,
                   mm.metric_key, mm.value_num, mm.suppressed, mm.source_dataset, mm.inputs
            FROM listing l JOIN practice_location pl ON pl.listing_id = l.id AND pl.cbsa_geoid = :cbsa
            LEFT JOIN geo_area pg ON pg.geo_id = pl.place_geoid AND pg.summary_level = '160' AND pg.vintage = :gv
            LEFT JOIN market_metric mm ON mm.listing_id = l.id AND mm.band = :band
            WHERE l.status = 'published'"""), {"cbsa": cbsa, "gv": act.get("tiger_cb"), "band": b})).mappings().all()
    by: dict[str, dict] = {}
    used = {"acs5"}
    for row in rows:
        lid = str(row["listing_id"])
        c = by.setdefault(lid, {"listing_id": lid, "name": row["name"], "geo_precision": row["geo_precision"], "suppressed": [],
                                "location": "disclosed_point" if (row["location_disclosed"] and row["pt_lat"] is not None) else "place_centroid",
                                "lat": row["pt_lat"] if row["location_disclosed"] else row["pl_lat"], "lng": row["pt_lng"] if row["location_disclosed"] else row["pl_lng"]})
        if not row["metric_key"] or not enabled.get(row["source_dataset"], True):
            continue
        for field, metric in FIELD_FOR.items():
            if row["metric_key"] == metric:
                used.add(row["source_dataset"])
                if row["suppressed"]:
                    c["suppressed"].append(field)
                else:
                    c[field] = float(row["value_num"]) if row["value_num"] is not None else None
        if row["metric_key"] == "establishments" and not row["suppressed"]:
            inputs = row["inputs"] or {}
            c["competition"] = {"count": float(row["value_num"]), "geo_level": inputs.get("geo_level"), "zctas": inputs.get("zctas")}
        if row["metric_key"] == "vets_per_10k_households" and not row["suppressed"] and "competition" in c:
            per = float(row["value_num"]) if row["value_num"] is not None else None
            c["competition"].update({"per_10k_households": per, "level": M.competition_level(per)})
    return {"band": b, "vintage": act.get("acs5"), "attribution": [reg[k]["attribution_text"] for k in sorted(used) if k in reg], "communities": list(by.values())}


@router.get("/listings/{listing_id}/market")
async def listing_market(listing_id: str, response: Response, band: str | None = Query(None)) -> dict:
    b = _band(band, "drive_10")
    r = sync_redis()
    version = r.get(f"listing:{listing_id}:market:version")
    key = f"listing:{listing_id}:market:{b}:v{int(version) if version else 0}:g{gate.version(r)}"
    cached = r.get(key)
    if cached:
        response.headers["x-cache"] = "hit"
        return json.loads(cached)
    async with engine.connect() as conn:
        exists = (await conn.execute(text("SELECT status FROM listing WHERE id = :id"), {"id": listing_id})).first()
        if not exists:
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "No such listing."})
        rows = (await conn.execute(text("""
            SELECT mm.*, pl.geo_precision FROM market_metric mm JOIN practice_location pl ON pl.listing_id = mm.listing_id
            WHERE mm.listing_id = :id AND mm.band = :band"""), {"id": listing_id, "band": b})).mappings().all()
        if not rows:
            if exists[0] == "published" and r.set(f"backfill:{listing_id}", "1", ex=BACKFILL_DEDUPE_TTL, nx=True):
                celery_app.send_task("census.backfill_listing", args=[listing_id])
            raise HTTPException(404, detail={"code": "NO_MARKET_DATA", "message": "Community data is being prepared for this listing."})
        reg = await _registry(conn)
    metrics = {}
    used = {"acs5"}
    for m in rows:
        if not gate.layer_enabled(r, sync_conn, m["source_dataset"]):
            continue
        used.add(m["source_dataset"])
        inputs = m["inputs"] or {}
        entry = {"value": None if m["suppressed"] else (float(m["value_num"]) if m["value_num"] is not None else None), "unit": m["unit"],
                 "is_derived": m["is_derived"], "formula_version": m["formula_version"], "moe": float(m["moe"]) if m["moe"] is not None else None,
                 "suppressed": m["suppressed"], "suppress_reason": m["suppress_reason"], "source_dataset": m["source_dataset"], "vintage": m["vintage"],
                 "geo_level": inputs.get("geo_level"), "inputs": {k: v for k, v in inputs.items() if k in ("acs5", "acs5_prior", "cbp", "zbp")} or None}
        if "components" in inputs: entry["components"] = inputs["components"]
        if "pet_incidence_rate" in inputs: entry["assumed_rate"] = inputs["pet_incidence_rate"]
        if m["metric_key"] == "median_hh_income" and m["is_derived"]: entry["approximate"] = True
        if m["metric_key"] in LABELS: entry["label"] = LABELS[m["metric_key"]]
        metrics[m["metric_key"]] = entry
    body = {"listing_id": listing_id, "band": b, "geo_precision": rows[0]["geo_precision"], "vintage": rows[0]["vintage"],
            "computed_at": max(m["computed_at"] for m in rows).isoformat(), "metrics": metrics,
            "attribution": [reg[k]["attribution_text"] for k in sorted(used) if k in reg]}
    r.set(key, json.dumps(body), ex=PANEL_TTL)
    response.headers["x-cache"] = "miss"
    return body
```

`app/db.py`:
```python
import psycopg2
from sqlalchemy.ext.asyncio import create_async_engine

from app.checks import async_dsn
from app.config import settings

engine = create_async_engine(async_dsn(settings.database_url), pool_pre_ping=True)


def sync_conn():
    c = psycopg2.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    c.autocommit = True
    return c
```
Add `market_data_public: bool = False` to `Settings`. Wire `market.router` in `main.py` before the catch-all. Run: `poetry run pytest -q` → all pass. Commit: `feat(census): member-gated market API — layers, markets, communities (place/catchment), panel with gate-versioned cache`.

---

### Task B6: Integration contract for Sub-project 2 and the admin Data Sources tab

**Files:**
- Create: `docs/integrations/market-data-api.md`
- Modify: `CLAUDE.md` (pointer), `DEPLOY.md` (Phase A exit runbook + variables)

- [ ] **Step 1: Write the contract** — `docs/integrations/market-data-api.md` containing: the API contract section of this plan verbatim; the **fixture → field mapping** table below; the admin tab mapping; the copy rules.

| Prototype source (`logic.js`) | Replaced by |
|---|---|
| `MARKETS` (name → center/zoom) | `GET /api/markets` |
| `communities()` → `pop, hh, income, growth, pets, econ, vets` per listing | `GET /api/markets/{cbsa}/communities` → same field names, numeric |
| `VETS[id]`, `ECON_K[id]` | `communities[].vets`, `communities[].econ` (already ×1000, i.e. dollars) |
| `P[].pop/growth/income/hh` strings on the detail page | `GET /api/listings/{id}/market` → `metrics.population.value` etc.; format client-side with the prototype's `fmtMetric` |
| `marketPanel()` `incomeNat = 75149`, `per10k`, `score` | `metrics.income_index_vs_us`, `metrics.vets_per_10k_households`, `metrics.opportunity_score` (+ `components`) |
| Admin **Data Sources** tab rows | `GET /api/admin/data-sources` (columns: Dataset · Source and license · Status · Action → `POST …/license`) |
| Data Layers rows / footer cards `on` state, card `src` text ("Census ACS 5-year", "Census CBP, NAICS 541940", …), legend titles | `GET /api/layers` → `label`, `source_label`, `vintage`, `caveat`, `enabled`. A disabled layer's row and card disappear (spec §11); no hard-coded source copy remains (spec §12) |
| `layers.competition` dots (`dot(size, 'rgba(120,86,190,.75)')`, size `8 + min(n, 14)`, tooltip "N veterinary establishments") | `communities[].competition.count`; tooltip gains the proxy caveat from `/api/layers` |
| Panel `compBars` Low/Moderate/High (`per10k < 1.4 / < 2.2`) and `per10k` | `communities[].competition.level` / `metrics.vets_per_10k_households` — thresholds now live in `metrics.competition_level` and are returned, not recomputed |
| `MARKETS[market].center/zoom`, `mdSubline: "… metro · within 20 miles"` | `GET /api/markets`; the "within 20 miles" copy stays a results-radius statement (unchanged) |

**Design-vs-spec copy conflicts (route to the VIN Foundation / Claude Design before SP2 wires them):** (1) the card/legend copy "Growth since 2015" must become a vintage statement ("ACS 2014–2018 → 2019–2023"); (2) "5–10 min drive time" / "10–20 min drive time" need the spec §8 approximation label ("≈ 8 km straight-line"); (3) the competition card needs the §5 proxy sentence. The API supplies all three strings via `/api/layers`; the approved design must be updated to show them.

Copy rules the frontend must honour when wiring (spec §8/§12/§14): every figure shows dataset + vintage (`attribution[]` and `metrics[].vintage`); `is_derived` → "derived estimate"; `median_hh_income.approximate` → "approximate"; `suppressed` → "Estimate too imprecise to show at this geography"; `geo_precision != 'rooftop'` → "approximate community data"; `opportunity_score` always with its three components and never near the price.

- [ ] **Step 2: Commit and hand off**

```bash
git add -A && git commit -m "docs(census): market-data API integration contract for Sub-project 2

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/census-data-layer && git push production feat/census-data-layer
```

**Phase B exit:** on QA, geocode a real listing (`census.geocode_listing`), confirm `practice_location`, `practice_catchment`, `market_metric` rows, `GET /api/listings/{id}/market` returns the panel with attribution, `GET /api/markets/12420/communities` returns the listing's community with the fixture field names; flip `cbp` to `unresolved` via the admin endpoint and confirm `vets`/`econ` vanish within 60 s and reappear when cleared.

---

## Layer rendering contract (the nine approved layers, their data, their source)

Rendering stays exactly as the approved components do it (`MarketMapView.vue`, `logic.js`); this table pins where each pixel's number and label come from once fixtures are replaced.

| Layer (design key) | Drawn as (existing component behaviour) | Number(s) | Data path | Geography | Source label & caveat (from `/api/layers`) | Gate |
|---|---|---|---|---|---|---|
| Practice Listings (`practices`) | price pins `pricePin(label, active)` at practice/generalized point | asking price | SP2 listings API | point or place centroid (D8) | — | published listings only |
| 5–10 min drive time (`drive5` in code, `drive_10` band) | `L.circle(hub, 8000 m, #003a70, .2)` | — | client-side; hub = selected practice or market center | 8 km buffer | "Straight-line 8 km approximation of drive time." | always |
| 10–20 min drive time (`drive10` in code, `drive_20` band) | `L.circle(hub, 16000 m, #339dde, .16)` | — | client-side | 16 km buffer | "Straight-line 16 km approximation …" | always |
| Median Household Income (`income`) | community bubble `dot(16 + 30·t, ramp)`; legend buckets `<$60K … >$150K` | `communities[].income` | `market_metric.median_hh_income` (band `place` by default) | place (drive bands on request) | ACS attribution + vintage; `approximate` for catchment bands | `acs5` cleared |
| Pet Ownership (est.) (`pets`) | bubble, orange ramp | `communities[].pets` | `pet_households_est` (derived, rate 0.57) | place | ACS attribution; "Derived estimate: households × 0.57 …" | `acs5` cleared |
| Population Growth (`growth`) | bubble, green ramp | `communities[].growth` | `population_growth_pct` (derived) | **place** (D12) | "ACS 2014–2018 → 2019–2023 …" | `acs5_prior` cleared |
| Households (`households`) | bubble, blue ramp | `communities[].hh` | `households` | place | ACS attribution | `acs5` cleared |
| Economic Profile (`econ`) | bubble, violet ramp; buckets `<$450K … >$900K` | `communities[].econ` | `revenue_per_establishment` (CBP payroll ÷ establishments) | **county** | CBP attribution; "Payroll per establishment, not revenue; county level." | `cbp` cleared |
| Veterinary Competition (`competition`) | offset dot `[lat+.012, lng+.012]`, size `8 + min(n,14)`, `rgba(120,86,190,.75)`; tooltip "N veterinary establishments"; panel bars Low/Moderate/High | `communities[].vets`, `communities[].competition.{count, per_10k_households, level}` | `establishments` from **ZBP** ZIP counts aggregated over the community's ZCTAs (fallback: county CBP apportioned by household share, labelled derived). Phase C (Task C1, D17): `competition.freshness.{level_live, diverges, as_of}` from the Places Aggregate API — a bucket and a flag, never a count | ZCTA→place / catchment | ZBP attribution; "… proxy for competitive density, not a count of independent practices. ZIP-code counts aggregated to the community." Freshness: the `google_places_aggregate` attribution text | `zbp` cleared (fallback needs `cbp`); `freshness` only while `google_places_aggregate` is cleared |

Sources in one sentence for stakeholders: demographics, households, income and growth are the Census Bureau's American Community Survey; competition is the Census Bureau's count of veterinary establishments (NAICS 541940) by ZIP code, with the county total as a benchmark; the economic profile is Census payroll per establishment; pet ownership is our estimate from households; drive-time rings are straight-line approximations until a routing licence exists. No third-party practice list is used (spec §12); no Google Maps data is used in V1 (D15), and the 2017 Google Places export is blocked.

## Phase C — Deferred by design (each has a stated trigger)

| Item | Spec ref | Trigger to build | Sketch |
|---|---|---|---|
| Tract choropleth vector tiles | §7 "Choropleth tiles", §10 CDN row | The approved design gains tract-level shading (today it draws community bubbles) | Nightly task: for each cleared value layer and z6–z12 over CBSAs with listings, `ST_AsMVT(ST_AsMVTGeom(...))` per tile → bucket `tiles/{metric}/{vintage}/{z}/{x}/{y}.pbf`, immutable, 30-day cache; Leaflet.VectorGrid client; new path per vintage flip |
| True isochrones (`isochrone_v2`) | §8 drive_catchment V2 | VIN Foundation licenses a routing engine (§15) | Replace `catchment.build` SQL with polygons from the engine; keep `method` column; rerun materialise |
| Satellite basemap | §2 imagery, §12 | Written licence naming commercial web display + attribution string | Flip `imagery` to `cleared` via admin; frontend shows the Satellite tab only when `GET /api/admin/data-sources` (or a public `/api/layers`) reports it cleared |
| Licensed pet-ownership rate | §8 pet_households_est, §15 | Licence signed | New dataset row `pet_ownership` cleared; `PET_RATE` becomes a per-CBSA table; `formula_version` → `v2` |
| AIES revenue benchmark | §2 aies, §15 | Dataset ID and geography confirmed | New loader + `revenue_per_establishment` v2 from AIES receipts |
| Block groups (`150`) | §6 | A buyer-facing need for sub-tract detail | Add `150` to `GEOGRAPHIES` and `BOUNDARY_FILES`; off by default |
| Auto-extend `market_state` | D4 | First listing geocoded outside TX/CA/FL/GA | `geocode.resolve` inserts the state and enqueues `census.load_tiger` + `census.load_acs` for it |
| Individual competitor locations (points, not counts) | §12 "Practice location databases … out of scope for V1"; D16 | The VIN Foundation approves a competitor-points layer and one source, in this order of preference: **Overture Maps Places** (`overture_places`), **Foursquare OS Places** (`fsq_os_places`), **VIN's member practice directory** (`vin_practice_directory`, VIN-owned; privacy/consent review and an opt-out). Purchased or scraped lists — including the 2017 Google Places export (D15) — stay blocked. | **Task C2 (sketch):** monthly Celery task downloads the release's `theme=places/type=place` GeoParquet for the market states' bounding boxes with pyarrow + shapely (no GDAL), asserts the release taxonomy contains `veterinarian` and aborts on drift (the ACS variable-check pattern), filters `categories.primary = 'veterinarian'` (or `taxonomy.primary` once Overture removes `categories`, September 2026), keeps `id, names.primary, addresses[0], geometry, confidence, sources[]`, writes `competitor_location(provider, provider_id, name, address, geom geography, confidence, sources jsonb, release, active bool)` behind a licence-gate trigger like `market_metric`'s; a member-gated `competition.points` layer (per-point tooltip: name, source, release); `competition.count` gains a second, labelled variant "practices located within the catchment (Overture, release YYYY-MM)" while the ZBP count remains the spec §5 figure; attribution from the registry row |
| Competition freshness signal (Google) | D17; SST §13 | VIN Foundation counsel accepts SST §13 (Customer Values; 30-day count cache) and a Google Cloud billing account with the Places Aggregate API enabled exists; `google_places_aggregate` cleared in the registry; `GOOGLE_MAPS_API_KEY` set on `worker` out-of-band | Task C1 below — the only Google Maps Platform mechanism whose terms fit a stored, Leaflet-rendered market layer |
| Tract-level growth (catchment bands) | D12 | Need for sub-place growth | Load the 2010→2020 tract relationship file (`tab20_tract20_tract10_natl.txt`), apportion 2014–2018 tract populations onto 2020 tracts by land-area share, then compute growth per catchment; `formula_version` → `v2` |
| Population-weighted apportionment | §7 area-overlap weights | Catchments that cut large, unevenly populated tracts | Weight tract overlap by block-group population instead of area (`150` rows); `method` → `euclidean_buffer_v1_bgweighted` |

### Task C1 (gated, Phase C): Places Aggregate freshness signal — D17

**Gate:** start only when `dataset_registry.google_places_aggregate.license_status = 'cleared'` (VIN Foundation counsel has accepted SST §13 **and** has read Terms §3.2.3(e) — "with or near a non-Google Map in a Customer Application" — as not reaching a derived bucket shown beside Leaflet; a Google Cloud project with the Places Aggregate API enabled and billing exists) and `GOOGLE_MAPS_API_KEY` is set on the `worker` service out-of-band — `railway variables --set GOOGLE_MAPS_API_KEY=<key> --service worker --environment <env>` after the 🚦 `railway status` check. The key never appears in chat, git or `.env.example`. Until then this task is documentation. **Superseded if the VIN Foundation chooses Google as the map engine (decision G0 in `docs/decisions/2026-09-05-competition-presentation-options.md`): the greenfield Google plan shows the live Aggregate count directly on the Google map and needs no Customer Values.**

**Files:**
- Create: `migrations/062_market_freshness.sql`, `app/census/google_aggregate.py`, `app/census/freshness.py`, `app/tasks/freshness.py`, `tests/census/test_google_aggregate.py`, `tests/census/test_freshness.py`
- Modify: `app/config.py` (add `google_maps_api_key: str | None = None`), `app/api/market.py:communities` (attach `freshness`), `app/api/market.py:layers` (attach `freshness_attribution`), `app/tasks/celery_app.py` (two beat entries), `tests/census/test_tasks.py`, `tests/api/test_market_api.py`

**Interfaces:**
- Consumes: `registry.is_cleared(conn, "google_places_aggregate")`, `registry.load(conn)["tiger_cb"].vintage`; `metrics.vets_per_10k(estab, hh)`, `metrics.competition_level(per10k)`; `catchment.BANDS`; `practice_location.point`, `practice_location.place_geoid`; `market_metric` rows `households` and `vets_per_10k_households` per band; `db.sync_conn()`; `gate.version()` (already in the B5 cache key — freshness rides the same key).
- Produces: `google_aggregate.Circle(lat, lng, radius_m)`, `google_aggregate.Polygon(coords)`, `google_aggregate.request_body(area) -> dict`, `google_aggregate.count_operational(http, area, api_key) -> int`; `freshness.Freshness(level_live, diverges)`, `freshness.compute(count, households, zbp_level) -> Freshness`, `freshness.write(conn, listing_id, band, f, now=None)`, `freshness.purge_expired(conn) -> int`, `freshness.refresh_listing(conn, http, listing_id, api_key) -> int` (bands written); Celery tasks `freshness.refresh_all`, `freshness.refresh_one(listing_id)`, `freshness.purge_expired`; `freshness.STALE_AFTER_DAYS = 7`; table `market_freshness`.

- [ ] **Step 1: Failing tests**

`tests/census/test_google_aggregate.py`:
```python
import json

import httpx
import pytest

from app.census import google_aggregate as G


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_count_operational_sends_a_count_insight_for_operational_veterinary_care_and_returns_the_count():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["key"], seen["json"] = str(req.url), req.headers["X-Goog-Api-Key"], json.loads(req.content)
        return httpx.Response(200, json={"count": 7})

    assert G.count_operational(_client(handler), G.Circle(30.27, -97.74, 8000), "k") == 7
    assert seen["url"] == G.ENDPOINT and seen["key"] == "k"
    assert seen["json"] == {
        "insights": ["INSIGHT_COUNT"],
        "filter": {
            "locationFilter": {"circle": {"latLng": {"latitude": 30.27, "longitude": -97.74}, "radius": 8000}},
            "typeFilter": {"includedTypes": ["veterinary_care"]},
            "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
        },
    }


def test_polygon_filter_uses_lat_lng_objects_in_ring_order():
    body = G.request_body(G.Polygon(((30.0, -97.0), (30.0, -97.1), (30.1, -97.1), (30.0, -97.0))))
    assert body["filter"]["locationFilter"] == {"customArea": {"polygon": {"coordinates": [
        {"latitude": 30.0, "longitude": -97.0}, {"latitude": 30.0, "longitude": -97.1},
        {"latitude": 30.1, "longitude": -97.1}, {"latitude": 30.0, "longitude": -97.0}]}}}


def test_non_2xx_raises_and_no_count_is_invented():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})

    with pytest.raises(httpx.HTTPStatusError):
        G.count_operational(_client(handler), G.Circle(1.0, 2.0, 8000), "k")
```

`tests/census/test_freshness.py` (uses the Phase B `conn` and `world` fixtures; `world` is the listing id):
```python
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.census import freshness as F


@pytest.fixture
def cleared_google(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key='google_places_aggregate'")
    conn.commit()


def test_compute_buckets_with_the_design_thresholds_and_flags_divergence():
    assert F.compute(7, 27600, "Moderate") == F.Freshness(level_live="High", diverges=True)   # 7 / 2.76 = 2.54 per 10k ≥ 2.2
    assert F.compute(3, 27600, "Low") == F.Freshness(level_live="Low", diverges=False)        # 1.09 per 10k < 1.4


def test_freshness_table_persists_no_count_ratio_or_place_ids(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'market_freshness'")
        cols = {r[0] for r in cur.fetchall()}
    assert cols == {"listing_id", "band", "provider", "level_live", "diverges", "fetched_at", "expires_at"}  # SST §13.2: the POI count never lands


def test_write_sets_a_30_day_expiry_and_upserts(conn, world, cleared_google):
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    F.write(conn, world, "place", F.Freshness("High", True), now=now)
    F.write(conn, world, "place", F.Freshness("Moderate", False), now=now + timedelta(days=1))
    with conn.cursor() as cur:
        cur.execute("SELECT level_live, diverges, expires_at - fetched_at FROM market_freshness WHERE listing_id = %s", (world,))
        assert cur.fetchall() == [("Moderate", False, timedelta(days=30))]


def test_uncleared_provider_cannot_be_written(conn, world):
    with pytest.raises(Exception) as e:
        F.write(conn, world, "place", F.Freshness("Low", False))
    assert "not cleared" in str(e.value)


def test_purge_removes_only_expired_rows(conn, world, cleared_google):
    F.write(conn, world, "place", F.Freshness("Low", False), now=datetime.now(timezone.utc) - timedelta(days=31))
    F.write(conn, world, "drive_10", F.Freshness("Low", False))
    assert F.purge_expired(conn) == 1


def test_refresh_listing_writes_three_bands_and_falls_back_to_a_circle_when_the_polygon_is_rejected(conn, world, cleared_google, materialized):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = req.read().decode()
        calls.append("polygon" if "customArea" in body else "circle")
        if "customArea" in body:
            return httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT"}})
        return httpx.Response(200, json={"count": 9})

    n = F.refresh_listing(conn, httpx.Client(transport=httpx.MockTransport(handler)), world, "k")
    assert n == 3 and calls == ["polygon", "circle", "circle", "circle"]   # place polygon → 400 → 8 km circle; then drive_10, drive_20
    with conn.cursor() as cur:
        cur.execute("SELECT band, level_live FROM market_freshness WHERE listing_id = %s ORDER BY band", (world,))
        rows = dict(cur.fetchall())
    assert set(rows) == {"drive_10", "drive_20", "place"} and rows["place"] == "High"   # 9 / 2.76 = 3.26 per 10k


def test_refresh_listing_is_a_no_op_while_the_gate_is_closed(conn, world, materialized):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("no Google call may leave the process while google_places_aggregate is uncleared")

    assert F.refresh_listing(conn, httpx.Client(transport=httpx.MockTransport(handler)), world, "k") == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/census/test_google_aggregate.py tests/census/test_freshness.py -q`
Expected: FAIL — `ModuleNotFoundError: app.census.google_aggregate`, then `relation "market_freshness" does not exist`.

- [ ] **Step 3: Migration and modules**

`migrations/062_market_freshness.sql`:
```sql
-- D17: persisted "Customer Values" derived from Google Places Aggregate counts (SST §13.1).
-- Deliberately no count, ratio or place-id column: the POI Count may live at most 30 days
-- (SST §13.2) and never reaches this table; the API returns level_live and diverges only.
CREATE TABLE market_freshness (
  listing_id  uuid NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  band        text NOT NULL CHECK (band IN ('place','drive_10','drive_20')),
  provider    text NOT NULL DEFAULT 'google_places_aggregate' REFERENCES dataset_registry(dataset_key),
  level_live  text NOT NULL CHECK (level_live IN ('Low','Moderate','High')),
  diverges    boolean NOT NULL,
  fetched_at  timestamptz NOT NULL,
  expires_at  timestamptz NOT NULL,
  PRIMARY KEY (listing_id, band, provider)
);

CREATE OR REPLACE FUNCTION market_freshness_license_gate() RETURNS trigger AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM dataset_registry WHERE dataset_key = NEW.provider AND license_status = 'cleared') THEN
    RAISE EXCEPTION 'dataset % is not cleared for use', NEW.provider USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER market_freshness_license_gate BEFORE INSERT OR UPDATE ON market_freshness
  FOR EACH ROW EXECUTE FUNCTION market_freshness_license_gate();
```

`app/census/google_aggregate.py`:
```python
"""Places Aggregate API client (D17). Returns one integer and nothing else.

Terms that shape this module: Google Maps Platform Service Specific Terms §13 — the POI Count may be
cached for at most 30 days and only to compute a "Customer Value"; Terms §3.2.3(e) — nothing
Google-authored is drawn on the Leaflet map. Callers therefore never persist the returned count.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

ENDPOINT = "https://areainsights.googleapis.com/v1:computeInsights"
PLACE_TYPE = "veterinary_care"  # Places API type, Table A


@dataclass(frozen=True)
class Circle:
    lat: float
    lng: float
    radius_m: int

    def location_filter(self) -> dict:
        return {"circle": {"latLng": {"latitude": self.lat, "longitude": self.lng}, "radius": self.radius_m}}


@dataclass(frozen=True)
class Polygon:
    coords: tuple[tuple[float, float], ...]  # (lat, lng) ring, counter-clockwise, closed

    def location_filter(self) -> dict:
        return {"customArea": {"polygon": {"coordinates": [{"latitude": a, "longitude": b} for a, b in self.coords]}}}


def request_body(area: Circle | Polygon) -> dict:
    return {
        "insights": ["INSIGHT_COUNT"],
        "filter": {
            "locationFilter": area.location_filter(),
            "typeFilter": {"includedTypes": [PLACE_TYPE]},
            "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
        },
    }


def count_operational(http: httpx.Client, area: Circle | Polygon, api_key: str) -> int:
    """One computeInsights call. Raises httpx.HTTPStatusError on any non-2xx (the monthly task logs and skips)."""
    r = http.post(ENDPOINT, json=request_body(area), headers={"X-Goog-Api-Key": api_key},
                  timeout=httpx.Timeout(45.0, connect=15.0))
    r.raise_for_status()
    return int(r.json().get("count", 0))
```

`app/census/freshness.py`:
```python
"""Customer Values from Google counts (D17): a level bucket and a divergence flag — nothing invertible."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.census import google_aggregate as G
from app.census import metrics as M
from app.census.catchment import BANDS
from app.census.registry import is_cleared, load

CACHE_DAYS = 30  # SST §13.2
PROVIDER = "google_places_aggregate"
PLACE_SIMPLIFY_DEG = 0.002  # ≈ 200 m; keeps city polygons to a few hundred vertices
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Freshness:
    level_live: str
    diverges: bool


def compute(count: int, households: float, zbp_level: str) -> Freshness:
    live = M.competition_level(M.vets_per_10k(count, households))
    return Freshness(level_live=live, diverges=(live != zbp_level))


def write(conn, listing_id, band: str, f: Freshness, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO market_freshness (listing_id, band, provider, level_live, diverges, fetched_at, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (listing_id, band, provider) DO UPDATE
                 SET level_live = EXCLUDED.level_live, diverges = EXCLUDED.diverges,
                     fetched_at = EXCLUDED.fetched_at, expires_at = EXCLUDED.expires_at""",
            (listing_id, band, PROVIDER, f.level_live, f.diverges, now, now + timedelta(days=CACHE_DAYS)),
        )


def purge_expired(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM market_freshness WHERE expires_at < now()")
        return cur.rowcount


def _shapes(cur, listing_id, band: str, geo_vintage: str) -> tuple[G.Circle | G.Polygon, G.Circle] | None:
    """(area to query, circle to fall back to). Bands drive_10/drive_20 are circles; 'place' is the city polygon."""
    cur.execute("SELECT ST_Y(ST_Transform(point, 4326)) AS lat, ST_X(ST_Transform(point, 4326)) AS lng, place_geoid "
                "FROM practice_location WHERE listing_id = %s", (listing_id,))
    row = cur.fetchone()
    if not row or row["lat"] is None:
        return None
    circle = G.Circle(row["lat"], row["lng"], BANDS.get(band, BANDS["drive_10"]))
    if band != "place" or not row["place_geoid"]:
        return circle, circle
    cur.execute(
        """WITH parts AS (
             SELECT (ST_Dump(ST_Transform(geom, 4326))).geom AS g
               FROM geo_area WHERE summary_level = '160' AND geo_id = %s AND vintage = %s)
           SELECT ST_AsGeoJSON(ST_ForcePolygonCCW(ST_SimplifyPreserveTopology(g, %s))) AS gj
             FROM parts ORDER BY ST_Area(g) DESC LIMIT 1""",
        (row["place_geoid"], geo_vintage, PLACE_SIMPLIFY_DEG),
    )
    g = cur.fetchone()
    if not g:
        return circle, circle
    ring = json.loads(g["gj"])["coordinates"][0]
    return G.Polygon(tuple((lat, lng) for lng, lat in ring)), circle


def _inputs(cur, listing_id, band: str) -> tuple[float, str] | None:
    cur.execute(
        """SELECT metric_key, value_num FROM market_metric
            WHERE listing_id = %s AND band = %s AND NOT suppressed
              AND metric_key IN ('households', 'vets_per_10k_households')""",
        (listing_id, band),
    )
    vals = {r["metric_key"]: float(r["value_num"]) for r in cur.fetchall() if r["value_num"] is not None}
    if vals.get("households", 0) <= 0 or "vets_per_10k_households" not in vals:
        return None
    return vals["households"], M.competition_level(vals["vets_per_10k_households"])


def refresh_listing(conn, http: httpx.Client, listing_id, api_key: str) -> int:
    """Fetch, derive, persist the two Customer Values per band. The count dies with this stack frame."""
    if not is_cleared(conn, PROVIDER):
        return 0
    geo_vintage = load(conn)["tiger_cb"].vintage
    written = 0
    with conn.cursor() as cur:
        for band in ("place", "drive_10", "drive_20"):
            shapes, inputs = _shapes(cur, listing_id, band, geo_vintage), _inputs(cur, listing_id, band)
            if shapes is None or inputs is None:
                continue
            area, fallback = shapes
            try:
                count = G.count_operational(http, area, api_key)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400 and area is not fallback:
                    count = G.count_operational(http, fallback, api_key)  # polygon rejected (size/vertex limit): 8 km circle
                else:
                    log.warning("freshness skipped listing=%s band=%s status=%s", listing_id, band, e.response.status_code)
                    continue
            households, zbp_level = inputs
            write(conn, listing_id, band, compute(count, households, zbp_level))
            written += 1
    conn.commit()
    return written
```

`app/config.py`: add `google_maps_api_key: str | None = None` beside `census_api_key` (optional; the worker is the only service that receives it).

- [ ] **Step 4: Run to verify passing**

Run: `poetry run pytest tests/census/test_google_aggregate.py tests/census/test_freshness.py -q` → all pass. The `market_freshness` column-set test is the compliance test: any later attempt to add a `count` column fails CI.

- [ ] **Step 5: Tasks, beat, API**

`app/tasks/freshness.py`:
```python
"""Monthly Google freshness signal (D17) and the 30-day purge (SST §13.2)."""
import httpx

from app.census import freshness as F
from app.census.registry import is_cleared
from app.config import settings
from app.db import sync_conn
from app.tasks.celery_app import celery_app


@celery_app.task(name="freshness.refresh_all")
def refresh_all() -> dict:
    with sync_conn() as conn:
        if not (settings.google_maps_api_key and is_cleared(conn, F.PROVIDER)):
            return {"skipped": "gate closed or key missing"}
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT m.listing_id FROM market_metric m JOIN listing l ON l.id = m.listing_id WHERE l.status = 'published'")
            ids = [r[0] for r in cur.fetchall()]
        written = 0
        with httpx.Client() as http:               # ≤ 1,200 QPM allowed; sequential calls stay far below it
            for lid in ids:
                written += F.refresh_listing(conn, http, lid, settings.google_maps_api_key)
        return {"listings": len(ids), "bands_written": written}


@celery_app.task(name="freshness.purge_expired")
def purge_expired() -> dict:
    with sync_conn() as conn:
        n = F.purge_expired(conn)
        conn.commit()
        return {"purged": n}
```

Beat (`app/tasks/celery_app.py`): `"freshness-monthly": {"task": "freshness.refresh_all", "schedule": crontab(minute=0, hour=4, day_of_month="2")}` and `"freshness-purge-daily": {"task": "freshness.purge_expired", "schedule": crontab(minute=30, hour=4)}`. Extend `test_beat_schedules_only_the_automatic_cadences` with `assert beat["freshness-monthly"]["task"] == "freshness.refresh_all" and beat["freshness-purge-daily"]["task"] == "freshness.purge_expired"`.

**Selection-triggered refresh (the "fetch when a location is selected" behaviour, without a Google call on the request path):** `app/tasks/freshness.py` also exposes `@celery_app.task(name="freshness.refresh_one") def refresh_one(listing_id: str)`, which opens `sync_conn()`, checks the gate and key exactly like `refresh_all`, and calls `F.refresh_listing` for that one listing. In `app/api/market.py`, the panel endpoint (`/api/listings/{id}/market`) and `communities` call `_touch_freshness(listing_id)` after reading: if the gate is cleared and the listing's `market_freshness` row is absent or `fetched_at < now() - STALE_AFTER_DAYS`, `redis.set(f"freshness:{listing_id}", "1", ex=86400, nx=True)` dedupes and, when it wins, `refresh_one.delay(str(listing_id))`. The response is served from the stored row (or without `freshness`) immediately; the next view shows the refreshed bucket. This is the B5 backfill-on-miss pattern applied to Google — the spec's rule "never call an external API at request time" holds, and a busy listing costs at most one Google call per band per day.

`app/api/market.py:communities` — after `c["competition"]` is assembled, and only when `is_cleared(conn, "google_places_aggregate")` (gate re-filtered on read, as B5 does for every layer):
```python
    fresh = {(r["listing_id"], r["band"]): r for r in (await conn.execute(text(
        "SELECT listing_id, band, level_live, diverges, fetched_at FROM market_freshness "
        "WHERE provider = 'google_places_aggregate' AND expires_at > now()"))).mappings().all()} if google_ok else {}
    ...
    if (f := fresh.get((row["listing_id"], b))) and "competition" in c:
        c["competition"]["freshness"] = {"level_live": f["level_live"], "diverges": f["diverges"], "as_of": f["fetched_at"].date().isoformat()}
```
`app/api/market.py:layers` — the `competition` entry gains `"freshness_attribution": reg["google_places_aggregate"].attribution_text` when cleared, else the key is absent. `tests/api/test_market_api.py` gains `test_communities_carry_freshness_only_when_google_is_cleared`: uncleared → `"freshness" not in c["competition"]`; after the `cleared_google` fixture and one `F.write(...)` → exactly the three keys `{"level_live", "diverges", "as_of"}`, and the response text never contains a Google count (assert `"poi_count" not in r.text`). Add `test_selecting_a_listing_with_a_stale_signal_enqueues_one_refresh`: with the gate cleared and a row written `fetched_at = now() - 8 days`, two panel requests enqueue `freshness.refresh_one` exactly once (`celery_app.send_task` patched; Redis key `freshness:{id}` present); with the gate closed nothing is enqueued.

- [ ] **Step 6: Commit**

```bash
git add migrations/062_market_freshness.sql app/census/google_aggregate.py app/census/freshness.py app/tasks/freshness.py app/config.py app/api/market.py app/tasks/celery_app.py tests/census/test_google_aggregate.py tests/census/test_freshness.py tests/census/test_tasks.py tests/api/test_market_api.py
git commit -m "feat(census): Places Aggregate freshness signal — Customer Values only (level_live, diverges), 30-day purge, gated on google_places_aggregate

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push origin HEAD && git push production HEAD
```

## Open items for the VIN Foundation (carried from the spec §15 and the Foundation spec §9)

Basemap licence (Esri in the design vs CARTO in the spec) · satellite vendor · licensed pet rate vs ACS-derived · isochrones vs straight-line · opportunity-score weights sign-off and publication · public teaser vs gated market data · AIES identifier · Census API key contact address to use in the User-Agent (`CENSUS_CONTACT_EMAIL`) · **Google Places Aggregate API (D17)** — counsel sign-off on SST §13 "Customer Values" (a Low/Moderate/High bucket and a divergence flag as the only persisted outputs) and a Google Cloud billing account · **competitor-points source (D16)** — approve Overture Maps Places (or Foursquare OS Places / VIN's directory) for a Phase C points layer · **disposition of the 2017 Google Places export (D15)** — done 2026-09-05: John kept the `place_id` column only (`practice_match_google_place_ids_2017.csv`) and deleted the file · **map engine (G0)** — Leaflet (approved design) or Google Maps: see `docs/decisions/2026-09-05-competition-presentation-options.md` and the greenfield plan `docs/superpowers/plans/2026-09-05-practice-match-google-maps-greenfield.md`; if Google is chosen, D16/D17 and Task C1 are superseded by that plan.

## Red-team review (2026-09-05) — findings and dispositions

| # | Finding | Severity | Disposition |
|---|---|---|---|
| C1 | **Competition layer incoherent.** CBP is county-level; the design renders per-community dots and Low/Moderate/High per community; `vets_per_10k` divided county establishments by catchment households (≈ 66/10k for Travis County vs the design's ≈ 2.5). No rendering/source plan existed for the layer. | High | D11: ZIP Code Business Patterns (`zbp`) aggregated over ZCTAs (A6, B3, B4); ratios computed over one geography; county apportionment fallback labelled derived; `GET /api/layers` + the layer rendering contract; caveat text per §5. |
| C2 | **Growth joined 2014–2018 tracts (2010 GEOIDs) to 2020 tracts.** Tract definitions changed in 2020; many GEOIDs do not exist in both vintages. | High | D12: growth at place level with county fallback (B4); tract crosswalk deferred (Phase C). |
| C3 | The design's community figures are city-level (Cedar Park 81,900), but the plan mapped them to `drive_10` catchments without saying so. | Medium | D10: three bands, `place` default for community surfaces, `drive_10` for the panel, `?band=` everywhere. |
| C4 | **Market endpoints were unauthenticated**, returned a coordinate per listing (an anonymized listing becomes locatable), and enqueued a backfill for any id (queue flooding). | High | D13 + `market_access`; `location_disclosed` rule (D8); enqueue only for existing published listings (B5). |
| C5 | A cached panel kept a just-blocked layer for up to 24 h, violating "hides within one minute" (§11). | Medium | Gate version counter in every cache key (`gate.invalidate` bumps it) and re-filtering on read (A9, B5). |
| C6 | The Census API key appeared in `CensusHTTPError` messages/logs; the ZCTA boundary file may be absent from GENZ2023; `4269::geography` cast should transform to 4326; archive-failure semantics unstated. | Medium | `redact()` in A3 with a test; GENZ2020 fallback in A4; `ST_Transform(…,4326)::geography` in B3/B4; archive failure fails the run (boto3 error propagates through `ingest.run`, recorded as `failed`). |
| C7 | Migration numbers `005`/`006` collided with Sub-project 2's range and could sort before `listing` exists. | Medium | D14 ranges; Phase B → `060`/`061`. |
| C8 | Registry lacked the spec §12 "practice location databases" blocked row the admin tab should show. | Low | `practice_locations` blocked row seeded (A1). |
| C9 | Design copy conflicts with the spec: "Growth since 2015"; drive-time labels without the approximation qualifier; competition card lacks the proxy sentence. | Medium | Strings supplied by `/api/layers`; conflicts routed to the VIN Foundation/Claude Design (B6). |
| C10 | Per-process concurrency semaphore (Celery concurrency 2 → up to 8 in flight per dataset). | Low | Accepted for V1 volumes; Redis token bucket if the Census API pushes back (429 halving already applies). |
| C11 | `ingest.run` is all-or-nothing per run; §11's "resume from the last completed geography page" is not implemented. | Low | Accepted: atomic runs satisfy "no partial vintage ever goes active"; a rerun is cheap. |
| C12 | Operator token = `API_SECRET_KEY` until SP2. | Low | Rotate `API_SECRET_KEY` when SP2 lands; `auth_stub.py` is deleted then. |
| C13 | Business addresses are sent to the Census Geocoder (a public federal service). | Info | Acceptable for business premises; noted for the VIN Foundation's privacy notice. |
| C14 | **A 2017 Google Places export (`Report_Hospital_Competitor_All_US_ZipCode_FULL.csv`) was proposed as the competition source.** Audit (appendix): 183,688 rows → 10,166 distinct places from 8,320 query ZIPs (≈ 20 % of the US; Texas 132 places, Austin absent, South Dakota none), swept 24 May–8 Jun 2017 with the legacy Nearby Search (the 60-result cap was hit in 645 ZIPs); 29.7 % of places are individual-practitioner listings, ≈ 5 % are pet retail, shelters or groomers, 38 % are unrated; addresses carry no state or ZIP; the geography column is corrupted; the file ends mid-record. Google Maps Platform Terms §3.2.3(a)(iii) and (c)(iv) and SST §14.2 forbid storing the content, using its coordinates in point-in-polygon analysis, or showing it on Leaflet. | High | D15: blocked source; audit appendix; registry note on `practice_locations`; `.gitignore` pattern so the file can never be committed. |
| C15 | "Update via the Google Maps API" was requested without a lawful mechanism identified. Every Google route was checked (appendix): Nearby/Text Search, Place Details refresh at each SKU tier, Places Aggregate API, Places UI Kit, Maps JavaScript API, legacy Places API. Only the Aggregate API's Customer Values fit a stored, Leaflet-rendered layer. | Medium | D17 + Task C1 (gated on counsel and billing); D16 for points from permissively licensed POI data; the design's competition count stays Census ZBP (spec §5). |

## Appendix — Audit of the 2017 Google Places export and the Google Maps Platform options (2026-09-05)

**The file.** `Report_Hospital_Competitor_All_US_ZipCode_FULL.csv` (83 MB, 192,473 lines) is an unquoted SQL Server table export (`----` separator row, `NULL` literals, a raw `geography` blob in an unnamed column whose high bytes were replaced by U+FFFD on export, so it is unrecoverable and breaks line counts; the `Lat`/`Long` text columns are the usable geometry). Columns: `ReportId, Id (SHA-1), ZipCode (the query ZIP), PlaceId, Name, Icon, PhotoRef, Rating, Address (street + city only), Lat, Long, IsAssociated, <geography>, Processed, CreatedOn, UpdatedOn`. It is the result table of a **legacy Google Places API Nearby Search sweep, one query per ZIP code**, paged to the legacy 60-result cap (`Icon` URLs under `maps.gstatic.com/mapfiles/place_api/`, `PhotoRef` in the legacy `CmRaAAAA…` form, 645 ZIPs at 60+ rows). No business names are reproduced here: they are Google content.

| Measure | Value |
|---|---|
| Rows / distinct `PlaceId` / distinct query ZIPs | 183,688 (ReportId 1–183,692, 4 gaps, last record truncated) / **10,166** / **8,320** of ~41,700 USPS ZIPs (461 of ~930 ZIP3 prefixes) |
| Sweep window | 2017-05-24 22:49 → 2017-06-08 14:56 (16 days); `UpdatedOn` never later |
| Rows per place | median 8, mean 18, max 585 (large search radius; every place recurs across neighbouring ZIP queries) |
| Coverage by query ZIP (places found) | CA 1,745 (3,340) · AL 642 (1,347) · AR 591 (908) · CO 508 (1,182) · AZ 373 (891) · CT 282 (593) · FL 109 (563) · **TX 404 (132)** · NY 550 (62) · NJ 253 (3) · **SD 0** — 3,732 ZIPs hold exactly one row |
| Austin–Round Rock (design market) | 0 Austin query ZIPs (787xx/733xx), 0 Austin addresses, 1 place inside the metro bounding box |
| Name classification (distinct places) | veterinary practice 50.7 % · **individual practitioner listing 29.7 %** (Google's per-DVM entries double-count clinics) · corporate chain 4.4 % · pet retail/farm/equine 2.0 % · retail chain 1.7 % · shelter/rescue 0.6 % · grooming/boarding 0.5 % · human medical 0.2 % · unclassified 10.3 % |
| Attribute quality | 38.0 % unrated (rating 0) · 43.4 % no photo · addresses lack state and ZIP in >99 % · 2 points outside US territory · `IsAssociated` = 0 everywhere · `Processed` = 1 for 1,175 rows |

**Verdict.** Not a candidate. On merit: nine years stale, a fifth of the country, the design's own market absent, a third of rows are practitioner duplicates. On terms: Google Maps Platform Terms §3.2.3(a) "Customer will not … (iii) copy and save business names, addresses, or user reviews"; §3.2.3(c) "Customer will not … (iv) use latitude/longitude values from the Places API as an input for point-in-polygon analysis" (exactly what a catchment count is); §3.2.3(e) / SST §14.2 "Customer must not use Google Maps Content from the Places API in conjunction with a non-Google map" (the approved design is Leaflet with Esri/CARTO tiles); SST §3 and the Places policies allow only `place_id` to be stored indefinitely, and SST §14.3 allows latitude/longitude for 30 days. The same limits applied under the 2017 Maps APIs terms, so the export was outside them from the day it was written. Disposition (VIN Foundation): delete the content or keep a one-column `place_id` file; nothing from it enters this project (D15; `.gitignore` carries `Report_Hospital_Competitor*.csv`).

**Every Google Maps Platform mechanism for "updating via the Google Maps API", verified 2026-09-05** (prices per 1,000 requests at the 0–100 K tier; free monthly caps by SKU tier: Essentials 10,000 · Pro 5,000 · Enterprise 1,000):

| Mechanism | Returns | Price / free | May we store it? | May it reach the Leaflet map? | Verdict |
|---|---|---|---|---|---|
| Places API (New) **Nearby Search**, `includedTypes: ["veterinary_care"]` | ≤ 20 places per call (`maxResultCount` 1–20), radius ≤ 50,000 m, **no pagination** | Pro $32 / 5,000 (Enterprise $35 for rating, phone, hours) | `place_id` only; lat/lng 30 days | No (SST §14.2) | Enumerating a metro needs hundreds of overlapping circles and yields content we cannot keep — no |
| Places API (New) **Text Search** | same tiers; IDs-only variant free | Pro $32 / 5,000; IDs Only $0 | same | No | no |
| **Place Details (IDs Only)** on a stored `place_id` | confirms the ID still resolves (`NOT_FOUND` when obsolete); Google asks that stored IDs be refreshed every 12 months | $0, unlimited | `place_id` | n/a | The only free, compliant use of the 10,166 IDs: an existence census, not a layer |
| Place Details Essentials / Pro / Enterprise | `location, formattedAddress, types` / `displayName, businessStatus, primaryType` / `rating, userRatingCount, websiteUri, nationalPhoneNumber, regularOpeningHours` | $5 / 10,000 · $17 / 5,000 · $20 / 1,000 | lat/lng 30 days; nothing else | No | no |
| **Places Aggregate API** `computeInsights` | `INSIGHT_COUNT` (or place IDs when the count ≤ 100) for a circle, region or custom polygon, filtered by type, operating status, rating, price; 1,200 QPM | Pro $10 / 5,000 | POI Count 30 days, solely to compute Customer Values; Customer Values indefinitely (SST §13.1–13.2) | Customer Values are ours (§13.1); the raw count is Google Maps Content and is not | **Yes, as D17 / Task C1** — bucket + divergence flag; counsel confirms the Customer-Value reading and the attribution wording |
| Places UI Kit | Google-rendered place list and details web components | per-request SKUs | nothing reaches our systems | Yes — SST §15.1 "prevails over the No Use with Non-Google Maps clause" | A "nearby practices" widget is lawful beside Leaflet, but no data reaches our tables or metrics — not a layer |
| Maps JavaScript API + Places on a **Google** map | points with full Places content | Dynamic Maps $7 / 10,000 + Places SKUs | as Places above | Only by replacing the Leaflet/Esri map with a Google map | A design change the VIN Foundation could choose; not pursued under the pixel-fidelity rule |
| Legacy Places API (`pagetoken`, 60 results) | what the 2017 sweep used | — | — | — | Closed to new Cloud projects since 1 March 2025; frozen for existing ones; 12-month notice before shutdown |

**Point sources that can be stored, drawn on Leaflet and refreshed (D16):**

| Source | Licence | Coverage / cadence | Provenance | Rank |
|---|---|---|---|---|
| Overture Maps Places | CDLA-Permissive-2.0; Foursquare-sourced rows Apache-2.0 | 64 M+ POIs worldwide; monthly GeoParquet (`s3://overturemaps-us-west-2/release/`); `categories` deprecated for `basic_category`/`taxonomy` (removal September 2026) | `sources[]` (dataset + record id) and `confidence` per feature | 1 |
| Foursquare OS Places | Apache-2.0 | 100 M+ POIs; monthly; gated download (Hugging Face / Iceberg) | Foursquare | 2 |
| VIN member practice directory | VIN-owned | VIN members only (a subset of practices) | VIN | 3 — consent review, opt-out |
| OpenStreetMap `amenity=veterinary` | ODbL 1.0 (share-alike) | 65,152 features worldwide (taginfo 2026-09-04); US coverage uneven | OSM | cross-check only; counsel on share-alike for a mixed database |
| State veterinary board premise registers | public records, per state | only states that license premises (e.g. CA, FL, CO, OR, NC) | official | supplementary, not national |
| Purchased lists (Data Axle, Dewey/SafeGraph, …) | commercial | national | vendor | blocked by spec §12 unless licensed with display rights |

The design's displayed competition **count** remains the Census ZBP establishment count (spec §5, D11) in every case; points and the Google freshness bucket are additive, gated layers.

**OpenStreetMap, specifically.** OSM is one crowdsourced geodatabase, not a family of products; what it offers this project is (a) **POIs** tagged `amenity=veterinary` (65,152 features worldwide on 2026-09-04: 48,160 nodes, 16,866 building outlines, 126 relations) with optional `name`, `addr:*`, `phone`, `website`, `opening_hours`, `healthcare:speciality` — no ratings, no business status, closures lag; (b) **basemap tiles** rendered from it by CARTO (already the spec's `osm_tiles` row; the Esri-vs-CARTO question stands); (c) boundaries and roads, which Census TIGER already covers; (d) **Nominatim** geocoding, whose usage policy (1 request/s, no bulk) rules it out for backfills — the Census Geocoder stays. Access paths for POIs: **Geofabrik state extracts** (`.osm.pbf`, updated daily; parse with `pyosmium`, filter `amenity=veterinary`) for a reproducible monthly load, or the **Overpass API** for ad-hoc queries (the public instance is rate-limited and not for production traffic; self-host or pay for a hosted one). Licence: **ODbL 1.0** — attribution "© OpenStreetMap contributors" everywhere the data appears, and **share-alike** for any "derivative database"; keeping OSM POIs in their own table and joining at query time is the OSMF "collective database" pattern, but whether `competitor_location` rows enriched with Census metrics stay a collective database is a counsel question. That is why OSM ranks as a cross-check: Overture Places (CDLA-Permissive; sourced from Meta, Microsoft, Foursquare and others, not from OSM) gives comparable POI coverage without share-alike.

## Self-review

- **Spec coverage:** §1 rules → constraints + A3 (client), A9/B1 (licence gate), B5 (never fetch on request); §2 register → A1 seed; §3 endpoints/auth → A3; §4 variables → A5 `VARIABLES`; §5 NAICS → A6 (incl. NAICS-2017 alias); §6 geography + resolution order → A4, B2; §7 pipeline → B2–B5; §8 formulas → B4 `metrics.py`; §9 refresh → A8 beat + B4 nightly + manual annual loads; §10 caching → A2 archive, B2 geocode cache, B5 panel cache, tiles deferred (Phase C); §11 failures → A3 retries/429, A5 abort-on-drift, B2 fallbacks, B5 empty state, A9 60 s gate; §12 licensing/attribution → A1 registry text, A8 audit, B5 attribution arrays; §13 DDL → A1, B1 (verbatim + `bds_measure`, `inputs`, `geocode_cache`, `geocode_review`, `license_audit_log`, `market_state` as documented additions); §14 quality → B4; §15 open items → listed above.
- **Placeholder scan:** none. Two deliberate STOP conditions (Phase B precondition; SP2's `generalized_location` column name) are explicit instructions, not gaps.
- **Type consistency:** `Dataset` fields (A1) used by A3/A5/A6; `CensusClient.fetch_table/validate_variables/build_url/request_count/concurrency` used consistently in A5/A6/A8; `ingest.run` yields `Run(id, rows, requests, raw_uri)` used identically in A5/A6; `ObjectStore.put_immutable(key, data, content_type)` matches the client's call; `catchment.build(conn, listing_id, geo_vintage)` matches B4/B5 tasks; `materialize_listing(conn, redis, listing_id)` matches B5 fixtures; `gate.layer_enabled(r, conn_factory, key)` signature matches A9 and B5 (`sync_conn` is a factory); metric keys in B4 rows match B5's `METRIC_FOR` and the API contract.
- **Deviation from the spec, recorded:** D3 (tiles deferred), D9 (`inputs jsonb`), D10 (`place` band), D11 (`zbp` dataset — needs the VIN Foundation's nod as an addition to §2), D12 (place-level growth), D13 (member gate), D14 (migration ranges); `bds_measure`, `zbp_industry`, `geocode_review`, `license_audit_log`, `market_state` tables; the licence FK is a trigger; `us:1` national row for the income benchmark.
- **Google / competitor additions (2026-09-05):** Task C1 reuses `metrics.vets_per_10k(estab, hh)`, `metrics.competition_level(per10k)`, `catchment.BANDS`, `registry.is_cleared`/`load`, `db.sync_conn` exactly as defined in A1, B3, B4, B5; the three new registry keys are in `SPEC_KEYS`; `market_freshness` has no count column by construction and a compliance test pins that; `.gitignore` blocks the 2017 export; the API example, layer contract, Phase C table and open items all point at D15–D17.
