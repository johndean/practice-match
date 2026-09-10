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
    LISTING_SUBMIT,
    LISTING_UPLOAD,
    hit,
)
from app.cache import sync_redis
from app.config import settings
from app.db import sync_conn
from app.mail.outbox import enqueue
from app.media.encode import encode_webp, sha256_hex
from app.storage import ObjectStore
from app.tasks.celery_app import celery_app

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
# The two states an edit re-enters review from (D3, widened by A-SL19 (1) on the SL5 review's
# Major-1). `paused` is published-but-hidden: it has been through review, the seller can put it
# back on the market with one click, and the arm used to fire on `published` alone — so pause →
# edit → republish returned CHANGED content to buyers that no reviewer had ever seen, with no
# audit row to say it had changed. An untouched pause/republish is still "immediate and
# reversible" (the design's admin footnote), which is all that footnote promises.
EDIT_REENTERS_REVIEW = ("published", "paused")

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
OWNERSHIPS = (
    "Sole proprietor",
    "Sole proprietor (LLC)",
    "Sole proprietor (S-corp)",
    "Two-doctor partnership",
    "Three-doctor LLC",
    "Four-doctor partnership",
    "Four-doctor LLC",
    "Five-doctor LLC",
    "Multi-doctor LLC",
    "Other",
)
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
              photos, photo_captions, seller_id, submitted_at, created_at, updated_at,
              (SELECT a.reason FROM audit_log a
                WHERE a.target_type = 'listing' AND a.target_id = listing.id::text
                  AND a.after ->> 'status' = 'declined'
                ORDER BY a.id DESC LIMIT 1) AS decline_reason"""
# A-SL19 (9), Info-3. `audit_log` is where a decision's words already live (D4), so the reason
# rides along with the row rather than in a column the decide handler would have to keep in step
# with the audit trail. `audit_log_target_idx` is `(target_type, target_id, at DESC)`, which is the
# subquery's own predicate. The recorded string is `"<action>: <the reviewer's words>"`
# (`admin_listings.decide_listing`); the seller is owed the words, not the vocabulary.
DECLINE_PREFIX = "decline: "


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


def _one_of_or_unchanged(field: str, raw: object, allowed: tuple[str, ...], stored: str | None) -> str:
    """A-SL31/A-SL32 (2): a value the seller did NOT change is not re-validated.

    `OWNERSHIPS` is the design's four-option select vocabulary while fifteen of the eighteen seeded
    hospitals carry the design's own richer prose ("Three-doctor LLC", the same register as the
    design's own fixture "Four-doctor LLC") directly in the `ownership` column, which has no
    database CHECK — so a seller who opened Edit on one of those and pressed Continue on step 1 was
    refused for a value they never typed. The fix: skip `_one_of` when the incoming value equals
    the row's OWN stored value — a no-op write — so nothing is loosened for new input and no design
    option is invented. `stored is None` never matches (a listing that has not set this column yet
    still requires a real value), so a bare create's null enum is refused exactly as before."""
    if stored is not None and raw == stored:
        return stored
    return _one_of(field, raw, allowed)


def _bldg_or_unchanged(raw: object, stored: str | None) -> str:
    """`_one_of_or_unchanged`'s twin for `bldg`: the wizard's own word and the column's are not
    spelled the same (`BLDG_IN`/`BLDG_OUT` — "Available separately" is stored as "Separate"), so
    "unchanged" is asked in the WIZARD's vocabulary: the column's stored word translated back
    through `BLDG_OUT` (the same expression `serialise_draft` reads it with), compared to what the
    seller actually sent. A changed value is still translated forward through `BLDG_IN`, exactly as
    before."""
    if stored is not None and BLDG_OUT.get(stored) == raw:
        return stored
    return BLDG_IN[_one_of("bldg", raw, tuple(BLDG_IN))]


