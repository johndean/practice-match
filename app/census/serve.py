"""Task B7: serve the six Community Context figures (pop, growth, income, hh, vets, econ_k)
to the listing serialiser, through one batched query per page with the same gate logic market.py
uses to decide what a buyer may see.

Functions `_active`, `_registry`, and `_extra_cleared` are moved from `app.api.market` to a
single source of truth so both `market.py`'s panel and the listing card read the same rules.
"""
from __future__ import annotations

from typing import Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncConnection


class CommunityRow(TypedDict):
    """The six Community Context figures and the three fields that say where each one comes from.
    Every field is nullable, and a null means unavailable — the dataset is not cleared, the value
    is suppressed, or there is no row for this metric (D-C31: never `0`, never `""`).

    D-C38 (John, 2026-09-11) — each figure is served at its OWN honest geography and the card
    names it, per tile:

      * `label` names the area the three AREA figures (`pop`, `hh`, `income`) and the off-card
        `vets` describe. `BAND_LABEL` when they came from the catchment band; None when they came
        from the listing's own Census place, which is the wording the design already uses.
      * `growth_scope` names the geography the GROWTH figure was measured at — "Dallas",
        "Orange County" — because growth exists at no finer geography than place-or-county until
        the 2010->2020 tract crosswalk is loaded (D12, a registered Phase C deferral), and a
        city figure under a catchment caption is the defect D-C38 exists to remove.
      * `income_note` replaces the median-income tile's sub-line when that median is an
        approximation rather than a published Census figure.

    `econ_k` is county everywhere and always (`materialize.py` writes `ctx.cbp` into all three
    bands), and the card does not render it — it feeds the Browse Payroll layer."""
    pop: str | None
    growth: str | None
    income: str | None
    hh: str | None
    vets: int | None
    econ_k: int | None
    label: str | None
    growth_scope: str | None
    income_note: str | None


async def _active(conn: AsyncConnection) -> dict[str, str]:
    """The currently-active vintage for each dataset key. Moved from market.py."""
    from sqlalchemy import text

    rows = (await conn.execute(text("SELECT dataset_key, vintage FROM active_vintage"))).mappings().all()
    return {r["dataset_key"]: r["vintage"] for r in rows}


async def _registry(conn: AsyncConnection) -> dict[str, dict[str, Any]]:
    """The dataset registry rows, one per dataset key. Moved from market.py."""
    from sqlalchemy import text

    rows = (await conn.execute(text("SELECT dataset_key, attribution_text, vintage, license_status, notes FROM dataset_registry"))).mappings().all()
    return {r["dataset_key"]: dict(r) for r in rows}


def _cleared(reg: dict[str, dict[str, Any]], dataset_key: str) -> bool:
    """Whether `dataset_key` is currently licence-cleared. Moved from market.py."""
    return bool(reg[dataset_key]["license_status"] == "cleared")


def _extra_cleared(reg: dict[str, dict[str, Any]], metric_key: str, source_dataset: str) -> bool:
    """A-C23 (1): a row's `source_dataset` is the ONE dataset `market_metric` can stamp it with,
    but three metrics fold in a SECOND dataset the generic gate above cannot see. Moved from market.py.

    A `suppressed` metric is null in the card, here and in the panel. An APPROXIMATE one is not:
    this function's docstring used to claim that "a metric that is `suppressed` OR `approximate`
    is null in the card", and nothing in this module has ever read `is_derived`, so the claim was
    false for every approximate figure the pipeline has produced — the Orlando listing's $69,780
    among them. D-C38 makes the card do what the contract actually asks
    (`docs/integrations/market-data-api.md`: an approximate median "renders 'approximate' beside
    the value") rather than what this docstring asserted: the figure is SHOWN, with `income_note`
    saying what it is. Nulling it would have been the worse answer anyway — a catchment median can
    never be suppressed (`materialize.py`), so the rule as written would have blanked the median
    on every listing D-C38 serves from a ring."""
    if metric_key == "population_growth_pct":
        return _cleared(reg, "acs5_prior")
    if metric_key == "vets_per_10k_households":
        return _cleared(reg, "acs5")
    if metric_key == "establishments" and source_dataset == "cbp":
        return _cleared(reg, "acs5")
    return True


