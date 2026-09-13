// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Component } from '../logic.js';
import { A, PILLS, cell, makeAdminDataSourcesAdapter, notCleared, toDataSourceRows, type Cell, type DataSourceItem, type DesignDataSourceRow } from './data_sources';

// ---------------------------------------------------------------------------------------
// The design's OWN `adminVals()` output is the oracle for every style string below, exactly as
// `users.test.ts` and `listings.test.ts` use it: "cell()/A() are copied verbatim from logic.js"
// is machine-checked rather than transcribed, and a change on either side fails here.
// ---------------------------------------------------------------------------------------
const designCells = (tab: string): Cell[][] => {
  const c = new Component({});
  c.setState({ adminTab: tab });
  return c.adminVals().rows.map((r: { cells: Cell[] }) => r.cells);
};
const DESIGN = designCells('data');       // Cleared ×3 · Unresolved · Blocked
const LISTINGS = designCells('listings'); // the one fixture row with an `info` pill ("Paused")

const PILL = {
  ok: DESIGN[0][2].pillStyle,
  bad: DESIGN[3][2].pillStyle,
  warn: designCells('users')[0][2].pillStyle,
  info: LISTINGS[3][2].pillStyle,
  // The one tone no fixture row on this tab uses, transcribed from logic.js's own `tones` table.
  mute: 'display: inline-block; font-size: 11.5px; font-weight: 500; padding: 4px 11px; border-radius: 999px; color: #494949; background: #f5f5f5; border: 1px solid #d4dde5;'
};
// `A("View terms")` — the design's own untoned button, the only one this tab keeps (ruling 18).
const VIEW_TERMS_STYLE = DESIGN[0][3].actions[0].style;

const ACS: DataSourceItem = {
  dataset_key: 'acs5',
  display_name: 'ACS 5-Year Detailed Tables',
  refresh_cadence: 'Annual (Dec)',
  license_status: 'cleared',
  license_name: 'Public domain',
  license_url: 'https://www.census.gov/data/developers/about/terms-of-service.html',
  attribution_text: 'Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023',
  last_verified_at: null,
  drift_flagged: false,
  notes: null,
  vintage: '2019–2023',
  active_vintage: null,
  active_vintage_note: null,
  last_run: null
};
const item = (over: Partial<DataSourceItem>): DataSourceItem => ({ ...ACS, ...over });
const rows = (items: (DataSourceItem | DesignDataSourceRow)[]): Cell[][] => toDataSourceRows(items);

afterEach(() => vi.restoreAllMocks());

