-- A38 fix round 1 / controller ruling on review I1 (2026-09-13), rewritten in fix round 2 on
-- rulings F2, F4 and F5 (2026-09-14): the operator notes 017 seeded are shortened to one sentence
-- each, EXCEPT where the sentence is legally material, so the admin Data Sources tab renders
-- inside the approved design.
--
-- THIS FILE IS STILL EDITABLE. `093` has been applied on NO deployed environment -- nothing from
-- `feat/admin-data-sources` has ever been shipped by `scripts/deploy.sh`, so neither QA nor
-- production has it in `schema_migration`; `git ls-tree origin/main migrations/` ends at 091. It
-- IS applied in the local per-worktree template databases, and `scripts/migrate.py`'s
-- `refuse_changed_files` refuses a changed checksum, so a local database has to be recreated
-- after an edit here. That is the same call the controller made for 092.
--
-- WHY THIS IS A DATA CHANGE AND NOT A RENDERING ONE. The tab prints `dataset_registry.notes`
-- VERBATIM into the Source column's sub-line. Clamping or truncating it client-side was offered
-- and REFUSED by the controller: this is the surface CLAUDE.md marks legally load-bearing
-- ("Blocked datasets never ship ... The admin Data Sources tab shows this gate; keep it"), and
-- hidden text on the legal gate is not an option. So the notes themselves are made to fit.
--
-- THE CAP IS MEASURED, in real Chromium at the design's own 1440x940 with its own three
-- stylesheets: the Source column is 376 px, the design's tallest fixture row is 94 px, and its
-- Source cell is one line of `attribution_text` plus TWO lines of sub-line. 115 characters of
-- composed sub-line is the largest that stayed on two lines across word lengths 4-22. It lives in
-- `app.census.registry.SOURCE_SUBLINE_CAP` with its measurement, `scripts/measure_source_subline_cap.py`
-- re-derives it, and `tests/census/test_registry.py::test_every_registry_note_fits_the_design_s_source_column`
-- is the pin. The pin counts the quarterly sweep's own " · Terms drift flagged" for every row the
-- sweep can reach (review F4), which is every row with a `license_url`: a note that fits only
-- until its terms page is edited does not fit.
--
-- TWO ROWS ARE DELIBERATELY LONGER THAN THE CAP AND ARE ALLOW-LISTED BY KEY
-- (`app.census.registry.LEGAL_NOTE_ROWS`, controller ruling F2): legally material text is never
-- shortened to fit a layout. `practice_locations` keeps the name of the blocked 2017 Google Places
-- export (plan D15) and the Google Maps Platform terms that forbid storing or rendering it -- the
-- first draft of this migration dropped both, which made plan D15's own sentence ("The registry's
-- `practice_locations` row names the file as blocked") false. `google_places_aggregate` keeps the
-- SST §13.2 in-memory-only condition its block rests on. Those two rows may wrap to a third line.
--
-- NOTHING ELSE IS LOST. Each note below keeps the decision it records and the reference that
-- carries the rest (a plan decision id, a spec section, a controller amendment); the full text 017
-- wrote is in that migration, which is applied and immutable, and in this repository's history.
-- THREE rows are NOT touched -- `acs5_prior`, `cbp` and `pet_ownership` already fit -- and no
-- row's `license_status`, `license_url` or `attribution_text` is read or written here: this
-- migration changes prose and nothing that decides whether a dataset may ship.
--
-- `imagery` is shortened FURTHER than its own two lines needed (fix round 3): the licence-decision
-- route refuses a decision whose composed sub-line would not fit, and that composition counts the
-- sweep's drift clause for a row that will have a terms URL -- so an 88-character note left this
-- row unable to RECORD a terms URL at all, which is the one act the route exists for. 017's own
-- "written licence names commercial web display" is kept verbatim (the condition a later reader
-- will quote); the subject it lost is the row itself. `google_places_aggregate` goes the other way
-- and regains SST §13.1 and the billing precondition: round 1 refuted that complaint because the
-- row composed to exactly 115 with no headroom, and the legal allow-list has since removed that
-- reason.
--
-- RED BEFORE THIS AND 092: ten rows over the cap (093's eight below and 092's two), and on the
-- rendered table `zbp` at 226 px, `google_places_aggregate` 190, `practice_locations` 187,
-- `overture_places` 173, `osm_tiles` 150 and five more over the design's tallest 94 px.
UPDATE dataset_registry SET notes = 'D11 / A-C6: ZIP counts come from CBP''s zip geography; ZIPs treated as ZCTAs.' WHERE dataset_key = 'zbp';
UPDATE dataset_registry SET notes = 'Spec §12 / D15: blocked, incl. Report_Hospital_Competitor_All_US_ZipCode_FULL.csv; Google Maps Platform Terms §3.2.3 and SST §14 forbid storing or rendering its content.' WHERE dataset_key = 'practice_locations';
UPDATE dataset_registry SET notes = 'D17: the POI count is held in memory only (SST §13.2, 30-day ceiling) and persisted values diverge from level_live (SST §13.1 Customer Values); clear only after VIN Foundation counsel accepts SST §13 and a Google Cloud billing account exists.' WHERE dataset_key = 'google_places_aggregate';
UPDATE dataset_registry SET notes = 'D16 rank 1; clear after Task C2.' WHERE dataset_key = 'overture_places';
UPDATE dataset_registry SET notes = 'D16 rank 2; redundant with overture_places unless Overture drops Foursquare.' WHERE dataset_key = 'fsq_os_places';
UPDATE dataset_registry SET notes = 'A-C1: CARTO is the Census analytical basemap; Esri stays where the design says.' WHERE dataset_key = 'osm_tiles';
UPDATE dataset_registry SET notes = 'Off until a written licence names commercial web display.' WHERE dataset_key = 'imagery';
UPDATE dataset_registry SET notes = 'Confirm identifier and geography before any revenue-benchmark layer is promised (§15).' WHERE dataset_key = 'aies';
