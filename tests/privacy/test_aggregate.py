"""Region aggregation (spec 2026-09-09 C.5 step 5; directive 4 step 5, 5).

Directive 5: "Where necessary, expand the redaction region sufficiently to prevent surrounding
pixels from reconstructing the identifying information", and "Do NOT crop away important image
content unnecessarily". Those two pull against each other, and the numbers below are the spec's
answer: a quarter of the shorter side for text, a fifth per side for a vision box (whose
coordinates are approximate), and a merge of anything within 8 px so a sign is one block rather
than a picket fence that leaks its letter count."""
from __future__ import annotations

from typing import Any

import pytest

from app.privacy import aggregate
from app.privacy.barcodes import Symbol
from app.privacy.identity import Match
from app.privacy.ocr import Line

SIZE = (1600, 1200)


def _line(text: str, x0: float, y0: float, x1: float, y1: float) -> Line:
    return Line(text, 0.95, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _box(region: dict[str, Any]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in region["polygon"]]
    ys = [p[1] for p in region["polygon"]]
    return min(xs), min(ys), max(xs), max(ys)


def test_a_matched_line_becomes_one_padded_auto_region() -> None:
    lines = [_line("HILL COUNTRY ANIMAL HOSPITAL", 100, 100, 500, 140)]
    detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("name", 0, "exact", 1.0)], symbols=[], vision={"status": "unavailable"},
        size=SIZE)
    assert [d["source"] for d in detected] == ["ocr_match"]
    assert len(redaction) == 1 and redaction[0]["source"] == "auto" and redaction[0]["expanded_from"] == 0
    x0, y0, x1, y1 = _box(redaction[0])
    pad = max(aggregate.OCR_PAD_MIN, round(40 * aggregate.OCR_PAD_FRACTION))   # 40 px is the shorter side
    assert (x0, y0, x1, y1) == (100 - pad, 100 - pad, 500 + pad, 140 + pad)


def test_an_unmatched_line_is_not_a_region_and_a_regex_line_is() -> None:
    """"each hit is an identifying region regardless of matching" -- but a line that matched
    nothing and hit no class is just a word on a wall."""
    lines = [_line("PLEASE KEEP DOGS ON A LEAD", 10, 10, 300, 40), _line("(512) 555-0100", 10, 60, 200, 90)]
    _detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("regex:phone", 1, "regex", 1.0)], symbols=[],
        vision={"status": "unavailable"}, size=SIZE)
    assert len(redaction) == 1 and _box(redaction[0])[1] > 40


def test_every_symbol_is_a_region_and_is_expanded_about_its_centroid() -> None:
    symbol = Symbol("QRCode", "url", [(100.0, 100.0), (200.0, 100.0), (200.0, 200.0), (100.0, 200.0)])
    detected, redaction = aggregate.regions_for(lines=[], matches=[], symbols=[symbol],
                                                vision={"status": "unavailable"}, size=SIZE)
    assert [d["source"] for d in detected] == ["barcode"]
    x0, y0, x1, y1 = _box(redaction[0])
    # `pytest.approx`, not `==`: `_scaled` computes `(100.0 * 1.15) / 2` as 57.499999999999993 and
    # the width back out as 115.0, while `100 * 1.15` is 114.99999999999999. Both are correct
    # IEEE754 and they are not equal; asserting bit equality on a scaled float is a test that fails
    # for arithmetic rather than for behaviour.
    assert (x1 - x0) == pytest.approx(100 * aggregate.BARCODE_EXPAND)
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((150.0, 150.0))


