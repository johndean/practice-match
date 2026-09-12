// The design-fixture stub for the app Playwright project (spec 2026-09-06 D6).
//
// It is DERIVED from `logic.js`'s own arrays rather than hand-copied, so it can never drift
// from the design: `toApiShape` is the exact inverse of `load.ts`'s `toPractice`, which means
// the app under test reconstructs the design's practices field for field and every pixel
// still matches the design file. `frontend/src/listings/load.test.ts` proves that round trip on
// all twenty-one fixtures, and on `MARKETS` too; if it ever fails, the pixel gate is about to
// fail with it and the fix belongs there, never in the tolerance.
//
// THE ONE FIELD THAT IS NOT WHAT THE SERVER WOULD SEND: `name`. The real endpoint never returns
// null — a listing whose `name_disclosed` is false is served the design's own anonymised label,
// `<area> Veterinary` (A-L5, `app/api/listings.py`'s `anonymised_name`). But the design's
// twenty-one fixtures carry no name at all: their titles come from `practiceName`'s own `NAMES`
// map, which A12 leaves in place behind `p.name`. Sending a label here would therefore override
// the design's own titles and move every card and detail screen. `null` is the value that means
// "the design has no name for this practice", and it is the only value that keeps the gates
// comparing like with like. `photos: []` is the same statement about the photo slots — and there
// it IS exactly what the server sends for a listing with no photographs. `photo_captions: []`
// says the same about the descriptions amendment A15 reads (A-L11): the design's fixtures have
// no words of their own, so every caption they render is the design's own fixed slot caption.
import { ECON_K, P, VETS } from '../src/logic.js';

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
    name_disclosed: true,
    market: p.market,
    area: p.area,
    type: p.type,
    city: p.area,
    state: (p.market || ', TX').split(', ')[1],
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
    photos: [],
    photo_captions: [],
    // B10: the design's OWN market-data figures, in the shape the endpoint serves them. B7 added
    // these two fields and this stub kept sending null for both, so `applyListings` installed
    // nothing and cleared the design's fixture keys — the app under test then had no
    // establishment count and no payroll figure for any of the twenty-one practices, and the
    // docked panel's Competitive Landscape row went blank against a reference that shows it.
    // A stub that contradicts the endpoint it stands in for is a trap; `undefined` here would be
    // one too, so an id the design has no figure for sends `null`, which is what the server does.
    vets: VETS[p.id] ?? null,
    econ_k: ECON_K[p.id] ?? null,
    // D-C32: the design's fixtures are all Census places, so no fixture is ever served a label —
    // and every approved state therefore keeps the design's own wording, byte for byte.
    community_label: null,
    // D-C38: the same statement about the two per-figure fields A27 reads. The design's fixtures
    // carry no geography to name and no approximate median, so both are null and the Growth and
    // Median income tiles render the design's own "Since <year>" and "Household, 2023" — which is
    // what keeps `detail`'s frozen hash where it is. A non-null here would move it.
    growth_scope: null,
    income_note: null,
    // A33.1: the design's fixtures carry no stored index and no approximate median, so the panel
    // falls through to the design's OWN fixture arithmetic (`incomeNat`) and its own sub-line —
    // which is what keeps every approved Browse state on its pixels. A non-null here would move
    // `browse-market-panel`.
    income_vs_us_pct: null,
    income_approximate: null
  };
}

/** The whole design catalogue as one `GET /api/listings` page body. */
export function designListingsBody() {
  return JSON.stringify({ items: P.map(toApiShape), next_cursor: null });
}
