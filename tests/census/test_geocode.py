"""Task B2 (spec §2 geocoder, §6 resolution order, §10 365-day cache, §11 fallbacks):
`app/census/geocode.py`'s client, address cache and fallback ladder, plus the
`census.geocode_listing` Celery task registered in `app/tasks/census.py`.

`tests/census/fixtures/geocoder_match.json` and `geocoder_nomatch.json` are REAL recorded
responses (controller amendment A-C15 correction 4 -- "a parser proved against an invented
shape proves nothing"), captured 2026-09-09 with a keyless, read-only GET against
`https://geocoding.geo.census.gov/geocoder/geographies/address` -- no ingestion, exactly the
shape-discovery act A-C13 (1) permits. MATCH is `450 Cypress Creek Rd, Cedar Park, TX 78613`
(Cedar Park City Hall); NOMATCH is a nonsense address. Both carry the `addressComponents` and
`tigerLine` blocks the brief's own invented fixture omitted, and MATCH's real GEOIDs (Census
Tract 203.55, Williamson County, Cedar Park city, ZCTA 78613, the Austin-Round Rock-San Marcos
CBSA) are what `_seed_geo` below seeds `geo_area` with, so the ladder's rooftop rung and its
ZCTA/place fallback rungs describe the same real place throughout.

Six correction-driven additions beyond the brief's own six tests (A-C15 correction 7: "six tests
will not reach the gate"): `_first_geoid`'s three parser guards tested directly, the mapping
drift test correction 2 asks for, a test that a stale/absent `active_vintage` row for `tiger_cb`
refuses cleanly, a test that an unruled state (outside `STATE_FIPS`) never reaches the place
query, a cached-nomatch test (the brief's own cache test only ever caches a MATCH), and a
tract-not-rooftop precision test (a match whose geographies carry no Census Tracts layer) --
plus three tests of the task itself, which the brief's file list never separately tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.census import geocode
from app.census.states import STATES as _STATES
from app.tasks import census as CT
from app.tasks.celery_app import celery_app
from tests.census.listing_fixtures import make_listing

FIX = Path(__file__).parent / "fixtures"
MATCH = json.loads((FIX / "geocoder_match.json").read_text())
NOMATCH = json.loads((FIX / "geocoder_nomatch.json").read_text())

CONTACT = "tech@vinfoundation.example.org"


def _geocoder(payload, seen=None):
    def handler(r):
        if seen is not None:
            seen.append(str(r.url))
        return httpx.Response(200, json=payload)

    return geocode.Geocoder(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "https://geocoding.geo.census.gov/geocoder",
        "PracticeMatch (test)",
    )


def _seed_geo(conn):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid) VALUES
                 ('48491020355','140','2023','Census Tract 203.55','48','491','48491',
                  ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)),
                  ST_SetSRID(ST_MakePoint(-97.8,30.55),4269)),
                 ('78613','860','2023','ZCTA5 78613',NULL,NULL,NULL,
                  ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)),
                  ST_SetSRID(ST_MakePoint(-97.8,30.55),4269)),
                 ('4813552','160','2023','Cedar Park city','48',NULL,'48',
                  ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)),
                  ST_SetSRID(ST_MakePoint(-97.8,30.55),4269))"""
        )
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)",
            ("tiger_cb", "2023", "test"),
        )


def _seed_county(conn, geo_id, state_fips, county_fips, name, polygon_wkt, centroid):
    lng, lat = centroid
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid)
               VALUES (%s, '050', '2023', %s, %s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4269)), ST_SetSRID(ST_MakePoint(%s, %s), 4269))""",
            (geo_id, name, state_fips, county_fips, state_fips, polygon_wkt, lng, lat),
        )


def _seed_zcta(conn, geo_id, polygon_wkt, centroid):
    """A standalone ZCTA -- unlike `_seed_geo`'s 78613, no tract polygon covers this one, by
    construction: its centroid sits outside `_seed_geo`'s square but inside `_seed_county`'s."""
    lng, lat = centroid
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid)
               VALUES (%s, '860', '2023', %s, NULL, NULL, NULL, ST_Multi(ST_GeomFromText(%s, 4269)), ST_SetSRID(ST_MakePoint(%s, %s), 4269))""",
            (geo_id, f"ZCTA5 {geo_id}", polygon_wkt, lng, lat),
        )


# A county square large enough to contain BOTH `_seed_geo`'s square ((-97.9,30.5)-(-97.7,30.6))
# AND `_ZCTA_NO_TRACT`'s centroid below, so 48491 (Williamson) is the SAME county geoid whether
# reached through a tract's own `parent_geo_id` (the "zcta" rung) or the standalone spatial join
# (the "county" rung) -- one consistent place throughout the ladder-order test.
_COUNTY_SQUARE = "POLYGON((-99.0 30.0,-97.0 30.0,-97.0 31.0,-99.0 31.0,-99.0 30.0))"
_ZCTA_NO_TRACT_GEOID = "78610"
_ZCTA_NO_TRACT_POLY = "POLYGON((-98.6 30.1,-98.4 30.1,-98.4 30.3,-98.6 30.3,-98.6 30.1))"
_ZCTA_NO_TRACT_CENTROID = (-98.5, 30.2)  # inside _COUNTY_SQUARE, outside _seed_geo's tract square


class _RecordingCursor:
    """Wraps a real psycopg2 cursor, recording the (whitespace-collapsed) text of every SQL
    statement executed through it -- used to prove a query never ran at all, not just that the
    overall outcome matches what an ungated query would also happen to produce."""

    def __init__(self, real, executed):
        self._real, self._executed = real, executed

    def execute(self, sql, params=None):
        self._executed.append(" ".join(sql.split()))
        return self._real.execute(sql, params)

    def fetchone(self):
        return self._real.fetchone()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._real.close()
        return False


class _RecordingConn:
    def __init__(self, real):
        self._real = real
        self.executed = []

    def cursor(self):
        return _RecordingCursor(self._real.cursor(), self.executed)


