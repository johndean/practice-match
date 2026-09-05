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
import { describe, expect, it, vi } from 'vitest';
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

  it('hides the ported chrome below the Popover floor, without adding a shadow child', () => {
    // .spill and .ctl carry no display:none of their own — in Chromium they are invisible
    // only because of the UA's `[popover]:not(:popover-open)` rule. Vite 5's default target
    // is chrome87/safari14/firefox78, all below the Popover floor (Chrome 114 / Safari 17 /
    // Firefox 125), where the four 12 px handles would paint and the Replace/Edit buttons
    // would stay tab-focusable. The guard is a constructable sheet rather than a second
    // <style> node so the shadow root keeps exactly the design's six children.
    const { root } = slot({ id: 'x', src: PHOTO });
    const sheets = (root as ShadowRoot & { adoptedStyleSheets?: CSSStyleSheet[] }).adoptedStyleSheets;

    expect(sheets).toHaveLength(1);
    const text = [...sheets![0].cssRules].map((r) => r.cssText).join('').replace(/\s+/g, ' ').trim();
    expect(text).toBe('@supports not selector(:popover-open) { .spill, .ctl { display: none; } }');
    expect(root.childNodes).toHaveLength(6);
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
    // without data-editable the .ctl stays opacity:0/pointer-events:none, and popover
    // elements are display:none until shown.
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
