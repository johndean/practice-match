"""The seller wizard's own surface (spec 2026-09-08, D7-D13, D16, D17).

Eight approved steps, a preview and a Submit that the design has drawn since V2 and that nothing
has ever persisted. This module is that persistence, and nothing about the screens changes.

Shapes copied from `app/api/listings.py` and `app/api/admin_users.py`, all load-bearing:

* **Every guard is a module-level constant used through `Depends`, never wrapped** — the route-guard
  and audit drift tests resolve a permission by the guard object's IDENTITY (`deps.permission_of`).
* **Every refusal uses `_error(code, message, status)`** — decision A5's body, imported from
  `app.api.listings` rather than copied, because two copies is how two envelopes appear. Query
  parameters are parsed by hand for the same reason: `Query(ge=...)` answers FastAPI's
  `{"detail": [...]}`, which is not the envelope the frontend's `AuthError` reads.
* **Connections are `with closing(sync_conn()) as conn, conn:`** — psycopg2's `with conn:` commits
  without closing.

**Ownership is enforced HERE, not in the matrix (D7).** `listing.manage_own` says a seller may
manage listings; `seller_id = principal.account_id` says which. A non-owner gets 404, never 403 — a
listing that is not yours should not be confirmed to exist.

**One permission, one route (controller amendment A-SL8).** The reviewer's read of a seller's draft
is NOT a second permission checked inside `read_one`; it is its own route,
`GET /api/admin/listings/{id}` in `app/api/admin_listings.py`, guarded once by `listing.review`.
A permission enforced in a handler body is invisible to `tests/auth/test_permissions.py`, which
resolves a route's guard by object identity — so a second one there would be watched by nothing.

**`listing.manage_own` is deliberately NOT in `permissions.AUDITED` (D8):** the wizard's autosave
rides on it, and one audit row per step per keystroke-batch into a table whose triggers refuse
DELETE is a slow leak. The transitions still write their own rows, under action names that name no
permission BY DESIGN — exactly like `applications.submit`/`answer`/`reapply`, and outside the drift
test's reach for the same documented reason. `tests/api/test_seller_listings.py` asserts that on
purpose rather than leaving it to be noticed.
"""
from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.api.listings import _error, drop_list_cache
from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.auth.limits import LISTING_PATCH, hit
from app.cache import sync_redis
from app.db import sync_conn

router = APIRouter(prefix="/api/seller")

# Hoisted, never wrapped (Global Constraint (f)).
REQUIRE_MANAGE_OWN = require("listing.manage_own")
Owner = Annotated[S.Principal, Depends(REQUIRE_MANAGE_OWN)]

MAX_LIST = 200
DEFAULT_LIMIT = 50
MAX_TEXT = 4_000
# The transitions the SELLER's own routes write. They name no permission by design — `account.self`
# does the same for `applications.submit`/`answer`/`reapply` — so the AST drift test never sees
# them and there is no list to add them to. One namespace, so an auditor greps `listing.` once.
EDIT_ACTION = "listing.edit"

# --- D10: the per-step whitelist, and the four mappings the approved design forces ---------------
#
# 1. `desc` is the `services` column. Step 4's textarea is `area("desc", "Services offered", ...)`
#    (logic.js:1177); `note` is the overview prose the seeder writes, not this.
# 2. `bldg` needs a value map: the select offers "Available separately" and the column's CHECK
#    allows 'Separate'.
# 3. `type` accepts 'Other' — the step-1 select offers it and migration 030 widened the CHECK.
# 4. `facilityType` had no column at all; 030 adds `facility_type`.
STEP_FIELDS: dict[int, tuple[str, ...]] = {
    1: ("name", "type", "est", "ownership"),
    2: ("city", "zip", "anon"),
    3: ("price", "rev", "revBand"),
    4: ("docs", "rooms", "sqft", "hours", "desc"),
    5: ("bldg", "facilityType", "facility"),
    7: ("anon", "revBand", "docsLocked"),
}
# The design's own option lists (logic.js:1174, :1178), checked here so a CheckViolation from the
# database can never become a 500.
TYPES = ("Small animal", "Mixed", "Large animal", "Emergency", "Specialty", "Other")
OWNERSHIPS = ("Sole proprietor", "Two-doctor partnership", "Multi-doctor LLC", "Other")
FACILITY_TYPES = ("Standalone", "Strip or plaza", "Medical park", "Other")
BLDG_IN = {"Included": "Included", "Available separately": "Separate", "Leased": "Leased"}
BLDG_OUT = {value: key for key, value in BLDG_IN.items()}
MONEY_FIELDS = ("price", "rev")
INT_FIELDS = ("est", "docs", "rooms", "sqft")

