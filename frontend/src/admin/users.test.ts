// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Component } from '../logic.js';
import {
  ACTIONS, NOTE_REQUIRED, PILLS, ROLE_LABELS, countsOf, makeAdminUsersAdapter, toUserRows,
  type Cell, type DesignUserRow, type UserItem, type UsersUi
} from './users';

// ---------------------------------------------------------------------------------------
// The design's OWN `adminVals()` output is the oracle for every style string below, so
// "the cell()/A() shapes and pill tones are copied verbatim from logic.js" is machine-checked
// rather than transcribed by hand — a change on either side fails here. The row CONTENT for
// the four fixture applicants is asserted against the design's strings too, wherever the live
// payload carries the same fact — which, since Task A36 put `decided_at`/`decided_by_name` in
// the payload, now includes row 4's "Approved August 12 by staff reviewer K. Alvarez."
// ---------------------------------------------------------------------------------------
const designCells = (tab: string): Cell[][] => {
  const c = new Component({});
  c.setState({ adminTab: tab });
  return c.adminVals().rows.map((r: { cells: Cell[] }) => r.cells);
};
const DESIGN = designCells('users');            // Priya (pending) · Marcus (pending) · Cho (needs_review) · Mendes (active)
const LISTINGS = designCells('listings');       // the one fixture row with an `info` pill ("Paused")

const PILL = {
  warn: DESIGN[0][2].pillStyle,
  bad: DESIGN[2][2].pillStyle,
  ok: DESIGN[3][2].pillStyle,
  info: LISTINGS[3][2].pillStyle,
  // The one tone no fixture row uses, so the one transcribed from logic.js's `tones` table
  // (`mute: ["#494949", "#f5f5f5", "#d4dde5"]`) rather than read back out of the design.
  mute: 'display: inline-block; font-size: 11.5px; font-weight: 500; padding: 4px 11px; border-radius: 999px; color: #494949; background: #f5f5f5; border: 1px solid #d4dde5;'
};
const BTN = {
  primary: DESIGN[0][3].actions[0].style,   // A("Approve", "primary")
  danger: DESIGN[0][3].actions[1].style,    // A("Decline", "danger")
  plain: DESIGN[2][3].actions[0].style      // A("Request info") — no tone
};

const PRIYA: UserItem = {
  account_id: 'a1', email: 'priya@example.test', state: 'pending', name: 'Dr. Priya Raghavan',
  affiliation_label: null, kind: 'buyer', flags: [], roles: [], grants: [],
  decided_at: null, decided_by_name: null,
  fields: { school_year: 'Texas A&M, 2016', license_state: 'TX', employer: 'Associate, two-doctor practice', intent: 'Looking to buy within 18 months in Central Texas.' }
};
const item = (over: Partial<UserItem>): UserItem => ({ ...PRIYA, ...over });

function recordingUi(note: string | null = 'a reviewer note') {
  const calls: string[] = [];
  const ui: UsersUi = {
    needsNote: (action) => { calls.push(`needsNote:${action}`); return Promise.resolve(note); },
    decide: (target, action, given) => { calls.push(`decide:${target.account_id}:${action}:${given}`); return Promise.resolve(); }
  };
  return { ui, calls };
}
const rowsFor = (items: (UserItem | DesignUserRow)[]): Cell[][] => toUserRows(items, recordingUi().ui);

