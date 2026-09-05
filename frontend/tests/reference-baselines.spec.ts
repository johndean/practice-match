import { test } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCREENS } from './screens';
import { booted, prepare, settle } from './harness';

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
      await page.screenshot({ path: join(OUT, `${s.name}-${process.platform}.png`), fullPage: true, animations: 'disabled', caret: 'hide', scale: 'css' });
    });
  }
});
