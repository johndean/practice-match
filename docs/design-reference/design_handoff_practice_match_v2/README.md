# Practice Match — Vue 3 implementation bundle

VIN Foundation veterinary practice marketplace. This bundle contains the **approved V2
design converted to a running Vue 3 application**, plus the **approved Census Data Source
Specification** that the data layer is built from.

Both artifacts are approved. Nothing in here is a draft.

---

## 1. What is in the bundle

```
vue-app/                              ← the Vue 3 application (this is the deliverable)
  index.html                          document shell: design-system tokens + fonts
  package.json / vite.config.js       Vite + @vitejs/plugin-vue
  src/
    main.js                           mounts App
    App.vue                           the entire approved UI, converted 1:1 from the prototype
    logic.js                          approved application logic, ported verbatim
    dc-logic.js                       small base class so logic.js runs unchanged under Vue
    directives/hover.js               applies the design's inline hover deltas
    components/
      ListingsMap.vue                 Browse Practices map (price pills, clustering)
      MarketMapView.vue               Market Data map (basemaps, drive rings, choropleth)
      ImageSlot.vue                   listing photo frame + approved empty state
    lib/leaflet.js                    Leaflet loader, basemap config, marker renderers
    styles/
      tokens.css                      brand palette + type tokens (from the approved build)
      global.css                      resets, scrollbar, keyframes
  public/
    assets/icons/                     VIN icon set + flagged substitutions
    assets/photos/                    listing photography
    assets/vin-foundation-logo.png    header lockup
    ds/                               VIN Design System tokens + ProximaNova webfonts

Practice Match V2.dc.html             the approved design reference (open in a browser)
Census Data Source Specification.dc.html   approved data-layer spec — build the API from this
AustinMap.jsx / MarketMap.jsx         original map sources the Vue components were ported from
support.js / image-slot.js / doc-page.js   runtime for the reference files only — do not ship
_ds/                                  design system consumed by the reference files
```

## 2. Run it

```bash
cd vue-app
npm install
npm run dev
```

Open the printed URL. To compare against the approved design, serve the bundle root over
HTTP and open `Practice Match V2.dc.html` — the two should be indistinguishable.

```bash
python3 -m http.server 8000      # from the bundle root
```

## 3. How the conversion works — read this before changing anything

The approved prototype was built as one component: an HTML template plus a logic class
that returns a flat object of render values. The conversion preserved both.

- **`logic.js` is the prototype's logic verbatim.** State shape, filter predicates, wizard
  validation, market data derivation, photo sets, admin fixtures — unchanged. `dc-logic.js`
  supplies `setState`, and `App.vue` makes `state` reactive, so `renderVals()` re-evaluates
  exactly as it did in the original render pass.
- **`App.vue`'s template is the prototype's template**, mechanically translated:
  `<sc-if>` → `v-if`, `<sc-for>` → `v-for`, `onClick` → `@click`, `style-hover` → `v-hover`.
  Every style string, dimension, color and word of copy is byte-identical.
- **Styling is inline, deliberately.** Do not refactor inline styles into classes or a
  utility framework as a first step. The approved values live on the elements they style;
  moving them is where pixel drift comes from. If the house style requires CSS modules,
  do it screen by screen and diff each against the reference file.

Consequence: `renderVals()` recomputes on any state change. That is correct for this app's
size (one market of listings). If profiling shows it matters, split it per screen — do not
rewrite it wholesale.

### Typography

One family throughout: **ProximaNova**, self-hosted from `public/ds/fonts`. Both type
tokens resolve to it, so headings and body share the family and separate by weight and size:

```css
--rf-serif:   'ProximaNova', Arial, Helvetica, sans-serif;  /* headings */
--rf-display: 'ProximaNova', Arial, Helvetica, sans-serif;  /* UI + body */
```

Headings are weight 700, uppercase where the design specifies it; UI and buttons are 500;
uppercase eyebrow labels are 800 with positive tracking. There are no third-party font
requests, and no Merriweather or Georgia fallback anywhere in the build.

