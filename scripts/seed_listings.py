#!/usr/bin/env python3
"""Seed (or re-seed) the eighteen demo hospitals into a Practice Match database.

Idempotent: an upsert keyed on `slug`, so a second run changes nothing but `updated_at` and
`listed_at` — the latter is recomputed from `listed_days_ago` on every import by design, so the
seeds never read as a year old; every row shifts by the same amount, so their relative order (what
`listing_page_idx` pages on) is preserved. Surviving rows keep their ids, so photo URLs and deep
links stay valid across a re-seed.

Every import also REMOVES the seed rows the file no longer carries (amendment A-L4, John
2026-09-08: "must remove the old seeded data when importing the new data"): in the same
transaction as the upsert, every `source='seed'` row whose slug is absent from
`seeds/hospitals.json` is deleted. `--reset` is the bigger hammer — it deletes every
`source='seed'` row first, reaching the same end state with fresh ids. A seller's own listing
(`source='seller'`) is never touched by either path; that is the whole point of the column.

A listing this seeder does not own is never rewritten: if a row with any other `source` already
holds one of the seed slugs, the import REFUSES (exit 5) and nothing commits — the operator is
told which slugs, and decides. Belt and braces, the upsert itself is scoped
`ON CONFLICT (slug) DO UPDATE ... WHERE listing.source = 'seed'`, so even a row inserted between
the check and the upsert cannot be overwritten; the zero-row update that leaves is refused too,
rather than skipping a listing in silence.

Runs inside the api container: `railway ssh --service api --environment QA` then
`python scripts/seed_listings.py --reset`, or as the `seed` role of scripts/start.sh.
Production takes `--production`, the way scripts/bootstrap_admin.py takes it: without the flag
`ENVIRONMENT=production` is refused (exit 2) before anything is opened, and with it the run says
on its first line which environment it is writing to — never on production without John's go
(spec 2026-09-06 D7).

Exit codes mirror scripts/migrate.py: 0 done, 2 refused before anything is opened (ENVIRONMENT
unset, production without --production, or DATABASE_URL unset), 3 database unreachable
(retryable), 4 the seed data is missing or malformed OR the database refused the import (an
unmigrated database is the usual cause), 5 a non-seed listing owns a seed slug (nothing was
written). Only 3 is retryable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
SEEDS_FILE = ROOT / "seeds" / "hospitals.json"
PHOTO_INDEX = ROOT / "seeds" / "hospitals" / "photos" / "index.json"
# Its own key, distinct from scripts/migrate.py's 'PMMG': two operators seeding at once must
# serialise, and a seed must not wait on (or block) a migration. ASCII 'PMSD'.
LOCK_KEY = 0x504D5344


def normalize_dsn(dsn: str) -> str:
    """The same normalisation as `scripts/migrate.normalize_dsn`, duplicated here deliberately.

    The container runs this file as `python scripts/seed_listings.py`, which puts `/app/scripts`
    on `sys.path[0]` — **not** `/app`. `scripts/` has no `__init__.py`, the project is
    `package-mode = false` and the image installs with `--no-root`, so nothing ever puts the
    repo root on the path: `from scripts.migrate import ...` raises ModuleNotFoundError the
    moment the seed role runs, and no test catches it (pytest and `runpy.run_path` both start
    with the repo root already on the path). `scripts/migrate.py` works in the container for
    exactly this reason — it imports nothing but stdlib and psycopg2.

    Twelve lines of duplication instead of a `sys.path` mutation, and
    `test_normalize_dsn_agrees_with_the_migration_runner` pins the two to the same answers."""
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


UPSERT = """
INSERT INTO listing (
  slug, name, street, city, state, zip, phone, hours, status, location_disclosed, name_disclosed,
  geom, area, type, market, price, rev, docs, rooms, sqft, bldg, est, listed_at,
  note, staff, services, facility, ownership, photos, source, updated_at
) VALUES (
  %(slug)s, %(name)s, %(street)s, %(city)s, %(state)s, %(zip)s, %(phone)s, %(hours)s,
  %(status)s, %(location_disclosed)s, %(name_disclosed)s,
  ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography,
  %(area)s, %(type)s, %(market)s, %(price)s, %(rev)s, %(docs)s, %(rooms)s, %(sqft)s,
  %(bldg)s, %(est)s, now() - make_interval(days => %(listed_days_ago)s),
  %(note)s, %(staff)s, %(services)s, %(facility)s, %(ownership)s,
  %(photos)s::jsonb, 'seed', now()
)
ON CONFLICT (slug) DO UPDATE SET
  name = EXCLUDED.name, street = EXCLUDED.street, city = EXCLUDED.city, state = EXCLUDED.state,
  zip = EXCLUDED.zip, phone = EXCLUDED.phone, hours = EXCLUDED.hours, status = EXCLUDED.status,
  location_disclosed = EXCLUDED.location_disclosed, name_disclosed = EXCLUDED.name_disclosed,
  geom = EXCLUDED.geom, area = EXCLUDED.area,
  type = EXCLUDED.type, market = EXCLUDED.market, price = EXCLUDED.price, rev = EXCLUDED.rev,
  docs = EXCLUDED.docs, rooms = EXCLUDED.rooms, sqft = EXCLUDED.sqft, bldg = EXCLUDED.bldg,
  est = EXCLUDED.est, listed_at = EXCLUDED.listed_at, note = EXCLUDED.note,
  staff = EXCLUDED.staff, services = EXCLUDED.services, facility = EXCLUDED.facility,
  ownership = EXCLUDED.ownership, photos = EXCLUDED.photos, updated_at = now()
