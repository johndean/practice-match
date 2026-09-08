-- Census & Market Data Source Specification v1.0 §13 — provenance and registry.
-- Created first: other tables reference ingest_run.
CREATE TABLE ingest_run (
  id bigserial PRIMARY KEY,
  dataset_key text NOT NULL,
  vintage text NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  status text NOT NULL CHECK (status IN ('running','succeeded','failed','aborted')),
  rows_written bigint DEFAULT 0,
  request_count integer DEFAULT 0,
  raw_payload_uri text,
  error_detail text
);

-- Every external source, and whether it may be used at all.
CREATE TABLE dataset_registry (
  dataset_key text PRIMARY KEY,
  display_name text NOT NULL,
  api_dataset_id text,
  base_url text NOT NULL,
  vintage text NOT NULL,
  naics_param text,
  refresh_cadence text NOT NULL,
  license_status text NOT NULL CHECK (license_status IN ('cleared','unresolved','blocked')),
  license_name text,
  license_url text,
  attribution_text text NOT NULL,
  last_verified_at timestamptz,
  notes text
);

ALTER TABLE ingest_run
  ADD CONSTRAINT ingest_run_dataset_fk
  FOREIGN KEY (dataset_key) REFERENCES dataset_registry(dataset_key);

-- Which vintage the app is allowed to read. Flipped only after QA.
CREATE TABLE active_vintage (
  dataset_key text PRIMARY KEY REFERENCES dataset_registry(dataset_key),
  vintage text NOT NULL,
  activated_at timestamptz NOT NULL,
  activated_by text NOT NULL
);

-- States whose geographies and ACS rows we load (plan decision D4; auto-extended by geocoding).
CREATE TABLE market_state (
  state_fips char(2) PRIMARY KEY,
  name text NOT NULL,
  added_at timestamptz NOT NULL DEFAULT now(),
  reason text NOT NULL
);
INSERT INTO market_state (state_fips, name, reason) VALUES
  ('48','Texas','design market Austin–Round Rock–San Marcos (12420)'),
  ('06','California','design market Sacramento–Roseville–Folsom (40900)'),
  ('12','Florida','design market Orlando–Kissimmee–Sanford (36740)'),
  ('13','Georgia','design market Atlanta–Sandy Springs–Roswell (12060)'),
  ('36','New York','A-C0 ¶10 / A-C1 ¶5 — seeds/hospitals.json demo markets (New York)'),
  ('08','Colorado','A-C0 ¶10 / A-C1 ¶5 — seeds/hospitals.json demo market (Denver)');

