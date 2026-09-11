import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { SCREENS } from './screens';

const ROOT = join(import.meta.dirname, '..', '..');
const PLANS = join(ROOT, 'docs', 'superpowers', 'plans');
const SPECS = join(ROOT, 'docs', 'superpowers', 'specs');
const read = (f: string) => readFileSync(join(PLANS, f), 'utf8');
const readSpec = (f: string) => readFileSync(join(SPECS, f), 'utf8');

const IDENTITY = '2026-09-05-practice-match-identity-access-email.md';
const MAP_ENGINES = '2026-09-05-practice-match-map-engines.md';
const CENSUS = '2026-09-05-practice-match-census-data-layer.md';
const SEED = '2026-09-06-practice-match-seed-listings.md';
const GOOGLE = '2026-09-05-practice-match-google-maps-greenfield.md';
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

  it('the identity plan executes the launch-removal list through the D15 amendment engine, never by hand-editing App.vue or logic.js (A-I8, 2026-09-07)', () => {
    const md = read(IDENTITY);
    // A-I8 replaced the earlier `convert-dc.mjs --launch` idea: a second generator mode cannot
    // coexist with one committed App.vue, and it would have left the oracle (the design file)
    // showing the jump bar the app had lost. The prototype blocks now leave the DESIGN through
    // ruled amendments (A6.x), and logic.js / App.vue are regenerated from it.
    expect(md).toContain('D15 amendment mechanism');
    expect(md).toContain('A6.1');
    expect(md).toContain('gen:design');
    expect(md).toContain('REGENERATED = pristine + amendments');
    expect(md).not.toContain('gen:app:launch');
    expect(md).not.toContain('remove jump bar markup, `gateStates`, demo credentials');
    // The one remaining mention of the old mode is the sentence that says why it was dropped.
    expect(md.split('\n').filter((l) => l.includes('--launch')), 'the --launch mode may be named only where its rejection is explained').toHaveLength(1);
  });

  it('the map-engines plan names ListingsMap.vue only inside a "deleted in Browse V3" clause (spec D19) and rebases onto V3\'s engine shape', () => {
    const md = read(MAP_ENGINES);
    // D19: naming the deleted file is fine — burying it behind a periphrasis is what V12 did and
    // John asked corrected ("correct the wording as required"). The token is allowed only on a
    // line that also says it was deleted in Browse V3; every other line naming it is an offender.
    const offenders = md.split('\n').filter((l) => l.includes('ListingsMap') && !l.includes('deleted in Browse V3'));
    expect(offenders, 'ListingsMap may be named only in a "deleted in Browse V3" clause').toEqual([]);
    expect(md).toContain('`ListingsMap.vue` (deleted in Browse V3)');
    // …and the SPEC, which this case did not read: it still named `ListingsMap.vue` a live map
    // surface at :25 and :264 after the plan was swept clean (final review M6, 2026-09-07).
    expect(readSpec(MAP_ENGINES_SPEC)).not.toContain('ListingsMap');
    expect(md).toContain('rectangle');
    expect(md).toContain('ring(');
    expect(md).toContain('panInside');
    expect(md).toContain('TooltipSpec');
    expect(md).toContain('one decision record');   // the basemap cross-reference, not a restatement
  });

  // I9a review, Important 1: the Census plan deleted `app/api/access.py` and its wrapper in the
  // same commit that left Map engines M3 importing them — two documents of record contradicting
  // each other, with the false one on the side an implementer builds from. The wrapper's whole
  // reason for existing (decide `MARKET_DATA_PUBLIC`) now lives in `permissions.allowed`, so there
  // is no shape of this plan in which the name is correct: neither plan may carry the token at all.
  it('neither the census nor the map-engines plan names the deleted market-access wrapper (I9a Important 1)', () => {
    for (const [plan, md] of [[CENSUS, read(CENSUS)], [MAP_ENGINES, read(MAP_ENGINES)]] as Array<[string, string]>) {
      const offenders = md.split('\n').filter((l) => l.includes('market_access'));
      expect(offenders, `${plan} still names the deleted market_access wrapper`).toEqual([]);
    }
    // …and both routers must name the permission that replaced it.
    expect(read(CENSUS)).toContain('Depends(require("market.read"))');
    expect(read(MAP_ENGINES)).toContain('Depends(require("market.read"))');
  });

  it('the census plan documents V3 rendering, the payroll label, the reserved word and the migration range', () => {
    const md = read(CENSUS);
    expect(md).toContain('community boundary shading');
    // A24 (2026-09-10/11): the grid is gone from the product, so it is gone from this plan's
    // rendering table too — the table is the artefact a reviewer audits coverage from.
    expect(md, 'the grid is gone from the product and from this plan').not.toContain('| Median Household Income (`income`) | community mosaic shading');
    expect(md).toContain('Average Practice Payroll');
    expect(md).toContain('Avg. payroll per practice');
    expect(md).not.toMatch(/community bubble `dot\(/);
    // The rendering table itself, not just the words around it (V11 deleted both builders).
    expect(md).not.toContain('pricePin');
    expect(md).not.toContain("dot(size, 'rgba(120,86,190,.75)')");
    expect(md).not.toMatch(/\|\s*(community )?bubble/);
    expect(md).toContain('`practicePin(label, selected)`');
    expect(md).toContain('| Veterinary Competition (`competition`) | graduated symbols at the listing point (D-C35)');
    // `016` is the Seed Listings plan's listing table, so the census range starts at `017`.
    expect(md).toContain('migrations/017_census_registry.sql');
    expect(md).not.toContain('migrations/016_census_registry.sql');
    expect(md).not.toContain('`010`–`059`');   // every citation of SP2's old range is renumbered
    expect(md).toContain('one decision record');
  });

  // V12 wrote these two paragraphs under option A ("V3 drops uppercase on every display-size
  // heading; there is no pre-V3 pixel oracle any more"). Task V13 withdrew that premise: A1 put
  // V2's typography back and all thirteen non-Browse screens hash to their V2 baselines again, so
  // both documents were instructing the next implementer with a retired rule (V13 review M2).
  it('the map-engines and census plans carry V13\'s correction, not option A\'s typography rule', () => {
    const correction = "Amended 2026-09-07: Task V13 restored V2's typography through local amendment A1 (Browse V3 spec D15/D16); the thirteen non-Browse screens are byte-identical to V2 again, so a pre-V3 pixel oracle exists for them. Browse-only elements keep V3's type.";
    expect(read(MAP_ENGINES)).toContain(correction);
    expect(read(CENSUS)).toContain(correction);
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

    // The FOURTH plan. This assertion was dropped when the I2 pins were added (re-review,
    // 2026-09-07): the map-engines SPEC pin below is not a substitute for it — the plan and the
    // spec are two documents, and the case's title claims four plans.
    expect(read(MAP_ENGINES)).toContain('Census SP3-A `017`–`059`');
  });

  // Re-review M8/M13a (2026-09-07): one sequence means the FILE NAMES have to agree with it too.
  // `007_license_audit.sql` ALTERs and REFERENCES `dataset_registry`, which the same plan creates
  // ten numbers later in `017_census_registry.sql`, so `scripts/migrate.py` could never have run
  // it — and the census plan's own D14 reserves `003`–`009` for Platform-level migrations with no
  // dependency on later tables. The Google plan's `009_google_registry.sql` is the same class of
  // defect from the other side: the map-engines plan records that `080` supersedes it while the
  // Google plan still said "Create".
  it('every plan names its migration files consistently with that sequence (M8, M13a)', () => {
    const census = read(CENSUS);
    expect(census, '`007` sorts before the `017` that creates dataset_registry, so it cannot run').not.toContain('007_license_audit');
    expect(census).toContain('migrations/020_license_audit.sql');
    expect(census, 'D14 must record `020` as taken so the next renumber sees it').toContain('`020` is taken');

    const google = read(GOOGLE);
    const orphans = google.split('\n').filter((l) => l.includes('009_google_registry') && !l.includes('superseded by `080_map_engines.sql`'));
    expect(orphans, '`009_google_registry.sql` may be named only beside its supersession note').toEqual([]);

    const identity = read(IDENTITY);
    expect(identity, '`012` is `012_api_tokens.sql`; `application` is created by `011_applications_roles.sql`').not.toContain('012_applications.sql');
    expect(identity).toContain('`migrations/011_applications_roles.sql` **in place**');
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

  // Re-pinned by Task V13 (option B, John 2026-09-07: "keep the V2 header and do not restyle
  // header or fonts"): the design reference is the pristine Rev 2 bundle plus the local
  // amendments, A1 put V2's display typography back, and option A's claim — that the thirteen
  // moved for good and byte-identity was abandoned — is withdrawn from CLAUDE.md, both where it
  // described the reference and in the verification gate.
  it('CLAUDE.md records the V2 folder\'s role and the local amendment that restored its heading typography', () => {
    const md = readFileSync(join(ROOT, 'CLAUDE.md'), 'utf8');
    expect(md).toContain('design_handoff_practice_match_v2');
    expect(md).toContain('pre-V3 oracle');
    expect(md).toContain('display-size heading');
    expect(md).toContain('LOCAL_AMENDMENTS.md');
    expect(md).toContain('spec D15');
    // Step 5 read 13 SAME / 0 MOVED once A1 paired by (tag, text, size) and the 28 px mobile
    // asking price came back, so the claim is all thirteen — not the twelve of the first pass.
    //
    // Task I8a's launch removal (A6, ruled D-I8-6) then ENDED that byte-identity by taking the
    // prototype jump bar off the top of every screen, so CLAUDE.md's sentence is dated rather
    // than dropped (review round 1, I3). `tests/test_docs.py` pins the dating; this still pins
    // the half that is A1's and does not expire — that A1's own effect is not understated.
    expect(md).toContain('thirteen non-Browse screens');
    expect(md).toContain('byte-identical to V2 again');
    expect(md).not.toContain('twelve of the thirteen');
    expect(md).not.toContain('option A makes it the proof');
    expect(md).not.toContain('V3 deliberately drops');
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

  /** The 28 states Browse V3 shipped, in the order `screens.ts` has always listed them. Wave 2a's
   *  fifteen account screens are appended AFTER these, so this list is the "did any of the 28
   *  move?" half of the count pin below. */
  const BROWSE_V3_STATES = [
    'gate-signin', 'gate-apply', 'gate-pending', 'gate-declined',
    'browse', 'browse-layer-menu', 'browse-compare-open', 'browse-legend-collapsed', 'browse-layers-open', 'browse-market-panel',
    'detail', 'interest-modal', 'requests', 'seller-dash',
    'wizard-step-1', 'wizard-step-7', 'wizard-preview', 'wizard-done',
    'admin-users', 'admin-listings', 'admin-requests', 'admin-data-sources',
    'mobile-list', 'mobile-map', 'mobile-sheet', 'mobile-detail',
    'header-1100', 'header-1000'
  ];

  // V10's fix round added the 28th state after V9 had written the plan's prose; CLAUDE.md was
  // updated and the plan was not, so Appendix A — the table Global Constraint (a) is discharged
  // against — counted 27 (M1).
  it('counts the 28 states that shipped, not the 27 V9 produced (M1)', () => {
    const md = read(BROWSE_V3);
    // Browse V3 shipped 28, and this plan's prose is the record of THAT — a historical claim that
    // stays true however the list grows afterwards. What must not change is that all 28 are still
    // approved states: Wave 2a's account screens (spec §6, Task S5) are 15 MORE, appended, and the
    // whole point of that task was that the 28 keep their pixels and their DOM. So the count is
    // asserted as "the 28 are all still here, and the list has only grown", which is what this pin
    // was always for — a state quietly leaving would otherwise pass a bare length check the moment
    // another was added.
    expect(SCREENS.length, 'the approved screen list shrank — a state left').toBeGreaterThanOrEqual(28);
    expect(SCREENS.slice(0, 28).map((s) => s.name), 'the 28 Browse V3 states moved or were reordered').toEqual(BROWSE_V3_STATES);
    expect(md).toContain('`SCREENS` (28 entries)');
    expect(md).toContain('28-state `dom.spec.ts` + 28-state `visual.spec.ts`');
    expect(md).toContain('for **all 28** states + the 28-state DOM oracle');
    // …and Appendix A names V10's oracle for the OPENED sheet, which is what the 28th state is.
    expect(md).toContain('the `mobile-sheet` state');
    // The one site that keeps V9's count is the verbatim quotation of
    // `baseline-manifest.mjs`'s own historical header comment; the plan states the fact beside
    // it rather than editing the quotation (addendum ruling 1, 2026-09-07).
    expect(md).toContain("(28 states after V10's `mobile-sheet`; the comment records V9's count.)");
  });

  // The superseded migration number, in the two places V12's own instructions and Appendix A
  // still carried it (addendum ruling 2, 2026-09-07).
  it('states the one migration sequence in its own instructions and audit table too (I2)', () => {
    const plan = read(BROWSE_V3);
    expect(plan).not.toMatch(/renumber to start at `015`|migrations at `015`/);
    expect(plan).toContain('`017`–`059`');
    expect(plan).toContain('migrations/017_census_registry.sql');
  });

  // The sixth dead-code entry, recorded where the other five are (M4).
  it('the V11 checklist carries the `MarketMap` grammar entry as its sixth deletion (M4)', () => {
    const md = read(BROWSE_V3);
    expect(md).toContain("*(added 2026-09-07, final review M4)*");
    expect(readSpec(BROWSE_V3_SPEC)).toContain("its `MarketMap: 'MarketMapView'` entry follows in its own commit");
  });

  // The basemap licence is one decision record (Census plan). V12 Step 6's own prose named
  // three anchors, none of which is where the record or its references landed (M3).
  it('V12 Step 6 names the anchors the record actually uses (M3)', () => {
    const md = read(BROWSE_V3);
    expect(md).not.toContain('the Map-engines plan §12');
    expect(md).not.toContain('the Browse V3 spec §"Legally load-bearing"');
    expect(md).toContain('`LEAFLET` tile-constant note');
  });

  // I2 / rulings 4a–4d (2026-09-07). Task V13's fix round swept option A out of the two
  // cross-plan documents and pinned the correction (above), but not out of the plan that OWNS
  // the decision. Its four audit tables are the surface a reviewer reads INSTEAD of the prose,
  // so an unmarked "option A" row there teaches a rule John withdrew — including two rows that
  // called the bundle's C14 byte-identical claim factually incorrect, which option B vindicated.
  it('no audit-table row cites option A as standing (I2)', () => {
    const rows = [...read(BROWSE_V3).matchAll(/^\|.*option A\).*$/gm)].map((m) => m[0]);
    expect(rows, 'an audit-table row still states option A').toEqual([]);
  });

  // Ruling 4d: V12 Step 11's commit template carried the superseded migration number in PLAIN
  // TEXT, which the backticked assertion in the case above could not see.
  it('states the one migration sequence in prose as well as in code spans (4d)', () => {
    expect(read(BROWSE_V3)).not.toMatch(/migrations start at `?015`?/);
  });

  // M1/M2: D20 — the mosaic redraw semantics John confirmed ("I AGREE with your decision") — was
  // indexed nowhere in the document that maps decisions to tasks and tests; A.6 was still titled
  // D1–D14 and its D16 row counted 25 edits where every other consumer of that number says 24.
  // M9: V17's Step 4 still prescribed the condition-based wait its own Outcome note refuted.
  it('indexes every spec decision through D21, counts A1 at 24, and supersedes what was refuted (M1, M2, M9)', () => {
    const md = read(BROWSE_V3);
    expect(md).toContain('### A.6 Spec decisions D1–D21');
    expect(md).toContain('D20');
    expect(md, 'A1 is 24 edits in the spec, LOCAL_AMENDMENTS.md, CLAUDE.md and two test assertions').not.toContain('25 edits');
    expect(md, 'V5\'s watcher block still describes the pre-D20 superset redraw').toContain('Superseded by D20 (John confirmed 2026-09-07)');
    expect(md, 'V17 Step 4 still prescribes the refuted condition-based wait').toContain('Superseded by the Outcome note above (recorded 2026-09-07)');
  });

  // M3: V15 replaced the blanket `not.toContain('ListingsMap')` ban with the per-line "deleted in
  // Browse V3" filter (spec D19). Three plan sites still described the retired rule as current —
  // re-executing V12 Step 5 from that text would write a line that FAILS the shipped test.
  it('describes its own ListingsMap drift rule as V15 left it (M3)', () => {
    const md = read(BROWSE_V3);
    expect(md).toContain('the token only inside a "deleted in Browse V3" clause');
    expect(md.split('superseded by Task V15 (spec D19)').length - 1, 'both V12 sites need the marker').toBeGreaterThanOrEqual(2);
  });
});

// I1 (2026-09-07): A2.2–A2.5 edit John's approved design — three of them deletions — and existed
// only in `LOCAL_AMENDMENTS.md`, `design-amendments.ts` and the SDD working directory, while the
// spec decision that owns them still said `selectMarker` was untouched. D15 makes the amendment
// list the retirement register for a re-issued bundle, so the spec is the text a future
// implementer reads while deciding what to undo.
describe('the durable record names every design amendment that shipped', () => {
  it('spec D17 records A2.2–A2.5 and no longer says every other handler is untouched (I1)', () => {
    const spec = readSpec(BROWSE_V3_SPEC);
    expect(spec).toContain('A2.5');
    expect(spec).not.toContain('leaving `selectMarker` and every other handler untouched');
    expect(spec, 'the wired handler C13 fixed must be named as the one that stayed').toContain('`mobileVals.selectMarker`');
  });

  it('spec D15 states the find-count contract the implementation actually honours (M4)', () => {
    const spec = readSpec(BROWSE_V3_SPEC);
    expect(spec).toContain('at the point it is applied');
    expect(spec, 'A2.5 matches A2.4\'s output, so no count can be measured against the pristine file').not.toContain('occurs exactly `count` times in the pristine file');
  });

  it('the spec keeps its decision records in one sequence (ruling 8)', () => {
    const spec = readSpec(BROWSE_V3_SPEC);
    expect(spec.indexOf('- **D8 —')).toBeLessThan(spec.indexOf('- **D9 —'));
    expect(spec.indexOf('- **D9 —')).toBeLessThan(spec.indexOf('- **D10 —'));
  });

  // Bare `A1`–`A4` would pass on any document that happens to contain those two characters —
  // `A1` appears inside the manifest prose already. The pin is the phrase each family is named
  // BY, so deleting or rewording one of them fails (re-review of this fix round, observation 2).
  it('CLAUDE.md names all four amendment families and says what each one does (I1)', () => {
    const claude = readFileSync(join(ROOT, 'CLAUDE.md'), 'utf8');
    const families: Array<[string, string]> = [
      ['A1 (typography)', 'Amendment **A1** (John, 2026-09-07: "keep the V2 header and do not restyle header or fonts") restores V2\'s display typography on 24 template elements'],
      ['A2 (mobile card)', '**A2** (spec D17 — the mobile practice card opens the detail;'],
      ['A2.2–A2.5 (C13 dead code)', '**A2.2–A2.5** then delete the `browseSel` orphans C13 left behind, including the unwired top-level `selectMarker`'],
      ['A3 (label)', '**A3** (spec D18 — "View full market report" → "View full listing")'],
      ['A4 (Compare)', '**A4** (spec D21 — Compare hides the "What this means" card)'],
    ];
    for (const [family, phrase] of families) expect(claude, `CLAUDE.md no longer names ${family}`).toContain(phrase);
  });

  // …and in the TASK, not merely somewhere in a 4,100-line file: the id set also appears in
  // Appendix A.6 and the Self-Review table, either of which would have satisfied a
  // whole-document `toContain`. The record has to sit with the task that shipped the edits, so
  // the pin reads only Task V14's own slice (re-review of this fix round, observation 2).
  it('the plan\'s V14 block itself lists the amendments that landed after A2 (I1)', () => {
    const md = read(BROWSE_V3);
    const start = md.indexOf('### Task V14:');
    expect(start, 'the plan has no `### Task V14:` heading any more').toBeGreaterThan(-1);
    const next = md.indexOf('\n### Task', start + 1);
    const v14 = md.slice(start, next === -1 ? md.length : next);
    for (const id of ['A2.2', 'A2.3', 'A2.4', 'A2.5']) expect(v14, `${id} appears outside Task V14, or nowhere`).toContain(id);
  });
});

