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
    _seed_band(conn, listing_id, "drive_10")

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["label"] == _BAND_LABEL
    assert row["pop"] == "167,997"
    assert row["hh"] == "59,588 households"
    assert row["income"] == "$69,780"
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
    _seed_band(conn, listing_id, "drive_10")

    active, registry = _seed_active_and_registry(conn)
    row = community_rows(conn, [listing_id], active=active, registry=registry)[listing_id]

    assert row["label"] == _BAND_LABEL
    assert row["pop"] == "167,997"
    assert row["vets"] == 10
    # `_SIX`'s median is seeded place-shaped (`is_derived=False`) in BOTH bands, so no qualifier
    # is added — the note follows the figure's own row, never the band it was read from.
    assert row["income_note"] is None


def test_place_rows_from_an_uncleared_dataset_fall_back_to_drive_10(conn):
    """The licence-gate case, and it is not hypothetical: place rows stamped with a dataset the
    VIN Foundation has not cleared are six nulls, and the complete `drive_10` band answers."""
    listing_id = make_listing(conn, city="Orlando", state="FL", zip="32819")
    _clear_all(conn)
    _seed_band(conn, listing_id, "place", source_dataset="acs5")
    _seed_band(conn, listing_id, "drive_10")
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
# with no MOE (`materialize.py:210`, `:241` — a catchment median is a household-weighted average
# of tract medians, never a published one, and can never be suppressed).
# ---------------------------------------------------------------------------------------------

_BAND_LABEL = "Within about 5 miles of the practice"

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


def _seed_geography(conn, listing_id, *, place_geoid=None, place_name=None, county_geoid=None, county_name=None):
    """The listing's geocoded place and county, and the `geo_area` rows that NAME them.

    D-C38 supersedes `serve.py`'s own "There is no geoid lookup and none is wanted": the Growth
    tile needs the name of the geography its figure was measured at, which is
    `practice_location.place_geoid` joined to `geo_area.name` at summary level 160 (or
    `county_geoid` at 050). `tiger_cb`'s active vintage is what picks the boundary edition, the
    same vintage `materialize.py` builds catchments against."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO practice_location (listing_id, address_hash, county_geoid, place_geoid, geo_precision, geocoded_at, geocoder_vintage) "
            "VALUES (%s, 'h', %s, %s, 'rooftop', now(), 'Current_Current')",
            (listing_id, county_geoid, place_geoid),
        )
        for geo_id, level, name in ((place_geoid, "160", place_name), (county_geoid, "050", county_name)):
            if geo_id is not None:
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
    """A ring median is a household-weighted average of the tract medians inside it, never a
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
    """D-C38's whole point on the Growth tile: the figure stays the City of Dallas — it exists at
    no finer geography until the 2010->2020 tract crosswalk is loaded (a registered Phase C
    deferral) — and `growth_scope` says so, beside a population that IS the ring's."""
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
    assert row["growth_scope"] == "City of Dallas"


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
