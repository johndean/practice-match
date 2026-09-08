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

import json
import re
from collections.abc import AsyncGenerator
from contextlib import closing
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from python_multipart.exceptions import FormParserError

# Starlette's own UploadFile, not FastAPI's subclass of it: the form parser produces the base
# class, so `isinstance(field, fastapi.UploadFile)` is False for every real upload.
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.api.listings import PHOTOS_ROOT, REQUIRE_LISTING_READ, _error, drop_list_cache, photo_list
from app.auth import audit
from app.auth import permissions as P
from app.auth import sessions as S
from app.auth.deps import require
from app.auth.limits import (
    LISTING_CREATE,
    LISTING_DELETE,
    LISTING_PATCH,
    LISTING_REORDER,
    LISTING_UPLOAD,
    hit,
)
from app.cache import sync_redis
from app.config import settings
from app.db import sync_conn
from app.media.encode import MAX_PHOTOS, encode_webp, sha256_hex
from app.storage import ObjectStore

router = APIRouter(prefix="/api/seller")

# Hoisted, never wrapped (Global Constraint (f)).
REQUIRE_MANAGE_OWN = require("listing.manage_own")
Owner = Annotated[S.Principal, Depends(REQUIRE_MANAGE_OWN)]
# The document read is `listing.read`'s, not `listing.manage_own`'s: every member may ASK for a
# document and the handler decides (D19). The guard object is `app/api/listings.py`'s own, imported
# rather than re-created, because `deps.permission_of` resolves a route's permission by the guard's
# IDENTITY — a second `require("listing.read")` here would be a second object for one permission.
Reader = Annotated[S.Principal, Depends(REQUIRE_LISTING_READ)]

MAX_LIST = 200
DEFAULT_LIMIT = 50
MAX_TEXT = 4_000
# A-SL18 (3), Minor-2. H1 bounded every upload's body; a chunked, length-less JSON body on the two
# PATCH routes below (`patch_step`, `reorder_photos`) was still read whole into memory by
# `request.body()` — the same unbounded-body exposure, from the same authenticated seller, on the
# same surface. 64 KB is generous for a single wizard step's whitelisted fields or a photo id list.
MAX_JSON_BYTES = 64 * 1024
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
# A-SL13 M1. D10's "refuse anything else" means garbage, not blanks. `state.w` initialises every
# numeric to `""` (logic.js:204); step 4 validates nothing at all and step 3 lets `rev` be blank
# whenever the range option is on (logic.js:1217), so the resting value SL7's autosave PATCHes IS
# the empty string — and a seller who has typed a number must be able to clear it again. `est` and
# `price` are not here: the design's own step validation guarantees both before it advances, and
# `listing_submittable_ck` demands them, so a blank one is the adapter disagreeing with the design.
OPTIONAL_NUMERIC = ("rev", "docs", "rooms", "sqft")
# 016's column types, so a number that cannot fit is a refusal rather than psycopg2's
# NumericValueOutOfRange escaping as a 500 (review L3). Negatives never arrive: `isdecimal()`.
INT_MAX, BIGINT_MAX = 2**31 - 1, 2**63 - 1
# `listing_submittable_ck`'s own list and its own exemptions (030). Mirrored rather than inferred:
# when the CHECK changes, this is the line that has to change with it (review M2).
REQUIRED_ONCE_SUBMITTED = ("name", "city", "zip", "type", "est", "price")
SUBMITTABLE_EXEMPT = ("draft", "withdrawn")

_COLUMNS = """id, slug, name, city, zip, state, area, market, type, est, ownership, price, rev,
              docs, rooms, sqft, hours, services, bldg, facility_type, facility, status,
              location_disclosed, name_disclosed, rev_disclosed, documents_disclosed,
              photos, seller_id, submitted_at, created_at, updated_at"""


