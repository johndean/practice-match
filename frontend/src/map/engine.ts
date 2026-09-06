export type LatLng = [number, number];
export type BaseKind = 'map' | 'satellite';
export interface MountOptions { center: LatLng; zoom: number; basemap: BaseKind; zoomControl?: 'bottomright' | false; scaleControl?: boolean; groups?: string[] }
export interface CircleStyle { fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }
/** V3's community mosaic cell (C5): a filled, strokeless rectangle on the shared canvas renderer. */
export interface AreaStyle { fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }
/** V3 needs two tooltip shapes the hard-coded one could not express: the sticky `rf-tip` on a
 *  mosaic cell, and the persistent `rf-callout` above a selected practice pin (C5, C6). */
export interface TooltipSpec { html: string; sticky?: boolean; permanent?: boolean; direction?: 'top' | 'bottom'; offset?: [number, number]; className?: string; opacity?: number }
/** V3's drive-time ring (C7): an unfilled, dashed, stroked circle. Deliberately NOT CircleStyle,
 *  which describes a filled, strokeless disc — the two option sets are mutually exclusive. */
export interface RingStyle { color: string; weight: number; dashArray?: string; fill: false; interactive?: boolean }
/** `keyboard` and `title` are part of the design's DOM, not decoration: Leaflet renders the
 *  first as the icon's tabindex and the second as its title attribute (MarketMapV3.jsx:288-289). */
export interface MarkerOptions { html: string; size: [number, number]; anchor: [number, number]; tooltip?: string | TooltipSpec; zIndexOffset?: number; interactive?: boolean; keyboard?: boolean; title?: string; onClick?: () => void }
export interface Handle { remove(): void; openTooltip?(): void }

/** The only map API the components use — exactly the surface the handoff's map components call. */
export interface MapEngine {
  readonly name: 'leaflet' | 'google';
  mount(el: HTMLElement, opts: MountOptions): Promise<void>;
  show(): void;
  setControls(opts: Pick<MountOptions, 'zoomControl' | 'scaleControl'>): void;
  setView(center: LatLng, zoom: number, animate?: boolean): void;
  getZoom(): number;
  zoomIn(): void;
  zoomOut(): void;
  fitBounds(points: LatLng[]): void;
  setBase(kind: BaseKind): void;
  circle(center: LatLng, radiusM: number, style: CircleStyle, group: string): Handle;
  rectangle(bounds: [LatLng, LatLng], style: AreaStyle, group: string, tooltip?: TooltipSpec, onClick?: () => void): Handle;
  ring(center: LatLng, radiusM: number, style: RingStyle, group: string): Handle;
  marker(pos: LatLng, opts: MarkerOptions, group: string): Handle;
  panInside(pos: LatLng, padding: [number, number]): void;
  clear(group: string): void;
  onMove(cb: (center: LatLng, zoom: number) => void): () => void;
  destroy(): void;
}
