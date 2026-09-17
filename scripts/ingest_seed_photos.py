#!/usr/bin/env python3
"""Turn every SEEDED photograph into a real listing asset, so the privacy pipeline processes it.

    ENVIRONMENT=qa poetry run python scripts/ingest_seed_photos.py --all --dry-run
    ENVIRONMENT=qa poetry run python scripts/ingest_seed_photos.py --all

Run inside the API container (the seed corpus is in the image: `Dockerfile`'s `COPY seeds/`), with
the bucket configured, and with a worker consuming the `media` queue.

WHY THIS EXISTS. The image-identifiability feature RENDERS an identifiable photograph with its
identifying words covered; it does not hide it. Under `NOT_SHOW`,
`app/privacy/delivery.py::buyer_variant` serves the REDACTED derivative — and a seeded photograph
is a relative PATH in `listing.photos` with no `listing_asset` row, so it has no derivative and
that arm answers None. Migration 040 made `NOT_SHOW` the default for every listing, so the demo
hospitals' photographs went dark on the 0.1.27 deploy. That is the spec's own ruled state —
§C.10's overrule banner says the seeds "are hidden until then" — and this script is the "then".

IT CHANGES NO VISIBILITY, deliberately. `identifiable_content_visibility` is written by exactly
one path, the owner's step-7 PATCH, and once a seed photograph is a processed asset `NOT_SHOW`
renders it MASKED. Nothing here needs to flip a setting and nothing here does.

WHAT IT KEYS ON: the ENTRY IS A PATH, never `source = 'seed'` (spec §C.10, skeptic finding 8).
`app/api/seller_listings.py::claim_from_seed` flips `source` to `'seller'` on the first seller
write of any kind, so a demo hospital somebody has pressed Edit on is `source = 'seller'` while
its photographs are still paths — and those are exactly the photographs with no derivative. The
predicate below is migration 040's own, for the same reason 040 used it.

THE SAME PATH A SELLER'S UPLOAD TAKES, by calling that path's own code rather than copying it:
`app/media/encode.py::encode_webp` for the display derivative, `app/api/seller_listings.py`'s
`_sniffed_photo`, `_insert_asset` and `_put`, `app/privacy/__init__.py`'s `display_key` and
`original_key`, and `app/privacy/record.py`'s `insert` and `enqueue_processing`. The bytes are read
through `app/api/listings.py::photo_file`, which is what refuses a `photos` entry that escapes
`PHOTOS_ROOT`; this file re-implements none of those rules.

WHAT IT DOES NOT DO: the ONE `exists()` check the upload route makes before writing `original.*`
is not made here. That check is defence in depth against a seller replaying a request; an asset
uuid is minted per photograph inside this process, so no earlier run of anything can hold its key,
and 300-odd HEAD requests would buy nothing. A photograph whose transaction rolls back leaves its
objects behind with no row — the same single orphan the upload route documents, unreadable because
every read goes through a row.

POSITION IS THE DESIGN. `photos[i]` fills the design's photo slot `i` (amendments A12.1-A12.5,
A15), so the array is rewritten IN PLACE and never compacted: a path becomes an asset id at the
same index, a `null` slot stays `null`, and the array keeps its length. `listing.photo_captions`
is not touched at all — it stays index-for-index parallel and goes on being the buyer payload's
positional fallback (`app/api/listings.py::photo_captions`) — while the caption is ALSO carried
onto `listing_asset.caption`, because the seller's step-6 tile reads only that
(`photo_tiles`: an asset entry's name is `captions.get(entry)` with no positional fallback) and
because `PATCH /listings/{id}/photos/{n}` answers `409 STATE` for an entry that is no longer a
path — the caption's home moves with the photograph.

IDEMPOTENT BY CONSTRUCTION: a converted entry is an asset id, and an asset id is not a path, so a
second run finds nothing to do. Nothing is keyed on a name or a hash.

Exit codes: 0 done (including "nothing to do"), 2 refused before anything was written
(`--production` withheld, or no object store), 4 at least one photograph was refused, 5 `--listing`
names no listing carrying a seeded photograph. A database that cannot be reached raises, exactly as
`scripts/reprocess_photos.py` lets it.

The `app.*` imports are inside the functions for the reason `scripts/bootstrap_admin.py` records:
`python scripts/ingest_seed_photos.py` puts `scripts/` on `sys.path`, not the repository root."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SAY = "[ingest_seed_photos]"

#: Migration `040`'s own predicate, and the ruling of spec §C.10: a `photos` entry holding a "/" is
#: a seeded photograph with no asset row. Never `source = 'seed'` -- `claim_from_seed` has already
#: moved that column for every demo hospital a seller has edited.
_SEEDED = ("EXISTS (SELECT 1 FROM jsonb_array_elements_text(photos) AS e"
           " WHERE position('/' IN e) > 0)")
_SCAN = f"SELECT id FROM listing WHERE {_SEEDED} ORDER BY slug"
_SCAN_ONE = f"SELECT id FROM listing WHERE id = %s AND {_SEEDED}"
#: The row this script rewrites, locked for the length of its own transaction so a seller's upload
#: (which appends to the same array) cannot interleave with this read-modify-write.
_LOCKED = "SELECT slug, photos, photo_captions FROM listing WHERE id = %s FOR UPDATE"


class Unusable(Exception):
    """A seeded photograph this run could not turn into an asset. Its entry stays a path, so its
    siblings still convert and a later run tries it again."""

    def __init__(self, entry: str, because: str) -> None:
        super().__init__(f"{entry}: {because}")
        self.entry = entry


def declared_type(entry: str) -> str | None:
    """The Content-Type a seed file's own suffix declares, or None for a suffix this pipeline does
    not take. Inverted from `app/privacy/__init__.py::PHOTO_EXT` rather than retyped, so the two
    cannot disagree about which three types exist; `.jpeg` is `app/media/encode.py`'s own second
    spelling of the first of them."""
    from app.privacy import PHOTO_EXT

    suffixes = {ext: content_type for content_type, ext in PHOTO_EXT.items()}
    suffixes[".jpeg"] = "image/jpeg"
    return suffixes.get(Path(entry).suffix.lower())


def caption_for(entry: str, position: int, stored: list[str | None]) -> str | None:
    """What this photograph is, in the best words anybody has written for it.

    The listing's own `photo_captions[position]` first -- a seller who used the positional route
    wrote those, and they are the seller's own words -- then the committed inventory's caption
    (`app/api/seller_listings.py::seed_captions`, the same map the wizard's tile falls back to
    today). Blank becomes NULL, which is how `caption_asset` already treats blank and null: one
    intent, "nobody has described this" -- and it is decided BEFORE the fallback, not after it:
    a blank string is TRUTHY, so a seller who cleared the description would otherwise have swallowed
    the inventory's own caption and left the photograph nameless."""
    from app.api.seller_listings import seed_captions

    own = (stored[position - 1] or "") if position - 1 < len(stored) else ""
    return (own.strip() or seed_captions().get(entry) or "").strip() or None


