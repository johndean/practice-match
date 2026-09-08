from app.census.registry import attribution, is_cleared, load

SPEC_KEYS = {"acs5", "acs5_subject", "acs5_prior", "cbp", "zbp", "qwi", "bds", "geocoder", "tiger_cb", "aies", "osm_tiles", "imagery", "pet_ownership", "practice_locations",
             "google_places_aggregate", "overture_places", "fsq_os_places"}  # last three: D16/D17 candidates, never ingested until cleared


def test_seed_matches_the_spec_dataset_register(conn):
    reg = load(conn)
    assert set(reg) == SPEC_KEYS
    assert reg["acs5"].api_dataset_id == "2023/acs/acs5" and reg["acs5"].vintage == "2019\u20132023"
    assert reg["acs5_prior"].api_dataset_id == "2018/acs/acs5"
    assert reg["cbp"].api_dataset_id == "2022/cbp" and reg["cbp"].naics_param == "NAICS2017"
    assert reg["qwi"].api_dataset_id == "timeseries/qwi/sa"
    assert reg["imagery"].license_status == "unresolved"
    assert reg["pet_ownership"].license_status == "blocked"
    assert reg["aies"].license_status == "unresolved"  # "Verify ID" in the spec → not cleared until confirmed
    assert reg["zbp"].api_dataset_id == "2022/zbp" and reg["zbp"].naics_param == "NAICS2017" and reg["zbp"].license_status == "cleared"
    assert reg["practice_locations"].license_status == "blocked"  # spec §12: third-party practice-location data is out of scope for V1
    for k in ("google_places_aggregate", "overture_places", "fsq_os_places"):
        assert reg[k].license_status == "unresolved"  # D16/D17: candidates only; the gate keeps them out of every table and payload
    for k in ("acs5", "acs5_subject", "acs5_prior", "cbp", "qwi", "bds", "geocoder", "tiger_cb"):
        assert reg[k].license_status == "cleared" and reg[k].license_name == "Public domain"


def test_is_cleared_and_attribution(conn):
    assert is_cleared(conn, "acs5") is True
    assert is_cleared(conn, "pet_ownership") is False
    assert is_cleared(conn, "nope") is False
    assert attribution(conn, ["acs5", "cbp"]) == [
        "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019\u20132023",
        "Source: U.S. Census Bureau, County Business Patterns, 2022",
    ]


def test_attribution_skips_unknown_keys_and_empty_list_short_circuits(conn):
    # docstring: "unknown keys are skipped, not invented" — exercise both arms of that filter.
    assert attribution(conn, ["acs5", "nope"]) == [
        "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019\u20132023",
    ]
    assert attribution(conn, []) == []


def test_dataset_cleared_property_reflects_license_status(conn):
    reg = load(conn)
    assert reg["acs5"].cleared is True
    assert reg["pet_ownership"].cleared is False
