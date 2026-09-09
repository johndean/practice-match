-- §10 geocode result cache: sha256(normalized_address) → payload, 365 days.
CREATE TABLE geocode_cache (
  address_hash text PRIMARY KEY,
  normalized_address text NOT NULL,
  payload jsonb NOT NULL,
  geocoded_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL DEFAULT now() + interval '365 days'
);
-- §11 "flag for staff": listings whose location fell back below rooftop precision.
CREATE TABLE geocode_review (
  id bigserial PRIMARY KEY,
  listing_id uuid NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);
