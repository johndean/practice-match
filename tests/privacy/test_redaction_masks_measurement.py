"""Before/after measurement harness (Task fix/surgical-redaction): are the shipped masks actually
surgical now, measured rather than eyeballed?

John's own words on seeing the pipeline's masks on the real 313-photograph QA corpus: "the blue
blocks are HUGE and not surgical ... can it be implemented with finer point and control?" The
real corpus itself is not available here -- re-running it costs real money and is John's own next
step once this is green -- so this measures the same MECHANISM on synthetic region sets built to
match the shape of the real collapse the task brief reports:

     2 findings ->  1 mask   on 50 photographs
     3 findings ->  1 mask   on 19 photographs
     4 findings ->  1 mask   on  9 photographs
     6 findings ->  2 masks  on  5 photographs

`tests/privacy/scenarios.cascade(n)` reproduces the MECHANISM CLAUDE.md diagnoses for that
collapse -- small findings each padded as a real OCR line would be, spaced closely enough that
every consecutive pair is "near" -- so it is used at n = 2, 3, 4, 6 as the comparison vehicle, and
`two_far_apart` and `legitimate_sign` stand beside it as the two boundary controls: a pair that
must never merge, and a pair that must always merge because merging it is the design's own
"right answer" (this module's docstring).

The "before" measurement is not a second, hand-duplicated copy of the pre-fix algorithm: it calls
the SAME `aggregate._merged`, with `gap=8.0` (the retired constant, named here rather than
re-imported since `aggregate.MERGE_GAP_PX` is now the new value) and `area_factor=None` (which
`_absorbs`'s own docstring defines as "the pre-fix rule, merge whenever near"), so the comparison
can never drift from what the shipped code actually does on either side of the change."""
from __future__ import annotations

import random
import statistics
from collections.abc import Sequence

from app.privacy import aggregate
from tests.privacy import scenarios

#: The retired threshold, named for comparison only -- `aggregate.MERGE_GAP_PX` is the new value.
OLD_GAP_PX = 8.0

TRIALS = 300


def _union_area(boxes: Sequence[scenarios.Box], size: tuple[int, int]) -> float:
    """The EXACT area the union of `boxes` covers, by coordinate compression over a grid built
    from every box's own edges -- so two OUTPUT masks that happen to overlap (which the design
    deliberately allows: "several small opaque rectangles ... may overlap, which is visually
    harmless") are never double-counted. At the region counts this module ever produces (tens at
    most) a grid of their own edges is exact and cheap. This is a MEASURE of the result, never a
    step `_merged` itself takes."""
    if not boxes:
        return 0.0
    xs = sorted({0.0, float(size[0])} | {b[0] for b in boxes} | {b[2] for b in boxes})
    ys = sorted({0.0, float(size[1])} | {b[1] for b in boxes} | {b[3] for b in boxes})
    total = 0.0
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        if x1 <= x0:
            continue
        cx = (x0 + x1) / 2
        for j in range(len(ys) - 1):
            y0, y1 = ys[j], ys[j + 1]
            if y1 <= y0:
                continue
            cy = (y0 + y1) / 2
            if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes):
                total += (x1 - x0) * (y1 - y0)
    return total


def _run(inputs: list[scenarios.Box], *, gap: float, area_factor: float | None) -> list[scenarios.Box]:
    wrapped = [(box, 12, None) for box in inputs]
    return [box for box, _pad, _origin in aggregate._merged(wrapped, gap=gap, area_factor=area_factor)]


def _trial_seed(*parts: object) -> int:
    return abs(hash(parts)) % 1_000_000


def _measure(generate, size: tuple[int, int] = scenarios.PHOTO, trials: int = TRIALS):
    """`(old_counts, old_fill_pct, new_counts, new_fill_pct)`, one entry per trial, for one
    scenario generator `generate(rng) -> list[Box]`."""
    old_counts: list[int] = []
    old_fill: list[float] = []
    new_counts: list[int] = []
    new_fill: list[float] = []
    image_area = float(size[0] * size[1])
    for seed in range(trials):
        rng = random.Random(seed)
        inputs = generate(rng)
        old = _run(inputs, gap=OLD_GAP_PX, area_factor=None)
        new = _run(inputs, gap=aggregate.MERGE_GAP_PX, area_factor=aggregate.MERGE_AREA_FACTOR)
        # the safety invariant, checked on every single trial this harness runs -- not only in
        # test_aggregate.py's own property test, because a measurement that quietly regressed
        # coverage while reporting a smaller number would be worse than useless.
        for box in inputs:
            assert any(aggregate._inside(box, out) for out in old), ("old dropped coverage", inputs)
            assert any(aggregate._inside(box, out) for out in new), ("new dropped coverage", inputs)
        old_counts.append(len(old))
        old_fill.append(100.0 * _union_area(old, size) / image_area)
        new_counts.append(len(new))
        new_fill.append(100.0 * _union_area(new, size) / image_area)
    return old_counts, old_fill, new_counts, new_fill


