import { test, expect, type BrowserContext, type Page } from '@playwright/test';
import { appOrigin, booted, click, expectApiStatus, firstMapPaintBudgetMs, listingsStubUrl, matchesListings, personaCredentials, personaSignIn, personaSignOut, prepare, reach, settleExpectedApiFailures, signInAs, signInAsPersona, waitMap, type PersonaCookies } from './harness';
import { designListingsBody } from './design-listings.mjs';
import { designBoundariesBody } from './design-boundaries.mjs';
import { FILL_LAYERS } from '../src/market/boundaries';
import { SCREENS } from './screens';

// `/reset?token=abc` (review fix round 1, Minor 8): the bare five paths above prove the routes
// render in a real browser; this one proves the same for a token-bearing URL — the gate frame
// renders without console errors. The token itself settling out of the address bar is proved
// at the composable level (useStateRouteSync.test.ts's A-S2 proofs), not re-asserted here.
const ROUTES = ['/', '/browse', '/browse?tab=market', '/browse?tab=listings', '/practices/p1', '/requests', '/seller', '/admin?tab=data', '/signup', '/forgot', '/verify', '/reset', '/accept-invite', '/reset?token=abc'];

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

  // A-I8: the account is loaded before the app mounts (`main.ts` → `useMe().load()`), so a
  // deep link into a member route is honoured by the SESSION — no gate click at all, where the
  // prototype's fixture button used to be the only way this URL survived a cold load. The
  // `?tab=market` is a legacy no-op kept deliberately: V3's Browse always shows market data.
  test('a deep link is honoured for a signed-in account, and a legacy ?tab= settles on Browse', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse?tab=market');
    await expect(page).toHaveURL(/\/browse$/);
    await expect(page.getByRole('button', { name: /^Layers/ })).toBeVisible();
  });

  // The design's OWN navigation — the header's four nav items, which only render once signed
  // in — rather than the prototype jump bar's six. A6.1 removes the bar; this proves the
  // routes are still written from the screens a member can actually reach.
  test('navigation writes the URL', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    await expect(page).toHaveURL(/\/browse$/);
    await page.getByRole('button', { name: 'My Requests', exact: true }).first().click();
    await expect(page).toHaveURL(/\/requests$/);
    await page.getByRole('button', { name: 'VIN Foundation Admin', exact: true }).first().click();
    await page.getByRole('button', { name: /^Data Sources\s*\d/ }).first().click();
    await expect(page).toHaveURL(/\/admin\?tab=data$/);
  });

  test('unknown routes redirect to /', async ({ page }) => {
    await page.goto('/definitely-not-a-route');
    await expect(page).toHaveURL(/\/$/);
  });

  // ---------------------------------------------------------------------------------------
  // Accessibility gate (John's ruling 2026-09-05, fix round 3 —
  // docs/decisions/2026-09-05-image-slot-editor-removed.md). The zero-gap audit measured 12
  // phantom tab stops on this screen: the design tool's Replace/Edit buttons inside each
  // <image-slot> shadow root, invisible (opacity:0) and mouse-inert (pointer-events:none)
  // but keyboard-focusable and named in the accessibility tree in every browser, because
  // the design's own `.ctl{display:flex}` beats the UA's closed-popover rule. The editor is
  // removed from the port; this is the repeatable end-to-end proof, in a real engine, that
  // it stays removed.
  //
  // Asserted twice over, because either alone could pass while the defect returned: the
  // structural half would miss an element focusable for some reason other than tabIndex, and
  // the behavioural half alone would not say WHICH node was reachable.
  // ---------------------------------------------------------------------------------------
  test('no element inside any image-slot shadow root is focusable on the Listing screen', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    await signInAs(page, 'design', '/practices/p1');
    await expect(page).toHaveURL(/\/practices\/p1$/);
    await page.locator('image-slot').first().waitFor();

    // The screen really does render the slots this test is about — otherwise an empty page
    // would pass it vacuously.
    const slots = await page.locator('image-slot').count();
    expect(slots, 'the Listing screen rendered no image-slot at all').toBeGreaterThan(0);

    // 1. Structural: nothing in any of those shadow roots is in the tab order, and none of
    //    the removed editor nodes is back under any name.
    const inside = await page.evaluate(() => {
      const out: { focusable: string[]; chrome: string[]; shadowChildren: number[] } = { focusable: [], chrome: [], shadowChildren: [] };
      for (const host of Array.from(document.querySelectorAll('image-slot'))) {
        const root = host.shadowRoot;
        if (!root) continue;
        out.shadowChildren.push(root.childNodes.length);
        for (const el of Array.from(root.querySelectorAll('*'))) {
          const name = el.tagName.toLowerCase() + (el.className ? '.' + el.className : '');
          if ((el as HTMLElement).tabIndex >= 0) out.focusable.push(name);
          if (el.matches('.spill, .ctl, [popover], input[type=file], button')) out.chrome.push(name);
        }
      }
      return out;
    });
    expect(inside.focusable, 'an image-slot shadow root contains a focusable element').toEqual([]);
    expect(inside.chrome, 'the design tool\'s editor chrome is back in the shadow root').toEqual([]);
    // style, .frame, .credit — the display-only tree, on every slot.
    expect(new Set(inside.shadowChildren)).toEqual(new Set([3]));

    // 2. Behavioural: walk the real tab order and confirm focus never enters one. 60 presses
    //    comfortably exceeds one full cycle of this screen (28 stops when the chrome was
    //    still there, 16 without it).
    //
    //    Round 4: the walk records EVERY landing, inside a slot or not, and asserts a
    //    positive as well as a negative. An emptiness assertion on its own is vacuous the
    //    moment the loop stops running — a changed sign-in flow, a renamed button, a focus
    //    trap, a Tab that goes nowhere would all leave `landedInside` empty and the gate
    //    green while proving nothing. `landedOutside` is the evidence that the keyboard walk
    //    happened at all, and that it actually moved rather than sticking on one element.
    await page.evaluate(() => document.body.focus());
    const landedInside: string[] = [];
    const landedOutside: string[] = [];
    for (let i = 0; i < 60; i++) {
      await page.keyboard.press('Tab');
      const at = await page.evaluate(() => {
        const deep = (d: Document | ShadowRoot): Element | null =>
          d.activeElement && d.activeElement.shadowRoot ? deep(d.activeElement.shadowRoot) : d.activeElement;
        const el = deep(document);
        if (!el || el === document.body) return null;   // focus left the page's own controls
        const root = el.getRootNode();
        const inSlot = root instanceof ShadowRoot && root.host?.tagName === 'IMAGE-SLOT';
        return { name: el.tagName.toLowerCase() + (el.className ? '.' + el.className : ''), inSlot };
      });
      if (!at) continue;
      (at.inSlot ? landedInside : landedOutside).push(at.name);
    }
    expect(landedOutside.length, 'the tab walk landed on nothing at all — the keyboard gate proved nothing').toBeGreaterThan(0);
    expect(new Set(landedOutside).size, 'the tab walk never moved — it landed on one element repeatedly').toBeGreaterThan(1);
    expect(landedInside, 'the tab order still reaches inside an image-slot shadow root').toEqual([]);
    expect(errors).toEqual([]);
  });

  // Performance gate (policy §3): the market map's first paint. The clock starts on the
  // NAVIGATION, so the budget covers everything a member pays for on a cold deep link —
  // `main.ts`'s `/api/config` + `/api/me` (A-I8), the app's own boot, A5.4's bootstrap, the
  // pending deep link and Leaflet's first paint. The session is established out of band
  // beforehand, so the sign-in itself is not on the clock — the same as when a real member
  // arrives with a cookie. The `?tab=market` is a legacy no-op kept here deliberately: V3's
  // Browse always shows market data. `[data-map]` is set by LeafletMapEngine.mount() once the
  // map is on the page.
  //
  // Controller ruling 2026-09-08: `firstMapPaintBudgetMs` (harness.ts) is 1500ms against a local
  // target and 3000ms against a remote one (`PW_APP_URL` set) — a bare 1500ms hard-coded here
  // measures the network on a remote run, not the app: the same test failed twice against QA at
  // 1842ms (Indonesia to a US region) while everything else passed.
  test('first map paint within budget', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design');                     // the cookie only; the clock starts below
    const started = Date.now();
    await page.goto('/browse?tab=market');
    await page.locator('[data-map]').waitFor();
    const elapsed = Date.now() - started;
    const budget = firstMapPaintBudgetMs();
    const target = process.env.PW_APP_URL ? 'remote' : 'local';
    expect(elapsed, `first map paint took ${elapsed}ms, over the ${target} budget of ${budget}ms`).toBeLessThanOrEqual(budget);
  });

  // A4 (spec D21, John: "if user clicks + Compare that action closes the 'What this means'
  // card, and when X Compare is clicked it closes the compare and the card appears again").
  // At 1440×940 (this project's default viewport) the floating interpretation card's own
  // dismiss button — `button[aria-label="Dismiss interpretation"]`, unique to that card, since
  // the docked panel's own "What this means" heading carries no such button — disappears while
  // Compare is open and returns when the same toggle (whose note reads "close" while open) is
  // clicked again.
  test('opening Compare hides the floating "What this means" card; closing Compare brings it back (A4, spec D21)', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    const dismiss = page.locator('button[aria-label="Dismiss interpretation"]');
    await expect(dismiss).toBeVisible();
    await click(page, 'Compare');
    await expect(dismiss).toHaveCount(0);
    await click(page, 'Compare');
    await expect(dismiss).toBeVisible();
  });
});

