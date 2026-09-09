// The design-fixture stub for the ADMIN LISTINGS queue — the `seller-dash`/`design-seller-
// listings.mjs` precedent (A-SL2, re-ruled A-SL23 (2)) applied to `admin-listings`, Task SL8.
//
// `admin-listings` is one of CLAUDE.md's thirteen frozen screens and its rows are the design's own
// `sets.listings.rows`, ALL FIVE of them — the "Flagged"/Investigate row included. A-SL24 (1) is
// explicit that the frozen capture "keeps its hash" through this stub answering "the design's
// fixture rows" (plural, unqualified) as a REAL page; A-SL24 (4)'s "the fifth fixture row … is not
// reproduced" is the LIVE mapping's own limit (`toListingRows`'s `PILLS`/`ACTIONS`, keyed by real
// `listing.status` values, has no entry a real row could ever match to "Flagged" — no such status
// exists) — not a limit on this oracle-only fixture, whose whole job is reproducing the design's
// pixels regardless of what a real response could ever contain. `DesignListingRow` does not run
// through `PILLS`/`ACTIONS` at all: it carries a row's own `pill`/`pillStyle` and action styles
// verbatim, so it represents a status backed by no column exactly as easily as one backed by five.
// This is `design-seller-listings.mjs`'s own `title`/`meta`/`note` move again — fields "the real
// endpoint would never send", carried here because the alternative is losing a screen's pixels.
//
// Until this task the harness answered this collection with an EMPTY page (`sellerPageBody([])`,
// "nothing fetches it yet"); with `frontend/src/admin/listings.ts`'s adapter now the app's
// default, the frozen capture has to answer through the SAME success path
// `design-seller-listings.mjs` already proved for `seller-dash` — a REAL page of
// `GET /api/admin/listings`.
//
// DERIVED, never hand-copied: the design's five rows come straight off `adminVals()`'s own
// COMPUTED cells (`main`, `sub`, `pill`, `pillStyle`, and each action's `label`/`style`), not
// retyped here. This file touches only `logic.js`, exactly as `design-seller-listings.mjs` and
// `design-wizard-draft.mjs` do — no TypeScript module, on either side of the D6 stub — so a
// `DesignListingRow` carries whole STYLE STRINGS rather than a tone name this file would have had
// to re-derive by importing `admin/listings.ts`'s own `cell()`/`A()` back into itself.
//
// `toListingRows` (`frontend/src/admin/listings.ts`) reads this shape verbatim: `title`/`titleSub`
// become the "Listing" cell's `main`/`sub`, `seller`/`figures` the "Seller and figures" cell's,
// `pill`/`pillStyle` are copied onto the status cell as they stand, and each action's own `style`
// likewise — so the app's LIVE table, built from the SAME `cell()`/`A()` `admin/listings.ts` copies
// verbatim from this very `adminVals()`, renders byte-identical pixels to what the reference (no
// adapter, `sets.listings.rows` itself) already draws.
import { Component } from '../src/logic.js';

/** The design's own Listings rows, computed exactly as the reference renders them — five, in
 *  `sets.listings.rows`' own order. */
function designListingCells() {
  const c = new Component({});
  c.setState({ adminTab: 'listings' });
  return c.adminVals().rows.map((r) => r.cells);
}

/** All five, as `toListingRows`'s `DesignListingRow` union arm expects — the Flagged row included
 *  (see the module note: it is unreachable from real data, never from this oracle-only fixture). */
export function designAdminListingRows() {
  return designListingCells().map((cells, i) => ({
    id: `admin-fixture-${i + 1}`,
    title: cells[0].main, titleSub: cells[0].sub,
    seller: cells[1].main, figures: cells[1].sub,
    pill: cells[2].pill, pillStyle: cells[2].pillStyle,
    actions: cells[3].actions.map((a) => ({ label: a.label, style: a.style }))
  }));
}

/** Those five rows as one complete page of `GET /api/admin/listings`. */
export function designAdminListingsBody() {
  return JSON.stringify({ items: designAdminListingRows(), next_cursor: null });
}
