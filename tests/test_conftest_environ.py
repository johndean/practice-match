"""The whole-environment isolation `tests/conftest.py` gives every test (Task P8 fix round 1,
CI run 35061796545 on `0174e32`, `tests/test_docs.py`'s Finding 2).

`tests/e2e/api_under_test.py`'s `PIPELINE_DEFAULTS` loop calls `os.environ.setdefault(name,
value)` DIRECTLY on the real process environment (spec 2026-09-09 E, controller amendment
A-IDP-2) — and its own test, `test_it_arms_the_privacy_pipeline_for_this_process_alone`, deletes
both names first with `monkeypatch.delenv(name, raising=False)`, believing that guarantees
teardown restores them. It does not, and the mechanism is pytest's own: `MonkeyPatch.delitem`
(which `delenv` calls) records an undo action only in its `else` branch —

    if name not in dic:
        if raising: raise KeyError(name)
        # else: nothing recorded at all
    else:
        self._setitem.append((dic, name, dic.get(name, NOTSET)))
        del dic[name]

— so calling it on a name that is ALREADY ABSENT with `raising=False` is a complete no-op: no
undo action, no record, nothing. `os.environ.setdefault(...)` immediately afterwards writes
through to the real environment with monkeypatch having tracked none of it, so it survives that
test's teardown for the rest of the pytest PROCESS — pytest collects every file into one process
by default. Confirmed directly (not just reasoned about): running only
`tests/e2e/test_api_under_test.py` in a fresh subprocess and inspecting `os.environ` afterwards
shows both `CELERY_TASK_ALWAYS_EAGER` and `PRIVACY_ENGINE_MODULE` still set.

Any later test in the same run that builds `app.config.Settings(...)` without naming either
setting then inherits them from the environment `Settings` (a `BaseSettings` subclass) falls back
to reading — which is exactly what failed two `tests/test_config.py` tests that construct
`Settings()` with neither in their kwargs, expecting the field defaults (`None` / `False`):
`Settings._test_only_settings_are_test_only` refuses a non-default value on either name outside
`ENVIRONMENT=test`, and CI's random test order put the leak before them.

The fix is `tests/conftest.py::_restore_environ`, an autouse, FUNCTION-scoped fixture (session
scope would only restore once, at the very end of the run — too late to stop test N from
poisoning test N+1) that snapshots the whole real `os.environ` before each test and restores it
byte for byte after, regardless of HOW a test or the code it calls wrote to it — `monkeypatch`,
direct assignment, or `os.environ.setdefault` alike. It closes this leak's exact mechanism and
every other shape the same mechanism could take (a future test file calling code that writes to
`os.environ` directly), rather than papering over these two names alone.

This module runs its two throwaway tests as a subprocess, `tests/conftest.py` loaded as a plugin
exactly as `test_conftest_db.py::test_the_session_that_built_the_template_drops_it` already does
for the same reason: a tmp_path module sits outside `tests/`, so pytest's own conftest discovery
would not find `tests/conftest.py` for it unless told to. `-p no:randomly` fixes this inner run's
test order to declaration order (arm-then-construct) regardless of what order pytest-randomly
would give the OUTER suite — the whole point being that the fix must hold whichever order the
real suite's random collection lands on, which this reproduces deterministically rather than by
chance.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODULE_SOURCE = '''
import os

from tests.e2e import api_under_test

FOUR = {
    "S3_ENDPOINT_URL": "https://s3.amazonaws.com",
    "S3_BUCKET": "pm-e2e",
    "S3_ACCESS_KEY_ID": "test-only-key-id",
    "S3_SECRET_ACCESS_KEY": "test-only-secret",
}
LOOPBACK = {
    "DATABASE_URL": "postgresql://pm:pm_dev_pw@localhost:5433/practice_match",
    "REDIS_URL": "redis://127.0.0.1:6380/0",
}


def test_1_the_pipeline_defaults_arm_with_both_names_absent_beforehand(monkeypatch):
    """`test_it_arms_the_privacy_pipeline_for_this_process_alone`'s own shape: delete both
    PIPELINE_DEFAULTS names first (the leak's precondition -- delenv on an absent name records
    no undo action at all), then arm them through the real `main()`."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    for name, value in {**FOUR, **LOOPBACK}.items():
        monkeypatch.setenv(name, value)
    for name in api_under_test.PIPELINE_DEFAULTS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(api_under_test.uvicorn, "run", lambda *a, **k: None)
    assert api_under_test.main(["--port", "8099"]) == 0
    assert os.environ["CELERY_TASK_ALWAYS_EAGER"] == "1"
    assert os.environ["PRIVACY_ENGINE_MODULE"] == "tests.e2e.stub_engines"


def test_2_a_clean_settings_construction_afterwards_must_not_raise():
    """The exact `tests/test_config.py` shape: neither test-only setting in `Settings()`'s
    kwargs, so both must sit at their safe defaults (None / False) -- which they can only do if
    nothing this process ran before it left them armed in the real environment."""
    from app.config import Settings

    base = {"database_url": "postgresql://x", "redis_url": "redis://x", "api_secret_key": "x"}
    Settings(**base, environment="production")
'''


def test_a_leaked_pipeline_default_does_not_survive_into_the_next_test(tmp_path):
    module = tmp_path / "test_leak_then_clean_construction.py"
    module.write_text(MODULE_SOURCE)

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-c", "pyproject.toml",
         "-p", "no:cacheprovider", "-p", "no:randomly", "-p", "tests.conftest", str(module)],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
