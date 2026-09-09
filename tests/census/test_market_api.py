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


def test_short_market_name():
    from app.api.market import short_market_name

    assert short_market_name("Austin-Round Rock-San Marcos, TX Metro Area") == "Austin, TX"
    assert short_market_name("Sacramento-Roseville-Folsom, CA Metro Area") == "Sacramento, CA"


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
    r = await client.get("/api/markets", headers=H)
    assert r.json() == [{"cbsa_geoid": "12420", "name": "Austin, TX", "center": [30.31, -97.75], "zoom": 10}]


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
