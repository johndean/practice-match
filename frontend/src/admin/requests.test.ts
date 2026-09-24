// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Component } from '../logic.js';
import {
  countsOf,
  LEVEL_LABEL,
  makeAdminRequestsAdapter,
  STATUS_PILL,
  toRequestRows,
  type AdminRequestCounts,
  type AdminRequestItem,
  type Cell,
  type DesignRequestRow
} from './requests';

// ---------------------------------------------------------------------------------------
// The design's OWN `adminVals()` output is the oracle for the pill/cell style strings, exactly
// as `users.test.ts` and `data_sources.test.ts` use it: "cell() is copied verbatim from
// logic.js" is machine-checked rather than transcribed, and a change on either side fails here.
// ---------------------------------------------------------------------------------------
const designCells = (tab: string): Cell[][] => {
  const c = new Component({});
  c.setState({ adminTab: tab });
  return c.adminVals().rows.map((r: { cells: Cell[] }) => r.cells);
};
const ACTIVITY = designCells('activity'); // the design's own four Requests rows

const PILL = {
  warn: ACTIVITY[0][2].pillStyle,  // "Awaiting seller"
  ok: ACTIVITY[1][2].pillStyle,    // "Engaged"
  bad: ACTIVITY[2][2].pillStyle    // "Declined"
};

const ITEM: AdminRequestItem = {
  id: 'req-1',
  status: 'PENDING',
  requested_disclosure_level: 'FULL_CONFIDENTIAL',
  approved_capabilities: null,
  requested_at: '2026-09-10T12:00:00+00:00',
  reviewed_at: null,
  listing_id: 'listing-1',
  listing_name: 'Cedar Park Animal Hospital',
  listing_type: 'Small animal',
  listing_city: 'Cedar Park',
  buyer_user_id: 'buyer-1',
  buyer_name: 'Dr. Rachel Mendes',
  seller_user_id: 'seller-1',
  seller_name: 'Dr. James Whitfield'
};
const item = (over: Partial<AdminRequestItem>): AdminRequestItem => ({ ...ITEM, ...over });
const rows = (items: (AdminRequestItem | DesignRequestRow)[]): Cell[][] => toRequestRows(items);

afterEach(() => vi.restoreAllMocks());

describe('toRequestRows renders the design\'s Requests table from the admin queue payload', () => {
  it('names the buyer in the Request column, with the requested level as its sub-line', () => {
    const [row] = rows([ITEM]);
    expect(row[0].main).toBe('Dr. Rachel Mendes');
    expect(row[0].sub).toBe('Requested: Full confidential');
  });

  it('names the practice and the seller in the Practice column', () => {
    const [row] = rows([ITEM]);
    expect(row[1].main).toBe('Cedar Park Animal Hospital');
    expect(row[1].sub).toBe('Dr. James Whitfield');
  });

  it('falls back to type + city when the listing has no name — admin/listings.ts\'s own idiom', () => {
    const [row] = rows([item({ listing_name: null })]);
    expect(row[1].main).toBe('Small animal practice — Cedar Park');
  });

  it('falls back to "Untitled listing" when neither a name nor a type/city pair exists', () => {
    const [row] = rows([item({ listing_name: null, listing_type: null })]);
    expect(row[1].main).toBe('Untitled listing');
  });

  it('shows a PENDING request as "Awaiting seller", the design\'s own warn tone', () => {
    const [row] = rows([item({ status: 'PENDING' })]);
    expect(row[2].pill).toBe('Awaiting seller');
    expect(row[2].pillStyle).toBe(PILL.warn);
  });

  it('shows an APPROVED request as "Engaged", the design\'s own ok tone, and names the APPROVED level', () => {
    const [row] = rows([item({ status: 'APPROVED', approved_capabilities: ['FINANCIALS'] })]);
    expect(row[2].pill).toBe('Engaged');
    expect(row[2].pillStyle).toBe(PILL.ok);
    expect(row[0].sub).toBe('Approved: Financials');
  });

  // D-C67 (John, 2026-09-24): a grant is a SET, so this cell names however many the seller
  // released — in this tab's own Title-case register and in the product's own declared order,
  // never the order the array happened to arrive in.
  it('names every capability an APPROVED request released, in the declared order', () => {
    const [row] = rows([item({ status: 'APPROVED', approved_capabilities: ['FLOOR_PLANS', 'IDENTITY'] })]);
    expect(row[0].sub).toBe('Approved: Identity, Floor plans');
  });

  it('says so, rather than falling back to what the buyer asked for, when an approval released nothing', () => {
    // `[]` is a real decision and `!= null` is what tells it from "no decision yet" — a truthiness
    // test here would print "Requested: Full confidential" over a grant that released nothing,
    // which is the reading D-C67 exists to remove one surface over.
    const [row] = rows([item({ status: 'APPROVED', approved_capabilities: [] })]);
    expect(row[0].sub).toBe('Approved: nothing released');
  });

  it('shows a DENIED request as "Declined", the design\'s own bad tone', () => {
    const [row] = rows([item({ status: 'DENIED' })]);
    expect(row[2].pill).toBe('Declined');
    expect(row[2].pillStyle).toBe(PILL.bad);
  });

  it('shows a REVOKED request as its own word, "Revoked"', () => {
    const [row] = rows([item({ status: 'REVOKED' })]);
    expect(row[2].pill).toBe('Revoked');
  });

  it('reports the age as days since the request, with no fabricated narrative sub-line', () => {
    vi.setSystemTime(new Date('2026-09-16T12:00:00Z'));
    const [row] = rows([item({ requested_at: '2026-09-10T12:00:00Z' })]);
    expect(row[3].main).toBe('6 days');
    expect(row[3].hasSub).toBe(false);
  });

  it('keeps the age singular at exactly one day', () => {
    vi.setSystemTime(new Date('2026-09-16T12:00:00Z'));
    const [row] = rows([item({ requested_at: '2026-09-15T12:00:00Z' })]);
    expect(row[3].main).toBe('1 day');
  });

  it('falls back to the raw level string for a level LEVEL_LABEL does not name', () => {
    const [row] = rows([item({ requested_disclosure_level: 'SOMETHING_NEW' })]);
    expect(row[0].sub).toBe('Requested: SOMETHING_NEW');
  });

  it('falls back to a muted pill of the raw status for a status STATUS_PILL does not name', () => {
    const [row] = rows([item({ status: 'SOMETHING_NEW' })]);
    expect(row[2].pill).toBe('SOMETHING_NEW');
  });

  it('says when a resolved request was reviewed, rather than inventing a status narrative', () => {
    vi.setSystemTime(new Date('2026-09-16T12:00:00Z'));
    const [row] = rows([item({ status: 'DENIED', requested_at: '2026-09-01T12:00:00Z', reviewed_at: '2026-09-03T09:00:00Z' })]);
    expect(row[3].main).toBe('15 days');
    expect(row[3].sub).toBe('Reviewed September 3');
  });

  it('renders no action button in any column — this tab has no Action column at all', () => {
    for (const row of rows([ITEM])) expect(row.every((c) => !c.hasActions)).toBe(true);
  });

});

