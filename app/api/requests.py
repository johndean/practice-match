"""Buyer-facing access-request routes (directive §6, §13). Guarded by the existing `request.create`
/`request.read_own` permissions (`app/auth/permissions.py:22`); the buyer/listing-specific decision
(is this MY request) is enforced in `app.disclosure.requests`, the same split
`app/api/seller_listings.py:18` already uses for listing ownership: "Ownership is enforced HERE,
not in the matrix."

These are the first routes in the per-buyer-disclosure subsystem, so three deviations from the
plan's own literal Step 4 code are recorded here rather than silently applied — all three are
provable defects in the plan's OWN given code (confirmed by RUNNING it, not by inspection alone;
see `.superpowers/sdd/2026-09-18-per-buyer-disclosure/task-05-report.md` for the RED transcripts),
not directive disagreements, and Task 4's own report (`task-04-report.md`) fixed its two
comparable ones the same way:

1. **`Refusal` comes from `app.api.seller_listings`, not `app.api.listings`.** Task 4's own module
   raises exactly that class (`task-04-report.md`, Deviation 1), so this module has to catch the
   SAME one — a second, differently-imported `Refusal` would never match an `isinstance`/`except`
   against the one `app.disclosure.requests` actually raises.
2. **`_serialisable` converts every `datetime` value to an ISO-8601 string before a dict reaches
   `JSONResponse`.** The plan's own literal `JSONResponse(row, status_code=201)`, run against the
   plan's own `test_a_buyer_can_request_access`, raises `TypeError: Object of type datetime is not
   JSON serializable` instead of answering 201: `app.disclosure.requests` deliberately returns
   `requested_at`/`reviewed_at`/`expires_at` as real `datetime.datetime` objects ("untouched by
   this module", `task-04-report.md`), and Starlette's `JSONResponse.render` calls the stdlib
   `json.dumps` with no encoder for one. Every route elsewhere in this codebase that serves a
   timestamp does this same conversion by hand (`app/api/seller_listings.py`'s own
   `"updated_at": row["updated_at"].isoformat()`, `app/api/admin_listings.py`'s `_iso`) — this
   module does it generically, over the VALUE rather than a second hard-coded list of which keys
   are timestamps, because a second list of the same fact drifting from the first is exactly
   CLAUDE.md's own A16.23/A40 lesson.
3. **`listing_id` (the body) and `request_id` (the path) are validated as real UUIDs before either
   reaches SQL**, via `_valid_uuid`. `app.disclosure.requests.create`/`get_one` pass the string
   straight into a `uuid`-typed column comparison with no guard of their own; psycopg2 sends a
   Python `str` parameter as a plain SQL literal, and Postgres's own literal-to-uuid cast fails a
   malformed one at EXECUTE time as `psycopg2.errors.InvalidTextRepresentation` — a raw 500, the
   exact class of bug `app.auth.deps.client_ip`'s own docstring names ("`X-Forwarded-For: unknown`
   raised InvalidTextRepresentation ... a 500 on the one write path that must never fail") and the
   one `app/api/seller_listings.py::_row` already guards against for a listing id (`try:
   UUID(listing_id) except ValueError: return None`, folded into the SAME 404 a
   well-formed-but-absent id gets). A malformed `request_id` collapses into the SAME 404
   `get_one` already gives a well-formed one that is not this buyer's — directive §22's own rule
   applied one step earlier: a request that is not yours is 404, never distinguished from one that
   cannot even be parsed by a different status code. A malformed `listing_id` collapses into the
   SAME 404 `create` already gives a well-formed-but-absent one, for the identical reason.

A fourth gap, found the same way, is closed without a numbered deviation because it is not in the
plan's given code at all: `request.json()` (what the plan's Step 4 uses) is unbounded and turns a
malformed body into a raw `json.JSONDecodeError`, not a `Refusal` — every OTHER JSON-reading route
in this codebase refuses a malformed or oversized body with the A5 envelope instead
(`app/api/interest.py::_read_capped`, `app/api/seller_listings.py::_json_body`); `_json_body` below
is that same idiom, sized for this module's own much smaller body (a uuid, a short message, an
enum word) rather than importing either module's differently-sized private helper. `disclosure_level`
and `message` are also checked for TYPE (not just presence) before they reach
`app.disclosure.requests.create`: a non-string `disclosure_level` would otherwise reach
`level not in REQUESTABLE_LEVELS`, and `in` against a `frozenset` raises `TypeError` for an
unhashable value (a JSON array or object) rather than answering `False` — the identical "malformed
input, raw 500" class the other three deviations close, one field over.

None of the above is a plan/directive disagreement — the directive is silent on all of it — and
none is a judgment call that points a different way from the plan; each is a mechanical correction
proved by reading the control flow and then running it, exactly Task 4's own precedent."""
from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.api.listings import _error
from app.api.seller_listings import Refusal
from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.auth.limits import ACCESS_REQUEST_CREATE, hit
from app.cache import sync_redis
from app.db import sync_conn
from app.disclosure import requests as req

router = APIRouter(prefix="/api")

