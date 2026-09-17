"""One case per transition of spec 2026-09-09 C.4, and one per dead end.

Directive 6: "No image may silently fall through the state machine." The proof of that is here: a
transition that is not in this table has no function to perform it, and every function refuses from
a state the table does not name."""
from __future__ import annotations

import re
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg2
import pytest

from app.privacy import PROCESSING_VERSION, record

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
    # Task P8's sweeper rule (2): a PROCESSING row older than `LOST_AFTER` is a child that died
    # mid-run. A state and not a flag -- it has no derivative to go on serving.
    ("PROCESSING", "REPROCESS_REQUIRED", "sweep_lost"),
)

# States from which the claim must write NOTHING: a ready row is never re-run by this path (its
# in-place re-run is `advance_in_place`), and a fresh PROCESSING row is another child's work.
UNCLAIMABLE = ("PROCESSING", "SCANNED", "REDACTION_GENERATED", "READY_FOR_REVIEW",
               "SELLER_CONFIRMED", "PUBLISHED", "REVIEW_REQUIRED")

#: Every state migration 041's CHECK permits, read at COLLECTION time -- which is why it is a
#: literal somewhere rather than a database fixture. THE MODULE's own, not a second copy (Task
#: P10): `reset_for_reprocess` is guarded by exactly this tuple, so the dead-end parametrisations
#: below and that writer's predicate cannot disagree about what the eleven states are. It is
#: pinned against `pg_constraint` itself, both ways, by
#: `test_the_state_tuples_are_the_states_the_column_check_permits` -- so a state added to the table
#: without a dead end being ruled for it fails here rather than going unnoticed.
ALL_STATES = record.ALL_STATES

#: Spec C.4 names ONE source per failure state: `PROCESSING -> PROCESSING_FAILED` (a decode,
#: OCR or vision error) and `SCANNED -> REDACTION_FAILED` (the fill or the re-encode). Written as
#: the table's own pairs so the dead ends below are the complement of what the spec names rather
#: than a list somebody typed.
FAIL_TABLE = (("PROCESSING_FAILED", "PROCESSING"), ("REDACTION_FAILED", "SCANNED"))

#: Spec C.4's two `-> REVIEW_REQUIRED` rows: the failure that spends the third attempt
#: (`PROCESSING | SCANNED`) and the third failed IN-PLACE re-run (the three ready states).
EXHAUST_SOURCES = ("PROCESSING", "SCANNED", *record.READY_STATES)


def _forbidden(*sources: str) -> tuple[str, ...]:
    """The complement of a writer's source states, in the CHECK's own order."""
    return tuple(state for state in ALL_STATES if state not in sources)


#: (the state asked for, the state the row is in) for every pair spec C.4 does NOT name.
FAIL_DEAD_ENDS = tuple((state, start) for state, source in FAIL_TABLE for start in _forbidden(source))


def _read(conn: Any, asset_id: UUID) -> record.PrivacyRow:
    """`record.read` answers `PrivacyRow | None`; every call in this file has just written the row
    it is reading, so a None here is the test's own failure and says so at once."""
    found = record.read(conn, asset_id)
    assert found is not None, f"the privacy row for {asset_id} vanished"
    return found


def _all_columns(conn: Any, asset_id: UUID) -> dict[str, Any]:
    """EVERY column of the privacy row, by name -- what a "writes nothing" case must compare.

    `PrivacyRow` is a sixteen-field projection and carries none of `ocr`, `identity_matches`,
    `vision`, `detected_regions`, `last_error`, `seller_review_status`, `detection_at` or
    `updated_at`. A dead-end case that compared the projection would still pass if a guard stopped
    protecting the four `jsonb` columns a late scan must not overwrite and kept protecting the
    status column -- which is precisely the subject of those cases (review Minor-6)."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM listing_asset_privacy WHERE asset_id = %s", (asset_id,))
        found = cur.fetchone()
        assert found is not None, f"the privacy row for {asset_id} vanished"
        return dict(zip([d.name for d in cur.description], found, strict=True))


def _age(conn: Any, asset_id: UUID, *, minutes: int) -> None:
    """The row, moved backwards in time. Every sweeper window and the claim's own lost-child term
    read `updated_at`, which is why every writer in `record.py` sets it explicitly."""
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET updated_at = %s WHERE asset_id = %s",
                    (datetime.now(UTC) - timedelta(minutes=minutes), asset_id))


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
        case "sweep_lost":
            # The WINDOW is part of this transition and not a fixture detail: rule (2) is
            # "PROCESSING for longer than `LOST_AFTER`", so the back-date belongs inside the one
            # call the row names.
            _age(conn, asset_id, minutes=30)
            record.sweep_candidates(conn)
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
    before = _all_columns(conn, asset_id)
    assert record.claim(conn, asset_id, 1) is None
    assert _all_columns(conn, asset_id) == before


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
        before = _all_columns(conn, asset_id)
        record.record_scan(conn, asset_id, ocr={"size": [1, 1], "lines": []}, identity_matches=[],
                           vision={"status": "ok"}, detected_regions=[{"box": [0, 0, 1, 1]}])
        assert _all_columns(conn, asset_id) == before


def test_record_derivative_writes_nothing_from_a_state_that_is_not_scanned(conn: Any) -> None:
    """The key and the hash of a derivative are written once per run, from SCANNED alone. A second
    write from READY_FOR_REVIEW would replace a confirmed row's derivative without the reset."""
    for start in ("UPLOADED", "PROCESSING", "REDACTION_GENERATED", "SELLER_CONFIRMED"):
        asset_id, listing_id = _row(conn, processing_status=start)
        before = _all_columns(conn, asset_id)
        record.record_derivative(conn, asset_id, key=f"listings/{listing_id}/photos/{uuid4()}/redacted.webp",
                                 sha256="f" * 64, regions=[{"source": "auto"}])
        assert _all_columns(conn, asset_id) == before


