"""POST /api/requests, GET /api/requests/mine, GET /api/requests/{id} (directive §6, §13).

Task 4's `app.disclosure.requests` already proved the lifecycle's own rules (create/list/decide/
revoke) at the module boundary; this file proves the HTTP surface around it: the guard is
`request.create`/`request.read_own` through `Depends` (never wrapped), every refusal renders the
`{"error": {"code", "message"}}` envelope, and — the most important test in this file, per the
task brief and directive §22 — a request that is not the caller's own is refused as 404, never
confirmed to exist.

Three deviations from the plan's own literal Step 4 code are fixed in `app/api/requests.py` and
proved here rather than merely asserted; see that module's own docstring and
`.superpowers/sdd/2026-09-18-per-buyer-disclosure/task-05-report.md` for the full account:

1. `Refusal` imported from `app.api.seller_listings` (Task 4's own deviation, inherited).
2. Every response is run through `_serialisable` before it reaches `JSONResponse` — the plan's own
   literal `JSONResponse(row, status_code=201)` 500s, because `requested_at` is a real
   `datetime.datetime` (`app.disclosure.requests` deliberately leaves it that way) and
   `json.dumps` (what `JSONResponse.render` calls) has no encoder for one. Proved directly by
   `test_a_buyer_can_request_access`'s own `response.status_code == 201` assertion, which is the
   plan's own test, unmodified.
3. `listing_id` (the body) and `request_id` (the path) are validated as real UUIDs, folded into the
   SAME "not found" refusal a well-formed-but-absent id already gets from
   `app.disclosure.requests`, rather than reaching Postgres as a plain string and raising
   `InvalidTextRepresentation` (a raw 500) on a malformed one.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.api.conftest import auth_headers


async def _seller_listing(conn, client, headers) -> str:
    """A published listing owned by whoever `headers` signs in as.

    Deviation from the plan's own literal Step 1 code (recorded in task-05-report.md): the UPDATE
    also sets `area`/`market`/`type`. `migrations/034_listing_publishable_sqft.sql`'s
    `listing_publishable_ck` requires `state`, `market`, `area` AND `sqft` all non-null for
    `status = 'published'` (030's original three widened by 034's fourth), and `016`'s own
    `listing_submittable_ck` requires `name`/`city`/`zip`/`type`/`est`/`price` non-null for any
    status other than draft/withdrawn. The plan's own literal statement set only `state` and
    `sqft` of the first group and left `type` out of the second — so every call raised
    `psycopg2.errors.CheckViolation` (`listing_publishable_ck` first, then `listing_submittable_ck`
    once that one was fixed) — proved by running it twice, not guessed once."""
    response = await client.post("/api/seller/listings", headers=headers)
    listing_id = response.json()["id"]
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status = 'published', name = 'Test Practice', city = 'Austin',"
                    " state = 'TX', zip = '78701', area = 'Austin', market = 'Austin, TX', type = 'Small animal',"
                    " est = 2010, price = 1000000, sqft = 3000 WHERE id = %s", (listing_id,))
    return listing_id


# --- creation ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_buyer_can_request_access(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller1@example.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _seller_listing(conn, client, seller_headers)
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer1@example.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    response = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id, "message": "Tell me more"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["listing_id"] == listing_id
    # Deviation 2's own proof: a fresh row's `requested_at` is set and `reviewed_at`/`expires_at`
    # are not — every kind this dict can hold has to survive `_serialisable` without a KeyError or
    # a raw `datetime` slipping through.
    assert isinstance(body["requested_at"], str) and body["requested_at"]
    assert body["reviewed_at"] is None and body["expires_at"] is None


@pytest.mark.asyncio
async def test_a_buyer_cannot_request_access_to_their_own_listing(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller2@example.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _seller_listing(conn, client, seller_headers)
    response = await client.post("/api/requests", headers=seller_headers, json={"listing_id": listing_id})
    assert response.status_code == 422 and response.json()["error"]["code"] == "SELF_REQUEST"


@pytest.mark.asyncio
async def test_a_second_request_while_one_is_pending_is_refused(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller3@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer3@example.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    response = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    assert response.status_code == 409 and response.json()["error"]["code"] == "ALREADY_REQUESTED"


@pytest.mark.asyncio
async def test_create_refuses_a_listing_that_does_not_exist(client, member) -> None:
    """The brief's own required case: a well-formed but absent listing_id is a clean 404, never a
    500 — `app.disclosure.requests.create`'s own `NOT_FOUND`, reached through this route."""
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-nf@example.org")
    response = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": str(uuid4())})
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_creating_a_request_writes_an_audit_row(client, conn, member, audit_rows) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller6@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer6@example.org")
    await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": listing_id})
    rows = [r for r in audit_rows() if r["action"] == "access.requested"]
    assert len(rows) == 1 and rows[0]["target_type"] == "request"


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_is_refused(client) -> None:
    response = await client.post("/api/requests", json={"listing_id": str(uuid4())})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_the_create_rate_limit_is_per_account(client, conn, member, monkeypatch) -> None:
    """Directive §6/§23. `app/api/seller_listings.py::test_the_create_rate_limit_is_per_account`'s
    own idiom: patch the module's imported constant down to one, so the flood is two calls rather
    than twenty-one. The second call is refused by the limiter before it can reach
    `ALREADY_REQUESTED` — `hit(...)` fires before `req.create` is ever called."""
    from app.api import requests as R

    monkeypatch.setattr(R, "ACCESS_REQUEST_CREATE", (1, 3600))
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-rl@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-rl@example.org")
    buyer_headers = auth_headers(b_cookies, b_hdr)
    first = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    assert first.status_code == 201, first.text
    refused = await client.post("/api/requests", headers=buyer_headers, json={"listing_id": listing_id})
    assert refused.status_code == 429 and refused.json()["error"]["code"] == "RATE_LIMITED"