// ---------------------------------------------------------------------------------------
// Mobile acceptance (README Task 9, verbatim): "at the prototype's mobile frame (390×800)
// the Map tab shows choropleth shading; the key does not overlap the `+` / `−` cluster
// (`document.elementFromPoint` on each button returns the button); the sheet opens
// full-height and scrolls; every one of the five sections renders; tapping a pin twice
// reaches the detail screen."
//
// And the tap-target rule (C13, verbatim): "every row in the sheet is `min-height: 46px`,
// the basemap buttons are 46px, and the close button is a 44×44 hit area around a 16px
// glyph. Nothing in the sheet is under 44px."
// ---------------------------------------------------------------------------------------
test.describe('mobile: the same map, market data in a sheet', () => {
  // Fix round 1, nit 5: scoped to the prototype's own 390×800 phone frame (App.vue:1242).
  // `z-index: 700` alone is NOT unique in App.vue — the desktop "More filters" popover
  // (App.vue:237) carries it too. That popover is not in the DOM while the mobile frame is
  // showing, so the bare selector is unambiguous today; scoping it means a future state that
  // renders both fails readably here instead of as a strict-mode violation everywhere.
  const PHONE = 'div[style*="width: 390px"][style*="height: 800px"]';
  const SHEET = 'div[style*="z-index: 700"]';
  const phone = (page: Page) => page.locator(PHONE);
  const sheet = (page: Page) => phone(page).locator(SHEET);
  /** The one navy Market data button, addressed by its dataset-count pill. */
  const dataButton = (page: Page) => phone(page).locator('button', { hasText: /of \d/ });

  async function openSheet(page: Page) {
    await dataButton(page).click();
    await expect(sheet(page)).toBeVisible();
  }

  // D-I8-7: the phone frame is asked for through the URL now — the "Mobile view" toggle lived
  // in the jump bar and left with it (A6.1). The harness viewport stays the design's 1440×940;
  // 390×800 is the PROTOTYPE's frame drawn inside that page.
  async function mobileMap(page: Page) {
    await prepare(page);
    await signInAs(page, 'design', '/browse?viewport=mobile');
    await click(page, 'Map');
    await waitMap(page);
  }

  test('the Map tab renders the market map inside the 390-wide phone frame', async ({ page }) => {
    await mobileMap(page);
    const box = (await page.locator('.leaflet-container').first().boundingBox())!;
    expect(Math.round(box.width), 'the map is not inside the prototype\'s 390px mobile frame').toBeGreaterThanOrEqual(380);
    expect(Math.round(box.width)).toBeLessThanOrEqual(392);
  });

  test('the Map tab shows community boundary shading', async ({ page }) => {
    await mobileMap(page);
    // The polygons are drawn on the engine's shared L.canvas renderer (A24.12 passes it to
    // L.geoJSON exactly as the mosaic passed it to L.rectangle), so "shading is showing"
    // means that canvas has painted pixels. Nothing is drawn from a cross-origin image, so
    // the canvas is untainted and readable.
    const painted = await page.evaluate(() => {
      const c = document.querySelector('.leaflet-overlay-pane canvas') as HTMLCanvasElement | null;
      if (!c) return -1;
      const px = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 3; i < px.length; i += 4) if (px[i] > 0) n++;
      return n;
    });
    expect(painted, 'no canvas in the Leaflet overlay pane — the boundary layer never drew').toBeGreaterThan(0);
  });

  test('the key does not overlap the + / − cluster: elementFromPoint on each button returns the button', async ({ page }) => {
    await mobileMap(page);
    for (const label of ['Zoom in', 'Zoom out']) {
      const btnLoc = page.getByRole('button', { name: label, exact: true });
      const box = (await btnLoc.boundingBox())!;
      const hit = await page.evaluate(([x, y, name]) => {
        const el = document.elementFromPoint(x as number, y as number);
        const target = document.querySelector(`button[aria-label="${name}"]`);
        return { same: el === target, contained: !!target && !!el && target.contains(el), got: el ? el.tagName + (el.getAttribute('aria-label') ?? '') : 'null' };
      }, [box.x + box.width / 2, box.y + box.height / 2, label] as const);
      expect(hit.same || hit.contained, `something covers the "${label}" button — elementFromPoint returned ${hit.got}`).toBe(true);
    }
  });

  test('one navy Market data button opens a full-height sheet that scrolls', async ({ page }) => {
    await mobileMap(page);
    const mapBox = (await page.locator('.leaflet-container').first().boundingBox())!;

    // Fix round 1, minor 3: "ONE navy Market data button" is the C13 wording, so assert the
    // count rather than reaching for `.last()` of however many there are, and assert the
    // colour the design gives it (`var(--vf-navy)` → #003a70) rather than only its text.
    await expect(dataButton(page), 'C13 gives the phone exactly one Market data button').toHaveCount(1);
    const navy = await dataButton(page).evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(navy, 'the Market data button is not the design\'s navy').toBe('rgb(0, 58, 112)');
    const buttonBox = (await dataButton(page).boundingBox())!;
    expect(Math.round(buttonBox.height), 'the Market data button is not 44px tall').toBe(44);

    await openSheet(page);
    const sheetBox = (await sheet(page).boundingBox())!;
    expect(Math.round(sheetBox.width)).toBe(Math.round(mapBox.width));
    expect(Math.round(sheetBox.height)).toBe(Math.round(mapBox.height));

    const scrolls = await sheet(page).locator('.rf-scroll').evaluate((el) => el.scrollHeight > el.clientHeight);
    expect(scrolls, 'the sheet body does not scroll — it cannot be carrying all five sections').toBe(true);
  });

  test('every one of the five sections renders, in order', async ({ page }) => {
    await mobileMap(page);
    await openSheet(page);
    const text = await sheet(page).innerText();
    // innerText is the RENDERED text, and rendered is what "renders" has to mean here: a
    // display:none section would drop out of it entirely. V3 sets `text-transform:
    // uppercase` on all four of the sheet's micro-labels and on the footer button (Global
    // Constraint (f): V3 preserves and EXTENDS micro-label uppercase while dropping it from
    // display headings), so the strings that reach the screen are SHADING, COMPARE AGAINST,
    // DATASETS, BASEMAP and SHOW MAP, while the "What this means" display heading is not
    // transformed. They are matched here exactly as they render, which pins that styling as
    // well as the section order. Confirmed character-for-character identical on the V3
    // reference (`PW_APP_URL=http://localhost:5174`): reference and app return the same
    // innerText for this sheet, so the case is the design's, not the port's.
    const order = ['SHADING', 'COMPARE AGAINST', 'DATASETS', 'What this means', 'BASEMAP'];
    let at = -1;
    for (const section of order) {
      const next = text.indexOf(section);
      expect(next, `the sheet does not render the "${section}" section`).toBeGreaterThan(-1);
      expect(next, `"${section}" is out of order in the sheet`).toBeGreaterThan(at);
      at = next;
    }
    expect(text).toContain('Why it matters');
    expect(text).toContain('SHOW MAP');

    // Fix round 1, minor 1: bullet 2 of C13's six-item list — "ramp + source/updated" — was
    // asserted nowhere, and the source line is the attribution CLAUDE.md marks legally load
    // bearing ("Source: U.S. Census Bureau, …" under Community Context). It sits between the
    // Shading rows and Compare against, which is where the design puts it
    // (Practice Match V3.dc.html:1417-1424).
    const ramp = text.indexOf('< $50K');            // the first class of the default income ramp
    const source = text.indexOf('Source:');
    const updated = text.indexOf('Updated:');
    expect(ramp, 'the sheet renders no ramp under the Shading rows').toBeGreaterThan(text.indexOf('SHADING'));
    expect(source, 'the sheet renders no "Source:" attribution line').toBeGreaterThan(ramp);
    expect(updated, 'the sheet renders no "Updated:" line').toBeGreaterThan(source);
    expect(updated, 'the ramp + source/updated block is not between Shading and Compare against')
      .toBeLessThan(text.indexOf('COMPARE AGAINST'));
    // A24.36 (fix round 1, Important 2): income shades at the CENSUS TRACT and its source line
    // said "community level" — the one line on this card that named no geography while the line
    // above it named the tract.
    expect(text).toContain('Source: U.S. Census ACS 5-year estimates (2023) · Census tract');
  });

  test('every tap target in the sheet is at least 44px', async ({ page }) => {
    await mobileMap(page);
    await openSheet(page);
    const sizes = await sheet(page).locator('button').evaluateAll((els) =>
      els.map((el) => { const r = el.getBoundingClientRect(); return { label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40), w: r.width, h: r.height }; })
    );
    expect(sizes.length, 'the sheet rendered no buttons at all').toBeGreaterThan(5);
    const small = sizes.filter((s) => s.h < 44 || s.w < 44);
    expect(small, 'these sheet tap targets are under 44px').toEqual([]);

    const close = (await page.getByRole('button', { name: 'Close market data' }).boundingBox())!;
    expect(Math.round(close.width)).toBe(44);
    expect(Math.round(close.height)).toBe(44);
    const glyph = (await page.getByRole('button', { name: 'Close market data' }).locator('img').boundingBox())!;
    expect(Math.round(glyph.width)).toBe(16);
    expect(Math.round(glyph.height)).toBe(16);
  });

  // Fix round 1, minor 2. The >= 44px rule above is real, but it passes on padding alone:
  // setting `rowStyle`/`datasetRowStyle` to `min-height: 1px` leaves it green, because 24px of
  // padding plus 22px of row content already clears 44. C13's stated means — "option and
  // dataset rows `min-height: 46px`, basemap buttons 46px" — was therefore verified only by
  // reading logic.js. Asserted here from the COMPUTED style, so the rule survives a change to
  // how the value is written.
  test('the sheet rows carry the design\'s 46px minimums, not merely enough padding', async ({ page }) => {
    await mobileMap(page);
    await openSheet(page);
    const rows = await sheet(page).locator('button').evaluateAll((els) =>
      els.map((el) => ({
        role: el.getAttribute('role'),
        label: (el.getAttribute('aria-label') || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 32),
        minHeight: parseFloat(getComputedStyle(el).minHeight) || 0,
        height: el.getBoundingClientRect().height
      }))
    );
    // Shading (7) + Compare against (6) are the design's role="option" rows; the Datasets rows
    // are the only other buttons the design gives a min-height to (`mob.datasetRowStyle`).
    const options = rows.filter((r) => r.role === 'option');
    const datasets = rows.filter((r) => !r.role && r.minHeight > 0);
    expect(options.length, 'the Shading + Compare against option rows').toBe(13);
    expect(datasets.length, 'the Datasets rows').toBe(6);
    for (const r of [...options, ...datasets]) {
      expect(r.minHeight, `"${r.label}" computes to min-height ${r.minHeight}px, under the design's 46px`).toBeGreaterThanOrEqual(46);
    }
    const basemaps = rows.filter((r) => r.label === 'Map' || r.label === 'Satellite');
    expect(basemaps.length, 'the Basemap section\'s two buttons').toBe(2);
    for (const b of basemaps) {
      expect(Math.round(b.height), `the "${b.label}" basemap button is ${b.height}px, not the design's 46px`).toBe(46);
    }
  });

  // Fix round 1, minor 4. C13's whole point: the mobile mount omits `on-basemap`
  // (Practice Match V3.dc.html:1359 vs the desktop's :324), so the map's 132px Map|Satellite
  // cluster cannot fight a full-width key on a 388px map — the SHEET owns basemap switching
  // instead. That was gated only by `mobile-map` at zero tolerance, which names the failure as
  // a pixel diff; this names it in words, on both sides of the contrast.
  test('the phone has no basemap tabs on the map — the sheet owns basemap switching', async ({ page }) => {
    await mobileMap(page);
    const tabs = page.getByRole('button', { name: 'Satellite', exact: true });
    await expect(tabs, 'a Map|Satellite tab pair leaked onto the phone map — on-basemap reached the mobile mount').toHaveCount(0);
    await openSheet(page);
    await expect(sheet(page).getByRole('button', { name: 'Satellite', exact: true }), 'the sheet does not own basemap switching').toHaveCount(1);
  });

  test('the desktop map keeps the basemap tabs the phone gives up', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await expect(page.getByRole('button', { name: 'Satellite', exact: true }), 'the desktop map lost its basemap tabs').toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Map', exact: true }), 'the desktop map lost its basemap tabs').toHaveCount(1);
  });

  // Review I1 (controller ruling, 2026-09-07): redraw-after-selection, MEASURED. What this
  // suite profiled before was mount only ('first map paint within budget' above); nothing
  // timed the interaction the design exercises most on the phone — tap a pin, tap another.
  //
  // A selection moves `driveCenter` (`sel ? [sel.lat, sel.lng] : cfg.center`, logic.js:382)
  // and `showDrive` (`!!sel`, :578), which are two of the five deps of MarketMapV3.jsx's own
  // area effect (`:268`), so the polygon layer really is rebuilt on the second tap. That
  // is the DESIGN's redraw cost on a 390×800 frame, not an over-trigger the port added:
  // MarketMapView.vue gates the overlay rebuild on exactly those five. The first tap is an
  // unmeasured warm-up, and it is a DIFFERENT pin from the second — tapping the same pin
  // twice navigates to the detail screen (C13), which is the case above, not this one.
  // The budget is the first-paint gate's 1500 ms, in the same spirit.
  test('a second pin tap repaints the map within budget', async ({ page }) => {
    await mobileMap(page);
    const pins = page.locator('.leaflet-marker-icon');
    await expect(pins.nth(1)).toBeVisible();
    // Leaflet writes each marker's `title` from `p.name + ' — ' + p.priceLabel`
    // (MarketMapView.vue's drawPins), so the callout to wait for can be named from the page
    // rather than from a copy of the fixture.
    const nameB = (await pins.nth(1).getAttribute('title'))!.split(' — ')[0];

    await pins.nth(0).click();
    await page.waitForTimeout(500);

    const started = Date.now();
    await pins.nth(1).click();
    await page.waitForFunction(
      (n) => [...document.querySelectorAll('.rf-callout')].some((el) => (el as HTMLElement).innerText.includes(n)),
      nameB
    );
    const elapsed = Date.now() - started;
    expect(elapsed, `the second pin tap took ${elapsed}ms to bring up "${nameB}"'s callout`).toBeLessThanOrEqual(1500);
  });

  test('tapping a pin twice reaches the detail screen — there is no peek card', async ({ page }) => {
    await mobileMap(page);
    const pin = page.locator('.leaflet-marker-icon').first();
    await pin.click();
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(/\/browse$/);              // first tap selects, it does not navigate
    await page.locator('.leaflet-marker-icon').first().click();
    // Either id shape (final review I2): locally the D6 stub serves the design's own fixtures, so
    // the route is `/practices/p3`; on a seeded target (`PW_APP_URL`, the QA parity run this spec
    // is deliberately kept in) the listing's id is a uuid and the route is `/practices/<uuid>`.
    // What is being proved is the NAVIGATION, not which practice the pin happened to be.
    await expect(page).toHaveURL(/\/practices\/[A-Za-z0-9-]+$/);
  });

  // A2 (spec D17, John: "resolve this"). Root cause (systematic-debugging, task V14 report):
  // the mobile results card's `open` set `browseSel`, which nothing has read since C13
  // removed the peek card it used to open — the tap was a no-op, unlike every other route
  // to the detail screen (a desktop card, a request row, a second pin tap). `open` now
  // navigates directly, the same way V2's card and C13's second pin tap both do.
  test('tapping the first result card in the list reaches the detail screen (A2)', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse?viewport=mobile');
    await phone(page).getByText('Revenue', { exact: false }).first().waitFor();

    const card = phone(page).locator('div[style*="cursor: pointer"]').filter({ hasText: 'Revenue' }).first();
    const area = (await card.locator('div[style*="font-size: 15px"]').innerText()).trim();

    await card.click();
    // Either id shape (final review I2) — see the comment on the second-pin-tap case above.
    await expect(page).toHaveURL(/\/practices\/[A-Za-z0-9-]+$/);
    await expect(page.getByText('Exterior photo').first()).toBeVisible();
    await expect(phone(page).getByText(area, { exact: false }).first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------------------
// Fix round 1, nit 7: a permanent guard for `atTop`.
//
// The Linux flake it fixes (interest-modal, 23,441 px on the vin-swe runner) cannot be
// reproduced on darwin by running the suite — the app's one position:fixed element only
// drifts when the page happens to be scrolled at capture time, and darwin never scrolls it.
// So deleting `atTop(p, MODAL)` from screens.ts would fail nothing here and silently re-open
// the flake on the runner that has it.
//
// This case forces the runner's behaviour instead of waiting for it: an init script scrolls
// the page 5px on EVERY click, which is exactly what Playwright's scroll-into-view does on
// Linux when the taller listing page pushes "I'm interested" past the fold. It then drives
// the real `SCREENS` step — not a copy of it — and asserts the page is back at the top with
// the overlay's box settled, which is the state the fullPage capture needs. Remove the
// `atTop` call and this fails on every platform.
// ---------------------------------------------------------------------------------------
test.describe('harness: atTop pins the interest modal against a scrolled capture', () => {
  test('the interest-modal step ends at scrollY 0 with the overlay settled, even when every click scrolls', async ({ page }) => {
    await prepare(page);
    // Capture phase, so it lands before the app's own handler and before Playwright's next
    // action — the same ordering a real scroll-into-view has.
    await page.addInitScript(() => document.addEventListener('click', () => window.scrollTo(0, 5), true));
    await booted(page);

    const step = SCREENS.find((s) => s.name === 'interest-modal');
    expect(step, 'there is no interest-modal state left to guard').toBeTruthy();
    await step!.steps(page);

    const settled = await page.evaluate(() =>
      new Promise<{ scrollY: number; overlays: number; stable: boolean }>((resolve) => {
        const el = document.querySelector('div[style*="z-index: 900"]');
        if (!el) return resolve({ scrollY: window.scrollY, overlays: 0, stable: false });
        const a = el.getBoundingClientRect();
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            const b = el.getBoundingClientRect();
            resolve({ scrollY: window.scrollY, overlays: 1, stable: a.top === b.top && a.left === b.left && a.height === b.height });
          })
        );
      })
    );
    expect(settled.overlays, 'the interest modal never opened, so this guard proved nothing').toBe(1);
    expect(
      settled.scrollY,
      'the interest-modal step left the page scrolled: its atTop() call is missing, so the modal\'s position:fixed overlay will be composited off-origin in the fullPage capture — the vin-swe Linux flake, back'
    ).toBe(0);
    expect(settled.stable, 'the overlay is still moving at the moment the capture would be taken').toBe(true);
  });
});