class Refusal(Exception):
    """A refusal the route renders through `_error`. Carries the envelope, never a status alone."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _number(field: str, raw: object) -> int | None:
    """A money or integer field as the design's text inputs produce it ("1,450,000", "$2,100,000").

    D10's last paragraph: strip `,`, `$` and spaces, refuse anything else. Not `int(float(x))` — a
    seller typing "1.45m" must be told, not silently given a practice worth one dollar.

    An empty string OR a JSON `null` CLEARS an optional field (A-SL13 M1; the `null` half is
    A-SL18 (5), Info-2 — the two clearing idioms are the same seller intent) and both still refuse
    a required one, and a number the column cannot hold is a 422 rather than a 500 (review L3)."""
    if raw is None and field in OPTIONAL_NUMERIC:
        return None
    if isinstance(raw, int) and not isinstance(raw, bool):
        cleaned = str(raw)
    elif isinstance(raw, str):
        if not raw.strip() and field in OPTIONAL_NUMERIC:
            return None
        cleaned = raw.replace(",", "").replace("$", "").replace(" ", "")
    else:
        raise Refusal("BAD_REQUEST", f"{field} must be a number.", 400)
    if not cleaned.isdecimal():
        raise Refusal("BAD_REQUEST", f"{field} must be a number.", 400)
    value = int(cleaned)
    if value > (BIGINT_MAX if field in MONEY_FIELDS else INT_MAX):
        raise Refusal("OUT_OF_RANGE", f"{field} is larger than this listing can hold.", 422)
    return value


def _text(field: str, raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise Refusal("BAD_REQUEST", f"{field} must be text.", 400)
    if len(raw) > MAX_TEXT:
        raise Refusal("BAD_REQUEST", f"{field} is too long.", 400)
    if "\x00" in raw:
        # psycopg2 raises a bare `ValueError("A string literal cannot contain NUL")` from
        # `cur.execute`, which reached the client as a 500 (review L3). Postgres cannot store one
        # in a `text` column at all, so this is the column's own rule said early.
        raise Refusal("BAD_TEXT", f"{field} must not contain a null character.", 422)
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


PHOTO_INDEX = PHOTOS_ROOT / "index.json"


@lru_cache(maxsize=1)
def seed_captions() -> dict[str, str]:
    """`<slug>/<file>` -> the caption `scripts/prepare_photos.py` recorded, read once per process.

    D26's other half: "the step-6 tile name is the seed caption or the uploaded filename". A seed
    row belongs to the demo seller on QA (D25), so Edit on one reaches `serialise_draft` and its
    `listing.photos` entries are relative paths that name no `listing_asset` row — the caption is
    the only name those tiles can have. The file is committed and copied into the image
    (`Dockerfile`: `COPY seeds/ ./seeds/`); an environment without it falls back to the file name
    rather than failing a draft read."""
    try:
        index = json.loads(PHOTO_INDEX.read_text())
        return {f"{slug}/{photo['file']}": photo["caption"]
                for slug, photos in index["hospitals"].items() for photo in photos}
    except (OSError, ValueError, KeyError):
        # Absent, malformed or restructured, the answer is the same fallback the docstring promises
        # (review L10). A draft read must not 500 because an inventory file changed shape.
        return {}


def photo_tiles(row: dict[str, Any], assets: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Step 6's tiles in `listing.photos`' own order, named as D26 says.

    Order comes from `listing.photos` and from nowhere else (D15 reason 3), which is why this is a
    projection of that array rather than a second sort of `assets`: a seller upload is named by the
    filename they chose, a seed path by its caption, and anything else by its own last segment so a
    stale entry still renders as a tile instead of throwing."""
    names = {asset["id"]: asset["name"] for asset in assets if asset["kind"] == "photo"}
    captions = seed_captions()
    return [{"id": entry, "name": names.get(entry) or captions.get(entry) or entry.rsplit("/", 1)[-1]}
            for entry in photo_list(row["photos"])]


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
        # The two ordered views step 6 renders (D26). `assets` stays exactly as SL3 wrote it — the
        # upload-ordered whole — and these are the projections: photographs in `listing.photos`'
        # order, documents with the route that reads each one back under D19's lock.
        "photos": photo_tiles(row, assets),
        "documents": [{**asset, "url": f"/api/seller/listings/{row['id']}/documents/{asset['id']}"}
                      for asset in assets if asset["kind"] != "photo"],
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


def assets_for(conn: Any, listing_ids: list[Any]) -> dict[Any, list[dict[str, Any]]]:
    """Every listing's assets, in ONE round trip (review L5).

    The dashboard used to call `assets_of` inside its comprehension: at `limit=200` that is 201
    queries for a screen that renders a name and a status. `ANY(%s)` is one, and the grouping is
    seeded from `listing_ids` so a listing with no assets still gets its empty list."""
    grouped: dict[Any, list[dict[str, Any]]] = {listing_id: [] for listing_id in listing_ids}
    if not listing_ids:
        # `= ANY('{}')` has no type Postgres can infer, and a dashboard with no listings is the
        # first thing a new seller sees.
        return grouped
    with conn.cursor() as cur:
        cur.execute("SELECT listing_id, id, kind, name, content_type, byte_size FROM listing_asset"
                    " WHERE listing_id = ANY(%s) ORDER BY listing_id, created_at, id", (listing_ids,))
        for r in cur.fetchall():
            grouped[r[0]].append({"id": str(r[1]), "kind": r[2], "name": r[3],
                                  "content_type": r[4], "byte_size": r[5]})
    return grouped


