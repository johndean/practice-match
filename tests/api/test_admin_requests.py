"""GET /api/admin/requests — the Admin > Requests tab's first real data (Task ADMIN-REQUESTS,
spec `docs/superpowers/specs/2026-09-21-request-oversight-thread-design.md`, "Two prerequisites").

This is `request.oversee`'s FIRST call site (`app/auth/permissions.py:52`, declared and enforced
nowhere until this route) and the first admin API for disclosure requests at all — `app/api/
requests.py` is the buyer's own door, `app/api/seller_requests.py` is the seller's own inbox, and
neither lets staff see across both. `app/api/admin_users.py::list_users` is the shape this mirrors:
a keyset `(requested_at, id)` cursor so tied timestamps never drop a row, a `counts` object beside
`items` computed over the WHOLE table and served on the FIRST page only (a cursored page answers
`counts: null`, the badge describing the whole table rather than one page of it), and NOT audited —
`admin_listings.py`'s own reason for `listing.review`, restated here for `request.oversee`: reading
a queue is a poll, and one audit row per poll into a table whose triggers refuse DELETE is the leak
I5 fix round 1 closed once already.

**Identity, deliberately.** A row names the buyer (`app/disclosure/requests.py::list_inbox`'s own
`buyer_name` — display name, falling back to the email, never a fabricated person), the SELLER the
same way (a second account join `list_inbox` has no reason to carry, since a seller's own inbox
already knows who they are), and the practice (`admin/listings.ts`'s own `item.name || label ||
'Untitled listing'` idiom, `label` composed from `type`/`city`). Staff may see both parties —
`app/api/requests.py::_BUYER_HIDDEN` exists because a BUYER must never learn a seller's identity,
and nothing here is that route.

**What is deliberately NOT served.** The design's own Requests ("activity") tab renders four
columns — Request, Practice, Status, Age — and its own footnote is explicit: "Message contents are
visible only in an abuse investigation, and every such view is logged." Serving `request.message`
on a general list a reviewer polls routinely would make that sentence false on the day this route
shipped, so this route never selects it — composing an investigation-gated single-request read is
future work, not a silent grant here. `denial_reason` (the seller's own words on a DENIED row) has
no column on the design's four-column table either and is left out for the identical "serve what
the tab actually renders and no more" reason, not because it is sensitive."""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.api.conftest import auth_headers


async def _listing(conn, client, seller_headers, *, name="Test Practice", city="Austin") -> str:
    """A published listing owned by whoever `seller_headers` signs in as — `test_requests.py`'s
    own `_seller_listing` helper, widened to take a name/city so more than one listing can be told
    apart on the admin queue."""
    response = await client.post("/api/seller/listings", headers=seller_headers)
    listing_id = response.json()["id"]
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing SET status = 'published', name = %s, city = %s, state = 'TX', zip = '78701',"
            " area = %s, market = %s, type = 'Small animal', est = 2010, price = 1000000, sqft = 3000"
            " WHERE id = %s",
            (name, city, city, f"{city}, TX", listing_id),
        )
    return listing_id


