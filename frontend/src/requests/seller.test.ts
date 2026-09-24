// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApiRequestRow } from './buyer';
import { RequestError, makeSellerRequestsAdapter } from './seller';

interface Call { url: string; init: { method: string; credentials: string; headers: Record<string, string>; body?: string } }

function fakeFetch(...answers: Array<{ status: number; body?: unknown; badJson?: boolean }>): { fn: typeof fetch; calls: Call[] } {
  const calls: Call[] = [];
  let n = 0;
  const fn = (vi.fn(async (url: RequestInfo | URL, init: Call['init']) => {
    calls.push({ url: String(url), init });
    const a = answers[Math.min(n++, answers.length - 1)];
    return {
      ok: a.status >= 200 && a.status < 300,
      status: a.status,
      json: () => (a.badJson ? Promise.reject(new SyntaxError('not JSON')) : Promise.resolve(a.body))
    } as unknown as Response;
  })) as unknown as typeof fetch;
  return { fn, calls };
}

const ROW = (over: Partial<ApiRequestRow> = {}): ApiRequestRow => ({
  id: 'r1', listing_id: 'p1', buyer_user_id: 'b1', status: 'PENDING',
  message: 'Would like to see the last three years of production by doctor.', requested_disclosure_level: 'FULL_CONFIDENTIAL',
  approved_capabilities: null, requested_at: '2026-08-21T10:00:00Z', reviewed_at: null,
  denial_reason: null, ...over
});

beforeEach(() => { document.cookie = 'pm_csrf=tok'; });
afterEach(() => { document.cookie = 'pm_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT'; });

describe('makeSellerRequestsAdapter', () => {
  it('inbox() reads /api/seller/requests with no CSRF header and no body, mapping every row', async () => {
    const { fn, calls } = fakeFetch({ status: 200, body: [ROW({ id: 'r1', status: 'PENDING' }), ROW({ id: 'r2', status: 'APPROVED' })] });
    const adapter = makeSellerRequestsAdapter(fn);
    const result = await adapter.inbox();
    expect(calls[0].url).toBe('/api/seller/requests');
    expect(calls[0].init.method).toBe('GET');
    expect(calls[0].init.headers['X-CSRF-Token']).toBeUndefined();
    expect(calls[0].init.headers['Content-Type']).toBeUndefined();
    // Neither ROW() here sets `buyer_name` (an older payload shape, or the API's own fallback
    // path finding nothing to prefer) — the design's UUID-carrying default, unchanged.
    expect(result.map((r) => ({ id: r.id, status: r.status, buyer: r.buyer }))).toEqual([
      { id: 'r1', status: 'pending', buyer: 'b1' },
      { id: 'r2', status: 'accepted', buyer: 'b1' }
    ]);
  });

  it('inbox() shows the buyer\'s served identity instead of the UUID, directive §5 (buyer identity)', async () => {
    const { fn } = fakeFetch({
      status: 200,
      body: [ROW({ id: 'r1', buyer_user_id: 'b1', buyer_name: 'Dr. Rachel Mendes' })]
    });
    const adapter = makeSellerRequestsAdapter(fn);
    const result = await adapter.inbox();
    expect(result[0].buyer).toBe('Dr. Rachel Mendes');
  });

  it('decide() posts the bare action to approve, with the CSRF header', async () => {
    const { fn, calls } = fakeFetch({ status: 200, body: ROW({ status: 'APPROVED' }) });
    const adapter = makeSellerRequestsAdapter(fn);
    const result = await adapter.decide('r1', 'approve');
    expect(calls[0].url).toBe('/api/seller/requests/r1/decide');
    expect(calls[0].init.method).toBe('POST');
    expect(calls[0].init.headers['X-CSRF-Token']).toBe('tok');
    expect(calls[0].init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(calls[0].init.body!)).toEqual({ action: 'approve' });
    expect(result.status).toBe('accepted');
  });

  it('decide() includes disclosure_capabilities and reason only when given', async () => {
    const { fn, calls } = fakeFetch(
      { status: 200, body: ROW({ status: 'APPROVED', approved_capabilities: ['FINANCIALS', 'FLOOR_PLANS'] }) },
      { status: 200, body: ROW({ status: 'DENIED', denial_reason: 'Under contract with another buyer.' }) }
    );
    const adapter = makeSellerRequestsAdapter(fn);
    await adapter.decide('r1', 'approve', ['FINANCIALS', 'FLOOR_PLANS']);
    expect(JSON.parse(calls[0].init.body!)).toEqual({ action: 'approve', disclosure_capabilities: ['FINANCIALS', 'FLOOR_PLANS'] });
    const denied = await adapter.decide('r1', 'deny', undefined, 'Under contract with another buyer.');
    expect(JSON.parse(calls[1].init.body!)).toEqual({ action: 'deny', reason: 'Under contract with another buyer.' });
    expect(denied.reply).toBe('Under contract with another buyer.');
  });

  // A53 (John's ruling, 2026-09-19): REVOKED reads as the design's own fourth word, `"revoked"`,
  // in the seller's own re-read inbox row too — not `"declined"`, which would misreport the
  // seller's own action back to them.
  it('revoke() posts an empty JSON body to .../revoke, with the CSRF header', async () => {
    const { fn, calls } = fakeFetch({ status: 200, body: ROW({ status: 'REVOKED' }) });
    const adapter = makeSellerRequestsAdapter(fn);
    const result = await adapter.revoke('r1');
    expect(calls[0].url).toBe('/api/seller/requests/r1/revoke');
    expect(calls[0].init.method).toBe('POST');
    expect(calls[0].init.headers['X-CSRF-Token']).toBe('tok');
    expect(JSON.parse(calls[0].init.body!)).toEqual({});
    expect(result.status).toBe('revoked');
  });

  it('a refusal with the A5 envelope becomes a RequestError carrying the server\'s own code and message', async () => {
    const { fn } = fakeFetch({ status: 409, body: { error: { code: 'STATE', message: 'This request is approved, not pending.' } } });
    const adapter = makeSellerRequestsAdapter(fn);
    await expect(adapter.decide('r1', 'approve')).rejects.toMatchObject(
      { name: 'RequestError', code: 'STATE', message: 'This request is approved, not pending.' }
    );
    await expect(adapter.decide('r1', 'approve')).rejects.toBeInstanceOf(RequestError);
  });

  it('a refusal with no parseable body still becomes a RequestError, never a raw SyntaxError', async () => {
    const { fn } = fakeFetch({ status: 502, badJson: true });
    const adapter = makeSellerRequestsAdapter(fn);
    await expect(adapter.revoke('r1')).rejects.toMatchObject({ code: 'UNKNOWN', message: 'HTTP 502' });
  });

  it('defaults to the real global fetch when no fetchFn is given', () => {
    expect(() => makeSellerRequestsAdapter()).not.toThrow();
  });
});

