# Practice Match Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Practice Match repo, Railway topology and domains, and ship the approved Claude Design as a pixel-faithful Vue app (fixture data) to `qa.foundation.vin` and `foundation.vin`, with an automated visual gate proving fidelity.

**Architecture:** One Docker image (Node builds `frontend/dist`, Python serves it + `/api/*`) deployed as Railway services `api` and `worker`, alongside `Postgres` (PostGIS) and `Redis`, in environments `QA` and `production`. The frontend is the handoff `vue-app/` verbatim plus a router sync layer around the untouched `logic.js`. A Playwright harness screenshots the reference `.dc.html` per screen state and asserts the Vue app matches.

**Tech Stack:** Vue 3.5 · Vite · vue-router 4 · TypeScript (new code only) · vitest · @playwright/test · leaflet 1.9.4 · Python 3.12 · Poetry 2.4.1 · FastAPI · SQLAlchemy 2 async + asyncpg · psycopg2-binary · Celery 5 + redis · pydantic-settings · pytest · Docker · Railway CLI ≥ 5.26

**Spec:** `docs/superpowers/specs/2026-09-05-practice-match-foundation-design.md` (read §3–§6 before any task that touches those areas).

## Global Constraints

- Ported files stay byte-identical except for the edits this plan names: `frontend/src/App.vue`, `logic.js`, `dc-logic.js`, `directives/hover.js`, `lib/leaflet.js`, `components/*.vue`. No restyling, no inline-style extraction, no copy edits, no renames, no Pinia, no per-screen split.
- The only edits to ported files: (a) `assets/` → `/assets/`, `ds/` → `/ds/` path prefixes; (b) `lib/leaflet.js` loader body (npm import, same exported API); (c) two lines in `App.vue`'s `<script setup>` to install the router sync composable; (d) `prototypeBar` default sourced from `import.meta.env`.
- `logic.js` is never edited except for the four `assets/photos/` path prefixes on lines 394–396 and 431.
- Route table (exact): `/`→`gate`; `/browse` + `?tab=listings|market` ↔ `browseMode`; `/practices/:id` ↔ `detailId`; `/requests`; `/seller`; `/admin` + `?tab=users|listings|activity|data` ↔ `adminTab`; unknown → `/`.
- Visual tolerance: `maxDiffPixels: 0, threshold: 0.1`; ceiling if relaxed `maxDiffPixelRatio: 0.001`, recorded in `playwright.config.ts` with the reason.
- Basemap tile hosts are aborted in both harness targets: `**/*.arcgisonline.com/**`.
- Health body (exact keys): `status, version, environment, commit_sha, db{ok, postgis_version|error}, redis{ok|error}`. `/api/healthz` is always 200; `/api/healthz/deep` is 503 when `db.ok` or `redis.ok` is false.
- `frontend/package.json` `version` == `pyproject.toml` `[project].version` (starts `0.1.0`).
- Fingerprinted build output goes to `dist/_app/` (Vite `build.assetsDir: '_app'`) so `/assets/*` (icons, photos, logo) is never served with immutable caching.
- Every commit: conventional message, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, pushed to both `origin` and `production`.
- Secrets never appear in git, chat, or `.env.example` values. `CENSUS_API_KEY` is set on `worker` out-of-band (John holds it).
- Before any `railway up`, variable change or service mutation: `railway status --json` must report project `Practice Match` — abort otherwise.
- Node 22 for builds (`nvm use 22`; `.nvmrc` = `22`). Python 3.12 (`poetry env use python3.12`).
- Work on branch `feat/foundation` in a worktree; `main` receives the merge at the end.

## Source material

- Handoff bundle (extracted copy available at `/private/tmp/claude-502/-Users-johndean-Development-Practice-Match/39b87aac-a222-47b1-8bec-a538c22fdc1f/scratchpad/design/small/design_handoff_practice_match_v2`; canonical zip: `/Users/johndean/Downloads/VIN FOUNDATION/Claude Design zips/Vin Foundation Marketplace Design.zip`). If the scratchpad copy is gone, `unzip` the zip into a temp dir; the bundle root is `design_handoff_practice_match_v2/`.
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

- [ ] **Step 13: Commit**

```bash
cd "/Users/johndean/Development/Practice Match"
git add -A
git commit -m "feat(frontend): import approved handoff, absolute asset paths, bundled Leaflet, DS cascade

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push origin feat/foundation && git push production feat/foundation
```

---

### Task 2: Router sync layer (vue-router around the untouched logic)

**Files:**
- Create: `frontend/src/router/routes.ts`, `frontend/src/router/sync.ts`, `frontend/src/router/sync.test.ts`, `frontend/src/router/useStateRouteSync.ts`, `frontend/src/main.ts`
- Modify: `frontend/src/App.vue:1295-1318` (script block only: two added lines + `prototypeBar` default), delete `frontend/src/main.js`

