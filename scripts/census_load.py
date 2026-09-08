#!/usr/bin/env python3
"""Operator entry points for the market-data layer. Runs inside the worker image
(`railway run --service worker -- python scripts/census_load.py …`) or locally against
docker-compose. Every subcommand is idempotent.

`--tiger` (Task A4) is the first subcommand: it loads TIGER cartographic boundary files
(`app/census/tiger.py`) for every state `market_state` names, into `geo_area`. Later tasks
(A5-A9) add `--acs`, `--cbp`, `--qwi`, `--activate`, … to the same subparser tree.

Exit codes: 0 done; 2 refused before anything is opened (no subcommand -- argparse's own exit --
or `DATABASE_URL` unset); 3 a required Census setting is missing (`require_key`/`require_contact`
in `app/census/client.py`, A-C3: `SystemExit(3)`, naming the variable); 4 the database is
unreachable (retryable); 5 the boundary download itself failed (`CensusHTTPError`, its message
already redacted -- A-C3 (3)).

The `app.*` imports are inside each `cmd_*` function for the reason `scripts/bootstrap_admin.py`
and `scripts/reset_rate_limits.py` record: `python scripts/census_load.py` puts `scripts/` on
`sys.path`, not the repository root, so an unconditional `import app...` at module scope would
break the very entry point this script exists to be. It also means the tiger subcommand's own
`pyshp`/`shapely` import cost is paid only when `--tiger` (or a later heavy subcommand) actually
runs.
"""
from __future__ import annotations

import argparse
import os
import sys

import httpx
import psycopg2
import psycopg2.extensions


def normalize_dsn(dsn: str) -> str:
    """The same normalisation as `scripts/migrate.normalize_dsn` (duplicated rather than
    imported, for the sys.path reason above): psycopg2 wants `postgresql://`, the app may hold
    `postgresql+asyncpg://`, and Railway's PostGIS template also hands out the legacy
    `postgres://` scheme."""
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


def _conn(dsn: str) -> psycopg2.extensions.connection:
    c = psycopg2.connect(normalize_dsn(dsn))
    c.autocommit = True
    return c


def cmd_tiger(args: argparse.Namespace) -> int:
    from app.census.client import CensusHTTPError, require_contact
    from app.census.tiger import load_boundaries
    from app.config import settings
    from app.storage import ObjectStore
    from app.version import VERSION

    # Fails closed before anything is opened (A-C1 (4) / A-C3 (2)): the User-Agent this
    # ingestion sends is always the VIN Foundation's designated technical contact, never a
    # default address and never a developer's own.
    contact = require_contact()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[census_load] DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        conn = _conn(dsn)
    except psycopg2.OperationalError as exc:
        print(f"[census_load] database unreachable: {type(exc).__name__}", file=sys.stderr)
        return 4
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
        states = [r[0] for r in cur.fetchall()]
    # `None` when the bucket is not configured (A-C2 P2) -- the boundary load still runs,
    # simply without archiving the raw zips.
    archive = ObjectStore.from_settings(settings)
    ua = f"PracticeMatch/{VERSION} ({contact})"
    # `follow_redirects=False` (controller correction, 2026-09-09): a 3xx from
    # www2.census.gov must never be transparently followed into a body that gets parsed and
    # archived without this script ever seeing the redirect.
    with httpx.Client(headers={"User-Agent": ua}, follow_redirects=False) as http:
        try:
            counts = load_boundaries(conn, http, states, args.vintage, archive)
        except CensusHTTPError as exc:
            # CensusHTTPError's own message is already redacted (A-C3 (3)).
            print(f"[census_load] boundary download failed: {exc}", file=sys.stderr)
            return 5
    for k, n in counts.items():
        print(f"  {k}: {n} rows")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="census_load", description="Operator entry points for the market-data layer.")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tiger", help="load TIGER boundary files for every market_state state")
    t.add_argument("--vintage", default="2023", help="TIGER cartographic boundary vintage year (default: 2023)")
    t.set_defaults(fn=cmd_tiger)
    args = p.parse_args(argv)
    result: int = args.fn(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
