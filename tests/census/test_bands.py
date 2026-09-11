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


def test_the_designs_bucket_rule_is_still_the_one_band_index_reimplements() -> None:
    """The stops are only half of a band: the COMPARISON decides which side of a stop a value
    falls. `band_index` reimplements the design's `bucket` in Python because the server has no
    JavaScript, so the design's own loop is pinned as a fixed string — a `>` where the design has
    `>=` would move every polygon that sits exactly on a stop and move nothing else, which is the
    one drift the stop pin above cannot see."""
    logic = (ROOT / "frontend" / "src" / "logic.js").read_text(encoding="utf-8")
    assert logic.count("while (i < cfg.stops.length && v >= cfg.stops[i]) i++;") == 1
