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

_STATE_NAMES_BY_ABBR = {"CA": "California", "TX": "Texas", "FL": "Florida", "GA": "Georgia", "NY": "New York", "CO": "Colorado"}


def test_state_fips_matches_the_market_state_registry(conn):
    """A-C15 correction 2: the six-entry mapping this module hard-codes must never drift from
    the states migration 017 pins in `market_state` -- nothing else would catch a silent
    divergence, since `_fallback` queries `geo_area.state_fips` directly rather than joining
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


def test_resolve_fails_without_a_place_fallback_for_a_state_outside_the_six_ruled_states(conn):
    """A-C15 correction 2: `STATE_FIPS` covers only the six ruled states; a listing outside them
    must reach `GeocodeFailed` without the place query ever running (`state_fips is None`)."""
    _seed_geo(conn)
    lid = make_listing(conn, zip="00000", city="Cedar Park", state="WA")
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
    # B4 owns census.backfill_listing (A-C14 (3): the brief's interface note wrongly said B5) --
    # published by name, so no import of B4's module is needed to prove the enqueue happened.
    assert sent == [("census.backfill_listing", [lid])]


def test_geocode_listing_task_without_a_contact_does_not_resolve_or_enqueue(conn, monkeypatch):
    monkeypatch.delenv("CENSUS_CONTACT_EMAIL", raising=False)
    lid = make_listing(conn)
    monkeypatch.setattr(geocode, "resolve", lambda *a, **kw: pytest.fail("must not run without a contact"))
    sent = []
    monkeypatch.setattr(celery_app, "send_task", lambda *a, **kw: sent.append(a))

    result = CT.geocode_listing(lid)

    assert sent == []
    assert result["listing_id"] == lid
    assert "CENSUS_CONTACT_EMAIL" in str(result["error"])


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
