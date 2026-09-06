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

  // Review M1: the case above puts both communities on the SAME longitude, so the cos(lat)
  // factor scales both candidates identically and can never decide the winner. Here it does:
  // at lat 60 (cos = 0.5) the community 0.012 deg EAST is effectively 0.006 away and beats the
  // one 0.010 deg NORTH. Delete `* Math.cos(...)` and 'north' wins instead — which is exactly
  // how a missing cos() mis-assigns cells wherever two communities compete mainly in longitude.
  it('lets the cos(lat) longitude scaling decide the owner when the competition is east-west', () => {
    const bbox = { minLat: 60, maxLat: 60.005, minLng: -97, maxLng: -96.995 };   // exactly one cell, centred (60.005, -96.995)
    const cells = mosaicCells([site('north', 60.015, -96.995), site('east', 60.005, -96.983)], bbox, 0.01);
    expect(cells).toHaveLength(1);
    expect(cells[0].site.name).toBe('east');
  });

  // Review M3: every distance is measured from the cell's CENTRE, half a step in from its
  // corner (~300 m at the shipped step of 0.0055). Here the midline between the two
  // communities (lat 30.0025) runs between the cell's corner (30) and its centre (30.005), so
  // corner and centre disagree: measure from the corner and 'south' wins.
  it('measures from the cell CENTRE, not its corner: the half-step offset decides the owner on a midline', () => {
    const bbox = { minLat: 30, maxLat: 30.005, minLng: -97, maxLng: -96.995 };   // exactly one cell, centred (30.005, -96.995)
    const cells = mosaicCells([site('south', 29.9925, -96.995), site('north', 30.0125, -96.995)], bbox, 0.01);
    expect(cells).toHaveLength(1);
    expect(cells[0].site.name).toBe('north');
  });

  it('drops a cell whose nearest community is farther than the 0.016 squared-degree cutoff, rather than shading empty country', () => {
    const bbox = { minLat: 30, maxLat: 30.02, minLng: -97.02, maxLng: -97 };
    expect(mosaicCells([site('far', 31.5, -96)], bbox, 0.01)).toEqual([]);
  });

  // Review M2: the case above proves a VERY distant community is dropped, which leaves the
  // threshold unpinned from below — shrink it and the mosaic all but disappears with every
  // test still green. This brackets 0.016 from both sides, in squared degrees: a centroid
  // 0.126 deg away (0.015876) is inside and its cell is kept; 0.127 deg (0.016129) is outside.
  it('brackets the 0.016 squared-degree cutoff: just inside is kept, just outside is dropped', () => {
    const bbox = { minLat: 30, maxLat: 30.005, minLng: -97, maxLng: -96.995 };   // exactly one cell, centred (30.005, -96.995)
    const kept = mosaicCells([site('inside', 30.131, -96.995)], bbox, 0.01);
    expect(kept).toHaveLength(1);
    expect(kept[0].site.name).toBe('inside');
    expect(mosaicCells([site('outside', 30.132, -96.995)], bbox, 0.01)).toEqual([]);
  });

  it('returns no cells at all when there are no communities', () => {
    expect(mosaicCells([], { minLat: 30, maxLat: 30.02, minLng: -97.02, maxLng: -97 }, 0.01)).toEqual([]);
  });
});
