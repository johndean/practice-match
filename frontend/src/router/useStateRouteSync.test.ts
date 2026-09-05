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
import type { RoutedState } from './sync';

// Vue's watchers flush on a microtask; router navigation resolves on a promise chain too.
// A macrotask tick (setTimeout) drains both, which is why this is used instead of a bare
// await nextTick() between steps that involve a navigation.
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

// logic.js's initial state literal never assigns `browseMode` (only go()/routing ever sets
// it), so TypeScript infers Component['state'] without that key. This test-only view widens
// the type for the routing-relevant fields without touching logic.js.
const routed = (c: InstanceType<typeof Component>) => c.state as unknown as RoutedState & { auth?: boolean };

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
  it('pushes the URL when state changes: browse+market, then admin+data', async () => {
    const { c, router } = await setup('/');
    c.setState({ screen: 'browse', browseMode: 'market', auth: true });
    await flush(); await nextTick();
    expect(router.currentRoute.value.fullPath).toBe('/browse?tab=market');

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
    expect(routed(c).browseMode).toBe('market');
    expect(router.currentRoute.value.fullPath).toBe('/browse?tab=market');
  });

  it('applies the pending route when only auth flips (no screen change in the same setState)', async () => {
    const { c } = await setup('/browse?tab=market');
    c.setState({ auth: true });
    await flush(); await nextTick();
    expect(c.state.screen).toBe('browse');
    expect(routed(c).browseMode).toBe('market');
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
});

describe('useStateRouteSync — unknown URL', () => {
  it('normalizes an unmatched URL to / and shows the gate', async () => {
    const { c, router } = await setup('/nope');
    expect(router.currentRoute.value.fullPath).toBe('/');
    expect(c.state.screen).toBe('gate');
  });
});
