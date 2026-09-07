// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useMe } from './me';

// The store's job is to hold what the API answered, so it is exercised THROUGH the api client
// against a stubbed network — no mock of our own code. I8's `main.ts` calls `load()` once before
// mount; `set()` is what `signIn` feeds it, and `clear()` what `signOut` does.
function stubFetch(answers: Record<string, { status: number; body: unknown }>): string[] {
  const urls: string[] = [];
  vi.stubGlobal('fetch', (url: string) => {
    urls.push(url);
    const answer = answers[url];
    // No entry = the request never lands, the way a proxy with nothing behind it behaves.
    if (!answer) return Promise.reject(new TypeError(`network error: ${url}`));
    return Promise.resolve({ ok: answer.status >= 200 && answer.status < 300, status: answer.status, json: () => Promise.resolve(answer.body) });
  });
  return urls;
}

const PERSONA = { id: 'a1', email: 'design@practice-match.test', name: 'Dr. Rachel Mendes', role: 'Administrator', initials: 'RM', state: 'active', roles: ['admin', 'buyer', 'seller', 'staff'], affiliation_label: 'StartUp Club' };
const SIGNED_OUT = { status: 401, body: { error: { code: 'UNAUTHORIZED', message: 'Sign in to continue.' } } };   // app/auth/deps.py's Unauthenticated
const FLAG_ON = { '/api/config': { status: 200, body: { market_data_public: true } } };
const FLAG_OFF = { '/api/config': { status: 200, body: { market_data_public: false } } };

// `load()` asks `/api/me` only when the readable `pm_csrf` cookie is there (A-I8.2), so the
// cases that exercise the principal set it and the cases about a signed-out visitor do not.
const SESSION_COOKIE = 'pm_csrf=double-submit-value';
const holdSession = () => { document.cookie = SESSION_COOKIE; };
const dropSession = () => { document.cookie = 'pm_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT'; };

beforeEach(() => { useMe().clear(); holdSession(); });
afterEach(() => { vi.unstubAllGlobals(); dropSession(); });

describe('useMe', () => {
  it('starts empty and closed — nothing is known before /api/config and /api/me answer', async () => {
    // A fresh copy of the module, so this asserts the DEFAULTS rather than whatever a
    // previously-run test left in the process-wide refs.
    vi.resetModules();
    const fresh = await import('./me');
    expect(fresh.useMe().me.value).toBeNull();
    expect(fresh.useMe().marketDataPublic.value).toBe(false);
  });

  it('load() reads the config flag and then the principal, and returns what it stored', async () => {
    const urls = stubFetch({ ...FLAG_ON, '/api/me': { status: 200, body: PERSONA } });
    const store = useMe();
    expect(await store.load()).toEqual(PERSONA);
    expect(store.me.value).toEqual(PERSONA);
    expect(store.marketDataPublic.value).toBe(true);
    expect(urls, 'the flag is read first: I8 renders the market column on the first paint').toEqual(['/api/config', '/api/me']);
  });

  it('load() leaves it null when the visitor is signed out, flag or no flag', async () => {
    const urls = stubFetch({ ...FLAG_ON, '/api/me': SIGNED_OUT });
    const store = useMe();
    expect(await store.load()).toBeNull();
    expect(store.me.value).toBeNull();
    expect(store.marketDataPublic.value).toBe(true);
    expect(urls).toEqual(['/api/config', '/api/me']);
  });

  it('fails the flag CLOSED when /api/config cannot be read, on every load', async () => {
    stubFetch({ ...FLAG_ON, '/api/me': { status: 200, body: PERSONA } });
    const store = useMe();
    await store.load();
    expect(store.marketDataPublic.value).toBe(true);
    stubFetch({ '/api/me': { status: 200, body: PERSONA } });        // /api/config never lands
    await store.load();
    expect(store.marketDataPublic.value, 'a config outage must not hand anonymous visitors market data').toBe(false);
  });

  it('reads a false flag as false, not as an outage', async () => {
    stubFetch({ ...FLAG_OFF, '/api/me': { status: 200, body: PERSONA } });
    await useMe().load();
    expect(useMe().marketDataPublic.value).toBe(false);
  });

  // Re-review: the ref is typed `Ref<boolean>`, so it must only ever hold a boolean. A 200 that
  // omits the field would otherwise store `undefined` — fail-closed in effect, but the type would
  // be lying and an `=== false` check in I8 would misread it.
  it('coerces a 200 that omits the flag, rather than storing undefined in a boolean ref', async () => {
    stubFetch({ '/api/config': { status: 200, body: {} }, '/api/me': { status: 200, body: PERSONA } });
    const store = useMe();
    await store.load();
    expect(store.marketDataPublic.value).toBe(false);
    expect(typeof store.marketDataPublic.value).toBe('boolean');
  });

  it('fails the flag closed when /api/config REFUSES, not only when it never lands', async () => {
    stubFetch({ '/api/config': { status: 500, body: { error: { code: 'INTERNAL', message: 'boom' } } }, '/api/me': { status: 200, body: PERSONA } });
    const store = useMe();
    await store.load();
    expect(store.marketDataPublic.value).toBe(false);
  });

  // Re-review: the blanket `.catch(() => false)` also swallowed a genuine client bug, leaving no
  // trace in dev. Only the two failures the API contract can produce become `false`.
  it('lets a bug in this code through instead of reading it as a closed flag', async () => {
    // Only /api/config misbehaves, and with something the contract cannot produce: a blanket
    // catch would swallow it, resolve `load()`, and leave the flag quietly false.
    vi.stubGlobal('fetch', (url: string) => {
      if (url === '/api/config') throw new RangeError('a bug in the client, not a network failure');
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(PERSONA) });
    });
    await expect(useMe().load()).rejects.toThrow(RangeError);
  });

  it('set() and clear() are what sign-in and sign-out call, and every importer sees the same refs', () => {
    const a = useMe();
    const b = useMe();
    a.set(PERSONA);
    expect(b.me.value).toEqual(PERSONA);
    b.clear();
    expect(a.me.value).toBeNull();
  });

  it('clear() leaves the site-wide flag alone — signing out does not close the market column', async () => {
    stubFetch({ ...FLAG_ON, '/api/me': { status: 200, body: PERSONA } });
    const store = useMe();
    await store.load();
    store.clear();
    expect(store.me.value).toBeNull();
    expect(store.marketDataPublic.value, 'MARKET_DATA_PUBLIC is a property of the deployment, not of the visitor').toBe(true);
  });
});