def columns_for(step: int, body: dict[str, Any], row: dict[str, Any] | None = None) -> dict[str, Any]:
    """The step's fields as database columns, or a `Refusal`.

    The whitelist is one-directional and total: a field from another step is a 400 rather than a
    silent no-op, because the wizard sends one step at a time and a mis-sent field means the
    adapter and this table disagree — which is a bug to see, not to absorb.

    `row` is the listing being validated (A-SL31/A-SL32 (2)) — `None` for every caller that has no
    row to compare against (the two-way pins in `tests/api/test_seller_listings.py`, which build a
    payload with no listing in mind), so the four enum branches below fall back to full validation
    exactly as they always have."""
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
            out["type"] = _one_of_or_unchanged("type", raw, TYPES, row["type"] if row is not None else None)
        elif field == "ownership":
            out["ownership"] = _one_of_or_unchanged("ownership", raw, OWNERSHIPS, row["ownership"] if row is not None else None)
        elif field == "facilityType":
            out["facility_type"] = _one_of_or_unchanged(
                "facilityType", raw, FACILITY_TYPES, row["facility_type"] if row is not None else None)
        elif field == "bldg":
            out["bldg"] = _bldg_or_unchanged(raw, row["bldg"] if row is not None else None)
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
        # `photo["file"]` is null for a slot the curation left empty (A-L10, merged from `main`):
        # nothing was written there, so there is no path for a caption to be keyed by.
        return {f"{slug}/{photo['file']}": photo["caption"]
                for slug, photos in index["hospitals"].items() for photo in photos if photo["file"]}
    except (OSError, ValueError, KeyError):
        # Absent, malformed or restructured, the answer is the same fallback the docstring promises
        # (review L10). A draft read must not 500 because an inventory file changed shape.
        return {}


