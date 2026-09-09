"""Materialisation into `market_metric` (plan Task B4b: spec §7/§8/§14, plan D9-D12). Builds on
`app.census.metrics` (pure maths, merged in B4a) and `app.census.catchment` (B3) to turn a
listing's location and catchments into the three-band rows a buyer's market panel reads.

Carries three corrections from B4a's review (A-C17), each proven here rather than in
`test_metrics.py` because they are the MATERIALISATION's responsibility, not the formulas':
`test_estimates_without_a_margin_of_error_are_suppressed_as_unmeasured` (an estimate with no MOE
must never be combined as though it were certain), and the delete-before-upsert and
nanosecond-version-stamp tests below (pre-flight corrections, A-C19)."""

from __future__ import annotations

import fakeredis
import pytest

from app.census import catchment, materialize
from tests.census.listing_fixtures import make_listing

PLACE = "POLYGON((-97.90 30.50,-97.70 30.50,-97.70 30.60,-97.90 30.60,-97.90 30.50))"  # covers both tracts and both ZCTAs


@pytest.fixture
def world(conn):
    """Two tracts, two ZCTAs, a place, a county, the nation; both ACS vintages; CBP; ZBP; active
    vintages; one geocoded listing."""
    lid = make_listing(conn)
    with conn.cursor() as cur:
        for i, gid in enumerate(["48491000001", "48491000002"]):
            x0 = -97.90 + 0.1 * i
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom) "
                "VALUES (%s,'140','2023',%s,'48','491','48491', ST_Multi(ST_GeomFromText(%s,4269)))",
                (gid, gid, f"POLYGON(({x0} 30.50,{x0+0.1} 30.50,{x0+0.1} 30.60,{x0} 30.60,{x0} 30.50))"),
            )
        for i, z in enumerate(["78613", "78664"]):
            x0 = -97.90 + 0.1 * i
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom) VALUES (%s,'860','2023',%s, ST_Multi(ST_GeomFromText(%s,4269)))",
                (z, z, f"POLYGON(({x0} 30.50,{x0+0.1} 30.50,{x0+0.1} 30.60,{x0} 30.60,{x0} 30.50))"),
            )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES "
            "('4813552','160','2023','Cedar Park city','48', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.80,30.55,4269))",
            (PLACE,),
        )
        cur.execute(
            "INSERT INTO ingest_run (dataset_key, vintage, started_at, status) VALUES "
            "('acs5','2019\u20132023',now(),'succeeded'),('acs5_prior','2014\u20132018',now(),'succeeded'),"
            "('cbp','2022',now(),'succeeded'),('zbp','2022',now(),'succeeded')"
        )
        cur.execute("SELECT id FROM ingest_run ORDER BY id")
        r1, r2, r3, r4 = [x[0] for x in cur.fetchall()]
        tracts = [
            ("48491000001", "B01003_001E", 4000, 200), ("48491000001", "B11001_001E", 1500, 95), ("48491000001", "B19013_001E", 118400, 9100),
            ("48491000002", "B01003_001E", 3000, 300), ("48491000002", "B11001_001E", 1200, 80), ("48491000002", "B19013_001E", 98000, 12000),
        ]
        cur.executemany("INSERT INTO acs_measure VALUES (%s,'140','2019\u20132023',%s,%s,%s,%s)", [(g, v, e, mo, r1) for g, v, e, mo in tracts])
        cur.executemany(
            "INSERT INTO acs_measure VALUES ('4813552','160','2019\u20132023',%s,%s,%s,%s)",
            [("B01003_001E", 81900, 900, r1), ("B11001_001E", 27600, 600, r1), ("B19013_001E", 118400, 4100, r1)],
        )
        cur.execute("INSERT INTO acs_measure VALUES ('4813552','160','2014\u20132018','B01003_001E',71716,850,%s)", (r2,))
        cur.execute("INSERT INTO acs_measure VALUES ('1','010','2019\u20132023','B19013_001E',75149,120,%s)", (r1,))
        cur.execute("INSERT INTO cbp_industry VALUES ('48491','050','2022','541940',210,3400,143850,NULL,%s)", (r3,))  # county benchmark: 210 practices
        cur.execute("INSERT INTO acs_measure VALUES ('48491','050','2019\u20132023','B11001_001E',230000,1200,%s)", (r1,))  # county households for apportionment
        cur.executemany(
            "INSERT INTO zbp_industry (geo_id, vintage, naics_code, establishments, ingest_run_id) VALUES (%s,'2022','541940',%s,%s)",
            [("78613", 5, r4), ("78664", 2, r4)],
        )
        cur.executemany(
            "INSERT INTO active_vintage VALUES (%s,%s,now(),'test')",
            [("acs5", "2019\u20132023"), ("acs5_prior", "2014\u20132018"), ("cbp", "2022"), ("zbp", "2022"), ("tiger_cb", "2023")],
        )
        cur.execute(
            "INSERT INTO practice_location (listing_id, address_hash, point, tract_geoid, county_geoid, place_geoid, geo_precision, geocoded_at, geocoder_vintage) "
            "VALUES (%s,'h', ST_SetSRID(ST_Point(-97.85,30.55),4269), '48491000001','48491','4813552','rooftop',now(),'Current_Current')",
            (lid,),
        )
    catchment.build(conn, lid, "2023")
    return lid


