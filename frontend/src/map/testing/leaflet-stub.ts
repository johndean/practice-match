export interface Call { fn: string; args: unknown[] }
export interface LeafletStub { calls: Call[]; map: FakeMap; tiles: FakeTile[]; L: unknown }

class FakeLayer { added: unknown[] = []; on(ev: string, cb: () => void) { (this as any)['on_' + ev] = cb; return this; } addTo(g: any) { g.added?.push(this); (this as any).parent = g; return this; } remove() { const p = (this as any).parent; if (p?.added) p.added = p.added.filter((x: unknown) => x !== this); } bindTooltip(text: string, opts: unknown) { (this as any).tooltip = { text, opts }; return this; } }
export class FakeTile extends FakeLayer { url: string; options: Record<string, unknown>; constructor(url: string, options: Record<string, unknown>) { super(); this.url = url; this.options = options; } setUrl(u: string) { this.url = u; } }
class FakeGroup extends FakeLayer { clearLayers() { this.added = []; } }
export class FakeMap { added: unknown[] = []; handlers: Record<string, () => void> = {}; center: unknown; zoom: number; invalidated = 0; attributionControl = { _update: () => { (this as any).attrUpdated = ((this as any).attrUpdated ?? 0) + 1; } };
  constructor(public el: HTMLElement, public opts: any) { this.center = opts.center; this.zoom = opts.zoom; el.dataset.leafletMounted = '1'; }
  setView(c: unknown, z: number, o?: unknown) { this.center = c; this.zoom = z; (this as any).lastSetView = [c, z, o]; }
  getZoom() { return this.zoom; } getCenter() { const c = this.center as [number, number]; return { lat: c[0], lng: c[1] }; }
  zoomIn() { this.zoom += 1; } zoomOut() { this.zoom -= 1; } invalidateSize() { this.invalidated += 1; }
  on(ev: string, cb: () => void) { ev.split(' ').forEach((e) => { this.handlers[e] = cb; }); } off(ev: string) { ev.split(' ').forEach((e) => { delete this.handlers[e]; }); }
  removeLayer(l: unknown) { this.added = this.added.filter((x) => x !== l); } remove() { (this as any).removed = true; } fitBounds(b: unknown, o?: unknown) { (this as any).fitted = [b, o]; } }

export function installLeafletStub(): LeafletStub {
  const calls: Call[] = []; const tiles: FakeTile[] = []; let map: FakeMap;
  const rec = (fn: string, ret: (...a: any[]) => unknown) => (...args: unknown[]) => { calls.push({ fn, args }); return ret(...args); };
  const L = {
    map: rec('map', (el: HTMLElement, opts: unknown) => (map = new FakeMap(el, opts))),
    tileLayer: rec('tileLayer', (url: string, options: Record<string, unknown>) => { const t = new FakeTile(url, options); tiles.push(t); return t; }),
    layerGroup: rec('layerGroup', () => new FakeGroup()),
    circle: rec('circle', (center: unknown, options: unknown) => Object.assign(new FakeLayer(), { center, options })),
    divIcon: rec('divIcon', (o: unknown) => ({ icon: o })),
    marker: rec('marker', (pos: unknown, options: unknown) => Object.assign(new FakeLayer(), { pos, options })),
    control: { zoom: rec('control.zoom', (o: unknown) => Object.assign(new FakeLayer(), { control: 'zoom', o })), scale: rec('control.scale', (o: unknown) => Object.assign(new FakeLayer(), { control: 'scale', o })) },
    latLngBounds: rec('latLngBounds', (pts: unknown) => ({ pts })),
  };
  (window as any).L = L;
  return { calls, get map() { return map; }, tiles, L };
}
