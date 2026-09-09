-- §13 geo_area: Census geographies with geometry, one row per GEOID per vintage.
CREATE TABLE geo_area (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL, -- 140 tract, 150 bg, 160 place, 860 zcta, 050 county, 310 cbsa, 040 state, 010 nation
  vintage text NOT NULL,
  name text NOT NULL,
  state_fips char(2),
  county_fips char(3),
  parent_geo_id text,
  land_area_m2 bigint,
  geom geometry(MultiPolygon, 4269),
  centroid geometry(Point, 4269),
  PRIMARY KEY (geo_id, summary_level, vintage)
);
CREATE INDEX geo_area_geom_gix ON geo_area USING gist (geom);
CREATE INDEX geo_area_level_idx ON geo_area (summary_level, vintage);
