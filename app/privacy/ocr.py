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
import math
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
#: sign that merely graze each other measure 0.304. It governs any two detections of one
#: photograph, a pair within ONE pass included (review M-2), not only a reading against its own
#: 2x twin. 0.5 sits between those measurements -- high enough that a
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


def _turn(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """The cross product of o->a and o->b: positive when o, a, b turn left."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The convex hull, wound counter-clockwise -- Andrew's monotone chain, stdlib only.

    The SINGLE normaliser this module has, and it does three jobs at once (review M-3, M-7). It
    fixes the WINDING, which is what tells `_clip` which side of an edge is inside and which an
    engine may answer either way round. It fixes the ORDER: a rectangle whose corners arrive
    crosswise is a bow-tie with a shoelace area of zero, which scored IoU 0.0 against the same
    rectangle written properly -- silently, so every 2x twin would have survived as a duplicate.
    And it is what `_min_area_rect` measures a merged cluster's footprint over.

    It answers fewer than three points for input that carries fewer than three DISTINCT ones, or
    that is collinear, and `[]` for input that is all one point -- so a caller must not divide by
    its area. `_iou` does not, and NOT because it refuses anything -- it has no refusal (fan-in
    m-B). What happens is structural: an empty hull sorts FIRST, so it becomes the
    Sutherland-Hodgman subject, `_clip` returns `[]` at its first edge, and `_iou`'s zero-
    intersection guard answers 0.0 before any division. A quad carrying only SOME unmeasurable
    coordinates is a different case and is not covered by that: its NaN vertex survives the hull
    and `_iou` answers NaN, which `_iou`'s own docstring records. `_min_area_rect` does not divide
    by the hull either: it is seeded with the axis-aligned box, which is an answer whatever the
    hull turns out to be."""
    ordered = sorted(set(points))

    def half(source: list[tuple[float, float]]) -> list[tuple[float, float]]:
        chain: list[tuple[float, float]] = []
        for point in source:
            while len(chain) >= 2 and _turn(chain[-2], chain[-1], point) <= 0:
                chain.pop()
            chain.append(point)
        return chain

    lower = half(ordered)
    upper = half(ordered[::-1])
    return lower[:-1] + upper[:-1]


def _min_area_rect(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The smallest-area rectangle, at ANY angle, containing every point -- four corners, so a
    merged `Line` keeps the four-point quad `c57f23d` declared.

    Rotating calipers: the minimum-area enclosing rectangle always has a side flush with one of the
    hull's edges (Freeman & Shapira, 1975), so trying each edge's own frame is exhaustive. Seeded
    with the axis-aligned box, which is itself one of the candidates. Whatever it returns CONTAINS
    the hull, and therefore every member quad -- a merged line's footprint can only ever grow."""
    x0, y0, x1, y1 = _bbox(points)
    best = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    best_area = (x1 - x0) * (y1 - y0)
    hull = _convex_hull(points)
    for (ax, ay), (bx, by) in zip(hull, hull[1:] + hull[:1], strict=True):
        length = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / length, (by - ay) / length
        along = [px * ux + py * uy for px, py in points]
        across = [py * ux - px * uy for px, py in points]
        low_a, high_a, low_c, high_c = min(along), max(along), min(across), max(across)
        area = (high_a - low_a) * (high_c - low_c)
        if area < best_area:
            best_area = area
            best = [(a * ux - c * uy, a * uy + c * ux)
                    for a, c in ((low_a, low_c), (high_a, low_c), (high_a, high_c), (low_a, high_c))]
    return best


def _crossing(a: tuple[float, float], b: tuple[float, float], a_side: float, b_side: float) -> tuple[float, float]:
    """Where the segment a->b meets the clipping edge, interpolated on the two signed distances.
    Called only when those differ in sign, so the denominator cannot be zero."""
    t = a_side / (a_side - b_side)
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def _clip(subject: list[tuple[float, float]],
          clipper: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """`subject` clipped to the convex polygon `clipper` -- Sutherland-Hodgman, stdlib only and no
    new dependency. Each of the clipper's edges keeps the part of the subject on its inner side, so
    what survives them all is exactly the intersection. `clipper` must be convex and wound
    counter-clockwise, which `_iou` guarantees by hulling both arguments first."""
    output = list(subject)
    edges = clipper
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
    """Intersection over union of the two QUADS, 0.0 when they do not overlap, `NaN` when one of
    them is partly unmeasurable.

    On the polygons themselves, because bounding boxes lie about a rotated sign (review N2): two
    stacked lines of one sign photographed at 45 degrees have a true intersection of exactly zero
    and a bounding-box IoU of 0.54, so a box rule merged them and lost a region -- and `Line`'s own
    docstring says the quad is four points rather than a rectangle for precisely that reason.

    IT CAN ANSWER `NaN`, AND EVERY CALLER'S COMPARISON MUST BE WRITTEN SO THAT A NaN MEANS DO NOT
    MERGE (fan-in m-B, on P4 re-review 4 §4). A quad carrying SOME NaN coordinates rather than all
    of them keeps its NaN vertex right through the geometry: `_convex_hull` can never pop a point
    whose `_turn` is NaN, because every comparison against NaN is False, so the vertex survives
    into the hull, the shoelace area is NaN, the union is NaN and the quotient is NaN. That is a
    STRUCTURAL statement and not a sample -- no NaN-bearing quad can reach `DUPLICATE_IOU` by any
    route -- and the sweep is only its corroboration: 60,000 overlapping near-twins (a 200x30 quad
    at `rng.uniform(0, 1000)` by `rng.uniform(0, 800)` and the same quad offset by
    `rng.uniform(-40, 40)` by `rng.uniform(-8, 8)`, one ordinate of one of the two then set to NaN,
    `random.Random(20260915)`, both argument orders) answered NaN for 23,402 of them -- 39.0 %; the
    rest clip to an empty intersection and take the 0.0 below -- with 0 merges, 0 verdict
    disagreements between the two orders and 0 exceptions.

    The safety of that is POLARITY, not luck. `_merge` asks `>= DUPLICATE_IOU`, which NaN fails, so
    such a pair stays apart. `nan < DUPLICATE_IOU` is ALSO False, so a second reader spelled the
    other way round (`if _iou(...) < DUPLICATE_IOU: keep_apart`) falls into the MERGE branch
    instead. P7 is the next reader of this function and its brief carries the same warning. Whether
    the real `rapidocr-onnxruntime` wheel can emit a NaN coordinate at all is unmeasured; what is
    measured is only what this geometry does downstream of one.

    An ALL-NaN quad is the other case and answers 0.0 rather than NaN -- it hulls to nothing, and
    why that is harmless is at the `sorted(...)` line below."""
    if not _boxes_overlap(a, b):
        return 0.0
    # SORTED, so the pair is canonical: `_merge` asks `_iou(lines[i], lines[j])` for `i < j`, and
    # without this which quad was the Sutherland-Hodgman subject and which the clipper followed
    # arrival order. The two answers differ in the last bit, invisible everywhere except exactly at
    # `DUPLICATE_IOU`, where `>=` flipped.
    #
    # A FLIP RATE IS MEANINGLESS WITHOUT ITS GENERATOR, and this line carried two in a row that had
    # none (89 of 2,000 in review round 3, then 380 of 4,000 in fix round 4; fan-in m-A). The
    # figure is governed by the COORDINATE MAGNITUDE, because that is what sets the ULP and so how
    # often the knife-edge is straddled: on identical geometry, changing nothing but the box the
    # pairs are placed in takes the same 4,000 from 17.9 % (0..100) through 9.8 % (0..250) and
    # 8.6 % (0..300) to 3.1 % (0..2000). So the generator is written down here with the rate, and
    # it is this. Four thousand pairs; the shape is a 100x26 quad and its own left half, both
    # turned about their shared top-left corner, so the intersection is exactly half the union;
    # that corner is placed at `rng.uniform(0, 1000)` by `rng.uniform(0, 800)`, a 1000x800 image
    # frame, and the angle is `rng.uniform(0, 90)` degrees, drawn in that order from
    # `random.Random(seed)`; a pair counts as flipped when `_iou(a, b) >= DUPLICATE_IOU` differs
    # from `_iou(b, a) >= DUPLICATE_IOU`. Against `_iou` WITHOUT this `sorted`, over seeds
    # 20260915 and 1..4: 172, 181, 175, 172, 182 of 4,000 -- 4.3 to 4.5 % -- with the two orders
    # up to 3.4e-14 apart. WITH it, the same five seeds: 0, and the two orders bit-identical.
    #
    # The rate belongs to the generator; the DEPENDENCE on arrival order belonged to this function,
    # and it is what is closed here. A canonical order rather than a tolerance: a tolerance moves
    # the threshold instead of removing the dependence, and leaves the same flip one epsilon
    # further out.
    #
    # It is also what makes an UNMEASURABLE quad harmless. A NaN coordinate reaches the geometry
    # intact -- every comparison against it is False, so `_boxes_overlap`'s `min`/`max` answer the
    # finite operand and the pre-check says the two overlap -- and an all-NaN quad hulls to nothing.
    # An empty hull sorts FIRST, so it is the subject rather than the clipper, and `_clip` returns
    # `[]` at its first edge: intersection 0, and the guard below answers before any division. That
    # is the `ZeroDivisionError` review round 3's m-2 measured, and it is closed by construction
    # rather than by a branch no test could kill. `read_text` catches the rest (`_merge` runs inside
    # its envelope now), so nothing from this geometry can reach a caller without a reason code.
    left, right = sorted((_convex_hull(a), _convex_hull(b)))
    intersection = _area(_clip(left, right))
    if intersection <= 0:
        return 0.0
    # Each quad is at least as large as the part they share, so the union is positive here.
    return intersection / (_area(left) + _area(right) - intersection)


def _rank(line: Line) -> tuple[float, float, str]:
    """The order a cluster's representative is chosen in, smallest first: most confident, then the
    LARGER quad, then the text that sorts first.

    Every term is a property of the line itself, so the representative is a function of the SET of
    detections and never of the order they arrived in (review M-6). Confidence is the ruling's own
    rule (A-IDP-11, review N4); area breaks a tie towards the fuller reading, which is the safer one
    to carry; the text is the last resort and exists only so that two readings agreeing on both
    numbers still answer deterministically.

    It is NOT a strict total order on `Line`, and that is deliberate rather than overlooked: two
    detections agreeing on all three terms still tie, and `<` then leaves whichever was seen first
    in place. Harmless, because a cluster emits `Line(winner.text, winner.confidence, footprint)`
    and the footprint is the CLUSTER's (review I-1) -- so two members of equal rank produce the same
    `Line` byte for byte whichever of them wins. What the third term buys is the case where the two
    numbers tie and the SPELLINGS do not, which is routine here (one sign read twice) and is what
    review round 3's I-2 gated."""
    return (-line.confidence, -_area(line.quad), line.text)


def _merge(lines: list[Line]) -> list[Line]:
    """One line per CLUSTER of overlapping quads: the representative's text and confidence, over
    the whole cluster's FOOTPRINT.

    Order-independent by construction (review N4). The greedy first-wins loop this replaces compared
    each new line against the lines it had ALREADY kept, so three chained detections of one region
    kept two lines when they arrived A,B,C and one when they arrived B,A,C -- from the same input.
    Clusters are built by TRANSITIVE overlap and the representative is `_rank`'s own, so neither the
    clusters nor their winners depend on arrival order.

    The QUAD is the cluster's, not the winner's (review I-1). Keeping the winner's own box meant a
    more confident PARTIAL reading replaced a full one and the part it did not cover produced no
    region at all: a 2x pass that answers `HILL COUNTRY` where the first pass read `HILL COUNTRY
    VET` lost the 80 px carrying `VET` under NOT_SHOW. `_min_area_rect` contains every member, so
    the merge can only ever grow what is covered -- which is the direction this sub-project's whole
    promise runs in. A single-member cluster keeps its own quad untouched.

    This de-duplicates the first pass against ITSELF as well as against its 2x twins (review M-2):
    the ruling clusters the set, and two overlapping detections of one painted line in a single pass
    are the same duplicate by the same measure."""
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
    members: dict[int, list[int]] = {}
    for index, line in enumerate(lines):
        cluster = root(index)
        members.setdefault(cluster, []).append(index)
        chosen = best.get(cluster)
        if chosen is None or _rank(line) < _rank(lines[chosen]):
            best[cluster] = index

    merged: list[Line] = []
    for index in sorted(best.values()):
        winner = lines[index]
        group = members[root(index)]
        if len(group) == 1:
            merged.append(winner)
        else:
            footprint = _min_area_rect([point for i in group for point in lines[i].quad])
            merged.append(Line(winner.text, winner.confidence, footprint))
    return merged


def read_text(image: Image.Image) -> list[Line]:
    """Every line the engine finds, plus a second pass on a 2x upscale whenever the first pass saw
    a short line or nothing at all. The second pass's coordinates are halved back into display
    space, and lines whose quads overlap by `DUPLICATE_IOU` or more collapse to ONE line: the most
    confident one's text, over the whole cluster's footprint.

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
        halved = [Line(line.text, line.confidence, [(x / 2, y / 2) for x, y in line.quad])
                  for line in found]
        # `_merge` is INSIDE the envelope (review round 3, m-2). It reads the engine's own
        # coordinates, so a quad outside `Engine.run`'s declared `list[tuple[float, float]]` --
        # a list of lists, say -- raises from the geometry, and review M2 already ruled that
        # `app/tasks/media.py` may never be handed something it has no reason code for.
        return _merge(lines + halved)
    except Exception as exc:  # the engine's own failures are not a documented, catchable set
        raise OcrError("OCR_ERROR") from exc
