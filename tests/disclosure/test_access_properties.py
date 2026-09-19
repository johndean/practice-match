# tests/disclosure/test_access_properties.py
"""The fail-closed PROPERTY (directive §19), swept over every reachable authorization state rather
than checked by example (`tests/disclosure/test_access.py`'s ten hand-picked ones). Per-buyer
disclosure plan Task 10. `itertools.product` over four axes is `tests/privacy/test_delivery.py`'s
own exhaustive-enumeration idiom, chosen deliberately over a new property-testing library
(`hypothesis` is not a dependency of this project -- `pyproject.toml` has none) so this file uses
the project's own established style for "prove a property over every state" rather than
introducing a parallel testing convention.

THE SINGLE SOUNDNESS STATEMENT the whole authorization boundary rests on, and the one thing this
file exists to prove holds with NO exception:

    a capability is granted if, and only if, status == APPROVED, the grant has not expired,
    the buyer is not the listing's own seller, and the level covers that capability.

This is the CONTRAPOSITIVE of "assume approved" (directive §19's own words: "Never assume
approval ... A missing authorization record means NOT AUTHORIZED"): for every state that is not
exactly (APPROVED, not-expired, buyer != seller, level covers X), the result must be `False` for
capability X, with no special case carved out for any of them.

Three deviations from the plan's own literal Step 1 test, found by RUNNING it against the real
database and reading the real error text -- not by inspection, and not fixed by touching the
expected-value formula, which is directive §19 restated and is never what a CHECK-constraint
mismatch should move:

1. `request_seller_is_not_buyer_ck CHECK (buyer_user_id <> seller_user_id)` (migration 096) is
   UNCONDITIONAL, not merely "for a non-pending row" as the plan's own `pytest.skip` guard assumed.
   RED, verbatim (`status="PENDING", buyer_is_seller=True`, the one combination the plan's own skip
   let through):
       psycopg2.errors.CheckViolation: new row for relation "request" violates check constraint
       "request_seller_is_not_buyer_ck"
   (confirmed against the real standalone database, not guessed from reading the migration; the
   DETAIL line names the seller's own account id twice, once as `buyer_user_id` and once as
   `seller_user_id`, which is the constraint's whole complaint.)
   No row with `buyer_user_id = seller_user_id` can EVER exist, in any status, so this axis cannot
   be tested by inserting one. Instead a genuine, DIFFERENT buyer's row is planted for the exact
   (status, expiry, level) under test, so the axis still exercises a real, populated `request` row
   on this exact listing rather than an empty table, and the assertion asks the boundary the
   sensitive question directly: does `authorized_capabilities` refuse the SELLER asking "what do I
   get, framed as a buyer" regardless of what some other real buyer genuinely holds on the very
   same listing. (Separately recorded in the "honest limits" section of this task's own report:
   because the CHECK constraint alone already makes this state unreachable through a real row, a
   sweep built this way cannot, by itself, distinguish "the database enforces this" from "the
   Python guard in `access.py` enforces this" -- both are true today, and either alone would
   suffice; only a schema change could make the distinction observable.)
2. `request_pending_has_no_decision_ck` requires `approved_disclosure_level IS NULL` whenever
   `status = 'PENDING'`. RED, verbatim (`status="PENDING", level="EXACT_LOCATION"`, a level the
   plan's cross product happily attaches to a still-pending row):
       psycopg2.errors.CheckViolation: new row for relation "request" violates check constraint
       "request_pending_has_no_decision_ck"
   A pending request never carries a level in this schema (the seller has not decided yet), so a
   non-`None` `level` is written as `NULL` whenever `status == "PENDING"`; the expected value is
   unaffected either way, since `should_be_authorized` is already `False` for every non-`APPROVED`
   status regardless of what level a decision would eventually record.
3. `request_approved_needs_decision_ck` requires `approved_disclosure_level IS NOT NULL` whenever
   `status = 'APPROVED'`. RED, verbatim (`status="APPROVED", level=None`, an approval with no level
   at all):
       psycopg2.errors.CheckViolation: new row for relation "request" violates check constraint
       "request_approved_needs_decision_ck"
   The database itself refuses to represent "approved, granting nothing" -- there is no such state
   to sweep, so it is skipped, the same way the plan's own draft already skips the one combination
   its author had noticed for a different axis.

Two more states directive §19 and this task's own brief name explicitly ("every disclosure level
including one the code has never heard of", "a listing that does not exist") cannot be reached
through a `request` row at all -- migration 096's own CHECK on `approved_disclosure_level` accepts
only the six capability names plus `FULL_CONFIDENTIAL` (`levels.py`'s own comment: "so Python and
the database cannot silently drift apart"), so there is no row to insert with an unrecognised
level, and a `request` row can never outlive the `listing` it references (`ON DELETE CASCADE`).
Both are proved directly below, calling the boundary the same way a route would rather than through
a planted row, since none can exist."""
from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.disclosure.access import authorized_capabilities, has_capability
from app.disclosure.levels import CAPABILITIES, REQUESTABLE_LEVELS, covers
from tests.disclosure.test_access import _account, _listing, _request