def _metric(conn, lid, key, band="drive_10"):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT value_num::float, unit, is_derived, formula_version, moe::float, suppressed, suppress_reason, source_dataset, vintage, inputs "
            "FROM market_metric WHERE listing_id=%s AND band=%s AND metric_key=%s",
            (lid, band, key),
        )
        return cur.fetchone()


def _weights(conn, lid, band, level):
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id, overlap_frac::float FROM practice_catchment WHERE listing_id=%s AND band=%s AND summary_level=%s", (lid, band, level))
        return dict(cur.fetchall())


def test_place_band_reproduces_the_design_style_city_figures(conn, world):
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    assert _metric(conn, world, "population", "place")[0] == 81900
    assert _metric(conn, world, "households", "place")[0] == 27600
    assert _metric(conn, world, "median_hh_income", "place")[0] == 118400 and _metric(conn, world, "median_hh_income", "place")[2] is False  # a real median, not approximate
    g = _metric(conn, world, "population_growth_pct", "place")
    assert g[0] == pytest.approx(14.2, abs=0.01) and g[9]["geo_level"] == "place" and g[9]["acs5_prior"] == "2014\u20132018"
    est = _metric(conn, world, "establishments", "place")
    # Both ZCTAs lie fully inside the place polygon, but PostGIS's ellipsoidal geography area
    # (`_PLACE_ZCTA_SQL`'s `ST_Area(...::geography)`) is not exact integration -- each ZCTA's own
    # overlap_frac against the place comes back ~0.999808, not precisely 1.0, even though the two
    # boundaries share the identical coordinates on that edge. 5*0.999808 + 2*0.999808 = 6.99866,
    # not 7 -- a real database's geometry engine, not a materialisation bug (measured directly
    # against this fixture's own coordinates before loosening this assertion).
    assert est[0] == pytest.approx(7, rel=1e-3) and est[7] == "zbp" and est[9]["geo_level"] == "zcta" and est[9]["zctas"] == 2
    # Same-geography consistency (C1): derived from the ACTUAL establishments figure just
    # asserted above, not the idealised "7", so this assertion is not vulnerable to the same
    # geography-engine rounding and can stay tight.
    assert _metric(conn, world, "vets_per_10k_households", "place")[0] == pytest.approx(est[0] / 2.76, rel=1e-6)
    assert _metric(conn, world, "opportunity_score", "place")[0] == 50


