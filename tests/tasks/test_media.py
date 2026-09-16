"""`media.process_photo` and `media.sweep` (spec 2026-09-09 C.5, E).

Directive 19: privacy processing failures fail CLOSED. Nothing in this module ever falls back to
the original, and nothing raises: a task that raised would leave the message unacked, the row
PROCESSING, and an operator with a traceback instead of a state -- which is exactly the shape
`app/tasks/census.py` already refuses.

Every case runs with the stub engines and a moto bucket. No model, no binary, no network.
"""
from __future__ import annotations

import io
import warnings
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg2
import pytest
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image

from app.privacy import PROCESSING_VERSION, display_key, original_key, record, redacted_key
from app.privacy.barcodes import Symbol
from app.privacy.ocr import Line
from app.tasks import media
from tests.privacy.conftest import make_listing, make_row


def _raises(exc: BaseException) -> Any:
    """A stand-in that raises whatever it was given, for any arguments. A lambda with a `throw`
    generator expression reads worse and hides which exception is being planted."""
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise exc
    return boom


@pytest.fixture(autouse=True)
def _engines(monkeypatch: pytest.MonkeyPatch, redis: Any) -> None:
    """The deterministic stub engines, no vision key, and a fake Redis.

    `redis` is asked for by name rather than left to the real client because the SUCCESS path ends
    in `app.cache.drop_list_cache_quietly()` -- the browse list cache is stale the moment a
    photograph becomes deliverable -- and a suite that reached a real Redis would be asserting
    against whatever else is on this machine's port."""
    for module in ("ocr", "barcodes"):
        monkeypatch.setattr(f"app.privacy.{module}.settings.privacy_engine_module", "tests.e2e.stub_engines")
        monkeypatch.setattr(f"app.privacy.{module}._LOADED", None)
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", None)


def _photo_bytes(w: int = 1200, h: int = 900) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (w, h), (240, 240, 240)).save(buffer, "WEBP", quality=80, method=0)
    return buffer.getvalue()


def _seeded(conn: Any, store: Any, **kwargs: Any) -> tuple[UUID, UUID]:
    asset_id, listing_id = make_row(conn, **kwargs)
    store.put(display_key(listing_id, asset_id), _photo_bytes(), "image/webp")
    store.put(original_key(listing_id, asset_id, ".jpg"), _photo_bytes(), "image/jpeg")
    return asset_id, listing_id


def _column(conn: Any, asset_id: UUID, column: str) -> Any:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {column} FROM listing_asset_privacy WHERE asset_id = %s", (asset_id,))
        return cur.fetchone()[0]


def _age(conn: Any, asset_ids: list[UUID], minutes: int) -> None:
    """Every sweeper window is opened by moving `updated_at` backwards, which is why every writer
    in `record.py` sets it explicitly."""
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET updated_at = %s WHERE asset_id = ANY(%s)",
                    (datetime.now(UTC) - timedelta(minutes=minutes), asset_ids))


# --------------------------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------------------------

def test_a_photograph_runs_all_the_way_to_ready_and_writes_its_derivative(conn: Any, store: Any) -> None:
    asset_id, listing_id = _seeded(conn, store)
    assert media.process_photo(str(asset_id), 1)["result"] == "ready"
    row = record.read(conn, asset_id)
    assert row is not None
    assert row.processing_status == "READY_FOR_REVIEW"
    assert row.redacted_storage_key == redacted_key(listing_id, asset_id)
    assert row.redacted_sha256 and store.get(row.redacted_storage_key) is not None
    assert row.buyer_visible is False                       # NOT_SHOW: only `confirm` makes it visible
    assert row.redaction_regions and row.redaction_regions[0]["source"] == "auto"
    assert _column(conn, asset_id, "processing_version") == PROCESSING_VERSION
    assert _column(conn, asset_id, "detection_at") is not None


def test_under_show_the_photograph_is_buyer_visible_the_moment_it_is_ready(conn: Any, store: Any) -> None:
    """Directive 8: "Selecting SHOW does NOT mean: skip scanning." The same pipeline runs, the
    derivative exists though it is not served, and switching to NOT_SHOW is then instant."""
    listing_id = make_listing(conn, "idp-show", visibility="SHOW")
    asset_id, _ = _seeded(conn, store, listing_id=listing_id)
    media.process_photo(str(asset_id), 1)
    row = record.read(conn, asset_id)
    assert row is not None
    assert row.buyer_visible is True and row.redacted_storage_key is not None


def test_no_key_is_not_a_failure(conn: Any, store: Any) -> None:
    """The distinction P6 draws, end to end: the pipeline completes and the record says so.

    `ANTHROPIC_API_KEY` is set on no service today, so this is the state QA and production are
    actually in -- a supported one, in which OCR, the regex classes and 2D symbols are the whole of
    the detection."""
    asset_id, _ = _seeded(conn, store)
    media.process_photo(str(asset_id), 1)
    assert _column(conn, asset_id, "vision ->> 'status'") == "unavailable"
    row = record.read(conn, asset_id)
    assert row is not None and row.processing_status == "READY_FOR_REVIEW"