**Interfaces:**
- Produces: `stateToRoute(state: RoutedState): RouteTarget`; `routeToPatch(to: {path: string; params: Record<string, unknown>; query: Record<string, unknown>}): Partial<RoutedState>`; `needsPatch(state, patch): boolean`; `sameLocation(a: RouteTarget, b: {path: string; query: Record<string, unknown>}): boolean`; `useStateRouteSync(component, router)`.
- Consumes: `Component` from `logic.js` — `state.screen`, `state.browseMode`, `state.detailId`, `state.adminTab`, `setState(patch)`.

- [ ] **Step 1: Write the failing sync tests**

`frontend/src/router/sync.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { stateToRoute, routeToPatch, needsPatch, sameLocation } from './sync';

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
export interface RoutedState { screen: string; browseMode?: string; detailId?: string; adminTab?: string }
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
import { needsPatch, routeToPatch, sameLocation, stateToRoute, type RoutedState } from './sync';

interface StatefulComponent { state: RoutedState; setState(patch: Partial<RoutedState>): void }

// Two one-way bindings with loop guards. Route → state is applied first so a
// deep link is honoured before the state → route watcher can rewrite the URL.
export function useStateRouteSync(c: StatefulComponent, router: Router): void {
  const apply = (to: { path: string; params: Record<string, unknown>; query: Record<string, unknown> }) => {
    const patch = routeToPatch(to);
    if (needsPatch(c.state, patch)) c.setState(patch);
  };
  apply(router.currentRoute.value);
  router.afterEach((to) => apply(to));
  watch(
    () => stateToRoute(c.state),
    (loc) => {
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

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/foundation && git push production feat/foundation
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
```

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

export type JumpLabel = 'Access' | 'Browse' | 'Listing' | 'Requests' | 'Seller' | 'Admin';

