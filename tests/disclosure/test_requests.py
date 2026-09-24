# tests/disclosure/test_requests.py
"""The request lifecycle (directive §5, §6, §15, §18). One test per transition and per refusal --
every refusal is a `Refusal`, so a route can catch it exactly as every other route in this
codebase already catches one.

Deviation from the plan's literal text, recorded in task-04-report.md: the plan's own Step 1/Step
3 both write `from app.api.listings import Refusal`, but `Refusal` is not defined, imported or
re-exported by `app.api.listings` at all on this branch -- it is defined at
`app/api/seller_listings.py:201`, which is also what the task brief names directly ("the same
class `app/api/seller_listings.py` already defines and raises") and the shape every other
cross-module import of it in this codebase already uses
(`tests/api/test_seller_listings.py:1940`, `tests/scripts/test_ingest_seed_photos.py:462`). The
plan's own predicted Step-2 failure (`ModuleNotFoundError: No module named
'app.disclosure.requests'`) would not even be reached with the literal import -- it fails one line
earlier with `ImportError: cannot import name 'Refusal' from 'app.api.listings'` -- so this file
imports from `app.api.seller_listings` instead, and that correction is what Step 2 below actually
demonstrates."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.api.seller_listings import Refusal
from app.disclosure import access, levels
from app.disclosure import requests as req


def _account(conn, email: str, state: str = "active") -> str:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'x',%s) RETURNING id", (email, state))
        return str(cur.fetchone()[0])


def _listing(conn, seller_id: str | None, status: str = "published") -> str:
    # zip/est/price/sqft (the SAME deviation Tasks 1 and 3 already recorded -- task-01-report.md,
    # task-03-report.md -- reapplied here rather than rediscovered): the plan's literal INSERT
    # satisfies neither `listing_submittable_ck` (030 -- name/city/zip/type/est/price for any
    # status but draft/withdrawn) nor `listing_publishable_ck`'s WIDENED shape (034 -- also
    # sqft, for a published row), both of which already apply on this branch's schema. Supplying
    # all four regardless of `status` is harmless for the `draft` case this file also needs
    # (`test_create_refuses_an_unpublished_listing`) and required for the `published` default.
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, seller_id, status,"
            " zip, est, price, sqft)"
            " VALUES (%s,'Test Practice','Austin','TX','Austin','Small animal','Austin, TX','seller',%s,%s,"
            " '78701',1990,1000000,2500)"
            " RETURNING id",
            (f"test-{uuid4().hex}", seller_id, status),
        )
        return str(cur.fetchone()[0])


def test_create_defaults_to_a_pending_full_confidential_request(conn) -> None:
    seller, buyer = _account(conn, "s1@x.org"), _account(conn, "b1@x.org")
    listing = _listing(conn, seller)
    row = req.create(conn, listing_id=listing, buyer_account_id=buyer, message="Tell me more")
    assert row["status"] == "PENDING" and row["requested_disclosure_level"] == "FULL_CONFIDENTIAL" and row["seller_user_id"] == seller


def test_create_refuses_a_listing_with_no_seller(conn) -> None:
    listing = _listing(conn, None)  # a seed listing
    buyer = _account(conn, "b2@x.org")
    with pytest.raises(Refusal) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert exc.value.code == "NO_SELLER"


def test_create_refuses_a_seller_requesting_their_own_listing(conn) -> None:
    seller = _account(conn, "s3@x.org")
    listing = _listing(conn, seller)
    with pytest.raises(Refusal) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=seller, message=None)
    assert exc.value.code == "SELF_REQUEST"


def test_create_refuses_an_unpublished_listing(conn) -> None:
    seller, buyer = _account(conn, "s4@x.org"), _account(conn, "b4@x.org")
    listing = _listing(conn, seller, status="draft")
    with pytest.raises(Refusal) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert exc.value.code == "NOT_FOUND"


def test_create_refuses_a_second_pending_request_for_the_same_pair(conn) -> None:
    seller, buyer = _account(conn, "s5@x.org"), _account(conn, "b5@x.org")
    listing = _listing(conn, seller)
    req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert exc.value.code == "ALREADY_REQUESTED"


def test_create_refuses_an_unrecognised_disclosure_level(conn) -> None:
    seller, buyer = _account(conn, "s6@x.org"), _account(conn, "b6@x.org")
    listing = _listing(conn, seller)
    with pytest.raises(Refusal) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None, requested_disclosure_level="EVERYTHING")
    assert exc.value.code == "BAD_LEVEL"


def test_create_lets_an_unexpected_database_error_propagate_rather_than_mislabel_it(conn) -> None:
    """The `except` clause in `create` exists to convert exactly ONE known error -- the partial
    unique index's `UniqueViolation` -- into a typed `ALREADY_REQUESTED` refusal. Any OTHER
    database error is a bug or a caller misuse this module must not disguise as a business
    refusal, so it re-raises untouched (the bare `raise` on the branch below the `if`). A
    `buyer_account_id` with no matching `account` row -- never possible through the real routes,
    whose principal is always an authenticated, existing account -- forces the INSERT's OTHER
    integrity constraint, the foreign key on `buyer_user_id`, to fire: a different exception class
    than `UniqueViolation`, which must come back exactly as raised, never as a `Refusal`."""
    seller = _account(conn, "s16@x.org")
    listing = _listing(conn, seller)
    with pytest.raises(Exception) as exc:
        req.create(conn, listing_id=listing, buyer_account_id=str(uuid4()), message=None)
    assert not isinstance(exc.value, Refusal)
    assert type(exc.value).__name__ != "UniqueViolation"


def test_get_one_succeeds_for_the_owning_buyer(conn) -> None:
    seller, buyer = _account(conn, "s17@x.org"), _account(conn, "b17@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message="Tell me more")
    fetched = req.get_one(conn, request_id=created["id"], buyer_account_id=buyer)
    assert fetched["id"] == created["id"] and fetched["message"] == "Tell me more"


def test_get_one_refuses_anyone_who_is_not_the_owning_buyer(conn) -> None:
    """directive §22 (IDOR): neither a different buyer nor the listing's own seller may confirm a
    request exists by reading it -- both get the SAME 404 an absent id would (seller_listings.py:18's
    rule), never a 403 that would leak "yes, something is there"."""
    seller, buyer, other_buyer = _account(conn, "s18@x.org"), _account(conn, "b18@x.org"), _account(conn, "o18@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc_other_buyer:
        req.get_one(conn, request_id=created["id"], buyer_account_id=other_buyer)
    assert exc_other_buyer.value.status == 404
    with pytest.raises(Refusal) as exc_seller:
        req.get_one(conn, request_id=created["id"], buyer_account_id=seller)
    assert exc_seller.value.status == 404


def test_list_mine_is_scoped_to_the_calling_buyer(conn) -> None:
    seller = _account(conn, "s7@x.org")
    buyer_a, buyer_b = _account(conn, "ba7@x.org"), _account(conn, "bb7@x.org")
    listing = _listing(conn, seller)
    req.create(conn, listing_id=listing, buyer_account_id=buyer_a, message=None)
    assert len(req.list_mine(conn, buyer_account_id=buyer_a)) == 1
    assert req.list_mine(conn, buyer_account_id=buyer_b) == []


def test_list_inbox_is_scoped_to_the_calling_seller(conn) -> None:
    seller_a, seller_b = _account(conn, "sa8@x.org"), _account(conn, "sb8@x.org")
    buyer = _account(conn, "b8@x.org")
    listing = _listing(conn, seller_a)
    req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert len(req.list_inbox(conn, seller_account_id=seller_a)) == 1
    assert req.list_inbox(conn, seller_account_id=seller_b) == []


def test_decide_approve_defaults_the_level_to_what_was_requested(conn) -> None:
    seller, buyer = _account(conn, "s9@x.org"), _account(conn, "b9@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None, requested_disclosure_level="IDENTITY")
    decided = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    # `approved_capabilities`, and a LIST rather than the single `"IDENTITY"` this line read until
    # D-C67 (2026-09-24): migration 097 replaced the column, and `covers()` is still the one door
    # from the buyer's requested level to the default grant, so the DEFAULT arm proves the same
    # thing it always did.
    assert decided["status"] == "APPROVED" and decided["approved_capabilities"] == ["IDENTITY"] and decided["reviewed_by"] == seller


def test_decide_approve_can_override_the_level_below_what_was_requested(conn) -> None:
    """A seller need not grant everything the buyer asked for -- `decide`'s own `disclosure_level`
    parameter, exercised here (every other test in this file leaves it `None`, which only ever
    proves the DEFAULT arm of `level = disclosure_level or ...`)."""
    seller, buyer = _account(conn, "s19@x.org"), _account(conn, "b19@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None, requested_disclosure_level="FULL_CONFIDENTIAL")
    decided = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level="IDENTITY", reason=None)
    assert decided["approved_capabilities"] == ["IDENTITY"]


def test_decide_approve_refuses_an_unrecognised_override_level(conn) -> None:
    seller, buyer = _account(conn, "s20@x.org"), _account(conn, "b20@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level="EVERYTHING", reason=None)
    assert exc.value.code == "BAD_LEVEL"


def test_decide_deny_records_the_reason(conn) -> None:
    seller, buyer = _account(conn, "s10@x.org"), _account(conn, "b10@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    decided = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="deny", disclosure_level=None, reason="Not a good fit")
    assert decided["status"] == "DENIED" and decided["denial_reason"] == "Not a good fit"


def test_decide_refuses_an_unrecognised_action(conn) -> None:
    seller, buyer = _account(conn, "s21@x.org"), _account(conn, "b21@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=seller, action="frobnicate", disclosure_level=None, reason=None)
    assert exc.value.code == "BAD_ACTION"


def test_decide_refuses_a_request_belonging_to_a_different_seller(conn) -> None:
    seller, other_seller, buyer = _account(conn, "s11@x.org"), _account(conn, "o11@x.org"), _account(conn, "b11@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=other_seller, action="approve", disclosure_level=None, reason=None)
    assert exc.value.status == 404  # a request that is not yours should not be confirmed to exist


def test_decide_refuses_a_request_that_is_not_pending(conn) -> None:
    """INVERTED BY D-C67 (2026-09-24) for the APPROVE arm alone, and kept for the DENY arm, which
    is what it now drives. It used to approve twice and assert `STATE` on the second call; the
    second approve is exactly how a seller narrows a grant now (see
    `test_decide_approve_narrows_an_already_approved_grant` below), so proving it refused would be
    proving the feature absent. Deny is unchanged and PENDING-only: taking back a decision already
    made is `revoke`, which has its own status, its own audit action and its own mail."""
    seller, buyer = _account(conn, "s12@x.org"), _account(conn, "b12@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=seller, action="deny", disclosure_level=None, reason="changed my mind")
    assert exc.value.code == "STATE"


def test_revoke_turns_an_approved_request_into_revoked(conn) -> None:
    seller, buyer = _account(conn, "s13@x.org"), _account(conn, "b13@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    revoked = req.revoke(conn, request_id=created["id"], seller_account_id=seller)
    assert revoked["status"] == "REVOKED"


def test_revoke_refuses_a_request_that_was_never_approved(conn) -> None:
    seller, buyer = _account(conn, "s14@x.org"), _account(conn, "b14@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.revoke(conn, request_id=created["id"], seller_account_id=seller)
    assert exc.value.code == "STATE"


def test_revoke_refuses_a_request_belonging_to_a_different_seller(conn) -> None:
    seller, other_seller, buyer = _account(conn, "s22@x.org"), _account(conn, "o22@x.org"), _account(conn, "b22@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    with pytest.raises(Refusal) as exc:
        req.revoke(conn, request_id=created["id"], seller_account_id=other_seller)
    assert exc.value.status == 404


def test_a_buyer_may_re_request_after_a_denial(conn) -> None:
    seller, buyer = _account(conn, "s15@x.org"), _account(conn, "b15@x.org")
    listing = _listing(conn, seller)
    first = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=first["id"], seller_account_id=seller, action="deny", disclosure_level=None, reason=None)
    second = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert second["id"] != first["id"]


def test_a_buyer_may_re_request_after_a_revocation(conn) -> None:
    """directive §15's other half: DENIED and REVOKED are the two closed states, and the partial
    unique index (migration 096) that makes `ALREADY_REQUESTED` a database invariant only
    excludes PENDING/APPROVED -- both arms have to be proved, not just the one the plan's own
    test file happened to write."""
    seller, buyer = _account(conn, "s23@x.org"), _account(conn, "b23@x.org")
    listing = _listing(conn, seller)
    first = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=first["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    req.revoke(conn, request_id=first["id"], seller_account_id=seller)
    second = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    assert second["id"] != first["id"]


def test_after_revoke_access_authorized_capabilities_is_empty_for_that_buyer(conn) -> None:
    """The property that ties this module to Task 3's `app/disclosure/access.py`: this module's
    OWN `revoke` (§15) must be honest that it closes the door on FUTURE authorized retrieval --
    proved here by calling Task 3's real authorization function, not by inspecting this module's
    return value, since a status string of "REVOKED" proves nothing about what
    `authorized_capabilities` -- the one function every confidential-resource route actually
    calls -- does with the row afterwards."""
    seller, buyer = _account(conn, "s24@x.org"), _account(conn, "b24@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None, requested_disclosure_level="FULL_CONFIDENTIAL")
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    assert access.authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) != frozenset()
    req.revoke(conn, request_id=created["id"], seller_account_id=seller)
    assert access.authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


# --- D-C67 (John, 2026-09-24: "all toggles must be fully functional and SELLER must be able to
# manage it all and per seller"). The seller chooses WHICH capabilities one buyer receives. Read
# with D-C66 (2026-09-24), which made the listing-wide ceilings per-buyer releasable and so made
# this grant the only thing left between a listing and disclosure.


def test_decide_approve_stores_exactly_the_subset_the_seller_named(conn) -> None:
    """The set the seller ticked is the set stored -- not a level that happens to contain it, and
    not the level the buyer asked for. `{FINANCIALS, FLOOR_PLANS}` is the case the old single-value
    column could never represent, and it is the grant the product's own accepted-row sentence has
    always described ("You released the financial packet and floor plan to this buyer.")."""
    seller, buyer = _account(conn, "s30@x.org"), _account(conn, "b30@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    decided = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
                        disclosure_level=None, reason=None,
                        disclosure_capabilities=["FLOOR_PLANS", "FINANCIALS"])
    assert decided["approved_capabilities"] == ["FINANCIALS", "FLOOR_PLANS"]
    held = access.authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer)
    # BOTH DIRECTIONS, asserted separately and each falsifiable on its own: what was named is held,
    # and what was NOT named is not. An assertion that only checked the first would pass just as
    # happily against a `FULL_CONFIDENTIAL` fallback, which is the exact bug this family exists to
    # prevent.
    assert held == frozenset({"FINANCIALS", "FLOOR_PLANS"})
    assert "IDENTITY" not in held and "EXACT_LOCATION" not in held and "UNREDACTED_IMAGES" not in held


def test_decide_approve_with_an_empty_set_releases_nothing(conn) -> None:
    """THE WHOLE RISK OF THIS FAMILY. The buyer asked for FULL_CONFIDENTIAL -- which is what every
    request defaults to (`app/api/requests.py`) -- and the seller approved naming no capability at
    all. A falsy test on the chosen set (`disclosure_capabilities or covers(requested)`) would fall
    through to that default and release all five. The row is APPROVED, and it grants nothing."""
    seller, buyer = _account(conn, "s31@x.org"), _account(conn, "b31@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None,
                        requested_disclosure_level="FULL_CONFIDENTIAL")
    decided = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
                        disclosure_level=None, reason=None, disclosure_capabilities=[])
    assert decided["status"] == "APPROVED"
    assert decided["approved_capabilities"] == []
    assert access.authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_decide_approve_naming_nothing_at_all_still_defaults_to_what_was_requested(conn) -> None:
    """The OTHER direction of the same seam, so neither can pass by accident: `None` is "the caller
    named no set", which is `decide`'s own long-standing default and must keep working. `[]` above
    and `None` here are two different answers and this pair is what proves the code tells them
    apart."""
    seller, buyer = _account(conn, "s32@x.org"), _account(conn, "b32@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None,
                        requested_disclosure_level="FULL_CONFIDENTIAL")
    decided = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
                        disclosure_level=None, reason=None, disclosure_capabilities=None)
    assert set(decided["approved_capabilities"]) == set(levels.CAPABILITIES)


def test_decide_approve_refuses_a_capability_this_product_does_not_have(conn) -> None:
    seller, buyer = _account(conn, "s33@x.org"), _account(conn, "b33@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
                  disclosure_level=None, reason=None, disclosure_capabilities=["FINANCIALS", "TELEPATHY"])
    assert exc.value.code == "BAD_LEVEL"


def test_decide_approve_refuses_the_umbrella_name_inside_the_set(conn) -> None:
    """`FULL_CONFIDENTIAL` is a level a buyer may ASK for, never a capability a grant may STORE --
    migration 097's own CHECK admits the five and nothing else, so a caller sending it inside the
    array is refused HERE rather than by a `CheckViolation` 500 two lines later."""
    seller, buyer = _account(conn, "s34@x.org"), _account(conn, "b34@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
                  disclosure_level=None, reason=None, disclosure_capabilities=["FULL_CONFIDENTIAL"])
    assert exc.value.code == "BAD_LEVEL"


def test_decide_approve_refuses_a_set_and_a_level_together(conn) -> None:
    seller, buyer = _account(conn, "s35@x.org"), _account(conn, "b35@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
                  disclosure_level="IDENTITY", reason=None, disclosure_capabilities=["FINANCIALS"])
    assert exc.value.code == "BAD_REQUEST"


def test_decide_approve_narrows_an_already_approved_grant(conn) -> None:
    """The second half of D-C67: the seller can SEE what a buyer holds and NARROW it later, without
    withdrawing the buyer's access entirely and making them ask again.

    Both directions of the narrowing are asserted separately: the capability that was TAKEN AWAY is
    gone, and the one that was KEPT is still held. Task 8's fix rounds are why -- twice in two
    consecutive rounds a two-sided gate masked itself because only the half that happened to pass
    was asserted."""
    seller, buyer = _account(conn, "s36@x.org"), _account(conn, "b36@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
              disclosure_level=None, reason=None, disclosure_capabilities=["IDENTITY", "FINANCIALS"])
    assert access.authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset({"IDENTITY", "FINANCIALS"})

    narrowed = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
                         disclosure_level=None, reason=None, disclosure_capabilities=["FINANCIALS"])
    assert narrowed["status"] == "APPROVED"
    held = access.authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer)
    assert "IDENTITY" not in held      # taken away
    assert "FINANCIALS" in held        # kept
    assert held == frozenset({"FINANCIALS"})


def test_decide_approve_widens_an_already_approved_grant(conn) -> None:
    """The other direction of the same control, so "narrow" is not passing merely because the
    second set is a subset of the first."""
    seller, buyer = _account(conn, "s37@x.org"), _account(conn, "b37@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
              disclosure_level=None, reason=None, disclosure_capabilities=["FINANCIALS"])
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
              disclosure_level=None, reason=None, disclosure_capabilities=["FINANCIALS", "FLOOR_PLANS"])
    assert access.authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset({"FINANCIALS", "FLOOR_PLANS"})


def test_decide_approve_can_narrow_an_approved_grant_all_the_way_to_nothing(conn) -> None:
    """The empty set is reachable on the NARROW path too, and it still means nothing rather than
    everything -- the same falsy-collapse bug, one call later, where the row is already APPROVED and
    a fall-through would re-read the buyer's own FULL_CONFIDENTIAL ask."""
    seller, buyer = _account(conn, "s38@x.org"), _account(conn, "b38@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
              disclosure_level=None, reason=None, disclosure_capabilities=["IDENTITY", "FINANCIALS"])
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
              disclosure_level=None, reason=None, disclosure_capabilities=[])
    assert access.authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_decide_approve_refuses_a_denied_or_revoked_row(conn) -> None:
    """Widening the approve arm to accept an APPROVED row must not resurrect a grant the seller
    already ended. Both terminal statuses, asserted separately."""
    seller = _account(conn, "s39@x.org")
    listing = _listing(conn, seller)

    denied_buyer = _account(conn, "b39a@x.org")
    denied = req.create(conn, listing_id=listing, buyer_account_id=denied_buyer, message=None)
    req.decide(conn, request_id=denied["id"], seller_account_id=seller, action="deny", disclosure_level=None, reason="no")
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=denied["id"], seller_account_id=seller, action="approve",
                  disclosure_level=None, reason=None, disclosure_capabilities=["FINANCIALS"])
    assert exc.value.code == "STATE"

    revoked_buyer = _account(conn, "b39b@x.org")
    revoked = req.create(conn, listing_id=listing, buyer_account_id=revoked_buyer, message=None)
    req.decide(conn, request_id=revoked["id"], seller_account_id=seller, action="approve",
              disclosure_level=None, reason=None, disclosure_capabilities=["FINANCIALS"])
    req.revoke(conn, request_id=revoked["id"], seller_account_id=seller)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=revoked["id"], seller_account_id=seller, action="approve",
                  disclosure_level=None, reason=None, disclosure_capabilities=["FINANCIALS"])
    assert exc.value.code == "STATE"
    assert access.authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=revoked_buyer) == frozenset()


