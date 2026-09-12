"""Policy §3's "hot queries use indexes" gate — `EXPLAIN (FORMAT JSON)` on the queries a slow plan
would be felt through, asserted against the index each one is supposed to use.

The harness is the one `docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md` §5
prints, including its `or name == "active_engine"` Seq-Scan exemption: the registry is ~20 rows, a
sequential scan there is correct, and the policy already says so. Carried forward unused (I9a fix
round 1, Important 3) precisely so Map engines M1's `active_engine` entry lands by adding a row to
`PLANS` and nothing else. What §5 does NOT have is `INDEXES` — a plan-shape assertion alone passes
for the wrong reason, because Postgres will index-scan a two-row table as happily as it will
sequential-scan it, so each entry also names the index the migration created and the assertion
fails if the planner stops choosing it.

The file is created in Wave 2a Task I9a rather than in Census B5 / Map engines M1 as §4's table
expects (that row is corrected): those two tasks own the `market_metric`, `practice_location` and
`dataset_registry` entries, and none of those tables exists yet.

**Row counts are part of the gate.** `users_queue` seeds 2,000 accounts before it explains anything.
An empty table makes every plan a sequential scan and every index assertion a coin toss — which is
the defect this file's first version had: it asserted an index on a table with no rows, where the
planner's choice says nothing about production. `SEEDS` is where an entry declares the shape of
database its plan is a claim about.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.api.admin_signups import COUNTS_SQL as SIGNUPS_COUNTS_SQL
from app.api.admin_signups import LIST_SQL as SIGNUPS_LIST_SQL
from app.api.admin_signups import MAX_LAUNCH_BATCH, UNMAILED_SQL
from app.api.admin_signups import MAX_LIST as SIGNUPS_MAX_LIST
from app.api.admin_users import LIST_SQL, MAX_LIST
from app.census.catchment import BANDS as CATCHMENT_BANDS
from app.census.catchment import METHOD as CATCHMENT_METHOD
from app.census.catchment import SQL as CATCHMENT_SQL
from app.census.serve import _PRECISION_SQL, _SCOPE_NAME_SQL

# Task I9a fix round 1, Important 2. `users_queue` is `GET /api/admin/users?state=pending` — the
# endpoint's OWN query, imported from the handler rather than retyped, so this gate cannot drift
# from the thing it is a gate on. Its parameters are what `list_users` builds for a first page
# filtered by state: no kind, no role, no cursor, `limit` capped and +1 for the has-more probe.
#
# `session_lookup` is `app.auth.sessions.resolve`'s Postgres half, taken on every request whose
# principal cache has expired. `session.id_hash` is the primary key (`migrations/010_accounts.sql`).
#
# (`migrations/011_applications_roles.sql`'s `application_queue_idx (status, submitted_at)` is NOT
# pinned here: no query in `app/` filters `application.status` — the queue is read through the
# `account`-driven join above — so there is nothing to explain. The first task that reads the
# application table by status should add its query here and pin that index then.)

# The one listing `_seed_catchment_geo` gives a real, matched geo_area row — shared between the
# seed and the plan's own params so the two cannot drift apart.
_CATCHMENT_LISTING_ID = "00000000-0000-0000-0000-0000000c3a90"

# Census Task B5's own target listing — shared between `_seed_panel_metrics` and the "panel" plan's
# own params, same reason as `_CATCHMENT_LISTING_ID` above.
_PANEL_LISTING_ID = "00000000-0000-0000-0000-0000000ac1e1"

# Census Task B7's target listings — shared between `_seed_community_rows` and the "community_rows"
# plan, same reason as above. The query fetches multiple listings in one batch.
_COMMUNITY_ROWS_LISTING_IDS = [
    "00000000-0000-0000-0000-0000000cb7a0",
    "00000000-0000-0000-0000-0000000cb7a1",
    "00000000-0000-0000-0000-0000000cb7a2",
]

# D-C38's second batched query (`app.census.serve._scope_names`) — the Growth tile's geography
# name. Its own three listings, shared with `_seed_scope_names` for the reason above.
_SCOPE_NAMES_LISTING_IDS = [
    "00000000-0000-0000-0000-0000000c38a0",
    "00000000-0000-0000-0000-0000000c38a1",
    "00000000-0000-0000-0000-0000000c38a2",
]

# The active `tiger_cb` edition the seed writes and the plan asks for — one constant, so the
# JOIN's third equality cannot silently stop matching.
_SCOPE_NAMES_VINTAGE = "2023"

PLANS: dict[str, tuple[str, tuple[Any, ...] | dict[str, Any]]] = {
    "users_queue": (
        "EXPLAIN (FORMAT JSON) " + LIST_SQL,
        {"state": "pending", "kind": None, "role": None, "cursor_at": None, "cursor_id": None, "limit": MAX_LIST + 1},
    ),
    "session_lookup": (
        "EXPLAIN (FORMAT JSON) SELECT account_id FROM session WHERE id_hash=%s",
        ("x",),
    ),
    "signups_list": (
        "EXPLAIN (FORMAT JSON) " + SIGNUPS_LIST_SQL,
        {"source": None, "consent_version": None, "cursor_at": None, "cursor_id": None, "limit": SIGNUPS_MAX_LIST + 1},
    ),
    # L5 (I5d.3 review): the OTHER query `GET /api/admin/signups` runs on every call — the grouped
    # count that answers the tab's counts, the current filter and (D-I5d-6) which filter values
    # exist. No `INDEXES` claim below: it is a full, ungated `GROUP BY` over the whole table, so it
    # is CORRECTLY a `HashAggregate` over a `Seq Scan` no matter what indexes exist — there is no
    # covering index on `(source, consent_version, launch_mailed_at)` to choose, and adding one
    # would be a real schema change, not what this entry is for. It is here so the query's SHAPE
    # (row estimate, node types) is pinned and visible, the same reason `active_engine` is
    # exempted from the Seq-Scan assertion below: a small/full-table scan can be the CORRECT plan.
    "signups_counts": (
        "EXPLAIN (FORMAT JSON) " + SIGNUPS_COUNTS_SQL,
        (),
    ),
    # L3 (final review): the launch mail's own scan (`app.api.admin_signups.launch_mail`), which
    # `test_migrate.py` proves the index exists for but never proves is USED — a later change to
    # the `ORDER BY` or a dropped `FOR UPDATE` could silently fall back to a full scan under a
    # row lock on a launch-day batch of thousands. `FOR UPDATE` is stripped: EXPLAIN cannot plan it
    # in every form, and the row-lock clause has no bearing on which scan the planner picks anyway.
    "signups_unmailed": (
        "EXPLAIN (FORMAT JSON) " + UNMAILED_SQL.replace(" FOR UPDATE", ""),
        (MAX_LAUNCH_BATCH,),
    ),
    # Task B3 correction 5: `app.census.catchment.SQL` joins `geo_area` on
    # `ST_Intersects(g.geom, ...)` with `g.geom` left BARE so `geo_area_geom_gix` (a GiST index on
    # that column) stays usable — the brief's own form wrapped `g.geom` in `ST_Transform(...)::
    # geography`, which made the index unusable and the query degrade to a full scan as the table
    # grows. `_CATCHMENT_LISTING_ID` is a fixed id seeded by `_seed_catchment_geo` below, matched
    # to the one `geo_area` row that actually contains the seeded point — real params, not stand-
    # ins, since a spatial predicate's selectivity is exactly what decides whether the planner
    # reaches for the index at all.
    "catchment_tracts": (
        "EXPLAIN (FORMAT JSON) " + CATCHMENT_SQL,
        {"band": "drive_10", "level": "140", "vintage": "2023", "method": CATCHMENT_METHOD,
         "radius": CATCHMENT_BANDS["drive_10"], "listing_id": _CATCHMENT_LISTING_ID},
    ),
    # Census Task B5: `GET /api/listings/{id}/market`'s own query on a cache miss
    # (`app.api.market._PANEL_SQL`, run inside `listing_market`). Hand-matched here — same columns,
    # same join, same WHERE — rather than imported: the production string is composed for
    # SQLAlchemy's `text()` (`:id`/`:band` bind markers, translated to asyncpg's own paramstyle at
    # execution) and cannot be handed to a raw psycopg2 cursor as-is, exactly the reason
    # `session_lookup` above is inlined rather than imported from `app.auth.sessions`. The brief's
    # own parenthetical guessed "market_metric PK lookup" — measured against 3,000 seeded listings
    # below, the planner reaches for `market_metric_lookup_idx` (listing_id, band, vintage)
    # instead: three columns beat the four-column primary key on the SAME (listing_id, band)
    # prefix this query actually filters on, so Postgres picks the narrower, cheaper index.
    "panel": (
        "EXPLAIN (FORMAT JSON) SELECT mm.*, pl.geo_precision FROM market_metric mm "
        + "JOIN practice_location pl ON pl.listing_id = mm.listing_id "
        + "WHERE mm.listing_id = %(listing_id)s AND mm.band = %(band)s",
        {"listing_id": _PANEL_LISTING_ID, "band": "drive_10"},
    ),
    # Census Task B7: `GET /api/listings`'s batch fetch for community context data
    # (`app.census.serve.community_rows`). This is the query that fetches market_metric rows for
    # a page of listings in one batch, filtering by listing_id array and band. The query should use
    # `market_metric_lookup_idx (listing_id, band, vintage)` for efficient lookup.
    "community_rows": (
        "EXPLAIN (FORMAT JSON) SELECT listing_id, metric_key, value_num, suppressed, source_dataset, vintage, is_derived, inputs "
        + "FROM market_metric WHERE listing_id = ANY(%s::uuid[]) AND band = %s",
        (_COMMUNITY_ROWS_LISTING_IDS, "place"),
    ),
    # D-C38 (fix round 1, finding 8): `community_rows` runs a SECOND batched query per page —
    # `_scope_names`, which resolves each listing's place and county NAME for the Growth tile's
    # sub-line. It had no entry here, so the one query this branch ADDED to the listings page was
    # the one query with no plan gate.
    #
    # IMPORTED, not hand-matched: `_SCOPE_NAME_SQL` is built for a raw psycopg2 cursor (`%s`
    # placeholders), so unlike `panel` — whose production string carries SQLAlchemy `:id` bind
    # markers and cannot be handed to this cursor — this gate can read the module's own string
    # and cannot drift from it. Its four parameters are exactly what `_scope_names` passes:
    # vintage, ids, vintage, ids, one pair per UNION branch.
    "scope_names": (
        "EXPLAIN (FORMAT JSON) " + _SCOPE_NAME_SQL,
        (_SCOPE_NAMES_VINTAGE, _SCOPE_NAMES_LISTING_IDS, _SCOPE_NAMES_VINTAGE, _SCOPE_NAMES_LISTING_IDS),
    ),
    # GEO-WIRE fix round 2, minor 3. `community_rows` runs a THIRD batched query per page since
    # the controller's non-rooftop ruling — `_precisions`, which reads each listing's
    # `geo_precision` to decide whether its area figures come from the ring or from its city. It
    # is on the listings page's own path, once per page, and it had no plan gate; `scope_names`
    # was added for exactly this omission one round earlier.
    #
    # IMPORTED like `scope_names`, for the same reason: `_PRECISION_SQL` is written for a raw
    # psycopg2 cursor, so this gate reads the module's own string and cannot drift from it. One
    # parameter, the page's listing ids, which is what `_precisions` passes.
    "precisions": (
        "EXPLAIN (FORMAT JSON) " + _PRECISION_SQL,
        (_SCOPE_NAMES_LISTING_IDS,),
    ),
}

# The index each plan must be using, by name. Absent for an entry whose only claim is its shape.
INDEXES: dict[str, tuple[str, ...]] = {
    # Both from `migrations/015_admin_list_indexes.sql`, which exists because this query had nothing
    # behind either half of it: `account_listing_idx (created_at DESC, id DESC)` serves the ORDER BY
    # that the cursor also pages on, and `application_account_idx (account_id, submitted_at DESC)`
    # serves the LEFT JOIN LATERAL that would otherwise cost one sequential scan of `application`
    # per account row.
    "users_queue": ("account_listing_idx", "application_account_idx"),
    "session_lookup": ("session_pkey",),
    "signups_list": ("interest_signup_listing_idx",),
    "signups_unmailed": ("interest_signup_unmailed_idx",),
    # migrations/018_census_geo.sql's GiST index on geo_area.geom — the one correction 5 exists to
    # keep usable.
    "catchment_tracts": ("geo_area_geom_gix",),
    # migrations/061_census_listing_tables.sql: `market_metric_lookup_idx (listing_id, band,
    # vintage)` for the metric rows, `practice_location_pkey` (its PRIMARY KEY IS `listing_id`) for
    # the join — measured, not the brief's guessed `market_metric_pkey` (see the PLANS entry above).
    "panel": ("market_metric_lookup_idx", "practice_location_pkey"),
    # Task B7: `market_metric_lookup_idx (listing_id, band, vintage)` serves the batch query that
    # filters on listing_id (via ANY clause) and band.
    "community_rows": ("market_metric_lookup_idx",),
    # D-C38: MEASURED, not assumed (the same discipline the `panel` entry above records). The
    # plan is `Append` over two `Nested Loop`s, each one a bitmap scan of
    # `practice_location_pkey` (its PRIMARY KEY IS `listing_id`, which the `ANY(...)` array
    # filters on) driving an `Index Scan` on `geo_area_pkey` — the primary key
    # (geo_id, summary_level, vintage) that `_scope_names`'s two-branch UNION exists to let each
    # branch descend. One join with an `OR` across `place_geoid`/`county_geoid` could not.
    "scope_names": ("practice_location_pkey", "geo_area_pkey"),
    # `practice_location`'s PRIMARY KEY IS `listing_id` (`migrations/061`), which is the only
    # column this query touches on either side of the `= ANY(...)`, so there is exactly one index
    # it can be right to use and this names it.
    "precisions": ("practice_location_pkey",),
}


def _seed_admin_queue(conn: Any) -> None:
    """2,000 accounts across the four states an operator sees, one application each, and a grant on
    the active ones — enough that the planner's choice is the one it would make on a real database.

    The `created_at` values are spread a minute apart so `account_listing_idx` has an ordering to
    serve; `ANALYZE` is what makes the numbers visible to the planner at all (without it Postgres
    plans against a default 10-page estimate and sorts)."""
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO account (email, password_hash, state, created_at)
                       SELECT 'plan-'||i||'@example.org', 'x', (ARRAY['pending','active','verified','declined'])[1 + (i % 4)],
                              now() - (i || ' minutes')::interval
                         FROM generate_series(1, 2000) i""")   # single `%` — psycopg2 interpolates only when params are passed
        cur.execute("""INSERT INTO application (account_id, kind, fields, status, submitted_at)
                       SELECT id, 'buyer', '{}'::jsonb, 'pending', created_at FROM account""")
        cur.execute("INSERT INTO role_grant (account_id, role, granted_by) SELECT id, 'buyer', id FROM account WHERE state='active'")
        cur.execute("ANALYZE account")
        cur.execute("ANALYZE application")
        cur.execute("ANALYZE role_grant")


