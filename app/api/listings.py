"""The listing read surface (spec 2026-09-06, D8; controller amendment A-L5).

Three routes, all guarded by `listing.read`: the paginated published list, one listing, and one
photograph. An anonymous caller gets the identity design's generic 401 and the frontend shows
the sign-in gate.

Shapes that are load-bearing:

* **`require(...)` is hoisted to ONE module-level constant** and used through `Depends`. The
  route-guard and audit drift tests resolve a route's permission by the guard's object
  IDENTITY (`app.auth.deps.permission_of`), so a wrapper would read as unguarded.
* **Refusals this module raises use `_error(...)`, which writes decision A5's body directly.**
  Everything `require` raises is an `AuthError` and is rendered by the one handler
  `deps.install(app)` registered. This module never raises a bare `HTTPException`, whose body
  would be `{"detail": ...}`; and it parses `limit`/`cursor` by hand rather than through
  `Query(ge=…, le=…)`, so a bad value gets the same `{"error": {...}}` envelope as everything
  else instead of FastAPI's `{"detail": [...]}`.
* **Connections are opened with `closing(sync_conn()) as conn, conn`,** exactly as
  `app.api.auth` does: psycopg2's own `with conn:` is the TRANSACTION manager and commits
  WITHOUT closing, so `with sync_conn() as conn:` alone leaks a connection per request.
* **`listing.read` is not in `permissions.AUDITED`,** so no handler here writes an audit row;
  `tests/auth/test_permissions.py::test_audited_permissions_are_written_by_their_handlers`
  keeps that honest rather than assumed.

**Disclosure is enforced HERE, on the server (A-L5, 2026-09-08).** Name, location, financials and
documents are flags of one kind — "Sellers control what buyers can see" — and a hidden value must
never reach a buyer's browser, so `serialise` is the only place a row becomes a payload and it
blanks what the flags hide:

* `location_disclosed = false` -> `street`, `zip`, `phone`, `lat` and `lng` are null; `city`,
  `state`, `area` and `hours` remain, because the design's anonymised card shows the area and an
  opening time identifies nobody (D8; `phone` joined the list in A-L5.1, ruled 2026-09-08 — a
  telephone number identifies the practice as surely as its street does).
* `name_disclosed = false` -> `name` is the design's own anonymised label, `<area> Veterinary`
  (`practiceName`'s fallback in `frontend/src/logic.js`), and `slug` is null WITH it: every slug in
  this codebase is its listing's name in slug form (`seeds/hospitals.json`:
  `6666_dallas_veterinary_specialist_hospital` <- "6666 Dallas Veterinary Specialist Hospital"), so
  returning it would hand back the hidden name in another spelling. Same posture as the address
  above: the flag nulls what it hides. **Task L6 therefore keys off `id`, never `slug`** (A-L5.1).

**Since the per-buyer disclosure plan's Task 8 (2026-09-18) each flag above is a CEILING rather
than the whole answer, and RULING D-C66 (John, 2026-09-24) settled which way the two combine.**
`list_listings`/`get_listing` compute the calling buyer's capabilities (one bulk query for a whole
page, one single-listing query for the detail route -- directive §23,
`app.disclosure.access.authorized_capabilities`/`_bulk`) and `serialise` reads *flag OR capability*
per field: the flag is the seller's PUBLIC DEFAULT and the capability RELEASES on top of it.

It was *flag AND capability* between 2026-09-18 and that ruling, and the defect that produced is
the ruling's own subject: all four of the seller's step-7 switches SHUT a ceiling and three of them
promise release on approval in as many words ("Keep practice name and address hidden **until I
approve a buyer**"), so a seller who ticked one and then approved a buyer released nothing at all --
`False and anything`. The directive's own ceiling-AND-grant sentences (§3, §8, §11, §18) are
superseded IN PLACE in `docs/superpowers/specs/2026-09-18-per-buyer-disclosure-directive.md`, and
`app/api/seller_listings.py::read_document` is the ONE deliberate asymmetry: there the ceiling is
REMOVED rather than ORed, because ORing it would rebuild an incident this module has already had.

Every seed sets both flags true (D8, A-L5), so every seeded hospital publishes its real name and
address to every signed-in buyer, which is what that data has always meant and what QA showed
before the directive; Wave 2b's sellers default to false -- all four columns are `NOT NULL DEFAULT
false` -- so a real wizard listing still discloses nothing until its seller opens a ceiling or
approves a buyer.

**All three routes are mounted only in `site_mode == "app"`** (A-L5.1), beside the auth,
applications and admin routers: they are member endpoints, and
`scripts/verify-deploy.sh production` asserts "member endpoints absent" behind the Coming Soon
page — a claim that has to be true of these too. It probes all four surfaces, and probes this one
for a 401 on QA.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.auth import sessions as S
from app.auth.deps import require
from app.cache import LIST_CACHE_PREFIX, sync_redis
from app.census.serve import community_rows
from app.config import settings
from app.db import sync_conn
from app.disclosure.access import authorized_capabilities, authorized_capabilities_bulk, has_capability
from app.disclosure.levels import capability_for_document_kind
from app.privacy import record
from app.privacy.delivery import PHOTO_HEADERS, buyer_variant, photo_url
from app.storage import ObjectStore
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Hoisted to a module-level constant, never wrapped (Global Constraint (g)).
REQUIRE_LISTING_READ = require("listing.read")
# Per-buyer disclosure plan Task 7: the FIRST of this module's three routes to need the caller's
# own identity rather than a discarded `dependencies=[...]` guard -- `app/api/seller_listings.py`'s
# own `Reader`, re-declared here from the SAME `REQUIRE_LISTING_READ` guard object rather than a
# second `require("listing.read")`, because `deps.permission_of` resolves a route's permission by
# the guard's object IDENTITY (`tests/api/test_listings.py::test_the_listings_routes_are_guarded_not_public`).
Reader = Annotated[S.Principal, Depends(REQUIRE_LISTING_READ)]

ROOT = Path(__file__).resolve().parent.parent.parent
PHOTOS_ROOT = ROOT / "seeds" / "hospitals" / "photos"
LIST_TTL_S = 60
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_MARKET_LEN = 64
#: D-IDP-11, replacing `private, max-age=86400`. See `app/privacy/delivery.py::PHOTO_HEADERS`: a
#: flip changes the URL AND the ETag, so no browser can revalidate its way back to a variant the
#: policy has replaced. Kept as a name because `tests/api/test_listings.py` pins it.
PHOTO_CACHE_CONTROL = PHOTO_HEADERS["Cache-Control"]
# GEO-WIRE (1). `app/api/market.py`'s `BACKFILL_DEDUPE_TTL` (600 s) and its key shape, one task
# earlier in the same chain: geocode -> backfill -> materialise.
GEOCODE_DEDUPE_PREFIX = "geocode:"
GEOCODE_DEDUPE_TTL = 600

_SELECT = """
-- Per-buyer disclosure plan Task 8 (2026-09-18): `seller_id` is read here, ONCE per row, so the
-- capability lookup (`app.disclosure.access.authorized_capabilities`/`_bulk`, called by the two
-- routes below) never costs a second query to learn who a listing's own seller is -- and so the
-- self-authorization guard those functions apply has a real value to check rather than always
-- seeing None. `documents_disclosed` joins its three siblings for Task 9's own use -- the
-- `documents_disclosed`/FINANCIALS-or-FLOOR_PLANS-or-FULL_CONFIDENTIAL ceiling `_documents` below
-- applies to the very SELECT that put it here, so Task 9 costs no second query of its own either.
-- Neither `seller_id` nor `documents_disclosed` is added to `serialise`'s OUTPUT directly --
-- `seller_id` never has been and never should be (it is an internal account id, not part of the
-- buyer contract), and `documents_disclosed` is a ceiling `_documents` consumes, not a fact a
-- buyer is shown by name (the `documents` array it gates IS the buyer-facing fact).
SELECT id, seller_id, slug, name, street, city, state, zip, phone, hours, status, location_disclosed,
       name_disclosed, rev_disclosed, documents_disclosed, identifiable_content_visibility,
       ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng,
       area, type, market, price, rev, docs, rooms, sqft, bldg, facility_type, est, listed_at,
       note, staff, services, facility, ownership, photos, photo_captions,
       coalesce((SELECT jsonb_object_agg(a.id::text, a.caption) FROM listing_asset a
                  WHERE a.listing_id = listing.id AND a.kind = 'photo' AND a.caption IS NOT NULL),
                '{}'::jsonb) AS asset_captions,
       -- GEO-WIRE (4). A scalar subquery, in `asset_captions`'s own shape, so `FROM listing`
       -- stays a single table every caller can go on appending its own WHERE to. `null` for a
       -- listing that has never been geocoded, which is what absence means everywhere else in
       -- this payload (D-C31).
       (SELECT pl.geo_precision FROM practice_location pl WHERE pl.listing_id = listing.id) AS geo_precision,
       -- Spec 2026-09-09 C.7 row 3, the `visible_photos` aggregate: every privacy record this
       -- listing's photographs have, keyed by asset id, so `_photo_urls` can resolve a whole page
       -- in ONE statement rather than a lookup per photograph.
       --
       -- The JOIN to `listing_asset` is NOT optional: `buyer_variant`'s SHOW arm answers a
       -- `Variant` only when the DISPLAY key and hash are both present, and the privacy table
       -- holds neither — so an aggregate carrying status, visibility and the redacted hash alone
       -- would resolve to None for every SHOW photograph in the country.
       coalesce((SELECT jsonb_object_agg(p.asset_id::text, jsonb_build_object(
                          'status', p.processing_status,
                          'visible', p.buyer_visible,
                          'redacted_key', p.redacted_storage_key,
                          'redacted', p.redacted_sha256,
                          'display_key', a.storage_key,
                          'display', a.sha256))
                   FROM listing_asset_privacy p
                   JOIN listing_asset a ON a.id = p.asset_id
                  WHERE p.listing_id = listing.id),
                '{}'::jsonb) AS visible_photos
  FROM listing