_COLUMNS = """id, slug, name, city, zip, state, area, market, type, est, ownership, price, rev,
              docs, rooms, sqft, hours, services, bldg, facility_type, facility, status,
              location_disclosed, name_disclosed, rev_disclosed, documents_disclosed,
              photos, seller_id, submitted_at, created_at, updated_at"""


class Refusal(Exception):
    """A refusal the route renders through `_error`. Carries the envelope, never a status alone."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _number(field: str, raw: object) -> int:
    """A money or integer field as the design's text inputs produce it ("1,450,000", "$2,100,000").

    D10's last paragraph: strip `,`, `$` and spaces, refuse anything else. Not `int(float(x))` — a
    seller typing "1.45m" must be told, not silently given a practice worth one dollar."""
    if isinstance(raw, int) and not isinstance(raw, bool):
        cleaned = str(raw)
    elif isinstance(raw, str):
        cleaned = raw.replace(",", "").replace("$", "").replace(" ", "")
    else:
        raise Refusal("BAD_REQUEST", f"{field} must be a number.", 400)
    if not cleaned.isdecimal():
        raise Refusal("BAD_REQUEST", f"{field} must be a number.", 400)
    return int(cleaned)


def _text(field: str, raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise Refusal("BAD_REQUEST", f"{field} must be text.", 400)
    if len(raw) > MAX_TEXT:
        raise Refusal("BAD_REQUEST", f"{field} is too long.", 400)
    return raw.strip() or None


def _one_of(field: str, raw: object, allowed: tuple[str, ...]) -> str:
    """One of `allowed`, or a `Refusal`.

    The `value is None` arm is spelled out rather than left to `not in`: `_text` types as
    `str | None`, `mypy --strict` does not narrow a membership test against a `tuple[str, ...]`,
    and neither `# type: ignore` nor `assert` is available to paper over it (Global Constraint (c))."""
    value = _text(field, raw)
    if value is None or value not in allowed:
        raise Refusal("BAD_REQUEST", f"{field} must be one of {', '.join(allowed)}.", 400)
    return value


def _flag(field: str, raw: object) -> bool:
    if not isinstance(raw, bool):
        raise Refusal("BAD_REQUEST", f"{field} must be true or false.", 400)
    return raw


def columns_for(step: int, body: dict[str, Any]) -> dict[str, Any]:
    """The step's fields as database columns, or a `Refusal`.

    The whitelist is one-directional and total: a field from another step is a 400 rather than a
    silent no-op, because the wizard sends one step at a time and a mis-sent field means the
    adapter and this table disagree — which is a bug to see, not to absorb."""
    if step not in STEP_FIELDS:
        raise Refusal("BAD_REQUEST", f"step must be one of {', '.join(str(s) for s in sorted(STEP_FIELDS))}.", 400)
    stray = sorted(set(body) - set(STEP_FIELDS[step]))
    if stray:
        raise Refusal("BAD_REQUEST", f"step {step} does not accept {', '.join(stray)}.", 400)
    out: dict[str, Any] = {}
    for field, raw in body.items():
        if field in MONEY_FIELDS or field in INT_FIELDS:
            out[field] = _number(field, raw)
        elif field == "type":
            out["type"] = _one_of("type", raw, TYPES)
        elif field == "ownership":
            out["ownership"] = _one_of("ownership", raw, OWNERSHIPS)
        elif field == "facilityType":
            out["facility_type"] = _one_of("facilityType", raw, FACILITY_TYPES)
        elif field == "bldg":
            out["bldg"] = BLDG_IN[_one_of("bldg", raw, tuple(BLDG_IN))]
        elif field == "desc":
            out["services"] = _text("desc", raw)
        elif field == "anon":
            # D20: the design's step-7 label names BOTH the practice name and the address, so one
            # switch sets both columns. The API keeps them independent, so Rev 3's split into four
            # switches needs no API change.
            shown = not _flag("anon", raw)
            out["name_disclosed"] = out["location_disclosed"] = shown
        elif field == "revBand":
            out["rev_disclosed"] = not _flag("revBand", raw)
        elif field == "docsLocked":
            out["documents_disclosed"] = not _flag("docsLocked", raw)
        else:
            out[field] = _text(field, raw)
    if step == 2 and "city" in out:
        # `area` is the card's own label and `serialise` interpolates it into the anonymised name.
        # The approved step 2 collects a city and a ZIP, so the city IS the area; `state` and
        # `market` come from the reviewer at the first publish (D12).
        out["area"] = out["city"]
    return out


def serialise_draft(row: dict[str, Any], assets: list[dict[str, Any]]) -> dict[str, Any]:
    """The OWNER's own truth (D11) — every column unblanked, nulls preserved, plus `assets[]`.

    Deliberately not `serialise`: that one is the BUYER contract, it applies the disclosure
    blanking, and every published-listing pixel depends on it. Two serialisers is what keeps the
    zero-regression claim on the read surface a fact rather than a hope.

    The keys are the wizard's own (`state.w` in logic.js:204), not the columns': the adapter hands
    this straight to `setW`, so `services` comes back as `desc`, `facility_type` as `facilityType`
    and `bldg` in the design's own wording."""
    return {
        "id": str(row["id"]), "status": row["status"],
        "name": row["name"], "type": row["type"], "est": row["est"], "ownership": row["ownership"],
        "city": row["city"], "zip": row["zip"],
        "price": row["price"], "rev": row["rev"],
        "docs": row["docs"], "rooms": row["rooms"], "sqft": row["sqft"], "hours": row["hours"],
        "desc": row["services"],
        "bldg": BLDG_OUT.get(row["bldg"]) if row["bldg"] else None,
        "facilityType": row["facility_type"], "facility": row["facility"],
        # The three switches, in the design's own polarity: on means HIDE.
        "anon": not row["name_disclosed"],
        "revBand": not row["rev_disclosed"],
        "docsLocked": not row["documents_disclosed"],
        "state": row["state"], "market": row["market"], "area": row["area"],
        "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
        "updated_at": row["updated_at"].isoformat(),
        "assets": assets,
    }


