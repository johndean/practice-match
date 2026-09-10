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
    """The six Community Context fields, all nullable. A null means unavailable — either the
    dataset is not cleared, the value is suppressed, or there is no row for this metric. The
    label indicates which data band was used: either the place name or "Within 10 minutes of
    the practice" for the drive_10 fallback, or None if no figures are available."""
    pop: str | None
    growth: str | None
    income: str | None
    hh: str | None
    vets: int | None
    econ_k: int | None
    label: str | None


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

    The card has no caveat affordance, so a metric that is `suppressed` OR `approximate` is null
    in the card (different from the panel, which has the affordance and keeps showing approximate
    figures). This is deliberate — the contract says so."""
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


def community_rows(
    conn: Any,
    listing_ids: list[str],
    *,
    active: dict[str, str],
    registry: dict[str, dict[str, Any]],
) -> dict[str, CommunityRow]:
    """One batched query for all listings on a page — ONE query per page, never per-row.
    Returns a dict keyed by listing_id, one CommunityRow per listing id asked for.

    D-C32 (2026-09-10) — the fallback is decided on FIGURES, never on row presence. The row is
    built from the `place` band first; if all six figures came out None — no place rows at all,
    every place row suppressed, or every place row stamped with a dataset the VIN Foundation has
    not cleared — it is built again from `drive_10`, and the label then reads "Within 10 minutes
    of the practice" so the card says which area it describes. If that band is empty too the row
    is six nulls with no label, which is what puts the design's own "Community data unavailable"
    card on the screen.

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
            SELECT listing_id, metric_key, value_num, suppressed, source_dataset, vintage, band
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

    # For each listing, build the place band's row first and fall back to drive_10 on FIGURES
    # (B-2): a place band that yields nothing — no rows, all suppressed, or an uncleared dataset —
    # is indistinguishable from no place at all to the buyer, and the drive_10 band can describe
    # the market where the place band cannot.
    result: dict[str, CommunityRow] = {}
    acs5_prior_vintage = active.get("acs5_prior")

    for lid in listing_ids:
        figures = _figures(metrics_by_listing_band.get((lid, "place"), {}), reg, acs5_prior_vintage)
        label: str | None = None
        if all(v is None for v in figures.values()):
            drive_10 = _figures(metrics_by_listing_band.get((lid, "drive_10"), {}), reg, acs5_prior_vintage)
            if any(v is not None for v in drive_10.values()):
                figures = drive_10
                label = "Within 10 minutes of the practice"

        result[lid] = {
            "pop": figures["pop"],
            "growth": figures["growth"],
            "income": figures["income"],
            "hh": figures["hh"],
            "vets": figures["vets"],
            "econ_k": figures["econ_k"],
            # B-3: `label` is None whenever the figures came from the listing's own community.
            # The design already names that community from the listing's own `area`, so the label
            # exists solely to OVERRIDE that wording when the figures did not come from it.
            "label": label,
        }

    return result