def photo_tiles(row: dict[str, Any], assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Step 6's tiles in `listing.photos`' own order, named by what the photograph SHOWS.

    Order comes from `listing.photos` and from nowhere else (D15 reason 3), which is why this is a
    projection of that array rather than a second sort of `assets`.

    The NAME is the seller's own caption (A-SL20: "have the user articulate what it is"). For an
    ASSET entry that is `listing_asset.caption`; for a SEED entry (SL7b, A-SL25 (10)) it is the
    listing's OWN `photo_captions[n]` FIRST — a seller's positional re-caption, `PATCH
    .../photos/{n}`, writes exactly that column, and it must be what the very next read shows — and
    only then the seed inventory's caption, and otherwise EMPTY. Never the filename D26 originally
    asked for (A-SL22 (2)): `DSC_0431.jpg` says nothing about what a buyer is looking at, and the
    design already has a truthful name for a photograph nobody has described, its own slot caption
    at that position, which the wizard fills in (amendment A16.4).

    An ASSET and a SEED entry are told apart by the VALUE ITSELF — an asset id is a bare uuid and a
    seed entry is always a `<slug>/<file>` path — `app/api/listings.py::get_listing_photo`'s own
    rule, not a second query. The DISCRIMINATOR (`source`, plus `position` for a seed entry) is on
    the TILE, not on `serialise_draft`'s own top-level keys (A-SL25 (4)'s pin is scoped there),
    so the frontend can route a click without parsing an id: `PATCH .../assets/{id}` for `"asset"`,
    the positional route by `position` for `"seed"`."""
    captions = {asset["id"]: asset["caption"] for asset in assets if asset["kind"] == "photo"}
    own = photo_list(row["photo_captions"])
    seeded = seed_captions()
    tiles: list[dict[str, Any]] = []
    # A null entry is a seed slot the curation left EMPTY (A-L10, merged from `main`): there is no
    # photograph there, so there is no tile for it — but its POSITION is still spent, so the
    # photograph after it keeps the position `photo_captions` itself indexes it by.
    for position, entry in enumerate(photo_list(row["photos"]), start=1):
        if entry is None:
            continue
        if "/" not in entry:
            tiles.append({"id": entry, "name": captions.get(entry) or "", "source": "asset"})
        else:
            stored = own[position - 1] if position - 1 < len(own) else None
            tiles.append({"id": entry, "name": stored or seeded.get(entry) or "",
                          "source": "seed", "position": position})
    return tiles


def serialise_draft(row: dict[str, Any], assets: list[dict[str, Any]]) -> dict[str, Any]:
    """The OWNER's own truth (D11) — every column unblanked, nulls preserved, plus `assets[]`.

    Deliberately not `serialise`: that one is the BUYER contract, it applies the disclosure
    blanking, and every published-listing pixel depends on it. Two serialisers is what keeps the
    zero-regression claim on the read surface a fact rather than a hope.

    The keys are the wizard's own (`state.w` in logic.js:204), not the columns': the adapter hands
    this straight to `setW`, so `services` comes back as `desc`, `facility_type` as `facilityType`
    and `bldg` in the design's own wording."""
    return {
        # `slug` is the owner's own row (D11 unblanks everything; the BUYER's `serialise` is what
        # hides it when the name is undisclosed). A-SL19 (9), Info-4: `/decide` answers this whole
        # payload, and the slug it writes at the first publish is what an admin tab links to.
        "id": str(row["id"]), "slug": row["slug"], "status": row["status"],
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
        # Info-3: the seller had no in-app way to read WHY a listing was declined — the reason
        # reached them by email and the Declined pill explained nothing. The latest decline's, and
        # null when there has never been one; SL7 renders it under that pill.
        "decline_reason": row["decline_reason"].removeprefix(DECLINE_PREFIX) if row["decline_reason"] else None,
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


def claim_from_seed(conn: Any, row: dict[str, Any], principal: S.Principal) -> None:
    """A-SL21: the first seller write of any kind makes a SEEDED listing the seller's own.

    D25 gave the eighteen demo hospitals a real `seller_id`, which is what puts them in the demo
    seller's wizard — and `scripts/seed_listings.py` rewrites every `source='seed'` row from
    `seeds/hospitals.json` on every import, deleting and re-inserting them under `--reset`. Without
    this, a re-seed would silently overwrite a seller's edits, put a listing the seller's edit had
    just taken to `in_review` back on the market with no review (`status` comes from the file), and
    cascade away the photographs and documents they had uploaded onto it
    (`listing_asset ... ON DELETE CASCADE`).

    So the row stops being the seeder's the moment the seller touches it, in the SAME transaction as
    the write: the seeder's own `WHERE source = 'seed'` scope then leaves it alone for ever, and an
    untouched sibling is still refreshable. Scoped by owner like every other write here (A-SL13 L1),
    and by `source = 'seed'` so a second write is a no-op rather than a second claim."""
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET source = 'seller'"
                    " WHERE id = %s AND seller_id = %s AND source = 'seed'",
                    (row["id"], principal.account_id))


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
        cur.execute("SELECT listing_id, id, kind, name, content_type, byte_size, caption FROM listing_asset"
                    " WHERE listing_id = ANY(%s) ORDER BY listing_id, created_at, id", (listing_ids,))
        for r in cur.fetchall():
            grouped[r[0]].append({"id": str(r[1]), "kind": r[2], "name": r[3],
                                  "content_type": r[4], "byte_size": r[5], "caption": r[6]})
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
        # A-SL19 (7): `422 BAD_FILTER`/`BAD_CURSOR`, the codes `/api/admin/listings` and
        # `/api/admin/users` answer for the same mistake — this route was the only one on the
        # listing surface refusing a bad list parameter differently from its neighbours.
        return _error("BAD_FILTER", "limit must be a number.", 422)
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
            return _error("BAD_CURSOR", "cursor must be a `<timestamp>|<id>` value from a previous"
                                        " page's next_cursor.", 422)
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
        with closing(sync_conn()) as conn, conn:
            # SL9 hardening (A-SL34 (2); SL5 re-review (a)): this was the one write route in the
            # module reading its precondition row through `owned_row` (no lock) instead of
            # `locked_row` (`FOR UPDATE`) — every other transition and asset write serialises this
            # read against a concurrent writer of the SAME row; this one did not, and a write could
            # slip in between the read and this route's own UPDATE (`test_a_concurrent_patch_
            # cannot_slip_between_the_precondition_read_and_the_write` demonstrates a withdrawn
            # listing resurrected by exactly that race).
            row = locked_row(conn, listing_id, principal)
            if row["status"] == "withdrawn":
                raise Refusal("STATE", "A withdrawn listing can no longer be edited.", 409)
            # A-SL31/A-SL32 (2): the row is the "did the seller actually change this" oracle, so it
            # has to be fetched before `columns_for` can compare against it.
            columns = columns_for(step, body, row)
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
            re_entering = row["status"] in EDIT_REENTERS_REVIEW
            # ...but only a PUBLISHED listing sits in a cached Browse payload, so the cache drop
            # stays keyed on that alone (A-SL13 L6's rule, unchanged by A-SL19 (1)).
            leaving_market = row["status"] == "published"
            assignments = ", ".join(f"{name} = %({name})s" for name in columns)
            sets = f"{assignments}, " if assignments else ""
            if re_entering:
                sets += "status = 'in_review', submitted_at = now(), "
            with conn.cursor() as cur:
                cur.execute(f"UPDATE listing SET {sets}updated_at = now()"
                            " WHERE id = %(id)s AND seller_id = %(seller)s",
                            {**columns, "id": row["id"], "seller": principal.account_id})
            claim_from_seed(conn, row, principal)
            if re_entering:
                audit.write(conn, actor=principal, action=EDIT_ACTION, target_type="listing",
                            target_id=row["id"], before={"status": row["status"]}, after={"status": "in_review"},
                            request=request)
            # Re-read through `locked_row` (SL9 hardening, matching `submit_listing`/`set_status`)
            # rather than a nullable `_row`: the row was just updated inside this transaction, so
            # its absence is not a state a request can reach, and a ternary for it would be an arm
            # no test could cover.
            payload = serialise_draft(locked_row(conn, listing_id, principal), assets_of(conn, row["id"]))
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
    """D3 for an ASSET write, in the write's own transaction (A-SL15 (1); A-SL19 (1)).

    John's ruling — "editing a published listing re-enters review and removes it from the market
    until approved again" — covers adding, reordering and deleting a photograph or a document: a
    photograph IS the listing to a buyer scrolling Browse, so a seller who swaps one on a live
    listing has changed what the market sees and the reviewer has to see it too. Same transition,
    same stamp and same audit row as `patch_step`'s own arm, which is why `EDIT_ACTION` is shared
    rather than a second name for one act.

    A PAUSED listing's assets are edits too (A-SL19 (1)): it is published-but-hidden and one click
    from the market, so swapping a photograph on one has to be reviewed exactly as swapping it on a
    live one is.

    Returns whether the listing WAS on the market, which is also the question "must the Browse
    cache be dropped?" (D16, review L6) — a paused listing's assets are in no published payload,
    and neither are a draft's."""
    was = str(row["status"])
    if was not in EDIT_REENTERS_REVIEW:
        return False
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status = 'in_review', submitted_at = now(), updated_at = now()"
                    " WHERE id = %s AND seller_id = %s", (row["id"], principal.account_id))
    audit.write(conn, actor=principal, action=EDIT_ACTION, target_type="listing", target_id=row["id"],
                before={"status": was}, after={"status": "in_review"}, request=request)
    return was == "published"


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
            # NO CAP (A-SL20, John 2026-09-09: "render ALL images"). D18's four-photograph limit
            # is withdrawn: the design's six slots are what it can CAPTION, not what a listing may
            # hold, and a hospital with nine photographs showed three. Every upload is stored and
            # every stored photograph is listed; the wizard names the ones past the design's slots
            # by the seller's own caption.
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
            claim_from_seed(conn, row, principal)
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
            # A-SL23 (6) m2. The list names PHOTOGRAPHS, and an EMPTY slot (A-L10, merged from
            # `main`) has no id to be named by — so the permutation is checked against the
            # non-null entries and the empty slots are spliced back at the positions they were
            # left at. Comparing against `entry or ""` instead refused the whole row (SL7 review,
            # Minor-2): thirty-five of the seeded slots were null, which said "this hospital's
            # photographs can never be reordered" rather than "an empty slot cannot be named".
            filled = [entry for entry in photos if entry is not None]
            if sorted(ids) != sorted(filled):
                raise Refusal("BAD_REQUEST",
                              "ids must be exactly this listing's photographs, in the new order.", 400)
            moved = iter(ids)
            reordered: list[str | None] = [None if entry is None else next(moved) for entry in photos]
            with conn.cursor() as cur:
                cur.execute("UPDATE listing SET photos = %s::jsonb, updated_at = now()"
                            " WHERE id = %s AND seller_id = %s",
                            (json.dumps(reordered), row["id"], principal.account_id))
            claim_from_seed(conn, row, principal)
            on_market = take_off_market(conn, row, principal, request)
            payload = serialise_draft(locked_row(conn, listing_id, principal), assets_of(conn, row["id"]))
    except Refusal as exc:
        return _refused(exc)
    if on_market:
        drop_list_cache(sync_redis())
    return JSONResponse(payload)


