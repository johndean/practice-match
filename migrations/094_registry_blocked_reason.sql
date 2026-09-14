-- A38 fix round 3 / controller ruling on re-review Important 2 (2026-09-14): the member's sentence
-- gets its own column, because it was sharing the operator's.
--
-- `dataset_registry.notes` had TWO readers and the branch's own artefacts named one of them. The
-- admin Data Sources tab prints it verbatim into the design's Source sub-line (which is why 092 and
-- 093 shortened it and `app.census.registry.SOURCE_SUBLINE_CAP` bounds it), and
-- `app/api/market.py`'s `_layer_state` served the SAME string to members as `blocked_reason` --
-- emitted by `GET /api/layers`, by the docked panel's payload and by the boundaries payload, and
-- documented in `docs/integrations/market-data-api.md` as the field that says WHY a layer is
-- blocked. Three of the four datasets `LAYERS` gates carry a seeded GEOGRAPHY note that would have
-- been served as the reason for a licence block: `cbp` "Parameter renames to NAICS2022 with the
-- 2023+ releases", `zbp` "D11 / A-C6: ZIP counts come from CBP's zip geography; ZIPs treated as
-- ZCTAs", `acs5_prior` "Growth baseline only". None of those is a reason for a block.
--
-- Fix round 2 then removed the one runtime writer of `notes` (the licence-decision route no longer
-- COALESCEs the operator's rationale into it), which was right for the tab and left the member's
-- reason with no author at all. The ruled fix is this column, not a restored write: the two
-- sentences have different audiences, different lengths and different authors, and one column
-- could only ever be right for one of them.
--
--   * `notes`          -- the OPERATOR's column and the admin tab's. Bounded by the measured
--                         `SOURCE_SUBLINE_CAP`, owned by migrations, never written at runtime.
--   * `blocked_reason` -- the MEMBER's sentence, served verbatim when a layer's licence is not
--                         cleared. Never a geography note. `DEFAULT_BLOCKED_REASON`
--                         ("Licence not cleared.") still stands in where a row has none, so the
--                         column is nullable and a row that says nothing says the default.
--
-- `tests/api/test_market_layers.py` and `tests/census/test_registry.py` pin the two readers against
-- their own columns in both directions, so neither can drift back into the other.
ALTER TABLE dataset_registry ADD COLUMN blocked_reason text;

-- The four datasets `app.api.market.LAYERS` gates, in a member's words. Every one of them is
-- `cleared` today, so none of these sentences is currently served: they are what a member WOULD be
-- told the day the VIN Foundation blocks or un-clears one, which is the state this column exists
-- for and the state nobody could write a sentence for before.
UPDATE dataset_registry SET blocked_reason = 'Census income, household and pet-household figures are unavailable while their licence is under review.' WHERE dataset_key = 'acs5';
UPDATE dataset_registry SET blocked_reason = 'Population growth is unavailable while the licence for the earlier Census release it is measured against is under review.' WHERE dataset_key = 'acs5_prior';
UPDATE dataset_registry SET blocked_reason = 'Average practice payroll is unavailable while its County Business Patterns licence is under review.' WHERE dataset_key = 'cbp';
UPDATE dataset_registry SET blocked_reason = 'Veterinary competition counts are unavailable while their ZIP Code Business Patterns licence is under review.' WHERE dataset_key = 'zbp';