def _seed_signups(conn: Any) -> None:
    """2,000 sign-ups a minute apart, then ANALYZE — without rows and statistics the planner sorts
    a 10-page estimate and the index assertion is a coin toss."""
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO interest_signup (email, email_normalised, consent_version, source, created_at)
                       SELECT 'plan-'||i||'@x.test', 'plan-'||i||'@x.test', 'coming-soon-v1', 'coming-soon',
                              now() - (i || ' minutes')::interval
                         FROM generate_series(1, 2000) i""")
        cur.execute("ANALYZE interest_signup")


def _seed_catchment_geo(conn: Any) -> None:
    """2,000 `listing`/`practice_location` rows plus the one seeded target, and 5,000 `geo_area`
    tracts scattered far from the target's point plus the one tract that actually contains it.

    Without the 2,000-row `practice_location` volume, `listing_id = %(listing_id)s` — an equality
    lookup on that table's OWN primary key — planned as a `Seq Scan` on the single seeded row: a
    correct choice for one row, but not what a real, thousands-of-listings `practice_location`
    plans against (same "row counts are part of the gate" reasoning `_seed_admin_queue` documents,
    applied to the OTHER side of this join).

    The 5,000 `geo_area` rows share the query's own `summary_level`/`vintage` with the one tract
    that actually contains the target point — those two equality filters therefore match nearly
    the WHOLE table (not selective on their own) while the spatial predicate matches almost
    nothing, which is what should push the planner onto `geo_area_geom_gix` rather than a
    sequential scan or the unrelated `(summary_level, vintage)` btree index. `ANALYZE` is what
    makes PostGIS's own geometry statistics visible to the planner at all — without it Postgres
    has no histogram to estimate the spatial predicate's selectivity from."""
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source, sqft, est, price)
                       SELECT md5(random()::text || i::text)::uuid, 'plan-catchment-'||i, 'Plan Catchment '||i, '1 Main St',
                              'Cedar Park', 'TX', '78613', 'published', 'Cedar Park', 'Small animal', 'Cedar Park, TX', 'seed', 3000, 2005, 1200000
                         FROM generate_series(1, 2000) i""")
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, point, geo_precision, geocoded_at, geocoder_vintage)
                       SELECT id, 'h-'||id, ST_SetSRID(ST_Point(-110 + (random() * 10), 25 + (random() * 10)), 4269),
                              'rooftop', now(), 'Current_Current'
                         FROM listing WHERE slug LIKE 'plan-catchment-%'""")
        cur.execute("""INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source, sqft, est, price)
                       VALUES (%s, 'plan-catchment-target', 'Plan Catchment Target', '1 Main St', 'Cedar Park', 'TX', '78613',
                               'published', 'Cedar Park', 'Small animal', 'Cedar Park, TX', 'seed', 3000, 2005, 1200000)""", (_CATCHMENT_LISTING_ID,))
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, point, geo_precision, geocoded_at, geocoder_vintage)
                       VALUES (%s, 'h-plan-catchment-target', ST_SetSRID(ST_Point(-97.85, 30.55), 4269), 'rooftop', now(), 'Current_Current')""",
                    (_CATCHMENT_LISTING_ID,))
        cur.execute("""INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom)
                       SELECT 'plan-tract-'||i, '140', '2023', 'plan-tract-'||i,
                              ST_Multi(ST_MakeEnvelope(-130 + (i % 500) * 0.1, 20 + (i / 500) * 0.05,
                                                        -130 + (i % 500) * 0.1 + 0.05, 20 + (i / 500) * 0.05 + 0.05, 4269))
                         FROM generate_series(1, 5000) i""")
        cur.execute("""INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom)
                       VALUES ('plan-tract-target', '140', '2023', 'plan-tract-target',
                               ST_Multi(ST_GeomFromText('POLYGON((-97.90 30.50,-97.80 30.50,-97.80 30.60,-97.90 30.60,-97.90 30.50))', 4269)))""")
        cur.execute("ANALYZE listing")
        cur.execute("ANALYZE practice_location")
        cur.execute("ANALYZE geo_area")


def _seed_panel_metrics(conn: Any) -> None:
    """3,000 listings, each geocoded and carrying `market_metric` rows across all three bands and
    five metric keys (the same shape `tests/census/test_materialize.py`'s `world` fixture writes),
    plus the one target row `PLANS["panel"]` explains against — without the volume, `market_metric`
    and `practice_location` plan against a handful of rows each, which says nothing about what the
    planner does on a real, thousands-of-listings table (same "row counts are part of the gate"
    reasoning `_seed_catchment_geo`/`_seed_admin_queue` document above). The target listing's own
    slug matches the same `LIKE` pattern as the noise rows, so one bulk INSERT gives it the same
    fifteen metric rows every other seeded listing gets — no separate statement needed."""
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source, sqft, est, price)
                       SELECT md5(random()::text || i::text)::uuid, 'plan-panel-'||i, 'Plan Panel '||i, '1 Main St',
                              'Cedar Park', 'TX', '78613', 'published', 'Cedar Park', 'Small animal', 'Cedar Park, TX', 'seed', 3000, 2005, 1200000
                         FROM generate_series(1, 3000) i""")
        cur.execute("""INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source, sqft, est, price)
                       VALUES (%s, 'plan-panel-target', 'Plan Panel Target', '1 Main St', 'Cedar Park', 'TX', '78613',
                               'published', 'Cedar Park', 'Small animal', 'Cedar Park, TX', 'seed', 3000, 2005, 1200000)""", (_PANEL_LISTING_ID,))
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, point, geo_precision, geocoded_at, geocoder_vintage)
                       SELECT id, 'h-'||id, ST_SetSRID(ST_Point(-97.8 + (random() * 0.2), 30.4 + (random() * 0.2)), 4269),
                              'rooftop', now(), 'Current_Current'
                         FROM listing WHERE slug LIKE 'plan-panel-%'""")
        cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived,
                                                   formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at)
                       SELECT l.id, b.band, m.metric_key, '2019\u20132023', 100, 'count', false, NULL, 5, false, NULL, 'acs5', now()
                         FROM listing l, (VALUES ('place'),('drive_10'),('drive_20')) AS b(band),
                              (VALUES ('population'),('households'),('median_hh_income'),('pet_households_est'),('income_index_vs_us')) AS m(metric_key)
                        WHERE l.slug LIKE 'plan-panel-%'""")
        cur.execute("ANALYZE listing")
        cur.execute("ANALYZE practice_location")
        cur.execute("ANALYZE market_metric")