@router.patch("/listings/{listing_id}/assets/{asset_id}")
async def caption_asset(listing_id: str, asset_id: str, request: Request, principal: Owner) -> Response:
    """What this photograph SHOWS, in the seller's own words (A-SL20, A-SL22 (2)).

    John's ruling, verbatim: "have the user articulate what it is". The design captions its six
    photo slots by practice type and the caption is fixed, so until now a photograph could only sit
    under a true caption by happening to show that slot's subject — which is what the hotfix chain
    on `main` spent two rounds discovering. The seller says it instead, once per photograph.

    PHOTOGRAPHS ONLY. A document tile is named by the filename the seller chose, which is a true
    name for a document and no name at all for a picture; a document has no design slot for this
    sentence to stand in for, so `kind <> 'photo'` is a 404 rather than a silent write.

    Blank and null are one intent (A-SL18, Info), exactly as they are for every optional wizard
    field: the seller is taking the description back, and the tile returns to the design's own slot
    caption. An edit either way is an EDIT (A-SL15 (1)) — what a buyer reads under a photograph is
    part of the listing — so a published or paused row re-enters review in the same transaction."""
    hit(sync_redis(), "listing:patch", str(principal.account_id), *LISTING_PATCH)
    try:
        parsed = _asset_uuid(asset_id)
        body = await _json_body(request)
        caption = _text("caption", body.get("caption"))
        with closing(sync_conn()) as conn, conn:
            row = locked_row(conn, listing_id, principal)
            _writable(row)
            with conn.cursor() as cur:
                cur.execute("UPDATE listing_asset SET caption = %s WHERE id = %s AND listing_id = %s"
                            " AND kind = 'photo' RETURNING id", (caption, parsed, row["id"]))
                if cur.fetchone() is None:
                    raise Refusal("NOT_FOUND", "No such asset.", 404)
                cur.execute("UPDATE listing SET updated_at = now() WHERE id = %s AND seller_id = %s",
                            (row["id"], principal.account_id))
            claim_from_seed(conn, row, principal)
            on_market = take_off_market(conn, row, principal, request)
            payload = serialise_draft(locked_row(conn, listing_id, principal), assets_of(conn, row["id"]))
    except Refusal as exc:
        return _refused(exc)
    if on_market:
        drop_list_cache(sync_redis())
    return JSONResponse(payload)


