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
// 200 is the endpoint's own MAX_LIMIT (`app/api/listings.py`). The demo catalogue is eighteen
// rows, so today it is one page — but `next_cursor` is followed until null (review M2), because
// a catalogue that outgrew one page would otherwise truncate in silence.
const LIST_URL = '/api/listings?limit=200';
// …and the loop is bounded. `AbortSignal.timeout` bounds each REQUEST, not the sequence, and
// `main.ts` awaits the whole read before it mounts — so a server that returns the same cursor
// for ever would hang the boot on a blank page, which is exactly what this module exists to
// prevent. Twenty pages is 4,000 listings, far past anything this product will hold.
export const MAX_PAGES = 20;

export interface ApiListing {
  id: string;
  // A-L5.1 (1): the slug is the listing's NAME in another spelling, so the server nulls it with
  // the name. Nothing here reads it — `p.id` is the API's `id` — but the field is part of the
  // contract and its nullability is the reason why.
  slug: string | null;
  name: string | null;
  // A-L5: served on every row, and dropped by `toPractice` — the design has no field for it.
  // Declared because the contract has it: `design-listings.mjs` claims to be `toPractice`'s exact
  // inverse, and a field the server sends and the stub does not is a gap in that claim (M1).
  name_disclosed: boolean;
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
  // Positional, and NULLABLE since A-L10: position `n` is the design's photo slot `n`, and the
  // server sends `null` for a slot no photograph of that hospital truthfully fills. Carried
  // through as-is — `photoSet`'s `p.photos[i]` renders the design's own placeholder for a null,
  // and compacting the list would put every later photograph under the wrong caption.
  photos: (string | null)[];
  // A-L11: one description per photograph, PARALLEL to `photos` — position `n` describes position
  // `n`, `null` where nobody has described that photograph yet. OPTIONAL because a server that
  // predates `090_listing_photo_captions.sql` does not send it, and because the D6 design-fixture
  // stub has nothing to say: A15 falls back to the design's own fixed slot caption wherever it is
  // absent, which is what keeps the approved states on their pixels.
  photo_captions?: (string | null)[];
  // B8: veterinary establishment count from Census CBP, or null if the market data is unavailable
  vets: number | null;
  // B8: annual payroll per establishment in $thousands from Census CBP, or null if unavailable
  econ_k: number | null;
  // B10 (D-C32), widened by D-C38: which area the AREA figures above describe — `pop`, `hh`,
  // `income` and the off-card `vets`, which move as one group. `null` means the listing's own
  // community (the Census `place` band), which is the wording the design already uses;
  // `"Within about 5 miles of the practice"` means the catchment band answered. The design
  // renders it wherever it names the area, so a buyer is never shown a catchment disguised as a
  // named city.
  community_label: string | null;
  // D-C38 (John, 2026-09-11): the geography the GROWTH figure was measured at, named exactly as
  // TIGER names it — "Dallas", "Orange County", never a composed "City of " prefix — which
  // `community_label` does NOT describe. `population_growth_pct` cannot
  // vary by band at all (the pipeline computes it once per listing and writes that one value into
  // all three bands, plan D12), so the Growth tile keeps the city-or-county figure and its own
  // sub-line names it. `null` where the geography has no name to give, and the design's own
  // "Since <year>" then stands.
  growth_scope: string | null;
  // D-C38: the median-income tile's whole sub-line, when that median is an approximation rather
  // than a published Census figure — a catchment median is a household-weighted average of the
  // tract medians inside the ring. Composed server-side because the tile has ONE sub-line and it
  // must carry the area and the qualifier together. `null` for a published place median, and the
  // design's own "Household, 2023" then stands.
  income_note: string | null;
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
  photos?: (string | null)[];
  photoCaptions?: (string | null)[];
  // B10 (D-C32): the API's `community_label`, under the design's own camel-case naming. Absent —
  // never `undefined` as a present key — when the figures came from the listing's own community,
  // which is what makes the design's `p.communityLabel || "…"` fall back to its own wording.
  communityLabel?: string;
  // D-C38: the same rule again for the two per-figure fields A27 reads — `growth_scope` and
  // `income_note` under the design's own camel-case naming, absent rather than present-and-
  // undefined, so `p.growthScope ? … : …` and `p.incomeNote || "…"` fall back to the design's
  // own literals and every approved state keeps its pixels.
  growthScope?: string;
  incomeNote?: string;
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
 * `name`, `photos` and `photoCaptions` are added only when the API actually sent them, so an API
 * row built from a design fixture maps back to exactly that fixture — which is what keeps the
 * pixel gates honest (D6) now that A12 has the design read the first two and A15 the third.
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
  // `!= null`, not `!== null` (M7): a malformed row with the key ABSENT would otherwise set
  // `p.name = undefined`, which is a key the design's `p.name ||` chain then has to absorb.
  if (row.name != null) p.name = row.name;
  if (row.photos.length > 0) p.photos = row.photos;
  // A-L11 (A15): the same rule again, and a presence test as well as a length one — a server
  // that predates `090_listing_photo_captions.sql` sends no `photo_captions` at all, and the
  // design's own fixed slot captions are the right answer for such a row.
  if (row.photo_captions && row.photo_captions.length > 0) p.photoCaptions = row.photo_captions;
  // B10 (D-C32): `!= null`, the same rule as `name` above — a row that omits the key entirely
  // must not set `p.communityLabel = undefined`, which would be a key the design's `||` chain
  // then has to absorb, and a difference the D6 round-trip identity would see.
  if (row.community_label != null) p.communityLabel = row.community_label;
  // D-C38: `!= null`, the same rule as `community_label` above and for the same M7 reason.
  if (row.growth_scope != null) p.growthScope = row.growth_scope;
  if (row.income_note != null) p.incomeNote = row.income_note;
  return p;
}

