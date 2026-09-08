import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { RESEEDABLE_HOSTS, REMOTE_RESEED_REQUIRED, remoteReseedError, remoteReseedPlan, reseedRemoteFixtures } from './global-setup';

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
  // Fix round 1, ruling 3 (2026-09-08). The brief's fixed error text is SUPERSEDED: the planner
  // requires every variable the seed truly needs, and the line names the missing ones.
  //
  // `scripts/seed_persona.py` needs two of its own — `DATABASE_URL` (the target's database) and
  // `PERSONA_PASSWORD` (the credential it writes) — and it imports `app.config.settings`, whose
  // `Settings` declares `database_url`, `redis_url`, `environment` and `api_secret_key` with NO
  // default: `load_settings()` prints `[config] missing or invalid environment variables: …` and
  // `SystemExit(1)`s if any is absent. The seed never opens Redis and never reads the secret — the
  // settings object simply refuses to construct without them — so they are required here for the
  // same reason: without them the reseed dies inside Python instead of on this line.
  const REMOTE = {
    PW_APP_URL: 'https://qa.foundation.vin',
    DATABASE_URL: 'postgresql://user:pw@host:5432/railway',
    PERSONA_PASSWORD: 'not-the-default',
    API_SECRET_KEY: 'not-the-default-either',
    ENVIRONMENT: 'qa',
    REDIS_URL: 'redis://user:pw@host:6379/0'
  };
  const without = (...names: string[]): NodeJS.ProcessEnv =>
    Object.fromEntries(Object.entries(REMOTE).filter(([k]) => !names.includes(k)));

  it('does not reseed a local run — the api web server already did', () => {
    expect(remoteReseedPlan({})).toStrictEqual({ run: false });
  });

  it('requires the seed\'s own two variables and the three app.config.Settings has no default for', () => {
    expect(REMOTE_RESEED_REQUIRED)
      .toEqual(['DATABASE_URL', 'PERSONA_PASSWORD', 'API_SECRET_KEY', 'ENVIRONMENT', 'REDIS_URL']);
  });

  it('reseeds a remote run that was given every one of them', () => {
    expect(remoteReseedPlan(REMOTE)).toStrictEqual({ run: true });
  });

  it('names the MISSING variables, in the declared order, and only those', () => {
    expect(remoteReseedPlan(without('API_SECRET_KEY', 'REDIS_URL'))).toStrictEqual({
      run: false,
      error: "a remote run must reseed the target's fixtures first; missing: API_SECRET_KEY, REDIS_URL"
    });
    expect(remoteReseedPlan(without('PERSONA_PASSWORD')).error)
      .toBe("a remote run must reseed the target's fixtures first; missing: PERSONA_PASSWORD");
    expect(remoteReseedPlan({ PW_APP_URL: REMOTE.PW_APP_URL }).error).toBe(
      "a remote run must reseed the target's fixtures first; " +
      'missing: DATABASE_URL, PERSONA_PASSWORD, API_SECRET_KEY, ENVIRONMENT, REDIS_URL'
    );
  });

  // ---------------------------------------------------------------------------------------
  // Fix round 2, I1 (review of efef060..11ad3f1). The seed is spawned with the INHERITED
  // environment, so the database it rewrites is whatever `DATABASE_URL` happens to be in the
  // shell — unrelated to the `PW_APP_URL` the tests photograph. Before S7, running the seed was a
  // deliberate act; now it is a side effect of `playwright test`, and the only thing between it
  // and the stakeholders' data was `ENVIRONMENT`, pulled from the same ambient shell.
  //
  // So the planner refuses the target itself, before anything is spawned. An ALLOW-list, not a
  // deny-list: a new production host, a preview deployment or a typo is refused by default rather
  // than reseeded because nobody thought to add it.
  // ---------------------------------------------------------------------------------------
  describe('the target allow-list (fix round 2, I1)', () => {
    const refusal = (target: string) =>
      `remote reseed refuses this target: ${target} — only QA and local test hosts may be reseeded`;

    it('allows QA and local test hosts, and nothing else', () => {
      expect(RESEEDABLE_HOSTS).toEqual(['qa.foundation.vin', 'localhost', '127.0.0.1']);
    });

    it('refuses production by host, whatever ENVIRONMENT says', () => {
      expect(remoteReseedPlan({ ...REMOTE, PW_APP_URL: 'https://foundation.vin' }))
        .toStrictEqual({ run: false, error: refusal('foundation.vin/qa') });
    });

    it('refuses ENVIRONMENT=production even on the QA host', () => {
      expect(remoteReseedPlan({ ...REMOTE, ENVIRONMENT: 'Production' }))
        .toStrictEqual({ run: false, error: refusal('qa.foundation.vin/Production') });
    });

    it('refuses a host nobody allow-listed', () => {
      for (const url of ['https://example.com', 'https://qa.foundation.vin.evil.test', 'https://preview-7.up.railway.app'])
        expect(remoteReseedPlan({ ...REMOTE, PW_APP_URL: url }).error, url).toMatch(/^remote reseed refuses this target: /);
    });

    it('refuses a PW_APP_URL it cannot parse, without echoing it', () => {
      const plan = remoteReseedPlan({ ...REMOTE, PW_APP_URL: 'not a url' });
      expect(plan).toStrictEqual({ run: false, error: refusal('(unparseable)/qa') });
      expect(plan.error).not.toContain('not a url');
    });

    it('names ENVIRONMENT as (unset) rather than pretending it was given', () => {
      const { ENVIRONMENT: _drop, ...noEnvironment } = { ...REMOTE, PW_APP_URL: 'https://foundation.vin' };
      expect(remoteReseedPlan(noEnvironment).error).toBe(refusal('foundation.vin/(unset)'));
    });

    it('reseeds a local test host', () => {
      for (const url of ['http://localhost:5173', 'http://127.0.0.1:8017'])
        expect(remoteReseedPlan({ ...REMOTE, PW_APP_URL: url, ENVIRONMENT: 'test' }), url).toStrictEqual({ run: true });
    });

    // The target is judged BEFORE the variables: telling an operator who has aimed at production
    // to "set DATABASE_URL" would be advice to make the accident possible.
    it('refuses the target before it asks for the missing variables', () => {
      expect(remoteReseedPlan({ PW_APP_URL: 'https://foundation.vin' }).error)
        .toBe(refusal('foundation.vin/(unset)'));
    });
  });

  it('builds that line from the same helper the plan uses', () => {
    expect(remoteReseedError(['REDIS_URL']))
      .toBe("a remote run must reseed the target's fixtures first; missing: REDIS_URL");
  });

  // An empty string is not a database, a password, a secret or a URL: `PERSONA_PASSWORD=` in a
  // shell whose Railway lookup failed would otherwise seed every fixture account with a hash of
  // the empty string.
  it('treats an empty value as missing', () => {
    for (const name of REMOTE_RESEED_REQUIRED) {
      expect(remoteReseedPlan({ ...REMOTE, [name]: '' }), name)
        .toStrictEqual({ run: false, error: `a remote run must reseed the target's fixtures first; missing: ${name}` });
    }
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
      PERSONA_PASSWORD: 'not-the-default',
      API_SECRET_KEY: 'not-the-default-either',
      ENVIRONMENT: 'qa',
      REDIS_URL: 'redis://user:pw@host:6379/0'
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
    // The literal, not a constant: `toThrow(undefined)` matches ANY throw, so a test written
    // against a constant that does not exist yet passes for the wrong reason.
    expect(() => reseedRemoteFixtures({ PW_APP_URL: 'https://qa.foundation.vin', DATABASE_URL: 'x' }, exec))
      .toThrow("a remote run must reseed the target's fixtures first; missing: PERSONA_PASSWORD, API_SECRET_KEY, ENVIRONMENT, REDIS_URL");
    expect(calls, 'nothing is executed when the plan refuses').toEqual([]);
  });
});

