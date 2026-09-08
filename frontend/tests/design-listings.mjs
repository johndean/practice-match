// The design-fixture stub for the app Playwright project (spec 2026-09-06 D6).
//
// It is DERIVED from `logic.js`'s own arrays rather than hand-copied, so it can never drift
// from the design: `toApiShape` is the exact inverse of `load.ts`'s `toPractice`, which means
// the app under test reconstructs the design's practices field for field and every pixel
// still matches the design file. `frontend/src/listings/load.test.ts` proves that round trip on
// all twenty-one fixtures, and on `MARKETS` too; if it ever fails, the pixel gate is about to
// fail with it and the fix belongs there, never in the tolerance.
//
// THE ONE PLACE THIS IS NOT WHAT THE SERVER WOULD SEND: `name`. The real endpoint never returns
// null — a listing whose `name_disclosed` is false is served the design's own anonymised label,
// `<area> Veterinary` (A-L5, `app/api/listings.py`'s `anonymised_name`). But the design's
// twenty-one fixtures carry no name at all: their titles come from `practiceName`'s own `NAMES`
// map, which A12 leaves in place behind `p.name`. Sending a label here would therefore override
// the design's own titles and move every card and detail screen. `null` is the value that means
// "the design has no name for this practice", and it is the only value that keeps the gates
// comparing like with like. `photos: []` is the same statement about the photo slots — and there
// it IS exactly what the server sends for a listing with no photographs.
import { MARKETS, P } from '../src/logic.js';

/**
 * One design fixture in the shape `GET /api/listings` returns.
 *
 * `i` is the fixture's index in `P`, used only to give each row a distinct `listed_at` in the
 * order the endpoint itself pages (`listed_at DESC, id DESC`). Nothing reads it — `toPractice`
 * drops it — but a stub that contradicts the endpoint it stands in for is a trap for the next
 * reader.
 */
export function toApiShape(p, i) {
  return {
    // A-L5.1 (1): the app keys off `id`, never `slug`, and here the design's own fixture id IS
    // the id — which is what keeps `NAMES[p.id]`, `SRC["ph-" + p.id + "-…"]` and the detail
    // route resolving to exactly what the design resolved them to.
    id: p.id,
    slug: null,
    name: null,
    market: p.market,
    area: p.area,
    type: p.type,
    city: p.area,
    state: p.market.split(', ')[1],
    street: null,
    zip: null,
    phone: null,
    hours: p.hours ?? null,
    price: p.price ?? null,
    rev: p.rev ?? null,
    docs: p.docs ?? null,
    rooms: p.rooms ?? null,
    sqft: p.sqft ?? null,
    bldg: p.bldg ?? null,
    est: p.est ?? null,
    listed: p.listed,
    listed_at: new Date(Date.UTC(2026, 8, 1) - i * 86400000).toISOString(),
    status: p.status,
    pop: p.pop ?? null,
    growth: p.growth ?? null,
    income: p.income ?? null,
    hh: p.hh ?? null,
    note: p.note ?? null,
    staff: p.staff ?? null,
    services: p.services ?? null,
    facility: p.facility ?? null,
    ownership: p.ownership ?? null,
    lat: p.lat ?? null,
    lng: p.lng ?? null,
    location_disclosed: true,
    photos: []
  };
}

/** The whole design catalogue as one `GET /api/listings` page body. */
export function designListingsBody() {
  return JSON.stringify({ items: P.map(toApiShape), next_cursor: null });
}

// `MARKETS` is imported for the round-trip's sake: `load.test.ts` reads it from `../logic.js`
// directly, and nothing imports it from here — but the design's market table is half of what
// this module is asserting the app reconstructs, and importing it keeps that visible.
export const DESIGN_MARKETS = MARKETS;
