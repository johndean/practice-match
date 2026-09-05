"""Single source of the release version: pyproject.toml [project].version.
frontend/package.json must match (tests/test_versions.py)."""
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def app_version() -> str:
    with _PYPROJECT.open("rb") as fh:
        version = tomllib.load(fh)["project"]["version"]
    assert isinstance(version, str)  # narrows tomllib's Any for mypy --strict (fix round 1, incidental)
    return version


VERSION = app_version()