def test_a_vision_box_is_padded_more_because_its_coordinates_are_approximate() -> None:
    vision = {"status": "ok", "identifies_practice": True,
              "regions": [{"kind": "logo", "label": "wall logo", "box": [400, 400, 600, 500],
                           "confidence": "low"}]}
    _detected, redaction = aggregate.regions_for(lines=[], matches=[], symbols=[], vision=vision, size=SIZE)
    x0, _y0, x1, _y1 = _box(redaction[0])
    assert x0 == 400 - max(aggregate.VISION_PAD_MIN, round(200 * aggregate.VISION_PAD_FRACTION))
    assert x1 == 600 + max(aggregate.VISION_PAD_MIN, round(200 * aggregate.VISION_PAD_FRACTION))


def test_every_confidence_is_filled_because_the_seller_removes_what_is_unnecessary() -> None:
    vision = {"status": "ok", "identifies_practice": True, "regions": [
        {"kind": "signage", "label": "a", "box": [10, 10, 60, 40], "confidence": "low"},
        {"kind": "logo", "label": "b", "box": [800, 800, 900, 900], "confidence": "high"}]}
    _detected, redaction = aggregate.regions_for(lines=[], matches=[], symbols=[], vision=vision, size=SIZE)
    assert len(redaction) == 2


def test_two_lines_of_one_sign_merge_into_one_polygon() -> None:
    """A picket fence of per-line boxes leaks the shape of the words between them."""
    lines = [_line("HILL COUNTRY", 100, 100, 400, 140), _line("ANIMAL HOSPITAL", 100, 146, 400, 186)]
    _detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("name", 0, "distinctive", 0.8), Match("name", 1, "token_set", 0.7)],
        symbols=[], vision={"status": "unavailable"}, size=SIZE)
    assert len(redaction) == 1
    _x0, y0, _x1, y1 = _box(redaction[0])
    assert y0 <= 100 - aggregate.OCR_PAD_MIN and y1 >= 186 + aggregate.OCR_PAD_MIN


def test_a_region_is_clamped_to_the_image() -> None:
    lines = [_line("HILL COUNTRY ANIMAL HOSPITAL", 0, 0, 200, 30)]
    _detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("name", 0, "exact", 1.0)], symbols=[],
        vision={"status": "unavailable"}, size=(300, 200))
    x0, y0, x1, y1 = _box(redaction[0])
    assert (x0, y0) == (0, 0) and x1 <= 300 and y1 <= 200


def test_the_same_inputs_give_the_same_output_every_time() -> None:
    """Directive 23's "deterministic processing", and what makes a regeneration reproducible."""
    lines = [_line("HILL COUNTRY ANIMAL HOSPITAL", 100, 100, 500, 140), _line("(512) 555-0100", 20, 900, 300, 940)]
    args: dict[str, Any] = {"lines": lines,
                            "matches": [Match("name", 0, "exact", 1.0), Match("regex:phone", 1, "regex", 1.0)],
                            "symbols": [], "vision": {"status": "unavailable"}, "size": SIZE}
    first = aggregate.regions_for(**args)
    second = aggregate.regions_for(**args)
    assert [r["polygon"] for r in first[1]] == [r["polygon"] for r in second[1]]
    assert [r["polygon"] for r in first[0]] == [r["polygon"] for r in second[0]]


def test_fillable_excludes_what_the_seller_removed_and_keeps_what_they_added() -> None:
    regions = [
        {"id": "1", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]], "source": "auto"},
        {"id": "2", "polygon": [[20, 20], [30, 20], [30, 30], [20, 30]], "source": "removed-by-seller"},
        {"id": "3", "polygon": [[40, 40], [50, 40], [50, 50], [40, 50]], "source": "manual"},
    ]
    assert [p[0] for p in aggregate.fillable(regions)] == [(0, 0), (40, 40)]