def test_mark_ready_writes_nothing_from_a_state_without_a_fresh_derivative(conn: Any) -> None:
    """READY_FOR_REVIEW is reached from REDACTION_GENERATED and from nowhere else: a row that
    failed, or one the seller has already confirmed, must not be promoted by the completion step of
    a run that no longer owns it."""
    for start in ("UPLOADED", "PROCESSING", "SCANNED", "SELLER_CONFIRMED", "REVIEW_REQUIRED"):
        asset_id, _ = _row(conn, processing_status=start)
        before = _all_columns(conn, asset_id)
        record.mark_ready(conn, asset_id, visible=True, version=9)
        assert _all_columns(conn, asset_id) == before


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


def _executed_sql(module: Any) -> dict[str, list[str]]:
    """Every `cur.execute(...)` call's SQL in `module`, one string per CALL, keyed by the top-level
    FUNCTION that owns it.

    An AST walk and not a regex over the source: a regex that ends a "statement" at a blank line or
    a docstring quote can span two `execute` calls, and one that contains `updated_at = now()`
    would then hide a neighbour that does not. `ast` gives the call boundary exactly -- and the
    function boundary with it, which is what lets the count below be EXACT per writer instead of a
    floor over the whole module. The literal parts of an f-string are Constants inside the
    JoinedStr, so `{RESET_COLUMNS}` contributes nothing -- which is right: every statement writes
    `updated_at = now()` in its own text, outside that fragment.

    `AsyncFunctionDef` beside `FunctionDef` (re-review 1, N4): `record.py` is psycopg2-sync and flat
    today, so nothing is missed either way, but a planted `async def` writer was invisible to this
    walk and to `_plain_calls` alike -- and a walk that cannot see a writer is exactly what the
    counting pin below exists to prevent.

    EVERY function, not only the module's top-level ones (re-review 2, Minor-2). The walk used to
    read `ast.parse(...).body`, so a writer nested in a CLASS body was invisible to all three pins
    at once -- a planted `class _PlantedSweeper` whose method issued an unguarded
    `UPDATE listing_asset_privacy SET last_error = NULL WHERE asset_id = %s` left this suite and
    `tests/test_docs.py` entirely green. "Assert the module declares no classes" was the cheaper
    alternative and is NOT this module's contract: `record.py` declares `PrivacyRow`. So the walk
    widens instead, and a class-nested writer is now counted, predicate-checked and
    `updated_at`-checked like any other.

    Each `execute` is attributed to its NEAREST enclosing function rather than to every function
    that encloses it, so a nested `def` cannot make one statement count twice. Nothing in
    `record.py` nests today; the count this pin makes exact is worth keeping exact."""
    import ast
    import inspect

    def owned(node: Any) -> list[str]:
        """The `execute` SQL this node owns, stopping at any nested function's boundary."""
        out: list[str] = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue     # the walk below reaches it as an owner in its own right
            if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "execute" and child.args):
                out.append(" ".join(piece.value for piece in ast.walk(child.args[0])
                                    if isinstance(piece, ast.Constant) and isinstance(piece.value, str)))
            out.extend(owned(child))
        return out

    found: dict[str, list[str]] = {}
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sql in owned(node):
            found.setdefault(node.name, []).append(sql)
    return found


def _plain_calls(module: Any, function: str) -> set[str]:
    """The names of the plain-function calls one function of `module` makes -- a `read(...)` but
    not a `cur.execute(...)`, and never a word that only appears in a docstring, which is why this
    is an AST walk and not a substring search over the source.

    `ast.walk`, so a function reaches this whether it is `def` or `async def` and whether it sits
    at the module's top level or in a class body -- the same widening `_executed_sql` takes, for
    the same reason (re-review 1 N4, re-review 2 Minor-2)."""
    import ast
    import inspect

    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
            return {call.func.id for call in ast.walk(node)
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)}
    pytest.fail(f"{module.__name__} declares no function {function}")


def _privacy_updates(module: Any) -> dict[str, list[str]]:
    """`_executed_sql`, narrowed to the statements that UPDATE the privacy row."""
    narrowed = {name: [sql for sql in sqls if "UPDATE listing_asset_privacy" in sql]
                for name, sqls in _executed_sql(module).items()}
    return {name: sqls for name, sqls in narrowed.items() if sqls}


#: Every function of `app/privacy/record.py` that UPDATEs the privacy row, and how many statements
#: it owns -- `reset_confirmation` has two because the seller's own region set is written in the
#: SAME statement as the transition, so the arm that carries regions is a second statement rather
#: than a second write.
#:
#: Review Minor-8: the count was `assert len(updates) >= 8` where the module had fourteen, a floor
#: loose enough that six statements could be lost without the sanity check noticing. This is exact
#: and pinned BOTH ways against the walk, so a writer added without a row here -- or a writer lost
#: -- fails rather than passing quietly.
PRIVACY_UPDATES = {
    "claim": 1,
    "record_scan": 1,
    "record_scan_in_place": 1,
    "record_derivative": 1,
    "mark_ready": 1,
    "fail": 1,
    "exhaust": 1,
    "confirm": 1,
    "reset_confirmation": 2,
    "reset_for_retry": 1,
    "flag_stale": 1,
    "flag_stale_version": 1,
    # Task P8's sweeper. Rule (2)'s lost-child transition is ONE statement that both finds the row
    # and moves it; rule (5)'s version flag is `flag_stale_version`'s, shared with
    # `scripts/reprocess_photos.py --all-stale`. The other four rules only SELECT and are counted
    # by nothing here, which is right -- they write nothing.
    "sweep_candidates": 1,
    "advance_in_place": 1,
    "bump_attempt": 1,
    "mark_published": 1,
    "set_visibility": 1,
    "reset_for_reprocess": 1,
}


