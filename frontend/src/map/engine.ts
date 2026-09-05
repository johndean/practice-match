export type LatLng = [number, number];
export type BaseKind = 'map' | 'satellite';
export interface MountOptions { center: LatLng; zoom: number; basemap: BaseKind; zoomControl?: 'bottomright' | false; scaleControl?: boolean; groups?: string[] }
export interface CircleStyle { fillColor: string; fillOpacity: number; stroke?: boolean; interactive?: boolean }
export interface MarkerOptions { html: string; size: [number, number]; anchor: [number, number]; tooltip?: string; zIndexOffset?: number; interactive?: boolean; onClick?: () => void }
export interface Handle { remove(): void }

/** The only map API the components use — exactly the surface the handoff's two Leaflet components call. */
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
  marker(pos: LatLng, opts: MarkerOptions, group: string): Handle;
  clear(group: string): void;
  onMove(cb: (center: LatLng, zoom: number) => void): () => void;
  destroy(): void;
}
