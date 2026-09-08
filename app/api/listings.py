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
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.auth.deps import require
from app.cache import sync_redis
from app.db import sync_conn

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

_SELECT = """
SELECT id, slug, name, street, city, state, zip, phone, hours, status, location_disclosed,
       name_disclosed, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng,
       area, type, market, price, rev, docs, rooms, sqft, bldg, est, listed_at,
       note, staff, services, facility, ownership, photos
  FROM listing
"""

def _error(code: str, message: str, status: int) -> JSONResponse:
    """Decision A5's body for the refusals this module raises itself."""
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


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


def photo_list(value: object) -> list[str]:
    """`listing.photos` as a list of relative paths.

    psycopg2 decodes a `jsonb` column to a Python list, so the string arm is unreachable from a
    request — but `serialise` is also called directly (by tests, and by Wave 2b's admin views,
    which read rows through other drivers), and 100 % branches is the gate. One helper with two
    tested arms, rather than the same defensive ternary written twice (pre-flight C2)."""
    if isinstance(value, str):
        loaded = json.loads(value)
        return [str(item) for item in loaded]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []   # a NULL `photos` (nothing writes one: the column is NOT NULL DEFAULT '[]')


def photo_file(photos: list[str], n: int) -> Path | None:
    """The file behind photo `n` (1-based) of `photos`, or None. The path comes from the
    database, so it is resolved under PHOTOS_ROOT and anything that escapes is refused —
    a `photos` value of `["../../../etc/passwd"]` must be a 404, not a file read."""
    if not 1 <= n <= len(photos):
        return None
    root = PHOTOS_ROOT.resolve()
    candidate = (root / photos[n - 1]).resolve()
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
        "price": row["price"], "rev": row["rev"], "docs": row["docs"], "rooms": row["rooms"],
        "sqft": row["sqft"], "bldg": row["bldg"], "est": row["est"],
        "listed": relative_listed(row["listed_at"], now),
        "listed_at": row["listed_at"].isoformat(),
        "status": row["status"],
        # D4: the community figures stay null until the Census plan supplies them; the UI
        # shows its existing empty state for them.
        "pop": None, "growth": None, "income": None, "hh": None,
        "note": row["note"], "staff": row["staff"], "services": row["services"],
        "facility": row["facility"], "ownership": row["ownership"],
        "lat": float(row["lat"]) if disclosed and row["lat"] is not None else None,
        "lng": float(row["lng"]) if disclosed and row["lng"] is not None else None,
        "location_disclosed": disclosed,
        "photos": [f"/api/listings/{listing_id}/photos/{n}" for n in range(1, len(photos) + 1)],
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
    # Nothing INVALIDATES it, by design: the only writer today is `scripts/seed_listings.py`, run
    # by hand in the api container, and a 60 s TTL is a shorter wait than the `railway ssh` session
    # that seeded it. Wave 2b's seller edits are the point at which this needs a real invalidation
    # (drop the `listings:v1:*` keys on write), and it is theirs to add, not this task's — a hard
    # requirement there rather than a nice-to-have, because a disclosure flag turned OFF must stop
    # reaching buyers at once (review round 2, M4).
    first_page = raw_cursor is None
    cache_key = f"listings:v1:{market or ''}::{limit}"
    if first_page:
        cached = sync_redis().get(cache_key)
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
    if first_page:
        sync_redis().setex(cache_key, LIST_TTL_S, payload)
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


def _published_photos(conn: Any, listing_id: str) -> list[str] | None:
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


@router.get("/listings/{listing_id}/photos/{n}", dependencies=[Depends(REQUIRE_LISTING_READ)])
async def get_listing_photo(listing_id: str, n: int) -> Response:
    with closing(sync_conn()) as conn, conn:
        photos = _published_photos(conn, listing_id)
    if photos is None:
        return _error("NOT_FOUND", "No such listing.", 404)
    path = photo_file(photos, n)
    if path is None:
        return _error("NOT_FOUND", "No such photograph.", 404)
    return Response(
        content=path.read_bytes(),
        media_type="image/webp",
        headers={"Cache-Control": PHOTO_CACHE_CONTROL},
    )
