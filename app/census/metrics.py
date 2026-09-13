"""Pure market-metric maths. Spec §8 (formulas, formula_version v1) and §14 (MOE/CV rules).
No I/O here so every rule is unit-testable with the spec's own numbers (task-B4-brief.md Steps
1-2, plan Task B4a). `competition_level` is unit-tested here but has no caller in this module —
the market API derives the competition band at serialisation time, not at materialisation time
(plan amendment A-C15 (7)); its absence of a caller in `app/census` is not a defect."""

from __future__ import annotations

import math
from collections.abc import Iterable

Z90: float = 1.645
CV_THRESHOLD: float = 0.30
PET_RATE: float = 0.57  # documented national placeholder until a licensed regional rate is cleared (§8)
FORMULA_VERSION: str = "v1"
COMPETITION_LEVELS: tuple[tuple[float, str], ...] = ((1.4, "Low"), (2.2, "Moderate"))  # per 10k households; else "High" — the approved design's thresholds


def cv(estimate: float | None, moe: float | None) -> float | None:
    """Coefficient of variation: (MOE / Z90) / |estimate|. `None` when the estimate is missing or
    zero (division would blow up) or the MOE itself is missing (§14)."""
    if estimate in (None, 0) or moe is None:
        return None
    return (float(moe) / Z90) / abs(float(estimate))


def high_moe(estimate: float | None, moe: float | None) -> bool:
    """True when the coefficient of variation strictly exceeds `CV_THRESHOLD` (§14). A `cv` of
    exactly the threshold, or one that cannot be computed at all, is not "high"."""
    c = cv(estimate, moe)
    return c is not None and c > CV_THRESHOLD


def weighted_count(parts: Iterable[tuple[float | None, float | None, float | None]]) -> tuple[float | None, float | None, int]:
    """Sum `weight * estimate` over parts that carry both an estimate and a weight; MOEs combine
    in quadrature — `sqrt(sum((weight * moe) ** 2))`. A part with a missing WEIGHT is excluded
    exactly like one with a missing estimate (B4a review, A-C17 (3)): `weighted_median` already
    treats a missing weight this way, and a caller should not have to remember which of the two
    weighting functions tolerates one. Returns `(estimate, moe, excluded)`, where `excluded`
    counts parts with no estimate or no weight; both `estimate` and `moe` are `None` when every
    part was excluded (including an empty iterable).

    B4b fix round 1 (A-C21 (1), correcting A-C17 (1)): the combined MOE is `None` (unknown) when
    NO contributing part reported one at all — never silently `0.0`, which reads as "measured with
    perfect precision", the exact opposite of what a missing margin means. A part that reports a
    GENUINE zero margin still contributes zero variance, and if at least one contributing part
    reports any margin (zero or otherwise), the combined MOE is still computable — a part with no
    margin among those simply contributes nothing to the quadrature sum, rather than poisoning the
    whole result to `None`. The earlier shape of this function conflated "nobody reported a
    margin" with "a margin of zero was reported", which let a whole-catchment lack of ACS margins
    for population/households read as certainty instead of the unmeasured case §14 must catch."""
    est = 0.0
    var = 0.0
    excluded = 0
    used = False
    moe_known = False
    for e, mo, w in parts:
        if e is None or w is None:
            excluded += 1
            continue
        used = True
        est += w * e
        if mo is not None:
            moe_known = True
            var += (w * mo) ** 2
    if not used:
        return None, None, excluded
    return est, (math.sqrt(var) if moe_known else None), excluded


