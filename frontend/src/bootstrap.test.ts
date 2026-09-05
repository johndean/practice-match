// @vitest-environment jsdom
//
// Regression test for the router-mount-order bug: `router.isReady()` only resolves once
// `router.install()` (i.e. `app.use(router)`) has triggered the router's own first
// navigation. Uses a real router built from the app's own route table (routes.ts) on
// createMemoryHistory, and a real detached <div> — no mocks, no stub router.
import { afterEach, describe, expect, it } from 'vitest';
import { createMemoryHistory, createRouter, type Router } from 'vue-router';
import type { App } from 'vue';
import { bootstrap } from './bootstrap';
import { routes } from './router/routes';

const TIMEOUT = Symbol('timeout');
const timeout = (ms: number) => new Promise<typeof TIMEOUT>((resolve) => setTimeout(() => resolve(TIMEOUT), ms));

let apps: App[] = [];
afterEach(() => { apps.forEach((a) => a.unmount()); apps = []; });

function memoryRouter(): Router {
  return createRouter({ history: createMemoryHistory(), routes });
}

describe('bootstrap', () => {
  it('mounts once the router is ready', async () => {
    const router = memoryRouter();
    const el = document.createElement('div');

    const app = await bootstrap(router, el);
    apps.push(app);

    expect(el.childElementCount).toBeGreaterThan(0);
    expect(router.currentRoute.value.fullPath).toBe('/');
  });

  it('installs the router before waiting for it — awaiting isReady() first would never resolve', async () => {
    const router = memoryRouter();

    // Without `use(router)`, nothing ever triggers the router's first navigation, so
    // `isReady()` never settles. This pins the vue-router behaviour `bootstrap()` relies on:
    // if this assertion ever fails, `bootstrap()`'s ordering no longer matters and the fix
    // (and this whole test) should be revisited.
    const racedAlone = await Promise.race([router.isReady().then(() => 'ready' as const), timeout(50)]);
    expect(racedAlone).toBe(TIMEOUT);

    // `bootstrap()` calls `use(router)` before awaiting `isReady()`, so it resolves quickly
    // even though the same router just sat unready for 50ms above.
    const el = document.createElement('div');
    const racedBoot = await Promise.race([
      bootstrap(router, el).then((app) => { apps.push(app); return 'booted' as const; }),
      timeout(2000)
    ]);
    expect(racedBoot).toBe('booted');
  });
});
