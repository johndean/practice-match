"""TIGER cartographic boundary files -> geo_area (Task A4).

Step 1's three tests are the brief's own, run verbatim. The rest are this task's own budget:
`load_boundaries`'s HTTP/archive/filter behaviour is not exercised by the brief's three unit
tests at all, and the 100 % branch coverage gate (`--cov=app --cov-branch`) covers `app/census`
the same as every other package under `app/`.

Archiving here follows the controller correction made during A3's review (2026-09-09), applied
from the start rather than repeated: the Census archive's key prefix is `census/` (A-C2 P1),
never A3's `raw/...`; a raw body is written only AFTER `parse_shapefile` has proven it parses,
never before or unconditionally; and any raised HTTP error is a `CensusHTTPError`, which redacts
the URL the same way every other Census fetch in this programme does (A-C3 (3)).
"""
from __future__ import annotations

import io
import zipfile

import httpx
import pytest
import shapefile  # pyshp
from moto import mock_aws

from app.census.client import CensusHTTPError
from app.census.tiger import BOUNDARY_FILES, BoundarySpec, load_boundaries, parse_shapefile, upsert_geo
from app.storage import ObjectStore

TRACT = BoundarySpec(summary_level="140", url="mem://tract", geoid_field="GEOID", name_field="NAMELSAD",
                     state_field="STATEFP", county_field="COUNTYFP", land_field="ALAND", parent="county")


def _zip_with_shapefile(records):
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    w.field("GEOID", "C", 11); w.field("NAMELSAD", "C", 40); w.field("STATEFP", "C", 2); w.field("COUNTYFP", "C", 3); w.field("ALAND", "N", 14, 0)
    for geoid, name, st, co, aland, ring in records:
        w.poly([ring]); w.record(geoid, name, st, co, aland)
    w.close()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cb_2023_48_tract_500k.shp", shp.getvalue()); z.writestr("cb_2023_48_tract_500k.shx", shx.getvalue()); z.writestr("cb_2023_48_tract_500k.dbf", dbf.getvalue())
    return buf.getvalue()


SQUARE = [(-97.9, 30.5), (-97.8, 30.5), (-97.8, 30.6), (-97.9, 30.6), (-97.9, 30.5)]
RECORDS = [("48453000101", "Census Tract 1.01", "48", "453", 1234567, SQUARE),
           ("48453000102", "Census Tract 1.02", "48", "453", 2345678, [(x + 0.2, y) for x, y in SQUARE])]


def test_parse_shapefile_yields_multipolygon_rows_with_parent_geoid():
    rows = parse_shapefile(_zip_with_shapefile(RECORDS), TRACT)
    assert [r.geo_id for r in rows] == ["48453000101", "48453000102"]
    r = rows[0]
    assert (r.summary_level, r.name, r.state_fips, r.county_fips, r.parent_geo_id, r.land_area_m2) == ("140", "Census Tract 1.01", "48", "453", "48453", 1234567)
    from shapely import wkb
    g = wkb.loads(r.wkb)
    assert g.geom_type == "MultiPolygon" and abs(g.area - 0.01) < 1e-6


def test_parse_shapefile_leaves_a_naturally_multipart_geometry_untouched():
    """A tract split by, e.g., a river or an island is stored as one shapefile record with
    several disjoint exterior rings -- pyshp's GeoJSON conversion already reports that as
    `MultiPolygon`, so the `Polygon -> MultiPolygon` wrap (the `geom.geom_type == "Polygon"`
    branch) must not run for it -- the one arm the brief's own three tests never exercise."""
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    w.field("GEOID", "C", 11); w.field("NAMELSAD", "C", 40); w.field("STATEFP", "C", 2); w.field("COUNTYFP", "C", 3); w.field("ALAND", "N", 14, 0)
    other = [(x + 5.0, y + 5.0) for x, y in SQUARE]
    w.poly([SQUARE, other])  # two disjoint exterior rings -- one record, two parts
    w.record("48453000103", "Census Tract 1.03", "48", "453", 999)
    w.close()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.shp", shp.getvalue()); z.writestr("x.shx", shx.getvalue()); z.writestr("x.dbf", dbf.getvalue())

    rows = parse_shapefile(buf.getvalue(), TRACT)
    from shapely import wkb
    g = wkb.loads(rows[0].wkb)
    assert g.geom_type == "MultiPolygon"
    assert len(g.geoms) == 2


