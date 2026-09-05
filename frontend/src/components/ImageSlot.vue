<template><image-slot ref="host" :id="id || undefined" :shape="shape || undefined" :placeholder="placeholder || undefined" :src="src || undefined"></image-slot></template>

<script setup>
// Parity port of the design's <image-slot> custom element
// (docs/design-reference/design_handoff_practice_match_v2/image-slot.js). Everything the
// slot draws lives in an open shadow root built in onMounted, exactly as the element's
// constructor builds it, so the host element itself stays empty — and the template holds
// nothing else, since a second root node (a comment included) would make the component a
// fragment and there would be no single host to attach the shadow root to.
//
// The host IS an <image-slot> element (vite.config.ts's isCustomElement keeps the compiler
// from resolving it as a component): the design's runtime renders that tag, and the DOM
// oracle compares tag names strictly. It carries the four attributes the design template
// writes on the element — id, shape, placeholder and, in the has-photo branch only, src —
// as real attributes, since that is where the design puts them; the empty-string cases
// drop out so the no-photo branch has no src attribute, exactly as the template has none.
//
// Read-only branch only. The design tool's runtime (window.omelette) is never present in
// this app, so `editable` is false throughout: no Replace/Edit controls, no drag-and-drop
// ingest, no reframe, and no .image-slots.state.json sidecar — `getSlot()` never returns
// anything, which fixes the stored view at the identity {s: 1, x: 0, y: 0}. Line numbers
// below refer to image-slot.js.
//
// Fix round 3 (John's ruling 2026-09-05, docs/decisions/2026-09-05-image-slot-editor-
// removed.md): the design tool's image editor is REMOVED from this port, not hidden. The
// zero-gap audit measured why hiding could not work — the design's own `.ctl{…display:flex…}`
// beats the UA's `[popover]:not(:popover-open){display:none}`, so the Replace/Edit buttons
// were keyboard-focusable and named in the accessibility tree in EVERY browser (12 phantom
// tab stops on the Listing screen; WCAG 2.1 SC 2.4.3, 4.1.2), and the design page has the
// identical defect. So the `.spill` reframe overlay, the `.ctl` strip and the hidden file
// input are gone, along with the ghost `src` mirroring and the Popover feature check that
// used to hide them below the floor. `image-slot.css` is untouched and still byte-for-byte
// the design's string — its editor rules are simply unused — and the DOM oracle drops the
// same three nodes from the DESIGN side (rule E, frontend/tests/dom.ts), so the two trees
// still match node for node. Permissioned photo management is a Wave 2b feature.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import css from './image-slot.css?raw';

const props = defineProps({
  // The element's observedAttributes (l.440-442). `mask` is deliberately not part of this
  // component's interface: the design never sets it, so only _render's no-mask branch
  // (l.1072-1085) is reachable here.
  id: { type: String, default: '' },
  shape: { type: String, default: 'rounded' },
  radius: { type: Number, default: 12 },
  src: { type: String, default: '' },
  placeholder: { type: String, default: 'Drop an image' },
  fit: { type: String, default: '' },
  credit: { type: String, default: '' },
  creditHref: { type: String, default: '' }
});

// Unsplash attribution rules, verbatim from l.108-146: an Unsplash src with no credit
// renders the error tile INSTEAD of the photo, and links back to unsplash.com carry the
// required utm referral params.
const UNSPLASH_HOMEPAGE_HREF = 'https://unsplash.com/?utm_source=claude_design&utm_medium=referral';
const isUnsplashHost = (u) => {
  try {
    return /(^|\.)unsplash\.com$/.test(new URL(u, document.baseURI).hostname.replace(/\.$/, ''));
  } catch {
    return false;
  }
};
const withReferral = (href) => {
  try {
    const u = new URL(href);
    if (!/(^|\.)unsplash\.com$/.test(u.hostname.replace(/\.$/, ''))) return href;
    if (!u.searchParams.has('utm_source')) u.searchParams.set('utm_source', 'claude_design');
    if (!u.searchParams.has('utm_medium')) u.searchParams.set('utm_medium', 'referral');
    return u.toString();
  } catch (e) {
    return href;
  }
};

// The empty-state glyph and the attribution-error glyph, verbatim from l.432-444.
const icon =
  '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
  '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/>' +
  '<path d="m21 15-5-5L5 21"/></svg>';
