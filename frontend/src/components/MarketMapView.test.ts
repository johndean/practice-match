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

// The two draws are told apart by the divIcon HTML they build: markers.js `dot()` opens
// with the bubble's width/height, `pricePin()` with the pill's font-family.
function drawOrder(stub: LeafletStub, from: number): string[] {
  return stub.calls
    .slice(from)
    .filter((c) => c.fn === 'divIcon')
    .map((c) => (/^<div style="width:/.test((c.args[0] as { html: string }).html) ? 'overlay' : 'pins'));
}

// Re-review minor 5: the two layer groups used to be picked out by CONSTRUCTION ORDER —
// `groups[0]` is overlay because MarketMapView passes `groups: ['overlay', 'pins']` at mount.
// That is a second hidden coupling of exactly the kind this file exists to be free of: swap
// the component's two group names and an index-keyed helper silently reads the invariant
// backwards, failing (or worse, passing) for a reason that has nothing to do with ordering.
//
// Each group is identified by ITS ROLE instead — which production renderer filled it. The
// engine keys its groups by name, so role is what the name means: `markers.js` `dot()` opens
// a community bubble's HTML with the div's width, `pricePin()` opens the pill with a
// font-family, and a drive-time ring is an L.circle carrying a radius. Creation order is
// never consulted, and the helper asserts that each group holds exactly one role, so a
// component change that mixed the two would fail here rather than be mislabelled.
type StubLayer = { seq: number; options?: { radius?: number; icon?: { icon?: { html?: string } } } };
type StubGroup = { clearLayers?: unknown; added: StubLayer[] };

const roleOf = (l: StubLayer): 'overlay' | 'pins' => {
  if (typeof l.options?.radius === 'number') return 'overlay';        // a drive-time L.circle
  return /^<div style="width:/.test(l.options?.icon?.icon?.html ?? '') ? 'overlay' : 'pins';
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

// Re-review minor 5: the group identification itself, stated as a property. The helper must
// name the groups from what filled them, so the two labels cannot swap when the engine's
// creation order does. Proven by break-and-restore as well: swapping MarketMapView's
// `groups: ['overlay', 'pins']` to `['pins', 'overlay']` leaves all of these green, where an
// index-keyed helper would read the invariant backwards.
describe('MarketMapView — group identification is by role, not creation order', () => {
  it('labels each group by the renderer that filled it, and refuses a group holding both', async () => {
    const { stub } = await mounted({ communities: 3, practices: 2 });
    const { overlay, pins } = layerGroups(stub);

    expect(overlay.added.map(roleOf)).toEqual(['overlay', 'overlay', 'overlay']);
    expect(pins.added.map(roleOf)).toEqual(['pins', 'pins']);
    expect(overlay).not.toBe(pins);
    // The labels track the CONTENT, so they cannot both come back as the same object even
    // though the two groups are indistinguishable by construction.
    expect(new Set([overlay, pins]).size).toBe(2);
  });

  it('recognises a drive-time ring as overlay content even though it is a circle, not a marker', async () => {
    const { stub, wrapper } = await mounted({ communities: 2, practices: 1 });
    await wrapper.setProps({ layers: { practices: true, competition: false, drive5: true, drive10: true } });
    const { overlay, pins } = layerGroups(stub);
    expect(overlay.added.filter((l) => typeof l.options?.radius === 'number')).toHaveLength(2);
    expect(pins.added).toHaveLength(1);
    expectOverlayBeforePins(stub);
  });
});

describe('MarketMapView — competition layer', () => {
  it('draws a purple competition marker per community with vets > 0, skipping ones with none', async () => {
    const stub = installLeafletStub();
    const withNoVets = { ...community(2), vets: 0 };
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1),
        communities: [...communities(2), withNoVets],
        layers: { practices: true, competition: true, drive5: false, drive10: false },
        valueLayer: undefined,
        center: [30.31, -97.75],
        zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();

    const { overlay } = layerGroups(stub);
    // Two of the three communities have vets > 0 (community(0)=4, community(1)=5); the third
    // (0 vets, the falsy-guard branch) is skipped, so exactly two markers get drawn.
    expect(overlay.added).toHaveLength(2);
    const html = (overlay.added[0] as { options?: { icon?: { icon?: { html?: string } } } }).options?.icon?.icon?.html ?? '';
    expect(html).toContain('rgba(120,86,190,.75)'); // markers.js dot()'s competition colour
  });
});

describe('MarketMapView — zoom/recenter controls and teardown', () => {
  it('the zoom-in, zoom-out and recenter buttons drive the engine', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: communities(1),
        layers: { practices: true, competition: false, drive5: false, drive10: false },
        valueLayer: undefined, center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();

    const zoomBefore = stub.map.zoom;
    await wrapper.find('button[aria-label="Zoom in"]').trigger('click');
    expect(stub.map.zoom).toBe(zoomBefore + 1);
    await wrapper.find('button[aria-label="Zoom out"]').trigger('click');
    expect(stub.map.zoom).toBe(zoomBefore);
    await wrapper.find('button[aria-label="Recenter"]').trigger('click');
    expect((stub.map as { lastSetView?: unknown }).lastSetView).toEqual([[30.31, -97.75], 10, undefined]);
  });

  it('destroys the engine on unmount, once it exists', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: communities(1),
        layers: { practices: true, competition: false, drive5: false, drive10: false },
        valueLayer: undefined, center: [30.31, -97.75], zoom: 10
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
        layers: { practices: true, competition: false, drive5: false, drive10: false },
        valueLayer: undefined, center: [30.31, -97.75], zoom: 10
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
        layers: { practices: true, competition: false, drive5: false, drive10: false },
        valueLayer: undefined, center: [30.31, -97.75], zoom: 10
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
        layers: { practices: true, competition: false, drive5: false, drive10: false },
        valueLayer: 'income', center: [30.31, -97.75], zoom: 10
      }
    });

    // The merged watcher (communities is one of its deps) fires now, while `engine` is still
    // null — loadLeaflet() is gated open, so onMounted's await never resumed.
    await wrapper.setProps({ communities: communities(3) });
    expect(stub.calls.filter((c) => c.fn === 'marker'), 'nothing should draw before the engine exists').toHaveLength(0);

    release();
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();
    // Once the engine is ready, onMounted's own drawOverlay()/drawPins() paint the final props.
    expect(stub.calls.some((c) => c.fn === 'marker'), 'the engine should draw once it exists').toBe(true);
  });
});

