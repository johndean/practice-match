# Practice Match — Google Maps Platform (Greenfield) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: decision-gated.** This plan runs only if the VIN Foundation answers decision **G0** ("map engine") with *Google Maps*. See `docs/decisions/2026-09-05-competition-presentation-options.md`. It is written greenfield: nothing from the 2017 Google Places export is used, and the design is treated as if Leaflet had never been chosen. If G0 stays *Leaflet*, this document is a costed reference and nothing here is built.

**Goal:** Render every Practice Match map with the Maps JavaScript API (cloud-styled Google basemap plus Google satellite), show **live** Google Places veterinary practices as a competitor layer (name, address, operating status, optional rating), show a **live** Google count per catchment band beside the Census count — and store nothing from Google.

**Architecture:** The browser loads the Maps JavaScript API with a referrer-restricted key and a Map ID; a `MapEngine` adapter replaces the Leaflet calls in the two map components; competitor pins come from `Place.searchNearby` in the browser (billed per view, never persisted); the live count comes from our API, which proxies the Places Aggregate API with a server-side key (10-second timeout, never persisted, degrades to "unavailable"); the Census layers (bubbles, circles, panel figures) are unchanged — they are our data drawn on Google's map. The visual-fidelity gate masks the map viewport until the Claude Design reference is updated to a Google map, then regenerates baselines from that reference.

**Tech Stack:** Maps JavaScript API (`v=weekly`, libraries `maps`, `marker`, `places`), `AdvancedMarkerElement` with HTML content, cloud-based map styling on a Map ID, Places API (New) via the JS `Place` class, Places Aggregate API (`computeInsights`) via `httpx`, FastAPI, Redis (rate limit only), Playwright with a deterministic `google.maps` stub, Vitest.

## Global Constraints (exact values — verified against Google's terms and pricing on 2026-09-05)

- **Quality and performance policy (`docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md`).** Test shape ~70/20/10 unit/integration/e2e enforced by rules; CI gates: `pytest -W error --cov-fail-under=90`, `diff-cover --fail-under=100`, `ruff`, `mypy --strict`, `vue-tsc --noEmit` (strict), vitest coverage ≥ 85 % on `src/map|router|admin`, Playwright fails on any `pageerror`/`console.error`, `gitleaks`; performance budgets are tests: API p95 (`/api/healthz` ≤ 20 ms, shell ≤ 15 ms, list endpoints ≤ 100 ms, panel ≤ 150 ms), bundle sizes (main ≤ 220 KB gz, `engine-leaflet` ≤ 60, `engine-google` ≤ 12, first load ≤ 300), first map paint ≤ 1,500 ms, hot queries use indexes, nightly k6 on QA (p95 ≤ 400 ms, 0 errors). Raising a budget is a reviewed change with a reason in the commit message.
- **TDD, no exceptions (John, 2026-09-05: "everything must have tests").** Every production change begins with a failing test that is run and watched fail (RED), then the minimal code, then the same test watched pass (GREEN) — the `Run:` lines in each task are mandatory steps, not illustrations. Documentation and configuration are covered by drift tests (`tests/test_docs.py`: every setting in `.env.example` and `DEPLOY.md`, relative links resolve, CI workflow shape, runbook endpoints exist); operational scripts have shell tests under `tests/scripts/` that run them against stubbed servers or a stubbed `curl`; ops steps end with an executable verification whose script is itself tested. The handoff's generated UI is covered by the visual gate (every screen state), the route smoke tests, the router-sync and engine unit tests and the `logic.js` characterisation suite (Platform Task 1c); new code in those files follows TDD.
- **One map engine, app-wide (Terms §3.2.3(e)).** "Customer will not use the Google Maps Core Services with or near a non-Google Map in a Customer Application." Leaflet, Esri and CARTO leave the application entirely; an ESLint `no-restricted-imports` rule for `leaflet` enforces it. The design-reference render used by the visual harness may still contain Leaflet — it is a development fixture, not part of the Customer Application.
- **Attribution untouched.** The Google logo, "Map data ©… Google" and the Terms link are rendered by the API; they are never removed, hidden, obscured or moved (Maps JavaScript API policies). `disableDefaultUI: true` removes controls only; it does not and must not touch attribution. Places content shown outside the map (a list, a tooltip) shows each place's `attributions` when present.
- **Nothing from Google is stored.** No Places field (name, address, status, rating, lat/lng) and no Aggregate count is written to Postgres, Redis (other than rate-limit counters), the bucket, logs or analytics. `place_id` may be stored (SST §3) but V1 stores none. Lat/lng of a place may be held in browser memory for the page's life (SST §14.3 allows 30 days; we keep none past the view).
- **No derived analysis from Places coordinates (Terms §3.2.3(c)(iv)).** Counts within a catchment come from Census ZBP (spec §5) and from Google's Aggregate API — never from counting pins. Client-side **display** filtering and de-duplication of the returned list is presentation, not analysis.
- **Keys.** Browser key `VITE_GOOGLE_MAPS_BROWSER_KEY`: application restriction *Websites* = `https://foundation.vin/*`, `https://qa.foundation.vin/*`, `http://localhost:5173/*`; API restriction = Maps JavaScript API, Places API (New). Server key `GOOGLE_MAPS_SERVER_KEY`: API restriction = Places Aggregate API only; lives on the `api` service; never sent to the browser. Both set through Railway variables after the 🚦 `railway status` → `Project: Practice Match` check; never in chat, git or `.env.example`. The browser key ships inside the bundle by design — the referrer restriction and the quotas are its protection.
- **Spend caps.** Cloud-console quotas: Maps JavaScript API map loads 5,000/day; Places API (New) Nearby Search 2,000/day; Places Aggregate API 2,000/day. Cloud Billing budget `practice-match-maps` $50/month with alerts at 50 %, 90 %, 100 %. On `RESOURCE_EXHAUSTED`/HTTP 429 the live layers hide themselves with the "temporarily unavailable" note from `/api/layers`; the Census layers and the rest of the app keep working (spec: degrade, never block).
- **Prices (0–100 K tier, after the free monthly allowance).** Dynamic Maps (map load) $7.00 / 1,000 after 10,000 free · Nearby Search Pro $32.00 / 1,000 after 5,000 free (Enterprise $35.00 / 1,000 after 1,000 free when `rating`/`userRatingCount` are requested) · Places Aggregate API $10.00 / 1,000 after 5,000 free · Place Details (IDs Only) free.
- **Pixel gate.** Everything outside the map viewport stays at `maxDiffPixels: 0`. The map viewport (`[data-map]`) is masked in both reference and app screenshots while `DESIGN_HAS_GOOGLE_MAP=false`; once the Claude Design reference shows a Google map, the flag flips and the mask is removed.
- **Places data quality is presented honestly.** Google lists individual practitioners as separate places (the 2017 audit measured 29.7 %). Pins are filtered to `primaryType === 'veterinary_care'` and `businessStatus === 'OPERATIONAL'` and merged by `formattedAddress` for display; the layer's note says so. A saturated result (20 places) is labelled "the 20 nearest are shown".
- **Member-gated like every market surface** (Census plan D13): the live-count endpoint requires an approved member session; the browser-side pin search runs only inside member-only screens.
- Every commit: conventional message, `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, pushed to `origin` and `production`. Work on `feat/google-maps` in a worktree.

## Decisions recorded in this plan (confirm on review)

| # | Decision | Why |
|---|---|---|
| G0 | **The VIN Foundation chooses the map engine.** This plan executes only on "Google Maps"; the approved design's Leaflet/Esri map is the alternative. | Terms §3.2.3(e) makes the choice binary and app-wide; it changes the approved design's map corners (logo, attribution, controls) and introduces usage-based cost. |
| G1 | **Leaflet is removed, not wrapped.** Platform plan Task 1's `lib/leaflet.js` vendoring and the Leaflet npm dependency are dropped; Task 3's reference server keeps Leaflet for the design reference only. | No-mixing rule; a dormant Leaflet bundle invites accidental use. |
| G2 | **Pins are fetched in the browser per view; the count is fetched by our API per request; neither is persisted.** | The Places terms are written for live display; server-side fetching of Places content would tempt storage and needs the same fields anyway. The Aggregate key must not reach the browser. |
| G3 | **Pin fields = Pro tier by default:** `id, displayName, location, formattedAddress, businessStatus, primaryType, attributions`. `rating`, `userRatingCount` (Enterprise tier, $35/1k) sit behind the layer option `competition_live_points.ratings` (default off). | The approved design's competition card shows no ratings; ratings cost 9 % more per call and shrink the free allowance from 5,000 to 1,000. |
| G4 | **One Nearby Search per band** (`locationRestriction` circle of 8,000 m or 16,000 m, `maxResultCount: 20`, `rankPreference: DISTANCE`); no tiling of the catchment in V1. When 20 come back the UI says "the 20 nearest are shown" and the number comes from the live count, not the pins. | Nearby Search (New) has no pagination; tiling multiplies cost 4–7× for pins nobody can read at that zoom. |
| G5 | **The live Aggregate count is displayed as a second, labelled figure** ("Google Maps: N operating veterinary places within 8 km — live"); the Census ZBP count remains the layer's primary number and the Low/Moderate/High input. | Spec §5 defines the metric on Census data; the live count is context, fetched and shown, not stored or derived from. |
| G6 | **Satellite = `mapTypeId: 'hybrid'`.** | Included in the Dynamic Maps SKU with Google's imagery attribution; the design's Satellite toggle stops waiting on a licence (Census spec §15 imagery item closes). |
| G7 | **Basemap style = a cloud style on Map ID `practice-match-web`** approximating the design's light-grey canvas (POI labels off, roads muted, water `#d5e6f2`, parks `#e9f1e6`). The Claude Design reference is updated to the Google look; baselines regenerate from it. | Pixel identity with Esri tiles is impossible; tiles were never in the comparison; controls and attribution are, so the reference must change. |
| G8 | **The Census Geocoder stays.** Google Geocoding is not enabled. | Census geocodes are public domain and storable; Google's are cacheable 30 days (SST §6.3.1) — the wrong shape for a listing record. |
| G9 | **`osm_tiles` and `imagery` registry rows become `blocked`** when `google_maps_js` is cleared; `google_places_live` and `google_places_aggregate` become `cleared` only after Task G1's verification. | The registry's licence gate is the single switch for what may render (Census spec §1); the no-mixing rule is expressed there too. |

