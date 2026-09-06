import subprocess
import sys
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


def test_every_permission_is_used_and_typescript_twin_is_current(tmp_path):
    ts = PM.to_typescript()
    assert "export const MATRIX" in ts and '"engine.activate": ["admin"]' in ts and "export type Permission =" in ts
    out = subprocess.run([sys.executable, "-m", "app.auth.permissions", "--ts"], capture_output=True, text=True, check=True).stdout
    assert out == ts
    from pathlib import Path
    twin = Path("frontend/src/auth/permissions.ts")
    assert twin.exists() and twin.read_text() == ts, "run: python -m app.auth.permissions --ts > frontend/src/auth/permissions.ts"


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
