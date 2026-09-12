"""Task B5: the member-gated market API -- layers, markets, communities and the per-listing panel
(spec 2026-09-05, plan Task B5; controller amendments A-C13 through A-C22).

Every route here sits behind `require("market.read")` (`app.auth.deps`); `settings.market_data_public`
widens that permission to `anonymous` rather than removing the dependency (Wave 2a Task I9a, A-C13
(3)). Corrections applied from pre-flight/review that the original brief got wrong:

* `app.db.engine` is a FUNCTION (`engine()`), not a ready-made object -- the brief's own illustrative
  code would fail on the very first request.
* A layer's state is THREE-valued (`enabled` | `disabled` | `blocked`), never a boolean: `cleared` ->
  `enabled`, `unresolved` -> `disabled`, `blocked` -> `blocked` (+ `blocked_reason`). "Off because a
  member turned a layer off" and "off because the licence is not cleared" are different fields on the
  admin surface, and B6's contract settled on `state`, not `enabled` (A-C14 (4)).
* The opportunity score is OMITTED from every payload -- not null, not hidden behind a flag, ABSENT --
  until the VIN Foundation signs off on its weights (A-C1 (9), A-C14 (5)). Tested by asserting the key
  is missing, never by asserting it is null.
* `tests/api/test_listings.py::test_the_listings_routes_are_guarded_not_public` walks every mounted
  route under the `/api/listings` prefix; the new `/api/listings/{id}/market` route is added there
  (guarded by `market.read`, not `listing.read`) rather than tripping that guard.
* The brief asserts `sync_redis().llen("celery") == 1"` for the backfill enqueue, which can never hold:
  `celery_app`'s own broker talks to the REAL `settings.redis_url` through kombu, never through
  `app.cache.sync_redis()` -- and the `member`/`H` fixtures below pull in the `redis` fixture
  (fakeredis), which patches exactly that second, unrelated client. `test_geocode.py` already solved
  this by monkeypatching `celery_app.send_task` and asserting on the calls captured -- the effect
  that matters, not a broker's raw queue length -- and this file follows the same pattern.
* A-C22's own carried Minor: no committed test failed if the INCOME half of `households or income
  suppressed -> score suppressed` were deleted. `tests/census/test_materialize.py` carries that case
  (it is `materialize_listing`'s own cascade, and the score never reaches this API's payload at all,
  so the API cannot be where it is proven).
"""
from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from app.api import market
from app.cache import sync_redis
from app.census import gate, materialize
from app.config import settings
from app.main import create_app
from app.tasks.celery_app import celery_app
from tests.api.conftest import ORIGIN, auth_headers
from tests.census.test_materialize import world  # noqa: F401 -- reuse the seeded listing fixture

# `H` was a module CONSTANT bearer token in the brief -- a legacy operator secret. Task I9a: the
# real member session is per-test state, so `H` is a fixture and every test that presents it takes
# it as a parameter, exactly as `tests/census/test_admin_api.py` does for the admin surface.


@pytest.fixture
async def client(scratch_dsn, monkeypatch):
    monkeypatch.setattr(settings, "database_url", scratch_dsn)
    r = sync_redis()
    for pat in ("listing:*", "backfill:*", "gate:*", "market:*"):
        for k in r.scan_iter(pat):
            r.delete(k)
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url=ORIGIN) as c:
        yield c


@pytest.fixture
def H(member):
    """The member session every read below presents. `member(("buyer",))` writes a real `active`
    account with the `buyer` grant and a live session into the scratch database; `auth_headers`
    turns its cookies into the literal `Cookie` header httpx 0.28 wants (Task I9a)."""
    _account_id, cookies, _csrf = member(("buyer",))
    return auth_headers(cookies)


@pytest.fixture
def materialized(conn, world):  # noqa: F811  (`world` the fixture, by name)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
            "('12420','310','2023','Austin-Round Rock-San Marcos, TX Metro Area', "
            "ST_Multi(ST_GeomFromText('POLYGON((-98 30,-97 30,-97 31,-98 31,-98 30))',4269)), "
            "ST_Point(-97.75,30.31,4269))"
        )
        cur.execute("UPDATE practice_location SET cbsa_geoid='12420' WHERE listing_id=%s", (world,))
    materialize.materialize_listing(conn, sync_redis(), world)
    return world