def _figures(
    metrics: dict[str, Any],
    reg: dict[str, dict[str, Any]],
    acs5_prior_vintage: str | None,
) -> dict[str, Any]:
    """The six Community Context figures for ONE band, formatted as the design spells them.

    Every figure is independent: a suppressed population leaves the households count standing,
    and a dataset that is not licence-cleared nulls only what it stamps. A figure that is absent
    is None — never zero, never an empty string (D-C31: "a missing figure is omitted, never
    zeroed"), because `null` is the only value the frontend's own guards read as absence."""
    figures: dict[str, Any] = {
        "pop": None, "growth": None, "income": None, "hh": None, "vets": None, "econ_k": None,
    }

    # Population
    if "population" in metrics:
        m = metrics["population"]
        if not m["suppressed"] and _cleared(reg, m["source_dataset"]):
            figures["pop"] = f"{round(float(m['value_num'])):,}"

    # Households
    if "households" in metrics:
        m = metrics["households"]
        if not m["suppressed"] and _cleared(reg, m["source_dataset"]):
            figures["hh"] = f"{round(float(m['value_num'])):,} households"

    # Median household income
    if "median_hh_income" in metrics:
        m = metrics["median_hh_income"]
        if not m["suppressed"] and _cleared(reg, m["source_dataset"]):
            figures["income"] = f"${round(float(m['value_num'])):,}"

    # Population growth (requires acs5_prior cleared, and an active acs5_prior vintage to name)
    if "population_growth_pct" in metrics:
        m = metrics["population_growth_pct"]
        if (
            not m["suppressed"]
            and _cleared(reg, m["source_dataset"])
            and _extra_cleared(reg, "population_growth_pct", m["source_dataset"])
            and acs5_prior_vintage
        ):
            prior_end_year = acs5_prior_vintage[-4:]  # Last 4 characters
            figures["growth"] = f"{float(m['value_num']):+.1f}% since {prior_end_year}"

    # Establishments (vets)
    if "establishments" in metrics:
        m = metrics["establishments"]
        if not m["suppressed"] and _cleared(reg, m["source_dataset"]) and _extra_cleared(reg, "establishments", m["source_dataset"]):
            figures["vets"] = int(float(m["value_num"]))

    # Payroll per establishment (econ_k) - in thousands. The column is historically named
    # `revenue_per_establishment`; the figure is payroll, not revenue (amendment A-C29).
    if "revenue_per_establishment" in metrics:
        m = metrics["revenue_per_establishment"]
        if not m["suppressed"] and _cleared(reg, m["source_dataset"]):
            figures["econ_k"] = round(float(m["value_num"]) / 1000)

    return figures


# D-C39 (John, 2026-09-11) — the ring is described by DISTANCE, not by time. The band is an 8 km
# straight-line buffer from the practice point (spec §8, "straight-line buffers of 8 km (≈10 min)
# and 16 km (≈20 min) … labeled as approximations"), not a routed drive time, and spec §15 still
# lists true drive-time isochrones as OPEN for V1. "About 5 miles" is what the geometry supports;
# "10 minutes" was a reading of it. The two sentences in the app that said otherwise
# (`App.vue`'s Insights heading and its footnote) are corrected in the same release.
BAND_LABEL = "Within about 5 miles of the practice"

# The area figures move as ONE GROUP (D-C38). `label` describes all of them at once, so a group
# drawn half from the ring and half from the city would put a city figure under a ring caption —
# the very defect D-C38 exists to remove. A figure the chosen band does not have is null, which is
# what the design's own guards read as absence; it is never backfilled from the other band.
_AREA_KEYS = ("pop", "hh", "income", "vets")

_SCOPE_NAME_SQL = """
    SELECT pl.listing_id, 'place', g.name
      FROM practice_location pl
      JOIN geo_area g ON g.geo_id = pl.place_geoid AND g.summary_level = '160' AND g.vintage = %s
     WHERE pl.listing_id = ANY(%s::uuid[])
    UNION ALL
    SELECT pl.listing_id, 'county', g.name
      FROM practice_location pl
      JOIN geo_area g ON g.geo_id = pl.county_geoid AND g.summary_level = '050' AND g.vintage = %s
     WHERE pl.listing_id = ANY(%s::uuid[])
"""