# ---- normalize / address_hash --------------------------------------------------------------


def test_normalize_is_case_and_punctuation_insensitive():
    a = geocode.normalize("1 Main St.", "Cedar Park", "tx", "78613")
    b = geocode.normalize("1  MAIN ST", " cedar park ", "TX", "78613-1234")
    assert a == b == "1 main st|cedar park|tx|78613"
    assert len(geocode.address_hash(a)) == 64


# ---- Geocoder.lookup ------------------------------------------------------------------------


def test_lookup_parses_geographies_and_uses_spec_benchmark_and_vintage():
    seen = []
    m = _geocoder(MATCH, seen).lookup("450 Cypress Creek Rd", "Cedar Park", "TX", "78613")
    assert m is not None
    assert (m.lat, m.lng) == (30.497509155435, -97.820278589313)
    assert m.matched_address == "450 CYPRESS CREEK RD, CEDAR PARK, TX, 78613"
    assert (m.tract_geoid, m.county_geoid, m.place_geoid, m.zcta_geoid, m.cbsa_geoid) == (
        "48491020355", "48491", "4813552", "78613", "12420",
    )
    url = seen[0]
    assert "geocoder/geographies/address?" in url
    assert "benchmark=Public_AR_Current" in url
    assert "vintage=Current_Current" in url
    # A-C15 correction 3: without `layers=all` the service returns no ZCTA and no CBSA geography.
    assert "layers=all" in url
    assert "format=json" in url


def test_lookup_returns_none_on_no_match():
    assert _geocoder(NOMATCH).lookup("999999 Nowhere Ln", "Nonexistentville", "TX", "00000") is None


# ---- _first_geoid parser guards -------------------------------------------------------------


def test_first_geoid_falls_back_to_the_second_needle_for_a_census_designated_place():
    geographies = {"Census Designated Places": [{"GEOID": "x"}]}
    assert geocode._first_geoid(geographies, "Incorporated Places", "Census Designated Places") == "x"


def test_first_geoid_skips_a_matching_key_whose_rows_are_empty():
    assert geocode._first_geoid({"Counties": []}, "Counties") is None


def test_first_geoid_returns_none_when_no_key_matches_any_needle():
    assert geocode._first_geoid({"Something Else": [{"GEOID": "x"}]}, "Counties") is None


# ---- STATE_FIPS drift against the market_state registry --------------------------------------

_STATE_NAMES_BY_ABBR = {abbr: name for abbr, _fips, name in _STATES}


def test_state_fips_matches_the_market_state_registry(conn):
    """A-C15 correction 2, now pinning all fifty-one rather than six: the mapping this module
    exposes must never drift from the states `market_state` carries -- nothing else would catch a
    silent divergence, since `_fallback` queries `geo_area.state_fips` directly rather than joining
    through a geography name lookup."""
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips, name FROM market_state")
        registry = dict(cur.fetchall())
    expected = {fips: _STATE_NAMES_BY_ABBR[abbr] for abbr, fips in geocode.STATE_FIPS.items()}
    assert registry == expected


# ---- resolve: the ladder ----------------------------------------------------------------------


def test_resolve_raises_when_no_tiger_vintage_is_active(conn):
    lid = make_listing(conn)
    with pytest.raises(geocode.GeocodeFailed):
        geocode.resolve(conn, _geocoder(MATCH), lid)


def test_resolve_rooftop_writes_location_and_caches(conn):
    _seed_geo(conn)
    lid = make_listing(conn)
    seen = []
    loc = geocode.resolve(conn, _geocoder(MATCH, seen), lid)
    assert loc.geo_precision == "rooftop" and loc.tract_geoid == "48491020355" and loc.cbsa_geoid == "12420"
    with conn.cursor() as cur:
        cur.execute("SELECT geo_precision, ST_X(point), county_geoid FROM practice_location WHERE listing_id=%s", (lid,))
        assert cur.fetchone() == ("rooftop", -97.820278589313, "48491")
        cur.execute("SELECT count(*) FROM geocode_cache")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM geocode_review WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 0
    # second listing at the same address -> served from cache, no HTTP call
    lid2 = make_listing(conn)
    geocode.resolve(conn, _geocoder(MATCH, seen), lid2)
    assert len(seen) == 1


def test_resolve_uses_tract_precision_and_flags_for_staff_when_the_match_carries_no_tract_geoid(conn):
    """A precision rung the brief's own tests never exercise: a real address match whose
    geographies carry no Census Tracts layer (`m.tract_geoid is None`) still resolves, at the
    "tract" (not "rooftop") precision, and is flagged for staff review like any other
    below-rooftop precision (§11)."""
    _seed_geo(conn)
    lid = make_listing(conn)
    payload = json.loads(json.dumps(MATCH))
    del payload["result"]["addressMatches"][0]["geographies"]["Census Tracts"]
    loc = geocode.resolve(conn, _geocoder(payload), lid)
    assert loc.geo_precision == "tract" and loc.tract_geoid is None and loc.county_geoid == "48491"
    with conn.cursor() as cur:
        cur.execute("SELECT reason FROM geocode_review WHERE listing_id=%s", (lid,))
        assert "tract" in cur.fetchone()[0]


def test_resolve_serves_a_cached_nomatch_without_a_second_http_call(conn):
    """The brief's own cache test only ever caches a MATCH; a cached "no geocoder match" must
    also stop a second HTTP call within the 365-day window (§10), while still re-running the
    §11 fallback ladder for the second listing."""
    _seed_geo(conn)
    lid = make_listing(conn, zip="78613")
    seen = []
    first = geocode.resolve(conn, _geocoder(NOMATCH, seen), lid)
    assert first.geo_precision == "zcta"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM geocode_cache")
        assert cur.fetchone()[0] == 1
    lid2 = make_listing(conn, zip="78613")
    second = geocode.resolve(conn, _geocoder(NOMATCH, seen), lid2)
    assert second.geo_precision == "zcta"
    assert len(seen) == 1  # the cached nomatch served the second listing; no second HTTP call