describe('MarketMapView — value-layer data gaps', () => {
  it('skips a community missing a value for the active valueLayer, drawing nothing for it', async () => {
    const stub = installLeafletStub();
    const noIncomeData = { ...community(5), values: { density: community(5).values.density } }; // no `income` key
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: [community(0), noIncomeData],
        layers: { practices: true, competition: false, drive5: false, drive10: false },
        valueLayer: 'income', center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();

    const { overlay } = layerGroups(stub);
    // Only community(0) has an `income` value; the other is skipped, not drawn as e.g. NaN-sized.
    expect(overlay.added).toHaveLength(1);
  });
});

describe('MarketMapView — practice pins: layer toggle, active state, click-through', () => {
  it('draws no pins at all when the practices layer is off', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(2), communities: communities(1),
        layers: { practices: false, competition: false, drive5: false, drive10: false },
        valueLayer: undefined, center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();
    expect(stub.calls.filter((c) => c.fn === 'marker')).toHaveLength(0);
  });

  it('stacks the active pin above the rest (zIndexOffset 1000) and calls onSelect when clicked', async () => {
    const stub = installLeafletStub();
    const onSelect = vi.fn();
    const ps = practices(2);
    const wrapper = mount(MarketMapView, {
      props: {
        practices: ps, communities: communities(1),
        layers: { practices: true, competition: false, drive5: false, drive10: false },
        valueLayer: undefined, activeId: ps[1].id, onSelect,
        center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();

    // Read the group's current CONTENTS, not the raw call log: `status` flipping to 'ready'
    // is itself one of the merged watcher's deps, so it redraws once more right after
    // onMounted's own direct call — idempotently, since drawPins() clears before it refills.
    // (Every other test in this file asserts the same way, via .added snapshots.)
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
        layers: { practices: true, competition: false, drive5: false, drive10: false },
        valueLayer: undefined, center: [30.31, -97.75], zoom: 10
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
  it('redraws the drive-time rings when driveCenter itself changes (not just the props it defaults from)', async () => {
    const stub = installLeafletStub();
    const wrapper = mount(MarketMapView, {
      props: {
        practices: practices(1), communities: communities(1),
        layers: { practices: true, competition: false, drive5: true, drive10: false },
        valueLayer: undefined, driveCenter: [30.4, -97.6],
        center: [30.31, -97.75], zoom: 10
      }
    });
    await vi.waitUntil(() => wrapper.find('button[aria-label="Zoom in"]').exists(), { timeout: 5000, interval: 1 });
    await flushPromises();

    const overlayGroup = (stub.map.added as { clearLayers?: unknown; added: { center?: unknown }[] }[]).filter((g) => g.clearLayers)[0];
    expect(overlayGroup.added).toHaveLength(1); // one drive5 ring, centred on driveCenter
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
