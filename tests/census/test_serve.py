"""Task B7: community_rows serves the six formatted Community Context fields (population,
growth, income, households, vets, econ_k) to the listing serialiser, with one batched query
per page and the same gate logic market.py uses to decide what a buyer may see.
"""
from __future__ import annotations

import logging

import fakeredis

from app.census import catchment, geocode, materialize
from app.census.serve import BAND_LABEL, community_rows
from tests.census.listing_fixtures import make_listing
from tests.census.test_geocode import NOMATCH, _geocoder


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
            ("acs5", "2019-2023", "test", "acs5_prior", "2014-2018", "test", "zbp", "2022", "test", "cbp", "2022", "test"),
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
                listing_id, "place", "population", "2019-2023", 142300, "count", False, None, 500, False, None, "acs5",
                listing_id, "place", "households", "2019-2023", 55000, "count", False, None, 200, False, None, "acs5",
                listing_id, "place", "median_hh_income", "2019-2023", 85000, "dollars", False, None, 2000, False, None, "acs5",
                listing_id, "place", "population_growth_pct", "2019-2023", 5.5, "percent", True, None, 0.5, False, None, "acs5",
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
                listing_id, "place", "population", "2019-2023", 142300, "count", False, None, 500, False, None, "acs5",
                listing_id, "place", "households", "2019-2023", 55000, "count", False, None, 200, False, None, "acs5",
                listing_id, "place", "median_hh_income", "2019-2023", 85000, "dollars", False, None, 2000, False, None, "acs5",
                listing_id, "place", "population_growth_pct", "2019-2023", 5.5, "percent", True, None, 0.5, False, None, "acs5",
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
                listing_id, "place", "population", "2019-2023", 142300, "count", False, None, 500, False, None, "acs5",
                listing_id, "place", "households", "2019-2023", 55000, "count", False, None, 200, False, None, "acs5",
                listing_id, "place", "median_hh_income", "2019-2023", 85000, "dollars", False, None, 2000, False, None, "acs5",
                listing_id, "place", "population_growth_pct", "2019-2023", 5.5, "percent", True, None, 0.5, False, None, "acs5",
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
                listing_id, "place", "population", "2019-2023", 142300, "count", False, None, 500, True, "high_moe", "acs5",
                listing_id, "place", "households", "2019-2023", 55000, "count", False, None, 200, False, None, "acs5",
            ),
        )

    active, registry = _seed_active_and_registry(conn)
    rows = community_rows(conn, [listing_id], active=active, registry=registry)

    row = rows[listing_id]
    assert row["pop"] is None  # suppressed
    assert row["hh"] == "55,000 households"  # not suppressed


def test_community_rows_missing_listing_is_six_nulls_and_no_label(conn):
    """Two listing ids, one with rows and one without -> the second carries six nulls and no
    label (Task B10, D-C32), which is what puts the design's own "Community data unavailable"
    card on the screen instead of a grid of blanks."""
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
                listing_id_1, "place", "population", "2019-2023", 142300, "count", False, None, 500, False, None, "acs5",
            ),
        )

    active, registry = _seed_active_and_registry(conn)
    rows = community_rows(conn, [listing_id_1, listing_id_2], active=active, registry=registry)

    assert listing_id_1 in rows
    assert rows[listing_id_2] == {
        "pop": None, "growth": None, "income": None, "hh": None,
        "vets": None, "econ_k": None, "label": None,
        # D-C38: a row that names no figure names no geography either.
        "growth_scope": None, "income_note": None,
    }


def test_community_rows_missing_metrics_returns_nulls(conn):
    """When specific metrics are absent from the data, their fields return null."""
    listing_id = make_listing(conn, city="Round Rock", state="TX")

    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = %s WHERE dataset_key = %s", ("cleared", "acs5"))
        cur.execute("UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s", ("06085", listing_id))
        cur.execute("DELETE FROM active_vintage WHERE dataset_key IN (%s, %s)", ("acs5", "acs5_prior"))
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s), (%s, %s, now(), %s)",
            ("acs5", "2019-2023", "test", "acs5_prior", "2014-2018", "test"),
        )

        # Only seed population metric (missing households, income, growth, vets, econ_k)
        cur.execute(
            "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (listing_id, "place", "population", "2019-2023", 142300, "count", False, None, 500, False, None, "acs5"),
        )

    active, registry = _seed_active_and_registry(conn)
    result = community_rows(conn, [listing_id], active=active, registry=registry)

    assert listing_id in result
    row = result[listing_id]
    # Only population should be populated
    assert row["pop"] == "142,300"
    # All others should be null (metrics missing)
    assert row["hh"] is None
    assert row["income"] is None
    assert row["growth"] is None
    assert row["vets"] is None
    assert row["econ_k"] is None


def test_community_rows_uncleared_dataset_returns_nulls(conn):
    """When dataset license is not cleared, its metrics return null even if data exists."""
    listing_id = make_listing(conn, city="Round Rock", state="TX")

    with conn.cursor() as cur:
        # First, temporarily set dataset to cleared so we can insert metrics
        cur.execute("UPDATE dataset_registry SET license_status = %s WHERE dataset_key = %s", ("cleared", "acs5"))
        cur.execute("UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s", ("06085", listing_id))
        cur.execute("DELETE FROM active_vintage WHERE dataset_key IN (%s, %s)", ("acs5", "acs5_prior"))
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s), (%s, %s, now(), %s)",
            ("acs5", "2019-2023", "test", "acs5_prior", "2014-2018", "test"),
        )

        # Seed metrics while dataset is cleared
        cur.execute(
            "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (
                listing_id, "place", "population", "2019-2023", 142300, "count", False, None, 500, False, None, "acs5",
                listing_id, "place", "households", "2019-2023", 55000, "count", False, None, 200, False, None, "acs5",
            ),
        )
        # Now set the dataset to unresolved (uncleared)
        cur.execute("UPDATE dataset_registry SET license_status = %s WHERE dataset_key = %s", ("unresolved", "acs5"))

    active, registry = _seed_active_and_registry(conn)
    result = community_rows(conn, [listing_id], active=active, registry=registry)

    assert listing_id in result
    row = result[listing_id]
    # All fields should be null because dataset license is unresolved (not cleared)
    assert row["pop"] is None
    assert row["hh"] is None