def test_resolve_falls_back_to_zcta_centroid_and_flags_for_staff(conn):
    _seed_geo(conn)
    lid = make_listing(conn, zip="78613")
    loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)
    assert loc.geo_precision == "zcta" and loc.tract_geoid == "48491020355" and loc.zcta_geoid == "78613"
    with conn.cursor() as cur:
        cur.execute("SELECT reason FROM geocode_review WHERE listing_id=%s", (lid,))
        assert "zcta" in cur.fetchone()[0]


def test_resolve_falls_back_to_place_then_fails(conn):
    _seed_geo(conn)
    lid = make_listing(conn, zip="00000", city="Cedar Park")
    loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)
    assert loc.geo_precision == "place" and loc.place_geoid == "4813552"
    lid2 = make_listing(conn, zip="00000", city="Nowhereville")
    with pytest.raises(geocode.GeocodeFailed):
        geocode.resolve(conn, _geocoder(NOMATCH), lid2)


def test_resolve_falls_back_to_county_and_flags_for_staff_when_no_tract_or_place_matches(conn):
    """A-C18 ruling 1 (Critical): Section 6's fourth rung -- a county covering the ZCTA's own
    centroid, tried only when the ZCTA is known (rung 1 found it) but no tract covers it, and no
    place matched either. Migration 061's `geo_precision` CHECK constraint has admitted 'county'
    since Task B1; before this rung existed, nothing could ever write it."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)",
            ("tiger_cb", "2023", "test"),
        )
    _seed_county(conn, "48491", "48", "491", "Williamson County", _COUNTY_SQUARE, (-97.75, 30.5))
    _seed_zcta(conn, _ZCTA_NO_TRACT_GEOID, _ZCTA_NO_TRACT_POLY, _ZCTA_NO_TRACT_CENTROID)
    # deliberately no place row at all: the place query must fail regardless of city
    lid = make_listing(conn, zip=_ZCTA_NO_TRACT_GEOID, city="Nowhereville", state="TX")
    loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)
    assert loc.geo_precision == "county" and loc.county_geoid == "48491"
    assert loc.tract_geoid is None and loc.place_geoid is None
    with conn.cursor() as cur:
        cur.execute("SELECT reason FROM geocode_review WHERE listing_id=%s", (lid,))
        assert "county" in cur.fetchone()[0]


def test_fallback_rung_order_is_zcta_then_place_then_county_then_geocode_failed(conn):
    """A-C18 ruling 1: pins the FIXED order of all four rungs so a future edit cannot silently
    reorder them. Each successive listing loses the higher-priority rung's data while KEEPING
    every lower rung's data available, so a wrong precedence (e.g. county checked before place)
    would resolve the wrong listing at the wrong precision instead of merely failing outright."""
    _seed_geo(conn)  # zcta 78613 + covering tract 48491020355 (parent county 48491) + place 4813552 "Cedar Park city"
    _seed_county(conn, "48491", "48", "491", "Williamson County", _COUNTY_SQUARE, (-97.75, 30.5))
    _seed_zcta(conn, _ZCTA_NO_TRACT_GEOID, _ZCTA_NO_TRACT_POLY, _ZCTA_NO_TRACT_CENTROID)

    # rung 1 (zcta+tract) wins even though a matching place AND a covering county both exist too
    lid1 = make_listing(conn, zip="78613", city="Cedar Park", state="TX")
    assert geocode.resolve(conn, _geocoder(NOMATCH), lid1).geo_precision == "zcta"

    # rung 1 fails (this zip's ZCTA has no covering tract) -> rung 2 (place) wins even though
    # rung 3's county is also available for this same zip
    lid2 = make_listing(conn, zip=_ZCTA_NO_TRACT_GEOID, city="Cedar Park", state="TX")
    assert geocode.resolve(conn, _geocoder(NOMATCH), lid2).geo_precision == "place"

    # rung 1 and rung 2 both fail (unmatched city) -> rung 3 (county) wins
    lid3 = make_listing(conn, zip=_ZCTA_NO_TRACT_GEOID, city="Nowhereville", state="TX")
    loc3 = geocode.resolve(conn, _geocoder(NOMATCH), lid3)
    assert loc3.geo_precision == "county" and loc3.county_geoid == "48491"

    # rungs 1-3 all fail (unknown zip, unmatched city) -> GeocodeFailed
    lid4 = make_listing(conn, zip="00000", city="Nowhereville", state="TX")
    with pytest.raises(geocode.GeocodeFailed):
        geocode.resolve(conn, _geocoder(NOMATCH), lid4)


def test_the_place_rung_now_runs_for_every_state_not_only_the_original_six(conn):
    """The INVERSE of what this test asserted until 2026-09-12, and the reason it was inverted.

    It used to prove that a Washington listing never even ran the place query -- `STATE_FIPS` had
    six entries, `state_fips` came back `None`, and the rung was skipped. That was the finite list
    of supported places, observable from the outside: a practice in forty-five states silently got
    one fewer chance to resolve. `STATE_FIPS` now derives from `app.census.states.STATES`, so the
    rung runs everywhere.

    Still discriminating, and in the same way A-C18 ruling 4 asked for: the recording connection
    asserts the place query's own SQL text DID execute, which a test asserting only the outcome
    could not tell from the guard still being there (both end in `GeocodeFailed` when no place
    row matches)."""
    _seed_geo(conn)
    for state in ("WA", "AK", "ME", "WY"):   # four states outside the original six, none seeded
        lid = make_listing(conn, zip="00000", city="Cedar Park", state=state)
        rec = _RecordingConn(conn)
        with pytest.raises(geocode.GeocodeFailed):
            geocode.resolve(rec, _geocoder(NOMATCH), lid)
        assert any("summary_level = '160'" in q for q in rec.executed), state
        assert any("summary_level = '860'" in q for q in rec.executed), state


def test_fallback_place_query_requires_a_true_prefix_not_a_substring_match(conn):
    """A-C18 ruling 4 (Minor): discriminating -- "Cedar Park city" (the only seeded place row in
    every other test) satisfies both a genuine prefix anchor (`LIKE 'cedar park %'`) and a bare
    substring search, so no test built only from it can tell the two apart. A decoy row that
    contains the city name as a SUBSTRING but not as a PREFIX must be rejected."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid) VALUES
                 ('4899999','160','2023','North Cedar Park CDP','48',NULL,'48',
                  ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)),
                  ST_SetSRID(ST_MakePoint(-97.8,30.55),4269))"""
        )
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s, %s, now(), %s)",
            ("tiger_cb", "2023", "test"),
        )
    lid = make_listing(conn, zip="00000", city="Cedar Park", state="TX")
    with pytest.raises(geocode.GeocodeFailed):
        geocode.resolve(conn, _geocoder(NOMATCH), lid)


# ---- census.geocode_listing (the task) --------------------------------------------------------


def test_census_geocode_listing_is_registered_under_its_stable_name():
    assert "census.geocode_listing" in celery_app.tasks
    assert CT.geocode_listing_task.name == "census.geocode_listing"


def test_geocode_listing_task_resolves_and_enqueues_the_b4_backfill_task(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    lid = make_listing(conn)
    captured = {}

    def fake_resolve(c, gc, listing_id):
        captured["conn"], captured["geocoder"], captured["listing_id"] = c, gc, listing_id
        return geocode.Location(listing_id, "rooftop", 30.5, -97.8, "t", "c", "p", "z", "m")

    monkeypatch.setattr(geocode, "resolve", fake_resolve)
    sent = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, args=None, **kw: sent.append((name, args)))

    result = CT.geocode_listing(lid)

    assert result == {"listing_id": lid, "precision": "rooftop"}
    assert captured["listing_id"] == lid
    assert isinstance(captured["geocoder"], geocode.Geocoder)
    # A-C18 ruling 2: A-C3 (2) is a standing ruling on this EXACT User-Agent shape (not merely
    # sibling precedent) -- pin the literal the task actually builds, not just its type.
    assert captured["geocoder"].ua == f"PracticeMatch/{CT.VERSION} ({CONTACT})"
    # B4 owns census.backfill_listing (A-C14 (3): the brief's interface note wrongly said B5) --
    # published by name, so no import of B4's module is needed to prove the enqueue happened.
    assert sent == [("census.backfill_listing", [lid])]


def test_geocode_listing_task_without_a_contact_raises_and_does_not_resolve_or_enqueue(conn, monkeypatch):
    """A-C18 ruling 3 (Important): a misconfigured worker must not report success. Returning a
    dict here (the old behaviour) let Celery record SUCCEEDED for a listing that was never
    geocoded, with a log line as the only trace -- unlike a load_* task's own refusal, there is
    no `ingest_run` row to carry the failure durably, so this task must raise instead."""
    monkeypatch.delenv("CENSUS_CONTACT_EMAIL", raising=False)
    lid = make_listing(conn)
    monkeypatch.setattr(geocode, "resolve", lambda *a, **kw: pytest.fail("must not run without a contact"))
    sent = []
    monkeypatch.setattr(celery_app, "send_task", lambda *a, **kw: sent.append(a))

    with pytest.raises(CT._NotReady, match="CENSUS_CONTACT_EMAIL"):
        CT.geocode_listing(lid)

    assert sent == []


def test_geocode_listing_task_lets_geocode_failed_propagate_without_enqueuing(conn, monkeypatch):
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    lid = make_listing(conn)

    def fake_resolve(c, gc, listing_id):
        raise geocode.GeocodeFailed("no match anywhere")

    monkeypatch.setattr(geocode, "resolve", fake_resolve)
    sent = []
    monkeypatch.setattr(celery_app, "send_task", lambda *a, **kw: sent.append(a))

    with pytest.raises(geocode.GeocodeFailed):
        CT.geocode_listing(lid)
    assert sent == []


def test_every_us_state_is_a_market_state_so_a_new_listing_needs_no_code_change(conn) -> None:
    """The "finite list of supported places" this removes was TWO hard-coded six-entry tables --
    `market_state`, seeded with exactly 48/06/12/13/36/08 by migration 017, and `STATE_FIPS` in
    this module, the same six again. Every loader in the programme reads the first and the
    geocoder's place rung reads the second, so a listing in the other forty-five states skipped a
    fallback rung entirely and no boundary or ACS row was ever loaded for it.

    `app.census.states.STATES` is now the single source both sides derive from, and this asserts
    the registry really carries all fifty states and the District of Columbia -- not a longer
    subset."""
    from app.census.states import STATES

    assert len(STATES) == 51, "fifty states and the District of Columbia"
    with conn.cursor() as cur:
        cur.execute("SELECT state_fips, name FROM market_state")
        registry = dict(cur.fetchall())
    assert registry == {fips: name for _abbr, fips, name in STATES}
    assert {fips for _a, fips, _n in STATES} >= {"48", "06", "12", "13", "36", "08"}, "the original six are still there"


def test_state_fips_is_derived_from_the_one_state_table_and_not_spelled_twice() -> None:
    """The drift this closes is the one A-C15 correction 2 warned about, widened: two hand-kept
    lists of states cannot be kept in step by review."""
    from app.census.states import STATES

    assert geocode.STATE_FIPS == {abbr: fips for abbr, fips, _name in STATES}


def test_practices_resolve_in_states_across_the_country_including_one_in_no_cbsa(conn) -> None:
    """The requirement this proves, stated as a prohibition: no city-specific code, and no finite
    list of supported places, anywhere. A listing in ANY US state must resolve with no code change.

    Four states are seeded, chosen so none is one of the six original demo markets and so they
    exercise different corners of the mapping: Montana (30), Maine (23), West Virginia (54) and
    Alaska (02). Every one resolves through the ZCTA rung to its own tract, in its own state, and
    the stored `tract_geoid` is the one seeded for THAT state rather than a neighbour's.

    **Bozeman, Montana is deliberately outside any CBSA** -- no `310` row is seeded for it at all
    -- because the metro is what the boundary endpoint keys on, and a practice that belongs to no
    metro must still geocode. Nothing in `resolve` reads a CBSA, and this is what says so.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES ('tiger_cb','2023',now(),'test')")
    # (state abbr, FIPS, county, tract geoid, zip, city, a box far from every other one)
    places = [
        ("MT", "30", "031", "30031000600", "59715", "Bozeman",   (-111.1, 45.6)),
        ("ME", "23", "005", "23005003600", "04101", "Portland",  (-70.3, 43.6)),
        ("WV", "54", "039", "54039001300", "25301", "Charleston", (-81.7, 38.3)),
        ("AK", "02", "020", "02020000400", "99501", "Anchorage", (-149.9, 61.2)),
    ]
    with conn.cursor() as cur:
        for _abbr, fips, county, tract, zip_, city, (x, y) in places:
            box = (f"POLYGON(({x} {y},{x + 0.1} {y},{x + 0.1} {y + 0.1},{x} {y + 0.1},{x} {y}))")
            cur.execute(
                """INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid) VALUES
                     (%s,'140','2023',%s,%s,%s,%s, ST_Multi(ST_GeomFromText(%s,4269)), ST_SetSRID(ST_MakePoint(%s,%s),4269)),
                     (%s,'860','2023',%s,NULL,NULL,NULL, ST_Multi(ST_GeomFromText(%s,4269)), ST_SetSRID(ST_MakePoint(%s,%s),4269)),
                     (%s,'050','2023',%s,%s,%s,%s, ST_Multi(ST_GeomFromText(%s,4269)), ST_SetSRID(ST_MakePoint(%s,%s),4269))""",
                (tract, f"Census Tract in {city}", fips, county, fips + county, box, x + 0.05, y + 0.05,
                 zip_, f"ZCTA5 {zip_}", box, x + 0.05, y + 0.05,
                 fips + county, f"{city} County", fips, county, fips, box, x + 0.05, y + 0.05),
            )

    for abbr, _fips, _county, tract, zip_, city, _pt in places:
        lid = make_listing(conn, zip=zip_, city=city, state=abbr)
        loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)
        assert loc.geo_precision == "zcta", f"{city}, {abbr} did not resolve"
        assert loc.tract_geoid == tract, f"{city}, {abbr} resolved to the wrong state's tract"
        with conn.cursor() as cur:
            cur.execute("SELECT tract_geoid FROM practice_location WHERE listing_id = %s", (lid,))
            assert cur.fetchone()[0] == tract, f"{city}, {abbr} resolved to the wrong state's tract"

    with conn.cursor() as cur:   # the premise of the Montana case, asserted rather than assumed
        cur.execute("SELECT count(*) FROM geo_area WHERE summary_level = '310'")
        assert cur.fetchone()[0] == 0, "no CBSA was seeded, so none of these practices is in a metro"


