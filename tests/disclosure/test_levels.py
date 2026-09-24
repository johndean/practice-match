# tests/disclosure/test_levels.py
"""The disclosure-level vocabulary (directive §16): six named capabilities, what
FULL_CONFIDENTIAL covers, and which capability an uploaded document's `kind` requires."""
from __future__ import annotations

import re
from typing import Any

from app.disclosure import levels


def test_the_five_specific_capabilities_are_each_self_covering() -> None:
    for capability in ("IDENTITY", "EXACT_LOCATION", "UNREDACTED_IMAGES", "FINANCIALS", "FLOOR_PLANS"):
        assert levels.covers(capability) == frozenset({capability})


def test_full_confidential_covers_every_specific_capability() -> None:
    assert levels.covers("FULL_CONFIDENTIAL") == levels.CAPABILITIES


def test_no_level_and_an_unknown_level_cover_nothing() -> None:
    assert levels.covers(None) == frozenset()
    assert levels.covers("NOT_A_LEVEL") == frozenset()


def test_requestable_levels_is_the_five_capabilities_plus_full_confidential() -> None:
    assert levels.REQUESTABLE_LEVELS == levels.CAPABILITIES | frozenset({"FULL_CONFIDENTIAL"})
    assert "PUBLIC" not in levels.REQUESTABLE_LEVELS  # nothing is ever requested/granted FOR the public tier — it needs no grant


def test_document_kind_maps_to_its_own_capability() -> None:
    assert levels.capability_for_document_kind("floor_plan") == "FLOOR_PLANS"
    assert levels.capability_for_document_kind("financials") == "FINANCIALS"


def test_an_undifferentiated_document_kind_requires_the_broadest_grant() -> None:
    # directive §19, applied to the one case the product cannot yet classify (D18 — no kind
    # picker exists, so every wizard upload is 'other' today).
    assert levels.capability_for_document_kind("equipment") == "FULL_CONFIDENTIAL"
    assert levels.capability_for_document_kind("other") == "FULL_CONFIDENTIAL"


def _permitted_levels(conn: Any, column: str) -> set[str]:
    """The values migration 096's own single-column CHECK on `request.<column>` admits, read
    from `pg_constraint` -- the same idiom `tests/privacy/test_record.py::_permitted_states` uses
    for `listing_asset_privacy.processing_status` -- rather than from the migration file's text,
    so a constraint changed without its Python mirror being re-read fails here rather than being
    trusted by inspection (the exact review finding, "Minor-5", that idiom's own docstring
    records).

    Selected by COLUMN, not by constraint name: `request`'s two disclosure-level columns each
    carry an UNNAMED single-column IN-list CHECK (PostgreSQL names them itself), while the
    table's other four CHECKs either constrain `status` (a different column, same shape) or span
    more than one column (`request_seller_is_not_buyer_ck`,
    `request_approved_needs_decision_ck`, `request_denied_needs_review_ck`,
    `request_pending_has_no_decision_ck`) and are excluded by the
    `array_length(c.conkey, 1) = 1` filter."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
            "  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]"
            " WHERE c.conrelid = 'request'::regclass AND c.contype = 'c'"
            "   AND array_length(c.conkey, 1) = 1 AND a.attname = %s",
            (column,),
        )
        found = cur.fetchall()
    assert len(found) == 1, f"expected one column CHECK on {column}, found {found}"
    return set(re.findall(r"'([A-Z_]+)'::text", str(found[0][0])))


def test_requestable_levels_matches_the_requested_disclosure_level_check(conn: Any) -> None:
    """Migration 096's own comment says `requested_disclosure_level`'s CHECK is "restated" in
    `levels.py` "so Python and the database cannot silently drift apart" -- restating a claim is
    not the same as proving it, so this pins the two lists together, in BOTH directions (set
    equality): every level `levels.py` names is one the column admits, and every value the
    column admits is one `levels.py` names. A level added to only one side fails here instead of
    surfacing later as a 500 (Task 5 inserting a value Postgres refuses) or a silent gap (a value
    Postgres would accept that no route or test has ever heard of)."""
    assert levels.REQUESTABLE_LEVELS == _permitted_levels(conn, "requested_disclosure_level")


# `test_requestable_levels_matches_the_approved_disclosure_level_check` stood here and is RETIRED
# by D-C67 (2026-09-24): migration 097 replaced `approved_disclosure_level` with
# `approved_capabilities`, so there is no such column to read a CHECK from. What it PROVED -- that
# the grant column's admitted values and Python's own list cannot drift apart -- is unchanged and
# is proved by `test_capabilities_matches_the_approved_capabilities_check` at the foot of this
# file, against the column that replaced it and against the narrower set that column admits.


# --- D-C67 (John, 2026-09-24: "all toggles must be fully functional and SELLER must be able to
# manage it all and per seller"): a grant is a SET of capabilities, not one named level. `covers()`
# above is untouched and keeps its own six-value contract -- it is still the one door from the
# BUYER's single requested level to the default grant -- and `granted()` below is the one door from
# what is actually STORED (`request.approved_capabilities`, migration 097) to what a buyer holds.


def test_granted_is_empty_for_no_grant_at_all() -> None:
    """`None` is "this row carries no decision" -- a PENDING or DENIED row. Fail closed, exactly as
    `covers(None)` does one function up."""
    assert levels.granted(None) == frozenset()


def test_granted_is_empty_for_a_stored_empty_set() -> None:
    """THE WHOLE RISK OF THIS FAMILY (D-C67's own fail-closed rule): an approval that names no
    capability grants NOTHING. An empty list is a real, stored decision -- distinct from `None` --
    and it must never collapse into "everything"."""
    assert levels.granted([]) == frozenset()


def test_granted_returns_exactly_the_capabilities_stored() -> None:
    assert levels.granted(["FINANCIALS", "FLOOR_PLANS"]) == frozenset({"FINANCIALS", "FLOOR_PLANS"})


def test_granted_drops_a_member_this_python_has_never_heard_of() -> None:
    """`covers()`'s own precedent, applied per MEMBER rather than per value: an unrecognised
    capability (a future migration adding one Python does not know about yet) confers nothing,
    while the recognised members beside it still confer themselves. Denying the whole set on one
    unknown member would be the other reading, and it would STRIP a buyer's existing access on the
    deploy that added the new name -- fail-closed about the unknown thing, never about the known
    ones."""
    assert levels.granted(["FINANCIALS", "TELEPATHY"]) == frozenset({"FINANCIALS"})


def test_granted_never_answers_full_confidential_as_a_member() -> None:
    """`FULL_CONFIDENTIAL` is a REQUESTABLE level, never a stored capability -- `CAPABILITIES` is
    the five, and migration 097's own CHECK admits only those. A row that somehow carried the
    umbrella name confers nothing for it rather than silently expanding to all five."""
    assert levels.granted(["FULL_CONFIDENTIAL"]) == frozenset()


def test_capabilities_matches_the_approved_capabilities_check(conn: Any) -> None:
    """The `approved_disclosure_level` pin above, moved to the column that replaced it (migration
    097). The array CHECK is `approved_capabilities <@ ARRAY[...]::text[]`, so `_permitted_levels`'
    own regex reads the five element literals out of `pg_get_constraintdef` exactly as it read the
    six out of an IN-list, and the set is `CAPABILITIES` rather than `REQUESTABLE_LEVELS`:
    `FULL_CONFIDENTIAL` is a name a buyer may ASK for and never one a grant may STORE."""
    assert levels.CAPABILITIES == _permitted_levels(conn, "approved_capabilities")