// --- D-C67 (John, 2026-09-24): the seller chooses WHICH capabilities this buyer receives --------

describe('makeSellerRequestsAdapter and the per-capability grant', () => {
  it('sends an EMPTY array as a real decision rather than dropping it', async () => {
    // THE OUTCOME D-C67 RULES ON, and NOT the fail-closed seam — the rationale this comment
    // carried was wrong and is corrected rather than deleted (fix round 1, review Minor-1). It
    // said `...(capabilities ? {...} : {})` would omit an empty array. It would not: `[]` is
    // TRUTHY in JavaScript, so that spelling includes the key and this case passes identically
    // under both. The seam the two spellings actually differ on is `null`, which is the test below
    // this one. `logic.test.ts` has stated this correctly since it was written, and the two files
    // disagreed until now; the Python twin
    // (`test_approve_with_an_empty_array_releases_nothing_over_the_wire`) IS a real fail-closed
    // gate, because `[]` really is falsy there.
    //
    // The assertion stays exactly as it was: what must remain true is that an empty set reaches
    // the wire as a decision, whatever a later refactor spells the guard.
    const { fn, calls } = fakeFetch({ status: 200, body: ROW({ status: 'APPROVED', approved_capabilities: [] }) });
    const adapter = makeSellerRequestsAdapter(fn);
    const row = await adapter.decide('r1', 'approve', []);
    expect(JSON.parse(calls[0].init.body!)).toEqual({ action: 'approve', disclosure_capabilities: [] });
    expect(row.granted).toEqual([]);
    expect(row.grantedLabel).toBe('You approved this buyer and released nothing.');
  });

  it('sends a null set as null, so the route refuses it rather than defaulting to everything', async () => {
    // The direction `!== undefined` actually buys over truthiness — an empty array is truthy in
    // JavaScript, so the two spellings agree about `[]` and disagree only here. `chooseAccess`
    // answers `string[] | null`, so this is the value a caller reaches by forwarding a dismissal.
    const { fn, calls } = fakeFetch({ status: 400, body: { error: { code: 'BAD_LEVEL', message: 'no' } } });
    const adapter = makeSellerRequestsAdapter(fn);
    await expect(adapter.decide('r1', 'approve', null as unknown as string[])).rejects.toThrow();
    expect(JSON.parse(calls[0].init.body!)).toEqual({ action: 'approve', disclosure_capabilities: null });
  });

  it('sends NO set at all when the caller names none, which is the API default arm', async () => {
    const { fn, calls } = fakeFetch({ status: 200, body: ROW({ status: 'APPROVED', approved_capabilities: ['IDENTITY'] }) });
    const adapter = makeSellerRequestsAdapter(fn);
    await adapter.decide('r1', 'approve');
    expect(JSON.parse(calls[0].init.body!)).toEqual({ action: 'approve' });
  });

  it('carries what the buyer holds, and the sentence naming it, onto the design row', async () => {
    const { fn } = fakeFetch({ status: 200, body: [ROW({ status: 'APPROVED', approved_capabilities: ['FLOOR_PLANS', 'FINANCIALS'] })] });
    const [row] = await makeSellerRequestsAdapter(fn).inbox();
    expect(row.granted).toEqual(['FINANCIALS', 'FLOOR_PLANS']);
    expect(row.grantedLabel).toBe('You released financials and floor plans to this buyer.');
  });

  it('carries NOTHING onto a row that has had no decision, so the design keeps its own sentence', async () => {
    const { fn } = fakeFetch({ status: 200, body: [ROW({ status: 'PENDING', approved_capabilities: null })] });
    const [row] = await makeSellerRequestsAdapter(fn).inbox();
    // `undefined`, never `[]`: an empty array here would make "released nothing" true of a request
    // the seller has not answered yet.
    expect(row.granted).toBeUndefined();
    expect(row.grantedLabel).toBeUndefined();
  });
});

