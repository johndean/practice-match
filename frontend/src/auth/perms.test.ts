import { ref } from 'vue';
import { describe, expect, it } from 'vitest';
import { makePermsAdapter } from './perms';
import { useMe, type Me } from './me';

const me = (roles: string[], state = 'active'): Me => ({
  id: '1', email: 'x@practice-match.test', name: 'X', role: 'R', initials: 'X', state, roles, affiliation_label: null
});

describe('makePermsAdapter — the prototype\'s window on the generated matrix (A40, D-C53)', () => {
  it('answers from `can()`, so the header hides exactly what the API would refuse', () => {
    const staff = makePermsAdapter({ me: ref(me(['staff'])) });
    expect(staff.allowed('page.admin')).toBe(true);
    expect(staff.allowed('page.seller'), 'page.seller is ["seller"] — a staff reviewer is not a seller').toBe(false);

    const buyer = makePermsAdapter({ me: ref(me(['buyer'])) });
    expect(buyer.allowed('page.admin')).toBe(false);
    expect(buyer.allowed('page.browse')).toBe(true);
  });

  it('refuses every member permission to a visitor with no account at all', () => {
    const anon = makePermsAdapter({ me: ref(null) });
    expect(anon.allowed('page.admin')).toBe(false);
    expect(anon.allowed('page.seller')).toBe(false);
  });

  // The reason this is a factory over a store rather than a snapshot: `signIn` writes the store
  // and `logic.js` re-reads `renderVals()` in the same breath, so an answer captured at boot would
  // show a member who has just signed in the doors of whoever was there before them (nobody).
  it('reads the principal at CALL time, so signing in changes the answer with no remount', () => {
    const store = { me: ref<Me | null>(null) };
    const perms = makePermsAdapter(store);
    expect(perms.allowed('page.admin')).toBe(false);
    store.me.value = me(['admin']);
    expect(perms.allowed('page.admin')).toBe(true);
  });

  it('a non-active account is an applicant whatever it was granted — `can`\'s own rule, not a second copy', () => {
    expect(makePermsAdapter({ me: ref(me(['admin'], 'pending')) }).allowed('page.admin')).toBe(false);
  });

  it('defaults to the app\'s own store, which is what app.setup.js passes the prototype', () => {
    useMe().set(me(['staff']));
    expect(makePermsAdapter().allowed('page.admin')).toBe(true);
    useMe().clear();
    expect(makePermsAdapter().allowed('page.admin')).toBe(false);
  });
});