describe('toDataSourceRows renders the design\'s Data Sources table from the registry payload', () => {
  it('names the dataset, its cadence and the fact that its terms have never been verified', () => {
    const [row] = rows([ACS]);
    expect(row[0].main).toBe('ACS 5-Year Detailed Tables');
    // `last_verified_at` is null for every dataset the quarterly sweep has not read a body for,
    // and "never" is what that means — never the date of a failed attempt
    // (`app/api/admin_data_sources.py`'s own note on the field's two authors).
    expect(row[0].sub).toBe('Annual (Dec) · Declared vintage 2019–2023 · Terms verified never');
  });

  it('serves the attribution string VERBATIM — it is never composed here (spec §12)', () => {
    const [row] = rows([ACS]);
    expect(row[1].main).toBe(ACS.attribution_text);
    expect(row[1].sub).toBe('Public domain');
  });

  it('says so when no licence has been recorded, rather than leaving the line empty', () => {
    const [row] = rows([item({ license_name: null, license_status: 'unresolved', license_url: null })]);
    expect(row[1].sub).toBe('Licence not recorded');
  });

  it('carries the operator\'s own notes and the drift flag on the source sub-line', () => {
    const [row] = rows([item({ notes: 'Growth baseline only', drift_flagged: true })]);
    expect(row[1].sub).toBe('Public domain · Growth baseline only · Terms drift flagged');
  });

  it('reports a successful load with its month and its row count', () => {
    const [row] = rows([item({ last_run: { status: 'succeeded', finished_at: '2026-06-14T09:12:00+00:00', rows_written: 4200 } })]);
    expect(row[0].sub).toBe('Annual (Dec) · Loaded June 2026 (4,200 rows) · Declared vintage 2019–2023 · Terms verified never');
  });

  it('never reports a load that did not succeed as a load', () => {
    const [row] = rows([item({ last_run: { status: 'failed', finished_at: '2026-06-14T09:12:00+00:00', rows_written: 0 } })]);
    expect(row[0].sub).toBe('Annual (Dec) · Last load failed June 2026 · Declared vintage 2019–2023 · Terms verified never');
  });

  it('omits the month of a run that has not finished, and counts a null row tally as none', () => {
    expect(rows([item({ last_run: { status: 'running', finished_at: null, rows_written: null } })])[0][0].sub)
      .toBe('Annual (Dec) · Last load running · Declared vintage 2019–2023 · Terms verified never');
    expect(rows([item({ last_run: { status: 'succeeded', finished_at: null, rows_written: null } })])[0][0].sub)
      .toBe('Annual (Dec) · Loaded (0 rows) · Declared vintage 2019–2023 · Terms verified never');
  });

  it('names the vintage the app is actually allowed to read, and when the terms were verified', () => {
    const [row] = rows([item({ active_vintage: '2019–2023', last_verified_at: '2026-06-02T00:00:00+00:00' })]);
    expect(row[0].sub).toBe('Annual (Dec) · Declared vintage 2019–2023 · Live vintage 2019–2023 · Terms verified June 2026');
  });

  // A38 fix round 1 (review M6, D-C53's "everything must be surfaced"): three fields the route
  // serves were not on the tab. TWO of them are now, and the third is recorded as deliberately not.
  it('names the DECLARED vintage beside the live one, so the two can be read against each other', () => {
    // `dataset_registry.vintage` is what the platform registered; `active_vintage.vintage` is what
    // the app is allowed to read today. A row where they differ is a real operational state — an
    // activation that has not happened — and before this the tab showed only the second of them.
    const [row] = rows([item({ vintage: '2019–2023', active_vintage: '2014–2018' })]);
    expect(row[0].sub).toBe('Annual (Dec) · Declared vintage 2019–2023 · Live vintage 2014–2018 · Terms verified never');
  });

  it('has no vintage clause where the registry declares none', () => {
    expect(rows([item({ vintage: null })])[0][0].sub).toBe('Annual (Dec) · Terms verified never');
  });

  it('carries the operator\'s activation note, in the design\'s own parenthesis, beside the vintage it explains', () => {
    // A-C7 (6)'s persisted "why": the CLI REQUIRES it when an activation is forced past the
    // row-count guard, and `app/api/admin_data_sources.py`'s own docstring says this tab is the
    // only surface that reads it back. The parenthesis is the design's own idiom on this very
    // sub-line ("Loaded June 2026 (4,200 rows)"), so it needs no word the design does not have.
    const [row] = rows([item({ active_vintage: '2022', active_vintage_note: 'forced past the row-count guard' })]);
    expect(row[0].sub).toBe('Annual (Dec) · Declared vintage 2019–2023 · Live vintage 2022 (forced past the row-count guard) · Terms verified never');
  });

  it('still shows an activation note where the live vintage itself is missing', () => {
    // `active_vintage.vintage` is NOT NULL, so this cannot happen through the CLI — but dropping
    // an operator's written note on the tab that IS its only reader is the one outcome this
    // module must not have, so the note takes its own clause rather than vanishing with its host.
    const [row] = rows([item({ active_vintage: null, active_vintage_note: 'why' })]);
    expect(row[0].sub).toBe('Annual (Dec) · Declared vintage 2019–2023 · why · Terms verified never');
  });

  it('reads a date in UTC, so a reviewer\'s own browser offset cannot move the month', () => {
    // 23:30 on 30 June UTC is 1 July in Sydney and 30 June in Austin; the answer is the month
    // the API actually stamped, whichever machine renders it (`admin/listings.ts`'s own rule).
    const [row] = rows([item({ last_verified_at: '2026-06-30T23:30:00+00:00' })]);
    expect(row[0].sub).toContain('Terms verified June 2026');
  });
});