# --- input validation (Deviations 2/3, and the module's own bounded JSON reader) --------------


@pytest.mark.asyncio
async def test_create_requires_listing_id(client, member) -> None:
    """An entirely empty body — the `_json_body` ternary's "raw is empty" arm — falls through to
    the plan's own `listing_id is required` refusal rather than a `BAD_JSON` one: no bytes at all
    is not malformed JSON, it is a JSON object with nothing in it."""
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-empty@example.org")
    response = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr))
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_create_refuses_a_malformed_listing_id(client, member) -> None:
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-badid@example.org")
    response = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": "not-a-uuid"})
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_create_refuses_a_non_string_listing_id(client, member) -> None:
    """`_valid_uuid`'s OTHER failure arm — a JSON value that is not a string at all, never reaching
    `UUID(...)`'s own `ValueError` path."""
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-numid@example.org")
    response = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json={"listing_id": 12345})
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_create_refuses_a_non_string_message(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-msg@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-msg@example.org")
    response = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr),
                                 json={"listing_id": listing_id, "message": 12345})
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_create_refuses_a_non_string_disclosure_level(client, conn, member) -> None:
    """Fail closed (directive §19) before this ever reaches `app.disclosure.requests.create`:
    `"level" not in REQUESTABLE_LEVELS` is safe for any hashable value but raises `TypeError` for
    an unhashable one (a JSON array or object), which `disclosure_level` could otherwise carry
    straight through unchecked."""
    _sid, s_cookies, s_hdr = member(("seller",), email="seller-lvl@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-lvl@example.org")
    response = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr),
                                 json={"listing_id": listing_id, "disclosure_level": ["FULL_CONFIDENTIAL"]})
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_LEVEL"


@pytest.mark.asyncio
async def test_create_refuses_malformed_json(client, member) -> None:
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-badjson@example.org")
    headers = {**auth_headers(b_cookies, b_hdr), "Content-Type": "application/json"}
    response = await client.post("/api/requests", headers=headers, content=b"{not valid json")
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_JSON"


@pytest.mark.asyncio
async def test_create_refuses_a_non_object_json_body(client, member) -> None:
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-array@example.org")
    response = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr), json=[1, 2, 3])
    assert response.status_code == 400 and response.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_create_refuses_a_body_over_the_size_cap(client, member) -> None:
    from app.api.requests import MAX_JSON_BYTES

    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-huge@example.org")
    response = await client.post("/api/requests", headers=auth_headers(b_cookies, b_hdr),
                                 json={"listing_id": str(uuid4()), "message": "x" * (MAX_JSON_BYTES + 1)})
    assert response.status_code == 413 and response.json()["error"]["code"] == "TOO_LARGE"


