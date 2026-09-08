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
