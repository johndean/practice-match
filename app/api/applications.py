"""The buyer and seller applications (spec §6).

Refusals are `app.auth.deps.AuthError` subclasses, never bare `HTTPException`s: FastAPI renders an
ordinary `HTTPException` as `{"detail": ...}`, and decision A5's body is
`{"error": {"code", "message"}}` — produced by the ONE handler `deps.install(app)` registers.

Connections are opened `with closing(sync_conn()) as conn, conn:`, exactly as `app.api.auth` does:
psycopg2's own `with conn:` is the TRANSACTION manager and commits WITHOUT closing, so `closing` is
what actually returns the connection to the pool. A refusal raised inside the block rolls back
everything the request wrote, which is what makes each submission atomic.
"""
from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from app.auth import audit, flags
from app.auth import permissions as PM
from app.auth import sessions as S
from app.auth.deps import AuthError, Unauthenticated, require
from app.cache import sync_redis
from app.db import sync_conn
from app.mail.outbox import enqueue

router = APIRouter(prefix="/api")

# Hoisted to a module-level constant and never wrapped: `tests/auth/test_permissions.py` resolves a
# route's permission by the guard's object IDENTITY (`deps.permission_of`), and the audit drift
# test only watches routes whose permission it can read.
REQUIRE_SELF = require("account.self")
Self = Annotated[S.Principal, Depends(REQUIRE_SELF)]

KINDS = ("buyer", "seller")
BUYER_REQUIRED = ("name", "school_year", "intent")
SELLER_REQUIRED = ("practice_name", "license_state")
ATTESTATION = {"buyer": "affirm", "seller": "ownership_attestation"}
TEMPLATE = {"buyer": "application_received", "seller": "seller_application_received"}
# A `pending`/`needs_review` row is the one under review; anything else is history.
OPEN_STATUSES = ("pending", "needs_review")
# The applicant's path back (John's ruling, 2026-09-07; spec §Lifecycle, amended). The account
# states from which a BUYER application may be opened: `verified` is the first application,
# `declined` is the re-apply. A SELLER application is opened from `active` and is governed by
# `seller.apply` instead — a declined seller may re-apply with no state change at all.
BUYER_APPLY_STATES = ("verified", "declined")
MAX_ANSWER = 4_000
# The three audit actions an applicant's own routes write, in ONE namespace (controller ruling,
# 2026-09-07 — `application.submit`, singular, was renamed while it was still free: Wave 2a has
# never been deployed, so no audit row anywhere carries the old name). Named as constants because
# the answer route also COUNTS its own rows (see `answer`), and a literal in two places would be a
# silent miscount.
SUBMIT_ACTION, ANSWER_ACTION, REAPPLY_ACTION = "applications.submit", "applications.answer", "applications.reapply"
# A closed row's `status` read back as the staff decision that produced it — what the applicant's
# history and the reviewer's detail both show. `admin_users.APPLICATION_STATUS` is the forward map.
DECISION = {"approved": "approve", "declined": "decline", "needs_review": "request_info"}
# `application.fields` is a jsonb column filled from an authenticated request body. Starlette
# imposes no body limit of its own, so these are the limit: enough room for every field the design
# collects (nine, the longest a free-text "intent"), and nowhere near enough to be a way of filling
# the disk one application at a time.
MAX_FIELDS, MAX_FIELDS_BYTES = 40, 16_000


class BadKind(AuthError):
    status = 422
    code = "BAD_KIND"
    message = "kind must be buyer or seller"


class FieldsRequired(AuthError):
    """The one refusal here that names what is wrong: the applicant needs to know which field to
    fill in. Field NAMES only — nothing they submitted is echoed back."""

    status = 422
    code = "FIELDS_REQUIRED"

    def __init__(self, missing: list[str]) -> None:
        self.message = "Required: " + ", ".join(missing)
        super().__init__()


class ApplicationState(AuthError):
    """The applicant's own account state, or an application of theirs already under review. Both
    say the same thing on purpose: this is the caller's own account, so there is nothing to
    disclose, and one message covers "not verified yet" and "already applied" without the UI
    having to reason about which."""

    status = 409
    code = "STATE"
    message = "An application already exists, or this account is not ready to apply."


class NotFound(AuthError):
    """An application that does not exist and one that belongs to somebody else are the SAME 404,
    never a 403: a 403 would confirm the id names a real application, which is exactly the
    enumeration the design's uniform responses exist to prevent."""

    status = 404
    code = "NOT_FOUND"
    message = "No such application."


class AnswerState(AuthError):
    """An answer to a row that is not waiting for one. The row is the caller's own, so naming the
    reason discloses nothing — and the UI needs to tell "already re-submitted" from "declined"."""

    status = 409
    code = "STATE"
    message = "This application is not waiting for an answer."