# --- GET /api/requests/mine --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mine_only_shows_the_signed_in_buyer_s_own_requests(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller4@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _a, a_cookies, a_hdr = member(("buyer",), email="buyera4@example.org")
    _b, b_cookies, b_hdr = member(("buyer",), email="buyerb4@example.org")
    a_headers, b_headers = auth_headers(a_cookies, a_hdr), auth_headers(b_cookies, b_hdr)
    await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})
    mine_a = await client.get("/api/requests/mine", headers=a_headers)
    mine_b = await client.get("/api/requests/mine", headers=b_headers)
    assert len(mine_a.json()) == 1 and mine_b.json() == []


# --- GET /api/requests/{id}, including directive §22's IDOR case ------------------------------


@pytest.mark.asyncio
async def test_get_one_succeeds_for_the_owning_buyer(client, conn, member) -> None:
    _sid, s_cookies, s_hdr = member(("seller",), email="seller5c@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _a, a_cookies, a_hdr = member(("buyer",), email="buyera5c@example.org")
    a_headers = auth_headers(a_cookies, a_hdr)
    created = await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})
    response = await client.get(f"/api/requests/{created.json()['id']}", headers=a_headers)
    assert response.status_code == 200
    assert response.json()["id"] == created.json()["id"]
    assert response.json()["requested_at"] == created.json()["requested_at"]


@pytest.mark.asyncio
async def test_get_one_refuses_a_request_that_belongs_to_another_buyer(client, conn, member) -> None:
    """The most important test in this file (task brief, directive §22): a request that is not the
    caller's own must be refused as 404 — never a 403, which would confirm it exists."""
    _sid, s_cookies, s_hdr = member(("seller",), email="seller5@example.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _a, a_cookies, a_hdr = member(("buyer",), email="buyera5@example.org")
    _b, b_cookies, b_hdr = member(("buyer",), email="buyerb5@example.org")
    a_headers, b_headers = auth_headers(a_cookies, a_hdr), auth_headers(b_cookies, b_hdr)
    created = await client.post("/api/requests", headers=a_headers, json={"listing_id": listing_id})
    response = await client.get(f"/api/requests/{created.json()['id']}", headers=b_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_one_refuses_the_listing_s_own_seller_too(client, conn, member) -> None:
    """The same IDOR case at the seller's own door: `request.read_own` is a role permission BOTH
    buyer and seller hold (a seller can also be a buyer of someone else's listing), so the route
    guard alone cannot tell them apart — the row-ownership check inside `req.get_one`
    (`buyer_user_id = the caller`) is what has to refuse the listing's own seller reading a buyer's
    request through this, the BUYER's door. `GET /api/seller/requests` (Task 6) is the seller's own."""
    _sid, s_cookies, s_hdr = member(("seller",), email="seller5b@example.org")
    seller_headers = auth_headers(s_cookies, s_hdr)
    listing_id = await _seller_listing(conn, client, seller_headers)
    _a, a_cookies, a_hdr = member(("buyer",), email="buyera5b@example.org")
    created = await client.post("/api/requests", headers=auth_headers(a_cookies, a_hdr), json={"listing_id": listing_id})
    response = await client.get(f"/api/requests/{created.json()['id']}", headers=seller_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_one_refuses_a_malformed_request_id(client, member) -> None:
    _bid, b_cookies, b_hdr = member(("buyer",), email="buyer-badreqid@example.org")
    response = await client.get("/api/requests/not-a-uuid", headers=auth_headers(b_cookies, b_hdr))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_buyer_never_receives_the_sellers_internal_account_id(
    client, conn, member,
) -> None:
    """Security review, 2026-09-19. `_COLUMNS` selects `seller_user_id` because the seller routes
    need it; the buyer routes returned the whole row. `app/api/listings.py`'s own `_SELECT` comment
    states the rule — an internal account id "never has been and never should be" part of the buyer
    contract — and the listing routes honoured it while these newer routes did not."""
    _sid, s_cookies, s_hdr = member(("seller",), email="idleak-seller@x.org")
    listing_id = await _seller_listing(conn, client, auth_headers(s_cookies, s_hdr))
    _bid, b_cookies, b_hdr = member(("buyer",), email="idleak-buyer@x.org")
    buyer = auth_headers(b_cookies, b_hdr)

    created = await client.post("/api/requests", json={"listing_id": listing_id}, headers=buyer)
    assert created.status_code == 201, created.text
    assert "seller_user_id" not in created.json()

    mine = (await client.get("/api/requests/mine", headers=buyer)).json()
    assert mine and all("seller_user_id" not in row for row in mine)

    one = (await client.get(f"/api/requests/{created.json()['id']}", headers=buyer)).json()
    assert "seller_user_id" not in one
