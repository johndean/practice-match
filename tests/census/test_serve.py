"""Task B7: community_rows serves the six formatted Community Context fields (population,
growth, income, households, vets, econ_k) to the listing serialiser, with one batched query
per page and the same gate logic market.py uses to decide what a buyer may see.
"""
from __future__ import annotations

import pytest

from app.census.serve import community_rows
from tests.census.listing_fixtures import make_listing


def _seed_active_and_registry(conn):
    """Helper to seed and fetch active vintages and registry."""
    with conn.cursor() as cur:
        # Seed active_vintage
        cur.execute(
            "DELETE FROM active_vintage WHERE dataset_key IN (%s, %s, %s, %s)",
            ("acs5", "acs5_prior", "zbp", "cbp"),
        )
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES "
            "(%s, %s, now(), %s), (%s, %s, now(), %s), (%s, %s, now(), %s), (%s, %s, now(), %s)",
            ("acs5", "2019–2023", "test", "acs5_prior", "2014–2018", "test", "zbp", "2022", "test", "cbp", "2022", "test"),
        )

        # Get active and registry
        cur.execute("SELECT dataset_key, vintage FROM active_vintage")
        active = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute("SELECT dataset_key, attribution_text, vintage, license_status, notes FROM dataset_registry")
        reg_cols = [d[0] for d in cur.description]
        registry = {r[0]: dict(zip(reg_cols, r)) for r in cur.fetchall()}

    return active, registry


def test_community_rows_formats_all_six_fields(conn):
    """All datasets cleared -> community_rows returns the six formatted values with exact strings."""
    listing_id = make_listing(conn, city="Round Rock", state="TX")

    with conn.cursor() as cur:
        # Set all datasets to cleared
        cur.execute(
            "UPDATE dataset_registry SET license_status = %s WHERE dataset_key IN (%s, %s, %s, %s)",
            ("cleared", "acs5", "acs5_prior", "zbp", "cbp"),
        )

        # Seed place_geoid for practice_location
        cur.execute(
            "UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s",
            ("06085", listing_id),
        )

        # Seed market_metric rows for all six fields
        cur.execute(
            "INSERT INTO market_metric "
            "(listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (
                listing_id, "place", "population", "2019–2023", 142300, "count", False, None, 500, False, None, "acs5",
                listing_id, "place", "households", "2019–2023", 55000, "count", False, None, 200, False, None, "acs5",
                listing_id, "place", "median_hh_income", "2019–2023", 85000, "dollars", False, None, 2000, False, None, "acs5",
                listing_id, "place", "population_growth_pct", "2019–2023", 5.5, "percent", True, None, 0.5, False, None, "acs5",
                listing_id, "place", "establishments", "2022", 12, "count", False, None, 1, False, None, "zbp",
                listing_id, "place", "revenue_per_establishment", "2022", 450000, "dollars", True, None, 50000, False, None, "cbp",
            ),
        )

    active, registry = _seed_active_and_registry(conn)
    rows = community_rows(conn, [listing_id], active=active, registry=registry)

    assert listing_id in rows
    row = rows[listing_id]
    assert row["pop"] == "142,300"
    assert row["hh"] == "55,000 households"
    assert row["income"] == "$85,000"
    assert row["growth"] == "+5.5% since 2018"
    assert row["vets"] == 12
    assert row["econ_k"] == 450


def test_community_rows_acs5_unresolved_nulls_most_fields(conn):
    """acs5 unresolved -> every figure null except establishments (zbp is cleared)."""
    listing_id = make_listing(conn)

    with conn.cursor() as cur:
        # First seed with all cleared so the gate passes
        cur.execute(
            "UPDATE dataset_registry SET license_status = %s WHERE dataset_key IN (%s, %s, %s, %s)",
            ("cleared", "acs5", "acs5_prior", "zbp", "cbp"),
        )

        # Seed place_geoid
        cur.execute(
            "UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s",
            ("06085", listing_id),
        )

        # Seed market_metric rows
        cur.execute(
            "INSERT INTO market_metric "
            "(listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (
                listing_id, "place", "population", "2019–2023", 142300, "count", False, None, 500, False, None, "acs5",
                listing_id, "place", "households", "2019–2023", 55000, "count", False, None, 200, False, None, "acs5",
                listing_id, "place", "median_hh_income", "2019–2023", 85000, "dollars", False, None, 2000, False, None, "acs5",
                listing_id, "place", "population_growth_pct", "2019–2023", 5.5, "percent", True, None, 0.5, False, None, "acs5",
                listing_id, "place", "establishments", "2022", 12, "count", False, None, 1, False, None, "zbp",
            ),
        )

        # Now change acs5 to unresolved to test the gate logic
        cur.execute(
            "UPDATE dataset_registry SET license_status = %s WHERE dataset_key = %s",
            ("unresolved", "acs5"),
        )

    active, registry = _seed_active_and_registry(conn)
    rows = community_rows(conn, [listing_id], active=active, registry=registry)

    row = rows[listing_id]
    assert row["pop"] is None
    assert row["hh"] is None
    assert row["income"] is None
    assert row["growth"] is None
    assert row["vets"] == 12  # zbp cleared, no acs5 requirement on zbp path
    assert row["econ_k"] is None


