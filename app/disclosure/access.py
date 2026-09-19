# app/disclosure/access.py
"""The one function every confidential-resource route calls (directive §12, §18, §19).

Reads ONLY the `request` table's current, active grant for a (listing, buyer) pair. Deliberately
does not know about `location_disclosed`, `identifiable_content_visibility` or any other ceiling
flag -- those are a SEPARATE, pre-existing concern (directive §8) checked at each call site beside
this function's answer, never inside it, so the two questions ("did the seller ever permit this at
all" and "did the seller approve THIS buyer") cannot be quietly merged back into one boolean by a
future edit that does not know they must stay apart.

Fails closed (directive §19): every branch below that cannot prove a specific capability is
authorized returns/omits it. There is no "assume yes" branch anywhere in this file."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.disclosure.levels import covers

# migrations/096_request.sql's `request_one_active_per_buyer_listing_uq` is a UNIQUE index on
# (listing_id, buyer_user_id) WHERE status IN ('PENDING','APPROVED') -- so at most ONE row can ever
# match "this listing, this buyer, status = 'APPROVED'" at a time. `cur.fetchone()` below relies on
# that database invariant directly: this is a single-row lookup, not an aggregation, and there is
# deliberately no ORDER BY/LIMIT to pick "the latest" among several, because several can never exist.
_ACTIVE_GRANT_SQL = (
    "SELECT approved_disclosure_level FROM request"
    " WHERE listing_id = %s AND buyer_user_id = %s AND status = 'APPROVED'"
    "   AND (expires_at IS NULL OR expires_at > now())"
)


def authorized_capabilities(conn: Any, *, listing_id: str, seller_id: str | None, buyer_account_id: str | None) -> frozenset[str]:
    """Every capability `buyer_account_id` currently holds for `listing_id` — the ceiling flags are
    NOT applied here (see module docstring); this is the grant alone."""
    if buyer_account_id is None or (seller_id is not None and str(buyer_account_id) == str(seller_id)):
        return frozenset()
    with conn.cursor() as cur:
        cur.execute(_ACTIVE_GRANT_SQL, (listing_id, buyer_account_id))
        row = cur.fetchone()
    return covers(row[0]) if row is not None else frozenset()


def has_capability(conn: Any, *, listing_id: str, seller_id: str | None, buyer_account_id: str | None, capability: str) -> bool:
    return capability in authorized_capabilities(conn, listing_id=listing_id, seller_id=seller_id, buyer_account_id=buyer_account_id)


def authorized_capabilities_bulk(
    conn: Any, *, buyer_account_id: str | None, listings: Sequence[tuple[str, str | None]]
) -> dict[str, frozenset[str]]:
    """`authorized_capabilities` for many listings in ONE extra query (directive §23) — the shape
    the paginated list route (Task 8) needs. `listings` is `(listing_id, seller_id)` pairs; the
    result is keyed by `listing_id` (str) and always has one entry per input pair, `frozenset()`
    for every listing with no active grant."""
    result: dict[str, frozenset[str]] = {listing_id: frozenset() for listing_id, _seller_id in listings}
    if buyer_account_id is None or not listings:
        return result
    ids = [listing_id for listing_id, seller_id in listings if seller_id is None or str(seller_id) != str(buyer_account_id)]
    if not ids:
        return result
    with conn.cursor() as cur:
        # ::uuid[] (deviation from the plan's literal SQL, see task-03-report.md): `ids` is a list
        # of Python `str`, which psycopg2 sends as a `text[]` array literal with no type hint of its
        # own -- `uuid = ANY(text[])` has no operator in PostgreSQL (unlike a bare scalar `%s` in
        # direct assignment/comparison position against one uuid column, which gets an implicit
        # cast for free). The explicit cast makes this the same single indexed `= ANY(...)` lookup
        # the plan intended, just spelled so PostgreSQL agrees on both sides' types.
        cur.execute(
            "SELECT listing_id, approved_disclosure_level FROM request"
            " WHERE listing_id = ANY(%s::uuid[]) AND buyer_user_id = %s AND status = 'APPROVED'"
            "   AND (expires_at IS NULL OR expires_at > now())",
            (ids, buyer_account_id),
        )
        for listing_id, level in cur.fetchall():
            result[str(listing_id)] = covers(level)
    return result
