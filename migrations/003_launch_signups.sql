-- Wave 2a Task I5d (John, 2026-09-08): the Admin "Launch sign-ups" capability.
--
-- `002_interest_signup.sql` is applied on production and its sha256 is in that database's ledger,
-- so it is never edited (scripts/migrate.py exits 4 on a changed applied file). This file is the
-- amendment. It is numbered 003 because the Census plan's D14 reserves 003-009 for Platform-level
-- migrations with no dependency on later tables, and an ALTER of a 002 table is precisely that;
-- the runner applies files in name order and skips what the ledger holds, so landing after
-- 010-015 is ordinary.
--
-- No BEGIN/COMMIT (the runner wraps this file and its ledger row in one transaction) and no
-- CREATE INDEX CONCURRENTLY (the runner cannot run a statement outside a transaction). The table
-- is a launch-notification list of a few thousand rows, so the brief ACCESS EXCLUSIVE lock the two
-- CREATE INDEX statements take is measured in milliseconds.

-- Exactly-once for the launch mail. NULL means "not yet mailed", which is what every row that
-- already exists must read as: a DEFAULT here would silently mark the whole existing list as
-- already told, and nobody who signed up before today would ever get the message they were
-- promised. Stamped in the SAME transaction as the email_outbox row, so a crash can neither mail
-- twice nor mark a row mailed without its outbox row.
ALTER TABLE interest_signup ADD COLUMN IF NOT EXISTS launch_mailed_at timestamptz;

-- The admin list's ORDER BY and the keyset the cursor pages on — the same column order as
-- `account_listing_idx` in 015, for the same reason: the index serves the sort as well as the
-- lookup, and a keyset cursor of (created_at, id) must not fall back to a sort of the whole table.
CREATE INDEX IF NOT EXISTS interest_signup_listing_idx ON interest_signup (created_at DESC, id DESC);

-- The launch mail's own scan: `WHERE launch_mailed_at IS NULL ORDER BY id LIMIT n FOR UPDATE`.
-- Partial, because the interesting set shrinks to zero as the send completes and a full index on
-- a column that is NULL for every row would be all of it.
CREATE INDEX IF NOT EXISTS interest_signup_unmailed_idx ON interest_signup (id) WHERE launch_mailed_at IS NULL;
