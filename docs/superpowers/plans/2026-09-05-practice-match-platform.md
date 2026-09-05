# Practice Match Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Practice Match repo, Railway topology and domains, and ship the approved Claude Design as a pixel-faithful Vue app (fixture data) to `qa.foundation.vin` and `foundation.vin`, with an automated visual gate proving fidelity.

**Architecture:** One Docker image (Node builds `frontend/dist`, Python serves it + `/api/*`) deployed as Railway services `api` and `worker`, alongside `Postgres` (PostGIS) and `Redis`, in environments `QA` and `production`. The frontend is the handoff `vue-app/` verbatim plus a router sync layer around the untouched `logic.js`. A Playwright harness screenshots the reference `.dc.html` per screen state and asserts the Vue app matches.

**Tech Stack:** Vue 3.5 · Vite · vue-router 4 · TypeScript (new code only) · vitest · @playwright/test · leaflet 1.9.4 · Python 3.12 · Poetry 2.4.1 · FastAPI · SQLAlchemy 2 async + asyncpg · psycopg2-binary · Celery 5 + redis · pydantic-settings · pytest · Docker · Railway CLI ≥ 5.26

**Spec:** `docs/superpowers/specs/2026-09-05-practice-match-platform-design.md` (read §3–§6 before any task that touches those areas).

## Global Constraints

- **Quality and performance policy (`docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md`).** Test shape ~70/20/10 unit/integration/e2e enforced by rules; CI gates: `pytest -W error --cov-fail-under=90`, `diff-cover --fail-under=100`, `ruff`, `mypy --strict`, `vue-tsc --noEmit` (strict), vitest coverage ≥ 85 % on `src/map|router|admin`, Playwright fails on any `pageerror`/`console.error`, `gitleaks`; performance budgets are tests: API p95 (`/api/healthz` ≤ 20 ms, shell ≤ 15 ms, list endpoints ≤ 100 ms, panel ≤ 150 ms), bundle sizes (main ≤ 220 KB gz, `engine-leaflet` ≤ 60, `engine-google` ≤ 12, first load ≤ 300), first map paint ≤ 1,500 ms, hot queries use indexes, nightly k6 on QA (p95 ≤ 400 ms, 0 errors). Raising a budget is a reviewed change with a reason in the commit message.
- **TDD, no exceptions (John, 2026-09-05: "everything must have tests").** Every production change begins with a failing test that is run and watched fail (RED), then the minimal code, then the same test watched pass (GREEN) — the `Run:` lines in each task are mandatory steps, not illustrations. Documentation and configuration are covered by drift tests (`tests/test_docs.py`: every setting in `.env.example` and `DEPLOY.md`, relative links resolve, CI workflow shape, runbook endpoints exist); operational scripts have shell tests under `tests/scripts/` that run them against stubbed servers or a stubbed `curl`; ops steps end with an executable verification whose script is itself tested. The handoff's generated UI is covered by the visual gate (every screen state), the route smoke tests, the router-sync and engine unit tests and the `logic.js` characterisation suite (Platform Task 1c); new code in those files follows TDD.
- Ported files stay byte-identical except for the edits this plan names: `logic.js`, `dc-logic.js`, `lib/leaflet.js`, `components/*.vue`. No restyling, no inline-style extraction, no copy edits, no renames, no Pinia, no per-screen split. **`frontend/src/App.vue` is GENERATED** from the design template by `frontend/scripts/convert-dc.mjs` (Tasks 4a–4b; John's ruling 2026-09-05: full mechanical re-conversion) — never hand-edited; `tests/app-generated.test.ts` fails if it drifts. `directives/hover.js` is deleted: hover is generated as CSS pseudo-class rules exactly as the design runtime does. `components/ImageSlot.vue` is a parity port of the design's `image-slot` element (Task 4c).
- The only edits to ported files: (a) `assets/` → `/assets/`, `ds/` → `/ds/` path prefixes; (b) `lib/leaflet.js` loader body (npm import, same exported API); (c) `App.vue`'s former `<script setup>` lives in the hand-maintained `frontend/src/app.setup.js` — the router-sync install (two import lines + one call), the `prototypeBar` default from `import.meta.env`, the `v` merge and the `__s`/`__arr` helpers are its only additions; (d) map components: effect order mirrored from the JSX (Task 4e).
- `logic.js` is never edited except for the four `assets/photos/` path prefixes on lines 394–396 and 431.
- Route table (exact): `/`→`gate`; `/browse` + `?tab=listings|market` ↔ `browseMode`; `/practices/:id` ↔ `detailId`; `/requests`; `/seller`; `/admin` + `?tab=users|listings|activity|data` ↔ `adminTab`; unknown → `/`.
- Signed-out visitors never reach a member screen by URL: the router sync applies the prototype's `go()` semantics — the gate renders, the URL is kept, and the intended route is applied the moment `state.auth` becomes true.
- Every response carries `X-Robots-Tag: noindex, nofollow` and `/robots.txt` disallows all, unless `PUBLIC_INDEXING=true` (never set before launch).
- `commit_sha` in `/api/healthz` is the deployed git SHA: `scripts/deploy.sh` sets the `COMMIT_SHA` service variable from `git rev-parse --short HEAD` before each `railway up`; the Dockerfile declares `ARG COMMIT_SHA`.
- Visual tolerance: `maxDiffPixels: 0, threshold: 0.1`; ceiling if relaxed `maxDiffPixelRatio: 0.001`, recorded in `playwright.config.ts` with the reason.
- Basemap tile hosts (`**/*.arcgisonline.com/**`) are intercepted on both harness targets and answered with a blank 1×1 image (`route.fulfill`, not `route.abort()` — an aborted request makes Chromium emit its own `console.error`, which the error gate forbids). *Amended 2026-09-05 by John's ruling on Task 3 deviation D2.*
- Health body (exact keys): `status, version, environment, commit_sha, site_mode, db{ok, postgis_version|error}, redis{ok|error}` (`site_mode` added by Task 11b, spec 2026-09-06: `"app"` | `"coming_soon"`). `/api/healthz` is always 200; `/api/healthz/deep` is 503 when `db.ok` or `redis.ok` is false.
- `frontend/package.json` `version` == `pyproject.toml` `[project].version` (starts `0.1.0`).
- Fingerprinted build output goes to `dist/_app/` (Vite `build.assetsDir: '_app'`) so `/assets/*` (icons, photos, logo) is never served with immutable caching.
- Every commit: conventional message, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, pushed to both `origin` and `production`.
- Secrets never appear in git, chat, or `.env.example` values. `CENSUS_API_KEY` is set on `worker` out-of-band (John holds it).
- Before any `railway up`, variable change or service mutation: `railway status --json` must report project `Practice Match` — abort otherwise.
- Node 22 for builds (`nvm use 22`; `.nvmrc` = `22`). Python 3.12 (`poetry env use python3.12`).
- Work on branch `feat/platform` in a worktree; `main` receives the merge at the end.

## Source material

- Handoff bundle (extracted copy available at `/private/tmp/claude-502/-Users-johndean-Development-Practice-Match/39b87aac-a222-47b1-8bec-a538c22fdc1f/scratchpad/design/small/design_handoff_practice_match_v2`; canonical zip: `/Users/johndean/Downloads/VIN FOUNDATION/Claude Design zips/Vin Platform Marketplace Design.zip`). If the scratchpad copy is gone, `unzip` the zip into a temp dir; the bundle root is `design_handoff_practice_match_v2/`.
- Reference patterns to copy from: `/Users/johndean/Development/Rounds.vin/scripts/start.sh`, `.../Rounds.vin/.github/workflows/quality.yml`, `.../Rounds.vin/.gitleaks.toml`, `/Users/johndean/Development/Po.vin/CLAUDE.md`, `.../Po.vin/DEPLOY.md`, `.../Po.vin/.claude/skills/povin-workflow/SKILL.md`.

## File map

| Path | Responsibility |
|---|---|
| `docs/design-reference/design_handoff_practice_match_v2/` | Handoff bundle minus `vue-app/` — the visual oracle. Never edited, never shipped. |
| `frontend/` | The handoff `vue-app/` + additions below. |
| `frontend/src/main.ts` | Creates app, installs router, mounts. (Replaces `main.js`.) |
| `frontend/src/router/routes.ts` | Route records; all render `App`. |
| `frontend/src/router/sync.ts` | Pure: `stateToRoute`, `routeToPatch`, `needsPatch`, `sameLocation`. |
| `frontend/src/router/useStateRouteSync.ts` | Wires `sync.ts` to the reactive `Component` + router. |
| `frontend/src/env.d.ts` | `ImportMetaEnv` typing for `VITE_ENVIRONMENT`. |
| `frontend/tests/playwright.config.ts` | Two projects: `app`, `reference`; two web servers. |
| `frontend/tests/reference-server.mjs` | Static server for the reference bundle. |
| `frontend/tests/screens.ts` | The 25 screen states — one table, two targets. |
| `frontend/tests/harness.ts` | Shared: tile blocking, settle, jump helpers. |
| `frontend/tests/reference-baselines.spec.ts` | Writes baselines from the reference. |
| `frontend/tests/visual.spec.ts` | Asserts the app against baselines. |
| `frontend/tests/smoke.spec.ts` | Routes render, no console errors, deep link → gate → state. |
| `frontend/src/**/*.test.ts` | vitest unit tests (paths lint, leaflet adapter, sync). |
| `app/config.py` | pydantic-settings; fail-fast at import. |
| `app/version.py` | Reads version from `pyproject.toml`. |
| `app/checks.py` | `check_db(url)`, `check_redis(url)` → dicts. |
| `app/api/health.py` | `/api/healthz`, `/api/healthz/deep`, `/api/{path}` 404. |
| `app/static.py` | SPA serving: `/_app` immutable, files, `index.html` fallback. |
| `app/main.py` | App factory + wiring. |
| `app/tasks/celery_app.py` | Celery instance + `ping`. |
| `migrations/001_init.sql` | `CREATE EXTENSION IF NOT EXISTS postgis;` |
| `scripts/migrate.py` | Ledger runner (`run(dsn) -> list[str]`, CLI `main()`). |
| `scripts/start.sh` | Role dispatch `api|worker|migrate`. |
| `scripts/deploy.sh`, `scripts/verify-deploy.sh` | Guarded deploy + post-deploy probes. |
| `tests/` | pytest (`conftest.py`, `test_config.py`, `test_health.py`, `test_static.py`, `test_migrate.py`, `test_celery.py`, `test_versions.py`), `tests/scripts/test_deploy_guard.sh`. |
| `Dockerfile`, `.dockerignore`, `railway.json`, `.railwayignore`, `docker-compose.dev.yml` | Build/deploy. |
| `.github/workflows/quality.yml`, `.gitleaks.toml` | CI. |
| `CLAUDE.md`, `DEPLOY.md`, `README.md`, `.env.example`, `.nvmrc`, `.claude/skills/practice-match-workflow/SKILL.md` | Working docs. |

---

### Task 1: Frontend builds — handoff import, asset paths, vendored Leaflet, DS cascade

**Files:**
- Create: `docs/design-reference/design_handoff_practice_match_v2/**` (copy), `frontend/**` (copy of `vue-app/`), `frontend/src/paths.test.ts`, `frontend/src/lib/leaflet.test.ts`, `frontend/tsconfig.json`, `frontend/src/env.d.ts`, `frontend/public/ds/preview/_preview.css`, `frontend/public/ds/ui_kits/vin/kit.css`, `.nvmrc`
- Modify: `frontend/src/App.vue` (path prefixes only), `frontend/src/components/*.vue` (path prefixes only), `frontend/src/logic.js:394-396,431`, `frontend/src/lib/leaflet.js:5-32`, `frontend/index.html`, `frontend/vite.config.js` → `frontend/vite.config.ts`, `frontend/package.json`

**Interfaces:**
- Produces: `loadLeaflet(): Promise<typeof L>` (unchanged signature, now resolves the bundled module); `BASEMAPS`, `LABEL_TILES`, `pill`, `clusterIcon`, `clusterize`, `pricePin`, `dot` unchanged.

- [ ] **Step 1: Copy the bundle and the app**

```bash
cd "/Users/johndean/Development/Practice Match"
B="/private/tmp/claude-502/-Users-johndean-Development-Practice-Match/39b87aac-a222-47b1-8bec-a538c22fdc1f/scratchpad/design/small/design_handoff_practice_match_v2"
mkdir -p docs/design-reference
rsync -a --exclude vue-app "$B/" docs/design-reference/design_handoff_practice_match_v2/
rsync -a "$B/vue-app/" frontend/
cp "$B/_ds/vin-design-system-019dcfa0-cc54-758a-91dc-85ded39fc8af/preview/_preview.css" frontend/public/ds/preview/_preview.css 2>/dev/null || { mkdir -p frontend/public/ds/preview frontend/public/ds/ui_kits/vin; cp "$B/_ds/vin-design-system-019dcfa0-cc54-758a-91dc-85ded39fc8af/preview/_preview.css" frontend/public/ds/preview/; }
cp "$B/_ds/vin-design-system-019dcfa0-cc54-758a-91dc-85ded39fc8af/ui_kits/vin/kit.css" frontend/public/ds/ui_kits/vin/kit.css
echo 22 > .nvmrc
ls frontend/src docs/design-reference/design_handoff_practice_match_v2
```
Expected: `frontend/src` has `App.vue logic.js dc-logic.js main.js components directives lib styles`; the reference dir has `Practice Match V2.dc.html support.js image-slot.js _ds assets AustinMap.jsx MarketMap.jsx README.md`.

- [ ] **Step 2: Install toolchain and test deps**

```bash
cd frontend && source ~/.nvm/nvm.sh && nvm use 22
npm install
npm install -D typescript vue-tsc vitest jsdom @types/node
npm install leaflet vue-router
npm install -D @types/leaflet
```

- [ ] **Step 3: Write the failing paths test**

`frontend/src/paths.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

describe('asset references', () => {
  it('uses absolute /assets and /ds paths only (Vite serves public/ at the root)', () => {
    const files = walk(import.meta.dirname).filter((f) => /\.(vue|js|ts)$/.test(f) && !f.endsWith('.test.ts'));
    const offenders: string[] = [];
    for (const f of files) {
      const src = readFileSync(f, 'utf8');
      const re = /["'(](assets|ds)\//g;
      let m: RegExpExecArray | null;
      while ((m = re.exec(src))) offenders.push(`${f}:${src.slice(0, m.index).split('\n').length}`);
    }
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 4: Run it — expect RED with 33 offenders**

Run: `npx vitest run src/paths.test.ts`
Expected: FAIL; the printed array lists 29 `App.vue`/component lines and 4 `logic.js` lines (394, 395, 396, 431).

- [ ] **Step 5: Fix the paths (prefix only)**

```bash
cd frontend/src
sed -i '' -E 's#(src|href)="(assets|ds)/#\1="/\2/#g' App.vue components/*.vue
sed -i '' -E 's#"assets/photos/#"/assets/photos/#g' logic.js
grep -c '"/assets/photos/' logic.js   # expect 4
```

- [ ] **Step 6: Run the paths test — expect GREEN**

Run: `npx vitest run src/paths.test.ts` → PASS.

- [ ] **Step 7: Write the failing Leaflet adapter test**

`frontend/src/lib/leaflet.test.ts`:
```ts
// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { loadLeaflet, BASEMAPS, LABEL_TILES } from './leaflet.js';

describe('loadLeaflet', () => {
  it('resolves the bundled Leaflet without injecting CDN tags', async () => {
    const L = await loadLeaflet();
    expect(typeof L.map).toBe('function');
    expect(L.version).toBe('1.9.4');
    expect(document.querySelectorAll('script[src*="unpkg.com"], link[href*="unpkg.com"]').length).toBe(0);
  });
  it('keeps the approved Esri basemap configuration', () => {
    expect(BASEMAPS.map.url).toContain('World_Light_Gray_Base');
    expect(BASEMAPS.map.attribution).toBe('Tiles © Esri');
    expect(BASEMAPS.satellite.attribution).toBe('Imagery © Esri, Maxar, Earthstar Geographics');
    expect(LABEL_TILES).toContain('World_Light_Gray_Reference');
  });
});
```

- [ ] **Step 8: Run it — expect RED**

Run: `npx vitest run src/lib/leaflet.test.ts`
Expected: FAIL — the promise never resolves under jsdom (no network) → test timeout, or `unpkg.com` tags found.

- [ ] **Step 9: Replace the loader body (lines 5–32 of `lib/leaflet.js`) — everything below line 33 stays byte-identical**

```js
// Leaflet is bundled from npm (same 1.9.4 the prototype loaded from unpkg) so
// production has no third-party runtime script dependency. Same exported API.
import * as Leaflet from "leaflet";
import "leaflet/dist/leaflet.css";

export function loadLeaflet() {
  if (!window.L) window.L = Leaflet;
  return Promise.resolve(window.L);
}
```
Keep the comment block on lines 1–3, then this, then the unchanged `// Esri basemaps…` section onward.

- [ ] **Step 10: Run the Leaflet test — expect GREEN**

Run: `npx vitest run src/lib/leaflet.test.ts` → PASS (2 tests).

- [ ] **Step 11: DS cascade + Vite config + TypeScript config**

`frontend/index.html` — replace the single `<link rel="stylesheet" href="/ds/colors_and_type.css" />` with the reference's three, same order:
```html
  <link rel="stylesheet" href="/ds/colors_and_type.css" />
  <link rel="stylesheet" href="/ds/preview/_preview.css" />
  <link rel="stylesheet" href="/ds/ui_kits/vin/kit.css" />
```

`frontend/vite.config.ts` (delete `vite.config.js`):
```ts
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  build: { assetsDir: '_app' },
  server: { port: 5173, strictPort: true },
  test: { include: ['src/**/*.test.ts'] }
});
```

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022", "module": "ESNext", "moduleResolution": "Bundler",
    "strict": true, "noEmit": true, "allowJs": true, "checkJs": false,
    "jsx": "preserve", "skipLibCheck": true, "types": ["vite/client", "node"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "src/**/*.js", "tests/**/*.ts"]
}
```

`frontend/src/env.d.ts`:
```ts
/// <reference types="vite/client" />
interface ImportMetaEnv { readonly VITE_ENVIRONMENT?: 'qa' | 'production' | 'test' }
interface ImportMeta { readonly env: ImportMetaEnv }
```

`frontend/package.json` scripts (replace the `scripts` block; keep `"name": "practice-match"`, `"version": "0.1.0"`, `"private": true`, `"type": "module"`):
```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "preview": "vite preview",
  "typecheck": "vue-tsc --noEmit -p tsconfig.json",
  "test": "vitest run",
  "test:e2e": "playwright test --config=tests/playwright.config.ts --project=app",
  "test:smoke": "playwright test --config=tests/playwright.config.ts --project=app smoke.spec.ts",
  "test:visual": "playwright test --config=tests/playwright.config.ts --project=app visual.spec.ts",
  "test:visual:baselines": "playwright test --config=tests/playwright.config.ts --project=reference"
}
```

- [ ] **Step 12: Build and typecheck**

Run: `npm run build && npm run typecheck`
Expected: `vite build` succeeds, output under `dist/_app/*` plus `dist/assets/`, `dist/ds/`; `vue-tsc` exits 0. If `vue-tsc` reports errors inside the ported `.vue`/`.js` files, add `// @ts-nocheck` is NOT allowed — instead set `"checkJs": false` (already) and confirm the error is in a `.ts` file you wrote.

**Performance gate (policy §3):** add `frontend/tests/bundle-budget.test.ts` from `docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md` §5 (RED before `npm run build` — `ENOENT dist/_app`; GREEN after: main bundle ≤ 220 KB gz). Add `tests/**/*.test.ts` to the vitest `include`.

- [ ] **Step 13: Commit**

```bash
cd "/Users/johndean/Development/Practice Match"
git add -A
git commit -m "feat(frontend): import approved handoff, absolute asset paths, bundled Leaflet, DS cascade

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push origin feat/platform && git push production feat/platform
```

---

### Task 1b: `MapEngine` interface and `LeafletMapEngine` — the Map-engines spec §11.1 amendment (pixels unchanged)

The two Leaflet components stop calling Leaflet directly and call one `MapEngine` interface; the only implementation in SP1 is `LeafletMapEngine`, which passes the handoff's exact options through. The marker-HTML builders move out of `lib/leaflet.js` (which imports Leaflet) so that nothing outside `src/map/engines/` and `src/lib/leaflet.js` depends on Leaflet — the Map-engines sub-project adds `GoogleMapEngine` behind the same interface. No pixel changes: Task 4's visual gate is the proof.

**Files:**
- Create: `frontend/src/map/engine.ts`, `frontend/src/map/markers.js`, `frontend/src/map/engines/leaflet.ts`, `frontend/src/map/create.ts`, `frontend/src/map/testing/leaflet-stub.ts`, `frontend/src/map/engines/leaflet.test.ts`, `frontend/src/map/markers.test.ts`, `frontend/src/map/boundary.test.ts`
- Modify: `frontend/src/lib/leaflet.js` (delete the five HTML builders `pill`, `clusterIcon`, `clusterize`, `pricePin`, `dot` — they move byte-identical to `markers.js`; keep `loadLeaflet`, `BASEMAPS`, `LABEL_TILES`), `frontend/src/components/MarketMapView.vue` (`<script setup>` and the three control buttons), `frontend/src/components/ListingsMap.vue` (`<script setup>`)

**Interfaces:**
- Consumes: `loadLeaflet()`, `BASEMAPS`, `LABEL_TILES` from `lib/leaflet.js` (Task 1).
- Produces (used unchanged by the Map-engines plan): `LatLng = [number, number]` (lat, lng — the handoff's convention); `BaseKind = 'map' | 'satellite'` (the handoff's `basemap` prop values); `MountOptions { center: LatLng; zoom: number; basemap: BaseKind; zoomControl?: 'bottomright' | false; scaleControl?: boolean; groups?: string[] }`; `CircleStyle { fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }`; `MarkerOptions { html: string; size: [number, number]; anchor: [number, number]; tooltip?: string; zIndexOffset?: number; interactive?: boolean; onClick?: () => void }`; `Handle { remove(): void }`; `MapEngine { readonly name: 'leaflet' | 'google'; mount(el, opts): Promise<void>; show(): void; setControls(opts): void; setView(center, zoom, animate?: boolean): void; getZoom(): number; zoomIn(): void; zoomOut(): void; fitBounds(points: LatLng[]): void; setBase(kind): void; circle(center, radiusM, style, group): Handle; marker(pos, opts, group): Handle; clear(group): void; onMove(cb: (center: LatLng, zoom: number) => void): () => void; destroy(): void }`; `LeafletMapEngine`; `createEngine(): Promise<MapEngine>`; `installLeafletStub(): LeafletStub` (tests); `pill`, `clusterIcon`, `clusterize`, `pricePin`, `dot` from `markers.js`.

- [ ] **Step 1: Failing tests**

`frontend/src/map/boundary.test.ts` — the import boundary (this project has no ESLint; the test is the rule):
```ts
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const SRC = join(import.meta.dirname, '..');
const ALLOWED = [/^map\/engines\//, /^lib\/leaflet\.js$/, /^map\/testing\//];
function walk(d: string): string[] { return readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : [p]; }); }

describe('map engine import boundary (Map-engines spec §2.2)', () => {
  it('only src/map/engines/* and src/lib/leaflet.js touch Leaflet or window.L', () => {
    const offenders = walk(SRC).filter((f) => /\.(vue|js|ts)$/.test(f) && !f.endsWith('.test.ts')).filter((f) => {
      const rel = relative(SRC, f);
      if (ALLOWED.some((re) => re.test(rel))) return false;
      const s = readFileSync(f, 'utf8');
      return /from\s+['"]leaflet|require\(['"]leaflet|window\.L\b|\bL\.(map|tileLayer|marker|divIcon|circle|layerGroup|control)\(/.test(s);
    }).map((f) => relative(SRC, f));
    expect(offenders).toEqual([]);
  });
});
```

`frontend/src/map/markers.test.ts` — the builders moved byte-identical:
```ts
import { describe, expect, it } from 'vitest';
import { clusterIcon, clusterize, dot, pill, pricePin } from './markers.js';

describe('marker HTML builders (moved from lib/leaflet.js)', () => {
  it('dot', () => {
    expect(dot(20, '#003a70')).toBe('<div style="width:20px;height:20px;border-radius:999px;background:#003a70;border:2px solid rgba(255,255,255,.85);box-sizing:border-box;"></div>');
    expect(dot(10, 'rgba(120,86,190,.75)', 'rgba(255,255,255,.9)')).toContain('border:2px solid rgba(255,255,255,.9)');
  });
  it('pricePin active/inactive', () => {
    expect(pricePin('$1.45M', true)).toContain('background:var(--vf-navy);color:var(--vf-white);');
    expect(pricePin('$1.45M', false)).toContain('border:1px solid #d4dde5;');
  });
  it('pill muted/active', () => {
    expect(pill('$860K', false, true)).toContain('background:var(--color-steel);color:var(--color-white);');
    expect(pill('$860K', true, false)).toContain('transform:translateY(-2px)');
  });
  it('clusterIcon and clusterize', () => {
    expect(clusterIcon(3)).toContain('>3</div>');
    const ms = [{ id: 'a', lat: 30.30, lng: -97.70 }, { id: 'b', lat: 30.31, lng: -97.71 }, { id: 'c', lat: 31.9, lng: -99.0 }];
    expect(clusterize(ms, 10).map((e) => e.kind)).toEqual(['pin', 'pin', 'pin']);
    const z8 = clusterize(ms, 8);
    expect(z8.find((e) => e.kind === 'cluster')?.ids).toEqual(['a', 'b']);
  });
});
```

`frontend/src/map/testing/leaflet-stub.ts` — a recording stand-in installed as `window.L` (`loadLeaflet()` returns `window.L` when present):
```ts
export interface Call { fn: string; args: unknown[] }
export interface LeafletStub { calls: Call[]; map: FakeMap; tiles: FakeTile[]; L: unknown }

class FakeLayer { added: unknown[] = []; on(ev: string, cb: () => void) { (this as any)['on_' + ev] = cb; return this; } addTo(g: any) { g.added?.push(this); (this as any).parent = g; return this; } remove() { const p = (this as any).parent; if (p?.added) p.added = p.added.filter((x: unknown) => x !== this); } bindTooltip(text: string, opts: unknown) { (this as any).tooltip = { text, opts }; return this; } }
export class FakeTile extends FakeLayer { url: string; options: Record<string, unknown>; constructor(url: string, options: Record<string, unknown>) { super(); this.url = url; this.options = options; } setUrl(u: string) { this.url = u; } }
class FakeGroup extends FakeLayer { clearLayers() { this.added = []; } }
export class FakeMap { added: unknown[] = []; handlers: Record<string, () => void> = {}; center: unknown; zoom: number; invalidated = 0; attributionControl = { _update: () => { (this as any).attrUpdated = ((this as any).attrUpdated ?? 0) + 1; } };
  constructor(public el: HTMLElement, public opts: any) { this.center = opts.center; this.zoom = opts.zoom; el.dataset.leafletMounted = '1'; }
  setView(c: unknown, z: number, o?: unknown) { this.center = c; this.zoom = z; (this as any).lastSetView = [c, z, o]; }
  getZoom() { return this.zoom; } getCenter() { const c = this.center as [number, number]; return { lat: c[0], lng: c[1] }; }
  zoomIn() { this.zoom += 1; } zoomOut() { this.zoom -= 1; } invalidateSize() { this.invalidated += 1; }
  on(ev: string, cb: () => void) { ev.split(' ').forEach((e) => { this.handlers[e] = cb; }); } off(ev: string) { ev.split(' ').forEach((e) => { delete this.handlers[e]; }); }
  removeLayer(l: unknown) { this.added = this.added.filter((x) => x !== l); } remove() { (this as any).removed = true; } fitBounds(b: unknown, o?: unknown) { (this as any).fitted = [b, o]; } }

export function installLeafletStub(): LeafletStub {
  const calls: Call[] = []; const tiles: FakeTile[] = []; let map: FakeMap;
  const rec = (fn: string, ret: (...a: any[]) => unknown) => (...args: unknown[]) => { calls.push({ fn, args }); return ret(...args); };
  const L = {
    map: rec('map', (el: HTMLElement, opts: unknown) => (map = new FakeMap(el, opts))),
    tileLayer: rec('tileLayer', (url: string, options: Record<string, unknown>) => { const t = new FakeTile(url, options); tiles.push(t); return t; }),
    layerGroup: rec('layerGroup', () => new FakeGroup()),
    circle: rec('circle', (center: unknown, options: unknown) => Object.assign(new FakeLayer(), { center, options })),
    divIcon: rec('divIcon', (o: unknown) => ({ icon: o })),
    marker: rec('marker', (pos: unknown, options: unknown) => Object.assign(new FakeLayer(), { pos, options })),
    control: { zoom: rec('control.zoom', (o: unknown) => Object.assign(new FakeLayer(), { control: 'zoom', o })), scale: rec('control.scale', (o: unknown) => Object.assign(new FakeLayer(), { control: 'scale', o })) },
    latLngBounds: rec('latLngBounds', (pts: unknown) => ({ pts })),
  };
  (window as any).L = L;
  return { calls, get map() { return map; }, tiles, L };
}
```

`frontend/src/map/engines/leaflet.test.ts` — the engine passes the handoff's exact options:
```ts
// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LeafletMapEngine } from './leaflet';
import { installLeafletStub } from '../testing/leaflet-stub';
import { BASEMAPS, LABEL_TILES } from '../../lib/leaflet.js';

afterEach(() => { vi.useRealTimers(); delete (window as any).L; });

async function mounted(opts: Partial<Parameters<LeafletMapEngine['mount']>[1]> = {}) {
  vi.useFakeTimers();
  const stub = installLeafletStub(); const el = document.createElement('div');
  const engine = new LeafletMapEngine();
  await engine.mount(el, { center: [30.31, -97.75], zoom: 10, basemap: 'map', zoomControl: false, scaleControl: true, groups: ['overlay', 'pins'], ...opts });
  return { stub, el, engine };
}

describe('LeafletMapEngine — MarketMapView shape', () => {
  it('creates the map, tiles, labels, scale control and groups exactly as the handoff did', async () => {
    const { stub, el } = await mounted();
    expect(stub.calls[0]).toEqual({ fn: 'map', args: [el, { center: [30.31, -97.75], zoom: 10, zoomControl: false, attributionControl: true }] });
    expect(stub.tiles[0].url).toBe(BASEMAPS.map.url); expect(stub.tiles[0].options).toEqual({ attribution: BASEMAPS.map.attribution, maxZoom: 18 });
    expect(stub.tiles[1].url).toBe(LABEL_TILES); expect(stub.tiles[1].options).toEqual({ maxZoom: 18, pane: 'shadowPane' });
    expect(stub.map.added).toContain(stub.tiles[1]);                       // labels shown on the gray canvas
    expect(stub.calls.find((c) => c.fn === 'control.scale')?.args).toEqual([{ imperial: true, metric: false, position: 'bottomright' }]);
    expect(stub.calls.filter((c) => c.fn === 'control.zoom')).toHaveLength(0);
    expect(stub.calls.filter((c) => c.fn === 'layerGroup')).toHaveLength(2);   // overlay then pins, created at mount in order
    expect(el.dataset.map).toBe('leaflet');
    vi.advanceTimersByTime(60); expect(stub.map.invalidated).toBe(1);
  });
  it('circle and marker pass the exact options; tooltip uses the design placement; clear empties the group', async () => {
    const { stub, engine } = await mounted();
    engine.circle([30.3, -97.7], 16000, { fillColor: '#339dde', fillOpacity: 0.16 }, 'overlay');
    expect(stub.calls.find((c) => c.fn === 'circle')?.args).toEqual([[30.3, -97.7], { radius: 16000, stroke: false, fillColor: '#339dde', fillOpacity: 0.16, interactive: false }]);
    const onClick = () => {};
    engine.marker([30.5, -97.8], { html: '<div>x</div>', size: [72, 26], anchor: [36, 13], zIndexOffset: 1000, onClick }, 'pins');
    expect(stub.calls.find((c) => c.fn === 'divIcon')?.args).toEqual([{ html: '<div>x</div>', className: '', iconSize: [72, 26], iconAnchor: [36, 13] }]);
    const m = stub.calls.find((c) => c.fn === 'marker')!;
    expect(m.args[0]).toEqual([30.5, -97.8]); expect((m.args[1] as any).zIndexOffset).toBe(1000); expect((m.args[1] as any).interactive).toBe(true);
    engine.marker([30.5, -97.8], { html: '<div>d</div>', size: [20, 20], anchor: [10, 10], tooltip: 'Cedar Park — $118K', interactive: true }, 'overlay');
    const marked = stub.calls.filter((c) => c.fn === 'marker'); expect(marked).toHaveLength(2);
    const groups = stub.calls.filter((c) => c.fn === 'layerGroup').length; expect(groups).toBe(2);
    const overlayGroup = (stub.map.added as any[]).find((g) => g.clearLayers && g.added.some((l: any) => l.tooltip));
    expect(overlayGroup.added[1].tooltip).toEqual({ text: 'Cedar Park — $118K', opts: { direction: 'top', offset: [0, -6] } });
    engine.clear('overlay'); expect(overlayGroup.added).toEqual([]);
  });
  it('setBase swaps the tile URL, toggles labels and refreshes attribution; setView animates when asked; show() invalidates after 80 ms', async () => {
    const { stub, engine } = await mounted();
    engine.setBase('satellite');
    expect(stub.tiles[0].url).toBe(BASEMAPS.satellite.url); expect(stub.map.added).not.toContain(stub.tiles[1]); expect((stub.map as any).attrUpdated).toBe(1);
    engine.setBase('map'); expect(stub.map.added).toContain(stub.tiles[1]);
    engine.setView([30.5, -97.8], 12, true); expect((stub.map as any).lastSetView).toEqual([[30.5, -97.8], 12, { animate: true }]);
    engine.setView([30.5, -97.8], 13); expect((stub.map as any).lastSetView).toEqual([[30.5, -97.8], 13, undefined]);
    engine.show(); vi.advanceTimersByTime(80); expect(stub.map.invalidated).toBe(2);
    let seen = 0; const off = engine.onMove((_c, z) => { seen = z; }); stub.map.zoom = 11; stub.map.handlers.zoomend(); expect(seen).toBe(11); off(); expect(stub.map.handlers.zoomend).toBeUndefined();
    engine.destroy(); expect((stub.map as any).removed).toBe(true);
  });
});

describe('LeafletMapEngine — ListingsMap shape', () => {
  it('adds the bottom-right zoom control and no scale control', async () => {
    const { stub } = await mounted({ zoomControl: 'bottomright', scaleControl: false, groups: ['layer'] });
    expect(stub.calls.find((c) => c.fn === 'control.zoom')?.args).toEqual([{ position: 'bottomright' }]);
    expect(stub.calls.filter((c) => c.fn === 'control.scale')).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/map` → FAIL (`Cannot find module './markers.js'`, `'./leaflet'`); `boundary.test.ts` FAILS listing `components/MarketMapView.vue` and `components/ListingsMap.vue`.

- [ ] **Step 3: Implement**

`frontend/src/map/markers.js`: cut the five functions `pill`, `clusterIcon`, `clusterize`, `pricePin`, `dot` out of `lib/leaflet.js` verbatim (from the `export function pill` line to the end of `dot`) and paste them here with the header comment `// Marker HTML builders, ported verbatim from the approved prototype. Inline styles are intentional: divIcons live outside the app stylesheet scope.`

`frontend/src/map/engine.ts`:
```ts
export type LatLng = [number, number];
export type BaseKind = 'map' | 'satellite';
export interface MountOptions { center: LatLng; zoom: number; basemap: BaseKind; zoomControl?: 'bottomright' | false; scaleControl?: boolean; groups?: string[] }
export interface CircleStyle { fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }
export interface MarkerOptions { html: string; size: [number, number]; anchor: [number, number]; tooltip?: string; zIndexOffset?: number; interactive?: boolean; onClick?: () => void }
export interface Handle { remove(): void }

/** The only map API the components use — exactly the surface the handoff's two Leaflet components call. */
export interface MapEngine {
  readonly name: 'leaflet' | 'google';
  mount(el: HTMLElement, opts: MountOptions): Promise<void>;
  show(): void;
  setControls(opts: Pick<MountOptions, 'zoomControl' | 'scaleControl'>): void;
  setView(center: LatLng, zoom: number, animate?: boolean): void;
  getZoom(): number;
  zoomIn(): void;
  zoomOut(): void;
  fitBounds(points: LatLng[]): void;
  setBase(kind: BaseKind): void;
  circle(center: LatLng, radiusM: number, style: CircleStyle, group: string): Handle;
  marker(pos: LatLng, opts: MarkerOptions, group: string): Handle;
  clear(group: string): void;
  onMove(cb: (center: LatLng, zoom: number) => void): () => void;
  destroy(): void;
}
```