@router.patch("/listings/{listing_id}/photos/{n}")
async def caption_seed_photo(listing_id: str, n: int, request: Request, principal: Owner) -> Response:
    """`caption_asset`'s twin for a SEED photograph (SL7b, A-SL25 (10)): "have the user articulate
    what it is", for the 195 seeded photographs a seller cannot reach by asset id because they are
    not asset rows at all — `listing.photos` holds a PATH for one, written by `scripts/
    seed_listings.py` from `seeds/hospitals/photos/index.json`, and `PATCH .../assets/{id}` has no
    uuid to match it against.

    POSITIONAL, 1-based — the buyer's own `GET .../photos/{n}` and `photo_file`'s convention — and
    writes `listing.photo_captions[n]`, PADDED to `len(photos)` with `""` when it is shorter
    (A-SL25 (7)'s one-caption-per-photograph contract): a caption at a position the column does not
    yet reach must not slide onto the photograph beside it once the column catches up.

    `n` out of range, or naming an EMPTY slot (A-L10's `null`), is `404 NOT_FOUND` — there is no
    photograph there to describe, the same fact `caption_asset` states for an asset id that names
    no row. An entry that is an ASSET, not a seed path, is `409 STATE`: the photograph is real, this
    is simply the wrong route for it — told apart by the value itself, never a second query
    (`app/api/listings.py::get_listing_photo`'s own rule: an asset id never contains a "/").

    Blank and null are one intent, exactly as `caption_asset` treats them: the seller is taking the
    description back, and the tile returns to the seed inventory's own caption (`photo_tiles`'s own
    fallback chain). An edit either way is an EDIT (A-SL15 (1)), claims the listing (A-SL21) and
    re-enters review a published or paused row, in the same transaction as `caption_asset`'s."""
    hit(sync_redis(), "listing:patch", str(principal.account_id), *LISTING_PATCH)
    try:
        body = await _json_body(request)
        caption = _text("caption", body.get("caption"))
        with closing(sync_conn()) as conn, conn:
            row = locked_row(conn, listing_id, principal)
            _writable(row)
            photos = photo_list(row["photos"])
            if not 1 <= n <= len(photos):
                raise Refusal("NOT_FOUND", "No such photograph.", 404)
            entry = photos[n - 1]
            if entry is None:
                raise Refusal("NOT_FOUND", "No such photograph.", 404)
            if "/" not in entry:
                raise Refusal("STATE", "That photograph is its own asset now; describe it through"
                              " its own caption.", 409)
            stored = photo_list(row["photo_captions"])
            padded = ([*stored, *[""] * (len(photos) - len(stored))])[:len(photos)]
            padded[n - 1] = caption or ""
            with conn.cursor() as cur:
                cur.execute("UPDATE listing SET photo_captions = %s::jsonb, updated_at = now()"
                            " WHERE id = %s AND seller_id = %s",
                            (json.dumps(padded), row["id"], principal.account_id))
            claim_from_seed(conn, row, principal)
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
            claim_from_seed(conn, row, principal)
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
            claim_from_seed(conn, row, principal)
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


