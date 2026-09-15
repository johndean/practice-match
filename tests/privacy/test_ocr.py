"""The OCR adapter (spec 2026-09-09 C.5 step 2). Directive 4: "Run OCR against EVERY image." An
engine error is therefore a FAILURE, never a skip -- that distinction is what this suite pins.

No model is downloaded and no network is touched: every case loads the stub engine through
`PRIVACY_ENGINE_MODULE`, which is the same seam the Playwright launcher uses."""
from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import itertools
import math
import random
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
    second = ocr.Line("HILLCOUNTRYVET", 0.99, _quad(11.0, 10.0, 199.0, 23.0))   # the 2x pass, halved
    engine = _TwoPass([first], [ocr.Line("HILLCOUNTRYVET", 0.99, _quad(22.0, 20.0, 398.0, 46.0))])
    monkeypatch.setattr("app.privacy.ocr._LOADED", engine)

    lines = ocr.read_text(_image())
    assert len(lines) == 1
    # The two readings tie at 0.99, so `_rank` falls to the larger quad — the 2x reading's, by
    # 2444 px against 2280 (review M-6: a tie may not be decided by which one arrived first).
    assert (lines[0].text, lines[0].confidence) == ("HILLCOUNTRYVET", 0.99)
    # …and the quad is the CLUSTER's footprint, which covers both readings (review I-1).
    assert _covers(lines[0].quad, first.quad) and _covers(lines[0].quad, second.quad)


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


def _rotated_about(quad: list[tuple[float, float]], degrees: float,
                   cx: float, cy: float) -> list[tuple[float, float]]:
    """`quad` turned about an arbitrary centre, so two quads can share one."""
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    return [(cx + (x - cx) * cos - (y - cy) * sin, cy + (x - cx) * sin + (y - cy) * cos)
            for x, y in quad]


def _rotated(x0: float, y0: float, x1: float, y1: float, degrees: float) -> list[tuple[float, float]]:
    """`_quad` turned about its own centre — a sign photographed at an angle, which is the only
    thing the four-point quad exists for and the one shape the suite never had."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    return [(cx + (x - cx) * cos - (y - cy) * sin, cy + (x - cx) * sin + (y - cy) * cos)
            for x, y in _quad(x0, y0, x1, y1)]


def test_two_stacked_lines_on_an_angled_sign_are_both_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review N2. A practice name and the line beneath it, on a sign photographed at 45 degrees:
    their polygons do not touch — the true intersection is exactly zero — but their AXIS-ALIGNED
    bounding boxes overlap by 0.5436, so a bbox rule merged them and the second line produced no
    redaction region. The same miss as I1 (a), reached by rotation instead of by identical text.

    De-duplication is therefore on the QUADS themselves; the bounding boxes survive only as a cheap
    pre-check that can answer "no" and never "yes"."""
    top = _rotated(10.0, 10.0, 210.0, 30.0, 45.0)
    below = _rotated(10.0, 56.0, 210.0, 76.0, 45.0)
    assert ocr._iou(top, below) == 0.0, "the two lines do not overlap at all"

    # Nothing at display size and both lines on the 2x pass — `read_text`'s own second trigger,
    # and the realistic one for small angled text.
    engine = _TwoPass([], [ocr.Line("TOP LINE", 0.9, [(x * 2, y * 2) for x, y in top]),
                           ocr.Line("SECOND LINE", 0.9, [(x * 2, y * 2) for x, y in below])])
    monkeypatch.setattr("app.privacy.ocr._LOADED", engine)
    assert [line.text for line in ocr.read_text(_image())] == ["TOP LINE", "SECOND LINE"]