WHERE listing.source = 'seed'
"""

# The pre-flight the refusal is built on: one SELECT naming every seed slug some other `source`
# already owns, run before anything is written, so the operator gets the whole list at once
# instead of discovering them one failed import at a time. (A module constant so the backstop
# arm below can be reached by a test without a real race.)
COLLISION_CHECK = "SELECT slug FROM listing WHERE source <> 'seed' AND slug = ANY(%s) ORDER BY slug"

# A-L4: everything the file no longer carries, in the same transaction as the upsert. `--reset`
# drops the slug filter and takes the lot.
DELETE_STALE = "DELETE FROM listing WHERE source = 'seed' AND NOT (slug = ANY(%s))"
DELETE_ALL_SEED = "DELETE FROM listing WHERE source = 'seed'"


class SeedDataError(Exception):
    """The seed file or the photo inventory is missing or does not carry what it must."""


class SlugCollision(Exception):
    """A listing with another `source` already owns one of the seed slugs.

    Not something to resolve automatically: the row belongs to a seller, and overwriting it with
    a demo hospital would be the loudest version of exactly what `source` exists to prevent."""

    def __init__(self, slugs: list[str]) -> None:
        super().__init__(f"a non-seed listing already owns {', '.join(slugs)}")


def load_seed(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        hospitals = data["hospitals"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SeedDataError(f"{path}: {type(exc).__name__}") from None
    if not isinstance(hospitals, list) or not hospitals:
        raise SeedDataError(f"{path}: no hospitals")
    return [dict(h) for h in hospitals]


def load_photo_index(path: Path) -> dict[str, Any]:
    """The same hardening as `load_seed`: a malformed inventory is exit 4, never a traceback."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        hospitals = loaded["hospitals"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SeedDataError(f"{path}: {type(exc).__name__}") from None
    if not isinstance(hospitals, dict):
        raise SeedDataError(f"{path}: hospitals is not an object keyed by slug")
    return dict(loaded)


def photo_paths(slug: str, index: dict[str, Any]) -> list[str | None]:
    """Relative paths under seeds/hospitals/photos/, in inventory order — which is the design's
    SLOT order, with `None` for a slot the curation left empty (A-L10).

    Positional, never compacted: `p.photos[i]` fills the design's photo slot `i` (amendment
    A12.2), so dropping an empty slot would slide every later photograph up one and caption it
    with the subject it does not show. A `None` reaches the browser as JSON `null`, where the
    design's own `photoSet` renders its placeholder for that slot."""
    entries = index.get("hospitals", {}).get(slug, [])
    try:
        return [None if entry["file"] is None else f"{slug}/{entry['file']}" for entry in entries]
    except (KeyError, TypeError) as exc:
        raise SeedDataError(f"{slug}: photo inventory entry is unusable ({type(exc).__name__})") from None


def row_params(hospital: dict[str, Any], photos: list[str | None]) -> dict[str, Any]:
    keys = (
        "slug", "name", "street", "city", "state", "zip", "phone", "hours", "status",
        "location_disclosed", "name_disclosed", "lat", "lng", "area", "type", "market",
        "price", "rev", "docs", "rooms", "sqft", "bldg", "est", "listed_days_ago", "note",
        "staff", "services", "facility", "ownership",
    )
    try:
        params: dict[str, Any] = {key: hospital[key] for key in keys}
    except KeyError as exc:
        raise SeedDataError(f"{hospital.get('slug', '?')}: missing {exc}") from None
    params["photos"] = json.dumps(photos)
    return params


