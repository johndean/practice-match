// Freezes the SHA-256 of every baseline PNG for the thirteen non-Browse screens. Written
// TWICE and only twice: in Task V1 over main's V2 oracles (the leak detector through V7), and
// again in Task V9 Step 8 over the V3 oracles, after the DOM oracle and the pixel gate proved
// all 27 states against V3 — because the V3 design deliberately restyled every display-size
// heading (V7 review, spec D6 option A), so the V2 hashes could not survive and byte-identity
// is not how zero regression is proved for these screens any more. Read by
// baseline-manifest.test.ts at the end of V10 and after every deletion commit in V11: a moved
// hash THERE means a code change moved a screen the design did not. The PNGs it hashes are
// git-ignored (.gitignore:6-7), so this is a within-worktree leak detector, not a CI oracle.
// Never regenerate it a third time to make a test pass.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));

export const SNAPSHOT_DIR = join(HERE, 'visual.spec.ts-snapshots');
export const MANIFEST_PATH = join(HERE, 'baseline-manifest.json');

export const UNCHANGED_SCREENS = [
  'mobile-list', 'mobile-detail',
  'detail', 'requests', 'seller-dash',
  'wizard-step-1', 'wizard-step-7', 'wizard-preview', 'wizard-done',
  'admin-users', 'admin-listings', 'admin-requests', 'admin-data-sources'
];

export function hashBaselines() {
  const out = {};
  for (const name of UNCHANGED_SCREENS) {
    const file = join(SNAPSHOT_DIR, `${name}-${process.platform}.png`);
    out[name] = createHash('sha256').update(readFileSync(file)).digest('hex');
  }
  return out;
}

export function writeManifest() {
  writeFileSync(MANIFEST_PATH, `${JSON.stringify({ platform: process.platform, screens: hashBaselines() }, null, 2)}\n`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) writeManifest();
