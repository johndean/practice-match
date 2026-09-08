#!/usr/bin/env python3
"""Seed (or re-seed) the eighteen demo hospitals into a Practice Match database.

Idempotent: an upsert keyed on `slug`, so a second run changes nothing but `updated_at`, and the
surviving rows keep their ids — photo URLs and deep links stay valid across a re-seed.

Every import also REMOVES the seed rows the file no longer carries (amendment A-L4, John
2026-09-08: "must remove the old seeded data when importing the new data"): in the same
transaction as the upsert, every `source='seed'` row whose slug is absent from
`seeds/hospitals.json` is deleted. `--reset` is the bigger hammer — it deletes every
`source='seed'` row first, reaching the same end state with fresh ids. A seller's own listing
(`source='seller'`) is never touched by either path; that is the whole point of the column.

Runs inside the api container: `railway ssh --service api --environment QA` then
`python scripts/seed_listings.py --reset`, or as the `seed` role of scripts/start.sh.
It refuses outright on `ENVIRONMENT=production`, exactly as scripts/seed_persona.py refuses —
never on production without John's go (spec 2026-09-06 D7).

Exit codes mirror scripts/migrate.py: 0 done, 2 refused (production, or DATABASE_URL unset),
3 database unreachable (retryable), 4 the seed data is missing or malformed (not retryable).
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
"""

# A-L4: everything the file no longer carries, in the same transaction as the upsert. `--reset`
# drops the slug filter and takes the lot.
DELETE_STALE = "DELETE FROM listing WHERE source = 'seed' AND NOT (slug = ANY(%s))"
DELETE_ALL_SEED = "DELETE FROM listing WHERE source = 'seed'"


class SeedDataError(Exception):
    """The seed file or the photo inventory is missing or does not carry what it must."""


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
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SeedDataError(f"{path}: {type(exc).__name__}") from None
    return dict(loaded)


def photo_paths(slug: str, index: dict[str, Any]) -> list[str]:
    """Relative paths under seeds/hospitals/photos/, in inventory order."""
    entries = index.get("hospitals", {}).get(slug, [])
    return [f"{slug}/{entry['file']}" for entry in entries]


def row_params(hospital: dict[str, Any], photos: list[str]) -> dict[str, Any]:
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
            if reset:
                cur.execute(DELETE_ALL_SEED)
            else:
                cur.execute(DELETE_STALE, (slugs,))
            removed = cur.rowcount
            # The seed rows that survived the delete are, by construction, exactly the slugs the
            # file carries — so this is the update count, and the rest are inserts. Counted from
            # the table rather than from `xmax`, which is an implementation detail. (A row of
            # another `source` holding one of these slugs would be updated in place and counted
            # here as an insert; nothing in this plan creates one, and the alternative — the
            # seeder silently rewriting a seller's row — is the thing to notice, not the count.)
            cur.execute("SELECT count(*) FROM listing WHERE source = 'seed'")
            # `SELECT count(*)` always returns exactly one row.
            updated = int(cast("tuple[int]", cur.fetchone())[0])
            for params in rows:
                cur.execute(UPSERT, params)
    finally:
        conn.close()
    print(f"[seed] inserted {len(rows) - updated}, updated {updated}, removed {removed}")
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the demo hospitals (spec 2026-09-06 D7).")
    parser.add_argument("--reset", action="store_true", help="delete every source='seed' row first")
    args = parser.parse_args(argv)
    if os.environ.get("ENVIRONMENT", "").lower() == "production":
        print("[seed] refusing to run against production — these are demo listings (D7: never on production without John's go)", file=sys.stderr)
        return 2
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
    print(f"[seed] done - {count} listings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
