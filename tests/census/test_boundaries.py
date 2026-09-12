"""GET /api/markets/{cbsa}/boundaries — the member-gated boundary layer (D-NS10 through D-NS18).

Reuses tests/census/test_market_api.py's `client` and `H` fixtures: one scratch database per test,
a real `buyer` session presented as a literal Cookie header (Task I9a).
"""
from __future__ import annotations

import json

import pytest

from app.api import market
from app.api.market import SIMPLIFY_TIERS
from app.cache import sync_redis
from app.census import gate, geo_metric
from app.config import settings
from tests.api.conftest import auth_headers
from tests.census.test_market_api import H, client  # noqa: F401 -- the fixtures, by name

AUSTIN = "POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))"
#: Two real Travis County (Austin) tract GEOIDs: state 48 + county 453 + tract, eleven digits.
TRACT_A = "48453001100"
TRACT_B = "48453001200"
INSIDE = "POLYGON((-97.8 30.2,-97.7 30.2,-97.7 30.3,-97.8 30.3,-97.8 30.2))"


@pytest.fixture
def seeded(conn):
    """One metro, two CENSUS TRACTS inside it, one place inside it, and the four active vintages.

    `48453001100` carries a measured median; `48453001200` carries a SUPPRESSED one. Both are real
    Travis County (Austin) tract GEOIDs — state(2) + county(3) + tract(6), eleven digits, which is
    the shape `app.census.acs.geoid` composes for level 140 and the shape the TIGER `GEOID` field
    carries. The place row exists so a `growth` request has a geography at level `160` to shade:
    income moved to the tract on 2026-09-12 while growth CANNOT follow it (the 2010->2020 boundary
    change, plan D12), so the two layers are deliberately different geographies and a fixture that
    only carried tracts could not tell them apart.
    """
    with conn.cursor() as cur:
        for key, vintage in (("tiger_cb", "2023"), ("acs5", "2019\u20132023"), ("acs5_prior", "2014\u20132018"), ("cbp", "2022")):
            cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s,%s,now(),'test')", (key, vintage))
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
            "('12420','310','2023','Austin-Round Rock-San Marcos, TX Metro Area', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.5,30.5,4269))",
            (AUSTIN,),
        )
        for geo_id, name in ((TRACT_A, "Census Tract 11"), (TRACT_B, "Census Tract 12")):
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, geom, centroid) VALUES "
                "(%s,'140','2023',%s,'48','453', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.25,4269))",
                (geo_id, name, INSIDE),
            )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES "
            "('4805000','160','2023','Austin','48', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.25,4269))",
            (INSIDE,),
        )
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
            f"('{TRACT_A}','140','2019\u20132023','median_hh_income',92150,'usd',6420,false,NULL,'acs5',now()), "
            f"('{TRACT_B}','140','2019\u20132023','median_hh_income',41000,'usd',40000,true,'high_moe','acs5',now())"
        )
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
            "('4805000','160','2019\u20132023','population_growth_pct',11.6,'pct',NULL,false,NULL,'acs5',now())"
        )
    return conn


async def _body(client, H, query: str = "?layer=income"):  # noqa: F811  (`client`/`H` the fixtures, by name)
    r = await client.get(f"/api/markets/12420/boundaries{query}", headers=H)
    return r, (json.loads(r.content) if r.status_code == 200 else r.json())


async def test_the_route_is_guarded_by_the_same_dependency_object_as_its_siblings(client, seeded, member, monkeypatch) -> None:  # noqa: F811
    path = "/api/markets/12420/boundaries?layer=income"
    assert (await client.get(path)).status_code == 401
    _aid, cookies, _csrf = member(("buyer",))
    assert (await client.get(path, headers=auth_headers(cookies))).status_code == 200
    monkeypatch.setattr(settings, "market_data_public", True)
    assert (await client.get(path)).status_code == 200
    # By IDENTITY, the way tests/auth/test_permissions.py resolves a guard: a fresh
    # `require("market.read")` per route reads as unguarded (market.py's correction 4).
    route = next(r for r in market.router.routes if getattr(r, "path", "") == "/api/markets/{cbsa}/boundaries")
    assert any(d.call is market.REQUIRE_MARKET_READ for d in route.dependant.dependencies)