async def test_market_endpoints_require_a_member_unless_public(client, materialized, member, monkeypatch):
    paths = ("/api/layers", "/api/markets", "/api/markets/12420/communities", f"/api/listings/{materialized}/market")
    for path in paths:
        assert (await client.get(path)).status_code == 401, path
    _aid, cookies, _csrf = member(("buyer",))
    for path in paths:
        assert (await client.get(path, headers=auth_headers(cookies))).status_code == 200, path
    # MARKET_DATA_PUBLIC widens the permission rather than removing the dependency: the same
    # `require("market.read")` now passes for an anonymous caller (Task I9a) -- on every one of the
    # four routes, since they all carry the identical dependency object.
    monkeypatch.setattr(settings, "market_data_public", True)
    for path in paths:
        assert (await client.get(path)).status_code == 200, path


async def test_layers_come_from_the_registry_with_three_valued_state_and_caveats(client, materialized, conn, H):
    layers = {l["key"]: l for l in (await client.get("/api/layers", headers=H)).json()}
    assert set(layers) == {"income", "pets", "growth", "households", "econ", "competition", "practices", "drive_10", "drive_20"}
    assert layers["income"]["source_label"].startswith("Source: U.S. Census Bureau, American Community Survey")
    assert layers["income"]["state"] == "enabled"
    assert layers["competition"]["dataset_key"] == "zbp" and "proxy" in layers["competition"]["caveat"] and layers["competition"]["geo_level"] == "zcta"
    assert layers["pets"]["is_derived"] is True and "0.57" in layers["pets"]["caveat"]
    assert layers["growth"]["vintage"] == "2014\u20132018 \u2192 2019\u20132023" and layers["growth"]["geo_level"] == "place"
    assert "approximation" in layers["drive_10"]["caveat"]
    # Never a bare boolean anywhere in the payload -- three-valued or nothing.
    assert all("enabled" not in l for l in layers.values())
    # `practices`/`drive_10`/`drive_20` carry no dataset at all -- always enabled, never blocked.
    assert layers["practices"]["state"] == "enabled" and "blocked_reason" not in layers["practices"]

    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='zbp'")
    gate.invalidate(sync_redis(), "zbp")
    layers = {l["key"]: l for l in (await client.get("/api/layers", headers=H)).json()}
    # "unresolved" is not yet cleared but is not a permanent refusal either -- `disabled`, not `blocked`.
    assert layers["competition"]["state"] == "disabled" and "blocked_reason" not in layers["competition"]

    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='blocked', notes='Counsel declined the terms.' WHERE dataset_key='zbp'")
    gate.invalidate(sync_redis(), "zbp")
    layers = {l["key"]: l for l in (await client.get("/api/layers", headers=H)).json()}
    assert layers["competition"]["state"] == "blocked" and layers["competition"]["blocked_reason"] == "Counsel declined the terms."


async def test_markets_lists_cbsas_with_published_listings(client, materialized, H):
    # Task CK: the catalogue names each row with the LISTING's own `market` column, never a
    # heuristic over the CBSA's official name. `materialized` builds on `world`, whose listing is
    # `make_listing`'s DEFAULT city/state ("Cedar Park", "TX") -- so its real market key is
    # "Cedar Park, TX", not "Austin, TX" (the pre-fix route's `short_market_name` over the CBSA's
    # own name, "Austin-Round Rock-San Marcos, TX Metro Area"). The CBSA and its centre are
    # unchanged; only the label the pre-fix route invented is gone.
    r = await client.get("/api/markets", headers=H)
    assert r.json() == [{"cbsa_geoid": "12420", "name": "Cedar Park, TX", "center": [30.31, -97.75], "zoom": 10}]


