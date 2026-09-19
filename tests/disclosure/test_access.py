"""The one function every confidential-resource route calls (directive §12, §18). Deliberately
does NOT fold in the pre-existing global ceiling flags (location_disclosed, etc.) -- those stay
exactly where they already are, in `serialise`/`buyer_variant`/`read_document`, ANDed with this
function's answer at the call site (directive §8: "separate these concepts"). What this function
owns is the buyer/listing grant, and only that."""
from __future__ import annotations

from uuid import uuid4

from app.disclosure.access import authorized_capabilities, authorized_capabilities_bulk, has_capability


def _account(conn, email: str) -> str:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'x','active') RETURNING id", (email,))
        return str(cur.fetchone()[0])


def _listing(conn, seller_id: str | None) -> str:
    # zip/est/price/sqft (Task 1's own deviation from the plan's literal helper, task-01-report.md):
    # the plan's INSERT satisfies listing_publishable_ck's ORIGINAL three-field shape (030) but not
    # its WIDENED shape (034, already applied in this repo) -- which also requires sqft for a
    # published row -- nor listing_submittable_ck's zip/est/price for any non-draft/withdrawn row.
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, seller_id, status,"
            " zip, est, price, sqft)"
            " VALUES (%s,'Test Practice','Austin','TX','Austin','Small animal','Austin, TX','seller',%s,'published',"
            " '78701',1990,1000000,2500)"
            " RETURNING id",
            (f"test-{uuid4().hex}", seller_id),
        )
        return str(cur.fetchone()[0])


def _request(conn, listing_id, buyer_id, seller_id, *, status="PENDING", level=None, expires_at=None):
    # ::uuid (deviation from the plan's literal helper, see task-03-report.md): the plan's second
    # CASE -- `CASE WHEN %s <> 'PENDING' THEN %s END` for reviewed_by -- has two "unknown"-typed
    # branches (the seller_id text literal and the implicit ELSE NULL), and PostgreSQL's
    # unknown-type resolution defaults a CASE with only unknown branches to `text`, not to the
    # uuid column it is being assigned into -- a bare `%s` in direct column-assignment position
    # (e.g. the `status`/`level` placeholders above) gets an implicit assignment cast for free, but
    # a CASE's own resolved type is fixed *before* it reaches that assignment context, so this one
    # branch needs an explicit cast. The first CASE (reviewed_at) never hit this: `now()` is a
    # concretely-typed branch, so the pair resolves to timestamptz without help.
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id, status, approved_disclosure_level,"
            " reviewed_at, reviewed_by, expires_at)"
            " VALUES (%s,%s,%s,%s,%s, CASE WHEN %s <> 'PENDING' THEN now() END, CASE WHEN %s <> 'PENDING' THEN %s::uuid END, %s)",
            (listing_id, buyer_id, seller_id, status, level, status, status, seller_id, expires_at),
        )


