-- One privacy record per photograph (directive 6 and 18; spec 2026-09-09 C.3). Documents carry no
-- row (D19): they are owner-and-staff only today and are out of redaction scope.
CREATE TABLE listing_asset_privacy (
  asset_id                      uuid PRIMARY KEY REFERENCES listing_asset(id) ON DELETE CASCADE,
  listing_id                    uuid NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  processing_status             text NOT NULL DEFAULT 'UPLOADED'
    CHECK (processing_status IN ('UPLOADED','PROCESSING','SCANNED','REDACTION_GENERATED','READY_FOR_REVIEW',
                                 'SELLER_CONFIRMED','PUBLISHED','PROCESSING_FAILED','REDACTION_FAILED',
                                 'REVIEW_REQUIRED','REPROCESS_REQUIRED')),
  processing_version            integer NOT NULL,
  attempts                      integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  last_error                    text,                                   -- a reason code, never bytes
  original_storage_key          text NOT NULL UNIQUE,                   -- listings/{l}/photos/{a}/original.{ext}
  redacted_storage_key          text UNIQUE,                            -- listings/{l}/photos/{a}/redacted.webp
  redacted_sha256               text,
  confirmed_sha256              text,                                   -- the derivative the confirmation covers
  ocr                           jsonb NOT NULL DEFAULT '{}'::jsonb,
  identity_matches              jsonb NOT NULL DEFAULT '[]'::jsonb,
  vision                        jsonb NOT NULL DEFAULT '{"status": "pending"}'::jsonb,
  detected_regions              jsonb NOT NULL DEFAULT '[]'::jsonb,
  redaction_regions             jsonb NOT NULL DEFAULT '[]'::jsonb,
  detection_at                  timestamptz,
  seller_review_status          text NOT NULL DEFAULT 'pending'
    CHECK (seller_review_status IN ('pending','looks_good','edited')),
  seller_confirmed              boolean NOT NULL DEFAULT false,
  seller_confirmed_at           timestamptz,
  seller_confirmation_account_id uuid REFERENCES account(id) ON DELETE SET NULL,
  buyer_visible                 boolean NOT NULL DEFAULT false,
  final_privacy_state           text CHECK (final_privacy_state IN ('SHOW','NOT_SHOW')),
  -- Staleness is a FLAG, never a state (spec C.4, D-IDP-16): a ready row goes on serving its
  -- current derivative while the in-place re-run replaces it, so a processing-version bump can
  -- never blank a published listing.
  reprocess_reason              text CHECK (reprocess_reason IN ('VERSION','IDENTITY_CHANGED','OPERATOR')),
  reprocess_requested_at        timestamptz,
  reprocessed_at                timestamptz,
  created_at                    timestamptz NOT NULL DEFAULT now(),
  updated_at                    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT lap_confirmed_ck   CHECK ((NOT seller_confirmed)
                                       OR (seller_confirmed_at IS NOT NULL AND final_privacy_state IS NOT NULL
                                           AND confirmed_sha256 IS NOT NULL AND confirmed_sha256 = redacted_sha256)),
  CONSTRAINT lap_stale_ck       CHECK ((reprocess_reason IS NULL) = (reprocess_requested_at IS NULL)),
  CONSTRAINT lap_status_confirmed_ck CHECK (processing_status <> 'SELLER_CONFIRMED' OR seller_confirmed),
  CONSTRAINT lap_visible_ready_ck CHECK ((NOT buyer_visible)
                                       OR processing_status IN ('READY_FOR_REVIEW','SELLER_CONFIRMED','PUBLISHED')),
  CONSTRAINT lap_ready_has_derivative_ck CHECK (
    processing_status NOT IN ('REDACTION_GENERATED','READY_FOR_REVIEW','SELLER_CONFIRMED','PUBLISHED')
    OR redacted_storage_key IS NOT NULL),
  CONSTRAINT lap_never_the_original_ck CHECK (redacted_storage_key IS DISTINCT FROM original_storage_key)
);
CREATE INDEX listing_asset_privacy_listing_idx ON listing_asset_privacy (listing_id, processing_status);
CREATE INDEX listing_asset_privacy_sweep_idx   ON listing_asset_privacy (processing_status, updated_at);
