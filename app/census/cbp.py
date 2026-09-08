"""County Business Patterns (spec §2 cbp, §5 NAICS). County granularity only.

The NAICS parameter name comes from the registry (`ds.naics_param`); the 2022 CBP release still
publishes under NAICS2017, so the spec's 2022-vintage code 459910 (Pet & Pet Supplies Retailers)
needs the alias 453910 -- requested under the alias, stored under the spec's own code (`NAICS`,
never `NAICS_ALIASES`'s key). Adapted from the task brief's illustrative draft to the client
interface A3's review round actually committed (controller amendment A-C5, exactly as `acs.py`
already is): `fetch_table` takes the raw `(get, for_, expected, in_, extra)` parameters and
validates + archives internally -- there is no public `build_url`/`validate_variables` pair for
a caller to chain -- and the client is used as a context manager rather than closed by hand."""
from __future__ import annotations

from collections.abc import Callable

import psycopg2.extensions

from app.census import ingest
from app.census.client import CensusClient
from app.census.registry import Dataset
from app.census.registry import load as load_registry

NAICS = ["541940", "812910", "459910"]
NAICS_ALIASES = {("NAICS2017", "459910"): "453910"}
# A-C6: `2022/cbp` has no `EMP_F`/`PAYANN_F` -- CBP's disclosure-avoidance is noise infusion, not
# withheld cells, and its noise-range variables are `EMP_N`/`PAYANN_N` ("Noise range for ...").
VARS = ["ESTAB", "EMP", "PAYANN", "EMP_N", "PAYANN_N"]
EXPECTED = ["ESTAB", "EMP", "PAYANN"]

UPSERT = """
INSERT INTO cbp_industry (geo_id, summary_level, vintage, naics_code, establishments, employment, annual_payroll_k, flag, ingest_run_id)
VALUES (%s, '050', %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (geo_id, summary_level, vintage, naics_code) DO UPDATE SET establishments = EXCLUDED.establishments,
  employment = EXCLUDED.employment, annual_payroll_k = EXCLUDED.annual_payroll_k, flag = EXCLUDED.flag, ingest_run_id = EXCLUDED.ingest_run_id
"""


def _int(v: str | None) -> int | None:
    return int(v) if v not in (None, "") else None


def _flags(row: dict[str, str | None]) -> str | None:
    parts = [f"{k}={row[k]}" for k in ("EMP_N", "PAYANN_N") if row.get(k)]
    return ";".join(parts) or None


def _county_geo_id(row: dict[str, str | None]) -> str:
    state, county = row.get("state"), row.get("county")
    if state is None or county is None:
        raise ValueError("CBP row missing 'state'/'county'")
    return state + county


def load(conn: psycopg2.extensions.connection, client_factory: Callable[[Dataset], CensusClient], states: list[str]) -> int:
    ds = load_registry(conn)["cbp"]
    if not ds.cleared:
        raise PermissionError(f"cbp is {ds.license_status}; loads are refused (spec §1 licensing gate)")
    param = ds.naics_param or "NAICS2017"
    with ingest.run(conn, "cbp", ds.vintage) as run, client_factory(ds) as client:
        for code in NAICS:
            requested = NAICS_ALIASES.get((param, code), code)
            for st in states:
                rows = client.fetch_table(["NAME", *VARS], "county:*", EXPECTED, f"state:{st}", {param: requested})
                payload = []
                for r in rows:
                    flags = _flags(r)
                    # A-C6: no suppression flag to branch on -- an absent/sentinel cell is
                    # already None through normalise()/_int, never 0 (spec §14 kept); a present
                    # EMP_N/PAYANN_N noise-range value does not itself null anything.
                    emp = _int(r.get("EMP"))
                    pay = _int(r.get("PAYANN"))
                    payload.append((_county_geo_id(r), ds.vintage, code, _int(r.get("ESTAB")), emp, pay, flags, run.id))
                with conn.cursor() as cur:
                    cur.executemany(UPSERT, payload)
                run.rows += len(payload)
        run.requests = client.request_count
        return run.rows
