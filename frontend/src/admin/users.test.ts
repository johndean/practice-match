// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { Component } from '../logic.js';
import { ACTIONS, NOTE_REQUIRED, PILLS, toUserRows, type Cell, type UserItem, type UsersUi } from './users';

// ---------------------------------------------------------------------------------------
// The design's OWN `adminVals()` output is the oracle for every style string below, so
// "the cell()/A() shapes and pill tones are copied verbatim from logic.js" is machine-checked
// rather than transcribed by hand — a change on either side fails here. The row CONTENT for
// the four fixture applicants is asserted against the design's strings too, wherever the live
// payload carries the same fact (`GET /api/admin/users` has no "Approved August 12 by staff
// reviewer K. Alvarez." to give, so row 4's sub-line is the applicant's intent instead).
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
  affiliation_label: null, kind: 'buyer', flags: [],
  fields: { school_year: 'Texas A&M, 2016', license_state: 'TX', employer: 'Associate, two-doctor practice', intent: 'Looking to buy within 18 months in Central Texas.' }
};
const item = (over: Partial<UserItem>): UserItem => ({ ...PRIYA, ...over });

function recordingUi(note: string | null = 'a reviewer note') {
  const calls: string[] = [];
  const ui: UsersUi = {
    needsNote: (action) => { calls.push(`needsNote:${action}`); return Promise.resolve(note); },
    reauthThen: async (post) => { calls.push('reauthThen'); await post(); },
    decide: (target, action, given) => { calls.push(`decide:${target.account_id}:${action}:${given}`); return Promise.resolve(); }
  };
  return { ui, calls };
}
const rowsFor = (items: UserItem[]): Cell[][] => toUserRows(items, recordingUi().ui);

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

  it('appends the free-text affiliation to the employer, and shows the Approved pill', () => {
    const [row] = rowsFor([item({
      name: 'Dr. Rachel Mendes', state: 'active', affiliation_label: 'StartUp Club',
      fields: { school_year: 'Texas A&M, 2014', license_state: 'TX', employer: 'Relief veterinarian', intent: 'Buy within 18 months.' }
    })]);
    expect(row[0]).toEqual(DESIGN[3][0]);      // "Dr. Rachel Mendes" / "Texas A&M, 2014 · TX license"
    expect(row[1].main).toBe('Relief veterinarian · StartUp Club');
    expect(row[2]).toEqual(DESIGN[3][2]);      // "Approved", ok
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
  // border. Anything else loses `style` and re-flows the table at maxDiffPixels: 0. There is no
  // "Seller" kicker: the V3 Admin Users tab has no such element, and how a seller application is
  // distinguished there is a Rev 3 design item.
  it('returns the design\'s own row shape — four cells per row, no wrapper', () => {
    const rows = rowsFor([PRIYA, item({ kind: 'seller' })]);
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(Array.isArray(row)).toBe(true);
      expect(row).toHaveLength(DESIGN[0].length);
      expect(Object.keys(row[0])).toEqual(Object.keys(DESIGN[0][0]));
    }
    // `kind` alone changes nothing that is rendered (the cells' action closures are per-call, so
    // the buttons are compared by label rather than by identity).
    const [buyer, seller] = [rowsFor([PRIYA])[0], rowsFor([item({ kind: 'seller' })])[0]];
    expect(seller.slice(0, 3)).toEqual(buyer.slice(0, 3));
    expect(seller[3].actions.map((a) => [a.label, a.style])).toEqual(buyer[3].actions.map((a) => [a.label, a.style]));
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
    expect(buttonsOf('active').actions.map((a) => [a.label, a.style])).toEqual([['Suspend', BTN.plain], ['Revoke', BTN.danger]]);
    expect(buttonsOf('suspended').actions.map((a) => [a.label, a.style])).toEqual([['Reinstate', BTN.plain], ['Revoke', BTN.danger]]);
  });

  it('offers nothing on a state with no transition left, and the cell says so', () => {
    expect(buttonsOf('revoked')).toMatchObject({ hasActions: false, actions: [] });
  });
});

describe('a decision is a note, sometimes a re-authentication, then the post', () => {
  const press = async (state: string, label: string, note: string | null = 'a reviewer note') => {
    const { ui, calls } = recordingUi(note);
    const row = toUserRows([item({ state })], ui)[0];
    await row[3].actions.find((a) => a.label === label)!.go();
    return calls;
  };

  it('requires a note for Decline, Request info, Suspend and Revoke — the four the API refuses without one', async () => {
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

  it('puts Revoke — and only Revoke — behind a re-authentication, because it is the one in REAUTH', async () => {
    expect(await press('active', 'Revoke')).toEqual(['needsNote:revoke', 'reauthThen', 'decide:a1:revoke:a reviewer note']);
    expect(await press('active', 'Suspend')).not.toContain('reauthThen');
  });
});
