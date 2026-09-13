"""Task GEO-WIRE: the whole per-listing chain, from the reviewer's Publish to the pin, the metro
and the market card — driven only through the product's own doors.

The per-listing market chain (`census.geocode_listing` -> `census.backfill_listing` ->
`market_metric`) was built in Phase B, and Task B9 wired the publish trigger onto it. Every LINK
had a green test and the WHOLE had none, which is how the chain could be trigger-complete and
still deliver a listing to Browse with no pin: `listing.geom`, the only column the pin is read
from, was written by `scripts/seed_listings.py` alone, so the twenty-nine hand-geocoded QA demo
hospitals had pins and nothing a seller published ever would. That defect lived in the gap BETWEEN
two tested links, which is the gap this file exists to close: it never calls `geocode.resolve`
itself, it publishes a listing through `POST /api/admin/listings/{id}/decide`, asserts the task
that request enqueued BY NAME, and then asks the product's own read routes what a buyer would see.

The two Celery tasks are then run INLINE, in the worker's own order, because there is no worker in
this suite — that is the seam, and it is the only one. Everything either side of it is the real
route, the real serialiser and the real database.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.census import geocode
from app.tasks import census as CT
from app.tasks.celery_app import celery_app
from tests.api.conftest import auth_headers

MATCH = json.loads((Path(__file__).parent.parent / "census" / "fixtures" / "geocoder_match.json").read_text())
# The fixture's own rooftop coordinate — `450 Cypress Creek Rd, Cedar Park, TX 78613`, a real
# recorded Census Geocoder response (`tests/census/test_geocode.py`'s own module docstring).
MATCH_LNG, MATCH_LAT = -97.820278589313, 30.497509155435
CONTACT = "tech@vinfoundation.example.org"
_REAL_GEOCODER = geocode.Geocoder

# Squares that CONTAIN the fixture's coordinate (30.4975 N), unlike `test_materialize.py`'s own
# world, whose tracts start at 30.50 — the point has to fall inside a tract for the catchment to
# weight anything.
_TRACT_A = "POLYGON((-97.90 30.45,-97.80 30.45,-97.80 30.55,-97.90 30.55,-97.90 30.45))"
_TRACT_B = "POLYGON((-97.80 30.45,-97.70 30.45,-97.70 30.55,-97.80 30.55,-97.80 30.45))"
_WIDE = "POLYGON((-99.0 30.0,-97.0 30.0,-97.0 31.0,-99.0 31.0,-99.0 30.0))"


def _seed_geography(conn: Any) -> None:
    """Tracts, ZCTAs, a place, a county and the CBSA the fixture's own GEOIDs name, plus the ACS,
    CBP and ZBP rows `materialize_listing` reads and the five active vintages everything is
    resolved at. Deliberately the fixture's REAL geoids (Census Tract 203.55, Williamson County,
    Cedar Park city, ZCTA 78613, CBSA 12420), so the geocoder's answer and the geography it is
    joined to describe one place throughout."""
    with conn.cursor() as cur:
        for gid, wkt in (("48491020355", _TRACT_A), ("48491020356", _TRACT_B)):
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, parent_geo_id, geom, centroid)"
                " VALUES (%s,'140','2023',%s,'48','491','48491', ST_Multi(ST_GeomFromText(%s,4269)), ST_Centroid(ST_GeomFromText(%s,4269)))",
                (gid, f"Census Tract {gid}", wkt, wkt),
            )
        for gid, wkt in (("78613", _TRACT_A), ("78664", _TRACT_B)):
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid)"
                " VALUES (%s,'860','2023',%s, ST_Multi(ST_GeomFromText(%s,4269)), ST_Centroid(ST_GeomFromText(%s,4269)))",
                (gid, f"ZCTA5 {gid}", wkt, wkt),
            )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES"
            " ('4813552','160','2023','Cedar Park city','48', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.80,30.50,4269)),"
            " ('48491','050','2023','Williamson County','48', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.80,30.50,4269)),"
            " ('12420','310','2023','Austin-Round Rock-San Marcos, TX Metro Area',NULL,"
            "  ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.31,4269))",
            (_WIDE, _WIDE, _WIDE),
        )
        cur.execute(
            "INSERT INTO ingest_run (dataset_key, vintage, started_at, status) VALUES"
            " ('acs5','2019\u20132023',now(),'succeeded'),('acs5_prior','2014\u20132018',now(),'succeeded'),"
            " ('cbp','2022',now(),'succeeded'),('zbp','2022',now(),'succeeded')"
        )
        cur.execute("SELECT id FROM ingest_run ORDER BY id")
        acs, prior, cbp, zbp = [r[0] for r in cur.fetchall()]
        cur.executemany(
            "INSERT INTO acs_measure VALUES (%s,'140','2019\u20132023',%s,%s,%s,%s)",
            [(g, v, e, m, acs) for g, v, e, m in (
                ("48491020355", "B01003_001E", 4000, 200), ("48491020355", "B11001_001E", 1500, 95),
                ("48491020355", "B19013_001E", 118400, 9100),
                ("48491020356", "B01003_001E", 3000, 300), ("48491020356", "B11001_001E", 1200, 80),
                ("48491020356", "B19013_001E", 98000, 12000),
            )],
        )
        cur.executemany(
            "INSERT INTO acs_measure VALUES ('4813552','160','2019\u20132023',%s,%s,%s,%s)",
            [("B01003_001E", 81900, 900, acs), ("B11001_001E", 27600, 600, acs), ("B19013_001E", 118400, 4100, acs)],
        )
        cur.execute("INSERT INTO acs_measure VALUES ('4813552','160','2014\u20132018','B01003_001E',71716,850,%s)", (prior,))
        cur.execute("INSERT INTO acs_measure VALUES ('1','010','2019\u20132023','B19013_001E',75149,120,%s)", (acs,))
        cur.execute("INSERT INTO acs_measure VALUES ('48491','050','2019\u20132023','B11001_001E',230000,1200,%s)", (acs,))
        cur.execute("INSERT INTO cbp_industry VALUES ('48491','050','2022','541940',210,3400,143850,NULL,%s)", (cbp,))
        cur.executemany(
            "INSERT INTO zbp_industry (geo_id, vintage, naics_code, establishments, ingest_run_id) VALUES (%s,'2022','541940',%s,%s)",
            [("78613", 5, zbp), ("78664", 2, zbp)],
        )
        cur.executemany(
            "INSERT INTO active_vintage VALUES (%s,%s,now(),'test')",
            [("acs5", "2019\u20132023"), ("acs5_prior", "2014\u20132018"), ("cbp", "2022"),
             ("zbp", "2022"), ("tiger_cb", "2023")],
        )


def _fixture_geocoder(*_args: Any, **_kw: Any) -> geocode.Geocoder:
    """The real `Geocoder`, over a transport that answers with the recorded MATCH body. Patched in
    over `geocode.Geocoder` so `census.geocode_listing` runs its OWN code — `resolve`, the address
    cache, the §11 ladder and both point writes — against a response the Census once really gave.

    `_REAL_GEOCODER`, not `geocode.Geocoder`: this function IS what that name is patched to."""
    return _REAL_GEOCODER(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=MATCH))),
        "https://geocoding.geo.census.gov/geocoder",
        "PracticeMatch (test)",
    )


async def _published_listing(client: Any, member: Any, monkeypatch: Any) -> tuple[str, list[tuple[str, Any]]]:
    """A seller's listing taken to `published` through the real wizard and the real reviewer's
    decision, and every task those requests enqueued."""
    _seller, s_cookies, s_headers = member(roles=("seller",), email="gw-seller@example.org")
    signed = auth_headers(s_cookies, s_headers)
    created = await client.post("/api/seller/listings", headers=signed)
    assert created.status_code == 201, created.text
    listing_id = created.json()["id"]
    for step, payload in (
        (1, {"name": "Cypress Creek Animal Hospital", "type": "Small animal", "est": "2005"}),
        # `anon: False` is the design's own step-7 switch read at step 2: "Sellers control what
        # buyers can see". Set BEFORE the publish, because a later edit would take the listing off
        # the market (D3) — which is itself the behaviour the second half of the pin test needs.
        (2, {"city": "Cedar Park", "zip": "78613", "anon": False}),
        (3, {"price": "1450000"}),
        (4, {"sqft": "3000"}),
    ):
        r = await client.patch(f"/api/seller/listings/{listing_id}?step={step}", json=payload, headers=signed)
        assert r.status_code == 200, r.text
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=signed)).status_code == 200

    sent: list[tuple[str, Any]] = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, args=None, **kw: sent.append((name, args)))
    _admin, a_cookies, a_headers = member(roles=("admin",), email="gw-admin@example.org")
    decided = await client.post(f"/api/admin/listings/{listing_id}/decide",
                                json={"action": "publish", "state": "TX", "market": "Austin, TX"},
                                headers=auth_headers(a_cookies, a_headers))
    assert decided.status_code == 200, decided.text
    return listing_id, sent


@pytest.fixture
def _geocoder_fixture(monkeypatch: Any) -> None:
    monkeypatch.setenv("CENSUS_CONTACT_EMAIL", CONTACT)
    monkeypatch.setattr(geocode, "Geocoder", _fixture_geocoder)


async def test_publishing_a_listing_carries_it_all_the_way_to_a_pin_a_metro_and_a_market_card(
    client: Any, conn: Any, redis: Any, member: Any, monkeypatch: Any, _geocoder_fixture: None
) -> None:
    """The whole chain, end to end. Task B9's trigger already carried (1)-(3) and (5)-(6); (4),
    the pin, reached nothing but a seeded row before this task, and no test anywhere walked the
    six together, which is why the one missing link could sit between two green ones."""
    _seed_geography(conn)
    listing_id, sent = await _published_listing(client, member, monkeypatch)
    # (1) The reviewer's decision enqueued the geocode BY NAME — no Census module on the request
    # path (spec §10).
    assert sent == [("census.geocode_listing", [listing_id])]

    # (2) The worker's own two steps, in its own order. `geocode_listing` enqueues the backfill the
    # same way; running it is the one seam this file has.
    sent.clear()
    assert CT.geocode_listing(listing_id) == {"listing_id": listing_id, "precision": "rooftop"}
    assert sent == [("census.backfill_listing", [listing_id])]
    backfilled = CT.backfill_listing(listing_id)
    assert backfilled["rows"], "the backfill wrote no market_metric rows"

    _account, cookies, _headers = member(("buyer",), email="gw-buyer@example.org")
    buyer = auth_headers(cookies, headers=None)

    # (3) The metro catalogue the Browse map keys on carries this listing's own market key.
    markets = (await client.get("/api/markets", headers=buyer)).json()
    assert [m["name"] for m in markets] == ["Austin, TX"]
    assert [m["cbsa_geoid"] for m in markets] == ["12420"]

    # (4) The pin. `listing.geom` is written by the geocode now, not by `seed_listings.py` alone.
    item = (await client.get(f"/api/listings/{listing_id}", headers=buyer)).json()
    assert (item["lat"], item["lng"]) == (MATCH_LAT, MATCH_LNG)
    assert item["geo_precision"] == "rooftop"
    listed = (await client.get("/api/listings", headers=buyer)).json()["items"]
    assert [(row["id"], row["lat"]) for row in listed] == [(listing_id, MATCH_LAT)]

    # (5) The Community Context card has figures instead of "Community data unavailable".
    assert item["pop"] is not None and item["income"] is not None

    # (6) And the docked panel's own endpoint answers with a card rather than a 404 + backfill.
    panel = await client.get(f"/api/listings/{listing_id}/market", headers=buyer)
    assert panel.status_code == 200, panel.text
    assert panel.json()["listing_id"] == listing_id


async def test_the_geocoded_pin_is_still_withheld_from_a_listing_that_hides_its_location(
    client: Any, conn: Any, redis: Any, member: Any, monkeypatch: Any, _geocoder_fixture: None
) -> None:
    """GEO-WIRE (3), the other half. A resolved point is not a published one: `location_disclosed`
    is `NOT NULL DEFAULT false` (`migrations/016_listing.sql`) and A-L5 blanks the point in
    `serialise`, so wiring the geocode must not become a way for an address the seller chose to
    hide to reach a buyer's browser as a pair of coordinates."""
    _seed_geography(conn)
    listing_id, _sent = await _published_listing(client, member, monkeypatch)
    CT.geocode_listing(listing_id)

    _account, cookies, _headers = member(("buyer",), email="gw-buyer@example.org")
    buyer = auth_headers(cookies, headers=None)
    shown = (await client.get(f"/api/listings/{listing_id}", headers=buyer)).json()
    assert (shown["lat"], shown["lng"]) == (MATCH_LAT, MATCH_LNG)

    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET location_disclosed = false WHERE id = %s", (listing_id,))
    hidden = (await client.get(f"/api/listings/{listing_id}", headers=buyer)).json()
    assert (hidden["lat"], hidden["lng"]) == (None, None)
    assert (hidden["street"], hidden["zip"]) == (None, None)
    # The precision is not a location: it says how well the point is known, and every field that
    # would say WHERE it is has just been blanked above.
    assert hidden["geo_precision"] == "rooftop"
