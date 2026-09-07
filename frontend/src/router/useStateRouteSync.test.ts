// @vitest-environment jsdom
//
// Exercises the composable itself (watch/afterEach wiring), not just the pure functions in
// sync.ts. Uses the REAL Component from logic.js, the REAL useStateRouteSync, and a real
// vue-router built from the app's own route table (routes.ts) on createMemoryHistory — no
// mocks, no stub router.
import { createApp, nextTick, reactive } from 'vue';
import { createMemoryHistory, createRouter, type Router } from 'vue-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Component } from '../logic.js';
import { useMe, type Me } from '../auth/me';
import { routes } from './routes';
import { useStateRouteSync } from './useStateRouteSync';

// A-I7's hand-over, executed by A-I8: `guard()` takes a principal, and `useStateRouteSync` is
// the caller that has one — `useMe().me.value`, loaded by main.ts before the app mounts. Every
// case below therefore signs in as a real principal rather than only flipping `state.auth`:
// with a permission the route needs, the deep link is honoured exactly as before; without it,
// the permission matrix has the second say and the visitor gets the `unavailable` gate.
//
// The design persona holds every role, so it is the DEFAULT here and every pre-existing case
// keeps asserting what it always asserted.
const MEMBER: Me = {
  id: '11111111-1111-1111-1111-111111111111', email: 'design@practice-match.test', name: 'Dr. Rachel Mendes',
  role: 'VIN Foundation admin · StartUp Club', initials: 'RM', state: 'active',
  roles: ['admin', 'buyer', 'seller', 'staff'], affiliation_label: 'StartUp Club'
};

// Vue's watchers flush on a microtask; router navigation resolves on a promise chain too.
// A macrotask tick (setTimeout) drains both, which is why this is used instead of a bare
// await nextTick() between steps that involve a navigation.
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

let apps: ReturnType<typeof createApp>[] = [];
afterEach(() => { apps.forEach((a) => a.unmount()); apps = []; useMe().clear(); });

async function setup(initialPath = '/', me: Me | null = MEMBER) {
  // The store is module-level state (me.ts says why it is not a Pinia store), so it is set
  // before the composable reads it and cleared in afterEach.
  if (me) useMe().set(me); else useMe().clear();
  const router = createRouter({ history: createMemoryHistory(), routes });
  // Push explicitly (even for '/') rather than relying on vue-router's install-time
  // auto-navigation, which only fires once app.use(router) runs — after isReady() below
  // would otherwise be awaited, causing it to hang forever for the '/' case.
  await router.push(initialPath);
  await router.isReady();
  const c = new Component({});
  c.state = reactive(c.state);
  const el = document.createElement('div');
  const app = createApp({ setup() { useStateRouteSync(c, router); return () => null; } });
  app.use(router);
  app.mount(el);
  apps.push(app);
  await flush(); await nextTick();
  return { c, router: router as Router, app };
}

describe('useStateRouteSync — state → route', () => {
  it('pushes the URL when state changes: browse, then admin+data', async () => {
    const { c, router } = await setup('/');
    c.setState({ screen: 'browse', auth: true });
    await flush(); await nextTick();
    expect(router.currentRoute.value.fullPath).toBe('/browse');

    c.setState({ screen: 'admin', adminTab: 'data' });
    await flush(); await nextTick();
    expect(router.currentRoute.value.fullPath).toBe('/admin?tab=data');
  });
});

describe('useStateRouteSync — route → state', () => {
  it('applies a deep link to a member route once signed in', async () => {
    const { c, router } = await setup('/');
    c.setState({ auth: true });
    await flush(); await nextTick();

    await router.push('/practices/p3');
    await flush(); await nextTick();
    expect(c.state.screen).toBe('detail');
    expect(c.state.detailId).toBe('p3');
  });
});

