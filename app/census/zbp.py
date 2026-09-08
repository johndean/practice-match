"""ZIP Code Business Patterns (plan D11) -- the community-level competition source (spec §2 zbp).
Establishment counts per ZIP for the spec's NAICS codes, using the same NAICS-2017 alias as CBP
(`app.census.cbp.NAICS_ALIASES`); employment/payroll are mostly suppressed at ZIP level and are
not requested here -- `ESTAB` is what the competition layer needs. Adapted to the committed
`CensusClient` interface exactly as `cbp.py` is (controller amendment A-C5)."""
from __future__ import annotations

from collections.abc import Callable

import psycopg2.extensions

from app.census import ingest
from app.census.cbp import NAICS, NAICS_ALIASES
from app.census.client import CensusClient
from app.census.registry import Dataset
from app.census.registry import load as load_registry

VARS = ["ESTAB"]

UPSERT = """
INSERT INTO zbp_industry (geo_id, summary_level, vintage, naics_code, establishments, flag, ingest_run_id)
VALUES (%s, '860', %s, %s, %s, %s, %s)
ON CONFLICT (geo_id, summary_level, vintage, naics_code) DO UPDATE SET establishments = EXCLUDED.establishments, flag = EXCLUDED.flag, ingest_run_id = EXCLUDED.ingest_run_id
"""


def _int(v: str | None) -> int | None:
    return int(v) if v not in (None, "") else None


def load(conn: psycopg2.extensions.connection, client_factory: Callable[[Dataset], CensusClient], states: list[str]) -> int:
    ds = load_registry(conn)["zbp"]
    if not ds.cleared:
        raise PermissionError(f"zbp is {ds.license_status}; loads are refused (spec §1 licensing gate)")
    param = ds.naics_param or "NAICS2017"
    with ingest.run(conn, "zbp", ds.vintage) as run, client_factory(ds) as client:
        for code in NAICS:
            requested = NAICS_ALIASES.get((param, code), code)
            for st in states:
                # ZBP geography is zipcode; 'in=state' filters to a state's ZIPs.
                rows = client.fetch_table(VARS, "zipcode:*", VARS, f"state:{st}", {param: requested})
                with conn.cursor() as cur:
                    cur.executemany(UPSERT, [
                        (r["zipcode"], ds.vintage, code, _int(r.get("ESTAB")), r.get("ESTAB_F"), run.id)
                        for r in rows
                    ])
                run.rows += len(rows)
        run.requests = client.request_count
        return run.rows
