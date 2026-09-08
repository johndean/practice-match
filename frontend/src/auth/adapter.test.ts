// @vitest-environment jsdom
//
// Review round 1, C1. The prototype's `auth` prop used to be built inline in `app.setup.js` as
// `{ signIn: api.signIn, signOut: () => api.signOut().then(() => useMe().clear()) }` — and
// `signIn` never wrote the answer into the store. So after an INTERACTIVE sign-in through the
// design's own form, `useMe().me.value` stayed null while `logic.js` believed it was signed in,
// and the next `guard()` call asked `can('page.browse', null)`, got false, and sent the member to
// the empty `unavailable` gate. `main.ts`'s load-before-mount hid it from every reload path,
// which is why only an end-to-end form sign-in could catch it (smoke.spec.ts does now).
//
// The adapter lives here — a hand-written, coverage-measured module — precisely so it has unit
// tests: `app.setup.js` is copied verbatim into App.vue by the generator and is not measured.
import { describe, expect, it } from 'vitest';
import { makeAuthAdapter } from './adapter';
import type { AuthApi } from './adapter';
import type { Me } from './me';

const ME: Me = {
  id: 'a1', email: 'buyer@practice-match.test', name: 'Dr. Rachel Mendes',
  role: 'Approved buyer · StartUp Club', initials: 'RM', state: 'active',
  roles: ['buyer'], affiliation_label: 'StartUp Club'
};

/** A fake store with the two methods the adapter uses, recording the order of every write. */
function fakeStore() {
  const writes: string[] = [];
  let held: Me | null = null;
  return {
    writes,
    get held() { return held; },
    set: (me: Me) => { writes.push(`set(${me.email})`); held = me; },
    clear: () => { writes.push('clear()'); held = null; }
  };
}

const STATUS = { status: 'check_email' };

/** A complete `AuthApi`, so a test can override just the one method it exercises. */
function fakeApi(overrides: Partial<AuthApi> = {}): AuthApi {
  return {
    signIn: () => Promise.resolve(ME),
    signOut: () => Promise.resolve({ status: 'signed_out' }),
    signUp: () => Promise.resolve(STATUS),
    verify: () => Promise.resolve(STATUS),
    forgot: () => Promise.resolve(STATUS),
    reset: () => Promise.resolve(STATUS),
    acceptInvite: () => Promise.resolve(STATUS),
    apply: () => Promise.resolve({ id: 'ap1', status: 'pending' }),
    answer: () => Promise.resolve(STATUS),
    applicationsMe: () => Promise.resolve({ current: null, history: [] }),
    resendVerification: () => Promise.resolve(STATUS),
    ...overrides
  };
}

describe('makeAuthAdapter (C1)', () => {
  it('writes the account into the store BEFORE its own promise resolves', async () => {
    const store = fakeStore();
    const calls: string[] = [];
    const adapter = makeAuthAdapter(fakeApi({
      signIn: (email, password) => { calls.push(`signIn(${email},${password})`); return Promise.resolve(ME); },
      signOut: () => Promise.resolve({ status: 'signed_out' })
    }), store);

    // The ordering IS the fix: `logic.js`'s own `.then` runs when this promise settles, and the
    // very next `guard()` reads the store. Asserted by observing the store at the moment the
    // adapter hands control back.
    const resolved = await adapter.signIn('buyer@practice-match.test', 'a-password');

    expect(calls).toEqual(['signIn(buyer@practice-match.test,a-password)']);
    expect(store.writes).toEqual(['set(buyer@practice-match.test)']);
    expect(store.held, 'the store must already hold the principal when the caller regains control').toBe(ME);
    expect(resolved, 'and the answer is still handed on, because logic.js reads the header strings from it').toBe(ME);
  });

  it('leaves the store alone when the sign-in is refused, and passes the refusal on', async () => {
    const store = fakeStore();
    const refusal = new Error('Email or password is incorrect.');
    const adapter = makeAuthAdapter(fakeApi({ signIn: () => Promise.reject(refusal) }), store);

    await expect(adapter.signIn('buyer@practice-match.test', 'wrong')).rejects.toBe(refusal);

    expect(store.writes, 'a refused sign-in must not leave a principal behind').toEqual([]);
    expect(store.held).toBeNull();
  });

  it('ends the session and then clears the store', async () => {
    const store = fakeStore();
    const calls: string[] = [];
    const adapter = makeAuthAdapter(fakeApi({
      signOut: () => { calls.push('signOut()'); return Promise.resolve({ status: 'signed_out' }); }
    }), store);
    store.set(ME);

    await adapter.signOut();

    expect(calls).toEqual(['signOut()']);
    expect(store.writes).toEqual(['set(buyer@practice-match.test)', 'clear()']);
    expect(store.held).toBeNull();
  });

  it('clears the store even when the API refuses the sign-out, and still reports the failure', async () => {
    // `logic.js`'s A5.3 resets the prototype whatever the network did, so the store has to agree:
    // a populated store behind a signed-out screen is a stale principal the next `guard()` would
    // trust. The rejection is still propagated, for a caller that wants to know.
    const store = fakeStore();
    const failure = new Error('network');
    const adapter = makeAuthAdapter(fakeApi({ signOut: () => Promise.reject(failure) }), store);
    store.set(ME);

    await expect(adapter.signOut()).rejects.toBe(failure);

    expect(store.held, 'the store must not outlive the screen that named it').toBeNull();
    expect(store.writes).toEqual(['set(buyer@practice-match.test)', 'clear()']);
  });
});

