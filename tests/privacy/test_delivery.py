"""The one resolver (spec 2026-09-09 C.7; directive 9 and 12).

Directive 12: "Every buyer-facing image request must resolve the authoritative listing privacy
state." This function IS that resolution, and it is pure, so every cell of
(visibility x status x buyer_visible x key-present) is a unit test rather than an integration
argument. Its `None` is a 404 on the bytes route and a null slot in the JSON.

The three rules it can never break: never the original, never display under NOT_SHOW, and never a
fallback when something is missing."""
from __future__ import annotations

import dataclasses
import itertools
from uuid import uuid4

import pytest

from app.privacy import record
from app.privacy.delivery import Variant, buyer_variant

STATUSES = ("UPLOADED", "PROCESSING", "SCANNED", "REDACTION_GENERATED", "READY_FOR_REVIEW",
            "SELLER_CONFIRMED", "PUBLISHED", "PROCESSING_FAILED", "REDACTION_FAILED",
            "REVIEW_REQUIRED", "REPROCESS_REQUIRED")
NOT_SHOW_OK = ("SELLER_CONFIRMED", "PUBLISHED")
SHOW_OK = ("READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")


def _row(status: str, *, visible: bool, redacted: bool = True) -> record.PrivacyRow:
    asset_id, listing_id = uuid4(), uuid4()
    return record.PrivacyRow(
        asset_id=asset_id, listing_id=listing_id, processing_status=status, processing_version=1,
        attempts=0, original_storage_key=f"listings/{listing_id}/photos/{asset_id}/original.jpg",
        redacted_storage_key=f"listings/{listing_id}/photos/{asset_id}/redacted.webp" if redacted else None,
        redacted_sha256="b" * 64 if redacted else None, confirmed_sha256=None, seller_confirmed=False,
        buyer_visible=visible, redaction_regions=[], reprocess_reason=None, final_privacy_state=None,
        display_storage_key=f"listings/{listing_id}/photos/{asset_id}/display.webp",
        display_sha256="d" * 64)


# `list(...)` and not the bare iterator the plan sketched: pytest 8.4 raises
# `PytestRemovedIn10Warning: Passing a generator/iterator to parametrize` and `-W error` turns that
# into a collection error, so the 176 cells could not be collected at all (deviation D1).
@pytest.mark.parametrize(("visibility", "status", "visible", "redacted"),
                         list(itertools.product(("SHOW", "NOT_SHOW"), STATUSES, (True, False), (True, False))))
def test_every_cell_resolves_to_the_one_answer_the_policy_allows(
    visibility: str, status: str, visible: bool, redacted: bool
) -> None:
    row = _row(status, visible=visible, redacted=redacted)
    got = buyer_variant(visibility, row, str(row.asset_id))
    if not visible:
        assert got is None
        return
    if visibility == "NOT_SHOW":
        expected = Variant(row.redacted_storage_key, "b" * 64, False) if (status in NOT_SHOW_OK and redacted) else None
    else:
        expected = Variant(row.display_storage_key, "d" * 64, False) if status in SHOW_OK else None
    assert got == expected


def test_the_original_is_never_the_answer() -> None:
    for visibility in ("SHOW", "NOT_SHOW"):
        for status in STATUSES:
            for visible in (True, False):
                got = buyer_variant(visibility, _row(status, visible=visible), "x")
                assert got is None or "original" not in got.key


def test_display_is_never_the_answer_under_not_show() -> None:
    for status in STATUSES:
        got = buyer_variant("NOT_SHOW", _row(status, visible=True), "x")
        assert got is None or got.key.endswith("redacted.webp")


def test_a_photograph_with_no_privacy_row_is_nothing_to_a_buyer() -> None:
    """A seller asset whose row is somehow absent -- there is no such path, and if one appeared the
    answer is still a null slot rather than the bytes."""
    assert buyer_variant("NOT_SHOW", None, "3f2a…") is None
    assert buyer_variant("SHOW", None, "3f2a…") is None


def test_a_seed_path_entry_is_the_disk_file_under_show_and_nothing_under_not_show() -> None:
    """Spec C.10: a seed photograph has no asset row and no derivative, so NOT_SHOW has nothing it
    could honestly serve."""
    assert buyer_variant("SHOW", None, "round-rock/1.webp", "a" * 64) == Variant("round-rock/1.webp", "a" * 64, True)
    assert buyer_variant("NOT_SHOW", None, "round-rock/1.webp", "a" * 64) is None


def test_a_stale_flag_changes_nothing_the_buyer_sees() -> None:
    """The resolver never reads `reprocess_reason`: a stale redaction is still a redaction, and the
    in-place re-run replaces it under a new hash (D-IDP-16).

    `dataclasses.replace`, not `_asdict()`: `PrivacyRow` is a frozen dataclass and not a
    NamedTuple, so it has no `_asdict`, and `vars()` on a frozen instance is an implementation
    detail. `replace` is the supported way and it type-checks under --strict."""
    row = _row("PUBLISHED", visible=True)
    flagged = dataclasses.replace(row, reprocess_reason="VERSION")
    assert buyer_variant("NOT_SHOW", flagged, "x") == buyer_variant("NOT_SHOW", row, "x")


#: --- Per-buyer disclosure plan (2026-09-18), Task 7: `buyer_variant` grows a buyer dimension ---
#:
#: `authorized` defaults False, and every test above this line omits the argument entirely -- which
#: is the proof, not an assumption, that the live contract survives: `authorized=False` must be
#: byte-for-byte the function this file already pinned, or the 176-cell matrix above would itself
#: start failing. The tests below are the NEW dimension only.


