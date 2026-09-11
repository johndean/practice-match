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
const LIST_URL = '/api/markets';
const TIMEOUT_MS = 8000;

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
  boundaries(marketName: string): Promise<Record<string, BoundaryCollection>>;
}

async function read(fetchFn: typeof fetch, url: string): Promise<unknown> {
  const res = await fetchFn(url, {
    credentials: 'same-origin',
    headers: { Accept: 'application/geo+json, application/json' },
    signal: AbortSignal.timeout(TIMEOUT_MS)
  });
  if (!res.ok) throw new Error(`${url} answered ${res.status}`);
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
  return {
    async boundaries(marketName: string) {
      const rows = await catalogue();
      const metro = rows.find((m) => m.name === marketName);
      if (!metro) throw new Error(`no CBSA for market ${marketName}`);
      const collections = await Promise.all(
        FILL_LAYERS.map((layer) => read(fetchFn, `/api/markets/${encodeURIComponent(metro.cbsa_geoid)}/boundaries?layer=${layer}`))
      );
      const out: Record<string, BoundaryCollection> = {};
      FILL_LAYERS.forEach((layer, i) => {
        const body = collections[i] as BoundaryCollection;
        if (!Array.isArray(body?.features)) throw new Error(`${layer}: the answer carries no features array`);
        out[layer] = body;
      });
      return out;
    }
  };
}
