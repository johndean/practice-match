"""Business Dynamics Statistics (spec §2 bds, §4 FIRM/ESTABS_ENTRY, §5 sector 54). State level.
Adapted from the task brief's illustrative draft to the client interface A3's review round
actually committed (controller amendment A-C5, exactly as `acs.py`/`cbp.py`/`zbp.py`/`qwi.py`
already are). `ESTABS_ENTRY` (not `ESTAB_ENTRY`) is the real `timeseries/bds` variable name,
verified against the live Census metadata (controller amendment A-C6)."""
from __future__ import annotations

from collections.abc import Callable

import psycopg2.extensions

from app.census import ingest
from app.census.client import CensusClient
from app.census.registry import Dataset
from app.census.registry import load as load_registry

# A-C6: the timeseries/bds variable is `ESTABS_ENTRY` ("Number of establishments born during the
# last 12 months"), not `ESTAB_ENTRY`; the table column `estab_entry` is unchanged.
VARS = ["FIRM", "ESTABS_ENTRY"]

UPSERT = """
INSERT INTO bds_measure (geo_id, summary_level, vintage, naics_code, firms, estab_entry, ingest_run_id)
VALUES (%s, '040', %s, '54', %s, %s, %s)
ON CONFLICT (geo_id, summary_level, vintage, naics_code) DO UPDATE SET firms = EXCLUDED.firms, estab_entry = EXCLUDED.estab_entry, ingest_run_id = EXCLUDED.ingest_run_id
"""


def _int(v: str | None) -> int | None:
    return int(v) if v not in (None, "") else None


def load(conn: psycopg2.extensions.connection, client_factory: Callable[[Dataset], CensusClient], states: list[str], *, year: int) -> int:
    ds = load_registry(conn)["bds"]
    if not ds.cleared:
        raise PermissionError(f"bds is {ds.license_status}; loads are refused (spec §1 licensing gate)")
    with ingest.run(conn, "bds", str(year)) as run, client_factory(ds) as client:
        for st in states:
            rows = client.fetch_table(VARS, f"state:{st}", VARS, None, {"YEAR": str(year), "NAICS": "54"})
            with conn.cursor() as cur:
                cur.executemany(UPSERT, [(r["state"], str(year), _int(r.get("FIRM")), _int(r.get("ESTABS_ENTRY")), run.id) for r in rows])
            run.rows += len(rows)
        run.requests = client.request_count
        return run.rows
