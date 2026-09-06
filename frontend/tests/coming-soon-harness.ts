import type { Page } from '@playwright/test';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { prepare, settle } from './harness';

export { settle };
const FONT = join(fileURLToPath(new URL('.', import.meta.url)), '../../coming-soon/public/ds/fonts/Merriweather-Latin.woff2');
const FONT_CSS = "@font-face{font-family:'Merriweather';font-style:normal;font-weight:400 700;font-display:swap;src:url('https://fonts.gstatic.com/merriweather-latin.woff2') format('woff2');}";

/** Same error gates and vendored runtime as the marketplace harness, plus: the design's Google Fonts
 *  request is answered with the app's own self-hosted Merriweather (identical glyphs on both targets,
 *  offline-safe), and on the app the sign-up POST is answered 202 so the confirmed state needs no backend. */
export async function prepareComingSoon(page: Page, target: 'reference' | 'app'): Promise<void> {
  await prepare(page);
  await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ status: 200, contentType: 'text/css', body: FONT_CSS }));
  await page.route('https://fonts.gstatic.com/**', (route) => route.fulfill({ status: 200, path: FONT, contentType: 'font/woff2' }));
  if (target === 'app') {
    await page.route('**/api/interest', (route) => route.fulfill({ status: 202, contentType: 'application/json', body: '{"status":"ok"}' }));
  }
}

export async function bootedComingSoon(page: Page, url: string): Promise<void> {
  await page.goto(url);
  await page.getByRole('button', { name: 'Notify me', exact: true }).waitFor({ state: 'visible' });
}
