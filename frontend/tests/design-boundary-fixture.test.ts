import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { DESIGN_AREAS_LITERAL } from './design-boundary-fixture';

// The fixture is generated (scripts/export_design_boundaries.py) and embedded verbatim into
// amendment A24.1's `replace`, which means it is embedded verbatim into the approved design file.
// Everything asserted here is a property the amendment depends on; nothing here is a number typed
// by hand — the counts are read from the fixture itself.
describe('the design boundary fixture (A24.1, spec §9.4)', () => {
  const fixture = JSON.parse(DESIGN_AREAS_LITERAL) as Record<string, { type: string; features: { type: string; id: string; properties: { geo_id: string; name: string; c: [number, number] }; geometry: { type: string } }[] }>;

  it('carries one FeatureCollection per ruled geography, and nothing else (D-C35)', () => {
    expect(Object.keys(fixture).sort()).toEqual(['050', '160', '860']);
    for (const level of Object.keys(fixture)) expect(fixture[level].type).toBe('FeatureCollection');
  });

  it('is valid JavaScript object-literal syntax, on one line, so A24.1 can interpolate it raw', () => {
    expect(DESIGN_AREAS_LITERAL).not.toContain('\n');
    // A JSON text is a JS object literal; this proves it parses as one on the runtime that will
    // evaluate the design's script, not only as JSON.
    expect(() => new Function(`return ${DESIGN_AREAS_LITERAL};`)()).not.toThrow();
  });

  it('every feature carries the geo_id, the name, the centroid and the geometry areaSet reads', () => {
    for (const level of Object.keys(fixture)) {
      expect(fixture[level].features.length, `${level} is empty`).toBeGreaterThan(0);
      for (const f of fixture[level].features) {
        expect(f.type).toBe('Feature');
        expect(f.id).toBe(f.properties.geo_id);
        expect(typeof f.properties.name).toBe('string');
        expect(f.properties.c).toHaveLength(2);
        const [lat, lng] = f.properties.c;
        // The design's own metro. A centroid outside it is a scoping bug in the generator.
        expect(lat, `${f.id} is not in the Austin metro`).toBeGreaterThan(29);
        expect(lat).toBeLessThan(32);
        expect(lng).toBeGreaterThan(-99);
        expect(lng).toBeLessThan(-96);
        expect(['Polygon', 'MultiPolygon']).toContain(f.geometry.type);
      }
    }
    // No feature carries a figure: the design assigns those from its own communities (§9.4).
    const props = fixture['860'].features.flatMap((f) => Object.keys(f.properties));
    expect([...new Set(props)].sort()).toEqual(['c', 'geo_id', 'name']);
  });

  it('is pure ASCII and inside the 120 KB cap the design file can carry', () => {
    const source = readFileSync(fileURLToPath(new URL('design-boundary-fixture.ts', import.meta.url)), 'utf8');
    expect(/^[\x00-\x7F]*$/.test(source), 'a non-ASCII byte reaches the design file through A24.1').toBe(true);
    expect(Buffer.byteLength(source, 'utf8')).toBeLessThanOrEqual(120_000);
    expect(source, 'the generated file must name its generator').toContain('scripts/export_design_boundaries.py');
  });
});
