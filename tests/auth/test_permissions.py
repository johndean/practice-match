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


def test_typescript_twin_is_current(tmp_path, monkeypatch):
    """Renamed in fix round 1 (Important 8): it only ever checked the twin. "Every permission is
    used by some route" — spec §4's exhaustive test (b) — needs routes that do not exist until
    I4-I6 and is scheduled in I9; `test_every_route_is_guarded_or_public` below is the half that
    can bite today.

    Nothing here depends on the CWD (Minor 7, completed in fix round 2 / NEW-4): the twin path is
    resolved from THIS file, and the child process gets an explicit `cwd` too — without it
    `python -m app.auth.permissions` resolves the `app` package from wherever pytest happened to be
    started and dies with a CalledProcessError. `monkeypatch.chdir(tmp_path)` proves it."""
    monkeypatch.chdir(tmp_path)
    repo = Path(__file__).resolve().parents[2]
    ts = PM.to_typescript()
    assert "export const MATRIX" in ts and '"engine.activate": ["admin"]' in ts and "export type Permission =" in ts
    out = subprocess.run([sys.executable, "-m", "app.auth.permissions", "--ts"], capture_output=True, text=True, check=True, cwd=repo).stdout
    assert out == ts
    twin = repo / "frontend" / "src" / "auth" / "permissions.ts"
    assert twin.exists() and twin.read_text() == ts, "run: python -m app.auth.permissions --ts > frontend/src/auth/permissions.ts"