// Deterministic rendering on both targets: no basemap tiles (markers still draw
// over the blank canvas), fonts loaded, pointer parked, animations settled.
export async function prepare(page: Page): Promise<void> {
  await page.route(/arcgisonline\.com/, (route) => route.abort());
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
  { name: 'interest-modal', steps: async (p) => { await jump(p, 'Listing'); await click(p, "I'm interested"); } },
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
git push origin feat/foundation && git push production feat/foundation
```

---

### Task 4: Visual parity to GREEN, plus route smoke tests

**Files:**
- Create: `frontend/tests/smoke.spec.ts`
- Modify (only if a diff demands it, and only these): `frontend/index.html`, `frontend/src/styles/global.css`, `frontend/src/styles/tokens.css`, `frontend/tests/harness.ts`, `frontend/tests/screens.ts`, `frontend/tests/playwright.config.ts`

**Interfaces:** none new.

- [ ] **Step 1: Triage each RED state from Task 3**

For every failing state open `frontend/test-results/**/<name>-diff.png` (Read tool). Classify the diff:

| Diff looks like | Allowed fix |
|---|---|
| Whole-page vertical offset / default spacing on `<p>`, `<h*>`, `<ul>`, `<button>` | The DS cascade is wrong: confirm `index.html` links the three `/ds/*.css` files in the reference's order (Task 1 step 11) and that `tokens.css`/`global.css` load after them (check `<head>` order in the served page). |
| Text anti-aliasing weight differs everywhere | `_preview.css` `-webkit-font-smoothing` not applied → same cascade check. |
| Map area differs only inside the Leaflet canvas | Timing: raise `waitMap` delay to 1000 ms in `harness.ts` (both targets use it). |
| Hover styling on one element | Pointer not parked: `settle()` already moves to (0,0); add `await page.mouse.move(0, 0)` before the step that opens a menu. |
| Modal/menu missing or extra | Selector clicked a different element; fix the locator in `screens.ts` (both targets). |
| A colour, size, or copy difference inside the design itself | **STOP.** Do not edit ported templates or styles. Report `DONE_WITH_CONCERNS` naming the state and attaching the diff path. |

- [ ] **Step 2: Re-run until GREEN**

Run: `npm run test:visual`
Expected: `25 passed`. If a residual diff is provably sub-pixel anti-aliasing (a few isolated pixels on glyph edges, nothing structural), relax `toHaveScreenshot` to `maxDiffPixelRatio: 0.001` (delete `maxDiffPixels`) and add a comment in `playwright.config.ts` naming the states and the date. Never go above 0.001.

- [ ] **Step 3: Write the failing smoke spec** — `frontend/tests/smoke.spec.ts`

```ts
import { test, expect, type Page } from '@playwright/test';
import { prepare } from './harness';

const ROUTES = ['/', '/browse', '/browse?tab=market', '/practices/p1', '/requests', '/seller', '/admin?tab=data'];

function trapErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  return errors;
}

test.describe('smoke', () => {
  for (const r of ROUTES) {
    test(`${r} renders the gate for a signed-out visitor without errors`, async ({ page }) => {
      await prepare(page);
      const errors = trapErrors(page);
      await page.goto(r);
      await expect(page.getByText('Approved members only')).toBeVisible();
      expect(errors).toEqual([]);
    });
  }

  test('a deep link is honoured after the fixture sign-in', async ({ page }) => {
    await prepare(page);
    await page.goto('/browse?tab=market');
    await page.getByRole('button', { name: 'Approved — enter', exact: true }).click();
    await expect(page).toHaveURL(/\/browse\?tab=market$/);
    await expect(page.getByRole('button', { name: 'Data Layers', exact: true })).toBeVisible();
  });

  test('navigation writes the URL', async ({ page }) => {
    await prepare(page);
    await page.goto('/');
    await page.getByRole('button', { name: 'Browse', exact: true }).first().click();
    await expect(page).toHaveURL(/\/browse$/);
    await page.getByText('Market Data', { exact: true }).first().click();
    await expect(page).toHaveURL(/\/browse\?tab=market$/);
    await page.getByRole('button', { name: 'Listing', exact: true }).first().click();
    await expect(page).toHaveURL(/\/practices\/p1$/);
    await page.getByRole('button', { name: 'Admin', exact: true }).first().click();
    await page.getByRole('button', { name: /^Data Sources\s*\d/ }).first().click();
    await expect(page).toHaveURL(/\/admin\?tab=data$/);
  });

  test('unknown routes redirect to /', async ({ page }) => {
    await page.goto('/definitely-not-a-route');
    await expect(page).toHaveURL(/\/$/);
  });
});
```

- [ ] **Step 4: Run — expect RED on at least one test, or explain why not**

Run: `npm run test:smoke`
Expected: if Task 2 is correct, these pass immediately — that is acceptable here because the behaviour under test was built (and unit-tested) in Task 2; the smoke spec is its end-to-end confirmation. If a test fails, the router wiring in `useStateRouteSync.ts` is wrong — fix it there, not in the test.

- [ ] **Step 5: Full frontend gate**

Run: `npm run typecheck && npm test && npm run build && npm run test:smoke && npm run test:visual` → all green.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "test(frontend): visual parity green (25 states) and route smoke suite

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/foundation && git push production feat/foundation
```

---

### Task 5: FastAPI skeleton — config (fail-fast), version, health endpoints, SPA serving

**Files:**
- Create: `pyproject.toml`, `app/__init__.py`, `app/config.py`, `app/version.py`, `app/checks.py`, `app/api/__init__.py`, `app/api/health.py`, `app/static.py`, `app/main.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_config.py`, `tests/test_versions.py`, `tests/test_health.py`, `tests/test_static.py`

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

- [ ] **Step 2: Failing tests — config fail-fast and version lockstep**

`tests/conftest.py` (env defaults must be set before any `app.*` import; ports 5433/6380 avoid a local Postgres/Redis):
```python
import os

os.environ.setdefault("DATABASE_URL", "postgresql://pm:pm_dev_pw@localhost:5433/practice_match")
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("API_SECRET_KEY", "test_only_secret_change_me")
```

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
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url="http://test") as c:
        yield c


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

from app.api.health import not_found_router, router as health_router
from app.config import settings
from app.static import DIST, mount_spa
from app.version import VERSION


def create_app(dist: Path | None = None) -> FastAPI:
    app = FastAPI(title="Practice Match API", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
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

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/foundation && git push production feat/foundation
```

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

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/foundation && git push production feat/foundation
```

---

### Task 7: Celery skeleton, role dispatcher, Docker image, Railway config

**Files:**
- Create: `app/tasks/__init__.py`, `app/tasks/celery_app.py`, `tests/test_celery.py`, `scripts/start.sh`, `Dockerfile`, `.dockerignore`, `railway.json`, `.railwayignore`, `scripts/verify-image.sh`

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
ARG RAILWAY_GIT_COMMIT_SHA=dev
WORKDIR /work/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_ENVIRONMENT=$ENVIRONMENT
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ARG RAILWAY_GIT_COMMIT_SHA=dev
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=2.4.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_NO_CACHE_DIR=1 \
    COMMIT_SHA=$RAILWAY_GIT_COMMIT_SHA
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

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/foundation && git push production feat/foundation
```

---

### Task 8: Railway project, services, environments, domains, guarded deploy scripts — first QA deploy

**Files:**
- Create: `scripts/deploy.sh`, `scripts/verify-deploy.sh`, `tests/scripts/test_deploy_guard.sh`
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
for svc in api worker; do
  echo "→ railway up --environment $ENV --service $svc --ci"
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
Expected: `healthz OK  version 0.1.0 … postgis 3.5.x`, `deep healthz OK`, `SPA fallback OK`. Open `$QA_URL` in the Playwright MCP browser (or `curl`) and confirm the gate renders with the jump bar (QA build).

- [ ] **Step 9: Commit the scripts**

```bash
git add scripts tests/scripts && git commit -m "feat(deploy): guarded railway deploy + post-deploy verification scripts

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/foundation && git push production feat/foundation
```

---

### Task 9: CI and working docs

**Files:**
- Create: `.github/workflows/quality.yml`, `.gitleaks.toml`, `CLAUDE.md`, `DEPLOY.md`, `README.md`, `.env.example`, `.claude/skills/practice-match-workflow/SKILL.md`

**Interfaces:** none new; CI consumes every script/test from Tasks 1–8.

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
- **Ported files are byte-identical** except the edits listed in `docs/superpowers/specs/2026-09-05-practice-match-foundation-design.md` §3. `logic.js` is never restructured. Inline styles stay inline. No CSS framework, no Pinia, no per-screen split without a visual diff per screen.
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

- [ ] **Step 7: Push and watch CI in both repos**

```bash
git add -A && git commit -m "ci(quality): gitleaks, pytest on PostGIS, frontend gates incl. visual parity; working docs

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push origin feat/foundation && git push production feat/foundation
gh run list --repo johndean/practice-match --branch feat/foundation --limit 3
gh run list --repo vin-swe/practice-match --branch feat/foundation --limit 3
gh run watch --repo johndean/practice-match "$(gh run list --repo johndean/practice-match --branch feat/foundation --limit 1 --json databaseId -q '.[0].databaseId')"
```
Expected: `gitleaks`, `backend`, `frontend` all green in both repos. A red `frontend/visual` step means Linux Chromium renders a state differently from darwin — download the `playwright-report` artifact, inspect the diff, and apply Task 4's triage table (harness timing/selector fixes only; a design-level diff is `DONE_WITH_CONCERNS`).

---

### Task 10: DNS, production deploy, live verification, hand-back

**Files:**
- Modify: `DEPLOY.md` (DNS values), `docs/superpowers/specs/2026-09-05-practice-match-foundation-design.md` (status line), `frontend/tests/playwright.config.ts` (live-target override)

**Interfaces:** `PW_APP_URL=<https://host>` makes the `app` project target a live deployment (no local dev server).

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

- [ ] **Step 4: Production**

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

Update the spec's status line to `Implemented 2026-09-__ — live on qa.foundation.vin and foundation.vin` and commit. Then write the hand-back:
- **Forwardable summary** (no jargon): Practice Match is live at foundation.vin as the approved design with sample listings; the sign-in is a preview until member accounts arrive; the team test site is qa.foundation.vin.
- **Engineer's note:** version, commit, both remotes pushed, CI green in both repos, visual suite 25/25 on QA, production smoke, worker ping; explicitly list anything not verified (e.g. Linux-vs-macOS rendering if the tolerance was relaxed) and the VIN Foundation open items (basemap licence, mobile breakpoint).

- [ ] **Step 7: Finish the branch**

Use superpowers:finishing-a-development-branch: merge `feat/foundation` → `main`, push `main` to both remotes, delete the branch, then invoke the Census data-layer plan.

---

## Self-review (run by the plan author before hand-off)

- **Spec coverage:** §1 scope → Tasks 1–10; §2 layout/stack → Tasks 1, 5, 7, 9; §3 frontend edits (paths, Leaflet, router, env props, DS cascade) → Tasks 1–2; §4 harness (state table, two targets, determinism, tolerance, 25 states) → Tasks 3–4 (+ CI regeneration in Task 9); §5 backend (healthz bodies, deep, SPA, config fail-fast, migrations, Celery/roles) → Tasks 5–7; §6 Railway/DNS/deploy loop → Tasks 8, 10; §7 CI/docs → Task 9; §8 tests → every task; §9 hand-offs → Task 10; §10 DoD → Task 10 step 6.
- **Deviation from spec, recorded:** baselines are regenerated from the reference in every CI run rather than committed as Linux PNGs (spec §4 said "committed"). Simpler, no binary churn, same oracle. The spec is amended in the same commit as this plan.
- **Placeholder scan:** no TBD/TODO; the only intentionally blank cells are the two DNS values Railway prints at Task 8 step 7, filled in Task 10 step 2.
- **Type consistency:** `stateToRoute/routeToPatch/needsPatch/sameLocation` names match across Task 2 files and tests; `SCREENS`/`Screen`, `prepare/booted/settle/jump/click/btn/waitMap` match across Tasks 3–4 and 10; `check_db/check_redis/create_app(dist)` match Tasks 5–7; `run(dsn, directory)`/`normalize_dsn` match Task 6 tests and conftest; `SKIP_VERIFY` matches Task 8 script and test.