def test_a_territory_skips_the_place_rung_because_states_py_deliberately_excludes_it(conn) -> None:
    """`STATE_FIPS` covers the fifty states and DC and NOTHING else, so `state_fips` is `None` for
    Puerto Rico and the place rung is skipped for it exactly as it used to be skipped for
    forty-five real states. That exclusion is a DATA decision recorded in `app/census/states.py`:
    the ACS 5-year detailed tables do not publish `B19013_001E` for the island areas on the same
    `state:*` geography, and TIGER publishes their tract files under separate vintages -- so a
    territory would resolve to a geography carrying no figure.

    Discriminating in the way A-C18 ruling 4 asked for, and for the same reason it gave: a null
    `state_fips` makes `state_fips = %s` fail identically with the guard deleted (SQL `NULL = NULL`
    is never true), so asserting only `GeocodeFailed` could not tell a real guard from no guard.
    The recording connection proves the place query's own SQL text never executes.

    The needle is the place rung's NAME PREFIX predicate, not `summary_level = '160'` (fix round
    2). Rung 1 now joins level 160 itself — every rung fills every geography its own point can be
    joined to — so a bare "160" needle would be satisfied by rung 1's own text and this assertion
    would pass whether or not the guard existed, which is precisely the failure mode A-C18 ruling
    4 wrote this test to avoid. `lower(p.name) LIKE lower(%s)` occurs in the place rung and
    nowhere else."""
    _seed_geo(conn)
    for territory in ("PR", "VI", "GU"):
        lid = make_listing(conn, zip="00000", city="Cedar Park", state=territory)
        rec = _RecordingConn(conn)
        with pytest.raises(geocode.GeocodeFailed):
            geocode.resolve(rec, _geocoder(NOMATCH), lid)
        assert geocode.STATE_FIPS.get(territory) is None, f"{territory} must not be in the state table"
        assert not any("lower(p.name) LIKE lower(%s)" in q for q in rec.executed), territory
        assert any("summary_level = '860'" in q for q in rec.executed), territory  # the zcta rung DID run


