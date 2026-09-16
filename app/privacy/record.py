"""The privacy row: its writer, the message that starts its pipeline, and the state machine.

One function per transition of spec 2026-09-09 C.4, and every one of them refuses from a state the
table does not name -- which is what makes directive 6's "no image may silently fall through the
state machine" a property of the code rather than a hope. Recorded as controller amendment A-IDP-1:
C.5's module list does not name a home for the transition table, and every later task needs one
place that owns the claim statement, the confirmation-reset rule and the CHECK-safe writes.

No engine, no Pillow and no boto import ever enters this module: the api imports it on the upload
path, and the worker imports it beside the engines, so it is the one file both sides share.

Every writer carries a state predicate and NONE of them raises: a transition the table does not
name matches no row, writes nothing and reports that it did (0, or None where 0 would read as a
count), which is what makes `media.process_photo`'s "never raises" (spec C.5) a property of these
statements rather than of the order its caller happens to try them in.

`bump_attempt` is guarded by `READY_STATES` and not by the plan's `CLAIMABLE_STATES` (controller
amendment A-IDP-8): `claim` counts the claimable states' attempt inside its own statement, so a
second counter there would spend the ladder twice as fast, and the in-place re-run this writer
exists for happens in the three ready states `claim` refuses by design. The same amendment, as
extended on the fix-round-1 re-review (N5), ratifies its dropping the plan's `*, code` parameter:
a failed in-place attempt writes NO `last_error`, because it is not yet an outcome anyone reads --
`exhaust` writes the code at the bound. P8 should not go looking for a parameter removed on
purpose.

The confirmation-reset rule ships as TWO constants, `RESET_COLUMNS` and `RESET_COLUMNS_EDITED`,
rather than the plan's single `RESET_COLUMNS` -- PostgreSQL refuses two assignments to the same
column in one UPDATE, so the plan's own `{RESET_COLUMNS}, seller_review_status = 'edited'` is not a
statement that runs -- and the controller ratified that split on the P3 review (fix round 1,
review Minor-2); P10's `apply_visibility_change` and P12's mask routes name the second one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.config import settings
from app.privacy import PROCESSING_VERSION
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

    THE EAGER BRANCH is the Playwright launcher's and nothing else's (controller amendment
    A-IDP-2, spec G). It exists because `send_task` IGNORES `task_always_eager` -- celery warns
    `AlwaysEagerIgnored` and publishes anyway (`celery/app/base.py`, 5.6.3) -- so the eager model
    cannot be had by a setting on the line below; `apply_async` is the call form that honours it.
    `settings.celery_task_always_eager` is refused at boot by `Settings` in every environment but
    `test`, so the import is unreachable on QA and in production, and
    `tests/api/test_import_surface.py` proves at RUN TIME that the api process holds no engine
    module after `create_app()`."""
    if settings.celery_task_always_eager:
        from app.tasks.media import process_photo_task  # a LAZY import; see the docstring

        process_photo_task.apply_async(args=(str(asset_id), version), queue="media")
        return
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
#: Sweeper rule (1): an UPLOADED row whose enqueue never arrived. Two minutes, so a row still
#: inside the api's own commit-then-publish window is never swept out from under it.
UNSTARTED_AFTER = "2 minutes"
#: Sweeper rule (3): the longest backoff (10 min) plus two -- past it a re-enqueue was lost, or a
#: mask route's regeneration failed and that route enqueues nothing itself.
RETRY_AFTER = "12 minutes"
MAX_ATTEMPTS = 3
#: Seconds before the first, second and third re-enqueue (spec C.5). Never `Task.retry()`. Only the
#: first `MAX_ATTEMPTS - 1` rungs are ever spent -- the third failure exhausts rather than
#: re-enqueueing -- so the ladder that RUNS today is 30 s then 2 min, and 600 is headroom for a
#: raised bound. Pinned by a test, so that no docstring or runbook can describe a rung that never
#: runs.
BACKOFF = (30, 120, 600)

#: Spec C.4 pairs each failure state with ONE source: `PROCESSING -> PROCESSING_FAILED` (a decode,
#: OCR or vision error) and `SCANNED -> REDACTION_FAILED` (the fill or the re-encode). `fail` routes
#: by the state it is ASKED to write rather than admitting the union, so a re-encode error cannot
#: move a PROCESSING row and a decode error cannot move a SCANNED one -- neither of which is a row
#: of the table. A state this map does not hold answers the empty tuple, which matches nothing.
FAIL_SOURCES: dict[str, tuple[str, ...]] = {
    "PROCESSING_FAILED": ("PROCESSING",),
    "REDACTION_FAILED": ("SCANNED",),
}
#: Spec C.4's two `-> REVIEW_REQUIRED` rows: the failure that spends the third attempt
#: (`PROCESSING | SCANNED`) and the third failed IN-PLACE re-run (the three ready states).
EXHAUST_SOURCES = ("PROCESSING", "SCANNED", *READY_STATES)


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

