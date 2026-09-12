import json
from pathlib import Path

from app.version import VERSION

ROOT = Path(__file__).resolve().parent.parent


def test_frontend_and_backend_versions_are_in_lockstep():
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text())
    assert pkg["version"] == VERSION


def test_lock_file_versions_are_in_lockstep():
    """package-lock.json carries its own two version fields (both npm-written) —
    the top-level `version` and `packages[""].version` — which drift from
    package.json's on a manual release bump. Both join the lockstep pin."""
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text())
    assert lock["version"] == VERSION
    assert lock["packages"][""]["version"] == VERSION
