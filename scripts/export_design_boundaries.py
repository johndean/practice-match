"""Generate the DESIGN's own boundary fixture from real `geo_area` rows (plan Task 3, spec §9.4).

Amendment A24.1 puts a `FeatureCollection` per fill layer into the approved design's `state`
literal, and the geometry in it has to be real: the whole point of this change is that the edges
are Census lines rather than the grid artefacts `mosaicCells` drew. This writes that literal once,
as a generated TypeScript module the amendment interpolates.

GEOMETRY ONLY, deliberately. `geo_metric` does not exist when this runs and ACS carries no ZCTA
row, so a fixture with figures in it would be a fixture with INVENTED figures in it. Each feature
carries its own centroid instead, and the design's own `areaSet` (A24.2) assigns it the value of
the nearest of the design's nine Austin communities — `mosaicCells`'s own rule ("spatial ASSIGNMENT
of existing community data, not interpolation, and not new data") applied to real polygons.

Simplified at `SIMPLIFY_DEG` degrees — TWENTY times coarser than the ~0.0005 degrees Census
spec §2b recommends for production write-time simplification — because this is a fixture, in the
same class as `design-listings.mjs`'s `name: null`: pixels only ever compare the reference against
an app fed this same fixture, and production geometry is proved by pytest, not by pixels.

The plan specified 0.005 and that produced 152,296 bytes, which `MAX_FIXTURE_BYTES` refused. Per
the plan's own instruction ("raise `SIMPLIFY_DEG` in steps of 0.005 and regenerate until it fits"),
this is the FIRST step that fits: 0.010 gives 112,986 bytes. Measured at 0.005/0.010/0.015/0.020/
0.025, the feature counts are identical at every tolerance (88 ZCTAs, 72 places, 5 counties), so
the coarsening drops detail from polygon outlines and drops no polygon.

TWO MEASURED PROPERTIES THE NEXT PERSON TO REGENERATE NEEDS, both found in Task 3 and neither
anticipated by the plan. Reported to the controller; NOT worked around here, because both the
tolerance and the cap are the plan's own ruled numbers.

(1) THIS SCRIPT IS NOT REPRODUCIBLE, and the cause is `ST_SimplifyPreserveTopology`, not this code.
    Six identical queries against one unchanging row in a SINGLE psql session returned FIVE distinct
    geometries (PostGIS 3.5 / GEOS). Across four whole runs of this script the ids, the counts and
    the centroids were identical every time and only three of the 72 PLACE polygons differed, in how
    many vertices survived simplification. `ST_Simplify` (Douglas-Peucker) IS deterministic -- 1
    distinct result from 6 -- but it is the wrong trade: it returns NULL for 5 of the 165 polygons
    (they vanish) and leaves 12 invalid against this function's 5. So the plan's choice is right on
    the merits and merely unstable byte for byte.
    WHY IT MATTERS: A24.1 interpolates this file's literal VERBATIM into the approved design file.
    Regenerating it therefore moves the design file, and every map baseline with it, for no design
    reason -- and a reviewer cannot tell that drift from a real change. Treat the COMMITTED bytes as
    the artefact; regenerate only for a deliberate, ruled reason (a new vintage, a new metro).

(2) THE COARSENING THE CAP FORCED COST VALIDITY, AND D-C49 RULED THE REPAIR. Invalid polygons among
    the 165, by tolerance: unsimplified 0 · 0.005 -> 1 · 0.010 -> 5 · 0.015 -> 6 (self-intersections
    and holes that end up outside their shell). Halving the tolerance leaves 1 but needs ~155 KB
    against a 120 KB cap, so John ruled on 2026-09-11: coarsen as committed, then REPAIR. Measured
    after `ST_MakeValid` on the real fixture: 0 of 165 invalid, exactly those 5 polygons changed and
    the other 160 byte-identical, worst case 1.41 % of a polygon's area and 52 m of its centroid --
    against a coarsening that already moves one ZCTA's area by 110 % and its centroid by 931 m, so
    the repair is nowhere near the dominant source of drift here. The cap is.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import psycopg2
import psycopg2.extensions

# Austin-Round Rock-San Marcos: the design's own metro, and `MARKETS`'s default (`logic.js`).
DESIGN_CBSA = "12420"
# D-C35's three, in the order the fixture lists them: TRACT (income), place (growth), county
# (econ). `income` moved 860 -> 140 on 2026-09-12 (controller ruling): the canonical granular unit
# is the Census tract, nationwide. `growth` and `econ` did NOT move -- growth cannot be computed at
# tract level across the 2010->2020 boundary change (plan D12) -- so this fixture deliberately
# mixes geographies, exactly as the map does.
LEVELS: tuple[str, ...] = ("140", "160", "050")
# 0.005, not 0.010, and the CAP moved with it -- both MEASURED, and the reason is that the Austin
# metro holds 503 TRACTS where it held 88 ZCTAs. Module bytes at level 140, measured on real TIGER
# geometry: 0.010 -> 220,905 · 0.005 -> 254,550 · 0.002 -> 348,023 · 0.001 -> 455,750 · 0.0005 ->
# 579,736. Every one of those is over the old 120,000 cap, so the cap could not survive the ruling
# in any case; 0.010 would also collapse a tract, which is typically 0.01-0.03 deg across, to a
# triangle, where on a ZCTA it merely coarsened an outline.
#
# THE CAP IS A BUNDLE BUDGET, NOT AN AESTHETIC ONE, and that is why it is not simply removed: A24.1
# interpolates this payload verbatim into the design's `state` literal, `frontend/src/logic.js`
# carries the same bytes as the hand port, and logic.js SHIPS. Measured headroom at the time of
# this change: the main bundle is 141.6 KB gzipped against `bundle-budget.test.ts`'s 220 KB, so
# 78 KB gzipped is what the fixture may grow by. 0.005 is the finest tolerance that fits with room
# to spare; the app itself never reads the fixture (with a `market` adapter present `loadAreas`
# fetches real polygons and the fixture path never runs), so every one of these bytes is paid for
# the REFERENCE's benefit alone. That is a real cost and it is recorded rather than hidden.
SIMPLIFY_DEG = 0.005
MAX_FIXTURE_BYTES = 280_000

# Scoped by CENTROID-inside-the-metro, not by ST_Intersects: a place or a ZCTA that merely grazes
# the metro boundary belongs to its neighbour, and an intersects test would drag a ring of
# half-outside polygons into a fixture whose whole job is to be small. The CBSA row is joined at
# the SAME vintage as the geography, never at a hard-coded one.
#
# COARSEN, THEN REPAIR (D-C49, John, 2026-09-11). `ST_SimplifyPreserveTopology` at this tolerance
# leaves 5 of the Austin fixture's 165 polygons INVALID -- self-intersections, and holes that end
# up outside their shell -- and halving the tolerance leaves 1 but needs ~155 KB against a 120 KB
# cap. The ruling is to keep the tolerance and repair the output. Measured on the real fixture
# after `ST_MakeValid`: 0 of 165 invalid, exactly those 5 polygons changed and the other 160
# byte-identical, worst case 1.41 % of a polygon's area and 52 m of its centroid -- against a
# coarsening that already moves one ZCTA's area by 110 % and its centroid by 931 m. The repair is
# therefore nowhere near the dominant source of drift in this fixture; the cap is.
#
# `ST_CollectionExtract(..., 3)` is the explicit handling the type change needs, not decoration:
# `ST_MakeValid` answers a spike with a GEOMETRYCOLLECTION of the polygon AND the dangling line,
# and a GeoJSON `GeometryCollection` would reach `L.geoJSON` on both targets and draw that line as
# a stroke the design has no class for. Extracting the areal parts leaves a geometry that is
# already a Polygon or a MultiPolygon untouched, so the fixture's type mix moves only where a
# repair really did split a polygon (142/23 -> 139/26) and its payload grows by 18 bytes.
_SQL = """
SELECT g.summary_level, g.geo_id, g.name,
       ST_AsGeoJSON(ST_CollectionExtract(
           ST_MakeValid(ST_SimplifyPreserveTopology(ST_Transform(g.geom, 4326), %(tol)s)), 3), 5) AS geometry,
       ST_Y(ST_Transform(g.centroid, 4326)) AS lat,
       ST_X(ST_Transform(g.centroid, 4326)) AS lng
  FROM geo_area g
  JOIN geo_area m ON m.summary_level = '310' AND m.vintage = g.vintage AND m.geo_id = %(cbsa)s
 WHERE g.summary_level = ANY(%(levels)s) AND g.vintage = %(vintage)s
   AND ST_Contains(m.geom, g.centroid)
 ORDER BY g.summary_level, g.geo_id