describe('useStateRouteSync — signed-out deep link + pending route on auth', () => {
  it('keeps the URL and shows the sign-in gate for a signed-out deep link into a member route', async () => {
    const { c, router } = await setup('/browse?tab=market');
    expect(c.state.screen).toBe('gate');
    expect(c.state.gate).toBe('signin');
    expect(router.currentRoute.value.fullPath).toBe('/browse?tab=market');
  });

  it('applies the pending route the instant auth flips true — the real signIn() pattern (screen + auth in one setState)', async () => {
    const { c, router } = await setup('/browse?tab=market');
    // logic.js:1039-1041 signIn(): this.setState({ screen: "browse", formError: "", auth: true });
    c.setState({ screen: 'browse', formError: '', auth: true });
    await flush(); await nextTick();
    expect(router.currentRoute.value.fullPath).toBe('/browse');
  });

  it('applies the pending route when only auth flips (no screen change in the same setState)', async () => {
    const { c } = await setup('/browse?tab=market');
    c.setState({ auth: true });
    await flush(); await nextTick();
    expect(c.state.screen).toBe('browse');
  });

  // Regression: dc-logic.js's setState() is Object.assign(state, patch), which sets keys in
  // the patch object's own order. `screen` here comes before `auth`, so both `auth` and
  // `loc` change in the same synchronous block, in that order — the composable's one
  // watcher must not assume `auth` was already true by the time it reasons about `screen`,
  // or vice versa; it must read `c.state.auth` fresh, not trust an argument captured at a
  // stale moment.
  it('settles at /browse regardless of setState key order (screen before auth)', async () => {
    const { c, router } = await setup('/browse?tab=market');
    c.setState({ screen: 'browse', auth: true });
    await flush(); await nextTick();
    expect(router.currentRoute.value.fullPath).toBe('/browse');
  });

  it('a signed-out deep link into a NON-Browse member route survives signIn()\'s hardcoded browse', async () => {
    const { c, router } = await setup('/practices/p1');
    const push = vi.spyOn(router, 'push'), replace = vi.spyOn(router, 'replace');
    c.setState({ screen: 'browse', formError: '', auth: true }); // logic.js:1404 verbatim
    await flush(); await nextTick(); await flush(); await nextTick();
    expect(c.state.screen).toBe('detail');
    expect(c.state.detailId).toBe('p1');
    expect(router.currentRoute.value.fullPath).toBe('/practices/p1');
    expect(push.mock.calls.length + replace.mock.calls.length).toBe(0); // no transitional /browse hop
  });

  it('keeps withholding the pending route if something else re-triggers the watcher before auth arrives, and pending survives to be applied once auth arrives', async () => {
    const { c, router } = await setup('/practices/p4');
    // Nothing in logic.js changes `screen` away from 'gate' without also flipping `auth`
    // true in the same setState (guard() enforces that invariant on every real transition)
    // — this bypasses that invariant on purpose, as a direct test of the watcher's own
    // resilience: whatever caused the retrigger, it must still withhold navigation while
    // genuinely signed out, rather than trusting that a retrigger only ever means auth
    // has arrived. `p9` (not the deep-linked `p4`) makes the eventual winner distinguishable.
    c.setState({ screen: 'detail', detailId: 'p9' });
    await flush(); await nextTick();
    expect(router.currentRoute.value.fullPath).toBe('/practices/p4');
    expect(c.state.screen).toBe('detail');

    // The withheld retrigger above must not have consumed `pending` — the original
    // deep-linked target (p4) is what actually gets applied once auth arrives, not the p9
    // used only to force the retrigger.
    c.setState({ auth: true });
    await flush(); await nextTick();
    expect(router.currentRoute.value.fullPath).toBe('/practices/p4');
    expect(c.state.detailId).toBe('p4');
  });
});

describe('useStateRouteSync — replace vs. push', () => {
  it('uses router.replace (not push) when only the query changes and the path stays the same', async () => {
    const { c, router } = await setup('/');
    c.setState({ screen: 'admin', adminTab: 'users', auth: true });
    await flush(); await nextTick();
    expect(router.currentRoute.value.fullPath).toBe('/admin');

    const pushSpy = vi.spyOn(router, 'push');
    const replaceSpy = vi.spyOn(router, 'replace');
    c.setState({ adminTab: 'data' }); // same screen/path, only the query changes
    await flush(); await nextTick();

    expect(router.currentRoute.value.fullPath).toBe('/admin?tab=data');
    expect(replaceSpy).toHaveBeenCalledTimes(1);
    expect(pushSpy).not.toHaveBeenCalled();
  });
});

