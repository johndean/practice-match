import type { Page } from '@playwright/test';
import { DECLINED_FIELDS, NEEDS_REVIEW_INFO_REQUEST, atTop, btn, click, expectApiStatus, reach, settleExpectedApiFailures, waitMap } from './harness';

export interface Screen {
  name: string;
  viewport?: { width: number; height: number }; // default 1440×940 from the config
  steps: (page: Page) => Promise<void>;         // reach() the entry, then identical clicks on both targets
}

// Every state ENTERS through `reach()` (amendment A-I8) and is then driven by the same clicks
// on both targets. The entry has to differ because the two targets are different things: the
// reference is a static prototype and gets there through the design's own props (injected by
// reference-server.mjs's `?props=`), the app signs in as a seeded account and deep-links the
// route. What used to be shared — `jump()` on the prototype jump bar, the "Prototype — access
// states" shortcuts, the jump bar's "Mobile view" toggle — leaves the design in A6.1/A6.2, so
// there is nothing left to share. See harness.ts's `reach` for the two drivers.
//
// V3 (C1): Browse Practices is ONE screen — map with market data on the left, the results
// rail on the right. There is no Listings / Market Data toggle and therefore no `market`
// helper: every Browse state starts from `browse`.
const browse = async (p: Page) => { await reach(p, { screen: 'browse' }); await waitMap(p); };
const wizard = async (p: Page) => { await reach(p, { screen: 'seller' }); await click(p, 'Create a listing'); };
const admin = async (p: Page) => { await reach(p, { screen: 'admin' }); };
// D-I8-7: the phone frame is a PROTOTYPE presentation, not a browser resize — the harness
// viewport stays the design's 1440×940. The "Mobile view" toggle that used to set it lived in
// the jump bar, so it is asked for through `startViewport` now: `?props=` on the reference,
// `?viewport=mobile` on the app.
const mobile = async (p: Page) => { await reach(p, { screen: 'browse', viewport: 'mobile' }); };
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

// ---------------------------------------------------------------------------------------
// The fifteen account-screen states (spec §6, controller amendment A-S5). Three helpers, and
// then one entry per state — everything else about them is in `reach()`.
// ---------------------------------------------------------------------------------------

/**
 * A state whose APP entry deliberately provokes a real `TOKEN_INVALID` (400) from the API, which
 * Chromium logs as a console error `prepare()` would otherwise fail the test on.
 *
 * The allowance is armed here, next to the state that needs it, for one status and one line; and
 * it is ASSERTED to have been used, so a state that quietly stopped provoking its 4xx fails rather
 * than passing on a dead exemption. On the reference nothing is armed and nothing is allowed —
 * there is no API there to fail.
 */
const provokes400 = async (p: Page, shows: string, enter: () => Promise<void>) => {
  expectApiStatus(p, 400);
  await enter();
  await p.getByText(shows).first().waitFor({ state: 'visible' });
  await settleExpectedApiFailures(p);
};

/**
 * `gate-reapply` — the ONE state whose data cannot reach the reference (A-S5 ruling 2).
 *
 * The app's form arrives pre-filled from `GET /api/applications/me`, and the reference has no
 * adapter to fetch anything with. These six inputs are the design's OWN, so the state is put in
 * one place by typing the seeded values into both targets: `fill()` REPLACES, so it is idempotent
 * on the app, where they are already there. What that costs is the pre-fill's own proof, and
 * `account-flows.spec.ts` pays it — it asserts every seeded value BEFORE typing anything.
 *
 * The blur at the end is not cosmetic: `fill()` focuses programmatically, which sets
 * `:focus-visible` in Chromium, and a focus ring on the last field would be a pixel difference
 * between two captures that happened to end on different fields.
 */