def test_two_lines_that_merely_graze_each_other_are_both_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review N3, the over-merge half of the threshold, which nothing gated: every de-dup case used
    either a near-exact pair (IoU 0.91) or a fully disjoint one, and a disjoint pair short-circuits
    before the ratio is ever computed. A pair that genuinely overlaps BELOW the threshold is the
    whole reason `DUPLICATE_IOU` is 0.5 rather than 0.01 — two lines of a stacked sign whose
    ascenders clip each other are two regions, not one."""
    upper = _quad(10.0, 10.0, 210.0, 40.0)
    lower = _quad(10.0, 26.0, 210.0, 56.0)
    assert ocr._iou(upper, lower) == pytest.approx(0.3043, abs=1e-4)

    engine = _TwoPass([], [ocr.Line("UPPER", 0.9, [(x * 2, y * 2) for x, y in upper]),
                           ocr.Line("LOWER", 0.9, [(x * 2, y * 2) for x, y in lower])])
    monkeypatch.setattr("app.privacy.ocr._LOADED", engine)
    assert [line.text for line in ocr.read_text(_image())] == ["UPPER", "LOWER"]


def test_a_chain_of_overlapping_detections_answers_the_same_whatever_order_it_arrives_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review N4. The greedy first-wins loop this replaces compared each second-pass line against
    the lines it had ALREADY kept, so with three chained detections of one region — A overlaps B, B
    overlaps C, A does not overlap C — the answer depended on the order the engine happened to
    return them in: A,B,C kept two lines and B,A,C kept one, from the same input.

    Clusters are built by transitive overlap and the most confident member of each survives, so the
    answer is a function of the SET of detections and of nothing else."""
    a = _quad(10.0, 10.0, 210.0, 40.0)
    b = _quad(10.0, 19.0, 210.0, 49.0)
    c = _quad(10.0, 28.0, 210.0, 58.0)
    assert ocr._iou(a, b) >= ocr.DUPLICATE_IOU and ocr._iou(b, c) >= ocr.DUPLICATE_IOU
    assert ocr._iou(a, c) < ocr.DUPLICATE_IOU

    detections = {"A": (0.70, a), "B": (0.90, b), "C": (0.80, c)}
    answers = set()
    for order in itertools.permutations("ABC"):
        engine = _TwoPass([], [ocr.Line(name, conf, [(x * 2, y * 2) for x, y in quad])
                               for name in order for conf, quad in [detections[name]]])
        monkeypatch.setattr("app.privacy.ocr._LOADED", engine)
        answers.add(tuple(sorted(line.text for line in ocr.read_text(_image()))))
    assert answers == {("B",)}, answers


def _area(polygon: list[tuple[float, float]]) -> float:
    """The shoelace area, computed here so a test never measures with the code under test."""
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                   in zip(polygon, polygon[1:] + polygon[:1], strict=True))) / 2.0


def _covers(outer: list[tuple[float, float]], inner: list[tuple[float, float]]) -> bool:
    """Whether every vertex of `inner` lies inside (or on) the convex polygon `outer`.

    Computed here rather than borrowed from the module under test, and winding-agnostic — a point
    is inside a convex polygon when it is on the SAME side of every edge, whichever way round the
    vertices were given."""
    edges = list(zip(outer, outer[1:] + outer[:1], strict=True))
    for px, py in inner:
        sides = [(bx - ax) * (py - ay) - (by - ay) * (px - ax) for (ax, ay), (bx, by) in edges]
        if not (all(s >= -1e-9 for s in sides) or all(s <= 1e-9 for s in sides)):
            return False
    return True