describe('toUserRows renders the design\'s Users table from the live payload', () => {
  it('reproduces the applicant and affiliation cells the approved design shows', () => {
    const [row] = rowsFor([PRIYA]);
    expect(row[0]).toEqual(DESIGN[0][0]);      // "Dr. Priya Raghavan" / "Texas A&M, 2016 · TX license"
    expect(row[1]).toEqual(DESIGN[0][1]);      // employer / “intent”
    expect(row[2]).toEqual(DESIGN[0][2]);      // "Pending", warn
  });

  it('pluralises a multi-state licence exactly as the design does', () => {
    const [row] = rowsFor([item({ name: 'Dr. Marcus Bell', fields: { school_year: 'Colorado State, 2009', license_state: 'TX, NM' } })]);
    expect(row[0]).toEqual(DESIGN[1][0]);      // "Colorado State, 2009 · TX, NM licenses"
  });

  it('replaces the intent quote with the reviewer hint when the application carries a flag', () => {
    const [row] = rowsFor([item({
      name: 'Dr. Alan Cho', state: 'needs_review', flags: ['employer_keyword'],
      fields: { school_year: 'Ohio State, 2004', license_state: 'TX', employer: 'Regional medical director, 14-hospital group', intent: 'never rendered while a flag stands' }
    })]);
    expect(row[0]).toEqual(DESIGN[2][0]);
    expect(row[1]).toEqual(DESIGN[2][1]);      // "Affiliation flagged: employer appears to be a consolidator."
    expect(row[2]).toEqual(DESIGN[2][2]);      // "Needs review", bad
  });

  it('writes the design\'s own approved sentence from the decision the API now serves', () => {
    // The design's fourth row, reproduced from a real payload for the first time: Task A36 put
    // `decided_at` and `decided_by_name` in `GET /api/admin/users`, so the provenance sentence is
    // the application's own decision rather than prose with nothing behind it.
    const [row] = rowsFor([item({
      name: 'Dr. Rachel Mendes', state: 'active', affiliation_label: 'StartUp Club',
      decided_at: '2026-08-12T15:04:05+00:00', decided_by_name: 'K. Alvarez',
      fields: { school_year: 'Texas A&M, 2014', license_state: 'TX', employer: 'Relief veterinarian', intent: 'Buy within 18 months.' }
    })]);
    expect(row[0]).toEqual(DESIGN[3][0]);      // "Dr. Rachel Mendes" / "Texas A&M, 2014 · TX license"
    expect(row[1]).toEqual(DESIGN[3][1]);      // "Relief veterinarian · StartUp Club" / "Approved August 12 by staff reviewer K. Alvarez."
    expect(row[2]).toEqual(DESIGN[3][2]);      // "Approved", ok
  });

  it('reads the day the API stamped, in UTC, whatever the runtime\'s own offset is', () => {
    // `formatDate`'s reason for existing: the same instant an hour before midnight UTC is the
    // NEXT day in half the world, and `toLocaleDateString` would report the reviewer's day rather
    // than the decision's.
    const [row] = rowsFor([item({ state: 'active', decided_at: '2026-01-31T23:30:00+00:00', decided_by_name: 'K. Alvarez' })]);
    expect(row[1].sub).toBe('Approved January 31 by staff reviewer K. Alvarez.');
  });

  it('names the day and not the decider when the payload carries no name', () => {
    const [row] = rowsFor([item({ state: 'active', decided_at: '2026-08-12T15:04:05+00:00', decided_by_name: null })]);
    expect(row[1].sub).toBe('Approved August 12.');
  });

  it('says nothing about a decision on an account the API has decided nothing about', () => {
    // An active account with no application row at all — seeded staff, or an invite — keeps the
    // design's own intent quote rather than an "Approved" sentence with no date behind it.
    const [row] = rowsFor([item({ state: 'active' })]);
    expect(row[1].sub).toBe('“Looking to buy within 18 months in Central Texas.”');
  });

  it('never calls a decline an approval, however recently it was decided', () => {
    // `decided_at` is stamped on a decline too, and the design has ONE provenance sentence and it
    // says "Approved" — so the sentence is gated on the state the pill is already showing.
    const [row] = rowsFor([item({ state: 'declined', decided_at: '2026-08-12T15:04:05+00:00', decided_by_name: 'K. Alvarez' })]);
    expect(row[1].sub).toBe('“Looking to buy within 18 months in Central Texas.”');
    expect(row[2]).toMatchObject({ pill: 'declined', pillStyle: PILL.mute });
  });

  it('names a flag the design has no copy for by the flag itself, rather than inventing prose', () => {
    const [row] = rowsFor([item({ flags: ['disposable_domain'] })]);
    expect(row[1].sub).toBe('Affiliation flagged: disposable_domain');
  });

  it('renders an application with no fields at all without inventing any', () => {
    const [row] = rowsFor([item({ fields: null, affiliation_label: null })]);
    expect(row[0]).toMatchObject({ hasMain: true, main: 'Dr. Priya Raghavan', hasSub: false, sub: '' });
    expect(row[1]).toMatchObject({ hasMain: false, main: '', hasSub: false, sub: '' });
  });

  // A-I7.2 (review Important 3): the rows ARE the design's rows — an array of cell arrays,
  // exactly `sets.<tab>.rows`, which `adminVals()`'s own
  // `set.rows.map((cells, i) => ({ cells, style }))` then wraps with the grid and the last-row
  // border. Anything else loses `style` and re-flows the table at maxDiffPixels: 0.
  it('returns the design\'s own row shape — four cells per row, no wrapper', () => {
    const rows = rowsFor([PRIYA, item({ kind: 'seller' })]);
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(Array.isArray(row)).toBe(true);
      expect(row).toHaveLength(DESIGN[0].length);
      expect(Object.keys(row[0])).toEqual(Object.keys(DESIGN[0][0]));
    }
  });
});

