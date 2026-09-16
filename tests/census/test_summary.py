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
import logging
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


def drop_summary_cache() -> None:
    """Drop only the keys THIS route writes, never the whole database (review 1, Minor-7).

    `sync_redis()` here is the REAL client at `REDIS_URL`, whose `tests/conftest.py` default is
    `redis://localhost:6380/0` — the shared compose stack's database 0, which also holds every
    other worktree's warm market/listing cache, the local rate-limit buckets and the Celery
    broker. `flushdb()` took all of it, and a reviewer running this file's own command cleared a
    colleague's Redis on 2026-09-14. `tests/census/test_market_api.py`'s `client` fixture — which
    every case in this file takes — already deletes `listing:*`, `backfill:*`, `gate:*` and
    `market:*` by pattern for exactly that reason; `summary:*` is the one prefix it does not cover
    and the only one this file needs, because the cache key is
    `summary:{cbsa}:{vintages}:g{gate}:m{geo}` (`app/api/market.py`) and nothing else in the
    database can serve this route a stale body.
    """
    r = sync_redis()
    for key in r.scan_iter("summary:*"):
        r.delete(key)


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
    drop_summary_cache()
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
    drop_summary_cache()
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
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked', blocked_reason = 'Licence refused by the vendor.' WHERE dataset_key = 'cbp'")
    gate.invalidate(sync_redis(), "zbp")
    gate.invalidate(sync_redis(), "cbp")
    drop_summary_cache()
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
    drop_summary_cache()
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
    drop_summary_cache()
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


async def test_a_cache_miss_logs_its_cost_once_and_a_hit_logs_nothing(client, seeded, H, caplog) -> None:  # noqa: F811
    """Fix round 1's spec gap: the AREA strip waits on this route and its cost was invisible from
    outside the process — six runs of `_SUMMARY_SQL` over the metro's whole envelope per miss,
    with a `percentile_cont` over every valued polygon of each layer's own level. `boundaries` has
    carried one INFO line per miss since fix round 2 of A24 for exactly that reason; this is its
    sibling, in the same shape and with the same rules.

    Identifiers and sizes only: `cbsa` is a Census geoid and the rest are counts and a duration.
    No figure the payload carries — no median, no quantile, no geography NAME — is in it. A cache
    HIT is silent, because a line per request would drown the thing this exists to make visible.
    """
    caplog.set_level(logging.INFO, logger="app.api.market")
    first, body = await _body(client, H)
    assert first.status_code == 200 and first.headers["x-cache"] == "miss"

    lines = [r for r in caplog.records if r.getMessage().startswith("summary miss ")]
    assert len(lines) == 1, [r.getMessage() for r in caplog.records]
    line = lines[0]
    assert line.levelno == logging.INFO
    fields = dict(pair.split("=", 1) for pair in line.getMessage().removeprefix("summary miss ").split(" "))
    assert sorted(fields) == ["cbsa", "layers", "ms", "rows"]
    assert fields["cbsa"] == "12420"
    # Read off the response rather than typed: `layers` is what the body carries and `rows` is the
    # polygons actually counted, summed across them — so a field wired to the wrong value fails.
    assert int(fields["layers"]) == len(body["layers"])
    assert int(fields["rows"]) == sum(l["count"] for l in body["layers"])
    assert int(fields["rows"]) > 0, "the fixture counted no polygons, so `rows` proves nothing"
    assert float(fields["ms"]) >= 0
    # The fixture's own median, by value, and the geography label it carries.
    assert "50000" not in line.getMessage() and "Census tract" not in line.getMessage()

    caplog.clear()
    again, _ = await _body(client, H)
    assert again.headers["x-cache"] == "hit"
    assert [r.getMessage() for r in caplog.records if r.getMessage().startswith("summary miss ")] == []


