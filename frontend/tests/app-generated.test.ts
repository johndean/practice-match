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
    for (const gone of ['browseMode', 'browseToggle', 'hasPeek']) {
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
    expect(insights.indexOf('View full listing')).toBeLessThan(insights.indexOf('Drive-time figures are approximated'));
  });
});
