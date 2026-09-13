-- A38 fix round 1 / controller ruling on review I1 (2026-09-13): the operator notes 017 seeded are
-- shortened to one sentence each, so the admin Data Sources tab renders inside the approved design.
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
-- composed sub-line (`license_name or "Licence not recorded"` + " · " + notes [+ " · Terms drift
-- flagged"]) is the largest that stayed on two lines across word lengths 4-12.
-- `tests/census/test_registry.py::test_every_registry_note_fits_the_design_s_source_column` is the
-- pin, and it was RED on these ten rows: zbp rendered 226 px, practice_locations 187 px,
-- google_places_aggregate 190 px, overture_places 173 px, osm_tiles 150 px, and four more over 94.
--
-- NOTHING IS LOST. Each note below keeps the decision it records and the reference that carries the
-- rest (a plan decision id, a spec section, a controller amendment); the full text 017 wrote is in
-- that migration, which is applied and immutable, and in this repository's history. Two rows are
-- NOT touched -- `acs5_prior`, `cbp` and `pet_ownership` already fit -- and no row's
-- `license_status`, `license_url` or `attribution_text` is read or written here: this migration
-- changes prose and nothing that decides whether a dataset may ship.
UPDATE dataset_registry SET notes = 'D11 / A-C6: ZIP counts come from CBP''s zip geography from 2019; ZIPs treated as ZCTAs.' WHERE dataset_key = 'zbp';
UPDATE dataset_registry SET notes = 'Spec §12: purchased or scraped location lists are out of scope for V1.' WHERE dataset_key = 'practice_locations';
UPDATE dataset_registry SET notes = 'D17: in-memory only; clear after counsel accepts SST §13.' WHERE dataset_key = 'google_places_aggregate';
UPDATE dataset_registry SET notes = 'D16 rank 1; clear on Foundation approval of Task C2.' WHERE dataset_key = 'overture_places';
UPDATE dataset_registry SET notes = 'D16 rank 2; redundant with overture_places unless Overture drops Foursquare rows.' WHERE dataset_key = 'fsq_os_places';
UPDATE dataset_registry SET notes = 'A-C1: CARTO is the Census analytical basemap; Esri stays where the design requires it.' WHERE dataset_key = 'osm_tiles';
UPDATE dataset_registry SET notes = 'Satellite toggle stays flagged off until a licence names commercial web display.' WHERE dataset_key = 'imagery';
UPDATE dataset_registry SET notes = 'Confirm identifier and geography before any revenue-benchmark layer is promised (§15).' WHERE dataset_key = 'aies';