def weighted_median(parts: Iterable[tuple[float | None, float | None]]) -> float | None:
    """Household-weighted MEDIAN of per-area medians — an approximation of a true median over the
    combined area (§14, amended 2026-09-12 by Task INCOME-MEDIAN).

    The rule: sort the contributing parts by value, accumulate their weights, and return the value
    whose own weight block contains the 50 % mark (half the total weight). When the cumulative
    weight lands EXACTLY on half the total the mark falls BETWEEN two parts rather than inside
    either, and the answer is the linear interpolation of the two straddling values — their
    midpoint, the same convention the ordinary median of an even number of observations uses. With
    unit weights this is exactly the ordinary median, and the result is invariant to duplicating
    every part: the statistic depends on the shape of the weight distribution, not on its total.

    Until 2026-09-12 this returned `Σ(v·w)/Σw` — a weighted MEAN — while its name, the column it
    fills (`median_hh_income`) and the card's own label all read it as a median. Over a
    right-skewed income distribution the mean of medians sits systematically above the median of
    medians; measured on QA over the 64 tracts in one Austin listing's 5-mile ring it read $109,744
    against a true $99,357, 10.5 % high.

    A part with a missing value, or a weight that is not a positive number, is skipped — missing,
    zero, negative or NaN alike (fix round 1, Minor 2). The earlier guard was `w not in (None, 0)`,
    which let the last two through: a negative weight makes the running total go DOWN, so the
    cumulative weight can cross half the total more than once, and a NaN poisons `sum` so that
    `cum < half` is False on the first test and the sentinel index reads the LAST part by negative
    indexing — `[(100000, 1000), (999999, nan)]` returned their midpoint, a number fabricated out of
    an unusable weight. No caller can produce either (`materialize.py` multiplies households by an
    overlap fraction, both non-negative), which is why the guard has to say so rather than rely on
    it. `None` when no part contributes any weight. The figure stays flagged approximate: it is still an approximation of
    the combined-area median and still has no combined margin of error by construction."""
    usable = sorted(((float(v), float(w)) for v, w in parts if v is not None and w is not None and float(w) > 0), key=lambda p: p[0])
    total = sum(w for _, w in usable)
    if not total:
        return None
    half = total / 2
    cum = 0.0
    i = -1
    while cum < half:
        i += 1
        cum += usable[i][1]
    value = usable[i][0]
    return value if cum > half else (value + usable[i + 1][0]) / 2


def pet_households_est(hh: float | None) -> int | None:
    """Estimated pet-owning households at the national placeholder incidence rate `PET_RATE`
    (§8). `None` when households is missing."""
    return None if hh is None else round(float(hh) * PET_RATE)


def population_growth_pct(now: float | None, prior: float | None) -> float | None:
    """Percentage change in population between two vintages. `None` when either figure is missing
    or the prior figure is zero (division would blow up); a real decline is a valid, negative
    answer."""
    if now is None or prior in (None, 0):
        return None
    return (float(now) - float(prior)) / float(prior) * 100


def vets_per_10k(estab: float | None, hh: float | None) -> float | None:
    """Establishments (NAICS 541940) per 10,000 households. `None` when either input is missing
    or households is zero; zero establishments is itself a valid answer."""
    if estab is None or hh in (None, 0):
        return None
    return float(estab) / (float(hh) / 10000)


def income_index_vs_us(local: float | None, us: float | None) -> float | None:
    """Local median household income as a percentage above (positive) or below (negative) the
    national figure. `None` when either figure is missing or the national figure is zero."""
    if local is None or us in (None, 0):
        return None
    return (float(local) - float(us)) / float(us) * 100


def revenue_per_establishment(payroll_k: float | None, estab: float | None) -> float | None:
    """Annual payroll (reported in thousands) per establishment, in dollars — a payroll proxy,
    not true revenue. `None` when either input is missing or there are no establishments."""
    if payroll_k is None or estab in (None, 0):
        return None
    return float(payroll_k) * 1000 / float(estab)


def opportunity_score(income: float | None, growth: float | None, per10k: float | None) -> int | None:
    """0-100 composite, rounded to the nearest whole point: 40% median household income (capped
    once it reaches $140,000), 35% population growth (capped once it reaches 40%), 25% inverse
    competition (floored at zero once establishments per 10k households reaches 3). `None` unless
    every input is present; the final score is clamped to `[0, 100]` even for an out-of-range
    input, since a per10k below zero can otherwise push the raw total past 100."""
    if income is None or growth is None or per10k is None:
        return None
    raw = 40 * min(float(income) / 140000, 1) + 35 * min(float(growth) / 40, 1) + 25 * max(0.0, 1 - float(per10k) / 3)
    return round(max(0.0, min(100.0, raw)))


def competition_level(per10k: float | None) -> str | None:
    """Bands `per10k` against `COMPETITION_LEVELS` (the approved design's thresholds); anything at
    or above the highest threshold is `"High"`. `None` when there is no input to band."""
    if per10k is None:
        return None
    for threshold, label in COMPETITION_LEVELS:
        if float(per10k) < threshold:
            return label
    return "High"