def test_community_rows_acs5_prior_not_cleared_nulls_growth(conn):
    """acs5_prior not cleared -> growth null, others present."""
    listing_id = make_listing(conn)

    with conn.cursor() as cur:
        # Set acs5 cleared, acs5_prior unresolved
        cur.execute(
            "UPDATE dataset_registry SET license_status = %s WHERE dataset_key IN (%s, %s)",
            ("cleared", "acs5", "zbp"),
        )
        cur.execute(
            "UPDATE dataset_registry SET license_status = %s WHERE dataset_key = %s",
            ("unresolved", "acs5_prior"),
        )

        # Seed place_geoid
        cur.execute(
            "UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s",
            ("06085", listing_id),
        )

        # Seed market_metric rows
        cur.execute(
            "INSERT INTO market_metric "
            "(listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (
                listing_id, "place", "population", "2019–2023", 142300, "count", False, None, 500, False, None, "acs5",
                listing_id, "place", "households", "2019–2023", 55000, "count", False, None, 200, False, None, "acs5",
                listing_id, "place", "median_hh_income", "2019–2023", 85000, "dollars", False, None, 2000, False, None, "acs5",
                listing_id, "place", "population_growth_pct", "2019–2023", 5.5, "percent", True, None, 0.5, False, None, "acs5",
            ),
        )

    active, registry = _seed_active_and_registry(conn)
    rows = community_rows(conn, [listing_id], active=active, registry=registry)

    row = rows[listing_id]
    assert row["pop"] == "142,300"
    assert row["hh"] == "55,000 households"
    assert row["income"] == "$85,000"
    assert row["growth"] is None  # acs5_prior not cleared
    assert row["vets"] is None
    assert row["econ_k"] is None


def test_community_rows_suppressed_population_nulls_only_pop(conn):
    """Suppressed population -> pop null AND hh present (independent)."""
    listing_id = make_listing(conn)

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE dataset_registry SET license_status = %s WHERE dataset_key IN (%s, %s, %s, %s)",
            ("cleared", "acs5", "acs5_prior", "zbp", "cbp"),
        )

        # Seed place_geoid
        cur.execute(
            "UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s",
            ("06085", listing_id),
        )

        # Seed market_metric rows, population suppressed
        cur.execute(
            "INSERT INTO market_metric "
            "(listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (
                listing_id, "place", "population", "2019–2023", 142300, "count", False, None, 500, True, "high_moe", "acs5",
                listing_id, "place", "households", "2019–2023", 55000, "count", False, None, 200, False, None, "acs5",
            ),
        )

    active, registry = _seed_active_and_registry(conn)
    rows = community_rows(conn, [listing_id], active=active, registry=registry)

    row = rows[listing_id]
    assert row["pop"] is None  # suppressed
    assert row["hh"] == "55,000 households"  # not suppressed


def test_community_rows_missing_listing_omitted_from_dict(conn):
    """Two listing ids, one with rows and one without -> the second is absent from the dict."""
    listing_id_1 = make_listing(conn, city="Round Rock")
    listing_id_2 = make_listing(conn, city="Cedar Park")

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE dataset_registry SET license_status = %s WHERE dataset_key IN (%s, %s, %s, %s)",
            ("cleared", "acs5", "acs5_prior", "zbp", "cbp"),
        )

        # Only seed rows for listing_id_1
        cur.execute(
            "UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s",
            ("06085", listing_id_1),
        )

        cur.execute(
            "INSERT INTO market_metric "
            "(listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (
                listing_id_1, "place", "population", "2019–2023", 142300, "count", False, None, 500, False, None, "acs5",
            ),
        )

    active, registry = _seed_active_and_registry(conn)
    rows = community_rows(conn, [listing_id_1, listing_id_2], active=active, registry=registry)

    assert listing_id_1 in rows
    assert listing_id_2 not in rows  # Missing from dict, not present with nulls
