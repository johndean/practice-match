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

  // ---------------------------------------------------------------------------------------
  // Ruling D-C54 (John, 2026-09-13, verbatim): "as logged in VIN FOUNDATION ADMIN i can no longer
  // access nor see MY REQUEST and LIST A PRACTICE - this is not right as SUPERADMIN JOHN DEAN i
  // need to see it all!!!"
  //
  // The header hides exactly what the API would refuse, so the header's own answer for an
  // admin-only account is now yes to everything. Written against `makePermsAdapter` rather than
  // against the generated table directly because THIS is what `logic.js` asks: John's account
  // holds `admin` alone, and the seeded design persona holds all four roles, which is why every
  // test in the suite passed while his header was missing two items.
  // ---------------------------------------------------------------------------------------
  it('gives an admin-only account every member door too — the superset rule (D-C54)', () => {
    const admin = makePermsAdapter({ me: ref(me(['admin'])) });
    expect(admin.allowed('page.seller'), '"List a Practice"').toBe(true);
    expect(admin.allowed('request.read_own'), '"My Requests"').toBe(true);
    expect(admin.allowed('request.create')).toBe(true);
    expect(admin.allowed('listing.manage_own')).toBe(true);
    expect(admin.allowed('request.answer_own')).toBe(true);
    expect(admin.allowed('seller.apply')).toBe(true);
    // ...and what it always held.
    expect(admin.allowed('page.admin')).toBe(true);
    expect(admin.allowed('page.browse')).toBe(true);
  });

  // `staff` is unchanged by D-C54 — the ruling names `admin` and nothing else — which is what
  // makes the case above a statement about one role rather than about privilege in general.
  it('leaves the staff reviewer exactly where it was: not a seller, not a buyer', () => {
    const staff = makePermsAdapter({ me: ref(me(['staff'])) });
    expect(staff.allowed('page.seller')).toBe(false);
    expect(staff.allowed('request.read_own')).toBe(false);
    expect(staff.allowed('request.create')).toBe(false);
    expect(staff.allowed('seller.apply')).toBe(false);
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