describe('makeSellerRequestsAdapter().chooseAccess', () => {
  afterEach(() => { document.body.innerHTML = ''; });

  it('opens the composed chooser with the buyer named, the five capabilities offered and what they hold pre-ticked', async () => {
    const adapter = makeSellerRequestsAdapter(fakeFetch().fn);
    const promise = adapter.chooseAccess('Dr. Rachel Mendes', ['FINANCIALS'], 'Change access');
    expect(document.body.textContent).toContain('Dr. Rachel Mendes');
    // The wizard step 7 blurb, verbatim — this product's own sentence for exactly this decision.
    expect(document.body.textContent).toContain('You decide what an approved buyer sees before you have spoken to them.');
    const boxes = [...document.querySelectorAll('input[type="checkbox"]')] as HTMLInputElement[];
    expect(boxes.map((b) => b.value)).toEqual(['IDENTITY', 'EXACT_LOCATION', 'UNREDACTED_IMAGES', 'FINANCIALS', 'FLOOR_PLANS']);
    expect(boxes.filter((b) => b.checked).map((b) => b.value)).toEqual(['FINANCIALS']);
    // `FULL_CONFIDENTIAL` is never offered: it is a level a BUYER may ask for, not a capability a
    // grant may store (`migrations/097_request_approved_capabilities.sql`'s own CHECK).
    expect(document.body.textContent).not.toContain('Full confidential');

    const floorPlans = boxes[4];
    floorPlans.checked = true; floorPlans.dispatchEvent(new Event('change'));
    const submit = [...document.querySelectorAll('button')].find((b) => b.textContent === 'Change access')!;
    submit.click();
    await expect(promise).resolves.toEqual(['FINANCIALS', 'FLOOR_PLANS']);
  });

  it('answers null when the seller dismisses it, and asks the server nothing either way', async () => {
    const { fn, calls } = fakeFetch();
    const promise = makeSellerRequestsAdapter(fn).chooseAccess('Dr. Rachel Mendes', [], 'Share more');
    ([...document.querySelectorAll('button')].find((b) => b.textContent === 'Cancel') as HTMLButtonElement).click();
    await expect(promise).resolves.toBeNull();
    expect(calls).toEqual([]);
  });
});
