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
 * follow the app to a remote host.
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
}

export interface Targets {
  /** baseURL for the `app` project only — `reference` always targets the local design server. */
  baseURL: string;
  webServer: WebServerSpec[];
}

export function resolveTargets(env: NodeJS.ProcessEnv, ports: { app: number; ref: number }): Targets {
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
  return {
    baseURL: live ?? `http://localhost:${ports.app}`,
    webServer: live ? [reference] : [vite, reference]
  };
}
