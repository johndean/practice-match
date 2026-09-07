import { defineConfig, devices } from '@playwright/test';
import { resolveTargets } from './targets';

const APP = Number(process.env.PW_APP_PORT) || 5173;
const REF = Number(process.env.PW_REF_PORT) || 5174;
const CS = Number(process.env.PW_CS_PORT) || 5175;
// 8017, not 8000: this machine runs several projects and one of them may already hold 8000, which
// `reuseExistingServer` would then silently adopt as "the API" (amendment A-I7).
const API = Number(process.env.PW_API_PORT) || 8017;
const VIEWPORT = { width: 1440, height: 940 }; // the design's preview size
const CS_VIEWPORT = { width: 1440, height: 900 }; // the Coming Soon design's $preview
// PW_APP_URL=https://<host> runs the `app` project against a live deployment and skips the
// local Vite server; the reference server (the design oracle) always runs locally. See
// tests/targets.ts, unit-tested in tests/targets.test.ts.
const { baseURL, csBaseURL, webServer } = resolveTargets(process.env, { app: APP, ref: REF, cs: CS, api: API });

export default defineConfig({
  testDir: '.',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  reporter: [['list']],
  // Mints one PW_RUN_ID per run, which every worker inherits, and clears a memo file another run
  // left behind — see tests/global-setup.ts for why the environment is the only channel that can
  // carry it (round 3, ruling 2).
  globalSetup: './global-setup.ts',
  // Baselines are produced from the reference by the `reference` project and
  // named <state>-<platform>.png. The app must never overwrite them.
  snapshotPathTemplate: '{testDir}/visual.spec.ts-snapshots/{arg}-{platform}{ext}',
  updateSnapshots: 'none',
  use: {
    // Task V17. Chromium's partial raster re-rasters only the invalidated part of a tile and
    // reuses the rest, so a pixel whose antialiasing sits exactly on the fence can come out
    // either way depending on which tiles were invalidated. `fullPage: true` — every approved
    // state uses it — takes Chromium's `captureBeyondViewport` path whenever the document is
    // taller than the viewport, and the design's root is `min-height: 100vh` with more content
    // than that, so it always is; that pass invalidates tiles after the page has settled and
    // the capture races the partial re-raster. The result was twelve pixels of the Browse
    // results rail's rounded card corners flipping between two grey levels in ~13 % of runs
    // (V16 caught it on `header-1000`; `header-1100` and `browse` flip identically) — and
    // because `reference-baselines.spec.ts` writes the oracle with a single raw screenshot,
    // that coin toss went straight into the baseline. Turning partial raster off pins the
    // raster: every tile is drawn whole, so the same DOM always produces the same bytes.
    // Set at the top level so the `reference` and `app` projects rasterise identically —
    // splitting it would make the oracle and the app disagree by those same pixels. Nothing
    // here is a tolerance: `maxDiffPixels: 0` below is unchanged (Global Constraint (e)).
    // Guarded by tests/capture-determinism.spec.ts.
    launchOptions: { args: ['--disable-partial-raster'] },
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
    //
    // `signin-form` is its own file rather than a describe inside smoke.spec.ts because Playwright
    // refuses `use({ trace })` in a describe group ("because it forces a new worker") and allows it
    // at the top level of a file: those three tests type a password into the design's own card, and
    // their trace is turned off on a live run alone (round 3, ruling 1).
    { name: 'app', testMatch: /(^|\/)(visual|smoke|dom|signin-form)\.spec\.ts$/, use: { ...devices['Desktop Chrome'], viewport: VIEWPORT, baseURL } },
    { name: 'reference', testMatch: /(^|\/)(reference-(baselines|dom)|capture-determinism)\.spec\.ts$/, use: { ...devices['Desktop Chrome'], viewport: VIEWPORT, baseURL: `http://localhost:${REF}` } },
    { name: 'coming-soon-reference', testMatch: /(^|\/)coming-soon-reference\.spec\.ts$/, use: { ...devices['Desktop Chrome'], viewport: CS_VIEWPORT, baseURL: `http://localhost:${REF}` } },
    { name: 'coming-soon', testMatch: /(^|\/)coming-soon-visual\.spec\.ts$/, use: { ...devices['Desktop Chrome'], viewport: CS_VIEWPORT, baseURL: csBaseURL } }
  ],
  webServer
});
