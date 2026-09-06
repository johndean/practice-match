import { test, expect, type Page } from '@playwright/test';
import { SCREENS } from './screens';
import { booted, prepare, settle } from './harness';

// ---------------------------------------------------------------------------------------
// End-to-end shading guard (review L1, controller ruling 2026-09-07).
//
// The pixel gate compares the app against a baseline generated from the reference through
// the SAME harness, so anything that blinds both targets at once is invisible to it: that is
// exactly how an opaque basemap-tile stub hid the C5/C7 community mosaic under the Esri label
// tiles (MarketMapV3.jsx:190 puts them in `shadowPane`, above the overlay pane) while all 27
// states passed at maxDiffPixels: 0. harness.test.ts guards the tile's bytes; this guards the
// thing the bytes are for — that the shading actually reaches the screen.
//
// It asserts against the design's own palette, not a remembered colour: `PALETTES.distinct`
// is the default (logic.js:276) and `browse` opens on "Median household income", so the map
// must contain at least one pixel of the `distinct.income` ramp as the map composites it —
// fillOpacity 0.5 (MarketMapV3.jsx:252-256) over Leaflet's #ddd ground, which is what shows
// through the transparent tile stub. ±1 per channel absorbs the compositor's rounding.
// ---------------------------------------------------------------------------------------

/** Well inside the map, clear of the market column and the floating legend/insight card. */
const MAP_SAMPLE = { x: 400, y: 200, width: 500, height: 600 };
/** logic.js:81 — PALETTES.distinct.income, the five classes of the default layer. */
const INCOME_RAMP = ['#e6f2e8', '#c2e0cd', '#a8d5b5', '#4c9a6a', '#1b6b3a'];
/** Leaflet's own container background, visible because the stubbed tiles are transparent. */
const GROUND = 221;

async function expectMosaicShading(page: Page): Promise<void> {
  const shot = (await page.screenshot({ clip: MAP_SAMPLE, animations: 'disabled', caret: 'hide', scale: 'css' })).toString('base64');
  // Decoded in the page: the browser owns a PNG decoder, so the test needs no image library.
  const hits = await page.evaluate(async ({ b64, ramp, ground }) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(img, 0, 0);
    const px = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    const want = ramp.map((hex) => [1, 3, 5].map((i) => Math.round((parseInt(hex.slice(i, i + 2), 16) + ground) / 2)));
    const found: Record<string, number> = {};
    for (let i = 0; i < px.length; i += 4) {
      for (let w = 0; w < want.length; w++) {
        const [r, g, b] = want[w];
        if (Math.abs(px[i] - r) <= 1 && Math.abs(px[i + 1] - g) <= 1 && Math.abs(px[i + 2] - b) <= 1) {
          found[ramp[w]] = (found[ramp[w]] || 0) + 1;
        }
      }
    }
    return found;
  }, { b64: shot, ramp: INCOME_RAMP, ground: GROUND });

  const total = Object.values(hits).reduce((a, b) => a + b, 0);
  expect(
    total,
    `no pixel in the map region matched a distinct.income ramp colour over #ddd, so the mosaic ` +
    `is not reaching the screen — and the pixel gate cannot see that, because it would blind ` +
    `the reference too. Matches by ramp class: ${JSON.stringify(hits)}`
  ).toBeGreaterThan(0);
}

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
      // Runs after the comparison, so it can never perturb the compared capture.
      if (s.name === 'browse') await expectMosaicShading(page);
    });
  }
});
