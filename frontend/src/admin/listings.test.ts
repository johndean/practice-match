// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Component } from '../logic.js';
import { designAdminListingRows } from '../../tests/design-admin-listings.mjs';
import {
  ACTIONS, NOTE_REQUIRED, PILLS,
  cell, makeAdminListingsAdapter, toListingRows,
  type Cell, type ListingItem, type ListingsUi
} from './listings';

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

const BASE: ListingItem = {
  id: 'l1', status: 'in_review', name: 'Mixed practice', type: 'Mixed', city: 'Bastrop',
  price: 860000, rev: 1200000, docs: 2, bldg: 'Leased', state: null, seller_name: 'Dr. Susan Ortiz',
  submitted_at: '2026-09-01T12:00:00Z'
};
const item = (over: Partial<ListingItem>): ListingItem => ({ ...BASE, ...over });
const rowsFor = (items: ListingItem[]): Cell[][] => toListingRows(items, recordingUi().ui);

describe('toListingRows renders the design\'s Listings table from the live payload', () => {
  it('reproduces the listing and figures cells the approved design shows for an in-review row', () => {
    const [row] = rowsFor([BASE]);
    expect(row[0]).toMatchObject({ hasMain: true, main: 'Mixed practice — Bastrop', hasSub: true, sub: 'Submitted September 1' });
    expect(row[1]).toMatchObject({ hasMain: true, main: 'Dr. Susan Ortiz', hasSub: true, sub: '$860K asking · $1.20M revenue · 2 doctors · building leased' });
    expect(row[2]).toMatchObject({ pill: 'In review', pillStyle: PILL.warn });
  });

  it('shows "Untitled listing" for a row with no city yet, exactly as the seller dashboard does', () => {
    const [row] = rowsFor([item({ city: null })]);
    expect(row[0].main).toBe('Untitled listing');
  });

  it('falls back to "Small animal" when the type is not yet set, and to "Asking price not set"', () => {
    const [row] = rowsFor([item({ type: null, price: null })]);
    expect(row[0].main).toBe('Small animal practice — Bastrop');
    expect(row[1].sub.startsWith('Asking price not set')).toBe(true);
  });

  it('omits a figure the listing does not have, rather than inventing one', () => {
    const [row] = rowsFor([item({ rev: null, docs: null, bldg: null })]);
    expect(row[1].sub).toBe('$860K asking');
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
});

describe('the pill and the decision buttons, per listing status', () => {
  const pillOf = (status: string) => rowsFor([item({ status })])[0][2];
  const buttonsOf = (status: string) => rowsFor([item({ status })])[0][3];

  it('carries the design\'s tones for the three statuses it pictures', () => {
    expect(pillOf('in_review')).toMatchObject({ pill: 'In review', pillStyle: PILL.warn });
    expect(pillOf('published')).toMatchObject({ pill: 'Published', pillStyle: PILL.ok });
    expect(pillOf('paused')).toMatchObject({ pill: 'Paused', pillStyle: PILL.info });
  });

  it('shows the status itself, muted, for a status the design never pictured here', () => {
    // `draft`, `withdrawn` and `declined` are real `listing.status` values with no ruled Admin
    // Listings pill (D24 (4)) — the state key stands rather than prose nobody approved, exactly
    // `admin/users.ts`'s own fallback for an unpictured account state. The "mute" tone comes from
    // this module's own `cell()`, not a hand-transcribed hex string.
    const mute = cell(null, null, null, 'no-such-tone').pillStyle;
    for (const status of ['draft', 'withdrawn', 'declined']) {
      expect(pillOf(status)).toMatchObject({ pill: status, pillStyle: mute });
    }
  });

  it('offers the buttons the approved design shows for in-review and published rows', () => {
    expect(buttonsOf('in_review').actions.map((a) => [a.label, a.style])).toEqual([['Publish', BTN.primary], ['Reject', BTN.danger]]);
    expect(buttonsOf('published').actions.map((a) => [a.label, a.style])).toEqual([['Unpublish', BTN.plain]]);
  });

  it('offers no button on a status the design never wired one for (paused, draft, withdrawn, declined)', () => {
    for (const status of ['paused', 'draft', 'withdrawn', 'declined']) {
      expect(buttonsOf(status)).toMatchObject({ hasActions: false, actions: [] });
    }
  });

  it('covers exactly the three statuses the design pictures, and no fourth', () => {
    expect(Object.keys(PILLS)).toEqual(['in_review', 'published', 'paused']);
    expect(Object.keys(ACTIONS)).toEqual(['in_review', 'published']);
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
    const calls = stubFetch({ status: 200, body: { items: [BASE], next_cursor: null } });
    const rows = await makeAdminListingsAdapter().list();
    expect(rows).toHaveLength(1);
    expect(rows[0][0].main).toBe('Mixed practice — Bastrop');
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('/api/admin/listings?limit=200');
    expect(calls[0].init.headers['X-CSRF-Token']).toBeUndefined();
  });

  it('follows next_cursor to the end, the way the seller dashboard\'s own list() does', async () => {
    const calls = stubFetch(
      { status: 200, body: { items: [item({ id: 'l1' })], next_cursor: '2026-09-01T00:00:00Z|l1' } },
      { status: 200, body: { items: [item({ id: 'l2' })], next_cursor: null } }
    );
    const rows = await makeAdminListingsAdapter().list();
    expect(rows).toHaveLength(2);
    expect(calls[1].url).toContain('cursor=2026-09-01T00%3A00%3A00Z%7Cl1');
  });

  it('rejects when the queue cannot be read, or answers no items', async () => {
    stubFetch({ status: 503 });
    await expect(makeAdminListingsAdapter().list()).rejects.toThrow('could not be read');
    stubFetch({ status: 200, body: { next_cursor: null } });
    await expect(makeAdminListingsAdapter().list()).rejects.toThrow('no items');
  });

  it('decides through the browser\'s own prompts, and posts the double-submit token', async () => {
    const calls = stubFetch(
      { status: 200, body: { items: [item({ status: 'in_review', state: null })], next_cursor: null } },
      { status: 200, body: {} }
    );
    vi.stubGlobal('prompt', vi.fn().mockReturnValueOnce('TX').mockReturnValueOnce('Austin, TX'));
    const rows = await makeAdminListingsAdapter().list();
    await rows[0][3].actions.find((a) => a.label === 'Publish')!.go();
    expect(calls[1].url).toBe('/api/admin/listings/l1/decide');
    expect(calls[1].init.headers['X-CSRF-Token']).toBe('tok123');
    expect(JSON.parse(calls[1].init.body!)).toEqual({ action: 'publish', reason: '', state: 'TX', market: 'Austin, TX' });
  });

  it('alerts the reviewer, rather than failing silently, when the decide is refused', async () => {
    stubFetch(
      { status: 200, body: { items: [item({ status: 'published' })], next_cursor: null } },
      { status: 409, body: { error: { code: 'STATE', message: 'cannot unpublish a listing in state paused' } } }
    );
    const alertSpy = vi.fn();
    vi.stubGlobal('alert', alertSpy);
    const rows = await makeAdminListingsAdapter().list();
    await rows[0][3].actions.find((a) => a.label === 'Unpublish')!.go();
    expect(alertSpy).toHaveBeenCalledWith('cannot unpublish a listing in state paused');
  });
});
