-- Image identifiability protection (spec 2026-09-09, D-IDP-14). John's directive 7: "The listing
-- must have a single authoritative setting ... Default: NOT_SHOW. The safest privacy state is the
-- default." Written by exactly one path: the owner's step-7 PATCH (app/api/seller_listings.py).
ALTER TABLE listing ADD COLUMN identifiable_content_visibility text NOT NULL DEFAULT 'NOT_SHOW'
  CHECK (identifiable_content_visibility IN ('SHOW','NOT_SHOW'));