"""

def _error(code: str, message: str, status: int) -> JSONResponse:
    """Decision A5's body for the refusals this module raises itself."""
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def has_geocode(conn: Any, listing_id: Any) -> bool:
    """Whether this listing already has the geography a geocode resolves (`practice_location`).

    Read INSIDE the caller's transaction, beside the status change it is deciding on; the enqueue
    itself happens after that transaction commits, which is the ordering `drop_list_cache` follows
    and for the same reason — a worker that started before the commit would read the pre-write row.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM practice_location WHERE listing_id = %s", (listing_id,))
        return cur.fetchone() is not None


def enqueue_geocode(cache: Any, listing_id: str) -> bool:
    """Enqueues `census.geocode_listing` for this listing unless it was already enqueued recently;
    True when this call is the one that sent it.

    **By NAME, never by import** (spec §10, and `app/tasks/census.py:326-348`'s own posture): the
    request path must not reach a Census write, and `send_task` is how one is asked for without
    importing the module that performs it.

    **Deduped on the listing id** in `app/api/market.py`'s own shape (`BACKFILL_DEDUPE_TTL`, the
    `nx=True` claim), because `has_geocode` alone cannot do it: the row it looks for is written by
    the WORKER, so every publish inside the window between the enqueue and that write saw no row
    and enqueued again. `clear_geocode_dedupe` is the one thing that re-opens the window early,
    and an address edit is the one event that calls it.
    """
    if not cache.set(f"{GEOCODE_DEDUPE_PREFIX}{listing_id}", "1", ex=GEOCODE_DEDUPE_TTL, nx=True):
        return False
    celery_app.send_task("census.geocode_listing", args=[listing_id])
    return True


def clear_geocode_dedupe(cache: Any, listing_id: str) -> None:
    """Forgets that this listing was recently enqueued, so the next publish geocodes it again.

    Called when the listing's address CHANGES — the one event that makes a pending or completed
    geocode describe somewhere the practice is not, and the one that arrives precisely inside the
    dedupe window, because a correction follows the publish that revealed the mistake."""
    cache.delete(f"{GEOCODE_DEDUPE_PREFIX}{listing_id}")


def anonymised_name(area: str) -> str:
    """The design's own label for a listing whose name is not disclosed (A-L5).

    `practiceName(p)` in `frontend/src/logic.js` ends `|| p.area + " Veterinary"`; this is that
    fallback, computed on the server so the browser is never handed the real name to fall back
    FROM. The frontend keeps its own expression unchanged (A12) — it simply finds `p.name` already
    filled in."""
    return f"{area} Veterinary"


def relative_listed(listed_at: datetime, now: datetime) -> str:
    """The design's own vocabulary for a card's "listed" line, rendered on the SERVER so the
    pixel gates never drift with the wall clock (the frontend copies the string through)."""
    days = (now - listed_at).days
    if days < 1:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 7:
        return f"{days} days ago"
    if days < 28:
        weeks = days // 7
        return "1 week ago" if weeks == 1 else f"{weeks} weeks ago"
    months = max(1, days // 30)
    return "1 month ago" if months == 1 else f"{months} months ago"


def encode_cursor(listed_at: datetime, listing_id: UUID) -> str:
    raw = f"{listed_at.isoformat()}|{listing_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(raw: str) -> tuple[datetime, UUID]:
    """The (listed_at, id) keyset a cursor names. Raises ValueError for anything else."""
    padded = raw + "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("bad cursor") from exc
    at, _, listing_id = decoded.partition("|")
    return datetime.fromisoformat(at), UUID(listing_id)


def photo_list(value: object) -> list[str | None]:
    """`listing.photos` — or its parallel `listing.photo_captions` (A-L11) — as a list of strings,
    `None` where the slot is empty (A-L10) or the photograph has no description of its own.

    The list is POSITIONAL: position `n` of both columns is one photograph, and the first six are
    the design's photo slots. The seeder stores a `null` for a slot the hospital's folder was too
    thin to fill. The null is carried, never dropped — compacting either list would slide every
    later photograph up one slot and put it under a caption describing something else, and would
    slide the two lists out of step with each other.

    One helper for both columns because they are the same shape and the same rule; the caller
    names which one it is reading.

    psycopg2 decodes a `jsonb` column to a Python list, so the string arm is unreachable from a
    request — but `serialise` is also called directly (by tests, and by Wave 2b's admin views,
    which read rows through other drivers), and 100 % branches is the gate. One helper with two
    tested arms, rather than the same defensive ternary written twice (pre-flight C2)."""
    if isinstance(value, str):
        loaded = json.loads(value)
        return [None if item is None else str(item) for item in loaded]
    if isinstance(value, list):
        return [None if item is None else str(item) for item in value]
    return []   # a NULL `photos` (nothing writes one: the column is NOT NULL DEFAULT '[]')


def photo_captions(photos: list[str | None], stored: list[str | None], owned: Mapping[str, str]) -> list[str]:
    """EXACTLY ONE description per photograph — always a string — whichever of its TWO homes it was
    written in.

    A SEED photograph's description is `listing.photo_captions[n]`, written by the seeder from the
    supplier's own filename (A-L11), and positional — position `n` describes position `n`. A
    SELLER's is `listing_asset.caption`, written by the seller in the wizard's photo step (A-SL20,
    John: "have the user articulate what it is"); there `listing.photos[n]` is that asset's UUID
    rather than a path, so the caption is looked up BY THE UUID and the column has nothing in it.
    `photo_captions` is one contract over both (A-SL23 (0)) — A-SL22 (2)'s "served as
    `photo_captions` for published listings", which SL7 could not deliver before A-L11 landed.

    The seller's own words win where both homes have something to say: a seeded listing the seller
    has since edited is theirs (A-SL21), and they have looked at the photograph.

    The answer is `len(photos)` long on BOTH paths — padded where the column is short, truncated
    where it is long (A-SL25 (7), on the SL7 re-review's Minor-D). The two lists are read BY INDEX
    (`photoSet`'s `p.photoCaptions[i]`), so a ragged pair is a caption sliding onto a photograph it
    does not describe; returning the column untouched wherever no asset had spoken made that
    guarantee conditional on a seller having captioned something, which is not a rule anyone could
    rely on.

    ONE rule for "nobody has described this one", and it is `""` (A-SL26 (2), the round-2
    re-review's Minor-E): a position past the end of the column, a JSON `null` inside it, and an
    asset with no caption are the same fact and now read the same. `photoSet` renders the design's
    own fixed slot caption in place of any of them — `p.photoCaptions[i] || <slot caption>`, both
    falsey — so nothing downstream could tell them apart; what differed was this function's promise
    against its behaviour, and SL7b's positional caption route writes this very column."""
    padded: list[str | None] = [*stored, *[""] * (len(photos) - len(stored))]
    if not owned:
        return [entry or "" for entry in padded[:len(photos)]]
    return [(owned.get(entry) if entry is not None else None) or padded[n] or "" for n, entry in enumerate(photos)]


def photo_file(photos: list[str | None], n: int) -> Path | None:
    """The file behind photo `n` (1-based) of `photos`, or None. The path comes from the
    database, so it is resolved under PHOTOS_ROOT and anything that escapes is refused —
    a `photos` value of `["../../../etc/passwd"]` must be a 404, not a file read.

    An EMPTY slot (A-L10) is None here for the same reason an out-of-range `n` is: there is no
    photograph to serve, so the route answers 404 and the design renders its placeholder."""
    if not 1 <= n <= len(photos):
        return None
    relative = photos[n - 1]
    if relative is None:
        return None
    root = PHOTOS_ROOT.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


@lru_cache(maxsize=1)
def seed_digests() -> dict[str, str]:
    """`<slug>/<file>` -> the SHA-256 `scripts/prepare_photos.py` recorded, read once per process.

    The sibling of `seed_captions()` (which lives in `app/api/seller_listings.py`); it is HERE
    because `serialise` is here and `seller_listings` imports from this module, never the reverse.
    An absent or malformed inventory falls back to an empty map, and a seed URL then carries no
    `?v=` -- a missing cache key, never a missing photograph."""
    try:
        index = json.loads((PHOTOS_ROOT / "index.json").read_text())
        return {f"{slug}/{photo['file']}": photo["sha256"]
                for slug, photos in index["hospitals"].items() for photo in photos if photo["file"]}
    except (OSError, ValueError, KeyError):
        return {}


def photo_response(body: bytes, sha256: str, request: Request) -> Response:
    """The bytes, or a 304. The ETag is the CONTENT hash, so a flip changes it and no browser can
    revalidate its way back to the variant it had (directive 14, "cached browser response")."""
    etag = f'"{sha256}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={**PHOTO_HEADERS, "ETag": etag})
    return Response(content=body, media_type="image/webp", headers={**PHOTO_HEADERS, "ETag": etag})


def _photo_urls(listing_id: str, photos: list[str | None], row: Mapping[str, Any], *,
                authorized: bool) -> list[str | None]:
    """One URL per slot, or None where the resolver refuses it (spec C.7 rows 3-4).

    Every decision here belongs to `buyer_variant`; this function's whole job is to hand it the
    listing's visibility and the photograph's own record and to turn its answer into a positional
    URL. The record comes from `_SELECT`'s `visible_photos` aggregate -- one query for the whole
    page, never a lookup per photograph -- and a seed PATH entry has no record at all, which is why
    the entry and the inventory digest are passed too.

    `authorized` (per-buyer disclosure plan Task 7) is ONE bool for the WHOLE listing, threaded
    straight through to every photograph's `buyer_variant` call: UNREDACTED_IMAGES is a listing-
    level capability, not a per-photograph one, so the caller computes it once (Task 8's `serialise`
    call, via `has_capability`/`authorized_capabilities_bulk`) and this function never asks the
    database anything of its own."""
    visibility = str(row["identifiable_content_visibility"])
    aggregate = row["visible_photos"]
    digests = seed_digests()
    out: list[str | None] = []
    for n, entry in enumerate(photos, start=1):
        if entry is None:
            out.append(None)
            continue
        found = aggregate.get(entry)
        asset = None if found is None else record.delivery_row(entry, row["id"], found)
        variant = buyer_variant(visibility, asset, entry, digests.get(entry), authorized=authorized)
        out.append(None if variant is None else photo_url(listing_id, n, variant.sha256))
    return out


def _documents(conn: Any, listing_id: str, *, capabilities: frozenset[str]) -> list[dict[str, Any]]:
    """Every non-photo asset THIS CALLER could actually fetch through `read_document`
    (`app/api/seller_listings.py`) -- directive §10's own "the JSON list must not advertise what
    the bytes route will refuse."  The route's own `allowed` boolean is
    `owner or staff or (published and has_capability(...))`; this list has
    no notion of owner/staff at all (the buyer-facing `get_listing` route this feeds is not how a
    seller or a reviewer reads their own listing -- they have `GET /api/seller/listings/{id}` and
    `GET /api/admin/listings/{id}` for that), so it is exactly the buyer arm of that same boolean,
    applied per document.

    Existence IS public, which is the product's own promise: step 7's approved copy reads "Buyers
    see the document titles and can ask for access." Titles are how a buyer knows what to request;
    withholding them would leave the request flow this whole subsystem exists to serve with nothing
    to point at.

    **RULING D-C66 (John, 2026-09-24) TOOK THE CEILING OFF THIS LIST.** Until then a
    `documents_disclosed = false` listing returned `[]` before the query ran -- so the seller who
    ticked "Keep floor plans and financial packet locked" hid the very titles that same toggle's
    help promises, and the buyer had nothing to ask about on precisely the listings where asking is
    the whole point. Titles are served whichever way the toggle is set now, and what the toggle's
    OFF position used to buy -- bytes with no grant behind them -- is gone from the bytes route in
    the same ruling (`app/api/seller_listings.py::read_document`), so no state is left in which
    this list advertises what that route will refuse for a reason this list cannot see.

    **THE COST, stated rather than hidden:** a locked listing used to run no query at all here and
    now runs one. That is one indexed lookup (`listing_asset_kind_idx`) on the DETAIL route only --
    the list route has no document UI and never calls this.

    Called once per single-listing read -- never from the list route, which has no document UI."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, kind, content_type FROM listing_asset"
                    " WHERE listing_id = %s AND kind <> 'photo' ORDER BY created_at", (listing_id,))
        rows = cur.fetchall()
    # NOT filtered by `capabilities` (controller ruling, 2026-09-19, correcting this task's own
    # brief). Step 7's approved copy — which directive §17 declares CORRECT and preserves — reads
    # "Buyers see the document titles and can ask for access." A buyer cannot ask for access to a
    # document they cannot see exists, so filtering the TITLES makes that promise false and leaves
    # the request flow with nothing to request. The ceiling (`documents_disclosed`) decides whether
    # the LIST appears at all; the per-buyer grant decides whether `read_document` serves the BYTES.
    # Directive §10's "do not expose the original merely because the buyer knows its URL" is about
    # CONTENT, and that refusal lives in the bytes route, which Task 9 also built and tests.
    # The TITLE is generic until this buyer holds the capability that opens the document (security
    # review, 2026-09-19). `listing_asset.name` is the seller's own upload filename, kept verbatim
    # by `app/api/seller_listings.py` bar path separators and length — so a packet saved as
    # "Smith_Family_Veterinary_2023_Financials.pdf" or "123_Main_St_Floor_Plan.pdf" would publish the
    # practice's identity or address to EVERY buyer with no grant at all, straight past
    # `name_disclosed`/`location_disclosed`, which are independent booleans a seller can leave shut
    # (migrations/016_listing.sql:25). That is the exact exposure this subsystem exists to prevent,
    # arriving through a string the platform re-publishes rather than through a field it gates.
    #
    # The row is still LISTED — the 2026-09-19 ruling stands, a buyer must see a document exists to
    # request it, and step 7's approved copy promises exactly that — so only the label changes.
    return [{"id": str(r[0]), "kind": r[2], "content_type": r[3],
             "name": r[1] if capability_for_document_kind(r[2]) in capabilities else _DOCUMENT_LABEL.get(r[2], "Document")}
            for r in rows]


#: What an ungranted buyer sees in place of the seller's own filename. Derived from the document's
#: KIND, which is platform vocabulary rather than seller-supplied text, so it can carry no identity.
_DOCUMENT_LABEL = {"financials": "Financial packet", "floor_plan": "Floor plan"}


def _point(value: Any, *, released: bool) -> float | None:
    """One coordinate, to a caller the listing's location has been released to, and to nobody else.

    Not released -> None: either the seller shut the `anon` ceiling and has approved nobody, or this
    caller is a buyer they have not approved. A25's "no point, no pin" stands beside it as its own,
    different guard -- `value is None`, a listing that has never been geocoded at all.

    **TASK 8 OF THE SELLER-WIZARD REPAIR (ruling D-C66, 2026-09-24) COLLAPSED THREE TIERS TO TWO,
    and the deleted one is recorded here rather than left as a gap a later reader has to reconstruct.**
    Between 2026-09-19 and this ruling there was a middle tier: a listing whose `location_disclosed`
    ceiling was OPEN served every buyer a point rounded to 2 decimal places (about 1.1 km) --
    directive §11's "approximate map representation" -- while the exact pair waited on an
    EXACT_LOCATION grant. That tier existed only because the ceiling was ANDed with the grant, which
    made "a public listing whose street is hidden from everyone" a reachable state. Under D-C66 it is
    not: an open ceiling publishes the street, the postcode and the telephone number to every
    signed-in buyer, so a coarsened pin beside a payload naming 123 Main St would be the SAME
    question answered two ways, up to 1.1 km apart -- and a shut ceiling now serves those three to a
    granted buyer, who must get the pin that goes with them. There is no remaining state in which
    "approximate" is the honest answer, so the rounding is gone rather than left unreachable.
    `tests/api/test_geo_wire.py` carried that tier's own pin and records the same supersession."""
    if not released or value is None:
        return None
    return float(value)


def serialise(row: Mapping[str, Any], now: datetime, community: Mapping[str, Any] | None = None,
             *, capabilities: frozenset[str] = frozenset(),
             documents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One database row as the JSON contract Task L6 maps, with both disclosure flags applied —
    see the module docstring: an undisclosed address loses its street, postcode, telephone number
    and point, an undisclosed name loses the name and the slug that spells it.

    **The two flags are INDEPENDENT by design (A-L5.2, ruled 2026-09-08).** A listing may hide its
    name and still show its address, point and telephone number — a buyer could then find the name
    in a search, and that is the seller's own choice under "Sellers control what buyers can see",
    not a leak to close here. Wave 2b's UI says so beside the two switches. Do not "fix" this by
    making one flag imply the other.

    **Per-buyer disclosure plan Task 8 (2026-09-18): `capabilities` is a SECOND, independent gate,
    ANDed against each flag rather than replacing it (directive §8, §24).** The default is the
    EMPTY set -- fail closed (directive §19): a caller that passes no `capabilities` argument at
    all gets the SAME redacted shape an unapproved buyer does, never the pre-Task-8 "ceiling alone
    decides" behaviour, so a future caller that forgets to compute one cannot accidentally leak a
    confidential field by omission.

    **Community data is optional (Task B7).** When provided (a CommunityRow from serve.community_rows),
    the six fields are populated; absence means they remain null.

    **Per-buyer disclosure plan Task 9 (2026-09-18): `documents` is the buyer-facing document list**
    (closing finding 9, the wizard-step audit's own name for this list being 100% fixture data
    before this task) -- ALREADY filtered to what `read_document` would actually serve this caller
    (`_documents`'s own docstring), so this parameter is never re-filtered here; `documents or []`
    is only the "an absent list is not the same key error as a real empty one" guard `capabilities`'
    own default already follows one field over."""
    # **RULING D-C66 (John, 2026-09-24): ceiling OR grant, where every line of this block used to
    # read ceiling AND grant.** The seller's flag is the PUBLIC DEFAULT and the buyer's grant
    # RELEASES on top of it — so a seller who shuts a ceiling publishes to nobody until they approve
    # someone (which is exactly what step 7's labels promise: "Keep practice name and address hidden
    # UNTIL I APPROVE A BUYER"), and a seller who leaves one open publishes to every signed-in
    # buyer, as this product did before the 2026-09-18 directive ANDed a grant in front of it.
    # Under AND, approving a buyer on a shut ceiling released NOTHING — `False and anything` — which
    # is the defect the ruling names. The directive's own ceiling-AND-grant sentences (§3, §8, §11,
    # §18) are superseded IN PLACE in
    # `docs/superpowers/specs/2026-09-18-per-buyer-disclosure-directive.md`.
    #
    #   `disclosed` the street, the postcode, the telephone number AND the point — one answer, never
    #               three quarters of one: `_point` used to take the ceiling as a SEPARATE argument
    #               and would have gone on returning None for the very buyer the seller had just
    #               approved (that entry's own docstring records the tier this collapsed).
    #   `named`     the practice name and the slug that spells it (A-L5.1).
    #
    # FAIL CLOSED IS NOW CARRIED ENTIRELY BY `capabilities` (directive §19), and that is the cost of
    # this shape rather than a boast: under AND a wrongly-granted capability still met a shut
    # ceiling, and under OR nothing stands behind it. Every producer of that set answers
    # `frozenset()` for an absent buyer, a missing row and an unknown level
    # (`app/disclosure/access.py`, `app/disclosure/levels.py::covers`), this parameter's own default
    # is the empty set, and `tests/api/test_listings_disclosure.py` re-proves the no-grant answer
    # field by field rather than inheriting it.
    disclosed = bool(row["location_disclosed"]) or "EXACT_LOCATION" in capabilities
    named = bool(row["name_disclosed"]) or "IDENTITY" in capabilities
    listing_id = str(row["id"])
    photos = photo_list(row["photos"])
    # Spec C.7 rows 3-4, computed ONCE and read twice below: the two arrays are parallel, and a
    # caption must not describe a slot the resolver refused.
    #
    # Per-buyer disclosure plan Task 8: `UNREDACTED_IMAGES` is a listing-level capability like the
    # other three, so it is read from the SAME `capabilities` set the caller already computed,
    # rather than asked for separately -- this replaces Task 7's own `authorized=False` placeholder
    # (its comment said so: "Task 8 is what computes the caller's actual UNREDACTED_IMAGES
    # capability ... and threads it in here").
    urls = _photo_urls(listing_id, photos, row, authorized="UNREDACTED_IMAGES" in capabilities)
    captions = photo_captions(photos, photo_list(row["photo_captions"]), row["asset_captions"])

    # Community context data (Task B7: six fields plus two Browse fields, Task B10: label for
    # fallback, D-C38: the two per-figure geography fields beside it)
    pop = None
    growth = None
    income = None
    hh = None
    vets = None
    econ_k = None
    community_label = None
    growth_scope = None
    income_note = None
    income_vs_us_pct = None
    income_approximate = None
    pet_rate = None
    if community is not None:
        pop = community.get("pop")
        growth = community.get("growth")
        income = community.get("income")
        hh = community.get("hh")
        vets = community.get("vets")
        econ_k = community.get("econ_k")
        community_label = community.get("label")
        growth_scope = community.get("growth_scope")
        income_note = community.get("income_note")
        income_vs_us_pct = community.get("income_vs_us_pct")
        income_approximate = community.get("income_approximate")
        pet_rate = community.get("pet_rate")

    return {
        "id": listing_id,
        "slug": row["slug"] if named else None,
        "name": row["name"] if named else anonymised_name(str(row["area"])),
        "name_disclosed": named,
        "market": row["market"], "area": row["area"], "type": row["type"],
        "city": row["city"], "state": row["state"],
        "street": row["street"] if disclosed else None,
        "zip": row["zip"] if disclosed else None,
        "phone": row["phone"] if disclosed else None,
        "hours": row["hours"],
        "price": row["price"], "rev": row["rev"] if row.get("rev_disclosed") or "FINANCIALS" in capabilities else None,
        "docs": row["docs"], "rooms": row["rooms"],
        "sqft": row["sqft"], "bldg": row["bldg"], "est": row["est"],
        # S6 (the seller-wizard audit, 2026-09-23; ruling D-C65). Step 5 asks "Facility type"
        # (Standalone / Strip or plaza / Medical park / Other) and `app/api/seller_listings.py`
        # validates and stores the answer -- and `_SELECT` did not name the column, so the buyer's
        # own "Facility type" row was computed from `bldg` instead, which answers the BUILDING
        # STATUS question (Included / Available separately / Leased). Amendment A58.3 pointed that
        # row at the listing's own `facilityType`; this is what fills it.
        #
        # SERVED UNDER THE DESIGN'S OWN NAME, camel-cased where every column beside it is not:
        # the seller's draft route already answers `facilityType` for the identical column
        # (`app/api/seller_listings.py`'s `toWizardState`), so one spelling reaches the client from
        # both routes and `load.ts` copies the key rather than renaming it a second way.
        #
        # UNGATED, deliberately: a building shape is not an identity fact. No disclosure flag and
        # no capability names it, so it follows `bldg` directly above and `type`, never `street`
        # and `phone`. `null` -- never a substituted default -- for a listing whose seller has not
        # answered, because the design draws no row at all for an absent value (A58.3, "absent
        # beats faked") and a default would republish every such listing as a standalone building
        # nobody ever said it was.
        "facilityType": row["facility_type"],
        "listed": relative_listed(row["listed_at"], now),
        "listed_at": row["listed_at"].isoformat(),
        "status": row["status"],
        # Task B7: Community Context figures from the market_metric table
        "pop": pop, "growth": growth, "income": income, "hh": hh,
        # Task B7: Two additional fields for Browse use
        "vets": vets, "econ_k": econ_k,
        # Task B10: Label indicating which data band was used for fallback
        "community_label": community_label,
        # D-C38: where the two figures the label does NOT describe come from. `growth_scope` names
        # growth's own place-or-county geography with the name TIGER itself gives ("Dallas",
        # "Orange County" — no composed "City of " prefix: level 160 covers designated places
        # too, and a CDP is not a city), because that
        # figure exists at no finer geography until the 2010->2020 tract crosswalk is loaded;
        # `income_note` replaces the median tile's sub-line when that median is an approximation
        # rather than a published Census figure. Both `null` when there is nothing to say.
        "growth_scope": growth_scope,
        "income_note": income_note,
        # A33.1 (Task SCREEN-LABELS, 2026-09-13): the two fields the docked panel's Median Income
        # tile composes its ONE sub-line from. `income_vs_us_pct` is the pipeline's own
        # `income_index_vs_us`, from the same band the median came from and against the same ACS
        # release — the panel used to compute its own against a constant in the design's script.
        # `income_approximate` is the FACT `income_note` states in prose, served beside it so the
        # panel is not reading the end of the detail card's sentence.
        "income_vs_us_pct": income_vs_us_pct,
        "income_approximate": income_approximate,
        # Task PET-RATE-PROVENANCE (John, 2026-09-15): the pet-ownership incidence rate this
        # listing's own estimated-pet-household row was computed with. Not a figure — the one
        # input the design needs so it can stop keeping a second, unexplained copy of the
        # constant. `null` where the listing has no pet row, and the design then shows no such
        # figure at all rather than inventing one from a rate nobody recorded.
        "pet_rate": pet_rate,
        # GEO-WIRE (4): how precisely this listing's point is known — 'rooftop', 'tract', 'zcta',
        # 'place', 'county' (`migrations/061`'s own CHECK), or `null` where it has never been
        # geocoded. The contract's copy rule keys on exactly this ("`geo_precision != \"rooftop\"`
        # → render 'approximate community data' near the map pin"), and both market endpoints have
        # served it since Task B5; the card and the pin are built from THIS payload, so until now
        # the one rule the contract states about precision could not be honoured where it applies.
        # NOT gated on `location_disclosed`: it says how well the point is known, never where it
        # is, and the two flags above it blank every field that would say where.
        "geo_precision": row["geo_precision"],
        "note": row["note"], "staff": row["staff"], "services": row["services"],
        "facility": row["facility"], "ownership": row["ownership"],
        "lat": _point(row["lat"], released=disclosed),
        "lng": _point(row["lng"], released=disclosed),
        "location_disclosed": disclosed,
        # Positional (A-L10): position `n` is the design's photo slot `n`, and an empty slot is a
        # JSON `null` rather than a URL that would 404 — `photoSet`'s `p.photos[i]` then falls to
        # the design's own placeholder for that slot instead of a broken image.
        #
        # Directive 9: under NOT_SHOW the buyer must not receive the original by "an API response"
        # either. A slot the resolver refuses is that same JSON null — never a URL that would 404
        # and, much worse, never one that would resolve to something else.
        "photos": urls,
        # A-L11: one description per photograph, PARALLEL to `photos` — position `n` describes
        # position `n`. The design's `photoSet` reads it as `p.photoCaptions[i]` and falls back to
        # its own fixed slot caption where the entry is null (amendment A15), which is what lets a
        # photograph past the sixth be rendered at all: the design has no seventh caption.
        #
        # A caption whose slot resolved to None becomes "", so no description of a hidden
        # photograph is delivered beside a null (spec F, "API response leakage").
        "photo_captions": [caption if url is not None else ""
                           for url, caption in zip(urls, captions, strict=True)],
        # Per-buyer disclosure plan Task 9: every non-photo asset this SAME caller could fetch
        # through `read_document` right now -- `_documents`'s own filter, already applied by the
        # caller (`get_listing`) before this dict is built. `[]`, never `None`, for a caller that
        # supplied nothing (`list_listings`, which renders no document UI at all).
        "documents": documents or [],
    }


def _rows(conn: Any, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Rows as dicts keyed by the names the QUERY produced — `cur.description`, not a tuple kept
    beside `_SELECT` by hand (review round 2, M5). A hand-kept tuple is checked for LENGTH by
    `strict=True` and for nothing else, so swapping two columns in one of the two lists mis-mapped
    every row in silence. `lat`/`lng` come through because `_SELECT` aliases them."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def _parse_limit(raw: str | None) -> int | None:
    if raw is None:
        return DEFAULT_LIMIT
    if not raw.isdecimal():
        return None
    value = int(raw)
    return value if 1 <= value <= MAX_LIMIT else None


@router.get("/listings")
async def list_listings(request: Request, principal: Reader) -> Response:
    limit = _parse_limit(request.query_params.get("limit"))
    if limit is None:
        return _error("BAD_REQUEST", "Invalid limit.", 400)
    # `or None`, so an EMPTY `?market=` means "no filter" to the SQL below AND to the cache key
    # (review round 2, I1). They disagreed: the key was `listings:v1:::50` for both spellings while
    # the query filtered on `market = ''`, which matches no row — so whichever spelling arrived
    # first decided, for sixty seconds and for every member, whether Browse showed everything or
    # nothing.
    market = request.query_params.get("market") or None
    if market is not None and len(market) > MAX_MARKET_LEN:
        return _error("BAD_REQUEST", "Invalid market.", 400)
    raw_cursor = request.query_params.get("cursor")
    keyset: tuple[datetime, UUID] | None = None
    if raw_cursor is not None:
        try:
            keyset = decode_cursor(raw_cursor)
        except ValueError:
            return _error("BAD_REQUEST", "Invalid cursor.", 400)

    # One key per (market, limit, buyer) — after I1 above, the two market/limit inputs that change
    # a FIRST page, PLUS the buyer's own account id since the per-buyer disclosure plan's Task 8
    # (2026-09-18). This line used to read "the list is published-only and carries no per-account
    # field, so every member sees the same bytes and the cache is safe to share across principals;
    # if a later task adds a per-account field to this payload, this key must gain the account id
    # or the cache must go" -- Task 8 is that later task: `serialise` now applies THIS caller's own
    # capabilities to name/location/revenue/photos, so two buyers can receive two different bodies
    # for the identical (market, limit). Without the account id here, a buyer holding an APPROVED
    # grant would write their own disclosed value into a cache entry every OTHER buyer reads for up
    # to `LIST_TTL_S` — "leave a field unguarded and it leaks to every buyer" at the cache layer
    # rather than at the capability check itself. `drop_list_cache`/`drop_list_cache_quietly`
    # (`app/cache.py`) need no change: both invalidate by a WILDCARD scan over the whole
    # `listings:v1:*` prefix, which still matches every one of these longer keys.
    #
    # Only the first page is cached (review round 2, M2). `decode_cursor` accepts any ISO timestamp
    # paired with any UUID and nothing rate-limits this route, so a cacheable cursor page let one
    # member mint an unbounded number of distinct entries — up to two hundred listings each, sixty
    # seconds each — and evict everything else from a small Railway Redis. Page one is the page
    # Browse loads and the only one whose key a caller cannot vary at will; later pages go straight
    # to the database, which is what the keyset index is for. The empty third segment keeps the
    # `listings:v1:<market>:<cursor>:<limit>` shape, so a later task that signs cursors can make
    # them cacheable again without a v2.
    #
    # It IS invalidated now (spec 2026-09-08 D16): every writer in `app/api/seller_listings.py` and
    # `app/api/admin_listings.py` calls `drop_list_cache` after its transaction commits, which is
    # what review round 2's M4 asked for — a disclosure flag turned OFF must stop reaching buyers at
    # once rather than within the TTL. Until Wave 2b there was no writer but `scripts/seed_listings.py`,
    # run by hand in the api container, for which 60 s was a shorter wait than the `railway ssh`
    # session that seeded it.
    first_page = raw_cursor is None
    cache_key = f"{LIST_CACHE_PREFIX}{market or ''}::{limit}::{principal.account_id}"
    # One binding for both ends of the cache (final review M9): the read below and the write at
    # the end of this function must not be able to reach two different clients.
    cache = sync_redis() if first_page else None
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(content=cached, media_type="application/json")

    where = ["status = 'published'"]
    params: list[Any] = []
    if market is not None:
        where.append("market = %s")
        params.append(market)
    if keyset is not None:
        where.append("(listed_at, id) < (%s, %s)")
        params += [keyset[0], keyset[1]]
    sql = f"{_SELECT} WHERE {' AND '.join(where)} ORDER BY listed_at DESC, id DESC LIMIT %s"
    params.append(limit + 1)  # one extra row tells us whether another page exists

    with closing(sync_conn()) as conn, conn:
        rows = _rows(conn, sql, tuple(params))
        now = datetime.now(UTC)
        page, more = rows[:limit], len(rows) > limit

        # Task B7: Fetch community context data for the page in one batched query
        page_ids = [str(row["id"]) for row in page]

        # Per-buyer disclosure plan Task 8 (directive §23): ONE extra query for the WHOLE page,
        # never one per listing -- `authorized_capabilities_bulk` (Task 3) is built for exactly
        # this call shape. `caps[listing_id]` is `frozenset()` for every listing this buyer holds
        # no active grant for, which is what makes it safe to pass unconditionally below.
        caps = authorized_capabilities_bulk(
            conn, buyer_account_id=str(principal.account_id),
            listings=[(str(row["id"]), row.get("seller_id")) for row in page],
        )

        # Fetch active vintages and registry for community_rows
        with conn.cursor() as cur:
            cur.execute("SELECT dataset_key, vintage FROM active_vintage")
            active = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute("SELECT dataset_key, attribution_text, vintage, license_status, notes FROM dataset_registry")
            assert cur.description is not None  # After execute(), description is never None
            reg_cols = [d[0] for d in cur.description]
            registry = {r[0]: dict(zip(reg_cols, r)) for r in cur.fetchall()}

        community_data = community_rows(conn, page_ids, active=active, registry=registry)

    body = {
        "items": [serialise(row, now, community=community_data.get(str(row["id"])),
                            capabilities=caps[str(row["id"])]) for row in page],
        "next_cursor": encode_cursor(page[-1]["listed_at"], UUID(str(page[-1]["id"]))) if more else None,
    }
    payload = json.dumps(body)
    if cache is not None:
        cache.setex(cache_key, LIST_TTL_S, payload)
    return Response(content=payload, media_type="application/json")


def _parsed_uuid(listing_id: str) -> UUID | None:
    """The path segment as a UUID, or None — a listing id that is not one names no listing, so it
    is this module's 404 rather than FastAPI's 422 on a `UUID` path parameter."""
    try:
        return UUID(listing_id)
    except ValueError:
        return None


def _published(conn: Any, listing_id: str) -> dict[str, Any] | None:
    parsed = _parsed_uuid(listing_id)
    if parsed is None:
        return None
    rows = _rows(conn, f"{_SELECT} WHERE id = %s AND status = 'published'", (parsed,))
    return rows[0] if rows else None


def _published_photos_and_visibility(conn: Any, listing_id: str) -> tuple[list[str | None], str, str | None] | None:
    """The `photos`, the authoritative privacy setting, AND the seller's account id of one
    published listing, or None when there is no such listing.

    THREE columns, not `_SELECT`'s thirty-odd and its two PostGIS accessors (review round 2, M6):
    the photo route uses nothing else, and a query that says what the route means cannot drift into
    reading something it should not. The setting is read in the SAME statement because spec C.7
    row 1 makes it the first input to every delivery decision — and a second query for it is a
    second chance to be reading a different listing's.

    `seller_id` joined Task 7 of the per-buyer disclosure plan: `has_capability` takes it to refuse
    treating a seller as their own buyer (`app/disclosure/access.py`'s own guard), and reading it
    HERE keeps this a single statement rather than a second round trip that could answer for a
    listing whose seller changed between the two reads (this product has no ownership-transfer
    feature, but the shape matches every other read in this function on principle)."""
    parsed = _parsed_uuid(listing_id)
    if parsed is None:
        return None
    rows = _rows(conn, "SELECT photos, identifiable_content_visibility, seller_id FROM listing"
                       " WHERE id = %s AND status = 'published'", (parsed,))
    if not rows:
        return None
    seller_id = rows[0]["seller_id"]
    return (photo_list(rows[0]["photos"]), str(rows[0]["identifiable_content_visibility"]),
            None if seller_id is None else str(seller_id))


@router.get("/listings/{listing_id}")
async def get_listing(listing_id: str, principal: Reader) -> Response:
    with closing(sync_conn()) as conn, conn:
        row = _published(conn, listing_id)
    if row is None:
        return _error("NOT_FOUND", "No such listing.", 404)

    # Task B7: Fetch community context data for the single listing
    now = datetime.now(UTC)
    with closing(sync_conn()) as conn, conn:
        # Fetch active vintages and registry for community_rows
        with conn.cursor() as cur:
            cur.execute("SELECT dataset_key, vintage FROM active_vintage")
            active = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute("SELECT dataset_key, attribution_text, vintage, license_status, notes FROM dataset_registry")
            assert cur.description is not None  # After execute(), description is never None
            reg_cols = [d[0] for d in cur.description]
            registry = {r[0]: dict(zip(reg_cols, r)) for r in cur.fetchall()}

        community_data = community_rows(conn, [str(row["id"])], active=active, registry=registry)
        # Per-buyer disclosure plan Task 8 (directive §23): ONE single-listing capability lookup —
        # the detail route's own shape of the same authorization boundary the list route's bulk
        # call uses.
        caps = authorized_capabilities(conn, listing_id=str(row["id"]), seller_id=row.get("seller_id"),
                                       buyer_account_id=str(principal.account_id))
        # Task 9: the SAME connection and the SAME `caps`, before either closes -- one more indexed
        # query (`listing_asset_kind_idx`), labelled by what this caller's own capabilities admit.
        # D-C66 (2026-09-24) took the listing's `documents_disclosed` ceiling out of this call: the
        # titles are the request flow's own signpost and are served whether the seller has locked
        # the documents or not.
        documents = _documents(conn, str(row["id"]), capabilities=caps)

    return JSONResponse(serialise(row, now, community=community_data.get(str(row["id"])),
                                  capabilities=caps, documents=documents))


def _object_bytes(key: str) -> bytes | None:
    """One object's bytes, or None. `_asset_bytes`'s own rule with the DECISION taken out of it:
    WHICH key is `buyer_variant`'s to make, and this reads the key it chose (spec C.7).

    Every "no" is the same None, and the route's 404: an unconfigured bucket, an object that is
    gone. A photograph that cannot be served is a missing photograph, never a 500 — and never a
    fallback to a different object (directive 19)."""
    store = ObjectStore.from_settings(settings)
    if store is None:
        return None
    try:
        return store.get(key)
    except (BotoCoreError, ClientError):
        # A bucket outage is a photograph that cannot be served, which is what a 404 says here —
        # `_error`'s envelope, never an unhandled exception (A-SL16 M2). The refusal that a
        # seller's WRITE gets is a 503, because a write can be retried into a different outcome.
        log.warning("[listings] object store unavailable reading a photograph")
        return None


def _privacy_for(conn: Any, listing_id: str, entry: str) -> record.PrivacyRow | None:
    """The one photograph's record, for the bytes route -- the single-row sibling of the list
    route's `visible_photos` aggregate.

    None for three different things, all of which the resolver answers the same way: a seed PATH
    entry (which is not a uuid at all), an entry whose row is gone, and an entry whose row belongs
    to another listing. The last is the IDOR check and it is in SQL through `record.read`'s own
    join plus the comparison below, never in a query parameter."""
    try:
        parsed = UUID(entry)
    except ValueError:
        return None                                   # a seed path entry: `buyer_variant` handles it
    row = record.read(conn, parsed)
    return row if row is not None and str(row.listing_id) == str(listing_id) else None


@router.api_route("/listings/{listing_id}/photos/{n}", methods=["GET", "HEAD"])
async def get_listing_photo(listing_id: str, n: int, request: Request, principal: Reader) -> Response:
    """The ONE buyer bytes route. Every query parameter is ignored for resolution: `?variant=`,
    `?v=` and anything else a caller invents cannot change what this returns (directive 20,
    "alternate image endpoints").

    `api_route(methods=["GET", "HEAD"])` and not `@router.get`: Starlette's own `Route` adds HEAD
    beside GET but FastAPI's `APIRoute` does not, so a `@router.get` route answers HEAD with
    **405**. Spec F's "HEAD mirrors GET on the buyer route and returns the same headers and no
    body" is a claim, and declaring both methods is what makes it true rather than a comment that
    says Starlette will handle it.

    ONE connection for both arms (A-SL16 L8): this is the hottest read on the buyer surface.

    **This is the door directive §9's last line is about**: "Direct access to the original asset
    URL must NOT bypass authorization." A caller reaching this route by its exact positional URL —
    guessed, bookmarked, or replayed — asks its OWN authorization here, every time, from the
    database, never from anything the request carries; the URL names a POSITION (`n`), never a
    storage key, and nothing about which bytes a prior request received changes what THIS one
    resolves to. `principal` REPLACES the router-level `dependencies=[Depends(REQUIRE_LISTING_READ)]`
    this route used to declare (Task 7 of the per-buyer disclosure plan) rather than sitting beside
    it: both spellings are `Depends` on the SAME `REQUIRE_LISTING_READ` object, so keeping both
    would make `route.dependant.dependencies` carry the guard twice and fail
    `tests/api/test_listings.py::test_the_listings_routes_are_guarded_not_public`'s `guards == [...]`
    pin — `app/api/seller_listings.py::read_document` is the existing precedent for a `Reader`
    parameter being the route's ONLY guard."""
    with closing(sync_conn()) as conn, conn:
        found = _published_photos_and_visibility(conn, listing_id)
        if found is None:
            return _error("NOT_FOUND", "No such listing.", 404)
        photos, visibility, seller_id = found
        entry = photos[n - 1] if 1 <= n <= len(photos) else None
        if entry is None:
            return _error("NOT_FOUND", "No such photograph.", 404)
        # Fails closed by construction (directive §19): `has_capability` returns False for every
        # input it cannot prove authorized, so an absent/expired/wrong-capability grant reaches
        # `buyer_variant` as `authorized=False` — the SAME answer this route always gave.
        authorized = has_capability(conn, listing_id=listing_id, seller_id=seller_id,
                                    buyer_account_id=str(principal.account_id), capability="UNREDACTED_IMAGES")
        variant = buyer_variant(visibility, _privacy_for(conn, listing_id, entry), entry,
                                seed_digests().get(entry), authorized=authorized)
        if variant is None:
            return _error("NOT_FOUND", "No such photograph.", 404)
        if not variant.from_disk:
            body = _object_bytes(variant.key)
            if body is None:
                # A bucket outage stays a 404 -- never a fallback to another key (directive 19).
                return _error("NOT_FOUND", "No such photograph.", 404)
            return photo_response(body, variant.sha256, request)
    # A seed entry: `listing.photos` holds a relative path, resolved under PHOTOS_ROOT by
    # `photo_file`, which is what refuses one that escapes it.
    path = photo_file(photos, n)
    if path is None:
        return _error("NOT_FOUND", "No such photograph.", 404)
    return photo_response(path.read_bytes(), variant.sha256, request)
