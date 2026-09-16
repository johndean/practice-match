"""The image-identifiability pipeline's two Celery entry points (spec 2026-09-09 C.5, E).

Registered by CALLING `celery_app.task(...)` rather than by decorating, exactly as
`app/mail/tasks.py` and `app/tasks/census.py` do and for the same reason: celery ships no type
information, so a decorator on a typed function is untyped and mypy --strict refuses it, and a
suppression is not the fix. The functions stay ordinary, fully typed and directly callable -- which
is what the tests call.

NEITHER FUNCTION RAISES FOR ANY FAILURE THIS PIPELINE CAN PRODUCE. Every one of them is a state
write plus a returned summary, the `_NotReady`/`_refuse` shape census established
(`app/tasks/census.py`): a database that will not connect, an object that is not there, a bucket
that answers an error, an engine that will not import, an engine that raises on this photograph, a
detection whose geometry is not measurable, a vision refusal, an encode that will not fit the
ladder. A task that raised would leave a traceback where an operator needs a state.

Two things are deliberately NOT swallowed, and neither is a failure this pipeline produces. An
exception outside that set escapes: `acks_late` acks a failed task, so the message is not
redelivered for ever, the row is left in `PROCESSING`, and `media.sweep`'s rule (2) recovers it
within six minutes -- a recorded, bounded outcome, and better than silently converting an unknown
error into "done". And `store.get`/`store.put` failures are converted at the two helpers below
rather than at the entry point, so the state written names the STAGE that failed.

Retry is not `Task.retry()` (which raises and needs a bound task) but a fresh `apply_async` with a
countdown from the ladder, after the failure has been recorded. The ladder is `record.BACKOFF`
`(30, 120, 600)` and the bound is `record.MAX_ATTEMPTS = 3`, so the rungs actually spent are 30 s
then 2 min; the third failure exhausts to `REVIEW_REQUIRED` instead of re-enqueueing, and the
600-second rung is headroom for a raised bound (`tests/tasks/test_media.py` pins that).

The api never imports this module -- it publishes `media.process_photo` by name -- so the OCR,
barcode and vision engines are importable in the worker process alone. The one exception is the
Playwright launcher's eager branch in `record.enqueue_processing`, which no deployed service can
reach (`Settings` refuses the setting outside `ENVIRONMENT=test`) and
`tests/api/test_import_surface.py` pins at run time.
"""
from __future__ import annotations

import io
import logging
from typing import Any
from uuid import UUID

import psycopg2
import psycopg2.extensions
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, ImageOps, UnidentifiedImageError

from app.cache import drop_list_cache_quietly
from app.config import settings
from app.db import sync_dsn
from app.media import redact
from app.media.encode import MAX_IMAGE_PIXELS
from app.privacy import PROCESSING_VERSION, aggregate, barcodes, identity, ocr, record, redacted_key, vision
from app.storage import ObjectStore
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)

# `app/media/encode.py` sets the same bound at its own import and this module imports it, so the
# assignment below is already true -- restated where this module OPENS an image so the bound is
# visible beside the `DecompressionBombError` arms that depend on it (a header that lies about its
# dimensions is refused at `Image.open`, before a pixel is decoded).
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

#: The listing facts the matcher and the prompt read, at run time and never from the privacy row.
#: The row cannot exist without its listing (`listing_asset_privacy.listing_id REFERENCES
#: listing(id) ON DELETE CASCADE`), which is why this SELECT has no "no such listing" arm.
_FACTS = """
SELECT l.name, l.street, l.city, l.state, l.zip, l.phone, l.slug, l.facility, l.services, l.hours,
       l.identifiable_content_visibility, a.email
  FROM listing l LEFT JOIN account a ON a.id = l.seller_id
 WHERE l.id = %s
"""


def _conn() -> psycopg2.extensions.connection:
    connection = psycopg2.connect(sync_dsn())
    connection.autocommit = True
    return connection


