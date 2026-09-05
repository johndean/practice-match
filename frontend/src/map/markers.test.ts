import { describe, expect, it } from 'vitest';
import { clusterIcon, clusterize, dot, pill, pricePin } from './markers.js';

describe('marker HTML builders (moved from lib/leaflet.js)', () => {
  it('dot', () => {
    expect(dot(20, '#003a70')).toBe('<div style="width:20px;height:20px;border-radius:999px;background:#003a70;border:2px solid rgba(255,255,255,.85);box-sizing:border-box;"></div>');
    expect(dot(10, 'rgba(120,86,190,.75)', 'rgba(255,255,255,.9)')).toContain('border:2px solid rgba(255,255,255,.9)');
  });
  it('pricePin active/inactive', () => {
    expect(pricePin('$1.45M', true)).toContain('background:var(--vf-navy);color:var(--vf-white);');
    expect(pricePin('$1.45M', false)).toContain('border:1px solid #d4dde5;');
  });
  it('pill muted/active', () => {
    expect(pill('$860K', false, true)).toContain('background:var(--color-steel);color:var(--color-white);');
    expect(pill('$860K', true, false)).toContain('transform:translateY(-2px)');
  });
  it('pill neither muted nor active falls back to the default (unselected) palette', () => {
    const html = pill('$860K', false, false);
    expect(html).toContain('background:var(--color-white);color:var(--color-navy);');
    expect(html).toContain('border:1px solid var(--border-subtle);');
    expect(html).toContain('transform:translateY(0)');
  });
  it('clusterIcon and clusterize', () => {
    expect(clusterIcon(3)).toContain('>3</div>');
    const ms = [{ id: 'a', lat: 30.30, lng: -97.70 }, { id: 'b', lat: 30.31, lng: -97.71 }, { id: 'c', lat: 31.9, lng: -99.0 }];
    expect(clusterize(ms, 10).map((e) => e.kind)).toEqual(['pin', 'pin', 'pin']);
    const z8 = clusterize(ms, 8);
    expect(z8.find((e) => e.kind === 'cluster')?.ids).toEqual(['a', 'b']);
  });
  it('clusterize uses the wider cell below zoom 8', () => {
    // Cell 0.9 (below zoom 8) buckets these two points together; cell 0.28 (zoom 8-9) would
    // not, since 0.9 rounds both to the same grid cell while 0.28 keeps them apart.
    const ms = [{ id: 'a', lat: 30.30, lng: -97.70 }, { id: 'b', lat: 30.70, lng: -97.90 }];
    const clustered = clusterize(ms, 5);
    expect(clustered).toHaveLength(1);
    expect(clustered[0].kind).toBe('cluster');
    expect(clustered[0].lat).toBeCloseTo(30.5);
    expect(clustered[0].lng).toBeCloseTo(-97.8);
    expect(clustered[0].count).toBe(2);
    expect(clustered[0].ids).toEqual(['a', 'b']);
  });
});
