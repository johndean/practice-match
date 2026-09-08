-- Seller listing lifecycle (spec 2026-09-08; D14, D15, D18, D19). A seller's uploaded photographs
-- and documents.
--
-- The BYTES live in object storage under `listings/{listing_id}/…` (D14); this table is the row
-- that says which object, whose, what kind and how big — so every read is a live permission
-- decision against the listing's status and the caller's principal rather than a signed URL that
-- outlives the decision that minted it (D15).
--
-- There is deliberately NO `position` column. `listing.photos` stays the ordered array of strings
-- it already is, and it remains the single home of photo ORDER (D15 reason 3): for a source='seed'
-- row an entry is a relative path under PHOTOS_ROOT, for a seller row it is an asset id. Two homes
-- for one fact is how orders drift.
CREATE TABLE listing_asset (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id   uuid        NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  -- 'photo' plus D18's four document kinds. The approved step 6 has no kind picker, so the wizard
  -- sends 'other'; the API takes `kind` today so that Rev 3's picker needs no API change.
  kind         text        NOT NULL
                           CHECK (kind IN ('photo','floor_plan','financials','equipment','other')),
  -- What the wizard's step-6 tile shows under the badge: the uploaded filename for a seller upload
  -- (D26). Never a path — the path is `storage_key`.
  name         text        NOT NULL,
  content_type text        NOT NULL,
  byte_size    bigint      NOT NULL,
  -- Of the STORED bytes: a photograph's re-encoded WebP, a document's own bytes.
  sha256       text        NOT NULL,
  -- `listings/{listing_id}/photos/{id}.webp` or `listings/{listing_id}/documents/{id}{ext}`.
  -- UNIQUE because put_immutable never overwrites: one object, one row, and a delete that could
  -- orphan a live asset is impossible.
  storage_key  text        NOT NULL UNIQUE,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- The wizard's step-6 read and the asset list on every draft GET.
CREATE INDEX listing_asset_listing_idx ON listing_asset (listing_id, created_at);
-- The document lock's lookup: this listing's documents, or this listing's photographs.
CREATE INDEX listing_asset_kind_idx    ON listing_asset (listing_id, kind);