// ---------------------------------------------------------------------------------------
// A-I8.2: no `/api/me` request for a visitor who plainly has no session.
//
// `main.ts` calls `load()` on EVERY page load, and for a signed-out visitor `/api/me` answers
// 401 — the ANSWER, not a failure (api.ts says so). But Chromium logs every 4xx subresource as
// `Failed to load resource: … 401 (Unauthorized)`, with no URL in the text and no way to
// suppress it, and the Playwright harness fails a test on any console error. Forgiving the line
// in the harness was tried and withdrawn: it is a gate hole, and the request was pointless
// anyway.
//
// `pm_csrf` is the tell. `app/api/auth.py` sets it in the same handler as `pm_session`, with the
// same lifetime, and deliberately leaves it readable (`httponly=False`) so the double-submit
// value can be echoed in `X-CSRF-Token`. No `pm_csrf` therefore means no usable session: even if
// a `pm_session` somehow outlived it, every state-changing call would already be refused for want
// of the token, so "signed out" is both the safe and the accurate reading.
// ---------------------------------------------------------------------------------------
describe('useMe().load() and the session cookie (A-I8.2)', () => {
  it('does not ask /api/me at all when there is no pm_csrf cookie', async () => {
    dropSession();
    const urls = stubFetch({ ...FLAG_ON, '/api/me': { status: 200, body: PERSONA } });
    const store = useMe();

    await expect(store.load()).resolves.toBeNull();

    expect(urls, 'the flag is still read — it is a property of the deployment, not the visitor').toEqual(['/api/config']);
    expect(store.me.value).toBeNull();
    expect(store.marketDataPublic.value, 'MARKET_DATA_PUBLIC still governs the anonymous market column').toBe(true);
  });

  it('asks /api/me when the cookie is there, exactly as before', async () => {
    const urls = stubFetch({ ...FLAG_ON, '/api/me': { status: 200, body: PERSONA } });
    expect(await useMe().load()).toEqual(PERSONA);
    expect(urls).toEqual(['/api/config', '/api/me']);
  });

  it('clears a previously-loaded principal when the cookie has gone (a signed-out reload)', async () => {
    const store = useMe();
    store.set(PERSONA);
    dropSession();
    stubFetch(FLAG_OFF);

    await expect(store.load()).resolves.toBeNull();
    expect(store.me.value, 'a stale principal must not survive a load that found no session').toBeNull();
  });

  it('reads the cookie at call time, not at import time', async () => {
    dropSession();
    stubFetch({ ...FLAG_ON, '/api/me': { status: 200, body: PERSONA } });
    const store = useMe();
    expect(await store.load()).toBeNull();

    holdSession();
    expect(await store.load(), 'signing in mid-session must be visible to the next load()').toEqual(PERSONA);
  });
});

