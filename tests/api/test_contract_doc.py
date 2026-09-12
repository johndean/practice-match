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
    # Read with the line breaks flattened (minor, whole-branch review 2026-09-11). This
    # assertion is NEGATIVE and its needle carried a hard newline, so re-wrapping the paragraph
    # satisfied it while the superseded rule was still in the document, word for word. A
    # whitespace-insensitive read is the only form a negative prose assertion can safely take.
    flat = re.sub(r"\s+", " ", text)
    assert "the row is built again from the `drive_10` band" not in flat

    # The two new fields, and what each one is for.
    assert "`growth_scope`" in text
    assert "`income_note`" in text
    # Growth's honest limit, stated rather than implied: it cannot vary below place-or-county
    # until the tract crosswalk lands, so the card names the geography instead of claiming one.
    assert "population_growth_pct" in text
    assert "crosswalk" in text
    # The geoid lookup that replaces the sentence above, named by its own columns.
    assert "place_geoid" in text and "geo_area.name" in text


def test_contract_doc_names_every_community_field_the_listing_serialiser_emits() -> None:
    """Minor, whole-branch review 2026-09-11: nothing compared the document's field names to the
    producer's own keys, so a tenth community field could reach `GET /api/listings` undocumented
    and Sub-project 2 would never learn of it.

    The keys are MEASURED, never typed here: `serialise` is called twice over one row — once with
    no community and once with every `CommunityRow` field filled — and the keys whose value moves
    between the two answers ARE the community-derived part of the contract, by construction. Both
    the field list (`CommunityRow`'s annotations) and the mapping (`label` -> `community_label`)
    come from the code.

    SCOPED to the community contract on purpose. This document is the market-data API's contract,
    not the full listing schema; `serialise`'s other forty-odd keys (disclosure, photographs, the
    seller's own columns) belong to Sub-project 2's own contract and are not claimed here."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.api.listings import serialise
    from app.census.serve import CommunityRow

    row = {
        "id": uuid4(), "slug": "s", "name": "N", "name_disclosed": True, "location_disclosed": True,
        "rev_disclosed": True, "market": "Orlando, FL", "area": "Orlando", "type": "Small animal",
        "city": "Orlando", "state": "FL", "street": "1 Main St", "zip": "32819", "phone": None,
        "hours": None, "price": 1, "rev": 1, "docs": 1, "rooms": 1, "sqft": 1, "bldg": "Included",
        "est": 2001, "listed_at": datetime(2026, 9, 1, tzinfo=UTC), "status": "published",
        "note": None, "staff": None, "services": None, "facility": None, "ownership": None,
        "lat": None, "lng": None, "photos": [], "photo_captions": [], "asset_captions": {},
        # GEO-WIRE (4): `_SELECT`'s own `practice_location.geo_precision`. It is a LISTING column,
        # not a `CommunityRow` field, so it is constant across the two calls below and the
        # measurement never claims it — which is exactly the distinction this test is drawing.
        "geo_precision": None,
    }
    now = datetime(2026, 9, 6, tzinfo=UTC)
    fields = tuple(CommunityRow.__annotations__)
    assert fields, "CommunityRow declares no fields — the measurement below would assert nothing"

    absent = serialise(row, now)
    present = serialise(row, now, community={k: f"<{k}>" for k in fields})
    emitted = sorted(k for k in present if present[k] != absent.get(k))
    assert len(emitted) == len(fields), (
        f"`serialise` passes through {len(emitted)} of CommunityRow's {len(fields)} fields "
        f"({emitted}); one of them is dropped or renamed onto a key that was already set"
    )

    text = DOC.read_text(encoding="utf-8")
    missing = [k for k in emitted if not re.search(rf"`{re.escape(k)}`", text)]
    assert missing == [], (
        "docs/integrations/market-data-api.md names no field for these keys of "
        f"GET /api/listings: {', '.join(missing)}"
    )


def test_contract_doc_states_the_boundary_caps_and_geographies_the_code_enforces() -> None:
    """A hand-maintained number in a document is a defect waiting to happen: every figure below is
    read off `app.api.market` rather than typed here, so the document cannot drift from the caps
    the route really applies (plan Global Constraint (i))."""
    from app.api import market

    text = DOC.read_text(encoding="utf-8")
    assert f"`MAX_BBOX_DEG = {market.MAX_BBOX_DEG}`" in text
    assert f"`MAX_FEATURES = {market.MAX_FEATURES}`" in text
    assert f"`MAX_BODY_BYTES = {market.MAX_BODY_BYTES:_}`" in text
    assert f"`BOUNDARY_TTL = {market.BOUNDARY_TTL}`" in text
    for layer, shading in market.SHADING.items():
        assert f'"{layer}"' in text or f"`{layer}`" in text, layer
        assert f'"summary_level": "{shading["summary_level"]}"' in text, layer
        assert shading["label"] in text, layer
    # The two properties §6 turns on, by name: a document that stops naming them is a contract
    # Task 10 can implement the no-data swatch wrongly against.
    for prop in ("suppress_reason", "band_ambiguous", "values_without_geometry"):
        assert f"`{prop}`" in text, prop
    # /api/layers' own sample must show the new member on every layer, shaded or not: an
    # integration contract whose example payload is missing a field is one Task 10 codes without.
    sample = text.split("## `GET /api/layers`", 1)[1].split("```", 2)[1]
    assert sample.count('"shading"') == 9, "every layer in the /api/layers sample must show the member"
    assert sample.count('"shading": null') == 9 - len(market.SHADING), (
        "every layer that does NOT shade must show shading: null"
    )
    # The one exception spec §6 grants, written down where an integrator will read it: a ZIP area
    # may be used where it IS the dataset's authoritative geography, and the answer must say so.
    if any(v["summary_level"] == "860" for v in market.SHADING.values()):
        assert "authoritative geography" in text
        assert "ZIP Code Business Patterns" in text
    assert '`shading` is the geography the MAP paints' in text


#: The adapter, as TEXT. `frontend/src/market/boundaries.ts` is TypeScript and this is pytest, so
#: it is read the way `frontend/src/listings/step-fields.json` is read — no parser, no build step,
#: no Node in the backend gate. A regex over source is a weak reader, so the assertions below are
#: written to fail LOUDLY if it reads nothing at all rather than to pass vacuously.
ADAPTER = Path(__file__).resolve().parents[2] / "frontend" / "src" / "market" / "boundaries.ts"


def test_the_refusal_codes_the_boundary_adapter_branches_on_are_pinned_to_the_route() -> None:
    """The retry ladder is a cross-language contract, and nothing pinned it.

    `boundaries.ts` branches on the literals `'AREA_TOO_LARGE'` and `'BBOX_TOO_LARGE'` to decide
    whether a refusal is one a smaller box can fix, one the whole-metro request can fix, or one
    that is final. `app/api/market.py` produces those strings and the contract doc restates them.
    Rename one on the server and New York goes blank with every gate in this repository green —
    the drift class this project has been bitten by repeatedly, which is why the caps beside this
    are pinned off the module rather than typed into the document.

    So: every code the CLIENT compares against `e.code` must (a) be raised by the `boundaries`
    route itself, and (b) be named in the contract doc. And the set is pinned exactly, so a THIRD
    code the client starts branching on has to be brought here rather than silently trusted.
    """
    import inspect

    from app.api import market

    adapter = ADAPTER.read_text(encoding="utf-8")
    # Every `e.code === 'X'` / `e.code !== 'X'` in the file, in either order of operands.
    branched = set(re.findall(r"e\.code\s*[!=]==\s*'([A-Z_]+)'", adapter))
    branched |= set(re.findall(r"'([A-Z_]+)'\s*[!=]==\s*e\.code", adapter))
    assert branched == {"AREA_TOO_LARGE", "BBOX_TOO_LARGE"}, (
        f"{ADAPTER.name} branches on {sorted(branched)}; the route, the contract doc and this pin "
        "must all be widened together when the client learns a new code"
    )

    route = inspect.getsource(market.boundaries)
    doc = DOC.read_text(encoding="utf-8")
    bounds = doc.split("**Bounds.**", 1)[1].split("**Licence.**", 1)[0]
    for code in sorted(branched):
        assert f'_error("{code}"' in route, (
            f"{ADAPTER.name} branches on {code!r} but `app.api.market.boundaries` never raises it"
        )
        assert code in bounds, (
            f"{ADAPTER.name} branches on {code!r} but the contract doc's Bounds section never names it"
        )


def test_the_metro_catalogue_name_join_is_the_same_field_on_both_sides() -> None:
    """The client resolves a metro by NAME, and nothing pinned what that name is.

    `boundaries.ts` joins `rows.find((m) => m.name === marketName)` where `marketName` is the
    design's own `P[i].market`; `markets()` serves `l.market AS name` precisely so that no name
    heuristic stands between the dropdown and the geoid (Task CK deleted `short_market_name` for
    exactly that reason). The two halves are in different languages and nothing connected them:
    alias that column to anything else — `cbsa_name`, `label`, the CBSA's official title — and
    every metro silently fails to resolve, with every gate in this repository green.

    Read as TEXT, the `step-fields.json` posture, like the refusal-code pin above it.
    """
    import inspect

    from app.api import market

    adapter = ADAPTER.read_text(encoding="utf-8")
    join = re.search(r"rows\.find\(\((\w+)\)\s*=>\s*\1\.(\w+)\s*===\s*marketName\)", adapter)
    assert join is not None, (
        f"{ADAPTER.name} no longer resolves a metro with `rows.find(m => m.<field> === marketName)`; "
        "this pin reads that join and must be rewritten with it"
    )
    field = join.group(2)
    assert field == "name", f"{ADAPTER.name} joins the metro catalogue on {field!r}"

    source = inspect.getsource(market.markets)
    assert f"l.market AS {field}" in source, (
        f"{ADAPTER.name} joins on {field!r} but `app.api.market.markets` does not select "
        f"`l.market AS {field}` — the dropdown key and the served name are no longer the same string"
    )


def test_contract_doc_states_when_a_listing_gets_its_geography() -> None:
    """Task GEO-WIRE. This document described the endpoints and said nothing about WHEN the
    geography behind them is resolved, so a reader could not tell an empty Community Context card
    ("this listing has not been geocoded yet") from a full one that is simply out of date. The
    trigger, its dedupe window, the event that invalidates a resolved geography and the precision a
    wizard-built address can actually reach are all part of the contract Sub-project 2 builds
    against, not implementation detail."""
    # Read with the line breaks flattened, the whole file's own convention for a prose needle
    # (`test_contract_doc_states_the_per_figure_geography_rule`): every sentence below is wrapped
    # in the document, so a literal read would pin the wrapping rather than the words.
    flat = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))

    # The trigger: the reviewer's own decision route, and the task it enqueues by name.
    assert "/api/admin/listings/{listing_id}/decide" in flat
    assert "`census.geocode_listing`" in flat
    # The seller's own door onto the market enqueues it too.
    assert "/api/seller/listings/{listing_id}/status" in flat
    # The event that invalidates a resolved geography, and what happens to it.
    assert "`practice_location`" in flat
    assert "a changed `city` or `zip`" in flat
    # The operator path the demo rows still take -- unchanged by this, and not the product's.
    assert "`scripts/census_load.py geocode`" in flat
    # Review minor 3: BOTH doors to a re-resolve are named, not just `--force`.
    assert "`--force` re-resolves one that has, and `--listing <id>`" in flat
    # The precision a wizard-built address can reach, stated rather than implied.
    assert "`geo_precision`" in flat
    assert "the wizard collects a city and a ZIP and no street" in flat


def test_contract_doc_states_that_a_non_rooftop_point_is_served_its_place_band() -> None:
    """Controller ruling, GEO-WIRE fix round 1. The catchment band is a ring around
    `practice_location.point` and `community_label` says it is "within about 5 miles of the
    practice" — true only of a rooftop match. A wizard-built listing resolves at `zcta`, so
    `community_rows` serves it the `place` band instead.

    Pinned because it changes WHICH GEOGRAPHY a figure describes, which is the one thing this
    document exists to let Sub-project 2 reason about: a reader who believes the D-C38 table
    unconditionally will caption a city figure as a ring on every listing a seller creates."""
    flat = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))

    # The rule, and the column the condition is read from.
    assert "only when `geo_precision` is `\"rooftop\"`" in flat
    assert "served the `place` band" in flat
    # ...and that it invents no copy: the place band is the path the design already renders.
    assert "no `community_label`" in flat
    # The reason, stated rather than implied.
    assert "a ZIP-code centroid" in flat
    # A listing that has never been geocoded is NOT swept up by it.
    assert "a listing with no `practice_location` row is unaffected" in flat
    # Fix round 2: the unincorporated case, which the first telling of this rule glossed as "a
    # true city figure" for every non-rooftop listing. A ZIP centroid inside no place has no city
    # band to be served, and the document has to say which of the two a reader is looking at.
    assert "where the ZIP centroid lies in one" in flat
    assert "the county carries growth and payroll and the area figures are unavailable" in flat
