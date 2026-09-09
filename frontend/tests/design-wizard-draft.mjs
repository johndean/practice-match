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
// Every other field is the value the design's own `state.w` already holds, so `toWizardState`
// changes nothing the wizard renders — `seller.test.ts` pins that, which is what keeps the three
// captures byte-identical while the app's real behaviour becomes honest: a listing created against
// the real API answers with no assets at all, and the wizard shows no tiles and "Photos attached 0".
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
 *  shapes one: every column the wizard reads, at the value the DESIGN's own `state.w` holds, and
 *  the two ordered projections step 6 renders. */
export function designWizardDraft(listingId) {
  const assets = designWizardAssets(listingId);
  return {
    id: listingId, slug: `listing-${listingId}`, status: 'draft',
    name: null, type: 'Small animal', est: null, ownership: 'Sole proprietor',
    city: null, zip: null, price: null, rev: null, docs: null, rooms: null, sqft: null,
    hours: null, desc: null, bldg: 'Included', facilityType: 'Standalone', facility: null,
    anon: true, revBand: false, docsLocked: true,
    state: null, market: null, area: null,
    decline_reason: null, submitted_at: null, updated_at: '2026-09-09T00:00:00+00:00',
    assets,
    photos: assets.filter((a) => a.kind === 'photo').map((a) => ({ id: a.id, name: a.name })),
    documents: assets.filter((a) => a.kind !== 'photo')
      .map((a) => ({ ...a, url: `/api/seller/listings/${listingId}/documents/${a.id}` }))
  };
}

/** That draft as the body of both writes the wizard captures make: the read after `create()`, and
 *  `wizard-done`'s Submit for review. */
export function designWizardDraftBody(listingId) {
  return JSON.stringify(designWizardDraft(listingId));
}
