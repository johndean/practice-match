"""One case per transition of spec 2026-09-09 C.4, and one per dead end.

Directive 6: "No image may silently fall through the state machine." The proof of that is here: a
transition that is not in this table has no function to perform it, and every function refuses from
a state the table does not name."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.privacy import record

#: The builder Step 2 writes; every privacy suite imports it, so a CHECK that changes fails once.
from tests.privacy.conftest import make_account, make_listing
from tests.privacy.conftest import make_row as _row

# (from, to, the call that performs it) -- the table read straight off spec C.4.
#
# Two rows of that table are performed by a function that takes a LISTING and not an asset
# (`mark_published`) or that is reached from three states at once (`reset_confirmation`); both have
# their own case below, because a builder call per parametrised row cannot express them.
TRANSITIONS = (
    ("UPLOADED", "PROCESSING", "claim"),
    ("PROCESSING_FAILED", "PROCESSING", "claim"),
    ("REDACTION_FAILED", "PROCESSING", "claim"),
    ("REPROCESS_REQUIRED", "PROCESSING", "claim"),
    ("PROCESSING", "SCANNED", "record_scan"),
    ("SCANNED", "REDACTION_GENERATED", "record_derivative"),
    ("REDACTION_GENERATED", "READY_FOR_REVIEW", "mark_ready"),
    ("READY_FOR_REVIEW", "SELLER_CONFIRMED", "confirm"),
    ("PROCESSING", "PROCESSING_FAILED", "fail"),
    ("SCANNED", "REDACTION_FAILED", "fail"),
    # `PROCESSING | SCANNED -> REVIEW_REQUIRED` is one row of spec C.4 and both of its sources are
    # here; the three ready states below are the table's NEXT row, the third failed in-place
    # re-run, which lands in the same state through the same function.
    ("PROCESSING", "REVIEW_REQUIRED", "exhaust"),
    ("SCANNED", "REVIEW_REQUIRED", "exhaust"),
    ("READY_FOR_REVIEW", "REVIEW_REQUIRED", "exhaust"),
    ("SELLER_CONFIRMED", "REVIEW_REQUIRED", "exhaust"),
    ("PUBLISHED", "REVIEW_REQUIRED", "exhaust"),
    ("REVIEW_REQUIRED", "UPLOADED", "reset_for_retry"),
    ("PROCESSING_FAILED", "UPLOADED", "reset_for_retry"),
    ("REDACTION_FAILED", "UPLOADED", "reset_for_retry"),
    ("REPROCESS_REQUIRED", "UPLOADED", "reset_for_retry"),
)

# States from which the claim must write NOTHING: a ready row is never re-run by this path (its
# in-place re-run is `advance_in_place`), and a fresh PROCESSING row is another child's work.
UNCLAIMABLE = ("PROCESSING", "SCANNED", "REDACTION_GENERATED", "READY_FOR_REVIEW",
               "SELLER_CONFIRMED", "PUBLISHED", "REVIEW_REQUIRED")


def _read(conn: Any, asset_id: UUID) -> record.PrivacyRow:
    """`record.read` answers `PrivacyRow | None`; every call in this file has just written the row
    it is reading, so a None here is the test's own failure and says so at once."""
    found = record.read(conn, asset_id)
    assert found is not None, f"the privacy row for {asset_id} vanished"
    return found


