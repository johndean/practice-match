#!/usr/bin/env python3
"""Ledger-based SQL migration runner (pattern from Rounds.vin).

Applies migrations/NNN_*.sql in name order, each exactly once, recorded in
schema_migrations, under a Postgres advisory lock (api and worker share one
railway.json, so two pre-deploy runs can overlap). A failing file raises and
aborts the deploy; it is not recorded, so the next deploy retries it.

Not supported yet: statements that cannot run inside a transaction
(CREATE INDEX CONCURRENTLY). Add statement splitting when the first such
migration is written.
"""
from __future__ import annotations

import os
import sys
from glob import glob
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "migrations"
LOCK_KEY = 0x504D4D47  # ASCII 'PMMG'


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


def run(dsn: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    applied: list[str] = []
    conn = psycopg2.connect(normalize_dsn(dsn))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
            try:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
                )
                for path in migration_files(directory):
                    name = Path(path).name
                    cur.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (name,))
                    if cur.fetchone():
                        print(f"  ✓ {name} (already applied)")
                        continue
                    print(f"  → {name}")
                    # The file's own SQL and its ledger row commit as ONE transaction:
                    # a failing ledger insert must not leave the file's SQL applied.
                    conn.autocommit = False
                    try:
                        cur.execute(Path(path).read_text(encoding="utf-8"))
                        cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (name,))
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
    print(f"[migrate] done — {len(applied)} applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
