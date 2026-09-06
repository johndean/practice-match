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
  const FOOTER = '\nexport { Component };\n';

  function designScript(html: string): string {
    const open = /<script type="text\/x-dc" data-dc-script[^>]*>/.exec(html)!;
    const start = open.index + open[0].length;
    return html.slice(start, html.indexOf('</script>', start));
  }

  it('matches byte-for-byte, header and export aside, with only the documented asset rewrite', () => {
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