// ---------------------------------------------------------------------------------------
// Fix round 1 (A-LB2), Important finding 1: a permanent guard for atTop's OWN-CONTAINER pin.
//
// `browse-panel-lightbox` (task L2 review) flaked once under full-suite load with a ~5 %-pixel
// diff localized entirely BELOW the docked panel's "Practice detail" header — the lightbox
// photograph itself was pixel-identical. Root cause: the docked panel's own `.rf-scroll`
// container (App.vue:630, `v.md?.hasSel`) is independently scrollable, and Playwright's
// click-actionability can scroll it into place before clicking the photo tile's transparent
// hit-target — exactly the same class of bug `atTop` was written for the PAGE scroll, one level
// deeper. `atTop()` pinned only `window.scrollY` before this fix; nothing reset the panel's own
// `scrollTop`.
//
// This case forces the runner's own click-actionability scroll instead of hoping to reproduce
// it under contention: an init script sets every `.rf-scroll` container's `scrollTop` to a
// nonzero value on every click (capture phase, before the app's own handlers and before
// Playwright's next action — the same ordering a real scroll-into-view has), then drives the
// real `browse-panel-lightbox` step — not a copy of it — and asserts every `.rf-scroll`
// container left in the DOM is back at `scrollTop` 0 once the step's own `atTop()` call returns.
// Remove atTop's container-pinning and this fails on every platform, not only under contention.
// ---------------------------------------------------------------------------------------
test.describe('harness: atTop pins the docked panel\'s own scroll', () => {
  test('the browse-panel-lightbox step ends with every .rf-scroll container at scrollTop 0, even when every click scrolls them', async ({ page }) => {
    await prepare(page);
    await page.addInitScript(() =>
      document.addEventListener(
        'click',
        () => document.querySelectorAll('.rf-scroll').forEach((el) => { (el as HTMLElement).scrollTop = 40; }),
        true
      )
    );
    await booted(page);

    const step = SCREENS.find((s) => s.name === 'browse-panel-lightbox');
    expect(step, 'there is no browse-panel-lightbox state left to guard').toBeTruthy();
    await step!.steps(page);

    const offsets = await page.evaluate(() =>
      Array.from(document.querySelectorAll('.rf-scroll')).map((el) => (el as HTMLElement).scrollTop)
    );
    expect(offsets.length, 'no .rf-scroll container was mounted, so this guard proved nothing').toBeGreaterThan(0);
    expect(
      offsets.every((n) => n === 0),
      'a docked panel .rf-scroll container is not at scrollTop 0: atTop() is not pinning the panel\'s own scroll, so content painted beneath the fixed lightbox scrim will differ across runs — the browse-panel-lightbox flake, back'
    ).toBe(true);
  });
});

// ---------------------------------------------------------------------------------------
// Fix round 2 (A-LB3), item 4: the Tab-cycling confirmation Step 10 asked for, and fix round 1
// refused to write against the broken `focusout` trap, is now the gate the ruling requires.
//
// A-LB3 replaced the trap with deterministic handling in the shared `keydown` closure (A19.9):
// on Tab with the dialog open, read the dialog's controls in DOM order (Close photo, Previous
// photo, Next photo — the container is `tabindex="-1"` and never in the cycle itself); on the
// last, wrap to the first; on Shift+Tab on the first (or on the container, which is where the
// mount-ref idiom leaves focus right after opening), wrap to the last. One `keydown` handler,
// synchronous, no `setTimeout`, no `relatedTarget` ambiguity.
//
// Reached through Round Rock (3 photographs, so Previous/Next both render) via the same click
// sequence `detail-lightbox` uses. Every assertion below is a single `Tab`/`Shift+Tab` keypress
// checked immediately after — no retry, no wait beyond Playwright's own actionability — because
// the fix is synchronous: nothing here is deferred to a macrotask the way the old trap was.
// ---------------------------------------------------------------------------------------
test.describe('A19 — the photo lightbox: the Tab trap holds (fix round 2, A-LB3)', () => {
  test('Tab from the last control returns to the first, Shift+Tab from the first returns to the last, and a full cycle in both directions never leaves the dialog', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await page.getByText('Round Rock').first().click();
    await click(page, 'View full listing');
    await page.getByRole('button', { name: 'Expand photo: Exterior — street view' }).click();
    const dialog = page.getByRole('dialog', { name: 'Photograph 1 of 3' });
    await dialog.waitFor({ state: 'visible' });

    const closeBtn = page.getByRole('button', { name: 'Close photo' });
    const prevBtn = page.getByRole('button', { name: 'Previous photo' });
    const nextBtn = page.getByRole('button', { name: 'Next photo' });

    // Opening focuses the dialog itself (the mount-ref idiom, A19.2) — the container case Shift+Tab
    // must also wrap from.
    await expect(dialog).toBeFocused();

    // A full forward cycle: dialog -> Close -> Previous -> Next -> (wrap) -> Close, asserted at
    // every step so a mid-cycle escape (the old defect) cannot hide behind a later correction.
    await page.keyboard.press('Tab');
    await expect(closeBtn, 'Tab from the dialog must reach the first control').toBeFocused();
    await page.keyboard.press('Tab');
    await expect(prevBtn).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(nextBtn).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(closeBtn, 'Tab from the last control (Next) must return to the first (Close), on this one keypress').toBeFocused();

    // A full backward cycle from there: Close -> (wrap) -> Next -> Previous -> Close.
    await page.keyboard.press('Shift+Tab');
    await expect(nextBtn, 'Shift+Tab from the first control (Close) must return to the last (Next), on this one keypress').toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await expect(prevBtn).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await expect(closeBtn).toBeFocused();

    // The container case: reopen (closing and reopening returns focus to the dialog itself, not
    // to a control), then Shift+Tab immediately — must wrap to the last control directly, not
    // bounce on the container the way the removed trap did.
    await closeBtn.click();
    await page.getByRole('button', { name: 'Expand photo: Exterior — street view' }).click();
    await dialog.waitFor({ state: 'visible' });
    await expect(dialog).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await expect(nextBtn, 'Shift+Tab from the container itself must reach the last control').toBeFocused();
  });
});

// ---------------------------------------------------------------------------------------
// Amendment A-I7 — the proof that the harness sign-in reaches the REAL API. No stub and no
// mock: `tests/targets.ts`'s `api` web server migrated the local Postgres, seeded the design
// persona and is serving `app.main:app`, and Vite proxies `/api` to it with the Host header
// intact. Three things are exercised here that nothing else in the suite touches — the
// proxy, a `Secure` session cookie accepted over `http://localhost` (a trustworthy origin in
// Chromium), and the Redis-cached principal behind `GET /api/me` — in a real browser.
//
// It asserts the SESSION, not the rendered screen — the screens are proved by visual.spec.ts
// and dom.spec.ts, which now enter through it (`reach`). A-I8 executed the order this note
// recorded: the sign-in existed and was proven here (I7), then `main.ts`'s `useMe().load()`
// bootstrap made the app honour it and `screens.ts` switched off `jump()` (I8a commit 1), then
// the jump bar went (I8a commit 3).
// ---------------------------------------------------------------------------------------
test.describe('harness: the design persona signs in against the real API (A-I7)', () => {
  test('signInAsPersona leaves pm_session and pm_csrf on the context and /api/me answers the persona', async ({ page }) => {
    await prepare(page);
    await signInAsPersona(page);

    const cookies = await page.context().cookies();
    const session = cookies.find((c) => c.name === 'pm_session');
    const csrf = cookies.find((c) => c.name === 'pm_csrf');
    expect(session, 'no pm_session cookie — the sign-in never reached the API through Vite\'s /api proxy').toBeTruthy();
    expect(session!.httpOnly, 'pm_session must stay HttpOnly: script must never be able to read it').toBe(true);
    expect(csrf, 'no pm_csrf cookie — the app cannot echo the double-submit value in X-CSRF-Token').toBeTruthy();
    expect(csrf!.httpOnly, 'pm_csrf is deliberately readable by script (app/api/auth.py:147)').toBe(false);

    const me = await page.evaluate(() =>
      fetch('/api/me', { credentials: 'same-origin' }).then((r) => r.json() as Promise<{ email: string; roles: string[] }>)
    );
    expect(me.email).toBe('design@practice-match.test');
    expect(me.roles).toEqual(['admin', 'buyer', 'seller', 'staff']);
  });
});

// ---------------------------------------------------------------------------------------
// The STATE-CHANGING half of the proxy proof (A-I7.2, review Important 2). Everything in the
// test above is exempt from `deps.check_origin_and_csrf` — sign-in has no session yet and GET is
// never checked — so none of it can catch the proxy rewriting the Host header. This can:
// `POST /api/auth/reauth` is a cookie-session state change, so the API compares the browser's
// `Origin` (http://localhost:5173) against `settings.origins` (empty on the api web server) plus
// `str(request.url)`, which is built from the HOST header. It answers 200 only while Vite
// preserves it; with `changeOrigin: true` the API sees http://localhost:8017 and refuses 403
// ORIGIN. It also exercises the double-submit the app itself will use: `pm_csrf` read from
// `document.cookie` by script, exactly as `src/auth/api.ts`'s `csrfToken()` does.
//
// In its OWN session, and signed out again in `finally` (re-review). `sessions.set_reauth`
// stamps `session.reauth_at` for `deps.REAUTH_WINDOW` (10 minutes), and the memoised persona
// session is shared by every other test in the worker — leaving THAT one re-authenticated would
// let an I8 test asserting a REAUTH-gated action DEMANDS a step-up pass vacuously. It costs one
// extra `SIGNIN_IP` attempt per run out of thirty, and `POST /api/auth/reauth` has no limiter.
// ---------------------------------------------------------------------------------------
test.describe('harness: the /api proxy preserves the Host header (A-I7.2)', () => {
  test('POST /api/auth/reauth from the page is accepted, in a session of its own', async ({ browser }) => {
    test.skip(!!process.env.PW_APP_URL, 'this proves Vite\'s /api proxy; a live deployment serves /api itself');

    // Both the session and the context are created INSIDE the guarded region (re-review 2): with
    // `personaSignIn()` outside it, a `browser.newContext()` that threw left a live session with
    // nothing to sign it out, and its ten-minute step-up window outlived the run.
    let cookies: PersonaCookies | undefined;
    let context: BrowserContext | undefined;
    let signOutStatus: number | undefined;
    try {
      cookies = await personaSignIn();
      context = await browser.newContext({ baseURL: appOrigin() });
      await context.addCookies(cookies);
      const page = await context.newPage();
      await prepare(page);
      await page.goto('/');

      const reauth = await page.evaluate(async (password) => {
        const match = /(?:^|;\s*)pm_csrf=([^;]*)/.exec(document.cookie);
        const response = await fetch('/api/auth/reauth', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(match ? match[1] : '') },
          body: JSON.stringify({ password })
        });
        return { csrfWasReadable: !!match, status: response.status, body: (await response.json()) as { status?: string; error?: { code?: string } } };
      }, personaCredentials().password);

      expect(reauth.csrfWasReadable, 'script could not read pm_csrf, so the app cannot echo the double-submit value').toBe(true);
      expect(
        reauth.status,
        `POST /api/auth/reauth answered ${reauth.status} (${reauth.body.error?.code ?? 'no code'}) instead of 200. ` +
        'An ORIGIN refusal here means Vite is rewriting the Host header — a `changeOrigin` on the ' +
        '/api proxy — so deps.check_origin_and_csrf builds a different origin than the browser sent.'
      ).toBe(200);
      expect(reauth.body.status).toBe('reauthenticated');

      // The cleanup is PROVEN, not hoped for: a `personaSignOut` that silently did nothing would
      // leave this session's step-up window standing and this test would still have passed. The
      // API answers 200 only after `sessions.revoke` has committed and dropped the cache entry.
      //
      // Checked from OUTSIDE the browser deliberately: asking the page for /api/me afterwards
      // would log "Failed to load resource: … 401 (Unauthorized)" as a console error, which
      // `prepare()`'s gate turns into a failure — a real 401 is the expected answer here.
      //
      // Asserted HERE rather than in the `finally`: an `expect` that threw from a `finally` would
      // replace whatever failed above it, so a broken reauth would be reported as a broken
      // sign-out.
      signOutStatus = await personaSignOut(cookies);
      expect(signOutStatus, 'personaSignOut did not end the session, so its 10-minute step-up window outlives this test').toBe(200);
    } finally {
      if (context) await context.close();
      // The safety net: whatever failed above — including `browser.newContext()` itself — the
      // session must not outlive this test. `signOutStatus` is set only by the happy path above,
      // so this neither repeats it nor masks its failure.
      if (cookies && signOutStatus === undefined) await personaSignOut(cookies);
    }
  });
});

