// @vitest-environment jsdom
//
// The one thing about MarketMapView that no other test can see: the ORDER in which the
// overlay (community bubbles, drive-time rings) and the price pins are redrawn. Leaflet
// gives every marker `z-index = pos.y + zIndexOffset`, so a bubble and the pin above it
// tie and DOM order in the shared markerPane decides which paints on top — and a layer
// group's markers move to the end of that pane every time the group is cleared and
// refilled. MarketMap.jsx runs effect 5 (overlay) before effect 6 (pins) on every commit,
// so the pins are always re-added last. The Vue port must do the same on every trigger.
//
// The engine is NOT mocked: the component obtains it through `createEngine()` exactly as it
// does in the app, and the real `LeafletMapEngine` runs against a recording fake of the
// Leaflet library.
//
// Zero-gap audit, Phase 7 — import order is no longer load-bearing. This file used to
// depend on `import '../map/engines/leaflet'` being evaluated BEFORE `installLeafletStub()`,
// because the real Leaflet module assigns `window.L` when it is evaluated and would
// overwrite the stub. Deleting that one line made the suite fail ("expected 0 to be greater
// than 0" — no draws recorded at all), which is exactly the accidental-module-evaluation-
// order coupling the audit forbids. The loader module is mocked instead, so the real
// `leaflet` package is never imported at all and the stub is the only Leaflet that exists,
// whatever order anything else evaluates in. `src/lib/leaflet.js` itself is untouched (its
// own contract is covered by src/lib/leaflet.test.ts, which does import the real library).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { FakeMap, installLeafletStub, type LeafletStub } from '../map/testing/leaflet-stub';
import MarketMapView from './MarketMapView.vue';

// Hoisted above every import by vitest. `loadLeaflet` hands back whatever the stub installed
// on `window.L`, so the engine under test is the real LeafletMapEngine driving the fake.
// BASEMAPS/LABEL_TILES are placeholders: this file asserts nothing about tile URLs (that is
// src/map/engines/leaflet.test.ts's job, which uses the real constants).
vi.mock('../lib/leaflet.js', () => ({
  loadLeaflet: () => Promise.resolve((window as { L?: unknown }).L),
  BASEMAPS: { map: { url: 'stub://map', attribution: '' }, satellite: { url: 'stub://satellite', attribution: '' } },
  LABEL_TILES: 'stub://labels'
}));

afterEach(() => { delete (window as { L?: unknown }).L; });

// Fixtures are BUILT, not fixed: every assertion below has to hold for any cardinality, so
// the tests generate the counts they need instead of hard-coding a shape.
const community = (i: number) => ({
  name: `Community ${i}`, lat: 30.5 + i / 100, lng: -97.8 + i / 100, vets: 4 + i,
  values: { income: { t: 0.1 * i, label: `$${100 + i}K`, color: '#4c9a6a' }, density: { t: 0.05 * i, label: `${i}/km²`, color: '#2f7d55' } }
});
const communities = (n: number) => Array.from({ length: n }, (_, i) => community(i));
const practices = (n: number, priceLabel = '$1.45M') =>
  Array.from({ length: n }, (_, i) => ({ id: `p${i}`, lat: 30.31 + i / 100, lng: -97.75 + i / 100, priceLabel }));

