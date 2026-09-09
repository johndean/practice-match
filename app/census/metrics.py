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
    in quadrature — `sqrt(sum((weight * moe) ** 2))`. A part with a missing MOE contributes zero
    variance, not a skip. A part with a missing WEIGHT is excluded exactly like one with a missing
    estimate (B4a review, A-C17 (3)): `weighted_median` already treats a missing weight this way,
    and a caller should not have to remember which of the two weighting functions tolerates one.
    Returns `(estimate, moe, excluded)`, where `excluded` counts parts with no estimate or no
    weight; both `estimate` and `moe` are `None` when every part was excluded (including an empty
    iterable)."""
    est = 0.0
    var = 0.0
    excluded = 0
    used = False
    for e, mo, w in parts:
        if e is None or w is None:
            excluded += 1
            continue
        used = True
        est += w * e
        var += (w * (mo or 0)) ** 2
    return (est if used else None, math.sqrt(var) if used else None, excluded)


def weighted_median(parts: Iterable[tuple[float | None, float | None]]) -> float | None:
    """Household-weighted average of per-area medians — an approximation of a true median over the
    combined area (§8). A part with a missing value or a missing/zero weight is skipped. `None`
    when no part contributes any weight."""
    num = 0.0
    den = 0.0
    for v, w in parts:
        if v is None or w in (None, 0):
            continue
        num += float(v) * float(w)
        den += float(w)
    return num / den if den else None


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
