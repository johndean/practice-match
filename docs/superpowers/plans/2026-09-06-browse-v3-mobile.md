# Browse V3 and Mobile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the approved *Practice Match V3, Rev 2* handoff bundle so Browse Practices becomes one screen — map with community mosaic shading on the left, nine result cards on the right — with the V3 market-data controls on desktop and a full-height market-data sheet on mobile, at zero pixel tolerance and with no backend change.

**Architecture:** `frontend/src/App.vue` and `frontend/src/generated/pseudo.css` are produced by `frontend/scripts/convert-dc.mjs` from the design file; `frontend/src/logic.js` is that same design file's `<script data-dc-script>` block ported verbatim with the one documented asset-path rewrite; `frontend/src/app.setup.js` is the hand-maintained setup block the generator inlines into `App.vue`. So the work is: land the V3 bundle → repoint the generator, the reference server and the harness at it → teach the generator V3's one unknown construct → close the gaps the generator cannot cover (map-engine primitives, the hand-written `MarketMapView.vue`, `markers.js`, the router, the screen list, the seven icons) → regenerate → re-baseline → prove the mobile sheet → sweep dead code one commit at a time → record the cross-plan deltas and hand back on QA.

**Tech Stack:** Vue 3.4 (`<script setup>`, no Pinia, no CSS framework) · TypeScript 6 (`vue-tsc`) · Vite 5 · Vitest 3 + `@vitest/coverage-v8` · Playwright 1.63 (visual, DOM-oracle, smoke projects) · Leaflet 1.9.4 behind the `MapEngine` interface · `htmlparser2` inside `convert-dc.mjs` · no new runtime dependency is added by this plan.

**Branch:** worktree `feat/browse-v3` cut from `main` (spec D1). It merges to `main` before the Census plan and both map-engine plans. Wave 2a (`feat/identity`) runs in parallel on backend-only tasks and rebases onto `main` before its frontend tasks I7/I8.

---

## Global Constraints

Every task's requirements implicitly include this section.

**(a) "Zero gaps" is defined, and this plan is auditable against it.** Every acceptance criterion in the bundle's `README.md`, every `CHANGE_LOG.md` entry C1–C14, every `DEAD_CODE_CHECKLIST.md` rule and every `FILE_INDEX.md` entry appears verbatim in exactly one task below, together with the test that proves it. Appendix A is the mapping table: item → task → test. A reviewer checks coverage from Appendix A without re-reading the bundle.

**(b) Generated files are never hand-edited.** `frontend/src/App.vue` and `frontend/src/generated/pseudo.css` are written only by `npm run gen:app`. `frontend/src/logic.js` is only ever replaced wholesale by the documented port of the design file's `<script data-dc-script>` block. A hand edit to any of the three is caught by `frontend/tests/app-generated.test.ts`. If the generator chokes on a V3 construct, **fix the generator, never the reference.**

**(c) Vue-only conversion (John, 2026-09-06: "convert to vue.js zero-gaps zero-regression").** The app stays Vue 3. `MarketMapV3.jsx`, `AustinMap.jsx`, `MarketMap.jsx`, `support.js`, `image-slot.js` and every other React or design-runtime file in the bundle are **reference material to PORT into Vue** (`MarketMapView.vue`, `markers.js`, `mosaic.js`, the generated `App.vue`/`logic.js`) — never imported, never bundled, never shipped. `frontend/src/**` contains no `react`/`react-dom`/`.jsx` import; `frontend/dist/_app/*.js` contains no React runtime marker. `convert-dc.mjs` remains the only path from the design file to Vue. Proven by `frontend/tests/vue-only.test.ts` (Task V5) and guarded on size by `frontend/tests/bundle-budget.test.ts`.

**(d) Zero regression.** Every existing test keeps passing. The test count only grows, **except** where a task explicitly deletes a test with the dead code it covered; the only such deletions in this plan are named in Task V11 (`markers.test.ts`: `'pill muted/active'`, `'pill neither muted nor active falls back to the default (unselected) palette'`, `'clusterIcon and clusterize'`, `'clusterize uses the wider cell below zoom 8'`, `'pricePin active/inactive'`, `'dot'`). No other test is deleted anywhere in this plan.

**(e) Zero pixel tolerance, never relaxed.** `frontend/tests/playwright.config.ts` stays at `maxDiffPixels: 0`. A failure is the change being wrong, not the gate being strict (spec D7). Relaxing it requires a recorded reason and John's sign-off, which this plan does not grant.

**(f) The unchanged screens must be byte-identical.** The spec calls these "the fourteen screens the bundle names as unchanged"; enumerating them yields **fifteen** baseline names, and all fifteen are held byte-identical:
`mobile-list`, `mobile-detail`, `header-1100`, `header-1000`, `detail`, `requests`, `seller-dash`, `wizard-step-1`, `wizard-step-7`, `wizard-preview`, `wizard-done`, `admin-users`, `admin-listings`, `admin-requests`, `admin-data-sources`.
Their baseline PNG SHA-256s are captured in a committed manifest **before** anything else changes (Task V1) and re-verified at the end of Tasks V7, V9, V10 and after **every** deletion commit in V11. `mobile-map` is expected to change completely (C13). A movement in any of the fifteen means the port leaked into shared code: **stop and diff** (C14, spec D6).

**(g) 100 % hand-written frontend coverage.** `npx vitest run --coverage` at 100 % lines, branches, functions and statements on every hand-written file under `frontend/src/**`. The documented exclusions in `frontend/vite.config.ts` (`src/App.vue`, `src/app.setup.js`, `src/logic.js`, `src/dc-logic.js`, `src/generated/**`, `src/lib/**`, `src/map/engine.ts`, `src/map/testing/**`, tests and `.d.ts`) are the convention and are **not** widened by this plan. New hand-written files — `frontend/src/map/mosaic.js` — are covered at 100 %.

**(h) Attribution stays visible on every map.** `attributionControl: true` on every mount; "Tiles © Esri" on the map basemap, "Imagery © Esri, Maxar, Earthstar Geographics" on satellite. Legally load-bearing (CLAUDE.md); not a style choice.

**(i) No backend change.** `git diff --stat app/ migrations/ scripts/ tests/` is empty for the whole branch. `poetry run pytest` is run once, at the end of Task V12, to prove it. (The one root-level exception is the version bump in V12: `pyproject.toml` and `frontend/package.json` move together, one patch, or `tests/test_versions.py` fails.)

**(j) QA-only deployment.** `scripts/deploy.sh QA` then `scripts/verify-deploy.sh QA`. Production stays in `coming_soon` mode and is not deployed by this sub-project. Before any Railway action, run `railway status` and read back **Project: Practice Match**.

**(k) Conventional commits, explicit pathspecs, both remotes.** Every commit names its files (`git add <path> …`), never `git add -A`/`.`. Every commit message carries the trailer:

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Push to both `origin` (vin-swe/practice-match) and `production` (johndean/practice-match) when the branch is handed back.

**(l) Line numbers in the bundle are advisory (spec D9).** The bundle's `file:line` citations run one to three lines high against the live tree. **Re-grep for the cited symbol before editing**; never edit by line number.

**(m) Deviations STOP.** Any divergence from this plan or the bundle — a value that does not match, an acceptance criterion that cannot be met as written, a file the bundle did not anticipate — stops work and is reported to John. Do not improvise a substitute.

**(n) Surgical diffs.** The change contains the ask and nothing else. No drive-by refactors, no reformatting, no removal of a function or feature while doing unrelated work.

---

## File Structure

| File | Kind | Responsibility | Task |
|---|---|---|---|
| `docs/design-reference/design_handoff_practice_match_v3/**` | reference (never shipped) | the V3 authority + mirrored `_ds/`, `vendor/`, `doc-page.js` | V1 |
| `docs/design-reference/design_handoff_practice_match_v2/**` | reference (never shipped) | **kept** — the regression oracle for the fifteen unchanged screens | untouched |
| `frontend/tests/baseline-manifest.mjs` / `.json` / `.test.ts` | gate (new) | SHA-256 manifest of the fifteen unchanged baselines; the leak detector | V1 |
| `frontend/tests/reference-bundle.test.ts` | gate (new) | the V3 folder is complete and its mirrored files are byte-identical to V2's | V1 |
| `frontend/tests/design-source.test.ts` | gate (new) | every pointer at "the approved design" names V3 | V2, V7 |
| `frontend/package.json` | tooling | `gen:app` reference path | V2 |
| `frontend/tests/reference-server.mjs` + `.test.ts` | tooling | serve V3 at `/`; `/coming-soon/` and both traversal guards unchanged | V2 |
| `frontend/tests/harness.ts` | tooling | vendored React/Leaflet bytes come from the V3 folder | V2 |
| `CLAUDE.md` | docs | source-of-truth path; V2 named as the regression oracle | V2, V12 |
| `frontend/scripts/convert-dc.mjs` + `frontend/tests/convert-dc.test.ts` | tooling | `MarketMapV3` → `MarketMapView`; the generated header names V3 | V3, V7 |
| `frontend/src/map/engine.ts` | hand-written (type-only) | `AreaStyle`, `TooltipSpec`, `rectangle`, `panInside`, widened `Handle`/`MarkerOptions` | V4 |
| `frontend/src/map/engines/leaflet.ts` + `.test.ts` | hand-written | one shared `L.canvas({padding:0.3})` per mount; rectangles; tooltip options forwarded verbatim; `panInside` | V4 |
| `frontend/src/map/mosaic.js` + `.test.ts` | hand-written (new) | `mosaicCells` / `mosaicBbox`, ported verbatim from `MarketMapV3.jsx:57-95` | V4 |
| `frontend/src/map/testing/leaflet-stub.ts` | test double | `rectangle`, `canvas`, `panInside`, `openTooltip` | V4 |
| `frontend/src/styles/global.css` | hand-written | the four `.rf-tip` / `.rf-callout` rules from the reference helmet | V4 |
| `frontend/src/map/markers.js` + `.test.ts` | hand-written | `practicePin`, `practiceCallout`; later loses `pill`/`clusterIcon`/`clusterize`/`pricePin`/`dot` | V5, V11 |
| `frontend/src/components/MarketMapView.vue` + `.test.ts` | hand-written | the V3 map: mosaic shading, `rf-tip`, persistent `rf-callout` + `panInside`, one dashed ring, `onBasemap`-gated tabs | V5 |
| `frontend/tests/vue-only.test.ts` | gate (new) | no React in `src/**` or in the built bundle | V5 |
| `frontend/public/assets/icons/*.svg` | assets | the seven new `sub-*` glyphs | V6 |
| `frontend/tests/icons.test.ts` | gate (new) | every icon the design and `src/**` reference exists on disk | V6 |
| `frontend/src/App.vue`, `logic.js`, `app.setup.js`, `generated/pseudo.css` | generated / ported | the V3 app | V7 |
| `frontend/tests/app-generated.test.ts` | gate | App.vue + pseudo.css byte-identity, `logic.js` port drift, `defineProps` vs the design's `data-props` | V7 |
| `frontend/src/router/sync.ts` + `sync.test.ts` + `useStateRouteSync.test.ts` | hand-written | `/browse` loses its `tab` query; legacy values no-op | V8 |
| `frontend/tests/screens.ts`, `visual.spec.ts-snapshots/**`, `dom-snapshots/**` | gates | one Browse state, three new V3 states, regenerated oracles | V9 |
| `frontend/tests/smoke.spec.ts` | gate | the mobile 390×800 acceptance; route/label updates | V8, V10 |
| `frontend/src/components/ListingsMap.vue` | deleted | dead once V10 is green | V11 |
| `docs/superpowers/plans/2026-09-05-*.md` (three) | docs | the cross-plan deltas | V12 |
| `frontend/tests/cross-plan-deltas.test.ts` | gate (new) | the deltas actually landed in those documents | V12 |

---

## Task V1: Land the V3 reference bundle, behind a baseline hash manifest

**Files:**
- Create: `frontend/tests/baseline-manifest.mjs`
- Create: `frontend/tests/baseline-manifest.json` (produced by the script above)
- Create: `frontend/tests/baseline-manifest.test.ts`
- Create: `frontend/tests/reference-bundle.test.ts`
- Create: `docs/design-reference/design_handoff_practice_match_v3/**` (the bundle, plus `_ds/`, `vendor/`, `doc-page.js` mirrored from V2)

**Interfaces:**
- Consumes: nothing from an earlier task — this is the first task on the branch.
- Produces: `frontend/tests/baseline-manifest.mjs` exports `UNCHANGED_SCREENS: string[]` (the fifteen names from Global Constraint (f)), `SNAPSHOT_DIR: string` (absolute path to `frontend/tests/visual.spec.ts-snapshots`), `MANIFEST_PATH: string` (absolute path to `frontend/tests/baseline-manifest.json`), `hashBaselines(): Record<string, string>` (screen name → lowercase hex SHA-256 of `<name>-<platform>.png`), and `writeManifest(): void`. Running the file as a script (`node tests/baseline-manifest.mjs`) calls `writeManifest()`. The manifest JSON is `{ "platform": string, "screens": Record<string, string> }`. Later tasks re-run `npx vitest run tests/baseline-manifest.test.ts` unchanged; **the manifest is written exactly once, here, and never regenerated by a later task.**

- [ ] **Step 1: Write the failing manifest test**

Create `frontend/tests/baseline-manifest.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { MANIFEST_PATH, UNCHANGED_SCREENS, hashBaselines } from './baseline-manifest.mjs';

// Global Constraint (f): the fifteen screens V3 does not touch (CHANGE_LOG C14 +
// DEAD_CODE_CHECKLIST "Zero-risk requirements") must be BYTE-identical before and after the
// port. Their SHA-256s are frozen here, once, on `main`'s baselines, before any V3 change
// lands. Every later task re-runs this file; a single moved byte means the port leaked into
// shared code — stop and diff, do not re-write the manifest.
describe('unchanged-screen baseline manifest', () => {
  const manifest = JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')) as { platform: string; screens: Record<string, string> };

  it('covers exactly the fifteen screens V3 must not move', () => {
    expect(Object.keys(manifest.screens).sort()).toEqual([...UNCHANGED_SCREENS].sort());
    expect(UNCHANGED_SCREENS).toHaveLength(15);
  });

  it('was captured on this platform, so the hashes are comparable', () => {
    expect(manifest.platform).toBe(process.platform);
  });

  it('every frozen baseline still hashes to its recorded SHA-256', () => {
    expect(hashBaselines()).toEqual(manifest.screens);
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd frontend && npx vitest run tests/baseline-manifest.test.ts`
Expected: FAIL — `Failed to load .../tests/baseline-manifest.mjs` (the module does not exist yet).

- [ ] **Step 3: Write the manifest script and produce the manifest**

Create `frontend/tests/baseline-manifest.mjs`:

```js
// Freezes the SHA-256 of every baseline PNG that the Browse V3 port must not move
// (CHANGE_LOG C14 + DEAD_CODE_CHECKLIST "Zero-risk requirements"). Written ONCE, on main's
// baselines, before Task V1 lands the bundle; read by baseline-manifest.test.ts at the end
// of V7, V9, V10 and after every deletion commit in V11. Never regenerate it to make a test
// pass — a changed hash is the leak detector doing its job.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));

export const SNAPSHOT_DIR = join(HERE, 'visual.spec.ts-snapshots');
export const MANIFEST_PATH = join(HERE, 'baseline-manifest.json');

export const UNCHANGED_SCREENS = [
  'mobile-list', 'mobile-detail',
  'header-1100', 'header-1000',
  'detail', 'requests', 'seller-dash',
  'wizard-step-1', 'wizard-step-7', 'wizard-preview', 'wizard-done',
  'admin-users', 'admin-listings', 'admin-requests', 'admin-data-sources'
];

export function hashBaselines() {
  const out = {};
  for (const name of UNCHANGED_SCREENS) {
    const file = join(SNAPSHOT_DIR, `${name}-${process.platform}.png`);
    out[name] = createHash('sha256').update(readFileSync(file)).digest('hex');
  }
  return out;
}

export function writeManifest() {
  writeFileSync(MANIFEST_PATH, `${JSON.stringify({ platform: process.platform, screens: hashBaselines() }, null, 2)}\n`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) writeManifest();
```

Run: `cd frontend && node tests/baseline-manifest.mjs`
Expected: writes `frontend/tests/baseline-manifest.json` with fifteen entries.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run tests/baseline-manifest.test.ts`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit the manifest**

```bash
git add frontend/tests/baseline-manifest.mjs frontend/tests/baseline-manifest.json frontend/tests/baseline-manifest.test.ts
git commit -m "test(visual): freeze the SHA-256 of the fifteen baselines V3 must not move

The leak detector for the Browse V3 port: CHANGE_LOG C14 and the
DEAD_CODE_CHECKLIST name these screens as untouched, so a moved byte in any
of them means the port reached into shared code.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 6: Write the failing bundle test**

Create `frontend/tests/reference-bundle.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const REF = join(fileURLToPath(new URL('.', import.meta.url)), '..', '..', 'docs', 'design-reference');
const V2 = join(REF, 'design_handoff_practice_match_v2');
const V3 = join(REF, 'design_handoff_practice_match_v3');

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

// README Task 1: the bundle deliberately omits the design-system, the vendored libraries and
// doc-page.js, and they must be MIRRORED UNCHANGED from V2 — without them the reference
// server serves a blank map. The V2 folder itself stays: it is the oracle for the deployed
// build and the only way to prove a regression came from this change.
describe('the V3 design reference bundle', () => {
  it('carries the authority file, the ported component and the four handoff documents', () => {
    for (const f of ['Practice Match V3.dc.html', 'MarketMapV3.jsx', 'README.md', 'CHANGE_LOG.md', 'DEAD_CODE_CHECKLIST.md', 'FILE_INDEX.md', 'support.js', 'image-slot.js', 'Census Data Source Specification.dc.html']) {
      expect(statSync(join(V3, f)).isFile(), `${f} is missing from the V3 bundle`).toBe(true);
    }
  });

  it('mirrors _ds/, vendor/ and doc-page.js from V2 byte-identically', () => {
    const mirrored = ['doc-page.js', ...walk(join(V2, '_ds')).map((f) => relative(V2, f)), ...walk(join(V2, 'vendor')).map((f) => relative(V2, f))];
    expect(mirrored.length, 'the V2 folder no longer carries the files V3 mirrors').toBeGreaterThan(1);
    const drifted = mirrored.filter((rel) => !readFileSync(join(V2, rel)).equals(readFileSync(join(V3, rel))));
    expect(drifted, 'these mirrored files differ between V2 and V3').toEqual([]);
  });

  it('carries no .DS_Store — a macOS artifact is not part of the design', () => {
    expect(walk(V3).filter((f) => f.endsWith('.DS_Store')).map((f) => relative(V3, f))).toEqual([]);
  });

  it('keeps the V2 folder as the regression oracle', () => {
    expect(statSync(join(V2, 'Practice Match V2.dc.html')).isFile()).toBe(true);
  });
});
```

- [ ] **Step 7: Run it to make sure it fails**

Run: `cd frontend && npx vitest run tests/reference-bundle.test.ts`
Expected: FAIL — `ENOENT: no such file or directory, scandir '.../design_handoff_practice_match_v3'`.

- [ ] **Step 8: Land the bundle**

```bash
cd "/Users/johndean/Development/Practice Match"
cp -R "/Users/johndean/Desktop/design_handoff_practice_match_v3" docs/design-reference/design_handoff_practice_match_v3
find docs/design-reference/design_handoff_practice_match_v3 -name .DS_Store -delete
cp -R docs/design-reference/design_handoff_practice_match_v2/_ds docs/design-reference/design_handoff_practice_match_v3/_ds
cp -R docs/design-reference/design_handoff_practice_match_v2/vendor docs/design-reference/design_handoff_practice_match_v3/vendor
cp docs/design-reference/design_handoff_practice_match_v2/doc-page.js docs/design-reference/design_handoff_practice_match_v3/doc-page.js
```

**Do not delete the V2 folder.** It is the oracle for the currently-deployed build. Retire it in a later commit.

- [ ] **Step 9: Run the test to verify it passes**

Run: `cd frontend && npx vitest run tests/reference-bundle.test.ts`
Expected: PASS, 4 tests.

- [ ] **Step 10: Verify the bundle's own acceptance criterion by hand**

> **Acceptance (README Task 1, verbatim):** "`python3 -m http.server` from the new folder, open `Practice Match V3.dc.html`, and the Browse screen renders with the grey Esri basemap, choropleth shading, nine result cards and no console errors."

```bash
cd "docs/design-reference/design_handoff_practice_match_v3" && python3 -m http.server 8099
```
Open `http://localhost:8099/Practice%20Match%20V3.dc.html`, click **Browse** in the prototype jump bar, and confirm all four: grey Esri basemap, shading over the communities, nine result cards, an empty console. Stop the server.

- [ ] **Step 11: Commit the bundle**

```bash
git add docs/design-reference/design_handoff_practice_match_v3 frontend/tests/reference-bundle.test.ts
git commit -m "feat(design): land the Practice Match V3 Rev 2 handoff bundle

Mirrors _ds/, vendor/ and doc-page.js from the V2 folder unchanged (README
Task 1); drops the macOS .DS_Store. The V2 folder stays as the regression
oracle for the fifteen screens V3 does not touch.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task V2: Repoint the generator, the reference server, the harness and CLAUDE.md at V3

**Files:**
- Create: `frontend/tests/design-source.test.ts`
- Modify: `frontend/package.json` (the `gen:app` script)
- Modify: `frontend/tests/reference-server.mjs` (the `''` root's `dir` and `index`)
- Modify: `frontend/tests/reference-server.test.ts` (the V2 title test's name; the two traversal tests' attack paths)
- Modify: `frontend/tests/harness.ts` (the `VENDOR` constant)
- Modify: `CLAUDE.md` (the "Source of truth for the UI" line)

**Interfaces:**
- Consumes: `docs/design-reference/design_handoff_practice_match_v3/` with its mirrored `vendor/` (Task V1).
- Produces: `npm run gen:app` reads `../docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html`; `node tests/reference-server.mjs <port>` serves that file at `/`; `frontend/tests/harness.ts`'s `VENDOR` resolves to `docs/design-reference/design_handoff_practice_match_v3/vendor`. `frontend/tests/design-source.test.ts` exports nothing; later tasks extend it.

> **Ordering fact this task must record.** `npm run gen:app` **cannot** run clean yet: V3's map is `<x-import component="MarketMapV3" …>` and the committed `convert-dc.mjs` knows only `AustinMap` and `MarketMap`. That is Task V3's RED. So this task repoints the *path* and leaves `frontend/tests/app-generated.test.ts` and `convert-dc.mjs`'s generated-header literal still naming V2 — they move in Task V7, in the same commit that actually regenerates `App.vue`. Repointing them here would turn `app-generated.test.ts` red for four tasks, which Global Constraint (d) forbids.

- [ ] **Step 1: Write the failing drift test**

Create `frontend/tests/design-source.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const ROOT = join(FRONTEND, '..');
const V3 = 'design_handoff_practice_match_v3';
const V3_FILE = 'Practice Match V3.dc.html';

