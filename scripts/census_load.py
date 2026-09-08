#!/usr/bin/env python3
"""Operator entry points for the market-data layer. Runs inside the worker image
(`railway run --service worker -- python scripts/census_load.py …`) or locally against
docker-compose. Every subcommand is idempotent.

`tiger` (Task A4) is the first subcommand: it loads TIGER cartographic boundary files
(`app/census/tiger.py`) for every state `market_state` names, into `geo_area`. `acs` (Task A5)
loads ACS detailed/subject/prior-vintage tables (`app/census/acs.py`) into `acs_measure` through
`CensusClient`, one `ingest_run` row per dataset. Later tasks (A6-A9) add `cbp`, `qwi`,
`activate`, … to the same subparser tree.

Exit codes follow the shared scheme every `census_load.py` subcommand uses (A-C4 ¶2, aligned
with `scripts/seed_listings.py`): 0 done; 2 refused before anything is opened (no subcommand --
argparse's own exit -- `DATABASE_URL` unset, or a required Census setting missing --
`require_key`/`require_contact` in `app/census/client.py` now raise `SystemExit(2)`, superseding
A-C3 ¶2's `SystemExit(3)`); 3 the database is unreachable (retryable); 4 a download or API fetch
failed (`CensusHTTPError`, its message already redacted -- A-C3 (3)); 5 validation failed -- `acs`
raises this when a response is missing an expected variable (`VariableMissing`; spec §4/¶12, a
partial vintage that must never go active) -- reserved more broadly for malformed bodies or
bounds once a subcommand that can hit those lands.

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
        return 3
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
            return 4
    for k, n in counts.items():
        print(f"  {k}: {n} rows")
    return 0


def cmd_acs(args: argparse.Namespace) -> int:
    from app.census import acs
    from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_contact, require_key
    from app.census.registry import Dataset
    from app.config import settings
    from app.storage import ObjectStore
    from app.version import VERSION

    # Fails closed before anything is opened (A-C4 ¶2): a Census API key and the VIN
    # Foundation's designated technical contact are both required before this touches the
    # network or the database. `CensusClient`'s own constructor refuses a missing contact
    # (controller amendment A-C3b M3) -- the client is built from `require_contact()`'s return
    # value here, never from `settings.census_contact_email` directly, so a missing contact is
    # this script's own exit-2 gate rather than a bare `ValueError` surfacing from inside
    # `acs.load` (the coordinator's binding correction to the task brief's draft CLI snippet).
    key = require_key()
    contact = require_contact()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[census_load] DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        conn = _conn(dsn)
    except psycopg2.OperationalError as exc:
        print(f"[census_load] database unreachable: {type(exc).__name__}", file=sys.stderr)
        return 3
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
        states = [r[0] for r in cur.fetchall()]
    # `None` when the bucket is not configured (A-C2 P2) -- the load still runs, simply
    # without archiving the raw responses.
    archive = ObjectStore.from_settings(settings)

    def factory(ds: Dataset) -> CensusClient:
        return CensusClient(key, ds, archive, version=VERSION, contact=contact)

    for ds_key in args.dataset:
        try:
            n = acs.load(conn, factory, ds_key, states)
        except CensusHTTPError as exc:
            # CensusHTTPError's own message is already redacted (A-C3 (3)).
            print(f"[census_load] {ds_key} download failed: {exc}", file=sys.stderr)
            return 4
        except VariableMissing as exc:
            # A partial load never activates a vintage (global constraint ¶12) -- `acs.load`'s
            # `ingest.run()` has already rolled back and recorded the run as 'aborted'.
            print(f"[census_load] {ds_key} failed validation: {exc}", file=sys.stderr)
            return 5
        print(f"  {ds_key}: {n} measures")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="census_load", description="Operator entry points for the market-data layer.")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tiger", help="load TIGER boundary files for every market_state state")
    t.add_argument("--vintage", default="2023", help="TIGER cartographic boundary vintage year (default: 2023)")
    t.set_defaults(fn=cmd_tiger)
    a = sub.add_parser("acs", help="load ACS detailed/subject/prior tables for every market_state state")
    a.add_argument("--dataset", nargs="+", default=["acs5", "acs5_subject", "acs5_prior"],
                    help="dataset_registry keys to load (default: all three ACS datasets)")
    a.set_defaults(fn=cmd_acs)
    args = p.parse_args(argv)
    result: int = args.fn(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