# ---------------------------------------------------------------------------------------------
# Task SNAP-METRO (family A31.14, 2026-09-14): the Census's OWN published figure for the metro.
#
# The AREA card read "median of 541 Census tracts" — `percentile_cont(0.5)` over the metro's
# valued tracts, 94,801 on CBSA 12420 — while the Census PUBLISHES a metro median household
# income for that same CBSA at summary level 310 (`acs_measure`, B19013_001E = 97,638 ± 1,163,
# 2019-2023). A stakeholder who knows the published figure read two "metro" numbers for one
# metro, which is D-C51's own defect one surface over.
#
# Every fixture below DISCRIMINATES: the published metro figure is nowhere near the median of the
# seeded tracts (97,638 against 50,000), so a route that went on serving the median would fail
# rather than pass by coincidence.
PUBLISHED_INCOME, PUBLISHED_INCOME_MOE = 97638, 1163
PUBLISHED_HOUSEHOLDS, PUBLISHED_HOUSEHOLDS_MOE = 806400, 2100
PUBLISHED_POP, PUBLISHED_POP_PRIOR = 2473275, 2168316


@pytest.fixture
def published(seeded, conn):
    """`seeded` plus the four ACS rows the Census publishes for CBSA 12420 at summary level 310.

    One `ingest_run` row, because `acs_measure.ingest_run_id` is `NOT NULL REFERENCES
    ingest_run(id)` (`migrations/019_census_measures.sql`) — the same shape
    `tests/census/test_geo_metric.py::_run` uses, for the same reason.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingest_run (dataset_key, vintage, started_at, status) "
            "VALUES ('acs5', '2019\u20132023', now(), 'succeeded') RETURNING id")
        run = cur.fetchone()[0]
        for vintage, variable, estimate, moe in (
            ("2019\u20132023", "B19013_001E", PUBLISHED_INCOME, PUBLISHED_INCOME_MOE),
            ("2019\u20132023", "B11001_001E", PUBLISHED_HOUSEHOLDS, PUBLISHED_HOUSEHOLDS_MOE),
            ("2019\u20132023", "B01003_001E", PUBLISHED_POP, 0),
            ("2014\u20132018", "B01003_001E", PUBLISHED_POP_PRIOR, 0),
        ):
            cur.execute(
                "INSERT INTO acs_measure (geo_id, summary_level, vintage, variable, estimate, moe, ingest_run_id) "
                "VALUES ('12420','310',%s,%s,%s,%s,%s)", (vintage, variable, estimate, moe, run))
    drop_summary_cache()
    return conn


async def test_the_published_metro_median_is_served_and_is_not_the_median_of_the_tracts(client, published, H) -> None:  # noqa: F811
    """The ruling itself. `median` (the tract distribution's own p50) stays exactly where it was —
    the bars are drawn from it — and `metro` carries the Census's own figure for the metro beside
    it, with the margin the Census publishes with it."""
    _r, body = await _body(client, H)
    income = _layer(body, "income")
    assert income["median"] == QUANTILES[2] == 50000.0, "the tract distribution must not move"
    assert income["metro"] == {
        "value": float(PUBLISHED_INCOME), "moe": float(PUBLISHED_INCOME_MOE),
        "kind": "published", "basis": market.METRO_BASIS["published"],
    }
    households = _layer(body, "households")
    assert households["metro"]["value"] == float(PUBLISHED_HOUSEHOLDS)
    assert households["metro"]["kind"] == "published"


async def test_a_metro_the_census_publishes_no_row_for_serves_no_metro_figure(client, seeded, H) -> None:  # noqa: F811
    """`seeded` writes no `acs_measure` row at all: absent beats faked, so every layer answers
    `metro: null` and the card falls back to its own "median of N Census tracts"."""
    _r, body = await _body(client, H)
    assert [row["metro"] for row in body["layers"]] == [None] * len(body["layers"])


async def test_the_two_derived_metro_figures_are_built_from_the_published_ones(client, published, H) -> None:  # noqa: F811
    """`pets` is the published metro households at the design's own documented rate and `growth`
    is the two published metro populations through `materialize.py`'s own formula (D12) — both
    `derived`, because the Census publishes neither, and both through `app.census.metrics` rather
    than a second spelling of the arithmetic."""
    from app.census import metrics as M

    _r, body = await _body(client, H)
    pets = _layer(body, "pets")
    assert pets["metro"] == {
        "value": float(M.pet_households_est(PUBLISHED_HOUSEHOLDS)), "moe": None,
        "kind": "derived", "basis": market.METRO_BASIS["derived"],
    }
    growth = _layer(body, "growth")
    assert growth["metro"]["value"] == M.population_growth_pct(PUBLISHED_POP, PUBLISHED_POP_PRIOR)
    assert (growth["metro"]["kind"], growth["metro"]["moe"]) == ("derived", None)


async def test_the_two_layers_the_census_publishes_no_metro_row_for_serve_none(client, published, H) -> None:  # noqa: F811
    """`econ` and `competition` are Business Patterns, which publishes nothing at summary level
    310 in this database — and a SUM over the metro's counties or ZIP areas is not available
    either, because this route's population is the metro's ENVELOPE and a sum over an envelope
    counts areas outside the metro. Both keep their own tract-distribution median and say so."""
    _r, body = await _body(client, H)
    assert _layer(body, "econ")["metro"] is None
    assert _layer(body, "competition")["metro"] is None
    assert _layer(body, "econ")["median"] == 818000.0, "the derived median stays where it was"


async def test_a_published_figure_with_no_published_margin_is_not_served(client, published, conn, H) -> None:  # noqa: F811
    """`materialize._suppression`'s own rule, applied to the metro row: a present estimate with no
    margin is UNMEASURED, not certain. One decision about a margin, made in one place, so the
    metro headline cannot claim a confidence the tract layer would refuse."""
    with conn.cursor() as cur:
        cur.execute("UPDATE acs_measure SET moe = NULL WHERE variable = 'B19013_001E'")
        cur.execute("UPDATE acs_measure SET moe = 900000 WHERE variable = 'B11001_001E'")
    drop_summary_cache()
    _r, body = await _body(client, H)
    assert _layer(body, "income")["metro"] is None, "no margin, no published metro figure"
    assert _layer(body, "households")["metro"] is None, "a margin this wide is high_moe"


async def test_a_layer_whose_licence_is_not_cleared_carries_no_metro_figure(client, published, conn, H) -> None:  # noqa: F811
    """The gate reaches the metro figure exactly as it reaches every other figure on the row: an
    uncleared dataset puts NOTHING of itself on the wire."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'unresolved' WHERE dataset_key = 'acs5'")
    gate.invalidate(sync_redis(), "acs5")
    drop_summary_cache()
    _r, body = await _body(client, H)
    for key in ("income", "households", "pets", "growth"):
        assert _layer(body, key)["state"] == "disabled", key
        assert _layer(body, key)["metro"] is None, key


