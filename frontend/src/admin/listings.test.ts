// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Component } from '../logic.js';
import { designAdminListingRows } from '../../tests/design-admin-listings.mjs';
import {
  ACTIONS, NOTE_REQUIRED, PILLS,
  cell, makeAdminListingsAdapter, toListingRows,
  type Cell, type ListingItem, type ListingsUi
} from './listings';

/** `list()` answers a PAGE now (A39, ruling 1) — the rows the table renders and the number the
 *  tab badges. Every case below that only cares about the rows reads them through this. */
const listRows = async (): Promise<Cell[][]> => (await makeAdminListingsAdapter().list()).rows;

// ---------------------------------------------------------------------------------------
// The design's OWN `adminVals()` output is the oracle for every style string below — exactly
// `admin/users.test.ts`'s own method, applied a second time so a drift in either copy fails on
// its own. The design's FIFTH Listings row ("Flagged"/Investigate) IS one of the five the frozen
// `admin-listings` capture's own oracle fixture reproduces verbatim (see the "reproduces the
// design's own five rows" test below and `design-admin-listings.mjs`'s module note) — what
// `listing.status` truly has no value for, and what `toListingRows`'s `PILLS`/`ACTIONS` therefore
// never produce from REAL data (A-SL24 (4)), is a status a live row could ever be decided by
// matching to it; nothing here invents one.
// ---------------------------------------------------------------------------------------
const designCells = (tab: string): Cell[][] => {
  const c = new Component({});
  c.setState({ adminTab: tab });
  return c.adminVals().rows.map((r: { cells: Cell[] }) => r.cells);
};
const DESIGN = designCells('listings');
// Row 0/1: "In review" (warn). Row 2: "Published" (ok). Row 3: "Paused" (info). Row 4: "Flagged"
// (bad) — the tone no LIVE status ever carries, still read here for the tone string alone.
const PILL = { warn: DESIGN[0][2].pillStyle, ok: DESIGN[2][2].pillStyle, info: DESIGN[3][2].pillStyle, bad: DESIGN[4][2].pillStyle };
const BTN = {
  primary: DESIGN[0][3].actions[0].style,   // A("Publish", "primary")
  danger: DESIGN[0][3].actions[1].style,    // A("Reject", "danger")
  plain: DESIGN[2][3].actions[0].style      // A("Unpublish") — no tone
};

function recordingUi(note: string | null = 'a reviewer note', fields: { state: string; market: string } | null = { state: 'TX', market: 'Austin, TX' }) {
  const calls: string[] = [];
  const ui: ListingsUi = {
    needsNote: (action) => { calls.push(`needsNote:${action}`); return Promise.resolve(note); },
    needsFields: (action) => { calls.push(`needsFields:${action}`); return Promise.resolve(fields); },
    decide: (item, action, given, f) => { calls.push(`decide:${item.id}:${action}:${given}:${f ? `${f.state}/${f.market}` : 'null'}`); return Promise.resolve(); }
  };
  return { ui, calls };
}

// `name: null` is the DESIGN's own row as a live payload, and it is what every case outside the
// "names the practice" block below is about. Until John's 2026-09-16 ruling this field was the one
// member of `ListingItem` nothing read, so it carried an arbitrary `'Mixed practice'`; a named row
// now takes its own name as the title, so leaving that value here would have quietly turned this
// whole file into the NAMED arm and left the unnamed one — the arm the ruling says must not
// regress, two of the thirty-two rows on QA — pinned by nothing. Every assertion below is
// unchanged from before that ruling, byte for byte, which is the proof it did not regress.
const BASE: ListingItem = {
  id: 'l1', status: 'in_review', name: null, type: 'Mixed', city: 'Bastrop',
  price: 860000, rev: 1200000, docs: 2, bldg: 'Leased', state: null, seller_name: 'Dr. Susan Ortiz',
  submitted_at: '2026-09-01T12:00:00Z',
  // A39: the three the queue now serves beside the draft (`app/api/admin_listings.py::list_all`)
  // and the decline reason `serialise_draft` has carried since A-SL19 (9).
  listed_at: '2026-08-24T09:00:00Z', status_changed_at: '2026-08-12T18:30:00Z',
  status_changed_by: 'buyer,seller', decline_reason: null
};
const item = (over: Partial<ListingItem>): ListingItem => ({ ...BASE, ...over });
const rowsFor = (items: ListingItem[]): Cell[][] => toListingRows(items, recordingUi().ui);