def test_every_reauth_and_audited_permission_is_a_real_permission():
    """Important 1: `REAUTH` held "users.revoke", `MATRIX` did not, and `to_typescript()` quietly
    filtered the dangling name out with `REAUTH & set(MATRIX)` — so the twin shipped a REAUTH list
    missing the one entry, and `require("users.revoke")` would have raised KeyError at wiring time.
    The filter is gone; this is what keeps the three lists in step, `AUDITED` included (nothing
    filtered that one either — it was simply never checked).

    Follow-up (John, 2026-09-06): `users.revoke` is audited as well as re-authenticated. It is a
    staff decision exactly like `users.decide`, which is audited; I5's decide endpoint writes the
    audit row for the revoke branch, and `test_audited_permissions_are_written_by_their_handlers`
    below is what will hold it to that."""
    assert PM.REAUTH <= set(PM.MATRIX)
    assert PM.AUDITED <= set(PM.MATRIX)
    assert PM.MATRIX["users.revoke"] == frozenset({"staff", "admin"})
    assert "users.revoke" in PM.REAUTH
    assert "users.revoke" in PM.AUDITED


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
    recurses through `original_router` and carries the include prefix.

    A `Mount` is recursed into when the mounted app exposes routes of its own (fix round 2
    observation): `Mount.routes` is `getattr(self.app, "routes", [])`, so a StaticFiles mount
    yields nothing and falls through to the GET-only line — while a mounted sub-application's
    write routes are SEEN by the guard test instead of being invisible to it."""
    from starlette.routing import Mount

    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _walk(included.routes, prefix + route.include_context.prefix)
        elif isinstance(route, Mount):
            if route.routes:
                yield from _walk(route.routes, prefix + route.path)
            else:
                yield "GET", prefix + route.path + "/{path:path}", None
        else:
            for method in sorted(route.methods):
                yield method, prefix + route.path, route


def _came_from_require(call):
    """True for `require()`'s own closure AND for anything wrapping it. Matched on where the
    callable was defined, because `functools.wraps` copies `__module__`/`__qualname__` onto the
    wrapper — so this still recognises a guard whose `__wrapped__` chain has been broken, which is
    precisely the case the drift tests must treat as an error rather than as "no guard here"
    (fix round 2, NEW-5)."""
    return getattr(call, "__module__", None) == "app.auth.deps" and getattr(call, "__qualname__", "").startswith("require.")


def _guards_of(route):
    """(callable, permission or None) for every `require(...)` guard on the route, sub-dependencies
    included. A `None` permission means "this came from `require` and we cannot read which one" —
    never "there is no guard"."""
    from app.auth.deps import permission_of

    def _walk_dependant(dependant):
        for dep in dependant.dependencies:
            perm = permission_of(dep.call)
            if perm is not None or _came_from_require(dep.call):
                yield dep.call, perm
            yield from _walk_dependant(dep)

    dependant = getattr(route, "dependant", None)
    return list(_walk_dependant(dependant)) if dependant is not None else []


def _permissions_of(route):
    return [perm for _, perm in _guards_of(route) if perm is not None]


def _unguarded(app):
    """(method, path) for every route that neither carries a readable `require(...)` guard nor is
    listed in `PUBLIC_ROUTES`."""
    return [(method, path) for method, path, route in _walk(app.routes)
            if not any(perm in PM.MATRIX for perm in _permissions_of(route)) and (method, path) not in PM.PUBLIC_ROUTES]


def _unresolvable(app):
    """(method, path) for every route carrying something that came from `require(...)` whose
    permission cannot be read back."""
    return [(method, path) for method, path, route in _walk(app.routes) for _, perm in _guards_of(route) if perm is None]


def _unaudited(app):
    """(method, path) for every route guarded by an AUDITED permission whose handler's source never
    calls `audit.write(`."""
    import inspect

    return [(method, path) for method, path, route in _walk(app.routes)
            if any(perm in PM.AUDITED for perm in _permissions_of(route)) and "audit.write(" not in inspect.getsource(route.endpoint)]


def test_every_route_is_guarded_or_public(dist):
    """Spec §4 Enforcement — "undeclared routes fail a test unless in PUBLIC_ROUTES" — and the
    plan's exhaustive test (a). Important 8: `PUBLIC_ROUTES` had no consumer anywhere in `app/` or
    in any brief I0-I10, so the classic auth fail-open (an I5/I6 endpoint added without its
    `Depends(require(...))`) had nothing watching for it. This is that watcher; it passes today
    because every route create_app() mounts is genuinely public, and starts earning its keep in I4."""
    from app.main import create_app

    assert _unguarded(create_app(dist=dist)) == [], "add a require(...) dependency, or list these in permissions.PUBLIC_ROUTES"
    # ...and the OTHER half of the check is live too: a route that carries `require(...)` is
    # accepted without being listed, which is how every I4-I6 endpoint will pass.
    from fastapi import Depends, FastAPI

    from app.auth.deps import require

    guarded = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @guarded.get("/api/admin/anything", dependencies=[Depends(require("page.admin"))])
    async def _guarded_endpoint() -> dict[str, bool]:
        return {"ok": True}

    assert _unguarded(guarded) == []


def test_a_mounted_sub_application_is_walked_rather_than_assumed_static(dist):
    """Fix round 2 observation: every `Mount` was treated as a GET-only StaticFiles mount, so a
    later task mounting a sub-application with write routes would have hidden them from the guard
    test entirely. `/_app` (StaticFiles, no routes of its own) still reads as one public GET."""
    from fastapi import FastAPI
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles

    from app.main import create_app

    assert ("GET", "/_app/{path:path}") in [(m, p) for m, p, _ in _walk(create_app(dist=dist).routes)]

    inner = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @inner.post("/danger")
    async def _danger() -> dict[str, bool]:
        return {"ok": True}

    host = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    host.router.routes.append(Mount("/api/sub", app=inner))
    host.router.routes.append(Mount("/files", app=StaticFiles(directory=str(dist))))
    seen = [(m, p) for m, p, _ in _walk(host.routes)]
    assert ("POST", "/api/sub/danger") in seen
    assert ("GET", "/files/{path:path}") in seen
    # Neither is in PUBLIC_ROUTES, so both are reported — the point being that the POST inside the
    # mounted app is reported at all.
    assert sorted(_unguarded(host)) == [("GET", "/files/{path:path}"), ("POST", "/api/sub/danger")]


def test_audited_permissions_are_written_by_their_handlers(dist):
    """Spec §4 says `require` writes the audit row for AUDITED permissions; the plan has each
    handler write a richer one by hand, which means adding a permission to `AUDITED` audits
    nothing on its own (Important 8). This is what makes the list binding: a route guarded by an
    audited permission whose handler never calls `audit.write` fails here. Trivially true today —
    no route uses `require` until I4.

    It also fails CLOSED (fix round 2, NEW-5): a route carrying something that came from `require`
    whose permission cannot be read back is an ERROR here, not a route quietly dropped from the
    watch list."""
    from app.main import create_app

    app = create_app(dist=dist)
    assert _unresolvable(app) == [], "a require(...) guard on this route cannot be resolved to a permission — do not wrap require(...); hoist it to a module-level constant"
    assert _unaudited(app) == [], "an audited permission guards this route but its handler writes no audit row"


# --- fix round 2, NEW-5: a re-wrapped `require` guard must stay readable, and must be an ERROR
# when it is not ---


def _require_and_wrapper():
    """A `require(...)` dependency and a `functools.wraps` wrapper around it — the shape I5 would
    produce by decorating a guard (to add a log line, or to narrow the return type for mypy)."""
    import functools

    from app.auth.deps import require

    guard = require("users.decide")

    @functools.wraps(guard)
    def wrapped(request):
        return guard(request)

    return guard, wrapped


def test_permission_of_follows_the_wrapped_chain():
    """`permission_of` is keyed by object identity, so any re-wrapping loses the entry. That fails
    CLOSED for the route-guard test (the route reads as unguarded and it shouts) but fails OPEN for
    the audit drift test, which simply stops watching a route it cannot read. Following
    `__wrapped__` is the first half of the fix; `test_audited_permissions_are_written_by_their_handlers`
    failing closed is the second."""
    from app.auth.deps import permission_of

    guard, wrapped = _require_and_wrapper()
    assert permission_of(guard) == "users.decide"
    assert permission_of(wrapped) == "users.decide"
    assert permission_of(lambda request: None) is None


def test_a_broken_guard_wrapper_is_an_error_not_a_silently_unwatched_route(conn, dist):
    """NEW-5, the second half. `permission_of` now follows `__wrapped__`, so a `functools.wraps`
    wrapper around a guard stays readable and both drift tests keep working. But a wrapper that
    breaks that chain (a hand-rolled one, or `del wrapper.__wrapped__`) must not read as "no guard
    here" — for the route-guard test that already failed closed, for the AUDIT test it failed OPEN:
    the route quietly dropped off the watch list and its handler could then lose its `audit.write`
    with a green suite. `_came_from_require` matches on where the callable was defined, which
    `functools.wraps` copies onto the wrapper, so the guard is still recognised even when its
    permission cannot be read."""
    from fastapi import Depends, FastAPI

    from app.auth import audit

    guard, wrapped = _require_and_wrapper()
    scratch = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @scratch.post("/api/admin/users/decide", dependencies=[Depends(wrapped)])
    async def decide() -> dict[str, bool]:
        audit.write(conn, actor=None, action="users.decide", target_type="account")
        return {"ok": True}

    # Readable through the wrapper: guarded, resolvable, and its handler audits.
    assert _unguarded(scratch) == [] and _unresolvable(scratch) == [] and _unaudited(scratch) == []
    assert _permissions_of(next(r for m, p, r in _walk(scratch.routes) if p == "/api/admin/users/decide")) == ["users.decide"]

    del wrapped.__wrapped__  # the chain is gone; the marker `functools.wraps` copied is not
    assert _unresolvable(scratch) == [("POST", "/api/admin/users/decide")]
    assert _unguarded(scratch) == [("POST", "/api/admin/users/decide")]
    assert guard is not wrapped
