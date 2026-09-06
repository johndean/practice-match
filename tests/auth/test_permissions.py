import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from app.auth import permissions as PM
from app.auth.sessions import Principal


def P(*roles, state="active"):
    return Principal(uuid4(), state, frozenset(roles), None, "session", "h")


def test_matrix_matches_the_spec_table():
    assert PM.MATRIX["page.gate"] == frozenset(PM.ROLES)
    assert PM.MATRIX["market.read"] == frozenset({"buyer", "seller", "staff", "admin"})
    assert PM.MATRIX["seller.apply"] == frozenset({"buyer"})
    assert PM.MATRIX["users.decide"] == frozenset({"staff", "admin"})
    assert PM.MATRIX["engine.activate"] == frozenset({"admin"}) and "engine.activate" in PM.REAUTH
    assert PM.MATRIX["abuse.investigate"] == frozenset({"admin"}) and "abuse.investigate" in PM.AUDITED
    assert {"users.decide", "roles.grant", "tokens.manage", "licence.decide", "users.review"} <= PM.AUDITED
    assert {"licence.decide", "engine.activate", "roles.grant", "tokens.manage"} <= PM.REAUTH


def test_effective_roles_require_an_active_account(monkeypatch):
    from app.config import settings
    assert PM.effective_roles(None) == frozenset({"anonymous"})
    monkeypatch.setattr(settings, "market_data_public", True)
    assert PM.allowed("market.read", None) is True
    monkeypatch.setattr(settings, "market_data_public", False)
    assert PM.allowed("market.read", None) is False
    assert PM.effective_roles(P("buyer", state="suspended")) == frozenset({"applicant"})
    assert PM.allowed("page.browse", P("buyer", state="suspended")) is False
    assert PM.allowed("page.browse", P("buyer")) is True
    assert PM.allowed("engine.activate", P("staff")) is False and PM.allowed("engine.activate", P("admin")) is True


def test_typescript_twin_is_current(tmp_path):
    """Renamed in fix round 1 (Important 8): it only ever checked the twin. "Every permission is
    used by some route" — spec §4's exhaustive test (b) — needs routes that do not exist until
    I4-I6 and is scheduled in I9; `test_every_route_is_guarded_or_public` below is the half that
    can bite today. The twin path is resolved from THIS file, not the CWD (Minor 7): pytest run
    from anywhere still finds it."""
    ts = PM.to_typescript()
    assert "export const MATRIX" in ts and '"engine.activate": ["admin"]' in ts and "export type Permission =" in ts
    out = subprocess.run([sys.executable, "-m", "app.auth.permissions", "--ts"], capture_output=True, text=True, check=True).stdout
    assert out == ts
    twin = Path(__file__).resolve().parents[2] / "frontend" / "src" / "auth" / "permissions.ts"
    assert twin.exists() and twin.read_text() == ts, "run: python -m app.auth.permissions --ts > frontend/src/auth/permissions.ts"


def test_every_reauth_permission_is_a_real_permission():
    """Important 1: `REAUTH` held "users.revoke", `MATRIX` did not, and `to_typescript()` quietly
    filtered the dangling name out with `REAUTH & set(MATRIX)` — so the twin shipped a REAUTH list
    missing the one entry, and `require("users.revoke")` would have raised KeyError at wiring time.
    The filter is gone; this is what keeps the two in step."""
    assert PM.REAUTH <= set(PM.MATRIX)
    assert PM.MATRIX["users.revoke"] == frozenset({"staff", "admin"})


# --- supplemental (not in the brief's Step 1 — added for 100% branch coverage) ---
# The subprocess call above proves the real `python -m app.auth.permissions --ts` entry point
# works, but a child process's coverage is never reported back to this one, so the module's own
# `if __name__ == "__main__":` guard and its nested `if "--ts" in sys.argv:` would otherwise show
# as never executed. `runpy.run_path(..., run_name="__main__")` re-execs the module's file IN this
# process (so pytest-cov sees it) with `__name__` actually set to "__main__", closing both
# branches without touching the given implementation. `run_path` (not `run_module`) on purpose:
# `run_module` on an already-imported dotted submodule name raises a RuntimeWarning ("found in
# sys.modules... prior to execution"), which `-W error` (the CI gate) turns into a failure.


