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
records the same operator name as always in `active_vintage.activated_by` and only afterwards.

`active_vintage.note` (A-C7 concern 1) is the persisted "why": `activate(..., note=None)` stores
whatever the caller passes (`None` by default) and the returned `Report` carries the SAME value
back, so the CLI's printed Report is not the only place a forced override's reason lives."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

import psycopg2.extensions

TABLE_FOR = {
    "acs5": "acs_measure",
    "acs5_subject": "acs_measure",
    "acs5_prior": "acs_measure",
    "cbp": "cbp_industry",
    "zbp": "zbp_industry",
    "bds": "bds_measure",
    # `geo_area` carries no `ingest_run_id` column and holds only one dataset (`tiger_cb`), so a
    # vintage-only count is unambiguous; every other table above is counted scoped to its own
    # `ingest_run.dataset_key` (A-C7 M2) because up to three dataset_keys share one table here.
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
    note: str | None = None  # `qa()` never sets this (it is not a diff of anything); `activate()` fills it in from its own `note` argument


def active(conn: psycopg2.extensions.connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, vintage FROM active_vintage")
        return dict(cur.fetchall())


def _count(cur: psycopg2.extensions.cursor, table: str, dataset_key: str, vint: str) -> int:
    """`geo_area` (the `tiger_cb` table) has no `ingest_run_id` column and holds only one
    dataset, so its count is vintage-only; every other table is scoped to the dataset's OWN
    `ingest_run` rows (A-C7 M2) -- `acs5`/`acs5_subject`/`acs5_prior` share `acs_measure` and, in
    real registry data, `acs5`/`acs5_subject` share a vintage string too, so an unscoped count
    would blend them (task-A7-review Major 2)."""
    if table == "geo_area":
        cur.execute(f"SELECT count(*) FROM {table} WHERE vintage = %s", (vint,))  # table from the static TABLE_FOR map, never user input
    else:
        cur.execute(
            f"SELECT count(*) FROM {table} m JOIN ingest_run r ON r.id = m.ingest_run_id WHERE m.vintage = %s AND r.dataset_key = %s",  # table from the static TABLE_FOR map, never user input
            (vint, dataset_key),
        )
    return cast("tuple[int]", cur.fetchone())[0]


def qa(conn: psycopg2.extensions.connection, dataset_key: str, vint: str) -> Report:
    table = TABLE_FOR[dataset_key]
    prior = active(conn).get(dataset_key)
    with conn.cursor() as cur:
        rows_new = _count(cur, table, dataset_key, vint)
        rows_prior = 0
        if prior and prior != vint:
            rows_prior = _count(cur, table, dataset_key, prior)
        cur.execute(
            "SELECT status FROM ingest_run WHERE dataset_key = %s AND vintage = %s ORDER BY id DESC LIMIT 1",
            (dataset_key, vint),
        )
        row = cur.fetchone()
    ratio = (rows_new / rows_prior) if rows_prior else None
    return Report(dataset_key, vint, prior if prior != vint else None, rows_new, rows_prior, ratio, row[0] if row else None)


def activate(
    conn: psycopg2.extensions.connection, dataset_key: str, vint: str, by: str, *, force: bool = False, note: str | None = None
) -> Report:
    rep = qa(conn, dataset_key, vint)
    if rep.last_run_status != "succeeded":
        raise ActivationRefused(f"latest ingest_run for {dataset_key} {vint} is {rep.last_run_status!r}, not 'succeeded'")
    if rep.ratio is not None and not (LOW <= rep.ratio <= HIGH) and not force:
        raise ActivationRefused(
            f"row count ratio {rep.ratio:.2f} vs active vintage {rep.prior_vintage} is outside [{LOW}, {HIGH}]; pass force=True after review"
        )
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by, note) VALUES (%s, %s, now(), %s, %s)
               ON CONFLICT (dataset_key) DO UPDATE SET vintage = EXCLUDED.vintage, activated_at = now(), activated_by = EXCLUDED.activated_by, note = EXCLUDED.note""",
            (dataset_key, vint, by, note),
        )
    return replace(rep, note=note)
