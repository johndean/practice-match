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
    # HOUSEKEEPING-A review (Minor), 2026-09-13 — the BELT the buckle needed. "Not tracked" is
    # true of a directory nobody has created yet, so this half passes on a machine that has never
    # run the Playwright MCP tooling and would go on passing if the ignore line were deleted:
    # the next run would write the scratch back into `git status`, and the next `git add -A`
    # would commit it. The rule itself is the subject here, in the shape
    # `test_the_coverage_report_is_ignored_and_untracked` below already uses.
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert ".playwright-mcp/" in lines, ".gitignore no longer carries the `.playwright-mcp/` line"


def test_the_coverage_report_is_ignored_and_untracked():
    """Fix round 1, Minor 5 (2026-09-13). `npm test` is `vitest run --coverage` since
    COVERAGE-HOTFIX and the backend gate writes `--cov-report=xml`, so running the documented
    gates leaves `coverage.xml` in the working tree — untracked, unignored, and one `git add -A`
    away from being committed. `frontend/coverage/` and `.coverage` were already ignored; this is
    the one artefact the same commands produce that was not.

    BOTH halves are asserted. "Not tracked" alone would pass today and go on passing if the ignore
    line were deleted, which is the state this test exists to prevent: `git check-ignore` is what
    makes the rule itself the subject."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "coverage.xml"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    assert [name for name in tracked if name] == []
    # `check=False` is the POINT of this call, not an oversight (ruff PLW1510): `git check-ignore`
    # answers by EXIT CODE — 0 ignored, 1 not ignored — so a non-zero status is the finding this
    # assertion reads, and `check=True` would raise instead of failing with the message below.
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "coverage.xml"], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert ignored.returncode == 0, "coverage.xml is not covered by .gitignore"
