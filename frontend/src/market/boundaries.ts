/**
 * `GET /api/markets/{cbsa}/boundaries` → the design's `market` adapter prop (spec §8.3).
 *
 * The seam A16 and A17 established: an app-only prop the reference never receives, declared in
 * `app.setup.js` with a `default` that builds the real client. The design's own script branches
 * on adapter PRESENCE, not on data — with this present the map draws what the API answered or
 * NOTHING, whatever it answered (A-SL23 (2)); with no adapter the design's fixture path runs
 * unchanged, which is what keeps the reference and the Claude Design preview on their pixels.
 *
 * The metro is resolved by NAME through `/api/markets` — the first thing in the product to call
 * that route, which has existed and been guarded since Phase B — because `logic.js` speaks in
 * market names ("Austin, TX") and knows no CBSA geoid, and teaching it one would be a change to
 * the design for the adapter's convenience. The catalogue is read once per page.
 *
 * **What a member sees when this fails, and why it is not a blank screen.** A rejection empties
 * the shading and nothing else: `MarketMapView.drawOverlay` paints the C7 drive-time ring BEFORE
 * it reaches the polygon layer, and `drawPins()` is a separate call, so the basemap, the practice
 * pins with their price callouts, the results rail, the filters and the detail panel all still
 * render — the design's own "practices only" map. The one case that must never happen is the
 * design's Austin FIXTURE polygons being drawn over a real metro, which is why a refusal empties
 * rather than falls back. Where the route exists but holds no values yet, the API still answers
 * with real outlines and null values, and those paint in the design's own `No data` grey with the
 * legend row that names it — so an unloaded pipeline degrades inside the design's own vocabulary.
 * **That makes the route's PRESENCE the operational precondition: this adapter must not reach an
 * environment before Task 9's endpoint does.**
 */
import { PAD, bboxOf, current, subscribe } from '../map/viewport';

const LIST_URL = '/api/markets';

/**
 * Sized against the MEASURED payload, not the fixture (Task 9's report): 88 Austin ZCTAs are
 * 53.3 KB raw / 10.5 KB gzipped at the committed fixture's 0.010 degree simplification, and a real
 * cb_500k TIGER load extrapolates to roughly 190-400 KB raw / 40-90 KB gzipped per layer. The
 * three fill layers are read in one `Promise.all`, so they share the connection and the worst
 * realistic case is about 270 KB gzipped arriving together - four seconds on a 500 kbit/s link
 * before the server has done anything. An 8-second deadline would abort that and leave a member on
 * an unshaded map, which is the exact outcome this whole task exists to avoid; 20 still bounds the
 * request, so nothing hangs for ever.
 */
const TIMEOUT_MS = 20000;

export const FILL_LAYERS = ['income', 'growth', 'econ'] as const;

export interface BoundaryProperties {
  geo_id: string; name: string;
  value: number | null; moe: number | null;
  suppressed: boolean; suppress_reason: string | null; band_ambiguous: boolean;
}
export interface BoundaryFeature { type: 'Feature'; id: string; properties: BoundaryProperties; geometry: unknown }
export interface BoundaryCollection { type: 'FeatureCollection'; state: string; features: BoundaryFeature[] }
interface MetroRow { cbsa_geoid: string; name: string }

/** What `logic.js` sees as `this.props.market`. */
export interface MarketAdapter {
  /** `bbox` is the value `viewport()` last handed out — `logic.js` holds it as the token it
   *  compares an arriving answer against, and never composes one itself. `null` asks for the whole
   *  metro envelope, which is the pre-map boot and what the reference would get if it had an
   *  adapter at all. */
  boundaries(marketName: string, bbox?: string | null): Promise<Record<string, BoundaryCollection>>;
  /** The ground the map is looking at, as the route's `bbox`, or `null` before a map exists. */
  viewport(): string | null;
  /** Fires once per SETTLED view (`src/map/viewport.ts`'s debounce); returns its unsubscribe. */
  onViewport(cb: () => void): () => void;
}

/** A refusal, carrying the route's own decision-A5 code so a caller can tell a cap that a smaller
 *  box would fix (`AREA_TOO_LARGE`) from one it would not (`BBOX_TOO_LARGE`, `BAD_LAYER`, a 401). */
class Refused extends Error {
  constructor(readonly status: number, readonly code: string | null, message: string) { super(message); }
}

