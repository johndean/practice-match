# RETRACTED — `browse-market-strip-location` was not a platform divergence

**Raised 2026-09-23. Retracted the same day, after investigation.** The defect described by the
earlier versions of this record does not exist. Kept rather than deleted, because the reasoning
error is worth more than the file.

## What was claimed

That the approved state `browse-market-strip-location` failed visual parity deterministically on
darwin (61962 pixels, ratio 0.05) while CI's linux Chromium passed the identical SHA, and that the
oracle's verdict therefore depended on which machine ran it.

## What is true

Re-run of the full documented sequence — `test:visual:baselines` then the whole `app` project —
**220 passed**, including this state. The failure does not reproduce.

It was an artefact of the investigator's own environment. Mid-gate, the scratch database `pm_gate`
was created to work around a `092` checksum block on the shared dev database. The reference
baselines were generated against that database in one state; by the time `visual.spec.ts` ran, the
suite's own account and listing flows had created 33 listings in it. Baseline and comparison were
captured either side of that change. Once both happen after it, they agree.

CI never saw it because CI starts from a fresh service-container database for every run and never
straddles the change.

## The hypotheses that were tested and killed, in order

1. **The LOCATION-mode summary adapter resolved after the screenshot.** Refuted by reading the
   diff image: the Market snapshot strip is pixel-identical — header, all six cards, every figure
   and bar.
2. **A map viewport or timing race.** Refuted twice. Raising the state's settle from 400 ms to
   4000 ms produced the identical 61962 pixels; and direct measurement showed both targets at the
   same container size (604x311 at top 141), the same pane transform
   `matrix(1, 0, 0, 1, -183, 0)`, the same tile `10/421/233` and the same 9 markers.
3. **Platform divergence between darwin and linux.** Refuted by this retraction: the sequence
   passes on darwin.

## The lesson worth keeping

**Baselines and the comparison must be generated against the same database state.** The reference
project is a static prototype, but the app project's flows mutate the database they share with it,
so generating baselines and then running the app project across a database change compares two
different worlds. Creating a scratch database part-way through a gate is exactly how that happens.

And the process lesson: "deterministic and local-only" is evidence of a stable local CONDITION, not
evidence of a platform defect. The first reading of that evidence was wrong, was written into the
repository, and was corrected only after the full sequence was re-run.

## Still open, and unrelated to the above

The shared dev database carried `092_esri_basemap_registry.sql` under a stale checksum, which is
what forced the scratch database in the first place. That was repaired on 2026-09-23 — the two
seeded `dataset_registry` rows brought to the file's current values and the ledger checksum
corrected — so a future gate can run against `practice_match` without a scratch database at all.
