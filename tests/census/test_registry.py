from app.census.registry import attribution, is_cleared, load

SPEC_KEYS = {"acs5", "acs5_subject", "acs5_prior", "cbp", "zbp", "qwi", "bds", "geocoder", "tiger_cb", "aies", "osm_tiles", "imagery", "pet_ownership", "practice_locations",
             "google_places_aggregate", "overture_places", "fsq_os_places",  # D16/D17 candidates, never ingested until cleared
             "esri_tiles", "esri_imagery"}  # A38 / controller ruling 17: the basemap the product ACTUALLY loads, registered so the tab's footer sentence is true of it

# The two strings `frontend/src/lib/leaflet.js` hands Leaflet as each layer's `attribution` today.
# Legally load-bearing (spec §12, CLAUDE.md "Attribution stays visible"), so they are pinned here
# by value AND pinned against that file in
# `tests/test_docs.py::test_the_esri_registry_rows_carry_the_attribution_the_map_actually_draws`.
ESRI_TILES_ATTRIBUTION = "Tiles \u00a9 Esri"
ESRI_IMAGERY_ATTRIBUTION = "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community"


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
    assert reg["zbp"].api_dataset_id == "2022/cbp" and reg["zbp"].naics_param == "NAICS2017" and reg["zbp"].license_status == "cleared"
    assert reg["practice_locations"].license_status == "blocked"  # spec §12: third-party practice-location data is out of scope for V1
    for k in ("google_places_aggregate", "overture_places", "fsq_os_places"):
        assert reg[k].license_status == "unresolved"  # D16/D17: candidates only; the gate keeps them out of every table and payload
    for k in ("acs5", "acs5_subject", "acs5_prior", "cbp", "qwi", "bds", "geocoder", "tiger_cb"):
        assert reg[k].license_status == "cleared" and reg[k].license_name == "Public domain"


def test_the_esri_basemap_is_registered_and_unresolved(conn):
    """A38, controller ruling 17 (2026-09-13). The product has loaded Esri tiles since the design
    was approved and `dataset_registry` had no row for either service — so the tab's own footer
    sentence ("No dataset reaches production until its license is recorded here") was false about
    the one dataset on every screen. Both rows are registered with the attribution the map draws
    TODAY, Esri's terms page, and `license_status = 'unresolved'`: clearing them is the VIN
    Foundation's decision under the one basemap decision record (the Census plan's "Basemap licence
    — one decision record"), never an implementer's, and `unresolved` is the truthful state until
    it is made. The imagery keeps shipping meanwhile — that is the ruling, and it is why the row
    has to exist and say so."""
    reg = load(conn)
    for key in ("esri_tiles", "esri_imagery"):
        assert reg[key].license_status == "unresolved", key
        assert reg[key].license_url == "https://www.esri.com/en-us/legal/terms/master-agreement", key
        assert reg[key].cleared is False, key
        # The notes say WHOSE decision is outstanding, so the row cannot be read as an oversight.
        assert "VIN Foundation" in reg[key].notes, key
    assert reg["esri_tiles"].attribution_text == ESRI_TILES_ATTRIBUTION
    assert reg["esri_imagery"].attribution_text == ESRI_IMAGERY_ATTRIBUTION


def test_registering_esri_did_not_clear_or_move_the_basemap_rows_already_there(conn):
    """A38: two rows were ADDED; none was edited. `osm_tiles` is the Census analytical basemap
    (CARTO) A-C1 ruled on and `imagery` is the spec's own vendor-TBD satellite row — both are still
    exactly what 017 seeded, so this migration cannot be read as having resolved the open basemap
    licence question by moving a status."""
    reg = load(conn)
    assert reg["osm_tiles"].license_status == "cleared" and reg["osm_tiles"].license_name == "ODbL 1.0"
    assert reg["imagery"].license_status == "unresolved"


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