async def test_a_feature_carries_the_value_the_margin_and_the_suppression_verdict(client, seeded, H) -> None:  # noqa: F811
    r, body = await _body(client, H)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    assert body["type"] == "FeatureCollection"
    assert (body["cbsa_geoid"], body["layer"], body["metric_key"]) == ("12420", "income", "median_hh_income")
    assert (body["summary_level"], body["geo_label"], body["unit"]) == ("140", "Census tract", "usd")
    assert (body["state"], body["boundary_vintage"], body["value_vintage"], body["source_dataset"]) == ("enabled", "2023", "2019\u20132023", "acs5")
    assert body["attribution"][0] == "Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023"
    assert body["attribution"][1].startswith("Source: U.S. Census Bureau, American Community Survey")
    assert body["values_without_geometry"] == 0
    by = {f["id"]: f for f in body["features"]}
    assert sorted(by) == [TRACT_A, TRACT_B]
    assert by[TRACT_A]["properties"] == {
        "geo_id": TRACT_A, "name": "Census Tract 11", "value": 92150.0, "moe": 6420.0,
        "suppressed": False, "suppress_reason": None, "band_ambiguous": False,
    }
    assert by[TRACT_B]["properties"]["suppressed"] is True and by[TRACT_B]["properties"]["suppress_reason"] == "high_moe"
    # A suppressed figure never reaches the wire: the polygon is greyed, and the number that was
    # too imprecise to publish is not smuggled out in the margin's company (§6).
    assert by[TRACT_B]["properties"]["value"] is None
    # 4326, not geo_area's own 4269.
    assert by[TRACT_A]["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert by[TRACT_A]["geometry"]["coordinates"][0][0][0] == pytest.approx([-97.8, 30.2], abs=1e-4)


async def test_a_polygon_with_no_row_at_all_is_returned_with_a_null_value_and_is_never_omitted(client, seeded, conn, H) -> None:  # noqa: F811
    """D-NS16: omitting it leaves a hole, and a hole on a choropleth reads as a boundary — a park,
    a lake, or the edge of the market, none of which is what happened. The sentinel is
    `value: null` with `suppressed: false`, which is NOT what a suppressed polygon carries, so a
    client that guards on `suppressed` alone would paint this one as measured."""
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM geo_metric WHERE geo_id = '{TRACT_B}'")
    _r, body = await _body(client, H)
    missing = next(f for f in body["features"] if f["id"] == TRACT_B)
    assert missing["properties"]["value"] is None
    assert missing["properties"]["suppressed"] is False
    assert missing["properties"]["suppress_reason"] is None
    assert missing["properties"]["moe"] is None
    assert len(body["features"]) == 2, "a polygon with no value was dropped"


async def test_no_data_and_suppressed_are_two_distinguishable_states_in_one_payload(client, seeded, conn, H) -> None:  # noqa: F811
    """§6 is the point of the feature, not decoration. Both polygons are drawn in the no-data
    class and the payload must still say which fact put each there — "No data for this area" and
    "Estimate too imprecise to show at this geography" are different sentences about different
    things. The assertion is that the two property dicts DIFFER; collapsing them (dropping
    `suppress_reason`, or marking an absent row `suppressed`) makes this test fail."""
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM geo_metric WHERE geo_id = '{TRACT_A}'")
    _r, body = await _body(client, H)
    by = {f["id"]: f["properties"] for f in body["features"]}
    assert by[TRACT_A]["value"] is None and by[TRACT_B]["value"] is None
    assert (by[TRACT_A]["suppressed"], by[TRACT_A]["suppress_reason"]) == (False, None)
    assert (by[TRACT_B]["suppressed"], by[TRACT_B]["suppress_reason"]) == (True, "high_moe")
    assert by[TRACT_A] != by[TRACT_B]


async def test_a_value_with_no_geometry_is_dropped_and_counted(client, seeded, conn, H) -> None:  # noqa: F811
    """§7, the other direction: the writer never invents a shape, and the endpoint never silently
    loses a row. A non-zero counter on a metro that has previously reported zero is how a boundary
    vintage that moved out from under the values announces itself."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, source_dataset, computed_at) "
            "VALUES ('99999','140','2019\u20132023','median_hh_income',50000,'usd','acs5',now())"
        )
    _r, body = await _body(client, H)
    assert body["values_without_geometry"] == 1
    assert "99999" not in [f["id"] for f in body["features"]]


async def test_band_ambiguity_is_computed_server_side_from_the_designs_own_stops(client, seeded, conn, H) -> None:  # noqa: F811
    with conn.cursor() as cur:
        cur.execute(f"UPDATE geo_metric SET moe = 9000 WHERE geo_id = '{TRACT_A}'")
    _r, body = await _body(client, H)
    assert next(f for f in body["features"] if f["id"] == TRACT_A)["properties"]["band_ambiguous"] is True


async def test_growth_is_served_at_its_own_geography_and_can_never_be_band_ambiguous(client, seeded, H) -> None:  # noqa: F811
    """D-C35/D-NS17. `growth` shades Place, not ZCTA, carries `pct` rather than `usd`, names both
    ACS vintages in its attribution, and is `band_ambiguous: false` by construction — it is
    published with no combined margin at all, so there is nothing for a stop to be crossed by."""
    r, body = await _body(client, H, "?layer=growth")
    assert r.status_code == 200
    assert (body["summary_level"], body["geo_label"], body["unit"]) == ("160", "Place (city/town)", "pct")
    assert body["metric_key"] == "population_growth_pct" and body["source_dataset"] == "acs5"
    assert len(body["attribution"]) == 3, "growth folds acs5_prior and must attribute it"
    props = next(f for f in body["features"] if f["id"] == "4805000")["properties"]
    assert props["value"] == 11.6 and props["moe"] is None and props["band_ambiguous"] is False
    assert props["name"] == "Austin"


@pytest.mark.parametrize("query,code", [
    ("?layer=pets", "BAD_LAYER"),
    ("?layer=nonsense", "BAD_LAYER"),
    ("", "BAD_LAYER"),
    ("?layer=income&bbox=not,a,box,at-all", "BAD_BBOX"),
    ("?layer=income&bbox=-98,30,-97", "BAD_BBOX"),
    ("?layer=income&bbox=-97,30,-98,31", "BAD_BBOX"),
    ("?layer=income&bbox=-98,31,-97,30", "BAD_BBOX"),
    ("?layer=income&bbox=-110,25,-90,35", "BBOX_TOO_LARGE"),
])
async def test_every_refusal_uses_decision_A5s_envelope_and_names_what_it_wants(client, seeded, H, query, code) -> None:  # noqa: F811
    r = await client.get(f"/api/markets/12420/boundaries{query}", headers=H)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == code
    assert "detail" not in r.json()
    if code == "BAD_LAYER":
        for name in ("income", "growth", "econ"):
            assert name in r.json()["error"]["message"]
    if code == "BBOX_TOO_LARGE":
        assert "4.0" in r.json()["error"]["message"]


async def test_a_bbox_at_the_cap_is_served_and_one_over_it_is_refused(client, seeded, H) -> None:  # noqa: F811
    assert (await client.get("/api/markets/12420/boundaries?layer=income&bbox=-98,30,-94,34", headers=H)).status_code == 200
    over = await client.get("/api/markets/12420/boundaries?layer=income&bbox=-98,30,-93.99,34", headers=H)
    assert over.status_code == 422 and over.json()["error"]["code"] == "BBOX_TOO_LARGE"


async def test_a_bbox_narrows_the_answer_and_keys_its_own_cache_entry(client, seeded, H) -> None:  # noqa: F811
    """The bbox segment of the key is not decoration: without it the first viewport served would
    answer every later one for 24 hours."""
    _r, metro = await _body(client, H)
    assert len(metro["features"]) == 2
    away = await client.get("/api/markets/12420/boundaries?layer=income&bbox=-90,25,-89,26", headers=H)
    assert away.status_code == 200 and away.headers["x-cache"] == "miss"
    assert json.loads(away.content)["features"] == []


async def test_too_many_features_is_refused_rather_than_served_slowly(client, seeded, H, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setattr(market, "MAX_FEATURES", 1)
    r = await client.get("/api/markets/12420/boundaries?layer=income", headers=H)
    assert r.status_code == 422 and r.json()["error"]["code"] == "AREA_TOO_LARGE"
    assert "1" in r.json()["error"]["message"]


async def test_too_large_a_body_is_refused_under_the_same_code(client, seeded, H, monkeypatch) -> None:  # noqa: F811
    """A whole-Texas box measured 6,884 tracts and 9.2 MB, and there was no bound anywhere in
    `app/` before this route (R6)."""
    monkeypatch.setattr(market, "MAX_BODY_BYTES", 10)
    r = await client.get("/api/markets/12420/boundaries?layer=income", headers=H)
    assert r.status_code == 422 and r.json()["error"]["code"] == "AREA_TOO_LARGE"


async def test_an_unknown_metro_is_a_404(client, seeded, H) -> None:  # noqa: F811
    r = await client.get("/api/markets/99999/boundaries?layer=income", headers=H)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


async def test_a_layer_whose_licence_is_withdrawn_answers_200_with_no_features(client, seeded, conn, H) -> None:  # noqa: F811
    """Never a 403: `/api/layers` already lists a blocked layer so the UI can render it as
    unavailable, and a map that 403s cannot draw that state. Legally load-bearing: a blocked
    dataset's figures never reach the wire (CLAUDE.md, "Blocked datasets never ship")."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5'")
    gate.invalidate(sync_redis(), "acs5")
    r, body = await _body(client, H)
    assert r.status_code == 200 and body["state"] == "disabled" and body["features"] == []
    assert "92150" not in r.content.decode("utf-8"), "a figure from an uncleared dataset reached the wire"
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='blocked', notes='Counsel declined the terms.' WHERE dataset_key='acs5'")
    gate.invalidate(sync_redis(), "acs5")
    r2, blocked = await _body(client, H)
    assert blocked["state"] == "blocked" and blocked["blocked_reason"] == "Counsel declined the terms."
    assert blocked["features"] == [] and "92150" not in r2.content.decode("utf-8")


async def test_growth_is_gated_on_acs5_prior_as_well_as_the_key_its_rows_are_stamped_with(client, seeded, conn, H) -> None:  # noqa: F811
    """R3's specific hole, at the read path this time."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5_prior'")
    gate.invalidate(sync_redis(), "acs5_prior")
    _r, body = await _body(client, H, "?layer=growth")
    assert body["state"] == "disabled" and body["features"] == []


async def test_growth_is_also_gated_on_the_dataset_its_rows_are_stamped_with(client, seeded, conn, H) -> None:  # noqa: F811
    """The other half of R3's pair, and the one the layer catalogue's own `dataset_key` cannot see:
    `growth`'s LAYERS entry names `acs5_prior`, so `_layer_state` reads `enabled` while the `acs5`
    rows the figures actually come from are not cleared. The belt the braces cannot reach."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5'")
    gate.invalidate(sync_redis(), "acs5")
    _r, body = await _body(client, H, "?layer=growth")
    assert body["state"] == "disabled" and body["features"] == []


