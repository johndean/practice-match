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
from app.census.serve import APPROXIMATE_BASIS, BAND_LABEL
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


# ---------------------------------------------------------------------------------------------
# A33.3 (Task SCREEN-LABELS, 2026-09-13; D-C51 caption audit §3.2, rows R13-R18) — EVERY LAYER
# ROW NAMES THE GEOGRAPHY IT SHADES.
#
# `LAYER_META.<layer>.sub` is the sentence under each row of the Browse "Market data layers"
# drawer. It read "Household income by community · ACS 5-year" for a layer that draws Census
# tracts, and the other five named no geography at all -- five rows silent and the sixth wrong.
# The wrong one is not a typo: income moved 860 -> 140 on 2026-09-12 and the row did not follow,
# which is exactly the drift `test_the_designs_geography_labels_are_the_ruled_ones` catches for
# `AREA_LABEL` and nothing caught here.
#
# So the rows are pinned against the SAME table -- `SHADING`, which the route, the legend, the
# map tip and the community notes all read -- and a layer that moves again fails on both sides at
# once. The phrase is the ruled label, lower-cased where the sentence demands it ("by place
# (city/town)", "by county"): what is pinned is the NAME, not its capitalisation.
# ---------------------------------------------------------------------------------------------


def _layer_subs() -> dict[str, str]:
    """Each layer's `sub` line from the amended design's `LAYER_META`, read rather than retyped.

    Anchored on the declaration and split per layer key, for `_dict_literal`'s own reason: this
    object is NESTED, so a flat `[^}]*` read stops at the first inner brace and a bare search for
    `income:` would match one of its thirty other occurrences in the file."""
    design = DESIGN.read_text(encoding="utf-8")
    start = design.index("const LAYER_META = {")
    block = design[start:design.index("\n};", start)]
    subs: dict[str, str] = {}
    layer = None
    for line in block.split("\n"):
        head = re.match(r"  (\w+): \{", line)
        if head:
            layer = head.group(1)
        m = re.match(r'    sub: "([^"]*)",', line)
        if m and layer:
            subs[layer] = m.group(1)
    return subs


def test_every_layer_row_names_the_geography_that_layer_shades() -> None:
    """The pin, both ways round: every shading layer has a row, and every row names its OWN ruled
    geography and no other layer's. The second half is what catches a copy-paste: "Total
    households by ZIP Code Tabulation Area" would pass a test that only looked for the presence of
    a geography word."""
    subs = _layer_subs()
    assert set(subs) == set(RULED_LABEL), (
        f"the design's LAYER_META rows ({sorted(subs)}) are not the shading layers "
        f"({sorted(RULED_LABEL)})"
    )
    for layer, sub in subs.items():
        own = RULED_LABEL[layer]
        assert f"by {own.lower()}" in sub.lower(), (
            f"LAYER_META.{layer}.sub does not name its own geography {own!r}: {sub!r}"
        )
        for label in RULED_LABEL.values():
            if label.lower() == own.lower():
                continue
            assert label.lower() not in sub.lower(), (
                f"LAYER_META.{layer}.sub names {label!r}, which is not the geography it shades"
            )


def test_no_layer_row_still_calls_its_geography_the_community() -> None:
    """The word the audit found, gone as a GEOGRAPHY from every row. It is a real word elsewhere
    in the catalogue -- `means` and `why` describe what a figure is for -- so the assertion is on
    the rows alone, which is the only place it stood for a geography."""
    for layer, sub in _layer_subs().items():
        assert "community" not in sub.lower(), (
            f"LAYER_META.{layer}.sub still calls its geography 'community': {sub!r}"
        )


