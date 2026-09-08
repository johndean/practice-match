"""`ingest_run` lifecycle (spec §13). Data written inside `run()` is one transaction:
committed on success, rolled back on any failure, and the run row records the
outcome. `VariableMissing` is recorded as `'aborted'` -- a schema drift (a partial vintage
that must never go active), not an ordinary outage."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import cast

import psycopg2.extensions

from app.census.client import VariableMissing


@dataclass
class Run:
    id: int
    rows: int = 0
    requests: int = 0
    raw_uri: str | None = None
    notes: list[str] = field(default_factory=list)


def start(conn: psycopg2.extensions.connection, dataset_key: str, vintage: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingest_run (dataset_key, vintage, started_at, status) VALUES (%s, %s, now(), 'running') RETURNING id",
            (dataset_key, vintage),
        )
        return cast("tuple[int]", cur.fetchone())[0]


def finish(
    conn: psycopg2.extensions.connection,
    run_id: int,
    status: str,
    *,
    rows: int = 0,
    requests: int = 0,
    raw_uri: str | None = None,
    error: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE ingest_run SET finished_at = now(), status = %s, rows_written = %s, request_count = %s,
               raw_payload_uri = %s, error_detail = %s WHERE id = %s""",
            (status, rows, requests, raw_uri, error, run_id),
        )


@contextmanager
def run(conn: psycopg2.extensions.connection, dataset_key: str, vintage: str) -> Iterator[Run]:
    was_autocommit = conn.autocommit
    conn.autocommit = True
    run_id = start(conn, dataset_key, vintage)          # visible immediately as 'running'
    r = Run(id=run_id)
    conn.autocommit = False                              # data writes below are one transaction
    try:
        yield r
        conn.commit()
        conn.autocommit = True
        finish(conn, run_id, "succeeded", rows=r.rows, requests=r.requests, raw_uri=r.raw_uri)
    except BaseException as exc:
        conn.rollback()
        conn.autocommit = True
        status = "aborted" if isinstance(exc, VariableMissing) else "failed"
        finish(conn, run_id, status, rows=0, requests=r.requests, raw_uri=r.raw_uri, error=f"{type(exc).__name__}: {exc}"[:2000])
        raise
    finally:
        conn.autocommit = was_autocommit
