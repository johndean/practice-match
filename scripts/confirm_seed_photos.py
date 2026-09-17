#!/usr/bin/env python3
"""A demo-only OPERATOR bulk confirm for the seeded hospitals' ingested photographs.

    ENVIRONMENT=qa poetry run python scripts/confirm_seed_photos.py --all --dry-run
    ENVIRONMENT=qa poetry run python scripts/confirm_seed_photos.py --all

Run inside the API container. It writes no object storage and calls no vision engine -- it moves
`listing_asset_privacy` rows through `app/privacy/record.py::confirm`, the table's ONE production
writer, which is precisely the transition Task P12's own review dialog will call the day it exists
(`READY_FOR_REVIEW -> SELLER_CONFIRMED`, `buyer_visible := true`, idempotent from
`SELLER_CONFIRMED`). This script neither adds that transition nor duplicates it: `confirm` was
already built, by the state-machine task the image-identifiability sub-project's plan calls P3, and
nothing before this script has ever called it in production.

WHY THIS EXISTS (John's ruling, 2026-09-17). `scripts/ingest_seed_photos.py` moves the seeded
photographs onto the supported path, but under `NOT_SHOW` a photograph is buyer-visible only AFTER
its seller confirms it -- `app/privacy/record.py`'s own docstring: "Under SHOW the photograph
becomes buyer-visible here without a confirmation; under NOT_SHOW only" after the confirm. Building
the seller's real review dialog (Task P12) first, or showing the demo photographs unmasked, were
the other two options John was offered; he chose a demo-only bulk confirm instead. THAT IS A
DELIBERATE BYPASS of the feature's one safety mechanism, permitted ONLY for the seeded demo data --
so this file's whole engineering problem is making that scope impossible to exceed, not merely
unlikely to be exceeded.

THE SCOPE, enforced by TWO INDEPENDENT CONDITIONS, both required, both in the ONE query below:

  1. The LISTING is one of the 29 hospitals `seeds/hospitals.json` names -- a closed set read from
     that file, via `seed_slugs()`, never a heuristic and never a status or a role. A listing
     `claim_from_seed` has since flipped to `source = 'seller'` is untouched by this condition,
     exactly as it is untouched by `scripts/ingest_seed_photos.py` itself (spec C.10): the slug is
     what names a demo hospital, not the column a seller's own edit moves.
  2. The PHOTOGRAPH is one `scripts/ingest_seed_photos.py` created -- `listing_asset.ingested_from_seed`
     (migration 043), stamped in the SAME statement that script already uses to write `caption`.
     Never a storage-key pattern (a real upload and a seed-ingested one share one key layout, spec
     C.2) and never the listing's `source` (condition 1's own reason, one column over): a seed
     listing's seller-uploaded photograph fails this condition even though its listing passes (1).

Both conditions must hold for a row to be so much as SELECTED as a candidate; refusing rather than
touching a row that fails either is `_CANDIDATES`'s WHERE clause, not a branch this script's Python
ever has to remember to take.

IT NEVER TOUCHES `identifiable_content_visibility`. The listings stay `NOT_SHOW` -- that is the
whole point: a confirmed photograph under `NOT_SHOW` renders MASKED, never unmasked, which is what
`app/privacy/delivery.py::buyer_variant`'s NOT_SHOW arm serves once `processing_status` is
`SELLER_CONFIRMED` (or later) and `buyer_visible` is true. A listing whose visibility is not
`NOT_SHOW` is skipped outright (its photographs are already buyer-visible with no confirmation at
all, spec C.1 step 2, so there is nothing for this script to bypass).

WHO CONFIRMS. `seller_confirmation_account_id REFERENCES account(id)`, so a confirmation needs a
real owning account -- the listing's own `seller_id` (D25: the demo hospitals are seeded owned by
`seller@practice-match.test`), read live rather than assumed. A candidate listing with no owner
(`seller_id IS NULL`) is reported and left alone: inventing an account to attribute the confirmation
to would be a second, worse bypass, and is refused rather than built.

AUDITED, ALWAYS. `audit_log` is append-only (migration 014), and this bypasses a safety gate, so it
must never be invisible: one row per photograph actually confirmed, `actor=None` (this codebase's
own shape for a standalone script, `scripts/seed_persona.py` and `scripts/bootstrap_admin.py`), a
`reason` that names the script and this ruling by date, and the state transition in `before`/`after`
-- so a later reader of `audit_log` can tell this apart from a seller's own real "Looks good" click
without having to already know this script exists.

`--limit N` throttles WRITES only, the same "staged rollout lever" `scripts/ingest_seed_photos.py`
offers: a photograph already confirmed, not yet ready, or on an unowned listing costs nothing and is
reported in full regardless of the limit -- the budget is spent only on a photograph this run
actually confirms (or, under `--dry-run`, would).

NEITHER `take_off_market` NOR `mark_published` IS CALLED, deliberately. The eventual P12 route's
own `confirm` calls `take_off_market` "if published/paused" as A-SL15's belt-and-braces -- but every
door that reaches READY_FOR_REVIEW on a LIVE listing today (a fresh upload, a mask edit) has ALREADY
taken that listing off market itself, so that call is a no-op there by construction. The seeded
hospitals are the one door that is not: `scripts/seed_listings.py` INSERTs them `published` directly
(migration 042's gate has no INSERT arm) and neither it nor `scripts/ingest_seed_photos.py` nor the
worker's own pipeline ever calls `take_off_market`, so their photographs reach READY_FOR_REVIEW while
the listing STAYS published -- and John's ruling is that they stay that way: the demo hospitals must
go on being BROWSABLE, with their photographs rendering masked, not vanish from Browse the moment an
operator brings their photographs online. `buyer_variant`'s NOT_SHOW arm already accepts
`SELLER_CONFIRMED` exactly as it accepts `PUBLISHED` (`_NOT_SHOW_READY`), so a seed photograph this
script confirms is fully buyer-visible without ever reaching `PUBLISHED` -- which nothing calls
`mark_published` to do, because that transition belongs to the reviewer's own decide route and this
is not a publish decision.

Exit codes: 0 done (including "nothing to confirm"), 2 refused before anything was written
(`--production` withheld), 5 `--listing` names a listing outside the 29-hospital closed set. A
database that cannot be reached raises, exactly as `scripts/ingest_seed_photos.py` lets it.

The `app.*` imports are inside the functions for the reason `scripts/bootstrap_admin.py` records:
`python scripts/confirm_seed_photos.py` puts `scripts/` on `sys.path`, not the repository root."""
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

