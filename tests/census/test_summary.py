"""GET /api/markets/{cbsa}/summary — the metro-wide summary the Market snapshot's AREA mode reads
(Task SNAP; ruling D-C50 as revised by the stakeholder, 2026-09-12).

The Browse "Market snapshot" strip used to compute a "metro median" from `communities()` — one row
per LISTING, each hospital's five-mile ring — while the map beside it paints Census geography per
layer. Dallas read Households **162K** over tracts that hold 0\u20135,988 and Competition **41** over
ZIP areas that hold 3\u201316. The stakeholder ruled the map correct and the snapshot wrong, so the
strip now summarises the polygons the map shades, and this is the route that measures them.

Reuses `tests/census/test_market_api.py`'s `client` and `H` fixtures — one scratch database per
test, a real `buyer` session presented as a literal Cookie header (Task I9a) — exactly as
`tests/census/test_boundaries.py` does for the sibling route.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api import market
from app.cache import sync_redis
from app.census import gate, geo_metric
from app.config import settings
from tests.api.conftest import auth_headers
from tests.census.test_market_api import H, client  # noqa: F401 -- the fixtures, by name

ROOT = Path(__file__).resolve().parents[2]
AUSTIN = "POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))"
INSIDE = "POLYGON((-97.8 30.2,-97.7 30.2,-97.7 30.3,-97.8 30.3,-97.8 30.2))"
OUTSIDE = "POLYGON((-90 40,-89 40,-89 41,-90 41,-90 40))"
#: Nine measured tract incomes, 10K to 90K. `percentile_cont` interpolates at `p * (n - 1)`, so
#: over nine sorted values the five fractions land at 0.8, 2, 4, 6 and 7.2 — 18K (interpolated),
#: 30K, 50K, 70K and 82K (interpolated). Chosen so the two INTERPOLATED fractions fall between
#: values rather than on them: a fixture where every quantile happens to be a member of the set
#: cannot tell `percentile_cont` from `percentile_disc` or from a hand-rolled nearest-rank.
MEASURED = [10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000]
QUANTILES = [18000.0, 30000.0, 50000.0, 70000.0, 82000.0]


def _tract(i: int) -> str:
    """A real-shaped Travis County tract geoid: state(2) + county(3) + tract(6), eleven digits."""
    return f"48453{i:06d}"


@pytest.fixture
def seeded(conn):
    """One metro; eleven tracts inside it (nine measured, one suppressed, one with no metric row
    at all) and one tract OUTSIDE the metro envelope; a place, a county and a ZIP area so the
    coarser layers have a geography of their own; and the five active vintages.

    The out-of-metro tract is the case a summary over "every polygon of that level" would get
    wrong in the direction nobody would notice: it carries a value, so including it moves the
    median without emptying anything.

    Redis is flushed because this route's cache key spans the vintages, the licence gate and the
    writer's version — none of which changes between tests in this file — so a body cached by an
    earlier test would otherwise be served to a later one. `tests/census/test_boundaries.py` does
    the same, for the same reason.
    """
    sync_redis().flushdb()
    with conn.cursor() as cur:
        for key, vintage in (("tiger_cb", "2023"), ("acs5", "2019\u20132023"),
                             ("acs5_prior", "2014\u20132018"), ("cbp", "2022"), ("zbp", "2022")):
            cur.execute("INSERT INTO active_vintage (dataset_key, vintage, activated_at, activated_by) VALUES (%s,%s,now(),'test')", (key, vintage))
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
            "('12420','310','2023','Austin-Round Rock-San Marcos, TX Metro Area', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.5,30.5,4269))",
            (AUSTIN,),
        )
        for i in range(11):
            cur.execute(
                "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, geom, centroid) VALUES "
                "(%s,'140','2023',%s,'48','453', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.25,4269))",
                (_tract(i), f"Census Tract {i}", INSIDE),
            )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, geom, centroid) VALUES "
            "('17031000100','140','2023','Census Tract far away','17','031', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-89.5,40.5,4269))",
            (OUTSIDE,),
        )
        for i, value in enumerate(MEASURED):
            cur.execute(
                "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
                "(%s,'140','2019\u20132023','median_hh_income',%s,'usd',100,false,NULL,'acs5',now())",
                (_tract(i), value),
            )
        # Tract 9 is SUPPRESSED (a published estimate the margin rules hide) and tract 10 has no
        # row at all. Both are counted, neither reaches a quantile.
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
            "(%s,'140','2019\u20132023','median_hh_income',999999,'usd',900000,true,'high_moe','acs5',now())",
            (_tract(9),),
        )
        # …and the far tract carries a value that would drag the median if the envelope were
        # ignored.
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
            "('17031000100','140','2019\u20132023','median_hh_income',1,'usd',1,false,NULL,'acs5',now())"
        )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, geom, centroid) VALUES "
            "('4805000','160','2023','Austin','48', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.25,4269))",
            (INSIDE,),
        )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, state_fips, county_fips, geom, centroid) VALUES "
            "('48453','050','2023','Travis County','48','453', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.25,4269))",
            (INSIDE,),
        )
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
            "('78704','860','2023','ZCTA5 78704', ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(-97.75,30.25,4269))",
            (INSIDE,),
        )
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, is_derived, formula_version, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
            "('4805000','160','2019\u20132023','population_growth_pct',11.6,'pct',NULL,true,'v1',false,NULL,'acs5',now()), "
            "('48453','050','2022','revenue_per_establishment',818000,'usd',NULL,true,'v1',false,NULL,'cbp',now()), "
            "('78704','860','2022','establishments',7,'count',NULL,false,NULL,false,NULL,'zbp',now())"
        )
        for i, value in enumerate((1400, 1500, 1600)):
            cur.execute(
                "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, moe, suppressed, suppress_reason, source_dataset, computed_at) VALUES "
                "(%s,'140','2019\u20132023','households',%s,'count',20,false,NULL,'acs5',now())",
                (_tract(i), value),
            )
    return conn


async def _body(client, H, cbsa: str = "12420"):  # noqa: F811  (`client`/`H` the fixtures, by name)
    r = await client.get(f"/api/markets/{cbsa}/summary", headers=H)
    return r, r.json()


def _layer(body: dict, key: str) -> dict:
    return next(l for l in body["layers"] if l["layer"] == key)


async def test_the_route_is_guarded_by_the_same_dependency_object_as_its_siblings(client, seeded, member, monkeypatch) -> None:  # noqa: F811
    path = "/api/markets/12420/summary"
    assert (await client.get(path)).status_code == 401
    _aid, cookies, _csrf = member(("buyer",))
    assert (await client.get(path, headers=auth_headers(cookies))).status_code == 200
    monkeypatch.setattr(settings, "market_data_public", True)
    assert (await client.get(path)).status_code == 200
    # By IDENTITY, the way tests/auth/test_permissions.py resolves a guard: a fresh
    # `require("market.read")` per route reads as unguarded (market.py's correction 4).
    route = next(r for r in market.router.routes if getattr(r, "path", "") == "/api/markets/{cbsa}/summary")
    assert any(d.call is market.REQUIRE_MARKET_READ for d in route.dependant.dependencies)


async def test_a_layer_carries_the_median_the_quantiles_and_the_three_counts(client, seeded, H) -> None:  # noqa: F811
    """The numbers the AREA cards print, measured rather than asserted from memory: nine measured
    tracts inside the metro give `percentile_cont`'s own interpolated five, and the median is the
    middle one of those five rather than a second, separately-computed figure that could disagree
    with the bars drawn beside it."""
    r, body = await _body(client, H)
    assert r.status_code == 200
    assert body["cbsa_geoid"] == "12420" and body["boundary_vintage"] == "2023"
    income = _layer(body, "income")
    assert (income["summary_level"], income["geo_label"], income["unit"]) == ("140", "Census tract", "usd")
    assert (income["state"], income["value_vintage"], income["source_dataset"]) == ("enabled", "2019\u20132023", "acs5")
    assert income["quantiles"] == QUANTILES
    assert income["median"] == QUANTILES[2], "the median must BE the middle quantile, not a second computation of it"
    # Eleven tracts intersect the metro envelope; the twelfth is 600 miles away and carries a
    # value, so a summary that ignored the envelope would report twelve and a lower median.
    assert (income["count"], income["with_value"], income["suppressed"], income["no_data"]) == (11, 9, 1, 1)
    assert income["count"] == income["with_value"] + income["suppressed"] + income["no_data"]


async def test_a_suppressed_or_absent_value_is_counted_and_never_summarised(client, seeded, conn, H) -> None:  # noqa: F811
    """The suppressed tract carries 999999 — an order of magnitude above every measured one — and
    the no-row tract carries nothing. Neither may reach a quantile, and both must be counted,
    because "this metro has eleven tracts and we can only summarise nine of them" is the honest
    statement and "this metro has nine tracts" is not."""
    _r, body = await _body(client, H)
    income = _layer(body, "income")
    assert max(income["quantiles"]) == 82000.0, "a suppressed figure reached the distribution"

    # Suppress every remaining measured tract: the layer keeps its title, its geography and its
    # counts, and answers with NO figures at all (A21.2n/o's posture, one level down).
    with conn.cursor() as cur:
        cur.execute("UPDATE geo_metric SET suppressed = true, suppress_reason = 'high_moe' WHERE metric_key = 'median_hh_income'")
    sync_redis().flushdb()
    _r, body = await _body(client, H)
    income = _layer(body, "income")
    assert (income["median"], income["quantiles"]) == (None, None)
    assert (income["count"], income["with_value"], income["suppressed"], income["no_data"]) == (11, 0, 10, 1)


async def test_every_shaded_layer_answers_at_its_own_geography(client, seeded, H) -> None:  # noqa: F811
    """One row per layer the map shades, each naming the geography it was measured at — the whole
    point of the ruling, since a card that borrows another layer's geography is the defect D-C50
    removed one surface over."""
    _r, body = await _body(client, H)
    assert [l["layer"] for l in body["layers"]] == list(market.SHADING)
    for key, level, label in (("income", "140", "Census tract"), ("growth", "160", "Place (city/town)"),
                              ("econ", "050", "County"), ("households", "140", "Census tract"),
                              ("pets", "140", "Census tract"), ("competition", "860", "ZIP Code Tabulation Area")):
        row = _layer(body, key)
        assert (row["summary_level"], row["geo_label"]) == (level, label), key
        assert row["unit"] == market.UNIT[key], key
    # A single-polygon layer still has a distribution: every fraction is that one value.
    assert _layer(body, "competition")["quantiles"] == [7.0] * 5
    assert _layer(body, "competition")["source_dataset"] == "zbp"
    # …and a layer whose geography exists but whose figure was never written is all no-data.
    pets = _layer(body, "pets")
    assert (pets["count"], pets["with_value"], pets["no_data"]) == (11, 0, 11)
    assert pets["median"] is None
    # Households: three of eleven tracts carry the figure, and the quantiles are theirs alone.
    assert _layer(body, "households")["with_value"] == 3
    assert _layer(body, "households")["median"] == 1500.0


async def test_the_attribution_is_read_from_the_registry_boundaries_first(client, seeded, H) -> None:  # noqa: F811
    """Legally load-bearing (Census spec §2b), and never composed here: the geometry's attribution
    leads, then one line per value dataset that actually answered."""
    _r, body = await _body(client, H)
    assert body["attribution"][0].startswith("Boundaries: U.S. Census Bureau, TIGER/Line")
    assert any("American Community Survey" in a for a in body["attribution"])
    assert any("County Business Patterns" in a for a in body["attribution"])
    assert any("ZIP Code Business Patterns" in a for a in body["attribution"])
    # Growth folds in a SECOND ACS vintage, so its prior-period attribution is there too.
    assert any("2014\u20132018" in a for a in body["attribution"])
    assert len(body["attribution"]) == len(set(body["attribution"])), "one line per source"


async def test_a_layer_whose_licence_is_not_cleared_carries_its_state_and_no_figures(client, seeded, conn, H) -> None:  # noqa: F811
    """Exactly the boundary route's gate, and for the same reason: no figure from an uncleared
    dataset reaches the wire, and the answer says WHY rather than 403ing a map that then cannot
    draw the state at all."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'unresolved' WHERE dataset_key = 'zbp'")
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked', notes = 'Licence refused by the vendor.' WHERE dataset_key = 'cbp'")
    gate.invalidate(sync_redis(), "zbp")
    gate.invalidate(sync_redis(), "cbp")
    sync_redis().flushdb()
    _r, body = await _body(client, H)
    comp = _layer(body, "competition")
    assert comp["state"] == "disabled"
    assert (comp["count"], comp["with_value"], comp["median"], comp["quantiles"]) == (0, 0, None, None)
    assert "blocked_reason" not in comp
    econ = _layer(body, "econ")
    assert econ["state"] == "blocked" and econ["blocked_reason"] == "Licence refused by the vendor."
    assert (econ["count"], econ["with_value"], econ["median"]) == (0, 0, None)
    # The cleared layers are untouched, and the withdrawn datasets' attribution is gone with them.
    assert _layer(body, "income")["state"] == "enabled"
    assert not any("Business Patterns" in a for a in body["attribution"])


