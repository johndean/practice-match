#!/usr/bin/env python3
"""Operator entry points for the market-data layer. Runs inside the worker image
(`railway run --service worker -- python scripts/census_load.py …`) or locally against
docker-compose. Every subcommand is idempotent.

`tiger` (Task A4) is the first subcommand: it loads TIGER cartographic boundary files
(`app/census/tiger.py`) for every state `market_state` names, into `geo_area`. `acs` (Task A5)
loads ACS detailed/subject/prior-vintage tables (`app/census/acs.py`) into `acs_measure` through
`CensusClient`, one `ingest_run` row per dataset. Task A6 adds the industry loads: `cbp`
(`app/census/cbp.py`, county-level competition benchmark, NAICS 541940/812910/459910 with the
NAICS-2017 alias for 459910), `zbp` (`app/census/zbp.py`, ZIP-level competition, plan D11), `qwi`
(`app/census/qwi.py`, resolving the latest published quarter via `qwi.latest_available` when
`--year`/`--quarter` are omitted, then trimming to the newest 20 quarters), and `bds`
(`app/census/bds.py`, `--year` required -- BDS has no "latest" auto-resolution). Task A7 adds
`activate` (`app/census/vintage.py`): the only path that flips `active_vintage`, the table the API
reads -- never automatic, never run from a Celery task. It first runs a QA diff (`vintage.qa`)
against whatever vintage is currently active for that dataset and refuses (exit 5) unless the
candidate vintage's latest `ingest_run` succeeded and, when a prior vintage exists, the row-count
ratio falls inside `[0.8, 1.25]`; `--force` overrides the ratio check only. `--note` (A-C7 concern
1) is persisted in `active_vintage.note`, REQUIRED with `--force` (argparse refuses its absence,
exit 2) and optional otherwise; the printed `Report` carries it back too, so a forced override's
"why" lives in the database, not only in a CLI's stdout at the moment it ran. Later tasks (A8-A9)
add more subcommands to the same tree.

Exit codes follow the shared scheme every `census_load.py` subcommand uses (A-C4 ¶2, aligned
with `scripts/seed_listings.py`): 0 done; 2 refused before anything is opened (no subcommand --
argparse's own exit -- `DATABASE_URL` unset, a required Census setting missing --
`require_key`/`require_contact` in `app/census/client.py` now raise `SystemExit(2)`, superseding
A-C3 ¶2's `SystemExit(3)` -- or a dataset that is licence-gated: every loader's `PermissionError`
for an `unresolved`/`blocked` `dataset_registry` row, spec §1, is a refusal too -- `qwi` checks
this itself, before `latest_available`'s probe, rather than through `qwi.load`'s own identical
check, so a blocked QWI dataset is never even queried -- or `zbp`'s `geo_area` holding no ZCTA
(`860`) rows yet (`zbp.MissingBoundaries`, controller amendment A-C6): naming the prerequisite
(`census_load.py tiger` first) is a refusal of the same kind); 3 the database
is unreachable (retryable) OR a `psycopg2.Error` raised after connect, e.g. `UndefinedTable` on an
unmigrated database (A-C7 (7) / I12: every `cmd_*` closes its connection in `try`/`finally` and
prints only the exception's type name here, never its text, which can carry the statement or the
DSN); 4 a download or API fetch
failed (`CensusHTTPError`, its message already redacted -- A-C3 (3)); 5 validation failed -- every
loader raises this when a response is missing an expected variable (`VariableMissing`; spec
§4/¶12, a partial vintage that must never go active) -- reserved more broadly for malformed
bodies or bounds, and is what `activate` returns for a QA diff or ingest-run status `vintage.qa`
refuses on (`ActivationRefused`).

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
    try:
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
    except psycopg2.Error as exc:
        # A-C7 (7) / I12: a database error raised AFTER connect (e.g. UndefinedTable on an
        # unmigrated database) used to escape as a bare traceback (exit 1) -- only the
        # exception's TYPE is printed, never its text, which can carry the statement or DSN.
        print(f"[census_load] database error: {type(exc).__name__}", file=sys.stderr)
        return 3
    finally:
        conn.close()


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
    try:
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
            except PermissionError as exc:
                # A licence-gated dataset (spec §1: `unresolved`/`blocked` never ingested) is a
                # refusal, not a download failure -- exit 2, "refused before anything is opened"
                # (A-C4 ¶2), never an uncaught exception out of `main()` (A5's review of itself).
                print(f"[census_load] {ds_key} refused: {exc}", file=sys.stderr)
                return 2
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
    except psycopg2.Error as exc:
        print(f"[census_load] database error: {type(exc).__name__}", file=sys.stderr)
        return 3
    finally:
        conn.close()


def cmd_cbp(args: argparse.Namespace) -> int:
    from app.census import cbp
    from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_contact, require_key
    from app.census.registry import Dataset
    from app.config import settings
    from app.storage import ObjectStore
    from app.version import VERSION

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
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
            states = [r[0] for r in cur.fetchall()]
        archive = ObjectStore.from_settings(settings)

        def factory(ds: Dataset) -> CensusClient:
            return CensusClient(key, ds, archive, version=VERSION, contact=contact)

        try:
            n = cbp.load(conn, factory, states)
        except PermissionError as exc:
            print(f"[census_load] cbp refused: {exc}", file=sys.stderr)
            return 2
        except CensusHTTPError as exc:
            print(f"[census_load] cbp download failed: {exc}", file=sys.stderr)
            return 4
        except VariableMissing as exc:
            print(f"[census_load] cbp failed validation: {exc}", file=sys.stderr)
            return 5
        print(f"  cbp: {n} rows")
        return 0
    except psycopg2.Error as exc:
        print(f"[census_load] database error: {type(exc).__name__}", file=sys.stderr)
        return 3
    finally:
        conn.close()


def cmd_zbp(args: argparse.Namespace) -> int:
    from app.census import zbp
    from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_contact, require_key
    from app.census.registry import Dataset
    from app.config import settings
    from app.storage import ObjectStore
    from app.version import VERSION

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
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
            states = [r[0] for r in cur.fetchall()]
        archive = ObjectStore.from_settings(settings)

        def factory(ds: Dataset) -> CensusClient:
            return CensusClient(key, ds, archive, version=VERSION, contact=contact)

        try:
            n = zbp.load(conn, factory, states)
        except PermissionError as exc:
            print(f"[census_load] zbp refused: {exc}", file=sys.stderr)
            return 2
        except zbp.MissingBoundaries as exc:
            # A-C6: `geo_area` holds no ZCTA (`860`) rows yet -- naming the prerequisite is a
            # refusal, exit 2, the same as a licence gate (A-C4 ¶2's "refused before anything is
            # opened").
            print(f"[census_load] zbp refused: {exc}", file=sys.stderr)
            return 2
        except CensusHTTPError as exc:
            print(f"[census_load] zbp download failed: {exc}", file=sys.stderr)
            return 4
        except VariableMissing as exc:
            print(f"[census_load] zbp failed validation: {exc}", file=sys.stderr)
            return 5
        print(f"  zbp: {n} rows")
        return 0
    except psycopg2.Error as exc:
        print(f"[census_load] database error: {type(exc).__name__}", file=sys.stderr)
        return 3
    finally:
        conn.close()


def cmd_bds(args: argparse.Namespace) -> int:
    from app.census import bds
    from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_contact, require_key
    from app.census.registry import Dataset
    from app.config import settings
    from app.storage import ObjectStore
    from app.version import VERSION

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
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
            states = [r[0] for r in cur.fetchall()]
        archive = ObjectStore.from_settings(settings)

        def factory(ds: Dataset) -> CensusClient:
            return CensusClient(key, ds, archive, version=VERSION, contact=contact)

        try:
            n = bds.load(conn, factory, states, year=args.year)
        except PermissionError as exc:
            print(f"[census_load] bds refused: {exc}", file=sys.stderr)
            return 2
        except CensusHTTPError as exc:
            print(f"[census_load] bds download failed: {exc}", file=sys.stderr)
            return 4
        except VariableMissing as exc:
            print(f"[census_load] bds failed validation: {exc}", file=sys.stderr)
            return 5
        print(f"  bds {args.year}: {n} rows")
        return 0
    except psycopg2.Error as exc:
        print(f"[census_load] database error: {type(exc).__name__}", file=sys.stderr)
        return 3
    finally:
        conn.close()


def cmd_qwi(args: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from app.census import qwi
    from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_contact, require_key
    from app.census.registry import Dataset
    from app.census.registry import load as load_registry
    from app.config import settings
    from app.storage import ObjectStore
    from app.version import VERSION

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
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
            states = [r[0] for r in cur.fetchall()]
        archive = ObjectStore.from_settings(settings)

        def factory(ds: Dataset) -> CensusClient:
            return CensusClient(key, ds, archive, version=VERSION, contact=contact)

        # The licence gate is checked here, before any network call -- `qwi.load`'s own
        # `ds.cleared` check (identical to every other loader's) would otherwise run only AFTER
        # `latest_available`'s probe already reached a blocked dataset's endpoint below.
        ds = load_registry(conn)["qwi"]
        if not ds.cleared:
            print(f"[census_load] qwi refused: qwi is {ds.license_status}; loads are refused (spec §1 licensing gate)", file=sys.stderr)
            return 2

        year, quarter = args.year, args.quarter
        if year is None or quarter is None:
            now = datetime.now(UTC)
            with factory(ds) as client:
                try:
                    year, quarter = qwi.latest_available(client, states[0], today=(now.year, (now.month - 1) // 3 + 1))
                except CensusHTTPError as exc:
                    print(f"[census_load] qwi download failed: {exc}", file=sys.stderr)
                    return 4
                except VariableMissing as exc:
                    # Mi1 (A6 review): a 200 response missing the `Emp` column (a schema drift, a
                    # malformed 200) is "validation failed", not an uncaught exception -- every
                    # other exception arm in this file already maps `VariableMissing` to exit 5.
                    print(f"[census_load] qwi validation failed: {exc}", file=sys.stderr)
                    return 5

        try:
            n = qwi.load(conn, factory, states, year=year, quarter=quarter)
        except PermissionError as exc:
            # I1 (A6 review): defense-in-depth for a live TOCTOU window -- the upfront registry
            # check above uses the same connection with no intervening commit, so this arm is
            # unreachable in practice today, but keeps `cmd_qwi`'s shape visually identical to
            # the other three subcommands', all of which catch `qwi.load`'s own licence gate.
            print(f"[census_load] qwi refused: {exc}", file=sys.stderr)
            return 2
        except CensusHTTPError as exc:
            print(f"[census_load] qwi download failed: {exc}", file=sys.stderr)
            return 4
        except VariableMissing as exc:
            print(f"[census_load] qwi failed validation: {exc}", file=sys.stderr)
            return 5
        trimmed = qwi.trim(conn)
        print(f"  qwi {year}Q{quarter}: {n} rows ({trimmed} trimmed)")
        return 0
    except psycopg2.Error as exc:
        print(f"[census_load] database error: {type(exc).__name__}", file=sys.stderr)
        return 3
    finally:
        conn.close()


def cmd_activate(args: argparse.Namespace) -> int:
    from app.census import vintage

    # Unlike every load subcommand above, `activate` never touches the Census API: no key, no
    # contact, no `market_state` query, no HTTP client -- it only reads/writes the database, so
    # it shares just the DATABASE_URL/unreachable/post-connect-database-error arms with them
    # (A-C7 (7)).
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[census_load] DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        conn = _conn(dsn)
    except psycopg2.OperationalError as exc:
        print(f"[census_load] database unreachable: {type(exc).__name__}", file=sys.stderr)
        return 3
    try:
        try:
            rep = vintage.activate(conn, args.dataset_key, args.vintage, args.by, force=args.force, note=args.note)
        except vintage.ActivationRefused as exc:
            # A refused diff or a non-succeeded ingest_run is "validation failed" (A-C4 ¶2's exit
            # 5) -- `active_vintage` is untouched, exactly as a bad ratio without `--force` leaves
            # it.
            print(f"[census_load] activation refused: {exc}", file=sys.stderr)
            return 5
        print(rep)
        # m2 (A7 review Minor 2): a forced activation says so on the confirmation line itself,
        # not only inside the `Report` repr printed above it.
        forced = " (forced)" if args.force else ""
        print(f"[census_load] {rep.dataset_key} is now active at vintage {rep.vintage!r} (by {args.by}){forced}")
        return 0
    except psycopg2.Error as exc:
        print(f"[census_load] database error: {type(exc).__name__}", file=sys.stderr)
        return 3
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    # Imported here, not inside `cmd_acs` alone (A5's review of itself): `--dataset`'s `choices`
    # must be built while the parser itself is under construction, before `parse_args` runs --
    # this is still "inside a function", never at module scope, so the sys.path reason `cmd_*`'s
    # own imports are deferred for (see the module docstring) does not apply here either. `activate`
    # (Task A7) needs `vintage.TABLE_FOR` the same way, for `dataset_key`'s `choices`.
    from app.census import acs, vintage

    p = argparse.ArgumentParser(prog="census_load", description="Operator entry points for the market-data layer.")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tiger", help="load TIGER boundary files for every market_state state")
    t.add_argument("--vintage", default="2023", help="TIGER cartographic boundary vintage year (default: 2023)")
    t.set_defaults(fn=cmd_tiger)
    a = sub.add_parser("acs", help="load ACS detailed/subject/prior tables for every market_state state")
    a.add_argument("--dataset", nargs="+", default=["acs5", "acs5_subject", "acs5_prior"], choices=sorted(acs.VARIABLES),
                    help="dataset_registry keys to load (default: all three ACS datasets)")
    a.set_defaults(fn=cmd_acs)
    c = sub.add_parser("cbp", help="load County Business Patterns (county-level competition benchmark) for every market_state state")
    c.set_defaults(fn=cmd_cbp)
    z = sub.add_parser("zbp", help="load ZIP Code Business Patterns (community-level competition, plan D11) for every market_state state")
    z.set_defaults(fn=cmd_zbp)
    q = sub.add_parser("qwi", help="load Quarterly Workforce Indicators for every market_state state, then trim to the newest 20 quarters")
    q.add_argument("--year", type=int, default=None, help="QWI year (default: resolved via the latest published quarter)")
    q.add_argument("--quarter", type=int, default=None, help="QWI quarter, 1-4 (default: resolved via the latest published quarter)")
    q.set_defaults(fn=cmd_qwi)
    b = sub.add_parser("bds", help="load Business Dynamics Statistics for every market_state state")
    b.add_argument("--year", type=int, required=True, help="BDS data year, e.g. 2022")
    b.set_defaults(fn=cmd_bds)
    v = sub.add_parser("activate", help="flip active_vintage for a dataset after a QA diff -- the only path that makes a loaded vintage the one the API reads")
    v.add_argument("dataset_key", choices=sorted(vintage.TABLE_FOR), help="dataset_registry key to activate (e.g. acs5)")
    v.add_argument("vintage", help="vintage string to activate, exactly as ingested (e.g. '2019\u20132023')")
    v.add_argument("--by", required=True, help="operator name recorded in active_vintage.activated_by")
    v.add_argument("--force", action="store_true", help="activate despite a row-count ratio outside [0.8, 1.25] (reviewed override)")
    v.add_argument("--note", default=None, help="reason for this activation, persisted in active_vintage.note; REQUIRED with --force, optional otherwise")
    v.set_defaults(fn=cmd_activate)
    args = p.parse_args(argv)
    if args.cmd == "activate" and args.force and not args.note:
        # A-C7 concern 1: a forced override -- the one case this ledger most needs a persisted
        # reason for -- must not go through without one. Checked here, not inside `cmd_activate`,
        # so it is argparse's own refusal (exit 2, "refused before anything is opened") like
        # every other bad-arguments case in this file.
        v.error("--note is required when --force is given")
    result: int = args.fn(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