describe('the status pill and the one action the tab still offers', () => {
  it('uses the design\'s own three pills for the three statuses the column really has', () => {
    expect(rows([item({ license_status: 'cleared' })])[0][2]).toEqual({ ...DESIGN[0][2] });
    expect(rows([item({ license_status: 'unresolved' })])[0][2].pill).toBe('Unresolved');
    expect(rows([item({ license_status: 'unresolved' })])[0][2].pillStyle).toBe(PILL.bad);
    expect(rows([item({ license_status: 'blocked' })])[0][2]).toEqual({ ...DESIGN[4][2] });
    expect(PILL.warn).not.toBe(PILL.bad);   // the tones really are distinct, so `toEqual` above bites
    expect(PILL.info).not.toBe(PILL.ok);
  });

  it('shows a status the column cannot hold as its own key, muted — absent beats faked', () => {
    const [row] = rows([item({ license_status: 'pending_counsel' })]);
    expect(row[2].pill).toBe('pending_counsel');
    expect(row[2].pillStyle).toBe(PILL.mute);
  });

  it('offers View terms — and nothing else — where a licence URL is recorded', () => {
    const [row] = rows([ACS]);
    expect(row[3].hasActions).toBe(true);
    expect(row[3].actions.map((a) => a.label)).toEqual(['View terms']);
    expect(row[3].actions[0].style).toBe(VIEW_TERMS_STYLE);
  });

  it('renders NO action at all where there is no URL to open (controller ruling 18)', () => {
    // "Assign review" and "Open question" were the design's own buttons on exactly these two
    // rows and neither called anything; A38.4/A38.5 removed them from the design. A row with no
    // recorded terms page therefore offers nothing, rather than a button that does nothing.
    const [row] = rows([item({ license_status: 'blocked', license_url: null })]);
    expect(row[3].hasActions).toBe(false);
    expect(row[3].actions).toEqual([]);
  });

  it('opens the recorded terms page in a new tab, with noopener', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    const [row] = rows([ACS]);
    await row[3].actions[0].go();
    expect(open).toHaveBeenCalledWith(ACS.license_url, '_blank', 'noopener');
  });
});

describe('the badge count — rows the VIN Foundation has not cleared (controller ruling)', () => {
  it('counts every row whose licence status is not `cleared`', () => {
    expect(notCleared([
      item({ license_status: 'cleared' }), item({ license_status: 'unresolved' }),
      item({ license_status: 'blocked' }), item({ license_status: 'cleared' })
    ])).toBe(2);
  });

  it('is zero for a registry with nothing outstanding, and zero for no rows at all', () => {
    expect(notCleared([item({ license_status: 'cleared' })])).toBe(0);
    expect(notCleared([])).toBe(0);
  });
});

describe('the design-fixture arm — what the pixel oracle is answered with', () => {
  const designRow: DesignDataSourceRow = {
    dataset_key: 'design-fixture-4', license_status: 'unresolved',
    dataset: DESIGN[3][0].main, datasetSub: DESIGN[3][0].sub,
    source: DESIGN[3][1].main, sourceSub: DESIGN[3][1].sub,
    pill: DESIGN[3][2].pill, pillStyle: DESIGN[3][2].pillStyle,
    actions: []
  };

  it('reproduces the design\'s own row byte for byte, styles included', () => {
    const [row] = rows([designRow]);
    expect(row[0]).toEqual(DESIGN[3][0]);
    expect(row[1]).toEqual(DESIGN[3][1]);
    expect(row[2]).toEqual(DESIGN[3][2]);
  });

  it('carries a fixture row\'s own action styles rather than re-deriving them', () => {
    const withTerms: DesignDataSourceRow = {
      ...designRow, license_status: 'cleared',
      dataset: DESIGN[0][0].main, datasetSub: DESIGN[0][0].sub,
      source: DESIGN[0][1].main, sourceSub: DESIGN[0][1].sub,
      pill: DESIGN[0][2].pill, pillStyle: DESIGN[0][2].pillStyle,
      actions: DESIGN[0][3].actions.map((a) => ({ label: a.label, style: a.style }))
    };
    const [row] = rows([withTerms]);
    expect(row[3].hasActions).toBe(true);
    expect(row[3].actions.map((a) => ({ label: a.label, style: a.style }))).toEqual(withTerms.actions);
    // A design fixture's button is the design's own no-op; it opens nothing.
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    return row[3].actions[0].go().then(() => expect(open).not.toHaveBeenCalled());
  });

  it('counts a design fixture exactly as it counts a registry row', () => {
    expect(notCleared([designRow])).toBe(1);
  });
});