def test_community_rows_suppressed_metrics_return_nulls(conn):
    """When metrics are suppressed, their fields return null."""
    listing_id = make_listing(conn, city="Round Rock", state="TX")

    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = %s WHERE dataset_key IN (%s, %s)", ("cleared", "acs5", "zbp"))
        cur.execute("UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s", ("06085", listing_id))
        cur.execute("DELETE FROM active_vintage WHERE dataset_key IN (%s, %s)", ("acs5", "acs5_prior"))
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s), (%s, %s, now(), %s), (%s, %s, now(), %s)",
            ("acs5", "2019-2023", "test", "acs5_prior", "2014-2018", "test", "zbp", "2022", "test"),
        )

        # Seed some metrics as suppressed
        cur.execute(
            "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (
                listing_id, "place", "population", "2019-2023", 142300, "count", False, None, 500, True, "high_moe", "acs5",
                listing_id, "place", "households", "2019-2023", 55000, "count", False, None, 200, False, None, "acs5",
                listing_id, "place", "establishments", "2022", 12, "count", False, None, 1, True, "too_few_records", "zbp",
            ),
        )

    active, registry = _seed_active_and_registry(conn)
    result = community_rows(conn, [listing_id], active=active, registry=registry)

    assert listing_id in result
    row = result[listing_id]
    # Suppressed population should return null, but unsuppressed households should be populated
    assert row["pop"] is None  # suppressed
    assert row["hh"] == "55,000 households"  # not suppressed
    assert row["vets"] is None  # suppressed
    assert row["econ_k"] is None  # missing metric


def test_community_rows_population_metric_absent_branches_to_households_check(conn):
    """Branch 135->142: When population metric is absent, control flows to households check.
    Other metrics present ensure the listing has rows; absence of population shows the branch."""
    listing_id = make_listing(conn, city="Round Rock", state="TX")

    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = %s WHERE dataset_key IN (%s, %s)", ("cleared", "acs5", "zbp"))
        cur.execute("UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s", ("06085", listing_id))
        cur.execute("DELETE FROM active_vintage WHERE dataset_key IN (%s, %s)", ("acs5", "acs5_prior"))
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s), (%s, %s, now(), %s)",
            ("acs5", "2019-2023", "test", "acs5_prior", "2014-2018", "test"),
        )

        # Seed households (NOT population) to show the branch when population key is missing
        cur.execute(
            "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (listing_id, "place", "households", "2019-2023", 55000, "count", False, None, 200, False, None, "acs5"),
        )

    active, registry = _seed_active_and_registry(conn)
    rows = community_rows(conn, [listing_id], active=active, registry=registry)

    row = rows[listing_id]
    assert row["pop"] is None  # population metric not present
    assert row["hh"] == "55,000 households"  # households present


def test_community_rows_acs5_prior_vintage_absent_nulls_growth(conn):
    """Branch in complex condition: When acs5_prior_vintage is None (not in active_vintage),
    growth does not get formatted even if data exists."""
    listing_id = make_listing(conn, city="Round Rock", state="TX")

    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = %s WHERE dataset_key IN (%s, %s, %s)", ("cleared", "acs5", "acs5_prior", "zbp"))
        cur.execute("UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s", ("06085", listing_id))

        # Seed active_vintage with acs5 but NOT acs5_prior - so acs5_prior_vintage will be None
        cur.execute("DELETE FROM active_vintage")
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)",
            ("acs5", "2019-2023", "test"),
        )

        # Seed all growth metrics but acs5_prior_vintage will be None
        cur.execute(
            "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()), "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (
                listing_id, "place", "population_growth_pct", "2019-2023", 5.5, "percent", True, None, 0.5, False, None, "acs5",
                listing_id, "place", "households", "2019-2023", 55000, "count", False, None, 200, False, None, "acs5",
            ),
        )

        # Manually fetch active and registry without calling _seed_active_and_registry
        cur.execute("SELECT dataset_key, vintage FROM active_vintage")
        active = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute("SELECT dataset_key, attribution_text, vintage, license_status, notes FROM dataset_registry")
        reg_cols = [d[0] for d in cur.description]
        registry = {r[0]: dict(zip(reg_cols, r)) for r in cur.fetchall()}

    rows = community_rows(conn, [listing_id], active=active, registry=registry)

    row = rows[listing_id]
    assert row["growth"] is None  # growth null because acs5_prior_vintage missing
    assert row["hh"] == "55,000 households"  # other metrics still present


def test_community_rows_revenue_per_establishment_suppressed_nulls_econ_k(conn):
    """Branch 178->182: When revenue_per_establishment is suppressed,
    econ_k is null even though the dataset is cleared."""
    listing_id = make_listing(conn, city="Round Rock", state="TX")

    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = %s WHERE dataset_key IN (%s, %s)", ("cleared", "acs5", "cbp"))
        cur.execute("UPDATE practice_location SET place_geoid = %s WHERE listing_id = %s", ("06085", listing_id))
        cur.execute("DELETE FROM active_vintage WHERE dataset_key = %s", ("acs5",))
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)",
            ("acs5", "2019-2023", "test"),
        )

        # Seed revenue_per_establishment as SUPPRESSED (not cleared path in the if condition)
        cur.execute(
            "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
            "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
            (listing_id, "place", "revenue_per_establishment", "2022", 450000, "dollars", True, None, 50000, True, "high_moe", "cbp"),
        )

    active, registry = _seed_active_and_registry(conn)
    rows = community_rows(conn, [listing_id], active=active, registry=registry)

    row = rows[listing_id]
    assert row["econ_k"] is None  # revenue_per_establishment suppressed


# ---------------------------------------------------------------------------------------------
# Task B10 / D-C32 — the drive-time fallback, and the card says which area it describes.
#
# The listing this exists for is the Orlando specialist centre: it geocoded ROOFTOP like every
# other seeded hospital and its address is not wrong in any way, but it sits in unincorporated
# Orange County where the Census has no `place`, so it has no `place`-band row at all. It does
# have complete `drive_10` figures, and a buyer may see them — provided the card says so, which
# is what `label` carries.
#
# The fallback is decided on FIGURES, never on row presence (B-2): a listing whose place rows are
# all suppressed, or whose place rows come from a dataset the VIN Foundation has not cleared,
# yields six nulls at the place band and must still reach its complete `drive_10` band.
# ---------------------------------------------------------------------------------------------

_SIX = (
    ("population", "2019-2023", 167997, "count", False, None, 500, False, None, "acs5"),
    ("households", "2019-2023", 59588, "count", False, None, 200, False, None, "acs5"),
    ("median_hh_income", "2019-2023", 69780, "dollars", False, None, 2000, False, None, "acs5"),
    ("population_growth_pct", "2019-2023", 9.0, "percent", True, None, 0.5, False, None, "acs5"),
    ("establishments", "2022", 10.8, "count", False, None, 1, False, None, "zbp"),
    ("revenue_per_establishment", "2022", 512000, "dollars", True, None, 50000, False, None, "cbp"),
)

_METRIC_INSERT = (
    "INSERT INTO market_metric "
    "(listing_id, band, metric_key, vintage, value_num, unit, is_derived, "
    "formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())"
)


def _seed_band(conn, listing_id, band, *, suppressed=False, source_dataset=None, metrics=_SIX):
    """Seed one band's six figures for `listing_id`, optionally all suppressed or all stamped
    with a dataset the caller has left uncleared."""
    with conn.cursor() as cur:
        for key, vintage, value, unit, derived, formula, moe, supp, reason, dataset in metrics:
            cur.execute(
                _METRIC_INSERT,
                (
                    listing_id, band, key, vintage, value, unit, derived, formula, moe,
                    True if suppressed else supp,
                    "high_moe" if suppressed else reason,
                    source_dataset or dataset,
                ),
            )