## 4. What is prototype scaffolding, not product

| Item | Action |
|---|---|
| Dark bar with "Jump to" links and the viewport switch | Controlled by the `prototypeBar` prop, default `false`. Delete the markup before launch. |
| "Prototype — access states" shortcuts on the sign-in card | Remove. Replace with real auth. |
| `startScreen` / `startViewport` props | Remove once routing exists. |
| Demo credentials pre-filled in the sign-in fields | Remove. |
| Fixture data in `logic.js` (`P`, `VETS`, `ECON_K`, admin rows, seller listings, requests) | Replace with API calls. Keep the field names — the UI reads them directly. |
| `support.js`, `image-slot.js`, `doc-page.js` | Reference-file runtime only. Never ship. |

## 5. Data layer

`Census Data Source Specification.dc.html` is the contract: dataset IDs, endpoints, NAICS
codes, variables, geography levels, refresh cadence, joins, derived fields, caching, licence
and attribution obligations, failure handling, and the database schema to implement.

Two obligations that are easy to miss and are legally load-bearing:

1. **Attribution must stay visible.** "Tiles © Esri" on the street basemap, the imagery
   credit on satellite, and the Census citation under Community Context. The OSM Foundation
   tile servers were rejected during design — their usage policy blocks embedded application
   traffic — so do not swap the tile URL back.
2. **Two datasets are blocked, by design.** Pet-ownership estimates (licence unresolved) and
   third-party practice-location data (undocumented provenance) must not reach production
   until the VIN Foundation clears them. The admin console's Data Sources tab shows this
   state; keep that gate.

## 6. Front-end integration checklist

1. **Routing.** `state.screen` (`gate` / `browse` / `detail` / `requests` / `seller` /
   `admin`) maps to routes; `state.mdTab` (`listings` / `market`) and `state.detailId` are
   query params. Add `vue-router` and drive these from the URL.
2. **Auth.** `state.auth` gates the header and every member screen. Wire to the real session;
   keep the approved approval states (pending / declined / approved) — they are designed
   screens, not error placeholders.
3. **Photos.** `ImageSlot` takes a `src`; supply signed URLs from `listing_photo`. The
   placeholder is the approved empty state — keep it for listings without photography.
4. **Icons.** `public/assets/icons/` holds the authentic VIN set plus four flagged
   substitutions: `sub-zoom-out-disc`, `sub-recenter-disc`, `sub-heart-filled`,
   `sub-check-filled`, `sub-info`, `sub-search`. The VIN set ships no minus, target, heart,
   check, info or search glyph. Replace the `sub-*` files when VIN provides real ones — the
   filenames are the only reference, so a drop-in replacement needs no code change.
5. **Fonts.** ProximaNova is self-hosted in `public/ds/fonts` and is the only family used.
6. **Accessibility.** Controls carry `aria-label`s where they are icon-only. The two
   responsive breakpoints (1180px identity text, 1050px nav collapse) are driven by a resize
   listener in `componentDidMount` — keep them; they exist because the header cannot shrink
   below its content.

## 7. Screen map

| Screen | Where | Notes |
|---|---|---|
| Access gate | `v.showGate` | Sign in, request access, pending, declined |
| Browse — Listings | `v.isBrowse`, `mdTab = listings` | Map left, results right (Zillow arrangement), 5 filters + More filters |
| Browse — Market Data | `mdTab = market` | 9 toggleable data layers, drive-time rings, docked practice panel |
| Practice detail | `v.isDetail` | Overview, financial snapshot, practice, property, locked documents, community context |
| Interest request | `v.interestOpen` | Modal → seller accept/decline → unlocks documents |
| My Requests | `v.isRequests` | Awaiting / engaged / declined |
| Seller listings + wizard | `v.isSeller` | Draft / in review / published / paused / withdrawn; 8-step wizard with validation and disclosure controls |
| VIN Foundation Admin | `v.isAdmin` | Users, Listings, Requests, Data Sources |
| Mobile | `v.isMobile` | List / Map toggle, detail sheet |