STATUSES = ("PENDING", "APPROVED", "DENIED", "REVOKED")
EXPIRIES = ("none", "future", "past")
LEVELS = (None, *sorted(REQUESTABLE_LEVELS))
BUYER_IS_SELLER = (False, True)


def _expiry(kind: str) -> str | None:
    now = datetime.now(UTC)
    return {
        "none": None,
        "future": (now + timedelta(days=1)).isoformat(),
        "past": (now - timedelta(days=1)).isoformat(),
    }[kind]


@pytest.mark.parametrize(
    ("status", "expiry", "level", "buyer_is_seller"),
    list(itertools.product(STATUSES, EXPIRIES, LEVELS, BUYER_IS_SELLER)),
)
def test_the_grant_soundness_property_holds_for_every_generated_state(
    conn, status: str, expiry: str, level: str | None, buyer_is_seller: bool
) -> None:
    """168 generated cases (4 statuses x 3 expiries x 7 levels-or-none [`REQUESTABLE_LEVELS`'s five
    named capabilities plus `FULL_CONFIDENTIAL`, plus `None`] x 2 buyer-is-seller states), six
    skipped as unrepresentable by the schema itself (deviation 3, above) -- 162 exercised, every one
    asserting the SAME soundness formula with no case exempted from it."""
    seller = _account(conn, f"seller-{uuid4().hex}@x.org")
    listing = _listing(conn, seller)

    if status == "APPROVED" and level is None:
        pytest.skip(
            "request_approved_needs_decision_ck refuses an APPROVED row with no level -- the "
            "database itself has no representation of 'approved, granting nothing'"
        )
    # Deviation 2: a pending request never carries a level in this schema, whatever the `level`
    # axis under test asks for -- the CHECK enforces it and the expected value does not depend on
    # it (every non-APPROVED status already yields `frozenset()` regardless of level).
    stored_level = None if status == "PENDING" else level

    if buyer_is_seller:
        # Deviation 1: no row can hold buyer_user_id = seller_user_id in ANY status. A genuine,
        # different buyer's row is planted for the same (status, expiry, level) so this axis still
        # exercises a real, populated row on this exact listing -- never an empty table standing in
        # for "nothing to find anyway" -- and the query asks the one question this axis exists for.
        decoy_buyer = _account(conn, f"decoy-{uuid4().hex}@x.org")
        _request(conn, listing, decoy_buyer, seller, status=status, level=stored_level, expires_at=_expiry(expiry))
        buyer = seller
    else:
        buyer = _account(conn, f"buyer-{uuid4().hex}@x.org")
        _request(conn, listing, buyer, seller, status=status, level=stored_level, expires_at=_expiry(expiry))

    got = authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer)
    should_be_authorized = status == "APPROVED" and expiry != "past" and not buyer_is_seller
    expected = covers(level) if should_be_authorized else frozenset()
    assert got == expected, (
        f"status={status} expiry={expiry} level={level} buyer_is_seller={buyer_is_seller} "
        f"got={sorted(got)} expected={sorted(expected)}"
    )