"""


def export(conn: psycopg2.extensions.connection, cbsa_geoid: str, geo_vintage: str) -> dict[str, dict[str, Any]]:
    """One `FeatureCollection` per ruled summary level, keyed by that level."""
    fixture: dict[str, dict[str, Any]] = {level: {"type": "FeatureCollection", "features": []} for level in LEVELS}
    with conn.cursor() as cur:
        cur.execute(_SQL, {"tol": SIMPLIFY_DEG, "cbsa": cbsa_geoid, "levels": list(LEVELS), "vintage": geo_vintage})
        for level, geo_id, name, geometry, lat, lng in cur.fetchall():
            fixture[level]["features"].append({
                "type": "Feature",
                "id": geo_id,
                "properties": {"geo_id": geo_id, "name": name, "c": [round(float(lat), 5), round(float(lng), 5)]},
                "geometry": json.loads(geometry),
            })
    return fixture


def module_text(fixture: dict[str, dict[str, Any]]) -> str:
    """The generated TypeScript module. The payload is `ensure_ascii=True` JSON on ONE line, so the
    design file gains no non-ASCII byte and a regeneration is a one-line diff; `\\` and `'` are
    escaped because it is emitted as a single-quoted TS string, and it is interpolated back into
    A24.1's `replace` verbatim, since JSON is valid JavaScript object-literal syntax."""
    payload = json.dumps(fixture, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    escaped = payload.replace("\\", "\\\\").replace("'", "\\'")
    counts = ", ".join(f"{level}: {len(fixture[level]['features'])}" for level in LEVELS)
    return (
        # PURE ASCII, every byte of it. Two gates assert it -- this module's pytest case and
        # `design-boundary-fixture.test.ts` -- because the payload below is interpolated verbatim
        # into the approved design file by A24.1, and a stray em dash would change that file's
        # encoding footprint. So the punctuation here is ASCII on purpose: `--`, not an em dash.
        "// GENERATED by scripts/export_design_boundaries.py -- never hand-edited.\n"
        "//\n"
        "// The DESIGN's own boundary fixture (amendment A24.1, spec 2026-09-10 section 9.4):\n"
        "// real `geo_area` polygons for the design's own Austin metro, at D-C35's three\n"
        "// geographies -- '140' tract (income), '160' place (growth), '050' county (econ) --\n"
        # Interpolated, never retyped: a tolerance named in two places is one that goes stale in
        # one of them (Global Constraint (i)).
        f"// simplified at {SIMPLIFY_DEG} degrees, scoped to polygons whose centroid is in CBSA 12420.\n"
        "//\n"
        "// GEOMETRY ONLY. Each feature carries `c: [lat, lng]`, its own centroid, and no figure:\n"
        "// the design's `areaSet` assigns it the value of the nearest of the design's own nine\n"
        "// Austin communities, which is `mosaicCells`'s assignment rule on real polygons.\n"
        f"// Feature counts at generation: {counts}.\n"
        f"export const DESIGN_AREAS_LITERAL = '{escaped}';\n"
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="write the design's boundary fixture from geo_area")
    p.add_argument("--out", default="frontend/tests/design-boundary-fixture.ts")
    p.add_argument("--cbsa", default=DESIGN_CBSA)
    p.add_argument("--vintage", default="2023")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[export_design_boundaries] DATABASE_URL is not set", file=sys.stderr)
        return 2
    conn = psycopg2.connect(dsn)
    try:
        fixture = export(conn, args.cbsa, args.vintage)
    finally:
        conn.close()
    text = module_text(fixture)
    size = len(text.encode("utf-8"))
    if size > MAX_FIXTURE_BYTES:
        print(f"[export_design_boundaries] fixture is {size} bytes, over the {MAX_FIXTURE_BYTES} cap", file=sys.stderr)
        return 1
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote " + args.out + ": " + ", ".join(f"{level}={len(fixture[level]['features'])}" for level in LEVELS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