// ---------------------------------------------------------------------------------------
// Task B10, A-C31 (4) — "The test that proves it is an end-to-end one, not a unit test. A unit
// test may accompany it; it may not replace it."
//
// Every unit test in this repository was green while the docked panel read "0" Population,
// "0.0% (5 yrs)", "$0K" Median Income, "0" Est. Pet Households and a "Flat" growth verdict for
// a listing the Census has no figures for. Nothing could see it: no unit test ever RENDERED the
// panel against such a listing, and the pixel oracle only ever sees the design's own fixtures,
// every one of which HAS figures. This does — the real app, in a real browser, through the
// design's own card click.
//
// It answers `/api/listings` with the design's OWN twenty-one practices and their six community
// fields NULLED, which is exactly the row `app/api/listings.py::serialise` serves for a listing
// `market_metric` has nothing for. Registering a route over `prepare()`'s D6 stub is the
// harness's own sanctioned pattern — `seller-dash-empty` does it, and Playwright matches the
// LAST registered handler first.
//
// WHY NOT THE REAL API, which is where the brief expected this to live. `listing-flows.spec.ts`
// runs the real one against the real database, and it cannot host this test today: a published
// listing with NO COORDINATES freezes the whole Browse screen. `serialise` nulls `lat`/`lng` for
// a listing whose seller has not disclosed the location (Wave 2b's default) and for one the
// geocoder could not place; `md.practices` carries the nulls; `MarketMapView` calls
// `engine.marker([null, null])`; Leaflet's `toLatLng([null, null])` returns `null` (its array
// branch is guarded by `typeof a[0] !== "object"`, and `typeof null === "object"`) and it then
// reads `.lat` off that null. The throw escapes Vue's post-flush queue and NOTHING renders
// afterwards — measured: after it, a results-card click and a Compare click both change no DOM
// at all. That defect is real, it is not Task B10's, and it is reported to the controller rather
// than fixed here or written a test against.
// ---------------------------------------------------------------------------------------
test.describe('Task B10 — the docked panel renders nothing where the Census has nothing (D-C31/D-C32)', () => {
  const BANNED = ['undefined', 'NaN', '$0K', '0.0%', 'Flat', 'Lean', 'Median', 'Challenging'];

  /** The design catalogue as `GET /api/listings` serves it, with `over` applied to every row. */
  async function serveListings(page: Page, over: Record<string, unknown>): Promise<void> {
    const stub = listingsStubUrl();
    expect(stub, 'this test overrides the D6 stub, and a live target has none to override').not.toBeNull();
    const body = JSON.parse(designListingsBody()) as { items: Record<string, unknown>[]; next_cursor: null };
    for (const item of body.items) Object.assign(item, over);
    await page.route(
      (url) => matchesListings(url.href, stub as string),
      (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    );
  }

  const NO_FIGURES = { pop: null, growth: null, income: null, hh: null, vets: null, econ_k: null, community_label: null, growth_scope: null, income_note: null };

  /** Cedar Park's docked panel, opened the way `browse-market-panel` opens it: a card click. */
  async function openPanel(page: Page) {
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await page.getByText('Cedar Park').first().click();
    const panel = page.locator('div.rf-scroll[style*="width: 366px"]');
    await panel.getByRole('button', { name: 'View full listing' }).waitFor({ state: 'visible' });
    return panel;
  }

  test('no figure, no zero, no verdict and no bars — and the design\'s own unavailable card instead', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    await serveListings(page, NO_FIGURES);
    const panel = await openPanel(page);

    const text = (await panel.innerText()).replace(/\s+/g, ' ');
    for (const banned of BANNED) {
      expect(text, `the docked panel renders "${banned}" for a listing with no community figures`)
        .not.toContain(banned);
    }
    // A bar drawn at its floor is a reading, not an absence: the competition row and the score
    // ring are not in the DOM at all, and neither are the four overview tiles.
    await expect(panel.getByText('Veterinary Establishments')).toHaveCount(0);
    await expect(panel.getByText('per 10k households')).toHaveCount(0);
    await expect(panel.getByText('Overall Score')).toHaveCount(0);
    await expect(panel.locator('[style*="conic-gradient"]')).toHaveCount(0);

    // A-C31 (2): the DESIGN'S OWN unavailable treatment, and the listing is still reachable.
    await expect(panel.getByText('Community data unavailable for this location')).toBeVisible();
    await expect(panel.getByText('The Census geography for this address has not been matched yet.')).toBeVisible();
    await expect(panel.getByRole('button', { name: 'View full listing' })).toBeVisible();

    // …and the detail behind it says the same rather than a grid of blanks.
    await panel.getByRole('button', { name: 'View full listing' }).click();
    await expect(page.getByText('Community data unavailable for this location')).toBeVisible();
    expect(errors).toEqual([]);
  });

  // THE ROOT-CAUSE CASE, and the one that can only be seen here. The test above shows the
  // unavailable card, which hides the whole Insights body — so it stays green even with A21.1c
  // reverted (measured). This one keeps `pop`, so `hasDemo` is TRUE and every tile, every bar
  // and every verdict is rendered against figures the API did not send: exactly the state the
  // eighteen seeded hospitals were in when the panel read "0" Households, "$0K" Median Income
  // and "Flat" Population Growth. Revert A21.1c and this test fails on those very strings.
  test('a listing with SOME figures shows those and fabricates none of the rest', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    await serveListings(page, { growth: null, income: null, hh: null, vets: null, econ_k: null, community_label: null });
    const panel = await openPanel(page);

    // "Median Income" is the design's own STATIC tile label and is always on this screen — the
    // banned word is the affluence VERDICT, so the label is neutralised before the scan rather
    // than the word being dropped from the list (the same false positive the unit suite hit).
    const text = (await panel.innerText()).replace(/\s+/g, ' ').replace(/Median Income/g, '[tile label]');
    // The one figure the API DID send is on the screen…
    await expect(panel.getByText('Population', { exact: true })).toBeVisible();
    expect(text, 'the Insights body must be rendered for this case to prove anything').toContain('Market Overview');
    // …and nothing else is invented around it: no zero, no NaN, and none of the nine verdicts
    // the three opportunity tiles and the score ring choose between.
    for (const banned of [...BANNED, 'Above avg.', 'Steady', 'Strong', 'Typical', 'Attractive', 'Balanced', 'Competition']) {
      expect(text, `the docked panel renders "${banned}" beside the one figure it does have`)
        .not.toContain(banned);
    }
    // No dangling units where a sub-line's figure is absent (F-2).
    expect(text).not.toContain('% (5 yrs)');
    expect(text).not.toContain('% vs US');
    // No competition row, no bars, no score (F-3).
    await expect(panel.getByText('per 10k households')).toBeVisible();       // the design's label stays
    await expect(panel.locator('[style*="conic-gradient"]')).toHaveCount(0); // the ring does not
    expect(errors).toEqual([]);
  });

  // D-C32: the same figures, but the API says they came from the drive-time band, not the
  // community. Nothing may present a drive-time catchment as a named city.
  test('the fallback label reaches every place that names the area, and nothing else moves', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    // D-C39 (2026-09-11): the ring is described by DISTANCE. It is an 8 km straight-line buffer
    // (spec §8), not a routed drive time, and true isochrones are still open for V1 (spec §15).
    const LABEL = 'Within about 5 miles of the practice';
    await serveListings(page, { community_label: LABEL });
    const panel = await openPanel(page);

    await expect(panel.getByText(LABEL)).toBeVisible();
    // D-C42 (John, 2026-09-11). The heading KEEPS its name and the geography renders on its own
    // sub-line beneath it — A21.5a let the label replace the heading, and D-C38 gives 28 of 29 QA
    // listings a label, so "Market Overview" appeared nowhere on QA and A27.3's own correction
    // was invisible.
    //
    // THIS IS THE ONLY ORACLE THE LABELLED PATH HAS, and it is here rather than in `screens.ts`
    // by measurement: the design's own fixtures carry no `communityLabel`, `design-listings.mjs`
    // sends `community_label: null`, and the REFERENCE has no way to be handed one — its listings
    // are `logic.js`'s own `P`, and reaching it would mean either editing the approved fixture
    // data or declaring a ninth prototype prop, neither of which this ruling authorises. So the
    // assertion is on the RENDERED DOM, not the payload: the sub-line is the heading's own next
    // element sibling, it carries the label, and it is set in the design's place-line 12.5px.
    await expect(panel.getByText('Market Overview', { exact: true })).toBeVisible();
    const beneath = await panel.evaluate((root) => {
      const heading = Array.from(root.querySelectorAll('div')).find((d) => (d.textContent || '').trim() === 'Market Overview');
      const next = heading && (heading.nextElementSibling as HTMLElement | null);
      return { heading: Boolean(heading), text: next && (next.textContent || '').trim(), size: next && getComputedStyle(next).fontSize };
    });
    expect(beneath.heading, 'the panel has no "Market Overview" heading — the label replaced it again').toBe(true);
    expect(beneath.text, 'the geography is not on the line directly beneath the heading').toBe(LABEL);
    expect(beneath.size, 'the sub-line is not the design\'s own place-line type').toBe('12.5px');
    // The figures themselves are the design's own and still render.
    await expect(panel.getByText('Veterinary Establishments')).toBeVisible();

    await panel.getByRole('button', { name: 'View full listing' }).click();
    const detail = page.getByRole('heading', { name: 'Community Context' }).locator('xpath=..');
    // The two sub-lines that used to name "the community" now name the area the figures describe.
    await expect(detail.getByText(LABEL).first()).toBeVisible();
    await expect(detail.getByText('Community, 2023')).toHaveCount(0);
    await expect(detail.getByText('In the community')).toHaveCount(0);
    await expect(detail.getByText(`Figures describe the area within about 5 miles of the practice, not the practice itself.`)).toBeVisible();
    // The Census attribution is legally load-bearing and is not part of the sentence that moved.
    await expect(detail.getByText('Source: U.S. Census Bureau, American Community Survey 2023 5-year estimates (public domain, attribution requested).')).toBeVisible();
    expect(errors).toEqual([]);
  });

  // D-C48 (John, 2026-09-11, on the whole-branch review). A27.7's ONE sub-line above the grid
  // describes the AREA figures, and the Population tile's sub-line is not one of them — it is
  // GROWTH, which the API measures at place-or-county and serves with its own `growth_scope`. So
  // the panel printed a city number under a ring caption on 28 of 29 QA listings.
  //
  // Its oracle is here, beside A27.7's, for the same measured reason: the design's own fixtures
  // carry no `growthScope`, `design-listings.mjs` sends `growth_scope: null`, and the reference
  // has no way to be handed one without editing approved fixture data or declaring a ninth
  // prototype prop. The assertion is therefore on the RENDERED DOM under a stubbed API.
  test('the panel\'s Population tile names the geography its growth figure came from', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    const LABEL = 'Within about 5 miles of the practice';
    await serveListings(page, { community_label: LABEL, growth_scope: 'Dallas' });
    const panel = await openPanel(page);

    const tile = await panel.evaluate((root) => {
      const label = Array.from(root.querySelectorAll('div')).find((d) => (d.textContent || '').trim() === 'Population');
      const box = label && (label.parentElement as HTMLElement | null);
      return box && (box.textContent || '').trim();
    });
    expect(tile, 'the panel has no Population tile').toBeTruthy();
    // The figure and its period lead, the geography follows, joined by the design's own middot —
    // the idiom of the detail card's Growth tile (A27.2) and of `income_note` (A27.1).
    expect(tile, 'the Population tile\'s growth sub-line names no geography')
      .toMatch(/[+-]\d+\.\d% \(5 yrs\) \u00b7 Dallas/);
    // The heading's own sub-line still says what the AREA figures describe, and says it once.
    await expect(panel.getByText('Market Overview', { exact: true })).toBeVisible();
    expect((await panel.innerText()).split(LABEL).length - 1,
      'the ring caption is stated more than once on the Insights tab').toBe(1);
    expect(errors).toEqual([]);
  });

  // …and with no label the wording is the design's own, which is what keeps the approved states
  // on their pixels: the D6 stub sends `community_label: null` for every fixture.
  test('with no label the design\'s own wording stands, byte for byte', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    const panel = await openPanel(page);
    // A27.3: the design's own two words, minus the parenthetical D-C39 ruled out. This heading
    // sat over PLACE-band figures on 28 of 29 listings and named a drive time the pipeline has
    // never computed.
    await expect(panel.getByText('Market Overview').first()).toBeVisible();
    await expect(panel.getByText('10 min drive')).toHaveCount(0);
    // A27.7 (D-C42): and with no label there is no sub-line ELEMENT at all — an empty one would
    // still take its `margin-top` and move every approved Browse capture. The heading's next
    // sibling is the overview tiles grid, exactly as the design has it.
    const beneath = await panel.evaluate((root) => {
      const heading = Array.from(root.querySelectorAll('div')).find((d) => (d.textContent || '').trim() === 'Market Overview');
      const next = heading && (heading.nextElementSibling as HTMLElement | null);
      return next && (next.textContent || '').trim();
    });
    expect(beneath, 'a sub-line was rendered for a listing the API sent no community_label for').toContain('Population');
    // A27.4: and its footnote, the second sentence D-C39 names.
    await expect(panel.getByText('A catchment figure is a straight-line area of about 5 miles around the practice, not a driving route.').first()).toBeVisible();
    await expect(panel.getByText('Drive-time figures are approximated')).toHaveCount(0);

    await panel.getByRole('button', { name: 'View full listing' }).click();
    const detail = page.getByRole('heading', { name: 'Community Context' }).locator('xpath=..');
    await expect(detail.getByText('Community, 2023')).toBeVisible();
    await expect(detail.getByText('In the community')).toBeVisible();
    await expect(detail.getByText('Figures describe the community around the practice, not the practice itself.')).toBeVisible();
    // A27.1/A27.2 null branches: the design's own two literals, which is what keeps `detail` on
    // its frozen hash.
    await expect(detail.getByText('Household, 2023').first()).toBeVisible();
    await expect(detail.getByText('Since 2015', { exact: true }).first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  // -----------------------------------------------------------------------------------------
  // D-C38 — per-figure geography, end to end in a real browser. The card's own tiles, not the
  // payload: the three area figures follow the catchment while the Growth tile says out loud
  // that its number is the city's, which is the whole reason John chose this option over the
  // one that relabels every tile uniformly.
  //
  // THE HONEST MEASURE this case exists to hold: THREE of the four tiles gain neighbourhood
  // detail. The Growth tile gains a label and nothing else, and will until the 2010->2020 tract
  // crosswalk is loaded.
  // -----------------------------------------------------------------------------------------
  test('each tile names where its own number comes from (D-C38)', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    const LABEL = 'Within about 5 miles of the practice';
    await serveListings(page, {
      community_label: LABEL,
      growth_scope: 'Dallas',
      income_note: `${LABEL} \u00b7 approximate`,
    });
    const panel = await openPanel(page);
    await panel.getByRole('button', { name: 'View full listing' }).click();
    const detail = page.getByRole('heading', { name: 'Community Context' }).locator('xpath=..');

    // Population and Households: the ring, named by the one label that describes them.
    await expect(detail.getByText(LABEL).first()).toBeVisible();
    // Median income: the ring AND the qualifier, in the one sub-line the tile has. The design's
    // own hard-coded "Household, 2023" is gone, which is the sub-line A21.5b/c could not reach.
    await expect(detail.getByText(`${LABEL} \u00b7 approximate`).first()).toBeVisible();
    await expect(detail.getByText('Household, 2023')).toHaveCount(0);
    // Growth: NOT the ring. The city, said out loud, beside the vintage A21.3d takes from the
    // API's own string. The stub is 'Dallas', the name TIGER itself gives (D-C41): the API
    // composes no "City of " prefix, so a fixture carrying one asserts a value the backend
    // cannot emit — which is the reading that made the prefix look composed in the first place.
    // `exact` on the negative: `getByText` matches by case-insensitive SUBSTRING, so a bare
    // 'Since 2015' would match the new sub-line's own tail and the assertion would say the
    // opposite of what it means.
    await expect(detail.getByText('Dallas \u00b7 since 2015').first()).toBeVisible();
    await expect(detail.getByText('Since 2015', { exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});

// -------------------------------------------------------------------------------------------
// Task MP1 — a published listing with no coordinates must not take the Browse map down with it.
//
// The failure this guards is a REAL-BROWSER one and cannot be seen anywhere else: `logic.js`
// handed `[null, null]` to `engine.marker`, Leaflet 1.9.4's `toLatLng` returned `null` for it
// (the array branch is gated on `typeof a[0] !== 'object'`, and `typeof null === 'object'`), and
// `_setPos` read `.lat` off the null — `pageerror: Cannot read properties of null (reading
// 'lat')`. ONE listing was enough: `drawPins`' `forEach` has no try/catch, so pin drawing
// stopped there for every listing after it, and the poisoned layer re-threw from inside
// Leaflet's own event loop on every later zoom pass.
//
// THIS TEST RUNS AGAINST THE VITE DEV SERVER (the `app` project's own target), where Vue's
// development `logError` re-throws out of `flushJobs` and drops the rest of the scheduler queue,
// so the whole screen stops responding — which is why the last assertion, that a results card
// still opens the docked panel, is the one that would have caught this. QA and production serve
// the production build, where Vue logs instead of re-throwing: there the same defect shows as
// pins silently missing from the offending listing onward and broken zoom, not a dead screen.
// -------------------------------------------------------------------------------------------
test.describe('Task MP1 — a listing with no coordinates keeps its place and gets no pin', () => {
  /** The design catalogue as `GET /api/listings` serves it, with `over` applied to the ONE row
   *  whose id is `id` — the shape the endpoint produces for a published listing whose seller has
   *  not disclosed its location (`location_disclosed` is `NOT NULL DEFAULT false`). */
  async function serveOne(page: Page, id: string, over: Record<string, unknown>): Promise<void> {
    const stub = listingsStubUrl();
    expect(stub, 'this test overrides the D6 stub, and a live target has none to override').not.toBeNull();
    const body = JSON.parse(designListingsBody()) as { items: Record<string, unknown>[]; next_cursor: null };
    const target = body.items.filter((r) => r.id === id);
    expect(target, `the design catalogue has no listing ${id}`).toHaveLength(1);
    Object.assign(target[0], over);
    await page.route(
      (url) => matchesListings(url.href, stub as string),
      (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    );
  }

  const AUSTIN = ['Cedar Park', 'Round Rock', 'South Austin', 'Georgetown', 'Kyle', 'East Austin', 'Lakeway', 'Dripping Springs', 'Pflugerville'];

  test('no page error, every located listing keeps its pin, and the screen still responds', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    // Cedar Park is the design's own first Austin listing and the one the results rail shows
    // first, so it is drawn first: with the defect standing it poisoned every pin after it.
    await serveOne(page, 'p1', { lat: null, lng: null, location_disclosed: false });

    await signInAs(page, 'design', '/browse');
    await waitMap(page);

    // Eight pins, one per LOCATED Austin listing, and none of them is Cedar Park's.
    const pins = page.locator('.leaflet-marker-icon');
    await expect(pins).toHaveCount(AUSTIN.length - 1);
    const titles = (await pins.evaluateAll((els) => els.map((e) => e.getAttribute('title') ?? ''))).join(' | ');
    for (const area of AUSTIN.slice(1)) {
      expect(titles, `${area}'s pin is missing — pin drawing stopped at the unlocated listing`).toContain(area);
    }
    expect(titles, 'a listing with no coordinates was drawn anyway').not.toContain('Cedar Park');

    // …and it keeps its place in the results: same count, still in the rail.
    await expect(page.getByText(`${AUSTIN.length} practices available`)).toBeVisible();

    // THE ASSERTION THAT WOULD HAVE CAUGHT THIS. Under the dev build the pin throw re-throws out
    // of Vue's scheduler and the screen stops responding, so a card click does nothing at all.
    await page.getByText('Cedar Park').first().click();
    const panel = page.locator('div.rf-scroll[style*="width: 366px"]');
    await expect(panel.getByRole('button', { name: 'View full listing' })).toBeVisible();

    // The drive-time ring's centre falls back to the metro centre rather than reaching
    // `L.circle([null, null])`, so selecting the unlocated listing does not throw either.
    await panel.getByRole('button', { name: 'View full listing' }).click();
    await expect(page.getByRole('heading', { name: 'Community Context' })).toBeVisible();

    expect(errors).toEqual([]);
  });

  // The control: with every coordinate present nothing is filtered, which is what keeps the
  // approved states on their pixels.
  test('…and with every coordinate present every listing is still pinned', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await expect(page.locator('.leaflet-marker-icon')).toHaveCount(AUSTIN.length);
    expect(errors).toEqual([]);
  });
});

// -------------------------------------------------------------------------------------------
// Task 10 (A24.14–A24.18) — what a member sees when the boundary route cannot answer.
//
// The rule is "the app draws what the API answered, or nothing at all", and nothing at all is
// exactly the blank screen that made this a fire once already: Task 4 reached QA on its own and
// the map read as empty. So the degradation is PHOTOGRAPHED here rather than asserted in prose.
// It cannot be an approved visual state — the reference receives no adapter and always draws the
// design's fixture, so there is no oracle to compare a failed load against; this is the same
// mechanism A16's and A17's adapter-failure paths are covered by.
//
// Two facts, together: the shading is gone (the design's Austin fixture is NOT drawn over a real
// metro, which is the honesty half), and everything else on the map still is — the basemap, the
// practice pins with their price callouts, and the results rail. `drawOverlay` paints the C7
// drive ring before it reaches the polygon layer and `drawPins()` is a separate call, which is
// why an empty overlay costs the member nothing but the colour.
// -------------------------------------------------------------------------------------------
test.describe('A24 — the boundary route is absent, and the map degrades rather than dying', () => {
  /** Painted pixels on the Leaflet overlay pane's shared canvas — the polygon layer's own
   *  surface, read the way the mobile shading smoke above reads it. */
  const paintedOverlay = (page: Page) => page.evaluate(() => {
    const c = document.querySelector('.leaflet-overlay-pane canvas') as HTMLCanvasElement | null;
    if (!c) return 0;
    const px = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 3; i < px.length; i += 4) if (px[i] > 0) n++;
    return n;
  });

  /** The adapter asks for every fill layer at once, so a refused route logs one 4xx console line
   *  per layer and each one has to be armed. Counted from `FILL_LAYERS` rather than typed: the
   *  list went from three to six on 2026-09-12 and a literal here would have made this case fail
   *  for arithmetic rather than for behaviour. `prepare()`'s own gate still fails the test on
   *  anything else — a page error, or a request nobody expected. */
  async function browseWith(page: Page, status: number): Promise<void> {
    await prepare(page);
    // The refusal is HELD until the allowances are armed, rather than raced against a timer:
    // `expectApiStatus` needs a page that has already navigated, and the three requests are made
    // at mount — so nothing may be DELIVERED before `release()`, which runs after arming.
    let release!: () => void;
    const held = new Promise<void>((resolve) => { release = resolve; });
    // Registered AFTER prepare()'s own route, and Playwright matches the LAST handler first.
    await page.route(
      (url) => url.pathname.startsWith('/api/markets/') && url.pathname.endsWith('/boundaries'),
      async (route) => {
        await held;
        await route.fulfill({ status, contentType: 'application/json', body: '{"error":{"code":"NOT_FOUND","message":"no such route"}}' });
      }
    );
    await signInAs(page, 'design', '/browse');
    for (let i = 0; i < FILL_LAYERS.length; i++) expectApiStatus(page, status);
    release();
    await waitMap(page);
    await settleExpectedApiFailures(page);
    await page.waitForTimeout(400);
  }

  test("a 404 leaves the map unshaded — and never falls back to the design's own Austin fixture", async ({ page }) => {
    await browseWith(page, 404);
    expect(await paintedOverlay(page), 'the polygon layer drew something after a refused load — the fixture must not stand in').toBe(0);
    // Everything the member still has. The pins are the proof the map is alive, not blank.
    await expect(page.locator('.leaflet-marker-pane .leaflet-marker-icon').first()).toBeVisible();
    expect(await page.locator('.leaflet-marker-pane .leaflet-marker-icon').count()).toBeGreaterThan(1);
    await expect(page.locator('.leaflet-container').first()).toBeVisible();
    // …and the results rail, the filters and the detail path are untouched.
    await expect(page.getByText('Cedar Park').first()).toBeVisible();
  });

  test('a refusal the member cannot fix — 401 — degrades the same way, not differently', async ({ page }) => {
    await browseWith(page, 401);
    expect(await paintedOverlay(page)).toBe(0);
    await expect(page.locator('.leaflet-marker-pane .leaflet-marker-icon').first()).toBeVisible();
    await expect(page.getByText('Cedar Park').first()).toBeVisible();
  });

  test('the route present but holding NO values paints real outlines in the design\'s own No data grey', async ({ page }) => {
    // The state QA is in until `geo_metric` is filled, and the one this whole design gained a
    // neutral swatch for (D-NS16): a polygon with no value is DRAWN, never omitted, because a
    // hole on a choropleth reads as a park, a lake or the edge of the market. So an unloaded
    // pipeline degrades inside the design's own vocabulary rather than as an empty map.
    await prepare(page);
    await page.route(
      (url) => url.pathname.startsWith('/api/markets/') && url.pathname.endsWith('/boundaries'),
      (route) => {
        const layer = new URL(route.request().url()).searchParams.get('layer') ?? 'income';
        const body = JSON.parse(designBoundariesBody(layer)) as { features: { properties: Record<string, unknown> }[] };
        for (const f of body.features) f.properties.value = null;
        route.fulfill({ status: 200, contentType: 'application/geo+json', body: JSON.stringify(body) });
      }
    );
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await page.waitForTimeout(400);
    // Painted, and painted in ONE colour — `#e6e6e6` at fillOpacity .5 over Leaflet's #ddd
    // ground, which is what the transparent tile stub leaves showing.
    const shades = await page.evaluate(() => {
      const c = document.querySelector('.leaflet-overlay-pane canvas') as HTMLCanvasElement | null;
      if (!c) return [];
      const px = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
      const seen = new Set<string>();
      for (let i = 0; i < px.length; i += 4) if (px[i + 3] > 0) seen.add(`${px[i]},${px[i + 1]},${px[i + 2]}`);
      return [...seen];
    });
    expect(shades.length, 'nothing was drawn — a value-less polygon must still be drawn (D-NS16)').toBeGreaterThan(0);
    // (0xe6 + 221) / 2 = 223 on every channel. Anti-aliased polygon edges add near neighbours,
    // so the assertion is that every painted shade is GREY — no ramp colour anywhere.
    for (const s of shades) {
      const [r, g, b] = s.split(',').map(Number);
      expect(Math.abs(r - g) + Math.abs(g - b), `a non-grey shade ${s} was painted for a value-less polygon`).toBeLessThanOrEqual(2);
    }
  });

  test('and with the route answering, the same page DOES paint polygons — so the two above measure the route, not the canvas', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await page.waitForTimeout(400);
    expect(await paintedOverlay(page), 'the control case must paint, or "0" above proves nothing').toBeGreaterThan(0);
  });
});

// -------------------------------------------------------------------------------------------
// A24.21–A24.23 — the map asks the API for the ground it is SHOWING (2026-09-12).
//
// The route has taken a `bbox` since Task 9 and the adapter never sent one, so every request was
// for the whole metro envelope — every screen paying for the whole of New York when it can see a
// fifth of it. (When this was wired the caps were still the ZCTA era's and that request was a 422
// outright; they were re-measured for Census tracts the same day — `MAX_FEATURES = 12000`,
// `MAX_BODY_BYTES = 6_000_000` — so both arms serve now and what the box buys is the size of the
// ANSWER: `tests/census/test_boundaries.py::test_the_viewport_bbox_narrows_new_yorks_answer_and_both_arms_now_serve`.)
//
// The unit tests own the arithmetic — `src/map/viewport.test.ts` for the padding, the grid and
// the debounce, `src/market/boundaries.test.ts` for the request and the retry, `src/logic.test.ts`
// for the guard. What only a real browser can prove is that the CHAIN is joined: Leaflet's own
// bounds → the engine → the viewport module → the adapter → the query string.
// -------------------------------------------------------------------------------------------
test.describe('A24.21–A24.23 — the boundary request carries the map own viewport', () => {
  const bboxesOf = (urls: string[]) => [...new Set(urls.map((u) => new URL(u).searchParams.get('bbox')))];

  /** `arm` is how many `422` console lines the FIRST settled view is expected to produce — six,
   *  one per layer, on a viewport wide enough that the boot box is past the route's span cap.
   *  They have to be armed BEFORE the view that provokes them and AFTER the page has an origin
   *  (`expectApiStatus` reads `page.url()` to tell the app from the reference), which is why the
   *  signed-out gate is visited first: it carries no map, so it provokes nothing, and it is the
   *  only moment in this sequence where both are true. */
  async function browseRecording(page: Page, arm = 0): Promise<string[]> {
    const urls: string[] = [];
    page.on('request', (r) => { if (/\/api\/markets\/[^/]+\/boundaries/.test(r.url())) urls.push(r.url()); });
    await prepare(page);
    if (arm > 0) {
      await page.goto('/browse');
      for (let i = 0; i < arm; i++) expectApiStatus(page, 422);
    }
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await page.waitForTimeout(900);          // the module's 250 ms settle, with room to spare
    return urls;
  }

  test('every boundary request names a box, and the box covers the map with the renderer own padding', async ({ page }) => {
    const urls = await browseRecording(page);
    expect(urls.length, 'the map asked for no boundaries at all').toBeGreaterThan(0);
    // NOT ONE whole-metro request: that is the request this change exists to stop making.
    expect(urls.filter((u) => new URL(u).searchParams.get('bbox') === null)).toEqual([]);

    const box = bboxesOf(urls).at(-1)!.split(',').map(Number);
    expect(box, 'the bbox is not four numbers').toHaveLength(4);
    const [w, s, e, n] = box;
    expect(e).toBeGreaterThan(w);
    expect(n).toBeGreaterThan(s);

    // The measured tie between the browser and the module: at zoom 10 a CSS pixel is
    // 360 / (256 x 2^10) degrees of longitude, the box is padded by 0.3 of the span on each side
    // (Leaflet's own canvas-renderer padding) and then snapped outward to at most one 1/8-tile
    // cell per side.
    const mapWidth = (await page.locator('.leaflet-container').first().boundingBox())!.width;
    const span = mapWidth * (360 / (256 * 2 ** 10));
    const cell = 360 / 2 ** 13;
    expect(e - w).toBeGreaterThanOrEqual(span * 1.6);
    expect(e - w).toBeLessThanOrEqual(span * 1.6 + 2 * cell);
  });

  // SUPERSEDED, 2026-09-12 (A32). `a metro switch pays for the whole-metro fallback ONCE per
  // layer, not twice` stood here: it armed three rounds of refusals, drained whatever was left
  // with `forgetExpectedApiFailures`, and asserted an UPPER bound, because the sequence it
  // measured was a race — its own comment recorded that cutting the 0.1.21 stale-box guard out
  // left it green, and named a metro envelope in the catalogue as "the real remedy … scheduled
  // for 0.1.22". That remedy was built, reviewed and withdrawn (the route is bbox-scoped and
  // metro-agnostic, so refusing on geometry would have blanked a member who panned off the
  // metro); what landed instead is A32, which removes the doomed round rather than declining to
  // send it. With no race left the count is deterministic in both directions, so the two cases
  // below assert EQUALITIES and spend every allowance they arm.

  // ---------------------------------------------------------------------------------------
  // A32 (2026-09-12) — a metro switch waits for the map to move before it asks.
  //
  // Measured on QA `db8bf67` (New York, 1,912 x 1,228): a metro switch pulled the whole metro
  // TWICE — 24 requests, 7.85 MB gzipped. `setMarket` runs BEFORE the map has moved, so the
  // request it used to issue carried the box the OLD metro was still settled on; on a wide screen
  // that box is past the route's span cap, the ladder falls back to the whole metro and pays for
  // it, and `logic.js`'s own guard then discards the answer because the settled view has moved on
  // by the time it lands. The listener repeats the sequence and THAT answer is drawn.
  //
  // The unit cases own the branch (`src/logic.test.ts`) and the notification (`src/map/
  // viewport.test.ts`, `src/components/MarketMapView.test.ts`). What only a real browser can
  // prove is the chain: the design's dropdown → `setMarket` → Vue's watcher → Leaflet's own
  // `setView` → the forced publish → the debounce → the adapter → the query string.
  // ---------------------------------------------------------------------------------------
  const REQUEST_SETTLE_MS = 1500;

  /** Click the metro dropdown's own row for `name` — A13's listbox, never a native select. */
  async function chooseMetro(page: Page, name: string): Promise<void> {
    await page.getByRole('combobox', { name: 'Metro area' }).click();
    const menu = page.getByRole('listbox', { name: 'Metro area' });
    await menu.waitFor({ state: 'visible' });
    await menu.getByRole('option', { name }).click();
    await page.waitForTimeout(REQUEST_SETTLE_MS);
  }

  /** The padded span the settled view will ask for, in degrees, read off the real map element —
   *  the same arithmetic `src/map/viewport.ts` does, so a case can STATE which side of the
   *  route's `MAX_BBOX_DEG` it is on instead of assuming a layout. */
  async function paddedSpanDeg(page: Page): Promise<number> {
    const width = (await page.locator('.leaflet-container').first().boundingBox())!.width;
    return width * (360 / (256 * 2 ** 10)) * 1.6;
  }

  /** Every box a set of recorded requests carried, in order, without de-duplicating: a count of
   *  requests is the thing these cases measure, so `bboxesOf`'s Set would hide the double pull.
   *  The whole-metro request's `null` is dropped — these are the boxes that were NAMED. */
  const boxesOf = (urls: string[]) => urls.map((u) => new URL(u).searchParams.get('bbox')).filter((b): b is string => b !== null);

  /** Painted pixels on the polygon layer's own canvas, the way the degradation block below reads
   *  them. Same-origin, so the canvas is untainted and readable. */
  const paintedPixels = (page: Page) => page.evaluate(() => {
    const c = document.querySelector('.leaflet-overlay-pane canvas') as HTMLCanvasElement | null;
    if (!c) return 0;
    const px = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 3; i < px.length; i += 4) if (px[i] > 0) n++;
    return n;
  });

  test('a metro switch on a WIDE map pulls the new metro whole ONCE per layer, and never asks with the old box', async ({ page }) => {
    // Wide enough that the padded box at the design's own zoom 10 is past the route's 4-degree
    // span cap — the shape of the QA measurement, where the map was 1,912 px. The precondition is
    // ASSERTED rather than assumed: if the Browse layout ever gives the map less of the window,
    // this says so instead of quietly testing the narrow case twice.
    await page.setViewportSize({ width: 2400, height: 1100 });
    // Every box past the cap is a console 422 and has to be armed BEFORE the view that provokes
    // it: six for the metro the page boots on, six more for the metro it switches to.
    const urls = await browseRecording(page, FILL_LAYERS.length);
    expect(urls.length).toBeGreaterThan(0);
    expect(await paddedSpanDeg(page), 'this viewport no longer produces a box past the route span cap')
      .toBeGreaterThan(4.0);
    const austin = boxesOf(urls);
    expect(austin.length, 'the boot never asked with a box').toBeGreaterThan(0);
    for (let i = 0; i < FILL_LAYERS.length; i++) expectApiStatus(page, 422);

    const before = urls.length;
    await chooseMetro(page, 'Atlanta, GA');

    const after = urls.slice(before);
    // NOT ONE request carrying a box Austin settled on. That request is the defect: its answer
    // was bought, discarded on arrival, and paid for again by the listener.
    expect(after.filter((u) => austin.includes(new URL(u).searchParams.get('bbox') ?? '')),
      'the metro switch asked with the box the previous metro was settled on').toEqual([]);
    // EXACTLY one whole-metro pull per layer — the ladder's fallback, once. Twelve is the defect.
    const wholeMetro = after.filter((u) => new URL(u).searchParams.get('bbox') === null);
    expect(wholeMetro.length, `the whole metro was pulled ${wholeMetro.length} times for ${FILL_LAYERS.length} layers`)
      .toBe(FILL_LAYERS.length);
    // …and every request is for the metro the member CHOSE. Atlanta's geoid, never Austin's.
    expect([...new Set(after.map((u) => new URL(u).pathname.split('/')[3]))]).toEqual(['12060']);
    // The refused round and the fallback round, and nothing before them.
    expect(after.length).toBe(FILL_LAYERS.length * 2);
    // Every one of the twelve allowances armed above is SPENT — `assertExpectedApiFailuresObserved`
    // at teardown fails on any that is not — so the refusal count is asserted as exactly as the
    // request count. There is no race left to lose.
  });

  test('a metro switch on a NARROW map asks for the new metro once per layer, and never for the old box', async ({ page }) => {
    // The project's own 1440 x 940, where the padded box sits UNDER the span cap — so nothing is
    // refused, nothing falls back, and the whole cost of a metro switch is one request per layer.
    // Before A32 it was twelve: six carrying the box the previous metro had settled on (served,
    // and describing ground the member is no longer looking at) and six carrying the real one.
    const urls = await browseRecording(page);
    expect(urls.length).toBeGreaterThan(0);
    expect(await paddedSpanDeg(page), 'this viewport now produces a box past the route span cap')
      .toBeLessThan(4.0);
    const austin = boxesOf(urls);

    const before = urls.length;
    await chooseMetro(page, 'Atlanta, GA');

    const after = urls.slice(before);
    expect(after.filter((u) => austin.includes(new URL(u).searchParams.get('bbox') ?? '')),
      'the metro switch asked with the box the previous metro was settled on').toEqual([]);
    expect(after.length, 'a metro switch costs more than one request per layer').toBe(FILL_LAYERS.length);
    expect(after.filter((u) => new URL(u).searchParams.get('bbox') === null), 'the whole metro was pulled at all').toEqual([]);
    expect([...new Set(after.map((u) => new URL(u).pathname.split('/')[3]))]).toEqual(['12060']);
    // One box, and it is a box over ATLANTA — the metro the member chose, not the one they left.
    const boxes = [...new Set(boxesOf(after))];
    expect(boxes).toHaveLength(1);
    const [w, , e] = boxes[0]!.split(',').map(Number);
    expect(w).toBeLessThan(-84.39);
    expect(e).toBeGreaterThan(-84.39);
  });

  // CONTINUITY — the case a client-side "is this box inside the metro?" guard would have failed,
  // and the reason that guard was withdrawn (review of ADAPT-STALE-2, 2026-09-12).
  //
  // `_BOUNDARY_SQL` filters on summary level, vintage and `ST_Intersects(geom, bbox)` and NEVER on
  // the CBSA: the `cbsa` path segment picks the whole-metro fallback box, the cache key and the
  // 404, and nothing else. So the shading has always followed a member who pans off the selected
  // metro, and it must keep doing so — "the map must work wherever a hospital is displayed".
  test('panning clean off the selected metro still asks, and still shades', async ({ page }) => {
    const urls = await browseRecording(page);
    const first = new URL(urls.at(-1)!).searchParams.get('bbox')!.split(',').map(Number);

    // Three full-width drags east: at zoom 10 the padded box is about 3.2 deg wide, so this
    // leaves Austin's own ground entirely — the design's practices span -98.09 to -97.62.
    const map = (await page.locator('.leaflet-container').first().boundingBox())!;
    for (let i = 0; i < 3; i++) {
      await page.mouse.move(map.x + map.width * 0.85, map.y + map.height / 2);
      await page.mouse.down();
      await page.mouse.move(map.x + map.width * 0.15, map.y + map.height / 2, { steps: 12 });
      await page.waitForTimeout(200);            // stand still: Leaflet throws an inertia pan otherwise
      await page.mouse.up();
      await page.waitForTimeout(700);
    }
    await page.waitForTimeout(REQUEST_SETTLE_MS);

    // The last request the map made names ground entirely east of where it started — so a request
    // WAS issued for the new box, and it is a box outside the metro. (There is no separate
    // "≥ 1 request carries this box" assertion: `last` is parsed from that request, so such a
    // line would match itself and measure nothing.)
    const last = new URL(urls.at(-1)!).searchParams.get('bbox')!.split(',').map(Number);
    expect(last[0], 'the map never left the ground it started on').toBeGreaterThan(first[2]);
    // …and the answer is drawn. A client that refused to ask here would leave this at zero.
    expect(await paintedPixels(page), 'the map went blank once it left the metro').toBeGreaterThan(0);
  });

  // A24.41/A24.42: `hasRamp` is true while `mdAreas === null`, which is precisely the state A32
  // puts the map in for the length of a metro switch. The legend must therefore keep its ramp and
  // its geography line throughout — the flicker those entries exist to prevent, now reachable by
  // a second route.
  test('the legend keeps its ramp and its geography line through a metro switch', async ({ page }) => {
    await browseRecording(page);
    // The two elements A24.41 and A24.42 gate on `areaFc.features.length > 0 || areasPending`:
    // the ramp's own "No data" class (`hasRamp`) and the geography line (`hasGeo`). Both are
    // present while `mdAreas === null`, which is exactly the state A32 holds the map in for the
    // length of a switch — so a ramp that vanished mid-switch would be the flicker those entries
    // exist to prevent, reached by a second route.
    const ramp = page.getByText('No data', { exact: true }).first();
    const geo = page.getByText('Census tract', { exact: true }).first();
    await expect(ramp, 'no ramp before the switch — this case would assert nothing').toBeVisible();
    await expect(geo).toBeVisible();

    await page.getByRole('combobox', { name: 'Metro area' }).click();
    const menu = page.getByRole('listbox', { name: 'Metro area' });
    await menu.waitFor({ state: 'visible' });
    await menu.getByRole('option', { name: 'Atlanta, GA' }).click();
    // MID-SWITCH: the map has moved, the settle has not fired, `mdAreas` is null.
    await page.waitForTimeout(120);
    await expect(ramp, 'the legend dropped its ramp while the new metro was pending').toBeVisible();
    await expect(geo, 'the legend dropped its geography line while the new metro was pending').toBeVisible();

    await page.waitForTimeout(REQUEST_SETTLE_MS);
    await expect(ramp).toBeVisible();
    await expect(geo).toBeVisible();
  });

  test('panning the map asks again, for the new ground and once', async ({ page }) => {
    const urls = await browseRecording(page);
    const before = bboxesOf(urls);
    expect(before.length).toBeGreaterThan(0);

    const map = (await page.locator('.leaflet-container').first().boundingBox())!;
    await page.mouse.move(map.x + map.width * 0.7, map.y + map.height / 2);
    await page.mouse.down();
    await page.mouse.move(map.x + map.width * 0.2, map.y + map.height / 2, { steps: 12 });
    // Stand still before letting go: Leaflet's drag handler measures the pointer's speed at
    // mouseup and throws an inertia pan if there is any, which would be a SECOND settled view.
    await page.waitForTimeout(200);
    await page.mouse.up();
    await page.waitForTimeout(1200);

    const after = bboxesOf(urls);
    // Exactly one new box — a drag is one settled view, not one request per mouse move.
    expect(after.length, 'the pan produced no new request, or more than one round of them').toBe(before.length + 1);
    expect(after.at(-1)).not.toBe(before.at(-1));
    // …and it is a box to the EAST of the one before it: dragging the map left moves the view right.
    expect(Number(after.at(-1)!.split(',')[0])).toBeGreaterThan(Number(before.at(-1)!.split(',')[0]));
  });
});

