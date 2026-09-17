"""Region aggregation (spec 2026-09-09 C.5 step 5; directive 4 step 5, 5).

Directive 5: "Where necessary, expand the redaction region sufficiently to prevent surrounding
pixels from reconstructing the identifying information", and "Do NOT crop away important image
content unnecessarily". Those two pull against each other, and the numbers below are the spec's
answer: a quarter of the shorter side for text, a fifth per side for a vision box (whose
coordinates are approximate), and a merge of anything within 8 px so a sign is one block rather
than a picket fence that leaks its letter count."""
from __future__ import annotations

import random
from typing import Any

import pytest

from app.privacy import aggregate
from app.privacy.barcodes import EXPAND, Symbol
from app.privacy.identity import Match
from app.privacy.ocr import Line
from tests.privacy import scenarios

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
    assert (x1 - x0) == pytest.approx(100 * EXPAND)
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


# ---------------------------------------------------------------------------------------------
# A region that would cover NOTHING (controller ruling, 2026-09-16: "there must be no input that
# silently results in nothing being covered"). Normalise first, then refuse.
#
# On a privacy feature a region that quietly covers nothing is the worst failure there is: the
# seller is told the mark is hidden and it is not, and nothing anywhere says otherwise. Every one
# of these arrived at a fill and drew no pixel before this ruling.
# ---------------------------------------------------------------------------------------------


def test_an_inverted_vision_box_covers_the_region_it_plainly_meant() -> None:
    """`x1 < x0` is a model handing back its corners the other way round. It is finite, so the
    non-finite guard passes it; `_pads` then took a NEGATIVE width, the `max(minimum, ...)` floor
    applied, and the result was a rectangle whose right edge sat left of its left edge -- which
    `PIL.ImageDraw.polygon` draws as nothing at all. The corners are swapped, and the region is the
    one the upright box would have produced, byte for byte."""
    inverted = {"status": "ok", "identifies_practice": True,
                "regions": [{"kind": "logo", "label": "wall logo", "box": [600, 500, 400, 400],
                             "confidence": "low"}]}
    upright = {"status": "ok", "identifies_practice": True,
               "regions": [{"kind": "logo", "label": "wall logo", "box": [400, 400, 600, 500],
                            "confidence": "low"}]}
    swapped, swapped_redaction = aggregate.regions_for(
        lines=[], matches=[], symbols=[], vision=inverted, size=SIZE)
    plain, plain_redaction = aggregate.regions_for(
        lines=[], matches=[], symbols=[], vision=upright, size=SIZE)
    assert swapped_redaction[0]["polygon"] == plain_redaction[0]["polygon"]
    assert swapped[0]["polygon"] == plain[0]["polygon"], "the RECORD keeps the region, not the inversion"
    assert _box(swapped_redaction[0])[0] == 400 - 40, "and it is the per-axis pad, as an upright box gets"


def test_a_vision_box_of_zero_area_is_refused_rather_than_padded_into_a_region() -> None:
    """A degenerate point or line is not a localisation, and padding one INVENTS a region 48 px
    across where the model said nothing was. `max(VISION_PAD_MIN, ...)` would have done exactly
    that, so this cannot be left to the covers-a-pixel check further down."""
    vision = {"status": "ok", "identifies_practice": True,
              "regions": [{"kind": "logo", "label": "a line", "box": [400, 400, 400, 500],
                           "confidence": "high"}]}
    with pytest.raises(aggregate.UnmeasurableRegion, match="vision covers no area"):
        aggregate.regions_for(lines=[], matches=[], symbols=[], vision=vision, size=SIZE)


def test_an_ocr_quad_of_zero_area_is_refused() -> None:
    """The same rule at the same door. The pad would have rescued this one into a 24 px block, so
    it is not caught by "covers a pixel" either -- a line with no extent is not a line."""
    quad = [(100.0, 100.0)] * 4
    with pytest.raises(aggregate.UnmeasurableRegion, match="ocr_match covers no area"):
        aggregate.regions_for(lines=[Line("HILL COUNTRY", 0.95, quad)],
                              matches=[Match("name", 0, "exact", 1.0)], symbols=[],
                              vision={"status": "unavailable"}, size=SIZE)


