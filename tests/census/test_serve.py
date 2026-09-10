"""Task B7: community_rows serves the six formatted Community Context fields (population,
growth, income, households, vets, econ_k) to the listing serialiser, with one batched query
per page and the same gate logic market.py uses to decide what a buyer may see.
"""
from __future__ import annotations

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
                listing_id_1, "place", "population", "2019-2023", 142300, "count", False, None, 500, False, None, "acs5",
            ),
        )

    active, registry = _seed_active_and_registry(conn)
    rows = community_rows(conn, [listing_id_1, listing_id_2], active=active, registry=registry)

    assert listing_id_1 in rows
    assert listing_id_2 not in rows  # Missing from dict, not present with nulls


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
