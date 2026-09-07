# File index

Every repo file the V3 work touches, at `johndean/practice-match@47281cb1e9c7` (`main`).
Line numbers are from that commit. `→` points at the task in `README.md` and the change
in `CHANGE_LOG.md`.

## Generated — never hand-edit

| File | Lines | What happens | Task |
|---|---|---|---|
| `frontend/src/App.vue` | 1330 total; `209-318` desktop listings branch, `221`+`332` `browseToggle` loops, `307` `<ListingsMap>`, `319` `v.md?.isMarket`, `376` `<MarketMapView>`, `379` `basemapTabs`, `1244` mobile `<ListingsMap>`, `1306-1307` imports | regenerated from the V3 reference | 6 |
| `frontend/src/logic.js` | 1233 total; `245` `isMarket`, `1074` `isBrowse`, `1075-1083` `browseToggle`, `162` "Market Data tab" section, `91` `econ` label | regenerated | 6 |
| `frontend/src/app.setup.js` | 27 total; `4-5` map imports | regenerated | 6 |
| `frontend/src/generated/pseudo.css` | 648 B | regenerated | 6 |

## Hand-written — edit these

| File | Lines | What happens | Task |
|---|---|---|---|
| `frontend/package.json` | `18` (`gen:app`) | reference path V2 → V3 | 2 |
| `frontend/src/map/engine.ts` | `3` `MountOptions`, `9-25` `MapEngine`, `20-21` `circle`/`marker` | add `rectangle`, `panInside`, `AreaStyle`, `TooltipSpec`; widen `Handle` | 3 |
| `frontend/src/map/engines/leaflet.ts` | `55` scale control, `73-77` `circle`, `78-86` `marker`, `82` tooltip, `111-118` `destroy` | implement the four additions; one canvas renderer per mount | 3 |
| `frontend/src/map/mosaic.js` | new | `mosaicCells` ported from `MarketMapV3.jsx:57-95` | 3a |
| `frontend/src/map/markers.js` | `47-56` `pricePin`, `58-63` `dot` | add `practicePin` + `practiceCallout` from `MarketMapV3.jsx:120-150` | 4 |
| `frontend/src/components/MarketMapView.vue` | `54` mount opts, `68-92` `drawOverlay`, `94-105` `drawPins`, `100-116` watcher comment, `117-122` watcher | rewritten against `MarketMapV3.jsx` | 4 |
| `frontend/src/styles/global.css` | append | `.rf-callout` / `.rf-tip` rules from `Practice Match V3.dc.html:61-64` | 3b |
| `frontend/src/router/sync.ts` | `6` `BROWSE_TABS`, `11-14` `stateToRoute`, `31` `routeToPatch` | drop the `tab` query; ignore legacy values | 7 |
| `frontend/src/map/testing/leaflet-stub.ts` | 3.7 KB | add `rectangle`, `canvas`, `panInside` | 3 |
| `frontend/tests/screens.ts` | `10-11` helpers, `21-24` browse states, `40-42` mobile states | one Browse screen; new V3 states; `mobile-map` re-baselined | 8, 9 |
| `frontend/src/components/ListingsMap.vue` | 66 | deleted after the mobile port | 9 |
| `frontend/tests/reference-server.mjs` | not in audited tree — read locally | serve the V3 folder | 2 |
| `CLAUDE.md` | `21` | source-of-truth path | 2 |

## Tests that assert the old behaviour

| File | Lines | Why it breaks |
|---|---|---|
| `frontend/src/router/sync.test.ts` | `4, 8, 22, 33, 35, 66, 68` | every case carries `browseMode` |
| `frontend/src/router/useStateRouteSync.test.ts` | `101` | sets `browseMode: 'listings'` |
| `frontend/tests/reference-server.test.ts` | `79-83` V2 title test, `85-96` traversal paths naming the V2 filename | reference file renamed |
| `frontend/src/components/MarketMapView.test.ts` | 28.8 KB | asserts bubbles, drive rings and `scaleControl: true` |
| `frontend/src/map/engines/leaflet.test.ts` | `330` `'LeafletMapEngine — ListingsMap shape'` | still valid — keep; add a MarketMap-shape block beside it |
| `frontend/src/logic.test.ts` | `41` admin tabs, `49-51` seller listings | unaffected — admin/seller are untouched |
| `frontend/tests/app-generated.test.ts` | 1.7 KB | passes only after Task 6 regenerates cleanly |
| `frontend/tests/dom.spec.ts`, `dom.ts`, `dom.walk.test.ts` | 26-30 KB each | DOM parity vs the reference; re-run after Task 6 |

## Untouched, deliberately

`frontend/index.html` (the design-system cascade at lines 9-11 is unchanged) ·
`frontend/src/lib/leaflet.js` (`BASEMAPS`, `LABEL_TILES` — V3 uses the same tiles) ·
`frontend/src/components/ImageSlot.vue` · `frontend/src/dc-logic.js` ·
`frontend/src/styles/tokens.css` · all of `app/`, `migrations/`, `scripts/`, `tests/`
(backend) · `coming-soon/` and its three test specs ·
`docs/design-reference/design_handoff_practice_match_v2/` (kept as the V2 oracle).
