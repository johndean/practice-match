import { test } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CS_SCREENS } from './coming-soon.screens';
import { bootedComingSoon, prepareComingSoon, settle } from './coming-soon-harness';

const OUT = join(fileURLToPath(new URL('.', import.meta.url)), 'visual.spec.ts-snapshots');

// Produces the oracle images from the approved Coming Soon design. Run only via
// `npm run test:cs:baselines`; the PNGs are generated per run, not committed.
test.describe('coming-soon reference baselines', () => {
  for (const s of CS_SCREENS) {
    test(s.name, async ({ page }) => {
      mkdirSync(OUT, { recursive: true });
      await prepareComingSoon(page, 'reference');
      if (s.viewport) await page.setViewportSize(s.viewport);
      await bootedComingSoon(page, '/coming-soon/');
      await s.steps(page);
      await settle(page);
      await page.screenshot({ path: join(OUT, `${s.name}-${process.platform}.png`), fullPage: true, animations: 'disabled', caret: 'hide', scale: 'css' });
    });
  }
});