async def test_markets_names_a_metro_by_the_listings_own_market_key_not_the_cbsa_name(client, materialized, conn, H):
    """QA evidence #1 (2026-09-12 03:38Z): New York's CBSA official name is "New York-Newark-
    Jersey City, NY-NJ", but the design's dropdown -- and the listing's own `market` column --
    reads "New York, NY". The pre-fix route's `short_market_name(ga.name)` heuristic produced the
    former, which never equals the latter, so `boundaries()`'s `rows.find((m) => m.name ===
    marketName)` always missed and no boundary request was ever made for New York."""
    from tests.census.listing_fixtures import make_listing

    lid = make_listing(conn, city="New York", state="NY")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
            "('35620','310','2023','New York-Newark-Jersey City, NY-NJ', "
            "ST_Multi(ST_GeomFromText('POLYGON((-75 40,-73 40,-73 41,-75 41,-75 40))',4269)), "
            "ST_Point(-74.02,40.72,4269))"
        )
        cur.execute(
            "INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoded_at, geocoder_vintage, cbsa_geoid) "
            "VALUES (%s, 'h', 'rooftop', now(), 'Current_Current', '35620')",
            (lid,),
        )
    rows = (await client.get("/api/markets", headers=H)).json()
    assert {"cbsa_geoid": "35620", "name": "New York, NY", "center": [40.72, -74.02], "zoom": 10} in rows
    assert not any("NY-NJ" in r["name"] for r in rows)


async def test_markets_serves_one_row_per_market_key_when_two_keys_share_a_cbsa(client, materialized, conn, H):
    """QA evidence #2: CBSA 42200 is "Santa Maria-Santa Barbara"; the design lists both cities as
    separate markets. Modelled here on the same shape with Sacramento/South Lake Tahoe (CBSA
    40900, per the brief) so the fixture geo_area row is realistic: two listing market keys, one
    CBSA, must serve as TWO rows -- one per key -- never collapsed into one by a `SELECT DISTINCT`
    over the CBSA's own name and centroid."""
    from tests.census.listing_fixtures import make_listing

    l1 = make_listing(conn, city="Sacramento", state="CA")
    l2 = make_listing(conn, city="South Lake Tahoe", state="CA")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
            "('40900','310','2023','Sacramento-Roseville-Folsom, CA Metro Area', "
            "ST_Multi(ST_GeomFromText('POLYGON((-122 38,-121 38,-121 39,-122 39,-122 38))',4269)), "
            "ST_Point(-121.49,38.58,4269))"
        )
        cur.executemany(
            "INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoded_at, geocoder_vintage, cbsa_geoid) "
            "VALUES (%s, 'h', 'rooftop', now(), 'Current_Current', '40900')",
            [(l1,), (l2,)],
        )
    rows = (await client.get("/api/markets", headers=H)).json()
    named = {r["name"]: r["cbsa_geoid"] for r in rows}
    assert named.get("Sacramento, CA") == "40900"
    assert named.get("South Lake Tahoe, CA") == "40900"
    pairs = [(r["name"], r["cbsa_geoid"]) for r in rows]
    assert len(pairs) == len(set(pairs))  # no duplicate (name, cbsa_geoid) pair


