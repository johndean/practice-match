"""The staff read of a seller's draft (controller amendment A-SL8, ruled 2026-09-09).

Spec §9's open question 5 asked whether the reviewer should read the draft through the seller's own
route with a second permission checked inside the handler. A-SL8 says no: a separate route with ONE
guard, because one guard per route is what `tests/auth/test_permissions.py` models — it resolves a
route's permission by the guard object's identity and cannot see a permission enforced in a handler
body, so a second one there is invisible to every drift test in the suite.

SL5 extends this module with the review queue (`GET /api/admin/listings`) and the three decisions
(`POST /api/admin/listings/{id}/decide`).
"""
from __future__ import annotations

from typing import Any

from tests.api.conftest import auth_headers


async def _draft(client: Any, member: Any) -> tuple[str, dict[str, str]]:
    """A seller's part-filled draft, and the seller's own signed headers — one account per test, so
    a caller that also needs the OWNER does not create them a second time (`account.email` is
    unique)."""
    _, cookies, headers = member(roles=("buyer", "seller"), email="al-seller@example.org")
    signed = auth_headers(cookies, headers)
    response = await client.post("/api/seller/listings", headers=signed)
    assert response.status_code == 201, response.text
    listing_id: str = response.json()["id"]
    await client.patch(f"/api/seller/listings/{listing_id}?step=1",
                       json={"name": "Hill Country Animal Hospital", "type": "Small animal", "est": "1998"},
                       headers=signed)
    return listing_id, signed


async def test_a_reviewer_reads_any_sellers_draft_through_listing_review(client: Any, conn: Any, member: Any) -> None:
    """D9's second arm, at its A-SL8 address: the reviewer opens the draft the seller submitted, and
    sees the OWNER's unblanked truth (`serialise_draft`) rather than the buyer's contract."""
    listing_id, _owner = await _draft(client, member)
    _, cookies, headers = member(roles=("staff",), email="al-staff@example.org")
    response = await client.get(f"/api/admin/listings/{listing_id}", headers=auth_headers(cookies, headers))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == listing_id
    assert body["name"] == "Hill Country Animal Hospital"   # not blanked, though name_disclosed is false
    assert body["status"] == "draft" and body["assets"] == []


async def test_the_route_carries_exactly_one_guard_and_it_is_listing_review(client: Any, conn: Any, dist: Any) -> None:
    """A-SL8 in the form the drift tests read. `listing.review` is `_STAFF`
    (`app/auth/permissions.py:38`), it is not in `AUDITED`, and the guard is a hoisted module
    constant so `permission_of` can resolve it by identity."""
    from app.api import admin_listings as AL
    from app.auth import permissions as PM
    from app.auth.deps import permission_of
    from app.main import create_app
    from tests.conftest import walk_routes

    assert permission_of(AL.REQUIRE_REVIEW) == "listing.review"
    assert PM.MATRIX["listing.review"] == frozenset({"staff", "admin"})
    assert "listing.review" not in PM.AUDITED
    paths = {path for _method, path, _route in walk_routes(create_app(dist=dist).routes)}
    assert "/api/admin/listings/{listing_id}" in paths


async def test_a_seller_may_not_read_the_review_surface(client: Any, conn: Any, member: Any) -> None:
    """The matrix does this, not the handler: `listing.review` is staff-only, so the owner of the
    listing is refused HERE and reads their own draft through `/api/seller/listings/{id}`."""
    listing_id, owner = await _draft(client, member)
    response = await client.get(f"/api/admin/listings/{listing_id}", headers=owner)
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"


async def test_an_anonymous_caller_gets_the_generic_401(client: Any, conn: Any) -> None:
    response = await client.get("/api/admin/listings/11111111-1111-1111-1111-111111111111")
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}


async def test_a_listing_that_does_not_exist_is_a_404_in_the_envelope(client: Any, conn: Any, member: Any) -> None:
    """Both arms of the read: an id that is no listing, and an id that is not a uuid at all — the
    second is this module's 404 rather than FastAPI's 422 on a `UUID` path parameter."""
    _, cookies, headers = member(roles=("staff",), email="al-staff@example.org")
    signed = auth_headers(cookies, headers)
    for path in ("/api/admin/listings/11111111-1111-1111-1111-111111111111",
                 "/api/admin/listings/not-a-uuid"):
        response = await client.get(path, headers=signed)
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "NOT_FOUND", "message": "No such listing."}}


