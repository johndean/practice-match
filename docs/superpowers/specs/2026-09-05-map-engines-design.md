# Practice Match — Map Engines and Layer Eligibility (Sub-project 4) — Design

**Date:** 2026-09-05 · **Status:** approved in brainstorming (Sections A–C with security/performance audits) · **Depends on:** Foundation spec (SP1), Census & Market Data Source Specification v1.0 and its plan (SP3), Google Maps greenfield plan (reference), `docs/decisions/2026-09-05-competition-presentation-options.md`.

## 0. Decisions taken in brainstorming

| Question | Decision |
|---|---|
| Purpose of the engine switch | **Permanent operating capability.** Admin can switch map engines at any time as licences, costs or agreements change; both engines are maintained for the life of the product; every switch is audited and takes effect within the existing 60-second gate. |
| Sequencing | **Adapter in SP1, Google as the next sub-project.** SP1 wraps the two Leaflet components in a `MapEngine` interface (same pixels, no new dependency). The Google engine, the engine setting and the eligibility matrix follow SP1 as this sub-project, switchable through the operator API until SP2's Admin ships. |
| What Admin controls | **The engine switch only.** Which layers may render on which engine is a licence fact encoded by us in the registry with the governing clause; Admin sees it read-only and continues to clear/block data sources as today. |
| Mechanism | **Registry engine rows + adapter.** Engines are rows in `dataset_registry` shown in the approved Admin → Data Sources table with an **Activate** action; exactly one engine is active (database constraint); layer eligibility is a column; one audit trail. |
| Default engine | **Leaflet** (the approved design) in every environment until an admin activates Google. |

## 1. Scope

**In scope.** A `MapEngine` interface with two implementations (`LeafletMapEngine`, `GoogleMapEngine`); server-selected, split engine bundles; the active-engine setting and the layer-eligibility rule in `dataset_registry`; the SPA shell rendered with config, preload hints and a per-page Content-Security-Policy; `/api/map-config`; the `enabled` rule in `/api/layers`; admin activation endpoint and change log; the two Admin table rows and the Activate action; the Google engine's runtime pieces reused from the Google plan (engine, live pins, live count, stub, runbook); e2e proof that the inactive engine is never loaded.

