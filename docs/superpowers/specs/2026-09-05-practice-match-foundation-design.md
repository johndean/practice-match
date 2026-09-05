# Practice Match — Foundation (Sub-project 1) — Design

| | |
|---|---|
| Date | 2026-09-05 |
| Status | Approved in conversation; awaiting written-spec review |
| Owner | John Dean |
| Product | Practice Match — VIN Foundation veterinary practice marketplace (internal working title; public name TBD by the VIN Foundation) |
| Domains | Production `https://foundation.vin` · QA `https://qa.foundation.vin` |
| Repos | `origin` = `vin-swe/practice-match` (QA/dev, internal) · `production` = `johndean/practice-match` |

## 0. Context and decisions

Practice Match was designed in Claude Design and handed off as a bundle
(`design_handoff_practice_match_v2/`, from
`/Users/johndean/Downloads/VIN FOUNDATION/Claude Design zips/Vin Foundation Marketplace Design.zip`;
canvas: `https://claude.ai/design/p/3047ec64-fe8c-4f97-9c16-50e41f780147?file=Practice+Match+V2.dc.html`).
The bundle contains three approved artifacts:

1. **`Practice Match V2.dc.html`** — the approved design. The single source of truth for every pixel.
2. **`vue-app/`** — a mechanical 1:1 Vue 3 conversion of the design: `App.vue` is the template with every inline style, dimension, colour and word of copy byte-identical; `logic.js` is the prototype's logic class verbatim; maps and the image slot are ported components.
3. **`Census Data Source Specification.dc.html`** — the approved contract for the market-data layer (datasets, formulas, schema, caching, licensing).

The work decomposes into three sub-projects. **This spec covers Sub-project 1 only.**

| Sub-project | Deliverable | Design input |
|---|---|---|
| **1 — Foundation (this spec)** | Repo, Railway, domains, CI, working docs, and the pixel-faithful Vue app on the design's fixture data, live on QA and production | this document |
| 2 — Application backend | Own auth + access approval, listings + wizard, photos, interest requests, document locks, admin console | its own spec (next) |
| 3 — Market-data layer | The Census spec implemented: PostGIS schema, ingest workers, derived metrics, materialisation, tiles, licence gates | the approved Census spec; implementation plan written after this spec is approved |

Decisions taken with John on 2026-09-05:

