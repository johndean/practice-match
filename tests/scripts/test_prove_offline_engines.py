"""scripts/prove_offline_engines.py — constraint (i)'s proof, as a runnable command.

Review M-8: the plan's snippet could not run as written (it removed `socket.socket` before the
import, which breaks `ssl`), the corrected one lived only in a git-ignored report, and no test in
the suite ever constructs a real engine — so the one proof the constraint has was a screenshot.
This pins the SCRIPT: that it closes every door, that it reports what it found, and that its
`__main__` guard exits 0. The engines themselves are stubbed here, because a unit suite may not
depend on a compiled wheel and a system OpenGL library; the point of the script is that an operator
can run it against the real ones, which is what the report records."""
from __future__ import annotations

import os
import runpy
import socket
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

from app.privacy import barcodes, ocr
from scripts import prove_offline_engines as PROVE

ROOT = Path(__file__).resolve().parents[2]


def test_every_door_onto_a_socket_is_closed() -> None:
    """A stand-in module, so this case cannot disturb the process it runs in."""
    stand_in = ModuleType("not_really_socket")
    for door in PROVE.SOCKET_DOORS:
        setattr(stand_in, door, object())

    assert PROVE.close_every_socket_door(stand_in) == list(PROVE.SOCKET_DOORS)
    assert all(getattr(stand_in, door) is None for door in PROVE.SOCKET_DOORS)


def test_the_sample_image_carries_the_three_cases_the_rule_must_keep_apart() -> None:
    image = PROVE.sample_image()
    assert image.size == (1200, 900)
    assert image.convert("L").getextrema()[0] < 255, "the text was drawn, not a blank page"


def test_the_report_names_the_engines_and_every_line_it_read() -> None:
    lines = [ocr.Line("HILL COUNTRY VET", 0.967, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])]
    found = PROVE.report(lambda image: lines, lambda image: [], Image.new("RGB", (4, 4)),
                         "rapidocr-onnxruntime/1.4.4", "zxing-cpp/3.1.1", ["socket"])
    assert "ocr engine: rapidocr-onnxruntime/1.4.4" in found
    assert "  line: 'HILL COUNTRY VET' conf=0.967" in found
    assert "lines returned: 1" in found


def test_the_script_runs_end_to_end_and_leaves_no_socket_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Through `__main__`, so the command an operator is told to run is the one that is gated.

    monkeypatch is ARMED on all five doors before the script shuts them, so its teardown restores
    the real `socket` module for the rest of the session — the script is meant to leave a process
    unable to reach the network, and this suite has to go on afterwards."""
    for door in PROVE.SOCKET_DOORS:
        monkeypatch.setattr(socket, door, getattr(socket, door))
    monkeypatch.setattr(ocr, "read_text", lambda image: [
        ocr.Line("HILL COUNTRY VET", 0.97, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])])
    monkeypatch.setattr(barcodes, "read_symbols", lambda image: [])

    with pytest.raises(SystemExit) as caught:
        runpy.run_path(str(ROOT / "scripts" / "prove_offline_engines.py"), run_name="__main__")

    assert caught.value.code == 0
    printed = capsys.readouterr().out
    assert "socket.socket is None" in printed and "lines returned: 1" in printed
    assert socket.socket is None, "the script really did close the doors"


def test_the_documented_command_runs_from_the_repository_root(tmp_path: Path) -> None:
    """Review round 3, I-1: the `runpy` case above drives the script from INSIDE pytest, where the
    repository root is already on `sys.path` — so it could never see the one thing that was broken.

    `pyproject.toml` is `package-mode = false`, so nothing installs `app` into the venv; it resolves
    only because the root is the working directory. `python scripts/<file>.py` puts `scripts/` on
    `sys.path[0]` and NOT the root, so the command the script's own docstring and the plan both give
    died with `ModuleNotFoundError: No module named 'app'` — M-8 asked for a RUNNABLE command.

    A SUBPROCESS from the repository root, therefore, which is the only shape that can fail. The
    engines are the stub pair through `PRIVACY_ENGINE_MODULE`, so this owes nothing to a compiled
    wheel or to a system OpenGL library; what it proves is the bootstrap and the exit code."""
    home = tmp_path / "home"
    home.mkdir()
    finished = subprocess.run(
        [sys.executable, "scripts/prove_offline_engines.py"], cwd=ROOT, capture_output=True,
        text=True, check=False,
        env={**os.environ, "HOME": str(home), "XDG_CACHE_HOME": str(home / ".cache"),
             "ENVIRONMENT": "test", "PRIVACY_ENGINE_MODULE": "tests.e2e.stub_engines",
             "DATABASE_URL": "postgresql://x/y", "REDIS_URL": "redis://localhost:6379/0",
             "API_SECRET_KEY": "x", "PYTHONPATH": ""},
    )
    assert finished.returncode == 0, finished.stderr
    assert "socket.socket is None" in finished.stdout
    assert "ocr engine: rapidocr-onnxruntime/" in finished.stdout
