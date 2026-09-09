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

Ownership (spec 2026-09-08 D25, John's ruling): the eighteen belong to
`seller@practice-match.test`, looked up BY EMAIL at seed time and written on both halves of the
upsert, so a re-seed re-asserts it. `--owner <email>` names a different account, `--no-owner`
seeds them unowned, an account that does not exist here leaves `seller_id` NULL and says so on
stdout (production has no persona accounts and must still be seedable), and on a --production run
the default is not applied at all unless `--owner` is passed.

...and a hospital its seller has EDITED is never re-seeded (amendment A-SL21): the first seller write
of any kind flips the row's `source` to 'seller' in the API's own transaction, every statement here is
scoped `source = 'seed'`, so the row is skipped — counted and named on the way out — while its
untouched siblings refresh. A seed slug held by a listing that belongs to nobody is unexplained and
still stops the whole import (exit 5).

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
from uuid import UUID

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


# D25, John's ruling: "Assign all eighteen QA seed listings to `seller@practice-match.test`, with
# real `seller_id` ownership." The persona scripts/seed_persona.py creates with roles buyer+seller
# (its ORACLE_PERSONAS loop), and which QA already has. An ADDRESS, never an id: the account is
# looked up at seed time, so this file carries no environment's primary keys.
SEED_OWNER_EMAIL = "seller@practice-match.test"


def resolve_owner(conn: Any, email: str | None) -> UUID | None:
    """The account id to own these rows, or None.

    **Absent is not a refusal.** Production has no persona accounts — `PERSONA_PASSWORD` is never
    set there and seed_persona.py refuses production outright (A-S6.1/A-S6.2) — and production
    must still be seedable. So a missing account leaves `seller_id` NULL and the run SAYS SO on
    stdout, which is a line an operator can act on rather than an exit code that stops a deploy.

    It says so from `seed()`, AFTER the commit, not from here (SL6 review, Minor-1): this runs
    inside the transaction, and the per-row backstop below can still roll that transaction back."""
    if email is None:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM account WHERE email = %s", (email,))
        found = cur.fetchone()
    if found is None:
        return None
    return cast("UUID", found[0])


UPSERT = """
INSERT INTO listing (
  slug, name, street, city, state, zip, phone, hours, status, location_disclosed, name_disclosed,
  rev_disclosed, documents_disclosed, seller_id,
  geom, area, type, market, price, rev, docs, rooms, sqft, bldg, est, listed_at,
  note, staff, services, facility, ownership, photos, photo_captions, source, updated_at
) VALUES (
  %(slug)s, %(name)s, %(street)s, %(city)s, %(state)s, %(zip)s, %(phone)s, %(hours)s,
  %(status)s, %(location_disclosed)s, %(name_disclosed)s,
  %(rev_disclosed)s, %(documents_disclosed)s, %(seller_id)s,
  ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography,
  %(area)s, %(type)s, %(market)s, %(price)s, %(rev)s, %(docs)s, %(rooms)s, %(sqft)s,
  %(bldg)s, %(est)s, now() - make_interval(days => %(listed_days_ago)s),
  %(note)s, %(staff)s, %(services)s, %(facility)s, %(ownership)s,
  %(photos)s::jsonb, %(photo_captions)s::jsonb, 'seed', now()
)
ON CONFLICT (slug) DO UPDATE SET
  name = EXCLUDED.name, street = EXCLUDED.street, city = EXCLUDED.city, state = EXCLUDED.state,
  zip = EXCLUDED.zip, phone = EXCLUDED.phone, hours = EXCLUDED.hours, status = EXCLUDED.status,
  location_disclosed = EXCLUDED.location_disclosed, name_disclosed = EXCLUDED.name_disclosed,
  -- D22 and D25, on the UPDATE half as well as the insert: the eighteen already exist on QA, so
  -- a disclosure flag or an ownership that only landed on an INSERT would never land at all.
  rev_disclosed = EXCLUDED.rev_disclosed, documents_disclosed = EXCLUDED.documents_disclosed,
  seller_id = EXCLUDED.seller_id,
  geom = EXCLUDED.geom, area = EXCLUDED.area,
  type = EXCLUDED.type, market = EXCLUDED.market, price = EXCLUDED.price, rev = EXCLUDED.rev,
  docs = EXCLUDED.docs, rooms = EXCLUDED.rooms, sqft = EXCLUDED.sqft, bldg = EXCLUDED.bldg,
  est = EXCLUDED.est, listed_at = EXCLUDED.listed_at, note = EXCLUDED.note,
  staff = EXCLUDED.staff, services = EXCLUDED.services, facility = EXCLUDED.facility,
  ownership = EXCLUDED.ownership, photos = EXCLUDED.photos,
  photo_captions = EXCLUDED.photo_captions, updated_at = now()
WHERE listing.source = 'seed'
"""

# The pre-flight both outcomes are built on: one SELECT naming every seed slug some other `source`
# already owns, run before anything is written, so the operator gets the whole list at once
# instead of discovering them one failed import at a time. (A module constant so the backstop
# arm below can be reached by a test without a real race.)
#
# `seller_id` comes back with the slug because the two cases are different (A-SL21). A row that
# BELONGS to someone is a seeded hospital its seller has edited — the wizard flipped `source` on
# their first write, precisely so this importer would leave it alone — and it is SKIPPED, counted
# and named. A row that belongs to nobody is unexplained (no seller can have claimed it), so it
# still stops the whole import at exit 5, which is what that code has always meant.
COLLISION_CHECK = ("SELECT slug, seller_id FROM listing"
                   " WHERE source <> 'seed' AND slug = ANY(%s) ORDER BY slug")

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


def photo_captions(slug: str, index: dict[str, Any]) -> list[str | None]:
    """One description per photograph, in inventory order — PARALLEL to `photo_paths` (A-L11).

    A photograph carries its own words because the design's six captions are fixed per slot and
    cannot describe a seventh photograph at all: `photoSet` reads `p.photoCaptions[i]` and falls
    back to the slot's own caption (amendment A15). Today the words are the supplier's filename
    description, recorded by `scripts/prepare_photos.py::caption_of`; a seller writes their own in
    Wave 2b. `None` where the position holds no photograph, so the two arrays stay index-for-index
    parallel however thin the folder was."""
    entries = index.get("hospitals", {}).get(slug, [])
    try:
        return [None if entry["caption"] is None else str(entry["caption"]) for entry in entries]
    except (KeyError, TypeError) as exc:
        raise SeedDataError(f"{slug}: photo inventory entry is unusable ({type(exc).__name__})") from None


def row_params(
    hospital: dict[str, Any], photos: list[str | None], captions: list[str | None]
) -> dict[str, Any]:
    keys = (
        "slug", "name", "street", "city", "state", "zip", "phone", "hours", "status",
        "location_disclosed", "name_disclosed", "rev_disclosed", "documents_disclosed",
        "lat", "lng", "area", "type", "market",
        "price", "rev", "docs", "rooms", "sqft", "bldg", "est", "listed_days_ago", "note",
        "staff", "services", "facility", "ownership",
    )
    try:
        params: dict[str, Any] = {key: hospital[key] for key in keys}
    except KeyError as exc:
        raise SeedDataError(f"{hospital.get('slug', '?')}: missing {exc}") from None
    params["photos"] = json.dumps(photos)
    params["photo_captions"] = json.dumps(captions)
    return params


def seed(dsn: str, *, reset: bool = False, owner: str | None = SEED_OWNER_EMAIL) -> int:
    hospitals = load_seed(SEEDS_FILE)
    index = load_photo_index(PHOTO_INDEX)
    rows = [
        row_params(h, photo_paths(str(h["slug"]), index), photo_captions(str(h["slug"]), index))
        for h in hospitals
    ]
    slugs = [str(params["slug"]) for params in rows]
    conn = psycopg2.connect(normalize_dsn(dsn))
    try:
        with conn, conn.cursor() as cur:
            # One transaction, one writer: the removal and the upsert are never observed apart,
            # and two operators seeding at once serialise instead of interleaving.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
            # Before anything is written: split the seed slugs some other `source` already holds
            # into the seller's own, which are skipped (A-SL21), and the unexplained, which refuse
            # the whole import. Raising here rolls the transaction back, so a refused run leaves
            # the database exactly as it found it.
            cur.execute(COLLISION_CHECK, (slugs,))
            held = cur.fetchall()
            claimed = sorted(str(row[0]) for row in held if row[1] is not None)
            collisions = [str(row[0]) for row in held if row[1] is None]
            if collisions:
                raise SlugCollision(collisions)
            seller_id = resolve_owner(conn, owner)
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
                if params["slug"] in claimed:
                    # A-SL21: the seller's own since their first edit. Not upserted, not deleted
                    # (both are scoped `source = 'seed'`), and not counted as an insert below.
                    continue
                cur.execute(UPSERT, {**params, "seller_id": seller_id})
                if cur.rowcount != 1:
                    # The scoped ON CONFLICT matched no row to update: another transaction
                    # inserted a non-seed listing on this slug after the check above. Refusing
                    # beats skipping it quietly.
                    raise SlugCollision([str(params["slug"])])
    finally:
        conn.close()
    # Everything below runs only when the transaction COMMITTED (SL6 review, Minor-1): a run that
    # wrote nothing — the pre-flight refusal, or the per-row backstop rolling back a race — says
    # nothing at all, rather than telling an operator how their listings were seeded when none was.
    if owner is not None and seller_id is None:
        print(f"[seed] {owner} does not exist here — seeding the listings unowned (seller_id NULL)")
    print(f"[seed] inserted {len(rows) - len(claimed) - updated}, updated {updated},"
          f" removed {removed}, skipped {len(claimed)} seller-owned")
    if claimed:
        print(f"[seed] left alone, the seller's own since their first edit: {', '.join(claimed)}")
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the demo hospitals (spec 2026-09-06 D7).")
    parser.add_argument("--reset", action="store_true", help="delete every source='seed' row first")
    parser.add_argument("--production", action="store_true", help="required to run against ENVIRONMENT=production")
    parser.add_argument("--owner", metavar="EMAIL", help=f"assign the listings to this account (default {SEED_OWNER_EMAIL})")
    parser.add_argument("--no-owner", action="store_true", help="seed the listings unowned (seller_id NULL)")
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
    # A demo persona must never own a production row. On a --production run the default is not
    # applied AT ALL unless --owner names an address explicitly (D25).
    if args.no_owner:
        owner_email = None
    elif args.owner:
        owner_email = args.owner
    elif environment.lower() == "production":
        owner_email = None
        print("[seed] production: no default owner (pass --owner to assign one)")
    else:
        owner_email = SEED_OWNER_EMAIL
    try:
        count = seed(dsn, reset=args.reset, owner=owner_email)
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
