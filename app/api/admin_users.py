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
* **`users.review` LISTS and `users.view_detail` VIEWS,** and only the second is in `AUDITED`
  (fix round 1, C2 — spec §4 audits "viewing an application detail"). Auditing the list wrote one
  row per poll of the I7 Users tab into a table whose triggers refuse DELETE.

One ordering is deliberate and worth stating rather than discovering (fix round 1, N3): inside
`decide` the Redis work (`S.revoke_all` / `S.invalidate_account`) and the outbox `enqueue` both run
BEFORE `decide_route`'s `audit.write`. A failure in the audit insert therefore rolls back the
Postgres side — the decision, the grants, the outbox row — while the Redis session keys stay
deleted. That is the fail-safe direction (the sessions end, the decision does not) and it is the
one place in the app where the two stores can diverge, so the order stays as it is.
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
REQUIRE_VIEW_DETAIL = require("users.view_detail")
REQUIRE_DECIDE = require("users.decide")
REQUIRE_REVOKE = require("users.revoke")      # in REAUTH: the one decision that needs a fresh password
REQUIRE_GRANT = require("roles.grant")
REQUIRE_TOKENS = require("tokens.manage")
REQUIRE_AUDIT = require("audit.read")
REQUIRE_PERMISSIONS = require("permissions.read")

# (No `Reviewer` alias: `list_users` carries `REQUIRE_REVIEW` as a route-level dependency rather
# than a handler parameter, so an alias for it would be dead — and ruff does not flag an unused
# module-level assignment, so nothing else would catch it. Fix round 2, NEW-2.)
DetailViewer = Annotated[S.Principal, Depends(REQUIRE_VIEW_DETAIL)]
Decider = Annotated[S.Principal, Depends(REQUIRE_DECIDE)]
Granter = Annotated[S.Principal, Depends(REQUIRE_GRANT)]
TokenManager = Annotated[S.Principal, Depends(REQUIRE_TOKENS)]
AuditReader = Annotated[S.Principal, Depends(REQUIRE_AUDIT)]

GRANTABLE_ROLES = ("buyer", "seller", "staff", "admin")
# What an api token may carry (fix round 1, F6 — John, 2026-09-07). A token is a <=90-day bearer
# credential with no session and no CSRF, and `deps.require` only enforces re-auth freshness for
# `kind == "session"`, so a `staff`/`admin` token would be a standing exemption from re-auth for
# every permission outside REAUTH. Automation gets member roles; administration keeps its sessions.
TOKEN_ROLES = ("buyer", "seller")
# The roles that make a target too privileged for a non-admin actor to touch (F1).
PRIVILEGED_ROLES = frozenset({"staff", "admin"})
# The two decisions nobody may aim at their own account (F2).
SELF_FORBIDDEN_ACTIONS = ("suspend", "revoke")
# The transaction-scoped advisory lock every removal of an `admin` grant takes before counting the
# survivors (fix round 2, NEW-1). ASCII 'PMAG' — Practice Match Admin Grants — in the same shape as
# `scripts/migrate.py`'s LOCK_KEY ('PMMG'), and deliberately a different value.
ADMIN_GRANT_LOCK = 0x504D4147
# `account.state`'s CHECK constraint (migrations/010) — the enum `state=` is validated against.
ACCOUNT_STATES = ("unverified", "verified", "pending", "needs_review", "declined", "active", "suspended", "revoked")
APPLICATION_KINDS = ("buyer", "seller")
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


class BadTokenRole(AuthError):
    status = 422
    code = "BAD_ROLE"
    message = f"an api token may only carry {' or '.join(TOKEN_ROLES)} — administration keeps its sessions"


class BadCursor(AuthError):
    status = 422
    code = "BAD_CURSOR"
    message = "cursor must be a `<timestamp>|<id>` value from a previous page's next_cursor."


class BadFilter(AuthError):
    """A `state=`/`kind=`/`role=` outside its enum. It used to answer `200 {"items": []}`, so a
    typo in the Admin Users tab read as "no such users" rather than "no such filter" — and
    inconsistently with this handler's own `cursor=` and with `grants`/`tokens` (fix round 1, F10)."""

    status = 422
    code = "BAD_FILTER"

    def __init__(self, name: str, allowed: tuple[str, ...]) -> None:
        self.message = f"{name} must be one of {', '.join(allowed)}"
        super().__init__()


class PrivilegedTarget(AuthError):
    """Spec §4 makes `users.decide` and `users.revoke` `{staff, admin}` alike, so without this any
    staff account could revoke every admin in a loop — and `revoke` is terminal in the API, leaving
    recovery to `bootstrap_admin.py` with production database credentials (fix round 1, F1)."""

    code = "PRIVILEGED_TARGET"
    message = "Only an admin may act on a staff or admin account."


class SelfAction(AuthError):
    """A one-request self-lockout of an administrative account (fix round 1, F2)."""

    code = "SELF_ACTION"
    message = "You cannot suspend or revoke your own account."


