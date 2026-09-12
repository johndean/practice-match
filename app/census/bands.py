"""Legend bands for the shaded layers (D-C36, D-NS17).

The design's published bands are kept — they are dollar-meaningful, legible, and what the design
published — and the honesty is carried by the hover tip rather than by re-cutting the legend. This
is the one implementation of "does this polygon's margin of error cross a legend stop", read both
by the endpoint (which puts the caveat in the tip, against the asking layer's OWN stops) and by `scripts/measure_band_ambiguity.py`
(which produces the share D-C34 gates the tract toggle on). Two implementations would put
different sentences on the same polygon.

`INCOME_STOPS` is a literal here and not a read of the design, because the design bundle is never
shipped and `app/` may not depend on it at run time. It was DERIVED from the amended design file
rather than copied out of a plan, and it is pinned two-way against that same file by
`tests/census/test_bands.py::test_the_design_income_stops_equal_the_band_constants`, so a re-cut
on either side fails on both. That pin is not decorative: D-C46 (John, 2026-09-11) re-scaled
`growth`'s stops the week this module was written, measured across 29,232 US places, because the
frozen ones put 79.9 % of them in one bucket and gave the declining 30.5 % no band at all. It
reached `growth` and not `income`; the next ruling may reach either."""
from __future__ import annotations

# logic.js's VALUE_LAYERS.income.stops. Five buckets, four stops (V3 widened income's ramp from
# V2's four; every other layer keeps four buckets and three stops).
INCOME_STOPS: tuple[int, ...] = (50000, 75000, 100000, 150000)

# logic.js's VALUE_LAYERS.households.stops, re-cut on 2026-09-12 when households moved from a
# graduated symbol at the listing point to a shaded layer at the CENSUS TRACT. The design's
# city-scale `[10000, 25000, 45000]` put 100.0 % of the 85,381 US tracts that carry
# `B11001_001E` into ONE class; these are its quartiles rounded to numbers a 10.5 px legend can
# carry (p25 1,054, p50 1,446, p75 1,897) and take 21.9 / 31.4 / 26.0 / 20.7 % of them.
# Pinned two-way against the design by `tests/census/test_bands.py`, exactly as income's are: a
# re-cut on either side fails on both.
HOUSEHOLDS_STOPS: tuple[int, ...] = (1000, 1500, 2000)


def band_index(value: float, stops: tuple[int, ...] = INCOME_STOPS) -> int:
    """The design's own right-open rule, `logic.js`'s `bucket`:
    `while (i < cfg.stops.length && v >= cfg.stops[i]) i++`. A value exactly ON a stop belongs to
    the band above it, on both sides of the wire."""
    i = 0
    while i < len(stops) and value >= stops[i]:
        i += 1
    return i


def band_ambiguous(value: float | None, moe: float | None, stops: tuple[int, ...] = INCOME_STOPS) -> bool:
    """Whether `value ± moe` spans more than one legend band.

    `False` for a missing value and for a missing margin, and those are two DIFFERENT states:
    a missing value is `_suppression(None, None) == (False, None)` — not suppressed, nothing to
    band — and a present value with no margin is already suppressed `no_moe`, so it is greyed
    rather than caveated. A margin of exactly zero spans nothing. None of these is "ambiguous",
    and a caveat on a polygon with no margin would be a sentence about a number that was never
    reported."""
    if value is None or not moe:
        return False
    return band_index(value - moe, stops) != band_index(value + moe, stops)