def _ring(metrics=_SIX):
    """`metrics` with the median shaped the way a CATCHMENT median actually comes out of the
    pipeline: `is_derived` TRUE and no MOE.

    Minor, whole-branch review 2026-09-11, the class commit `0154d54` set out to remove — stub
    only values the API can emit. `_SIX` carries a published median (`is_derived=False`, a real
    MOE), which is the PLACE shape: `materialize.py`'s `_band_inputs` returns `income_is_approx`
    FALSE only on the `place` branch and hard-codes TRUE with a null MOE for every catchment,
    because a ring median is a household-weighted median of the tract medians inside it and
    never a published figure. So `_SIX` seeded into `drive_10` described a row the pipeline
    cannot write, and a test asserting `income_note is None` off it was pinning a state
    production can never reach — and would have obstructed a correct change to `serve.py`.

    The two tests that pin the qualifier's INDEPENDENCE from the band still pass their own
    explicit tuples and are untouched: `serve.py` reads the served row's own `is_derived` on
    purpose, so that an approximate PLACE median — which the producer does not make today — could
    not lose the word in silence."""
    return tuple(
        (m[0], m[1], m[2], m[3], True, m[5], None, m[7], m[8], m[9]) if m[0] == "median_hh_income" else m
        for m in metrics
    )


def _clear_all(conn):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE dataset_registry SET license_status = %s WHERE dataset_key IN (%s, %s, %s, %s)",
            ("cleared", "acs5", "acs5_prior", "zbp", "cbp"),
        )


def test_a_place_band_listing_carries_no_label(conn):
    """D-C32: the label exists only to OVERRIDE the design's own wording. A listing whose figures
    came from its own community keeps that wording, so the label is None."""
    listing_id = make_listing(conn, city="Round Rock", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place")

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["label"] is None
    assert row["pop"] == "167,997"


def test_a_listing_with_no_place_rows_falls_back_to_drive_10_and_says_so(conn):
    """The Orlando shape: no `place` row at all (unincorporated county, no Census place), complete
    `drive_10` figures. The figures are served and the card is told which area they describe.

    §8 of the D-C38 brief: if this listing's card changes at all beyond the Growth tile's new
    sub-line, the implementation is wrong. The six figures below are the ones it was served
    before; only the label's WORDING moves, under D-C39."""
    listing_id = make_listing(conn, city="Orlando", state="FL", zip="32819")
    _clear_all(conn)
    _seed_band(conn, listing_id, "drive_10", metrics=_ring())

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["label"] == _BAND_LABEL
    assert row["pop"] == "167,997"
    assert row["hh"] == "59,588 households"
    assert row["income"] == "$69,780"
    # A ring median is always approximate, so the card always says so beside it.
    assert row["income_note"] == f"{_BAND_LABEL} \u00b7 approximate"
    assert row["growth"] == "+9.0% since 2018"
    assert row["vets"] == 10
    assert row["econ_k"] == 512


def test_place_rows_that_are_all_suppressed_fall_back_to_drive_10(conn):
    """B-2, and still true under D-C38: the choice is decided on FIGURES, not on row presence.
    Place rows exist here, and every one of them is suppressed, so the place band yields no area
    figure and the catchment answers."""
    listing_id = make_listing(conn, city="Orlando", state="FL", zip="32819")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", suppressed=True)
    _seed_band(conn, listing_id, "drive_10", metrics=_ring())

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["label"] == _BAND_LABEL
    assert row["pop"] == "167,997"
    assert row["vets"] == 10
    # The served row is the ring's, and a ring median is derived, so the qualifier is there. The
    # note follows the FIGURE'S OWN row rather than the band it was read from, which is a
    # distinction the two tests further down pin on their own explicit tuples; this fixture is no
    # longer the place to make it, because it made it with a row the pipeline cannot write.
    assert row["income_note"] == f"{_BAND_LABEL} \u00b7 approximate"


def test_place_rows_from_an_uncleared_dataset_fall_back_to_drive_10(conn):
    """The licence-gate case, and it is not hypothetical: place rows stamped with a dataset the
    VIN Foundation has not cleared are six nulls, and the complete `drive_10` band answers."""
    listing_id = make_listing(conn, city="Orlando", state="FL", zip="32819")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", source_dataset="acs5")
    _seed_band(conn, listing_id, "drive_10", metrics=_ring())
    with conn.cursor() as cur:
        # `drive_10`'s establishments/payroll rows stay on zbp/cbp, which remain cleared.
        cur.execute(
            "UPDATE market_metric SET source_dataset = %s WHERE listing_id = %s AND band = %s",
            ("acs5", listing_id, "place"),
        )
        cur.execute(
            "UPDATE dataset_registry SET license_status = %s WHERE dataset_key = %s",
            ("unresolved", "acs5"),
        )

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    # acs5 is uncleared, so the four ACS figures are null in BOTH bands — but the drive_10 band
    # still carries the two CBP/ZBP figures, and `vets` is one of the four area figures, which is
    # what makes the catchment the band the area group is read from.
    assert row["label"] == _BAND_LABEL
    assert row["vets"] == 10
    assert row["econ_k"] == 512
    assert row["pop"] is None


def test_a_listing_with_neither_band_is_six_nulls_and_no_label(conn):
    """D-C32's third case: no figures anywhere. Six nulls and no label, so the frontend reaches
    the design's own "Community data unavailable" card."""
    listing_id = make_listing(conn, city="Cedar Park", state="TX")
    _clear_all(conn)

    active, registry = _seed_active_and_registry(conn)
    result = community_rows(conn, [listing_id], active=active, registry=registry)

    assert result[listing_id] == {
        "pop": None, "growth": None, "income": None, "hh": None,
        "vets": None, "econ_k": None, "label": None,
        "growth_scope": None, "income_note": None,
    }


def test_a_drive_20_only_listing_reaches_no_figures(conn):
    """`drive_20` is not a fallback D-C32 sanctions: only `place` and `drive_10` are read, so a
    listing with nothing but a 20-minute band is the unavailable card, never a wider area served
    under a narrower heading."""
    listing_id = make_listing(conn, city="Cedar Park", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "drive_20")

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["label"] is None
    assert row["pop"] is None
    assert row["vets"] is None


# ---------------------------------------------------------------------------------------------
# D-C38 / D-C39 (John, 2026-09-11) — per-figure geography. Each figure is served at its own
# honest geography and the row NAMES it, per tile.
#
# The defect this replaces: all twelve Dallas listings sat inside one Census place, so the
# place-preferred rule served all twelve the City of Dallas — the same four numbers under twelve
# different neighbourhood headings — while their own catchment figures were already materialised
# and unreachable by any screen.
#
# What changes, and what does NOT:
#   * The three AREA figures (population, households, median income) and the off-card `vets` come
#     from the catchment band, with `place` as the fallback. They move as ONE GROUP, because one
#     `label` describes all of them and a group half-drawn from each band would put a city figure
#     under a catchment caption — the very defect being fixed.
#   * `growth` keeps its place-or-county geography (D12: `materialize.py` computes it once, OUTSIDE
#     the band loop) and `growth_scope` NAMES that geography, so the tile stops implying it
#     describes the ring beside it.
#   * `econ_k` keeps county.
#   * D-C39: the ring is described by DISTANCE, not by time. It is an 8 km straight-line buffer
#     (spec §8), not a routed drive time, and true isochrones are still open for V1 (spec §15).
#
# `_SIX` CANNOT TELL THE BANDS APART — it seeds identical values in both (`_seed_band`), which is
# why no test above could see the flip. The two tuples below differ in every area figure, and
# `_CATCHMENT_SIX`'s median is the shape the pipeline actually produces for a ring: `is_derived`
# with no MOE (`materialize.py:210`, `:241` — a catchment median is a household-weighted median
# of tract medians, never a published one, and can never be suppressed).
# ---------------------------------------------------------------------------------------------

# IMPORTED, never re-typed (I3, whole-branch review 2026-09-11). A copy here would go on
# asserting the old sentence after `serve.py`'s own moved, which is the drift these tests exist
# to catch; `tests/census/test_band_distance.py` links that sentence to the band radius in turn.
_BAND_LABEL = BAND_LABEL

# The City of Dallas, as every one of its twelve listings was served before D-C38.
_PLACE_SIX = (
    ("population", "2019-2023", 1299553, "count", False, None, 500, False, None, "acs5"),
    ("households", "2019-2023", 528038, "count", False, None, 200, False, None, "acs5"),
    ("median_hh_income", "2019-2023", 67760, "dollars", False, None, 2000, False, None, "acs5"),
    ("population_growth_pct", "2019-2023", -1.5, "percent", True, None, 0.5, False, None, "acs5"),
    ("establishments", "2022", 250, "count", False, None, 1, False, None, "zbp"),
    ("revenue_per_establishment", "2022", 512000, "dollars", True, None, 50000, False, None, "cbp"),
)

# Foxtrot's own ring — "Highland Park / affluent central", the listing John was shown.
_CATCHMENT_SIX = (
    ("population", "2019-2023", 369569, "count", False, None, 500, False, None, "acs5"),
    ("households", "2019-2023", 181745, "count", False, None, 200, False, None, "acs5"),
    ("median_hh_income", "2019-2023", 109548, "dollars", True, None, None, False, None, "acs5"),
    ("population_growth_pct", "2019-2023", -1.5, "percent", True, None, 0.5, False, None, "acs5"),
    ("establishments", "2022", 41, "count", False, None, 1, False, None, "zbp"),
    ("revenue_per_establishment", "2022", 512000, "dollars", True, None, 50000, False, None, "cbp"),
)


def _seed_geography(conn, listing_id, *, place_geoid=None, place_name=None, county_geoid=None, county_name=None,
                    precision="rooftop"):
    """The listing's geocoded place and county, and the `geo_area` rows that NAME them.

    D-C38 supersedes `serve.py`'s own "There is no geoid lookup and none is wanted": the Growth
    tile needs the name of the geography its figure was measured at, which is
    `practice_location.place_geoid` joined to `geo_area.name` at summary level 160 (or
    `county_geoid` at 050). `tiger_cb`'s active vintage is what picks the boundary edition, the
    same vintage `materialize.py` builds catchments against."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO practice_location (listing_id, address_hash, county_geoid, place_geoid, geo_precision, geocoded_at, geocoder_vintage) "
            "VALUES (%s, 'h', %s, %s, %s, now(), 'Current_Current')",
            (listing_id, county_geoid, place_geoid, precision),
        )
        # A `geo_area` row only where the caller gave a NAME. A geoid with no name is the
        # "geocoded, but the active boundary edition does not resolve it" case (I4) — the row is
        # deliberately absent, not present with a null name, which `geo_area.name` forbids.
        for geo_id, level, name in ((place_geoid, "160", place_name), (county_geoid, "050", county_name)):
            if geo_id is not None and name is not None:
                cur.execute(
                    "INSERT INTO geo_area (geo_id, summary_level, vintage, name) VALUES (%s, %s, '2023', %s)",
                    (geo_id, level, name),
                )
        cur.execute("DELETE FROM active_vintage WHERE dataset_key = 'tiger_cb'")
        cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES ('tiger_cb', '2023', now(), 'test')")


def _set_geo_level(conn, listing_id, metric_key, geo_level):
    """Stamp one metric's own `inputs->>'geo_level'`, in every band — which is exactly what
    `materialize.py` does for growth (`ctx.growth_inputs`, written into all three bands) and for
    payroll (`"geo_level": "county"`). The fixtures above seed no `inputs` at all, so a row
    without this stamp is the "growth exists but names no geography" case."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE market_metric SET inputs = jsonb_build_object('geo_level', %s) WHERE listing_id = %s AND metric_key = %s",
            (geo_level, listing_id, metric_key),
        )