async def test_markets_orders_one_market_key_that_spans_two_cbsas_deterministically(client, materialized, conn, H):
    """The REVERSE of the case above, and the one that was undefined (fix round 2, Minor 1).

    Where a metro boundary runs through a market key's own listings, one `listing.market` value
    holds rows in two CBSAs. The client resolves a metro with `rows.find(m => m.name === marketName)`
    — the FIRST match — and `ORDER BY l.market` alone left Postgres free to return either row first,
    so the same catalogue could shade a different half of the country between two requests with
    nothing anywhere to notice. `pl.cbsa_geoid` is the tie-break: still arbitrary, now STABLE.
    """
    from tests.census.listing_fixtures import make_listing

    ids = [make_listing(conn, city="Kansas City", state="MO") for _ in range(2)]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom, centroid) VALUES "
            "(%s,'310','2023',%s, ST_Multi(ST_GeomFromText(%s,4269)), ST_Point(%s,%s,4269))",
            [
                ("28140", "Kansas City, MO-KS Metro Area", "POLYGON((-95 38,-94 38,-94 39,-95 39,-95 38))", -94.58, 39.10),
                ("41140", "St. Joseph, MO-KS Metro Area", "POLYGON((-95 39,-94 39,-94 40,-95 40,-95 39))", -94.85, 39.77),
            ],
        )
        cur.executemany(
            "INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoded_at, geocoder_vintage, cbsa_geoid) "
            "VALUES (%s, 'h', 'rooftop', now(), 'Current_Current', %s)",
            [(ids[0], "41140"), (ids[1], "28140")],
        )
    mine = [r["cbsa_geoid"] for r in (await client.get("/api/markets", headers=H)).json() if r["name"] == "Kansas City, MO"]
    assert mine == ["28140", "41140"], mine

    # …and the served order ALONE cannot prove this, which is the whole point of the defect: an
    # unordered query returns SOME order, and on this fixture Postgres happens to return the right
    # one — measured, by deleting the tie-break and watching this test still pass. A result that is
    # accidentally right is exactly what was shipping. So the guarantee is pinned where it lives,
    # in the query, the way `test_contract_doc` pins the refusal codes off the route's own source.
    import inspect
    import re

    sql = inspect.getsource(market.markets)
    # Anchored on the SQL literal's own closing quotes, so the prose above cannot be read as SQL.
    order_by = re.search(r'ORDER BY ([\w. ,]+)"""', sql)
    assert order_by is not None, "markets() has no ORDER BY at all; its row order is undefined"
    ordered = [c.strip() for c in order_by.group(1).split(",")]
    assert ordered == ["l.market", "pl.cbsa_geoid"], (
        f"markets() orders by {ordered}; one market key spanning two CBSAs then has no defined "
        "first row, and `rows.find(m => m.name === marketName)` on the client takes whichever "
        "Postgres felt like returning"
    )


async def test_markets_omits_a_published_listing_whose_point_is_in_no_cbsa(client, materialized, conn, H):
    """QA evidence #3's mirror: a published listing whose geocode never resolved a CBSA
    (`practice_location.cbsa_geoid IS NULL`) must never appear in the catalogue at all -- stated
    behaviour (docs/integrations/market-data-api.md), not a silent fallback to some default."""
    from tests.census.listing_fixtures import make_listing

    lid = make_listing(conn, city="Nowhere", state="MT")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoded_at, geocoder_vintage) "
            "VALUES (%s, 'h', 'rooftop', now(), 'Current_Current')",
            (lid,),
        )
    rows = (await client.get("/api/markets", headers=H)).json()
    assert not any(r["name"] == "Nowhere, MT" for r in rows)


async def test_communities_default_to_place_band_with_fixture_fields_and_competition(client, materialized, H):
    body = (await client.get("/api/markets/12420/communities", headers=H)).json()
    assert body["band"] == "place" and body["vintage"] == "2019\u20132023"
    c = body["communities"][0]
    assert c["name"] == "Cedar Park city" and c["pop"] == 81900 and c["hh"] == 27600 and c["income"] == 118400
    assert c["growth"] == pytest.approx(14.2, abs=0.01) and c["pets"] == 15732 and c["econ"] == pytest.approx(143850 * 1000 / 210)
    # `vets`/`competition.count` come from PostGIS's own ellipsoidal-geography area, which is not
    # exact integration: the two seeded ZCTAs each overlap the place at ~0.999808, not precisely
    # 1.0, even though the boundaries share the identical coordinate on that edge — a real database's
    # geometry engine, not a materialisation or serialisation bug (`tests/census/test_materialize.py`
    # documents the same figure at its source).
    assert c["vets"] == pytest.approx(7, rel=1e-3)
    assert c["competition"]["count"] == pytest.approx(7, rel=1e-3)
    assert c["competition"]["geo_level"] == "zcta" and c["competition"]["zctas"] == 2 and c["competition"]["level"] == "High"
    assert c["competition"]["per_10k_households"] == pytest.approx(c["vets"] / 2.76, rel=1e-6)
    assert c["location"] == "place_centroid" and (c["lat"], c["lng"]) == (30.55, -97.8)
    # opportunity_score is a listing-panel-only concern and never appears on a community row either.
    assert "opportunity_score" not in c and "score" not in c
    drive = (await client.get("/api/markets/12420/communities?band=drive_10", headers=H)).json()
    assert drive["band"] == "drive_10" and drive["communities"][0]["pop"] < 81900


