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

#: The distribution this adapter drives, named once so the constant and its guard agree.
_DIST = "rapidocr-onnxruntime"


def _engine_name() -> str:
    """`<distribution>/<installed version>`, or `<distribution>/unavailable` when the distribution
    is not installed.

    READ rather than written down: `pyproject.toml` admits anything below 2.0.0, so a later
    `poetry lock` can move the engine under a hard-coded constant and leave every privacy row from
    then on naming a version that produced nothing (review I2).

    GUARDED, because IMPORTING AN ADAPTER NEVER RAISES (review N1). An unguarded lookup made a
    process whose image does not carry the wheel die on `import app.privacy.ocr` with a raw
    `PackageNotFoundError` -- which is precisely the deployment `OcrUnavailable` and its
    OCR_UNAVAILABLE reason code exist to REPORT, so the fix for one finding removed the only path
    to the other. That case is live the moment Task P5 imports this module into
    `app/tasks/media.py`, and again under any D5 route that splits the engines out of the api's
    image. The marker keeps the constant's `<name>/<version>` shape so nothing that reads a record
    has to learn a second grammar -- though no row can ever carry it, because `read_text` raises
    before a scan is recorded."""
    try:
        return f"{_DIST}/{importlib.metadata.version(_DIST)}"
    except importlib.metadata.PackageNotFoundError:
        return f"{_DIST}/unavailable"


#: Recorded in the privacy row's `ocr.engine`, so a record says which engine produced it.
ENGINE = _engine_name()
#: A line shorter than this is re-read on a 2x upscale -- directories, business cards, door vinyl.
UPSCALE_BELOW_PX = 24
#: Two lines are the SAME line when their QUADS overlap by at least this much (intersection over
#: union of the polygons themselves, never of their bounding boxes -- review N2). The second pass
#: re-reads the same photograph at 2x, so one sign's two readings halve back onto each other within
#: a pixel or two, measured at 0.914 on the pair this rule was written for; two stacked lines of one
#: sign that merely graze each other measure 0.304. 0.5 sits between those -- high enough that a
#: neighbouring line of the same sign stays its own region, low enough that a box which grew or
#: shrank by a third in the sharper read is still recognised as the line it is (amendment A-IDP-11).
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
    """The quad's axis-aligned bounding box, used ONLY as `_iou`'s pre-check."""
    xs = [x for x, _ in quad]
    ys = [y for _, y in quad]
    return min(xs), min(ys), max(xs), max(ys)


def _boxes_overlap(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
    """Whether the two bounding boxes intersect. A cheap NO: polygons inside boxes that miss each
    other cannot possibly meet, so that case skips the clipping entirely. It can never answer YES
    on its own -- that is review N2's whole point."""
    ax0, ay0, ax1, ay1 = _bbox(a)
    bx0, by0, bx1, by1 = _bbox(b)
    return min(ax1, bx1) > max(ax0, bx0) and min(ay1, by1) > max(ay0, by0)


def _area(polygon: list[tuple[float, float]]) -> float:
    """The shoelace area, unsigned, so a quad wound either way measures the same."""
    total = 0.0
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def _counter_clockwise(polygon: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """`polygon` wound counter-clockwise, which is what tells `_clip` which side of an edge is in.
    An engine's quad arrives wound either way, so this is normalisation and not a correction."""
    signed = sum(x0 * y1 - x1 * y0
                 for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1], strict=True))
    return polygon if signed >= 0 else polygon[::-1]


def _crossing(a: tuple[float, float], b: tuple[float, float], a_side: float, b_side: float) -> tuple[float, float]:
    """Where the segment a->b meets the clipping edge, interpolated on the two signed distances.
    Called only when those differ in sign, so the denominator cannot be zero."""
    t = a_side / (a_side - b_side)
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def _clip(subject: list[tuple[float, float]],
          clipper: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """`subject` clipped to the convex polygon `clipper` -- Sutherland-Hodgman, stdlib only and no
    new dependency. An OCR quad is four points and convex, which is this algorithm's one
    precondition; each of the clipper's edges keeps the part of the subject on its inner side, so
    what survives all four edges is exactly the intersection."""
    output = list(subject)
    edges = _counter_clockwise(clipper)
    for (ax, ay), (bx, by) in zip(edges, edges[1:] + edges[:1], strict=True):
        if not output:
            return []
        ex, ey = bx - ax, by - ay
        kept: list[tuple[float, float]] = []
        previous = output[-1]
        previous_side = ex * (previous[1] - ay) - ey * (previous[0] - ax)
        for point in output:
            side = ex * (point[1] - ay) - ey * (point[0] - ax)
            if side >= 0:
                if previous_side < 0:
                    kept.append(_crossing(previous, point, previous_side, side))
                kept.append(point)
            elif previous_side >= 0:
                kept.append(_crossing(previous, point, previous_side, side))
            previous, previous_side = point, side
        output = kept
    return output


def _iou(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Intersection over union of the two QUADS, 0.0 when they do not overlap.

    On the polygons themselves, because bounding boxes lie about a rotated sign (review N2): two
    stacked lines of one sign photographed at 45 degrees have a true intersection of exactly zero
    and a bounding-box IoU of 0.54, so a box rule merged them and lost a region -- and `Line`'s own
    docstring says the quad is four points rather than a rectangle for precisely that reason."""
    if not _boxes_overlap(a, b):
        return 0.0
    intersection = _area(_clip(a, b))
    if intersection <= 0:
        return 0.0
    # Each quad is at least as large as the part they share, so the union is positive here.
    return intersection / (_area(a) + _area(b) - intersection)


def _merge(lines: list[Line]) -> list[Line]:
    """One line per CLUSTER of overlapping quads, the most confident member of each.

    Order-independent by construction (review N4). The greedy first-wins loop this replaces compared
    each new line against the lines it had ALREADY kept, so three chained detections of one region
    kept two lines when they arrived A,B,C and one when they arrived B,A,C -- from the same input.
    Clusters are built by TRANSITIVE overlap, so the answer is a function of the set of detections
    and of nothing else; ties in confidence go to the earlier line, which keeps a first-pass reading
    ahead of its own 2x twin."""
    parent = list(range(len(lines)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i, one in enumerate(lines):
        for j, other in enumerate(lines[i + 1:], start=i + 1):
            if _iou(one.quad, other.quad) >= DUPLICATE_IOU:
                parent[root(j)] = root(i)

    best: dict[int, int] = {}
    for index, line in enumerate(lines):
        cluster = root(index)
        chosen = best.get(cluster)
        if chosen is None or line.confidence > lines[chosen].confidence:
            best[cluster] = index
    return [lines[index] for index in sorted(best.values())]


def read_text(image: Image.Image) -> list[Line]:
    """Every line the engine finds, plus a second pass on a 2x upscale whenever the first pass saw
    a short line or nothing at all. The second pass's coordinates are halved back into display
    space, and lines whose quads overlap by `DUPLICATE_IOU` or more collapse to the most confident
    of them.

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
    halved = [Line(line.text, line.confidence, [(x / 2, y / 2) for x, y in line.quad])
              for line in found]
    return _merge(lines + halved)