def assets_of(conn: Any, listing_id: Any) -> list[dict[str, Any]]:
    """One listing's assets — `assets_for`'s single-row case, so both read the same query."""
    return assets_for(conn, [listing_id])[listing_id]


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
        assets = assets_for(conn, [row["id"] for row in page])
        items = [serialise_draft(row, assets[row["id"]]) for row in page]
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
    slug of the same name and can never make `seed_listings.py` refuse (exit 5).

    Rate-limited like every other write (review L4): D17 named three buckets and left this one out,
    but an authenticated seller can otherwise mint unbounded rows, each taking the `slug=''`
    serialisation point on the way."""
    hit(sync_redis(), "listing:create", str(principal.account_id), *LISTING_CREATE)
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status, seller_id) VALUES ('', 'seller', 'draft', %s) RETURNING id",
                    (principal.account_id,))
        # RETURNING id on a just-inserted row always yields exactly one row (`applications.py:220`).
        listing_id = cast("tuple[UUID]", cur.fetchone())[0]
        cur.execute("UPDATE listing SET slug = %s WHERE id = %s AND seller_id = %s",
                    (f"listing-{listing_id}", listing_id, principal.account_id))
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
    try:
        body = await _json_body(request)
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
            # A-SL13 M2: `listing_submittable_ck` forbids clearing any of these once the listing
            # has been submitted, and the design invites the attempt — the seller "may keep
            # editing" an in-review listing (App.vue:1259). Refused BEFORE the statement, so the
            # CHECK can never become the 500 this module's own comment promises it never will.
            cleared = [name for name in REQUIRED_ONCE_SUBMITTED if name in columns and columns[name] is None]
            if cleared and row["status"] not in SUBMITTABLE_EXEMPT:
                raise Refusal("NOT_SUBMITTABLE",
                              f"A submitted listing cannot have {', '.join(cleared)} cleared.", 409)
            leaving_market = row["status"] == "published"
            assignments = ", ".join(f"{name} = %({name})s" for name in columns)
            sets = f"{assignments}, " if assignments else ""
            if leaving_market:
                sets += "status = 'in_review', submitted_at = now(), "
            with conn.cursor() as cur:
                cur.execute(f"UPDATE listing SET {sets}updated_at = now()"
                            " WHERE id = %(id)s AND seller_id = %(seller)s",
                            {**columns, "id": row["id"], "seller": principal.account_id})
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
    #
    # Only when the listing WAS on the market, which is D16's own wording — "every write that can
    # change a published payload" (review L6). A draft's autosave changes nothing a buyer can read,
    # and a SCAN plus a DELETE per key on each of 240 patches an hour flushes Browse for everyone.
    if leaving_market:
        drop_list_cache(sync_redis())
    return JSONResponse(payload)


# --- Assets (D14, D15, D18, D19) -----------------------------------------------------------------
#
# Photographs are RE-ENCODED (app/media/encode.py) and documents are stored as uploaded. Both are
# read back through an API route, never a signed URL: the permission decision is per request, so a
# document stops being readable the moment the listing is unpublished or the account is suspended
# — which a URL minted an hour ago cannot express (D15 reason 1).
PHOTO_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_PHOTO_BYTES = 15 * 1024 * 1024
# D18/Q3, John's ruled default: PDF, CSV and XLSX. The design names a spreadsheet ("Equipment list ·
# Spreadsheet", logic.js:1290) and only ever shows the badges "Photo" and "PDF", so CSV and XLSX are
# badged with the uppercased extension — a new VALUE in an existing slot, not new markup.
DOCUMENT_TYPES = {
    "application/pdf": ".pdf",
    "text/csv": ".csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}
DOCUMENT_KINDS = ("floor_plan", "financials", "equipment", "other")
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_DOCUMENTS = 6
DOCUMENT_HEADERS = {"Content-Disposition": "attachment", "X-Content-Type-Options": "nosniff",
                    "Cache-Control": "private, no-store"}
# What a multipart envelope costs on top of the file itself: two boundaries, the part headers and
# the `kind` field. There is no `Content-Length` pre-check any more — `_bounded_stream` bounds the
# STREAMED total at `limit + this` as the body arrives, and `_upload_bytes` then checks what
# actually arrived against `limit` exactly. Charged against the whole envelope rather than measured
# per file, so a legitimate file at exactly `limit` bytes with an unusually long filename or extra
# form fields is a spurious 413 — accepted as a conservative bound (review Info-3).
MULTIPART_OVERHEAD = 4096
MAX_FILENAME = 200


def store_for_request() -> ObjectStore:
    """The configured store, or a `Refusal` the route renders as a 503.

    `from_settings` returning None is a legitimate state (a developer's machine, a fresh test
    database), and the API must keep serving every READ there — including the eighteen seed
    hospitals' photographs, which come off disk and need no bucket at all. Only the writes stop,
    and they say why."""
    store = ObjectStore.from_settings(settings)
    if store is None:
        raise Refusal("STORAGE_UNAVAILABLE",
                      "Uploads are unavailable: object storage is not configured (S3_BUCKET).", 503)
    return store


def locked_row(conn: Any, listing_id: str, principal: S.Principal) -> dict[str, Any]:
    """This principal's listing, LOCKED for the rest of the transaction, scoped IN THE SQL.

    Two things at once, both load-bearing (SL3 review):

    * the ownership predicate is in the statement rather than in a Python comparison after a read
      by id, so no write in this module can be reached by a caller the SELECT would have refused;
    * `FOR UPDATE` serialises two concurrent uploads to the same listing, which is what makes the
      four-photo cap a real cap rather than a check-then-act race. A second request waits here and
      then counts four photographs, instead of counting three at the same instant as the first.

    A listing that is not this principal's is a 404, never a 403 (D7)."""
    try:
        parsed = UUID(listing_id)
    except ValueError:
        raise Refusal("NOT_FOUND", "No such listing.", 404) from None
    rows = _rows(conn, f"SELECT {_COLUMNS} FROM listing WHERE id = %s AND seller_id = %s FOR UPDATE",
                 (parsed, principal.account_id))
    if not rows:
        raise Refusal("NOT_FOUND", "No such listing.", 404)
    return rows[0]


