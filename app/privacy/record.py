"""The privacy row: its writer, the message that starts its pipeline, and the state machine.

One function per transition of spec 2026-09-09 C.4, and every one of them refuses from a state the
table does not name -- which is what makes directive 6's "no image may silently fall through the
state machine" a property of the code rather than a hope. Recorded as controller amendment A-IDP-1:
C.5's module list does not name a home for the transition table, and every later task needs one
place that owns the claim statement, the confirmation-reset rule and the CHECK-safe writes.

No engine, no Pillow and no boto import ever enters this module: the api imports it on the upload
path, and the worker imports it beside the engines, so it is the one file both sides share.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
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


#: Spec C.4's three ready states. `buyer_visible` is never true outside them (lap_visible_ready_ck).
READY_STATES = ("READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")
#: Directive 6's four. Left only by the claim of a retry, a Try-again or a delete.
ERROR_STATES = ("PROCESSING_FAILED", "REDACTION_FAILED", "REVIEW_REQUIRED", "REPROCESS_REQUIRED")
#: What `media.process_photo` may take. REVIEW_REQUIRED is NOT here: its retries are spent and only
#: the seller's "Try again" moves it.
CLAIMABLE_STATES = ("UPLOADED", "PROCESSING_FAILED", "REDACTION_FAILED", "REPROCESS_REQUIRED")
#: The hard time limit (300 s) plus a minute -- past it a PROCESSING row is a lost child.
LOST_AFTER = "6 minutes"
MAX_ATTEMPTS = 3
#: Seconds before the first, second and third re-enqueue (spec C.5). Never `Task.retry()`. Only the
#: first `MAX_ATTEMPTS - 1` rungs are ever spent -- the third failure exhausts rather than
#: re-enqueueing -- so the ladder that RUNS today is 30 s then 2 min, and 600 is headroom for a
#: raised bound. Pinned by a test, so that no docstring or runbook can describe a rung that never
#: runs.
BACKOFF = (30, 120, 600)


def _reset_columns(review_status: str) -> str:
    """The confirmation-reset rule, as one fragment so every writer applies exactly the same one.
    "Every write that produces, or will produce, a derivative the seller has not seen" (spec C.4).

    `seller_review_status` is the rule's ONE variable, and it is a PARAMETER rather than an
    assignment appended after the fragment: PostgreSQL refuses two assignments to the same column
    in one UPDATE ("multiple assignments to same column"), so `{RESET_COLUMNS}, seller_review_status
    = 'edited'` is not a statement that runs. One body, two bindings, no writer free to invent a
    third set of columns."""
    return (
        "seller_confirmed = false, seller_confirmed_at = NULL, seller_confirmation_account_id = NULL,"
        " final_privacy_state = NULL, confirmed_sha256 = NULL,"
        f" seller_review_status = '{review_status}', buyer_visible = false"
    )


#: The rule as a fresh run applies it (the claim, the exhaustion): the seller has seen nothing of
#: what is coming, so the review goes back to the beginning.
RESET_COLUMNS = _reset_columns("pending")
#: The rule as the seller's OWN edit applies it -- "a manual mask is added or a mask removed ...
#: `seller_review_status := 'edited'`" (spec C.4). 'edited' is a fact about the photograph that no
#: later "Looks good" erases, which `confirm`'s CASE is the other half of.
RESET_COLUMNS_EDITED = _reset_columns("edited")

_READ = """
SELECT p.asset_id, p.listing_id, p.processing_status, p.processing_version, p.attempts,
       p.original_storage_key, p.redacted_storage_key, p.redacted_sha256, p.confirmed_sha256,
       p.seller_confirmed, p.buyer_visible, p.redaction_regions, p.reprocess_reason,
       p.final_privacy_state,
       a.storage_key AS display_storage_key, a.sha256 AS display_sha256
  FROM listing_asset_privacy p JOIN listing_asset a ON a.id = p.asset_id
