# Defect — `browse-market-strip-location` diverges on macOS and not on Linux

**Found 2026-09-23**, during the full verification gate for the D-C64 docs merge (`fbd8b1b`).
Recorded rather than fixed, on John's instruction to proceed with the deploy and take this next.

## What happens

`npm run test:e2e` (the `app` project) fails one approved state on macOS:

```
[app] tests/visual.spec.ts:88 visual parity with the approved design browse-market-strip-location
61962 pixels (ratio 0.05 of all image pixels) are different.
```

`npm run test:visual:baselines` passes all 120 reference captures in the same run. Every other
app-target state passes: **219 passed, 1 failed.**

## What is established

- **Deterministic.** Two isolated re-runs both report exactly `61962 pixels`. Not antialiasing
  noise, not a timing flake in the usual sense — the same pixels differ every time.
- **Not caused by the commit under test.** `git diff 66075c6..HEAD` is one markdown file, 97
  insertions. `frontend/src`, the design bundle, `tests/` and every fixture are byte-identical, so
  the previous main executes the same code against the same inputs.
- **Platform-specific.** CI's `frontend (typecheck · unit · build · smoke · visual parity)` job is
  `success` on this exact SHA, running Linux Chromium. The divergence appears only on darwin.
- **Not a stale committed baseline.** The expected snapshots are untracked — `git log` returns
  nothing for `browse-market-strip-location-darwin.png` — because both sides are generated in the
  same run, the reference project writing what the app project is compared against.

## The leading hypothesis, untested

This is the one approved state that captures the Market snapshot strip in **LOCATION** mode, whose
figures reach the app through the `market` adapter rather than through a `?props=` payload. If the
adapter's summary resolves after the screenshot on darwin and before it on linux, the app would
capture the AREA-mode bars against a reference drawn in LOCATION mode — a plausible 5 % of the
image, and consistent with the difference being stable rather than random.

**This is a hypothesis and has not been tested.** The next step is to read the diff PNG at
`test-results/visual-visual-parity-with--9a02d-rowse-market-strip-location-app/` and establish
which region differs before touching anything — the failure may equally be a font fallback or a
canvas rendering difference, and guessing would waste the measurement.

## Why it matters beyond one red test

The oracle is the arbiter of design fidelity at `maxDiffPixels: 0`. A state that passes on one
platform and fails on another means the gate's verdict depends on who runs it, which weakens every
future "no pixel moved" claim made from a developer machine. Either the app has a real race that
Linux timing hides, or the oracle needs a wait the app target does not currently perform.

## Not in scope of this record

The shared dev database carries `092_esri_basemap_registry.sql` under a different checksum than
main's file, so `scripts/migrate.py` refuses and every local backend run fails until the database
is recreated. That is a separate operational item and needs John's word, a reset being destructive
and the database shared across worktrees.
