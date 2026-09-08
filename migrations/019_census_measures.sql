-- §13 measure tables, long format.
CREATE TABLE acs_measure (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,
  vintage text NOT NULL,
  variable text NOT NULL, -- e.g. B19013_001E
  estimate numeric,
  moe numeric,
  ingest_run_id bigint NOT NULL REFERENCES ingest_run(id),
  PRIMARY KEY (geo_id, summary_level, vintage, variable)
);
CREATE INDEX acs_measure_var_idx ON acs_measure (variable, vintage);

CREATE TABLE cbp_industry (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,
  vintage text NOT NULL,
  naics_code text NOT NULL, -- '541940'
  establishments integer,
  employment integer,
  annual_payroll_k bigint,
  flag text, -- Census noise/suppression flag, verbatim
  ingest_run_id bigint NOT NULL REFERENCES ingest_run(id),
  PRIMARY KEY (geo_id, summary_level, vintage, naics_code)
);

CREATE TABLE qwi_measure (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,
  naics_code text NOT NULL, -- '5419'
  year smallint NOT NULL,
  quarter smallint NOT NULL,
  avg_monthly_earnings integer,
  sector_employment integer,
  sector_hires integer,
  ingest_run_id bigint NOT NULL REFERENCES ingest_run(id),
  PRIMARY KEY (geo_id, summary_level, naics_code, year, quarter)
);

-- BDS is not in the spec's DDL but is in its dataset register and variable map (FIRM, ESTABS_ENTRY).
CREATE TABLE bds_measure (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,
  vintage text NOT NULL, -- BDS year, e.g. '2022'
  naics_code text NOT NULL, -- '54'
  firms integer,
  estab_entry integer,
  ingest_run_id bigint NOT NULL REFERENCES ingest_run(id),
  PRIMARY KEY (geo_id, summary_level, vintage, naics_code)
);
