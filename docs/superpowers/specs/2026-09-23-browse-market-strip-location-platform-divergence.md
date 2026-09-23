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

## Investigated 2026-09-23 — the first hypothesis is REFUTED

The record's original hypothesis was that the LOCATION-mode summary adapter resolved after the
screenshot. **That is wrong**, and it was disproved by reading the diff image rather than by
reasoning:

- **The Market snapshot strip is pixel-identical.** The LOCATION header, all six cards, every
  figure and every bar show no difference at all. The adapter is innocent.
- **The whole difference is a map pan of about 188 px.** The `$2.65M` pin is present in BOTH
  images — at y≈165 in the reference and y≈353 in the app. Same pin, same price, shifted
  vertically. The results rail is identical in both ("9 PRACTICES AVAILABLE", the same two
  listings), so the listing data agrees; only the map's viewport differs, which brings different
  pins into frame.
- **It is not a timing race.** Raising the state's final settle from 400 ms to 4000 ms produced
  the identical 61962 pixels. That also rules out the 250 ms viewport debounce (A24.21-A24.23) and
  the boundary refetch behind it.
- **The trigger is the strip expansion.** `browse-market-panel` selects the SAME practice with the
  SAME waits and passes; the only difference is `click('Expand all six layers')`, which resizes the
  map container.

**What remains unknown**, and is where the next session starts: why a container resize leaves the
app's map centred ~188 px from the reference's, deterministically on darwin and not on linux. A
purely structural difference would fail on CI too, and does not — so something in that resize path
depends on a quantity that varies by platform, scrollbar width and font metrics being the obvious
candidates since both change container height.

**The next step is measurement, not a fix:** read Leaflet's actual centre and zoom from both
targets after the expansion. That turns "about 188 px" into two numbers and says whether the app
recentres on resize while the reference anchors, or whether both recentre from different container
heights.

**Deferred by John, 2026-09-23**, on the ground that no user is affected — which is correct: both
renders are the application behaving properly.

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
