import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { REMOTE_RESEED_ERROR, remoteReseedPlan, reseedRemoteFixtures } from './global-setup';

// ---------------------------------------------------------------------------------------
// Task S7 (John's ruling, 2026-09-08): "Before Task I10, add a deterministic test-fixture
// reset/reseed mechanism so every DOM/visual run begins from a known baseline and can be
// repeated without manual intervention" and "shared QA fixtures must not be left in a mutated
// state after a live QA run".
//
// A LOCAL run already reseeds: `targets.ts`'s `api` web server runs `migrate` →
// `reset_rate_limits` → `seed_persona` before it serves (A-I7, A-S5.1). Under `PW_APP_URL` that
// entry is not started at all — the live deployment brings its own API — so a remote run had no
// reseed anywhere, and the eight live account flows left QA's fixtures mutated: a consumed verify
// token, a rotated `verified@` password, an answered application. `remoteReseedPlan` decides,
// from the environment alone, whether this run must reseed before any test — the same place the
// local reseed implicitly happens.
//
// Pure, so the decision is testable without a database, a deployment or a subprocess.
// ---------------------------------------------------------------------------------------
describe('remoteReseedPlan (S7)', () => {
  it('does not reseed a local run — the api web server already did', () => {
    expect(remoteReseedPlan({})).toStrictEqual({ run: false });
  });

  it('reseeds a remote run that was given the target database and the persona password', () => {
    expect(remoteReseedPlan({
      PW_APP_URL: 'https://qa.foundation.vin',
      DATABASE_URL: 'postgresql://user:pw@host:5432/railway',
      PERSONA_PASSWORD: 'not-the-default'
    })).toStrictEqual({ run: true });
  });

  it('refuses a remote run with no target database', () => {
    expect(remoteReseedPlan({ PW_APP_URL: 'https://qa.foundation.vin', PERSONA_PASSWORD: 'not-the-default' }))
      .toStrictEqual({ run: false, error: REMOTE_RESEED_ERROR });
  });

  it('refuses a remote run with no persona password', () => {
    expect(remoteReseedPlan({ PW_APP_URL: 'https://qa.foundation.vin', DATABASE_URL: 'postgresql://user:pw@host:5432/railway' }))
      .toStrictEqual({ run: false, error: REMOTE_RESEED_ERROR });
  });

  it('names both variables, and the reason, in one line', () => {
    expect(REMOTE_RESEED_ERROR).toBe(
      "a remote run must reseed the target's fixtures first; set DATABASE_URL (the target's database) and PERSONA_PASSWORD"
    );
  });

  // An empty string is not a database and not a password: `PERSONA_PASSWORD=` in a shell that
  // failed to read the value from Railway would otherwise seed every fixture account with a
  // hash of "" and hand the run a sign-in it cannot make.
  it('treats an empty value as missing', () => {
    expect(remoteReseedPlan({ PW_APP_URL: 'https://qa.foundation.vin', DATABASE_URL: '', PERSONA_PASSWORD: 'x' }))
      .toStrictEqual({ run: false, error: REMOTE_RESEED_ERROR });
    expect(remoteReseedPlan({ PW_APP_URL: 'https://qa.foundation.vin', DATABASE_URL: 'postgresql://x/y', PERSONA_PASSWORD: '' }))
      .toStrictEqual({ run: false, error: REMOTE_RESEED_ERROR });
  });
});

describe('reseedRemoteFixtures (S7)', () => {
  const calls: { file: string; args: readonly string[]; options: { cwd: string; stdio: 'inherit' } }[] = [];
  const exec = (file: string, args: readonly string[], options: { cwd: string; stdio: 'inherit' }): void => {
    calls.push({ file, args, options });
  };

  it('runs nothing on a local run', () => {
    calls.length = 0;
    expect(reseedRemoteFixtures({}, exec)).toBe(false);
    expect(calls).toEqual([]);
  });

  it('runs the seed from the repository root, with the inherited environment and no captured output', () => {
    calls.length = 0;
    const ran = reseedRemoteFixtures({
      PW_APP_URL: 'https://qa.foundation.vin',
      DATABASE_URL: 'postgresql://user:pw@host:5432/railway',
      PERSONA_PASSWORD: 'not-the-default'
    }, exec);
    expect(ran).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0].file).toBe('poetry');
    expect(calls[0].args).toEqual(['run', 'python', 'scripts/seed_persona.py']);
    // `stdio: 'inherit'` and no `env` key: the seed inherits this process's environment (which is
    // where DATABASE_URL and PERSONA_PASSWORD are) and writes straight to the terminal. Neither
    // value is passed on a command line, logged, or captured into a string this file could print
    // — and the seed itself prints no secret (tests/api/test_admin_users.py proves that).
    expect(calls[0].options).toEqual({ cwd: expect.any(String), stdio: 'inherit' });
    // The repository root, proved by what is in it — `poetry` and `app.main` resolve there, and
    // `scripts/seed_persona.py` is the path this command hands them, relative to it.
    expect(existsSync(join(calls[0].options.cwd, 'scripts', 'seed_persona.py')), calls[0].options.cwd).toBe(true);
  });

  it('throws the plan\'s own line rather than running a run that would mutate the target unreproducibly', () => {
    calls.length = 0;
    // The literal, not the constant: `toThrow(undefined)` matches ANY throw, so a test written
    // against the constant alone would have passed before the constant existed.
    expect(() => reseedRemoteFixtures({ PW_APP_URL: 'https://qa.foundation.vin' }, exec))
      .toThrow("a remote run must reseed the target's fixtures first; set DATABASE_URL (the target's database) and PERSONA_PASSWORD");
    expect(calls, 'nothing is executed when the plan refuses').toEqual([]);
  });
});
