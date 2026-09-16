"""The union of everything the pipeline found, expanded and merged into what the fill covers.

Directive 4 step 5 asks for "a structured detection result"; directive 5 asks that a region be
expanded "sufficiently to prevent surrounding pixels from reconstructing the identifying
information" while not cropping away useful content. Two columns come out of this module:

  detected_regions   every candidate BEFORE expansion, tagged by source. The record, and what makes
                     a decision explainable months later.
  redaction_regions  what the fill covers: expanded, merged, each with an id the seller's Remove
                     targets.

Deterministic by construction -- sorted inputs, integer arithmetic, no set iteration order in the
output -- because a regeneration that produced different regions from the same scan would change a
derivative the seller had already confirmed."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from app.privacy.barcodes import EXPAND, Symbol
from app.privacy.identity import Match
from app.privacy.ocr import Line

#: Text: at least 12 px, or a quarter of the region's shorter side.
OCR_PAD_MIN = 12
OCR_PAD_FRACTION = 0.25
#: Vision: more, because a model's "coordinate and localization outputs are approximate".
VISION_PAD_MIN = 24
VISION_PAD_FRACTION = 0.20
#: Expanded boxes that overlap or sit within this many pixels become one polygon.
MERGE_GAP_PX = 8
#: A symbol's four corners are scaled about their centroid by `barcodes.EXPAND`. THE CONSTANT IS
#: NOT RESTATED HERE (controller ruling, 2026-09-16): `app/privacy/barcodes.py` declares it beside
#: the adapter whose symbols it describes, and a second copy of 1.15 in this module was a number
#: that could be changed in one place and not the other with nothing to notice.

Box = tuple[float, float, float, float]


class UnmeasurableRegion(ValueError):
    """A detection whose geometry is not a measurable quantity. Reason code AGGREGATE_UNMEASURABLE.

    AN ADDITION TO THE PLAN'S LITERAL MODULE, and it is the Task P7 brief's own instruction:
    "`_iou` can answer NaN for an unmeasurable quad, and every caller's comparison must be written
    so that NaN means DO NOT MERGE -- a comparison written the other way round would silently merge
    regions it cannot measure." `_near` IS such a comparison and it is written the other way round;
    the polarity is closed at the one DOOR every detection enters by rather than at the comparison,
    which is the argument `app/privacy/ocr.py::_iou` makes for its own all-NaN case.

    Why a refusal and not a repair. Measured on this tree's own arithmetic, a single non-finite
    ordinate does one of three things depending only on WHICH vertex carries it -- which is not a
    behaviour anything downstream could be written against, and one of the three is silent:

      * `_bounds` DROPS it when it is not the first value `min`/`max` see (`min([100.0, nan])` is
        `100.0`), so the region shrinks to the box of the quad's other corners and an identifying
        line is covered one corner short, with nothing raised anywhere;
      * `_bounds` KEEPS it when it is first, and `_padded`'s `round(nan)` then raises
        `ValueError: cannot convert float NaN to integer` -- an exception `app/tasks/media.py` has
        no reason code for, which is what `ocr.py`'s review M2 ruled against. An infinity reaches
        the same line as an `OverflowError`, so the two arrive by different exceptions;
      * `_near`'s every comparison against a NaN is False, so `not (... or ...)` is True and an
        unmeasurable box MERGES WITH EVERY OTHER REGION IN THE PHOTOGRAPH. `PIL.ImageDraw.polygon`
        then accepts the NaN vertex without raising and fills something undefined -- measured, it
        filled a pixel.

    None of those is an answer. A detection that cannot be measured cannot be covered, and a
    derivative that quietly does not cover an identifying region is the outcome this sub-project
    exists to prevent, so the photograph FAILS (directive 19, fail closed) and the seller is shown
    a state rather than a derivative that looks finished. A `ValueError` subclass, so a caller
    written against the accidental `round()` failure above still catches it, carrying its reason
    code as its message exactly as `OcrError` and `BarcodeError` do.

    UNMEASURED, and recorded as such: whether the real `rapidocr-onnxruntime` wheel can emit a
    non-finite coordinate at all is not known -- `ocr._iou`'s docstring says the same of itself.
    What is known is what this arithmetic does downstream of one.
    """


def _bounds(polygon: Sequence[Sequence[float]]) -> Box:
    xs = [float(p[0]) for p in polygon]
    ys = [float(p[1]) for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _checked(polygon: Sequence[Sequence[float]], source: str) -> Box:
    """The detection's bounds, NORMALISED -- or `UnmeasurableRegion`. The one door every detection
    enters by; see that class for why a refusal rather than a repair.

    Three things happen here, in this order, and the order is the controller's ruling of
    2026-09-16: normalise first, then refuse.

    FINITE, over EVERY ordinate and never the bounding box's four: `min`/`max` swallow a NaN that
    is not the first value they see, so a check on `_bounds`' output would pass exactly the quads
    whose region silently shrinks. `math.isfinite` is false for a NaN and for both infinities.

    NORMALISED, which is what `_bounds` IS -- `min`/`max` over the corners, so a vision box handed
    back as `x1 < x0` becomes the region it plainly meant rather than a rectangle whose right edge
    sits left of its left edge. Measured before the fix: `[600, 500, 400, 400]` produced the
    polygon `[[576, 476], [424, 476], [424, 424], [576, 424]]`, which `PIL.ImageDraw.polygon`
    draws as NOTHING.

    NON-DEGENERATE: a point or a line is not a localisation. This cannot be left to `_covering`
    below, because both pads would RESCUE it -- `max(VISION_PAD_MIN, ...)` turns a zero-area vision
    box into an invented 48 px block where the model said nothing was, and `max(OCR_PAD_MIN, ...)`
    does the same at 24 px for a line with no extent. A symbol has no pad at all and scales to a
    point, so that arm is the one that drew nothing outright."""
    if not all(math.isfinite(float(ordinate)) for point in polygon for ordinate in (point[0], point[1])):
        raise UnmeasurableRegion(f"AGGREGATE_UNMEASURABLE: {source} is not finite")
    box = _bounds(polygon)
    if box[2] <= box[0] or box[3] <= box[1]:
        raise UnmeasurableRegion(f"AGGREGATE_UNMEASURABLE: {source} covers no area")
    return box


def _covering(box: Box, source: str) -> Box:
    """The EXPANDED box, or `UnmeasurableRegion` when the clamp has emptied it.

    The second way to cover nothing, and the one no check on the detection itself can see: a quad
    wholly outside the image is perfectly measurable and perfectly non-degenerate, and it is
    `_padded`'s own clamp that empties it -- `max(0.0, x0 - pad)` holds at the detection while
    `min(float(w), x1 + pad)` falls to the image's edge, so the box comes out inverted and the fill
    paints nothing. A detection that merely OVERHANGS the frame still clamps to a real region and
    is kept, which is the boundary this guard is written against: a sign at the edge of the
    photograph is covered, and only a detection with no pixel inside the image at all is refused."""
    if box[2] <= box[0] or box[3] <= box[1]:
        raise UnmeasurableRegion(f"AGGREGATE_UNMEASURABLE: {source} lies outside the image")
    return box


def rect(box: Box) -> list[list[float]]:
    """A box as the four-point polygon every region is stored as. PUBLIC, because P12's mask routes
    build a manual region from the seller's dragged box and must not reach into a private helper of
    another module to do it."""
    x0, y0, x1, y1 = box
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _pads(box: Box, minimum: int, fraction: float, *, per_axis: bool) -> tuple[int, int]:
    """The horizontal and the vertical pad, in pixels.

    TWO RULES, because spec C.5 step 5 states two and contrasts them in one sentence: "OCR/regex/
    barcode regions pad `max(12 px, 25 % of the SHORTER SIDE)`; vision boxes pad
    `max(24 px, 20 % PER SIDE)`".

    A line of type is long and thin, and a pad taken per axis would give it a horizontal margin
    many times its vertical one -- a quarter of 400 px against a quarter of 40 -- which is
    directive 5's "do NOT crop away important image content unnecessarily" in the direction the
    text rule has to guard. A vision box is approximate in its OWN width and its OWN height (the
    model is estimating both), so each axis is grown from its own extent.

    Recorded as a deviation from the plan's literal `_padded`, which took `min(width, height)` for
    both callers and so could not satisfy the plan's own vision case: `[400, 400, 600, 500]` is
    200 x 100, the plan's test asserts a pad of `max(24, round(200 * 0.20))` = 40, and the shared
    rule answers `max(24, round(100 * 0.20))` = 24. The specification's two phrasings and the
    plan's test agree with each other; only the implementation sketch did not."""
    width, height = box[2] - box[0], box[3] - box[1]
    basis_x, basis_y = (width, height) if per_axis else (min(width, height), min(width, height))
    return max(minimum, round(basis_x * fraction)), max(minimum, round(basis_y * fraction))