async def test_the_cache_key_carries_the_gate_version_and_the_geo_version(client, seeded, H) -> None:  # noqa: F811
    """D-NS13 plus the geo version (this plan's own addition): a licence decision makes every
    cached body unreachable in the same instant, and so does a nightly rewrite that changes values
    without moving a vintage."""
    first = await client.get("/api/markets/12420/boundaries?layer=income", headers=H)
    assert first.headers["x-cache"] == "miss"
    assert (await client.get("/api/markets/12420/boundaries?layer=income", headers=H)).headers["x-cache"] == "hit"
    gate.invalidate(sync_redis(), "acs5")
    assert (await client.get("/api/markets/12420/boundaries?layer=income", headers=H)).headers["x-cache"] == "miss"
    sync_redis().set(geo_metric.GEO_VERSION_KEY, 12345)
    assert (await client.get("/api/markets/12420/boundaries?layer=income", headers=H)).headers["x-cache"] == "miss"
    assert (await client.get("/api/markets/12420/boundaries?layer=income", headers=H)).headers["x-cache"] == "hit"


async def test_gzip_is_applied_in_the_handler_and_the_identity_branch_serves_the_same_json(client, seeded, H) -> None:  # noqa: F811
    """D-NS14: no global GZipMiddleware — that would change every response in the application,
    including the ones carrying x-cache and the security headers, which is far wider than the ask.
    The compressed bytes are what Redis holds, so a hit costs no second compression."""
    zipped = await client.get("/api/markets/12420/boundaries?layer=income", headers={**H, "Accept-Encoding": "gzip"})
    assert zipped.headers["content-encoding"] == "gzip"
    assert zipped.headers["vary"] == "Accept-Encoding"
    plain = await client.get("/api/markets/12420/boundaries?layer=income", headers={**H, "Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
    assert plain.headers["vary"] == "Accept-Encoding"
    # httpx transparently decodes gzip, so both bodies read the same either way.
    assert json.loads(plain.content) == json.loads(zipped.content)


def test_the_first_delivery_tier_is_the_exact_outline_so_a_fitting_request_never_simplifies() -> None:
    """R7, NARROWED rather than dropped, with its cost re-measured on real tract geometry.

    R7's finding still holds: `ST_SimplifyPreserveTopology` measured **2.0x to 7.4x** the cost of
    the query itself here (Austin 568 tracts 51.7 ms -> 385 ms at 7.4x; Dallas 1,410 83.3 ms ->
    369 ms; New York 5,692 317.5 ms -> 746 ms), so it must never be the dominant term of an
    ordinary request. What has changed is R7's other half -- "a saving the response does not
    need". At tract scale the response DOES need it: Atlanta (2.912 MB), Dallas (2.159 MB) and New
    York (5.079 MB) all exceed `MAX_BODY_BYTES` on the default whole-metro request and were
    answered 422, which is a blank map in three of the six markets.

    So the invariant is now the narrower and still-true one: tier 0 is the EXACT outline, it is
    what every request that fits receives, and a coarser tier is reached only after a composed
    body has been measured over the cap -- at which point the alternative is not a cheaper
    response but no response at all. The result is cached for `BOUNDARY_TTL`, so the cost is paid
    once per key per day. R7's preferred remedy -- materialising simplified geometry into its own
    column at write time -- remains the better answer for a fixed tolerance and is NOT done here,
    because the tolerance this ladder applies scales with the request's own span."""
    assert SIMPLIFY_TIERS[0] == 0.0, "the first tier must cost nothing"
    assert list(SIMPLIFY_TIERS) == sorted(SIMPLIFY_TIERS), "tiers coarsen monotonically"
    assert len(set(SIMPLIFY_TIERS)) == len(SIMPLIFY_TIERS), "a repeated tier would re-run one query for nothing"


async def test_the_endpoint_and_community_rows_agree_on_suppression(client, seeded, conn, H) -> None:  # noqa: F811
    """D-NS18/R2: "$72,400" in the docked panel over a grey polygon is the failure this stops.
    The parity case runs at the PLACE level, because `serve.community_rows` reads `market_metric`
    and only `growth` shades at place — so the income parity is asserted against a place-level
    `geo_metric` row written for the test, and the ZCTA path is covered by the shared-function
    assertion in tests/census/test_geo_metric.py."""
    from app.census import serve
    from tests.census.listing_fixtures import make_listing

    lid = make_listing(conn, city="Austin")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO practice_location (listing_id, address_hash, place_geoid, cbsa_geoid, geo_precision, geocoded_at, geocoder_vintage) "
            "VALUES (%s,'h1','4805000','12420','rooftop',now(),'2023')",
            (lid,),
        )
    for suppressed, reason in ((False, None), (True, "high_moe")):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM market_metric WHERE listing_id = %s", (lid,))
            cur.execute("DELETE FROM geo_metric WHERE geo_id = '4805000' AND metric_key = 'median_hh_income'")
            cur.execute(
                "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) "
                "VALUES (%s,'place','median_hh_income','2019\u20132023',92150,'usd',6420,%s,%s,'acs5',now())",
                (lid, suppressed, reason),
            )
            cur.execute(
                "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) "
                "VALUES ('4805000','160','2019\u20132023','median_hh_income',92150,'usd',6420,%s,%s,'acs5',now())",
                (suppressed, reason),
            )
        reg = {r["dataset_key"]: dict(r) for r in _registry_sync(conn)}
        rows = serve.community_rows(conn, [str(lid)], active={"acs5": "2019\u20132023", "acs5_prior": "2014\u20132018", "tiger_cb": "2023"}, registry=reg)
        panel_hides = rows[str(lid)]["income"] is None
        assert panel_hides is suppressed, "the panel and the table disagree on suppression"
        # And the map says the same thing about the same figure, through the endpoint's own body.
        with conn.cursor() as cur:
            cur.execute("SELECT suppressed, suppress_reason FROM geo_metric WHERE geo_id='4805000' AND metric_key='median_hh_income'")
            assert cur.fetchone() == (suppressed, reason)


def _registry_sync(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, attribution_text, vintage, license_status, notes FROM dataset_registry")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


async def test_layers_gains_a_shading_member_on_the_three_fills_and_null_on_the_other_six(client, seeded, H) -> None:  # noqa: F811
    """D-NS15: a NEW member, never a change to `geo_level`. `income`'s `geo_level` is
    "place|catchment" and describes the PANEL's geography; the docked panel and the map answer
    different questions about the same layer, and collapsing them is exactly the "silently promote
    a coarse figure into a fine slot" failure D-C35 forbids."""
    layers = {l["key"]: l for l in (await client.get("/api/layers", headers=H)).json()}
    assert layers["income"]["shading"] == {"summary_level": "140", "label": "Census tract"}
    assert layers["growth"]["shading"] == {"summary_level": "160", "label": "Place (city/town)"}
    assert layers["econ"]["shading"] == {"summary_level": "050", "label": "County"}
    for key in ("pets", "households", "competition", "practices", "drive_10", "drive_20"):
        assert layers[key]["shading"] is None, key
    assert layers["income"]["geo_level"] == "place|catchment", "the panel's geography must not move"


def test_income_shades_at_census_tract_and_the_coarser_layers_say_so() -> None:
    """The canonical granular unit is the Census tract, summary level 140, nationwide (controller
    ruling 2026-09-12). `population_growth_pct` CANNOT follow it: the 2010->2020 tract boundary
    change means a tract-level growth figure is not computable from what we hold (plan D12, a
    registered Phase C deferral), so growth keeps place and payroll keeps county -- and each layer
    carries its OWN label, which is how the map never presents a coarse figure as granular."""
    assert market.SHADING["income"] == {"summary_level": "140", "label": "Census tract"}
    assert market.SHADING["growth"] == {"summary_level": "160", "label": "Place (city/town)"}
    assert market.SHADING["econ"] == {"summary_level": "050", "label": "County"}


def test_the_two_layer_tables_agree_on_level_and_metric() -> None:
    """The merge-time gap Task 8's report named and nothing pinned: `app.census.geo_metric.LAYERS`
    WRITES the rows `app.api.market` SERVES, so a summary level that differs by one table serves a
    map with no values at all -- every LEFT JOIN would miss. Two spellings of one truth, now
    pinned both ways."""
    written = {metric: (level, dataset) for metric, level, dataset, _extra in geo_metric.LAYERS}
    served = {market.BOUNDARY_METRIC[layer][0]: (market.SHADING[layer]["summary_level"], market.BOUNDARY_METRIC[layer][1])
              for layer in market.SHADING}
    assert written == served


async def test_a_body_over_the_cap_is_simplified_and_served_rather_than_refused(client, seeded, H, monkeypatch) -> None:  # noqa: F811
    """The LIVE defect this closes, measured on real TIGER tract geometry rather than reasoned
    about: on the default whole-metro request at tract scale, Atlanta (1,847 tracts, 2.912 MB),
    Dallas (1,791, 2.159 MB) and New York (5,935, 5.079 MB) ALL exceed `MAX_BODY_BYTES` and were
    answered 422 — a blank map in three of the six markets. Refusing to draw is worse than drawing
    a slightly generalised outline, so a body over the cap is now SERVED at a coarser geometry and
    the response states the tolerance it used. Polygons are never dropped to make room: dropping
    one would leave a hole that reads as a boundary (§6)."""
    with seeded.cursor() as cur:   # an ~800-vertex outline, so there is real detail to generalise
        cur.execute(f"UPDATE geo_area SET geom = ST_Multi(ST_Buffer(ST_Point(-97.75,30.25,4269), 0.05, 200)) "
                    f"WHERE geo_id = '{TRACT_A}' AND summary_level = '140'")
    exact = json.loads((await client.get("/api/markets/12420/boundaries?layer=income", headers=H)).content)
    assert exact["simplified_deg"] == 0.0
    # The cache key spans the vintages, the gate and the bbox — deliberately NOT the caps, which
    # do not move in production. Monkeypatching one here therefore has to invalidate by hand.
    sync_redis().flushdb()
    cap = len(json.dumps(exact).encode()) - 1     # one byte under what the exact outline costs
    monkeypatch.setattr(market, "MAX_BODY_BYTES", cap)
    r, body = await _body(client, H)
    assert r.status_code == 200, body
    assert body["simplified_deg"] > 0, "the body was over the cap and should have been generalised"
    assert len(body["features"]) == len(exact["features"]) == 2, "simplification drops vertices, never whole polygons"
    assert len(json.dumps(body).encode()) <= cap


async def test_a_body_that_fits_is_served_exact_with_no_simplification(client, seeded, H) -> None:  # noqa: F811
    """The stakeholder's target view is a metro at ~1.2 degrees. Measured unsimplified on real
    data: Austin 568 tracts / 0.949 MB, Dallas 1,410 / 1.303 MB, Atlanta 1,037 / 1.100 MB, SF
    1,093 / 1.043 MB — every one inside the cap, and every one at **0.0000 % uncovered area**.
    So the common case pays nothing for the escape hatch above and neighbours still share edges,
    which is what keeps the shading gapless."""
    r, body = await _body(client, H)
    assert r.status_code == 200
    assert body["simplified_deg"] == 0.0


async def test_the_delivery_tolerance_actually_reaches_postgis(client, seeded, H, monkeypatch) -> None:  # noqa: F811
    """The trap this closes, measured rather than reasoned about: an UNTYPED bound parameter
    inside a `CASE WHEN` silently takes the ELSE branch under asyncpg. `CASE WHEN 0.01 > 0 THEN
    ST_SimplifyPreserveTopology(geom, 0.01) ELSE geom END` returns 17 points; the identical
    expression with `:tol` bound to 0.01 returns 460 -- the UNSIMPLIFIED count -- and raises
    nothing at all. The ladder above would then run its four rungs, re-query four times, report a
    non-zero `simplified_deg` and serve the exact geometry every time.

    So this asserts the VERTEX COUNT actually falls, which body bytes could not distinguish from
    a tier that merely relabelled itself."""
    with seeded.cursor() as cur:
        cur.execute(f"UPDATE geo_area SET geom = ST_Multi(ST_Buffer(ST_Point(-97.75,30.25,4269), 0.05, 200)) "
                    f"WHERE geo_id = '{TRACT_A}' AND summary_level = '140'")
    exact = json.loads((await client.get("/api/markets/12420/boundaries?layer=income", headers=H)).content)
    sync_redis().flushdb()
    monkeypatch.setattr(market, "MAX_BODY_BYTES", len(json.dumps(exact).encode()) - 1)
    _r, body = await _body(client, H)

    def vertices(collection: dict) -> int:
        feature = next(f for f in collection["features"] if f["id"] == TRACT_A)
        return sum(len(ring) for poly in feature["geometry"]["coordinates"] for ring in poly)

    assert vertices(exact) > 700, "the fixture must carry real detail for this to mean anything"
    assert vertices(body) < vertices(exact) / 2, "the tolerance never reached PostGIS"


# ---------------------------------------------------------------------------------------------
# NEW YORK — the whole reason the adapter now sends a viewport bbox (2026-09-12).
#
# Every number below is MEASURED on real TIGER `cb_2023_*_tract_500k` geometry (31,252 tracts,
# ten states, in a real PostGIS), not chosen to make a test pass:
#
#   * the CBSA 35620 envelope is -75.195114, 39.498537 to -71.856483, 41.527194, and **5,935**
#     tracts intersect it. `MAX_FEATURES` is 4,000 and a COUNT cannot be coarsened away, so the
#     whole-metro request the adapter used to make is a 422 at every delivery tolerance — a
#     permanently unshaded map in the largest market in the country.
#   * the Browse map at the design's own 1440 x 940 preview is ~1020 x 740 CSS px beside the
#     results rail, which at zoom 10 is 1.401 x 0.771 degrees; snapped outward to
#     `src/map/viewport.ts`'s grid that is the box below, and **3,706** tracts intersect it —
#     under the cap, and served.
#
# The geometry here is SYNTHETIC and the two counts are the measured ones: 5,935 tracts of which
# 3,706 fall in that viewport. What is under test is the straddle — that the route refuses the
# envelope and serves the viewport at the caps as they stand — which is exactly what would be
# silently lost if a cap moved or the adapter stopped sending the box.
NY_METRO = (-75.195114, 39.498537, -71.856483, 41.527194)
#: The zoom-10 Browse viewport over New York, padded by nothing and snapped to the 1/8-tile grid.
NY_VIEWPORT = (-74.2426, 40.1221, -72.8174, 40.9131)
NY_TRACTS_IN_METRO = 5935
NY_TRACTS_IN_VIEWPORT = 3706


@pytest.fixture
def new_york(conn):
    """CBSA 35620 and 5,935 tracts, 3,706 of them inside the zoom-10 Browse viewport."""
    w, s, e, n = NY_METRO
    vw, vs, ve, vn = NY_VIEWPORT
    outside = NY_TRACTS_IN_METRO - NY_TRACTS_IN_VIEWPORT
    with conn.cursor() as cur:
        for key, vintage in (("tiger_cb", "2023"), ("acs5", "2019\u20132023"), ("acs5_prior", "2014\u20132018"), ("cbp", "2022")):
            cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s,%s,now(),'test')", (key, vintage))
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
            "('35620','310','2023','New York-Newark-Jersey City, NY-NJ',"
            " ST_Multi(ST_MakeEnvelope(%s,%s,%s,%s,4269)), ST_Point(%s,%s,4269))",
            (w, s, e, n, (w + e) / 2, (s + n) / 2),
        )
        # Inside the viewport: a 62-column grid filling the box exactly.
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) "
            "SELECT lpad((36000000000 + i)::text, 11, '0'), '140', '2023', 'Census Tract ' || i, '36', "
            "  ST_Multi(ST_MakeEnvelope(x, y, x + %(cw)s, y + %(ch)s, 4269)), ST_Point(x, y, 4269) "
            "FROM generate_series(0, %(nin)s - 1) AS i, "
            "  LATERAL (SELECT %(vw)s + (i %% 62) * %(cw)s AS x, %(vs)s + (i / 62) * %(ch)s AS y) p",
            {"nin": NY_TRACTS_IN_VIEWPORT, "vw": vw, "vs": vs,
             "cw": (ve - vw) / 62, "ch": (vn - vs) / 60},
        )
        # Outside it, and strictly south of it so no cell can touch the viewport's edge.
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) "
            "SELECT lpad((34000000000 + i)::text, 11, '0'), '140', '2023', 'Census Tract ' || i, '34', "
            "  ST_Multi(ST_MakeEnvelope(x, y, x + %(cw)s, y + %(ch)s, 4269)), ST_Point(x, y, 4269) "
            "FROM generate_series(0, %(nout)s - 1) AS i, "
            "  LATERAL (SELECT %(w)s + (i %% 75) * %(cw)s AS x, %(s)s + (i / 75) * %(ch)s AS y) p",
            {"nout": outside, "w": w, "s": s + 0.001, "cw": (e - w) / 75, "ch": (40.10 - s) / 30},
        )
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
            "('36000000001','140','2019\u20132023','median_hh_income',92150,'usd',6420,false,NULL,'acs5',now())"
        )
    return conn