# Hoisted to module-level constants, never wrapped (Global Constraint 10) — the route-guard and
# audit-drift tests resolve a route's permission by the guard object's IDENTITY
# (`app.auth.deps.permission_of`), so a wrapper around either would read as unguarded.
REQUIRE_REQUEST_CREATE = require("request.create")
REQUIRE_REQUEST_READ_OWN = require("request.read_own")
Requester = Annotated[S.Principal, Depends(REQUIRE_REQUEST_CREATE)]
OwnRequestReader = Annotated[S.Principal, Depends(REQUIRE_REQUEST_READ_OWN)]

# Sized for this body's three short fields (a uuid, a short message, an enum word) — not a wizard
# step's whole field set, which is why `app/api/seller_listings.py`'s own MAX_JSON_BYTES is 64 KB.
MAX_JSON_BYTES = 8 * 1024


def _refused(exc: Refusal) -> JSONResponse:
    return _error(exc.code, exc.message, exc.status)


def _valid_uuid(value: object) -> bool:
    """Deviation 3. `value` is not necessarily a `str` at all — a JSON body field can be any type."""
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _serialisable(row: dict[str, Any]) -> dict[str, Any]:
    """Deviation 2. `row` with every `datetime` value rendered as an ISO-8601 string."""
    return {key: (value.isoformat() if isinstance(value, datetime) else value) for key, value in row.items()}


async def _json_body(request: Request) -> dict[str, Any]:
    """The request's JSON object, or a `Refusal` — never a raw `json.JSONDecodeError` or an
    unbounded read (see the fourth gap in the module docstring)."""
    total = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_JSON_BYTES:
            raise Refusal("TOO_LARGE", f"Body must be no larger than {MAX_JSON_BYTES // 1024} KB.", 413)
        chunks.append(chunk)
    raw = b"".join(chunks)
    try:
        body = json.loads(raw) if raw else {}
    except ValueError as exc:
        raise Refusal("BAD_JSON", "Body must be JSON.", 400) from exc
    if not isinstance(body, dict):
        raise Refusal("BAD_REQUEST", "Body must be an object.", 400)
    return body


@router.post("/requests", status_code=201)
async def create_request(request: Request, principal: Requester) -> Response:
    """`POST /api/requests` — directive §6's "may ... request access to additional confidential
    information." Rate-limited BEFORE any other work (A-RL2's own reason: the reservation and the
    decision have to be one server-side step)."""
    hit(sync_redis(), "request:create", str(principal.account_id), *ACCESS_REQUEST_CREATE)
    try:
        body = await _json_body(request)
        listing_id = body.get("listing_id")
        if not listing_id:
            raise Refusal("BAD_REQUEST", "listing_id is required.", 400)
        if not _valid_uuid(listing_id):
            # Folded into the SAME refusal `req.create` gives a well-formed-but-absent id
            # (Deviation 3) — a malformed one is not a different fact from the caller's chair.
            raise Refusal("NOT_FOUND", "No such listing.", 404)
        message = body.get("message")
        if message is not None and not isinstance(message, str):
            raise Refusal("BAD_REQUEST", "message must be a string.", 400)
        level = body.get("disclosure_level", "FULL_CONFIDENTIAL")
        if not isinstance(level, str):
            # The fourth gap: `level not in REQUESTABLE_LEVELS` inside `req.create` raises
            # `TypeError` for an unhashable value rather than answering False.
            raise Refusal("BAD_LEVEL", "disclosure_level must be a string.", 400)
        with closing(sync_conn()) as conn, conn:
            row = req.create(
                conn, listing_id=listing_id, buyer_account_id=str(principal.account_id),
                message=message, requested_disclosure_level=level,
            )
            # Directive §14: user (actor), listing and disclosure level, beside the target request
            # row `audit.write` already stamps with the action and the timestamp.
            audit.write(conn, actor=principal, action="access.requested", target_type="request",
                       target_id=row["id"], after={"listing_id": listing_id, "level": row["requested_disclosure_level"]},
                       request=request)
    except Refusal as exc:
        return _refused(exc)
    return JSONResponse(_serialisable(row), status_code=201)


@router.get("/requests/mine")
async def list_my_requests(principal: OwnRequestReader) -> Response:
    """`GET /api/requests/mine` — scoped to the AUTHENTICATED caller alone (the task brief's own
    rule: "If a parameter could let a caller name someone else, it does not exist"). There is no
    query parameter here for a reason: `buyer_account_id` comes from `principal`, never from the
    request, so there is nothing in this route's own signature a caller could set to another
    buyer's id."""
    with closing(sync_conn()) as conn, conn:
        rows = req.list_mine(conn, buyer_account_id=str(principal.account_id))
    return JSONResponse([_serialisable(row) for row in rows])


@router.get("/requests/{request_id}")
async def get_my_request(request_id: str, principal: OwnRequestReader) -> Response:
    """`GET /api/requests/{request_id}` — directive §22's IDOR case: a request that is not this
    buyer's own is refused as 404, identically to one that does not exist at all, never a 403 that
    would confirm something is there."""
    try:
        if not _valid_uuid(request_id):
            raise Refusal("NOT_FOUND", "No such request.", 404)
        with closing(sync_conn()) as conn, conn:
            row = req.get_one(conn, request_id=request_id, buyer_account_id=str(principal.account_id))
    except Refusal as exc:
        return _refused(exc)
    return JSONResponse(_serialisable(row))
