import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _run_import_without(*missing: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in missing}
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run([sys.executable, "-c", "import app.config"], env=env, capture_output=True, text=True, check=False)


def test_missing_required_variable_exits_1_and_names_it():
    r = _run_import_without("DATABASE_URL")
    assert r.returncode == 1
    assert "DATABASE_URL" in r.stderr


def test_all_required_present_imports_cleanly():
    r = _run_import_without()
    assert r.returncode == 0, r.stderr


def test_origins_split_and_trimmed(monkeypatch):
    from app.config import Settings
    s = Settings(database_url="postgresql://x", redis_url="redis://x", environment="test",
                 api_secret_key="x", allowed_origins=" https://foundation.vin, https://qa.foundation.vin ")
    assert s.origins == ["https://foundation.vin", "https://qa.foundation.vin"]


def test_site_mode_defaults_to_app_and_rejects_unknown_values():
    from pydantic import ValidationError

    from app.config import Settings
    base = {"database_url": "postgresql://x", "redis_url": "redis://x", "environment": "test", "api_secret_key": "x"}
    assert Settings(**base).site_mode == "app"
    assert Settings(**base, site_mode="coming_soon").site_mode == "coming_soon"
    with pytest.raises(ValidationError):
        Settings(**base, site_mode="marketplace")


def test_invalid_site_mode_exits_1_and_names_it():
    env = dict(os.environ, SITE_MODE="marketplace", PYTHONPATH=str(ROOT))
    r = subprocess.run([sys.executable, "-c", "import app.config"], env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 1
    assert "SITE_MODE" in r.stderr


def test_qa_never_runs_coming_soon_mode():
    from pydantic import ValidationError

    from app.config import Settings
    base = {"database_url": "postgresql://x", "redis_url": "redis://x", "api_secret_key": "x"}
    with pytest.raises(ValidationError):
        Settings(**base, environment="qa", site_mode="coming_soon")
    with pytest.raises(ValidationError):
        Settings(**base, environment="QA", site_mode="coming_soon")  # M-6: the guard is case-insensitive
    assert Settings(**base, environment="production", site_mode="coming_soon").site_mode == "coming_soon"
    assert Settings(**base, environment="test", site_mode="coming_soon").site_mode == "coming_soon"


def test_load_settings_exits_1_in_process_and_names_the_variables(monkeypatch, capsys):
    from app.config import load_settings
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(SystemExit) as info:
        load_settings()
    assert info.value.code == 1
    err = capsys.readouterr().err
    assert "DATABASE_URL" in err and "REDIS_URL" in err


def test_load_settings_names_a_model_level_error_cleanly(monkeypatch, capsys):
    """A model_validator error has an empty loc; the boot message must still be one clean line (I1)."""
    from app.config import load_settings
    monkeypatch.setenv("ENVIRONMENT", "qa")
    monkeypatch.setenv("SITE_MODE", "coming_soon")
    with pytest.raises(SystemExit) as info:
        load_settings()
    assert info.value.code == 1
    err = capsys.readouterr().err
    assert "SITE_MODE=coming_soon is never valid on QA" in err and "Traceback" not in err and "IndexError" not in err


_BASE = {"database_url": "postgresql://x", "redis_url": "redis://x", "environment": "test", "api_secret_key": "x"}


def _settings(**kw):
    from app.config import Settings
    return Settings(**_BASE, **kw)


def test_log_level_defaults_to_info_and_normalises_case_and_whitespace():
    """Release-tip review, Important 1. `app/main.py`'s `_configure_logging` hands this value
    straight to `logging.Logger.setLevel`, which raises `ValueError: Unknown level` for anything it
    does not recognise — INSIDE `create_app()`, which runs at module import, so uvicorn never loads
    the app and the container restart-loops with a bare traceback. A trailing space is enough:
    `setLevel("INFO ")` raises. Whitespace and case are normalised here rather than being treated as
    typos, because neither is one."""
    assert _settings().log_level == "INFO"
    assert _settings(log_level="debug").log_level == "DEBUG"
    assert _settings(log_level="  INFO  ").log_level == "INFO"


def test_a_known_level_is_kept_so_log_level_actually_selects_the_level():
    """The perturbation the review asked for: a validator hard-coded to return "INFO" would pass
    every other case in this file and silently pin the api at INFO for ever. `WARNING` must survive
    as `WARNING`, and `WARN` — a real, if deprecated, member of
    `logging.getLevelNamesMapping()` — is a KNOWN level, not a typo, so it survives too."""
    import logging

    assert _settings(log_level="WARNING").log_level == "WARNING"
    assert _settings(log_level="warn").log_level == "WARN"
    assert logging.getLevelNamesMapping()["WARN"] == logging.WARNING
    for name in logging.getLevelNamesMapping():
        assert _settings(log_level=name.lower()).log_level == name


def test_an_unknown_log_level_falls_back_to_info_and_never_raises():
    """RULING (release-tip review): a log level never takes the api down. `20` is the realistic
    typo — a number where a name belongs — and `setLevel("20")` raises today. The value is refused,
    INFO is used, and the process boots."""
    from app import config

    assert _settings(log_level="20").log_level == "INFO"
    assert _settings(log_level="verbose").log_level == "INFO"
    assert config.log_level_rejected == "verbose"


def test_the_rejected_log_level_is_recorded_only_while_there_is_one():
    """The record is what lets `_configure_logging` name the refused value in ONE warning line
    rather than swallowing the typo. It is cleared by a good value, so it always describes the
    settings object most recently built rather than accumulating across a process."""
    from app import config

    _settings(log_level="nonsense")
    assert config.log_level_rejected == "nonsense"
    _settings(log_level="ERROR")
    assert config.log_level_rejected is None
