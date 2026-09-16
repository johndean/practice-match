"""The publishing gate's predicate, one case per offender class (spec 2026-09-09 C.8).

Directive 11: a listing cannot be published while any of its photographs has not been through the
pipeline. `app/privacy/gate.py` calls the SAME SQL function migration 042's trigger calls, so the
cases below are read against `migrations/042_listing_publish_photos_ready_trigger.sql` as much as
against the Python: a route and the database cannot disagree about what "ready" means, and these
are the rows of that one definition.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.privacy import gate
from tests.privacy.conftest import make_listing, make_row


def test_under_not_show_only_a_confirmed_photograph_with_a_derivative_passes(conn: Any) -> None:
    """Directive 11 (3): under NOT_SHOW "seller explicitly confirms the result". SELLER_CONFIRMED
    is the floor and READY_FOR_REVIEW is not enough -- "Never allow AI_PASSED to mean
    READY_TO_PUBLISH"."""
    listing_id = make_listing(conn, "gate-ns", visibility="NOT_SHOW")
    ready, _ = make_row(conn, listing_id=listing_id, processing_status="READY_FOR_REVIEW")
    make_row(conn, listing_id=listing_id, processing_status="SELLER_CONFIRMED",
             confirmed=True, buyer_visible=True)
    assert gate.photos_not_ready(conn, listing_id) == [(str(ready), "READY_FOR_REVIEW")]


def test_under_show_the_floor_is_ready_for_review_and_not_scanned(conn: Any) -> None:
    """Controller ruling 8 gave a range from SCANNED; the spec narrows it to READY_FOR_REVIEW,
    because directive 11 (1) says "completed processing" and SCANNED is mid-run."""
    listing_id = make_listing(conn, "gate-show", visibility="SHOW")
    scanned, _ = make_row(conn, listing_id=listing_id, processing_status="SCANNED")
    make_row(conn, listing_id=listing_id, processing_status="READY_FOR_REVIEW", buyer_visible=True)
    assert gate.photos_not_ready(conn, listing_id) == [(str(scanned), "SCANNED")]


@pytest.mark.parametrize("status", ["UPLOADED", "PROCESSING", "PROCESSING_FAILED", "REDACTION_FAILED",
                                    "REVIEW_REQUIRED", "REPROCESS_REQUIRED"])
def test_every_unfinished_or_failed_state_is_an_offender_under_both_settings(conn: Any, status: str) -> None:
    for visibility in ("SHOW", "NOT_SHOW"):
        listing_id = make_listing(conn, f"gate-{status}-{visibility}", visibility=visibility)
        asset_id, _ = make_row(conn, listing_id=listing_id, processing_status=status)
        assert gate.photos_not_ready(conn, listing_id) == [(str(asset_id), status)]


def test_a_flagged_row_is_stale_and_a_new_publication_waits_for_it(conn: Any) -> None:
    listing_id = make_listing(conn, "gate-stale", visibility="NOT_SHOW")
    asset_id, _ = make_row(conn, listing_id=listing_id, processing_status="SELLER_CONFIRMED",
                           confirmed=True, buyer_visible=True, reprocess_reason="VERSION")
    assert gate.photos_not_ready(conn, listing_id) == [(str(asset_id), "STALE")]


def test_a_photograph_with_no_privacy_row_at_all_is_an_offender(conn: Any) -> None:
    """There is no path that creates one -- the upload writes both rows in one transaction -- and
    if one appeared the gate refuses rather than assuming."""
    listing_id = make_listing(conn, "gate-orphan", visibility="NOT_SHOW")
    asset_id, _ = make_row(conn, listing_id=listing_id, processing_status="SELLER_CONFIRMED",
                           confirmed=True, buyer_visible=True)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM listing_asset_privacy WHERE asset_id = %s", (asset_id,))
    assert gate.photos_not_ready(conn, listing_id) == [(str(asset_id), "NO_PRIVACY_ROW")]


def test_a_seed_path_entry_passes_under_show_and_is_seed_unprocessed_under_not_show(conn: Any) -> None:
    for visibility, expected in (("SHOW", []), ("NOT_SHOW", [("round-rock/1.webp", "SEED_UNPROCESSED")])):
        listing_id = make_listing(conn, f"gate-seed-{visibility}", visibility=visibility)
        with conn.cursor() as cur:
            cur.execute("UPDATE listing SET photos = '[\"round-rock/1.webp\"]'::jsonb WHERE id = %s",
                        (listing_id,))
        assert gate.photos_not_ready(conn, listing_id) == expected


def test_a_listing_with_no_photographs_has_no_offenders(conn: Any) -> None:
    """A listing may be published with none -- the design's empty slots are a legitimate state, and
    the gate is about the photographs there ARE."""
    assert gate.photos_not_ready(conn, make_listing(conn, "gate-empty")) == []


def test_the_offenders_come_back_in_listing_photos_order(conn: Any) -> None:
    """The wizard names them by position, so the order has to be the array's and not the table's."""
    listing_id = make_listing(conn, "gate-order", visibility="NOT_SHOW")
    first, _ = make_row(conn, listing_id=listing_id, processing_status="UPLOADED")
    second, _ = make_row(conn, listing_id=listing_id, processing_status="PROCESSING")
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET photos = %s::jsonb WHERE id = %s",
                    (json.dumps([str(second), str(first)]), listing_id))
    assert [entry for entry, _status in gate.photos_not_ready(conn, listing_id)] == [str(second), str(first)]


def test_the_two_messages_are_the_specs_own_and_differ_by_the_review_clause(conn: Any) -> None:
    """Spec H's two rows. Under NOT_SHOW the seller's confirmation is part of readiness, so the
    message says so; under SHOW it is processing alone. Neither claims detection is certain (spec
    H, directive 23) -- `tests/test_docs.py` is what holds that across the whole product, and this
    is the local half: these are the two strings a seller actually meets."""
    assert gate.NOT_READY_MESSAGE == {
        "NOT_SHOW": "Every photograph must finish processing and be reviewed before this"
                    " listing can be submitted.",
        "SHOW": "Every photograph must finish processing before this listing can be submitted.",
    }


def test_the_extra_key_names_every_offender_by_id_and_state(conn: Any) -> None:
    """Additive inside decision A5's `error` object: an existing client reads `code` and `message`
    and is unaffected, and the wizard's step-6 tiles are what name the photographs."""
    assert gate.not_ready_extra([("a", "UPLOADED"), ("b", "STALE")]) == {
        "photos": [{"id": "a", "status": "UPLOADED"}, {"id": "b", "status": "STALE"}],
    }
