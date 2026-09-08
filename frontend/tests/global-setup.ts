/**
 * Runs ONCE in the Playwright runner process, before any worker starts (round 3, ruling 2).
 *
 * It exists to mint one id per RUN. The persona memo file (`harness.ts`'s `MEMO_FILE`) lets a
 * worker re-use a session another worker of the same run already paid an `SIGNIN_IP` attempt for —
 * which matters precisely when Playwright shuts a worker down after a test failure and starts a new
 * one, because otherwise a failing run pays its sign-ins again until the API answers 429 and buries
 * the failure that started it (review round 1, M3).
 *
 * That needs a value every worker of the run agrees on, and the environment is the only such
 * channel: workers inherit the runner's `process.env`. A worker-local value cannot do it — round 2
 * derived the id from `process.uptime()`, which is stable inside a green run (one worker) and
 * different in every restarted worker, i.e. useless in the only case the file is for.
 *
 * `?? randomUUID()` rather than always minting: an outer harness (CI sharding, a wrapper script)
 * may want to declare the run itself, and then the file legitimately belongs to it.
 *
 * The delete is the run-scoping guarantee. Playwright's own clearing of `test-results/` is anchored
 * to the CWD it was launched from, which only coincides with `MEMO_FILE` when the suite runs from
 * `frontend/`; this is anchored to the source tree and therefore always right. A file this run did
 * not stamp may name sessions that have since been revoked, and adopting one would run later tests
 * as the wrong account with no failure anywhere near the cause.
 *
 * Task S7 (John's ruling, 2026-09-08) gave it a second job: a REMOTE run reseeds the target's
 * fixtures here, because this is the same place a local run implicitly does it — before any test.
 * See `remoteReseedPlan` below.
 */
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { existsSync, readFileSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { MEMO_FILE, isStaleMemoFile, runId } from './harness';

/** The repository root — where `poetry` and `app.main` resolve, and the `cwd` `targets.ts` gives
 *  the local `api` web server for the same three scripts. `import.meta.url` rather than
 *  `__dirname`: this module is ESM under both Playwright's loader and vitest, and `harness.ts`
 *  resolves the design bundle the same way. */
const REPO_ROOT = fileURLToPath(new URL('../..', import.meta.url));

/**
 * Every variable a remote reseed needs, in the order the refusal names them (fix round 1, ruling
 * 3, 2026-09-08 — this SUPERSEDES the brief's fixed error text).
 *
 * The first two are `scripts/seed_persona.py`'s own: `DATABASE_URL` is the target's database and
 * `PERSONA_PASSWORD` is the credential it writes into every fixture account. The other three are
 * `app.config.Settings`' remaining no-default fields — the seed imports `app.config.settings`, and
 * `load_settings()` prints `[config] missing or invalid environment variables: …` and exits 1 if
 * any of them is absent. The seed never opens Redis and never reads the secret; the settings
 * object simply will not construct without them, so a run that omits one dies inside Python with a
 * message about configuration rather than here with a message about the reseed.
 */
export const REMOTE_RESEED_REQUIRED = ['DATABASE_URL', 'PERSONA_PASSWORD', 'API_SECRET_KEY', 'ENVIRONMENT', 'REDIS_URL'] as const;

/** One line, naming the variables that are MISSING — thrown, not warned: a remote run that
 *  silently skipped the reseed would photograph whatever the LAST run left behind. */
export function remoteReseedError(missing: readonly string[]): string {
  return `a remote run must reseed the target's fixtures first; missing: ${missing.join(', ')}`;
}

/**
 * The only hosts a remote reseed may be pointed at (fix round 2, I1 — review of efef060..11ad3f1).
 *
 * An ALLOW-list, deliberately, not a deny-list of `foundation.vin`: a new production host, a
 * preview deployment or a typo is then refused by default rather than reseeded because nobody
 * thought to add it. `qa.foundation.vin` is the QA deployment; `localhost` and `127.0.0.1` are a
 * developer pointing `PW_APP_URL` at their own stack, which is a test host by construction.
 *
 * The reason this check exists at all: `reseedRemoteFixtures` spawns the seed with the INHERITED
 * environment, so the database it rewrites is whatever `DATABASE_URL` holds in the shell —
 * unrelated to the `PW_APP_URL` the tests then photograph. Before S7, running the seed was a
 * deliberate act; now it is a side effect of `playwright test`, and `ENVIRONMENT` (the seed's own
 * production refusal, `scripts/seed_persona.py`) is pulled from that same ambient shell. This
 * refuses the whole run before anything is spawned. It is a refusal, not a skip flag: the run does
 * not continue unreseeded, it does not start.
 */
export const RESEEDABLE_HOSTS = ['qa.foundation.vin', 'localhost', '127.0.0.1'] as const;

/** The target as the refusal names it: `<host>/<ENVIRONMENT>`. The raw `PW_APP_URL` is never
 *  echoed — a URL may carry credentials — so an unparseable one is reported as its shape only. */
function describeTarget(env: NodeJS.ProcessEnv): { host: string; refusable: boolean; label: string } {
  let host: string;
  try {
    host = new URL(env.PW_APP_URL ?? '').hostname;
  } catch {
    host = '(unparseable)';
  }
  const environment = env.ENVIRONMENT ?? '';
  const refusable = !(RESEEDABLE_HOSTS as readonly string[]).includes(host) || environment.toLowerCase() === 'production';
  return { host, refusable, label: `${host}/${environment || '(unset)'}` };
}

export interface RemoteReseedPlan {
  run: boolean;
  error?: string;
}

/**
 * Whether this run must reseed the target's fixtures before any test, decided from the
 * environment alone (pure, so `global-setup.test.ts` can pin it without a database).
 *
 * A LOCAL run (no `PW_APP_URL`) already reseeds: `targets.ts`'s `api` web server runs `migrate` →
 * `reset_rate_limits` → `seed_persona` and only then serves, and Playwright waits on its health
 * check (A-I7, A-S5.1). Under `PW_APP_URL` that entry is not started at all — the live deployment
 * brings its own API — so nothing reseeded, and the eight live account flows of `account-flows`,
 * `dom` and `visual` left the shared QA fixtures mutated: verify, reset and invite tokens
 * consumed, `verify-me@` confirmed, `verified@`'s password rotated, `invited@` given a password,
 * `needs-review@`'s application answered and `declined@` carrying a second one. John's ruling:
 * "every DOM/visual run begins from a known baseline and can be repeated without manual
 * intervention" · "shared QA fixtures must not be left in a mutated state after a live QA run".
 *
 * There is no skip flag. Either the run is given what it needs to restore the target, or it does
 * not start — the alternative is a green run that proves nothing, because the state it
 * photographed came from the run before it.
 *
 * An empty string counts as missing: `PERSONA_PASSWORD=` from a shell whose Keychain read failed
 * would otherwise seed every fixture account with a hash of the empty string.
 */
export function remoteReseedPlan(env: NodeJS.ProcessEnv): RemoteReseedPlan {
  if (!env.PW_APP_URL) return { run: false };
  // The TARGET is judged first (fix round 2, I1): telling an operator who has aimed a reseed at
  // production to "set DATABASE_URL" would be advice to make the accident possible.
  const target = describeTarget(env);
  if (target.refusable) {
    return { run: false, error: `remote reseed refuses this target: ${target.label} — only QA and local test hosts may be reseeded` };
  }
  const missing = REMOTE_RESEED_REQUIRED.filter((name) => !env[name]);
  if (missing.length > 0) return { run: false, error: remoteReseedError(missing) };
  return { run: true };
}

/** The plan, executed. `stdio: 'inherit'` and no `env` key, deliberately: the seed inherits this
 *  process's environment — which is where `DATABASE_URL` and `PERSONA_PASSWORD` live, never a
 *  command line another process can read — and writes straight to the terminal rather than into a
 *  string this file could log. `scripts/seed_persona.py` prints ten addresses and no secret
 *  (`tests/api/test_admin_users.py` asserts that), and nothing here prints anything at all.
 *  `execFileSync` throws on a non-zero exit, which fails the run before its first test. */
export type SeedExec = (file: string, args: readonly string[], options: { cwd: string; stdio: 'inherit' }) => void;

export function reseedRemoteFixtures(env: NodeJS.ProcessEnv, exec: SeedExec = execFileSync): boolean {
  const plan = remoteReseedPlan(env);
  if (plan.error) throw new Error(plan.error);
  if (!plan.run) return false;
  exec('poetry', ['run', 'python', 'scripts/seed_persona.py'], { cwd: REPO_ROOT, stdio: 'inherit' });
  return true;
}

export default function globalSetup(): void {
  process.env.PW_RUN_ID = process.env.PW_RUN_ID ?? randomUUID();
  const existing = existsSync(MEMO_FILE) ? readFileSync(MEMO_FILE, 'utf8') : null;
  if (isStaleMemoFile(existing, runId())) rmSync(MEMO_FILE, { force: true });
  reseedRemoteFixtures(process.env);
}
