import { describe, expect, it } from 'vitest';
import { resolveTargets } from './targets';

describe('resolveTargets', () => {
  const ports = { app: 5173, ref: 4174, cs: 4175, api: 8017 };
  it('runs against localhost with all four servers when PW_APP_URL is unset', () => {
    const t = resolveTargets({}, ports);
    expect(t.baseURL).toBe('http://localhost:5173');
    expect(t.csBaseURL).toBe('http://localhost:4175');
    expect(t.webServer.map((w) => w.url)).toEqual([
      'http://localhost:5173',
      'http://localhost:8017/api/healthz',
      'http://localhost:4174/',
      'http://localhost:4175'
    ]);
    expect(t.webServer[3].cwd).toBe('../../coming-soon');
  });
  it('runs the app against the live deployment but keeps the reference and coming-soon servers local when PW_APP_URL is set', () => {
    const t = resolveTargets({ PW_APP_URL: 'https://qa.foundation.vin' }, ports);
    expect(t.baseURL).toBe('https://qa.foundation.vin');
    expect(t.csBaseURL).toBe('http://localhost:4175');
    expect(t.webServer.map((w) => w.url)).toEqual(['http://localhost:4174/', 'http://localhost:4175']);
  });

  // ---------------------------------------------------------------------------------------
  // Amendment A-I7: the `app` project's parity suite reaches a REAL API through Vite's `/api`
  // proxy — no stubs and no mocks. The api web server migrates, seeds the design persona and
  // only then serves, and it runs from the repository ROOT (`../..` from tests/), which is
  // where `poetry` and `app.main` resolve. Under PW_APP_URL the app is a live deployment that
  // brings its own API, so this entry is not started at all — exactly like the Vite server.
  // ---------------------------------------------------------------------------------------
  describe('the api web server (A-I7)', () => {
    const api = (env: NodeJS.ProcessEnv = {}) =>
      resolveTargets(env, ports).webServer.find((w) => w.url.endsWith('/api/healthz'));

    // A-S5.1 (John's ruling, 2026-09-08): `reset_rate_limits.py` joins the chain, between the
    // migration and the seed. The limits themselves do not move — they are security controls and
    // `tests/api/test_auth.py` still proves each refusal — but the LOCAL environment's counters
    // are cleared before the API serves, so consecutive suite runs are independent instead of the
    // third one meeting `FORGOT_IP` in the middle of a screenshot. The script refuses anywhere but
    // `ENVIRONMENT=test` against a loopback Redis, so this line can never reach QA or production;
    // in CI it runs and deletes nothing (a fresh Redis service per job).
    // A-SL28 (round-4 NEEDS_CONTEXT): the server itself is `tests/e2e/api_under_test.py`, a
    // TEST-ONLY launcher that starts moto's in-process S3 mock, creates the bucket and then runs
    // uvicorn exactly as the bare command did — so `listing-flows.spec.ts`'s photograph reaches a
    // real upload route locally and in CI instead of `503 STORAGE_UNAVAILABLE`. It refuses to
    // start anywhere but `ENVIRONMENT=test` (`tests/e2e/test_api_under_test.py` pins that).
    it('resets the local rate limits and seeds the persona before it serves, from the repository root', () => {
      const w = api()!;
      expect(w.command).toBe(
        'poetry run python scripts/migrate.py && poetry run python scripts/reset_rate_limits.py && poetry run python scripts/seed_persona.py && poetry run python -m tests.e2e.api_under_test --port 8017'
      );
      expect(w.cwd).toBe('../..');
      expect(w.url).toBe('http://localhost:8017/api/healthz');
      expect(w.timeout).toBe(90_000);
      expect(w.reuseExistingServer).toBe(true);
    });

    it('is not started when the app runs against a live deployment', () => {
      expect(api({ PW_APP_URL: 'https://qa.foundation.vin' })).toBeUndefined();
    });

    // The four `S3_*` defaults are DUMMIES for the in-process moto bucket (A-SL28): an AWS-shaped
    // endpoint, because moto intercepts by request URL and a Railway-shaped host would escape to
    // the network (A-SL16 M4), and a bucket name and credentials that exist nowhere. The same
    // "process env wins" rule as the first four, so a run that carries real settings is unchanged.
    it('carries the docker-compose.dev.yml defaults tests/conftest.py already uses, and the moto bucket\'s', () => {
      expect(api()!.env).toEqual({
        DATABASE_URL: 'postgresql://pm:pm_dev_pw@localhost:5433/practice_match',
        REDIS_URL: 'redis://localhost:6380/0',
        ENVIRONMENT: 'test',
        API_SECRET_KEY: 'test_only_secret_change_me',
        S3_ENDPOINT_URL: 'https://s3.amazonaws.com',
        S3_BUCKET: 'pm-e2e',
        S3_ACCESS_KEY_ID: 'test-only-key-id',
        S3_SECRET_ACCESS_KEY: 'test-only-secret'
      });
    });

    it('lets the process environment override each default, so CI\'s job env wins', () => {
      expect(
        api({ DATABASE_URL: 'postgresql://pm:pm_dev_pw@localhost:5433/ci', API_SECRET_KEY: 'ci_only_secret_change_me', S3_BUCKET: 'ci-bucket' })!.env
      ).toEqual({
        DATABASE_URL: 'postgresql://pm:pm_dev_pw@localhost:5433/ci',
        REDIS_URL: 'redis://localhost:6380/0',
        ENVIRONMENT: 'test',
        API_SECRET_KEY: 'ci_only_secret_change_me',
        S3_ENDPOINT_URL: 'https://s3.amazonaws.com',
        S3_BUCKET: 'ci-bucket',
        S3_ACCESS_KEY_ID: 'test-only-key-id',
        S3_SECRET_ACCESS_KEY: 'test-only-secret'
      });
    });
  });
});