describe('toListingRows renders the design\'s Listings table from the live payload', () => {
  it('reproduces the listing and figures cells the approved design shows for an in-review row', () => {
    const [row] = rowsFor([BASE]);
    expect(row[0]).toMatchObject({ hasMain: true, main: 'Mixed practice — Bastrop', hasSub: true, sub: 'Submitted September 1' });
    // A39: an in-review listing is not on the market, and the row says so — the design's own
    // words from its own Paused row, now on every status a buyer cannot find.
    expect(row[1]).toMatchObject({ hasMain: true, main: 'Dr. Susan Ortiz', hasSub: true, sub: '$860K asking · $1.20M revenue · 2 doctors · building leased · hidden from search' });
    expect(row[2]).toMatchObject({ pill: 'In review', pillStyle: PILL.warn });
  });

  it('shows "Untitled listing" for a row with no city yet, exactly as the seller dashboard does', () => {
    const [row] = rowsFor([item({ city: null })]);
    expect(row[0].main).toBe('Untitled listing');
  });

  it('never calls a listing of unknown type a "Small animal practice" (fix round 1, D-C53)', () => {
    // This was the one place left on the tab that FABRICATED a datum: a listing whose `type` is
    // null rendered "Small animal practice — Bastrop", a clinical category no seller had chosen
    // and no column held, on a screen whose whole ruling is "zero-fake data". The honest copy was
    // already in the same expression — the seller dashboard's own "Untitled listing", which is
    // what a row with nothing to name itself by has always read.
    const [row] = rowsFor([item({ type: null, price: null })]);
    expect(row[0].main).toBe('Untitled listing');
    expect(row[0].main).not.toContain('Small animal');
    // The absent price is still named as absent rather than omitted: a row with no asking price
    // is a real state of a real draft, and "Asking price not set" states it.
    expect(row[1].sub.startsWith('Asking price not set')).toBe(true);
  });

  it('...and still names the practice when the type IS set', () => {
    expect(rowsFor([item({ type: 'Mixed' })])[0][0].main).toBe('Mixed practice — Bastrop');
  });

  // -------------------------------------------------------------------------------------
  // D-C53, John's ruling of 2026-09-16: "the admin listings rows should name their practice".
  // Measured on QA 0.1.25 with the staff persona: `GET /api/admin/listings` served a practice
  // `name` on 30 of its 32 rows and the tab rendered it on NONE — every row was labelled by type
  // and city, and that label was shared by more than one row six times over (seven rows all read
  // "Small animal practice — Dallas"). A reviewer about to press Unpublish was telling them apart
  // by asking price and date. The name was already on the wire: `list_all` builds every item from
  // `serialise_draft`, the OWNER's own truth, and `ListingItem.name` has carried it since SL8.
  //
  // The composed label is NOT discarded — type and city are how a reviewer SCANS, the name is how
  // they IDENTIFY — so it moves onto the status line beneath the title in the design's own ` · `
  // idiom, the join the figures cell beside it already uses.
  // -------------------------------------------------------------------------------------
  it('names the practice the row is about, where the queue serves a name', () => {
    expect(rowsFor([item({ name: 'Round Rock Animal Hospital' })])[0][0].main).toBe('Round Rock Animal Hospital');
  });

  it('keeps the type and city a reviewer scans by, on the status line beneath the name', () => {
    expect(rowsFor([item({ name: 'Round Rock Animal Hospital' })])[0][0])
      .toMatchObject({ hasSub: true, sub: 'Mixed practice — Bastrop · Submitted September 1' });
  });

  it('joins nothing it does not have: a named row with no label, and a named row with no date', () => {
    // The `metaSource` rule, one surface over: a composer with one half missing writes the half it
    // has, never a dangling ` · `. A named draft that has not reached a city yet has no label to
    // scan by, and an undated row has no status line — each leaves the other standing alone.
    expect(rowsFor([item({ name: 'Round Rock Animal Hospital', city: null })])[0][0])
      .toMatchObject({ main: 'Round Rock Animal Hospital', hasSub: true, sub: 'Submitted September 1' });
    expect(rowsFor([item({ name: 'Round Rock Animal Hospital', submitted_at: null })])[0][0])
      .toMatchObject({ main: 'Round Rock Animal Hospital', hasSub: true, sub: 'Mixed practice — Bastrop' });
  });

  it('leaves an UNNAMED row exactly as it stood — the composed label, and the status line alone', () => {
    // The ruling's own floor: two of the thirty-two rows on QA are in this state and nothing about
    // them may regress. `BASE` carries no name, so every case in this file outside this block is
    // already a pin on that arm; these two say it in one place.
    expect(rowsFor([item({ name: null })])[0][0])
      .toMatchObject({ main: 'Mixed practice — Bastrop', hasSub: true, sub: 'Submitted September 1' });
    expect(rowsFor([item({ name: null, city: null })])[0][0])
      .toMatchObject({ main: 'Untitled listing', hasSub: true, sub: 'Submitted September 1' });
  });

  it('omits a figure the listing does not have, rather than inventing one', () => {
    const [row] = rowsFor([item({ rev: null, docs: null, bldg: null, status: 'published' })]);
    expect(row[1].sub).toBe('$860K asking');
  });

  it('says "doctor" singular for exactly one, not the design\'s own plural default', () => {
    const [row] = rowsFor([item({ docs: 1 })]);
    expect(row[1].sub).toContain('1 doctor ·');
    expect(row[1].sub).not.toContain('1 doctors');
  });

  it('falls back to the bldg column\'s own lowercased word when it is not one of the wizard\'s three', () => {
    // `Separate`, the CHECK constraint's own spelling (`migrations/016_listing.sql`) — never the
    // wizard's `BLDG_OUT` translation `Available separately` — is what a row would carry if the
    // translation were ever skipped; BLDG_SUB has no entry for it, so this is the `??` fallback.
    const [row] = rowsFor([item({ bldg: 'Separate' })]);
    expect(row[1].sub).toContain('separate');
  });

  it('leaves the "Listing" sub-line empty for a row with no submission date', () => {
    const [row] = rowsFor([item({ submitted_at: null })]);
    expect(row[0]).toMatchObject({ hasSub: false, sub: '' });
  });

  it('names no seller for an unowned seed row, absent rather than invented (D24)', () => {
    const [row] = rowsFor([item({ seller_name: null })]);
    expect(row[1]).toMatchObject({ hasMain: false, main: '' });
  });

  // A-SL24 (4): the design's row shape, an array of cell arrays wrapped by `adminVals()`'s own
  // `set.rows.map`, which loses `style` and re-flows the table at `maxDiffPixels: 0` if anything
  // else came back (`admin/users.test.ts`'s own Important-3 pin, applied here).
  it('returns the design\'s own row shape — four cells per row, no wrapper', () => {
    const rows = rowsFor([BASE, item({ id: 'l2', status: 'published' })]);
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(Array.isArray(row)).toBe(true);
      expect(row).toHaveLength(DESIGN[0].length);
      expect(Object.keys(row[0])).toEqual(Object.keys(DESIGN[0][0]));
    }
  });

  // The frozen `admin-listings` capture's own proof (A-SL24 (1), the `seller-dash` precedent):
  // `frontend/tests/design-admin-listings.mjs` derives its `DesignListingRow` fixtures off this
  // very `adminVals()` output — ALL FIVE, "Flagged" included, because the fixture carries a row's
  // own `pill`/`pillStyle` and action styles verbatim rather than deriving them from `PILLS`/
  // `ACTIONS` (A-SL24 (4)'s limit is on the LIVE mapping keyed by real `listing.status`, which
  // truly has no "flagged" value to key on — not on this oracle-only passthrough) — and this is
  // the pin that the round trip back through `toListingRows` reproduces it byte for byte, the same
  // success path the app renders through. `go` is compared by BEHAVIOUR, not by identity — two
  // closures never `===`, and the design's own is a prototype no-op while this module's decides
  // for real (the module note explains why).
  it('reproduces the design\'s own five rows exactly, from the harness fixture', () => {
    const stable = (rows: Cell[][]) => rows.map((row) => row.map(
      (c) => ({ ...c, actions: c.actions.map(({ label, style }) => ({ label, style })) })
    ));
    expect(stable(toListingRows(designAdminListingRows(), recordingUi().ui))).toEqual(stable(DESIGN));
  });

  it('a design row\'s own action "go" behaves exactly like the design\'s prototype no-op it stands in for', async () => {
    const { ui, calls } = recordingUi();
    const rows = toListingRows(designAdminListingRows(), ui);
    await expect(rows[0][3].actions[0].go()).resolves.toBeUndefined();
    // ...and it never reaches the ui at all — a design row's own action is inert, exactly as the
    // prototype's is, never `decision()`'s wired closure.
    expect(calls).toEqual([]);
  });
});

