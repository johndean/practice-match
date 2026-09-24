"""Seller-facing access-request routes (directive §5, §13, §14, §15). Guarded by the existing
`request.answer_own` permission (`app/auth/permissions.py:24`, seller-only); the request-specific
decision (is this MY request, on MY listing) is enforced in `app.disclosure.requests`, the same
split `app/api/seller_listings.py:18` already uses for listing ownership: "Ownership is enforced
HERE, not in the matrix." A non-owned request is 404, never 403 — a request that is not yours
should not be confirmed to exist (`app.disclosure.requests._owned_pending_or_approved`'s own rule,
applied here as directive §22's IDOR case for the seller's own door).

This is Task 5's sibling and reuses its already-proved fixes rather than declaring a second copy
of them, per this task's own brief ("Task 5 ... set the pattern ... reuse it rather than writing a
second"). Full account in
`.superpowers/sdd/2026-09-18-per-buyer-disclosure/task-06-report.md`; summarised here because the
next reader of THIS file needs to know why these imports look the way they do, not just that
`task-05-report.md` says so:

1. **`_valid_uuid`, `_serialisable` and `_json_body` (which itself bounds the body at
   `MAX_JSON_BYTES`) are IMPORTED from `app.api.requests`, not redeclared.** `request_id` (every
   route below's path segment) has the IDENTICAL gap Task 5 found and fixed for `listing_id`: a
   malformed value reaching Postgres's
   own literal-to-uuid cast as `psycopg2.errors.InvalidTextRepresentation` — a raw 500 — rather
   than the clean 404 a well-formed-but-not-yours id already gets from
   `app.disclosure.requests`. `disclosure_level` (the decide body) has the identical gap Task 5
   found for its own `disclosure_level`: `level not in REQUESTABLE_LEVELS` raises `TypeError` for
   an unhashable value (a JSON array/object) rather than answering `False`. A malformed or
   oversized JSON body has the identical gap Task 5 found for `request.json()`. Declaring a
   second copy of any of the four is exactly the "two lists of one fact drift" lesson CLAUDE.md
   records at A16.23/A40 — one table, one set of malformed-input guards for it.
2. **`reason` (the seller's own free text on `deny`) needs the SAME class of guard, one field
   over.** `app.disclosure.requests.decide`'s deny branch sends it straight into
   `UPDATE request SET denial_reason = %s ...`; a non-string value either fails psycopg2's own
   adapter outright (a dict has none) or mismatches the `text` column's type at the database (a
   list, adapted to a Postgres ARRAY literal) — both raw 500s absent a type check here, proved by
   running it (task-06-report.md), not merely reasoned about.
3. **`revoke_request` also rate-limits, beyond the plan's own literal Step 3 code.**
   `app/api/seller_listings.py` throttles EVERY mutating route it defines (create, patch, upload,
   reorder, delete, submit, status — confirmed by reading the whole file, not by inspecting one
   route) and revoke is a mutating action against the identical table `decide` is, so leaving it
   unthrottled while its sibling is throttled would be an inconsistency this codebase does not
   otherwise have. Both share `ACCESS_REQUEST_DECIDE`'s budget — "a seller deciding on many
   requests in one sitting" plainly includes revoking one.

None of the above touches `app/api/requests.py` or `app/disclosure/requests.py` — both are already
committed and outside this task's own file list."""
from __future__ import annotations

from contextlib import closing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.api.listings import _error
from app.api.requests import _json_body, _serialisable, _valid_uuid
from app.api.seller_listings import Refusal
from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.auth.limits import ACCESS_REQUEST_DECIDE, hit
from app.cache import drop_list_cache_quietly, sync_redis
from app.db import sync_conn
from app.disclosure import requests as req
from app.disclosure.notify import notify_decision

router = APIRouter(prefix="/api/seller")

#: Tells "the key was not sent" from "the key was sent as JSON `null`" — see `decide_request`.
_ABSENT: Any = object()

# Hoisted to a module-level constant, never wrapped (Global Constraint 10) — the route-guard and
# audit-drift tests resolve a route's permission by the guard object's IDENTITY
# (`app.auth.deps.permission_of`), so a wrapper would read as unguarded.
REQUIRE_REQUEST_ANSWER_OWN = require("request.answer_own")
Answerer = Annotated[S.Principal, Depends(REQUIRE_REQUEST_ANSWER_OWN)]