def seeded_positions(photos: list[str | None]) -> list[int]:
    """The 1-based positions holding a seed PATH. A `null` slot and an entry that is already an
    asset id are both absent, which is the whole of this script's idempotency."""
    return [n for n, entry in enumerate(photos, start=1) if entry is not None and "/" in entry]


def ingest_photo(conn: Any, store: Any, listing_id: UUID, photos: list[str | None],
                 position: int, caption: str | None) -> UUID:
    """One seeded photograph, through the upload path's own code. Returns the new asset id.

    Every rule here belongs to somebody else: containment to `photo_file`, the magic-byte check to
    `_sniffed_photo`, normalisation to `encode_webp`, the row and its key to `_insert_asset`, the
    bucket write to `_put`, the privacy record to `record.insert`. This function decides only the
    ORDER, which is the upload route's: the row is written inside the open transaction and both
    objects are written before it commits, so a committed row can never point at an object that
    was never written (`_insert_asset`'s own docstring)."""
    from app.api.listings import photo_file
    from app.api.seller_listings import _insert_asset, _put, _sniffed_photo
    from app.media.encode import encode_webp
    from app.privacy import PROCESSING_VERSION, display_key, original_key
    from app.privacy import record as privacy_record

    entry = str(photos[position - 1])
    # CONTAINMENT FIRST, and it is `photo_file`'s own rule rather than a second copy of it: the
    # path comes from the database, so `["../../../etc/passwd"]` must be refused before anything
    # else is asked about it.
    path = photo_file(photos, position)
    if path is None:
        raise Unusable(entry, "no readable file under the seed photo root")
    content_type = declared_type(entry)
    if content_type is None:
        raise Unusable(entry, "not one of the three photograph types")
    data = path.read_bytes()
    ext = _sniffed_photo(data, content_type)
    if ext is None:
        raise Unusable(entry, "the bytes are not the photograph the suffix claims")
    encoded = encode_webp(data)
    if encoded is None:
        raise Unusable(entry, "could not be read as a photograph")
    webp, digest = encoded
    asset_id, key = _insert_asset(conn, listing_id, "photo", Path(entry).name, "image/webp",
                                  webp, digest, lambda a: display_key(listing_id, a))
    with conn.cursor() as cur:
        # `ingested_from_seed` (migration 043, Task SEED-CONFIRM): the ONE marker
        # `scripts/confirm_seed_photos.py` keys its scope on, set in the same statement that
        # already writes `caption` -- never derived from `storage_key` or from `source`.
        cur.execute("UPDATE listing_asset SET caption = %s, ingested_from_seed = true WHERE id = %s",
                    (caption, asset_id))
    source_key = original_key(listing_id, asset_id, ext)
    _put(store, source_key, data, content_type)
    _put(store, key, webp, "image/webp")
    privacy_record.insert(conn, asset_id=asset_id, listing_id=listing_id,
                          original_storage_key=source_key, version=PROCESSING_VERSION)
    return asset_id