def _perform(conn: Any, call: str, asset_id: UUID, listing_id: UUID) -> None:
    """The one call each transition names, with the arguments that transition takes. A `match` and
    not a dict of partials: each arm is read against its own TRANSITIONS row, and an arm added
    without a row (or a row added without an arm) is visible in one screen rather than hidden
    behind a KeyError at run time."""
    match call:
        case "claim":
            record.claim(conn, asset_id, 1)
        case "record_scan":
            record.record_scan(conn, asset_id, ocr={"size": [800, 600], "lines": []},
                               identity_matches=[], vision={"status": "unavailable"}, detected_regions=[])
        case "record_derivative":
            record.record_derivative(conn, asset_id, key=f"listings/{listing_id}/photos/{asset_id}/redacted.webp",
                                     sha256="b" * 64, regions=[])
        case "mark_ready":
            record.mark_ready(conn, asset_id, visible=False, version=1)
        case "confirm":
            record.confirm(conn, asset_id, account_id=make_account(conn), visibility="NOT_SHOW", edited=False)
        case "fail":
            state = "REDACTION_FAILED" if _read(conn, asset_id).processing_status == "SCANNED" \
                else "PROCESSING_FAILED"
            record.fail(conn, asset_id, state=state, code="UNDECODABLE")
        case "exhaust":
            record.exhaust(conn, asset_id, code="OCR_ERROR")
        case _:
            record.reset_for_retry(conn, asset_id)


@pytest.mark.parametrize(("start", "end", "call"), TRANSITIONS)
def test_every_contracted_transition_is_performed_by_its_own_function(
    conn: Any, start: str, end: str, call: str
) -> None:
    asset_id, listing_id = _row(conn, processing_status=start)
    _perform(conn, call, asset_id, listing_id)
    assert _read(conn, asset_id).processing_status == end


@pytest.mark.parametrize("start", UNCLAIMABLE)
def test_the_claim_writes_nothing_from_a_state_it_does_not_own(conn: Any, start: str) -> None:
    """The dead ends. A duplicate message, a late retry and a redelivered task all land here, and
    what makes them harmless is that the claim is ONE conditional UPDATE that matches no row."""
    asset_id, _ = _row(conn, processing_status=start)
    before = _read(conn, asset_id)
    assert record.claim(conn, asset_id, 1) is None
    assert _read(conn, asset_id) == before


def test_a_lost_processing_row_is_claimable_after_six_minutes(conn: Any) -> None:
    """`acks_late` + `reject_on_worker_lost`: a child killed mid-run leaves the row PROCESSING. The
    redelivered run finds it recent and writes nothing; the sweeper's rule (2) marks it
    REPROCESS_REQUIRED. This is the window that separates the two."""
    asset_id, _ = _row(conn, processing_status="PROCESSING", attempts=1)
    assert record.claim(conn, asset_id, 1) is None
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET updated_at = %s WHERE asset_id = %s",
                    (datetime.now(UTC) - timedelta(minutes=7), asset_id))
    claimed = record.claim(conn, asset_id, 1)
    assert claimed is not None and claimed.attempts == 2


def test_a_stale_enqueue_below_the_current_version_claims_nothing(conn: Any) -> None:
    asset_id, _ = _row(conn, processing_status="UPLOADED", processing_version=2)
    assert record.claim(conn, asset_id, 1) is None


def test_the_claim_applies_the_confirmation_reset_rule(conn: Any) -> None:
    """Spec C.4's reset rule: a derivative the seller has not seen can never inherit a
    confirmation. Applied IN THE CLAIM's own statement, so no window exists between the two."""
    asset_id, _ = _row(conn, processing_status="REDACTION_FAILED", confirmed=True)
    claimed = record.claim(conn, asset_id, 1)
    assert claimed is not None
    after = _read(conn, asset_id)
    assert (after.seller_confirmed, after.confirmed_sha256, after.buyer_visible) == (False, None, False)


def test_a_confirmed_row_keeps_its_confirmation_through_an_in_place_re_run(conn: Any) -> None:
    """The ONE derivative write that does not reset (spec C.5): the in-place re-run of a confirmed
    row, whose region set is by construction a superset of the confirmed one, advances
    confirmed_sha256 with redacted_sha256 in the same UPDATE."""
    asset_id, _ = _row(conn, processing_status="SELLER_CONFIRMED", confirmed=True,
                       buyer_visible=True, reprocess_reason="VERSION")
    record.advance_in_place(conn, asset_id, sha256="e" * 64, version=2, regions=[])
    after = _read(conn, asset_id)
    assert after.processing_status == "SELLER_CONFIRMED"
    assert after.seller_confirmed and after.confirmed_sha256 == "e" * 64 == after.redacted_sha256
    assert after.reprocess_reason is None and after.processing_version == 2
    assert after.buyer_visible, "a version bump must darken no listing (spec C.5)"


