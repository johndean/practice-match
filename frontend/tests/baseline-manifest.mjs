// Freezes the SHA-256 of every baseline PNG for the thirteen non-Browse screens. It is
// regenerated ONLY when the design reference itself changes by a ruling, and the regeneration
// is recorded with that ruling: Task V1 froze it over main's V2 oracles (the leak detector
// through V7); Task V9 Step 8 re-based it on the V3 oracles, after the DOM oracle and the
// pixel gate proved all 27 states against V3 (the V3 design had restyled every display-size
// heading, so the V2 hashes could not survive — spec D6 option A); Task V13 Step 5 re-based it
// again after John's ruling "keep the V2 header and do not restyle header or fonts" put V2's
// typography back through local design amendment A1 (spec D15/D16, option B), which returned
// all thirteen screens to their V1-era V2 hashes; Task I8a re-based NINE of them (`seller-dash`,
// the four `wizard-*`, the four `admin-*`) when the account menu began rendering the signed-in
// account's true label instead of the design's single fixture persona (A5.4 / A-I8.2, default
// D-I8-8) — the other four kept their hashes there, because the account those screens are
// captured as is a buyer whose computed label IS the fixture's. Task I8a's third commit then
// re-based ALL thirteen: the launch removal (A6.1–A6.6, A7.1–A7.2) took the prototype jump bar
// off the top of every screen, so all 28 approved states moved by ruled design change (D-I8-6).
// Read by baseline-manifest.test.ts: a moved
// hash there means a CODE change moved a screen the design did not. The PNGs it hashes are
// git-ignored (.gitignore:6-7), so this is a within-worktree leak detector, not a CI oracle.
// Never regenerate it to make a test pass — only to record a ruled design change.
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