async def test_growth_with_only_one_of_the_two_published_periods_serves_no_metro_figure(client, published, conn, H) -> None:  # noqa: F811
    """`population_growth_pct` is `None` when either period is missing, and a rate built from one
    period is not a rate at all."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM acs_measure WHERE vintage = '2014\u20132018'")
    drop_summary_cache()
    _r, body = await _body(client, H)
    assert _layer(body, "growth")["metro"] is None
    assert _layer(body, "income")["metro"] is not None, "income must not follow growth's own inputs"


def test_the_metro_basis_phrases_are_drawn_from_the_designs_own_closed_word_list() -> None:
    """A34/D-C51's rule, pinned rather than asserted in prose: the caption the design PRINTS is
    this string, so a basis word invented on the server would be a seventh geography phrase on the
    screen without a single design file changing. Both phrases name the metro and exactly one
    basis word from the audit's §3.1 list (`Census published`, `derived estimate`)."""
    assert set(market.METRO_BASIS) == {"published", "derived"}
    for kind, phrase in market.METRO_BASIS.items():
        assert phrase.endswith(" for the metro"), phrase
        assert phrase[: -len(" for the metro")] in ("Census published", "derived estimate"), phrase
        assert kind in phrase or kind == "published", phrase


async def test_a_row_the_census_published_no_estimate_for_is_skipped(client, published, conn, H) -> None:  # noqa: F811
    """`acs_measure.estimate` is NULLABLE and `app/census/acs.py`'s `_num` writes NULL for a value
    the Census published as a non-number, so an absent figure has to be SKIPPED rather than
    coerced: `float(None)` here would take the whole route down for one metro."""
    with conn.cursor() as cur:
        cur.execute("UPDATE acs_measure SET estimate = NULL WHERE variable = 'B01003_001E'")
    drop_summary_cache()
    r, body = await _body(client, H)
    assert r.status_code == 200
    assert _layer(body, "growth")["metro"] is None, "a rate was built from a figure the Census did not publish"
    assert _layer(body, "income")["metro"] is not None, "one absent variable emptied the others"
