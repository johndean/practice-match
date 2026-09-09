"""Pure-maths unit tests for `app.census.metrics` (plan Task B4a, spec §8 formulas and §14
MOE/CV rules). No database, no network, no fixtures — every input is a literal number so the
module is exercised exactly as it will run: no I/O.

The brief's own illustrative comment for the materialisation test claims a coefficient of
variation "≈ 0.36" where the real figure (computed here, not eyeballed) is 0.3118 against the
0.30 threshold — a 3.9% margin dressed up as comfortable. To not repeat that mistake, every CV
value below is computed with Python and asserted to four decimal places, and the threshold cases
below are deliberately spread: two pairs sit clearly either side of 0.30 and a third sits exactly
on the boundary, to prove `high_moe` uses a strict `>` rather than `>=`.
"""

from __future__ import annotations

import math

import pytest

from app.census import metrics as m


def test_cv_computes_moe_over_z90_over_estimate() -> None:
    # moe/Z90/|estimate|, computed independently: 500/1.645/1000 = 0.303951...
    assert m.cv(1000, 500) == pytest.approx(0.303951, abs=1e-6)
    assert m.cv(1000, 490) == pytest.approx(0.297872, abs=1e-6)
    assert m.cv(1000, 800) == pytest.approx(0.486322, abs=1e-6)
    assert m.cv(1000, 200) == pytest.approx(0.121581, abs=1e-6)
    assert m.cv(1000, 493.5) == pytest.approx(0.30, abs=1e-9)  # exactly on the threshold
    assert m.cv(-1000, 500) == pytest.approx(0.303951, abs=1e-6)  # abs() of a negative estimate


def test_cv_is_none_without_a_usable_estimate_or_moe() -> None:
    assert m.cv(None, 10) is None       # estimate missing
    assert m.cv(0, 10) is None          # estimate zero — division would blow up
    assert m.cv(100, None) is None      # moe missing


def test_high_moe_uses_a_strict_threshold() -> None:
    # Two pairs clearly either side of 0.30, one pair barely either side, and the boundary itself.
    assert m.high_moe(1000, 800) is True     # cv ≈ 0.486 — clearly above
    assert m.high_moe(1000, 200) is False    # cv ≈ 0.122 — clearly below
    assert m.high_moe(1000, 500) is True     # cv ≈ 0.304 — just above
    assert m.high_moe(1000, 490) is False    # cv ≈ 0.298 — just below
    assert m.high_moe(1000, 493.5) is False  # cv == 0.30 exactly — not strictly greater
    assert m.high_moe(0, 10) is False        # cv is None (estimate zero) → not high


def test_weighted_count_sums_with_weights_and_combines_moe_in_quadrature() -> None:
    est, moe, excluded = m.weighted_count([(100, 10, 1.0), (200, 20, 0.5), (None, 5, 1.0)])
    assert est == 200 and moe == pytest.approx(math.sqrt(10**2 + 10**2)) and excluded == 1


def test_weighted_count_returns_an_unknown_moe_when_no_part_reports_one() -> None:
    """B4b fix round 1 (A-C21 (1)), correcting A-C17 (1): the earlier shape of this test asserted
    `moe == 0.0` here, which is exactly the information-loss bug the reviewer traced by hand --
    when every CONTRIBUTING part has an estimate but no margin at all, the combined margin must
    come back `None` (unmeasured), not `0.0` (measured with perfect precision). A `0.0` combined
    margin now means at least one part genuinely REPORTED a zero margin (see the next test), never
    "nobody said.\""""
    est, moe, excluded = m.weighted_count([(300, None, 2.0)])
    assert est == 600 and moe is None and excluded == 0


def test_weighted_count_treats_a_genuinely_reported_zero_moe_as_zero_variance() -> None:
    """The other side of the same fix: a part that reports an ACTUAL zero margin (not a missing
    one) still contributes zero variance, exactly as before -- the distinction is "no part said
    anything" (None) versus "a part said zero" (0.0), not whether zero appears in the arithmetic."""
    est, moe, excluded = m.weighted_count([(300, 0.0, 2.0)])
    assert est == 600 and moe == 0.0 and excluded == 0


def test_weighted_count_combines_a_mix_of_reported_and_missing_moe() -> None:
    """When AT LEAST ONE contributing part reports a real margin, the combined margin is still
    computable -- a part with no margin contributes zero variance to that sum (skipped from the
    quadrature sum, not from the estimate), rather than poisoning the whole result to `None`."""
    est, moe, excluded = m.weighted_count([(100, 10, 1.0), (200, None, 1.0)])
    assert est == 300 and moe == pytest.approx(10.0) and excluded == 0


def test_weighted_count_with_no_usable_estimate_returns_none_est_and_moe() -> None:
    est, moe, excluded = m.weighted_count([(None, 5, 1.0), (None, 3, 1.0)])
    assert est is None and moe is None and excluded == 2


def test_weighted_count_of_an_empty_iterable_returns_none_est_and_moe() -> None:
    est, moe, excluded = m.weighted_count([])
    assert est is None and moe is None and excluded == 0


