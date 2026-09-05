// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LeafletMapEngine } from './leaflet';
import { installLeafletStub } from '../testing/leaflet-stub';
import { BASEMAPS, LABEL_TILES } from '../../lib/leaflet.js';

afterEach(() => { vi.useRealTimers(); delete (window as any).L; });

async function mounted(opts: Partial<Parameters<LeafletMapEngine['mount']>[1]> = {}) {
  vi.useFakeTimers();
  const stub = installLeafletStub(); const el = document.createElement('div');
  const engine = new LeafletMapEngine();
  await engine.mount(el, { center: [30.31, -97.75], zoom: 10, basemap: 'map', zoomControl: false, scaleControl: true, groups: ['overlay', 'pins'], ...opts });
  return { stub, el, engine };
}

describe('LeafletMapEngine — MarketMapView shape', () => {
  it('creates the map, tiles, labels, scale control and groups exactly as the handoff did', async () => {
    const { stub, el } = await mounted();
    expect(stub.calls[0]).toEqual({ fn: 'map', args: [el, { center: [30.31, -97.75], zoom: 10, zoomControl: false, attributionControl: true }] });
    expect(stub.tiles[0].url).toBe(BASEMAPS.map.url); expect(stub.tiles[0].options).toEqual({ attribution: BASEMAPS.map.attribution, maxZoom: 18 });
    expect(stub.tiles[1].url).toBe(LABEL_TILES); expect(stub.tiles[1].options).toEqual({ maxZoom: 18, pane: 'shadowPane' });
    expect(stub.map.added).toContain(stub.tiles[1]);                       // labels shown on the gray canvas
    expect(stub.calls.find((c) => c.fn === 'control.scale')?.args).toEqual([{ imperial: true, metric: false, position: 'bottomright' }]);
    expect(stub.calls.filter((c) => c.fn === 'control.zoom')).toHaveLength(0);
    expect(stub.calls.filter((c) => c.fn === 'layerGroup')).toHaveLength(2);   // overlay then pins, created at mount in order
    expect(el.dataset.map).toBe('leaflet');
    vi.advanceTimersByTime(60); expect(stub.map.invalidated).toBe(1);
  });
  it('circle and marker pass the exact options; tooltip uses the design placement; clear empties the group', async () => {
    const { stub, engine } = await mounted();
    engine.circle([30.3, -97.7], 16000, { fillColor: '#339dde', fillOpacity: 0.16 }, 'overlay');
    expect(stub.calls.find((c) => c.fn === 'circle')?.args).toEqual([[30.3, -97.7], { radius: 16000, stroke: false, fillColor: '#339dde', fillOpacity: 0.16, interactive: false }]);
    const onClick = () => {};
    engine.marker([30.5, -97.8], { html: '<div>x</div>', size: [72, 26], anchor: [36, 13], zIndexOffset: 1000, onClick }, 'pins');
    expect(stub.calls.find((c) => c.fn === 'divIcon')?.args).toEqual([{ html: '<div>x</div>', className: '', iconSize: [72, 26], iconAnchor: [36, 13] }]);
    const m = stub.calls.find((c) => c.fn === 'marker')!;
    expect(m.args[0]).toEqual([30.5, -97.8]); expect((m.args[1] as any).zIndexOffset).toBe(1000); expect((m.args[1] as any).interactive).toBe(true);
    engine.marker([30.5, -97.8], { html: '<div>d</div>', size: [20, 20], anchor: [10, 10], tooltip: 'Cedar Park — $118K', interactive: true }, 'overlay');
    const marked = stub.calls.filter((c) => c.fn === 'marker'); expect(marked).toHaveLength(2);
    const groups = stub.calls.filter((c) => c.fn === 'layerGroup').length; expect(groups).toBe(2);
    const overlayGroup = (stub.map.added as any[]).find((g) => g.clearLayers && g.added.some((l: any) => l.tooltip));
    expect(overlayGroup.added[1].tooltip).toEqual({ text: 'Cedar Park — $118K', opts: { direction: 'top', offset: [0, -6] } });
    engine.clear('overlay'); expect(overlayGroup.added).toEqual([]);
  });
  it('setBase swaps the tile URL, toggles labels and refreshes attribution; setView animates when asked; show() invalidates after 80 ms', async () => {
    const { stub, engine } = await mounted();
    engine.setBase('satellite');
    expect(stub.tiles[0].url).toBe(BASEMAPS.satellite.url); expect(stub.map.added).not.toContain(stub.tiles[1]); expect((stub.map as any).attrUpdated).toBe(1);
    engine.setBase('map'); expect(stub.map.added).toContain(stub.tiles[1]);
    engine.setView([30.5, -97.8], 12, true); expect((stub.map as any).lastSetView).toEqual([[30.5, -97.8], 12, { animate: true }]);
    engine.setView([30.5, -97.8], 13); expect((stub.map as any).lastSetView).toEqual([[30.5, -97.8], 13, undefined]);
    engine.show(); vi.advanceTimersByTime(80); expect(stub.map.invalidated).toBe(2);
    let seen = 0; const off = engine.onMove((_c, z) => { seen = z; }); stub.map.zoom = 11; stub.map.handlers.zoomend(); expect(seen).toBe(11); off(); expect(stub.map.handlers.zoomend).toBeUndefined();
    engine.destroy(); expect((stub.map as any).removed).toBe(true);
  });
});

describe('LeafletMapEngine — ListingsMap shape', () => {
  it('adds the bottom-right zoom control and no scale control', async () => {
    const { stub } = await mounted({ zoomControl: 'bottomright', scaleControl: false, groups: ['layer'] });
    expect(stub.calls.find((c) => c.fn === 'control.zoom')?.args).toEqual([{ position: 'bottomright' }]);
    expect(stub.calls.filter((c) => c.fn === 'control.scale')).toHaveLength(0);
  });
});
