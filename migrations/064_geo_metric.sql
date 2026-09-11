-- Neighbourhood shading (spec 2026-09-10; D-C34, D-C35). One row per geography per metric per
-- vintage, at the geography the metric is honest at -- ZCTA '860' for income, place '160' for
-- growth, county '050' for payroll per establishment. `market_metric`'s sibling: same column
-- vocabulary, same licence gate, a different subject. `market_metric` answers "what is the market
-- around THIS PRACTICE"; this answers "what is true of THIS ZIP CODE". A polygon has no listing,
-- and shading a metro's ZCTAs off market_metric would mean one row per listing per polygon,
-- recomputed whenever a listing moved.
--
-- `064`, not `091`: D14 assigns SP3-B the `060`+ range (060/061/062/063 are taken) and `090`-`099`
-- is main's platform range (A-C10). The ledger runner applies each file exactly once and refuses
-- only files whose bytes no longer match a recorded checksum, so sorting before an already-applied
-- `090` is not a problem. Depends on `dataset_registry` (017) and nothing later.
CREATE TABLE geo_metric (
  geo_id text NOT NULL,
  summary_level char(3) NOT NULL,          -- '860' zcta | '160' place | '050' county (018's own comment)
  vintage text NOT NULL,                   -- the VALUE's vintage: '2019–2023' (acs5, en dash) | '2022' (cbp)
  metric_key text NOT NULL,                -- 'median_hh_income' | 'population_growth_pct' | 'revenue_per_establishment'
  value_num numeric,
  unit text NOT NULL,                      -- 'usd' | 'pct' -- market_metric's own vocabulary
  is_derived boolean NOT NULL DEFAULT false,
  formula_version text,
  moe numeric,
  suppressed boolean NOT NULL DEFAULT false,
  suppress_reason text,                    -- 'no_moe' | 'high_moe' | 'input_suppressed' | 'source_flag'
  inputs jsonb,                            -- D9's shape: {"acs5":"2019–2023","geo_level":"zcta"}
  source_dataset text NOT NULL REFERENCES dataset_registry(dataset_key),
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (geo_id, summary_level, vintage, metric_key)
);
-- The read path's only access pattern: one layer, one geography level, one vintage, joined to
-- geo_area by geo_id. Without this it is a sequential scan of every geography in six states. A
-- PARTIAL index per summary level measured 25.0 ms against this one's 49.8 ms on an Austin z11
-- viewport; it is not here because at ~130 ZCTAs the 25 ms is not the cost that matters and three
-- indexes on a table with one access pattern is three things to keep in step. It is the first
-- thing to add if this query ever appears in a slow log.
CREATE INDEX geo_metric_layer_idx ON geo_metric (summary_level, metric_key, vintage);

-- The twin of market_metric_license_gate (061:59-68, body replaced at 062:22-28). Same reason: a
-- table that will accept a blocked dataset's values is one code path away from shading them. The
-- read path filters live and gate.py expires a cached answer inside 60 s, but neither stops a
-- nightly writer from filling the table with figures nobody may show -- and a polygon layer is
-- exactly where that would go unnoticed, because a map has no per-figure attribution line to look
-- wrong. IS DISTINCT FROM also catches a missing registry row (NULL): the trigger is BEFORE, so it
-- runs before the foreign key's own AFTER-row check and is the refusal an unknown key actually
-- meets.
--
-- No DECLARE section, deliberately: `tests/test_migrate.py::
-- test_migration_files_never_manage_their_own_transaction` treats `; BEGIN` as a self-managed
-- transaction, and 061 and 062 both carry that note. The message names only the dataset key,
-- following 062's own correction -- 061 read license_status twice and a concurrent registry update
-- between the two reads could name a stale status.
CREATE OR REPLACE FUNCTION geo_metric_license_gate() RETURNS trigger AS $$
BEGIN
  IF (SELECT license_status FROM dataset_registry WHERE dataset_key = NEW.source_dataset) IS DISTINCT FROM 'cleared' THEN
    RAISE EXCEPTION 'geo_metric write refused: dataset % is not licence-cleared (licence gate)', NEW.source_dataset;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER geo_metric_license_gate BEFORE INSERT OR UPDATE ON geo_metric
  FOR EACH ROW EXECUTE FUNCTION geo_metric_license_gate();