const warnIcon =
  '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>' +
  '<path d="M12 9v4"/><path d="M12 17h.01"/></svg>';

// The constructor's shadow tree (l.501-529) minus the editor — the frame and the credit
// span. The editor nodes the design also builds there (.spill with its .ghost and four
// .handle children, the .ctl strip with its two buttons, and the hidden file input) are not
// built here at all; see the ruling in the header comment.
const markup =
  '<div class="frame" part="frame">' +
  '  <img part="image" alt="" draggable="false" style="display:none">' +
  '  <div class="empty" part="empty">' + icon +
  '    <div class="cap"></div>' +
  '    <div class="sub">or <u>browse files</u></div></div>' +
  '  <div class="attr-error" part="attribution-error">' + warnIcon +
  '    <div class="cap">This photo needs attribution</div></div>' +
  '  <div class="loading" part="loading"></div>' +
  '  <div class="ring" part="ring"></div>' +
  '</div>' +
  '<span class="credit" part="credit"></span>';

const host = ref(null);
let el = null;   // the host element
let frame = null;
let ring = null;
let img = null;
let empty = null;
let cap = null;
let sub = null;
let creditEl = null;
let ro = null;
// Render-owned swap in flight, cleared only by the img's own load/error (l.567-577).
let loadPending = false;
// A transient attribution-error wipe of a showing image makes the follow-up render a
// replacement (spinner), not a first fill (blank frame) — see _render's empty branch.
let hidShowing = false;

const contain = () => String(props.fit || 'cover').toLowerCase() === 'contain';

// The single release discipline for the replacement-in-flight mask (l.959-967), without
// the ingest generation guard: nothing encodes images in a read-only slot.
function releaseMask(settled) {
  if (!loadPending && (settled || img.complete)) el.removeAttribute('data-swapping');
}

// Baseline geometry (l.973-984): `base` is the scale at view-scale 1 — cover fills the
// frame, contain fits inside it. Null until the image has loaded (naturalWidth is 0
// before that) or while the slot has no layout box.
function geom() {
  const iw = img.naturalWidth;
  const ih = img.naturalHeight;
  const fw = el.clientWidth;
  const fh = el.clientHeight;
  if (!iw || !ih || !fw || !fh) return null;
  return { iw, ih, fw, fh, base: contain() ? Math.min(fw / iw, fh / ih) : Math.max(fw / iw, fh / ih) };
}

// l.998-1046, read-only: no reframe, so no top-layer spill or control pinning, and the
// stored view is always {s: 1, x: 0, y: 0} — which also makes _clampView (l.988-996) a
// no-op, since x and y are already inside every clamp range.
function applyView() {
  const g = geom();
  if (!g) {
    // Dimensions not known yet (before img load) — centered fit so there is no flash of
    // an unpositioned image before the geometry lands.
    img.style.width = '100%';
    img.style.height = '100%';
    img.style.left = '50%';
    img.style.top = '50%';
    img.style.objectFit = contain() ? 'contain' : 'cover';
    return;
  }
  // Baseline (cover-fill or contain-fit) × view scale 1. Width/height and left/top are
  // all frame-%, so a responsive resize keeps the same crop.
  const k = g.base;
  img.style.width = (g.iw * k / g.fw * 100) + '%';
  img.style.height = (g.ih * k / g.fh * 100) + '%';
  img.style.left = '50%';
  img.style.top = '50%';
  img.style.objectFit = '';
}

// The credit overlay (l.1174-1213). `_userUrl` is always null here (no sidecar), so the
// credit belongs to `src` and shows whenever both are present.
function renderCredit(url, credit, attrError) {
  const showCredit = !!(url && credit && !attrError);
  creditEl.textContent = '';
  if (showCredit) {
    let href = '';
    const rawHref = props.creditHref || '';
    if (rawHref) {
      try {
        const u = new URL(rawHref, document.baseURI);
        if (u.protocol === 'http:' || u.protocol === 'https:') href = withReferral(u.href);
      } catch {}
    }
    const mkLink = (text, linkHref) => {
      const a = document.createElement('a');
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener noreferrer');
      a.setAttribute('href', linkHref);
      a.textContent = text;
      return a;
    };
    const m = /^Photo by (.+) on Unsplash$/.exec(credit);
    if (m) {
      creditEl.appendChild(document.createTextNode('Photo by '));
      creditEl.appendChild(href ? mkLink(m[1], href) : document.createTextNode(m[1]));
      creditEl.appendChild(document.createTextNode(' on '));
      creditEl.appendChild(mkLink('Unsplash', UNSPLASH_HOMEPAGE_HREF));
    } else if (href) {
      creditEl.appendChild(mkLink(credit, href));
    } else {
      creditEl.textContent = credit;
    }
  }
  el.toggleAttribute('data-credit', showCredit);
}

