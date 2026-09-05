import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildAppVue, convert, extractTemplate } from '../scripts/convert-dc.mjs';

const ROOT = join(import.meta.dirname, '..');
const DC = join(ROOT, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v2', 'Practice Match V2.dc.html');

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
    const out = compileTemplate({ source: descriptor.template!.content, filename: 'App.vue', id: 'app', compilerOptions: { whitespace: 'preserve' } });
    expect(out.errors).toEqual([]);
  });
  it('retired the JS hover directive: no v-hover, no hover.js', () => {
    expect(readFileSync(join(ROOT, 'src/App.vue'), 'utf8')).not.toContain('v-hover');
    expect(() => readFileSync(join(ROOT, 'src/directives/hover.js'))).toThrow();
  });
});
