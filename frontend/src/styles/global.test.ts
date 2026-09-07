import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = join(import.meta.dirname, '..', '..', '..');
const CSS = readFileSync(join(ROOT, 'frontend', 'src', 'styles', 'global.css'), 'utf8');
const REFERENCE = readFileSync(join(ROOT, 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'Practice Match V3.dc.html'), 'utf8');

// README Task 3b: .rf-callout and .rf-tip target LEAFLET's own tooltip elements, which live
// outside component scope, so they cannot be scoped styles — global.css is their home. They
// are copied out of the reference's helmet, so this test compares them against the reference
// rather than restating them, including the ::before arrow-colour overrides.
describe('.rf-tip / .rf-callout reach the app exactly as the reference declares them', () => {
  const RULES = [
    '.leaflet-tooltip.rf-callout { background: #fff; border: 1px solid rgba(0,58,112,.12); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,58,112,.22); padding: 8px 10px; color: #003a70; white-space: nowrap; }',
    '.leaflet-tooltip.rf-callout::before { border-top-color: #fff; }',
    '.leaflet-tooltip.rf-tip { background: #fff; border: 1px solid rgba(0,58,112,.12); border-radius: 6px; box-shadow: 0 3px 10px rgba(0,58,112,.18); color: #003a70; }',
    '.leaflet-tooltip.rf-tip::before { border-top-color: #fff; }'
  ];

  it('the four rules this test pins are the four the reference helmet declares', () => {
    for (const rule of RULES) expect(REFERENCE, `the reference no longer declares: ${rule}`).toContain(rule);
  });

  it('global.css carries all four, byte-for-byte', () => {
    for (const rule of RULES) expect(CSS, `global.css is missing: ${rule}`).toContain(rule);
  });
});
