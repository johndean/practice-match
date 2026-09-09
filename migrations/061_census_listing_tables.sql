-- §13 listing-dependent tables, verbatim, plus the licence-gate trigger (§1) and
-- market_metric.inputs (plan decision D9).
CREATE TABLE practice_location (
  listing_id uuid PRIMARY KEY REFERENCES listing(id) ON DELETE CASCADE,
  address_hash text NOT NULL,
  point geometry(Point, 4269),
  tract_geoid text,
  county_geoid text,
  place_geoid text,
  zcta_geoid text,
  cbsa_geoid text,
  geo_precision text NOT NULL CHECK (geo_precision IN ('rooftop','tract','zcta','place','county')),
  geocoded_at timestamptz NOT NULL,
  geocoder_vintage text NOT NULL
);
CREATE INDEX practice_location_point_gix ON practice_location USING gist (point);

CREATE TABLE practice_catchment (
  listing_id uuid NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  band text NOT NULL CHECK (band IN ('drive_10','drive_20')),
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL DEFAULT '140',
  vintage text NOT NULL,
  overlap_frac numeric(6,5) NOT NULL CHECK (overlap_frac > 0 AND overlap_frac <= 1),
  method text NOT NULL, -- 'euclidean_buffer_v1' | 'isochrone_v2'
  PRIMARY KEY (listing_id, band, geo_id, vintage)
);

CREATE TABLE market_metric (
  listing_id uuid NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  band text NOT NULL,
  metric_key text NOT NULL,
  vintage text NOT NULL,
  value_num numeric,
  value_text text,
  unit text NOT NULL, -- 'count' | 'usd' | 'pct' | 'ratio' | 'score'
  is_derived boolean NOT NULL DEFAULT false,
  formula_version text,
  moe numeric,
  suppressed boolean NOT NULL DEFAULT false,
  suppress_reason text,
  source_dataset text NOT NULL REFERENCES dataset_registry(dataset_key),
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (listing_id, band, metric_key, vintage)
);
CREATE INDEX market_metric_lookup_idx ON market_metric (listing_id, band, vintage);
ALTER TABLE market_metric ADD COLUMN inputs jsonb;  -- D9: {"acs5":"2019–2023","cbp":"2022"}

-- §1 "Licensing gates production … enforced by a foreign key to license_status = 'cleared'":
-- a plain FK cannot express the predicate, so the gate is a trigger. Existing rows survive a
-- status flip (the API hides them within 60 s via app/census/gate.py); new writes are refused.
--
-- No DECLARE section: a `DECLARE x text; BEGIN` block reads, to `tests/test_migrate.py`'s
-- `test_migration_files_never_manage_their_own_transaction` regex, exactly like a migration
-- managing its own transaction (`;` immediately before `BEGIN`) — that test's own docstring
-- names 014_audit_log.sql's DECLARE-free trigger as the shape it expects. The status is looked
-- up twice (insert/update on market_metric is rare) rather than held in a local variable, so
-- the function body opens straight on `$$\nBEGIN` as 014's does.
CREATE OR REPLACE FUNCTION market_metric_license_gate() RETURNS trigger AS $$
BEGIN
  IF (SELECT license_status FROM dataset_registry WHERE dataset_key = NEW.source_dataset) IS DISTINCT FROM 'cleared' THEN
    RAISE EXCEPTION 'market_metric write refused: dataset % is % (licence gate)', NEW.source_dataset,
      COALESCE((SELECT license_status FROM dataset_registry WHERE dataset_key = NEW.source_dataset), 'unknown');
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER market_metric_license_gate BEFORE INSERT OR UPDATE ON market_metric
  FOR EACH ROW EXECUTE FUNCTION market_metric_license_gate();
