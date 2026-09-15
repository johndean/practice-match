# Migration numbers — the one ledger

`scripts/migrate.py` records each file's SHA-256 and refuses a tree whose bytes moved, so **an applied migration is immutable** and two branches must never claim the same number. `main` alone is not enough to decide the next free number: a number claimed on an *unmerged branch* is taken, and two branches took `092` on 2026-09-15 before this file existed.

**Claim a number by adding a row here, in the same commit as the migration file.** Before you claim, run:

```
for r in $(git for-each-ref --format='%(refname)' refs/heads refs/remotes); do
  git ls-tree -r --name-only "$r" -- migrations/ 2>/dev/null
done | sort -u | tail -n 20
```

**Run it as a loop, one ref at a time, and do not "simplify" it back.** `git ls-tree` takes exactly ONE
tree-ish; every ref after the first is swallowed as a pathspec, so the single-command form reports only
`main`'s files and says nothing about any unmerged branch — which is the only kind of claim that ever
collides. This file shipped with that broken form on 2026-09-15 and it was measured the next day:
as published it returned **2** files and found **0** numbered 092 or above; the loop returns **6** and
finds **4**, every one of them on a branch that has not merged. A ledger whose own check cannot see the
failure it names is not a ledger.

| # | File | Branch | What |
|---|---|---|---|
| 090 | `090_listing_photo_captions.sql` | **main** | photograph captions |
| 091 | `091_listing_provenance.sql` | **main** | listing provenance |
| 092 | `092_esri_basemap_registry.sql` | `feat/admin-data-sources` | the two Esri basemap registry rows |
| 093 | `093_registry_notes_fit_the_tab.sql` | `feat/admin-data-sources` | shorten the seeded registry notes to the measured cap |
| 094 | `094_registry_blocked_reason.sql` | `feat/admin-data-sources` | the member-facing "why is this blocked" column |
| 095 | `095_ingest_run_notes.sql` | `fix/census-204` | per-run notes (which states were skipped, and why) |
| 096 | `096_request.sql` | *(reserved — A43, the Requests build)* | `request` + `request_event` |
| 099 | `099_avma_pet_rate_registry.sql` | `feat/pet-rate-provenance` | the AVMA cited-statistic registry row, and the blocked per-geography feed's note stops standing in for it |

**Next free: 100.** `097` is held by `feat/admin-data-sources` and `098` by `feat/a41-settings` — both
were told "097" in briefs written minutes apart by the same author who wrote this file, and were
deconflicted by message before either wrote a file. Neither number is claimed below yet, because a row
here means a file exists; if either task turns out to need no migration, its number returns to free.
`099` IS claimed — the row above, and the file beside it in the same commit.

The identifiability sub-project holds its own carve-out at `040`–`049` (amendment A-C12); `043`–`049` are still free inside it.