-- §2 dataset register, verbatim. Rows marked unresolved/blocked must not ship (§2, §12).
INSERT INTO dataset_registry
  (dataset_key, display_name, api_dataset_id, base_url, vintage, naics_param, refresh_cadence, license_status, license_name, license_url, attribution_text, notes) VALUES
  ('acs5','ACS 5-Year Detailed Tables','2023/acs/acs5','https://api.census.gov/data','2019–2023',NULL,'Annual (Dec)','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023',NULL),
  ('acs5_subject','ACS 5-Year Subject Tables','2023/acs/acs5/subject','https://api.census.gov/data','2019–2023',NULL,'Annual (Dec)','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, American Community Survey 5-Year Subject Tables, 2019–2023',NULL),
  ('acs5_prior','ACS 5-Year, baseline for growth','2018/acs/acs5','https://api.census.gov/data','2014–2018',NULL,'Static','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2014–2018','Growth baseline only'),
  ('cbp','County Business Patterns','2022/cbp','https://api.census.gov/data','2022','NAICS2017','Annual (Apr)','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, County Business Patterns, 2022','Parameter renames to NAICS2022 with the 2023+ releases'),
  ('zbp','ZIP Code Business Patterns','2022/zbp','https://api.census.gov/data','2022','NAICS2017','Annual (Apr)','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, ZIP Code Business Patterns, 2022','Plan decision D11 — community-level competition counts; ZIP codes treated as ZCTAs (approximation labelled in the UI). Confirm 2022/zbp exists at api.census.gov/data.html; fall back to 2021/zbp.'),
  ('qwi','Quarterly Workforce Indicators','timeseries/qwi/sa','https://api.census.gov/data','latest quarter',NULL,'Quarterly','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, Quarterly Workforce Indicators',NULL),
  ('bds','Business Dynamics Statistics','timeseries/bds','https://api.census.gov/data','latest',NULL,'Annual','cleared','Public domain','https://www.census.gov/data/developers/about/terms-of-service.html','Source: U.S. Census Bureau, Business Dynamics Statistics',NULL),
  ('geocoder','Census Geocoder (geographies)',NULL,'https://geocoding.geo.census.gov/geocoder','Current_Current',NULL,'On write','cleared','Public domain','https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html','Geocoding: U.S. Census Bureau Geocoder',NULL),
  ('tiger_cb','TIGER Cartographic Boundary files','TIGER2023/cb_2023_*','https://www2.census.gov/geo/tiger/GENZ2023/shp','2023',NULL,'Annual','cleared','Public domain','https://www.census.gov/programs-surveys/geography/technical-documentation/naming-convention/cartographic-boundary-file.html','Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023',NULL),
  ('aies','Annual Integrated Economic Survey',NULL,'https://api.census.gov/data','TBD',NULL,'Annual','unresolved','Verify ID',NULL,'Source: U.S. Census Bureau, Annual Integrated Economic Survey','Confirm dataset identifier and geography availability before any revenue-benchmark layer is promised (§15)'),
  ('osm_tiles','Street basemap tiles (CARTO, OSM data)',NULL,'https://basemaps.cartocdn.com/light_all','live',NULL,'live','cleared','ODbL 1.0','https://www.openstreetmap.org/copyright','© OpenStreetMap contributors © CARTO','John''s ruling (A-C1, this plan''s "Basemap licence — one decision record"): CARTO is the basemap for the Census analytical / market-data map layer; the approved visual design keeps Esri tiles ("Tiles © Esri") where the design requires it, but Census analytical rendering must not depend on an Esri-only implementation'),
  ('imagery','Satellite basemap',NULL,'vendor TBD','live',NULL,'live','unresolved',NULL,NULL,'Imagery attribution pending licence','Satellite toggle stays behind a feature flag until a written licence names commercial web display'),
  ('pet_ownership','Pet ownership incidence (commercial)',NULL,'licensed feed','n/a',NULL,'n/a','blocked',NULL,NULL,'Pet-ownership incidence (licensed) — not in use','Ship only the ACS-derived estimate (rate 0.57) until a licence is signed'),
  ('practice_locations','Third-party practice location data',NULL,'n/a','n/a',NULL,'n/a','blocked',NULL,NULL,'Practice locations (third party) — not in use','Spec §12: purchased or scraped veterinary location lists are out of scope for V1 (undocumented provenance). Includes the 2017 Google Places export Report_Hospital_Competitor_All_US_ZipCode_FULL.csv (D15): Google Maps Platform Terms §3.2.3 and SST §14 forbid storing or rendering its content. Competition counts come from Census establishment totals only.'),
  ('google_places_aggregate','Google Places Aggregate API (competition freshness signal)',NULL,'https://areainsights.googleapis.com/v1','live',NULL,'Monthly','unresolved','Google Maps Platform Terms + Service Specific Terms §13','https://cloud.google.com/maps-platform/terms/maps-service-terms','Competition freshness derived from Google Places counts (Google)','D17 / Task C1. The POI count is held in memory only (SST §13.2, 30-day ceiling); persisted values are level_live and diverges (SST §13.1 Customer Values). Clear only after VIN Foundation counsel accepts SST §13 and a Google Cloud billing account exists. Key GOOGLE_MAPS_API_KEY on the worker service only.'),
  ('overture_places','Overture Maps Places (competitor points)',NULL,'s3://overturemaps-us-west-2/release','monthly release',NULL,'Monthly','unresolved','CDLA-Permissive-2.0 (Foursquare-sourced rows: Apache-2.0)','https://docs.overturemaps.org/attribution/','Practice locations: © Overture Maps Foundation contributors (CDLA-Permissive-2.0); portions © Foursquare (Apache-2.0)','D16 rank 1. Taxonomy entry veterinarian; per-feature sources[] and confidence retained. Clear after the VIN Foundation approves a competitor-points layer (Task C2).'),
  ('fsq_os_places','Foursquare OS Places (competitor points, alternate)',NULL,'https://huggingface.co/datasets/foursquare/fsq-os-places','monthly release',NULL,'Monthly','unresolved','Apache-2.0','https://opensource.foursquare.com/os-places/','Practice locations: Foursquare OS Places (Apache-2.0)','D16 rank 2; category label Veterinarian. Redundant with overture_places unless Overture stops carrying Foursquare rows.');
