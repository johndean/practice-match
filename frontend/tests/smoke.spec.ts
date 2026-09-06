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