// Docs/config drift gate: every pointer at "the approved design" must name ONE folder. When
// the reference moves, these four move together or the toolchain silently regenerates,
// screenshots or documents the wrong revision.
describe('every pointer at the approved design names V3', () => {
  it('package.json gen:app converts the V3 reference', () => {
    const pkg = JSON.parse(readFileSync(join(FRONTEND, 'package.json'), 'utf8')) as { scripts: Record<string, string> };
    expect(pkg.scripts['gen:app']).toContain(`${V3}/'${V3_FILE}'`);
    expect(pkg.scripts['gen:app']).not.toContain('design_handoff_practice_match_v2');
  });

  it('the reference server serves V3 at "/" and keeps the /coming-soon mount first', () => {
    const src = readFileSync(join(FRONTEND, 'tests', 'reference-server.mjs'), 'utf8');
    expect(src).toContain(`design-reference/${V3}`);
    expect(src).toContain(`index: '/${V3_FILE}'`);
    expect(src.indexOf("prefix: '/coming-soon'")).toBeLessThan(src.indexOf("prefix: ''"));
    expect(src).not.toContain('design_handoff_practice_match_v2');
  });

  it('the Playwright harness serves the vendored React/Leaflet bytes out of the V3 folder', () => {
    expect(readFileSync(join(FRONTEND, 'tests', 'harness.ts'), 'utf8')).toContain(`${V3}/vendor`);
  });

  it('CLAUDE.md names the V3 design file as the source of truth for the UI', () => {
    const md = readFileSync(join(ROOT, 'CLAUDE.md'), 'utf8');
    expect(md).toContain(`docs/design-reference/${V3}/${V3_FILE}\` is the approved design`);
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd frontend && npx vitest run tests/design-source.test.ts`
Expected: FAIL — four failures, the first reading `expected '…design_handoff_practice_match_v2/'Practice Match V2.dc.html'…' to contain "design_handoff_practice_match_v3/'Practice Match V3.dc.html'"`.

- [ ] **Step 3: Repoint `package.json`**

In `frontend/package.json`, replace the `gen:app` script with:

```json
    "gen:app": "node scripts/convert-dc.mjs ../docs/design-reference/design_handoff_practice_match_v3/'Practice Match V3.dc.html' src/app.setup.js src/App.vue src/generated/pseudo.css"
```

- [ ] **Step 4: Repoint the reference server**

In `frontend/tests/reference-server.mjs`, replace the `ROOTS` block with:

```js
// docs/design-reference/coming-soon serves the Coming Soon design (Task 11e); the
// Practice Match V3 handoff keeps serving from "/" as before. The first root whose
// prefix the request path starts with wins, so "/coming-soon" is listed first.
const ROOTS = [
  { prefix: '/coming-soon', dir: normalize(join(HERE, '../../docs/design-reference/coming-soon')), index: '/Coming Soon.dc.html' },
  { prefix: '', dir: normalize(join(HERE, '../../docs/design-reference/design_handoff_practice_match_v3')), index: '/Practice Match V3.dc.html' }
];
```

Both traversal guards (the raw `..` segment rejection and the `file.startsWith(root.dir)` check) stay exactly as they are.

- [ ] **Step 5: Repoint the reference-server tests**

In `frontend/tests/reference-server.test.ts`, rename the title test and update the two traversal literals. The assertion string does **not** change — V3 still carries `Practice Match — internal working title`:

```ts
  it('keeps serving the Practice Match V3 marketplace design at "/"', async () => {
    const res = await fetch(`${base}/`);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain('Practice Match — internal working title');
  });

  it('rejects a traversal attempt through the coming-soon prefix rather than silently serving the marketplace file', async () => {
    // A raw literal ".." on the wire — a normal browser/fetch request would resolve this
    // client-side to "/Practice Match V3.dc.html" and never send the ".." at all.
    const res = await rawGet(port, '/coming-soon/../Practice%20Match%20V3.dc.html');
    expect([403, 404]).toContain(res.status);
  });

  it('still rejects the percent-encoded-slash bypass of the URL parser\'s own dot-segment normalization', async () => {
    const res = await rawGet(port, '/coming-soon/..%2fdesign_handoff_practice_match_v3%2fPractice%20Match%20V3.dc.html');
    expect([403, 404]).toContain(res.status);
  });
```

- [ ] **Step 6: Repoint the Playwright harness's vendored bytes**

In `frontend/tests/harness.ts`, change the `VENDOR` constant (the mirrored files are byte-identical, proven by `reference-bundle.test.ts`, so this changes no behaviour — it keeps V3 the single reference root):

```ts
const VENDOR = join(fileURLToPath(new URL('.', import.meta.url)), '../../docs/design-reference/design_handoff_practice_match_v3/vendor');
```

- [ ] **Step 7: Repoint CLAUDE.md**

In `CLAUDE.md`, under "## Source of truth for the UI", replace the first line with:

```markdown
`docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` is the approved design. Rules, each violated by an assistant somewhere before:
```

Leave every rule beneath it intact — they all still apply.

- [ ] **Step 8: Run the drift test and the whole unit suite**

Run: `cd frontend && npx vitest run tests/design-source.test.ts`
Expected: PASS, 4 tests.

Run: `cd frontend && npm run typecheck && npm test`
Expected: PASS. `app-generated.test.ts` still compares against V2 and `src/App.vue` is still V2-generated, so it stays green (see the ordering note above).

- [ ] **Step 9: Verify the reference server by hand**

Run: `cd frontend && node tests/reference-server.mjs 4174`
Open `http://localhost:4174/` — the V3 Browse design renders. Stop the server.

- [ ] **Step 10: Record the deferred half of the bundle's acceptance**

> **Acceptance (README Task 2, verbatim):** "`npm test` green; `node tests/reference-server.mjs 4174` serves V3 at `/`; `npm run gen:app` runs without error (output correctness is Task 6)."

The first two clauses are met by Steps 8 and 9. The third **cannot** be met yet. Prove that it fails for exactly one known reason and no other:

Run: `cd frontend && npm run gen:app`
Expected: FAIL with `Error: unknown x-import component MarketMapV3`. Nothing is written — `convert()` throws before `writeFileSync`. Confirm with `git status --porcelain frontend/src` → empty. Task V3 discharges this clause.

- [ ] **Step 11: Commit**

```bash
git add frontend/package.json frontend/tests/reference-server.mjs frontend/tests/reference-server.test.ts frontend/tests/harness.ts frontend/tests/design-source.test.ts CLAUDE.md
git commit -m "chore(design): point the generator, reference server and harness at V3

package.json gen:app, tests/reference-server.mjs, tests/harness.ts's vendored
bytes and CLAUDE.md's source-of-truth line all name the V3 bundle; a new
design-source drift test keeps them pointing at one folder. app-generated.test.ts
and convert-dc.mjs's generated header move in the regeneration commit, so the
byte-identity gate stays green throughout.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task V3: Teach the generator V3's constructs (must precede any regeneration)

**Files:**
- Modify: `frontend/scripts/convert-dc.mjs` (the `COMPONENTS` map)
- Modify: `frontend/tests/convert-dc.test.ts` (new `describe` block)

**Interfaces:**
- Consumes: `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` (Task V1); `convert`, `extractTemplate`, `buildAppVue`, `compileExpr` from `frontend/scripts/convert-dc.mjs`.
- Produces: `COMPONENTS` in `convert-dc.mjs` gains `MarketMapV3: 'MarketMapView'` (the existing `AustinMap: 'ListingsMap'` and `MarketMap: 'MarketMapView'` entries are **kept** — they are generator grammar, not app code, and removing them is not in the bundle's checklist). `convert(extractTemplate(<the V3 file>))` returns `{ template, pseudoCss }` without throwing, and the template compiles under `@vue/compiler-sfc` with zero errors. Task V7 depends on this.

> **The bundle named three constructs to check first** (README Task 6): `ref="{{ … }}"`, `aria-selected="{{ o.selected }}"`, and a sibling pair of `<sc-if>` switching an `<img src>` between two static files. Measured against the committed generator, **all three already convert correctly** — `attrValue()` binds them as `:ref`, `:aria-selected` and two independent `<template v-if>` blocks with the static `assets/` → `/assets/` rewrite applied. They are locked in below as regression tests, not fixed. The construct that actually breaks is the one the bundle did not name: `<x-import component="MarketMapV3">`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/tests/convert-dc.test.ts`, inside the existing `describe('convert — template constructs', …)` block (before its closing `});`):

```ts
  // V3 (Rev 2) constructs. The bundle's README Task 6 flags three to check before
  // regenerating; all three already convert, and are pinned here so a future generator edit
  // cannot silently break the V3 reference. The fourth — the x-import component NAME — is
  // the one that actually throws, because the design's map component was renamed
  // AustinMap/MarketMap → MarketMapV3.
  describe('V3 reference constructs', () => {
    it('maps the V3 map component onto the same Vue component, with every kebab-case prop bound', () => {
      const { template } = convert('<x-import component="MarketMapV3" from="./MarketMapV3.jsx" on-basemap="{{ md.setBasemap }}" practices="{{ md.practices }}" active-layer="{{ md.activeLayer }}" show-drive="{{ md.showDrive }}" on-area="{{ md.selectArea }}" recenter-key="{{ md.recenterKey }}" hint-size="100%,100%"></x-import>');
      expect(template).toBe('<div class="sc-host-x" style="display: contents"><MarketMapView :on-basemap="v.md?.setBasemap" :practices="v.md?.practices" :active-layer="v.md?.activeLayer" :show-drive="v.md?.showDrive" :on-area="v.md?.selectArea" :recenter-key="v.md?.recenterKey"></MarketMapView></div>');
    });

    it('binds a ref callback (the compare menu scrolls itself into view on open)', () => {
      expect(convert('<div role="listbox" aria-label="Comparison layer" ref="{{ md.compareMenuRef }}"></div>').template)
        .toBe('<div role="listbox" aria-label="Comparison layer" :ref="v.md?.compareMenuRef"></div>');
    });

    it('binds aria-selected on a listbox option, keeping false as a rendered value rather than a dropped attribute', () => {
      expect(convert('<button onClick="{{ o.go }}" role="option" aria-selected="{{ o.selected }}">x</button>').template)
        .toBe('<button @click="v.o?.go" role="option" :aria-selected="v.o?.selected">x</button>');
    });

    it('converts a sibling sc-if pair switching an img between two static files into two independent v-if blocks with absolute asset paths', () => {
      const { template } = convert('<button><sc-if value="{{ md.compareOpen }}" hint-placeholder-val="{{ false }}"><img src="assets/icons/sub-close-thin.svg" alt="" width="14" height="14" style="{{ md.comparePlusStyle }}"></sc-if><sc-if value="{{ md.compareClosed }}" hint-placeholder-val="{{ true }}"><img src="assets/icons/sub-plus-thin.svg" alt="" width="14" height="14" style="{{ md.comparePlusStyle }}"></sc-if></button>');
      expect(template).toBe('<button><template v-if="v.md?.compareOpen"><img src="/assets/icons/sub-close-thin.svg" alt width="14" height="14" :style="v.md?.comparePlusStyle"></template><template v-if="v.md?.compareClosed"><img src="/assets/icons/sub-plus-thin.svg" alt width="14" height="14" :style="v.md?.comparePlusStyle"></template></button>');
    });
  });
```

Then append, at the end of the file (a new top-level `describe`, after the closing `});` of `describe('convert — template constructs', …)`):

```ts
describe('the whole V3 reference converts and compiles', () => {
  const DC = join(import.meta.dirname, '..', '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'Practice Match V3.dc.html');

  it('converts without throwing and produces a template the Vue SFC compiler accepts', async () => {
    const { template, pseudoCss } = convert(extractTemplate(readFileSync(DC, 'utf8')));
    expect(template.length).toBeGreaterThan(100_000);
    expect(pseudoCss).toContain(':hover{');
    const { compileTemplate } = await import('@vue/compiler-sfc');
    const out = compileTemplate({ source: template, filename: 'App.vue', id: 'app', compilerOptions: { whitespace: 'preserve', isCustomElement: (tag: string) => tag === 'image-slot' } });
    expect(out.errors).toEqual([]);
  });

  it('renders both V3 maps as MarketMapView and no ListingsMap — V3 has no listings map, on desktop or on mobile', () => {
    const { template } = convert(extractTemplate(readFileSync(DC, 'utf8')));
    expect(template.split('<MarketMapView').length - 1).toBe(2);
    expect(template).not.toContain('<ListingsMap');
  });
});
```

Add the two imports the new block needs at the top of `frontend/tests/convert-dc.test.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run tests/convert-dc.test.ts`
Expected: FAIL — 3 failures, all `Error: unknown x-import component MarketMapV3` (the first new case and both cases in the whole-reference block). The `ref`, `aria-selected` and paired-`sc-if` cases **PASS on the first run**: they are regression locks on grammar the committed generator already has, and that is the finding, not a shortcut.

- [ ] **Step 3: Write the minimal implementation**

In `frontend/scripts/convert-dc.mjs`, extend the `COMPONENTS` map (one entry added; the two existing entries stay — `AustinMap` is inert grammar once V3 lands and is not on the dead-code checklist):

```js
const COMPONENTS = { AustinMap: 'ListingsMap', MarketMap: 'MarketMapView', MarketMapV3: 'MarketMapView', 'image-slot': 'ImageSlot' };
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run tests/convert-dc.test.ts`
Expected: PASS — the whole file, including the six new cases.

- [ ] **Step 5: Discharge Task V2's deferred acceptance clause without touching the tree**

> **Acceptance (README Task 2, third clause, verbatim):** "`npm run gen:app` runs without error (output correctness is Task 6)."

Run the generator with throwaway outputs, so the regeneration commit stays Task V7's:

```bash
cd frontend && node scripts/convert-dc.mjs \
  "../docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
  src/app.setup.js /tmp/v3-App.vue /tmp/v3-pseudo.css
```
Expected: exits 0, printing `wrote /tmp/v3-App.vue (…) and /tmp/v3-pseudo.css (…)`.
Then: `git status --porcelain frontend/src` → empty.

- [ ] **Step 6: Run the frontend gate**

Run: `cd frontend && npm run typecheck && npm test && npm run build`
Expected: PASS on all three; coverage thresholds unchanged (`convert-dc.mjs` lives under `scripts/`, outside the coverage `include`).

- [ ] **Step 7: Commit**

```bash
git add frontend/scripts/convert-dc.mjs frontend/tests/convert-dc.test.ts
git commit -m "feat(gen): convert V3's MarketMapV3 x-import, and pin V3's three flagged constructs

The design's map component was renamed AustinMap/MarketMap -> MarketMapV3, which
the committed COMPONENTS map did not know. ref=\"{{ }}\", aria-selected=\"{{ }}\"
and a sibling sc-if pair on an <img src> already converted correctly; they are
pinned as regression tests. The whole V3 reference now converts and compiles.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task V4: Extend the map engine — rectangles on one shared canvas, tooltip specs, `panInside`

**Files:**
- Create: `frontend/src/map/mosaic.js`
- Create: `frontend/src/map/mosaic.test.ts`
- Modify: `frontend/src/map/engine.ts`
- Modify: `frontend/src/map/engines/leaflet.ts`
- Modify: `frontend/src/map/engines/leaflet.test.ts`
- Modify: `frontend/src/map/testing/leaflet-stub.ts`
- Modify: `frontend/src/styles/global.css`
- Create: `frontend/src/styles/global.test.ts`

**Interfaces:**
- Consumes: nothing from V1–V3 at runtime; `docs/design-reference/design_handoff_practice_match_v3/` (Task V1) is read by `global.test.ts`.
- Produces, from `frontend/src/map/engine.ts`:
  - `export interface AreaStyle { fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }`
  - `export interface TooltipSpec { html: string; sticky?: boolean; permanent?: boolean; direction?: 'top' | 'bottom'; offset?: [number, number]; className?: string; opacity?: number }`
  - `export interface Handle { remove(): void; openTooltip?(): void }`
  - `MarkerOptions.tooltip?: string | TooltipSpec` (was `string`)
  - `MapEngine.rectangle(bounds: [LatLng, LatLng], style: AreaStyle, group: string, tooltip?: TooltipSpec, onClick?: () => void): Handle`
  - `MapEngine.panInside(pos: LatLng, padding: [number, number]): void`
  - `MountOptions` is unchanged; its `scaleControl?: boolean` option is **kept** (DEAD_CODE_CHECKLIST: "Keep it. No component passes `true` after this work, but it is one tested line and re-adding a scale bar is a product decision, not a code one.")
- Produces, from `frontend/src/map/mosaic.js`: `MOSAIC_STEP = 0.0055`, `BBOX_PAD_LAT = 0.13`, `BBOX_PAD_LNG = 0.15`, `mosaicBbox(sites) -> { minLat, maxLat, minLng, maxLng }`, `mosaicCells(sites, bbox, step) -> Array<{ site, bounds: [[number, number], [number, number]] }>`.

> **Recorded interface extension.** The README's §3a signature is `rectangle(bounds, style, group, tooltip?)`. A fifth optional `onClick` is appended because the same README snippet's ported code ends `.on("click", () => onArea && onArea(site.name))` (`MarketMapV3.jsx:268`) — the click is part of the behaviour being ported, and the engine is the only place it can live under the import boundary (`frontend/src/map/boundary.test.ts`). This is a strict superset of the bundle's signature, not a change to it.

- [ ] **Step 1: Write the failing mosaic tests**

Create `frontend/src/map/mosaic.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { BBOX_PAD_LAT, BBOX_PAD_LNG, MOSAIC_STEP, mosaicBbox, mosaicCells } from './mosaic.js';

const site = (name: string, lat: number, lng: number) => ({ name, lat, lng, values: {} });

describe('mosaicCells — the community mosaic geometry, ported from MarketMapV3.jsx:57-95', () => {
  it('uses the approved step and bbox padding', () => {
    expect(MOSAIC_STEP).toBe(0.0055);
    expect(BBOX_PAD_LAT).toBe(0.13);
    expect(BBOX_PAD_LNG).toBe(0.15);
  });

  it('pads the bounding box 0.13 lat / 0.15 lng around the community extent', () => {
    expect(mosaicBbox([site('a', 30.2, -97.9), site('b', 30.6, -97.6)])).toEqual({
      minLat: 30.2 - 0.13, maxLat: 30.6 + 0.13, minLng: -97.9 - 0.15, maxLng: -97.6 + 0.15
    });
  });

  it('tiles the bbox at `step` and gives each cell square bounds of exactly one step', () => {
    const bbox = { minLat: 30, maxLat: 30.02, minLng: -97.02, maxLng: -97 };
    const cells = mosaicCells([site('a', 30.01, -97.01)], bbox, 0.01);
    expect(cells).toHaveLength(4);                                   // 2 rows x 2 columns
    const [[lat0, lng0], [lat1, lng1]] = cells[0].bounds;
    expect(lat1 - lat0).toBeCloseTo(0.01, 10);
    expect(lng1 - lng0).toBeCloseTo(0.01, 10);
    expect(lat0).toBeCloseTo(30, 10);
    expect(lng0).toBeCloseTo(-97.02, 10);
  });

  it('assigns every cell to its NEAREST community centroid, longitude scaled by cos(lat)', () => {
    const bbox = { minLat: 30, maxLat: 30.04, minLng: -97.02, maxLng: -97 };
    const cells = mosaicCells([site('north', 30.035, -97.01), site('south', 30.005, -97.01)], bbox, 0.01);
    const owner = (lat: number) => cells.find((c) => Math.abs(c.bounds[0][0] - lat) < 1e-9)!.site.name;
    expect(owner(30)).toBe('south');
    expect(owner(30.03)).toBe('north');
  });

  it('drops a cell whose nearest community is farther than the 0.016 squared-degree cutoff, rather than shading empty country', () => {
    const bbox = { minLat: 30, maxLat: 30.02, minLng: -97.02, maxLng: -97 };
    expect(mosaicCells([site('far', 31.5, -96)], bbox, 0.01)).toEqual([]);
  });

  it('returns no cells at all when there are no communities', () => {
    expect(mosaicCells([], { minLat: 30, maxLat: 30.02, minLng: -97.02, maxLng: -97 }, 0.01)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/map/mosaic.test.ts`
Expected: FAIL — `Failed to resolve import "./mosaic.js"`.

- [ ] **Step 3: Write `mosaic.js`**

Create `frontend/src/map/mosaic.js`:

```js
// Community mosaic geometry, ported verbatim from the approved prototype's MarketMapV3.jsx
// (mosaicCells, lines 57-95). Presentation logic, not engine logic, so it lives beside
// markers.js rather than inside an engine.
//
// GEOMETRY NOTE, from the reference's own header: the prototype has no ZCTA boundary file,
// so community areas are approximated as the cells nearest each community's centroid,
// clipped to the metro bounding box. Cells are contiguous and non-overlapping, which is what
// area shading requires, but they are NOT real Census boundaries — the UI labels them
// "approximate community areas". Production loads tiger_cb ZCTA polygons per the Census Data
// Source Specification (Sub-project 3) and drops this approximation.
//
// This is "community mosaic shading" (spec D5). The word "choropleth" is reserved for the
// Census plan's Phase C server-generated tract-level vector tiles, which are a different
// thing at a different granularity.

export const MOSAIC_STEP = 0.0055;
export const BBOX_PAD_LAT = 0.13;
export const BBOX_PAD_LNG = 0.15;

/** MarketMapV3.jsx:239-246 — the metro extent, padded so shading reaches past the outermost community. */
export function mosaicBbox(sites) {
  const lats = sites.map((c) => c.lat);
  const lngs = sites.map((c) => c.lng);
  return {
    minLat: Math.min.apply(null, lats) - BBOX_PAD_LAT,
    maxLat: Math.max.apply(null, lats) + BBOX_PAD_LAT,
    minLng: Math.min.apply(null, lngs) - BBOX_PAD_LNG,
    maxLng: Math.max.apply(null, lngs) + BBOX_PAD_LNG
  };
}

/**
 * Each cell is assigned the class of its nearest community centroid, which yields crisp
 * finite boundaries rather than overlapping discs. This is spatial ASSIGNMENT of existing
 * community data, not interpolation, and not new data.
 */
export function mosaicCells(sites, bbox, step) {
  const out = [];
  for (let lat = bbox.minLat; lat < bbox.maxLat; lat += step) {
    for (let lng = bbox.minLng; lng < bbox.maxLng; lng += step) {
      const cLat = lat + step / 2, cLng = lng + step / 2;
      let best = null, bestD = Infinity;
      for (let i = 0; i < sites.length; i++) {
        const s = sites[i];
        const dLat = s.lat - cLat;
        const dLng = (s.lng - cLng) * Math.cos((cLat * Math.PI) / 180);
        const d = dLat * dLat + dLng * dLng;
        if (d < bestD) { bestD = d; best = s; }
      }
      // Drop cells too far from every community rather than shading empty country.
      if (!best || bestD > 0.016) continue;
      out.push({ site: best, bounds: [[lat, lng], [lat + step, lng + step]] });
    }
  }
  return out;
}
```

- [ ] **Step 4: Run them to verify they pass**

Run: `cd frontend && npx vitest run src/map/mosaic.test.ts --coverage.include='src/map/mosaic.js'`
Expected: PASS, 6 tests, `mosaic.js` at 100 % lines/branches/functions/statements.

- [ ] **Step 5: Commit the mosaic helper**

```bash
git add frontend/src/map/mosaic.js frontend/src/map/mosaic.test.ts
git commit -m "feat(map): port mosaicCells from MarketMapV3.jsx as map/mosaic.js

Step 0.0055, bbox padded 0.13 lat / 0.15 lng, nearest-centroid assignment with
the 0.016 cutoff — the geometry behind V3's community mosaic shading (C5).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 6: Write the failing engine tests**

Append to `frontend/src/map/engines/leaflet.test.ts` (a new top-level `describe`, at the end of the file):

```ts
// C5/C6/C7 (README Task 3): the four primitives V3's market map needs and the shipped engine
// did not have. One canvas renderer per MOUNT is the load-bearing one — a renderer per
// rectangle makes a mosaic this dense unusable.
describe('LeafletMapEngine — V3 area shading, tooltip specs and panInside', () => {
  it('creates exactly one canvas renderer per mount and hands it to every rectangle', async () => {
    const { stub, engine } = await mounted({ scaleControl: false, groups: ['overlay', 'pins'] });
    expect(stub.calls.filter((c) => c.fn === 'canvas')).toHaveLength(1);
    expect(stub.calls.find((c) => c.fn === 'canvas')?.args).toEqual([{ padding: 0.3 }]);

    const renderer = stub.canvas;
    engine.rectangle([[30.1, -97.9], [30.2, -97.8]], { fillColor: '#4c9a6a', fillOpacity: 0.5 }, 'overlay');
    engine.rectangle([[30.2, -97.9], [30.3, -97.8]], { fillColor: '#1b6b3a', fillOpacity: 0.5 }, 'overlay');
    expect(stub.calls.filter((c) => c.fn === 'canvas')).toHaveLength(1);
    for (const r of stub.calls.filter((c) => c.fn === 'rectangle')) {
      expect((r.args[1] as { renderer: unknown }).renderer).toBe(renderer);
    }
  });

  it('passes the design\'s rectangle options and defaults stroke off, interactive on', async () => {
    const { stub, engine } = await mounted({ scaleControl: false });
    engine.rectangle([[30.1, -97.9], [30.2, -97.8]], { fillColor: '#4c9a6a', fillOpacity: 0.5 }, 'overlay');
    const args = stub.calls.find((c) => c.fn === 'rectangle')!.args;
    expect(args[0]).toEqual([[30.1, -97.9], [30.2, -97.8]]);
    expect(args[1]).toMatchObject({ stroke: false, fillColor: '#4c9a6a', fillOpacity: 0.5, interactive: true });

    engine.rectangle([[1, 2], [3, 4]], { fillColor: '#000', fillOpacity: 1, stroke: true, interactive: false }, 'overlay');
    expect(stub.calls.filter((c) => c.fn === 'rectangle')[1].args[1]).toMatchObject({ stroke: true, interactive: false });
  });

  it('adds the rectangle to the NAMED group and removes it by its handle', async () => {
    const { stub, engine } = await mounted({ scaleControl: false, groups: ['overlay', 'pins'] });
    const groups = (stub.map.added as { clearLayers?: unknown; added: unknown[] }[]).filter((g) => g.clearLayers);
    const handle = engine.rectangle([[1, 2], [3, 4]], { fillColor: '#000', fillOpacity: 1 }, 'pins');
    expect(groups[0].added).toHaveLength(0);          // 'overlay' untouched
    expect(groups[1].added).toHaveLength(1);          // 'pins' is the named group
    handle.remove();
    expect(groups[1].added).toHaveLength(0);
  });

  it('forwards a rectangle tooltip spec verbatim, minus its html, and wires the area click', async () => {
    const { stub, engine } = await mounted({ scaleControl: false });
    let clicked = '';
    engine.rectangle([[1, 2], [3, 4]], { fillColor: '#000', fillOpacity: 1 }, 'overlay',
      { html: '<div>Cedar Park</div>', sticky: true, className: 'rf-tip' },
      () => { clicked = 'Cedar Park'; });
    const rect = (stub.map.added as { clearLayers?: unknown; added: { tooltip?: unknown; on_click?: () => void }[] }[])
      .filter((g) => g.clearLayers)[0].added[0];
    expect(rect.tooltip).toEqual({ text: '<div>Cedar Park</div>', opts: { sticky: true, className: 'rf-tip' } });
    rect.on_click!();
    expect(clicked).toBe('Cedar Park');
  });

  it('a rectangle with neither tooltip nor click binds neither', async () => {
    const { stub, engine } = await mounted({ scaleControl: false });
    engine.rectangle([[1, 2], [3, 4]], { fillColor: '#000', fillOpacity: 1 }, 'overlay');
    const rect = (stub.map.added as { clearLayers?: unknown; added: { tooltip?: unknown; on_click?: unknown }[] }[])
      .filter((g) => g.clearLayers)[0].added[0];
    expect(rect.tooltip).toBeUndefined();
    expect(rect.on_click).toBeUndefined();
  });

  it('a marker tooltip spec is forwarded verbatim; a bare string keeps the old defaults', async () => {
    const { stub, engine } = await mounted({ scaleControl: false, groups: ['pins'] });
    engine.marker([30.5, -97.8], {
      html: '<i></i>', size: [78, 34], anchor: [39, 34],
      tooltip: { html: '<div>callout</div>', direction: 'top', offset: [0, -22], className: 'rf-callout', permanent: true, opacity: 1 }
    }, 'pins');
    engine.marker([30.6, -97.8], { html: '<i></i>', size: [78, 34], anchor: [39, 34], tooltip: 'Cedar Park — $118K' }, 'pins');
    const pins = (stub.map.added as { clearLayers?: unknown; added: { tooltip?: unknown }[] }[]).filter((g) => g.clearLayers)[0].added;
    expect(pins[0].tooltip).toEqual({ text: '<div>callout</div>', opts: { direction: 'top', offset: [0, -22], className: 'rf-callout', permanent: true, opacity: 1 } });
    expect(pins[1].tooltip).toEqual({ text: 'Cedar Park — $118K', opts: { direction: 'top', offset: [0, -6] } });
  });

  it('a marker handle can open its own tooltip — selection opens the callout programmatically, not only on hover', async () => {
    const { stub, engine } = await mounted({ scaleControl: false, groups: ['pins'] });
    const handle = engine.marker([30.5, -97.8], { html: '<i></i>', size: [78, 34], anchor: [39, 34], tooltip: { html: '<div>c</div>', permanent: true } }, 'pins');
    handle.openTooltip!();
    const pin = (stub.map.added as { clearLayers?: unknown; added: { tooltipOpened?: number }[] }[]).filter((g) => g.clearLayers)[0].added[0];
    expect(pin.tooltipOpened).toBe(1);
  });

  it('panInside pans with the design\'s padding and animation', async () => {
    const { stub, engine } = await mounted({ scaleControl: false });
    engine.panInside([30.5052, -97.8203], [48, 110]);
    expect((stub.map as { pannedInside?: unknown }).pannedInside).toEqual([[30.5052, -97.8203], { padding: [48, 110], animate: true }]);
  });

  it('rectangle and panInside are inert after destroy(), like every other method', async () => {
    const { stub, engine } = await mounted({ scaleControl: false });
    engine.destroy();
    const before = stub.calls.length;
    const handle = engine.rectangle([[1, 2], [3, 4]], { fillColor: '#000', fillOpacity: 1 }, 'overlay');
    engine.panInside([30.5, -97.8], [48, 110]);
    expect(stub.calls).toHaveLength(before);
    expect((stub.map as { pannedInside?: unknown }).pannedInside).toBeUndefined();
    expect(() => handle.remove()).not.toThrow();     // the no-op handle is still safe to call
  });

  it('a re-mount builds a fresh canvas renderer rather than drawing into the removed map\'s', async () => {
    const { stub, engine } = await mounted({ scaleControl: false });
    const first = stub.canvas;
    engine.destroy();
    const stub2 = installLeafletStub();
    await engine.mount(document.createElement('div'), { center: [30.31, -97.75], zoom: 10, basemap: 'map', zoomControl: false, scaleControl: false, groups: ['overlay'] });
    expect(stub2.canvas).not.toBe(first);
    engine.rectangle([[1, 2], [3, 4]], { fillColor: '#000', fillOpacity: 1 }, 'overlay');
    expect((stub2.calls.find((c) => c.fn === 'rectangle')!.args[1] as { renderer: unknown }).renderer).toBe(stub2.canvas);
  });
});
```

Also rename the two existing `describe` titles so the shapes they assert are named for what they are after V3 (DEAD_CODE_CHECKLIST: *"`engines/leaflet.test.ts:330` `'LeafletMapEngine — ListingsMap shape'` — rename, don't delete — the assertions cover the engine's mount contract, which still matters."*). Re-grep for the strings rather than trusting the line number:

```ts
describe('LeafletMapEngine — mount contract, scaleControl option kept', () => {
```
(was `describe('LeafletMapEngine — MarketMapView shape', …)`; its body is unchanged, and it is now the test that keeps the `scaleControl` option alive), and

```ts
describe('LeafletMapEngine — bottom-right zoom control, no scale control', () => {
  it('adds the bottom-right zoom control and no scale control', async () => {
```
(was `describe('LeafletMapEngine — ListingsMap shape', …)`; its body is unchanged).

- [ ] **Step 7: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/map/engines/leaflet.test.ts`
Expected: FAIL — the new block fails with `TypeError: engine.rectangle is not a function`, and `stub.canvas` is `undefined`.

- [ ] **Step 8: Extend the Leaflet stub**

In `frontend/src/map/testing/leaflet-stub.ts`:

Add `openTooltip()` to `FakeLayer` (append to its body, after `bindTooltip`):

```ts
openTooltip() { (this as any).tooltipOpened = ((this as any).tooltipOpened ?? 0) + 1; return this; }
```

Add `panInside` to `FakeMap` (append to its body, after `fitBounds`):

```ts
panInside(pos: unknown, o?: unknown) { (this as any).pannedInside = [pos, o]; }
```

Add a canvas-renderer record to the stub's return shape — change the interface, the closure and the returned object:

```ts
export interface LeafletStub { calls: Call[]; map: FakeMap; tiles: FakeTile[]; canvas: unknown; L: unknown }
```

```ts
  const calls: Call[] = []; const tiles: FakeTile[] = []; let map: FakeMap; let canvas: unknown = null;
```

Add these two entries to the `L` object literal (beside `circle` and `marker`):

```ts
    rectangle: rec('rectangle', (bounds: unknown, options: unknown) => Object.assign(new FakeLayer(), { bounds, options })),
    canvas: rec('canvas', (o: unknown) => (canvas = { renderer: 'canvas', options: o })),
```

And return it:

```ts
  return { calls, get map() { return map; }, tiles, get canvas() { return canvas; }, L };
```

- [ ] **Step 9: Extend the engine interface**

In `frontend/src/map/engine.ts`, replace the type block and add the two methods:

```ts
export type LatLng = [number, number];
export type BaseKind = 'map' | 'satellite';
export interface MountOptions { center: LatLng; zoom: number; basemap: BaseKind; zoomControl?: 'bottomright' | false; scaleControl?: boolean; groups?: string[] }
export interface CircleStyle { fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }
/** V3's community mosaic cell (C5): a filled, strokeless rectangle on the shared canvas renderer. */
export interface AreaStyle { fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }
/** V3 needs two tooltip shapes the hard-coded one could not express: the sticky `rf-tip` on a
 *  mosaic cell, and the persistent `rf-callout` above a selected practice pin (C5, C6). */
export interface TooltipSpec { html: string; sticky?: boolean; permanent?: boolean; direction?: 'top' | 'bottom'; offset?: [number, number]; className?: string; opacity?: number }
export interface MarkerOptions { html: string; size: [number, number]; anchor: [number, number]; tooltip?: string | TooltipSpec; zIndexOffset?: number; interactive?: boolean; onClick?: () => void }
export interface Handle { remove(): void; openTooltip?(): void }

/** The only map API the components use — exactly the surface the handoff's map components call. */
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
  rectangle(bounds: [LatLng, LatLng], style: AreaStyle, group: string, tooltip?: TooltipSpec, onClick?: () => void): Handle;
  marker(pos: LatLng, opts: MarkerOptions, group: string): Handle;
  panInside(pos: LatLng, padding: [number, number]): void;
  clear(group: string): void;
  onMove(cb: (center: LatLng, zoom: number) => void): () => void;
  destroy(): void;
}
```

- [ ] **Step 10: Implement in the Leaflet engine**

In `frontend/src/map/engines/leaflet.ts`:

Widen the import and add the tooltip helper below `NOOP_UNSUBSCRIBE`:

```ts
import type { AreaStyle, BaseKind, CircleStyle, Handle, LatLng, MapEngine, MarkerOptions, MountOptions, TooltipSpec } from '../engine';
```

```ts
// "Tooltip options forwarded verbatim" (README Task 3b): everything on the spec except the
// html itself is handed to Leaflet untouched, so a new option in the design needs no engine
// change. A bare string keeps the pre-V3 defaults, so nothing else on the map moves.
const tipOptions = (t: TooltipSpec) => { const { html: _html, ...rest } = t; return rest; };
```

Add the renderer field beside `zoomCtl`/`scaleCtl`:

```ts
  private zoomCtl: any = null; private scaleCtl: any = null; private canvas: any = null;
```

In `mount()`, create it once — immediately after the label tile layer is set up and before the groups are made:

```ts
    // ONE canvas renderer per mount, shared by every mosaic cell (MarketMapV3.jsx:248). A
    // renderer per rectangle is what makes a mosaic this dense unusable.
    this.canvas = L.canvas({ padding: 0.3 });
```

Add `rectangle()` immediately after `circle()`:

```ts
  rectangle(bounds: [LatLng, LatLng], s: AreaStyle, group: string, tooltip?: TooltipSpec, onClick?: () => void): Handle {
    if (this.destroyed) return NOOP_HANDLE;
    const r = this.L.rectangle(bounds, { renderer: this.canvas, stroke: s.stroke ?? false, fillColor: s.fillColor, fillOpacity: s.fillOpacity, interactive: s.interactive ?? true });
    if (tooltip) r.bindTooltip(tooltip.html, tipOptions(tooltip));
    if (onClick) r.on('click', onClick);
    r.addTo(this.group(group));
    return { remove: () => r.remove(), openTooltip: () => r.openTooltip() };
  }
```

Replace the tooltip line inside `marker()` and widen its returned handle:

```ts
    if (typeof o.tooltip === 'string') m.bindTooltip(o.tooltip, { direction: 'top', offset: [0, -6] });
    else if (o.tooltip) m.bindTooltip(o.tooltip.html, tipOptions(o.tooltip));
    if (o.onClick) m.on('click', o.onClick);
    m.addTo(this.group(group));
    return { remove: () => m.remove(), openTooltip: () => m.openTooltip() };
```

Add `panInside()` immediately after `marker()`:

```ts
  // MarketMapV3.jsx:303-306 — selecting a practice opens its callout and pans just enough to
  // bring the callout into view. The 110 px vertical padding is deliberate: ~70 px callout
  // plus the 34 px pin.
  panInside(pos: LatLng, padding: [number, number]): void { if (this.destroyed) return; this.map.panInside(pos, { padding, animate: true }); }
```

In `destroy()`, drop the renderer with the rest of the map-bound state — add one line beside `this.zoomCtl = null;`:

```ts
    this.canvas = null;
```

- [ ] **Step 11: Run the tests to verify they pass**

Run: `cd frontend && npm run typecheck && npx vitest run src/map/engines/leaflet.test.ts`
Expected: PASS — the whole file, including the ten new cases.

> **Acceptance (README Task 3, verbatim):** "new unit tests in `frontend/src/map/engines/leaflet.test.ts` (the stub in `frontend/src/map/testing/leaflet-stub.ts` needs `rectangle`, `canvas` and `panInside` added) covering: one canvas renderer per mount; rectangle added to the named group and removed by its handle; tooltip options forwarded verbatim; `panInside` no-ops after `destroy()`. `npm run typecheck && npm test` green."

- [ ] **Step 12: Write the failing global-CSS test**

Create `frontend/src/styles/global.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = join(import.meta.dirname, '..', '..', '..');
const CSS = readFileSync(join(ROOT, 'frontend', 'src', 'styles', 'global.css'), 'utf8');
const REFERENCE = readFileSync(join(ROOT, 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'Practice Match V3.dc.html'), 'utf8');

// README Task 3b: .rf-callout and .rf-tip target LEAFLET's own tooltip elements, which live
// outside component scope, so they cannot be scoped styles — global.css is their home. They
// are copied out of the reference's helmet, so this test compares them against the reference
// rather than restating them, including the ::before arrow-colour overrides.
describe('.rf-tip / .rf-callout reach the app exactly as the reference declares them', () => {
  const RULES = [
    '.leaflet-tooltip.rf-callout { background: #fff; border: 1px solid rgba(0,58,112,.12); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,58,112,.22); padding: 8px 10px; color: #003a70; white-space: nowrap; }',
    '.leaflet-tooltip.rf-callout::before { border-top-color: #fff; }',
    '.leaflet-tooltip.rf-tip { background: #fff; border: 1px solid rgba(0,58,112,.12); border-radius: 6px; box-shadow: 0 3px 10px rgba(0,58,112,.18); color: #003a70; }',
    '.leaflet-tooltip.rf-tip::before { border-top-color: #fff; }'
  ];

  it('the four rules this test pins are the four the reference helmet declares', () => {
    for (const rule of RULES) expect(REFERENCE, `the reference no longer declares: ${rule}`).toContain(rule);
  });

  it('global.css carries all four, byte-for-byte', () => {
    for (const rule of RULES) expect(CSS, `global.css is missing: ${rule}`).toContain(rule);
  });
});
```

- [ ] **Step 13: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/styles/global.test.ts`
Expected: FAIL — the second test, `global.css is missing: .leaflet-tooltip.rf-callout { … }`.

- [ ] **Step 14: Append the four rules to `global.css`**

Append to `frontend/src/styles/global.css`, after the `.leaflet-container` rule:

```css
/* Leaflet tooltip skins from the V3 reference helmet. They target Leaflet's own tooltip
   elements, which are created outside any component's scope, so they cannot be scoped. */
.leaflet-tooltip.rf-callout { background: #fff; border: 1px solid rgba(0,58,112,.12); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,58,112,.22); padding: 8px 10px; color: #003a70; white-space: nowrap; }
.leaflet-tooltip.rf-callout::before { border-top-color: #fff; }
.leaflet-tooltip.rf-tip { background: #fff; border: 1px solid rgba(0,58,112,.12); border-radius: 6px; box-shadow: 0 3px 10px rgba(0,58,112,.18); color: #003a70; }
.leaflet-tooltip.rf-tip::before { border-top-color: #fff; }
```

- [ ] **Step 15: Run the whole frontend gate**

Run: `cd frontend && npm run typecheck && npm test && npm run build`
Expected: PASS on all three, coverage thresholds met (`leaflet.ts` and `mosaic.js` at 100 %).

- [ ] **Step 16: Commit**

```bash
git add frontend/src/map/engine.ts frontend/src/map/engines/leaflet.ts frontend/src/map/engines/leaflet.test.ts frontend/src/map/testing/leaflet-stub.ts frontend/src/styles/global.css frontend/src/styles/global.test.ts
git commit -m "feat(map): rectangles on one shared canvas, tooltip specs, panInside

The four primitives V3's market map needs (README Task 3): AreaStyle +
rectangle() on a single L.canvas({padding: 0.3}) per mount, TooltipSpec
forwarded verbatim with a bare string keeping the old defaults, Handle.openTooltip
so selection can open a callout programmatically, and panInside([48, 110]).
The scaleControl option is kept, per the dead-code checklist. .rf-tip and
.rf-callout are copied out of the reference helmet into global.css.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task V5: Port `MarketMapView.vue` and `markers.js` to the V3 map

**Files:**
- Modify: `frontend/src/map/markers.js`
- Modify: `frontend/src/map/markers.test.ts`
- Modify: `frontend/src/components/MarketMapView.vue`
- Modify: `frontend/src/components/MarketMapView.test.ts`
- Create: `frontend/tests/vue-only.test.ts`

**Interfaces:**
- Consumes: `rectangle`, `panInside`, `TooltipSpec`, `AreaStyle`, `Handle.openTooltip` from `frontend/src/map/engine.ts` and `frontend/src/map/engines/leaflet.ts` (Task V4); `MOSAIC_STEP`, `mosaicBbox`, `mosaicCells` from `frontend/src/map/mosaic.js` (Task V4); `createEngine()` from `frontend/src/map/create.ts` (unchanged).
- Produces:
  - `frontend/src/map/markers.js` gains `practicePin(label: string, selected: boolean) -> string` and `practiceCallout(p: { name, priceLabel, meta?, photoSrc? }) -> string`.
  - `frontend/src/components/MarketMapView.vue` accepts exactly the props the generated `App.vue` will pass, from `Practice Match V3.dc.html:324` (desktop) and `:1359` (mobile):
    `practices: Array`, `communities: Array`, `activeLayer: String|null`, `basemap: String`, `onBasemap: Function|null`, `activeId: String|null`, `onSelect: Function|null`, `onArea: Function|null`, `center: Array`, `zoom: Number`, `driveCenter: Array|null`, `showDrive: Boolean`, `resizeKey: String`, `recenterKey: Number`.
    The props `layers` and `valueLayer` are **removed** (DEAD_CODE_CHECKLIST, "Delete by hand").
  - `frontend/tests/vue-only.test.ts` exports nothing; it is the Global Constraint (c) gate.

> **`onBasemap` is the gate for the `Map | Satellite` tabs** (C13, `MarketMapV3.jsx:360, 382`). Desktop passes it; mobile does not, because the sheet owns basemap switching and the 132 px cluster would otherwise sit under the key on a 388 px map. Desktop is unaffected.

- [ ] **Step 1: Write the failing marker tests**

Append to the existing `describe` in `frontend/src/map/markers.test.ts` (before its closing `});`), and add `practiceCallout, practicePin` to the import list at the top of the file:

```ts
  it('practicePin unselected: a label chip above a small navy dot', () => {
    const html = practicePin('$1.45M', false);
    expect(html).toContain('flex-direction:column;align-items:center;gap:3px;');
    expect(html).toContain('font-size:11.5px;font-weight:800;');
    expect(html).toContain('background:#ffffff;color:#003a70;');
    expect(html).toContain('>$1.45M</div>');
    expect(html).toContain('width:9px;height:9px;border-radius:999px;background:#003a70;');
  });

  it('practicePin selected: one prominent dot and no chip — the open callout already carries the price', () => {
    const html = practicePin('$1.45M', true);
    expect(html).toContain('width:20px;height:20px;border-radius:999px;background:#339dde;');
    expect(html).toContain('border:3px solid #fff;');
    expect(html).not.toContain('$1.45M');
  });

  it('practiceCallout renders the photo, name, price and meta', () => {
    const html = practiceCallout({ name: 'Cedar Park', priceLabel: '$1.45M', meta: '3 DVMs · 4,200 sq ft', photoSrc: '/assets/photos/round-rock-exterior-street.webp' });
    expect(html).toContain('<img src="/assets/photos/round-rock-exterior-street.webp"');
    expect(html).toContain('object-position:60% 45%');
    expect(html).toContain('>Cedar Park</div>');
    expect(html).toContain('>$1.45M</div>');
    expect(html).toContain('>3 DVMs · 4,200 sq ft</div>');
  });

  it('practiceCallout omits the photo block entirely when there is no photo, and renders empty meta rather than "undefined"', () => {
    const html = practiceCallout({ name: 'Kyle', priceLabel: '$1.18M' });
    expect(html).not.toContain('<img');
    expect(html).not.toContain('undefined');
    expect(html).toContain('color:#494949;white-space:nowrap"></div>');
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/map/markers.test.ts`
Expected: FAIL — `SyntaxError: The requested module './markers.js' does not provide an export named 'practicePin'`.

- [ ] **Step 3: Port the two marker builders**

Append to `frontend/src/map/markers.js`, ported verbatim from `MarketMapV3.jsx:115-152` (inline styles included — the file's own header explains why):

```js
export function practicePin(label, selected) {
  // Selected: a single prominent dot — the open callout above it carries the price, so a
  // pill as well would duplicate it.
  if (selected) {
    return (
      '<div style="display:flex;justify-content:center;align-items:flex-end;height:100%">' +
        '<div style="width:20px;height:20px;border-radius:999px;background:#339dde;' +
        'border:3px solid #fff;box-shadow:0 2px 7px rgba(0,58,112,.45)"></div>' +
      "</div>"
    );
  }
  return (
    '<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">' +
      '<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;font-size:11.5px;font-weight:800;' +
      "white-space:nowrap;padding:3px 8px;border-radius:5px;background:#ffffff;color:#003a70;" +
      "border:1px solid rgba(0,58,112,.18);box-shadow:0 1px 4px rgba(0,58,112,.22);" + '">' + label + "</div>" +
      '<div style="width:9px;height:9px;border-radius:999px;background:#003a70;' +
      'border:2px solid #fff;box-shadow:0 1px 4px rgba(0,58,112,.4)"></div>' +
    "</div>"
  );
}

export function practiceCallout(p) {
  const photo = p.photoSrc
    ? '<div style="width:62px;height:48px;flex:none;border-radius:4px;overflow:hidden;background:#deecf7">' +
      '<img src="' + p.photoSrc + '" alt="" style="width:100%;height:100%;object-fit:cover;object-position:60% 45%;display:block"></div>'
    : "";
  return (
    '<div style="display:flex;gap:9px;align-items:center;font-family:ProximaNova,Arial,Helvetica,sans-serif">' +
      photo +
      '<div style="min-width:0">' +
        '<div style="font-size:12px;font-weight:800;color:#003a70;white-space:nowrap">' + p.name + "</div>" +
        '<div style="font-size:15px;font-weight:800;color:#003a70;line-height:1.2">' + p.priceLabel + "</div>" +
        '<div style="font-size:10.5px;color:#494949;white-space:nowrap">' + (p.meta || "") + "</div>" +
      "</div>" +
    "</div>"
  );
}
```

- [ ] **Step 4: Run them to verify they pass**

Run: `cd frontend && npx vitest run src/map/markers.test.ts`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit the marker builders**

```bash
git add frontend/src/map/markers.js frontend/src/map/markers.test.ts
git commit -m "feat(map): port practicePin and practiceCallout from MarketMapV3.jsx

C6: pin geometry [78,34]/[39,34], a selected pin reduced to one prominent dot,
and the callout card (photo, name, price, meta) the persistent rf-callout renders.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 6: Write the failing component tests**

In `frontend/src/components/MarketMapView.test.ts`, replace the two role helpers and add the V3 block. First, the helpers — the mosaic is a rectangle, not a bubble, so "overlay" is no longer told apart by `dot()`'s HTML:

```ts
// The two layer groups are identified by ROLE — which production renderer filled them —
// never by construction order. In V3 the overlay group holds mosaic RECTANGLES and the
// dashed drive-time circle; the pins group holds practice markers.
type StubLayer = { seq: number; bounds?: unknown; options?: { radius?: number; icon?: { icon?: { html?: string } } } };
type StubGroup = { clearLayers?: unknown; added: StubLayer[] };

const roleOf = (l: StubLayer): 'overlay' | 'pins' => {
  if (l.bounds !== undefined) return 'overlay';                 // a mosaic L.rectangle
  if (typeof l.options?.radius === 'number') return 'overlay';  // the dashed drive-time ring
  return 'pins';
};
```

and replace `drawOrder`:

```ts
// V3 tells the two draws apart by the Leaflet factory each uses: the overlay is rectangles
// and circles, the pins are divIcon markers.
function drawOrder(stub: LeafletStub, from: number): string[] {
  return stub.calls
    .slice(from)
    .filter((c) => c.fn === 'rectangle' || c.fn === 'circle' || c.fn === 'divIcon')
    .map((c) => (c.fn === 'divIcon' ? 'pins' : 'overlay'));
}
```

Then append this block at the end of the file:

```ts
// ---------------------------------------------------------------------------------------
// V3 (Rev 2). C5 community mosaic shading, C6 pins + persistent callout + panInside,
// C7 the single dashed drive-time ring, C11 no scale control, C13 onBasemap gates the tabs.
// ---------------------------------------------------------------------------------------
describe('MarketMapView — the V3 map', () => {
  const v3Props = (over: Record<string, unknown> = {}) => ({
    practices: practices(3), communities: communities(4), activeLayer: 'income', basemap: 'map',
    activeId: null, onSelect: null, onArea: null, center: [30.31, -97.75], zoom: 10,
    driveCenter: null, showDrive: false, resizeKey: '', recenterKey: 0, ...over
  });

  it('mounts with no scale control and attribution on — the app owns the bottom-right corner for the Layers button', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props() });
    await flushPromises();
    expect(stub.calls[0].args[1]).toEqual({ center: [30.31, -97.75], zoom: 10, zoomControl: false, attributionControl: true });
    expect(stub.calls.filter((c) => c.fn === 'control.scale')).toHaveLength(0);
    expect(stub.calls.filter((c) => c.fn === 'control.zoom')).toHaveLength(0);
  });

  it('shades one mosaic cell per community cell for the active layer, on the shared canvas renderer', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props() });
    await flushPromises();
    const rects = stub.calls.filter((c) => c.fn === 'rectangle');
    expect(rects.length).toBeGreaterThan(0);
    expect(stub.calls.filter((c) => c.fn === 'canvas')).toHaveLength(1);
    for (const r of rects) {
      expect((r.args[1] as { renderer: unknown; fillOpacity: number; stroke: boolean }).renderer).toBe(stub.canvas);
      expect((r.args[1] as { fillOpacity: number }).fillOpacity).toBe(0.5);
      expect((r.args[1] as { stroke: boolean }).stroke).toBe(false);
      expect((r.args[1] as { fillColor: string }).fillColor).toBe('#4c9a6a');
    }
  });

  it('draws nothing when no layer is active, and re-shades when the active layer changes', async () => {
    const stub = installLeafletStub();
    const w = mount(MarketMapView, { props: v3Props({ activeLayer: null }) });
    await flushPromises();
    expect(stub.calls.filter((c) => c.fn === 'rectangle')).toHaveLength(0);
    await w.setProps({ activeLayer: 'income' });
    await flushPromises();
    expect(stub.calls.filter((c) => c.fn === 'rectangle').length).toBeGreaterThan(0);
  });

  it('skips a community with no value for the active layer rather than shading it', async () => {
    const stub = installLeafletStub();
    const blank = { name: 'Blank', lat: 30.5, lng: -97.8, values: {} };
    mount(MarketMapView, { props: v3Props({ communities: [...communities(2), blank], activeLayer: 'density' }) });
    await flushPromises();
    for (const r of stub.calls.filter((c) => c.fn === 'rectangle')) {
      expect((r.args[1] as { fillColor: string }).fillColor).toBe('#2f7d55');
    }
  });

  it('binds the sticky rf-tip carrying name, metric name, value and source note', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, {
      props: v3Props({ communities: [{ name: 'Cedar Park', lat: 30.5, lng: -97.8, metricName: 'Median household income', sourceNote: 'ACS 2019–2023', values: { income: { t: 0.5, label: '$118,400', color: '#4c9a6a' } } }] })
    });
    await flushPromises();
    const overlay = (stub.map.added as StubGroup[]).filter((g) => g.clearLayers)[0];
    const tip = (overlay.added[0] as unknown as { tooltip: { text: string; opts: unknown } }).tooltip;
    expect(tip.opts).toEqual({ sticky: true, className: 'rf-tip' });
    expect(tip.text).toContain('Cedar Park');
    expect(tip.text).toContain('Median household income');
    expect(tip.text).toContain('$118,400');
    expect(tip.text).toContain('ACS 2019–2023');
  });

  it('clicking a mosaic cell reports its community through onArea', async () => {
    const stub = installLeafletStub();
    const seen: string[] = [];
    mount(MarketMapView, {
      props: v3Props({ communities: [{ name: 'Cedar Park', lat: 30.5, lng: -97.8, values: { income: { t: 0.5, label: '$118K', color: '#4c9a6a' } } }], onArea: (n: string) => seen.push(n) })
    });
    await flushPromises();
    const overlay = (stub.map.added as StubGroup[]).filter((g) => g.clearLayers)[0];
    (overlay.added[0] as unknown as { on_click: () => void }).on_click();
    expect(seen).toEqual(['Cedar Park']);
  });

  it('draws ONE dashed unfilled drive-time ring at 16 000 m, not two filled circles (C7)', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props({ showDrive: true, driveCenter: [30.5052, -97.8203] }) });
    await flushPromises();
    const circles = stub.calls.filter((c) => c.fn === 'circle');
    expect(circles).toHaveLength(1);
    expect(circles[0].args).toEqual([[30.5052, -97.8203], { radius: 16000, color: '#003a70', weight: 1.5, dashArray: '4 4', fill: false, interactive: false }]);
  });

  it('draws no ring when showDrive is false, and none when there is no centre to draw it around', async () => {
    const stub = installLeafletStub();
    const w = mount(MarketMapView, { props: v3Props({ showDrive: false, driveCenter: [30.5, -97.8] }) });
    await flushPromises();
    expect(stub.calls.filter((c) => c.fn === 'circle')).toHaveLength(0);
    await w.setProps({ showDrive: true, driveCenter: null, center: null });
    await flushPromises();
    expect(stub.calls.filter((c) => c.fn === 'circle')).toHaveLength(0);
  });

  it('uses practicePin at [78, 34] / [39, 34] and binds the rf-callout at the unselected offset', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props({ practices: practices(1) }) });
    await flushPromises();
    expect(stub.calls.find((c) => c.fn === 'divIcon')!.args[0]).toMatchObject({ className: '', iconSize: [78, 34], iconAnchor: [39, 34] });
    const pins = (stub.map.added as StubGroup[]).filter((g) => g.clearLayers)[1];
    expect((pins.added[0] as unknown as { tooltip: { opts: unknown } }).tooltip.opts)
      .toEqual({ direction: 'top', offset: [0, -34], className: 'rf-callout', permanent: false, opacity: 1 });
  });

  it('selecting a practice makes its callout permanent, opens it, and pans it inside with [48, 110]', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props({ practices: practices(2), activeId: 'p1' }) });
    await flushPromises();
    const pins = (stub.map.added as StubGroup[]).filter((g) => g.clearLayers)[1];
    const selected = pins.added.find((l) => (l as unknown as { tooltip?: { opts: { permanent: boolean } } }).tooltip?.opts.permanent)!;
    expect((selected as unknown as { tooltip: { opts: unknown } }).tooltip.opts)
      .toEqual({ direction: 'top', offset: [0, -22], className: 'rf-callout', permanent: true, opacity: 1 });
    expect((selected as unknown as { tooltipOpened: number }).tooltipOpened).toBe(1);
    expect((selected as unknown as { options: { zIndexOffset: number } }).options.zIndexOffset).toBe(1000);
    expect((stub.map as unknown as { pannedInside: unknown }).pannedInside).toEqual([[30.32, -97.74], { padding: [48, 110], animate: true }]);
  });

  it('clicking a pin reports its id through onSelect', async () => {
    const stub = installLeafletStub();
    const seen: string[] = [];
    mount(MarketMapView, { props: v3Props({ practices: practices(1), onSelect: (id: string) => seen.push(id) }) });
    await flushPromises();
    const pins = (stub.map.added as StubGroup[]).filter((g) => g.clearLayers)[1];
    (pins.added[0] as unknown as { on_click: () => void }).on_click();
    expect(seen).toEqual(['p0']);
  });

  it('renders the Map | Satellite tabs only when onBasemap is passed (desktop), never without it (mobile)', async () => {
    installLeafletStub();
    const desktop = mount(MarketMapView, { props: v3Props({ onBasemap: () => {} }) });
    await flushPromises();
    expect(desktop.findAll('button[aria-pressed]')).toHaveLength(2);
    expect(desktop.find('button[aria-pressed="true"]').text()).toBe('Map');

    installLeafletStub();
    const mobile = mount(MarketMapView, { props: v3Props() });
    await flushPromises();
    expect(mobile.findAll('button[aria-pressed]')).toHaveLength(0);
    expect(mobile.findAll('button[aria-label]').map((b) => b.attributes('aria-label'))).toEqual(['Zoom in', 'Zoom out']);
  });

  it('the basemap tabs call onBasemap and the zoom buttons drive the engine', async () => {
    const stub = installLeafletStub();
    const picked: string[] = [];
    const w = mount(MarketMapView, { props: v3Props({ onBasemap: (k: string) => picked.push(k) }) });
    await flushPromises();
    await w.findAll('button[aria-pressed]')[1].trigger('click');
    expect(picked).toEqual(['satellite']);
    const before = stub.map.zoom;
    await w.find('button[aria-label="Zoom in"]').trigger('click');
    expect(stub.map.zoom).toBe(before + 1);
    await w.find('button[aria-label="Zoom out"]').trigger('click');
    expect(stub.map.zoom).toBe(before);
  });

  it('recenterKey re-applies the view without a prop change to centre or zoom', async () => {
    const stub = installLeafletStub();
    const w = mount(MarketMapView, { props: v3Props() });
    await flushPromises();
    stub.map.setView([1, 2], 3);
    await w.setProps({ recenterKey: 1 });
    await flushPromises();
    expect(stub.map.center).toEqual([30.31, -97.75]);
    expect(stub.map.zoom).toBe(10);
  });

  it('renders at a 390 px phone width — no fixed widths keep the map from filling its host', async () => {
    installLeafletStub();
    const w = mount(MarketMapView, { props: v3Props(), attachTo: document.body });
    await flushPromises();
    const root = w.element as HTMLElement;
    expect(root.style.position).toBe('absolute');
    expect(root.style.inset).toBe('0px');
    expect(root.innerHTML).not.toMatch(/width:\s*\d+px/);
    w.unmount();
  });
});
```

Delete nothing else in this file: every pre-V3 case that still describes behaviour V3 keeps (mount/unmount lifecycle, the merged watcher's ordering invariant, the `!engine` guards, `resizeKey`, `setBase`) stays and must stay green. Where an existing case asserts a bubble, a `pricePin`, `scaleControl: true` or the `layers`/`valueLayer` props, rewrite its **expectation** to the V3 behaviour above — do not delete the case (Global Constraint (d)).

- [ ] **Step 7: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/components/MarketMapView.test.ts`
Expected: FAIL — the new block fails on the first case with `expected { …, scaleControl: true } to equal { …, attributionControl: true }`, and the mosaic cases with `expected [] to have a length greater than 0` (no `rectangle` calls: the component still draws bubbles).

- [ ] **Step 8: Rewrite the component**

Replace `frontend/src/components/MarketMapView.vue` entirely. The control cluster, the status overlay and every literal below are `MarketMapV3.jsx:154-436`, ported:

```vue
<template>
  <div style="position: absolute; inset: 0; background: #f5f5f5;">
    <div ref="host" style="position: absolute; inset: 0;"></div>

    <div
      v-if="status === 'ready'"
      style="position: absolute; right: 12px; top: 16px; z-index: 500; display: flex; flex-direction: column; gap: 4px;"
    >
      <div style="display: flex; flex-direction: column; background: #fff; border: 1px solid #d4dde5; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,58,112,.16); width: 132px;">
        <div v-if="props.onBasemap" style="display: flex; padding: 3px; gap: 2px;">
          <button
            v-for="k in BASEMAP_KEYS"
            :key="k"
            :aria-pressed="props.basemap === k"
            :style="basemapTabStyle(k)"
            @click="props.onBasemap && props.onBasemap(k)"
          >{{ k === 'map' ? 'Map' : 'Satellite' }}</button>
        </div>
        <span v-if="props.onBasemap" style="height: 1px; background: #e6e6e6;"></span>
        <div style="display: flex;">
          <button :style="stackBtn" aria-label="Zoom in" @click="engine && engine.zoomIn()">+</button>
          <span style="width: 1px; background: #e6e6e6;"></span>
          <button :style="stackBtn" aria-label="Zoom out" @click="engine && engine.zoomOut()">−</button>
        </div>
      </div>
    </div>

    <div
      v-if="status !== 'ready'"
      style="position: absolute; inset: 0; display: grid; place-items: center; background: #f5f5f5; text-align: center; padding: 24px; font-family: ProximaNova, Arial, Helvetica, sans-serif;"
    >
      <div v-if="status === 'loading'" style="font-size: 13px; font-weight: 500; color: #494949;">Loading map…</div>
      <div v-else style="max-width: 320px;">
        <div style="font-size: 17px; font-weight: 700; color: #003a70;">Map unavailable</div>
        <p style="font-size: 13px; color: #494949; line-height: 1.6;">The map service could not be reached. Listings on the right are unaffected, and every market layer is still readable as a table in Market snapshot.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { practiceCallout, practicePin } from '../map/markers.js';
import { MOSAIC_STEP, mosaicBbox, mosaicCells } from '../map/mosaic.js';
import { createEngine } from '../map/create';

const props = defineProps({
  practices: { type: Array, default: () => [] }, communities: { type: Array, default: () => [] },
  activeLayer: { type: String, default: null }, basemap: { type: String, default: 'map' },
  onBasemap: { type: Function, default: null }, activeId: { type: String, default: null },
  onSelect: { type: Function, default: null }, onArea: { type: Function, default: null },
  center: { type: Array, default: () => [30.31, -97.75] }, zoom: { type: Number, default: 10 },
  driveCenter: { type: Array, default: null }, showDrive: { type: Boolean, default: false },
  resizeKey: { type: String, default: '' }, recenterKey: { type: Number, default: 0 }
});
const host = ref(null);
const status = ref('loading');
let engine = null;

const BASEMAP_KEYS = ['map', 'satellite'];
const stackBtn = 'flex: 1; height: 32px; display: grid; place-items: center; padding: 0; background: none; border: 0; cursor: pointer; font-family: ProximaNova, Arial, Helvetica, sans-serif; font-size: 17px; font-weight: 500; color: #003a70; line-height: 1;';
const basemapTabStyle = (k) =>
  'flex: 1; height: 28px; border: 0; border-radius: 5px; cursor: pointer; font-family: ProximaNova, Arial, Helvetica, sans-serif; font-size: 12px; font-weight: 500; line-height: 1; color: ' +
  (props.basemap === k ? '#003a70' : '#7a8590') + '; background: ' + (props.basemap === k ? '#deecf7' : 'transparent') + ';';

onMounted(async () => {
  try {
    const e = await createEngine();
    if (!host.value || engine) return;
    // C11: zoomControl:false, attributionControl:true (attribution is legally load-bearing),
    // and NO scale control — Leaflet pins it bottom-right, directly under V3's Layers button.
    await e.mount(host.value, { center: props.center, zoom: props.zoom, basemap: props.basemap, zoomControl: false, scaleControl: false, groups: ['overlay', 'pins'] });
    engine = e;
    status.value = 'ready';
    drawOverlay();
    drawPins();
  } catch { status.value = 'error'; }
});
onBeforeUnmount(() => { if (engine) { engine.destroy(); engine = null; } });

watch([() => props.basemap, status], () => { if (engine) engine.setBase(props.basemap); });
watch([() => props.center && props.center[0], () => props.center && props.center[1], () => props.zoom, () => props.recenterKey, status], () => { if (engine && props.center) engine.setView(props.center, props.zoom, true); });
watch(() => props.resizeKey, () => { if (engine) engine.show(); });

// C7 drive-time ring + C5 community mosaic shading.
function drawOverlay() {
  if (!engine) return;
  engine.clear('overlay');
  const hub = props.driveCenter || props.center;
  if (props.showDrive && hub) {
    engine.circle(hub, 16000, { radius: 16000, color: '#003a70', weight: 1.5, dashArray: '4 4', fill: false, interactive: false }, 'overlay');
  }
  if (!props.activeLayer || !props.communities.length) return;
  const bbox = mosaicBbox(props.communities);
  mosaicCells(props.communities, bbox, MOSAIC_STEP).forEach(({ site, bounds }) => {
    const v = site.values[props.activeLayer];
    if (v == null) return;
    engine.rectangle(bounds, { fillColor: v.color, fillOpacity: 0.5, stroke: false, interactive: true }, 'overlay',
      { html: tipHtml(site, v), sticky: true, className: 'rf-tip' },
      () => props.onArea && props.onArea(site.name));
  });
}

function tipHtml(site, v) {
  return (
    '<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;min-width:150px">' +
      '<div style="font-size:12.5px;font-weight:800;color:#003a70">' + site.name + '</div>' +
      '<div style="font-size:11px;color:#494949;margin-top:3px">' + (site.metricName || '') + '</div>' +
      '<div style="font-size:15px;font-weight:800;color:#003a70;margin-top:1px">' + v.label + '</div>' +
      '<div style="font-size:10px;color:#767676;margin-top:5px">' + (site.sourceNote || '') + '</div>' +
    '</div>'
  );
}

// C6 practice pins: the selected practice's callout stays open on the map, and the map pans
// just far enough to bring both pin and callout inside the viewport.
function drawPins() {
  if (!engine) return;
  engine.clear('pins');
  props.practices.forEach((p) => {
    const selected = p.id === props.activeId;
    const handle = engine.marker([p.lat, p.lng], {
      html: practicePin(p.priceLabel, selected), size: [78, 34], anchor: [39, 34],
      zIndexOffset: selected ? 1000 : 0,
      tooltip: { html: practiceCallout(p), direction: 'top', offset: [0, selected ? -22 : -34], className: 'rf-callout', permanent: selected, opacity: 1 },
      onClick: () => props.onSelect && props.onSelect(p.id)
    }, 'pins');
    if (selected) {
      handle.openTooltip();
      engine.panInside([p.lat, p.lng], [48, 110]);
    }
  });
}

// MarketMapV3.jsx's area effect and pin effect, as ONE ordered watcher. React runs every
// effect whose deps changed in declaration order on each commit, so the overlay's layers are
// always re-added to Leaflet's shared panes before the practice pins and the pins therefore
// paint on top. Two separate Vue watchers cannot promise that: they are queued in the order
// their props are written during the parent's re-render (the design template lists
// `practices` before `communities`), which put the pins first and let the shading repaint
// over them.
//
// The merged dep list is deliberately a superset of the reference's area effect: the overlay
// now also redraws when only `practices` or `activeId` change, which React would not do.
// That over-trigger is the price of the guarantee — clearing and re-adding both groups in
// one callback is the only way to fix their relative pane order — and it is safe because
// both draws are idempotent full rebuilds of their own layer group.
watch(
  [() => props.communities, () => props.activeLayer, () => props.showDrive, () => props.driveCenter && props.driveCenter[0],
    () => props.practices, () => props.activeId, status],
  () => { drawOverlay(); drawPins(); },
  { deep: true }
);
</script>
```

> The dashed ring is passed through `engine.circle()`, whose `CircleStyle` carries `fillColor`/`fillOpacity`. V3's ring has no fill at all, so the design's own option object (`radius`, `color`, `weight`, `dashArray`, `fill: false`, `interactive: false`) is handed through verbatim and the engine's `circle()` spreads it. **If `circle()` as implemented in Task V4 does not forward these keys unchanged, STOP** — that is a real gap between the engine and C7 and John decides whether `circle()` widens or a `ring()` primitive is added. Do not silently approximate the ring with a filled circle.

- [ ] **Step 9: Run them to verify they pass**

Run: `cd frontend && npm run typecheck && npx vitest run src/components/MarketMapView.test.ts`
Expected: PASS — the whole file.

> **Acceptance (README Task 4, verbatim):** "`frontend/src/components/MarketMapView.test.ts` updated and green; choropleth cells appear for every enabled layer, hovering a cell shows the `rf-tip` with name/metric/value/source, selecting a pin opens a persistent callout and the map pans so the callout is fully visible at 1440×940." The 1440×940 half is proven by the `browse-market-panel` visual state in Task V9.

- [ ] **Step 10: Write the failing Vue-only test**

Create `frontend/tests/vue-only.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const FRONTEND = join(import.meta.dirname, '..');
const SRC = join(FRONTEND, 'src');
const DIST = join(FRONTEND, 'dist', '_app');

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

// Global Constraint (c) — John, 2026-09-06: "convert to vue.js zero-gaps zero-regression".
// MarketMapV3.jsx and the rest of the handoff's React files are reference material to PORT,
// never to import or ship. convert-dc.mjs is the only path from the design file to Vue.
describe('the app is Vue-only', () => {
  it('no file under src/ imports react, react-dom or a .jsx module', () => {
    const offenders: string[] = [];
    for (const f of walk(SRC).filter((f) => /\.(vue|ts|js)$/.test(f))) {
      const src = readFileSync(f, 'utf8');
      if (/\bfrom\s+['"]react(-dom)?(\/[^'"]*)?['"]/.test(src)) offenders.push(`${relative(SRC, f)}: react import`);
      if (/\brequire\(\s*['"]react(-dom)?['"]\s*\)/.test(src)) offenders.push(`${relative(SRC, f)}: react require`);
      if (/\bfrom\s+['"][^'"]+\.jsx['"]/.test(src)) offenders.push(`${relative(SRC, f)}: .jsx import`);
    }
    expect(offenders).toEqual([]);
  });

  it('react is not a dependency of the app', () => {
    const pkg = JSON.parse(readFileSync(join(FRONTEND, 'package.json'), 'utf8')) as { dependencies: Record<string, string>; devDependencies: Record<string, string> };
    expect(Object.keys(pkg.dependencies)).not.toContain('react');
    expect(Object.keys(pkg.dependencies)).not.toContain('react-dom');
    expect(Object.keys(pkg.devDependencies)).not.toContain('react');
    expect(Object.keys(pkg.devDependencies)).not.toContain('react-dom');
  });

  it('the built bundle carries no React runtime', () => {
    const js = readdirSync(DIST).filter((f) => f.endsWith('.js'));
    expect(js.length, 'no built bundle to check — run npm run build first').toBeGreaterThan(0);
    const offenders = js.filter((f) => {
      const text = readFileSync(join(DIST, f), 'utf8');
      return text.includes('__REACT_DEVTOOLS_GLOBAL_HOOK__') || text.includes('react-dom') || /\breact\.production\.min\b/.test(text);
    });
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 11: Run it**

Run: `cd frontend && npm run build && npx vitest run tests/vue-only.test.ts`
Expected: PASS, 3 tests. (If it fails, a React import reached `src/` — that is exactly the regression this gate exists for; stop and remove it, do not weaken the test.)

- [ ] **Step 12: Run the frontend gate**

Run: `cd frontend && npm run typecheck && npm test && npm run build`
Expected: PASS on all three; 100 % coverage on `src/components/MarketMapView.vue`, `src/map/markers.js`, `src/map/mosaic.js`, `src/map/engines/leaflet.ts`.

- [ ] **Step 13: Commit**

```bash
git add frontend/src/components/MarketMapView.vue frontend/src/components/MarketMapView.test.ts frontend/tests/vue-only.test.ts
git commit -m "feat(map): port MarketMapView.vue to the V3 map

C5 community mosaic shading on the shared canvas renderer with the sticky
rf-tip; C6 practicePin at [78,34]/[39,34] with a persistent rf-callout and
panInside([48,110]); C7 one dashed unfilled 16 000 m ring; C11 no scale control,
attribution on; C13 the Map|Satellite tabs render only when onBasemap is passed,
so the same component serves the 1440 desktop and the 390 phone. Adds the
Vue-only gate: no React import in src/, no React runtime in the bundle.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task V6: The seven new icons

**Files:**
- Create: `frontend/public/assets/icons/sub-chevron.svg`, `sub-close-thin.svg`, `sub-plus-thin.svg`, `sub-bar-chart.svg`, `sub-reset-view.svg`, `sub-legend-list.svg`, `sub-layers-stack.svg`
- Create: `frontend/tests/icons.test.ts`

**Interfaces:**
- Consumes: `docs/design-reference/design_handoff_practice_match_v3/assets/icons/` (Task V1).
- Produces: seven files under `frontend/public/assets/icons/`, byte-identical to the bundle's. No icon is removed — "No icon was removed between V2 and V3; nothing to delete."

- [ ] **Step 1: Write the failing icon test**

Create `frontend/tests/icons.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const FRONTEND = join(import.meta.dirname, '..');
const PUBLIC_ICONS = join(FRONTEND, 'public', 'assets', 'icons');
const BUNDLE_ICONS = join(FRONTEND, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'assets', 'icons');
const DC = join(FRONTEND, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'Practice Match V3.dc.html');

const NEW_IN_V3 = ['sub-chevron.svg', 'sub-close-thin.svg', 'sub-plus-thin.svg', 'sub-bar-chart.svg', 'sub-reset-view.svg', 'sub-legend-list.svg', 'sub-layers-stack.svg'];

function referenced(text: string): string[] {
  return [...new Set([...text.matchAll(/\/?assets\/icons\/([A-Za-z0-9._-]+\.svg)/g)].map((m) => m[1]))].sort();
}

// README Task 5. Filenames are the contract: a real VIN glyph drops in with no code change.
describe('icon assets', () => {
  it('ships the seven glyphs V3 introduces, byte-identical to the bundle', () => {
    for (const f of NEW_IN_V3) {
      expect(existsSync(join(PUBLIC_ICONS, f)), `${f} is missing from frontend/public/assets/icons/`).toBe(true);
      expect(readFileSync(join(PUBLIC_ICONS, f)).equals(readFileSync(join(BUNDLE_ICONS, f))), `${f} differs from the bundle's copy`).toBe(true);
    }
  });

  it('every icon the V3 design references exists on disk — no /assets/icons 404 on any screen', () => {
    const missing = referenced(readFileSync(DC, 'utf8')).filter((f) => !existsSync(join(PUBLIC_ICONS, f)));
    expect(missing).toEqual([]);
  });

  it('every icon the generated app references exists on disk', () => {
    const missing = referenced(readFileSync(join(FRONTEND, 'src', 'App.vue'), 'utf8')).filter((f) => !existsSync(join(PUBLIC_ICONS, f)));
    expect(missing).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run tests/icons.test.ts`
Expected: FAIL — `sub-chevron.svg is missing from frontend/public/assets/icons/`, and the second test lists all seven.

- [ ] **Step 3: Copy the seven icons**

```bash
cd "/Users/johndean/Development/Practice Match"
for f in sub-chevron sub-close-thin sub-plus-thin sub-bar-chart sub-reset-view sub-legend-list sub-layers-stack; do
  cp "docs/design-reference/design_handoff_practice_match_v3/assets/icons/$f.svg" "frontend/public/assets/icons/$f.svg"
done
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd frontend && npx vitest run tests/icons.test.ts`
Expected: PASS, 3 tests. (The third passes vacuously until Task V7 regenerates `App.vue`; it is a standing invariant from here on.)

- [ ] **Step 5: Run the frontend gate**

Run: `cd frontend && npm run typecheck && npm test && npm run build`
Expected: PASS.

> **Acceptance (README Task 5, verbatim):** "no 404 for `/assets/icons/*` in the browser network log on any screen." The static test above is the fast gate; the end-to-end proof is `npm run test:smoke` and `npm run test:visual`, whose `prepare()` throws on any `console.error` and a missing `<img>` logs one. Both are run in Task V9.

- [ ] **Step 6: Commit**

```bash
git add frontend/public/assets/icons frontend/tests/icons.test.ts
git commit -m "feat(assets): add the seven sub-* glyphs V3 introduces

chevron, thin close, thin plus, bar-chart, reset-view, legend-list and
layers-stack — the VIN set ships none of them (README Task 5). Filenames are the
contract; a real VIN glyph drops in with no code change. Nothing is removed.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task V7: Regenerate the app from V3 — `App.vue`, `pseudo.css`, `app.setup.js`, `logic.js`

**Files:**
- Modify: `frontend/scripts/convert-dc.mjs` (the generated-header literal in `buildAppVue`)
- Modify: `frontend/tests/convert-dc.test.ts` (the header assertion)
- Modify: `frontend/tests/app-generated.test.ts` (the `DC` constant; three new drift tests)
- Modify: `frontend/tests/design-source.test.ts` (two new assertions)
- Modify: `frontend/src/app.setup.js` (the `layerPalette` prop V3 introduces)
- Regenerate: `frontend/src/App.vue`, `frontend/src/generated/pseudo.css`
- Replace: `frontend/src/logic.js`
- Modify: `frontend/src/logic.test.ts` (characterisation updates only where V3 changed a value)

**Interfaces:**
- Consumes: `convert`, `extractTemplate`, `buildAppVue` from `frontend/scripts/convert-dc.mjs` with the `MarketMapV3` mapping (Task V3); `MarketMapView.vue`'s V3 prop list (Task V5); the seven icons (Task V6); `frontend/tests/baseline-manifest.test.ts` (Task V1).
- Produces: `frontend/src/logic.js` exporting `Component` with V3's `renderVals()` — `md.isMarket` unconditional for `screen === 'browse'`, the three named palettes on `layerPalette`, the `econ` layer labelled **"Average Practice Payroll" / "Avg. payroll per practice"**, `mobileVals` carrying `sheetOpen`, `openSheet`, `closeSheet`, `layerLabel`, `basemaps`, `rowStyle`, `datasetRowStyle` and **no** `hasPeek`/`peek`, and **no** `isBrowse`/`browseToggle`/`browseMode`. `frontend/src/app.setup.js` gains `layerPalette: { type: String, default: 'distinct' }`. Task V8 depends on `browseMode` having no reader; Tasks V9 and V10 depend on the regenerated template.

> **`logic.js` is a hand-executed, fully specified transform, not a `gen:app` output.** `npm run gen:app` writes only `src/App.vue` and `src/generated/pseudo.css`; it *reads* `src/app.setup.js` and inlines it. `src/logic.js` is the design file's `<script type="text/x-dc" data-dc-script>` block with exactly three edits: the two-line provenance header plus `import { DCLogic } from './dc-logic.js';`, the platform spec §3 rule-1 asset rewrite (`"assets/` → `"/assets/`, five occurrences in V3), and a trailing `export { Component };`. The bundle's `FILE_INDEX.md` files `logic.js` under "Generated — never hand-edit", which is true in spirit and wrong in mechanism — Step 4 below adds the drift test that makes the transform machine-checked, so "never hand-edit" becomes enforceable rather than aspirational.

> **Prototype scaffolding stays.** The `prototypeBar` jump bar, the "Prototype — access states" shortcuts, the pre-filled demo credentials, `startScreen`/`startViewport` and every fixture in `logic.js` remain exactly as V3 renders them (README §8: "This plan removes none of it — that is Sub-project 2"). They are removed by Wave 2a's Task I8, which spec D2 redefines as a `--launch` mode of `convert-dc.mjs` rather than a hand edit of `App.vue`. **After I8 lands, `npm run gen:app` must not be re-run blindly** — the launch build comes from `npm run gen:app:launch`, and running the plain script would restore the scaffolding. That warning belongs in the same breath as any future regeneration.

- [ ] **Step 1: Repoint the byte-identity gate at V3 (RED)**

In `frontend/tests/app-generated.test.ts`, change the `DC` constant:

```ts
const DC = join(ROOT, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'Practice Match V3.dc.html');
```

In `frontend/scripts/convert-dc.mjs`, change the generated-header literal inside `buildAppVue` (this is the only V2 string left in the generator):

```js
export function buildAppVue(template, setupJs, pseudoCssImport) {
  return `<!-- GENERATED by frontend/scripts/convert-dc.mjs from docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html — do not edit; run \`npm run gen:app\` -->\n<template>\n${template}\n</template>\n\n<script setup>\nimport '${pseudoCssImport}';\n${setupJs}</script>\n`;
}
```

In `frontend/tests/convert-dc.test.ts`, update the matching assertion inside `'is idempotent and buildAppVue assembles the SFC…'`:

```ts
    expect(sfc.startsWith('<!-- GENERATED by frontend/scripts/convert-dc.mjs from docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html — do not edit; run `npm run gen:app` -->\n<template>\n')).toBe(true);
```

In `frontend/tests/design-source.test.ts`, add two assertions inside the existing `describe`:

```ts
  it('the generator stamps the V3 path into every file it writes', () => {
    expect(readFileSync(join(FRONTEND, 'scripts', 'convert-dc.mjs'), 'utf8')).toContain(`design-reference/${V3}/${V3_FILE}`);
  });

  it('the byte-identity gate compares against V3', () => {
    expect(readFileSync(join(FRONTEND, 'tests', 'app-generated.test.ts'), 'utf8')).toContain(`'${V3}'`);
  });
```

Run: `cd frontend && npx vitest run tests/app-generated.test.ts`
Expected: FAIL — `regenerating yields byte-identical App.vue and pseudo.css (no hand edits survive)` fails, because `src/App.vue` is still V2's output.

- [ ] **Step 2: Regenerate `App.vue` and `pseudo.css`**

Run: `cd frontend && npm run gen:app`
Expected: `wrote src/App.vue (…) and src/generated/pseudo.css (… rules)`.

Review the diff — **do not edit the output**. Confirm every removal the checklist promises:

```bash
git diff --stat frontend/src/App.vue frontend/src/generated/pseudo.css
grep -c '<ListingsMap' frontend/src/App.vue        # expect 0 — desktop AND mobile mounts gone
grep -c '<MarketMapView' frontend/src/App.vue      # expect 2 — desktop and mobile
grep -n 'browseToggle\|isBrowse\|basemapTabs' frontend/src/App.vue   # expect no hits
```

Expected removals (DEAD_CODE_CHECKLIST, "Removed for you by the generator"): the whole `v-if="v.isBrowse"` desktop listings layout; both `v.browseToggle` loops; the desktop `<ListingsMap>` mount; the mobile `<ListingsMap>` mount, now a `<MarketMapView>`; the in-panel `basemapTabs` loop. Re-grep for each symbol rather than trusting the bundle's line numbers (Global Constraint (l)).

Run: `cd frontend && npx vitest run tests/app-generated.test.ts`
Expected: the byte-identity test PASSES; the SFC-compiles test PASSES.

- [ ] **Step 3: Add the props drift test and the `layerPalette` prop (RED → GREEN)**

Append to `frontend/tests/app-generated.test.ts` a new `it` inside the existing `describe`:

```ts
  it('app.setup.js declares every prop the design declares — a new design prop is otherwise silently undefined at runtime', () => {
    const html = readFileSync(DC, 'utf8');
    const tag = /<script type="text\/x-dc" data-dc-script[^>]*data-props="([^"]*)"/.exec(html)!;
    const decoded = tag[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&');
    const declared = Object.keys(JSON.parse(decoded) as Record<string, unknown>).filter((k) => !k.startsWith('$'));
    const setup = readFileSync(join(ROOT, 'src/app.setup.js'), 'utf8');
    expect(declared).toContain('layerPalette');
    for (const p of declared) expect(setup, `app.setup.js does not declare the design prop "${p}"`).toMatch(new RegExp(`\\b${p}\\s*:`));
  });
```

Run: `cd frontend && npx vitest run tests/app-generated.test.ts`
Expected: FAIL — `app.setup.js does not declare the design prop "layerPalette"`.

In `frontend/src/app.setup.js`, add the prop V3 introduces (`data-props`: enum `distinct | cool | colorblind`, default `distinct`, section "Market data", label "Data layer palette" — C10):

```js
// Prototype-only props. `prototypeBar` must be false in production.
const props = defineProps({
  prototypeBar: { type: Boolean, default: import.meta.env.VITE_ENVIRONMENT !== 'production' },
  startScreen: { type: String, default: 'gate' },
  startViewport: { type: String, default: 'desktop' },
  // V3 C10: three named palettes — `distinct` (default), `cool`, `colorblind`.
  layerPalette: { type: String, default: 'distinct' }
});
```

Re-run the generator so `App.vue` carries the new setup block (`buildAppVue` inlines `app.setup.js` verbatim):

Run: `cd frontend && npm run gen:app && npx vitest run tests/app-generated.test.ts`
Expected: PASS.

- [ ] **Step 4: Add the `logic.js` port drift test (RED)**

Append to `frontend/tests/app-generated.test.ts`, as a new top-level `describe` at the end of the file:

```ts
// logic.js is NOT written by gen:app — it is the design file's own <script data-dc-script>
// block with exactly three edits: the provenance header + the DCLogic import, the platform
// spec §3 rule-1 asset rewrite, and the trailing export. This test makes that transform
// machine-checked, so "never hand-edit logic.js" is enforceable rather than aspirational.
describe('logic.js is the design script block, ported verbatim', () => {
  const HEADER = "// Ported verbatim from the approved prototype 'Practice Match V3.dc.html'.\n"
    + '// Do not restyle or restructure: every value here is design-approved.\n'
    + "import { DCLogic } from './dc-logic.js';\n";
  const FOOTER = '\nexport { Component };\n';

  function designScript(html: string): string {
    const open = /<script type="text\/x-dc" data-dc-script[^>]*>/.exec(html)!;
    const start = open.index + open[0].length;
    return html.slice(start, html.indexOf('</script>', start));
  }

  it('matches byte-for-byte, header and export aside, with only the documented asset rewrite', () => {
    const body = designScript(readFileSync(DC, 'utf8')).replace(/"assets\//g, '"/assets/').replace(/\n+$/, '\n');
    expect(readFileSync(join(ROOT, 'src/logic.js'), 'utf8')).toBe(HEADER + body + FOOTER);
  });

  it('carries V3\'s market-data shape and none of V2\'s Listings tab', () => {
    const logic = readFileSync(join(ROOT, 'src/logic.js'), 'utf8');
    for (const gone of ['browseMode', 'browseToggle', 'isBrowse', 'hasPeek']) {
      expect(logic, `logic.js still carries ${gone}`).not.toContain(gone);
    }
    for (const present of ['sheetOpen', 'openSheet', 'closeSheet', 'layerLabel', 'datasetRowStyle', 'layerPalette', 'Average Practice Payroll', 'Avg. payroll per practice']) {
      expect(logic, `logic.js is missing ${present}`).toContain(present);
    }
  });
});
```

Run: `cd frontend && npx vitest run tests/app-generated.test.ts`
Expected: FAIL — the byte-for-byte test, with a large string diff (`src/logic.js` is still V2's port).

- [ ] **Step 5: Port `logic.js` from the V3 design file (GREEN)**

Perform the transform the test specifies. Do it mechanically — never by hand-editing the old file:

```bash
cd "/Users/johndean/Development/Practice Match" && python3 - <<'PY'
import re, pathlib
dc = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text(encoding="utf8")
m = re.search(r'<script type="text/x-dc" data-dc-script[^>]*>', dc)
body = dc[m.end():dc.index("</script>", m.end())]
body = body.replace('"assets/', '"/assets/')          # platform spec §3 rule 1
body = re.sub(r'\n+\Z', '\n', body)
header = ("// Ported verbatim from the approved prototype 'Practice Match V3.dc.html'.\n"
          "// Do not restyle or restructure: every value here is design-approved.\n"
          "import { DCLogic } from './dc-logic.js';\n")
pathlib.Path("frontend/src/logic.js").write_text(header + body + "\nexport { Component };\n", encoding="utf8")
print("logic.js:", len(header + body) + 26, "bytes")
PY
```

Run: `cd frontend && npx vitest run tests/app-generated.test.ts tests/design-source.test.ts tests/icons.test.ts`
Expected: PASS on all three files.

- [ ] **Step 6: Update the logic characterisation suite where V3 changed a value**

Run: `cd frontend && npx vitest run src/logic.test.ts`
For each failure, change the **expectation** to V3's value and leave the case in place (Global Constraint (d)). The known movers are the `econ` layer's label and metric copy (C10: "Payroll per Veterinary Establishment (CBP)" / "Revenue per establishment" → **"Average Practice Payroll"** / **"Avg. payroll per practice"**) and any assertion that reads `browseMode`, `browseToggle`, `isBrowse`, `hasPeek` or `peek`. The admin-tabs case (`logic.test.ts:41`) and the seller-listings cases (`:49-51`) are **unaffected** — "My Listings" is the seller dashboard, a different feature with the same word (DEAD_CODE_CHECKLIST). Add one case for each new `mobileVals` member:

```ts
it('mobileVals exposes the market-data sheet and no peek card (C13)', () => {
  const mob = c.renderVals().mob;
  expect(typeof mob.openSheet).toBe('function');
  expect(typeof mob.closeSheet).toBe('function');
  expect(mob.sheetOpen).toBe(false);
  expect(typeof mob.layerLabel).toBe('string');
  expect(Array.isArray(mob.basemaps)).toBe(true);
  expect(mob).not.toHaveProperty('hasPeek');
  expect(mob).not.toHaveProperty('peek');
});
```

Run: `cd frontend && npx vitest run src/logic.test.ts`
Expected: PASS.

- [ ] **Step 7: Run the frontend gate and the leak detector**

Run: `cd frontend && npm run typecheck && npm test && npm run build`
Expected: PASS on all three, including `baseline-manifest.test.ts`, `vue-only.test.ts`, `icons.test.ts`, `app-generated.test.ts`, `convert-dc.test.ts`, `reference-bundle.test.ts`, `design-source.test.ts`.

> **Acceptance (README Task 6, verbatim):** "`npm run typecheck && npm test && npm run build` green; `frontend/tests/app-generated.test.ts` green (it asserts the generated files match the reference — that is the test that catches a hand edit)."

- [ ] **Step 8: Run the full previous gate, and record precisely what is expected to be red**

The Playwright suites cannot all be green here: the screen list still clicks `'Market Data'` and the baselines and DOM snapshots are still V2's. Those are regenerated in Task V9. What **must** be green now is the leak detector — the fifteen unchanged screens, whose oracles have not been touched:

```bash
cd frontend
npx playwright test --config=tests/playwright.config.ts --project=app visual.spec.ts \
  -g "mobile-list|mobile-detail|header-1100|header-1000|detail|requests|seller-dash|wizard-|admin-"
```
Expected: 15 passed. **If any of the fifteen fails here, the port leaked into shared code — STOP and diff** (C14, Global Constraint (f)).

```bash
npx playwright test --config=tests/playwright.config.ts --project=app dom.spec.ts \
  -g "mobile-list|mobile-detail|header-1100|header-1000|detail|requests|seller-dash|wizard-|admin-"
```
Expected: 15 passed, for the same reason.

Expected RED, and made green in Task V9: `browse-listings`, `browse-market`, `browse-market-layers-closed`, `browse-market-panel`, `mobile-map`, `interest-modal` (visual + DOM), and `smoke.spec.ts`'s `'a deep link is honoured after the fixture sign-in'` and `'navigation writes the URL'` (they click `'Market Data'` and assert `'Data Layers'`). Record the failing list; nothing else may be red.

- [ ] **Step 9: Commit**

```bash
git add frontend/scripts/convert-dc.mjs frontend/tests/convert-dc.test.ts frontend/tests/app-generated.test.ts frontend/tests/design-source.test.ts frontend/src/app.setup.js frontend/src/App.vue frontend/src/generated/pseudo.css frontend/src/logic.js frontend/src/logic.test.ts
git commit -m "feat(app): regenerate App.vue, pseudo.css and logic.js from the V3 design

C1 the Listings tab is gone and Browse is one screen; C2-C4 the market-data
column, ramp-chip layer menu and Compare; C8 the merged legend/insight card;
C9 the Layers drawer; C10 three palettes and the Average Practice Payroll
rename; C12 the nine-card rail; C13 the mobile map is now MarketMapView.
app.setup.js gains V3's layerPalette prop. New drift tests pin the logic.js
port and the design-vs-defineProps contract.

Prototype scaffolding stays (README §8). Wave 2a's I8 removes it via
convert-dc.mjs --launch (spec D2); after I8 lands, do not re-run `npm run
gen:app` blindly — the launch build comes from `gen:app:launch`.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task V8: The router loses `/browse`'s `tab` query, without breaking a single old link

**Files:**
- Modify: `frontend/src/router/sync.ts`
- Modify: `frontend/src/router/sync.test.ts`
- Modify: `frontend/src/router/useStateRouteSync.test.ts`
- Modify: `frontend/tests/smoke.spec.ts`

**Interfaces:**
- Consumes: `frontend/src/logic.js` with no `browseMode` reader (Task V7).
- Produces: `RoutedState` without `browseMode` — `{ screen: string; detailId?: string; adminTab?: string; gate?: string; auth?: boolean }`; `stateToRoute({ screen: 'browse' }) -> { path: '/browse', query: {} }`; `routeToPatch({ path: '/browse', … }) -> { screen: 'browse' }` for any `?tab=` value. `ADMIN_TABS` and its `'listings'` member are the **admin console's** tabs — a different feature with the same word — and are untouched. Task V12's identity-plan delta depends on `browseMode` being gone from `RoutedState`.

- [ ] **Step 1: Run the grep gate that authorises removing the field**

The DEAD_CODE_CHECKLIST permits deleting `RoutedState.browseMode` **only if** no reader remains after the regeneration:

```bash
cd "/Users/johndean/Development/Practice Match"
grep -rn "browseMode\|browseToggle" frontend/src
```
Expected: hits only in `frontend/src/router/sync.ts`, `frontend/src/router/sync.test.ts` and `frontend/src/router/useStateRouteSync.test.ts` — nothing in `App.vue` or `logic.js`. If `logic.js` still reads it, **STOP**: Task V7 did not land the V3 script block.

- [ ] **Step 2: Write the failing router tests**

In `frontend/src/router/sync.test.ts`, change the fixture and the browse cases (every other case is untouched):

```ts
const base = { screen: 'gate', detailId: 'p1', adminTab: 'users' };
```

Replace the two `stateToRoute` browse cases with one, and drop `browseMode` from the two `guard`/`needsPatch` cases that carry it:

```ts
  it('maps browse to /browse with no query — V3 has one Browse screen, not two tabs', () =>
    expect(stateToRoute({ ...base, screen: 'browse' })).toEqual({ path: '/browse', query: {} }));
```

Replace the three `routeToPatch` browse cases with:

```ts
  it('/browse → browse', () => expect(routeToPatch(r('/browse'))).toEqual({ screen: 'browse' }));
  it('/browse?tab=market → browse, the legacy query silently ignored', () =>
    expect(routeToPatch(r('/browse', { tab: 'market' }))).toEqual({ screen: 'browse' }));
  it('/browse?tab=listings → browse, the legacy query silently ignored', () =>
    expect(routeToPatch(r('/browse', { tab: 'listings' }))).toEqual({ screen: 'browse' }));
  it('/browse?tab=bogus → browse', () => expect(routeToPatch(r('/browse', { tab: 'bogus' }))).toEqual({ screen: 'browse' }));
  it('a legacy /browse?tab= URL settles without a redirect loop: the state it produces routes back to a bare /browse', () => {
    const patch = routeToPatch(r('/browse', { tab: 'market' }));
    const target = stateToRoute({ ...base, ...patch });
    expect(target).toEqual({ path: '/browse', query: {} });
    expect(routeToPatch(r(target.path, target.query))).toEqual(patch);   // fixed point: no second navigation
  });
```

In the `round-trips every screen` case, replace `{ ...base, screen: 'browse', browseMode: 'market' }` with `{ ...base, screen: 'browse' }`. In the `guard` and `needsPatch` cases, replace `{ screen: 'browse', browseMode: 'market' }` / `{ screen: 'browse', browseMode: 'listings' }` with `{ screen: 'browse' }`.

In `frontend/src/router/useStateRouteSync.test.ts`, re-grep for `browseMode` (the bundle cites line 101; Global Constraint (l)) and drop the field from the state it seeds.

Run: `cd frontend && npx vitest run src/router`
Expected: FAIL — `expected { screen: 'browse', browseMode: 'listings' } to deeply equal { screen: 'browse' }`.

- [ ] **Step 3: Simplify the router**

In `frontend/src/router/sync.ts`, delete `BROWSE_TABS` (line 6 as cited; re-grep), drop the field from `RoutedState`, and collapse both branches:

```ts
export interface RoutedState { screen: string; detailId?: string; adminTab?: string; gate?: string; auth?: boolean }
```

```ts
const ADMIN_TABS = ['users', 'listings', 'activity', 'data'] as const;
```

```ts
    case 'browse': return { path: '/browse', query: {} };
```

```ts
  // Any legacy ?tab= is ignored: Browse Practices is one screen in V3, so /browse,
  // /browse?tab=market and /browse?tab=listings all land here and the URL settles to
  // /browse without a second navigation. Old links and bookmarks must not 404 or loop.
  if (to.path === '/browse') return { screen: 'browse' };
```

`pick()` stays — `ADMIN_TABS` still uses it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run typecheck && npx vitest run src/router`
Expected: PASS.

- [ ] **Step 5: Update the smoke spec's two V2-shaped assertions**

In `frontend/tests/smoke.spec.ts`, keep `'/browse?tab=market'` in `ROUTES` (proving the legacy URL still resolves) and update the two cases that assert the removed tab:

```ts
  test('a deep link is honoured after the fixture sign-in, and a legacy ?tab= settles on Browse', async ({ page }) => {
    await prepare(page);
    await page.goto('/browse?tab=market');
    await page.getByRole('button', { name: 'Approved — enter', exact: true }).click();
    await expect(page).toHaveURL(/\/browse$/);
    await expect(page.getByRole('button', { name: /^Layers/ })).toBeVisible();
  });

  test('navigation writes the URL', async ({ page }) => {
    await prepare(page);
    await page.goto('/');
    await page.getByRole('button', { name: 'Browse', exact: true }).first().click();
    await expect(page).toHaveURL(/\/browse$/);
    await page.getByRole('button', { name: 'Listing', exact: true }).first().click();
    await expect(page).toHaveURL(/\/practices\/p1$/);
    await page.getByRole('button', { name: 'Admin', exact: true }).first().click();
    await page.getByRole('button', { name: /^Data Sources\s*\d/ }).first().click();
    await expect(page).toHaveURL(/\/admin\?tab=data$/);
  });
```

Also update the performance-gate case's comment and target — `/browse?tab=market` still works, but say why:

```ts
  // Performance gate (policy §3): the market map's first paint. The clock starts on the
  // navigation, not after it — the deep link is signed in through the gate's fixture button,
  // which is the only way this URL survives a cold load, so the budget covers boot + gate +
  // the pending deep link + Leaflet's first paint. The `?tab=market` is a legacy no-op kept
  // here deliberately: V3's Browse always shows market data. `[data-map]` is set by
  // LeafletMapEngine.mount() once the map is on the page.
```

- [ ] **Step 6: Run the smoke suite**

Run: `cd frontend && npm run test:smoke`
Expected: PASS. (`prepare()` throws on any `console.error`, so this is also the end-to-end proof that no `/assets/icons/*` 404 remains — README Task 5.)

> **Acceptance (README Task 7, verbatim):** "`/browse`, `/browse?tab=market` and `/browse?tab=listings` all render Browse Practices; the URL settles without a loop; `npm test` green."
> **Zero-risk requirement (DEAD_CODE_CHECKLIST, verbatim):** "`/browse?tab=market` and `/browse?tab=listings` still resolve to Browse Practices — old links and bookmarks must not 404 or loop" and "no route was deleted: `router/routes.ts` is unchanged (every path already renders the one `App` component)". Confirm the second with `git diff --stat frontend/src/router/routes.ts` → empty.

- [ ] **Step 7: Re-run the grep gate**

```bash
grep -rn "browseMode\|browseToggle\|BROWSE_TABS" frontend/src frontend/tests
```
Expected: no hits anywhere.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/router/sync.ts frontend/src/router/sync.test.ts frontend/src/router/useStateRouteSync.test.ts frontend/tests/smoke.spec.ts
git commit -m "feat(router): /browse loses its tab query; legacy values silently no-op

C1: with no Listings tab, ?tab=market and ?tab=listings are meaningless, so they
resolve to the one Browse screen and the URL settles to /browse without a second
navigation. BROWSE_TABS and RoutedState.browseMode go — no reader remains after
the V3 regeneration. ADMIN_TABS' 'listings' member is the admin console's tab, a
different feature with the same word, and is untouched.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task V9: The screen list and the regenerated oracles

**Files:**
- Modify: `frontend/tests/screens.ts`
- Regenerate: `frontend/tests/visual.spec.ts-snapshots/**` (PNGs)
- Regenerate: `frontend/tests/dom-snapshots/**`
- Delete: `frontend/tests/visual.spec.ts-snapshots/browse-listings-darwin.png`, `browse-market-darwin.png` and their DOM snapshots

**Interfaces:**
- Consumes: the regenerated app (Task V7), the V3-serving reference server (Task V2), the V3 router (Task V8).
- Produces: `SCREENS` with **27** entries (25 − 2 collapsed + 3 new). Names Tasks V10–V12 depend on: `browse`, `browse-layer-menu`, `browse-compare-open`, `browse-legend-collapsed`, `browse-market-layers-closed`, `browse-market-panel`, `mobile-map`. The `market` helper is deleted; `browse`, `wizard`, `admin` and `mobile` helpers stay.

> **`browse-market-layers-closed` keeps its name.** README Task 8 says only "update the label" (V3's button reads **Layers** with a count pill, `Practice Match V3.dc.html:519-524`), not "rename the state". The name is now imprecise — V3's drawer *opens* on that click — but renaming it is an unrequested deviation that would orphan a third baseline. **STOP and ask John** if a rename is wanted; do not do it unilaterally.

- [ ] **Step 1: Rewrite the screen list**

In `frontend/tests/screens.ts`, delete the `market` helper and replace the Browse block. The whole file becomes:

```ts
import type { Page } from '@playwright/test';
import { btn, click, jump, waitMap } from './harness';

export interface Screen {
  name: string;
  viewport?: { width: number; height: number }; // default 1440×940 from the config
  steps: (page: Page) => Promise<void>;         // identical clicks on reference and app, from the gate
}

// V3 (C1): Browse Practices is ONE screen — map with market data on the left, the results
// rail on the right. There is no Listings / Market Data toggle and therefore no `market`
// helper: every Browse state starts from `browse`.
const browse = async (p: Page) => { await jump(p, 'Browse'); await waitMap(p); };
const wizard = async (p: Page) => { await jump(p, 'Seller'); await click(p, 'Create a listing'); };
const admin = async (p: Page) => { await jump(p, 'Admin'); };
const mobile = async (p: Page) => { await click(p, 'Mobile view'); await jump(p, 'Browse'); };

export const SCREENS: Screen[] = [
  { name: 'gate-signin', steps: async () => {} },
  { name: 'gate-apply', steps: async (p) => { await click(p, 'Request access'); } },
  { name: 'gate-pending', steps: async (p) => { await click(p, 'Pending approval'); } },
  { name: 'gate-declined', steps: async (p) => { await click(p, 'Request declined'); } },
  { name: 'browse', steps: browse },
  // The Market data card's layer select (V3's `md.toggleLayerMenu` trigger). It is the first
  // aria-haspopup="listbox" on the screen; Compare's identical control is the second, and
  // only exists once Compare is open.
  { name: 'browse-layer-menu', steps: async (p) => { await browse(p); await p.locator('button[aria-haspopup="listbox"]').first().click(); await p.waitForTimeout(400); } },
  // C4: Compare is collapsed by default; opening it reveals the shared layer-select control
  // and the six-row bar chart. Picking the metric that already shades the map would reset the
  // comparison (no self-compare), so pick the second option.
  { name: 'browse-compare-open', steps: async (p) => { await browse(p); await click(p, 'Compare'); await p.locator('button[aria-haspopup="listbox"]').nth(1).click(); await p.getByRole('option').nth(1).click(); await p.waitForTimeout(400); } },
  // C8: the merged legend/insight card is dismissible.
  { name: 'browse-legend-collapsed', steps: async (p) => { await browse(p); await p.getByRole('button', { name: 'Dismiss interpretation' }).click(); await p.waitForTimeout(400); } },
  // C9: V3's drawer button reads "Layers" with a count pill, where V2's read "Data Layers".
  { name: 'browse-market-layers-closed', steps: async (p) => { await browse(p); await click(p, 'Layers'); await p.waitForTimeout(400); } },
  { name: 'browse-market-panel', steps: async (p) => { await browse(p); await p.getByText('Cedar Park').first().click(); await p.waitForTimeout(400); } },
  { name: 'detail', steps: async (p) => { await jump(p, 'Listing'); } },
  // The jump bar's default listing (Cedar Park / p1) always carries a pre-seeded pending
  // request in the prototype's demo data (logic.js `state.requests`), so it never shows
  // "I'm interested" — only "Request sent". Open a listing with no seeded request instead
  // (Round Rock / p2) via a Browse results card, which does show the button.
  { name: 'interest-modal', steps: async (p) => { await browse(p); await p.getByText('Round Rock').first().click(); await click(p, "I'm interested"); } },
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

- [ ] **Step 2: Prove each new state's steps against the reference before trusting them**

The steps run identically on the reference and the app, so a wrong selector fails on both and is invisible in a diff. Verify the three new states on the reference first:

```bash
cd frontend
npx playwright test --config=tests/playwright.config.ts --project=reference reference-baselines.spec.ts \
  -g "browse-layer-menu|browse-compare-open|browse-legend-collapsed"
```
Then open the three PNGs under `frontend/tests/visual.spec.ts-snapshots/` and confirm by eye: the layer menu is open with its ramp chips; Compare is open showing the eyebrow, the second control and the six-row bar chart; the What-this-means card is gone. **If a step timed out or the state does not match the design, fix the step — never the tolerance** (Global Constraint (e)).

- [ ] **Step 3: Regenerate every baseline and DOM snapshot from the V3 reference**

```bash
cd frontend && npm run test:visual:baselines
```
This runs the whole `reference` project — `reference-baselines.spec.ts` (the PNGs) and `reference-dom.spec.ts` (the DOM oracle's snapshots) — against the V3 reference server, for all 27 states.

- [ ] **Step 4: Remove the two orphaned oracles**

```bash
cd "/Users/johndean/Development/Practice Match"
git rm frontend/tests/visual.spec.ts-snapshots/browse-listings-darwin.png frontend/tests/visual.spec.ts-snapshots/browse-market-darwin.png
git rm frontend/tests/dom-snapshots/browse-listings.json frontend/tests/dom-snapshots/browse-market.json
git status --porcelain frontend/tests/visual.spec.ts-snapshots frontend/tests/dom-snapshots
```
Expected: the two Browse names are gone and `browse-darwin.png`, `browse-layer-menu-darwin.png`, `browse-compare-open-darwin.png`, `browse-legend-collapsed-darwin.png` are new. (DEAD_CODE_CHECKLIST: "the orphaned baseline PNG … for whichever screen name you dropped — a stale oracle image is dead weight that still gets committed.")

- [ ] **Step 5: Run the leak detector before looking at anything else**

Run: `cd frontend && npx vitest run tests/baseline-manifest.test.ts`
Expected: PASS — all fifteen frozen SHA-256s unchanged after a full baseline regeneration.
**If any hash moved, STOP and diff.** Do not re-run `baseline-manifest.mjs`; the manifest is the evidence, not the target (C14, spec D6).

- [ ] **Step 6: Eyeball the Browse pair by hand**

The risk register's own mitigation: "regenerate baselines and app screenshots in the **same** commit, and eyeball the Browse pair by hand." Open `browse-darwin.png` and `browse-market-panel-darwin.png` and confirm against `Practice Match V3.dc.html` at 1440×940: the 300 px scrolling market column (C2), the ramp-chip layer menu (C3), the merged legend/insight card at `left: 16px; bottom: 22px; width: 360px` (C8), the navy Layers button with its `6 of 6` pill (C9), the nine result cards with wrapping meta rows and no horizontal scroll (C12), the mosaic shading and the single dashed ring (C5, C7), and the "Tiles © Esri" attribution (Global Constraint (h)).

- [ ] **Step 7: Run the full previous gate**

```bash
cd frontend
npm run typecheck && npm test && npm run build
npm run test:smoke
npm run test:visual
npx playwright test --config=tests/playwright.config.ts --project=app dom.spec.ts
```
Expected: all green — 27 visual states at `maxDiffPixels: 0`, 27 DOM-oracle states, the smoke suite, and the unit suite including `baseline-manifest.test.ts`.

> **Acceptance (README Task 8, verbatim):** "`npm run test:smoke && npm run test:visual` green at zero tolerance."
> **Rule (README Task 8, verbatim):** "Do not relax the tolerance in `tests/playwright.config.ts`; a failure here is the change being wrong, not the gate being strict."
> **Zero-risk requirement (DEAD_CODE_CHECKLIST, verbatim):** "`npm run test:visual` green at zero tolerance, baselines regenerated in the same commit" and "`npm run test:smoke` green."
> **C12 acceptance (verbatim):** "at 1440×940 no card row overflows and the page has no horizontal scroll." Confirmed by `browse` passing at zero tolerance against the reference at that viewport.

- [ ] **Step 8: Commit the screens and the oracles together**

```bash
git add frontend/tests/screens.ts frontend/tests/visual.spec.ts-snapshots frontend/tests/dom-snapshots
git commit -m "test(visual): one Browse state, three new V3 states, oracles regenerated

browse-listings and browse-market collapse into `browse`; the drawer click
target is now `Layers`; browse-layer-menu, browse-compare-open and
browse-legend-collapsed are added for the states V2 had no equivalent for.
Baselines and DOM snapshots are regenerated from the V3 reference in this same
commit, and the fifteen frozen unchanged-screen hashes are byte-identical.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task V10: Mobile — the same map, market data in a full-height sheet

**Files:**
- Modify: `frontend/tests/smoke.spec.ts` (a new `test.describe` block)
- Modify (only if the assertions below demand it): `frontend/src/components/MarketMapView.vue`

**Interfaces:**
- Consumes: the regenerated mobile Map tab (Task V7 — `App.vue`'s mobile `<ListingsMap>` became a `<MarketMapView>`, and `logic.js`'s `mobileVals` gained `sheetOpen`/`openSheet`/`closeSheet`/`layerLabel`/`basemaps`/`rowStyle`/`datasetRowStyle` and lost `hasPeek`/`peek`); `MarketMapView.vue`'s `onBasemap`-gated tabs (Task V5); the regenerated `mobile-map` baseline (Task V9).
- Produces: no new module. The five acceptance assertions and the tap-target assertion below become permanent members of the `app` Playwright project, so a later change that shrinks a row or lets the key drift over the zoom cluster fails immediately.

> **What the phone gets** (reference `Practice Match V3.dc.html:1357-1490`, C13): the same `MarketMapView` the desktop uses, **minus `onBasemap`** — that prop now gates the map's own `Map | Satellite` tabs, because the 132 px control cluster at `right: 12px; top: 16px` and a full-width key cannot share a 388 px-wide map. Mobile omits it and owns basemap switching in the sheet; the `+` / `−` buttons stay. A compact key at `left/right: 12px; bottom: 64px`. One navy button at `bottom: 12px`, 44 px tall, carrying the layers-stack glyph, the active layer name and the dataset count pill. A full-height sheet (`position: absolute; inset: 0; z-index: 700`) with five sections in order — Shading, ramp + source/updated, Compare against, Datasets, What this means / Why it matters, Basemap — a thin `×` in the header and a full-width `Show map` in the footer. **No peek card**: tapping an already-selected pin opens the detail screen. The List / Map toggle and the results list are unchanged.

> **Prototype scaffolding stays here too.** The mobile frame is reached through the design's own "Mobile view" jump-bar control, which Wave 2a's I8 removes together with `startViewport` (spec D2). These tests use it deliberately; when I8 lands they move to whatever control replaces it, and `npm run gen:app` must not be re-run blindly afterwards.

- [ ] **Step 1: Write the failing mobile acceptance tests**

Append to `frontend/tests/smoke.spec.ts`, as a new top-level `test.describe` after the existing one. Extend the file's import to `import { booted, click, jump, prepare, waitMap } from './harness';`:

```ts
// ---------------------------------------------------------------------------------------
// Mobile acceptance (README Task 9, verbatim): "at the prototype's mobile frame (390×800)
// the Map tab shows choropleth shading; the key does not overlap the `+` / `−` cluster
// (`document.elementFromPoint` on each button returns the button); the sheet opens
// full-height and scrolls; every one of the five sections renders; tapping a pin twice
// reaches the detail screen."
//
// And the tap-target rule (C13, verbatim): "every row in the sheet is `min-height: 46px`,
// the basemap buttons are 46px, and the close button is a 44×44 hit area around a 16px
// glyph. Nothing in the sheet is under 44px."
// ---------------------------------------------------------------------------------------
test.describe('mobile: the same map, market data in a sheet', () => {
  const SHEET = 'div[style*="z-index: 700"]';

  async function mobileMap(page: Page) {
    await prepare(page);
    await booted(page);
    await click(page, 'Mobile view');
    await jump(page, 'Browse');
    await click(page, 'Map');
    await waitMap(page);
  }

  test('the Map tab renders the market map inside the 390-wide phone frame', async ({ page }) => {
    await mobileMap(page);
    const box = (await page.locator('.leaflet-container').first().boundingBox())!;
    expect(Math.round(box.width), 'the map is not inside the prototype\'s 390px mobile frame').toBeGreaterThanOrEqual(380);
    expect(Math.round(box.width)).toBeLessThanOrEqual(392);
  });

  test('the Map tab shows community mosaic shading', async ({ page }) => {
    await mobileMap(page);
    // The mosaic is drawn on the engine's shared L.canvas renderer, so "shading is showing"
    // means that canvas has painted pixels. Nothing is drawn from a cross-origin image, so
    // the canvas is untainted and readable.
    const painted = await page.evaluate(() => {
      const c = document.querySelector('.leaflet-overlay-pane canvas') as HTMLCanvasElement | null;
      if (!c) return -1;
      const px = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 3; i < px.length; i += 4) if (px[i] > 0) n++;
      return n;
    });
    expect(painted, 'no canvas in the Leaflet overlay pane — the mosaic never drew').toBeGreaterThan(0);
  });

  test('the key does not overlap the + / − cluster: elementFromPoint on each button returns the button', async ({ page }) => {
    await mobileMap(page);
    for (const label of ['Zoom in', 'Zoom out']) {
      const btnLoc = page.getByRole('button', { name: label, exact: true });
      const box = (await btnLoc.boundingBox())!;
      const hit = await page.evaluate(([x, y, name]) => {
        const el = document.elementFromPoint(x as number, y as number);
        const target = document.querySelector(`button[aria-label="${name}"]`);
        return { same: el === target, contained: !!target && !!el && target.contains(el), got: el ? el.tagName + (el.getAttribute('aria-label') ?? '') : 'null' };
      }, [box.x + box.width / 2, box.y + box.height / 2, label] as const);
      expect(hit.same || hit.contained, `something covers the "${label}" button — elementFromPoint returned ${hit.got}`).toBe(true);
    }
  });

  test('one navy Market data button opens a full-height sheet that scrolls', async ({ page }) => {
    await mobileMap(page);
    const mapBox = (await page.locator('.leaflet-container').first().boundingBox())!;
    await page.locator('button', { hasText: /of \d/ }).last().click();
    const sheet = page.locator(SHEET);
    await expect(sheet).toBeVisible();

    const sheetBox = (await sheet.boundingBox())!;
    expect(Math.round(sheetBox.width)).toBe(Math.round(mapBox.width));
    expect(Math.round(sheetBox.height)).toBe(Math.round(mapBox.height));

    const scrolls = await sheet.locator('.rf-scroll').evaluate((el) => el.scrollHeight > el.clientHeight);
    expect(scrolls, 'the sheet body does not scroll — it cannot be carrying all five sections').toBe(true);
  });

  test('every one of the five sections renders, in order', async ({ page }) => {
    await mobileMap(page);
    await page.locator('button', { hasText: /of \d/ }).last().click();
    const text = await page.locator(SHEET).innerText();
    const order = ['Shading', 'Compare against', 'Datasets', 'What this means', 'Basemap'];
    let at = -1;
    for (const section of order) {
      const next = text.indexOf(section);
      expect(next, `the sheet does not render the "${section}" section`).toBeGreaterThan(-1);
      expect(next, `"${section}" is out of order in the sheet`).toBeGreaterThan(at);
      at = next;
    }
    expect(text).toContain('Why it matters');
    expect(text).toContain('Show map');
  });

  test('every tap target in the sheet is at least 44px', async ({ page }) => {
    await mobileMap(page);
    await page.locator('button', { hasText: /of \d/ }).last().click();
    const sizes = await page.locator(SHEET).locator('button').evaluateAll((els) =>
      els.map((el) => { const r = el.getBoundingClientRect(); return { label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40), w: r.width, h: r.height }; })
    );
    expect(sizes.length, 'the sheet rendered no buttons at all').toBeGreaterThan(5);
    const small = sizes.filter((s) => s.h < 44 || s.w < 44);
    expect(small, 'these sheet tap targets are under 44px').toEqual([]);

    const close = (await page.getByRole('button', { name: 'Close market data' }).boundingBox())!;
    expect(Math.round(close.width)).toBe(44);
    expect(Math.round(close.height)).toBe(44);
    const glyph = (await page.getByRole('button', { name: 'Close market data' }).locator('img').boundingBox())!;
    expect(Math.round(glyph.width)).toBe(16);
    expect(Math.round(glyph.height)).toBe(16);
  });

  test('tapping a pin twice reaches the detail screen — there is no peek card', async ({ page }) => {
    await mobileMap(page);
    const pin = page.locator('.leaflet-marker-icon').first();
    await pin.click();
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(/\/browse$/);              // first tap selects, it does not navigate
    await page.locator('.leaflet-marker-icon').first().click();
    await expect(page).toHaveURL(/\/practices\/p\d+$/);
  });
});
```

Add `type Page` to the Playwright import at the top of the file if it is not already there:

```ts
import { test, expect, type Page } from '@playwright/test';
```

- [ ] **Step 2: Run them and record what fails**

Run: `cd frontend && npm run test:smoke`
Expected: the seven new tests are the only candidates to fail. Every failure is a real defect in the port, not a test to soften. The three that are most likely and their fixes:
- *`elementFromPoint` returns the key, not the button* — the key must sit at `bottom: 64px` and the button strip at `bottom: 12px` (C13). This is generated markup: if it is wrong, the reference and the app disagree and `mobile-map` also fails the visual gate. **Fix the reference-to-app path, never the test.**
- *No canvas in the overlay pane* — `MarketMapView.vue` did not draw, most likely because `activeLayer` is not being passed on mobile. Re-read `Practice Match V3.dc.html:1359`'s `<x-import>` prop list and confirm `App.vue` passes `:active-layer="v.md?.activeLayer"`.
- *The `Map | Satellite` tabs are present on mobile* — `onBasemap` leaked into the mobile mount. `Practice Match V3.dc.html:1359` does not pass `on-basemap`; if `App.vue` does, the generator is at fault, not the component.

If a fix is needed in `MarketMapView.vue`, make it there and re-run `npx vitest run src/components/MarketMapView.test.ts` as well. **If a fix would require editing `App.vue` or `logic.js`, STOP** — the fix belongs in the design reference or the generator (Global Constraint (b), (m)).

- [ ] **Step 3: Run them again to verify they pass**

Run: `cd frontend && npm run test:smoke`
Expected: PASS, all seven new tests plus the pre-existing smoke cases.

> **Acceptance (README Task 9, verbatim):** "at the prototype's mobile frame (390×800) the Map tab shows choropleth shading; the key does not overlap the `+` / `−` cluster (`document.elementFromPoint` on each button returns the button); the sheet opens full-height and scrolls; every one of the five sections renders; tapping a pin twice reaches the detail screen."
> **Tap targets (README Task 9, verbatim):** "Every tap target in the sheet is ≥44px: option and dataset rows `min-height: 46px`, basemap buttons 46px, and the close button a 44×44 hit area with a 16px glyph (negative margins keep the header's optical alignment)."

- [ ] **Step 4: Run the full previous gate and the leak detector**

```bash
cd frontend
npm run typecheck && npm test && npm run build
npm run test:smoke
npm run test:visual
npx playwright test --config=tests/playwright.config.ts --project=app dom.spec.ts
npx vitest run tests/baseline-manifest.test.ts
```
Expected: all green. In particular `mobile-list` and `mobile-detail` must still be byte-identical — C13: "The three mobile baselines will all move. `mobile-map` changes completely; `mobile-list` and `mobile-detail` should not — check them by hand." The manifest test is that check, automated; also open `mobile-map-darwin.png` and confirm by eye that it shows the shaded map, the compact key, the navy Market data button and no price pills or clusters.

- [ ] **Step 5: Commit**

```bash
git add frontend/tests/smoke.spec.ts frontend/src/components/MarketMapView.vue
git commit -m "test(mobile): pin V3's market-data sheet acceptance at 390x800

C13: the mobile Map tab is the desktop map. The seven assertions are the
bundle's own acceptance, verbatim — mosaic shading painted on the overlay
canvas, elementFromPoint proving the key never covers the +/- cluster, a
full-height scrolling sheet with all five sections in order, every tap target
>= 44px with a 44x44 close around a 16px glyph, and a second tap on a selected
pin reaching the detail screen because there is no peek card.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task V11: The dead-code sweep — one deletion per commit, in the checklist's order

**Files (one commit each, in this order):**
1. Delete: `frontend/src/components/ListingsMap.vue` · Modify: `frontend/src/app.setup.js`, `frontend/src/App.vue` (regenerated)
2. Modify: `frontend/src/map/markers.js` (`pill`, `clusterIcon`, `clusterize`), `frontend/src/map/markers.test.ts`
3. Modify: `frontend/src/map/markers.js` (`pricePin`), `frontend/src/map/markers.test.ts`
4. Modify: `frontend/src/map/markers.js` (`dot`), `frontend/src/map/markers.test.ts`

**Interfaces:**
- Consumes: Task V10 green (the ordering rule: "delete it and its import at `app.setup.js:4`, but only after Task 9 is green, and **in its own commit so a revert is one `git revert`**").
- Produces: `frontend/src/map/markers.js` exporting exactly `practicePin` and `practiceCallout`. No engine surface changes: `MountOptions.scaleControl` and `engines/leaflet.ts`'s scale-control lines are **kept** — "No component passes `true` after this work, but it is one tested line and re-adding a scale bar is a product decision, not a code one."

> **What is already discharged elsewhere, and must be re-verified here, not re-done:** `router/sync.ts`'s `BROWSE_TABS`, the `browseMode` branch in `stateToRoute` and `RoutedState.browseMode` (Task V8) · `screens.ts`'s `market` helper and one of `browse-listings`/`browse-market`, plus the orphaned baseline PNGs (Task V9) · `MarketMapView.vue`'s `layers.competition` bubble pass and its `layers`/`valueLayer` props (Task V5) · every "Removed for you by the generator" line (Task V7).

> **Explicitly kept, and why** (DEAD_CODE_CHECKLIST, "Do NOT delete — looks dead, isn't"): `engine.ts`'s `scaleControl` option and `engines/leaflet.ts`'s scale-control lines · `engines/leaflet.test.ts`'s mount-contract block (renamed in Task V4, not deleted) · `ADMIN_TABS`'s `'listings'` member · `logic.js`'s seller listings and `logic.test.ts`'s seller cases · `docs/design-reference/design_handoff_practice_match_v2/`.
> **One recorded judgement the checklist does not cover:** `convert-dc.mjs`'s `COMPONENTS` entry `AustinMap: 'ListingsMap'` and the `convert-dc.test.ts` case that exercises it are **kept**. They are generator grammar, not app code — a pure string transform, exercised by a unit test that never imports the component — and V3 emits no `AustinMap`. Removing them is not on any checklist and would be an unrequested deviation. Flagged for John in the hand-back note.

### Commit 1 — `ListingsMap.vue`

- [ ] **Step 1: Prove it is unreferenced except by its import**

```bash
grep -rn "ListingsMap" frontend/src
```
Expected: exactly two hits — `frontend/src/app.setup.js` (the import) and `frontend/src/App.vue` (the same import line, inlined by the generator). **No `<ListingsMap>` element anywhere.** If a mount remains, Task V7 did not regenerate cleanly: STOP.

- [ ] **Step 2: Delete the component and its import**

```bash
git rm frontend/src/components/ListingsMap.vue
```

In `frontend/src/app.setup.js`, delete the line:

```js
import ListingsMap from './components/ListingsMap.vue';
```

Regenerate so `App.vue`'s inlined setup block matches (the import lives inside the generated file; editing `App.vue` by hand would violate Global Constraint (b)):

Run: `cd frontend && npm run gen:app`

- [ ] **Step 3: Verify the grep gate and the gates**

```bash
grep -rn "ListingsMap" frontend/src            # expect: no hits
cd frontend && npm run typecheck && npm test && npm run build
npx vitest run tests/baseline-manifest.test.ts
```
Expected: all green, including `app-generated.test.ts` (App.vue is byte-identical to a fresh generation) and the fifteen frozen hashes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ListingsMap.vue frontend/src/app.setup.js frontend/src/App.vue
git commit -m "refactor(map): delete ListingsMap.vue, dead since the mobile port

V3's mobile Map tab is MarketMapView, so nothing mounts the listings map on any
screen. Its own commit so a revert is one \`git revert\` (DEAD_CODE_CHECKLIST).
The import is removed from app.setup.js and App.vue regenerated, never edited.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Commit 2 — the clustering helpers

- [ ] **Step 1: Prove they are unreferenced**

```bash
grep -rn "clusterize\|clusterIcon\|\bpill\b" frontend/src
```
Expected: hits only in `frontend/src/map/markers.js` (the definitions) and `frontend/src/map/markers.test.ts` (their tests). If anything else references them, STOP.

- [ ] **Step 2: Delete the three functions and the four tests that cover them**

From `frontend/src/map/markers.js`, delete `pill`, `clusterIcon` and `clusterize` in full.

From `frontend/src/map/markers.test.ts`, delete exactly these four cases (Global Constraint (d) — these are the named, authorised test deletions; "`clusterize` has unit tests in `map/markers.test.ts` — delete those with it, never leave orphan tests"):
- `'pill muted/active'`
- `'pill neither muted nor active falls back to the default (unselected) palette'`
- `'clusterIcon and clusterize'`
- `'clusterize uses the wider cell below zoom 8'`

and remove `clusterIcon, clusterize, pill` from the file's import list.

- [ ] **Step 3: Verify**

```bash
grep -rn "clusterize\|clusterIcon\|\bpill\b" frontend/src   # expect: no hits
cd frontend && npm run typecheck && npm test && npm run build
npx vitest run tests/baseline-manifest.test.ts
```
Expected: green, `markers.js` still at 100 % coverage.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/map/markers.js frontend/src/map/markers.test.ts
git commit -m "refactor(map): delete pill, clusterIcon and clusterize with ListingsMap

Dead with the listings map. Their four unit tests are deleted with them — never
leave orphan tests (DEAD_CODE_CHECKLIST). Own commit, one \`git revert\`.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Commit 3 — `pricePin`

- [ ] **Step 1: Prove it is unreferenced**

```bash
grep -rn "pricePin" frontend/src
```
Expected: hits only in `frontend/src/map/markers.js` and `frontend/src/map/markers.test.ts`. (The checklist asks for exactly this check: "Verify with `grep -rn pricePin frontend/src` before deleting.")

- [ ] **Step 2: Delete `pricePin` and its test**

Delete `pricePin` from `frontend/src/map/markers.js`, delete the case `'pricePin active/inactive'` from `frontend/src/map/markers.test.ts`, and drop `pricePin` from the import list.

- [ ] **Step 3: Verify**

```bash
grep -rn "pricePin" frontend/src                            # expect: no hits
cd frontend && npm run typecheck && npm test && npm run build
npx vitest run tests/baseline-manifest.test.ts
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/map/markers.js frontend/src/map/markers.test.ts
git commit -m "refactor(map): delete pricePin, replaced by practicePin

C6: V3's pin is practicePin at [78,34]/[39,34]; nothing renders the V2 price
pill any more. Own commit, one \`git revert\`.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Commit 4 — `dot`

- [ ] **Step 1: Prove it is unreferenced, checking `MarketMapView.test.ts` first**

```bash
grep -rn "\bdot(" frontend/src
grep -n "dot" frontend/src/components/MarketMapView.test.ts
```
Expected: hits only in `frontend/src/map/markers.js` and `frontend/src/map/markers.test.ts`. `MarketMapView.test.ts` must not reference `dot` — Task V5 replaced its `roleOf`/`drawOrder` helpers, which used `dot()`'s HTML shape to tell the two draws apart. If it still does, STOP and finish that rewrite first ("check `MarketMapView.test.ts` first").

- [ ] **Step 2: Delete `dot` and its test**

Delete `dot` from `frontend/src/map/markers.js`, delete the case `'dot'` from `frontend/src/map/markers.test.ts`, and drop `dot` from the import list. The file now exports exactly `practicePin` and `practiceCallout`; update its header comment's scope if it names the removed builders.

- [ ] **Step 3: Verify**

```bash
grep -rn "\bdot(" frontend/src                              # expect: no hits
cd frontend && npm run typecheck && npm test && npm run build
npx vitest run tests/baseline-manifest.test.ts
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/map/markers.js frontend/src/map/markers.test.ts
git commit -m "refactor(map): delete dot, replaced by community mosaic shading

C5: V3 shades contiguous area with rectangles on a canvas renderer rather than
drawing one sized bubble per community. Own commit, one \`git revert\`.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Closing the checklist

- [ ] **Step 1: Re-verify every line the checklist assigns to another task**

```bash
cd "/Users/johndean/Development/Practice Match"
grep -rn "browseMode\|browseToggle\|BROWSE_TABS\|isBrowse\|hasPeek\|basemapTabs" frontend/src frontend/tests   # expect: no hits
grep -rn "Market Data tab" frontend/src                                                                        # expect: no hits
grep -rn "valueLayer\|layers.competition" frontend/src                                                          # expect: no hits
git diff --stat main -- frontend/src/router/routes.ts                                                           # expect: empty
ls frontend/tests/visual.spec.ts-snapshots | grep -c "browse-listings\|browse-market-darwin"                    # expect: 0
grep -n "scaleControl" frontend/src/map/engine.ts frontend/src/map/engines/leaflet.ts                           # expect: still present — KEPT on purpose
grep -n "'listings'" frontend/src/router/sync.ts                                                                # expect: ADMIN_TABS only
ls docs/design-reference/design_handoff_practice_match_v2 >/dev/null                                            # expect: still there
```

- [ ] **Step 2: Run the full previous gate**

```bash
cd frontend
npm run typecheck && npm test && npm run build
npm run test:smoke
npm run test:visual
npx playwright test --config=tests/playwright.config.ts --project=app dom.spec.ts
npx vitest run tests/baseline-manifest.test.ts
```
Expected: all green — 27 visual states at zero tolerance, 27 DOM states, the smoke suite including the seven mobile acceptance tests, 100 % coverage on every hand-written file, and the fifteen frozen hashes unchanged.

- [ ] **Step 3: Prove the backend was never touched**

> **Zero-risk requirement (DEAD_CODE_CHECKLIST, verbatim):** "backend untouched: `git diff --stat app/ migrations/ scripts/ tests/` is empty."

```bash
cd "/Users/johndean/Development/Practice Match"
git diff --stat main -- app/ migrations/ scripts/ tests/
```
Expected: empty output.

- [ ] **Step 4: Commit nothing here** — this closing section is verification only. If any grep or gate above is not as stated, STOP and report.

---

## Task V12: Cross-plan deltas, the version bump, and the QA hand-back

**Files:**
- Create: `frontend/tests/cross-plan-deltas.test.ts`
- Modify: `docs/superpowers/plans/2026-09-05-practice-match-identity-access-email.md` (Tasks I7, I8)
- Modify: `docs/superpowers/plans/2026-09-05-practice-match-map-engines.md` (Tasks M5, M7)
- Modify: `docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md` (D3, D14, the `LAYERS` label, the layer-rendering table, the basemap licence item)
- Modify: `CLAUDE.md` (the V2 folder's new role)
- Modify: `frontend/package.json`, `pyproject.toml` (one patch, in lockstep)

**Interfaces:**
- Consumes: `RoutedState` without `browseMode` (Task V8); `ListingsMap.vue` deleted (Task V11); `logic.js`'s "Average Practice Payroll" copy (Task V7).
- Produces: three amended plans whose next execution rebases onto V3's shape rather than V2's, and `frontend/tests/cross-plan-deltas.test.ts` proving the amendments landed. Nothing in `frontend/src/` changes.

> **Why the drift test lives under `frontend/tests/`, not `tests/`.** The DEAD_CODE_CHECKLIST's zero-risk requirement is that `git diff --stat app/ migrations/ scripts/ tests/` be empty for this branch (Global Constraint (i)). A pytest docs test would break it. The frontend suite reads repo files freely (`design-source.test.ts`, `reference-bundle.test.ts`, `paths.test.ts` all do), so it is the right home here.

- [ ] **Step 1: Write the failing cross-plan drift test**

Create `frontend/tests/cross-plan-deltas.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = join(import.meta.dirname, '..', '..');
const PLANS = join(ROOT, 'docs', 'superpowers', 'plans');
const read = (f: string) => readFileSync(join(PLANS, f), 'utf8');

const IDENTITY = '2026-09-05-practice-match-identity-access-email.md';
const MAP_ENGINES = '2026-09-05-practice-match-map-engines.md';
const CENSUS = '2026-09-05-practice-match-census-data-layer.md';

// Browse V3 spec §6. These three plans were written against V2's Browse screen and go stale
// the moment V3 merges; this test is what stops them being executed against the old shape.
describe('cross-plan deltas (Browse V3 spec §6)', () => {
  it('the identity plan no longer keys a permission on browseMode', () => {
    const md = read(IDENTITY);
    expect(md).not.toContain("patch.browseMode === 'market'");
    expect(md).not.toContain("'browse-market': 'market.read'");
    expect(md).not.toContain("ROUTE_PERMS['browse-market']");
    expect(md).toContain("browse: 'page.browse'");
    expect(md).toContain("can('market.read')");
  });

  it('the identity plan executes the launch-removal list through the generator, not by hand-editing App.vue', () => {
    const md = read(IDENTITY);
    expect(md).toContain('convert-dc.mjs --launch');
    expect(md).toContain('gen:app:launch');
    expect(md).not.toContain('remove jump bar markup, `gateStates`, demo credentials');
  });

  it('the map-engines plan no longer edits ListingsMap.vue and rebases onto V3\'s engine shape', () => {
    const md = read(MAP_ENGINES);
    expect(md).not.toContain('`ListingsMap.vue` (use `useMapHost()`)');
    expect(md).not.toContain('and `ListingsMap.vue`');
    expect(md).toContain('rectangle');
    expect(md).toContain('panInside');
    expect(md).toContain('TooltipSpec');
  });

  it('the census plan documents V3 rendering, the payroll label, the reserved word and the migration range', () => {
    const md = read(CENSUS);
    expect(md).toContain('community mosaic shading');
    expect(md).toContain('Average Practice Payroll');
    expect(md).toContain('Avg. payroll per practice');
    expect(md).not.toMatch(/community bubble `dot\(/);
    expect(md).toContain('015');
    expect(md).toContain('one decision record');
  });

  it('CLAUDE.md names the V2 folder as the regression oracle for the unchanged screens', () => {
    const md = readFileSync(join(ROOT, 'CLAUDE.md'), 'utf8');
    expect(md).toContain('design_handoff_practice_match_v2');
    expect(md).toContain('regression oracle');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run tests/cross-plan-deltas.test.ts`
Expected: FAIL — five failures, the first reading `expected '…' not to contain "patch.browseMode === 'market'"`.

- [ ] **Step 3: Amend the identity plan, Task I7**

Re-grep for each string (Global Constraint (l)).

In I7's **Produces** paragraph, replace the `ROUTE_PERMS` parenthetical:

```
`ROUTE_PERMS: Record<string, Permission>` (`browse → page.browse`, `detail → listing.read`, `requests → request.read_own`, `seller → page.seller`, `admin-* → page.admin`); the market column inside Browse checks `can('market.read')` separately, honouring `MARKET_DATA_PUBLIC` (when false, anonymous and applicant visitors see the map and results without shading and a sign-in prompt in the market column)
```

Replace the `ROUTE_PERMS` constant:

```ts
export const ROUTE_PERMS: Record<string, Permission> = { browse: 'page.browse', detail: 'listing.read', requests: 'request.read_own', seller: 'page.seller', admin: 'page.admin' };
```

Replace `permFor`:

```ts
function permFor(patch: Partial<RoutedState>): Permission | null {
  if (!patch.screen || patch.screen === 'gate') return null;
  // Browse V3 (spec D3): Browse Practices is ONE screen, so the route permission keys on
  // `patch.screen` alone — there is no browseMode to branch on. The market-data column
  // inside the screen checks can('market.read') itself, honouring MARKET_DATA_PUBLIC.
  return ROUTE_PERMS[patch.screen] ?? null;
}
```

In I7's test snippet, replace the browse case:

```ts
    expect(guard({ ...base, auth: true }, { screen: 'browse' }, { me: buyer })).toEqual({ apply: { screen: 'browse' }, pending: null });
```

Add one sentence to the end of I7's `screens.ts` note:

```
`screens.ts` edits apply **on top of** Browse V3's screen list (docs/superpowers/plans/2026-09-06-browse-v3-mobile.md, Task V9): there is one `browse` state, not `browse-listings`/`browse-market`, and three new states — `browse-layer-menu`, `browse-compare-open`, `browse-legend-collapsed`.
```

- [ ] **Step 4: Amend the identity plan, Task I8**

In I8's **Files → Modify** list, replace the `frontend/src/App.vue (…)` entry with:

```
`frontend/scripts/convert-dc.mjs` (a `--launch` mode that strips the prototype blocks during conversion), `frontend/package.json` (a `gen:app:launch` twin of `gen:app`), `frontend/tests/app-generated.test.ts` (asserts BOTH modes are byte-identical to a fresh conversion), `frontend/tests/convert-dc.test.ts` (unit tests for the stripping rules)
```

Replace I8's Step 3 heading and body:

```markdown
- [ ] **Step 3: Execute the launch-removal list through the generator (`convert-dc.mjs --launch`), never by hand**

Browse V3 spec D2: `frontend/src/App.vue` is generated, so a hand edit is undone by the next
`npm run gen:app` and breaks `frontend/tests/app-generated.test.ts`. Add a `--launch` flag to
`convert-dc.mjs` that, during conversion, drops the jump-bar markup block, the
"Prototype — access states" shortcuts block and the pre-filled demo credentials, and add a
`gen:app:launch` script that writes the same three outputs. `app-generated.test.ts` asserts
both modes reproduce their committed output byte-for-byte, so the launch build stays honest
and `npm run gen:app` still reproduces the prototype build. `startScreen`/`startViewport` are
dropped from `app.setup.js`'s `defineProps` in the same change. The `unavailable` gate state
is added to the design reference (a Claude Design update) and reaches the app by
regeneration — not by editing `App.vue`.

**After this task lands, `npm run gen:app` must not be re-run for a production build**: the
launch build comes from `npm run gen:app:launch`.
```

- [ ] **Step 5: Amend the map-engines plan, Tasks M5 and M7**

In M5's **Files → Modify** list, drop `ListingsMap.vue`:

```
- Modify: `frontend/src/map/create.ts` (config-driven), `frontend/vite.config.ts` (`manualChunks`, `build.manifest`), `frontend/src/components/MarketMapView.vue` (use `useMapHost()`), `frontend/src/main.ts` (`installGateWatcher(router)`), `frontend/src/map/boundary.test.ts` (allow the Google loader in `engines/`)
```

In M5's components paragraph, replace the sentence naming both components:

```
Components: `MarketMapView.vue` — the only map component after Browse V3 deleted `ListingsMap.vue` — replaces its `createEngine()` call (Task 1b) with `const host = useMapHost(); engine = await host.attach(hostEl, { center, zoom, basemap, zoomControl: false, scaleControl: false }); … onBeforeUnmount(() => host.detach())`.
```

Add a sequencing note at the top of M5:

```markdown
> **Rebase note (Browse V3, spec D4).** This task lands **after** the Browse V3 sub-project.
> `engine.ts` by then already carries `AreaStyle`, `TooltipSpec`, `Handle.openTooltip`,
> `rectangle(bounds, style, group, tooltip?, onClick?)` and `panInside(pos, padding)`, and
> `MarketMapView.vue` is the V3 port (community mosaic shading on one shared canvas renderer,
> `rf-tip`/`rf-callout`, one dashed 16 km ring, `scaleControl: false`). `GoogleMapEngine`
> must implement `rectangle` and `panInside` too, and `engines/contract.test.ts` must cover
> them for both engines. `ListingsMap.vue` no longer exists.
```

In M7, correct the three `?tab=market` comments (the URLs still work — they are legacy no-ops):

```ts
    // `?tab=market` is a legacy no-op after Browse V3 (spec D4): Browse Practices is one
    // screen and always shows market data. The URL is kept here because it is the shape old
    // links take, and it must keep resolving.
```

- [ ] **Step 6: Amend the census plan**

Replace decision **D3**:

```
| D3 | **Tract-level choropleth vector tiles deferred to Phase C.** Browse V3 ships *community mosaic shading* — client-side `L.rectangle` cells over community areas from the market-data payload — which is community granularity, not tract. The word "choropleth" is reserved in this programme for the Phase C server-generated MVT tile pipeline (spec §7/§10), which still has no consumer. | YAGNI; flagged for the VIN Foundation with the basemap licence question. |
```

Replace decision **D14**:

```
| D14 | **Migration ranges:** SP3-A `015`–`059`, SP3-B `060`+. `001`–`002` are taken (`001_init`, `002_interest_signup`) and SP2/identity holds `010`–`014`. | Phase B tables reference `listing(id)`, which SP2 creates; numbered ordering must guarantee it exists first. |
```

Renumber every migration filename in the plan accordingly — `migrations/002_census_registry.sql` → `migrations/015_census_registry.sql`, `003_census_geo.sql` → `016_census_geo.sql`, `004_census_measures.sql` → `017_census_measures.sql` — and update the precondition note that cites the `010`–`059` range. Re-grep for `002_census_registry` to be sure none is missed.

Rewrite the **Layer rendering contract** table's rendering column against V3 (C5, C7). The four rows that name a bubble become:

```
| Median Household Income (`income`) | community mosaic shading, green ramp (`L.rectangle` cells, `fillOpacity: 0.5`, step 0.0055); legend buckets `<$60K … >$150K` | … |
| Pet Ownership (est.) (`pets`) | community mosaic shading, orange ramp | … |
| Population Growth (`growth`) | community mosaic shading, **brown** ramp (C10: teal read as a second green beside income) | … |
| Households (`households`) | community mosaic shading, blue ramp | … |
| Average Practice Payroll (`econ`) | community mosaic shading, rose ramp; buckets `<$450K … >$900K` | … |
```

and the two drive-time rows collapse to one:

```
| Drive-time catchment (`drive`) | one dashed, unfilled ring: `radius: 16000, color: '#003a70', weight: 1.5, dashArray: '4 4', fill: false, interactive: false` (C7 — V2's two filled circles are gone) | … |
```

Add a sentence under the table:

```
Rendering follows the approved V3 design (`docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html`, `MarketMapV3.jsx`) and the shipped `frontend/src/components/MarketMapView.vue` / `frontend/src/map/mosaic.js`, not V2's bubbles.
```

Rename the econ layer everywhere the API and the UI meet (`LAYERS`, `/api/layers` fixtures, `LABELS`, the metric-label test): `"label": "Economic Profile"` → `"label": "Average Practice Payroll"`, and `"Payroll per establishment"` → `"Avg. payroll per practice"`. The metric key `revenue_per_establishment` is unchanged — only the human copy moves. Add this rename to the plan's existing "Design-vs-spec copy conflicts" list in Task B6.

Replace the basemap-licence open item with a single decision record:

```
**Basemap licence — one decision record, owned by John and the VIN Foundation.** The approved design uses Esri tiles ("Tiles © Esri", "Imagery © Esri, Maxar, Earthstar Geographics"); this spec registered CARTO. It is **one** open question, recorded here and referenced — not restated — by the Map-engines plan §12 and the Browse V3 spec §"Legally load-bearing". Do not swap either way without that decision. Attribution stays visible on every map regardless (`attributionControl: true`).
```

Add the same one-line reference in the map-engines plan §12 in place of its own duplicate open item.

- [ ] **Step 7: Amend CLAUDE.md**

Under "## Source of truth for the UI", after the (already repointed, Task V2) first line, add:

```markdown
`docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html` is kept as the **regression oracle** for the fifteen screens V3 does not touch (`mobile-list`, `mobile-detail`, `header-1100`, `header-1000`, `detail`, `requests`, `seller-dash`, the four `wizard-*`, the four `admin-*`) — their baseline hashes are frozen in `frontend/tests/baseline-manifest.json`. Retire it only when that manifest retires.
```

- [ ] **Step 8: Run the drift test**

Run: `cd frontend && npx vitest run tests/cross-plan-deltas.test.ts`
Expected: PASS, 5 tests.

- [ ] **Step 9: Bump the version in lockstep**

`frontend/package.json`: `"version": "0.1.1"`. `pyproject.toml`: `version = "0.1.1"`. (`app/version.py` reads `pyproject.toml`, so no backend file changes — Global Constraint (i).)

Run: `poetry run pytest tests/test_versions.py -q`
Expected: PASS.

- [ ] **Step 10: Prove the backend is untouched and still green**

```bash
cd "/Users/johndean/Development/Practice Match"
git diff --stat main -- app/ migrations/ scripts/ tests/     # expect: empty
docker compose -f docker-compose.dev.yml up -d
poetry run pytest
```
Expected: the diff is empty and the whole backend suite is green — the proof that this sub-project changed no backend file (spec §5).

- [ ] **Step 11: Commit**

```bash
git add docs/superpowers/plans/2026-09-05-practice-match-identity-access-email.md docs/superpowers/plans/2026-09-05-practice-match-map-engines.md docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md CLAUDE.md frontend/tests/cross-plan-deltas.test.ts frontend/package.json pyproject.toml
git commit -m "docs(plans): record the Browse V3 cross-plan deltas; bump to 0.1.1

Spec §6. Identity I7's permFor() keys on patch.screen alone (browseMode is gone)
and the market column checks can('market.read'); I8 executes the launch-removal
list through convert-dc.mjs --launch instead of hand-editing the generated
App.vue. Map-engines M5 drops ListingsMap.vue and rebases onto V3's engine
shape; M7's ?tab=market comments say it is a legacy no-op. The census plan's
layer-rendering table is rewritten for community mosaic shading and the single
dashed ring, the econ layer is 'Average Practice Payroll', 'choropleth' is
reserved for the Phase C tract tiles, migrations start at 015, and the
Esri-vs-CARTO licence becomes one decision record. A drift test keeps all of it
true. CLAUDE.md names the V2 folder as the regression oracle.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 12: Full gate, then merge to `main`**

```bash
cd frontend
npm run typecheck && npm test && npm run build
npm run test:smoke
npm run test:visual
npx playwright test --config=tests/playwright.config.ts --project=app dom.spec.ts
npx vitest run tests/baseline-manifest.test.ts
cd .. && poetry run pytest
```
Expected: everything green. Then merge `feat/browse-v3` into `main` and push to **both** remotes:

```bash
git push origin main
git push production main
```

- [ ] **Step 13: Confirm the Railway target, then deploy to QA only**

```bash
railway status     # MUST read "Project: Practice Match" — read it back before anything else
scripts/deploy.sh QA
scripts/verify-deploy.sh QA
```
Expected: `verify-deploy.sh QA` green — `environment=qa`, `site_mode=app`, `commit_sha` equal to this checkout's HEAD, PostGIS and Redis OK. **Production is not deployed by this sub-project** (spec §5, Global Constraint (j)); it stays in `coming_soon`.

- [ ] **Step 14: Click-through on https://qa.foundation.vin**

Walk every changed flow by hand and screenshot each:

1. **Sign in** → **Browse Practices**. One screen: map on the left with shading, nine result cards on the right, **no Listings / Market Data toggle**.
2. **Layer select** — open the Market data dropdown; seven options (`No shading — practices only` + six datasets), each with its four-stop ramp chip; the active row carries a check. Pick a different layer; the map re-shades and the key's bucket labels change.
3. **Compare** — collapsed by default with a thin `+`; open it; the `COMPARE AGAINST` eyebrow, the second layer-select and the six-row bar chart appear, each bar in the class colour that community is shaded with. Pick the metric already shading the map: the comparison resets (no self-compare).
4. **Layers drawer** — the navy **Layers** button with its `6 of 6` pill; open it, the 296 px panel sits above the button; disable a dataset and confirm it leaves the Market data dropdown; re-enable it.
5. **Legend / insight card** — one card reading **What this means** with **Why it matters** beneath the divider; dismiss it with the thin `×`.
6. **Map** — hover a shaded area: the `rf-tip` shows name, metric, value and source. Click a practice pin: a persistent callout opens with photo, name, price and meta, and the map pans so the whole callout is visible. **"Tiles © Esri" is visible.** Switch to **Satellite** and back; attribution follows.
7. **Drive time** — enable it: one dashed ring, not two filled circles.
8. **Legacy URLs** — visit `/browse?tab=market` and `/browse?tab=listings`: both land on Browse, the URL settles to `/browse`, nothing loops.
9. **Mobile view** → **Map** tab: shading, the compact key above the button strip, one navy **Market data** button. Open the sheet: full height, scrolls, five sections. Tap a pin, then tap it again: the detail screen opens. Back to **List**: unchanged.
10. **Unchanged screens** — Listing detail, Requests, Seller dashboard, the wizard and the four admin tabs: spot-check that nothing moved.

- [ ] **Step 15: Write the forwardable summary and the engineer's note**

Plain language, for stakeholders, plus screenshots of the live QA screens:

> **Browse Practices is now one screen.** The Listings / Market Data toggle is gone. The map sits on the left with market data shaded over the communities it covers; the nine practice cards sit on the right. You pick which dataset shades the map from a dropdown that shows each dataset's colour scale; a Compare panel puts a second metric beside it as a bar chart; a Layers button chooses which datasets are available at all; and one card explains what the shading means and why it matters. Selecting a practice opens a card on the map that stays open, and the map moves just enough to keep it in view. Drive-time is now a single dashed ring at ten miles.
>
> **On a phone**, the Map tab shows the same map. A navy **Market data** button opens a full-height panel with everything the desktop has — shading, sources, Compare, datasets, the explanation and the basemap switch — with every control comfortably tappable. Tapping a practice pin a second time opens its listing.
>
> **Nothing about the market numbers themselves has changed**: they are still the design's sample figures. The real Census-backed data is a separate, already-approved piece of work.
>
> This is on QA (https://qa.foundation.vin) only. Production is unchanged and still shows the Coming Soon page.

> **Engineer's note.** Zero-tolerance pixel and DOM gates green on all 27 states; the fifteen screens V3 does not touch are byte-identical to before the port, verified by a committed SHA-256 manifest at four checkpoints. 100 % coverage on every hand-written frontend file. No backend file changed (`poetry run pytest` green, `git diff app/ migrations/ scripts/ tests/` empty). **Risks:** (1) the community mosaic is thousands of `L.rectangle`s on one shared canvas renderer — profiled at 1440×940 and 390×800, but it is the largest new code and the first thing to look at if the map ever feels slow on an older phone; (2) three approved plans (Identity, Map-engines, Census) were amended to match V3 and must be re-read before they are executed — the amendments are held true by `frontend/tests/cross-plan-deltas.test.ts`; (3) once Wave 2a's Task I8 lands, `npm run gen:app` must not be re-run for a production build — the launch build comes from `gen:app:launch`.

---

## Self-Review

Run against the spec with fresh eyes, per the writing-plans skill.

**1. Spec coverage.** Every section of `docs/superpowers/specs/2026-09-06-browse-v3-mobile-design.md`:

| Spec item | Task |
|---|---|
| §2 In-scope: land the bundle | V1 |
| §2 repoint the generator and reference server | V2 |
| §2 extend the map engine | V4 |
| §2 port `MarketMapView.vue` | V5 |
| §2 the seven new icons | V6 |
| §2 regenerate `App.vue`/`logic.js`/`app.setup.js`/`pseudo.css` | V7 |
| §2 the router's `tab` query becomes a no-op | V8 |
| §2 the test screen list and baselines | V9 |
| §2 the mobile port (Task 9) | V10 |
| §2 the dead-code sweep (Task 10) | V11 |
| §2 the cross-plan deltas + QA verification and hand-back | V12 |
| §2 Out: Census API, Google engine, the launch-removal list, production | excluded everywhere; recorded in V7's and V10's scaffolding notes and V12's I8 delta |
| §3 the generator is the single source | Global Constraint (b); V7 |
| §3 V2 folder kept as the oracle | V1 Step 8, V12 Step 7 |
| §4 D1 sequencing / worktree | plan header ("Branch") |
| §4 D2 I8 via `--launch` | V7 note, V10 note, V12 Step 4 |
| §4 D3 permissions on the merged Browse | V12 Step 3 |
| §4 D4 map-engines follows V3 | V12 Step 5 |
| §4 D5 census follows V3's rendering and copy | V12 Step 6 |
| §4 D6 baselines regenerated, fifteen byte-identical | V1, V9 Step 5, V10 Step 4, V11 |
| §4 D7 tolerance never relaxed | Global Constraint (e); V9 Step 7 |
| §4 D8 dead-code order, one file per commit | V11 |
| §4 D9 line numbers advisory | Global Constraint (l); repeated in V4, V8, V12 |
| §5 quality gates (unit, typecheck, build, smoke, visual, DOM, bundle budget, drift tests) | end of V3, V4, V5, V6, V7, V9, V10, V11, V12 |
| §5 mobile acceptance at 390×800 | V10 |
| §5 backend suite unaffected | V11 closing Step 3; V12 Step 10 |
| §5 attribution visible | Global Constraint (h); V5 mount options; V12 Step 14.6 |
| §5 QA-only deployment | V12 Steps 13–14 |
| §6 all five cross-plan delta rows | V12 Steps 3–7 |
| §7 risk 1 (mosaic) | V4 (unit-tested before any baseline), V5, engineer's note |
| §7 risk 2 (mobile rewrite; byte-identical leak detector) | V1, V10 Step 4 |
| §7 risk 3 (generator constructs before regeneration) | V3, ordered before V7 |
| §7 risk 4 (two worktrees) | plan header; V12 Step 4 |
| §7 risk 5 (stale plans) | V12 |

**Gaps found and closed inline:** (i) the spec and `FILE_INDEX.md` both call `logic.js` "generated", but `gen:app` writes only `App.vue` and `pseudo.css` — V7 Steps 4–5 add the explicit port and a drift test that makes it machine-checked. (ii) Neither the spec nor the bundle mentions V3's new `layerPalette` prop, which must be declared in `app.setup.js` or `PALETTES[props.layerPalette]` reads `undefined` — V7 Step 3 adds it plus a `data-props`-vs-`defineProps` drift test. (iii) The bundle's Task-2 acceptance ("`gen:app` runs without error") is unsatisfiable before the generator learns `MarketMapV3` — V2 Step 10 records the exact expected failure and V3 Step 5 discharges it. (iv) `convert-dc.mjs`'s generated-header literal and `app-generated.test.ts`'s `DC` constant both name V2 and are not in the bundle's Task-2 file list — moved into V7 so the byte-identity gate never goes red between tasks.

**2. Placeholder scan.** No "TBD", "TODO", "implement later", "add appropriate error handling", "write tests for the above" or "similar to Task N" appears. Every code step carries real code; every repeated construct is repeated in full rather than cross-referenced. Two steps deliberately say "record what fails and fix the port" (V10 Step 2, V7 Step 6) — both enumerate the specific expected failures and the specific fix for each, and both forbid softening the test.

**3. Type consistency.** Checked across tasks: `rectangle(bounds, style, group, tooltip?, onClick?)` is declared in V4's Interfaces, implemented in V4 Step 10, called in V5's `drawOverlay` and asserted in V4's tests with the same five arguments. `panInside(pos, padding)` is a two-argument engine method throughout (the `{ padding, animate: true }` object is built inside the engine, never by the caller). `Handle.openTooltip?()` is declared optional in `engine.ts`, always returned by `marker()` and `rectangle()`, and called as `handle.openTooltip()` in `MarketMapView.vue` and `handle.openTooltip!()` in the TypeScript test. `TooltipSpec.html` is the only key stripped by `tipOptions`, and every test's expected `opts` object omits exactly `html`. `mosaicBbox`/`mosaicCells`/`MOSAIC_STEP` keep the same names in `mosaic.js`, its test and `MarketMapView.vue`. `UNCHANGED_SCREENS`/`MANIFEST_PATH`/`hashBaselines` keep the same names in `baseline-manifest.mjs` and its test. `MarketMapView.vue`'s prop names match `Practice Match V3.dc.html:324` kebab-for-camel, one for one, and the V3 generator test asserts that mapping.

---

## Appendix A — Zero-gap coverage map

Every acceptance criterion, change-log entry, dead-code rule and file-index entry in the bundle, with the task that owns it and the test that proves it.

### A.1 README acceptance criteria

| # | Bundle task | Owning task | Test that proves it |
|---|---|---|---|
| 1 | Land the reference bundle | V1 | `reference-bundle.test.ts` (4 cases) + the by-hand `python3 -m http.server` render |
| 2 | Repoint generator, reference server, CLAUDE.md | V2 (+V3 Step 5 for the `gen:app` clause) | `design-source.test.ts`, `reference-server.test.ts`, `npm test`, the by-hand `:4174` check |
| 3 | Extend the map engine | V4 | `leaflet.test.ts` V3 block (10 cases), `mosaic.test.ts` (6), `global.test.ts` (2), `npm run typecheck && npm test` |
| 4 | Port `MarketMapView.vue` | V5 | `MarketMapView.test.ts` V3 block (15 cases), `markers.test.ts` (4 new); 1440×940 via `browse-market-panel` in V9 |
| 5 | Icons — no `/assets/icons/*` 404 | V6 | `icons.test.ts` (3) + `npm run test:smoke`'s `console.error` gate (V8 Step 6) |
| 6 | Regenerate | V7 | `app-generated.test.ts` (5 cases incl. the new logic.js and defineProps drift tests), `npm run typecheck && npm test && npm run build` |
| 7 | Router | V8 | `sync.test.ts` (incl. the fixed-point no-loop case), `useStateRouteSync.test.ts`, `smoke.spec.ts` |
| 8 | Test screens + baselines | V9 | `npm run test:smoke && npm run test:visual` at zero tolerance; `baseline-manifest.test.ts` |
| 9 | Mobile | V10 | `smoke.spec.ts`'s 7-case mobile describe (shading, `elementFromPoint`, full-height + scroll, five sections, tap targets, double-tap → detail) |
| 10 | Dead code | V11 | per-commit grep gates + the full previous gate + `baseline-manifest.test.ts` after each |

### A.2 CHANGE_LOG C1–C14

| Entry | Owning task | Test |
|---|---|---|
| C1 Listings tab removed | V7 (template/logic), V8 (router), V9 (screens) | `app-generated.test.ts` logic-shape case; `sync.test.ts`; the single `browse` baseline |
| C2 Market data panel, 300 px `rf-scroll` column | V7 | `browse` visual + DOM baselines |
| C3 Layer menu rows carry the layer's ramp | V7, V6 | `browse-layer-menu` baseline; `icons.test.ts` (`sub-chevron`) |
| C4 Compare against | V7, V3 (`:ref` support) | `browse-compare-open` baseline; `convert-dc.test.ts` ref case |
| C5 Community mosaic shading replaces bubbles | V4, V5 | `mosaic.test.ts`; `leaflet.test.ts` canvas/rectangle cases; `MarketMapView.test.ts` mosaic + `rf-tip` cases |
| C6 Practice pins and callouts | V4, V5 | `markers.test.ts` `practicePin`/`practiceCallout`; `MarketMapView.test.ts` selection/panInside case |
| C7 One dashed 16 000 m ring | V5 | `MarketMapView.test.ts` "ONE dashed unfilled drive-time ring" case |
| C8 Legend + interpretation merged | V7, V6 | `browse-legend-collapsed` baseline; `icons.test.ts` (`sub-bar-chart`, `sub-legend-list`) |
| C9 Layers drawer | V7, V6 | `browse-market-layers-closed` baseline; `icons.test.ts` (`sub-layers-stack`) |
| C10 Three palettes; econ renamed | V7 | `app-generated.test.ts` logic-shape case (`layerPalette`, "Average Practice Payroll"); `logic.test.ts` |
| C11 No scale control, attribution on | V4, V5 | `MarketMapView.test.ts` mount case; `leaflet.test.ts` mount-contract block |
| C12 Results rail, wrapping meta row | V7 | `browse` baseline at 1440×940 (zero tolerance = no overflow, no horizontal scroll) |
| C13 Mobile map is the desktop map | V5 (`onBasemap` gate), V7 (generated), V10 (acceptance) | `MarketMapView.test.ts` onBasemap case; the 7-case mobile describe; `mobile-map` baseline |
| C14 What did not change | V1, V9, V10, V11 | `baseline-manifest.test.ts` at four checkpoints |

### A.3 DEAD_CODE_CHECKLIST

| Line | Owning task | Gate |
|---|---|---|
| Generator removes: desktop `v-if="v.isBrowse"` branch, both `browseToggle` loops, desktop `<ListingsMap>`, mobile `<ListingsMap>` → `<MarketMapView>`, `mobileVals.hasPeek`/`peek`, `basemapTabs`, `isBrowse`+`browseToggle`, every `browseMode` read, the "Market Data tab" header | V7 | V7 Step 2 greps; `app-generated.test.ts` logic-shape case; V11 closing greps |
| `grep -rn "browseMode\|browseToggle" frontend/src` → no hits outside tests | V8 | V8 Steps 1, 7 |
| By hand: `BROWSE_TABS`, the `stateToRoute` branch, `RoutedState.browseMode` (only if no grep hit) | V8 | V8 Steps 1, 3, 7 |
| By hand: `screens.ts` `market` helper; one of `browse-listings`/`browse-market`; the orphaned baseline PNG | V9 | V9 Steps 1, 4 |
| By hand: `MarketMapView.vue`'s `layers.competition` pass and its `layers`/`valueLayer` props | V5 | V5 Step 8 (rewritten file); V11 closing grep |
| After Task 9, own commit: `ListingsMap.vue` + `app.setup.js` import | V11 commit 1 | grep gate + full gate |
| After Task 9, own commit: `pill`, `clusterIcon`, `clusterize` + their unit tests | V11 commit 2 | grep gate + named test deletions |
| `pricePin` (verify by grep first) | V11 commit 3 | grep gate |
| `dot` (check `MarketMapView.test.ts` first) | V11 commit 4 | grep gate + the `MarketMapView.test.ts` grep |
| **Keep:** `scaleControl` option; the renamed engine describe; `ADMIN_TABS.listings`; seller listings; the V2 folder | V4, V11, V12 | V11 closing greps; `reference-bundle.test.ts` "keeps the V2 folder" |
| Zero-risk: legacy `?tab=` resolves, no route deleted, the fifteen byte-identical, visual green at zero tolerance with baselines in the same commit, smoke green, backend untouched | V8, V9, V10, V11, V12 | V8 Step 6; V9 Steps 5, 7, 8; V11 closing Steps 1–3; V12 Step 10 |

### A.4 FILE_INDEX

| Entry | Owning task |
|---|---|
| `App.vue`, `logic.js`, `app.setup.js`, `generated/pseudo.css` | V7 |
| `frontend/package.json` `gen:app` | V2 |
| `map/engine.ts`, `map/engines/leaflet.ts`, `map/testing/leaflet-stub.ts` | V4 |
| `map/mosaic.js` (new) | V4 |
| `map/markers.js` (`practicePin`, `practiceCallout`) | V5 |
| `components/MarketMapView.vue` | V5 |
| `styles/global.css` (`.rf-callout`, `.rf-tip`) | V4 |
| `router/sync.ts` | V8 |
| `tests/screens.ts` | V9 |
| `components/ListingsMap.vue` (deleted) | V11 |
| `tests/reference-server.mjs` | V2 |
| `CLAUDE.md` | V2, V12 |
| Tests that assert the old behaviour: `sync.test.ts`, `useStateRouteSync.test.ts`, `reference-server.test.ts`, `MarketMapView.test.ts`, `leaflet.test.ts`, `app-generated.test.ts`, `dom.spec.ts`/`dom.ts`/`dom.walk.test.ts` | V8, V2, V5, V4, V7, V9 |
| `logic.test.ts` (admin/seller cases unaffected) | V7 Step 6 |
| Untouched deliberately: `index.html`, `lib/leaflet.js`, `ImageSlot.vue`, `dc-logic.js`, `tokens.css`, all of `app/`, `migrations/`, `scripts/`, `tests/`, `coming-soon/`, the V2 folder | verified in V11 closing Steps 1–3 and V12 Step 10 |

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-06-browse-v3-mobile.md`. Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration. **REQUIRED SUB-SKILL:** `superpowers:subagent-driven-development`.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.