def ingest_listing(conn: Any, store: Any, listing_id: UUID, *, dry_run: bool,
                   budget: int | None) -> tuple[list[UUID], int, int]:
    """One listing, in ONE transaction: (asset ids to enqueue, refused, photographs accounted for).

    The array is rewritten IN PLACE at the positions that converted -- a path becomes an asset id
    at the same index, a `null` slot stays `null`, the length never moves -- because `photos[i]`
    fills the design's photo slot `i` (A12.1-A12.5, A15) and `photo_captions` is parallel to it.
    `photo_captions` itself is never written: it goes on being the buyer payload's positional
    fallback, while the caption ALSO travels onto the asset row, which is the only name the
    seller's step-6 tile can read once the entry is an asset id."""
    from app.api.listings import photo_list

    with conn, conn.cursor() as cur:
        cur.execute(_LOCKED, (listing_id,))
        found = cur.fetchone()
        if found is None:
            # Deleted between the scan and this lock. Nothing to say and nothing to do.
            return [], 0, 0
        slug, photos, stored = str(found[0]), photo_list(found[1]), photo_list(found[2])
        positions = seeded_positions(photos)[:budget]
        if dry_run:
            print(f"{SAY} {slug}: would ingest {len(positions)} photograph(s)")
            for position in positions:
                entry = str(photos[position - 1])
                print(f"{SAY}   photo {position}  {entry}  "
                      f"{caption_for(entry, position, stored) or '(no description)'}")
            return [], 0, len(positions)
        started: list[UUID] = []
        refused = 0
        for position in positions:
            entry = str(photos[position - 1])
            try:
                asset_id = ingest_photo(conn, store, listing_id, photos, position,
                                        caption_for(entry, position, stored))
            except Unusable as exc:
                print(f"{SAY}   refused {exc}", file=sys.stderr)
                refused += 1
                continue
            photos[position - 1] = str(asset_id)
            started.append(asset_id)
        if started:
            cur.execute("UPDATE listing SET photos = %s::jsonb, updated_at = now() WHERE id = %s",
                        (json.dumps(photos), listing_id))
        print(f"{SAY} {slug}: ingested {len(started)} photograph(s), {refused} refused")
    return started, refused, len(positions)