def test_the_area_figures_come_from_the_catchment_band_when_both_bands_have_them(conn):
    """D-C38, and the gate the D-C32 suite never had: BOTH bands are seeded, with DIFFERENT
    figures, and the row must be able to say which one each figure came from.

    Population, households, median income and `vets` are the practice's own ring. Growth and
    payroll are identical in both bands by construction, so they are served unchanged."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _seed_band(conn, listing_id, "drive_10", metrics=_CATCHMENT_SIX)

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["pop"] == "369,569"
    assert row["hh"] == "181,745 households"
    assert row["income"] == "$109,548"
    assert row["vets"] == 41
    assert row["label"] == _BAND_LABEL
    assert row["growth"] == "-1.5% since 2018"
    assert row["econ_k"] == 512


def test_a_catchment_median_carries_the_approximate_qualifier(conn):
    """A ring median is a household-weighted median of the tract medians inside it, never a
    published figure — `materialize.py` stamps it `is_derived` with no MOE, and it can never be
    suppressed. The contract has always said an approximate median renders the word beside the
    value (`docs/integrations/market-data-api.md`); until D-C38 the card had no way to."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _seed_band(conn, listing_id, "drive_10", metrics=_CATCHMENT_SIX)

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["income_note"] == f"{_BAND_LABEL} · approximate"


def test_a_place_band_median_is_published_and_carries_no_qualifier(conn):
    """The other arm: a place median IS published by the Census, so nothing is added to it and
    the design's own "Household, 2023" sub-line stands byte for byte."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["income"] == "$67,760"
    assert row["label"] is None
    assert row["income_note"] is None


def test_growth_keeps_its_place_geography_and_the_row_names_it(conn):
    """D-C38's whole point on the Growth tile: the figure stays the city's — it exists at no
    finer geography until the 2010->2020 tract crosswalk is loaded (a registered Phase C
    deferral) — and `growth_scope` says so, beside a population that IS the ring's.

    The scope is TIGER's own place NAME with nothing prefixed. The first implementation composed
    "City of " + name, matching D-C38's option text, and that is wrong for a census-designated
    place: `app/census/tiger.py:102` loads level 160 from `NAME`, which carries no legal
    descriptor, so Florin — which the Sacramento listings resolve to — would have been labelled
    "City of Florin". Ruled 2026-09-11: name what TIGER gives and invent no descriptor."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_geography(conn, listing_id, place_geoid="4819000", place_name="Dallas", county_geoid="48113", county_name="Dallas County")
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _seed_band(conn, listing_id, "drive_10", metrics=_CATCHMENT_SIX)
    _set_geo_level(conn, listing_id, "population_growth_pct", "place")

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["pop"] == "369,569"
    assert row["growth"] == "-1.5% since 2018"
    assert row["growth_scope"] == "Dallas"