def _refused(exc: Refusal) -> Response:
    return _error(exc.code, exc.message, exc.status)


def _audit_after(row: dict[str, Any]) -> dict[str, Any]:
    """Directive §14 / this task's own brief: "who decided, when, and for which buyer and
    listing." `row` (from `app.disclosure.requests`) already carries all four, plainly typed
    (`_row`'s own `str()` conversion) — no `datetime` here, so no `_serialisable` is needed for
    what `audit.write` itself will `json.dumps`."""
    return {
        "listing_id": row["listing_id"],
        "buyer_user_id": row["buyer_user_id"],
        "status": row["status"],
        # D-C67 (2026-09-24): the grant is a SET, so the audit records the set. `None` on a denied
        # row, exactly as the single `level` was, and a LIST on an approved one — including the
        # empty list, which is a decision that released nothing and must be as legible in the trail
        # as one that released everything.
        "capabilities": row.get("approved_capabilities"),
    }


@router.get("/requests")
async def list_inbox(principal: Answerer) -> Response:
    """`GET /api/seller/requests` — directive §5's "Seller dashboard must provide a buyer-access
    area." Scoped to the AUTHENTICATED seller alone, `app.api.requests.list_my_requests`'s own
    shape (Task 5): no parameter exists that could let a caller name a different seller, so there
    is nothing here for an IDOR test to prove the absence of."""
    with closing(sync_conn()) as conn, conn:
        rows = req.list_inbox(conn, seller_account_id=str(principal.account_id))
    return JSONResponse([_serialisable(row) for row in rows])


@router.post("/requests/{request_id}/decide")
async def decide_request(request_id: str, request: Request, principal: Answerer) -> Response:
    """`POST /api/seller/requests/{id}/decide` — directive §5's approve/deny. Rate-limited BEFORE
    any other work, Task 5's own reasoning (`app.auth.limits.hit`'s own docstring: "the
    reservation is taken BEFORE the caller does the work it gates")."""
    hit(sync_redis(), "request:decide", str(principal.account_id), *ACCESS_REQUEST_DECIDE)
    try:
        if not _valid_uuid(request_id):
            # Folded into the SAME refusal a well-formed-but-not-yours id already gets from
            # `app.disclosure.requests` (Deviation 1) — directive §22's IDOR case, one input
            # earlier: a malformed id is not a different fact from the caller's chair.
            raise Refusal("NOT_FOUND", "No such request.", 404)
        body = await _json_body(request)
        action = body.get("action")
        if not isinstance(action, str):
            # `req.decide`'s own `if/elif/else` would refuse this the same way once it reached
            # SQL (any type is safe against `==`), but checking here narrows `action` to `str`
            # for the ternaries below and answers BAD_ACTION before a connection is even opened.
            raise Refusal("BAD_ACTION", "action must be 'approve' or 'deny'.", 400)
        level = body.get("disclosure_level")
        if level is not None and not isinstance(level, str):
            raise Refusal("BAD_LEVEL", "disclosure_level must be a string.", 400)
        # D-C67 (John, 2026-09-24): the seller chooses WHICH capabilities this buyer receives.
        # `disclosure_capabilities` is the SET; `disclosure_level` above stays for the named levels
        # a buyer may ask for, which `app.disclosure.requests._chosen_capabilities` expands through
        # `covers()` — so the existing all-five path is still reachable from either spelling.
        #
        # ABSENT AND `null` ARE DIFFERENT ANSWERS HERE, which no other field on this route needs
        # and this one does. An absent key is "the caller named no set" and takes the default arm
        # (the level the buyer asked for). An explicit JSON `null` is REFUSED rather than read as
        # absent, because that is the shape a client reaches by accident: `chooseAccess` answers
        # `string[] | null` — `null` meaning the seller dismissed the drawer — and a caller who
        # forwarded it without checking would otherwise be handed the requested level, which every
        # request in this product defaults to `FULL_CONFIDENTIAL`. A refusal is the fail-closed
        # answer to "I do not know what you meant" about a disclosure decision.
        #
        # An EMPTY array is a real decision and reaches `_chosen_capabilities` as one: see that
        # function's own docstring for what a falsy test would cost. The element type guard is the
        # fourth-gap class Deviation 1 records, one field over: `value not in CAPABILITIES` raises
        # `TypeError` for an unhashable member (a nested array or object) rather than answering
        # False.
        capabilities = body.get("disclosure_capabilities", _ABSENT)
        if capabilities is _ABSENT:
            capabilities = None
        elif not isinstance(capabilities, list) or any(not isinstance(v, str) for v in capabilities):
            raise Refusal("BAD_LEVEL", "disclosure_capabilities must be an array of strings.", 400)
        reason = body.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise Refusal("BAD_REQUEST", "reason must be a string.", 400)
        with closing(sync_conn()) as conn, conn:
            row = req.decide(
                conn, request_id=request_id, seller_account_id=str(principal.account_id),
                action=action, disclosure_level=level, reason=reason,
                disclosure_capabilities=capabilities,
            )
            # `action` is guaranteed "approve" or "deny" here: any other value made `req.decide`
            # raise `BAD_ACTION` above, before `row` was ever assigned.
            audit.write(
                conn, actor=principal, action=f"access.{'approved' if action == 'approve' else 'denied'}",
                target_type="request", target_id=request_id, after=_audit_after(row),
                # The seller's own words, `app/api/admin_listings.py`'s own shape for a decision's
                # rationale — never duplicated into `after` too (directive §14's closing sentence).
                reason=reason if action == "deny" else None,
                request=request,
            )
            # Ruling D-C62 (2026-09-21): the buyer is told, inside the SAME transaction as the
            # decision and its audit row — a decision cannot commit without its mail, or vice
            # versa (`app.disclosure.notify`'s own docstring for the privacy guarantee this
            # depends on: composed from `authorized_capabilities`, asked AFTER this write).
            notify_decision(conn, row=row)
    except Refusal as exc:
        return _refused(exc)
    # Spec D16, and ruling D-C66 (2026-09-24) is what made it load-bearing on THIS route (fix round
    # 2, review Important-2). `GET /api/listings` caches its first page for 60 s under a key that
    # carries the buyer's own account id, and `serialise` applies that buyer's own capabilities to
    # the name, the address, the pin and the revenue -- so a decision that changes what this buyer
    # may see and does NOT drop the cache leaves their Browse page a minute out of date. Every
    # writer in `seller_listings.py` and `admin_listings.py` has dropped it since D16; no request
    # route ever did, because before the per-buyer plan a grant changed no field in this payload.
    # AFTER the commit, never inside the transaction: `drop_list_cache`'s own docstring gives the
    # reason (a drop against an uncommitted write lets a concurrent read re-cache the old payload
    # for the full TTL), and this line sits after the `except` so a refusal drops nothing.
    drop_list_cache_quietly()
    return JSONResponse(_serialisable(row))


