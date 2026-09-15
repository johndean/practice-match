-- Task PET-RATE-PROVENANCE (John's requirement of 2026-09-15), controller ruling (4).
--
-- The registry held ONE row, `pet_ownership`, for three different things:
--   (a) the single cited national incidence statistic the product actually uses;
--   (b) the AVMA Sourcebook publication, which this product does not and may not redistribute;
--   (c) the per-geography licensed incidence FEED, which is `blocked` and not in use.
-- Its note -- "Ship only the ACS-derived estimate (rate 0.57) until a licence is signed" -- was
-- the operating instruction for (a) written on the row for (c), and it named a rate that is no
-- longer the one in use. A reader of the Data Sources tab could not tell which of the three was
-- blocked, and the one thing actually shipping had no row of its own at all.
--
-- (a) gets its row. Its status is `unresolved`, which is the honest middle of this registry's own
-- three-valued gate: the statistic is VERIFIED against the published 2025 edition and is cited in
-- the product, and the right to redistribute the Sourcebook is NOT established -- its copyright
-- page prohibits reproduction or transmission in any form without the AVMA's written permission.
-- `unresolved` is deliberately NOT `blocked`: `blocked` is this schema's word for "must not ship"
-- (`market_metric`'s own trigger refuses a row whose source is not `cleared`, and the layer gate
-- reports `blocked` as a permanent refusal), and John commissioned the rate corrected and the
-- provenance recorded, not the layer withdrawn. Nothing references this key as a `source_dataset`
-- -- the pets rows are stamped `acs5`, because the HOUSEHOLDS are what the Census supplied -- so
-- this row gates nothing and reports.
--
-- No extract of the Sourcebook is stored here or anywhere: the rate, its edition, its reference
-- period and an attribution are the whole of what this product carries from it.
INSERT INTO dataset_registry
  (dataset_key, display_name, api_dataset_id, base_url, vintage, naics_param, refresh_cadence,
   license_status, license_name, license_url, attribution_text, notes)
VALUES (
  'avma_pet_rate',
  'AVMA Sourcebook — national pet-ownership rate (cited statistic)',
  NULL,
  'https://www.avma.org/resources-tools/reports-statistics/pet-ownership-and-demographics-sourcebook',
  '2025',
  NULL,
  'On publication (AVMA Sourcebook edition)',
  'unresolved',
  'AVMA Sourcebook — all rights reserved',
  'https://www.avma.org/resources-tools/reports-statistics/pet-ownership-and-demographics-sourcebook',
  'Pet-ownership incidence: American Veterinary Medical Association, 2025 Pet Ownership and Demographics Sourcebook',
  'SOURCE VERIFIED / LICENCE-REDISTRIBUTION UNRESOLVED. The one cited statistic: 58.6 % of United States households own at least one pet (American Veterinary Medical Association, 2025 Pet Ownership and Demographics Sourcebook; reference period 2025) — the rate in app/census/pet_rate.py, behind every estimated-pet-household figure the product shows. The Sourcebook itself may not be reproduced or transmitted without the AVMA''s written permission, so no table, figure or page of it is stored or shipped: the rate, the edition, the reference period and this attribution are the whole of what this product carries. NOT the per-geography licensed incidence feed, which is `pet_ownership` and stays blocked. Clear only when the VIN Foundation holds written permission naming this use.'
);

-- (c) keeps its status and loses the instruction that belonged to (a).
--
-- SHORTENED WHEN THIS BRANCH MERGED (2026-09-15). `feat/admin-data-sources` caps the Data Sources
-- tab's SOURCE sub-line at `app.census.registry.SOURCE_SUBLINE_CAP` = 115 COMPOSED characters, and
-- this row has no `license_name`, so the tab renders "Licence not recorded · <note>" -- 23
-- characters before the note begins. The note written here first was 113, composing to 136, which
-- reddened that pin AND made `POST /api/admin/data-sources/pet_ownership/license` answer 422: the
-- route refuses a decision whose composed line would not fit. This branch's own closing comment
-- says the note "is deliberately kept UNDER the cap" -- it measured the note and the cap is on the
-- composed line -- so this is that intent, measured the way the cap is. 87 characters, composing
-- to 110 of 115. Recorded rather than hidden: clearing this row LATER adds a terms URL and with it
-- the sweep's 22-character drift clause, which this note would not leave room for, so whoever
-- clears it shortens the note in the same migration. Both facts the branch wrote are kept.
UPDATE dataset_registry
SET notes = 'Spec §12: the LICENSED per-geography feed; none is licensed. Cited rate: avma_pet_rate.',
    display_name = 'Pet-ownership incidence, per geography (licensed feed)'
WHERE dataset_key = 'pet_ownership';

-- TWO THINGS A LATER READER WILL NEED, BOTH RECORDED RATHER THAN LEFT TO BE DISCOVERED.
--
-- 1. THIS ROW CONTRADICTS A RECORDED RULING, DELIBERATELY AND WITH ITS PREMISE GONE.
--    `docs/superpowers/specs/2026-09-13-admin-control-surface-design.md` §10 question 4 (controller,
--    2026-09-14) ruled: "The pets 0.57 factor: a registry row or a methodology note? -- A METHODOLOGY
--    NOTE in the layer's own caveat. It is a modelled factor, not a dataset; a `dataset_registry` row
--    would imply a licence and a vintage it does not have." That reasoning was correct about `0.57`,
--    which had no source, no edition and no licence to state. It is not correct about what replaces
--    it: the factor now HAS a named publisher, a named edition, a reference period and a licence
--    position that is explicitly unresolved -- which is exactly what this table records -- and Task
--    PET-RATE-PROVENANCE's own ruling 4 (John's requirement of 2026-09-15) asks for that status
--    "recorded on the `dataset_registry` row and visible on the admin Data Sources tab". The earlier
--    ruling's own condition ("a licence and a vintage it does not have") is what changed. It is named
--    here, and in the task report, so the controller can reverse it in one line rather than find an
--    unexplained row. The METHODOLOGY NOTE it ruled for is ALSO shipped and is not replaced by this:
--    `app.api.market.PETS_CAVEAT` carries it on the layer, composed from the same provenance record.
--
-- 2. THE NOTE ABOVE IS OVER THE ADMIN TAB'S MEASURED CAP, AND BELONGS ON ITS ALLOW-LIST.
--    `feat/admin-data-sources` (unmerged at the time of writing) caps a registry note at
--    `app.census.registry.SOURCE_SUBLINE_CAP` = 115 composed characters so the Data Sources tab
--    renders inside the approved design, with `LEGAL_NOTE_ROWS` allow-listing rows whose text is
--    legally material -- "legally material text is never shortened to fit a layout" (its ruling F2).
--    `avma_pet_rate` is that category: every clause above is either the citation, the copyright
--    condition the unresolved status rests on, or the separation from the blocked feed. WHOEVER
--    MERGES THE TWO BRANCHES adds `avma_pet_rate` to `LEGAL_NOTE_ROWS`; it is not a defect in either.
--    `pet_ownership`'s new note is deliberately kept UNDER the cap (093 lists it among the three
--    rows that "already fit" and does not touch it), so nothing else on that branch has to move.
