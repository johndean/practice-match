// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthError, acceptInvite, answer, applicationsMe, apply, config, csrfToken, forgot, me, reauth, reset, signIn, signOut, signUp, verify } from './api';

interface Call { url: string; init: { method: string; credentials: string; headers: Record<string, string>; body?: string } }

/**
 * The network boundary and nothing else. Every answer is a plain object with the three members
 * `api.ts` reads (`ok`, `status`, `json`), so this needs neither `Response` nor a real server —
 * the real server is exercised by the Playwright persona proof (tests/smoke.spec.ts).
 */
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

const PERSONA = { id: 'a1', email: 'design@practice-match.test', name: 'Dr. Rachel Mendes', role: 'Administrator', initials: 'RM', state: 'active', roles: ['admin', 'buyer', 'seller', 'staff'], affiliation_label: 'StartUp Club' };

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = 'pm_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

describe('csrfToken', () => {
  it('reads the pm_csrf cookie — the one cookie app/api/auth.py deliberately leaves readable', () => {
    expect(csrfToken('pm_session=nope; pm_csrf=abc123; other=1')).toBe('abc123');
    expect(csrfToken('pm_csrf=a%2Bb')).toBe('a+b');
  });
  it('is the empty string when there is no session to protect', () => {
    expect(csrfToken('')).toBe('');
    expect(csrfToken('pm_session=only')).toBe('');
  });
  it('defaults to document.cookie', () => {
    document.cookie = 'pm_csrf=from-the-document';
    expect(csrfToken()).toBe('from-the-document');
  });
});

describe('signIn', () => {
  it('posts the credentials as same-origin JSON and returns the Me', async () => {
    const calls = stubFetch({ status: 200, body: PERSONA });
    expect(await signIn('design@practice-match.test', 'hunter2')).toEqual(PERSONA);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('/api/auth/signin');
    expect(calls[0].init.method).toBe('POST');
    expect(calls[0].init.credentials).toBe('same-origin');
    expect(calls[0].init.headers['Content-Type']).toBe('application/json');
    expect(calls[0].init.body).toBe(JSON.stringify({ email: 'design@practice-match.test', password: 'hunter2' }));
  });

  it('throws the server\'s own code and message on a 401', async () => {
    stubFetch({ status: 401, body: { error: { code: 'INVALID_CREDENTIALS', message: 'Email or password is incorrect.' } } });
    const thrown = await signIn('a@b.co', 'wrong').catch((e: unknown) => e);
    expect(thrown).toBeInstanceOf(AuthError);
    expect((thrown as AuthError).code).toBe('INVALID_CREDENTIALS');
    expect((thrown as AuthError).message).toBe('Email or password is incorrect.');
    expect((thrown as AuthError).name).toBe('AuthError');
  });

  it('carries the rate limiter\'s code through unchanged, so the caller can tell 429 from 401', async () => {
    stubFetch({ status: 429, body: { error: { code: 'RATE_LIMITED', message: 'Too many attempts. Try again later.' } } });
    await expect(signIn('a@b.co', 'x')).rejects.toMatchObject({ code: 'RATE_LIMITED' });
  });

  it('falls back to a code and a status when the body is not the A5 error shape', async () => {
    stubFetch({ status: 502, text: '<html>bad gateway</html>' });
    const thrown = (await signIn('a@b.co', 'x').catch((e: unknown) => e)) as AuthError;
    expect(thrown.code).toBe('UNKNOWN');
    expect(thrown.message).toBe('HTTP 502');
  });
});

describe('the state-changing calls send X-CSRF-Token, read from the cookie', () => {
  it('on signUp, verify, apply, signOut and reauth', async () => {
    document.cookie = 'pm_csrf=double-submit';
    const calls = stubFetch({ status: 202, body: { status: 'check_email' } }, { status: 200, body: { status: 'verified' } },
      { status: 202, body: { id: 'ap1', status: 'pending' } }, { status: 200, body: { status: 'signed_out' } },
      { status: 200, body: { status: 'reauthenticated' } });
    expect(await signUp('a@b.co', 'pw')).toEqual({ status: 'check_email' });
    expect(await verify('tok')).toEqual({ status: 'verified' });
    expect(await apply('buyer', { name: 'A', affirm: true })).toEqual({ id: 'ap1', status: 'pending' });
    expect(await signOut()).toEqual({ status: 'signed_out' });
    expect(await reauth('pw')).toEqual({ status: 'reauthenticated' });
    expect(calls.map((c) => c.url)).toEqual(['/api/auth/signup', '/api/auth/verify', '/api/applications', '/api/auth/signout', '/api/auth/reauth']);
    expect(calls.map((c) => c.init.headers['X-CSRF-Token'])).toEqual(Array(5).fill('double-submit'));
    expect(calls.map((c) => c.init.body)).toEqual([
      JSON.stringify({ email: 'a@b.co', password: 'pw' }),
      JSON.stringify({ token: 'tok' }),
      JSON.stringify({ kind: 'buyer', fields: { name: 'A', affirm: true } }),
      undefined,                                   // signout carries no body
      JSON.stringify({ password: 'pw' })
    ]);
  });
});