describe('the facts the design has no element for, stated in its own ` · ` idiom', () => {
  it('leads a seller application\'s affiliation sub-line with "Seller applicant" (ruling 8)', () => {
    // Spec §6 asks that a seller application be distinguishable on this tab; A-I7.2 measured that
    // V3 draws no kicker, so the ruling puts the fact in the sub-line rather than in an element
    // the design does not have. Everything else about the row is unchanged.
    const [seller] = rowsFor([item({ kind: 'seller' })]);
    const [buyer] = rowsFor([PRIYA]);
    expect(seller[1].sub).toBe('Seller applicant · “Looking to buy within 18 months in Central Texas.”');
    expect(seller[0]).toEqual(buyer[0]);
    expect(seller[2]).toEqual(buyer[2]);
    expect(seller[3].actions.map((a) => [a.label, a.style])).toEqual(buyer[3].actions.map((a) => [a.label, a.style]));
  });

  it('leads a flagged seller application with the marker and keeps the reviewer\'s hint', () => {
    const [row] = rowsFor([item({ kind: 'seller', flags: ['employer_keyword'] })]);
    expect(row[1].sub).toBe('Seller applicant · Affiliation flagged: employer appears to be a consolidator.');
  });

  it('names the VIN membership the footnote says is recorded (ruling 6)', () => {
    const [row] = rowsFor([item({ fields: { ...PRIYA.fields, vin_member_id: '884201' } })]);
    expect(row[0].sub).toBe('Texas A&M, 2016 · TX license · VIN member 884201');
  });

  it('names a VIN Foundation role and how its holder came to hold it (ruling 7)', () => {
    const [row] = rowsFor([item({
      name: 'Dr. Rachel Mendes', state: 'active', roles: ['admin', 'buyer'],
      grants: [{ role: 'admin', granted_by_name: 'Dr. Priya Raghavan', granted_at: '2026-08-12T09:00:00+00:00' },
               { role: 'buyer', granted_by_name: 'Dr. Priya Raghavan', granted_at: '2026-01-04T09:00:00+00:00' }],
      fields: { school_year: 'Texas A&M, 2014', license_state: 'TX' }
    })]);
    expect(row[0].sub).toBe('Texas A&M, 2014 · TX license · VIN Foundation admin · granted by Dr. Priya Raghavan August 12');
  });

  it('prefers admin over staff where an account holds both, exactly as role_label orders them', () => {
    const [row] = rowsFor([item({
      roles: ['admin', 'staff'],
      grants: [{ role: 'admin', granted_by_name: 'K. Alvarez', granted_at: '2026-03-02T09:00:00+00:00' },
               { role: 'staff', granted_by_name: 'K. Alvarez', granted_at: '2026-02-01T09:00:00+00:00' }],
      fields: {}
    })]);
    expect(row[0].sub).toBe('VIN Foundation admin · granted by K. Alvarez March 2');
  });

  it('says when, not by whom, where the grant names no granter', () => {
    const [row] = rowsFor([item({
      roles: ['staff'], grants: [{ role: 'staff', granted_by_name: null, granted_at: '2026-02-01T09:00:00+00:00' }], fields: {}
    })]);
    expect(row[0].sub).toBe('VIN Foundation staff · granted February 1');
  });

  it('names the role alone where the account holds it with no live grant row to describe it', () => {
    const [row] = rowsFor([item({ roles: ['staff'], grants: [], fields: {} })]);
    expect(row[0].sub).toBe('VIN Foundation staff');
  });

  it('says nothing extra about a buyer or a seller — the Status pill already does', () => {
    const [row] = rowsFor([item({
      roles: ['buyer', 'seller'],
      grants: [{ role: 'buyer', granted_by_name: 'K. Alvarez', granted_at: '2026-02-01T09:00:00+00:00' }]
    })]);
    expect(row[0]).toEqual(DESIGN[0][0]);
  });

  it('names the two VIN Foundation roles in app/auth/labels.py\'s own words', () => {
    // Pinned across the language boundary by `tests/test_docs.py`; asserted here too so a change
    // to this table fails in the suite that owns the file as well as in the one that owns the pin.
    expect(ROLE_LABELS).toEqual({ admin: 'VIN Foundation admin', staff: 'VIN Foundation staff' });
  });
});

