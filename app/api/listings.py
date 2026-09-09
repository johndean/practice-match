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

Every seed sets both flags true (D8, A-L5), so nothing John sees on QA changes; Wave 2b's sellers
default to false, which is why both branches have to be right now rather than later.

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
from pathlib import Path
from typing import Any
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.auth.deps import require
from app.cache import sync_redis
from app.config import settings
from app.db import sync_conn
from app.storage import ObjectStore

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Hoisted to a module-level constant, never wrapped (Global Constraint (g)).
REQUIRE_LISTING_READ = require("listing.read")

ROOT = Path(__file__).resolve().parent.parent.parent
PHOTOS_ROOT = ROOT / "seeds" / "hospitals" / "photos"
LIST_TTL_S = 60
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_MARKET_LEN = 64
PHOTO_CACHE_CONTROL = "private, max-age=86400"
LIST_CACHE_PREFIX = "listings:v1:"

_SELECT = """
SELECT id, slug, name, street, city, state, zip, phone, hours, status, location_disclosed,
       name_disclosed, rev_disclosed, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng,
       area, type, market, price, rev, docs, rooms, sqft, bldg, est, listed_at,
       note, staff, services, facility, ownership, photos, photo_captions
  FROM listing
"""

def _error(code: str, message: str, status: int) -> JSONResponse:
    """Decision A5's body for the refusals this module raises itself."""
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def drop_list_cache(cache: Any) -> int:
    """Every `listings:v1:*` key, dropped; the number removed.

    Spec 2026-09-08 D16, which is this module's own review-round-2 M4 requirement made real: a
    disclosure flag turned OFF must stop reaching buyers AT ONCE, not within the 60 s TTL. Every
    writer in `app/api/seller_listings.py` and `app/api/admin_listings.py` calls this AFTER its
    transaction commits — the ordering `admin_users.py` learned in I5c fix round 1 — because
    dropping the key while the write is uncommitted leaves a window in which a concurrent read
    re-caches the pre-write payload for the full TTL.

    `scan_iter`, not `keys`: the cache is small but a blocking KEYS on a shared Railway Redis is a
    stall every other consumer pays for. The prefix is the key shape's own, so a v2 key scheme
    cannot be silently missed — it would not match, and the test that plants two keys would fail.
    """
    removed = 0
    for key in cache.scan_iter(match=f"{LIST_CACHE_PREFIX}*"):
        cache.delete(key)
        removed += 1
    return removed


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


