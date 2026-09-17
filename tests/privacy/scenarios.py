"""Synthetic finding-region scenarios shared between the aggregate merge property tests
(`test_aggregate.py`) and the before/after measurement harness
(`test_redaction_masks_measurement.py`), so the two never describe two different distributions of
the same claim. Not a `test_*` module -- pytest never collects it, and it carries no assertions of
its own.

Every generator returns a list of already-PADDED boxes (`(x0, y0, x1, y1)` tuples), which is the
shape `app/privacy/aggregate._merged` consumes once its own callers have padded a raw detection --
and takes a `random.Random` so a scenario is reproducible from its seed alone, the project's own
"deterministic by construction" rule (`aggregate.py`'s module docstring).

Task brief (2026-09-17), measured on the real 313-photograph QA corpus: two findings collapsed
into one mask on 50 photographs, three into one on 19, four into one on 9, six into two on 5.
Two different GEOMETRIES both produce "several findings, fewer masks", and the fix has to keep
one and break the other, so both are generated here, named for what they are rather than for the
mask count they happen to produce:

  * a LEGITIMATE cluster -- lines of one sign, or entries on a directory board -- packed close
    enough that the space BETWEEN them is a small fraction of what they cover. `_merged`'s own
    docstring calls merging one of these into one block "the right answer anyway".
  * a CASCADE -- findings each near enough to their immediate neighbour to satisfy a naive gap
    test, chained across a span where most of the enclosed area is empty photograph: a sign near
    the top and a door number near the bottom, joined by nothing the seller would call one thing.
"""
from __future__ import annotations

import random

from app.privacy import aggregate

Box = tuple[float, float, float, float]

#: A typical listing photograph -- the same figure `test_aggregate.py`'s own `SIZE` uses.
PHOTO: tuple[int, int] = (1600, 1200)


def _clamped_box(x0: float, y0: float, w: float, h: float, size: tuple[int, int]) -> Box:
    sw, sh = size
    x0 = max(0.0, min(x0, sw - w))
    y0 = max(0.0, min(y0, sh - h))
    return (x0, y0, x0 + w, y0 + h)


def _ocr_padded(box: Box, size: tuple[int, int]) -> Box:
    """A raw finding, expanded exactly the way `aggregate._padded` expands a real OCR line --
    called through the real function rather than a second copy of its formula, so a scenario
    meant to represent "already padded" boxes (the contract every generator here promises) is
    padded the same amount the real pipeline would pad it, and a change to the pad formula is felt
    here too rather than silently diverging."""
    padded, _pad = aggregate._padded(box, aggregate.OCR_PAD_MIN, aggregate.OCR_PAD_FRACTION, size)
    return padded


def scattered(rng: random.Random, n: int, size: tuple[int, int] = PHOTO) -> list[Box]:
    """`n` findings placed independently anywhere in the frame. Most pairs land far enough apart
    that nothing should merge; the rare close pair (two draws can land beside each other) is
    exactly the case a correct merge must still catch, so this is not filtered to avoid it."""
    boxes = []
    for _ in range(n):
        w = rng.uniform(20.0, 180.0)
        h = rng.uniform(14.0, 90.0)
        boxes.append(_clamped_box(rng.uniform(0, size[0]), rng.uniform(0, size[1]), w, h, size))
    return boxes


def overlapping_pair(rng: random.Random, size: tuple[int, int] = PHOTO) -> list[Box]:
    """Two boxes whose interiors genuinely intersect -- the plainest "must become one" case."""
    w, h = rng.uniform(60.0, 160.0), rng.uniform(30.0, 80.0)
    x0, y0 = rng.uniform(0, size[0] - w - 40), rng.uniform(0, size[1] - h - 40)
    a = _clamped_box(x0, y0, w, h, size)
    # `b` shares at least a third of `a`'s own extent on each axis, so the two interiors overlap
    # by construction rather than by chance.
    ox, oy = rng.uniform(w * 0.3, w * 0.7), rng.uniform(h * 0.3, h * 0.7)
    b = _clamped_box(x0 + ox, y0 + oy, w, h, size)
    return [a, b]


def adjacent_pair(rng: random.Random, gap: float, size: tuple[int, int] = PHOTO) -> list[Box]:
    """Two boxes touching or separated by exactly `gap` px -- the boundary case a merge threshold
    is drawn against, at whatever `gap` the caller wants to probe."""
    w, h = rng.uniform(60.0, 160.0), rng.uniform(30.0, 80.0)
    x0, y0 = rng.uniform(0, size[0] - w - w - gap - 10), rng.uniform(0, size[1] - h - 10)
    a = _clamped_box(x0, y0, w, h, size)
    b = _clamped_box(x0 + w + gap, y0, w, h, size)
    return [a, b]