describe('the pill and the decision buttons, per listing status', () => {
  const pillOf = (status: string) => rowsFor([item({ status })])[0][2];
  const buttonsOf = (status: string) => rowsFor([item({ status })])[0][3];

  it('carries the design\'s tones for the three statuses it pictures', () => {
    expect(pillOf('in_review')).toMatchObject({ pill: 'In review', pillStyle: PILL.warn });
    expect(pillOf('published')).toMatchObject({ pill: 'Published', pillStyle: PILL.ok });
    expect(pillOf('paused')).toMatchObject({ pill: 'Paused', pillStyle: PILL.info });
  });

  it('names draft, withdrawn and declined in the mute tone, never their raw key (A39, ruling 5)', () => {
    // Until this task these three rendered the COLUMN's own value — "in_review" would have, too,
    // had the design not pictured it — so a reviewer read `withdrawn` where every other row read
    // English. The words are John's ruling; the "mute" tone comes from this module's own `cell()`,
    // not a hand-transcribed hex string, and it is the tone the design itself gives an inactive
    // pill (`cell()`'s own default).
    const mute = cell(null, null, null, 'no-such-tone').pillStyle;
    for (const [status, label] of [['draft', 'Draft'], ['withdrawn', 'Withdrawn'], ['declined', 'Declined']]) {
      expect(pillOf(status)).toMatchObject({ pill: label, pillStyle: mute });
    }
  });

  it('a status this table does not know renders muted rather than blank — the `??` that is left', () => {
    // No `listing.status` value reaches this any more (the case below pins that all six are
    // named), and it is not inert: `STATUSES` mirrors the column's own CHECK, so a seventh value
    // added there and not here would otherwise render `undefined`. "flagged" is the design's own
    // fifth fixture row, which is exactly such a status — pictured, backed by no column, and
    // unreachable from real data (A-SL24 (4)).
    const mute = cell(null, null, null, 'no-such-tone').pillStyle;
    expect(pillOf('flagged')).toMatchObject({ pill: 'flagged', pillStyle: mute });
    expect(buttonsOf('flagged')).toMatchObject({ hasActions: false, actions: [] });
  });

  it('has a pill for every status `listing.status` can hold, so no raw key can reach the table', () => {
    // The `??` fallback in `toListingRows` still stands — a status added to the column and not to
    // this table renders muted rather than blank — but no value the API can report reaches it now.
    // `tests/test_docs.py::test_the_admin_listings_table_matches_the_api` pins the other direction.
    expect(Object.keys(PILLS).sort()).toEqual(['declined', 'draft', 'in_review', 'paused', 'published', 'withdrawn']);
  });

  it('offers the decisions the API really allows, and Publish on the two rows a reversal is legal from', () => {
    // Ruling 3 (D-C53): `DECISIONS['publish']` has always allowed `declined` and `paused`, and the
    // tab's own footnote promises unpublishing is "immediate and reversible" — so the design's own
    // primary Publish button appears there. Ruling 4: "Edit" and "Contact seller" are GONE
    // (superseding A-SL33 (3)) — no route, no status transition, no audit row, so under D-C53 they
    // are not buttons. Every style below is the DESIGN's own, read off `adminVals()`.
    expect(buttonsOf('in_review').actions.map((a) => [a.label, a.style])).toEqual([['Publish', BTN.primary], ['Reject', BTN.danger]]);
    expect(buttonsOf('published').actions.map((a) => [a.label, a.style])).toEqual([['Unpublish', BTN.plain]]);
    expect(buttonsOf('paused').actions.map((a) => [a.label, a.style])).toEqual([['Publish', BTN.primary]]);
    expect(buttonsOf('declined').actions.map((a) => [a.label, a.style])).toEqual([['Publish', BTN.primary]]);
  });

  it('offers nothing on the two statuses no decision can move (draft, withdrawn)', () => {
    for (const status of ['draft', 'withdrawn']) {
      expect(buttonsOf(status)).toMatchObject({ hasActions: false, actions: [] });
    }
  });

  it('no button on the tab is a no-op: every one of them carries a decision (ruling 4, D-C53)', () => {
    // A-SL33 (3) kept "Edit" and "Contact seller" as the design's own inert buttons; D-C53
    // supersedes it — "a button that does nothing is removed by amendment". This is the pin that
    // says so in terms nothing can quietly re-add: every label the live table offers, on every
    // status, is one of the three the API decides.
    const decided = new Set(['Publish', 'Reject', 'Unpublish']);
    for (const status of ['draft', 'in_review', 'published', 'paused', 'withdrawn', 'declined']) {
      for (const a of buttonsOf(status).actions) expect(decided, `${status}: ${a.label}`).toContain(a.label);
    }
  });

  // A-SL33 (3)'s own point, kept and re-aimed: a hand-typed style string can silently go stale.
  // The live table's every button and every pill is COMPOSED from the design's own elements
  // (John's 2026-09-13 decision, the A8 precedent), so each style is compared against the one
  // `adminVals()` itself computes — the Publish button paused and declined rows now carry is the
  // design's own In-review Publish, byte for byte, and not a new control.
  it('every live button and pill wears a style the design itself computes', () => {
    const designStyles = new Set(DESIGN.flatMap((row) => row[3].actions.map((a) => a.style)));
    const designPills = new Set(DESIGN.map((row) => row[2].pillStyle));
    for (const status of ['draft', 'in_review', 'published', 'paused', 'withdrawn', 'declined']) {
      for (const a of buttonsOf(status).actions) expect(designStyles, `${status}: ${a.label}`).toContain(a.style);
      if (PILLS[status][1] !== 'mute') expect(designPills, status).toContain(pillOf(status).pillStyle);
    }
  });

  it('covers the four statuses a decision is legal from, and no fifth', () => {
    expect(Object.keys(ACTIONS)).toEqual(['in_review', 'published', 'paused', 'declined']);
  });
});

