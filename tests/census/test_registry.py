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

# ---------------------------------------------------------------------------------------
# A38 fix round 1, review I1 / controller ruling (2026-09-13): a note that does not fit the
# approved design's row.
#
# The admin Data Sources tab prints `notes` VERBATIM into the Source column's sub-line -- no
# truncation and no clamping, by ruling: this is the platform's legal gate and hidden text is not
# an option there. So the fit has to be true of the DATA, and this is where it is made true.
#
# MEASURED, not chosen, in real Chromium at the design's own 1440x940 with the design's own three
# stylesheets, against the app's own markup (`frontend/src/App.vue`'s admin table, grid
# `1.1fr 1.6fr .8fr .8fr`, `gap: 20px`, row `padding: 16px 20px`, card `max-width: 1180px`):
#
#   * the Source column is **376 px** wide;
#   * the design's own five fixture rows are 75, 94, 75, 94 and 93 px tall, and the tallest of them
#     is **94 px** -- a 61 px Source cell, which is one line of `attribution_text` at 14 px plus
#     TWO lines of sub-line at 12.5 px/1.5;
#   * probing the composed sub-line at word lengths 4, 5, 6, 8, 10 and 12 characters, the first
#     length to need a THIRD line was 120 characters (five-letter words). **115** is the largest
#     that stayed on two lines for every mix probed, and that is the cap below. A second probe, at
#     word lengths 5 to 22 behind the registry's own longest `license_name`
#     ("CDLA-Permissive-2.0 (Foursquare-sourced rows: Apache-2.0)", 57 characters), put nothing
#     over two lines up to 120 either, so 115 is a floor under both.
#
# WHAT THIS CAP CANNOT FIX, recorded rather than implied: `attribution_text` is the Source cell's
# MAIN line and is legally verbatim (spec §12), so a long credit takes two or three lines of its
# own -- `overture_places`' 117-character credit renders three, and its row is 136 px whatever its
# note says. Measured after these migrations, every row's SUB-LINE is at most the design's own two
# lines and the tallest row is 136 px, against 226 px before (zbp). The rows still over 94 px are
# over it on a string no one may shorten.
#
# The sub-line is `license_name or "Licence not recorded"`, then ` · ` and the note, then
# ` · Terms drift flagged` while the quarterly sweep has the row flagged
# (`frontend/src/admin/data_sources.ts`'s own composition, restated here because this is a
# cross-language pin and there is no way to import it). The drift clause is counted only when the
# row actually carries the flag, as the tab renders it -- and it costs 22 characters, which is why
# the migrations leave headroom where a row can afford it.
#
# A character count is a PROXY for a wrap: the same 115 characters of longer words can still take a
# third line, which is why the probe took the worst mix rather than an average. It is the cap the
# ruling asked for, and it is the one thing a migration can be held to.
SOURCE_SUBLINE_CAP = 115
DRIFT_CLAUSE = " · Terms drift flagged"


def test_every_registry_note_fits_the_design_s_source_column(conn):
    """Every `dataset_registry.notes` value, after every migration, renders inside the approved
    design's own row height.

    RED before migrations 092 (rewritten) and 093: `zbp` carried a 458-character note that rendered
    226 px tall against the design's 94, with `practice_locations` at 187 px,
    `google_places_aggregate` at 190 px and six more over the design -- measured, on the real
    registry, in the browser."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT dataset_key, license_name, notes, drift_flagged FROM dataset_registry "
            "WHERE notes IS NOT NULL AND notes <> '' ORDER BY dataset_key"
        )
        rows = cur.fetchall()
    assert rows, "no registry row carries a note, so this pin measures nothing"
    over = []
    for key, license_name, notes, drift in rows:
        sub = f"{license_name or 'Licence not recorded'} · {notes}" + (DRIFT_CLAUSE if drift else "")
        if len(sub) > SOURCE_SUBLINE_CAP:
            over.append(f"{key}: {len(sub)} characters, {len(sub) - SOURCE_SUBLINE_CAP} over")
    assert not over, (
        "these registry notes do not fit the approved design's Source column "
        f"({SOURCE_SUBLINE_CAP} characters of sub-line, measured): " + "; ".join(over) +
        ". The tab prints notes verbatim by ruling, so shorten the note in a migration -- never the "
        "rendering."
    )
