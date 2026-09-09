"""The staff surface over sellers' listings (spec 2026-09-08 D9; controller amendment A-SL8).

Three routes: the reviewer's read of one seller's draft, the review QUEUE the Admin > Listings tab
renders, and the DECISION — publish, decline or unpublish — that puts a listing on the market or
takes it off (controller amendment A-SL14: one module, one router, one audit vocabulary).

**A-SL8, and the reason it is a separate module rather than an arm of `read_one`.** Spec §9's open
question 5 asked whether the reviewer should read through the seller's own route with a second
permission checked inside the handler. The answer is no: `tests/auth/test_permissions.py` resolves
a route's permission from its dependant tree by the guard object's IDENTITY, so a permission
enforced in a handler body is watched by neither the route-guard test nor the audit drift test. One
guard per route keeps both honest, and `/api/admin` is already the prefix the Coming Soon probe
asserts absent.

`serialise_draft` is imported from `app.api.seller_listings`, not re-implemented: the reviewer and
the owner must see the same draft, and two serialisers for one contract is how they stop agreeing.
`_row` is imported under its private name for the same reason and is deliberately left alone (SL3
review L7): it is the seller module's own "one row by id, or None for anything that is not one",
the reviewer needs exactly that, and renaming a function two modules read would be a wider diff
than the nit is worth. The underscore says "not the API surface", not "not importable".
"""
from __future__ import annotations

import re
from contextlib import closing
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.listings import _error, drop_list_cache
from app.api.seller_listings import _COLUMNS, _row, _rows, assets_for, assets_of, serialise_draft
from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.cache import sync_redis
from app.db import sync_conn
from app.mail.outbox import enqueue

router = APIRouter(prefix="/api/admin")

# Hoisted, never wrapped (Global Constraint (f)). `listing.review` is staff/admin
# (`app/auth/permissions.py:38`) and is deliberately NOT in `AUDITED` — reading the queue is a poll,
# and one audit row per poll into a table whose triggers refuse DELETE is the leak I5 fix round 1
# closed for `users.review`. The DECISIONS are what SL5 audits.
REQUIRE_REVIEW = require("listing.review")
# ...and the DECISION's own, which IS in `AUDITED` (spec D8): publishing, declining or unpublishing
# a listing is a staff decision of exactly the class `users.decide` is.
REQUIRE_PUBLISH = require("listing.publish")
Publisher = Annotated[S.Principal, Depends(REQUIRE_PUBLISH)]

MAX_LIST = 200
DEFAULT_LIMIT = 50
# `listing.status`'s own CHECK (migrations/030). A `status=` outside it is a 422, never
# `200 {"items": []}` — a typo in the tab must not read as "no such listings" (the F10 lesson from
# `admin_users.py`). There is no `flagged`: the design's fifth Admin row invents one and D24 says
# outright that inventing it is out of scope.
STATUSES = ("draft", "in_review", "published", "paused", "withdrawn", "declined")
# The three the design's own Listings tab offers (logic.js:1063-1067): Publish, Reject, Unpublish.
# Each names the states it is legal from, and the state it reaches.
DECISIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "publish": (("in_review", "declined", "paused"), "published"),
    "decline": (("in_review",), "declined"),
    "unpublish": (("published",), "paused"),
}
# `admin_users.py:109`'s pattern, one entry rather than four: a decline is a decision the seller is
# owed a reason for, and a blank one is a 422 rather than a row with an empty note.
NOTE_REQUIRED = ("decline",)
# An unpublish tells nobody: the design's admin footnote calls it "immediate and reversible", and
# the seller reads it on their own dashboard.
MAIL = {"publish": "listing_published", "decline": "listing_declined"}
MAX_SLUG_BASE = 80
# A-SL19 (2), Major-2. D12 makes `state` and `market` the reviewer's ONLY input, and the approved
# design reads the state back OUT of the market string — `stateOf(market)` is
# `(market || "Austin, TX").split(", ")[1] || "TX"` (logic.js:805), rendered by the buyer detail's
# subtitle and its "General location" row (A12.8/A12.9). So an unchecked "Phoenix" would publish a
# Phoenix practice the detail labels "Phoenix, TX", and `market` is also what Browse pages and
# filters on, so a malformed one quietly makes the listing unfindable. A CONSTANT rather than
# `^[A-Z]{2}$`, because `XX` matches that and is not a state.
USPS_STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
})
# The shape every seeded market already has ("Austin, TX", "Lake Tahoe, CA"): a city of 2-60
# characters carrying no comma of its own, then the two-letter code.
MARKET_RE = re.compile(r"^[^,]{2,60}, [A-Z]{2}$")


