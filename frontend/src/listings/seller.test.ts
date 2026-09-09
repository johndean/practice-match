// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Component } from '../logic.js';
import { designWizardDraft, designWizardTiles } from '../../tests/design-wizard-draft.mjs';
import {
  ListingError,
  MAX_PAGES,
  makeListingsAdapter,
  money,
  toDashboardRow,
  toWizardState,
  type Draft
} from './seller';

interface Call { url: string; init: { method: string; credentials: string; headers: Record<string, string>; body?: unknown } }

/** The network boundary and nothing else — `src/auth/api.test.ts`'s own stub, unchanged. */
function stubFetch(...answers: Array<{ status: number; body?: unknown; text?: string }>): Call[] {
  const calls: Call[] = [];
  let n = 0;
  vi.stubGlobal('fetch', (url: string, init: Call['init']) => {
    calls.push({ url, init });
    const a = answers[Math.min(n++, answers.length - 1)];
    return Promise.resolve({
      ok: a.status >= 200 && a.status < 300,
      status: a.status,
      json: () => ('text' in a ? Promise.reject(new SyntaxError('not JSON')) : Promise.resolve(a.body))
    });
  });
  return calls;
}

/** A draft as `app/api/seller_listings.py::serialise_draft` sends it, with every key present. */
function draft(over: Partial<Draft> = {}): Draft {
  return {
    id: 'a3f1', slug: 'listing-a3f1', status: 'draft',
    name: null, type: null, est: null, ownership: null, city: null, zip: null,
    price: null, rev: null, docs: null, rooms: null, sqft: null, hours: null, desc: null,
    bldg: null, facilityType: null, facility: null,
    anon: true, revBand: false, docsLocked: true,
    state: null, market: null, area: null,
    decline_reason: null, submitted_at: null, updated_at: '2026-09-08T10:00:00Z',
    assets: [], photos: [], documents: [],
    ...over
  };
}

