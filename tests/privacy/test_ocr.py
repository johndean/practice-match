"""The OCR adapter (spec 2026-09-09 C.5 step 2). Directive 4: "Run OCR against EVERY image." An
engine error is therefore a FAILURE, never a skip -- that distinction is what this suite pins.

No model is downloaded and no network is touched: every case loads the stub engine through
`PRIVACY_ENGINE_MODULE`, which is the same seam the Playwright launcher uses."""
from __future__ import annotations

import importlib.metadata
import sys
import types
from typing import Any

import pytest
from PIL import Image

from app.privacy import ocr


@pytest.fixture(autouse=True)
def _stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.privacy.ocr.settings.privacy_engine_module", "tests.e2e.stub_engines")
    monkeypatch.setattr("app.privacy.ocr._LOADED", None)


def _image(w: int = 800, h: int = 600) -> Image.Image:
    return Image.new("RGB", (w, h), (255, 255, 255))


def test_every_line_carries_its_text_confidence_and_quad_in_display_pixels() -> None:
    lines = ocr.read_text(_image())
    assert lines and all(len(line.quad) == 4 for line in lines)
    assert all(0.0 <= line.confidence <= 1.0 for line in lines)
    assert {line.text for line in lines} == {"HILL COUNTRY ANIMAL HOSPITAL", "(512) 555-0100"}
    assert all(0 <= x <= 800 and 0 <= y <= 600 for line in lines for x, y in line.quad)


def test_a_short_line_is_re_read_on_a_doubled_image_and_its_quad_is_halved_back() -> None:
    """Directories and business cards: a line under 24 px is the case the second pass exists for.

    The stub's FIRST pass returns one line whose quad is 12 px tall at 800x600, which is what makes
    `read_text` upscale; the telephone number exists only on the doubled image, so a missing second
    pass is a missing line rather than a subtle coordinate error. Its quad comes back halved into
    display space -- y in [180, 198] of a 600 px image, not the [360, 396] the doubled pass saw."""
    lines = ocr.read_text(_image())
    tiny = [line for line in lines if line.text == "(512) 555-0100"]
    assert tiny, "the second pass did not run: the first pass's only line was not short"
    assert max(y for _, y in tiny[0].quad) == pytest.approx(198.0)
    assert max(x for x, _ in tiny[0].quad) == pytest.approx(280.0)


def test_a_first_pass_of_tall_lines_alone_runs_no_second_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other side of the trigger, so the branch is a decision and not an accident: an engine
    whose only line is 90 px tall is read once, at display size, and never upscaled."""
    class Tall:
        """Records the size of every image it is handed, so "no second pass" is an observation."""

        def __init__(self) -> None:
            self.seen: list[tuple[int, int]] = []

        def run(self, image: Image.Image) -> list[ocr.Line]:
            self.seen.append(image.size)
            return [ocr.Line("TALL", 0.9, [(0.0, 0.0), (100.0, 0.0), (100.0, 90.0), (0.0, 90.0)])]

    engine = Tall()
    monkeypatch.setattr("app.privacy.ocr._LOADED", engine)
    assert [line.text for line in ocr.read_text(_image())] == ["TALL"]
    assert engine.seen == [(800, 600)]


def test_a_first_pass_that_found_nothing_is_re_read_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `or nothing at all` half of `read_text`'s own contract, which no stub reaches: a
    photograph whose signage the engine misses entirely at display size is the same case as a
    short line, and the upscale is the second chance."""
    class Blind:
        def __init__(self) -> None:
            self.seen: list[tuple[int, int]] = []

        def run(self, image: Image.Image) -> list[ocr.Line]:
            self.seen.append(image.size)
            if image.height == 600:
                return []
            return [ocr.Line("LATE", 0.5, [(0.0, 0.0), (80.0, 0.0), (80.0, 60.0), (0.0, 60.0)])]

    engine = Blind()
    monkeypatch.setattr("app.privacy.ocr._LOADED", engine)
    assert ocr.read_text(_image()) == [ocr.Line("LATE", 0.5, [(0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0)])]
    assert engine.seen == [(800, 600), (1600, 1200)]