def nested(rng: random.Random, size: tuple[int, int] = PHOTO) -> list[Box]:
    """One box entirely inside another -- a barcode beside a matched OCR line's own region, or a
    small vision box the identity matcher's line already contains."""
    ow, oh = rng.uniform(200.0, 400.0), rng.uniform(120.0, 240.0)
    ox, oy = rng.uniform(0, size[0] - ow), rng.uniform(0, size[1] - oh)
    outer = _clamped_box(ox, oy, ow, oh, size)
    iw, ih = ow * rng.uniform(0.2, 0.5), oh * rng.uniform(0.2, 0.5)
    ix = ox + rng.uniform(0, ow - iw)
    iy = oy + rng.uniform(0, oh - ih)
    inner = (ix, iy, ix + iw, iy + ih)
    return [outer, inner]


def legitimate_sign(rng: random.Random, lines: int, size: tuple[int, int] = PHOTO,
                     line_gap: float = 6.0) -> list[Box]:
    """`lines` OCR-line-shaped boxes stacked with a small, realistic line-height gap and a shared
    x-range -- a business name over two or three lines, or a directory board's many rows. The
    module's own docstring calls merging this into one block "the right answer anyway".

    Each RAW line is padded exactly as `aggregate._padded` would pad it before returning, because
    that is what actually makes two lines of one sign merge in the real pipeline: a 6 px line-height
    gap is not itself inside `MERGE_GAP_PX`, but each line's own OCR pad (>= 12 px, a quarter of its
    shorter side) reaches past it on both sides, so the PADDED boxes end up overlapping outright --
    exactly the fixture `test_two_lines_of_one_sign_merge_into_one_polygon` already pins by hand."""
    w = rng.uniform(220.0, 420.0)
    h = rng.uniform(28.0, 44.0)
    x0 = rng.uniform(0, size[0] - w)
    y0 = rng.uniform(0, size[1] - lines * (h + line_gap))
    boxes = []
    y = y0
    for _ in range(lines):
        raw = _clamped_box(x0 + rng.uniform(-4, 4), y, w, h, size)
        boxes.append(_ocr_padded(raw, size))
        y += h + line_gap
    return boxes


def cascade(rng: random.Random, n: int, size: tuple[int, int] = PHOTO, *, step_gap: float = 3.0,
            drift: float | None = None) -> list[Box]:
    """`n` small findings in a column that WANDERS as it goes down the frame -- several distinct
    small marks (signage, a plaque, a sticker, a vent label) that are not neatly stacked, each a
    short realistic step below the last and independently padded as an OCR line would be.
    Consecutive raw boxes are `step_gap` apart vertically (well inside what either box's own OCR
    pad reaches) and drift sideways by up to `drift` px, so every CONSECUTIVE pair is close in
    both axes -- "near" by construction -- while the column as a whole wanders far enough that the
    first and last finding can be nowhere near each other. A single-linkage merge with no other
    guard absorbs the whole chain into one box spanning most of the column's height and drift,
    even though the findings themselves are small and most of the enclosed rectangle is empty
    photograph -- 2.5x each box's own width by default, chosen (a parameter sweep recorded in the
    task report) as the point where the real corpus's own reported "6 findings -> 2 masks"
    outcome first appears in this synthetic reproduction under the OLD rule, rather than the
    tighter "6 -> 1" a barely-drifting column produces."""
    w, h = rng.uniform(30.0, 70.0), rng.uniform(20.0, 40.0)
    step_drift = w * 2.5 if drift is None else drift
    x = rng.uniform(w, size[0] - 2 * w)
    y = 20.0
    boxes = []
    for _ in range(n):
        raw = _clamped_box(x, y, w, h, size)
        boxes.append(_ocr_padded(raw, size))
        x = max(0.0, min(size[0] - w, x + rng.uniform(-step_drift, step_drift)))
        y += h + step_gap
    return boxes