def test_a_symbol_found_only_in_the_original_is_covered_where_it_is_on_the_DISPLAY(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The original is read once, for symbols only: a symbol the display encode softened must still
    be found (spec C.5 2b). Its coordinates are the ORIGINAL's, and `encode_webp` bounds the display
    to 1600 px on its long edge -- so a quad carried across unscaled would put the fill at up to
    2.5x the wrong place on a phone photograph, which is the whole point of the mapping this
    asserts. The original here is 2400 x 1800 and the display 1200 x 900, so the factor is exactly
    one half and the region's own polygon says where it landed."""
    asset_id, listing_id = _seeded(conn, store)
    store.put(original_key(listing_id, asset_id, ".jpg"), _photo_bytes(2400, 1800), "image/jpeg")
    monkeypatch.setattr("app.tasks.media.ocr.read_text", lambda image: [])

    def symbols(image: Image.Image) -> list[Symbol]:
        # Only the ORIGINAL carries the symbol; the display's own pass finds nothing.
        if image.size != (2400, 1800):
            return []
        return [Symbol("QRCode", "url", [(1000.0, 800.0), (1200.0, 800.0), (1200.0, 1000.0), (1000.0, 1000.0)])]

    monkeypatch.setattr("app.tasks.media.barcodes.read_symbols", symbols)
    assert media.process_photo(str(asset_id), 1)["result"] == "ready"
    detected = _column(conn, asset_id, "detected_regions")
    assert [r["source"] for r in detected] == ["barcode"]
    # Halved into display space, then expanded about its centroid by `aggregate.BARCODE_EXPAND`.
    assert detected[0]["polygon"] == [[500.0, 400.0], [600.0, 400.0], [600.0, 500.0], [500.0, 500.0]]
    row = record.read(conn, asset_id)
    assert row is not None
    xs = [p[0] for p in row.redaction_regions[0]["polygon"]]
    assert max(xs) < 700, f"the fill is nowhere near the symbol's own half of the display: {row.redaction_regions}"


def test_a_photograph_whose_original_is_gone_is_still_scanned_from_its_display(
    conn: Any, store: Any
) -> None:
    """The original is an EXTRA symbol pass, never a precondition. P2 records that a put which
    fails after `original.*` was written leaves an unreferenced object; the mirror case -- a row
    whose original is not on the bucket -- must not fail a photograph whose display is right there.
    `_fetch` answers None and the display's own pass is the whole scan."""
    asset_id, listing_id = _seeded(conn, store)
    store.delete(original_key(listing_id, asset_id, ".jpg"))
    assert media.process_photo(str(asset_id), 1)["result"] == "ready"
    row = record.read(conn, asset_id)
    assert row is not None and row.processing_status == "READY_FOR_REVIEW"


# --------------------------------------------------------------------------------------------
# The claim
# --------------------------------------------------------------------------------------------

def test_a_duplicate_message_writes_nothing(conn: Any, store: Any) -> None:
    asset_id, _ = _seeded(conn, store)
    media.process_photo(str(asset_id), 1)
    before = record.read(conn, asset_id)
    assert media.process_photo(str(asset_id), 1)["result"] == "already_processed"
    assert record.read(conn, asset_id) == before


def test_a_message_that_finds_a_run_in_progress_returns_and_writes_nothing(conn: Any, store: Any) -> None:
    """`reject_on_worker_lost` redelivers the message of a killed child. The redelivered run finds
    the row PROCESSING with a recent `updated_at`, and the sweeper -- not this run -- finishes it."""
    asset_id, _ = _seeded(conn, store, processing_status="PROCESSING", attempts=1)
    assert media.process_photo(str(asset_id), 1)["result"] == "in_progress"
    row = record.read(conn, asset_id)
    assert row is not None and row.processing_status == "PROCESSING"


def test_two_workers_racing_one_photograph_leave_exactly_one_run(conn: Any, store: Any,
                                                                 scratch_dsn: str) -> None:
    """THE CLAIM, as a race and not as a predicate. Two `process_photo` calls with their claiming
    statements interleaved: the holder takes the row with `SELECT ... FOR UPDATE`, the second call's
    claim blocks on that lock, and the first claims and commits underneath it. Exactly one run does
    the work -- the other writes nothing at all, which is what `attempts` proves: a second claim
    would have counted a second attempt on a row that only ever ran once."""
    import threading

    asset_id, _ = _seeded(conn, store)
    holder = psycopg2.connect(scratch_dsn)
    results: dict[str, Any] = {}
    thread = threading.Thread(target=lambda: results.update(second=media.process_photo(str(asset_id), 1)))
    try:
        with holder.cursor() as cur:
            cur.execute("SELECT attempts FROM listing_asset_privacy WHERE asset_id = %s FOR UPDATE", (asset_id,))
        thread.start()
        _wait_for_a_blocked_backend(conn)
        with holder.cursor() as cur:
            # The holder's own claim, in its OWN transaction, then committed under the blocked one.
            cur.execute("UPDATE listing_asset_privacy SET processing_status = 'PROCESSING',"
                        " attempts = attempts + 1, updated_at = now() WHERE asset_id = %s", (asset_id,))
        holder.commit()
    finally:
        holder.close()
        if thread.ident is not None:
            thread.join(timeout=30)
    assert not thread.is_alive(), "the racing run did not return within 30 s of the lock being released"
    assert results["second"]["result"] == "in_progress", results
    assert _column(conn, asset_id, "attempts") == 1, "the loser counted an attempt it never made"


def _wait_for_a_blocked_backend(conn: Any, timeout: float = 20.0) -> None:
    """Block until another backend on this database is waiting on a lock -- the interleaving this
    race needs, observed rather than slept for."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                        " AND datname = current_database()")
            if int(cur.fetchone()[0]) > 0:
                return
        time.sleep(0.05)
    pytest.fail("the racing run never reached the row lock; the race was not driven")


def test_a_missing_row_is_a_summary_and_never_an_exception(conn: Any, store: Any) -> None:
    assert media.process_photo("44444444-4444-4444-8444-444444444444", 1)["result"] == "gone"


def test_an_asset_id_that_is_not_a_uuid_is_a_summary(conn: Any) -> None:
    """A hand-published message, or one from a version of the api that spelled the argument
    differently. `UUID(...)` raising inside a Celery task would be a traceback per redelivery."""
    assert media.process_photo("not-a-uuid", 1)["result"] == "gone"


def test_a_stale_enqueue_below_the_current_version_does_nothing(conn: Any, store: Any) -> None:
    asset_id, _ = _seeded(conn, store, processing_version=3)
    assert media.process_photo(str(asset_id), 1)["result"] == "already_processed"


# --------------------------------------------------------------------------------------------
# The ladder
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("failure", "state", "code"), [
    ("undecodable", "PROCESSING_FAILED", "UNDECODABLE"),
    ("ocr", "PROCESSING_FAILED", "OCR_ERROR"),
    ("vision", "PROCESSING_FAILED", "VISION_REFUSED"),
    ("unmeasurable", "PROCESSING_FAILED", "AGGREGATE_UNMEASURABLE"),
    ("encode", "REDACTION_FAILED", "ENCODE_TOO_LARGE"),
])
def test_each_failure_class_writes_its_own_state_and_re_enqueues_with_the_ladder(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch, failure: str, state: str, code: str
) -> None:
    scheduled: list[dict[str, Any]] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown: scheduled.append({"args": args, "countdown": countdown}))
    asset_id, listing_id = _seeded(conn, store)
    if failure == "undecodable":
        store.put(display_key(listing_id, asset_id), b"not an image", "image/webp")
    elif failure == "ocr":
        monkeypatch.setattr("app.tasks.media.ocr.read_text", _raises(media.ocr.OcrError("OCR_ERROR")))
    elif failure == "vision":
        monkeypatch.setattr("app.tasks.media.vision.analyse",
                            lambda *a, **k: {"status": "failed", "code": "VISION_REFUSED"})
    elif failure == "unmeasurable":
        # A REAL non-finite quad through the real `aggregate.regions_for`, not a planted raise: the
        # line is a telephone number, so the regex class produces a hit and the OCR arm reaches
        # `_checked` with the NaN in it (P7 §5 -- without the refusal `_near` merges it with every
        # region in the photograph and `round(nan)` raises a ValueError nothing has a code for).
        monkeypatch.setattr("app.tasks.media.ocr.read_text", lambda image: [
            Line("(512) 555-0100", 0.9, [(float("nan"), 10.0), (200.0, 10.0), (200.0, 40.0), (10.0, 40.0)])])
    else:
        monkeypatch.setattr("app.tasks.media.redact.fill_regions", lambda display, polygons: None)

    for attempt, delay in enumerate(record.BACKOFF, start=1):
        media.process_photo(str(asset_id), 1)
        row = record.read(conn, asset_id)
        assert row is not None
        if attempt < record.MAX_ATTEMPTS:
            assert (row.processing_status, row.attempts) == (state, attempt)
            assert _column(conn, asset_id, "last_error") == code
            assert scheduled[-1]["countdown"] == delay
            assert scheduled[-1]["args"] == (str(asset_id), 1)
        else:
            # The third failure EXHAUSTS rather than re-enqueueing, which is why only the ladder's
            # first two rungs are ever spent -- `delay` on this pass is 600 and nothing scheduled it.
            assert row.processing_status == "REVIEW_REQUIRED" and len(scheduled) == record.MAX_ATTEMPTS - 1
            assert [s["countdown"] for s in scheduled] == list(record.BACKOFF[:record.MAX_ATTEMPTS - 1])
    final = record.read(conn, asset_id)
    assert final is not None
    assert final.buyer_visible is False and final.redacted_storage_key is None
    assert _column(conn, asset_id, "last_error") == code


def test_the_ladder_a_seller_actually_experiences_is_thirty_seconds_then_two_minutes(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The constant is `(30, 120, 600)` and the bound is three attempts, so the third rung is never
    reached. Stated as its own case rather than left implied by the loop above, because a runbook
    sentence that promises ten minutes would be describing a delay no seller can ever be served."""
    scheduled: list[int] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown: scheduled.append(countdown))
    monkeypatch.setattr("app.tasks.media.redact.fill_regions", lambda display, polygons: None)
    asset_id, _ = _seeded(conn, store)
    for _ in range(record.MAX_ATTEMPTS + 2):
        media.process_photo(str(asset_id), 1)
    assert scheduled == [30, 120]
    assert record.BACKOFF[record.MAX_ATTEMPTS - 1] == 600, "the unreachable rung is still the constant's last"