def _fetch(store: ObjectStore, key: str) -> bytes | None:
    """One object, or None for a missing key AND for a bucket that answered an error.

    `ObjectStore.get` returns None only for a 404 and RE-RAISES every other `ClientError`, so an
    outage would otherwise leave this module -- whose contract is that it does not raise --
    propagating a boto exception out of a Celery task. The caller's answer is the same either way
    and it is fail-closed: no derivative, a recorded reason, a retry. This is
    `app/api/listings.py::_asset_bytes`' own rule, in the worker."""
    try:
        return store.get(key)
    except (BotoCoreError, ClientError) as exc:
        log.error("[media] object read failed: %s", type(exc).__name__)
        return None


def _store_object(store: ObjectStore, key: str, body: bytes) -> bool:
    """The derivative, put; False when the bucket refused it. `ObjectStore.put` catches nothing."""
    try:
        store.put(key, body, "image/webp")
        return True
    except (BotoCoreError, ClientError) as exc:
        log.error("[media] object write failed: %s", type(exc).__name__)
        return False


def _facts(conn: Any, listing_id: UUID) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(_FACTS, (listing_id,))
        columns = [d[0] for d in cur.description]
        return dict(zip(columns, cur.fetchone(), strict=True))


def _summary(asset_id: str, result: str, **extra: Any) -> dict[str, object]:
    return {"asset": asset_id, "result": result, **extra}


def _original_symbols(original: bytes, size: tuple[int, int]) -> list[barcodes.Symbol]:
    """Every 2D symbol in the ORIGINAL, in DISPLAY coordinates.

    The original is read once, for symbols only: a symbol the display encode softened must still be
    found (spec C.5 2b). Its quads are in the original's own pixel space, and `encode_webp` reaches
    display by applying EXIF orientation and then bounding the long edge to 1600 px (1100 px on the
    fallback rung) -- so a quad carried across unscaled would put the fill at up to 2.5x the wrong
    place on a phone photograph, covering nothing and hiding part of the practice instead.

    Orientation is applied here for the same reason: `ImageOps.exif_transpose` is what display was
    built through, so a portrait photograph's original is 90 degrees off display until it is
    applied, and no scale factor can correct a rotation. After it, the two differ by a uniform
    scale per axis and the map is exact -- `_within` rounds each dimension independently, so the
    two factors are taken independently rather than assumed equal."""
    with Image.open(io.BytesIO(original)) as source:
        upright = ImageOps.exif_transpose(source)
        found = list(barcodes.read_symbols(upright.convert("RGB")))
        sx, sy = size[0] / upright.width, size[1] / upright.height
    return [barcodes.Symbol(s.fmt, s.payload_kind, [(x * sx, y * sy) for x, y in s.quad]) for s in found]


