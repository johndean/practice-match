import { test, expect } from '@playwright/test';
import { CS_SCREENS } from './coming-soon.screens';
import { bootedComingSoon, prepareComingSoon, settle } from './coming-soon-harness';

// Every approved Coming Soon state must match the reference's screenshot.
test.describe('coming-soon visual parity with the approved design', () => {
  for (const s of CS_SCREENS) {
    test(s.name, async ({ page }) => {
      await prepareComingSoon(page, 'app');
      if (s.viewport) await page.setViewportSize(s.viewport);
      await bootedComingSoon(page, '/');
      await s.steps(page);
      await settle(page);
      await expect(page).toHaveScreenshot(`${s.name}.png`, { fullPage: true });
    });
  }
});