def test_a_census_designated_place_is_not_called_a_city(conn):
    """The case that made the composed prefix wrong. TIGER's level-160 `NAME` is bare, so a CDP
    arrives as "Florin" and any "City of " prefix states a legal status it does not have. The
    Sacramento listings resolve to exactly this. Reverting to a composed prefix fails here."""
    listing_id = make_listing(conn, city="Sacramento", state="CA")
    _clear_all(conn)
    _seed_geography(conn, listing_id, place_geoid="0624638", place_name="Florin", county_geoid="06067", county_name="Sacramento County")
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _seed_band(conn, listing_id, "drive_10", metrics=_CATCHMENT_SIX)
    _set_geo_level(conn, listing_id, "population_growth_pct", "place")

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["growth_scope"] == "Florin"
    assert "City of" not in (row["growth_scope"] or "")


def test_a_county_level_growth_figure_is_named_as_its_county(conn):
    """The Orlando shape. Its growth row is the only county-level one on QA, because the practice
    sits in unincorporated Orange County where the Census has no place — `materialize.py` falls
    from level 160 to 050 and stamps `geo_level: "county"`. Until now that figure was pooled in
    silence; it is named."""
    listing_id = make_listing(conn, city="Orlando", state="FL", zip="32819")
    _clear_all(conn)
    _seed_geography(conn, listing_id, county_geoid="12095", county_name="Orange County")
    _seed_band(conn, listing_id, "drive_10", metrics=_CATCHMENT_SIX)
    _set_geo_level(conn, listing_id, "population_growth_pct", "county")

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["label"] == _BAND_LABEL
    assert row["growth"] == "-1.5% since 2018"
    assert row["growth_scope"] == "Orange County"


def test_a_growth_figure_whose_geography_has_no_name_carries_no_scope(conn):
    """D-C31's rule applied to the new field: where the join has nothing to say the row says
    nothing, and the Growth tile keeps A21.3d's own "Since <year>" sub-line unchanged. Reached
    two ways here — no `practice_location` row at all, and no `geo_area` name behind one."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _set_geo_level(conn, listing_id, "population_growth_pct", "place")

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["growth"] == "-1.5% since 2018"
    assert row["growth_scope"] is None


def test_a_listing_with_neither_band_carries_no_scope_and_no_income_note(conn):
    """§8: a per-figure rule makes an all-null row RARER; it must not make it unreachable. The
    design's own "Community data unavailable" card is still what this reaches."""
    listing_id = make_listing(conn, city="Cedar Park", state="TX")
    _clear_all(conn)

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row == {
        "pop": None, "growth": None, "income": None, "hh": None,
        "vets": None, "econ_k": None, "label": None,
        "growth_scope": None, "income_note": None,
    }


def test_a_derived_place_median_carries_the_qualifier_too(conn):
    """Fix round 1, finding 5. The qualifier follows the SERVED ROW's own `is_derived`, never the
    band the area group came from.

    `income_note` used to be gated on `label is not None` — on the group having come from the
    catchment — which is true of every approximate median the pipeline produces TODAY
    (`materialize.py` derives the catchment median and reads the place median straight from the
    ACS) but is not what makes a figure approximate. An approximate place median would have lost
    the qualifier silently, and the contract's copy rule has no band condition in it:
    "`median_hh_income.approximate: true` → render 'approximate' beside the value"
    (`docs/integrations/market-data-api.md`).

    With no label there is no area to name, so the note is the qualifier alone — the tile's one
    sub-line says the number is approximate and nothing it cannot support."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    derived_place = tuple(
        ("median_hh_income", "2019-2023", 67760, "dollars", True, None, None, False, None, "acs5")
        if m[0] == "median_hh_income" else m
        for m in _PLACE_SIX
    )
    _seed_band(conn, listing_id, "place", metrics=derived_place)

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["label"] is None
    assert row["income"] == "$67,760"
    assert row["income_note"] == "Approximate"


# ---------------------------------------------------------------------------------------------
# Fix round 1, finding 3 — the shape of the suppression rule, which is ASYMMETRIC in two ways
# that were both deliberate, both documented in `_AREA_KEYS`, and neither tested.
#
# `from_catchment = any(drive[k] is not None for k in _AREA_KEYS)` where `_AREA_KEYS` is
# `("pop", "hh", "income", "vets")`. So:
#
#   (a) `vets` is OFF-CARD — the Community Context card never renders it; it feeds the Browse
#       competition layer — and it is still a vote. An off-card figure can therefore decide which
#       band the three ON-CARD figures are read from.
#   (b) Once the group comes from the catchment it comes from the catchment WHOLE. A figure the
#       catchment suppresses is null even where the place band has it, because one `label`
#       describes the whole group and a group drawn half from each band would put a city figure
#       under a ring caption — the very defect D-C38 exists to remove.
#
# Together they have one consequence worth naming: a listing whose place band is fully populated
# can reach the design's own "Community data unavailable" card, if the catchment suppresses
# everything except the one figure the card never shows.
# ---------------------------------------------------------------------------------------------


def _suppressing(metrics, *keys):
    """`metrics` with the NAMED rows marked suppressed. `_seed_band`'s own `suppressed=True` is
    all-or-nothing; the two shapes below are partial by nature."""
    return tuple(
        (m[0], m[1], m[2], m[3], m[4], m[5], m[6], True, "high_moe", m[9]) if m[0] in keys else m
        for m in metrics
    )


def test_an_off_card_figure_decides_the_on_card_group_s_band(conn):
    """(a), and the consequence it carries. The catchment suppresses every figure but
    `establishments` — the `vets` count, which this card never renders — and that one off-card
    figure is enough to move the whole area group to the catchment. The three ON-CARD figures are
    then the catchment's own, which is to say null, while the place band's complete ACS figures
    go unread: a populated card becomes the design's "Community data unavailable" card.

    This is the rule working as ruled, not a defect — `vets` is one of `_AREA_KEYS` because it
    describes the same area as the other three and a group split across bands is the thing D-C38
    forbids. It is pinned here because nothing else pins it, and a later reader deciding to drop
    `vets` from `_AREA_KEYS` should have to do it deliberately."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _seed_band(conn, listing_id, "drive_10", metrics=_suppressing(
        _CATCHMENT_SIX, "population", "households", "median_hh_income",
        "population_growth_pct", "revenue_per_establishment",
    ))

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    # The off-card figure is the only one the catchment kept, and it carried the vote.
    assert row["vets"] == 41
    assert row["label"] == _BAND_LABEL
    # The three the card renders are the catchment's, which is to say absent — NOT the place's
    # 1,299,553 / 528,038 households / $67,760, which is what the card showed before D-C38.
    assert row["pop"] is None
    assert row["hh"] is None
    assert row["income"] is None
    # Growth and payroll are not area figures, so they still answer from whichever band has them.
    assert row["growth"] == "-1.5% since 2018"
    assert row["econ_k"] == 512


