// @vitest-environment jsdom
//
// The real entry point (index.html's <script type="module" src="/src/main.ts">): imports the
// app's singleton router (routes.ts, createWebHistory) and the two global stylesheets, reads the
// account AND the listings before it mounts, then bootstraps into '#app' by selector — the one
// thing every other test exercises through bootstrap.ts directly (bootstrap.test.ts) or a
// memory-history router built from `routes` (useStateRouteSync.test.ts), never this file itself.
//
// I1 (review round 1): `P` and `MARKETS` are read through `await import('./logic.js')` AFTER the
// module registry has been reset and `main.ts` has run, never through a top-level import.
// `vi.resetModules()` clears the registry so each test's `import('./main')` re-evaluates main.ts
// AND its dependency graph — `src/logic.js` included — so a statically imported `P` would be the
// FIRST module instance, which nothing under test ever touches, and every "the fixtures survive"
// assertion would pass even if `loadListings` wiped the arrays.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

/** The prototype's fixture arrays as the instance under test sees them, after main.ts ran. */
async function loadedFixtures(): Promise<{ ids: string[]; markets: string[] }> {
  const { MARKETS, P } = await import('./logic.js');
  return {
    ids: (P as unknown as Array<{ id: string }>).map((p) => p.id),
    markets: Object.keys(MARKETS as unknown as Record<string, unknown>)
  };
}

/** The same arrays read from a pristine registry — what "unchanged" has to mean. */
let pristine: { ids: string[]; markets: string[] };

beforeEach(async () => {
  vi.resetModules();
  pristine = await loadedFixtures();
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
    expect(document.getElementById('app')?.childElementCount).toBeGreaterThan(0);
    // Spec D6 / pre-flight I5: a 401 at the gate leaves the prototype's arrays exactly as the
    // design wrote them — the visitor gets the sign-in card, never a blank or empty Browse.
    expect(await loadedFixtures()).toEqual(pristine);
  });

  it('still mounts, on the design’s fixtures, when the network is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network down'); }));

    await import('./main');
    await flush();
    await flush();

    expect(document.getElementById('app')?.childElementCount).toBeGreaterThan(0);
    expect(await loadedFixtures()).toEqual(pristine);
  });

  // A-L6.2 (1) / review C1: an empty catalogue is the state QA is in between Task L7's deploy
  // and its seed. The design cannot render one, so the fixtures stay and the app mounts on them.
  it('still mounts, on the design’s fixtures, when the catalogue is empty', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string) => (
      String(input).startsWith('/api/listings')
        ? new Response('{"items":[],"next_cursor":null}', { status: 200, headers: { 'content-type': 'application/json' } })
        : new Response('', { status: 401 })
    )));

    await import('./main');
    await flush();
    await flush();

    expect(document.getElementById('app')?.childElementCount).toBeGreaterThan(0);
    expect(await loadedFixtures()).toEqual(pristine);
  });

  // A-L6.2 (1) / review I2: `applyListings` sits outside `loadListings`' try, so a malformed ROW
  // inside a well-formed page still throws out of it. The listings arm catches exactly like the
  // account arm — otherwise `Promise.all` rejects, `bootstrap()` never runs and the page is blank.
  it('still mounts when the listings read throws outright', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string) => (
      String(input).startsWith('/api/listings')
        ? new Response('{"items":[null],"next_cursor":null}', { status: 200, headers: { 'content-type': 'application/json' } })
        : new Response('', { status: 401 })
    )));

    await import('./main');
    await flush();
    await flush();

    expect(document.getElementById('app')?.childElementCount).toBeGreaterThan(0);
    expect(await loadedFixtures()).toEqual(pristine);
  });
});