// ---------------------------------------------------------------------------------------
// A31 (Task SNAP, ruling D-C50 as revised, 2026-09-12) — the Market snapshot's two modes, in a
// real browser and through the real adapter.
//
// The two approved states photograph both modes, and pixels cannot say WHY a number is what it
// is: the point of this ruling is that the AREA figure comes from `GET /api/markets/{cbsa}/summary`
// — the polygons the map shades — and not from the listings, and those two can agree by accident
// on a fixture. So this reads the ANSWER the page itself received and the STRING the card printed,
// and checks that the second follows the first.
//
// The answer is taken off the page's own `response` event rather than re-fetched through
// `page.request`: an APIRequestContext does not go through `page.route`, so a second fetch would
// reach the real API and read a different body from the one the app rendered — which is exactly
// what a test like this must not do.
// ---------------------------------------------------------------------------------------
interface SummaryRow { layer: string; median: number | null; with_value: number; geo_label: string }

test.describe('A31 — the Market snapshot has two modes (D-C50 as revised)', () => {
  test('the strip reads the metro summary in AREA mode, and the practice in LOCATION', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    const asked: string[] = [];
    const answers: Promise<{ layers: SummaryRow[] }>[] = [];
    page.on('response', (r) => {
      if (!r.url().includes('/summary')) return;
      asked.push(r.url());
      answers.push(r.json() as Promise<{ layers: SummaryRow[] }>);
    });
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await click(page, 'Expand all six layers');

    // The route was actually called, for the METRO and with no bbox — "metro median" names the
    // metro, and a median over whatever is on screen would move with every pan.
    expect(asked.length, 'the app never asked for the metro summary').toBeGreaterThan(0);
    expect(asked.at(-1)).toMatch(/\/api\/markets\/\d+\/summary$/);
    const summary = await answers[answers.length - 1];
    const income = summary.layers.find((l) => l.layer === 'income')!;
    expect(income.median, 'the summary answered no median, so this case proves nothing').not.toBeNull();

    const strip = page.locator('div.rf-scroll[style*="max-height: 40vh"]');
    await expect(strip.getByText(/^AREA · /)).toBeVisible();
    await expect(strip.getByText('Census areas across the metro, as the map shades them')).toBeVisible();
    // The figure the card prints IS the answered median, formatted by the design's own
    // `fmtMetric` — read off the response rather than retyped, so the assertion cannot drift.
    const card = strip.locator('div[style*="border-radius: 8px"]').filter({ hasText: 'Median household income' }).first();
    await expect(card).toContainText(`$${Math.round(income.median! / 1000)}K`);
    // …and it names the geography and the count it summarised, which is the whole correction: a
    // number under a caption that does not describe it is the defect D-C50 removed. The count is
    // grouped by the PAGE's own `toLocaleString`, evaluated in the page rather than here, so this
    // assertion reads the same separator the design does on a browser in any locale.
    const grouped = await page.evaluate((n: number) => n.toLocaleString(), income.with_value);
    // Fix round 1's Addendum (2026-09-13): the caption states exactly what the number IS and the
    // word "metro" is gone from it — the Census PUBLISHES a metro median at summary level 310
    // (97,638 ± 1,163 for CBSA 12420) and this is the median OF the metro's valued areas (94,801
    // on the same metro), so "metro median" beside a published figure gave a reader two different
    // numbers under one name. The heading still says "AREA · … metro", which is true of the SCOPE.
    await expect(card).toContainText(`median of ${grouped} ${income.geo_label}s`);
    await expect(card, 'the caption still claims to be the metro’s own median').not.toContainText('metro median');

    // LOCATION: selecting a practice switches the header and the figures, and the AREA caption
    // leaves the card entirely — "median of N areas" is AREA mode's wording alone.
    await page.getByText('Cedar Park').first().click();
    await expect(strip.getByText(/^LOCATION · /)).toBeVisible();
    await expect(strip.getByText(/^AREA · /)).toHaveCount(0);
    await expect(card).not.toContainText('median of');
    // Closing the docked panel returns to AREA — the ruling's own last sentence.
    await page.getByRole('button', { name: 'Close panel' }).first().click();
    await expect(strip.getByText(/^AREA · /)).toBeVisible();
    expect(errors).toEqual([]);
  });

  // The LIVE data path, which no fixture reaches: 28 of 29 QA listings carry a `community_label`
  // (D-C38), and in LOCATION mode the ruling puts that label on every card as its value note. The
  // design's own fixtures carry none, so the reference — and therefore both approved states —
  // renders the short fallback "community level" and can never photograph this. This is the case
  // that does, and it MEASURES the consequence rather than only asserting the string: the label is
  // 38 characters at 10.5 px beside a 24 px figure in a 232 px card, so the note wraps, and the
  // number recorded here is what a reader needs to judge whether the ruling wants revisiting.
  //
  // The listings stub is written inline rather than reached for: `serveListings` is scoped to the
  // docked-panel suite above, and hoisting it would be a drive-by edit to a passing file.
  test('LOCATION mode names each figure’s own geography, once (A31.12)', async ({ page }) => {
    // Fix round 1 (2026-09-13). Before it this case asserted every card's note WAS the ring label,
    // which is what the task shipped and what D-C48 had already ruled against one surface over:
    // `growth` is served at place-or-county with its own `growth_scope` and `econ` is the county
    // CBP row everywhere and always, so the ring sentence was false on two of the six cards on 28
    // of 29 QA listings. The LIVE path is what is measured — the API's own fields through
    // `load.ts` onto the card — because that is the only place the defect was visible.
    await prepare(page);
    const LABEL = 'Within about 5 miles of the practice';
    const SCOPE = 'Travis County';
    const stub = listingsStubUrl();
    expect(stub, 'this test overrides the D6 stub, and a live target has none to override').not.toBeNull();
    const body = JSON.parse(designListingsBody()) as { items: Record<string, unknown>[] };
    const APPROX = `${LABEL} \u00b7 approximate`;
    for (const item of body.items) {
      item.community_label = LABEL;
      item.growth_scope = SCOPE;
      item.income_note = APPROX;   // D-C51: the API's own qualifier for a catchment median
    }
    await page.route(
      (url) => matchesListings(url.href, stub as string),
      (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    );
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await click(page, 'Expand all six layers');
    await page.getByText('Cedar Park').first().click();

    const strip = page.locator('div.rf-scroll[style*="max-height: 40vh"]');
    await expect(strip.getByText(/^LOCATION · /)).toBeVisible();
    const notes = await strip.locator('span[style*="font-size: 10.5px"]').allInnerTexts();
    expect(notes.length, 'the strip rendered no value notes at all').toBeGreaterThan(0);
    // Four of the six cards ARE the ring the label describes; growth names the geography the API
    // served and payroll names the county it is always measured at.
    expect(new Set(notes)).toEqual(new Set([LABEL, APPROX, SCOPE, 'surrounding county']));
    expect(notes.filter((n) => n === APPROX).length, 'the income card dropped the API\u2019s own qualifier (D-C51)').toBe(1);
    expect(notes.filter((n) => n === SCOPE).length, 'growth did not take its own `growth_scope`').toBe(1);
    expect(notes.filter((n) => n === 'surrounding county').length, 'payroll did not name the county').toBe(1);
    expect(notes.some((n) => n.includes('metro median')), 'the AREA wording reached LOCATION mode').toBe(false);
    // ONE STRING PER FACT (A24.44–A24.57), measured on the rendered strip rather than asserted:
    // the basis belongs to the mode sub-line and each card's own note, and to nothing else.
    const sources = await strip.locator('div[style*="font-size: 10px"]').allInnerTexts();
    expect(sources.length, 'the strip rendered no source lines at all').toBeGreaterThan(0);
    for (const src of sources) {
      expect(src, `a source line repeats the basis: "${src}"`).not.toContain(LABEL);
      expect(src.trimEnd().endsWith('·'), `a source line ends in a dangling separator: "${src}"`).toBe(false);
    }
    const printed = (await strip.innerText()).split(LABEL).length - 1;
    expect(printed, 'the basis is named on the sub-line and on the four cards it describes').toBe(5);
    console.log(`[A31.12] the practice basis is printed ${printed} time(s) on the strip; growth reads "${SCOPE}"`);
  });
});

