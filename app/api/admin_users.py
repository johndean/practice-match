"""The Admin > Users surface (spec §4/§6): the review queue, the five staff decisions, role grants,
automation api tokens, and the two read endpoints the admin screens are built on.

**John's binding condition (2026-09-06).** `GET /api/admin/users` returns accounts of EVERY state
and EVERY role — Staff and Admin rows too, including the bootstrap-created admins and the caller's
own account — each with its `roles[]` and, per grant, `granted_by` and `granted_at`; it accepts a
`role=` filter alongside `state=` and `kind=`. No role is hidden from the list. There is no separate
"SuperAdmin" application role: Admin is the top role (it alone grants roles, and every grant is
re-authenticated and audited), and the Postgres superuser is a database credential that never
appears in the app.

Two shapes here are load-bearing and easy to undo by accident:

* **Every guard is a module-level constant, never wrapped.** `tests/auth/test_permissions.py`
  resolves a route's permission by the guard's object IDENTITY (`deps.permission_of`); a wrapper
  around one reads as "guarded but unresolvable", which those tests treat as an error rather than
  quietly dropping the route from the audit watch list.
* **`audit.write(` is called in each audited endpoint's OWN body,** never through a helper: the
  drift test reads `inspect.getsource(route.endpoint)`, so delegating the write to `decide()` would
  make every one of these routes read as unaudited.
"""
from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast
from uuid import UUID

import psycopg2.extensions
import redis as redis_sync
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.auth import audit
from app.auth import permissions as PM
from app.auth import sessions as S
from app.auth import tokens as T
from app.auth.deps import AuthError, Unauthenticated, require
from app.cache import sync_redis
from app.db import sync_conn
from app.mail.outbox import enqueue

router = APIRouter(prefix="/api/admin")

REQUIRE_REVIEW = require("users.review")
REQUIRE_DECIDE = require("users.decide")
REQUIRE_REVOKE = require("users.revoke")      # in REAUTH: the one decision that needs a fresh password
REQUIRE_GRANT = require("roles.grant")
REQUIRE_TOKENS = require("tokens.manage")
REQUIRE_AUDIT = require("audit.read")
REQUIRE_PERMISSIONS = require("permissions.read")

Reviewer = Annotated[S.Principal, Depends(REQUIRE_REVIEW)]
Decider = Annotated[S.Principal, Depends(REQUIRE_DECIDE)]
Granter = Annotated[S.Principal, Depends(REQUIRE_GRANT)]
TokenManager = Annotated[S.Principal, Depends(REQUIRE_TOKENS)]
AuditReader = Annotated[S.Principal, Depends(REQUIRE_AUDIT)]

GRANTABLE_ROLES = ("buyer", "seller", "staff", "admin")
OPEN_STATUSES = ("pending", "needs_review")
APPLICATION_ACTIONS = ("approve", "decline", "request_info")
NOTE_REQUIRED = ("decline", "request_info", "suspend", "revoke")
# The decision table (spec §4). `revoke` is reachable from every state but `revoked` itself.
EVERY_STATE = ("unverified", "verified", "pending", "needs_review", "declined", "active", "suspended")
TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "approve": (frozenset({"pending", "needs_review"}), "active"),
    "decline": (frozenset({"pending", "needs_review"}), "declined"),
    "request_info": (frozenset({"pending"}), "needs_review"),
    "suspend": (frozenset({"active"}), "suspended"),
    "reinstate": (frozenset({"suspended"}), "active"),
    "revoke": (frozenset(EVERY_STATE), "revoked"),
}
APPLICATION_STATUS = {"approve": "approved", "decline": "declined", "request_info": "needs_review"}
# Suspend and revoke are ACCOUNT actions, so they carry no seller variant; `request_info` has no
# seller template of its own (one "we need more from you" mail serves both), which is why this is a
# table rather than string surgery on the buyer template name.
EMAIL = {
    ("buyer", "approve"): "application_approved",
    ("buyer", "decline"): "application_declined",
    ("seller", "approve"): "seller_application_approved",
    ("seller", "decline"): "seller_application_declined",
    ("buyer", "request_info"): "application_info_requested",
    ("seller", "request_info"): "application_info_requested",
    ("buyer", "suspend"): "account_suspended",
    ("seller", "suspend"): "account_suspended",
    ("buyer", "revoke"): "account_revoked",
    ("seller", "revoke"): "account_revoked",
}
# `revoke` also ends every session, which is what makes a suspension visible on the NEXT request:
# `invalidate_account` alone drops the principal cache and the cookie still resolves.
ENDS_EVERY_SESSION = ("suspend", "revoke")
MAX_LIST, MAX_AUDIT, MAX_TOKEN_DAYS = 200, 500, 90
MAX_NAME, MAX_NOTE, MAX_REASON = 120, 4_000, 4_000