class _TwoPass:
    """An engine whose two passes are written by the case that plants it: the first at display size,
    the second on the doubled image. `read_text` halves the second pass's coordinates back, so a
    doubled quad of [(2x, 2y) …] lands exactly on its display-space twin."""

    def __init__(self, first: list[ocr.Line], second: list[ocr.Line]) -> None:
        self._first, self._second = first, second

    def run(self, image: Image.Image) -> list[ocr.Line]:
        return self._second if image.height > 600 else self._first


def _quad(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def test_the_same_words_on_a_second_sign_are_kept_because_the_quads_are_disjoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A-IDP-11, the ruled rule (review I1 (a)). A practice's name is on the building AND on the van
    in the same photograph. De-duplicating by TEXT returned one line, so the van's sign produced no
    redaction region at all under NOT_SHOW — the exact miss directive 4 exists to prevent. Two lines
    are the same line when their QUADS overlap, never because they read the same."""
    sign = ocr.Line("HILL COUNTRY", 0.9, _quad(10.0, 10.0, 200.0, 22.0))
    engine = _TwoPass(
        [sign],
        # the same sign, doubled — it halves back onto `sign` exactly and must be dropped;
        # and the van, far down the frame, which must survive.
        [ocr.Line("HILL COUNTRY", 0.9, _quad(20.0, 20.0, 400.0, 44.0)),
         ocr.Line("HILL COUNTRY", 0.8, _quad(20.0, 900.0, 300.0, 948.0))],
    )
    monkeypatch.setattr("app.privacy.ocr._LOADED", engine)
    lines = ocr.read_text(_image())
    assert lines == [sign, ocr.Line("HILL COUNTRY", 0.8, _quad(10.0, 450.0, 150.0, 474.0))]


def test_one_sign_read_twice_with_different_spellings_is_one_line_because_the_quads_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other direction, and it is not hypothetical: on the REAL wheel the same painted line came
    back "HILL COUNTRYVET" at display size and "HILLCOUNTRYVET" on the 2x pass (review I1 (b)), so a
    text rule left two regions for one sign. The quads agree to within a pixel, which is what the
    threshold reads."""
    first = ocr.Line("HILL COUNTRYVET", 0.99, _quad(10.0, 10.0, 200.0, 22.0))
    engine = _TwoPass([first], [ocr.Line("HILLCOUNTRYVET", 0.99, _quad(22.0, 20.0, 398.0, 46.0))])
    monkeypatch.setattr("app.privacy.ocr._LOADED", engine)
    assert ocr.read_text(_image()) == [first]


def test_a_second_pass_that_dies_while_it_is_being_read_is_an_error_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review M2: `found` was bound inside the `try` and iterated outside it, so an engine answering
    a lazy iterable raised its own exception THROUGH `read_text` instead of `OcrError` — and
    `app/tasks/media.py` would see something it has no reason code for."""
    def dying() -> Any:
        yield ocr.Line("LATE", 0.5, _quad(0.0, 0.0, 20.0, 24.0))
        raise RuntimeError("second pass died")

    class Lazy:
        """Deliberately out of contract — `Engine.run` declares `list[Line]` — which is the point:
        the first pass is already defended by `list(...)`, and the second must be too."""

        def run(self, image: Image.Image) -> Any:
            if image.height > 600:
                return dying()
            return [ocr.Line("SHORT", 0.9, _quad(0.0, 0.0, 10.0, 12.0))]

    monkeypatch.setattr("app.privacy.ocr._LOADED", Lazy())
    with pytest.raises(ocr.OcrError):
        ocr.read_text(_image())


def test_a_module_without_an_engine_class_is_unavailable_not_an_attribute_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review M1: the `AttributeError` half of the loader's `except` was never exercised — narrowing
    it to `except ImportError` left all 23 cases green, because coverage cannot see which exception
    type a handler catches. This is the arm that fires when Task P8's launcher points the setting at
    a module whose class has been renamed."""
    monkeypatch.setitem(sys.modules, "tests.e2e.engineless", types.ModuleType("tests.e2e.engineless"))
    monkeypatch.setattr("app.privacy.ocr.settings.privacy_engine_module", "tests.e2e.engineless")
    monkeypatch.setattr("app.privacy.ocr._LOADED", None)
    with pytest.raises(ocr.OcrUnavailable) as caught:
        ocr.read_text(_image())
    assert isinstance(caught.value.__cause__, AttributeError)


def test_the_engine_is_built_once_per_process() -> None:
    first = ocr._engine()
    assert ocr._engine() is first


def test_an_engine_that_will_not_import_is_unavailable_and_one_that_raises_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two different reason codes, because they mean different things to an operator: the wheel is
    missing from the image, versus this photograph broke the engine."""
    monkeypatch.setattr("app.privacy.ocr.settings.privacy_engine_module", "tests.e2e.no_such_engine")
    monkeypatch.setattr("app.privacy.ocr._LOADED", None)
    with pytest.raises(ocr.OcrUnavailable):
        ocr.read_text(_image())

    class Broken:
        def run(self, image: Image.Image) -> list[ocr.Line]:
            raise RuntimeError("onnxruntime said no")

    monkeypatch.setattr("app.privacy.ocr._LOADED", Broken())
    with pytest.raises(ocr.OcrError):
        ocr.read_text(_image())


def test_the_real_adapter_is_the_wheel_that_ships_its_own_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """With PRIVACY_ENGINE_MODULE unset -- every deployed service, because `Settings` refuses the
    variable anywhere but `ENVIRONMENT=test` -- the adapter asks for `rapidocr_onnxruntime` by name
    and wraps its `RapidOCR`, with `intra_op_num_threads=1` so two prefork children do not each
    start a thread pool the size of the machine.

    A stand-in in `sys.modules` is what the import resolves to here, so this case pins the WIRING --
    the keyword, the wrapper, and the `(result, elapsed)` tuple the real engine answers -- without
    loading 16 MB of ONNX weights into every run of the suite. That the weights are in the wheel,
    and that reaching them opens no socket, is proved by the task's own recorded run with
    `socket.socket` removed, and by `tests/conftest.py::_no_stray_network` over this whole file."""
    built: list[dict[str, Any]] = []

    class FakeRapidOCR:
        def __init__(self, **kwargs: Any) -> None:
            built.append(kwargs)

        def __call__(self, image: Image.Image) -> tuple[list[Any], list[float]]:
            return ([[[(10, 20), (110, 20), (110, 60), (10, 60)], "WHEEL", 0.77]], [0.01])

    wheel = types.ModuleType("rapidocr_onnxruntime")
    wheel.RapidOCR = FakeRapidOCR
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", wheel)
    monkeypatch.setattr("app.privacy.ocr.settings.privacy_engine_module", None)
    monkeypatch.setattr("app.privacy.ocr._LOADED", None)

    assert ocr.read_text(_image()) == [
        ocr.Line("WHEEL", 0.77, [(10.0, 20.0), (110.0, 20.0), (110.0, 60.0), (10.0, 60.0)])]
    assert built == [{"intra_op_num_threads": 1}]


def test_a_blank_photograph_answers_no_lines_rather_than_none() -> None:
    """`RapidOCR` answers `None` for an image it found nothing in, and `None` is not a list. The
    wrapper is the one place that difference is absorbed, so nothing downstream has to know it."""
    assert ocr._Rapid(lambda image: (None, [])).run(_image()) == []


def test_a_missing_wheel_is_unavailable_rather_than_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    """The operator-facing half of OCR_UNAVAILABLE: the engine is absent from the image entirely,
    which is a deployment fact rather than anything about this photograph."""
    monkeypatch.setattr("app.privacy.ocr.settings.privacy_engine_module", None)
    monkeypatch.setattr("app.privacy.ocr._LOADED", None)
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", None)
    with pytest.raises(ocr.OcrUnavailable):
        ocr.read_text(_image())


def test_the_engine_name_is_recorded_for_the_privacy_row() -> None:
    """Spec C.3 gives `ocr.engine` its reason: "so a record says which engine produced it". A
    hard-coded version cannot keep that promise — `pyproject.toml` admits `<2.0.0`, and Task P6
    re-runs `poetry lock`, so a resolved 1.5.x would leave every privacy row from then on naming an
    engine that did not produce it while every gate stayed green (review I2). The constant and the
    installed distribution move together or this goes red."""
    assert ocr.ENGINE == f"rapidocr-onnxruntime/{importlib.metadata.version('rapidocr-onnxruntime')}"