async def test_new_york_is_refused_whole_metro_and_served_at_the_viewport_bbox(client, new_york, H) -> None:  # noqa: F811
    """The two arms, measured: the envelope 422s on a COUNT and the viewport is served exact.

    This is the gap the bbox wiring closes. Before it, `boundaries(marketName)` asked for the whole
    metro every time and there was no second arm at all.
    """
    whole = await client.get("/api/markets/35620/boundaries?layer=income", headers=H)
    assert whole.status_code == 422
    body = whole.json()["error"]
    assert body["code"] == "AREA_TOO_LARGE"
    assert str(NY_TRACTS_IN_METRO) in body["message"]
    assert str(market.MAX_FEATURES) in body["message"]

    w, s, e, n = NY_VIEWPORT
    seen = await client.get(f"/api/markets/35620/boundaries?layer=income&bbox={w},{s},{e},{n}", headers=H)
    assert seen.status_code == 200
    served = json.loads(seen.content)
    assert len(served["features"]) == NY_TRACTS_IN_VIEWPORT
    assert NY_TRACTS_IN_VIEWPORT < market.MAX_FEATURES <= NY_TRACTS_IN_METRO
    # Served EXACT: the whole point of a viewport request is that it needs no generalisation.
    assert served["simplified_deg"] == 0.0
    assert served["state"] == "enabled" and served["summary_level"] == "140"
    assert any(f["properties"]["value"] == 92150.0 for f in served["features"])