class NotFound(AuthError):
    status = 404
    code = "NOT_FOUND"
    message = "No such account."


class BadAction(AuthError):
    status = 422
    code = "BAD_ACTION"
    message = f"action must be one of {', '.join(sorted(TRANSITIONS))}"


class NoteRequired(AuthError):
    status = 422
    code = "NOTE_REQUIRED"
    message = "A note is required for this decision."


class BadRole(AuthError):
    status = 422
    code = "BAD_ROLE"
    message = f"role must be one of {', '.join(GRANTABLE_ROLES)}"


class BadCursor(AuthError):
    status = 422
    code = "BAD_CURSOR"
    message = "cursor must be an ISO 8601 timestamp from a previous page."


class StateConflict(AuthError):
    status = 409
    code = "STATE"

    def __init__(self, action: str, state: str) -> None:
        self.message = f"cannot {action} an account in state {state}"
        super().__init__()


class Decision(BaseModel):
    action: str = Field(max_length=32)
    note: str = Field(default="", max_length=MAX_NOTE)


class GrantIn(BaseModel):
    role: str = Field(max_length=32)
    grant: bool
    reason: str = Field(max_length=MAX_REASON)


class TokenIn(BaseModel):
    name: str = Field(max_length=MAX_NAME)
    role: str = Field(max_length=32)
    days: int = MAX_TOKEN_DAYS


def _roles(cur: Any, account_id: UUID) -> list[str]:
    cur.execute("SELECT role FROM role_grant WHERE account_id=%s AND revoked_at IS NULL ORDER BY role", (account_id,))
    return [r[0] for r in cur.fetchall()]


def _grants(cur: Any, account_id: UUID) -> list[dict[str, str]]:
    """Every live grant with WHO made it and WHEN — John's condition, and the only way the Admin >
    Users tab can show an admin how another admin came to be one."""
    cur.execute("""SELECT role, granted_by::text, granted_at FROM role_grant
                    WHERE account_id=%s AND revoked_at IS NULL ORDER BY role""", (account_id,))
    return [{"role": r[0], "granted_by": r[1], "granted_at": r[2].isoformat()} for r in cur.fetchall()]


def _actor_account(conn: psycopg2.extensions.connection, actor: S.Principal) -> UUID:
    """The actor's own `account.id`, or the generic 401.

    `role_grant.granted_by`, `application.decided_by` and `api_token.created_by` are foreign keys,
    and `deps.LEGACY_ADMIN` — the synthetic id the `API_SECRET_KEY` bearer resolves to, alive until
    Task I9 — names no `account` row. Without this the operator bearer's grant is an integrity
    error: a 500 on a credential path, and an unattributable write if the constraint ever went."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM account WHERE id=%s", (actor.account_id,))
        row = cur.fetchone()
    if row is None:
        raise Unauthenticated
    return cast("UUID", row[0])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _cursor(value: str) -> str:
    """`created_at` as the next page's cursor, URL-SAFE: an ISO offset of `+00:00` arrives back as
    a space, because `+` in a query string decodes to one, and the refusal that follows would look
    like a bug in whatever built the link. `Z` is the same instant, survives the round trip, and is
    what `datetime.fromisoformat` and Postgres both accept on the way in."""
    return datetime.fromisoformat(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


LIST_SQL = """
SELECT a.id, a.email, a.state, a.display_name, a.affiliation_label, a.created_at, a.last_sign_in_at,
       ap.id, ap.kind, ap.fields, ap.flags, ap.status, ap.submitted_at,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('role', g.role, 'granted_by', g.granted_by, 'granted_at', g.granted_at)
                                  ORDER BY g.role)
                   FROM role_grant g WHERE g.account_id = a.id AND g.revoked_at IS NULL), '[]'::jsonb)
  FROM account a
  LEFT JOIN LATERAL (SELECT * FROM application WHERE account_id = a.id ORDER BY submitted_at DESC LIMIT 1) ap ON true
 WHERE (%(state)s::text IS NULL OR a.state = %(state)s)
   AND (%(kind)s::text IS NULL OR ap.kind = %(kind)s)
   AND (%(role)s::text IS NULL OR EXISTS (SELECT 1 FROM role_grant g
                                           WHERE g.account_id = a.id AND g.role = %(role)s AND g.revoked_at IS NULL))
   AND (%(cursor)s::timestamptz IS NULL OR a.created_at < %(cursor)s::timestamptz)
 ORDER BY a.created_at DESC, a.id DESC
 LIMIT %(limit)s