#: `PrivacyRow`'s sixteen fields in the dataclass's own order, as SQL. ONE list, read by the SELECT
#: below and by `claim`'s own `RETURNING`, so the compare-and-set and the read can never answer
#: with different shapes.
_COLUMNS = """p.asset_id, p.listing_id, p.processing_status, p.processing_version, p.attempts,
       p.original_storage_key, p.redacted_storage_key, p.redacted_sha256, p.confirmed_sha256,
       p.seller_confirmed, p.buyer_visible, p.redaction_regions, p.reprocess_reason,
       p.final_privacy_state,
       a.storage_key AS display_storage_key, a.sha256 AS display_sha256"""

_READ = f"""
SELECT {_COLUMNS}
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
    nothing at all (a stale enqueue).

    ONE statement, and the row it answers with is the row IT wrote. `app/db.py`'s `sync_conn()` is
    autocommit, so an UPDATE followed by a separate `read()` commits between the two and hands the
    caller a second snapshot -- one another connection may already have moved on (review Minor-4).
    The `FROM listing_asset` join is what lets `RETURNING` carry the display key and hash
    `PrivacyRow` joins off that table, so the whole record comes back from the claiming statement
    itself."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE listing_asset_privacy p SET processing_status = 'PROCESSING',"
            f" attempts = attempts + 1, last_error = NULL, {RESET_COLUMNS}, updated_at = now()"
            f" FROM listing_asset a"
            f" WHERE a.id = p.asset_id AND p.asset_id = %s AND p.processing_version <= %s"
            f"   AND (p.processing_status = ANY(%s)"
            f"        OR (p.processing_status = 'PROCESSING'"
            f"            AND p.updated_at < now() - interval '{LOST_AFTER}'))"
            f" RETURNING {_COLUMNS}",
            (asset_id, version, list(CLAIMABLE_STATES)),
        )
        found = cur.fetchone()
    return None if found is None else _built(found)


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


def record_scan_in_place(conn: Any, asset_id: UUID, *, ocr: dict[str, Any],
                         identity_matches: list[dict[str, Any]], vision: dict[str, Any],
                         detected_regions: list[dict[str, Any]]) -> None:
    """`record_scan` WITHOUT the state change -- the in-place re-run's scan columns, written while
    the row stays in the ready state it is being re-run in (D-IDP-16).

    Guarded by the three READY states, and that guard is the whole difference from its sibling: an
    in-place re-run happens in a ready state and nowhere else, so a row that stopped being ready
    between this run's read and this write is one this statement must not touch. It writes no
    `processing_status`, so there is no transition to refuse -- only a scan to decline to record
    for a photograph the pipeline no longer owns. `advance_in_place`, which runs immediately after
    it, carries the same predicate and REPORTS the refusal (its rowcount); this one does not need
    to, because the two are written together and the caller branches on the one that matters."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET ocr = %s::jsonb, identity_matches = %s::jsonb,"
            " vision = %s::jsonb, detected_regions = %s::jsonb, updated_at = now()"
            " WHERE asset_id = %s AND processing_status = ANY(%s)",
            (json.dumps(ocr), json.dumps(identity_matches), json.dumps(vision),
             json.dumps(detected_regions), asset_id, list(READY_STATES)),
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
    text. Returns the attempts spent -- which is what decides between a re-enqueue and `exhaust` --
    or 0 when the row's state is not the one spec C.4 pairs with this failure, in which case
    NOTHING was written.

    0 is unambiguous rather than overloaded: a row this function can legitimately move is
    PROCESSING or SCANNED, and both were reached through `claim`'s own `attempts = attempts + 1`,
    so a real row's count here is never 0.

    The predicate is the whole of the "never raises" contract (spec C.5). Without it,
    `fail(..., state="PROCESSING_FAILED")` on a confirmed row moved it out of its ready state
    WITHOUT the reset rule; the row was then a `buyer_visible` non-ready row, `lap_visible_ready_ck`
    refused the statement, and psycopg2 raised a CheckViolation from inside a task contracted never
    to raise. `bump_attempt` is the in-place re-run's counter, and it is not this."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET processing_status = %s, last_error = %s,"
            " updated_at = now() WHERE asset_id = %s AND processing_status = ANY(%s)"
            " RETURNING attempts",
            (state, code, asset_id, list(FAIL_SOURCES.get(state, ()))),
        )
        found = cur.fetchone()
    return 0 if found is None else int(found[0])