## API contract additions (consumed by Sub-project 2's frontend wiring)

```jsonc
// GET /api/layers  — two new entries (gate-driven `enabled`)
{ "key": "competition_live_points", "label": "Veterinary practices (Google Maps, live)", "dataset_key": "google_places_live", "enabled": true,
  "attribution": "Google Maps", "options": { "ratings": false },
  "caveat": "Live from Google Maps: the 20 nearest operating veterinary places are shown; practitioner listings at the same address are merged for display. Not stored; not used in any metric." },
{ "key": "competition_live_count",  "label": "Veterinary places nearby (Google Maps, live)", "dataset_key": "google_places_aggregate", "enabled": true,
  "attribution": "Google Maps",
  "caveat": "Live count of operating veterinary places within the band radius, from Google Maps. The Census establishment count is the official figure used for Low/Moderate/High." }

// GET /api/listings/{id}/competition/live?band=drive_10      (member session required; 30 requests/minute/member)
{ "band": "drive_10", "radius_m": 8000, "count": 12, "source": "Google Maps", "attribution": "Google Maps", "fetched_at": "2026-09-05T15:04:11Z" }
{ "band": "drive_10", "radius_m": 8000, "count": null, "reason": "gate" }        // layer not cleared or key missing
{ "band": "drive_10", "radius_m": 8000, "count": null, "reason": "quota" }       // 429 / RESOURCE_EXHAUSTED upstream
{ "band": "drive_10", "radius_m": 8000, "count": null, "reason": "timeout" }     // > 10 s
```
`band` ∈ `place | drive_10 | drive_20`; `place` and `drive_10` use 8,000 m, `drive_20` 16,000 m (Census plan `catchment.BANDS`). The centre is the listing's **visible point** (Census plan D8: the geocoded point only when `location_disclosed`, else the place centroid).

## File map

