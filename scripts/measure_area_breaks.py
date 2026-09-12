"""The choropleth's class breaks, as a measurement rather than a choice.

`AREA_LAYERS` in the design (amendment A24.25) cuts the three COUNT layers at the scale the MAP
paints, which is a different distribution from the community cards `VALUE_LAYERS` classes: 1,480
households is an ordinary Census tract and an implausibly small city. A break table nobody can
re-derive is a guess with a date on it, so this reports the served distribution and what each
candidate cut does to it -- the precedent is `scripts/measure_band_ambiguity.py`, and like it this
runs nowhere on the request path and builds nothing.

It reads what the ROUTE WOULD SERVE, not what the table holds: a suppressed row is `value: null`
on the wire (`app/api/market.py::_boundary_feature`), so it is not part of the distribution a
legend describes. That distinction is the whole reason the competition breaks moved -- ZIP Code
Business Patterns publishes no count for a category under three establishments, so the served
distribution has a FLOOR of three and a first class labelled "1-3" promises two counts the data
cannot hold.

Measured on QA, 2026-09-12, and printed into `LOCAL_AMENDMENTS.md`'s A24.25 and A24.37 rows:

    households  140  83,783 served  p25 1,054  p50 1,446  p75 1,897   [1000, 1500, 2000]
                -> 21.9 / 31.4 / 26.0 / 20.7 %      (the design's [10000, 25000, 45000]: 100.0 / 0 / 0 / 0)
    pets        140  83,783 served  p25   601  p50   824  p75 1,081   [600, 850, 1100]
                -> 24.9 / 27.9 / 23.7 / 23.5 %
    competition 860   4,719 served  min 3  p50 4  p75 6  p90 8        [4, 6, 10]
                -> 37.0 / 36.1 / 21.4 / 5.5 %       (the design's [3, 6, 10]: first class EMPTY, 73.1 % in one)
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2
import psycopg2.extensions


def served(conn: psycopg2.extensions.connection, metric_key: str, vintage: str) -> list[float]:
    """Every value the route would actually put on the wire for one metric, sorted.

    Suppressed rows are excluded because the endpoint serves them as `null` whatever their
    `value_num` says, and a class break is a statement about the values a member can see."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT value_num FROM geo_metric WHERE metric_key = %s AND vintage = %s "
            "AND value_num IS NOT NULL AND NOT suppressed ORDER BY value_num",
            (metric_key, vintage),
        )
        return [float(v) for (v,) in cur.fetchall()]


def quantile(values: list[float], p: float) -> float | None:
    """The value at `p` of a SORTED list, by position -- the same rule the design's own `bucket`
    reads a break with, and deliberately not an interpolating quantile: a break is compared
    against a value that exists."""
    return values[int(p * (len(values) - 1))] if values else None


def shares(values: list[float], stops: list[float]) -> list[float]:
    """The percentage of `values` in each class under `stops`, using the DESIGN's own right-open
    rule (`logic.js`'s `bucket`: `while (i < stops.length && v >= stops[i]) i++`), so a number
    printed here is the share a legend class really holds."""
    counts = [0] * (len(stops) + 1)
    for v in values:
        i = 0
        while i < len(stops) and v >= stops[i]:
            i += 1
        counts[i] += 1
    return [(100.0 * c / len(values)) if values else 0.0 for c in counts]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="report the served distribution of a shaded layer and what a cut does to it")
    p.add_argument("--metric", required=True)
    p.add_argument("--vintage", required=True)
    p.add_argument("--stops", required=True, help="comma-separated, e.g. 1000,1500,2000")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[measure_area_breaks] DATABASE_URL is not set", file=sys.stderr)
        return 2
    stops = [float(s) for s in args.stops.split(",")]
    conn = psycopg2.connect(dsn)
    try:
        values = served(conn, args.metric, args.vintage)
    finally:
        conn.close()
    if not values:
        print(f"[measure_area_breaks] {args.metric} @ {args.vintage}: nothing served", file=sys.stderr)
        return 1
    marks = " ".join(f"p{int(p * 100)} {quantile(values, p):g}" for p in (0.25, 0.5, 0.75, 0.9))
    print(f"{args.metric} @ {args.vintage}: {len(values)} served, min {values[0]:g}, max {values[-1]:g}, {marks}")
    print("  " + " / ".join(f"{s:.1f}" for s in shares(values, stops)) + f" %  on {stops}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