class LastAdmin(AuthError):
    """`roles.grant` is admin-only, so zero admins is a state with no way back inside the app
    (fix round 1, F5)."""

    code = "LAST_ADMIN"
    message = "An admin grant cannot be removed from its own holder, or from the last admin."


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


def _refuse_unsafe_target(
    cur: Any,
    *,
    actor: S.Principal,
    actor_account: UUID,
    account_id: UUID,
    self_forbidden: bool,
    removing_admin: bool,
) -> None:
    """The one place `decide` and `grants` agree on who may be acted upon (fix round 1, F1/F2/F5).

    Three rules, all of them refusals BEFORE any write, all with decision A5's body:

    1. **A non-admin actor may not act on a `staff` or `admin` target.** Staff is the least
       privileged administrative role and could otherwise unseat the most privileged one.
    2. **Nobody may suspend or revoke themselves.** Not an escalation — a one-request lockout.
    3. **An `admin` grant is never removed from its own holder, nor when it is the last live one.**

    `removing_admin` says the OPERATION removes admin grants — `grants` with `grant=false` on
    `admin`, or `decide`'s `revoke`, which strips every grant the target holds. Rule 3 then applies
    only when the target actually holds `admin`: it is a floor under the admin population, not a
    restriction on `revoke`, and reading it the other way would refuse a lone staff member revoking
    an ordinary applicant.

    **Rule 3 serialises (fix round 2, NEW-1).** The count was read with no lock over `role_grant`,
    while each caller locks only its own TARGET account row — so two admins ungranting or revoking
    *each other* locked different rows, both saw `count = 2`, and both committed: zero live admins,
    the exact state this rule exists to prevent, with recovery meaning `bootstrap_admin.py` and
    production database credentials. `pg_advisory_xact_lock` is held for the rest of the
    transaction, so the second caller waits, then re-reads `count = 1` and is refused. It is taken
    only on the path that removes an admin grant, so ordinary decisions and grants never queue
    behind it; adding an admin needs no lock, because it can only raise the count. Deadlock-free:
    it is a single lock taken after the per-row locks, so no two transactions can hold what the
    other wants.

    Rule 3's two halves are one expression on purpose. The second half cannot be reached over HTTP
    in a single request — `roles.grant` is admin-only, so any actor who gets here holds a live admin
    grant of their own and the count can never be 1 for a target that is not them — so a separate
    branch for it could never be exercised. It is what the concurrent case above resolves to, and
    what makes the invariant hold if `roles.grant` is ever widened; it is exercised directly by
    `tests/api/test_admin_users.py::test_the_last_admin_guard_does_not_depend_on_the_actor_being_the_admin_removed`
    and concurrently by the two `..._cannot_reach_zero` tests beside it.
    """
    if self_forbidden and account_id == actor_account:
        raise SelfAction
    target_roles = set(_roles(cur, account_id))
    if "admin" not in actor.roles and PRIVILEGED_ROLES & target_roles:
        raise PrivilegedTarget
    if removing_admin and "admin" in target_roles:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADMIN_GRANT_LOCK,))
        cur.execute("SELECT count(*) FROM role_grant WHERE role='admin' AND revoked_at IS NULL")
        if account_id == actor_account or cast("tuple[int]", cur.fetchone())[0] <= 1:
            raise LastAdmin


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


CURSOR_SEPARATOR = "|"


def _cursor(created_at: str, account_id: str) -> str:
    """The next page's KEYSET cursor, `"<created_at>|<id>"` (fix round 1, F3).

    It carries the id as well as the timestamp because the sort does: with `created_at` alone and
    the predicate `created_at < cursor`, every row sharing the last row's timestamp was DROPPED and
    the caller was then handed `next_cursor: null` — told the list was complete. Probed on the
    shipped code: 3 of 6 accounts returned. `now()` is TRANSACTION time, so any bulk import or
    fixture loader makes ties routine, and silent omission contradicts John's binding condition
    outright.

    URL-safe: an ISO offset of `+00:00` arrives back as a space, because `+` in a query string
    decodes to one. `Z` is the same instant, survives the round trip, and is what both
    `datetime.fromisoformat` and Postgres accept on the way in."""
    return f"{datetime.fromisoformat(created_at).astimezone(UTC).isoformat().replace('+00:00', 'Z')}{CURSOR_SEPARATOR}{account_id}"


def _keyset(cursor: str | None) -> tuple[str | None, UUID | None]:
    """`cursor` split back into `(created_at, id)`, or `(None, None)` for the first page. Anything
    that is not a `<timestamp>|<uuid>` pair is a 422 — never a `DataError`-shaped 500 out of an
    attacker-supplied query string."""
    if cursor is None:
        return None, None
    at, separator, raw_id = cursor.partition(CURSOR_SEPARATOR)
    if not separator:
        raise BadCursor
    try:
        datetime.fromisoformat(at)
        return at, UUID(raw_id)
    except ValueError:
        raise BadCursor from None


