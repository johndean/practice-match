import psycopg2
import pytest

from tests.census.listing_fixtures import make_listing


def test_market_metric_refuses_datasets_that_are_not_cleared(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)
                       VALUES (%s, 'drive_10', 'population', '2019\u20132023', 1, 'count', 'acs5', now())""", (lid,))
        with pytest.raises(psycopg2.errors.RaiseException) as e:
            cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)
                           VALUES (%s, 'drive_10', 'pet_households_licensed', 'n/a', 1, 'count', 'pet_ownership', now())""", (lid,))
        assert "pet_ownership" in str(e.value) and "blocked" in str(e.value)


def test_status_flip_blocks_future_writes_but_keeps_rows(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)
                       VALUES (%s, 'drive_10', 'population', '2019\u20132023', 1, 'count', 'acs5', now())""", (lid,))
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5'")
        with pytest.raises(psycopg2.errors.RaiseException):
            cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)
                           VALUES (%s, 'drive_20', 'population', '2019\u20132023', 1, 'count', 'acs5', now())""", (lid,))
        cur.execute("SELECT count(*) FROM market_metric WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 1  # existing rows stay; the API hides them via the gate (A9)


def test_practice_location_precision_is_constrained_and_cascades(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("""INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoded_at, geocoder_vintage)
                           VALUES (%s, 'h', 'approximate', now(), 'Current_Current')""", (lid,))
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoded_at, geocoder_vintage)
                       VALUES (%s, 'h', 'rooftop', now(), 'Current_Current')""", (lid,))
        cur.execute("DELETE FROM listing WHERE id=%s", (lid,))
        cur.execute("SELECT count(*) FROM practice_location WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 0


def test_catchment_overlap_bounds(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("""INSERT INTO practice_catchment (listing_id, band, geo_id, vintage, overlap_frac, method)
                       VALUES (%s, 'drive_10', '48453000101', '2023', 1.5, 'euclidean_buffer_v1')""", (lid,))