#: Writers whose statement deliberately carries NO `processing_status` predicate at all, each named
#: with the reason it is safe without one. **Empty today, and that is the point**: every one of
#: `record.py`'s fifteen privacy UPDATEs names the column in its own WHERE, so the assertion below
#: has no exception to grant. The door exists so that a writer which genuinely needs none has to be
#: declared here in one line -- rather than slipping through as the omission `fail`, `exhaust` and
#: `advance_in_place` slipped through as, which is the whole of the fix round's Important-1.
UNGUARDED_UPDATES: dict[str, str] = {}

#: The one writer whose predicate is CONDITIONAL rather than a plain state test, declared by name
#: so no reader has to discover it (re-review N2). It is NOT exempt from the assertion below -- it
#: names the column in its own WHERE like every other statement -- and what the ternary around that
#: name does is something no assertion over a statement's TEXT can read, which is why it is said
#: here in words instead.
CONDITIONAL_GUARDS = {
    "set_visibility": (
        "the GRANT arm is gated on READY_STATES, because `lap_visible_ready_ck` would refuse the "
        "write outright and a flip that raised on one photograph would abandon the rest of the "
        "listing; the WITHDRAW arm is unconditional, because hiding is always safe (spec C.1 "
        "step 4). So the predicate is `(NOT %s OR processing_status = ANY(%s))`, a ternary."
    ),
}


def _where_clause(sql: str) -> str:
    """A statement's WHERE clause and nothing else: everything after the first `WHERE`, stopped at
    `RETURNING`. The empty string when there is no WHERE at all -- a whole-table UPDATE, which the
    caller reads as "no predicate" exactly as it reads a WHERE that names no state."""
    if "WHERE" not in sql:
        return ""
    return sql.split("WHERE", 1)[1].split("RETURNING", 1)[0]


def test_every_update_in_the_module_names_the_state_it_is_allowed_from() -> None:
    """The STRUCTURAL half of the module docstring's "every writer carries a state predicate".

    Until this pin that sentence was enforced only by hand-written dead-end cases -- the same
    enumeration that missed three of fourteen writers and produced the fix round's Important-1,
    where `fail` on a confirmed row raised a `CheckViolation` out of a task contracted never to
    raise. `PRIVACY_UPDATES` below counts statements and says nothing about what is in them, so a
    writer that lost its predicate stayed green there (re-review N2, reproduced by deleting
    `bump_attempt`'s).

    What is asserted is the weakest thing that is still load-bearing and that a statement's text
    can carry honestly: every counted UPDATE has a WHERE, and that WHERE names `processing_status`.
    It cannot tell a right predicate from a wrong one -- the per-transition and dead-end cases are
    what do that, against a real database -- but it can tell a predicate from NONE, which is the
    failure that actually happened.

    The scan is the WHERE CLAUSE PROPER and stops at `RETURNING` (re-review 2, Minor-1). Reading
    the whole tail let a statement satisfy this by NAMING the column in what it gives BACK:
    `… WHERE asset_id = %s RETURNING attempts, processing_status`, with no predicate whatsoever,
    passed. No writer in `record.py` takes that shape today -- `claim` is the only one whose
    RETURNING carries the column and it reaches it through the f-string `{_COLUMNS}`, which the
    walk drops -- so the exposure was a FUTURE writer that returns the row it moved, P8's sweeper
    among them. That is the one this pin most needs to catch."""
    by_function = _privacy_updates(record)
    assert by_function, "the walk found no privacy UPDATEs at all"
    missing = [
        f"{name}: {sql[:120]}"
        for name, sqls in by_function.items() if name not in UNGUARDED_UPDATES
        for sql in sqls
        if "processing_status" not in _where_clause(sql)
    ]
    assert missing == [], missing
    declared = set(UNGUARDED_UPDATES) | set(CONDITIONAL_GUARDS)
    stale = sorted(declared - set(by_function))
    assert stale == [], f"declared for writers this module no longer has: {stale}"
    for name, reason in (UNGUARDED_UPDATES | CONDITIONAL_GUARDS).items():
        assert len(reason) > 40, f"{name}'s reason says nothing useful"


