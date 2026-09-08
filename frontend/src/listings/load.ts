// The app's one bridge from the API to the approved prototype's fixture arrays (spec
// 2026-09-06 D6). `logic.js` is the design file's script block, ported verbatim and never
// restructured, so this module does not reshape it: it MUTATES the exported `P` and `MARKETS`
// objects in place, and every reader inside `logic.js` — renderVals(), photoSet(),
// marketPanel() — sees the new data through the binding it already had.
//
// The field names below are the contract: they are the design's own, and the CLAUDE.md
// launch-removal note requires them to survive the removal of the fixtures themselves.

export const MARKET_ZOOM = 10;
// A hung request must not leave the app unmounted. `loadListings` is awaited before
// `bootstrap()`, so without a deadline a slow or black-holed /api/listings gives the member a
// BLANK PAGE — not the sign-in gate (pre-flight I5). Five seconds is far above the endpoint's
// 100 ms p95 budget and far below a user's patience.
export const LOAD_TIMEOUT_MS = 5000;
// The geographic centre of the contiguous United States: the only sane place to point a map
// for a market whose every listing has withheld its location.
export const US_CENTER: [number, number] = [39.8283, -98.5795];
// 200 is the endpoint's own MAX_LIMIT (`app/api/listings.py`), and the whole demo catalogue is
// eighteen rows — one page, no cursor to follow.
const LIST_URL = '/api/listings?limit=200';

export interface ApiListing {
  id: string;
  // A-L5.1 (1): the slug is the listing's NAME in another spelling, so the server nulls it with
  // the name. Nothing here reads it — `p.id` is the API's `id` — but the field is part of the
  // contract and its nullability is the reason why.
  slug: string | null;
  name: string | null;
  market: string;
  area: string;
  type: string;
  city: string;
  state: string;
  street: string | null;
  zip: string | null;
  phone: string | null;
  hours: string | null;
  price: number | null;
  rev: number | null;
  docs: number | null;
  rooms: number | null;
  sqft: number | null;
  bldg: string | null;
  est: number | null;
  listed: string;
  listed_at: string;
  status: string;
  pop: string | null;
  growth: string | null;
  income: string | null;
  hh: string | null;
  note: string | null;
  staff: string | null;
  services: string | null;
  facility: string | null;
  ownership: string | null;
  lat: number | null;
  lng: number | null;
  location_disclosed: boolean;
  photos: string[];
}

export interface Practice {
  id: string;
  area: string;
  type: string;
  price: number | null;
  rev: number | null;
  docs: number | null;
  rooms: number | null;
  sqft: number | null;
  bldg: string | null;
  lat: number | null;
  lng: number | null;
  est: number | null;
  listed: string;
  status: string;
  pop: string | null;
  growth: string | null;
  income: string | null;
  hh: string | null;
  note: string | null;
  staff: string | null;
  hours: string | null;
  services: string | null;
  facility: string | null;
  ownership: string | null;
  market: string;
  name?: string;
  photos?: string[];
}

export type Markets = Record<string, { center: [number, number]; zoom: number }>;

export interface ListingsPage {
  items: ApiListing[];
  next_cursor: string | null;
}

/**
 * One API row as the design's template reads it.
 *
 * `id` is the API's `id`, never its `slug` (A-L5.1 (1)): a listing whose name is not disclosed is
 * served `slug: null`, because a slug is the name in another spelling — so the slug is not a key
 * the frontend can rely on, and `id` is. The design uses `p.id` as a DOM key, as the key of its
 * own `NAMES`/`SRC` fixture maps and as the detail route's segment; a uuid serves all three.
 *
 * `name` and `photos` are added only when the API actually sent them, so an API row built from a
 * design fixture maps back to exactly that fixture — which is what keeps the pixel gates honest
 * (D6) now that A12 has the design read both.
 */
export function toPractice(row: ApiListing): Practice {
  const p: Practice = {
    id: row.id,
    area: row.area,
    type: row.type,
    price: row.price,
    rev: row.rev,
    docs: row.docs,
    rooms: row.rooms,
    sqft: row.sqft,
    bldg: row.bldg,
    lat: row.lat,
    lng: row.lng,
    est: row.est,
    listed: row.listed,
    status: row.status,
    pop: row.pop,
    growth: row.growth,
    income: row.income,
    hh: row.hh,
    note: row.note,
    staff: row.staff,
    hours: row.hours,
    services: row.services,
    facility: row.facility,
    ownership: row.ownership,
    market: row.market
  };
  if (row.name !== null) p.name = row.name;
  if (row.photos.length > 0) p.photos = row.photos;
  return p;
}

/** The mean position of `market`'s located practices, or the centre of the US if it has none. */
export function centroid(practices: Practice[], market: string): [number, number] {
  const located = practices.filter((p) => p.market === market && p.lat !== null && p.lng !== null);
  if (located.length === 0) return US_CENTER;
  const lat = located.reduce((sum, p) => sum + (p.lat as number), 0) / located.length;
  const lng = located.reduce((sum, p) => sum + (p.lng as number), 0) / located.length;
  return [lat, lng];
}

/**
 * Replace the fixture practices and reconcile the market table, both IN PLACE.
 *
 * A market the design already knows keeps its own centre and zoom: the design's Austin centre
 * is [30.31, -97.75] while the centroid of its nine Austin fixtures is about [30.36, -97.77],
 * and recomputing it would pan the map and fail a zero-tolerance visual gate for a reason that
 * has nothing to do with this change. A market with no listings left is dropped so the metro
 * selector never offers an empty one.
 */
export function applyListings(rows: ApiListing[], practices: Practice[], markets: Markets): void {
  const next = rows.map(toPractice);
  practices.length = 0;
  for (const p of next) practices.push(p);
  const wanted = new Set(next.map((p) => p.market));
  for (const key of Object.keys(markets)) {
    if (!wanted.has(key)) delete markets[key];
  }
  for (const key of wanted) {
    if (!(key in markets)) markets[key] = { center: centroid(next, key), zoom: MARKET_ZOOM };
  }
}

/**
 * Fetch the published listings and install them. Returns whether it did.
 *
 * A refusal (the anonymous 401 the identity design intends), an unreachable API, a request
 * that outlives `LOAD_TIMEOUT_MS` and an unparseable body all leave the design's fixtures in
 * place and return false — the screen must never go blank because a read failed, and the abort
 * surfaces as a rejected promise, which the `catch` below already handles. A 200 always wins,
 * empty list included: at that point the API is the source of truth and the design's own
 * "no results" state is the honest thing to show.
 */
export async function loadListings(
  fetchFn: typeof fetch,
  practices: Practice[],
  markets: Markets,
  url: string = LIST_URL
): Promise<boolean> {
  let page: ListingsPage;
  try {
    const response = await fetchFn(url, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(LOAD_TIMEOUT_MS)
    });
    if (!response.ok) return false;
    page = (await response.json()) as ListingsPage;
  } catch {
    return false;
  }
  applyListings(page.items, practices, markets);
  return true;
}
