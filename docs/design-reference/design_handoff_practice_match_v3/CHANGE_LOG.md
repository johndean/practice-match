# Change log — V2 shipped → V3 approved

One entry per design change, with the reference lines that define it and the repo files it
lands in (see `FILE_INDEX.md`). Line numbers prefixed `V3:` are in
`Practice Match V3.dc.html`; `MMV3:` is `MarketMapV3.jsx`.

**The reference is the authority.** V3 differs from V2 by 568 added and 229 removed lines.
The entries below are the substantive changes; anything not named here still ships as the
reference renders it, and the visual gate is what proves it.

---

## C1 — Listings tab removed; Browse Practices is one screen

**V2:** `browseToggle` rendered a two-tab switch — `Listings` / `Market Data` — and
`state.browseMode` selected between two full desktop layouts.

```js
// logic.js:1074-1083 (today)
isBrowse: s.screen === "browse" && (s.browseMode || "listings") === "listings",
browseToggle: [
  { key: "listings", label: "Listings" },
  { key: "market", label: "Market Data" }
]
```

**V3:** no toggle, no `browseMode`. Browse is the map with market data plus the results
rail (V3:272 `md.isMarket`, V3:1770 `isMarket: s.screen === "browse"`). The desktop
listings branch and both toggle loops are gone from the template.

**Lands in:** `App.vue` (209-318, 221, 332 removed), `logic.js` (245, 1074-1083),
`router/sync.ts`, `tests/screens.ts`. → Tasks 6, 7, 8.

**Acceptance:** no element anywhere reads `browseMode`; `/browse?tab=market` renders
Browse without redirecting; one Browse baseline, not two.

---

## C2 — Market data panel: three levels in a scrolling column

**V3:328-433.** A fixed-width 300px column at `left: 16px; top: 16px; bottom: 72px`,
`overflow-y: auto` (class `rf-scroll`), holding, in order:

1. **Market data card** (V3:331-370) — header `Market data` at 15px/500 with a collapse
   chevron; the layer `<button role="listbox">` trigger (V3:344, 40px tall, 1px
   `var(--border-subtle)`, 6px radius, 14px type); the class ramp with its real bucket
   labels (V3:351-364); source and updated lines at 10.5px `#767676` (V3:366-367).
2. **Compare** (V3:376-430) — see C4.
3. The layer menu itself is **not** in the column: V3:435-449 positions it absolutely
   against the map (`left: 16px; top: 118px; width: 300px; z-index: 620`) with
   `max-height: calc(100% - 134px)`, because an absolute child cannot escape a scrolling
   ancestor's padding box.

Header copy is `Market data` — no info icon. **V2 had neither this card nor a layer
select**: V2 switched layers inside the Data Layers drawer and showed basemap tabs in the
panel (`App.vue:379` `basemapTabs`).

**Lands in:** generated `App.vue`/`logic.js`. → Task 6.

---

## C3 — Layer menu rows carry the layer's own ramp

**V3:437-446** — each option is a button with a 20×20 chip built from that layer's four
ramp stops stacked vertically, the label, and a check on the active row
(`sub-check-filled.svg`, 11×11). Seven options: `No shading — practices only` plus the
six datasets.

**Lands in:** generated. New icon: `sub-chevron.svg`. → Tasks 5, 6.

---

## C4 — Compare against

**V3:376-430.** Collapsed by default: one row reading `Compare` with a bare stroke glyph —
thin `+` when closed (`sub-plus-thin.svg`), thin `×` when open (`sub-close-thin.svg`),
14×14, `opacity: .7`, **no disc, no fill** — and a trailing hint (`(optional)` →
`1 metric` → `close`).

Open, it shows an uppercase `COMPARE AGAINST` eyebrow (9.5px/800, `.11em` tracking,
`var(--vf-accent)`), then the **same** trigger + listbox control as the layer select
(V3:390-407, `md.layerSelectStyle` shared), then a six-row bar chart.

Two details that are load-bearing:

- **Each bar takes the class colour that community is shaded with on the map**, per layer's
  own scale — not a single hue per series. The keys beside the labels are therefore the
  full ramp as a `linear-gradient`, not one chip (V3:423-424).
