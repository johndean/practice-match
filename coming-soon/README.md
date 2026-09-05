# VIN Foundation — Coming Soon (Vue 3)

A public placeholder page. It announces that something is coming, captures an email for
launch notification, and deliberately reveals nothing about the product.

This is a pixel-for-pixel conversion of the approved design `Coming Soon.dc.html`.

---

## Run it

```bash
npm install
npm run dev        # dev server
npm run build      # static output in dist/
npm run preview    # serve the build locally
```

`npm run build` produces a fully static `dist/` — deploy it to any host or CDN.

## What is in here

```
index.html                    document shell: title, meta description, fonts, tokens
package.json / vite.config.js Vite + @vitejs/plugin-vue
src/
  main.js                     mounts App, registers the hover directive
  App.vue                     the entire page, converted 1:1 from the approved design
  logic.js                    approved logic, ported verbatim (validation, states, motifs)
  dc-logic.js                 small base class so logic.js runs unchanged under Vue
  directives/hover.js         applies the design's inline hover deltas
  styles/tokens.css           VIN Foundation palette + type tokens
  styles/global.css           resets, link colors, keyframes, reduced-motion
public/
  assets/vin-foundation-logo.png
  ds/colors_and_type.css      VIN Design System tokens + ProximaNova @font-face
  ds/fonts/                   ProximaNova Light / Regular / Sbold / Bold
```

## Fidelity

Every color, dimension, weight, animation timing and word of copy is byte-identical to the
approved design. The conversion was mechanical: `<sc-if>` → `v-if`, `<sc-for>` → `v-for`,
`onClick` → `@click`, `style-hover` → the `v-hover` directive. Verified in a live Vue
runtime — all four form states, the redacted-hint interaction, the ring motif and the
staggered entrance all behave as approved.

**Styling is inline, deliberately.** Do not refactor the inline styles into classes as a
first step; the approved values live on the elements they style, and moving them is where
pixel drift comes from.

## Brand compliance (VIN Foundation Brand Style Guide 2026)

- **§04 Colour** — only the six approved values: navy `#003a70`, accent `#339dde`,
  accent background `#deecf7`, text `#494949`, neutral light `#f5f5f5`, white `#ffffff`.
- **§05 Typography** — Merriweather Bold for the headline (Georgia fallback), Proxima Nova
  Regular for body, Semibold for the button, Bold uppercase for eyebrow labels.
- **§03 Logo** — the full-colour horizontal lockup on white, an approved background, with
  clear space preserved and no shadow, outline or container effect.
- Eyebrow labels are solid navy (10.4:1 on white, 8.6:1 on the accent panel). The
  `In development` label uses `#339dde`, which §04 assigns to eyebrow labels.

## Before publishing — two things to wire up

1. **The email form is front-end only.** `logic.js` validates the address and shows the
   confirmed state, but nothing is sent anywhere. Point `submit()` at your list provider
   (Mailchimp, HubSpot, or an internal endpoint) and handle the network-failure case — the
   error slot below the field already exists for it. Add whatever consent record your
   privacy policy requires; the page promises one message only, never shared.
2. **Fonts.** ProximaNova is self-hosted from `public/ds/fonts`. Merriweather loads from
   Google Fonts in `index.html` — self-host it if third-party requests are not permitted.

Also worth adding before launch: a favicon (`public/assets/favicon.png`, referenced in
`index.html` — the VIN Foundation circular emblem is the guide's recommendation for
favicons) and an Open Graph image, since the page will be shared.

## The redacted hint

Under the paragraph, `It's for` is followed by blacked-out navy blocks. Clicking them never
reveals anything — it advances a drier one-line quip each time and stops at the last. The
block widths are arbitrary and are **not** the letter counts of any real sentence, so
nothing can be inferred from them. Copy lives in `TEASES` in `logic.js`.