class NotABuyer(AuthError):
    """Spec §4: `seller.apply` belongs to the `buyer` role alone — selling starts by being an
    approved buyer."""

    code = "FORBIDDEN"
    message = "Only approved buyers may apply to sell."


class ApplicationIn(BaseModel):
    kind: str = Field(max_length=32)
    fields: dict[str, Any]

    @field_validator("fields")
    @classmethod
    def _bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > MAX_FIELDS or len(json.dumps(value)) > MAX_FIELDS_BYTES:
            raise ValueError("fields is too large")
        return value


class AnswerIn(BaseModel):
    answer: str = Field(max_length=MAX_ANSWER)

    @field_validator("answer")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Whitespace is not an answer: staff asked a question, and a blank re-submission would put
        the row back in the queue as though one had been given."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("answer is required")
        return stripped


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _validate(kind: str, fields: dict[str, Any]) -> None:
    required = BUYER_REQUIRED if kind == "buyer" else SELLER_REQUIRED
    missing = [k for k in required if not str(fields.get(k, "")).strip()]
    attestation = ATTESTATION[kind]
    if not fields.get(attestation):
        missing.append(attestation)
    if missing:
        raise FieldsRequired(missing)


@router.post("/applications", status_code=202)
async def submit(body: ApplicationIn, request: Request, principal: Self) -> dict[str, str]:
    """`202`, not `201`: the row exists, but what the applicant is being told is that a human will
    look at it."""
    if body.kind not in KINDS:
        raise BadKind
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            # The applicant's own row is read FIRST, and `state` is taken from it rather than from
            # `principal.state`: the principal comes from a 60 s cache (`sessions.CACHE_TTL`), so a
            # member who verified their address a moment ago would otherwise be told to verify it
            # again. `FOR UPDATE` also serialises this against a second submission of the same
            # application, which is what the duplicate check below relies on.
            cur.execute("SELECT email, state FROM account WHERE id=%s FOR UPDATE", (principal.account_id,))
            row = cur.fetchone()
            if row is None:
                # `deps.LEGACY_ADMIN` — the `API_SECRET_KEY` bearer — passes `account.self` and
                # names no `account` row, so the INSERT below would be a foreign-key violation:
                # a 500 on a credential path. The refusal is the generic anonymous 401.
                raise Unauthenticated
            email, state = cast("str", row[0]), cast("str", row[1])
            # A buyer application opens at `verified` and moves the account to `pending`. A seller
            # application is made from an account that is already `active` with the buyer role and
            # leaves the account exactly where it is — moving it to `pending` would strip every
            # role on the next request (`permissions.effective_roles`).
            if body.kind == "buyer" and state not in BUYER_APPLY_STATES:
                raise ApplicationState
            if body.kind == "seller" and not PM.allowed("seller.apply", principal):
                raise NotABuyer
            # A `declined` buyer applying again is a RE-APPLICATION: a new row, with the declined
            # one kept as history, and the account back to `pending` (John's ruling, 2026-09-07).
            reapplying = body.kind == "buyer" and state == "declined"
            _validate(body.kind, body.fields)
            # One open row per ACCOUNT, not per kind (spec §Lifecycle, amended): `admin_users.decide`
            # acts on "the account's latest open application" whatever its kind, so a second open
            # row of another kind would make a staff decision ambiguous about which row it closed.
            cur.execute("SELECT 1 FROM application WHERE account_id=%s AND status = ANY(%s)",
                        (principal.account_id, list(OPEN_STATUSES)))
            if cur.fetchone() is not None:
                raise ApplicationState
            cur.execute("INSERT INTO application (account_id, kind, fields, flags) VALUES (%s,%s,%s,%s) RETURNING id",
                        (principal.account_id, body.kind, json.dumps(body.fields), flags.compute(body.fields, email)))
            # RETURNING id on a just-inserted row always yields exactly one row.
            app_id = cast("tuple[UUID]", cur.fetchone())[0]
            if body.kind == "buyer":
                cur.execute("UPDATE account SET state='pending', display_name=COALESCE(display_name, %s) WHERE id=%s",
                            (str(body.fields["name"]).strip(), principal.account_id))
                # The cached principal still says `verified`; the account no longer does. Spec §3's
                # S4: a principal cache is DELETED on any change, never waited out.
                S.invalidate_account(sync_redis(), principal.account_id)
        enqueue(conn, to=email, template=TEMPLATE[body.kind], params={},
                idempotency_key=f"{principal.account_id}:{TEMPLATE[body.kind]}:{app_id}")
        audit.write(conn, actor=principal, action=REAPPLY_ACTION if reapplying else SUBMIT_ACTION,
                    target_type="application", target_id=app_id, after={"kind": body.kind}, request=request)
    return {"id": str(app_id), "status": "pending"}


