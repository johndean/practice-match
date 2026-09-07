-- Task I5, fix round 1 (F9). `GET /api/admin/users` is budgeted at <= 150 ms (spec §6) and had no
-- index behind either half of its query:
--
--   * it sorts the whole `account` table (`ORDER BY a.created_at DESC, a.id DESC`, now also the
--     keyset the cursor pages on), and nothing indexed `account(created_at)`;
--   * its `LEFT JOIN LATERAL (SELECT * FROM application WHERE account_id = a.id
--     ORDER BY submitted_at DESC LIMIT 1)` had nothing to use either — Postgres does not index a
--     foreign key, and migrations/011 creates only `application_queue_idx (status, submitted_at)`
--     — so it cost one sequential scan of `application` per account row.
--
-- The column order matches the query's ORDER BY in both cases, so each index serves the sort as
-- well as the lookup.
CREATE INDEX account_listing_idx ON account (created_at DESC, id DESC);
CREATE INDEX application_account_idx ON application (account_id, submitted_at DESC);
