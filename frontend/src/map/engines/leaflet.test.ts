// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LeafletMapEngine } from './leaflet';
import { installLeafletStub } from '../testing/leaflet-stub';
import { BASEMAPS, LABEL_TILES } from '../../lib/leaflet.js';

// Only `loadLeaflet` is replaced; BASEMAPS/LABEL_TILES come from the real module, because
// this file asserts on their actual values. The replacement behaves exactly like the real
// loader when `window.L` is already set (which installLeafletStub() does) — except that a
// test can hold it open on `loader.gate`, which is the only way to reproduce a destroy()
// that lands while mount() is still awaiting the library. `src/lib/leaflet.js` is untouched.
const loader = vi.hoisted(() => ({ gate: null as Promise<void> | null }));
vi.mock('../../lib/leaflet.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/leaflet.js')>();
  return { ...actual, loadLeaflet: async () => { if (loader.gate) await loader.gate; return (window as any).L; } };
});

afterEach(() => { vi.useRealTimers(); delete (window as any).L; loader.gate = null; });

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

describe('LeafletMapEngine — teardown', () => {
  // John's ruling F: mount()'s 60 ms and show()'s 80 ms invalidateSize timers outlive a
  // destroy() that happens before they fire, and Leaflet then throws
  // "Cannot read properties of undefined (reading '_leaflet_pos')" on the removed map —
  // the `navigation writes the URL` smoke failure. The timers must be tracked and cleared.
  it('clears the mount and show invalidateSize timers on destroy', async () => {
    const { stub, engine } = await mounted();
    engine.show();
    engine.destroy();
    vi.advanceTimersByTime(200);
    expect((stub.map as any).removed).toBe(true);
    expect(stub.map.invalidated).toBe(0);
  });

  // Not firing is only half of it: the set that holds them must also be DRAINED, or a
  // long-lived engine would accumulate dead handles and re-clear ids the platform may
  // already have recycled.
  //
  // Re-review minor (ii): this used to prove that by calling destroy() twice and expecting
  // the second call to clear nothing — which became tautological the moment destroy() grew
  // its early-return guard (the second call returns before it can clear anything, drained
  // set or not). Measured through a fresh lifecycle instead: if the set were not drained it
  // would still hold the first lifecycle's two handles, and the second destroy() would clear
  // three timers rather than the one the second mount() actually scheduled.
  it('drains the pending-timer set on destroy, so a later lifecycle clears only its own timers', async () => {
    const { engine } = await mounted();
    engine.show();
    const cleared = vi.spyOn(globalThis, 'clearTimeout');

    engine.destroy();
    expect(cleared).toHaveBeenCalledTimes(2); // mount()'s 60 ms and show()'s 80 ms

    cleared.mockClear();
    installLeafletStub();
    await engine.mount(document.createElement('div'), { center: [30.31, -97.75], zoom: 10, basemap: 'map', zoomControl: false, scaleControl: true });
    engine.destroy();
    expect(cleared, 'the first lifecycle\'s handles were still in the set').toHaveBeenCalledTimes(1);
    cleared.mockRestore();
  });

  // ---------------------------------------------------------------------------------------
  // Zero-gap audit, Phase 8. `clearTimeout called twice` is a proxy for the properties that
  // actually matter; the five below assert those directly — no leak, no callback after
  // teardown, idempotent teardown, inert afterwards, and revivable by a fresh mount().
  // ---------------------------------------------------------------------------------------
  it('leaks no timer: after destroy the loop holds none of the engine\'s, however many were queued', async () => {
    const { engine } = await mounted();
    for (let i = 0; i < 5; i++) engine.show();          // five 80 ms invalidateSize timers
    expect(vi.getTimerCount()).toBe(6);                  // + mount()'s 60 ms

    engine.destroy();
    // The real property: nothing of this engine's is left in the event loop at all — not
    // merely absent from a private Set, and not merely un-fired for the 200 ms the previous
    // test happened to advance.
    expect(vi.getTimerCount()).toBe(0);
  });

  it('lets no callback run after destroy, however far time advances', async () => {
    const { stub, engine } = await mounted();
    engine.show();
    engine.destroy();

    vi.advanceTimersByTime(60_000);
    await vi.runAllTimersAsync();
    expect(stub.map.invalidated).toBe(0);
  });

  it('is idempotent: a second destroy tears nothing down a second time', async () => {
    const { stub, engine } = await mounted();
    engine.destroy();
    expect((stub.map as any).removed).toBe(true);

    // Observe whether the second call re-runs teardown rather than trusting that the
    // underlying library tolerates it. Leaflet's own Map.remove() reaches into
    // `this._container._leaflet_id`, `this._panes` and `this._layers`, all of which the
    // first call already tore down — "it happens not to throw today" is not the guarantee
    // the audit asks for.
    (stub.map as any).removed = false;
    expect(() => engine.destroy()).not.toThrow();
    expect((stub.map as any).removed, 'destroy() ran the map teardown a second time').toBe(false);
  });

  it('stays inert after destroy: a later show() schedules nothing on the removed map', async () => {
    const { stub, engine } = await mounted();
    engine.destroy();

    engine.show();
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(60_000);
    expect(stub.map.invalidated).toBe(0);
  });

  // Re-review minor (i): "inert" must hold for the WHOLE public surface, not only the
  // timers. Every one of these reached `this.map` after it had been removed — on real
  // Leaflet that is the `_leaflet_pos` / `_container is null` family of crashes, and the
  // only reason the app has not hit them is that both map components null their `engine`
  // reference on unmount. The engine must not depend on its callers doing that.
  it('turns every public method into a no-op after destroy: nothing throws, nothing reaches the map', async () => {
    const { stub, engine } = await mounted();
    const before = {
      calls: stub.calls.length,
      zoom: stub.map.zoom,
      center: stub.map.center,
      invalidated: stub.map.invalidated,
      lastSetView: (stub.map as any).lastSetView,
      fitted: (stub.map as any).fitted,
      attrUpdated: (stub.map as any).attrUpdated,
      handlers: Object.keys(stub.map.handlers).length,
      tileUrl: stub.tiles[0].url,
      added: (stub.map.added as unknown[]).length,
      groupLayers: (stub.map.added as any[]).filter((g) => g.clearLayers).map((g) => g.added.length)
    };

    engine.destroy();

    expect(() => {
      engine.show();
      engine.setControls({ zoomControl: 'bottomright', scaleControl: false });
      engine.setView([1, 2], 5, true);
      engine.zoomIn();
      engine.zoomOut();
      engine.fitBounds([[1, 2], [3, 4]]);
      engine.setBase('satellite');
      engine.clear('overlay');
      engine.circle([1, 2], 100, { fillColor: '#000', fillOpacity: 1 }, 'overlay');
      engine.marker([1, 2], { html: '<i></i>', size: [1, 1], anchor: [0, 0] }, 'pins');
      engine.onMove(() => {});
      engine.getZoom();
    }).not.toThrow();

    vi.advanceTimersByTime(60_000);
    expect({
      calls: stub.calls.length,
      zoom: stub.map.zoom,
      center: stub.map.center,
      invalidated: stub.map.invalidated,
      lastSetView: (stub.map as any).lastSetView,
      fitted: (stub.map as any).fitted,
      attrUpdated: (stub.map as any).attrUpdated,
      handlers: Object.keys(stub.map.handlers).length,
      tileUrl: stub.tiles[0].url,
      added: (stub.map.added as unknown[]).length,
      groupLayers: (stub.map.added as any[]).filter((g) => g.clearLayers).map((g) => g.added.length)
    }).toEqual(before);
  });

  it('returns usable no-op values from the handle-returning methods after destroy', async () => {
    const { engine } = await mounted();
    engine.destroy();

    // Callers hold on to these; they must be safe to use, not undefined.
    expect(() => engine.circle([1, 2], 100, { fillColor: '#000', fillOpacity: 1 }, 'overlay').remove()).not.toThrow();
    expect(() => engine.marker([1, 2], { html: '<i></i>', size: [1, 1], anchor: [0, 0] }, 'pins').remove()).not.toThrow();
    expect(() => engine.onMove(() => {})()).not.toThrow();
  });

  // Re-review item 7 — the mount/destroy race. mount() clears `destroyed` BEFORE awaiting
  // the library, so a destroy() that lands during that await used to be forgotten: the map
  // was then created, its 60 ms invalidateSize scheduled, and nothing held a reference to
  // tear any of it down. (A destroy() before any mount at all threw outright, because
  // `this.map` was undefined.)
  it('honours a destroy() that lands while mount() is still awaiting the library', async () => {
    vi.useFakeTimers();
    let release!: () => void;
    loader.gate = new Promise<void>((r) => { release = r; });
    const stub = installLeafletStub();
    const engine = new LeafletMapEngine();

    const mounting = engine.mount(document.createElement('div'), { center: [30.31, -97.75], zoom: 10, basemap: 'map', zoomControl: false, scaleControl: true, groups: ['overlay', 'pins'] });
    expect(() => engine.destroy()).not.toThrow();   // no map exists yet
    release();
    await expect(mounting).resolves.toBeUndefined();

    expect(stub.calls.filter((c) => c.fn === 'map'), 'a map was created after destroy()').toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(60_000);
  });

  // Round 4, item 2: every other guard is asserted directly, but getZoom()'s was only ever
  // exercised inside the not.toThrow() block above — which would still pass if it returned a
  // stale zoom read off the removed map. Pin the value and the no-touch property.
  it('getZoom() after destroy returns 0 and reads nothing off the map', async () => {
    const { stub, engine } = await mounted();
    engine.setView([30.5, -97.8], 13);
    expect(engine.getZoom()).toBe(13);          // live: the real value

    stub.map.zoom = 99;                          // a value only a map read could return
    engine.destroy();

    expect(engine.getZoom()).toBe(0);
    expect(stub.map.zoom, 'getZoom() reached the removed map').toBe(99);
  });

  // Round 4, item 1: destroy() drained the timers but left `groups`, `zoomCtl` and
  // `scaleCtl` populated with objects bound to the REMOVED map. A re-mounted instance then
  // found the stale entries — `group()` returns the cached group without addTo()-ing the new
  // map, and setControls() sees a truthy control and adds none — so every marker, circle and
  // clear() went to layer groups attached to a map that no longer exists, silently drawing
  // nothing. mount() is the engine's single (re)initialisation point, so teardown has to
  // leave nothing behind for it to trip over.
  describe('re-mounting the same instance after destroy', () => {
    const mountOn = (engine: LeafletMapEngine, el = document.createElement('div')) =>
      engine.mount(el, { center: [30.31, -97.75], zoom: 10, basemap: 'map', zoomControl: 'bottomright', scaleControl: true, groups: ['overlay', 'pins'] });
    const groupsOf = (stub: ReturnType<typeof installLeafletStub>) =>
      (stub.map.added as { clearLayers?: unknown; added: unknown[] }[]).filter((g) => typeof g.clearLayers === 'function');

    it('rebuilds the layer groups on the NEW map, so markers and clear() reach it', async () => {
      vi.useFakeTimers();
      const first = installLeafletStub();
      const engine = new LeafletMapEngine();
      await mountOn(engine);
      engine.marker([30.5, -97.8], { html: '<i></i>', size: [1, 1], anchor: [0, 0] }, 'pins');
      expect(groupsOf(first)[1].added).toHaveLength(1);
      engine.destroy();

      const second = installLeafletStub();
      await mountOn(engine);
      expect(groupsOf(second), 'the new map got no layer groups of its own').toHaveLength(2);

      const firstPinsBefore = groupsOf(first)[1].added.length;
      engine.marker([30.6, -97.9], { html: '<i></i>', size: [1, 1], anchor: [0, 0] }, 'pins');

      expect(groupsOf(second)[1].added, 'the marker did not reach the new map\'s group').toHaveLength(1);
      expect(groupsOf(first)[1].added, 'the marker went to the removed map\'s group').toHaveLength(firstPinsBefore);
      // …and clear() drives the new group, not the stale one.
      engine.clear('pins');
      expect(groupsOf(second)[1].added).toEqual([]);
    });

    it('rebuilds the zoom and scale controls on the NEW map', async () => {
      vi.useFakeTimers();
      installLeafletStub();
      const engine = new LeafletMapEngine();
      await mountOn(engine);
      engine.destroy();

      const second = installLeafletStub();
      await mountOn(engine);
      expect(second.calls.filter((c) => c.fn === 'control.zoom'), 'the new map got no zoom control').toHaveLength(1);
      expect(second.calls.filter((c) => c.fn === 'control.scale'), 'the new map got no scale control').toHaveLength(1);
    });
  });

  // …and "inert" must not mean "permanently dead": mount() is the single point that
  // (re)initialises the engine, so a fresh mount on the same instance works normally again.
  // Without this the destroyed-guard would silently swallow the new map's invalidateSize.
  it('comes back to life on a fresh mount(): the guard is reset, not permanent', async () => {
    const { engine } = await mounted();
    engine.destroy();

    const stub2 = installLeafletStub();
    await engine.mount(document.createElement('div'), { center: [30.31, -97.75], zoom: 10, basemap: 'map', zoomControl: false, scaleControl: true });
    vi.advanceTimersByTime(60);
    expect(stub2.map.invalidated).toBe(1);
    engine.show();
    vi.advanceTimersByTime(80);
    expect(stub2.map.invalidated).toBe(2);
  });
});

describe('LeafletMapEngine — ListingsMap shape', () => {
  it('adds the bottom-right zoom control and no scale control', async () => {
    const { stub } = await mounted({ zoomControl: 'bottomright', scaleControl: false, groups: ['layer'] });
    expect(stub.calls.find((c) => c.fn === 'control.zoom')?.args).toEqual([{ position: 'bottomright' }]);
    expect(stub.calls.filter((c) => c.fn === 'control.scale')).toHaveLength(0);
  });
});
