// @vitest-environment jsdom
//
// The one thing about MarketMapView that no other test can see: the ORDER in which the
// overlay (V3's community mosaic rectangles and the dashed drive-time ring) and the practice
// pins are redrawn. Leaflet gives every marker `z-index = pos.y + zIndexOffset`, so two
// layers can tie and DOM order in the shared panes decides which paints on top — and a layer
// group's layers move to the end of their pane every time the group is cleared and refilled.
// MarketMapV3.jsx runs its area effect (`:220-268`) before its pin effect (`:270-310`) on
// every commit, so the pins are always re-added last. The Vue port must do the same on every
// trigger, which is why one merged watcher owns both draws.
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
import { MOSAIC_STEP, mosaicBbox, mosaicCells } from '../map/mosaic.js';
import MarketMapView from './MarketMapView.vue';

// Hoisted above every import by vitest. `loadLeaflet` hands back whatever the stub installed
// on `window.L`, so the engine under test is the real LeafletMapEngine driving the fake.
// BASEMAPS/LABEL_TILES are placeholders: this file asserts nothing about tile URLs (that is
// src/map/engines/leaflet.test.ts's job, which uses the real constants).
//
// `loader.gate`, held open by only one test (mirrors src/map/engines/leaflet.test.ts's own
// gate), is the only way to reproduce a watched-prop change landing while onMounted's
// `await createEngine()` / `await e.mount()` chain is still in flight — `engine` is null
// only during that window, which is exactly the `if (!engine) return;` guards' target.
const loader = vi.hoisted(() => ({ gate: null as Promise<void> | null }));
vi.mock('../lib/leaflet.js', () => ({
  loadLeaflet: async () => { if (loader.gate) await loader.gate; return (window as { L?: unknown }).L; },
  BASEMAPS: { map: { url: 'stub://map', attribution: '' }, satellite: { url: 'stub://satellite', attribution: '' } },
  LABEL_TILES: 'stub://labels'
}));

afterEach(() => { delete (window as { L?: unknown }).L; loader.gate = null; });

// Fixtures are BUILT, not fixed: every assertion below has to hold for any cardinality, so
// the tests generate the counts they need instead of hard-coding a shape.
const community = (i: number) => ({
  name: `Community ${i}`, lat: 30.5 + i / 100, lng: -97.8 + i / 100, vets: 4 + i,
  values: { income: { t: 0.1 * i, label: `$${100 + i}K`, color: '#4c9a6a' }, density: { t: 0.05 * i, label: `${i}/km²`, color: '#2f7d55' } }
});
const communities = (n: number) => Array.from({ length: n }, (_, i) => community(i));
const practices = (n: number, priceLabel = '$1.45M') =>
  Array.from({ length: n }, (_, i) => ({ id: `p${i}`, lat: 30.31 + i / 100, lng: -97.75 + i / 100, priceLabel }));
// V3 shades one rectangle per MOSAIC CELL, so the overlay's cardinality is the mosaic's and
// not the community count. mosaic.js is the production geometry (covered by its own tests),
// so the expectation stays a statement about the CURRENT communities rather than a number
// pinned to one fixture shape.
const cellCount = (n: number) => mosaicCells(communities(n), mosaicBbox(communities(n)), MOSAIC_STEP).length;

// V3 tells the two draws apart by the Leaflet factory each uses: the overlay is rectangles
// and circles, the pins are divIcon markers.
function drawOrder(stub: LeafletStub, from: number): string[] {
  return stub.calls
    .slice(from)
    .filter((c) => c.fn === 'rectangle' || c.fn === 'circle' || c.fn === 'divIcon')
    .map((c) => (c.fn === 'divIcon' ? 'pins' : 'overlay'));
}

// The two layer groups are identified by ROLE — which production renderer filled them —
// never by construction order. In V3 the overlay group holds mosaic RECTANGLES and the
// dashed drive-time circle; the pins group holds practice markers.
type StubLayer = { seq: number; bounds?: unknown; options?: { radius?: number; icon?: { icon?: { html?: string } } } };
type StubGroup = { clearLayers?: unknown; added: StubLayer[] };

const roleOf = (l: StubLayer): 'overlay' | 'pins' => {
  if (l.bounds !== undefined) return 'overlay';                 // a mosaic L.rectangle
  if (typeof l.options?.radius === 'number') return 'overlay';  // the dashed drive-time ring
  return 'pins';
};