@pytest.mark.parametrize(("broken", "code", "state"), [
    ("display_object", "DISPLAY_MISSING", "PROCESSING_FAILED"),
    ("display_read", "DISPLAY_MISSING", "PROCESSING_FAILED"),
    ("ocr_import", "OCR_UNAVAILABLE", "PROCESSING_FAILED"),
    ("barcode_import", "BARCODE_UNAVAILABLE", "PROCESSING_FAILED"),
    ("barcode_run", "BARCODE_ERROR", "PROCESSING_FAILED"),
    ("original_unreadable", "BARCODE_ERROR", "PROCESSING_FAILED"),
    ("derivative_write", "STORAGE_ERROR", "REDACTION_FAILED"),
])
def test_every_remaining_failure_class_records_its_own_reason_code(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch, broken: str, code: str, state: str
) -> None:
    """The rest of directive 19's fail-closed surface, one case per branch, because
    `--cov-branch --cov-fail-under=100` counts them and because each is a DIFFERENT sentence in the
    runbook. Two of them exist only because `ObjectStore` re-raises: `get` passes on every
    `ClientError` that is not a 404, and `put` catches nothing at all."""
    monkeypatch.setattr(media.process_photo_task, "apply_async", lambda args, countdown: None)
    asset_id, listing_id = _seeded(conn, store)
    if broken == "display_object":
        store.delete(display_key(listing_id, asset_id))
    elif broken == "display_read":
        monkeypatch.setattr("app.tasks.media.ObjectStore.get", _raises(ClientError(
            {"Error": {"Code": "InternalError"}}, "GetObject")))
    elif broken == "ocr_import":
        monkeypatch.setattr("app.tasks.media.ocr.read_text",
                            _raises(media.ocr.OcrUnavailable("OCR_UNAVAILABLE")))
    elif broken == "barcode_import":
        monkeypatch.setattr("app.tasks.media.barcodes.read_symbols",
                            _raises(media.barcodes.BarcodeUnavailable("BARCODE_UNAVAILABLE")))
    elif broken == "barcode_run":
        monkeypatch.setattr("app.tasks.media.barcodes.read_symbols",
                            _raises(media.barcodes.BarcodeError("BARCODE_ERROR")))
    elif broken == "original_unreadable":
        store.put(original_key(listing_id, asset_id, ".jpg"), b"not an image", "image/jpeg")
    else:
        monkeypatch.setattr("app.tasks.media.ObjectStore.put", _raises(BotoCoreError()))
    media.process_photo(str(asset_id), 1)
    row = record.read(conn, asset_id)
    assert row is not None
    assert _column(conn, asset_id, "last_error") == code
    assert row.processing_status == state
    assert row.buyer_visible is False