def seed(dsn: str, *, reset: bool = False) -> int:
    hospitals = load_seed(SEEDS_FILE)
    index = load_photo_index(PHOTO_INDEX)
    rows = [row_params(h, photo_paths(str(h["slug"]), index)) for h in hospitals]
    slugs = [str(params["slug"]) for params in rows]
    conn = psycopg2.connect(normalize_dsn(dsn))
    try:
        with conn, conn.cursor() as cur:
            # One transaction, one writer: the removal and the upsert are never observed apart,
            # and two operators seeding at once serialise instead of interleaving.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
            # Before anything is written: refuse the whole import if a listing this seeder does
            # not own holds one of these slugs. Raising here rolls the transaction back, so a
            # refused run leaves the database exactly as it found it.
            cur.execute(COLLISION_CHECK, (slugs,))
            collisions = [str(row[0]) for row in cur.fetchall()]
            if collisions:
                raise SlugCollision(collisions)
            if reset:
                cur.execute(DELETE_ALL_SEED)
            else:
                cur.execute(DELETE_STALE, (slugs,))
            removed = cur.rowcount
            # The seed rows that survived the delete are, by construction, exactly the slugs the
            # file carries — so this is the update count, and the rest are inserts. Counted from
            # the table rather than from `xmax`, which is an implementation detail. Exact now
            # that the check above has refused every slug another `source` owns: nothing but a
            # seed row can be on the receiving end of one of these upserts.
            cur.execute("SELECT count(*) FROM listing WHERE source = 'seed'")
            # `SELECT count(*)` always returns exactly one row.
            updated = int(cast("tuple[int]", cur.fetchone())[0])
            for params in rows:
                cur.execute(UPSERT, params)
                if cur.rowcount != 1:
                    # The scoped ON CONFLICT matched no row to update: another transaction
                    # inserted a non-seed listing on this slug after the check above. Refusing
                    # beats skipping it quietly.
                    raise SlugCollision([str(params["slug"])])
    finally:
        conn.close()
    print(f"[seed] inserted {len(rows) - updated}, updated {updated}, removed {removed}")
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the demo hospitals (spec 2026-09-06 D7).")
    parser.add_argument("--reset", action="store_true", help="delete every source='seed' row first")
    parser.add_argument("--production", action="store_true", help="required to run against ENVIRONMENT=production")
    args = parser.parse_args(argv)
    environment = os.environ.get("ENVIRONMENT")
    if environment is None:
        # Fail CLOSED, the way scripts/bootstrap_admin.py does through `settings.environment`
        # (app/config.py declares it with no default, so a missing variable stops that script at
        # import). Keying on `.get(..., "")` here would let production's DATABASE_URL and a
        # forgotten ENVIRONMENT put eighteen demo hospitals in the stakeholders' database.
        print("[seed] ENVIRONMENT is not set — refusing to guess which database this is", file=sys.stderr)
        return 2
    if environment.lower() == "production":
        # The same "say it out loud" shape as scripts/bootstrap_admin.py and scripts/deploy.sh's
        # Railway-project guard, for the same reason: this machine speaks to more than one
        # environment, and these are demo listings.
        if not args.production:
            print("[seed] refusing to run against production without --production", file=sys.stderr)
            return 2
        print("[seed] running against PRODUCTION, as --production says")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[seed] DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        count = seed(dsn, reset=args.reset)
    except SeedDataError as exc:
        print(f"[seed] seed data unusable: {exc}", file=sys.stderr)
        return 4
    except psycopg2.OperationalError as exc:
        print(f"[seed] database unreachable: {type(exc).__name__}", file=sys.stderr)
        return 3
    except SlugCollision as exc:
        print(f"[seed] refusing: {exc} — nothing was written", file=sys.stderr)
        return 5
    except psycopg2.Error as exc:
        # Anything the database itself refused. The realistic one is an UNMIGRATED database:
        # `listing` does not exist and psycopg2 raises UndefinedTable, which is a
        # ProgrammingError, not an OperationalError — it used to escape as a traceback and exit 1.
        # Not retryable, so it joins 4 rather than 3. Only the class and the SQLSTATE are printed:
        # a psycopg2 message can carry the statement, and the statement carries the data.
        print(f"[seed] database refused the import: {type(exc).__name__} ({getattr(exc, 'pgcode', '?')})", file=sys.stderr)
        return 4
    print(f"[seed] done - {count} listings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