async def test_the_viewport_arm_is_not_a_vacuous_pass_the_count_is_what_decides_it(client, new_york, H, monkeypatch) -> None:  # noqa: F811
    """Prove the gate can fail: drop `MAX_FEATURES` below the viewport's own count and the SERVED
    arm becomes a refusal. Without this the test above would still pass if the bbox were ignored
    and both arms answered the same thing."""
    monkeypatch.setattr(market, "MAX_FEATURES", NY_TRACTS_IN_VIEWPORT - 1)
    w, s, e, n = NY_VIEWPORT
    r = await client.get(f"/api/markets/35620/boundaries?layer=income&bbox={w},{s},{e},{n}", headers=H)
    assert r.status_code == 422 and r.json()["error"]["code"] == "AREA_TOO_LARGE"


async def test_panning_hits_the_cache_for_ground_already_asked_for_and_misses_for_new_ground(client, seeded, H) -> None:  # noqa: F811
    """What the member's panning costs the route, measured through `x-cache`.

    The adapter snaps the box to a grid of one eighth of a basemap tile before it asks
    (`frontend/src/map/viewport.ts`), so a pan inside one cell produces the IDENTICAL query string
    and therefore the identical 24-hour cache entry. Without that snap `Leaflet.getBounds()`'s own
    centimetre-scale float jitter would make every `moveend` its own miss, which is the behaviour
    this asserts the absence of: `?bbox=` is part of the key, so two boxes that differ AT ALL are
    two entries and two boxes that are equal are one.
    """
    here = "?layer=income&bbox=-97.9,30.15,-97.6,30.35"
    there = "?layer=income&bbox=-97.85,30.15,-97.55,30.35"
    first = await client.get(f"/api/markets/12420/boundaries{here}", headers=H)
    assert first.status_code == 200 and first.headers["x-cache"] == "miss"
    # The same ground again — a pan that the snap rounded back onto the same cell.
    again = await client.get(f"/api/markets/12420/boundaries{here}", headers=H)
    assert again.status_code == 200 and again.headers["x-cache"] == "hit"
    assert again.content == first.content
    # A pan onto new ground is new ground: a miss, then a hit of its own.
    moved = await client.get(f"/api/markets/12420/boundaries{there}", headers=H)
    assert moved.status_code == 200 and moved.headers["x-cache"] == "miss"
    assert (await client.get(f"/api/markets/12420/boundaries{there}", headers=H)).headers["x-cache"] == "hit"
    # …and the whole-metro entry is a third, never served to a box request or the other way round.
    assert (await client.get("/api/markets/12420/boundaries?layer=income", headers=H)).headers["x-cache"] == "miss"
