from app.census import registry as reg
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
# A38, review I1 (Source column) and F1 (Dataset column): a value that does not fit the approved
# design's row.
#
# The tab prints `notes`, `license_name`, `refresh_cadence` and the vintages VERBATIM -- no
# truncation and no clamping, by ruling, because this is the platform's legal gate and hidden text
# on it is not an option. So the fit is a property of the DATA, and this is where it is made true.
# Both caps and both vocabularies live in `app.census.registry` with their measurements, imported
# here so there is ONE copy; `scripts/measure_source_subline_cap.py` re-derives them in a real
# browser and fails if either has moved.
#
# A character count is a PROXY for a wrap: the same 115 characters of longer words can still take a
# third line, which is why each probe took the worst word mix rather than an average.
# ---------------------------------------------------------------------------------------


def _sublines(conn):
    """Every registry row as the tab composes its two sub-lines, from the database's own state.

    The Python here is `frontend/src/admin/data_sources.ts`'s composition restated -- a
    cross-language pin, the way `PILLS` and the attribution strings already are, because there is
    no way to import a TypeScript module into pytest. `data_sources.test.ts` pins the TypeScript
    side against the same strings."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT r.dataset_key, r.license_name, r.notes, r.license_url, r.refresh_cadence,
                      r.vintage, a.vintage, a.note,
                      (SELECT json_build_object('status', i.status, 'finished_at', i.finished_at, 'rows_written', i.rows_written)
                         FROM ingest_run i WHERE i.dataset_key = r.dataset_key ORDER BY i.id DESC LIMIT 1)
                 FROM dataset_registry r LEFT JOIN active_vintage a USING (dataset_key)
                ORDER BY r.dataset_key"""
        )
        rows = cur.fetchall()

    def real(v: str | None) -> str | None:
        return v if v is not None and v not in reg.PLACEHOLDER_VINTAGES else None

    out = []
    for key, name, notes, url, cadence, vintage, live_vintage, live_note, run in rows:
        source = [name or "Licence not recorded"]
        if notes:
            source.append(notes)
        # The sweep's own clause, counted for every row it CAN reach -- `license.py`'s
        # `WHERE license_url IS NOT NULL`. A row it can never flag never renders it.
        drift = reg.DRIFT_CLAUSE if url is not None else ""

        dataset = [cadence]
        declared, live = real(vintage), real(live_vintage)
        note = f" ({live_note})" if live_note else ""
        if live is not None:
            dataset.append((f"Declared {declared} · live {live}" if declared is not None and declared != live else f"Live vintage {live}") + note)
        elif live_note:
            dataset.append(live_note)
        dataset.append("Terms verified never")
        out.append((key, " · ".join(source) + drift, " · ".join(dataset), run))
    return out


def test_every_registry_note_fits_the_design_s_source_column(conn):
    """Every `dataset_registry.notes` value, after every migration, renders inside the approved
    design's own row height -- in the WORST state the quarterly sweep can put it in.

    RED before migrations 092 (rewritten) and 093: `zbp` carried a 458-character note that rendered
    226 px tall against the design's 94, with `practice_locations` at 187 px,
    `google_places_aggregate` at 190 px and six more over the design. RED again in fix round 2 with
    the drift clause counted (review F4): `google_places_aggregate` 137, `overture_places` 134,
    `zbp` 124, `osm_tiles` 119, `fsq_os_places` 116 -- five rows that fitted only until their terms
    page was edited, in an arm no test database could ever execute."""
    rows = _sublines(conn)
    assert rows, "no registry row was read, so this pin measures nothing"
    over = [
        f"{key}: {len(sub)} characters, {len(sub) - reg.SOURCE_SUBLINE_CAP} over"
        for key, sub, _dataset, _run in rows
        if len(sub) > reg.SOURCE_SUBLINE_CAP and key not in reg.LEGAL_NOTE_ROWS
    ]
    assert not over, (
        "these registry notes do not fit the approved design's Source column "
        f"({reg.SOURCE_SUBLINE_CAP} characters of sub-line, measured): " + "; ".join(over) +
        ". The tab prints notes verbatim by ruling, so shorten the note in a migration -- never the "
        "rendering."
    )