def _writable(row: dict[str, Any]) -> None:
    """Withdrawn is terminal — the same rule the per-step PATCH applies, said once for the assets."""
    if row["status"] == "withdrawn":
        raise Refusal("STATE", "A withdrawn listing can no longer be edited.", 409)


def take_off_market(conn: Any, row: dict[str, Any], principal: S.Principal, request: Request) -> bool:
    """D3 for an ASSET write, in the write's own transaction (controller amendment A-SL15 (1)).

    John's ruling — "editing a published listing re-enters review and removes it from the market
    until approved again" — covers adding, reordering and deleting a photograph or a document: a
    photograph IS the listing to a buyer scrolling Browse, so a seller who swaps one on a live
    listing has changed what the market sees and the reviewer has to see it too. Same transition,
    same stamp and same audit row as `patch_step`'s own arm, which is why `EDIT_ACTION` is shared
    rather than a second name for one act.

    Returns whether the listing WAS on the market, which is also the question "must the Browse
    cache be dropped?" (D16, review L6): a draft's assets are in no published payload."""
    if row["status"] != "published":
        return False
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status = 'in_review', submitted_at = now(), updated_at = now()"
                    " WHERE id = %s AND seller_id = %s", (row["id"], principal.account_id))
    audit.write(conn, actor=principal, action=EDIT_ACTION, target_type="listing", target_id=row["id"],
                before={"status": "published"}, after={"status": "in_review"}, request=request)
    return True


def _asset_uuid(asset_id: str, noun: str = "asset") -> UUID:
    """A path segment as a uuid, or the 404 that segment names. Never FastAPI's 422 on a `UUID`
    path parameter, which would answer `{"detail": [...]}` instead of the envelope."""
    try:
        return UUID(asset_id)
    except ValueError:
        raise Refusal("NOT_FOUND", f"No such {noun}.", 404) from None


def _sniffed(content_type: str, data: bytes) -> bool:
    """Whether the BYTES agree with the declared type (D15's "content sniffed rather than trusted").

    A browser sets `Content-Type` from the file extension, and an extension is a claim the uploader
    controls. This is not a virus scan and does not pretend to be one; it is the cheap check that a
    thing stored as a PDF and served with `Content-Disposition: attachment` really is one."""
    if content_type == "application/pdf":
        return data.startswith(b"%PDF-")
    if content_type.endswith("spreadsheetml.sheet"):
        return data.startswith(b"PK\x03\x04")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _too_large(limit: int) -> str:
    return f"The file is larger than {limit // (1024 * 1024)} MB."


