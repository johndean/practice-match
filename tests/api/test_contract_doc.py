"""Task B6: the integration contract for Sub-project 2 and the admin Data Sources tab
(`docs/integrations/market-data-api.md`) must name every route the application actually mounts and
carry the fixture field names `logic.js` reads, so the document and the routers cannot drift apart
silently.

Plan Task B6's own numbered pre-flight note (A-C0 paragraph 12 / A-C15 (7)): "B6 cannot go RED
before B5 exists (its drift test imports both routers) ... the import is deferred inside the test
functions." The brief this test is adapted from imported `app.api.market` and
`app.api.admin_data_sources` at MODULE scope instead, which the ruling above forbids -- both
imports below are therefore inside the test functions, not at the top of this file, even though
B5 has since landed and the module-scope form would happen to work today. The ruling is about how
this file is written, not about whether the import currently succeeds.

The brief's own illustrative fixture-mapping table also named seven fields (`pop`, `hh`, `income`,
`growth`, `pets`, `econ`, `vets`) but only ever wrote five of them as their OWN backtick-quoted
token -- `pop` and `hh` appeared only inside longer code spans (`` `pop, hh, income, growth, pets,
econ, vets` ``, `` `P[].pop/growth/income/hh` ``), which `` `{field}` `` cannot match as a
substring bounded by backticks on both sides. The document below gives all seven their own
inline-code mention."""
from __future__ import annotations

import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "integrations" / "market-data-api.md"


def _paths(router):
    return sorted({r.path for r in router.routes if getattr(r, "path", None)})


def test_contract_doc_names_every_market_and_admin_route():
    from app.api import admin_data_sources, market

    text = DOC.read_text(encoding="utf-8")
    for path in _paths(market.router) + _paths(admin_data_sources.router):
        assert path in text, path


def test_contract_doc_carries_the_fixture_field_names_and_the_vintage_statement():
    text = DOC.read_text(encoding="utf-8")
    for field in ("pop", "hh", "income", "growth", "pets", "econ", "vets"):
        assert re.search(rf"`{field}`", text), field
    assert "ACS 2014\u20132018 \u2192 2019\u20132023" in text


def test_contract_doc_states_the_band_fallback_and_the_community_label() -> None:
    """Task B10 / D-C32, widened by D-C38 / D-C39 (2026-09-11). The document said the serialiser
    reads "at the `place` band", which the band fallback makes false, and `community_label`
    appeared nowhere. Both are pinned here so the sentence cannot drift back: this is the contract
    Sub-project 2 builds its card heading from."""
    text = DOC.read_text(encoding="utf-8")

    # The sentence that was wrong, in every spelling it could come back as.
    assert "from `market_metric` at the `place` band" not in text
    assert "`place` band by default" not in text

    # The field, its two values, and the rule the frontend has to honour.
    assert "`community_label`" in text
    assert '"Within about 5 miles of the practice"' in text
    assert "Which band a listing's figures come from" in text
    # D-C39: the ring is described by DISTANCE, not by time. The band is an 8 km straight-line
    # buffer, not a routed drive time, so the old wording may not come back.
    assert '"Within 10 minutes of the practice"' not in text
    # The choice is decided on figures, never on row presence -- the whole point of B-2.
    assert "decided on FIGURES, not on row presence" in text
    # `drive_20` is explicitly NOT a fallback.
    assert "`drive_20` is never a fallback" in text
    # D-C31 at the payload boundary.
    assert "never `0`, never `\"\"`" in text


def test_contract_doc_states_the_per_figure_geography_rule() -> None:
    """D-C38 (John, 2026-09-11). The document's whole-row rule -- "the row is built from the
    `place` band first; if all six figures came out null it is built again from `drive_10`" -- is
    superseded by a PER-FIGURE one, and so is its "There is no geoid lookup and none is wanted".
    Both are pinned here in the spelling they would come back as, because an integration contract
    that still describes the old rule is how Sub-project 2 builds the wrong card."""
    text = DOC.read_text(encoding="utf-8")

    # The two superseded rules, gone AS RULES. The retired geoid sentence is still QUOTED in the
    # paragraph that retires it -- a reader who searches for it should find out why it went -- so
    # the assertion is on the claim it used to make, which is its own continuation.
    assert "and none is wanted: the label exists" not in text
    assert "which D-C38 supersedes" in text
    assert "the row is built again from the\n`drive_10` band" not in text

    # The two new fields, and what each one is for.
    assert "`growth_scope`" in text
    assert "`income_note`" in text
    # Growth's honest limit, stated rather than implied: it cannot vary below place-or-county
    # until the tract crosswalk lands, so the card names the geography instead of claiming one.
    assert "population_growth_pct" in text
    assert "crosswalk" in text
    # The geoid lookup that replaces the sentence above, named by its own columns.
    assert "place_geoid" in text and "geo_area.name" in text