def test_the_legal_rows_are_the_only_ones_allowed_past_the_source_cap(conn):
    """The allow-list is an exception, and an exception nobody checks becomes a habit.

    Controller ruling F2 (2026-09-14): legally material text is never shortened to fit a layout, so
    `practice_locations` (the blocked 2017 Google Places export, plan D15, and the Google Maps
    Platform terms that forbid storing or rendering it) and `google_places_aggregate` (the SST
    §13.2 condition its block rests on) may wrap to a third line. This asserts they are the ONLY
    two, that both really are over the cap -- an allow-list entry for a row that fits is a licence
    nobody needs -- and that each still says the thing it is exempt for."""
    subs = {key: sub for key, sub, _d, _r in _sublines(conn)}
    assert set(reg.LEGAL_NOTE_ROWS) <= set(subs), "the allow-list names a dataset the registry does not hold"
    for key, reason in reg.LEGAL_NOTE_ROWS.items():
        assert len(subs[key]) > reg.SOURCE_SUBLINE_CAP, f"{key} fits the cap; it does not need an exception ({reason})"
    with conn.cursor() as cur:
        cur.execute("SELECT notes FROM dataset_registry WHERE dataset_key = 'practice_locations'")
        note = cur.fetchone()[0]
    # Plan D15's own sentence -- "The registry's `practice_locations` row names the file as blocked"
    # -- is true only while this row names it.
    assert "Report_Hospital_Competitor_All_US_ZipCode_FULL.csv" in note
    assert "Google Maps Platform Terms" in note and "forbid storing or rendering" in note
    with conn.cursor() as cur:
        cur.execute("SELECT notes FROM dataset_registry WHERE dataset_key = 'google_places_aggregate'")
        assert "SST §13.2" in cur.fetchone()[0]


def test_every_registry_row_fits_the_design_s_dataset_column(conn):
    """The Dataset sub-line, the same way (review F1).

    RED before this round: fix round 1's M6 pushed `Declared vintage <v>` on EVERY row --
    `dataset_registry.vintage` is NOT NULL -- so `acs5` composed
    `Annual (Dec) · Declared vintage 2019\u20132023 · Terms verified never`, and on a loaded row (QA has
    a completed run and a live vintage for every Census dataset) `Annual (Dec) · Loaded September
    2026 (85,381 rows) · Declared vintage 2019\u20132023 · Terms verified never` -- 102 characters,
    THREE lines, 112 px against the design's tallest 94, and four lines at 131 px with an
    activation note. The ruling names the live vintage only, the declared one only where it
    differs, and never a placeholder.

    WHAT THIS PIN CANNOT HOLD, recorded rather than implied: a COMPLETED LOAD adds about 35
    characters (`Loaded September 2026 (85,381 rows)`), and 73 of the cap's 78 are spent by that
    clause and `Terms verified …` alone -- so a loaded row that also names a live vintage is 98
    characters and takes a third line at this width whatever the vintage says. That is measured,
    it is the `overture_places` precedent one column over, and no cap can fix it without a
    restructure nobody has ruled. The pin therefore holds what the REGISTRY owns; the load clause
    is excluded and named here."""
    rows = _sublines(conn)
    over = [
        f"{key}: {len(sub)} characters, {len(sub) - reg.DATASET_SUBLINE_CAP} over"
        for key, _source, sub, _run in rows
        if len(sub) > reg.DATASET_SUBLINE_CAP
    ]
    assert not over, (
        "these Dataset sub-lines do not fit the approved design's Dataset column "
        f"({reg.DATASET_SUBLINE_CAP} characters, measured at 258 px): " + "; ".join(over)
    )


# The measured residue on the Dataset column, pinned so it cannot grow silently. `Loaded September
# 2026 (85,381 rows)` is 35 characters; with `Terms verified never` it is 73 of the cap's 78 on its
# own, so a loaded row that also names its live vintage is 98 and takes a third line at 258 px
# whatever the vintage says. The controller accepted and RECORDED that (the `overture_places`
# precedent on the Source column); fix round 1's own composition was 102, and 131 px with an
# activation note beside it.
LOADED_ACS5_DATASET_SUBLINE = 98


