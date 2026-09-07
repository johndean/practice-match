import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { SCREENS } from './screens';
import { booted, prepare, settle } from './harness';

// ---------------------------------------------------------------------------------------
// Task V17 — the oracle generator has to be bit-reproducible.
//
// `reference-baselines.spec.ts` writes each baseline with ONE raw
// `page.screenshot({ fullPage: true })` and nothing downstream re-takes it, so a capture that
// is not bit-reproducible bakes whichever image it happened to produce into the oracle. The
// app project cannot reveal that — `toHaveScreenshot` re-captures until it matches — so the
// only symptom is the one V16 hit: `header-1000-darwin.png` flipping between two hashes
// across repeated `npm run test:visual:baselines` runs with no code change (~13 % of runs
// took the minority image), while its DOM snapshot never moved.
//
// The flip is twelve pixels: a two-pixel-wide column at the results rail's cards' left edge,
// four clusters of three rows, each the antialiasing of a card's rounded left corner, each
// off by exactly one grey level. The rail's cards sit at fractional y offsets (118.25 tall,
// 10 px apart), so those corner pixels are on the fence, and Chromium's PARTIAL RASTER —
// re-rastering only the invalidated part of a tile and reusing the rest — resolves them one
// way or the other depending on which tiles the `fullPage` capture's beyond-viewport pass
// invalidates. Nothing in the page moves: across 24 fresh loads the sub-pixel geometry is
// identical and a viewport-sized capture is identical 24/24; only `fullPage` (which every
// approved state uses, and which takes Chromium's `captureBeyondViewport` path whenever the
// document is taller than the viewport — it always is here, the design's root is
// `min-height: 100vh` with 18 px more content) flips. Pinning the raster is therefore the
// fix: `--disable-partial-raster` in `playwright.config.ts`, applied to every project so the
// reference and the app rasterise the same way. It is not a tolerance change — the gate
// stays at `maxDiffPixels: 0` (Global Constraint (e)).
//
// This test is the guard. Ten loads at ~13 % per-capture flip rate fail ~75 % of the time
// without the flag; with it the same ten are byte-identical.
// ---------------------------------------------------------------------------------------

const CAPTURES = 10;

test.setTimeout(180_000);

test.describe('capture determinism', () => {
  // The two states README §2 names for V3's short-column collapse. They share one cause with
  // the rest of the Browse family (`browse` flips identically, 12 pixels at x 987–988), and
  // one fix; these two are the ones the flake was found on and are cheap enough to gate.
  for (const name of ['header-1000', 'header-1100']) {
    test(`${name} is byte-identical across ${CAPTURES} captures`, async ({ page }) => {
      const s = SCREENS.find((x) => x.name === name)!;
      await prepare(page);
      if (s.viewport) await page.setViewportSize(s.viewport);
      const hashes: string[] = [];
      for (let i = 0; i < CAPTURES; i++) {
        await booted(page);
        await s.steps(page);
        await settle(page);
        const shot = await page.screenshot({ fullPage: true, animations: 'disabled', caret: 'hide', scale: 'css' });
        hashes.push(createHash('sha256').update(shot).digest('hex'));
      }
      const tally = [...hashes.reduce((m, k) => m.set(k, (m.get(k) ?? 0) + 1), new Map<string, number>())]
        .map(([k, n]) => `${k.slice(0, 12)}×${n}`)
        .join(' ');
      expect(
        new Set(hashes).size,
        `${name} produced more than one image from ${CAPTURES} identical page loads, so the ` +
        `baseline written by reference-baselines.spec.ts is a coin toss: ${tally}`
      ).toBe(1);
    });
  }
});