def _scope_names(conn: Any, listing_ids: list[str], geo_vintage: str | None) -> dict[tuple[str, str], str]:
    """Each listing's place and county NAME, keyed by `(listing_id, geo_level)` — ONE batched
    query for the whole page, never one per row.

    D-C38 supersedes this module's own "There is no geoid lookup and none is wanted": the Growth
    tile has to name the geography its figure was measured at, and that name is a join from
    `practice_location.place_geoid` / `county_geoid` (migrations/061) to `geo_area.name`.

    TWO branches of a UNION rather than one join with an OR, because each branch then reads
    `geo_area`'s own primary key (geo_id, summary_level, vintage) straight down; an OR across two
    different columns gives the planner nothing to descend. `geo_vintage` is the active `tiger_cb`
    edition — the same boundary vintage `materialize.py` builds catchments against — and a
    database with no active `tiger_cb` matches no row and names nothing, which is the same answer
    as a listing that was never geocoded.

    The two summary levels are LITERALS in the SQL, so the tag beside each name ('place',
    'county') is the level it was actually read at, not a re-derivation of it."""
    names: dict[tuple[str, str], str] = {}
    with conn.cursor() as cur:
        cur.execute(_SCOPE_NAME_SQL, (geo_vintage, listing_ids, geo_vintage, listing_ids))
        for lid, level, name in cur.fetchall():
            names[(str(lid), level)] = name
    return names


