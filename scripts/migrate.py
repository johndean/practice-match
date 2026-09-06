#!/usr/bin/env python3
"""Ledger-based SQL migration runner (pattern from Rounds.vin).

Applies migrations/NNN_*.sql in name order, each exactly once, recorded in
schema_migrations, under a Postgres advisory lock (api and worker share one
railway.json, so two pre-deploy runs can overlap). A failing file raises and
aborts the deploy; it is not recorded, so the next deploy retries it.

Each file's own SQL and its `schema_migrations` ledger row commit as ONE
transaction (see `run` below) — a migration file must therefore never contain
its own `BEGIN`/`COMMIT`/`ROLLBACK`. Statements that cannot run inside a
transaction at all (`CREATE INDEX CONCURRENTLY`, `VACUUM`, `CREATE DATABASE`)
are not supported by this runner and need their own runner path — add
statement splitting (or a separate non-transactional runner) when the first
such migration is written (Identity plan, Task I1).

An applied migration is IMMUTABLE: the ledger records each file's sha256, and a
file whose content no longer matches the checksum recorded for it stops the run
with exit 4 rather than leaving the database silently out of step with the tree.
Amend a never-deployed file only while no persistent database has run it, and say
so in the commit (Task I5c, Step 0 — I6 re-review O3, ruled 2026-09-07).
"""
from __future__ import annotations

import hashlib
import os
import sys
from glob import glob
from pathlib import Path

import psycopg2
import psycopg2.extensions

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "migrations"
LOCK_KEY = 0x504D4D47  # ASCII 'PMMG'


class ChangedMigration(RuntimeError):
    """An already-applied file whose content no longer matches its recorded checksum. Carries the
    file NAME as its only argument: `main` turns it into the operator-facing line and exit 4, so
    that the message lives in exactly one place."""


def checksum(path: str) -> str:
    """sha256 of the file's BYTES — what the ledger records and what a later run compares against.
    Bytes, not decoded text, so a line-ending or encoding change is a change."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_dsn(dsn: str) -> str:
    """psycopg2 wants postgresql://; the app may hold postgresql+asyncpg://. Railway's
    PostGIS template also hands out the legacy postgres:// scheme — libpq accepts it
    unmodified, but normalise it here too for robustness/consistency with
    app/checks.py's async_dsn (fix round 5)."""
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[str]:
    return sorted(glob(str(directory / "[0-9][0-9][0-9]_*.sql")))


def refuse_changed_files(cur: psycopg2.extensions.cursor, files: list[str]) -> None:
    """Raises `ChangedMigration` for the first already-applied file whose bytes no longer hash to
    the checksum the ledger recorded. Runs BEFORE anything is applied, so a tree that disagrees
    with the database changes nothing at all.

    A NULL checksum is a row written by a runner older than this change (or by the `ADD COLUMN`
    below), and is never a refusal: the first deploy carrying this change must not refuse to run
    against every database that already exists."""
    cur.execute("SELECT name, checksum FROM schema_migrations")
    recorded = dict(cur.fetchall())
    for path in files:
        stored = recorded.get(Path(path).name)
        if stored is not None and stored != checksum(path):
            raise ChangedMigration(Path(path).name)


def run(dsn: str, directory: Path | None = None) -> list[str]:
    # Resolved here rather than as a default argument (Task I5c): a default binds
    # `MIGRATIONS_DIR` once, at import, so `main()` — which passes no directory — could not be
    # pointed at a scratch tree by a test.
    directory = MIGRATIONS_DIR if directory is None else directory
    applied: list[str] = []
    conn = psycopg2.connect(normalize_dsn(dsn))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
            try:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now(),"
                    " checksum text)"
                )
                # A ledger created before Task I5c has no `checksum` column at all.
                cur.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum text")
                files = migration_files(directory)
                refuse_changed_files(cur, files)
                for path in files:
                    name = Path(path).name
                    cur.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (name,))
                    if cur.fetchone():
                        print(f"  ✓ {name} (already applied)")
                        continue
                    print(f"  → {name}")
                    # The file's own SQL and its ledger row commit as ONE transaction:
                    # a failing ledger insert must not leave the file's SQL applied. The checksum
                    # is written in that same transaction — a ledger row without one would read as
                    # a legacy row and never be checked again.
                    conn.autocommit = False
                    try:
                        cur.execute(Path(path).read_text(encoding="utf-8"))
                        cur.execute("INSERT INTO schema_migrations (name, checksum) VALUES (%s, %s)", (name, checksum(path)))
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise
                    finally:
                        conn.autocommit = True
                    applied.append(name)
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    finally:
        conn.close()
    return applied


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[migrate] DATABASE_URL is not set", file=sys.stderr)
        return 2
    print(f"[migrate] applying from {MIGRATIONS_DIR}")
    try:
        applied = run(dsn)
    except psycopg2.OperationalError as exc:  # cannot reach the database: retryable, distinct from a broken file
        print(f"[migrate] database unreachable: {type(exc).__name__}", file=sys.stderr)
        return 3
    except ChangedMigration as exc:  # the tree disagrees with the database: never retryable, and 3 must stay "retry"
        print(f"[migrate] {exc} changed after it was applied — drop and recreate the database or restore the file", file=sys.stderr)
        return 4
    print(f"[migrate] done — {len(applied)} applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
