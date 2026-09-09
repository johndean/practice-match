import psycopg2
import pytest

from app.census import catchment
from tests.census.listing_fixtures import make_listing


def _seed(conn, lid):
    with conn.cursor() as cur:
        # three 0.1 x 0.1 degree tracts west to east; the practice sits in the middle of the first.
        for i, gid in enumerate(["48000000001", "48000000002", "48000000003"]):
            x0 = -97.90 + 0.1 * i
            cur.execute("""INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom) VALUES (%s,'140','2023',%s,
                           ST_Multi(ST_GeomFromText(%s, 4269)))""",
                        (gid, gid, f"POLYGON(({x0} 30.50,{x0+0.1} 30.50,{x0+0.1} 30.60,{x0} 30.60,{x0} 30.50))"))
        # one ZCTA covering the first two tracts, one far away
        cur.execute("""INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom) VALUES
            ('78613','860','2023','ZCTA5 78613', ST_Multi(ST_GeomFromText('POLYGON((-97.90 30.50,-97.70 30.50,-97.70 30.60,-97.90 30.60,-97.90 30.50))',4269))),
            ('79999','860','2023','ZCTA5 79999', ST_Multi(ST_GeomFromText('POLYGON((-99.0 31.0,-98.9 31.0,-98.9 31.1,-99.0 31.1,-99.0 31.0))',4269)))""")
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, point, geo_precision, geocoded_at, geocoder_vintage)
                       VALUES (%s, 'h', ST_SetSRID(ST_Point(-97.85, 30.55), 4269), 'rooftop', now(), 'Current_Current')""", (lid,))


def test_build_with_no_practice_location_writes_nothing(conn):
    """B3 review carried item (A-C19): a listing that has not been geocoded yet has no
    `practice_location` row at all. `build()`'s SQL starts `FROM practice_location p ... WHERE
    p.listing_id = %s AND p.point IS NOT NULL`, so a missing row makes the whole FROM clause
    empty and every band/level INSERT affects zero rows -- correct by inspection, but unproven
    until now. Seeds no `geo_area` either, so a bug that somehow matched geographies without a
    location would still be caught (there is nothing to intersect against)."""
    lid = make_listing(conn)
    counts = catchment.build(conn, lid, "2023")
    assert counts == {"drive_10": {"140": 0, "860": 0}, "drive_20": {"140": 0, "860": 0}}
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM practice_catchment WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 0


def test_buffers_intersect_tracts_and_zctas_with_overlap_fractions(conn):
    lid = make_listing(conn)
    _seed(conn, lid)
    counts = catchment.build(conn, lid, "2023")
    assert counts == {"drive_10": {"140": 2, "860": 1}, "drive_20": {"140": 3, "860": 1}}
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id, overlap_frac::float, method FROM practice_catchment WHERE listing_id=%s AND band='drive_10' AND summary_level='140' ORDER BY geo_id", (lid,))
        rows = cur.fetchall()
    assert rows[0][0] == "48000000001" and 0.9 < rows[0][1] <= 1.0 and rows[0][2] == "euclidean_buffer_v1"
    assert rows[1][0] == "48000000002" and 0.0 < rows[1][1] < 0.5
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id, overlap_frac::float FROM practice_catchment WHERE listing_id=%s AND band='drive_10' AND summary_level='860'", (lid,))
        (zcta, frac), = cur.fetchall()
    assert zcta == "78613" and 0.4 < frac < 0.8


def test_rebuild_replaces_rows(conn):
    lid = make_listing(conn)
    _seed(conn, lid)
    catchment.build(conn, lid, "2023")
    catchment.build(conn, lid, "2023")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM practice_catchment WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 7


class _RaisingOnSecondCatchmentInsert(psycopg2.extensions.cursor):
    """Raises on the SECOND catchment INSERT (band=drive_10, level=860) so a test can prove
    `catchment.build` rolls its DELETE and every INSERT back together, rather than leaving a
    listing with half its catchment when a failure lands partway through (A-C16 / task-B3
    correction 6: production connections are pooled with `autocommit=True`, so each statement
    commits as it runs unless `build` manages its own transaction)."""

    def execute(self, query, vars=None):  # matches psycopg2's own cursor.execute signature
        if isinstance(query, str) and query == catchment.SQL and vars is not None and vars.get("band") == "drive_10" and vars.get("level") == "860":
            raise psycopg2.Error("forced failure (RED/behavioural test): partial catchment insert")
        return super().execute(query, vars)


def test_build_rolls_back_atomically_on_a_failure_partway(scratch_dsn):
    conn = psycopg2.connect(scratch_dsn)
    conn.autocommit = True  # the production shape: pooled connections default to autocommit
    lid = make_listing(conn)
    _seed(conn, lid)
    catchment.build(conn, lid, "2023")  # first build succeeds, leaving 7 rows in place

    raising_conn = psycopg2.connect(scratch_dsn, cursor_factory=_RaisingOnSecondCatchmentInsert)
    raising_conn.autocommit = True
    try:
        with pytest.raises(psycopg2.Error):
            catchment.build(raising_conn, lid, "2023")
    finally:
        raising_conn.close()

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM practice_catchment WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 7  # the DELETE that would have cleared these rolled back too
    conn.close()
