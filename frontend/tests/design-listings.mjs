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
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Component, ECON_K, P, VETS } from '../src/logic.js';

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
    // A33.1: the design's fixtures carry no stored index and no approximate median. `income_note`
    // and `income_approximate` therefore stay null here and the tile shows no qualifier, which is
    // the design's own sub-line byte for byte. `income_vs_us_pct` is null in the ROW and supplied
    // by `designListingsBody` instead — see its own note; putting it here would break this
    // function's one promise, that it is the exact inverse of `toPractice`.
    income_vs_us_pct: null,
    income_approximate: null
  };
}

//: The design's OWN fixture constant for the U.S. median household income, read out of the method
//: that declares it rather than typed here — so if the design's constant ever moves, the stub
//: moves with it instead of quietly disagreeing. `marketPanel`'s source is the declaration site
//: (`const incomeNat = 75149;`), and reading it this way needs no file access and no second copy.
const INCOME_NAT = Number(/const incomeNat = (\d+);/.exec(String(Component.prototype.marketPanel))[1]);

//: `logic.js`'s OWN `num`, EVALUATED from its own declaration rather than re-implemented (fix
//: round 2, review Minor). The first version of `designIncomeIndex` parsed the median with
//: `String(p.income).replace(/[^0-9.]/g, '')` — the strip-every-non-digit form A24.43 removed from
//: the snapshot strip for losing a leading minus, and A24.58 removed from `communities()` for
//: gluing a trailing year onto the digits ("+14.2% since 2015" → 14.22015). It agreed with the
//: design on all 21 fixtures, every one of them a positive "$118,400"-shaped string, and would
//: have disagreed the moment one carried either. `num` is a module-level arrow in `logic.js` and
//: is not exported, so it is not reachable through `Component.prototype`; its declaration is one
//: line and is read and evaluated here, which is a DERIVATION and not a copy — a re-cut of `num`
//: moves this with it. Same discipline as `INCOME_NAT` above, one file read further.
const num = (() => {
  const src = readFileSync(fileURLToPath(new URL('../src/logic.js', import.meta.url)), 'utf8');
  const decl = /^const num = (\(s\) => \{.*\});$/m.exec(src);
  if (!decl) throw new Error('logic.js no longer declares `const num = (s) => { … };` on one line');
  // eslint-disable-next-line no-new-func -- the design's own source is the definition, not input
  return new Function(`return ${decl[1]};`)();
})();

/** The design's own index for one fixture: how far its median sits above or below the U.S. figure
 *  the design itself divides by, ALREADY ROUNDED so `Math.round(sel.incomeVsUs)` in the panel and
 *  the design's own `Math.round(((c.income - incomeNat) / incomeNat) * 100)` cannot differ by one
 *  through double rounding. `null` for a fixture with no median, which is what the API sends —
 *  and `num`'s own zero-for-a-string-carrying-no-number contract everywhere else, because the
 *  panel reads `c.income`, which `communities()` produced with this very function. */
export function designIncomeIndex(p) {
  if (p.income == null) return null;
  return Math.round(((num(p.income) - INCOME_NAT) / INCOME_NAT) * 100);
}

/** The whole design catalogue as one `GET /api/listings` page body.
 *
 * A33.1c — WHY THIS BODY CARRIES ONE FIELD `toApiShape` DOES NOT. With the market adapter present
 * the panel reads the SERVED index or nothing and never the design's own constant, and the app
 * under test always has that adapter while the reference never does. So an API that answered
 * `income_vs_us_pct: null` here would make the app render no index over a reference that renders
 * one, and `browse-market-panel`, `browse-panel-lightbox` and `browse-market-strip-location`
 * would diverge for a reason that is about the harness rather than about the design. The oracle
 * answers the app with the DESIGN'S OWN number, which is exactly what `harness.ts` does for the
 * seller's listings and the admin review queue (A16.1, A17.1): "the oracle answers the app with
 * those same four rows".
 *
 * It is added HERE and not in `toApiShape` because that function has one promise — it is the
 * exact inverse of `load.ts`'s `toPractice`, pinned fixture by fixture in
 * `frontend/src/listings/load.test.ts` — and a field the design's own `P` cannot carry would
 * break it. This function stands in for the SERVER, which does carry it. */
export function designListingsBody() {
  return JSON.stringify({
    items: P.map((p, i) => ({ ...toApiShape(p, i), income_vs_us_pct: designIncomeIndex(p) })),
    next_cursor: null
  });
}