beforeEach(() => {
  document.cookie = 'pm_csrf=tok';
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = 'pm_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

describe('money', () => {
  it('is the design\'s own money(), value for value', () => {
    // Ported from logic.js:251 rather than imported: `money` is a method on the prototype's
    // Component and the mapping below is a pure function. This pins the port against the
    // original for every branch it has, so the copy cannot drift.
    const design = new Component({});
    for (const n of [null, '', 0, 999, 1000, 12_345, 999_999, 1_000_000, 1_450_000, 9_999_999, 10_000_000, 123_000_000]) {
      expect(money(n as number | null)).toBe(design.money(n));
    }
  });
});

describe('toDashboardRow', () => {
  it("renders the design's own three strings", () => {
    expect(toDashboardRow(draft({
      id: 'a3f1', status: 'published', name: 'Cedar Park Animal Hospital', city: 'Cedar Park',
      type: 'Small animal', price: 1_450_000, docs: 3, sqft: 4200
    }))).toEqual({
      id: 'a3f1', status: 'published',
      title: 'Small animal practice — Cedar Park',
      meta: '$1.45M · 3 doctors · 4,200 sq ft',
      note: 'Live · visible in search'
    });
  });

  it("names an untitled draft the design's own way and says what a listing with no figures is", () => {
    // "Untitled listing" and "Price to be set" are both the design's own words (logic.js:209 and
    // the submit handler at logic.js:1236); nothing here is invented copy.
    expect(toDashboardRow(draft())).toMatchObject({ title: 'Untitled listing', meta: 'Price to be set', note: 'Draft' });
  });

  it('writes one note per lifecycle state and never a count no column supplies (A-SL2)', () => {
    const note = (status: string, over: Partial<Draft> = {}) => toDashboardRow(draft({ status, ...over })).note;
    expect(note('published')).toBe('Live · visible in search');
    expect(note('in_review')).toBe('Submitted · awaiting VIN Foundation review');
    expect(note('draft')).toBe('Draft');
    expect(note('paused')).toBe('Paused by you · hidden from search');
    expect(note('withdrawn')).toBe('Withdrawn');
    expect(note('declined')).toBe('Declined · edit and re-submit');
  });

  it("puts the reviewer's reason under the Declined pill and nowhere else (A-SL19 Info-3)", () => {
    expect(toDashboardRow(draft({ status: 'declined', decline_reason: 'Add the 2025 tax return.' })).note)
      .toBe('Add the 2025 tax return.');
    // The reason survives a later publish, so every other pill keeps its own prose.
    expect(toDashboardRow(draft({ status: 'published', decline_reason: 'Add the 2025 tax return.' })).note)
      .toBe('Live · visible in search');
  });

  it("calls a listing with a community but no practice type the design's own default", () => {
    // `state.w` starts at `type: "Small animal"` (logic.js:204), so that is the design's own word
    // for a practice whose type nobody has chosen — and a status outside the lifecycle table
    // falls back to `draft` exactly as the design's own `map[status] || map.draft` does.
    expect(toDashboardRow(draft({ city: 'Bastrop' })).title).toBe('Small animal practice — Bastrop');
    expect(toDashboardRow(draft({ status: 'flagged' })).note).toBe('Draft');
  });

  it('leaves out a figure the seller has not given', () => {
    expect(toDashboardRow(draft({ price: 860_000, docs: 2 })).meta).toBe('$860K · 2 doctors');
    expect(toDashboardRow(draft({ sqft: 3000 })).meta).toBe('Price to be set · 3,000 sq ft');
    expect(toDashboardRow(draft({ docs: 1 })).meta).toBe('Price to be set · 1 doctor');
  });

  it('groups the square feet the same way in every locale (A-SL23 (6) m1)', () => {
    // `toLocaleString()` with no locale reads the BROWSER's, so a seller on de-DE saw `4.200 sq
    // ft` and one on fr-FR `4 200 sq ft`, while the design's own fixture — and the pixel oracle —
    // say `4,200`. Every other value in this mapping is a deterministic port of the design's own
    // `money()`; this one is now too (SL7 review, Minor-1).
    const group = vi.spyOn(Number.prototype, 'toLocaleString').mockReturnValue('4.200');
    expect(toDashboardRow(draft({ sqft: 4200 })).meta).toBe('Price to be set · 4,200 sq ft');
    expect(group, 'the mapping must not consult the browser locale at all').not.toHaveBeenCalled();
    vi.restoreAllMocks();
    expect(toDashboardRow(draft({ sqft: 1_234_567 })).meta).toBe('Price to be set · 1,234,567 sq ft');
    expect(toDashboardRow(draft({ sqft: 999 })).meta).toBe('Price to be set · 999 sq ft');
    expect(toDashboardRow(draft({ sqft: 1000 })).meta).toBe('Price to be set · 1,000 sq ft');
  });
});

describe('toWizardState', () => {
  it("maps a draft onto state.w's own key names, as strings the design's fields can edit", () => {
    expect(toWizardState(draft({
      name: 'ABC Animal Hospital', type: 'Mixed', est: 1998, ownership: 'Multi-doctor LLC',
      city: 'Bastrop', zip: '78602', price: 860_000, rev: 700_000, docs: 2, rooms: 4, sqft: 3000,
      hours: 'Mon-Fri', desc: 'Dentistry', bldg: 'Leased', facilityType: 'Medical park',
      facility: 'Two surgical suites', anon: false, revBand: true, docsLocked: false, state: 'TX'
    }))).toEqual({
      name: 'ABC Animal Hospital', type: 'Mixed', est: '1998', ownership: 'Multi-doctor LLC',
      city: 'Bastrop', zip: '78602', price: '860000', rev: '700000', docs: '2', rooms: '4', sqft: '3000',
      hours: 'Mon-Fri', desc: 'Dentistry', bldg: 'Leased', facilityType: 'Medical park',
      facility: 'Two surgical suites', anon: false, revBand: true, docsLocked: false, state: 'TX'
    });
  });

  it('turns every absent column into the empty string the design\'s own initial `w` holds', () => {
    expect(toWizardState(draft())).toEqual({
      name: '', type: '', est: '', ownership: '', city: '', zip: '', price: '', rev: '', docs: '',
      rooms: '', sqft: '', hours: '', desc: '', bldg: '', facilityType: '', facility: '',
      anon: true, revBand: false, docsLocked: true, state: ''
    });
  });
});

describe('the adapter', () => {
  const api = () => makeListingsAdapter();

  it('list() maps every draft to the design\'s own dashboard row shape', async () => {
    const calls = stubFetch({ status: 200, body: { items: [draft({ id: 'x', status: 'paused' })], next_cursor: null } });
    expect(await api().list()).toEqual([{
      id: 'x', status: 'paused', title: 'Untitled listing', meta: 'Price to be set',
      note: 'Paused by you · hidden from search'
    }]);
    expect(calls[0].url).toBe('/api/seller/listings?limit=200');
    expect(calls[0].init.method).toBe('GET');
    expect(calls[0].init.headers['X-CSRF-Token']).toBeUndefined();
  });

  it('list() rejects rather than installing an empty dashboard when the answer is not a page (A-L6.2 (1))', async () => {
    // A-SL22 (1): a LOADED empty array is a real answer and empties the dashboard, so "no
    // answer" cannot be spelled the same way. A body with no `items` array is not a page.
    stubFetch({ status: 200, body: { next_cursor: null } });
    await expect(api().list()).rejects.toThrow('The listings could not be read.');
  });

  it('list() rejects a refusal with the server\'s own message', async () => {
    stubFetch({ status: 429, body: { error: { code: 'RATE_LIMITED', message: 'Too many requests.' } } });
    await expect(api().list()).rejects.toThrow('Too many requests.');
  });

  it('create() returns the new id', async () => {
    const calls = stubFetch({ status: 201, body: { id: 'new-1' } });
    expect(await api().create()).toBe('new-1');
    expect(calls[0].init.method).toBe('POST');
  });

  it('get() hands the wizard its state and its tiles', async () => {
    stubFetch({ status: 200, body: draft({
      id: 'a3f1', city: 'Bastrop',
      photos: [{ id: 'p1', name: 'Front door in the morning' }, { id: 'p2', name: '' }],
      documents: [{ id: 'd1', kind: 'other', name: 'Floor plan.pdf', content_type: 'application/pdf', byte_size: 10, url: '/x' }]
    }) });
    expect(await api().get('a3f1')).toEqual({
      w: expect.objectContaining({ city: 'Bastrop' }),
      assets: [
        { kind: 'Photo', name: 'Front door in the morning', id: 'p1' },
        { kind: 'Photo', name: '', id: 'p2' },
        { kind: 'PDF', name: 'Floor plan.pdf', id: 'd1' }
      ]
    });
  });

  it('get() badges a document with its own uppercased extension (spec Q3)', async () => {
    stubFetch({ status: 200, body: draft({ documents: [
      { id: 'd1', kind: 'financials', name: 'P&L.csv', content_type: 'text/csv', byte_size: 1, url: '/x' },
      { id: 'd2', kind: 'other', name: 'Equipment.xlsx', content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', byte_size: 1, url: '/x' },
      { id: 'd3', kind: 'other', name: 'no-extension', content_type: 'application/pdf', byte_size: 1, url: '/x' }
    ] }) });
    expect((await api().get('a3f1')).assets.map((a) => a.kind)).toEqual(['CSV', 'XLSX', 'PDF']);
  });

  it('patch() sends the step in the query and only the fields it was given', async () => {
    const calls = stubFetch({ status: 200, body: draft({ city: 'Buda' }) });
    const answer = await api().patch('a3f1', 2, { city: 'Buda', zip: '78610' });
    expect(calls[0].url).toBe('/api/seller/listings/a3f1?step=2');
    expect(calls[0].init.method).toBe('PATCH');
    expect(calls[0].init.headers['X-CSRF-Token']).toBe('tok');
    expect(calls[0].init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ city: 'Buda', zip: '78610' });
    expect(answer.w.city).toBe('Buda');
  });

  it("patch() surfaces the server's own message and code", async () => {
    stubFetch({ status: 422, body: { error: { code: 'BAD_FIELD', message: 'est must be a year.' } } });
    await expect(api().patch('a3f1', 1, { est: 'soon' })).rejects.toMatchObject({
      name: 'ListingError', code: 'BAD_FIELD', message: 'est must be a year.'
    });
  });

  it('a refusal that is not the A5 envelope still becomes an Error with a message', async () => {
    stubFetch({ status: 502, text: 'a proxy said no' });
    await expect(api().submit('a3f1')).rejects.toMatchObject({ code: 'UNKNOWN', message: 'HTTP 502' });
  });

  it('upload() posts multipart with the CSRF header and no Content-Type of its own', async () => {
    const calls = stubFetch({ status: 201, body: { id: 'as-1', kind: 'photo', name: 'x.jpg', content_type: 'image/webp', byte_size: 9 } });
    const file = new File([new Uint8Array([1])], 'x.jpg', { type: 'image/jpeg' });
    expect(await api().upload('a3f1', file)).toMatchObject({ id: 'as-1' });
    expect(calls[0].url).toBe('/api/seller/listings/a3f1/photos');
    expect(calls[0].init.headers['X-CSRF-Token']).toBe('tok');
    // The browser must set the multipart boundary; a Content-Type here would break the parser.
    expect(calls[0].init.headers['Content-Type']).toBeUndefined();
    const body = calls[0].init.body as FormData;
    expect((body.get('file') as File).name).toBe('x.jpg');
  });

  it('document() defaults its kind to other (D18 — the approved step 6 has no picker)', async () => {
    const calls = stubFetch({ status: 201, body: { id: 'as-2' } });
    await api().document('a3f1', new File([new Uint8Array([1])], 'p.pdf', { type: 'application/pdf' }));
    expect(calls[0].url).toBe('/api/seller/listings/a3f1/documents');
    expect((calls[0].init.body as FormData).get('kind')).toBe('other');
    await api().document('a3f1', new File([new Uint8Array([1])], 'p.pdf', { type: 'application/pdf' }), 'financials');
    expect((calls[1].init.body as FormData).get('kind')).toBe('financials');
  });

  it('caption() sends the seller\'s own words for one photograph (A-SL20)', async () => {
    const calls = stubFetch({ status: 200, body: draft() });
    await api().caption('a3f1', 'as-1', 'Reception, looking in');
    expect(calls[0].url).toBe('/api/seller/listings/a3f1/assets/as-1');
    expect(calls[0].init.method).toBe('PATCH');
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ caption: 'Reception, looking in' });
  });

  it('remove() deletes one asset and reads nothing back', async () => {
    const calls = stubFetch({ status: 204, text: 'no content' });
    await api().remove('a3f1', 'as-1');
    expect(calls[0].url).toBe('/api/seller/listings/a3f1/assets/as-1');
    expect(calls[0].init.method).toBe('DELETE');
  });

  it('reorder() sends the full ordered list', async () => {
    const calls = stubFetch({ status: 200, body: draft() });
    await api().reorder('a3f1', ['b', 'a']);
    expect(calls[0].url).toBe('/api/seller/listings/a3f1/photos');
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ ids: ['b', 'a'] });
  });

  it('submit() posts the wizard\'s own Submit for review', async () => {
    const calls = stubFetch({ status: 200, body: draft({ status: 'in_review' }) });
    expect((await api().submit('a3f1')).w).toBeDefined();
    expect(calls[0].url).toBe('/api/seller/listings/a3f1/submit');
    expect(calls[0].init.method).toBe('POST');
  });

  it('setStatus() sends the dashboard\'s own three actions and refuses a fourth', async () => {
    const calls = stubFetch({ status: 200, body: draft() });
    for (const action of ['pause', 'republish', 'withdraw'] as const) await api().setStatus('a3f1', action);
    expect(calls.map((c) => JSON.parse(String(c.init.body)).action)).toEqual(['pause', 'republish', 'withdraw']);
    expect(calls[0].url).toBe('/api/seller/listings/a3f1/status');
    await expect(api().setStatus('a3f1', 'delete' as 'pause')).rejects.toThrow('delete is not one of pause, republish, withdraw.');
    expect(calls).toHaveLength(3);
  });

  it('pick() opens a real file dialog and resolves with the file, or null when it is dismissed', async () => {
    const inputs: HTMLInputElement[] = [];
    vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
      const el = Object.getPrototypeOf(document).createElement.call(document, tag) as HTMLInputElement;
      if (tag === 'input') inputs.push(el);
      return el;
    }) as typeof document.createElement);
    const chosen = api().pick();
    const file = new File([new Uint8Array([1])], 'x.jpg', { type: 'image/jpeg' });
    Object.defineProperty(inputs[0], 'files', { value: [file] });
    inputs[0].dispatchEvent(new Event('change'));
    expect(await chosen).toBe(file);

    const dismissed = api().pick();
    inputs[1].dispatchEvent(new Event('cancel'));
    expect(await dismissed).toBeNull();
    vi.restoreAllMocks();
  });

  it('pick() treats an empty selection as a dismissal', async () => {
    const inputs: HTMLInputElement[] = [];
    vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
      const el = Object.getPrototypeOf(document).createElement.call(document, tag) as HTMLInputElement;
      if (tag === 'input') inputs.push(el);
      return el;
    }) as typeof document.createElement);
    const chosen = api().pick();
    inputs[0].dispatchEvent(new Event('change'));
    expect(await chosen).toBeNull();
    vi.restoreAllMocks();
  });

  it('describe() asks the seller what the photograph shows, and trims what they say', () => {
    vi.stubGlobal('prompt', vi.fn().mockReturnValueOnce('  Reception, looking in  ').mockReturnValueOnce(null));
    expect(api().describe()).toBe('Reception, looking in');
    expect(api().describe()).toBe('');
  });

  it('is a ListingError with the code every time, so a caller can branch on it', () => {
    expect(new ListingError('STATE', 'no').code).toBe('STATE');
    expect(new ListingError('STATE', 'no').name).toBe('ListingError');
  });

  // --- A-SL23 (7) I1: one page was one page, and the cursor was dropped -------------------
  it('list() follows next_cursor to the end', async () => {
    const calls = stubFetch(
      { status: 200, body: { items: [draft({ id: 'a' })], next_cursor: 'c1' } },
      { status: 200, body: { items: [draft({ id: 'b' })], next_cursor: null } }
    );
    expect((await api().list()).map((r) => r.id)).toEqual(['a', 'b']);
    expect(calls.map((c) => c.url)).toEqual([
      '/api/seller/listings?limit=200',
      '/api/seller/listings?limit=200&cursor=c1'
    ]);
  });

  it('list() stops after MAX_PAGES rather than following a cursor that never ends', async () => {
    const calls = stubFetch({ status: 200, body: { items: [draft()], next_cursor: 'always' } });
    expect(await api().list()).toHaveLength(MAX_PAGES);
    expect(calls).toHaveLength(MAX_PAGES);
  });

  it('list() percent-encodes the cursor it was handed', async () => {
    const calls = stubFetch(
      { status: 200, body: { items: [], next_cursor: 'a b&c' } },
      { status: 200, body: { items: [], next_cursor: null } }
    );
    await api().list();
    expect(calls[1].url).toBe('/api/seller/listings?limit=200&cursor=a%20b%26c');
  });

  // --- A-SL23 (6) m7: the "Add files" button's own promise -------------------------------
  function pickReturns(file: File | null): void {
    const inputs: HTMLInputElement[] = [];
    vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
      const el = Object.getPrototypeOf(document).createElement.call(document, tag) as HTMLInputElement;
      if (tag === 'input') {
        inputs.push(el);
        queueMicrotask(() => {
          if (file) Object.defineProperty(el, 'files', { value: [file] });
          el.dispatchEvent(new Event(file ? 'change' : 'cancel'));
        });
      }
      return el;
    }) as typeof document.createElement);
  }

  it('pick() offers documents as well as photographs (D18\'s three types)', () => {
    const inputs: HTMLInputElement[] = [];
    vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
      const el = Object.getPrototypeOf(document).createElement.call(document, tag) as HTMLInputElement;
      if (tag === 'input') inputs.push(el);
      return el;
    }) as typeof document.createElement);
    void api().pick();
    expect(inputs[0].accept).toBe(
      'image/jpeg,image/png,image/webp,application/pdf,text/csv,'
      + 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    );
    vi.restoreAllMocks();
  });

  it('attach() uploads a photograph, asks what it shows and hands back the refreshed draft', async () => {
    const calls = stubFetch(
      { status: 201, body: { id: 'as-1', kind: 'photo', name: 'x.jpg', content_type: 'image/webp', byte_size: 9 } },
      { status: 200, body: draft({ photos: [{ id: 'as-1', name: 'Reception, looking in' }] }) }
    );
    pickReturns(new File([new Uint8Array([1])], 'x.jpg', { type: 'image/jpeg' }));
    vi.stubGlobal('prompt', vi.fn().mockReturnValue('Reception, looking in'));
    const answer = await api().attach('a3f1');
    expect(answer?.assets).toEqual([{ kind: 'Photo', name: 'Reception, looking in', id: 'as-1' }]);
    expect(calls.map((c) => c.url)).toEqual([
      '/api/seller/listings/a3f1/photos', '/api/seller/listings/a3f1/assets/as-1'
    ]);
    vi.restoreAllMocks();
  });

  it('attach() routes a document to the document route, and never asks it what it shows', async () => {
    const calls = stubFetch(
      { status: 201, body: { id: 'as-2', kind: 'other', name: 'Floor plan.pdf', content_type: 'application/pdf', byte_size: 9 } },
      { status: 200, body: draft({ documents: [{ id: 'as-2', kind: 'other', name: 'Floor plan.pdf', content_type: 'application/pdf', byte_size: 9, url: '/x' }] }) }
    );
    const prompt = vi.fn();
    vi.stubGlobal('prompt', prompt);
    pickReturns(new File([new Uint8Array([1])], 'Floor plan.pdf', { type: 'application/pdf' }));
    const answer = await api().attach('a3f1');
    expect(answer?.assets).toEqual([{ kind: 'PDF', name: 'Floor plan.pdf', id: 'as-2' }]);
    expect(calls.map((c) => c.url)).toEqual([
      '/api/seller/listings/a3f1/documents', '/api/seller/listings/a3f1'
    ]);
    expect((calls[0].init.body as FormData).get('kind')).toBe('other');
    expect(prompt, 'a document is not a photograph and has no caption to write').not.toHaveBeenCalled();
    vi.restoreAllMocks();
  });

  it('attach() resolves with null when the seller dismisses the dialog, and uploads nothing', async () => {
    const calls = stubFetch({ status: 200, body: draft() });
    pickReturns(null);
    expect(await api().attach('a3f1')).toBeNull();
    expect(calls).toHaveLength(0);
    vi.restoreAllMocks();
  });

  it('attach() rejects with the caption refusal, not just the upload one (SL7 review, Major-3)', async () => {
    // Nested handlers made the caption's rejection a sibling of the upload's fulfilment, so a 429
    // on `LISTING_PATCH` escaped as an unhandled rejection and the tile list never refreshed.
    stubFetch(
      { status: 201, body: { id: 'as-1', kind: 'photo', name: 'x.jpg', content_type: 'image/webp', byte_size: 9 } },
      { status: 429, body: { error: { code: 'RATE_LIMITED', message: 'Too many requests.' } } }
    );
    pickReturns(new File([new Uint8Array([1])], 'x.jpg', { type: 'image/jpeg' }));
    vi.stubGlobal('prompt', vi.fn().mockReturnValue('Reception'));
    await expect(api().attach('a3f1')).rejects.toMatchObject({ code: 'RATE_LIMITED' });
    vi.restoreAllMocks();
  });
});