# ---- Task GEO-WIRE: one writer for the pin ----------------------------------------------------


def test_resolve_writes_the_listings_own_pin_from_the_resolved_point(conn):
    """GEO-WIRE (3). `listing.geom` is the column `GET /api/listings` serves as `lat`/`lng`
    (`app/api/listings.py`'s `_SELECT`), and until this it was written by `scripts/seed_listings.py`
    ALONE -- so a real seller's listing, geocoded on publish, still reached Browse with no pin.

    The point is written HERE, beside `practice_location.point`, rather than in the Celery task or
    the CLI: `resolve` is where the resolved coordinate exists, and a second writer somewhere else
    is how the two columns start disagreeing. `geography(Point,4326)` is the listing column's own
    type (`migrations/016_listing.sql:26`) and `ST_SetSRID(ST_MakePoint(lng,lat),4326)::geography`
    is the seeder's own expression, so both writers write the same thing."""
    _seed_geo(conn)
    lid = make_listing(conn)
    geocode.resolve(conn, _geocoder(MATCH), lid)
    with conn.cursor() as cur:
        cur.execute("SELECT ST_X(geom::geometry), ST_Y(geom::geometry) FROM listing WHERE id=%s", (lid,))
        assert cur.fetchone() == (-97.820278589313, 30.497509155435)


