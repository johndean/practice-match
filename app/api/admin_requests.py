"""`GET /api/admin/requests` — the Admin > Requests tab's first real data (Task ADMIN-REQUESTS,
spec `docs/superpowers/specs/2026-09-21-request-oversight-thread-design.md`, "Two prerequisites"
for ruling D-C63's staff oversight thread, which this module does NOT build — see that spec's own
"the thread itself is NOT" scope note).

`request.oversee` (`app/auth/permissions.py:52`, `_STAFF`) had ZERO call sites before this route;
this is its first. There was no admin read across the disclosure-request lifecycle at all —
`app/api/requests.py` is the buyer's own door (`request.create`/`request.read_own`),
`app/api/seller_requests.py` is the seller's own inbox (`request.answer_own`) — so this module,
`app/disclosure/requests.py`'s third reader, is where staff first sees across both.

**Shape mirrors `app/api/admin_users.py::list_users`** (Task A36's own precedent, applied one tab
over): a keyset `(requested_at, id)` cursor so two rows sharing a timestamp are never dropped
(`admin_users.py`'s own fix round 1, F3), a `counts` object beside `items` computed over the WHOLE
`request` table and served on the FIRST page only — a cursored page answers `counts: null`, because
the badge describes the table and a paging caller already holds it (`admin_users.py`'s own review
Minor 1) — and NOT audited: `listing.review`'s own reason, restated here for `request.oversee`,
"reading the queue is a poll, and one audit row per poll into a table whose triggers refuse DELETE
is the leak I5 fix round 1 closed once already." The per-item DECIDE this precedent audits has no
counterpart here — staff does not decide a disclosure request, the seller does
(`app/api/seller_requests.py::decide_request`) — so there is no decision this module could audit
even if the design's own four-column table (Request, Practice, Status, Age; no Action column at
all) offered one.

**Identity — deliberate, per the task brief's own instruction.** `app/api/requests.py::_BUYER_HIDDEN`
exists because a BUYER must never learn a SELLER's identity (`seller_user_id` is stripped from
every buyer-facing response); that rule has no bearing here, because the caller is STAFF, not a
buyer, and `request.oversee` is precisely the permission to see both parties to a disclosure
request. So `LIST_SQL` joins `account` TWICE — once for the buyer, once for the seller — on
`app/disclosure/requests.py::list_inbox`'s own idiom (`display_name`, falling back to `email`,
never a fabricated person; that function's own docstring: "the identical 'an id nobody can read'
problem `admin_users.py::LIST_SQL`'s `d.display_name`/`gb.display_name` joins already answer") —
and a `listing` join for the practice's own `name`/`type`/`city`, read by `admin/listings.ts`'s own
`item.name || label || 'Untitled listing'` idiom on the frontend side, so a row never claims a
clinical category ("Small animal practice") that no column actually holds.

**What this route deliberately does NOT serve.** The design's own Requests tab footnote
(`logic.js`'s `sets.activity.footnote`) says outright: "Message contents are visible only in an
abuse investigation, and every such view is logged." Selecting `request.message` into a list a
reviewer polls routinely would make that sentence false the day this route shipped — an
investigation-gated single-request read is a real future door and not one this list quietly opens.
`denial_reason` (the seller's own words on a DENIED row) is left out for the same "serve what the
tab renders and no more" reason: the design's four columns (Request, Practice, Status, Age) have
no slot for it, unlike the Listings tab's `decline_reason` sub-line, which the design DOES draw a
slot for."""
from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.api.listings import _error
from app.auth.deps import AuthError, require
from app.db import sync_conn

router = APIRouter(prefix="/api/admin")

# Hoisted, never wrapped (`admin_listings.py`'s own Global Constraint note): the route-guard test
# resolves a route's permission by the guard object's IDENTITY, so a permission enforced any other
# way would read as unguarded. No `Overseer`/`Depends(...)` handler parameter exists beside it —
# this route reads no `Principal` field and is not audited (module note), so `admin_listings.py`'s
# own `list_all` is the precedent: `dependencies=[Depends(REQUIRE_REVIEW)]` alone, nothing named.
REQUIRE_OVERSEE = require("request.oversee")

MAX_LIST = 200
DEFAULT_LIMIT = 50

# `request.status`'s own CHECK (migrations/096_request.sql). A `status=` outside it is a 422,
# never `200 {"items": []}` — `admin_users.py`'s own F10 lesson: a typo in the tab's own filter
# must not read as "no such requests".
STATUSES = ("PENDING", "APPROVED", "DENIED", "REVOKED")


class BadCursor(AuthError):
    status = 422
    code = "BAD_CURSOR"
    message = "cursor must be a `<timestamp>|<id>` value from a previous page's next_cursor."


class BadFilter(AuthError):
    status = 422
    code = "BAD_FILTER"

    def __init__(self, name: str, allowed: tuple[str, ...]) -> None:
        self.message = f"{name} must be one of {', '.join(allowed)}"
        super().__init__()


CURSOR_SEPARATOR = "|"


def _cursor(requested_at: str, request_id: str) -> str:
    """`admin_users.py::_cursor`'s own shape and its own reason: URL-safe (a `+00:00` offset would
    decode back from a query string as a space; `Z` survives the round trip and both
    `datetime.fromisoformat` and Postgres accept it), and carries the id as well as the timestamp
    so two rows sharing one `requested_at` are never dropped."""
    return f"{datetime.fromisoformat(requested_at).astimezone(UTC).isoformat().replace('+00:00', 'Z')}{CURSOR_SEPARATOR}{request_id}"


