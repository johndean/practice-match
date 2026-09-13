"""scripts/measure_source_subline_cap.py — the admin table's two layout caps as a measurement.

A38 review F11: `SOURCE_SUBLINE_CAP` and `DATASET_SUBLINE_CAP` are numbers measured once in a real
browser, and every registry note is held to them by ruling — so the probe that produced them is
committed and re-runnable, the way `scripts/measure_area_breaks.py` re-derives `AREA_LAYERS`. The
script itself only orchestrates: it runs the Playwright case, reads what it printed, and compares.
The browser is not started here — a unit test that launched Chromium would be the e2e suite — so
`subprocess.run` is the seam, and every arm this script can take is driven through it.
"""
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from app.census.registry import DATASET_SUBLINE_CAP, SOURCE_SUBLINE_CAP
from scripts import measure_source_subline_cap as MS

ROOT = Path(__file__).resolve().parents[2]

GOOD = (
    f"[A38-CAPS] SOURCE_SUBLINE_CAP={SOURCE_SUBLINE_CAP} maxPx=61 twoLinePx=61\n"
    f"[A38-CAPS] DATASET_SUBLINE_CAP={DATASET_SUBLINE_CAP} maxPx=61 twoLinePx=61\n"
    f"[A38-CAPS] designTallestPx={MS.DESIGN_TALLEST_PX} datasetPx={MS.DATASET_COLUMN_PX} sourcePx={MS.SOURCE_COLUMN_PX}\n"
)


def _probe(monkeypatch: pytest.MonkeyPatch, stdout: str, returncode: int = 0) -> None:
    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert cmd[:3] == ["npx", "playwright", "test"] and MS.GREP in cmd
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    monkeypatch.setattr(subprocess, "run", fake)


def test_both_caps_still_hold_is_a_zero_and_says_so(monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    _probe(monkeypatch, GOOD)
    assert MS.main() == 0
    out = capsys.readouterr().out
    assert f"ok  SOURCE_SUBLINE_CAP: probe {SOURCE_SUBLINE_CAP}, constant {SOURCE_SUBLINE_CAP}" in out
    assert "both caps still hold" in out


def test_a_cap_the_probe_no_longer_measures_is_reported_and_is_a_one(monkeypatch: pytest.MonkeyPatch,
                                                                     capsys: pytest.CaptureFixture[str]) -> None:
    """The whole point: a grid or type change moves the true two-line limit and the constant does
    not follow. Reported, never rewritten — a cap is a ruled number."""
    _probe(monkeypatch, GOOD.replace(f"DATASET_SUBLINE_CAP={DATASET_SUBLINE_CAP}", "DATASET_SUBLINE_CAP=70"))
    assert MS.main() == 1
    out = capsys.readouterr().out
    assert "OUT DATASET_SUBLINE_CAP: probe 70" in out
    assert "a cap is a ruled number" in out


def test_a_design_that_has_moved_under_the_caps_is_reported_too(monkeypatch: pytest.MonkeyPatch,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    """Both caps are counts of characters in a column of a known width, inside a row of a known
    height. If the design's own row is no longer 94 px in a 258/376 px pair, the counts describe
    nothing, whatever they measure."""
    _probe(monkeypatch, GOOD.replace(f"sourcePx={MS.SOURCE_COLUMN_PX}", "sourcePx=400"))
    assert MS.main() == 1
    out = capsys.readouterr().out
    assert "OUT the Source column: 400 px" in out


def test_a_probe_that_failed_is_the_probes_exit_code_and_never_a_pass(monkeypatch: pytest.MonkeyPatch,
                                                                      capsys: pytest.CaptureFixture[str]) -> None:
    """A red probe means a cap no longer buys two lines. Swallowing that into a green run is how a
    measured number becomes a remembered one."""
    _probe(monkeypatch, "1 failed\n", returncode=1)
    with pytest.raises(SystemExit) as exc:
        MS.main()
    assert exc.value.code == 1
    assert "the probe FAILED" in capsys.readouterr().out


def test_a_probe_that_printed_no_measurement_is_refused_rather_than_assumed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A renamed case would otherwise make this script pass by measuring nothing at all."""
    _probe(monkeypatch, "3 passed\n")
    with pytest.raises(SystemExit) as exc:
        MS.main()
    assert "printed no SOURCE_SUBLINE_CAP measurement" in str(exc.value.code)


def test_the_main_guard_is_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    """`scripts/` is inside the 100 % gate, and the `if __name__` line is reachable only by running
    the file AS a script — `test_measure_area_breaks.py`'s own shape, for the same reason."""
    _probe(monkeypatch, "3 passed\n")
    monkeypatch.setattr(sys, "argv", ["measure_source_subline_cap.py"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "measure_source_subline_cap.py"), run_name="__main__")
    assert "printed no SOURCE_SUBLINE_CAP measurement" in str(exc.value.code)