// ---------------------------------------------------------------------------------------
// A39, ruling 5 (D-C53): the sub-lines. Until this task every row read "Submitted <date>" — the
// only date the payload carried — so a listing published in March and a listing paused yesterday
// both reported the day their seller pressed Submit, and the design's own "Published August 24",
// "Paused by seller August 12" and "hidden from search" had no producer at all.
// ---------------------------------------------------------------------------------------
describe('the sub-line each status carries, from the dates the queue now serves', () => {
  const subOf = (over: Partial<ListingItem>) => rowsFor([item(over)])[0][0];
  const figuresOf = (over: Partial<ListingItem>) => rowsFor([item(over)])[0][1].sub;

  it('dates a published row by `listed_at`, the day it reached the market', () => {
    // NOT `submitted_at`, and not `updated_at`: `listed_at` is stamped at the FIRST publish and
    // never again (`admin_listings.decide_listing`), which is the date a buyer has seen.
    expect(subOf({ status: 'published' }).sub).toBe('Published August 24');
  });

  it('names the seller when the seller paused it, and the reviewer when a reviewer unpublished it', () => {
    // Two doors reach `paused` — the seller's own `POST /api/seller/listings/{id}/status` and the
    // reviewer's `unpublish` — and the audit row's `actor_role` is the only thing in the payload
    // that tells them apart (ruling 5).
    expect(subOf({ status: 'paused', status_changed_by: 'buyer,seller' }).sub).toBe('Paused by seller August 12');
    expect(subOf({ status: 'paused', status_changed_by: 'seller' }).sub).toBe('Paused by seller August 12');
    expect(subOf({ status: 'paused', status_changed_by: 'staff' }).sub).toBe('Unpublished by reviewer August 12');
    expect(subOf({ status: 'paused', status_changed_by: 'admin,buyer' }).sub).toBe('Unpublished by reviewer August 12');
    // `app/auth/audit.py` prefixes a CI token's roles with `token:` and writes `legacy:operator`
    // for the operator secret, which holds no account at all; neither is the seller.
    expect(subOf({ status: 'paused', status_changed_by: 'token:staff' }).sub).toBe('Unpublished by reviewer August 12');
    expect(subOf({ status: 'paused', status_changed_by: 'legacy:operator' }).sub).toBe('Unpublished by reviewer August 12');
    expect(subOf({ status: 'paused', status_changed_by: null }).sub).toBe('Unpublished by reviewer August 12');
  });

  it('reads an account holding BOTH roles as the reviewer — the one case the role list cannot settle', () => {
    // Recorded rather than hidden: `actor_role` is a role LIST, and an account that is both a
    // seller and a reviewer (John's own all-roles persona is) pausing its OWN listing is written
    // exactly as a reviewer unpublishing somebody else's. The unambiguous discriminator is the
    // audit ACTION, which names the route; ruling 5 names `actor_role`, so this is what it says.
    expect(subOf({ status: 'paused', status_changed_by: 'admin,buyer,seller,staff' }).sub).toBe('Unpublished by reviewer August 12');
  });

  it('says nothing where there is no date to say it with, rather than a guess', () => {
    expect(subOf({ status: 'published', listed_at: null })).toMatchObject({ hasSub: false, sub: '' });
    expect(subOf({ status: 'paused', status_changed_at: null })).toMatchObject({ hasSub: false, sub: '' });
  });

  it('gives a declined row the reviewer\'s own reason, which is the one thing its seller needs', () => {
    expect(subOf({ status: 'declined', decline_reason: 'The revenue figures do not match the returns.' }).sub)
      .toBe('The revenue figures do not match the returns.');
  });

  it('...and falls back to the submission line where no reason was ever recorded', () => {
    expect(subOf({ status: 'declined' }).sub).toBe('Submitted September 1');
  });

  it('leaves every other status on the submission line it already had', () => {
    for (const status of ['draft', 'in_review', 'withdrawn']) expect(subOf({ status }).sub, status).toBe('Submitted September 1');
  });

  it('says "hidden from search" on every status a buyer cannot find, and on none they can', () => {
    // The design's own words, from its own Paused row — and true of all five: `GET /api/listings`
    // serves `status = 'published'` alone. The footnote above the table has always said it; the
    // rows said it on one status out of five.
    for (const status of ['draft', 'in_review', 'paused', 'withdrawn', 'declined']) {
      expect(figuresOf({ status }).endsWith(' · hidden from search'), status).toBe(true);
    }
    expect(figuresOf({ status: 'published' })).not.toContain('hidden from search');
  });
});

