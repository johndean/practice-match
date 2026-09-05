import type { BaseKind, CircleStyle, Handle, LatLng, MapEngine, MarkerOptions, MountOptions } from '../engine';
import { BASEMAPS, LABEL_TILES, loadLeaflet } from '../../lib/leaflet.js';

/** Leaflet 1.9.4 behind MapEngine. Every option below is the handoff's, unchanged — Task 4's visual gate proves it. */
export class LeafletMapEngine implements MapEngine {
  readonly name = 'leaflet' as const;
  private L!: any; private map!: any; private tile!: any; private labels!: any;
  private zoomCtl: any = null; private scaleCtl: any = null;
  private readonly groups = new Map<string, any>();

  async mount(el: HTMLElement, opts: MountOptions): Promise<void> {
    const L = await loadLeaflet(); this.L = L;
    this.map = L.map(el, { center: opts.center, zoom: opts.zoom, zoomControl: false, attributionControl: true });
    const cfg = BASEMAPS[opts.basemap] || BASEMAPS.map;
    this.tile = L.tileLayer(cfg.url, { attribution: cfg.attribution, maxZoom: 18 }).addTo(this.map);
    // The gray canvas carries almost no labels — Esri's matching reference layer supplies them.
    this.labels = L.tileLayer(LABEL_TILES, { maxZoom: 18, pane: 'shadowPane' });
    if (opts.basemap === 'map') this.labels.addTo(this.map);
    for (const g of opts.groups ?? []) this.group(g);
    this.setControls(opts);
    el.dataset.map = 'leaflet';
    setTimeout(() => this.map.invalidateSize(), 60);
  }
  show(): void { setTimeout(() => this.map.invalidateSize(), 80); }
  setControls(opts: Pick<MountOptions, 'zoomControl' | 'scaleControl'>): void {
    if (opts.zoomControl && !this.zoomCtl) this.zoomCtl = this.L.control.zoom({ position: opts.zoomControl }).addTo(this.map);
    if (!opts.zoomControl && this.zoomCtl) { this.zoomCtl.remove(); this.zoomCtl = null; }
    if (opts.scaleControl && !this.scaleCtl) this.scaleCtl = this.L.control.scale({ imperial: true, metric: false, position: 'bottomright' }).addTo(this.map);
    if (!opts.scaleControl && this.scaleCtl) { this.scaleCtl.remove(); this.scaleCtl = null; }
  }
  setView(center: LatLng, zoom: number, animate?: boolean): void { this.map.setView(center, zoom, animate === undefined ? undefined : { animate }); }
  getZoom(): number { return this.map.getZoom(); }
  zoomIn(): void { this.map.zoomIn(); }
  zoomOut(): void { this.map.zoomOut(); }
  fitBounds(points: LatLng[]): void { this.map.fitBounds(this.L.latLngBounds(points), { padding: [24, 24] }); }
  setBase(kind: BaseKind): void {
    const cfg = BASEMAPS[kind] || BASEMAPS.map;
    this.tile.setUrl(cfg.url);
    if (kind === 'map') this.labels.addTo(this.map); else this.map.removeLayer(this.labels);
    this.tile.options.attribution = cfg.attribution;
    if (this.map.attributionControl._update) this.map.attributionControl._update();
  }
  circle(center: LatLng, radiusM: number, s: CircleStyle, group: string): Handle {
    const c = this.L.circle(center, { radius: radiusM, stroke: s.stroke ?? false, fillColor: s.fillColor, fillOpacity: s.fillOpacity, interactive: s.interactive ?? false }).addTo(this.group(group));
    return { remove: () => c.remove() };
  }
  marker(pos: LatLng, o: MarkerOptions, group: string): Handle {
    const icon = this.L.divIcon({ html: o.html, className: '', iconSize: o.size, iconAnchor: o.anchor });
    const m = this.L.marker(pos, { icon, zIndexOffset: o.zIndexOffset ?? 0, interactive: o.interactive ?? true });
    if (o.tooltip) m.bindTooltip(o.tooltip, { direction: 'top', offset: [0, -6] });
    if (o.onClick) m.on('click', o.onClick);
    m.addTo(this.group(group));
    return { remove: () => m.remove() };
  }
  clear(group: string): void { this.groups.get(group)?.clearLayers(); }
  onMove(cb: (center: LatLng, zoom: number) => void): () => void {
    const h = () => { const c = this.map.getCenter(); cb([c.lat, c.lng], this.map.getZoom()); };
    this.map.on('moveend zoomend', h);
    return () => this.map.off('moveend zoomend', h);
  }
  destroy(): void { this.map.remove(); }
  private group(name: string) { let g = this.groups.get(name); if (!g) { g = this.L.layerGroup().addTo(this.map); this.groups.set(name, g); } return g; }
}
