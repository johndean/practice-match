import { test, expect, type Page } from '@playwright/test';
import { prepare } from './harness';

const ROUTES = ['/', '/browse', '/browse?tab=market', '/practices/p1', '/requests', '/seller', '/admin?tab=data'];

function trapErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  return errors;
}

test.describe('smoke', () => {
  for (const r of ROUTES) {
    test(`${r} renders the gate for a signed-out visitor without errors`, async ({ page }) => {
      await prepare(page);
      const errors = trapErrors(page);
      await page.goto(r);
      await expect(page.getByText('Approved members only')).toBeVisible();
      expect(errors).toEqual([]);
    });
  }

  test('a deep link is honoured after the fixture sign-in', async ({ page }) => {
    await prepare(page);
    await page.goto('/browse?tab=market');
    await page.getByRole('button', { name: 'Approved — enter', exact: true }).click();
    await expect(page).toHaveURL(/\/browse\?tab=market$/);
    await expect(page.getByRole('button', { name: 'Data Layers', exact: true })).toBeVisible();
  });

  test('navigation writes the URL', async ({ page }) => {
    await prepare(page);
    await page.goto('/');
    await page.getByRole('button', { name: 'Browse', exact: true }).first().click();
    await expect(page).toHaveURL(/\/browse$/);
    await page.getByText('Market Data', { exact: true }).first().click();
    await expect(page).toHaveURL(/\/browse\?tab=market$/);
    await page.getByRole('button', { name: 'Listing', exact: true }).first().click();
    await expect(page).toHaveURL(/\/practices\/p1$/);
    await page.getByRole('button', { name: 'Admin', exact: true }).first().click();
    await page.getByRole('button', { name: /^Data Sources\s*\d/ }).first().click();
    await expect(page).toHaveURL(/\/admin\?tab=data$/);
  });

  test('unknown routes redirect to /', async ({ page }) => {
    await page.goto('/definitely-not-a-route');
    await expect(page).toHaveURL(/\/$/);
  });

  // Performance gate (policy §3): the market map's first paint. The clock starts on the
  // navigation, not after it — the deep link is signed in through the gate's fixture
  // button, which is the only way `/browse?tab=market` survives a cold load, so the
  // budget covers boot + gate + the pending deep link + Leaflet's first paint.
  // `[data-map]` is set by LeafletMapEngine.mount() once the map is on the page.
  test('first map paint within budget', async ({ page }) => {
    await prepare(page);
    const started = Date.now();
    await page.goto('/browse?tab=market');
    await page.getByRole('button', { name: 'Approved — enter', exact: true }).click();
    await page.locator('[data-map]').waitFor();
    const elapsed = Date.now() - started;
    expect(elapsed, `first map paint took ${elapsed}ms`).toBeLessThanOrEqual(1500);
  });
});
