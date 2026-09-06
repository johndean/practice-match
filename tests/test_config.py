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
