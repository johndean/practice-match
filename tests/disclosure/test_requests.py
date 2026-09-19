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
from app.disclosure import access
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
    assert decided["status"] == "APPROVED" and decided["approved_disclosure_level"] == "IDENTITY" and decided["reviewed_by"] == seller


def test_decide_approve_can_override_the_level_below_what_was_requested(conn) -> None:
    """A seller need not grant everything the buyer asked for -- `decide`'s own `disclosure_level`
    parameter, exercised here (every other test in this file leaves it `None`, which only ever
    proves the DEFAULT arm of `level = disclosure_level or ...`)."""
    seller, buyer = _account(conn, "s19@x.org"), _account(conn, "b19@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None, requested_disclosure_level="FULL_CONFIDENTIAL")
    decided = req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level="IDENTITY", reason=None)
    assert decided["approved_disclosure_level"] == "IDENTITY"


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
    seller, buyer = _account(conn, "s12@x.org"), _account(conn, "b12@x.org")
    listing = _listing(conn, seller)
    created = req.create(conn, listing_id=listing, buyer_account_id=buyer, message=None)
    req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
    with pytest.raises(Refusal) as exc:
        req.decide(conn, request_id=created["id"], seller_account_id=seller, action="approve", disclosure_level=None, reason=None)
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