def test_a_symbol_quad_of_zero_area_is_refused() -> None:
    """`_scaled` multiplies the half-extents by 1.15, so a degenerate symbol scales to a point and
    the fill draws nothing -- the one arm no pad protects."""
    symbol = Symbol("QRCode", "url", [(100.0, 100.0), (200.0, 100.0), (200.0, 100.0), (100.0, 100.0)])
    with pytest.raises(aggregate.UnmeasurableRegion, match="barcode covers no area"):
        aggregate.regions_for(lines=[], matches=[], symbols=[symbol],
                              vision={"status": "unavailable"}, size=SIZE)


def test_a_detection_entirely_outside_the_image_is_refused_rather_than_clamped_to_nothing() -> None:
    """The second way to cover nothing, and the one no area check on the DETECTION can see. The
    quad is 100 x 40 and perfectly measurable; it is the CLAMP that empties it -- `max(0, x0 - pad)`
    holds at 1988 while `min(1600, x1 + pad)` falls to 1600, so the expanded box comes out with its
    right edge 388 px left of its left edge and the fill paints nothing."""
    lines = [_line("HILL COUNTRY ANIMAL HOSPITAL", 2000, 100, 2100, 140)]
    with pytest.raises(aggregate.UnmeasurableRegion, match="ocr_match lies outside the image"):
        aggregate.regions_for(lines=lines, matches=[Match("name", 0, "exact", 1.0)], symbols=[],
                              vision={"status": "unavailable"}, size=SIZE)


def test_a_detection_that_merely_overhangs_the_edge_is_kept_and_clamped() -> None:
    """The boundary of the rule above: a sign at the edge of the frame is a real region and must
    still be covered. Only a detection with NO pixel inside the image is refused."""
    lines = [_line("HILL COUNTRY ANIMAL HOSPITAL", 1550, 100, 1700, 140)]
    _detected, redaction = aggregate.regions_for(
        lines=lines, matches=[Match("name", 0, "exact", 1.0)], symbols=[],
        vision={"status": "unavailable"}, size=SIZE)
    x0, _y0, x1, _y1 = _box(redaction[0])
    assert x0 == 1538 and x1 == 1600 and x1 > x0


# ---------------------------------------------------------------------------------------------
# THE SAFETY INVARIANT (Task fix/surgical-redaction, John's ruling 2026-09-17, on seeing the
# masks the pipeline was drawing on the real 313-photograph corpus: "the blue blocks are HUGE and
# not surgical ... can it be implemented with finer point and control?"). Coverage of the findings
# themselves must NEVER decrease -- only the space BETWEEN findings is freed. Written FIRST,
# before any change to the merge rule below, the way `test_ocr.py`'s own
# `test_a_merged_footprint_can_only_ever_grow_what_is_covered` pins the identical property one
# layer up (a cluster's footprint can only ever grow what it replaces, never shrink it).
#
# `_merged` takes `(box, pad, origin)` triples; the geometry alone decides the property, so a
# fixed pad (12) and origin (None) stand in for every trial here. `tests/privacy/scenarios.py` is
# shared with the before/after measurement harness (`test_redaction_masks_measurement.py`) so the
# two can never describe two different distributions of the same claim.
# ---------------------------------------------------------------------------------------------


def _wrapped(boxes: list[scenarios.Box]) -> list[tuple[scenarios.Box, int, int | None]]:
    return [(box, 12, None) for box in boxes]


def _covers_every_input(inputs: list[scenarios.Box],
                        outputs: list[tuple[scenarios.Box, int, int | None]]) -> bool:
    """Whether every box the merge was HANDED is still inside some box it HANDS BACK -- the
    invariant, stated once, exactly the shape `aggregate._inside` already exists to check."""
    return all(any(aggregate._inside(inp, out[0]) for out in outputs) for inp in inputs)


def _assert_covers(inputs: list[scenarios.Box], outputs: list[tuple[scenarios.Box, int, int | None]]) -> None:
    assert _covers_every_input(inputs, outputs), (
        "the merge lost coverage of at least one finding", inputs, outputs)