# --- The seller's own transitions (D2, D4) -------------------------------------------------------
#
# Submit, and the dashboard's own three buttons. Every one writes an audit row (D4) under an action
# that names NO permission by design, exactly as `EDIT_ACTION` above does and for the same reason:
# `listing.manage_own` is not in `permissions.AUDITED`, so the drift test never sees these routes
# and there is no list to add them to. One namespace, so an auditor greps `listing.` once.
SUBMIT_ACTION, PAUSE_ACTION, REPUBLISH_ACTION, WITHDRAW_ACTION = (
    "listing.submit", "listing.pause", "listing.republish", "listing.withdraw")
SUBMITTABLE_FROM = ("draft", "declined", "in_review")
# The dashboard's own three (logic.js:958), each with the states the lifecycle table allows and the
# state it reaches.
TRANSITIONS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "pause": (("published",), "paused", PAUSE_ACTION),
    # No re-review: the design's admin footnote calls unpublishing "immediate and reversible"
    # (logic.js:1061), and a pause the seller can undo is not a new listing.
    "republish": (("paused",), "published", REPUBLISH_ACTION),
    # Terminal, from anywhere but itself: "withdrawn listings keep their history for reporting but
    # no longer appear in search" (logic.js:1061).
    "withdraw": (("draft", "in_review", "published", "paused", "declined"), "withdrawn", WITHDRAW_ACTION),
}
# The design's own client-side validation (logic.js:1215-1217), re-validated on the server because
# a client check is a courtesy and this one guards a CHECK constraint. `type` is here and not in
# the design's list for the reason A-SL13 M2 gives: `listing_submittable_ck` demands it, the
# per-step PATCH takes step 1's fields one at a time, and a CHECK met by a request is a 500.
REQUIRED_TO_SUBMIT = (("name", "A practice name"), ("est", "A year established"),
                      ("type", "A practice type"), ("city", "A city"), ("zip", "A ZIP code"),
                      ("price", "An asking price"))