async def test_communities_rejects_an_unknown_band(client, materialized, H):
    r = await client.get("/api/markets/12420/communities?band=nonsense", headers=H)
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_BAND"


async def test_disclosed_location_returns_the_point_for_members(client, materialized, conn, H):
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET location_disclosed = true WHERE id=%s", (materialized,))
    c = (await client.get("/api/markets/12420/communities", headers=H)).json()["communities"][0]
    assert c["location"] == "disclosed_point" and (c["lat"], c["lng"]) == (30.55, -97.85)


async def test_uncleared_layer_is_absent_within_60s(client, materialized, conn, H):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key IN ('zbp','cbp')")
    gate.invalidate(sync_redis(), "zbp")
    gate.invalidate(sync_redis(), "cbp")
    c = (await client.get("/api/markets/12420/communities", headers=H)).json()["communities"][0]
    assert "vets" not in c and "econ" not in c and "competition" not in c and "pop" in c


async def test_suppressed_community_field_is_listed_not_valued(client, materialized, conn, H):
    """A field can be suppressed at the DATA level (`market_metric.suppressed`) with its dataset
    still fully cleared -- a different path than the licence gate above. The field then has no
    numeric key of its own at all; its name appears in `suppressed` instead, exactly the shape the
    fixed-field design contract (pop/hh/income/growth/pets/econ/vets, all plain numbers) needs to
    stay honest about a hidden value rather than answer with a fabricated one."""
    with conn.cursor() as cur:
        cur.execute("UPDATE market_metric SET suppressed=true, suppress_reason='high_moe' WHERE listing_id=%s AND band='place' AND metric_key='households'", (materialized,))
    c = (await client.get("/api/markets/12420/communities", headers=H)).json()["communities"][0]
    assert "hh" not in c and "hh" in c["suppressed"] and c["pop"] == 81900


async def test_competition_count_serialises_without_a_per10k_partner(client, materialized, conn, H):
    """`establishments` and `vets_per_10k_households` are two separate rows, and the second can be
    suppressed (`input_suppressed`, cascading from a suppressed households figure) while the first
    is not -- `competition` must still carry its `count`/`geo_level`/`zctas`, just without
    `per_10k_households`/`level`, rather than disappearing or crashing on a missing partner row."""
    with conn.cursor() as cur:
        cur.execute("UPDATE market_metric SET suppressed=true, suppress_reason='input_suppressed' WHERE listing_id=%s AND band='place' AND metric_key='vets_per_10k_households'", (materialized,))
    c = (await client.get("/api/markets/12420/communities", headers=H)).json()["communities"][0]
    assert c["competition"]["count"] == pytest.approx(7, rel=1e-3)
    assert "per_10k_households" not in c["competition"] and "level" not in c["competition"]


async def test_a_null_establishments_count_is_absent_not_a_server_error(client, materialized, conn, H):
    """The C2 shape, one module over (whole-branch re-review, 2026-09-11). `market_metric.value_num`
    is nullable and `suppressed` is `NOT NULL DEFAULT false`, so "the source did not answer" is a
    NULL on an unsuppressed row -- which is what `materialize.py` writes when a formula has no
    inputs. `app/api/market.py` guarded that shape on the two lines either side of the
    `establishments` branch and not on the branch itself, so the one unguarded `float()` in the
    module would raise and the whole communities route would answer 500.

    D-C31 governs the answer: an absent figure is absent. The community keeps every figure that
    IS servable and simply carries no `competition` count, exactly as a suppressed row does."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE market_metric SET value_num=NULL WHERE listing_id=%s AND band='place' AND metric_key='establishments'",
            (materialized,),
        )
    r = await client.get("/api/markets/12420/communities", headers=H)
    assert r.status_code == 200, f"a null establishments count took the whole route down: {r.status_code}"
    c = r.json()["communities"][0]
    assert "count" not in c.get("competition", {})
    assert c["pop"] == 81900  # every other figure is untouched


async def test_uncleared_acs5_prior_hides_growth_from_communities_but_not_population(client, materialized, conn, H):
    """Growth's own gate is `acs5_prior cleared` (the layer-rendering contract table), even though
    the `market_metric` row materialize.py writes for it is stamped `source_dataset='acs5'` (its
    formula combines two ACS vintages, but the row can only carry one dataset key) -- so this cannot
    be proven by the generic per-`source_dataset` gate alone; the community serialiser must also
    consult `acs5_prior`'s own licence status for this one field."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5_prior'")
    gate.invalidate(sync_redis(), "acs5_prior")
    c = (await client.get("/api/markets/12420/communities", headers=H)).json()["communities"][0]
    assert "growth" not in c and c["pop"] == 81900