def test_the_coverage_property_holds_over_every_generated_region_set() -> None:
    """THE property, run first against `_merged` exactly as it ships today -- CONFIRMED rather
    than assumed, because a bounding-box union can only ever grow what it absorbs, so this is
    expected to pass against the pre-fix code and does. It is re-run, unchanged, once the merge
    rule below tightens, which is what makes it the test that makes every other change in this
    module safe: 60 trials of each of the ten named scenarios (600 generated region sets in all)
    -- scattered, overlapping, adjacent, nested, a legitimate multi-line sign, a cascade, two
    genuinely far-apart findings, one region, zero regions and a degenerate zero-area point."""
    for name in scenarios.NAMED_SCENARIOS:
        for seed in range(60):
            rng = random.Random((abs(hash(name)) % 100_000) * 1_000 + seed)
            inputs = scenarios.build(name, rng)
            outputs = aggregate._merged(_wrapped(inputs))
            _assert_covers(inputs, outputs)


def test_the_coverage_property_actually_catches_a_dropped_region() -> None:
    """Proof the gate above is not vacuous (standing project practice: "Prove a gate can fail" --
    perturb what it guards and watch it fail). A plausible slip when teaching `_merged` to
    sometimes REFUSE a merge -- which the fix below must do -- is to drop the refused neighbour
    instead of leaving it in the output untouched. `_saboteur` is exactly that slip, written once
    here and never shipped: it is fed the SAME two boxes `_merged` itself is handed, and the same
    `_assert_covers` check that passes against the real function raises against this one, with a
    concrete counterexample rather than an assertion of faith."""
    def _saboteur(boxes: list[tuple[scenarios.Box, int, int | None]]
                  ) -> list[tuple[scenarios.Box, int, int | None]]:
        out: list[tuple[scenarios.Box, int, int | None]] = []
        for box, pad, origin in boxes:
            if out and aggregate._near(out[-1][0], box):
                continue   # BUG: a near-but-not-absorbed neighbour is silently dropped
            out.append((box, pad, origin))
        return out

    close = [(10.0, 10.0, 50.0, 40.0), (54.0, 10.0, 94.0, 40.0)]   # 4 px apart: `_near` says True
    wrapped = _wrapped(close)

    _assert_covers(close, aggregate._merged(wrapped))   # the real thing: still green

    with pytest.raises(AssertionError):
        _assert_covers(close, _saboteur(wrapped))


# ---------------------------------------------------------------------------------------------
# WHY THE RUNNING TRUE AREA IS TRACKED, rather than re-derived from a box that may already be
# inflated. The direct guard against a slab compares the union a merge would produce to what the
# two sides being joined actually cover -- and the FIRST, simpler way to write that comparison
# measures each side by its OWN bounding box, which is exactly wrong once one side is already the
# result of an earlier merge: the running box grows every hop, and comparing the NEXT hop only to
# that already-grown box lets the ratio drift back toward 1 forever, however little of the final
# box is real content. `_growing_void_chain` is constructed (not sampled) to make that failure
# concrete and measured rather than argued.
# ---------------------------------------------------------------------------------------------


def _growing_void_chain(k: int, *, base_w: float = 500.0, base_h: float = 20.0,
                         tiny: float = 10.0) -> list[scenarios.Box]:
    """A wide, short first finding (a plausible banner/sign shape), then `k` tiny findings, each
    sitting exactly `MERGE_GAP_PX` below the PREVIOUS one's own bottom edge and centred in the
    wide box's own x-range -- so every consecutive pair is "near" by construction, and a rule that
    keeps absorbing them grows the covered area by `tiny + MERGE_GAP_PX` in height at every step
    while the TRUE content grows by only `tiny * tiny`. The x-range never has to widen (it is
    already 500 px), which isolates the one axis a per-hop check can be fooled on."""
    gap = aggregate.MERGE_GAP_PX
    boxes: list[scenarios.Box] = [(0.0, 0.0, base_w, base_h)]
    y = base_h
    for _ in range(k):
        y += gap
        boxes.append((base_w / 2 - tiny / 2, y, base_w / 2 + tiny / 2, y + tiny))
        y += tiny
    return boxes


