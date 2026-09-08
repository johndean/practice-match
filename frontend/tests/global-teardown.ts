/**
 * Runs ONCE in the Playwright runner process, after the last worker has finished.
 *
 * It exists for the "after" half of John's ruling of 2026-09-08 (Task S7, fix round 1): "every
 * DOM/visual run begins from a known baseline and can be repeated without manual intervention"
 * AND "shared QA fixtures must not be left in a mutated state after a live QA run". `global-setup`
 * meets the first — reseeding before a remote run makes each run deterministic whatever the last
 * one did — but it cannot meet the second, because between the end of a live run and whoever opens
 * QA next, the fixtures are however the eight account flows left them: a verify token consumed,
 * `verified@`'s password rotated, `invited@` given one, an application answered.
 *
 * So a remote run reseeds at BOTH ends, through the same planner and the same script. There is no
 * second copy of the decision here: `reseedRemoteFixtures` is `global-setup.ts`'s, so a change to
 * what a reseed requires or how it is run reaches this end too, by construction.
 *
 * Nothing changes for a LOCAL run. `remoteReseedPlan` returns `{ run: false }` without
 * `PW_APP_URL`, and a local run's fixtures are reseeded by the `api` web server on its next start
 * (`targets.ts`) — which is also why reseeding locally at the end would be pure duplicated work.
 *
 * A failure is REPORTED, never swallowed: `execFileSync` throws on a non-zero exit and nothing
 * here catches it, so Playwright fails the run. A teardown that gave up quietly would leave QA
 * mutated and say nothing, which is the exact state the ruling is about.
 */
import { type SeedExec, reseedRemoteFixtures } from './global-setup';

/** Extracted from the default export only so `global-teardown.test.ts` can pin the behaviour
 *  without a real subprocess — Playwright calls the default export with its own `FullConfig`. */
export function teardownReseed(env: NodeJS.ProcessEnv, exec?: SeedExec): boolean {
  return reseedRemoteFixtures(env, exec);
}

export default function globalTeardown(): void {
  teardownReseed(process.env);
}
