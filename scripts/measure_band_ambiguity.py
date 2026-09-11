"""D-C34's trigger for the tract toggle, as a number rather than a date.

"A tract toggle follows, and ITS TRIGGER IS A MEASUREMENT, NOT A DATE: the share of tract polygons
whose margin of error spans more than one legend band, measured under D-C36 and reported before
the toggle is built." This reports that share per summary level, from `geo_metric` and
`app.census.bands`. It runs nowhere on the request path and builds nothing.
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2
import psycopg2.extensions

from app.census.bands import band_ambiguous


def measure(conn: psycopg2.extensions.connection, metric_key: str, vintage: str) -> dict[str, dict[str, int]]:
    """`{summary_level: {polygons, with_value, with_moe, ambiguous}}` for one metric and vintage.

    Every polygon in the table is counted, including the ones with no figure: the share that
    matters to D-C34 is over the polygons a reader would SEE, and a no-data polygon is drawn.

    `value_num` and `moe` are `numeric`, so psycopg2 hands back `Decimal`; both are cast to
    `float` before `band_ambiguous` rather than compared as `Decimal`, because `INCOME_STOPS` is
    a tuple of `int` and mixing the two silently works today and is one arithmetic change from
    not working."""
    out: dict[str, dict[str, int]] = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT summary_level, value_num, moe FROM geo_metric WHERE metric_key = %s AND vintage = %s",
            (metric_key, vintage),
        )
        for level, value, moe in cur.fetchall():
            row = out.setdefault(level, {"polygons": 0, "with_value": 0, "with_moe": 0, "ambiguous": 0})
            row["polygons"] += 1
            if value is not None:
                row["with_value"] += 1
            if moe is not None:
                row["with_moe"] += 1
            if band_ambiguous(None if value is None else float(value), None if moe is None else float(moe)):
                row["ambiguous"] += 1
    return out


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="report the share of polygons whose margin spans a legend band")
    p.add_argument("--metric", default="median_hh_income")
    p.add_argument("--vintage", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[measure_band_ambiguity] DATABASE_URL is not set", file=sys.stderr)
        return 2
    conn = psycopg2.connect(dsn)
    try:
        result = measure(conn, args.metric, args.vintage)
    finally:
        conn.close()
    for level in sorted(result):
        row = result[level]
        share = (100.0 * row["ambiguous"] / row["with_moe"]) if row["with_moe"] else 0.0
        print(
            f"{level}: {row['polygons']} polygons, {row['with_value']} with a value, "
            f"{row['with_moe']} with a margin, {row['ambiguous']} ambiguous ({share:.1f}% of those with a margin)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
