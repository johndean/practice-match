"""zxing-cpp behind an adapter (spec C.5 step 2b, D-IDP-7). EVERY 2D symbol is a redaction region
under NOT_SHOW regardless of payload: a QR cannot be reviewed by eye, and the worker never fetches
one -- no egress, no SSRF. The payload is classified offline and the STRING is never stored."""
from __future__ import annotations

import importlib
import importlib.metadata
import sys
import types
from typing import Any

import pytest
from PIL import Image

from app.privacy import barcodes


@pytest.mark.parametrize(("payload", "kind"), [
    ("https://hillcountryvet.example/appointments", "url"),
    ("hillcountryvet.example", "url"),
    ("tel:+15125550100", "phone"),
    ("(512) 555-0100", "phone"),
    ("BEGIN:VCARD\nFN:Hill Country\nEND:VCARD", "vcard"),
    ("staff room", "text"),
])
def test_a_payload_is_classified_and_never_returned(payload: str, kind: str) -> None:
    assert barcodes.classify(payload) == kind


def test_an_undecodable_finder_pattern_is_still_a_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    """`return_errors=True`: a QR the engine can see but not decode is exactly the case a seller
    would most want covered, and it has no payload to classify."""
    class Partial:
        def read(self, image: Image.Image) -> list[barcodes.Symbol]:
            return [barcodes.Symbol("QRCode", "undecodable", [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)])]

    monkeypatch.setattr("app.privacy.barcodes._LOADED", Partial())
    found = barcodes.read_symbols(Image.new("RGB", (200, 200)))
    assert [s.payload_kind for s in found] == ["undecodable"]


def test_an_engine_that_will_not_import_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.privacy.barcodes.settings.privacy_engine_module", "tests.e2e.no_such_engine")
    monkeypatch.setattr("app.privacy.barcodes._LOADED", None)
    with pytest.raises(barcodes.BarcodeUnavailable):
        barcodes.read_symbols(Image.new("RGB", (200, 200)))