def exhaust(conn: Any, asset_id: UUID, *, code: str) -> int:
    """The failure that spends the third attempt: REVIEW_REQUIRED, the reset rule applied,
    `buyer_visible` false -- a fail-closed null slot, on a published listing too. Never the
    original (directive 19).

    Returns the number of rows moved: 0 when the state is not one of `EXHAUST_SOURCES`, in which
    case nothing was written. It fails closed either way -- its own statement applies the reset
    rule, so every state it admits lands unconfirmed and invisible -- but a state spec C.4 does not
    name is still a transition this module does not perform (review Minor-1)."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE listing_asset_privacy SET processing_status = 'REVIEW_REQUIRED',"
            f" last_error = %s, {RESET_COLUMNS}, updated_at = now()"
            f" WHERE asset_id = %s AND processing_status = ANY(%s)",
            (code, asset_id, list(EXHAUST_SOURCES)),
        )
        return int(cur.rowcount)


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


def flag_stale_version(conn: Any, *, reason: str) -> list[UUID]:
    """`flag_stale` for every ready row BELOW the current processing version, whatever listing it
    belongs to. Returns the rows to enqueue after the commit.

    Two callers, one statement: the sweeper's rule (5) marks them `VERSION`, and
    `scripts/reprocess_photos.py --all-stale` marks the same set `OPERATOR` when a human asks for
    the re-run rather than waiting five minutes for beat. The reason is the only thing that differs
    between them, so it is the only parameter -- a second copy of this UPDATE in the script would
    be a second production writer of the privacy row, which
    `tests/test_docs.py::test_every_writer_of_the_privacy_row_is_declared_and_only_one_is_production`
    refuses by design.

    `reprocess_reason IS NULL` is what makes it idempotent: a row already flagged is not re-stamped,
    so five minutes of sweeps do not enqueue five re-runs of one photograph."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET reprocess_reason = %s, reprocess_requested_at = now(),"
            " updated_at = now() WHERE processing_status = ANY(%s) AND reprocess_reason IS NULL"
            "   AND processing_version < %s RETURNING asset_id",
            (reason, list(READY_STATES), PROCESSING_VERSION),
        )
        return [UUID(str(r[0])) for r in cur.fetchall()]


def _sql_array(values: tuple[str, ...]) -> str:
    """A tuple of this module's own state names as a SQL array LITERAL, for the read-only sweeper
    predicates that are interpolated rather than parameterised. Nothing a caller supplies reaches
    it: every value comes from the constants above."""
    return "ARRAY[" + ",".join(f"'{value}'" for value in values) + "]"


#: The four sweeper rules that only ever LOOK: `(name, predicate, window)`. The two that write --
#: rule (2)'s lost child and rule (5)'s version bump -- are statements of their own below and in
#: `flag_stale_version`, because each is a transition and every transition in this codebase carries
#: its own state predicate in this module (spec C.5).
_SWEEP_RULES: tuple[tuple[str, str, str], ...] = (
    # (1) the api committed the row and its publish never arrived.
    ("unstarted", "processing_status = 'UPLOADED'", UNSTARTED_AFTER),
    # (3) a re-enqueue was lost, or a mask route's regeneration failed -- that route enqueues
    #     nothing itself. `attempts < MAX_ATTEMPTS`: REVIEW_REQUIRED is the seller's to leave.
    ("retry", (f"processing_status = ANY({_sql_array(('PROCESSING_FAILED', 'REDACTION_FAILED'))})"
               f" AND attempts < {MAX_ATTEMPTS}"), RETRY_AFTER),
    # (4) a row the sweeper itself (or a lost child) put back, that nothing picked up.
    ("reprocess", "processing_status = 'REPROCESS_REQUIRED'", LOST_AFTER),
    # (6) a flagged ready row whose in-place re-run never ran.
    ("flagged", f"processing_status = ANY({_sql_array(READY_STATES)}) AND reprocess_reason IS NOT NULL",
     LOST_AFTER),
)


