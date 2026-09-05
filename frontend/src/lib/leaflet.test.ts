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
  it('keeps the approved Esri basemap configuration', () => {
    expect(BASEMAPS.map.url).toContain('World_Light_Gray_Base');
    expect(BASEMAPS.map.attribution).toBe('Tiles © Esri');
    expect(BASEMAPS.satellite.attribution).toBe('Imagery © Esri, Maxar, Earthstar Geographics');
    expect(LABEL_TILES).toContain('World_Light_Gray_Reference');
  });
});
