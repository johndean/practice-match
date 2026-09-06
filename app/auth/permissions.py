"""The permission matrix — the only place roles meet capabilities (spec §4). `python -m app.auth.permissions --ts` prints the TypeScript twin."""
from __future__ import annotations

import json
import sys

from app.auth.sessions import Principal
from app.config import settings

ROLES = ("anonymous", "applicant", "buyer", "seller", "staff", "admin")
_ALL = frozenset(ROLES)
_MEMBERS = frozenset({"buyer", "seller", "staff", "admin"})
_STAFF = frozenset({"staff", "admin"})
_ADMIN = frozenset({"admin"})

MATRIX: dict[str, frozenset[str]] = {
    "page.gate": _ALL,
    "account.self": _ALL - {"anonymous"},
    "page.browse": _MEMBERS, "listing.read": _MEMBERS,
    "market.read": _MEMBERS,                     # + anonymous while MARKET_DATA_PUBLIC (effective_roles)
    "layer.google_live": _MEMBERS, "layer.satellite": _MEMBERS,
    "request.create": frozenset({"buyer", "seller"}), "request.read_own": frozenset({"buyer", "seller"}),
    "seller.apply": frozenset({"buyer"}),
    "page.seller": frozenset({"seller"}), "listing.manage_own": frozenset({"seller"}), "request.answer_own": frozenset({"seller"}),
    "page.admin": _STAFF, "users.review": _STAFF, "users.decide": _STAFF,
    # Split from "users.review" in I5 fix round 1 (John, 2026-09-07). Spec §4 audits "viewing an
    # application DETAIL" — the detail, not the list — and everything in AUDITED writes a row from
    # its own handler, so leaving the LIST audited meant one row per poll of the Admin > Users tab
    # into a table whose triggers refuse DELETE and which has no retention path. Same roles; the
    # difference is only which of the two reads leaves a trace.
    "users.view_detail": _STAFF,
    # Revoke is one branch of the admin Users screen's decide action, split out as its own
    # permission because it — and only it — is in REAUTH (spec §4: "Approve · Decline · Request
    # info · Suspend · Revoke (re-auth for Revoke)"). Fix round 1, Important 1: it was in REAUTH
    # and in no MATRIX row, so `require("users.revoke")` would have raised KeyError at wiring time
    # and the twin's REAUTH list silently omitted it.
    "users.revoke": _STAFF,
    "listing.review": _STAFF, "listing.publish": _STAFF, "request.oversee": _STAFF,
    "abuse.investigate": _ADMIN,
    "data_sources.read": _STAFF,
    "licence.decide": _ADMIN, "engine.activate": _ADMIN, "roles.grant": _ADMIN, "tokens.manage": _ADMIN,
    "audit.read": _STAFF, "permissions.read": _STAFF,
}
REAUTH = frozenset({"licence.decide", "engine.activate", "roles.grant", "tokens.manage", "users.revoke"})
# "users.revoke" joins the list in I3 fix round 1's follow-up (John, 2026-09-06): it is a staff
# decision exactly like "users.decide", which is audited, and I5's decide endpoint writes the audit
# row for its revoke branch. `tests/auth/test_permissions.py` pins both that membership and
# `AUDITED <= set(MATRIX)`, so a name here can no longer drift away from a real permission.
AUDITED = frozenset({"users.view_detail", "users.decide", "users.revoke", "roles.grant", "tokens.manage", "licence.decide", "engine.activate", "abuse.investigate"})
# A token principal's permission set is its ROLE's set minus these (spec §Automation tokens,
# amended 2026-09-07; Task I5b). Automation may now carry `staff` and `admin`, so the containment
# that used to come from "no privileged tokens exist" has to be written down: a leaked admin token
# can neither mint another token nor revoke one. `allowed()` below is the one place it is
# subtracted, which is what `deps.require` — every guarded route — asks (I5b review, L2: the
# earlier wording claimed "every consumer of the matrix", but `GET /api/admin/permissions` reads
# MATRIX/REAUTH/AUDITED directly; it publishes `token_denied` beside them instead). The OTHER half
# of the same rule (a token never satisfies a re-auth gate, which puts Revoke, licence decisions,
# engine activation and role grants out of its reach too) lives in `deps.require`, because it is
# about a request's freshness rather than about the matrix.
# Not exported to the TypeScript twin: the browser only ever holds a session.
TOKEN_DENIED = frozenset({"tokens.manage"})
# (method, path template) for every route that is deliberately reachable without a permission.
# `tests/auth/test_permissions.py::test_every_route_is_guarded_or_public` walks `create_app()` and
# fails on anything here that is neither guarded by `require(...)` nor listed below (spec §4
# Enforcement) — fix round 1, Important 8, which is also why the routes that already shipped are
# spelled out rather than waved through by the test.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/api/healthz"), ("GET", "/api/healthz/deep"), ("GET", "/robots.txt"), ("GET", "/"), ("GET", "/{path:path}"),
    ("POST", "/api/auth/signup"), ("POST", "/api/auth/verify"), ("POST", "/api/auth/signin"),
    ("POST", "/api/auth/password/forgot"), ("POST", "/api/auth/password/reset"), ("POST", "/api/webhooks/resend"),
    # The other half of `scripts/bootstrap_admin.py` (Task I5): the single-use `invite` token IS
    # the credential, so the caller is anonymous by construction — exactly like `password/reset`.
    ("POST", "/api/auth/accept-invite"),
    ("GET", "/_app/{path:path}"),      # the built bundle (StaticFiles), same public surface as "/" and the SPA catch-all
    ("POST", "/api/interest"),         # the Coming Soon launch-notification sign-up: anonymous by design, rate-limited instead
    # `app.api.health.not_found_router`'s catch-all: it exists so an unknown /api/* path answers a
    # JSON 404 instead of falling through to the SPA's index.html. It reads nothing and writes
    # nothing, on any method.
    *((method, "/api/{path:path}") for method in ("DELETE", "GET", "PATCH", "POST", "PUT")),
})