# --- Task SL5: the review queue and the three decisions (spec 2026-09-08 D8, D12, D13) ---------


def test_the_matrix_and_route_guard_tests_still_pass_with_listing_publish_audited() -> None:
    """D8, and the three pins that could have moved with it.

    `listing.publish` joins `AUDITED` because publishing, declining or unpublishing a listing is a
    staff decision of exactly the class `users.decide` is. `listing.review` stays OUT for the
    reason `users.review` is out (one audit row per poll of a tab into a table whose triggers
    refuse DELETE), `REAUTH` is untouched BY THIS PLAN — publishing is not in the class of revoke /
    role grant / token mint / licence decision — and `ADMINISTRATIVE` does not move WITH IT: it is
    DERIVED from the matrix and `listing.publish` was already `_STAFF`.

    SL9 merge (2026-09-09): `main`'s Task I5d joined `REAUTH` with `signups.notify` (the launch
    mail is at least as consequential as a revocation) independently of this plan, which is why
    the set below and `ADMINISTRATIVE`'s count (16 before that merge, matching the three `signups.*`
    permissions it also added — `tests/auth/test_matrix.py`'s own 19-element pin is the same
    number, read the same way) both carry it now; `listing.publish` joining `AUDITED` moved
    neither."""
    from app.auth import permissions as PM

    assert "listing.publish" in PM.AUDITED
    assert "listing.review" not in PM.AUDITED and "listing.manage_own" not in PM.AUDITED
    assert PM.REAUTH == frozenset({"licence.decide", "engine.activate", "roles.grant", "tokens.manage", "users.revoke", "signups.notify"})
    assert "listing.publish" in PM.ADMINISTRATIVE and len(PM.ADMINISTRATIVE) == 19


async def _staff(client: Any, member: Any) -> dict[str, str]:
    _, cookies, headers = member(roles=("staff",), email="al-staff@example.org")
    return auth_headers(cookies, headers)


