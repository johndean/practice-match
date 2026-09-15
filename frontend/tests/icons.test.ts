import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const FRONTEND = join(import.meta.dirname, '..');
const PUBLIC_ICONS = join(FRONTEND, 'public', 'assets', 'icons');
const BUNDLE_ICONS = join(FRONTEND, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'assets', 'icons');
const DC = join(FRONTEND, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'Practice Match V3.dc.html');
// The bundle's SECOND amendable file. A51 (John, 2026-09-16) put the first `assets/icons/`
// reference into it — the recenter button's crosshair — and until then nothing walked it, so a
// glyph named only by the map component could have 404'd on every Browse screen unseen.
const JSX = join(FRONTEND, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'MarketMapV3.jsx');

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

  // A51: the map component is the one part of the design that is PORTED by hand rather than
  // generated, so its icons reach the app through `MarketMapView.vue` and not through App.vue.
  // Both sides are walked, and each glyph is required to be the bundle's own bytes — the reference
  // serves the bundle's copy and the app serves `frontend/public/`'s, and a diff between them is a
  // pixel diff on every desktop Browse capture.
  it('every icon the V3 map component references ships, on both targets, byte-identical to the bundle', () => {
    const named = referenced(readFileSync(JSX, 'utf8'));
    expect(named.length, 'the map component names no icon at all — A51\'s recenter glyph is gone').toBeGreaterThan(0);
    for (const f of named) {
      expect(existsSync(join(BUNDLE_ICONS, f)), `${f} is missing from the design bundle`).toBe(true);
      expect(existsSync(join(PUBLIC_ICONS, f)), `${f} is missing from frontend/public/assets/icons/`).toBe(true);
      expect(readFileSync(PUBLIC_ICONS + '/' + f).equals(readFileSync(BUNDLE_ICONS + '/' + f)), `${f} differs from the bundle's copy`).toBe(true);
    }
    // …and the port really does draw them: the hand-written Vue mirror names the same set.
    expect(referenced(readFileSync(join(FRONTEND, 'src', 'components', 'MarketMapView.vue'), 'utf8')),
      'the ported map component draws a different set of glyphs from the design\'s own').toEqual(named);
  });

  it('every icon the generated app references exists on disk', () => {
    const missing = referenced(readFileSync(join(FRONTEND, 'src', 'App.vue'), 'utf8')).filter((f) => !existsSync(join(PUBLIC_ICONS, f)));
    expect(missing).toEqual([]);
  });
});
