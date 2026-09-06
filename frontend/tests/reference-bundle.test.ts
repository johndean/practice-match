import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const REF = join(fileURLToPath(new URL('.', import.meta.url)), '..', '..', 'docs', 'design-reference');
const V2 = join(REF, 'design_handoff_practice_match_v2');
const V3 = join(REF, 'design_handoff_practice_match_v3');

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

// README Task 1: the bundle deliberately omits the design-system, the vendored libraries and
// doc-page.js, and they must be MIRRORED UNCHANGED from V2 — without them the reference
// server serves a blank map. The V2 folder itself stays: it is the oracle for the deployed
// build and the only way to prove a regression came from this change.
describe('the V3 design reference bundle', () => {
  // Task V13 added the local-amendment pair (spec D15): the pristine Rev 2 file the bundle
  // shipped, frozen as `.rev2` and never edited, and the human-readable amendment log beside it.
  it('carries the authority file, the frozen pristine copy, the amendment log, the ported component and the four handoff documents', () => {
    for (const f of ['Practice Match V3.dc.html', 'Practice Match V3.rev2.dc.html', 'LOCAL_AMENDMENTS.md', 'MarketMapV3.jsx', 'README.md', 'CHANGE_LOG.md', 'DEAD_CODE_CHECKLIST.md', 'FILE_INDEX.md', 'support.js', 'image-slot.js', 'Census Data Source Specification.dc.html']) {
      expect(statSync(join(V3, f)).isFile(), `${f} is missing from the V3 bundle`).toBe(true);
    }
  });

  it('mirrors _ds/, vendor/ and doc-page.js from V2 byte-identically', () => {
    const mirrored = ['doc-page.js', ...walk(join(V2, '_ds')).map((f) => relative(V2, f)), ...walk(join(V2, 'vendor')).map((f) => relative(V2, f))];
    expect(mirrored.length, 'the V2 folder no longer carries the files V3 mirrors').toBeGreaterThan(1);
    const drifted = mirrored.filter((rel) => !readFileSync(join(V2, rel)).equals(readFileSync(join(V3, rel))));
    expect(drifted, 'these mirrored files differ between V2 and V3').toEqual([]);
  });

  it('carries no .DS_Store — a macOS artifact is not part of the design', () => {
    expect(walk(V3).filter((f) => f.endsWith('.DS_Store')).map((f) => relative(V3, f))).toEqual([]);
  });

  it('keeps the V2 folder as the regression oracle', () => {
    expect(statSync(join(V2, 'Practice Match V2.dc.html')).isFile()).toBe(true);
  });
});
