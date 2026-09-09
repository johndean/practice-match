-- Phase-review finding (A-C24 (2)): `market_metric.band` carried no constraint at all, where its
-- sibling `practice_catchment.band` (061) has `CHECK (band IN ('drive_10','drive_20'))`. A
-- constraint that exists on one table and not its twin is the one that eventually admits a bad
-- value -- `market_metric` additionally uses `'place'` (the design's city-level figures, which
-- `practice_catchment` has no row for at all, since a catchment IS a drive-time ring), so its
-- check names all three bands `app.census.materialize.BANDS`/`app.api.market.BANDS` already agree
-- on, not just the two `practice_catchment` admits.
--
-- `060`/`061`/`062` are frozen (A-C15 (4)/A-C16): this is a NEW migration in the phase's own range,
-- never an edit to one of them.
ALTER TABLE market_metric
  ADD CONSTRAINT market_metric_band_check CHECK (band IN ('place', 'drive_10', 'drive_20'));
