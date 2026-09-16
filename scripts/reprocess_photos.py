#!/usr/bin/env python3
"""Flag photographs for an in-place re-run, and enqueue them (spec 2026-09-09 C.5).

    ENVIRONMENT=qa poetry run python scripts/reprocess_photos.py --listing <uuid>
    ENVIRONMENT=qa poetry run python scripts/reprocess_photos.py --all-stale

Run inside the WORKER container: it publishes to the same broker the worker consumes. It marks
`reprocess_reason = 'OPERATOR'` and NOTHING else -- a marked ready row keeps its state and goes on
serving the derivative it has, so this is safe on a published listing (D-IDP-16). The re-run itself
is `media.process_photo`'s, and a failure of one never darkens the listing: the row leaves its
ready state only at the third failed attempt, and then to a null slot and never to the original
(directive 19).

`media.sweep` does the same thing on a five-minute cadence for a row below `PROCESSING_VERSION`
(rule 5). This script exists for the two cases the cadence does not cover: ONE listing an operator
wants re-run now, whatever its version, and the whole stale set without waiting for beat.

It writes the privacy row through `app/privacy/record.py` and never by hand -- `--listing` is
`record.flag_stale` and `--all-stale` is `record.flag_stale_version`, the same statement the
sweeper's rule (5) runs, with `reason` as its only parameter. That is the one-production-writer rule
`tests/test_docs.py::test_every_writer_of_the_privacy_row_is_declared_and_only_one_is_production`
enforces: every transition of that table carries a state predicate, and it carries it in one file.

The enqueue is BY NAME (`record.enqueue_processing` -> `celery_app.send_task`), so this process
never imports `app.tasks.media` and therefore never loads an OCR, barcode or vision engine to write
a flag.

The `app.*` imports are inside `main()` for the reason `scripts/bootstrap_admin.py` records:
`python scripts/reprocess_photos.py` puts `scripts/` on `sys.path`, not the repository root."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv: Sequence[str] | None = None) -> int:
    from contextlib import closing

    from app.db import sync_conn
    from app.privacy import PROCESSING_VERSION, record

    parser = argparse.ArgumentParser(description="Flag photographs for an in-place privacy re-run.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--listing", type=UUID, help="every ready photograph of one listing")
    group.add_argument("--all-stale", action="store_true",
                       help=f"every ready photograph below processing version {PROCESSING_VERSION}")
    args = parser.parse_args(argv)

    # `with conn` is a TRANSACTION and not a close (psycopg2's own contract), so the flags commit
    # before a single message is published -- a worker that picked one up before the commit would
    # read the row as unflagged and do nothing at all.
    with closing(sync_conn()) as conn, conn:
        flagged = (record.flag_stale(conn, listing_id=args.listing, reason="OPERATOR")
                   if args.listing is not None
                   else record.flag_stale_version(conn, reason="OPERATOR"))
    for asset_id in flagged:
        record.enqueue_processing(asset_id, PROCESSING_VERSION)
    # The count and nothing else: an operator running this against production does not need a list
    # of asset ids in a terminal, and `media.sweep` would have found the same rows anyway.
    print(f"[reprocess_photos] flagged and enqueued {len(flagged)} photograph(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