@router.post("/applications/{application_id}/answer")
async def answer(application_id: UUID, body: AnswerIn, request: Request, principal: Self) -> dict[str, str]:
    """The applicant answers the reviewer's `info_request` IN THE APP and re-submits (John's
    ruling, 2026-09-07; spec §Lifecycle, amended). The answer lands on the same row, which goes
    back to `pending`, and `application_received` is queued again under a new cause.

    The screens for this do not exist yet — the V2/V3 designs have no answer field — so until
    John's Rev 3 design lands (Task I8) this path is reachable by API only.
    """
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT email FROM account WHERE id=%s FOR UPDATE", (principal.account_id,))
            row = cur.fetchone()
            if row is None:
                # `deps.LEGACY_ADMIN` — the `API_SECRET_KEY` bearer — passes `account.self` and
                # names no `account` row. Same generic 401 as `submit` gives it.
                raise Unauthenticated
            email = cast("str", row[0])
            # Scoped to the caller's own account in the WHERE clause, so "no such application" and
            # "not yours" are one indistinguishable 404. `FOR UPDATE` serialises two answers to the
            # same row, which is what makes the `needs_review` check below a real gate.
            cur.execute("SELECT kind, status FROM application WHERE id=%s AND account_id=%s FOR UPDATE",
                        (application_id, principal.account_id))
            application = cur.fetchone()
            if application is None:
                raise NotFound
            kind, status = cast("str", application[0]), cast("str", application[1])
            if status != "needs_review":
                raise AnswerState
            cur.execute("""UPDATE application SET answer=%s, answered_at=now(), resubmitted_at=now(), status='pending'
                            WHERE id=%s""", (body.answer, application_id))
            if kind == "buyer":
                # Only a buyer application moves the ACCOUNT, exactly as in `submit`: a seller
                # applies from an `active` account, and demoting it to `pending` would strip every
                # role on the next request (`permissions.effective_roles`).
                cur.execute("UPDATE account SET state='pending' WHERE id=%s", (principal.account_id,))
                S.invalidate_account(sync_redis(), principal.account_id)
            # `n` = which submission of this row this is, for the outbox idempotency cause. The row
            # carries one `resubmitted_at` rather than a counter, so the count comes from the
            # append-only audit trail: one `applications.answer` row per PREVIOUS re-submission,
            # plus one for the original submission and one for this one.
            cur.execute("SELECT count(*) FROM audit_log WHERE target_type='application' AND target_id=%s AND action=%s",
                        (str(application_id), ANSWER_ACTION))
            n = cast("tuple[int]", cur.fetchone())[0] + 2
        template = TEMPLATE[kind]
        enqueue(conn, to=email, template=template, params={},
                idempotency_key=f"{principal.account_id}:{template}:{application_id}:{n}")
        audit.write(conn, actor=principal, action=ANSWER_ACTION, target_type="application",
                    target_id=application_id, before={"status": status}, after={"status": "pending", "kind": kind},
                    request=request)
    return {"status": "pending"}


MINE = """SELECT id, kind, status, info_request, answer, answered_at, resubmitted_at, submitted_at,
                 decision_note, decided_at
            FROM application WHERE account_id=%s ORDER BY submitted_at DESC, id DESC"""


def _mine_row(r: tuple[Any, ...]) -> dict[str, Any]:
    return {"id": str(r[0]), "kind": r[1], "status": r[2], "info_request": r[3], "answer": r[4],
            "answered_at": _iso(r[5]), "resubmitted_at": _iso(r[6]), "submitted_at": r[7].isoformat(),
            "decision": DECISION.get(r[2]), "reason": r[8], "decided_at": _iso(r[9])}


@router.get("/applications/me")
async def mine(principal: Self) -> dict[str, Any]:
    """`current` — the row the applicant can act on — and the `history` behind it.

    `current` is the one open (`pending`/`needs_review`) row, or, when nothing is open, the newest
    row there is; `history` is every OTHER row, newest first, so a row is never in both.
    `info_request` is the reviewer's question when the row is `needs_review`.

    Reshaped in I5c (2026-09-07) from a map keyed by kind: a re-application leaves closed rows
    behind, and the old shape — one entry per kind — had nowhere to put them. `kind` travels on
    each entry instead.
    """
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(MINE, (principal.account_id,))
        rows = [_mine_row(r) for r in cur.fetchall()]
    current = next((r for r in rows if r["status"] in OPEN_STATUSES), rows[0] if rows else None)
    return {"current": current, "history": [r for r in rows if r is not current]}
