import { test, expect } from '@playwright/test';
import { SCREENS } from './screens';
import { booted, prepare, settle } from './harness';

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
    });
  }
});