def test_cli_entrypoint_prints_the_ts_twin_when_run_as___main__(monkeypatch, capsys):
    import runpy
    monkeypatch.setattr(sys, "argv", ["app.auth.permissions", "--ts"])
    runpy.run_path(PM.__file__, run_name="__main__")
    assert capsys.readouterr().out == PM.to_typescript()


def test_cli_entrypoint_prints_nothing_without_the_flag(monkeypatch, capsys):
    import runpy
    monkeypatch.setattr(sys, "argv", ["app.auth.permissions"])
    runpy.run_path(PM.__file__, run_name="__main__")
    assert capsys.readouterr().out == ""


# --- fix round 1, Important 8: PUBLIC_ROUTES and AUDITED get the consumers spec §4 promised ---


def _walk(routes, prefix=""):
    """(method, path, route) for everything mounted, spelled the way PUBLIC_ROUTES spells it — the
    raw path template (`/{path:path}`), not the compiled `path_format` (`/{path}`). FastAPI 0.141
    keeps an included router as a wrapper object rather than flattening its routes, so the walk
    recurses through `original_router` and carries the include prefix; a StaticFiles mount serves
    GET beneath its own prefix and has no methods of its own."""
    from starlette.routing import Mount

    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _walk(included.routes, prefix + route.include_context.prefix)
        elif isinstance(route, Mount):
            yield "GET", prefix + route.path + "/{path:path}", None
        else:
            for method in sorted(route.methods):
                yield method, prefix + route.path, route


def _permissions_of(route):
    """Every permission `require(...)` guards this route with, sub-dependencies included. A route
    with no FastAPI dependant at all (a Mount, or a plain Starlette route) guards nothing."""
    from app.auth.deps import permission_of

    def _walk_dependant(dependant):
        for dep in dependant.dependencies:
            perm = permission_of(dep.call)
            if perm is not None:
                yield perm
            yield from _walk_dependant(dep)

    dependant = getattr(route, "dependant", None)
    return list(_walk_dependant(dependant)) if dependant is not None else []


def test_every_route_is_guarded_or_public(dist):
    """Spec §4 Enforcement — "undeclared routes fail a test unless in PUBLIC_ROUTES" — and the
    plan's exhaustive test (a). Important 8: `PUBLIC_ROUTES` had no consumer anywhere in `app/` or
    in any brief I0-I10, so the classic auth fail-open (an I5/I6 endpoint added without its
    `Depends(require(...))`) had nothing watching for it. This is that watcher; it passes today
    because every route create_app() mounts is genuinely public, and starts earning its keep in I4."""
    from app.main import create_app

    undeclared = [
        (method, path)
        for method, path, route in _walk(create_app(dist=dist).routes)
        if not any(p in PM.MATRIX for p in _permissions_of(route))
        and (method, path) not in PM.PUBLIC_ROUTES
    ]
    assert undeclared == [], "add a require(...) dependency, or list these in permissions.PUBLIC_ROUTES"
    # ...and the OTHER half of the check is live too: a route that carries `require(...)` is
    # accepted without being listed, which is how every I4-I6 endpoint will pass.
    from fastapi import Depends, FastAPI

    from app.auth.deps import require

    guarded = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @guarded.get("/api/admin/anything", dependencies=[Depends(require("page.admin"))])
    async def _guarded_endpoint() -> dict[str, bool]:
        return {"ok": True}

    assert [(m, p) for m, p, r in _walk(guarded.routes) if not any(x in PM.MATRIX for x in _permissions_of(r))] == []


def test_audited_permissions_are_written_by_their_handlers(dist):
    """Spec §4 says `require` writes the audit row for AUDITED permissions; the plan has each
    handler write a richer one by hand, which means adding a permission to `AUDITED` audits
    nothing on its own (Important 8). This is what makes the list binding: a route guarded by an
    audited permission whose handler never calls `audit.write` fails here. Trivially true today —
    no route uses `require` until I4."""
    import inspect

    from app.main import create_app

    unaudited = [
        (method, path)
        for method, path, route in _walk(create_app(dist=dist).routes)
        if any(p in PM.AUDITED for p in _permissions_of(route))
        and "audit.write(" not in inspect.getsource(route.endpoint)
    ]
    assert unaudited == [], "an audited permission guards this route but its handler writes no audit row"
