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
