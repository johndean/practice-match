"""scripts/export_design_boundaries.py — the design's own boundary fixture (plan Task 3).

The fixture is GEOMETRY ONLY: `geo_metric` does not exist when it is generated and ACS at ZCTA is
not loaded, so a fixture carrying figures would be carrying invented ones. Each feature carries its
own centroid instead, and the design's own script (A24.2's `areaSet`) assigns it the value of the
nearest of the design's nine Austin communities — `mosaicCells`'s own assignment rule, applied to
real polygons."""
import json
import runpy
import sys
from pathlib import Path

import psycopg2
import pytest

from scripts import export_design_boundaries as EB

ROOT = Path(__file__).resolve().parent.parent.parent

# A 1-degree metro square, one ZCTA inside it, one place inside it, one county inside it, and one
# ZCTA whose centroid is OUTSIDE it — the case that proves the scope really is the metro.
_METRO = "POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))"
_INSIDE = "POLYGON((-97.8 30.2,-97.7 30.2,-97.7 30.3,-97.8 30.3,-97.8 30.2))"
_OUTSIDE = "POLYGON((-96.8 30.2,-96.7 30.2,-96.7 30.3,-96.8 30.3,-96.8 30.2))"


def _geo(conn: psycopg2.extensions.connection, geo_id: str, level: str, name: str, wkt: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) "
            "VALUES (%s, %s, '2023', %s, ST_Multi(ST_GeomFromText(%s, 4269)), ST_Centroid(ST_GeomFromText(%s, 4269)))",
            (geo_id, level, name, wkt, wkt),
        )


@pytest.fixture
def world(conn: psycopg2.extensions.connection) -> psycopg2.extensions.connection:
    _geo(conn, "12420", "310", "Austin-Round Rock-San Marcos, TX Metro Area", _METRO)
    _geo(conn, "48453001100", "140", "Census Tract 11", _INSIDE)
    _geo(conn, "48201010100", "140", "Census Tract 101", _OUTSIDE)
    _geo(conn, "4805000", "160", "Austin", _INSIDE)
    _geo(conn, "48453", "050", "Travis County", _INSIDE)
    return conn


def test_export_returns_one_collection_per_ruled_level_scoped_to_the_metro(world: psycopg2.extensions.connection) -> None:
    fixture = EB.export(world, EB.DESIGN_CBSA, "2023")
    assert sorted(fixture) == ["050", "140", "160"]
    assert [f["id"] for f in fixture["140"]["features"]] == ["48453001100"], "a tract outside the metro was exported"
    assert [f["id"] for f in fixture["160"]["features"]] == ["4805000"]
    assert [f["id"] for f in fixture["050"]["features"]] == ["48453"]
    for collection in fixture.values():
        assert collection["type"] == "FeatureCollection"


def test_every_feature_carries_a_geo_id_a_name_a_centroid_and_a_geometry(world: psycopg2.extensions.connection) -> None:
    feature = EB.export(world, EB.DESIGN_CBSA, "2023")["140"]["features"][0]
    assert feature["type"] == "Feature" and feature["id"] == "48453001100"
    assert feature["properties"]["geo_id"] == "48453001100"
    assert feature["properties"]["name"] == "Census Tract 11"
    lat, lng = feature["properties"]["c"]
    assert 30.2 < lat < 30.3 and -97.8 < lng < -97.7, "the centroid is not [lat, lng] in WGS84"
    assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
    # 4326, not 4269: geo_area.geom is NAD83 and GeoJSON is WGS84.
    #
    # Walk down to the first coordinate pair instead of indexing at a fixed depth. The plan's
    # specimen for this line read `coords[0][0][0][0] ... or coords[0][0][0] ...`, which cannot
    # work: `or` does not catch exceptions, so for a Polygon the left operand raises
    # `TypeError: 'float' object is not subscriptable` before the right one is ever reached. And a
    # Polygon is exactly what comes back — `ST_SimplifyPreserveTopology` returns a single-part
    # MultiPolygon as a Polygon, so the nesting depth is NOT fixed and no constant index is right
    # for both. Measured, not assumed (Task 3 report, defect 1).
    coords: object = feature["geometry"]["coordinates"]
    while isinstance(coords, list) and coords and isinstance(coords[0], list):
        coords = coords[0]
    lng, lat2 = coords  # type: ignore[misc]
    assert -98 < lng < -97 and 30 < lat2 < 31, "the geometry was not transformed out of 4269 into WGS84"


