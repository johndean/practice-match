"""The Admin "Launch sign-ups" surface (Task I5d, John 2026-09-08).

`interest_signup` is filled by the public Coming Soon page (`app/api/interest.py`, spec
2026-09-06 §3), whose own closing sentence is "No email is sent from here; the Identity wave's
Resend pipeline reads this table at launch". This module is the other end of that sentence: the
list staff read, the export they hand to whoever addresses the mail, and the one send.

Three shapes here are load-bearing, exactly as in `app/api/admin_users.py` beside it:

* **Every guard is a module-level constant, never wrapped.** `tests/auth/test_permissions.py`
  resolves a route's permission by the guard's object IDENTITY.
* **`audit.write(` is called in each audited endpoint's OWN body**, never through a helper: the
  drift test reads `inspect.getsource(route.endpoint)`.
* **`signups.read` LISTS and is not audited; `signups.export` and `signups.notify` are.** Same
  reasoning as `users.review` vs `users.view_detail` (I5 fix round 1, C2): a screen that polls the
  list must not write one row per poll into a table whose triggers refuse DELETE.

The keyset cursor helpers come from `admin_users` rather than being copied (D-I5d-11). F3 — a
cursor carrying only a timestamp, which dropped every row sharing the last row's `created_at` and
then reported the list complete — is exactly the defect a second copy would re-introduce, and
`now()` is transaction time, so ties are routine in this table too. `_keyset` raises
`admin_users.BadCursor` on anything that is not a `<timestamp>|<uuid>` pair, which is why that
class is not imported here: it is never referenced by name, only raised through the helper.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.admin_users import _cursor, _iso, _keyset
from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import AuthError, require
from app.db import sync_conn

router = APIRouter(prefix="/api/admin")

REQUIRE_SIGNUPS_READ = require("signups.read")
REQUIRE_SIGNUPS_EXPORT = require("signups.export")
REQUIRE_SIGNUPS_NOTIFY = require("signups.notify")

Exporter = Annotated[S.Principal, Depends(REQUIRE_SIGNUPS_EXPORT)]
Notifier = Annotated[S.Principal, Depends(REQUIRE_SIGNUPS_NOTIFY)]

MAX_LIST = 200
# At most this many rows leave in one file. The table is a launch-notification list, not an event
# stream; the cap is a floor under memory rather than a product limit (D-I5d-8).
MAX_EXPORT = 100_000
CSV_COLUMNS = ("id", "email", "source", "consent_version", "created_at", "launch_mailed_at")
# The characters a spreadsheet reads as the start of a formula. `app/api/interest.py`'s EMAIL_RE
# accepts an address beginning with any of the first four, so this is a value this table can hold.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class BadFilter(AuthError):
    """A `source=`/`consent_version=` value that names no row. Validated against the values the
    table actually holds, not a hard-coded enum (D-I5d-6): both columns are free `text`, so an enum
    would refuse a legitimate future source — while a 200 with an empty list would read as "no such
    sign-ups" instead of "no such filter" (the F10 defect, in this tab)."""

    status = 422
    code = "BAD_FILTER"

    def __init__(self, name: str, known: list[str]) -> None:
        self.message = f"{name} must be one of {', '.join(known) or '(no sign-ups yet)'}"
        super().__init__()


# One grouped scan answers three questions: the counts the tab shows, the count for the current
# filter, and (D-I5d-6) which filter values exist. Kept as one statement so those three can never
# disagree with each other.
COUNTS_SQL = """
SELECT source, consent_version, (launch_mailed_at IS NOT NULL) AS mailed, count(*)
  FROM interest_signup GROUP BY 1, 2, 3
"""

LIST_SQL = """
SELECT id, email, source, consent_version, created_at, launch_mailed_at
  FROM interest_signup
 WHERE (%(source)s::text IS NULL OR source = %(source)s)
   AND (%(consent_version)s::text IS NULL OR consent_version = %(consent_version)s)
   AND (%(cursor_at)s::timestamptz IS NULL
        OR (created_at, id) < (%(cursor_at)s::timestamptz, %(cursor_id)s::uuid))
 ORDER BY created_at DESC, id DESC
 LIMIT %(limit)s
"""


class Counts:
    """The grouped counts, read once and asked several questions.

    A small class rather than a tuple of dicts because the filter validation, the `filtered` count
    and the response body all read the same rows, and naming them here is what keeps the handler
    from re-deriving any of them differently."""

    def __init__(self, rows: list[tuple[str, str, bool, int]]) -> None:
        self.rows = rows
        self.total = sum(n for _s, _c, _m, n in rows)
        self.mailed = sum(n for _s, _c, m, n in rows if m)
        self.by_source: dict[str, int] = {}
        self.by_consent: dict[str, int] = {}
        for source, consent, _mailed, n in rows:
            self.by_source[source] = self.by_source.get(source, 0) + n
            self.by_consent[consent] = self.by_consent.get(consent, 0) + n

    def filtered(self, source: str | None, consent_version: str | None) -> int:
        return sum(n for s, c, _m, n in self.rows
                   if (source is None or s == source) and (consent_version is None or c == consent_version))

    def body(self, source: str | None, consent_version: str | None) -> dict[str, Any]:
        return {"total": self.total, "launch_mailed": self.mailed, "not_mailed": self.total - self.mailed,
                "filtered": self.filtered(source, consent_version),
                "by_source": dict(sorted(self.by_source.items())),
                "by_consent_version": dict(sorted(self.by_consent.items()))}


