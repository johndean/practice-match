// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { loadLeaflet, BASEMAPS, LABEL_TILES } from './leaflet.js';

describe('loadLeaflet', () => {
  it('resolves the bundled Leaflet without injecting CDN tags', async () => {
    const L = await loadLeaflet();
    expect(typeof L.map).toBe('function');
    expect(L.version).toBe('1.9.4');
    expect(document.querySelectorAll('script[src*="unpkg.com"], link[href*="unpkg.com"]').length).toBe(0);
  });
  // Both sides of `if (!window.L)`, which nothing covered (M10: this file is hand-written and
  // has a test file of its own, so it belongs under the same gate as the rest of `src/`).
  // Importing the npm build already exposes `window.L` under jsdom, so the assignment is only
  // reachable from a page that has not exposed it — which is the case the guard exists for.
  const globals = window as unknown as { L?: unknown };
  it('exposes the bundled Leaflet as `window.L` when the page has not', async () => {
    const exposed = globals.L;
    delete globals.L;
    try {
      const L = await loadLeaflet();
      expect(globals.L, 'loadLeaflet must publish the global the prototype reads').toBe(L);
      expect((L as { version: string }).version).toBe('1.9.4');
    } finally {
      globals.L = exposed;
    }
  });

  it('reuses an already-exposed global instead of reassigning it', async () => {
    const exposed = globals.L;
    const sentinel = { map: () => undefined, version: 'already-here' };
    globals.L = sentinel;
    try {
      expect(await loadLeaflet(), 'a second map mount must not replace the live Leaflet global').toBe(sentinel);
    } finally {
      globals.L = exposed;
    }
  });

  it('keeps the approved Esri basemap configuration', () => {
    expect(BASEMAPS.map.url).toContain('World_Light_Gray_Base');
    expect(BASEMAPS.map.attribution).toBe('Tiles © Esri');
    expect(BASEMAPS.satellite.attribution).toBe('Imagery © Esri, Maxar, Earthstar Geographics');
    expect(LABEL_TILES).toContain('World_Light_Gray_Reference');
  });
});