describe('useStateRouteSync — no state↔route loop', () => {
  it('produces exactly one navigation for a state change, and none for a repeat of the same state', async () => {
    const { c, router } = await setup('/');
    const pushSpy = vi.spyOn(router, 'push');
    const replaceSpy = vi.spyOn(router, 'replace');

    c.setState({ screen: 'requests', auth: true });
    await flush(); await nextTick();
    expect(pushSpy.mock.calls.length + replaceSpy.mock.calls.length).toBe(1);

    c.setState({ screen: 'requests', auth: true }); // identical values — no reactive change, no navigation
    await flush(); await nextTick();
    expect(pushSpy.mock.calls.length + replaceSpy.mock.calls.length).toBe(1);
  });

  it('a burst of five setState calls navigates a bounded number of times, with no oscillation', async () => {
    const { c, router } = await setup('/');
    c.setState({ auth: true });
    await flush(); await nextTick();

    const pushSpy = vi.spyOn(router, 'push');
    const replaceSpy = vi.spyOn(router, 'replace');

    c.setState({ screen: 'browse' });
    await flush(); await nextTick();
    c.setState({ screen: 'requests' });
    await flush(); await nextTick();
    c.setState({ screen: 'seller' });
    await flush(); await nextTick();
    c.setState({ screen: 'admin', adminTab: 'data' });
    await flush(); await nextTick();
    c.setState({ screen: 'browse' });
    await flush(); await nextTick();

    const total = pushSpy.mock.calls.length + replaceSpy.mock.calls.length;
    expect(total).toBeGreaterThan(0);
    expect(total).toBeLessThanOrEqual(5);
    expect(router.currentRoute.value.fullPath).toBe('/browse');

    // Quiescent afterwards — no oscillation/self-retriggering.
    await flush(); await nextTick();
    expect(pushSpy.mock.calls.length + replaceSpy.mock.calls.length).toBe(total);
  });
});

// F4: signed in and already on Browse, an in-session router.push('/browse?tab=market')
// (e.g. a stale bookmark or a Back/Forward navigation within the same session) used to
// leave the URL at the legacy query forever: routeToPatch strips ?tab=, so the resulting
// patch ({screen:'browse'}) never differs from the current state, needsPatch is false, no
// setState fires, and the state→route watcher — which only reacts to state changes — never
// runs. apply() now also settles the URL directly against the current state after the
// needsPatch check, whenever there is no pending gate to protect.
describe('useStateRouteSync — a stale in-session ?tab= on Browse settles', () => {
  it('signed in on Browse, an in-session router.push(\'/browse?tab=market\') settles to /browse with exactly one replace, then stays quiescent', async () => {
    const { c, router } = await setup('/');
    c.setState({ screen: 'browse', auth: true });
    await flush(); await nextTick();
    expect(router.currentRoute.value.fullPath).toBe('/browse');

    const pushSpy = vi.spyOn(router, 'push');
    const replaceSpy = vi.spyOn(router, 'replace');
    await router.push('/browse?tab=market');
    await flush(); await nextTick();
    expect(router.currentRoute.value.fullPath).toBe('/browse');
    expect(pushSpy).toHaveBeenCalledTimes(1);       // our own initiating push
    expect(replaceSpy).toHaveBeenCalledTimes(1);    // the composable settling the stale query

    // Quiescence: no further navigation across two more flushes.
    await flush(); await nextTick();
    await flush(); await nextTick();
    expect(pushSpy).toHaveBeenCalledTimes(1);
    expect(replaceSpy).toHaveBeenCalledTimes(1);
    expect(router.currentRoute.value.fullPath).toBe('/browse');
  });
});

describe('useStateRouteSync — unknown URL', () => {
  it('normalizes an unmatched URL to / and shows the gate', async () => {
    const { c, router } = await setup('/nope');
    expect(router.currentRoute.value.fullPath).toBe('/');
    expect(c.state.screen).toBe('gate');
  });
});

