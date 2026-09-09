"""The Admin > Data Sources surface (Census spec §2/§9/§12): every registered dataset with its
licence status, its attribution string, its active vintage and its last ingest run — and the one
place a human decision changes `dataset_registry.license_status`.

This is the console behind CLAUDE.md's "Blocked datasets never ship … The admin Data Sources tab
shows this gate; keep it." Nothing here loads, ingests or renders data; it reports the gate and
lets an admin move it.

Shapes that are load-bearing, each one already broken somewhere in this codebase before:

* **Every guard is a module-level constant, never wrapped.** `tests/auth/test_permissions.py`
  resolves a route's permission by the guard's object IDENTITY (`deps.permission_of`), and a
  wrapper reads as "guarded but unresolvable", which that test treats as an error.
  `data_sources.read` (staff/admin) sits on the ROUTER, so both routes carry it; `/license` adds
  `licence.decide` (admin, and in `permissions.REAUTH` — the caller confirmed their password in
  the last ten minutes, and no `api_token` can ever satisfy it, whatever role it carries).
* **`audit.write(` is called in `decide_license`'s OWN body.** `licence.decide` is in
  `permissions.AUDITED` and the drift test reads `inspect.getsource(route.endpoint)`, so
  delegating the write to a helper would make this route read as unaudited (A-C0 ¶3).
* **Two ledgers, and they are not the same ledger.** `audit_log` (via `app.auth.audit`) records
  WHO changed the gate, from what to what; `license_audit_log` is the LICENCE ledger the quarterly
  sweep writes into (`app.census.license`), and a human decision belongs in it too — with
  `changed = false`, because a decision is not evidence that the published terms moved. Both rows
  and the registry update commit together or not at all.
* **No bare `HTTPException`** (A-C0 ¶4): a refusal from this module carries decision A5's
  `{"error": {"code", "message"}}` through `_error(...)`, the shape `app/api/listings.py` uses.
* **The Redis write happens AFTER the commit** (the ruling `app/api/admin_users.py` records):
  dropping the gate's cached answer while the decision was still uncommitted leaves a window in
  which a concurrent reader re-caches the pre-decision status for another full minute.

**`last_verified_at` and `drift_flagged` are independent, and reported as such** (A-C8 (11), from
the A8 review's i3/i4):

* `last_verified_at` answers "when was this licence last VERIFIED", and it has two authors, which a
  reader has to know before trusting it (A-C9 (4)). The quarterly sweep
  (`app/census/license.py`) sets it only on a check that actually read a body, so a dataset with no
  `license_audit_log` row — or whose only check failed, or 404ed — reads `null`, "never verified",
  never the date of the attempt. `decide_license` below is the second author: an admin who has just
  read the terms is the strongest verification event in this system, so a decision stamps the field
  too, without fetching anything. The two are told apart after the fact in the LEDGER, where a
  human decision is the row with no `content_sha256` and no `http_status`. So a non-null value here
  means "a body was hashed OR an admin decided" — never, on its own, "a body was hashed".
* `drift_flagged` is its own field and never derived from the time. A later sweep that finds the
  terms unchanged since the drift REFRESHES `last_verified_at` and leaves the flag standing; only
  an admin decision here clears it. A console that inferred "verified" from a recent date would
  quietly retire a drift nobody had looked at.

`attribution_text` is returned verbatim from `dataset_registry` and is never composed here: it is
legally load-bearing (spec §12), and the whole point of holding it in the database is that a terms
change propagates in one UPDATE.
"""
from __future__ import annotations

import logging
from contextlib import closing
from datetime import datetime
from typing import Annotated, Any, Literal, cast

import redis as redis_sync
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.cache import sync_redis
from app.census import gate
from app.db import sync_conn

log = logging.getLogger(__name__)

# `data_sources.read` on the router: staff and admin read the console. `/license` carries
# `licence.decide` of its own, below.
REQUIRE_DATA_SOURCES_READ = require("data_sources.read")
REQUIRE_LICENCE_DECIDE = require("licence.decide")

router = APIRouter(prefix="/api/admin", dependencies=[Depends(REQUIRE_DATA_SOURCES_READ)])

LicenceDecider = Annotated[S.Principal, Depends(REQUIRE_LICENCE_DECIDE)]

MAX_NAME, MAX_NOTES = 200, 4_000
# `license_audit_log.url` is NOT NULL, and a decision made without one still has to say what it
# was: a named human's, not a fetch.
OPERATOR_DECISION = "operator decision"

LIST_SQL = """
SELECT r.dataset_key, r.display_name, r.api_dataset_id, r.vintage, r.refresh_cadence,
       r.license_status, r.license_name, r.license_url, r.attribution_text,
       r.last_verified_at, r.drift_flagged, r.notes,
       a.vintage, a.note,
       (SELECT json_build_object('status', i.status, 'finished_at', i.finished_at, 'rows_written', i.rows_written)
          FROM ingest_run i WHERE i.dataset_key = r.dataset_key ORDER BY i.id DESC LIMIT 1)
  FROM dataset_registry r LEFT JOIN active_vintage a USING (dataset_key)
 ORDER BY r.dataset_key
"""


def _error(code: str, message: str, status: int) -> JSONResponse:
    """Decision A5's body for the refusals this module raises itself."""
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _row(r: tuple[Any, ...]) -> dict[str, Any]:
    """One `LIST_SQL` row as the console reads it.

    `active_vintage_note` is A-C7 (6)'s persisted "why": the CLI requires it when an activation is
    forced past the row-count guard, and this tab is the only surface that reads it back — a note
    written for a human and shown to nobody would be a strange thing to have made mandatory."""
    return {
        "dataset_key": r[0], "display_name": r[1], "api_dataset_id": r[2], "vintage": r[3],
        "refresh_cadence": r[4], "license_status": r[5], "license_name": r[6], "license_url": r[7],
        "attribution_text": r[8], "last_verified_at": _iso(r[9]), "drift_flagged": r[10], "notes": r[11],
        "active_vintage": r[12], "active_vintage_note": r[13], "last_run": r[14],
    }


