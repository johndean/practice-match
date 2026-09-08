"""The staff surface over sellers' listings (spec 2026-09-08 D9; controller amendment A-SL8).

One route today: the reviewer's read of a seller's draft. SL5 adds the review queue and the three
decisions (approve / decline / request changes) beside it.

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

from contextlib import closing
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response

from app.api.listings import _error
from app.api.seller_listings import _row, assets_of, serialise_draft
from app.auth.deps import require
from app.db import sync_conn

router = APIRouter(prefix="/api/admin")

# Hoisted, never wrapped (Global Constraint (f)). `listing.review` is staff/admin
# (`app/auth/permissions.py:38`) and is deliberately NOT in `AUDITED` — reading the queue is a poll,
# and one audit row per poll into a table whose triggers refuse DELETE is the leak I5 fix round 1
# closed for `users.review`. The DECISIONS are what SL5 audits.
REQUIRE_REVIEW = require("listing.review")


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
