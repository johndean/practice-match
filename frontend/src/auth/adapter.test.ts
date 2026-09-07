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

describe('makeAuthAdapter (C1)', () => {
  it('writes the account into the store BEFORE its own promise resolves', async () => {
    const store = fakeStore();
    const calls: string[] = [];
    const adapter = makeAuthAdapter({
      signIn: (email, password) => { calls.push(`signIn(${email},${password})`); return Promise.resolve(ME); },
      signOut: () => Promise.resolve({ status: 'signed_out' })
    }, store);

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
    const adapter = makeAuthAdapter({ signIn: () => Promise.reject(refusal), signOut: () => Promise.resolve(null) }, store);

    await expect(adapter.signIn('buyer@practice-match.test', 'wrong')).rejects.toBe(refusal);

    expect(store.writes, 'a refused sign-in must not leave a principal behind').toEqual([]);
    expect(store.held).toBeNull();
  });

  it('ends the session and then clears the store', async () => {
    const store = fakeStore();
    const calls: string[] = [];
    const adapter = makeAuthAdapter({
      signIn: () => Promise.resolve(ME),
      signOut: () => { calls.push('signOut()'); return Promise.resolve({ status: 'signed_out' }); }
    }, store);
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
    const adapter = makeAuthAdapter({ signIn: () => Promise.resolve(ME), signOut: () => Promise.reject(failure) }, store);
    store.set(ME);

    await expect(adapter.signOut()).rejects.toBe(failure);

    expect(store.held, 'the store must not outlive the screen that named it').toBeNull();
    expect(store.writes).toEqual(['set(buyer@practice-match.test)', 'clear()']);
  });
});