**Out of scope.** Per-user or per-screen engine choice (forbidden by Google's terms — see §6); editing eligibility in Admin; new Admin tabs; the Google Cloud project itself (Google plan Task G1, John); the design-reference update for a Google-map variant (Google plan G6 Step 5); Places UI Kit and Overture points layers (registry rows are defined here; their loaders are separate work).

## 2. Architecture

### 2.1 The interface

Every map surface — `MarketMapView.vue` and `ListingsMap.vue`, the handoff's two Leaflet components — calls only `MapEngine`:

```ts
interface MapEngine {
  mount(el: HTMLElement, center: LatLng, zoom: number): Promise<void>;
  show(): void;                       // after re-parenting: Leaflet invalidateSize(), Google resize
  setView(center: LatLng, zoom: number): void;
  fitBounds(points: LatLng[]): void;
  setBase(kind: 'street' | 'satellite'): void;
  circle(center: LatLng, radiusM: number, style: CircleStyle, group?: string): Handle;
  marker(pos: LatLng, content: HTMLElement, group?: string): Handle;   // the design's divIcon HTML, verbatim
  clear(group: string): void;
  onMove(cb: (center: LatLng, zoom: number) => void): () => void;
  destroy(): void;
}
```

This is the complete surface the handoff uses today (`L.map`, `tileLayer`, `circle`, `marker` + `divIcon`, `layerGroup`/`clearLayers`, `bindTooltip`, `setView`, `invalidateSize`, `control`). Tooltips are rendered inside the marker's own HTML in both engines so the design's tooltip markup and CSS are reused unchanged.

### 2.2 Two implementations

- **`LeafletMapEngine`** reproduces the handoff's calls exactly: same tile URL (from the active basemap row), same `divIcon` HTML, same tooltip markup, same control placement. The SP1 pixel gate (`maxDiffPixels: 0`) is unchanged by construction.
- **`GoogleMapEngine`** is the Google plan's Task G2: Maps JavaScript API on a cloud-styled Map ID, `AdvancedMarkerElement` carrying the same HTML, `mapTypeId: 'hybrid'` for satellite, `disableDefaultUI: true` (controls only — the Google logo, "Map data ©" and Terms link are rendered by the API and never touched).

Only `frontend/src/map/engines/*` may import `leaflet` or the Google loader (ESLint `no-restricted-imports` everywhere else).

### 2.3 Split engine bundles, server-selected

Each engine is its own Vite chunk (`engines/leaflet`, `engines/google`). **The server decides the engine before the first byte of JavaScript runs** and the browser downloads only the active engine's code. `app/static.py`, which already serves `index.html`, renders per request from an in-process snapshot (§4.1):

```html
<script id="pm-config" type="application/json">{"engine":"leaflet","gate":42}</script>
<link rel="modulepreload" href="/_app/engine-leaflet-3f9c.js">
<!-- Google active: -->
<link rel="modulepreload" href="/_app/engine-google-91ab.js">
<link rel="preconnect" href="https://maps.googleapis.com"><link rel="preconnect" href="https://maps.gstatic.com">
```

The engine chunk therefore loads in parallel with the app bundle (HTTP/2 + `modulepreload`); no client-side check, no extra round trip. Chunk filenames come from Vite's `manifest.json`, read once at process start.

### 2.4 Load path and performance model (estimates, US East via Railway's edge)

| Step | Leaflet active | Google active |
|---|---|---|
| Shell HTML (config + preload) | ~50–100 ms | same |
| App bundle ‖ engine chunk | app ~120 KB gz ‖ Leaflet ~42 KB gz | app ‖ engine chunk ~4 KB gz |
| Map runtime | in the chunk | Maps JS core ~250–350 KB gz from Google's CDN, ~300–600 ms |
| First map paint after shell | ~250–450 ms | ~600–1,000 ms |
| Tiles | Esri/CARTO raster, CDN-cached | Google vector tiles, CDN-cached |

The Google column is slower because Google's runtime is larger — a property of Google Maps, not of the switch. The switch adds nothing to either column.

### 2.5 Runtime rules

- **One long-lived map instance per session**, re-parented between screens and `show()`n on display. On Google this keeps billable map loads at one per session (the Dynamic Maps SKU counts every `new Map`); on Leaflet it avoids re-fetching tiles on every Browse ↔ Detail navigation.
- **Places calls are debounced (300 ms) and memoised in page memory** per (hub, band); results never leave the page's memory.
- **One engine per page load, never swapped in the client.** If the configured engine's chunk or runtime fails, the map area shows the design's empty-state panel ("Map temporarily unavailable") and reports telemetry; the rest of the page works. The only fallback to Leaflet is the server's, when no config snapshot is available (§9).
- **A switch reaches open sessions on their next route change** (the router sync re-renders the map container). New sessions get it at once. No session ever shows two engines.
- **Default:** Leaflet. Google is activatable only after `map_engine_google` is `cleared` (Google plan Task G1 verification).

## 3. Data model

Migration `080_map_engines.sql` (this sub-project owns `080`–`089`; Census SP3-A `002`–`009`, SP2 `010`–`059`, SP3-B `060`+). It alters `dataset_registry` (Census plan A1) and adds one table.

```sql
ALTER TABLE dataset_registry
  ADD COLUMN kind text NOT NULL DEFAULT 'dataset' CHECK (kind IN ('dataset','basemap','engine')),
  ADD COLUMN engines text[] NOT NULL DEFAULT '{leaflet,google}',   -- engines this row may render on (licence fact)
  ADD COLUMN active boolean NOT NULL DEFAULT false;                 -- engine rows only

CREATE UNIQUE INDEX dataset_registry_one_active_engine ON dataset_registry ((kind)) WHERE kind = 'engine' AND active;

-- Activation requires a cleared engine; an active engine cannot be un-cleared.
CREATE OR REPLACE FUNCTION engine_row_rules() RETURNS trigger AS $$
BEGIN
  IF NEW.kind = 'engine' AND NEW.active AND NEW.license_status <> 'cleared' THEN
    RAISE EXCEPTION 'engine % must be cleared before activation', NEW.dataset_key USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.kind <> 'engine' AND NEW.active THEN
    RAISE EXCEPTION 'only engine rows can be active' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER engine_row_rules BEFORE INSERT OR UPDATE ON dataset_registry FOR EACH ROW EXECUTE FUNCTION engine_row_rules();

CREATE TABLE registry_change_log (
  id bigserial PRIMARY KEY,
  dataset_key text NOT NULL REFERENCES dataset_registry(dataset_key),
  changed_at timestamptz NOT NULL DEFAULT now(),
  actor text NOT NULL,               -- member id, or 'operator' before SP2
  actor_ip inet,
  actor_ua text,
  field text NOT NULL CHECK (field IN ('license_status','active')),
  old_value text,
  new_value text,
  reason text
);
REVOKE UPDATE, DELETE ON registry_change_log FROM PUBLIC;   -- append-only for the application role
```

Rows (seeded by `080`; `notes` carries the clause):

| dataset_key | kind | engines | license_status at seed | active |
|---|---|---|---|---|
| `map_engine_leaflet` — "Map engine — Leaflet + Esri tiles" | engine | `{leaflet}` | cleared (Leaflet BSD-2-Clause; tiles governed by their own rows) | **true** |
| `map_engine_google` — "Map engine — Google Maps Platform" (basemap and satellite) | engine | `{google}` | unresolved → cleared by Google plan G1 | false |
| `esri_tiles` (the design's URL) | basemap | `{leaflet}` | unresolved (Esri licence question, Foundation spec §9) | — |
| `osm_tiles` (CARTO, existing row) | basemap | `{leaflet}` | cleared | — |
| `imagery` (existing row) | basemap | `{leaflet}` | unresolved | — |
| Census rows (`acs5`, `acs5_subject`, `acs5_prior`, `cbp`, `zbp`, `qwi`, `bds`, `geocoder`, `tiger_cb`) | dataset | `{leaflet,google}` | as seeded by A1 | — |
| `google_places_live`, `google_places_aggregate` | dataset | `{google}` | unresolved → G1 | — |
| `places_ui_kit` | dataset | `{leaflet,google}` | unresolved (billing) | — |
| `google_maps_link` | dataset | `{leaflet,google}` | cleared (Maps URLs: no key, no Core Service) | — |
| `overture_places`, `fsq_os_places`, `osm_poi` | dataset | `{leaflet,google}` | unresolved (VIN Foundation / counsel) | — |
| `practice_locations` (incl. the 2017 Google export) | dataset | `{}` | blocked | — |

**The eligibility rule, computed in one place (`app/census/gate.py`):**

```
active_engine = the single row with kind='engine' AND active   (none → 'map_engine_leaflet' by the server fallback)
enabled(row)  = row.license_status = 'cleared'
             AND active_engine.license_status = 'cleared'
             AND engine_name(active_engine) ∈ row.engines          -- engine_name = dataset_key minus the 'map_engine_' prefix: 'leaflet' | 'google'
```

Nothing in the frontend decides eligibility; the client's only check is defensive (§7 S7).

**Activation** (`POST /api/admin/data-sources/{key}/activate`) runs one transaction: `UPDATE dataset_registry SET active=false WHERE kind='engine'` then `UPDATE … SET active=true WHERE dataset_key=:key AND kind='engine' AND license_status='cleared'` (0 rows → 409), then a `registry_change_log` row, then `gate.invalidate`. Activating the already-active engine is a no-op that neither logs nor bumps the gate.

## 4. API and shell rendering

### 4.1 The shell (`app/static.py`)

- Per-request template substitution into `index.html`: `pm-config` JSON, `modulepreload` for the active engine chunk, `preconnect` hints for Google, and the `Content-Security-Policy` header (§4.2).
- **Config snapshot** `(engine, gate_version, enabled_rows, csp)` held in-process with a **15 s TTL**, refreshed from Redis (`market:gate:v`, registry snapshot) — never a database read per request; the Vite manifest is read once at start.
- **JSON escaping:** `<`, `>`, `&`, U+2028, U+2029 are emitted as `\uXXXX` so no registry string can close the `<script>`.
- **Authenticated shells only** (a valid SP2 session cookie; before SP2, only when `MARKET_DATA_PUBLIC=true` — the Census plan's QA-evaluation override, which also opens `/api/map-config`) carry the Google runtime config `{ "google": { "mapId": "...", "browserKey": "..." } }` (a valid member session cookie is present). Anonymous shells carry `{engine, gate}` and the hints. Values come from the `api` service environment (`GOOGLE_MAPS_BROWSER_KEY`, `GOOGLE_MAPS_MAP_ID`) — a key rotation is a Railway variable change, not a rebuild. The browser key is public by design and referrer-restricted; quotas are its real protection (§7 S1).
- Headers: `Cache-Control: no-cache`, weak `ETag` = hash(manifest, engine, gate, authenticated?) → 304 on repeat visits.

### 4.2 Content-Security-Policy per page

The CSP is the **union of the allowlists of the enabled rows** (engine + basemaps + datasets), each row's hosts a constant in code keyed by `dataset_key`, computed once per snapshot:

| Row | script-src | img-src | connect-src | frame-src |
|---|---|---|---|---|
| `map_engine_leaflet` | `'self'` | `'self' data:` | `'self'` | — |
| `esri_tiles` | — | `server.arcgisonline.com` | — | — |
| `osm_tiles` | — | `*.basemaps.cartocdn.com` | — | — |
| `map_engine_google`, `google_places_live` | `maps.googleapis.com` | `maps.gstatic.com *.googleapis.com *.ggpht.com` | `maps.googleapis.com places.googleapis.com` | — |
| `places_ui_kit` | `maps.googleapis.com` | `maps.gstatic.com *.googleapis.com` | `maps.googleapis.com places.googleapis.com` | — |

Basemap `base_url` values are validated against the same allowlist on write (`/license` endpoint) — an admin cannot point the Leaflet engine at an arbitrary host.

### 4.3 Endpoints

| Endpoint | Auth | Behaviour |
|---|---|---|
| `GET /api/map-config` | member (`require_member`; operator token pre-SP2) | `{engine, gate, leaflet:{tiles, attribution} \| google:{mapId, browserKey}}` — used by the SPA after sign-in (anonymous shell) and on route change after it sees the gate move |
| `GET /api/layers` | as in the Census plan | each entry gains `engines`; top level gains `engine`; `enabled` follows §3's rule |
| every API response | — | header `X-PM-Gate: <version>`; the client refetches `/api/layers` and `/api/map-config` on its next route change when the value changes — **no polling** |
| `GET /api/admin/data-sources` | operator/admin (`require_operator` → SP2 admin role) | rows gain `kind`, `engines`, `active` |
| `POST /api/admin/data-sources/{key}/license` | operator/admin | existing (Census A9); now also writes `registry_change_log` (`field='license_status'`) and validates basemap `base_url` against §4.2 |
| `POST /api/admin/data-sources/{key}/activate` | operator/admin | §3 activation; CSRF token + SameSite cookie (SP2 sessions); 5 requests/minute; **disabled on production until SP2 ships** (`ADMIN_ACTIVATE_ENABLED`, default false in production) |
| `GET /api/admin/data-sources/changes?limit=50` | operator/admin | newest `registry_change_log` rows |

## 5. Admin UI (approved Data Sources table; two rows and one action)

Columns Dataset · Source and license · Status · Action, rendered by the existing `cell`/`A` helpers:

| Dataset | Source and license | Status | Action |
|---|---|---|---|
| Map engine — Leaflet + Esri tiles · *Approved design* | Leaflet (BSD-2-Clause); tiles licensed by their own rows below | **Active** (ok) | — |
| Map engine — Google Maps Platform · *Basemap, satellite, live Places* | Google Maps Platform Terms · Places content renders on this engine only (Terms §3.2.3(e)) | **Cleared** (info) or **Unresolved** (warn) | **Activate** → becomes **Confirm switch** for 6 s → POST `/activate` |

Every other row's "Source and license" sub-line gains "Renders on: Leaflet · Google" or "Google map only — Terms §3.2.3(e)". After confirmation the Status pills swap, the change log records the decision, and the gate bumps. No new component or tab; the tab badge keeps counting unresolved rows. All registry text renders through Vue text bindings (no `v-html`).

## 6. Compliance rules the design encodes

- **Google Maps Platform Terms §3.2.3(e):** "Customer will not use the Google Maps Core Services with or near a non-Google Map in a Customer Application." → one engine active per environment; never per user or per screen; the inactive engine's code and tile hosts are never requested (proved in e2e); Google layers carry `engines = {google}`.
- **SST §14.2 / §3.2.3(a),(c)(iv):** no Places content on Leaflet; nothing from Google stored; no counts derived from Places coordinates. Inherited from the Census and Google plans; the matrix enforces the first.
- **SST §15.1:** Places UI Kit may sit beside Leaflet → `places_ui_kit` carries `{leaflet,google}`.
- **Maps JavaScript API policies:** attribution untouched; `disableDefaultUI` removes controls only.
- **D8 (Census plan):** every Google-bound location leaving the browser — the "Open in Google Maps" query, the UI Kit search centre, the pins' search centre — is built from the **visible point / place name** the API returns (place centroid unless `location_disclosed`). The precise point of an undisclosed listing is never in the browser, so it cannot leak.
- **The one assumption for counsel:** that "one engine active at a time" satisfies §3.2.3(e). Everything else follows Google's text directly.

## 7. Security requirements (from the audits)

| # | Requirement |
|---|---|
| S1 | Google runtime config inlined only in authenticated shells; anonymous shells carry no key. Google-side per-day quotas (and per-minute-per-user where Google offers them) plus budget alerts are the real limit — referrer restrictions are spoofable and only deter casual reuse. |
| S2 | Inlined JSON escapes `<`, `>`, `&`, U+2028/9; a unit test proves `</script>` cannot survive; Admin renders registry text without `v-html`. |
| S3 | Per-page CSP from enabled rows (§4.2); basemap `base_url` validated against the allowlist on write. |
| S4 | Admin POSTs: SameSite cookie **and** double-submit CSRF token (SP2); admin role, operator token pre-SP2; `activate` rate-limited 5/min, idempotent, production-disabled until SP2. |
| S5 | Activation is a two-statement transaction; the partial unique index is the backstop; zero-active is unobservable. |
| S6 | `registry_change_log` append-only; records actor, IP, user agent, reason. |
| S7 | Straddled requests: both `/api/layers` and `/api/map-config` carry `gate`; mismatch → refetch. A map component enables only layers whose `engines` include the engine it **mounted**. |
| S8 | Browser-side Places spend is bounded by Google quotas + the 300 ms debounce + in-page memoisation; the count proxy stays server-side and rate-limited. |
| S10 | No client-side engine swap; failure → empty-state panel + telemetry. |
| S11 | CSP is the union over enabled rows, so clearing `places_ui_kit` widens Leaflet pages lawfully and nothing else does. |
| S12 | D8 location invariant for every Google-bound query; tested against an undisclosed fixture listing. |
| S13 | Client error telemetry strips `key=` parameters; server logs never receive Google script URLs. |
| S14 | No live Google key in CI or GitHub; e2e uses the deterministic stub; the live check is `verify-google.sh` run by John against QA. |
| S15 | Operator-token actions attribute to `operator` with IP/UA; rotate `API_SECRET_KEY` when SP2 lands (Census C12). |

## 8. Performance requirements

| # | Requirement |
|---|---|
| P1 | Shell rendering does no I/O per request: manifest at start; 15 s in-process snapshot; weak ETag; `Cache-Control: no-cache`. |
| P2 | First map paint adds **no request on the critical path** versus the single-bundle baseline: the engine chunk is preloaded and starts before the app bundle finishes (asserted in e2e). |
| P3 | A switch drops no caches: the Census plan's B5 payload cache is re-filtered through the gate on read; only the shell/layers snapshots refresh. |
| P4 | Eligibility is evaluated in memory over the registry snapshot (~20 rows). |
| P6 | Re-parenting a long-lived map calls `show()` (Leaflet `invalidateSize`, Google resize). |
| P7 | Playwright: `app-leaflet` runs the full visual gate; `app-google` runs smoke, the map screens and the no-mixing assertions only. |
| P8 | The performance budget is two deterministic checks (preload tag matches the manifest; engine chunk request starts before the app bundle completes) — no Lighthouse in CI. |
| P9 | Redis unavailable: the shell keeps serving its last snapshot; `/api/layers` falls back to one Postgres read; healthz reports `redis.ok=false`. |

## 9. Degradation (spec rule: degrade, never block)

| Failure | Behaviour |
|---|---|
| No config snapshot and Redis unavailable at first request | Shell renders **Leaflet** (safe direction); healthz `redis.ok=false` |
| Zero active engine rows (should be impossible) | Server treats Leaflet as active |
| Configured engine's chunk or runtime fails (network, `RefererNotAllowedMapError`, CSP) | Map area shows the design's empty-state panel "Map temporarily unavailable"; telemetry (key-stripped); listings, search, messaging unaffected |
| Google quota exhausted | Google layers hide with their `/api/layers` note; map and Census layers unaffected |
| Switch during a session | Applied on the next route change; the in-flight page finishes on its current engine |

## 10. Testing

- **Contract tests over both engines:** one suite (`engine.contract.test.ts`) runs against `LeafletMapEngine` (Leaflet stub) and `GoogleMapEngine` (Google stub): mount marks the element, circles carry the design's radius/colour, markers carry the given HTML and clear by group, `setBase` maps to the right tile/type, `show()` triggers resize.
- **Eligibility:** pure-function table test over §3's matrix under both engines; trigger tests (activate uncleared → error; un-clear active → error; non-engine `active` → error; unique index holds after a swap); activation idempotency; change-log row; gate bump.
- **Shell:** authenticated vs anonymous config; JSON escaping; CSP union per enabled set; ETag/304; preload href equals the manifest chunk.
- **API:** `/api/map-config` auth; `/api/layers.enabled` under both engines; `X-PM-Gate`; CSRF rejection; `activate` rate limit and production disable; `/license` basemap host validation.
- **E2E (`app-leaflet`, `app-google`):** each engine mounts from the server-rendered config; **the other engine's chunk and tile hosts receive zero requests** (route interception); after an admin activation the next route mounts the new engine and both maps never coexist; Google layers absent under Leaflet, Esri tiles absent under Google; the engine chunk request starts before the app bundle completes.
- **Visual gate:** `app-leaflet` unchanged at `maxDiffPixels: 0`; `app-google` masks `[data-map]` until the Google design variant exists.
- **Location invariant:** for an undisclosed fixture listing, the Maps link query and the pins/UI Kit search centre equal the place centroid.

## 11. Sequencing and plan impacts

1. **SP1 Foundation — Task 1 amendment:** add `frontend/src/map/engine.ts` and `frontend/src/map/engines/leaflet.ts`; point `MarketMapView.vue` and `ListingsMap.vue` at the interface; add the ESLint import rule. Pixels unchanged; Leaflet stays vendored. No other SP1 change.
2. **Census A1 + A9 first** (registry + seed; gate + `/api/admin/data-sources`): prerequisites of this sub-project; A1's seed is not edited — `080` adds the columns and rows.
3. **This sub-project (plan to follow):** `080_map_engines.sql`; shell rendering + CSP + ETag; `/api/map-config`; `/api/layers` rule; `activate` + change log + `/changes`; Admin rows and action (operator token until SP2); `engines/google.ts` and the Google plan's G3 (pins), G4 (count proxy), G6 (stub, mask), G7 (runbook). The Google plan's G5 "block tiles" trigger and G8 "remove Leaflet" deltas are **superseded** by the matrix and dropped.
4. **SP2 Admin** attaches the real admin role and CSRF to endpoints that already exist; enables `activate` on production.

Before SP2 there are no member sessions, so evaluating Google on QA uses `MARKET_DATA_PUBLIC=true` on the QA environment only (never production): shells carry the Google config, `/api/map-config` is open, and the operator token performs the activation.

## 12. Open items

- **Counsel:** confirm that one engine active per environment, never simultaneously, satisfies Terms §3.2.3(e).
- **John:** Google Cloud project, keys, Map ID, quotas, budget (Google plan Task G1) before `map_engine_google` can be cleared.
- **VIN Foundation:** Esri tile licence for the design's URL (`esri_tiles` starts unresolved; CARTO is the cleared alternative); approve the two Admin rows and the Activate wording; commission the Google-map variant of the design reference for the `app-google` visual gate.

## 13. Definition of done

- Both engines pass the contract suite; `app-leaflet` visual gate green at `maxDiffPixels: 0`; `app-google` smoke and no-mixing assertions green with the stub.
- On QA: with Leaflet active, `curl -s https://qa.foundation.vin/ | grep modulepreload` names the Leaflet chunk and the CSP header names only Leaflet hosts; after `POST …/map_engine_google/activate` (operator token; `map_engine_google` cleared), the next shell names the Google chunk and CSP, `/api/layers` shows Google layers enabled and Esri tiles disabled, and the change log holds the row; activating again is a no-op.
- `registry_change_log` cannot be updated or deleted by the application role.
- Healthz reports `map.engine` and `redis.ok`.
