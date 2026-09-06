import { test, expect, type Page } from '@playwright/test';
import { booted, click, jump, prepare, waitMap } from './harness';
import { SCREENS } from './screens';

const ROUTES = ['/', '/browse', '/browse?tab=market', '/browse?tab=listings', '/practices/p1', '/requests', '/seller', '/admin?tab=data'];

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

  test('a deep link is honoured after the fixture sign-in, and a legacy ?tab= settles on Browse', async ({ page }) => {
    await prepare(page);
    await page.goto('/browse?tab=market');
    await page.getByRole('button', { name: 'Approved — enter', exact: true }).click();
    await expect(page).toHaveURL(/\/browse$/);
    await expect(page.getByRole('button', { name: /^Layers/ })).toBeVisible();
  });

  test('navigation writes the URL', async ({ page }) => {
    await prepare(page);
    await page.goto('/');
    await page.getByRole('button', { name: 'Browse', exact: true }).first().click();
    await expect(page).toHaveURL(/\/browse$/);
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
    await page.goto('/practices/p1');
    await page.getByRole('button', { name: 'Approved — enter', exact: true }).click();
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
  // navigation, not after it — the deep link is signed in through the gate's fixture button,
  // which is the only way this URL survives a cold load, so the budget covers boot + gate +
  // the pending deep link + Leaflet's first paint. The `?tab=market` is a legacy no-op kept
  // here deliberately: V3's Browse always shows market data. `[data-map]` is set by
  // LeafletMapEngine.mount() once the map is on the page.
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

  async function mobileMap(page: Page) {
    await prepare(page);
    await booted(page);
    await click(page, 'Mobile view');
    await jump(page, 'Browse');
    await click(page, 'Map');
    await waitMap(page);
  }

  test('the Map tab renders the market map inside the 390-wide phone frame', async ({ page }) => {
    await mobileMap(page);
    const box = (await page.locator('.leaflet-container').first().boundingBox())!;
    expect(Math.round(box.width), 'the map is not inside the prototype\'s 390px mobile frame').toBeGreaterThanOrEqual(380);
    expect(Math.round(box.width)).toBeLessThanOrEqual(392);
  });

  test('the Map tab shows community mosaic shading', async ({ page }) => {
    await mobileMap(page);
    // The mosaic is drawn on the engine's shared L.canvas renderer, so "shading is showing"
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
    expect(painted, 'no canvas in the Leaflet overlay pane — the mosaic never drew').toBeGreaterThan(0);
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
    expect(text).toContain('Source: U.S. Census ACS 5-year estimates (2023) · community level');
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
    await booted(page);
    await jump(page, 'Browse');
    await waitMap(page);
    await expect(page.getByRole('button', { name: 'Satellite', exact: true }), 'the desktop map lost its basemap tabs').toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Map', exact: true }), 'the desktop map lost its basemap tabs').toHaveCount(1);
  });

  test('tapping a pin twice reaches the detail screen — there is no peek card', async ({ page }) => {
    await mobileMap(page);
    const pin = page.locator('.leaflet-marker-icon').first();
    await pin.click();
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(/\/browse$/);              // first tap selects, it does not navigate
    await page.locator('.leaflet-marker-icon').first().click();
    await expect(page).toHaveURL(/\/practices\/p\d+$/);
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