// --- A-SL23 (2): the oracle's own page, and the row that carries its own words ----------------
describe('toDashboardRow on the design\'s own fixture row', () => {
  it('takes the row\'s own words where a row has them', () => {
    // `frontend/tests/design-seller-listings.mjs` serves the DESIGN's four dashboard fixtures as a
    // real page of `/api/seller/listings`, so `seller-dash` reaches its frozen pixels through the
    // SUCCESS path instead of through a rejected load. Their prose is not constructible from any
    // column (A-SL2), so the row carries it — `design-listings.mjs`'s `name: null` again.
    expect(toDashboardRow({
      id: 's1', status: 'published', title: 'Small animal practice — Cedar Park',
      meta: '$1.45M · 3 doctors · 4,200 sq ft', note: 'Live since August 24 · 34 views, 2 requests'
    })).toEqual({
      id: 's1', status: 'published', title: 'Small animal practice — Cedar Park',
      meta: '$1.45M · 3 doctors · 4,200 sq ft', note: 'Live since August 24 · 34 views, 2 requests'
    });
  });

  it('is the identity on every one of the design\'s four rows', () => {
    for (const row of new Component({}).state.sellerListings) expect(toDashboardRow(row)).toEqual(row);
  });

  it('derives all three from the columns for a row the real endpoint sent', () => {
    expect(toDashboardRow(draft({ id: 'x', status: 'draft' }))).toEqual({
      id: 'x', status: 'draft', title: 'Untitled listing', meta: 'Price to be set', note: 'Draft'
    });
  });
});