def diagonal_pair(rng: random.Random, size: tuple[int, int] = PHOTO) -> list[Box]:
    """Two OCR-line-shaped findings offset DIAGONALLY (corner-near-corner, not edge-near-edge) by
    just enough real distance that each one's own OCR pad still brings them within a few pixels of
    each other -- near by construction, at both the old and the new gap -- while the union
    encloses an L-shaped void neither line's own content ever reached. This is the plainest
    two-finding case `MERGE_AREA_FACTOR` exists for: the gap test alone cannot tell it apart from a
    genuinely adjacent pair, because it IS genuinely close in both axes; only the ratio of what is
    covered to what was found can."""
    w, h = rng.uniform(120.0, 220.0), rng.uniform(24.0, 36.0)
    margin = 60.0   # comfortably more than any OCR pad this box can draw, so neither box clamps
    x0 = rng.uniform(margin, size[0] - 2.4 * w - margin)
    y0 = rng.uniform(margin, size[1] - 2.4 * h - margin)
    first_raw = (x0, y0, x0 + w, y0 + h)
    first = _ocr_padded(first_raw, size)
    # place the SECOND raw box so that, once IT is padded too, the two padded boxes sit a couple
    # of true pixels apart on BOTH axes -- solved from the pad THIS box actually received (both
    # boxes share `w, h` so the pad is identical) rather than assumed, so this does not quietly
    # stop being adversarial if the pad formula ever moves.
    pad_x = x0 - first[0]
    pad_y = y0 - first[1]
    true_gap = rng.uniform(1.0, 3.0)
    gx = true_gap + 2 * pad_x
    gy = true_gap + 2 * pad_y
    second_raw = (x0 + w + gx, y0 + h + gy, x0 + w + gx + w, y0 + h + gy + h)
    second = _ocr_padded(second_raw, size)
    return [first, second]


def two_far_apart(rng: random.Random, size: tuple[int, int] = PHOTO, *, min_gap: float = 150.0) -> list[Box]:
    """The reported defect's simplest shape: a sign near the top, a door number near the bottom,
    with real empty photograph between them and no intermediate finding to chain through. Neither
    the old algorithm's direct pairwise test nor the new one should merge these two."""
    w1, h1 = rng.uniform(150.0, 320.0), rng.uniform(40.0, 70.0)
    w2, h2 = rng.uniform(30.0, 70.0), rng.uniform(18.0, 30.0)
    top = _clamped_box(rng.uniform(0, size[0] - w1), rng.uniform(10.0, 60.0), w1, h1, size)
    bottom_y = top[3] + rng.uniform(min_gap, min_gap + 250.0)
    bottom_y = min(bottom_y, size[1] - h2 - 10.0)
    bottom = _clamped_box(rng.uniform(0, size[0] - w2), max(bottom_y, top[3] + 1.0), w2, h2, size)
    return [top, bottom]


def one_region(rng: random.Random, size: tuple[int, int] = PHOTO) -> list[Box]:
    return [_clamped_box(rng.uniform(0, size[0] - 100), rng.uniform(0, size[1] - 40), 100.0, 40.0, size)]


def zero_regions() -> list[Box]:
    return []


def degenerate_point(rng: random.Random, size: tuple[int, int] = PHOTO) -> list[Box]:
    """A region with no extent at all. `regions_for`'s own callers can never produce one --
    `_checked`/`_covering` refuse it before it reaches `_merged` -- but `_merged` is exercised
    directly here (as the module's own tests already do for `_near`), so its arithmetic must not
    raise on the shape it would be handed if that were ever bypassed."""
    x, y = rng.uniform(0, size[0]), rng.uniform(0, size[1])
    return [(x, y, x, y)]


#: Every named category the task brief lists, callable with just an `rng` and an optional `n` --
#: the one place both test modules read the roster from, so neither can enumerate a different set.
NAMED_SCENARIOS = ("scattered", "overlapping", "adjacent", "nested", "legitimate_sign", "cascade",
                    "diagonal_pair", "two_far_apart", "one_region", "zero_region", "degenerate")


def build(name: str, rng: random.Random, size: tuple[int, int] = PHOTO) -> list[Box]:
    """One scenario from `NAMED_SCENARIOS`, at a size the caller sweeps over trials with."""
    if name == "scattered":
        return scattered(rng, rng.randint(2, 8), size)
    if name == "overlapping":
        return overlapping_pair(rng, size)
    if name == "adjacent":
        return adjacent_pair(rng, rng.uniform(0.0, 4.0), size)
    if name == "nested":
        return nested(rng, size)
    if name == "legitimate_sign":
        return legitimate_sign(rng, rng.randint(2, 8), size)
    if name == "cascade":
        return cascade(rng, rng.randint(4, 10), size)
    if name == "diagonal_pair":
        return diagonal_pair(rng, size)
    if name == "two_far_apart":
        return two_far_apart(rng, size)
    if name == "one_region":
        return one_region(rng, size)
    if name == "zero_region":
        return zero_regions()
    if name == "degenerate":
        return degenerate_point(rng, size)
    raise ValueError(f"unknown scenario {name!r}")   # pragma: no cover -- every caller uses NAMED_SCENARIOS
