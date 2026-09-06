import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = join(import.meta.dirname, '..', '..');
const PLANS = join(ROOT, 'docs', 'superpowers', 'plans');
const SPECS = join(ROOT, 'docs', 'superpowers', 'specs');
const read = (f: string) => readFileSync(join(PLANS, f), 'utf8');
const readSpec = (f: string) => readFileSync(join(SPECS, f), 'utf8');

const IDENTITY = '2026-09-05-practice-match-identity-access-email.md';
const MAP_ENGINES = '2026-09-05-practice-match-map-engines.md';
const CENSUS = '2026-09-05-practice-match-census-data-layer.md';
const SEED = '2026-09-06-practice-match-seed-listings.md';
const BROWSE_V3 = '2026-09-06-browse-v3-mobile.md';
const IDENTITY_SPEC = '2026-09-05-identity-access-email-design.md';
const MAP_ENGINES_SPEC = '2026-09-05-map-engines-design.md';
const BROWSE_V3_SPEC = '2026-09-06-browse-v3-mobile-design.md';

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
    expect(md).toContain("the market column inside Browse checks `can('market.read')` separately");
    expect(md).toContain("there is one `browse` state, not `browse-listings`/`browse-market`");
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
    expect(md).toContain('one decision record');   // the basemap cross-reference, not a restatement
  });

  it('the census plan documents V3 rendering, the payroll label, the reserved word and the migration range', () => {
    const md = read(CENSUS);
    expect(md).toContain('community mosaic shading');
    expect(md).toContain('Average Practice Payroll');
    expect(md).toContain('Avg. payroll per practice');
    expect(md).not.toMatch(/community bubble `dot\(/);
    // The rendering table itself, not just the words around it (V11 deleted both builders).
    expect(md).not.toContain('pricePin');
    expect(md).not.toContain("dot(size, 'rgba(120,86,190,.75)')");
    expect(md).not.toMatch(/\|\s*(community )?bubble/);
    expect(md).toContain('`practicePin(label, selected)`');
    expect(md).toContain('| Veterinary Competition (`competition`) | community mosaic shading');
    // `016` is the Seed Listings plan's listing table, so the census range starts at `017`.
    expect(md).toContain('migrations/017_census_registry.sql');
    expect(md).not.toContain('migrations/016_census_registry.sql');
    expect(md).not.toContain('`010`–`059`');   // every citation of SP2's old range is renumbered
    expect(md).toContain('one decision record');
  });

  it('the census plan carries README §5\'s disabled-vs-blocked contract, which V3\'s fixtures conflate', () => {
    const md = read(CENSUS);
    expect(md).toContain('"disabled"');
    expect(md).toContain('"blocked"');
    expect(md).toContain('licence');
  });

  // One migration sequence, four plans. A number that is right in one plan and wrong in
  // another is a silent collision: `scripts/migrate.py` runs files in numeric order, and git
  // will not flag two plans claiming `016` because they live in different files.
  it('the four plans agree on one migration sequence: identity 010-015, Seed 016, census 017+', () => {
    const seed = read(SEED);
    expect(seed).toContain('migrations/016_listing.sql');
    expect(seed).not.toMatch(/starts? at `?015/);

    const identity = read(IDENTITY);
    expect(identity).toContain('migrations `010`–`015`');
    expect(identity).toContain('015_admin_list_indexes');
    expect(identity).not.toContain('this wave uses `010`–`014`');
    // Final review I2 (2026-09-07): the reservation clause, not just the wave clause. The
    // plan reserved `010`–`019` for SP2 while the census plan took `017`–`059`, so two plans
    // directed an implementer to create `017`, `018` and `019` — and this case passed, because
    // it read the half of the sentence that was already right.
    expect(identity).not.toContain('`010`–`019`');

    // The census plan's own range row, and the gap it leaves.
    const census = read(CENSUS);
    expect(census).toContain('`003`–`009` are unassigned');
  });

  // Same sequence, in the SPECS. A reader meets whichever document they open first, and three
  // of them still carried the superseded ranges after V12 corrected the four plans (I2).
  it('the three specs state the same one migration sequence as the plans', () => {
    const identity = readSpec(IDENTITY_SPEC);
    expect(identity).not.toContain('`010`–`019`');
    expect(identity).toContain('migrations `010`–`015`');

    const mapEngines = readSpec(MAP_ENGINES_SPEC);
    expect(mapEngines).not.toContain('SP2 `010`–`059`');
    expect(mapEngines).not.toContain('Census SP3-A `002`–`009`');
    expect(mapEngines).toContain('Census SP3-A `017`–`059`');

    const browseV3 = readSpec(BROWSE_V3_SPEC);
    expect(browseV3).not.toContain('renumber to start at `015`');
    expect(browseV3).not.toContain('migrations start at `015`');
    expect(browseV3).toContain('migrations start at `017`');
  });

  it('CLAUDE.md records the V2 folder\'s role and V3\'s heading typography', () => {
    const md = readFileSync(join(ROOT, 'CLAUDE.md'), 'utf8');
    expect(md).toContain('design_handoff_practice_match_v2');
    expect(md).toContain('pre-V3 oracle');
    expect(md).toContain('display-size heading');
  });
});

// This sub-project's OWN plan is the artefact Global Constraint (a) is discharged against and
// the one a reviewer is told to audit coverage from without re-reading the design bundle, so
// where it describes what shipped it has to be right about it. Each pin below sits at a
// sentence the final review (2026-09-07) found describing something else.
describe('the Browse V3 plan describes what shipped', () => {
  it('the engineer\'s note records the mosaic redraw as measured and reference-exact (I1)', () => {
    const md = read(BROWSE_V3);
    expect(md).toContain('a second pin tap repaints the map within budget');
    expect(md).toContain('reference-exact');
  });
});