`frontend/src/map/engines/leaflet.ts`:
```ts
import type { BaseKind, CircleStyle, Handle, LatLng, MapEngine, MarkerOptions, MountOptions } from '../engine';
import { BASEMAPS, LABEL_TILES, loadLeaflet } from '../../lib/leaflet.js';

/** Leaflet 1.9.4 behind MapEngine. Every option below is the handoff's, unchanged — Task 4's visual gate proves it. */
export class LeafletMapEngine implements MapEngine {
  readonly name = 'leaflet' as const;
  private L!: any; private map!: any; private tile!: any; private labels!: any;
  private zoomCtl: any = null; private scaleCtl: any = null;
  private readonly groups = new Map<string, any>();

  async mount(el: HTMLElement, opts: MountOptions): Promise<void> {
    const L = await loadLeaflet(); this.L = L;
    this.map = L.map(el, { center: opts.center, zoom: opts.zoom, zoomControl: false, attributionControl: true });
    const cfg = BASEMAPS[opts.basemap] || BASEMAPS.map;
    this.tile = L.tileLayer(cfg.url, { attribution: cfg.attribution, maxZoom: 18 }).addTo(this.map);
    // The gray canvas carries almost no labels — Esri's matching reference layer supplies them.
    this.labels = L.tileLayer(LABEL_TILES, { maxZoom: 18, pane: 'shadowPane' });
    if (opts.basemap === 'map') this.labels.addTo(this.map);
    for (const g of opts.groups ?? []) this.group(g);
    this.setControls(opts);
    el.dataset.map = 'leaflet';
    setTimeout(() => this.map.invalidateSize(), 60);
  }
  show(): void { setTimeout(() => this.map.invalidateSize(), 80); }
  setControls(opts: Pick<MountOptions, 'zoomControl' | 'scaleControl'>): void {
    if (opts.zoomControl && !this.zoomCtl) this.zoomCtl = this.L.control.zoom({ position: opts.zoomControl }).addTo(this.map);
    if (!opts.zoomControl && this.zoomCtl) { this.zoomCtl.remove(); this.zoomCtl = null; }
    if (opts.scaleControl && !this.scaleCtl) this.scaleCtl = this.L.control.scale({ imperial: true, metric: false, position: 'bottomright' }).addTo(this.map);
    if (!opts.scaleControl && this.scaleCtl) { this.scaleCtl.remove(); this.scaleCtl = null; }
  }
  setView(center: LatLng, zoom: number, animate?: boolean): void { this.map.setView(center, zoom, animate === undefined ? undefined : { animate }); }
  getZoom(): number { return this.map.getZoom(); }
  zoomIn(): void { this.map.zoomIn(); }
  zoomOut(): void { this.map.zoomOut(); }
  fitBounds(points: LatLng[]): void { this.map.fitBounds(this.L.latLngBounds(points), { padding: [24, 24] }); }
  setBase(kind: BaseKind): void {
    const cfg = BASEMAPS[kind] || BASEMAPS.map;
    this.tile.setUrl(cfg.url);
    if (kind === 'map') this.labels.addTo(this.map); else this.map.removeLayer(this.labels);
    this.tile.options.attribution = cfg.attribution;
    if (this.map.attributionControl._update) this.map.attributionControl._update();
  }
  circle(center: LatLng, radiusM: number, s: CircleStyle, group: string): Handle {
    const c = this.L.circle(center, { radius: radiusM, stroke: s.stroke ?? false, fillColor: s.fillColor, fillOpacity: s.fillOpacity, interactive: s.interactive ?? false }).addTo(this.group(group));
    return { remove: () => c.remove() };
  }
  marker(pos: LatLng, o: MarkerOptions, group: string): Handle {
    const icon = this.L.divIcon({ html: o.html, className: '', iconSize: o.size, iconAnchor: o.anchor });
    const m = this.L.marker(pos, { icon, zIndexOffset: o.zIndexOffset ?? 0, interactive: o.interactive ?? true });
    if (o.tooltip) m.bindTooltip(o.tooltip, { direction: 'top', offset: [0, -6] });
    if (o.onClick) m.on('click', o.onClick);
    m.addTo(this.group(group));
    return { remove: () => m.remove() };
  }
  clear(group: string): void { this.groups.get(group)?.clearLayers(); }
  onMove(cb: (center: LatLng, zoom: number) => void): () => void {
    const h = () => { const c = this.map.getCenter(); cb([c.lat, c.lng], this.map.getZoom()); };
    this.map.on('moveend zoomend', h);
    return () => this.map.off('moveend zoomend', h);
  }
  destroy(): void { this.map.remove(); }
  private group(name: string) { let g = this.groups.get(name); if (!g) { g = this.L.layerGroup().addTo(this.map); this.groups.set(name, g); } return g; }
}
```

`frontend/src/map/create.ts` (SP1 version; the Map-engines plan makes it config-driven):
```ts
import type { MapEngine } from './engine';
export async function createEngine(): Promise<MapEngine> {
  const { LeafletMapEngine } = await import('./engines/leaflet');
  return new LeafletMapEngine();
}
```

`frontend/src/components/MarketMapView.vue` — template: the three buttons become `@click="engine && engine.zoomIn()"`, `@click="engine && engine.zoomOut()"`, `@click="engine && engine.setView(props.center, props.zoom)"`. Replace the whole `<script setup>` with:
```js
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { dot, pricePin } from '../map/markers.js';
import { createEngine } from '../map/create';

const props = defineProps({
  practices: { type: Array, default: () => [] }, communities: { type: Array, default: () => [] }, layers: { type: Object, default: () => ({}) },
  valueLayer: { type: String, default: null }, basemap: { type: String, default: 'map' }, activeId: { type: String, default: null },
  onSelect: { type: Function, default: null }, center: { type: Array, default: () => [30.31, -97.75] }, zoom: { type: Number, default: 10 },
  driveCenter: { type: Array, default: null }, resizeKey: { type: String, default: '' }
});
const host = ref(null);
const status = ref('loading');
let engine = null;
const ctrlBtn = 'width: 32px; height: 32px; display: grid; place-items: center; background: none; border: 0; border-radius: 999px; cursor: pointer; padding: 0; filter: drop-shadow(0 1px 3px rgba(0,58,112,.3));';
const ctrlIcon = 'display: block; opacity: .85;';

onMounted(async () => {
  try {
    const e = await createEngine();
    if (!host.value || engine) return;
    await e.mount(host.value, { center: props.center, zoom: props.zoom, basemap: props.basemap, zoomControl: false, scaleControl: true, groups: ['overlay', 'pins'] });
    engine = e;
    status.value = 'ready';
    drawOverlay();
    drawPins();
  } catch { status.value = 'error'; }
});
onBeforeUnmount(() => { if (engine) { engine.destroy(); engine = null; } });

watch([() => props.basemap, status], () => { if (engine) engine.setBase(props.basemap); });
watch([() => props.center && props.center[0], () => props.center && props.center[1], () => props.zoom, status], () => { if (engine && props.center) engine.setView(props.center, props.zoom, true); });
watch(() => props.resizeKey, () => { if (engine) engine.show(); });

// Drive-time rings + community data bubbles
function drawOverlay() {
  if (!engine) return;
  engine.clear('overlay');
  const hub = props.driveCenter || props.center;
  if (props.layers.drive10 && hub) engine.circle(hub, 16000, { fillColor: '#339dde', fillOpacity: 0.16 }, 'overlay');
  if (props.layers.drive5 && hub) engine.circle(hub, 8000, { fillColor: '#003a70', fillOpacity: 0.2 }, 'overlay');
  if (props.valueLayer) {
    props.communities.forEach((c) => {
      const v = c.values[props.valueLayer];
      if (v == null) return;
      const size = 16 + Math.round(v.t * 30);
      engine.marker([c.lat, c.lng], { html: dot(size, v.color), size: [size, size], anchor: [size / 2, size / 2], tooltip: c.name + ' — ' + v.label, interactive: true }, 'overlay');
    });
  }
  if (props.layers.competition) {
    props.communities.forEach((c) => {
      const n = c.vets || 0;
      if (!n) return;
      const size = 8 + Math.min(n, 14);
      engine.marker([c.lat + 0.012, c.lng + 0.012], { html: dot(size, 'rgba(120,86,190,.75)', 'rgba(255,255,255,.9)'), size: [size, size], anchor: [size / 2, size / 2], tooltip: c.name + ' — ' + n + ' veterinary establishments', interactive: true }, 'overlay');
    });
  }
}

// Practice price pins
function drawPins() {
  if (!engine) return;
  engine.clear('pins');
  if (!props.layers.practices) return;
  props.practices.forEach((p) => {
    const active = p.id === props.activeId;
    engine.marker([p.lat, p.lng], { html: pricePin(p.priceLabel, active), size: [72, 26], anchor: [36, 13], zIndexOffset: active ? 1000 : 0, onClick: () => props.onSelect && props.onSelect(p.id) }, 'pins');
  });
}

watch([() => props.communities, () => props.layers.drive5, () => props.layers.drive10, () => props.layers.competition, () => props.valueLayer, () => props.driveCenter && props.driveCenter[0], status], drawOverlay, { deep: true });
watch([() => props.practices, () => props.activeId, () => props.layers.practices, status], drawPins, { deep: true });
```

`frontend/src/components/ListingsMap.vue` — replace the `<script setup>` with:
```js
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { clusterIcon, clusterize, pill } from '../map/markers.js';
import { createEngine } from '../map/create';

const props = defineProps({
  markers: { type: Array, default: () => [] }, activeId: { type: String, default: null }, hoverId: { type: String, default: null },
  onSelect: { type: Function, default: null }, onClusterClick: { type: Function, default: null },
  center: { type: Array, default: () => [30.31, -97.75] }, zoom: { type: Number, default: 10 }, dimmed: { type: Array, default: () => [] }, resizeKey: { type: String, default: '' }
});
const host = ref(null);
const status = ref('loading');
const z = ref(props.zoom);
let engine = null;
let offMove = null;

onMounted(async () => {
  try {
    const e = await createEngine();
    if (!host.value || engine) return;
    await e.mount(host.value, { center: props.center, zoom: props.zoom, basemap: 'map', zoomControl: 'bottomright', scaleControl: false, groups: ['layer'] });
    engine = e;
    offMove = e.onMove((_c, zoom) => { z.value = zoom; });
    status.value = 'ready';
    draw();
  } catch { status.value = 'error'; }
});
onBeforeUnmount(() => { if (offMove) offMove(); if (engine) { engine.destroy(); engine = null; } });

function draw() {
  if (!engine) return;
  engine.clear('layer');
  clusterize(props.markers, z.value).forEach((entry) => {
    if (entry.kind === 'cluster') {
      engine.marker([entry.lat, entry.lng], { html: clusterIcon(entry.count), size: [44, 44], anchor: [22, 22],
        onClick: () => { engine.setView([entry.lat, entry.lng], Math.max(z.value + 2, 11)); if (props.onClusterClick) props.onClusterClick(entry.ids); } }, 'layer');
    } else {
      const m = entry.m;
      const active = m.id === props.activeId || m.id === props.hoverId;
      engine.marker([m.lat, m.lng], { html: pill(m.priceLabel, active, props.dimmed.indexOf(m.id) > -1), size: [70, 26], anchor: [35, 13], zIndexOffset: active ? 1000 : 0,
        onClick: () => props.onSelect && props.onSelect(m.id) }, 'layer');
    }
  });
}

watch([() => props.markers, () => props.activeId, () => props.hoverId, z, status, () => props.dimmed], draw, { deep: true });
watch(() => props.resizeKey, () => { if (engine) engine.show(); });
watch([() => props.center && props.center[0], () => props.center && props.center[1], () => props.zoom, status], () => { if (engine && props.center) engine.setView(props.center, props.zoom, true); });
```
(The handoff's `zoomend` handler becomes `onMove`; `z` only changes on a zoom change, so redraws happen exactly when they did.)

- [ ] **Step 4: Run to verify passing**

Run: `cd frontend && npx vitest run && npm run build && npx vue-tsc --noEmit` → all pass; `dist/_app/` contains a separate `leaflet-*.js` chunk (the dynamic import) and the main bundle no longer contains `tileLayer`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/map frontend/src/lib/leaflet.js frontend/src/components/MarketMapView.vue frontend/src/components/ListingsMap.vue
git commit -m "refactor(map): MapEngine interface + LeafletMapEngine; marker builders moved out of lib/leaflet.js (pixels unchanged)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 1c: Characterisation tests for the untouched `logic.js`

The approved prototype's state machine is exercised end-to-end by the visual gate and the route smoke tests, but nothing pins its **rules** (sign-in gating, jump-bar behaviour, admin tab sets) at the unit level. These tests do — against the file exactly as shipped (the SP1 rule "logic.js untouched" stands). Characterisation tests are written against existing behaviour, so the RED step is a deliberate proof that they bite.

**Files:**
- Create: `frontend/src/logic.test.ts`

**Interfaces:**
- Consumes: `Component` from `frontend/src/logic.js` (`new Component({})`; `setState(patch)`; `go(screen)()`; `jumpTo(screen)()`; `renderVals()`; `adminVals()`; `filtered()`; `activeFilterCount()`; `setListingStatus(id, status)`; `money(n)`).
- Produces: nothing new — a safety net SP2 relies on when it wires the API into these transitions.

- [ ] **Step 1: Write the characterisation tests**

`frontend/src/logic.test.ts`:
```ts
// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { Component } from './logic.js';

let c: any;
beforeEach(() => { c = new Component({}); });

describe('logic.js — characterisation of the approved prototype (file untouched)', () => {
  it('starts signed out on the sign-in gate with the design defaults', () => {
    expect(c.state).toMatchObject({ screen: 'gate', gate: 'signin', auth: false, viewport: 'desktop', mobileTab: 'list', adminTab: 'users', detailId: 'p1', sellerView: 'dash' });
  });

  it('go() refuses navigation while signed out and returns to the sign-in gate', () => {
    c.setState({ screen: 'browse', userMenu: true });
    c.go('requests')();
    expect(c.state).toMatchObject({ screen: 'gate', gate: 'signin', userMenu: false, auth: false });
  });

  it('jumpTo() (the prototype jump bar) signs in and navigates; jumpTo("gate") signs out', () => {
    c.jumpTo('admin')();
    expect(c.state).toMatchObject({ screen: 'admin', auth: true, interest: 'closed', userMenu: false, gate: 'signin' });
    c.jumpTo('gate')();
    expect(c.state).toMatchObject({ screen: 'gate', auth: false });
  });

  it('go() navigates once signed in', () => {
    c.jumpTo('browse')();
    c.go('seller')();
    expect(c.state.screen).toBe('seller');
  });

  it('renderVals exposes the four nav items and six jumps with the design labels, plus the signed-in flags', () => {
    const v = c.renderVals();
    expect(v.nav.map((n: any) => n.label)).toEqual(['Browse Practices', 'My Requests', 'List a Practice', 'VIN Foundation Admin']);
    expect(v.jumps.map((j: any) => j.label)).toEqual(['Access', 'Browse', 'Listing', 'Requests', 'Seller', 'Admin']);
    expect(v.signedIn).toBe(false);
    expect(v.signedOut).toBe(true);
  });

  it('adminVals renders the four tabs and switches the row set with adminTab', () => {
    expect(c.adminVals().tabs.map((t: any) => t.label)).toEqual(['Users', 'Listings', 'Requests', 'Data Sources']);
    c.setState({ adminTab: 'data' });
    const a = c.adminVals();
    expect(a.columns).toEqual(['Dataset', 'Source and license', 'Status', 'Action']);
    expect(a.rows).toHaveLength(5);
    expect(a.footnote).toContain('No dataset reaches production until its license is recorded here');
  });

  it('setListingStatus changes exactly the targeted seller listing', () => {
    c.setListingStatus('s1', 'paused');
    expect(c.state.sellerListings.map((l: any) => [l.id, l.status])).toEqual([['s1', 'paused'], ['s2', 'in_review'], ['s3', 'draft'], ['s4', 'paused']]);
  });

  it('filters: activeFilterCount counts non-default filters and filtered() never grows', () => {
    const all = c.filtered().length;
    expect(c.activeFilterCount()).toBe(0);
    c.setState({ f: { ...c.state.f, doctors: '1' } });
    expect(c.activeFilterCount()).toBe(1);
    expect(c.filtered().length).toBeLessThanOrEqual(all);
  });

  it('money() formats the way the seller cards show it', () => {
    expect(c.money(1450000)).toBe('$1.45M');
    expect(c.money(860000)).toBe('$860K');
  });
});
```

- [ ] **Step 2: Run, then prove the tests bite (the RED of a characterisation suite)**

Run: `cd frontend && npx vitest run src/logic.test.ts` → all pass (they describe existing behaviour). If `money()` or a label differs from the literal above, the failure message shows the prototype's actual value — pin **that** value (the prototype is the oracle; never change `logic.js`).
Then change `expect(c.state.screen).toBe('seller')` to `'browse'` → run → **FAIL** with `expected 'seller' to be 'browse'` → revert. Every remaining test must be shown to fail the same way once; a test that cannot be made to fail is deleted.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/logic.test.ts
git commit -m "test(logic): characterisation suite for the untouched prototype state machine

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Router sync layer (vue-router around the untouched logic)

**Files:**
- Create: `frontend/src/router/routes.ts`, `frontend/src/router/sync.ts`, `frontend/src/router/sync.test.ts`, `frontend/src/router/useStateRouteSync.ts`, `frontend/src/main.ts`
- Modify: `frontend/src/App.vue:1295-1318` (script block only: two added lines + `prototypeBar` default), delete `frontend/src/main.js`

**Interfaces:**
- Produces: `stateToRoute(state: RoutedState): RouteTarget`; `routeToPatch(to: {path: string; params: Record<string, unknown>; query: Record<string, unknown>}): Partial<RoutedState>`; `guard(state: RoutedState & {auth?: boolean}, patch: Partial<RoutedState>): { apply: Partial<RoutedState>; pending: Partial<RoutedState> | null }` (signed-out + member screen → `apply = {screen:'gate', gate:'signin'}`, `pending = patch`); `needsPatch(state, patch): boolean`; `sameLocation(a: RouteTarget, b: {path: string; query: Record<string, unknown>}): boolean`; `useStateRouteSync(component, router)`.
- Consumes: `Component` from `logic.js` — `state.screen`, `state.browseMode`, `state.detailId`, `state.adminTab`, `setState(patch)`.

- [ ] **Step 1: Write the failing sync tests**

`frontend/src/router/sync.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { stateToRoute, routeToPatch, guard, needsPatch, sameLocation } from './sync';

const base = { screen: 'gate', browseMode: 'listings', detailId: 'p1', adminTab: 'users' };

describe('stateToRoute', () => {
  it('maps gate to /', () => expect(stateToRoute(base)).toEqual({ path: '/', query: {} }));
  it('maps browse listings to /browse with no query', () =>
    expect(stateToRoute({ ...base, screen: 'browse' })).toEqual({ path: '/browse', query: {} }));
  it('maps browse market to /browse?tab=market', () =>
    expect(stateToRoute({ ...base, screen: 'browse', browseMode: 'market' })).toEqual({ path: '/browse', query: { tab: 'market' } }));
  it('maps detail to /practices/:id', () =>
    expect(stateToRoute({ ...base, screen: 'detail', detailId: 'p7' })).toEqual({ path: '/practices/p7', query: {} }));
  it('maps requests and seller', () => {
    expect(stateToRoute({ ...base, screen: 'requests' }).path).toBe('/requests');
    expect(stateToRoute({ ...base, screen: 'seller' }).path).toBe('/seller');
  });
  it('maps admin tabs, omitting the default users tab', () => {
    expect(stateToRoute({ ...base, screen: 'admin' })).toEqual({ path: '/admin', query: {} });
    expect(stateToRoute({ ...base, screen: 'admin', adminTab: 'data' })).toEqual({ path: '/admin', query: { tab: 'data' } });
  });
  it('treats an undefined browseMode as listings (the logic does the same)', () =>
    expect(stateToRoute({ ...base, screen: 'browse', browseMode: undefined })).toEqual({ path: '/browse', query: {} }));
});

describe('routeToPatch', () => {
  const r = (path: string, query: Record<string, unknown> = {}, params: Record<string, unknown> = {}) => ({ path, query, params });
  it('/ → gate', () => expect(routeToPatch(r('/'))).toEqual({ screen: 'gate' }));
  it('/browse → browse listings', () => expect(routeToPatch(r('/browse'))).toEqual({ screen: 'browse', browseMode: 'listings' }));
  it('/browse?tab=market → browse market', () => expect(routeToPatch(r('/browse', { tab: 'market' }))).toEqual({ screen: 'browse', browseMode: 'market' }));
  it('/browse?tab=bogus → listings', () => expect(routeToPatch(r('/browse', { tab: 'bogus' }))).toEqual({ screen: 'browse', browseMode: 'listings' }));
  it('/practices/p3 → detail p3', () => expect(routeToPatch(r('/practices/p3', {}, { id: 'p3' }))).toEqual({ screen: 'detail', detailId: 'p3' }));
  it('/admin?tab=activity → admin activity', () => expect(routeToPatch(r('/admin', { tab: 'activity' }))).toEqual({ screen: 'admin', adminTab: 'activity' }));
  it('/admin?tab=nope → users', () => expect(routeToPatch(r('/admin', { tab: 'nope' }))).toEqual({ screen: 'admin', adminTab: 'users' }));
  it('unknown path → gate', () => expect(routeToPatch(r('/whatever'))).toEqual({ screen: 'gate' }));
  it('round-trips every screen', () => {
    for (const s of [
      { ...base, screen: 'browse', browseMode: 'market' },
      { ...base, screen: 'detail', detailId: 'g4' },
      { ...base, screen: 'requests' }, { ...base, screen: 'seller' },
      { ...base, screen: 'admin', adminTab: 'listings' }
    ]) {
      const loc = stateToRoute(s);
      const params = loc.path.startsWith('/practices/') ? { id: loc.path.split('/')[2] } : {};
      expect({ ...s, ...routeToPatch({ ...loc, params }) }).toEqual(s);
    }
  });
});

describe('guard (the prototype\'s go() semantics)', () => {
  it('sends a signed-out visitor to the gate and remembers the intended route', () =>
    expect(guard({ ...base, auth: false }, { screen: 'browse', browseMode: 'market' }))
      .toEqual({ apply: { screen: 'gate', gate: 'signin' }, pending: { screen: 'browse', browseMode: 'market' } }));
  it('applies member routes directly when signed in', () =>
    expect(guard({ ...base, auth: true }, { screen: 'admin', adminTab: 'data' })).toEqual({ apply: { screen: 'admin', adminTab: 'data' }, pending: null }));
  it('never guards the gate itself', () =>
    expect(guard({ ...base, auth: false }, { screen: 'gate' })).toEqual({ apply: { screen: 'gate' }, pending: null }));
});

describe('needsPatch / sameLocation', () => {
  it('needsPatch is false when state already matches', () =>
    expect(needsPatch({ ...base, screen: 'browse' }, { screen: 'browse', browseMode: 'listings' })).toBe(false));
  it('needsPatch is true on any difference', () =>
    expect(needsPatch(base, { screen: 'browse', browseMode: 'listings' })).toBe(true));
  it('sameLocation compares path and query', () => {
    expect(sameLocation({ path: '/browse', query: { tab: 'market' } }, { path: '/browse', query: { tab: 'market' } })).toBe(true);
    expect(sameLocation({ path: '/browse', query: {} }, { path: '/browse', query: { tab: 'market' } })).toBe(false);
  });
});
```

- [ ] **Step 2: Run — expect RED** — `npx vitest run src/router/sync.test.ts` → FAIL "Cannot find module './sync'".

- [ ] **Step 3: Implement `sync.ts`**

```ts
export type Screen = 'gate' | 'browse' | 'detail' | 'requests' | 'seller' | 'admin';
export interface RoutedState { screen: string; browseMode?: string; detailId?: string; adminTab?: string; gate?: string; auth?: boolean }
export interface RouteTarget { path: string; query: Record<string, string> }
interface RouteLike { path: string; params: Record<string, unknown>; query: Record<string, unknown> }

const BROWSE_TABS = ['listings', 'market'] as const;
const ADMIN_TABS = ['users', 'listings', 'activity', 'data'] as const;

export function stateToRoute(s: RoutedState): RouteTarget {
  switch (s.screen) {
    case 'browse': {
      const mode = s.browseMode || 'listings';
      return { path: '/browse', query: mode === 'market' ? { tab: 'market' } : {} };
    }
    case 'detail': return { path: `/practices/${s.detailId || 'p1'}`, query: {} };
    case 'requests': return { path: '/requests', query: {} };
    case 'seller': return { path: '/seller', query: {} };
    case 'admin': {
      const tab = s.adminTab || 'users';
      return { path: '/admin', query: tab === 'users' ? {} : { tab } };
    }
    default: return { path: '/', query: {} };
  }
}

function pick<T extends string>(v: unknown, allowed: readonly T[], fallback: T): T {
  return (allowed as readonly string[]).includes(String(v)) ? (v as T) : fallback;
}

export function routeToPatch(to: RouteLike): Partial<RoutedState> {
  if (to.path === '/browse') return { screen: 'browse', browseMode: pick(to.query.tab, BROWSE_TABS, 'listings') };
  if (to.path.startsWith('/practices/') && typeof to.params.id === 'string') return { screen: 'detail', detailId: to.params.id };
  if (to.path === '/requests') return { screen: 'requests' };
  if (to.path === '/seller') return { screen: 'seller' };
  if (to.path === '/admin') return { screen: 'admin', adminTab: pick(to.query.tab, ADMIN_TABS, 'users') };
  return { screen: 'gate' };
}

// The prototype's go(): a member screen requested while signed out shows the gate
// (sign-in tab) and the request is remembered until auth flips true.
export function guard(state: RoutedState & { auth?: boolean }, patch: Partial<RoutedState>): { apply: Partial<RoutedState>; pending: Partial<RoutedState> | null } {
  if (patch.screen && patch.screen !== 'gate' && !state.auth) return { apply: { screen: 'gate', gate: 'signin' } as Partial<RoutedState>, pending: patch };
  return { apply: patch, pending: null };
}

export function needsPatch(state: RoutedState, patch: Partial<RoutedState>): boolean {
  return Object.entries(patch).some(([k, v]) => (state as Record<string, unknown>)[k] !== v);
}

export function sameLocation(a: RouteTarget, b: { path: string; query: Record<string, unknown> }): boolean {
  if (a.path !== b.path) return false;
  const ak = Object.keys(a.query), bk = Object.keys(b.query);
  return ak.length === bk.length && ak.every((k) => String(a.query[k]) === String(b.query[k]));
}
```

- [ ] **Step 4: Run — expect GREEN** — `npx vitest run src/router/sync.test.ts` → all pass.

- [ ] **Step 5: Routes, composable, main.ts, App.vue wiring**

`frontend/src/router/routes.ts`:
```ts
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import App from '../App.vue';

// Every route renders the single approved component; the URL is a mirror of
// state.screen (+ browseMode / detailId / adminTab). See router/sync.ts.
export const routes: RouteRecordRaw[] = [
  { path: '/', component: App },
  { path: '/browse', component: App },
  { path: '/practices/:id', component: App },
  { path: '/requests', component: App },
  { path: '/seller', component: App },
  { path: '/admin', component: App },
  { path: '/:pathMatch(.*)*', redirect: '/' }
];

export const router = createRouter({ history: createWebHistory(), routes });
```

`frontend/src/router/useStateRouteSync.ts`:
```ts
import { watch } from 'vue';
import type { Router } from 'vue-router';
import { guard, needsPatch, routeToPatch, sameLocation, stateToRoute, type RoutedState } from './sync';

interface StatefulComponent { state: RoutedState; setState(patch: Partial<RoutedState>): void }

// Route → state first (so a deep link is honoured before the state → route watcher can
// rewrite the URL), then state → route. A member route requested while signed out shows
// the gate, keeps the URL, and is applied the moment the fixture sign-in flips auth.
export function useStateRouteSync(c: StatefulComponent, router: Router): void {
  let pending: Partial<RoutedState> | null = null;
  const apply = (to: { path: string; params: Record<string, unknown>; query: Record<string, unknown> }) => {
    const g = guard(c.state, routeToPatch(to));
    pending = g.pending;
    if (needsPatch(c.state, g.apply)) c.setState(g.apply);
  };
  apply(router.currentRoute.value);
  router.afterEach((to) => apply(to));
  watch(() => c.state.auth, (auth) => {
    if (auth && pending) { const p = pending; pending = null; c.setState(p); }
  });
  watch(
    () => stateToRoute(c.state),
    (loc) => {
      if (pending) return;                       // keep the deep link visible while the gate is shown
      const cur = router.currentRoute.value;
      if (sameLocation(loc, cur)) return;
      if (loc.path === cur.path) router.replace(loc); else router.push(loc);
    },
    { deep: true }
  );
}
```

`frontend/src/main.ts` (delete `main.js`):
```ts
import { createApp } from 'vue';
import { router } from './router/routes';
import './styles/tokens.css';
import './styles/global.css';
import { h } from 'vue';
import { RouterView } from 'vue-router';

router.isReady().then(() => {
  createApp({ render: () => h(RouterView) }).use(router).mount('#app');
});
```
Update `frontend/index.html`: `<script type="module" src="/src/main.ts"></script>`.

`frontend/src/App.vue` script edits (only these):
```js
import { useRouter } from 'vue-router';                       // add after the vue import
import { useStateRouteSync } from './router/useStateRouteSync'; // add after the hover import
// …
const props = defineProps({
  prototypeBar: { type: Boolean, default: import.meta.env.VITE_ENVIRONMENT !== 'production' },  // was: default: false
  startScreen: { type: String, default: 'gate' },
  startViewport: { type: String, default: 'desktop' }
});
// …
c.state = reactive(c.state);
useStateRouteSync(c, useRouter());                             // add directly after the reactive() line
```

- [ ] **Step 6: Typecheck, unit tests, build**

Run: `npm run typecheck && npm test && npm run build` → all green.

- [ ] **Step 7: Manual sanity in dev (agent only — John does not run locally)**

Run: `npm run dev &` then `curl -s localhost:5173/browse | grep -c 'src/main.ts'` → `1`. Kill the dev server.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat(frontend): vue-router sync layer over the untouched prototype logic

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/platform && git push production feat/platform
```

---

### Task 3: Visual-fidelity harness — reference server, screen table, baseline generator, visual spec

**Files:**
- Create: `frontend/tests/playwright.config.ts`, `frontend/tests/reference-server.mjs`, `frontend/tests/harness.ts`, `frontend/tests/screens.ts`, `frontend/tests/reference-baselines.spec.ts`, `frontend/tests/visual.spec.ts`, `frontend/tests/visual.spec.ts-snapshots/*-darwin.png` (generated)
- Modify: `frontend/package.json` (already has the scripts from Task 1), `.gitignore` (add `frontend/test-results/`, `frontend/playwright-report/` — already present)

**Interfaces:**
- Produces: `SCREENS: Screen[]` with `{ name, viewport?, steps(page) }`; helpers `prepare(page)`, `settle(page)`, `jump(page, label)`, `click(page, text)`, `btn(page, nameRegex)`, `waitMap(page)`.
- Consumes: the app at `http://localhost:5173/` (Task 2 routes) and the reference at `http://localhost:5174/`.

- [ ] **Step 1: Install Playwright**

```bash
cd frontend && npm install -D @playwright/test && npx playwright install chromium
# Vendor the exact files support.js loads (SRI-pinned, so the bytes must be identical) so CI
# never depends on unpkg being up. MIT-licensed; committed under the reference bundle.
V="../docs/design-reference/design_handoff_practice_match_v2/vendor"; mkdir -p "$V"
curl -sSL -o "$V/react.production.min.js"     https://unpkg.com/react@18.3.1/umd/react.production.min.js
curl -sSL -o "$V/react-dom.production.min.js" https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js
curl -sSL -o "$V/babel.min.js"                https://unpkg.com/@babel/standalone@7.29.0/babel.min.js
curl -sSL -o "$V/leaflet.css"                 https://unpkg.com/leaflet@1.9.4/dist/leaflet.css     # AustinMap.jsx / MarketMap.jsx load Leaflet from unpkg too (John's ruling, Task 3 D3)
curl -sSL -o "$V/leaflet.js"                  https://unpkg.com/leaflet@1.9.4/dist/leaflet.js
grep -ohE 'https://unpkg.com/[^"]+' "$V/../support.js" "$V/../AustinMap.jsx" "$V/../MarketMap.jsx" | sort -u   # must list exactly these five URLs; verify each file's SHA-384 against the SRI hash in the source
```

**Error gate (policy §2):** `prepare()` also registers the `pageerror` and `console.error` handlers from `docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md` §5 — any browser error fails the test. RED: add a temporary `console.error('x')` to `main.ts` and watch the smoke test fail; remove it.

- [ ] **Step 2: Reference static server** — `frontend/tests/reference-server.mjs`

```js
// Serves the approved design bundle so Playwright can screenshot the reference.
// The bundle's runtime (support.js) re-fetches location.href to parse <x-dc>, so
// "/" must return the same bytes as the design file itself.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const ROOT = normalize(join(HERE, '../../docs/design-reference/design_handoff_practice_match_v2'));
const PORT = Number(process.argv[2] || 5174);
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.jsx': 'text/javascript',
  '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpeg': 'image/jpeg', '.jpg': 'image/jpeg',
  '.webp': 'image/webp', '.woff': 'font/woff', '.ttf': 'font/ttf', '.json': 'application/json', '.md': 'text/plain'
};

createServer(async (req, res) => {
  const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  const rel = pathname === '/' ? '/Practice Match V2.dc.html' : pathname;
  const file = normalize(join(ROOT, rel));
  if (!file.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
  try {
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(body);
  } catch {
    res.writeHead(404); res.end();
  }
}).listen(PORT, () => console.log(`[reference-server] ${ROOT} on http://localhost:${PORT}`));
```

- [ ] **Step 3: Playwright config** — `frontend/tests/playwright.config.ts`

```ts
import { defineConfig, devices } from '@playwright/test';

const APP = Number(process.env.PW_APP_PORT) || 5173;
const REF = Number(process.env.PW_REF_PORT) || 5174;
const VIEWPORT = { width: 1440, height: 940 }; // the design's preview size

export default defineConfig({
  testDir: '.',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  reporter: [['list']],
  // Baselines are produced from the reference by the `reference` project and
  // named <state>-<platform>.png. The app must never overwrite them.
  snapshotPathTemplate: '{testDir}/visual.spec.ts-snapshots/{arg}-{platform}{ext}',
  updateSnapshots: 'none',
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000
  },
  expect: {
    timeout: 15_000,
    toHaveScreenshot: {
      // Spec §4: same Chromium, same fonts, same DOM → zero tolerance to start.
      // If relaxed, the ceiling is maxDiffPixelRatio 0.001 and the reason goes here.
      maxDiffPixels: 0,
      threshold: 0.1,
      animations: 'disabled',
      caret: 'hide',
      scale: 'css'
    }
  },
  projects: [
    { name: 'app', testMatch: /(visual|smoke)\.spec\.ts/, use: { ...devices['Desktop Chrome'], viewport: VIEWPORT, baseURL: `http://localhost:${APP}` } },
    { name: 'reference', testMatch: /reference-baselines\.spec\.ts/, use: { ...devices['Desktop Chrome'], viewport: VIEWPORT, baseURL: `http://localhost:${REF}` } }
  ],
  webServer: [
    { command: `npm run dev -- --port ${APP} --strictPort`, url: `http://localhost:${APP}`, cwd: '..', timeout: 60_000, reuseExistingServer: !process.env.CI, stdout: 'ignore', stderr: 'pipe' },
    { command: `node tests/reference-server.mjs ${REF}`, url: `http://localhost:${REF}/`, cwd: '..', timeout: 30_000, reuseExistingServer: !process.env.CI, stdout: 'ignore', stderr: 'pipe' }
  ]
});
```

- [ ] **Step 4: Shared helpers** — `frontend/tests/harness.ts`

```ts
import type { Page } from '@playwright/test';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

export type JumpLabel = 'Access' | 'Browse' | 'Listing' | 'Requests' | 'Seller' | 'Admin';

// Deterministic rendering on both targets: no basemap tiles (markers still draw
// over the blank canvas), fonts loaded, pointer parked, animations settled.
const VENDOR = join(fileURLToPath(new URL('.', import.meta.url)), '../../docs/design-reference/design_handoff_practice_match_v2/vendor');
const VENDORED: Record<string, string> = {
  'https://unpkg.com/react@18.3.1/umd/react.production.min.js': 'react.production.min.js',
  'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js': 'react-dom.production.min.js',
  'https://unpkg.com/@babel/standalone@7.29.0/babel.min.js': 'babel.min.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css': 'leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js': 'leaflet.js'
};

export async function prepare(page: Page): Promise<void> {
  // Fulfil, don't abort: an aborted tile request makes Chromium log console.error, which the error gate fails on (John's ruling, Task 3 D2).
  await page.route(/arcgisonline\.com/, (route) => route.fulfill({ status: 200, contentType: 'image/gif', body: BLANK_GIF }));
  // The reference runtime loads React/Babel from unpkg with SRI hashes; serve the vendored
  // identical bytes so the suite is deterministic and offline-safe (same hashes → SRI passes).
  await page.route('https://unpkg.com/**', (route) => {
    const file = VENDORED[route.request().url()];
    return file ? route.fulfill({ path: join(VENDOR, file), contentType: 'text/javascript' }) : route.abort();
  });
}

export async function booted(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByRole('button', { name: 'Access', exact: true }).first().waitFor({ state: 'visible' });
}

export async function settle(page: Page): Promise<void> {
  await page.evaluate(() => (document as Document & { fonts: FontFaceSet }).fonts.ready);
  await page.mouse.move(0, 0);
  await page.waitForTimeout(600);
}

// The design's own prototype jump bar: signs in and switches screen on both targets.
export async function jump(page: Page, label: JumpLabel): Promise<void> {
  await page.getByRole('button', { name: label, exact: true }).first().click();
}

export async function click(page: Page, text: string): Promise<void> {
  await page.getByText(text, { exact: true }).first().click();
}

export function btn(page: Page, name: RegExp) {
  return page.getByRole('button', { name }).first();
}

export async function waitMap(page: Page): Promise<void> {
  await page.locator('.leaflet-container').first().waitFor({ state: 'visible' });
  await page.waitForTimeout(700); // Leaflet setView + marker layer
}
```

- [ ] **Step 5: The screen table** — `frontend/tests/screens.ts`

```ts
import type { Page } from '@playwright/test';
import { btn, click, jump, waitMap } from './harness';

export interface Screen {
  name: string;
  viewport?: { width: number; height: number }; // default 1440×940 from the config
  steps: (page: Page) => Promise<void>;         // identical clicks on reference and app, from the gate
}

const browse = async (p: Page) => { await jump(p, 'Browse'); await waitMap(p); };
const market = async (p: Page) => { await browse(p); await click(p, 'Market Data'); await waitMap(p); };
const wizard = async (p: Page) => { await jump(p, 'Seller'); await click(p, 'Create a listing'); };
const admin = async (p: Page) => { await jump(p, 'Admin'); };
const mobile = async (p: Page) => { await click(p, 'Mobile view'); await jump(p, 'Browse'); };

export const SCREENS: Screen[] = [
  { name: 'gate-signin', steps: async () => {} },
  { name: 'gate-apply', steps: async (p) => { await click(p, 'Request access'); } },
  { name: 'gate-pending', steps: async (p) => { await click(p, 'Pending approval'); } },
  { name: 'gate-declined', steps: async (p) => { await click(p, 'Request declined'); } },
  { name: 'browse-listings', steps: browse },
  { name: 'browse-market', steps: market },
  { name: 'browse-market-layers-closed', steps: async (p) => { await market(p); await click(p, 'Data Layers'); } },
  { name: 'browse-market-panel', steps: async (p) => { await market(p); await p.getByText('Cedar Park').first().click(); await p.waitForTimeout(400); } },
  { name: 'detail', steps: async (p) => { await jump(p, 'Listing'); } },
  { name: 'interest-modal', steps: async (p) => { await jump(p, 'Browse'); await click(p, 'Round Rock'); await click(p, "I'm interested"); } },   // p2: the default listing p1 already has a pending request in the seed data, so its button reads "Request pending" (John's ruling, Task 3 D4)
  { name: 'requests', steps: async (p) => { await jump(p, 'Requests'); } },
  { name: 'seller-dash', steps: async (p) => { await jump(p, 'Seller'); } },
  { name: 'wizard-step-1', steps: wizard },
  { name: 'wizard-step-7', steps: async (p) => { await wizard(p); await btn(p, /^7/).click(); } },
  { name: 'wizard-preview', steps: async (p) => { await wizard(p); await btn(p, /^8/).click(); } },
  { name: 'wizard-done', steps: async (p) => { await wizard(p); await btn(p, /^8/).click(); await click(p, 'Submit for review'); } },
  { name: 'admin-users', steps: admin },
  { name: 'admin-listings', steps: async (p) => { await admin(p); await btn(p, /^Listings\s*\d/).click(); } },
  { name: 'admin-requests', steps: async (p) => { await admin(p); await btn(p, /^Requests\s*\d/).click(); } },
  { name: 'admin-data-sources', steps: async (p) => { await admin(p); await btn(p, /^Data Sources\s*\d/).click(); } },
  { name: 'mobile-list', steps: mobile },
  { name: 'mobile-map', steps: async (p) => { await mobile(p); await click(p, 'Map'); await waitMap(p); } },
  { name: 'mobile-detail', steps: async (p) => { await mobile(p); await p.getByText('Cedar Park').first().click(); } },
  { name: 'header-1100', viewport: { width: 1100, height: 940 }, steps: browse },
  { name: 'header-1000', viewport: { width: 1000, height: 940 }, steps: browse }
];
```

- [ ] **Step 6: Baseline generator** — `frontend/tests/reference-baselines.spec.ts`

```ts
import { test } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCREENS } from './screens';
import { booted, prepare, settle } from './harness';

const OUT = join(fileURLToPath(new URL('.', import.meta.url)), 'visual.spec.ts-snapshots');

// Produces the oracle images from the approved design. Run only via
// `npm run test:visual:baselines`; commit the PNGs.
test.describe('reference baselines', () => {
  for (const s of SCREENS) {
    test(s.name, async ({ page }) => {
      mkdirSync(OUT, { recursive: true });
      await prepare(page);
      if (s.viewport) await page.setViewportSize(s.viewport);
      await booted(page);
      await s.steps(page);
      await settle(page);
      await page.screenshot({ path: join(OUT, `${s.name}-${process.platform}.png`), fullPage: true, animations: 'disabled', caret: 'hide', scale: 'css' });
    });
  }
});
```

- [ ] **Step 7: Visual spec** — `frontend/tests/visual.spec.ts`

```ts
import { test, expect } from '@playwright/test';
import { SCREENS } from './screens';
import { booted, prepare, settle } from './harness';

// Every approved screen state must match the reference's screenshot.
test.describe('visual parity with the approved design', () => {
  for (const s of SCREENS) {
    test(s.name, async ({ page }) => {
      await prepare(page);
      if (s.viewport) await page.setViewportSize(s.viewport);
      await booted(page);
      await s.steps(page);
      await settle(page);
      await expect(page).toHaveScreenshot(`${s.name}.png`, { fullPage: true });
    });
  }
});
```

- [ ] **Step 8: Generate baselines from the reference**

Run: `npm run test:visual:baselines`
Expected: 25 passed; `ls tests/visual.spec.ts-snapshots | wc -l` → `25`, all `*-darwin.png`. Open two (`gate-signin`, `browse-market`) with the Read tool and confirm they show the design (jump bar on top, sign-in card / market map). If any test fails on a selector, fix the selector in `screens.ts` using the reference's DOM (`page.pause()` is acceptable locally) — never by editing the reference.

- [ ] **Step 9: Run the visual spec — expect RED, and record it**

Run: `npm run test:visual 2>&1 | tee /tmp/visual-red.txt; grep -E '✘|✓' /tmp/visual-red.txt | sort | uniq -c`
Expected: some states fail (this is the RED for Task 4). Write the failing state names into the Task 4 report later. If ALL 25 pass on the first run, stop and re-check that `snapshotPathTemplate` is pointing at the generated files (a pass with zero baselines is impossible because `updateSnapshots: 'none'` fails on a missing baseline).

- [ ] **Step 10: Ignore generated baselines, commit the harness**

Baselines are regenerated from the reference on every run (locally and in CI), so they are never committed. Add to `.gitignore`: `frontend/tests/visual.spec.ts-snapshots/`.

```bash
git add .gitignore frontend/tests frontend/package.json frontend/package-lock.json
git commit -m "test(visual): reference-driven Playwright harness with 25 screen states

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push origin feat/platform && git push production feat/platform
```

---

> **Task 1b check:** the `MapEngine` refactor (Task 1b) must produce zero pixel differences on every map state; any map-region diff after Task 1b is a Task 1b bug, not a design mismatch.

> **Task 4 re-planned 2026-09-05 (John's ruling):** the hand conversion produced port bugs (hover restore, `d.` vs `v.d.`, watcher order) and two design-tool artifacts (interpolation spans, `image-slot`). Instead of spot fixes, `App.vue` is regenerated mechanically from the design template by a golden-tested transpiler (4a–4b), `ImageSlot` is ported for parity (4c), a DOM oracle compares app and design element by element (4d), and parity is brought to green under both oracles (4e). The route smoke suite from the original Task 4 already exists (commit 5a5ea8c).

### Task 4a: `convert-dc` — the design-template → Vue transpiler (runtime-faithful, golden-tested)

**Decision (John, 2026-09-05):** the Vue conversion is regenerated mechanically from the design, not hand-fixed. The design file `Practice Match V2.dc.html` is an HTML template inside `<x-dc>…</x-dc>` with a small grammar rendered by the tool's runtime (`support.js`): `{{ expr }}` interpolations, `<sc-if value="{{…}}">`, `<sc-for list="{{…}}" as="x">`, `onClick="{{ fn }}"`-style events, `style-hover="css"` pseudo-classes, `<x-import component="AustinMap|MarketMap">` for the two JSX map components, and the `<image-slot>` custom element. This task writes a transpiler that mirrors those runtime rules exactly; Task 4b regenerates `App.vue` from it.

**Files:**
- Create: `frontend/scripts/convert-dc.mjs`, `frontend/tests/convert-dc.test.ts`
- Modify: `frontend/package.json` (`"gen:app"` script; dev dep `htmlparser2`)

**Interfaces:**
- Produces (ESM, Node): `extractTemplate(html: string): string` (innerHTML of `<x-dc>` with the `<helmet>…</helmet>` block removed); `compileExpr(expr: string, scope: Set<string>): string` (the runtime's `resolve` grammar → a JS expression over `v`); `convert(templateHtml: string): { template: string; pseudoCss: string }`; `buildAppVue(template: string, setupJs: string, pseudoCssImport: string): string`; CLI `node scripts/convert-dc.mjs <dc.html> <app.setup.js> <out App.vue> <out pseudo.css>`.
- Also applied (not a runtime rule — the plan's Global Constraint (a)): static attribute values beginning `assets/` or `ds/` are rewritten to `/assets/`, `/ds/` (Vite serves `public/` at the root); bound values are untouched because `logic.js` already carries absolute paths.
- Runtime rules mirrored (from `docs/design-reference/design_handoff_practice_match_v2/support.js`, line refs in that file): template = innerHTML of `<x-dc>` (`parseDcDocument`, l.24–37) · `{{ }}` in text → `<span class="sc-interp">String(v)</span>`; `undefined`/`null`/booleans render nothing (`walkText`, l.569–609) · attribute whole-`{{}}` → the resolved value; mixed → string join with `?? ""` (`compileAttr`, l.401–412) · `style` string → per-declaration inline style (`cssToObj`, l.392) · `value`/`checked` undefined → `""`/`false` (`walkElement`, l.801–803) · `style-<pseudo>="css"` → a generated class whose rule is `.cls:pseudo{ css !important… }` (`createPseudoSheet`+`importantify`, l.1600s) · events: React `onChange` fires like the native `input` event on text inputs/textareas and like `change` on `select`/checkbox/radio · `sc-if value` truthiness (`walkIf`) · `sc-for list as` with `$index`, non-arrays → `[]` (`walkFor`) · expression grammar (`resolve`, l.205–296): parens, `=== !== == !=`, `!`, `true/false/null/undefined`, numbers, quoted strings, dotted/bracket paths that never throw on missing intermediates.

- [ ] **Step 1: Failing golden tests**

`frontend/tests/convert-dc.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { buildAppVue, compileExpr, convert, extractTemplate } from '../scripts/convert-dc.mjs';

const S = new Set<string>();

describe('compileExpr — the runtime resolve() grammar', () => {
  it('prefixes root identifiers with v., leaves loop aliases and $index alone, and never throws on missing paths', () => {
    expect(compileExpr('showPrototypeBar', S)).toBe('v.showPrototypeBar');
    expect(compileExpr('md.panel.photos.currentId', S)).toBe('v.md?.panel?.photos?.currentId');
    expect(compileExpr('j.go', new Set(['j']))).toBe('j?.go');
    expect(compileExpr('$index', new Set(['$index']))).toBe('$index');
    expect(compileExpr('rows[$index].label', new Set(['$index']))).toBe('v.rows?.[$index]?.label');
    expect(compileExpr('a[b.c]', S)).toBe('v.a?.[v.b?.c]');
  });
  it('translates equality, negation, literals and parentheses', () => {
    expect(compileExpr("gate === 'signin'", S)).toBe("(v.gate) === ('signin')");
    expect(compileExpr('!(auth == true)', S)).toBe('!((v.auth) == (true))');
    expect(compileExpr('count != 0', S)).toBe('(v.count) != (0)');
    expect(compileExpr('null', S)).toBe('null'); expect(compileExpr('12.5', S)).toBe('12.5'); expect(compileExpr('"x"', S)).toBe('"x"');
  });
});

describe('convert — template constructs', () => {
  it('wraps text interpolations in sc-interp spans that vanish for null/undefined/boolean, keeping literal text and whitespace verbatim', () => {
    const { template } = convert('<p>Hello {{ name }} and {{ other }}!</p>');
    expect(template).toBe('<p>Hello <span v-if="__s(v.name) !== null" class="sc-interp">{{ __s(v.name) }}</span> and <span v-if="__s(v.other) !== null" class="sc-interp">{{ __s(v.other) }}</span>!</p>');
  });
  it('binds whole-interpolated attributes, joins mixed ones with ?? "", and defaults value/checked', () => {
    const { template } = convert('<input value="{{ form.email }}" placeholder="Hi {{ who }}!" onChange="{{ setEmail }}" checked="{{ on }}">');
    expect(template).toBe('<input :value="(v.form?.email) ?? \'\'" :placeholder="`Hi ${(v.who) ?? \'\'}!`" @input="v.setEmail" :checked="(v.on) ?? false">');
  });
  it('maps React events: onClick → @click; onChange → @input on text controls and @change on select/checkbox/radio', () => {
    expect(convert('<button onClick="{{ go }}">x</button>').template).toBe('<button @click="v.go">x</button>');
    expect(convert('<select onChange="{{ pick }}"></select>').template).toBe('<select @change="v.pick"></select>');
    expect(convert('<input type="checkbox" onChange="{{ toggle }}">').template).toBe('<input type="checkbox" @change="v.toggle">');
    expect(convert('<textarea onChange="{{ set }}"></textarea>').template).toBe('<textarea @input="v.set"></textarea>');
    expect(convert('<div onMouseEnter="{{ a }}" onMouseLeave="{{ b }}"></div>').template).toBe('<div @mouseenter="v.a" @mouseleave="v.b"></div>');
  });
  it('turns style-hover into a generated pseudo-class with !important declarations, deduplicated by css text', () => {
    const { template, pseudoCss } = convert('<button class="x" style-hover="background: rgba(255,255,255,.26); color: #fff"></button><a style-hover="background: rgba(255,255,255,.26); color: #fff"></a><i style-hover="opacity: .5"></i>');
    expect(template).toBe('<button class="x sch0"></button><a class="sch0"></a><i class="sch1"></i>');
    expect(pseudoCss).toBe('.sch0:hover{background: rgba(255,255,255,.26) !important;color: #fff !important}\n.sch1:hover{opacity: .5 !important}\n');
  });
  it('merges a pseudo class into a dynamic class binding', () => {
    expect(convert('<b class="{{ cls }}" style-hover="x: y"></b>').template).toBe('<b :class="[v.cls, \'sch0\']"></b>');
  });
  it('converts sc-if and sc-for (with $index and the array guard), scoping loop aliases', () => {
    const { template } = convert('<sc-if value="{{ isDesktop }}" hint-placeholder-val="{{ true }}"><sc-for list="{{ nav }}" as="n" hint-placeholder-count="4"><button onClick="{{ n.go }}" style="{{ n.style }}">{{ n.label }} {{ title }}</button></sc-for></sc-if>');
    expect(template).toBe('<template v-if="v.isDesktop"><template v-for="(n, $index) in __arr(v.nav)" :key="$index"><button @click="n?.go" :style="n?.style"><span v-if="__s(n?.label) !== null" class="sc-interp">{{ __s(n?.label) }}</span> <span v-if="__s(v.title) !== null" class="sc-interp">{{ __s(v.title) }}</span></button></template></template>');
  });
  it('maps x-import and image-slot to the Vue components with bound props and drops hint-* attributes', () => {
    const { template } = convert('<x-import component="AustinMap" from="./AustinMap.jsx" markers="{{ markers }}" active-id="{{ activeId }}" on-select="{{ selectMarker }}" hint-size="100%,100%"></x-import><image-slot id="{{ p.photoId }}" shape="rect" src="{{ p.photoSrc }}" placeholder="{{ p.photoLabel }}"></image-slot>');
    expect(template).toBe('<ListingsMap :markers="v.markers" :active-id="v.activeId" :on-select="v.selectMarker"></ListingsMap><ImageSlot :id="v.p?.photoId" shape="rect" :src="v.p?.photoSrc" :placeholder="v.p?.photoLabel"></ImageSlot>');
    expect(convert('<x-import component="MarketMap" from="./MarketMap.jsx" practices="{{ md.practices }}"></x-import>').template).toBe('<MarketMapView :practices="v.md?.practices"></MarketMapView>');
  });
  it('drops HTML comments and the helmet block, escapes text, keeps attribute case', () => {
    expect(extractTemplate('<html><x-dc><helmet><style>a{}</style></helmet>\n<div aria-label="Go">a &amp; b</div></x-dc><script data-dc-script></script></html>')).toBe('\n<div aria-label="Go">a &amp; b</div>');
    expect(convert('<!-- note --><div>a &lt; b</div>').template).toBe('<div>a &lt; b</div>');
  });
  it('rewrites the design\'s relative asset paths to the app\'s absolute public paths (Global Constraint (a)), static values only', () => {
    expect(convert('<img src="assets/vin-foundation-logo.png" alt="VIN"><link href="ds/kit.css"><img src="{{ p.photoSrc }}">').template)
      .toBe('<img src="/assets/vin-foundation-logo.png" alt="VIN"><link href="/ds/kit.css"><img :src="v.p?.photoSrc">');
  });
  it('the CLI runs from a path containing spaces (self-invocation guard compares file paths, not URL strings)', async () => {
    const { mkdtempSync, writeFileSync, readFileSync, existsSync } = await import('node:fs');
    const { execFileSync } = await import('node:child_process');
    const { join } = await import('node:path');
    const dir = mkdtempSync(join(process.env.TMPDIR ?? '/tmp', 'convert dc '));
    writeFileSync(join(dir, 'd.html'), '<html><x-dc><div>{{ a }}</div></x-dc></html>'); writeFileSync(join(dir, 'setup.js'), 'const x = 1;\n');
    execFileSync(process.execPath, [join(import.meta.dirname, '..', 'scripts', 'convert-dc.mjs'), join(dir, 'd.html'), join(dir, 'setup.js'), join(dir, 'App.vue'), join(dir, 'pseudo.css')]);
    expect(existsSync(join(dir, 'App.vue')) && readFileSync(join(dir, 'App.vue'), 'utf8').includes('sc-interp')).toBe(true);
  });
  it('is idempotent and buildAppVue assembles the SFC from the generated template and the hand-maintained setup script', () => {
    const t = convert('<div>{{ a }}</div>');
    expect(convert('<div>{{ a }}</div>')).toEqual(t);
    const sfc = buildAppVue(t.template, "const x = 1;\n", './generated/pseudo.css');
    expect(sfc.startsWith('<!-- GENERATED by frontend/scripts/convert-dc.mjs from docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html — do not edit; run `npm run gen:app` -->\n<template>\n')).toBe(true);
    expect(sfc).toContain("<script setup>\nimport './generated/pseudo.css';\nconst x = 1;\n</script>");
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && source ~/.nvm/nvm.sh && nvm use 22 && npm install -D htmlparser2 && npx vitest run tests/convert-dc.test.ts` → **FAIL** (`Cannot find module '../scripts/convert-dc.mjs'`).

- [ ] **Step 3: Implement `frontend/scripts/convert-dc.mjs`**

```js
#!/usr/bin/env node
// Design template → Vue template. Mirrors the dc runtime (docs/design-reference/.../support.js) rule for rule; see the
// plan's Task 4a "Runtime rules mirrored". Output is deterministic: the same input always yields the same output.
import { readFileSync, writeFileSync } from 'node:fs';
import { parseDocument } from 'htmlparser2';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const IDENT_RE = /^[A-Za-z_$][\w$]*/;
const NUMBER_RE = /^-?\d+(\.\d+)?$/;
const EVENTS = { onClick: 'click', onInput: 'input', onSubmit: 'submit', onKeyDown: 'keydown', onKeyUp: 'keyup', onKeyPress: 'keypress', onMouseDown: 'mousedown', onMouseUp: 'mouseup',
  onMouseEnter: 'mouseenter', onMouseLeave: 'mouseleave', onFocus: 'focus', onBlur: 'blur', onDoubleClick: 'dblclick', onContextMenu: 'contextmenu', onMouseMove: 'mousemove',
  onMouseOver: 'mouseover', onMouseOut: 'mouseout', onPointerDown: 'pointerdown', onPointerUp: 'pointerup', onPointerMove: 'pointermove', onPointerEnter: 'pointerenter', onPointerLeave: 'pointerleave' };
const COMPONENTS = { AustinMap: 'ListingsMap', MarketMap: 'MarketMapView', 'image-slot': 'ImageSlot' };
const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const escAttr = (s) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
const jsStr = (s) => `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;

export function extractTemplate(html) {
  const open = /<x-dc(?:\s[^>]*)?>/.exec(html); const close = html.lastIndexOf('</x-dc>');
  if (!open || close < 0) throw new Error('no <x-dc> template');
  return html.slice(open.index + open[0].length, close).replace(/<helmet(?:\s[^>]*)?>[\s\S]*?<\/helmet\s*>/gi, '');
}

function parensWrapWhole(e) { let d = 0; for (let i = 0; i < e.length - 1; i++) { if (e[i] === '(') d++; else if (e[i] === ')') { d--; if (d === 0) return false; } } return true; }
function topEquality(e) {
  let d = 0;
  for (let i = 0; i < e.length; i++) {
    const c = e[i];
    if (c === '[' || c === '(') d++; else if (c === ']' || c === ')') d--;
    else if (d === 0 && (c === '=' || c === '!') && e[i + 1] === '=') {
      if (i > 0 && (e[i - 1] === '=' || e[i - 1] === '!')) continue;
      if (!e.slice(0, i).trim()) continue;
      const op = e[i + 2] === '=' ? c + '==' : c + '=';
      return { index: i, op };
    }
  }
  return null;
}
export function compileExpr(src, scope) {
  const e = String(src).trim();
  if (!e) return 'undefined';
  if (e[0] === '(' && e[e.length - 1] === ')' && parensWrapWhole(e)) return compileExpr(e.slice(1, -1), scope);
  const eq = topEquality(e);
  if (eq) return `(${compileExpr(e.slice(0, eq.index), scope)}) ${eq.op} (${compileExpr(e.slice(eq.index + eq.op.length), scope)})`;
  if (e[0] === '!') return `!(${compileExpr(e.slice(1), scope)})`;
  if (['true', 'false', 'null', 'undefined'].includes(e) || NUMBER_RE.test(e)) return e;
  if (e.length >= 2 && (e[0] === '"' || e[0] === "'") && e[e.length - 1] === e[0]) return e;
  const head = e.match(IDENT_RE); if (!head) return 'undefined';
  let out = scope.has(head[0]) ? head[0] : `v.${head[0]}`; let i = head[0].length;
  while (i < e.length) {
    if (e[i] === '.') { const m = e.slice(i + 1).match(IDENT_RE) || e.slice(i + 1).match(/^\d+/); if (!m) return 'undefined'; out += /^\d/.test(m[0]) ? `?.[${m[0]}]` : `?.${m[0]}`; i += 1 + m[0].length; }
    else if (e[i] === '[') { let d = 1, j = i + 1; while (j < e.length && d > 0) { if (e[j] === '[') d++; else if (e[j] === ']') { d--; if (d === 0) break; } j++; } if (d !== 0) return 'undefined'; out += `?.[${compileExpr(e.slice(i + 1, j), scope)}]`; i = j + 1; }
    else return 'undefined';
  }
  return out;
}

const WHOLE = /^\s*\{\{([\s\S]+?)\}\}\s*$/; const PARTS = /\{\{([\s\S]+?)\}\}/g;
function attrValue(raw, scope) {   // → { kind: 'static'|'expr', js }
  const whole = raw.match(WHOLE);
  if (whole) return { kind: 'expr', js: compileExpr(whole[1], scope) };
  if (!raw.includes('{{')) return { kind: 'static', js: raw };
  const parts = raw.split(PARTS);
  return { kind: 'expr', js: '`' + parts.map((s, i) => (i & 1) ? `\${(${compileExpr(s, scope)}) ?? ''}` : s.replace(/`/g, '\\`')).join('') + '`' };
}
function importantify(css) {
  const decls = []; let start = 0, depth = 0, quote = '';
  for (let i = 0; i < css.length; i++) { const c = css[i]; if (quote) { if (c === '\\') i++; else if (c === quote) quote = ''; } else if (c === '"' || c === "'") quote = c; else if (c === '(') depth++; else if (c === ')') depth--; else if (c === ';' && depth === 0) { decls.push(css.slice(start, i)); start = i + 1; } }
  decls.push(css.slice(start));
  return decls.map((d) => d.trim()).filter(Boolean).map((d) => /!important$/i.test(d) ? d : `${d} !important`).join(';');
}