def _padded(box: Box, minimum: int, fraction: float, size: tuple[int, int], *,
            per_axis: bool = False) -> tuple[Box, int]:
    """The box grown by `_pads` and clamped to the image, and the pad the record keeps.

    ONE `pad_px` for a two-axis pad, and it is the LARGER: `_merged` already records
    `max(a.pad, b.pad)` when it absorbs one region into another, so the field has always meant
    "the widest expansion that contributed to this region" rather than a per-edge measurement."""
    x0, y0, x1, y1 = box
    pad_x, pad_y = _pads(box, minimum, fraction, per_axis=per_axis)
    w, h = size
    return ((max(0.0, x0 - pad_x), max(0.0, y0 - pad_y), min(float(w), x1 + pad_x), min(float(h), y1 + pad_y)),
            max(pad_x, pad_y))


def _scaled(polygon: Sequence[Sequence[float]], factor: float, size: tuple[int, int]) -> Box:
    x0, y0, x1, y1 = _bounds(polygon)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hw, hh = (x1 - x0) * factor / 2, (y1 - y0) * factor / 2
    w, h = size
    return max(0.0, cx - hw), max(0.0, cy - hh), min(float(w), cx + hw), min(float(h), cy + hh)


def _near(a: Box, b: Box) -> bool:
    """Whether the two expanded boxes overlap or sit within `MERGE_GAP_PX` of each other.

    EVERY ORDINATE REACHING HERE IS FINITE, and that is load-bearing rather than incidental:
    `_checked` refuses a detection before `_padded` or `_scaled` can ever hand this a NaN. Written
    as it is, a NaN makes all four comparisons False and this answers True -- an unmeasurable box
    would merge with every region in the photograph. The polarity is not fixable in place, because
    `not (... or ...)` is the only spelling in which two DISJOINT boxes answer False; what closes it
    is that no such box can arrive. See `UnmeasurableRegion`."""
    return not (a[2] + MERGE_GAP_PX < b[0] or b[2] + MERGE_GAP_PX < a[0]
                or a[3] + MERGE_GAP_PX < b[1] or b[3] + MERGE_GAP_PX < a[1])