// The two draws are told apart by the divIcon HTML they build: markers.js `dot()` opens
// with the bubble's width/height, `pricePin()` with the pill's font-family.
function drawOrder(stub: LeafletStub, from: number): string[] {
  return stub.calls
    .slice(from)
    .filter((c) => c.fn === 'divIcon')
    .map((c) => (/^<div style="width:/.test((c.args[0] as { html: string }).html) ? 'overlay' : 'pins'));
}

// The two layer groups, in the order MarketMapView asks the engine to create them at mount
// (`groups: ['overlay', 'pins']`) — identified by construction order, not by contents, so a
// fixture with zero overlay markers would still be found.
function layerGroups(stub: LeafletStub) {
  const groups = (stub.map.added as { clearLayers?: unknown; added: { seq: number }[] }[])
    .filter((g) => typeof g.clearLayers === 'function');
  expect(groups).toHaveLength(2);
  return { overlay: groups[0], pins: groups[1] };
}
// The attach sequence of every layer currently in a group. `seq` is stamped by the stub on
// every `addTo()`, so it records the order Leaflet's shared markerPane actually saw.
const attachSeqs = (g: { added: { seq: number }[] }) => g.added.map((l) => l.seq);

async function mounted(n = { communities: 2, practices: 1 }) {
  const stub = installLeafletStub();
  const wrapper = mount(MarketMapView, {
    props: {
      practices: practices(n.practices),
      communities: communities(n.communities),
      layers: { practices: true, competition: false, drive5: false, drive10: false },
      valueLayer: 'income',
      center: [30.31, -97.75],
      zoom: 10
    }
  });
  // MarketMapView reaches its engine through a DYNAMIC import (map/create.ts). A single
  // flushPromises() only drains the microtask queue, which is enough once the module is in
  // vitest's cache but not on the very first load — the second, undocumented job the deleted
  // eager import was doing. Waiting on the component's own ready signal (the zoom controls
  // render only once `status === 'ready'`, i.e. after `await e.mount()` resolved) is
  // deterministic regardless of when any module happens to be evaluated.
  await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
  await flushPromises();
  return { stub, wrapper };
}

// The invariant, stated once: after a redraw, every layer sitting in the overlay group was
// attached to the map strictly before every layer sitting in the pins group. Cardinality-
// free by construction — it compares the LAST overlay attach against the FIRST pin attach,
// so 2 communities or 20, 1 practice or 9, the assertion is the same one.
function expectOverlayBeforePins(stub: LeafletStub) {
  const { overlay, pins } = layerGroups(stub);
  const o = attachSeqs(overlay);
  const p = attachSeqs(pins);
  expect(o.length, 'no overlay layers were drawn — the fixture does not exercise the invariant').toBeGreaterThan(0);
  expect(p.length, 'no pin layers were drawn — the fixture does not exercise the invariant').toBeGreaterThan(0);
  expect(Math.max(...o), `last overlay attach #${Math.max(...o)} must precede first pin attach #${Math.min(...p)}`)
    .toBeLessThan(Math.min(...p));
}

describe('MarketMapView — redraw order', () => {
  it('redraws every overlay layer before every pin when only `practices` changes', async () => {
    const { stub, wrapper } = await mounted();
    expect(drawOrder(stub, 0).length).toBeGreaterThan(0); // the map really mounted and drew

    const from = stub.calls.length;
    await wrapper.setProps({ practices: practices(1, '$1.50M') });

    // Both groups rebuild, overlay first — MarketMap.jsx's effect 5 then effect 6. That the
    // overlay redraws at all on a pins-only change is the deliberate superset documented on
    // the watcher: one callback is the only way to promise the relative order.
    expectOverlayBeforePins(stub);

    // The same invariant read off the divIcon stream, stated semantically rather than as a
    // literal ['overlay', 'overlay', 'pins'] — that array pinned the fixture's cardinality
    // (two communities, one practice) into the expectation, so adding a third community
    // would have failed a test about ORDER for a reason that has nothing to do with order.
    const order = drawOrder(stub, from);
    expect(order).toContain('overlay');
    expect(order).toContain('pins');
    expect(order.indexOf('pins'), 'a pin was drawn before an overlay').toBeGreaterThan(order.lastIndexOf('overlay'));
    expect(order.slice(order.indexOf('pins')), 'an overlay was drawn after the first pin').not.toContain('overlay');
  });

  // Phase 6: changing the number of communities or practices must not invalidate the test.
  // Same assertions, five different fixture shapes — including the asymmetric ones that a
  // hard-coded expected array could never survive.
  for (const n of [
    { communities: 1, practices: 1 },
    { communities: 2, practices: 1 },
    { communities: 3, practices: 2 },
    { communities: 5, practices: 4 },
    { communities: 2, practices: 9 }
  ]) {
    it(`holds the overlay-before-pins order with ${n.communities} communities and ${n.practices} practices`, async () => {
      const { stub, wrapper } = await mounted(n);
      expectOverlayBeforePins(stub); // at mount
      await wrapper.setProps({ practices: practices(n.practices, '$2.00M') });
      expectOverlayBeforePins(stub); // and after a pins-only prop change
      // Both groups really were rebuilt (cleared and refilled), not merely appended to.
      const { overlay, pins } = layerGroups(stub);
      expect(attachSeqs(overlay)).toHaveLength(n.communities);
      expect(attachSeqs(pins)).toHaveLength(n.practices);
    });
  }

  // Phase 2/6, root cause measured rather than assumed. Two separate watchers are unsafe in
  // TWO independent ways, and a probe with the overlay watcher declared FIRST (the faithful
  // mirror of MarketMap.jsx's effect 5 → effect 6) demonstrated both:
  //
  //   1. an OVERLAY-ONLY trigger (`valueLayer`, `communities`, a drive-time toggle) fires
  //      only the overlay watcher, so the community bubbles are re-attached to the shared
  //      markerPane AFTER the untouched pins and paint on top of them — overlay seq 12,13
  //      against a pin still at 11. Declaration order cannot help: the other watcher never
  //      ran at all;
  //   2. when BOTH fire, Vue's pre-flush queue orders the two jobs by when their sources
  //      were TOUCHED during the parent's patch, not by declaration order — pins landed at
  //      seq 14 ahead of overlay at 15,16 even with the overlay watcher declared first.
  //
  // One merged watcher that always runs drawOverlay() then drawPins() is the only shape
  // that closes both. These two tests pin one failure mode each.
  it('holds the order when the trigger is an OVERLAY-ONLY prop (valueLayer), which fires no pins work of its own', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(2),
        communities: communities(3),
        layers: { practices: true, competition: false, drive5: false, drive10: false },
        valueLayer: 'income',
        center: [30.31, -97.75],
        zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();
    expectOverlayBeforePins(stub);

    await wrapper.setProps({ valueLayer: 'density' }); // touches nothing on the pins side
    expectOverlayBeforePins(stub);
    const { overlay, pins } = layerGroups(stub);
    expect(attachSeqs(overlay)).toHaveLength(3); // rebuilt…
    expect(attachSeqs(pins)).toHaveLength(2);    // …and so were the pins, after them
  });

  it('holds the order when the trigger is a community change rather than a practice change', async () => {
    const { stub, wrapper } = await mounted({ communities: 2, practices: 3 });
    await wrapper.setProps({ communities: communities(4) });
    expectOverlayBeforePins(stub);
    const { overlay, pins } = layerGroups(stub);
    expect(attachSeqs(overlay)).toHaveLength(4);
    expect(attachSeqs(pins)).toHaveLength(3);
  });
});

// Phase 7: the properties that make the test above trustworthy, asserted rather than assumed.
describe('MarketMapView — test isolation (no import-order or real-Leaflet coupling)', () => {
  it('never instantiates real Leaflet: the map is the stub\'s FakeMap and window.L is the stub', async () => {
    const { stub } = await mounted();
    expect(stub.map).toBeInstanceOf(FakeMap);
    expect((window as { L?: unknown }).L).toBe(stub.L);
    // Real Leaflet stamps its container; the fake stamps its own marker instead.
    expect(document.querySelector('.leaflet-container')).toBeNull();
  });

  it('exercises the real MarketMapView and the real LeafletMapEngine, not a stand-in', async () => {
    const { wrapper, stub } = await mounted();
    // The component's own template (its zoom controls appear only once status === 'ready',
    // which only happens after the real engine's mount() resolved).
    expect(wrapper.find('button[aria-label="Zoom in"]').exists()).toBe(true);
    // Options only LeafletMapEngine.mount() passes — nothing in this test file supplies them.
    expect(stub.calls[0].fn).toBe('map');
    expect(stub.calls[0].args[1]).toMatchObject({ zoomControl: false, attributionControl: true });
    // …and the divIcon payloads come from src/map/markers.js, the production renderer.
    expect(stub.calls.some((c) => c.fn === 'divIcon')).toBe(true);
  });
});
