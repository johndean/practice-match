/**
 * Where the Playwright projects point, extracted from playwright.config.ts so it can be
 * unit-tested (tests/targets.test.ts) — the config file itself is loaded by Playwright's
 * own runner and never by vitest.
 *
 * `PW_APP_URL=https://qa.foundation.vin` runs the `app` project against a live deployment
 * instead of a local Vite dev server, so the same parity suite that gates CI can be pointed
 * at the built image serving real traffic. The Vite web server is then not started at all.
 * The reference server always runs locally: it serves the approved design from disk and is
 * the oracle the visual baselines and DOM snapshots are generated from, so it must never
 * follow the app to a remote host. The coming-soon Vite dev server likewise always runs
 * locally — there is no live-deployment mode for it.
 *
 * The `api` entry (amendment A-I7) is the REAL backend the `app` project's parity suite signs
 * into through Vite's `/api` proxy — no stub and no mock. It migrates the database and seeds the
 * design persona before it serves, and it follows the Vite server: under `PW_APP_URL` the live
 * deployment brings its own API and this entry is not started.
 */

/** The subset of Playwright's `webServer` entry shape this config uses. */
export interface WebServerSpec {
  command: string;
  url: string;
  cwd: string;
  timeout: number;
  reuseExistingServer: boolean;
  stdout: 'ignore';
  stderr: 'pipe';
  /** Only the `api` entry sets this. Playwright already inherits `process.env` for every web
   *  server, so these are DEFAULTS the process environment overrides — see `API_ENV_DEFAULTS`. */
  env?: Record<string, string>;
}

export interface Targets {
  /** baseURL for the `app` project only — `reference` always targets the local design server. */
  baseURL: string;
  /** baseURL for the `coming-soon` project — the coming-soon Vite dev server, always local. */
  csBaseURL: string;
  webServer: WebServerSpec[];
}

/**
 * What `app.config.Settings` requires of the api web server, defaulted to the values
 * `docker-compose.dev.yml`, `.env.example` and `tests/conftest.py` already agree on, so
 * `docker compose -f docker-compose.dev.yml up -d` is the only local precondition. Each entry is
 * a DEFAULT: whatever the process environment holds for that name wins, which is how CI's own
 * `frontend` job env (its service ports and `API_SECRET_KEY`) takes over unchanged. Resolving
 * each name HERE, rather than handing Playwright `env: API_ENV_DEFAULTS`, is what makes that
 * true: Playwright merges `{ ...DEFAULT_ENVIRONMENT_VARIABLES, ...process.env, ...webServer.env }`
 * — the spec's `env` WINS over the process environment — so a literal spread would have let
 * these local defaults beat CI's job env (A-I7.2). Forwarding only these four also keeps the
 * config object from carrying every unrelated variable on the machine, at no cost: Playwright
 * passes the whole process environment through regardless.
 */
const API_ENV_DEFAULTS: Record<string, string> = {
  DATABASE_URL: 'postgresql://pm:pm_dev_pw@localhost:5433/practice_match',
  REDIS_URL: 'redis://localhost:6380/0',
  ENVIRONMENT: 'test',
  API_SECRET_KEY: 'test_only_secret_change_me',
  // A-SL28: the four settings `ObjectStore.from_settings` needs before the upload routes will
  // write, as DUMMIES for the in-process moto bucket `tests/e2e/api_under_test.py` creates — so
  // `listing-flows.spec.ts`'s photograph reaches a real upload route locally and in CI instead of
  // `503 STORAGE_UNAVAILABLE`. An AWS-shaped endpoint, because moto intercepts by request URL and a
  // Railway-shaped host would escape to the network (A-SL16 M4; the launcher refuses any other);
  // a bucket and credentials that exist nowhere. Same rule as the four above: a run that carries
  // real values keeps them, and a live target (`PW_APP_URL`) never starts this entry at all.
  S3_ENDPOINT_URL: 'https://s3.amazonaws.com',
  S3_BUCKET: 'pm-e2e',
  S3_ACCESS_KEY_ID: 'test-only-key-id',
  S3_SECRET_ACCESS_KEY: 'test-only-secret'
};

