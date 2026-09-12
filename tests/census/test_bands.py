"""Band ambiguity for the income layer (D-C36, D-NS17).

The design's bands are not re-cut: they are dollar-meaningful, legible, and what the design
published. The honesty is carried by the hover tip, and this is what the tip and the tract-toggle
measurement both read — ONE implementation, because two would put different sentences on the same
polygon.

The two pins at the bottom are the whole point of the module living here rather than in the
endpoint: `INCOME_STOPS` is a literal in shipped code (the design bundle is never shipped, so
`app/` may not read it at run time), and these cases are what stop that literal drifting from the
design in either direction. D-C46 (John, 2026-09-11) moved `growth`'s stops the week this was
written, which is the drift they exist to catch."""
import re
from pathlib import Path

from app.census import bands

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "docs" / "design-reference" / "design_handoff_practice_match_v3" / "Practice Match V3.dc.html"


def _value_layers() -> str:
    """The amended design's `VALUE_LAYERS` object literal, and nothing else.

    Anchored on the declaration rather than searched for by layer name: `income:` occurs thirty
    times in the file, and a pin that can match the wrong one is a pin that can pass while the
    design's real stops move."""
    design = DESIGN.read_text(encoding="utf-8")
    start = design.index("const VALUE_LAYERS = {")
    return design[start:design.index("\n};", start)]


def test_band_index_is_the_designs_own_right_open_rule() -> None:
    """`logic.js`'s `bucket`: `while (i < cfg.stops.length && v >= cfg.stops[i]) i++`. Right-open,
    so a value exactly ON a stop belongs to the band ABOVE it."""
    assert bands.band_index(0) == 0
    assert bands.band_index(49999.99) == 0
    assert bands.band_index(50000) == 1
    assert bands.band_index(74999) == 1
    assert bands.band_index(75000) == 2
    assert bands.band_index(100000) == 3
    assert bands.band_index(149999) == 3
    assert bands.band_index(150000) == 4
    assert bands.band_index(10 ** 9) == 4


def test_band_ambiguous_is_true_only_when_the_margin_crosses_a_stop() -> None:
    # The spec's own example: $92,150 ± $6,420 spans 85,730..98,570 — both inside 75K-100K.
    assert bands.band_ambiguous(92150, 6420) is False
    # Widen it past 100,000 and it spans two bands.
    assert bands.band_ambiguous(92150, 9000) is True
    # And past 75,000 downwards.
    assert bands.band_ambiguous(78000, 4000) is True
    # Exactly to the stop is not across it: the rule is right-open, so 100,000 IS the next band —
    # hi == 100000 lands in band 3 and lo in band 2, which IS a crossing.
    assert bands.band_ambiguous(95000, 5000) is True
    assert bands.band_ambiguous(94999, 5000) is False


def test_a_missing_value_or_a_missing_margin_is_never_ambiguous() -> None:
    """Global Constraint (c): the producer's sentinel. `_suppression(None, None)` returns
    `(False, None)` — a missing VALUE is not suppressed and there is nothing to band — and a
    present value with a missing margin is already `suppressed='no_moe'`, so it is greyed rather
    than caveated. Neither is 'ambiguous', and a guard that said otherwise would put a margin
    caveat on a polygon that has no margin."""
    assert bands.band_ambiguous(None, 6420) is False
    assert bands.band_ambiguous(92150, None) is False
    assert bands.band_ambiguous(None, None) is False
    assert bands.band_ambiguous(92150, 0) is False


def test_the_design_income_stops_equal_the_band_constants() -> None:
    """Two-way, against the AMENDED design file itself — the shape
    `tests/api/test_seller_listings.py::test_the_design_ownership_options_equal_ownerships_tuple`
    (A22, Task SL10) established. If the design's bands are ever re-cut, this fails on both sides
    at once instead of the map and the legend quietly disagreeing."""
    layers = _value_layers()
    m = re.search(r"income:\s*\{[^}]*?stops:\s*\[([^\]]*)\]", layers)
    assert m, "VALUE_LAYERS.income no longer declares `stops` — the design's bands moved"
    assert tuple(int(s) for s in m.group(1).split(",")) == bands.INCOME_STOPS
    # …and the buckets the legend prints are still five, one more than the stops (D-C36).
    b = re.search(r"income:\s*\{[^}]*?buckets:\s*\[([^\]]*)\]", layers)
    assert b and len(b.group(1).split(",")) == len(bands.INCOME_STOPS) + 1


