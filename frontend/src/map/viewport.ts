/**
 * The map's CURRENT viewport, as the one box the boundary adapter asks the API for.
 *
 * `GET /api/markets/{cbsa}/boundaries` has accepted a `bbox` since Task 9 and the adapter never
 * sent one, so it always asked for the whole metro envelope. This module is the channel that
 * closes that: `MarketMapView` publishes what the map is looking at, and `src/market/boundaries.ts`
 * asks for exactly that ground.
 *
 * TWO views, and the distinction is load-bearing (fix round 1). `current()` is the LIVE view — it
 * moves with the wheel and is the debounce's input, nothing more. `settled()` is the view that
 * stayed still long enough to be asked about, and it is the ONLY one the adapter answers from:
 * both the box a request carries and the token `logic.js` checks an arriving answer against come
 * from it, so the two can never describe different ground.
 *
 * The numbers below were first measured against `MAX_FEATURES = 4000`, which was sized for the
 * ZCTA era; the caps were re-measured for Census tracts on 2026-09-12 (`app/api/market.py`) and
 * are now 12,000 features and 6,000,000 bytes. So the box is no longer what stands between New
 * York and a blank map — it is what keeps the answer the size of the screen. Measured on the
 * stakeholder's own 1460 x 1228 map: the first New York view is 7,470 tracts and 4.25 MB served
 * (652 KB gzipped), against 9,767 tracts for the widest box the route accepts at all.
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
 * It is not free, and what it costs is BYTES rather than a refusal. Measured on QA's own tract
 * geometry at 1460 x 1228 px: New York's first view is 5,262 tracts bare and 7,470 padded, which
 * is 4.27 MB against 6.54 MB unsimplified — so the padding is what pushes that view off the exact
 * outline and onto the 1/4000 delivery tier (0.78 CSS px of latitude at zoom 10, invisible). The
 * unpadded retry in `boundaries()` stays: it is the route's own instruction on `AREA_TOO_LARGE`
 * ("Zoom in or pass a smaller bbox"), and a geography denser than today's will reach it.
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
 * An eighth, and not a quarter or a whole tile. That used to be a CEILING — a quarter tile did not
 * fit under `MAX_FEATURES = 4000` and an eighth did — and since the caps were re-measured for
 * Census tracts it is not: measured on QA, New York's first view snapped to a quarter tile is
 * 7,651 tracts and 4,329,601 bytes at its delivery tier, comfortably inside both caps. What binds
 * now is the WIRE. Outward snapping adds up to one cell per side to a body that is already the
 * largest this product serves, and a quarter tile buys nothing for it: +181 tracts and +75,570
 * bytes (+1.8 %) for a cache hit on pans up to 64 px instead of 32. An eighth costs at most 3.1 %
 * of the span per side. Expressed against the zoom, so it is 32 px at every scale.
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

let live: Viewport | null = null;
let settledView: Viewport | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

const key = (v: Viewport | null) => (v === null ? null : bboxOf(v, PAD));

/** The LIVE view — what the map is looking at this instant.
 *
 *  TESTS ONLY, the way `reset()` below is: no production reader takes it (`MarketMapView.vue`
 *  publishes, `src/market/boundaries.ts` reads `settled()`), and a future one that reached for it
 *  to decide what to fetch would reintroduce fix round 1's finding exactly — an answer discarded
 *  for a view the member was already back on. It is exported so the debounce's INPUT can be
 *  observed separately from its output. */
export function current(): Viewport | null {
  return live;
}

/**
 * The view the adapter answers for: the last one that stayed still long enough to be asked about.
 *
 * Fix round 1, finding 1 (reproduced by the reviewer). `settled` used to be a KEY, advanced when a
 * request was issued, while the adapter's `viewport()` answered from the LIVE view. One box could
 * then be both "already asked — suppressed here" and "stale — discarded by `logic.js`'s guard":
 * zoom one step away, let the in-flight answer land (discarded against the live box), zoom straight
 * back inside 250 ms (suppressed, because the key is where this module already is) and the member
 * keeps a view nothing is drawn for and nothing will ever re-request. Keeping the settled VIEW and
 * answering from it closes that without touching the guard, which was right all along — it was
 * handed the wrong token.
 */
export function settled(): Viewport | null {
  return settledView;
}

/** `MarketMapView` calls this at mount, on every `moveend`/`zoomend`, and with `null` on unmount. */
export function publish(v: Viewport | null): void {
  live = v;
  if (timer !== null) { clearTimeout(timer); timer = null; }
  // A torn-down map leaves NO box behind, and leaves none AT ONCE: waiting out the debounce would
  // let the adapter answer for a view that no longer exists. The notification still waits, so a
  // remount inside the window costs no request.
  if (v === null) {
    if (settledView === null) return;
    settledView = null;
    timer = setTimeout(() => { timer = null; notify(); }, DEBOUNCE_MS);
    return;
  }
  // Nothing to say when the SNAPPED box is where it already was: `invalidateSize()`, a selection
  // that pans the map inside the current cell, and the float jitter of any `moveend` at all all
  // land here, and none of them is a new question for the API.
  if (key(v) === key(settledView)) return;
  timer = setTimeout(() => {
    timer = null;
    settledView = live;
    notify();
  }, DEBOUNCE_MS);
}

/** One listener's failure is not the others' — `logic.js`'s own handler already swallows its
 *  rejection, and this loop must not depend on that staying true. */
function notify(): void {
  for (const cb of [...listeners]) { try { cb(); } catch { /* a subscriber's own problem */ } }
}

export function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

/** Tests only: a module-level singleton with no way back to its initial state is untestable. */
export function reset(): void {
  live = null;
  settledView = null;
  if (timer !== null) { clearTimeout(timer); timer = null; }
  listeners.clear();
}
