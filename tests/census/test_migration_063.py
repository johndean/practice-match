"""Migration 063 (A-C24 (2), the whole-phase review): `market_metric.band` carried no constraint
at all, where its sibling `practice_catchment.band` (061) has `CHECK (band IN ('drive_10',
'drive_20'))` -- a constraint that exists on one table and not its twin is the one that eventually
admits a bad value. `060`/`061`/`062` are frozen (A-C15 (4)/A-C16); this is a NEW migration in the
phase's own range, never an edit to one of them.

`market_metric` additionally uses `'place'` (the design's city-level figures -- a catchment IS a
drive-time ring, so `practice_catchment` never has a `'place'` row at all), so its check names all
three bands `app.census.materialize.BANDS`/`app.api.market.BANDS` already agree on, not merely the
two `practice_catchment` admits."""
import psycopg2
import pytest

from tests.census.listing_fixtures import make_listing


def test_market_metric_refuses_a_band_outside_the_three_the_application_uses(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)"
            " VALUES (%s, 'bogus_band', 'population', '2019\u20132023', 1, 'count', 'acs5', now())",
            (lid,),
        )


def test_market_metric_still_accepts_each_of_its_three_real_bands(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur:
        for band in ("place", "drive_10", "drive_20"):
            cur.execute(
                "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)"
                " VALUES (%s, %s, 'population', '2019\u20132023', 1, 'count', 'acs5', now())",
                (lid, band),
            )
        cur.execute("SELECT count(*) FROM market_metric WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 3
