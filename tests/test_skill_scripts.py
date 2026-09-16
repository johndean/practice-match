"""Pins the argument guard on `.claude/skills/status-artifact/compose_status_example.py`.

Incident, HOUSEKEEPING-C fix round 1 (2026-09-13): the script hard-coded
`/tmp/pm-artifact-v4.html` for both read and write, so running it AT ALL — including to verify a
ruff fix changed no output — overwrote the controller's LIVE published artifact with whatever
fixture was lying around. The fix made the screenshot directory and the artifact path both
required command-line arguments, with no default pointing at any real file; a run with the wrong
argument count prints usage and exits non-zero. Round 2 re-review (Minor): that guard was pinned
by no test at all — this file is that pin, run through a real subprocess so it exercises exactly
what an operator (or another accidental invocation) would.

SAFETY NOTE for anyone re-proving RED by temporarily restoring a default path in the script itself:
running the REVERTED script for real, even from a test, reaches the real hard-coded path and
overwrites `/tmp/pm-artifact-v4.html` again — this happened once already during this very fix
(round 2), because the pre-fix script ignores a second CLI argument entirely and falls through to
the hard-coded write. Prove that RED by reasoning about the reverted source (it plainly hard-codes
the path) or by renaming the real file aside first — never by executing the reverted script
against a live machine's `/tmp`.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".claude" / "skills" / "status-artifact" / "compose_status_example.py"
# The path the incident overwrote. Never written to by this file — every assertion below only
# reads it, to prove the script left it alone.
LIVE_ARTIFACT = Path("/tmp/pm-artifact-v4.html")

# A minimal valid JPEG (SOI + EOI markers, no scan data) — enough for base64.b64encode to run
# over real bytes without needing a real photograph.
STUB_JPEG = bytes.fromhex("ffd8ffd9")
SHOT_NAMES = (
    "qa-0122-strip-location-def",
    "qa-0123-panel-def",
    "qa-0123-zoom-20-no-placeholder",
    "qa-0123-admin-buyer-header-gate",
)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, check=False,
    )


def test_compose_status_example_prints_usage_and_exits_nonzero_with_no_arguments():
    result = _run([])
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()
    assert str(SCRIPT.name) in result.stderr
    assert result.stdout == ""


def test_compose_status_example_prints_usage_and_exits_nonzero_with_one_argument(tmp_path):
    result = _run([str(tmp_path)])
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()
    assert result.stdout == ""


def test_compose_status_example_writes_only_the_given_output_file(tmp_path):
    """The guard is not merely present, it is EFFECTIVE: with two explicit temp paths, the only
    filesystem writes are the screenshot directory's own `status-v8.html` and the given artifact
    path. `LIVE_ARTIFACT` — the path the incident overwrote — is provably untouched, whether or
    not it happens to exist on the machine running this test."""
    shots = tmp_path / "shots"
    shots.mkdir()
    for name in SHOT_NAMES:
        (shots / f"{name}.jpg").write_bytes(STUB_JPEG)
    artifact = tmp_path / "artifact.html"
    original_artifact = '<html><body><section class="status" data-doc="status">OLD</section></body></html>'
    artifact.write_text(original_artifact, encoding="utf-8")

    live_existed_before = LIVE_ARTIFACT.exists()
    live_hash_before = hashlib.sha256(LIVE_ARTIFACT.read_bytes()).hexdigest() if live_existed_before else None

    result = _run([str(tmp_path), str(artifact)])
    assert result.returncode == 0, f"stderr: {result.stderr}"

    # It wrote the two files it was told to, and nothing else in the directory it was given.
    assert (tmp_path / "status-v8.html").exists()
    new_artifact = artifact.read_text(encoding="utf-8")
    assert new_artifact != original_artifact
    assert '<section class="status" data-doc="status">' in new_artifact
    assert sorted(p.name for p in tmp_path.iterdir()) == ["artifact.html", "shots", "status-v8.html"]

    # The one file this test exists to protect: unchanged, existence and content alike.
    assert LIVE_ARTIFACT.exists() == live_existed_before
    if live_existed_before:
        assert hashlib.sha256(LIVE_ARTIFACT.read_bytes()).hexdigest() == live_hash_before