def serialise(row: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """One database row as the JSON contract Task L6 maps, with both disclosure flags applied —
    see the module docstring: an undisclosed address loses its street, postcode, telephone number
    and point, an undisclosed name loses the name and the slug that spells it.

    **The two flags are INDEPENDENT by design (A-L5.2, ruled 2026-09-08).** A listing may hide its
    name and still show its address, point and telephone number — a buyer could then find the name
    in a search, and that is the seller's own choice under "Sellers control what buyers can see",
    not a leak to close here. Wave 2b's UI says so beside the two switches. Do not "fix" this by
    making one flag imply the other."""
    disclosed = bool(row["location_disclosed"])
    named = bool(row["name_disclosed"])
    listing_id = str(row["id"])
    photos = photo_list(row["photos"])
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
        "price": row["price"], "rev": row["rev"] if row.get("rev_disclosed") else None,
        "docs": row["docs"], "rooms": row["rooms"],
        "sqft": row["sqft"], "bldg": row["bldg"], "est": row["est"],
        "listed": relative_listed(row["listed_at"], now),
        "listed_at": row["listed_at"].isoformat(),
        "status": row["status"],
        # D4: the community figures stay null until the Census plan supplies them. The UI then
        # renders the design's own empty state for them — the dashed "Community data unavailable
        # for this location" card — which is what amendments A12.10/A12.11 reach (final review I1;
        # before them a null `pop` rendered the populated four-tile grid with every value blank,
        # under the Census attribution). A12.6/A12.7 are why a null `growth`/`hh` does not throw.
        "pop": None, "growth": None, "income": None, "hh": None,
        "note": row["note"], "staff": row["staff"], "services": row["services"],
        "facility": row["facility"], "ownership": row["ownership"],
        "lat": float(row["lat"]) if disclosed and row["lat"] is not None else None,
        "lng": float(row["lng"]) if disclosed and row["lng"] is not None else None,
        "location_disclosed": disclosed,
        # Positional (A-L10): position `n` is the design's photo slot `n`, and an empty slot is a
        # JSON `null` rather than a URL that would 404 — `photoSet`'s `p.photos[i]` then falls to
        # the design's own placeholder for that slot instead of a broken image.
        "photos": [
            None if path is None else f"/api/listings/{listing_id}/photos/{n}"
            for n, path in enumerate(photos, start=1)
        ],
        # A-L11: one description per photograph, PARALLEL to `photos` — position `n` describes
        # position `n`. The design's `photoSet` reads it as `p.photoCaptions[i]` and falls back to
        # its own fixed slot caption where the entry is null (amendment A15), which is what lets a
        # photograph past the sixth be rendered at all: the design has no seventh caption.
        "photo_captions": photo_list(row["photo_captions"]),
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


@router.get("/listings", dependencies=[Depends(REQUIRE_LISTING_READ)])
async def list_listings(request: Request) -> Response:
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

    # One key per (market, limit) — after I1 above, the two inputs that change a FIRST page. The
    # list is published-only and carries no per-account field, so every member sees the same bytes
    # and the cache is safe to share across principals; if a later task adds a per-account field to
    # this payload, this key must gain the account id or the cache must go.
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
    cache_key = f"{LIST_CACHE_PREFIX}{market or ''}::{limit}"
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
    body = {
        "items": [serialise(row, now) for row in page],
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


def _published_photos(conn: Any, listing_id: str) -> list[str | None] | None:
    """The `photos` of one published listing, or None when there is no such listing.

    One column, not `_SELECT`'s thirty-one and its two PostGIS accessors (review round 2, M6): the
    photo route uses nothing else, and a query that says what the route means cannot drift into
    reading something it should not."""
    parsed = _parsed_uuid(listing_id)
    if parsed is None:
        return None
    rows = _rows(conn, "SELECT photos FROM listing WHERE id = %s AND status = 'published'", (parsed,))
    return photo_list(rows[0]["photos"]) if rows else None


@router.get("/listings/{listing_id}", dependencies=[Depends(REQUIRE_LISTING_READ)])
async def get_listing(listing_id: str) -> Response:
    with closing(sync_conn()) as conn, conn:
        row = _published(conn, listing_id)
    if row is None:
        return _error("NOT_FOUND", "No such listing.", 404)
    return JSONResponse(serialise(row, datetime.now(UTC)))


def _asset_bytes(conn: Any, listing_id: str, entry: str) -> bytes | None:
    """A seller-uploaded photograph's bytes, or None.

    The SECOND arm of `listing.photos`'s single `if` (spec 2026-09-08 D15 reason 3): a
    `source='seed'` entry is a relative path resolved under PHOTOS_ROOT by `photo_file`, and a
    seller entry is an asset uuid resolved here. Both arms are tested, and the URL the browser asks
    for is identical — which is why no amendment, no baseline and no `toPractice` field moves.

    Every "no" is the same None, and the route's 404: an entry that is not a uuid, a uuid that
    names no asset of this listing, an unconfigured bucket, an object that is gone. A photograph
    that cannot be served is a missing photograph, never a 500."""
    try:
        asset_id = UUID(entry)
    except ValueError:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT storage_key FROM listing_asset WHERE id=%s AND listing_id=%s AND kind='photo'",
                    (asset_id, UUID(listing_id)))
        found = cur.fetchone()
    if found is None:
        return None
    store = ObjectStore.from_settings(settings)
    if store is None:
        return None
    try:
        return store.get(found[0])
    except (BotoCoreError, ClientError):
        # A bucket outage is a photograph that cannot be served, which is what a 404 says here —
        # `_error`'s envelope, never an unhandled exception (A-SL16 M2). The refusal that a
        # seller's WRITE gets is a 503, because a write can be retried into a different outcome.
        log.warning("[listings] object store unavailable reading %s", found[0])
        return None


@router.get("/listings/{listing_id}/photos/{n}", dependencies=[Depends(REQUIRE_LISTING_READ)])
async def get_listing_photo(listing_id: str, n: int) -> Response:
    # ONE connection for both arms (A-SL16 L8): this is the hottest read on the buyer surface, and
    # the seller arm used to close this one and open a second to resolve the asset.
    with closing(sync_conn()) as conn, conn:
        photos = _published_photos(conn, listing_id)
        if photos is None:
            return _error("NOT_FOUND", "No such listing.", 404)
        entry = photos[n - 1] if 1 <= n <= len(photos) else None
        if entry is not None and "/" not in entry:
            # A seller's photograph: `listing.photos` holds the asset uuid, not a path. A seed
            # entry always contains a "/" (`<slug>/<n>.webp`), so the two are told apart by the
            # value itself rather than by a second query for the row's `source`.
            content = _asset_bytes(conn, listing_id, entry)
            if content is None:
                return _error("NOT_FOUND", "No such photograph.", 404)
            return Response(content=content, media_type="image/webp",
                            headers={"Cache-Control": PHOTO_CACHE_CONTROL})
    path = photo_file(photos, n)
    if path is None:
        return _error("NOT_FOUND", "No such photograph.", 404)
    return Response(
        content=path.read_bytes(),
        media_type="image/webp",
        headers={"Cache-Control": PHOTO_CACHE_CONTROL},
    )
