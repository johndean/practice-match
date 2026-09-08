"""Vintage QA + activation (spec §1 'vintages advance only through a migration', §9 'loads to a
new vintage, runs QA diffs, then flips the active vintage flag'). `activate()` is the ONLY path
that writes `active_vintage` -- the API reads that table, never `ingest_run`, so nothing goes
live until an operator runs this (`scripts/census_load.py activate`); it never runs from a
Celery task.

`qa()` compares the candidate vintage's row count against whatever vintage is CURRENTLY active
for that dataset (not the previous ingest_run) -- `rows_prior`/`ratio` are `0`/`None` for a
dataset's first-ever activation, since there is nothing yet to divide by. `activate()` refuses
(`ActivationRefused`, never a bare exception) unless the vintage's latest `ingest_run` succeeded
and, when a prior vintage exists, the row-count ratio falls inside `[LOW, HIGH]`; `force=True`
records the same operator name as always in `active_vintage.activated_by` and only afterwards --
the `Report` returned (and printed by the CLI) is where the "why" of a forced override is read
back, since `active_vintage` itself carries no free-text reason column."""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import psycopg2.extensions

TABLE_FOR = {
    "acs5": "acs_measure",
    "acs5_subject": "acs_measure",
    "acs5_prior": "acs_measure",
    "cbp": "cbp_industry",
    "zbp": "zbp_industry",
    "bds": "bds_measure",
    "tiger_cb": "geo_area",
}
LOW, HIGH = 0.8, 1.25


class ActivationRefused(Exception):
    pass


@dataclass(frozen=True)
class Report:
    dataset_key: str
    vintage: str
    prior_vintage: str | None
    rows_new: int
    rows_prior: int
    ratio: float | None
    last_run_status: str | None


def active(conn: psycopg2.extensions.connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, vintage FROM active_vintage")
        return dict(cur.fetchall())


def qa(conn: psycopg2.extensions.connection, dataset_key: str, vint: str) -> Report:
    table = TABLE_FOR[dataset_key]
    prior = active(conn).get(dataset_key)
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table} WHERE vintage = %s", (vint,))  # table from the static TABLE_FOR map, never user input
        rows_new = cast("tuple[int]", cur.fetchone())[0]
        rows_prior = 0
        if prior and prior != vint:
            cur.execute(f"SELECT count(*) FROM {table} WHERE vintage = %s", (prior,))
            rows_prior = cast("tuple[int]", cur.fetchone())[0]
        cur.execute(
            "SELECT status FROM ingest_run WHERE dataset_key = %s AND vintage = %s ORDER BY id DESC LIMIT 1",
            (dataset_key, vint),
        )
        row = cur.fetchone()
    ratio = (rows_new / rows_prior) if rows_prior else None
    return Report(dataset_key, vint, prior if prior != vint else None, rows_new, rows_prior, ratio, row[0] if row else None)


def activate(conn: psycopg2.extensions.connection, dataset_key: str, vint: str, by: str, *, force: bool = False) -> Report:
    rep = qa(conn, dataset_key, vint)
    if rep.last_run_status != "succeeded":
        raise ActivationRefused(f"latest ingest_run for {dataset_key} {vint} is {rep.last_run_status!r}, not 'succeeded'")
    if rep.ratio is not None and not (LOW <= rep.ratio <= HIGH) and not force:
        raise ActivationRefused(
            f"row count ratio {rep.ratio:.2f} vs active vintage {rep.prior_vintage} is outside [{LOW}, {HIGH}]; pass force=True after review"
        )
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)
               ON CONFLICT (dataset_key) DO UPDATE SET vintage = EXCLUDED.vintage, activated_at = now(), activated_by = EXCLUDED.activated_by""",
            (dataset_key, vint, by),
        )
    return rep
