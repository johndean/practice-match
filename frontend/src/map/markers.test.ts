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
  it('clusterIcon and clusterize', () => {
    expect(clusterIcon(3)).toContain('>3</div>');
    const ms = [{ id: 'a', lat: 30.30, lng: -97.70 }, { id: 'b', lat: 30.31, lng: -97.71 }, { id: 'c', lat: 31.9, lng: -99.0 }];
    expect(clusterize(ms, 10).map((e) => e.kind)).toEqual(['pin', 'pin', 'pin']);
    const z8 = clusterize(ms, 8);
    expect(z8.find((e) => e.kind === 'cluster')?.ids).toEqual(['a', 'b']);
  });
});
