"""Celery entry points for the market-data layer (Task A8; `census.load_zbp` added in the A8 fix
round, A-C8 (8)/i1). Phase B adds `census.geocode_listing`, `census.materialize_metrics` and
`census.backfill_listing`.

Each task opens its own psycopg2 connection through `_conn()`, the same shape
`scripts/census_load.py`'s own `_conn(dsn)` uses (reading `settings.database_url`, via the
canonical `app.db.sync_dsn()` helper -- A-C8 (6)/m5 -- since a Celery task takes no CLI arguments)
-- Census loads are occasional and heavy (annual/quarterly), not the mail pipeline's per-minute
drain `app.db.sync_conn()`'s pool exists for, so a plain connection per invocation is the right
shape here too. Every task calls the SAME loader and activation functions the CLI calls
(`app.census.acs/cbp/bds/qwi/tiger/zbp`) -- never a second implementation -- and NOTHING here ever
calls `app.census.vintage.activate`: flipping `active_vintage` stays operator-initiated, through
`scripts/census_load.py activate`, never a scheduled task (A-C7 (8), enforced by an AST scan over
this package in `tests/test_tasks_never_activates_vintage.py`, A-C8 (2)/m1).

Registered by CALLING `celery_app.task(...)` rather than by decorating, exactly as
`app/mail/tasks.py` already does (and explains at the bottom of that module): celery ships no
type information, so `@celery_app.task(...)` on a typed function is an untyped decorator mypy
--strict refuses, and the standing rulings forbid a suppression comment as the fix. The functions
below stay ordinary, fully typed and directly callable -- which is also what the tests call.

`require_key()`/`require_contact()` (`app/census/client.py`) are `SystemExit(2)` gates -- correct
at a CLI entry point, fatal inside a worker process that also runs the mail pipeline every minute.
`_resolve_contact()`/`_resolve_key_and_contact()` catch that `SystemExit` and raise `_NotReady`
instead, naming only the missing variable (never a value -- there being none to redact); every
task below catches `_NotReady` in turn, records a failed `ingest_run` itself (the loader's OWN
`ingest.run()` never even opens without a client to hand it -- there is nothing else that would
record the attempt) and returns a summary dict instead of letting the worker go down with it
(tested).

The licence gate (spec §1: a `dataset_registry` row that is `unresolved`/`blocked` is never
ingested) is checked TWICE for `load_tiger` and `load_qwi` specifically (A-C8 (1) M1 and (9) i2):
`tiger.load_boundaries` has no internal `cleared` check at all, and `qwi.latest_available` probes
Census -- and `CensusClient.fetch_table` archives every successful body -- BEFORE `qwi.load`'s own
`cleared` check would ever run. `acs`/`cbp`/`bds`/`zbp`'s own `load()` functions already gate
before their first request, so no second check is needed in their tasks (harmless there, but
redundant)."""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import psycopg2
import psycopg2.extensions

from app.census import acs, bds, cbp, ingest, license, qwi, tiger, zbp
from app.census.client import CensusClient, missing_archive_settings, require_archive, require_contact, require_key
from app.census.registry import Dataset
from app.census.registry import load as load_registry
from app.config import settings
from app.db import sync_dsn
from app.storage import ObjectStore
from app.tasks.celery_app import celery_app
from app.version import VERSION

log = logging.getLogger(__name__)


class _NotReady(Exception):
    """A task's `CENSUS_API_KEY`/`CENSUS_CONTACT_EMAIL` prerequisite is absent. Every task below
    catches this -- it must never propagate `require_key()`/`require_contact()`'s
    `SystemExit(2)` (their CLI-entry-point gate, A-C4 ¶2) out of a Celery task and take the
    worker the mail pipeline shares down with it."""


def _conn() -> psycopg2.extensions.connection:
    """`app.db.sync_dsn()` (A-C8 (6)/m5): the same DSN normalisation `app.db.sync_conn()` and
    `scripts/census_load.py::normalize_dsn` already own -- this used to inline its own
    `.replace("postgresql+asyncpg://", "postgresql://", 1)`, byte-for-byte the same rule
    duplicated a third place."""
    c = psycopg2.connect(sync_dsn())
    c.autocommit = True
    return c