@router.get("/data-sources")
def list_data_sources() -> list[dict[str, Any]]:
    """Every registered dataset, blocked and unresolved ones included and marked as such.

    A plain `def`, so FastAPI runs it in its threadpool (A-C9 (6), the rule A-I5d's CSV export
    already follows): everything below it — `sync_conn()`, the query, the commit — is blocking
    psycopg2, and on the event loop that would park every other request in the process for the
    duration.

    Guarded by `data_sources.read`, which is NOT in `permissions.AUDITED`, so no audit row is
    written here — reading the gate is not a decision, and one row per poll of the Data Sources tab
    into a table whose triggers refuse DELETE is the leak `users.review` was split out to avoid."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(LIST_SQL)
        return [_row(row) for row in cur.fetchall()]


class LicenseDecision(BaseModel):
    """A human licence decision. Only `status` is required: every other field COALESCEs onto what
    is already recorded, so blocking a source does not mean retyping its licence name and URL."""

    status: Literal["cleared", "unresolved", "blocked"]
    name: str | None = Field(default=None, max_length=MAX_NAME)
    url: HttpUrl | None = None
    notes: str | None = Field(default=None, max_length=MAX_NOTES)


@router.post("/data-sources/{dataset_key}/license")
def decide_license(dataset_key: str, body: LicenseDecision, request: Request, principal: LicenceDecider) -> Response:
    """Record a licence decision, and hide or reveal the layer within the minute.

    A plain `def` for the reason `list_data_sources` gives (A-C9 (6)), and the reason is stronger
    here: this handler takes a row lock and holds it across three writes, so on the event loop a
    single contended decision would stall the whole process rather than one worker thread.

    `licence.decide` is admin-only and in `permissions.REAUTH`: the caller confirmed their password
    in the last ten minutes, and no `api_token` can ever reach here — a licence decision is a named
    human's, which is exactly what the audit row records.

    `drift_flagged` comes down and `last_verified_at` goes to now: the admin has just looked at the
    terms, which is the only event in this system besides the sweep that counts as a verification
    (see the `last_verified_at` paragraph above — this handler is its second author)."""
    if body.url is not None and body.url.scheme != "https":
        # A-C9 (5). `app/census/license.py` re-fetches this URL quarterly and hashes what comes
        # back; over clear text anything on the path can rewrite the page the drift check compares.
        # `HttpUrl` allows both schemes, so the narrowing is here, at the only door that edits it.
        return _error("BAD_FIELD", "A licence URL must use https.", 422)
    url = str(body.url) if body.url else None
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            # Read-then-write under one row lock: the `before` the audit row records has to be the
            # state this decision actually replaced, not one a concurrent decision has since moved.
            cur.execute("SELECT license_status, drift_flagged FROM dataset_registry WHERE dataset_key = %s FOR UPDATE", (dataset_key,))
            row = cur.fetchone()
            if row is None:
                # Nothing written, nothing invalidated. The key is not echoed back: it is
                # caller-supplied text, and the console already knows what it asked for.
                return _error("NOT_FOUND", "No such data source.", 404)
            before = {"license_status": row[0], "drift_flagged": row[1]}
            cur.execute(
                """UPDATE dataset_registry
                      SET license_status = %s,
                          license_name = COALESCE(%s, license_name),
                          license_url = COALESCE(%s, license_url),
                          notes = COALESCE(%s, notes),
                          drift_flagged = false,
                          last_verified_at = now()
                    WHERE dataset_key = %s
                RETURNING license_status, drift_flagged""",
                (body.status, body.name, url, body.notes, dataset_key),
            )
            # The row exists and is locked, so the UPDATE matched it; the cast is what that
            # guarantees already, and a branch that can never be taken is one no test could close.
            status, drift = cast("tuple[str, bool]", cur.fetchone())
            cur.execute(
                "INSERT INTO license_audit_log (dataset_key, url, changed) VALUES (%s, %s, false)",
                (dataset_key, url or OPERATOR_DECISION),
            )
        # In this handler's own body, and named after the permission that guards it (A-C0 ¶3).
        # `reason` carries the admin's own words; `before`/`after` carry the gate, which is the
        # thing an auditor is looking for.
        audit.write(conn, actor=principal, action="licence.decide", target_type="dataset_registry",
                    target_id=dataset_key, before=before, after={"license_status": status, "drift_flagged": drift},
                    reason=body.status if not body.notes else f"{body.status}: {body.notes}", request=request)
    # AFTER the commit above: `invalidate` drops the gate's cached answer for this dataset and
    # bumps `market:gate:v`, which keys away every cached panel and community payload assembled
    # under the old decision (red-team C5).
    try:
        gate.invalidate(sync_redis(), dataset_key)
    except redis_sync.RedisError as exc:
        # A-C9 (3). The decision is already committed and permanent; this is a cache drop. Failing
        # the request now would show an admin a 500 for a change that HAS been made, and they would
        # re-try or escalate — so it is logged and swallowed, and the gate's own 60 s TTL is the
        # backstop that self-heals within the window spec §11 promises. Only the exception's TYPE
        # is logged, never its text, which can carry a host and port (the rule
        # `app/census/license.py` follows for the same reason).
        log.error("[census] licence decision for %s committed but the layer gate was not invalidated: %s",
                  dataset_key, type(exc).__name__)
    return JSONResponse({"dataset_key": dataset_key, "license_status": status})