describe('me()', () => {
  it('GETs /api/me and returns the payload, with no CSRF header on a read', async () => {
    const calls = stubFetch({ status: 200, body: PERSONA });
    expect(await me()).toEqual(PERSONA);
    expect(calls[0].url).toBe('/api/me');
    expect(calls[0].init.method).toBe('GET');
    expect(calls[0].init.headers['X-CSRF-Token']).toBeUndefined();
    expect(calls[0].init.body).toBeUndefined();
  });

  it('is null when signed out — a 401 here is the answer, not a failure', async () => {
    stubFetch({ status: 401, body: { error: { code: 'UNAUTHORIZED', message: 'Sign in to continue.' } } });   // app/auth/deps.py's Unauthenticated.code
    expect(await me()).toBeNull();
  });

  it('still throws on anything else, so a broken API is never read as "signed out"', async () => {
    stubFetch({ status: 500, body: { error: { code: 'INTERNAL', message: 'boom' } } });
    await expect(me()).rejects.toMatchObject({ code: 'INTERNAL' });
  });
});

describe('forgot, reset, acceptInvite, answer — POST with credentials and the CSRF header', () => {
  it('post the exact path and body, and return the parsed body', async () => {
    document.cookie = 'pm_csrf=double-submit';
    const calls = stubFetch(
      { status: 202, body: { status: 'check_email' } },
      { status: 200, body: { status: 'reset' } },
      { status: 200, body: { status: 'active' } },
      { status: 200, body: { status: 'pending' } }
    );
    expect(await forgot('a@b.co')).toEqual({ status: 'check_email' });
    expect(await reset('tok', 'newpw')).toEqual({ status: 'reset' });
    expect(await acceptInvite('tok', 'newpw')).toEqual({ status: 'active' });
    expect(await answer('ap1', 'Yes, I confirm.')).toEqual({ status: 'pending' });
    expect(calls.map((c) => c.url)).toEqual([
      '/api/auth/password/forgot',
      '/api/auth/password/reset',
      '/api/auth/accept-invite',
      '/api/applications/ap1/answer'
    ]);
    expect(calls.map((c) => c.init.method)).toEqual(Array(4).fill('POST'));
    expect(calls.map((c) => c.init.credentials)).toEqual(Array(4).fill('same-origin'));
    expect(calls.map((c) => c.init.headers['X-CSRF-Token'])).toEqual(Array(4).fill('double-submit'));
    expect(calls.map((c) => c.init.body)).toEqual([
      JSON.stringify({ email: 'a@b.co' }),
      JSON.stringify({ token: 'tok', password: 'newpw' }),
      JSON.stringify({ token: 'tok', password: 'newpw' }),
      JSON.stringify({ answer: 'Yes, I confirm.' })
    ]);
  });

  it('answer() encodes the application id into the path', async () => {
    const calls = stubFetch({ status: 200, body: { status: 'pending' } });
    await answer('needs/slash', 'ok');
    expect(calls[0].url).toBe('/api/applications/needs%2Fslash/answer');
  });

  it('throws the server\'s AuthError on a 4xx, like every other call', async () => {
    stubFetch({ status: 400, body: { error: { code: 'TOKEN_EXPIRED', message: 'This link has expired.' } } });
    await expect(reset('stale', 'newpw')).rejects.toMatchObject({ code: 'TOKEN_EXPIRED' });
  });
});

describe('applicationsMe()', () => {
  it('GETs /api/applications/me and returns {current, history}, with no CSRF header on a read', async () => {
    const rows = {
      current: { id: 'ap1', kind: 'buyer', status: 'pending', info_request: null, answer: null, fields: { name: 'A' }, decision_note: null },
      history: []
    };
    const calls = stubFetch({ status: 200, body: rows });
    expect(await applicationsMe()).toEqual(rows);
    expect(calls[0].url).toBe('/api/applications/me');
    expect(calls[0].init.method).toBe('GET');
    expect(calls[0].init.headers['X-CSRF-Token']).toBeUndefined();
    expect(calls[0].init.body).toBeUndefined();
  });

  it('throws like every other read when the endpoint is broken', async () => {
    stubFetch({ status: 500, body: { error: { code: 'INTERNAL', message: 'boom' } } });
    await expect(applicationsMe()).rejects.toMatchObject({ code: 'INTERNAL' });
  });
});

// A-I7.2 / review Important 4: `MARKET_DATA_PUBLIC` had no runtime source, so the client's twin
// of the matrix could not honour the one rule that is not the matrix.
describe('config()', () => {
  it('GETs /api/config, with no CSRF header on a read', async () => {
    const calls = stubFetch({ status: 200, body: { market_data_public: true } });
    expect(await config()).toEqual({ market_data_public: true });
    expect(calls[0].url).toBe('/api/config');
    expect(calls[0].init.method).toBe('GET');
    expect(calls[0].init.headers['X-CSRF-Token']).toBeUndefined();
  });

  it('throws like every other read when the endpoint is broken — the caller decides the default', async () => {
    stubFetch({ status: 500, body: { error: { code: 'INTERNAL', message: 'boom' } } });
    await expect(config()).rejects.toMatchObject({ code: 'INTERNAL' });
  });
});
