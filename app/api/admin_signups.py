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
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.admin_users import _cursor, _iso, _keyset
from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import AuthError, require
from app.config import settings
from app.db import sync_conn
from app.mail import templates as TP
from app.mail.outbox import enqueue

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


def _params(source: str | None, consent_version: str | None, keyset: tuple[str | None, UUID | None], limit: int) -> dict[str, Any]:
    keyset_at, keyset_id = keyset
    return {"source": source, "consent_version": consent_version,
            "cursor_at": keyset_at, "cursor_id": keyset_id, "limit": limit}


@router.get("/signups", dependencies=[Depends(REQUIRE_SIGNUPS_READ)])
def list_signups(source: str | None = None, consent_version: str | None = None,
                 cursor: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Every launch-notification sign-up, newest first, with the counts the tab shows.

    A plain `def` (final review M1), so FastAPI runs it in the anyio threadpool like
    `export_signups` and `launch_mail` beside it: `COUNTS_SQL` is an ungated `GROUP BY` over the
    whole table, budgeted at 150 ms by `tests/perf/test_api_latency.py`, and this endpoint's own
    docstring says it is polled by a screen — an `async def` would run all of that blocking
    psycopg2 work on the event loop, stalling every other request for the duration, every poll.

    NOT audited (`signups.read` is not in `AUDITED`): this is the read a screen polls, and one row
    per poll would fill an append-only table with reads of the list. The bulk export beside it is
    audited, because that is the act that takes the addresses somewhere else.

    L4 (I5d.3 review): `cursor` is parsed and validated FIRST, before any connection is opened —
    matching `admin_users.list_users`'s own first line — so a malformed cursor's 422 costs no
    query. Passing a `cursor=` string straight into `_params` (which used to call `_keyset` itself)
    would parse it only after `_counts` had already run."""
    keyset = _keyset(cursor)
    capped = min(max(limit, 1), MAX_LIST)
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        counts = _counts(cur)
        _check_filters(counts, source, consent_version)
        cur.execute(LIST_SQL, _params(source, consent_version, keyset, capped + 1))
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
        cur.execute(LIST_SQL, _params(source, consent_version, (None, None), MAX_EXPORT))
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


# --- the launch mail ----------------------------------------------------------------------------


class LaunchCopyNotApproved(AuthError):
    """Controller amendment A-I5d.4 (John, 2026-09-08, verbatim): "Launch email — COPY NOT YET
    APPROVED. Do not send." Checked first, before the postal-address setting and before
    `SITE_MODE` — a 409 about the WORLD, not about the caller, so an admin who did everything right
    still cannot make an unapproved message sendable. `app.mail.templates.LAUNCH_COPY_APPROVED` is
    the single flag this reads; flipping it is John's decision, not this endpoint's."""

    status = 409
    code = "LAUNCH_COPY_NOT_APPROVED"
    message = "The launch email copy has not been approved yet."


class LaunchMailNotConfigured(AuthError):
    """A-I5d.4's second gate: the CAN-SPAM footer has no postal address to print.
    `settings.vin_foundation_postal_address` is never defaulted to a placeholder (John's ruling:
    "Do not invent the address"), so an empty setting refuses the send by naming the variable
    rather than shipping a footer with a blank line. A-I5d.4b, L2: whitespace-only counts as empty
    too — `VIN_FOUNDATION_POSTAL_ADDRESS=" "` is truthy in Python, and without stripping it the
    footer would render "VIN Foundation ·  ", the exact blank line this gate exists to prevent."""

    status = 409
    code = "LAUNCH_MAIL_NOT_CONFIGURED"
    message = "VIN_FOUNDATION_POSTAL_ADDRESS is not set; the launch email cannot be sent."


class SiteNotLaunched(AuthError):
    """The launch mail, attempted while the site is still serving the Coming Soon page (D-I5d-5).

    Not a permission problem — the caller may well be an admin — so it is a 409 about the world,
    not a 403 about them. The message the mail carries says Practice Match is open; sending it
    before `SITE_MODE=app` would make the VIN Foundation's one promised message a false one."""

    status = 409
    code = "NOT_LAUNCHED"
    message = "The launch email cannot be sent while the site is in coming-soon mode."


LAUNCH_TEMPLATE = "launch_announcement"
# One call acts on at most this many rows (D-I5d-9): the handler holds one pooled connection for
# the length of its transaction, and an unbounded call would write tens of thousands of outbox rows
# under it. `remaining` in the response is how the caller knows to call again.
MAX_LAUNCH_BATCH = 500

LAUNCH_COUNTS_SQL = """
SELECT count(*) FILTER (WHERE launch_mailed_at IS NOT NULL),
       count(*) FILTER (WHERE launch_mailed_at IS NULL)
  FROM interest_signup
"""
# `FOR UPDATE`, not `SKIP LOCKED`: two admins clicking Send at the same moment must not each mail
# half the list. The second caller blocks on the first's rows, and READ COMMITTED re-evaluates the
# WHERE after the lock is granted — so once the first transaction commits, those rows have a
# `launch_mailed_at` and drop out of the second caller's result entirely.
UNMAILED_SQL = "SELECT id, email FROM interest_signup WHERE launch_mailed_at IS NULL ORDER BY id LIMIT %s FOR UPDATE"


class LaunchMailIn(BaseModel):
    # Defaults to a dry run (D-I5d-10): the caller has to say `false` out loud to send something
    # that cannot be unsent.
    dry_run: bool = True


@router.post("/signups/launch-mail")
def launch_mail(body: LaunchMailIn, request: Request, principal: Notifier) -> dict[str, Any]:
    """Queues the launch announcement for every sign-up that has not had it — at most
    `MAX_LAUNCH_BATCH` per call — or, on a dry run, queues nothing and stamps nothing.

    A plain `def` (A-I5d.4b, L4), so FastAPI runs it in the anyio threadpool like `export_signups`
    beside it: up to 500 blocking inserts plus one `SELECT … FOR UPDATE` and one audit write is the
    largest single-request body of work in the codebase, and an `async def` would run all of it on
    the event loop, stalling every other request for as long as it takes.

    Exactly once, and it survives a crash: the `enqueue` and the `launch_mailed_at` stamp commit in
    the SAME transaction, so there is no state in which a row is marked mailed without its outbox
    row, or has two. The outbox's own idempotency key is a second belt but not the braces
    (D-I5d-4): `purge_outbox` deletes delivered rows a day later, so the key is gone by the time a
    careless second call could do damage.

    `signups.notify` is in REAUTH, so the caller has confirmed their password within ten minutes
    and no api token can reach this at all (`deps.TokenCannotReauth`) — which is the containment
    that keeps a leaked automation credential away from the VIN Foundation's whole launch list.

    A REAL send is gated three ways, each a 409 about the world rather than the caller, checked in
    this order (A-I5d.4 adds the first two to D-I5d-5's `SiteNotLaunched`): the copy must be
    approved, the CAN-SPAM postal address must be configured, and the site must actually be open.
    A DRY RUN is exempt from all three — D-I5d-5's "the count is readable, the message is not
    sendable" — because it queues nothing, stamps nothing, and talks to nobody. It still writes one
    audit row, `reason: dry_run`, the way rehearsing a mass mail deserves a trace.

    Nothing here talks to Resend. The Celery `mail.send` task drains the outbox, applies
    `EMAIL_ALLOWLIST` outside production and refuses suppressed addresses, all unchanged."""
    if not body.dry_run:
        if not TP.LAUNCH_COPY_APPROVED:
            raise LaunchCopyNotApproved
        if not (settings.vin_foundation_postal_address or "").strip():
            raise LaunchMailNotConfigured
        if settings.site_mode != "app":
            raise SiteNotLaunched
    queued = 0
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute(LAUNCH_COUNTS_SQL)
            already, pending = cast("tuple[int, int]", cur.fetchone())
            batch: list[tuple[Any, str]] = []
            if not body.dry_run:
                cur.execute(UNMAILED_SQL, (MAX_LAUNCH_BATCH,))
                batch = cast("list[tuple[Any, str]]", cur.fetchall())
        for signup_id, email in batch:
            # `enqueue` returns False when the key is already there — count what was really
            # written, so the response cannot claim a row it did not create. `postal_address`
            # travels in the enqueued params (A-I5d.4), alongside `link`, so a row already queued
            # keeps the address that was configured when it was queued.
            if enqueue(conn, to=email, template=LAUNCH_TEMPLATE,
                       params={"link": settings.link_base_url, "postal_address": settings.vin_foundation_postal_address},
                       idempotency_key=f"{signup_id}:{LAUNCH_TEMPLATE}:1"):
                queued += 1
        if batch:
            with conn.cursor() as cur:
                cur.execute("UPDATE interest_signup SET launch_mailed_at = now() WHERE id = ANY(%s)",
                            ([signup_id for signup_id, _email in batch],))
        selected = len(batch) if not body.dry_run else min(pending, MAX_LAUNCH_BATCH)
        # In this handler's own body, never through a helper: the audit drift test reads
        # `inspect.getsource(route.endpoint)`. A dry run is audited too — rehearsing a mass mail is
        # worth a line — and `reason` is what tells the two apart.
        audit.write(conn, actor=principal, action="signups.notify", target_type="interest_signup",
                    after={"selected": selected, "queued": queued, "already_mailed": already, "not_mailed": pending},
                    reason="dry_run" if body.dry_run else "send", request=request)
    return {"dry_run": body.dry_run, "selected": selected, "queued": queued,
            "already_mailed": already, "not_mailed": pending,
            "remaining": pending - len(batch)}
