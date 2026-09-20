-- Ruling D-C59 (John, 2026-09-20, verbatim): "a buyer can not be a seller and a seller can not be
-- a buyer - we will always keep accounts separate and if the edge case exists then then the user
-- will have to have 2 accounts". Spec: docs/superpowers/specs/2026-09-20-account-role-exclusivity-
-- ruling.md, which measured that NOTHING enforced it: `role_grant` (migration 011) has one CHECK,
-- on the role NAME, and no constraint, trigger or application code stopped one account holding
-- both `buyer` and `seller` at once. This migration is that enforcement, in the database, so the
-- invariant holds no matter which future code path writes the table.
--
-- MECHANISM CHOSEN, AND WHY IT IS NOT A UNIQUE INDEX. The idiomatic Postgres way to say "at most
-- one of these two values per group" is a generated "bucket" column (both `buyer` and `seller` map
-- to one value) under a partial unique index (`WHERE revoked_at IS NULL`). That is fully safe
-- under concurrency for free -- the index itself serialises two conflicting inserts -- but
-- `CREATE UNIQUE INDEX` VALIDATES EVERY EXISTING ROW at build time and fails outright the moment
-- one already violates it. The ruling's own spec says plainly that whether any account on QA or
-- production already holds both roles is a question THIS RULING DOES NOT ANSWER, and that nothing
-- here may migrate an existing account's roles. A mechanism that can refuse to install itself
-- depending on what the table happens to hold is therefore the wrong tool, however idiomatic.
--
-- A trigger has no such failure mode: creating a trigger function and attaching it does not scan
-- or validate a single row already in the table. A legacy account that holds both roles today (if
-- one exists -- unknown, see the spec's "Open" section) is left EXACTLY as it is: this migration
-- neither reads nor writes `role_grant` itself, and the trigger below only ever refuses a FUTURE
-- write that would newly create, or re-create, the violation. That is exactly the shape the
-- ruling's "Open" section calls for.
--
-- CONCURRENCY. The naive form of this trigger -- "SELECT the other role for this account, raise if
-- found" -- is not safe by itself: two transactions granting `buyer` and `seller` to the SAME
-- account at the same moment would each run that SELECT before the other's INSERT is visible under
-- ordinary MVCC/read-committed rules, both would find nothing, and both would commit, leaving the
-- exact account the ruling forbids. `pg_advisory_xact_lock`, keyed on the account id, closes that:
-- it is the same idiom `scripts/seed_persona.py`'s own `SEED_LOCK_KEY` uses for an identical class
-- of problem (a cross-row invariant a single-row CHECK constraint cannot express, on a table this
-- migration cannot unconditionally re-validate). The lock is per ACCOUNT -- `hashtextextended` of
-- the account id, never a table-wide lock -- so two different accounts' grants never contend with
-- each other. The second of two racing transactions blocks until the first commits or rolls back,
-- then re-runs its own check against what is now actually true, so the race is CLOSED rather than
-- merely narrowed: whichever of the two writes second discovers the first's committed grant and is
-- refused, exactly as if the two had been serialised by hand.
--
-- WHAT THIS DOES NOT DO, ON PURPOSE. It does not touch a single existing `role_grant` row: no
-- UPDATE, no DELETE, no backfill. An account that already holds both roles today keeps holding
-- both after this migration runs -- the trigger cannot see it and would not touch it if it could --
-- and remains free to revoke either role at any time (a revoke only ever sets `revoked_at`, which
-- the guard below exempts unconditionally). What changes is that NO ACCOUNT CAN NEWLY ENTER that
-- state from this migration forward, in this table, however it is written.

-- NOTE ON SHAPE: this function deliberately declares no DECLARE section. A `DECLARE ... ;`
-- block ends in a semicolon immediately before `BEGIN`, which trips
-- tests/test_migrate.py::test_migration_files_never_manage_their_own_transaction -- that guard's
-- regex (`(?:^|;)\s*(begin|commit|rollback)\b`) exists to catch a migration that opens its own
-- transaction, and cannot distinguish that from a PL/pgSQL block's own `BEGIN` once a semicolon
-- precedes it (014_audit_log.sql's function avoids this the same way, by declaring nothing before
-- its own `BEGIN`). The `other_role` value below is therefore computed inline, twice, rather than
-- once into a declared variable.
CREATE OR REPLACE FUNCTION role_grant_enforce_exclusivity() RETURNS trigger AS $$
BEGIN
  -- Only a grant becoming ACTIVE, of `buyer` or `seller`, is interesting here. A revoke
  -- (`NEW.revoked_at IS NOT NULL`) is always allowed -- it can only ever remove a role, never add
  -- one -- and a `staff`/`admin` grant is untouched by this ruling (D-C54's superset stands).
  IF NEW.revoked_at IS NOT NULL OR NEW.role NOT IN ('buyer', 'seller') THEN
    RETURN NEW;
  END IF;

  -- Serialises every role_grant write for THIS account (see the note above) before the EXISTS
  -- check below can be answered by a result the other side of a race has not committed yet.
  PERFORM pg_advisory_xact_lock(hashtextextended(NEW.account_id::text, 0));

  -- `id IS DISTINCT FROM NEW.id` excludes the row this statement is itself writing: an ordinary
  -- INSERT can never self-match (its role is NEW.role, never the other role), but a direct UPDATE
  -- that renames an existing active row's OWN `role` column in place (buyer -> seller on the same
  -- id, with no separate revoke) would otherwise see its own pre-update value here, since a BEFORE
  -- trigger runs before the row it is validating is actually rewritten.
  IF EXISTS (
    SELECT 1 FROM role_grant
     WHERE account_id = NEW.account_id
       AND role = (CASE NEW.role WHEN 'buyer' THEN 'seller' ELSE 'buyer' END)
       AND revoked_at IS NULL
       AND id IS DISTINCT FROM NEW.id
  ) THEN
    RAISE EXCEPTION
      'account % already holds an active % grant; buyer and seller are mutually exclusive (ruling D-C59)',
      NEW.account_id, (CASE NEW.role WHEN 'buyer' THEN 'seller' ELSE 'buyer' END)
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS role_grant_exclusivity ON role_grant;
CREATE TRIGGER role_grant_exclusivity
  BEFORE INSERT OR UPDATE ON role_grant
  FOR EACH ROW EXECUTE FUNCTION role_grant_enforce_exclusivity();