def test_the_in_place_re_run_replaces_the_auto_set_but_unions_it_on_a_confirmed_row() -> None:
    """Spec C.5: on an unconfirmed row the fresh scan REPLACES the auto set; on a confirmed row the
    two are UNIONED, so the new derivative hides a superset of what the seller confirmed and
    nothing they never saw is revealed. The seller's own regions carry forward by id either way,
    and a new auto region inside a removed one is recorded and not filled."""
    old = [{"id": "a1", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]], "source": "auto"},
           {"id": "m1", "polygon": [[90, 90], [99, 90], [99, 99], [90, 99]], "source": "manual"},
           {"id": "r1", "polygon": [[40, 40], [60, 40], [60, 60], [40, 60]], "source": "removed-by-seller"}]
    fresh = [{"id": "a2", "polygon": [[20, 20], [30, 20], [30, 30], [20, 30]], "source": "auto"},
             {"id": "a3", "polygon": [[45, 45], [55, 45], [55, 55], [45, 55]], "source": "auto"}]

    unconfirmed = aggregate.union_auto(old, fresh, confirmed=False)
    assert {r["id"] for r in unconfirmed} == {"a2", "m1", "r1"}          # a1 gone, a3 inside r1
    confirmed = aggregate.union_auto(old, fresh, confirmed=True)
    assert {r["id"] for r in confirmed} == {"a1", "a2", "m1", "r1"}      # a1 kept -- never fewer
    assert all(r["source"] != "auto" or r["id"] != "a3" for r in confirmed)


# ---------------------------------------------------------------------------------------------
# An unmeasurable detection (Task P7 brief; `app/privacy/ocr.py::_iou`'s own warning).
#
# "`_iou` can answer NaN for an unmeasurable quad, and every caller's comparison must be written so
# that NaN means DO NOT MERGE. A comparison written the other way round would silently merge
# regions it cannot measure." `_near` IS such a comparison and it is written the other way round --
# it has to be, because `not (... or ...)` is the only spelling in which two DISJOINT boxes answer
# False. So the polarity is not fixed at the comparison; the value is refused at the one door every
# detection enters by, and these cases pin both halves of that.
# ---------------------------------------------------------------------------------------------

NOT_A_NUMBER = float("nan")


def test_the_merge_comparison_absorbs_an_unmeasurable_box_which_is_why_it_must_never_see_one() -> None:
    """The hazard, stated rather than implied. Every comparison against a NaN is False, so
    `not (False or False or False or False)` is True: an unmeasurable box merges with a region on
    the far side of the photograph, and the merged box is unmeasurable too. `_near` is correct for
    every finite input and cannot be spelled to answer False here without breaking the disjoint
    case, so what protects it is that `regions_for` refuses the value first."""
    far = (900.0, 900.0, 950.0, 950.0)
    assert aggregate._near((NOT_A_NUMBER,) * 4, far) is True
    assert aggregate._near((0.0, 0.0, 10.0, 10.0), far) is False


def test_an_unmeasurable_ocr_quad_is_refused_and_not_merged() -> None:
    lines = [Line("HILL COUNTRY ANIMAL HOSPITAL", 0.95,
                  [(NOT_A_NUMBER, 100.0), (500.0, 100.0), (500.0, 140.0), (100.0, 140.0)])]
    with pytest.raises(aggregate.UnmeasurableRegion, match="AGGREGATE_UNMEASURABLE: ocr_match"):
        aggregate.regions_for(lines=lines, matches=[Match("name", 0, "exact", 1.0)], symbols=[],
                              vision={"status": "unavailable"}, size=SIZE)


def test_an_unmeasurable_ordinate_the_bounds_would_have_dropped_is_refused_too() -> None:
    """The SILENT half, and the reason the check walks every vertex rather than the bounding box.
    `min`/`max` answer the finite operand whenever the NaN is not the first value they see -- so
    `_bounds` on this quad returns (100, 100, 500, 140), the box of its other three corners, and
    the region would have been drawn one corner short of the sign with nothing raised anywhere."""
    quad = [(100.0, 100.0), (500.0, 100.0), (500.0, 140.0), (100.0, NOT_A_NUMBER)]
    assert aggregate._bounds(quad) == (100.0, 100.0, 500.0, 140.0), "the premise: the NaN is dropped"
    with pytest.raises(aggregate.UnmeasurableRegion):
        aggregate.regions_for(lines=[Line("HILL COUNTRY", 0.95, quad)],
                              matches=[Match("name", 0, "exact", 1.0)], symbols=[],
                              vision={"status": "unavailable"}, size=SIZE)


