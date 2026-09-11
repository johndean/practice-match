"""GET /api/markets/{cbsa}/boundaries — the member-gated boundary layer (D-NS10 through D-NS18).

Reuses tests/census/test_market_api.py's `client` and `H` fixtures: one scratch database per test,
a real `buyer` session presented as a literal Cookie header (Task I9a).
"""
from __future__ import annotations

import json

import pytest

from app.api import market
from app.cache import sync_redis
from app.census import gate, geo_metric
from app.config import settings
from tests.api.conftest import auth_headers
from tests.census.test_market_api import H, client  # noqa: F401 -- the fixtures, by name

AUSTIN = "POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))"
INSIDE = "POLYGON((-97.8 30.2,-97.7 30.2,-97.7 30.3,-97.8 30.3,-97.8 30.2))"


@pytest.fixture
def seeded(conn):
    """One metro, two ZCTAs inside it, one place inside it, and the four active vintages.

    `78704` carries a measured median; `78745` carries a SUPPRESSED one. The place row exists so a
    `growth` request has a geography at level `160` to shade — the two layers are deliberately
    different geographies (D-C35), and a fixture that only carried ZCTAs could not tell them apart.
    """
    with conn.cursor() as cur:
        for key, vintage in (("tiger_cb", "2023"), ("acs5", "2019\u20132023"), ("acs5_prior", "2014\u20132018"), ("cbp", "2022")):
            cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s,%s,now(),'test')", (key, vintage))
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
            "('12420','310','2023','Austin-Round Rock-San Marcos, TX Metro Area', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.5,30.5,4269))",
            (AUSTIN,),
        )
        for geo_id, name in (("78704", "ZCTA5 78704"), ("78745", "ZCTA5 78745")):
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
                "(%s,'860','2023',%s, ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.25,4269))",
                (geo_id, name, INSIDE),
            )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES "
            "('4805000','160','2023','Austin','48', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.25,4269))",
            (INSIDE,),
        )
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
            "('78704','860','2019\u20132023','median_hh_income',92150,'usd',6420,false,NULL,'acs5',now()), "
            "('78745','860','2019\u20132023','median_hh_income',41000,'usd',40000,true,'high_moe','acs5',now())"
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
    assert (body["summary_level"], body["geo_label"], body["unit"]) == ("860", "ZIP Code Tabulation Area", "usd")
    assert (body["state"], body["boundary_vintage"], body["value_vintage"], body["source_dataset"]) == ("enabled", "2023", "2019\u20132023", "acs5")
    assert body["attribution"][0] == "Boundaries: U.S. Census Bureau, TIGER/Line Cartographic Boundary Files 2023"
    assert body["attribution"][1].startswith("Source: U.S. Census Bureau, American Community Survey")
    assert body["values_without_geometry"] == 0
    by = {f["id"]: f for f in body["features"]}
    assert sorted(by) == ["78704", "78745"]
    assert by["78704"]["properties"] == {
        "geo_id": "78704", "name": "ZCTA5 78704", "value": 92150.0, "moe": 6420.0,
        "suppressed": False, "suppress_reason": None, "band_ambiguous": False,
    }
    assert by["78745"]["properties"]["suppressed"] is True and by["78745"]["properties"]["suppress_reason"] == "high_moe"
    # A suppressed figure never reaches the wire: the polygon is greyed, and the number that was
    # too imprecise to publish is not smuggled out in the margin's company (§6).
    assert by["78745"]["properties"]["value"] is None
    # 4326, not geo_area's own 4269.
    assert by["78704"]["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert by["78704"]["geometry"]["coordinates"][0][0][0] == pytest.approx([-97.8, 30.2], abs=1e-4)


async def test_a_polygon_with_no_row_at_all_is_returned_with_a_null_value_and_is_never_omitted(client, seeded, conn, H) -> None:  # noqa: F811
    """D-NS16: omitting it leaves a hole, and a hole on a choropleth reads as a boundary — a park,
    a lake, or the edge of the market, none of which is what happened. The sentinel is
    `value: null` with `suppressed: false`, which is NOT what a suppressed polygon carries, so a
    client that guards on `suppressed` alone would paint this one as measured."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM geo_metric WHERE geo_id = '78745'")
    _r, body = await _body(client, H)
    missing = next(f for f in body["features"] if f["id"] == "78745")
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
        cur.execute("DELETE FROM geo_metric WHERE geo_id = '78704'")
    _r, body = await _body(client, H)
    by = {f["id"]: f["properties"] for f in body["features"]}
    assert by["78704"]["value"] is None and by["78745"]["value"] is None
    assert (by["78704"]["suppressed"], by["78704"]["suppress_reason"]) == (False, None)
    assert (by["78745"]["suppressed"], by["78745"]["suppress_reason"]) == (True, "high_moe")
    assert by["78704"] != by["78745"]


async def test_a_value_with_no_geometry_is_dropped_and_counted(client, seeded, conn, H) -> None:  # noqa: F811
    """§7, the other direction: the writer never invents a shape, and the endpoint never silently
    loses a row. A non-zero counter on a metro that has previously reported zero is how a boundary
    vintage that moved out from under the values announces itself."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, source_dataset, computed_at) "
            "VALUES ('99999','860','2019\u20132023','median_hh_income',50000,'usd','acs5',now())"
        )
    _r, body = await _body(client, H)
    assert body["values_without_geometry"] == 1
    assert "99999" not in [f["id"] for f in body["features"]]


