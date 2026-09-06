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
            if body.kind == "buyer" and state != "verified":
                raise ApplicationState
            if body.kind == "seller" and not PM.allowed("seller.apply", principal):
                raise NotABuyer
            _validate(body.kind, body.fields)
            cur.execute("SELECT 1 FROM application WHERE account_id=%s AND kind=%s AND status = ANY(%s)",
                        (principal.account_id, body.kind, list(OPEN_STATUSES)))
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
        audit.write(conn, actor=principal, action="application.submit", target_type="application",
                    target_id=app_id, after={"kind": body.kind}, request=request)
    return {"id": str(app_id), "status": "pending"}


@router.get("/applications/me")
async def mine(principal: Self) -> dict[str, Any]:
    """The latest application per kind — what the applicant's own "Application status" screen
    reads. `info_request` is the reviewer's question when the row is `needs_review`."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (kind) kind, status, info_request, submitted_at
                         FROM application WHERE account_id=%s ORDER BY kind, submitted_at DESC""", (principal.account_id,))
        return {r[0]: {"status": r[1], "info_request": r[2], "submitted_at": r[3].isoformat()} for r in cur.fetchall()}
