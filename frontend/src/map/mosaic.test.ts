import { describe, expect, it } from 'vitest';
import { BBOX_PAD_LAT, BBOX_PAD_LNG, MOSAIC_STEP, mosaicBbox, mosaicCells } from './mosaic.js';

const site = (name: string, lat: number, lng: number) => ({ name, lat, lng, values: {} });

describe('mosaicCells — the community mosaic geometry, ported from MarketMapV3.jsx:57-95', () => {
  it('uses the approved step and bbox padding', () => {
    expect(MOSAIC_STEP).toBe(0.0055);
    expect(BBOX_PAD_LAT).toBe(0.13);
    expect(BBOX_PAD_LNG).toBe(0.15);
  });

  it('pads the bounding box 0.13 lat / 0.15 lng around the community extent', () => {
    expect(mosaicBbox([site('a', 30.2, -97.9), site('b', 30.6, -97.6)])).toEqual({
      minLat: 30.2 - 0.13, maxLat: 30.6 + 0.13, minLng: -97.9 - 0.15, maxLng: -97.6 + 0.15
    });
  });

  it('tiles the bbox at `step` and gives each cell square bounds of exactly one step', () => {
    const bbox = { minLat: 30, maxLat: 30.02, minLng: -97.02, maxLng: -97 };
    const cells = mosaicCells([site('a', 30.01, -97.01)], bbox, 0.01);
    expect(cells).toHaveLength(4);                                   // 2 rows x 2 columns
    const [[lat0, lng0], [lat1, lng1]] = cells[0].bounds;
    expect(lat1 - lat0).toBeCloseTo(0.01, 10);
    expect(lng1 - lng0).toBeCloseTo(0.01, 10);
    expect(lat0).toBeCloseTo(30, 10);
    expect(lng0).toBeCloseTo(-97.02, 10);
  });

  it('assigns every cell to its NEAREST community centroid, longitude scaled by cos(lat)', () => {
    const bbox = { minLat: 30, maxLat: 30.04, minLng: -97.02, maxLng: -97 };
    const cells = mosaicCells([site('north', 30.035, -97.01), site('south', 30.005, -97.01)], bbox, 0.01);
    const owner = (lat: number) => cells.find((c) => Math.abs(c.bounds[0][0] - lat) < 1e-9)!.site.name;
    expect(owner(30)).toBe('south');
    expect(owner(30.03)).toBe('north');
  });

  it('drops a cell whose nearest community is farther than the 0.016 squared-degree cutoff, rather than shading empty country', () => {
    const bbox = { minLat: 30, maxLat: 30.02, minLng: -97.02, maxLng: -97 };
    expect(mosaicCells([site('far', 31.5, -96)], bbox, 0.01)).toEqual([]);
  });

  it('returns no cells at all when there are no communities', () => {
    expect(mosaicCells([], { minLat: 30, maxLat: 30.02, minLng: -97.02, maxLng: -97 }, 0.01)).toEqual([]);
  });
});
