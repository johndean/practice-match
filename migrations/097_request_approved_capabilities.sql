-- D-C67 (John, 2026-09-24, verbatim: "all toggles must be fully functional and SELLER must be able
-- to manage it all and per seller"), read with D-C66 (2026-09-24), which made the seller's
-- listing-wide ceilings per-buyer releasable and so made the GRANT the only thing left between a
-- listing and disclosure.
--
-- THE NUMBER IS CLAIMED, not taken from the end of the list (`docs/MIGRATIONS.md`'s own rule, and
-- `DEPLOY.md`'s): `097` returned to FREE on 2026-09-15 when two branches merged having written no
-- file, the register carries this file's row, and the documented per-ref loop finds no other claim
-- on it. It sits BELOW `099` and `100` deliberately — it alters `request` and depends on `096`
-- alone, and neither later file creates or reads that table, so filename order is correct on a
-- fresh database (proved by applying the whole ladder into an empty one).
--
-- THIS RELEASE CANNOT BE ROLLED BACK BY REDEPLOYING THE PREVIOUS IMAGE, and that is stated here
-- because nothing else in this repository would say it (fix round 1, review Important-2). The
-- `DROP COLUMN` below is the FIRST in this repository's history -- `grep -l "DROP COLUMN"
-- migrations/*.sql` returns this file and nothing else, every prior migration being additive --
-- and `scripts/migrate.py` has no down mechanism at all. The previous image's
-- `app/disclosure/access.py` and `app/disclosure/requests.py` both SELECT
-- `approved_disclosure_level`, so redeploying it makes `GET /api/listings`, `GET /api/listings/{id}`,
-- the seller inbox and the decide route raise `UndefinedColumn`. The same window opens for the
-- length of a rolling restart, since migrations run at api start.
--
-- THE RECOVERY IS FORWARD, NEVER BACKWARD: re-deploy THIS release (or later). The data is safe and
-- the mapping is invertible -- the backfill below is a total function with an inverse, so a down
-- migration could be written if one is ever wanted -- but no code reads the old column any more, so
-- restoring it would be restoring a column with no reader.
--
-- WHAT LIMITS THE BLAST RADIUS, measured rather than assumed (2026-09-24): production answers
-- `"site_mode":"coming_soon"` on `GET /api/healthz`, and `app/main.py:130` mounts `listings_router`,
-- `seller_listings_router`, `requests_router` and `seller_requests_router` ONLY under
-- `site_mode == "app"`. On production today those routes are not mounted at all -- they fall
-- through to `not_found_router`'s JSON 404 -- so there is nothing there for a rollback to break.
-- The window is real on QA (which may never run `coming_soon`, `app/config.py:129`) and on
-- production from the day it switches to `app`. Ship to QA first and verify there, as always.
--
-- A grant is a SET of capabilities, not one named level. Until now `request.approved_disclosure_level`
-- held exactly one of six values, so of the thirty-two subsets of the five capabilities a seller
-- could store six: each capability alone, or all five. The product's own approved sentence for an
-- accepted inbox row -- "You released the financial packet and floor plan to this buyer."
-- (`frontend/src/logic.js`'s `sellerVals`) -- describes a grant of TWO, which that column could
-- never represent; and `app/api/requests.py`'s own default makes every request FULL_CONFIDENTIAL,
-- so with no chooser in front of it one click of Accept released all five together.
--
-- ONE HOME FOR ONE FACT (`migrations/031_listing_asset.sql`'s own rule: "two homes for one fact is
-- how orders drift"): the single-value column is REPLACED rather than kept beside an array, so no
-- reader can ask the stale one. `requested_disclosure_level` is untouched -- a buyer still asks for
-- one named level, which is what directive §16 models and what `app.disclosure.levels.covers()`
-- still maps to a default grant set.
--
-- THE THREE STATES ARE DISTINCT AND EACH MEANS SOMETHING DIFFERENT:
--   NULL          no decision has been taken (PENDING), or the decision was a refusal (DENIED)
--   '{}'          a decision that released NOTHING -- D-C67's own fail-closed rule, and the one
--                 state the old column could not hold at all, because
--                 `request_approved_needs_decision_ck` requires a non-NULL value on an APPROVED row
--   '{FINANCIALS,...}'  exactly what the seller ticked
ALTER TABLE request ADD COLUMN approved_capabilities text[];

-- Backfill through `app.disclosure.levels.covers()`'s own rule, spelled in SQL: the umbrella name
-- expands to the five it covers, every other value stands for itself. A NULL stays NULL.
UPDATE request SET approved_capabilities = CASE
    WHEN approved_disclosure_level IS NULL THEN NULL
    WHEN approved_disclosure_level = 'FULL_CONFIDENTIAL'
      THEN ARRAY['IDENTITY','EXACT_LOCATION','UNREDACTED_IMAGES','FINANCIALS','FLOOR_PLANS']
    ELSE ARRAY[approved_disclosure_level]
  END;

-- Both cross-column CHECKs name the departing column, so each is dropped and restated against the
-- new one. Restated rather than edited: PostgreSQL has no ALTER ... ALTER CONSTRAINT for a CHECK.
ALTER TABLE request DROP CONSTRAINT request_approved_needs_decision_ck;
ALTER TABLE request DROP CONSTRAINT request_pending_has_no_decision_ck;
ALTER TABLE request DROP COLUMN approved_disclosure_level;

-- The membership CHECK, 096's own IN-list one column over. `array_position(... , NULL) IS NULL` is
-- not decoration: `ARRAY[NULL]::text[] <@ ARRAY['IDENTITY',...]` evaluates to NULL, and a CHECK
-- passes on NULL, so without it a grant of `{NULL}` would be storable and would read as one
-- unknown member. `tests/disclosure/test_levels.py` pins this element list against
-- `app.disclosure.levels.CAPABILITIES` in both directions, read from `pg_constraint`.
ALTER TABLE request ADD CONSTRAINT request_approved_capabilities_ck CHECK (
  approved_capabilities IS NULL
  OR (array_position(approved_capabilities, NULL) IS NULL
      AND approved_capabilities <@ ARRAY['IDENTITY','EXACT_LOCATION','UNREDACTED_IMAGES','FINANCIALS','FLOOR_PLANS']::text[]));

-- 096's own two, verbatim but for the column name. The one-directional reading is unchanged: a
-- REVOKED row keeps the capabilities it was approved with, for history.
ALTER TABLE request ADD CONSTRAINT request_approved_needs_decision_ck CHECK (
  status <> 'APPROVED' OR (approved_capabilities IS NOT NULL AND reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL));
ALTER TABLE request ADD CONSTRAINT request_pending_has_no_decision_ck CHECK (
  status <> 'PENDING' OR (reviewed_at IS NULL AND reviewed_by IS NULL AND approved_capabilities IS NULL));
