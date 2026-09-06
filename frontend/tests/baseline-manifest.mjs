// Freezes the SHA-256 of every baseline PNG that the Browse V3 port must not move
// (CHANGE_LOG C14 + DEAD_CODE_CHECKLIST "Zero-risk requirements", minus header-1100 and
// header-1000: those run `steps: browse` and are Browse screenshots, which README §2 requires
// V3 to change — spec D6). Written ONCE, over the Step-0 oracles regenerated from main's V2
// reference, before Task V1 lands the bundle; read by baseline-manifest.test.ts at the end of
// V7, V9, V10 and after every deletion commit in V11. The PNGs it hashes are git-ignored
// (.gitignore:6-7), so this is a within-worktree leak detector, not a CI oracle. Never
// regenerate it to make a test pass — a changed hash is the leak detector doing its job.
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