async def _bounded_stream(
    request: Request, limit: int, *, overhead: int = MULTIPART_OVERHEAD, message: str | None = None
) -> AsyncGenerator[bytes, None]:
    """The request body chunk by chunk, refusing the moment the running total passes the ceiling.

    A-SL16 H1, and the reason the multipart parser is driven by hand rather than through
    `request.form()`: `Content-Length` is a claim, a `Transfer-Encoding: chunked` request makes none
    at all, and Starlette puts NO ceiling on a file part — `max_part_size` guards data parts only
    (`starlette/formparsers.py`), while a file part streams into a `SpooledTemporaryFile` whose
    `spool_max_size` is the memory→disk threshold rather than a limit. So one authenticated request
    with no declared length could stream without bound onto the container's disk and then be read
    whole into memory. Bounding the stream is what makes the ceiling real: the refusal is raised
    while the body is still arriving, and at most `limit + overhead` bytes are ever buffered
    anywhere.

    `_json_body` reuses this same generator with `overhead=0` (A-SL18 (3), Minor-2): the JSON PATCH
    routes have no multipart envelope to allow for, so their boundary is `limit` exactly rather than
    `limit + MULTIPART_OVERHEAD` — a body of exactly `limit` bytes is accepted, one byte more is
    not. `message` overrides `_too_large`'s "file" wording for a caller that is bounding something
    else."""
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit + overhead:
            raise Refusal("TOO_LARGE", message or _too_large(limit), 413)
        yield chunk


async def _upload_bytes(request: Request, limit: int) -> tuple[str, str, bytes, dict[str, str]]:
    """(filename, content type, bytes, the other form fields) from a one-file multipart body.

    The text fields come back as a plain dict because the `FormData` itself does not outlive this
    function: Starlette spools a file part to a `SpooledTemporaryFile` that rolls over to disk past
    1 MB, and only FastAPI's own parameter machinery closes it — a route that parses the form owns
    the handle (A-SL15 (2)). Left open, every upload leaks a temporary file and, under `-W error`,
    a ResourceWarning that fails the suite."""
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        # Starlette answers a non-form content type with an empty `FormData`; said here, because
        # the parser below is handed the stream directly and would call it a malformed form.
        raise Refusal("BAD_REQUEST", "A single `file` part is required.", 400)
    try:
        form = await MultiPartParser(request.headers, _bounded_stream(request, limit)).parse()
    except (MultiPartException, FormParserError) as exc:
        # Two libraries, two exceptions, one refusal: Starlette raises its own for the limits it
        # enforces (too many parts, an oversized non-file part) and lets python-multipart's own
        # parse error through untouched. A body that is not the multipart form it claims to be is
        # the caller's 400, never an unhandled 500.
        raise Refusal("BAD_REQUEST", "The upload could not be read as a multipart form.", 400) from exc
    try:
        # `isinstance`, not two `hasattr`s: it is what narrows the `UploadFile | str | None` a form
        # field really is, so this reads without a `# type: ignore` (Global Constraint (c)).
        field = form.get("file")
        if not isinstance(field, UploadFile):
            raise Refusal("BAD_REQUEST", "A single `file` part is required.", 400)
        data = await field.read()
        # Belt to the stream's braces: the bound above counts the whole envelope, this counts the
        # file, so a part one byte over is refused even though the request as a whole fitted.
        if len(data) > limit:
            raise Refusal("TOO_LARGE", _too_large(limit), 413)
        # The filename is DISPLAY only — the object key is derived from the listing id and a
        # server-generated uuid, never from anything the uploader typed. Both separators are cut
        # (A-SL16 L4): a Windows client sends `C:\\Users\\jane\\accounts.pdf`, and a local path has no
        # business in the row or in the payload.
        name = re.split(r"[\\/]", field.filename or "file")[-1][:MAX_FILENAME] or "file"
        # `text/csv; charset=utf-8` is the same type as `text/csv` (A-SL16 L2); some clients send
        # the parameter and an exact comparison called them unsupported.
        content_type = (field.content_type or "").split(";", 1)[0].strip().lower()
        fields = {key: value for key, value in form.multi_items() if isinstance(value, str)}
        return name, content_type, data, fields
    finally:
        await form.close()


async def _json_body(request: Request) -> dict[str, Any]:
    """The request's JSON object, or a `Refusal` — never a raw `JSONDecodeError` (SL3 review).

    Read through `_bounded_stream` at `MAX_JSON_BYTES` with no multipart overhead (A-SL18 (3),
    Minor-2): both PATCH routes used to read the whole body through `request.body()`, which has no
    ceiling at all — the same unbounded-body exposure H1 closed on the upload routes, left standing
    here on the same authenticated surface."""
    raw = b"".join([chunk async for chunk in
                     _bounded_stream(request, MAX_JSON_BYTES, overhead=0, message="Body must be no larger than 64 KB.")])
    try:
        body = json.loads(raw) if raw else {}
    except ValueError as exc:
        raise Refusal("BAD_JSON", "Body must be JSON.", 400) from exc
    if not isinstance(body, dict):
        raise Refusal("BAD_REQUEST", "Body must be an object.", 400)
    return body