describe('the pill and the decision buttons, per account state', () => {
  const pillOf = (state: string) => rowsFor([item({ state })])[0][2];
  const buttonsOf = (state: string) => rowsFor([item({ state })])[0][3];

  it('carries the design\'s tones', () => {
    expect(pillOf('pending')).toMatchObject({ pill: 'Pending', pillStyle: PILL.warn });
    expect(pillOf('needs_review')).toMatchObject({ pill: 'Needs review', pillStyle: PILL.bad });
    expect(pillOf('active')).toMatchObject({ pill: 'Approved', pillStyle: PILL.ok });
    expect(pillOf('suspended')).toMatchObject({ pill: 'Suspended', pillStyle: PILL.info });
    expect(pillOf('revoked')).toMatchObject({ pill: 'Revoked', pillStyle: PILL.bad });
  });

  it('shows the state itself, muted, for the three ACCOUNT_STATES the design has no pill for', () => {
    // `unverified`, `verified` and `declined` are real states with no ruled label, so the state
    // key is shown rather than prose nobody approved. Listed in PILLS rather than left to the
    // fallback, because `tests/test_docs.py` pins PILLS's keys against `ACCOUNT_STATES` (M3).
    expect(pillOf('unverified')).toMatchObject({ pill: 'unverified', pillStyle: PILL.mute });
    expect(pillOf('verified')).toMatchObject({ pill: 'verified', pillStyle: PILL.mute });
    expect(pillOf('declined')).toMatchObject({ pill: 'declined', pillStyle: PILL.mute });
  });

  it('covers every account state the API can report, and fails soft on one it cannot yet', () => {
    expect(Object.keys(PILLS)).toHaveLength(8);                       // pinned against ACCOUNT_STATES from pytest
    expect(pillOf('hibernating')).toMatchObject({ pill: 'hibernating', pillStyle: PILL.mute });
    expect(buttonsOf('hibernating')).toMatchObject({ hasActions: false, actions: [] });
    expect(Object.keys(ACTIONS)).toEqual(['pending', 'needs_review', 'active', 'suspended']);
  });

  it('offers the buttons the approved design shows for each state (a legal subset of the API\'s transitions)', () => {
    expect(buttonsOf('pending').actions.map((a) => [a.label, a.style])).toEqual([['Approve', BTN.primary], ['Decline', BTN.danger], ['Request info', BTN.plain]]);
    expect(buttonsOf('needs_review').actions.map((a) => [a.label, a.style])).toEqual([['Approve', BTN.primary], ['Decline', BTN.danger]]);
    expect(buttonsOf('active').actions.map((a) => [a.label, a.style])).toEqual([['Suspend', BTN.plain]]);
    expect(buttonsOf('suspended').actions.map((a) => [a.label, a.style])).toEqual([['Reinstate', BTN.plain]]);
  });

  it('renders no Revoke button on any state, because no step-up element exists to complete it', () => {
    // The controller's ruling 6 (2026-09-13): `users.revoke` is in `permissions.REAUTH`, the API
    // refuses it without a fresh password, and V3 draws no step-up. A button that cannot complete
    // its action is fake (D-C53), so it is not rendered until John approves the dialog — while
    // `NOTE_REQUIRED` keeps mirroring the API's own four, which pytest pins by equality.
    for (const state of Object.keys(PILLS)) {
      expect(buttonsOf(state).actions.map((a) => a.label), state).not.toContain('Revoke');
    }
    expect(Object.values(ACTIONS).flat()).not.toContain('revoke');
    expect(NOTE_REQUIRED).toContain('revoke');
  });

  it('offers nothing on a state with no transition left, and the cell says so', () => {
    expect(buttonsOf('revoked')).toMatchObject({ hasActions: false, actions: [] });
  });
});

