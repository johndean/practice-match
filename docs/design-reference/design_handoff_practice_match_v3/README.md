# Handoff: Practice Match V3 — Browse Practices (map + market data)

Audit, plan and instructions for a developer or Claude Code agent working in
`vin-swe/practice-match` (mirror: `johndean/practice-match`), branch `main`,
audited at tree `47281cb1e9c7` on 2026-09-06.

**No code was changed to produce this package.** Nothing here was applied to the repo.

---

## 1. What this is

The site currently ships **Practice Match V2**. This bundle is **Practice Match V3**, the
approved next revision of the Browse Practices experience, plus the exact steps to land it.

Two asks drive the work:

1. **Remove the Listings tab.** V3 has no Listings/Market Data toggle. Browse Practices is
   one screen: the map with market data on the left, the results rail on the right.
2. **Ship the redesigned market data view** — layer select, colour ramps, Compare,
   Layers drawer, legend/insight card, choropleth shading, practice callouts.

The files in this bundle are **design references written in HTML**, not production code.
`Practice Match V3.dc.html` is the authority for every pixel, value and word of copy.

## 2. Fidelity

**High fidelity.** V3 is final: real colours, type, spacing, copy and interaction states.
The gate is `npm run test:visual` at zero tolerance, with baselines regenerated from this
bundle. Reference widths that must match: **1440×940** (primary), plus the existing
**1100** and **1000** header states, and the short-column collapse behaviour built into
the market panel (the legend/insight card yields before the controls column does).

## 3. The one thing to understand before touching anything

`frontend/src/App.vue`, `frontend/src/logic.js` and `frontend/src/app.setup.js` are
**generated**, not hand-written:

```
frontend/package.json:18
"gen:app": "node scripts/convert-dc.mjs ../docs/design-reference/design_handoff_practice_match_v2/'Practice Match V2.dc.html' src/app.setup.js src/App.vue src/generated/pseudo.css"
```

So the surgical change is **not** hand-editing App.vue. It is:

1. land this bundle as the new design reference,
2. repoint the generator and the reference server at it,
3. regenerate,
4. close the small number of gaps the generator cannot cover — the map engine's missing
   primitives, the hand-written `MarketMapView.vue`, the router's `tab` query, the test
   screen list, the new icons.

Hand-editing the generated files would be undone by the next `npm run gen:app` and would
break `frontend/tests/app-generated.test.ts`.

`scripts/convert-dc.mjs` is referenced by `package.json` and unit-tested by
`frontend/tests/convert-dc.test.ts`, but did not appear in the GitHub tree listing for
`frontend/` at the audited commit. **Confirm it is committed before starting** — if it is
untracked locally, commit it first; the whole plan depends on it.

## 4. Execution order

Each task is self-contained with its own acceptance criteria. Do them in order; the visual
gate only means anything after Task 6.

| # | Task | Files | Risk |
|---|---|---|---|
| 1 | Land the V3 reference bundle | `docs/design-reference/design_handoff_practice_match_v3/**` (new) | none |
| 2 | Repoint generator, reference server, CLAUDE.md | `frontend/package.json`, `frontend/tests/reference-server.mjs`, `frontend/tests/reference-server.test.ts`, `CLAUDE.md` | low |
| 3 | Extend the map engine (rectangle, tooltip options, panInside, scale position) | `frontend/src/map/engine.ts`, `frontend/src/map/engines/leaflet.ts` + tests | **highest — the only real new code** |
| 4 | Port `MarketMapView.vue` to the V3 map | `frontend/src/components/MarketMapView.vue` + test | high |
| 5 | Copy the seven new icons | `frontend/public/assets/icons/` | none |
| 6 | Regenerate the app from V3 | `frontend/src/{App.vue,logic.js,app.setup.js,generated/pseudo.css}` | medium |
| 7 | Router: `/browse` loses its `tab` query | `frontend/src/router/sync.ts` + tests | low |
| 8 | Test screens + baselines | `frontend/tests/screens.ts`, `visual.spec.ts-snapshots/**` | low |
| 9 | Mobile: same map, market data in a sheet | `frontend/src/components/MarketMapView.vue`, `ListingsMap.vue`, generated | high |
| 10 | Dead code sweep | see `DEAD_CODE_CHECKLIST.md` | low |

`CHANGE_LOG.md` describes each design change with its reference line numbers (C1-C14).
`FILE_INDEX.md` lists every repo file the work touches, and why.

