import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const FRONTEND = join(import.meta.dirname, '..');
const BUNDLE = join(FRONTEND, '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3');
const BUNDLE_FONTS = join(BUNDLE, 'assets', 'fonts');
const PUBLIC_FONTS = join(FRONTEND, 'public', 'assets', 'fonts');
const DC = join(BUNDLE, 'Practice Match V3.dc.html');
const GLOBAL_CSS = join(FRONTEND, 'src', 'styles', 'global.css');

// ---------------------------------------------------------------------------------------
// A14.6 — Montserrat 600, self-hosted (John, 2026-09-08: "Self-host Montserrat 600 under the SIL
// Open Font Licence, scoped exclusively to the Give button and its menu").
//
// The live vinfoundation.org Give button is set in Montserrat 600; the design bundle loads only
// ProximaNova, whose ladder has no 600 at all, so "match button design pixel-by-pixel" cannot be
// met from the bundle's own faces. The ruling adds ONE face, and it has to reach BOTH targets
// identically or the zero-tolerance pixel gate would be comparing two different typefaces:
//
//   reference  the amended design's helmet <style> (amendment A14.6), served from the bundle root
//              by tests/reference-server.mjs → `assets/fonts/Montserrat-SemiBold.woff2`
//   app        frontend/src/styles/global.css, the helmet's port (the same file the four Leaflet
//              tooltip rules are ported into) → `/assets/fonts/Montserrat-SemiBold.woff2`
//
// which is exactly the platform spec's §3 rule-1 asset rewrite (`assets/` → `/assets/`), the same
// one `logic.js`'s port and the DOM oracle's Rule B apply. Both paths resolve to byte-identical
// copies of the same file, and that is what the first case below proves.
// ---------------------------------------------------------------------------------------
describe('the Give control\'s self-hosted Montserrat (A14.6)', () => {
  const FILES = ['Montserrat-SemiBold.woff2', 'OFL.txt'];

  it('ships in the design bundle and in the app\'s public assets, byte-identical', () => {
    for (const f of FILES) {
      expect(existsSync(join(BUNDLE_FONTS, f)), `${f} is missing from the design bundle's assets/fonts/`).toBe(true);
      expect(existsSync(join(PUBLIC_FONTS, f)), `${f} is missing from frontend/public/assets/fonts/`).toBe(true);
      expect(readFileSync(join(PUBLIC_FONTS, f)).equals(readFileSync(join(BUNDLE_FONTS, f))),
        `${f} differs between the bundle and the app — the two targets would render different pixels`).toBe(true);
    }
  });

  it('is a real WOFF2, and the licence it ships under travels with it', () => {
    // wOF2 — the WOFF2 signature (W3C WOFF2 §4.1). A truncated or mis-fetched download would
    // otherwise sit on disk and simply fail to load in the browser, which `font-display: swap`
    // would hide behind the fallback face on both targets at once.
    expect(readFileSync(join(BUNDLE_FONTS, 'Montserrat-SemiBold.woff2')).subarray(0, 4).toString('latin1')).toBe('wOF2');
    const ofl = readFileSync(join(BUNDLE_FONTS, 'OFL.txt'), 'utf8');
    expect(ofl, 'the ruling names the licence — it ships beside the font, always').toContain('SIL Open Font License, Version 1.1');
    expect(ofl).toContain('Montserrat');
  });

  it('the reference declares exactly one @font-face, for Montserrat 600, from the bundle\'s own assets', () => {
    const dc = readFileSync(DC, 'utf8');
    expect(dc.split('@font-face').length - 1, 'A14.6 adds one face and no more').toBe(1);
    expect(faceRule(dc)).toContain("font-family: 'Montserrat';");
    expect(faceRule(dc)).toContain("src: url('assets/fonts/Montserrat-SemiBold.woff2') format('woff2');");
    expect(faceRule(dc)).toContain('font-weight: 600; font-style: normal; font-display: swap;');
  });

  it('global.css carries the reference\'s rule, differing only by the `assets/` → `/assets/` rewrite', () => {
    // Derived from the reference rather than restated, so the app cannot drift onto a different
    // face, weight, file or display strategy than the oracle it is measured against.
    const expected = faceRule(readFileSync(DC, 'utf8')).replace("url('assets/", "url('/assets/");
    expect(faceRule(readFileSync(GLOBAL_CSS, 'utf8'))).toBe(expected);
  });
});

/** The `@font-face { … }` block, indentation stripped so the two files' own layouts do not matter. */
function faceRule(text: string): string {
  const at = text.indexOf('@font-face');
  expect(at, 'no @font-face at all').toBeGreaterThan(-1);
  return text.slice(at, text.indexOf('}', at) + 1).split('\n').map((l) => l.trim()).join('\n');
}
