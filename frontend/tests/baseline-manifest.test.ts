import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { MANIFEST_PATH, UNCHANGED_SCREENS, hashBaselines } from './baseline-manifest.mjs';

// Global Constraint (f) / spec D6: the thirteen screens V3 does not touch (CHANGE_LOG C14 +
// DEAD_CODE_CHECKLIST "Zero-risk requirements", minus the two header states, which are Browse
// screenshots) must be BYTE-identical before and after the port. Their SHA-256s are frozen
// here, once, on `main`'s Step-0 baselines, before any V3 change lands. Every later task
// re-runs this file; a single moved byte means the port leaked into shared code — stop and
// diff, do not re-write the manifest.
describe('unchanged-screen baseline manifest', () => {
  const manifest = JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')) as { platform: string; screens: Record<string, string> };

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