---

## Task 1 — Land the reference bundle

Copy this whole folder to `docs/design-reference/design_handoff_practice_match_v3/`.

Then mirror what the V2 folder carries and this one deliberately does not:

- `_ds/vin-design-system-…/` — copy from
  `docs/design-reference/design_handoff_practice_match_v2/_ds/` unchanged.
- `vendor/leaflet.{js,css}`, `vendor/react*.production.min.js` — copy from the V2 folder
  unchanged. The reference loads Leaflet and React from `vendor/`; without them the
  reference server serves a blank map.
- `doc-page.js` — only needed by `Census Data Source Specification.dc.html`; copy it too.

**Do not delete the V2 folder.** It is the oracle for the currently-deployed build and the
only way to prove a regression came from this change. Retire it in a later commit.

**Acceptance:** `python3 -m http.server` from the new folder, open
`Practice Match V3.dc.html`, and the Browse screen renders with the grey Esri basemap,
choropleth shading, nine result cards and no console errors.

---

## Task 2 — Repoint the generator and the reference server

**`frontend/package.json:18`** — change the reference path only:

```diff
- "gen:app": "node scripts/convert-dc.mjs ../docs/design-reference/design_handoff_practice_match_v2/'Practice Match V2.dc.html' src/app.setup.js src/App.vue src/generated/pseudo.css"
+ "gen:app": "node scripts/convert-dc.mjs ../docs/design-reference/design_handoff_practice_match_v3/'Practice Match V3.dc.html' src/app.setup.js src/App.vue src/generated/pseudo.css"
```

**`frontend/tests/reference-server.mjs`** (not in the audited tree listing — read it
locally) serves the reference from disk at `/`. Point its root at the V3 folder and its
served filename at `Practice Match V3.dc.html`. Keep the `/coming-soon/` mount and both
traversal guards exactly as they are.

**`frontend/tests/reference-server.test.ts:79-83`** asserts the V2 file is served:

```ts
it('keeps serving the Practice Match V2 marketplace design at "/"', async () => {
  const res = await fetch(`${base}/`);
  expect(res.status).toBe(200);
  expect(await res.text()).toContain('Practice Match — internal working title');
});
```

Rename the test to V3 and keep the assertion string — V3 still carries
`Practice Match — internal working title`. The two traversal tests
(`reference-server.test.ts:85-96`) name `Practice Match V2.dc.html` in their attack
paths; update those literals to the V3 filename so they still probe a real file.

**`CLAUDE.md:21`** — the source-of-truth line:

```diff
- `docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html` is the approved design.
+ `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` is the approved design.
```

Leave every rule beneath it intact — they all still apply.

**Acceptance:** `npm test` green; `node tests/reference-server.mjs 4174` serves V3 at
`/`; `npm run gen:app` runs without error (output correctness is Task 6).

---

## Task 3 — Extend the map engine

This is the only substantial new code, and the only place the V3 design needs a capability
the shipped engine does not have. Four gaps, all read straight off `MarketMapV3.jsx`:

### 3a. Rectangles with a canvas renderer — the choropleth

`MarketMapV3.jsx:248-269` draws the shading as a mosaic of rectangles on a shared canvas
renderer, one per cell, coloured by the active layer's class colour:

```js
const canvas = L.canvas({ padding: 0.3 });
mosaicCells(communities, bbox, 0.0055).forEach(({ site, bounds }) => {
  const v = site.values[activeLayer];
  if (v == null) return;
  L.rectangle(bounds, { renderer: canvas, stroke: false, fillColor: v.color, fillOpacity: 0.5, interactive: true })
```

`frontend/src/map/engine.ts:9-25` has `circle` and `marker` and nothing else. Add:

```ts
export interface AreaStyle { fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }
export interface TooltipSpec { html: string; sticky?: boolean; permanent?: boolean; direction?: 'top' | 'bottom'; offset?: [number, number]; className?: string; opacity?: number }
// on MapEngine:
rectangle(bounds: [LatLng, LatLng], style: AreaStyle, group: string, tooltip?: TooltipSpec): Handle;
```

Implement in `frontend/src/map/engines/leaflet.ts` beside `circle()` (line 73), and hold
**one** `L.canvas({ padding: 0.3 })` renderer per mount — created in `mount()`, cleared in
`destroy()` alongside `groups`/`zoomCtl`/`scaleCtl` (line 111-118). A renderer per
rectangle is what makes a mosaic this dense unusable.