def sweep_candidates(conn: Any) -> dict[str, list[UUID]]:
    """The six rules' subjects, keyed `unstarted`, `retry`, `reprocess`, `flagged`, `lost`,
    `version` (spec C.5). THE ONLY THING IN THIS PIPELINE THAT FINDS A ROW NOTHING ELSE WILL.

    Four of the six only look; two of them WRITE, and both writes are here rather than in
    `app/tasks/media.py` because a transition of the privacy row belongs to this module and to no
    other (`tests/test_docs.py`'s one-production-writer pin, which Task P8's own brief names).

      (2) A PROCESSING row older than `LOST_AFTER` is a child that died mid-run: it becomes
          REPROCESS_REQUIRED with `last_error = 'TASK_LOST'`, in ONE statement that both finds it
          and moves it, so two sweeps running at once cannot both claim to have recovered it. A
          STATE and not a flag -- the row has no derivative to go on serving.
      (5) A ready row below `PROCESSING_VERSION` is flagged VERSION and does NOT move: it goes on
          serving the derivative it has while the in-place re-run replaces it (D-IDP-16).

    The four SELECTs run FIRST, so neither write can widen the set the same pass then enqueues: a
    row rule (2) has just moved to REPROCESS_REQUIRED carries a fresh `updated_at` and is outside
    rule (4)'s window anyway, and a row rule (5) has just flagged is outside rule (6)'s. The order
    makes that true by construction rather than by that arithmetic.

    Every window is `updated_at`, which every writer in this module sets explicitly and
    `listing_asset_privacy_sweep_idx` (`processing_status, updated_at`) is the index for."""
    found: dict[str, list[UUID]] = {}
    with conn.cursor() as cur:
        for name, predicate, window in _SWEEP_RULES:
            cur.execute(f"SELECT asset_id FROM listing_asset_privacy"
                        f" WHERE {predicate} AND updated_at < now() - interval '{window}'")
            found[name] = [UUID(str(r[0])) for r in cur.fetchall()]
        cur.execute(
            f"UPDATE listing_asset_privacy SET processing_status = 'REPROCESS_REQUIRED',"
            f" last_error = 'TASK_LOST', updated_at = now()"
            f" WHERE processing_status = 'PROCESSING' AND updated_at < now() - interval '{LOST_AFTER}'"
            f" RETURNING asset_id")
        found["lost"] = [UUID(str(r[0])) for r in cur.fetchall()]
    found["version"] = flag_stale_version(conn, reason="VERSION")
    return found


def advance_in_place(conn: Any, asset_id: UUID, *, sha256: str, version: int,
                     regions: list[dict[str, Any]]) -> int:
    """The one derivative write that does not reset (spec C.5). The re-run's region set is the OLD
    set unioned with the new on a confirmed row, so the fresh derivative hides a superset of what
    the seller confirmed -- which is what makes advancing `confirmed_sha256` with `redacted_sha256`
    honest rather than a silent re-confirmation. The state, `buyer_visible` and
    `lap_visible_ready_ck` are untouched, so a version bump darkens no listing.

    **Guarded by the three READY states**, because the in-place re-run is a ready row's re-run and
    nothing else (D-IDP-16): unguarded it set a derivative hash and cleared the stale flag from ANY
    state, including `UPLOADED` and `REVIEW_REQUIRED`, where it wrote a `redacted_sha256` beside a
    NULL `redacted_storage_key` -- a shape `lap_ready_has_derivative_ck` does not constrain outside
    the ready states, so nothing in the database refused it. Returns the number of rows moved: 0
    when the state forbids it and nothing was written."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET redacted_sha256 = %s,"
            " confirmed_sha256 = CASE WHEN seller_confirmed THEN %s ELSE confirmed_sha256 END,"
            " redaction_regions = %s::jsonb, processing_version = %s, reprocessed_at = now(),"
            " reprocess_reason = NULL, reprocess_requested_at = NULL, attempts = 0,"
            " updated_at = now() WHERE asset_id = %s AND processing_status = ANY(%s)",
            (sha256, sha256, json.dumps(regions), version, asset_id, list(READY_STATES)),
        )
        return int(cur.rowcount)


def bump_attempt(conn: Any, asset_id: UUID) -> int | None:
    """The in-place re-run's FAILURE arm: "a failed in-place run counts an attempt and re-enqueues"
    (spec C.5). Returns the NEW count, or None when the row's state forbids it.

    Guarded by the three READY states, because that is where an in-place re-run happens -- the row
    never leaves its state (D-IDP-16) and `buyer_visible` is untouched, so counting a failure
    darkens no listing. `claim` deliberately refuses those three, so this is the only way a flagged
    ready row's attempt is counted; and it refuses everything `claim` DOES take, because the claim
    counts that attempt in its own statement and a second count would spend the ladder twice as
    fast.

    None and not 0: a caller that read a 0 as "the first attempt" would index `BACKOFF[-1]` -- the
    10-minute rung the bound never reaches -- for a row it never touched. The caller spends
    `BACKOFF[n - 1]` while `n < MAX_ATTEMPTS` and calls `exhaust` at `n == MAX_ATTEMPTS`; the chain
    that does that is P8's, not this module's, and `last_error` is written there, by `exhaust`,
    because a re-enqueued attempt is not yet an outcome anyone reads."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset_privacy SET attempts = attempts + 1, updated_at = now()"
            " WHERE asset_id = %s AND processing_status = ANY(%s) RETURNING attempts",
            (asset_id, list(READY_STATES)),
        )
        found = cur.fetchone()
    return None if found is None else int(found[0])


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
