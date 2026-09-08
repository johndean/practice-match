def _cols(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position", (table,))
    return [r[0] for r in cur.fetchall()]


def test_registry_and_ledger_tables_match_spec_13(conn):
    with conn.cursor() as cur:
        assert _cols(cur, "ingest_run") == ["id", "dataset_key", "vintage", "started_at", "finished_at", "status",
                                            "rows_written", "request_count", "raw_payload_uri", "error_detail"]
        assert _cols(cur, "dataset_registry") == ["dataset_key", "display_name", "api_dataset_id", "base_url", "vintage",
                                                  "naics_param", "refresh_cadence", "license_status", "license_name",
                                                  "license_url", "attribution_text", "last_verified_at", "notes"]
        assert _cols(cur, "active_vintage") == ["dataset_key", "vintage", "activated_at", "activated_by"]
        cur.execute("SELECT conname FROM pg_constraint WHERE conname = 'ingest_run_dataset_fk'")
        assert cur.fetchone(), "spec §13 adds the ingest_run → dataset_registry FK after the registry exists"


def test_geo_area_has_geometry_and_gist_index(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT type, srid FROM geometry_columns WHERE f_table_name='geo_area' AND f_geometry_column='geom'")
        assert cur.fetchone() == ("MULTIPOLYGON", 4269)
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename='geo_area'")
        names = {r[0] for r in cur.fetchall()}
        assert {"geo_area_geom_gix", "geo_area_level_idx"} <= names


def test_measure_tables_have_spec_primary_keys(conn):
    with conn.cursor() as cur:
        for table, pk in [
            ("acs_measure", ["geo_id", "summary_level", "vintage", "variable"]),
            ("cbp_industry", ["geo_id", "summary_level", "vintage", "naics_code"]),
            ("qwi_measure", ["geo_id", "summary_level", "naics_code", "year", "quarter"]),
            ("bds_measure", ["geo_id", "summary_level", "vintage", "naics_code"]),
        ]:
            cur.execute("""
                SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass AND i.indisprimary ORDER BY array_position(i.indkey, a.attnum)""", (table,))
            assert [r[0] for r in cur.fetchall()] == pk, table


def test_license_status_is_constrained(conn):
    import psycopg2
    with conn.cursor() as cur, pytest_raises(psycopg2.errors.CheckViolation):
        cur.execute("""INSERT INTO dataset_registry (dataset_key, display_name, base_url, vintage, refresh_cadence,
                       license_status, attribution_text) VALUES ('x','x','x','x','x','maybe','x')""")


def test_market_state_seeds_all_six_demo_states(conn):
    # A-C0 ¶10 / A-C1 ¶5: CA, TX, FL, GA, NY, CO — seeds/hospitals.json has demo hospitals in all six.
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips FROM market_state")
        assert {r[0] for r in cur.fetchall()} == {"06", "08", "12", "13", "36", "48"}


def test_osm_tiles_note_records_johns_carto_decision_not_pending(conn):
    # Basemap licence — one decision record: John ruled CARTO for the Census analytical layer.
    with conn.cursor() as cur:
        cur.execute("SELECT notes FROM dataset_registry WHERE dataset_key = 'osm_tiles'")
        (notes,) = cur.fetchone()
        assert "CARTO" in notes
        assert "pending" not in notes


from contextlib import contextmanager

import pytest


@contextmanager
def pytest_raises(exc):
    with pytest.raises(exc):
        yield