async def test_uncleared_acs5_hides_vets_per_10k_from_communities_but_keeps_the_establishment_count(client, materialized, conn, H):
    """A-C23 (1): a licence hole of the same shape as growth's. `vets_per_10k_households` always
    divides the establishment count by a household estimate (`M.vets_per_10k(est, hh_e)` in
    `app.census.materialize`), yet its own `market_metric.source_dataset` names whichever dataset
    produced the ESTABLISHMENT half (`zbp` here) -- never `acs5`, the dataset the household half
    actually came from. Withdrawing `acs5`'s licence must hide this figure exactly as unresolving
    `acs5_prior` already hides growth, even though `zbp` itself stays cleared throughout. The
    establishment COUNT on its own primary (ZBP) path folds in no household data at all, so it
    must stay visible -- proving the fix targets the ratio, not the whole competition object."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5'")
    gate.invalidate(sync_redis(), "acs5")
    c = (await client.get("/api/markets/12420/communities", headers=H)).json()["communities"][0]
    assert "competition" in c
    assert "per_10k_households" not in c["competition"] and "level" not in c["competition"]
    assert c["competition"]["count"] == pytest.approx(7, rel=1e-3)


async def test_uncleared_acs5_hides_vets_per_10k_from_the_panel_too(client, materialized, conn, H):
    """The panel serialiser carries the same extra gate the community one does: `acs5` withdrawn
    must drop `vets_per_10k_households` from `metrics` even though the row's own `source_dataset`
    (`zbp`) remains cleared, exactly as it drops `population_growth_pct` when `acs5_prior` alone is
    withdrawn."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5'")
    gate.invalidate(sync_redis(), "acs5")
    m = (await client.get(f"/api/listings/{materialized}/market?band=place", headers=H)).json()["metrics"]
    assert "vets_per_10k_households" not in m
    assert "establishments" in m and m["establishments"]["source_dataset"] == "zbp"


async def test_uncleared_acs5_hides_the_cbp_fallback_establishment_count(client, materialized, conn, H):
    """A-C23 (1)'s second figure: the establishment count's OWN fallback path -- county CBP
    apportioned by household share (`app.census.materialize._competition`'s
    `estab * (hh_e / county_hh)`) -- is stamped `source_dataset='cbp'`, which names the
    establishment half but not the household share folded into the multiplication. Force the
    fallback by unresolving `zbp` (the primary path), confirm the CBP-sourced count is still shown
    while `acs5` stays cleared, then confirm it disappears when `acs5` is ALSO withdrawn even
    though `cbp` itself never moves -- the same shape as growth's own explicit `acs5_prior` gate."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='zbp'")
    gate.invalidate(sync_redis(), "zbp")
    materialize.materialize_listing(conn, sync_redis(), materialized)
    c = (await client.get("/api/markets/12420/communities", headers=H)).json()["communities"][0]
    assert c["competition"]["count"] > 0  # the fallback is live: acs5 is still cleared

    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5'")
    gate.invalidate(sync_redis(), "acs5")
    c2 = (await client.get("/api/markets/12420/communities", headers=H)).json()["communities"][0]
    assert "vets" not in c2 and "competition" not in c2


async def test_listing_panel_is_cached_and_re_gated_on_read(client, materialized, conn, H):
    r = await client.get(f"/api/listings/{materialized}/market", headers=H)
    assert r.status_code == 200 and r.headers["x-cache"] == "miss"
    m = r.json()["metrics"]
    assert m["population"]["unit"] == "count" and m["establishments"]["source_dataset"] == "zbp"
    # A-C1 (9) / A-C14 (5): computed and stored, never published, until the VIN Foundation signs off.
    assert "opportunity_score" not in m
    assert m["revenue_per_establishment"]["label"] == "Avg. payroll per practice"
    r2 = await client.get(f"/api/listings/{materialized}/market", headers=H)
    # A-C23 (3): a cache hit must be proven to return the SAME payload, not merely the same header
    # -- the header alone cannot tell a correct cache from one serving stale or wrong bytes.
    assert r2.headers["x-cache"] == "hit" and r2.json() == r.json()
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='blocked' WHERE dataset_key='zbp'")
    gate.invalidate(sync_redis(), "zbp")
    m2 = (await client.get(f"/api/listings/{materialized}/market", headers=H)).json()["metrics"]
    assert "establishments" not in m2 and "population" in m2  # gate version changed the key; blocked layer gone


async def test_uncleared_acs5_prior_hides_growth_from_the_panel_too(client, materialized, conn, H):
    """The panel serialiser carries the same `acs5_prior` gate the community one does (correction
    6) -- population_growth_pct's own `market_metric.source_dataset` is stamped `acs5`, so only an
    explicit check against `acs5_prior` can hide it when THAT dataset is the one pulled."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='acs5_prior'")
    gate.invalidate(sync_redis(), "acs5_prior")
    m = (await client.get(f"/api/listings/{materialized}/market?band=place", headers=H)).json()["metrics"]
    assert "population_growth_pct" not in m and "population" in m