async def _submitted(client: Any, member: Any) -> tuple[str, dict[str, str]]:
    """A seller's listing, complete and in review — what the queue exists to show. Complete now
    means `sqft` too (A-SL33 (1)): `REQUIRED_TO_SUBMIT` names it beside price, so a listing this
    helper builds can also reach a real publish, which most of this module's tests go on to do."""
    listing_id, signed = await _draft(client, member)
    await client.patch(f"/api/seller/listings/{listing_id}?step=2",
                       json={"city": "Cedar Park", "zip": "78613"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": "1450000"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"sqft": "3000"}, headers=signed)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)).status_code == 200
    return listing_id, signed


def _row(conn: Any, listing_id: str) -> tuple[Any, ...]:
    with conn.cursor() as cur:
        cur.execute("SELECT status, state, market, slug FROM listing WHERE id=%s", (listing_id,))
        row: tuple[Any, ...] = cur.fetchone()
    return row


def _audit(conn: Any, listing_id: str) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute("SELECT action, before, after, reason FROM audit_log WHERE target_type='listing'"
                    " AND target_id=%s ORDER BY id", (str(listing_id),))
        rows: list[tuple[Any, ...]] = cur.fetchall()
    return rows


def _outbox(conn: Any) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute("SELECT template, to_email, params, idempotency_key FROM email_outbox ORDER BY id")
        rows: list[tuple[Any, ...]] = cur.fetchall()
    return rows


async def test_the_queue_returns_every_listing_and_narrows_by_status(
    client: Any, conn: Any, member: Any
) -> None:
    """D24, and John's standing rule for the admin surface: every Admin tab shows real database
    data. A bad `status=` is a 422 in the envelope, never `200 {"items": []}` — a typo in the tab
    must not read as "no such listings" (the `admin_users.py` BadFilter lesson, F10)."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    body = (await client.get("/api/admin/listings", headers=staff)).json()
    assert [item["id"] for item in body["items"]] == [listing_id]
    assert body["items"][0]["status"] == "in_review"
    assert body["items"][0]["name"] == "Hill Country Animal Hospital"
    assert body["items"][0]["seller_name"] == "Dr. Rachel Mendes"
    assert body["next_cursor"] is None

    assert [item["id"] for item in (await client.get("/api/admin/listings?status=in_review", headers=staff)).json()["items"]] == [listing_id]
    assert (await client.get("/api/admin/listings?status=published", headers=staff)).json()["items"] == []

    refused = await client.get("/api/admin/listings?status=flagged", headers=staff)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "BAD_FILTER"


async def test_the_queue_is_keyset_paged_and_walks_every_row_exactly_once(
    client: Any, conn: Any, member: Any
) -> None:
    """`/api/admin/users`'s own shape: `(updated_at, id)`, so tied timestamps do not drop a row."""
    listing_id, signed = await _submitted(client, member)
    others = [(await client.post("/api/seller/listings", headers=signed)).json()["id"] for _ in range(2)]
    staff = await _staff(client, member)

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(3):
        query = "/api/admin/listings?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = (await client.get(query, headers=staff)).json()
        seen += [item["id"] for item in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == sorted([listing_id, *others]) and len(seen) == 3
    assert cursor is None

    for bad in ("nonsense", "2026-09-09T00:00:00Z|not-a-uuid"):
        refused = await client.get(f"/api/admin/listings?cursor={bad}", headers=staff)
        assert refused.status_code == 422 and refused.json()["error"]["code"] == "BAD_CURSOR", bad
    bad_limit = await client.get("/api/admin/listings?limit=many", headers=staff)
    assert bad_limit.status_code == 422 and bad_limit.json()["error"]["code"] == "BAD_FILTER"
    assert len((await client.get("/api/admin/listings?limit=99999", headers=staff)).json()["items"]) == 3


async def test_a_buyer_and_a_seller_cannot_read_the_queue(client: Any, conn: Any, member: Any) -> None:
    """The matrix does this: `listing.review` is staff/admin (permissions.py:38)."""
    _listing_id, owner = await _draft(client, member)
    _, cookies, headers = member(roles=("buyer",), email="al-buyer@example.org")
    for signed in (owner, auth_headers(cookies, headers)):
        response = await client.get("/api/admin/listings", headers=signed)
        assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"


async def test_publish_needs_state_and_market_on_the_first_publish_and_not_after(
    client: Any, conn: Any, member: Any
) -> None:
    """D12, John's ruled default Q2: the approved step 2 collects a city and a ZIP, so the reviewer
    supplies the state and the metro at the FIRST publish. `030`'s publishable CHECK would refuse a
    listing without them anyway; answering it here means the reviewer is told which two fields, in
    the envelope, instead of meeting a 500."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    refused = await client.post(f"/api/admin/listings/{listing_id}/decide",
                                json={"action": "publish"}, headers=staff)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "FIELDS_REQUIRED"
    assert "state" in refused.json()["error"]["message"] and "market" in refused.json()["error"]["message"]
    assert _row(conn, listing_id)[0] == "in_review"

    published = await client.post(f"/api/admin/listings/{listing_id}/decide",
                                  json={"action": "publish", "state": "TX", "market": "Austin, TX"},
                                  headers=staff)
    assert published.status_code == 200 and published.json()["status"] == "published"
    # A-SL19 (9), Info-4: the full draft, so an admin tab can link to what it just published
    # without a re-read.
    assert published.json()["slug"] == f"hill-country-animal-hospital-{listing_id[:8]}"
    status, state, market, _slug = _row(conn, listing_id)
    assert (status, state, market) == ("published", "TX", "Austin, TX")
    with conn.cursor() as cur:
        cur.execute("SELECT area FROM listing WHERE id=%s", (listing_id,))
        assert cur.fetchone()[0] == "Cedar Park"      # the step-2 PATCH's own, untouched

    # ...and a later republish needs neither: the row already has both.
    assert (await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "unpublish"},
                              headers=staff)).status_code == 200
    again = await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "publish"}, headers=staff)
    assert again.status_code == 200 and _row(conn, listing_id)[0] == "published"


async def test_publish_also_requires_square_footage_named_in_the_envelope(client: Any, conn: Any, member: Any) -> None:
    """A-SL33 (1): the SL8 review's Critical finding, fixed at the decide layer. `logic.js` calls
    `p.sqft.toLocaleString()` with no guard at six sites Browse renders a practice from, so a
    listing published with no floor area is not a blank field, it is a blank app the moment Browse
    next renders. `_submitted()` now makes a genuinely publishable listing (A-SL33's fixture fix);
    this proves the refusal by CLEARING sqft first, on BOTH a first publish and a republish — the
    database CHECK (034) applies to every transition to 'published', not only the first, so the
    friendly envelope check does too."""
    listing_id, signed = await _submitted(client, member)
    staff = await _staff(client, member)
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"sqft": ""}, headers=signed)

    refused = await client.post(f"/api/admin/listings/{listing_id}/decide",
                                json={"action": "publish", "state": "TX", "market": "Austin, TX"}, headers=staff)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "FIELDS_REQUIRED"
    assert "square footage" in refused.json()["error"]["message"]
    assert _row(conn, listing_id)[0] == "in_review", "the refused write must not have landed"

    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"sqft": "3000"}, headers=signed)
    published = await client.post(f"/api/admin/listings/{listing_id}/decide",
                                  json={"action": "publish", "state": "TX", "market": "Austin, TX"}, headers=staff)
    assert published.status_code == 200 and _row(conn, listing_id)[0] == "published"

    # A REPUBLISH — `state` is already set, so this is not the first-publish branch — is refused
    # the same way if a later edit clears sqft again.
    await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "unpublish"}, headers=staff)
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"sqft": ""}, headers=signed)
    refused_again = await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "publish"}, headers=staff)
    assert refused_again.status_code == 422 and refused_again.json()["error"]["code"] == "FIELDS_REQUIRED"
    assert _row(conn, listing_id)[0] == "in_review"


async def test_publish_rewrites_the_slug_once_and_never_again(client: Any, conn: Any, member: Any) -> None:
    """D13. `listing-<id>` becomes the name in slug form plus the first eight characters of the id,
    so a seller's "Hill Country Animal Hospital" can never collide with a seed slug of the same
    name and can never make the next `seed_listings.py` run refuse (exit 5). Only on the FIRST
    publish: a republished listing keeps the slug buyers may have bookmarked."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    assert _row(conn, listing_id)[3] == f"listing-{listing_id}"
    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "publish", "state": "TX", "market": "Austin, TX"}, headers=staff)
    slug = _row(conn, listing_id)[3]
    assert slug == f"hill-country-animal-hospital-{listing_id[:8]}"

    await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "unpublish"}, headers=staff)
    await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "publish"}, headers=staff)
    assert _row(conn, listing_id)[3] == slug


