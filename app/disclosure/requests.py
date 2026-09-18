# app/disclosure/requests.py
"""The request lifecycle: create, list, decide, revoke (directive §5, §6, §15). Every write here
goes through exactly one of these six functions; the two route files (Tasks 5, 6) are thin HTTP
wrappers that resolve a Principal, call one of these, and render the result or the Refusal it
raised. Reuses `app.api.seller_listings.Refusal` rather than declaring a second exception type, so
every route's EXISTING `_refused`/`_error` rendering already knows how to answer one (Global
Constraint: no inline HTTPException; deviation from the plan's literal `from app.api.listings
import Refusal` recorded in task-04-report.md -- `Refusal` is defined at
`app/api/seller_listings.py:201` and `app.api.listings` neither defines nor re-exports it).

Revocation (directive §15) is honest about its own limit and this module never implies
otherwise: `revoke` prevents FUTURE authorized retrieval by moving the row out of the status
`app.disclosure.access.authorized_capabilities` looks for (`'APPROVED'`) -- once revoked, that
function's single query can never again match this row, so no later call through the one
authorization boundary can return a capability for it (`tests/disclosure/test_requests.py`'s
`test_after_revoke_access_authorized_capabilities_is_empty_for_that_buyer` proves exactly this,
against the real function, not against this module's own return value). It cannot, and does not
claim to, recall a file the buyer already downloaded before the seller revoked -- that copy left
this system's control the moment it was served."""
from __future__ import annotations

from typing import Any

from app.api.seller_listings import Refusal
from app.disclosure.levels import REQUESTABLE_LEVELS

_COLUMNS = (
    "id, listing_id, buyer_user_id, seller_user_id, message, status, requested_disclosure_level,"
    " approved_disclosure_level, requested_at, reviewed_at, reviewed_by, denial_reason, expires_at"
)


def _row(cur: Any) -> dict[str, Any]:
    names = [d[0] for d in cur.description]
    values = cur.fetchone()
    return {name: (str(value) if name.endswith("_id") or name in ("id", "reviewed_by") else value) for name, value in zip(names, values, strict=True)}


def create(conn: Any, *, listing_id: str, buyer_account_id: str, message: str | None,
          requested_disclosure_level: str = "FULL_CONFIDENTIAL") -> dict[str, Any]:
    if requested_disclosure_level not in REQUESTABLE_LEVELS:
        raise Refusal("BAD_LEVEL", f"disclosure_level must be one of {', '.join(sorted(REQUESTABLE_LEVELS))}.", 400)
    with conn.cursor() as cur:
        cur.execute("SELECT seller_id FROM listing WHERE id = %s AND status = 'published'", (listing_id,))
        found = cur.fetchone()
        if found is None:
            raise Refusal("NOT_FOUND", "No such listing.", 404)
        seller_id = found[0]
        if seller_id is None:
            raise Refusal("NO_SELLER", "This listing has no seller account to request access from.", 422)
        if str(seller_id) == str(buyer_account_id):
            raise Refusal("SELF_REQUEST", "You cannot request access to your own listing.", 422)
        try:
            cur.execute(
                f"INSERT INTO request (listing_id, buyer_user_id, seller_user_id, message, requested_disclosure_level)"
                f" VALUES (%s,%s,%s,%s,%s) RETURNING {_COLUMNS}",
                (listing_id, buyer_account_id, seller_id, message, requested_disclosure_level),
            )
        except Exception as exc:  # psycopg2.errors.UniqueViolation — the partial index (migration 096)
            if type(exc).__name__ == "UniqueViolation":
                raise Refusal("ALREADY_REQUESTED", "You already have a pending or approved request for this listing.", 409) from exc
            raise
        return _row(cur)


def get_one(conn: Any, *, request_id: str, buyer_account_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM request WHERE id = %s AND buyer_user_id = %s", (request_id, buyer_account_id))
        if cur.fetchone() is None:
            raise Refusal("NOT_FOUND", "No such request.", 404)
        cur.execute(f"SELECT {_COLUMNS} FROM request WHERE id = %s AND buyer_user_id = %s", (request_id, buyer_account_id))
        return _row(cur)


def list_mine(conn: Any, *, buyer_account_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM request WHERE buyer_user_id = %s ORDER BY requested_at DESC", (buyer_account_id,))
        names = [d[0] for d in cur.description]
        return [{name: (str(value) if name.endswith("_id") or name in ("id", "reviewed_by") else value) for name, value in zip(names, row, strict=True)}
                for row in cur.fetchall()]


def list_inbox(conn: Any, *, seller_account_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM request WHERE seller_user_id = %s ORDER BY requested_at DESC", (seller_account_id,))
        names = [d[0] for d in cur.description]
        return [{name: (str(value) if name.endswith("_id") or name in ("id", "reviewed_by") else value) for name, value in zip(names, row, strict=True)}
                for row in cur.fetchall()]


def _owned_pending_or_approved(conn: Any, *, request_id: str, seller_account_id: str, required_status: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM request WHERE id = %s AND seller_user_id = %s", (request_id, seller_account_id))
        found = cur.fetchone()
    if found is None:
        raise Refusal("NOT_FOUND", "No such request.", 404)  # seller_listings.py:18's rule: not yours, not found
    if found[0] != required_status:
        raise Refusal("STATE", f"This request is {found[0].lower()}, not {required_status.lower()}.", 409)


def decide(conn: Any, *, request_id: str, seller_account_id: str, action: str,
          disclosure_level: str | None, reason: str | None) -> dict[str, Any]:
    _owned_pending_or_approved(conn, request_id=request_id, seller_account_id=seller_account_id, required_status="PENDING")
    with conn.cursor() as cur:
        if action == "approve":
            cur.execute("SELECT requested_disclosure_level FROM request WHERE id = %s", (request_id,))
            level = disclosure_level or cur.fetchone()[0]
            if level not in REQUESTABLE_LEVELS:
                raise Refusal("BAD_LEVEL", f"disclosure_level must be one of {', '.join(sorted(REQUESTABLE_LEVELS))}.", 400)
            cur.execute(
                f"UPDATE request SET status = 'APPROVED', approved_disclosure_level = %s, reviewed_at = now(),"
                f" reviewed_by = %s, updated_at = now() WHERE id = %s RETURNING {_COLUMNS}",
                (level, seller_account_id, request_id),
            )
        elif action == "deny":
            cur.execute(
                f"UPDATE request SET status = 'DENIED', denial_reason = %s, reviewed_at = now(),"
                f" reviewed_by = %s, updated_at = now() WHERE id = %s RETURNING {_COLUMNS}",
                (reason, seller_account_id, request_id),
            )
        else:
            raise Refusal("BAD_ACTION", "action must be 'approve' or 'deny'.", 400)
        return _row(cur)


def revoke(conn: Any, *, request_id: str, seller_account_id: str) -> dict[str, Any]:
    _owned_pending_or_approved(conn, request_id=request_id, seller_account_id=seller_account_id, required_status="APPROVED")
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE request SET status = 'REVOKED', updated_at = now() WHERE id = %s RETURNING {_COLUMNS}",
            (request_id,),
        )
        return _row(cur)