def test_catchment_bands_aggregate_tracts_and_zctas_coherently(conn, world):
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    wt = _weights(conn, world, "drive_10", "140")
    wz = _weights(conn, world, "drive_10", "860")
    exp_pop = 4000 * wt["48491000001"] + 3000 * wt["48491000002"]
    exp_hh = 1500 * wt["48491000001"] + 1200 * wt["48491000002"]
    exp_estab = 5 * wz["78613"] + 2 * wz.get("78664", 0)
    assert _metric(conn, world, "population")[0] == pytest.approx(exp_pop, rel=1e-6)
    inc = _metric(conn, world, "median_hh_income")
    assert inc[2] is True and inc[3] == "v1"  # catchment median is an approximation -> labelled derived
    est = _metric(conn, world, "establishments")
    assert est[0] == pytest.approx(exp_estab, rel=1e-6) and est[9]["geo_level"] == "zcta"
    assert _metric(conn, world, "vets_per_10k_households")[0] == pytest.approx(exp_estab / (exp_hh / 10000), rel=1e-6)  # same geography top and bottom (C1)
    g = _metric(conn, world, "population_growth_pct")
    assert g[0] == pytest.approx(14.2, abs=0.01) and g[9]["geo_level"] == "place"  # growth is place-level for every band (D12)
    rev = _metric(conn, world, "revenue_per_establishment")
    assert rev[0] == pytest.approx(143850 * 1000 / 210) and rev[7] == "cbp" and rev[9]["geo_level"] == "county"
    assert _metric(conn, world, "opportunity_score")[9]["components"].keys() == {"income", "growth", "vets_per_10k"}


def test_high_moe_suppresses_the_value_and_its_derivatives(conn, world):
    with conn.cursor() as cur:
        cur.execute("UPDATE acs_measure SET moe = 900 WHERE variable='B11001_001E' AND summary_level='140'")  # CV ~ 0.36 on catchment households
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    hh = _metric(conn, world, "households")
    assert hh[5] is True and hh[6] == "high_moe" and hh[0] is not None  # row kept, flagged (§14)
    pets = _metric(conn, world, "pet_households_est")
    assert pets[5] is True and pets[6] == "input_suppressed"


def test_without_zbp_competition_falls_back_to_labelled_county_apportionment(conn, world):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='zbp'")
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    est = _metric(conn, world, "establishments", "place")
    assert est[7] == "cbp" and est[2] is True and est[9]["method"] == "county_apportioned"
    assert est[0] == pytest.approx(210 * 27600 / 230000)  # county establishments x place households / county households


def test_uncleared_cbp_and_zbp_leave_no_competition_rows(conn, world):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key IN ('cbp','zbp')")
    n = materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    assert n == 3 * 6  # per band: population, households, median income, growth, pets, income index -- no establishments/per10k/payroll/score
    assert _metric(conn, world, "establishments") is None and _metric(conn, world, "opportunity_score") is None


# ---- carried from B4a's review (A-C17 (1)): an estimate with no MOE is unmeasured, not certain --


def test_estimates_without_a_margin_of_error_are_suppressed_as_unmeasured(conn, world):
    """A present ACS estimate whose `moe` is `NULL` is the MOST confident-looking row possible
    (`cv()` returns `None`, and the old `high_moe()`-only check reads `None` as "not high") --
    exactly backwards from the suppress-under-uncertainty rule §14 exists to enforce. This is the
    materialisation's own guard, not a formula (metrics.py's signatures are unchanged): a missing
    MOE is suppressed with its own reason, `no_moe`, distinct from `high_moe`, and the value
    itself is still stored (the row is kept, per §14) rather than discarded."""
    with conn.cursor() as cur:
        cur.execute("UPDATE acs_measure SET moe = NULL WHERE geo_id='4813552' AND variable IN ('B11001_001E','B19013_001E')")
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    hh = _metric(conn, world, "households", "place")
    assert hh[0] == 27600 and hh[4] is None and hh[5] is True and hh[6] == "no_moe"
    inc = _metric(conn, world, "median_hh_income", "place")
    assert inc[0] == 118400 and inc[4] is None and inc[5] is True and inc[6] == "no_moe" and inc[2] is False  # still a real median, just unmeasured-flagged
    pets = _metric(conn, world, "pet_households_est", "place")
    assert pets[5] is True and pets[6] == "input_suppressed"  # cascades, same as high_moe already does
    pop = _metric(conn, world, "population", "place")
    assert pop[5] is False  # population's own MOE is untouched


# ---- pre-flight corrections (A-C19): delete-before-upsert, nanosecond version stamp -----------