"""


@router.get("/users")
async def list_users(
    request: Request,
    principal: Reviewer,
    state: str | None = None,
    kind: str | None = None,
    role: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Every account, in every state and every role — the caller's own included (John, 2026-09-06).

    `state=`, `kind=` and `role=` narrow it; `cursor=` is the previous page's last `created_at`.
    Accounts created in the same microsecond would straddle a page boundary; nothing here writes
    two accounts in one transaction, so that is a theoretical edge rather than a live one, and it
    is recorded rather than papered over with a composite cursor the Admin tab has no use for."""
    if cursor is not None:
        try:
            datetime.fromisoformat(cursor)
        except ValueError:
            raise BadCursor from None
    capped = min(max(limit, 1), MAX_LIST)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute(LIST_SQL, {"state": state, "kind": kind, "role": role, "cursor": cursor, "limit": capped + 1})
            rows = cur.fetchall()
        items = [
            {"account_id": str(r[0]), "email": r[1], "state": r[2], "name": r[3], "affiliation_label": r[4],
             "created_at": r[5].isoformat(), "last_sign_in_at": _iso(r[6]),
             "application_id": str(r[7]) if r[7] is not None else None, "kind": r[8], "fields": r[9],
             "flags": r[10] or [], "application_status": r[11], "submitted_at": _iso(r[12]),
             "roles": [g["role"] for g in r[13]], "grants": r[13]}
            for r in rows[:capped]
        ]
        # `users.review` is in `permissions.AUDITED`: reading the queue is itself a recorded act,
        # because the queue is other people's applications.
        audit.write(conn, actor=principal, action="users.list", target_type="account",
                    after={"state": state, "kind": kind, "role": role, "returned": len(items)}, request=request)
    return {"items": items, "next_cursor": _cursor(cast("str", items[-1]["created_at"])) if len(rows) > capped else None}


@router.get("/users/{account_id}")
async def detail(account_id: UUID, request: Request, principal: Reviewer) -> dict[str, Any]:
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email, state, display_name, affiliation_label, created_at, last_sign_in_at FROM account WHERE id=%s", (account_id,))
            account = cur.fetchone()
            if account is None:
                raise NotFound
            cur.execute("""SELECT id, kind, fields, flags, status, submitted_at, decided_at, decision_note, info_request
                             FROM application WHERE account_id=%s ORDER BY submitted_at DESC""", (account_id,))
            applications = [
                {"id": str(r[0]), "kind": r[1], "fields": r[2], "flags": r[3], "status": r[4],
                 "submitted_at": _iso(r[5]), "decided_at": _iso(r[6]), "decision_note": r[7], "info_request": r[8]}
                for r in cur.fetchall()
            ]
            grants = _grants(cur, account_id)
        audit.write(conn, actor=principal, action="users.view", target_type="account", target_id=account_id, request=request)
    return {
        "account": {"id": str(account[0]), "email": account[1], "state": account[2], "name": account[3],
                    "affiliation_label": account[4], "created_at": account[5].isoformat(), "last_sign_in_at": _iso(account[6])},
        "applications": applications,
        "roles": [g["role"] for g in grants],
        "grants": grants,
    }