class Decision(BaseModel):
    # A-SL19 (10), Info-6: a typo in a field name is refused rather than silently ignored, as the
    # seller PATCH refuses a stray field (`columns_for`). FastAPI renders the refusal through the
    # app-wide `RequestValidationError` handler (`app/auth/deps.py`), in decision A5's envelope.
    model_config = ConfigDict(extra="forbid")

    action: str = Field(max_length=32)
    reason: str = Field(default="", max_length=2_000)
    # D12: supplied by the reviewer at the FIRST publish, because the approved step 2 collects a
    # city and a ZIP and inventing a wizard field is forbidden (John's ruled default, spec Q2).
    state: str = Field(default="", max_length=2)
    market: str = Field(default="", max_length=64)


def bad_field(state: str, market: str) -> str | None:
    """Why the reviewer's two fields cannot be written, or None (A-SL19 (2)).

    Checked BEFORE the UPDATE, so a malformed metro is refused in the envelope rather than stored
    and then read back by the design as a Texas one — A-SL13 M2's rule ("validate before the
    statement") applied to the one input D12 leaves to a human."""
    if state not in USPS_STATES:
        return "state must be a two-letter US state or DC code."
    if MARKET_RE.match(market) is None:
        return 'market must read "<City>, <ST>" — the metro the design shows beside the practice.'
    if market[-2:] != state:
        return f"market must be in {state}, the state this listing is being published in."
    return None


