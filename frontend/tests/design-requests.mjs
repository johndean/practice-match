// The design-fixture stub for the per-buyer access-request collection (Task 14 of
// docs/superpowers/plans/2026-09-18-per-buyer-disclosure.md), in `design-seller-listings.mjs`'s
// own shape and for the identical reason.
//
// `detail`, `requests` and `seller-dash` (`mobile-detail` and `seller-dash-empty` render the
// first and the third's own screens) are among CLAUDE.md's thirteen frozen screens, and once an
// adapter is wired the app renders what the real endpoints answered and nothing else (A16.1's own
// rule, A52's own application of it): `GET /api/requests/mine` for the buyer's own "My Requests"
// list and the detail screen's `sent`/`req`/`unlocked`, `GET /api/seller/requests` for the seller
// dashboard's own inbox. Both would otherwise answer a real, freshly-seeded local database's
// EMPTY array, and the app would correctly render no rows at all — a real state, but not the
// frozen one, whose pixels are the design's own three fixture requests.
//
// DERIVED from `logic.js`'s own array rather than hand-copied, exactly as `design-seller-
// listings.mjs` is derived from `sellerListings` and `design-listings.mjs` from `P`.
//
// THE ROWS ARE HANDED BACK VERBATIM, in the design's OWN shape (`id`, `pid`, `buyer`, `status`,
// `msg`, `reply?`, `when`) rather than synthesised as `ApiRequestRow`s the real endpoint could
// have sent. That is `design-seller-listings.mjs`'s own `title`/`meta`/`note` situation one
// screen over, and for the identical reason: the ACCEPTED row's own reply — "Happy to share.
// Financial packet unlocked — call me next week." — is not constructible from any column the real
// `request` table has (`denial_reason` exists only for a DENIED row; `migrations/096_request.sql`
// gives an approval no free-text field at all). `frontend/src/requests/buyer.ts`'s `toDesignRow`
// recognises a row already in this shape (`'pid' in row`) and returns it as it stands, the same
// union `toDashboardRow` already takes for `DesignRow` — every row the real endpoints send takes
// the other arm.
//
// The three fixture rows' own `pid`s (`p1`, `p7`, `p6`) are why `sellerVals`'s ORIGINAL filter
// (`r.pid === "p1" || r.pid === "p7" || r.pid === "p6"`) — still the no-adapter path's fallback —
// and this stub's UNFILTERED array agree on every row: there is nothing here for the seller's own
// endpoint to exclude.
import { Component } from '../src/logic.js';

/** The design's own three request rows, read out of the prototype's initial state. */
export function designRequestRows() {
  return new Component({}).state.requests;
}

/** Those three rows as `GET /api/requests/mine` or `GET /api/seller/requests` answers them — a
 *  bare array, neither route paginating (`app/api/requests.py::list_my_requests`,
 *  `app/api/seller_requests.py::list_inbox`). */
export function designRequestsBody() {
  return JSON.stringify(designRequestRows());
}