function layerGroups(stub: LeafletStub) {
  const groups = (stub.map.added as StubGroup[]).filter((g) => typeof g.clearLayers === 'function');
  expect(groups, 'the engine did not create exactly the two groups MarketMapView asks for').toHaveLength(2);
  const labelled = groups.map((g) => {
    const roles = [...new Set(g.added.map(roleOf))];
    expect(roles, `a layer group holds ${roles.length} renderer roles — the two draws are not separated`).toHaveLength(1);
    return { role: roles[0], group: g };
  });
  const overlay = labelled.find((x) => x.role === 'overlay');
  const pins = labelled.find((x) => x.role === 'pins');
  expect(Boolean(overlay && pins), 'could not identify both groups by the renderer that filled them').toBe(true);
  return { overlay: overlay!.group, pins: pins!.group };
}
// The attach sequence of every layer currently in a group. `seq` is stamped by the stub on
// every `addTo()`, so it records the order Leaflet's shared markerPane actually saw.
const attachSeqs = (g: StubGroup) => g.added.map((l) => l.seq);

async function mounted(n = { communities: 2, practices: 1 }) {
  const stub = installLeafletStub();
  const wrapper = mount(MarketMapView, {
    props: {
      practices: practices(n.practices),
      communities: communities(n.communities),
      activeLayer: 'income',
      showDrive: false,
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

    // The invariant, whether or not the overlay redrew: every overlay layer on the map was
    // attached before every pin. `practices` is not one of the reference's five area-effect
    // deps, so since the I1 ruling (2026-09-07) the overlay is NOT rebuilt here — it simply
    // stays where it is, and refilling the pins group moves the pins to the end of the shared
    // panes on their own. Before that ruling this same trigger rebuilt all 12,560 rectangles.
    expectOverlayBeforePins(stub);

    // The same invariant read off the divIcon stream, stated semantically rather than as a
    // literal ['overlay', 'overlay', 'pins'] — that array pinned the fixture's cardinality
    // (two communities, one practice) into the expectation, so adding a third community
    // would have failed a test about ORDER for a reason that has nothing to do with order.
    const order = drawOrder(stub, from);
    expect(order, 'a pins-only change rebuilt the mosaic — the reference\'s area effect would not have').not.toContain('overlay');
    expect(order).toContain('pins');
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
      expect(attachSeqs(overlay)).toHaveLength(cellCount(n.communities));
      expect(attachSeqs(pins)).toHaveLength(n.practices);
    });
  }

  // Phase 2/6, root cause measured rather than assumed. Two separate watchers are unsafe in
  // TWO independent ways, and a probe with the overlay watcher declared FIRST (the faithful
  // mirror of MarketMapV3.jsx's area effect → pin effect) demonstrated both:
  //
  //   1. an OVERLAY-ONLY trigger (`activeLayer`, `communities`, a drive-time toggle) fires
  //      only the overlay watcher, so the mosaic rectangles are re-attached to the shared
  //      panes AFTER the untouched pins and paint on top of them — overlay seq 12,13
  //      against a pin still at 11. Declaration order cannot help: the other watcher never
  //      ran at all;
  //   2. when BOTH fire, Vue's pre-flush queue orders the two jobs by when their sources
  //      were TOUCHED during the parent's patch, not by declaration order — pins landed at
  //      seq 14 ahead of overlay at 15,16 even with the overlay watcher declared first.
  //
  // One merged watcher that always runs drawOverlay() then drawPins() is the only shape
  // that closes both. These two tests pin one failure mode each.
  it('holds the order when the trigger is an OVERLAY-ONLY prop (activeLayer), which fires no pins work of its own', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(2),
        communities: communities(3),
        activeLayer: 'income',
        showDrive: false,
        center: [30.31, -97.75],
        zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();
    expectOverlayBeforePins(stub);

    await wrapper.setProps({ activeLayer: 'density' }); // touches nothing on the pins side
    expectOverlayBeforePins(stub);
    const { overlay, pins } = layerGroups(stub);
    expect(attachSeqs(overlay)).toHaveLength(cellCount(3)); // rebuilt…
    expect(attachSeqs(pins)).toHaveLength(2);               // …and so were the pins, after them
  });

  it('holds the order when the trigger is a community change rather than a practice change', async () => {
    const { stub, wrapper } = await mounted({ communities: 2, practices: 3 });
    await wrapper.setProps({ communities: communities(4) });
    expectOverlayBeforePins(stub);
    const { overlay, pins } = layerGroups(stub);
    expect(attachSeqs(overlay)).toHaveLength(cellCount(4)); // the mosaic of the NEW communities
    expect(attachSeqs(pins)).toHaveLength(3);
  });
});