def test_a_derivative_the_bucket_refused_is_never_claimed_by_the_row(conn: Any, store: Any,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """The row must never name a key whose object is not there: `lap_ready_has_derivative_ck` sees
    the COLUMN and not the bucket, so it would let a ready row point at nothing."""
    monkeypatch.setattr(media.process_photo_task, "apply_async", lambda args, countdown: None)
    asset_id, listing_id = _seeded(conn, store)
    monkeypatch.setattr("app.tasks.media.ObjectStore.put", _raises(BotoCoreError()))
    media.process_photo(str(asset_id), 1)
    row = record.read(conn, asset_id)
    assert row is not None
    assert row.redacted_storage_key is None and row.redacted_sha256 is None
    assert store.get(redacted_key(listing_id, asset_id)) is None


@pytest.mark.parametrize("attempts", [1, record.MAX_ATTEMPTS - 1])
def test_a_row_the_sweeper_took_back_mid_run_is_left_alone(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch, scratch_dsn: str, attempts: int
) -> None:
    """`record.fail` and `record.exhaust` both report 0 when the row's state is not one the
    transition names, and 0 must never be read as a write that happened: `BACKOFF[0 - 1]` is the
    600-second rung the bound never reaches, scheduled for a row this run never touched.

    Driven by a REAL concurrent actor rather than a stubbed return. This run has been inside the
    OCR call for longer than `LOST_AFTER`, so `media.sweep`'s own rule (2) -- run here from a
    second connection, the real `record.sweep_candidates` -- has declared it a lost child and taken
    the row to REPROCESS_REQUIRED, which is neither a `FAIL_SOURCES` state nor an `EXHAUST_SOURCES`
    one. Both rungs of the ladder are covered: `attempts=1` is the arm that would have re-enqueued,
    `attempts=MAX-1` the arm whose claim spends the bound and means to exhaust."""
    scheduled: list[Any] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown: scheduled.append(countdown))
    asset_id, _ = _seeded(conn, store, processing_status="PROCESSING_FAILED", attempts=attempts)
    other = psycopg2.connect(scratch_dsn)
    other.autocommit = True
    try:
        def overtaken_by_the_sweeper(image: Any) -> Any:
            _age(other, [asset_id], minutes=30)
            assert record.sweep_candidates(other)["lost"] == [asset_id]
            raise media.ocr.OcrError("OCR_ERROR")

        monkeypatch.setattr("app.tasks.media.ocr.read_text", overtaken_by_the_sweeper)
        assert media.process_photo(str(asset_id), 1)["result"] == "state_changed"
    finally:
        other.close()
    assert scheduled == [], "a run that wrote nothing must not re-enqueue itself"
    row = record.read(conn, asset_id)
    assert row is not None
    assert row.processing_status == "REPROCESS_REQUIRED"
    assert _column(conn, asset_id, "last_error") == "TASK_LOST"


