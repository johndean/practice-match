// @vitest-environment jsdom
//
// ImageSlot is a parity port of the design's <image-slot> custom element
// (docs/design-reference/design_handoff_practice_match_v3/image-slot.js). The pixels are
// judged by the visual gate against the element's own rendering, so what these tests pin
// is the thing the gate depends on: the shadow tree the element builds in its constructor
// (l.494-528), the stylesheet it injects (l.290-425), and the read-only branch of
// _render() (l.1068-1213 with `data-editable` false — no window.omelette, no sidecar).
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';

// Vitest stubs every `.css` request — `?raw` included — with `export default ""` unless
// `test.css` is enabled (vitest's own CSSEnablerPlugin), which would make an assertion on
// the injected stylesheet vacuously true. Hand the component the real file instead, which
// is what Vite's `?raw` gives it in dev and in the build. (import.meta.dirname, not
// `new URL(…, import.meta.url)`: Vite rewrites that form into a served asset URL.)
const CSS_PATH = join(import.meta.dirname, 'image-slot.css');
const css = readFileSync(CSS_PATH, 'utf8');

// The design's own stylesheet, read out of the read-only reference: image-slot.js builds it
// as one `const stylesheet = '…' + '…'` concatenation (l.290-425) whose comment lines are
// dropped before the literals are joined. Evaluating it here makes the port's CSS file a
// byte-for-byte assertion against the element's real text rather than a transcription.
const SLOT_JS = join(import.meta.dirname, '..', '..', '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'image-slot.js');
function designStylesheet(): string {
  const src = readFileSync(SLOT_JS, 'utf8');
  const start = src.indexOf('const stylesheet =');
  // The last rule marks the end of the concatenation. Its own indexOf must be checked
  // BEFORE being used as a search offset: indexOf clamps a negative fromIndex to 0, so a
  // missing marker would silently search from the top of the file, find some unrelated
  // "';", and hand eval() an empty slice — a bare SyntaxError instead of this named one.
  const lastRule = src.indexOf(':host([data-attribution-error]) .ring{display:none}');
  if (start < 0 || lastRule < 0) throw new Error('image-slot.js: stylesheet literal not found');
  const end = src.indexOf("';", lastRule);
  if (end < 0) throw new Error('image-slot.js: stylesheet literal not found');
  const literals = src.slice(start + 'const stylesheet ='.length, end + 1).split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
  return eval('(' + literals + ')') as string;
}
vi.mock('./image-slot.css?raw', async () => {
  const { readFileSync: read } = await import('node:fs');
  const { join: j } = await import('node:path');
  return { default: read(j(import.meta.dirname, 'image-slot.css'), 'utf8') };
});

const { default: ImageSlot } = await import('./ImageSlot.vue');

const PHOTO = '/assets/photos/round-rock-exterior-street.webp';

function slot(props: Record<string, unknown>) {
  const wrapper = mount(ImageSlot, { props });
  const host = wrapper.element as HTMLElement;
  const root = host.shadowRoot;
  if (!root) throw new Error('ImageSlot did not attach a shadow root');
  return { wrapper, host, root };
}

const frameOf = (root: ShadowRoot) => root.querySelector('.frame') as HTMLElement;
const ringOf = (root: ShadowRoot) => root.querySelector('.ring') as HTMLElement;
const imgOf = (root: ShadowRoot) => root.querySelector('.frame img') as HTMLImageElement;
const capOf = (root: ShadowRoot) => root.querySelector('.empty .cap') as HTMLElement;
const emptyOf = (root: ShadowRoot) => root.querySelector('.empty') as HTMLElement;
const creditOf = (root: ShadowRoot) => root.querySelector('.credit') as HTMLElement;
// image-slot.js l.108-146, verbatim.
const UNSPLASH_HOMEPAGE_HREF = 'https://unsplash.com/?utm_source=claude_design&utm_medium=referral';

describe('ImageSlot — shadow root and structure', () => {
  // The Popover-present test fakes support on the prototype; undo it for every other test.
  afterEach(() => { delete (HTMLElement.prototype as { popover?: unknown }).popover; });

  it('renders an <image-slot> host carrying the design template\'s own attributes', () => {
    // The DOM oracle compares tag names strictly and reads the host's attributes, which in
    // the design are the ones the template wrote on <image-slot> (never only props).
    const filled = slot({ id: 'ph-p2-exterior', shape: 'rect', src: PHOTO, placeholder: 'Exterior' }).host;
    expect(filled.tagName.toLowerCase()).toBe('image-slot');
    expect(filled.getAttribute('id')).toBe('ph-p2-exterior');
    expect(filled.getAttribute('shape')).toBe('rect');
    expect(filled.getAttribute('placeholder')).toBe('Exterior');
    expect(filled.getAttribute('src')).toBe(PHOTO);
    // The design's no-photo branch writes no src attribute at all (…dc.html l.328).
    expect(slot({ id: 'ph-p1-exterior', shape: 'rect', placeholder: 'Exterior' }).host.hasAttribute('src')).toBe(false);
  });

  it('renders the element\'s shadow tree, not light DOM', () => {
    const { host, root } = slot({ id: 'x', shape: 'rect', placeholder: 'Practice exterior' });

    expect(host.shadowRoot).toBeTruthy();
    expect(host.innerHTML).toBe('');
    // constructor order: frame > (img, empty, attr-error, loading, ring), then credit.
    expect(root.querySelector('.frame')?.getAttribute('part')).toBe('frame');
    expect([...frameOf(root).children].map((c) => c.tagName.toLowerCase() + '.' + c.className))
      .toEqual(['img.', 'div.empty', 'div.attr-error', 'div.loading', 'div.ring']);
    expect(root.querySelector('.credit')?.parentNode).toBe(root); // outside .frame's overflow clip
    expect(emptyOf(root).querySelector('svg')).toBeTruthy();
    expect(root.querySelector('.attr-error .cap')?.textContent).toBe('This photo needs attribution');
  });

  it('injects the element\'s stylesheet verbatim', () => {
    const { root } = slot({ id: 'x' });
    const styles = root.querySelectorAll('style');

    expect(styles).toHaveLength(1);
    expect(styles[0].textContent).toBe(css);
    // …and that file is the design's `stylesheet` string byte for byte — the concatenation
    // has no newlines, only the two-space runs its source literals begin with.
    expect(css).toBe(designStylesheet());
  });

  // ---------------------------------------------------------------------------------------
  // Fix round 3 (John's ruling, 2026-09-05 — docs/decisions/2026-09-05-image-slot-editor-
  // removed.md). The design tool's image editor is REMOVED from the port, not hidden.
  //
  // The zero-gap audit measured the reason: the design's own `.ctl{…display:flex…}` beats
  // the UA's `[popover]:not(:popover-open){display:none}` rule, so the Replace/Edit buttons
  // were keyboard-focusable and announced by assistive technology in EVERY browser — 12
  // phantom tab stops on the Listing screen (WCAG 2.1 SC 2.4.3, 4.1.2) — and hiding them
  // only below the Popover floor could never reach that. The editor is design-tool chrome:
  // unpermissioned, gated on `data-editable`, which the app never sets, and with no upload
  // backend. Permissioned photo management is a Wave 2b feature.
  //
  // So there is nothing left to hide, and the Popover feature check is gone with it. The
  // stylesheet stays byte-for-byte (asserted above) — its editor rules are simply unused —
  // and the DOM oracle drops the DESIGN side's editor nodes instead (rule E, tests/dom.ts).
  // ---------------------------------------------------------------------------------------
  it('builds no editor chrome at all: no .spill, no .ctl, no file input', () => {
    const { root } = slot({ id: 'x', src: PHOTO });

    expect(root.querySelector('.spill')).toBeNull();
    expect(root.querySelector('.ctl')).toBeNull();
    expect(root.querySelector('input[type=file]')).toBeNull();
    // …and none of their parts survive under another name.
    expect(root.querySelector('.ghost')).toBeNull();
    expect(root.querySelector('.handle')).toBeNull();
    expect(root.querySelectorAll('button')).toHaveLength(0);
    expect(root.querySelectorAll('input')).toHaveLength(0);
    expect(root.querySelector('[popover]')).toBeNull();
  });

  it('leaves nothing inside the shadow root focusable, on any engine', () => {
    // The requirement the audit's 12 phantom tab stops failed. Stated as the property
    // itself — "no focusable area in this shadow root" — not as a list of removed nodes, so
    // re-adding any focusable element (a button, a link, anything with a tabindex) fails
    // here even if it is called something new. jsdom models no layout, but tabIndex is a
    // real IDL attribute: it is >= 0 exactly for the elements that are in the tab order
    // when rendered, which after this change must be none of them.
    const { root } = slot({ id: 'x', src: PHOTO });

    const focusable = [...root.querySelectorAll('*')].filter((n) => (n as HTMLElement).tabIndex >= 0);
    expect(focusable.map((n) => n.tagName.toLowerCase() + (n.className ? '.' + n.className : ''))).toEqual([]);
  });

  it('no longer feature-checks Popover — the branch and everything it hid are gone', () => {
    // Both engines now produce the identical tree, so nothing about the port depends on the
    // Popover API any more. Asserted on both sides of the old branch so a re-introduced
    // feature check (which would write an inline style the DOM oracle reports) fails here.
    const withoutPopover = slot({ id: 'x', src: PHOTO }).root;
    Object.defineProperty(HTMLElement.prototype, 'popover', { value: null, configurable: true });
    const withPopover = slot({ id: 'x', src: PHOTO }).root;

    expect(withPopover.innerHTML).toBe(withoutPopover.innerHTML);
    expect([...withPopover.querySelectorAll('*')].filter((n) => n.hasAttribute('style')).map((n) => n.getAttribute('style')))
      .toEqual([...withoutPopover.querySelectorAll('*')].filter((n) => n.hasAttribute('style')).map((n) => n.getAttribute('style')));
  });

  it('exposes exactly the design\'s display-only ::part() handles', () => {
    const { root } = slot({ id: 'x', src: PHOTO });
    expect([...root.querySelectorAll('[part]')].map((n) => n.getAttribute('part')))
      .toEqual(['frame', 'image', 'empty', 'attribution-error', 'loading', 'ring', 'credit']);
  });

  it('builds the constructor\'s display-only shadow nodes and nothing else', () => {
    const { host, root } = slot({ id: 'x', src: PHOTO });

    // image-slot.js l.501-529 minus the editor: style, .frame, .credit. The .spill overlay,
    // the .ctl strip and the file input are gone (fix round 3); the DOM oracle drops the
    // same three from the design side so the two trees still match node for node.
    expect(root.childNodes).toHaveLength(3);
    expect([...root.children].map((c) => c.tagName.toLowerCase() + (c.className ? '.' + c.className : '')))
      .toEqual(['style', 'div.frame', 'span.credit']);
    expect(host.hasAttribute('data-editable')).toBe(false);
    // .sub ("or browse files") is the browse affordance: present in the tree, hidden by
    // _render's read-only branch (image-slot.js l.1088).
    expect((root.querySelector('.sub') as HTMLElement).style.display).toBe('none');
  });
});

describe('ImageSlot — shape', () => {
  it('leaves rect square-cornered', () => {
    const { root } = slot({ id: 'x', shape: 'rect' });

    expect(frameOf(root).style.borderRadius).toBe('');
    expect(ringOf(root).style.borderRadius).toBe('');
  });

  it('rounds by `radius`, defaulting to 12px', () => {
    expect(frameOf(slot({ id: 'x' }).root).style.borderRadius).toBe('12px');
    expect(frameOf(slot({ id: 'x', shape: 'rounded' }).root).style.borderRadius).toBe('12px');
    expect(frameOf(slot({ id: 'x', shape: 'rounded', radius: 20 }).root).style.borderRadius).toBe('20px');
  });

  it('falls back to 12px when radius is not a finite number', () => {
    expect(frameOf(slot({ id: 'x', shape: 'rounded', radius: Number.NaN }).root).style.borderRadius).toBe('12px');
  });

  it('an empty shape prop falls back to rounded, in the template attribute and in render()', () => {
    const { host, root } = slot({ id: 'x', shape: '' });
    expect(host.hasAttribute('shape')).toBe(false); // template: `:shape="shape || undefined"`
    expect(frameOf(root).style.borderRadius).toBe('12px'); // render(): `String(props.shape || 'rounded')`
  });

  it('uses 50% for circle and 9999px for pill, on the ring too', () => {
    const circle = slot({ id: 'x', shape: 'circle' }).root;
    expect(frameOf(circle).style.borderRadius).toBe('50%');
    expect(ringOf(circle).style.borderRadius).toBe('50%');

    const pill = slot({ id: 'x', shape: 'pill' }).root;
    expect(frameOf(pill).style.borderRadius).toBe('9999px');
    expect(ringOf(pill).style.borderRadius).toBe('9999px');
  });
});

describe('ImageSlot — empty state', () => {
  it('shows the ring, the glyph and the placeholder caption', () => {
    const { host, root } = slot({ id: 'x', shape: 'rect', placeholder: 'Practice exterior' });

    expect(ringOf(root).style.display).toBe('');
    expect(host.hasAttribute('data-filled')).toBe(false); // the ring's only hide gate
    expect(capOf(root).textContent).toBe('Practice exterior');
    expect(emptyOf(root).style.display).toBe('flex');
    expect(imgOf(root).style.display).toBe('none');
    expect(imgOf(root).hasAttribute('src')).toBe(false);
  });

  it('falls back to the element\'s own default caption', () => {
    expect(capOf(slot({ id: 'x' }).root).textContent).toBe('Drop an image');
    expect(capOf(slot({ id: 'x', placeholder: '' }).root).textContent).toBe('Drop an image');
  });

  it('an unset id (default \'\') writes no id attribute at all', () => {
    const { host } = slot({});
    expect(host.hasAttribute('id')).toBe(false);
  });
});

describe('ImageSlot — blocked Unsplash attribution', () => {
  it('hides the photo behind the attribution-error tile for a real Unsplash host with no credit', () => {
    const { host, root } = slot({ id: 'x', src: 'https://images.unsplash.com/photo-1234' });
    expect(host.hasAttribute('data-attribution-error')).toBe(true);
    expect(host.hasAttribute('data-filled')).toBe(false);
    expect(imgOf(root).style.display).toBe('none');
    expect(imgOf(root).hasAttribute('src')).toBe(false);
    expect(emptyOf(root).style.display).toBe('none'); // the error tile owns this state, not .empty
  });

  it('re-showing an attribution-blocked photo (hidShowing) after the src is cleared, then re-set', async () => {
    const { wrapper, host, root } = slot({ id: 'x', src: 'https://images.unsplash.com/photo-1234' });
    expect(host.hasAttribute('data-attribution-error')).toBe(true);

    // Clears the blocked src: hidShowing becomes true (attrError was true and img had a src).
    await wrapper.setProps({ src: '' });
    expect(host.hasAttribute('data-attribution-error')).toBe(false);
    expect(emptyOf(root).style.display).toBe('flex');

    // Setting a normal (non-Unsplash) photo now takes the `hidShowing` branch in the filled
    // path (prev !== url still holds since the src actually changed to a new value).
    await wrapper.setProps({ src: PHOTO });
    expect(host.hasAttribute('data-filled')).toBe(true);
  });
});

describe('ImageSlot — filled state', () => {
  it('shows the image and hides the ring', () => {
    const { host, root } = slot({ id: 'x', shape: 'rect', src: PHOTO, placeholder: 'Practice exterior' });

    expect(imgOf(root).getAttribute('src')).toBe(PHOTO);
    expect(imgOf(root).style.display).toBe('block');
    expect(imgOf(root).getAttribute('alt')).toBe('');
    expect(emptyOf(root).style.display).toBe('none');
    // :host([data-filled]) .ring{display:none} — image-slot.css
    expect(host.hasAttribute('data-filled')).toBe(true);
    expect(css).toContain(':host([data-filled]) .ring{display:none}');
  });

  it('mirrors nothing onto a reframe ghost — the reframe overlay no longer exists', () => {
    // image-slot.js l.1142/l.1167 assigned the frame image's URL to .spill .ghost and
    // removed it again when the slot emptied. With the overlay gone the port must not keep
    // a second <img> alive fetching the same photo.
    const { root } = slot({ id: 'x', src: PHOTO });
    expect(root.querySelectorAll('img')).toHaveLength(1);
    expect((root.querySelector('img') as HTMLImageElement).getAttribute('src')).toBe(PHOTO);
  });

  it('centres the image at the fit baseline before it loads', () => {
    const { root } = slot({ id: 'x', src: PHOTO });
    const img = imgOf(root);

    // _applyView's no-geometry branch (image-slot.js l.1023-1031): naturalWidth is 0 in
    // jsdom, as it is in a browser before decode.
    expect([img.style.width, img.style.height, img.style.left, img.style.top]).toEqual(['100%', '100%', '50%', '50%']);
    expect(img.style.objectFit).toBe('cover');
    expect(imgOf(slot({ id: 'x', src: PHOTO, fit: 'contain' }).root).style.objectFit).toBe('contain');
  });

  it('computes real width/height once the image has real geometry (applyView\'s baseline branch)', () => {
    const { host, root } = slot({ id: 'x', src: PHOTO, fit: 'contain' });
    const img = imgOf(root);
    // jsdom never lays anything out, so applyView's no-geometry branch is all any other test
    // sees; stub the four reads geom() makes (naturalWidth/Height on the img, clientWidth/
    // Height on the host) and fire the same 'load' event the browser would, which calls
    // applyView() again (image-slot.js l.567-577).
    Object.defineProperty(img, 'naturalWidth', { value: 400, configurable: true });
    Object.defineProperty(img, 'naturalHeight', { value: 300, configurable: true });
    Object.defineProperty(host, 'clientWidth', { value: 200, configurable: true });
    Object.defineProperty(host, 'clientHeight', { value: 200, configurable: true });

    img.dispatchEvent(new Event('load'));

    // contain: base = min(fw/iw, fh/ih) = min(200/400, 200/300) = 0.5
    expect(img.style.width).toBe('100%');   // 400 * 0.5 / 200 * 100
    expect(img.style.height).toBe('75%');   // 300 * 0.5 / 200 * 100
    expect(img.style.left).toBe('50%');
    expect(img.style.top).toBe('50%');
    expect(img.style.objectFit).toBe(''); // cleared once real geometry is known — the CSS default applies
  });

  it('computes the cover baseline (Math.max) with real geometry, not just contain (Math.min)', () => {
    const { host, root } = slot({ id: 'x', src: PHOTO }); // fit defaults to cover
    const img = imgOf(root);
    Object.defineProperty(img, 'naturalWidth', { value: 400, configurable: true });
    Object.defineProperty(img, 'naturalHeight', { value: 300, configurable: true });
    Object.defineProperty(host, 'clientWidth', { value: 200, configurable: true });
    Object.defineProperty(host, 'clientHeight', { value: 200, configurable: true });

    img.dispatchEvent(new Event('load'));

    // cover: base = max(fw/iw, fh/ih) = max(0.5, 0.667) = 0.667 (400*0.667/200*100 = 133.3%)
    expect(img.style.width).toBe((400 * (200 / 300) / 200 * 100) + '%');
    expect(img.style.height).toBe((300 * (200 / 300) / 200 * 100) + '%');
  });

  it('geom() is null when only some of the four dimensions are known', () => {
    // The no-geometry fallback style values below are only reachable through geom()
    // returning null, so an unchanged fallback proves each partial case still short-circuits
    // — naturalWidth/Height and clientWidth/Height each have to be checked independently.
    const cases: Array<[number, number, number, number]> = [
      [400, 0, 200, 200], // naturalHeight missing
      [400, 300, 0, 200], // clientWidth missing
      [400, 300, 200, 0]  // clientHeight missing
    ];
    for (const [iw, ih, fw, fh] of cases) {
      const { host, root } = slot({ id: 'x', src: PHOTO });
      const img = imgOf(root);
      Object.defineProperty(img, 'naturalWidth', { value: iw, configurable: true });
      Object.defineProperty(img, 'naturalHeight', { value: ih, configurable: true });
      Object.defineProperty(host, 'clientWidth', { value: fw, configurable: true });
      Object.defineProperty(host, 'clientHeight', { value: fh, configurable: true });
      img.dispatchEvent(new Event('load'));
      expect(img.style.width, `iw=${iw} ih=${ih} fw=${fw} fh=${fh}`).toBe('100%');
    }
  });
});

describe('ImageSlot — reactivity', () => {
  it('re-renders on prop change', async () => {
    const { wrapper, host, root } = slot({ id: 'x', shape: 'rect', placeholder: 'Practice exterior' });

    await wrapper.setProps({ placeholder: 'Treatment area' });
    expect(capOf(root).textContent).toBe('Treatment area');

    await wrapper.setProps({ src: PHOTO });
    expect(imgOf(root).getAttribute('src')).toBe(PHOTO);
    expect(host.hasAttribute('data-filled')).toBe(true);

    await wrapper.setProps({ shape: 'circle' });
    expect(frameOf(root).style.borderRadius).toBe('50%');

    await wrapper.setProps({ src: '' });
    expect(imgOf(root).hasAttribute('src')).toBe(false);
    expect(host.hasAttribute('data-filled')).toBe(false);
  });

  it('masks the stale photo while a replacement loads', async () => {
    const { wrapper, host } = slot({ id: 'x', src: PHOTO });
    expect(host.hasAttribute('data-swapping')).toBe(false); // first fill: no spinner

    await wrapper.setProps({ src: '/assets/photos/round-rock-exterior-side.webp' });
    expect(host.hasAttribute('data-swapping')).toBe(true);
  });

  it('re-rendering with the same src (a different prop changed) takes the no-op releaseMask branch, not a re-swap', async () => {
    const { wrapper, host, root } = slot({ id: 'x', src: PHOTO, placeholder: 'Practice exterior' });
    expect(host.hasAttribute('data-swapping')).toBe(false);
    // The image "finishes loading" first, so loadPending is false before the next render —
    // without this, releaseMask()'s `!loadPending` guard alone would short-circuit the call,
    // never reaching the `settled || img.complete` check this test targets.
    imgOf(root).dispatchEvent(new Event('load'));

    // Only `placeholder` changes; `src` is the same value, so render()'s `prev !== url` is
    // false and it calls releaseMask() (no swap, settled undefined) instead of re-assigning
    // img.src — which is what evaluates `img.complete` rather than short-circuiting on `settled`.
    await wrapper.setProps({ placeholder: 'Treatment area' });
    expect(capOf(root).textContent).toBe('Treatment area');
    expect(imgOf(root).getAttribute('src')).toBe(PHOTO);
    expect(host.hasAttribute('data-swapping')).toBe(false);
  });
});

describe('ImageSlot — Unsplash attribution-error gate (isUnsplashHost)', () => {
  it('degrades to false — no attribution-error tile — when the src cannot be parsed as a URL', () => {
    // A space in the host is genuinely unparseable (`new URL` throws), not merely an
    // unusual value; isUnsplashHost's catch branch is only reachable this way.
    const { host } = slot({ id: 'x', src: 'http://exa mple.com/photo.jpg' });
    expect(host.hasAttribute('data-attribution-error')).toBe(false);
  });
});

describe('ImageSlot — credit attribution (renderCredit / withReferral)', () => {
  it('shows nothing and clears data-credit when there is no credit text', () => {
    const { host, root } = slot({ id: 'x', src: PHOTO });
    expect(host.hasAttribute('data-credit')).toBe(false);
    expect(creditOf(root).textContent).toBe('');
  });

  it('shows plain text when credit has no creditHref', () => {
    const { host, root } = slot({ id: 'x', src: PHOTO, credit: 'Interior by Acme Corp' });
    expect(host.hasAttribute('data-credit')).toBe(true);
    expect(creditOf(root).textContent).toBe('Interior by Acme Corp');
    expect(creditOf(root).querySelector('a')).toBeNull();
  });

  it('falls back to plain text when creditHref cannot be parsed as a URL', () => {
    const { root } = slot({ id: 'x', src: PHOTO, credit: 'Interior by Acme Corp', creditHref: 'http://exa mple.com/x' });
    expect(creditOf(root).textContent).toBe('Interior by Acme Corp');
    expect(creditOf(root).querySelector('a')).toBeNull();
  });

  it('falls back to plain text when creditHref parses but is not http(s)', () => {
    const { root } = slot({ id: 'x', src: PHOTO, credit: 'Interior by Acme Corp', creditHref: 'mailto:owner@example.com' });
    expect(creditOf(root).textContent).toBe('Interior by Acme Corp');
    expect(creditOf(root).querySelector('a')).toBeNull();
  });

  it('links non-Unsplash credit text to a valid creditHref, unmodified (not an Unsplash host, so no utm rewrite)', () => {
    const { root } = slot({ id: 'x', src: PHOTO, credit: 'Interior by Acme Corp', creditHref: 'https://acme.example/credits/1' });
    const a = creditOf(root).querySelector('a');
    expect(a?.textContent).toBe('Interior by Acme Corp');
    expect(a?.getAttribute('href')).toBe('https://acme.example/credits/1');
    expect(a?.getAttribute('target')).toBe('_blank');
    expect(a?.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('a "Photo by X on Unsplash" credit with no href links only the trailing "Unsplash" word', () => {
    const { root } = slot({ id: 'x', src: PHOTO, credit: 'Photo by Jane Doe on Unsplash' });
    const credit = creditOf(root);
    expect(credit.textContent).toBe('Photo by Jane Doe on Unsplash');
    const links = [...credit.querySelectorAll('a')];
    expect(links).toHaveLength(1);
    expect(links[0].textContent).toBe('Unsplash');
    expect(links[0].getAttribute('href')).toBe(UNSPLASH_HOMEPAGE_HREF);
  });

  it('a "Photo by X on Unsplash" credit with a valid Unsplash creditHref links the name too, with utm params added', () => {
    const { root } = slot({ id: 'x', src: PHOTO, credit: 'Photo by Jane Doe on Unsplash', creditHref: 'https://unsplash.com/photos/abc' });
    const links = [...creditOf(root).querySelectorAll('a')];
    expect(links).toHaveLength(2);
    expect(links[0].textContent).toBe('Jane Doe');
    expect(links[0].getAttribute('href')).toBe('https://unsplash.com/photos/abc?utm_source=claude_design&utm_medium=referral');
    expect(links[1].textContent).toBe('Unsplash');
    expect(links[1].getAttribute('href')).toBe(UNSPLASH_HOMEPAGE_HREF);
  });

  it('does not duplicate utm params already present on the creditHref', () => {
    const { root } = slot({
      id: 'x', src: PHOTO, credit: 'Photo by Jane Doe on Unsplash',
      creditHref: 'https://unsplash.com/photos/abc?utm_source=x&utm_medium=y'
    });
    const links = [...creditOf(root).querySelectorAll('a')];
    expect(links[0].getAttribute('href')).toBe('https://unsplash.com/photos/abc?utm_source=x&utm_medium=y');
  });

  it("withReferral falls back to the href unchanged if the internal re-parse ever throws (defensive branch)", () => {
    // Unreachable through any real caller: `u.href` (the only input withReferral ever
    // receives) is always a valid absolute URL by construction, so re-parsing it can never
    // throw in practice — proven separately by direct probing of `new URL(new URL(x).href)`
    // across many inputs. The catch exists as a safety net anyway, so it is exercised here by
    // stubbing the global URL constructor to throw ONLY on withReferral's own single-argument
    // re-parse call, leaving every other URL construction (jsdom's own use, and the first,
    // two-argument parse at l.176) untouched.
    const RealURL = globalThis.URL;
    const TRIGGER = 'https://unsplash.com/photos/forced-throw';
    function StubURL(this: unknown, url: string, base?: string) {
      if (base === undefined && url === TRIGGER) throw new Error('forced for test');
      return new RealURL(url, base);
    }
    vi.stubGlobal('URL', StubURL);
    try {
      const { root } = slot({ id: 'x', src: PHOTO, credit: 'Photo by Jane Doe on Unsplash', creditHref: TRIGGER });
      const links = [...creditOf(root).querySelectorAll('a')];
      expect(links[0].getAttribute('href')).toBe(TRIGGER); // unchanged: no utm params appended
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe('ImageSlot — ResizeObserver wiring', () => {
  it('observes the host when ResizeObserver is available, and its notify callback itself re-renders, and disconnects on unmount', () => {
    let capturedCallback: (() => void) | undefined;
    let observedTarget: Element | undefined;
    let disconnectCalls = 0;
    class FakeResizeObserver {
      constructor(cb: () => void) { capturedCallback = cb; }
      observe(el: Element) { observedTarget = el; }
      disconnect() { disconnectCalls += 1; }
    }
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    try {
      const { wrapper, host, root } = slot({ id: 'x', src: PHOTO });
      const img = imgOf(root);
      expect(observedTarget).toBe(host);
      expect(capturedCallback).toBeTypeOf('function');
      expect(img.style.width).toBe('100%'); // no-geometry fallback, before — same as after if notify did nothing

      // Real geometry (naturalWidth/Height on the img, clientWidth/Height on the host) is not
      // reactive — nothing but an actual render()/applyView() call picks it up. Stubbing it
      // and firing only the captured notify callback (no prop change, no other trigger) is
      // what makes the resulting width discriminating: '200%' could not appear here unless
      // the ResizeObserver wiring genuinely re-rendered, unlike the previous version of this
      // test, whose 'rect stays square' assertion held whether or not notify did anything.
      Object.defineProperty(img, 'naturalWidth', { value: 400, configurable: true });
      Object.defineProperty(img, 'naturalHeight', { value: 200, configurable: true });
      Object.defineProperty(host, 'clientWidth', { value: 100, configurable: true });
      Object.defineProperty(host, 'clientHeight', { value: 100, configurable: true });
      capturedCallback!();

      // cover (default fit): base = max(fw/iw, fh/ih) = max(100/400, 100/200) = 0.5
      expect(img.style.width).toBe('200%');  // 400 * 0.5 / 100 * 100
      expect(img.style.height).toBe('100%'); // 200 * 0.5 / 100 * 100

      wrapper.unmount();
      expect(disconnectCalls).toBe(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