def test_no_request_at_all_grants_nothing(conn) -> None:
    seller, buyer = _account(conn, "s1@x.org"), _account(conn, "b1@x.org")
    listing = _listing(conn, seller)
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_a_pending_request_grants_nothing(conn) -> None:
    seller, buyer = _account(conn, "s2@x.org"), _account(conn, "b2@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="PENDING")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_an_approved_request_grants_exactly_what_it_covers(conn) -> None:
    seller, buyer = _account(conn, "s3@x.org"), _account(conn, "b3@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="APPROVED", level="EXACT_LOCATION")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset({"EXACT_LOCATION"})
    assert has_capability(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer, capability="EXACT_LOCATION")
    assert not has_capability(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer, capability="FINANCIALS")


def test_full_confidential_grants_every_capability(conn) -> None:
    seller, buyer = _account(conn, "s4@x.org"), _account(conn, "b4@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="APPROVED", level="FULL_CONFIDENTIAL")
    from app.disclosure.levels import CAPABILITIES
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == CAPABILITIES


def test_a_denied_request_grants_nothing(conn) -> None:
    seller, buyer = _account(conn, "s5@x.org"), _account(conn, "b5@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="DENIED")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_a_revoked_request_grants_nothing_even_though_the_level_column_is_still_set(conn) -> None:
    seller, buyer = _account(conn, "s6@x.org"), _account(conn, "b6@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="REVOKED", level="FULL_CONFIDENTIAL")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_an_expired_approval_grants_nothing(conn) -> None:
    seller, buyer = _account(conn, "s7@x.org"), _account(conn, "b7@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer, seller, status="APPROVED", level="FULL_CONFIDENTIAL", expires_at="2000-01-01T00:00:00Z")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_no_buyer_at_all_grants_nothing(conn) -> None:
    seller = _account(conn, "s8@x.org")
    listing = _listing(conn, seller)
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=None) == frozenset()


def test_a_grant_on_one_listing_does_not_leak_to_another(conn) -> None:
    seller, buyer = _account(conn, "s9@x.org"), _account(conn, "b9@x.org")
    listing_x, listing_y = _listing(conn, seller), _listing(conn, seller)
    _request(conn, listing_x, buyer, seller, status="APPROVED", level="FULL_CONFIDENTIAL")
    assert authorized_capabilities(conn, listing_id=listing_y, seller_id=seller, buyer_account_id=buyer) == frozenset()


def test_bulk_matches_the_single_lookup_for_every_listing_in_one_extra_query(conn) -> None:
    seller, buyer = _account(conn, "s10@x.org"), _account(conn, "b10@x.org")
    listing_x, listing_y = _listing(conn, seller), _listing(conn, seller)
    _request(conn, listing_x, buyer, seller, status="APPROVED", level="IDENTITY")
    result = authorized_capabilities_bulk(conn, buyer_account_id=buyer, listings=[(listing_x, seller), (listing_y, seller)])
    assert result[listing_x] == frozenset({"IDENTITY"})
    assert result[listing_y] == frozenset()


def test_buyer_a_approved_does_not_leak_to_buyer_b_on_the_same_listing(conn) -> None:
    """The isolation property (directive §7), which is the point of this whole subsystem, proved
    here at this module's own boundary rather than deferred entirely to the dedicated route-level
    test the plan schedules later (Task 11 -- a separate, higher-level proof, not a reason to omit
    it here). This is a different axis from `test_a_grant_on_one_listing_does_not_leak_to_another`
    above, which holds the buyer fixed and varies the listing; this one holds the LISTING fixed and
    varies the buyer -- two buyers, one seller, one listing, which is exactly what directive §7's
    acceptance test is about: approving buyer A must not authorize buyer B on that same listing."""
    seller = _account(conn, "s11@x.org")
    buyer_a, buyer_b = _account(conn, "a11@x.org"), _account(conn, "b11@x.org")
    listing = _listing(conn, seller)
    _request(conn, listing, buyer_a, seller, status="APPROVED", level="FULL_CONFIDENTIAL")
    # Buyer B never requested at all -- the no-row-yet case, on the SAME listing buyer A now holds.
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer_a) == frozenset(
        {"IDENTITY", "EXACT_LOCATION", "UNREDACTED_IMAGES", "FINANCIALS", "FLOOR_PLANS"}
    )
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer_b) == frozenset()
    assert has_capability(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer_a, capability="FINANCIALS")
    assert not has_capability(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer_b, capability="FINANCIALS")
    # Buyer B also has an active request of their own on the SAME listing, PENDING -- asking is not
    # being granted, and buyer A's approval must not spill into buyer B's still-open row either.
    _request(conn, listing, buyer_b, seller, status="PENDING")
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=buyer_b) == frozenset()
    # The bulk form must hold the same isolation for both buyers in one call each.
    bulk_a = authorized_capabilities_bulk(conn, buyer_account_id=buyer_a, listings=[(listing, seller)])
    bulk_b = authorized_capabilities_bulk(conn, buyer_account_id=buyer_b, listings=[(listing, seller)])
    assert bulk_a[listing] == frozenset({"IDENTITY", "EXACT_LOCATION", "UNREDACTED_IMAGES", "FINANCIALS", "FLOOR_PLANS"})
    assert bulk_b[listing] == frozenset()


def test_a_seller_is_never_authorized_as_a_buyer_on_their_own_listing(conn) -> None:
    """Defence in depth: migration 096's own request_seller_is_not_buyer_ck CHECK means no `request`
    row for buyer_user_id == seller_user_id can ever exist, so this path is already unreachable via
    the table -- but a caller that mis-resolves and passes the seller's own account id as
    `buyer_account_id` must still be denied, never accidentally treated as a valid (if row-less)
    buyer that happens to have made no request."""
    seller = _account(conn, "s12@x.org")
    listing = _listing(conn, seller)
    assert authorized_capabilities(conn, listing_id=listing, seller_id=seller, buyer_account_id=seller) == frozenset()
    assert not has_capability(conn, listing_id=listing, seller_id=seller, buyer_account_id=seller, capability="IDENTITY")


def test_bulk_with_no_buyer_grants_nothing_for_every_listing(conn) -> None:
    """Fail closed (directive §19), the bulk form's own copy of `test_no_buyer_at_all_grants_nothing`:
    a `None` buyer must deny every listing in the page, not merely raise or return an empty dict."""
    seller = _account(conn, "s13@x.org")
    listing_x, listing_y = _listing(conn, seller), _listing(conn, seller)
    result = authorized_capabilities_bulk(conn, buyer_account_id=None, listings=[(listing_x, seller), (listing_y, seller)])
    assert result == {listing_x: frozenset(), listing_y: frozenset()}


def test_bulk_with_no_listings_returns_an_empty_result(conn) -> None:
    """An empty page asks no question and gets no rows back -- not an error, not a KeyError waiting
    to happen for a caller that indexes into the result by a listing_id it never sent."""
    buyer = _account(conn, "b13@x.org")
    assert authorized_capabilities_bulk(conn, buyer_account_id=buyer, listings=[]) == {}


def test_bulk_never_authorizes_a_seller_as_a_buyer_on_their_own_listings(conn) -> None:
    """The bulk form's own copy of `test_a_seller_is_never_authorized_as_a_buyer_on_their_own_listing`
    (directive §18/§19): every listing in the page belongs to the account asking "am I the buyer
    here", so the seller-exclusion filter empties the query entirely -- and the function must still
    answer with `frozenset()` per listing rather than skip straight to a query with no ids."""
    seller = _account(conn, "s14@x.org")
    listing_x, listing_y = _listing(conn, seller), _listing(conn, seller)
    result = authorized_capabilities_bulk(conn, buyer_account_id=seller, listings=[(listing_x, seller), (listing_y, seller)])
    assert result == {listing_x: frozenset(), listing_y: frozenset()}
