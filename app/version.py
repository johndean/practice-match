"""Single source of the release version: pyproject.toml [project].version.
frontend/package.json must match (tests/test_versions.py)."""
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def app_version() -> str:
    with _PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


VERSION = app_version()