def test_a_figure_the_catchment_suppresses_is_never_backfilled_from_the_place(conn):
    """(b). The catchment has population and households and suppresses the median; the place band
    has all three. The median is NULL — never the place's $67,760 read in beside two catchment
    figures under one caption that says "within about 5 miles of the practice".

    `_AREA_KEYS`'s own comment is the rule: "A figure the chosen band does not have is null …; it
    is never backfilled from the other band." A per-figure backfill here would put a city median
    under a ring caption, which is the defect D-C38 exists to remove, one tile further along."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _seed_band(conn, listing_id, "drive_10", metrics=_suppressing(_CATCHMENT_SIX, "median_hh_income"))

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["label"] == _BAND_LABEL
    assert row["pop"] == "369,569"
    assert row["hh"] == "181,745 households"
    assert row["income"] is None
    assert row["income"] != "$67,760"
    # No median, no note: the qualifier belongs to a figure that is shown.
    assert row["income_note"] is None


# ---------------------------------------------------------------------------------------------
# C2 (whole-branch review, 2026-09-11) — a row whose `value_num` is NULL.
#
# `market_metric.value_num` is NULLABLE (`migrations/061_census_listing_tables.sql:34`) and
# `suppressed` is `NOT NULL DEFAULT false` (`:40`), and the pipeline writes exactly that pair:
# `_suppression(None, moe)` returns `(False, None)` on purpose — "A missing value has nothing to
# suppress: there is no row content to falsely read as certain" (`materialize.py:105-107`) — and
# `materialize.py:239-244` emits the row regardless of whether the ACS answered.
#
# So a NULL value reaches `_figures` behind BOTH of its guards, and `float(None)` raised
# `TypeError: float() argument must be a string or a real number, not 'NoneType'` out of the
# listings serialiser: a 500 on the whole page, not one blank tile.
#
# A null figure is ABSENT, not an error. D-C31's rule governs it — "a missing figure is omitted,
# never zeroed" — and `_figures`'s own docstring already promises the answer: "A figure that is
# absent is None". The row's existence was never the claim; the value is.
#
# This branch did not create the bug, it widened it: at base only one band was evaluated unless
# the other yielded nothing, and this branch evaluates BOTH for EVERY listing (`serve.py:290-291`),
# so a single unanswered figure in either band took the page down.
# ---------------------------------------------------------------------------------------------


def _nulling(metrics, *keys):
    """`metrics` with the NAMED rows carrying no value — `value_num` NULL, no MOE, and
    `suppressed` FALSE, which is the exact row `materialize.py` writes for a figure the Census
    did not answer."""
    return tuple(
        (m[0], m[1], None, m[3], m[4], m[5], None, False, None, m[9]) if m[0] in keys else m
        for m in metrics
    )


def test_every_figure_with_a_null_value_is_absent_rather_than_a_500(conn):
    """All six rows present, all six unanswered. Before the guard this raised `TypeError:
    float() argument must be a string or a real number, not 'NoneType'` on the first of them."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_nulling(
        _SIX, "population", "households", "median_hh_income",
        "population_growth_pct", "establishments", "revenue_per_establishment",
    ))

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["pop"] is None
    assert row["hh"] is None
    assert row["income"] is None
    assert row["growth"] is None
    assert row["vets"] is None
    assert row["econ_k"] is None
    # No figure came from the catchment, so nothing overrides the design's own wording, and the
    # growth scope names a geography no figure was measured at.
    assert row["label"] is None
    assert row["growth_scope"] is None
    assert row["income_note"] is None


def test_a_null_figure_is_absent_on_its_own_and_leaves_the_other_five_standing(conn):
    """`_figures`'s "Every figure is independent" holds for an unanswered value exactly as it
    holds for a suppressed one: the population is absent and the other five are served."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_nulling(_SIX, "population"))

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["pop"] is None
    assert row["hh"] == "59,588 households"
    assert row["income"] == "$69,780"
    assert row["growth"] == "+9.0% since 2018"
    assert row["vets"] == 10
    assert row["econ_k"] == 512


def test_a_null_catchment_figure_does_not_vote_the_area_group_to_the_catchment(conn):
    """The band choice reads FIGURES, and an unanswered value is not one. The catchment's four
    area rows are all present and all unanswered, so the place band — which has them — answers,
    and the card keeps its own community's wording."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _seed_band(conn, listing_id, "drive_10", metrics=_nulling(
        _CATCHMENT_SIX, "population", "households", "median_hh_income", "establishments",
    ))

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["label"] is None
    assert row["pop"] == "1,299,553"
    assert row["income"] == "$67,760"
    assert row["vets"] == 250


# ---------------------------------------------------------------------------------------------
# I4 (whole-branch review, 2026-09-11) — a scope that goes null FLEET-WIDE, and says nothing.
#
# `_scope_names` joins `geo_area` on the CURRENT `active_vintage.tiger_cb`, and
# `practice_location` carries no vintage column: its geoids were resolved by the Census geocoder
# at whatever edition was current then. Activate a `tiger_cb` whose `geo_area` rows are not
# loaded — or not loaded yet — and the join matches nothing for EVERY listing at once. Every
# growth sub-line loses its geography while the card goes on saying the figures came from a ring,
# which is the D-C38 defect restored silently and everywhere.
#
# `_scope_names`'s own docstring made the conflation explicit: "a database with no active
# `tiger_cb` matches no row and names nothing, which is the same answer as a listing that was
# never geocoded." It is not the same answer. One is a listing the geocoder could not place; the
# other is an operations fault that has just blanked the whole fleet.
#
# RULED HERE (implementer, justified in the fix report): the page keeps serving and the fault
# becomes AUDIBLE, rather than the page failing. C2 one finding up removed exactly this class of
# thing — a data-ops condition taking the listings page down — and reinstating it for a missing
# sub-line would be worse than the defect. The join stays pinned to the active vintage, because
# `geo_area` holds several editions and a place's NAME can change between them (annexation,
# renaming), so dropping the term would name the area from an arbitrary edition.
#
# The two states are separated in the QUERY, not by a second one: `LEFT JOIN` with the geoid's
# own `IS NOT NULL` in the WHERE, so a row comes back for every listing that HAS a geoid and its
# `name` is null exactly when the active vintage could not resolve it. Same two-branch UNION,
# same index descent, same one query per page.
# ---------------------------------------------------------------------------------------------