async def test_growths_own_gate_is_the_prior_acs_vintage(client, seeded, conn, H) -> None:  # noqa: F811
    """Correction 6, applied here: the `geo_metric` rows for `population_growth_pct` are stamped
    `acs5`, while the figure is a difference of two ACS periods — so an `acs5_prior` licence that
    moves must turn the layer off even though the generic per-`source_dataset` gate cannot see it."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'unresolved' WHERE dataset_key = 'acs5_prior'")
    gate.invalidate(sync_redis(), "acs5_prior")
    sync_redis().flushdb()
    _r, body = await _body(client, H)
    assert _layer(body, "growth")["state"] == "disabled"
    assert _layer(body, "income")["state"] == "enabled", "income must not follow growth's own gate"

    # …and the OTHER direction, which is the belt-and-braces arm: growth's catalogue entry names
    # `acs5_prior`, so a withdrawn `acs5` licence leaves `_layer_state` reading "enabled" while the
    # rows themselves are stamped with the dataset that just moved. Without the second check the
    # layer would go on serving figures from an uncleared dataset.
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'cleared' WHERE dataset_key = 'acs5_prior'")
        cur.execute("UPDATE dataset_registry SET license_status = 'unresolved' WHERE dataset_key = 'acs5'")
    gate.invalidate(sync_redis(), "acs5")
    sync_redis().flushdb()
    _r, body = await _body(client, H)
    assert _layer(body, "growth")["state"] == "disabled"
    assert _layer(body, "growth")["with_value"] == 0


async def test_an_unknown_metro_is_a_404_in_decision_a5s_envelope(client, seeded, H) -> None:  # noqa: F811
    r, body = await _body(client, H, "99999")
    assert r.status_code == 404
    assert body == {"error": {"code": "NOT_FOUND", "message": "No such metro."}}


async def test_the_cache_key_carries_the_gate_version_and_the_geo_version(client, seeded, H) -> None:  # noqa: F811
    """§11's one-minute ceiling: a licence decision makes every cached body unreachable in the same
    instant, and so does a nightly rewrite that changes values without moving a vintage."""
    first = await client.get("/api/markets/12420/summary", headers=H)
    assert first.headers["x-cache"] == "miss"
    assert (await client.get("/api/markets/12420/summary", headers=H)).headers["x-cache"] == "hit"
    gate.invalidate(sync_redis(), "acs5")
    assert (await client.get("/api/markets/12420/summary", headers=H)).headers["x-cache"] == "miss"
    sync_redis().set(geo_metric.GEO_VERSION_KEY, 12345)
    assert (await client.get("/api/markets/12420/summary", headers=H)).headers["x-cache"] == "miss"
    assert (await client.get("/api/markets/12420/summary", headers=H)).headers["x-cache"] == "hit"
    # A hit is the same body, byte for byte — the cache holds the answer, never a recomputation.
    assert (await client.get("/api/markets/12420/summary", headers=H)).json() == first.json()


async def test_the_cache_key_carries_every_value_vintage_not_only_the_acs_one(client, seeded, conn, H) -> None:  # noqa: F811
    """One body carries six layers stamped with four datasets, so ONE vintage in the key is not
    enough: activate a new ZIP Business Patterns vintage and the competition card must move, even
    though every ACS figure in the same body is unchanged."""
    assert (await client.get("/api/markets/12420/summary", headers=H)).headers["x-cache"] == "miss"
    assert (await client.get("/api/markets/12420/summary", headers=H)).headers["x-cache"] == "hit"
    with conn.cursor() as cur:
        cur.execute("UPDATE active_vintage SET vintage = '2023' WHERE dataset_key = 'zbp'")
    r = await client.get("/api/markets/12420/summary", headers=H)
    assert r.headers["x-cache"] == "miss"
    assert _layer(r.json(), "competition")["value_vintage"] == "2023"


async def test_the_contract_docs_example_payload_carries_every_member_the_route_emits(client, seeded, H) -> None:  # noqa: F811
    """`docs/integrations/market-data-api.md` is what Sub-project 2 codes against, and a documented
    payload missing a member is one an integrator codes without. Compared against a REAL response
    rather than a typed list, which is the precedent the boundary route's own pin set — a key set
    maintained by hand is the same defect one level up. `blocked_reason` is excluded on purpose: it
    appears only when a licence is withdrawn, so a payload that always carried it would be the
    wrong example."""
    doc = (ROOT / "docs" / "integrations" / "market-data-api.md").read_text(encoding="utf-8")
    section = doc.split("## `GET /api/markets/{cbsa}/summary", 1)[1]
    example = json.loads(section.split("```json", 1)[1].split("```", 1)[0])
    _r, live = await _body(client, H)
    assert set(example) == set(live), (
        "the documented summary payload and the real one carry different members: "
        f"{sorted(set(example) ^ set(live))}"
    )
    assert set(example["layers"][0]) == set(live["layers"][0]), "the documented LAYER shape has drifted"
