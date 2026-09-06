# Browse V3 and Mobile — Design

**Status:** approved by John Dean 2026-09-06 ("the V3 Rev 2 bundle implementation should be done before the Census plan and the two map-engine plans"). Sub-project "Browse V3". Runs now, in its own worktree, in parallel with Wave 2a's backend tasks; merges to `main` before the Census, Map-engines and Google plans start.

**Source of truth:** the design handoff bundle *Practice Match V3, Rev 2* (John's Claude Design export, delivered 2026-09-06), landed in the repo as `docs/design-reference/design_handoff_practice_match_v3/`. `Practice Match V3.dc.html` is the authority for every pixel, value and word of copy. The bundle's own `README.md` (10 tasks), `CHANGE_LOG.md` (C1–C14), `DEAD_CODE_CHECKLIST.md` and `FILE_INDEX.md` are the requirements; this spec records how they join the programme and the decisions the bundle could not make.

## 1. What changes for the member

Browse Practices becomes one screen. The Listings / Market Data toggle is gone. The map, with market data shaded over the communities it covers, sits on the left; the results rail with nine practice cards sits on the right. On the map: a layer select with colour-ramp chips, three named palettes, a Compare panel (six-row bar chart), a Layers drawer with a count pill, one merged legend-and-insight card, persistent practice callouts that pan into view, and a single dashed 16 km drive-time ring. On mobile, the Map tab shows the same map; a navy **Market data** button opens a full-height sheet (Shading, ramp and sources, Compare against, Datasets, What this means, Basemap) with every tap target at 44 px or more. The List tab and the detail screen do not change.

Nothing about accounts, applications or e-mail is in this sub-project (Wave 2a). Nothing about the real Census API is in it either (Sub-project 3): the market data on the V3 screens is the design's fixture data, exactly as on qa.foundation.vin today.

## 2. Scope

**In:** the bundle's ten tasks — land the reference bundle; repoint the generator and the reference server; extend the map engine (rectangles on a shared canvas renderer, tooltip specs, `panInside`, no scale control on the market map); port `MarketMapView.vue` from `MarketMapV3.jsx`; the seven new icons; regenerate `App.vue`/`logic.js`/`app.setup.js`/`pseudo.css`; the router's `tab` query becomes a no-op; the test screen list and baselines; the mobile port (Task 9); the dead-code sweep (Task 10) — plus the cross-plan deltas in §6 and a QA verification and hand-back.

**Out:** the real Census-backed market data API and its `dataset_registry` (Census plan); the Google map engine and the Admin engine switch (Map-engines and Google plans); removal of the prototype jump bar, demo credentials and access-state shortcuts (Wave 2a Task I8, see D2); any change to production, which stays in Coming Soon mode.

## 3. Architecture

The surgical change is not hand-editing `App.vue`. `frontend/src/App.vue`, `frontend/src/logic.js` and `frontend/src/app.setup.js` are **generated** from the design file by `frontend/scripts/convert-dc.mjs` (committed at `c00bc37`; the bundle's "confirm it is committed" precondition is already satisfied — verified against `main` at 47281cb). The work is: land the bundle → repoint `gen:app` and the reference server → regenerate → close the gaps the generator cannot cover (map-engine primitives, the hand-written `MarketMapView.vue`, the router, the screen list, the icons, the mobile sheet's hand-written parts) → sweep dead code, one file per commit.

Components and their owners:

| Unit | Kind | Change |
|---|---|---|
| `docs/design-reference/design_handoff_practice_match_v3/` | reference (never shipped) | new; mirrors `_ds/`, `vendor/leaflet.*`, `vendor/react*.production.min.js`, `doc-page.js` from the V2 folder unchanged; the V2 folder stays as the regression oracle for the screens that must not move |
| `frontend/package.json` `gen:app`; `frontend/tests/reference-server.mjs` | tooling | point at V3; the reference server's `''` root serves `Practice Match V3.dc.html`; `/coming-soon` root unchanged |
| `frontend/src/map/engine.ts`, `engines/leaflet.ts`, new `map/mosaic.js`, `map/testing/leaflet-stub.ts` | hand-written | `rectangle()` on one shared `L.canvas({padding: 0.3})` per mount; `MarkerOptions.tooltip: string \| TooltipSpec`; `panInside(latlng, {padding: [48, 110]})` that no-ops after `destroy()`; `MountOptions.scaleControl` kept (default true) and set `false` by the market map |
| `frontend/src/components/MarketMapView.vue` | hand-written | port of `MarketMapV3.jsx`: community mosaic shading per enabled layer (step 0.0055, bbox padded 0.13 lat / 0.15 lng), `rf-tip` hover, `practicePin` markers with persistent `rf-callout` and `panInside`, one dashed unfilled 16 000 m ring (`weight 1.5, dashArray '4 4'`), `zoomControl:false, attributionControl:true`, no scale control; renders at 390 px wide; `Map \| Satellite` tabs only when `onBasemap` is passed (desktop passes it, mobile does not) |
| `frontend/src/App.vue`, `logic.js`, `app.setup.js`, `generated/pseudo.css` | generated | regenerated; three new generator constructs must be supported first: `ref="{{ … }}"`, `aria-selected="{{ o.selected }}"`, paired `<sc-if>` on `<img src>` |
| `frontend/src/router/sync.ts` | hand-written | `/browse`, `/browse?tab=market`, `/browse?tab=listings` all render Browse; `BROWSE_TABS`, the `browseMode` branch and (once no grep hit remains) `RoutedState.browseMode` go |
| `frontend/tests/screens.ts`, `visual.spec.ts-snapshots/**` | gates | `browse-listings` + `browse-market` → `browse`; "Data Layers" click target → "Layers"; new `browse-compare-open`, `browse-layer-menu`, `browse-legend-collapsed`; mobile states `mobile-map` (changes), `mobile-list`, `mobile-detail` (byte-identical) |
| `frontend/public/assets/icons/` | assets | seven new SVGs: `sub-chevron`, `sub-close-thin`, `sub-plus-thin`, `sub-bar-chart`, `sub-reset-view`, `sub-legend-list`, `sub-layers-stack` |
| `frontend/src/components/ListingsMap.vue`, `map/markers.js` `pill`/`clusterIcon`/`clusterize`/`pricePin`/`dot` | dead after Task 9 / Task 4 | deleted **after Task 9 is green, each in its own commit** so a revert is one `git revert`; `engine.ts`'s `scaleControl` option is kept; `ADMIN_TABS.listings` and the seller "My Listings" code are unrelated and untouched |

## 4. Decisions

- **D1 — Sequencing (John, 2026-09-06).** Browse V3 runs now in worktree `feat/browse-v3` from `main`, in parallel with Wave 2a's backend tasks (I4–I6, which touch no frontend file). It merges to `main` first, under the standing condition (production stays Coming Soon; QA remains the working marketplace). It precedes the Census plan and both map-engine plans. Wave 2a rebases onto `main` before its frontend tasks I7/I8.
- **D2 — The generator stays the single source; I8 stops hand-editing `App.vue`.** The launch-removal list (jump bar, demo credentials, access-state shortcuts, `startScreen`/`startViewport`) is executed by a `--launch` mode of `convert-dc.mjs` that strips those blocks during conversion, so `npm run gen:app` reproduces the launch build and `frontend/tests/app-generated.test.ts` stays honest. The identity plan's Task I8 is amended to this design (§6). Until I8 lands, the prototype scaffolding remains, exactly as the bundle's README §8 expects.
- **D3 — Permissions on the merged Browse screen.** The screen is gated by `page.browse`; the market-data shading, layer menu, Compare and Layers drawer on it are gated by `market.read` (honouring `MARKET_DATA_PUBLIC`: when false, anonymous and applicant visitors see the map and results without shading and a sign-in prompt in the market column). The identity plan's Task I7 `permFor()` loses its `browseMode` key (§6).
- **D4 — Map-engines follows V3.** Map-engines Task M5 rebases onto V3's `engine.ts`/`MarketMapView.vue` shape and drops its `ListingsMap.vue` edit (the file no longer exists). Its e2e URLs `/browse?tab=market` keep working as a no-op but its comments are corrected.
- **D5 — Census follows the approved design's rendering and copy.** The Census plan's layer-rendering table is rewritten against V3 (community mosaic shading per layer, one dashed 16 km ring); the economic layer is labelled **"Average Practice Payroll" / "Avg. payroll per practice"** everywhere the API and the UI meet; V3's client-side shading is called **community mosaic shading** in every document so it is not confused with the Census plan's later tract-level tile pipeline (which keeps the word choropleth); the Census plan's migrations renumber to start at `015` (identity uses `010`–`014`).
- **D6 — Baselines.** Browse baselines are regenerated from V3 at zero tolerance in the same run (`npm run test:visual:baselines` then `npm run test:visual`). The fourteen screens the bundle names as unchanged — `mobile-list`, `mobile-detail`, `header-1100`, `header-1000`, `detail`, `requests`, `seller-dash`, the four `wizard-*`, the four `admin-*` — must be **byte-identical** before and after; a movement means the port leaked into shared code: stop and diff. `mobile-map` is expected to change completely.
- **D7 — Tolerance is never relaxed.** `tests/playwright.config.ts` stays at zero; a failure is the change being wrong, not the gate being strict.
- **D8 — Dead-code order.** Deletions happen only after Task 9 is green, one file per commit, each verified by `grep` (no remaining references) and a green frontend gate.
- **D9 — Line numbers in the bundle are advisory.** The bundle's file:line citations run one to three lines high against the live tree; implementers re-grep for the cited symbol before editing.

## 5. Quality gates (Quality and Performance Policy applies)

Every task test-first. Frontend: `npm run typecheck && npm test && npm run build` (hand-written code at 100 % lines, branches, functions, statements; generated files are excluded by the documented convention and covered by the pixel and DOM gates), `npm run test:smoke`, `npm run test:visual` at zero tolerance, the DOM oracle, the bundle budget, `app-generated.test.ts` drift, `reference-server.test.ts`, `convert-dc.test.ts` (extended for the three new constructs). Mobile acceptance at 390×800: shading visible on the Map tab; the key does not overlap the `+`/`−` cluster (`document.elementFromPoint` on each button returns the button); the sheet opens full-height, scrolls, renders all five sections; tapping a selected pin twice reaches the detail screen; every sheet target ≥ 44 px (rows `min-height: 46px`, basemap buttons 46 px, close 44×44 around a 16 px glyph). Backend suite unaffected (`poetry run pytest` still green — no backend file changes). Attribution stays visible on every map (`attributionControl: true`; "Tiles © Esri"). Deployment only to QA (`scripts/deploy.sh QA`, `scripts/verify-deploy.sh QA`); production untouched.

## 6. Cross-plan deltas (recorded in the plan's penultimate task)

| Document | Change |
|---|---|
| Identity plan, Task I7 | `permFor()` keys on `patch.screen` only; Browse = `page.browse`; the market column checks `can('market.read')`; `ROUTE_PERMS['browse-market']` removed; `screens.ts` edits apply on top of V3's screen list |
| Identity plan, Task I8 | replaces hand edits of `App.vue` with `convert-dc.mjs --launch` (D2); `gen:app` gains a `gen:app:launch` twin; `app-generated.test.ts` asserts both modes |
| Map-engines plan, Task M5 | file list drops `ListingsMap.vue`; `engine.ts`/`MarketMapView.vue` changes rebase onto V3 (rectangles, `TooltipSpec`, `panInside`, canvas renderer); M7's `?tab=market` comments corrected |
| Census plan | layer-rendering table rewritten for community mosaic shading and the single dashed ring; econ label "Average Practice Payroll"; "choropleth" reserved for Phase C tract tiles; migrations start at `015`; the Esri-vs-CARTO basemap licence becomes one decision record owned by John and the VIN Foundation (today it is an open item in three documents) |
| CLAUDE.md | "Source of truth for the UI" points at the V3 design file; the V2 folder is the regression oracle for the fourteen unchanged screens |

## 7. Risks

1. **C5 community mosaic shading** (rectangles on a shared canvas) is the largest new code and the highest pixel risk; it lands behind unit tests on the engine and `MarketMapView.test.ts` before any baseline is regenerated.
2. **Task 9 mobile** rewrites the mobile Map tab entirely; the byte-identical rule on `mobile-list`/`mobile-detail` is the leak detector.
3. **Three new generator constructs** — supported and unit-tested in `convert-dc.mjs` before regeneration, or Task 6 stops.
4. **Two worktrees in flight** (Wave 2a and Browse V3): disjoint file sets by construction (backend vs frontend); the merge order is fixed by D1; the first Wave 2a frontend task rebases.
5. **Map-engines and Census plans go stale** until §6 lands; their execution is sequenced after this sub-project by John's ruling, so nothing is built against the old shape.
