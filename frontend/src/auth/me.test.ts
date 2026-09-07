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

beforeEach(() => useMe().clear());
afterEach(() => vi.unstubAllGlobals());

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