describe('PILLS is the design\'s own vocabulary for `dataset_registry.license_status`', () => {
  it('names all three values the column\'s CHECK constraint allows', () => {
    expect(Object.keys(PILLS).sort()).toEqual(['blocked', 'cleared', 'unresolved']);
  });

  it('uses the words the approved design prints, in the design\'s own tones', () => {
    expect(PILLS.cleared[0]).toBe(DESIGN[0][2].pill);
    expect(PILLS.unresolved[0]).toBe(DESIGN[3][2].pill);
    expect(PILLS.blocked[0]).toBe(DESIGN[4][2].pill);
  });
});

describe('cell() and A() really are logic.js\'s own, all three tones and all five (M6 pattern)', () => {
  // This tab draws ONE untoned button, so `toDataSourceRows` alone can never exercise `A()`'s
  // primary and danger arms — and the whole point of the third verbatim copy is that a drift on
  // either side fails HERE rather than being covered for by `admin/users.ts`'s copy. So both arms
  // are compared against the design's own computed buttons on the tabs that draw them.
  const USERS = designCells('users');

  it('reproduces the design\'s primary, danger and untoned buttons byte for byte', () => {
    const go = () => Promise.resolve();
    expect(A('Approve', 'primary', go).style).toBe(USERS[0][3].actions[0].style);
    expect(A('Decline', 'danger', go).style).toBe(USERS[0][3].actions[1].style);
    expect(A('Request info', undefined, go).style).toBe(USERS[2][3].actions[0].style);
  });

  it('reproduces every pill tone the design has, the two this tab never draws included', () => {
    expect(cell(null, null, 'Pending', 'warn').pillStyle).toBe(PILL.warn);
    expect(cell(null, null, 'Paused', 'info').pillStyle).toBe(PILL.info);
    expect(cell(null, null, 'Cleared', 'ok').pillStyle).toBe(PILL.ok);
    expect(cell(null, null, 'Blocked', 'bad').pillStyle).toBe(PILL.bad);
    expect(cell(null, null, 'Anything').pillStyle).toBe(PILL.mute);
  });
});

describe('makeAdminDataSourcesAdapter, against the real fetch boundary', () => {
  interface Call { url: string; init: { method: string; credentials: string; headers: Record<string, string> } }

  function stubFetch(answer: { status: number; body?: unknown }): Call[] {
    const calls: Call[] = [];
    vi.stubGlobal('fetch', (url: string, init: Call['init']) => {
      calls.push({ url, init });
      return Promise.resolve({ ok: answer.status >= 200 && answer.status < 300, status: answer.status, json: () => Promise.resolve(answer.body) });
    });
    return calls;
  }

  beforeEach(() => { document.cookie = 'pm_csrf=tok123'; });
  afterEach(() => vi.unstubAllGlobals());

  it('reads the whole registry in one request and counts what is not cleared', async () => {
    const calls = stubFetch({ status: 200, body: [ACS, item({ dataset_key: 'pet_ownership', license_status: 'blocked', license_url: null })] });
    const { rows, count } = await makeAdminDataSourcesAdapter().list();
    expect(rows).toHaveLength(2);
    expect(rows[0][0].main).toBe('ACS 5-Year Detailed Tables');
    expect(count).toBe('1');
    // One request: the route answers the whole registry ordered by key, with no cursor to follow.
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('/api/admin/data-sources');
    expect(calls[0].init.method).toBe('GET');
    expect(calls[0].init.credentials).toBe('same-origin');
  });

  // A38 fix round 1 (review M4): a READ carries neither header. `admin/listings.ts`'s own `send`
  // and `auth/api.ts` both gate them on `method !== 'GET'`, for the reason `auth/api.ts` records —
  // `check_origin_and_csrf` returns early on GET/HEAD/OPTIONS, so the token is never checked, and
  // sending it anyway is a value the server would refuse if it were ever empty. This module claims
  // to be those two copied verbatim, so it behaves like them.
  it('sends no CSRF token and no Content-Type on the read, as both siblings do', async () => {
    const calls = stubFetch({ status: 200, body: [] });
    await makeAdminDataSourcesAdapter().list();
    expect(calls[0].init.headers ?? {}).toEqual({});
  });

  it('rejects when the registry cannot be read — which empties the tab, never falls back', async () => {
    stubFetch({ status: 403 });
    await expect(makeAdminDataSourcesAdapter().list()).rejects.toThrow('could not be read');
  });

  it('rejects a body that is not the array the route answers', async () => {
    stubFetch({ status: 200, body: { items: [] } });
    await expect(makeAdminDataSourcesAdapter().list()).rejects.toThrow('no rows');
  });
});