const fillDeclinedApplication = async (p: Page) => {
  for (const [label, value] of [
    ['Full name and credentials', DECLINED_FIELDS.name],
    ['VIN member ID (if you have one)', ''],
    ['Veterinary school and graduation year', DECLINED_FIELDS.school_year],
    ['License state', DECLINED_FIELDS.license_state],
    ['Current practice or employer', DECLINED_FIELDS.employer],
    ['Why do you want access?', DECLINED_FIELDS.intent]
  ] as const) {
    await p.getByLabel(label, { exact: true }).fill(value);
  }
  await p.getByRole('checkbox').first().setChecked(DECLINED_FIELDS.affirm);
  await p.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  // Playwright scrolls each field into view before it fills it, and the design's `<header>` is
  // `position: sticky` — which a fullPage screenshot composites at the offset it PAINTS at, so a
  // page left scrolled by N pixels puts the whole header N pixels down the capture while the flow
  // content behind it does not move. That is the `interest-modal` failure `atTop` was written for
  // (see harness.ts), and it is why the first run of this state differed from the reference by
  // 3,381 pixels — every one of them in the header. Pinned to the top, exactly as that state is.
  await atTop(p, 'header');
};

export const SCREENS: Screen[] = [
  { name: 'gate-signin', steps: async (p) => { await reach(p); } },
  // A-S4: reached by BEING an address that is confirmed and has not applied — A5.4's bootstrap
  // lands `verified@` on the Request Access card, on both targets. The design's own "Request
  // access" link used to be the way in; A8.1c sends an anonymous visitor's click to the sign-up
  // card instead, which is correct (there is no application without an account) and is why this
  // state now names an account like the two status gates below do.
  { name: 'gate-apply', steps: async (p) => { await reach(p, { gate: 'apply', persona: 'verified' }); } },
  // The two status gates were reached by the "Prototype — access states" buttons (A6.2 removes
  // them). On the app they are now reached by BEING in that state: `reach` signs in as the
  // seeded `pending@` / `declined@` account and A5.4's bootstrap maps the account's state to
  // the gate. On the reference — no session, no API — the same gate comes from `startGate`.
  { name: 'gate-pending', steps: async (p) => { await reach(p, { gate: 'pending', persona: 'pending' }); } },
  { name: 'gate-declined', steps: async (p) => { await reach(p, { gate: 'rejected', persona: 'declined' }); } },
  { name: 'browse', steps: browse },
  // The Market data card's layer select (V3's `md.toggleLayerMenu` trigger). It is the first
  // aria-haspopup="listbox" on the screen; Compare's identical control is the second, and
  // only exists once Compare is open.
  //
  // This state and the three below it (`browse-legend-collapsed`, `browse-layers-open`,
  // `browse-market-panel`) each wait for the thing the state exists to SHOW before the settle
  // (review M9, 2026-09-07). A bare `waitForTimeout` cannot tell "the click worked" from "the
  // click no-opped on both targets", which is exactly how the old `mobile-detail` step passed
  // while capturing the wrong screen (V9). The 400 ms settle stays after it: it is what the
  // committed baselines were taken through, and every one of them must stay byte-identical.
  { name: 'browse-layer-menu', steps: async (p) => { await browse(p); await p.locator('button[aria-haspopup="listbox"]').first().click(); await p.getByRole('listbox', { name: 'Active market layer' }).waitFor({ state: 'visible' }); await p.waitForTimeout(400); } },
  // C4: Compare is collapsed by default; opening it reveals the shared layer-select control
  // and the six-row bar chart. Picking the metric that already shades the map would reset the
  // comparison (no self-compare), so pick the second option — the menu's first row is
  // "Choose a metric…" (logic.js `compareOptions`). The option lookup is scoped to the
  // compare menu's own listbox: Browse's native <select>s (market, filters, sort) own the
  // `option` role too and come first in the DOM, so an unscoped getByRole('option') resolves
  // to a collapsed <select>'s hidden child on BOTH targets and never clicks.
  { name: 'browse-compare-open', steps: async (p) => { await browse(p); await click(p, 'Compare'); await p.locator('button[aria-haspopup="listbox"]').nth(1).click(); await p.getByRole('listbox', { name: 'Comparison layer' }).getByRole('option').nth(1).click(); await p.waitForTimeout(400); } },
  // C8: the merged legend/insight card is dismissible.
  { name: 'browse-legend-collapsed', steps: async (p) => { await browse(p); await p.getByRole('button', { name: 'Dismiss interpretation' }).click(); await p.getByRole('button', { name: 'Dismiss interpretation' }).waitFor({ state: 'detached' }); await p.waitForTimeout(400); } },
  // C9: V3's drawer button reads "Layers" with a count pill, where V2's read "Data Layers".
  // The `-market-` infix went with the Listings/Market Data split (spec D12) and the state is
  // `browse-layers-OPEN` because that is what it shows: under V2 the drawer stood open and the
  // click closed it, under V3 the click opens it, so the inherited `-closed` suffix described
  // the opposite of the screenshot (review L2; controller ruling 2026-09-07 amending D12).
  { name: 'browse-layers-open', steps: async (p) => { await browse(p); await click(p, 'Layers'); await p.getByRole('button', { name: 'Close layers' }).waitFor({ state: 'visible' }); await p.waitForTimeout(400); } },
  { name: 'browse-market-panel', steps: async (p) => { await browse(p); await p.getByText('Cedar Park').first().click(); await p.getByText('View full listing').first().waitFor({ state: 'visible' }); await p.waitForTimeout(400); } },
  { name: 'detail', steps: async (p) => { await reach(p, { screen: 'detail' }); } },
  // The default listing (Cedar Park / p1 — `state.detailId`, and the route `reach` deep-links)
  // always carries a pre-seeded pending request in the prototype's demo data (logic.js
  // `state.requests`), so it never shows
  // "I'm interested" — only "Request sent". Open a listing with no seeded request instead
  // (Round Rock / p2) via a Browse results card.
  //
  // V3 needs the middle step the card alone used to cover: a card tap opens the DOCKED
  // practice-detail panel (`md.rows[].select` → `mdSel`, logic.js:673) on its Insights tab,
  // and that panel's own primary button is what reaches the listing screen
  // (`md.panel.openListing`, V3:704-705 / logic.js:879). The design labels it "View full
  // listing" there (spec D18, A3 — was "View full market report"); the identically-wired
  // button on the panel's other tabs (V3:717) reads the same "View full listing" since A11
  // (John, 2026-09-08: unify — was "Open full listing"). Without this step the state timed out
  // on the V3 reference itself waiting for "I'm interested" — the same dead `results[].open`
  // handler that broke `mobile-detail`, and the same ruling applies: use the design's own
  // route (controller, 2026-09-07).
  { name: 'interest-modal', steps: async (p) => { await browse(p); await p.getByText('Round Rock').first().click(); await click(p, 'View full listing'); await click(p, "I'm interested"); await atTop(p, MODAL); } },
  { name: 'requests', steps: async (p) => { await reach(p, { screen: 'requests' }); } },
  { name: 'seller-dash', steps: async (p) => { await reach(p, { screen: 'seller' }); } },
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
  // (A2 has since given the mobile card its own navigation — see the `results[].open`
  // characterisation in logic.test.ts — but this state stays on C13's pin route, which is
  // what the CHANGE_LOG describes and what the baseline was taken through.)
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
  { name: 'header-1000', viewport: { width: 1000, height: 940 }, steps: browse },

  // ---------------------------------------------------------------------------------------
  // The account screens (spec §6). Each is a new value of `state.gate`, so the reference reaches
  // every one through `startGate` and the app through the real route, the real account or the
  // real token — see harness.ts's `referenceUrl`/`appPlan` for the two drivers and why they
  // differ where they do.
  // ---------------------------------------------------------------------------------------
  { name: 'gate-signup', steps: async (p) => { await reach(p, { gate: 'signup' }); } },
  // Reached by BEING an address that has not confirmed itself: A8.3b's bootstrap lands
  // `unverified@` here and puts its address in the card's own copy, which is why this state names
  // an account on both targets rather than only on the app.
  { name: 'gate-check-email', steps: async (p) => { await reach(p, { gate: 'check-email', persona: 'unverified' }); } },
  // A token no seed created: the API's own 400 is what produces this card, not an assertion.
  { name: 'gate-verify-expired', steps: async (p) => { await provokes400(p, 'This link is no longer valid', () => reach(p, { gate: 'verify-expired' })); } },
  { name: 'gate-forgot', steps: async (p) => { await reach(p, { gate: 'forgot' }); } },
  // The form renders from the token in the URL and spends it only on submit, which this state
  // never does — the run's counter still advances (see `appPlan`).
  { name: 'gate-reset', steps: async (p) => { await reach(p, { gate: 'reset' }); } },
  // Two matching passwords against an unseeded token: the policy passes, the token does not, and
  // the card is `POST /api/auth/password/reset`'s real verdict.
  { name: 'gate-reset-expired', steps: async (p) => { await provokes400(p, 'This link is no longer valid', () => reach(p, { gate: 'reset-expired' })); } },
  { name: 'gate-invite', steps: async (p) => { await reach(p, { gate: 'invite' }); } },
  // The reviewer's question comes from the seeded application on the app and from A9.1's
  // `startAnswerNote` on the reference — the same words, pinned against the seed in test_docs.py.
  { name: 'gate-answer', steps: async (p) => { await reach(p, { gate: 'answer', persona: 'needsReview', note: NEEDS_REVIEW_INFO_REQUEST }); } },
  // A signed-in buyer deep-linking a route their access does not include. The only account-screen
  // state captured signed in, which is why the reference reaches it through `startScreen`.
  { name: 'gate-unavailable', steps: async (p) => { await reach(p, { gate: 'unavailable', persona: 'buyer' }); } },
  { name: 'gate-reapply', steps: async (p) => { await reach(p, { gate: 'apply', persona: 'declined' }); await fillDeclinedApplication(p); } },
  // The five outcomes that end on the sign-in card with a message (spec §3's notice slot). The
  // app performs the real flow — a verify link, a reset request, a reset, an accepted invitation,
  // a dead one — and the reference is handed the same words through `startNotice`.
  { name: 'gate-signin-verified', steps: async (p) => { await reach(p, { gate: 'signin', notice: 'verified' }); } },
  { name: 'gate-signin-reset-sent', steps: async (p) => { await reach(p, { gate: 'signin', notice: 'reset-sent' }); } },
  { name: 'gate-signin-password-updated', steps: async (p) => { await reach(p, { gate: 'signin', notice: 'password-updated' }); } },
  { name: 'gate-signin-invite-set', steps: async (p) => { await reach(p, { gate: 'signin', notice: 'invite-set' }); } },
  { name: 'gate-signin-invite-expired', steps: async (p) => { await provokes400(p, 'This invitation link is no longer valid. Ask the VIN Foundation for a new one.', () => reach(p, { gate: 'signin', notice: 'invite-expired' })); } },
  // ---------------------------------------------------------------------------------------
  // The empty dashboard (controller amendment A-SL17, John ~05:00 WITA 2026-09-09, verbatim
  // intent: "A real seller with zero listings should see the dashboard shell with no
  // invented/sample listings. Add the empty-dashboard state to the approved visual/DOM oracle.").
  //
  // APPENDED, never inserted: `screens.ts`'s order is the oracle's order and the manifest is
  // keyed by name, so a new state at the end is the one shape that moves no existing hash.
  //
  // The design has no empty-table treatment and none is invented: the shell with zero rows IS the
  // state, which is what that ruling says to capture. The reference is handed `[]` through
  // A16.11's `startMyListings`; the app is answered a real, EMPTY page by `reach`'s own route,
  // over the design's own four rows that `prepare()` answers every other state with (A-SL23 (2)).
  // ---------------------------------------------------------------------------------------
  { name: 'seller-dash-empty', steps: async (p) => { await reach(p, { screen: 'seller', myListings: [] }); } }
];
