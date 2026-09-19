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
  approved_disclosure_level: null, requested_at: '2026-08-21T10:00:00Z', reviewed_at: null,
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
    expect(result.map((r) => ({ id: r.id, status: r.status, buyer: r.buyer }))).toEqual([
      { id: 'r1', status: 'pending', buyer: 'b1' },
      { id: 'r2', status: 'accepted', buyer: 'b1' }
    ]);
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

  it('decide() includes disclosure_level and reason only when given', async () => {
    const { fn, calls } = fakeFetch(
      { status: 200, body: ROW({ status: 'APPROVED', approved_disclosure_level: 'FULL_CONFIDENTIAL' }) },
      { status: 200, body: ROW({ status: 'DENIED', denial_reason: 'Under contract with another buyer.' }) }
    );
    const adapter = makeSellerRequestsAdapter(fn);
    await adapter.decide('r1', 'approve', 'FULL_CONFIDENTIAL');
    expect(JSON.parse(calls[0].init.body!)).toEqual({ action: 'approve', disclosure_level: 'FULL_CONFIDENTIAL' });
    const denied = await adapter.decide('r1', 'deny', undefined, 'Under contract with another buyer.');
    expect(JSON.parse(calls[1].init.body!)).toEqual({ action: 'deny', reason: 'Under contract with another buyer.' });
    expect(denied.reply).toBe('Under contract with another buyer.');
  });

  it('revoke() posts an empty JSON body to .../revoke, with the CSRF header', async () => {
    const { fn, calls } = fakeFetch({ status: 200, body: ROW({ status: 'REVOKED' }) });
    const adapter = makeSellerRequestsAdapter(fn);
    const result = await adapter.revoke('r1');
    expect(calls[0].url).toBe('/api/seller/requests/r1/revoke');
    expect(calls[0].init.method).toBe('POST');
    expect(calls[0].init.headers['X-CSRF-Token']).toBe('tok');
    expect(JSON.parse(calls[0].init.body!)).toEqual({});
    expect(result.status).toBe('declined');
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