INCOMPLETE_TAIL = "is needed before this listing can be submitted."


def _complete_enough(row: dict[str, Any]) -> None:
    """The design's own rules before it will show step 8, said server-side, plus a fourth this
    endpoint adds on top (A-SL33 (1), fix round 1 on the SL8 review's Critical finding).

    The compound rule is spelled out separately because it is about a PAIR: "an asking price and
    either an exact revenue figure or the range option" (logic.js:1217). `revBand` on means
    `rev_disclosed` false, so "the range option is chosen" reads here as the flag being off.

    `sqft` is checked LAST and is not one of the design's own three client-side rules — it is the
    fourth `listing_publishable_ck` (034) now names, because `frontend/src/logic.js` calls
    `p.sqft.toLocaleString()` with no guard at six sites Browse renders a practice from: a listing
    published with no floor area is not a blank field, it is a blank app the moment Browse next
    renders. Told here, in the envelope, rather than met as a database error when a reviewer later
    publishes it.
    """
    for column, label in REQUIRED_TO_SUBMIT:
        if row[column] is None:
            raise Refusal("INCOMPLETE", f"{label} {INCOMPLETE_TAIL}", 422)
    if row["rev"] is None and row["rev_disclosed"]:
        raise Refusal("INCOMPLETE", f"An exact revenue figure — or the range option — {INCOMPLETE_TAIL}", 422)
    if row["sqft"] is None:
        raise Refusal("INCOMPLETE", f"Approximate square feet {INCOMPLETE_TAIL}", 422)


def owner_email(conn: Any, principal: S.Principal) -> str:
    """The signed-in seller's own address. Read rather than carried on the principal: a session
    resolves to an account id, and the mail goes to whatever that account's address is NOW."""
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE id = %s", (principal.account_id,))
        # An authenticated principal's account exists by construction — `sessions._load` joins it.
        return cast("tuple[str]", cur.fetchone())[0]


