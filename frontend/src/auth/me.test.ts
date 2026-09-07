// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useMe } from './me';

// The store's one job is to hold what `GET /api/me` answered, so it is exercised THROUGH the
// api client against a stubbed network — no mock of our own code. I8's `main.ts` calls `load()`
// once before mount; `set()` is what `signIn` feeds it, and `clear()` what `signOut` does.
function stubFetch(status: number, body: unknown): void {
  vi.stubGlobal('fetch', () => Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) }));
}

const PERSONA = { id: 'a1', email: 'design@practice-match.test', name: 'Dr. Rachel Mendes', role: 'Administrator', initials: 'RM', state: 'active', roles: ['admin', 'buyer', 'seller', 'staff'], affiliation_label: 'StartUp Club' };

beforeEach(() => useMe().clear());
afterEach(() => vi.unstubAllGlobals());

describe('useMe', () => {
  it('starts empty — nothing is known about the visitor before /api/me answers', () => {
    expect(useMe().me.value).toBeNull();
  });

  it('load() fills it from /api/me and returns what it stored', async () => {
    stubFetch(200, PERSONA);
    const store = useMe();
    expect(await store.load()).toEqual(PERSONA);
    expect(store.me.value).toEqual(PERSONA);
  });

  it('load() leaves it null when the visitor is signed out', async () => {
    stubFetch(200, PERSONA);
    await useMe().load();
    stubFetch(401, { error: { code: 'UNAUTHENTICATED', message: 'Sign in to continue.' } });
    expect(await useMe().load()).toBeNull();
    expect(useMe().me.value).toBeNull();
  });

  it('set() and clear() are what sign-in and sign-out call, and every importer sees the same ref', () => {
    const a = useMe();
    const b = useMe();
    a.set(PERSONA);
    expect(b.me.value).toEqual(PERSONA);
    b.clear();
    expect(a.me.value).toBeNull();
  });
});
