import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { MANIFEST_PATH, SNAPSHOT_DIR, UNCHANGED_SCREENS, hashBaselines } from './baseline-manifest.mjs';

// Global Constraint (f) / spec D6 (option B, Task V13): the thirteen non-Browse screens. Local
// design amendment A1 put V2's display typography back, so they hash to their V1-era V2 baselines
// and byte-identity is the primary proof once more — for FOUR of them still (`detail`, `requests`,
// `mobile-list`, `mobile-detail`). The other nine were re-based by Task I8a: since A5.4 the
// account menu renders the signed-in account's own label, and `seller-dash`, the four `wizard-*`
// and the four `admin-*` are captured as the accounts that can actually open them (a seller and an
// admin), so their header line differs from the design's single fixture persona by design
// (A-I8.2 / D-I8-8). The buyer-family states did not move there: the oracle persona for those is a
// buyer whose computed label reproduces the fixture letter for letter, which is why it was chosen.
// Task I8a's third commit then re-based all thirteen again — the launch removal took the prototype
// jump bar off the top of every screen, so all 28 approved states moved BY DESIGN, by ruled
// amendment rather than by a code leak (D-I8-6). The manifest keeps doing the job it was built
// for: from here on, a moved hash means a CODE change moved a screen the design did not. Zero regression is proved
// as well by the DOM oracle (node-for-node identical to the amended V3 reference) plus the
// zero-tolerance pixel gate. A moved hash means a CODE change moved a screen the design did
// not: stop and diff, never re-write the manifest.
//
// Amendment A14 (John, 2026-09-08: "the Give button must be identical to the
// https://vinfoundation.org/ where the button is an actual drop down (match button design
// pixel-by-pixel)", and on the font: "Self-host Montserrat 600 under the SIL Open Font Licence,
// scoped exclusively to the Give button and its menu. Keep the rest of the design typography
// unchanged.") re-based the manifest a third time. The Give control is ONE unconditional
// <button> at V3:104, outside both the signedIn and the signedOut blocks, so it is in the header
// of every desktop screen; A14 changes its face, size, weight, padding and radius and gives it a
// chevron, which reflows the header's flex row everywhere it appears. Ruled design change,
// applied through the D15 engine, so the design and the app moved together — the DOM oracle
// stayed node-for-node identical and the pixel gate stayed at maxDiffPixels: 0 throughout.
//
// ELEVEN of the thirteen moved, not thirteen: `mobile-list` and `mobile-detail` are captured
// inside the prototype's 390x800 phone frame, which renders its own mobile header and never the
// desktop one, so the Give control is not on those two screenshots at all. Their hashes are
// UNCHANGED across A14 — which is the tidiest available proof that this amendment reached
// nothing but the desktop header, since a font or token leak would have moved them too.
//
// Amendment A18 (John, 2026-09-09: "the arrow icons are backwards on each location, reverse
// each") re-based ONE row. The detail's Back-to-results arrow (V3:895) pointed away from the
// results — the glyph points left unrotated and the design had rotated it; A18.2 removes the
// rotation, so `detail` moved by ruled design change. The other twelve kept their hashes: the
// two phone-frame captures because the frame's own sign-out arrow (V3:1434) is not in the ruling
// and was not touched, the other ten because nothing but that one `<img>` style changed. That is
// the tidiest available proof that A18 reached exactly the two elements John named. A18.1's
// site (the docked panel's CTA) is a Browse capture and not in this manifest. (Line numbers
// name the design as it stood at this re-pin; the rows in LOCAL_AMENDMENTS.md carry the ones
// re-checked after later insertions.)
//
// From here a moved hash means a CODE change moved a screen the design did not.
const manifest = JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')) as { platform: string; screens: Record<string, string> };

// The manifest is a within-worktree leak detector (spec D13 / Global Constraint (l2)), not a
// CI oracle: its PNGs are git-ignored (.gitignore:6-7) and were frozen once, on one platform's
// Step-0 baselines. A fresh checkout — CI included — has none of them, on any platform, so this
// suite is only meaningful on the platform the manifest was captured on, with those PNGs
// present in the worktree. Skip (rather than fail) when either half is missing; CI's real
// protection for the unchanged screens is `npm run test:visual` at zero tolerance, against
// baselines regenerated from the reference in the same run.
const platformMatches = manifest.platform === process.platform;
const pngsPresent = platformMatches && UNCHANGED_SCREENS.every((name) => existsSync(join(SNAPSHOT_DIR, `${name}-${process.platform}.png`)));
const canRun = platformMatches && pngsPresent;
const skipReason = !platformMatches
  ? `manifest was frozen on ${manifest.platform}; this run is ${process.platform} — the pixel gate is the oracle here`
  : 'manifest PNGs are not present in this worktree (git-ignored) — the pixel gate is the oracle here';

describe.skipIf(!canRun)(canRun ? 'unchanged-screen baseline manifest' : `unchanged-screen baseline manifest (skipped: ${skipReason})`, () => {
  it('covers exactly the thirteen screens V3 must not move', () => {
    expect(Object.keys(manifest.screens).sort()).toEqual([...UNCHANGED_SCREENS].sort());
    expect(UNCHANGED_SCREENS).toHaveLength(13);
  });

  it('was captured on this platform, so the hashes are comparable', () => {
    expect(manifest.platform).toBe(process.platform);
  });

  it('every frozen baseline still hashes to its recorded SHA-256', () => {
    expect(hashBaselines()).toEqual(manifest.screens);
  });
});