# --------------------------------------------------------------------------------------------
# The in-place re-run
# --------------------------------------------------------------------------------------------

def test_an_in_place_re_run_replaces_the_derivative_without_leaving_the_ready_state(
    conn: Any, store: Any
) -> None:
    """D-IDP-16: a processing-version bump must darken no listing. The row keeps its state,
    `buyer_visible` and confirmation throughout; the OLD derivative is served under its old hash
    until the one UPDATE at the end."""
    asset_id, listing_id = _seeded(conn, store, processing_status="SELLER_CONFIRMED", confirmed=True,
                                   buyer_visible=True, reprocess_reason="VERSION")
    store.put(redacted_key(listing_id, asset_id), b"the old derivative", "image/webp")
    assert media.process_photo(str(asset_id), 1)["result"] == "rerun"
    row = record.read(conn, asset_id)
    assert row is not None
    assert row.processing_status == "SELLER_CONFIRMED" and row.buyer_visible is True
    assert row.seller_confirmed and row.confirmed_sha256 == row.redacted_sha256
    assert row.reprocess_reason is None and store.get(redacted_key(listing_id, asset_id)) != b"the old derivative"
    assert _column(conn, asset_id, "reprocessed_at") is not None
    assert _column(conn, asset_id, "attempts") == 0


def test_an_in_place_re_run_keeps_every_region_the_seller_confirmed(conn: Any, store: Any) -> None:
    """`aggregate.union_auto` on a CONFIRMED row unions rather than replaces, so the new derivative
    hides a superset of what the seller approved -- and the seller's own manual mask survives a
    re-run that would never have found it."""
    manual = {"id": "m1", "polygon": [[10.0, 10.0], [90.0, 10.0], [90.0, 60.0], [10.0, 60.0]],
              "source": "manual", "expanded_from": None, "pad_px": 0, "by": None, "at": None}
    asset_id, _ = _seeded(conn, store, processing_status="SELLER_CONFIRMED", confirmed=True,
                          buyer_visible=True, reprocess_reason="OPERATOR", redaction_regions=[manual])
    assert media.process_photo(str(asset_id), 1)["result"] == "rerun"
    row = record.read(conn, asset_id)
    assert row is not None
    assert manual in row.redaction_regions
    assert any(r["source"] == "auto" for r in row.redaction_regions)