// ---------------------------------------------------------------------------------------
// Review I1 (controller ruling, 2026-09-07): the overlay rebuild is REFERENCE-EXACT.
//
// MarketMapV3.jsx's area effect (`:268`) has five deps — [communities, activeLayer,
// showDrive, driveCenter && driveCenter[0], status] — and React re-runs it only when one of
// them changed. The merged watcher above keeps its deliberate superset of those deps,
// because one callback is the only shape that can promise the overlay-then-pins pane order;
// the overlay REBUILD is gated on the reference's own five instead, compared the way React
// compares them (`communities` by identity, the rest by value).
//
// A pin or card SELECTION still rebuilds the mosaic, and that cost is the DESIGN's, not the
// port's: selecting moves `driveCenter` (`sel ? [sel.lat, sel.lng] : cfg.center`,
// logic.js:382) and `showDrive` (`!!sel`, :578), so React re-runs its area effect too. What
// no longer happens is a full 12,560-rectangle rebuild on a trigger that leaves all five
// untouched — `practices` and `activeId` (logic.js:361, `s.mdSel`) are the two deps the
// superset added.
// ---------------------------------------------------------------------------------------
describe('MarketMapView — the overlay redraws on the reference\'s five area deps, and only those', () => {
  it('rebuilds no mosaic rectangle when only activeId changes, and redraws the pins with the new selection', async () => {
    const stub = installLeafletStub();
    const ps = practices(3);
    const wrapper = mount(MarketMapView, {
      props: {
        practices: ps, communities: communities(4), activeLayer: 'income',
        showDrive: false, center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();
    const rectsAtMount = stub.calls.filter((c) => c.fn === 'rectangle').length;
    expect(rectsAtMount, 'the fixture never shaded a mosaic, so it cannot show one being skipped').toBe(cellCount(4));
    const overlayAtMount = attachSeqs(layerGroups(stub).overlay);
    const from = stub.calls.length;

    await wrapper.setProps({ activeId: ps[2].id });

    const rebuilt = stub.calls.filter((c) => c.fn === 'rectangle').length - rectsAtMount;
    expect(rebuilt, `an activeId-only change rebuilt ${rebuilt} mosaic rectangles; the reference's area effect would have drawn none`).toBe(0);
    // A SKIP, not a silent loss: the same layer objects are still on the map (`seq` is
    // stamped once per addTo, so an identical seq list is the same attachments), with the
    // pins re-added after them.
    const { overlay, pins } = layerGroups(stub);
    expect(attachSeqs(overlay), 'the mosaic left the map — it was cleared and not refilled').toEqual(overlayAtMount);
    expect(drawOrder(stub, from), 'the pins did not redraw for the new selection').toEqual(['pins', 'pins', 'pins']);
    expectOverlayBeforePins(stub);
    expect((pins.added[2] as unknown as { options: { zIndexOffset: number } }).options.zIndexOffset).toBe(1000);
  });

  it('rebuilds the overlay and THEN the pins when driveCenter[0] moves — which is what a selection does', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(2), communities: communities(4), activeLayer: 'income',
        showDrive: true, driveCenter: [30.4, -97.6], center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();
    const rectsAtMount = stub.calls.filter((c) => c.fn === 'rectangle').length;
    const from = stub.calls.length;

    await wrapper.setProps({ driveCenter: [30.9, -97.1] });

    expect(
      stub.calls.filter((c) => c.fn === 'rectangle').length - rectsAtMount,
      'driveCenter moved and the mosaic did not redraw — the gate is skipping one of the reference\'s own five deps'
    ).toBe(cellCount(4));
    const order = drawOrder(stub, from);
    expect(order).toContain('overlay');
    expect(order).toContain('pins');
    expect(order.indexOf('pins'), 'a pin was drawn before an overlay').toBeGreaterThan(order.lastIndexOf('overlay'));
    expectOverlayBeforePins(stub);
    const { overlay } = layerGroups(stub);
    expect((overlay.added.find((l) => typeof l.options?.radius === 'number') as unknown as { center: unknown }).center,
      'the ring did not move to the new driveCenter').toEqual([30.9, -97.1]);
  });
});

// Re-review minor 5: the group identification itself, stated as a property. The helper must
// name the groups from what filled them, so the two labels cannot swap when the engine's
// creation order does. Proven by break-and-restore as well: swapping MarketMapView's
// `groups: ['overlay', 'pins']` to `['pins', 'overlay']` leaves all of these green, where an
// index-keyed helper would read the invariant backwards.
describe('MarketMapView — group identification is by role, not creation order', () => {
  it('labels each group by the renderer that filled it, and refuses a group holding both', async () => {
    const { stub } = await mounted({ communities: 3, practices: 2 });
    const { overlay, pins } = layerGroups(stub);

    expect(overlay.added).toHaveLength(cellCount(3));
    expect(new Set(overlay.added.map(roleOf))).toEqual(new Set(['overlay']));
    expect(pins.added.map(roleOf)).toEqual(['pins', 'pins']);
    expect(overlay).not.toBe(pins);
    // The labels track the CONTENT, so they cannot both come back as the same object even
    // though the two groups are indistinguishable by construction.
    expect(new Set([overlay, pins]).size).toBe(2);
  });

  it('recognises a drive-time ring as overlay content even though it is a circle, not a marker', async () => {
    const { stub, wrapper } = await mounted({ communities: 2, practices: 1 });
    await wrapper.setProps({ showDrive: true, driveCenter: [30.5, -97.8] });
    const { overlay, pins } = layerGroups(stub);
    expect(overlay.added.filter((l) => typeof l.options?.radius === 'number')).toHaveLength(1);
    expect(pins.added).toHaveLength(1);
    expectOverlayBeforePins(stub);
  });
});

describe('MarketMapView — teardown', () => {
  it('destroys the engine on unmount, once it exists', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: communities(1),
        center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();

    wrapper.unmount();
    expect((stub.map as { removed?: boolean }).removed).toBe(true);
  });
});

describe('MarketMapView — onMounted guards and error handling', () => {
  it('unmounting before createEngine()/mount() settles hits the (!host.value) guard instead of crashing', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: communities(1),
        center: [30.31, -97.75], zoom: 10
      }
    });
    // Unmount synchronously, before the async onMounted chain (createEngine() await, then
    // e.mount()'s own await) has a chance to resume — `host.value` is null by then.
    wrapper.unmount();
    await flushPromises();
    // The absence of an unhandled rejection or thrown error (vitest fails the test on
    // either) proves the guard was hit rather than a crash; asserting `L.map` was never
    // called is the discriminating check that it's the (!host.value) guard doing that,
    // not e.g. a mount that happened to complete harmlessly after unmount.
    expect(stub.calls.filter((c) => c.fn === 'map')).toHaveLength(0);
  });

  it('shows "Map unavailable" when the engine fails to mount (onMounted\'s catch branch)', async () => {
    // Deliberately do NOT installLeafletStub(): loadLeaflet() resolves to `undefined`
    // (window.L was never set), so LeafletMapEngine.mount()'s `L.map(...)` throws and the
    // rejection reaches onMounted's try/catch.
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: communities(1),
        center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.text().includes('Map unavailable'), { timeout: 5000, interval: 1 });
    expect(wrapper.find('button[aria-label="Zoom in"]').exists()).toBe(false);
  });

  it('a watched prop change that lands before the engine finishes mounting hits drawOverlay/drawPins\' (!engine) guards, not a crash', async () => {
    let release!: () => void;
    loader.gate = new Promise<void>((r) => { release = r; });
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: communities(2),
        activeLayer: 'income', center: [30.31, -97.75], zoom: 10
      }
    });

    // The merged watcher (communities is one of its deps) fires now, while `engine` is still
    // null — loadLeaflet() is gated open, so onMounted's await never resumed.
    await wrapper.setProps({ communities: communities(3) });
    expect(stub.calls.filter((c) => c.fn === 'marker'), 'nothing should draw before the engine exists').toHaveLength(0);

    release();
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();
    // Once the engine is ready, the `status` flip runs the merged watcher and THAT paints the
    // final props: onMounted has not called drawOverlay()/drawPins() itself since V5 (see the
    // watcher's own comment in MarketMapView.vue) — calling them there built every layer twice.
    expect(stub.calls.some((c) => c.fn === 'marker'), 'the engine should draw once it exists').toBe(true);
  });
});