SAY = "[confirm_seed_photos]"

#: Named once, quoted verbatim into every audit row this script writes (Part 2's own requirement:
#: "naming the operator action and that it was John's 2026-09-17 demo-only ruling"). Not a generic
#: "confirm" string: a reader of `audit_log` must be able to tell this bypass apart from a seller's
#: real "Looks good" click (the eventual P12 route) on sight, with no other context.
RULING = ("scripts/confirm_seed_photos.py -- demo-only operator bulk confirm under John's "
          "2026-09-17 ruling; bypasses the seller's own review, permitted only for the seeded "
          "demo hospitals' ingested photographs")

#: The two states `buyer_variant`'s NOT_SHOW arm already treats as "buyer may see this" (P3's own
#: `record.READY_STATES` minus the not-yet-confirmed one); a row already in one of them has nothing
#: for this script to do.
_ALREADY_CONFIRMED = ("SELLER_CONFIRMED", "PUBLISHED")

#: Condition 2 alone, as the join clause every candidate row must satisfy; condition 1 (the closed
#: slug set) is bound at call time via `%s = ANY(...)`. `l.identifiable_content_visibility` and
#: `l.seller_id` travel with each row because both are read PER LISTING, never assumed.
_CANDIDATES = """
SELECT l.id, l.slug, l.seller_id, l.identifiable_content_visibility,
       a.id AS asset_id, a.name, a.caption, p.processing_status
  FROM listing l
  JOIN listing_asset a ON a.listing_id = l.id AND a.ingested_from_seed
  JOIN listing_asset_privacy p ON p.asset_id = a.id
 WHERE l.slug = ANY(%s)
"""
_CANDIDATES_ALL = f"{_CANDIDATES} ORDER BY l.slug, a.created_at"
_CANDIDATES_ONE = f"{_CANDIDATES} AND l.id = %s ORDER BY a.created_at"
#: `--listing` names something outside the 29-hospital set (condition 1 fails for the WHOLE
#: listing, not merely for one of its photographs) -- exit 5, `scripts/ingest_seed_photos.py`'s own
#: convention for the equivalent case.
_LISTING_IN_SEED_SET = "SELECT 1 FROM listing WHERE id = %s AND slug = ANY(%s)"


def seed_slugs() -> list[str]:
    """The 29 hospital slugs `seeds/hospitals.json` names -- condition 1's closed set, read from
    the committed file and never derived from a status, a role or any other proxy. `seed_listings.py`
    is the seeder that upserts these rows; this is the same file, read rather than parsed twice."""
    data = json.loads((ROOT / "seeds" / "hospitals.json").read_text())
    return [h["slug"] for h in data["hospitals"]]


def _describe(name: str, caption: str | None) -> str:
    return f"{name}  {caption or '(no description)'}"