def _roll_tiger_forward(conn, vintage="2024"):
    """Activate a `tiger_cb` edition whose `geo_area` rows are not loaded — the shape of a
    boundary refresh whose ingest has not run, or has run partially."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM active_vintage WHERE dataset_key = 'tiger_cb'")
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) "
            "VALUES ('tiger_cb', %s, now(), 'test')", (vintage,),
        )


def test_a_tiger_roll_forward_that_blanks_every_scope_says_so_in_the_log(conn, caplog):
    """The fleet-wide case. The listing is geocoded, its place is named at the edition that was
    current, and the active edition has no rows at all: the scope goes null and the log names the
    vintage and the count, so the condition cannot be mistaken for "these listings were never
    geocoded"."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_geography(conn, listing_id, place_geoid="4819000", place_name="Dallas", county_geoid="48113", county_name="Dallas County")
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _set_geo_level(conn, listing_id, "population_growth_pct", "place")
    _roll_tiger_forward(conn)

    active, registry = _seed_active_and_registry(conn)
    with caplog.at_level(logging.WARNING, logger="app.census.serve"):
        row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    # The figure still serves; only the name it would have been qualified by is gone.
    assert row["growth"] == "-1.5% since 2018"
    assert row["growth_scope"] is None
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "2024" in message, f"the warning does not name the active tiger_cb vintage: {message!r}"
    assert "2" in message, f"the warning does not count the geoids it could not resolve: {message!r}"


def test_a_listing_that_was_never_geocoded_is_silent(conn, caplog):
    """The other half of the conflation, and the reason the warning has to be earned rather than
    fired whenever a scope is null: a listing with no `practice_location` row has no geoid to
    resolve, so there is nothing to warn about and a page of them must not shout."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _set_geo_level(conn, listing_id, "population_growth_pct", "place")

    active, registry = _seed_active_and_registry(conn)
    with caplog.at_level(logging.WARNING, logger="app.census.serve"):
        row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["growth_scope"] is None
    assert caplog.records == []


def test_a_resolved_page_is_silent(conn, caplog):
    """The healthy path warns about nothing — proved here so the assertions above cannot be
    satisfied by a warning that fires unconditionally."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_geography(conn, listing_id, place_geoid="4819000", place_name="Dallas", county_geoid="48113", county_name="Dallas County")
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _set_geo_level(conn, listing_id, "population_growth_pct", "place")

    active, registry = _seed_active_and_registry(conn)
    with caplog.at_level(logging.WARNING, logger="app.census.serve"):
        row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["growth_scope"] == "Dallas"
    assert caplog.records == []


