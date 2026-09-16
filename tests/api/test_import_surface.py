"""The api process imports no detection ENGINE (spec 2026-09-09 C.5's "The api never imports the
engines").

NOT "no api module imports `app.tasks.media`" -- `app/privacy/aggregate.py` imports `Symbol` and
`Line` from the two adapter modules at module scope, so an api module that imports `aggregate` (as
P12's mask routes will) pulls `app.privacy.ocr` and `app.privacy.barcodes` into the api process by
design. That is fine and is not what the rule protects: the adapters load their engines LAZILY,
inside `_load` and `_Zxing.__init__`, so importing them costs nothing and reaches no wheel. What
must never happen is the api holding `rapidocr_onnxruntime`, `onnxruntime`, `zxingcpp` or
`anthropic` -- 510 MB of wheels on the request path, and three of them with an inference session's
worth of memory behind them.

WHY A SUBPROCESS. `sys.modules` is a property of a PROCESS, and pytest imports every test module in
the repository during collection, before the first test runs -- `tests/tasks/test_media.py` among
them, whose own `from app.tasks import media` is exactly what this file must be able to see the
absence of. Asserting on this process's `sys.modules` would therefore be asserting about pytest's
collection order rather than about the api, and would pass or fail for reasons that have nothing to
do with the app's import graph. A fresh interpreter has no such history, and the probe below is the
same one the task's gate runs from the command line
(`poetry run pytest tests/api/test_import_surface.py -q -W error`, alone).

The second case is what stops the first being a fake green: the SAME probe, asked to import an
engine first, must report it. A probe that reported an empty list whatever the process held would
pass this file for ever.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent

#: The wheels the api must not hold. `rapidocr_onnxruntime` drives `onnxruntime`; `zxingcpp` is the
#: 2D-symbol reader; `anthropic` is the vision SDK. Import names, not distribution names.
ENGINE_MODULES = ("rapidocr_onnxruntime", "onnxruntime", "zxingcpp", "anthropic")

#: Built, run in a fresh interpreter, and asked what it is holding. `argv[1]` is the dist directory
#: `create_app` needs; `argv[2]`, when present, is a module to import BEFORE the app, which is how
#: the probe is shown to be able to see one at all.
_PROBE = f"""
import json, sys
from pathlib import Path

planted = sys.argv[2] if len(sys.argv) > 2 else None
if planted:
    __import__(planted)

from app.main import create_app

app = create_app(dist=Path(sys.argv[1]))
print(json.dumps({{
    "built": type(app).__name__,
    "engines": sorted(n for n in {list(ENGINE_MODULES)!r} if n in sys.modules),
    "task_module": "app.tasks.media" in sys.modules,
}}))
"""


def _probe(dist: Path, *, plant: str | None = None) -> dict[str, Any]:
    """The probe's answer, from a process that has imported nothing else."""
    argv = [sys.executable, "-c", _PROBE, str(dist), *([plant] if plant else [])]
    done = subprocess.run(argv, cwd=ROOT, env=dict(os.environ), capture_output=True, text=True, check=False)
    assert done.returncode == 0, f"the probe did not run:\n{done.stderr}"
    answer: dict[str, Any] = json.loads(done.stdout)
    assert answer["built"] == "FastAPI", answer
    return answer


def test_a_fresh_interpreter_that_builds_the_app_loads_no_engine_wheel(dist: Path) -> None:
    """`create_app()` in a process of its own, with nothing else imported first."""
    assert _probe(dist)["engines"] == []


def test_a_fresh_interpreter_that_builds_the_app_does_not_import_the_task_module(dist: Path) -> None:
    """The eager branch (controller amendment A-IDP-2) is `app.tasks.media`'s ONLY importer under
    `app/`, and it cannot run outside `ENVIRONMENT=test`: `Settings` refuses
    `CELERY_TASK_ALWAYS_EAGER` at boot everywhere else. Building the app never reaches it."""
    assert _probe(dist)["task_module"] is False


def test_the_probe_reports_an_engine_that_is_actually_there(dist: Path) -> None:
    """The gate's own gate. Without this, `engines == []` would pass for a probe that could not see
    an engine at all -- a list comprehension over the wrong names, a `sys.modules` read in the
    wrong process, a probe that never ran. `zxingcpp` is the cheapest of the four to import (a
    ~1 MB wheel, no session, no models)."""
    assert _probe(dist, plant="zxingcpp")["engines"] == ["zxingcpp"]