def test_an_unconfirmed_row_gains_no_confirmation_from_an_in_place_re_run(conn: Any) -> None:
    """The other arm of the same CASE. A flagged READY_FOR_REVIEW row has nothing to carry forward,
    and the re-run must not invent one: `confirmed_sha256` stays NULL and the row stays
    unconfirmed, so the seller still has to look at it."""
    asset_id, _ = _row(conn, processing_status="READY_FOR_REVIEW", reprocess_reason="OPERATOR",
                       buyer_visible=True)
    record.advance_in_place(conn, asset_id, sha256="e" * 64, version=3,
                            regions=[{"source": "auto", "box": [1, 2, 3, 4]}])
    after = _read(conn, asset_id)
    assert after.processing_status == "READY_FOR_REVIEW" and after.buyer_visible
    assert after.redacted_sha256 == "e" * 64 and after.confirmed_sha256 is None
    assert not after.seller_confirmed
    assert after.redaction_regions == [{"source": "auto", "box": [1, 2, 3, 4]}]


def test_confirm_refuses_from_every_state_but_ready_and_is_idempotent_from_confirmed(conn: Any) -> None:
    """Directive 11: "Never allow AI_PASSED to mean READY_TO_PUBLISH." A failed photograph cannot
    be confirmed INTO readiness."""
    account = make_account(conn)   # `seller_confirmation_account_id` REFERENCES account(id)
    for start in ("UPLOADED", "PROCESSING", "SCANNED", "REDACTION_GENERATED", "REVIEW_REQUIRED"):
        asset_id, _ = _row(conn, processing_status=start)
        assert record.confirm(conn, asset_id, account_id=account, visibility="NOT_SHOW", edited=False) is False
    ready, _ = _row(conn, processing_status="READY_FOR_REVIEW")
    assert record.confirm(conn, ready, account_id=account, visibility="NOT_SHOW", edited=False) is True
    assert record.confirm(conn, ready, account_id=account, visibility="NOT_SHOW", edited=False) is True


def test_confirm_refuses_a_ready_row_that_has_no_derivative_hash(conn: Any) -> None:
    """`lap_ready_has_derivative_ck` constrains the KEY, not the hash, so a READY_FOR_REVIEW row
    with a null `redacted_sha256` is a shape the database permits. `confirmed_sha256 :=
    redacted_sha256` on such a row would be a confirmation of nothing, and `lap_confirmed_ck` would
    let it through (`NULL = NULL` is NULL, and a CHECK passes on NULL) -- so the WHERE clause
    carries `redacted_sha256 IS NOT NULL` and this is the case that holds it there."""
    asset_id, _ = _row(conn, processing_status="READY_FOR_REVIEW")
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET redacted_sha256 = NULL WHERE asset_id = %s", (asset_id,))
    assert record.confirm(conn, asset_id, account_id=make_account(conn),
                          visibility="NOT_SHOW", edited=False) is False
    assert _read(conn, asset_id).processing_status == "READY_FOR_REVIEW"


def test_confirm_records_the_listing_setting_and_an_edited_review_that_never_reverts(conn: Any) -> None:
    """`final_privacy_state` is what P10's flip compares, and `seller_review_status` is 'edited' for
    ever once a mask has been touched: a later "Looks good" with `edited=False` must not erase the
    fact that the seller changed the machine's answer."""
    asset_id, _ = _row(conn, processing_status="READY_FOR_REVIEW")
    account = make_account(conn)
    assert record.confirm(conn, asset_id, account_id=account, visibility="SHOW", edited=True) is True
    after = _read(conn, asset_id)
    assert after.final_privacy_state == "SHOW" and after.buyer_visible
    assert after.confirmed_sha256 == after.redacted_sha256
    assert record.confirm(conn, asset_id, account_id=account, visibility="SHOW", edited=False) is True
    assert _review_status(conn, asset_id) == "edited"


