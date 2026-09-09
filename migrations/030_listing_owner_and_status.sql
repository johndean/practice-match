-- Seller listing lifecycle (spec 2026-09-08; D2, D5, D10, D12, D20, D22).
--
-- The listing table was written for eighteen seeded hospitals, every one of them complete. It now
-- has to hold a SELLER'S OWN listing from the moment they click "Create a listing", which is a row
-- with a slug and nothing else, and to carry that row through draft -> in_review -> published with
-- paused, declined and terminal withdrawn beside it.
--
-- Migration numbers: the spec says "017". 017-019 were taken by the Census branch's Task A1 while
-- this spec was being written, and an applied migration is never renumbered — controller amendment
-- A-SL3. A-SL5 then moved this plan off 020/021 too, once those collided with the Census plan's own
-- reserved 020/023/060/061: this sub-project's migrations are 030 and 031, a range no other plan
-- claims.
--
-- Nothing here is destructive: three ADD COLUMNs, two CHECK swaps, six DROP NOT NULLs, two new
-- CHECKs, one index, and one backfill of the rows that already exist.

-- D5. Nullable: a production seed row belongs to the VIN Foundation, not to a person, and
-- `scripts/seed_listings.py --production` never assigns a demo persona (D25). ON DELETE SET NULL:
-- a withdrawn listing keeps its history for reporting after the account that made it is gone, and
-- who did what lives in audit_log, which carries no foreign key either.
ALTER TABLE listing ADD COLUMN seller_id uuid REFERENCES account(id) ON DELETE SET NULL;

-- D10 mapping 4. The approved step-5 select asks "Facility type" (Standalone / Strip or plaza /
-- Medical park / Other, logic.js:1178) and there was nowhere to put the answer. Nothing reads it
-- yet; dropping a seller's answer to an approved question on the floor is the opposite of "the UX
-- true".
ALTER TABLE listing ADD COLUMN facility_type text;

-- D20. The other two of the four disclosure flags. Sellers hide by default, exactly as
-- location_disclosed and name_disclosed do; the wizard's step-3 and step-7 switches are INVERTED
-- against these (`revBand` on means rev_disclosed false).
ALTER TABLE listing ADD COLUMN rev_disclosed      boolean NOT NULL DEFAULT false;
ALTER TABLE listing ADD COLUMN documents_disclosed boolean NOT NULL DEFAULT false;

-- D22, and the reason this is in the migration rather than in the seeder: every row that exists
-- when this file applies is one of the eighteen demo hospitals, which show everything (A-L5 already
-- set the other two flags true in seeds/hospitals.json). Without this line, applying 030 to QA
-- would blank eighteen revenue figures on the buyer detail until the next re-seed.
UPDATE listing SET rev_disclosed = true, documents_disclosed = true WHERE source = 'seed';

-- D2. `declined` is the sixth status: a reviewer's refusal that the seller may edit and re-submit.
ALTER TABLE listing DROP CONSTRAINT listing_status_check;
ALTER TABLE listing ADD  CONSTRAINT listing_status_check
  CHECK (status IN ('draft','in_review','published','paused','withdrawn','declined'));

-- D10 mapping 3. The approved step-1 select offers "Other" (logic.js:1174). An `Other` listing
-- matches only the Browse type filter's "Any", which is honest.
ALTER TABLE listing DROP CONSTRAINT listing_type_check;
ALTER TABLE listing ADD  CONSTRAINT listing_type_check
  CHECK (type IN ('Small animal','Mixed','Large animal','Emergency','Specialty','Other'));

-- D12. Six NOT NULLs a draft cannot satisfy. The approved step 2 collects a city and a ZIP and
-- nothing else, so `state`, `market` and `area` cannot come from the seller: `area` is derived from
-- the city on the step-2 PATCH and `state`/`market` are supplied by the reviewer at the first
-- publish (John's ruled default, spec §16 Q2).
ALTER TABLE listing ALTER COLUMN name   DROP NOT NULL;
ALTER TABLE listing ALTER COLUMN city   DROP NOT NULL;
ALTER TABLE listing ALTER COLUMN state  DROP NOT NULL;
ALTER TABLE listing ALTER COLUMN area   DROP NOT NULL;
ALTER TABLE listing ALTER COLUMN type   DROP NOT NULL;
ALTER TABLE listing ALTER COLUMN market DROP NOT NULL;

-- ...and what replaces them. The DATABASE guarantees serialise() never meets a null it cannot
-- render, rather than one code path promising it.
--
-- Submittable: everything the approved wizard's own client-side validation demands before step 8
-- (logic.js:1215-1217 — name and est; city and zip; price and either rev or the range option),
-- plus the type its step-1 select always has a value for. A draft may be empty; so may a withdrawn
-- listing, because withdrawing an abandoned draft is a legal move and terminal.
ALTER TABLE listing ADD CONSTRAINT listing_submittable_ck
  CHECK (status IN ('draft','withdrawn')
         OR (name IS NOT NULL AND city IS NOT NULL AND zip IS NOT NULL
             AND type IS NOT NULL AND est IS NOT NULL AND price IS NOT NULL));

-- Publishable: the three the buyer surface dereferences. `area` builds the anonymised name
-- (app/api/listings.py's anonymised_name), `market` is what the Browse filter pages on and what
-- `stateOf(market)` splits for the detail's state label (A12.8/A12.9), and `state` is the row's own.
ALTER TABLE listing ADD CONSTRAINT listing_publishable_ck
  CHECK (status <> 'published'
         OR (state IS NOT NULL AND market IS NOT NULL AND area IS NOT NULL));

-- D5. The seller dashboard's only query: this owner's listings, most recently touched first.
CREATE INDEX listing_owner_idx ON listing (seller_id, updated_at DESC);
