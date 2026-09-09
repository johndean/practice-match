"""Drive-time catchments, V1 (spec Section 7 'Catchment build', Section 8 drive_catchment):
straight-line buffers of 8 km (approx 10 min) and 16 km (approx 20 min) in geography space,
intersected with tracts (ACS inputs) and ZCTAs (ZBP competition inputs, D11); overlap_frac =
intersected area / unit area. Geometry is NAD83 (4269); geography maths is done after
ST_Transform to 4326 (red-team C6).

Task B3 correction 5: the join predicate keeps `g.geom` BARE -- the buffer is what gets
transformed, into geometry at the SAME srid (4269) as the column -- rather than wrapping `g.geom`
itself in `ST_Transform(...)::geography`. Wrapping the indexed column in two function calls made
`geo_area_geom_gix` (a GiST index built on the bare `geom` column) unusable, so the predicate
degraded to a full scan of `geo_area` as the table grows; with `g.geom` unwrapped, PostGIS can use
the index's `&&` bounding-box operator to drive `ST_Intersects(geometry, geometry)`
(`tests/perf/test_query_plans.py::test_hot_query_uses_an_index[catchment_tracts]` proves the
planner actually chooses it, rather than asserting it in prose). The overlap-fraction SELECT list
still measures area in geography space (accurate on a sphere); only the JOIN's filter predicate
changed.

Task B3 correction 6: `build()` explicitly manages one transaction around its DELETE and every
INSERT. Production connections come from `app.db`'s pool with `autocommit=True` (each statement
commits the instant it runs), so the brief's delete-then-insert sequence, left as separate
autocommitting statements, could leave a listing with half its catchment if a later INSERT failed.
`build()` toggles `autocommit` off for its own duration (the same pattern `scripts/migrate.py`
uses to commit a migration file and its ledger row as one unit) and restores the connection's
prior setting afterwards, so it is safe to call regardless of the caller's own autocommit state.

Task B3 correction 7 (B3 review, carried into B4b by A-C19): the `GREATEST(0.00001, ...)` floor
in `SQL` below is not an arbitrary epsilon -- it is `practice_catchment.overlap_frac`'s own column
precision, `numeric(6,5)` (`migrations/061_census_listing_tables.sql`), which stores exactly five
digits after the decimal point and so cannot represent anything smaller than `0.00001` without
rounding to `0.00000`. That column also carries `CHECK (overlap_frac > 0 AND overlap_frac <= 1)`
(migration `061`), so a genuinely nonzero intersection too small to survive rounding at that
precision -- a sliver of a tract just grazing the buffer -- would otherwise round to zero and be
refused outright by the CHECK constraint at INSERT time. Flooring the computed fraction at the
column's own smallest representable positive value keeps a real, if negligible, overlap storable
instead of turning a rounding artefact into a failed write.
"""
from __future__ import annotations

import psycopg2.extensions

BANDS: dict[str, int] = {"drive_10": 8000, "drive_20": 16000}
METHOD = "euclidean_buffer_v1"
LEVELS: tuple[str, ...] = ("140", "860")

SQL = """
INSERT INTO practice_catchment (listing_id, band, geo_id, summary_level, vintage, overlap_frac, method)
SELECT p.listing_id, %(band)s, g.geo_id, %(level)s, %(vintage)s,
       LEAST(1.0, GREATEST(0.00001,
         ST_Area(ST_Intersection(ST_Transform(g.geom, 4326)::geography, b.buf))
         / NULLIF(ST_Area(ST_Transform(g.geom, 4326)::geography), 0))),
       %(method)s
FROM practice_location p
CROSS JOIN LATERAL (SELECT ST_Buffer(ST_Transform(p.point, 4326)::geography, %(radius)s) AS buf) b
JOIN geo_area g
  ON g.summary_level = %(level)s AND g.vintage = %(vintage)s
  AND ST_Intersects(g.geom, ST_Transform(b.buf::geometry, 4269))
WHERE p.listing_id = %(listing_id)s AND p.point IS NOT NULL
"""


def build(conn: psycopg2.extensions.connection, listing_id: str, geo_vintage: str) -> dict[str, dict[str, int]]:
    """Rebuilds every drive-time/summary-level catchment row for `listing_id` at `geo_vintage`,
    as one transaction (correction 6): the DELETE and every band/level INSERT below either all
    commit or all roll back together, regardless of the connection's own `autocommit` setting.

    Returns rows written per band per summary level, e.g. `{"drive_10": {"140": 2, "860": 1}, ...}`.
    """
    counts: dict[str, dict[str, int]] = {}
    previous_autocommit = conn.autocommit
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM practice_catchment WHERE listing_id = %s AND vintage = %s", (listing_id, geo_vintage))
            for band, radius in BANDS.items():
                counts[band] = {}
                for level in LEVELS:
                    params: dict[str, str | int] = {
                        "band": band, "level": level, "vintage": geo_vintage, "method": METHOD,
                        "radius": radius, "listing_id": listing_id,
                    }
                    cur.execute(SQL, params)
                    counts[band][level] = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = previous_autocommit
    return counts