def test_resolve_below_rooftop_writes_the_fallback_centroid_as_the_pin(conn):
    """The §11 ladder's own rungs carry a point too (the ZCTA/place/county centroid), and that
    point is the one `practice_location` is written with -- so the pin follows it rather than
    staying null for every listing the geocoder cannot match. `GET /api/listings` then serves a
    pin the Community Context card's own figures were computed around."""
    _seed_geo(conn)
    lid = make_listing(conn, zip="78613")
    loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)
    assert loc.geo_precision == "zcta"
    with conn.cursor() as cur:
        cur.execute("SELECT ST_X(geom::geometry), ST_Y(geom::geometry) FROM listing WHERE id=%s", (lid,))
        assert cur.fetchone() == (-97.8, 30.55)


# ---- fix round 1: the pin, the review queue and the Browse cache -------------------------------


def _pin(conn, lid):
    with conn.cursor() as cur:
        cur.execute("SELECT ST_X(geom::geometry), ST_Y(geom::geometry) FROM listing WHERE id=%s", (lid,))
        return cur.fetchone()


def _open_reviews(conn, lid):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM geocode_review WHERE listing_id=%s AND resolved_at IS NULL", (lid,))
        return cur.fetchone()[0]


def test_a_resolve_that_finds_no_coordinate_leaves_an_existing_pin_alone(conn):
    """Review minor 4. The pin write used a `CASE WHEN … IS NULL THEN NULL` mirroring the
    `practice_location` row above it — which means a re-resolve that lands on a rung with no
    coordinate would have NULLED a pin that was already there. `scripts/seed_listings.py` writes
    the seeds' own curated points, so the row this could silently blank is a demo hospital's.

    The rung is reachable, not hypothetical: `geo_area.centroid` is nullable, and a place row
    loaded without one resolves at `place` precision with `lat`/`lng` both `None`. Absence of a
    new coordinate is not evidence against the coordinate already held."""
    with conn.cursor() as cur:
        # A place the city name matches, with NO centroid — and no ZCTA for this ZIP, so the
        # ladder cannot take rung 1 and falls to rung 2.
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom) VALUES "
            "('4813552','160','2023','Cedar Park city','48',"
            " ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)))"
        )
        cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by)"
                    " VALUES ('tiger_cb','2023',now(),'test')")
    lid = make_listing(conn, zip="00000", city="Cedar Park")
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET geom = ST_SetSRID(ST_MakePoint(-97.75,30.51),4326)::geography WHERE id=%s", (lid,))

    loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)

    assert (loc.geo_precision, loc.lat, loc.lng) == ("place", None, None)
    assert _pin(conn, lid) == (-97.75, 30.51), "a resolve with no coordinate must not blank the pin"


def test_the_pin_and_the_practice_location_point_are_the_same_place(conn):
    """Review minor 7. `practice_location.point` is `geometry(Point,4269)` (NAD83) and
    `listing.geom` is `geography(Point,4326)` (WGS84), and the two used to be built by two
    separate expressions that happened to agree. They are now ONE coordinate put through an
    explicit `ST_Transform`, so they are the same point by construction rather than by
    coincidence.

    Stated honestly about what this gate does and does not prove: it catches a swapped argument
    pair (`ST_MakePoint(lat, lng)`) or a mis-declared SRID, either of which separates the two
    columns by hundreds of kilometres. It does NOT distinguish the two DATUMS, because PROJ
    treats NAD83 and WGS84 as equivalent absent a grid shift and returns the identical numbers —
    which is the very reason the seeder's own convention (`ST_SetSRID(..., 4326)` over a Census
    coordinate) has always been right to sub-metre, and why minor 7 is a correctness-of-
    construction change rather than a change of behaviour."""
    _seed_geo(conn)
    lid = make_listing(conn)
    geocode.resolve(conn, _geocoder(MATCH), lid)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ST_X(l.geom::geometry), ST_Y(l.geom::geometry),"
            "       ST_X(ST_Transform(p.point, 4326)), ST_Y(ST_Transform(p.point, 4326))"
            "  FROM listing l JOIN practice_location p ON p.listing_id = l.id WHERE l.id = %s", (lid,)
        )
        gx, gy, px, py = cur.fetchone()
    assert abs(gx - px) < 1e-7 and abs(gy - py) < 1e-7


def test_two_sub_rooftop_resolves_leave_one_open_review_row(conn):
    """Review minor 8. `geocode_review` is the staff queue for a listing that resolved below
    rooftop (§11), and it has no uniqueness of its own (`migrations/060_geocode_cache.sql`). Every
    re-publish, every address correction and every `census_load.py geocode --force` runs `resolve`
    again, so the queue grew one duplicate row per pass for a condition that had not changed —
    the same listing, the same reason, nothing for staff to do twice.

    An UNRESOLVED row is the open item, so a second resolve adds nothing while one stands. A row a
    staff member has closed (`resolved_at`) does not suppress a new one: the condition recurring
    after it was dealt with is a real new item. No migration — the guard is in the INSERT."""
    _seed_geo(conn)
    lid = make_listing(conn, zip="78613")

    assert geocode.resolve(conn, _geocoder(NOMATCH), lid).geo_precision == "zcta"
    assert _open_reviews(conn, lid) == 1
    assert geocode.resolve(conn, _geocoder(NOMATCH), lid).geo_precision == "zcta"
    assert _open_reviews(conn, lid) == 1, "a second pass must not re-queue an open review"

    with conn.cursor() as cur:
        cur.execute("UPDATE geocode_review SET resolved_at = now() WHERE listing_id = %s", (lid,))
    geocode.resolve(conn, _geocoder(NOMATCH), lid)
    assert _open_reviews(conn, lid) == 1, "once staff have closed it, the condition can be raised again"


