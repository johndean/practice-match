import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { MANIFEST_PATH, SNAPSHOT_DIR, UNCHANGED_SCREENS, hashBaselines } from './baseline-manifest.mjs';

// Global Constraint (f) / spec D6: the thirteen screens V3 does not touch (CHANGE_LOG C14 +
// DEAD_CODE_CHECKLIST "Zero-risk requirements", minus the two header states, which are Browse
// screenshots) must be BYTE-identical before and after the port. Their SHA-256s are frozen
// here, once, on `main`'s Step-0 baselines, before any V3 change lands. Every later task
// re-runs this file; a single moved byte means the port leaked into shared code — stop and
// diff, do not re-write the manifest.
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
