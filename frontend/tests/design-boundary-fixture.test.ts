import { describe, expect, it } from 'vitest';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { DESIGN_AREAS_LITERAL } from './design-boundary-fixture';

// The fixture is generated (scripts/export_design_boundaries.py) and embedded verbatim into
// amendment A24.1's `replace`, which means it is embedded verbatim into the approved design file.
// Everything asserted here is a property the amendment depends on; nothing here is a number typed
// by hand — the counts are read from the fixture itself.
describe('the design boundary fixture (A24.1, spec §9.4)', () => {
  const fixture = JSON.parse(DESIGN_AREAS_LITERAL) as Record<string, { type: string; features: { type: string; id: string; properties: { geo_id: string; name: string; c: [number, number] }; geometry: { type: string; coordinates: unknown[] } }[] }>;

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

  // THE COMMITTED BYTES ARE THE ARTEFACT, and this is what stops them being regenerated casually.
  // `ST_SimplifyPreserveTopology` is NON-DETERMINISTIC: Task 3 measured five distinct geometries
  // from six identical queries against one unchanging row in a single psql session (PostGIS 3.5 /
  // GEOS). A24.1 interpolates this literal VERBATIM into the approved design file, so a
  // regeneration moves the design file and every map baseline with it, for no design reason — and
  // a reviewer cannot tell that drift from a real change. So this file is pinned the way the
  // pristine bundle twins are pinned in `design-amendments.test.ts`: by its hash.
  //
  // The hash is NOT a number to retype when the gate goes red. A red here means the fixture has
  // been regenerated, and the question to answer before touching this line is whether there was a
  // RULED reason to regenerate it (a new vintage, a new metro, a new tolerance). If there was, the
  // baselines re-base under that ruling and the hash moves with them. If there was not, restore
  // the committed file (`git checkout -- frontend/tests/design-boundary-fixture.ts`) and leave
  // this line alone. Regenerated 2026-09-11 under D-C49 (coarsen as committed, then repair).
  it('is the frozen artefact, byte for byte — the generator is not reproducible', () => {
    const source = readFileSync(fileURLToPath(new URL('design-boundary-fixture.ts', import.meta.url)));
    expect(createHash('sha256').update(source).digest('hex')).toBe('9d5e9d9ba6f7519f65904e3a2b8579aead047d6555fce3ecac47dc80187e2102');
  });

  // D-C49 (John, 2026-09-11): coarsen at the committed tolerance, then repair, so the fixture is
  // both inside the cap and geometrically valid. A GeometryCollection is what `ST_MakeValid`
  // answers a spike with, and it is legal GeoJSON — `L.geoJSON` would draw its line parts as a
  // stroke the design has no class for — so the generator extracts the areal parts. Measured on
  // these committed bytes through PostGIS: 165 features, 0 invalid, 0 empty.
  it('carries only non-empty areal geometries, at every ruled level', () => {
    for (const level of Object.keys(fixture)) {
      for (const f of fixture[level].features) {
        expect(['Polygon', 'MultiPolygon'], `${f.id} is a ${f.geometry.type}`).toContain(f.geometry.type);
        expect((f.geometry as { coordinates: unknown[] }).coordinates.length, `${f.id} is empty`).toBeGreaterThan(0);
      }
    }
  });

  it('is pure ASCII and inside the 120 KB cap the design file can carry', () => {
    const source = readFileSync(fileURLToPath(new URL('design-boundary-fixture.ts', import.meta.url)), 'utf8');
    expect(/^[\x00-\x7F]*$/.test(source), 'a non-ASCII byte reaches the design file through A24.1').toBe(true);
    expect(Buffer.byteLength(source, 'utf8')).toBeLessThanOrEqual(120_000);
    expect(source, 'the generated file must name its generator').toContain('scripts/export_design_boundaries.py');
  });
});