// CLAUDE.md is the document every session reads first, so a pointer that is wrong there is
// wrong everywhere. Each pin below is one final-review finding (2026-09-07).
describe('CLAUDE.md points at what shipped', () => {
  const claude = () => readFileSync(join(ROOT, 'CLAUDE.md'), 'utf8');

  it('names the Browse V3 spec §3 and the drift test that enforces it, not the Platform spec (M5)', () => {
    expect(claude()).toContain('docs/superpowers/specs/2026-09-06-browse-v3-mobile-design.md` §3');
    expect(claude()).toContain('frontend/tests/app-generated.test.ts');
    expect(claude()).not.toContain('2026-09-05-practice-match-platform-design.md');
  });

  it('points at the one basemap decision record by name, and no longer restates the question (M3)', () => {
    expect(claude()).toContain('Basemap licence — one decision record');
    expect(claude()).not.toContain('Platform spec §9');
    // The census plan's own registry seed comment restated it too.
    expect(read(CENSUS)).not.toContain('VIN Foundation decision pending (Platform spec §9)');
  });

  it('describes zero tolerance precisely: no pixel differs, and what "differs" means (M10)', () => {
    expect(claude()).toContain('maxDiffPixels: 0');
    expect(claude()).toContain('threshold: 0.1');
    expect(claude()).toContain('YIQ');
  });
});

// M8: the byte-exact drift test performs a FOURTH normalisation the documented list omits.
describe('the logic.js port lists every normalisation it performs', () => {
  it('the Browse V3 spec \u00a73 names the trailing-newline normalisation as well (M8)', () => {
    expect(readSpec(BROWSE_V3_SPEC)).toContain('trailing-newline');
  });
  // Seed Listings L6 (spec 2026-09-06 D6): the trailing export now names the two fixture arrays
  // as well, so `src/listings/load.ts` can replace `P` and `MARKETS` in place. Same rule as M8's
  // — a port edit the \u00a73 list does not spell out is an undocumented hand edit, whatever the
  // drift test says.
  it('the Browse V3 spec \u00a73 spells out the export the listings loader needs (Seed Listings L6)', () => {
    expect(readSpec(BROWSE_V3_SPEC)).toContain('export { Component, MARKETS, P, VETS, ECON_K };');
  });
});
