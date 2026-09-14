"""Quarterly Workforce Indicators (spec §2 qwi, §5 industry 5419, §9 keep 20 quarters).

`latest_available` walks back from the current quarter (QWI is published on a lag of roughly
three quarters) until a table exists -- `scripts/census_load.py qwi` uses it when
`--year`/`--quarter` are omitted, then loads that quarter and calls `trim`. Adapted from the task
brief's illustrative draft to the client interface A3's review round actually committed
(controller amendment A-C5, exactly as `acs.py`/`cbp.py`/`zbp.py` already are): `fetch_table`
takes the raw `(get, for_, expected, in_, extra)` parameters and validates internally -- there is
no public `build_url`/`validate_variables` pair to chain."""
from __future__ import annotations

from collections.abc import Callable

import psycopg2.extensions

from app.census import ingest
from app.census.client import CensusClient, CensusHTTPError
from app.census.registry import Dataset
from app.census.registry import load as load_registry

VARS = ["EarnBeg", "Emp", "HirA"]
EXTRA = {"industry": "5419", "ownercode": "A05", "seasonadj": "U"}


class NoQuarterAvailable(RuntimeError):
    """`latest_available` probed its whole twelve-quarter window and the Census published a
    table for none of it -- which is a real, reachable answer for a state absent from the QWI
    programme (Alaska, Michigan), and the exact shape `--states 02` produces.

    Named rather than left a bare `RuntimeError` for the same reason `zbp.MissingBoundaries` is:
    `scripts/census_load.py` maps it to one of the documented exit codes, and a CLI arm that
    caught every `RuntimeError` would swallow unrelated ones. A `RuntimeError` subclass, so
    nothing that already caught the bare class stops catching it (Task CENSUS-204 fix round 1,
    Important-2)."""


UPSERT = """
INSERT INTO qwi_measure (geo_id, summary_level, naics_code, year, quarter, avg_monthly_earnings, sector_employment, sector_hires, ingest_run_id)
VALUES (%s, '050', '5419', %s, %s, %s, %s, %s, %s)
ON CONFLICT (geo_id, summary_level, naics_code, year, quarter) DO UPDATE SET avg_monthly_earnings = EXCLUDED.avg_monthly_earnings,
  sector_employment = EXCLUDED.sector_employment, sector_hires = EXCLUDED.sector_hires, ingest_run_id = EXCLUDED.ingest_run_id
"""


def _int(v: str | None) -> int | None:
    return int(float(v)) if v not in (None, "") else None


def _county_geo_id(row: dict[str, str | None]) -> str:
    state, county = row.get("state"), row.get("county")
    if state is None or county is None:
        raise ValueError("QWI row missing 'state'/'county'")
    return state + county


def latest_available(client: CensusClient, state: str, *, today: tuple[int, int]) -> tuple[int, int]:
    """QWI lags ~3 quarters; walk back from the current quarter until a table exists.

    Task CENSUS-204, defect 1: the walk is seeded at TODAY's quarter, so on a ~3-quarter lag the
    very first probe is always a quarter the Census has not published -- and the Census says so
    with **HTTP 204 and a zero-byte body**, never the 404/400 this used to tolerate. A 204 is a
    2xx, so the client parsed `""` and raised `JSONDecodeError` from inside `fetch_table`: the
    404/400 arm below was never reached and this function could not succeed in production at all
    (measured on the live API 2026-09-14, `task-qwi-bds-runs-report.md` §3 root cause A). The
    client now answers `None` for that shape, which is the "keep walking" signal; the 404/400 arm
    stays for the older behaviour and any other endpoint that still answers that way, and every
    other status still propagates."""
    y, q = today
    for _ in range(12):
        try:
            if client.fetch_table(["Emp"], f"state:{state}", ["Emp"], None, {"year": str(y), "quarter": str(q), **EXTRA}) is not None:
                return (y, q)
        except CensusHTTPError as exc:
            if exc.status not in (404, 400):
                raise
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    raise NoQuarterAvailable("no QWI quarter available in the last 12")


def load(
    conn: psycopg2.extensions.connection,
    client_factory: Callable[[Dataset], CensusClient],
    states: list[str],
    *,
    year: int,
    quarter: int,
) -> int:
    ds = load_registry(conn)["qwi"]
    if not ds.cleared:
        raise PermissionError(f"qwi is {ds.license_status}; loads are refused (spec §1 licensing gate)")
    with ingest.run(conn, "qwi", f"{year}Q{quarter}") as run, client_factory(ds) as client:
        for st in states:
            rows = client.fetch_table(VARS, "county:*", VARS, f"state:{st}", {"year": str(year), "quarter": str(quarter), **EXTRA})
            if rows is None:
                # Task CENSUS-204, defect 3. A state the Census publishes nothing for is RECORDED
                # and SKIPPED; the run completes with the states that do publish. Measured on the
                # live API 2026-09-14: Alaska (02) and Michigan (26) are absent from the QWI
                # programme entirely -- 204 at every quarter back to 2022Q4, with no industry
                # filter at all, so this is not small-cell suppression and waiting never fixes it
                # -- and `ORDER BY state_fips` puts Alaska SECOND, so the run used to write
                # Alabama and then die on `json.loads("")`. Nothing here names a state: the rule
                # is measured per run, so a state that starts or stops publishing needs no code
                # change. `--states` (scripts/census_load.py) re-runs one on its own.
                run.notes.append(f"qwi: no data for state {st} at {year}Q{quarter}; skipped")
                continue
            with conn.cursor() as cur:
                cur.executemany(UPSERT, [
                    (_county_geo_id(r), year, quarter, _int(r.get("EarnBeg")), _int(r.get("Emp")), _int(r.get("HirA")), run.id)
                    for r in rows
                ])
            run.rows += len(rows)
        run.requests = client.request_count
        return run.rows


def trim(conn: psycopg2.extensions.connection, keep: int = 20) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM qwi_measure q USING (
              SELECT geo_id, summary_level, naics_code, year, quarter,
                     row_number() OVER (PARTITION BY geo_id, summary_level, naics_code ORDER BY year DESC, quarter DESC) AS rn
              FROM qwi_measure) x
            WHERE q.geo_id = x.geo_id AND q.summary_level = x.summary_level AND q.naics_code = x.naics_code
              AND q.year = x.year AND q.quarter = x.quarter AND x.rn > %s""", (keep,))
        return cur.rowcount
