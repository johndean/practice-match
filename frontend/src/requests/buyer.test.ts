// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  type ApiRequestRow,
  RequestError,
  formatWhen,
  makeBuyerRequestsAdapter,
  toDesignRow,
  toDesignStatus
} from './buyer';

interface Call { url: string; init: { method: string; credentials: string; headers: Record<string, string>; body?: string } }

/** The network boundary and nothing else — `src/listings/seller.test.ts`'s own `stubFetch`, in
 *  `market/boundaries.test.ts`'s injected-`fetchFn` shape rather than `vi.stubGlobal`'d, since
 *  this module takes the fetcher as a parameter. */
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
  message: 'Interested in a phased transition.', requested_disclosure_level: 'FULL_CONFIDENTIAL',
  approved_capabilities: null, requested_at: '2026-08-29T10:00:00Z', reviewed_at: null,
  denial_reason: null, ...over
});

beforeEach(() => { document.cookie = 'pm_csrf=tok'; });
afterEach(() => { document.cookie = 'pm_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT'; });

describe('toDesignStatus', () => {
  // A53 (John's ruling, 2026-09-19): REVOKED gets its own fourth word rather than collapsing
  // onto DENIED's "declined" — the two states read differently on both the buyer's own surfaces
  // and the seller's own inbox (A53.2/A53.3's honest pill and resolvedNote for their own action).
  it('maps the API\'s four statuses onto the design\'s own four words', () => {
    expect(toDesignStatus('PENDING')).toBe('pending');
    expect(toDesignStatus('APPROVED')).toBe('accepted');
    expect(toDesignStatus('DENIED')).toBe('declined');
    expect(toDesignStatus('REVOKED')).toBe('revoked');
  });
});

describe('formatWhen', () => {
  it('is the design\'s own short date style, in an explicit locale', () => {
    expect(formatWhen('2026-08-29T10:00:00Z')).toBe('Aug 29');
  });
});

describe('toDesignRow', () => {
  it('carries the message and the denial reason through when both are set', () => {
    const row = toDesignRow(ROW({ status: 'DENIED', message: 'Do you expect the team to stay?', denial_reason: 'Under contract with another buyer.' }));
    expect(row).toEqual({
      id: 'r1', pid: 'p1', buyer: 'b1', status: 'declined',
      msg: 'Do you expect the team to stay?', reply: 'Under contract with another buyer.', when: 'Aug 29'
    });
  });

  it('never renders the word "null" for a request with no message or no reply', () => {
    const row = toDesignRow(ROW({ message: null, denial_reason: null }));
    expect(row.msg).toBe('');
    expect(row.reply).toBe('');
  });

  // The e2e oracle's own stub (design-requests.mjs) hands back logic.js's `s.requests` fixture
  // rows verbatim — carrying the design's own ACCEPTED-row reply prose no real column has — and
  // this is the union arm that takes them as they stand, `toDashboardRow`'s own `DesignRow` shape
  // one module over.
  it('takes an already design-shaped row (carrying `pid`) as it stands', () => {
    const designRow = { id: 'r2', pid: 'p7', buyer: 'Dr. Rachel Mendes', status: 'accepted' as const, msg: 'Would like to see the last three years of production by doctor.', reply: 'Happy to share. Financial packet unlocked — call me next week.', when: 'Aug 21' };
    expect(toDesignRow(designRow)).toEqual(designRow);
  });

  it('defaults a design-shaped row\'s missing reply to an empty string, never undefined', () => {
    const designRow = { id: 'r1', pid: 'p1', buyer: 'Dr. Rachel Mendes', status: 'pending' as const, msg: 'Interested in a phased transition.', when: 'Aug 29' };
    expect(toDesignRow(designRow).reply).toBe('');
  });

  // A53: a revoke never sets `denial_reason` (`app/disclosure/requests.py::revoke` touches only
  // `status`), so a revoked row's own reply is empty on the real adapter path — no reply is
  // fabricated for an action the schema has no free-text field for, A52.6's own reasoning one
  // status over.
  it('a revoked row maps to the design\'s own fourth word and carries no fabricated reply', () => {
    const row = toDesignRow(ROW({ status: 'REVOKED', denial_reason: null }));
    expect(row.status).toBe('revoked');
    expect(row.reply).toBe('');
  });
});