"""


@dataclass(frozen=True)
class PrivacyRow:
    """One photograph's record, joined to the `listing_asset` row that holds the DISPLAY key and
    hash -- so `app/privacy/delivery.py::buyer_variant` can decide a request from one object and
    the resolver stays pure."""

    asset_id: UUID
    listing_id: UUID
    processing_status: str
    processing_version: int
    attempts: int
    original_storage_key: str
    redacted_storage_key: str | None
    redacted_sha256: str | None
    confirmed_sha256: str | None
    seller_confirmed: bool
    buyer_visible: bool
    redaction_regions: list[dict[str, Any]]
    reprocess_reason: str | None
    #: The listing's setting at the moment of confirmation. P10's SHOW -> NOT_SHOW flip compares it
    #: (`seller_confirmed AND final_privacy_state = 'NOT_SHOW'`); nothing else reads it.
    final_privacy_state: str | None
    display_storage_key: str | None
    display_sha256: str | None


def _built(values: Any) -> PrivacyRow:
    """`_READ`'s column order IS the dataclass's field order, which the read tests hold."""
    return PrivacyRow(*values)


def read(conn: Any, asset_id: UUID) -> PrivacyRow | None:
    with conn.cursor() as cur:
        cur.execute(f"{_READ} WHERE p.asset_id = %s", (asset_id,))
        found = cur.fetchone()
    return None if found is None else _built(found)


def rows_for(conn: Any, listing_id: UUID) -> list[PrivacyRow]:
    with conn.cursor() as cur:
        cur.execute(f"{_READ} WHERE p.listing_id = %s ORDER BY p.created_at, p.asset_id", (listing_id,))
        return [_built(r) for r in cur.fetchall()]


def claim(conn: Any, asset_id: UUID, version: int) -> PrivacyRow | None:
    """ONE conditional UPDATE, and the whole of this pipeline's idempotency (spec C.5).

    A run that claims nothing writes nothing and returns None -- which is what makes a duplicate
    message harmless, a redelivered task a no-op and a late retry unable to clobber a confirmation:
    a ready row is never claimed by this path. The reset rule is applied in the SAME statement, so
    a fresh run can never inherit a confirmation, and a version below the current one claims
    nothing at all (a stale enqueue)."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE listing_asset_privacy SET processing_status = 'PROCESSING',"
            f" attempts = attempts + 1, last_error = NULL, {RESET_COLUMNS}, updated_at = now()"
            f" WHERE asset_id = %s AND processing_version <= %s"
            f"   AND (processing_status = ANY(%s)"
            f"        OR (processing_status = 'PROCESSING' AND updated_at < now() - interval '{LOST_AFTER}'))"
            f" RETURNING asset_id",
            (asset_id, version, list(CLAIMABLE_STATES)),
        )
        if cur.fetchone() is None:
            return None
    return read(conn, asset_id)


