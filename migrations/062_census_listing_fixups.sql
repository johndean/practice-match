-- B1 review findings (A-C16), closed as a NEW migration: 060/061 are frozen -- two other
-- worktrees have already applied them, and the runner refuses a changed file in every database
-- that has seen it.
--
-- Finding 1 (untested UPDATE arm) needed no schema change: `market_metric_license_gate` already
-- fires `BEFORE INSERT OR UPDATE`, it was only ever exercised by INSERTs. That gap is closed by
-- a test alone (tests/census/test_migration_062.py).
--
-- Finding 2: the trigger read `dataset_registry.license_status` twice -- once in the `IF`, again
-- inside the exception message's `COALESCE` -- so a concurrent `UPDATE dataset_registry` between
-- the two reads could make the message name a status that is no longer current (the
-- accept-or-refuse decision itself is unaffected; it is decided entirely by the first read).
-- Rewritten to read the status ONCE and name the dataset key -- which cannot go stale -- in the
-- message, and not the status it happened to read.
--
-- No DECLARE section, for the same reason 061 has none: a `DECLARE x text; BEGIN` block reads,
-- to `tests/test_migrate.py`'s `test_migration_files_never_manage_their_own_transaction` regex,
-- exactly like a migration managing its own transaction (a `;` immediately before `BEGIN`) --
-- `014_audit_log.sql` is the precedent for the DECLARE-free `$$\nBEGIN` shape. `CREATE OR
-- REPLACE FUNCTION` keeps the same function OID, so the trigger already bound to this function
-- name picks up the new body without a `CREATE TRIGGER`.
CREATE OR REPLACE FUNCTION market_metric_license_gate() RETURNS trigger AS $$
BEGIN
  IF (SELECT license_status FROM dataset_registry WHERE dataset_key = NEW.source_dataset) IS DISTINCT FROM 'cleared' THEN
    RAISE EXCEPTION 'market_metric write refused: dataset % is not licence-cleared (licence gate)', NEW.source_dataset;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

-- Finding 3: `geocode_review`, alone among the listing-scoped tables `060`/`061` added, carried
-- no foreign key to `listing` -- an orphan review row could outlive the listing it flagged. Same
-- `ON DELETE CASCADE` its siblings (`practice_location`, `practice_catchment`, `market_metric`)
-- use.
ALTER TABLE geocode_review
  ADD CONSTRAINT geocode_review_listing_id_fkey FOREIGN KEY (listing_id) REFERENCES listing(id) ON DELETE CASCADE;