def test_a_second_sellers_request_cannot_be_narrowed_by_this_seller(conn) -> None:
    """The widened status set must not have widened the OWNERSHIP check with it."""
    seller_a, seller_b = _account(conn, "s40a@x.org"), _account(conn, "s40b@x.org")
    buyer = _account(conn, "b40@x.org")
    listing = _listing(conn, seller_a)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller_a, action="approve",
              disclosure_level=None, reason=None, disclosure_capabilities=["FINANCIALS"])
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=seller_b, action="approve",
                  disclosure_level=None, reason=None, disclosure_capabilities=[])
    assert exc.value.code == "NOT_FOUND"
    assert access.authorized_capabilities(conn, listing_id=listing, seller_id=seller_a, buyer_account_id=buyer) == frozenset({"FINANCIALS"})


# --- Fix round 1, review Important-1: an approve that names NOTHING must not re-expand a grant ----


def test_decide_approve_naming_nothing_is_refused_on_an_already_approved_row(conn) -> None:
    """**THE WIDENING-BY-OMISSION SURFACE.** `decide`'s default arm predates this ruling: it was
    written when PENDING was the only status it could see, where "the caller named no set" sensibly
    means "the level the buyer asked for". Once the approve arm also accepts an APPROVED row that
    reading is wrong in the dangerous direction — every request in this product is created
    `FULL_CONFIDENTIAL` (`app/api/requests.py`), so a bare `{"action": "approve"}` on a row the
    seller had narrowed to `{FINANCIALS}` would restore identity, the street, the telephone, the
    exact pin, the unredacted photographs, the financial packet and the floor plans, with no 409, no
    warning and no mail (the outbox idempotency key has already fired).

    It is refused, and the grant is asserted UNCHANGED afterwards rather than only the refusal — a
    refusal that had already written would pass the first assertion alone."""
    seller, buyer = _account(conn, "s41@x.org"), _account(conn, "b41@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
              disclosure_level=None, reason=None, disclosure_capabilities=["FINANCIALS"])

    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
                  disclosure_level=None, reason=None)
    assert exc.value.code == "BAD_REQUEST"
    assert access.authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset({"FINANCIALS"})


def test_decide_approve_on_an_approved_row_still_takes_an_explicitly_named_level(conn) -> None:
    """The refusal above is NARROW, and this is what keeps it so: it refuses an UNDER-SPECIFIED
    decision, never a widening the caller actually asked for. A seller who names
    `FULL_CONFIDENTIAL` on a narrowed row gets exactly that — it is their decision, stated."""
    seller, buyer = _account(conn, "s42@x.org"), _account(conn, "b42@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
              disclosure_level=None, reason=None, disclosure_capabilities=["FINANCIALS"])
    widened = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve",
                        disclosure_level="FULL_CONFIDENTIAL", reason=None)
    assert sorted(widened["approved_capabilities"]) == sorted(levels.CAPABILITIES)