def community_rows(
    conn: Any,
    listing_ids: list[str],
    *,
    active: dict[str, str],
    registry: dict[str, dict[str, Any]],
) -> dict[str, CommunityRow]:
    """Two batched queries for a whole page — never one per row, whatever the page holds.

    D-C38 (2026-09-11) — PER-FIGURE GEOGRAPHY. Each figure is served at its own honest geography
    and the row names it. This supersedes D-C32's whole-row rule ("built from the `place` band
    first; if all six figures came out None it is built again from `drive_10`"), which was written
    for one condition — the Orlando specialist centre in unincorporated Orange County, which has
    no Census place at all — and was never asked what it does to a listing INSIDE a large city.
    What it did: all twelve Dallas listings sit in one Census place, so all twelve were served the
    City of Dallas — one median household income under twelve different neighbourhood headings —
    while their own catchment figures sat materialised and unreachable.

    The rule now:

      * The three AREA figures (`pop`, `hh`, `income`) and the off-card `vets` come from the
        catchment band, with `place` as the fallback, AS ONE GROUP — see `_AREA_KEYS`. `label` is
        set whenever that group came from the catchment.
      * `growth` and `econ_k` are taken from whichever band carries them, because neither can vary
        by band at all: `materialize.py` computes growth ONCE per listing outside the band loop
        and writes that one value into all three bands (D12), and always writes the county CBP
        row for payroll. `growth_scope` names growth's own geography so the tile stops implying it
        describes the ring beside it.
      * `drive_20` is still never a fallback: a wider area served under a narrower heading would
        be a reading the data does not support.

    What D-C32 ruled and this keeps: the card SAYS which area it describes, so a buyer is never
    shown a catchment disguised as a named city — a rule that governed one listing of 29 and now
    governs nearly all of them. And where NEITHER band has figures the row is all nulls with no
    label, which is what puts the design's own "Community data unavailable" card on the screen; a
    per-figure rule makes that rarer, and must not make it unreachable.

    Parameters:
        conn: sync psycopg2 database connection
        listing_ids: the listing ids on this page
        active: dict of active vintages by dataset_key
        registry: dict of dataset registry entries by dataset_key

    Returns:
        dict mapping listing_id (str) to CommunityRow, one entry per requested id
    """
    if not listing_ids:
        return {}

    # Use the passed-in registry
    reg = registry

    # Fetch all market_metric rows for these listings, both place and drive_10 bands
    with conn.cursor() as cur:
        cur.execute("""
            SELECT listing_id, metric_key, value_num, suppressed, source_dataset, vintage, band, is_derived, inputs
            FROM market_metric
            WHERE listing_id = ANY(%s::uuid[]) AND band = ANY(%s::text[])
            ORDER BY listing_id, band
        """, (listing_ids, ["place", "drive_10"]))
        raw_rows = cur.fetchall()

    # Get column names from cursor description
    if raw_rows:
        columns = [d[0] for d in cur.description]
        rows = [dict(zip(columns, row)) for row in raw_rows]
    else:
        rows = []

    # Build the metrics by (listing_id, band)
    metrics_by_listing_band: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        lid = str(row["listing_id"])
        band = row["band"]
        key = (lid, band)
        if key not in metrics_by_listing_band:
            metrics_by_listing_band[key] = {}
        metrics_by_listing_band[key][row["metric_key"]] = row

    result: dict[str, CommunityRow] = {}
    acs5_prior_vintage = active.get("acs5_prior")
    names = _scope_names(conn, listing_ids, active.get("tiger_cb"))

    for lid in listing_ids:
        place_metrics = metrics_by_listing_band.get((lid, "place"), {})
        drive_metrics = metrics_by_listing_band.get((lid, "drive_10"), {})
        place = _figures(place_metrics, reg, acs5_prior_vintage)
        drive = _figures(drive_metrics, reg, acs5_prior_vintage)

        # The area group, at the finest geography that actually has it. Decided on FIGURES, never
        # on row presence (B-2, and still true): a place band that yields nothing — no rows, all
        # suppressed, or an uncleared dataset — is indistinguishable from no place at all to the
        # buyer, and the catchment can describe the market where the place cannot.
        from_catchment = any(drive[k] is not None for k in _AREA_KEYS)
        area = drive if from_catchment else place
        area_metrics = drive_metrics if from_catchment else place_metrics

        # B-3, widened by D-C38: `label` is None whenever the area figures came from the listing's
        # own community. The design already names that community from the listing's own `area`, so
        # the label exists solely to OVERRIDE that wording when the figures did not come from it.
        label = BAND_LABEL if from_catchment else None

        # An approximate median is SHOWN with the word beside it, never blanked — a catchment
        # median is a household-weighted average of the tract medians inside the ring rather than
        # a published Census figure, which is exactly what `is_derived` records.
        income_note = None
        if label is not None and area["income"] is not None and area_metrics["median_hh_income"]["is_derived"]:
            income_note = f"{label} · approximate"

        # Growth and payroll are byte-identical in every band by construction, so "whichever band
        # carries it" is a choice between two copies of one number — but the GEOGRAPHY it was
        # measured at is its own, and that is what the card has to name.
        growth = drive["growth"] if drive["growth"] is not None else place["growth"]
        econ_k = drive["econ_k"] if drive["econ_k"] is not None else place["econ_k"]

        growth_scope = None
        if growth is not None:
            source = drive_metrics if drive["growth"] is not None else place_metrics
            level = (source["population_growth_pct"]["inputs"] or {}).get("geo_level")
            name = names.get((lid, level))
            if name is not None:
                # TIGER's place `NAME` drops the legal descriptor ("Dallas"); its county
                # `NAMELSAD` keeps it ("Orange County"). D-C38's option text read "City of
                # Dallas", and composing that prefix was the first implementation — but the
                # descriptor is not ours to invent: `app/census/tiger.py:102` loads level 160
                # from `NAME`, so a census-designated place comes through as "Florin" and the
                # composed string would read "City of Florin", which Florin is not. The
                # Sacramento listings resolve to exactly that.
                #
                # Controller ruling on the implementer's own concern (2026-09-11): use the name
                # TIGER gives and prefix nothing. "Dallas · since 2018" and "Florin · since 2018"
                # both say where the figure was measured, which is what John ruled, without
                # asserting a legal status the data does not carry. Loading `NAMELSAD` for level
                # 160 would give the true descriptor and is the better long answer; it needs a
                # TIGER re-ingest and is not this change.
                growth_scope = name

        result[lid] = {
            "pop": area["pop"],
            "growth": growth,
            "income": area["income"],
            "hh": area["hh"],
            "vets": area["vets"],
            "econ_k": econ_k,
            "label": label,
            "growth_scope": growth_scope,
            "income_note": income_note,
        }

    return result