export function resolveTargets(env: NodeJS.ProcessEnv, ports: { app: number; ref: number; cs: number; api: number }): Targets {
  const live = env.PW_APP_URL;
  const reuseExistingServer = !env.CI;
  const vite: WebServerSpec = {
    command: `npm run dev -- --port ${ports.app} --strictPort`,
    url: `http://localhost:${ports.app}`,
    cwd: '..',
    timeout: 60_000,
    reuseExistingServer,
    stdout: 'ignore',
    stderr: 'pipe'
  };
  const reference: WebServerSpec = {
    command: `node tests/reference-server.mjs ${ports.ref}`,
    url: `http://localhost:${ports.ref}/`,
    cwd: '..',
    timeout: 30_000,
    reuseExistingServer,
    stdout: 'ignore',
    stderr: 'pipe'
  };
  const apiEnv: Record<string, string> = {};
  for (const [name, value] of Object.entries(API_ENV_DEFAULTS)) apiEnv[name] = env[name] ?? value;
  // `cwd` is the repository root (Playwright resolves it against this config's directory), which
  // is where `poetry` and `app.main` resolve. Migrate, clear the local rate-limit counters, seed
  // the persona, then serve: the health check below is what Playwright waits on, so the suite
  // never races any of the three.
  //
  // A-S5.1 (John's ruling, 2026-09-08): `reset_rate_limits.py` is what makes consecutive LOCAL
  // runs independent. The limits themselves are untouched — `SIGNIN_IP` is still 30 per fixed
  // 15-minute window and `FORGOT_IP` still 10 per hour, and `tests/api/test_auth.py` still proves
  // each refusal — but a suite that spends fifteen sign-ins, three forgot calls and one sign-up
  // per run (the arithmetic is in `harness.ts`'s `personaSessionMemos` docstring) would otherwise
  // have met `FORGOT_IP` on its third run of the hour, in the middle of a screenshot. The script
  // refuses unless `ENVIRONMENT` is exactly `test` AND Redis is on loopback, so this line cannot
  // reach QA or production; in CI it runs and deletes nothing.
  //
  // A-SL28: the server itself is `tests/e2e/api_under_test.py` — a TEST-ONLY launcher that starts
  // moto's S3 mock in the api's own process, creates the bucket named by `S3_BUCKET` and then runs
  // uvicorn exactly as the bare `uvicorn app.main:app --port N` did — so the photograph half of
  // `listing-flows.spec.ts` reaches a real upload route here and in CI. It refuses to start
  // anywhere but `ENVIRONMENT=test` (`tests/e2e/test_api_under_test.py` pins that, and the other
  // two refusals), for the same reason `reset_rate_limits.py` does.
  //
  // SL7b (A-SL25 (10)): `seed_listings.py` joins the chain, the same reason `seed_persona.py` is
  // here — the click-to-caption flow spec re-describes one of the eighteen SEEDED photographs, and
  // that data must exist before any test runs rather than be a test's own side effect. It defaults
  // to owning every hospital by `seller@practice-match.test` (`SEED_OWNER_EMAIL`), the very persona
  // `seed_persona.py` just created, and is idempotent (`ON CONFLICT (slug) DO UPDATE ... WHERE
  // listing.source = 'seed'`), so a second run of this chain changes nothing a seller has since
  // edited. `prepare()` stubs `/api/listings` for every pixel and smoke spec (`harness.ts`), so
  // eighteen real rows in the database change no approved capture's pixels.
  const api: WebServerSpec = {
    command: `poetry run python scripts/migrate.py && poetry run python scripts/reset_rate_limits.py && poetry run python scripts/seed_persona.py && poetry run python scripts/seed_listings.py && poetry run python -m tests.e2e.api_under_test --port ${ports.api}`,
    url: `http://localhost:${ports.api}/api/healthz`,
    cwd: '../..',
    timeout: 90_000,
    reuseExistingServer,
    stdout: 'ignore',
    stderr: 'pipe',
    env: apiEnv
  };
  const comingSoon: WebServerSpec = {
    command: `npm run dev -- --port ${ports.cs} --strictPort`,
    url: `http://localhost:${ports.cs}`,
    cwd: '../../coming-soon',
    timeout: 60_000,
    reuseExistingServer,
    stdout: 'ignore',
    stderr: 'pipe'
  };
  return {
    baseURL: live ?? `http://localhost:${ports.app}`,
    csBaseURL: `http://localhost:${ports.cs}`,
    webServer: live ? [reference, comingSoon] : [vite, api, reference, comingSoon]
  };
}