def test_a_merged_line_covers_the_whole_cluster_not_just_the_winners_quad(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review I-1, and the one place this task has lost coverage rather than gained it.

    The first pass reads the whole line `HILL COUNTRY VET` at 18 px (x 100..420, conf 0.62 — 18 px
    is what triggers the 2x pass); the 2x pass segments it differently, answers `HILL COUNTRY` over
    x 100..340 alone at conf 0.95, and answers the tail NOWHERE, because the wheel drops any
    recognition under its own `text_score` of 0.5. Keeping the winner's own QUAD returned the
    partial: the 80 px carrying `VET` — text the engine FOUND at display size — produced no region,
    and under NOT_SHOW nothing filled it. P5 pads by 12 px, which leaves 68 of those 80 bare.

    So the representative decides the TEXT and the CONFIDENCE (ruling A-IDP-11, review N4) and the
    CLUSTER decides the QUAD: the footprint of every member, which can only ever grow."""
    full = _quad(100.0, 10.0, 420.0, 28.0)
    partial = _quad(100.0, 10.0, 340.0, 28.0)
    engine = _TwoPass([ocr.Line("HILL COUNTRY VET", 0.62, full)],
                      [ocr.Line("HILL COUNTRY", 0.95, [(x * 2, y * 2) for x, y in partial])])
    monkeypatch.setattr("app.privacy.ocr._LOADED", engine)

    lines = ocr.read_text(_image())
    assert [line.text for line in lines] == ["HILL COUNTRY"], "the representative is the confident one"
    assert lines[0].confidence == 0.95
    assert len(lines[0].quad) == 4, "`Line`'s four-point contract survives the merge"
    assert _covers(lines[0].quad, full), "the footprint must still span the whole first-pass line"
    assert _covers(lines[0].quad, partial)


def test_a_chain_of_shifted_detections_is_covered_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same loss, amplified: seven detections of one region each offset 9 px keep a 30 px quad
    for an 84 px footprint. The cluster's own extent is what a caller is handed."""
    members = [ocr.Line(f"L{i}", 0.5 + i / 100, _quad(10.0, 10.0 + 9 * i, 210.0, 40.0 + 9 * i))
               for i in range(7)]
    monkeypatch.setattr("app.privacy.ocr._LOADED", _TwoPass([], [
        ocr.Line(m.text, m.confidence, [(x * 2, y * 2) for x, y in m.quad]) for m in members]))

    lines = ocr.read_text(_image())
    assert len(lines) == 1
    assert all(_covers(lines[0].quad, member.quad) for member in members)
    assert min(y for _, y in lines[0].quad) == pytest.approx(10.0)
    assert max(y for _, y in lines[0].quad) == pytest.approx(94.0)


def test_two_overlapping_readings_in_ONE_pass_collapse_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review M-2, a characterisation: the ruling clusters the SET, so the first pass is
    de-duplicated against itself and not only against its 2x twins. A caller can therefore receive
    FEWER lines than the engine returned, which the report's caller-facing sentence used to describe
    in one direction only. `engine.seen` proves no second pass ran — both detections are the first
    pass's own."""
    class OnePass:
        def __init__(self) -> None:
            self.seen: list[tuple[int, int]] = []

        def run(self, image: Image.Image) -> list[ocr.Line]:
            self.seen.append(image.size)
            return [ocr.Line("HILL COUNTRY", 0.90, _quad(10.0, 10.0, 210.0, 53.0)),
                    ocr.Line("HILL COUNTRY VET", 0.85, _quad(10.0, 10.0, 310.0, 53.0))]

    engine = OnePass()
    monkeypatch.setattr("app.privacy.ocr._LOADED", engine)
    lines = ocr.read_text(_image())
    assert engine.seen == [(800, 600)], "no second pass: both lines are 43 px tall"
    assert [line.text for line in lines] == ["HILL COUNTRY"], "the more confident reading represents"
    # …and I-1's footprint is what stops the collapse losing the tail it did not read.
    assert _covers(lines[0].quad, _quad(10.0, 10.0, 310.0, 53.0))


def test_a_quad_wound_the_other_way_measures_the_same(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review M-3 and M-7. `_iou` hulls both arguments, which is the module's single normaliser:
    it fixes the winding an engine may answer either way round, and it fixes the ORDER — a
    rectangle whose corners arrive crosswise is a bow-tie whose shoelace area is zero, and it used
    to score 0.0 against the same rectangle written properly, so every 2x twin would have survived
    as a duplicate. Neither was gated: every quad the suite built was wound the same way."""
    upright = _quad(10.0, 10.0, 210.0, 40.0)
    assert ocr._iou(upright, upright[::-1]) == pytest.approx(1.0)
    assert ocr._iou(upright, [(10.0, 10.0), (210.0, 40.0), (210.0, 10.0), (10.0, 40.0)]) == pytest.approx(1.0)

    reversed_twin = ocr.Line("B", 0.8, _quad(11.0, 10.0, 209.0, 41.0)[::-1])
    monkeypatch.setattr("app.privacy.ocr._LOADED",
                        _TwoPass([], [ocr.Line("A", 0.9, [(x * 2, y * 2) for x, y in upright]),
                                      ocr.Line(reversed_twin.text, 0.8,
                                               [(x * 2, y * 2) for x, y in reversed_twin.quad])]))
    assert [line.text for line in ocr.read_text(_image())] == ["A"]


def test_a_confidence_tie_is_broken_by_area_whichever_way_the_quad_is_wound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review M-6 and M-3's second half. A tie goes to the LARGER quad — the fuller reading, the
    safer one to carry — and never to whichever arrived first. `_area` is unsigned for exactly this
    reason: the larger member here is wound clockwise, so a signed area would rank it as the
    smallest thing in the cluster and hand the region to the shorter reading."""
    small = ocr.Line("SMALL", 0.9, _quad(10.0, 10.0, 200.0, 22.0))
    large = ocr.Line("LARGE", 0.9, _quad(11.0, 10.0, 199.0, 23.0)[::-1])   # clockwise, and bigger
    for order in ((small, large), (large, small)):
        monkeypatch.setattr("app.privacy.ocr._LOADED", _TwoPass(
            [], [ocr.Line(m.text, m.confidence, [(x * 2, y * 2) for x, y in m.quad]) for m in order]))
        assert [line.text for line in ocr.read_text(_image())] == ["LARGE"], order


def test_a_merged_cluster_of_angled_readings_takes_an_angled_footprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The footprint is the smallest rectangle at ANY angle, not the axis-aligned box: two readings
    of one sign photographed at 45 degrees are covered by a tilted rectangle a fraction of the size
    of their upright bounding box, so a merge on angled signage does not black out the frame."""
    one = _rotated(10.0, 10.0, 210.0, 40.0, 45.0)
    two = _rotated(14.0, 12.0, 214.0, 42.0, 45.0)
    monkeypatch.setattr("app.privacy.ocr._LOADED", _TwoPass(
        [], [ocr.Line("A", 0.9, [(x * 2, y * 2) for x, y in one]),
             ocr.Line("B", 0.8, [(x * 2, y * 2) for x, y in two])]))

    lines = ocr.read_text(_image())
    assert len(lines) == 1 and _covers(lines[0].quad, one) and _covers(lines[0].quad, two)
    x0, y0, x1, y1 = ocr._bbox(lines[0].quad)
    assert _area(lines[0].quad) < 0.5 * (x1 - x0) * (y1 - y0), "an upright box would be twice the size"


def test_the_threshold_is_bounded_by_its_two_boundary_cases_and_by_nothing_narrower() -> None:
    """Review M-9, stated rather than hidden: the suite BOUNDS `DUPLICATE_IOU` and does not pin it.
    The grazing pair must not merge and the chain's links must, which leaves every value in
    (0.3043, 0.5385] passing — 0.35 ships green today. A-IDP-11 ruled the RULE and not the number,
    so a retune is legal; this is what makes it move the band and both boundary cases together
    instead of drifting through one of them."""
    graze = ocr._iou(_quad(10.0, 10.0, 210.0, 40.0), _quad(10.0, 26.0, 210.0, 56.0))
    chain = ocr._iou(_quad(10.0, 10.0, 210.0, 40.0), _quad(10.0, 19.0, 210.0, 49.0))
    assert (graze, chain) == (pytest.approx(0.3043, abs=1e-4), pytest.approx(0.5385, abs=1e-4))
    assert graze < ocr.DUPLICATE_IOU <= chain


def test_a_merged_footprint_can_only_ever_grow_what_is_covered() -> None:
    """The PROPERTY behind review I-1, over random clusters rather than one fixture.

    Whatever `_merge` hands back for a cluster must contain every member of it. That is the whole
    direction this sub-project runs in: a de-duplication rule may decide which TEXT is carried, and
    it may never shrink the area a redaction would fill. Checked here against quads at arbitrary
    angles, offsets and sizes, and against the area too — the footprint is never smaller than the
    largest member it replaced."""
    rng = random.Random(20260914)
    for _ in range(300):
        cluster = [ocr.Line(f"L{i}", rng.random(),
                            _rotated(x := rng.uniform(0, 400), y := rng.uniform(0, 400),
                                     x + rng.uniform(20, 300), y + rng.uniform(8, 60),
                                     rng.uniform(0, 360)))
                   for i in range(rng.randint(2, 6))]
        footprint = ocr._min_area_rect([point for line in cluster for point in line.quad])
        assert len(footprint) == 4
        for member in cluster:
            assert _covers(footprint, member.quad), (footprint, member.quad)
            assert _area(footprint) >= _area(member.quad) - 1e-9


def test_the_last_tie_break_term_is_the_text_and_it_decides_the_same_way_in_either_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review round 3, I-2: `_rank`'s THIRD term is what the ruling names as making the tie total,
    and it was the one term no mutation could kill — replacing it with `""` left the whole suite
    green while the surviving TEXT followed arrival order.

    The triggering shape is this suite's own, not a contrivance. Equal confidence is routine (two
    readings of one sign at 0.99). Equal area is routine too, and EXACT: the 2x pass's coordinates
    are divided by two, so a doubled quad halves back onto its first-pass twin as the identical
    tuple — which is the premise two other cases here are built on. Different text is the case the
    whole de-duplication rule exists for: the real wheel answered `HILL COUNTRYVET` at display size
    and `HILLCOUNTRYVET` at 2x for one painted line. `(-0.99, -2280.0, text)` against
    `(-0.99, -2280.0, other)` is decided by the text and by nothing else.

    Only the SPELLING handed onward is at stake — the quad is the cluster's footprint either way and
    the confidences are equal — but P5's identity matcher is what receives it, and which of two
    spellings that is may not depend on the order an engine happened to answer in."""
    quad = _quad(10.0, 10.0, 200.0, 22.0)
    first = ocr.Line("HILL COUNTRYVET", 0.99, quad)
    twin = ocr.Line("HILLCOUNTRYVET", 0.99, quad)          # identical quad, so identical area
    assert _area(first.quad) == _area(twin.quad)

    answers = set()
    for order in ((first, twin), (twin, first)):
        monkeypatch.setattr("app.privacy.ocr._LOADED", _TwoPass(
            [], [ocr.Line(m.text, m.confidence, [(x * 2, y * 2) for x, y in m.quad]) for m in order]))
        lines = ocr.read_text(_image())
        assert len(lines) == 1
        answers.add(lines[0].text)
    assert answers == {"HILL COUNTRYVET"}, answers


def test_a_pair_exactly_on_the_threshold_decides_the_same_way_in_either_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review round 3, m-1. `_merge` asks `_iou(lines[i].quad, lines[j].quad)` for `i < j`, so which
    quad is the Sutherland-Hodgman SUBJECT and which the CLIPPER followed arrival order, and the two
    answers differ in the last bit. Invisible everywhere except exactly at `DUPLICATE_IOU`, where
    `>=` flips: a 150x20 reading wholly inside a 200x30 one is intersection 3000 over union 6000 —
    exactly 0.5 — and measured 0.49999999999999994 one way against 0.5000000000000001 the other, so
    the same two detections merged or did not according to which arrived first.

    No coverage was at stake either way (merged, the footprint covers both; unmerged, both are
    kept), but a count and a text that change with arrival order are not a function of the set.
    Measure-zero on the wheel's own float coordinates and 4.5 % on round-number geometry, which is
    what every stub engine here and any vector source produces."""
    # A 100x26 reading and its own left half, both turned 7 degrees about their shared corner. The
    # rotation is what puts the arithmetic where the two orders disagree: measured before the fix,
    # 0.5000000000000002 one way (MERGE, one line back) against 0.4999999999999999 the other (do
    # not, two lines back).
    #
    # A POPULATION RATE FOR THAT FLIP NEEDS ITS GENERATOR, and the two this comment used to quote
    # (380 of 4,000 here, 89 of 2,000 in the review) had none -- the same 4,000 pairs give anything
    # from 3.1 % to 17.9 % depending only on how large the coordinates are, because that is what
    # sets the ULP (fan-in m-A). The generator, and the rate that belongs to it, are written out in
    # full at `_iou`'s own `sorted(...)` line: in short, this exact shape placed uniformly in a
    # 1000x800 frame at a uniform angle flips 172-182 of 4,000 over five seeds without the fix and
    # 0 of 4,000 with it. The dependence on arrival order is what belonged to `_iou`, and this case
    # pins it on one pair rather than on a population -- which is why the assertions below are an
    # exact equality and not a rate.
    outer = _rotated_about(_quad(60.0, 50.0, 160.0, 76.0), 7.0, 60.0, 50.0)
    inner = _rotated_about(_quad(60.0, 50.0, 110.0, 76.0), 7.0, 60.0, 50.0)
    assert _area(inner) * 2 == pytest.approx(_area(outer)), "3000 inside 6000 — the exact knife-edge"
    assert ocr._iou(outer, inner) == pytest.approx(ocr.DUPLICATE_IOU)
    # The fix is a CANONICAL ORDER, not a tolerance: `_iou` sorts the two hulls before clipping, so
    # both calls do identical arithmetic. A tolerance would have moved the threshold instead of
    # removing the dependence, and left the same flip one epsilon further out.
    assert ocr._iou(outer, inner) == ocr._iou(inner, outer)

    counts = set()
    for order in ((outer, inner), (inner, outer)):
        monkeypatch.setattr("app.privacy.ocr._LOADED", _TwoPass(
            [], [ocr.Line("X", 0.9, [(x * 2, y * 2) for x, y in quad]) for quad in order]))
        counts.add(len(ocr.read_text(_image())))
    assert len(counts) == 1, f"the same set answered {counts} depending on arrival order"


def test_a_quad_carrying_a_nan_is_its_own_line_and_never_a_division_by_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review round 3, m-2. A NaN coordinate slips through `_boxes_overlap` — every comparison
    against NaN is False, so `min`/`max` answer the finite operand and the pre-check says "overlap"
    — and then hulls to nothing, which made `_iou`'s union exactly zero and raised a raw
    `ZeroDivisionError` straight past `read_text`'s `OcrError` envelope.

    A quad nobody can measure is a quad nobody can merge, so it clusters with nothing and keeps its
    place in the answer — `app/privacy/ocr.py`'s own version of the rule A25 states for a listing
    with no coordinates: a missing point omits the pin and never fabricates one."""
    good = ocr.Line("GOOD", 0.9, _quad(10.0, 10.0, 210.0, 40.0))
    nowhere = (float("nan"), float("nan"))
    broken = ocr.Line("NAN", 0.8, [nowhere, nowhere, nowhere, nowhere])
    assert ocr._iou(good.quad, broken.quad) == 0.0 == ocr._iou(broken.quad, good.quad)

    monkeypatch.setattr("app.privacy.ocr._LOADED", _TwoPass(
        [], [ocr.Line(m.text, m.confidence, [(x * 2, y * 2) for x, y in m.quad]) for m in (good, broken)]))
    assert [line.text for line in ocr.read_text(_image())] == ["GOOD", "NAN"]


def test_a_quad_outside_the_engine_contract_is_an_error_and_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of m-2. `Engine.run` declares `list[tuple[float, float]]`; an engine that
    answers a list of LISTS is outside that contract, and the geometry's own `set(points)` then
    raises `TypeError: unhashable type: 'list'`. `_merge` used to run OUTSIDE `read_text`'s
    `except Exception -> OcrError`, so it escaped with no reason code — the exact shape review M2
    ruled out for the lazy-iterable engine, reintroduced by a later round's own helper."""
    class Unhashable:
        def run(self, image: Image.Image) -> list[ocr.Line]:
            return [ocr.Line("A", 0.9, [[10.0, 10.0], [210.0, 10.0], [210.0, 22.0], [10.0, 22.0]]),
                    ocr.Line("B", 0.8, [[11.0, 10.0], [209.0, 10.0], [209.0, 23.0], [11.0, 23.0]])]

    monkeypatch.setattr("app.privacy.ocr._LOADED", Unhashable())
    with pytest.raises(ocr.OcrError):
        ocr.read_text(_image())


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


def test_an_absent_distribution_leaves_the_module_importable_and_the_reason_code_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review N1. `ENGINE` reads the installed version (I2), and reading it at import meant that a
    process whose image does not carry the wheel died on `import app.privacy.ocr` with a raw
    `PackageNotFoundError` — so `OcrUnavailable`, the reason code that exists to REPORT exactly that
    deployment, became unreachable. `test_a_missing_wheel_is_unavailable_rather_than_a_traceback`
    cannot see it: it simulates a missing MODULE (`sys.modules[...] = None`), not a missing
    DISTRIBUTION.

    Importing an adapter never raises. The version is looked up behind a guard, the constant keeps
    its `<name>/<version>` shape with `unavailable` where a version would be, and the engine's
    absence is still reported through the reason code."""
    def raiser(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr("importlib.metadata.version", raiser)
    # Executed a second time WITHOUT registering it (review M-1). `import_module` after a
    # `delitem` makes Python's own loader `setattr` the fresh module onto the `app.privacy`
    # PACKAGE, which monkeypatch does not undo — after which every later string-path patch in
    # this file (`"app.privacy.ocr._LOADED"`, the autouse `_stub`) resolved to the fresh module while
    # the module-level `ocr` binding ran the original. The suite was green by position
    # alone: reversed, it was 14 failed of 20 here and 5 of 15 in the twin.
    spec = importlib.util.find_spec("app.privacy.ocr")
    assert spec is not None and spec.loader is not None
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)

    assert fresh.ENGINE == "rapidocr-onnxruntime/unavailable"
    monkeypatch.setattr(fresh.settings, "privacy_engine_module", None)
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", None)
    with pytest.raises(fresh.OcrUnavailable):
        fresh.read_text(_image())


def test_the_engine_name_is_recorded_for_the_privacy_row() -> None:
    """Spec C.3 gives `ocr.engine` its reason: "so a record says which engine produced it". A
    hard-coded version cannot keep that promise — `pyproject.toml` admits `<2.0.0`, and Task P6
    re-runs `poetry lock`, so a resolved 1.5.x would leave every privacy row from then on naming an
    engine that did not produce it while every gate stayed green (review I2). The constant and the
    installed distribution move together or this goes red."""
    assert ocr.ENGINE == f"rapidocr-onnxruntime/{importlib.metadata.version('rapidocr-onnxruntime')}"