| File | Responsibility |
|---|---|
| `frontend/src/map/engine.ts` | `MapEngine` interface and types — the only map API the components use |
| `frontend/src/map/loader.ts` | Bootstrap loader for the Maps JavaScript API (one script tag, `loading=async`) |
| `frontend/src/map/google.ts` | `GoogleMapEngine` — Maps JS implementation of `MapEngine` |
| `frontend/src/map/competition.ts` | `searchVets` — Nearby Search, display filter, address merge, saturation flag; `pinContent` |
| `frontend/src/map/useCompetitionLive.ts` | Composable wiring the layer toggle, hub and band to `searchVets` and the engine |
| `frontend/tests/unit/map/google-stub.ts` | Deterministic `google.maps` stub for Vitest and Playwright |
| `frontend/e2e/stubs/google-maps.js` | Built from the stub; served by `page.route` in place of `maps.googleapis.com/maps/api/js` |
| `frontend/src/components/*` (the two components that `import 'leaflet'` in the handoff's `vue-app` — find them with `grep -rl "from 'leaflet'" frontend/src`) | Leaflet calls replaced by `MapEngine` calls |
| `app/api/competition_live.py` | Live count proxy: member gate, rate limit, visible point, Aggregate call, timeout, no persistence |
| `app/api/access.py` | `visible_point(conn, listing_id, geo_vintage) -> tuple[float, float] | None` (D8 rule) |
| `app/census/google_aggregate.py` | Aggregate client (sync from the Census plan, plus `count_operational_async`) |
| `migrations/009_google_registry.sql` | Registry rows `google_maps_js`, `google_places_live`; notes update on `google_places_aggregate` |
| `frontend/e2e/visual.spec.ts`, `frontend/e2e/harness.ts` | Map-viewport mask while `DESIGN_HAS_GOOGLE_MAP=false`; Google loader stub route |
| `DEPLOY.md`, `docs/RUNBOOK-google-quota.md` | Console setup, keys, quotas, what to do when a quota trips |

---

### Task G1: Google Cloud project, keys, Map ID, quotas, budget, Railway variables (ops — John, with exact steps)

**Files:**
- Create: `DEPLOY.md` §"Google Maps Platform", `scripts/verify-google.sh`
- Test: manual verification commands below (no automated test can hold a live key)

**Interfaces:**
- Produces: Railway variables `VITE_GOOGLE_MAPS_BROWSER_KEY`, `VITE_GOOGLE_MAPS_MAP_ID` (service `api`, both environments; consumed at image build as Dockerfile `ARG`s like `ARG COMMIT_SHA`), `GOOGLE_MAPS_SERVER_KEY` (service `api`, runtime); `settings.google_maps_server_key: str | None`.

- [ ] **Step 1: Console setup (John)**

1. Google Cloud console → New project **`practice-match`** under the VIN Foundation organisation; link the VIN Foundation billing account.
2. APIs & Services → Enable **Maps JavaScript API**, **Places API (New)**, **Places Aggregate API**. Do **not** enable "Places API" (legacy).
3. Credentials → Create API key **`practice-match-browser`** → Application restrictions: *Websites* — `https://foundation.vin/*`, `https://qa.foundation.vin/*`, `http://localhost:5173/*` → API restrictions: *Restrict key* — Maps JavaScript API, Places API (New).
4. Credentials → Create API key **`practice-match-server`** → Application restrictions: *None* (Railway egress addresses are not fixed) → API restrictions: Places Aggregate API only.
5. Map Management → Create Map ID **`practice-match-web`** (Map type: JavaScript, Vector, Tilt/Rotation off) → Map Styles → New style from *Light*: Points of interest → labels off; Roads → arterial `#f2f2f2`, local `#f7f7f7`; Water `#d5e6f2`; Parks `#e9f1e6`; Administrative labels colour `#5b6770` → associate with the Map ID.
6. APIs & Services → Quotas: Maps JavaScript API *Map loads per day* → 5,000; Places API (New) *Nearby Search requests per day* → 2,000; Places Aggregate API *Requests per day* → 2,000.
7. Billing → Budgets & alerts → **`practice-match-maps`**, $50 per month, thresholds 50 %, 90 %, 100 %, email John.

- [ ] **Step 2: Railway variables (John or the executor with John's keys pasted only into the terminal)**

```bash
railway status                         # 🚦 must print: Project: Practice Match
for env in QA production; do
  railway variables --set VITE_GOOGLE_MAPS_BROWSER_KEY=<browser key> --set VITE_GOOGLE_MAPS_MAP_ID=practice-match-web --service api --environment $env
  railway variables --set GOOGLE_MAPS_SERVER_KEY=<server key> --service api --environment $env
done
```

- [ ] **Step 2b: Failing shell test for the verification script**

`tests/scripts/test_verify_google.sh` — runs `scripts/verify-google.sh` against a stubbed `curl` so the script's parsing and its "never print a key" rule are proved without a live key:
```bash
#!/usr/bin/env bash
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }
STUB=$(mktemp -d); trap 'rm -rf "$STUB"' EXIT
cat > "$STUB/curl" <<'SH'
#!/usr/bin/env bash
# areainsights → a count; anything with -w '%{http_code}' → 200
case "$*" in *areainsights.googleapis.com*) echo '{"count": 17}';; *http_code*) echo 200;; *) echo '{}';; esac
SH
chmod +x "$STUB/curl"
out=$(PATH="$STUB:$PATH" GOOGLE_MAPS_SERVER_KEY=secret-server VITE_GOOGLE_MAPS_BROWSER_KEY=secret-browser bash scripts/verify-google.sh 2>&1) || fail "script exited non-zero: $out"
[[ "$out" == *"aggregate ok, Cedar Park 8 km count: 17"* ]] || fail "count line missing: $out"
[[ "$out" != *secret-server* && "$out" != *secret-browser* ]] || fail "a key value leaked into the output"
if PATH="$STUB:$PATH" bash scripts/verify-google.sh >/dev/null 2>&1; then fail "missing GOOGLE_MAPS_SERVER_KEY must fail"; fi
echo "verify-google.sh OK"
```
Run: `bash tests/scripts/test_verify_google.sh` → **FAIL** (`scripts/verify-google.sh: No such file or directory`).

- [ ] **Step 3: Verify from the terminal**

`scripts/verify-google.sh`:
```bash
#!/usr/bin/env bash
# Verifies the server key against the Places Aggregate API and the browser key's referrer rule. Prints counts, never keys.
set -euo pipefail
: "${GOOGLE_MAPS_SERVER_KEY:?set in the shell for this check only}"
curl -sS -X POST "https://areainsights.googleapis.com/v1:computeInsights" \
  -H "X-Goog-Api-Key: ${GOOGLE_MAPS_SERVER_KEY}" -H "Content-Type: application/json" \
  -d '{"insights":["INSIGHT_COUNT"],"filter":{"locationFilter":{"circle":{"latLng":{"latitude":30.5052,"longitude":-97.8203},"radius":8000}},"typeFilter":{"includedTypes":["veterinary_care"]},"operatingStatus":["OPERATING_STATUS_OPERATIONAL"]}}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("aggregate ok, Cedar Park 8 km count:", d.get("count", d))'
# Browser key: a request without an allowed referrer must be refused.
: "${VITE_GOOGLE_MAPS_BROWSER_KEY:?}"
code=$(curl -s -o /dev/null -w '%{http_code}' "https://maps.googleapis.com/maps/api/js?key=${VITE_GOOGLE_MAPS_BROWSER_KEY}&v=weekly")
echo "browser key without referrer -> HTTP ${code} (200 is expected: the JS loads; the referrer check happens at runtime — open the QA site and confirm no RefererNotAllowedMapError in the console)"
```
Expected: an integer count for Cedar Park (a plausibility check: tens, not thousands), and no `RefererNotAllowedMapError` on `https://qa.foundation.vin`.

Run: `bash tests/scripts/test_verify_google.sh` → `verify-google.sh OK` (GREEN) **before** the live run against the real keys; add it to the backend CI job.

- [ ] **Step 4: Document and commit**

Add the §"Google Maps Platform" section to `DEPLOY.md` with the steps above (keys named, never valued). Commit: `docs(deploy): Google Maps Platform project, keys, Map ID, quotas, budget`.

---

### Task G2: `MapEngine` interface, loader and `GoogleMapEngine`; replace Leaflet in the two map components

**Files:**
- Create: `frontend/src/map/engine.ts`, `frontend/src/map/loader.ts`, `frontend/src/map/google.ts`, `frontend/tests/unit/map/google-stub.ts`, `frontend/tests/unit/map/loader.test.ts`, `frontend/tests/unit/map/google.test.ts`
- Modify: the two Leaflet components (`grep -rl "from 'leaflet'" frontend/src`), `frontend/package.json` (remove `leaflet`, add nothing — the API loads from Google), `frontend/.eslintrc.cjs` (`no-restricted-imports` for `leaflet`), `frontend/index.html` (remove the Leaflet CSS link), `Dockerfile` (`ARG VITE_GOOGLE_MAPS_BROWSER_KEY`, `ARG VITE_GOOGLE_MAPS_MAP_ID`)

**Interfaces:**
- Produces: `MapEngine` (`mount(el, center, zoom)`, `setBase('street'|'satellite')`, `setView(center, zoom)`, `fitBounds(points)`, `circle(center, radiusM, style, group?) -> Handle`, `marker(pos, contentEl, group?) -> Handle`, `clear(group)`, `destroy()`), `loadGoogleMaps(key, version='weekly') -> Promise<typeof google>`, `new GoogleMapEngine({ g, mapId })`, `makeGoogleStub(nearby?) -> typeof google` (tests).

- [ ] **Step 1: Failing tests**

`frontend/tests/unit/map/google-stub.ts`:
```ts
// A deterministic stand-in for the Maps JavaScript API. Records calls; renders marker content into the map element.
import type { LatLng } from '../../../src/map/engine';

export interface StubPlace { id: string; displayName: string; formattedAddress: string; lat: number; lng: number; businessStatus: string; primaryType: string; rating?: number; userRatingCount?: number }

export function makeGoogleStub(nearby: StubPlace[] = []) {
  class LatLngBounds { pts: LatLng[] = []; extend(p: LatLng) { this.pts.push(p); return this; } }
  class Map {
    typeId = 'roadmap'; fitted: LatLng[] = [];
    constructor(public el: HTMLElement, public opts: Record<string, unknown>) { el.dataset.mapId = String(opts.mapId); }
    setMapTypeId(t: string) { this.typeId = t; }
    setCenter(c: LatLng) { this.opts.center = c; }
    setZoom(z: number) { this.opts.zoom = z; }
    fitBounds(b: LatLngBounds) { this.fitted = b.pts; }
  }
  class Circle {
    static live = new Set<Circle>();
    constructor(public opts: Record<string, unknown>) { Circle.live.add(this); }
    setMap(m: unknown) { if (!m) Circle.live.delete(this); }
  }
  class AdvancedMarkerElement {
    private _map: Map | null = null; position: LatLng; content: HTMLElement;
    constructor(o: { map: Map; position: LatLng; content: HTMLElement }) { this.position = o.position; this.content = o.content; this.map = o.map; }
    get map() { return this._map; }
    set map(m: Map | null) { this._map = m; if (m) m.el.appendChild(this.content); else this.content.remove(); }
  }
  class Place {
    static lastRequest: Record<string, unknown> | null = null;
    static async searchNearby(req: Record<string, unknown>) {
      Place.lastRequest = req;
      return { places: nearby.map((p) => ({ ...p, location: { lat: () => p.lat, lng: () => p.lng }, attributions: [] })) };
    }
  }
  const SearchNearbyRankPreference = { DISTANCE: 'DISTANCE', POPULARITY: 'POPULARITY' };
  const libs: Record<string, unknown> = { maps: { Map, Circle, LatLngBounds }, marker: { AdvancedMarkerElement }, places: { Place, SearchNearbyRankPreference } };
  const g = { maps: { importLibrary: async (name: string) => libs[name], Map, Circle, LatLngBounds, marker: { AdvancedMarkerElement }, places: { Place, SearchNearbyRankPreference } } };
  return { g: g as unknown as typeof google, Circle, Place, Map };
}
```

`frontend/tests/unit/map/loader.test.ts`:
```ts
import { describe, expect, it, beforeEach } from 'vitest';
import { loadGoogleMaps } from '../../../src/map/loader';

describe('loadGoogleMaps', () => {
  beforeEach(() => { document.head.innerHTML = ''; delete (window as any).google; });

  it('adds one async bootstrap script with the key, weekly channel and a ready callback, and resolves on callback', async () => {
    const p = loadGoogleMaps('KEY');
    const scripts = document.head.querySelectorAll('script');
    expect(scripts).toHaveLength(1);
    expect(scripts[0].src).toBe('https://maps.googleapis.com/maps/api/js?key=KEY&v=weekly&loading=async&callback=__pmMapsReady');
    expect(scripts[0].async).toBe(true);
    (window as any).google = { maps: {} };
    (window as any).__pmMapsReady();
    await expect(p).resolves.toBe((window as any).google);
  });

  it('loads once — a second call returns the same promise and adds no script', async () => {
    const a = loadGoogleMaps('KEY'); const b = loadGoogleMaps('KEY');
    expect(a).toBe(b);
    expect(document.head.querySelectorAll('script')).toHaveLength(1);
  });
});
```

`frontend/tests/unit/map/google.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { GoogleMapEngine } from '../../../src/map/google';
import { makeGoogleStub } from './google-stub';

async function mounted() {
  const { g, Circle, Map } = makeGoogleStub();
  const el = document.createElement('div');
  const engine = new GoogleMapEngine({ g, mapId: 'practice-match-web' });
  await engine.mount(el, { lat: 30.27, lng: -97.74 }, 10);
  return { engine, el, Circle, Map };
}

describe('GoogleMapEngine', () => {
  it('mounts a Google map with the Map ID, default UI off, and marks the element', async () => {
    const { el } = await mounted();
    expect(el.dataset.map).toBe('google');
    expect(el.dataset.mapId).toBe('practice-match-web');
  });

  it('draws circles with the design radius and colour and removes them by group', async () => {
    const { engine, Circle } = await mounted();
    engine.circle({ lat: 30.27, lng: -97.74 }, 8000, { color: '#003a70', fillOpacity: 0.2 }, 'drive');
    engine.circle({ lat: 30.27, lng: -97.74 }, 16000, { color: '#339dde', fillOpacity: 0.16 }, 'drive');
    const opts = [...Circle.live].map((c) => c.opts);
    expect(opts.map((o) => o.radius)).toEqual([8000, 16000]);
    expect(opts[0]).toMatchObject({ strokeColor: '#003a70', fillColor: '#003a70', fillOpacity: 0.2, clickable: false });
    engine.clear('drive');
    expect(Circle.live.size).toBe(0);
  });

  it('places HTML markers into the map element and removes them by group', async () => {
    const { engine, el } = await mounted();
    const dot = document.createElement('div'); dot.className = 'dot';
    engine.marker({ lat: 30.5, lng: -97.8 }, dot, 'competition');
    expect(el.querySelector('.dot')).toBe(dot);
    engine.clear('competition');
    expect(el.querySelector('.dot')).toBeNull();
  });

  it('switches satellite to the hybrid map type and back to roadmap', async () => {
    const { engine, el } = await mounted();
    engine.setBase('satellite');
    engine.setBase('street');
    // the stub records the last type on the Map instance attached to the element
    expect((el as any).__lastTypeIds ?? ['hybrid', 'roadmap']).toEqual(['hybrid', 'roadmap']);
  });
});
```
(The last assertion is made real in Step 3 by having the engine record `el.__lastTypeIds` only in test builds? No — keep production clean: change the stub's `setMapTypeId` to push onto `this.el.dataset.typeIds` and assert `el.dataset.typeIds === 'hybrid,roadmap'`. Do that in Step 3 while making tests pass; the stub is test code.)

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run tests/unit/map` → FAIL (`Cannot find module '../../../src/map/loader'`).

- [ ] **Step 3: Implement**

`frontend/src/map/engine.ts`:
```ts
export interface LatLng { lat: number; lng: number }
export interface Handle { remove(): void }
export interface CircleStyle { color: string; fillOpacity: number; weight?: number }
export type BaseKind = 'street' | 'satellite';

/** The only map API the components use. One implementation (Google) exists; the interface keeps the components engine-agnostic and testable. */
export interface MapEngine {
  mount(el: HTMLElement, center: LatLng, zoom: number): Promise<void>;
  setBase(kind: BaseKind): void;
  setView(center: LatLng, zoom: number): void;
  fitBounds(points: LatLng[]): void;
  circle(center: LatLng, radiusM: number, style: CircleStyle, group?: string): Handle;
  marker(pos: LatLng, content: HTMLElement, group?: string): Handle;
  clear(group: string): void;
  destroy(): void;
}
```

`frontend/src/map/loader.ts`:
```ts
declare global { interface Window { google?: typeof google; __pmMapsReady?: () => void } }

let pending: Promise<typeof google> | null = null;

/** Bootstrap loader (Google's recommended `loading=async` form). One script tag per page; libraries are imported lazily by the engine. */
export function loadGoogleMaps(key: string, version = 'weekly'): Promise<typeof google> {
  if (window.google?.maps && !pending) return Promise.resolve(window.google);
  if (pending) return pending;
  pending = new Promise<typeof google>((resolve, reject) => {
    window.__pmMapsReady = () => resolve(window.google as typeof google);
    const s = document.createElement('script');
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=${encodeURIComponent(version)}&loading=async&callback=__pmMapsReady`;
    s.async = true;
    s.onerror = () => { pending = null; reject(new Error('Google Maps failed to load')); };
    document.head.appendChild(s);
  });
  return pending;
}
```

`frontend/src/map/google.ts`:
```ts
import type { BaseKind, CircleStyle, Handle, LatLng, MapEngine } from './engine';

export interface GoogleEngineOptions { g: typeof google; mapId: string }

export class GoogleMapEngine implements MapEngine {
  private map!: google.maps.Map;
  private readonly groups = new Map<string, Set<{ remove(): void }>>();
  constructor(private readonly opts: GoogleEngineOptions) {}

  async mount(el: HTMLElement, center: LatLng, zoom: number): Promise<void> {
    const { Map } = (await this.opts.g.maps.importLibrary('maps')) as google.maps.MapsLibrary;
    await this.opts.g.maps.importLibrary('marker');
    // disableDefaultUI removes controls only. The Google logo, "Map data ©" and Terms link are rendered by the API
    // and must stay exactly as rendered (Maps JavaScript API policies).
    this.map = new Map(el, { center, zoom, mapId: this.opts.mapId, disableDefaultUI: true, zoomControl: true, gestureHandling: 'greedy', clickableIcons: false });
    el.dataset.map = 'google';
  }
  setBase(kind: BaseKind): void { this.map.setMapTypeId(kind === 'satellite' ? 'hybrid' : 'roadmap'); }
  setView(center: LatLng, zoom: number): void { this.map.setCenter(center); this.map.setZoom(zoom); }
  fitBounds(points: LatLng[]): void {
    const b = new this.opts.g.maps.LatLngBounds();
    for (const p of points) b.extend(p);
    this.map.fitBounds(b, 24);
  }
  circle(center: LatLng, radiusM: number, style: CircleStyle, group = 'default'): Handle {
    const c = new this.opts.g.maps.Circle({ map: this.map, center, radius: radiusM, strokeColor: style.color, strokeWeight: style.weight ?? 1, fillColor: style.color, fillOpacity: style.fillOpacity, clickable: false });
    return this.track(group, { remove: () => c.setMap(null) });
  }
  marker(pos: LatLng, content: HTMLElement, group = 'default'): Handle {
    const m = new this.opts.g.maps.marker.AdvancedMarkerElement({ map: this.map, position: pos, content });
    return this.track(group, { remove: () => { m.map = null; } });
  }
  clear(group: string): void { this.groups.get(group)?.forEach((h) => h.remove()); this.groups.delete(group); }
  destroy(): void { for (const g of [...this.groups.keys()]) this.clear(g); }
  private track(group: string, h: { remove(): void }): Handle {
    const set = this.groups.get(group) ?? new Set<{ remove(): void }>();
    this.groups.set(group, set); set.add(h);
    return { remove: () => { h.remove(); set.delete(h); } };
  }
}
```

Component changes (both Leaflet components): replace `L.map(el, …)` with `const engine = new GoogleMapEngine({ g: await loadGoogleMaps(import.meta.env.VITE_GOOGLE_MAPS_BROWSER_KEY), mapId: import.meta.env.VITE_GOOGLE_MAPS_MAP_ID }); await engine.mount(el, center, zoom)`; `L.tileLayer(esriUrl)` → nothing (the Map ID's cloud style is the basemap); the satellite toggle → `engine.setBase(kind)`; `L.circle(hub, { radius: 8000, color: '#003a70', fillOpacity: .2 })` → `engine.circle(hub, 8000, { color: '#003a70', fillOpacity: 0.2 }, 'drive')`; every `L.marker(pos, { icon: L.divIcon({ html }) })` → build the same HTML into an element and `engine.marker(pos, el, group)`; `bindTooltip(text)` → the marker element gets `title={text}` and the design's tooltip class rendered on hover inside the marker element itself (the design's tooltip markup and CSS are reused verbatim); `map.fitBounds(…)` → `engine.fitBounds(points)`. Remove the Leaflet CSS link from `index.html`, `leaflet` from `package.json`, and add to ESLint: `'no-restricted-imports': ['error', { paths: [{ name: 'leaflet', message: 'Terms §3.2.3(e): one map engine. Use src/map/engine.ts.' }] }]`. Dockerfile: `ARG VITE_GOOGLE_MAPS_BROWSER_KEY` and `ARG VITE_GOOGLE_MAPS_MAP_ID` before `npm run build` (Railway supplies declared ARGs from service variables, as with `ARG ENVIRONMENT`).

- [ ] **Step 4: Run to verify passing**

Run: `cd frontend && npx vitest run tests/unit/map && npm run lint && npm run build` → tests pass; lint passes (no `leaflet` import anywhere); the bundle contains no `leaflet` string (`! grep -q leaflet dist/_app/*.js`).

- [ ] **Step 5: Commit**

```bash
git add frontend Dockerfile
git commit -m "feat(map): Google Maps engine — loader, MapEngine adapter, Leaflet removed (Terms §3.2.3(e))

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task G3: Live competitor pins — `searchVets`, display filter, address merge, saturation, composable

**Files:**
- Create: `frontend/src/map/competition.ts`, `frontend/src/map/useCompetitionLive.ts`, `frontend/tests/unit/map/competition.test.ts`
- Modify: the market map component (layer toggle `competition_live_points` → composable)

**Interfaces:**
- Consumes: `MapEngine`, `loadGoogleMaps`, `/api/layers` entry `competition_live_points` (`enabled`, `options.ratings`, `caveat`).
- Produces: `searchVets(g, center, radiusM, { ratings }) -> Promise<{ places: Competitor[]; saturated: boolean }>`; `Competitor { id, name, address, position, status, primaryType, rating?, ratingCount?, attributions: string[] }`; `pinContent(c: Competitor) -> HTMLElement`; `useCompetitionLive(engine, layers, hub, band)`.

- [ ] **Step 1: Failing tests**

`frontend/tests/unit/map/competition.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { pinContent, searchVets } from '../../../src/map/competition';
import { makeGoogleStub, type StubPlace } from './google-stub';

const clinic: StubPlace = { id: 'a', displayName: 'Cedar Park Animal Hospital', formattedAddress: '100 Main St, Cedar Park, TX 78613', lat: 30.5, lng: -97.82, businessStatus: 'OPERATIONAL', primaryType: 'veterinary_care' };
const practitioner: StubPlace = { ...clinic, id: 'b', displayName: 'Jane Doe, DVM' };                       // same address → merged
const closed: StubPlace = { ...clinic, id: 'c', formattedAddress: '9 Elm St, Cedar Park, TX', businessStatus: 'CLOSED_PERMANENTLY' };
const groomer: StubPlace = { ...clinic, id: 'd', formattedAddress: '5 Oak St, Cedar Park, TX', primaryType: 'pet_groomer' };

describe('searchVets', () => {
  it('requests operational veterinary_care places by distance within the band radius, Pro fields only by default', async () => {
    const { g, Place } = makeGoogleStub([clinic]);
    await searchVets(g, { lat: 30.5, lng: -97.82 }, 8000, { ratings: false });
    expect(Place.lastRequest).toEqual({
      fields: ['id', 'displayName', 'location', 'formattedAddress', 'businessStatus', 'primaryType', 'attributions'],
      locationRestriction: { center: { lat: 30.5, lng: -97.82 }, radius: 8000 },
      includedPrimaryTypes: ['veterinary_care'], maxResultCount: 20, rankPreference: 'DISTANCE',
    });
  });

  it('adds rating fields only when the layer option asks (Enterprise SKU)', async () => {
    const { g, Place } = makeGoogleStub([clinic]);
    await searchVets(g, { lat: 30.5, lng: -97.82 }, 8000, { ratings: true });
    expect((Place.lastRequest as any).fields).toEqual(expect.arrayContaining(['rating', 'userRatingCount']));
  });

  it('merges practitioner listings at the same address and drops closed and non-veterinary places', async () => {
    const { g } = makeGoogleStub([clinic, practitioner, closed, groomer]);
    const { places, saturated } = await searchVets(g, { lat: 30.5, lng: -97.82 }, 8000, { ratings: false });
    expect(places.map((p) => p.id)).toEqual(['a']);
    expect(saturated).toBe(false);
  });

  it('flags saturation when Google returns the 20-result maximum', async () => {
    const twenty = Array.from({ length: 20 }, (_, i) => ({ ...clinic, id: `p${i}`, formattedAddress: `${i} Main St` }));
    const { g } = makeGoogleStub(twenty);
    expect((await searchVets(g, { lat: 30.5, lng: -97.82 }, 16000, { ratings: false })).saturated).toBe(true);
  });
});

describe('pinContent', () => {
  it('renders the design pin with name and address, Google attribution text, and no coordinates in the DOM', () => {
    const el = pinContent({ id: 'a', name: 'Cedar Park Animal Hospital', address: '100 Main St', position: { lat: 30.5, lng: -97.82 }, status: 'OPERATIONAL', primaryType: 'veterinary_care', attributions: [] });
    expect(el.className).toBe('vet-pin');
    expect(el.querySelector('.vet-pin__tip')?.textContent).toContain('Cedar Park Animal Hospital');
    expect(el.querySelector('.vet-pin__tip')?.textContent).toContain('Google Maps');
    expect(el.outerHTML).not.toMatch(/30\.5|-97\.82/);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run tests/unit/map/competition.test.ts` → FAIL (module missing).

- [ ] **Step 3: Implement**

`frontend/src/map/competition.ts`:
```ts
import type { LatLng } from './engine';

export interface Competitor { id: string; name: string; address: string; position: LatLng; status: string; primaryType: string; rating?: number; ratingCount?: number; attributions: string[] }

const PRO_FIELDS = ['id', 'displayName', 'location', 'formattedAddress', 'businessStatus', 'primaryType', 'attributions'];
const ENTERPRISE_FIELDS = ['rating', 'userRatingCount'];
export const MAX_RESULTS = 20; // Nearby Search (New) maximum; there is no pagination

/**
 * One Nearby Search per band. Results live in memory for this view only — nothing here is ever persisted
 * (Google Maps Platform Terms §3.2.3(a)/(b)), and nothing here is counted into a metric (§3.2.3(c)(iv)).
 */
export async function searchVets(g: typeof google, center: LatLng, radiusM: number, opts: { ratings: boolean }): Promise<{ places: Competitor[]; saturated: boolean }> {
  const { Place, SearchNearbyRankPreference } = (await g.maps.importLibrary('places')) as google.maps.PlacesLibrary;
  const fields = opts.ratings ? [...PRO_FIELDS, ...ENTERPRISE_FIELDS] : [...PRO_FIELDS];
  const { places } = await Place.searchNearby({ fields, locationRestriction: { center, radius: radiusM }, includedPrimaryTypes: ['veterinary_care'], maxResultCount: MAX_RESULTS, rankPreference: SearchNearbyRankPreference.DISTANCE });
  const seen = new Set<string>();
  const out: Competitor[] = [];
  for (const p of places) {
    if (p.primaryType !== 'veterinary_care' || p.businessStatus !== 'OPERATIONAL' || !p.location) continue;
    const key = (p.formattedAddress ?? p.id).trim().toLowerCase();   // practitioner listings share the clinic's address
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ id: p.id, name: p.displayName ?? '', address: p.formattedAddress ?? '', position: { lat: p.location.lat(), lng: p.location.lng() }, status: p.businessStatus ?? '', primaryType: p.primaryType ?? '',
      rating: p.rating ?? undefined, ratingCount: p.userRatingCount ?? undefined, attributions: (p.attributions ?? []).map((a) => a.provider ?? '') });
  }
  return { places: out, saturated: places.length >= MAX_RESULTS };
}

/** The design's competitor pin (class names from the approved CSS) with a hover tip. No coordinates are written into the DOM. */
export function pinContent(c: Competitor): HTMLElement {
  const el = document.createElement('div');
  el.className = 'vet-pin';
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', c.name);
  const tip = document.createElement('div');
  tip.className = 'vet-pin__tip';
  const rating = c.rating != null ? ` · ${c.rating.toFixed(1)}★ (${c.ratingCount ?? 0})` : '';
  tip.textContent = `${c.name}${rating} — ${c.address} · Google Maps${c.attributions.length ? ' · ' + c.attributions.join(', ') : ''}`;
  el.appendChild(tip);
  return el;
}
```

`frontend/src/map/useCompetitionLive.ts`:
```ts
import { watch, type Ref } from 'vue';
import type { LatLng, MapEngine } from './engine';
import { pinContent, searchVets } from './competition';

export interface LayerInfo { enabled: boolean; options?: { ratings?: boolean }; caveat: string }
export const BAND_RADIUS_M: Record<string, number> = { place: 8000, drive_10: 8000, drive_20: 16000 };

/** Redraws the live competitor pins whenever the layer is on and the hub or band changes. Errors hide the layer and surface `note`. */
export function useCompetitionLive(engine: MapEngine, g: () => Promise<typeof google>, layer: Ref<LayerInfo | undefined>, on: Ref<boolean>, hub: Ref<LatLng | null>, band: Ref<string>, note: Ref<string>) {
  let seq = 0;
  watch([layer, on, hub, band], async ([l, isOn, h, b]) => {
    const my = ++seq;
    engine.clear('competition');
    note.value = '';
    if (!l?.enabled || !isOn || !h) return;
    try {
      const { places, saturated } = await searchVets(await g(), h, BAND_RADIUS_M[b] ?? 8000, { ratings: Boolean(l.options?.ratings) });
      if (my !== seq) return;                                        // a newer selection superseded this one
      for (const p of places) engine.marker(p.position, pinContent(p), 'competition');
      note.value = saturated ? `The 20 nearest are shown. ${l.caveat}` : l.caveat;
    } catch (e) {
      if (my !== seq) return;
      note.value = /RESOURCE_EXHAUSTED|429/.test(String(e)) ? 'Live practice pins are temporarily unavailable (daily limit reached).' : 'Live practice pins are unavailable right now.';
    }
  }, { immediate: true });
}
```
Wire the composable into the market map component where the Leaflet competition dots were drawn; the Census `competition` dots remain the design's density layer and are unaffected.

- [ ] **Step 4: Run to verify passing**

Run: `cd frontend && npx vitest run tests/unit/map` → pass; `npm run build`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/map frontend/tests/unit/map frontend/src/components
git commit -m "feat(map): live Google Places competitor pins — display filter, address merge, saturation note

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task G4: Live count proxy — `GET /api/listings/{id}/competition/live`

**Files:**
- Create: `app/api/competition_live.py`, `tests/api/test_competition_live.py`
- Modify: `app/api/access.py` (add `visible_point`), `app/census/google_aggregate.py` (add `count_operational_async`), `app/config.py` (`google_maps_server_key: str | None = None`), `app/main.py` (include router)

**Interfaces:**
- Consumes: `require_member` (SP2), `registry.is_cleared(conn, key)` and `registry.load(conn)["tiger_cb"].vintage` (Census plan A1), `practice_location` and `geo_area` (Census plan), `settings.redis_url`.
- Produces: the endpoint above; `access.visible_point(conn, listing_id, geo_vintage) -> tuple[float, float] | None`; `google_aggregate.count_operational_async(http, area, api_key) -> int`; `competition_live.BANDS = {"place": 8000, "drive_10": 8000, "drive_20": 16000}`, `RATE_LIMIT = (30, 60)`, `UPSTREAM_TIMEOUT_S = 10.0`; dependency `competition_live.http_client()` (overridable in tests).

- [ ] **Step 1: Failing tests**

`tests/api/test_competition_live.py` (uses the Census plan's `client`, `conn`, `world`/`materialized` fixtures and a member session fixture `member_headers` from SP2's tests):
```python
import json

import httpx
import pytest

from app.api import competition_live as CL
from app.main import app


def _override(handler):
    async def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=httpx.Timeout(CL.UPSTREAM_TIMEOUT_S))
    app.dependency_overrides[CL.http_client] = factory


@pytest.fixture
def google_cleared(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key IN ('google_maps_js','google_places_live','google_places_aggregate')")
    conn.commit()


@pytest.fixture(autouse=True)
def server_key(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "google_maps_server_key", "server-k")
    yield
    app.dependency_overrides.clear()


async def test_gate_closed_returns_null_count_and_makes_no_google_call(client, materialized, member_headers):
    def handler(req):  # noqa: ANN001
        raise AssertionError("no upstream call while google_places_aggregate is uncleared")
    _override(handler)
    r = await client.get(f"/api/listings/{materialized}/competition/live?band=drive_10", headers=member_headers)
    assert r.status_code == 200 and r.json() == {"band": "drive_10", "radius_m": 8000, "count": None, "reason": "gate"}


async def test_live_count_proxies_the_aggregate_api_for_the_visible_point_and_stores_nothing(client, conn, materialized, member_headers, google_cleared):
    seen = {}
    def handler(req):  # noqa: ANN001
        seen["key"], seen["body"] = req.headers["X-Goog-Api-Key"], json.loads(req.content)
        return httpx.Response(200, json={"count": 12})
    _override(handler)
    r = await client.get(f"/api/listings/{materialized}/competition/live?band=drive_20", headers=member_headers)
    body = r.json()
    assert r.status_code == 200 and body["count"] == 12 and body["radius_m"] == 16000 and body["source"] == "Google Maps" and body["attribution"] == "Google Maps"
    assert seen["key"] == "server-k"
    assert seen["body"]["filter"]["locationFilter"]["circle"]["radius"] == 16000
    assert seen["body"]["filter"]["typeFilter"] == {"includedTypes": ["veterinary_care"]}
    # The fixture listing is not location_disclosed: the circle is centred on the place centroid (D8), not the geocoded point.
    c = seen["body"]["filter"]["locationFilter"]["circle"]["latLng"]
    assert (round(c["latitude"], 2), round(c["longitude"], 2)) == (30.55, -97.80)
    with conn.cursor() as cur:  # nothing persisted anywhere
        cur.execute("SELECT count(*) FROM information_schema.columns WHERE column_name ILIKE '%google%' OR table_name ILIKE '%google%'")
        assert cur.fetchone()[0] == 0


async def test_quota_and_timeout_degrade_to_reasons(client, materialized, member_headers, google_cleared):
    _override(lambda req: httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}}))
    assert (await client.get(f"/api/listings/{materialized}/competition/live", headers=member_headers)).json()["reason"] == "quota"
    def slow(req):  # noqa: ANN001
        raise httpx.ReadTimeout("slow", request=req)
    _override(slow)
    assert (await client.get(f"/api/listings/{materialized}/competition/live", headers=member_headers)).json()["reason"] == "timeout"


async def test_requires_a_member_and_rate_limits_per_member(client, materialized, member_headers, google_cleared):
    assert (await client.get(f"/api/listings/{materialized}/competition/live")).status_code in (401, 403)
    _override(lambda req: httpx.Response(200, json={"count": 1}))
    codes = [(await client.get(f"/api/listings/{materialized}/competition/live", headers=member_headers)).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


async def test_unknown_band_is_rejected(client, materialized, member_headers):
    assert (await client.get(f"/api/listings/{materialized}/competition/live?band=walk", headers=member_headers)).status_code == 422
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/api/test_competition_live.py -q` → FAIL (`ImportError: app.api.competition_live`).

- [ ] **Step 3: Implement**

`app/api/access.py` — add:
```python
def visible_point(conn, listing_id, geo_vintage: str) -> tuple[float, float] | None:
    """D8: the geocoded point only when the seller disclosed the location; otherwise the place centroid. WGS84 (lat, lng)."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT CASE WHEN l.location_disclosed THEN ST_Y(ST_Transform(pl.point, 4326)) ELSE ST_Y(ST_Transform(ga.centroid, 4326)) END AS lat,
                      CASE WHEN l.location_disclosed THEN ST_X(ST_Transform(pl.point, 4326)) ELSE ST_X(ST_Transform(ga.centroid, 4326)) END AS lng
                 FROM practice_location pl
                 JOIN listing l ON l.id = pl.listing_id AND l.status = 'published'
                 LEFT JOIN geo_area ga ON ga.summary_level = '160' AND ga.geo_id = pl.place_geoid AND ga.vintage = %s
                WHERE pl.listing_id = %s""",
            (geo_vintage, listing_id),
        )
        row = cur.fetchone()
    return None if not row or row[0] is None else (float(row[0]), float(row[1]))
```

`app/census/google_aggregate.py` — add beside `count_operational`:
```python
async def count_operational_async(http: httpx.AsyncClient, area: Circle | Polygon, api_key: str) -> int:
    r = await http.post(ENDPOINT, json=request_body(area), headers={"X-Goog-Api-Key": api_key})
    r.raise_for_status()
    return int(r.json().get("count", 0))
```

`app/api/competition_live.py`:
```python
"""Live Google count for a listing's band — fetched per request, never persisted (Google Maps Platform Terms §3.2.3(a)/(b))."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.access import require_member, visible_point
from app.census import google_aggregate as G
from app.census.registry import is_cleared, load
from app.config import settings
from app.db import sync_conn

router = APIRouter()
BANDS = {"place": 8000, "drive_10": 8000, "drive_20": 16000}
RATE_LIMIT = (30, 60)          # requests, seconds, per member
UPSTREAM_TIMEOUT_S = 10.0
Band = Literal["place", "drive_10", "drive_20"]


async def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(UPSTREAM_TIMEOUT_S, connect=5.0))


_redis: aioredis.Redis | None = None


def _r() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url)
    return _redis


async def _rate_limit(member_id: str) -> None:
    key = f"competition_live:{member_id}:{int(datetime.now(timezone.utc).timestamp()) // RATE_LIMIT[1]}"
    n = await _r().incr(key)
    if n == 1:
        await _r().expire(key, RATE_LIMIT[1])
    if n > RATE_LIMIT[0]:
        raise HTTPException(429, "Too many live-count requests; try again in a minute.")


@router.get("/api/listings/{listing_id}/competition/live")
async def live_count(listing_id: UUID, band: Band = Query("drive_10"), member=Depends(require_member), http: httpx.AsyncClient = Depends(http_client)) -> dict:
    await _rate_limit(str(member.id))
    radius = BANDS[band]
    base = {"band": band, "radius_m": radius}
    with sync_conn() as conn:
        if not settings.google_maps_server_key or not is_cleared(conn, "google_places_aggregate"):
            return {**base, "count": None, "reason": "gate"}
        point = visible_point(conn, listing_id, load(conn)["tiger_cb"].vintage)
    if point is None:
        raise HTTPException(404, {"error": {"code": "NO_MARKET_DATA"}})
    try:
        async with http:
            count = await G.count_operational_async(http, G.Circle(point[0], point[1], radius), settings.google_maps_server_key)
    except httpx.HTTPStatusError as e:
        return {**base, "count": None, "reason": "quota" if e.response.status_code == 429 else "upstream"}
    except httpx.TimeoutException:
        return {**base, "count": None, "reason": "timeout"}
    return {**base, "count": count, "source": "Google Maps", "attribution": "Google Maps", "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}
```
Register the router in `app/main.py` next to the market router. Add `google_maps_server_key: str | None = None` to `Settings`.

- [ ] **Step 4: Run to verify passing**

Run: `poetry run pytest tests/api/test_competition_live.py -q` → pass. `poetry run pytest -q` → everything else still green.

- [ ] **Step 5: Commit**

```bash
git add app/api/competition_live.py app/api/access.py app/census/google_aggregate.py app/config.py app/main.py tests/api/test_competition_live.py
git commit -m "feat(api): live Google Maps veterinary count per band — member-gated, rate-limited, never persisted

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task G5: Registry rows, `/api/layers` entries, the no-mixing switch in the gate

**Files:**
- Create: `migrations/009_google_registry.sql`
- Modify: `app/api/market.py:layers` (two entries), `tests/census/test_registry.py` (`SPEC_KEYS` + statuses), `tests/api/test_market_api.py` (layers assertions)

**Interfaces:**
- Consumes: `dataset_registry`, `registry.is_cleared`, the layer-entry shape from the Census plan B5.
- Produces: registry keys `google_maps_js`, `google_places_live`; layer keys `competition_live_points`, `competition_live_count`.

- [ ] **Step 1: Failing tests**

Extend `tests/census/test_registry.py`: add `"google_maps_js", "google_places_live"` to `SPEC_KEYS`; assert both `unresolved` at seed time. Extend `tests/api/test_market_api.py`:
```python
async def test_layers_carry_the_two_live_google_entries_gated_by_the_registry(client, conn, materialized):
    layers = {l["key"]: l for l in (await client.get("/api/layers")).json()["layers"]}
    assert layers["competition_live_points"]["enabled"] is False and layers["competition_live_count"]["enabled"] is False
    assert layers["competition_live_points"]["attribution"] == "Google Maps" and layers["competition_live_points"]["options"] == {"ratings": False}
    assert "not stored" in layers["competition_live_points"]["caveat"].lower() and "official" in layers["competition_live_count"]["caveat"]
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key IN ('google_maps_js','google_places_live','google_places_aggregate')")
    conn.commit()
    layers = {l["key"]: l for l in (await client.get("/api/layers")).json()["layers"]}
    assert layers["competition_live_points"]["enabled"] is True and layers["competition_live_count"]["enabled"] is True


async def test_clearing_google_maps_blocks_the_non_google_basemaps(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key='google_maps_js'")
        cur.execute("SELECT dataset_key, license_status FROM dataset_registry WHERE dataset_key IN ('osm_tiles','imagery') ORDER BY 1")
        assert cur.fetchall() == [("imagery", "blocked"), ("osm_tiles", "blocked")]
```

- [ ] **Step 2: Run to verify failure** — `poetry run pytest tests/census/test_registry.py tests/api/test_market_api.py -q` → FAIL.

- [ ] **Step 3: Implement**

`migrations/009_google_registry.sql`:
```sql
-- Greenfield Google plan (G0/G9). Rows start unresolved; Task G1's verification clears them through the admin endpoint.
INSERT INTO dataset_registry
  (dataset_key, display_name, api_dataset_id, base_url, vintage, naics_param, refresh_cadence, license_status, license_name, license_url, attribution_text, notes) VALUES
  ('google_maps_js','Google Maps JavaScript API (basemap, satellite)',NULL,'https://maps.googleapis.com/maps/api/js','live',NULL,'live','unresolved','Google Maps Platform Terms','https://cloud.google.com/maps-platform/terms','Map data ©Google (rendered by the API)','G0/G1: cleared when the VIN Foundation chooses Google, keys are restricted and quotas/budget are set. Clearing it blocks osm_tiles and imagery (Terms §3.2.3(e), one map engine).'),
  ('google_places_live','Google Places — live competitor pins (never stored)',NULL,'https://maps.googleapis.com/maps/api/js (places library)','live',NULL,'live','unresolved','Google Maps Platform Terms + SST §14','https://cloud.google.com/maps-platform/terms/maps-service-terms','Google Maps','G2/G3: displayed live on the Google map only; nothing persisted; no metric derived from pins (Terms §3.2.3(c)(iv)).');

UPDATE dataset_registry SET attribution_text = 'Google Maps',
  notes = 'G5: live count per band shown on the Google map beside the Census count; fetched per request via /api/listings/{id}/competition/live; never persisted.'
  WHERE dataset_key = 'google_places_aggregate';

-- One map engine: when Google is the basemap, the non-Google tile rows cannot be cleared.
CREATE OR REPLACE FUNCTION google_engine_blocks_other_basemaps() RETURNS trigger AS $$
BEGIN
  IF NEW.dataset_key = 'google_maps_js' AND NEW.license_status = 'cleared' THEN
    UPDATE dataset_registry SET license_status = 'blocked',
      notes = coalesce(notes, '') || ' Blocked by the one-map-engine rule (Terms §3.2.3(e)) while google_maps_js is cleared.'
      WHERE dataset_key IN ('osm_tiles', 'imagery') AND license_status <> 'blocked';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER google_engine_blocks_other_basemaps AFTER UPDATE OF license_status ON dataset_registry
  FOR EACH ROW EXECUTE FUNCTION google_engine_blocks_other_basemaps();
```

`app/api/market.py:layers` — append to the layer list:
```python
    {"key": "competition_live_points", "label": "Veterinary practices (Google Maps, live)", "dataset_key": "google_places_live", "metric": None, "is_derived": False, "geo_level": "point",
     "attribution": "Google Maps", "options": {"ratings": False},
     "caveat": "Live from Google Maps: the 20 nearest operating veterinary places are shown; practitioner listings at the same address are merged for display. Not stored; not used in any metric."},
    {"key": "competition_live_count", "label": "Veterinary places nearby (Google Maps, live)", "dataset_key": "google_places_aggregate", "metric": None, "is_derived": False, "geo_level": "band",
     "attribution": "Google Maps",
     "caveat": "Live count of operating veterinary places within the band radius, from Google Maps. The Census establishment count is the official figure used for Low/Moderate/High."},
```
`enabled` is computed exactly as for the other layers (`is_cleared(dataset_key)`).

- [ ] **Step 4: Run to verify passing** — the two test files pass; `poetry run pytest -q` green.

- [ ] **Step 5: Commit** — `feat(census): Google registry rows, live layer entries, one-map-engine trigger`.

---

### Task G6: Visual gate — Google loader stub, map-viewport mask, smoke test, design-reference hand-off

**Files:**
- Create: `frontend/e2e/stubs/google-maps.js` (generated from `google-stub.ts` by a tiny esbuild step in `package.json`: `"build:stubs": "esbuild tests/unit/map/google-stub.ts --bundle --format=iife --global-name=__stub --outfile=e2e/stubs/google-maps.js"`)
- Modify: `frontend/e2e/harness.ts` (`prepare()`), `frontend/e2e/visual.spec.ts`, `frontend/e2e/smoke.spec.ts`, `frontend/playwright.config.ts` (env `DESIGN_HAS_GOOGLE_MAP`)

**Interfaces:**
- Consumes: Platform plan Task 3's `prepare(page)` and Task 4's `smoke.spec.ts`.
- Produces: `prepare()` routes `https://maps.googleapis.com/maps/api/js**` to the stub and invokes the `callback` query parameter; `MAP_MASK = page.locator('[data-map]')` applied while `process.env.DESIGN_HAS_GOOGLE_MAP !== 'true'`.

- [ ] **Step 1: Failing tests**

`frontend/e2e/smoke.spec.ts` — add:
```ts
test('the market map mounts on the Google engine with the configured Map ID and shows live pins from the stub', async ({ page }) => {
  await prepare(page);                                         // stub serves 3 fixture places
  await page.goto('/browse?tab=market');
  await page.getByRole('button', { name: /sign in/i }).click();
  const map = page.locator('[data-map="google"]');
  await expect(map).toHaveAttribute('data-map-id', 'practice-match-web');
  await page.getByRole('checkbox', { name: /Veterinary practices \(Google Maps, live\)/ }).check();
  await expect(map.locator('.vet-pin')).toHaveCount(3);
  await expect(page.getByText(/Google Maps/)).toBeVisible();   // attribution text reaches the screen
});
```
`visual.spec.ts`: every `toHaveScreenshot` call gains `mask: process.env.DESIGN_HAS_GOOGLE_MAP === 'true' ? [] : [page.locator('[data-map]')]` in **both** the reference and app projects (the reference's Leaflet map is masked with the same selector, which the reference server injects as `data-map` on the design's map container).

- [ ] **Step 2: Run to verify failure** — `npx playwright test smoke` → FAIL (no `[data-map="google"]`; the real Google script is blocked by the harness's default network policy).

- [ ] **Step 3: Implement**

In `harness.ts` `prepare()`:
```ts
await page.route('https://maps.googleapis.com/maps/api/js**', async (route) => {
  const cb = new URL(route.request().url()).searchParams.get('callback') ?? '__pmMapsReady';
  const stub = await fs.readFile(new URL('./stubs/google-maps.js', import.meta.url), 'utf8');
  await route.fulfill({ contentType: 'application/javascript', body: `${stub}\nwindow.google = __stub.makeGoogleStub(${JSON.stringify(FIXTURE_PLACES)}).g;\nwindow[${JSON.stringify(cb)}]();` });
});
```
with `FIXTURE_PLACES` = three operational `veterinary_care` places around the fixture hub (distinct addresses). Reference server: add `data-map` to the design's map container element in the served `.dc.html` (a one-line string replace on the `id="map"` container). `playwright.config.ts`: read `DESIGN_HAS_GOOGLE_MAP` (default `'false'`).

- [ ] **Step 4: Run to verify passing** — `npx playwright test` → smoke passes; visual passes with the map masked; `DESIGN_HAS_GOOGLE_MAP=true npx playwright test visual` is **expected to fail** until the design reference is updated (this is the gate working).

- [ ] **Step 5: Design-reference hand-off (Claude Design)**

Update `Practice Match V2.dc.html` on the canvas: replace the Esri/Leaflet map frame in `MarketMap.jsx` and `AustinMap.jsx` with a Google map frame — Google logo bottom-left, "Map data ©2026 Google · Terms" bottom-right, zoom control bottom-right above it — and move the design's own bottom-left controls so they do not overlap the logo (the API refuses overlap; the policy forbids obscuring it). Export the new `.dc.html`, refresh `docs/design-reference/`, set `DESIGN_HAS_GOOGLE_MAP=true` in CI, regenerate baselines. Until that lands, the mask stays.

- [ ] **Step 6: Commit** — `test(e2e): Google loader stub, map-viewport mask, live-pins smoke`.

---

### Task G7: Runbook, health, cost guard

**Files:**
- Create: `docs/RUNBOOK-google-quota.md`
- Modify: `app/api/health.py` (`google: {"configured": bool}` in `/api/healthz`), `DEPLOY.md`

- [ ] **Step 1: Failing tests**

`tests/test_health.py` — add:
```python
async def test_healthz_reports_google_configured_without_leaking_the_key(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "google_maps_server_key", "server-k")
    r = await client.get("/api/healthz")
    assert r.json()["google"] == {"configured": True}
    assert "server-k" not in r.text
```
`tests/test_docs.py` — add:
```python
def test_google_runbook_and_deploy_variables_exist():
    assert (ROOT / "docs" / "RUNBOOK-google-quota.md").read_text().count("quota") >= 3
    text = (ROOT / "DEPLOY.md").read_text()
    for var in ("GOOGLE_MAPS_BROWSER_KEY", "GOOGLE_MAPS_MAP_ID", "GOOGLE_MAPS_SERVER_KEY"):
        assert var in text, var
```
Run: `poetry run pytest tests/test_health.py tests/test_docs.py -q` → **FAIL** (`KeyError: 'google'`, `FileNotFoundError: docs/RUNBOOK-google-quota.md`).

- [ ] **Step 2: Implement**

- Health: add `"google": {"configured": bool(settings.google_maps_server_key)}` to the healthz body.
- `docs/RUNBOOK-google-quota.md`: what a tripped quota looks like (`reason: quota`, hidden live layers, budget email), how to raise a quota deliberately (console, not code), how to rotate either key (create new → update Railway variable → `railway up` → delete old), and the monthly cost check (Cloud console → Billing → Reports filtered to the three SKUs).
- `DEPLOY.md`: the three variables and which service holds each.

- [ ] **Step 3: Run — GREEN**

Run: `poetry run pytest tests/test_health.py tests/test_docs.py -q` → all pass.

- [ ] **Step 4: Commit** — `docs(ops): Google Maps quota runbook; healthz reports google.configured`.

---

### Task G8: Deltas to the Platform and Census plans (documentation task; apply only when G0 = Google)

| Plan | Task | Change |
|---|---|---|
| Platform | Task 1 | Drop the `lib/leaflet.js` npm import and the `leaflet` dependency; keep the reference bundle's Leaflet files under `docs/design-reference/` (design fixture only). Remove the Leaflet CSS from `index.html`. Add `ARG VITE_GOOGLE_MAPS_BROWSER_KEY`, `ARG VITE_GOOGLE_MAPS_MAP_ID` to the Dockerfile. |
| Platform | Task 2 | No change (router sync is engine-agnostic). |
| Platform | Task 3 | `prepare()` gains the Google loader stub route (G6); the reference server injects `data-map`; `toHaveScreenshot` gains the map mask while `DESIGN_HAS_GOOGLE_MAP=false`. |
| Platform | Task 4 | Parity triage excludes the masked map viewport; the design-reference hand-off (G6 Step 5) is added to the DoD. |
| Platform | Task 8 | `deploy.sh` documents the three new Railway variables; `verify-deploy.sh` checks `healthz.google.configured === true` on QA. |
| Platform spec | §2, §9 | Map engine = Google Maps JavaScript API; the Esri-vs-CARTO basemap item and the satellite licence item close; attribution and no-mixing rules added. |
| Census | D3 (tiles) | Choropleth tiles, if ever built, render through `google.maps.Data`/`deck.gl` on the Google map; bucket path unchanged. |
| Census | D16 / Task C2 | Optional. Live Google pins cover the "literal competitors" need on screen; Overture remains the only source for anything that must be **stored** or **analysed** (e.g., a future exportable competitor list). |
| Census | D17 / Task C1 | **Superseded.** The live Aggregate count is displayed directly (G5); no Customer Values, no `market_freshness` table. |
| Census | Registry | `osm_tiles`, `imagery` → blocked by the G5 trigger when `google_maps_js` clears. |

- [ ] **Step 1: Failing test** — the edits above are exercised by `tests/test_docs.py::test_relative_markdown_links_resolve` (every link in the edited plans must still resolve) and by a new assertion: `assert "Map engine = Google Maps JavaScript API" in (ROOT / "docs/superpowers/specs/2026-09-05-practice-match-platform-design.md").read_text()`. Run: `poetry run pytest tests/test_docs.py -q` → **FAIL** (assertion: the spec still names Leaflet).

- [ ] **Step 2: Apply the deltas in the table.**

- [ ] **Step 3: Run — GREEN** — `poetry run pytest tests/test_docs.py -q` → all pass. Commit: `docs(plans): apply the Google-engine deltas to the Platform and Census plans`.

## Cost model (Google list prices, 0–100 K tier, after free allowances)

| Volume per month | Map loads (Dynamic Maps) | Nearby Search (pins, 1 call per band view) | Aggregate (live count, 1 call per band view) | Monthly bill |
|---|---|---|---|---|
| **V1 assumption:** 3,000 member sessions, 6,000 map loads, 2,000 competition views × 2 bands | 6,000 (≤ 10,000 free) | 4,000 (≤ 5,000 free) | 4,000 (≤ 5,000 free) | **$0** |
| 3×: 18,000 loads, 12,000 band views | 8,000 × $7 = $56 | 7,000 × $32 = $224 | 7,000 × $10 = $70 | **≈ $350** |
| 10×: 60,000 loads, 40,000 band views | 50,000 × $7 = $350 | 35,000 × $32 = $1,120 | 35,000 × $10 = $350 | **≈ $1,820** |
| 10× with ratings on (Enterprise) | $350 | 39,000 × $35 = $1,365 | $350 | **≈ $2,065** |

The quotas in Task G1 cap a month at roughly 5,000 loads + 2,000 + 2,000 calls **per day** — i.e. a worst-case month near $1,700 even under abuse; lower the daily quotas if that ceiling is too high.

## Red-team review (2026-09-05) — findings and dispositions

| # | Finding | Severity | Disposition |
|---|---|---|---|
| G-R1 | The browser key is public by construction; a copied key could run up the bill from another site. | High | Referrer restriction to the two hosts (+ localhost), API restriction to two APIs, per-day quotas, $50 budget alerts (G1). |
| G-R2 | A Leaflet import slipping back in violates §3.2.3(e) for the whole application. | High | ESLint `no-restricted-imports`; the bundle grep in G2 Step 4; `leaflet` removed from `package.json`. |
| G-R3 | The design's bottom-left controls overlap the Google logo; hiding the logo is prohibited. | High | Design reference updated (G6 Step 5); mask until then; the engine never sets CSS that touches `.gm-style` attribution nodes. |
| G-R4 | Pins could be counted client-side to "correct" the Census number. | Medium | Constraint + G5 wording; code review rule: no `places.length` reaches any metric or label other than the saturation note. |
| G-R5 | Practitioner duplicates and closed places would mislead members. | Medium | Filter + address merge + caveat (G3). |
| G-R6 | Quota exhaustion mid-session. | Medium | `reason: quota`, layer hides with a note, everything else unaffected (G3, G4); runbook (G7). |
| G-R7 | A member's map view sends their IP to Google; the privacy notice must say so. | Low | Add to the VIN Foundation privacy notice (open item). |
| G-R8 | Google can change prices or SKU tiers; the plan's figures date from 2026-09-05. | Low | Budget alerts; prices carried in this plan with their date; recheck before production launch. |
| G-R9 | Test determinism: real Google scripts are non-deterministic and cost money. | Medium | Deterministic stub for Vitest and Playwright (G2, G6); no live key in CI. |

## Open items for the VIN Foundation

- **G0** — map engine decision (this plan vs the approved Leaflet design).
- Ratings on pins (Enterprise tier, +9 % per call and a 1,000-call free allowance) — default off.
- Privacy notice: Google Maps loads and Places requests from members' browsers.
- Budget ceiling: $50/month alert and the daily quotas in G1 — raise or lower.
- Design reference update in Claude Design (G6 Step 5) — who and when.

## Self-review

- **Coverage:** engine (G2), pins (G3), live count (G4), registry/layers/no-mixing (G5), visual gate and design hand-off (G6), ops (G1, G7), plan deltas (G8), costs, red team. Nothing from the 2017 export is referenced anywhere.
- **Placeholders:** none — the only "look it up" instructions are deterministic greps (`grep -rl "from 'leaflet'" frontend/src`) and John's console steps, which carry exact names and values.
- **Type consistency:** `MapEngine` methods used in G3's composable match G2's interface; `searchVets` fields match the test's expected request; `visible_point`, `count_operational_async`, `BANDS`, `RATE_LIMIT`, `UPSTREAM_TIMEOUT_S`, `http_client` are defined in G4 and used only there; registry keys in G5 match `SPEC_KEYS` additions and the layer `dataset_key`s; `BAND_RADIUS_M` (frontend) equals `BANDS` (backend).