def test_a_third_failed_in_place_re_run_ends_in_review_required_with_a_null_slot(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one way a published listing comes to hold a non-ready photograph. Fail closed: the slot
    is null to buyers, never the original and never display."""
    scheduled: list[int] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown: scheduled.append(countdown))
    monkeypatch.setattr("app.tasks.media.redact.fill_regions", lambda display, polygons: None)
    asset_id, _ = _seeded(conn, store, processing_status="PUBLISHED", confirmed=True,
                          buyer_visible=True, reprocess_reason="VERSION")
    for _ in range(record.MAX_ATTEMPTS):
        media.process_photo(str(asset_id), 1)
    row = record.read(conn, asset_id)
    assert row is not None
    assert row.processing_status == "REVIEW_REQUIRED" and row.buyer_visible is False
    assert row.seller_confirmed is False
    assert scheduled == [30, 120]
    assert _column(conn, asset_id, "last_error") == "ENCODE_TOO_LARGE"


def test_a_failed_in_place_re_run_goes_on_serving_the_derivative_it_has(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first two rungs of the same ladder, from the buyer's side: the row does not leave its
    state, `buyer_visible` stays true and the hash the delivery resolver reads is unchanged."""
    monkeypatch.setattr(media.process_photo_task, "apply_async", lambda args, countdown: None)
    monkeypatch.setattr("app.tasks.media.redact.fill_regions", lambda display, polygons: None)
    asset_id, listing_id = _seeded(conn, store, processing_status="PUBLISHED", confirmed=True,
                                   buyer_visible=True, reprocess_reason="VERSION")
    store.put(redacted_key(listing_id, asset_id), b"the old derivative", "image/webp")
    before = record.read(conn, asset_id)
    assert media.process_photo(str(asset_id), 1)["result"] == "rerun_failed"
    after = record.read(conn, asset_id)
    assert after is not None and before is not None
    assert (after.processing_status, after.buyer_visible) == ("PUBLISHED", True)
    assert after.redacted_sha256 == before.redacted_sha256 and after.reprocess_reason == "VERSION"
    assert store.get(redacted_key(listing_id, asset_id)) == b"the old derivative"


def test_an_in_place_re_run_whose_scan_fails_changes_nothing_but_the_count(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The re-run's OTHER failure door: the scan itself, not the encode. Same rule -- the row keeps
    its state, its visibility and its derivative, and only `attempts` moves."""
    monkeypatch.setattr(media.process_photo_task, "apply_async", lambda args, countdown: None)
    monkeypatch.setattr("app.tasks.media.ocr.read_text", _raises(media.ocr.OcrError("OCR_ERROR")))
    asset_id, _ = _seeded(conn, store, processing_status="SELLER_CONFIRMED", confirmed=True,
                          buyer_visible=True, reprocess_reason="OPERATOR")
    before = record.read(conn, asset_id)
    assert media.process_photo(str(asset_id), 1) == {"asset": str(asset_id), "result": "rerun_failed",
                                                     "error": "OCR_ERROR", "retry_in": 30}
    after = record.read(conn, asset_id)
    assert after is not None and before is not None
    assert (after.processing_status, after.buyer_visible, after.attempts) == ("SELLER_CONFIRMED", True, 1)
    assert after.redacted_sha256 == before.redacted_sha256 and after.reprocess_reason == "OPERATOR"
    # A failed in-place attempt writes NO `last_error` (amendment A-IDP-8): it is not yet an outcome
    # anyone reads, and `exhaust` writes the code at the bound.
    assert _column(conn, asset_id, "last_error") is None


def test_an_in_place_re_run_whose_derivative_cannot_be_written_keeps_the_old_one(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bucket refuses the new bytes. The OLD object is still there, still named by the row, and
    still served: an in-place re-run that cannot write counts an attempt and leaves everything else
    alone (D-IDP-16)."""
    monkeypatch.setattr(media.process_photo_task, "apply_async", lambda args, countdown: None)
    asset_id, listing_id = _seeded(conn, store, processing_status="PUBLISHED", confirmed=True,
                                   buyer_visible=True, reprocess_reason="VERSION")
    store.put(redacted_key(listing_id, asset_id), b"the old derivative", "image/webp")
    monkeypatch.setattr("app.tasks.media.ObjectStore.put", _raises(BotoCoreError()))
    assert media.process_photo(str(asset_id), 1) == {"asset": str(asset_id), "result": "rerun_failed",
                                                     "error": "STORAGE_ERROR", "retry_in": 30}
    row = record.read(conn, asset_id)
    assert row is not None
    assert (row.processing_status, row.buyer_visible, row.attempts) == ("PUBLISHED", True, 1)
    assert store.get(redacted_key(listing_id, asset_id)) == b"the old derivative"


def test_an_in_place_re_run_that_produces_the_same_bytes_writes_no_object(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag is cleared and the version advanced, and the bucket is not written to at all: a
    version bump that changes nothing about this photograph costs one PUT less per photograph."""
    asset_id, _listing_id = _seeded(conn, store)
    assert media.process_photo(str(asset_id), 1)["result"] == "ready"
    settled = record.read(conn, asset_id)
    assert settled is not None
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET reprocess_reason = 'OPERATOR',"
                    " reprocess_requested_at = now(), processing_version = 0 WHERE asset_id = %s", (asset_id,))
    puts: list[str] = []
    real_put = media.ObjectStore.put
    monkeypatch.setattr("app.tasks.media.ObjectStore.put",
                        lambda self, key, data, content_type: (puts.append(key),
                                                               real_put(self, key, data, content_type))[1])
    assert media.process_photo(str(asset_id), 1) == {"asset": str(asset_id), "result": "rerun", "changed": False}
    assert puts == []
    row = record.read(conn, asset_id)
    assert row is not None
    assert row.reprocess_reason is None and row.redacted_sha256 == settled.redacted_sha256
    assert _column(conn, asset_id, "processing_version") == PROCESSING_VERSION


@pytest.mark.parametrize("stage", ["bump", "advance"])
def test_an_in_place_re_run_of_a_row_that_stopped_being_ready_abandons_it(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch, scratch_dsn: str, stage: str
) -> None:
    """`bump_attempt` answers None and `advance_in_place` answers 0 when the state forbids the
    write -- the two ways a flagged ready row can stop being one under a running re-run (a
    reviewer's decision, a third failure of a concurrent re-run). Neither may be read as a success,
    and None must never index `BACKOFF[-1]`."""
    monkeypatch.setattr(media.process_photo_task, "apply_async", lambda args, countdown: None)
    asset_id, _ = _seeded(conn, store, processing_status="READY_FOR_REVIEW", reprocess_reason="VERSION")
    other = psycopg2.connect(scratch_dsn)
    other.autocommit = True
    try:
        def moved_by_somebody_else(*args: Any, **kwargs: Any) -> Any:
            record.exhaust(other, asset_id, code="ENCODE_TOO_LARGE")
            return None if stage == "bump" else real_fill(*args, **kwargs)

        real_fill = media.redact.fill_regions
        monkeypatch.setattr("app.tasks.media.redact.fill_regions", moved_by_somebody_else)
        assert media.process_photo(str(asset_id), 1)["result"] == "rerun_abandoned"
    finally:
        other.close()
    row = record.read(conn, asset_id)
    assert row is not None and row.processing_status == "REVIEW_REQUIRED"


# --------------------------------------------------------------------------------------------
# The whole-worker refusals
# --------------------------------------------------------------------------------------------

def test_an_unconfigured_bucket_leaves_the_row_where_it_is(conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Not a per-photograph failure: `S3_*` is unset for the whole worker (which is every deployed
    service today, spec A.2). Writing PROCESSING_FAILED on every row of every listing would spend
    three attempts on an operator's configuration mistake."""
    monkeypatch.setattr("app.tasks.media.ObjectStore.from_settings", lambda settings: None)
    asset_id, _ = make_row(conn, processing_status="UPLOADED")
    assert media.process_photo(str(asset_id), 1)["result"] == "storage_unavailable"
    row = record.read(conn, asset_id)
    assert row is not None and row.processing_status == "UPLOADED"


def test_a_database_that_will_not_connect_is_a_summary_from_both_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one failure that happens before there is any row to write a state onto. The reason is
    the exception CLASS and never its text, which can carry the DSN."""
    monkeypatch.setattr("app.tasks.media.psycopg2.connect", _raises(psycopg2.OperationalError("nope")))
    assert media.process_photo(str(uuid4()), 1)["result"] == "database_unavailable"
    assert media.sweep() == {"enqueued": 0, "error": "database_unavailable"}


def test_neither_entry_point_ever_names_the_dsn_in_its_answer(monkeypatch: pytest.MonkeyPatch,
                                                              caplog: Any) -> None:
    """A psycopg2 message carries the connection string. The summary and the log line both name the
    exception CLASS and nothing else."""
    secret = "postgresql://pm:hunter2@db.internal:5432/practice_match"
    monkeypatch.setattr("app.tasks.media.psycopg2.connect",
                        _raises(psycopg2.OperationalError(f"could not connect to {secret}")))
    with caplog.at_level("ERROR"):
        answer = media.process_photo(str(uuid4()), 1)
    assert "hunter2" not in repr(answer) and "hunter2" not in caplog.text
    assert "OperationalError" in caplog.text


# --------------------------------------------------------------------------------------------
# The sweeper
# --------------------------------------------------------------------------------------------

def test_the_sweeper_applies_its_six_rules_and_enqueues_each_subject_once(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One UPDATE or one enqueue per rule (spec C.5). Every window is set by moving `updated_at`
    backwards, which is why every writer in `record.py` sets it explicitly."""
    sent: list[str] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown=None: sent.append(args[0]))
    subjects = {
        "unstarted": _seeded(conn, store, processing_status="UPLOADED")[0],
        "lost": _seeded(conn, store, processing_status="PROCESSING", attempts=1)[0],
        "retry": _seeded(conn, store, processing_status="PROCESSING_FAILED", attempts=1)[0],
        "reprocess": _seeded(conn, store, processing_status="REPROCESS_REQUIRED", attempts=1)[0],
        "version": _seeded(conn, store, processing_status="READY_FOR_REVIEW", processing_version=0)[0],
        "flagged": _seeded(conn, store, processing_status="READY_FOR_REVIEW", reprocess_reason="OPERATOR")[0],
    }
    fresh = _seeded(conn, store, processing_status="PROCESSING", attempts=1)[0]   # not yet lost
    _age(conn, list(subjects.values()), minutes=30)
    summary = media.sweep()
    assert sorted(sent) == sorted(str(a) for a in subjects.values())
    assert str(fresh) not in sent
    lost = record.read(conn, subjects["lost"])
    assert lost is not None
    assert lost.processing_status == "REPROCESS_REQUIRED"
    assert lost.reprocess_reason is None                                      # a state, not a flag
    assert _column(conn, subjects["lost"], "last_error") == "TASK_LOST"
    version = record.read(conn, subjects["version"])
    assert version is not None
    assert version.reprocess_reason == "VERSION" and version.processing_status == "READY_FOR_REVIEW"
    assert summary["enqueued"] == len(subjects)
    assert {name: summary[name] for name in subjects} == dict.fromkeys(subjects, 1)


def test_the_sweeper_finds_the_row_a_dead_worker_abandoned_and_the_pipeline_finishes_it(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE WHOLE POINT OF THE SWEEPER, end to end and not by rule. A worker claimed this
    photograph and was killed: the row is PROCESSING, no message exists for it anywhere, and
    nothing else in the system will ever look at it again. The sweeper's own enqueue is what runs
    `process_photo` here, and the photograph reaches READY_FOR_REVIEW."""
    asset_id, _ = _seeded(conn, store, processing_status="PROCESSING", attempts=1)
    _age(conn, [asset_id], minutes=30)
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown=None: media.process_photo(*args))
    assert media.sweep()["enqueued"] == 1
    row = record.read(conn, asset_id)
    assert row is not None
    assert row.processing_status == "READY_FOR_REVIEW" and row.redacted_storage_key is not None


def test_a_row_still_inside_its_window_is_not_swept(conn: Any, store: Any,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """Each rule's window, one row either side of it. Without the windows the sweeper would
    re-enqueue a photograph a worker is in the middle of, every five minutes, for ever."""
    sent: list[str] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown=None: sent.append(args[0]))
    windows = {"UPLOADED": 2, "PROCESSING": 6, "PROCESSING_FAILED": 12, "REDACTION_FAILED": 12,
               "REPROCESS_REQUIRED": 6}
    inside, outside = [], []
    for state, minutes in windows.items():
        young, _ = _seeded(conn, store, processing_status=state, attempts=1)
        old, _ = _seeded(conn, store, processing_status=state, attempts=1)
        _age(conn, [young], minutes=minutes - 1)
        _age(conn, [old], minutes=minutes + 1)
        inside.append(young)
        outside.append(old)
    media.sweep()
    assert sorted(sent) == sorted(str(a) for a in outside)
    assert [str(a) for a in inside if str(a) in sent] == []


def test_a_failed_row_that_has_spent_its_attempts_is_not_swept(conn: Any, store: Any,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule (3) is `attempts < 3`. REVIEW_REQUIRED is the seller's to leave, through Try again."""
    sent: list[str] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown=None: sent.append(args[0]))
    spent, _ = _seeded(conn, store, processing_status="PROCESSING_FAILED", attempts=3)
    done, _ = _seeded(conn, store, processing_status="REVIEW_REQUIRED", attempts=3)
    _age(conn, [spent, done], minutes=60)
    media.sweep()
    assert sent == []


def test_a_sweep_with_nothing_to_do_enqueues_nothing(conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(media.process_photo_task, "apply_async",
                        lambda args, countdown=None: sent.append(args[0]))
    assert media.sweep() == {"enqueued": 0, "unstarted": 0, "retry": 0, "reprocess": 0,
                             "flagged": 0, "lost": 0, "version": 0}
    assert sent == []


# --------------------------------------------------------------------------------------------
# The Playwright execution model -- controller amendment A-IDP-2
# --------------------------------------------------------------------------------------------

def test_the_eager_branch_runs_the_pipeline_inline_and_never_calls_send_task(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Controller amendment A-IDP-2. `send_task` ignores `task_always_eager` and warns
    `AlwaysEagerIgnored`, which `-W error` turns into a failure -- so the eager path must not reach
    it at all, and the assertion below is on the WARNING as much as on the state."""
    monkeypatch.setattr("app.privacy.record.settings.celery_task_always_eager", True)
    monkeypatch.setattr(media.celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr("app.privacy.record.celery_app.send_task",
                        _raises(AssertionError("send_task must not be reached while eager")))
    asset_id, _ = _seeded(conn, store, processing_status="UPLOADED")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        record.enqueue_processing(asset_id, 1)
    row = record.read(conn, asset_id)
    assert row is not None and row.processing_status == "READY_FOR_REVIEW"


def test_the_default_path_publishes_by_name_and_imports_no_task_module(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr("app.privacy.record.settings.celery_task_always_eager", False)
    monkeypatch.setattr("app.privacy.record.celery_app.send_task",
                        lambda name, **kw: sent.append((name, kw)))
    record.enqueue_processing(uuid4(), 1)
    # The asset id is read back out of the call rather than restated, so this asserts the SHAPE of
    # what was published without a second copy of the value under test.
    assert sent == [("media.process_photo", {"args": [sent[0][1]["args"][0], 1], "queue": "media"})]


def test_the_eager_pipeline_stops_at_the_bound_instead_of_recursing_for_ever(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With eager Celery the `apply_async` in the ladder executes INLINE, and Celery ignores
    `countdown` when eager -- so a failing photograph re-enters `process_photo` immediately. The
    bound is what stops it: three attempts, then REVIEW_REQUIRED."""
    monkeypatch.setattr("app.privacy.record.settings.celery_task_always_eager", True)
    monkeypatch.setattr(media.celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr("app.tasks.media.redact.fill_regions", lambda display, polygons: None)
    asset_id, _ = _seeded(conn, store, processing_status="UPLOADED")
    record.enqueue_processing(asset_id, 1)
    row = record.read(conn, asset_id)
    assert row is not None
    assert (row.processing_status, row.attempts) == ("REVIEW_REQUIRED", record.MAX_ATTEMPTS)