def _rows(conn: Any, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Rows as dicts keyed by the names the QUERY produced — `app/api/listings.py::_rows`'s own
    shape and its own reason (review round 2, M5): a hand-kept column tuple beside `_COLUMNS` is
    checked for LENGTH by `strict=True` and for nothing else, so swapping two names in one of the
    two lists mis-maps every row in silence.

    `conn: Any`, like its sibling: psycopg2's `cursor.description` types as `tuple[Column, ...] |
    None` and `--strict` rejects iterating it, which is not a defect worth a `cast` at every call
    site — one untyped seam, in the one function that reads a cursor's metadata."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def _row(conn: Any, listing_id: str) -> dict[str, Any] | None:
    try:
        parsed = UUID(listing_id)
    except ValueError:
        return None
    rows = _rows(conn, f"SELECT {_COLUMNS} FROM listing WHERE id = %s", (parsed,))
    return rows[0] if rows else None


def owned_row(conn: Any, listing_id: str, principal: S.Principal) -> dict[str, Any]:
    """The listing, or a 404 `Refusal` — for anything that is not this principal's (D7)."""
    row = _row(conn, listing_id)
    if row is None or row["seller_id"] != principal.account_id:
        raise Refusal("NOT_FOUND", "No such listing.", 404)
    return row


def assets_of(conn: Any, listing_id: Any) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, kind, name, content_type, byte_size FROM listing_asset"
                    " WHERE listing_id = %s ORDER BY created_at, id", (listing_id,))
        return [{"id": str(r[0]), "kind": r[1], "name": r[2], "content_type": r[3], "byte_size": r[4]}
                for r in cur.fetchall()]


def _refused(exc: Refusal) -> JSONResponse:
    return _error(exc.code, exc.message, exc.status)


@router.get("/listings", dependencies=[Depends(REQUIRE_MANAGE_OWN)])
async def list_mine(request: Request) -> Response:
    """The dashboard's source: every status, most recently touched first — `listing_owner_idx`'s
    own order. Keyset-paged in `/api/admin/users`'s shape."""
    principal = request.state.principal
    raw_limit = request.query_params.get("limit")
    if raw_limit is not None and not raw_limit.isdecimal():
        return _error("BAD_REQUEST", "Invalid limit.", 400)
    limit = min(max(int(raw_limit or DEFAULT_LIMIT), 1), MAX_LIST)
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
            return _error("BAD_REQUEST", "Invalid cursor.", 400)
    where = "seller_id = %s" + (" AND (updated_at, id) < (%s::timestamptz, %s::uuid)" if keyset else "")
    params: list[Any] = [principal.account_id, *(keyset or ())]
    with closing(sync_conn()) as conn, conn:
        rows = _rows(conn, f"SELECT {_COLUMNS} FROM listing WHERE {where} ORDER BY updated_at DESC, id DESC LIMIT %s",
                     (*params, limit + 1))
        page = rows[:limit]
        items = [serialise_draft(row, assets_of(conn, row["id"])) for row in page]
    # `page` is never empty when `more` is true (one extra row was asked for and arrived), so the
    # cursor is read off `page[-1]` without a second emptiness test — an arm no request can reach
    # is an arm no test can cover (Global Constraint (a)).
    more = len(rows) > limit
    last = page[-1] if more else None
    return JSONResponse({
        "items": items,
        "next_cursor": f"{last['updated_at'].astimezone(UTC).isoformat().replace('+00:00', 'Z')}|{last['id']}" if last else None,
    })


@router.post("/listings", status_code=201)
async def create(principal: Owner) -> Response:
    """Called once, when *Create a listing* is first clicked.

    `slug = 'listing-' || id` (D13). It stays `NOT NULL UNIQUE`, nothing about the seeder's
    `ON CONFLICT (slug)` changes, and the first publish rewrites it to the name plus the first
    eight characters of the id — so a seller's "ABC Animal Hospital" can never collide with a seed
    slug of the same name and can never make `seed_listings.py` refuse (exit 5)."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status, seller_id) VALUES ('', 'seller', 'draft', %s) RETURNING id",
                    (principal.account_id,))
        # RETURNING id on a just-inserted row always yields exactly one row (`applications.py:220`).
        listing_id = cast("tuple[UUID]", cur.fetchone())[0]
        cur.execute("UPDATE listing SET slug = %s WHERE id = %s", (f"listing-{listing_id}", listing_id))
    return JSONResponse({"id": str(listing_id)}, status_code=201)


@router.get("/listings/{listing_id}")
async def read_one(listing_id: str, principal: Owner) -> Response:
    """The wizard's read for Edit and Continue. The OWNER's, and only theirs — the reviewer reads
    the same draft through `GET /api/admin/listings/{id}` (A-SL8)."""
    with closing(sync_conn()) as conn, conn:
        try:
            row = owned_row(conn, listing_id, principal)
        except Refusal as exc:
            return _refused(exc)
        return JSONResponse(serialise_draft(row, assets_of(conn, row["id"])))


@router.patch("/listings/{listing_id}")
async def patch_step(listing_id: str, request: Request, principal: Owner) -> Response:
    """One call per step, the step's whitelisted field set only (D10), applying D3's
    published -> in_review transition and dropping the listings cache after the commit (D16)."""
    hit(sync_redis(), "listing:patch", str(principal.account_id), *LISTING_PATCH)
    raw_step = request.query_params.get("step", "")
    body = await request.json() if await request.body() else {}
    if not isinstance(body, dict):
        return _error("BAD_REQUEST", "Body must be an object.", 400)
    try:
        step = int(raw_step) if raw_step.isdecimal() else -1
        columns = columns_for(step, body)
        with closing(sync_conn()) as conn, conn:
            row = owned_row(conn, listing_id, principal)
            if row["status"] == "withdrawn":
                raise Refusal("STATE", "A withdrawn listing can no longer be edited.", 409)
            # D3, John's ruling: the FIRST save to a published listing moves it to in_review and off
            # the market at once. `GET /api/listings` filters `status = 'published'`, so the
            # transition alone does the removing — no new code on the read side. Subsequent PATCHes
            # in the same review cycle do not re-transition, which is why this is `== 'published'`
            # and not `!= 'in_review'`.
            leaving_market = row["status"] == "published"
            assignments = ", ".join(f"{name} = %({name})s" for name in columns)
            sets = f"{assignments}, " if assignments else ""
            if leaving_market:
                sets += "status = 'in_review', submitted_at = now(), "
            with conn.cursor() as cur:
                cur.execute(f"UPDATE listing SET {sets}updated_at = now() WHERE id = %(id)s",
                            {**columns, "id": row["id"]})
            if leaving_market:
                audit.write(conn, actor=principal, action=EDIT_ACTION, target_type="listing",
                            target_id=row["id"], before={"status": "published"}, after={"status": "in_review"},
                            request=request)
            # Re-read through `owned_row` rather than a nullable `_row`: the row was just updated
            # inside this transaction, so its absence is not a state a request can reach, and a
            # ternary for it would be an arm no test could cover.
            payload = serialise_draft(owned_row(conn, listing_id, principal), assets_of(conn, row["id"]))
    except Refusal as exc:
        return _refused(exc)
    # AFTER the commit (D16, and I5c fix round 1's ordering): a disclosure flag turned OFF must stop
    # reaching buyers at once, and dropping the key while the write was uncommitted would leave a
    # window in which a concurrent read re-cached the pre-write payload for the full TTL.
    drop_list_cache(sync_redis())
    return JSONResponse(payload)
