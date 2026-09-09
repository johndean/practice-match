"""`tests/e2e/api_under_test.py` — the api web server the Playwright `app` project starts (controller
amendment A-SL28, on the round-4 NEEDS_CONTEXT).

It exists so that `listing-flows.spec.ts`'s photograph runs LOCALLY and in CI against a real
upload route: the route refuses every write with `503 STORAGE_UNAVAILABLE` until all four `S3_*`
settings are present, no local or CI environment has a bucket, and `moto[s3]` — pytest's own S3
double — is already a dev dependency. The launcher starts `mock_aws()` in the api's own process,
creates the bucket, then serves uvicorn exactly as `frontend/tests/targets.ts`'s command used to.

Test-only by construction, and these cases are the pin: it refuses anywhere but `ENVIRONMENT=test`,
refuses without the four settings, refuses an endpoint moto would not intercept (A-SL16 M4 — moto
matches the request URL, so a Railway-shaped host escapes to the network), and never starts a
server on a refusal. `uvicorn.run` is monkeypatched throughout: nothing here binds a port.
"""
from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto.core.models import botocore_stubber

from tests.e2e import api_under_test

FOUR = {
    "S3_ENDPOINT_URL": "https://s3.amazonaws.com",
    "S3_BUCKET": "pm-e2e",
    "S3_ACCESS_KEY_ID": "test-only-key-id",
    "S3_SECRET_ACCESS_KEY": "test-only-secret",
}


@pytest.fixture
def server(monkeypatch: Any) -> list[dict[str, Any]]:
    """`uvicorn.run`, recorded rather than run. While it is "running", the api's own process holds
    the moto bucket — so each call records what a request would have found there."""
    calls: list[dict[str, Any]] = []

    def fake_run(app: str, **kwargs: Any) -> None:
        s3 = boto3.client("s3", region_name="us-east-1")
        calls.append({"app": app, "buckets": [b["Name"] for b in s3.list_buckets()["Buckets"]],
                      "intercepting": botocore_stubber.enabled, **kwargs})

    monkeypatch.setattr(api_under_test.uvicorn, "run", fake_run)
    return calls


@pytest.fixture
def test_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    for name, value in FOUR.items():
        monkeypatch.setenv(name, value)


def test_it_creates_the_bucket_in_its_own_process_and_serves_the_app_on_the_port(server: Any, test_env: None, capsys: Any) -> None:
    assert api_under_test.main(["--port", "8099"]) == 0
    # While the server runs, moto intercepts every botocore call in this process and the bucket
    # `S3_BUCKET` names is there to answer them — so `ObjectStore.from_settings` finds a store.
    assert server == [{"app": "app.main:app", "port": 8099, "buckets": ["pm-e2e"], "intercepting": True}]
    # Nothing but the one start line: a credential may be in the environment.
    assert capsys.readouterr().err.strip().splitlines() == ["[api_under_test] moto bucket pm-e2e ready; serving app.main:app on port 8099"]


def test_the_mock_lives_exactly_as_long_as_the_server(server: Any, test_env: None) -> None:
    """After `main` returns, botocore is no longer intercepted — the mock's own switch, not a
    network call, is the proof (the fixture recorded it ON during the serve)."""
    assert botocore_stubber.enabled is False
    assert api_under_test.main(["--port", "8099"]) == 0
    assert server[0]["intercepting"] is True
    assert botocore_stubber.enabled is False


@pytest.mark.parametrize("environment", ["qa", "production", "Test", "test ", "", None])
def test_it_refuses_anywhere_but_the_test_environment(server: Any, test_env: None, monkeypatch: Any, capsys: Any, environment: str | None) -> None:
    if environment is None:
        monkeypatch.delenv("ENVIRONMENT")
    else:
        monkeypatch.setenv("ENVIRONMENT", environment)
    assert api_under_test.main(["--port", "8099"]) != 0
    assert server == [], "a refusal must never start the server"
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "ENVIRONMENT" in err and "test" in err


@pytest.mark.parametrize("missing", sorted(FOUR))
def test_it_refuses_without_every_one_of_the_four_s3_settings(server: Any, test_env: None, monkeypatch: Any, capsys: Any, missing: str) -> None:
    monkeypatch.delenv(missing)
    assert api_under_test.main(["--port", "8099"]) != 0
    assert server == []
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and missing in err


def test_an_empty_setting_counts_as_missing(server: Any, test_env: None, monkeypatch: Any) -> None:
    monkeypatch.setenv("S3_BUCKET", "")
    assert api_under_test.main(["--port", "8099"]) != 0
    assert server == []


@pytest.mark.parametrize("endpoint", ["https://bucket.up.railway.app", "http://localhost:9000", "https://s3.amazonaws.com.evil.example"])
def test_it_refuses_an_endpoint_moto_would_not_intercept(server: Any, test_env: None, monkeypatch: Any, capsys: Any, endpoint: str) -> None:
    """A-SL16 M4: moto matches the request URL. Any other host would make the api under test call
    the network with the dummy credentials — a test suite that can talk to the internet is not one."""
    monkeypatch.setenv("S3_ENDPOINT_URL", endpoint)
    assert api_under_test.main(["--port", "8099"]) != 0
    assert server == []
    assert "amazonaws.com" in capsys.readouterr().err


def test_the_port_is_required(server: Any, test_env: None) -> None:
    with pytest.raises(SystemExit) as exc:
        api_under_test.main([])
    assert exc.value.code == 2
    assert server == []


def test_the_cli_entry_point_runs_as___main__(server: Any, test_env: None, monkeypatch: Any) -> None:
    """`python -m tests.e2e.api_under_test --port N` is what `targets.ts` runs; the module's own
    `__main__` guard hands `main()`'s code to `SystemExit`. Run with a refusing environment so
    no server is even asked for — and by path, as `tests/test_reset_rate_limits.py` does, because
    `run_module` on an already-imported module raises the sys.modules `RuntimeWarning` that
    `-W error` turns into a failure."""
    monkeypatch.setenv("ENVIRONMENT", "qa")
    monkeypatch.setattr("sys.argv", ["api_under_test", "--port", "8099"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path(api_under_test.__file__)), run_name="__main__")
    assert exc.value.code != 0
    assert server == []