def test_weighted_count_treats_a_missing_weight_like_an_excluded_part() -> None:
    """B4a review (A-C17 (3)): `weighted_count` and `weighted_median` disagreed on whether a
    weight may be missing -- `weighted_median` already skips a `None` weight (see
    `test_weighted_median_skips_a_present_value_with_a_missing_weight` below), while
    `weighted_count` unconditionally did `float(w)`, which raises `TypeError` on `None`. A caller
    should not have to remember which function tolerates a missing weight, so `weighted_count` now
    excludes a part with no weight exactly as it already excludes one with no estimate."""
    est, moe, excluded = m.weighted_count([(100, 10, 1.0), (200, 20, None)])
    assert est == 100 and moe == 10.0 and excluded == 1


def test_weighted_median_is_household_weighted_average() -> None:
    assert m.weighted_median([(100000, 1000), (50000, 3000), (None, 500)]) == 62500


def test_weighted_median_skips_zero_weight_as_well_as_missing_value() -> None:
    assert m.weighted_median([(100000, 1000), (999999, 0)]) == 100000


def test_weighted_median_skips_a_present_value_with_a_missing_weight() -> None:
    """B4a review (A-C17 (2)): the compound guard `v is None or w in (None, 0)` had an untested
    arm -- a present VALUE paired with a MISSING weight -- that branch coverage cannot see through
    a single compound boolean. Every existing case above pairs a missing value with a present
    weight, or a present value with a present-but-zero weight; this is the remaining combination."""
    assert m.weighted_median([(100000, 1000), (999999, None)]) == 100000


def test_weighted_median_is_none_with_no_usable_weight() -> None:
    assert m.weighted_median([(None, 1)]) is None
    assert m.weighted_median([]) is None


def test_pet_households_est() -> None:
    assert m.pet_households_est(27600) == 15732
    assert m.pet_households_est(None) is None


def test_population_growth_pct() -> None:
    assert m.population_growth_pct(81900, 71716) == pytest.approx(14.2, abs=0.01)
    assert m.population_growth_pct(90, 100) == pytest.approx(-10.0)   # decline is a valid answer
    assert m.population_growth_pct(100, 0) is None    # prior zero — division would blow up
    assert m.population_growth_pct(None, 100) is None
    assert m.population_growth_pct(100, None) is None


def test_vets_per_10k() -> None:
    assert m.vets_per_10k(7, 27600) == pytest.approx(2.536, abs=1e-3)
    assert m.vets_per_10k(0, 1000) == 0.0    # zero establishments is a real answer, not "missing"
    assert m.vets_per_10k(None, 27600) is None
    assert m.vets_per_10k(7, None) is None
    assert m.vets_per_10k(7, 0) is None


def test_income_index_vs_us() -> None:
    assert m.income_index_vs_us(118400, 75149) == pytest.approx(57.55, abs=0.01)
    assert m.income_index_vs_us(50000, 75149) == pytest.approx(-33.465515, abs=1e-4)   # below the US figure
    assert m.income_index_vs_us(None, 75149) is None
    assert m.income_index_vs_us(118400, None) is None
    assert m.income_index_vs_us(118400, 0) is None


def test_revenue_per_establishment() -> None:
    assert m.revenue_per_establishment(4795, 7) == pytest.approx(685000, abs=1)
    assert m.revenue_per_establishment(None, 7) is None
    assert m.revenue_per_establishment(4795, None) is None
    assert m.revenue_per_establishment(4795, 0) is None


def test_opportunity_score_is_clamped_rounded_and_needs_all_inputs() -> None:
    # 40*(118400/140000) + 35*(14.2/40) + 25*(1 - 2.54/3) = 33.83 + 12.43 + 3.83 = 50.09 -> 50
    assert m.opportunity_score(118400, 14.2, 2.54) == 50
    assert m.opportunity_score(200000, 60, 4.0) == 75       # income and growth capped, competition floor 0
    assert m.opportunity_score(0, 0, 0) == 25
    assert m.opportunity_score(0, 0, 3) == 0                # every term bottoms out at once
    assert m.opportunity_score(140000, 40, -10) == 100      # a pathological negative per10k still clamps at 100
    assert m.opportunity_score(-140000, 0, 3) == 0          # a pathological negative income still floors at 0
    assert m.opportunity_score(None, 14.2, 2.54) is None
    assert m.opportunity_score(118400, None, 2.54) is None
    assert m.opportunity_score(118400, 14.2, None) is None


def test_formula_version_is_pinned() -> None:
    """B4a review (A-C17 (4)): nothing asserted `FORMULA_VERSION`'s value -- a silent bump would
    let two generations of a metric (computed under different formulas) coexist in `market_metric`
    under the same `formula_version` string, since the materialisation stamps every derived row
    with whatever this constant currently holds."""
    assert m.FORMULA_VERSION == "v1"


def test_competition_level_uses_the_design_thresholds() -> None:
    assert m.competition_level(1.39) == "Low"        # first iteration's own threshold trips
    assert m.competition_level(1.4) == "Moderate"     # first iteration false, second trips
    assert m.competition_level(2.0) == "Moderate"
    assert m.competition_level(2.2) == "High"         # both iterations false — falls through
    assert m.competition_level(5.0) == "High"
    assert m.competition_level(None) is None