def decide(
    conn: psycopg2.extensions.connection,
    r: redis_sync.Redis,
    *,
    actor: S.Principal,
    account_id: UUID,
    action: str,
    note: str,
) -> tuple[str, list[str]]:
    """One staff decision, applied: spec §4's transition table, the role grant or revocation it
    implies, the application row it closes, the mail it queues and the sessions it ends. Returns
    the account's new `(state, roles)`.

    It does NOT write the audit row. The brief's Step 3 had it do so; the controller's ruling
    (2026-09-06) is that `audit.write(` must appear in each audited ENDPOINT's own source, because
    that is what `tests/auth/test_permissions.py::test_audited_permissions_are_written_by_their_handlers`
    reads — so `decide_route` writes it, and the `request` parameter the brief's signature carried
    (only ever the audit row's source of ip/ua/request-id) went with it."""
    if action not in TRANSITIONS:
        raise BadAction
    if action in NOTE_REQUIRED and not note.strip():
        raise NoteRequired
    allowed_from, to = TRANSITIONS[action]
    actor_account = _actor_account(conn, actor)
    with conn.cursor() as cur:
        cur.execute("SELECT state, email FROM account WHERE id=%s FOR UPDATE", (account_id,))
        row = cur.fetchone()
        if row is None:
            raise NotFound
        state, email = row
        cur.execute("""SELECT id, kind FROM application WHERE account_id=%s AND status = ANY(%s)
                        ORDER BY submitted_at DESC LIMIT 1""", (account_id, list(OPEN_STATUSES)))
        application = cur.fetchone()
        kind = application[1] if application is not None else "buyer"
        if kind == "seller" and action in APPLICATION_ACTIONS:
            # A seller applies from an account that is ALREADY `active`. The application has a
            # state machine; the account does not move with it — demoting an approved buyer to
            # `pending` would strip every role on their next request.
            allowed_from, to = frozenset({"active"}), "active"
        if state not in allowed_from:
            raise StateConflict(action, state)
        if action == "approve":
            cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                        (account_id, kind, actor_account))
        if action == "revoke":
            cur.execute("UPDATE role_grant SET revoked_at=now() WHERE account_id=%s AND revoked_at IS NULL", (account_id,))
        if application is not None and action in APPLICATION_ACTIONS:
            cur.execute("""UPDATE application SET status=%s, decided_by=%s, decided_at=now(), decision_note=%s, info_request=%s
                            WHERE id=%s""",
                        (APPLICATION_STATUS[action], actor_account, note if action != "request_info" else None,
                         note if action == "request_info" else None, application[0]))
        cur.execute("UPDATE account SET state=%s WHERE id=%s", (to, account_id))
        roles = _roles(cur, account_id)
    template = EMAIL.get((kind, action))
    if template is not None:
        enqueue(conn, to=email, template=template, params={"note": note},
                idempotency_key=f"{account_id}:{template}:{application[0] if application is not None else action}")
    if action in ENDS_EVERY_SESSION:
        # `revoke_all`, not `invalidate_account`: dropping the principal cache alone leaves the
        # cookie resolving to a live session, so the suspended member gets a 403 on the routes
        # their (now empty) roles no longer reach instead of the generic 401 spec §3 asks for.
        S.revoke_all(conn, r, account_id)
    else:
        S.invalidate_account(r, account_id)
    return to, roles


@router.post("/users/{account_id}/decide")
async def decide_route(account_id: UUID, body: Decision, request: Request, principal: Decider) -> dict[str, Any]:
    if body.action == "revoke":
        # Spec §4: "Approve · Decline · Request info · Suspend · Revoke (re-auth for Revoke)".
        # `users.revoke` is in REAUTH and in AUDITED; calling the hoisted guard re-runs the whole
        # check — principal, Origin/CSRF, matrix, freshness — for the one branch that needs it.
        REQUIRE_REVOKE(request)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state FROM account WHERE id=%s FOR UPDATE", (account_id,))
            row = cur.fetchone()
        # `decide` refuses a missing account itself; this placeholder only ever survives to the
        # audit row's `before` if that stops being true.
        before = row[0] if row is not None else ""
        state, roles = decide(conn, sync_redis(), actor=principal, account_id=account_id, action=body.action, note=body.note)
        audit.write(conn, actor=principal, action="users.revoke" if body.action == "revoke" else "users.decide",
                    target_type="account", target_id=account_id, before={"state": before},
                    after={"state": state, "roles": roles},
                    # Free text, and a staff member's own words — never a credential (controller
                    # ruling, 2026-09-06). `audit.write` redacts secret-shaped keys in
                    # before/after; `reason` is not redacted, so nothing but the decision and the
                    # reviewer's note goes in it.
                    reason=body.action if not body.note.strip() else f"{body.action}: {body.note}", request=request)
    return {"state": state, "roles": roles}


