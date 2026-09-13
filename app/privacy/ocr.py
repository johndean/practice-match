"""The OCR adapter -- the ONLY module in `app/` that imports an OCR engine (spec 2026-09-09 C.5).

`rapidocr-onnxruntime` bundles its PP-OCR models in the wheel, so nothing is downloaded at run time
and a network-blocked test proves it. The engine object is built once per prefork child (a
module-level lazy singleton) with `intra_op_num_threads = 1`, because the worker runs two children
and each would otherwise start a thread pool the size of the machine.

Directive 4 says "Run OCR against EVERY image", so this module has no "skip" outcome: an engine that
will not import raises `OcrUnavailable` and one that fails on a photograph raises `OcrError`, and
`app/tasks/media.py` turns both into PROCESSING_FAILED with the matching reason code."""
from __future__ import annotations

import importlib
import importlib.metadata
from typing import Any, NamedTuple, Protocol, cast

from PIL import Image

from app.config import settings

#: Recorded in the privacy row's `ocr.engine`, so a record says which engine produced it -- which
#: means it is READ from the installed distribution and never written down. `pyproject.toml` admits
#: anything below 2.0.0, so a later `poetry lock` can move the engine under a hard-coded constant
#: and leave every row from then on naming a version that produced nothing (review I2). The
#: distribution's metadata is on disk whether or not the engine module is ever imported, so this
#: costs the api nothing and does not break `_load`'s laziness.
ENGINE = f"rapidocr-onnxruntime/{importlib.metadata.version('rapidocr-onnxruntime')}"
#: A line shorter than this is re-read on a 2x upscale -- directories, business cards, door vinyl.
UPSCALE_BELOW_PX = 24
#: Two lines are the SAME line when their quads' bounding boxes overlap by at least this much
#: (intersection over union). The second pass re-reads the same photograph at 2x, so one sign's two
#: readings halve back onto each other within a pixel or two -- an IoU above 0.9 -- while two
#: separate signs in one frame do not touch at all; 0.5 sits between those, far enough above zero
#: that nothing merely adjacent is merged and far enough below one that a box which grew or shrank
#: by a third in the sharper read is still recognised as the line it is (amendment A-IDP-11).
DUPLICATE_IOU = 0.5


class Line(NamedTuple):
    """One recognised line, in DISPLAY-pixel space. The quad is the engine's rotated box, kept as
    four points rather than a bounding rectangle so a sign photographed at an angle is covered by
    the polygon it actually occupies."""

    text: str
    confidence: float
    quad: list[tuple[float, float]]


class OcrUnavailable(RuntimeError):
    """The engine is not installed or will not import. Reason code OCR_UNAVAILABLE."""


class OcrError(RuntimeError):
    """The engine raised on this photograph. Reason code OCR_ERROR."""


class Engine(Protocol):
    def run(self, image: Image.Image) -> list[Line]: ...


_LOADED: Engine | None = None


def _engine() -> Engine:
    global _LOADED
    if _LOADED is None:
        _LOADED = _load()
    return _LOADED


def _load() -> Engine:
    module = settings.privacy_engine_module
    if module is not None:
        try:
            return cast("Engine", importlib.import_module(module).OcrEngine())
        except (ImportError, AttributeError) as exc:
            raise OcrUnavailable("OCR_UNAVAILABLE") from exc
    # Deliberately lazy, and deliberately dynamic: the api process must never import an OCR engine,
    # and `rapidocr_onnxruntime` ships neither a `py.typed` marker nor a stub, so a static
    # `from rapidocr_onnxruntime import RapidOCR` would need a `type: ignore` that this
    # sub-project's constraint (e) forbids. `import_module` asks for the same module by name.
    try:
        rapid = importlib.import_module("rapidocr_onnxruntime")
    except ImportError as exc:
        raise OcrUnavailable("OCR_UNAVAILABLE") from exc
    return _Rapid(rapid.RapidOCR(intra_op_num_threads=1))


class _Rapid:
    """`RapidOCR()(img)` answers `[[quad], text, score]` per line, or `None` for a blank image."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def run(self, image: Image.Image) -> list[Line]:
        result, _elapsed = self._engine(image)
        return [Line(text, float(score), [(float(x), float(y)) for x, y in quad])
                for quad, text, score in (result or [])]


def _height(quad: list[tuple[float, float]]) -> float:
    return max(y for _, y in quad) - min(y for _, y in quad)


def _bbox(quad: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """The quad's axis-aligned bounding box. A rotated box is compared by its bounds rather than by
    its own polygon: the two readings of one sign differ by a degree or two at most, and the extra
    area a bounding box claims is the same area for both of them."""
    xs = [x for x, _ in quad]
    ys = [y for _, y in quad]
    return min(xs), min(ys), max(xs), max(ys)


def _iou(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Intersection over union of two quads' bounding boxes, 0.0 when they do not overlap."""
    ax0, ay0, ax1, ay1 = _bbox(a)
    bx0, by0, bx1, by1 = _bbox(b)
    width = min(ax1, bx1) - max(ax0, bx0)
    height = min(ay1, by1) - max(ay0, by0)
    if width <= 0 or height <= 0:
        return 0.0
    # Past that guard the intersection is positive, and each box is at least as large as it, so the
    # union is positive too -- there is no zero to divide by.
    intersection = width * height
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - intersection
    return intersection / union


def read_text(image: Image.Image) -> list[Line]:
    """Every line the engine finds, plus a second pass on a 2x upscale whenever the first pass saw
    a short line or nothing at all. The second pass's coordinates are halved back into display
    space, and a line whose quad overlaps one already kept by `DUPLICATE_IOU` or more is dropped.

    De-duplication is by GEOMETRY and never by text (amendment A-IDP-11). Two readings of one sign
    routinely disagree about its words -- the same painted line came back "HILL COUNTRYVET" at
    display size and "HILLCOUNTRYVET" at 2x -- and a practice's name is often on the building AND on
    the van in one photograph, where a text rule drops the van's sign and NOTHING under NOT_SHOW
    ever fills it. Distinct quads carrying identical text are therefore both kept."""
    engine = _engine()
    try:
        lines = list(engine.run(image))
        if not lines or any(_height(line.quad) < UPSCALE_BELOW_PX for line in lines):
            doubled = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
            found = list(engine.run(doubled))
        else:
            found = []
    except Exception as exc:  # the engine's own failures are not a documented, catchable set
        raise OcrError("OCR_ERROR") from exc
    for line in found:
        halved = Line(line.text, line.confidence, [(x / 2, y / 2) for x, y in line.quad])
        if not any(_iou(seen.quad, halved.quad) >= DUPLICATE_IOU for seen in lines):
            lines.append(halved)
    return lines
