// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';
import { loadLeaflet, BASEMAPS, LABEL_TILES } from './leaflet.js';

/** The amended design this file is a hand-written port of (spec §3). Read, never re-typed: the
 *  basemap constants are the one thing both files spell out, so they are compared rather than
 *  copied. */
// `import.meta.dirname`, not `new URL(..., import.meta.url)`: this file runs under jsdom, where
// `import.meta.url` is the served http URL and `fileURLToPath` refuses it (ImageSlot.test.ts's
// own note).
const DESIGN_JSX = join(import.meta.dirname, '../../../docs/design-reference/design_handoff_practice_match_v3/MarketMapV3.jsx');

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
    expect(LABEL_TILES).toContain('World_Light_Gray_Reference');
  });

  // A35.7 (ruling D-C52, 2026-09-13). MEASURED from the service itself on the day:
  // `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer?f=pjson` carries
  // `"copyrightText": "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community"`.
  // The design and this port both said "Imagery © Esri, Maxar, Earthstar Geographics" — Maxar is
  // the vendor's former name, and the service's own description now credits "Vantor imagery at
  // 0.3m resolution". Attribution is legally load-bearing on this project (CLAUDE.md), so the
  // string is Esri's own credit line VERBATIM rather than one composed from it — the same rule
  // `dataset_registry.attribution_text` follows for every Census dataset.
  //
  // The gray canvas's "Tiles © Esri" is NOT touched: it is the approved design's own string and
  // John's ruling names it, and D-C52 reaches the satellite line alone.
  const SATELLITE_ATTRIBUTION = 'Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community';
  it('credits the satellite imagery with Esri\'s own current copyrightText (A35.7)', () => {
    expect(BASEMAPS.satellite.attribution).toBe(SATELLITE_ATTRIBUTION);
    expect(BASEMAPS.satellite.attribution, 'Maxar is the vendor\'s former name; the service says Vantor').not.toContain('Maxar');
    // …and the design says the same thing, because this file is its port and the amended design is
    // the authority (spec §3). Compared, never copied.
    expect(readFileSync(DESIGN_JSX, 'utf8')).toContain(`attribution: ${JSON.stringify(SATELLITE_ATTRIBUTION)}`);
  });

  // A35.1/A35.2 — the last zoom level each service actually has a tile for. Esri publishes the
  // gray Canvas basemaps "from Level 14 through Level 16" in North America and answers HTTP 200
  // with a grey "Map data not yet available" JPEG past it; World_Imagery is real to z19 at every
  // US point probed (0.3 m, Esri's published US floor) and deeper in some metros, which is not
  // knowable client-side. These are the values Leaflet requests at; the DISPLAY ceiling is 20 and
  // belongs to the map, not to a basemap.
  it('declares the native zoom each Esri service is actually cached to (A35.1/A35.2)', () => {
    expect(BASEMAPS.map.maxNativeZoom).toBe(16);
    expect(BASEMAPS.satellite.maxNativeZoom).toBe(19);
    const jsx = readFileSync(DESIGN_JSX, 'utf8');
    expect(jsx).toContain('maxNativeZoom: 16');
    expect(jsx).toContain('maxNativeZoom: 19');
  });
});