def _merged(boxes: list[tuple[Box, int, int | None]]) -> list[tuple[Box, int, int | None]]:
    """Repeatedly absorb any two boxes within MERGE_GAP_PX. Quadratic in the number of regions,
    which is tens at most: a photograph with hundreds of separate identifying regions is a
    directory board, and merging it into one block is the right answer anyway."""
    out = list(boxes)
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                if _near(out[i][0], out[j][0]):
                    a, b = out[i], out[j]
                    box = (min(a[0][0], b[0][0]), min(a[0][1], b[0][1]),
                           max(a[0][2], b[0][2]), max(a[0][3], b[0][3]))
                    out[i] = (box, max(a[1], b[1]), a[2] if a[2] is not None else b[2])
                    del out[j]
                    changed = True
                    break
            if changed:
                break
    return sorted(out, key=lambda item: (item[0][1], item[0][0]))


def regions_for(*, lines: Sequence[Line], matches: Sequence[Match], symbols: Sequence[Symbol],
                vision: Mapping[str, Any], size: tuple[int, int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(detected_regions, redaction_regions)` -- the two jsonb columns, in that order.

    Raises `UnmeasurableRegion`, and nothing else, when a detection's geometry is not finite."""
    detected: list[dict[str, Any]] = []
    padded: list[tuple[Box, int, int | None]] = []

    for index in sorted({m.line for m in matches}):
        if index >= len(lines):
            continue
        source = "regex" if all(m.field.startswith("regex:") for m in matches if m.line == index) else "ocr_match"
        quad = lines[index].quad
        bounds = _checked(quad, source)
        detected.append({"source": source, "polygon": [[x, y] for x, y in quad], "line": index, "label": None})
        box, pad = _padded(bounds, OCR_PAD_MIN, OCR_PAD_FRACTION, size)
        padded.append((_covering(box, source), pad, index))

    for symbol in symbols:
        _checked(symbol.quad, "barcode")
        detected.append({"source": "barcode", "polygon": [[x, y] for x, y in symbol.quad],
                         "line": None, "label": symbol.payload_kind})
        padded.append((_covering(_scaled(symbol.quad, EXPAND, size), "barcode"), 0, None))

    for region in vision.get("regions", ()):
        # `_checked` NORMALISES as well as refusing, so the box below is upright whichever way
        # round the model handed its corners back -- and the RECORD keeps that region rather than
        # the inversion, because `detected_regions` is what makes a decision explainable later.
        upright = _checked(rect((float(region["box"][0]), float(region["box"][1]),
                                 float(region["box"][2]), float(region["box"][3]))), "vision")
        detected.append({"source": "vision", "polygon": rect(upright), "line": None, "label": region.get("label")})
        grown, pad = _padded(upright, VISION_PAD_MIN, VISION_PAD_FRACTION, size, per_axis=True)
        padded.append((_covering(grown, "vision"), pad, None))

    redaction = [{"id": str(uuid4()), "polygon": rect(box), "source": "auto",
                  "expanded_from": origin, "pad_px": pad, "by": None, "at": None}
                 for box, pad, origin in _merged(padded)]
    return detected, redaction


def fillable(regions: Sequence[Mapping[str, Any]]) -> list[list[tuple[float, float]]]:
    """Every polygon the fill covers: auto and manual, never `removed-by-seller`."""
    return [[(float(p[0]), float(p[1])) for p in r["polygon"]]
            for r in regions if r.get("source") != "removed-by-seller"]


def _inside(inner: Box, outer: Box) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def union_auto(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]], *,
               confirmed: bool) -> list[dict[str, Any]]:
    """The in-place re-run's rule (spec C.5).

    The seller's own regions -- manual, and the ones they removed -- carry forward by id, always. The
    AUTO set is replaced on an unconfirmed row and UNIONED on a confirmed one, so a confirmed
    derivative can only ever hide MORE than the seller approved and never less. A fresh auto region
    lying inside a region the seller removed is recorded in `detected_regions` by the caller and is
    not filled: they said that one was unnecessary and a re-run does not overrule them."""
    kept = [dict(r) for r in old if r.get("source") != "auto"]
    removed = [_bounds(r["polygon"]) for r in old if r.get("source") == "removed-by-seller"]
    fresh = [dict(r) for r in new
             if r.get("source") == "auto" and not any(_inside(_bounds(r["polygon"]), box) for box in removed)]
    if confirmed:
        kept += [dict(r) for r in old if r.get("source") == "auto"]
    return sorted(kept + fresh, key=lambda r: (_bounds(r["polygon"])[1], _bounds(r["polygon"])[0], r["id"]))
