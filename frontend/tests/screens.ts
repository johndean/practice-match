import type { Page } from '@playwright/test';
import { atTop, btn, click, jump, waitMap } from './harness';

export interface Screen {
  name: string;
  viewport?: { width: number; height: number }; // default 1440×940 from the config
  steps: (page: Page) => Promise<void>;         // identical clicks on reference and app, from the gate
}

// V3 (C1): Browse Practices is ONE screen — map with market data on the left, the results
// rail on the right. There is no Listings / Market Data toggle and therefore no `market`
// helper: every Browse state starts from `browse`.
const browse = async (p: Page) => { await jump(p, 'Browse'); await waitMap(p); };
const wizard = async (p: Page) => { await jump(p, 'Seller'); await click(p, 'Create a listing'); };
const admin = async (p: Page) => { await jump(p, 'Admin'); };
const mobile = async (p: Page) => { await click(p, 'Mobile view'); await jump(p, 'Browse'); };
// App.vue's single position:fixed element — the interest modal's backdrop (see harness.ts's
// `atTop`, which explains why this one state has to be pinned to the top of the page).
const MODAL = 'div[style*="z-index: 900"]';
// The prototype's own 390×800 phone frame (App.vue:1242) and the market-data sheet inside it.
// `z-index: 700` is not unique in App.vue on its own — the desktop "More filters" popover
// carries it too — so the sheet is always addressed through the frame. `atTop` takes a plain
// CSS selector (it runs document.querySelector in the page), and the popover is not in the DOM
// while the mobile frame is showing, so the bare selector is unambiguous there.
const PHONE = 'div[style*="width: 390px"][style*="height: 800px"]';
const SHEET = 'div[style*="z-index: 700"]';