async def test_band_ambiguity_is_computed_server_side_from_the_designs_own_stops(client, seeded, conn, H) -> None:  # noqa: F811
    with conn.cursor() as cur:
        cur.execute("UPDATE geo_metric SET moe = 9000 WHERE geo_id = '78704'")
    _r, body = await _body(client, H)
    assert next(f for f in body["features"] if f["id"] == "78704")["properties"]["band_ambiguous"] is True


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


def test_no_sql_string_in_this_module_simplifies_geometry_on_the_request_path() -> None:
    """R7. ST_SimplifyPreserveTopology measured five to EIGHT times the cost of the query itself,
    which makes it the dominant term of every request for a saving the response does not need.
    Simplification belongs at write time or not at all: if a future geography needs it, the
    simplified geometry is materialised into its own column by the nightly job, once per vintage."""
    from pathlib import Path

    source = Path(market.__file__).read_text(encoding="utf-8")
    assert "ST_Simplify" not in source


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
    assert layers["income"]["shading"] == {"summary_level": "860", "label": "ZIP Code Tabulation Area"}
    assert layers["growth"]["shading"] == {"summary_level": "160", "label": "Place (city/town)"}
    assert layers["econ"]["shading"] == {"summary_level": "050", "label": "County"}
    for key in ("pets", "households", "competition", "practices", "drive_10", "drive_20"):
        assert layers[key]["shading"] is None, key
    assert layers["income"]["geo_level"] == "place|catchment", "the panel's geography must not move"


def test_the_shaded_layers_and_the_writers_LAYERS_are_one_truth() -> None:
    """`app.census.geo_metric.LAYERS` (Task 8, the only writer of `geo_metric`) and this module's
    `SHADING` + `BOUNDARY_METRIC` (Task 9, the only reader) spell the same three facts twice —
    metric_key, summary_level, and the dataset the rows are STAMPED with. Task 8's own report
    flagged that nothing pinned them; this is that pin, closed in the merge rather than after it.

    The failure it stops is SILENT, which is why a pin and not a comment: let the two drift and the
    endpoint reads level "860" for a metric the writer materialised at "160", finds nothing, and
    returns a well-formed EMPTY FeatureCollection — a map with no shading, no error, and no log
    line. Two spellings of one truth is this project's most-repeated defect class.

    Deliberately OUT of scope: `market.LAYERS["growth"]["dataset_key"]` is `acs5_prior`, which is
    the LICENCE gate's key, not the stamp. The rows are stamped `acs5` and `acs5_prior` is carried
    in the writer's own fourth element ("also gated on"). Pinning those two together would assert a
    falsehood — they are different questions about the same layer, as D-NS15 is for `geo_level`.
    """
    writer = {metric: (level, source) for metric, level, source, _also_gated_on in geo_metric.LAYERS}
    assert len(writer) == len(geo_metric.LAYERS), "a metric_key is spelled twice in geo_metric.LAYERS"
    assert writer, "vacuous: the writer declares no layers at all"

    assert set(market.SHADING) == set(market.BOUNDARY_METRIC), (
        "every shaded layer needs both a geography (SHADING) and a metric (BOUNDARY_METRIC); "
        f"SHADING-only={set(market.SHADING) - set(market.BOUNDARY_METRIC)}, "
        f"BOUNDARY_METRIC-only={set(market.BOUNDARY_METRIC) - set(market.SHADING)}"
    )
    reader = {
        market.BOUNDARY_METRIC[layer][0]: (market.SHADING[layer]["summary_level"], market.BOUNDARY_METRIC[layer][1])
        for layer in market.SHADING
    }
    assert len(reader) == len(market.SHADING), "two shaded layers claim the same metric_key"

    # Two-way by construction: dict equality names a layer either side is missing AND a fact either
    # side spells differently, in one assertion.
    assert reader == writer, "the boundary endpoint and the geo_metric writer disagree"
