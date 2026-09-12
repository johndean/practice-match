"""ZIP Code Business Patterns (plan D11) -- the community-level competition source (spec §2 zbp).
Establishment counts per ZIP for the spec's NAICS codes, using the same NAICS-2017 alias as CBP
(`app.census.cbp.NAICS_ALIASES`); employment/payroll are mostly suppressed at ZIP level and are
not requested here -- `ESTAB` is what the competition layer needs.

The all-industry total (`TOTAL_NAICS`) is fetched in the same pass and stored under its own NAICS
key; it is the ZIP-coverage universe the competition layer reads to tell a withheld count from an
uncovered ZIP (review round 1, Important 3).

Controller amendment A-C6 (2026-09-09): the standalone `zbp` dataset ends at vintage 2018 --
`2022/zbp` is a 404. From 2019 the ZIP-level Business Patterns are served by the CBP endpoint's
OWN `zip code` geography (Census's own summary level `861` for this request -- distinct from the
`860` (ZCTA) `summary_level` this application stores every ZIP-level row under, D11's
ZIP≈ZCTA approximation; variable `ZIPCODE`, no `in=` clause), so `dataset_registry`'s `zbp` row's
`api_dataset_id` is `2022/cbp` and this loader makes ONE request per NAICS code (three total),
never one per state. ZBP publishes no establishment-count
suppression flag -- the brief's illustrative `ESTAB_F` was never a real Census variable, so
`zbp_industry` carries no `flag` column. A response's `ZIPCODE`s are kept only when already
present in `geo_area` as summary level `860` -- the market states' ZCTAs A4's TIGER load already
bounds (D11's ZIP≈ZCTA approximation) -- and the load refuses outright, naming the prerequisite,
when that set is empty. Adapted to the committed `CensusClient` interface exactly as `cbp.py` is
(controller amendment A-C5)."""
from __future__ import annotations

from collections.abc import Callable

import psycopg2.extensions

from app.census import ingest
from app.census.cbp import NAICS, NAICS_ALIASES
from app.census.client import CensusClient
from app.census.registry import Dataset
from app.census.registry import load as load_registry

VARS = ["ZIPCODE", "ESTAB"]

#: The ALL-INDUSTRY total, requested in the same pass as the three industry codes and stored
#: under its own key (review round 1, Important 3, 2026-09-12).
#:
#: The Census publishes ZIP-level INDUSTRY detail only where a category has three or more
#: establishments -- "if a given NAICS category has less than three business establishments, the
#: number of establishments won't be reported for that category, but they will be included in the
#: sum total". Measured on QA before this was written: `zbp_industry` held a minimum of 3 and not
#: one row below it, nationally. Without the total there is no way to tell a ZIP area with one or
#: two veterinary practices -- a real, withheld figure -- from a ZIP area ZIP Code Business
#: Patterns does not cover at all, and `geo_metric` served both as `value: null, suppressed:
#: false`: 393 of Dallas's 535 ZCTAs claiming "no data" over cells the Census had withheld, which
#: is the mirror image of the CBP over-suppression this same branch fixed.
#:
#: `00` is the Census's own code for the total across all industries on this endpoint, and it
#: needs no alias in any NAICS vintage.
TOTAL_NAICS = "00"

UPSERT = """
INSERT INTO zbp_industry (geo_id, summary_level, vintage, naics_code, establishments, ingest_run_id)
VALUES (%s, '860', %s, %s, %s, %s)
ON CONFLICT (geo_id, summary_level, vintage, naics_code) DO UPDATE SET establishments = EXCLUDED.establishments, ingest_run_id = EXCLUDED.ingest_run_id
"""


class MissingBoundaries(RuntimeError):
    """`geo_area` holds no ZCTA (`860`) rows yet -- `zbp` has nothing to bound its ZIPs to
    (A-C6): run `census_load.py tiger` first."""


def _int(v: str | None) -> int | None:
    return int(v) if v not in (None, "") else None


def load(conn: psycopg2.extensions.connection, client_factory: Callable[[Dataset], CensusClient], states: list[str]) -> int:
    """`states` is accepted (unused) only so this loader's call shape matches `cbp.load`'s and
    `bds.load`'s in `scripts/census_load.py` (A-C6): the CBP `zip code` geography accepts no
    `in=` clause, so there is no per-state request to make."""
    ds = load_registry(conn)["zbp"]
    if not ds.cleared:
        raise PermissionError(f"zbp is {ds.license_status}; loads are refused (spec §1 licensing gate)")
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id FROM geo_area WHERE summary_level = '860'")
        zctas = {r[0] for r in cur.fetchall()}
    if not zctas:
        raise MissingBoundaries("zbp needs the market states' ZCTAs in geo_area — run 'census_load.py tiger' first")
    param = ds.naics_param or "NAICS2017"
    with ingest.run(conn, "zbp", ds.vintage) as run, client_factory(ds) as client:
        for code in (*NAICS, TOTAL_NAICS):
            requested = NAICS_ALIASES.get((param, code), code)
            rows = client.fetch_table(VARS, "zip code:*", VARS, None, {param: requested})
            payload = [(r["ZIPCODE"], ds.vintage, code, _int(r.get("ESTAB")), run.id) for r in rows if r["ZIPCODE"] in zctas]
            with conn.cursor() as cur:
                cur.executemany(UPSERT, payload)
            run.rows += len(payload)
        run.requests = client.request_count
        return run.rows
