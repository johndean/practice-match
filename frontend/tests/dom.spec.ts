import { test, expect } from '@playwright/test';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCREENS } from './screens';
import { booted, prepare, settle } from './harness';
import { diff, readReferenceSnapshot, serialize, summarise } from './dom';

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