// ---------------------------------------------------------------------------------------
// A-I7 / A-I8: the permission matrix has the second say.
//
// `guard()` asks three questions in order — is this a member route at all, is the visitor
// signed in, does the visitor hold the route's permission — and the third one needs a
// principal. This is the composable actually supplying one. Without it, `guard`'s
// `ROUTE_PERMS` branch is unreachable in the running app and the client would show a screen
// the API is going to refuse.
//
// Nothing is REMEMBERED for a refusal (`pending: null`): unlike the signed-out case, there
// is no later moment at which the same account becomes allowed in, so holding the URL open
// would be holding it open forever.
//
// `gate: 'unavailable'` renders an EMPTY gate column today: the design has no such state and
// "absent beats faked" forbids inventing one, so Task I8b adds it with John's copy (the
// title is ruled — "This page is not available to your account"). Known and recorded in
// A-I8.1, deliberately not patched around here.
// ---------------------------------------------------------------------------------------
describe('useStateRouteSync — the route permission (A-I7 hand-over, executed by A-I8)', () => {
  const BUYER: Me = { ...MEMBER, role: 'Approved buyer', roles: ['buyer'] };
  const APPLICANT: Me = { ...MEMBER, role: 'Applicant', roles: [], state: 'pending' };

  it('honours a deep link the account holds the permission for', async () => {
    const { c } = await setup('/seller', MEMBER);
    c.setState({ auth: true });
    await flush(); await nextTick();
    expect(c.state.screen).toBe('seller');
  });

  it('sends a signed-in account that does not hold the route permission to the unavailable gate', async () => {
    // `page.seller` is `["seller"]` only, so a buyer-only account is allowed nowhere near the
    // seller dashboard. Driven IN SESSION (signed in first, then navigate), which is the path
    // `guard` is consulted on — see the recorded gap at the bottom of this block for the one
    // path it is not.
    const { c, router } = await setup('/', BUYER);
    c.setState({ auth: true });
    await flush(); await nextTick();

    await router.push('/seller');
    await flush(); await nextTick();
    expect(c.state.screen).toBe('gate');
    expect(c.state.gate).toBe('unavailable');
    expect(router.currentRoute.value.fullPath, 'the URL settles to the gate: nothing is pending, so nothing holds it open').toBe('/');
  });

  it('refuses an in-session navigation to a route the account does not hold', async () => {
    const { c, router } = await setup('/browse', BUYER);
    c.setState({ auth: true });
    await flush(); await nextTick();
    expect(c.state.screen, 'a buyer holds page.browse').toBe('browse');

    await router.push('/admin');
    await flush(); await nextTick();
    expect(c.state.gate, 'page.admin is ["admin","staff"]').toBe('unavailable');
  });

  it('a non-active account is an applicant whatever it was granted, so no member route opens', async () => {
    // `effectiveRoles` (can.ts) returns `['applicant']` for any state but `active`, so this
    // account's `admin` grant buys it nothing — the rule the server enforces, mirrored here.
    const { c, router } = await setup('/', APPLICANT);
    c.setState({ auth: true });
    await flush(); await nextTick();
    expect(c.state.screen).toBe('gate');

    await router.push('/browse');
    await flush(); await nextTick();
    expect(c.state.gate, 'page.browse is ["admin","buyer","seller","staff"]; an applicant is none of them').toBe('unavailable');
  });

  it('an anonymous visitor still gets the sign-in gate, not the unavailable one — the fail-closed order', async () => {
    // `guard`'s three questions in order: a member route at all, signed in, permitted. Signed out
    // is answered SECOND, before the matrix is consulted, so a visitor with no account gets the
    // sign-in gate and keeps their deep link — not the `unavailable` gate, which would tell
    // somebody who has simply not signed in that their account may not have this page.
    //
    // It is also the only case that exercises `setup()`'s null branch (`useMe().clear()`), i.e.
    // the composable reading a genuinely empty store rather than a principal.
    const { c, router } = await setup('/admin', null);
    expect(c.state.screen).toBe('gate');
    expect(c.state.gate, 'signed out is answered before the matrix is consulted').toBe('signin');
    expect(router.currentRoute.value.fullPath, 'the deep link is held open until auth arrives').toBe('/admin');
  });

  // ---------------------------------------------------------------------------------------
  // The remembered deep link is permission-checked TOO (review round 1, G).
  //
  // `guard()` is consulted on the route → state side, but the patch a SIGNED-OUT deep link leaves
  // behind used to be applied by the watcher without a second call — so a visitor who deep-linked
  // a route their account does not hold, and then signed in, landed on it. The principal is not
  // knowable at the moment the link is remembered and is knowable at the moment it is applied,
  // which is where the check now happens.
  // ---------------------------------------------------------------------------------------
  it('permission-checks the remembered deep link when auth arrives, not only when it was typed', async () => {
    const { c, router } = await setup('/admin', BUYER);
    expect(c.state.gate, 'signed out, so the sign-in gate — and the link is remembered').toBe('signin');
    expect(router.currentRoute.value.fullPath, 'the URL stays as typed until auth arrives').toBe('/admin');

    c.setState({ auth: true });
    await flush(); await nextTick();

    expect(c.state.screen, 'page.admin is ["admin","staff"]; a buyer holds neither').toBe('gate');
    expect(c.state.gate).toBe('unavailable');
    expect(router.currentRoute.value.fullPath, 'nothing is pending any more, so the URL settles').toBe('/');
  });

  it('still honours a remembered deep link the account DOES hold', async () => {
    const { c, router } = await setup('/browse', BUYER);
    expect(c.state.gate).toBe('signin');

    c.setState({ auth: true });
    await flush(); await nextTick();

    expect(c.state.screen).toBe('browse');
    expect(router.currentRoute.value.fullPath).toBe('/browse');
  });

  it('honours a remembered deep link into a non-Browse route for an account that holds it', async () => {
    // The seller dashboard, for the account that can open it — the case that proves the new
    // `guard` call passes the PATCH through rather than flattening every pending link to Browse.
    const { c, router } = await setup('/seller', MEMBER);
    c.setState({ auth: true });
    await flush(); await nextTick();
    expect(c.state.screen).toBe('seller');
    expect(router.currentRoute.value.fullPath).toBe('/seller');
  });
});