async def _request(client, buyer_headers, listing_id, *, message="Tell me more") -> str:
    response = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id, "message": message})
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_staff_lists_requests_across_sellers_and_buyers(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-admreq1@example.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _listing(conn, client, seller_headers, name="Cedar Park Animal Hospital", city="Cedar Park")
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-admreq1@example.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    request_id = await _request(client, buyer_headers, listing_id)

    _staff_id, staff_cookies, staff_hdr = member(("staff",), email="staff-admreq1@example.org")
    response = await client.get("/api/admin/requests", headers=auth_headers(staff_cookies, staff_hdr))
    assert response.status_code == 200, response.text
    body = response.json()
    item = next(r for r in body["items"] if r["id"] == request_id)
    assert item["status"] == "PENDING"
    assert item["listing_id"] == listing_id
    assert item["listing_name"] == "Cedar Park Animal Hospital"
    assert item["listing_city"] == "Cedar Park"
    assert item["buyer_name"] == "Dr. Rachel Mendes"
    assert item["seller_name"] == "Dr. Rachel Mendes"
    assert item["buyer_user_id"] and item["seller_user_id"]


@pytest.mark.asyncio
async def test_a_buyer_cannot_read_the_admin_queue(client, member) -> None:
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-admreq2@example.org")
    response = await client.get("/api/admin/requests", headers=auth_headers(b_cookies, b_hdr))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_seller_cannot_read_the_admin_queue(client, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-admreq2@example.org")
    response = await client.get("/api/admin/requests", headers=auth_headers(s_cookies, s_hdr))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_is_refused(client) -> None:
    response = await client.get("/api/admin/requests")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_the_counts_describe_the_whole_table_not_the_page(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-admreq3@example.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_a = await _listing(conn, client, seller_headers, name="Practice A", city="Austin")
    listing_b = await _listing(conn, client, seller_headers, name="Practice B", city="Buda")
    _b1, b1_cookies, b1_hdr = member(("buyer",), email="buyer-admreq3a@example.org")
    _b2, b2_cookies, b2_hdr = member(("buyer",), email="buyer-admreq3b@example.org")
    pending_id = await _request(client, auth_headers(b1_cookies, b1_hdr), listing_a)
    denied_id = await _request(client, auth_headers(b2_cookies, b2_hdr), listing_b)
    await client.post(f"/api/seller/requests/{denied_id}/decide", headers=seller_headers, json={"action": "deny", "reason": "Not a fit"})

    _staff_id, staff_cookies, staff_hdr = member(("staff",), email="staff-admreq3@example.org")
    staff_headers = auth_headers(staff_cookies, staff_hdr)
    first_page = await client.get("/api/admin/requests?limit=1", headers=staff_headers)
    assert first_page.status_code == 200
    counts = first_page.json()["counts"]
    assert counts is not None and counts["pending"] >= 1 and counts["total"] >= 2

    cursor = first_page.json()["next_cursor"]
    assert cursor is not None
    second_page = await client.get(f"/api/admin/requests?limit=1&cursor={cursor}", headers=staff_headers)
    assert second_page.status_code == 200
    # A page past the first answers no counts at all (the badge describes the whole table, which a
    # paging caller already holds) — `admin_users.py`'s own M-1 economy, mirrored here.
    assert second_page.json()["counts"] is None
    seen_ids = {r["id"] for r in first_page.json()["items"]} | {r["id"] for r in second_page.json()["items"]}
    assert {pending_id, denied_id} <= seen_ids


@pytest.mark.asyncio
async def test_pagination_walks_every_row_via_cursor(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-admreq4@example.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    ids = []
    for i in range(3):
        listing_id = await _listing(conn, client, seller_headers, name=f"Practice {i}", city="Austin")
        _bid, b_cookies, b_hdr = member(("buyer",), email=f"buyer-admreq4-{i}@example.org")
        ids.append(await _request(client, auth_headers(b_cookies, b_hdr), listing_id))

    _staff_id, staff_cookies, staff_hdr = member(("staff",), email="staff-admreq4@example.org")
    staff_headers = auth_headers(staff_cookies, staff_hdr)
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        query = "/api/admin/requests?limit=1" + (f"&cursor={cursor}" if cursor else "")
        page = (await client.get(query, headers=staff_headers)).json()
        seen.extend(r["id"] for r in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert set(ids) <= set(seen)
    assert len(seen) == len(set(seen))  # no id duplicated across pages


@pytest.mark.asyncio
async def test_message_and_denial_reason_are_not_served(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-admreq5@example.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _listing(conn, client, seller_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-admreq5@example.org")
    request_id = await _request(client, auth_headers(b_cookies, b_hdr), listing_id, message="Confidential ask")
    await client.post(f"/api/seller/requests/{request_id}/decide", headers=seller_headers,
                      json={"action": "deny", "reason": "Internal seller reason"})

    _staff_id, staff_cookies, staff_hdr = member(("staff",), email="staff-admreq5@example.org")
    response = await client.get("/api/admin/requests", headers=auth_headers(staff_cookies, staff_hdr))
    item = next(r for r in response.json()["items"] if r["id"] == request_id)
    assert "message" not in item and "denial_reason" not in item


@pytest.mark.asyncio
async def test_listing_the_admin_queue_is_not_audited(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-admreq6@example.org")
    listing_id = await _listing(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-admreq6@example.org")
    await _request(client, auth_headers(b_cookies, b_hdr), listing_id)
    _staff_id, staff_cookies, staff_hdr = member(("staff",), email="staff-admreq6@example.org")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log")
        before = cur.fetchone()[0]
    await client.get("/api/admin/requests", headers=auth_headers(staff_cookies, staff_hdr))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log")
        after = cur.fetchone()[0]
    assert after == before


@pytest.mark.asyncio
async def test_a_malformed_cursor_is_refused(client, member) -> None:
    _staff_id, staff_cookies, staff_hdr = member(("staff",), email="staff-admreq7@example.org")
    response = await client.get("/api/admin/requests?cursor=not-a-cursor", headers=auth_headers(staff_cookies, staff_hdr))
    assert response.status_code == 422 and response.json()["error"]["code"] == "BAD_CURSOR"


@pytest.mark.asyncio
async def test_a_bad_status_filter_is_refused(client, member) -> None:
    _staff_id, staff_cookies, staff_hdr = member(("staff",), email="staff-admreq8@example.org")
    response = await client.get("/api/admin/requests?status=NOT_A_STATUS", headers=auth_headers(staff_cookies, staff_hdr))
    assert response.status_code == 422 and response.json()["error"]["code"] == "BAD_FILTER"


@pytest.mark.asyncio
async def test_the_status_filter_narrows_the_queue(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-admreq9@example.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_a = await _listing(conn, client, seller_headers, name="Practice A9", city="Austin")
    listing_b = await _listing(conn, client, seller_headers, name="Practice B9", city="Buda")
    _b1, b1_cookies, b1_hdr = member(("buyer",), email="buyer-admreq9a@example.org")
    _b2, b2_cookies, b2_hdr = member(("buyer",), email="buyer-admreq9b@example.org")
    pending_id = await _request(client, auth_headers(b1_cookies, b1_hdr), listing_a)
    denied_id = await _request(client, auth_headers(b2_cookies, b2_hdr), listing_b)
    await client.post(f"/api/seller/requests/{denied_id}/decide", headers=seller_headers, json={"action": "deny", "reason": "No"})

    _staff_id, staff_cookies, staff_hdr = member(("staff",), email="staff-admreq9@example.org")
    staff_headers = auth_headers(staff_cookies, staff_hdr)
    response = await client.get("/api/admin/requests?status=PENDING", headers=staff_headers)
    ids = {r["id"] for r in response.json()["items"]}
    assert pending_id in ids and denied_id not in ids


@pytest.mark.asyncio
async def test_a_request_without_context_refuses_a_nonexistent_id_gracefully(client, member) -> None:
    """Not a real gap in this route (there is no `{id}` path segment to probe) — kept as the
    module's own sanity check that a bare unauthenticated GET on a bogus admin sub-path 404s
    through the app's ordinary routing rather than this router swallowing it."""
    _staff_id, staff_cookies, staff_hdr = member(("staff",), email="staff-admreq10@example.org")
    response = await client.get(f"/api/admin/requests/{uuid4()}", headers=auth_headers(staff_cookies, staff_hdr))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_buyer_name_falls_back_to_email_when_no_display_name(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-admreq11@example.org")
    listing_id = await _listing(conn, client, auth_headers(s_cookies, s_hdr))
    bid, b_cookies, b_hdr = member(("buyer",), email="buyer-admreq11@example.org")
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET display_name = NULL WHERE id = %s", (bid,))
    request_id = await _request(client, auth_headers(b_cookies, b_hdr), listing_id)
    _staff_id, staff_cookies, staff_hdr = member(("staff",), email="staff-admreq11@example.org")
    response = await client.get("/api/admin/requests", headers=auth_headers(staff_cookies, staff_hdr))
    item = next(r for r in response.json()["items"] if r["id"] == request_id)
    assert item["buyer_name"] == "buyer-admreq11@example.org"
