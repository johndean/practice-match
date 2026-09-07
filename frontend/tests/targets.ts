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
  API_SECRET_KEY: 'test_only_secret_change_me'
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
  // is where `poetry` and `app.main` resolve. Migrate, then seed the persona, then serve: the
  // health check below is what Playwright waits on, so the suite never races the seed.
  const api: WebServerSpec = {
    command: `poetry run python scripts/migrate.py && poetry run python scripts/seed_persona.py && poetry run uvicorn app.main:app --port ${ports.api}`,
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
