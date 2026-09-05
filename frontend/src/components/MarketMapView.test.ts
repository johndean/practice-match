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
// The engine is not mocked: the component obtains it through `createEngine()` exactly as it
// does in the app, and `loadLeaflet()` hands back whatever `window.L` already holds — so
// installing the Leaflet stub first puts a recording fake under the real LeafletMapEngine.
import { afterEach, describe, expect, it } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
// Eagerly pull in the module `createEngine()` would import lazily. Leaflet's UMD bundle
// assigns `window.L = L` when it is evaluated, so letting that happen during the component's
// own `await createEngine()` would overwrite the stub installed below and the real library
// would answer instead. Importing it first, then installing the stub, keeps the fake on top.
import '../map/engines/leaflet';
import { installLeafletStub, type LeafletStub } from '../map/testing/leaflet-stub';
import MarketMapView from './MarketMapView.vue';

afterEach(() => { delete (window as { L?: unknown }).L; });

const COMMUNITIES = [
  { name: 'Cedar Park', lat: 30.51, lng: -97.82, vets: 4, values: { income: { t: 0.5, label: '$118K', color: '#4c9a6a' } } },
  { name: 'Round Rock', lat: 30.51, lng: -97.68, vets: 6, values: { income: { t: 0.8, label: '$131K', color: '#2f7d55' } } }
];
const practices = (priceLabel: string) => [{ id: 'p1', lat: 30.31, lng: -97.75, priceLabel }];

// The two draws are told apart by the divIcon HTML they build: markers.js `dot()` opens
// with the bubble's width/height, `pricePin()` with the pill's font-family.
function drawOrder(stub: LeafletStub, from: number): string[] {
  return stub.calls
    .slice(from)
    .filter((c) => c.fn === 'divIcon')
    .map((c) => (/^<div style="width:/.test((c.args[0] as { html: string }).html) ? 'overlay' : 'pins'));
}

async function mounted() {
  const stub = installLeafletStub();
  const wrapper = mount(MarketMapView, {
    props: {
      practices: practices('$1.45M'),
      communities: COMMUNITIES,
      layers: { practices: true, competition: false, drive5: false, drive10: false },
      valueLayer: 'income',
      center: [30.31, -97.75],
      zoom: 10
    }
  });
  await flushPromises();
  return { stub, wrapper };
}

describe('MarketMapView — redraw order', () => {
  it('redraws the overlay before the pins when only `practices` changes', async () => {
    const { stub, wrapper } = await mounted();
    expect(drawOrder(stub, 0).length).toBeGreaterThan(0); // the map really mounted and drew

    const from = stub.calls.length;
    await wrapper.setProps({ practices: practices('$1.50M') });

    // Both groups rebuild, overlay first — MarketMap.jsx's effect 5 then effect 6. That the
    // overlay redraws at all on a pins-only change is the deliberate superset documented on
    // the watcher: one callback is the only way to promise the relative order.
    expect(drawOrder(stub, from)).toEqual(['overlay', 'overlay', 'pins']);
  });
});