def _insert_asset(conn: Any, listing_id: UUID, kind: str, name: str, content_type: str,
                  data: bytes, digest: str, suffix: str) -> tuple[UUID, str]:
    """One row, written once, with its final key — the (asset id, storage key) pair.

    The id is minted HERE rather than by the table's default (A-SL16 M1): a placeholder
    `storage_key` would hold an entry in a table-wide UNIQUE index for the length of the whole
    transaction, and that transaction contains a bucket PUT, so two sellers uploading to two
    DIFFERENT listings would block on each other for a network round trip.

    The caller writes the object BEFORE the transaction commits: a committed row pointing at an
    object that was never written is a broken listing, while an object with no row is a few
    kilobytes nothing reads. Fail in the direction that leaves the database honest."""
    asset_id = uuid4()
    key = f"listings/{listing_id}/{'photos' if kind == 'photo' else 'documents'}/{asset_id}{suffix}"
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing_asset (id, listing_id, kind, name, content_type, byte_size,"
                    " sha256, storage_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (asset_id, listing_id, kind, name, content_type, len(data), digest, key))
    return asset_id, key


def _put(store: ObjectStore, key: str, data: bytes, content_type: str) -> None:
    """`store.put`, with a bucket outage as a refusal rather than a 500 (A-SL16 M2).

    `app/storage.py` re-raises every `ClientError` that is not a 404, so a rejected credential, a
    throttle or an outage used to leave an unhandled exception and FastAPI's
    `{"detail": "Internal Server Error"}` — not decision A5's envelope, and not the
    `STORAGE_UNAVAILABLE` code that describes exactly this."""
    try:
        store.put(key, data, content_type)
    except (BotoCoreError, ClientError) as exc:
        raise Refusal("STORAGE_UNAVAILABLE", "Object storage is unavailable; try again.", 503) from exc


def _drop_object(store: ObjectStore, key: str) -> None:
    try:
        store.delete(key)
    except (BotoCoreError, ClientError) as exc:
        raise Refusal("STORAGE_UNAVAILABLE", "Object storage is unavailable; try again.", 503) from exc


def _fetch(store: ObjectStore, key: str) -> bytes | None:
    try:
        return store.get(key)
    except (BotoCoreError, ClientError) as exc:
        raise Refusal("STORAGE_UNAVAILABLE", "Object storage is unavailable; try again.", 503) from exc


def _asset_payload(asset_id: UUID, kind: str, name: str, content_type: str, size: int) -> dict[str, Any]:
    return {"id": str(asset_id), "kind": kind, "name": name, "content_type": content_type, "byte_size": size}


@router.post("/listings/{listing_id}/photos", status_code=201)
async def upload_photo(listing_id: str, request: Request, principal: Owner) -> Response:
    """One photograph, re-encoded to WebP with every metadatum stripped (D15).

    Stripping is the point, not tidiness: a phone photograph carries GPS EXIF, and a listing whose
    location is undisclosed must not ship its coordinates inside a picture (A10.2, "Sellers control
    what buyers can see")."""
    hit(sync_redis(), "listing:upload", str(principal.account_id), *LISTING_UPLOAD)
    try:
        store = store_for_request()
        name, content_type, data, _fields = await _upload_bytes(request, MAX_PHOTO_BYTES)
        if content_type not in PHOTO_TYPES:
            raise Refusal("UNSUPPORTED_TYPE", f"A photograph must be one of {', '.join(PHOTO_TYPES)}.", 415)
        with closing(sync_conn()) as conn, conn:
            row = locked_row(conn, listing_id, principal)
            _writable(row)
            photos = photo_list(row["photos"])
            # John's ruling, restated in D18: "Keep the existing 4-photo seller-upload cap." The
            # seed pipeline's MAX_PHOTOS is the API's cap too, enforced server-side with the row
            # locked, and the fifth upload is surfaced through the wizard's single error slot
            # (logic.js:1197). Checked BEFORE the insert, so the client gets this envelope rather
            # than a constraint violation.
            if len(photos) >= MAX_PHOTOS:
                raise Refusal("PHOTO_LIMIT", f"A listing may carry {MAX_PHOTOS} photographs.", 409)
            encoded = encode_webp(data)
            if encoded is None:
                raise Refusal("BAD_IMAGE", "That file could not be read as a photograph.", 422)
            webp, digest = encoded
            asset_id, key = _insert_asset(conn, row["id"], "photo", name, "image/webp", webp, digest, ".webp")
            _put(store, key, webp, "image/webp")
            with conn.cursor() as cur:
                cur.execute("UPDATE listing SET photos = %s::jsonb, updated_at = now()"
                            " WHERE id = %s AND seller_id = %s",
                            (json.dumps([*photos, str(asset_id)]), row["id"], principal.account_id))
            on_market = take_off_market(conn, row, principal, request)
            payload = _asset_payload(asset_id, "photo", name, "image/webp", len(webp))
    except Refusal as exc:
        return _refused(exc)
    if on_market:
        drop_list_cache(sync_redis())
    return JSONResponse(payload, status_code=201)


@router.patch("/listings/{listing_id}/photos")
async def reorder_photos(listing_id: str, request: Request, principal: Owner) -> Response:
    """The full ordered id list, and nothing else moves.

    `listing.photos` is the single home of photo order (D15 reason 3), so a reorder is one UPDATE
    of that array — no `listing_asset` row carries a position to disagree with it. The list must be
    a permutation of what is already there: a partial list would silently DELETE photographs from
    the gallery, which is not what dragging a tile means."""
    hit(sync_redis(), "listing:reorder", str(principal.account_id), *LISTING_REORDER)
    try:
        body = await _json_body(request)
        ids = body.get("ids")
        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
            raise Refusal("BAD_REQUEST", "ids must be the listing's photograph ids, in the new order.", 400)
        with closing(sync_conn()) as conn, conn:
            row = locked_row(conn, listing_id, principal)
            _writable(row)
            photos = photo_list(row["photos"])
            if sorted(ids) != sorted(photos):
                raise Refusal("BAD_REQUEST",
                              "ids must be exactly this listing's photographs, in the new order.", 400)
            with conn.cursor() as cur:
                cur.execute("UPDATE listing SET photos = %s::jsonb, updated_at = now()"
                            " WHERE id = %s AND seller_id = %s",
                            (json.dumps(ids), row["id"], principal.account_id))
            on_market = take_off_market(conn, row, principal, request)
            payload = serialise_draft(locked_row(conn, listing_id, principal), assets_of(conn, row["id"]))
    except Refusal as exc:
        return _refused(exc)
    if on_market:
        drop_list_cache(sync_redis())
    return JSONResponse(payload)


@router.delete("/listings/{listing_id}/assets/{asset_id}", status_code=204)
async def delete_asset(listing_id: str, asset_id: str, request: Request, principal: Owner) -> Response:
    """One asset, gone: the object, then the row, then its entry in `listing.photos`.

    The ROW is what decides whether the asset existed. `app/storage.py`'s `delete()` does report
    whether the key was there (A-SL1, `159f526`), but an S3 delete of an absent key succeeds
    anyway, so the store cannot tell a second delete from a first and nothing here branches on its
    answer. The SELECT and the DELETE are scoped by `listing_id` as well as by asset id, so another
    listing's asset is a 404 rather than a deletion, and the listing row is locked for the whole
    transaction so two concurrent deletes of the same photograph serialise.

    The object goes FIRST, inside the transaction (A-SL16 M2): a delete that cannot remove the
    object refuses and leaves the row exactly where it was, which is recoverable. The other order
    answers 500 for work that was already done and 404 on the retry."""
    hit(sync_redis(), "listing:delete", str(principal.account_id), *LISTING_DELETE)
    try:
        store = store_for_request()
        parsed = _asset_uuid(asset_id)
        with closing(sync_conn()) as conn, conn:
            row = locked_row(conn, listing_id, principal)
            _writable(row)
            with conn.cursor() as cur:
                cur.execute("SELECT storage_key, kind FROM listing_asset WHERE id = %s AND listing_id = %s"
                            " FOR UPDATE", (parsed, row["id"]))
                found = cur.fetchone()
            if found is None:
                raise Refusal("NOT_FOUND", "No such asset.", 404)
            key, kind = found
            _drop_object(store, key)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM listing_asset WHERE id = %s AND listing_id = %s", (parsed, row["id"]))
            if kind == "photo":
                remaining = [entry for entry in photo_list(row["photos"]) if entry != str(parsed)]
                with conn.cursor() as cur:
                    cur.execute("UPDATE listing SET photos = %s::jsonb, updated_at = now()"
                                " WHERE id = %s AND seller_id = %s",
                                (json.dumps(remaining), row["id"], principal.account_id))
            on_market = take_off_market(conn, row, principal, request)
    except Refusal as exc:
        return _refused(exc)
    if on_market:
        drop_list_cache(sync_redis())
    return Response(status_code=204)


@router.post("/listings/{listing_id}/documents", status_code=201)
async def upload_document(listing_id: str, request: Request, principal: Owner) -> Response:
    """One document, stored exactly as uploaded.

    Not re-encoded: a financial statement is the seller's own artefact and re-writing it would
    change what a buyer is shown. What is checked is the TYPE (D18/Q3's three), the BYTES behind
    the declared type, the size, and the count."""
    hit(sync_redis(), "listing:upload", str(principal.account_id), *LISTING_UPLOAD)
    try:
        store = store_for_request()
        name, content_type, data, fields = await _upload_bytes(request, MAX_DOCUMENT_BYTES)
        # The approved step 6 has no kind picker (D18), so the wizard sends nothing and the row
        # reads `other`; a blank field CLEARS to the same default rather than being refused, so an
        # adapter that always sends the field behaves like one that omits it.
        kind = fields.get("kind") or "other"
        if kind not in DOCUMENT_KINDS:
            raise Refusal("BAD_REQUEST", f"kind must be one of {', '.join(DOCUMENT_KINDS)}.", 400)
        if content_type not in DOCUMENT_TYPES:
            raise Refusal("UNSUPPORTED_TYPE",
                          f"A document must be one of {', '.join(sorted(DOCUMENT_TYPES))}.", 415)
        if not _sniffed(content_type, data):
            raise Refusal("BAD_DOCUMENT", "That file's contents do not match the type it was sent as.", 422)
        with closing(sync_conn()) as conn, conn:
            row = locked_row(conn, listing_id, principal)
            _writable(row)
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM listing_asset WHERE listing_id = %s AND kind <> 'photo'",
                            (row["id"],))
                held = cast("tuple[int]", cur.fetchone())[0]
            if held >= MAX_DOCUMENTS:
                raise Refusal("DOCUMENT_LIMIT", f"A listing may carry {MAX_DOCUMENTS} documents.", 409)
            asset_id, key = _insert_asset(conn, row["id"], kind, name, content_type, data,
                                          sha256_hex(data), DOCUMENT_TYPES[content_type])
            _put(store, key, data, content_type)
            on_market = take_off_market(conn, row, principal, request)
            payload = _asset_payload(asset_id, kind, name, content_type, len(data))
    except Refusal as exc:
        return _refused(exc)
    if on_market:
        drop_list_cache(sync_redis())
    return JSONResponse(payload, status_code=201)


