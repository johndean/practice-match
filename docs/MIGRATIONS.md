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
| 040 | `040_listing_identifiable_content_visibility.sql` | `feat/image-identifiability` | the listing's one authoritative identifiable-content setting (`SHOW`/`NOT_SHOW`, default `NOT_SHOW`) |
| 041 | `041_listing_asset_privacy.sql` | `feat/image-identifiability` | one privacy record per photograph — the per-image state machine |
| 042 | `042_listing_publish_photos_ready_trigger.sql` | `feat/image-identifiability` | the fail-closed publish gate: no `published` listing while a photograph is not ready |
| 090 | `090_listing_photo_captions.sql` | **main** | photograph captions |
| 091 | `091_listing_provenance.sql` | **main** | listing provenance |
| 092 | `092_esri_basemap_registry.sql` | `feat/admin-data-sources` | the two Esri basemap registry rows |
| 093 | `093_registry_notes_fit_the_tab.sql` | `feat/admin-data-sources` | shorten the seeded registry notes to the measured cap |
| 094 | `094_registry_blocked_reason.sql` | `feat/admin-data-sources` | the member-facing "why is this blocked" column |
| 095 | `095_ingest_run_notes.sql` | `fix/census-204` | per-run notes (which states were skipped, and why) |
| 096 | `096_request.sql` | *(reserved — A43, the Requests build)* | `request` + `request_event` |
| 099 | `099_avma_pet_rate_registry.sql` | `feat/pet-rate-provenance` | the AVMA cited-statistic registry row, and the blocked per-geography feed's note stops standing in for it |

**Next free: 097.** `097` WAS held by `feat/admin-data-sources` and `098` by `feat/a41-settings` — both
were told "097" in briefs written minutes apart by the same author who wrote this file, and were
deconflicted by message before either wrote a file. **Both numbers returned to free on 2026-09-15**,
when those two branches merged to `main` having written no migration at all: this file's own rule is
that a row here means a file exists, and the per-ref loop above finds no `096`, `097` or `098` on any
ref. `096` stays RESERVED for A43 (the row above), which is a reservation and not a file. `099` is
claimed — the row above, and the file beside it.

The identifiability sub-project holds its own carve-out at `040`–`049` (amendment A-C12); `043`–`049` are still free inside it.
