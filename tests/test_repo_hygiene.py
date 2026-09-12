import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_playwright_mcp_scratch_is_not_tracked():
    """Playwright MCP tooling scratch (`.playwright-mcp/*.yml`) was committed by accident.
    0.1.21 added `.playwright-mcp/` to `.gitignore`, which cannot untrack files already
    tracked — `git rm -r --cached .playwright-mcp` is the fix (working files kept)."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z", ".playwright-mcp"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    tracked = [name for name in tracked if name]
    assert tracked == []
