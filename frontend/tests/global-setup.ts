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
 */
import { randomUUID } from 'node:crypto';
import { existsSync, readFileSync, rmSync } from 'node:fs';
import { MEMO_FILE, isStaleMemoFile, runId } from './harness';

export default function globalSetup(): void {
  process.env.PW_RUN_ID = process.env.PW_RUN_ID ?? randomUUID();
  const existing = existsSync(MEMO_FILE) ? readFileSync(MEMO_FILE, 'utf8') : null;
  if (isStaleMemoFile(existing, runId())) rmSync(MEMO_FILE, { force: true });
}
