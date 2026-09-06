import type { Page } from '@playwright/test';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

export type JumpLabel = 'Access' | 'Browse' | 'Listing' | 'Requests' | 'Seller' | 'Admin';

// Deterministic rendering on both targets: no basemap tiles (markers still draw
// over the blank canvas), fonts loaded, pointer parked, animations settled.
const VENDOR = join(fileURLToPath(new URL('.', import.meta.url)), '../../docs/design-reference/design_handoff_practice_match_v3/vendor');
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

// 1×1 fully transparent GIF, used for the stubbed basemap tiles and to answer the
// reference's pre-hydration image-slot noise below. It MUST be transparent, not merely
// blank-looking: MarketMapV3.jsx:190 puts the Esri label tiles in `shadowPane` (z-index
// 500), deliberately ABOVE the community mosaic in the overlay pane (z-index 400), so an
// opaque stub paints 24 solid squares over the C5/C7 shading and the zero-tolerance gate
// compares two unshaded maps. The previous constant
// (R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==) carried no Graphic Control Extension
// and was therefore opaque white — harmless under V2, which drew nothing beneath the
// labels. Guarded by harness.test.ts (controller ruling 2026-09-07). With a transparent
// tile the basemap area is Leaflet's own #ddd rather than white, on both targets.
export const BLANK_GIF = Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64');

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

// ---------------------------------------------------------------------------------------
// The one state whose capture a page scroll can move.
//
// App.vue has exactly ONE `position: fixed` element — the interest modal's overlay
// (`position: fixed; inset: 0; z-index: 900; … place-items: center`). Everything else on all
// 27 approved states is in normal flow, and a fullPage screenshot captures flow content
// whole regardless of where the page happens to be scrolled. A fixed element is different:
// it is composited at the offset it PAINTS at, so a page scrolled by N pixels puts the whole
// overlay — backdrop and the dialog centred inside it — N pixels down the screenshot while
// the dimmed content behind it does not move.
//
// That is what failed CI on the vin-swe runner at fa17a91 (`interest-modal`, 23,441 pixels,
// 1 %), and only there: comparing that run's own expected/actual pair pixel by pixel, the
// actual aligns with the expected EXACTLY at dy = +5 and dx = 0 (zero mismatching samples
// across the dialog) — a pure translation, nothing reflowed, no animation mid-flight (the
// runner's log even says "captured a stable screenshot"). The backdrop's top edge sits at
// y = 0 in one and y = 5 in the other, its bottom edge at 939 and 943.
//
// The scroll comes from the click itself: Playwright scrolls a target into view before
// clicking it, and the listing page is ~20 px taller on the Linux runner than on darwin
// (2375 vs 2355 for the same commit, font metrics), which is enough to push "I'm interested"
// past the fold and scroll the page a few pixels first. Reproduced on darwin by scrolling
// 5 px by hand before the capture: 23,608 pixels, the same failure.
//
// So the capture is pinned instead of hoped for: scroll back to the top, then hold until the
// overlay's own box has been identical across two consecutive animation frames with the page
// still at the top. Nothing is relaxed and no tolerance moves — the screenshot is simply
// taken from the one viewport position the design's centred dialog is drawn for.
export async function atTop(page: Page, selector: string): Promise<void> {
  await page.locator(selector).first().waitFor({ state: 'visible' });
  await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' as ScrollBehavior }));
  await page.waitForFunction(
    (sel) =>
      new Promise<boolean>((resolve) => {
        const el = document.querySelector(sel);
        if (!el) return resolve(false);
        const a = el.getBoundingClientRect();
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            const b = el.getBoundingClientRect();
            resolve(window.scrollY === 0 && a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height);
          })
        );
      }),
    selector
  );
}

export async function waitMap(page: Page): Promise<void> {
  await page.locator('.leaflet-container').first().waitFor({ state: 'visible' });
  await page.waitForTimeout(700); // Leaflet setView + marker layer
}