describe('a decision is a note, sometimes the first-publish fields, then the post', () => {
  const press = async (over: Partial<ListingItem>, label: string, note: string | null = 'a reviewer note', fields: { state: string; market: string } | null = { state: 'TX', market: 'Austin, TX' }) => {
    const { ui, calls } = recordingUi(note, fields);
    const row = toListingRows([item(over)], ui)[0];
    await row[3].actions.find((a) => a.label === label)!.go();
    return calls;
  };

  it('requires a reason for Reject, the one action `NOTE_REQUIRED` names', async () => {
    expect(NOTE_REQUIRED).toEqual(['decline']);
    expect(await press({ status: 'in_review' }, 'Reject')).toEqual(['needsNote:decline', 'decide:l1:decline:a reviewer note:null']);
  });

  it('sends nothing when the reviewer cancels the reason prompt, or leaves it blank', async () => {
    expect(await press({ status: 'in_review' }, 'Reject', null)).toEqual(['needsNote:decline']);
    expect(await press({ status: 'in_review' }, 'Reject', '   ')).toEqual(['needsNote:decline']);
  });

  it('asks for neither prompt for an action that is not publish', async () => {
    expect(await press({ status: 'published' }, 'Unpublish')).toEqual(['decide:l1:unpublish::null']);
  });

  it('asks for state and market ONLY on a first publish (state is still null)', async () => {
    expect(await press({ status: 'in_review', state: null }, 'Publish')).toEqual(['needsFields:publish', 'decide:l1:publish::TX/Austin, TX']);
  });

  it('asks for neither on a republish — the listing already has a state', async () => {
    expect(await press({ status: 'in_review', state: 'TX' }, 'Publish')).toEqual(['decide:l1:publish::null']);
  });

  it('sends nothing when the reviewer cancels either field prompt', async () => {
    expect(await press({ status: 'in_review', state: null }, 'Publish', 'ignored', null)).toEqual(['needsFields:publish']);
  });
});

