/**
 * The map's CURRENT viewport, as the one box the boundary adapter asks the API for.
 *
 * `GET /api/markets/{cbsa}/boundaries` has accepted a `bbox` since Task 9 and the adapter never
 * sent one, so it always asked for the whole metro envelope — which at Census-tract scale is
 * 5,935 tracts in New York against the route's own `MAX_FEATURES = 4000`, a count no delivery
 * tolerance can coarsen away and therefore a permanently blank map in the largest market in the
 * country. This module is the channel that closes that: `MarketMapView` publishes what the map
 * is looking at, `src/market/boundaries.ts` reads it and asks for exactly that ground.
 *
 * A module-level singleton, deliberately: there is one Browse map, `MarketMapView` mounts it and
 * `logic.js` — a verbatim port that knows nothing about Leaflet — asks for the shading. Threading
 * the bounds through the design's own props would mean amending the template `App.vue` is
 * generated from, for a value no template renders. `reset()` exists for the tests, which is the
 * only honest way to have a singleton.
 */
export interface Viewport { w: number; s: number; e: number; n: number; zoom: number }

/**
 * The fraction of the viewport, on every side, the box is grown by before it is snapped.
 *
 * MEASURED from the renderer this app already ships, not chosen: `LeafletMapEngine.mount` builds
 * its shared canvas renderer with `padding: 0.3`, and Leaflet's `Renderer._update` sizes that
 * canvas to the map view plus `padding` of it in each direction (leaflet-src.js:12470,
 * `_updateTransform` at :12520).
 * Beyond 0.3 of the viewport the renderer paints NOTHING during a drag, whatever we fetched, so a
 * larger padding buys no pixel; and `Renderer.getEvents` maps `moveend: this._update`, so the
 * moment a larger box would start to matter is the moment the refetch is already in flight. 0.3
 * is therefore both the largest padding that can show and the smallest that covers a drag.
 *
 * It is not free. Measured on real TIGER tracts (31,252 rows, 10 states): a 1440 x 940 Browse map
 * centred on the New York CBSA centroid at zoom 10 sees 3,706 tracts unpadded and 4,811 at this
 * padding, and `MAX_FEATURES` is 4,000 — which is why `boundaries()` retries once, unpadded, on
 * the route's own `AREA_TOO_LARGE`. Doing what the refusal asks for ("Zoom in or pass a smaller
 * bbox") is the route's contract, not a workaround.
 */
export const PAD = 0.3;

/**
 * How long after the last move the box is considered settled.
 *
 * Leaflet's own number: `leaflet-src.js:4827` waits `250` ms for `_onZoomTransitionEnd`, and
 * `leaflet.css:198` gives `.leaflet-zoom-animated` a `transform 0.25s` transition. Until then the
 * map is still moving, so a request issued earlier is a request for a box the user is not on yet.
 */
export const DEBOUNCE_MS = 250;

/**
 * One eighth of a 256 px basemap tile — 32 CSS px — at the zoom the map is drawn at.
 *
 * The box is snapped OUTWARD to this grid so that the same ground always produces the same query
 * string and therefore the same 24-hour cache entry on the route (`boundaries:...:b{bbox}`).
 * Without it, `Leaflet.getBounds()` hands back a float that moves at the 1e-7-degree — centimetre
 * — scale on every `moveend`, and every pan would be its own cache miss.
 *
 * An eighth, and not a quarter or a whole tile, is the measured ceiling rather than a preference:
 * outward snapping adds up to one cell per side, and New York at zoom 10 has room for about 0.07
 * degrees per side before it crosses `MAX_FEATURES` (3,945 tracts at 1.541 x 0.848 degrees, 4,148
 * at 1.681 x 0.925). A quarter tile is 0.088 degrees at zoom 10 and does not fit; an eighth is
 * 0.044 and does. Expressed against the zoom, so it is 32 px at every scale.
 */
export const GRID_TILE_FRACTION = 8;

/** The latitude Web Mercator stops at, and therefore the furthest north or south a Leaflet map
 *  can actually be looking, however far out it is zoomed (leaflet-src.js, `SphericalMercator`). */
const MAX_LAT = 85.051129;

export function grid(zoom: number): number {
  return 360 / 2 ** (Math.round(zoom) + Math.log2(GRID_TILE_FRACTION));
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
/** Six decimals, the precision the route's own `ST_AsGeoJSON(..., 6)` serves — rounded OUTWARD,
 *  so the string is never a hair inside the box the snap just chose. */
const out6 = (v: number, up: boolean) => (up ? Math.ceil(v * 1e6) : Math.floor(v * 1e6)) / 1e6;

/** The query-string bbox for one viewport: `minLng,minLat,maxLng,maxLat`, padded and snapped. */
export function bboxOf(v: Viewport, pad: number): string {
  const g = grid(v.zoom);
  const dx = (v.e - v.w) * pad;
  const dy = (v.n - v.s) * pad;
  const w = clamp(Math.floor((v.w - dx) / g) * g, -180, 180);
  const s = clamp(Math.floor((v.s - dy) / g) * g, -MAX_LAT, MAX_LAT);
  const e = clamp(Math.ceil((v.e + dx) / g) * g, -180, 180);
  const n = clamp(Math.ceil((v.n + dy) / g) * g, -MAX_LAT, MAX_LAT);
  return [out6(w, false), out6(s, false), out6(e, true), out6(n, true)].join(',');
}

let viewport: Viewport | null = null;
let settled: string | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

const key = (v: Viewport | null) => (v === null ? null : bboxOf(v, PAD));

/** What the map is looking at right now, or `null` before one is mounted and after it is gone. */
export function current(): Viewport | null {
  return viewport;
}

/** `MarketMapView` calls this at mount, on every `moveend`/`zoomend`, and with `null` on unmount. */
export function publish(v: Viewport | null): void {
  viewport = v;
  if (timer !== null) { clearTimeout(timer); timer = null; }
  // Nothing to say when the SNAPPED box is where it already was: `invalidateSize()`, a selection
  // that pans the map inside the current cell, and the float jitter of any `moveend` at all all
  // land here, and none of them is a new question for the API.
  if (key(v) === settled) return;
  timer = setTimeout(() => {
    timer = null;
    settled = key(viewport);
    // One listener's failure is not the others' — `logic.js`'s own handler already swallows its
    // rejection, and this loop must not depend on that staying true.
    for (const cb of [...listeners]) { try { cb(); } catch { /* a subscriber's own problem */ } }
  }, DEBOUNCE_MS);
}

export function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

/** Tests only: a module-level singleton with no way back to its initial state is untestable. */
export function reset(): void {
  viewport = null;
  settled = null;
  if (timer !== null) { clearTimeout(timer); timer = null; }
  listeners.clear();
}
