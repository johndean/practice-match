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
// A53 (Task REVOKE-UI, John's ruling of 2026-09-19) then re-based ONE of the thirteen,
// `seller-dash`: the family's own Revoke button (A53.1) renders on the screen's default fixture
// accepted row, so its pixels changed by the same ruled composition every other family in
// CLAUDE.md's amendment paragraph records — the other twelve, `requests` included, are unmoved,
// measured the A33 method (baselines regenerated cold before and after A53, all 58 PNG and DOM
// hashes diffed, and exactly `seller-dash`/`seller-dash-empty` — the second not among these
// thirteen — differ).
// Ruling D-C59 (John, 2026-09-20 — "a buyer can not be a seller and a seller can not be a
// buyer") then re-based FIVE: `seller-dash` and the four `wizard-*`. No template or script in
// the design bundle changed — `scripts/seed_persona.py`'s `seller@practice-match.test` persona
// changed, from `roles=("buyer","seller")` (exactly the account shape the ruling forbids, which
// `migrations/100_role_exclusivity.sql`'s trigger now refuses to grant) to `roles=("seller",)` —
// so the account menu these five screens render renders "Approved seller · StartUp Club" rather
// than "Approved buyer and seller · StartUp Club", the SAME A5.4/A-I8.2 mechanism the I8a re-base
// above used for the identical reason one ruling earlier. Measured the A33 method: baselines were
// regenerated cold before and after (a git stash of the ruling's own diff, and a database with
// and without migration 100 applied, since a persistent dev database does not un-apply a
// migration just because the working tree reverts it), and all 58 PNG and DOM hashes diffed.
// EIGHT states differ in total — `seller-dash`, `seller-dash-empty`, `wizard-step-1`,
// `wizard-step-7`, `wizard-preview`, `wizard-done`, `wizard-step-6-photos`, `wizard-step-6-review`
// — every one of them a screen captured as the `seller` persona and no other; `seller-dash-empty`,
// `wizard-step-6-photos` and `wizard-step-6-review` are not among these thirteen and carry no
// entry here. The other FIVE of the thirteen — `mobile-list`, `mobile-detail`, `detail`,
// `requests` and all four `admin-*` (captured as `design`, whose computed label is unchanged:
// `role_label` reads `admin` first in its own `elif` chain regardless of whether `design@` holds
// two roles or four) — are unmoved, which is the proof the ruling reached the seller persona's
// label and nothing else.
// Ruling D-C61 (John, 2026-09-21 — "no link may lead to a refusal", amendment family A55) then
// re-based SEVEN: `detail`, `requests`, `seller-dash` and the four `wizard-*` — every one of the
// thirteen captured as a `buyer` or `seller` persona (`page.admin` false for both), whose header
// now omits the VIN Foundation Admin door (A55.4, gated on `startPerms`/`this.props.perms`). This
// is the EXACT set A40's own held measurement named in 2026-09-13 ("the filter moved 28 of the 58
// approved states and seven of baseline-manifest.json's thirteen frozen hashes"), now finally
// spent under the ruling that pays for it. Measured the A33 method: baselines were regenerated
// cold before and after (a git stash of this branch's own diff) and all 59 PNG and DOM hashes
// diffed — THIRTY approved states move in total (two more than A40's 28-state prediction, both
// approved states appended to `screens.ts` after A40's 2026-09-13 measurement and captured as a
// non-admin persona: `seller-dash-empty` and `browse-recenter-location` — not a leak, the array
// simply grew), and `gate-seller-needed` is appended, an addition rather than a re-base. The other
// SIX of the thirteen — `mobile-list`, `mobile-detail` (the phone frame renders its own header,
// A14's own proof) and all four `admin-*` (captured as `design`, which holds `page.admin`
// regardless) — are unmoved, which is the proof the ruling reached exactly the header's own nav
// array and nothing else.
// Amendment family A57 (John, 2026-09-21 — "'withdrew' and 'withdrawed' are terms that should be
// used", read over A53's eight new pieces of copy) then re-based ONE of the thirteen again,
// `seller-dash`: its default fixture's accepted row (`r2`, `p7`) carries the SAME `canRevoke`
// button A53.1 put there, and A57.1 renames its text from "Revoke" to "Withdraw" — the one string
// on this screen the family's seven entries reach, since no approved state's default fixture ever
// carries a request whose `status` actually IS `"revoked"` (A57.2-A57.7's own branches are
// unreached pixels, e2e-only). Measured the A33 method: baselines were regenerated cold before and
// after (`git stash push` of this family's own two source files, `design-amendments.ts` and
// `LOCAL_AMENDMENTS.md`, regenerating the bundle between runs) and all 59 PNG and DOM hashes
// diffed — exactly TWO approved states move, `seller-dash` and `seller-dash-empty` (the second not
// among these thirteen, appended after A40's own 2026-09-13 measurement), both by the identical
// single-node diff (`"Revoke"` -> `"Withdraw"`, confirmed by diffing the DOM snapshot JSON
// directly). The other TWELVE of the thirteen are unmoved, which is the proof the ruling reached
// exactly the seller inbox's own button text and nothing else.
// Ruling D-C65 (John, 2026-09-23 — "implement full seller wizard audit", amendment family A58)
// then re-based ONE of the thirteen, `detail`. Findings S5 and S6 of the eight-step audit are two
// rows of the buyer's Property block that were FABRICATED: `{ k: "Parking", v: "On-site" }` was a
// hard-coded literal on every listing the product has ever served (`parking` occurs in no
// migration, no column, no route, no adapter and no wizard step, so no seller has ever been
// asked), and the row labelled "Facility type" was computed from `bldg` — the BUILDING STATUS the
// wizard's step 5 asks first — rather than from the listing's own `facilityType`, so a seller who
// answered "Medical park" was published to buyers as "Standalone building". A58.2 deletes the
// first and A58.3 makes the second read the listing's own field and render NO row while it carries
// none (absent beats faked). Two rows leaving a four-row, two-column grid reflows the page, so
// this hash is re-pinned under the ruling — the A18/A34/A38/A53/A55/A57 mechanism, a DESIGN change
// through the D15 engine with the app and the oracle moving together (the pixel gate stayed at
// maxDiffPixels: 0 and the DOM oracle stayed node-for-node identical throughout).
// The other TWELVE are unmoved, measured the A33 method and re-hashed from the PNGs after the
// write rather than inferred from this file's own test passing: baselines were regenerated cold
// before and after and all 59 PNG and 59 DOM hashes diffed — FOUR approved states move, `detail`,
// `detail-lightbox`, `detail-lightbox-next` and `interest-modal`, each in BOTH oracles and each
// one of the four captures that reach the desktop detail screen; the last three are not among
// these thirteen. `mobile-detail` does NOT move, which is the proof the change reached this block
// and nothing else: the phone frame renders its own detail screen and no `sections` block at all
// (`v.d?.sections` has exactly one reader in `App.vue`), so it has never drawn the Property block.
// The node-level diff on `detail` is TWO removals of 121 lines each and ZERO additions — the two
// row <div>s — with "Building status" and "Approximate square feet" surviving once each.
// Ruling D-C67 (John, 2026-09-24 — "all toggles must be fully functional and SELLER must be able
// to manage it all and per seller", amendment entries A58.7a-A58.7d) then re-based ONE of the
// thirteen again, `seller-dash`, and for the SAME reason A53 did: the family's one template edit
// (A58.7d) puts a "Change access" button beside the Withdraw button A53.1 already draws inside its
// own `i.canRevoke` block, and this screen's default fixture carries the accepted row (`r2`, `p7`)
// that block renders on. The ruling asks for a control the product has never drawn and a control
// is pixels, so the re-pin is intrinsic to it rather than a gate made to pass — the A18/A34/A38/
// A53/A55/A57 mechanism, a DESIGN change through the D15 engine with the app and the oracle moving
// together. The family's other three entries are SCRIPT-ONLY and reach no pixel: A58.7a's
// `r.grantedLabel` is absent on the design's own fixtures and on the oracle's `design-requests.mjs`
// rows alike, so both targets read the design's own sentence byte for byte, and A58.7b/A58.7c are
// handlers. Measured the A33 method: baselines were regenerated cold before the change and again
// after it and all 60 PNG and 60 DOM hashes diffed — exactly TWO approved states move,
// `seller-dash` and `seller-dash-empty`, in BOTH oracles, which is the identical pair A57's own
// measurement named and for the identical structural reason (`seller-dash-empty` is the EMPTY
// LISTINGS dashboard and renders the same inbox; it is not among these thirteen and carries no
// entry here). The other TWELVE are unmoved, re-hashed from the regenerated PNGs after the write
// rather than inferred from this file's own test passing.
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