async def test_decline_requires_a_reason(client: Any, conn: Any, member: Any) -> None:
    """`admin_users.py:109`'s pattern: a decline is a decision the seller is owed a reason for, and
    a blank one is a 422 rather than a row with an empty note."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    for body in ({"action": "decline"}, {"action": "decline", "reason": "   "}):
        refused = await client.post(f"/api/admin/listings/{listing_id}/decide", json=body, headers=staff)
        assert refused.status_code == 422 and refused.json()["error"]["code"] == "NOTE_REQUIRED"
    assert _row(conn, listing_id)[0] == "in_review"

    declined = await client.post(f"/api/admin/listings/{listing_id}/decide",
                                 json={"action": "decline", "reason": "Revenue figures need a source."},
                                 headers=staff)
    assert declined.status_code == 200 and _row(conn, listing_id)[0] == "declined"
    assert _audit(conn, listing_id)[-1][3] == "decline: Revenue figures need a source."


async def test_unpublish_moves_a_published_listing_to_paused(client: Any, conn: Any, member: Any) -> None:
    """The design's own third action (logic.js:1063-1067), and only from `published`."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    refused = await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "unpublish"}, headers=staff)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "STATE"

    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "publish", "state": "TX", "market": "Austin, TX"}, headers=staff)
    assert (await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "unpublish"},
                              headers=staff)).status_code == 200
    assert _row(conn, listing_id)[0] == "paused"


async def test_an_action_the_listings_tab_does_not_offer_is_refused_in_the_envelope(
    client: Any, conn: Any, member: Any
) -> None:
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    # A-SL19 (5): `422 BAD_ACTION`, the code `/api/admin/users` already answers for the same
    # mistake on the same tab family (`admin_users.py`'s `BadAction`).
    refused = await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "withdraw"}, headers=staff)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "BAD_ACTION"
    assert "publish" in refused.json()["error"]["message"]