def _scan(conn: Any, row: record.PrivacyRow, store: ObjectStore) -> tuple[dict[str, Any], str | None]:
    """Spec C.5 steps 1-5. `(scan, failure_code)` -- exactly one of the two is meaningful."""
    display = _fetch(store, row.display_storage_key or "")
    if display is None:
        return {}, "DISPLAY_MISSING"
    try:
        image = Image.open(io.BytesIO(display)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return {}, "UNDECODABLE"
    try:
        lines = ocr.read_text(image)
    except ocr.OcrUnavailable:
        return {}, "OCR_UNAVAILABLE"
    except ocr.OcrError:
        return {}, "OCR_ERROR"
    try:
        symbols = list(barcodes.read_symbols(image))
        original = _fetch(store, row.original_storage_key)
        if original is not None:
            symbols += _original_symbols(original, image.size)
    except barcodes.BarcodeUnavailable:
        return {}, "BARCODE_UNAVAILABLE"
    except (barcodes.BarcodeError, UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombError):
        return {}, "BARCODE_ERROR"

    facts = _facts(conn, row.listing_id)
    found = identity.matches([line.text for line in lines], facts, facts["email"])
    seen = vision.analyse(display, name=facts["name"], city=facts["city"], state=facts["state"])
    if seen["status"] == "failed":
        return {}, str(seen["code"])
    try:
        detected, regions = aggregate.regions_for(lines=lines, matches=found, symbols=symbols,
                                                  vision=seen, size=image.size)
    except aggregate.UnmeasurableRegion:
        # P7 §5: one non-finite ordinate either shrinks the region silently, raises out of
        # `round()` with no reason code, or merges with every region in the photograph. The
        # aggregator refuses it at the one door; this is the reason code that refusal carries, and
        # the message is NOT used -- it names the source, and `last_error` holds a code.
        return {}, "AGGREGATE_UNMEASURABLE"
    return {
        "display": display,
        "visibility": facts["identifiable_content_visibility"],
        "ocr": {"engine": ocr.ENGINE, "size": list(image.size),
                "lines": [{"text": line.text, "confidence": line.confidence,
                           "quad": [[x, y] for x, y in line.quad]} for line in lines],
                "barcodes": [{"format": s.fmt, "payload_kind": s.payload_kind,
                              "quad": [[x, y] for x, y in s.quad]} for s in symbols]},
        "identity_matches": [{"field": m.field, "line": m.line, "method": m.method, "score": m.score}
                             for m in found],
        "vision": seen,
        "detected_regions": detected,
        "redaction_regions": regions,
    }, None


def _retry_or_exhaust(conn: Any, row: record.PrivacyRow, *, state: str, code: str,
                      version: int) -> dict[str, object]:
    """The ladder, for a CLAIMED row.

    The count that decides is the claimed row's own: `record.claim` spent this attempt in its own
    statement, so `row.attempts` is already 1, 2 or 3 and no second counter exists.

    THE DECISION COMES BEFORE THE WRITE, and that ordering is load-bearing. Spec C.4's two
    `-> REVIEW_REQUIRED` rows come from PROCESSING and SCANNED -- `record.EXHAUST_SOURCES` holds
    exactly those -- so writing PROCESSING_FAILED first and exhausting afterwards would find no row
    to move, and the photograph would sit at its bound with no state saying so and no sweeper rule
    that could reach it (rule (3) is `attempts < MAX_ATTEMPTS`).

    A 0 from either writer means the row's state is no longer one the transition names, because
    another actor moved it between this run's claim and now -- the seller's "Try again" is the one
    that happens. Nothing was written, so nothing is re-enqueued: `BACKOFF[0 - 1]` would be the
    ten-minute rung the bound never reaches, scheduled for a photograph this run never touched."""
    if row.attempts >= record.MAX_ATTEMPTS:
        moved = record.exhaust(conn, row.asset_id, code=code)
        return _summary(str(row.asset_id), "review_required" if moved else "state_changed", error=code)
    if record.fail(conn, row.asset_id, state=state, code=code) == 0:
        log.warning("[media] %s left %s before its failure could be written", row.asset_id, state)
        return _summary(str(row.asset_id), "state_changed", error=code)
    delay = record.BACKOFF[row.attempts - 1]
    process_photo_task.apply_async(args=(str(row.asset_id), version), countdown=delay)
    return _summary(str(row.asset_id), state.lower(), error=code, retry_in=delay)


def _run(conn: Any, row: record.PrivacyRow, store: ObjectStore, version: int) -> dict[str, object]:
    """A claimed row, from PROCESSING to READY_FOR_REVIEW (spec C.5 steps 1-7).

    The three writers between the scan and readiness each carry their own state predicate, so a row
    another actor moved mid-run is simply not written -- the summary below would then say "ready"
    for a row that is elsewhere, which is a log line and not a state, and fails closed either way:
    nothing was written, so nothing became visible."""
    scan, failure = _scan(conn, row, store)
    if failure is not None:
        return _retry_or_exhaust(conn, row, state="PROCESSING_FAILED", code=failure, version=version)
    record.record_scan(conn, row.asset_id, ocr=scan["ocr"], identity_matches=scan["identity_matches"],
                       vision=scan["vision"], detected_regions=scan["detected_regions"])
    filled = redact.fill_regions(scan["display"], aggregate.fillable(scan["redaction_regions"]))
    if filled is None:
        return _retry_or_exhaust(conn, row, state="REDACTION_FAILED", code="ENCODE_TOO_LARGE",
                                 version=version)
    body, digest = filled
    key = redacted_key(row.listing_id, row.asset_id)
    if not _store_object(store, key, body):
        # The derivative exists but could not be written. REDACTION_FAILED and a retry: the row must
        # never claim a key whose object is not there (`lap_ready_has_derivative_ck` would let it,
        # because the CHECK sees the column and not the bucket).
        return _retry_or_exhaust(conn, row, state="REDACTION_FAILED", code="STORAGE_ERROR",
                                 version=version)
    record.record_derivative(conn, row.asset_id, key=key, sha256=digest,
                             regions=scan["redaction_regions"])
    record.mark_ready(conn, row.asset_id, visible=scan["visibility"] == "SHOW", version=PROCESSING_VERSION)
    drop_list_cache_quietly()
    return _summary(str(row.asset_id), "ready", regions=len(scan["redaction_regions"]))


def _rerun_failed(conn: Any, row: record.PrivacyRow, *, code: str, version: int) -> dict[str, object]:
    """An in-place re-run's failure: the attempt is counted and the row does NOT leave its state, so
    the derivative it already has goes on being served (D-IDP-16).

    `record.bump_attempt` returns the NEW count, or None when the row is no longer in one of the
    three ready states -- which is not 0, deliberately, because a caller reading 0 as "the first
    attempt" would index `BACKOFF[-1]`. At the bound `record.exhaust` DOES apply, the ready states
    being among `EXHAUST_SOURCES`: the row moves to REVIEW_REQUIRED with the confirmation reset, a
    fail-closed null slot on a published listing and never the original (directive 19)."""
    attempts = record.bump_attempt(conn, row.asset_id)
    if attempts is None:
        log.warning("[media] %s stopped being ready mid re-run; nothing written", row.asset_id)
        return _summary(str(row.asset_id), "rerun_abandoned", error=code)
    if attempts >= record.MAX_ATTEMPTS:
        moved = record.exhaust(conn, row.asset_id, code=code)
        return _summary(str(row.asset_id), "review_required" if moved else "state_changed", error=code)
    delay = record.BACKOFF[attempts - 1]
    process_photo_task.apply_async(args=(str(row.asset_id), version), countdown=delay)
    return _summary(str(row.asset_id), "rerun_failed", error=code, retry_in=delay)


def _rerun(conn: Any, row: record.PrivacyRow, store: ObjectStore, version: int) -> dict[str, object]:
    """The in-place re-run of a flagged READY row (D-IDP-16).

    The row does not leave its state, so `buyer_visible` and the CHECK that guards it are untouched
    and the OLD derivative goes on being served under its old hash until the one UPDATE at the end.

    The object is written BEFORE the row is advanced, so the bytes exist before anything names them.
    If `advance_in_place` then reports 0 -- the row stopped being ready under us -- the bucket holds
    a derivative the row does not describe; that is the honest cost of this ordering and it is
    fail-closed, because the only ways out of a ready state (`exhaust`, a delete) leave nothing
    buyer-visible to serve the mismatch to. The other ordering would leave a READY row naming a hash
    whose object was never written, which a buyer WOULD be served."""
    scan, failure = _scan(conn, row, store)
    if failure is not None:
        return _rerun_failed(conn, row, code=failure, version=version)
    regions = aggregate.union_auto(row.redaction_regions, scan["redaction_regions"],
                                   confirmed=row.seller_confirmed)
    filled = redact.fill_regions(scan["display"], aggregate.fillable(regions))
    if filled is None:
        return _rerun_failed(conn, row, code="ENCODE_TOO_LARGE", version=version)
    body, digest = filled
    changed = digest != row.redacted_sha256
    if changed and not _store_object(store, redacted_key(row.listing_id, row.asset_id), body):
        return _rerun_failed(conn, row, code="STORAGE_ERROR", version=version)
    record.record_scan_in_place(conn, row.asset_id, ocr=scan["ocr"],
                                identity_matches=scan["identity_matches"], vision=scan["vision"],
                                detected_regions=scan["detected_regions"])
    if record.advance_in_place(conn, row.asset_id, sha256=digest, version=PROCESSING_VERSION,
                               regions=regions) == 0:
        log.warning("[media] %s stopped being ready mid re-run; the flag stands", row.asset_id)
        return _summary(str(row.asset_id), "rerun_abandoned")
    if changed:
        drop_list_cache_quietly()
    return _summary(str(row.asset_id), "rerun", changed=changed)


def process_photo(asset_id: str, version: int) -> dict[str, object]:
    """One photograph, from UPLOADED (or a retry, or a flagged ready row) to its derivative."""
    try:
        conn = _conn()
    except psycopg2.Error as exc:
        # Before any row can be read there is nothing to write a state onto. The class name only --
        # a psycopg2 message can carry the DSN (A-C7 (7)'s rule, exit 3's own reason).
        log.error("[media] database unreachable: %s", type(exc).__name__)
        return _summary(asset_id, "database_unavailable")
    try:
        try:
            parsed = UUID(asset_id)
        except ValueError:
            return _summary(asset_id, "gone")
        row = record.read(conn, parsed)
        if row is None:
            return _summary(asset_id, "gone")
        store = ObjectStore.from_settings(settings)
        if store is None:
            # Not a per-photograph failure: the bucket is unconfigured for the whole worker. The
            # row is left where it is and the sweeper brings it back when the bucket returns.
            log.error("[media] object store not configured -- %s left in %s", asset_id, row.processing_status)
            return _summary(asset_id, "storage_unavailable")
        if row.processing_status in record.READY_STATES and row.reprocess_reason is not None:
            return _rerun(conn, row, store, version)
        claimed = record.claim(conn, parsed, version)
        if claimed is None:
            # The row as it is NOW, and not as the read above found it. A plain SELECT does not
            # wait on another transaction's `FOR UPDATE`, so the read above can be older than the
            # claim: in a real two-worker race it saw UPLOADED, the claim then BLOCKED on the
            # winner's transaction and matched nothing once that worker had made the row
            # PROCESSING -- and a summary built from the stale read called that "already_processed"
            # when it is the "in_progress" this distinction exists for. `or row` covers the row
            # having been deleted meanwhile: the last state this run actually observed is then the
            # only honest thing it can report.
            settled = record.read(conn, parsed) or row
            return _summary(asset_id, "in_progress" if settled.processing_status == "PROCESSING"
                            else "already_processed")
        return _run(conn, claimed, store, version)
    finally:
        conn.close()


def sweep() -> dict[str, object]:
    """Six rules, every five minutes. Nothing here decides anything about a photograph -- it only
    puts rows the pipeline lost back on the queue (spec C.5). Like `process_photo`, it answers a
    database it cannot reach with a summary rather than a traceback: beat will call it again in
    five minutes and nothing has been lost.

    One enqueue per SUBJECT and not per rule: a row two rules both name is published once."""
    try:
        conn = _conn()
    except psycopg2.Error as exc:
        log.error("[media] database unreachable: %s", type(exc).__name__)
        return {"enqueued": 0, "error": "database_unavailable"}
    try:
        found = record.sweep_candidates(conn)
        subjects = sorted({asset_id for group in found.values() for asset_id in group})
        for asset_id in subjects:
            process_photo_task.apply_async(args=(str(asset_id), PROCESSING_VERSION), countdown=0)
        return {"enqueued": len(subjects), **{name: len(group) for name, group in found.items()}}
    finally:
        conn.close()


# Registered by CALLING `celery_app.task(...)`; see the module docstring. `acks_late` acks on
# return, so a retry is always a fresh message; `reject_on_worker_lost` redelivers the message of a
# child killed mid-run, and the redelivered run finds the row PROCESSING and writes nothing.
process_photo_task = celery_app.task(name="media.process_photo", acks_late=True, reject_on_worker_lost=True,
                                     time_limit=300, soft_time_limit=240)(process_photo)
sweep_task = celery_app.task(name="media.sweep", acks_late=True, reject_on_worker_lost=True,
                             time_limit=300, soft_time_limit=240)(sweep)
