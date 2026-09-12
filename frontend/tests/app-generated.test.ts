import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildAppVue, convert, extractTemplate } from '../scripts/convert-dc.mjs';

const ROOT = join(import.meta.dirname, '..');
const DC = join(ROOT, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'Practice Match V3.dc.html');

describe('App.vue is generated from the design', () => {
  it('regenerating yields byte-identical App.vue and pseudo.css (no hand edits survive)', () => {
    const { template, pseudoCss } = convert(extractTemplate(readFileSync(DC, 'utf8')));
    expect(readFileSync(join(ROOT, 'src/App.vue'), 'utf8')).toBe(buildAppVue(template, readFileSync(join(ROOT, 'src/app.setup.js'), 'utf8'), './generated/pseudo.css'));
    expect(readFileSync(join(ROOT, 'src/generated/pseudo.css'), 'utf8')).toBe(pseudoCss);
  });
  it('the generated template compiles under the Vue SFC compiler with preserved whitespace', async () => {
    const { parse, compileTemplate } = await import('@vue/compiler-sfc');
    const { descriptor, errors } = parse(readFileSync(join(ROOT, 'src/App.vue'), 'utf8'));
    expect(errors).toEqual([]);
    const out = compileTemplate({ source: descriptor.template!.content, filename: 'App.vue', id: 'app', compilerOptions: { whitespace: 'preserve', isCustomElement: (tag: string) => tag === 'image-slot' } });
    expect(out.errors).toEqual([]);
  });
  it('retired the JS hover directive: no v-hover, no hover.js', () => {
    expect(readFileSync(join(ROOT, 'src/App.vue'), 'utf8')).not.toContain('v-hover');
    expect(() => readFileSync(join(ROOT, 'src/directives/hover.js'))).toThrow();
  });
  it('app.setup.js declares every prop the design declares — a new design prop is otherwise silently undefined at runtime', () => {
    const html = readFileSync(DC, 'utf8');
    const tag = /<script type="text\/x-dc" data-dc-script[^>]*data-props="([^"]*)"/.exec(html)!;
    const decoded = tag[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&');
    const declared = Object.keys(JSON.parse(decoded) as Record<string, unknown>).filter((k) => !k.startsWith('$'));
    const setup = readFileSync(join(ROOT, 'src/app.setup.js'), 'utf8');
    expect(declared).toContain('layerPalette');
    for (const p of declared) expect(setup, `app.setup.js does not declare the design prop "${p}"`).toMatch(new RegExp(`\\b${p}\\s*:`));
  });
});