async def test_every_decide_branch_writes_exactly_one_audit_row_named_after_the_permission(
    client: Any, conn: Any, member: Any
) -> None:
    """D8. Three branches, one action name — `listing.publish`, the permission's own — so
    `test_every_audited_action_is_named_after_a_permission` is satisfied with nothing added to
    `MULTI_ACTION_PERMISSIONS` or `CASCADED_ACTIONS`, and an auditor greps one string."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "publish", "state": "TX", "market": "Austin, TX"}, headers=staff)
    await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "unpublish"}, headers=staff)
    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "publish"}, headers=staff)
    decisions = [row for row in _audit(conn, listing_id) if row[0] == "listing.publish"]
    assert [(row[1], row[2], row[3]) for row in decisions] == [
        ({"status": "in_review"}, {"status": "published"}, "publish"),
        ({"status": "published"}, {"status": "paused"}, "unpublish"),
        ({"status": "paused"}, {"status": "published"}, "publish"),
    ]


def test_the_decide_handler_writes_its_own_audit_row() -> None:
    """The drift test's own rule (`test_audited_permissions_are_written_by_their_handlers` reads
    `inspect.getsource(route.endpoint)`), asserted HERE too so a refactor that moves the write into
    a helper fails at the task that owns the handler rather than three files away."""
    import inspect

    from app.api.admin_listings import decide_listing

    assert "audit.write(" in inspect.getsource(decide_listing)


async def test_publish_and_decline_enqueue_their_template_to_the_seller(
    client: Any, conn: Any, member: Any
) -> None:
    """One row each, keyed on the decision, so a reviewer who clicks twice sends one email."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "decline", "reason": "Revenue figures need a source."}, headers=staff)
    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "publish", "state": "TX", "market": "Austin, TX"}, headers=staff)
    rows = [row for row in _outbox(conn) if row[0].startswith("listing_")]
    assert [(row[0], row[1]) for row in rows] == [
        ("listing_submitted", "al-seller@example.org"),
        ("listing_declined", "al-seller@example.org"),
        ("listing_published", "al-seller@example.org"),
    ]
    assert rows[1][2] == {"reason": "Revenue figures need a source."}
    assert rows[1][3] == f"{listing_id}:listing_declined:in_review->declined"
    assert rows[2][3] == f"{listing_id}:listing_published:declined->published"
    # ...and an unpublish tells nobody: the design's admin footnote calls it "immediate and
    # reversible", and the seller sees it on their own dashboard.
    await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "unpublish"}, headers=staff)
    assert len([row for row in _outbox(conn) if row[0].startswith("listing_")]) == 3


async def test_a_seed_listing_with_no_owner_is_decided_without_a_mail(
    client: Any, conn: Any, member: Any
) -> None:
    """`listing.seller_id` is nullable by D5 — a production seed row belongs to the VIN Foundation,
    not to a person — so a decision on one has nobody to write to. It is still audited."""
    staff = await _staff(client, member)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, name, city, state, zip, area, type, market, source,"
                    " status, est, price, sqft) VALUES ('unowned','Unowned','Austin','TX','78701','Austin',"
                    "'Small animal','Austin, TX','seed','in_review',2015,750000,3000) RETURNING id")
        listing_id = str(cur.fetchone()[0])
    response = await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "publish"}, headers=staff)
    assert response.status_code == 200 and _row(conn, listing_id)[0] == "published"
    assert [row[0] for row in _audit(conn, listing_id)] == ["listing.publish"]
    assert [row for row in _outbox(conn) if row[0].startswith("listing_")] == []
    # ...and the queue names no seller for it rather than inventing one (D24: unbuilt rows are
    # absent, never faked). This is also `sellers_for`'s empty arm — a page of unowned seed rows.
    queue = (await client.get("/api/admin/listings", headers=staff)).json()
    assert [(item["id"], item["seller_id"], item["seller_name"]) for item in queue["items"]] == [
        (listing_id, None, None)]


async def test_a_decision_on_an_unowned_or_missing_listing_is_404(
    client: Any, conn: Any, member: Any
) -> None:
    """Staff see every listing, so there is no ownership scope here — but an id that names none is
    a 404 in the envelope, and so is an id that is not a uuid at all."""
    staff = await _staff(client, member)
    for path in ("/api/admin/listings/11111111-1111-1111-1111-111111111111/decide",
                 "/api/admin/listings/not-a-uuid/decide"):
        response = await client.post(path, json={"action": "publish"}, headers=staff)
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "NOT_FOUND", "message": "No such listing."}}