def _report(label: str, old_counts: list[int], old_fill: list[float],
            new_counts: list[int], new_fill: list[float]) -> None:
    print(f"\n{label}  ({len(old_counts)} trials)")
    print(f"  BEFORE (gap={OLD_GAP_PX:g}px, no area guard):  "
          f"masks median={statistics.median(old_counts):.1f} max={max(old_counts)}   "
          f"masked-area median={statistics.median(old_fill):.2f}%  max={max(old_fill):.2f}%")
    print(f"  AFTER  (gap={aggregate.MERGE_GAP_PX:g}px, factor={aggregate.MERGE_AREA_FACTOR:g}):     "
          f"masks median={statistics.median(new_counts):.1f} max={max(new_counts)}   "
          f"masked-area median={statistics.median(new_fill):.2f}%  max={max(new_fill):.2f}%")


def test_cascade_matching_the_real_corpus_bucket_sizes_before_and_after() -> None:
    """`n` = 3, 4, 6 -- the finding counts the task brief's own corpus table reports collapsing to
    one or two masks, reproduced through the SAME mechanism CLAUDE.md diagnoses: each consecutive
    small finding padded and placed a few real pixels from the last, so every hop is "near" and the
    chain can only be broken by the area guard, never by the gap alone. `n=2` is reported
    separately below (`test_two_findings_close_enough_to_chain_but_not_aligned`): a bare pair with
    no third finding to chain through is not, on its own, the shape that produced a slab -- see
    that test's own docstring for the shape that is, and this is recorded as a measured fact rather
    than assumed away."""
    results = {}
    for n in (3, 4, 6):
        results[n] = _measure(lambda rng, n=n: scenarios.cascade(rng, n))
        old_counts, old_fill, new_counts, new_fill = results[n]
        _report(f"cascade, n={n} findings", old_counts, old_fill, new_counts, new_fill)
        print(f"    masks==1 share: before {100 * old_counts.count(1) / len(old_counts):.0f}%  "
              f"after {100 * new_counts.count(1) / len(new_counts):.0f}%")

    for n, (old_counts, old_fill, new_counts, new_fill) in results.items():
        assert statistics.median(new_fill) < statistics.median(old_fill), (
            "the fix must reduce the median masked area for a cascade of this size", n)
        assert max(new_fill) <= 12.0, (
            "no cascade case should cover more than an eighth of the photograph after the fix", n, max(new_fill))
        old_full_collapse = old_counts.count(1) / len(old_counts)
        new_full_collapse = new_counts.count(1) / len(new_counts)
        assert new_full_collapse < old_full_collapse, (
            "the share of trials that fully collapse to one mask must fall", n,
            old_full_collapse, new_full_collapse)


def test_two_findings_close_enough_to_chain_but_not_aligned() -> None:
    """The reported defect's OWN two-finding shape, measured rather than approximated by a bare
    close pair: two ordinary OCR-line findings whose PADDED boxes sit only a couple of pixels
    apart in both axes -- genuinely "near" by any reasonable gap, old or new -- but offset
    diagonally rather than stacked, so the union encloses an L-shaped void neither line ever
    touched. `scenarios.diagonal_pair` constructs this from the real OCR pad formula rather than
    from chosen numbers. This is the case the gap threshold alone can never tell apart from a
    genuinely adjacent pair; only `MERGE_AREA_FACTOR` can, and this is where it does the most
    per-finding work of anything measured in this file."""
    old_counts, old_fill, new_counts, new_fill = _measure(scenarios.diagonal_pair)
    _report("diagonal_pair (2 findings, near but not aligned)", old_counts, old_fill, new_counts, new_fill)

    assert statistics.median(old_counts) == 1, "the premise: before the fix, this pair merges into one slab"
    assert statistics.median(new_counts) == 2, "after the fix, the two findings are kept separate"
    assert statistics.median(new_fill) < statistics.median(old_fill) / 1.5, (
        "the fix must meaningfully shrink the covered area for this exact shape")


def test_two_findings_with_real_empty_photograph_stay_bounded_before_and_after() -> None:
    """The simplest reported shape: two ordinary findings, real empty photograph between them.
    Reported for completeness -- this is the one case where BEFORE already refuses to merge
    directly (no chain to exploit), which the report states honestly rather than implying the fix
    changed something here."""
    old_counts, old_fill, new_counts, new_fill = _measure(scenarios.two_far_apart)
    _report("two_far_apart (2 findings, real gap)", old_counts, old_fill, new_counts, new_fill)
    assert old_counts == new_counts == [2] * TRIALS, (
        "a direct pair with a real gap was already refused before the fix -- confirmed, not assumed")


def test_a_legitimate_sign_is_unchanged_by_the_fix() -> None:
    """The control in the other direction: a real multi-line sign (2-8 lines) must still merge
    into one clean rectangle, at essentially the same area, before and after -- the fix must not
    have bought its improvement on the cascade cases by breaking the one merge that IS correct."""
    for lines in (2, 3, 5, 8):
        old_counts, old_fill, new_counts, new_fill = _measure(
            lambda rng, lines=lines: scenarios.legitimate_sign(rng, lines))
        _report(f"legitimate_sign, {lines} lines", old_counts, old_fill, new_counts, new_fill)
        assert old_counts == new_counts == [1] * TRIALS, (
            "a genuine multi-line sign must still merge into one rectangle", lines)
        # areas move by at most a few percent of the frame -- the tightened gap can very rarely
        # shave a corner off a jittered fixture; it must never fragment the sign.
        for o, n in zip(old_fill, new_fill, strict=True):
            assert abs(o - n) < 1.0, (lines, o, n)