The cell geometry (`mosaicCells`, `MarketMapV3.jsx:57-95`, step `0.0055`, bbox padded
`0.13` lat / `0.15` lng, `MarketMapV3.jsx:241-246`) is presentation logic, not engine
logic. Port it verbatim into a helper next to `markers.js` — `frontend/src/map/mosaic.js`
— and unit-test it: same community list in, same cell count and bounds out.

### 3b. Tooltip options

`frontend/src/map/engines/leaflet.ts:82` hard-codes the only tooltip shape it supports:

```ts
if (o.tooltip) m.bindTooltip(o.tooltip, { direction: 'top', offset: [0, -6] });
```

V3 needs two more shapes. The choropleth cell tooltip
(`MarketMapV3.jsx:259-267`): `{ sticky: true, className: 'rf-tip' }`. The practice
callout (`MarketMapV3.jsx:291-297`):

```js
.bindTooltip(practiceCallout(p), { direction: 'top', offset: [0, selected ? -22 : -34], className: 'rf-callout', permanent: selected, opacity: 1 })
```

Widen `MarkerOptions.tooltip` to `string | TooltipSpec` and pass the options through.
Keep the current defaults for a bare string so nothing else moves.

`.rf-callout` and `.rf-tip` are styled in the reference's helmet
(`Practice Match V3.dc.html:61-64`) — including the `::before` arrow colour override.
Those four rules must reach the app; `frontend/src/styles/global.css` is the right home
(they target Leaflet's own tooltip elements, which live outside component scope).

### 3c. `panInside`

`MarketMapV3.jsx:303-306`: selecting a practice opens its callout and pans just enough to
bring the callout into view.

```js
mk.openTooltip();
if (map.panInside) map.panInside([p.lat, p.lng], { padding: [48, 110], animate: true });
```

Add `panInside(pos: LatLng, padding: [number, number]): void` to the engine interface and
implement it with the same `destroyed` guard every other method carries. The 110px vertical
padding is deliberate: ~70px callout plus the 34px pin.

Also needed: a handle that can open its own tooltip, or an `openTooltip` option on
`MarkerOptions` — the marker's tooltip must open programmatically on selection, not only
on hover. Prefer widening `Handle` to `{ remove(): void; openTooltip?(): void }`.

### 3d. The scale control

`MarketMapView.vue:54` mounts with `scaleControl: true`, and
`engines/leaflet.ts:55` pins it to `position: 'bottomright'`. **V3's market map mounts no
scale control at all** (`MarketMapV3.jsx:185`: `{ center, zoom, zoomControl: false,
attributionControl: true }`) — the app owns the bottom-right corner for the Layers button.
Pass `scaleControl: false` from the component (Task 4) and leave the engine's option in
place for `ListingsMap`. Do **not** delete the option.

Attribution stays on: `attributionControl: true` is legally load-bearing (CLAUDE.md).

**Acceptance:** new unit tests in `frontend/src/map/engines/leaflet.test.ts` (the stub in
`frontend/src/map/testing/leaflet-stub.ts` needs `rectangle`, `canvas` and `panInside`
added) covering: one canvas renderer per mount; rectangle added to the named group and
removed by its handle; tooltip options forwarded verbatim; `panInside` no-ops after
`destroy()`. `npm run typecheck && npm test` green.

---

## Task 4 — Port `MarketMapView.vue`

`frontend/src/components/MarketMapView.vue` (123 lines) is the hand-written Vue port of
V2's `MarketMap.jsx`. Rewrite its two draw functions against `MarketMapV3.jsx`,
keeping the component's existing shape: the single ordered watcher, the mount/unmount
lifecycle, and the comment at lines 100-116 explaining why the two draws share one watcher.
That reasoning still holds and the merged watcher is still required.

What changes:

| Now (V2) | V3 |
|---|---|
| `drawOverlay` draws community **bubbles**: `dot(16 + v.t * 30, v.color)` markers (lines 68-92) | choropleth **rectangles** via the new `rectangle()` + `mosaic.js` |
| a second bubble pass for `layers.competition` (lines 82-91) | not in V3's map — competition is a legend/overlay concern, not a bubble |
| drive rings: two filled `circle`s, `#339dde`/`#003a70` at 16000m/8000m (lines 71-73) | one **dashed unfilled** ring: `radius: 16000, color: '#003a70', weight: 1.5, dashArray: '4 4', fill: false` (`MarketMapV3.jsx:230-235`) |
| `drawPins` uses `pricePin`, size `[72, 26]`, anchor `[36, 13]` (lines 94-105) | `practicePin`, size `[78, 34]`, anchor `[39, 34]`, plus the `rf-callout` tooltip and `panInside` on select (`MarketMapV3.jsx:278-307`) |
| `scaleControl: true` (line 54) | `scaleControl: false` |
| props: `layers`, `valueLayer` | V3's map takes `activeLayer`, `showDrive`, `onArea`, `recenterKey` (`MarketMapV3.jsx:155-170`) |

Port `practicePin` and `practiceCallout` (`MarketMapV3.jsx:120-150`) into
`frontend/src/map/markers.js` beside `pricePin`, verbatim, inline styles included — the
existing file's own comment explains why those styles stay inline.

The prop names the generated `App.vue` will pass come from the reference's own
`<x-import>` tag (`Practice Match V3.dc.html:324`). Read that line and match it exactly;
the generator maps kebab-case attributes to props.

**Acceptance:** `frontend/src/components/MarketMapView.test.ts` updated and green;
choropleth cells appear for every enabled layer, hovering a cell shows the `rf-tip` with
name/metric/value/source, selecting a pin opens a persistent callout and the map pans so
the callout is fully visible at 1440×940.

---

## Task 5 — Icons

Seven glyphs are referenced by V3 and absent from the V2 asset set. Copy from this bundle's
`assets/icons/` to `frontend/public/assets/icons/`:

`sub-chevron.svg`, `sub-close-thin.svg`, `sub-plus-thin.svg`, `sub-bar-chart.svg`,
`sub-reset-view.svg`, `sub-legend-list.svg`, `sub-layers-stack.svg`

All seven are `sub-*` substitutions in the sense CLAUDE.md and the V2 README use: the VIN
set ships no chevron, thin close, thin plus, bar-chart, reset-view, legend-list or
layers-stack glyph. `sub-plus-thin` and `sub-layers-stack` were drawn for V3 as 1.8px
stroke, `#5b6672`, 24×24 viewBox, matching the rest. Filenames are the contract — a real
VIN glyph drops in with no code change.

No icon was removed between V2 and V3; nothing to delete.

**Acceptance:** no 404 for `/assets/icons/*` in the browser network log on any screen.

---

## Task 6 — Regenerate

```bash
cd frontend && npm run gen:app && npm run typecheck && npm test
```

This rewrites `src/App.vue`, `src/app.setup.js`, `src/logic.js` and
`src/generated/pseudo.css`. Review the diff, do not edit the output. Expect:

- the desktop listings branch to disappear (`App.vue:209-318` today: `v-if="v.isBrowse"`,
  the `browseToggle` loop at 221 and 332, the `<ListingsMap>` mount at 307);
- `v.md?.isMarket` (`App.vue:319`) to become unconditional for `screen === 'browse'`
  (`Practice Match V3.dc.html:1770`: `isMarket: s.screen === "browse"`);
- the `basemapTabs` loop (`App.vue:379`) to move into the map's own control cluster;
- `logic.js` to lose `browseToggle` (1075-1083) and the `browseMode` reads at 245, 1074,
  1079, 1082;
- the mobile `<ListingsMap>` mount (`App.vue:1244`) to become a **second `<MarketMapView>`**
  — V3's mobile map is now `MarketMapV3.jsx` too (see Task 9).

If the generator chokes on a V3 construct, fix the generator, not the reference. Three
constructs are new in V3 and worth checking first: `ref="{{ … }}"` on an element
(`Practice Match V3.dc.html:395`, the compare menu's scroll-into-view ref),
`aria-selected="{{ o.selected }}"` on a `<button role="option">`, and `<sc-if>` used
twice as a sibling pair to switch an `<img src>` between two static files
(lines 377-382). Vue equivalents: `:ref`, `:aria-selected`, two `v-if` blocks.

**Acceptance:** `npm run typecheck && npm test && npm run build` green;
`frontend/tests/app-generated.test.ts` green (it asserts the generated files match the
reference — that is the test that catches a hand edit).

---

## Task 7 — Router

With no Listings tab, `/browse?tab=market` and `/browse?tab=listings` are meaningless.
Zero-risk removal means **the old URLs must keep working**, silently landing on Browse.

`frontend/src/router/sync.ts:6`:

```diff
- const BROWSE_TABS = ['listings', 'market'] as const;
```

`sync.ts:11-14` — `stateToRoute`:

```diff
- case 'browse': {
-   const mode = s.browseMode || 'listings';
-   return { path: '/browse', query: mode === 'market' ? { tab: 'market' } : {} };
- }
+ case 'browse': return { path: '/browse', query: {} };
```

`sync.ts:31` — `routeToPatch`:

```diff
- if (to.path === '/browse') return { screen: 'browse', browseMode: pick(to.query.tab, BROWSE_TABS, 'listings') };
+ // Any legacy ?tab= is ignored: Browse Practices is one screen in V3.
+ if (to.path === '/browse') return { screen: 'browse' };
```

Keep `browseMode` out of `RoutedState` (line 2) only if `logic.js` no longer reads it
after Task 6 — check, don't assume. `ADMIN_TABS` and its `'listings'` member are the
admin console's tabs and are **unrelated**; leave them alone.

Tests to update: `frontend/src/router/sync.test.ts` (lines 4, 8, 22, 33, 35, 66, 68 all
assert `browseMode`), and `frontend/src/router/useStateRouteSync.test.ts:101`.
Add one new case: `/browse?tab=market` → `{ screen: 'browse' }`, no redirect loop.

**Acceptance:** `/browse`, `/browse?tab=market` and `/browse?tab=listings` all render
Browse Practices; the URL settles without a loop; `npm test` green.

---

## Task 8 — Test screens and baselines

`frontend/tests/screens.ts` — the 25 approved states. Changes:

- line 11: `const market = …` clicks `'Market Data'`. That tab is gone; `market` becomes
  `browse`.
- line 21-24: `browse-listings` and `browse-market` are now the same screen. Keep **one**,
  named `browse`. `browse-market-layers-closed` clicks `'Data Layers'` — V3's button
  reads **`Layers`** with a count pill (`Practice Match V3.dc.html:519-524`); update the
  label. `browse-market-panel` (click `Cedar Park`) still applies.
- Add the states V3 introduces and V2 had no equivalent for: `browse-compare-open`
  (Compare → pick a second metric), `browse-layer-menu` (the Market data dropdown open),
  `browse-legend-collapsed` (legend/insight dismissed).
- `mobile-list`, `mobile-map`, `mobile-detail`, `header-1100`, `header-1000` are
  unchanged.

Then regenerate the oracle images from the new reference and diff:

```bash
cd frontend && npm run test:visual:baselines && npm run test:visual
```

Commit the PNGs. **Do not relax the tolerance** in `tests/playwright.config.ts`; a
failure here is the change being wrong, not the gate being strict.

**Acceptance:** `npm run test:smoke && npm run test:visual` green at zero tolerance.

---

## Task 9 — Mobile: the same map, market data in a sheet

V3's mobile Map tab was still V2's listings map — price pills and clustering, no layers, no
legend, no compare. It is now the **same `MarketMapV3`** the desktop uses, so choropleth
shading, practice callouts and the drive-time ring all match.

What the phone gets (reference `Practice Match V3.dc.html:1357-1490`):

- **The map**, mounted with the same props as desktop **minus `onBasemap`** — that prop is
  now what gates the map's own `Map | Satellite` tabs (`MarketMapV3.jsx:360`), because the
  132px control cluster at `right: 12px; top: 16px` and a full-width key cannot share a
  388px-wide map. Mobile omits it and owns basemap switching in the sheet; the `+` / `−`
  buttons stay.
- **A compact key** pinned at `left/right: 12px; bottom: 64px`: active layer title (11.5px),
  the ramp, and class labels at 8.5px.
- **One navy button** at `bottom: 12px`, 44px tall: layers-stack glyph, active layer name,
  dataset count pill.
- **A full-height sheet** (`position: absolute; inset: 0; z-index: 700`) with five sections
  in order — Shading (the seven layer options as 44px rows), ramp + source/updated lines,
  Compare against (options + the class-coloured bars), Datasets (enable/disable), What this
  means / Why it matters, Basemap. Header carries the thin `×`; footer a full-width
  `Show map` button.
- **No peek card.** The map's callout carries the practice; tapping an already-selected pin
  opens the detail screen (`mobileVals.selectMarker`).
- **List stays a tab.** The List / Map toggle and the results list are unchanged.

In the app this means `App.vue:1244`'s `<ListingsMap>` becomes a `<MarketMapView>`, and
`MarketMapView.vue` must work at 390×~520 as well as 1440 — it takes no fixed widths today,
so this is a props change, not a layout rewrite. Every tap target in the sheet is ≥44px:
option and dataset rows `min-height: 46px`, basemap buttons 46px, and the close button a
44×44 hit area with a 16px glyph (negative margins keep the header's optical alignment).

**Acceptance:** at the prototype's mobile frame (390×800) the Map tab shows choropleth
shading; the key does not overlap the `+` / `−` cluster (`document.elementFromPoint` on
each button returns the button); the sheet opens full-height and scrolls; every one of the
five sections renders; tapping a pin twice reaches the detail screen.

---

## Task 10 — Dead code

See `DEAD_CODE_CHECKLIST.md`. The short version: less is dead than it looks. The mobile
map still needs `ListingsMap.vue` and the clustering helpers, so the only genuinely dead
code is the desktop listings branch — which the generator removes for you in Task 6 — plus
the router's tab handling and the two duplicated test screens.

---

## 5. Answering the API question

You asked whether the six market datasets exist in the real API. **They do not.** At the
audited commit the backend serves exactly two API surfaces:

```
app/api/health.py      GET /api/healthz
app/api/interest.py    the coming-soon interest signup
```

`migrations/` holds `001_init.sql` and `002_interest_signup.sql`. There is no
`dataset_registry`, no community geometry, no Census ingest. Every number in the V3 market
view comes from fixtures in the generated `logic.js` — `P` (line 5), `MARKETS` (28),
`VETS`, `ECON_K`, and the derived values in `marketVals()`.

So V3 ships against fixtures, exactly as V2 does, and none of this plan depends on the API.
The contract for the real thing is already written and approved:
`Census Data Source Specification.dc.html` (in this bundle) — dataset IDs, NAICS codes,
variables, geography levels, refresh cadence, joins, derived fields, caching, licence and
attribution obligations, failure handling and the schema. That is Sub-project 3, and it is
out of scope here.

One consequence worth flagging now: V3's Layers drawer lets a user disable a dataset, and
the admin Data Sources tab still gates pet-ownership estimates on an unresolved licence
(CLAUDE.md, "Legally load-bearing"). When the API lands, "disabled by the user" and
"blocked by licence" must stay distinguishable — V3's fixtures conflate them.

## 6. Map library

You asked how far fidelity goes on the map, and answered: match the prototype exactly, swap
the library if needed. **No swap is needed.** V3's map is Leaflet 1.9.4 with the same Esri
grey basemap and label layer the app already loads (`frontend/src/lib/leaflet.js`,
`BASEMAPS` + `LABEL_TILES`). Everything V3 adds — rectangles, canvas renderer, tooltip
classes, `panInside` — is stock Leaflet the engine simply does not expose yet. Task 3 is
additive.

The open licence question in CLAUDE.md (Esri tiles in the design vs CARTO in the Census
spec) is untouched by this work and still needs a VIN Foundation decision.

## 7. Risk register

| Risk | Why | Mitigation |
|---|---|---|
| `convert-dc.mjs` not committed | absent from the audited tree | verify before Task 1; commit if untracked |
| Generator can't parse V3's new constructs | `:ref`, `aria-selected`, paired `sc-if` on `<img>` | Task 6 names all three; fix the generator, never the reference |
| Choropleth performance | mosaic at step 0.0055 is thousands of rectangles | one shared canvas renderer (Task 3a); profile at 1440×940 before shipping |
| Baseline churn hides a regression | every Browse baseline changes at once | regenerate baselines and app screenshots in the **same** commit, and eyeball the Browse pair by hand |
| Visual gate fails on the mobile screens | they should not change at all | if a mobile baseline moves, the port leaked — stop and diff |
| Vestigial `isBrowse: false` | `Practice Match V3.dc.html:2831` — a render value nothing reads | harmless; remove it from the reference in a follow-up if you want the generated `logic.js` truly clean |

## 8. What is prototype scaffolding, not product

Unchanged from V2 and still true in V3: the `prototypeBar` jump bar, the
"Prototype — access states" shortcuts, pre-filled demo credentials, `startScreen` /
`startViewport`, and the fixture data in `logic.js`. CLAUDE.md's launch-removal list
covers all of it. This plan removes none of it — that is Sub-project 2.
