#!/usr/bin/env python3
"""Operator entry points for the market-data layer. Runs inside the worker image, reached with
`railway ssh --service worker --environment QA` then `python scripts/census_load.py …` (never
`railway run`, which executes on the OPERATOR'S machine with the worker's variables injected —
controller amendment A-C11 (1), 2026-09-09, superseding this docstring's own former `railway run`
form; see DEPLOY.md's "Census Phase A exit (QA)"), or locally against docker-compose. Every
subcommand is idempotent.

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
(`census_load.py tiger` first) is a refusal of the same kind -- or an empty `market_state` (A-C11
(6)): resolving `qwi`'s latest published quarter needs at least one state -- or `require_archive`
(`app/census/client.py`, A-C11 (10)) finding a `CENSUS_API_KEY` set but the raw archive still
unconfigured, naming the missing `S3_*` settings); 3 the database
is unreachable (retryable) OR a `psycopg2.Error` raised after connect, e.g. `UndefinedTable` on an
unmigrated database (A-C7 (7) / I12: every `cmd_*` closes its connection in `try`/`finally` and
prints only the exception's type name here, never its text, which can carry the statement or the
DSN); 4 a download or API fetch
failed (`CensusHTTPError`, its message already redacted -- A-C3 (3)); 5 validation failed -- every
loader raises this when a response is missing an expected variable (`VariableMissing`; spec
§4/¶12, a partial vintage that must never go active) -- reserved more broadly for malformed
bodies or bounds (`tiger`'s own arm, A-C11 (3): a truncated or corrupt boundary zip --
`zipfile.BadZipFile`/`shapefile.ShapefileException` -- maps here too), and is what `activate`
returns for a QA diff or ingest-run status `vintage.qa` refuses on (`ActivationRefused`).

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
    import zipfile

    import shapefile  # type: ignore[import-untyped]  # pyshp ships no py.typed marker / stubs (A-C0 ¶7)

    from app.census.client import CensusHTTPError, redact, require_archive, require_contact
    from app.census.registry import load as load_registry
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
        # m1 (controller amendment A-C11 (2)): unlike every other loader's own `load()`,
        # `tiger.load_boundaries` has no internal `cleared` check at all -- the Celery task
        # already gates this (A-C8 (9)/i2); the CLI did not.
        ds = load_registry(conn)["tiger_cb"]
        if not ds.cleared:
            print(f"[census_load] tiger refused: tiger_cb is {ds.license_status}; loads are refused (spec §1 licensing gate)", file=sys.stderr)
            return 2
        with conn.cursor() as cur:
            cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
            states = [r[0] for r in cur.fetchall()]
        # `None` when the bucket is not configured (A-C2 P2) -- the boundary load still runs,
        # simply without archiving the raw zips, UNLESS a live load is possible at all (A-C1 ¶7 /
        # A-C11 (10)), in which case `require_archive` refuses instead of silently disabling it.
        archive = ObjectStore.from_settings(settings)
        require_archive(archive, settings)
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
            except (zipfile.BadZipFile, shapefile.ShapefileException) as exc:
                # m2 (controller amendment A-C11 (3)): a truncated or corrupt download -- neither
                # exception carries a URL, but every raised/logged message in this programme is
                # redacted on principle (A-C3 (3)'s habit, uniform even when nothing to strip).
                print(f"[census_load] boundary file corrupt or unreadable: {redact(str(exc))}", file=sys.stderr)
                return 5
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
    from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_archive, require_contact, require_key
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
        require_archive(archive, settings)

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
    from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_archive, require_contact, require_key
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
        require_archive(archive, settings)

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
    from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_archive, require_contact, require_key
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
        require_archive(archive, settings)

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
    from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_archive, require_contact, require_key
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
        require_archive(archive, settings)

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
    from app.census.client import CensusClient, CensusHTTPError, VariableMissing, require_archive, require_contact, require_key
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
        require_archive(archive, settings)

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
            if not states:
                # m5 (controller amendment A-C11 (6)): resolving the latest published quarter
                # indexes `states[0]` -- an empty `market_state` gave a bare `IndexError` (exit 1)
                # instead of a named refusal. Unreachable today (017_census_registry.sql seeds six
                # rows and nothing deletes them), but the CLI must not depend on that forever.
                print("[census_load] qwi refused: market_state has no rows yet; qwi's latest-quarter resolution needs at least one state", file=sys.stderr)
                return 2
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


def cmd_materialize(args: argparse.Namespace) -> int:
    """Task B4b: rebuilds `market_metric` rows -- one listing, given `--listing`, or every
    geocoded listing otherwise -- from whatever vintages are currently active. Never touches the
    Census API (no key/contact gate, like `activate`), so it shares only the
    DATABASE_URL/unreachable/post-connect-database-error arms with the keyed loaders above; unlike
    `activate`, it DOES need Redis, for the listing cache-version bump `materialize_listing` sets
    on every call."""
    from app.cache import sync_redis
    from app.census import materialize

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
        redis = sync_redis()
        try:
            if args.listing:
                n = materialize.materialize_listing(conn, redis, args.listing)
                print(f"  {args.listing}: {n} rows")
            else:
                counts = materialize.materialize_all(conn, redis)
                for lid, n in counts.items():
                    print(f"  {lid}: {n} rows")
                print(f"  {len(counts)} listing(s) materialised")
        except RuntimeError as exc:
            # `app.census.materialize._Ctx`'s own refusal: no active acs5/tiger_cb vintage yet --
            # an operator hasn't run `tiger`/`acs` then `activate` -- "refused before anything
            # useful happened" in spirit, so it maps to the same exit 2 every other
            # licence-gate/missing-prerequisite refusal in this file uses.
            print(f"[census_load] materialize refused: {exc}", file=sys.stderr)
            return 2
        return 0
    except psycopg2.Error as exc:
        print(f"[census_load] database error: {type(exc).__name__}", file=sys.stderr)
        return 3
    finally:
        conn.close()


def cmd_geocode(args: argparse.Namespace) -> int:
    """Task B9: resolves every listing without a `practice_location` row, or one with `--listing`,
    or with `--force` re-resolves one that already has a row. Calls the same `app.census.geocode`
    code the Celery task calls, synchronously: geocode, then `catchment.build`, then
    `materialize.materialize_listing`, so one command takes a listing from an address to its
    figures. Never touches the Census API (no key/contact gate, like `activate` and `materialize`),
    so it shares only the DATABASE_URL/unreachable/post-connect-database-error arms; it DOES need
    Redis, like `materialize`."""
    from app.cache import sync_redis
    from app.census import catchment, geocode, materialize

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
        redis = sync_redis()
        # Fetch the listings to geocode
        with conn.cursor() as cur:
            if args.listing:
                cur.execute("SELECT id FROM listing WHERE id = %s", (args.listing,))
            else:
                # Listings without a practice_location row, or --force re-geocodes existing ones
                if args.force:
                    cur.execute("SELECT id FROM listing ORDER BY id")
                else:
                    cur.execute(
                        "SELECT l.id FROM listing l LEFT JOIN practice_location p ON l.id = p.listing_id "
                        "WHERE p.listing_id IS NULL ORDER BY l.id"
                    )
            rows = cur.fetchall()

        if args.listing and not rows:
            print(f"[census_load] geocode refused: no such listing {args.listing}", file=sys.stderr)
            return 2

        # If there's nothing to geocode and we're not looking for a specific listing,
        # we're done — no need to check vintage. This makes the command safely re-runnable
        # during a live load (run repeatedly, skip completed listings, succeed when all done).
        if not rows:
            geocoded_count = 0
        else:
            # Fail fast when no boundary vintage is active: the resolver and the catchment build
            # both need it, and refusing here names what to run instead of dying deeper in.
            # A database error on this SELECT falls to the function's own `except psycopg2.Error`
            # below, which returns 3 — a second handler here would be the same code twice, and
            # the parameterised guard test already proves 3 for a post-connect error (round 5).
            with conn.cursor() as cur:
                cur.execute("SELECT vintage FROM active_vintage WHERE dataset_key = 'tiger_cb'")
                row = cur.fetchone()
            if row is None:
                print("[census_load] geocode refused: no active tiger_cb vintage — run census_load.py tiger and activate it", file=sys.stderr)
                return 2

            # Geocode each listing
            geocoded_count = 0
            import httpx
            ua = f"PracticeMatch/{__import__('app.version', fromlist=['VERSION']).VERSION} (census-operator)"
            with httpx.Client(headers={"User-Agent": ua}) as http:
                gc = geocode.Geocoder(http, "https://geocoding.geo.census.gov/geocoder", ua)
                for (listing_id,) in rows:
                    try:
                        loc = geocode.resolve(conn, gc, listing_id)
                        # Determine rung
                        # The ladder's rung IS the precision the resolver recorded; an if/elif
                        # chain that re-states each name would be an identity function with five
                        # branches nothing can distinguish (controller, B9 round 5).
                        rung = loc.geo_precision
                        # Check if geocode_review was written (below rooftop)
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1 FROM geocode_review WHERE listing_id = %s", (listing_id,))
                            has_review = cur.fetchone() is not None
                        review_str = "review row written" if has_review else "no review needed"
                        print(f"  {listing_id}: {rung} ({review_str})")
                        geocoded_count += 1
                        # Build catchment and materialize
                        geo_vintage = materialize.active_geo_vintage(conn)
                        catchment.build(conn, listing_id, geo_vintage)
                        materialize.materialize_listing(conn, redis, listing_id)
                    except geocode.GeocodeFailed as exc:
                        print(f"  {listing_id}: geocoding failed: {exc}", file=sys.stderr)
                        return 5

        print(f"[census_load] {geocoded_count} listing(s) geocoded")
        return 0
    except RuntimeError as exc:
        # No active vintage
        print(f"[census_load] geocode refused: {exc}", file=sys.stderr)
        return 2
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
    g = sub.add_parser("geocode", help="geocode listings -- every one without a practice_location row, or one given --listing, or all with --force")
    g.add_argument("--listing", default=None, help="listing id to geocode (default: every listing without a geocoded location)")
    g.add_argument("--force", action="store_true", help="re-geocode listings that already have a practice_location row")
    g.set_defaults(fn=cmd_geocode)
    m = sub.add_parser("materialize", help="rebuild market_metric rows for one listing (--listing) or every geocoded listing, from the active vintages")
    m.add_argument("--listing", default=None, help="listing id to materialise (default: every listing with a geocoded location)")
    m.set_defaults(fn=cmd_materialize)
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