async function read(fetchFn: typeof fetch, url: string): Promise<unknown> {
  const res = await fetchFn(url, {
    credentials: 'same-origin',
    headers: { Accept: 'application/geo+json, application/json' },
    signal: AbortSignal.timeout(TIMEOUT_MS)
  });
  if (!res.ok) {
    // The body is read for its CODE only, and never trusted to exist: a proxy's 502 and an
    // AbortSignal's own failure both arrive here with no envelope at all.
    let code: string | null = null;
    try {
      const body = await res.json() as { error?: { code?: unknown } };
      if (typeof body?.error?.code === 'string') code = body.error.code;
    } catch { /* not this route's envelope; the status is all there is to say */ }
    throw new Refused(res.status, code, `${url} answered ${res.status}${code === null ? '' : ` ${code}`}`);
  }
  return res.json();
}

export function makeMarketAdapter(fetchFn: typeof fetch = globalThis.fetch.bind(globalThis)): MarketAdapter {
  // Memoised on the RESOLVED value, never on the promise: a refused catalogue (the 401 an
  // anonymous visitor gets at the gate, or a restart) would otherwise be cached as a rejection
  // for the life of the page and every later metro change would fail without asking again.
  let metros: MetroRow[] | null = null;
  async function catalogue(): Promise<MetroRow[]> {
    if (metros !== null) return metros;
    const body = await read(fetchFn, LIST_URL);
    if (!Array.isArray(body)) throw new Error('the market catalogue answered no array');
    metros = body as MetroRow[];
    return metros;
  }
  const collect = async (geoid: string, bbox: string | null) => {
    const at = bbox === null ? '' : `&bbox=${encodeURIComponent(bbox)}`;
    const collections = await Promise.all(
      FILL_LAYERS.map((layer) => read(fetchFn, `/api/markets/${encodeURIComponent(geoid)}/boundaries?layer=${layer}${at}`))
    );
    const out: Record<string, BoundaryCollection> = {};
    FILL_LAYERS.forEach((layer, i) => {
      const body = collections[i] as BoundaryCollection;
      if (!Array.isArray(body?.features)) throw new Error(`${layer}: the answer carries no features array`);
      out[layer] = body;
    });
    return out;
  };
  return {
    viewport() {
      const v = current();
      return v === null ? null : bboxOf(v, PAD);
    },
    onViewport: subscribe,
    async boundaries(marketName: string, bbox: string | null = null) {
      // Read BEFORE the catalogue is awaited: `bbox` is the box `logic.js` took from `viewport()`
      // one statement ago, and the first call of the page has a `/api/markets` round trip in front
      // of it. Read after that, the retry's bare box could describe a different view from the
      // padded box that was sent.
      const v = current();
      const rows = await catalogue();
      const metro = rows.find((m) => m.name === marketName);
      if (!metro) throw new Error(`no CBSA for market ${marketName}`);
      try {
        return await collect(metro.cbsa_geoid, bbox);
      } catch (e) {
        // ONE retry, and only where the route's own refusal names a box the client can change.
        // The ladder is the route's instruction, not an invention of ours:
        //
        //   AREA_TOO_LARGE  — "Zoom in or pass a smaller bbox". The padding is 0.3 of the viewport
        //     on every side and dropping it is exactly what there is to give back: in New York at
        //     zoom 10 that is the difference between 4,811 tracts (refused) and 3,706 (served).
        //   BBOX_TOO_LARGE  — the box is wider than `MAX_BBOX_DEG`, which means the member is
        //     looking at more than one metro. The honest next question is the metro itself, which
        //     is the request this adapter made before it learned to send a box at all, and is what
        //     keeps a zoomed-out small metro shaded instead of losing its colour. The cap itself is
        //     never restated here — the SERVER says which one it hit.
        //
        // Anything else (a bad layer, a 401, a 404, a body that is not a FeatureCollection) is not
        // made true by asking a second time, and leaves the map in the unshaded state Task 10
        // photographs.
        if (!(e instanceof Refused)) throw e;
        const again = e.code === 'BBOX_TOO_LARGE' ? null : (v === null ? null : bboxOf(v, 0));
        if (bbox === null || (e.code !== 'AREA_TOO_LARGE' && e.code !== 'BBOX_TOO_LARGE') || again === bbox) throw e;
        if (e.code === 'AREA_TOO_LARGE' && again === null) throw e;
        return await collect(metro.cbsa_geoid, again);
      }
    }
  };
}