def _area_layers() -> str:
    """The amended design's `AREA_LAYERS` object literal — the CHOROPLETH's own class breaks
    (A24.25, D-L1). Anchored on the declaration for the same reason `_value_layers` is."""
    design = DESIGN.read_text(encoding="utf-8")
    start = design.index("const AREA_LAYERS = {")
    return design[start:design.index("\n};", start)]


def test_the_design_households_stops_equal_the_band_constants() -> None:
    """Income's pin, for the second layer that carries a published margin and can therefore be
    band-ambiguous. `band_ambiguous` takes its stops as a parameter and the endpoint passes
    `BAND_STOPS[layer]`, so asking the question against the WRONG layer's legend is possible in
    principle -- and would be invisible, because it answers True or False either way. The two
    tables must agree, and here they are made to.

    The DESIGN side is `AREA_LAYERS`, not `VALUE_LAYERS`: the choropleth and the community cards
    class the same metric at different geographies, and it is the choropleth's legend a polygon's
    caveat is about (A24.25)."""
    layers = _area_layers()
    m = re.search(r"households:\s*\{[^}]*?stops:\s*\[([^\]]*)\]", layers)
    assert m, "AREA_LAYERS.households no longer declares `stops` — the map's bands moved"
    assert tuple(int(s) for s in m.group(1).split(",")) == bands.HOUSEHOLDS_STOPS
    b = re.search(r"households:\s*\{[^}]*?buckets:\s*\[([^\]]*)\]", layers)
    # The LABELS are counted by their quotes, not by commas: a tract-scale label carries a
    # thousands separator ("1,000 to 1,500") and splitting on commas counts it twice.
    assert b and len(re.findall(r'"[^"]*"', b.group(1))) == len(bands.HOUSEHOLDS_STOPS) + 1


def test_every_layer_the_endpoint_bands_has_the_designs_own_stops_and_no_other_does() -> None:
    """The set, both ways. A layer in `BAND_STOPS` with no published margin would be asking a
    question about a number nobody reported; a layer with a margin and NO entry would silently
    answer False for every polygon, which is the quieter failure of the two."""
    from app.api.market import BAND_STOPS

    assert set(BAND_STOPS) == {"income", "households"}
    assert BAND_STOPS["income"] is bands.INCOME_STOPS
    assert BAND_STOPS["households"] is bands.HOUSEHOLDS_STOPS


def test_band_index_keeps_the_minus_sign_on_a_break_that_has_a_band_below_zero() -> None:
    """`band_index` takes its `stops` as a parameter, and the design now has a break with a band
    BELOW ZERO: D-C46 re-scaled `growth` to `[0, 5, 15]`, whose bottom bucket is labelled
    "Declining", because the frozen `[10, 20, 35]` had no band a decline could land in at all.

    So the one arithmetic this function must not do is the one `logic.js`'s `num()` does: strip the
    minus sign, which turns every decline into a growth band. Nothing routes growth through here
    today (D-NS17 bands only `income`), but the parameter invites it, and a decline reaching band 0
    is what makes that safe. Derived from the design rather than retyped, so a ruling that
    supersedes D-C46 moves this case with it."""
    layers = _value_layers()
    m = re.search(r"growth:\s*\{[^}]*?stops:\s*\[([^\]]*)\]", layers)
    assert m, "VALUE_LAYERS.growth no longer declares `stops`"
    growth = tuple(int(s) for s in m.group(1).split(","))
    assert bands.band_index(growth[0] - 1, growth) == 0      # below the first stop: the bottom band
    assert bands.band_index(growth[0], growth) == 1          # right-open, exactly as for income
    assert bands.band_ambiguous(growth[0] - 1, 0.5, growth) is False
    assert bands.band_ambiguous(growth[0] - 1, 2, growth) is True


def test_the_designs_bucket_rule_is_still_the_one_band_index_reimplements() -> None:
    """The stops are only half of a band: the COMPARISON decides which side of a stop a value
    falls. `band_index` reimplements the design's `bucket` in Python because the server has no
    JavaScript, so the design's own loop is pinned as a fixed string — a `>` where the design has
    `>=` would move every polygon that sits exactly on a stop and move nothing else, which is the
    one drift the stop pin above cannot see."""
    logic = (ROOT / "frontend" / "src" / "logic.js").read_text(encoding="utf-8")
    assert logic.count("while (i < cfg.stops.length && v >= cfg.stops[i]) i++;") == 1