def test_every_layer_row_follows_the_one_ruled_grammar() -> None:
    """One sentence for all six -- `<statistic> by <geography> · <dataset>` -- so a member reading
    down the drawer is reading one list and not six. Pinned as a SHAPE rather than as six
    literals: the strings themselves are the design's and belong in
    `frontend/tests/design-amendments.ts`, and what this owns is that none of them drifts out of
    the grammar the ruling set."""
    for layer, sub in _layer_subs().items():
        statistic, sep, rest = sub.partition(" by ")
        assert sep, f"LAYER_META.{layer}.sub does not use the ruled 'by' grammar: {sub!r}"
        assert statistic and statistic[0].isupper(), f"{layer}: the statistic leads: {sub!r}"
        geography, mid, dataset = rest.partition(" \u00b7 ")
        assert mid, f"LAYER_META.{layer}.sub names no dataset after its geography: {sub!r}"
        assert geography.lower() == RULED_LABEL[layer].lower(), (
            f"{layer}: the geography phrase is {geography!r}, not the ruled {RULED_LABEL[layer]!r}"
        )
        assert dataset, f"{layer}: the dataset half is empty: {sub!r}"



# ---------------------------------------------------------------------------------------------
# A34 / GATE 3 (Task ONE-VOCABULARY, 2026-09-13; ruling D-C51, John: "WE MUST COMMUNICATE THE
# EXACT DESCRIPTION OF THE NUMBER SO USERS UNDERSTAND THE DIFFERENCES AND THEY ARE MEASURING
# DIFFERENT THINGS ... RIGHT NOW THEY ARE ALL LABELED THE SAME SO THE LOGIC WOULD BE THEY ARE
# SAME") — THE VOCABULARY IS THE SAME ON BOTH SIDES OF THE WIRE.
#
# The tests above pin the four MAP geographies. Two more words in the audit's closed list (§3.1)
# are the SERVER'S and the design has no way to invent them: the catchment phrase the API serves
# as `community_label` / the head of `income_note`, and the basis word `approximate` the API
# appends to it. The design composes both -- the docked panel joins its own " · approximate"
# to the served index (A33.1b/A33.1c.2), and its prose describes the catchment in its own words
# (A27.4, A34.7/A34.8) -- so a change to either on the server leaves the client saying something
# the server no longer says. Pinned here, in the shape the geography tests above established.
# ---------------------------------------------------------------------------------------------


def test_the_designs_catchment_prose_states_the_distance_the_api_serves() -> None:
    """`BAND_LABEL` carries a distance and the design's own prose repeats it in words.

    D-C39: the band is a straight-line buffer (spec §8) and the label says how far it reaches, so
    a change to the radius has to reach the sentences that describe it. The design never receives
    `BAND_LABEL` itself -- it renders whatever the payload carries -- but it DOES state the
    distance in its own copy, and that copy is what goes stale in silence."""
    miles = re.search(r"about (\d+) miles", BAND_LABEL)
    assert miles, f"BAND_LABEL no longer states a distance: {BAND_LABEL!r}"
    design = DESIGN.read_text(encoding="utf-8")
    stated = set(re.findall(r"about (\d+) miles", design))
    assert stated, "no sentence in the design describes the catchment at all"
    assert stated == {miles.group(1)}, (
        f"the design describes the catchment as {sorted(stated)} miles; the API serves "
        f"{miles.group(1)} ({BAND_LABEL!r})"
    )


def test_the_designs_approximate_qualifier_is_the_word_the_api_composes() -> None:
    """One basis word, one spelling, both sides.

    `serve.py` composes `income_note` as `<label> · <APPROXIMATE_BASIS>` and the docked panel
    composes its own sub-line as `<index> · <the same word>` (A33.1b). Two spellings of one
    basis is how the detail card and the panel come to qualify the same median differently, which
    is the collision (C1) the audit found and this ruling closes."""
    design = DESIGN.read_text(encoding="utf-8")
    joined = f" · {APPROXIMATE_BASIS}"
    assert joined in design, (
        f"the design no longer joins the qualifier the way the API does ({joined!r})"
    )
    assert APPROXIMATE_BASIS == APPROXIMATE_BASIS.lower(), (
        "the API's own qualifier is lower case; the design joins it after a middot and must not "
        "have to re-case it"
    )