# The permissions no ordinary member can hold — the matrix rows whose holders are staff/admin only.
# Derived, never listed: a permission added to an admin-only row is administrative from that commit,
# with nothing to keep in step by hand.
ADMINISTRATIVE = frozenset(perm for perm, holders in MATRIX.items() if holders <= _STAFF)


def permissions_of(roles: frozenset[str]) -> frozenset[str]:
    """Every permission this set of roles carries — `MATRIX` read the other way round."""
    return frozenset(perm for perm, holders in MATRIX.items() if holders & roles)


def may_mint(role: str, minter_roles: frozenset[str]) -> bool:
    """Whether an account holding `minter_roles` may mint an api token carrying `role`.

    "The minter must hold the role being granted (no escalation)" (spec §Automation tokens) is the
    PERMISSION-SUBSET rule, not a `role_grant` row (controller ruling, 2026-09-07): every
    administrative permission the minted role carries must already be the minter's, so nobody can
    mint a token that administers more than they do. `tokens.manage` is admin-only and an admin's
    administrative set is all of `ADMINISTRATIVE`, so an admin mints any of the four roles without
    granting itself `staff` first — and no principal that can reach `POST /api/admin/tokens` today
    can be refused. The guard is what keeps that true if `tokens.manage` ever widens.

    Compared over `ADMINISTRATIVE` rather than over the whole permission set because the matrix is
    not a ladder: `buyer`/`seller` carry `request.create`, `request.read_own`, `seller.apply`,
    `page.seller`, `listing.manage_own` and `request.answer_own`, which no administrator holds, so
    a plain subset test would refuse the `k6-qa`/`e2e-qa`/`deploy-verify` tokens the spec names. A
    buyer token is not more powerful than the admin who minted it, only different; escalation here
    means administrative reach, and that is exactly what this compares.
    """
    return permissions_of(frozenset({role})) & ADMINISTRATIVE <= permissions_of(minter_roles)


def effective_roles(principal: Principal | None) -> frozenset[str]:
    if principal is None:
        return frozenset({"anonymous"})
    if principal.state != "active":
        return frozenset({"applicant"})
    return frozenset(principal.roles) | {"applicant"} if principal.roles else frozenset({"applicant"})


def allowed(perm: str, principal: Principal | None) -> bool:
    # First, and before `effective_roles` (I5b review, L4): the answer needs neither the roles nor
    # the settings read, and this is the hottest path in the app.
    if principal is not None and principal.kind == "token" and perm in TOKEN_DENIED:
        return False
    roles = effective_roles(principal)
    if perm == "market.read" and settings.market_data_public and "anonymous" in roles:
        return True
    return bool(roles & MATRIX[perm])


def to_typescript() -> str:
    perms = sorted(MATRIX)
    lines = ["// GENERATED by `python -m app.auth.permissions --ts` — do not edit.",
             f"export const ROLES = {json.dumps(list(ROLES))} as const;",
             "export type Role = (typeof ROLES)[number];",
             "export type Permission =\n  " + " |\n  ".join(json.dumps(p) for p in perms) + ";",
             "export const MATRIX: Record<Permission, readonly Role[]> = {"]
    lines += [f"  {json.dumps(p)}: {json.dumps(sorted(MATRIX[p]))}," for p in perms]
    # `sorted(REAUTH)`, not `sorted(REAUTH & set(MATRIX))`: the intersection quietly dropped a
    # REAUTH entry that named no permission instead of failing (Important 1). The invariant is
    # pinned by tests/auth/test_permissions.py::test_every_reauth_permission_is_a_real_permission.
    lines += ["};", f"export const REAUTH: readonly Permission[] = {json.dumps(sorted(REAUTH))};", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    if "--ts" in sys.argv:
        sys.stdout.write(to_typescript())
