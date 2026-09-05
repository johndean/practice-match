import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCREENS } from './screens';
import { booted, prepare, settle } from './harness';
import { diff, serialize, type DomNode } from './dom';

const SNAPSHOTS = join(fileURLToPath(new URL('.', import.meta.url)), 'dom-snapshots');

function referenceSnapshot(name: string): DomNode {
  return JSON.parse(readFileSync(join(SNAPSHOTS, `${name}.json`), 'utf8')) as DomNode;
}

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
      expect(diff(referenceSnapshot(s.name), await serialize(page))).toEqual([]);
    });
  }
});