describe('makeBuyerRequestsAdapter', () => {
  it('create() posts to /api/requests with the CSRF header and the listing id and message', async () => {
    const { fn, calls } = fakeFetch({ status: 201, body: ROW() });
    const adapter = makeBuyerRequestsAdapter(fn);
    const result = await adapter.create('p1', 'Interested in a phased transition.');
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('/api/requests');
    expect(calls[0].init.method).toBe('POST');
    expect(calls[0].init.credentials).toBe('same-origin');
    expect(calls[0].init.headers['X-CSRF-Token']).toBe('tok');
    expect(calls[0].init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(calls[0].init.body!)).toEqual({ listing_id: 'p1', message: 'Interested in a phased transition.' });
    expect(result.status).toBe('pending');
  });

  it('create() omits message and disclosure_level when neither is given, and includes disclosure_level when it is', async () => {
    const { fn, calls } = fakeFetch({ status: 201, body: ROW() }, { status: 201, body: ROW() });
    const adapter = makeBuyerRequestsAdapter(fn);
    await adapter.create('p1');
    expect(JSON.parse(calls[0].init.body!)).toEqual({ listing_id: 'p1' });
    await adapter.create('p1', 'hello', 'FULL_CONFIDENTIAL');
    expect(JSON.parse(calls[1].init.body!)).toEqual({ listing_id: 'p1', message: 'hello', disclosure_level: 'FULL_CONFIDENTIAL' });
  });

  it('mine() reads /api/requests/mine with no CSRF header and no body, mapping every row', async () => {
    const { fn, calls } = fakeFetch({
      status: 200,
      body: [ROW({ id: 'r1', status: 'PENDING' }), ROW({ id: 'r2', status: 'APPROVED' }), ROW({ id: 'r3', status: 'DENIED', denial_reason: 'Not engaging further.' }), ROW({ id: 'r4', status: 'REVOKED' })]
    });
    const adapter = makeBuyerRequestsAdapter(fn);
    const result = await adapter.mine();
    expect(calls[0].url).toBe('/api/requests/mine');
    expect(calls[0].init.method).toBe('GET');
    expect(calls[0].init.headers['X-CSRF-Token']).toBeUndefined();
    expect(calls[0].init.headers['Content-Type']).toBeUndefined();
    expect(calls[0].init.body).toBeUndefined();
    expect(result.map((r) => r.status)).toEqual(['pending', 'accepted', 'declined', 'revoked']);
    expect(result[2].reply).toBe('Not engaging further.');
  });

  it('a refusal with the A5 envelope becomes a RequestError carrying the server\'s own code and message', async () => {
    const { fn } = fakeFetch({ status: 409, body: { error: { code: 'ALREADY_REQUESTED', message: 'You already have a pending or approved request for this listing.' } } });
    const adapter = makeBuyerRequestsAdapter(fn);
    await expect(adapter.create('p1', 'hi')).rejects.toMatchObject(
      { name: 'RequestError', code: 'ALREADY_REQUESTED', message: 'You already have a pending or approved request for this listing.' }
    );
    await expect(adapter.create('p1', 'hi')).rejects.toBeInstanceOf(RequestError);
  });

  it('a refusal with no parseable body still becomes a RequestError, never a raw SyntaxError', async () => {
    const { fn } = fakeFetch({ status: 502, badJson: true });
    const adapter = makeBuyerRequestsAdapter(fn);
    await expect(adapter.mine()).rejects.toMatchObject({ code: 'UNKNOWN', message: 'HTTP 502' });
  });

  it('defaults to the real global fetch when no fetchFn is given', () => {
    expect(() => makeBuyerRequestsAdapter()).not.toThrow();
  });
});