async def test_place_band_panel_on_request(client, materialized, H):
    body = (await client.get(f"/api/listings/{materialized}/market?band=place", headers=H)).json()
    assert body["band"] == "place" and body["metrics"]["population"]["value"] == 81900


async def test_panel_vintage_names_the_acs_vintage_regardless_of_row_order(client, materialized, conn, H):
    """A-C24 (1): the top-level `vintage` was read from `rows[0]["vintage"]` off an unordered
    query whose rows carry two vintage FAMILIES -- `acs5`'s "2019\u20132023" and the `zbp`/`cbp` family's
    "2022" -- so it named whichever row happened to come back first, correct today only because
    "2019\u20132023" happens to sort before "2022" (and `market_metric_lookup_idx (listing_id, band,
    vintage)` is the index Postgres reaches for on exactly this (listing_id, band) lookup, per
    Task B5's own EXPLAIN). Force a `zbp`/`cbp`-family row to carry a vintage that sorts BEFORE the
    ACS one and confirm the top-level field is unmoved: it must name the ACS vintage on purpose,
    never whichever row a scan happens to surface first."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE market_metric SET vintage = '0000' WHERE listing_id=%s AND band='place' "
            "AND metric_key IN ('establishments', 'revenue_per_establishment')",
            (materialized,),
        )
    sync_redis().incr(f"listing:{materialized}:market:version")
    body = (await client.get(f"/api/listings/{materialized}/market?band=place", headers=H)).json()
    assert body["vintage"] == "2019\u20132023"


async def test_panel_rejects_an_unknown_band(client, materialized, H):
    r = await client.get(f"/api/listings/{materialized}/market?band=nonsense", headers=H)
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_BAND"


async def test_suppressed_metric_hides_value_but_keeps_reason(client, materialized, conn, H):
    with conn.cursor() as cur:
        cur.execute("UPDATE market_metric SET suppressed=true, suppress_reason='high_moe' WHERE listing_id=%s AND metric_key='households'", (materialized,))
    sync_redis().incr(f"listing:{materialized}:market:version")
    hh = (await client.get(f"/api/listings/{materialized}/market", headers=H)).json()["metrics"]["households"]
    assert hh["value"] is None and hh["suppressed"] is True and hh["suppress_reason"] == "high_moe"


async def test_the_same_figure_can_be_hidden_at_one_band_and_approximate_at_another(client, materialized, conn, H):
    """A-C21 (5), carried into the market API: a catchment-band figure that is a household-weighted
    median of medians is ALWAYS shown with an `approximate` caveat and never suppressed for a missing
    combined margin (A-C22's ratified boundary -- a median of medians has no combined margin by
    construction); the SAME metric at the place band is a real single ACS estimate that CAN be
    suppressed outright when its own margin is too wide. The two facts must never be conflated: a
    suppressed entry is never marked approximate (there is no value to caveat), and an approximate
    entry is never marked suppressed (the value shown IS the approximation)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE market_metric SET suppressed=true, suppress_reason='high_moe' "
            "WHERE listing_id=%s AND band='place' AND metric_key='median_hh_income'",
            (materialized,),
        )
    sync_redis().incr(f"listing:{materialized}:market:version")
    place = (await client.get(f"/api/listings/{materialized}/market?band=place", headers=H)).json()["metrics"]["median_hh_income"]
    assert place["value"] is None and place["suppressed"] is True and place["suppress_reason"] == "high_moe"
    assert "approximate" not in place

    drive = (await client.get(f"/api/listings/{materialized}/market?band=drive_10", headers=H)).json()["metrics"]["median_hh_income"]
    assert drive["value"] is not None and drive["suppressed"] is False and drive.get("approximate") is True