// ---------------------------------------------------------------------------------------
// Fix round 2, I2 (review of efef060..11ad3f1). The one line that makes the whole feature happen
// lives in a default export nothing imports: delete it and every vitest, the config pin and the
// entire Playwright suite stay green while remote runs silently stop reseeding — the exact
// regression S7 exists to prevent. Pinned as source text, the same idiom
// `playwright-config.test.ts` uses on the config's own keys, with comment lines stripped so a
// commented-out call cannot satisfy it.
// ---------------------------------------------------------------------------------------
/** The default export's body, comment lines stripped so a commented-out call cannot satisfy a
 *  pin — the same source-text idiom `playwright-config.test.ts` uses on the config's own keys. */
function defaultExportOf(file: string): string {
  const source = readFileSync(fileURLToPath(new URL(`./${file}`, import.meta.url)), 'utf8')
    .replace(/^\s*(\/\/|\*|\/\*).*$/gm, '');
  const at = source.indexOf('export default function');
  expect(at, `${file} has a default export`).toBeGreaterThan(-1);
  return source.slice(at);
}

describe('the hooks Playwright actually calls (fix round 2, I2)', () => {
  it('globalSetup reseeds — and still mints the run id and clears a foreign memo file', () => {
    const body = defaultExportOf('global-setup.ts');
    expect(body).toContain('reseedRemoteFixtures(process.env);');
    expect(body, 'the two lines S7 inherited must not have been displaced by the third')
      .toContain('process.env.PW_RUN_ID = process.env.PW_RUN_ID ?? randomUUID();');
    expect(body).toContain('rmSync(MEMO_FILE, { force: true })');
  });
});