@router.post("/listings/{listing_id}/submit")
async def submit_listing(listing_id: str, request: Request, principal: Owner) -> Response:
    """The wizard's *Submit for review* (logic.js:1236), persisted.

    Legal from `draft`, `declined` and `in_review` and from nothing else: a published or paused
    listing is already through review, and a withdrawn one is terminal. A second press within one
    review cycle does NOT re-stamp `submitted_at`, which is what makes the outbox key stable and
    the second email not exist — the seller "may keep editing while it waits" (the submitted card),
    so pressing Submit again is an ordinary thing to do rather than a mistake to refuse."""
    hit(sync_redis(), "listing:submit", str(principal.account_id), *LISTING_SUBMIT)
    try:
        with closing(sync_conn()) as conn, conn:
            row = locked_row(conn, listing_id, principal)
            before = row["status"]
            if before not in SUBMITTABLE_FROM:
                raise Refusal("STATE", f"cannot submit a listing in state {before}", 409)
            _complete_enough(row)
            with conn.cursor() as cur:
                # `AND submitted_at IS NOT NULL`: an in-review listing always carries a stamp
                # through this API (both roads into `in_review` write one), and the key below is
                # built from it — so a row that somehow has none starts its review cycle here
                # rather than reaching `.isoformat()` as a null.
                cur.execute("UPDATE listing SET status = 'in_review', updated_at = now(),"
                            " submitted_at = CASE WHEN %(keep)s AND submitted_at IS NOT NULL"
                            "                     THEN submitted_at ELSE now() END"
                            " WHERE id = %(id)s AND seller_id = %(seller)s RETURNING submitted_at",
                            {"keep": before == "in_review", "id": row["id"], "seller": principal.account_id})
                stamped = cast("tuple[datetime]", cur.fetchone())[0]
            enqueue(conn, to=owner_email(conn, principal), template="listing_submitted", params={},
                    idempotency_key=f"{row['id']}:listing_submitted:{stamped.isoformat()}")
            claim_from_seed(conn, row, principal)
            audit.write(conn, actor=principal, action=SUBMIT_ACTION, target_type="listing",
                        target_id=row["id"], before={"status": before}, after={"status": "in_review"},
                        request=request)
            payload = serialise_draft(locked_row(conn, listing_id, principal), assets_of(conn, row["id"]))
    except Refusal as exc:
        return _refused(exc)
    drop_list_cache(sync_redis())
    return JSONResponse(payload)


@router.post("/listings/{listing_id}/status")
async def set_status(listing_id: str, request: Request, principal: Owner) -> Response:
    """Pause, republish or withdraw — the dashboard's own three (logic.js:958).

    One route rather than three, because they are one decision table: the action names the states
    it is legal from and the state it reaches, and everything else about the three is identical.
    Rate-limited on its own bucket, so a seller who pauses a listing has not spent their
    submissions."""
    hit(sync_redis(), "listing:status", str(principal.account_id), *LISTING_SUBMIT)
    try:
        body = await _json_body(request)
        action = body.get("action")
        if not isinstance(action, str) or action not in TRANSITIONS:
            raise Refusal("BAD_REQUEST", f"action must be one of {', '.join(TRANSITIONS)}.", 400)
        allowed_from, after, recorded = TRANSITIONS[action]
        with closing(sync_conn()) as conn, conn:
            row = locked_row(conn, listing_id, principal)
            before = row["status"]
            if before not in allowed_from:
                raise Refusal("STATE", f"cannot {action} a listing in state {before}", 409)
            with conn.cursor() as cur:
                cur.execute("UPDATE listing SET status = %s, updated_at = now()"
                            " WHERE id = %s AND seller_id = %s", (after, row["id"], principal.account_id))
            claim_from_seed(conn, row, principal)
            audit.write(conn, actor=principal, action=recorded, target_type="listing", target_id=row["id"],
                        before={"status": before}, after={"status": after}, request=request)
            payload = serialise_draft(locked_row(conn, listing_id, principal), assets_of(conn, row["id"]))
    except Refusal as exc:
        return _refused(exc)
    # AFTER the commit (D16), and unconditionally — unlike `patch_step`, whose autosave arm is
    # conditional because it fires 240 times an hour (A-SL13 L6). A transition is a deliberate act
    # bounded by `LISTING_SUBMIT`, three of the four move a row onto or off the market, and a SCAN
    # that matches nothing costs one round trip.
    drop_list_cache(sync_redis())
    # Task B9: enqueue geocoding when republishing (republish moves from paused to published)
    if action == "republish":
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM practice_location WHERE listing_id = %s", (listing_id,))
            if cur.fetchone() is None:
                celery_app.send_task("census.geocode_listing", args=[listing_id])
    return JSONResponse(payload)
