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


def test_requestable_levels_matches_the_approved_disclosure_level_check(conn: Any) -> None:
    """Same pin, the grant column. `approved_disclosure_level` carries no NOT NULL (a PENDING or
    DENIED row has none), but its CHECK lists the identical six levels as the request column's --
    a future migration that widened one column's list without the other's would be exactly the
    "two copies of a value list that nothing compares" defect this test exists to catch, one
    column over from the first."""
    assert levels.REQUESTABLE_LEVELS == _permitted_levels(conn, "approved_disclosure_level")