@router.get("/listings/{listing_id}/documents/{asset_id}")
async def read_document(listing_id: str, asset_id: str, principal: Reader) -> Response:
    """A document, to its owner and to staff and to nobody else.

    That is the design's "Locked — seller approval" exactly as it is drawn (`logic.js:1288-1290`),
    with no new approval workflow — John's ruling, D19. The buyer-with-an-accepted-request arm
    belongs to the requests sub-project and is the arm that will be added here when a `request`
    table exists; inventing it now would be inventing a workflow nobody approved.

    Guarded by `listing.read` so every member reaches the handler, and the handler is what refuses:
    the alternative — `listing.manage_own` — would answer staff a 403 from the matrix and could
    never answer them the document."""
    try:
        parsed_asset = _asset_uuid(asset_id, "document")
        parsed_listing = _asset_uuid(listing_id, "document")
        with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT a.content_type, a.storage_key, l.seller_id, l.documents_disclosed, l.status"
                        " FROM listing_asset a JOIN listing l ON l.id = a.listing_id"
                        " WHERE a.id = %s AND a.listing_id = %s AND a.kind <> 'photo'",
                        (parsed_asset, parsed_listing))
            found = cur.fetchone()
        if found is None:
            raise Refusal("NOT_FOUND", "No such document.", 404)
        content_type, key, seller_id, _disclosed, _status = found
        # Owner or staff, and NOTHING else (Major-1, A-SL18 (1)): spec D19 and §5's route table
        # allow only those two until the requests sub-project adds a buyer-with-an-accepted-request
        # arm, and `documents_disclosed`/`status` alone are not that arm — a round of this module
        # once let disclosure and "published" stand in for it, which let ANY signed-in member
        # download a document the moment a seller flipped one switch, with no request and no
        # accept. `_disclosed`/`_status` stay read off the row, unused, as the exact two values that
        # future arm will AND in beside this boolean (`… or (has_accepted_request and _disclosed and
        # _status == "published")`) — not inferred from the query, so the query needs no change
        # when that arm lands.
        #
        # Staff by the MATRIX, not by a hard-coded role tuple: `listing.review` is the staff/admin
        # capability the reviewer already holds, so a later role change moves both together.
        allowed = seller_id == principal.account_id or P.allowed("listing.review", principal)
        if not allowed:
            raise Refusal("LOCKED", "This document is locked until the seller approves access.", 403)
        store = store_for_request()
        content = _fetch(store, key)
        if content is None:
            raise Refusal("NOT_FOUND", "No such document.", 404)
    except Refusal as exc:
        return _refused(exc)
    return Response(content=content, media_type=content_type, headers=DOCUMENT_HEADERS)