def _seed_community_rows(conn: Any) -> None:
    """3,000+ listings with market_metric rows for the batch query test. The seed function creates
    enough data for the planner to prefer index scans. The `_COMMUNITY_ROWS_LISTING_IDS` constants
    define specific listing ids that are guaranteed to have data."""
    with conn.cursor() as cur:
        # Seed background listings for planner context
        cur.execute("""INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source, sqft, est, price)
                       SELECT md5(random()::text || i::text)::uuid, 'plan-community-bg-'||i, 'Plan Community BG '||i, '1 Main St',
                              'Cedar Park', 'TX', '78613', 'published', 'Cedar Park', 'Small animal', 'Cedar Park, TX', 'seed', 3000, 2005, 1200000
                         FROM generate_series(1, 3000) i""")
        # Insert the three target listings, using full UUID in slug to ensure uniqueness
        for i, listing_id in enumerate(_COMMUNITY_ROWS_LISTING_IDS):
            cur.execute("""INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source, sqft, est, price)
                           VALUES (%s, %s, %s, '1 Main St', 'Cedar Park', 'TX', '78613',
                                   'published', 'Cedar Park', 'Small animal', 'Cedar Park, TX', 'seed', 3000, 2005, 1200000)
                           ON CONFLICT (slug) DO NOTHING""",
                        (listing_id, f"plan-community-target-{listing_id}", f"Plan Community Target {i+1}"))
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, point, geo_precision, geocoded_at, geocoder_vintage)
                       SELECT id, 'h-'||id, ST_SetSRID(ST_Point(-97.8 + (random() * 0.2), 30.4 + (random() * 0.2)), 4269),
                              'rooftop', now(), 'Current_Current'
                         FROM listing WHERE slug LIKE 'plan-community-%'""")
        # Seed market_metric rows for place band across all listings
        cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived,
                                                   formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at)
                       SELECT l.id, 'place', m.metric_key, '2019-2023', 100, 'count', false, NULL, 5, false, NULL, 'acs5', now()
                         FROM listing l,
                              (VALUES ('population'),('households'),('median_hh_income'),('population_growth_pct'),('establishments')) AS m(metric_key)
                        WHERE l.slug LIKE 'plan-community-%'""")
        # Seed some drive_10 band rows to add noise and make index selection more likely
        cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, is_derived,
                                                   formula_version, moe, suppressed, suppress_reason, source_dataset, computed_at)
                       SELECT l.id, 'drive_10', 'population', '2019-2023', 100, 'count', false, NULL, 5, false, NULL, 'acs5', now()
                         FROM listing l WHERE l.slug LIKE 'plan-community-%'""")
        cur.execute("ANALYZE listing")
        cur.execute("ANALYZE practice_location")
        cur.execute("ANALYZE market_metric")


def _seed_scope_names(conn: Any) -> None:
    """3,000 geocoded listings, each with a place and a county geoid, and the `geo_area` rows that
    name them: 3,000 places at summary level 160 and 300 counties at 050, on one `tiger_cb`
    vintage — plus a second vintage's worth of the same geoids, so that the vintage equality in
    the join is SELECTIVE rather than free. Without the volume this plans against a handful of
    rows and says nothing about a real page ("row counts are part of the gate", the reasoning
    `_seed_admin_queue` documents).

    Both UNION branches read `geo_area` by its own primary key (geo_id, summary_level, vintage)
    and `practice_location` by its (listing_id), which is what `_scope_names`'s docstring claims
    the two-branch shape buys over one join with an OR across two different columns."""
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source, sqft, est, price)
                       SELECT md5(random()::text || i::text)::uuid, 'plan-scope-'||i, 'Plan Scope '||i, '1 Main St',
                              'Dallas', 'TX', '75201', 'published', 'Dallas', 'Small animal', 'Dallas, TX', 'seed', 3000, 2005, 1200000
                         FROM generate_series(1, 3000) i""")
        for i, listing_id in enumerate(_SCOPE_NAMES_LISTING_IDS):
            cur.execute("""INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source, sqft, est, price)
                           VALUES (%s, %s, %s, '1 Main St', 'Dallas', 'TX', '75201',
                                   'published', 'Dallas', 'Small animal', 'Dallas, TX', 'seed', 3000, 2005, 1200000)""",
                        (listing_id, f"plan-scope-target-{listing_id}", f"Plan Scope Target {i + 1}"))
        # `row_number()` gives each listing its OWN place geoid and one of 300 counties, so the
        # join is a real many-to-one lookup rather than 3,000 rows all hitting one index entry.
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, place_geoid, county_geoid, geo_precision, geocoded_at, geocoder_vintage)
                       SELECT id, 'h-'||id, '48' || lpad(n::text, 5, '0'), '48' || lpad((n % 300)::text, 3, '0'),
                              'rooftop', now(), 'Current_Current'
                         FROM (SELECT id, row_number() OVER (ORDER BY slug) AS n FROM listing WHERE slug LIKE 'plan-scope-%') s""")   # single `%`: psycopg2 interpolates only when params are passed
        for vintage in (_SCOPE_NAMES_VINTAGE, "2022"):
            cur.execute("""INSERT INTO geo_area (geo_id, summary_level, vintage, name)
                           SELECT '48' || lpad(i::text, 5, '0'), '160', %s, 'Plan Place '||i FROM generate_series(1, 3003) i""",
                        (vintage,))
            cur.execute("""INSERT INTO geo_area (geo_id, summary_level, vintage, name)
                           SELECT '48' || lpad(i::text, 3, '0'), '050', %s, 'Plan County '||i FROM generate_series(0, 299) i""",
                        (vintage,))
        cur.execute("ANALYZE listing")
        cur.execute("ANALYZE practice_location")
        cur.execute("ANALYZE geo_area")


SEEDS: dict[str, Any] = {"users_queue": _seed_admin_queue, "signups_list": _seed_signups, "signups_counts": _seed_signups,
                        "signups_unmailed": _seed_signups, "catchment_tracts": _seed_catchment_geo, "panel": _seed_panel_metrics,
                        "community_rows": _seed_community_rows, "scope_names": _seed_scope_names,
                        # 3,000 `practice_location` rows, which `_seed_scope_names` already writes
                        # for its own plan and which are exactly what this one needs — "row counts
                        # are part of the gate", and a handful of rows would make the planner's
                        # choice a coin toss.
                        "precisions": _seed_scope_names}


def _node_types(plan: dict[str, Any]) -> list[str]:
    out = [plan.get("Node Type")]
    for child in plan.get("Plans", []):
        out += _node_types(child)
    return out


def _index_names(plan: dict[str, Any]) -> list[str]:
    out = [plan["Index Name"]] if "Index Name" in plan else []
    for child in plan.get("Plans", []):
        out += _index_names(child)
    return out


@pytest.mark.parametrize("name", sorted(PLANS))
def test_hot_query_uses_an_index(conn, name):
    seed = SEEDS.get(name)
    if seed is not None:
        seed(conn)
    sql, params = PLANS[name]
    with conn.cursor() as cur:
        cur.execute(sql, params)
        plan = cur.fetchone()[0][0]["Plan"]
    types = _node_types(plan)
    indexes = _index_names(plan)
    # The named-index assertion runs FIRST so a dropped or unchosen index is diagnosed by name
    # rather than reported as the generic "there is a Seq Scan in here somewhere" the two policy §5
    # assertions below would give (both fire too, for the same cause).
    missing = [i for i in INDEXES.get(name, ()) if i not in indexes]
    assert missing == [], f"{name}: {missing} not used; the plan uses {indexes} — nodes {types}"
    # L5 (I5d.3 review): `signups_counts` joins `active_engine`'s exemption from both policy
    # assertions below — a full, ungated `GROUP BY` over the whole table has no index to use BY
    # DESIGN (there is no covering index on `(source, consent_version, launch_mailed_at)`), so a
    # `HashAggregate` over a `Seq Scan` is the correct plan, not a regression to catch.
    assert any("Index" in t for t in types) or name == "signups_counts", types
    assert "Seq Scan" not in types or name in ("active_engine", "signups_counts"), types   # the registry is ~20 rows; a seq scan there is fine


def test_both_scope_name_branches_descend_geo_area_s_primary_key(conn):
    """D-C38 (fix round 1, finding 8). `INDEXES` above is a SET-membership claim, and that is not
    enough for a UNION of two structurally identical branches: an index named once satisfies it
    however many branches use it.

    Measured, not reasoned. Making the place branch's join non-sargable
    (`upper(g.geo_id) = upper(pl.place_geoid)`) leaves the `scope_names` entry above GREEN — the
    county branch still names both indexes, and Postgres reaches for `geo_area_level_idx` to
    bitmap every level-160 row at that vintage, so there is no `Seq Scan` node to catch either.
    What actually happened is a `Hash Join` over a full scan of one summary level, which is the
    degradation `_scope_names`'s two-branch shape exists to prevent and which grows with
    `geo_area`, not with the page.

    So the claim is COUNTED: one `geo_area_pkey` descent and one `practice_location_pkey` lookup
    per branch, two of each in the plan. The mutation above turns the first into 1 and fails."""
    _seed_scope_names(conn)
    sql, params = PLANS["scope_names"]
    with conn.cursor() as cur:
        cur.execute(sql, params)
        plan = cur.fetchone()[0][0]["Plan"]
    indexes = _index_names(plan)
    types = _node_types(plan)
    assert indexes.count("geo_area_pkey") == 2, (
        f"each UNION branch must descend geo_area's primary key; the plan uses {indexes} — nodes {types}"
    )
    assert indexes.count("practice_location_pkey") == 2, (
        f"each UNION branch must look practice_location up by listing_id; the plan uses {indexes} — nodes {types}"
    )