- **Backend shape:** FastAPI + Celery worker, the Rounds.vin topology (one Docker image, `api` + `worker` services, Postgres with PostGIS, Redis). Chosen because the Census layer is a batch-ingest + PostGIS problem and John already runs this exact shape in production.
- **Identity:** own email + password auth (FastAPI JWT), designed so Flowint SSO can be layered in later as Po.vin's hybrid login. Implemented in Sub-project 2; nothing in this spec depends on it.
- **Deploys:** manual `railway up` per environment (Po.vin pattern). No git auto-deploy.
- **`foundation.vin` is attached now**, before real authentication exists. The prototype (fixture data, design's fake sign-in) is publicly reachable; the jump bar is off in production. John accepted this explicitly.
- **Handoff `vue-app/` is the base of the frontend** (TDD's generated-code exception, granted by John). TDD governs everything added around it.

## 1. Scope

**In scope**

- Git repo with both remotes; conventional commits; every commit pushed to both.
- Railway project `Practice Match`: environments `production` and `QA`; services `api`, `worker`, `Postgres` (PostGIS), `Redis` in each.
- `qa.foundation.vin` and `foundation.vin` on the `api` service of their environment.
- The Vue app from the handoff, running on its fixture data, with vue-router, self-hosted assets and a vendored Leaflet — every screen in the design's screen map rendering on QA and production.
- The visual-fidelity harness: Playwright baselines generated from the reference `.dc.html`, asserted against the Vue app, enforced in CI.
- FastAPI skeleton: `/api/healthz`, `/api/healthz/deep`, SPA static serving, config, ledger-based SQL migrations with `001_init.sql` enabling PostGIS, Celery skeleton with a `ping` task.
- CI (`quality.yml`): gitleaks, pytest against PostGIS + Redis services, frontend typecheck/build, Playwright smoke + visual, baseline regeneration job.
- Working docs: `CLAUDE.md`, `DEPLOY.md`, `.claude/skills/practice-match-workflow/SKILL.md`, `.env.example`, `.gitleaks.toml`, `.railwayignore`, `.nvmrc`.

**Out of scope (later sub-projects)**

- Any real data: users, auth, listings, photos, requests, documents, admin actions (SP2).
- Census ingest, PostGIS tables beyond the extension, market metrics, tiles (SP3).
- Removing the prototype affordances (jump bar markup, access-state shortcuts, pre-filled demo credentials) — the README's launch-removal list executes in SP2 with real auth.
- Splitting `App.vue` into per-screen components or extracting inline styles. Not before the visual gate exists; then only screen by screen, each diffed.
- `www.foundation.vin` — not in the design; add a redirect only if the VIN Foundation asks.

## 2. Repository layout and stack

```
practice-match/
  frontend/                       Vue 3 + Vite — the handoff vue-app/, path-fixed (§3)
    public/assets/{icons,photos}/ public/assets/vin-foundation-logo.png  public/ds/{colors_and_type.css,fonts/}
    src/App.vue  src/logic.js  src/dc-logic.js  src/components/  src/directives/  src/lib/  src/styles/
    src/router/                   NEW: routes + state<->route sync (TypeScript)
    tests/                        Playwright: playwright.config.ts, screens.ts, visual.spec.ts, smoke.spec.ts,
                                  reference-baselines.spec.ts, visual.spec.ts-snapshots/
  app/                            FastAPI: main.py, config.py, api/health.py, db.py, tasks/celery_app.py
  migrations/                     001_init.sql … (numbered, applied once via ledger)
  scripts/                        migrate.py, start.sh, deploy.sh, verify-deploy.sh
  tests/                          pytest
  docs/design-reference/          the handoff bundle verbatim — visual-harness oracle; never shipped
  docs/superpowers/specs/         this document and successors
  docs/plans/                     implementation plans (foundation, census data layer, …)
  Dockerfile                      stage 1 node:22 builds frontend/dist; stage 2 python:3.12-slim serves it + API
  railway.json                    DOCKERFILE builder · preDeploy migrate · healthcheck /api/healthz
  pyproject.toml · poetry.lock    Python 3.12, Poetry
  .github/workflows/quality.yml
  CLAUDE.md · DEPLOY.md · README.md · .env.example · .gitignore · .gitleaks.toml · .railwayignore · .nvmrc (22)
  .claude/skills/practice-match-workflow/SKILL.md
```

**Versions.** Python 3.12; FastAPI, SQLAlchemy 2 (async, asyncpg), psycopg2-binary (migrate runner), Celery 5, redis-py, pydantic-settings, python-jose + passlib (installed now, used in SP2), httpx, structlog, pytest + pytest-asyncio. Node 22; Vue 3.5; Vite and `@vitejs/plugin-vue` at current stable; `vue-tsc` for typecheck; `vitest`; `@playwright/test`; `leaflet@1.9.4` (the exact version the handoff loads). Exact versions pinned by lockfiles.

**Languages.** New frontend code is TypeScript (`tsconfig` with `allowJs: true`, `checkJs: false`). The ported `App.vue`, `logic.js`, `dc-logic.js`, `directives/hover.js`, `lib/leaflet.js` and the three components stay JavaScript as shipped.

**Git.** `origin` = vin-swe (QA/dev), `production` = johndean. Conventional commits `feat(scope): …`, `fix(scope): …`, `chore(release): vX.Y.Z — …`. Co-author trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Push to both remotes on every commit. Implementation happens on feature branches / worktrees; `main` receives merges.

**Versioning.** `frontend/package.json` and `pyproject.toml` carry the same version, bumped one patch per release, surfaced by `/api/healthz`.

## 3. Frontend: the pixel-faithful port

**Base.** `frontend/` is the handoff `vue-app/` copied verbatim. The handoff does not build as shipped (Rollup cannot resolve `assets/vin-foundation-logo.png` from `App.vue`); the fixes below are the *only* edits to ported files.

**Changes to the handoff — an exhaustive list**

1. **Asset paths.** Every relative `assets/…` and `ds/…` reference in `App.vue`, the three components, `logic.js` and `lib/leaflet.js` (29 in templates, 4 in scripts) becomes absolute `/assets/…` / `/ds/…`, served from `frontend/public/`. Nothing else in those lines changes.
2. **Leaflet vendored.** `lib/leaflet.js` stops injecting `unpkg.com` script/CSS tags and instead `import`s `leaflet` (1.9.4) and `leaflet/dist/leaflet.css`. Its exported API (`loadLeaflet()`, `BASEMAPS`, marker renderers) is unchanged so the components need no edits. Basemap URLs and attribution strings stay exactly as shipped (Esri; see §9 for the licence question).
3. **vue-router as a sync layer.** `logic.js` is not edited. `src/router/` adds:
   - `routes.ts` — the table below; every route renders the one `App` component.
   - `sync.ts` — two pure functions: `stateToRoute(state) → { path, query, params }` and `routeToPatch(route) → Partial<State>`.
   - `App.vue` gains a `watch` on `state.screen`, `state.browseMode`, `state.detailId`, `state.adminTab` → `router.push` (screen change) or `router.replace` (tab/id change within a screen); and a `router.afterEach` that calls `component.setState(routeToPatch(to))` when the patch differs from current state (guarding the loop).

   | Route | `state.screen` | Synced extras |
   |---|---|---|
   | `/` | `gate` | gate sub-state (`signin` / `apply` / `status`) stays internal |
   | `/browse` | `browse` | `?tab=listings\|market` ↔ `state.browseMode` (default `listings`; the handoff README's `mdTab` is the docked panel's tab, not this switch) |
   | `/practices/:id` | `detail` | `params.id` ↔ `state.detailId` |
   | `/requests` | `requests` | — |
   | `/seller` | `seller` | `sellerView` (`dash` / `wizard`) and `step` stay internal |
   | `/admin` | `admin` | `?tab=users\|listings\|activity\|data` ↔ `state.adminTab` (the design's own keys; `activity` is the Requests tab, `data` is Data Sources) |
   | anything else | — | redirect to `/` |

   Member screens depend on `state.auth` (fixture sign-in). `renderVals()` selects a screen by `state.screen` alone, so the sync layer — not the router — enforces the prototype's `go()` rule: a member route requested while signed out renders the gate (sign-in tab), keeps the URL, and applies the requested route the moment `auth` becomes true (`guard()` in `router/sync.ts`).
4. **Prototype props from the environment.** `prototypeBar` = `import.meta.env.VITE_ENVIRONMENT !== 'production'` (jump bar on in QA, off in production). `startScreen` and `startViewport` remain as props with their defaults and are not driven by the URL: the jump bar's own "Mobile view" / "Desktop view" toggle is the design's mobile switch, and the visual harness uses it on both targets (see §9 on the undefined real-device breakpoint). `VITE_ENVIRONMENT` is set at image build time from the Railway service variable `ENVIRONMENT` (Dockerfile `ARG`).

5. **Design-system cascade.** The reference loads three design-system stylesheets before the design's own `<style>` (`colors_and_type.css`, `preview/_preview.css`, `ui_kits/vin/kit.css`); the handoff `vue-app` loads only the first. `_preview.css` carries `* { margin: 0; padding: 0 }` and `-webkit-font-smoothing`, so default element spacing differs without it. `frontend/index.html` links all three from `/ds/` in the reference's order, ahead of `tokens.css`/`global.css`. (`_ds_bundle.js` only defines unused DS demo components and is not shipped.)

**Kept exactly as designed.** The prototype jump bar markup (gated), the "Prototype — access states" shortcuts, the pre-filled demo credentials, all fixture data in `logic.js` (`P`, `MARKETS`, `VETS`, `ECON_K`, `sellerListings`, `requests`, admin rows), all inline styles, all copy, the `v-hover` directive, ProximaNova from `/ds/fonts`, the VIN icon set incl. the six flagged `sub-*` substitutions, the three listing photos.

**Explicitly not done.** No restyling; no extraction of inline styles into classes; no copy edits; no renaming; no Pinia; no per-screen component split; no CSS framework.

## 4. Visual-fidelity harness (the TDD gate for "pixel-by-pixel")

The reference `.dc.html` is the oracle. It renders standalone in a browser: `support.js` loads React 18.3.1, ReactDOM and Babel standalone from unpkg (SRI-pinned) and compiles `AustinMap.jsx` / `MarketMap.jsx` in-page. Its default props are `prototypeBar: true`, `startScreen: 'gate'`, `startViewport: 'desktop'`, preview `1440×940`.

**One state table, two targets.** `frontend/tests/screens.ts` defines each approved screen state once:

```ts
export interface Screen {
  name: string;                                   // baseline file stem
  viewport?: { width: number; height: number };   // default 1440×940
  steps: (page: Page) => Promise<void>;           // same clicks on both targets (role/text selectors), starting from the gate
}
```

- **Reference target** (`reference-baselines.spec.ts`, `npm run test:visual:baselines`): a static server serves `docs/design-reference/`; per state the harness opens `Practice Match V2.dc.html` (its defaults already show the jump bar on the gate at 1440×940), runs `steps`, waits, and saves `visual.spec.ts-snapshots/<name>-<platform>.png`.
- **App target** (`visual.spec.ts`, `npm run test:visual`): Vite serves the app at `/`; per state the test runs the same `steps` (the jump bar and in-screen clicks reach every state on both targets, so the reference needs no `data-props` rewriting) and asserts `expect(page).toHaveScreenshot('<name>.png')`.

**Determinism rules (both targets).** Block basemap tile hosts (`**/*.arcgisonline.com/**` → abort) so maps render markers/pills over a blank canvas; serve the reference runtime's React/ReactDOM/Babel from vendored, byte-identical copies (`docs/design-reference/…/vendor/`) via `page.route('https://unpkg.com/**')` so the suite never depends on a CDN; `animations: 'disabled'`, `caret: 'hide'`; wait for `document.fonts.ready` and one settled frame; fixed viewport; workers = 1. Fonts are the same self-hosted ProximaNova files on both sides.

**Tolerance.** Start at `maxDiffPixels: 0, threshold: 0.1`. If Chromium subpixel noise forces relaxation, the ceiling is `maxDiffPixelRatio: 0.001` and the actual value plus the reason is recorded in `playwright.config.ts` and in this section. Rounds runs 0.005 / 0.2; this project is stricter because both sides render in the same browser with the same DOM.

**States (26).** gate-signin · gate-apply · gate-pending · gate-declined · browse-listings · browse-market · browse-market-layers-open · browse-market-panel (docked practice) · detail · detail-docs-locked · interest-modal · requests · seller-dash · wizard-step-1 · wizard-step-7 (disclosure toggles) · wizard-preview · wizard-done · admin-users · admin-listings · admin-requests · admin-data-sources · mobile-list · mobile-map · mobile-detail · header-1100 (identity text collapses) · header-1000 (nav collapses to Menu). Each is reached by the same `steps` on both targets.

**RED → GREEN.** `visual.spec.ts` fails before the port is wired (no app / no match). The port is complete when every state passes. Baselines are **regenerated from the reference in every run** — locally (`npm run test:visual:baselines`) and in CI, in the same job and browser build that then runs `test:visual` — so no baseline PNGs are committed and the oracle can never go stale. CI enforces the suite on every push.

## 5. Backend skeleton, database, worker

**FastAPI (`app/main.py`).**

- `GET /api/healthz` → `200` always:
  ```json
  { "status": "ok", "version": "0.1.0", "environment": "qa", "commit_sha": "abc1234",
    "db": { "ok": true, "postgis_version": "3.5.x" }, "redis": { "ok": true } }
  ```
  Component failures set `ok: false` (with an `error` string) and leave `status: "ok"` — Railway's healthcheck must not restart the API while Postgres is provisioning.
- `GET /api/healthz/deep` → `200` when db and redis both respond, else `503` with the same body. Used by `scripts/verify-deploy.sh`, never by Railway.
- Static serving of `frontend/dist` mounted after `/api/*`; unknown non-API paths return `index.html` (SPA fallback) so `/browse` deep-links work. `/api/*` unknown paths return JSON 404, never `index.html`.
- CORS allowlist from `ALLOWED_ORIGINS` (comma-separated); default empty.
- `X-Robots-Tag: noindex, nofollow` on every response and `/robots.txt` disallow-all until `PUBLIC_INDEXING=true` (both hosts are public prototypes before Sub-project 2).

**Config (`app/config.py`, pydantic-settings).** `DATABASE_URL`, `REDIS_URL`, `ENVIRONMENT` (`qa` | `production` | `test`), `API_SECRET_KEY`, `ALLOWED_ORIGINS`; optional `COMMIT_SHA` (from `RAILWAY_GIT_COMMIT_SHA`). Missing required var → `SystemExit` at import with the variable named.

**Migrations.** `scripts/migrate.py` is Rounds' ledger runner: globs `migrations/[0-9][0-9][0-9]_*.sql`, applies each not yet in `schema_migrations` under a Postgres advisory lock, records it. `001_init.sql` contains exactly `CREATE EXTENSION IF NOT EXISTS postgis;`. Railway `preDeployCommand` runs the runner before every deploy of `api`; a failing file aborts the deploy.

**Celery (`app/tasks/celery_app.py`).** Broker/backend = `REDIS_URL`; one task `ping() → "pong"`. `scripts/start.sh` dispatches roles `api | worker | migrate` by `RAILWAY_SERVICE_NAME` then `$1` (Rounds logic), including the worker's foreground stdlib health server on `$PORT` and the Celery liveness watchdog.

**Tests (pytest).** healthz body shape and 200 with components down; `/api/healthz/deep` 503 with components down; SPA fallback serves `index.html` for `/browse` and JSON 404 for `/api/nope`; migrate runner applies a file once and records it; config exits with the missing variable named.

## 6. Railway, DNS, deploy loop

**Topology.** Railway project `Practice Match`. Environments `production`, `QA`. Services in each: `api` (Dockerfile, role api), `worker` (same image, role worker), `Postgres` (Railway **PostGIS** template, image pinned `postgis/postgis:16-3.5`), `Redis`. `DATABASE_URL` / `REDIS_URL` are Railway variable references to the environment's own Postgres/Redis, so QA data is isolated from production.

**Service variables (per environment, set out-of-band, never in git).** `ENVIRONMENT`, `API_SECRET_KEY`, `ALLOWED_ORIGINS` (`https://foundation.vin` / `https://qa.foundation.vin`), plus the two references. `railway.json`: builder `DOCKERFILE`, `preDeployCommand: python scripts/migrate.py`, `startCommand: bash scripts/start.sh api`, `healthcheckPath: /api/healthz`, `healthcheckTimeout: 60`, restart `ON_FAILURE` × 3.

**Domains (name.com; John applies the records).**

| Host | Record | Target | Railway side |
|---|---|---|---|
| `qa.foundation.vin` | CNAME | `<id>.up.railway.app` (from Railway after adding the domain) | `api` service, `QA` environment |
| `foundation.vin` | A | the IPv4 Railway shows for the apex (po.vin and rounds.vin use this pattern) | `api` service, `production` environment |

The current `A 91.195.240.94` (name.com parking) on both hosts is replaced.

**Deploy loop.** No git auto-deploy. `scripts/deploy.sh <QA|production>`:

1. `railway status` — must print `Project: Practice Match`; anything else aborts (John's 🚦 rule).
1a. `railway variable set COMMIT_SHA=$(git rev-parse --short HEAD)` on `api` and `worker` (`--skip-deploys`) so `/api/healthz` reports the deployed commit (CLI uploads are not git-connected).
2. `railway up --environment <env> --service api --ci`
3. `railway up --environment <env> --service worker --ci`
4. `scripts/verify-deploy.sh <env>` — `curl /api/healthz` (expects the environment name and the new version), `curl /api/healthz/deep` (expects 200), tails `railway logs --service api` for the boot lines.

Order of operations for every change: deploy QA → verify on `qa.foundation.vin` (incl. the visual suite where relevant) → deploy production → smoke-check `foundation.vin`. Rollback: `railway up` from the last good commit; a failed migration never reaches a running service because it runs pre-deploy.

## 7. CI and working docs

**`.github/workflows/quality.yml`** (mirrors Rounds): `gitleaks` (binary install, `.gitleaks.toml`) · `backend` (services `postgis/postgis:16-3.5`, `redis:7-alpine`; Poetry install; `python scripts/migrate.py`; `pytest -v`) · `frontend` (Node 22; `npm ci`; `npm run typecheck`; `npm run build`; Playwright chromium; `test:smoke`; `test:visual`; upload `playwright-report` on failure) · the `frontend` job runs `test:visual:baselines` (oracle from the reference) immediately before `test:visual`, and uploads report + snapshots as an artifact on failure. The workflow lives in the repo and therefore runs in both remotes; enabling Actions on the vin-swe internal repo is a John action if it is off.

**`CLAUDE.md`** — environments table with URLs and Railway env names; the 🚦 `railway status` rule verbatim; two-remote push; **SSOT = `docs/design-reference/Practice Match V2.dc.html`** — "reference open first, port verbatim, absent beats faked"; no local dev — QA is the loop; the four-layer verification gate (tests · visual suite · click-through on QA · post-deploy smoke on production); the launch-removal list (jump bar markup, access-state shortcuts, demo credentials, `startViewport` query — SP2); the two legally load-bearing rules from the handoff (attribution always visible on maps and under Community Context; datasets with unresolved licences never ship). **`DEPLOY.md`** — variables, deploy and verify commands, expected healthz output, rollback table. **`.claude/skills/practice-match-workflow/SKILL.md`** — the craft, adapted from `povin-workflow` and `rounds`. **`README.md`** — what this is, layout, how to run the suites. **`.env.example`** — every variable with a placeholder. **`.railwayignore`** — `node_modules`, `.git`, `frontend/dist`, `.env*`, `*.log`, `docs/design-reference` (the reference bundle never ships).

## 8. Testing summary and error handling

| Layer | Tool | What |
|---|---|---|
| Router sync | vitest | `stateToRoute` / `routeToPatch` round-trip for every row of the §3 table; unknown route → `/`; tab defaults; no-op patch when route already matches state |
| Asset paths | vitest | no relative `assets/` or `ds/` reference remains in `frontend/src` (guards the 33 fixes) |
| Leaflet adapter | vitest | `loadLeaflet()` resolves the bundled module and injects no external tags; `BASEMAPS` unchanged from the handoff |
| Screens | Playwright smoke | every route renders without console errors; `/api/healthz` reachable |
| Pixel fidelity | Playwright visual | §4 |
| Backend | pytest | §5 |

Errors handled in this sub-project: component outages degrade `/api/healthz` instead of crashing the process; the SPA fallback never shadows `/api/*`; the migrate runner aborts a deploy on a failed file; the worker container exits (and Railway restarts it) if Celery dies. The Census spec's "Map unavailable → list-only view" is runtime behaviour for SP3's plan.

## 9. Open items and hand-offs

**John (needed to finish SP1)**

- Apply the two DNS records in §6 once Railway shows the targets.
- Confirm GitHub Actions is enabled on `vin-swe/practice-match`.
- Confirm the vin-swe repo may hold the design reference bundle (it contains the VIN Foundation logo, photos and design system files).
- **Census API key (in hand, 2026-09-05).** Set it out-of-band — `railway variables --set CENSUS_API_KEY=<key> --service worker --environment <env>` or the dashboard — for both environments once the services exist. It is consumed by Sub-project 3's ingest worker; the spec treats a missing key as a hard startup failure of the ingest worker. Never paste it in chat, commit it, or place it in `.env.example`.

**VIN Foundation (does not block SP1; carried into the SP3 plan)**

- **Basemap licence conflict.** The Census spec registers the street basemap as CARTO (`basemaps.cartocdn.com/light_all`, ODbL attribution); the approved design and its README use Esri ArcGIS Online tiles ("Tiles © Esri"). Esri's basemap terms are their own licence question. The port ships the design's Esri URLs unchanged; the choice must be made before public launch.
- **Mobile activation width.** The design's mobile layout is a prototype toggle, not a breakpoint; the width at which real devices get it is undefined. Decide before SP2 ships to phones.
- The spec's §15 open items: satellite imagery vendor; licensed pet-ownership rate vs ACS-derived; isochrones vs straight-line buffers; opportunity-score weights sign-off; public teaser vs gated market data; AIES dataset ID.
- Public product name (replaces "Practice Match").

## 10. Definition of done (Sub-project 1)

- [ ] Both remotes hold `main`; every commit is on both.
- [ ] `https://qa.foundation.vin/api/healthz` and `https://foundation.vin/api/healthz` return the §5 body with the right `environment`, `db.ok: true`, `postgis_version` present, `redis.ok: true`.
- [ ] Every screen in the design's screen map is reachable on both hosts by URL and by clicking through the fixture flows.
- [ ] `npm run test:visual` passes in CI (Linux) and against live QA (`PW_APP_URL=https://qa.foundation.vin`) with baselines regenerated from the reference; tolerance recorded.
- [ ] `quality.yml` green on `main` in both repos.
- [ ] `CLAUDE.md`, `DEPLOY.md`, the workflow skill, `README.md`, `.env.example` present and accurate.
- [ ] Worker service healthy in both environments; `ping` task round-trips (verified via `celery inspect ping` from a one-off `railway run`).
- [ ] John has the plain-language summary, screenshots of the live screens, and the engineer's note listing anything not verified.
