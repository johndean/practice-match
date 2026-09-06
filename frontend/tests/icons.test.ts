import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const FRONTEND = join(import.meta.dirname, '..');
const PUBLIC_ICONS = join(FRONTEND, 'public', 'assets', 'icons');
const BUNDLE_ICONS = join(FRONTEND, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'assets', 'icons');
const DC = join(FRONTEND, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'Practice Match V3.dc.html');

const NEW_IN_V3 = ['sub-chevron.svg', 'sub-close-thin.svg', 'sub-plus-thin.svg', 'sub-bar-chart.svg', 'sub-reset-view.svg', 'sub-legend-list.svg', 'sub-layers-stack.svg'];

function referenced(text: string): string[] {
  return [...new Set([...text.matchAll(/\/?assets\/icons\/([A-Za-z0-9._-]+\.svg)/g)].map((m) => m[1]))].sort();
}

// README Task 5. Filenames are the contract: a real VIN glyph drops in with no code change.
describe('icon assets', () => {
  it('ships the seven glyphs V3 introduces, byte-identical to the bundle', () => {
    for (const f of NEW_IN_V3) {
      expect(existsSync(join(PUBLIC_ICONS, f)), `${f} is missing from frontend/public/assets/icons/`).toBe(true);
      expect(readFileSync(join(PUBLIC_ICONS, f)).equals(readFileSync(join(BUNDLE_ICONS, f))), `${f} differs from the bundle's copy`).toBe(true);
    }
  });

  it('every icon the V3 design references exists on disk — no /assets/icons 404 on any screen', () => {
    const missing = referenced(readFileSync(DC, 'utf8')).filter((f) => !existsSync(join(PUBLIC_ICONS, f)));
    expect(missing).toEqual([]);
  });

  it('every icon the generated app references exists on disk', () => {
    const missing = referenced(readFileSync(join(FRONTEND, 'src', 'App.vue'), 'utf8')).filter((f) => !existsSync(join(PUBLIC_ICONS, f)));
    expect(missing).toEqual([]);
  });
});