def test_a_per_hop_area_check_against_an_already_grown_box_lets_a_cluster_run_away() -> None:
    """The measurement behind `MERGE_AREA_FACTOR`'s own docstring, pinned as a test rather than
    left as an assertion in a comment. Twenty tiny findings, each individually ordinary, chained
    onto one wide first finding: a rule that compares a candidate merge only to the box it is
    about to join -- never to what has actually been found -- absorbs every one of them into a
    single cluster whose true content is a sliver of its own area, because the ratio it checks is
    measured against a denominator that has ALREADY grown by the same unchecked amount. The
    shipped rule, which threads the running TRUE area through every merge instead, refuses to
    keep growing once that ratio would break `MERGE_AREA_FACTOR` -- not eventually, but within the
    first couple of hops -- so the same chain comes back as more than one region."""
    chain = _growing_void_chain(20)
    true_area = sum(aggregate._area(b) for b in chain)

    def _naive_merge(boxes: list[scenarios.Box]) -> list[scenarios.Box]:
        out = list(boxes)
        changed = True
        while changed:
            changed = False
            for i in range(len(out)):
                for j in range(i + 1, len(out)):
                    a, b = out[i], out[j]
                    if not aggregate._near(a, b):
                        continue
                    union = aggregate._bounding(a, b)
                    # the FIRST, rejected design: measured against the box each side already IS,
                    # never against what either side has actually found.
                    if aggregate._area(union) <= aggregate.MERGE_AREA_FACTOR * (
                            aggregate._area(a) + aggregate._area(b)):
                        out[i] = union
                        del out[j]
                        changed = True
                        break
                if changed:
                    break
        return out

    naive = _naive_merge(chain)
    assert len(naive) == 1, "the naive per-hop check absorbs the whole chain into one cluster"
    naive_fill = true_area / aggregate._area(naive[0])
    assert naive_fill < 0.10, (
        f"the naive rule's own fill ratio should have collapsed toward zero: got {naive_fill:.3f}")

    shipped = aggregate._merged(_wrapped(chain))
    _assert_covers(chain, shipped)
    assert len(shipped) > 1, "the shipped rule must break the chain the naive rule could not"
    for box, _pad, _origin in shipped:
        members = [b for b in chain if aggregate._inside(b, box)]
        fill = sum(aggregate._area(b) for b in members) / aggregate._area(box)
        assert fill >= 1 / aggregate.MERGE_AREA_FACTOR - 1e-9, (fill, box, shipped)


# ---------------------------------------------------------------------------------------------
# THE MERGE RULE ITSELF, tightened under the same ruling: "merge only where merging is honest --
# boxes that genuinely overlap, or that are touching/adjacent within a small true gap -- not
# boxes that are merely in the same half of the picture." `MERGE_AREA_FACTOR` is the direct guard
# against a slab; the smaller `MERGE_GAP_PX` is complementary and deliberately not load-bearing by
# itself in the cases below (every gap used here is well inside BOTH the old 8 px and the new
# value), so a passing test demonstrates the area guard's own necessity rather than merely a
# smaller number.
# ---------------------------------------------------------------------------------------------


def test_two_findings_with_real_empty_photograph_between_them_stay_two_masks() -> None:
    """The reported defect's simplest shape: a sign near the top, a door number near the bottom,
    real empty photograph between them and no intermediate finding to chain through. This is the
    case that used to become one slab covering everything in between; it must not."""
    rng = random.Random(20260917)
    for _ in range(40):
        inputs = scenarios.two_far_apart(rng)
        outputs = aggregate._merged(_wrapped(inputs))
        assert len(outputs) == 2, (inputs, outputs)
        _assert_covers(inputs, outputs)


def test_a_merge_that_would_balloon_the_covered_area_is_refused() -> None:
    """A direct, hand-computed case for `_absorbs`: two boxes close enough in both axes to satisfy
    `_near` at the DEFAULT gap, diagonally offset so the union encloses far more than either box's
    own true content, and refused."""
    a = (0.0, 0.0, 40.0, 30.0)
    b = (44.0, 34.0, 84.0, 64.0)   # 4 px away on each axis -- near, but the union is mostly void
    assert aggregate._near(a, b)
    true_area = aggregate._area(a) + aggregate._area(b)
    union_area = aggregate._area(aggregate._bounding(a, b))
    assert union_area > aggregate.MERGE_AREA_FACTOR * true_area, "the fixture itself must be adversarial"
    assert not aggregate._absorbs(a, b, true_area)