// logic.js is NOT written by gen:app — it is the design file's own <script data-dc-script>
// block with exactly three edits: the provenance header + the DCLogic import, the platform
// spec §3 rule-1 asset rewrite, and the trailing export. This test makes that transform
// machine-checked, so "never hand-edit logic.js" is enforceable rather than aspirational.
describe('logic.js is the design script block, ported verbatim', () => {
  const HEADER = "// Ported verbatim from the approved prototype 'Practice Match V3.dc.html'.\n"
    + '// Do not restyle or restructure: every value here is design-approved.\n'
    + "import { DCLogic } from './dc-logic.js';\n";
  // The trailing export names the two fixture ARRAYS as well as the class (Seed Listings L6,
  // spec D6): `src/listings/load.ts` replaces `P` and `MARKETS` in place at start-up, which is
  // the one way to hand the API's listings to a script that is ported verbatim and never
  // restructured. It is still the same single accepted edit point — the last line — and the
  // ported body above it stays byte-identical. Listed in the Browse V3 spec §3 with the other
  // three normalisations.
  const FOOTER = '\nexport { Component, MARKETS, P, VETS, ECON_K };\n';

  function designScript(html: string): string {
    const open = /<script type="text\/x-dc" data-dc-script[^>]*>/.exec(html)!;
    const start = open.index + open[0].length;
    return html.slice(start, html.indexOf('</script>', start));
  }

  it('matches byte-for-byte, header and export aside, with only the documented asset rewrite', () => {
    // FOUR normalisations, and all four are now listed in the Browse V3 spec §3 (review M8):
    // the HEADER and FOOTER above, the asset rewrite, and `\n+$` → `\n` — the design's script
    // block ends with two newlines and the ported file with one.
    const body = designScript(readFileSync(DC, 'utf8')).replace(/"assets\//g, '"/assets/').replace(/\n+$/, '\n');
    expect(readFileSync(join(ROOT, 'src/logic.js'), 'utf8')).toBe(HEADER + body + FOOTER);
  });

  it('carries V3\'s market-data shape and none of V2\'s Listings tab', () => {
    const logic = readFileSync(join(ROOT, 'src/logic.js'), 'utf8');
    // A28.2-A28.4 (John, 2026-09-11, ruling D-C44) append the legacy panel's own orphans to this
    // list: `layerHelp`, `fillRows`, `overlayRows` and the two drive-band layer-default flags the
    // deleted rows were the sole reader of. They are here rather than only in
    // `design-amendments.test.ts` because that suite asserts on the DESIGN and this one asserts
    // on the PORT — a hand edit that put any of them back into `logic.js` alone would fail the
    // byte-parity case above, and this names what it was.
    for (const gone of ['browseMode', 'browseToggle', 'hasPeek', 'fillRows', 'overlayRows', 'layerHelp', 'drive5', 'drive10']) {
      expect(logic, `logic.js still carries ${gone}`).not.toContain(gone);
    }
    // README §7, risk register: the V3 reference still declares a vestigial `isBrowse: false`
    // (V3 script block line 1435) that nothing reads. logic.js is a VERBATIM port, so it ships
    // too. Pinned as a fact, not a defect — it goes when the design reference drops it.
    expect((logic.match(/isBrowse/g) ?? []).length, 'isBrowse should appear exactly once — the reference\'s vestigial `isBrowse: false`').toBe(1);
    expect(logic).toContain('isBrowse: false');
    for (const present of ['sheetOpen', 'openSheet', 'closeSheet', 'layerLabel', 'datasetRowStyle', 'layerPalette', 'Average Practice Payroll', 'Avg. payroll per practice']) {
      expect(logic, `logic.js is missing ${present}`).toContain(present);
    }
  });

  // ------------------------------------------------------------------------------------------
  // Task MP1, fix round 1 (Minor-2). TWO FURTHER COPIES OF THE NULL-COORDINATE HAZARD, shipped
  // deliberately. Both are the DESIGN'S OWN pre-existing dead code — not residue of any
  // amendment — and both build a coordinate pair, or a bounding box over coordinates, with no
  // finite-point test of the kind A25 gave the three live readers:
  //
  //   * `mob.markers` (V3:3665) — `list.map((p) => ({ id, lat, lng, priceLabel }))`, the mobile
  //     map's own marker list. `[null, null]` here would reach Leaflet's `toLatLng` exactly as
  //     `md.practices` did.
  //   * `marketVals`'s `minLat`/`maxLat`/`minLng`/`maxLng` (V3:2151-2152) — a padded metro
  //     bounding box over the communities' coordinates. `Math.min.apply(null, [null, …])` is 0,
  //     so one unlocated community stretches it to the equator, which is precisely the failure
  //     A25.3 measured in the mosaic's own bbox (100,482,513 cells).
  //
  // NEITHER IS DELETED. Deleting them is an unruled edit to the approved design. The bundle's
  // dead-code rule had only ever been applied to orphans an amendment itself created (A2.3-A2.5,
  // A13.6-A13.7) until A28.2-A28.4 (John, 2026-09-11, ruling D-C44) applied it to the legacy
  // panel's own pre-existing orphans — and that widening is the point: it took a RULING, named
  // the identifiers, and was measured one by one. These two are not in it. They are INERT ONLY
  // BECAUSE NO TEMPLATE CONSUMES THEM, and that —
  // not their existence — is what this case pins, in the same spirit as the reference's
  // vestigial `isBrowse: false` above: as facts, not defects. The day either is wired to a
  // template this fails, and whoever wires it is made to give it A25.1's finite-coordinate test
  // first. Asserted on the generated `App.vue` AND on the design's own template, so it covers
  // the reference (the oracle) as well as the app.
  // ------------------------------------------------------------------------------------------
  it('the design\'s two unread coordinate readers are still unread (Task MP1, Minor-2)', () => {
    const logic = readFileSync(join(ROOT, 'src/logic.js'), 'utf8');
    const appVue = readFileSync(join(ROOT, 'src/App.vue'), 'utf8');
    const designTemplate = extractTemplate(readFileSync(DC, 'utf8'));

    // 1. `mob.markers`: declared exactly once, in the shape that carries raw coordinates, and
    //    read by no template on either side. The phone frame's map is a `<MarketMapView>` fed
    //    `v.md?.practices`, which A25.1 filters.
    expect((logic.match(/markers:/g) ?? []).length, 'markers is declared more than once').toBe(1);
    expect(logic).toContain('markers: list.map((p) => ({ id: p.id, lat: p.lat, lng: p.lng,');
    expect(appVue, 'mob.markers now reaches a template, carrying unfiltered coordinates').not.toContain('markers');
    expect(designTemplate, 'the design\'s own template now reads markers, carrying unfiltered coordinates').not.toContain('markers');

    // 2. The metro bounding box: each local appears exactly once — its own declaration — so
    //    nothing reads it. A second occurrence of any of the four is a reader.
    for (const name of ['minLat', 'maxLat', 'minLng', 'maxLng']) {
      expect((logic.match(new RegExp(name, 'g')) ?? []).length, `${name} has a reader now`).toBe(1);
    }
  });
});

// ------------------------------------------------------------------------------------------
// Task B10 (D-C31/D-C32) — the four TEMPLATE amendments this task adds. A script guard can be
// proved by a unit test on the render values; a template one cannot: reverting A21.5a leaves
// `overviewTitle` computed and simply stops rendering it, and the DOM oracle cannot see it
// either, because the reference and the app are generated from the SAME amended design and
// would move together. A mutation probe on the generated template is the only gate that fails,
// so these are pins on `App.vue` itself.
// ------------------------------------------------------------------------------------------
describe('the docked panel and the detail card say which area their figures describe (D-C32)', () => {
  const appVue = readFileSync(join(ROOT, 'src/App.vue'), 'utf8');

  it('A21.5a: the panel’s Insights heading is data, never a hard-coded drive band', () => {
    expect(appVue).toContain('{{ __s(v.md?.panel?.overviewTitle) }}');
    expect(appVue, 'the heading is hard-coded again').not.toContain('>Market Overview (10 min drive)<');
  });

  it('A21.5d: the detail’s attribution sentence is data, and the Census attribution is untouched', () => {
    expect(appVue).toContain('{{ __s(v.d?.demoScope) }}');
    expect(appVue).not.toContain('attribution requested). Figures describe the community around the practice');
    // Legally load-bearing (spec §12) and not part of the sentence that moved.
    expect(appVue).toContain('Source: U.S. Census Bureau, American Community Survey 2023 5-year estimates (public domain, attribution requested).');
  });

  it('A21.4b/c/d: the panel reaches the DESIGN’S OWN unavailable card, and no second one exists', () => {
    expect(appVue).toContain('v-if="v.md?.panel?.hasDemo"');
    expect(appVue).toContain('v-if="v.md?.panel?.noDemo"');
    // Twice and only twice: the detail's card and the panel's, the same markup (A-C31 (2):
    // "do not invent a second unavailable card").
    expect((appVue.match(/Community data unavailable for this location/g) ?? []).length).toBe(2);
    expect((appVue.match(/The Census geography for this address has not been matched yet\./g) ?? []).length).toBe(2);
    // The "View full listing" CTA stays OUTSIDE both branches — navigation is not data — and the
    // footnote that describes the figures stays inside `hasDemo` with them.
    const insights = appVue.slice(appVue.indexOf('v-if="v.md?.panel?.isInsights"'), appVue.indexOf('v-if="v.md?.panel?.isOther"'));
    expect((insights.match(/v-if="v\.md\?\.panel\?\.hasDemo"/g) ?? []).length).toBe(2);
    expect(insights.indexOf('v-if="v.md?.panel?.noDemo"')).toBeLessThan(insights.indexOf('View full listing'));
    // A27.4 (D-C39) corrected the footnote's first sentence: the band is a straight-line
    // catchment, never a drive time. Its place in the order is what this line measures.
    expect(insights.indexOf('View full listing')).toBeLessThan(insights.indexOf('A catchment figure is a straight-line area'));
    expect(appVue, 'the corrected footnote must not come back as a drive time').not.toContain('Drive-time figures are approximated');
  });

  // D-C42 (John, 2026-09-11). The sub-line A27.7 puts under the heading is a TEMPLATE amendment,
  // so it is pinned here for the reason the four above are: the reference and the app are
  // generated from the same amended design and would lose it together, leaving the DOM oracle and
  // the pixel gate both green. Reverting A27.7 leaves `overviewScope` computed and rendered
  // nowhere, which is exactly the shape A21.5a's own pin was written for.
  it('A27.7: the geography is a sub-line UNDER the heading, and the heading is still data', () => {
    const insights = appVue.slice(appVue.indexOf('v-if="v.md?.panel?.isInsights"'), appVue.indexOf('v-if="v.md?.panel?.isOther"'));
    // The heading interpolation A21.5a introduced is untouched — A27.6 retired its BEHAVIOUR,
    // not its markup.
    expect(insights).toContain('{{ __s(v.md?.panel?.overviewTitle) }}');
    // …and the label now renders beneath it, in its own element, gated so that a listing with no
    // label has no element at all rather than an empty one.
    expect(insights, 'the sub-line is not rendered anywhere on the Insights tab').toContain('{{ __s(v.md?.panel?.overviewScope) }}');
    expect(insights).toContain('v-if="v.md?.panel?.hasOverviewScope"');
    expect(
      insights.indexOf('{{ __s(v.md?.panel?.overviewTitle) }}'),
      'the geography is not BENEATH the heading'
    ).toBeLessThan(insights.indexOf('{{ __s(v.md?.panel?.overviewScope) }}'));
    // …and it is above the tiles it describes, not appended after the section.
    expect(insights.indexOf('{{ __s(v.md?.panel?.overviewScope) }}'))
      .toBeLessThan(insights.indexOf('v-for="(o, $index) in __arr(v.md?.panel?.overviewTiles)"'));
    // The design's own place line, taken whole — A27.7 invents no type, colour or spacing. Three
    // times in the file and only three: `md.panel.place`, A27.7's own, and A31.10's snapshot-strip
    // mode sub-line, which is composed from the SAME declaration for the same reason (Task SNAP).
    // The count is what keeps that true: a fourth occurrence is either another composition — which
    // belongs in this list — or a style someone typed by hand.
    expect((appVue.match(/font-size: 12\.5px; color: var\(--vf-text\); margin-top: 2px;/g) ?? []).length).toBe(3);
  });

  // ---------------------------------------------------------------------------------------
  // A31 (Task SNAP, ruling D-C50 as revised, 2026-09-12) — the Market snapshot's two modes.
  // ---------------------------------------------------------------------------------------
  it('A31.10: the mode is the FIRST thing in the strip’s body, in the design’s own heading pair', () => {
    const strip = appVue.slice(appVue.indexOf('v-if="v.md?.stripOpen"'), appVue.indexOf('Sources: U.S. Census Bureau (ACS, CBP)'));
    expect(strip).toContain('{{ __s(v.md?.stripMode) }}');
    expect(strip).toContain('v-if="v.md?.hasStripModeSub"');
    expect(strip).toContain('{{ __s(v.md?.stripModeSub) }}');
    // First: before the sub-line, and both before the first card.
    expect(strip.indexOf('{{ __s(v.md?.stripMode) }}')).toBeLessThan(strip.indexOf('{{ __s(v.md?.stripModeSub) }}'));
    expect(strip.indexOf('{{ __s(v.md?.stripModeSub) }}'))
      .toBeLessThan(strip.indexOf('v-for="(c, $index) in __arr(v.md?.stripCards)"'));
    // The heading is the docked panel's own Insights heading declaration, byte for byte — no new
    // size, weight or colour reaches the strip.
    expect(strip).toContain('style="font-family: var(--rf-display); font-size: 14.5px; font-weight: 800; color: var(--vf-navy);"');
    // …and it is INSIDE `stripOpen`, which is what keeps every Browse state but the two that open
    // the strip on its own pixels: the collapsed header row is unchanged.
    const header = appVue.slice(appVue.indexOf('Market snapshot'), appVue.indexOf('v-if="v.md?.stripOpen"'));
    expect(header, 'the mode reached the always-visible header row').not.toContain('stripMode');
  });
});