def slug_for(name: str, listing_id: Any) -> str:
    """D13. The name in slug form plus the first eight characters of the id, so a seller's "ABC
    Animal Hospital" can never collide with the seed slug of the same name and can never make the
    next `seed_listings.py` run refuse (exit 5, its collision pre-flight).

    `name` is never null here: publish is legal only from `in_review`, `declined` and `paused`, and
    `listing_submittable_ck` (030) requires a name in every one of them. A name of nothing but
    punctuation IS reachable, though — `_text` refuses only a blank — so the empty base falls back
    rather than producing a slug that is a bare id fragment."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "listing"
    return f"{base[:MAX_SLUG_BASE]}-{str(listing_id)[:8]}"


def sellers_for(conn: Any, seller_ids: list[Any]) -> dict[Any, str | None]:
    """Each owner's display name, in ONE round trip — `assets_for`'s own shape and its own reason.

    The Admin > Listings tab names the seller beside the figures ("Dr. Susan Ortiz",
    logic.js:1063), and the queue is the only place that name is needed; `serialise_draft` is the
    OWNER's view of their own listing and has no business carrying it."""
    if not seller_ids:
        # `= ANY('{}')` has no type Postgres can infer, and a queue of unowned seed rows is the
        # ordinary state of a fresh database.
        return {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, display_name FROM account WHERE id = ANY(%s)", (seller_ids,))
        return {row[0]: row[1] for row in cur.fetchall()}


@router.get("/listings", dependencies=[Depends(REQUIRE_REVIEW)])
async def list_all(request: Request) -> Response:
    """The review queue: every listing in every status, most recently touched first.

    Keyset-paged in `/api/admin/users`'s shape — `(updated_at, id)`, so tied timestamps never drop
    a row (fix round 1, F3) — and NOT audited, for the reason `users.review` is not: one row per
    poll of a tab into a table whose triggers refuse DELETE. The DECISION below is what is audited.

    No ownership scope: `listing.review` is the permission to look at anybody's listing, which is
    the whole job."""
    raw_limit = request.query_params.get("limit")
    if raw_limit is not None and not raw_limit.isdecimal():
        return _error("BAD_FILTER", "limit must be a number.", 422)
    limit = min(max(int(raw_limit or DEFAULT_LIMIT), 1), MAX_LIST)
    status = request.query_params.get("status")
    if status is not None and status not in STATUSES:
        return _error("BAD_FILTER", f"status must be one of {', '.join(STATUSES)}.", 422)
    cursor = request.query_params.get("cursor")
    keyset: tuple[str, UUID] | None = None
    if cursor is not None:
        at, separator, raw_id = cursor.partition("|")
        try:
            if not separator:
                raise ValueError(cursor)
            datetime.fromisoformat(at)
            keyset = (at, UUID(raw_id))
        except ValueError:
            return _error("BAD_CURSOR", "cursor must be a `<timestamp>|<id>` value from a previous"
                                        " page's next_cursor.", 422)
    where = ["TRUE"] + (["status = %s"] if status else []) + (["(updated_at, id) < (%s::timestamptz, %s::uuid)"] if keyset else [])
    params: list[Any] = [*([status] if status else []), *(keyset or ())]
    with closing(sync_conn()) as conn, conn:
        rows = _rows(conn, f"SELECT {_COLUMNS} FROM listing WHERE {' AND '.join(where)}"
                           " ORDER BY updated_at DESC, id DESC LIMIT %s", (*params, limit + 1))
        page = rows[:limit]
        assets = assets_for(conn, [row["id"] for row in page])
        names = sellers_for(conn, [row["seller_id"] for row in page if row["seller_id"] is not None])
        items = [{**serialise_draft(row, assets[row["id"]]),
                  "seller_id": str(row["seller_id"]) if row["seller_id"] is not None else None,
                  "seller_name": names.get(row["seller_id"])}
                 for row in page]
    # `page` is never empty when `more` is true (one extra row was asked for and arrived), so the
    # cursor is read off `page[-1]` without a second emptiness test.
    last = page[-1] if len(rows) > limit else None
    return JSONResponse({
        "items": items,
        "next_cursor": f"{last['updated_at'].astimezone(UTC).isoformat().replace('+00:00', 'Z')}|{last['id']}" if last else None,
    })


@router.post("/listings/{listing_id}/decide")
async def decide_listing(listing_id: str, body: Decision, request: Request, principal: Publisher) -> Response:
    """Publish, decline or unpublish (D12).

    Audited from THIS body on every branch — the drift test reads `inspect.getsource(route.endpoint)`,
    so delegating the write to a helper would read as unaudited (D8) — and `action="listing.publish"`
    on all three branches is what satisfies `test_every_audited_action_is_named_after_a_permission`
    with nothing added to `MULTI_ACTION_PERMISSIONS` or `CASCADED_ACTIONS`."""
    if body.action not in DECISIONS:
        # A-SL19 (5): `422 BAD_ACTION`, the code `/api/admin/users` answers for the same mistake on
        # the same tab family (`admin_users.BadAction`).
        return _error("BAD_ACTION", f"action must be one of {', '.join(DECISIONS)}", 422)
    if body.action in NOTE_REQUIRED and not body.reason.strip():
        return _error("NOTE_REQUIRED", "A reason is required to decline a listing.", 422)
    allowed_from, after = DECISIONS[body.action]
    try:
        parsed = UUID(listing_id)
    except ValueError:
        return _error("NOT_FOUND", "No such listing.", 404)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, name, state, seller_id FROM listing WHERE id = %s FOR UPDATE", (parsed,))
            row = cur.fetchone()
            if row is None:
                return _error("NOT_FOUND", "No such listing.", 404)
            before, name, state, seller_id = row
            if before not in allowed_from:
                return _error("STATE", f"cannot {body.action} a listing in state {before}", 409)
            first_publish = body.action == "publish" and state is None
            if first_publish and not (body.state.strip() and body.market.strip()):
                # 030's publishable CHECK would refuse this anyway; answering it here means the
                # reviewer is told which two fields, in the envelope, instead of meeting a 500.
                return _error("FIELDS_REQUIRED",
                              "state and market are required to publish this listing for the first time.", 422)
            problem = bad_field(body.state.strip(), body.market.strip()) if first_publish else None
            if problem is not None:
                return _error("BAD_FIELD", problem, 422)
            sets = "status = %(status)s, updated_at = now()"
            params: dict[str, Any] = {"status": after, "id": parsed}
            if first_publish:
                # D13's rewrite happens ONCE, here: a republished listing keeps the slug buyers may
                # have bookmarked.
                # A-SL19 (3), Major-3: Browse SORTS and pages on `listed_at`
                # (`ORDER BY listed_at DESC, id DESC`, `listing_page_idx`), so a draft created in
                # March and published today would otherwise land mid-list where no buyer paging
                # "newest first" would ever meet it. Stamped here and never again: a republish
                # after review is not a new listing and keeps the date buyers have seen.
                sets += ", state = %(state)s, market = %(market)s, slug = %(slug)s, listed_at = now()"
                params |= {"state": body.state.strip(), "market": body.market.strip(),
                           "slug": slug_for(name, parsed)}
            cur.execute(f"UPDATE listing SET {sets} WHERE id = %(id)s", params)
            cur.execute("SELECT email FROM account WHERE id = %s", (seller_id,))
            owner = cur.fetchone()
        template = MAIL.get(body.action)
        if template is not None and owner is not None:
            # A-SL19 (6): only `listing_declined` declares a `reason`, so passing one with a
            # publish persisted a reviewer's free text in `email_outbox.params` for a mail that can
            # never render it.
            enqueue(conn, to=cast("tuple[str]", owner)[0], template=template,
                    params={"reason": body.reason} if template == MAIL["decline"] else {},
                    idempotency_key=f"{parsed}:{template}:{before}->{after}")
        audit.write(conn, actor=principal, action="listing.publish", target_type="listing",
                    target_id=parsed, before={"status": before}, after={"status": after},
                    # Free text, and a staff member's own words — never a credential, the rule
                    # `admin_users.decide_route` records. `before`/`after` are redacted by
                    # `audit.write`; `reason` is not, so nothing but the decision and the note goes in.
                    reason=body.action if not body.reason.strip() else f"{body.action}: {body.reason}",
                    request=request)
        # A-SL19 (9), Info-4: the whole draft, like every seller route, so the tab can link to the
        # listing it has just published — the slug it needs for that link is written above, by this
        # request. Read after the audit row so `decline_reason` carries the decision just made.
        decided = _rows(conn, f"SELECT {_COLUMNS} FROM listing WHERE id = %s", (parsed,))[0]
        payload = serialise_draft(decided, assets_of(conn, parsed))
    # AFTER the commit (D16): a publish must reach Browse at once and an unpublish must leave it at
    # once, and dropping the key while the write was uncommitted would re-cache the old payload.
    drop_list_cache(sync_redis())
    return JSONResponse(payload)


@router.get("/listings/{listing_id}", dependencies=[Depends(REQUIRE_REVIEW)])
async def read_one(listing_id: str) -> Response:
    """One seller's draft, in the owner's own unblanked shape (D11).

    No ownership scope: `listing.review` is the permission to look at anybody's listing, which is
    the whole job. An id that names no listing — or is not a uuid at all — is this module's 404
    rather than FastAPI's 422 on a `UUID` path parameter."""
    with closing(sync_conn()) as conn, conn:
        row: dict[str, Any] | None = _row(conn, listing_id)
        if row is None:
            return _error("NOT_FOUND", "No such listing.", 404)
        return JSONResponse(serialise_draft(row, assets_of(conn, row["id"])))