/** Which screens hash differently from what the manifest recorded, in manifest order. */
export function compare(recorded, actual) {
  const moved = Object.keys(recorded).filter((name) => recorded[name] !== actual[name]);
  return { ok: moved.length === 0, moved };
}

/**
 * What an invocation MEANS, separated from doing it so it can be tested without a subprocess.
 *
 * This function exists because of a real defect (2026-09-11, found by Task 1 of the
 * neighbourhood-shading plan): there was no argument parsing here at all, so
 * `node tests/baseline-manifest.mjs --check` ignored the flag, rewrote the manifest and exited
 * 0. A step that ran `--check` and then the vitest guard was comparing the manifest against the
 * very PNGs it had just been written from, so a screen a code change had genuinely moved
 * reported green. The manifest is the leak detector for the thirteen screens the design must
 * not move; a flag that silently re-pins it defeats the only thing it does.
 *
 * An unrecognised argument REFUSES rather than falling through to a write, because falling
 * through to a write is exactly how the defect behaved.
 */
export function route(argv) {
  if (argv.length === 0) return { writes: true };
  if (argv.length === 1 && argv[0] === '--write') return { writes: true };
  if (argv.length === 1 && argv[0] === '--check') return { writes: false };
  throw new Error(
    `baseline-manifest: unknown argument ${JSON.stringify(argv.join(' '))} — use --check to compare, ` +
    '--write (or no argument) to re-pin under a ruling'
  );
}

/** Returns the process exit code; never writes under `--check`. */
export function main(argv) {
  const { writes } = route(argv);
  if (writes) {
    writeManifest();
    return 0;
  }
  const recorded = JSON.parse(readFileSync(MANIFEST_PATH, 'utf8'));
  if (recorded.platform !== process.platform) {
    process.stderr.write(`baseline-manifest: pinned on ${recorded.platform}, this run is ${process.platform} — cannot compare\n`);
    return 2;
  }
  const { ok, moved } = compare(recorded.screens, hashBaselines());
  if (ok) {
    process.stdout.write(`baseline-manifest: ${Object.keys(recorded.screens).length} frozen screens checked, none moved\n`);
    return 0;
  }
  process.stderr.write(`baseline-manifest: MOVED — ${moved.join(', ')}\n`);
  process.stderr.write('A moved hash means a CODE change moved a screen the design did not. Stop and diff; never re-pin to make a gate pass.\n');
  return 1;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) process.exit(main(process.argv.slice(2)));