// S1: the eight account-lifecycle methods the later gate screens (routes, forgot/reset,
// accept-invite, the application status card) call through. Every one is a plain pass-through —
// unlike signIn/signOut, none of them has an opinion about the store — so each test asserts the
// same three things: the same-named `api` function is called with the same arguments, its result
// is handed straight back, and the store is left exactly as it was found.
describe('makeAuthAdapter — the nine lifecycle pass-throughs', () => {
  // A-S4.1: the ninth. Like the other eight it has no opinion about the store — a re-sent
  // verification mail does not change who `useMe()` says the visitor is.
  it('resendVerification calls api.resendVerification with no arguments and returns its result, untouched by the store', async () => {
    const calls: unknown[] = [];
    const store = fakeStore();
    const adapter = makeAuthAdapter(fakeApi({ resendVerification: (...args: unknown[]) => { calls.push(args); return Promise.resolve(STATUS); } }), store);

    expect(await adapter.resendVerification()).toBe(STATUS);

    expect(calls).toEqual([[]]);
    expect(store.writes).toEqual([]);
  });

  it('signUp calls api.signUp with the same arguments and returns its result, untouched by the store', async () => {
    const calls: unknown[] = [];
    const store = fakeStore();
    const adapter = makeAuthAdapter(fakeApi({ signUp: (email, password) => { calls.push([email, password]); return Promise.resolve(STATUS); } }), store);

    expect(await adapter.signUp('a@b.co', 'pw')).toBe(STATUS);

    expect(calls).toEqual([['a@b.co', 'pw']]);
    expect(store.writes).toEqual([]);
  });

  it('verify calls api.verify with the same argument and returns its result, untouched by the store', async () => {
    const calls: unknown[] = [];
    const store = fakeStore();
    const adapter = makeAuthAdapter(fakeApi({ verify: (token) => { calls.push([token]); return Promise.resolve(STATUS); } }), store);

    expect(await adapter.verify('tok')).toBe(STATUS);

    expect(calls).toEqual([['tok']]);
    expect(store.writes).toEqual([]);
  });

  it('forgot calls api.forgot with the same argument and returns its result, untouched by the store', async () => {
    const calls: unknown[] = [];
    const store = fakeStore();
    const adapter = makeAuthAdapter(fakeApi({ forgot: (email) => { calls.push([email]); return Promise.resolve(STATUS); } }), store);

    expect(await adapter.forgot('a@b.co')).toBe(STATUS);

    expect(calls).toEqual([['a@b.co']]);
    expect(store.writes).toEqual([]);
  });

  it('reset calls api.reset with the same arguments and returns its result, untouched by the store', async () => {
    const calls: unknown[] = [];
    const store = fakeStore();
    const adapter = makeAuthAdapter(fakeApi({ reset: (token, password) => { calls.push([token, password]); return Promise.resolve(STATUS); } }), store);

    expect(await adapter.reset('tok', 'newpw')).toBe(STATUS);

    expect(calls).toEqual([['tok', 'newpw']]);
    expect(store.writes).toEqual([]);
  });

  it('acceptInvite calls api.acceptInvite with the same arguments and returns its result, untouched by the store', async () => {
    const calls: unknown[] = [];
    const store = fakeStore();
    const adapter = makeAuthAdapter(fakeApi({ acceptInvite: (token, password) => { calls.push([token, password]); return Promise.resolve(STATUS); } }), store);

    expect(await adapter.acceptInvite('tok', 'newpw')).toBe(STATUS);

    expect(calls).toEqual([['tok', 'newpw']]);
    expect(store.writes).toEqual([]);
  });

  it('apply calls api.apply with the same arguments and returns its result, untouched by the store', async () => {
    const calls: unknown[] = [];
    const store = fakeStore();
    const result = { id: 'ap1', status: 'pending' };
    const adapter = makeAuthAdapter(fakeApi({ apply: (kind, fields) => { calls.push([kind, fields]); return Promise.resolve(result); } }), store);

    expect(await adapter.apply('buyer', { name: 'A' })).toBe(result);

    expect(calls).toEqual([['buyer', { name: 'A' }]]);
    expect(store.writes).toEqual([]);
  });

  it('answer calls api.answer with the same arguments and returns its result, untouched by the store', async () => {
    const calls: unknown[] = [];
    const store = fakeStore();
    const adapter = makeAuthAdapter(fakeApi({ answer: (applicationId, text) => { calls.push([applicationId, text]); return Promise.resolve(STATUS); } }), store);

    expect(await adapter.answer('ap1', 'Yes, I confirm.')).toBe(STATUS);

    expect(calls).toEqual([['ap1', 'Yes, I confirm.']]);
    expect(store.writes).toEqual([]);
  });

  it('applicationsMe calls api.applicationsMe with no arguments and returns its result, untouched by the store', async () => {
    const calls: unknown[] = [];
    const store = fakeStore();
    const result = { current: null, history: [] };
    const adapter = makeAuthAdapter(fakeApi({ applicationsMe: () => { calls.push([]); return Promise.resolve(result); } }), store);

    expect(await adapter.applicationsMe()).toBe(result);

    expect(calls).toEqual([[]]);
    expect(store.writes).toEqual([]);
  });
});