// _render (l.1068-1213), read-only branch.
function render() {
  if (!el) return;

  // Shape. Presets use border-radius so the dashed ring can follow the rounded outline.
  const shape = String(props.shape || 'rounded').toLowerCase();
  let radius = '';
  if (shape === 'circle') radius = '50%';
  else if (shape === 'pill') radius = '9999px';
  else if (shape === 'rounded') radius = (Number.isFinite(props.radius) ? props.radius : 12) + 'px';
  frame.style.borderRadius = radius;
  frame.style.clipPath = '';
  ring.style.borderRadius = radius;
  ring.style.display = '';

  // `editable` is false (no window.omelette.writeFile): no data-editable, and the browse
  // affordance under the caption stays hidden (l.1086-1089).
  sub.style.display = 'none';

  // Content. There is no sidecar, so the author-controlled `src` is the only source.
  const srcAttr = props.src || '';
  const url = srcAttr;
  cap.textContent = props.placeholder || 'Drop an image';
  const credit = (props.credit || '').trim();
  const attrError = !!(!credit && srcAttr && isUnsplashHost(srcAttr));
  el.toggleAttribute('data-attribution-error', attrError);
  if (url && !attrError) {
    const prev = img.getAttribute('src');
    if (prev !== url) {
      // Replacing an already-shown image: mark the swap BEFORE setting src so the stale
      // frame is never revealed. First fill keeps the placeholder until load — no spinner.
      if (prev || hidShowing) el.setAttribute('data-swapping', '');
      loadPending = true;
      img.src = url;
    } else {
      releaseMask();
    }
    hidShowing = false;
    img.style.display = 'block';
    empty.style.display = 'none';
    el.setAttribute('data-filled', '');
    applyView();
  } else {
    el.removeAttribute('data-swapping');
    // The src is being removed — no load/error will ever fire for it.
    loadPending = false;
    hidShowing = attrError && !!img.getAttribute('src');
    img.style.display = 'none';
    img.removeAttribute('src');
    // The error tile owns the blocked-photo state; .empty stays for the genuinely-empty slot.
    empty.style.display = attrError ? 'none' : 'flex';
    el.removeAttribute('data-filled');
  }

  renderCredit(url, credit, attrError);
}

onMounted(() => {
  el = host.value;
  const root = el.shadowRoot || el.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  style.textContent = css;
  const tpl = document.createElement('template');
  tpl.innerHTML = markup;
  root.appendChild(style);
  root.appendChild(tpl.content);
  // No Popover feature check any more: the nodes it used to hide below the floor are not
  // built at all, so there is nothing engine-dependent left here and every browser gets the
  // identical tree — which is also what keeps `el.style` empty for the DOM oracle.
  frame = root.querySelector('.frame');
  ring = root.querySelector('.ring');
  img = root.querySelector('.frame img');
  empty = root.querySelector('.empty');
  cap = root.querySelector('.empty .cap');
  sub = root.querySelector('.sub');
  creditEl = root.querySelector('.credit');
  // naturalWidth/Height aren't known until load — re-apply so the cover baseline is
  // computed from real dimensions, not the 100%×100% fallback. load/error also release
  // the replacement-in-flight mask (l.594-611).
  img.addEventListener('load', () => { loadPending = false; releaseMask(true); applyView(); });
  img.addEventListener('error', () => { loadPending = false; releaseMask(true); });
  // width%/height% in applyView encode the frame aspect at call time, so a host resize
  // would stretch the image until the next render (l.700-706).
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => render());
    ro.observe(el);
  }
  render();
});

onBeforeUnmount(() => {
  if (ro) { ro.disconnect(); ro = null; }
});

watch(
  () => [props.id, props.shape, props.radius, props.src, props.placeholder, props.fit, props.credit, props.creditHref],
  () => render()
);
</script>
