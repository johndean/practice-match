// Freezes the SHA-256 of every baseline PNG for the thirteen non-Browse screens. Written
// THREE times and only three times: in Task V1 over main's V2 oracles (the leak detector
// through V7); in Task V9 Step 8 over the V3 oracles, after the DOM oracle and the pixel gate
// proved all 27 states against V3 (the V3 design had restyled every display-size heading, so
// the V2 hashes could not survive — spec D6 option A); and in Task V13 Step 5, after John's
// ruling "keep the V2 header and do not restyle header or fonts" put V2's typography back
// through local design amendment A1 (spec D15/D16, option B), which returned twelve of the
// thirteen to their V1-era V2 hashes. (`mobile-detail` is the exception: its 28 px
// `{{ d.priceLabel }}` shares a (tag, text) key, so A1's pairing rule could not reach it —
// recorded for John, not re-based silently.) Read by baseline-manifest.test.ts: a moved hash
// there means a code change moved a screen the design did not. The PNGs it hashes are
// git-ignored (.gitignore:6-7), so this is a within-worktree leak detector, not a CI oracle.
// Never regenerate it again to make a test pass.
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