export function convert(templateHtml) {
  const doc = parseDocument(templateHtml, { lowerCaseTags: false, lowerCaseAttributeNames: false, recognizeSelfClosing: true, decodeEntities: true });
  const pseudo = new Map(); const rules = [];
  const pseudoClass = (kind, css) => { const k = `${kind}|${css}`; if (!pseudo.has(k)) { const cls = 'sch' + pseudo.size.toString(36); pseudo.set(k, cls); const pe = kind === 'before' || kind === 'after'; rules.push(`.${cls}${pe ? '::' : ':'}${kind}{${pe ? css : importantify(css)}}`); } return pseudo.get(k); };
  const text = (t, scope) => t.split(PARTS).map((s, i) => (i & 1) ? `<span v-if="__s(${compileExpr(s, scope)}) !== null" class="sc-interp">{{ __s(${compileExpr(s, scope)}) }}</span>` : esc(s)).join('');
  const element = (el, scope) => {
    const tag = el.name; const a = el.attribs;
    if (tag === 'sc-if') return `<template v-if="${escAttr(compileExpr(a.value.match(WHOLE)?.[1] ?? a.value, scope))}">${kids(el, scope)}</template>`;
    if (tag === 'sc-for') { const alias = a.as || 'item'; const inner = new Set([...scope, alias, '$index']); return `<template v-for="(${alias}, $index) in __arr(${escAttr(compileExpr(a.list.match(WHOLE)?.[1] ?? a.list, scope))})" :key="$index">${kids(el, inner)}</template>`; }
    let out = tag; const attrs = []; let classStatic = null, classExpr = null; const pseudos = [];
    if (tag === 'x-import') out = COMPONENTS[a.component]; else if (tag === 'image-slot') out = COMPONENTS['image-slot'];
    if (!out) throw new Error(`unknown x-import component ${a.component}`);
    for (const [name, raw] of Object.entries(a)) {
      if (name.startsWith('hint-') || name === 'sc-name' || name === 'data-dc-tpl' || (tag === 'x-import' && (name === 'component' || name === 'from'))) continue;
      if (name.startsWith('style-')) { pseudos.push(pseudoClass(name.slice(6), raw)); continue; }
      if (name in EVENTS || name === 'onChange') {
        const js = compileExpr(raw.match(WHOLE)?.[1] ?? raw, scope);
        const ev = name === 'onChange' ? ((tag === 'select' || (tag === 'input' && /^(checkbox|radio)$/i.test(a.type || ''))) ? 'change' : 'input') : EVENTS[name];
        attrs.push(`@${ev}="${escAttr(js)}"`); continue;
      }
      const v = attrValue(raw, scope);
      if (name === 'class') { if (v.kind === 'static') classStatic = v.js; else classExpr = v.js; continue; }
      if (v.kind === 'static') attrs.push(raw === '' ? name : `${name}="${escAttr(raw.replace(/^(assets|ds)\//, '/$1/'))}"`);   // Global Constraint (a): the design's relative public paths become absolute
      else if (name === 'value') attrs.push(`:value="${escAttr(`(${v.js}) ?? ''`)}"`);
      else if (name === 'checked') attrs.push(`:checked="${escAttr(`(${v.js}) ?? false`)}"`);
      else attrs.push(`:${name}="${escAttr(v.js)}"`);
    }
    if (classExpr) attrs.unshift(`:class="${escAttr(pseudos.length ? `[${classExpr}, ${pseudos.map(jsStr).join(', ')}]` : classExpr)}"`);
    else if (classStatic !== null || pseudos.length) attrs.unshift(`class="${escAttr([classStatic, ...pseudos].filter(Boolean).join(' '))}"`);
    const open = `<${out}${attrs.length ? ' ' + attrs.join(' ') : ''}>`;
    return VOID.has(tag) ? open : `${open}${kids(el, scope)}</${out}>`;
  };
  const kids = (node, scope) => node.children.map((c) => c.type === 'text' ? text(c.data, scope) : c.type === 'tag' || c.type === 'script' || c.type === 'style' ? element(c, scope) : '').join('');
  return { template: kids(doc, new Set()), pseudoCss: rules.map((r) => r + '\n').join('') };
}

export function buildAppVue(template, setupJs, pseudoCssImport) {
  return `<!-- GENERATED by frontend/scripts/convert-dc.mjs from docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html — do not edit; run \`npm run gen:app\` -->\n<template>\n${template}\n</template>\n\n<script setup>\nimport '${pseudoCssImport}';\n${setupJs}</script>\n`;
}

if (fileURLToPath(import.meta.url) === resolve(process.argv[1] ?? '')) {   // path comparison, not URL string: the repo path contains a space
  const [dc, setup, outVue, outCss] = process.argv.slice(2);
  const { template, pseudoCss } = convert(extractTemplate(readFileSync(dc, 'utf8')));
  writeFileSync(outVue, buildAppVue(template, readFileSync(setup, 'utf8'), './generated/pseudo.css'));
  writeFileSync(outCss, pseudoCss);
  console.log(`wrote ${outVue} (${template.length} chars) and ${outCss} (${pseudoCss.split('\n').length - 1} rules)`);
}
```
`package.json`: `"gen:app": "node scripts/convert-dc.mjs ../docs/design-reference/design_handoff_practice_match_v2/'Practice Match V2.dc.html' src/app.setup.js src/App.vue src/generated/pseudo.css"`.

- [ ] **Step 4: Run to verify passing** — `npx vitest run tests/convert-dc.test.ts` → all pass; adjust nothing in the tests — if an expectation and the runtime disagree, the runtime (support.js) wins and the test is corrected to the runtime's rule with a comment citing the line.

- [ ] **Step 5: Commit** — `feat(gen): convert-dc transpiler — design template to Vue, runtime-faithful (spans, pseudo-classes, events, if/for, imports)`.

---

### Task 4b: Generate `App.vue` from the design; hand-maintained setup script; drift test; retire `hover.js`

**Files:**
- Create: `frontend/src/app.setup.js` (the `<script setup>` body, moved from `App.vue` — byte-identical logic plus the three additions below), `frontend/src/generated/pseudo.css` (generated), `frontend/tests/app-generated.test.ts`
- Modify: `frontend/src/App.vue` (now generated), `frontend/vite.config.ts` (`vue({ template: { compilerOptions: { whitespace: 'preserve' } } })`), `frontend/src/logic.test.ts` (unchanged expectations — `logic.js` is untouched), `frontend/src/map/boundary.test.ts` (unchanged)
- Delete: `frontend/src/directives/hover.js` (hover is now the generated pseudo-class stylesheet — exactly what the runtime does)

**Interfaces:**
- `app.setup.js` exports nothing; it defines for the template: `v = computed(() => ({ ...props, ...c.renderVals() }))` (the runtime merges user props into vals, `support.js` l.1085), `__s = (x) => (x == null || typeof x === 'boolean' || typeof x === 'object') ? null : String(x)`, `__arr = (x) => (Array.isArray(x) ? x : [])`, and the component imports `ListingsMap`, `MarketMapView`, `ImageSlot` — no `vHover`.

- [ ] **Step 1: Failing drift test**

`frontend/tests/app-generated.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildAppVue, convert, extractTemplate } from '../scripts/convert-dc.mjs';