def test_every_update_in_the_module_sets_updated_at() -> None:
    """The sweeper's age windows and `listing_asset_privacy_sweep_idx` read `updated_at`, and there
    is no trigger precedent in `migrations/` -- `listing.updated_at` is maintained the same way, by
    hand, in `app/api/seller_listings.py`. A statement that forgets it makes a row invisible to the
    sweeper for ever, so the rule is checked rather than trusted (spec C.3).

    WHAT THIS WALK CANNOT SEE, stated rather than left to be discovered (re-review 3, Minor-c; Task
    P8 closed it on entry): `_executed_sql` keys every statement by the FUNCTION that owns it, so a
    statement at MODULE level -- outside any `def`, executed at import -- is counted by nothing
    here, and would therefore escape this count, the `updated_at` rule and
    `test_every_update_in_the_module_names_the_state_it_is_allowed_from`'s predicate rule alike.
    That is acceptable for `record.py` specifically, and for two reasons rather than one. First,
    the module opens NO connection and holds no cursor: every statement it runs is run through a
    `conn` its caller passed, so a module-level `cur.execute` would need a module-level connection
    this file has never had and whose addition is not a subtle edit. Second, EXISTENCE is still
    caught elsewhere -- `tests/test_docs.py::test_every_writer_of_the_privacy_row_is_declared_and_
    only_one_is_production` regexes the file's TEXT, not its AST, so a module-level writer is seen
    there whatever encloses it. What would genuinely escape is the PREDICATE check, which is why
    this is written down: a module-level writer in `record.py` is a finding, not a style, and the
    walk is to be widened rather than the statement explained."""
    by_function = _privacy_updates(record)
    assert {name: len(sqls) for name, sqls in by_function.items()} == PRIVACY_UPDATES
    missing = [sql[:120] for sqls in by_function.values() for sql in sqls
               if "updated_at = now()" not in sql]
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


@pytest.mark.parametrize("start", ALL_STATES)
def test_the_reprocess_reset_starts_any_state_again_and_leaves_it_fail_closed(
    conn: Any, start: str
) -> None:
    """P10's SHOW -> NOT_SHOW arm (spec C.1 step 3), from every state the table names.

    The flip meets a row in any of the eleven -- a READY_FOR_REVIEW row whose derivative somebody
    deleted off the bucket is exactly as unservable as an UPLOADED one -- so `ALL_STATES` IS this
    transition, and what the parametrisation asserts is that the landing is fail-closed from each:
    UPLOADED, no derivative claim, no confirmation, invisible, and the ladder's budget back."""
    asset_id, _ = _row(conn, processing_status=start, attempts=2,
                       confirmed=start == "SELLER_CONFIRMED", buyer_visible=start in record.READY_STATES)
    record.reset_for_reprocess(conn, asset_id)
    after = _read(conn, asset_id)
    assert after.processing_status == "UPLOADED"
    assert (after.redacted_storage_key, after.redacted_sha256, after.confirmed_sha256) == (None, None, None)
    assert (after.seller_confirmed, after.buyer_visible, after.attempts) == (False, False, 0)
    assert _review_status(conn, asset_id) == "pending"


def test_the_reprocess_reset_clears_the_stale_flag_a_fresh_run_supersedes(conn: Any) -> None:
    """D-IDP-16: `reprocess_reason` is a flag on a READY row awaiting an IN-PLACE re-run, and
    `advance_in_place` is the only writer that clears it -- nothing on the fresh `claim` ->
    `mark_ready` path ever reaches that function. A row sent back to UPLOADED still carrying one
    would come back READY_FOR_REVIEW and STALE for ever, which the publishing gate's own third arm
    reads as an offender. Both columns move together: `lap_stale_ck` holds
    `(reprocess_reason IS NULL) = (reprocess_requested_at IS NULL)`."""
    asset_id, _ = _row(conn, processing_status="SELLER_CONFIRMED", confirmed=True,
                       buyer_visible=True, reprocess_reason="VERSION")
    record.reset_for_reprocess(conn, asset_id)
    assert _read(conn, asset_id).reprocess_reason is None
    with conn.cursor() as cur:
        cur.execute("SELECT reprocess_requested_at FROM listing_asset_privacy WHERE asset_id = %s",
                    (asset_id,))
        assert cur.fetchone()[0] is None, "lap_stale_ck's other half"


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