describe('the design\'s own rows, as the pixel oracle serves them', () => {
  // `DesignRequestRow` -- the arm `frontend/tests/design-admin-requests.mjs` answers the app
  // through, so the frozen `admin-requests` capture keeps its hash while the live path renders
  // real disclosure requests.
  const design = (i: number): DesignRequestRow => ({
    id: `design-${i}`,
    request: ACTIVITY[i][0].main, requestSub: ACTIVITY[i][0].sub,
    practice: ACTIVITY[i][1].main, practiceSub: ACTIVITY[i][1].sub,
    pill: ACTIVITY[i][2].pill, pillStyle: ACTIVITY[i][2].pillStyle,
    age: ACTIVITY[i][3].main, ageSub: ACTIVITY[i][3].sub
  });

  it('reproduces all four of the design\'s rows, cell for cell and style for style', () => {
    const result = rows([0, 1, 2, 3].map(design));
    for (const [i, row] of result.entries()) expect(row, `row ${i}`).toEqual(ACTIVITY[i]);
  });
});

describe('countsOf', () => {
  it('reads a well-formed counts object', () => {
    const counts: AdminRequestCounts | null = countsOf({ counts: { pending: 4, total: 9 } });
    expect(counts).toEqual({ pending: 4, total: 9 });
  });

  it('is null where the page carries none — the badge stays unmounted rather than reading "0"', () => {
    expect(countsOf({ counts: null })).toBeNull();
    expect(countsOf({})).toBeNull();
  });
});

describe('STATUS_PILL and LEVEL_LABEL', () => {
  it('covers every status request.status\'s own CHECK constraint holds', () => {
    expect(Object.keys(STATUS_PILL).sort()).toEqual(['APPROVED', 'DENIED', 'PENDING', 'REVOKED']);
  });

  it('covers every level app.disclosure.levels.REQUESTABLE_LEVELS holds', () => {
    expect(Object.keys(LEVEL_LABEL).sort()).toEqual(
      ['EXACT_LOCATION', 'FINANCIALS', 'FLOOR_PLANS', 'FULL_CONFIDENTIAL', 'IDENTITY', 'UNREDACTED_IMAGES']
    );
  });
});

describe('makeAdminRequestsAdapter', () => {
  it('walks every page via cursor and returns the combined rows with the first page\'s counts', async () => {
    const pageOne = { items: [ITEM], next_cursor: 'cursor-1', counts: { pending: 2, total: 3 } };
    const pageTwo = { items: [item({ id: 'req-2' })], next_cursor: null, counts: null };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => pageOne })
      .mockResolvedValueOnce({ ok: true, json: async () => pageTwo });
    vi.stubGlobal('fetch', fetchMock);

    const adapter = makeAdminRequestsAdapter();
    const result = await adapter.list();

    expect(result.rows.length).toBe(2);
    expect(result.counts).toEqual({ pending: 2, total: 3 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/requests?limit=200');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/admin/requests?limit=200&cursor=cursor-1');
    // No X-CSRF-Token and no Content-Type — this is a GET, `admin/data_sources.ts`'s own rule.
    expect(fetchMock.mock.calls[0][1]).toEqual({ method: 'GET', credentials: 'same-origin' });
  });

  it('throws when the queue could not be read', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({ ok: false }));
    await expect(makeAdminRequestsAdapter().list()).rejects.toThrow();
  });

  it('throws when the answer carries no items array at all', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({}) }));
    await expect(makeAdminRequestsAdapter().list()).rejects.toThrow('the request queue answered no items');
  });
});
