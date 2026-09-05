import { test } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCREENS } from './screens';
import { booted, prepare, settle } from './harness';
import { serialize } from './dom';

const OUT = join(fileURLToPath(new URL('.', import.meta.url)), 'dom-snapshots');

// Produces the DOM oracle's snapshots from the approved design — the second oracle
// alongside reference-baselines.spec.ts's pixel screenshots. Run only via
// `--project=reference`; the JSON is git-ignored (see .gitignore) and regenerated here,
// never hand-edited.
test.describe('reference DOM snapshots', () => {
  for (const s of SCREENS) {
    test(s.name, async ({ page }) => {
      mkdirSync(OUT, { recursive: true });
      await prepare(page);
      if (s.viewport) await page.setViewportSize(s.viewport);
      await booted(page);
      await s.steps(page);
      await settle(page);
      writeFileSync(join(OUT, `${s.name}.json`), JSON.stringify(await serialize(page, { design: true }), null, 2));
    });
  }
});