def _filter(name: str, value: str | None, allowed: tuple[str, ...]) -> str | None:
    if value is not None and value not in allowed:
        raise BadFilter(name, allowed)
    return value


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
   AND (%(cursor_at)s::timestamptz IS NULL
        OR (a.created_at, a.id) < (%(cursor_at)s::timestamptz, %(cursor_id)s::uuid))
 ORDER BY a.created_at DESC, a.id DESC
 LIMIT %(limit)s
"""


@router.get("/users", dependencies=[Depends(REQUIRE_REVIEW)])
async def list_users(
    state: str | None = None,
    kind: str | None = None,
    role: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Every account, in every state and every role — the caller's own included (John, 2026-09-06).

    `state=`, `kind=` and `role=` narrow it, each validated against its own enum; `cursor=` is the
    previous page's `next_cursor`, a `(created_at, id)` keyset that walks tied timestamps without
    dropping a row (fix round 1, F3).

    Guarded by `users.review` and NOT audited (fix round 1, C2): spec §4 audits viewing an
    application DETAIL, which is `users.view_detail` on the route below."""
    keyset_at, keyset_id = _keyset(cursor)
    filters = {"state": _filter("state", state, ACCOUNT_STATES),
               "kind": _filter("kind", kind, APPLICATION_KINDS),
               "role": _filter("role", role, GRANTABLE_ROLES)}
    capped = min(max(limit, 1), MAX_LIST)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute(LIST_SQL, {**filters, "cursor_at": keyset_at, "cursor_id": keyset_id, "limit": capped + 1})
            rows = cur.fetchall()
        items = [
            {"account_id": str(r[0]), "email": r[1], "state": r[2], "name": r[3], "affiliation_label": r[4],
             "created_at": r[5].isoformat(), "last_sign_in_at": _iso(r[6]),
             "application_id": str(r[7]) if r[7] is not None else None, "kind": r[8], "fields": r[9],
             "flags": r[10] or [], "application_status": r[11], "submitted_at": _iso(r[12]),
             "roles": [g["role"] for g in r[13]], "grants": r[13]}
            for r in rows[:capped]
        ]
    last = items[-1] if len(rows) > capped else None
    return {"items": items,
            "next_cursor": _cursor(cast("str", last["created_at"]), cast("str", last["account_id"])) if last is not None else None}


@router.get("/users/{account_id}")
async def detail(account_id: UUID, request: Request, principal: DetailViewer) -> dict[str, Any]:
    """Spec §4: viewing an application detail is audited — this is the read that leaves a row."""
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
        # Before the application lookup and before every INSERT/UPDATE below: a refusal here
        # leaves the target row exactly as it was (fix round 1, F1/F2).
        #
        # `revoke` strips EVERY grant the target holds, so it removes an admin grant whenever the
        # target has one — and takes rule 3's lock and count with it (fix round 2, NEW-1). Without
        # that, two admins revoking each other concurrently reached zero admins by exactly the
        # route the re-review demonstrated for `grants`.
        _refuse_unsafe_target(cur, actor=actor, actor_account=actor_account, account_id=account_id,
                              self_forbidden=action in SELF_FORBIDDEN_ACTIONS, removing_admin=action == "revoke")
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
    before and after.

    Removing an `admin` grant is the one direction with a floor under it (fix round 1, F5): never
    from its own holder, and never the last live one — `roles.grant` is admin-only, so zero admins
    is a state with no way back short of `bootstrap_admin.py` and database credentials."""
    if body.role not in GRANTABLE_ROLES:
        raise BadRole
    with closing(sync_conn()) as conn, conn:
        actor_account = _actor_account(conn, principal)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM account WHERE id=%s FOR UPDATE", (account_id,))
            if cur.fetchone() is None:
                raise NotFound
            _refuse_unsafe_target(cur, actor=principal, actor_account=actor_account, account_id=account_id,
                                  self_forbidden=False, removing_admin=not body.grant and body.role == "admin")
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
    and lifetime — never the secret half.

    `buyer` or `seller` only (fix round 1, F6): see `TOKEN_ROLES`."""
    if body.role not in TOKEN_ROLES:
        raise BadTokenRole
    days = min(max(body.days, 1), MAX_TOKEN_DAYS)
    with closing(sync_conn()) as conn, conn:
        actor_account = _actor_account(conn, principal)
        issued = T.issue_api_token(conn, name=body.name, role=body.role, created_by=actor_account, ttl=timedelta(days=days))
        # The id comes back from the mint (fix round 1, N5) rather than being sliced back out of
        # `raw`, which hard-coded the `pm_` prefix length in a second place. Only the id — never
        # the secret half — reaches a table whose triggers refuse DELETE.
        audit.write(conn, actor=principal, action="tokens.create", target_type="api_token", target_id=issued.token_id,
                    after={"name": body.name, "role": body.role, "days": days}, request=request)
    return {"token": issued.raw}


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