async def test_every_decision_drops_the_listings_cache_after_the_commit(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """D16: a publish must reach Browse at once and an unpublish must leave it at once. AFTER the
    commit — dropping the key while the write was uncommitted would let a concurrent read re-cache
    the old payload for the full TTL."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)

    async def _drops(body: dict[str, Any]) -> bool:
        redis.set("listings:v1:::50", b'{"items": []}')
        redis.set("session:keep-me", b"x")
        assert (await client.post(f"/api/admin/listings/{listing_id}/decide", json=body, headers=staff)).status_code == 200
        assert redis.get("session:keep-me") == b"x"
        return redis.get("listings:v1:::50") is None

    # All four decisions the three branches can make, in an order the lifecycle allows.
    assert await _drops({"action": "decline", "reason": "Revenue figures need a source."})
    assert await _drops({"action": "publish", "state": "TX", "market": "Austin, TX"})
    assert await _drops({"action": "unpublish"})
    assert await _drops({"action": "publish"})


async def test_the_buyer_surface_shows_a_listing_only_while_it_is_published(
    client: Any, conn: Any, member: Any
) -> None:
    """The whole lifecycle, through the PUBLIC route: `GET /api/listings` filters
    `status = 'published'`, so the reviewer's decision alone is what puts a listing on the market
    and takes it off again (D3's other half)."""
    listing_id, signed = await _submitted(client, member)
    staff = await _staff(client, member)

    async def _on_the_market() -> bool:
        body = (await client.get("/api/listings", headers=signed)).json()
        return listing_id in [item["id"] for item in body["items"]]

    assert not await _on_the_market()
    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "publish", "state": "TX", "market": "Austin, TX"}, headers=staff)
    assert await _on_the_market()
    # ...and an edit takes it straight back off (D3, John's ruling), until it is approved again.
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"rooms": "6"}, headers=signed)
    assert not await _on_the_market()
    await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "publish"}, headers=staff)
    assert await _on_the_market()


# --- Fix round 1 (A-SL19) ------------------------------------------------------------------------


async def test_the_reviewers_state_and_market_are_validated_before_any_write(
    client: Any, conn: Any, member: Any
) -> None:
    """A-SL19 (2), Major-2. D12 makes these two the reviewer's ONLY input, and the approved design
    reads the state back out of the market string — `stateOf(market)` is
    `(market || "Austin, TX").split(", ")[1] || "TX"` (logic.js:805), which the buyer detail's
    subtitle and its "General location" row render (A12.8/A12.9). So an unvalidated "Phoenix"
    publishes a Phoenix practice the detail labels "Phoenix, TX", and a malformed `market` also
    makes the listing unfilterable, because Browse pages on it."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    for body in (
        {"action": "publish", "state": "XX", "market": "Phoenix, XX"},   # no such USPS state
        {"action": "publish", "state": "tx", "market": "Austin, tx"},    # lower case is not a code
        {"action": "publish", "state": "AZ", "market": "Phoenix"},       # no ", ST" suffix at all
        {"action": "publish", "state": "AZ", "market": "P, AZ"},         # a one-character city
        {"action": "publish", "state": "TX", "market": "Phoenix, AZ"},   # the suffix disagrees
    ):
        refused = await client.post(f"/api/admin/listings/{listing_id}/decide", json=body, headers=staff)
        assert refused.status_code == 422, body
        assert refused.json()["error"]["code"] == "BAD_FIELD", body
    # ...before any write: the row is untouched by all five.
    assert _row(conn, listing_id) == ("in_review", None, None, f"listing-{listing_id}")

    # The review's own case, the right way round: a Phoenix practice in Arizona.
    ok = await client.post(f"/api/admin/listings/{listing_id}/decide",
                           json={"action": "publish", "state": "AZ", "market": "Phoenix, AZ"}, headers=staff)
    assert ok.status_code == 200
    assert _row(conn, listing_id)[1:3] == ("AZ", "Phoenix, AZ")


def test_the_state_codes_are_the_fifty_plus_dc() -> None:
    """A-SL19 (2): a module constant, not a regex — `^[A-Z]{2}$` accepts `XX`, and the reviewer's
    two characters end up in the buyer detail's own state label."""
    from app.api.admin_listings import USPS_STATES

    assert len(USPS_STATES) == 51
    assert {"TX", "AZ", "DC", "CA", "NY", "WY"} <= USPS_STATES
    assert "XX" not in USPS_STATES and "PR" not in USPS_STATES


