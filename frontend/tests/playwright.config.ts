import { defineConfig, devices } from '@playwright/test';
import { resolveTargets } from './targets';

const APP = Number(process.env.PW_APP_PORT) || 5173;
const REF = Number(process.env.PW_REF_PORT) || 5174;
const VIEWPORT = { width: 1440, height: 940 }; // the design's preview size
// PW_APP_URL=https://<host> runs the `app` project against a live deployment and skips the
// local Vite server; the reference server (the design oracle) always runs locally. See
// tests/targets.ts, unit-tested in tests/targets.test.ts.
const { baseURL, webServer } = resolveTargets(process.env, { app: APP, ref: REF });

export default defineConfig({
  testDir: '.',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  reporter: [['list']],
  // Baselines are produced from the reference by the `reference` project and
  // named <state>-<platform>.png. The app must never overwrite them.
  snapshotPathTemplate: '{testDir}/visual.spec.ts-snapshots/{arg}-{platform}{ext}',
  updateSnapshots: 'none',
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000
  },
  expect: {
    timeout: 15_000,
    toHaveScreenshot: {
      // Spec §4: same Chromium, same fonts, same DOM → zero tolerance to start.
      // If relaxed, the ceiling is maxDiffPixelRatio 0.001 and the reason goes here.
      maxDiffPixels: 0,
      threshold: 0.1,
      animations: 'disabled',
      caret: 'hide',
      scale: 'css'
    }
  },
  projects: [
    // Anchored at a path boundary (start-or-slash) and the extension: an unanchored
    // (visual|smoke|dom) would also match "reference-dom.spec.ts" as a substring, which
    // belongs to the reference project only.
    { name: 'app', testMatch: /(^|\/)(visual|smoke|dom)\.spec\.ts$/, use: { ...devices['Desktop Chrome'], viewport: VIEWPORT, baseURL } },
    { name: 'reference', testMatch: /(^|\/)reference-(baselines|dom)\.spec\.ts$/, use: { ...devices['Desktop Chrome'], viewport: VIEWPORT, baseURL: `http://localhost:${REF}` } }
  ],
  webServer
});