def test_reset_for_retry_refuses_from_a_ready_state(conn: Any) -> None:
    for start in (*record.READY_STATES, "PROCESSING", "SCANNED", "REDACTION_GENERATED"):
        asset_id, _ = _row(conn, processing_status=start)
        assert record.reset_for_retry(conn, asset_id) is False


def test_record_scan_writes_nothing_from_a_state_that_is_not_processing(conn: Any) -> None:
    """A dead end of the same shape as the claim's: the scan of a run whose row has already moved
    on -- a lost child's late return, a duplicated chain -- must not overwrite a newer record."""
    for start in ("UPLOADED", "SCANNED", "READY_FOR_REVIEW", "REVIEW_REQUIRED"):
        asset_id, _ = _row(conn, processing_status=start)
        before = _read(conn, asset_id)
        record.record_scan(conn, asset_id, ocr={"size": [1, 1], "lines": []}, identity_matches=[],
                           vision={"status": "ok"}, detected_regions=[{"box": [0, 0, 1, 1]}])
        assert _read(conn, asset_id) == before


def test_record_derivative_writes_nothing_from_a_state_that_is_not_scanned(conn: Any) -> None:
    """The key and the hash of a derivative are written once per run, from SCANNED alone. A second
    write from READY_FOR_REVIEW would replace a confirmed row's derivative without the reset."""
    for start in ("UPLOADED", "PROCESSING", "REDACTION_GENERATED", "SELLER_CONFIRMED"):
        asset_id, listing_id = _row(conn, processing_status=start)
        before = _read(conn, asset_id)
        record.record_derivative(conn, asset_id, key=f"listings/{listing_id}/photos/{uuid4()}/redacted.webp",
                                 sha256="f" * 64, regions=[{"source": "auto"}])
        assert _read(conn, asset_id) == before


def test_mark_ready_writes_nothing_from_a_state_without_a_fresh_derivative(conn: Any) -> None:
    """READY_FOR_REVIEW is reached from REDACTION_GENERATED and from nowhere else: a row that
    failed, or one the seller has already confirmed, must not be promoted by the completion step of
    a run that no longer owns it."""
    for start in ("UPLOADED", "PROCESSING", "SCANNED", "SELLER_CONFIRMED", "REVIEW_REQUIRED"):
        asset_id, _ = _row(conn, processing_status=start)
        before = _read(conn, asset_id)
        record.mark_ready(conn, asset_id, visible=True, version=9)
        assert _read(conn, asset_id) == before


def test_mark_ready_makes_a_show_listings_photograph_visible_without_a_confirmation(conn: Any) -> None:
    """Spec C.4: "under SHOW `buyer_visible := true`" at readiness -- the confirmation is what
    NOT_SHOW needs, not what SHOW needs."""
    asset_id, _ = _row(conn, processing_status="REDACTION_GENERATED")
    record.mark_ready(conn, asset_id, visible=True, version=1)
    after = _read(conn, asset_id)
    assert after.processing_status == "READY_FOR_REVIEW" and after.buyer_visible


def test_publishing_advances_only_the_gated_rows_and_never_reverts(conn: Any) -> None:
    """PUBLISHED means "published at least once": a pause, unpublish or withdrawal does not revert
    it -- `_published_photos`' status filter is what hides the listing (spec C.4)."""
    confirmed, listing_id = _row(conn, processing_status="SELLER_CONFIRMED", confirmed=True,
                                 buyer_visible=True)
    show = _row(conn, processing_status="READY_FOR_REVIEW", buyer_visible=True, listing_id=listing_id)[0]
    not_show = _row(conn, processing_status="READY_FOR_REVIEW", listing_id=listing_id)[0]
    pending, _ = _row(conn, processing_status="UPLOADED", listing_id=listing_id)
    record.mark_published(conn, listing_id)
    assert _read(conn, confirmed).processing_status == "PUBLISHED"
    assert _read(conn, show).processing_status == "PUBLISHED"
    assert _read(conn, not_show).processing_status == "READY_FOR_REVIEW"
    assert _read(conn, pending).processing_status == "UPLOADED"
    record.mark_published(conn, listing_id)
    assert _read(conn, confirmed).processing_status == "PUBLISHED"