// -------------------------------------------------------------------------------------------
// A35 — THE BASEMAP NEVER REQUESTS A TILE ESRI DOES NOT HAVE, AND THE MEMBER ZOOMS PAST IT.
// John, 2026-09-13 (ruling D-C52): "allow a user to zoom in BELOW the level of the last actual
// map layer … the map allows user to zoom in as far as they want … this message is never seen".
//
// WHY NO GATE CAUGHT IT, and why this one is in a real browser. `harness.ts` answers every
// arcgisonline request with a transparent 1x1 GIF at any zoom, and every approved state captures
// at z10 (desktop) / z9 (phone) with no zoom step — so the pixels could never show it. The unit
// case (`src/map/engines/leaflet.test.ts`) owns the OPTIONS; what only Chromium can prove is what
// Leaflet does WITH them: that `_clampZoom` holds the URL at the native max while `_limitZoom`
// lets the map itself reach 20, on both basemaps, across a switch.
//
// The URLs are recorded rather than the tiles inspected: the stub deliberately answers 200 to
// everything (an abort logs a console error the harness's own gate would fail on), which is
// exactly what Esri does for a missing tile too. The REQUEST is the observable.
// -------------------------------------------------------------------------------------------
test.describe('A35 — the gray basemap never asks Esri for a tile it does not have (D-C52)', () => {
  /** The last level each Esri service is actually cached to, MEASURED 2026-09-13 (the task brief's
   *  own probe: the Canvas tilemaps report zero tiles at 17+ at all nine US points; World_Imagery
   *  is real at z19 everywhere probed, rural Texas included). */
  const NATIVE_MAX: Record<string, number> = { 'gray-base': 16, 'gray-labels': 16, imagery: 19 };
  const CEILING = 20;

  type TileHit = { service: string; z: number };
  const SERVICE: Record<string, string> = {
    'Canvas/World_Light_Gray_Base': 'gray-base',
    'Canvas/World_Light_Gray_Reference': 'gray-labels',
    World_Imagery: 'imagery'
  };

  /** Every basemap tile the page asks for, from before the first navigation — a tile requested at
   *  mount counts as much as one requested after a click. */
  function recordTiles(page: Page): TileHit[] {
    const hits: TileHit[] = [];
    page.on('request', (r) => {
      const m = /arcgisonline\.com\/ArcGIS\/rest\/services\/(.+?)\/MapServer\/tile\/(\d+)\//.exec(r.url());
      if (m && SERVICE[m[1]]) hits.push({ service: SERVICE[m[1]], z: Number(m[2]) });
    });
    return hits;
  }

  /** The MAP's own zoom, read off Leaflet's own animation proxy — the element `Map._animMoveEnd`
   *  transforms to `scale(getZoomScale(zoom, 1))`, i.e. 2^(zoom-1), on every `moveend`
   *  (leaflet-src.js:4756). Read from the DOM rather than through a hook, because the production
   *  code must not grow a test-only seam: the app exposes no zoom and this case does not ask it to.
   *  The TILE z cannot stand in — separating the two is the whole point of the ruling.
   *
   *  `animating` comes back with it because Leaflet SWALLOWS a zoom request made during a zoom
   *  animation (`Map._tryAnimatedZoom`: `if (this._animatingZoom) { return true; }`), and the proxy
   *  carries the TARGET zoom from `zoomanim` onward — so a press timed off the proxy alone lands
   *  inside the previous transition and is discarded, which is what held an early draft of this
   *  case at zoom 11. `leaflet-zoom-anim` is on the MAP PANE, not on the container
   *  (leaflet-src.js:4808/4834), and is carried for exactly the length of that transition. */
  const mapState = (page: Page) => page.evaluate(() => {
    const pane = document.querySelector('.leaflet-map-pane') as HTMLElement | null;
    const proxy = document.querySelector('.leaflet-map-pane > .leaflet-proxy') as HTMLElement | null;
    if (pane === null || proxy === null) return null;
    const m = /scale\(([0-9.e+-]+)\)/.exec(proxy.style.transform);
    return {
      zoom: m === null ? null : Math.round(Math.log2(Number(m[1]))) + 1,
      animating: pane.classList.contains('leaflet-zoom-anim')
    };
  });
  const mapZoom = async (page: Page) => (await mapState(page))?.zoom ?? null;

  /** One press of the design's own "+" control, waited out rather than slept through — in the PAGE,
   *  because every zoom step also settles a new viewport and pulls six layers of boundary polygons,
   *  and a poll driven from the test would be spending its budget on those round trips. Returns the
   *  zoom it settled on — equal to `from` when the map refused to move, which is the ceiling. */
  const STEP_TIMEOUT_MS = 10_000;
  async function zoomInOnce(page: Page, from: number): Promise<number> {
    await page.getByRole('button', { name: 'Zoom in' }).first().click();
    try {
      await page.waitForFunction((prev) => {
        const pane = document.querySelector('.leaflet-map-pane');
        const proxy = document.querySelector('.leaflet-map-pane > .leaflet-proxy') as HTMLElement | null;
        if (pane === null || proxy === null) return false;
        const m = /scale\(([0-9.e+-]+)\)/.exec(proxy.style.transform);
        if (m === null) return false;
        return !pane.classList.contains('leaflet-zoom-anim')
          && Math.round(Math.log2(Number(m[1]))) + 1 !== prev;
      }, from, { timeout: STEP_TIMEOUT_MS, polling: 100 });
    } catch {
      return from;                       // the map did not move: this is the ceiling
    }
    return (await mapZoom(page)) as number;
  }

  /** The basemap tiles the layer is actually SHOWING, classified the same way the requests are.
   *  Necessary as well as the request log, and deterministic where it is not: once a URL has been
   *  loaded, Chromium serves it from the memory cache and emits no network event at all, so
   *  switching BACK to a basemap whose tiles are already in hand can legitimately make zero
   *  requests. What the layer asked for is still written on every `<img>` in the tile pane — and
   *  an EMPTY tile pane is exactly the blank map A35.6's reset exists to prevent. */
  const tileSrcs = (page: Page): Promise<TileHit[]> => page.evaluate(() => {
    const SRC: Record<string, string> = {
      'Canvas/World_Light_Gray_Base': 'gray-base',
      'Canvas/World_Light_Gray_Reference': 'gray-labels',
      World_Imagery: 'imagery'
    };
    return [...document.querySelectorAll('.leaflet-tile-pane img')].flatMap((el) => {
      const m = /arcgisonline\.com\/ArcGIS\/rest\/services\/(.+?)\/MapServer\/tile\/(\d+)\//.exec((el as HTMLImageElement).src);
      return m && SRC[m[1]] ? [{ service: SRC[m[1]], z: Number(m[2]) }] : [];
    });
  });

  /** Painted pixels on the polygon layer's own canvas — the shading must survive the whole climb,
   *  because the canvas renderer has no zoom limit and the tiles beneath it now do. */
  const paintedOverlay = (page: Page) => page.evaluate(() => {
    const c = document.querySelector('.leaflet-overlay-pane canvas') as HTMLCanvasElement | null;
    if (!c) return 0;
    const px = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 3; i < px.length; i += 4) if (px[i] > 0) n++;
    return n;
  });

  // Ten zoom steps, each settling a new viewport and pulling six layers of real boundary polygons
  // through the harness — the cost of measuring the real chain rather than a stub of it.
  test.setTimeout(180_000);

  test('+ reaches zoom 20, every Canvas request stops at 16, and Satellite stops at 19', async ({ page }) => {
    const hits = recordTiles(page);
    await prepare(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await page.waitForTimeout(600);
    expect(await mapZoom(page), 'the design opens Austin at zoom 10 — read through the same channel as the rest').toBe(10);

    // Press + until the map stops. The count is bounded well above the ceiling so a map that keeps
    // going says so by failing the equality below rather than by looping.
    let z = 10;
    for (let i = 0; i < 14; i++) {
      const next = await zoomInOnce(page, z);
      if (next === z) break;
      z = next;
    }

    await page.waitForTimeout(1200);           // let the last level's tiles and the last boundary load fly

    const gray = hits.filter((h) => h.service !== 'imagery');
    expect(gray.length, 'the gray canvas asked for no tiles at all — the recorder is not watching').toBeGreaterThan(0);
    // (i) The defect itself, stated as the thing that must never be requested: Esri answers 200 with
    // a 2,521-byte "Map data not yet available" JPEG for any Canvas tile past 16.
    expect([...new Set(gray.filter((h) => h.z > NATIVE_MAX['gray-base']).map((h) => h.z))].sort((a, b) => a - b),
      'the gray canvas was asked for a level Esri answers with "Map data not yet available"').toEqual([]);
    // (ii) …and it still asks AT the ceiling. A layer that quietly stopped drawing at 16 would pass
    // the assertion above and leave the member on a blank map, which is not the ruling.
    expect(Math.max(...gray.map((h) => h.z)), 'the gray canvas stopped short of its own native max').toBe(NATIVE_MAX['gray-base']);

    // (iii) The member gets the whole way there, and no further. Before this change Leaflet derived
    // the map's ceiling from the layers (`getMaxZoom` -> `_layersMaxZoom`) and it was 18.
    expect(z, 'the + button did not reach the map\'s own ceiling of 20').toBe(CEILING);

    // (iv) The polygons are canvas layers with no zoom limit, and they still paint at 20 — the
    // upscaled basemap is underneath them, not instead of them.
    expect(await paintedOverlay(page), 'the shading vanished on the way up').toBeGreaterThan(0);

    // (v) The other basemap, switched AT the ceiling — which is where A35.6's reset is load-bearing,
    // because the two services clamp to different tile zooms and `redraw()` alone leaves the
    // layer holding the previous zoom's world range. An empty tile pane here is the blank map.
    const beforeSat = hits.length;
    const satTab = page.getByRole('button', { name: 'Satellite', exact: true });
    await satTab.click();
    await expect(satTab, 'the Satellite tab did not take').toHaveAttribute('aria-pressed', 'true');
    await page.waitForTimeout(1500);
    const shown = await tileSrcs(page);
    expect(shown.length, 'the tile pane is EMPTY at zoom 20 — the basemap switch drew no tiles at all').toBeGreaterThan(0);
    expect([...new Set(shown.map((h) => h.service))], 'the tile pane is not showing the imagery service').toEqual(['imagery']);
    expect(Math.max(...shown.map((h) => h.z)), 'Satellite is not drawing at its own native max').toBe(NATIVE_MAX.imagery);
    expect(hits.slice(beforeSat).filter((h) => h.z > NATIVE_MAX[h.service]),
      'Satellite was asked past Esri\'s published US floor of z19').toEqual([]);

    await page.getByRole('button', { name: 'Map', exact: true }).click();
    await page.waitForTimeout(1500);
    const back = await tileSrcs(page);
    expect(back.length, 'the tile pane is EMPTY after switching back — the reset did not take in this direction').toBeGreaterThan(0);
    expect([...new Set(back.map((h) => h.service))], 'the tile pane is not showing the gray canvas').toEqual(['gray-base']);
    expect(Math.max(...back.map((h) => h.z)),
      'the gray canvas is drawing past the level Esri has a tile for').toBe(NATIVE_MAX['gray-base']);

    // (vi) The whole recording, in one sentence: not one request, at any zoom, on either basemap,
    // for a tile the service that serves it does not have.
    const past = hits.filter((h) => h.z > NATIVE_MAX[h.service]);
    expect(past, `requests past a service's native max: ${JSON.stringify(past)}`).toEqual([]);

    // …and nothing is DRAWN past it either, on either basemap, at any point in the run.
    expect((await tileSrcs(page)).filter((h) => h.z > NATIVE_MAX[h.service])).toEqual([]);

    const byZoom = [...new Set(hits.map((h) => h.service))].sort().map((s) => {
      const zs = hits.filter((h) => h.service === s).map((h) => h.z);
      return `${s}: z${Math.min(...zs)}–${Math.max(...zs)} (${zs.length} requests)`;
    });
    console.log(`[A35] map zoom reached ${z}; ${byZoom.join('; ')}`);
  });
});