async def test_the_first_publish_stamps_listed_at_and_a_republish_does_not(
    client: Any, conn: Any, member: Any
) -> None:
    """A-SL19 (3), Major-3. `listed_at` is Browse's SORT KEY and keyset cursor (`ORDER BY listed_at
    DESC, id DESC`, `listing_page_idx`), not only the "listed 3 days ago" label — so a draft
    created in March and published today would otherwise land mid-list, where no buyer paging
    "newest first" would ever meet it as new. Stamped on the FIRST publish only: a republish after
    review keeps the date buyers have already seen."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET listed_at = now() - interval '180 days' WHERE id=%s", (listing_id,))

    def _listed_at() -> Any:
        with conn.cursor() as cur:
            cur.execute("SELECT listed_at FROM listing WHERE id=%s", (listing_id,))
            return cur.fetchone()[0]

    stale = _listed_at()
    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "publish", "state": "TX", "market": "Austin, TX"}, headers=staff)
    fresh = _listed_at()
    assert fresh > stale, "the first publish is when a listing is listed"

    await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "unpublish"}, headers=staff)
    await client.post(f"/api/admin/listings/{listing_id}/decide", json={"action": "publish"}, headers=staff)
    assert _listed_at() == fresh, "a republish is not a new listing"


async def test_a_publish_enqueues_no_reason(client: Any, conn: Any, member: Any) -> None:
    """A-SL19 (6), Minor-3. `listing_published` declares no params, so a `reason` passed with it was
    a reviewer's free text persisted in `email_outbox.params` for a mail that can never show it."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "publish", "state": "TX", "market": "Austin, TX",
                            "reason": "Looks good to me."}, headers=staff)
    rows = {row[0]: row[2] for row in _outbox(conn)}
    assert rows["listing_published"] == {}


async def test_decide_returns_the_full_draft_of_the_decided_listing(
    client: Any, conn: Any, member: Any
) -> None:
    """A-SL19 (9), Info-4. The seller routes return the whole `serialise_draft`; this one returned
    `{"id", "status"}`, so an admin tab could not link to the listing it had just published without
    a second read — and the slug it needs for that link is written by this very request."""
    listing_id, _signed = await _submitted(client, member)
    staff = await _staff(client, member)
    body = (await client.post(f"/api/admin/listings/{listing_id}/decide",
                              json={"action": "publish", "state": "TX", "market": "Austin, TX"},
                              headers=staff)).json()
    assert body["id"] == listing_id and body["status"] == "published"
    assert body["slug"] == f"hill-country-animal-hospital-{listing_id[:8]}"
    assert body["state"] == "TX" and body["market"] == "Austin, TX"
    assert body["name"] == "Hill Country Animal Hospital" and body["assets"] == []


async def test_the_draft_carries_the_latest_decline_reason(client: Any, conn: Any, member: Any) -> None:
    """A-SL19 (9), Info-3. The seller had no in-app way to read why a listing was declined — the
    reason reached them by email only, and the Declined pill explained nothing. `serialise_draft`
    now carries the latest decline's own words (and null when there has been no decline), which is
    what SL7 feeds the design's per-listing note with."""
    listing_id, signed = await _submitted(client, member)
    staff = await _staff(client, member)
    assert (await client.get(f"/api/seller/listings/{listing_id}", headers=signed)).json()["decline_reason"] is None

    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "decline", "reason": "Revenue figures need a source."}, headers=staff)
    body = (await client.get(f"/api/seller/listings/{listing_id}", headers=signed)).json()
    assert body["status"] == "declined"
    # The reviewer's own words, without the audit row's `<action>: ` prefix.
    assert body["decline_reason"] == "Revenue figures need a source."

    # ...and the LATEST of them, when a listing has been round the loop twice.
    await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)
    await client.post(f"/api/admin/listings/{listing_id}/decide",
                      json={"action": "decline", "reason": "Still no source."}, headers=staff)
    assert (await client.get(f"/api/seller/listings/{listing_id}", headers=signed)).json()["decline_reason"] == "Still no source."
    # The reviewer reads the same field on the same draft (one serialiser, one contract).
    assert (await client.get(f"/api/admin/listings/{listing_id}", headers=staff)).json()["decline_reason"] == "Still no source."


