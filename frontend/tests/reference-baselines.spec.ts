import { expect, test } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCREENS } from './screens';
import { booted, placeholderRings, prepare, settle } from './harness';

const OUT = join(fileURLToPath(new URL('.', import.meta.url)), 'visual.spec.ts-snapshots');

// Produces the oracle images from the approved design. Run only via
// `npm run test:visual:baselines`; commit the PNGs.
test.describe('reference baselines', () => {
  for (const s of SCREENS) {
    test(s.name, async ({ page }) => {
      mkdirSync(OUT, { recursive: true });
      await prepare(page);
      if (s.viewport) await page.setViewportSize(s.viewport);
      await booted(page);
      await s.steps(page);
      await settle(page);
      // B2 (A-I8.2), guarded at the moment the oracle is WRITTEN — the cheapest place, since a
      // baseline with the dashed placeholder ring drawn over the practice photo becomes the thing
      // every later run is compared against. `prepare()` suppresses the design runtime's
      // document re-fetch on this origin for exactly this reason; the mechanism is in its
      // comment. `browse` is the state the race was measured on (it lost it every time);
      // `detail` and `interest-modal` mount six and nine slots and happened to win, so they are
      // checked here too at no extra cost.
      // A19's three states mount filled slots beneath a 55 % scrim, where a pre-hydration ring
      // would be frozen into the oracle.
      if (['browse', 'detail', 'interest-modal', 'detail-lightbox', 'browse-panel-lightbox', 'detail-lightbox-next'].includes(s.name)) {
        expect(
          await placeholderRings(page),
          'an <image-slot> with a real src is still drawing its placeholder ring, so this baseline would freeze the design tool\'s pre-hydration artifact instead of the design'
        ).toEqual([]);
      }
      await page.screenshot({ path: join(OUT, `${s.name}-${process.platform}.png`), fullPage: true, animations: 'disabled', caret: 'hide', scale: 'css' });
    });
  }
});