describe('MarketMapView — active-layer data gaps', () => {
  it('skips a community missing a value for the active layer, drawing nothing for it', async () => {
    const stub = installLeafletStub();
    const noIncomeData = { ...community(5), values: { density: community(5).values.density } }; // no `income` key
    const sites = [community(0), noIncomeData];
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: sites,
        activeLayer: 'income', center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();

    const { overlay } = layerGroups(stub);
    // Only community(0) has an `income` value, so every shaded cell is one of ITS cells: the
    // cells the mosaic assigned to the other community are dropped, not shaded with a
    // missing value (a `v == null` cell would have drawn as `undefined`-coloured).
    const tips = overlay.added.map((l) => (l as unknown as { tooltip: { text: string } }).tooltip.text);
    expect(tips.length).toBeGreaterThan(0);
    expect(tips.every((t) => t.includes('Community 0'))).toBe(true);
    expect(tips.some((t) => t.includes('Community 5'))).toBe(false);
    // …and strictly fewer than the mosaic's own cell count, which is the discriminating proof
    // that cells really were skipped rather than reassigned to the community that has data.
    expect(tips.length).toBeLessThan(mosaicCells(sites, mosaicBbox(sites), MOSAIC_STEP).length);
  });
});

describe('MarketMapView — practice pins: active state, click-through', () => {
  it('stacks the active pin above the rest (zIndexOffset 1000) and calls onSelect when clicked', async () => {
    const stub = installLeafletStub();
    const onSelect = vi.fn();
    const ps = practices(2);
    const wrapper = mount(MarketMapView, {
      props: {
        practices: ps, communities: communities(1),
        activeId: ps[1].id, onSelect,
        center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();

    // Read the group's current CONTENTS, not the raw call log: drawPins() clears before it
    // refills, so the group is the state of the map while the log is its whole history.
    // (This case and the next reach for the group BY INDEX rather than through
    // `layerGroups(stub)`, which every V3 case uses: neither fixture passes an `activeLayer`,
    // so nothing fills the overlay group and a helper that labels each group by the renderer
    // that filled it has nothing to read. Everywhere the overlay is drawn, use the helper.)
    const pinsGroup = (stub.map.added as { clearLayers?: unknown; added: unknown[] }[]).filter((g) => g.clearLayers)[1];
    expect(pinsGroup.added).toHaveLength(2);
    expect((pinsGroup.added[0] as { options: { zIndexOffset: number } }).options.zIndexOffset).toBe(0);    // ps[0], not active
    expect((pinsGroup.added[1] as { options: { zIndexOffset: number } }).options.zIndexOffset).toBe(1000); // ps[1], active

    const clickedPin = pinsGroup.added[1] as { on_click?: () => void };
    expect(clickedPin.on_click).toBeTypeOf('function');
    clickedPin.on_click!();
    expect(onSelect).toHaveBeenCalledWith(ps[1].id);
  });

  it('a click does nothing (and does not throw) when no onSelect prop is given', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: communities(1),
        center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();

    const pinsGroup = (stub.map.added as { clearLayers?: unknown; added: unknown[] }[]).filter((g) => g.clearLayers)[1];
    const clickedPin = pinsGroup.added[0] as { on_click?: () => void };
    const callsBefore = stub.calls.length;
    expect(() => clickedPin.on_click!()).not.toThrow();
    // `not.toThrow()` alone would also pass a broken guard that quietly did something else on
    // click; the call log being unchanged is the discriminating proof that nothing happened
    // at all — `props.onSelect && …` really did short-circuit rather than reach the engine.
    expect(stub.calls.length).toBe(callsBefore);
  });
});

describe('MarketMapView — driveCenter reactivity', () => {
  it('redraws the drive-time ring when driveCenter itself changes (not just the props it defaults from)', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: communities(1),
        showDrive: true, driveCenter: [30.4, -97.6],
        center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();

    const overlayGroup = (stub.map.added as { clearLayers?: unknown; added: { center?: unknown }[] }[]).filter((g) => g.clearLayers)[0];
    expect(overlayGroup.added).toHaveLength(1); // one dashed ring, centred on driveCenter
    expect(overlayGroup.added[0].center).toEqual([30.4, -97.6]);

    await wrapper.setProps({ driveCenter: [30.9, -97.1] });
    expect(overlayGroup.added).toHaveLength(1); // cleared and rebuilt, still exactly one ring
    expect(overlayGroup.added[0].center, 'the ring did not move to the new driveCenter').toEqual([30.9, -97.1]);
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

// ---------------------------------------------------------------------------------------
// V3 (Rev 2). C5 community mosaic shading, C6 pins + persistent callout + panInside,
// C7 the single dashed drive-time ring, C11 no scale control, C13 onBasemap gates the tabs.
// ---------------------------------------------------------------------------------------
describe('MarketMapView — the V3 map', () => {
  // vue-tsc derives MarketMapView's public prop types from its runtime `defineProps`, where
  // `{ type: String, default: null }` widens to `string | undefined` — plain JS cannot spell
  // "String | null", which is what the design's own `data-props` declare (`Practice Match
  // V3.dc.html:324`) and what the generated App.vue passes. The nulls are load-bearing at
  // runtime: Vue substitutes a prop's DEFAULT for `undefined`, so `center: undefined` would
  // silently restore the Austin centre the no-centre case asserts the absence of.
  //
  // So each null is cast on its own VALUE and the props object itself is left un-cast: a
  // whole-object cast (`as Record<string, never>`) also silenced prop value typing, and
  // `zoom: 'ten'` typechecked clean (fix round 1, L4). It no longer does.
  const NO_ID = null as unknown as string;
  const NO_FN = null as unknown as (...args: never[]) => unknown;
  const NO_LATLNG = null as unknown as unknown[];

  const v3Props = (over: Record<string, unknown> = {}) => ({
    practices: practices(3), communities: communities(4), activeLayer: 'income', basemap: 'map',
    activeId: NO_ID, onSelect: NO_FN, onArea: NO_FN, center: [30.31, -97.75], zoom: 10,
    driveCenter: NO_LATLNG, showDrive: false, resizeKey: '', recenterKey: 0, ...over
  });

  it('mounts with no scale control and attribution on — the app owns the bottom-right corner for the Layers button', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props() });
    await flushPromises();
    expect(stub.calls[0].args[1]).toEqual({ center: [30.31, -97.75], zoom: 10, zoomControl: false, attributionControl: true });
    expect(stub.calls.filter((c) => c.fn === 'control.scale')).toHaveLength(0);
    expect(stub.calls.filter((c) => c.fn === 'control.zoom')).toHaveLength(0);
  });

  it('shades one mosaic cell per community cell for the active layer, on the shared canvas renderer', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props() });
    await flushPromises();
    const rects = stub.calls.filter((c) => c.fn === 'rectangle');
    // Exactly one rectangle per mosaic cell, built ONCE — `toBeGreaterThan(0)` could not tell
    // one draw from two, which is how the double draw at mount hid (M2).
    expect(rects).toHaveLength(cellCount(4));
    expect(stub.calls.filter((c) => c.fn === 'canvas')).toHaveLength(1);
    for (const r of rects) {
      expect((r.args[1] as { renderer: unknown; fillOpacity: number; stroke: boolean }).renderer).toBe(stub.canvas);
      expect((r.args[1] as { fillOpacity: number }).fillOpacity).toBe(0.5);
      expect((r.args[1] as { stroke: boolean }).stroke).toBe(false);
      expect((r.args[1] as { fillColor: string }).fillColor).toBe('#4c9a6a');
      // M1: a non-interactive Path takes no pointer events, so the rf-tip would never open
      // and the cell click would never fire — the README acceptance criterion, in one word.
      expect((r.args[1] as { interactive: boolean }).interactive).toBe(true);
    }
  });

  it('draws nothing when no layer is active, and re-shades when the active layer changes', async () => {
    const stub = installLeafletStub();
    const w = mount(MarketMapView, { props: v3Props({ activeLayer: null }) });
    await flushPromises();
    expect(stub.calls.filter((c) => c.fn === 'rectangle')).toHaveLength(0);
    await w.setProps({ activeLayer: 'income' });
    await flushPromises();
    expect(stub.calls.filter((c) => c.fn === 'rectangle').length).toBeGreaterThan(0);
  });

  it('skips a community with no value for the active layer rather than shading it', async () => {
    const stub = installLeafletStub();
    const blank = { name: 'Blank', lat: 30.5, lng: -97.8, values: {} };
    mount(MarketMapView, { props: v3Props({ communities: [...communities(2), blank], activeLayer: 'density' }) });
    await flushPromises();
    for (const r of stub.calls.filter((c) => c.fn === 'rectangle')) {
      expect((r.args[1] as { fillColor: string }).fillColor).toBe('#2f7d55');
    }
  });

  it('binds the sticky rf-tip carrying name, metric name, value and source note', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, {
      props: v3Props({ communities: [{ name: 'Cedar Park', lat: 30.5, lng: -97.8, metricName: 'Median household income', sourceNote: 'ACS 2019–2023', values: { income: { t: 0.5, label: '$118,400', color: '#4c9a6a' } } }] })
    });
    await flushPromises();
    const overlay = layerGroups(stub).overlay;
    const tip = (overlay.added[0] as unknown as { tooltip: { text: string; opts: unknown } }).tooltip;
    expect(tip.opts).toEqual({ sticky: true, className: 'rf-tip' });
    // L6: the WHOLE string, against the reference's literal (MarketMapV3.jsx:256-264). Four
    // substrings left the tip's own inline styles unguarded — `min-width:150px → 140px` used
    // to survive — and tooltips are absent from V9's DOM oracle, so nothing else would notice.
    expect(tip.text).toBe(
      '<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;min-width:150px">' +
        '<div style="font-size:12.5px;font-weight:800;color:#003a70">Cedar Park</div>' +
        '<div style="font-size:11px;color:#494949;margin-top:3px">Median household income</div>' +
        '<div style="font-size:15px;font-weight:800;color:#003a70;margin-top:1px">$118,400</div>' +
        '<div style="font-size:10px;color:#767676;margin-top:5px">ACS 2019–2023</div>' +
      '</div>'
    );
  });

  it('clicking a mosaic cell reports its community through onArea', async () => {
    const stub = installLeafletStub();
    const seen: string[] = [];
    mount(MarketMapView, {
      props: v3Props({ communities: [{ name: 'Cedar Park', lat: 30.5, lng: -97.8, values: { income: { t: 0.5, label: '$118K', color: '#4c9a6a' } } }], onArea: (n: string) => seen.push(n) })
    });
    await flushPromises();
    const overlay = layerGroups(stub).overlay;
    (overlay.added[0] as unknown as { on_click: () => void }).on_click();
    expect(seen).toEqual(['Cedar Park']);
  });

  it('draws ONE dashed unfilled drive-time ring at 16 000 m, not two filled circles (C7)', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props({ showDrive: true, driveCenter: [30.5052, -97.8203] }) });
    await flushPromises();
    const overlay = layerGroups(stub).overlay;
    expect(overlay.added.filter((l) => typeof l.options?.radius === 'number')).toHaveLength(1);
    const circles = stub.calls.filter((c) => c.fn === 'circle');
    expect(circles).toHaveLength(1);
    expect(circles[0].args).toEqual([[30.5052, -97.8203], { radius: 16000, color: '#003a70', weight: 1.5, dashArray: '4 4', fill: false, interactive: false }]);
  });

  it('draws no ring when showDrive is false, and none when there is no drive centre to draw it around', async () => {
    const stub = installLeafletStub();
    const w = mount(MarketMapView, { props: v3Props({ showDrive: false, driveCenter: [30.5, -97.8] }) });
    await flushPromises();
    expect(stub.calls.filter((c) => c.fn === 'circle')).toHaveLength(0);
    // L1: the reference draws only for a real drive centre (MarketMapV3.jsx:230). The map's
    // own centre is NOT a fallback, so turning the ring on without one still draws nothing.
    await w.setProps({ showDrive: true, driveCenter: NO_LATLNG });
    await flushPromises();
    expect(stub.calls.filter((c) => c.fn === 'circle')).toHaveLength(0);
    // …and with no map centre either, the view watcher's own `props.center &&` guards hold.
    await w.setProps({ center: NO_LATLNG });
    await flushPromises();
    expect(stub.calls.filter((c) => c.fn === 'circle')).toHaveLength(0);
  });

  it('uses practicePin at [78, 34] / [39, 34] and binds the rf-callout at the unselected offset', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props({ practices: practices(1) }) });
    await flushPromises();
    expect(stub.calls.find((c) => c.fn === 'divIcon')!.args[0]).toMatchObject({ className: '', iconSize: [78, 34], iconAnchor: [39, 34] });
    const pins = layerGroups(stub).pins;
    expect((pins.added[0] as unknown as { tooltip: { opts: unknown } }).tooltip.opts)
      .toEqual({ direction: 'top', offset: [0, -34], className: 'rf-callout', permanent: false, opacity: 1 });
  });

  it('selecting a practice makes its callout permanent, opens it, and pans it inside with [48, 110]', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props({ practices: practices(2), activeId: 'p1' }) });
    await flushPromises();
    const pins = layerGroups(stub).pins;
    const selected = pins.added.find((l) => (l as unknown as { tooltip?: { opts: { permanent: boolean } } }).tooltip?.opts.permanent)!;
    expect((selected as unknown as { tooltip: { opts: unknown } }).tooltip.opts)
      .toEqual({ direction: 'top', offset: [0, -22], className: 'rf-callout', permanent: true, opacity: 1 });
    expect((selected as unknown as { tooltipOpened: number }).tooltipOpened).toBe(1);
    expect((selected as unknown as { options: { zIndexOffset: number } }).options.zIndexOffset).toBe(1000);
    expect((stub.map as unknown as { pannedInside: unknown }).pannedInside).toEqual([[30.32, -97.74], { padding: [48, 110], animate: true }]);
  });

  it('every practice pin is focusable and carries the reference\'s native title (MarketMapV3.jsx:288-289)', async () => {
    const stub = installLeafletStub();
    const one = { id: 'p0', lat: 30.31, lng: -97.75, name: 'Cedar Park Veterinary', priceLabel: '$1.45M' };
    mount(MarketMapView, { props: v3Props({ practices: [one] }) });
    await flushPromises();
    // Leaflet turns these into the icon's tabindex and title attribute, so they are part of
    // the design's DOM and the DOM oracle compares them.
    const m = stub.calls.find((c) => c.fn === 'marker')!;
    expect((m.args[1] as { keyboard: boolean }).keyboard).toBe(true);
    expect((m.args[1] as { title: string }).title).toBe('Cedar Park Veterinary — $1.45M');
  });

  it('draws each layer exactly ONCE per mount — the merged watcher owns the initial draw, as the reference\'s effects do', async () => {
    const stub = installLeafletStub();
    mount(MarketMapView, { props: v3Props({ practices: practices(1), activeId: 'p0', showDrive: true, driveCenter: [30.5, -97.8] }) });
    await flushPromises();
    // MarketMapV3.jsx's effects run at mount, bail on `!mapRef.current`, and run once when
    // status flips. The port's merged watcher has `status` among its deps and does the same:
    // onMounted must NOT also call drawOverlay()/drawPins() itself, or every layer — ~2 000
    // canvas rectangles here — is built twice on a screen V10 mounts on a 390 px phone.
    expect(stub.calls.filter((c) => c.fn === 'rectangle')).toHaveLength(cellCount(4));
    expect(stub.calls.filter((c) => c.fn === 'circle')).toHaveLength(1);
    expect(stub.calls.filter((c) => c.fn === 'marker')).toHaveLength(1);
    expect((stub.map as unknown as { pannedInsideCount: number }).pannedInsideCount).toBe(1);
  });

  it('clicking a pin reports its id through onSelect', async () => {
    const stub = installLeafletStub();
    const seen: string[] = [];
    mount(MarketMapView, { props: v3Props({ practices: practices(1), onSelect: (id: string) => seen.push(id) }) });
    await flushPromises();
    const pins = layerGroups(stub).pins;
    (pins.added[0] as unknown as { on_click: () => void }).on_click();
    expect(seen).toEqual(['p0']);
  });

  it('renders the Map | Satellite tabs only when onBasemap is passed (desktop), never without it (mobile)', async () => {
    installLeafletStub();
    const desktop = mount(MarketMapView, { props: v3Props({ onBasemap: () => {} }) });
    await flushPromises();
    expect(desktop.findAll('button[aria-pressed]')).toHaveLength(2);
    expect(desktop.find('button[aria-pressed="true"]').text()).toBe('Map');

    installLeafletStub();
    const mobile = mount(MarketMapView, { props: v3Props() });
    await flushPromises();
    expect(mobile.findAll('button[aria-pressed]')).toHaveLength(0);
    expect(mobile.findAll('button[aria-label]').map((b) => b.attributes('aria-label'))).toEqual(['Zoom in', 'Zoom out']);
  });

  it('the basemap tabs call onBasemap and the zoom buttons drive the engine', async () => {
    const stub = installLeafletStub();
    const picked: string[] = [];
    const w = mount(MarketMapView, { props: v3Props({ onBasemap: (k: string) => picked.push(k) }) });
    await flushPromises();
    await w.findAll('button[aria-pressed]')[1].trigger('click');
    expect(picked).toEqual(['satellite']);
    const before = stub.map.zoom;
    await w.find('button[aria-label="Zoom in"]').trigger('click');
    expect(stub.map.zoom).toBe(before + 1);
    await w.find('button[aria-label="Zoom out"]').trigger('click');
    expect(stub.map.zoom).toBe(before);
  });

  it('recenterKey re-applies the view without a prop change to centre or zoom', async () => {
    const stub = installLeafletStub();
    const w = mount(MarketMapView, { props: v3Props() });
    await flushPromises();
    stub.map.setView([1, 2], 3);
    await w.setProps({ recenterKey: 1 });
    await flushPromises();
    expect(stub.map.center).toEqual([30.31, -97.75]);
    expect(stub.map.zoom).toBe(10);
  });

  it('the zoom buttons carry the reference\'s own width:auto — the DOM oracle compares live el.style, not computed layout', async () => {
    installLeafletStub();
    const w = mount(MarketMapView, { props: v3Props(), attachTo: document.body });
    await flushPromises();
    for (const label of ['Zoom in', 'Zoom out']) {
      expect((w.find(`button[aria-label="${label}"]`).element as HTMLElement).style.width).toBe('auto');
    }
    w.unmount();
  });

  it('a mosaic cell click is inert when onArea is absent, and the basemap tabs vanish when onBasemap is withdrawn', async () => {
    const stub = installLeafletStub();
    const w = mount(MarketMapView, { props: v3Props({ onBasemap: () => {}, onArea: null }) });
    await flushPromises();
    const overlay = layerGroups(stub).overlay;
    expect(() => (overlay.added[0] as unknown as { on_click: () => void }).on_click()).not.toThrow();
    await w.setProps({ onBasemap: NO_FN });
    expect(w.findAll('button[aria-pressed]')).toHaveLength(0);
  });

  it('renders at a 390 px phone width — no fixed widths keep the map from filling its host', async () => {
    installLeafletStub();
    const w = mount(MarketMapView, { props: v3Props(), attachTo: document.body });
    await flushPromises();
    const root = w.element as HTMLElement;
    expect(root.style.position).toBe('absolute');
    expect(root.style.inset).toBe('0px');
    const hostEl = root.firstElementChild as HTMLElement;
    expect(hostEl.style.position).toBe('absolute');
    expect(hostEl.style.inset).toBe('0px');
    expect(hostEl.outerHTML).not.toMatch(/width:\s*\d+px/);
    const fixed = [...root.querySelectorAll<HTMLElement>('*')].map((el) => el.style.width).filter((wd) => /px$/.test(wd));
    expect(fixed).toEqual(['132px', '1px']);          // the control cluster and its hairline
    expect(fixed.every((wd) => parseFloat(wd) <= 390)).toBe(true);
    w.unmount();
  });
});
