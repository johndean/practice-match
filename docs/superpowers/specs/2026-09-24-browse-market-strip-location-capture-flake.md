# `browse-market-strip-location` is not a byte-deterministic capture

**Recorded 2026-09-24, during Task 2 of the seller wizard repair (A58.2/A58.3).** This is a finding,
not a fix. Nothing here was changed; the flake is live.

**Supersedes, on the cause,
`docs/superpowers/specs/2026-09-23-browse-market-strip-location-platform-divergence.md`.** That
record's retraction stands — there was never a platform divergence — but its "lesson worth keeping"
attributes the difference it saw to baselines straddling a `pm_gate` database change, and the
measurement below disputes that: the same state produces two different PNGs from the SAME code, on
ONE machine, with NO database change between the captures. The database rule it states is sound in
general and is not withdrawn; it is no longer the established explanation of what happened there.

## The claim

The approved state `browse-market-strip-location` produces **two different PNGs from the same code**
across runs of `npm run test:visual:baselines`. It is a capture-side raster flip, not an application
difference.

## Why it is being written down

It has now cost two false conclusions:

1. It produced a **false "platform divergence" report** from the controller, retracted afterwards
   with the wrong cause attached.
2. It appeared in Task 2's own cold before/after re-basing measurement as a **fifth moved state**,
   alongside the four the change really moved. Had it not been chased, this task would have reported
   a Browse state re-basing under a ruling that reaches only the buyer's detail screen — a change
   claiming a blast radius it does not have, which is exactly the class of error the A33 measurement
   method exists to prevent.

## The three proofs that it is the capture and not the code

Measured on darwin during Task 2, with amendments A58.2/A58.3 (a buyer-detail-screen change that
touches no Browse surface) applied:

1. **The DOM snapshot is byte-identical.** `dom-snapshots/browse-market-strip-location.json` hashes
   the same before and after. The two oracles disagree, and only the pixel one moved — a real
   application change moves both, as all four states this task genuinely moved did.

2. **Two fresh re-captures WITH the change applied reproduce the PRE-change hash exactly.**

   | capture | SHA-256 |
   |---|---|
   | pre-change baseline run | `fdc147067d1396bfda9b08a61738a766885a625d1667aca385827fe536112bcb` |
   | post-change baseline run | `11b4963d4fedd3ddd852575b440d5ac62028454c8f344fab3bdbc314d6ea058c` |
   | re-capture 2 (change applied) | `fdc147067d1396bfda9b08a61738a766885a625d1667aca385827fe536112bcb` |
   | re-capture 3 (change applied) | `fdc147067d1396bfda9b08a61738a766885a625d1667aca385827fe536112bcb` |

   Three captures of the same code, two distinct hashes. The `11b4963d…` value appeared once and
   never again.

3. **The app's own visual-parity case for that state passes** against the `fdc14706…` baseline
   (`npm run test:e2e`, 220/220). So the app and the reference agree at `maxDiffPixels: 0` — which a
   genuine divergence could not do.

## Why no gate catches it

`frontend/tests/capture-determinism.spec.ts` asserts byte-identity across ten captures for
**`header-1000` and `header-1100` only**. Those two were chosen when the partial-raster defect was
found (Task V17) because they were the states that exhibited it; the suite was never widened.
`browse-market-strip-location` is a Browse capture with a Leaflet canvas and a selected practice, so
it has strictly more moving parts than either of the two that are checked.

## What this is NOT

Not a tolerance question. `playwright.config.ts` keeps `maxDiffPixels: 0` beside `threshold: 0.1`,
and relaxing either requires a recorded reason (CLAUDE.md, "Source of truth for the UI"). Nothing
here proposes relaxing anything — a non-deterministic ORACLE is the problem, and a wider tolerance
would hide it rather than fix it. The `--disable-partial-raster` launch flag is already set at the
top level of the config for both projects, so whatever this is, it is not the defect that flag was
added for, or not only that one.

## Open, for whoever picks this up

- Which pixels differ between `fdc14706…` and `11b4963d…`? Not measured here. A pixel diff of the
  two would say whether this is the same rounded-corner antialiasing class as V17's finding or
  something on the map canvas.
- Is the flip sensitive to what ran before it in the same worker? Both runs that produced it were
  full 120-test `reference` runs; the two clean re-captures were single-test runs. That correlation
  is suggestive and is NOT established — two data points either side.
- Does `capture-determinism.spec.ts` want widening to every state that renders the map, or is a
  ten-capture check too expensive at 18 s per state (the two it covers already cost ~37 s of every
  baseline run)?

Until it is settled, a re-basing measurement that reports `browse-market-strip-location` as moved
should re-capture it twice before believing it.