def _permitted_states(conn: Any) -> set[str]:
    """The states migration 041's own CHECK on `processing_status` permits, read from
    `pg_constraint`.

    Selected by its COLUMN -- a `conkey` of length one naming `processing_status` -- and never by
    name: three other CHECKs on this table mention the column (`lap_status_confirmed_ck`,
    `lap_visible_ready_ck`, `lap_ready_has_derivative_ck`), and the column check itself is unnamed
    in `041` and carries whatever name PostgreSQL gave it."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
            "  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]"
            " WHERE c.conrelid = 'listing_asset_privacy'::regclass AND c.contype = 'c'"
            "   AND array_length(c.conkey, 1) = 1 AND a.attname = 'processing_status'"
        )
        found = cur.fetchall()
    assert len(found) == 1, f"expected one column CHECK on processing_status, found {found}"
    return set(re.findall(r"'([A-Z_]+)'::text", str(found[0][0])))


def test_the_state_tuples_are_the_states_the_column_check_permits(conn: Any) -> None:
    """Every name in READY_STATES, ERROR_STATES and CLAIMABLE_STATES is one migration 041's CHECK
    accepts, and the three sets say what spec C.4 says about each other: nothing claimable is
    ready, and REVIEW_REQUIRED is an error state the claim may NOT take (its retries are spent and
    only the seller's "Try again" moves it).

    Review Minor-5: the first sentence of that promise used to be performed by nothing -- the body
    asserted set relations among the tuples and read no CHECK at all, so "one migration 041's CHECK
    accepts" was true by inspection rather than by test. The CHECK is read here, and pinned BOTH
    ways: `ALL_STATES`, which every dead-end parametrisation above is the complement of, IS the
    CHECK's own list, and every state the CHECK permits is one this module names -- so a state
    added to `041` without a transition or a dead end ruled for it fails here."""
    import inspect

    permitted = _permitted_states(conn)
    assert set(ALL_STATES) == permitted
    named = set(record.READY_STATES) | set(record.ERROR_STATES) | set(record.CLAIMABLE_STATES)
    assert named <= permitted, sorted(named - permitted)
    source = inspect.getsource(record)
    unnamed = sorted(state for state in permitted if state not in source)
    assert unnamed == [], f"041 permits states app/privacy/record.py never names: {unnamed}"
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


def test_the_failure_states_and_their_sources_are_the_tables_own() -> None:
    """Spec C.4 pairs each failure state with ONE source, and `fail` routes by the state it is
    asked to write rather than admitting the union of the two -- otherwise a re-encode error could
    move a PROCESSING row and a decode error a SCANNED one, neither of which is a row of the
    table."""
    assert record.FAIL_SOURCES == {state: (source,) for state, source in FAIL_TABLE}
    assert record.EXHAUST_SOURCES == EXHAUST_SOURCES


@pytest.mark.parametrize(("state", "start"), FAIL_DEAD_ENDS)
def test_the_failure_writes_nothing_from_a_state_the_table_does_not_pair_it_with(
    conn: Any, state: str, start: str
) -> None:
    """The dead ends `fail` had none of. Unguarded, `fail(..., state="PROCESSING_FAILED")` on a
    ready row moved it out of its ready state WITHOUT the reset rule, and the row is then a
    `buyer_visible` non-ready row -- which `lap_visible_ready_ck` refuses, so psycopg2 raised a
    CheckViolation from inside a task spec C.5 contracts never to raise."""
    asset_id, _ = _row(conn, processing_status=start, attempts=2)
    before = _all_columns(conn, asset_id)
    assert record.fail(conn, asset_id, state=state, code="UNDECODABLE") == 0
    assert _all_columns(conn, asset_id) == before


def test_the_failure_refuses_a_buyer_visible_row_rather_than_raising(conn: Any) -> None:
    """The hazard in its own case, on the shape that produced it: a confirmed, buyer-visible row.
    `media.process_photo` "never raises" (spec C.5) -- every outcome is a state write plus a
    returned summary -- so a failure the state forbids is a refused no-op and not an exception
    escaping the task."""
    asset_id, _ = _row(conn, processing_status="SELLER_CONFIRMED", confirmed=True,
                       buyer_visible=True, attempts=2)
    before = _all_columns(conn, asset_id)
    assert record.fail(conn, asset_id, state="PROCESSING_FAILED", code="UNDECODABLE") == 0
    assert _all_columns(conn, asset_id) == before


def test_a_failure_state_the_table_does_not_name_at_all_writes_nothing(conn: Any) -> None:
    """`FAIL_SOURCES` is asked for the state's sources and answers the empty tuple for one it does
    not hold, which matches no row: fail-closed, and never a KeyError inside the task."""
    asset_id, _ = _row(conn, processing_status="PROCESSING", attempts=2)
    before = _all_columns(conn, asset_id)
    assert record.fail(conn, asset_id, state="REVIEW_REQUIRED", code="OCR_ERROR") == 0
    assert _all_columns(conn, asset_id) == before


@pytest.mark.parametrize("start", _forbidden(*EXHAUST_SOURCES))
def test_the_exhaustion_writes_nothing_from_a_state_the_table_does_not_name(
    conn: Any, start: str
) -> None:
    """Review Minor-1. Unguarded, `exhaust` admitted `UPLOADED`, `REDACTION_GENERATED`,
    `PROCESSING_FAILED`, `REDACTION_FAILED`, `REVIEW_REQUIRED` and `REPROCESS_REQUIRED` ->
    `REVIEW_REQUIRED`, none of which is a row of spec C.4. It fails closed, so nothing could raise
    -- but a transition the table does not name is still a transition the table does not name."""
    asset_id, _ = _row(conn, processing_status=start, attempts=3)
    before = _all_columns(conn, asset_id)
    assert record.exhaust(conn, asset_id, code="OCR_ERROR") == 0
    assert _all_columns(conn, asset_id) == before


@pytest.mark.parametrize("start", EXHAUST_SOURCES)
def test_the_exhaustion_reports_the_one_row_it_moved(conn: Any, start: str) -> None:
    asset_id, _ = _row(conn, processing_status=start, buyer_visible=start in record.READY_STATES,
                       attempts=3)
    assert record.exhaust(conn, asset_id, code="OCR_ERROR") == 1
    assert _read(conn, asset_id).processing_status == "REVIEW_REQUIRED"


@pytest.mark.parametrize("start", _forbidden(*record.READY_STATES))
def test_the_in_place_advance_writes_nothing_from_a_state_that_is_not_ready(
    conn: Any, start: str
) -> None:
    """The in-place re-run is a READY row's re-run and nothing else (spec C.5, D-IDP-16).
    Unguarded, `advance_in_place` set a derivative hash and cleared the stale flag from ANY state,
    including `UPLOADED` and `REVIEW_REQUIRED`, where it wrote a `redacted_sha256` beside a NULL
    `redacted_storage_key` -- a shape `lap_ready_has_derivative_ck` does not constrain outside the
    ready states, so nothing in the database refused it."""
    asset_id, _ = _row(conn, processing_status=start, attempts=2)
    before = _all_columns(conn, asset_id)
    assert record.advance_in_place(conn, asset_id, sha256="e" * 64, version=9, regions=[]) == 0
    assert _all_columns(conn, asset_id) == before


def test_the_in_place_advance_reports_the_one_row_it_moved(conn: Any) -> None:
    asset_id, _ = _row(conn, processing_status="PUBLISHED", confirmed=True, buyer_visible=True,
                       reprocess_reason="VERSION")
    assert record.advance_in_place(conn, asset_id, sha256="e" * 64, version=2, regions=[]) == 1


def test_the_in_place_re_runs_failure_counts_an_attempt_without_leaving_the_ready_state(
    conn: Any,
) -> None:
    """Spec C.5: "A failed in-place run counts an attempt and re-enqueues". `claim` refuses the
    three ready states by design, so a flagged ready row's re-run has no other way to count one --
    and `fail` is the wrong instrument, because it would move a PUBLISHED row out of its ready
    state and darken a live listing, which D-IDP-16 forbids ("a version bump darkens no
    listing")."""
    for start in record.READY_STATES:
        asset_id, _ = _row(conn, processing_status=start, confirmed=start == "SELLER_CONFIRMED",
                           buyer_visible=True, reprocess_reason="VERSION")
        assert record.bump_attempt(conn, asset_id) == 1
        after = _read(conn, asset_id)
        assert (after.processing_status, after.attempts) == (start, 1)
        assert after.buyer_visible, "a counted attempt darkens no listing"
        assert after.reprocess_reason == "VERSION", "the flag survives; only the re-run clears it"
        assert record.bump_attempt(conn, asset_id) == 2


def test_the_counted_attempt_indexes_the_ladder_the_caller_spends(conn: Any) -> None:
    """`bump_attempt` returns the NEW count, which is what P8 reads against `MAX_ATTEMPTS` and what
    indexes `BACKOFF`: the first failure spends `BACKOFF[0]`, the second `BACKOFF[1]`, and the
    third does not re-enqueue at all -- it exhausts. The ladder is read from the module here rather
    than re-typed, so a changed rung moves this case with it."""
    asset_id, _ = _row(conn, processing_status="PUBLISHED", buyer_visible=True,
                       reprocess_reason="OPERATOR")
    counted = [record.bump_attempt(conn, asset_id) for _ in range(record.MAX_ATTEMPTS)]
    assert counted == [1, 2, 3]
    spent = [record.BACKOFF[n - 1] for n in counted if n < record.MAX_ATTEMPTS]
    assert spent == [30, 120]
    assert counted[-1] == record.MAX_ATTEMPTS, "the third failure exhausts rather than re-enqueueing"


@pytest.mark.parametrize("start", _forbidden(*record.READY_STATES))
def test_no_attempt_is_counted_from_a_state_no_in_place_re_run_owns(conn: Any, start: str) -> None:
    """None, not 0: a row whose state forbids the count wrote nothing, and a caller that read a 0
    as "the first attempt" would spend `BACKOFF[-1]` -- the 10-minute rung the bound never reaches
    -- on a row it never touched. Every claimable state is here too, because the CLAIM counts that
    attempt itself and a second count would spend the ladder twice as fast."""
    asset_id, _ = _row(conn, processing_status=start, attempts=1)
    before = _all_columns(conn, asset_id)
    assert record.bump_attempt(conn, asset_id) is None
    assert _all_columns(conn, asset_id) == before


@pytest.mark.parametrize("start", [s for s in ALL_STATES if s != "PROCESSING"])
def test_the_sweepers_lost_child_rule_moves_nothing_from_any_other_state(conn: Any, start: str) -> None:
    """Rule (2)'s dead ends. It is the sweeper's only STATE transition, and an unguarded version of
    it would take a SCANNED row mid-encode, a REVIEW_REQUIRED row the seller has not touched and a
    PUBLISHED row's whole listing back to the queue every five minutes for ever."""
    asset_id, _ = _row(conn, processing_status=start)
    _age(conn, asset_id, minutes=60)
    before = _all_columns(conn, asset_id)
    record.sweep_candidates(conn)
    after = _all_columns(conn, asset_id)
    # `flag_stale_version` legitimately marks a ready row below the version; nothing else may move.
    assert after["processing_status"] == before["processing_status"]
    assert after["last_error"] == before["last_error"]


def test_the_lost_child_rule_waits_out_its_window(conn: Any) -> None:
    """The window is the whole difference between "a worker is busy with this" and "a worker died
    with this". Inside it the row is left alone; outside it the row is taken back."""
    asset_id, _ = _row(conn, processing_status="PROCESSING", attempts=1)
    _age(conn, asset_id, minutes=5)
    assert record.sweep_candidates(conn)["lost"] == []
    assert _read(conn, asset_id).processing_status == "PROCESSING"
    _age(conn, asset_id, minutes=7)
    assert record.sweep_candidates(conn)["lost"] == [asset_id]
    assert _read(conn, asset_id).processing_status == "REPROCESS_REQUIRED"


def test_the_version_flag_marks_a_stale_ready_row_once_and_leaves_its_state_alone(conn: Any) -> None:
    """Rule (5), and `scripts/reprocess_photos.py --all-stale`'s own statement. Staleness is a FLAG
    (D-IDP-16): the row keeps its state, its confirmation and its visibility, and goes on serving
    the derivative it has while the in-place re-run replaces it.

    Idempotent, which is what stops five minutes of sweeps enqueueing five re-runs of one
    photograph: a row that already carries a reason is not re-stamped."""
    stale, _ = _row(conn, processing_status="PUBLISHED", processing_version=0, buyer_visible=True)
    current, _ = _row(conn, processing_status="PUBLISHED", processing_version=PROCESSING_VERSION,
                      buyer_visible=True)
    not_ready, _ = _row(conn, processing_status="PROCESSING_FAILED", processing_version=0)
    assert record.flag_stale_version(conn, reason="VERSION") == [stale]
    after = _read(conn, stale)
    assert (after.processing_status, after.buyer_visible, after.reprocess_reason) == ("PUBLISHED", True, "VERSION")
    assert _read(conn, current).reprocess_reason is None
    assert _read(conn, not_ready).reprocess_reason is None
    assert record.flag_stale_version(conn, reason="OPERATOR") == []
    assert _read(conn, stale).reprocess_reason == "VERSION", "a flagged row was re-stamped"


def test_the_in_place_scan_writes_its_columns_without_touching_the_state(conn: Any) -> None:
    """`record_scan`'s twin for the re-run: the four scan columns, and no transition at all."""
    asset_id, _ = _row(conn, processing_status="SELLER_CONFIRMED", confirmed=True, buyer_visible=True)
    record.record_scan_in_place(conn, asset_id, ocr={"size": [800, 600], "lines": []},
                                identity_matches=[{"field": "name", "line": 0, "method": "exact", "score": 1.0}],
                                vision={"status": "unavailable"}, detected_regions=[{"source": "vision"}])
    row = _all_columns(conn, asset_id)
    assert (row["processing_status"], row["buyer_visible"]) == ("SELLER_CONFIRMED", True)
    assert row["identity_matches"] == [{"field": "name", "line": 0, "method": "exact", "score": 1.0}]
    assert row["detected_regions"] == [{"source": "vision"}]
    assert row["vision"] == {"status": "unavailable"}


@pytest.mark.parametrize("start", [s for s in ALL_STATES if s not in record.READY_STATES])
def test_the_in_place_scan_writes_nothing_from_a_state_that_is_not_ready(conn: Any, start: str) -> None:
    """Its dead ends. An in-place re-run happens in a ready state and nowhere else, so a row that
    stopped being ready mid-run must not have a late scan written over the one its own run
    recorded -- the four `jsonb` columns are exactly what `_all_columns` exists to compare."""
    asset_id, _ = _row(conn, processing_status=start)
    before = _all_columns(conn, asset_id)
    record.record_scan_in_place(conn, asset_id, ocr={"size": [1, 1], "lines": []}, identity_matches=[],
                                vision={"status": "ok"}, detected_regions=[{"source": "ocr_match"}])
    assert _all_columns(conn, asset_id) == before


def test_the_claim_is_one_statement_that_returns_the_row_it_claimed() -> None:
    """Review Minor-4. `app/db.py:239`'s `sync_conn()` is AUTOCOMMIT, so a claim that is an UPDATE
    followed by a separate `read()` COMMITS between the two and hands the caller a second snapshot
    -- one another connection may already have moved on -- rather than the row it claimed. The
    whole point of a compare-and-set is that what it returns is what it wrote, so the claim is ONE
    `UPDATE ... RETURNING` over the read's own column list and calls `read` not at all.

    Structural, because the window it closes is between two statements and cannot be driven shut
    from outside: what is asserted is that there is no second statement to have a window with."""
    statements = _executed_sql(record)["claim"]
    assert len(statements) == 1, statements
    sql = statements[0]
    assert sql.startswith("UPDATE listing_asset_privacy"), sql[:80]
    assert "RETURNING" in sql, "the claim answers with nothing of its own"
    assert "read" not in _plain_calls(record, "claim"), "the claim re-reads instead of returning"


def test_the_claimed_row_is_the_full_record_and_not_a_narrower_one(conn: Any) -> None:
    """The other half of the case above: one statement is only worth having if it answers with the
    WHOLE row. The claim's `RETURNING` is the read's own column list, which this proves by
    comparing the claimed row with a read of it -- every field, through `PrivacyRow`'s equality,
    including the two joined off `listing_asset` that a bare `RETURNING` could not reach at all."""
    asset_id, _ = _row(conn, processing_status="UPLOADED")
    claimed = record.claim(conn, asset_id, 1)
    assert claimed is not None
    assert claimed == _read(conn, asset_id)
    assert (claimed.processing_status, claimed.attempts) == ("PROCESSING", 1)
    assert claimed.display_storage_key is not None and claimed.display_sha256 == "d" * 64


def _wait_for_a_blocked_backend(conn: Any, seconds: float = 20.0) -> None:
    """Block until another backend on this database is waiting on a lock.

    Without it the racing thread might not have issued its UPDATE before the holder claims and
    commits, and the case would pass having proved nothing about concurrency -- the same outcome
    reached sequentially."""
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                        " AND wait_event_type = 'Lock'")
            if int(cur.fetchone()[0]) >= 1:
                return
        time.sleep(0.02)
    pytest.fail("the racing claim never reached the row lock; the race was not driven")


def test_two_connections_claiming_one_row_leave_exactly_one_winner(conn: Any, scratch_dsn: str) -> None:
    """The compare-and-set as a RACE and not only as a predicate (review §3): two connections with
    their statements in flight at the same instant, and exactly one of them claims.

    The interleaving is forced rather than hoped for -- the holder takes the row with
    `SELECT ... FOR UPDATE`, the racer's UPDATE then blocks on that lock, and the holder claims and
    commits underneath it. When the lock is released PostgreSQL re-evaluates the racer's WHERE
    against the row as it now is (READ COMMITTED), finds it PROCESSING with a fresh `updated_at`,
    and matches nothing. That is exactly what a duplicate message and a redelivered task do."""
    asset_id, _ = _row(conn, processing_status="UPLOADED")
    holder = psycopg2.connect(scratch_dsn)   # NOT autocommit: it holds the row while the racer waits
    answers: dict[str, record.PrivacyRow | None] = {}
    escaped: list[psycopg2.Error] = []

    def race() -> None:
        """The racing claim, owning its connection from open to close and swallowing NOTHING.

        The connection is opened AND closed in here (re-review 2, Minor-3): nothing outside this
        thread can close it, and the scratch database's `DROP ... WITH (FORCE)` cannot terminate a
        backend this thread is still using, because the `finally` below has run before the test
        returns. And a DATABASE error does not ESCAPE this thread: one that does reaches pytest
        through its `threadexception` hook as a `PytestUnhandledThreadExceptionWarning`, which
        `-W error` promotes to an error on whichever test happens to be running when it lands --
        the NEXT test's setup, once this one has returned, which is worse to read than the failure
        it is attached to. It is recorded instead, and the test asserts on it below, in its own
        name. `psycopg2.Error` and not a blind `Exception`: that is the whole class this finding is
        about (`OperationalError: server closed the connection unexpectedly`, `InterfaceError:
        connection already closed`), and a bug in `record.claim` itself is not a masking error --
        it is one pytest SHOULD surface however loudly it can.

        The CONNECT is inside the `try` too (re-review 3, Minor-b; Task P8 closed it on entry).
        It used to sit above it, so the one `psycopg2.Error` most likely of all -- the connection
        itself failing -- was the one error this arm could not record, and it escaped as exactly
        the `PytestUnhandledThreadExceptionWarning` the paragraph above exists to prevent.
        Reproduced by pointing this connect at a closed port: one `-W error` run reported the case
        FAILED and errored a second time in the same run, two reports for one cause."""
        racer: Any = None
        try:
            racer = psycopg2.connect(scratch_dsn)
            racer.autocommit = True
            answers["racer"] = record.claim(racer, asset_id, 1)
        except psycopg2.Error as exc:
            escaped.append(exc)
        finally:
            # `None` when the connect itself was what failed: there is nothing to close, and a
            # bare `racer.close()` would raise an AttributeError over the error just recorded.
            if racer is not None:
                racer.close()

    # Built before the `try`, so the `finally` can always ask whether it is still running -- a
    # `finally` that cannot name the thread is the same defect one step further out.
    thread = threading.Thread(target=race)
    try:
        with holder.cursor() as cur:
            cur.execute("SELECT attempts FROM listing_asset_privacy WHERE asset_id = %s FOR UPDATE",
                        (asset_id,))
        thread.start()
        _wait_for_a_blocked_backend(conn)
        answers["holder"] = record.claim(holder, asset_id, 1)
        holder.commit()
    finally:
        # The lock goes FIRST, so a racer blocked on it finishes in milliseconds, and only then do
        # we wait -- the thread owns its own connection, so there is nothing here to close.
        holder.close()
        # ONLY a thread that was started (re-review 3, Minor-a; Task P8 closed it on entry).
        # `Thread.join` raises `RuntimeError: cannot join thread before it is started`, and this
        # `finally` runs for every way the body above can fail -- including the ways that fail
        # BEFORE `thread.start()`, such as the row lock itself. Reproduced by raising one line
        # above `start()`: the real error was reported only as "During handling of the above
        # exception, another exception occurred" behind a `RuntimeError` about joining.
        if thread.ident is not None:
            thread.join(timeout=30)
    assert not thread.is_alive(), (
        "the racing claim did not return within 30 s of the lock being released; its connection is "
        "the thread's own, so nothing here has closed it and no second error is masking this one"
    )
    assert escaped == [], f"the racing claim raised instead of answering: {escaped}"
    assert set(answers) == {"holder", "racer"}, answers
    won = [row for row in answers.values() if row is not None]
    assert len(won) == 1, f"both connections claimed the same row: {answers}"
    assert (won[0].processing_status, won[0].attempts) == ("PROCESSING", 1)
    assert _read(conn, asset_id).attempts == 1, "the loser counted an attempt it never made"


def test_the_builder_makes_both_confirmation_sides_against_the_derivative_it_serves(conn: Any) -> None:
    """Review Minor-7, on the shared builder P7-P13 all import.

    Two shapes it could not make. A confirmation is always recorded as NOT_SHOW, so P10's flip --
    whose predicate is `seller_confirmed AND final_privacy_state = 'NOT_SHOW'` -- had no way to
    build the OTHER side of it; and `confirmed=True` on a state outside the four derivative states
    wrote `confirmed_sha256` beside a NULL `redacted_sha256`, a shape `lap_confirmed_ck` admits
    only through three-valued logic (`NULL = NULL` is NULL, and a CHECK passes on NULL) and which
    no real row ever has. A confirmed row now carries the derivative its confirmation covers,
    whatever state it is in, which is what `lap_confirmed_ck` says a confirmation IS; a case that
    wants the other shape asks for it explicitly, by poking the column, as
    `test_confirm_refuses_a_ready_row_that_has_no_derivative_hash` does."""
    for side in ("NOT_SHOW", "SHOW"):
        asset_id, _ = _row(conn, processing_status="SELLER_CONFIRMED", confirmed=True,
                           buyer_visible=True, final_privacy_state=side)
        after = _read(conn, asset_id)
        assert after.final_privacy_state == side
        assert after.seller_confirmed and after.confirmed_sha256 is not None
        assert after.confirmed_sha256 == after.redacted_sha256
    failed, _ = _row(conn, processing_status="REDACTION_FAILED", confirmed=True)
    stale = _read(conn, failed)
    assert stale.confirmed_sha256 is not None
    assert stale.confirmed_sha256 == stale.redacted_sha256
    assert stale.redacted_storage_key is not None
