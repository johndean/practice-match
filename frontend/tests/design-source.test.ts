import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const ROOT = join(FRONTEND, '..');
const V3 = 'design_handoff_practice_match_v3';
const V3_FILE = 'Practice Match V3.dc.html';

// Docs/config drift gate: every pointer at "the approved design" must name ONE folder. When
// the reference moves, these four move together or the toolchain silently regenerates,
// screenshots or documents the wrong revision.
describe('every pointer at the approved design names V3', () => {
  it('package.json gen:app converts the V3 reference', () => {
    const pkg = JSON.parse(readFileSync(join(FRONTEND, 'package.json'), 'utf8')) as { scripts: Record<string, string> };
    expect(pkg.scripts['gen:app']).toContain(`${V3}/'${V3_FILE}'`);
    expect(pkg.scripts['gen:app']).not.toContain('design_handoff_practice_match_v2');
  });

  it('the reference server serves V3 at "/" and keeps the /coming-soon mount first', () => {
    const src = readFileSync(join(FRONTEND, 'tests', 'reference-server.mjs'), 'utf8');
    expect(src).toContain(`design-reference/${V3}`);
    expect(src).toContain(`index: '/${V3_FILE}'`);
    expect(src.indexOf("prefix: '/coming-soon'")).toBeLessThan(src.indexOf("prefix: ''"));
    expect(src).not.toContain('design_handoff_practice_match_v2');
  });

  it('the Playwright harness serves the vendored React/Leaflet bytes out of the V3 folder', () => {
    expect(readFileSync(join(FRONTEND, 'tests', 'harness.ts'), 'utf8')).toContain(`${V3}/vendor`);
  });

  it('the ImageSlot parity fixture reads the V3 bundle\'s image-slot.js', () => {
    expect(readFileSync(join(FRONTEND, 'src', 'components', 'ImageSlot.test.ts'), 'utf8')).toContain(`'${V3}', 'image-slot.js'`);
  });

  it('CLAUDE.md names the V3 design file as the source of truth for the UI', () => {
    const md = readFileSync(join(ROOT, 'CLAUDE.md'), 'utf8');
    expect(md).toContain(`docs/design-reference/${V3}/${V3_FILE}\` is the approved design`);
  });
});