@router.post("/users/{account_id}/grants")
async def grants(account_id: UUID, body: GrantIn, request: Request, principal: Granter) -> dict[str, list[str]]:
    """`roles.grant` is `admin` only and in REAUTH: every grant — Staff and Admin included — is
    made by a named admin who has just re-entered their password, and is audited with the roles
    before and after."""
    if body.role not in GRANTABLE_ROLES:
        raise BadRole
    with closing(sync_conn()) as conn, conn:
        actor_account = _actor_account(conn, principal)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM account WHERE id=%s FOR UPDATE", (account_id,))
            if cur.fetchone() is None:
                raise NotFound
            before = _roles(cur, account_id)
            if body.grant:
                cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                            (account_id, body.role, actor_account))
            else:
                cur.execute("UPDATE role_grant SET revoked_at=now() WHERE account_id=%s AND role=%s AND revoked_at IS NULL",
                            (account_id, body.role))
            roles = _roles(cur, account_id)
        S.invalidate_account(sync_redis(), account_id)
        audit.write(conn, actor=principal, action="roles.grant", target_type="account", target_id=account_id,
                    before={"roles": before}, after={"roles": roles}, reason=body.reason, request=request)
    return {"roles": roles}


@router.post("/tokens", status_code=201)
async def create_token(body: TokenIn, request: Request, principal: TokenManager) -> dict[str, str]:
    """Minted once and shown once: only the SHA-256 is stored (`app.auth.tokens`), so a token that
    is not copied out of this response is gone. The audit row records the token's id, name, role
    and lifetime — never the secret half."""
    if body.role not in GRANTABLE_ROLES:
        raise BadRole
    days = min(max(body.days, 1), MAX_TOKEN_DAYS)
    with closing(sync_conn()) as conn, conn:
        actor_account = _actor_account(conn, principal)
        raw = T.issue_api_token(conn, name=body.name, role=body.role, created_by=actor_account, ttl=timedelta(days=days))
        # `pm_<uuid>.<secret>` — the id half only. Sliced rather than parsed so there is no
        # "impossible" None branch on a value this line has just minted.
        token_id = raw.split(".", 1)[0][3:]
        audit.write(conn, actor=principal, action="tokens.create", target_type="api_token", target_id=token_id,
                    after={"name": body.name, "role": body.role, "days": days}, request=request)
    return {"token": raw}


@router.post("/tokens/{token_id}/revoke")
async def revoke_token(token_id: UUID, request: Request, principal: TokenManager) -> dict[str, str]:
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("UPDATE api_token SET revoked_at=now() WHERE id=%s AND revoked_at IS NULL RETURNING id", (token_id,))
        if cur.fetchone() is None:
            raise NotFound
        audit.write(conn, actor=principal, action="tokens.revoke", target_type="api_token", target_id=token_id, request=request)
    return {"status": "revoked"}


@router.get("/audit")
async def audit_read(principal: AuditReader, limit: int = 100) -> list[dict[str, Any]]:
    """The trail, newest first. `audit_log` is append-only by trigger (migrations/014), so this is
    the only way to read it short of psql — and it is deliberately not itself audited: a read that
    writes a row would make the tail of the trail nothing but reads of the trail."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("""SELECT id, at, actor_id::text, actor_role, action, target_type, target_id, before, after, reason
                         FROM audit_log ORDER BY id DESC LIMIT %s""", (min(max(limit, 1), MAX_AUDIT),))
        return [{"id": r[0], "at": r[1].isoformat(), "actor_id": r[2], "actor_role": r[3], "action": r[4],
                 "target_type": r[5], "target_id": r[6], "before": r[7], "after": r[8], "reason": r[9]}
                for r in cur.fetchall()]


@router.get("/permissions", dependencies=[Depends(REQUIRE_PERMISSIONS)])
async def permissions_read() -> dict[str, Any]:
    """The matrix as the API itself holds it — what the admin Permissions view renders, and the
    check that the TypeScript twin (`python -m app.auth.permissions --ts`) has not drifted from
    the running server."""
    return {"roles": list(PM.ROLES), "matrix": {k: sorted(v) for k, v in sorted(PM.MATRIX.items())},
            "reauth": sorted(PM.REAUTH), "audited": sorted(PM.AUDITED)}