# ---- fix round 2: every rung fills every geography its own point can be joined to --------------


def test_the_zcta_rung_resolves_the_place_and_cbsa_its_centroid_lies_in(conn):
    """Fix round 2, Important 1. Rung 1 returned the ZCTA, the tract covering its centroid and
    that tract's parent county, and NOTHING else — no `place_geoid`, no `cbsa_geoid` — while rung 2
    (which sets a place) only runs when rung 1 has already FAILED.

    That is the rung a real seller's listing lands on: the wizard collects a city and a ZIP and no
    street, so the geocoder cannot match an address. Two things followed from the gap, both of
    which the rest of this programme had already been built to deliver:

    * `materialize._band_inputs("place")` returns `None` without `ctx.place`, so the listing had
      ZERO `place`-band rows — and the controller's fix-round-1 ruling, which serves exactly these
      listings their PLACE band, then had nothing to serve and produced four blank tiles. The
      ruling was right; the ladder was not making it true.
    * `GET /api/markets` requires `practice_location.cbsa_geoid`, so the listing's metro never
      joined the map's catalogue — one of the three things wiring the geocode exists to deliver.

    The point the rung holds is the ZCTA centroid, and every one of those geographies is a
    containment join away from it — the same `ST_Contains(..., z.centroid)` the rung already runs
    twice, for the tract and the county."""
    _seed_geo(conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom) VALUES"
            " ('12420','310','2023','Austin-Round Rock-San Marcos, TX Metro Area',"
            "  ST_Multi(ST_GeomFromText('POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))',4269)))"
        )
    lid = make_listing(conn, zip="78613")

    loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)

    assert loc.geo_precision == "zcta"
    assert loc.place_geoid == "4813552", "the ZCTA centroid lies inside Cedar Park city"
    assert loc.cbsa_geoid == "12420"
    with conn.cursor() as cur:
        cur.execute("SELECT place_geoid, cbsa_geoid FROM practice_location WHERE listing_id=%s", (lid,))
        assert cur.fetchone() == ("4813552", "12420")