- The compare menu is **in-flow** below its trigger, not absolute, because it lives inside
  `rf-scroll`; it caps at `max-height: 232px` and a `ref` callback scrolls the host so
  the whole menu is visible on open (V3:395).
- Selecting the metric already shading the map resets the comparison — no self-compare.

**Lands in:** generated `App.vue` (the `:ref` needs generator support) / `logic.js`.
→ Task 6.

---

## C5 — Choropleth replaces community bubbles

**MMV3:222-271.** V2 drew one sized dot per community (`dot(16 + v.t * 30, v.color)`).
V3 shades contiguous area: a mosaic of `L.rectangle` cells on a single
`L.canvas({ padding: 0.3 })` renderer, `stroke: false`, `fillOpacity: 0.5`,
`fillColor` = the community's class colour; step `0.0055`, bbox padded 0.13 lat /
0.15 lng. Hover shows the `rf-tip` card: name, metric name, value, source note.

**Lands in:** `map/engine.ts`, `map/engines/leaflet.ts`, new `map/mosaic.js`,
`MarketMapView.vue`. → Tasks 3a, 4. **Highest-risk change in the set.**

---

## C6 — Practice pins and callouts

**MMV3:273-310.** Pin geometry changes (`[72,26]`/`[36,13]` → `[78,34]`/`[39,34]`,
`practicePin` replacing `pricePin`) and selection now opens a **persistent** callout —
photo, name, price, meta — with `className: 'rf-callout'`, `permanent: selected`,
`offset: [0, selected ? -22 : -34]`, followed by
`map.panInside([lat, lng], { padding: [48, 110] })` so an edge marker's callout is never
off-screen.

**Lands in:** `map/markers.js`, engine tooltip options + `panInside`,
`MarketMapView.vue`, `styles/global.css`. → Tasks 3b, 3c, 4.

---

## C7 — Drive-time ring

**MMV3:230-235.** V2's two filled rings (`#003a70` at 8km, `#339dde` at 16km,
`fillOpacity` .2/.16) become one dashed outline: `radius: 16000, color: '#003a70',
weight: 1.5, dashArray: '4 4', fill: false, interactive: false`.

**Lands in:** `MarketMapView.vue`. → Task 4.

---

## C8 — Legend and interpretation merged into one card

**V3:451-478.** V2 kept the legend and the interpretation text as separate stacked cards,
which collided in a short column — flex items default to `min-height: auto`, so
`flex: 0 1 auto` could not shrink them. V3 is one card at
`left: 16px; bottom: 22px; width: 360px`: a `sub-bar-chart` badge, the heading
`What this means` (17px/800), the interpretation, then `Why it matters` on
`var(--vf-neutral)` beneath a divider. Each section dismissible; the card scrolls rather
than overflowing. Its close is the bare thin `×` (`sub-close-thin.svg`, 15×15).

**Lands in:** generated; `legendBoxStyle` at V3:2016 carries the short-column rule.
→ Task 6. New icons: `sub-bar-chart.svg`, `sub-legend-list.svg`.

---

## C9 — Layers drawer

**V3:480-525.** Bottom-right: a navy `Layers` button (40px, 13.5px/500 white type) with a
stacked-sheets glyph (`sub-layers-stack.svg`, 16×16, white via
`filter: brightness(0) invert(1)`), a count pill (`6 of 6`) on
`rgba(255,255,255,.22)`, and a caret that flips. Open, a 296px panel sits above it
(`bottom: 48px`) headed `Market data layers` / `select any or all`, one row per dataset
with its ramp chip, title, description and a checkbox; footer copy explains that enabled
layers appear in the Market data dropdown.

The map's own scale control moved out of this corner — see C11.

**Lands in:** generated. → Tasks 5, 6.

---

## C10 — Palettes: one hue per layer, three sets

**V3:1489-1514.** Three named palettes selectable via the `layerPalette` prop
(`distinct` default, `cool`, `colorblind`). The `distinct` set, verbatim:

```js
income:      ["#e6f2e8", "#c2e0cd", "#a8d5b5", "#4c9a6a", "#1b6b3a"]   /* green, 5 classes */
pets:        ["#fdf0dc", "#f6c886", "#e89331", "#b3630f"]              /* orange  */
competition: ["#e9e2f6", "#c3b0e6", "#9a7ed4", "#7856be"]              /* purple  */
growth:      ["#efe6dd", "#d2b696", "#a3764a", "#5f3a1e"]              /* brown   */
households:  ["#e4eff8", "#a9cfe9", "#5aa2d0", "#1f6fa8"]              /* blue    */
econ:        ["#fce8ef", "#f2b8cd", "#dd7ba1", "#b0446e"]              /* rose    */
```

Growth is **brown** deliberately: as teal it read as a second green beside income, and the
two are the only layers that can shade the map. `BRAND_RAMP`
(`["#deecf7", "#9dc9e9", "#339dde", "#003a70"]`) remains the fallback.

Also renamed: `econ` from `Payroll per Veterinary Establishment (CBP)` /
`Revenue per establishment` to **`Average Practice Payroll`** /
`Avg. payroll per practice` (V3:1517-1530 `VALUE_LAYERS`), with the help text making
clear it is a proxy for practice size, not revenue.

**Lands in:** generated `logic.js`. → Task 6.

---

## C11 — Map controls and the scale bar

**MMV3:185, 340-360.** The market map mounts `{ zoomControl: false, attributionControl: true }`
and **no scale control** — the app's own controls sit at `right: 12px; top: 16px`
(zoom in / out / recenter / legend, `sub-reset-view.svg`, `sub-legend-list.svg`).
`MarketMapView.vue:54` currently passes `scaleControl: true`, which Leaflet pins bottom
-right (`engines/leaflet.ts:55`) — directly under V3's Layers button.

Attribution stays visible. That is not a style choice (CLAUDE.md, "Legally load-bearing").

**Lands in:** `MarketMapView.vue`. → Task 4 / 3d.

---

## C12 — Results rail

**V3:527-725.** Nine cards beside the map. The card meta row wraps
(`flex-wrap: wrap`, per-item spacing instead of a left-border divider — a border breaks
once a row wraps), so no row overflows its 230px column at 1440. The opportunity tiles
(V3:688, `oppTiles`) read `Affluence`, `Population Growth`, `Sector Payroll`.

**Lands in:** generated. → Task 6.

**Acceptance:** at 1440×940 no card row overflows and the page has no horizontal scroll.

---

## C13 — Mobile map is the desktop map

**V3:1357-1490.** The mobile Map tab was still V2's listings map (`AustinMap.jsx`: price
pills, clustering, no market data). It is now `MarketMapV3` — the same component, the same
choropleth, the same callouts.

Mobile-specific arrangement: a compact key above the button strip (`bottom: 64px`), one
navy **Market data** button (`bottom: 12px`, 44px, layer name + count pill), and a
full-height sheet carrying Shading / ramp + sources / Compare against / Datasets / What this
means / Basemap. No peek card — tapping an already-selected pin opens the detail screen.
List stays a tab.

**`MarketMapV3.jsx:360, 382` changed:** the `Map | Satellite` tabs now render only when an
`onBasemap` prop is passed. Desktop passes it; mobile does not, because the sheet owns
basemap switching and the 132px cluster would otherwise sit under the key on a 388px map.
Desktop is unaffected.

**Lands in:** `App.vue:1244` (`<ListingsMap>` → `<MarketMapView>`),
`MarketMapView.vue` (must render at 390px wide), generated `logic.js`
(`mobileVals`: `sheetOpen`, `openSheet`, `closeSheet`, `layerLabel`, `basemaps`,
`rowStyle`, `datasetRowStyle`; `hasPeek`/`peek` removed). → Task 9.

**Tap targets:** every row in the sheet is `min-height: 46px`, the basemap buttons are
46px, and the close button is a 44×44 hit area around a 16px glyph. Nothing in the sheet is
under 44px.

**The three mobile baselines will all move.** `mobile-map` changes completely;
`mobile-list` and `mobile-detail` should not — check them by hand.

---

## C14 — What did not change

`detail`, `requests`, `seller-dash`, the four `wizard-*` and the four `admin-*` screens
are untouched by V3. Their baselines must be byte-identical. If one moves, the port leaked
into shared code — stop and diff.
