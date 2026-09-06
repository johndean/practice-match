import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = join(import.meta.dirname, '..', '..');
const PLANS = join(ROOT, 'docs', 'superpowers', 'plans');
const read = (f: string) => readFileSync(join(PLANS, f), 'utf8');

const IDENTITY = '2026-09-05-practice-match-identity-access-email.md';
const MAP_ENGINES = '2026-09-05-practice-match-map-engines.md';
const CENSUS = '2026-09-05-practice-match-census-data-layer.md';

// Browse V3 spec §6. These three plans were written against V2's Browse screen and go stale
// the moment V3 merges; this test is what stops them being executed against the old shape.
describe('cross-plan deltas (Browse V3 spec §6)', () => {
  it('the identity plan no longer keys a permission on browseMode', () => {
    const md = read(IDENTITY);
    expect(md).not.toContain("patch.browseMode === 'market'");
    expect(md).not.toContain("'browse-market': 'market.read'");
    expect(md).not.toContain("ROUTE_PERMS['browse-market']");
    expect(md).toContain("browse: 'page.browse'");
    expect(md).toContain("can('market.read')");
  });

  it('the identity plan executes the launch-removal list through the generator, not by hand-editing App.vue', () => {
    const md = read(IDENTITY);
    expect(md).toContain('convert-dc.mjs --launch');
    expect(md).toContain('gen:app:launch');
    expect(md).not.toContain('remove jump bar markup, `gateStates`, demo credentials');
  });

  it('the map-engines plan no longer mentions ListingsMap anywhere and rebases onto V3\'s engine shape', () => {
    const md = read(MAP_ENGINES);
    expect(md).not.toContain('ListingsMap');   // catches the M5 file list, the components paragraph AND the setControls parenthetical
    expect(md).toContain('rectangle');
    expect(md).toContain('ring(');
    expect(md).toContain('panInside');
    expect(md).toContain('TooltipSpec');
  });

  it('the census plan documents V3 rendering, the payroll label, the reserved word and the migration range', () => {
    const md = read(CENSUS);
    expect(md).toContain('community mosaic shading');
    expect(md).toContain('Average Practice Payroll');
    expect(md).toContain('Avg. payroll per practice');
    expect(md).not.toMatch(/community bubble `dot\(/);
    expect(md).toContain('`015`');
    expect(md).not.toContain('`010`–`059`');   // every citation of SP2's old range is renumbered
    expect(md).toContain('one decision record');
  });

  it('the census plan carries README §5\'s disabled-vs-blocked contract, which V3\'s fixtures conflate', () => {
    const md = read(CENSUS);
    expect(md).toContain('"disabled"');
    expect(md).toContain('"blocked"');
    expect(md).toContain('licence');
  });

  it('CLAUDE.md records the V2 folder\'s role and V3\'s heading typography', () => {
    const md = readFileSync(join(ROOT, 'CLAUDE.md'), 'utf8');
    expect(md).toContain('design_handoff_practice_match_v2');
    expect(md).toContain('pre-V3 oracle');
    expect(md).toContain('display-size heading');
  });
});
