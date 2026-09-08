// @vitest-environment jsdom
//
// The real entry point (index.html's <script type="module" src="/src/main.ts">): imports the
// app's singleton router (routes.ts, createWebHistory) and the two global stylesheets, reads the
// account AND the listings before it mounts, then bootstraps into '#app' by selector — the one
// thing every other test exercises through bootstrap.ts directly (bootstrap.test.ts) or a
// memory-history router built from `routes` (useStateRouteSync.test.ts), never this file itself.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MARKETS, P } from './logic.js';

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

// The design's own fixture data, as it stands before main.ts runs. Both cases below assert it is
// still there afterwards: a refused or broken read must leave the prototype's arrays alone.
const FIXTURE_IDS = (P as unknown as Array<{ id: string }>).map((p) => p.id);
const FIXTURE_MARKETS = Object.keys(MARKETS as unknown as Record<string, unknown>);

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = '<div id="app"></div>';
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

describe('main.ts', () => {
  it('bootstraps the real router into #app by selector after asking the API for listings', async () => {
    // A refused read is the ordinary signed-out case AND the case this test wants: the design's
    // fixtures survive, so the assertion below is about mounting, not about seeded data.
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 401 })));

    await import('./main');
    await flush();
    await flush();

    expect(fetch).toHaveBeenCalledWith('/api/listings?limit=200', expect.anything());
    const root = document.getElementById('app');
    expect(root?.childElementCount).toBeGreaterThan(0);
    // Spec D6 / pre-flight I5: a 401 at the gate leaves the prototype's arrays exactly as the
    // design wrote them — the visitor gets the sign-in card, never a blank or empty Browse.
    expect((P as unknown as Array<{ id: string }>).map((p) => p.id)).toEqual(FIXTURE_IDS);
    expect(Object.keys(MARKETS as unknown as Record<string, unknown>)).toEqual(FIXTURE_MARKETS);
  });

  it('still mounts, on the design’s fixtures, when the network is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network down'); }));

    await import('./main');
    await flush();
    await flush();

    const root = document.getElementById('app');
    expect(root?.childElementCount).toBeGreaterThan(0);
    expect((P as unknown as Array<{ id: string }>).map((p) => p.id)).toEqual(FIXTURE_IDS);
    expect(Object.keys(MARKETS as unknown as Record<string, unknown>)).toEqual(FIXTURE_MARKETS);
  });
});