def main(argv: Sequence[str] | None = None) -> int:
    from contextlib import closing

    from app.api.seller_listings import Refusal
    from app.config import settings
    from app.db import sync_conn
    from app.privacy import PROCESSING_VERSION
    from app.privacy import record as privacy_record
    from app.storage import ObjectStore

    parser = argparse.ArgumentParser(description="Ingest the seeded photographs as listing assets.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--listing", type=UUID, help="one listing, by id")
    group.add_argument("--all", action="store_true", help="every listing carrying a seed photograph")
    parser.add_argument("--dry-run", action="store_true",
                        help="name what would be created, per listing, and write nothing")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="stop after N photographs -- the staged-rollout lever")
    parser.add_argument("--production", action="store_true",
                        help="required to run against ENVIRONMENT=production")
    args = parser.parse_args(argv)

    # `scripts/seed_listings.py`'s own guard, for its reason and one more: this run writes objects
    # to a real bucket AND enqueues work that calls a paid vision API.
    if settings.environment.lower() == "production":
        if not args.production:
            print(f"{SAY} refusing to run against production without --production", file=sys.stderr)
            return 2
        # The same "say it out loud" shape `scripts/seed_listings.py` and `scripts/deploy.sh` use:
        # this machine speaks to more than one environment, and this run spends money in whichever
        # one it is pointed at.
        print(f"{SAY} running against PRODUCTION, as --production says")
    # Resolved for the DRY RUN as well, deliberately: a preview that cannot predict the real run's
    # refusal is a preview of the wrong run.
    store = ObjectStore.from_settings(settings)
    if store is None:
        print(f"{SAY} object storage is not configured (S3_BUCKET) -- nothing can be written",
              file=sys.stderr)
        return 2

    enqueue: list[UUID] = []
    refused = 0
    seen = 0
    with closing(sync_conn()) as conn:
        with conn.cursor() as cur:
            cur.execute(*((_SCAN_ONE, (args.listing,)) if args.listing is not None else (_SCAN,)))
            listings = [UUID(str(row[0])) for row in cur.fetchall()]
        if args.listing is not None and not listings:
            print(f"{SAY} {args.listing} is not a listing carrying a seeded photograph",
                  file=sys.stderr)
            return 5
        try:
            for listing_id in listings:
                budget = None if args.limit is None else args.limit - seen
                if budget == 0:
                    break
                started, failures, accounted = ingest_listing(
                    conn, store, listing_id, dry_run=args.dry_run, budget=budget)
                enqueue.extend(started)
                refused += failures
                seen += accounted
        except Refusal as exc:
            # A bucket outage mid-run. Everything already committed stays committed and is
            # enqueued below; the rest is left for the next run, whose entries are still paths.
            print(f"{SAY} object storage refused the write ({exc.code}) -- stopping", file=sys.stderr)
            refused += 1

    # AFTER every transaction has committed (the upload route's own rule, spec C.5 step 0): a task
    # published inside the transaction could be taken by a prefork child before the row exists.
    for asset_id in enqueue:
        privacy_record.enqueue_processing(asset_id, PROCESSING_VERSION)
    verb = "would ingest" if args.dry_run else "ingested"
    print(f"{SAY} {verb} {seen if args.dry_run else len(enqueue)} photograph(s)"
          f" across {len(listings)} listing(s)"
          + ("" if args.dry_run else f"; {refused} refused"))
    return 4 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