def test_the_module_text_is_pure_ascii_one_line_and_names_its_generator(world: psycopg2.extensions.connection) -> None:
    text = EB.module_text(EB.export(world, EB.DESIGN_CBSA, "2023"))
    assert text.isascii(), "a non-ASCII byte would change the design file's encoding footprint"
    assert "scripts/export_design_boundaries.py" in text, "the generated file must name its generator"
    body = [line for line in text.split("\n") if line.startswith("export const DESIGN_AREAS_LITERAL")]
    assert len(body) == 1, "the literal must be exactly one line, so a diff on it is one line"
    literal = body[0].split(" = ", 1)[1].rstrip(";").strip()
    assert literal.startswith("'") and literal.endswith("'")
    assert json.loads(literal[1:-1].replace("\\'", "'").replace("\\\\", "\\"))["140"]["features"][0]["id"] == "48453001100"


def test_a_name_carrying_a_quote_or_a_backslash_survives_the_single_quoted_string(conn: psycopg2.extensions.connection) -> None:
    """`module_text` emits the payload as a SINGLE-QUOTED TypeScript string, and A24.1 interpolates
    that payload verbatim into the approved design file. An apostrophe in a place name that is not
    escaped therefore closes the string early and corrupts the design bundle — the one failure in
    this module that could not be caught downstream, because the damage is to a file the pixel
    gates regenerate FROM.

    The escaping exists in `module_text`; nothing exercised it. Measured on the real Austin fixture
    there are ZERO apostrophes and ZERO backslashes across all 165 features, so the real data would
    never have found a mistake here — but `--cbsa` reaches any metro, and US place names carrying
    an apostrophe are common outside this one (`O'Brien`, `Coeur d'Alene`). This is the case that
    makes the escaping real rather than decorative."""
    _geo(conn, "12420", "310", "Austin-Round Rock-San Marcos, TX Metro Area", _METRO)
    nasty = "O'Brien \\ d'Alene"
    _geo(conn, "48453001100", "140", nasty, _INSIDE)

    text = EB.module_text(EB.export(conn, EB.DESIGN_CBSA, "2023"))
    assert text.isascii()
    literal = next(ln for ln in text.split("\n") if ln.startswith("export const DESIGN_AREAS_LITERAL"))
    payload = literal.split(" = ", 1)[1].rstrip(";").strip()
    assert payload.startswith("'") and payload.endswith("'")

    # Decode it the way a JavaScript engine decodes a single-quoted string literal, then parse.
    # If either escape were missing this raises rather than returning the name.
    decoded = payload[1:-1].replace("\\'", "'").replace("\\\\", "\\")
    assert json.loads(decoded)["140"]["features"][0]["properties"]["name"] == nasty

    # And the closing quote really is the LAST one: an unescaped apostrophe would put a bare `'`
    # inside the body and end the string early.
    body = payload[1:-1]
    for i, ch in enumerate(body):
        if ch == "'":
            assert i > 0 and body[i - 1] == "\\", "an unescaped apostrophe would close the TS string early"


