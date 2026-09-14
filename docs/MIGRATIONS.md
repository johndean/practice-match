# Migration numbers — the one ledger

`scripts/migrate.py` records each file's SHA-256 and refuses a tree whose bytes moved, so **an applied migration is immutable** and two branches must never claim the same number. `main` alone is not enough to decide the next free number: a number claimed on an *unmerged branch* is taken, and two branches took `092` on 2026-09-15 before this file existed.

**Claim a number by adding a row here, in the same commit as the migration file.** Before you claim, run:

```
git ls-tree -r --name-only --full-name $(git for-each-ref --format='%(refname)' refs/heads refs/remotes) -- migrations/ 2>/dev/null | sort -u | tail -n 20
```

| # | File | Branch | What |
|---|---|---|---|
| 090 | `090_listing_photo_captions.sql` | **main** | photograph captions |
| 091 | `091_listing_provenance.sql` | **main** | listing provenance |
| 092 | `092_esri_basemap_registry.sql` | `feat/admin-data-sources` | the two Esri basemap registry rows |
| 093 | `093_registry_notes_fit_the_tab.sql` | `feat/admin-data-sources` | shorten the seeded registry notes to the measured cap |
| 094 | `094_registry_blocked_reason.sql` | `feat/admin-data-sources` | the member-facing "why is this blocked" column |
| 095 | `095_ingest_run_notes.sql` | `fix/census-204` | per-run notes (which states were skipped, and why) |
| 096 | `096_request.sql` | *(reserved — A43, the Requests build)* | `request` + `request_event` |

**Next free: 097.**

The identifiability sub-project holds its own carve-out at `040`–`049` (amendment A-C12); `043`–`049` are still free inside it.
