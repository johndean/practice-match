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
    The recording connection proves the place query's own SQL text never executes."""
    _seed_geo(conn)
    for territory in ("PR", "VI", "GU"):
        lid = make_listing(conn, zip="00000", city="Cedar Park", state=territory)
        rec = _RecordingConn(conn)
        with pytest.raises(geocode.GeocodeFailed):
            geocode.resolve(rec, _geocoder(NOMATCH), lid)
        assert geocode.STATE_FIPS.get(territory) is None, f"{territory} must not be in the state table"
        assert not any("summary_level = '160'" in q for q in rec.executed), territory
        assert any("summary_level = '860'" in q for q in rec.executed), territory  # the zcta rung DID run