describe('a decision is a note, then the post', () => {
  const press = async (state: string, label: string, note: string | null = 'a reviewer note') => {
    const { ui, calls } = recordingUi(note);
    const row = toUserRows([item({ state })], ui)[0];
    await row[3].actions.find((a) => a.label === label)!.go();
    return calls;
  };

  it('requires a note for Decline, Request info and Suspend — the rendered three of the API\'s four', async () => {
    expect(NOTE_REQUIRED).toEqual(['decline', 'request_info', 'suspend', 'revoke']);
    expect(await press('pending', 'Decline')).toEqual(['needsNote:decline', 'decide:a1:decline:a reviewer note']);
    expect(await press('pending', 'Request info')).toEqual(['needsNote:request_info', 'decide:a1:request_info:a reviewer note']);
    expect(await press('active', 'Suspend')).toEqual(['needsNote:suspend', 'decide:a1:suspend:a reviewer note']);
  });

  it('asks for no note on Approve and Reinstate, which the API accepts without one', async () => {
    expect(await press('pending', 'Approve')).toEqual(['decide:a1:approve:']);
    expect(await press('suspended', 'Reinstate')).toEqual(['decide:a1:reinstate:']);
  });

  it('sends nothing when the reviewer cancels the prompt, or leaves it blank', async () => {
    expect(await press('pending', 'Decline', null)).toEqual(['needsNote:decline']);
    expect(await press('pending', 'Decline', '   ')).toEqual(['needsNote:decline']);
  });
});

describe('the design\'s own rows, as the pixel oracle serves them', () => {
  // `DesignUserRow` — the arm `frontend/tests/design-admin-users.mjs` answers the app through, so
  // the frozen `admin-users` capture keeps its hash while the live path renders real accounts.
  // Two of the design's rows are unreachable from a real payload by construction: Cho's
  // NEEDS-REVIEW row offers "Request info", which `TRANSITIONS` allows from `pending` only, and
  // every row's action set is the design's own rather than `ACTIONS`.
  const design = (i: number): DesignUserRow => ({
    account_id: `design-${i}`,
    applicant: DESIGN[i][0].main, applicantSub: DESIGN[i][0].sub,
    affiliation: DESIGN[i][1].main, intent: DESIGN[i][1].sub,
    pill: DESIGN[i][2].pill, pillStyle: DESIGN[i][2].pillStyle,
    actions: DESIGN[i][3].actions.map((a) => ({ label: a.label, style: a.style }))
  });

  it('reproduces all four of the design\'s rows, cell for cell and style for style', () => {
    const rows = rowsFor([0, 1, 2, 3].map(design));
    for (const [i, row] of rows.entries()) {
      expect(row.slice(0, 3), `row ${i}`).toEqual(DESIGN[i].slice(0, 3));
      expect(row[3].actions.map((a) => [a.label, a.style])).toEqual(DESIGN[i][3].actions.map((a) => [a.label, a.style]));
    }
  });

  it('carries a button set no live state could produce, and makes it a no-op', async () => {
    const [cho] = rowsFor([design(2)]);
    expect(cho[3].actions.map((a) => a.label)).toEqual(['Request info', 'Decline']);
    expect(ACTIONS.needs_review).not.toContain('request_info');
    const { ui, calls } = recordingUi();
    await toUserRows([design(2)], ui)[0][3].actions[0].go();
    expect(calls).toEqual([]);
  });

  it('keeps the design\'s Revoke button on the approved row, which the live table does not render', () => {
    const [mendes] = rowsFor([design(3)]);
    expect(mendes[3].actions.map((a) => a.label)).toEqual(['Suspend', 'Revoke']);
  });
});