def test_an_unmeasurable_symbol_quad_is_refused() -> None:
    symbol = Symbol("QRCode", "url", [(100.0, 100.0), (float("inf"), 100.0), (200.0, 200.0), (100.0, 200.0)])
    with pytest.raises(aggregate.UnmeasurableRegion, match="barcode"):
        aggregate.regions_for(lines=[], matches=[], symbols=[symbol],
                              vision={"status": "unavailable"}, size=SIZE)


def test_an_unmeasurable_vision_box_is_refused() -> None:
    """An infinity, not a NaN: `round(inf)` is an OverflowError where `round(nan)` is a ValueError,
    so the two arrive at `_padded` by different exceptions and neither is one `app/tasks/media.py`
    has a reason code for. `math.isfinite` is false for both."""
    vision = {"status": "ok", "identifies_practice": True,
              "regions": [{"kind": "logo", "label": "wall logo", "box": [400, 400, float("-inf"), 500],
                           "confidence": "low"}]}
    with pytest.raises(aggregate.UnmeasurableRegion, match="vision"):
        aggregate.regions_for(lines=[], matches=[], symbols=[], vision=vision, size=SIZE)


def test_a_match_pointing_past_the_last_line_is_skipped_rather_than_raising() -> None:
    """`regions_for` takes the lines and the matches as two arguments, so nothing in its own
    signature holds them to one scan. `app/privacy/identity.py` indexes into the lines it was
    handed, so the pipeline cannot produce this -- but a caller that passed last run's matches
    beside this run's lines would otherwise raise `IndexError` out of the aggregator, which is an
    exception `app/tasks/media.py` has no reason code for. The line that is there is still a
    region; the one that is not is not invented."""
    lines = [_line("HILL COUNTRY ANIMAL HOSPITAL", 100, 100, 500, 140)]
    detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("name", 0, "exact", 1.0), Match("name", 7, "exact", 1.0)],
        symbols=[], vision={"status": "unavailable"}, size=SIZE)
    assert [d["line"] for d in detected] == [0] and len(redaction) == 1


def test_a_merged_region_keeps_the_line_index_of_the_text_in_it() -> None:
    """`expanded_from` is what P12's Remove and the seller's review trace a mask back to, so a
    merge of a line with a symbol must report the LINE: `None` would say "no text was involved
    here" about a block that covers a sign."""
    lines = [_line("HILL COUNTRY ANIMAL HOSPITAL", 100, 100, 400, 140)]
    symbol = Symbol("QRCode", "url", [(405.0, 100.0), (455.0, 100.0), (455.0, 150.0), (405.0, 150.0)])
    _detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("name", 0, "exact", 1.0)], symbols=[symbol],
        vision={"status": "unavailable"}, size=SIZE)
    assert len(redaction) == 1 and redaction[0]["expanded_from"] == 0


def test_two_symbols_merging_report_no_line_because_neither_came_from_one() -> None:
    """The other arm of the same expression. A QR beside a barcode is one block and `expanded_from`
    is honestly null -- the field says which OCR line produced a region, and no line did."""
    symbols = [Symbol("QRCode", "url", [(100.0, 100.0), (200.0, 100.0), (200.0, 200.0), (100.0, 200.0)]),
               Symbol("DataMatrix", "text", [(210.0, 100.0), (310.0, 100.0), (310.0, 200.0), (210.0, 200.0)])]
    _detected, redaction = aggregate.regions_for(lines=[], matches=[], symbols=symbols,
                                                 vision={"status": "unavailable"}, size=SIZE)
    assert len(redaction) == 1 and redaction[0]["expanded_from"] is None