async def test_a_malformed_listing_id_is_404_not_a_crash(client, H):
    """`listing.id` is a `uuid` column (`migrations/016_listing.sql`); a caller-supplied path
    segment that is not a UUID at all must read as "no such listing" here, exactly as
    `app.api.listings._parsed_uuid` already treats one -- asyncpg refuses to bind a non-UUID string
    to a `uuid` parameter at all (`DataError`), so without this guard the query itself raises before
    the 404 branch ever runs."""
    r = await client.get("/api/listings/not-a-uuid/market", headers=H)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


async def test_missing_metrics_404_and_enqueue_backfill_once_for_real_listings_only(client, conn, H, monkeypatch):
    from tests.census.listing_fixtures import make_listing

    sent: list[tuple[str, list[str] | None]] = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, args=None, **kw: sent.append((name, args)))

    lid = make_listing(conn)
    r1 = await client.get(f"/api/listings/{lid}/market", headers=H)
    r2 = await client.get(f"/api/listings/{lid}/market", headers=H)
    assert r1.status_code == r2.status_code == 404 and r1.json()["error"]["code"] == "NO_MARKET_DATA"
    # Deduped by `backfill:{id}` -- the effect asserted is "enqueued exactly once", not a raw broker
    # length (see the module docstring: the real broker and the fake Redis these fixtures install
    # are two different connections, so `sync_redis().llen("celery")` can never observe this).
    assert sent == [("census.backfill_listing", [lid])]

    r3 = await client.get("/api/listings/00000000-0000-0000-0000-000000000000/market", headers=H)
    assert r3.status_code == 404 and r3.json()["error"]["code"] == "NOT_FOUND"
    assert sent == [("census.backfill_listing", [lid])]  # unknown ids never enqueue (red-team C4)


async def test_an_unpublished_listing_with_market_data_still_404s_as_not_found(client, conn, H, monkeypatch):
    """A-C23 (2): the published-listing check was compounded with the cache-dedupe check
    (`exists[0] == "published" and r.set(...)`) into a SINGLE condition that only ever gated
    whether to enqueue a backfill -- it never gated whether to SERVE a panel that already had
    rows. A listing that is no longer published (withdrawn after being materialised, most
    plausibly) but still carries `market_metric` rows from before would have had its panel served
    in full under the old code, because `if not rows:` is false and the publication status is
    never consulted again. Deleting the published half of the old compound condition would have
    passed every test committed before this one -- none seeded rows for an unpublished listing.
    The fix gates the WHOLE response on publication, the same posture `communities()`'s own SQL
    already takes (`JOIN listing l ON ... AND l.status = 'published'`), and separates the
    cache-dedupe check into its own, no-longer-compounded `if`."""
    from tests.census.listing_fixtures import make_listing

    sent: list[tuple[str, list[str] | None]] = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, args=None, **kw: sent.append((name, args)))

    lid = make_listing(conn, status="draft")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO practice_location (listing_id, address_hash, geo_precision, geocoded_at, geocoder_vintage) "
            "VALUES (%s, 'h', 'rooftop', now(), 'Current_Current')",
            (lid,),
        )
        cur.execute(
            "INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at) "
            "VALUES (%s, 'drive_10', 'population', '2019\u20132023', 44800, 'count', 'acs5', now())",
            (lid,),
        )
    r = await client.get(f"/api/listings/{lid}/market", headers=H)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert sent == []
