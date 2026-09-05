import { defineConfig, devices } from '@playwright/test';

const APP = Number(process.env.PW_APP_PORT) || 5173;
const REF = Number(process.env.PW_REF_PORT) || 5174;
const VIEWPORT = { width: 1440, height: 940 }; // the design's preview size

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
    { name: 'app', testMatch: /(visual|smoke)\.spec\.ts/, use: { ...devices['Desktop Chrome'], viewport: VIEWPORT, baseURL: `http://localhost:${APP}` } },
    { name: 'reference', testMatch: /reference-baselines\.spec\.ts/, use: { ...devices['Desktop Chrome'], viewport: VIEWPORT, baseURL: `http://localhost:${REF}` } }
  ],
  webServer: [
    { command: `npm run dev -- --port ${APP} --strictPort`, url: `http://localhost:${APP}`, cwd: '..', timeout: 60_000, reuseExistingServer: !process.env.CI, stdout: 'ignore', stderr: 'pipe' },
    { command: `node tests/reference-server.mjs ${REF}`, url: `http://localhost:${REF}/`, cwd: '..', timeout: 30_000, reuseExistingServer: !process.env.CI, stdout: 'ignore', stderr: 'pipe' }
  ]
});
