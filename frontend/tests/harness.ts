import type { Page } from '@playwright/test';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

export type JumpLabel = 'Access' | 'Browse' | 'Listing' | 'Requests' | 'Seller' | 'Admin';

// Deterministic rendering on both targets: no basemap tiles (markers still draw
// over the blank canvas), fonts loaded, pointer parked, animations settled.
const VENDOR = join(fileURLToPath(new URL('.', import.meta.url)), '../../docs/design-reference/design_handoff_practice_match_v2/vendor');
// support.js loads React/ReactDOM/Babel from unpkg with SRI; AustinMap.jsx and MarketMap.jsx
// (loaded by the reference's Browse/Listing/Market screens) separately load Leaflet from
// unpkg the same SRI-pinned way — all five must be vendored or the map screens never boot.
const VENDORED: Record<string, { file: string; type: string }> = {
  'https://unpkg.com/react@18.3.1/umd/react.production.min.js': { file: 'react.production.min.js', type: 'text/javascript' },
  'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js': { file: 'react-dom.production.min.js', type: 'text/javascript' },
  'https://unpkg.com/@babel/standalone@7.29.0/babel.min.js': { file: 'babel.min.js', type: 'text/javascript' },
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css': { file: 'leaflet.css', type: 'text/css' },
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js': { file: 'leaflet.js', type: 'text/javascript' }
};

// 1×1 transparent GIF, used to answer the reference's pre-hydration image-slot noise below.
const BLANK_GIF = Buffer.from('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==', 'base64');

export async function prepare(page: Page): Promise<void> {
  page.on('pageerror', (e) => { throw new Error(`page error: ${e.message}`); });
  page.on('console', (m) => { if (m.type() === 'error') throw new Error(`console.error: ${m.text()}`); });
  // Fulfilling (not aborting) the basemap tiles: an aborted <img> request logs its own
  // "Failed to load resource: net::ERR_FAILED" console error in Chromium, which the error
  // gate above would then fail the test on. A blank tile gives the same deterministic,
  // offline-safe result the comment above promises (no basemap imagery, markers still draw
  // over the blank canvas) without that side effect.
  await page.route(/arcgisonline\.com/, (route) => route.fulfill({ status: 200, contentType: 'image/gif', body: BLANK_GIF }));
  // The reference runtime loads React/Babel/Leaflet from unpkg with SRI hashes; serve the
  // vendored identical bytes so the suite is deterministic and offline-safe (same hashes →
  // SRI passes). An abort() here would fail the error gate the same way the tile fix above
  // does, so anything else under unpkg.com is fulfilled with a blank response, not aborted.
  await page.route('https://unpkg.com/**', (route) => {
    const v = VENDORED[route.request().url()];
    return route.fulfill(v ? { path: join(VENDOR, v.file), contentType: v.type } : { status: 200, contentType: 'text/plain', body: '' });
  });
  // Reference-only, harmless noise: the design tool's <image-slot> custom element
  // (image-slot.js) upgrades on the raw, pre-hydration DOM — before the dc-runtime's
  // first React render replaces it — and requests its own literal, unresolved "{{ expr }}"
  // placeholder text as an image URL, plus a `.image-slots.state.json` sidecar probe. Both
  // 404 on any host but the design tool's own editor and never recur once React mounts;
  // neither occurs on the Vue app (compiled bindings, no raw-text DOM phase; see
  // ImageSlot.vue's `v-if="src"`). Answer them rather than let this artifact of the
  // reference's own runtime trip the error gate.
  await page.route(/%7B%7B|\.image-slots\.state\.json$/, (route) => {
    const url = route.request().url();
    return route.fulfill(
      url.endsWith('.image-slots.state.json')
        ? { status: 200, contentType: 'application/json', body: '{}' }
        : { status: 200, contentType: 'image/gif', body: BLANK_GIF }
    );
  });
}

export async function booted(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByRole('button', { name: 'Access', exact: true }).first().waitFor({ state: 'visible' });
}

export async function settle(page: Page): Promise<void> {
  await page.evaluate(() => (document as Document & { fonts: FontFaceSet }).fonts.ready);
  await page.mouse.move(0, 0);
  await page.waitForTimeout(600);
}

// The design's own prototype jump bar: signs in and switches screen on both targets.
export async function jump(page: Page, label: JumpLabel): Promise<void> {
  await page.getByRole('button', { name: label, exact: true }).first().click();
}

export async function click(page: Page, text: string): Promise<void> {
  await page.getByText(text, { exact: true }).first().click();
}

export function btn(page: Page, name: RegExp) {
  return page.getByRole('button', { name }).first();
}

export async function waitMap(page: Page): Promise<void> {
  await page.locator('.leaflet-container').first().waitFor({ state: 'visible' });
  await page.waitForTimeout(700); // Leaflet setView + marker layer
}
