"""What `GET /api/markets/{cbsa}/boundaries` would emit for a box, per delivery tier.

The tool the boundary caps were set from (Task CAP, 2026-09-12), committed because the numbers in
`app/api/market.py`'s cap comment are only as good as the ability to take them again — at the next
TIGER vintage, at the next summary level, or the next time someone asks whether a cap still fits
the geography. Precedent: `scripts/measure_band_ambiguity.py`, which exists for the same reason.

It reuses the route's OWN `_BOUNDARY_SQL` — the same `CAST(:tol)`, the same
`ST_SimplifyPreserveTopology`, the same `ST_AsGeoJSON(…, 6)` — and reports the byte total the
route's `compose()` would produce, so the figures are the route's rather than a model of one.

Two modes, because a remote database and a local one want different things:

  --mode exact   pull the geometry, build the real body, `json.dumps(...).encode()`, gzip it. The
                 authority, and the only mode that can report a GZIPPED size.
  --mode length  compute the same byte total SERVER-side and return one row per tier, so a database
                 across a TCP proxy is measured without pulling tens of megabytes per tier. It was
                 validated against `exact` before it was trusted: on a 5,113-tract box tier 0
                 matched byte for byte and the simplified tiers agreed within 18 bytes, which is
                 `ST_SimplifyPreserveTopology`'s own non-determinism and not arithmetic.

`--sweep` answers the other question the caps needed: the densest box `MAX_BBOX_DEG` admits
anywhere, by counting tracts in a `MAX_BBOX_DEG`-square window around every point of a lattice over
the lower 48.

READ-ONLY throughout: the connection is opened read-only, every statement is a SELECT, and nothing
here writes, migrates or caches. It runs nowhere on the request path.

    DATABASE_URL=… poetry run python scripts/measure_boundary_caps.py --box ny-default-padded
    DATABASE_URL=… poetry run python scripts/measure_boundary_caps.py --sweep --top 5
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from typing import Any, cast

import psycopg2
import psycopg2.extensions
from sqlalchemy.engine import RowMapping

from app.api.market import _BOUNDARY_SQL, MAX_BBOX_DEG, SIMPLIFY_TIERS, _boundary_feature
from app.census.bands import INCOME_STOPS

#: The views the caps were measured against, all on the stakeholder's own 1460 x 1228 px map.
#: `minLng, minLat, maxLng, maxLat`, exactly as the route takes a `bbox`.
BOXES: dict[str, tuple[float, float, float, float]] = {
    "ny-default-padded": (-75.629883, 39.682617, -72.377930, 41.748047),
    "ny-default-bare": (-75.058594, 40.078125, -72.993164, 41.396484),
    "manhattan-z10-padded": (-75.585938, 39.726563, -72.333984, 41.835938),
    "manhattan-z11-padded": (-74.772949, 40.253906, -73.146973, 41.308594),
    "densest-legal-box": (-77.0, 38.5, -73.0, 42.5),
}

#: `compose()`'s envelope. It is a few hundred bytes against tens of megabytes of geometry, but it
#: is carried so the total is the ROUTE's total and not the features' alone.
ENVELOPE: dict[str, Any] = {
    "type": "FeatureCollection", "cbsa_geoid": "", "layer": "", "metric_key": "",
    "summary_level": "", "geo_label": "", "unit": "usd", "state": "enabled",
    "boundary_vintage": "", "value_vintage": "", "source_dataset": "",
    "attribution": ["", ""], "values_without_geometry": 0, "simplified_deg": 0.0, "features": [],
}

# `json.dumps` with DEFAULT separators (", " / ": ") — the route never passes `separators=`, so
# every comma and colon in the geometry costs two bytes rather than one, which is why the geometry
# term below adds the comma and colon counts back. Each constant is the KEY it stands for, without
# its value; the values are measured per row, because every one of them varies:
#   {"type": "Feature", "id":  26   , "properties": {  17   "geo_id":  10   , "name":  10
#   , "value":  11   , "moe":  9    , "suppressed":  16   , "suppress_reason":  21
#   , "band_ambiguous":  20   }  1   , "geometry":  14   }  1
_FIXED = 26 + 17 + 10 + 10 + 11 + 9 + 16 + 21 + 20 + 1 + 14 + 1

# `band_ambiguous` decides `true` (4 bytes) or `false` (5), and it is 1 byte per feature that this
# arithmetic got wrong until the two modes were compared. Built from `app.census.bands`'s OWN
# stops rather than typed here, and spelling `band_index`'s right-open rule (`value >= stop` moves
# up a band) exactly, so the tool cannot drift from the module the route uses.
def _band_index(expr: str) -> str:
    return " + ".join(f"(CASE WHEN {expr} >= {s} THEN 1 ELSE 0 END)" for s in INCOME_STOPS)


_AMBIGUOUS = (
    f"(m.value_num IS NOT NULL AND COALESCE(m.moe, 0) <> 0 "
    f"AND ({_band_index('(m.value_num - m.moe)')}) <> ({_band_index('(m.value_num + m.moe)')}))"
)

# Python renders a float with `repr`, which always carries a `.` or an `e`; PostgreSQL's `to_json`
# prints 92150::float8 as `92150`. Two bytes per whole-numbered figure, twice per feature — which
# is most of the other 8 bytes the mode comparison caught.
def _float_len(col: str) -> str:
    return (f"CASE WHEN {col} IS NULL THEN 4 ELSE length(to_json({col}::float8)::text) "
            f"+ CASE WHEN to_json({col}::float8)::text ~ '[.e]' THEN 0 ELSE 2 END END")

_LEN_SQL = f"""
SELECT count(*) AS features,
       COALESCE(SUM(
         {_FIXED}
         + 2 * (length(g.geo_id) + 2)
         + length(to_json(g.name)::text)
         + CASE WHEN COALESCE(m.suppressed, false) THEN 4 ELSE {_float_len('m.value_num')} END
         + ({_float_len('m.moe')})
         + CASE WHEN COALESCE(m.suppressed, false) THEN 4 ELSE 5 END
         + length(COALESCE(to_json(m.suppress_reason)::text, 'null'))
         + CASE WHEN {_AMBIGUOUS} THEN 4 ELSE 5 END
         + length(gj) + (length(gj) - length(replace(gj, ',', '')))
                      + (length(gj) - length(replace(gj, ':', '')))
       ), 0) AS feature_bytes
  FROM geo_area g
  LEFT JOIN geo_metric m
    ON m.geo_id = g.geo_id AND m.summary_level = g.summary_level
   AND m.metric_key = %(metric)s AND m.vintage = %(value_vintage)s
  CROSS JOIN LATERAL (SELECT ST_AsGeoJSON(ST_Transform(
        CASE WHEN CAST(%(tol)s AS double precision) > 0
             THEN ST_SimplifyPreserveTopology(g.geom, CAST(%(tol)s AS double precision))
             ELSE g.geom END, 4326), 6) AS gj) j
 WHERE g.summary_level = %(level)s AND g.vintage = %(geo_vintage)s
   AND ST_Intersects(g.geom, ST_Transform(ST_MakeEnvelope(%(w)s, %(s)s, %(e)s, %(n)s, 4326), 4269))
