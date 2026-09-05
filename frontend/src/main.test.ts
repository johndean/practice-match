// @vitest-environment jsdom
//
// The real entry point (index.html's <script type="module" src="/src/main.ts">): imports the
// app's singleton router (routes.ts, createWebHistory) and the two global stylesheets, then
// bootstraps into '#app' by selector — the one thing every other test exercises through
// bootstrap.ts directly (bootstrap.test.ts) or a memory-history router built from `routes`
// (useStateRouteSync.test.ts), never this file itself.
import { afterEach, describe, expect, it } from 'vitest';

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

afterEach(() => {
  document.body.innerHTML = '';
});

describe('main.ts', () => {
  it('bootstraps the real router into #app by selector', async () => {
    document.body.innerHTML = '<div id="app"></div>';

    await import('./main');
    await flush();

    const root = document.getElementById('app');
    expect(root?.childElementCount).toBeGreaterThan(0);
  });
});
