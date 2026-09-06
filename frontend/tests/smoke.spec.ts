import { test, expect, type Page } from '@playwright/test';
import { booted, click, jump, prepare, waitMap } from './harness';

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
  const SHEET = 'div[style*="z-index: 700"]';

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
    await page.locator('button', { hasText: /of \d/ }).last().click();
    const sheet = page.locator(SHEET);
    await expect(sheet).toBeVisible();

    const sheetBox = (await sheet.boundingBox())!;
    expect(Math.round(sheetBox.width)).toBe(Math.round(mapBox.width));
    expect(Math.round(sheetBox.height)).toBe(Math.round(mapBox.height));

    const scrolls = await sheet.locator('.rf-scroll').evaluate((el) => el.scrollHeight > el.clientHeight);
    expect(scrolls, 'the sheet body does not scroll — it cannot be carrying all five sections').toBe(true);
  });

  test('every one of the five sections renders, in order', async ({ page }) => {
    await mobileMap(page);
    await page.locator('button', { hasText: /of \d/ }).last().click();
    const text = await page.locator(SHEET).innerText();
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
  });

  test('every tap target in the sheet is at least 44px', async ({ page }) => {
    await mobileMap(page);
    await page.locator('button', { hasText: /of \d/ }).last().click();
    const sizes = await page.locator(SHEET).locator('button').evaluateAll((els) =>
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
