"""TIGER cartographic boundary files → geo_area (spec §2 tiger_cb, §6 levels, §13).

Pure Python: pyshp reads the shapefile inside the zip, shapely normalises to MultiPolygon
WKB, PostGIS computes the centroid. No GDAL in the image (plan D2).

Archiving (controller correction, 2026-09-09, from A3's review): every raw zip is written to
the generic `ObjectStore` (`app/storage.py`) under the `census/` prefix A-C2 ¶1 actually rules
-- `census/tiger/<vintage>/<file>` -- never A3's `raw/...` naming. The archive is append-only
by convention (A-C3 (1)): `exists(key)` is checked before `put(key, data, content_type)`, so a
retried or re-run load never overwrites what an earlier run recorded. Nothing is EVER archived
before `parse_shapefile` has proven the body parses -- a redirect page or a corrupt zip must
never occupy a key forever, so the write happens strictly after the parse succeeds, never before
or in parallel with it. `archive=None` (the default, and what `ObjectStore.from_settings` returns
when the bucket is not configured) simply skips archiving; the boundary load still runs.

`_get_with_fallback` raises `CensusHTTPError` (`app/census/client.py`) for any failing status,
which redacts the URL through `redact()` the same way every other Census fetch in this programme
does (A-C3 (3)) -- even though a TIGER URL never carries a `key=` parameter to strip, the habit
is uniform across the module. The `httpx.Client` this module is handed is expected to be built
with `follow_redirects=False` (the caller's concern -- `scripts/census_load.py`, and later the
`census.load_tiger` Celery task -- construct it), so a 3xx is never silently followed into an
unarchived, unparsed body.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import httpx
import psycopg2
import psycopg2.extensions
import shapefile  # type: ignore[import-untyped]  # pyshp ships no py.typed marker / stubs
from shapely import wkb
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.census.client import CensusHTTPError
from app.storage import ObjectStore

BASE = "https://www2.census.gov/geo/tiger/GENZ{y}/shp"

#: TIGER files run tens to hundreds of MB; the spec §3 45 s read timeout is for the (small)
#: Census Data API JSON responses, not this bulk static-file download.
_TIMEOUT = httpx.Timeout(connect=15.0, read=300.0, write=15.0, pool=15.0)


@dataclass(frozen=True)
class BoundarySpec:
    summary_level: str
    url: str
    geoid_field: str
    name_field: str
    state_field: str | None
    county_field: str | None
    land_field: str | None
    parent: str | None  # 'county' | 'state' | 'nation' | None


@dataclass(frozen=True)
class GeoRow:
    geo_id: str
    summary_level: str
    name: str
    state_fips: str | None
    county_fips: str | None
    parent_geo_id: str | None
    land_area_m2: int | None
    wkb: bytes


def BOUNDARY_FILES(vintage_year: int, state_fips: list[str]) -> list[BoundarySpec]:
    b = BASE.format(y=vintage_year)
    y = vintage_year
    specs = [
        BoundarySpec("010", f"{b}/cb_{y}_us_nation_5m.zip", "GEOID", "NAME", None, None, "ALAND", None),
        BoundarySpec("040", f"{b}/cb_{y}_us_state_500k.zip", "GEOID", "NAME", "STATEFP", None, "ALAND", "nation"),
        BoundarySpec("050", f"{b}/cb_{y}_us_county_500k.zip", "GEOID", "NAMELSAD", "STATEFP", "COUNTYFP", "ALAND", "state"),
        BoundarySpec("310", f"{b}/cb_{y}_us_cbsa_500k.zip", "GEOID", "NAME", None, None, "ALAND", None),
        # ZCTAs are 2020-based; the GENZ{y} folder may not republish them -- load_boundaries falls
        # back to GENZ2020.
        BoundarySpec("860", f"{b}/cb_{y}_us_zcta520_500k.zip", "GEOID20", "NAME20", None, None, "ALAND20", None),
    ]
    for st in state_fips:
        specs.append(BoundarySpec("140", f"{b}/cb_{y}_{st}_tract_500k.zip", "GEOID", "NAMELSAD", "STATEFP", "COUNTYFP", "ALAND", "county"))
        specs.append(BoundarySpec("160", f"{b}/cb_{y}_{st}_place_500k.zip", "GEOID", "NAME", "STATEFP", None, "ALAND", "state"))
    return specs


def _parent(spec: BoundarySpec, state: str | None, county: str | None) -> str | None:
    if spec.parent == "county" and state and county:
        return state + county
    if spec.parent == "state":
        return state
    if spec.parent == "nation":
        return "1"
    return None


def parse_shapefile(zip_bytes: bytes, spec: BoundarySpec) -> list[GeoRow]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = {n.rsplit(".", 1)[1].lower(): n for n in z.namelist() if n.lower().endswith((".shp", ".shx", ".dbf"))}
        reader = shapefile.Reader(shp=io.BytesIO(z.read(names["shp"])), shx=io.BytesIO(z.read(names["shx"])), dbf=io.BytesIO(z.read(names["dbf"])))
    rows: list[GeoRow] = []
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        geom = shape(sr.shape.__geo_interface__)
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        state = str(rec[spec.state_field]) if spec.state_field else None
        county = str(rec[spec.county_field]) if spec.county_field else None
        land = rec.get(spec.land_field) if spec.land_field else None
        rows.append(GeoRow(
            geo_id=str(rec[spec.geoid_field]), summary_level=spec.summary_level, name=str(rec[spec.name_field]),
            state_fips=state, county_fips=county, parent_geo_id=_parent(spec, state, county),
            land_area_m2=int(land) if land not in (None, "") else None, wkb=geom.wkb,
        ))
    return rows


UPSERT = """
INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, land_area_m2, geom, centroid)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, ST_Multi(ST_GeomFromWKB(%s, 4269)), ST_Centroid(ST_GeomFromWKB(%s, 4269)))
ON CONFLICT (geo_id, summary_level, vintage) DO UPDATE SET
  name = EXCLUDED.name, state_fips = EXCLUDED.state_fips, county_fips = EXCLUDED.county_fips,
  parent_geo_id = EXCLUDED.parent_geo_id, land_area_m2 = EXCLUDED.land_area_m2, geom = EXCLUDED.geom, centroid = EXCLUDED.centroid