/** The mean position of `market`'s located practices, or the centre of the US if it has none. */
export function centroid(practices: Practice[], market: string): [number, number] {
  const located = practices.filter((p) => p.market === market && p.lat !== null && p.lng !== null);
  // A COPY (review M3): returning the exported constant would hand one shared array to every
  // unlocatable market, so a single in-place normalisation would corrupt all of them and the
  // constant itself.
  if (located.length === 0) return [...US_CENTER];
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
 *
 * B8: also install the market-data maps VETS and ECON_K from the API rows, and clear any
 * fixture keys that were there before. A null figure installs no key, and `communities()` then
 * yields `undefined` for it — never 0 (A21.1/A21.1c, D-C31: a missing figure is omitted, never
 * zeroed).
 *
 * B10: the CLEAR runs BEFORE the install, not after. The design's own fixture ids are exactly
 * what the D6 stub sends back (`tests/design-listings.mjs`), so clearing afterwards deleted every
 * figure the page had just installed and the docked panel had no establishment count for any
 * design fixture. On a seeded environment the ids are uuids and the two orders are equivalent.
 */
export function applyListings(
  rows: ApiListing[],
  practices: Practice[],
  markets: Markets,
  vets?: Record<string, number>,
  econ_k?: Record<string, number>
): void {
  const next = rows.map(toPractice);

  // B8: map every row BEFORE clearing anything, so a malformed row leaves the fixtures standing
  if (vets && econ_k) {
    // Clear fixture keys (p1…p9, c1…c4, o1…o4, g1…g4) FIRST — see the note above.
    const fixtureIds = ['p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9',
                        'c1', 'c2', 'c3', 'c4',
                        'o1', 'o2', 'o3', 'o4',
                        'g1', 'g2', 'g3', 'g4'];
    for (const id of fixtureIds) {
      delete vets[id];
      delete econ_k[id];
    }

    // Install API vets and econ_k (only non-null values get keys)
    for (const row of rows) {
      if (row.vets != null) vets[row.id] = row.vets;
      if (row.econ_k != null) econ_k[row.id] = row.econ_k;
    }
  }

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

/** `base` with a `cursor` query parameter added, whichever query it already carries. */
function withCursor(base: string, cursor: string): string {
  return `${base}${base.includes('?') ? '&' : '?'}cursor=${encodeURIComponent(cursor)}`;
}

/**
 * Fetch every published listing and install them. Returns whether it did.
 *
 * A refusal (the anonymous 401 the identity design intends), an unreachable API, a request
 * that outlives `LOAD_TIMEOUT_MS` and an unparseable body all leave the design's fixtures in
 * place and return false — the screen must never go blank because a read failed, and the abort
 * surfaces as a rejected promise, which the `catch` below already handles.
 *
 * AN EMPTY OR MALFORMED 200 DOES THE SAME (A-L6.2 (1), review C1/I2). The brief's earlier "a 200
 * always wins, empty list included" is withdrawn: the design has no empty-catalogue state at
 * this level — `detail()` reads `P[0]` and `renderVals()` reads
 * `MARKETS[s.market || "Austin, TX"].center`, both on every render — so emptying the prototype's
 * arrays is a blank APP, not an empty Browse. Between Task L7's deploy and its seed, and in any
 * environment that has not been seeded, the member therefore sees the design's fixtures, which
 * is the pre-L6 behaviour.
 *
 * `applyListings` maps every row BEFORE it clears anything, so even a malformed row inside an
 * otherwise well-formed page leaves the fixtures standing; `main.ts` catches that throw so the
 * app still mounts.
 *
 * B8: also accepts the market-data maps VETS and ECON_K so they can be installed from the API.
 */
export async function loadListings(
  fetchFn: typeof fetch,
  practices: Practice[],
  markets: Markets,
  url: string = LIST_URL,
  vets?: Record<string, number>,
  econ_k?: Record<string, number>
): Promise<boolean> {
  const rows: ApiListing[] = [];
  try {
    let next: string | null = url;
    for (let page = 0; next !== null && page < MAX_PAGES; page++) {
      const response = await fetchFn(next, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(LOAD_TIMEOUT_MS)
      });
      if (!response.ok) return false;
      const body = (await response.json()) as ListingsPage;
      if (!Array.isArray(body.items)) return false;
      rows.push(...body.items);
      next = body.next_cursor ? withCursor(url, body.next_cursor) : null;
    }
  } catch {
    return false;
  }
  if (rows.length === 0) return false;
  applyListings(rows, practices, markets, vets, econ_k);
  return true;
}