def test_one_listing_whose_place_alone_is_unnamed_still_warns(conn, caplog):
    """The warning counts GEOIDS, not listings: this one resolves its county and not its place,
    which is a partial boundary ingest rather than a fleet-wide blanking, and is worth the same
    sentence. The county name is still served."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_geography(conn, listing_id, place_geoid="4819000", county_geoid="48113", county_name="Dallas County")
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _set_geo_level(conn, listing_id, "population_growth_pct", "county")

    active, registry = _seed_active_and_registry(conn)
    with caplog.at_level(logging.WARNING, logger="app.census.serve"):
        row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["growth_scope"] == "Dallas County"
    assert len(caplog.records) == 1
    assert "2023" in caplog.records[0].getMessage()


# ---- fix round 1, Important 1: a point that is not a rooftop match is served its city ----------


_PLACE_POLY = "POLYGON((-97.95 30.40,-97.65 30.40,-97.65 30.60,-97.95 30.60,-97.95 30.40))"
_ELSEWHERE_POLY = "POLYGON((-96.00 30.40,-95.70 30.40,-95.70 30.60,-96.00 30.60,-96.00 30.40))"


def _seed_ladder_world(conn, *, place_covers_the_zcta: bool) -> None:
    """The world a WIZARD listing actually lands in, with NO `practice_location` row: `resolve()`
    writes that itself, through the §11 ladder, which is the whole point of these two tests.

    Two tracts and two ZCTAs around one point, a place, a county and the ACS/CBP/ZBP rows behind
    them. The CITY figures (place, level 160) and the RING figures (tracts, level 140) are
    deliberately different numbers, so an assertion on one of them cannot pass for the other's
    reason."""
    with conn.cursor() as cur:
        squares = {
            "48491000001": "POLYGON((-97.90 30.45,-97.80 30.45,-97.80 30.55,-97.90 30.55,-97.90 30.45))",
            "48491000002": "POLYGON((-97.80 30.45,-97.70 30.45,-97.70 30.55,-97.80 30.55,-97.80 30.45))",
        }
        for gid, wkt in squares.items():
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid)"
                " VALUES (%s,'140','2023',%s,'48','491','48491', ST_Multi(ST_GeomFromText(%s,4269)),"
                "         ST_Centroid(ST_GeomFromText(%s,4269)))",
                (gid, f"Census Tract {gid}", wkt, wkt),
            )
        for gid, wkt in (("78613", squares["48491000001"]), ("78664", squares["48491000002"])):
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid)"
                " VALUES (%s,'860','2023',%s, ST_Multi(ST_GeomFromText(%s,4269)), ST_Centroid(ST_GeomFromText(%s,4269)))",
                (gid, f"ZCTA5 {gid}", wkt, wkt),
            )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid)"
            " VALUES ('4813552','160','2023','Cedar Park city','48', ST_Multi(ST_GeomFromText(%s,4269)),"
            "         ST_Centroid(ST_GeomFromText(%s,4269)))",
            (_PLACE_POLY if place_covers_the_zcta else _ELSEWHERE_POLY,) * 2,
        )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid)"
            " VALUES ('48491','050','2023','Williamson County','48',"
            "  ST_Multi(ST_GeomFromText('POLYGON((-99 30,-97 30,-97 31,-99 31,-99 30))',4269)), ST_Point(-98,30.5,4269))"
        )
        cur.execute("DELETE FROM active_vintage WHERE dataset_key = 'tiger_cb'")
        cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by)"
                    " VALUES ('tiger_cb','2023',now(),'test')")

        cur.execute(
            "INSERT INTO ingest_run (dataset_key, vintage, started_at, status) VALUES"
            " ('acs5','2019-2023',now(),'succeeded'),('acs5_prior','2014-2018',now(),'succeeded'),"
            " ('cbp','2022',now(),'succeeded'),('zbp','2022',now(),'succeeded')"
        )
        cur.execute("SELECT id FROM ingest_run ORDER BY id DESC LIMIT 4")
        zbp_r, cbp_r, prior_r, acs_r = [r[0] for r in cur.fetchall()]
        # THE CITY: level 160, the figures the ruling serves.
        cur.executemany(
            "INSERT INTO acs_measure VALUES ('4813552','160','2019-2023',%s,%s,%s,%s)",
            [("B01003_001E", 81900, 900, acs_r), ("B11001_001E", 27600, 600, acs_r), ("B19013_001E", 118400, 4100, acs_r)],
        )
        cur.execute("INSERT INTO acs_measure VALUES ('4813552','160','2014-2018','B01003_001E',71716,850,%s)", (prior_r,))
        # THE RING: level 140, deliberately different figures.
        cur.executemany(
            "INSERT INTO acs_measure VALUES (%s,'140','2019-2023',%s,%s,%s,%s)",
            [(g, v, e, m, acs_r) for g, v, e, m in (
                ("48491000001", "B01003_001E", 4000, 200), ("48491000001", "B11001_001E", 1500, 95),
                ("48491000001", "B19013_001E", 118400, 9100),
                ("48491000002", "B01003_001E", 3000, 300), ("48491000002", "B11001_001E", 1200, 80),
                ("48491000002", "B19013_001E", 98000, 12000),
            )],
        )
        # The county: households for the CBP apportionment, and its own population both vintages so
        # growth still has a geography when there is no place at all.
        cur.execute("INSERT INTO acs_measure VALUES ('48491','050','2019-2023','B11001_001E',230000,1200,%s)", (acs_r,))
        cur.execute("INSERT INTO acs_measure VALUES ('48491','050','2019-2023','B01003_001E',600000,2000,%s)", (acs_r,))
        cur.execute("INSERT INTO acs_measure VALUES ('48491','050','2014-2018','B01003_001E',500000,2000,%s)", (prior_r,))
        cur.execute("INSERT INTO acs_measure VALUES ('1','010','2019-2023','B19013_001E',75149,120,%s)", (acs_r,))
        cur.execute("INSERT INTO cbp_industry VALUES ('48491','050','2022','541940',210,3400,143850,NULL,%s)", (cbp_r,))
        cur.executemany(
            "INSERT INTO zbp_industry (geo_id, vintage, naics_code, establishments, ingest_run_id)"
            " VALUES (%s,'2022','541940',%s,%s)",
            [("78613", 5, zbp_r), ("78664", 2, zbp_r)],
        )


def _through_the_ladder(conn, *, place_covers_the_zcta: bool):
    """A listing taken from a city and a ZIP to its served `CommunityRow` through the REAL chain —
    `geocode.resolve` (the §11 ladder, no street, so the zcta rung), `catchment.build` and
    `materialize_listing` — and nothing hand-inserted in between."""
    _seed_ladder_world(conn, place_covers_the_zcta=place_covers_the_zcta)
    _clear_all(conn)
    # The active vintages come FIRST: `materialize_listing` refuses without them, which is its own
    # guard against materialising against nothing and is not this test's subject.
    active, registry = _seed_active_and_registry(conn)
    listing_id = make_listing(conn, city="Cedar Park", state="TX", zip="78613", street=None)

    location = geocode.resolve(conn, _geocoder(NOMATCH), listing_id)
    assert location.geo_precision == "zcta", "the rung this whole ruling is about"
    catchment.build(conn, listing_id, "2023")
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), listing_id)

    return listing_id, location, community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]


def test_a_wizard_listing_is_served_its_city_through_the_real_ladder(conn):
    """Controller ruling (fix round 1), proven END TO END in fix round 2 — because the fix-round-1
    test that claimed to prove it did not.

    That test seeded `geo_precision='zcta'` TOGETHER WITH a `place_geoid`, a combination the real
    `resolve()` could not produce: the zcta rung set no place at all. So it exercised the gate in
    `community_rows` and said nothing about the case, and the ruled behaviour — "a true city figure
    at the precision we hold" — actually produced four BLANK tiles for every listing it targeted,
    `materialize` having written no `place` band for a listing with no `ctx.place`.

    Nothing is hand-inserted here between the address and the answer: a listing with a city, a ZIP
    and NO street goes through `geocode.resolve` (which takes the zcta rung), `catchment.build` and
    `materialize_listing`, and `community_rows` is asked what a buyer would see.

    BOTH bands carry figures — that is what makes this a test of the ruling rather than of an empty
    catchment: without the `geo_precision` term the ring would win, and the assertion below would
    read the tracts' weighted numbers instead of the city's."""
    listing_id, location, row = _through_the_ladder(conn, place_covers_the_zcta=True)

    assert location.place_geoid == "4813552"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM market_metric WHERE listing_id=%s AND band='place'", (listing_id,))
        assert cur.fetchone()[0] > 0, "the ruling has nothing to serve without a place band"
        cur.execute("SELECT count(*) FROM market_metric WHERE listing_id=%s AND band='drive_10'", (listing_id,))
        assert cur.fetchone()[0] > 0, "...and nothing to CHOOSE between without a catchment band"

    # The CITY's own figures (level 160), not the ring's weighted tract sums.
    assert (row["pop"], row["hh"], row["income"]) == ("81,900", "27,600 households", "$118,400")
    # ...under the design's own wording, which is what "no new copy" means.
    assert row["label"] is None


def test_a_wizard_listing_in_no_place_has_no_area_figures_and_says_so(conn):
    """The honest other half, and the case the ladder must NOT paper over. A ZCTA centroid inside
    no place at all (unincorporated — D-C32's Orlando condition, one rung lower) resolves with
    `place_geoid` NULL rather than reaching for a place whose boundary does not contain it.

    The area group is then genuinely unavailable, and the payload says so the way it says every
    other absence: `null`, never a zero and never a ring relabelled as a city. Growth and payroll
    still arrive, from the county, because neither varies by band."""
    listing_id, location, row = _through_the_ladder(conn, place_covers_the_zcta=False)

    assert location.place_geoid is None
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM market_metric WHERE listing_id=%s AND band='place'", (listing_id,))
        assert cur.fetchone()[0] == 0, "no place, no place band — and that is correct"

    assert (row["pop"], row["hh"], row["income"], row["vets"]) == (None, None, None, None)
    assert row["label"] is None
    # Growth and payroll do not vary by band, so the county carries them (D12).
    assert row["growth"] is not None
    assert row["econ_k"] is not None


def test_a_rooftop_listing_keeps_its_catchment_and_its_label(conn):
    """The other half of the same ruling, and the reason it is scoped to precision rather than
    applied to everyone: a rooftop point IS the practice, so the ring around it is exactly what
    D-C38 put there and the sentence describing it is true. All twenty-nine QA demo hospitals
    carry a street and resolve at rooftop, so none of them moves.

    A listing with NO `practice_location` row at all is untouched by this too — the rule needs to
    KNOW the point is approximate, and an absent row says nothing. That case is already pinned by
    `test_the_area_figures_come_from_the_catchment_band_when_both_bands_have_them`, which seeds no
    location and asserts the catchment."""
    listing_id = make_listing(conn, city="Dallas", state="TX")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", metrics=_PLACE_SIX)
    _seed_band(conn, listing_id, "drive_10", metrics=_CATCHMENT_SIX)
    _seed_geography(conn, listing_id, place_geoid="4819000", place_name="Dallas", precision="rooftop")

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert (row["pop"], row["hh"], row["income"]) == ("369,569", "181,745 households", "$109,548")
    assert row["label"] == BAND_LABEL
