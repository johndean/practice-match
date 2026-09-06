"""Task I5b — the role-by-endpoint matrix, run twice per row: once as a session principal and once
as an api-token principal of the SAME role (John's ruling, 2026-09-07: automation tokens carry any
of the four roles).

The rows are generated from the running app, not typed out: every route `create_app()` mounts that
carries a readable `require(...)` guard, crossed with the four member roles and the two principal
kinds. The contract is "identical, with two exceptions", so that is exactly what is asserted — a
token's outcome is compared against the SESSION's outcome for the same row, and only

  * a `tokens.manage` route (`permissions.TOKEN_DENIED`: the token never holds it), and
  * a re-auth-gated route the session may use (`permissions.REAUTH`: the token can never be fresh)

may differ, each with its own 403 message. A new route, or a new permission in either set, is
picked up here without editing this file; a new EXCEPTION is not, which is the point.

`deps.current_principal` is the seam: it resolves a cookie/bearer into a `Principal`, and that
resolution is already covered by `tests/auth/test_deps.py` (a real `pm_<id>.<secret>` bearer, out
of Postgres) and by `tests/api/test_admin_users.py` (over HTTP, end to end). What this file pins is
the decision the guard makes once the principal exists — every route, every role, both kinds — so
it needs no database and no Redis to say something about all of them at once.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from starlette.requests import Request

from app.auth import deps
from app.auth import permissions as PM
from app.auth import sessions as S
from tests.auth.test_permissions import _permissions_of, _walk

MEMBER_ROLES = ("buyer", "seller", "staff", "admin")
ORIGIN = "https://qa.foundation.vin"
PASS = (200, None, None)


def _rows(dist):
    """(method, path, permission) for every guarded route the app mounts, deduplicated and sorted."""
    from app.main import create_app

    return sorted({(method, path, perm) for method, path, route in _walk(create_app(dist=dist).routes)
                   for perm in _permissions_of(route) if perm in PM.MATRIX})


def _request(method: str, path: str) -> Request:
    """A request that satisfies everything the guard checks BESIDES the principal: a matching
    Origin, and the CSRF double-submit a cookie session needs on a state change (a token principal
    is exempt from both, which is what makes the two kinds comparable here)."""
    return Request({"type": "http", "method": method, "path": path, "raw_path": path.encode(), "query_string": b"",
                    "root_path": "", "scheme": "https", "server": ("qa.foundation.vin", 443), "client": ("198.51.100.7", 1),
                    "headers": [(b"host", b"qa.foundation.vin"), (b"origin", ORIGIN.encode()),
                                (b"x-csrf-token", b"t"), (b"cookie", b"pm_csrf=t")]})


def _principal(role: str, kind: str) -> S.Principal:
    """An active member of one role. The session confirmed its password a moment ago, so a re-auth
    gate is the one thing it does NOT fail on; the token has no `reauth_at` to confirm, ever."""
    return S.Principal(uuid4(), "active", frozenset({role}), datetime.now(UTC) if kind == "session" else None,
                       kind, "h" if kind == "session" else None)


def _outcome(monkeypatch, perm: str, method: str, path: str, principal: S.Principal) -> tuple[int, str | None, str | None]:
    monkeypatch.setattr(deps, "current_principal", lambda request: principal)
    try:
        deps.require(perm)(_request(method, path))
    except deps.AuthError as exc:
        return exc.status_code, exc.detail["error"]["code"], exc.detail["error"]["message"]
    return PASS


def _expected_token(perm: str, session: tuple[int, str | None, str | None]) -> tuple[int, str | None, str | None]:
    if perm in PM.TOKEN_DENIED:
        return 403, "TOKEN_SCOPE", deps.TOKENS_MANAGE_MESSAGE
    if session == PASS and perm in PM.REAUTH:
        return 403, "REAUTH_TOKEN", deps.REAUTH_TOKEN_MESSAGE
    return session


def test_every_guarded_route_answers_a_token_principal_as_it_answers_its_session(dist, monkeypatch):
    drifted, exceptions = [], {"reauth": 0, "tokens": 0, "identical_and_allowed": 0}
    for method, path, perm in _rows(dist):
        for role in MEMBER_ROLES:
            session = _outcome(monkeypatch, perm, method, path, _principal(role, "session"))
            token = _outcome(monkeypatch, perm, method, path, _principal(role, "token"))
            expected = _expected_token(perm, session)
            if token != expected:
                drifted.append(f"{method} {path} ({perm}) as {role}: token answered {token}, expected {expected}")
            elif token != session:
                exceptions["tokens" if perm in PM.TOKEN_DENIED else "reauth"] += 1
            elif token == PASS:
                exceptions["identical_and_allowed"] += 1
    assert drifted == [], drifted
    # ...and the comparison is not vacuous: both exceptions really fire, and most rows really are
    # identical (a matrix that refused every token would satisfy the loop above just as well).
    assert exceptions["tokens"] and exceptions["reauth"] and exceptions["identical_and_allowed"]


def test_the_matrix_covers_the_privileged_routes_this_task_opened_tokens_to(dist):
    """The generated rows are only as good as what they contain: a staff/admin token is now
    possible, so the routes it could reach have to BE in the matrix above."""
    rows = {(method, path): perm for method, path, perm in _rows(dist)}
    assert rows[("POST", "/api/admin/tokens")] == "tokens.manage"
    assert rows[("POST", "/api/admin/users/{account_id}/grants")] == "roles.grant"
    assert rows[("GET", "/api/admin/users")] == "users.review"
    assert rows[("GET", "/api/admin/audit")] == "audit.read"


def test_a_token_principal_holds_its_roles_permissions_minus_tokens_manage():
    """The structural half, in the matrix itself rather than through a route: `allowed()` is what
    `require` asks, and it subtracts `TOKEN_DENIED` from a token principal of any role. The
    escalation case the brief names — a principal holding `tokens.manage` WITHOUT the role it is
    minting — cannot arise from the matrix either: `tokens.manage` is admin-only."""
    assert PM.TOKEN_DENIED == frozenset({"tokens.manage"})
    assert PM.MATRIX["tokens.manage"] == frozenset({"admin"}) and "staff" not in PM.MATRIX["tokens.manage"]
    for role in MEMBER_ROLES:
        session, token = _principal(role, "session"), _principal(role, "token")
        assert PM.allowed("tokens.manage", token) is False, role
        for perm in PM.MATRIX:
            if perm not in PM.TOKEN_DENIED:
                assert PM.allowed(perm, token) == PM.allowed(perm, session), (role, perm)
