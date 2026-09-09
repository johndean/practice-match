// The design-fixture stub for ONE seller draft — the listing "Create a listing" makes on the
// oracle — in the D6 / A-SL23 (2) stub's own shape and for the same reason (A-SL25 (1)).
//
// `wizard-step-1`, `wizard-preview` and `wizard-done` are three of CLAUDE.md's thirteen frozen
// screens, and all three reach the wizard through "Create a listing" (`screens.ts`'s `wizard`
// helper). Until this ruling the app reached their pixels through a HOLE: `startWizard` left
// `wizAssets` unset, A16.4's tile source keyed on that rather than on the adapter, and the design's
// own four-item literal rendered — so the app agreed with the reference because it was showing the
// DESIGN's three fixture photographs on a listing that has none. The design's step rail jumps to
// any step with no save and no read, so a real seller saw them too, and "Photos attached 3" on the
// screen immediately before Submit for review (SL7 re-review, Critical-A).
//
// A16.4 keys on the adapter now, exactly as A16.1 does on the dashboard, so the app renders the
// draft the API answered and nothing else. The oracle therefore has to ANSWER — through the
// success path — with a draft carrying the design's own three photograph tiles, which is the
// answer the dashboard already gets from `design-seller-listings.mjs`.
//
// DERIVED, never hand-copied: the tiles are read out of the prototype's own `wizardVals()` with no
// adapter passed, which is `logic.js`'s fallback literal `[Exterior.jpg, Lobby.jpg, Treatment.jpg,
// Floor plan.pdf].slice(0, 3 + (w.photos || 0))` evaluated at the design's own `w.photos: 0`. Edit
// that literal and this stub follows it; hand-copy a tile and `harness.test.ts` fails.
//
// Every other column is what `create` really leaves there — NULL, all twenty-one of them (A-SL27
// (1); `harness.test.ts` pins the set, and `tests/api/test_seller_listings.py` pins the API's).
// Until round 4 this stub answered the DESIGN's own `type`, `ownership`, `bldg` and `facilityType`
// for a listing nobody had touched, which hid CRITICAL-C: the real API answers null for all four,
// `toWizardState` turned each into `""`, and the first Continue was a 400. `toWizardState` leaves a
// null column alone now, so the design's literal supplies the default on the app exactly as it does
// on the reference, and `seller.test.ts` pins that laying this draft over the design's `w` moves
// nothing — which is what keeps the three captures byte-identical while the app's real behaviour is
// honest: a listing created against the real API opens on the design's four defaults, with no tiles
// and "Photos attached 0".
import { Component } from '../src/logic.js';

/** The design's own step-6 tiles for a wizard nobody has typed into. */
export function designWizardTiles() {
  return new Component({}).wizardVals().uploads;
}

/** What the API would have stored for a tile of that badge. `Photo` is the only badge the design's
 *  fresh-wizard literal produces today; the other two are `app/api/seller_listings.py`'s own
 *  `DOCUMENT_TYPES`, here so a design change that adds a document tile keeps this stub truthful. */
const CONTENT_TYPE = { Photo: 'image/webp', PDF: 'application/pdf', CSV: 'text/csv' };

/** Those tiles as `listing_asset` rows, in the `ApiAsset` shape `serialise_draft` sends. */
export function designWizardAssets(listingId) {
  return designWizardTiles().map((tile, i) => ({
    id: `${listingId}-a${i + 1}`,
    // `photo` is the API's own kind; a document's kind is `other` until Rev 3 gives step 6 a
    // picker (spec D18, `app/api/seller_listings.py::upload_document`).
    kind: tile.kind === 'Photo' ? 'photo' : 'other',
    name: tile.name,
    content_type: CONTENT_TYPE[tile.kind] || 'application/octet-stream',
    byte_size: 1024 * (i + 1)
  }));
}

/** The whole draft `GET /api/seller/listings/{id}` answers with, exactly as `serialise_draft`
 *  shapes one for a row `create` has just inserted: every column NULL, the switches, and the two
 *  ordered projections step 6 renders — carrying the design's own three tiles.
 *
 *  `revBand: false` is the design's value, not the table's: `create` leaves `rev_disclosed` at
 *  its default `false`, which `serialise_draft` answers as `revBand: true`, while the design's
 *  `w` opens the step-7 switch OFF. A-SL27 (1) rules the NULL set alone; this one field is
 *  recorded for the controller in the round-4 report rather than moved here, because `wizard-step-7`
 *  is a frozen capture of that switch. */
export function designWizardDraft(listingId, status = 'draft') {
  const assets = designWizardAssets(listingId);
  return {
    id: listingId, slug: `listing-${listingId}`, status,
    name: null, type: null, est: null, ownership: null,
    city: null, zip: null, price: null, rev: null, docs: null, rooms: null, sqft: null,
    hours: null, desc: null, bldg: null, facilityType: null, facility: null,
    anon: true, revBand: false, docsLocked: true,
    state: null, market: null, area: null,
    decline_reason: null, submitted_at: null, updated_at: '2026-09-09T00:00:00+00:00',
    assets,
    photos: assets.filter((a) => a.kind === 'photo').map((a) => ({ id: a.id, name: a.name, source: 'asset' })),
    documents: assets.filter((a) => a.kind !== 'photo')
      .map((a) => ({ ...a, url: `/api/seller/listings/${listingId}/documents/${a.id}` }))
  };
}

/** That draft as the body of both reads the wizard captures make: the one after `create()`, and
 *  `wizard-done`'s Submit for review — which answers `in_review`, because that is what
 *  `POST …/submit` leaves the listing as (round-2 re-review, Info-F). Nothing reads the status:
 *  `logic.js` discards the resolved value and the design's "Submitted" card is drawn
 *  synchronously. A stub that says something the endpoint it stands in for cannot say is a trap
 *  for the next reader, which is the same rule `design-listings.mjs` states about its own one
 *  field that differs. */
export function designWizardDraftBody(listingId, status = 'draft') {
  return JSON.stringify(designWizardDraft(listingId, status));
}