def _keyset(cursor: str | None) -> tuple[str | None, UUID | None]:
    if cursor is None:
        return None, None
    at, separator, raw_id = cursor.partition(CURSOR_SEPARATOR)
    if not separator:
        raise BadCursor
    try:
        datetime.fromisoformat(at)
        return at, UUID(raw_id)
    except ValueError:
        raise BadCursor from None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


# The badge: every PENDING request over the WHOLE table, the one status still waiting on a seller
# to act — `admin_users.py::COUNTS_SQL`'s own one-grouped-scan pattern, so the badge and the total
# can never disagree with each other about which rows they came from.
COUNTS_SQL = "SELECT status, count(*) FROM request GROUP BY 1"


def queue_counts(conn: Any) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(COUNTS_SQL)
        rows = cast("list[tuple[str, int]]", cur.fetchall())
    return {"pending": sum(n for status, n in rows if status == "PENDING"), "total": sum(n for _status, n in rows)}


_COLUMNS = (
    "r.id, r.status, r.requested_disclosure_level, r.approved_capabilities,"
    " r.requested_at, r.reviewed_at, r.listing_id, r.buyer_user_id, r.seller_user_id,"
    # ALIASED, not bare — `b.display_name`/`se.display_name` (and `.email` beside each) would
    # otherwise both land in a dict key named `display_name`/`email`, and `dict(zip(names, row))`
    # keeps only the LAST occurrence of a repeated key: the buyer's own name would be silently
    # overwritten by the seller's, in a dict that is never even wrong-shaped enough to raise.
    " b.display_name AS buyer_display_name, b.email AS buyer_email,"
    " se.display_name AS seller_display_name, se.email AS seller_email,"
    " l.name AS listing_name, l.type AS listing_type, l.city AS listing_city"
)

# Both account joins are INNER: `request.buyer_user_id`/`seller_user_id` are `NOT NULL REFERENCES
# account(id) ON DELETE CASCADE` (migrations/096_request.sql), so a request row can never outlive
# either account, and `listing_id` carries the identical `NOT NULL … ON DELETE CASCADE` — a request
# can never outlive its listing either. No `LEFT JOIN` is standing in for a case that cannot occur.
LIST_SQL = f"""
SELECT {_COLUMNS}
  FROM request r
  JOIN account b ON b.id = r.buyer_user_id
  JOIN account se ON se.id = r.seller_user_id
  JOIN listing l ON l.id = r.listing_id
 WHERE (%(status)s::text IS NULL OR r.status = %(status)s)
   AND (%(cursor_at)s::timestamptz IS NULL
        OR (r.requested_at, r.id) < (%(cursor_at)s::timestamptz, %(cursor_id)s::uuid))
 ORDER BY r.requested_at DESC, r.id DESC
 LIMIT %(limit)s
"""


def _name(display_name: str | None, email: str) -> str:
    """`app/disclosure/requests.py::list_inbox`'s own fallback, applied to both parties: a real
    identity already on file rather than `None` or a blank string."""
    return (display_name or "").strip() or email


@router.get("/requests", dependencies=[Depends(REQUIRE_OVERSEE)])
async def list_requests(request: Request) -> Response:
    """The disclosure-request queue across every seller and every buyer — `request.oversee`'s
    first call site. See the module docstring for what is served, what is deliberately withheld,
    and why this route is not audited."""
    raw_limit = request.query_params.get("limit")
    if raw_limit is not None and not raw_limit.isdecimal():
        return _error("BAD_FILTER", "limit must be a number.", 422)
    limit = min(max(int(raw_limit or DEFAULT_LIMIT), 1), MAX_LIST)
    status = request.query_params.get("status")
    if status is not None and status not in STATUSES:
        raise BadFilter("status", STATUSES)
    cursor = request.query_params.get("cursor")
    cursor_at, cursor_id = _keyset(cursor)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute(LIST_SQL, {"status": status, "cursor_at": cursor_at, "cursor_id": cursor_id, "limit": limit + 1})
            names = [d[0] for d in cast("tuple[Any, ...]", cur.description)]
            rows = [dict(zip(names, row, strict=True)) for row in cur.fetchall()]
            counts: dict[str, int] | None = None
            if cursor is None:
                counts = queue_counts(conn)
        page = rows[:limit]
        items = [
            {
                "id": str(row["id"]),
                "status": row["status"],
                "requested_disclosure_level": row["requested_disclosure_level"],
                "approved_capabilities": row["approved_capabilities"],
                "requested_at": row["requested_at"].isoformat(),
                "reviewed_at": _iso(row["reviewed_at"]),
                "listing_id": str(row["listing_id"]),
                "listing_name": row["listing_name"],
                "listing_type": row["listing_type"],
                "listing_city": row["listing_city"],
                "buyer_user_id": str(row["buyer_user_id"]),
                "buyer_name": _name(row["buyer_display_name"], row["buyer_email"]),
                "seller_user_id": str(row["seller_user_id"]),
                "seller_name": _name(row["seller_display_name"], row["seller_email"]),
            }
            for row in page
        ]
    last = page[-1] if len(rows) > limit else None
    return JSONResponse({
        "items": items,
        "next_cursor": _cursor(cast("str", last["requested_at"].isoformat()), str(last["id"])) if last is not None else None,
        "counts": counts,
    })
