// @vitest-environment jsdom
//
// ImageSlot is a parity port of the design's <image-slot> custom element
// (docs/design-reference/design_handoff_practice_match_v2/image-slot.js). The pixels are
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
const SLOT_JS = join(import.meta.dirname, '..', '..', '..', 'docs', 'design-reference', 'design_handoff_practice_match_v2', 'image-slot.js');
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

  // .spill and .ctl carry no display:none of their own — in Chromium they are invisible only
  // because of the UA's `[popover]:not(:popover-open)` rule. Vite 5's default build target is
  // chrome87/safari14/firefox78, all below the Popover floor (Chrome 114 / Safari 17 /
  // Firefox 125), where the four 12 px handles would paint and the Replace/Edit buttons would
  // stay tab-focusable. A plain feature check covers every one of those engines — unlike a
  // constructable stylesheet, which Safari < 16.4 and Firefox < 101 do not have either.
  const chrome = (root: ShadowRoot) => [root.querySelector('.spill'), root.querySelector('.ctl')] as HTMLElement[];

  it('hides the ported chrome inline where the Popover API is missing, without adding a shadow child', () => {
    // jsdom has no Popover API, so this is the sub-floor branch as a browser below the floor
    // would take it.
    expect('popover' in HTMLElement.prototype).toBe(false);
    const { root } = slot({ id: 'x', src: PHOTO });

    expect(chrome(root).map((el) => el.style.display)).toEqual(['none', 'none']);
    expect(root.childNodes).toHaveLength(6); // no extra <style> node — the oracle counts six
  });

  it('leaves the chrome untouched where the Popover API exists, so the oracle sees the design\'s styles', () => {
    // Every gate browser has it: the branch must be dead there, or `el.style` would carry a
    // declaration the design's element never sets and the DOM oracle would report it.
    Object.defineProperty(HTMLElement.prototype, 'popover', { value: null, configurable: true });
    const { root } = slot({ id: 'x', src: PHOTO });

    expect(chrome(root).map((el) => el.style.display)).toEqual(['', '']);
    expect(chrome(root).map((el) => el.getAttribute('style'))).toEqual([null, null]);
    expect(root.childNodes).toHaveLength(6);
  });

  // ---------------------------------------------------------------------------------------
  // Zero-gap audit, Phase 11. `style.display === 'none'` on the two chrome hosts is only the
  // first link. What the requirement actually is — the controls must be UNAVAILABLE, not
  // merely invisible — needs the whole cascade closed, because a control that is
  // visually gone but still tab-focusable and still in the accessibility tree is NOT fixed.
  //
  // jsdom cannot answer that directly: it models neither layout nor focusable-area rules
  // (`b.focus()` succeeds inside a display:none subtree, `getComputedStyle` does not apply a
  // shadow ancestor's cascade, `checkVisibility` is unimplemented). So the proof is
  // structural instead, and it is a complete one — these four facts together force
  // `display: none` to be the computed value in every engine that implements the cascade,
  // and a `display: none` element generates no box, is not a focusable area (HTML §6.6.2
  // requires a focusable area to be *being rendered*), is excluded from the accessibility
  // tree, and receives no pointer events:
  //
  //   1. every interactive/painting node of the chrome sits under an inline display:none;
  //   2. the shadow root's ONLY author stylesheet is image-slot.css (one <style>, asserted
  //      byte-for-byte above), so nothing else in the root can compete;
  //   3. that stylesheet's only `!important` declarations set display to `none` — an
  //      inline declaration outranks every non-important author rule, so no rule in it can
  //      restore a box;
  //   4. the chrome carries no `part`, so no `::part()` rule from the outer document can
  //      reach in either, and `display` is not inherited, so nothing else crosses the
  //      shadow boundary.
  // ---------------------------------------------------------------------------------------
  // The nearest ancestor (the node itself included), up to but not through the shadow root,
  // whose INLINE style hides it. Inline is the level the fallback writes at.
  const hiddenAncestor = (node: Element, root: ShadowRoot): HTMLElement | null => {
    for (let n: Node | null = node; n && n !== root; n = (n as Element).parentNode) {
      const e = n as HTMLElement;
      if (e.style && e.style.display === 'none') return e;
    }
    return null;
  };

  it('leaves no chrome node interactive below the Popover floor: every control sits under a display:none host', () => {
    expect('popover' in HTMLElement.prototype).toBe(false);
    const { root } = slot({ id: 'x', src: PHOTO });

    // Everything the editor chrome can paint or focus: the two Replace/Edit buttons, the
    // four resize handles, the translucent reframe ghost (which _render fills with the real
    // src), and the file input. Queried from the root, so a node moved out of .spill/.ctl
    // in some future edit would still have to be accounted for here.
    const interactive = [...root.querySelectorAll('.ctl button, .spill .handle, .spill .ghost')];
    expect(interactive.map((n) => n.tagName.toLowerCase() + '.' + (n.className || '')))
      .toEqual(['img.ghost', 'div.handle', 'div.handle', 'div.handle', 'div.handle', 'button.', 'button.']);
    for (const node of interactive) {
      expect(hiddenAncestor(node, root), `${node.tagName}.${node.className} is still rendered`).not.toBeNull();
    }
    // The file input is hidden by the design's own `hidden` attribute, not by the fallback.
    expect((root.querySelector('input') as HTMLInputElement).hasAttribute('hidden')).toBe(true);
  });

  it('cannot have that display:none overridden: the stylesheet\'s only !important declarations are display:none', () => {
    // If the design ever gained, say, `.ctl{display:flex !important}`, the inline fallback
    // would lose the cascade and the buttons would come back — silently, since jsdom shows
    // no layout. Pin the complete !important set instead.
    const important = [...css.matchAll(/[-a-z]+\s*:[^;{}]*?!important/g)].map((m) => m[0].replace(/\s+/g, ' '));
    expect(important).toEqual(['display:none !important', 'display:none !important']);
  });

  it('exposes no ::part() handle on the chrome, so no outer rule can reach past the fallback', () => {
    const { root } = slot({ id: 'x', src: PHOTO });
    const parts = [...root.querySelectorAll('[part]')].map((n) => n.getAttribute('part'));
    expect(parts).toEqual(['frame', 'image', 'empty', 'attribution-error', 'loading', 'ring', 'credit']);
    expect([...root.querySelectorAll('.spill, .spill *, .ctl, .ctl *')].some((n) => n.hasAttribute('part'))).toBe(false);
  });

  it('builds the constructor\'s six shadow nodes, editor chrome included but inert', () => {
    const { host, root } = slot({ id: 'x', src: PHOTO });

    // image-slot.js l.501-529: style, .frame, .credit, .spill, .ctl, the file input.
    expect(root.childNodes).toHaveLength(6);
    expect([...root.children].map((c) => c.tagName.toLowerCase() + (c.className ? '.' + c.className : '')))
      .toEqual(['style', 'div.frame', 'span.credit', 'div.spill', 'div.ctl', 'input']);
    const spill = root.querySelector('.spill') as HTMLElement;
    expect([spill.getAttribute('popover'), spill.getAttribute('data-dc-edit-transparent')]).toEqual(['manual', '']);
    expect([...spill.children].map((c) => c.tagName.toLowerCase() + '.' + c.className)).toEqual(['img.ghost', 'div.handle', 'div.handle', 'div.handle', 'div.handle']);
    expect([...spill.querySelectorAll('.handle')].map((h) => h.getAttribute('data-c'))).toEqual(['nw', 'ne', 'sw', 'se']);
    const ctl = root.querySelector('.ctl') as HTMLElement;
    expect([ctl.getAttribute('popover'), ctl.getAttribute('data-dc-edit-transparent')]).toEqual(['manual', '']);
    expect([...ctl.querySelectorAll('button')].map((b) => [b.getAttribute('data-act'), b.getAttribute('title'), b.textContent]))
      .toEqual([['replace', 'Replace image', 'Replace'], ['edit', 'Reframe image', 'Edit']]);
    const input = root.querySelector('input') as HTMLInputElement;
    expect([input.type, input.getAttribute('accept'), input.hasAttribute('hidden')]).toEqual(['file', 'image/png,image/jpeg,image/webp,image/avif', true]);
    // Read-only port: the chrome exists so the tree matches, but nothing drives it —
    // without data-editable the .ctl stays opacity:0/pointer-events:none, and .spill (which
    // sets no display of its own) is display:none under the UA popover rule.
    //
    // "inert" in this test's title means "nothing drives it", NOT "unreachable": .ctl's own
    // display:flex beats the UA popover rule, so above the Popover floor its two buttons
    // remain tab-focusable and named in the accessibility tree — measured in Chromium on
    // both targets, see the zero-gap audit report's NEEDS_CONTEXT item. Below the floor the
    // feature-check branch above removes them entirely.
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

  it('mirrors the src onto the reframe ghost, and drops it again when the slot empties', async () => {
    // image-slot.js l.1142 / l.1167: _render assigns the same URL to .spill .ghost as to
    // the frame image, and removes it in the empty branch. The ghost is never shown here
    // (the popover stays closed) but the attribute is part of the tree the oracle reads.
    const { wrapper, root } = slot({ id: 'x', src: PHOTO });
    const ghost = root.querySelector('.spill .ghost') as HTMLImageElement;
    expect(ghost.getAttribute('src')).toBe(PHOTO);

    await wrapper.setProps({ src: '' });
    expect(ghost.hasAttribute('src')).toBe(false);
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
});
