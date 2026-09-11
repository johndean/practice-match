"""The privacy row: its writer, and the message that starts its pipeline.

Task P3 adds the state machine on top of this module -- the claim, the reset rule and one function
per transition. Everything here is what the UPLOAD needs and nothing more, so the api's import of
this module pulls in no engine, no Pillow and no model.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.tasks.celery_app import celery_app


def insert(conn: Any, *, asset_id: UUID, listing_id: UUID, original_storage_key: str, version: int) -> None:
    """The row, in the UPLOAD's own transaction (spec C.4's first transition).

    Written inside the transaction that inserts `listing_asset` and appends to `listing.photos`, so
    a committed asset can never exist without a privacy record -- which is the whole of directive
    2's "NO path through which an image can bypass privacy processing" at the database level."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing_asset_privacy (asset_id, listing_id, processing_version, original_storage_key)"
            " VALUES (%s,%s,%s,%s)",
            (asset_id, listing_id, version, original_storage_key),
        )


def enqueue_processing(asset_id: UUID, version: int) -> None:
    """Publishes `media.process_photo` BY NAME, AFTER the caller's transaction has committed.

    By name (`send_task`) rather than by importing the task object: in every deployed environment
    the api must never import `app.tasks.media`, whose transitive imports are the OCR, barcode and
    vision adapters. The queue is named explicitly rather than left to `task_routes` so the routing
    is readable at the call site and does not change if a route is ever edited.

    A failure to publish is NOT swallowed here -- the caller runs this after the commit and outside
    its own `except Refusal`, so a broker outage answers 500 while the row stays `UPLOADED` and
    `media.sweep`'s rule (1) enqueues it within two minutes (spec C.5).

    Task P8 adds one branch above this line, for the Playwright launcher alone (controller
    amendment A-IDP-2): `send_task` does NOT honour `task_always_eager`, so the eager execution
    model cannot be had by a setting on this call."""
    celery_app.send_task("media.process_photo", args=[str(asset_id), version], queue="media")