def record_scan(conn: Any, asset_id: UUID, *, ocr: dict[str, Any], identity_matches: list[dict[str, Any]],
                vision: dict[str, Any], detected_regions: list[dict[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'SCANNED', ocr = %s::jsonb,"
            " identity_matches = %s::jsonb, vision = %s::jsonb, detected_regions = %s::jsonb,"
            " updated_at = now() WHERE asset_id = %s AND processing_status = 'PROCESSING'",
            (json.dumps(ocr), json.dumps(identity_matches), json.dumps(vision),
             json.dumps(detected_regions), asset_id),
        )


def record_derivative(conn: Any, asset_id: UUID, *, key: str, sha256: str,
                      regions: list[dict[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'REDACTION_GENERATED',"
            " redacted_storage_key = %s, redacted_sha256 = %s, redaction_regions = %s::jsonb,"
            " updated_at = now() WHERE asset_id = %s AND processing_status = 'SCANNED'",
            (key, sha256, json.dumps(regions), asset_id),
        )


def mark_ready(conn: Any, asset_id: UUID, *, visible: bool, version: int) -> None:
    """REDACTION_GENERATED -> READY_FOR_REVIEW, `detection_at` and `processing_version` stamped.
    Under SHOW the photograph becomes buyer-visible here without a confirmation; under NOT_SHOW only
    `confirm` does that.

    `processing_version = %s` is spec C.5 step 7's "processing_version stamped", and it is written
    HERE and not at the claim because the version a completed record should carry is the one the RUN
    used. A row created before a version bump and completed after it would otherwise stay below the
    constant, be flagged VERSION by the sweeper within five minutes, and be re-run in place for a
    scan it had just done."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'READY_FOR_REVIEW',"
            " detection_at = now(), processing_version = %s, buyer_visible = %s, updated_at = now()"
            " WHERE asset_id = %s AND processing_status = 'REDACTION_GENERATED'",
            (version, visible, asset_id),
        )


def fail(conn: Any, asset_id: UUID, *, state: str, code: str) -> int:
    """PROCESSING_FAILED or REDACTION_FAILED with a reason CODE, never bytes and never response
    text. Returns the attempts spent, which is what decides between a re-enqueue and `exhaust`."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = %s, last_error = %s,"
            " updated_at = now() WHERE asset_id = %s RETURNING attempts",
            (state, code, asset_id),
        )
        return int(cur.fetchone()[0])


def exhaust(conn: Any, asset_id: UUID, *, code: str) -> None:
    """The failure that spends the third attempt: REVIEW_REQUIRED, the reset rule applied,
    `buyer_visible` false -- a fail-closed null slot, on a published listing too. Never the
    original (directive 19)."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE listing_asset_privacy SET processing_status = 'REVIEW_REQUIRED',"
            f" last_error = %s, {RESET_COLUMNS}, updated_at = now() WHERE asset_id = %s",
            (code, asset_id),
        )


def confirm(conn: Any, asset_id: UUID, *, account_id: UUID, visibility: str, edited: bool) -> bool:
    """"Looks good". True when the row is (now) confirmed, False when its state forbids it.

    Idempotent from SELLER_CONFIRMED, refused from every other state -- 409 STATE at the route.
    `confirmed_sha256 := redacted_sha256` is what `lap_confirmed_ck` then holds, which makes
    "confirmed against its current derivative" a column comparison rather than an inference; the
    `redacted_sha256 IS NOT NULL` term is what stops that becoming a confirmation of NOTHING, since
    a CHECK passes on a NULL and `NULL = NULL` is NULL."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'SELLER_CONFIRMED',"
            " seller_confirmed = true, seller_confirmed_at = now(),"
            " seller_confirmation_account_id = %s, final_privacy_state = %s,"
            " confirmed_sha256 = redacted_sha256, buyer_visible = true,"
            " seller_review_status = CASE WHEN %s OR seller_review_status = 'edited'"
            "                             THEN 'edited' ELSE 'looks_good' END,"
            " updated_at = now()"
            " WHERE asset_id = %s AND processing_status IN ('READY_FOR_REVIEW','SELLER_CONFIRMED')"
            "   AND redacted_sha256 IS NOT NULL RETURNING asset_id",
            (account_id, visibility, edited, asset_id),
        )
        return cur.fetchone() is not None


def reset_confirmation(conn: Any, asset_id: UUID, *, regions: list[dict[str, Any]] | None = None) -> bool:
    """A mask added or removed, or the SHOW -> NOT_SHOW flip on a row not confirmed under NOT_SHOW:
    back to READY_FOR_REVIEW with the reset rule and `seller_review_status` 'edited'. True when a row
    moved.

    **Guarded by the three READY states**, which is the whole of its safety. Without the guard this
    is `WHERE asset_id = %s` and it PROMOTES: a REDACTION_FAILED or REVIEW_REQUIRED row that still
    carries a stale `redacted_storage_key` (which `lap_ready_has_derivative_ck` permits, since it
    only constrains the ready states downwards) would become READY_FOR_REVIEW, be confirmable, and
    end up `buyer_visible` over a derivative whose regeneration had failed. Spec C.1 step 3 says
    these transitions come "from SELLER_CONFIRMED/PUBLISHED"; a non-ready row belongs on the
    re-enqueue arm instead, and P10's `apply_visibility_change` reads this function's False as
    exactly that instruction.

    Under SHOW the row's visibility returns with readiness, which `mark_ready` does; here it goes
    false in every case, because between this write and the regeneration the derivative on the
    bucket is not the one the row describes."""
    with conn.cursor() as cur:
        if regions is None:
            cur.execute(f"UPDATE listing_asset_privacy SET processing_status = 'READY_FOR_REVIEW',"
                        f" {RESET_COLUMNS_EDITED}, updated_at = now()"
                        f" WHERE asset_id = %s AND processing_status = ANY(%s) RETURNING asset_id",
                        (asset_id, list(READY_STATES)))
        else:
            cur.execute(f"UPDATE listing_asset_privacy SET processing_status = 'READY_FOR_REVIEW',"
                        f" {RESET_COLUMNS_EDITED},"
                        f" redaction_regions = %s::jsonb, updated_at = now()"
                        f" WHERE asset_id = %s AND processing_status = ANY(%s) RETURNING asset_id",
                        (json.dumps(regions), asset_id, list(READY_STATES)))
        return cur.fetchone() is not None


def reset_for_retry(conn: Any, asset_id: UUID) -> bool:
    """"Try again", from the four error states only -- 409 STATE from anywhere else."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'UPLOADED', attempts = 0,"
            " last_error = NULL, updated_at = now()"
            " WHERE asset_id = %s AND processing_status = ANY(%s) RETURNING asset_id",
            (asset_id, list(ERROR_STATES)),
        )
        return cur.fetchone() is not None


def flag_stale(conn: Any, *, listing_id: UUID, reason: str) -> list[UUID]:
    """Staleness is a FLAG, never a state (D-IDP-16): the ready rows of this listing are marked and
    their CURRENT derivatives go on being served while the in-place re-run replaces them. Returns
    the rows to enqueue after the commit."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET reprocess_reason = %s, reprocess_requested_at = now(),"
            " updated_at = now() WHERE listing_id = %s AND processing_status = ANY(%s)"
            "   AND reprocess_reason IS NULL RETURNING asset_id",
            (reason, listing_id, list(READY_STATES)),
        )
        return [UUID(str(r[0])) for r in cur.fetchall()]


def advance_in_place(conn: Any, asset_id: UUID, *, sha256: str, version: int,
                     regions: list[dict[str, Any]]) -> None:
    """The one derivative write that does not reset (spec C.5). The re-run's region set is the OLD
    set unioned with the new on a confirmed row, so the fresh derivative hides a superset of what
    the seller confirmed -- which is what makes advancing `confirmed_sha256` with `redacted_sha256`
    honest rather than a silent re-confirmation. The state, `buyer_visible` and
    `lap_visible_ready_ck` are untouched, so a version bump darkens no listing."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET redacted_sha256 = %s,"
            " confirmed_sha256 = CASE WHEN seller_confirmed THEN %s ELSE confirmed_sha256 END,"
            " redaction_regions = %s::jsonb, processing_version = %s, reprocessed_at = now(),"
            " reprocess_reason = NULL, reprocess_requested_at = NULL, attempts = 0,"
            " updated_at = now() WHERE asset_id = %s",
            (sha256, sha256, json.dumps(regions), version, asset_id),
        )


def mark_published(conn: Any, listing_id: UUID) -> None:
    """Every gated photograph of a listing that has just reached `published`. PUBLISHED means
    "published at least once" and is not reverted by a pause, unpublish or withdrawal -- the
    listing's own status filter is what hides it (spec C.4)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = 'PUBLISHED', updated_at = now()"
            " WHERE listing_id = %s AND processing_status IN ('READY_FOR_REVIEW','SELLER_CONFIRMED')"
            "   AND buyer_visible",
            (listing_id,),
        )


def set_visibility(conn: Any, asset_id: UUID, *, visible: bool) -> None:
    """The NOT_SHOW -> SHOW flip's per-row arm (spec C.1 step 4): readiness alone decides."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET buyer_visible = %s, updated_at = now()"
            " WHERE asset_id = %s AND (NOT %s OR processing_status = ANY(%s))",
            (visible, asset_id, visible, list(READY_STATES)),
        )
