"""Celery entry points for the market-data layer (Task A8). Phase B adds `census.geocode_listing`,
`census.materialize_metrics` and `census.backfill_listing`.

Each task opens its own psycopg2 connection through `_conn()`, the same shape
`scripts/census_load.py`'s own `_conn(dsn)` uses (reading `settings.database_url` here since a
Celery task takes no CLI arguments) -- Census loads are occasional and heavy (annual/quarterly),
not the mail pipeline's per-minute drain `app.db.sync_conn()`'s pool exists for, so a plain
connection per invocation is the right shape here too. Every task calls the SAME loader and
activation functions the CLI calls (`app.census.acs/cbp/bds/qwi/tiger`) -- never a second
implementation -- and NOTHING here ever calls `app.census.vintage.activate`: flipping
`active_vintage` stays operator-initiated, through `scripts/census_load.py activate`, never a
scheduled task (A-C7 (8)).

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
(tested)."""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

import httpx
import psycopg2
import psycopg2.extensions

from app.census import acs, bds, cbp, ingest, license, qwi, tiger
from app.census.client import CensusClient, require_contact, require_key
from app.census.registry import Dataset
from app.census.registry import load as load_registry
from app.config import settings
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
    c = psycopg2.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
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
    """Both settings, for the four tasks that build a `CensusClient`. Two plain `str` results
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


def _refuse(conn: psycopg2.extensions.connection, dataset_key: str, vintage: str, reason: str) -> dict[str, object]:
    """Records a failed `ingest_run` directly -- the loader's own `ingest.run()` never runs, since
    there is no client ready to hand it -- and returns a summary instead of raising."""
    log.error("[census] %s refused: %s", dataset_key, reason)
    run_id = ingest.start(conn, dataset_key, vintage)
    ingest.finish(conn, run_id, "failed", error=reason)
    return {"dataset": dataset_key, "error": reason}


def load_tiger(vintage: str = "2023") -> dict[str, object]:
    conn = _conn()
    try:
        try:
            contact = _resolve_contact()
        except _NotReady as exc:
            return _refuse(conn, "tiger_cb", vintage, str(exc))
        archive = ObjectStore.from_settings(settings)
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
        archive = ObjectStore.from_settings(settings)

        def factory(d: Dataset) -> CensusClient:
            return CensusClient(key, d, archive, version=VERSION, contact=contact)

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
        archive = ObjectStore.from_settings(settings)

        def factory(d: Dataset) -> CensusClient:
            return CensusClient(key, d, archive, version=VERSION, contact=contact)

        return {"rows": cbp.load(conn, factory, _states(conn))}
    finally:
        conn.close()


def load_qwi(year: int | None = None, quarter: int | None = None) -> dict[str, object]:
    conn = _conn()
    try:
        ds = load_registry(conn)["qwi"]
        try:
            key, contact = _resolve_key_and_contact()
        except _NotReady as exc:
            return _refuse(conn, "qwi", ds.vintage, str(exc))
        archive = ObjectStore.from_settings(settings)

        def factory(d: Dataset) -> CensusClient:
            return CensusClient(key, d, archive, version=VERSION, contact=contact)

        states = _states(conn)
        if year is None or quarter is None:
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
        archive = ObjectStore.from_settings(settings)

        def factory(d: Dataset) -> CensusClient:
            return CensusClient(key, d, archive, version=VERSION, contact=contact)

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
load_qwi_task = celery_app.task(name="census.load_qwi")(load_qwi)
load_bds_task = celery_app.task(name="census.load_bds")(load_bds)
license_audit_task = celery_app.task(name="census.license_audit")(license_audit)