def test_a_zcta_centroid_in_no_place_leaves_the_place_geoid_null(conn):
    """Unincorporated. A ZCTA centroid that lies inside no place at all resolves with
    `place_geoid` NULL — honestly, rather than by reaching for a place whose boundary does not
    contain the point. `materialize`'s own county fallback then carries growth and payroll, and
    the area group is genuinely unavailable; the contract document says so.

    This is the Orlando specialist centre's condition (D-C32) arriving one rung lower."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid) VALUES"
            " ('48491020355','140','2023','Census Tract 203.55','48','491','48491',"
            "  ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)),"
            "  ST_SetSRID(ST_MakePoint(-97.8,30.55),4269)),"
            " ('78613','860','2023','ZCTA5 78613',NULL,NULL,NULL,"
            "  ST_Multi(ST_GeomFromText('POLYGON((-97.9 30.5,-97.7 30.5,-97.7 30.6,-97.9 30.6,-97.9 30.5))',4269)),"
            "  ST_SetSRID(ST_MakePoint(-97.8,30.55),4269)),"
            # A real place, far away — so the join runs and correctly matches nothing.
            " ('4813552','160','2023','Cedar Park city','48',NULL,'48',"
            "  ST_Multi(ST_GeomFromText('POLYGON((-96.0 30.5,-95.9 30.5,-95.9 30.6,-96.0 30.6,-96.0 30.5))',4269)),"
            "  ST_SetSRID(ST_MakePoint(-95.95,30.55),4269))"
        )
        cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by)"
                    " VALUES ('tiger_cb','2023',now(),'test')")
    lid = make_listing(conn, zip="78613")

    loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)

    assert loc.geo_precision == "zcta"
    assert loc.place_geoid is None
    assert loc.tract_geoid == "48491020355"


def test_the_place_rung_resolves_the_county_and_cbsa_its_own_centroid_lies_in(conn):
    """The same rule applied to rung 2 (fix round 2). Its point is the PLACE centroid rather than
    the ZIP's, but it is still a point, and a county and a CBSA are still one containment join
    away from it — so the rung that used to return a place and nothing else now returns all three.

    Why it matters where rung 1's mattered: without a county, `materialize._Ctx` has no CBP row,
    so the payroll figure and the county growth fallback both vanish; without a CBSA the listing's
    metro never reaches `GET /api/markets`. Neither is a property of WHICH rung answered."""
    _seed_geo(conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom) VALUES"
            " ('48491','050','2023','Williamson County','48',"
            "  ST_Multi(ST_GeomFromText('POLYGON((-99 30,-97 30,-97 31,-99 31,-99 30))',4269))),"
            " ('12420','310','2023','Austin-Round Rock-San Marcos, TX Metro Area',NULL,"
            "  ST_Multi(ST_GeomFromText('POLYGON((-99 30,-97 30,-97 31,-99 31,-99 30))',4269)))"
        )
    # An unknown ZIP, so rung 1 cannot answer and rung 2 does.
    lid = make_listing(conn, zip="00000", city="Cedar Park", state="TX")

    loc = geocode.resolve(conn, _geocoder(NOMATCH), lid)

    assert loc.geo_precision == "place" and loc.place_geoid == "4813552"
    assert loc.county_geoid == "48491"
    assert loc.cbsa_geoid == "12420"


# ---- fix round 2, Moderate 2: the cache drop belongs to the task, after the backfill enqueue ----


def test_resolve_is_a_pure_postgis_write_and_never_reaches_redis(conn):
    """Fix round 2, Moderate 2. Fix round 1 put `drop_list_cache(sync_redis())` INSIDE `resolve()`,
    which put a network call between two committed point columns and the backfill that turns them
    into figures: `resolve` runs to completion (autocommit, so both writes are durable), the drop
    raises on a Redis blip, `geocode_listing` never reaches its `send_task`, and a later republish
    sees `has_geocode() == True` and does not re-trigger. The listing keeps a pin and NO market
    card, silently and permanently — GEO-WIRE's own defect, wearing the fix for a smaller one.

    `resolve` is a PostGIS write and nothing else again. `app.cache` is not imported by
    `app/census/geocode.py` at all, which is what this asserts — the ~25 direct callers in this
    file stopped opening a real Redis connection with it."""
    import app.census.geocode as G

    assert not hasattr(G, "drop_list_cache") and not hasattr(G, "sync_redis")
    _seed_geo(conn)
    lid = make_listing(conn)

    calls: list[str] = []
    from app import cache as cache_module
    original = cache_module.sync_redis
    try:
        cache_module.sync_redis = lambda: calls.append("redis") or original()  # type: ignore[assignment]
        geocode.resolve(conn, _geocoder(MATCH), lid)
    finally:
        cache_module.sync_redis = original  # type: ignore[assignment]
    assert calls == []


def test_the_task_drops_the_browse_cache_only_after_the_backfill_is_enqueued(conn, monkeypatch):
    """The ORDER is the whole point: the durable work is committed, the backfill is queued, and
    only then is a cache touched. A drop that fails after that costs a stale Browse page for the
    rest of its 60 s TTL and nothing else — the figures are already on their way."""
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    _seed_geo(conn)
    lid = make_listing(conn)
    order: list[str] = []

    # Built BEFORE the patch: `_geocoder` calls `geocode.Geocoder` itself, so patching the name
    # to a factory that calls `_geocoder` would recurse.
    gc = _geocoder(MATCH)
    monkeypatch.setattr(geocode, "Geocoder", lambda *a, **kw: gc)
    monkeypatch.setattr(celery_app, "send_task", lambda name, args=None, **kw: order.append(f"enqueue:{name}"))
    from app import cache as cache_module
    monkeypatch.setattr(cache_module, "drop_list_cache", lambda cache: order.append("drop"))

    CT.geocode_listing(lid)

    assert order == ["enqueue:census.backfill_listing", "drop"]


def test_a_redis_failure_during_the_cache_drop_is_logged_and_never_replaces_the_result(conn, monkeypatch, caplog):
    """The failure this whole move exists to bound, taken to its conclusion (fix round 4). The
    ordering already meant a blip here could not cost the listing its backfill; what it still did
    was replace the task's OUTCOME with an exception — the geocode succeeded, both point columns
    are committed, the backfill is queued, and Celery would have recorded the task as FAILED and
    retried a whole Census round trip to re-do work that was already done.

    A cache drop is not the task's job. It is logged at WARNING and swallowed, the way
    `app/api/admin_data_sources.py` already treats a gate invalidation that fails after its
    decision has committed — and the cache's own 60 s TTL is the backstop. Only the exception's
    TYPE is logged, never its text, which can carry a host and port.

    `redis.exceptions.RedisError` specifically, never a bare `except`: a `TypeError` from this
    module's own code is a defect and must still surface."""
    import logging

    import redis as redis_sync

    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    _seed_geo(conn)
    lid = make_listing(conn)
    sent: list[str] = []

    def _boom(cache):
        raise redis_sync.exceptions.ConnectionError("redis://someone:6379 is having a moment")

    gc = _geocoder(MATCH)
    monkeypatch.setattr(geocode, "Geocoder", lambda *a, **kw: gc)
    monkeypatch.setattr(celery_app, "send_task", lambda name, args=None, **kw: sent.append(name))
    from app import cache as cache_module
    monkeypatch.setattr(cache_module, "drop_list_cache", _boom)

    with caplog.at_level(logging.WARNING, logger="app.tasks.census"):
        assert CT.geocode_listing(lid) == {"listing_id": lid, "precision": "rooftop"}

    assert sent == ["census.backfill_listing"]
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM practice_location WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 1, "the durable write is committed either way"

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "ConnectionError" in warnings[0].getMessage()
    assert "6379" not in warnings[0].getMessage(), "the type, never the text: it can carry a host"


def test_a_non_redis_error_from_the_cache_drop_still_surfaces(conn, monkeypatch):
    """The other side of the narrow `except`. A `TypeError` (or anything else that is not a
    `RedisError`) coming out of the drop is this codebase's own defect, not an infrastructure
    blip, and swallowing it would hide it for as long as nobody reads the logs."""
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    _seed_geo(conn)
    lid = make_listing(conn)

    def _boom(cache):
        raise TypeError("drop_list_cache() got an unexpected keyword argument")

    gc = _geocoder(MATCH)
    monkeypatch.setattr(geocode, "Geocoder", lambda *a, **kw: gc)
    monkeypatch.setattr(celery_app, "send_task", lambda *a, **kw: None)
    from app import cache as cache_module
    monkeypatch.setattr(cache_module, "drop_list_cache", _boom)

    with pytest.raises(TypeError):
        CT.geocode_listing(lid)


def test_the_task_really_clears_a_planted_browse_page(conn, redis, monkeypatch):
    """The behaviour fix round 1 pinned at `resolve` level, re-pinned where it now lives: a real
    `listings:v1:*` key, the real `drop_list_cache`, and the task. The two tests above assert the
    ORDER and the failure bound with a spy; this one asserts the key actually goes."""
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    _seed_geo(conn)
    lid = make_listing(conn)
    redis.set("listings:v1:::50", b"stale page")

    gc = _geocoder(MATCH)
    monkeypatch.setattr(geocode, "Geocoder", lambda *a, **kw: gc)
    monkeypatch.setattr(celery_app, "send_task", lambda *a, **kw: None)

    CT.geocode_listing(lid)

    assert redis.get("listings:v1:::50") is None