export const SCREENS: Screen[] = [
  { name: 'gate-signin', steps: async () => {} },
  { name: 'gate-apply', steps: async (p) => { await click(p, 'Request access'); } },
  { name: 'gate-pending', steps: async (p) => { await click(p, 'Pending approval'); } },
  { name: 'gate-declined', steps: async (p) => { await click(p, 'Request declined'); } },
  { name: 'browse', steps: browse },
  // The Market data card's layer select (V3's `md.toggleLayerMenu` trigger). It is the first
  // aria-haspopup="listbox" on the screen; Compare's identical control is the second, and
  // only exists once Compare is open.
  { name: 'browse-layer-menu', steps: async (p) => { await browse(p); await p.locator('button[aria-haspopup="listbox"]').first().click(); await p.waitForTimeout(400); } },
  // C4: Compare is collapsed by default; opening it reveals the shared layer-select control
  // and the six-row bar chart. Picking the metric that already shades the map would reset the
  // comparison (no self-compare), so pick the second option — the menu's first row is
  // "Choose a metric…" (logic.js `compareOptions`). The option lookup is scoped to the
  // compare menu's own listbox: Browse's native <select>s (market, filters, sort) own the
  // `option` role too and come first in the DOM, so an unscoped getByRole('option') resolves
  // to a collapsed <select>'s hidden child on BOTH targets and never clicks.
  { name: 'browse-compare-open', steps: async (p) => { await browse(p); await click(p, 'Compare'); await p.locator('button[aria-haspopup="listbox"]').nth(1).click(); await p.getByRole('listbox', { name: 'Comparison layer' }).getByRole('option').nth(1).click(); await p.waitForTimeout(400); } },
  // C8: the merged legend/insight card is dismissible.
  { name: 'browse-legend-collapsed', steps: async (p) => { await browse(p); await p.getByRole('button', { name: 'Dismiss interpretation' }).click(); await p.waitForTimeout(400); } },
  // C9: V3's drawer button reads "Layers" with a count pill, where V2's read "Data Layers".
  // The `-market-` infix went with the Listings/Market Data split (spec D12) and the state is
  // `browse-layers-OPEN` because that is what it shows: under V2 the drawer stood open and the
  // click closed it, under V3 the click opens it, so the inherited `-closed` suffix described
  // the opposite of the screenshot (review L2; controller ruling 2026-09-07 amending D12).
  { name: 'browse-layers-open', steps: async (p) => { await browse(p); await click(p, 'Layers'); await p.waitForTimeout(400); } },
  { name: 'browse-market-panel', steps: async (p) => { await browse(p); await p.getByText('Cedar Park').first().click(); await p.waitForTimeout(400); } },
  { name: 'detail', steps: async (p) => { await jump(p, 'Listing'); } },
  // The jump bar's default listing (Cedar Park / p1) always carries a pre-seeded pending
  // request in the prototype's demo data (logic.js `state.requests`), so it never shows
  // "I'm interested" — only "Request sent". Open a listing with no seeded request instead
  // (Round Rock / p2) via a Browse results card.
  //
  // V3 needs the middle step the card alone used to cover: a card tap opens the DOCKED
  // practice-detail panel (`md.rows[].select` → `mdSel`, logic.js:673) on its Insights tab,
  // and that panel's own primary button is what reaches the listing screen
  // (`md.panel.openListing`, V3:704-705 / logic.js:879). The design labels it "View full
  // market report" there; the identically-wired "Open full listing" (V3:717) exists only on
  // the panel's other tabs. Without this step the state timed out on the V3 reference itself
  // waiting for "I'm interested" — the same dead `results[].open` handler that broke
  // `mobile-detail`, and the same ruling applies: use the design's own route (controller,
  // 2026-09-07).
  { name: 'interest-modal', steps: async (p) => { await browse(p); await p.getByText('Round Rock').first().click(); await click(p, 'View full market report'); await click(p, "I'm interested"); await atTop(p, MODAL); } },
  { name: 'requests', steps: async (p) => { await jump(p, 'Requests'); } },
  { name: 'seller-dash', steps: async (p) => { await jump(p, 'Seller'); } },
  { name: 'wizard-step-1', steps: wizard },
  { name: 'wizard-step-7', steps: async (p) => { await wizard(p); await btn(p, /^7/).click(); } },
  { name: 'wizard-preview', steps: async (p) => { await wizard(p); await btn(p, /^8/).click(); } },
  { name: 'wizard-done', steps: async (p) => { await wizard(p); await btn(p, /^8/).click(); await click(p, 'Submit for review'); } },
  { name: 'admin-users', steps: admin },
  { name: 'admin-listings', steps: async (p) => { await admin(p); await btn(p, /^Listings\s*\d/).click(); } },
  { name: 'admin-requests', steps: async (p) => { await admin(p); await btn(p, /^Requests\s*\d/).click(); } },
  { name: 'admin-data-sources', steps: async (p) => { await admin(p); await btn(p, /^Data Sources\s*\d/).click(); } },
  { name: 'mobile-list', steps: mobile },
  { name: 'mobile-map', steps: async (p) => { await mobile(p); await click(p, 'Map'); await waitMap(p); } },
  // V10 review, minor 1: the OPENED sheet had no oracle of its own. `mobile-map` captures it
  // closed, so C13's five sections, the ramp, and the "Source:" / "Updated:" lines — the
  // attribution CLAUDE.md marks legally load-bearing — were gated only by the smoke block.
  // This state puts the sheet itself under the same zero-tolerance pixel gate and the same
  // node-for-node DOM oracle as every other approved screen.
  //
  // The harness viewport stays the design's 1440×940, exactly as the other three mobile states
  // do: 390×800 is the PROTOTYPE's phone frame, drawn inside that page, not a browser resize.
  // `atTop` pins the page at scroll 0 and waits for the sheet's box to settle, so the capture
  // cannot drift the way interest-modal's did on the Linux runner.
  { name: 'mobile-sheet', steps: async (p) => {
      await mobile(p);
      await click(p, 'Map');
      await waitMap(p);
      await p.locator(PHONE).locator('button', { hasText: /of \d/ }).click();
      await p.locator(PHONE).locator(SHEET).waitFor({ state: 'visible' });
      await atTop(p, SHEET);
    } },
  // The phone reaches this screen from the MAP, not the list. CHANGE_LOG C13, verbatim:
  // "No peek card — tapping an already-selected pin opens the detail screen"
  // (logic.js `mobileVals.selectMarker`: the same id twice → `{ screen: "detail" }`). V3's
  // result card cannot get here at all — `results[].open` was repurposed to
  // `{ browseSel, activeId }` (V3 design script:3087, ported at logic.js:1530) where V2's
  // set `screen: "detail"`, and `browseSel` is bound by no markup, so the card tap is a dead
  // handler on the reference and the app alike (V7 Step 8: `mobile-detail` failed to
  // navigate on BOTH targets; controller ruling 2026-09-07 — the harness must not invent a
  // card navigation the design does not have). Waiting for the detail screen's own
  // "Exterior photo" band (V3:1522) keeps the step from ever silently no-opping again.
  //
  // The ORDER is load-bearing: go straight to Map. A result-card tap first is not inert even
  // though nothing visible changes — it sets `activeId` (logic.js:1530), which makes the next
  // single pin tap open the detail where a fresh session needs two, so the step would still
  // pass while exercising half of C13's route (review I1).
  { name: 'mobile-detail', steps: async (p) => {
      await mobile(p);
      await click(p, 'Map');
      await waitMap(p);
      await p.locator('.leaflet-marker-icon').first().click();   // select
      await p.waitForTimeout(400);
      await p.locator('.leaflet-marker-icon').first().click();   // tap the selected pin again
      await p.getByText('Exterior photo').first().waitFor({ state: 'visible' });
    } },
  { name: 'header-1100', viewport: { width: 1100, height: 940 }, steps: browse },
  { name: 'header-1000', viewport: { width: 1000, height: 940 }, steps: browse }
];