const ROOT = join(import.meta.dirname, '..');
const DC = join(ROOT, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v2', 'Practice Match V2.dc.html');

describe('App.vue is generated from the design', () => {
  it('regenerating yields byte-identical App.vue and pseudo.css (no hand edits survive)', () => {
    const { template, pseudoCss } = convert(extractTemplate(readFileSync(DC, 'utf8')));
    expect(readFileSync(join(ROOT, 'src/App.vue'), 'utf8')).toBe(buildAppVue(template, readFileSync(join(ROOT, 'src/app.setup.js'), 'utf8'), './generated/pseudo.css'));
    expect(readFileSync(join(ROOT, 'src/generated/pseudo.css'), 'utf8')).toBe(pseudoCss);
  });
  it('the generated template compiles under the Vue SFC compiler with preserved whitespace', async () => {
    const { parse, compileTemplate } = await import('@vue/compiler-sfc');
    const { descriptor, errors } = parse(readFileSync(join(ROOT, 'src/App.vue'), 'utf8'));
    expect(errors).toEqual([]);
    const out = compileTemplate({ source: descriptor.template!.content, filename: 'App.vue', id: 'app', compilerOptions: { whitespace: 'preserve' } });
    expect(out.errors).toEqual([]);
  });
  it('retired the JS hover directive: no v-hover, no hover.js', () => {
    expect(readFileSync(join(ROOT, 'src/App.vue'), 'utf8')).not.toContain('v-hover');
    expect(() => readFileSync(join(ROOT, 'src/directives/hover.js'))).toThrow();
  });
});
```
Run: `npx vitest run tests/app-generated.test.ts` → **FAIL** (App.vue is the hand conversion; hover.js exists).

- [ ] **Step 2: Move the script, generate, wire**

`frontend/src/app.setup.js` = the current `<script setup>` body of `App.vue` with: the `vHover` import removed; `import ImageSlot from './components/ImageSlot.vue'` kept; `const v = computed(() => ({ ...props, ...c.renderVals() }));` replacing `computed(() => c.renderVals())`; and `const __s = …; const __arr = …;` added (as in Interfaces). Then `npm run gen:app`; `git rm frontend/src/directives/hover.js`; vite config `vue({ template: { compilerOptions: { whitespace: 'preserve' } } })`.

- [ ] **Step 3: Run — GREEN** — `npx vitest run` (all suites incl. Task 1c's `logic.test.ts` unchanged), `npx vue-tsc --noEmit`, `npm run build`; `npx playwright test --project=reference` still 25/25. The app project is measured (expect a large jump from 4/25) and recorded — parity is finished in Task 4e.

- [ ] **Step 4: Commit** — `feat(frontend): App.vue generated from the design template; hover as generated pseudo-classes; setup script extracted`.

---

### Task 4c: `ImageSlot.vue` — parity port of the design's `<image-slot>` element (John's ruling D)

**Files:**
- Modify: `frontend/src/components/ImageSlot.vue`
- Create: `frontend/src/components/image-slot.css` (the element's stylesheet text, copied from `image-slot.js`), `frontend/src/components/ImageSlot.test.ts`

**Interfaces:**
- Props: `id: string`, `shape: 'rect' | 'rounded' | 'circle' | 'pill'` (default `rounded`), `radius?: number` (default 12), `src?: string`, `placeholder?: string` (default `'Drop an image'`), `fit?: string`, `credit?: string`, `creditHref?: string` — the element's `observedAttributes` (`image-slot.js` l.440–442).
- Renders an **open shadow root** (`attachShadow({ mode: 'open' })` in `onMounted`) containing exactly the element's `_frame`/`_ring`/glyph/caption structure and its stylesheet, with the read-only branch of `_render()` (`data-editable` false: the `_sub` controls hidden) — the source is `docs/design-reference/design_handoff_practice_match_v2/image-slot.js` `_render()` (l.~840–940) and the CSS text the constructor injects (l.~497–560). `shape=rect` → no border radius; `rounded` → `radius`px; `circle` → 50 %; `pill` → 9999px; `src` present → `<img>` with `object-fit` per `fit`; absent → dashed ring + glyph + caption `placeholder`.

- [ ] **Step 1: Failing tests** — `ImageSlot.test.ts` (jsdom, `@vue/test-utils` — install if absent): mounts with `{ id: 'x', shape: 'rect', placeholder: 'Practice exterior' }` → `wrapper.element.shadowRoot` exists, contains a frame element with `border-radius: ''`, a visible ring, a caption whose text is `Practice exterior`, no `<img>`; with `src` → an `<img src>` inside the frame and the ring hidden; `shape: 'circle'` → frame `border-radius: 50%`; the shadow stylesheet text equals `image-slot.css`. Run → **FAIL** (current component renders a flat band in light DOM).
- [ ] **Step 2: Port** — copy the stylesheet text verbatim into `image-slot.css` (imported with `?raw`), build the shadow tree in `onMounted`, re-render on prop change (`watch`), never include the editor controls or the sidecar/store logic (reference-runtime only per the handoff README).
- [ ] **Step 3: Run — GREEN** — `npx vitest run src/components/ImageSlot.test.ts`, full suite, `npm run build`.
- [ ] **Step 4: Commit** — `feat(frontend): ImageSlot parity port of the design's image-slot element (shadow DOM, ring, glyph, caption)`.

---

### Task 4d: DOM oracle — element-by-element comparison of app vs design for every state

**Files:**
- Create: `frontend/tests/dom.ts` (serializer + normaliser), `frontend/tests/reference-dom.spec.ts` (writes `dom-snapshots/<state>.json` from the design, git-ignored), `frontend/tests/dom.spec.ts` (compares the app), `frontend/tests/dom.test.ts` (unit tests of the normaliser)
- Modify: `frontend/tests/playwright.config.ts` (`reference` project also matches `reference-dom.spec.ts`; `app` project also matches `dom.spec.ts`), `.gitignore` (`frontend/tests/dom-snapshots/`)

**Interfaces:**
- `serialize(page): Promise<DomNode>` — evaluates in the page: root = `document.querySelector('div[style*="min-height: 100vh"]')`; for each element: `{ tag, attrs: sorted [name, value] pairs excluding data-dc-tpl, data-reactroot, data-v-*, key, class and style (class and style have their own fields — ratified by John 2026-09-05); class: sorted tokens with /^sc[hp][0-9a-z]+$/ → '<pseudo>'; style: sorted declarations from el.style (property → value); props: sorted [name, value] pairs of the live `el.value` on `input`/`select`/`textarea` and `el.checked` on `input[type=checkbox|radio]` only (rule C, narrowed in fix round 2 — `selected` belongs to `<option>` and is not read); children }`; style declarations carry `!important` as `[prop, value + ' !important']` when `getPropertyPriority(prop) === 'important'` (fix round 2); text nodes → `{ text }` with `sc-interp` spans kept; **whitespace-only text nodes are dropped from child lists on both targets** (rule W; "whitespace" is exactly the compiler's set — space, tab, LF, CR, FF (`/^[ \t\n\r\f]*$/`) or empty; a non-breaking space is content and is kept — fix round 2); comment nodes and any other non-element, non-text node are dropped (ratified 2026-09-05); `.leaflet-container` → `{ tag: 'div', leaflet: true }` (maps are covered by pixels); `el.shadowRoot` → child `{ shadow: [...] }` inserted as the first child (ratified 2026-09-05).
- **Oracle normalisation rules accepted by John on 2026-09-05 (after the 4d review; built test-first in fix round 1):** **W** — whitespace-only text nodes are dropped: Vue's template compiler removes leading/trailing whitespace-only text nodes and condenses interior ones to `' '` even under `whitespace: 'preserve'` (`@vue/compiler-core` `condenseWhitespace`), while the design's React runtime renders every source whitespace node, so no transpiler output can match them; **B** — on the design side, `src`/`href` values beginning `assets/` or `ds/` are read as `/assets/`, `/ds/` (the plan's mandated path rewrite, allowed edit (a)); any other path difference is still reported; **C** — on `input`, `select`, `textarea` the `value`/`checked`/`selected` attributes are excluded from `attrs` (Vue mirrors form state onto the attribute — `@vue/runtime-dom` `patchProp`; React sets only the property) and the live properties are compared instead via `props`, so a wrong selected option is still reported. Evidence: with W+B+C simulated offline over the 4d snapshots, all 25 states align structurally and 17/25 are identical; the remaining 8 differ only at `image-slot` hosts and the missing `div.sc-host-x` x-import wrapper — both Task 4e's scope. Tag names are compared strictly — the oracle never normalises a host tag: the design renders `<image-slot>`, so the app must too (Task 4e makes `ImageSlot.vue`'s root an `<image-slot>` element). `diff(a: DomNode, b: DomNode): string[]` → paths like `div[0]/div[2]/span[1]: child[0] text "Approved buyer" ≠ "Approved buyer "` (text and node-kind mismatches are reported at the parent's path with the child index — fix round 2 added the index to text lines); a tag mismatch reports `tag a ≠ b` and still compares that node's own attrs/class/style/props, skipping only its children (fix round 2); a shadow-root child-count mismatch is reported as `<path>/shadow: child count N ≠ M` before recursing (reviewer finding, fix round 1 — `compareChildren` alone only walks `min(N, M)`).

- [ ] **Step 1: Failing tests** — `dom.test.ts` (node): `diff` reports the first differing attribute, class-token set, style declaration, text, child count, **shadow child count** and shadow content with paths, and a differing `props` entry (`select[1]: prop value "Austin, TX" ≠ "Any"`); `normalise` maps `scp3` and `sch3` both to `<pseudo>`, sorts attributes and style declarations, **drops whitespace-only and empty text nodes from `children` and `shadow`**, rewrites design-side `src`/`href` `assets/`→`/assets/` and `ds/`→`/ds/` (and leaves `/assets/…` and any other value untouched), and recurses into element `children` (a nested `scp…` class is substituted). `dom.spec.ts` on the app: for each `SCREENS` state, `expect(diff(referenceSnapshot(state), await serialize(page))).toEqual([])`. Run: `npx vitest run tests/dom.test.ts` → **FAIL** (module missing); `npx playwright test --project=reference` → writes snapshots; `--project=app` `dom.spec.ts` → FAIL on divergent states (that is the triage list for 4e).
- [ ] **Step 2: Implement** the serializer/normaliser/diff and the two specs (they reuse `SCREENS`, `prepare`, `settle` from the harness exactly as `visual.spec.ts` does).
- [ ] **Step 3: Run — GREEN for the unit tests; record the per-state DOM diffs** in the report (they are inputs to 4e, not defects of 4d).
- [ ] **Step 4: Commit** — `test(dom): DOM oracle — normalised element-by-element comparison of app vs design per state`.

**Fix round 1 (2026-09-05, after review — John's rulings):**
- [ ] Report a shadow-root child-count mismatch (`dom.ts` shadow branches in `compareChild` and `diff`): RED — unit test with unequal shadow arrays expects `…/shadow: child count 2 ≠ 1`; GREEN — emit the line before recursing.
- [ ] Rule W: RED — `normalise` test: `children: [{text:'\n  '}, el, {text:''}, el2]` → `[el, el2]`; same for `shadow`. GREEN in `normalise`.
- [ ] Rule B: RED — `normalise({ …, attrs: [['src','assets/x.png']] }, { design: true })` → `'/assets/x.png'`; app side unchanged. GREEN. (The reference spec passes `design: true`; the app spec does not — `serialize(page, { design })` or an equivalent flag on `normalise`.)
- [ ] Rule C: RED — the in-page walk records `props` for `input`/`select`/`textarea` and excludes `value`/`checked`/`selected` from `attrs`; `diff` reports `select[1]: prop value "Austin, TX" ≠ "Any"`. GREEN.
- [ ] Re-run `--project=reference` (snapshots are regenerated with the new shape) then `--project=app`; record the per-state residual diffs in the report (expected: 17/25 identical; the rest differ only at `image-slot` hosts and the `div.sc-host-x` wrapper — Task 4e's inputs).
- [ ] Commit — `test(dom): oracle rules W/B/C (whitespace-only text, design asset paths, live form props) and shadow child-count check`.

**Fix round 2 (2026-09-05, cleanup — John's ruling "clean up all ten now"; files: `frontend/tests/dom.ts`, `dom.test.ts`, `dom.spec.ts` only; every item test-first; one commit):**
- [ ] **Whitespace = the compiler's set.** `isWhitespaceOnlyText` uses `/^[ \t\n\r\f]*$/` (Vue `compiler-core` `isWhitespace`: char codes 32, 9, 10, 13, 12). RED: `normalise` keeps a `{ text: '\u00a0' }` child and drops `{ text: ' \n\t' }` and `{ text: '' }`.
- [ ] **Rule C narrowed.** `props` = `value` on `input`/`select`/`textarea`; `checked` only on `input` with `type` `checkbox` or `radio`; `selected` is not read. RED (jsdom): a walked `<input type="text" value="a">` yields `props [['value','a']]` only; `<input type="checkbox" checked>` yields `[['checked','true'],['value','on']]`; `<select>` yields only `value`.
- [ ] **One walk, unit-tested.** Extract the in-page walk to an exported, self-contained `walkPage(arg: { rootSelector: string; formTags: string[] }): RawNode | null` (no reference to module scope — Playwright stringifies it); `serialize` calls `page.evaluate(walkPage, { rootSelector: ROOT_SELECTOR, formTags: [...FORM_TAGS] })`, so `FORM_TAGS` is defined once. `dom.walk.test.ts` (or a `// @vitest-environment jsdom` block) builds fixtures with `document.body.innerHTML` + `attachShadow` and calls `walkPage` directly. RED: the import fails (not exported); then each walk assertion.
- [ ] **`!important` recorded.** Style pairs are `[prop, value + ' !important']` when `decl.getPropertyPriority(prop) === 'important'`. RED (jsdom): `<div style="color: red !important">` → `[['color', 'red !important']]`; `<div style="color: red">` → `[['color', 'red']]`.
- [ ] **Tag mismatch keeps comparing the node.** After `path: tag a ≠ b`, attrs/class/style/props of that node are still compared; only children are skipped. RED: fixture with `image-slot` vs `div` AND a differing `placeholder` attr → both lines, no child lines.
- [ ] **Indexed text lines.** `compareChild`'s text case reports `${displayPath}: child[${index}] text "a" ≠ "b"`. RED: the exact-string test becomes `div[0]/div[2]/span[1]: child[0] text "Approved buyer" ≠ "Approved buyer "`; two differing text children at indexes 0 and 2 produce two distinguishable lines.
- [ ] **Missing snapshot names the fix.** Move the snapshot reader into `dom.ts` as `readReferenceSnapshot(dir: string, name: string): DomNode`; when the file is missing it throws `Missing DOM snapshot "<name>" in <dir> — run: npx playwright test --config=tests/playwright.config.ts --project=reference`. `dom.spec.ts` calls it. RED: unit test with a temp dir expects that message.
- [ ] **Recursion into element children asserted.** RED→GREEN test: a nested child with class `scp4` inside `children` is normalised to `<pseudo>` (the test is expected to pass once written only if the branch already works — write it, run it, and if it passes immediately, break the branch deliberately once to prove the test bites, then restore).
- [ ] **W + shadow + props combined.** RED→GREEN test: a `{ shadow: [{ text: '\n' }, <input with props>, { text: '' }] }` normalises to the single input with its `props` intact (same immediate-pass rule as above).
- [ ] Re-run `--project=reference` (snapshot shape changes: `checked` gone from text inputs, `!important` suffixes) then `--project=app dom.spec.ts`; record the per-state result (the residual shapes are Task 4e's unless 4e has already landed, in which case expect 25/25).
- [ ] Commit — `test(dom): oracle cleanup — compiler whitespace set, narrowed form props, single unit-tested walk, !important, tag-mismatch attrs, indexed text lines, snapshot hint`.

---

### Task 4e: Parity to GREEN — DOM oracle + pixel gate on all 25 states, map effect order, `_leaflet_pos`, smoke

**Files (the only ones that may change; anything else → `NEEDS_CONTEXT`):**
- `frontend/scripts/convert-dc.mjs` + `tests/convert-dc.test.ts` (a rule the transpiler got wrong — fix the rule, add the golden test, regenerate), `frontend/src/app.setup.js`, `frontend/src/components/ImageSlot.vue` + its css/test (incl. making the shadow host an `<image-slot>` element so the DOM oracle's tag comparison matches the design), `frontend/vite.config.ts` (**only** `vue({ template: { compilerOptions: { isCustomElement: (tag) => tag === 'image-slot' } } })` alongside the existing `whitespace: 'preserve'`; `tests/app-generated.test.ts` passes the same option to `compileTemplate`), `frontend/src/components/MarketMapView.vue` and `ListingsMap.vue` (**effect order only**: mirror `MarketMap.jsx`'s six `useEffect`s / `AustinMap.jsx`'s four in declaration order — one ordered watcher that redraws overlay then pins, as React runs effects in declaration order on every commit), `frontend/src/map/engines/leaflet.ts` + `leaflet.test.ts` (John's ruling F: `mount()`/`show()` timers are tracked and cleared in `destroy()`; test: destroy before the 60/80 ms timers fire → `invalidateSize` never called), `frontend/src/styles/global.css`, `tokens.css`, `frontend/tests/harness.ts`, `screens.ts`, `playwright.config.ts`, `smoke.spec.ts`.

- [ ] **Step 1: Triage from the oracle** — run `npx playwright test --project=reference` then `--project=app`; for every state list: DOM diff paths, pixel diff count, cause, which allowed file fixes it. Anything outside the allowed files or the named causes → stop with `NEEDS_CONTEXT`.
**Known residuals from the 4d oracle (controller's offline simulation over the 4d snapshots, 2026-09-05 — confirm in Step 1, do not assume):** with oracle rules W/B/C in place, all 25 states align structurally and 17/25 are DOM-identical; the 8 others (`browse-listings`, `browse-market`, `browse-market-layers-closed`, `browse-market-panel`, `detail`, `interest-modal`, `header-1000`, `header-1100`) differ only in two shapes: (i) **x-import host wrapper** — the design runtime (`support.js` `walkComponent`) renders every `<x-import>` inside `<div class="sc-host-x" style="display: contents">` (`hostPositionStyle` keeps only positional properties from an `x-import` `style` attribute; the three x-imports in this template carry none, so the host style is exactly `display: contents`; `data-dc-tpl` is dropped by the oracle). The transpiler emits the component bare, so the app is one wrapper level short (`child count 1 ≠ 2` at the map container's parent, `class ['sc-host-x'] ≠ []`, `child[0] element ≠ leaflet`). Fix in `convert-dc.mjs` with a golden test: wrap each `x-import` component tag in that host `div`; check the design's injected CSS for any `.sc-host-x` rule before assuming pixels are unchanged. (ii) **`image-slot` host** — `tag image-slot ≠ div`; host attrs `placeholder`, `shape`, `src` missing on the app's host (they are the element's own attributes in the design and must be on the host, not only props); `shadow: child count 6 ≠ 3` (the design's shadow root renders six nodes, the port renders three — port the shadow content exactly from `image-slot.js`); `shadow/style[0]` text differs (the port carried a 2903-byte subset of the design's 4524-byte stylesheet; the design's CSS text is the JS `const stylesheet = …` concatenation verbatim — the port must carry the identical string); after the host tag matches, the oracle also exposes `shadow/div[3]/img[0]: attr src` — `image-slot.js` `_render` mirrors the photo URL onto the reframe ghost, so the port does too (a filled slot requests its image twice, as the design does — *accepted by John 2026-09-05 as a fifth residual shape*). Everything else — `select`/`textarea` state, asset paths, whitespace — is already equal under the accepted oracle rules; any residual of another shape is a `NEEDS_CONTEXT` stop.
- [ ] **Step 2: Fix at the cause, regenerate, re-run** until `dom.spec.ts` 25/25 and `visual.spec.ts` 25/25 at `maxDiffPixels: 0`. The `_leaflet_pos` fix is test-first in `engines/leaflet.test.ts` (RED: a fake-timer run past 80 ms after `destroy()` calls `invalidateSize` on the removed map).
- [ ] **Step 3: Smoke** — `smoke.spec.ts` (committed in 5a5ea8c) 11/11 incl. the first-map-paint budget and the no-`pageerror` route walk.
- [ ] **Step 4: Full gate** — `npx vitest run && npx vue-tsc --noEmit && npm run build && npx playwright test` → all green; `npm run gen:app` leaves the tree unchanged (drift test).
- [ ] **Step 5: Commit** — `feat(frontend): pixel and DOM parity with the approved design on all 25 states; map effect order; leaflet timers cleared on destroy`.

**Fix round 1 (2026-09-05, after review — John's rulings; files: `frontend/src/components/ImageSlot.vue` + `ImageSlot.test.ts`, `frontend/src/components/MarketMapView.vue` + a new `MarketMapView.test.ts`, `frontend/src/map/engines/leaflet.test.ts`, `frontend/scripts/convert-dc.mjs` + `tests/convert-dc.test.ts`; every item test-first; one commit):**
- [ ] **Popover fallback (Important, ruling: additive).** The ported editor chrome (`.spill` handles, `.ctl` Replace/Edit buttons) is hidden only by the UA's closed-popover `display:none`; below the Popover floor (Chrome 114 / Safari 17 / Firefox 125; our Vite 5 default target is Chrome 87 / Safari 14 / Firefox 78) it paints and is focusable. Fix in `ImageSlot.vue` `onMounted`: a second `CSSStyleSheet` attached via `root.adoptedStyleSheets = [sheet]` whose only rule is `@supports not selector(:popover-open) { .spill, .ctl { display: none } }` — no shadow child is added (the oracle's shadow child count stays 6; pixels in Chromium unchanged). RED (jsdom): `shadowRoot.adoptedStyleSheets` contains one sheet whose text includes that rule and `shadowRoot.childNodes.length` is still 6 (if jsdom lacks `adoptedStyleSheets`/`CSSStyleSheet()`, feature-detect and assert the branch via a stubbed constructor — say so in the report).
- [ ] **Ghost `src` (brief-deviation → accepted).** Keep `ImageSlot.vue`'s reframe-ghost `src` mirroring; no code change.
- [ ] **`designStylesheet()` guard (Minor #3).** In `ImageSlot.test.ts`, hoist the end-marker `indexOf` into its own variable and assert it is `>= 0` so a missing marker fails with `stylesheet literal not found`, not a bare `SyntaxError`. RED: temporarily point the marker at a non-existent string → the helper throws the named error.
- [ ] **Merged-watcher comment (Minor #4).** Add one sentence to the rationale comment in `MarketMapView.vue`: the single watcher deliberately redraws the overlay on `practices`/`activeId` changes too (a superset of `MarketMap.jsx`'s effect 5 deps) so overlay-before-pins order is guaranteed. Comment only.
- [ ] **Unit guards for order and cleanup (Minor #5).** New `frontend/src/components/MarketMapView.test.ts` (jsdom + the stub engine from `frontend/src/map/testing/leaflet-stub.ts`, injected the way the component already obtains its engine): mount with practices+communities, change `practices` only, assert the engine's recorded call order has the overlay redraw before the pins redraw. RED first (assert the reverse order fails). In `leaflet.test.ts`: after `destroy()`, the engine's pending-timer set is empty (expose it read-only for tests or assert via the stub's clearTimeout count).
- [ ] **Transpiler guard order (Minor #6).** In `convert-dc.mjs`, check unknown component before the `x-import`-with-`style` throw. RED: golden test — an unknown component carrying a `style` attribute reports `unknown x-import component …`, not the style error.
- [ ] `npx vitest run && npx vue-tsc --noEmit && npm run gen:app` (no drift) → green; then `npx playwright test --config=tests/playwright.config.ts --project=app` — visual 25/25, dom 25/25, smoke 11/11 unchanged.
- [ ] Commit — `fix(frontend): image-slot chrome hidden without Popover support; order/cleanup unit guards; test and transpiler guard fixes`.

**Fix round 2 (2026-09-05 — John's ruling: replace the stylesheet fallback with a feature-detected branch; files: `frontend/src/components/ImageSlot.vue` + `ImageSlot.test.ts` only; one commit):**
- [ ] **Why:** constructable stylesheets (`new CSSStyleSheet()` / `adoptedStyleSheets`) are absent on Safari < 16.4 and Firefox < 101, so the fix-round-1 fallback covered Chrome/Edge 87–113 only; on the other sub-floor engines the constructor threw and the chrome still painted.
- [ ] **Remove** `POPOVER_FALLBACK` and the `adoptedStyleSheets` attach (and its test).
- [ ] **Add** in `onMounted`, after the shadow content is rendered: `if (!('popover' in HTMLElement.prototype)) { for (const el of root.querySelectorAll<HTMLElement>('.spill, .ctl')) el.style.display = 'none'; }` — on every engine with the Popover API (all gate browsers) the branch is dead, so the DOM oracle (`el.style` declarations, attrs, shadow child count) and the pixels are untouched; on every engine below the floor the chrome is hidden with a plain inline style, no stylesheet API needed.
- [ ] **RED (jsdom has no Popover API):** after mount, both `.spill` and `.ctl` have `style.display === 'none'` and `shadowRoot.childNodes.length` is still 6; a second test defines `popover` on `HTMLElement.prototype` (`Object.defineProperty(..., { value: null, configurable: true })`, deleted in `afterEach`) before mounting and asserts neither element has an inline `display`. GREEN with the branch.
- [ ] **Full gate:** `npx vitest run && npx vue-tsc --noEmit && npm run gen:app` (no drift) → `--project=reference` then `--project=app` → visual 25/25, dom 25/25, smoke 11/11.
- [ ] Commit — `fix(frontend): image-slot chrome hidden by a Popover feature check on every engine below the floor`.

**Fix round 3 (2026-09-05 — John's ruling after the zero-gap audit: remove the design tool's image editor from the port; files: `frontend/src/components/ImageSlot.vue` + `ImageSlot.test.ts`, `frontend/tests/dom.ts` + `dom.test.ts` (+ `dom.walk.test.ts` only if the walk changes), and — for the re-review's minor follow-ups on the audit commits, cleaned in the same round per John's standing preference — `frontend/src/map/engines/leaflet.ts` + `leaflet.test.ts`; one commit):**
- [ ] **Why.** The design's own stylesheet sets `.ctl{display:flex}`, which beats the UA closed-popover rule, so the Replace/Edit buttons are keyboard-focusable and announced by assistive technology in every browser (12 phantom tab stops on the Listing screen; WCAG 2.1 SC 2.4.3, 4.1.2). The design has the same defect. The editor exists only for the design tool: unpermissioned, gated on `data-editable`, which the app never sets. The product feature is **permissioned photo management** in Wave 2b (see `docs/decisions/2026-09-05-image-slot-editor-removed.md`).
- [ ] **Remove from the port's shadow template:** the `.spill` reframe overlay (with its `.ghost` and `.handle` children), the `.ctl` strip, and the hidden `<input type="file">`; delete their handlers, the reframe/ghost `src` mirroring, and the Popover feature-check branch (nothing is left to hide). `image-slot.css` stays byte-for-byte (its editor rules are simply unused). RED: `ImageSlot.test.ts` asserts the shadow root contains no `.spill`, no `.ctl`, no `input[type=file]`, and that no element inside it is focusable (`tabIndex >= 0` count 0); keep the stylesheet byte-for-byte test; remove the Popover-branch tests.
- [ ] **Oracle rule E (ratified by John 2026-09-05):** inside an `image-slot` shadow root, the **design-side** nodes `.spill`, `.ctl` and `input[type=file]` are dropped before comparison (`normalise`, `design: true` only). The app side is never filtered — an app-side occurrence is reported. RED: a design shadow of six nodes normalises to three; an app shadow containing a `.ctl` still reports it.
- [ ] **Gates:** `npx vitest run && npx vue-tsc --noEmit && npm run gen:app` (no drift) → `--project=reference` (snapshots regenerated: the design's editor nodes disappear from every image-slot shadow) → `--project=app`: visual 25/25 (the chrome was invisible), dom 25/25, smoke 11/11. Prove the accessibility fix end-to-end: a smoke or dom-level check that no element inside any `image-slot` shadow root on the Listing screen is focusable.
- [ ] **Re-review minors on the audit commits (same round):** (i) `leaflet.ts` — make every public method a no-op after `destroy()` (`setView`, `zoomIn/Out`, `clear`, `setBase`, `fitBounds`, `onMove`, `marker`, `circle` currently reach the removed map), test-first with the stub: each called after destroy neither throws nor touches the stub map; (ii) `leaflet.test.ts` — the "drains the pending-timer set" test's second assertion is tautological under the early-return guard: re-point it to assert `timers` is empty after the first destroy (expose read-only for tests or observe via the stub) and fix its now-obsolete comment; (iii) `dom.test.ts:148-150` — the stale "Rule C" comment still describes the pre-narrowing behaviour; correct it. The sub-floor Playwright check for non-interactivity is moot once the chrome is removed. **Extended by John (2026-09-05, "close these gaps"): every minor from the audit re-review closes in this round** — (iv) `dom.ts` gains `summarise(lines, max = 40)` (first `max` lines + `… and K more (N total)`), used by `dom.spec.ts` as the failure message while `diff()` keeps returning every line (RED: unit tests for both branches); (v) `MarketMapView.test.ts` identifies the overlay/pins groups by the renderer role that filled them (drive-time circle radius / community dot / price pin) — *ratified by John 2026-09-05 in place of "by name": the group name is private to the engine and unobservable without editing the stub or the component* — not by construction order (RED: the index-keyed helper mislabels under a swapped order, the name-keyed one does not); (vi) `leaflet.ts` `mount()` re-checks `destroyed` after `await loadLeaflet()` and aborts without creating the map or scheduling timers (RED: deferred `loadLeaflet`, `destroy()` before it resolves → no map on the stub, zero timers, no throw). Not actionable in code, recorded in the report: the `a5d9a66` subject is superseded by the committed Listing-screen focusability check; the `8322c02` body wording lives in pushed history and is not rewritten. Files added to this round: `frontend/tests/dom.spec.ts`, `frontend/src/components/MarketMapView.test.ts`.
- [ ] Commit — `fix(frontend): remove the design tool's image editor from image-slot; oracle ignores the design's editor chrome (John's ruling)`.

**Fix round 4 (2026-09-05 — John: "close all three now"; files: `frontend/src/map/engines/leaflet.ts`, `leaflet.test.ts`, `frontend/tests/smoke.spec.ts`; one commit):**
- [ ] `destroy()` also clears `groups`, `zoomCtl` and `scaleCtl` so a re-mounted instance rebuilds them on the new map. RED (stub): mount → `group('pins')` → destroy → mount again → `clear('pins')`/`marker(...)` attach to the NEW map (the stub's second map records the layer; the first does not).
- [ ] `getZoom()` after `destroy()` returns `0` and touches no map — pinned by an explicit assertion (currently only inside `not.toThrow()`).
- [ ] Smoke Tab-walk positive counter: the Listing-screen keyboard gate records where each Tab press landed and asserts the walk visited at least one element outside any image-slot (so the loop demonstrably ran) while visiting none inside one. RED: temporarily make the walk return before pressing → the positive assertion fails.
- [ ] Gates: `npx vitest run && npx vue-tsc --noEmit` → green; `--project=app smoke.spec.ts` → 12/12. Commit — `test(frontend): engine teardown drops groups and controls; getZoom pinned after destroy; keyboard gate proves the walk ran`.

**Recorded rulings folded in:** A (hover) — solved by construction (generated pseudo-classes); B (`d.`→`v.d.`) — solved by construction (the transpiler resolves paths); C (watcher order) — 4e; D (ImageSlot) — 4c; E (interpolation spans) — the transpiler reproduces **every** span, superseding the "three spots" ruling in the stricter direction; F (`_leaflet_pos`) — 4e.

---

### Task 5: FastAPI skeleton — config (fail-fast), version, health endpoints, SPA serving

**Files:**
- Create: `pyproject.toml`, `app/__init__.py`, `app/config.py`, `app/version.py`, `app/checks.py`, `app/api/__init__.py`, `app/api/health.py`, `app/static.py`, `app/main.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_config.py`, `tests/test_versions.py`, `tests/test_health.py`, `tests/test_static.py`, `tests/perf/__init__.py`, `tests/perf/test_api_latency.py`; `poetry.lock` is committed with `pyproject.toml` (Task 7's Dockerfile needs it)

**Interfaces:**
- Produces: `settings: Settings` (`database_url`, `redis_url`, `environment`, `api_secret_key`, `allowed_origins`, `commit_sha`, `origins: list[str]`); `VERSION: str`; `async check_db(url) -> dict`, `async check_redis(url) -> dict`; `create_app(dist: Path | None = None) -> FastAPI`; module-level `app`.
- Consumes: `frontend/dist/` layout from Task 1 (`index.html`, `_app/`, `assets/`, `ds/`).

- [ ] **Step 1: Project file and environment**

`pyproject.toml`:
```toml
[project]
name = "practice-match"
version = "0.1.0"
description = "VIN Foundation veterinary practice marketplace — API and worker"
requires-python = ">=3.12,<3.13"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy[asyncio]>=2.0",
  "asyncpg>=0.30",
  "psycopg2-binary>=2.9",
  "celery[redis]>=5.4",
  "redis>=5.2",
  "pydantic-settings>=2.6",
  "httpx>=0.27",
  "structlog>=24.4",
  "greenlet>=3.0",  # explicit: SQLAlchemy's platform marker omits arm64 and Poetry 2.4.1 does not honour the asyncio-extra marker (John's ruling 2026-09-05)
]

[tool.poetry]
package-mode = false

[tool.poetry.group.dev.dependencies]
pytest = ">=8.3"
pytest-asyncio = ">=0.24"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["poetry-core>=2.0"]
build-backend = "poetry.core.masonry.api"
```

```bash
cd "/Users/johndean/Development/Practice Match"
poetry env use python3.12 && poetry install
mkdir -p app/api tests && touch app/__init__.py app/api/__init__.py tests/__init__.py
```

**Performance gate (policy §3; amended 2026-09-05 by John's ruling — in scope for Task 5):** `tests/perf/__init__.py` (empty) and `tests/perf/test_api_latency.py`, verbatim from `docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md` §5 (the `client` fixture comes from `tests/conftest.py`):
```python
import statistics
import time

import pytest

BUDGET_MS = {"/api/healthz": 20, "/": 15}   # Census B5 and Map engines M3/M4 extend this dict in their tasks


async def p95(client, path: str, n: int = 50) -> float:
    await client.get(path)  # warm-up
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = await client.get(path)
        samples.append((time.perf_counter() - t0) * 1000)
        assert r.status_code < 500, path
    return statistics.quantiles(samples, n=20)[18]


@pytest.mark.parametrize("path, budget", sorted(BUDGET_MS.items()))
async def test_p95_within_budget(client, path, budget):
    assert await p95(client, path) <= budget, f"{path} p95 over {budget} ms"
```
Run (after Step 5): `poetry run pytest tests/perf -q` → 2 passed. RED first: run it before `app/main.py` exists → `ModuleNotFoundError` from the conftest import.. RED: it fails with the app missing; GREEN after this task at both budgets.

- [ ] **Step 2: Failing tests — config fail-fast and version lockstep**

`tests/conftest.py` (env defaults must be set before any `app.*` import; ports 5433/6380 avoid a local Postgres/Redis):
```python
import os

os.environ.setdefault("DATABASE_URL", "postgresql://pm:pm_dev_pw@localhost:5433/practice_match")
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("API_SECRET_KEY", "test_only_secret_change_me")

from pathlib import Path  # noqa: E402  (env defaults must precede any app.* import)

import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    d = tmp_path / "dist"
    (d / "_app").mkdir(parents=True)
    (d / "assets" / "icons").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><div id=\"app\"></div>")
    (d / "_app" / "index-abc123.js").write_text("console.log(1)")
    (d / "assets" / "icons" / "pad-lock.svg").write_text("<svg/>")
    return d


@pytest.fixture
async def client(dist):
    from app.main import create_app  # imported here so this conftest loads before app.main exists (Steps 2-3)

    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url="http://test") as c:
        yield c
```
*(Amended 2026-09-05, John's ruling: `dist` and `client` live here so `tests/perf/` and `tests/test_static.py` share them; the lazy import keeps Steps 2–3 runnable before `app/main.py` exists.)*

`tests/test_config.py`:
```python
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_import_without(*missing: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in missing}
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run([sys.executable, "-c", "import app.config"], env=env, capture_output=True, text=True)


def test_missing_required_variable_exits_1_and_names_it():
    r = _run_import_without("DATABASE_URL")
    assert r.returncode == 1
    assert "DATABASE_URL" in r.stderr


def test_all_required_present_imports_cleanly():
    r = _run_import_without()
    assert r.returncode == 0, r.stderr


def test_origins_split_and_trimmed(monkeypatch):
    from app.config import Settings
    s = Settings(database_url="postgresql://x", redis_url="redis://x", environment="test",
                 api_secret_key="x", allowed_origins=" https://foundation.vin, https://qa.foundation.vin ")
    assert s.origins == ["https://foundation.vin", "https://qa.foundation.vin"]
```

`tests/test_versions.py`:
```python
import json
from pathlib import Path

from app.version import VERSION

ROOT = Path(__file__).resolve().parent.parent


def test_frontend_and_backend_versions_are_in_lockstep():
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text())
    assert pkg["version"] == VERSION
```

Run: `poetry run pytest tests/test_config.py tests/test_versions.py -q` → FAIL (`ModuleNotFoundError: app.config`).

- [ ] **Step 3: Implement config and version**

`app/config.py`:
```python
"""Runtime settings. Every required variable is read once at import; a missing one
exits the process naming it, so a misconfigured deploy fails at boot, not on the
first request."""
from __future__ import annotations

import sys

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str
    redis_url: str
    environment: str  # qa | production | test
    api_secret_key: str
    allowed_origins: str = ""
    commit_sha: str = "dev"
    public_indexing: bool = False  # flip to true at launch; until then every response is noindex

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        names = ", ".join(sorted({str(e["loc"][0]).upper() for e in exc.errors()}))
        print(f"[config] missing or invalid environment variables: {names}", file=sys.stderr)
        raise SystemExit(1) from None


settings = load_settings()
```

`app/version.py`:
```python
"""Single source of the release version: pyproject.toml [project].version.
frontend/package.json must match (tests/test_versions.py)."""
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def app_version() -> str:
    with _PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


VERSION = app_version()
```

Run: `poetry run pytest tests/test_config.py tests/test_versions.py -q` → 4 passed.

- [ ] **Step 4: Failing tests — health endpoints and SPA serving**

`tests/test_health.py`:
```python
import httpx
import pytest
from httpx import ASGITransport

from app.config import settings
from app.main import app
from app.version import VERSION

KEYS = {"status", "version", "environment", "commit_sha", "db", "redis"}


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def components_down(monkeypatch):
    # Real connection failures (closed port), not mocks.
    monkeypatch.setattr(settings, "database_url", "postgresql://x:x@127.0.0.1:1/x")
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")


async def test_healthz_has_the_contract_keys(client):
    r = await client.get("/api/healthz")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == KEYS
    assert body["status"] == "ok"
    assert body["version"] == VERSION
    assert body["environment"] == "test"
    assert "ok" in body["db"] and "ok" in body["redis"]


async def test_healthz_stays_200_with_components_down(client, components_down):
    r = await client.get("/api/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["db"]["ok"] is False and "error" in body["db"]
    assert body["redis"]["ok"] is False and "error" in body["redis"]


async def test_deep_healthz_is_503_with_components_down(client, components_down):
    r = await client.get("/api/healthz/deep")
    assert r.status_code == 503
    assert r.json()["db"]["ok"] is False


async def test_unknown_api_route_is_json_404_not_index(client):
    r = await client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["error"]["code"] == "NOT_FOUND"
```

`tests/test_static.py`:
```python
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app


# `dist` and `client` are shared fixtures in tests/conftest.py (amended 2026-09-05); drop any import this module no longer uses.


async def test_root_serves_index_with_no_cache(client):
    r = await client.get("/")
    assert r.status_code == 200 and 'id="app"' in r.text
    assert r.headers["cache-control"] == "no-cache"


async def test_deep_link_falls_back_to_index(client):
    r = await client.get("/browse?tab=market")
    assert r.status_code == 200 and 'id="app"' in r.text


async def test_fingerprinted_bundle_is_immutable(client):
    r = await client.get("/_app/index-abc123.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


async def test_design_assets_are_short_cached_not_immutable(client):
    r = await client.get("/assets/icons/pad-lock.svg")
    assert r.status_code == 200 and r.text == "<svg/>"
    assert r.headers["cache-control"] == "public, max-age=3600"


async def test_api_404_wins_over_spa_fallback(client):
    r = await client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


async def test_noindex_until_public_indexing_is_enabled(client):
    r = await client.get("/")
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    robots = await client.get("/robots.txt")
    assert robots.status_code == 200 and robots.text == "User-agent: *\nDisallow: /\n"


async def test_indexing_allowed_when_flag_is_set(dist, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "public_indexing", True)
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url="http://test") as c:
        assert "x-robots-tag" not in (await c.get("/")).headers
        assert (await c.get("/robots.txt")).text == "User-agent: *\nAllow: /\n"


async def test_path_traversal_never_escapes_dist(client):
    r = await client.get("/..%2F..%2Fpyproject.toml")
    assert r.status_code == 200 and 'id="app"' in r.text  # falls back to index, not the file
```

Run: `poetry run pytest tests/test_health.py tests/test_static.py -q` → FAIL (`ModuleNotFoundError: app.main`).

- [ ] **Step 5: Implement checks, health, static, main**

`app/checks.py`:
```python
"""Component probes for the health endpoints. They never raise: any failure becomes
{"ok": False, "error": "..."} so /api/healthz stays 200 while Railway provisions."""
from __future__ import annotations

import asyncio

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TIMEOUT_S = 3.0


def async_dsn(url: str) -> str:
    """Railway hands out postgresql://…; SQLAlchemy's asyncpg dialect wants postgresql+asyncpg://…"""
    return url if url.startswith("postgresql+asyncpg://") else url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _err(exc: BaseException) -> dict:
    return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


async def check_db(url: str) -> dict:
    engine = create_async_engine(async_dsn(url), connect_args={"timeout": TIMEOUT_S})
    try:
        async with engine.connect() as conn:
            result = await asyncio.wait_for(conn.execute(text("SELECT postgis_version()")), TIMEOUT_S)
            return {"ok": True, "postgis_version": str(result.scalar_one())}
    except Exception as exc:  # noqa: BLE001 — reported, never raised
        return _err(exc)
    finally:
        await engine.dispose()


async def check_redis(url: str) -> dict:
    client = aioredis.from_url(url, socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S)
    try:
        await asyncio.wait_for(client.ping(), TIMEOUT_S)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    finally:
        await client.aclose()
```

`app/api/health.py`:
```python
import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.checks import check_db, check_redis
from app.config import settings
from app.version import VERSION

router = APIRouter(prefix="/api")
not_found_router = APIRouter(prefix="/api")  # include LAST among /api routers


async def _body() -> dict:
    db, redis_ = await asyncio.gather(check_db(settings.database_url), check_redis(settings.redis_url))
    return {
        "status": "ok",
        "version": VERSION,
        "environment": settings.environment,
        "commit_sha": settings.commit_sha,
        "db": db,
        "redis": redis_,
    }


@router.get("/healthz")
async def healthz() -> dict:
    """Railway's healthcheck. Always 200; component state is inside the body."""
    return await _body()


@router.get("/healthz/deep")
async def healthz_deep() -> JSONResponse:
    """Post-deploy probe (scripts/verify-deploy.sh). 503 unless every component is up."""
    body = await _body()
    code = 200 if body["db"]["ok"] and body["redis"]["ok"] else 503
    return JSONResponse(body, status_code=code)


@not_found_router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def api_not_found(path: str) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": {"code": "NOT_FOUND", "message": f"No API route /api/{path}"}},
        status_code=404,
    )
```

`app/static.py`:
```python
"""Serve the built Vue app. Fingerprinted bundles under /_app are immutable for a
year; design assets (/assets, /ds) are short-cached because their names never
change (the sub-* icons will be swapped in place); index.html always revalidates."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
INDEX_HEADERS = {"Cache-Control": "no-cache"}
FILE_HEADERS = {"Cache-Control": "public, max-age=3600"}


class ImmutableStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):  # type: ignore[override]
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


def mount_spa(app: FastAPI, dist: Path = DIST) -> None:
    if not dist.exists():
        return
    root = dist.resolve()
    app.mount("/_app", ImmutableStaticFiles(directory=root / "_app"), name="app-bundle")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(root / "index.html", headers=INDEX_HEADERS)

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = (root / path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate, headers=FILE_HEADERS)
        return FileResponse(root / "index.html", headers=INDEX_HEADERS)
```

`app/main.py`:
```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.health import not_found_router, router as health_router
from app.config import settings
from app.static import DIST, mount_spa
from app.version import VERSION


def create_app(dist: Path | None = None) -> FastAPI:
    app = FastAPI(title="Practice Match API", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def robots_header(request, call_next):
        response = await call_next(request)
        if not settings.public_indexing:
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.get("/robots.txt", include_in_schema=False)
    async def robots() -> PlainTextResponse:
        return PlainTextResponse("User-agent: *\nAllow: /\n" if settings.public_indexing else "User-agent: *\nDisallow: /\n")

    if settings.origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
            allow_methods=["*"], allow_headers=["*"],
        )
    app.include_router(health_router)
    # Future /api routers are included here, BEFORE the catch-all below.
    app.include_router(not_found_router)
    mount_spa(app, dist or DIST)
    return app


app = create_app()
```

Run: `poetry run pytest -q` → all pass (the `components_down` tests fail fast on port 1; the shape test tolerates a down DB because `db.ok` may be false until Task 6).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(api): FastAPI skeleton — fail-fast config, health endpoints, SPA serving

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/platform && git push production feat/platform
```


**Fix round 1 (2026-09-05, after review — John's ruling "fix all five now"; files: `app/checks.py`, `app/api/health.py`, `app/main.py`, `app/static.py`, `tests/test_health.py`, `tests/test_main.py` (new), `pyproject.toml` + `poetry.lock` (dev group only); one commit):**
- [ ] **Prove the finding first.** Add `mypy>=1.13` to `[tool.poetry.group.dev.dependencies]` (Task 9 will wire it into CI; adding it now is what makes this round testable), `poetry lock && poetry install`, then `poetry run mypy app --strict` → RED: errors on the bare `dict` returns (`app/checks.py` `_err`, `check_db`, `check_redis`; `app/api/health.py` `_body`, `healthz`) and the untyped `robots_header(request, call_next)` / `file_response(*args, **kwargs)`. Record the error list.
- [ ] **Types.** `app/checks.py`: `class ComponentStatus(TypedDict, total=False): ok: bool; postgis_version: str; error: str`; `_err(exc: Exception) -> ComponentStatus`; `async def check_db(url: str) -> ComponentStatus`; `async def check_redis(url: str) -> ComponentStatus`. `app/api/health.py`: `class HealthBody(TypedDict): status: str; version: str; environment: str; commit_sha: str; db: ComponentStatus; redis: ComponentStatus`; `_body(...) -> HealthBody`; `healthz() -> HealthBody`; `healthz_deep() -> JSONResponse`. `app/main.py`: `async def robots_header(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response`. `app/static.py`: give `file_response` the installed Starlette signature (read it from `starlette/staticfiles.py` in the virtualenv — do not guess) and drop the `# type: ignore[override]` if the signature now matches. GREEN: `poetry run mypy app --strict` → `Success: no issues found`.
- [ ] **Generic health error text.** `_err` returns `{"ok": False, "error": type(exc).__name__}` and logs the full message once via `logging.getLogger(__name__).warning("health check failed: %s", exc)`; the public body never carries driver text. RED: a test in `tests/test_health.py` asserts `body["db"]["error"]` has no whitespace and equals an exception class name (e.g. `OSError`/`ConnectionRefusedError` for port 1) and that `caplog` holds the detail; adjust any existing assertion that expected raw text (RED first, then GREEN).
- [ ] **CORS test.** New `tests/test_main.py`: with `settings.allowed_origins` monkeypatched to `"https://qa.foundation.vin"` and the app created after the patch, a preflight `OPTIONS /api/healthz` with `Origin: https://qa.foundation.vin` and `Access-Control-Request-Method: GET` returns `access-control-allow-origin: https://qa.foundation.vin`; with `allowed_origins=""` the header is absent. RED first (the assertion shape must fail before the wiring is confirmed — if it passes immediately, break the middleware condition once, watch it fail, restore).
- [ ] **Engine per call.** No code change: add a one-line comment above `check_db` that the Identity plan's `app/db.py` (Task I1) owns the pooled engine and this probe will use it then.
- [ ] `poetry run pytest -q -W error` → all green; `poetry run mypy app --strict` → clean. Commit — `fix(api): strict types for health and static serving; generic health error text; CORS test`.

**Fix round 2 (2026-09-05 — re-review observation, closed per John's standing "no parking" preference; files: `app/checks.py`, `tests/test_health.py`; one commit):**
- [ ] `check_db` builds its engine outside its own `try`, so a malformed DSN raises instead of degrading to `{ok: False, error}`. Move `create_async_engine(...)` inside the `try`. RED: `await check_db("not-a-dsn")` returns `{"ok": False, "error": "ArgumentError"}` (or the class SQLAlchemy actually raises — record it) instead of raising; same shape check for `check_redis("not-a-url")`.
- [ ] `poetry run pytest -q -W error` green; `poetry run mypy app --strict` clean. Commit — `fix(api): health probes degrade on a malformed DSN instead of raising`.

**Fix round 3 (2026-09-05 — John's ruling on the Task 6 stop: "pool the connections now"; files: new `app/db.py`, `app/checks.py`, `app/main.py`, new `tests/test_db.py`; `tests/perf/test_api_latency.py` untouched; one commit, made BEFORE Task 6's own commit, by the Task 6 implementer):**
- [ ] **Why.** With Postgres and Redis up (Task 6), `/api/healthz` opened a new async engine and a new Redis client per call (~100 ms) and the policy's p95 ≤ 20 ms budget failed; it passed in Task 5 only because refused connections are instant.
- [ ] **`app/db.py`** — `get_engine(url: str) -> AsyncEngine` and `get_redis(url: str) -> Redis` return one instance per (running event loop, url), created lazily on first use (`weakref.WeakKeyDictionary[AbstractEventLoop, dict[str, …]]`; engine `pool_pre_ping=True, pool_size=5, max_overflow=5`; redis `from_url(url)`); `async def dispose_all() -> None` disposes every cached engine and closes every cached client (all loops' entries for the current loop; other loops' entries are dropped). This is the Identity plan's Task I1 module pulled forward; that plan now extends it instead of creating it.
- [ ] **`app/checks.py`** — `check_db(url)` / `check_redis(url)` keep their signatures and the round-1/2 error semantics but obtain the engine/client via `app.db` inside the `try` (a malformed URL still raises there and degrades to `{ok: False, error: <class>}`); no per-call `dispose()`/`aclose()` — the pooled objects live for the loop.
- [ ] **`app/main.py`** — a FastAPI `lifespan` that calls `dispose_all()` on shutdown; `create_app` passes it.
- [ ] **Tests (`tests/test_db.py`, RED first):** (1) two `get_engine(url)` calls in one loop return the same object and `get_engine(other_url)` a different one; (2) after `dispose_all()` a new call returns a fresh object; (3) two `check_db(url)` calls create ONE engine (patch `app.db.create_async_engine` and count calls) — this is the RED that exists today (two); (4) the perf gate with the services UP: `poetry run pytest tests/perf -q` → RED is the current `~107 ms > 20 ms` failure, GREEN after pooling (quote both p95 values). Existing degradation tests keep passing (malformed URL → `ArgumentError`/`ValueError` class names).
- [ ] Gates with the containers UP: `poetry run pytest -q -W error` all green (`db_ready` fixture in the tree); `poetry run mypy app --strict` clean. Commit — `feat(db): pooled per-loop engine and redis client; health probes reuse them (p95 under budget with services up)`.

**Fix round 4 (2026-09-05 — John's ruling on the flagged deviation: replace the event-loop close hook with a test fixture; files: `app/db.py`, `tests/conftest.py`, `tests/test_db.py`, `tests/test_main.py`; one commit):**
- [ ] **Remove `_hook_loop_close`** and `_hooked_loops` from `app/db.py`: production code no longer monkeypatches `loop.close`; the cache stays a `WeakKeyDictionary` keyed by loop and `dispose_all()` stays the only disposal path (called by the app lifespan in production and by the fixture in tests). RED: a unit test asserts `asyncio.get_running_loop().close` is the loop's own bound method after `get_engine(url)` (i.e. untouched).
- [ ] **Autouse fixture** in `tests/conftest.py`: `@pytest.fixture(autouse=True) async def _dispose_pools(): yield; await dispose_all()` (import lazily inside the fixture, as `client` does). RED: with the hook removed and the fixture absent, `poetry run pytest tests/test_db.py tests/test_health.py -q -W error` trips `ResourceWarning`/unclosed-socket errors under per-test loops (quote it); GREEN with the fixture.
- [ ] **Lifespan test** in `tests/test_main.py`: enter `create_app()`'s lifespan — `async with app.router.lifespan_context(app):` — after calling `get_engine(settings.database_url)` once, patch `app.db.dispose_all` (or observe the cache) and assert shutdown disposed the current loop's entries. RED: temporarily drop `dispose_all()` from the lifespan → the assertion fails.
- [ ] **Restore the connection-establishment timeouts (Important, from the fix-round-3 re-review).** Fix round 3 dropped them when the construction moved into `app/db.py`: the engine lost `connect_args={"timeout": TIMEOUT_S}` (asyncpg's default is 60 s, so a black-holed Postgres now hangs `check_db` for a minute — `engine.connect()` sits outside the `wait_for`) and the Redis client lost `socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S`. Move `TIMEOUT_S = 3.0` to `app/db.py` (import it in `app/checks.py`), pass `connect_args={"timeout": TIMEOUT_S}` in `get_engine` and both socket timeouts in `get_redis`. RED: unit tests patch `create_async_engine` / `aioredis.from_url` and assert the kwargs carry the timeouts (fail today); GREEN after. **Strengthened (John, 2026-09-05: "fix all of this"):** (a) `check_db` wraps `engine.connect()` AND the query in one `asyncio.wait_for(..., TIMEOUT_S)` (and `check_redis` its `ping()`), so no driver default can hold the probe; (b) a behavioural black-hole test — a local TCP server that accepts and never replies — proves each probe returns `{ok: False, error: <class>}` within `TIMEOUT_S + 2` s (RED today: the DB probe hangs toward asyncpg's 60 s default; cap the RED run and quote it).
- [ ] Gates with the containers up: `poetry run pytest -q -W error` all green (no `ResourceWarning`), `poetry run mypy app --strict` clean. Commit — `fix(db): dispose pools via a test fixture and the app lifespan, not an event-loop close hook`.

**Fix round 5 (2026-09-06 — found by the first QA deploy (Task 8): Railway's PostGIS template emits the legacy `postgres://` scheme; files: `app/checks.py`, `scripts/migrate.py`, `tests/test_health.py` or `tests/test_db.py`, `tests/test_migrate.py`; one commit):**
- [ ] **Bug.** `app/checks.py::async_dsn()` rewrites only `postgresql://` to `postgresql+asyncpg://`; a `postgres://` URL reaches SQLAlchemy 2.x, whose `postgres` dialect alias was removed → `NoSuchModuleError: sqlalchemy.dialects:postgres`, `db.ok=false`, `/api/healthz/deep` 503 on QA. libpq accepts both spellings, so `scripts/migrate.py` ran fine.
- [ ] **Fix, test-first.** `async_dsn()`: `if url.startswith("postgres://"): url = "postgresql://" + url[len("postgres://"):]` before the existing rewrite; correct its docstring (Railway hands out `postgres://` on this template). `scripts/migrate.py::normalize_dsn()`: accept `postgres://` the same way. RED: `async_dsn("postgres://u:p@h:5432/db")` → `"postgresql+asyncpg://u:p@h:5432/db"` (fails today); `normalize_dsn("postgres://…")` returns the psycopg2-ready form; both `postgresql://` cases unchanged.
- [ ] Gates: `poetry run pytest -q -W error` green, `mypy app --strict` and `mypy scripts/migrate.py --strict` clean. Commit — `fix(db): accept the legacy postgres:// scheme Railway emits`. Then Task 8 redeploys QA and verifies (`db.ok true`, `postgis 3.5.x`, `deep` 200).
- [ ] **Follow-up from the round-5 re-review (folded into Task 9 fix round 1's backend commit):** `async_dsn()`'s inherited fallback `url.replace("postgresql://", "postgresql+asyncpg://", 1)` is unanchored; rewrite it as a `startswith`-guarded prefix replacement like the new `postgres://` branch, so a `postgresql://` appearing inside a query value can never be rewritten. RED: `async_dsn("postgresql+asyncpg://u:p@h/db?x=postgresql://y")` is returned unchanged and `async_dsn("postgresql://u:p@h/db?x=postgresql://y")` rewrites only the leading scheme.

---

### Task 6: Migrations runner, PostGIS extension, local Postgres/Redis

**Files:**
- Create: `docker-compose.dev.yml`, `migrations/001_init.sql`, `scripts/migrate.py`, `tests/test_migrate.py`
- Modify: `tests/conftest.py` (DB-ready fixture), `tests/test_health.py` (DB-up assertion)

**Interfaces:**
- Produces: `scripts/migrate.py`: `run(dsn: str, directory: Path = MIGRATIONS_DIR) -> list[str]` (names applied this run), `main() -> int`; CLI `python scripts/migrate.py` reads `DATABASE_URL`.

- [ ] **Step 1: Local services**

`docker-compose.dev.yml`:
```yaml
# Local PostGIS + Redis for pytest. John does not run the app locally; this exists
# for the test suite (and CI mirrors these images in quality.yml).
services:
  db:
    image: postgis/postgis:16-3.5
    platform: linux/amd64  # the official PostGIS image ships no arm64 build; a no-op on amd64 CI/Railway (John's ruling 2026-09-05)
    environment:
      POSTGRES_USER: pm
      POSTGRES_PASSWORD: pm_dev_pw
      POSTGRES_DB: practice_match
    ports: ["5433:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pm -d practice_match"]
      interval: 5s
      timeout: 5s
      retries: 10
  redis:
    image: redis:7-alpine
    ports: ["6380:6379"]
```

```bash
docker compose -f docker-compose.dev.yml up -d && sleep 8 && docker compose -f docker-compose.dev.yml ps
```
Expected: both services `running` (db `healthy`).

- [ ] **Step 2: Failing migration tests**

`tests/test_migrate.py`:
```python
import importlib.util
import uuid
from pathlib import Path

import psycopg2
import pytest

from app.config import settings

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("migrate", ROOT / "scripts" / "migrate.py")
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)  # type: ignore[union-attr]


def _maintenance_dsn(dsn: str) -> str:
    return dsn.rsplit("/", 1)[0] + "/postgres"


@pytest.fixture
def scratch_db():
    """A brand-new database per test so 'first run applies, second run skips' is real."""
    name = f"pm_test_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(_maintenance_dsn(settings.database_url))
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    dsn = settings.database_url.rsplit("/", 1)[0] + f"/{name}"
    try:
        yield dsn
    finally:
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.close()


def test_applies_each_file_once_and_records_it(scratch_db):
    first = migrate.run(scratch_db)
    second = migrate.run(scratch_db)
    assert first == ["001_init.sql"]
    assert second == []
    with psycopg2.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM schema_migrations ORDER BY name")
        assert [r[0] for r in cur.fetchall()] == ["001_init.sql"]
        cur.execute("SELECT postgis_version()")
        assert cur.fetchone()[0].startswith("3.")


def test_failing_file_raises_and_is_not_recorded(scratch_db, tmp_path):
    (tmp_path / "001_bad.sql").write_text("SELECT 1 FROM table_that_does_not_exist;")
    with pytest.raises(psycopg2.Error):
        migrate.run(scratch_db, directory=tmp_path)
    with psycopg2.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM schema_migrations")
        assert cur.fetchone()[0] == 0


def test_normalize_dsn_strips_the_asyncpg_dialect():
    assert migrate.normalize_dsn("postgresql+asyncpg://u:p@h/db") == "postgresql://u:p@h/db"
    assert migrate.normalize_dsn("postgresql://u:p@h/db") == "postgresql://u:p@h/db"
```

Run: `poetry run pytest tests/test_migrate.py -q` → FAIL (`scripts/migrate.py` missing).

- [ ] **Step 3: Implement the runner and the first migration**

`migrations/001_init.sql`:
```sql
-- Sub-project 1: prove PostGIS is available on the Railway database.
-- Application tables (Sub-project 2) and Census tables (Sub-project 3) arrive in
-- their own numbered files.
CREATE EXTENSION IF NOT EXISTS postgis;
```

`scripts/migrate.py`:
```python
#!/usr/bin/env python3
"""Ledger-based SQL migration runner (pattern from Rounds.vin).

Applies migrations/NNN_*.sql in name order, each exactly once, recorded in
schema_migrations, under a Postgres advisory lock (api and worker share one
railway.json, so two pre-deploy runs can overlap). A failing file raises and
aborts the deploy; it is not recorded, so the next deploy retries it.

Not supported yet: statements that cannot run inside a transaction
(CREATE INDEX CONCURRENTLY). Add statement splitting when the first such
migration is written.
"""
from __future__ import annotations

import os
import sys
from glob import glob
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "migrations"
LOCK_KEY = 0x504D4D47  # ASCII 'PMMG'


def normalize_dsn(dsn: str) -> str:
    """psycopg2 wants postgresql://; the app may hold postgresql+asyncpg://."""
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[str]:
    return sorted(glob(str(directory / "[0-9][0-9][0-9]_*.sql")))


def run(dsn: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    applied: list[str] = []
    conn = psycopg2.connect(normalize_dsn(dsn))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
            try:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
                )
                for path in migration_files(directory):
                    name = Path(path).name
                    cur.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (name,))
                    if cur.fetchone():
                        print(f"  ✓ {name} (already applied)")
                        continue
                    print(f"  → {name}")
                    cur.execute(Path(path).read_text(encoding="utf-8"))
                    cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (name,))
                    applied.append(name)
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    finally:
        conn.close()
    return applied


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[migrate] DATABASE_URL is not set", file=sys.stderr)
        return 2
    print(f"[migrate] applying from {MIGRATIONS_DIR}")
    applied = run(dsn)
    print(f"[migrate] done — {len(applied)} applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `poetry run pytest tests/test_migrate.py -q` → 3 passed.

- [ ] **Step 4: Health reports PostGIS when the database is up**

Append to `tests/conftest.py`:
```python
import psycopg2
import pytest


@pytest.fixture(scope="session")
def db_ready():
    """Fails loudly (never skips) when the local services are down."""
    try:
        psycopg2.connect(os.environ["DATABASE_URL"]).close()
    except psycopg2.Error as exc:  # pragma: no cover
        pytest.fail(f"Postgres not reachable at {os.environ['DATABASE_URL']}: {exc}\n"
                    "Start it: docker compose -f docker-compose.dev.yml up -d")
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("migrate", Path(__file__).resolve().parent.parent / "scripts" / "migrate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    mod.run(os.environ["DATABASE_URL"])
```

Append to `tests/test_health.py`:
```python
import re


async def test_healthz_reports_postgis_and_redis_up(client, db_ready):
    body = (await client.get("/api/healthz")).json()
    assert body["db"]["ok"] is True, body["db"]
    assert re.match(r"^3\.\d+", body["db"]["postgis_version"])
    assert body["redis"]["ok"] is True, body["redis"]
    r = await client.get("/api/healthz/deep")
    assert r.status_code == 200
```

Run: `poetry run pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(db): ledger migration runner, PostGIS extension, local PostGIS/Redis compose

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/platform && git push production feat/platform
```


**Fix round 1 (2026-09-05, after review — John's ruling "fix all three now"; files: `scripts/migrate.py`, `tests/test_migrate.py`, `pyproject.toml` + `poetry.lock` (dev group only); one commit):**
- [ ] **Atomic apply-and-record (Important, plan-mandated).** In `run()`, each migration file's SQL and its `INSERT INTO schema_migrations` execute in ONE transaction: `conn.autocommit = False` for the per-file block, `cur.execute(sql)` then the insert, then `conn.commit()`; any exception → `conn.rollback()` and re-raise (the advisory lock stays session-level and is released in the existing `finally`). `CREATE EXTENSION` is transactional in Postgres, so `001_init.sql` is unaffected. RED (scratch DB): a temp migration `002_tmp.sql` that creates a table, with the ledger insert forced to fail (monkeypatch the cursor's `execute` to raise on the `INSERT`) → after `run()` raises, the table does NOT exist and the ledger has no row for it; GREEN with the single transaction. Keep the existing failure-not-recorded test.
- [ ] **CLI tests (Minor).** `main()` returns `2` and prints the variable name to stderr when `DATABASE_URL` is unset (`monkeypatch.delenv`); returns `0` and applies nothing on a second run against the scratch DB (`monkeypatch.setenv`), asserting the printed list of applied names is empty. RED first (the tests fail before any change only if `main()` misbehaves — if they pass immediately, break `main()`'s return once, watch, restore).
- [ ] **Driver stubs (Minor).** Add `types-psycopg2` to `[tool.poetry.group.dev.dependencies]`, `poetry lock && poetry install`, and prove it: `poetry run mypy scripts/migrate.py --strict` → `Success` (RED before: `import-untyped` on `psycopg2`).
- [ ] Gates with the containers up: `poetry run pytest -q -W error` all green; `poetry run mypy app --strict` clean; `poetry run mypy scripts/migrate.py --strict` clean. Commit — `fix(db): migration apply and ledger record commit as one transaction; CLI tests; psycopg2 stubs`.

---

### Task 7: Celery skeleton, role dispatcher, Docker image, Railway config

**Files:**
- Create: `app/tasks/__init__.py`, `app/tasks/celery_app.py`, `tests/test_celery.py`, `scripts/start.sh`, `Dockerfile`, `.dockerignore`, `railway.json`, `.railwayignore`, `scripts/verify-image.sh`, `tests/test_build_config.py`, `tests/scripts/test_start_sh.sh` *(added 2026-09-05: both are created by Steps 2b–3 but were missing from this list)*

**Interfaces:**
- Produces: `celery_app` (broker/backend = `settings.redis_url`), task `ping` (`app.tasks.celery_app.ping`); container roles `api | worker | migrate`.

- [ ] **Step 1: Failing Celery test**

`tests/test_celery.py`:
```python
from app.config import settings
from app.tasks.celery_app import celery_app, ping


def test_ping_task_returns_pong():
    assert ping() == "pong"


def test_broker_and_backend_are_the_configured_redis():
    assert celery_app.conf.broker_url == settings.redis_url
    assert celery_app.conf.result_backend == settings.redis_url


def test_task_is_registered_under_its_stable_name():
    assert "practice_match.ping" in celery_app.tasks
```

Run: `poetry run pytest tests/test_celery.py -q` → FAIL (module missing).

- [ ] **Step 2: Implement**

`app/tasks/__init__.py` empty. `app/tasks/celery_app.py`:
```python
"""Celery application. Sub-project 1 ships only `ping` so the worker service
deploys healthy; the Census ingest tasks (Sub-project 3) register here."""
from celery import Celery

from app.config import settings

celery_app = Celery("practice_match", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_default_queue="celery",
)


@celery_app.task(name="practice_match.ping")
def ping() -> str:
    return "pong"
```

Run: `poetry run pytest -q` → all pass.

- [ ] **Step 2b: Failing dispatcher and build-config tests**

`tests/scripts/test_start_sh.sh` — the dispatcher contract Step 3 must satisfy: the role comes from `$1`, else from `RAILWAY_SERVICE_NAME`; `DRY_RUN=1` prints the command instead of `exec`-ing it; an unknown role exits non-zero.
```bash
#!/usr/bin/env bash
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }
out=$(DRY_RUN=1 bash scripts/start.sh api) || fail "api role exited non-zero"
[[ "$out" == *uvicorn* && "$out" == *app.main:app* ]] || fail "api role should start uvicorn app.main:app, got: $out"
out=$(DRY_RUN=1 RAILWAY_SERVICE_NAME=worker bash scripts/start.sh) || fail "worker role via RAILWAY_SERVICE_NAME exited non-zero"
[[ "$out" == *celery* && "$out" == *worker* ]] || fail "worker role should start a celery worker, got: $out"
if DRY_RUN=1 bash scripts/start.sh bogus 2>/dev/null; then fail "unknown role must exit non-zero"; fi
echo "start.sh dispatcher OK"
```

`tests/test_build_config.py`:
```python
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_declares_the_build_args_and_the_dispatcher_entrypoint():
    d = (ROOT / "Dockerfile").read_text()
    assert "ARG ENVIRONMENT=qa" in d and "ARG COMMIT_SHA=dev" in d
    assert 'ENTRYPOINT ["bash", "scripts/start.sh"]' in d and 'CMD ["api"]' in d


def test_railway_json_points_at_the_dispatcher_migrations_and_healthz():
    cfg = json.loads((ROOT / "railway.json").read_text())
    assert cfg["deploy"]["startCommand"] == "bash scripts/start.sh api"
    assert cfg["deploy"]["preDeployCommand"] == "python scripts/migrate.py"
    assert cfg["deploy"]["healthcheckPath"] == "/api/healthz"


def test_ignore_files_keep_secrets_tests_and_node_modules_out_of_uploads_and_images():
    for name in (".railwayignore", ".dockerignore"):
        text = (ROOT / name).read_text().split()
        for entry in ("frontend/node_modules", "tests", ".env", ".env.*"):
            assert entry in text, f"{name} lacks {entry}"
```
Run: `bash tests/scripts/test_start_sh.sh` → **FAIL** (`scripts/start.sh: No such file or directory`). Run: `poetry run pytest tests/test_build_config.py -q` → **FAIL** (`FileNotFoundError: Dockerfile`).

- [ ] **Step 3: Role dispatcher** — `scripts/start.sh` (from Rounds, without the GCP block)

```bash
#!/usr/bin/env bash
# Container entrypoint: one image, three roles. Railway sets RAILWAY_SERVICE_NAME;
# a service named worker/*-worker always runs Celery (railway.json's startCommand
# says "api", which would otherwise leave the queue unserved).
set -euo pipefail

if [[ -n "${RAILWAY_SERVICE_NAME:-}" ]] && [[ "${RAILWAY_SERVICE_NAME,,}" =~ ^(worker|celery|.*-worker)$ ]]; then
  role="worker"
elif [[ -n "${1:-}" ]]; then
  role="$1"
elif [[ -n "${RAILWAY_SERVICE_NAME:-}" ]]; then
  case "${RAILWAY_SERVICE_NAME,,}" in *migrate*) role="migrate" ;; *) role="api" ;; esac
else
  role="api"
fi
echo "[start.sh] role=$role (RAILWAY_SERVICE_NAME=${RAILWAY_SERVICE_NAME:-unset}, \$1=${1:-})" >&2

case "$role" in
  api)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    # Celery serves no HTTP; Railway's healthcheck would restart-loop the service.
    # Run Celery in the background and a stdlib health server in the foreground;
    # if Celery dies, terminate PID 1 so Railway restarts a clean container.
    celery -A app.tasks.celery_app:celery_app worker -B --loglevel=info --concurrency="${CELERY_CONCURRENCY:-2}" --queues=celery &
    CELERY_PID=$!
    echo "[start.sh] celery pid=$CELERY_PID" >&2
    (
      while kill -0 "$CELERY_PID" 2>/dev/null; do sleep 2; done
      echo "[start.sh] celery exited — terminating health server" >&2
      kill -TERM 1 2>/dev/null || true
    ) &
    exec python -c "
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
        self.wfile.write(b'{\"status\":\"ok\",\"role\":\"worker\"}')
    def do_HEAD(self):
        self.send_response(200); self.end_headers()
    def log_message(self, *a, **kw): pass
port = int(os.environ.get('PORT', '8000'))
print(f'[worker-health] listening on :{port}', flush=True)
HTTPServer(('0.0.0.0', port), H).serve_forever()
"
    ;;
  migrate)
    exec python scripts/migrate.py
    ;;
  *)
    echo "unknown role: $role (expected api | worker | migrate)" >&2; exit 2 ;;
esac
```
`chmod +x scripts/start.sh`.

- [ ] **Step 4: Image and Railway config**

`Dockerfile`:
```dockerfile
# syntax=docker/dockerfile:1.7
# Practice Match — one image for the api and worker services.
# Stage 1 builds the Vue app; stage 2 serves it from FastAPI. Railway populates
# declared ARGs from service variables: ENVIRONMENT (qa|production) drives the
# frontend's VITE_ENVIRONMENT; RAILWAY_GIT_COMMIT_SHA stamps both layers.
FROM node:22-bookworm-slim AS frontend-build
ARG ENVIRONMENT=qa
WORKDIR /work/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_ENVIRONMENT=$ENVIRONMENT
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
# `railway up` builds are not git-connected, so RAILWAY_GIT_COMMIT_SHA is usually absent;
# scripts/deploy.sh sets the COMMIT_SHA service variable before each upload instead.
ARG COMMIT_SHA=dev
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=2.4.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_NO_CACHE_DIR=1 \
    COMMIT_SHA=$COMMIT_SHA
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install "poetry==${POETRY_VERSION}"
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-cache
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY --from=frontend-build /work/frontend/dist/ ./frontend/dist/
EXPOSE 8000
ENTRYPOINT ["bash", "scripts/start.sh"]
CMD ["api"]
```

`.dockerignore`:
```
.git
.github
.superpowers
docs
tests
frontend/node_modules
frontend/dist
frontend/tests
frontend/test-results
frontend/playwright-report
.env
.env.*
*.log
.DS_Store
```

`railway.json`:
```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "preDeployCommand": "python scripts/migrate.py",
    "startCommand": "bash scripts/start.sh api",
    "healthcheckPath": "/api/healthz",
    "healthcheckTimeout": 60,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3,
    "numReplicas": 1
  }
}
```

`.railwayignore` (what `railway up` uploads; the build is remote):
```
.git
.github
.superpowers
docs
tests
frontend/node_modules
frontend/dist
frontend/tests
frontend/test-results
frontend/playwright-report
.env
.env.*
*.log
```

Run: `bash tests/scripts/test_start_sh.sh && poetry run pytest tests/test_build_config.py -q` → `start.sh dispatcher OK`, 3 passed (GREEN for Step 2b). Add `bash tests/scripts/test_start_sh.sh` to the backend CI job in Task 9.

- [ ] **Step 5: Local image verification** — `scripts/verify-image.sh`

```bash
#!/usr/bin/env bash
# Builds the image and runs both roles against the local compose services.
set -euo pipefail
cd "$(dirname "$0")/.."
docker build --build-arg ENVIRONMENT=test -t practice-match:local .
COMMON=(-e PORT=8000 -e ENVIRONMENT=test -e API_SECRET_KEY=local_only
        -e DATABASE_URL=postgresql://pm:pm_dev_pw@host.docker.internal:5433/practice_match
        -e REDIS_URL=redis://host.docker.internal:6380/0)
cleanup() { docker rm -f pm-api pm-worker >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run -d --name pm-api "${COMMON[@]}" -p 8010:8000 practice-match:local api >/dev/null
docker run -d --name pm-worker "${COMMON[@]}" -e RAILWAY_SERVICE_NAME=worker -p 8011:8000 practice-match:local >/dev/null
sleep 6
api=$(curl -sf http://localhost:8010/api/healthz)
echo "$api" | python3 -c 'import sys,json; b=json.load(sys.stdin); assert b["status"]=="ok" and b["environment"]=="test", b; assert b["db"]["ok"] and b["redis"]["ok"], b; print("api healthz OK", b["db"]["postgis_version"])'
curl -sf http://localhost:8010/ | grep -q 'id="app"' && echo "index.html served"
curl -sf http://localhost:8010/browse | grep -q 'id="app"' && echo "SPA fallback OK"
curl -sf http://localhost:8010/_app/ -o /dev/null -w '%{http_code}\n' | grep -qE '^(200|404)$'
curl -sf http://localhost:8011/api/healthz | grep -q '"role":"worker"' && echo "worker health OK"
docker logs pm-worker 2>&1 | grep -q 'celery@' && echo "celery booted"
```
`chmod +x scripts/verify-image.sh`.

Run: `scripts/verify-image.sh`
Expected: `api healthz OK 3.5.x`, `index.html served`, `SPA fallback OK`, `worker health OK`, `celery booted`. (Requires compose from Task 6 running.)

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(infra): Celery skeleton, role dispatcher, Docker image, Railway config

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/platform && git push production feat/platform
```


**Accepted deviations (John, 2026-09-06):** (1) `app/tasks/celery_app.py` carries two inline `# type: ignore[import-untyped]` / `# type: ignore[untyped-decorator]` comments — Celery ships no `py.typed`; a `[tool.mypy.overrides]` entry may replace them when Task 9 touches `pyproject.toml`'s tool config. (2) `scripts/start.sh` has the `DRY_RUN=1` branch that Step 2b's test requires (Step 3's snippet lacked it) and lowercases `RAILWAY_SERVICE_NAME` with `tr` rather than the bash-4-only `${var,,}` (macOS system bash is 3.2). (3) `scripts/verify-image.sh` captures each command's output into a variable before matching instead of `cmd | grep -q` under `set -o pipefail`, which was flaky (exit 22 / SIGPIPE 141); same messages and logic.

**Fix round 1 (2026-09-06 — John: "fix the three minors and add a non-root user"; files: `Dockerfile`, `.dockerignore`, `.railwayignore`, `scripts/verify-image.sh`, `tests/test_build_config.py`, new `tests/scripts/test_verify_image_sh.sh`; one commit):**
- [ ] **Non-root user.** Runtime stage: after the last `COPY`, `RUN useradd --system --uid 10001 --create-home --shell /usr/sbin/nologin app && chown -R app:app /app`, then `USER app` before `ENTRYPOINT`. Nothing writes under `/app` at runtime (uvicorn and the Celery worker keep no files there; `migrate` only reads). RED: `tests/test_build_config.py` asserts a `USER app` line exists after the last `COPY` and before `ENTRYPOINT`; `scripts/verify-image.sh` adds a sixth check — `docker exec pm-api id -u` and `docker exec pm-worker id -u` both print `10001` (prints `non-root OK`) — which fails today (`0`).
- [ ] **Idempotent verifier, stub-tested.** `scripts/verify-image.sh` calls its `cleanup` (`docker rm -f pm-api pm-worker >/dev/null 2>&1 || true`) BEFORE the first `docker run`. New `tests/scripts/test_verify_image_sh.sh` puts a fake `docker` (and fake `curl`) on `PATH` that log every invocation and return canned success output; it asserts the log's first `docker` line is the `rm -f pm-api pm-worker` and that the script exits 0 with all six OK lines. RED first (no leading cleanup → assertion fails).
- [ ] **Ignore `.venv`.** Add `.venv` to `.dockerignore` and `.railwayignore`; `tests/test_build_config.py` asserts it (RED first).
- [ ] **Stale comment.** Fix the Dockerfile header comment: only the runtime stage receives `COMMIT_SHA`. Comment only.
- [ ] Gates: `poetry run pytest -q -W error` green; `poetry run mypy app --strict` clean; `bash tests/scripts/test_start_sh.sh && bash tests/scripts/test_verify_image_sh.sh` OK; real `scripts/verify-image.sh` run → six OK lines (record the output). Commit — `fix(infra): image runs as a non-root user; verifier idempotent and stub-tested; ignore .venv`.

**Fix round 2 (2026-09-06 — Task 8 finding: `ARG ENVIRONMENT=qa` means a production build that fails to receive the variable silently ships the prototype jump bar; files: `Dockerfile`, `scripts/verify-image.sh`, `tests/test_build_config.py`, `tests/scripts/test_verify_image_sh.sh`; one commit):**
- [ ] `Dockerfile`: `ARG ENVIRONMENT` with NO default in both stages, and in the frontend stage `RUN test -n "$ENVIRONMENT" || { echo "ENVIRONMENT build arg is required (qa|production)" >&2; exit 1; }` before `npm run build`. `scripts/verify-image.sh` passes `--build-arg ENVIRONMENT=qa`. RED: `tests/test_build_config.py` asserts the Dockerfile has no `ARG ENVIRONMENT=` default and contains the guard; the stub shell test asserts the fake `docker build` received `--build-arg ENVIRONMENT=qa`. Railway forwards the `ENVIRONMENT` service variable as a build arg (proven on QA: the bundle constant-folded the prototype bar on), so nothing changes for real deploys. Commit — `fix(infra): the image build requires an explicit ENVIRONMENT`.

---

### Task 8: Railway project, services, environments, domains, guarded deploy scripts — first QA deploy

**Files:**
- Create: `scripts/deploy.sh`, `scripts/verify-deploy.sh`, `tests/scripts/test_deploy_guard.sh`, `tests/scripts/test_verify_deploy.sh` *(added 2026-09-06: created by Step 1b but missing from this list)*
- Railway state (not files): project `Practice Match`; envs `production`, `QA`; services `api`, `worker`, PostGIS db, `Redis`; domains.

**Interfaces:**
- Produces: `scripts/deploy.sh QA|production` (honours `SKIP_VERIFY=1`), `scripts/verify-deploy.sh QA|production [BASE_URL]`.

- [ ] **Step 1: Failing guard test** — `tests/scripts/test_deploy_guard.sh`

```bash
#!/usr/bin/env bash
# deploy.sh must refuse to run `railway up` unless the linked project is Practice Match,
# must reject unknown environments, and must deploy api then worker when the guard passes.
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ -x scripts/deploy.sh ]] || { echo "FAIL: scripts/deploy.sh missing or not executable"; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
export FAKE_LOG="$tmp/log"; : > "$FAKE_LOG"
cat > "$tmp/railway" <<'F'
#!/usr/bin/env bash
case "$1" in
  status) echo "{\"name\":\"${FAKE_PROJECT}\"}" ;;
  variable) : ;;
  up) echo "UP $*" >> "$FAKE_LOG" ;;
esac
F
chmod +x "$tmp/railway"

if FAKE_PROJECT="Purchase Order" PATH="$tmp:$PATH" scripts/deploy.sh QA 2>/dev/null; then echo "FAIL: accepted wrong project"; exit 1; fi
grep -q "UP" "$FAKE_LOG" && { echo "FAIL: railway up ran despite the guard"; exit 1; }
if FAKE_PROJECT="Practice Match" PATH="$tmp:$PATH" scripts/deploy.sh staging 2>/dev/null; then echo "FAIL: accepted unknown environment"; exit 1; fi
FAKE_PROJECT="Practice Match" SKIP_VERIFY=1 PATH="$tmp:$PATH" scripts/deploy.sh QA >/dev/null
[[ $(grep -c "^UP" "$FAKE_LOG") -eq 2 ]] || { echo "FAIL: expected 2 railway up calls"; cat "$FAKE_LOG"; exit 1; }
grep -q -- "--environment QA --service api" "$FAKE_LOG" || { echo "FAIL: api not deployed to QA"; exit 1; }
grep -q -- "--environment QA --service worker" "$FAKE_LOG" || { echo "FAIL: worker not deployed to QA"; exit 1; }
echo "deploy guard OK"
```
`chmod +x tests/scripts/test_deploy_guard.sh`. Run it → FAIL: `scripts/deploy.sh missing`.

- [ ] **Step 1b: Failing test for `verify-deploy.sh`**

Contract Step 2's script must satisfy: `scripts/verify-deploy.sh <ENV>` resolves the target from the environment name (`QA` → `https://qa.foundation.vin`, `production` → `https://foundation.vin`) unless `VERIFY_BASE_URL` is set; it prints `healthz OK …`, `deep healthz OK`, `SPA fallback OK`; it fails when the body's `environment` does not equal the lower-cased `<ENV>` or when `commit_sha` differs from `EXPECT_SHA` (default `git rev-parse --short HEAD`).

`tests/scripts/test_verify_deploy.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }
PORT=8765
python3 - "$PORT" <<'PY' &
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
BODY = {"status": "ok", "version": "0.1.0", "environment": "qa", "commit_sha": "abc1234", "db": {"ok": True, "postgis_version": "3.5.2"}, "redis": {"ok": True}}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/healthz"):
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(BODY).encode())
        else:
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(b'<!doctype html><div id="app"></div>')
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
SRV=$!; trap 'kill $SRV' EXIT; sleep 0.5
out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA) || fail "a healthy target must verify; output: $out"
for line in "healthz OK" "deep healthz OK" "SPA fallback OK"; do [[ "$out" == *"$line"* ]] || fail "missing '$line' in: $out"; done
if VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh production >/dev/null 2>&1; then fail "environment mismatch must fail"; fi
if VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=deadbee bash scripts/verify-deploy.sh QA >/dev/null 2>&1; then fail "commit mismatch must fail"; fi
echo "verify-deploy.sh OK"
```
Run: `bash tests/scripts/test_verify_deploy.sh` → **FAIL** (`scripts/verify-deploy.sh: No such file or directory`).

- [ ] **Step 2: Deploy and verify scripts**

`scripts/deploy.sh`:
```bash
#!/usr/bin/env bash
# Deploy to one Railway environment. Guards John's standing rule: read `railway status`
# back and refuse unless the linked project is Practice Match — this machine runs
# several Railway projects and `railway up` ships to whatever is linked.
set -euo pipefail
ENV="${1:-}"
[[ "$ENV" == "QA" || "$ENV" == "production" ]] || { echo "usage: $0 QA|production" >&2; exit 64; }
cd "$(dirname "$0")/.."
PROJECT=$(railway status --json | python3 -c 'import sys,json; print(json.load(sys.stdin).get("name",""))')
if [[ "$PROJECT" != "Practice Match" ]]; then
  echo "🚦 STOP: railway is linked to '${PROJECT:-nothing}', not 'Practice Match'. Fix with: railway link" >&2
  exit 65
fi
echo "🚦 railway status → Project: $PROJECT | target environment: $ENV"
SHA=$(git rev-parse --short HEAD)
for svc in api worker; do
  railway variable set "COMMIT_SHA=$SHA" --service "$svc" --environment "$ENV" --skip-deploys >/dev/null
  echo "→ railway up --environment $ENV --service $svc --ci  (commit $SHA)"
  railway up --environment "$ENV" --service "$svc" --ci
done
[[ -n "${SKIP_VERIFY:-}" ]] || scripts/verify-deploy.sh "$ENV"
```

`scripts/verify-deploy.sh`:
```bash
#!/usr/bin/env bash
# Post-deploy probes. Usage: verify-deploy.sh QA|production [BASE_URL]
# BASE_URL defaults to the environment's custom domain; pass the *.up.railway.app
# URL before DNS is live.
set -euo pipefail
ENV="${1:?usage: verify-deploy.sh QA|production [BASE_URL]}"
case "$ENV" in
  QA)         BASE="${2:-https://qa.foundation.vin}"; WANT=qa ;;
  production) BASE="${2:-https://foundation.vin}";    WANT=production ;;
  *) echo "usage: verify-deploy.sh QA|production [BASE_URL]" >&2; exit 64 ;;
esac
echo "→ GET $BASE/api/healthz"
curl -sf --max-time 20 "$BASE/api/healthz" | python3 -c "
import sys, json
b = json.load(sys.stdin)
assert b['environment'] == '$WANT', b
assert b['db']['ok'] and b['redis']['ok'], b
print('healthz OK  version', b['version'], ' commit', b['commit_sha'], ' postgis', b['db']['postgis_version'])"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$BASE/api/healthz/deep")
[[ "$code" == "200" ]] || { echo "deep healthz returned $code" >&2; exit 1; }
echo "deep healthz OK"
curl -sf --max-time 20 "$BASE/browse" | grep -q 'id="app"' && echo "SPA fallback OK"
echo "→ recent api logs"
railway logs --service api --environment "$ENV" 2>/dev/null | tail -20 || true
```
`chmod +x scripts/deploy.sh scripts/verify-deploy.sh`. Run `tests/scripts/test_deploy_guard.sh` → `deploy guard OK`.

Run: `bash tests/scripts/test_deploy_guard.sh && bash tests/scripts/test_verify_deploy.sh` → both print OK (GREEN for Steps 1 and 1b) before any Railway resource is touched.

- [ ] **Step 3: Create the project and services (production environment)**

```bash
cd "/Users/johndean/Development/Practice Match"
railway whoami                                   # johndean@vin.com
railway init --name "Practice Match"             # creates + links this directory (default env: production)
railway status --json | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["name"], [e["node"]["name"] for e in d["environments"]["edges"]])'
railway add --service api
railway add --service worker
railway deploy -t postgis                        # Railway Templates "PostGIS" (code: postgis)
railway add --database redis
railway service list --json                      # note the PostGIS service's exact name → $DB below
```
Expected: `Practice Match ['production']`; services `api`, `worker`, `Redis`, and the PostGIS service (name as printed, e.g. `PostGIS` or `Postgres`). Set `DB="<that name>"` in your shell for the next steps.

- [ ] **Step 4: Pin the database image**

The template's image tag is a rolling build. Before any data exists: Railway dashboard → project `Practice Match` → the `$DB` service → **Settings → Source → Image** → set `postgis/postgis:16-3.5` → Deploy. (No CLI command changes a service image in v5.26; if `railway service --help` on your version shows one, use it.) Confirm later via healthz `postgis_version` = `3.5.x`.

- [ ] **Step 5: Variables (production)**

Find the private-network URL variable exposed by the DB service:
```bash
railway variable list --service "$DB" --environment production --json | python3 -c 'import sys,json; [print(k, "→ private" if ".railway.internal" in str(v) else "") for k,v in json.load(sys.stdin).items() if "URL" in k]'
```
Use the key whose value contains `.railway.internal` (call it `$DBURLKEY`, normally `DATABASE_URL`; some templates name it `DATABASE_PRIVATE_URL`). Then, quoting the references so the shell does not expand them:
```bash
SECRET=$(openssl rand -hex 32)
for svc in api worker; do
  railway variable set "ENVIRONMENT=production" --service $svc --environment production --skip-deploys
  railway variable set "API_SECRET_KEY=$SECRET" --service $svc --environment production --skip-deploys
  railway variable set "ALLOWED_ORIGINS=https://foundation.vin" --service $svc --environment production --skip-deploys
  railway variable set "DATABASE_URL=\${{${DB}.${DBURLKEY}}}" --service $svc --environment production --skip-deploys
  railway variable set "REDIS_URL=\${{Redis.REDIS_URL}}" --service $svc --environment production --skip-deploys
done
railway variable list --service api --environment production --kv | sed -E 's/(SECRET_KEY|URL)=.*/\1=<redacted>/'
```
Expected: five keys listed for `api` (values redacted in your output — never paste them).

- [ ] **Step 6: QA environment**

```bash
railway environment new QA --duplicate production
SECRET_QA=$(openssl rand -hex 32)
for svc in api worker; do
  railway variable set "ENVIRONMENT=qa" --service $svc --environment QA --skip-deploys
  railway variable set "API_SECRET_KEY=$SECRET_QA" --service $svc --environment QA --skip-deploys
  railway variable set "ALLOWED_ORIGINS=https://qa.foundation.vin" --service $svc --environment QA --skip-deploys
done
# Isolation check: the QA database host must differ from production's.
railway variable list --service "$DB" --environment QA --json | python3 -c 'import sys,json; print([v for k,v in json.load(sys.stdin).items() if k=="'"$DBURLKEY"'"][0].split("@")[1].split("/")[0])'
railway variable list --service "$DB" --environment production --json | python3 -c 'import sys,json; print([v for k,v in json.load(sys.stdin).items() if k=="'"$DBURLKEY"'"][0].split("@")[1].split("/")[0])'
```
Expected: two different hosts. Repeat Step 4's image pin for the QA database service.

- [ ] **Step 7: Domains**

```bash
railway domain --service api --environment QA               # Railway-provided *.up.railway.app for pre-DNS testing
railway domain qa.foundation.vin --service api --environment QA
railway domain --service api --environment production
railway domain foundation.vin --service api --environment production
```
Each custom-domain command prints the DNS record Railway needs. Copy both records verbatim into `DEPLOY.md` §DNS (Task 9) and into the hand-back for John. Expected shapes: `qa.foundation.vin CNAME <id>.up.railway.app`; `foundation.vin A <ip>` (or a CNAME-flattening instruction — record whatever Railway prints).

- [ ] **Step 8: First deploy — QA**

```bash
git status --short | grep -q . && { echo "commit first"; exit 1; }
SKIP_VERIFY=1 scripts/deploy.sh QA
QA_URL="https://$(railway domain list --service api --environment QA --json | python3 -c 'import sys,json; d=json.load(sys.stdin); print([x for x in (d if isinstance(d,list) else d.get("domains",d.get("serviceDomains",[]))) if "railway.app" in json.dumps(x)][0].get("domain"))')"
scripts/verify-deploy.sh QA "$QA_URL"
```
If the `railway domain list --json` shape differs, read the `*.up.railway.app` host from `railway domain list --service api --environment QA` (plain) and set `QA_URL` by hand.
Expected: `healthz OK  version 0.1.0 … postgis 3.5.x`, `deep healthz OK`, `SPA fallback OK`, and `commit_sha` equal to `git rev-parse --short HEAD`. Open `$QA_URL` and confirm the gate renders **with the jump bar** — that proves Railway passed `ENVIRONMENT` into the Docker `ARG` (`VITE_ENVIRONMENT=qa`). If the bar is missing, the build arg did not arrive: add `GET /api/config → {"environment": …}` to `app/api/health.py`, fetch it in `main.ts` before mounting, and pass `prototypeBar` from it instead of `import.meta.env`; record the change in the spec.

- [ ] **Step 9: Commit the scripts**

```bash
git add scripts tests/scripts && git commit -m "feat(deploy): guarded railway deploy + post-deploy verification scripts

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/platform && git push production feat/platform
```


**Rulings during execution (John, 2026-09-06):** the PostGIS image pin is done with the CLI (`railway service source connect --image postgis/postgis:16-3.5 --service PostGIS --environment production`, available in Railway CLI 5.26) after the 🚦 check, for production and — if the duplicate did not inherit it — QA. The private-network key on this template is `DATABASE_PRIVATE_URL` (the template's `DATABASE_URL` is the public `rlwy.net` proxy), so `DATABASE_URL=${{PostGIS.DATABASE_PRIVATE_URL}}`. Accepted adaptations: `railway logs --lines 20` (5.26 streams by default; a `| tail` never returns); `scripts/verify-deploy.sh` resolves its target `$2` → `VERIFY_BASE_URL` → the environment's default domain and `EXPECT_SHA` defaults to `git rev-parse --short HEAD` (Step 1b's contract required both); the healthz probe is a real pipe so a failed fetch fails the check. **Hazard found and fixed:** `~/.railway/config.json` linked `/Users/johndean` itself to the CE.VIN project, so every unlinked directory under `$HOME` resolved to CE.VIN — an unguarded `railway up` would have deployed over CE.VIN's production API; the 🚦 guard caught it, and John ruled `railway unlink` in `/Users/johndean`. Task 9's `DEPLOY.md` documents the hazard and the guard.


**Fix round 1 (2026-09-06, after review — John's ruling "fix all four before the production deploy"; files: `scripts/verify-deploy.sh`, `tests/scripts/test_verify_deploy.sh`; one commit):**
- [ ] **The SPA-fallback check must be able to fail (Important, plan-mandated — the sketch's `curl … | grep -q 'id="app"' && echo "SPA fallback OK"` cannot fail the script under `set -e`).** Rewrite as `curl -fsS --max-time 20 "$BASE/browse" | grep -q 'id="app"' || { echo "FAIL: SPA fallback missing at $BASE/browse" >&2; exit 1; }; echo "SPA fallback OK"`. RED: the shell test serves `/browse` without `id="app"` (healthz and deep healthy) and asserts the script exits non-zero with that message — today it exits 0.
- [ ] **`postgis_version` must be present when `db.ok` is true**: assert it and print it; RED: a healthz body with `db.ok true` and no `postgis_version` → non-zero exit with `FAIL: postgis_version missing`.
- [ ] **curl reports errors**: every `curl -sf` becomes `curl -fsS` (silent progress, loud errors).
- [ ] **Negative paths in `tests/scripts/test_verify_deploy.sh`**: add cases for `/api/healthz/deep` returning 503 (exit non-zero, message names deep) and the SPA-missing case above; keep the existing pass, environment-mismatch and commit-mismatch cases. Both shell tests green: `bash tests/scripts/test_deploy_guard.sh && bash tests/scripts/test_verify_deploy.sh`.
- [ ] Re-run the verify against QA once more (`scripts/verify-deploy.sh QA https://qa.foundation.vin`) to prove the hardened gate still passes on the live deployment. Commit — `fix(deploy): verify-deploy fails on a missing SPA shell or PostGIS version; curl reports errors; negative-path tests`.

**Fix round 2 (2026-09-06 — round-1 concern, closed per John's standing "no parking" preference; files: `scripts/verify-deploy.sh`, `tests/scripts/test_verify_deploy.sh`; one commit):**
- [ ] **Hermetic shell test.** The trailing `railway logs --lines 20` makes the happy-path case call live Railway (and would print an auth error in CI). Tail logs only when no explicit base URL was given (the argument/`VERIFY_BASE_URL` path is the ad hoc probe the tests use) AND `railway whoami` succeeds; otherwise print `logs: skipped (explicit target)` / `logs: skipped (railway not logged in)`. RED: the shell test's fake `railway` on `PATH` records any invocation and the happy-path case asserts none happened (fails today); GREEN after. Commit — `fix(deploy): verify-deploy tails Railway logs only for the default target and a logged-in CLI`.

---

### Task 9: CI and working docs

**Files:**
- Create: `.github/workflows/quality.yml`, `.gitleaks.toml`, `CLAUDE.md`, `DEPLOY.md`, `README.md`, `.env.example`, `.claude/skills/practice-match-workflow/SKILL.md`, `tests/test_docs.py` *(added 2026-09-06: created by Step 0 but missing from this list)*
- Modify: `pyproject.toml` + `poetry.lock` (dev group only: `pyyaml` for the drift tests; a `[tool.mypy.overrides]` entry for `celery.*` may replace Task 7's inline type-ignores here), `tests/test_versions.py` if Step 0 extends it

**Interfaces:** none new; CI consumes every script/test from Tasks 1–8. *Process note (2026-09-06): Step 7's `git add -A … && git push …` is replaced by the standing rule — the implementer commits with explicit pathspecs and does not push; the controller pushes after review and then runs the `gh run` watch commands in both repos.*

- [ ] **Step 0: Failing drift tests for CI, secrets scanning and the working docs**

`tests/test_docs.py` (`poetry add --group dev pyyaml`):
```python
import re
import tomllib
from pathlib import Path

import yaml

from app.config import Settings

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", ROOT / "CLAUDE.md", ROOT / "DEPLOY.md", *sorted((ROOT / "docs").rglob("*.md"))]


def env_names() -> set[str]:
    return {(f.alias or name).upper() for name, f in Settings.model_fields.items()}


def test_every_setting_is_documented_in_env_example_and_deploy_md():
    example = (ROOT / ".env.example").read_text()
    deploy = (ROOT / "DEPLOY.md").read_text()
    missing = sorted(n for n in env_names() if not re.search(rf"(?m)^#?\s*{n}=", example) or n not in deploy)
    assert missing == []


def test_relative_markdown_links_resolve():
    broken = []
    for doc in DOCS:
        for m in re.finditer(r"\]\(((?!https?://|#|mailto:)[^)\s]+)\)", doc.read_text(encoding="utf-8")):
            target = (doc.parent / m.group(1).split("#")[0]).resolve()
            if not target.exists():
                broken.append(f"{doc.relative_to(ROOT)} -> {m.group(1)}")
    assert broken == []


def test_ci_workflow_runs_every_gate():
    path = ROOT / ".github" / "workflows" / "quality.yml"
    wf = yaml.safe_load(path.read_text())
    assert {"gitleaks", "backend", "frontend"} <= set(wf["jobs"])
    text = path.read_text()
    for cmd in ("poetry run pytest", "bash tests/scripts/test_start_sh.sh", "npx vitest run", "npx playwright test"):
        assert cmd in text, cmd


def test_gitleaks_config_parses():
    tomllib.loads((ROOT / ".gitleaks.toml").read_text())


def test_working_docs_carry_the_railway_status_rule_and_the_key_handling_rule():
    for name in ("CLAUDE.md", "DEPLOY.md"):
        text = (ROOT / name).read_text()
        assert "railway status" in text and "Project: Practice Match" in text, name
        assert "CENSUS_API_KEY" in text and "never" in text.lower(), name
```
Run: `poetry run pytest tests/test_docs.py -q` → **FAIL** (`FileNotFoundError: .github/workflows/quality.yml`, `.env.example`, `DEPLOY.md`).

- [ ] **Step 1: CI workflow** — `.github/workflows/quality.yml`

```yaml
name: Quality

on:
  push:
    branches: [main, 'feat/**']
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: quality-${{ github.ref }}
  cancel-in-progress: true

jobs:
  gitleaks:
    name: gitleaks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Install gitleaks
        run: |
          set -euo pipefail
          V=8.21.2
          curl -sSL -o gitleaks.tar.gz "https://github.com/gitleaks/gitleaks/releases/download/v${V}/gitleaks_${V}_linux_x64.tar.gz"
          tar -xzf gitleaks.tar.gz gitleaks && sudo mv gitleaks /usr/local/bin/ && gitleaks version
      - run: gitleaks detect --config .gitleaks.toml --verbose --redact

  backend:
    name: backend (pytest against PostGIS + Redis)
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgis/postgis:16-3.5
        env: { POSTGRES_USER: pm, POSTGRES_PASSWORD: pm_dev_pw, POSTGRES_DB: practice_match }
        ports: ['5433:5432']
        options: >-
          --health-cmd "pg_isready -U pm -d practice_match" --health-interval 5s --health-timeout 5s --health-retries 10
      redis:
        image: redis:7-alpine
        ports: ['6380:6379']
        options: >-
          --health-cmd "redis-cli ping" --health-interval 5s --health-timeout 3s --health-retries 10
    env:
      DATABASE_URL: postgresql://pm:pm_dev_pw@localhost:5433/practice_match
      REDIS_URL: redis://localhost:6380/0
      ENVIRONMENT: test
      API_SECRET_KEY: ci_only_secret_change_me
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pipx install poetry==2.4.1
      - run: poetry install --no-interaction
      - run: poetry run python scripts/migrate.py
      - run: poetry run pytest -v
      - run: bash tests/scripts/test_deploy_guard.sh

  frontend:
    name: frontend (typecheck · unit · build · smoke · visual parity)
    runs-on: ubuntu-latest
    defaults:
      run: { working-directory: frontend }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm', cache-dependency-path: frontend/package-lock.json }
      - run: npm ci
      - run: npm run typecheck
      - run: npm test
      - run: npm run build
      - run: npx playwright install --with-deps chromium
      - name: Smoke
        run: npm run test:smoke
      - name: Generate the oracle from the approved design (this run's Linux Chromium)
        run: npm run test:visual:baselines
      - name: Visual parity — the app must match the design
        run: npm run test:visual
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-report
          path: |
            frontend/playwright-report
            frontend/test-results
            frontend/tests/visual.spec.ts-snapshots
          retention-days: 14
```

**CI gates (policy §2):** the `backend` job runs `poetry run ruff check app tests`, `poetry run mypy app --strict`, `poetry run pytest -q -W error --cov=app --cov-report=xml --cov-fail-under=90`, `bash tests/scripts/*.sh`, and on pull requests `diff-cover coverage.xml --compare-branch=origin/main --fail-under=100`; the `frontend` job runs `npx vue-tsc --noEmit`, `npx vitest run --coverage --coverage.thresholds.lines=85 --coverage.include='src/map/**' --coverage.include='src/router/**' --coverage.include='src/admin/**'`, `npm run build`, `npx vitest run tests/bundle-budget.test.ts`, `npx playwright test`. `tests/test_docs.py::test_ci_workflow_runs_every_gate` asserts every one of these commands appears in `quality.yml` (extend its list). `DEPLOY.md` gains the rollback procedure: redeploy the previous image (`railway redeploy --service api --environment <env>` after `railway status` shows `Project: Practice Match`), then `scripts/verify-deploy.sh`.

- [ ] **Step 2: gitleaks config** — `.gitleaks.toml`

```toml
# Gitleaks — Practice Match. Direct binary in CI (not the paid Action for orgs).
title = "Practice Match gitleaks config"

[extend]
useDefault = true

[allowlist]
description = "Placeholders in example/test files; design-reference is vendored design source"
paths = [
  '''(?i)\.env\.example$''',
  '''(?i)^docs/.*''',
  '''(?i)^frontend/tests/.*''',
  '''(?i)^tests/.*''',
]
regexes = [
  '''pm_dev_pw''',
  '''test_only_secret_change_me''',
  '''ci_only_secret_change_me''',
  '''local_only''',
]
```
Run locally: `brew list gitleaks >/dev/null 2>&1 || brew install gitleaks; gitleaks detect --config .gitleaks.toml --redact` → `no leaks found`.

- [ ] **Step 3: `.env.example`, `README.md`**

`.env.example`:
```bash
# Practice Match — service variables. Real values live only in Railway (per service,
# per environment) and are set out-of-band. Never commit real values.
DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match   # Railway: ${{<db service>.DATABASE_URL}}
REDIS_URL=redis://localhost:6380/0                                      # Railway: ${{Redis.REDIS_URL}}
ENVIRONMENT=qa                                                          # qa | production | test — also drives VITE_ENVIRONMENT at image build
API_SECRET_KEY=change_me                                                # openssl rand -hex 32; different per environment
ALLOWED_ORIGINS=https://qa.foundation.vin                              # comma-separated CORS allowlist
# CENSUS_API_KEY=                                                       # worker only, Sub-project 3; John holds the key
```

`README.md`:
```markdown
# Practice Match

VIN Foundation veterinary practice marketplace. Production https://foundation.vin · QA https://qa.foundation.vin.

- **Design (SSOT):** `docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html` — every pixel in `frontend/` must match it; `npm run test:visual` proves it.
- **Frontend:** Vue 3 + Vite in `frontend/` (the approved handoff, plus a router sync layer). `npm run typecheck && npm test && npm run build`.
- **Backend:** FastAPI + Celery in `app/`, SQL migrations in `migrations/`, one Docker image, Railway services `api` + `worker` + PostGIS + Redis.
- **Tests:** `docker compose -f docker-compose.dev.yml up -d && poetry run pytest` · `cd frontend && npm run test:smoke && npm run test:visual:baselines && npm run test:visual`.
- **Deploy:** `scripts/deploy.sh QA` → verify on qa.foundation.vin → `scripts/deploy.sh production`. Read `CLAUDE.md` and `DEPLOY.md` first.
- **Specs and plans:** `docs/superpowers/specs/`, `docs/superpowers/plans/`.
```

- [ ] **Step 4: `CLAUDE.md`**

```markdown
# CLAUDE.md — Practice Match

VIN Foundation veterinary practice marketplace (internal working title). Read this, then `.claude/skills/practice-match-workflow/SKILL.md` (the craft), before substantive work.

## Environments

| | URL | Railway env | Backend | Use |
|---|---|---|---|---|
| QA | https://qa.foundation.vin | `QA` | own PostGIS + Redis (isolated) | verify everything here first; test freely |
| Production | https://foundation.vin | `production` | own PostGIS + Redis | stakeholders' real data once Sub-project 2 ships |

`GET /api/healthz` on either host returns `environment`, `version`, `commit_sha`, `db.postgis_version`, `redis.ok`. **John does not run the app locally** — the loop is code → `scripts/deploy.sh QA` → verify on qa.foundation.vin → `scripts/deploy.sh production` → smoke on foundation.vin.

> ### 🚦 ALWAYS confirm the Railway target before uploading or changing anything
> This machine runs 5+ Railway projects; `railway up` ships to whatever is linked. Before ANY `railway up`, variable change, or service mutation run `railway status` and read it back — it must say **Project: Practice Match**. `scripts/deploy.sh` enforces this; do not bypass it with a bare `railway up`. Never pass `--project` from memory. Never set a global `RAILWAY_TOKEN`.

## Source of truth for the UI

`docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html` is the approved design. Rules, each violated by an assistant somewhere before:

- **Reference open first, port verbatim, absent beats faked.** No invented UI, no placeholder banners, no "TODO Phase X", no simplifications.
- **Ported files are byte-identical** except the edits listed in `docs/superpowers/specs/2026-09-05-practice-match-platform-design.md` §3. `logic.js` is never restructured. Inline styles stay inline. No CSS framework, no Pinia, no per-screen split without a visual diff per screen.
- **`npm run test:visual` is the arbiter.** Baselines are generated from the reference in the same run (`npm run test:visual:baselines`). Tolerance is zero (`playwright.config.ts`); relaxing it requires a recorded reason.
- The design-system cascade matters: `frontend/index.html` links `colors_and_type.css`, `preview/_preview.css`, `ui_kits/vin/kit.css` in that order, before the app styles.

## Non-negotiables (from po.vin / rounds.vin, still true here)

- **Surgical diffs.** The change contains the ask and nothing else. Never remove a function or feature while doing unrelated work. No drive-by refactors or reformatting.
- **No destructive actions** without explicit instruction in the current conversation.
- **Verification gate before every production deploy — all four:** (1) `poetry run pytest` + `npm run typecheck && npm test && npm run build`; (2) `npm run test:smoke` and `npm run test:visual` green; (3) click-through on https://qa.foundation.vin of the changed flow; (4) post-deploy smoke on https://foundation.vin (`scripts/verify-deploy.sh production`). Verified = ship; no need to ask.
- **Push every commit to both remotes:** `origin` (vin-swe/practice-match) and `production` (johndean/practice-match). Conventional commits; trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Versions in lockstep:** `frontend/package.json` and `pyproject.toml`, one patch per release (`tests/test_versions.py`).
- **Close the loop:** forwardable plain-language summary + screenshots of the live screens + a one-line engineer's note with any risk.

## Legally load-bearing (from the approved design and the Census spec)

- **Attribution stays visible** on every map ("Tiles © Esri" today; whatever the VIN Foundation's final basemap licence requires) and under Community Context ("Source: U.S. Census Bureau, …"). Attribution strings will come from `dataset_registry.attribution_text`, not hard-coded, once Sub-project 3 lands.
- **Blocked datasets never ship.** Pet-ownership incidence (licence unresolved) and third-party practice-location data must not be ingested or displayed until the VIN Foundation clears them. The admin Data Sources tab shows this gate; keep it.
- **Open licence question:** the design uses Esri basemap tiles; the Census spec registered CARTO. Do not swap either way without the VIN Foundation's decision (spec §9).

## Launch-removal list (execute in Sub-project 2, with real auth)

Prototype jump bar markup (`prototypeBar`, already off in production) · "Prototype — access states" shortcuts on the sign-in card · pre-filled demo credentials · `startScreen`/`startViewport` props · fixture data in `logic.js` (`P`, `MARKETS`, `VETS`, `ECON_K`, `sellerListings`, `requests`, admin rows — keep field names; the UI reads them).

## Layout

`frontend/` Vue app · `frontend/tests/` Playwright (`screens.ts` = the 25 approved states) · `app/` FastAPI (`api/health.py`, `static.py`, `checks.py`, `tasks/celery_app.py`) · `migrations/` numbered SQL (ledger runner `scripts/migrate.py`) · `scripts/` `start.sh` (roles api|worker|migrate), `deploy.sh`, `verify-deploy.sh`, `verify-image.sh` · `tests/` pytest · `docs/design-reference/` the handoff bundle (never shipped) · `docs/superpowers/{specs,plans}/`.

## Common operations

```bash
docker compose -f docker-compose.dev.yml up -d && poetry run pytest            # backend tests
cd frontend && npm run typecheck && npm test && npm run build                  # frontend gates
cd frontend && npm run test:smoke && npm run test:visual:baselines && npm run test:visual
scripts/deploy.sh QA && scripts/deploy.sh production                           # after the gate
railway logs --service api --environment QA | tail -50
railway variable list --service api --environment QA | sed -E 's/(SECRET_KEY|URL)=.*/\1=<redacted>/'
```
```

- [ ] **Step 5: `DEPLOY.md`**

```markdown
# Practice Match deploy runbook

Railway project **Practice Match** · environments `QA`, `production` · services `api`, `worker`, PostGIS database, `Redis`. One Docker image; `scripts/start.sh` picks the role from `RAILWAY_SERVICE_NAME`. `railway.json`: pre-deploy `python scripts/migrate.py`, healthcheck `/api/healthz`.

## Variables (per service, per environment — set out-of-band, never in git or chat)

| Variable | api | worker | Value |
|---|---|---|---|
| `ENVIRONMENT` | ✓ | ✓ | `qa` / `production` (also builds `VITE_ENVIRONMENT`: jump bar on in QA, off in production) |
| `API_SECRET_KEY` | ✓ | ✓ | `openssl rand -hex 32`, different per environment |
| `ALLOWED_ORIGINS` | ✓ | ✓ | `https://qa.foundation.vin` / `https://foundation.vin` |
| `DATABASE_URL` | ✓ | ✓ | `${{<db service>.DATABASE_URL}}` (the `.railway.internal` one) |
| `REDIS_URL` | ✓ | ✓ | `${{Redis.REDIS_URL}}` |
| `CENSUS_API_KEY` | | ✓ | Sub-project 3; John holds it. `railway variable set CENSUS_API_KEY=… --service worker --environment <env>` |

## DNS (name.com)

| Host | Record | Target |
|---|---|---|
| `qa.foundation.vin` | CNAME | *(paste the value Railway printed for the QA api domain)* |
| `foundation.vin` | A | *(paste the value Railway printed for the production api domain)* |

Both hosts currently point at name.com parking (`91.195.240.94`); replace those records. Check with `dig +short qa.foundation.vin CNAME` and `dig +short foundation.vin A`, then `railway domain status qa.foundation.vin --service api --environment QA`.

## Deploy

```bash
railway status                       # MUST print Project: Practice Match
scripts/deploy.sh QA                 # api + worker → verify-deploy.sh QA
# click through the changed flow on https://qa.foundation.vin
scripts/deploy.sh production         # api + worker → verify-deploy.sh production
```

Expected `verify-deploy.sh` output: `healthz OK  version X.Y.Z  commit <sha>  postgis 3.5.x`, `deep healthz OK`, `SPA fallback OK`. Boot lines to look for in `railway logs --service api`: `[start.sh] role=api`, `Uvicorn running on http://0.0.0.0:<port>`; on the worker: `[start.sh] role=worker`, `celery@… ready`, `[worker-health] listening`.

## Rollback

| Failure | Action | RTO |
|---|---|---|
| Bad build on QA | fix forward; QA is disposable | — |
| Regression on production | `git checkout <last good sha>` then `SKIP_VERIFY=1 scripts/deploy.sh production`; verify; return to `main` | ~5 min |
| Migration failed | Deploy aborted by the pre-deploy hook; the running version stays. Fix the SQL file (it was not recorded) and redeploy | — |
| Worker crash-loop | `railway logs --service worker --environment <env>`; the health server exits with Celery so Railway restarts it — check `REDIS_URL` reference and Redis service health | — |
| Wrong project deployed | `scripts/deploy.sh` refuses; if a bare `railway up` was used, redeploy the affected project's own last good commit | — |
```

- [ ] **Step 6: The workflow skill** — `.claude/skills/practice-match-workflow/SKILL.md`

```markdown
---
name: practice-match-workflow
description: How work is done on Practice Match (foundation.vin) — request intake, design-fidelity rules, the verification gate, guarded Railway deploys, and the hand-back John expects. Use for any feature, fix, or deploy in this repo.
---

# Practice Match: request → verified deploy

## The situation
- There is no human QA layer. QA (qa.foundation.vin) is where verification happens; production (foundation.vin) is what the VIN Foundation and its members see. John does not run the app locally.
- The approved Claude Design is the visual contract. `npm run test:visual` compares the app to the design itself; a red suite means the app is wrong, not the test.
- This machine runs several Railway projects. `scripts/deploy.sh` exists so a wrong link can never ship this app over another product.

## Phase 1 — Intake
Requests arrive in stakeholder language. Ask until unambiguous: who (buyer / seller / VIN Foundation admin), where (which screen in `frontend/tests/screens.ts`), edge cases, what "working" looks like. Restate before building. John prefers eight questions to the wrong feature.

## Phase 2 — Recon
Open the reference `.dc.html` for any UI work. Read the spec/plan in `docs/superpowers/`. For data-driven work, read the Census spec (`docs/design-reference/.../Census Data Source Specification.dc.html`) and probe live endpoints before trusting remembered shapes.

## Phase 3 — Build (TDD, surgical)
Failing test first (vitest / pytest / Playwright state), minimal code, green, refactor. The diff contains the feature and nothing else. Never remove or rename while doing unrelated work. Name the regression surface out loud when touching shared code (`logic.js` render values, `static.py`, `start.sh`, `deploy.sh`).

## Phase 4 — Gate (all four, every production deploy)
1. `poetry run pytest` · `cd frontend && npm run typecheck && npm test && npm run build`
2. `npm run test:smoke` · `npm run test:visual:baselines && npm run test:visual`
3. Deploy QA (`scripts/deploy.sh QA`), click through the changed flow on https://qa.foundation.vin
4. Deploy production, `scripts/verify-deploy.sh production`, load the changed flow on https://foundation.vin

## Phase 5 — Deploy
`scripts/deploy.sh QA|production` only. It runs `railway status` and refuses any project but Practice Match, deploys `api` then `worker`, then probes. If the full gate passed, deploy production without asking.

## Phase 6 — Hand-back
Plain-language summary John can forward (no jargon, UUIDs, versions, paths) · screenshots of the live screens · one engineer's line: version, what was verified, flagged risk. Say exactly what was NOT verified.

## Mistakes that have actually happened on sibling projects — do not repeat
Unfaithful ports with the reference closed · collateral removal · destructive actions without instruction · false "done" without live verification · deploying with the wrong Railway link · trusting remembered API shapes · treating "tests pass" as done.
```

Run: `poetry run pytest tests/test_docs.py -q` → 5 passed (GREEN for Step 0: every setting documented, every link resolves, CI runs every gate).

- [ ] **Step 7: Push and watch CI in both repos**

```bash
git add -A && git commit -m "ci(quality): gitleaks, pytest on PostGIS, frontend gates incl. visual parity; working docs

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/platform && git push production feat/platform
gh run list --repo johndean/practice-match --branch feat/platform --limit 3
gh run list --repo vin-swe/practice-match --branch feat/platform --limit 3
gh run watch --repo johndean/practice-match "$(gh run list --repo johndean/practice-match --branch feat/platform --limit 1 --json databaseId -q '.[0].databaseId')"
```
Expected: `gitleaks`, `backend`, `frontend` all green in both repos. A red `frontend/visual` step means Linux Chromium renders a state differently from darwin — download the `playwright-report` artifact, inspect the diff, and apply Task 4's triage table (harness timing/selector fixes only; a design-level diff is `DONE_WITH_CONCERNS`).


**Accepted deviations (John, 2026-09-06):** the frontend job builds before vitest (bundle-budget reads `dist/`); the Playwright steps are two raw invocations (`--project=reference` then `--project=app`) so `dom.spec.ts` runs; a generated-code drift step (`npm run gen:app` + `git diff --exit-code`) is part of the frontend job; the link drift test ignores fenced code; `.env.example`/`DEPLOY.md` list `COMMIT_SHA` and `PUBLIC_INDEXING`; `DEPLOY.md` §DNS carries the four real records (apex CNAME + TXT ownership records supersede the A-record expectation); `CLAUDE.md` names `CENSUS_API_KEY` handling and uses `railway logs --lines`; one `pytest` step with coverage.

**Fix round 1 (2026-09-06 — John's ruling "track the tools and fix the twelve findings"; files: `pyproject.toml` + `poetry.lock` (dev group + `[tool.ruff]`), `frontend/package.json` + `frontend/package-lock.json` (devDependencies), `.github/workflows/quality.yml`, `tests/test_docs.py`, and the source files carrying the twelve pre-existing ruff findings; one commit):**
- [ ] **Track the tools.** Dev group: `ruff`, `pytest-cov`, `diff-cover` (pin the versions the CI job installed ad hoc: ruff 0.16.6, pytest-cov 7.1.0, diff-cover 10.5.1); frontend `devDependencies`: `@vitest/coverage-v8` (3.2.7, matching the installed vitest major). `poetry lock && poetry install`; `npm install --save-dev @vitest/coverage-v8@3.2.7` (lockfile updated). Remove the `poetry run pip install …` and `npm install --no-save …` lines from `quality.yml`; the job runs the tracked tools.
- [ ] **`[tool.ruff]` with no ignores.** Add `[tool.ruff]` (`target-version = "py312"`, `line-length` matching the code) and `[tool.ruff.lint]` selecting the policy's rule set — the default set plus `I` (isort) and `RUF`; NO `ignore`/`extend-ignore`. Remove `--extend-ignore I001,RUF100,PLW1510` from `quality.yml`. RED: `poetry run ruff check app tests scripts` → the twelve findings (quote them).
- [ ] **Fix the twelve findings at source** in their files (five `I001` import-sort, six `RUF100` stale `# noqa`, one `PLW1510` `subprocess.run` without `check=`): `ruff check --fix` for the mechanical ones, then read every change — a removed `noqa` must not re-surface a real finding; the `subprocess.run` gets an explicit `check=False` or `check=True` matching the call's intent (the config fail-fast test inspects the return code, so `check=False`). GREEN: `poetry run ruff check app tests scripts` clean; `poetry run pytest -q -W error` still all green; `mypy` clean.
- [ ] **Drift test:** `tests/test_docs.py` asserts `quality.yml` contains no `pip install` and no `npm install --no-save`, and that `[tool.ruff]` exists with no `ignore` keys (RED before the change). Commit — `ci(quality): track ruff, coverage and diff-cover as dependencies; ruff clean at source; no ignores`.
- [ ] **`DEPLOY.md`:** add the rule that `SKIP_VERIFY=1` exists only to sequence the very first deploy of a commit and must never be habitual — Railway's own healthcheck passes on an always-200 `/api/healthz`, so `scripts/verify-deploy.sh` is the only gate that reads component state (`db.ok`, `postgis_version`, `deep` 200). Drift test asserts the sentence's key phrase.
- [ ] **Frontend coverage 100/100/100 (John, 2026-09-06: "the code should have 100%+ coverage").** Files added to this round: `frontend/vite.config.ts` (or a new `frontend/vitest.config.ts`) for `test.coverage`, the unit-test files that close the branches, and `docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md` (row already updated). Configure `coverage.provider = 'v8'`, `coverage.include = ['src/**/*.{ts,js,vue}']`, `coverage.exclude = ['src/App.vue', 'src/logic.js', 'src/dc-logic.js', 'src/generated/**', 'src/lib/**', 'src/map/engine.ts', 'src/map/testing/**', 'src/**/*.test.ts', 'src/**/*.d.ts']` (generated or untouched prototype files stay under the pixel/DOM/characterisation gates; type-only files and test helpers have no runtime code), `coverage.thresholds = { lines: 100, branches: 100, functions: 100, statements: 100 }`; `quality.yml` runs `npx vitest run --coverage` with no inline include/threshold flags. RED: today's scoped run reports branches 93.1 % (`markers.js` 4,6,28; `engines/leaflet.ts` 40,54,56,62–64,67; `router/sync.ts` 15,19; `router/useStateRouteSync.ts` 28) and one uncovered function in `leaflet.ts`; the widened scope will show what `components/*.vue`, `bootstrap.ts` and `app.setup.js` still miss — write the missing unit tests (each asserting the branch's behaviour, not merely executing it) until every metric reads 100 %.
- [ ] **Review findings folded in (2026-09-06):** (a) the `backend` job's `actions/checkout@v4` gets `fetch-depth: 0` so `diff-cover --compare-branch=origin/main` can see `origin/main` on pull requests (RED: the drift test asserts the backend checkout step carries `fetch-depth: 0`); (b) every job gets `timeout-minutes` (gitleaks 10, backend 30, frontend 45) — drift test asserts each job has one; (c) drop the duplicate standalone `npx vitest run tests/bundle-budget.test.ts` step (the full run already executes it) and relax the drift test's required substring to the full-run command; (d) `DEPLOY.md`'s image-pin note names the CLI route (`railway service source connect --image postgis/postgis:16-3.5 --service PostGIS --environment <env>`, run only after the 🚦 check) alongside the dashboard.
- [ ] **Accepted by John (2026-09-06), previously undisclosed:** `DEPLOY.md`'s rollback is the dashboard route — service → Deployments → last good deployment → Redeploy → `scripts/verify-deploy.sh <env>` (the CLI `railway redeploy` can only redeploy the latest deployment); `CLAUDE.md`'s redaction pattern is `(SECRET|KEY|URL)` so `CENSUS_API_KEY` is redacted too. Keep both.


**Ratified (John, 2026-09-06):** `src/app.setup.js` is in the coverage exclude list (it is the hand-maintained script source the generator inlines into `App.vue`; the file never executes at runtime, like `App.vue` itself); the attribution-link fallback branch in `ImageSlot.vue` is exercised by a test that stubs the global `URL` constructor (unreachable through real inputs; no production change).

**Fix round 2 (2026-09-06 — John's ruling "remove the dead guard"; files: `frontend/src/components/ImageSlot.vue`, `frontend/src/components/ImageSlot.test.ts` only if an assertion references the guard; one commit):**
- [ ] Delete the unreachable `if (!el) return;` at the top of `render()` in `ImageSlot.vue` (every caller runs after `el` is set synchronously and nothing ever nulls it — trace recorded in the round-1 report). The failing check is the coverage threshold: RED — `npx vitest run --coverage` reports Branches 99.69 % and fails the 100 % threshold; GREEN — 100/100/100/100 after the deletion.
- [ ] Gates: `npx vitest run --coverage` all four metrics 100 %; `npx vue-tsc --noEmit`; `npm run gen:app` no drift; `npx playwright test --config=tests/playwright.config.ts --project=reference` then `--project=app` (visual 25/25, dom 25/25, smoke 12/12 — no rendered output depended on the guard). Commit — `fix(frontend): drop the unreachable render guard so branch coverage reads 100 %`.

**Fix round 3 (2026-09-06 — re-review minors, closed per John's standing "no parking" preference; files: `tests/test_docs.py`, `docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md`, `frontend/src/components/MarketMapView.test.ts`, `frontend/src/components/ImageSlot.test.ts`; one commit):**
- [ ] **Drift test pins the coverage contract:** `tests/test_docs.py` parses `frontend/vite.config.ts` (regex is fine) and asserts all four thresholds are `100` and the exclude list is exactly the ratified set (the brief's nine entries plus `src/app.setup.js`). RED: lower one threshold in a temp copy → fails; restore.
- [ ] **Drift test hardens the ruff check:** also assert no `per-file-ignores` and that `extend-select` contains `I` and `RUF`, and reject a top-level `[tool.ruff] ignore` even when `[tool.ruff.lint]` exists.
- [ ] **Policy doc:** the Types-and-lint row's command becomes `poetry run ruff check app tests scripts && poetry run mypy app --strict` (CI already runs `scripts`); the drift test asserts the policy row and the workflow agree on the ruff paths.
- [ ] **Weak-form assertions tightened:** `MarketMapView.test.ts` — the "unmounting before createEngine()/mount() settles" test asserts the engine was never created (stub `L.map` call count 0) rather than relying on an unhandled rejection; "a click does nothing when no `onSelect` is given" asserts the stub recorded no selection side effect in addition to `not.toThrow()`; `ImageSlot.test.ts` — the ResizeObserver-notify test flips a prop the re-render must pick up and asserts the resulting style, not a value that holds either way. Each keeps its RED-ability (break the branch once, watch, restore).
- [ ] **Shell-test ports (from the Task 8 re-review):** `tests/scripts/test_verify_deploy.sh` binds four fixed ports (8765–8768) and collided once with a concurrent run; switch its local servers to an ephemeral port (bind 0, read the chosen port back) so parallel CI jobs and local runs cannot collide. File added to this round: `tests/scripts/test_verify_deploy.sh`. RED: two simultaneous invocations of the test today fail with `Address already in use`; GREEN: both pass.
- [ ] Gates: `poetry run pytest -q -W error`; `bash tests/scripts/test_verify_deploy.sh` (twice, concurrently); `cd frontend && npx vitest run --coverage` still 100/100/100/100. Commit — `test(quality): drift tests pin the coverage and ruff contracts; policy row matches CI; discriminating assertions; ephemeral test ports`.

---

### Task 10: DNS, production deploy, live verification, hand-back

**Files:**
- Modify: `DEPLOY.md` (DNS values), `docs/superpowers/specs/2026-09-05-practice-match-platform-design.md` (status line), `frontend/tests/playwright.config.ts` (live-target override)
- Create: `frontend/tests/targets.ts`, `frontend/tests/targets.test.ts` *(added 2026-09-06: created by Steps 0–1 but missing from this list)*, `scripts/k6-smoke.js`, `.github/workflows/perf.yml` *(added 2026-09-06: mandated by the "Nightly load smoke" paragraph after Step 3; the k6 `MEMBER_TOKEN` is a GitHub Actions secret John sets — never a file)*

**Interfaces:** `PW_APP_URL=<https://host>` makes the `app` project target a live deployment (no local dev server). `resolveTargets(env, ports)` returns `{ baseURL, webServer }` where each `webServer` entry carries Playwright's full `WebServer` options (`command, url, cwd, timeout, reuseExistingServer, stdout, stderr`) — the `{ command; url }` shape in Step 0 is the minimum the test asserts, not the whole type *(clarified 2026-09-06 after the Task 10 review)*.

- [ ] **Step 0: Failing test for the live-target resolver**

Extract the target logic from `playwright.config.ts` into `frontend/tests/targets.ts` so it can be tested: `resolveTargets(env: NodeJS.ProcessEnv, ports: { app: number; ref: number }) -> { baseURL: string; webServer: Array<{ command: string; url: string }> }`.

`frontend/tests/targets.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { resolveTargets } from './targets';

describe('resolveTargets', () => {
  it('runs against localhost with both servers when PW_APP_URL is unset', () => {
    const t = resolveTargets({}, { app: 5173, ref: 4174 });
    expect(t.baseURL).toBe('http://localhost:5173');
    expect(t.webServer.map((w) => w.url)).toEqual(['http://localhost:5173', 'http://localhost:4174/']);
  });
  it('runs against the live deployment and starts only the reference server when PW_APP_URL is set', () => {
    const t = resolveTargets({ PW_APP_URL: 'https://qa.foundation.vin' }, { app: 5173, ref: 4174 });
    expect(t.baseURL).toBe('https://qa.foundation.vin');
    expect(t.webServer).toHaveLength(1);
    expect(t.webServer[0].url).toBe('http://localhost:4174/');
  });
});
```
Run: `cd frontend && npx vitest run tests/targets.test.ts` → **FAIL** (`Cannot find module './targets'`). (Add `tests/**/*.test.ts` to the vitest `include` list.)

- [ ] **Step 1: Live-target override in Playwright**

In `frontend/tests/playwright.config.ts`: 
```ts
const LIVE = process.env.PW_APP_URL; // e.g. https://qa.foundation.vin — runs the app project against a deployment
```
Set the `app` project's `baseURL: LIVE ?? \`http://localhost:${APP}\`` and build `webServer` as an array that omits the Vite entry when `LIVE` is set:
```ts
webServer: [
  ...(LIVE ? [] : [{ command: `npm run dev -- --port ${APP} --strictPort`, url: `http://localhost:${APP}`, cwd: '..', timeout: 60_000, reuseExistingServer: !process.env.CI, stdout: 'ignore' as const, stderr: 'pipe' as const }]),
  { command: `node tests/reference-server.mjs ${REF}`, url: `http://localhost:${REF}/`, cwd: '..', timeout: 30_000, reuseExistingServer: !process.env.CI, stdout: 'ignore' as const, stderr: 'pipe' as const }
],
```
Run `npm run test:visual` locally (no `PW_APP_URL`) → still 25 passed. Commit: `test(visual): PW_APP_URL runs the parity suite against a live host`.

Implement `resolveTargets` in `frontend/tests/targets.ts` and have `playwright.config.ts` spread its result (`baseURL`, `webServer`). Run: `npx vitest run tests/targets.test.ts` → 2 passed (GREEN for Step 0).

- [ ] **Step 2: Hand John the DNS records — CHECKPOINT**

Report (in chat) the two records from Task 8 step 7 and stop this task until John confirms they are applied. Then:
```bash
dig +short qa.foundation.vin CNAME; dig +short foundation.vin A
railway domain status qa.foundation.vin --service api --environment QA
railway domain status foundation.vin --service api --environment production
```
Expected: the CNAME/A values Railway asked for; both domain statuses show the certificate issued. Fill the two table cells in `DEPLOY.md` §DNS with the real values and commit (`docs(deploy): record DNS targets`).

- [ ] **Step 3: QA on its real host, including the full visual suite**

```bash
scripts/verify-deploy.sh QA
cd frontend && PW_APP_URL=https://qa.foundation.vin npm run test:smoke && PW_APP_URL=https://qa.foundation.vin npm run test:visual
```
Expected: verify OK; smoke green; visual `25 passed` against the live QA build (the QA image has the jump bar on, so every state is reachable).

**Nightly load smoke (policy §3):** add `scripts/k6-smoke.js` from `docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md` §5 and `.github/workflows/perf.yml` (schedule `0 6 * * *`; installs k6; runs against `https://qa.foundation.vin` with `MEMBER_TOKEN` from a GitHub secret — the operator token until SP2). Test first: `tests/test_docs.py::test_perf_workflow_targets_qa_with_thresholds` asserts the workflow file exists, names `qa.foundation.vin`, and `k6-smoke.js` declares `p(95)<400` and `rate==0`. Run the workflow manually once (`gh workflow run perf.yml`) and record the p95 in `DEPLOY.md`.

- [ ] **Step 3b (added 2026-09-06): `DEPLOY.md` note** — `scripts/verify-deploy.sh` asserts the deployed `commit_sha` equals `EXPECT_SHA`; unset OR empty both fall back to the current checkout's `git rev-parse --short HEAD` (bash `${EXPECT_SHA:-…}` treats them identically — verified by the Task 8 round-2 re-review: `EXPECT_SHA=""` inside a checkout still asserts against local HEAD); a non-empty value is compared verbatim; the assertion is skipped ONLY when the script runs outside a git checkout. When the branch has moved past the deployed tree, pass `EXPECT_SHA=<deployed sha>` explicitly (as done for QA at `087acc1`). Two sentences next to the `SKIP_VERIFY` rule; the drift test asserts `EXPECT_SHA` appears in `DEPLOY.md`. The Task 8 report's "explicitly empty disables the check" wording is wrong and must not be copied.
- [ ] **Step 4: Production** — *Gate added 2026-09-06 (John, after seeing the prototype jump bar on qa.foundation.vin): the bar stays on QA (`ENVIRONMENT=qa`) and must be OFF in production. Before `scripts/deploy.sh production`, the controller shows John the QA-verified state and gets his explicit go; after the deploy, the served production bundle must contain `prototypeBar:{type:Boolean,default:!1}` (the Task 8 check) and the gate screen must render without the bar — if either fails, roll back and STOP.*

> **Superseded 2026-09-06 (John: production publishes a Coming Soon page, not the marketplace — spec `docs/superpowers/specs/2026-09-06-coming-soon-production-mode-design.md`).** The commands below are NOT run. Task 11 executes here (11a → 11f), and the production step at the end of Task 11f replaces this one: production deploys the same image with `SITE_MODE=coming_soon` and `PUBLIC_INDEXING=true`, and the served bundle check becomes the coming-soon title check. The prototype-bar gate is moot on production (no marketplace bundle is served) and stays in force for the launch flip (`DEPLOY.md` §Site mode). John's go for the coming-soon production deploy was given 2026-09-06 ("approved and push coming soon to production").

```bash
git status --short | grep -q . && { echo "commit first"; exit 1; }
scripts/deploy.sh production
cd frontend && PW_APP_URL=https://foundation.vin npx playwright test --config=tests/playwright.config.ts --project=app smoke.spec.ts --grep "renders the gate"
```
Expected: `healthz OK … environment production`; the gate smoke tests pass on foundation.vin (jump-bar-dependent tests are not run against production, where the bar is off). Open https://foundation.vin and confirm: no jump bar, the gate renders, "Approved — enter" → Browse works.

- [ ] **Step 5: Worker round-trip in both environments**

```bash
railway run --service worker --environment QA -- python -c "from app.tasks.celery_app import ping; print(ping.delay().get(timeout=20))"
railway run --service worker --environment production -- python -c "from app.tasks.celery_app import ping; print(ping.delay().get(timeout=20))"
```
Expected: `pong` twice. (`railway run` executes locally with that service's variables; the task is consumed by the deployed worker via the Redis URL — if the private `.railway.internal` host is unreachable from this machine, use `railway ssh --service worker --environment <env>` and run the same one-liner inside the container.)

- [ ] **Step 6: Screenshots and hand-back**

```bash
cd frontend && PW_APP_URL=https://qa.foundation.vin npx playwright test --config=tests/playwright.config.ts --project=reference --grep "gate-signin|browse-listings|browse-market|detail|seller-dash|admin-users" 
```
(That regenerates six reference PNGs into `tests/visual.spec.ts-snapshots/` — they are pixel-identical to the live app by the suite above, so they double as the live screenshots.) Copy them to `/private/tmp/…/scratchpad/handback/` and send them to John with `SendUserFile`.

Update the spec's status line to `Implemented 2026-09-__ — live on qa.foundation.vin (marketplace) and foundation.vin (coming soon)` and commit. Then write the hand-back:
- **Forwardable summary** (no jargon) *(amended 2026-09-06 for the coming-soon pivot)*: foundation.vin shows the VIN Foundation Coming Soon page and collects launch-notification sign-ups; the full marketplace is live for the team on qa.foundation.vin as the approved design with sample listings; the sign-in there is a preview until member accounts arrive; launching the marketplace on foundation.vin later is one setting change and a redeploy.
- **Engineer's note:** version, commit, both remotes pushed, both hosts `noindex` until launch, the fact that production still exposes the design's "Prototype — access states" shortcuts (anyone can enter the fixture marketplace and its fictional admin console — accepted by John 2026-09-05, removed in Sub-project 2), CI green in both repos, visual suite 25/25 on QA, production smoke, worker ping; explicitly list anything not verified (e.g. Linux-vs-macOS rendering if the tolerance was relaxed) and the VIN Foundation open items (basemap licence, mobile breakpoint).

- [ ] **Step 7: Finish the branch**

Use superpowers:finishing-a-development-branch: merge `feat/platform` → `main`, push `main` to both remotes, delete the branch, then invoke the Census data-layer plan.

---

### Task 11: Coming Soon production mode — spec `docs/superpowers/specs/2026-09-06-coming-soon-production-mode-design.md` (John, 2026-09-06). Executed AFTER Task 10 Steps 0–3b and BEFORE Task 10 Step 4; sub-tasks 11a → 11f in order, one implementer at a time.

**Why:** production (`foundation.vin`) publishes the VIN Foundation Coming Soon page, not the marketplace. QA keeps the marketplace; the coming-soon page never goes to QA. Same image, one `SITE_MODE` variable; launch later is a variable flip and a redeploy. John gave the production go on 2026-09-06 ("approved and push coming soon to production") — it is acted on once 11a–11d and 11f are green and re-reviewed; 11e (pixel gate) waits for the design file and does not block the deploy.

**Source of the page:** `/Users/johndean/Downloads/VIN FOUNDATION/Coming Soon/coming_soon_vue` (identical to `Vin Foundation Marketplace Design (1).zip` → `coming_soon_vue/`, 21 files incl. `public/ds/fonts/ProximaNova-*`). Copy excludes `node_modules/` and `dist/`.

---

### Task 11a: Import the page and build it into the image

**Files:**
- Create: `coming-soon/**` (copied verbatim), `coming-soon/package-lock.json`
- Modify: `Dockerfile`, `.dockerignore`, `.railwayignore`, `.gitignore`, `tests/test_build_config.py`

**Interfaces:**
- Produces: image path `/app/coming-soon/dist/` (Vite output with `index.html`, `_app/`, `assets/`, `ds/`). *Corrected 2026-09-06 after 11b's real image run:* the api's `/_app` mount is a `StaticFiles` that requires the directory at boot, so the default `assets/` layout crashes the api in coming-soon mode; spec §4 edit 3 (`build.assetsDir = '_app'`) is therefore made in **11b**, not 11d.

- [ ] **Step 1: Copy and lock**
```bash
rsync -a --exclude node_modules --exclude dist "/Users/johndean/Downloads/VIN FOUNDATION/Coming Soon/coming_soon_vue/" coming-soon/
diff -r --exclude node_modules --exclude dist "/Users/johndean/Downloads/VIN FOUNDATION/Coming Soon/coming_soon_vue" coming-soon && echo identical
cd coming-soon && npm install && npm run build && ls dist && cd ..
```
Expected: `identical`; `dist/index.html` exists. `.gitignore` gains:
```
coming-soon/dist/
coming-soon/coverage/
frontend/coverage/
```
(`node_modules/` is already ignored globally.) `.dockerignore` and `.railwayignore` gain `coming-soon/node_modules` and `coming-soon/dist`.

- [ ] **Step 2: Failing build-config tests** — append to `tests/test_build_config.py`:
```python
def test_dockerfile_builds_the_coming_soon_page_in_its_own_stage():
    d = (ROOT / "Dockerfile").read_text()
    assert "FROM node:22-bookworm-slim AS coming-soon-build" in d
    assert "COPY coming-soon/package.json coming-soon/package-lock.json ./" in d
    assert "COPY --from=coming-soon-build /work/coming-soon/dist/ ./coming-soon/dist/" in d


def test_ignore_files_keep_the_coming_soon_build_and_modules_out():
    for name in (".railwayignore", ".dockerignore"):
        text = (ROOT / name).read_text().split()
        for entry in ("coming-soon/node_modules", "coming-soon/dist"):
            assert entry in text, f"{name} lacks {entry}"
    assert "coming-soon/dist/" in (ROOT / ".gitignore").read_text().split()
    assert "frontend/coverage/" in (ROOT / ".gitignore").read_text().split()
```
Run: `poetry run pytest tests/test_build_config.py -q -W error` → FAIL (both new tests).

- [ ] **Step 3: Dockerfile** — insert after the `frontend-build` stage (before `FROM python:3.12-slim-bookworm AS runtime`):
```dockerfile
# The VIN Foundation Coming Soon page (John's Vue project, coming-soon/): built into the
# same image and served by the api when SITE_MODE=coming_soon (production until launch).
FROM node:22-bookworm-slim AS coming-soon-build
WORKDIR /work/coming-soon
COPY coming-soon/package.json coming-soon/package-lock.json ./
RUN npm ci
COPY coming-soon/ ./
RUN npm run build
```
and in the runtime stage, directly after the existing `COPY --from=frontend-build …` line:
```dockerfile
COPY --from=coming-soon-build /work/coming-soon/dist/ ./coming-soon/dist/
```
(The `chown -R app:app /app` that follows covers it.) Update the header comment: "Stages 1–2 build the two frontends; stage 3 serves the one SITE_MODE selects."

- [ ] **Step 4: GREEN** — `poetry run pytest tests/test_build_config.py -q -W error` → all pass; `bash tests/scripts/test_verify_image_sh.sh` still OK; real `docker build --build-arg ENVIRONMENT=qa -t practice-match:local .` succeeds and `docker run --rm --entrypoint ls practice-match:local coming-soon/dist` lists `index.html`.

- [ ] **Step 5: Commit**
```bash
git add coming-soon .gitignore .dockerignore .railwayignore Dockerfile tests/test_build_config.py
git commit -m "feat(coming-soon): import the VIN Foundation coming-soon page and build it into the image

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
(`git add coming-soon` adds the copied files and the lockfile; `coming-soon/dist` and `node_modules` are ignored.)

---

### Task 11b: `SITE_MODE` — the api serves the site the mode selects; health reports it

**Files:**
- Modify: `app/config.py`, `app/static.py`, `app/main.py`, `app/api/health.py`, `tests/test_config.py`, `tests/test_static.py`, `tests/test_health.py`, `tests/conftest.py`, `.env.example`, `DEPLOY.md`, `CLAUDE.md`, `tests/test_docs.py`, `scripts/verify-image.sh`, `tests/scripts/test_verify_image_sh.sh`, `coming-soon/vite.config.js` + `tests/test_build_config.py` *(added 2026-09-06 — Step 2b below)*

**Interfaces:**
- Produces: `settings.site_mode: str` (`"app"` | `"coming_soon"`); `app.static.COMING_SOON_DIST: Path`; `app.static.dist_for(mode: str) -> Path`; `HealthBody.site_mode: str`.

- [ ] **Step 1: Failing tests**

`tests/test_config.py` — append:
```python
def test_site_mode_defaults_to_app_and_rejects_unknown_values():
    from pydantic import ValidationError

    from app.config import Settings
    base = {"database_url": "postgresql://x", "redis_url": "redis://x", "environment": "test", "api_secret_key": "x"}
    assert Settings(**base).site_mode == "app"
    assert Settings(**base, site_mode="coming_soon").site_mode == "coming_soon"
    with pytest.raises(ValidationError):
        Settings(**base, site_mode="marketplace")


def test_invalid_site_mode_exits_1_and_names_it():
    env = dict(os.environ, SITE_MODE="marketplace", PYTHONPATH=str(ROOT))
    r = subprocess.run([sys.executable, "-c", "import app.config"], env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 1
    assert "SITE_MODE" in r.stderr
```
(`import pytest` at the top of the file if absent.)

`tests/conftest.py` — append a coming-soon dist fixture:
```python
@pytest.fixture
def coming_dist(tmp_path: Path) -> Path:
    d = tmp_path / "coming-soon-dist"
    (d / "_app").mkdir(parents=True)
    (d / "ds").mkdir()
    (d / "index.html").write_text('<!doctype html><title>VIN Foundation — Coming Soon</title><div id="app"></div>')
    (d / "_app" / "index-cs1.js").write_text("console.log(2)")
    (d / "ds" / "colors_and_type.css").write_text(":root{}")
    return d
```

`tests/test_static.py` — append:
```python
def test_dist_for_selects_the_directory_by_mode():
    from app.static import COMING_SOON_DIST, DIST, dist_for
    assert dist_for("app") == DIST
    assert dist_for("coming_soon") == COMING_SOON_DIST


async def test_coming_soon_mode_serves_the_coming_soon_shell_everywhere_but_the_api(coming_dist, monkeypatch):
    import app.static
    from app.config import settings
    monkeypatch.setattr(settings, "site_mode", "coming_soon")
    monkeypatch.setattr(app.static, "COMING_SOON_DIST", coming_dist)
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        for path in ("/", "/browse", "/practices/p1", "/..%2F..%2Fpyproject.toml"):
            r = await c.get(path)
            assert r.status_code == 200 and "VIN Foundation — Coming Soon" in r.text, path
            assert r.headers["cache-control"] == "no-cache"
        assert (await c.get("/_app/index-cs1.js")).headers["cache-control"] == "public, max-age=31536000, immutable"
        assert (await c.get("/ds/colors_and_type.css")).headers["cache-control"] == "public, max-age=3600"
        r = await c.get("/api/nope")
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
        assert (await c.get("/api/healthz")).json()["site_mode"] == "coming_soon"


async def test_app_mode_never_serves_the_coming_soon_shell(client):
    r = await client.get("/")
    assert "Coming Soon" not in r.text
    assert (await client.get("/api/healthz")).json()["site_mode"] == "app"
```

`tests/test_health.py` — `KEYS` becomes `{"status", "version", "environment", "commit_sha", "db", "redis", "site_mode"}`.

Run: `poetry run pytest tests/test_config.py tests/test_static.py tests/test_health.py -q -W error` → FAIL (`site_mode` unknown; `dist_for` missing; KEYS mismatch).

- [ ] **Step 2: Implement**

`app/config.py` — add the field and validator:
```python
from pydantic import ValidationError, field_validator
…
    public_indexing: bool = False  # flip to true at launch; until then every response is noindex
    site_mode: str = "app"  # app | coming_soon — which built site the api serves (spec 2026-09-06)

    @field_validator("site_mode")
    @classmethod
    def _site_mode_known(cls, v: str) -> str:
        if v not in ("app", "coming_soon"):
            raise ValueError("SITE_MODE must be 'app' or 'coming_soon'")
        return v
```
(`load_settings`'s error path already prints the field name uppercased: `SITE_MODE`.)

`app/static.py`:
```python
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
COMING_SOON_DIST = Path(__file__).resolve().parent.parent / "coming-soon" / "dist"


def dist_for(mode: str) -> Path:
    """The built site the api serves: the marketplace, or the Coming Soon page (production until launch)."""
    return COMING_SOON_DIST if mode == "coming_soon" else DIST
```
`mount_spa` is unchanged.

`app/main.py`: `from app.static import dist_for, mount_spa` and `mount_spa(app, dist or dist_for(settings.site_mode))` (keep the `dist` override for tests).

`app/api/health.py`: `HealthBody` gains `site_mode: str`; `_body` adds `"site_mode": settings.site_mode`.

- [ ] **Step 2b (added 2026-09-06 — found by this task's real image run): the coming-soon bundle goes under `_app/`** — spec §4 edit 3, moved here from 11d. RED first: append to `tests/test_build_config.py`
```python
def test_coming_soon_build_emits_its_bundle_under_app_like_the_marketplace():
    # app/static.py mounts /_app at boot; without this the api crashes in coming-soon mode (11b, 2026-09-06).
    assert "assetsDir: '_app'" in (ROOT / "coming-soon" / "vite.config.js").read_text()
```
Run: `poetry run pytest tests/test_build_config.py -q -W error` → FAIL. Then `coming-soon/vite.config.js` becomes exactly:
```js
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  // `_app` matches the marketplace build so app/static.py's immutable-cache rule applies.
  build: { assetsDir: '_app' }
});
```
Run the test again → PASS. (`cd coming-soon && npm run build && ls dist` shows `_app/`; the real `scripts/verify-image.sh` in Step 4 rebuilds the image and is the end-to-end proof — its seventh check was the RED that exposed this.)

- [ ] **Step 3: Docs and drift**

`.env.example` — add `SITE_MODE=app                                                            # app | coming_soon — production runs coming_soon until launch (QA never does)`.

`DEPLOY.md` — variables table row `| \`SITE_MODE\` | ✓ | ✓ | \`app\` on QA, \`coming_soon\` on production until launch — selects the built site the api serves |`, plus a new section:
```markdown
## Site mode (Coming Soon on production)

| Variable | QA | production |
|---|---|---|
| `ENVIRONMENT` | `qa` | `production` |
| `SITE_MODE` | `app` | `coming_soon` |
| `PUBLIC_INDEXING` | unset (noindex) | `true` |

Production publishes the VIN Foundation Coming Soon page (`coming-soon/`); QA is the marketplace. The coming-soon page never goes to QA. **Launch:** `railway status` (Project: Practice Match) → `railway variable set SITE_MODE=app --service api --environment production --skip-deploys` (and `--service worker`) → decide `PUBLIC_INDEXING` → `scripts/deploy.sh production` → `scripts/verify-deploy.sh production` reports `site_mode app`.
```
`CLAUDE.md` — one line under the deploy notes: "`SITE_MODE` (`app` | `coming_soon`) selects which built site the api serves; production runs `coming_soon` until launch; QA never does."

`tests/test_docs.py` — `test_every_setting_is_documented_in_env_example_and_deploy_md` already covers the new setting (RED until the docs are written). Append:
```python
def test_deploy_md_documents_the_site_mode_matrix():
    text = (ROOT / "DEPLOY.md").read_text()
    assert "SITE_MODE" in text and "coming_soon" in text
    assert "never goes to QA" in text
    for name in ("CLAUDE.md",):
        assert "SITE_MODE" in (ROOT / name).read_text(), name
```

`scripts/verify-image.sh` — third container and a seventh check (the cleanup drops it too):
```bash
cleanup() { docker rm -f pm-api pm-worker pm-coming >/dev/null 2>&1 || true; }
…
docker run -d --name pm-coming "${COMMON[@]}" -e SITE_MODE=coming_soon -p 8012:8000 practice-match:local api >/dev/null
…
coming_body=$(curl -fsS http://localhost:8012/)
[[ "$coming_body" == *'VIN Foundation — Coming Soon'* && "$coming_body" != *'<title>Practice Match'* ]] \
  || { echo "FAIL: SITE_MODE=coming_soon did not serve the coming-soon shell"; exit 1; }
coming_health=$(curl -fsS http://localhost:8012/api/healthz)
[[ "$coming_health" == *'"site_mode":"coming_soon"'* ]] || { echo "FAIL: healthz did not report site_mode coming_soon"; exit 1; }
echo "coming soon OK"
```
`tests/scripts/test_verify_image_sh.sh` — the fake `curl` gains two branches BEFORE the generic `/api/healthz` and index branches: `":8012/api/healthz"` → `{"status":"ok","site_mode":"coming_soon"}` and `":8012/"` → `<!doctype html><title>VIN Foundation — Coming Soon</title><div id="app"></div>`; the expected-lines loop gains `"coming soon OK"` (seven lines); the first-docker-call assertion becomes `docker rm -f pm-api pm-worker pm-coming`; the header comment says seven checks. RED first (the seventh line is absent today; the cleanup assertion fails once the script changes if the test is not updated — both directions are covered).

- [ ] **Step 4: GREEN** — `poetry run pytest -q -W error` all green; `poetry run mypy app --strict` clean; `poetry run ruff check app tests scripts` clean; `bash tests/scripts/test_verify_image_sh.sh` OK; real `scripts/verify-image.sh` → seven OK lines (record).

- [ ] **Step 5: Commit**
```bash
git add app/config.py app/static.py app/main.py app/api/health.py tests/test_config.py tests/test_static.py tests/test_health.py tests/conftest.py .env.example DEPLOY.md CLAUDE.md tests/test_docs.py scripts/verify-image.sh tests/scripts/test_verify_image_sh.sh coming-soon/vite.config.js tests/test_build_config.py
git commit -m "feat(api): SITE_MODE selects the served site (marketplace or coming soon); health reports site_mode; coming-soon bundle under _app

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11c: `POST /api/interest` — launch-notification sign-ups

**Files:**
- Create: `migrations/002_interest_signup.sql`, `app/ratelimit.py`, `app/api/interest.py`, `tests/api/__init__.py`, `tests/api/test_interest.py`
- Modify: `app/main.py`, `tests/test_migrate.py`, `tests/perf/test_api_latency.py`

**Interfaces:**
- Consumes: `app.db.get_engine(url)`, `app.db.get_redis(url)`, `app.checks.async_dsn(url)`.
- Produces: `POST /api/interest` → `202 {"status":"ok"}` | `422 {"error":"invalid_email"}` | `429 {"error":"rate_limited"}`; table `interest_signup`; `app.ratelimit.hit(client, scope, subject, limit, window_s) -> bool`; constant `app.api.interest.CONSENT_VERSION = "coming-soon-v1"`.

- [ ] **Step 1: Failing tests**

`migrations/002_interest_signup.sql` is created in Step 2; first the schema test — append to `tests/test_migrate.py`:
```python
def test_002_creates_interest_signup_with_a_unique_normalised_email(scratch_db):
    applied = migrate.run(scratch_db)
    assert applied == ["001_init.sql", "002_interest_signup.sql"]
    with psycopg2.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) VALUES ('A@x.com', 'a@x.com', 'coming-soon-v1')")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) VALUES ('a@X.com', 'a@x.com', 'coming-soon-v1')")
```
(`test_applies_each_file_once_and_records_it` must now expect both files: update its two assertions to `["001_init.sql", "002_interest_signup.sql"]`.)

`tests/api/__init__.py` empty. `tests/api/test_interest.py`:
```python
import uuid

import psycopg2
import pytest

from app.api.interest import CONSENT_VERSION
from app.config import settings


def _rows(norm: str) -> list[tuple]:
    with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT email, email_normalised, consent_version, source FROM interest_signup WHERE email_normalised = %s", (norm,))
        return cur.fetchall()


@pytest.fixture
def addr():
    """A unique address per test so rate-limit windows and rows never cross tests; rows are removed after."""
    tag = uuid.uuid4().hex[:10]
    yield f"Test-{tag}@Example.org"
    with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM interest_signup WHERE email_normalised LIKE %s", (f"test-{tag}@%",))


def _ip() -> str:
    """A fresh client address per call (16M values) so per-IP windows never collide across tests or reruns."""
    n = uuid.uuid4().int
    return "10." + ".".join(str((n >> s) & 255) for s in (16, 8, 0))


async def test_new_address_is_stored_normalised_with_consent_and_source(client, db_ready, addr):
    r = await client.post("/api/interest", json={"email": f"  {addr} "}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 202 and r.json() == {"status": "ok"}
    assert _rows(addr.lower()) == [(addr, addr.lower(), CONSENT_VERSION, "coming-soon")]


async def test_duplicate_address_answers_the_same_and_keeps_one_row(client, db_ready, addr):
    ip = _ip()
    await client.post("/api/interest", json={"email": addr}, headers={"x-forwarded-for": ip})
    r = await client.post("/api/interest", json={"email": addr.upper()}, headers={"x-forwarded-for": ip})
    assert r.status_code == 202 and r.json() == {"status": "ok"}
    assert len(_rows(addr.lower())) == 1


@pytest.mark.parametrize("bad", ["", "   ", "nope", "a@b", "a b@c.com", "x@" + "y" * 250 + ".com"])
async def test_invalid_address_is_422_and_writes_nothing(client, db_ready, bad):
    r = await client.post("/api/interest", json={"email": bad}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 422 and r.json() == {"error": "invalid_email"}
    assert _rows(bad.strip().lower()) == []


async def test_missing_body_field_is_422(client):
    assert (await client.post("/api/interest", json={})).status_code == 422


async def test_sixth_request_in_a_minute_from_one_client_is_429(client, db_ready):
    ip = _ip()
    for i in range(5):
        r = await client.post("/api/interest", json={"email": f"rl-{uuid.uuid4().hex[:8]}@example.org"}, headers={"x-forwarded-for": ip})
        assert r.status_code == 202, i
    r = await client.post("/api/interest", json={"email": f"rl-{uuid.uuid4().hex[:8]}@example.org"}, headers={"x-forwarded-for": ip})
    assert r.status_code == 429 and r.json() == {"error": "rate_limited"}


async def test_fourth_attempt_for_one_address_in_a_day_is_429(client, db_ready, addr):
    for i in range(3):
        assert (await client.post("/api/interest", json={"email": addr}, headers={"x-forwarded-for": _ip()})).status_code == 202, i
    r = await client.post("/api/interest", json={"email": addr}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 429


async def test_hit_counts_within_a_window_and_denies_past_the_limit():
    # An async test on pytest's own loop (asyncio auto mode): the pooled client is then disposed by the
    # autouse `_dispose_pools` fixture. A private `asyncio.run()` loop leaked the connection and its
    # GC-time ResourceWarning failed under `-W error` (11c, 2026-09-06).
    from app.db import get_redis
    from app.ratelimit import hit

    client = get_redis(settings.redis_url)
    subject = uuid.uuid4().hex
    assert [await hit(client, "unit", subject, 2, 60) for _ in range(3)] == [True, True, False]
```
(The `rl-…@example.org` rows are cleaned by a module-level fixture: add `@pytest.fixture(autouse=True, scope="module")` that deletes `email_normalised LIKE 'rl-%'` after the module.)

`tests/perf/test_api_latency.py` — `BUDGET_MS` stays GET-only (its parametrised test issues GETs); the POST row is its own test, appended (add `import uuid`, `import psycopg2`, `from app.config import settings` at the top):
```python
async def test_interest_stored_path_p95_within_budget(client, db_ready):
    """Spec 2026-09-06 §3: the full path — validation, three Redis counters, one INSERT — at p95 ≤ 100 ms.
    Every request carries a fresh client IP and a fresh address so no rate limit trips; rows are removed after."""
    tag = uuid.uuid4().hex[:8]
    samples: list[float] = []
    try:
        for i in range(50):
            n = uuid.uuid4().int
            ip = "10." + ".".join(str((n >> s) & 255) for s in (16, 8, 0))
            t0 = time.perf_counter()
            r = await client.post("/api/interest", json={"email": f"perf-{tag}-{i}@example.org"}, headers={"x-forwarded-for": ip})
            samples.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 202, r.text
        assert statistics.quantiles(samples, n=20)[18] <= 100, "/api/interest p95 over 100 ms"
    finally:
        with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM interest_signup WHERE email_normalised LIKE %s", (f"perf-{tag}-%",))
```

Run: `poetry run pytest tests/api tests/test_migrate.py tests/perf -q -W error` → FAIL (`app.api.interest` missing; migration missing).

- [ ] **Step 2: Implement**

`migrations/002_interest_signup.sql`:
```sql
-- Coming Soon production mode (spec 2026-09-06): launch-notification sign-ups from foundation.vin.
-- No email is sent from here; the Identity wave's Resend pipeline reads this table at launch.
CREATE TABLE IF NOT EXISTS interest_signup (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  email            text        NOT NULL,
  email_normalised text        NOT NULL UNIQUE,
  consent_version  text        NOT NULL,
  source           text        NOT NULL DEFAULT 'coming-soon',
  created_at       timestamptz NOT NULL DEFAULT now()
);
```

`app/ratelimit.py`:
```python
"""Fixed-window counters in Redis (INCR + EXPIRE) — the only state the sign-up endpoint shares
across api instances. Subjects (client IP, normalised address) are hashed into the key."""
from __future__ import annotations

import hashlib
import time

from redis.asyncio import Redis


async def hit(client: Redis, scope: str, subject: str, limit: int, window_s: int) -> bool:
    """Counts one hit for `subject` in the current `window_s`-second window; True while within `limit`."""
    bucket = int(time.time()) // window_s
    key = f"rl:{scope}:{bucket}:{hashlib.sha256(subject.encode()).hexdigest()[:16]}"
    count = int(await client.incr(key))
    if count == 1:
        await client.expire(key, window_s)
    return count <= limit
```

`app/api/interest.py`:
```python
"""POST /api/interest — the Coming Soon page's launch-notification sign-up (spec 2026-09-06)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.checks import async_dsn
from app.config import settings
from app.db import get_engine, get_redis
from app.ratelimit import hit

router = APIRouter(prefix="/api")
CONSENT_VERSION = "coming-soon-v1"  # the page's promise: one message when it launches, never shared
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$")
LIMITS: dict[str, tuple[int, int]] = {"ip_minute": (5, 60), "ip_day": (30, 86_400), "email_day": (3, 86_400)}


class InterestIn(BaseModel):
    email: str


def normalise(email: str) -> str | None:
    e = email.strip()
    if len(e) > 254 or not EMAIL_RE.match(e):
        return None
    return e.lower()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/interest", status_code=202)
async def interest(body: InterestIn, request: Request) -> JSONResponse:
    norm = normalise(body.email)
    if norm is None:
        return JSONResponse({"error": "invalid_email"}, status_code=422)
    redis_ = get_redis(settings.redis_url)
    ip = client_ip(request)
    for scope, subject in (("ip_minute", ip), ("ip_day", ip), ("email_day", norm)):
        limit, window = LIMITS[scope]
        if not await hit(redis_, scope, subject, limit, window):
            return JSONResponse({"error": "rate_limited"}, status_code=429)
    engine = get_engine(async_dsn(settings.database_url))
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO interest_signup (email, email_normalised, consent_version, source) "
                "VALUES (:email, :norm, :consent, 'coming-soon') ON CONFLICT (email_normalised) DO NOTHING"
            ),
            {"email": body.email.strip(), "norm": norm, "consent": CONSENT_VERSION},
        )
    return JSONResponse({"status": "ok"}, status_code=202)
```
`app/main.py`: `from app.api.interest import router as interest_router` and `app.include_router(interest_router)` before `app.include_router(not_found_router)`.

- [ ] **Step 3: GREEN** — `poetry run pytest -q -W error` all green with the compose containers up (`db_ready` applies `002`); `poetry run mypy app --strict` clean; `poetry run ruff check app tests scripts` clean.

- [ ] **Step 4: Commit**
```bash
git add migrations/002_interest_signup.sql app/ratelimit.py app/api/interest.py app/main.py tests/api/__init__.py tests/api/test_interest.py tests/test_migrate.py tests/perf/test_api_latency.py
git commit -m "feat(api): POST /api/interest — launch-notification sign-ups with Redis rate limits

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11d: Wire the page — `submit()` posts to the API; Merriweather self-hosted; unit tests at 100 %

**Files:**
- Modify: `coming-soon/src/logic.js`, `coming-soon/index.html`, `coming-soon/vite.config.js`, `coming-soon/package.json` + `package-lock.json`, `.github/workflows/quality.yml`, `tests/test_docs.py`
- Create: `coming-soon/src/logic.test.js`, `coming-soon/public/ds/merriweather.css`, `coming-soon/public/ds/fonts/Merriweather-Latin.woff2` *(one variable-weight file — Google serves Merriweather v33 as a variable font, the same woff2 for 400 and 700; corrected 2026-09-06 after the first command returned TrueType)*, `coming-soon/public/ds/fonts/OFL-Merriweather.txt`

**Interfaces:**
- Consumes: `POST /api/interest` (11c) — `202` success, `429` rate-limited, anything else failure.

**Scope note:** the spec's three edits (§4) are the only changes to what the page ships (edit 3, `assetsDir`, landed in 11b). The test tooling this task adds — vitest devDependencies and a `test` script in `package.json`, the `test` block in `vite.config.js`, `src/logic.test.js` — is the §5 unit gate; none of it reaches `dist/`. The self-hosted font files and `merriweather.css` are edit 2 of §4.

- [ ] **Step 1: Tooling** — `cd coming-soon && npm install --save-dev vitest@3.2.7 @vitest/coverage-v8@3.2.7 jsdom@30` and add `"test": "vitest run --coverage"` to `scripts`. `vite.config.js` (which already carries `build.assetsDir = '_app'` from 11b) becomes:
```js
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  // `_app` matches the marketplace build so app/static.py's immutable-cache rule applies.
  build: { assetsDir: '_app' },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.js'],
    coverage: {
      provider: 'v8',
      include: ['src/logic.js'],   // the hand-written logic; App.vue, dc-logic.js and hover.js are the delivered page (pixel gate)
      thresholds: { lines: 100, branches: 100, functions: 100, statements: 100 }
    }
  }
});
```

- [ ] **Step 2: Failing tests** — `coming-soon/src/logic.test.js`:
```js
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Component } from './logic.js';

const make = () => new Component();
const respond = (status) => vi.fn(async () => ({ status }));

afterEach(() => vi.unstubAllGlobals());

describe('valid()', () => {
  it('accepts ordinary addresses and rejects malformed ones', () => {
    const c = make();
    expect(c.valid('you@practice.com')).toBe(true);
    expect(c.valid(' You@Practice.COM ')).toBe(true);
    for (const bad of ['', 'nope', 'a@b', 'a b@c.com', null, undefined]) expect(c.valid(bad)).toBe(false);
  });
});

describe('submit()', () => {
  it('asks for an address when the field is empty and does not call the network', async () => {
    const c = make(); vi.stubGlobal('fetch', respond(202));
    await c.submit();
    expect(c.state.error).toBe('Enter your email address.');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('rejects a malformed address without calling the network', async () => {
    const c = make(); c.state.email = 'nope'; vi.stubGlobal('fetch', respond(202));
    await c.submit();
    expect(c.state.error).toBe("That address doesn't look right. Check it and try again.");
    expect(fetch).not.toHaveBeenCalled();
  });
  it('posts the trimmed address to /api/interest and shows the confirmed state on 202', async () => {
    const c = make(); c.state.email = '  You@Practice.com '; vi.stubGlobal('fetch', respond(202));
    await c.submit();
    expect(fetch).toHaveBeenCalledWith('/api/interest', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'You@Practice.com' })
    });
    expect(c.state).toMatchObject({ done: true, error: '', email: 'You@Practice.com', sending: false });
  });
  it('explains a 429 in the error slot and stays on the form', async () => {
    const c = make(); c.state.email = 'you@practice.com'; vi.stubGlobal('fetch', respond(429));
    await c.submit();
    expect(c.state).toMatchObject({ done: false, error: 'Too many attempts — please try again later.', sending: false });
  });
  it('treats any other status as a failure the visitor can retry', async () => {
    const c = make(); c.state.email = 'you@practice.com'; vi.stubGlobal('fetch', respond(500));
    await c.submit();
    expect(c.state).toMatchObject({ done: false, error: 'Something went wrong. Please try again.', sending: false });
  });
  it('treats a network failure the same way', async () => {
    const c = make(); c.state.email = 'you@practice.com';
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    await c.submit();
    expect(c.state).toMatchObject({ done: false, error: 'Something went wrong. Please try again.', sending: false });
  });
  it('ignores a second click while a request is in flight', async () => {
    const c = make(); c.state.email = 'you@practice.com';
    let release; vi.stubGlobal('fetch', vi.fn(() => new Promise((r) => { release = () => r({ status: 202 }); })));
    const first = c.submit();
    await c.submit();
    expect(fetch).toHaveBeenCalledTimes(1);
    release(); await first;
    expect(c.state.done).toBe(true);
  });
});

describe('renderVals()', () => {
  it('maps state to the template: form/done flags, error, input border, five blocks, four rings', () => {
    const c = make(); const v = c.renderVals();
    expect(v.isForm).toBe(true); expect(v.isDone).toBe(false); expect(v.hasError).toBe(false);
    expect(v.blocks).toHaveLength(5); expect(v.rings).toHaveLength(4);
    expect(v.inputStyle).toContain('border: 1px solid #c3d4e2');
    c.state.error = 'x';
    expect(c.renderVals().inputStyle).toContain('var(--color-red)');
  });
  it('advances the teaser on poke and stops at the last quip', () => {
    const c = make();
    for (let i = 0; i < 10; i++) c.renderVals().poke();
    expect(c.renderVals().tease).toBe(c.TEASES[c.TEASES.length - 1]);
  });
  it('setEmail clears a previous error; Enter submits; reset returns to the form', async () => {
    const c = make(); c.state.error = 'old';
    c.renderVals().setEmail({ target: { value: 'you@practice.com' } });
    expect(c.state).toMatchObject({ email: 'you@practice.com', error: '' });
    vi.stubGlobal('fetch', respond(202));
    c.renderVals().onKey({ key: 'Enter' });
    await new Promise((r) => setTimeout(r, 0));
    expect(c.state.done).toBe(true);
    c.renderVals().onKey({ key: 'a' });
    c.renderVals().reset();
    expect(c.state).toMatchObject({ done: false, email: '', error: '' });
  });
});
```
Run: `cd coming-soon && npx vitest run --coverage` → FAIL (`sending` undefined, no fetch, coverage below 100).

- [ ] **Step 3: Wire `submit()`** — in `coming-soon/src/logic.js`, `state` becomes `{ email: "", error: "", done: false, pokes: 0, sending: false }` and `submit` becomes:
```js
  // Wired to the Practice Match API (spec 2026-09-06): the page's own validation runs first,
  // then one POST; 202 confirms, 429 and any failure use the error slot below the field.
  submit = async () => {
    const e = this.state.email.trim();
    if (!e) return this.setState({ error: "Enter your email address." });
    if (!this.valid(e)) return this.setState({ error: "That address doesn't look right. Check it and try again." });
    if (this.state.sending) return;
    this.setState({ sending: true, error: "" });
    try {
      const res = await fetch("/api/interest", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: e })
      });
      if (res.status === 202) return this.setState({ sending: false, error: "", done: true, email: e });
      if (res.status === 429) return this.setState({ sending: false, error: "Too many attempts — please try again later." });
      this.setState({ sending: false, error: "Something went wrong. Please try again." });
    } catch {
      this.setState({ sending: false, error: "Something went wrong. Please try again." });
    }
  };
```
Nothing else in the file changes (the README's inline-style rule stands).

- [ ] **Step 4: Self-host Merriweather** — fetch the OFL font once. Google Fonts only answers woff2 to a full Chrome user agent, and it serves Merriweather v33 as a **variable** font: the `latin` blocks for weight 400 and 700 name the same file (verified 2026-09-06: 97 608 bytes, magic `wOF2`). Pick the `latin` subset by its `/* latin */` comment:
```bash
cd coming-soon/public/ds/fonts
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
curl -fsS -A "$UA" "https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&display=swap" -o merri.css
url=$(python3 -c 'import re,sys; css=open(sys.argv[1]).read(); urls={re.search(r"url\((\S+?)\)", b).group(1) for s,b in re.findall(r"/\* (\w[\w-]*) \*/\s*@font-face \{(.*?)\}", css, re.S) if s=="latin"}; assert len(urls)==1, urls; print(urls.pop())' merri.css)
curl -fsS -o Merriweather-Latin.woff2 "$url"
rm merri.css
curl -fsS -o OFL-Merriweather.txt https://raw.githubusercontent.com/SorkinType/Merriweather/master/OFL.txt
file Merriweather-Latin.woff2      # Web Open Font Format (Version 2), TrueType
head -c 4 Merriweather-Latin.woff2 # wOF2
```
If `file` does not report WOFF2 or the `assert` fails, STOP and report. `coming-soon/public/ds/merriweather.css`:
```css
/* Merriweather (SIL Open Font License, see fonts/OFL-Merriweather.txt) — self-hosted so the page
   makes no third-party request and pixel tests are deterministic (README: "self-host before launch").
   One variable-weight file (Google Fonts v33, latin subset) covers the 400 and 700 the page uses. */
@font-face { font-family: 'Merriweather'; font-style: normal; font-weight: 400 700; font-display: swap; src: url('/ds/fonts/Merriweather-Latin.woff2') format('woff2'); }
```
`coming-soon/index.html`: replace the two `<link rel="preconnect" …>` lines and the Google Fonts `<link rel="stylesheet" …>` with `<link rel="stylesheet" href="/ds/merriweather.css" />`, and change the comment above them to `<!-- Merriweather carries headlines per the VIN Foundation Brand Style Guide 2026 §05 — self-hosted (OFL). -->`. No other change to the file.

- [ ] **Step 5: CI** — `.github/workflows/quality.yml` gains a job:
```yaml
  coming-soon:
    name: coming-soon (unit at 100% · build)
    runs-on: ubuntu-latest
    timeout-minutes: 15
    defaults:
      run: { working-directory: coming-soon }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm', cache-dependency-path: coming-soon/package-lock.json }
      - run: npm ci
      - run: npx vitest run --coverage
      - run: npm run build
```
`tests/test_docs.py` — in `test_ci_workflow_runs_every_gate` the job-set assertion becomes `assert {"gitleaks", "backend", "frontend", "coming-soon"} <= set(wf["jobs"])` (RED first). `REQUIRED_CI_COMMANDS` is unchanged: `npx vitest run --coverage` and `npm run build` already appear there and now describe both Node jobs. The timeout test iterates every job, so it covers the new one without change.

- [ ] **Step 6: GREEN** — `cd coming-soon && npx vitest run --coverage` → all tests pass, coverage 100/100/100/100; `npm run build` → `dist/_app/*.js`; `poetry run pytest tests/test_docs.py -q -W error` green; the page in `npm run preview` renders Merriweather headlines with the network tab showing no `fonts.googleapis.com` request (record).

- [ ] **Step 7: Commit**
```bash
git add coming-soon/src/logic.js coming-soon/src/logic.test.js coming-soon/index.html coming-soon/vite.config.js coming-soon/package.json coming-soon/package-lock.json coming-soon/public/ds/merriweather.css coming-soon/public/ds/fonts/Merriweather-Latin.woff2 coming-soon/public/ds/fonts/OFL-Merriweather.txt .github/workflows/quality.yml tests/test_docs.py
git commit -m "feat(coming-soon): sign-up posts to /api/interest; Merriweather self-hosted; logic unit-tested at 100 %

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11e: Pixel gate against `Coming Soon.dc.html` — WAITS for John's design export (NEEDS_HUMAN if `docs/design-reference/coming-soon/Coming Soon.dc.html` is absent); does not block 11f or the production deploy

**Files:**
- Create: `docs/design-reference/coming-soon/` (John's export: `Coming Soon.dc.html` + its runtime files as exported), `frontend/tests/coming-soon.screens.ts`, `frontend/tests/coming-soon-visual.spec.ts`, `frontend/tests/coming-soon-reference.spec.ts`
- Modify: `frontend/tests/reference-server.mjs` (serve `/coming-soon/` from the new folder), `frontend/tests/playwright.config.ts` + `frontend/tests/targets.ts` (two more projects and a third local server), `.github/workflows/quality.yml` (run the two new projects after the existing ones)

**Interfaces:**
- Produces: Playwright projects `coming-soon-reference` (design at `http://localhost:5174/coming-soon/`) and `coming-soon` (Vite dev server for `coming-soon/` on `http://localhost:5175`, `npm run dev -- --port 5175 --strictPort` with `cwd: ../coming-soon`); baselines `frontend/tests/visual.spec.ts-snapshots/cs-<state>-<platform>.png`.

- [ ] **Step 1:** If the design file is absent → STOP, `NEEDS_HUMAN`: "Provide the Claude Design export of `Coming Soon.dc.html` (with its support runtime) into `docs/design-reference/coming-soon/`." Otherwise continue.
- [ ] **Step 2: Screens** — `frontend/tests/coming-soon.screens.ts`:
```ts
import type { Page } from '@playwright/test';

export interface CsScreen { name: string; viewport?: { width: number; height: number }; steps: (page: Page) => Promise<void>; }
const field = (p: Page) => p.getByLabel('Email address');
const notify = (p: Page) => p.getByRole('button', { name: /notify/i }).first();

export const CS_SCREENS: CsScreen[] = [
  { name: 'cs-idle', steps: async () => {} },
  { name: 'cs-invalid', steps: async (p) => { await field(p).fill('nope'); await notify(p).click(); } },
  { name: 'cs-done', steps: async (p) => { await field(p).fill('you@practice.com'); await notify(p).click(); await p.getByText("You're on the list").waitFor(); } },
  { name: 'cs-tease-2', steps: async (p) => { const b = p.getByRole('button', { name: /Redacted/ }); await b.click(); await b.click(); } },
  { name: 'cs-mobile', viewport: { width: 390, height: 844 }, steps: async () => {} }
];
```
(Read the exact button label from the design's `App.vue`/design file — `notify` matches the design's copy; if the copy differs, use the exact text.) The `coming-soon` project's `prepare()` routes `POST **/api/interest` → `route.fulfill({ status: 202, contentType: 'application/json', body: '{"status":"ok"}' })` so `cs-done` needs no backend; the design's own submit sets `done` without a network call.
- [ ] **Step 3:** Reference spec writes `cs-*` baselines from the design (same pattern as `reference-baselines.spec.ts`, using `document.fonts.ready` + 600 ms settle); visual spec compares the app at `maxDiffPixels: 0`. Both projects added to `playwright.config.ts` via `targets.ts` (unit-tested: `PW_APP_URL` does not affect the coming-soon projects). CI runs `--project=coming-soon-reference` then `--project=coming-soon` in the frontend job.
- [ ] **Step 4:** All `cs-*` states pass at 0 px. Commit — `test(coming-soon): zero-pixel parity with the approved Coming Soon design, five states`.

---

### Task 11f: Mode-aware deploy verification and the production step

**Files:**
- Modify: `scripts/verify-deploy.sh`, `tests/scripts/test_verify_deploy.sh`, `DEPLOY.md`, `tests/test_docs.py`; and Task 10 Step 4 (below) is superseded by this task's production procedure.

- [ ] **Step 1: Failing shell cases** — in `tests/scripts/test_verify_deploy.sh` the fake server gains modes `coming_ok` (healthz `site_mode: "coming_soon"`, `/` and `/browse` bodies contain `<title>VIN Foundation — Coming Soon</title>`, `POST /api/interest` with an invalid address → 422), `coming_wrong_shell` (`site_mode: "coming_soon"` but the marketplace shell `id="app"` without the title), `coming_interest_500` (POST → 500), and the existing `ok` body gains `"site_mode": "app"`. Cases: coming_ok → exit 0, prints `coming-soon shell OK` and `interest endpoint OK`; coming_wrong_shell → non-zero, message `coming-soon shell missing`; coming_interest_500 → non-zero, message names `interest`; a body WITHOUT `site_mode` → non-zero, `site_mode missing`. Run → FAIL (today's script ignores `site_mode`).
- [ ] **Step 2: Script** — after the healthz parse (which now also asserts `site_mode` is present and prints it), replace the SPA block with:
```bash
mode=$(curl -fsS --max-time 20 "$BASE/api/healthz" | python3 -c 'import sys,json; print(json.load(sys.stdin)["site_mode"])')
if [[ "$mode" == "coming_soon" ]]; then
  for path in / /browse; do
    curl -fsS --max-time 20 "$BASE$path" | grep -q '<title>VIN Foundation — Coming Soon</title>' \
      || { echo "FAIL: coming-soon shell missing at $BASE$path" >&2; exit 1; }
  done
  echo "coming-soon shell OK"
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -X POST -H 'Content-Type: application/json' -d '{"email":"not-an-email"}' "$BASE/api/interest")
  [[ "$code" == "422" ]] || { echo "FAIL: interest endpoint answered $code to an invalid address (expected 422)" >&2; exit 1; }
  echo "interest endpoint OK"
else
  curl -fsS --max-time 20 "$BASE/browse" | grep -q 'id="app"' \
    || { echo "FAIL: SPA fallback missing at $BASE/browse" >&2; exit 1; }
  echo "SPA fallback OK"
fi
```
(The healthz python block adds `mode = b.get("site_mode"); assert mode, f"FAIL: site_mode missing from healthz: {b}"` and prints `site_mode`, then the shell re-reads it as above — or export it from the python block via a temp file; either is fine, tested by the `site_mode missing` case.)
- [ ] **Step 3: Docs** — `DEPLOY.md` "Deploy" section: expected verify output in coming-soon mode (`healthz OK … site_mode coming_soon`, `deep healthz OK`, `coming-soon shell OK`, `interest endpoint OK`); the drift test asserts `coming-soon shell OK` appears in `DEPLOY.md`.
- [ ] **Step 4: GREEN** — both shell tests green; live: `EXPECT_SHA=<deployed> scripts/verify-deploy.sh QA https://qa.foundation.vin` still passes in app mode (QA is unchanged). Commit — `fix(deploy): verify-deploy is site-mode aware — coming-soon shell and interest endpoint on production, SPA shell on QA`.

**Production step (supersedes Task 10 Step 4; John's go given 2026-09-06 — re-confirm the QA state to him in the pause report before running it):**
1. 🚦 `railway status` → `Project: Practice Match`.
2. `railway variable set SITE_MODE=coming_soon --service api --environment production --skip-deploys`; same for `--service worker`; `railway variable set PUBLIC_INDEXING=true --service api --environment production --skip-deploys`. QA gets `SITE_MODE=app` explicitly on both services (`--environment QA`) so the matrix is stated, not defaulted. List keys (redacted) and record.
3. Tree clean → `scripts/deploy.sh production` (verifies at HEAD in coming-soon mode) — expected `healthz OK … site_mode coming_soon`, `deep healthz OK`, `coming-soon shell OK`, `interest endpoint OK`, `commit_sha == HEAD`. Then the same verify against `https://api-production-ebcf.up.railway.app`.
4. Read-only checks: `curl -sI https://foundation.vin/` has no `X-Robots-Tag`; `curl -fsS https://foundation.vin/robots.txt` is `User-agent: *\nAllow: /`; the served `/` contains the coming-soon title and NOT `<title>Practice Match`; `curl -fsS https://qa.foundation.vin/api/healthz` still reports `site_mode app` (QA untouched).
5. On any failure: roll back (dashboard → api → Deployments → last good → Redeploy; there is no previous production deployment, so instead `railway variable set SITE_MODE=…` is irrelevant — the failure state is Railway's fallback 404 page as before) and STOP with the logs.
6. Task 10 Steps 5–6 (worker round-trip, spec status line "live on qa.foundation.vin (marketplace) and foundation.vin (coming soon)", hand-back) follow; the hand-back names both sites and the launch flip.

---

## Red-team review (2026-09-05) — findings and dispositions

| # | Finding | Severity | Disposition |
|---|---|---|---|
| F1 | Deep links bypassed the fixture gate: `routeToPatch` set a member screen while `auth=false`, and `renderVals` shows a screen by `state.screen` alone. The smoke test asserting the gate would have failed. | High | Fixed in Task 2: `guard()` applies the prototype's `go()` semantics (gate + remembered route, applied when `auth` flips); state→route watcher pauses while a route is pending. Spec §3 corrected. |
| F2 | Visual harness depended on unpkg at CI time (React/ReactDOM/Babel loaded by `support.js`). An unpkg outage = red CI, and reference rendering could drift with CDN changes. | Medium | Fixed in Task 3: vendored the three SRI-pinned files; `prepare()` fulfils `https://unpkg.com/**` from disk on both targets. |
| F3 | `commit_sha` would read `dev` on every deploy — `railway up` builds are not git-connected. | Medium | Fixed in Tasks 7–8: `deploy.sh` sets `COMMIT_SHA` per service before upload; Dockerfile `ARG COMMIT_SHA`. |
| F4 | Two public prototype hosts with fixture listings and a fictional admin console were indexable. | Medium | Fixed in Task 5: `X-Robots-Tag: noindex, nofollow` + `robots.txt` disallow until `PUBLIC_INDEXING=true`. |
| F5 | `VITE_ENVIRONMENT` via Docker `ARG` from a Railway service variable was asserted, not verified. | Low | Task 8 step 8 now verifies the jump bar on QA and names the runtime-config fallback. |
| F6 | `updateSnapshots: 'none'` + a missing baseline: confirmed Playwright fails (desired). | Info | No change. |
| F7 | Two `railway up` builds per deploy (api, worker) double build time. | Low | Accepted — Rounds pattern; revisit with a registry image if builds exceed ~8 min. |
| F8 | `routeToPatch` + `jumpTo` interplay: `jumpTo` sets auth and screen together, so the pending-route logic never fires for jump-bar navigation. | Info | Verified by reading `logic.js:154`; no change. |
| F9 | The design's access-state shortcuts remain on production (anyone "enters" the prototype). | Accepted risk | John's decision 2026-09-05; removed in Sub-project 2; called out in the hand-back. |
| F10 | `railway environment new QA --duplicate production` duplicates the database service with the template's rolling image tag. | Low | Task 8 step 6 already repeats the image pin for QA. |

## Self-review (run by the plan author before hand-off)

- **Spec coverage:** §1 scope → Tasks 1–10; §2 layout/stack → Tasks 1, 5, 7, 9; §3 frontend edits (paths, Leaflet, router, env props, DS cascade) → Tasks 1–2; §4 harness (state table, two targets, determinism, tolerance, 25 states) → Tasks 3–4 (+ CI regeneration in Task 9); §5 backend (healthz bodies, deep, SPA, config fail-fast, migrations, Celery/roles) → Tasks 5–7; §6 Railway/DNS/deploy loop → Tasks 8, 10; §7 CI/docs → Task 9; §8 tests → every task; §9 hand-offs → Task 10; §10 DoD → Task 10 step 6.
- **Deviation from spec, recorded:** baselines are regenerated from the reference in every CI run rather than committed as Linux PNGs (spec §4 said "committed"). Simpler, no binary churn, same oracle. The spec is amended in the same commit as this plan.
- **Placeholder scan:** no TBD/TODO; the only intentionally blank cells are the two DNS values Railway prints at Task 8 step 7, filled in Task 10 step 2.
- **Type consistency:** `stateToRoute/routeToPatch/needsPatch/sameLocation` names match across Task 2 files and tests; `SCREENS`/`Screen`, `prepare/booted/settle/jump/click/btn/waitMap` match across Tasks 3–4 and 10; `check_db/check_redis/create_app(dist)` match Tasks 5–7; `run(dsn, directory)`/`normalize_dsn` match Task 6 tests and conftest; `SKIP_VERIFY` matches Task 8 script and test.
