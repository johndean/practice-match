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
import { routes } from './routes';
import { useStateRouteSync } from './useStateRouteSync';

// Vue's watchers flush on a microtask; router navigation resolves on a promise chain too.
// A macrotask tick (setTimeout) drains both, which is why this is used instead of a bare
// await nextTick() between steps that involve a navigation.
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

let apps: ReturnType<typeof createApp>[] = [];
afterEach(() => { apps.forEach((a) => a.unmount()); apps = []; });

async function setup(initialPath = '/') {
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