def _states(conn: psycopg2.extensions.connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips FROM market_state ORDER BY 1")
        return [r[0] for r in cur.fetchall()]


def _resolve_contact() -> str:
    """`CENSUS_CONTACT_EMAIL`, or `_NotReady` -- never `require_contact()`'s own `SystemExit(2)`
    (see the module docstring). Every task here sends a User-Agent, so every task needs this;
    `load_tiger`'s static-file fetch is the only one that needs nothing more."""
    try:
        return require_contact(os.environ)
    except SystemExit:
        raise _NotReady("CENSUS_CONTACT_EMAIL is not set; refused before any Census request") from None


def _resolve_key_and_contact() -> tuple[str, str]:
    """Both settings, for the five tasks that build a `CensusClient`. Two plain `str` results
    (never `str | None`) is the point: a boolean-flagged `_resolve(need_key=...)` returning
    `tuple[str | None, str]` forced every caller that passes `need_key=True` to convince mypy
    --strict the key it just got can never be `None` -- an `assert` repeated at every call site
    for a fact already true by construction. Two named functions, one per shape actually needed,
    make that assert unnecessary instead."""
    contact = _resolve_contact()
    try:
        key = require_key(os.environ)
    except SystemExit:
        raise _NotReady("CENSUS_API_KEY is not set; refused before any Census request") from None
    return key, contact


def _factory(key: str, contact: str, archive: ObjectStore | None) -> Callable[[Dataset], CensusClient]:
    """One client factory, shared by every load task (A-C8 (7)/m6) -- the first cut of this
    module wrote the same three-line closure four times over."""
    def factory(d: Dataset) -> CensusClient:
        return CensusClient(key, d, archive, version=VERSION, contact=contact)
    return factory


def _refuse(conn: psycopg2.extensions.connection, dataset_key: str, vintage: str, reason: str) -> dict[str, object]:
    """Records a failed `ingest_run` directly -- the loader's own `ingest.run()` never runs, since
    there is no client ready to hand it -- and returns a summary instead of raising."""
    log.error("[census] %s refused: %s", dataset_key, reason)
    run_id = ingest.start(conn, dataset_key, vintage)
    ingest.finish(conn, run_id, "failed", error=reason)
    return {"dataset": dataset_key, "error": reason}


def _resolve_archive(
    conn: psycopg2.extensions.connection, dataset_key: str, vintage: str
) -> tuple[ObjectStore | None, dict[str, object] | None]:
    """A-C1 ¶7 / controller amendment A-C11 (10): once a live Census load is possible
    (`settings.census_api_key` set), the raw archive must never come back silently disabled --
    every load task calls this right where it used to call bare `ObjectStore.from_settings(
    settings)`, exactly where `scripts/census_load.py`'s own `cmd_*` entry points call
    `require_archive` directly. `require_archive`'s `SystemExit(2)` (correct at a CLI entry point)
    is converted here the same way `require_key`/`require_contact`'s already are: caught and
    turned into a recorded, failed `ingest_run` instead of taking the worker down. Returns
    `(archive, None)` when ready to proceed, or `(None, refusal)` when the caller must return
    `refusal` immediately instead."""
    archive = ObjectStore.from_settings(settings)
    try:
        require_archive(archive, settings)
    except SystemExit:
        missing = missing_archive_settings(settings)
        reason = f"the raw archive is required once CENSUS_API_KEY is set; missing: {', '.join(missing)} (A-C1 ¶7)"
        return None, _refuse(conn, dataset_key, vintage, reason)
    return archive, None


def load_tiger(vintage: str = "2023") -> dict[str, object]:
    conn = _conn()
    try:
        ds = load_registry(conn)["tiger_cb"]
        if not ds.cleared:
            # A-C8 (9)/i2: tiger.load_boundaries has no internal cleared check at all (unlike
            # every other loader in this package) -- the task adds one, like its siblings.
            return _refuse(conn, "tiger_cb", vintage, f"tiger_cb is {ds.license_status}; loads are refused (spec §1 licensing gate)")
        try:
            contact = _resolve_contact()
        except _NotReady as exc:
            return _refuse(conn, "tiger_cb", vintage, str(exc))
        archive, refusal = _resolve_archive(conn, "tiger_cb", vintage)
        if refusal is not None:
            return refusal
        ua = f"PracticeMatch/{VERSION} ({contact})"
        # follow_redirects=False (tiger.py's own docstring: the Celery task is expected to build
        # its httpx.Client this way) -- a 3xx must never be silently followed into a body that
        # gets parsed and archived without this task ever seeing the redirect.
        with httpx.Client(headers={"User-Agent": ua}, follow_redirects=False) as http:
            return {"dataset": "tiger_cb", "counts": tiger.load_boundaries(conn, http, _states(conn), vintage, archive)}
    finally:
        conn.close()


def load_acs(dataset_key: str = "acs5") -> dict[str, object]:
    conn = _conn()
    try:
        ds = load_registry(conn)[dataset_key]
        try:
            key, contact = _resolve_key_and_contact()
        except _NotReady as exc:
            return _refuse(conn, dataset_key, ds.vintage, str(exc))
        archive, refusal = _resolve_archive(conn, dataset_key, ds.vintage)
        if refusal is not None:
            return refusal
        factory = _factory(key, contact, archive)
        return {"dataset": dataset_key, "rows": acs.load(conn, factory, dataset_key, _states(conn))}
    finally:
        conn.close()


def load_cbp() -> dict[str, object]:
    conn = _conn()
    try:
        ds = load_registry(conn)["cbp"]
        try:
            key, contact = _resolve_key_and_contact()
        except _NotReady as exc:
            return _refuse(conn, "cbp", ds.vintage, str(exc))
        archive, refusal = _resolve_archive(conn, "cbp", ds.vintage)
        if refusal is not None:
            return refusal
        factory = _factory(key, contact, archive)
        return {"rows": cbp.load(conn, factory, _states(conn))}
    finally:
        conn.close()


def load_zbp() -> dict[str, object]:
    """A-C8 (8)/i1: parity with `cbp`/`bds` -- manual trigger only, no beat entry (ZBP is annual
    and John-approved per load, `A-C8 (8)`); `zbp.load` gates on `cleared` internally, before its
    first request, exactly as `cbp.load`/`bds.load`/`acs.load` already do."""
    conn = _conn()
    try:
        ds = load_registry(conn)["zbp"]
        try:
            key, contact = _resolve_key_and_contact()
        except _NotReady as exc:
            return _refuse(conn, "zbp", ds.vintage, str(exc))
        archive, refusal = _resolve_archive(conn, "zbp", ds.vintage)
        if refusal is not None:
            return refusal
        factory = _factory(key, contact, archive)
        return {"rows": zbp.load(conn, factory, _states(conn))}
    finally:
        conn.close()


def load_qwi(year: int | None = None, quarter: int | None = None) -> dict[str, object]:
    conn = _conn()
    try:
        ds = load_registry(conn)["qwi"]
        if not ds.cleared:
            # A-C8 (1)/M1: `qwi.load`'s own `cleared` check runs only AFTER `latest_available`
            # has already probed Census (up to twelve requests) and archived every successful
            # body -- exactly the hazard `scripts/census_load.py::cmd_qwi` already guards against.
            # Checked here, before the resolve branch, so a blocked dataset makes no request at
            # all -- reached precisely when `year`/`quarter` are omitted, which is exactly the
            # shape the `qwi-quarterly` beat entry publishes.
            return _refuse(conn, "qwi", ds.vintage, f"qwi is {ds.license_status}; loads are refused (spec §1 licensing gate)")
        try:
            key, contact = _resolve_key_and_contact()
        except _NotReady as exc:
            return _refuse(conn, "qwi", ds.vintage, str(exc))
        archive, refusal = _resolve_archive(conn, "qwi", ds.vintage)
        if refusal is not None:
            return refusal
        factory = _factory(key, contact, archive)
        states = _states(conn)
        if year is None or quarter is None:
            if not states:
                # m5 (controller amendment A-C11 (6)): resolving the latest published quarter
                # indexes `states[0]` -- an empty `market_state` used to raise a bare `IndexError`
                # and crash the task instead of recording a named, failed `ingest_run`.
                return _refuse(conn, "qwi", ds.vintage, "market_state has no rows yet; qwi's latest-quarter resolution needs at least one state")
            now = datetime.now(UTC)
            with factory(ds) as client:
                year, quarter = qwi.latest_available(client, states[0], today=(now.year, (now.month - 1) // 3 + 1))
        rows = qwi.load(conn, factory, states, year=year, quarter=quarter)
        trimmed = qwi.trim(conn, keep=20)
        return {"year": year, "quarter": quarter, "rows": rows, "trimmed": trimmed}
    finally:
        conn.close()


def load_bds(year: int) -> dict[str, object]:
    conn = _conn()
    try:
        try:
            key, contact = _resolve_key_and_contact()
        except _NotReady as exc:
            return _refuse(conn, "bds", str(year), str(exc))
        archive, refusal = _resolve_archive(conn, "bds", str(year))
        if refusal is not None:
            return refusal
        factory = _factory(key, contact, archive)
        return {"year": year, "rows": bds.load(conn, factory, _states(conn), year=year)}
    finally:
        conn.close()


def license_audit() -> dict[str, object]:
    conn = _conn()
    try:
        try:
            contact = _resolve_contact()
        except _NotReady as exc:
            # No `ingest_run` row here (spec §9's ledger for this task is `license_audit_log`,
            # not `ingest_run` -- nothing was scoped to a dataset/vintage to record against): the
            # "never crash the worker on a missing key/contact" rule still applies, so this is
            # logged and returned rather than raised.
            log.error("[census] license_audit refused: %s", exc)
            return {"checked": 0, "drift": [], "error": str(exc)}
        ua = f"PracticeMatch/{VERSION} ({contact})"
        with httpx.Client(headers={"User-Agent": ua}) as http:
            results = license.audit(conn, http)
        return {"checked": len(results), "drift": [r.dataset_key for r in results if r.changed]}
    finally:
        conn.close()


# Registered by CALLING `celery_app.task(...)` rather than by decorating (see the module
# docstring): the functions above stay ordinary, fully typed and directly callable.
load_tiger_task = celery_app.task(name="census.load_tiger")(load_tiger)
load_acs_task = celery_app.task(name="census.load_acs")(load_acs)
load_cbp_task = celery_app.task(name="census.load_cbp")(load_cbp)
load_zbp_task = celery_app.task(name="census.load_zbp")(load_zbp)
load_qwi_task = celery_app.task(name="census.load_qwi")(load_qwi)
load_bds_task = celery_app.task(name="census.load_bds")(load_bds)
license_audit_task = celery_app.task(name="census.license_audit")(license_audit)

# Phase B, B2: geocode_listing_task registers here.

# Phase B, B4: backfill_listing_task and materialize_all_task register here.