def test_a_listing_that_does_not_exist_grants_nothing(conn) -> None:
    """directive §19/this task's own brief: "a listing that does not exist." No `request` row can
    reference one (`ON DELETE CASCADE`, and the FK refuses the INSERT outright), so this asks the
    boundary directly with a listing id nothing was ever created for -- the fail-closed answer a
    route gets when a caller names a listing that was deleted, or never existed, between the moment
    a link was generated and the moment it was followed."""
    seller = _account(conn, f"seller-{uuid4().hex}@x.org")
    buyer = _account(conn, f"buyer-{uuid4().hex}@x.org")
    ghost_listing = str(uuid4())
    assert authorized_capabilities(
        conn, listing_id=ghost_listing, seller_id=seller, buyer_account_id=buyer
    ) == frozenset()
    assert not has_capability(
        conn, listing_id=ghost_listing, seller_id=seller, buyer_account_id=buyer, capability="FULL_CONFIDENTIAL"
    )


def test_a_null_buyer_grants_nothing_even_with_a_real_active_grant_on_the_same_listing(conn) -> None:
    """directive §19/this task's own brief: "a null buyer" -- an unauthenticated caller, or a route
    that failed to resolve one, must never be answered by SOMEONE ELSE's grant. A real, active,
    FULL_CONFIDENTIAL approval for a genuine buyer sits on this exact listing while the question
    asked is about no buyer at all."""
    seller = _account(conn, f"seller-{uuid4().hex}@x.org")
    listing = _listing(conn, seller)
    real_buyer = _account(conn, f"buyer-{uuid4().hex}@x.org")
    _request(conn, listing, real_buyer, seller, status="APPROVED", level="FULL_CONFIDENTIAL")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=None) == frozenset()


def test_a_capability_the_code_has_never_heard_of_is_never_granted(conn) -> None:
    """directive §19/this task's own brief: "every disclosure level including one the code has
    never heard of." Migration 096's own CHECK on `approved_disclosure_level` makes an unrecognised
    STORED level unrepresentable as a row (deviation note, module docstring) -- proved instead at
    the boundary `authorized_capabilities`/`covers` themselves present, with no database read
    needed for that half: an unrecognised value reaching `covers()` by any future path (a level
    added to the CHECK before Python's own table is updated to match, a differently-sourced caller)
    must fail closed, never raise and never fall through to a permissive default.

    The MIRRORED question -- a caller asking about a CAPABILITY name nobody defined, rather than a
    stored level -- is asked through the real, DATABASE-BACKED `has_capability`, against the
    broadest real grant this schema can produce (`FULL_CONFIDENTIAL`, which `covers()` already
    expands to every one of `CAPABILITIES`' five names): "BOGUS" must still be refused, because it
    can never be a member of anything `covers()` returns. Asserting `"BOGUS" not in CAPABILITIES`
    alone would test the vocabulary, not the function; this calls `has_capability` itself so the
    contract under test is the one a route actually depends on."""
    assert covers("A_LEVEL_THIS_CODE_HAS_NEVER_HEARD_OF") == frozenset()
    assert covers("") == frozenset()
    assert "BOGUS" not in CAPABILITIES  # the vocabulary fact `has_capability`'s own refusal rests on

    seller = _account(conn, f"seller-{uuid4().hex}@x.org")
    listing = _listing(conn, seller)
    buyer = _account(conn, f"buyer-{uuid4().hex}@x.org")
    _request(conn, listing, buyer, seller, status="APPROVED", level="FULL_CONFIDENTIAL")
    assert not has_capability(
        conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer, capability="BOGUS"
    ), "a capability name nobody defined must be refused even against the broadest real grant"