"""


def upsert_geo(conn: psycopg2.extensions.connection, rows: list[GeoRow], vintage: str) -> int:
    with conn.cursor() as cur:
        cur.executemany(UPSERT, [(r.geo_id, r.summary_level, vintage, r.name, r.state_fips, r.county_fips, r.parent_geo_id,
                                  r.land_area_m2, psycopg2.Binary(r.wkb), psycopg2.Binary(r.wkb)) for r in rows])
    return len(rows)


def _archive_key(vintage: str, url: str) -> str:
    """`census/` (A-C2 ¶1), never A3's `raw/...` -- the Census archive's own prefix."""
    return f"census/tiger/{vintage}/{url.rsplit('/', 1)[1]}"


def _get_with_fallback(http: httpx.Client, spec: BoundarySpec, vintage: str) -> httpx.Response:
    """One request, with the single documented exception (D2 / spec note): ZCTAs are
    2020-based and a `GENZ{vintage}` folder may not republish them, so a 404 on that one
    summary level retries against the fixed `GENZ2020` release before giving up. Any other
    failing status -- on this attempt or the retry -- raises `CensusHTTPError`, which redacts
    the URL (A-C3 (3))."""
    resp = http.get(spec.url, timeout=_TIMEOUT)
    if resp.status_code == 404 and spec.summary_level == "860":
        fallback_url = spec.url.replace(f"GENZ{vintage}", "GENZ2020").replace(f"cb_{vintage}_", "cb_2020_")
        resp = http.get(fallback_url, timeout=_TIMEOUT)
    if resp.status_code >= 400:
        raise CensusHTTPError(resp.status_code, str(resp.url))
    return resp


def load_boundaries(
    conn: psycopg2.extensions.connection,
    http: httpx.Client,
    states: list[str],
    vintage: str = "2023",
    archive: ObjectStore | None = None,
) -> dict[str, int]:
    """Downloads and upserts every boundary file. ZCTAs (national file) are kept only
    when their centroid falls inside a market state, to bound table size."""
    counts: dict[str, int] = {}
    state_geoms: list[BaseGeometry] | None = None
    for spec in BOUNDARY_FILES(int(vintage), states):
        resp = _get_with_fallback(http, spec, vintage)
        body = resp.content
        rows = parse_shapefile(body, spec)  # never archived unless this line does not raise
        if archive is not None:
            key = _archive_key(vintage, str(resp.url))
            if not archive.exists(key):  # append-only by convention (A-C3 (1)): never re-write an archived key
                archive.put(key, body, "application/zip")
        if spec.summary_level == "040":
            state_geoms = [wkb.loads(r.wkb) for r in rows if r.geo_id in states]
        if spec.summary_level == "860" and state_geoms:
            market = unary_union(state_geoms)
            rows = [r for r in rows if market.contains(wkb.loads(r.wkb).centroid)]
        counts[f"{spec.summary_level}:{str(resp.url).rsplit('/', 1)[1]}"] = upsert_geo(conn, rows, vintage)
    return counts