def test_parse_shapefile_nests_an_interior_ring_as_a_hole():
    """A4 review m-1: nothing previously constructed a record with an exterior ring plus a hole
    (e.g. a county with a water body punched out) to prove pyshp's ring-orientation-based GeoJSON
    conversion nests it as a Polygon interior ring rather than a second exterior ring. The
    shapefile format requires the exterior ring clockwise and a hole counter-clockwise (pyshp's
    own `Writer.poly` docstring) -- both rings below are wound accordingly."""
    outer = [(-97.9, 30.5), (-97.9, 30.6), (-97.8, 30.6), (-97.8, 30.5), (-97.9, 30.5)]   # clockwise
    hole = [(-97.87, 30.53), (-97.83, 30.53), (-97.83, 30.57), (-97.87, 30.57), (-97.87, 30.53)]   # counter-clockwise
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    w.field("GEOID", "C", 11); w.field("NAMELSAD", "C", 40); w.field("STATEFP", "C", 2); w.field("COUNTYFP", "C", 3); w.field("ALAND", "N", 14, 0)
    w.poly([outer, hole])
    w.record("48453000104", "Census Tract 1.04", "48", "453", 999)
    w.close()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("h.shp", shp.getvalue()); z.writestr("h.shx", shx.getvalue()); z.writestr("h.dbf", dbf.getvalue())

    rows = parse_shapefile(buf.getvalue(), TRACT)
    from shapely import wkb
    g = wkb.loads(rows[0].wkb)
    assert g.geom_type == "MultiPolygon" and len(g.geoms) == 1
    assert len(g.geoms[0].interiors) == 1
    assert g.is_valid


def test_upsert_is_idempotent_and_computes_centroid(conn):
    rows = parse_shapefile(_zip_with_shapefile(RECORDS), TRACT)
    assert upsert_geo(conn, rows, "2023") == 2
    assert upsert_geo(conn, rows, "2023") == 2  # same rows again -> still 2, no duplicates
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), max(ST_SRID(geom)) FROM geo_area WHERE summary_level='140' AND vintage='2023'")
        assert cur.fetchone() == (2, 4269)
        cur.execute("SELECT ST_X(centroid), ST_Y(centroid) FROM geo_area WHERE geo_id='48453000101'")
        x, y = cur.fetchone()
        assert abs(x + 97.85) < 1e-6 and abs(y - 30.55) < 1e-6
        cur.execute("SELECT ST_Contains(geom, centroid) FROM geo_area WHERE geo_id='48453000101'")
        assert cur.fetchone()[0] is True


def test_boundary_files_cover_every_spec_level_for_the_market_states():
    specs = BOUNDARY_FILES(2023, ["48", "06"])
    levels = sorted({s.summary_level for s in specs})
    assert levels == ["010", "040", "050", "140", "160", "310", "860"]
    urls = {s.url for s in specs}
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_48_tract_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_06_place_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_cbsa_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_zcta520_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip" in urls
    assert "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_nation_5m.zip" in urls


# --- load_boundaries: HTTP, the ZCTA 2020 fallback, state-containment filtering and archiving ---
# (this task's own budget -- not in the brief's Step 1, but required for the 100 % branch gate)

def _shp_zip(stem: str, fields: list[tuple[str, str, int, int]], rows: list[tuple[tuple, list]]) -> bytes:
    """A tiny single- or multi-record shapefile, zipped under `stem`, generalising the brief's
    own `_zip_with_shapefile` to the other six summary levels' different field names."""
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    for name, typ, size, dec in fields:
        w.field(name, typ, size, dec)
    for record, ring in rows:
        w.poly([ring])
        w.record(*record)
    w.close()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{stem}.shp", shp.getvalue())
        z.writestr(f"{stem}.shx", shx.getvalue())
        z.writestr(f"{stem}.dbf", dbf.getvalue())
    return buf.getvalue()


# A Texas-sized square, big enough to contain one ZCTA centroid and exclude the other.
TX_SQUARE = [(-99.0, 29.0), (-97.0, 29.0), (-97.0, 31.0), (-99.0, 31.0), (-99.0, 29.0)]
ZCTA_INSIDE = [(-98.05, 29.95), (-97.95, 29.95), (-97.95, 30.05), (-98.05, 30.05), (-98.05, 29.95)]
ZCTA_OUTSIDE = [(40.0, 40.0), (40.1, 40.0), (40.1, 40.1), (40.0, 40.1), (40.0, 40.0)]