def confirm_listing(conn: Any, listing_id: UUID, slug: str, seller_id: UUID | None, visibility: str,
                    rows: list[tuple[Any, ...]], *, dry_run: bool, budget: int | None
                    ) -> tuple[list[UUID], int, int]:
    """One listing's candidates, already fetched (`asset_id, name, caption, processing_status`).
    Returns (confirmed asset ids, photographs accounted for towards `--limit`, total candidates).

    Bucketed FIRST and acted on only in the fourth branch, so `already`/`not_ready`/`unowned` are
    always reported in full -- nothing is written for them, so nothing about `--limit` should hide
    them from an operator reading the summary line."""
    from app.api.seller_listings import PRIVACY_ACTION
    from app.auth import audit
    from app.privacy import record as privacy_record

    total = len(rows)
    if visibility != "NOT_SHOW":
        # Spec C.1 step 2: under SHOW a ready photograph is already buyer-visible with no
        # confirmation at all, so there is nothing here for this script to bypass.
        print(f"{SAY} {slug}: identifiable_content_visibility is {visibility}, not NOT_SHOW -- "
              f"{total} photograph(s) already visible, nothing to confirm")
        return [], 0, total
    already = not_ready = unowned = 0
    confirmed: list[UUID] = []
    accounted = 0
    for asset_id, name, caption, status in rows:
        if status in _ALREADY_CONFIRMED:
            already += 1
            continue
        if status != "READY_FOR_REVIEW":
            not_ready += 1
            continue
        if seller_id is None:
            unowned += 1
            continue
        if budget == 0:
            break
        accounted += 1
        if budget is not None:
            budget -= 1
        if dry_run:
            print(f"{SAY}   would confirm  {asset_id}  {_describe(name, caption)}")
            continue
        with conn:
            if privacy_record.confirm(conn, asset_id, account_id=seller_id, visibility=visibility,
                                      edited=False):
                audit.write(conn, actor=None, action=PRIVACY_ACTION, target_type="listing_asset",
                            target_id=asset_id, before={"processing_status": "READY_FOR_REVIEW"},
                            after={"processing_status": "SELLER_CONFIRMED"}, reason=RULING)
                confirmed.append(asset_id)
            # `confirm` returned False: another writer moved this row between the SELECT above and
            # this statement (a real seller's own confirm, or a mask edit resetting it). Nothing
            # was written, so nothing is claimed -- a later run sees whatever state it settled in.
    verb = "would confirm" if dry_run else "confirmed"
    print(f"{SAY} {slug}: {verb} {accounted} photograph(s) ({already} already confirmed, "
          f"{not_ready} not ready, {unowned} unowned, left alone)")
    return confirmed, accounted, total


def main(argv: Sequence[str] | None = None) -> int:
    from contextlib import closing

    from app.cache import drop_list_cache_quietly
    from app.config import settings
    from app.db import sync_conn

    parser = argparse.ArgumentParser(
        description="Demo-only operator bulk confirm for the seeded hospitals' ingested photographs.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--listing", type=UUID, help="one seeded listing, by id")
    group.add_argument("--all", action="store_true", help="every one of the 29 seeded hospitals")
    parser.add_argument("--dry-run", action="store_true",
                        help="name what would be confirmed, per listing, and write nothing")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="stop after N confirmations -- the staged-rollout lever")
    parser.add_argument("--production", action="store_true",
                        help="required to run against ENVIRONMENT=production")
    args = parser.parse_args(argv)

    # `scripts/ingest_seed_photos.py`'s own guard, for the same reason: this writes to the database
    # and to the append-only audit log, in whichever environment it is pointed at.
    if settings.environment.lower() == "production":
        if not args.production:
            print(f"{SAY} refusing to run against production without --production", file=sys.stderr)
            return 2
        print(f"{SAY} running against PRODUCTION, as --production says")

    slugs = seed_slugs()
    total_confirmed: list[UUID] = []
    total_would = 0
    seen = 0
    with closing(sync_conn()) as conn:
        with conn.cursor() as cur:
            if args.listing is not None:
                cur.execute(_LISTING_IN_SEED_SET, (args.listing, slugs))
                if cur.fetchone() is None:
                    print(f"{SAY} {args.listing} is not one of the seeded demo hospitals",
                          file=sys.stderr)
                    return 5
                cur.execute(_CANDIDATES_ONE, (slugs, args.listing))
            else:
                cur.execute(_CANDIDATES_ALL, (slugs,))
            found = cur.fetchall()
        by_listing: dict[tuple[UUID, str, UUID | None, str], list[tuple[Any, ...]]] = {}
        order: list[tuple[UUID, str, UUID | None, str]] = []
        for listing_id, slug, seller_id, visibility, asset_id, name, caption, status in found:
            key = (UUID(str(listing_id)), slug, UUID(str(seller_id)) if seller_id else None, visibility)
            if key not in by_listing:
                by_listing[key] = []
                order.append(key)
            by_listing[key].append((asset_id, name, caption, status))
        for listing_id, slug, seller_id, visibility in order:
            budget = None if args.limit is None else args.limit - seen
            if budget == 0:
                break
            confirmed, accounted, _total = confirm_listing(
                conn, listing_id, slug, seller_id, visibility, by_listing[(listing_id, slug, seller_id, visibility)],
                dry_run=args.dry_run, budget=budget)
            total_confirmed.extend(confirmed)
            if args.dry_run:
                total_would += accounted
            seen += accounted

    if total_confirmed:
        drop_list_cache_quietly()
    verb = "would confirm" if args.dry_run else "confirmed"
    count = total_would if args.dry_run else len(total_confirmed)
    print(f"{SAY} {verb} {count} photograph(s) across {len(order)} listing(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
