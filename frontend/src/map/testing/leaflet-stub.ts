export interface Call { fn: string; args: unknown[] }
export interface LeafletStub { calls: Call[]; map: FakeMap; tiles: FakeTile[]; canvas: unknown; L: unknown }

// Every addTo() stamps a monotonically increasing `seq`, so a test can read back the order
// in which layers were attached — which is the order Leaflet's SHARED markerPane sees, and
// therefore what decides which of two z-index-tied markers paints on top. Counting attaches
// lets MarketMapView.test.ts state its invariant semantically ("every overlay layer was
// attached before every pin layer") instead of pinning a fixture-shaped expected array.
let SEQ = 0;

class FakeLayer { added: unknown[] = []; seq = -1; on(ev: string, cb: () => void) { (this as any)['on_' + ev] = cb; return this; } addTo(g: any) { g.added?.push(this); (this as any).parent = g; this.seq = SEQ++; return this; } remove() { const p = (this as any).parent; if (p?.added) p.added = p.added.filter((x: unknown) => x !== this); } bindTooltip(text: string, opts: unknown) { (this as any).tooltip = { text, opts }; return this; } openTooltip() { (this as any).tooltipOpened = ((this as any).tooltipOpened ?? 0) + 1; return this; } }
export class FakeTile extends FakeLayer { url: string; options: Record<string, unknown>; constructor(url: string, options: Record<string, unknown>) { super(); this.url = url; this.options = options; } setUrl(u: string) { this.url = u; } }
class FakeGroup extends FakeLayer { clearLayers() { this.added = []; } }
export class FakeMap { added: unknown[] = []; handlers: Record<string, () => void> = {}; center: unknown; zoom: number; invalidated = 0; attributionControl = { _update: () => { (this as any).attrUpdated = ((this as any).attrUpdated ?? 0) + 1; } };
  constructor(public el: HTMLElement, public opts: any) { this.center = opts.center; this.zoom = opts.zoom; el.dataset.leafletMounted = '1'; }
  // Leaflet's own `setView` ALWAYS settles: `_resetView` (leaflet-src.js:4287) runs
  // `_moveStart -> _move -> _moveEnd`, and `_moveEnd` fires `zoomend` when the zoom changed and
  // `moveend` unconditionally — the animated pan path reaches the same `_moveEnd` when its
  // transition ends. This stub used to move silently, which made A32's recentre flag look like
  // it leaked into the next user pan when in a real browser the `setView`'s own `moveend`
  // always spends it.
  setView(c: unknown, z: number, o?: unknown) { const zoomed = this.zoom !== z; this.center = c; this.zoom = z; (this as any).lastSetView = [c, z, o]; if (zoomed) this.handlers.zoomend?.(); this.handlers.moveend?.(); }
  getZoom() { return this.zoom; } getCenter() { const c = this.center as [number, number]; return { lat: c[0], lng: c[1] }; }
  // The Browse map measured at the design's own 1440 x 940 preview: 1020 x 740 CSS px beside the
  // results rail, which at zoom 10 is 1.401 deg of longitude and, at New York's latitude, 0.771
  // of latitude. Halved per zoom level, the way a tile pyramid is. `boundsReads` is how a test
  // proves a destroyed engine did not reach in here for a stale box.
  boundsReads = 0;
  getBounds() {
    this.boundsReads += 1;
    const c = this.center as [number, number];
    const k = 2 ** (10 - this.zoom);
    const dLng = 0.7005 * k; const dLat = 0.3855 * k;
    return { getSouth: () => c[0] - dLat, getWest: () => c[1] - dLng, getNorth: () => c[0] + dLat, getEast: () => c[1] + dLng };
  }
  zoomIn() { this.zoom += 1; } zoomOut() { this.zoom -= 1; } invalidateSize() { this.invalidated += 1; }
  on(ev: string, cb: () => void) { ev.split(' ').forEach((e) => { this.handlers[e] = cb; }); } off(ev: string) { ev.split(' ').forEach((e) => { delete this.handlers[e]; }); }
  removeLayer(l: unknown) { this.added = this.added.filter((x) => x !== l); } remove() { (this as any).removed = true; } fitBounds(b: unknown, o?: unknown) { (this as any).fitted = [b, o]; } panInside(pos: unknown, o?: unknown) { (this as any).pannedInside = [pos, o]; (this as any).pannedInsideCount = ((this as any).pannedInsideCount ?? 0) + 1; } }

export function installLeafletStub(): LeafletStub {
  SEQ = 0;
  const calls: Call[] = []; const tiles: FakeTile[] = []; let map: FakeMap; let canvas: unknown = null;
  const rec = (fn: string, ret: (...a: any[]) => unknown) => (...args: unknown[]) => { calls.push({ fn, args }); return ret(...args); };
  const L = {
    map: rec('map', (el: HTMLElement, opts: unknown) => (map = new FakeMap(el, opts))),
    tileLayer: rec('tileLayer', (url: string, options: Record<string, unknown>) => { const t = new FakeTile(url, options); tiles.push(t); return t; }),
    layerGroup: rec('layerGroup', () => new FakeGroup()),
    circle: rec('circle', (center: unknown, options: unknown) => Object.assign(new FakeLayer(), { center, options })),
    rectangle: rec('rectangle', (bounds: unknown, options: unknown) => Object.assign(new FakeLayer(), { bounds, options })),
    // L.geoJSON constructs one path per feature and hands each to `onEachFeature`, which is where
    // MarketMapView's tooltip and click handler are bound — so the fake has to construct them too,
    // or a per-feature binding would be untestable.
    geoJSON: rec('geoJSON', (data: { features?: unknown[] }, options: { onEachFeature?: (f: unknown, l: unknown) => void }) => {
      const group = Object.assign(new FakeLayer(), { data, options, features: [] as FakeLayer[] });
      for (const f of data?.features ?? []) {
        const child = new FakeLayer();
        group.features.push(child);
        options?.onEachFeature?.(f, child);
      }
      return group;
    }),
    canvas: rec('canvas', (o: unknown) => (canvas = { renderer: 'canvas', options: o })),
    divIcon: rec('divIcon', (o: unknown) => ({ icon: o })),
    marker: rec('marker', (pos: unknown, options: unknown) => Object.assign(new FakeLayer(), { pos, options })),
    control: { zoom: rec('control.zoom', (o: unknown) => Object.assign(new FakeLayer(), { control: 'zoom', o })), scale: rec('control.scale', (o: unknown) => Object.assign(new FakeLayer(), { control: 'scale', o })) },
    latLngBounds: rec('latLngBounds', (pts: unknown) => ({ pts })),
  };
  (window as any).L = L;
  return { calls, get map() { return map; }, tiles, get canvas() { return canvas; }, L };
}
