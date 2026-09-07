# Dead-code checklist — Listings tab removal

"Remove, clean code, no dead code, zero risk." Worked through by category. The finding that
matters most: **less is dead than it looks**, because V3's mobile map still uses the
listings map component and its clustering helpers.

Tick each line only after `npm run typecheck && npm test && npm run build` passes.

## Removed for you by the generator (Task 6)

Do not hand-delete these — regenerate and confirm they are gone.

- [ ] `App.vue:209-318` — the whole `v-if="v.isBrowse"` desktop listings layout
- [ ] `App.vue:221`, `App.vue:332` — the two `v.browseToggle` loops
- [ ] `App.vue:307` — the desktop `<ListingsMap>` mount
- [ ] `App.vue:1244` — the mobile `<ListingsMap>` mount, now a `<MarketMapView>` (Task 9)
- [ ] `logic.js` `mobileVals` — `hasPeek` and `peek` (the peek card is gone from V3)
- [ ] `App.vue:379` — the in-panel `basemapTabs` loop (V3 puts basemap switching in the map's control cluster)
- [ ] `logic.js:1074-1083` — `isBrowse` + `browseToggle`
- [ ] `logic.js:245`, `1079`, `1082` — every `browseMode` read
- [ ] `logic.js:162` — the `// ---- Market Data tab ----` section header

Verify with `grep -rn "browseMode\|browseToggle" frontend/src` → no hits outside tests.

## Delete by hand

- [ ] `frontend/src/router/sync.ts:6` — `BROWSE_TABS`
- [ ] `frontend/src/router/sync.ts:11-14` — the `browseMode` branch in `stateToRoute`
- [ ] `frontend/src/router/sync.ts:2` — `browseMode?: string` on `RoutedState`, **only if**
      no `grep -rn browseMode frontend/src` hit remains after Task 6
- [ ] `frontend/tests/screens.ts:11` — the `market` helper (fold into `browse`)
- [ ] `frontend/tests/screens.ts:21-22` — one of `browse-listings` / `browse-market`
- [ ] the orphaned baseline PNG in `frontend/tests/visual.spec.ts-snapshots/` for whichever
      screen name you dropped — a stale oracle image is dead weight that still gets committed
- [ ] `MarketMapView.vue:82-91` — the `layers.competition` bubble pass (not in V3's map)
- [ ] `MarketMapView.vue` — the `layers` / `valueLayer` props, replaced by `activeLayer` /
      `showDrive` / `onArea` / `recenterKey`

## Do NOT delete — looks dead, isn't

| Candidate | Why it stays |
|---|---|
| `frontend/src/components/ListingsMap.vue` | **Now genuinely dead once Task 9 lands** — V3's mobile map is `MarketMapV3` too. Delete it and its import at `app.setup.js:4`, but only after Task 9 is green, and in its own commit so a revert is one `git revert`. |
| `markers.js:3` `pill`, `:17` `clusterIcon`, `:26` `clusterize` | dead with `ListingsMap.vue`. Same rule: after Task 9, own commit. `clusterize` has unit tests in `map/markers.test.ts` — delete those with it, never leave orphan tests. |
| `markers.js:47` `pricePin` | dead once Task 4 lands `practicePin` and Task 9 removes `ListingsMap`. Verify with `grep -rn pricePin frontend/src` before deleting. |
| `markers.js:58` `dot` | V2's bubble builder, replaced by the choropleth. Dead after Task 4 — check `MarketMapView.test.ts` first. |
| `engine.ts` `scaleControl` option, `engines/leaflet.ts:55` | **Keep it.** No component passes `true` after this work, but it is one tested line and re-adding a scale bar is a product decision, not a code one. |
| `engines/leaflet.test.ts:330` `'LeafletMapEngine — ListingsMap shape'` | rename to the market-map shape rather than deleting — the assertions cover the engine's mount contract, which still matters. |
| `ADMIN_TABS`'s `'listings'` member (`sync.ts:7`) | the admin console's Listings tab — a different feature with the same word. |
| `logic.js` seller listings (`110`, `600`, `860`) and `logic.test.ts:41-51` | "My Listings" is the seller dashboard, untouched by this work. |
| `docs/design-reference/design_handoff_practice_match_v2/` | the oracle for the deployed build. Retire it in a later commit, not this one. |

## Zero-risk requirements

- [ ] `/browse?tab=market` and `/browse?tab=listings` still resolve to Browse Practices —
      old links and bookmarks must not 404 or loop
- [ ] no route was deleted: `router/routes.ts` is unchanged (every path already renders the
      one `App` component)
- [ ] `mobile-map` **is expected to change** (Task 9). `mobile-list`, `mobile-detail`,
      `header-1100`, `header-1000`, `detail`, `requests`, `seller-dash`, the four `wizard-*`
      and the four `admin-*` baselines are **byte-identical** before and after
- [ ] `npm run test:visual` green at zero tolerance, baselines regenerated in the same commit
- [ ] `npm run test:smoke` green
- [ ] backend untouched: `git diff --stat app/ migrations/ scripts/ tests/` is empty