describe('countsOf reads the badge, or says there is none', () => {
  it('takes the two numbers the API serves', () => {
    expect(countsOf({ counts: { open: 3, total: 29 } })).toEqual({ open: 3, total: 29 });
  });

  it('answers null where the response carried no counts at all', () => {
    expect(countsOf({ items: [] })).toBeNull();
  });

  it('answers null rather than a partial badge where the shape is not the two numbers', () => {
    expect(countsOf({ counts: { open: '3', total: 29 } })).toBeNull();
    expect(countsOf({ counts: { open: 3 } })).toBeNull();
  });
});

describe('makeAdminUsersAdapter, against the real fetch boundary', () => {
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
  const page = (items: unknown[], over: Record<string, unknown> = {}) =>
    ({ status: 200, body: { items, next_cursor: null, counts: { open: 1, total: 4 }, ...over } });
  const reload = () => vi.fn();

  beforeEach(() => { document.cookie = 'pm_csrf=tok123'; });
  afterEach(() => vi.unstubAllGlobals());

  it('lists one page, mapped through toUserRows, with no double-submit token on the read', async () => {
    const calls = stubFetch(page([PRIYA]));
    const { rows, counts } = await makeAdminUsersAdapter().list(reload());
    expect(rows).toHaveLength(1);
    expect(rows[0][0].main).toBe('Dr. Priya Raghavan');
    expect(counts).toEqual({ open: 1, total: 4 });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('/api/admin/users?limit=200');
    expect(calls[0].init.headers['X-CSRF-Token']).toBeUndefined();
  });

  it('follows next_cursor to the end, and keeps the first page\'s counts', async () => {
    const calls = stubFetch(
      page([item({ account_id: 'a1' })], { next_cursor: '2026-09-01T00:00:00Z|a1' }),
      page([item({ account_id: 'a2' })], { counts: undefined })
    );
    const { rows, counts } = await makeAdminUsersAdapter().list(reload());
    expect(rows).toHaveLength(2);
    expect(calls[1].url).toContain('cursor=2026-09-01T00%3A00%3A00Z%7Ca1');
    expect(counts).toEqual({ open: 1, total: 4 });
  });

  it('answers no badge at all when no page carried one', async () => {
    stubFetch(page([PRIYA], { counts: undefined }));
    expect((await makeAdminUsersAdapter().list(reload())).counts).toBeNull();
  });

  it('rejects when the queue cannot be read, or answers no items', async () => {
    stubFetch({ status: 503 });
    await expect(makeAdminUsersAdapter().list(reload())).rejects.toThrow('could not be read');
    stubFetch({ status: 200, body: { next_cursor: null } });
    await expect(makeAdminUsersAdapter().list(reload())).rejects.toThrow('no items');
  });

  it('approves through the API, with the double-submit token, and re-reads the queue after it', async () => {
    const calls = stubFetch(page([PRIYA]), { status: 200, body: { state: 'active', roles: ['buyer'] } });
    const again = vi.fn();
    const { rows } = await makeAdminUsersAdapter().list(again);
    await rows[0][3].actions.find((a) => a.label === 'Approve')!.go();
    expect(calls[1].url).toBe('/api/admin/users/a1/decide');
    expect(calls[1].init.headers['X-CSRF-Token']).toBe('tok123');
    expect(JSON.parse(calls[1].init.body!)).toEqual({ action: 'approve', note: '' });
    expect(again).toHaveBeenCalledTimes(1);
  });

  it('asks for the decline reason through the browser\'s own prompt, and sends it', async () => {
    const calls = stubFetch(page([PRIYA]), { status: 200, body: {} });
    const promptSpy = vi.fn().mockReturnValueOnce('affiliation could not be verified');
    vi.stubGlobal('prompt', promptSpy);
    const { rows } = await makeAdminUsersAdapter().list(reload());
    await rows[0][3].actions.find((a) => a.label === 'Decline')!.go();
    expect(promptSpy).toHaveBeenCalledWith('Why is this account being declined?');
    expect(JSON.parse(calls[1].init.body!)).toEqual({ action: 'decline', note: 'affiliation could not be verified' });
  });

  it('asks the applicant\'s own question on Request info, and the reviewer\'s reason on Suspend', async () => {
    const promptSpy = vi.fn().mockReturnValue('because');
    vi.stubGlobal('prompt', promptSpy);
    const first = stubFetch(page([PRIYA]), { status: 200, body: {} });
    const { rows } = await makeAdminUsersAdapter().list(reload());
    await rows[0][3].actions.find((a) => a.label === 'Request info')!.go();
    expect(promptSpy).toHaveBeenLastCalledWith('What do you need from this applicant before a decision can be made?');
    expect(JSON.parse(first[1].init.body!)).toMatchObject({ action: 'request_info' });

    const second = stubFetch(page([item({ state: 'active' })]), { status: 200, body: {} });
    const active = await makeAdminUsersAdapter().list(reload());
    await active.rows[0][3].actions.find((a) => a.label === 'Suspend')!.go();
    expect(promptSpy).toHaveBeenLastCalledWith('Why is this account being suspended?');
    expect(JSON.parse(second[1].init.body!)).toMatchObject({ action: 'suspend' });
  });

  it('sends nothing, and re-reads nothing, when the reviewer cancels the note prompt', async () => {
    const calls = stubFetch(page([PRIYA]));
    vi.stubGlobal('prompt', vi.fn().mockReturnValueOnce(null));
    const again = vi.fn();
    const { rows } = await makeAdminUsersAdapter().list(again);
    await rows[0][3].actions.find((a) => a.label === 'Decline')!.go();
    expect(calls).toHaveLength(1);            // the list GET alone — no decide POST followed the cancel
    expect(again).not.toHaveBeenCalled();
  });

  it('alerts the reviewer, rather than failing silently, when the decision is refused — and still re-reads', async () => {
    // A 409 is the API saying the row is not in the state the reviewer was looking at, so the
    // queue is re-read on a refusal exactly as on a success: the cure for a stale row is the data.
    stubFetch(page([PRIYA]), { status: 409, body: { error: { code: 'STATE', message: 'approve is not allowed from state active' } } });
    const alertSpy = vi.fn();
    vi.stubGlobal('alert', alertSpy);
    const again = vi.fn();
    const { rows } = await makeAdminUsersAdapter().list(again);
    await rows[0][3].actions.find((a) => a.label === 'Approve')!.go();
    expect(alertSpy).toHaveBeenCalledWith('approve is not allowed from state active');
    expect(again).toHaveBeenCalledTimes(1);
  });

  it('alerts with generic wording when the refusal is not the API\'s own envelope', async () => {
    // The `??` fallback: a proxy error page, or a 401 with no body — not a refusal that names a
    // reason.
    stubFetch(page([PRIYA]), { status: 502, body: {} });
    const alertSpy = vi.fn();
    vi.stubGlobal('alert', alertSpy);
    const { rows } = await makeAdminUsersAdapter().list(reload());
    await rows[0][3].actions.find((a) => a.label === 'Approve')!.go();
    expect(alertSpy).toHaveBeenCalledWith('That decision could not be recorded.');
  });
});
