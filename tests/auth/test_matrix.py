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


# --- controller ruling, 2026-09-07 (concern 4): what "the minter holds the role" means ---


def test_permissions_of_reads_the_matrix_the_other_way_round():
    assert PM.permissions_of(frozenset({"admin"})) == {p for p, holders in PM.MATRIX.items() if "admin" in holders}
    assert PM.permissions_of(frozenset()) == frozenset()
    assert PM.permissions_of(frozenset({"buyer", "seller"})) == PM.permissions_of(frozenset({"buyer"})) | PM.permissions_of(frozenset({"seller"}))


def test_a_minter_may_never_mint_a_token_that_administers_more_than_it_does():
    """"Holds the role" is the permission-subset rule, not a `role_grant` row: a token may carry
    role R only when every ADMINISTRATIVE permission R carries is already the minter's. No live
    principal can be refused by it — `tokens.manage` is admin-only and an admin's administrative
    set is the whole of it — so the inputs are constructed here rather than driven through a route.

    The comparison is over `ADMINISTRATIVE` and not over the whole permission set because the
    matrix is not a ladder: `buyer`/`seller` carry `request.create`, `request.read_own`,
    `seller.apply`, `page.seller`, `listing.manage_own` and `request.answer_own`, which NO
    administrator holds — a plain subset test would refuse the `k6-qa`/`e2e-qa`/`deploy-verify`
    tokens the spec names. A buyer token is not more powerful than the admin who minted it."""
    # L3: the expected set spelled out, not the implementation's own expression restated (which
    # would have been true of any matrix). Sixteen rows today — every one of them staff/admin only.
    assert PM.ADMINISTRATIVE == frozenset({
        "abuse.investigate", "audit.read", "data_sources.read", "engine.activate", "licence.decide",
        "listing.publish", "listing.review", "page.admin", "permissions.read", "request.oversee",
        "roles.grant", "tokens.manage", "users.decide", "users.review", "users.revoke", "users.view_detail",
    })
    assert len(PM.ADMINISTRATIVE) == 16
    assert "market.read" not in PM.ADMINISTRATIVE and "request.create" not in PM.ADMINISTRATIVE

    admin, staff = frozenset({"admin"}), frozenset({"staff"})
    for role in MEMBER_ROLES:
        assert PM.may_mint(role, admin) is True, role                 # an admin mints all four...
    assert PM.may_mint("admin", staff) is False                       # ...and nobody mints upward
    assert PM.may_mint("staff", staff) is True
    assert PM.may_mint("buyer", frozenset()) is True                  # a member role administers nothing
    assert PM.may_mint("staff", frozenset({"buyer", "seller"})) is False
    # The rule is a statement about permissions, so it survives a matrix change: `staff` is
    # mintable by `admin` because staff's administrative permissions are a subset of admin's.
    assert PM.permissions_of(staff) & PM.ADMINISTRATIVE <= PM.permissions_of(admin)
    assert not PM.permissions_of(admin) & PM.ADMINISTRATIVE <= PM.permissions_of(staff)


# The `PM.REAUTH` permissions the generated rows cannot see, each with why (L1). `_rows` reads a
# route's DEPENDANT tree, so a guard invoked inside a handler body is invisible to it — the sweep's
# one blind spot, and the reason this list is asserted EXACTLY: an entry that gains a route, or a
# new in-handler guard, fails here instead of quietly leaving the sweep.
REAUTH_OUTSIDE_THE_SWEEP = {
    # `decide_route` calls `REQUIRE_REVOKE(request)` in its body for the `revoke` branch
    # (app/api/admin_users.py). Driven over HTTP, as a token and as a session, by
    # tests/api/test_admin_users.py::test_an_api_token_never_satisfies_a_reauth_gate.
    "users.revoke": "in-handler guard",
    # No route mounts these yet — they arrive with the Map-engines sub-project, and the rows above
    # will pick them up on the commit that adds them.
    "licence.decide": "no route yet",
    "engine.activate": "no route yet",
}


def test_every_reauth_permission_is_either_swept_or_listed_with_its_reason(dist):
    """L1. The file's claim is that a new route or a new REAUTH permission is picked up without
    editing it; that is true only for route-level guards, so the exceptions are named rather than
    silently missing."""
    swept = {perm for _method, _path, perm in _rows(dist)}
    assert set(REAUTH_OUTSIDE_THE_SWEEP) <= PM.REAUTH, "an entry here names no re-auth permission"
    assert PM.REAUTH - swept == set(REAUTH_OUTSIDE_THE_SWEEP), (
        "a REAUTH permission is neither swept by the generated rows nor listed above with its reason")
    assert "tokens.manage" in swept and "roles.grant" in swept