def test_a_merge_within_the_bounded_factor_is_accepted() -> None:
    """The other arm of the same check: two boxes close enough that absorbing them barely grows
    the covered area past what they already cover, which is accepted."""
    a = (0.0, 0.0, 100.0, 100.0)
    b = (100.0, 0.0, 110.0, 100.0)   # touching, same height: union == the sum, ratio 1.0
    assert aggregate._near(a, b)
    true_area = aggregate._area(a) + aggregate._area(b)
    assert aggregate._absorbs(a, b, true_area)


def test_adjacent_lines_within_the_new_smaller_gap_still_merge() -> None:
    """The boundary case the tightened `MERGE_GAP_PX` is drawn at: two boxes separated by exactly
    the new gap merge, and one separated by one pixel more does not."""
    rng = random.Random(1)
    at_gap = scenarios.adjacent_pair(rng, float(aggregate.MERGE_GAP_PX))
    just_over = scenarios.adjacent_pair(rng, float(aggregate.MERGE_GAP_PX) + 1.0)
    assert len(aggregate._merged(_wrapped(at_gap))) == 1
    assert len(aggregate._merged(_wrapped(just_over))) == 2


def test_overlapping_findings_still_merge_into_one_rectangle() -> None:
    rng = random.Random(2)
    for _ in range(20):
        inputs = scenarios.overlapping_pair(rng)
        outputs = aggregate._merged(_wrapped(inputs))
        assert len(outputs) == 1, (inputs, outputs)
        _assert_covers(inputs, outputs)


def test_a_nested_region_still_merges_into_its_outer_box() -> None:
    rng = random.Random(3)
    for _ in range(20):
        inputs = scenarios.nested(rng)
        outputs = aggregate._merged(_wrapped(inputs))
        assert len(outputs) == 1, (inputs, outputs)
        _assert_covers(inputs, outputs)


def test_a_legitimate_multi_line_sign_still_merges_into_one_clean_rectangle() -> None:
    """The property the module's own docstring names: "a photograph with hundreds of separate
    identifying regions is a directory board, and merging it into one block is the right answer
    anyway." Two to eight stacked OCR-line-shaped boxes, a realistic line-height gap apart, must
    still come back as ONE region -- the tightened rule does not turn a real sign into a picket
    fence again."""
    rng = random.Random(4)
    for _ in range(30):
        inputs = scenarios.legitimate_sign(rng, rng.randint(2, 8))
        outputs = aggregate._merged(_wrapped(inputs))
        assert len(outputs) == 1, (inputs, outputs)
        _assert_covers(inputs, outputs)


def test_the_gap_was_actually_tightened_and_the_area_factor_is_the_new_guard() -> None:
    """Pins the two chosen numbers directly, so a future change to either is a deliberate,
    reviewed edit to this line rather than a silent drift: the gap is HALVED from the retired 8 px
    (`tests/privacy/test_redaction_masks_measurement.py`'s own `OLD_GAP_PX`), and the area factor
    is a real, finite bound -- not merely present, but strictly greater than 1.0 (a factor of
    exactly 1 would refuse every merge that is not already a pure overlap, including the sign
    fixture two lines of text are meant to become) and comfortably under the ratios this file's
    own cascade/diagonal measurements show a slab reaching."""
    assert aggregate.MERGE_GAP_PX == 4
    assert 1.0 < aggregate.MERGE_AREA_FACTOR < 3.0


def test_the_existing_sign_fixture_and_symbol_merges_are_unmoved_by_the_tightened_rule() -> None:
    """A characterisation pin: the two hand-written merge fixtures already in this file
    (`test_two_lines_of_one_sign_merge_into_one_polygon`,
    `test_a_merged_region_keeps_the_line_index_of_the_text_in_it`) still merge under the new gap
    and area rule, because their padded boxes genuinely overlap once padding is applied -- this
    test states that fact directly on the boxes themselves, independent of `regions_for`."""
    sign_a = (100 - 12, 100 - 12, 400 + 12, 140 + 12)   # `test_two_lines_of_one_sign...`'s own pads
    sign_b = (100 - 12, 146 - 12, 400 + 12, 186 + 12)
    assert aggregate._merged(_wrapped([sign_a, sign_b])).__len__() == 1
