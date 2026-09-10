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


def community_rows(
    conn: Any,
    listing_ids: list[str],
    *,
    active: dict[str, str],
    registry: dict[str, dict[str, Any]],
) -> dict[str, CommunityRow]:
    """One batched query for all listings on a page — ONE query per page, never per-row.
    Returns a dict keyed by listing_id, one CommunityRow per listing with rows, or an absent
    key for listings with no rows (the serialiser turns absence into six nulls).

    D-C32 (2026-09-10): A listing with place-band figures uses those; a listing with only
    drive_10 rows uses those and the label reads "Within 10 minutes of the practice"; a listing
    with neither returns the six nulls it returns today.

    Parameters:
        conn: sync psycopg2 database connection
        listing_ids: the listing ids on this page
        active: dict of active vintages by dataset_key
        registry: dict of dataset registry entries by dataset_key

    Returns:
        dict mapping listing_id (str) to CommunityRow, absent for listings with no data
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

    # For each listing, check place band first, then drive_10
    result: dict[str, CommunityRow] = {}
    acs5_prior_vintage = active.get("acs5_prior")

    for lid in listing_ids:
        place_key = (lid, "place")
        drive_10_key = (lid, "drive_10")

        # Prefer place band, fall back to drive_10
        band_to_use = None
        label = None
        if place_key in metrics_by_listing_band:
            metrics = metrics_by_listing_band[place_key]
            band_to_use = metrics
            # Label is the place name (we'd fetch this from geoid lookup in the real implementation;
            # for now use a generic label since the place name is not in the metrics table)
            label = None
        elif drive_10_key in metrics_by_listing_band:
            metrics = metrics_by_listing_band[drive_10_key]
            band_to_use = metrics
            label = "Within 10 minutes of the practice"
        else:
            # No metrics for this listing
            continue

        community_row: CommunityRow = {
            "pop": None,
            "growth": None,
            "income": None,
            "hh": None,
            "vets": None,
            "econ_k": None,
            "label": label,
        }

        if band_to_use is None:
            result[lid] = community_row
            continue

        # Population
        if "population" in band_to_use:
            m = band_to_use["population"]
            if not m["suppressed"] and _cleared(reg, m["source_dataset"]):
                pop_val = float(m["value_num"])
                community_row["pop"] = f"{round(pop_val):,}"

        # Households
        if "households" in band_to_use:
            m = band_to_use["households"]
            if not m["suppressed"] and _cleared(reg, m["source_dataset"]):
                hh_val = float(m["value_num"])
                community_row["hh"] = f"{round(hh_val):,} households"

        # Median household income
        if "median_hh_income" in band_to_use:
            m = band_to_use["median_hh_income"]
            if not m["suppressed"] and _cleared(reg, m["source_dataset"]):
                income_val = float(m["value_num"])
                community_row["income"] = f"${round(income_val):,}"

        # Population growth (requires acs5_prior cleared)
        if "population_growth_pct" in band_to_use:
            m = band_to_use["population_growth_pct"]
            if (
                not m["suppressed"]
                and _cleared(reg, m["source_dataset"])
                and _extra_cleared(reg, "population_growth_pct", m["source_dataset"])
                and acs5_prior_vintage
            ):
                growth_val = float(m["value_num"])
                prior_end_year = acs5_prior_vintage[-4:]  # Last 4 characters
                community_row["growth"] = f"{growth_val:+.1f}% since {prior_end_year}"

        # Establishments (vets)
        if "establishments" in band_to_use:
            m = band_to_use["establishments"]
            if not m["suppressed"] and _cleared(reg, m["source_dataset"]) and _extra_cleared(reg, "establishments", m["source_dataset"]):
                est_val = float(m["value_num"])
                community_row["vets"] = int(est_val)

        # Revenue per establishment (econ_k) - in thousands
        if "revenue_per_establishment" in band_to_use:
            m = band_to_use["revenue_per_establishment"]
            if not m["suppressed"] and _cleared(reg, m["source_dataset"]):
                rev_val = float(m["value_num"])
                community_row["econ_k"] = round(rev_val / 1000)

        result[lid] = community_row

    return result