async def test_a_body_pydantic_refuses_is_the_a5_envelope_on_both_decide_routes(
    client: Any, conn: Any, member: Any
) -> None:
    """A-SL19 (10), Concern 5 / Info-6. A body FastAPI itself refuses — a field of the wrong type, a
    string past its `max_length`, an unknown field — must answer decision A5's envelope, never
    FastAPI's `{"detail": [...]}`, on the admin surface as everywhere else.

    NOTE for the controller: the app-wide `RequestValidationError` handler A-SL19 (10) asks for
    ALREADY EXISTS — `app/auth/deps.py:158-167`, installed by `deps.install(app)` since Task I4 fix
    round 1 (Minor 1) — and its code is `INVALID_REQUEST`, which `app/api/webhooks.py:90` and six
    assertions across `tests/api/test_auth.py` and `tests/api/test_applications.py` already pin for
    signup, sign-in, the applications surface and the Resend webhook. Renaming it to `BAD_BODY`
    would change the refusal code of every route in the app from inside an SL5 fix round, so this
    test pins the ENVELOPE (which is what the ruling is for) and the existing code. See the report."""
    listing_id, _signed = await _submitted(client, member)
    account_id, cookies, headers = member(roles=("admin",), email="al-admin@example.org")
    admin = auth_headers(cookies, headers)
    for path, body in (
        (f"/api/admin/listings/{listing_id}/decide", {"action": 3}),
        (f"/api/admin/listings/{listing_id}/decide", {"action": "publish", "state": "TEXAS"}),
        # A-SL19 (10): `Decision` forbids unknown fields, so a typo is refused rather than ignored.
        (f"/api/admin/listings/{listing_id}/decide", {"action": "publish", "reasons": "typo"}),
        (f"/api/admin/users/{account_id}/decide", {"action": ["approve"]}),
    ):
        response = await client.post(path, json=body, headers=admin)
        assert response.status_code == 422, (path, body)
        assert set(response.json()) == {"error"}, (path, body)
        assert set(response.json()["error"]) == {"code", "message"}, (path, body)
        assert response.json()["error"]["code"] == "INVALID_REQUEST", (path, body)


# --- Task B9: publish enqueues geocoding when there is no practice_location row -----------
async def test_publish_enqueues_geocode_task_when_listing_has_no_practice_location(
    client: Any, conn: Any, member: Any, monkeypatch: Any
) -> None:
    """Task B9: when a listing is published and has no practice_location row, the geocode
    task is enqueued."""
    listing_id, _signed = await _submitted(client, member)
    account_id, cookies, headers = member(roles=("admin",), email="al-admin@example.org")
    admin = auth_headers(cookies, headers)

    enqueued = []
    def fake_send_task(name, args=None, **kw):
        enqueued.append((name, args))

    from app.tasks.celery_app import celery_app
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    response = await client.post(f"/api/admin/listings/{listing_id}/decide",
                                json={"action": "publish", "state": "TX", "market": "Austin, TX"},
                                headers=admin)
    assert response.status_code == 200

    # Check that geocode_listing was enqueued
    assert ("census.geocode_listing", [str(listing_id)]) in enqueued


async def test_publish_does_not_enqueue_geocode_when_practice_location_exists(
    client: Any, conn: Any, member: Any, monkeypatch: Any
) -> None:
    """Task B9: when a listing is published and already has a practice_location row,
    the geocode task is NOT enqueued."""
    listing_id, _signed = await _submitted(client, member)
    with conn.cursor() as cur:
        # Add a practice_location row
        cur.execute("INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoder_vintage, geocoded_at) "
                        "VALUES (%s, %s, %s, %s, now()),",
                    (listing_id, "hash1", "rooftop", "Current_Current"))

    account_id, cookies, headers = member(roles=("admin",), email="al-admin@example.org")
    admin = auth_headers(cookies, headers)

    enqueued = []
    def fake_send_task(name, args=None, **kw):
        enqueued.append((name, args))

    from app.tasks.celery_app import celery_app
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    response = await client.post(f"/api/admin/listings/{listing_id}/decide",
                                json={"action": "publish", "state": "TX", "market": "Austin, TX"},
                                headers=admin)
    assert response.status_code == 200

    # Check that geocode_listing was NOT enqueued
    assert ("census.geocode_listing", [str(listing_id)]) not in enqueued