NATION_ZIP = _shp_zip("cb_2023_us_nation_5m", [("GEOID", "C", 1, 0), ("NAME", "C", 40, 0), ("ALAND", "N", 14, 0)],
                      [(("1", "United States", 1), TX_SQUARE)])
STATE_ZIP = _shp_zip("cb_2023_us_state_500k", [("GEOID", "C", 2, 0), ("NAME", "C", 40, 0), ("STATEFP", "C", 2, 0), ("ALAND", "N", 14, 0)],
                     [(("48", "Texas", "48", 100), TX_SQUARE)])
COUNTY_ZIP = _shp_zip("cb_2023_us_county_500k", [("GEOID", "C", 5, 0), ("NAMELSAD", "C", 40, 0), ("STATEFP", "C", 2, 0), ("COUNTYFP", "C", 3, 0), ("ALAND", "N", 14, 0)],
                      [(("48453", "Travis County", "48", "453", 50), TX_SQUARE)])
CBSA_ZIP = _shp_zip("cb_2023_us_cbsa_500k", [("GEOID", "C", 5, 0), ("NAME", "C", 40, 0), ("ALAND", "N", 14, 0)],
                    [(("12420", "Austin-Round Rock-San Marcos, TX", 60), TX_SQUARE)])
TRACT_ZIP = _shp_zip("cb_2023_48_tract_500k", [("GEOID", "C", 11, 0), ("NAMELSAD", "C", 40, 0), ("STATEFP", "C", 2, 0), ("COUNTYFP", "C", 3, 0), ("ALAND", "N", 14, 0)],
                     [(("48453000101", "Census Tract 1.01", "48", "453", 10), TX_SQUARE)])
PLACE_ZIP = _shp_zip("cb_2023_48_place_500k", [("GEOID", "C", 7, 0), ("NAME", "C", 40, 0), ("STATEFP", "C", 2, 0), ("ALAND", "N", 14, 0)],
                     [(("4805000", "Austin", "48", 20), TX_SQUARE)])
ZCTA_ZIP_2020 = _shp_zip("cb_2020_us_zcta520_500k", [("GEOID20", "C", 5, 0), ("NAME20", "C", 5, 0), ("ALAND20", "N", 14, 0)],
                         [(("78701", "78701", 5), ZCTA_INSIDE), (("99999", "99999", 5), ZCTA_OUTSIDE)])


_BY_SUFFIX = {
    "cb_2023_us_nation_5m.zip": NATION_ZIP,
    "cb_2023_us_state_500k.zip": STATE_ZIP,
    "cb_2023_us_county_500k.zip": COUNTY_ZIP,
    "cb_2023_us_cbsa_500k.zip": CBSA_ZIP,
    "cb_2023_48_tract_500k.zip": TRACT_ZIP,
    "cb_2023_48_place_500k.zip": PLACE_ZIP,
    "cb_2020_us_zcta520_500k.zip": ZCTA_ZIP_2020,
}