def test_materialize_replaces_the_prior_vintage_generation_rather_than_leaving_two(conn, world):
    """The UPSERT keys on (listing_id, band, metric_key, vintage) -- when the active acs5 vintage
    changes, the new vintage is a DIFFERENT primary key, so `ON CONFLICT` alone would leave the
    OLD vintage's row sitting beside the new one. `materialize_listing` must delete a band's rows
    before rewriting it so a vintage change cannot leave two generations of one metric in one
    band."""
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO ingest_run (dataset_key, vintage, started_at, status) VALUES ('acs5','2024\u20132028',now(),'succeeded')")
        cur.execute("SELECT id FROM ingest_run WHERE dataset_key='acs5' AND vintage='2024\u20132028'")
        (run_id,) = cur.fetchone()
        for var, est, moe in [("B01003_001E", 90000, 1000), ("B11001_001E", 30000, 700), ("B19013_001E", 130000, 5000)]:
            cur.execute("INSERT INTO acs_measure VALUES ('4813552','160','2024\u20132028',%s,%s,%s,%s)", (var, est, moe, run_id))
        cur.execute("UPDATE active_vintage SET vintage='2024\u20132028' WHERE dataset_key='acs5'")
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    with conn.cursor() as cur:
        cur.execute("SELECT vintage, value_num::float FROM market_metric WHERE listing_id=%s AND band='place' AND metric_key='population'", (world,))
        rows = cur.fetchall()
    assert rows == [("2024\u20132028", 90000.0)]


def test_version_stamp_uses_nanosecond_resolution_so_two_runs_in_one_second_differ(conn, world, monkeypatch):
    """The brief's own illustrative `int(time.time())` truncates to whole seconds: two
    materialisations inside the same wall-clock second would stamp the SAME version, and a client
    caching on that version would keep serving stale figures after the second run. Proven
    deterministically by pinning `time.time_ns` to two values that fall inside one whole second."""
    ticks = iter([1_700_000_000_100_000_000, 1_700_000_000_100_000_001])
    monkeypatch.setattr(materialize.time, "time_ns", lambda: next(ticks))
    r = fakeredis.FakeRedis()

    materialize.materialize_listing(conn, r, world)
    v1 = r.get(f"listing:{world}:market:version")
    materialize.materialize_listing(conn, r, world)
    v2 = r.get(f"listing:{world}:market:version")

    assert v1 != v2
    assert int(v1) == 1_700_000_000_100_000_000
    assert int(v2) == 1_700_000_000_100_000_001


# ---- branch coverage: growth resolution, and the competition fallback's own edges -------------


def test_growth_stays_none_when_no_geography_yields_a_prior_population(conn):
    """`_Ctx.__init__`'s growth-resolution loop tries `("160", place)` then `("050", county)`,
    breaking on the first geography that yields a growth figure. A listing with a place but no
    county, and place data for the acs5 vintage but none for acs5_prior, exercises all three
    branches no other test here reaches: the place iteration computes a real `now`/`prior` pair
    but `g` comes back `None` (loop back to the top rather than break), the county iteration has
    no `gid` at all (`continue`), and the loop then exhausts both tuple entries without ever
    breaking. `population_growth_pct` is absent from the place band as a result."""
    lid = make_listing(conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES "
            "('4813552','160','2023','Cedar Park city','48', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.80,30.55,4269))",
            (PLACE,),
        )
        cur.execute(
            "INSERT INTO ingest_run (dataset_key, vintage, started_at, status) VALUES ('acs5','2019\u20132023',now(),'succeeded')"
        )
        cur.execute("SELECT id FROM ingest_run WHERE dataset_key='acs5'")
        (run_id,) = cur.fetchone()
        cur.execute("INSERT INTO acs_measure VALUES ('4813552','160','2019\u20132023','B01003_001E',50000,500,%s)", (run_id,))
        # No acs5_prior row at all for the place: `now`/`prior` resolve but `prior` is None, so
        # `population_growth_pct` returns None -- the place iteration does not break.
        cur.executemany(
            "INSERT INTO active_vintage VALUES (%s,%s,now(),'test')",
            [("acs5", "2019\u20132023"), ("acs5_prior", "2014\u20132018"), ("tiger_cb", "2023")],
        )
        cur.execute(
            "INSERT INTO practice_location (listing_id, address_hash, point, place_geoid, geo_precision, geocoded_at, geocoder_vintage) "
            "VALUES (%s,'h', ST_SetSRID(ST_Point(-97.80,30.55),4269), '4813552','rooftop',now(),'Current_Current')",
            (lid,),
        )
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), lid)
    assert _metric(conn, lid, "population", "place")[0] == 50000
    assert _metric(conn, lid, "population_growth_pct", "place") is None


