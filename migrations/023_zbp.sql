-- ZIP Code Business Patterns — the community-level competition source (plan D11). ZIP codes are
-- stored as summary_level '860' (ZCTA) geo_ids; the ZIP≈ZCTA approximation is labelled in the UI.
CREATE TABLE zbp_industry (
  geo_id text NOT NULL,            -- 5-digit ZIP
  summary_level char(3) NOT NULL DEFAULT '860',
  vintage text NOT NULL,
  naics_code text NOT NULL,        -- '541940' | '812910' | '459910'
  establishments integer,
  ingest_run_id bigint NOT NULL REFERENCES ingest_run(id),
  PRIMARY KEY (geo_id, summary_level, vintage, naics_code)
);
