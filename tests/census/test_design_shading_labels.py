"""The design's shading geographies, pinned from the backend gate (D-C35, Task 10).

`md.active.geoLine` — "ZIP Code Tabulation Area", "Place (city/town)", "County" — is the DESIGN's
own `AREA_LABEL` rather than a runtime read of `/api/layers`. Spec §8.4 proposed the runtime read;
this stream did not take it, and the call is recorded in the plan's Task 10 Step 9: the string is
identical on both sides, and reading it at runtime would add a third fetch, a loading state on a
surface whose pixels are frozen, and a second source of truth for one word. §8.4's own scope note
already keeps `sourceLine`/`updatedLine` on `LAYER_META` for the same class of reason (A-C1 (11)).

So the two are pinned instead, in the shape
`tests/api/test_seller_listings.py::test_the_design_ownership_options_equal_ownerships_tuple`
(A22) established. Task 9 has now landed, so the right-hand side is `app.api.market.SHADING`
ITSELF rather than a typed copy of D-C35's ruled values — which is the one-line re-point Task 10's
report asked for, and closes its concern 4. A geography that moves on one side and not the other
is now a failure here rather than a map that labels a tract a ZIP area. The LEVEL half also has a
real counterpart and is pinned to it —
`app.census.tiger.BOUNDARY_FILES` must actually be able to load all three, or the endpoint would
have no geometry to serve whatever the design says.
"""

import re
from pathlib import Path

from app.api.market import SHADING, THRESHOLD_RULE
from app.census.tiger import BOUNDARY_FILES

# D-C35 (John, 2026-09-10): every layer at its own geography, and the legend names it. `income`
# moved 860 -> 140 "Census tract" on 2026-09-12 (controller ruling); both sides read SHADING, so
# the move is made in one place and this test is what proves the design followed it.
RULED_LEVEL = {layer: v["summary_level"] for layer, v in SHADING.items()}
RULED_LABEL = {layer: v["label"] for layer, v in SHADING.items()}

DESIGN = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "design-reference"
    / "design_handoff_practice_match_v3"
    / "Practice Match V3.dc.html"
)


def _dict_literal(name: str) -> dict[str, str]:
    m = re.search(rf"const {name} = \{{([^}}]*)\}};", DESIGN.read_text(encoding="utf-8"))
    assert m, f"the design no longer declares {name}"
    return dict(re.findall(r'(\w+):\s*"([^"]*)"', m.group(1)))


def test_the_designs_geography_labels_are_the_ruled_ones() -> None:
    assert _dict_literal("AREA_LABEL") == RULED_LABEL


def test_the_designs_geography_levels_are_the_ruled_ones() -> None:
    assert _dict_literal("AREA_LEVEL") == RULED_LEVEL


def test_every_ruled_summary_level_is_one_tiger_can_actually_load() -> None:
    """A label the boundary loader cannot produce geometry for is a legend line over an empty map."""
    loadable = {spec.summary_level for spec in BOUNDARY_FILES(2023, ["48"])}
    assert set(RULED_LEVEL.values()) <= loadable


def test_the_census_threshold_rule_is_one_sentence_read_by_both_the_api_and_the_design() -> None:
    """Review round 1, Important 3. A ZIP area whose veterinary count the Census withheld under
    its own three-establishment rule is served `suppressed: true, suppress_reason:
    "source_threshold"`, and TWO surfaces have to explain that to a member: the layer catalogue's
    `caveat`, which an integrator reads, and the map's own tooltip, which a buyer reads. Two
    spellings of one rule is how they come to disagree, so the sentence is pinned across them --
    the same shape `test_the_designs_geography_labels_are_the_ruled_ones` above uses for the
    geography names."""
    design = DESIGN.read_text(encoding="utf-8")
    assert THRESHOLD_RULE in design, "the design's tooltip no longer states the Census rule the API states"
    assert design.count(THRESHOLD_RULE) == 1, "the rule is stated once in the design, not twice"
    assert "source_threshold" in design, "nothing in the design branches on the reason the API sends"