// --- A-SL25 (1): the oracle's created draft is the design's own wizard, field for field ---------
describe('the design\'s wizard draft (frontend/tests/design-wizard-draft.mjs)', () => {
  it('changes nothing the design\'s own initial `w` holds', () => {
    // A16.14 chains `create → get` and A16.17's `openDraft` lays the draft's values over the
    // DESIGN's initial `w`. `wizard-step-1`, `wizard-preview` and `wizard-done` are frozen
    // screens, so the draft the oracle answers with has to leave that `w` exactly as it was —
    // otherwise the app's three captures diverge from the reference, which renders the literal.
    //
    // Spelled as a merge rather than a bare `toEqual`: `toWizardState` emits `state`, which the
    // design's `w` has no key for (the reviewer supplies it at the first publish, spec Q2), and
    // does not emit `photos`, the design's own fake counter that `openDraft` keeps. So the
    // assertion is the one that matters — applying the draft moves nothing the design declares.
    const w = new Component({}).state.w as Record<string, unknown>;
    const applied = toWizardState(designWizardDraft('wiz-1') as unknown as Draft);
    expect({ ...w, ...applied }).toEqual({ ...w, state: '' });
  });

  it('its photograph tiles are the design\'s own three, through toWizardDraft', async () => {
    // The other half: `get()` maps the draft to what A16.4 renders, so what the app draws on the
    // app project is what `logic.js`'s own fallback literal draws on the reference.
    stubFetch({ status: 200, body: designWizardDraft('wiz-1') });
    expect((await makeListingsAdapter().get('wiz-1')).assets.map((a) => [a.kind, a.name])).toEqual(
      designWizardTiles().map((t: { kind: string; name: string }) => [t.kind, t.name])
    );
  });
});