def test_a_loaded_row_is_the_one_measured_exception_on_the_dataset_column(conn):
    """The state QA is actually in, driven rather than reasoned about.

    Every Census dataset on QA has a completed `ingest_run` and an `active_vintage` row
    (`app/census/census_load.py` refuses to materialise without one), which is the state fix round
    1's `Declared vintage` clause pushed to FOUR lines. No test database has a run or an activation
    of its own, so this case makes one -- otherwise the arm the cap exists for is dead, which is
    exactly what review F4 caught in the drift clause.

    RED before the ruling: `Annual (Dec) · Loaded September 2026 (85,381 rows) · Declared vintage
    2019\u20132023 · Terms verified never`, 102 characters."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingest_run (dataset_key, vintage, status, started_at, finished_at, rows_written) "
            "VALUES ('acs5', '2019\u20132023', 'succeeded', now(), timestamptz '2026-09-20 00:00+00', 85381)"
        )
        cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by, note) VALUES ('acs5', '2019\u20132023', now(), 'census_load', NULL)")
    key, _source, dataset, run = next(r for r in _sublines(conn) if r[0] == "acs5")
    assert key == "acs5" and run is not None and run["status"] == "succeeded"
    # The tab composes the load clause between the cadence and the vintage
    # (`frontend/src/admin/data_sources.ts`); `_sublines` leaves it out so the cap above holds what
    # the REGISTRY owns, and it is put back here because this is the case that measures it.
    loaded = dataset.replace(
        "Annual (Dec) · ", f"Annual (Dec) · Loaded September 2026 ({run['rows_written']:,} rows) · ", 1
    )
    assert "Declared vintage" not in loaded
    assert loaded == "Annual (Dec) · Loaded September 2026 (85,381 rows) · Live vintage 2019\u20132023 · Terms verified never"
    assert len(loaded) == LOADED_ACS5_DATASET_SUBLINE, (
        f"the loaded Dataset sub-line is {len(loaded)} characters against the recorded "
        f"{LOADED_ACS5_DATASET_SUBLINE}; it is already past the {reg.DATASET_SUBLINE_CAP}-character "
        "two-line cap by ruling, and it may not grow further without one"
    )


def test_a_live_vintage_is_named_once_and_a_placeholder_never(conn):
    """The ruling's own three clauses, driven against the real registry rather than a fixture.

    `vintage` is NOT NULL (017:14) and holds `n/a`, `live`, `TBD` and `Current_Current` -- the
    Census Geocoder's benchmark identifier -- for datasets that have no vintage at all, so the
    clause the fix round added printed "Declared vintage n/a" on a blocked row."""
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, vintage FROM dataset_registry ORDER BY dataset_key")
        vintages = cur.fetchall()
    placeholders = [k for k, v in vintages if v in reg.PLACEHOLDER_VINTAGES]
    assert placeholders, "no registry row carries a placeholder vintage, so this pin measures nothing"
    for key, dataset_sub in ((k, d) for k, _s, d, _r in _sublines(conn)):
        assert "Declared vintage" not in dataset_sub, f"{key}: the retired fix-round-1 clause is back"
        if key in placeholders:
            assert "vintage" not in dataset_sub.lower(), f"{key} names a placeholder as a vintage: {dataset_sub!r}"


def test_the_refresh_cadence_vocabulary_is_017s_own(conn):
    """Review F7 / M9. `refresh_cadence` is free text and the tab prints it verbatim as the Dataset
    sub-line's first clause, so a second spelling of one cadence -- 092's original `Live tiles`
    beside 017's `live` -- reads as two different things on one table. 092 was corrected; this is
    the gate that was missing, and it reads the vocabulary from `app.census.registry` so the
    renderer's fixtures and the database cannot drift apart silently."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT refresh_cadence FROM dataset_registry ORDER BY 1")
        found = {row[0] for row in cur.fetchall()}
    assert found <= set(reg.REFRESH_CADENCES), (
        f"the registry holds a cadence outside 017's vocabulary: {sorted(found - set(reg.REFRESH_CADENCES))}"
    )