def test_the_stub_engine_is_reached_through_the_same_setting_the_launcher_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The seam itself, on the barcode side: `PRIVACY_ENGINE_MODULE` names a module and its
    `BarcodeEngine` is what `read_symbols` runs. The stub carries no symbol, so a photograph with
    no QR in it answers an empty list -- which is the ordinary case, not an error."""
    monkeypatch.setattr("app.privacy.barcodes.settings.privacy_engine_module", "tests.e2e.stub_engines")
    monkeypatch.setattr("app.privacy.barcodes._LOADED", None)
    assert barcodes.read_symbols(Image.new("RGB", (200, 200))) == []
    assert barcodes._engine() is barcodes._engine()      # built once per process, as the OCR one is


def test_the_real_adapter_wraps_the_wheels_own_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """With PRIVACY_ENGINE_MODULE unset -- every deployed service -- the adapter imports `zxingcpp`
    and reads with `return_errors=True`, which is the only reason an undecodable symbol reaches a
    caller at all. A stand-in in `sys.modules` is what the import resolves to, so the WIRING is
    pinned here (the keywords, the four corners in order, `valid` deciding the kind) without
    depending on a compiled extension being importable in this environment.

    `str(result.format)` and not the enum: the record keeps a name, and `BarcodeFormat` is an
    `IntEnum` whose `__str__` gives it."""
    seen: list[dict[str, Any]] = []

    def _point(x: int, y: int) -> Any:
        return types.SimpleNamespace(x=x, y=y)

    position = types.SimpleNamespace(top_left=_point(10, 20), top_right=_point(50, 20),
                                     bottom_right=_point(50, 60), bottom_left=_point(10, 60))

    def read_barcodes(image: Image.Image, **kwargs: Any) -> list[Any]:
        seen.append(kwargs)
        return [types.SimpleNamespace(position=position, text="https://hillcountryvet.example/a",
                                      valid=True, format="QR Code"),
                types.SimpleNamespace(position=position, text="", valid=False, format="QR Code")]

    wheel = types.ModuleType("zxingcpp")
    wheel.read_barcodes = read_barcodes
    monkeypatch.setitem(sys.modules, "zxingcpp", wheel)
    monkeypatch.setattr("app.privacy.barcodes.settings.privacy_engine_module", None)
    monkeypatch.setattr("app.privacy.barcodes._LOADED", None)

    quad = [(10.0, 20.0), (50.0, 20.0), (50.0, 60.0), (10.0, 60.0)]
    assert barcodes.read_symbols(Image.new("RGB", (200, 200))) == [
        barcodes.Symbol("QR Code", "url", quad), barcodes.Symbol("QR Code", "undecodable", quad)]
    assert seen == [{"try_rotate": True, "try_downscale": True, "return_errors": True}]


def test_a_missing_wheel_is_unavailable_rather_than_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.privacy.barcodes.settings.privacy_engine_module", None)
    monkeypatch.setattr("app.privacy.barcodes._LOADED", None)
    monkeypatch.setitem(sys.modules, "zxingcpp", None)
    with pytest.raises(barcodes.BarcodeUnavailable):
        barcodes.read_symbols(Image.new("RGB", (200, 200)))


def test_an_engine_that_raises_on_this_photograph_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """BARCODE_ERROR, the other reason code: the wheel is there and this photograph broke it, which
    `app/tasks/media.py` turns into PROCESSING_FAILED rather than a silent skip."""
    class Broken:
        def read(self, image: Image.Image) -> list[barcodes.Symbol]:
            raise ValueError("unsupported image format")

    monkeypatch.setattr("app.privacy.barcodes._LOADED", Broken())
    with pytest.raises(barcodes.BarcodeError):
        barcodes.read_symbols(Image.new("RGB", (200, 200)))


def test_a_module_without_an_engine_class_is_unavailable_not_an_attribute_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review M1, the twin of `test_ocr.py`'s own case: narrowing `except (ImportError,
    AttributeError)` to `except ImportError` left every case green at 100 % branch coverage, because
    coverage cannot see WHICH exception type a handler catches."""
    monkeypatch.setitem(sys.modules, "tests.e2e.engineless", types.ModuleType("tests.e2e.engineless"))
    monkeypatch.setattr("app.privacy.barcodes.settings.privacy_engine_module", "tests.e2e.engineless")
    monkeypatch.setattr("app.privacy.barcodes._LOADED", None)
    with pytest.raises(barcodes.BarcodeUnavailable) as caught:
        barcodes.read_symbols(Image.new("RGB", (200, 200)))
    assert isinstance(caught.value.__cause__, AttributeError)


def test_an_absent_distribution_leaves_the_module_importable_and_the_reason_code_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review N1, the twin of `test_ocr.py`'s own case: importing an adapter never raises, and
    `BARCODE_UNAVAILABLE` stays reachable for the deployment it describes."""
    def raiser(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr("importlib.metadata.version", raiser)
    monkeypatch.delitem(sys.modules, "app.privacy.barcodes")
    fresh = importlib.import_module("app.privacy.barcodes")

    assert fresh.ENGINE == "zxing-cpp/unavailable"
    monkeypatch.setattr(fresh.settings, "privacy_engine_module", None)
    monkeypatch.setitem(sys.modules, "zxingcpp", None)
    with pytest.raises(fresh.BarcodeUnavailable):
        fresh.read_symbols(Image.new("RGB", (200, 200)))


def test_the_engine_name_and_the_expansion_are_recorded_for_the_privacy_row() -> None:
    """`ENGINE` is pinned to the INSTALLED distribution for the reason review I2 gives — a record
    whose only purpose is to be trustworthy may not name a version nothing checked, and the range in
    `pyproject.toml` runs to `<4.0.0`. `EXPAND` is pinned to the ruled value rather than to
    `> 1.0`, which admitted 1.0001: spec C.5 step 2b says the symbol's corners are expanded 15 %."""
    assert barcodes.ENGINE == f"zxing-cpp/{importlib.metadata.version('zxing-cpp')}"
    assert barcodes.EXPAND == 1.15