@router.post("/requests/{request_id}/revoke")
async def revoke_request(request_id: str, request: Request, principal: Answerer) -> Response:
    """`POST /api/seller/requests/{id}/revoke` — directive §15. Honest about its own limit: this
    route calls `app.disclosure.requests.revoke` and nothing else decides what revocation does —
    see that function's own docstring (Task 4) for why "prevents FUTURE authorized retrieval" is
    the whole of what this can promise, and never "recalls a file already downloaded.\""""
    hit(sync_redis(), "request:decide", str(principal.account_id), *ACCESS_REQUEST_DECIDE)
    try:
        if not _valid_uuid(request_id):
            raise Refusal("NOT_FOUND", "No such request.", 404)
        with closing(sync_conn()) as conn, conn:
            row = req.revoke(conn, request_id=request_id, seller_account_id=str(principal.account_id))
            audit.write(conn, actor=principal, action="access.revoked", target_type="request",
                       target_id=request_id, after=_audit_after(row), request=request)
            # Ruling D-C62 (2026-09-21): same transaction, same reasoning as `decide_request` above.
            notify_decision(conn, row=row)
    except Refusal as exc:
        return _refused(exc)
    # Spec D16, same placement and same reasoning as `decide_request` above — and this is the arm
    # that LEAKS rather than merely lags. A53/A57 put a Withdraw button on the seller's inbox and
    # tell them "You withdrew this buyer's access. The buyer no longer sees the financial packet or
    # floor plan."; without this line the buyer went on reading the released name, address and
    # revenue on their own cached Browse page for up to 60 seconds after being told otherwise.
    drop_list_cache_quietly()
    return JSONResponse(_serialisable(row))