def _executed_sql(module: Any) -> list[str]:
    """Every `cur.execute(...)` call's SQL in `module`, one string per CALL.

    An AST walk and not a regex over the source: a regex that ends a "statement" at a blank line or
    a docstring quote can span two `execute` calls, and one that contains `updated_at = now()`
    would then hide a neighbour that does not. `ast` gives the call boundary exactly. The literal
    parts of an f-string are Constants inside the JoinedStr, so `{RESET_COLUMNS}` contributes
    nothing -- which is right: every statement writes `updated_at = now()` in its own text,
    outside that fragment."""
    import ast
    import inspect

    found: list[str] = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute" and node.args):
            continue
        found.append(" ".join(piece.value for piece in ast.walk(node.args[0])
                              if isinstance(piece, ast.Constant) and isinstance(piece.value, str)))
    return found


def test_every_update_in_the_module_sets_updated_at() -> None:
    """The sweeper's age windows and `listing_asset_privacy_sweep_idx` read `updated_at`, and there
    is no trigger precedent in `migrations/` -- `listing.updated_at` is maintained the same way, by
    hand, in `app/api/seller_listings.py`. A statement that forgets it makes a row invisible to the
    sweeper for ever, so the rule is checked rather than trusted (spec C.3)."""
    updates = [sql for sql in _executed_sql(record) if "UPDATE listing_asset_privacy" in sql]
    assert len(updates) >= 8, "far fewer UPDATEs than this module has -- the walk found the wrong calls"
    missing = [sql[:120] for sql in updates if "updated_at = now()" not in sql]
    assert missing == [], missing


def test_the_reset_promotes_nothing_from_a_state_that_is_not_ready(conn: Any) -> None:
    """Spec C.1 step 3 says the reset's transitions come "from SELLER_CONFIRMED/PUBLISHED". Without
    the READY_STATES guard this UPDATE is `WHERE asset_id = %s` and it PROMOTES: a REDACTION_FAILED
    row that still carries a stale derivative key would become READY_FOR_REVIEW, then confirmable,
    then buyer-visible over a derivative whose regeneration had failed."""
    for start in ("UPLOADED", "PROCESSING", "SCANNED", "PROCESSING_FAILED", "REDACTION_FAILED",
                  "REVIEW_REQUIRED", "REPROCESS_REQUIRED"):
        asset_id, _ = _row(conn, processing_status=start)
        assert record.reset_confirmation(conn, asset_id) is False
        assert _read(conn, asset_id).processing_status == start
    for start in record.READY_STATES:
        asset_id, _ = _row(conn, processing_status=start, buyer_visible=True)
        assert record.reset_confirmation(conn, asset_id) is True
        after = _read(conn, asset_id)
        assert after.processing_status == "READY_FOR_REVIEW"
        assert not after.seller_confirmed and not after.buyer_visible
        assert after.confirmed_sha256 is None and after.final_privacy_state is None
        assert _review_status(conn, asset_id) == "edited"


