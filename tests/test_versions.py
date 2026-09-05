import json
from pathlib import Path

from app.version import VERSION

ROOT = Path(__file__).resolve().parent.parent


def test_frontend_and_backend_versions_are_in_lockstep():
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text())
    assert pkg["version"] == VERSION