def test_zbp_returning_no_usable_estimate_falls_back_to_county_apportionment(conn, world):
    """`_competition`'s ZBP branch can be ENTERED (the dataset is cleared and the band has ZCTA
    weights) and still come back with no usable estimate -- every ZCTA in the catchment simply
    has no `zbp_industry` row for this vintage -- which is a different path than
    `test_without_zbp_competition_falls_back_to_labelled_county_apportionment` above (there, the
    dataset itself is unresolved, so the ZBP branch is never entered at all)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM zbp_industry")
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    est = _metric(conn, world, "establishments", "place")
    assert est[7] == "cbp" and est[2] is True and est[9]["method"] == "county_apportioned"


def test_cbp_apportionment_skips_when_the_establishment_count_itself_is_census_suppressed(conn, world):
    """The CBP fallback's own `estab is not None` guard: Census can suppress a noise-flagged
    establishment count to NULL (`cbp_industry.establishments`) even on a row that otherwise
    exists and is licence-cleared. Combined with no ZBP data (as above), `_competition` returns
    `None` outright -- a different reason than the licence-gate case
    `test_uncleared_cbp_and_zbp_leave_no_competition_rows` already covers."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM zbp_industry")
        cur.execute("UPDATE cbp_industry SET establishments = NULL WHERE naics_code='541940'")
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    assert _metric(conn, world, "establishments", "place") is None
    assert _metric(conn, world, "opportunity_score", "place") is None


def test_competition_from_zbp_without_a_cleared_cbp_skips_revenue_but_keeps_opportunity_score(conn, world):
    """`revenue_per_establishment` is gated on `ctx.cbp` (a real CBP row), independently of which
    source `_competition` actually used. With `cbp` unresolved, `ctx.cbp` is `None` even though
    ZBP alone resolves `establishments` just fine -- the revenue figure is skipped, but
    `opportunity_score` (which needs only income/growth/vets-per-10k, none of them CBP-specific)
    is not."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='cbp'")
    materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    est = _metric(conn, world, "establishments", "place")
    assert est[7] == "zbp"
    assert _metric(conn, world, "revenue_per_establishment", "place") is None
    assert _metric(conn, world, "opportunity_score", "place") is not None


# ---- structural edges: no location, no active vintages ----------------------------------------


def test_materialize_listing_with_no_location_writes_nothing(conn):
    """A listing that has not been geocoded yet has no `practice_location` row and no catchments
    -- every band's inputs come back empty, so nothing is written and nothing crashes."""
    lid = make_listing(conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingest_run (dataset_key, vintage, started_at, status) VALUES ('acs5','2019\u20132023',now(),'succeeded')"
        )
        cur.execute(
            "INSERT INTO active_vintage VALUES ('acs5','2019\u20132023',now(),'test'), ('tiger_cb','2023',now(),'test')"
        )
    n = materialize.materialize_listing(conn, fakeredis.FakeRedis(), lid)
    assert n == 0
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM market_metric WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 0


def test_materialize_listing_requires_an_active_acs5_and_tiger_cb_vintage(conn):
    lid = make_listing(conn)
    with pytest.raises(RuntimeError):
        materialize.materialize_listing(conn, fakeredis.FakeRedis(), lid)


def test_materialize_all_returns_empty_dict_when_no_listing_has_a_location(conn):
    assert materialize.materialize_all(conn, fakeredis.FakeRedis()) == {}


def test_materialize_all_materialises_every_geocoded_listing(conn, world):
    n = materialize.materialize_listing(conn, fakeredis.FakeRedis(), world)
    counts = materialize.materialize_all(conn, fakeredis.FakeRedis())
    assert counts == {world: n}


# ---- active_geo_vintage: how app.tasks.census reaches the active vintage without importing -----
# app.census.vintage directly (a committed AST guard walks every module under app/tasks/ and
# fails on that import, however indirect the need -- A-C15 (9)).


def test_active_geo_vintage_returns_the_active_tiger_cb_vintage(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO active_vintage VALUES ('tiger_cb','2023',now(),'test')")
    assert materialize.active_geo_vintage(conn) == "2023"


def test_active_geo_vintage_raises_without_one(conn):
    with pytest.raises(RuntimeError):
        materialize.active_geo_vintage(conn)