def test_the_reset_can_carry_the_seller_s_own_region_set(conn: Any) -> None:
    """The mask routes' arm (P12): "a manual mask is added or a mask removed" is the SAME
    transition with the new region set written in the same statement, so no window exists in which
    the row is back in review against the regions it had before the edit."""
    regions = [{"id": "r1", "source": "manual", "box": [10, 20, 30, 40]}]
    asset_id, _ = _row(conn, processing_status="SELLER_CONFIRMED", confirmed=True, buyer_visible=True,
                       redaction_regions=[{"id": "r0", "source": "auto"}])
    assert record.reset_confirmation(conn, asset_id, regions=regions) is True
    after = _read(conn, asset_id)
    assert after.processing_status == "READY_FOR_REVIEW" and after.redaction_regions == regions
    assert not after.seller_confirmed and not after.buyer_visible
    # ...and the guard holds on this arm too, not only on the one above.
    failed, _ = _row(conn, processing_status="REDACTION_FAILED")
    assert record.reset_confirmation(conn, failed, regions=regions) is False
    assert _read(conn, failed).redaction_regions == []


def test_staleness_is_a_flag_on_the_ready_rows_and_never_a_state(conn: Any) -> None:
    """D-IDP-16: a marked row goes on serving the derivative it has while the in-place re-run
    replaces it. The listing's non-ready rows are not marked (they are being processed already) and
    a row already carrying a reason is not re-stamped, so a second PATCH does not enqueue a second
    re-run of the same photograph."""
    listing = make_listing(conn, f"idp-{uuid4().hex[:8]}")
    ready, _ = _row(conn, processing_status="READY_FOR_REVIEW", listing_id=listing, buyer_visible=True)
    published, _ = _row(conn, processing_status="PUBLISHED", listing_id=listing, buyer_visible=True)
    pending, _ = _row(conn, processing_status="UPLOADED", listing_id=listing)
    already, _ = _row(conn, processing_status="SELLER_CONFIRMED", confirmed=True, listing_id=listing,
                      reprocess_reason="OPERATOR")
    elsewhere, _ = _row(conn, processing_status="READY_FOR_REVIEW")

    flagged = record.flag_stale(conn, listing_id=listing, reason="IDENTITY_CHANGED")
    assert sorted(flagged) == sorted([ready, published])
    assert _read(conn, ready).reprocess_reason == "IDENTITY_CHANGED"
    assert _read(conn, ready).processing_status == "READY_FOR_REVIEW"
    assert _read(conn, ready).buyer_visible, "a flagged row goes on serving its derivative"
    assert _read(conn, pending).reprocess_reason is None
    assert _read(conn, already).reprocess_reason == "OPERATOR"
    assert _read(conn, elsewhere).reprocess_reason is None
    assert record.flag_stale(conn, listing_id=listing, reason="VERSION") == []


def test_visibility_is_granted_only_to_a_ready_row_and_withdrawn_from_any(conn: Any) -> None:
    """The NOT_SHOW -> SHOW flip's per-row arm (spec C.1 step 4). Granting is gated on readiness --
    `lap_visible_ready_ck` would refuse the write outright, and a flip that raised on one
    photograph would abandon the rest of the listing -- while withdrawing is unconditional, because
    hiding is always safe."""
    for start in ("UPLOADED", "PROCESSING", "SCANNED", "REDACTION_GENERATED", "PROCESSING_FAILED",
                  "REVIEW_REQUIRED"):
        asset_id, _ = _row(conn, processing_status=start)
        record.set_visibility(conn, asset_id, visible=True)
        assert _read(conn, asset_id).buyer_visible is False
    ready, _ = _row(conn, processing_status="READY_FOR_REVIEW")
    record.set_visibility(conn, ready, visible=True)
    assert _read(conn, ready).buyer_visible is True
    record.set_visibility(conn, ready, visible=False)
    assert _read(conn, ready).buyer_visible is False
    hidden, _ = _row(conn, processing_status="PROCESSING_FAILED")
    record.set_visibility(conn, hidden, visible=False)
    assert _read(conn, hidden).buyer_visible is False


