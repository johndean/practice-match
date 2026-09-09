// The design-fixture stub for the seller COLLECTION, in the D6 stub's own shape and for the
// same reason (A-SL2, as re-ruled by controller amendment A-SL23 (2)).
//
// `seller-dash` is one of CLAUDE.md's thirteen frozen screens and its four rows are the DESIGN's
// own `sellerListings` fixtures. Until this ruling the app reached them through an ERROR: the
// oracle answered the collection with a body carrying no `items`, `list()` rejected on it, and
// `sellerVals` fell back to `s.sellerListings`. That made the frozen capture depend on a failure
// the real API cannot produce — and the same fallback showed a REAL seller four invented
// listings whenever their load genuinely failed (SL7 review, Critical-2). Both are gone: with
// the adapter present the dashboard renders what the API answered and nothing else, so the
// oracle has to ANSWER, through the success path, with the design's own four rows.
//
// It is DERIVED from `logic.js`'s own array rather than hand-copied, exactly as
// `design-listings.mjs` is derived from `P`, so it can never drift from the design.
//
// THE THREE FIELDS THAT ARE NOT WHAT THE SERVER WOULD SEND: `title`, `meta` and `note`. This is
// `design-listings.mjs`'s `name: null` again — a value the real endpoint never sends, carried so
// that the DESIGN's own words stand in the oracle — and here it is unavoidable rather than
// merely convenient: A-SL2 recorded that the design's row prose is not constructible from any
// column ("Live since August 24 · 34 views, 2 requests" needs a view count and a request count
// this slice does not have; "Draft started August 30" needs a creation date `serialise_draft`
// does not carry). `toDashboardRow` therefore takes a row's own words where a row has them and
// derives them from the columns where it does not — which is every row the real API sends.
import { Component } from '../src/logic.js';

/** The design's own four dashboard rows, read out of the prototype's initial state. */
export function designSellerRows() {
  return new Component({}).state.sellerListings;
}

/** Those four rows as one complete page of `GET /api/seller/listings`. */
export function designSellerPageBody() {
  return JSON.stringify({ items: designSellerRows(), next_cursor: null });
}