def test_main_writes_the_module_and_reports_the_counts(world: psycopg2.extensions.connection, scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "design-boundary-fixture.ts"
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert EB.main(["--out", str(out), "--vintage", "2023"]) == 0
    assert "140=1" in capsys.readouterr().out
    assert out.read_text(encoding="utf-8").count("DESIGN_AREAS_LITERAL") == 1


def test_main_refuses_without_a_database_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert EB.main(["--out", str(tmp_path / "x.ts")]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_main_refuses_a_fixture_over_the_cap(world: psycopg2.extensions.connection, scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The cap is not decoration: the literal is embedded in a 306 KB design file that
    `applyAmendments` string-searches once per amendment."""
    out = tmp_path / "too-big.ts"
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(EB, "MAX_FIXTURE_BYTES", 10)
    assert EB.main(["--out", str(out), "--vintage", "2023"]) == 1
    assert "over the 10" in capsys.readouterr().err
    assert not out.exists(), "a refused fixture must not be written"


def test_the_main_guard_is_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    """runpy re-executes the file in THIS process with __name__ == "__main__", so pytest-cov
    sees the guard (the idiom tests/scripts/test_seed_listings.py established)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["export_design_boundaries.py"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "export_design_boundaries.py"), run_name="__main__")
    assert exc.value.code == 2


# --- D-C49 (John, 2026-09-11): coarsen as committed, then REPAIR -------------------------------
# Task 3 measured that `ST_SimplifyPreserveTopology` at the committed 0.010 leaves 5 of the Austin
# fixture's 165 polygons geometrically invalid (self-intersections, and holes that end up outside
# their shell), and that halving the tolerance leaves 1 but needs ~155 KB against a 120 KB cap.
# John ruled: keep the tolerance, repair the output. Measured after the repair on the real fixture:
# 0 of 165 invalid, 5 polygons changed and the other 160 byte-identical, worst-case drift on a
# repaired polygon 1.41 % of its area and 52 m of its centroid — against a coarsening that already
# moves one ZCTA's area by 110 % and its centroid by 931 m, so the repair does not materially move
# an outline. `ST_CollectionExtract(…, 3)` is not decoration: `ST_MakeValid` answers a spike with a
# GEOMETRYCOLLECTION of polygons AND lines, and a GeoJSON `GeometryCollection` in the fixture would
# reach `L.geoJSON` on both targets. Extracting the areal parts is the explicit handling; it leaves
# a geometry that is already a Polygon or a MultiPolygon alone, which is why the fixture's type mix
# barely moves (142/23 → 139/26) and its payload grows by 18 bytes.

_HOLE_OUTSIDE_SHELL = (
    "POLYGON((-97.8 30.2,-97.7 30.2,-97.7 30.3,-97.8 30.3,-97.8 30.2),"
    "(-97.65 30.22,-97.62 30.22,-97.62 30.25,-97.65 30.25,-97.65 30.22))"
)
_SPIKE = "POLYGON((-97.8 30.2,-97.6 30.2,-97.6 30.4,-97.8 30.4,-97.8 30.2,-97.4 30.6,-97.8 30.2))"


def _postgis_verdict(conn: psycopg2.extensions.connection, geometry: dict[str, object]) -> tuple[bool, str]:
    """Ask PostGIS what it makes of the geometry the fixture actually carries — the round trip is
    the point: this is the JSON a browser will hand to `L.geoJSON`, not an intermediate."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ST_IsValid(g), GeometryType(g) FROM (SELECT ST_GeomFromGeoJSON(%s) AS g) s",
            (json.dumps(geometry),),
        )
        valid, geom_type = cur.fetchone()
    return bool(valid), str(geom_type)


def test_a_polygon_simplification_leaves_invalid_is_repaired_before_it_is_exported(conn: psycopg2.extensions.connection) -> None:
    _geo(conn, "12420", "310", "Austin-Round Rock-San Marcos, TX Metro Area", _METRO)
    _geo(conn, "48453001100", "140", "Census Tract 11", _HOLE_OUTSIDE_SHELL)

    feature = EB.export(conn, EB.DESIGN_CBSA, "2023")["140"]["features"][0]
    valid, geom_type = _postgis_verdict(conn, feature["geometry"])
    assert valid, "an invalid polygon reached the fixture — D-C49 ruled the repair, not a tolerance change"
    assert geom_type == "MULTIPOLYGON", "repairing a hole that lies outside its shell splits it into parts"


def test_a_repair_that_yields_a_geometry_collection_exports_only_its_polygons(conn: psycopg2.extensions.connection) -> None:
    """`ST_MakeValid` answers a spike with a GEOMETRYCOLLECTION — the polygon AND the dangling line.
    A `GeometryCollection` is legal GeoJSON and `L.geoJSON` would draw the line as a stroke the
    design has no class for, so the areal parts are extracted explicitly rather than trusted."""
    _geo(conn, "12420", "310", "Austin-Round Rock-San Marcos, TX Metro Area", _METRO)
    _geo(conn, "48453001100", "140", "Census Tract 11", _SPIKE)

    feature = EB.export(conn, EB.DESIGN_CBSA, "2023")["140"]["features"][0]
    valid, geom_type = _postgis_verdict(conn, feature["geometry"])
    assert valid
    assert geom_type == "MULTIPOLYGON", f"a {geom_type} reached the fixture"
    assert feature["geometry"]["type"] == "MultiPolygon"


def test_every_exported_geometry_is_areal_and_non_empty(world: psycopg2.extensions.connection) -> None:
    """The invariant the two cases above are instances of, asserted over the whole export: nothing
    but a Polygon or a MultiPolygon, and never an empty one — an empty geometry is a hole in a
    choropleth, which reads as a boundary rather than as an absence (D-NS16's whole argument)."""
    for collection in EB.export(world, EB.DESIGN_CBSA, "2023").values():
        for feature in collection["features"]:
            assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
            assert feature["geometry"]["coordinates"], f"{feature['id']} exported empty coordinates"