def test_the_rows_of_a_listing_are_read_in_order_and_no_other_listings_are(conn: Any) -> None:
    """`rows_for` is what the wizard's review dialog, the publish gate's predicate and P10's flip
    all page over, so it is scoped to the one listing and ordered the way the step-6 tiles are."""
    listing = make_listing(conn, f"idp-{uuid4().hex[:8]}")
    mine = [_row(conn, processing_status="UPLOADED", listing_id=listing)[0] for _ in range(3)]
    other, _ = _row(conn, processing_status="UPLOADED")
    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM listing_asset_privacy WHERE listing_id = %s"
                    " ORDER BY created_at, asset_id", (listing,))
        expected = [UUID(str(r[0])) for r in cur.fetchall()]
    assert sorted(expected) == sorted(mine)
    assert [r.asset_id for r in record.rows_for(conn, listing)] == expected
    assert other not in [r.asset_id for r in record.rows_for(conn, listing)]


def test_a_row_that_is_not_there_reads_as_none(conn: Any) -> None:
    """The absence the resolver and the routes branch on: a document, a deleted photograph, an
    asset id a caller invented. Never an exception, never a default-constructed row."""
    assert record.read(conn, uuid4()) is None
    assert record.rows_for(conn, uuid4()) == []


def test_the_read_joins_the_display_object_the_resolver_needs(conn: Any) -> None:
    """`PrivacyRow` carries the DISPLAY key and hash off `listing_asset` so `buyer_variant` can
    decide a request from one object (spec C.7) -- the join is part of the contract, not an
    optimisation."""
    from app.privacy import display_key, original_key

    asset_id, listing_id = _row(conn, processing_status="READY_FOR_REVIEW")
    row = _read(conn, asset_id)
    assert row.listing_id == listing_id
    assert row.display_storage_key == display_key(listing_id, asset_id)
    assert row.display_sha256 == "d" * 64
    assert row.original_storage_key == original_key(listing_id, asset_id, ".jpg")
    assert row.redacted_storage_key != row.original_storage_key


def test_the_failure_returns_the_attempts_that_decide_the_next_move(conn: Any) -> None:
    """`fail` is the only writer whose RETURN VALUE is read: P8's `_retry_or_exhaust` compares it
    with MAX_ATTEMPTS, so a count that does not come back from the row itself would make the ladder
    a guess."""
    asset_id, _ = _row(conn, processing_status="PROCESSING", attempts=2)
    assert record.fail(conn, asset_id, state="PROCESSING_FAILED", code="OCR_ERROR") == 2
    assert _read(conn, asset_id).attempts == 2


def test_the_exhausted_row_is_a_fail_closed_null_slot(conn: Any) -> None:
    """Spec C.4's "the third failed in-place re-run": the reset rule applied and `buyer_visible`
    false, on a PUBLISHED row too. A photograph whose redaction cannot be produced is withdrawn
    from buyers -- never served as the original (directive 19)."""
    asset_id, _ = _row(conn, processing_status="PUBLISHED", confirmed=True, buyer_visible=True,
                       reprocess_reason="VERSION")
    record.exhaust(conn, asset_id, code="ENCODE_TOO_LARGE")
    after = _read(conn, asset_id)
    assert after.processing_status == "REVIEW_REQUIRED"
    assert not after.buyer_visible and not after.seller_confirmed
    assert after.confirmed_sha256 is None and after.final_privacy_state is None
    assert after.original_storage_key != after.redacted_storage_key
    assert _review_status(conn, asset_id) == "pending"


def test_the_retry_clears_the_attempts_the_ladder_spent(conn: Any) -> None:
    """"Try again" is a fresh budget, not a fourth attempt on the old one (spec C.4)."""
    asset_id, _ = _row(conn, processing_status="REVIEW_REQUIRED", attempts=3)
    assert record.reset_for_retry(conn, asset_id) is True
    after = _read(conn, asset_id)
    assert (after.processing_status, after.attempts) == ("UPLOADED", 0)


