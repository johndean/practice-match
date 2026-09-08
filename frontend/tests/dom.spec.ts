import { test, expect } from '@playwright/test';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCREENS } from './screens';
import { booted, prepare, settle } from './harness';
import { diff, readReferenceSnapshot, serialize, summarise } from './dom';

// ---------------------------------------------------------------------------------------
// A-L6.2 (2) — not against a remote target.
//
// This suite compares the app against baselines generated from the DESIGN file. Since Task L6
// the app reads its practices from `/api/listings`: locally `prepare()` answers with the
// design's own fixtures (spec D6), so the comparison still means what it always meant, but
// against a remote target that stub is disarmed by design (`listingsStubUrl`) and QA is seeded
// with eighteen different hospitals. Every Browse, detail, mobile and market state would then
// differ by construction, and the operator would get a wall of red with no way to tell a
// regression from the expected data change. The remote parity run is smoke, sign-in and account
// flows from here (docs/RUNBOOK-identity.md §12).
// ---------------------------------------------------------------------------------------
test.skip(
  !!process.env.PW_APP_URL,
  "the oracles compare against the design's fixtures; a seeded target differs by construction — A-L6.2"
);

const SNAPSHOTS = join(fileURLToPath(new URL('.', import.meta.url)), 'dom-snapshots');

// The DOM oracle: every approved screen state's rendered DOM must structurally match the
// design's, element by element — a second gate alongside visual.spec.ts's pixel
// comparison, naming any structural/attribute/style/text divergence by path instead of
// leaving it to be inferred from a pixel diff.
test.describe('DOM parity with the approved design', () => {
  for (const s of SCREENS) {
    test(s.name, async ({ page }) => {
      await prepare(page);
      if (s.viewport) await page.setViewportSize(s.viewport);
      await booted(page);
      await s.steps(page);
      await settle(page);
      // The assertion is still on the WHOLE list — nothing is capped away — but the message
      // Playwright prints when it fails is summarise()'d, so a badly diverged state stays
      // readable instead of dumping hundreds of lines into the run (re-review minor 4).
      const lines = diff(readReferenceSnapshot(SNAPSHOTS, s.name), await serialize(page));
      expect(lines, summarise(lines)).toEqual([]);
    });
  }
});
