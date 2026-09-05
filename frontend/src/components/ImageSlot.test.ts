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
  });

  it('carries no editor, reframe or sidecar chrome', () => {
    const { host, root } = slot({ id: 'x', src: PHOTO });

    expect(root.querySelector('.ctl')).toBeNull();
    expect(root.querySelector('.spill')).toBeNull();
    expect(root.querySelector('input')).toBeNull();
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