def test_the_scan_records_what_the_run_found(conn: Any) -> None:
    """`ocr`, `identity_matches`, `vision` and `detected_regions` are the audit record directive 18
    asks for; the SCANNED transition is the one place they are written."""
    asset_id, _ = _row(conn, processing_status="PROCESSING")
    record.record_scan(conn, asset_id, ocr={"size": [800, 600], "lines": [{"text": "HILL COUNTRY"}]},
                       identity_matches=[{"field": "name", "method": "substring"}],
                       vision={"status": "ok", "regions": []},
                       detected_regions=[{"box": [1, 2, 3, 4], "source": "ocr"}])
    with conn.cursor() as cur:
        cur.execute("SELECT ocr, identity_matches, vision, detected_regions"
                    " FROM listing_asset_privacy WHERE asset_id = %s", (asset_id,))
        ocr, matches, vision, detected = cur.fetchone()
    assert ocr == {"size": [800, 600], "lines": [{"text": "HILL COUNTRY"}]}
    assert matches == [{"field": "name", "method": "substring"}]
    assert vision == {"status": "ok", "regions": []}
    assert detected == [{"box": [1, 2, 3, 4], "source": "ocr"}]


def test_the_derivative_write_records_its_key_hash_and_regions(conn: Any) -> None:
    asset_id, listing_id = _row(conn, processing_status="SCANNED")
    key = f"listings/{listing_id}/photos/{asset_id}/redacted.webp"
    record.record_derivative(conn, asset_id, key=key, sha256="c" * 64,
                             regions=[{"source": "auto", "box": [0, 0, 5, 5]}])
    after = _read(conn, asset_id)
    assert (after.redacted_storage_key, after.redacted_sha256) == (key, "c" * 64)
    assert after.redaction_regions == [{"source": "auto", "box": [0, 0, 5, 5]}]


def test_only_the_rungs_the_bound_can_spend_are_ever_spent() -> None:
    """`_retry_or_exhaust` re-enqueues only while `attempts < MAX_ATTEMPTS`, so with three attempts
    the ladder that actually runs is BACKOFF[0] and BACKOFF[1]. The third rung is headroom for a
    raised bound and is pinned here so no commit body, docstring or runbook can describe a
    "30 s / 2 min / 10 min ladder" that never reaches its last rung."""
    assert record.MAX_ATTEMPTS == 3
    assert record.BACKOFF[:record.MAX_ATTEMPTS - 1] == (30, 120)
    assert len(record.BACKOFF) >= record.MAX_ATTEMPTS - 1


def test_the_state_tuples_are_the_states_the_column_check_permits() -> None:
    """Every name in READY_STATES, ERROR_STATES and CLAIMABLE_STATES is one migration 041's CHECK
    accepts, and the three sets say what spec C.4 says about each other: nothing claimable is
    ready, and REVIEW_REQUIRED is an error state the claim may NOT take (its retries are spent and
    only the seller's "Try again" moves it)."""
    assert set(record.READY_STATES).isdisjoint(record.ERROR_STATES)
    assert set(record.CLAIMABLE_STATES).isdisjoint(record.READY_STATES)
    assert set(record.CLAIMABLE_STATES) == set(record.ERROR_STATES) - {"REVIEW_REQUIRED"} | {"UPLOADED"}


def test_a_completed_run_stamps_the_version_it_ran_under(conn: Any) -> None:
    """Spec C.5 step 7. A row created before a version bump and completed after it must not be left
    below the constant: the sweeper would flag it VERSION within five minutes and re-run in place a
    scan that had just been done."""
    asset_id, _ = _row(conn, processing_status="REDACTION_GENERATED", processing_version=1)
    record.mark_ready(conn, asset_id, visible=False, version=4)
    assert _read(conn, asset_id).processing_version == 4


def _review_status(conn: Any, asset_id: UUID) -> str:
    """`seller_review_status` is written by the reset rule and by `confirm` but is not a field of
    `PrivacyRow` (P12's dialog reads it through its own serialiser), so the cases that assert on it
    read the column."""
    with conn.cursor() as cur:
        cur.execute("SELECT seller_review_status FROM listing_asset_privacy WHERE asset_id = %s", (asset_id,))
        return str(cur.fetchone()[0])