describe('makeAdminListingsAdapter, against the real fetch boundary', () => {
  interface Call { url: string; init: { method: string; credentials: string; headers: Record<string, string>; body?: string } }

  function stubFetch(...answers: Array<{ status: number; body?: unknown }>): Call[] {
    const calls: Call[] = [];
    let n = 0;
    vi.stubGlobal('fetch', (url: string, init: Call['init']) => {
      calls.push({ url, init });
      const a = answers[Math.min(n++, answers.length - 1)];
      return Promise.resolve({ ok: a.status >= 200 && a.status < 300, status: a.status, json: () => Promise.resolve(a.body) });
    });
    return calls;
  }

  beforeEach(() => {
    document.cookie = 'pm_csrf=tok123';
  });
  afterEach(() => vi.unstubAllGlobals());

  it('lists one page, mapped through toListingRows, with the double-submit token on the decide alone', async () => {
    const calls = stubFetch({ status: 200, body: { counts: { in_review: 1 }, items: [BASE], next_cursor: null } });
    const rows = await listRows();
    expect(rows).toHaveLength(1);
    expect(rows[0][0].main).toBe('Mixed practice — Bastrop');
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('/api/admin/listings?limit=200');
    expect(calls[0].init.headers['X-CSRF-Token']).toBeUndefined();
  });

  it('follows next_cursor to the end, the way the seller dashboard\'s own list() does', async () => {
    // The second page carries NO `counts`, which is the envelope `list_all` really answers a
    // continuation request with (fix round 1, M-1): the badge is a fact about the table, an
    // unindexed `count(*)` to compute, and the route stops paying for it once a `cursor` is given.
    const calls = stubFetch(
      { status: 200, body: { counts: { in_review: 1 }, items: [item({ id: 'l1' })], next_cursor: '2026-09-01T00:00:00Z|l1' } },
      { status: 200, body: { items: [item({ id: 'l2' })], next_cursor: null } }
    );
    const { rows, counts } = await makeAdminListingsAdapter().list();
    expect(rows).toHaveLength(2);
    expect(calls[1].url).toContain('cursor=2026-09-01T00%3A00%3A00Z%7Cl1');
    expect(counts, 'a continuation page without counts is not an error').toEqual({ in_review: 1 });
  });

  it('takes the badge off the FIRST page and lets no later page move it (fix round 2, Minor 1)', async () => {
    // Both halves of M-1's client rule, which nothing held before this case. A regression in
    // either direction is invisible at 100 % coverage: demanding `counts` on every page throws
    // "the review queue answered no counts" on page 2, and A39.2's rejection arm then empties the
    // table and blanks the badge for every reviewer; letting a later page WRITE the badge would
    // show a number the route no longer sends and nobody measured.
    stubFetch(
      { status: 200, body: { counts: { in_review: 1 }, items: [item({ id: 'l1' })], next_cursor: '2026-09-01T00:00:00Z|l1' } },
      { status: 200, body: { counts: { in_review: 99 }, items: [item({ id: 'l2' })], next_cursor: null } }
    );
    const { rows, counts } = await makeAdminListingsAdapter().list();
    expect(rows).toHaveLength(2);
    expect(counts, 'page 1 answered the badge; page 2 cannot move it').toEqual({ in_review: 1 });
  });

  it('...and a FIRST page with no counts is still refused', async () => {
    // The rule is "the first page alone", not "whichever page happens to carry one": a queue that
    // answers no badge at all is the case `items`' own guard exists for.
    stubFetch({ status: 200, body: { items: [item({ id: 'l1' })], next_cursor: null } });
    await expect(makeAdminListingsAdapter().list()).rejects.toThrow('no counts');
  });

  it('rejects when the queue cannot be read, or answers no items', async () => {
    stubFetch({ status: 503 });
    await expect(makeAdminListingsAdapter().list()).rejects.toThrow('could not be read');
    stubFetch({ status: 200, body: { next_cursor: null } });
    await expect(makeAdminListingsAdapter().list()).rejects.toThrow('no items');
  });

  it('decides through the browser\'s own prompts, and posts the double-submit token', async () => {
    const calls = stubFetch(
      { status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'in_review', state: null })], next_cursor: null } },
      { status: 200, body: {} }
    );
    vi.stubGlobal('prompt', vi.fn().mockReturnValueOnce('TX').mockReturnValueOnce('Austin, TX'));
    const rows = await listRows();
    await rows[0][3].actions.find((a) => a.label === 'Publish')!.go();
    expect(calls[1].url).toBe('/api/admin/listings/l1/decide');
    expect(calls[1].init.headers['X-CSRF-Token']).toBe('tok123');
    expect(JSON.parse(calls[1].init.body!)).toEqual({ action: 'publish', reason: '', state: 'TX', market: 'Austin, TX' });
  });

  it('alerts the reviewer, rather than failing silently, when the decide is refused', async () => {
    stubFetch(
      { status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'published' })], next_cursor: null } },
      { status: 409, body: { error: { code: 'STATE', message: 'cannot unpublish a listing in state paused' } } }
    );
    const alertSpy = vi.fn();
    vi.stubGlobal('alert', alertSpy);
    const rows = await listRows();
    await rows[0][3].actions.find((a) => a.label === 'Unpublish')!.go();
    expect(alertSpy).toHaveBeenCalledWith('cannot unpublish a listing in state paused');
  });

  it('alerts the reviewer with the design\'s own generic wording when the refusal carries no message', async () => {
    // The `??` fallback: a decide refusal whose body is not the A5 envelope shape at all (a proxy
    // error page, say) rather than one that names the field or the reason.
    stubFetch(
      { status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'published' })], next_cursor: null } },
      { status: 502, body: {} }
    );
    const alertSpy = vi.fn();
    vi.stubGlobal('alert', alertSpy);
    const rows = await listRows();
    await rows[0][3].actions.find((a) => a.label === 'Unpublish')!.go();
    expect(alertSpy).toHaveBeenCalledWith('That listing could not be unpublished.');
  });

  it('asks for a decline reason through the browser\'s own prompt, and sends it', async () => {
    const calls = stubFetch(
      { status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'in_review' })], next_cursor: null } },
      { status: 200, body: {} }
    );
    const promptSpy = vi.fn().mockReturnValueOnce('affiliation could not be verified');
    vi.stubGlobal('prompt', promptSpy);
    const rows = await listRows();
    await rows[0][3].actions.find((a) => a.label === 'Reject')!.go();
    expect(promptSpy).toHaveBeenCalledWith('Why is this listing being rejected?');
    expect(JSON.parse(calls[1].init.body!)).toMatchObject({ action: 'decline', reason: 'affiliation could not be verified' });
  });

  it('sends nothing when the reviewer cancels the state prompt on a first publish', async () => {
    const calls = stubFetch({ status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'in_review', state: null })], next_cursor: null } });
    vi.stubGlobal('prompt', vi.fn().mockReturnValueOnce(null));
    const rows = await listRows();
    await rows[0][3].actions.find((a) => a.label === 'Publish')!.go();
    expect(calls).toHaveLength(1);   // the list GET alone — no decide POST followed the cancel
  });

  it('sends nothing when the reviewer answers the state prompt but cancels the market one', async () => {
    const calls = stubFetch({ status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'in_review', state: null })], next_cursor: null } });
    vi.stubGlobal('prompt', vi.fn().mockReturnValueOnce('TX').mockReturnValueOnce(null));
    const rows = await listRows();
    await rows[0][3].actions.find((a) => a.label === 'Publish')!.go();
    expect(calls).toHaveLength(1);
  });

  // ---------------------------------------------------------------------------------------
  // A39, rulings 1 and 2: the badge is the API's, and the table refreshes when a decision lands.
  // ---------------------------------------------------------------------------------------

  it('hands the tab its badge from the envelope, never a literal (ruling 1)', async () => {
    stubFetch({ status: 200, body: { counts: { in_review: 7, total: 41 }, items: [BASE], next_cursor: null } });
    expect((await makeAdminListingsAdapter().list()).counts).toEqual({ in_review: 7 });
  });

  it('refuses a queue that answers no counts, exactly as it refuses one that answers no items', async () => {
    // The badge would otherwise read "0" or vanish, and a reviewer cannot tell either from "no
    // listings are waiting" — the same reason `items` is checked rather than defaulted.
    stubFetch({ status: 200, body: { items: [], next_cursor: null } });
    await expect(makeAdminListingsAdapter().list()).rejects.toThrow('no counts');
    stubFetch({ status: 200, body: { counts: { in_review: 'three' }, items: [], next_cursor: null } });
    await expect(makeAdminListingsAdapter().list()).rejects.toThrow('no counts');
  });

  it('tells the host to re-read the queue once a decision lands, so the row changes without a reload', async () => {
    // Ruling 2. Before this the POST returned the updated draft and the adapter DISCARDED it: the
    // pill, the buttons and the badge all stood until the reviewer reloaded the page, which is
    // what made a reviewer press Publish twice. The adapter does not set state itself — it says a
    // decision landed, and the ADMIN-GATE seam (`loadAdmin`, A40.3) re-lists through this very
    // adapter, so the rows and the counts settle by the one path that ever writes them.
    const calls = stubFetch(
      { status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'published' })], next_cursor: null } },
      { status: 200, body: {} }
    );
    const adapter = makeAdminListingsAdapter();
    const reloads: number[] = [];
    adapter.onDecision(() => { reloads.push(calls.length); });
    const rows = (await adapter.list()).rows;
    await rows[0][3].actions.find((a) => a.label === 'Unpublish')!.go();
    expect(reloads, 'the reload is asked for exactly once, after the POST').toEqual([2]);
  });

  it('RE-READS after a 409 STATE — the one refusal that means the row on screen is wrong (I-2)', async () => {
    // Fix round 1, Important-2. `409 STATE` (`admin_listings.py`'s own code) is returned precisely
    // when the listing is no longer in the state this row was drawn from — another reviewer moved
    // it. The DECISION did not land, and that is what the earlier "nothing moved, so there is
    // nothing to re-read" note was about; but the TABLE is stale, so the pill kept reading
    // "In review" and the Publish button kept being offered, which is the pre-A39 condition
    // reached by a second door. The alert still fires, and the row it contradicts is corrected.
    stubFetch(
      { status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'published' })], next_cursor: null } },
      { status: 409, body: { error: { code: 'STATE', message: 'cannot unpublish a listing in state paused' } } }
    );
    const alertSpy = vi.fn();
    vi.stubGlobal('alert', alertSpy);
    const adapter = makeAdminListingsAdapter();
    let reloaded = 0;
    adapter.onDecision(() => { reloaded += 1; });
    const rows = (await adapter.list()).rows;
    await rows[0][3].actions.find((a) => a.label === 'Unpublish')!.go();
    expect(alertSpy, 'the reviewer is still told why').toHaveBeenCalledWith('cannot unpublish a listing in state paused');
    expect(reloaded, 'and the row the alert contradicts is re-read through the one loader').toBe(1);
  });

  it('does not ask for a reload for a refusal that moved nothing — a 422, or a body with no code', async () => {
    // Keyed on the SERVER's own code, never on "any refusal": a `422 NOTE_REQUIRED` means the
    // reviewer left the reason blank, the listing is exactly where the row says it is, and
    // re-reading the whole queue would spend a request to learn nothing.
    for (const answer of [
      { status: 422, body: { error: { code: 'NOTE_REQUIRED', message: 'a reason is required.' } } },
      { status: 502, body: {} }
    ]) {
      stubFetch({ status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'published' })], next_cursor: null } }, answer);
      vi.stubGlobal('alert', vi.fn());
      const adapter = makeAdminListingsAdapter();
      let reloaded = false;
      adapter.onDecision(() => { reloaded = true; });
      const rows = (await adapter.list()).rows;
      await rows[0][3].actions.find((a) => a.label === 'Unpublish')!.go();
      expect(reloaded, `${answer.status}: nothing moved, so there is nothing to re-read`).toBe(false);
    }
  });

  it('tells the reviewer when the decide never reached the server at all (fix round 2)', async () => {
    // Recorded by the re-review as a PRE-EXISTING gap, older than A39 and unchanged by fix round
    // 1: the button binding is `go: () => Promise<void>` and the design's own template does not
    // await it, so a REJECTED promise — `fetch` throwing on an offline browser or a DNS failure,
    // never an HTTP status — became an unhandled rejection and the reviewer saw NOTHING happen.
    // A refusal the server SENT already alerts; a request that never arrived must say so through
    // the same door, in the same words the `??` fallback uses for a bodyless refusal.
    stubFetch({ status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'published' })], next_cursor: null } });
    const alertSpy = vi.fn();
    vi.stubGlobal('alert', alertSpy);
    const rows = await listRows();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await expect(rows[0][3].actions.find((a) => a.label === 'Unpublish')!.go()).resolves.toBeUndefined();
    expect(alertSpy).toHaveBeenCalledWith('That listing could not be unpublished.');
  });

  it('...and a rejected REJECT says "rejected", the same root verb the refusal wording uses', async () => {
    // The other arm of the catch's own ternary, reached only when a DECLINE is the decide that
    // never arrives — the `unpublish` case above cannot exercise it, and a wrong verb here would
    // read "declineed" to the one reviewer who meets it.
    stubFetch({ status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'in_review' })], next_cursor: null } });
    const alertSpy = vi.fn();
    vi.stubGlobal('alert', alertSpy);
    vi.stubGlobal('prompt', vi.fn().mockReturnValueOnce('affiliation could not be verified'));
    const rows = await listRows();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await rows[0][3].actions.find((a) => a.label === 'Reject')!.go();
    expect(alertSpy).toHaveBeenCalledWith('That listing could not be rejected.');
  });

  it('...and a rejected decide asks for no reload, because nothing moved', async () => {
    stubFetch({ status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'published' })], next_cursor: null } });
    vi.stubGlobal('alert', vi.fn());
    const adapter = makeAdminListingsAdapter();
    let reloaded = false;
    adapter.onDecision(() => { reloaded = true; });
    const rows = (await adapter.list()).rows;
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await rows[0][3].actions.find((a) => a.label === 'Unpublish')!.go();
    expect(reloaded).toBe(false);
  });

  it('decides perfectly well for a host that registered nothing — the reference and the unit tests', async () => {
    const calls = stubFetch(
      { status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'published' })], next_cursor: null } },
      { status: 200, body: {} }
    );
    const rows = await listRows();
    await expect(rows[0][3].actions.find((a) => a.label === 'Unpublish')!.go()).resolves.toBeUndefined();
    expect(calls, 'and spends no request re-reading a queue nobody is rendering').toHaveLength(2);
  });

  it('alerts with the decline-specific wording when a decline itself is refused', async () => {
    // The other side of the same `${action === 'decline' ? 'rejected' : action}ed` ternary the
    // generic-wording test above exercises via 'unpublish' — reached only when the DECLINE decide
    // call itself is the one that fails, not merely requested.
    stubFetch(
      { status: 200, body: { counts: { in_review: 1 }, items: [item({ status: 'in_review' })], next_cursor: null } },
      { status: 502, body: {} }
    );
    vi.stubGlobal('prompt', vi.fn().mockReturnValueOnce('affiliation could not be verified'));
    const alertSpy = vi.fn();
    vi.stubGlobal('alert', alertSpy);
    const rows = await listRows();
    await rows[0][3].actions.find((a) => a.label === 'Reject')!.go();
    expect(alertSpy).toHaveBeenCalledWith('That listing could not be rejected.');
  });
});
