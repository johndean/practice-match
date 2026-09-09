"""ACS 5-year loads (spec §2 acs5 / acs5_subject / acs5_prior, §4 variables, §6 levels).
Long format: one `acs_measure` row per (geo, variable); each `_E` carries its `_M` as moe.

`load()` uses `CensusClient` through the interface A3's review round actually committed
(controller amendment A-C3b), not the task brief's illustrative draft: `fetch_table` takes the
raw `(get, for_, expected, in_)` parameters and validates internally (m5) -- there is no public
`build_url`/`validate_variables` pair for a caller to chain -- and the client owns its own
`httpx.Client` through `__enter__`/`__exit__` (m3), so `load()` uses it as a context manager
rather than calling `close()` itself.

A response missing an expected variable raises `VariableMissing` from inside `fetch_table`,
before any row from that geography is written; `ingest.run()` records that as `'aborted'` and
rolls back whatever the run had written so far -- a partial load never activates a vintage
(global constraint ¶12)."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import psycopg2.extensions

from app.census import ingest
from app.census.client import CensusClient
from app.census.registry import Dataset
from app.census.registry import load as load_registry

VARIABLES: dict[str, list[str]] = {
    "acs5": ["B01003_001E", "B01003_001M", "B11001_001E", "B11001_001M", "B19013_001E", "B19013_001M",
             "B19301_001E", "B01002_001E", "B25003_002E", "B25001_001E"],
    "acs5_subject": ["S1501_C02_015E"],
    "acs5_prior": ["B01003_001E", "B01003_001M"],
}

CBSA_COL = "metropolitan statistical area/micropolitan statistical area"


@dataclass(frozen=True)
class Geo:
    summary_level: str
    for_: str
    in_: str | None


@dataclass(frozen=True)
class Measure:
    geo_id: str
    summary_level: str
    variable: str
    estimate: Decimal | None
    moe: Decimal | None


def GEOGRAPHIES(states: list[str]) -> list[Geo]:
    geos: list[Geo] = []
    for st in states:
        geos += [
            Geo("140", "tract:*", f"state:{st}"),
            Geo("160", "place:*", f"state:{st}"),
            Geo("050", "county:*", f"state:{st}"),
            Geo("040", f"state:{st}", None),
        ]
    geos += [Geo("310", f"{CBSA_COL}:*", None), Geo("010", "us:1", None)]
    return geos


def geoid(row: Mapping[str, str | None], summary_level: str) -> str:
    def field(key: str) -> str:
        value = row.get(key)
        if value is None:
            raise ValueError(f"geography row missing {key!r} for summary_level {summary_level!r}")
        return value

    if summary_level == "140":
        return field("state") + field("county") + field("tract")
    if summary_level == "160":
        return field("state") + field("place")
    if summary_level == "050":
        return field("state") + field("county")
    if summary_level == "040":
        return field("state")
    if summary_level == "310":
        return field(CBSA_COL)
    if summary_level == "010":
        return field("us")
    raise ValueError(summary_level)


def _num(v: str | None) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def to_measures(rows: list[dict[str, str | None]], variables: list[str], summary_level: str) -> list[Measure]:
    estimates = [v for v in variables if v.endswith("E")]
    out: list[Measure] = []
    for row in rows:
        gid = geoid(row, summary_level)
        for var in estimates:
            moe_var = var[:-1] + "M"
            out.append(Measure(
                gid, summary_level, var, _num(row.get(var)),
                _num(row.get(moe_var)) if moe_var in variables else None,
            ))
    return out


UPSERT = """
INSERT INTO acs_measure (geo_id, summary_level, vintage, variable, estimate, moe, ingest_run_id)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (geo_id, summary_level, vintage, variable) DO UPDATE
SET estimate = EXCLUDED.estimate, moe = EXCLUDED.moe, ingest_run_id = EXCLUDED.ingest_run_id
"""


def load(
    conn: psycopg2.extensions.connection,
    client_factory: Callable[[Dataset], CensusClient],
    dataset_key: str,
    states: list[str],
) -> int:
    ds = load_registry(conn)[dataset_key]
    if not ds.cleared:
        raise PermissionError(f"{dataset_key} is {ds.license_status}; loads are refused (spec §1 licensing gate)")
    variables = VARIABLES[dataset_key]
    with ingest.run(conn, dataset_key, ds.vintage) as run, client_factory(ds) as client:
        for geo in GEOGRAPHIES(states):
            rows = client.fetch_table(["NAME", *variables], geo.for_, variables, geo.in_)
            measures = to_measures(rows, variables, geo.summary_level)
            with conn.cursor() as cur:
                cur.executemany(
                    UPSERT,
                    [(m.geo_id, m.summary_level, ds.vintage, m.variable, m.estimate, m.moe, run.id) for m in measures],
                )
            run.rows += len(measures)
        run.requests = client.request_count
        return run.rows