def _counts(cur: Any) -> Counts:
    cur.execute(COUNTS_SQL)
    return Counts(cast("list[tuple[str, str, bool, int]]", cur.fetchall()))


def _check_filters(counts: Counts, source: str | None, consent_version: str | None) -> None:
    """Both filters against the values the table holds (D-I5d-6). Raised BEFORE the list query, so
    a refused request costs one grouped scan and nothing else."""
    if source is not None and source not in counts.by_source:
        raise BadFilter("source", sorted(counts.by_source))
    if consent_version is not None and consent_version not in counts.by_consent:
        raise BadFilter("consent_version", sorted(counts.by_consent))


def _params(source: str | None, consent_version: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    keyset_at, keyset_id = _keyset(cursor)
    return {"source": source, "consent_version": consent_version,
            "cursor_at": keyset_at, "cursor_id": keyset_id, "limit": limit}


@router.get("/signups", dependencies=[Depends(REQUIRE_SIGNUPS_READ)])
async def list_signups(source: str | None = None, consent_version: str | None = None,
                       cursor: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Every launch-notification sign-up, newest first, with the counts the tab shows.

    NOT audited (`signups.read` is not in `AUDITED`): this is the read a screen polls, and one row
    per poll would fill an append-only table with reads of the list. The bulk export beside it is
    audited, because that is the act that takes the addresses somewhere else."""
    capped = min(max(limit, 1), MAX_LIST)
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        counts = _counts(cur)
        _check_filters(counts, source, consent_version)
        cur.execute(LIST_SQL, _params(source, consent_version, cursor, capped + 1))
        rows = cur.fetchall()
    items = [{"id": str(r[0]), "email": r[1], "source": r[2], "consent_version": r[3],
              "created_at": r[4].isoformat(), "launch_mailed_at": _iso(r[5])}
             for r in rows[:capped]]
    last = items[-1] if len(rows) > capped else None
    return {"items": items,
            "next_cursor": _cursor(cast("str", last["created_at"]), cast("str", last["id"])) if last is not None else None,
            "counts": counts.body(source, consent_version)}


def _safe(value: str) -> str:
    """`value`, with a leading formula character neutralised (D-I5d-7).

    A single apostrophe is what every spreadsheet reads as "the rest is text". The untransformed
    value is always one `GET /api/admin/signups` away; this file's audience is a spreadsheet."""
    return "'" + value if value.startswith(FORMULA_PREFIXES) else value


def _csv_rows(source: str | None, consent_version: str | None) -> Iterator[str]:
    """The file, one rendered line at a time.

    A SYNC generator on purpose: Starlette iterates one in a threadpool, so the blocking psycopg2
    reads below never run on the event loop. An ordinary client-side cursor, not a named one —
    `sync_conn()` is autocommit and psycopg2 refuses a server-side cursor outside a transaction
    (D-I5d-8 records the upgrade path). `closing(...)` inside the generator is what returns the
    connection to the pool when a client disconnects mid-file: the generator is closed, the
    `finally` runs."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)

    def flush() -> str:
        line = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return line

    writer.writerow(CSV_COLUMNS)
    yield flush()
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(LIST_SQL, _params(source, consent_version, None, MAX_EXPORT))
        for row in cur:
            writer.writerow([_safe(str(row[0])), _safe(row[1]), _safe(row[2]), _safe(row[3]),
                             row[4].isoformat(), _iso(row[5]) or ""])
            yield flush()


@router.get("/signups.csv")
def export_signups(request: Request, principal: Exporter,
                   source: str | None = None, consent_version: str | None = None) -> StreamingResponse:
    """The same list as a downloadable RFC 4180 file: CRLF, minimal quoting, doubled quotes, UTF-8
    and no BOM (D-I5d-7).

    A plain `def`, so FastAPI runs it in a threadpool like the generator it returns. The filters are
    validated and the audit row is written BEFORE the first byte leaves, so a client that
    disconnects mid-file still leaves the trace that the export was asked for."""
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            _check_filters(_counts(cur), source, consent_version)
        audit.write(conn, actor=principal, action="signups.export", target_type="interest_signup",
                    after={"source": source, "consent_version": consent_version}, request=request)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return StreamingResponse(
        _csv_rows(source, consent_version),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="practice-match-signups-{stamp}.csv"'},
    )