def _handler() -> httpx.MockTransport:
    """One full `BOUNDARY_FILES(2023, ["48"])` pass. The ZCTA GENZ2023 URL always 404s (the
    documented case this programme falls back for); every other URL, including the GENZ2020
    fallback, answers 200."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("cb_2023_us_zcta520_500k.zip"):
            return httpx.Response(404)
        for suffix, body in _BY_SUFFIX.items():
            if url.endswith(suffix):
                return httpx.Response(200, content=body)
        raise AssertionError(f"unexpected URL in test transport: {url}")

    return httpx.MockTransport(handler)


@pytest.fixture
def store():
    import boto3

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="pm-test")
        yield ObjectStore(endpoint_url=None, bucket="pm-test", access_key="x", secret_key="y", region="us-east-1")


def test_load_boundaries_upserts_every_level_and_filters_zctas_by_state_containment(conn):
    http = httpx.Client(transport=_handler())
    counts = load_boundaries(conn, http, ["48"], "2023")
    assert counts == {
        "010:cb_2023_us_nation_5m.zip": 1,
        "040:cb_2023_us_state_500k.zip": 1,
        "050:cb_2023_us_county_500k.zip": 1,
        "310:cb_2023_us_cbsa_500k.zip": 1,
        # the fallback body's own filename, not the GENZ2023 request that 404'd
        "860:cb_2020_us_zcta520_500k.zip": 1,
        "140:cb_2023_48_tract_500k.zip": 1,
        "160:cb_2023_48_place_500k.zip": 1,
    }
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id FROM geo_area WHERE summary_level = '860'")
        assert [r[0] for r in cur.fetchall()] == ["78701"], "the out-of-state ZCTA centroid must be dropped"
        cur.execute("SELECT geo_id, parent_geo_id FROM geo_area WHERE summary_level = '140'")
        assert cur.fetchone() == ("48453000101", "48453")


def test_load_boundaries_archives_every_raw_body_under_the_census_prefix(conn, store):
    http = httpx.Client(transport=_handler())
    load_boundaries(conn, http, ["48"], "2023", archive=store)
    assert store.exists("census/tiger/2023/cb_2023_us_state_500k.zip")
    assert store.get("census/tiger/2023/cb_2023_us_state_500k.zip") == STATE_ZIP
    # the ZCTA key is named for the body actually fetched (the 2020 fallback), never the
    # GENZ2023 URL that 404'd and was never archived
    assert store.exists("census/tiger/2023/cb_2020_us_zcta520_500k.zip")
    assert not store.exists("census/tiger/2023/cb_2023_us_zcta520_500k.zip")


def test_load_boundaries_skips_archiving_a_key_that_already_exists(conn, store):
    store.put("census/tiger/2023/cb_2023_us_nation_5m.zip", b"already archived", "application/zip")
    http = httpx.Client(transport=_handler())
    load_boundaries(conn, http, ["48"], "2023", archive=store)
    # append-only by convention (A-C3 (1)): a key already there is never overwritten
    assert store.get("census/tiger/2023/cb_2023_us_nation_5m.zip") == b"already archived"


def test_load_boundaries_runs_with_archiving_disabled_by_default(conn):
    """`archive=None` is the default -- what `ObjectStore.from_settings` returns when the
    bucket is not configured (A-C2 P2) -- and the load must still complete."""
    http = httpx.Client(transport=_handler())
    counts = load_boundaries(conn, http, ["48"], "2023")
    assert sum(counts.values()) == 7


def test_a_malformed_body_is_never_archived(conn, store):
    """A body that is not a valid shapefile zip must never occupy an archive key -- the archive
    is append-only, and an object stored before validation would be orphaned there forever."""

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("cb_2023_us_nation_5m.zip"):
            return httpx.Response(200, content=b"not a zip file")
        raise AssertionError("only the nation URL should be requested before the failure")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(zipfile.BadZipFile):
        load_boundaries(conn, http, ["48"], "2023", archive=store)
    assert store.exists("census/tiger/2023/cb_2023_us_nation_5m.zip") is False


def test_a_3xx_response_raises_a_redacted_census_http_error_not_a_bad_zip_file(conn):
    """A4 review M-2 / A-C4 ¶1: only a 2xx is a success everywhere in this programme now,
    `tiger.py` included. `follow_redirects=False` (the caller's concern) means a genuine 3xx from
    www2.census.gov is never transparently followed -- but before this fix it was also never
    REJECTED here, so the redirect page flowed into `parse_shapefile` and blew up as an uncaught
    `zipfile.BadZipFile` instead of the documented, redacted `CensusHTTPError`."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://www2.census.gov/elsewhere"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(CensusHTTPError) as exc:
        load_boundaries(conn, http, ["48"], "2023")
    assert exc.value.status == 302


def test_a_persistent_5xx_raises_a_redacted_census_http_error(conn):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(CensusHTTPError) as exc:
        load_boundaries(conn, http, ["48"], "2023")
    assert exc.value.status == 500
    assert "key=" not in str(exc.value)


def test_the_zcta_fallback_also_failing_raises(conn):
    """Both the GENZ2023 attempt and the GENZ2020 retry 404 -- there is nothing left to fall
    back to, and the error must surface rather than be swallowed."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("zcta520_500k.zip"):
            return httpx.Response(404)
        return httpx.Response(200, content=NATION_ZIP if "nation" in url else STATE_ZIP if "state" in url
                               else COUNTY_ZIP if "county" in url else CBSA_ZIP)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(CensusHTTPError) as exc:
        load_boundaries(conn, http, [], "2023")
    assert exc.value.status == 404
