"""The design's shading geographies, pinned from the backend gate (D-C35, Task 10).

`md.active.geoLine` — "ZIP Code Tabulation Area", "Place (city/town)", "County" — is the DESIGN's
own `AREA_LABEL` rather than a runtime read of `/api/layers`. Spec §8.4 proposed the runtime read;
this stream did not take it, and the call is recorded in the plan's Task 10 Step 9: the string is
identical on both sides, and reading it at runtime would add a third fetch, a loading state on a
surface whose pixels are frozen, and a second source of truth for one word. §8.4's own scope note
already keeps `sourceLine`/`updatedLine` on `LAYER_META` for the same class of reason (A-C1 (11)).

So the two are pinned instead, in the shape
`tests/api/test_seller_listings.py::test_the_design_ownership_options_equal_ownerships_tuple`
(A22) established. **Task 9 has not landed**, so `app.api.market.SHADING` does not exist yet: the
right-hand side below is D-C35's ruled values, and Task 9 or Task 11 re-points it at `SHADING`
in one line. The LEVEL half already has a real counterpart today and is pinned to it —
`app.census.tiger.BOUNDARY_FILES` must actually be able to load all three, or the endpoint would
have no geometry to serve whatever the design says.
"""

import re
from pathlib import Path

from app.census.tiger import BOUNDARY_FILES

# D-C35 (John, 2026-09-10): every layer at its own geography, and the legend names it.
RULED_LEVEL = {"income": "860", "growth": "160", "econ": "050"}
RULED_LABEL = {"income": "ZIP Code Tabulation Area", "growth": "Place (city/town)", "econ": "County"}

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
