-- Seller listing lifecycle (spec 2026-09-08 D12; controller amendment A-SL33 (1), fix round 1 on
-- the SL8 review's Critical finding).
--
-- `listing_publishable_ck` (030) requires `state`, `market` and `area` because `serialise` and the
-- buyer detail dereference them unconditionally. It missed a fourth: `frontend/src/logic.js` calls
-- `p.sqft.toLocaleString()` with no guard at every site Browse renders a practice from — the
-- desktop map's results list, the mobile list, and the detail screen (`:673`, `:677`, `:1349`,
-- `:1392`, `:1654`) — so a listing published with no floor area is not a blank field, it is a blank
-- app: `null.toLocaleString()` throws, and that throw happens on the very next render of ANY
-- screen holding that listing in its practice array, not merely the listing's own card. Nothing
-- before this migration required `sqft` for a published row: not `listing_submittable_ck` (030,
-- which submit's own completeness check mirrors), not `decide_listing`'s first-publish gate
-- (`app/api/admin_listings.py`), and no CHECK at all — `sqft` (016) is a plain nullable `integer`.
--
-- Migration numbers: 030-033 are this plan's and are spent (`docs/superpowers/plans/2026-09-08-
-- seller-listing-lifecycle.md`'s own note on 032); 034 is the next free number in this range.
--
-- REPORTS AND REFUSES rather than silently applying a constraint an existing row already violates
-- (the same care 030 itself did not need, because 030 ran before any real listing existed to
-- violate anything — this one runs on a table Task SL1-SL8 have been writing to for days). Any
-- published row with no floor area today would otherwise have this migration succeed while
-- leaving a row that already crashes Browse in place, silently, forever (the CHECK only stops the
-- NEXT write, not the row that is already broken) — so the count is asked FIRST, and a non-zero
-- answer aborts the whole migration with the ids named, before either statement below runs.
--
-- No `DECLARE` section (tests/test_migrate.py::test_migration_files_never_manage_their_own_
-- transaction's own regex matches a `begin`/`commit`/`rollback` keyword right after a `;`, which a
-- `DECLARE … ;` block's own closing semicolon would trip — `014_audit_log.sql`'s function body
-- avoids the same trap by putting `BEGIN` right after `AS $$` instead, which is exactly what this
-- block does too): the count and the ids are each a subquery inline in the `RAISE EXCEPTION`
-- itself.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM listing WHERE status = 'published' AND sqft IS NULL) THEN
    RAISE EXCEPTION 'migration 034 refused: % published listing(s) with no sqft already violate the'
      ' widened listing_publishable_ck (ids: %) - fix or unpublish these rows before re-running',
      (SELECT count(*) FROM listing WHERE status = 'published' AND sqft IS NULL),
      (SELECT string_agg(id::text, ', ') FROM listing WHERE status = 'published' AND sqft IS NULL);
  END IF;
END $$;

-- Widened, not weakened: the three existing fields are unchanged, `sqft` joins them.
ALTER TABLE listing DROP CONSTRAINT listing_publishable_ck;
ALTER TABLE listing ADD  CONSTRAINT listing_publishable_ck
  CHECK (status <> 'published'
         OR (state IS NOT NULL AND market IS NOT NULL AND area IS NOT NULL AND sqft IS NOT NULL));