def test_not_show_with_authorization_serves_the_display_derivative() -> None:
    """Directive §9, first half: "If a seller authorizes unredacted images for Buyer A: Buyer A may
    receive the authorized version" -- stated with no further condition on the listing's own
    NOT_SHOW ceiling. The escape hatch Task 7 adds: a buyer who holds UNREDACTED_IMAGES for this
    listing receives display even while the listing is globally NOT_SHOW."""
    row = _row("PUBLISHED", visible=True, redacted=True)
    got = buyer_variant("NOT_SHOW", row, str(row.asset_id), authorized=True)
    assert got == Variant(row.display_storage_key, "d" * 64, False)


def test_not_show_without_authorization_still_serves_only_the_redacted_derivative() -> None:
    """Directive §9, second half, in the SAME function the first half is tested in: "Buyer B must
    continue receiving only the permitted redacted version." This is also exactly what the 176-cell
    matrix above already proves for `authorized`'s default -- restated here, explicitly, as the
    other half of the A/B pairing the directive states as one sentence."""
    row = _row("PUBLISHED", visible=True, redacted=True)
    got = buyer_variant("NOT_SHOW", row, str(row.asset_id), authorized=False)
    assert got == Variant(row.redacted_storage_key, "b" * 64, False)


def test_buyer_a_and_buyer_b_on_the_same_not_show_listing_at_the_same_moment_diverge_only_by_grant() -> None:
    """Directive §7's own critical security test, at the level `buyer_variant` can state it: ONE
    row, ONE listing, ONE moment, two calls that differ ONLY in `authorized` -- so a future edit
    that collapses the two paths back into one answer breaks this single test rather than requiring
    two separate ones to both be remembered and both be right."""
    row = _row("PUBLISHED", visible=True, redacted=True)
    buyer_a = buyer_variant("NOT_SHOW", row, str(row.asset_id), authorized=True)
    buyer_b = buyer_variant("NOT_SHOW", row, str(row.asset_id), authorized=False)
    assert buyer_a == Variant(row.display_storage_key, "d" * 64, False)
    assert buyer_b == Variant(row.redacted_storage_key, "b" * 64, False)
    assert buyer_a != buyer_b


def test_show_discloses_the_display_derivative_regardless_of_authorization() -> None:
    """The OTHER half of the live contract that has to survive: "SHOW -> the display derivative" is
    unconditional, exactly as it is today -- SHOW already discloses to every buyer (directive §8,
    "if it controls publication/redaction of listing assets, preserve that functionality where
    appropriate"), so a per-buyer grant only ever WIDENS what NOT_SHOW would otherwise hide and
    never narrows what SHOW already reveals. No QA listing is SHOW today (every seed and every
    Wave-2b default is NOT_SHOW, per this module's own docstring), so this is a property proved
    here rather than one any live photograph currently exercises."""
    row = _row("PUBLISHED", visible=True, redacted=True)
    with_grant = buyer_variant("SHOW", row, str(row.asset_id), authorized=True)
    without_grant = buyer_variant("SHOW", row, str(row.asset_id), authorized=False)
    expected = Variant(row.display_storage_key, "d" * 64, False)
    assert with_grant == expected
    assert without_grant == expected


def test_an_authorized_buyer_gets_nothing_rather_than_a_fallback_when_display_is_not_ready() -> None:
    """Directive §19: never a fallback to something else. `SCANNED` is ready for neither variant --
    an authorized buyer on a NOT_SHOW listing whose display derivative has not finished processing
    gets a null slot, NEVER the redacted derivative instead (a fallback nobody asked for) and never
    a stale answer manufactured from readiness the row does not have."""
    row = _row("SCANNED", visible=True, redacted=True)
    assert buyer_variant("NOT_SHOW", row, str(row.asset_id), authorized=True) is None


def test_a_seed_entry_ignores_authorization_entirely() -> None:
    """Spec C.10: a seed photograph has no asset row and no `request` row to hold a grant against.
    `authorized=True` changes nothing about it in either direction -- still the disk file under
    SHOW, still nothing under NOT_SHOW -- which is what keeps every one of John's 29 demo hospitals'
    approved-state pixels exactly where they are."""
    assert buyer_variant("SHOW", None, "round-rock/1.webp", "a" * 64, authorized=True) == Variant("round-rock/1.webp", "a" * 64, True)
    assert buyer_variant("NOT_SHOW", None, "round-rock/1.webp", "a" * 64, authorized=True) is None


def test_the_buyer_url_is_positional_and_carries_twelve_characters_of_the_content_hash() -> None:
    """Spec F: the `?v=` is a CACHE KEY and never a selector, so it is the hash of the variant the
    server decided on -- twelve characters, which is what changes the URL when a mask moves."""
    from app.privacy.delivery import photo_url

    listing_id = uuid4()
    assert photo_url(listing_id, 3, "a" * 64) == f"/api/listings/{listing_id}/photos/3?v={'a' * 12}"


def test_the_owner_url_takes_the_callers_own_prefix_so_one_function_serves_both_routes() -> None:
    """The owner's and the reviewer's tile URLs differ only in the route each principal's
    permission opens (spec C.6), and there is exactly one producer of the `?v=`."""
    from app.privacy.delivery import owner_url

    asset_id = uuid4()
    assert owner_url("/api/seller/listings/7/photos", asset_id, "b" * 64) == f"/api/seller/listings/7/photos/{asset_id}?v={'b' * 12}"
    assert owner_url("/api/admin/listings/7/photos", asset_id, "b" * 64) == f"/api/admin/listings/7/photos/{asset_id}?v={'b' * 12}"