"""

_SWEEP_SQL = f"""
WITH centres AS (
  SELECT lon, lat FROM generate_series(-124.0, -68.0, %(step)s) AS lon,
                       generate_series(25.0, 48.0, %(step)s) AS lat
)
SELECT c.lon, c.lat,
       (SELECT count(*) FROM geo_area g
         WHERE g.summary_level = %(level)s AND g.vintage = %(geo_vintage)s
           AND ST_Intersects(g.geom, ST_Transform(ST_MakeEnvelope(
                 c.lon - {MAX_BBOX_DEG / 2}, c.lat - {MAX_BBOX_DEG / 2},
                 c.lon + {MAX_BBOX_DEG / 2}, c.lat + {MAX_BBOX_DEG / 2}, 4326), 4269))) AS tracts
  FROM centres c
 ORDER BY tracts DESC
 LIMIT %(top)s
"""

#: The route's own SQL, with SQLAlchemy's `:name` bind markers rewritten for psycopg2. Done by
#: substitution rather than by keeping a second copy, so this tool cannot drift from the route.
_ROUTE_SQL = _BOUNDARY_SQL
for _name in ("tol", "metric", "value_vintage", "level", "geo_vintage", "w", "s", "e", "n"):
    _ROUTE_SQL = _ROUTE_SQL.replace(f":{_name}", f"%({_name})s")


def active_vintages(conn: psycopg2.extensions.connection) -> dict[str, str]:
    """`{dataset_key: vintage}` — the same table the route reads, so a measurement is taken against
    the vintages that are actually being served."""
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, vintage FROM active_vintage ORDER BY activated_at")
        return dict(cur.fetchall())


def params(box: tuple[float, float, float, float], tol: float, level: str,
           geo_vintage: str, value_vintage: str, metric: str) -> dict[str, Any]:
    w, s, e, n = box
    return {"metric": metric, "value_vintage": value_vintage, "level": level,
            "geo_vintage": geo_vintage, "w": w, "s": s, "e": e, "n": n, "tol": tol}


def envelope_bytes(n: int) -> int:
    """What the per-feature sum must be added to: the envelope plus the ", " between features.
    Measured rather than assumed — compose the same body with `n` empty objects and subtract."""
    body = dict(ENVELOPE, features=[{}] * n)
    return len(json.dumps(body).encode("utf-8")) - 2 * n


def measure_tier(conn: psycopg2.extensions.connection, p: dict[str, Any], mode: str) -> tuple[int, int, int | None]:
    """`(features, raw_bytes, gzip_bytes | None)` for one box at one tier."""
    with conn.cursor() as cur:
        if mode == "exact":
            cur.execute(_ROUTE_SQL, p)
            # `cur.description` is Optional to mypy and never None after a SELECT that returned;
            # the assert is the narrowing, not a hope.
            assert cur.description is not None
            cols = [c.name for c in cur.description]
            # `_boundary_feature` is typed for SQLAlchemy's `RowMapping` and reads it by key only,
            # which a dict satisfies; the cast says so rather than loosening the route's own type.
            rows = [cast("RowMapping", dict(zip(cols, r, strict=True))) for r in cur.fetchall()]
            body = dict(ENVELOPE, simplified_deg=p["tol"],
                        features=[_boundary_feature(row, "income") for row in rows])
            raw = json.dumps(body).encode("utf-8")
            return len(rows), len(raw), len(gzip.compress(raw))
        cur.execute(_LEN_SQL, p)
        row = cur.fetchone()
        assert row is not None, "the length query aggregates and always returns exactly one row"
        features, feature_bytes = row
        return int(features), int(feature_bytes) + envelope_bytes(int(features)), None


def measure_box(conn: psycopg2.extensions.connection, box: tuple[float, float, float, float],
                mode: str, level: str, metric: str, vintages: tuple[str, str]) -> list[dict[str, Any]]:
    """One row per delivery tier, in `SIMPLIFY_TIERS` order — the order the route walks them."""
    span = max(box[2] - box[0], box[3] - box[1])
    out: list[dict[str, Any]] = []
    for frac in SIMPLIFY_TIERS:
        tol = span * frac
        features, raw, packed = measure_tier(
            conn, params(box, tol, level, vintages[0], vintages[1], metric), mode)
        out.append({"frac": frac, "tol": tol, "features": features, "raw": raw, "gzip": packed})
    return out


def sweep(conn: psycopg2.extensions.connection, level: str, geo_vintage: str,
          step: float, top: int) -> list[tuple[float, float, int]]:
    """The densest `MAX_BBOX_DEG`-square windows on a lattice over the lower 48, densest first."""
    with conn.cursor() as cur:
        cur.execute(_SWEEP_SQL, {"level": level, "geo_vintage": geo_vintage, "step": step, "top": top})
        return [(float(lon), float(lat), int(n)) for lon, lat, n in cur.fetchall()]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="what the boundary route would emit for a box, per delivery tier")
    p.add_argument("--box", action="append", choices=sorted(BOXES), help="repeatable; default every box")
    p.add_argument("--mode", choices=("exact", "length"), default="length")
    p.add_argument("--level", default="140", help="summary level; 140 is the Census tract")
    p.add_argument("--metric", default="median_hh_income")
    p.add_argument("--sweep", action="store_true", help="report the densest legal box instead")
    p.add_argument("--step", type=float, default=0.5, help="sweep lattice spacing in degrees")
    p.add_argument("--top", type=int, default=5)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[measure_boundary_caps] DATABASE_URL is not set", file=sys.stderr)
        return 2
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    try:
        active = active_vintages(conn)
        geo_vintage, value_vintage = active.get("tiger_cb", ""), active.get("acs5", "")
        print(f"# level={args.level} tiger_cb={geo_vintage!r} acs5={value_vintage!r} mode={args.mode}")
        if args.sweep:
            print("lon|lat|tracts")
            for lon, lat, n in sweep(conn, args.level, geo_vintage, args.step, args.top):
                print(f"{lon}|{lat}|{n}")
            return 0
        print("box|tier_frac|tol_deg|features|raw_bytes|gzip_bytes")
        for name in args.box or sorted(BOXES):
            for row in measure_box(conn, BOXES[name], args.mode, args.level, args.metric,
                                   (geo_vintage, value_vintage)):
                packed = "" if row["gzip"] is None else row["gzip"]
                print(f"{name}|{row['frac']}|{row['tol']:.6f}|{row['features']}|{row['raw']}|{packed}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
