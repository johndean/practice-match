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
        cur.execute("""INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source)
                       SELECT md5(random()::text || i::text)::uuid, 'plan-catchment-'||i, 'Plan Catchment '||i, '1 Main St',
                              'Cedar Park', 'TX', '78613', 'published', 'Cedar Park', 'Small animal', 'Cedar Park, TX', 'seed'
                         FROM generate_series(1, 2000) i""")
        cur.execute("""INSERT INTO practice_location (listing_id, address_hash, point, geo_precision, geocoded_at, geocoder_vintage)
                       SELECT id, 'h-'||id, ST_SetSRID(ST_Point(-110 + (random() * 10), 25 + (random() * 10)), 4269),
                              'rooftop', now(), 'Current_Current'
                         FROM listing WHERE slug LIKE 'plan-catchment-%'""")
        cur.execute("""INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source)
                       VALUES (%s, 'plan-catchment-target', 'Plan Catchment Target', '1 Main St', 'Cedar Park', 'TX', '78613',
                               'published', 'Cedar Park', 'Small animal', 'Cedar Park, TX', 'seed')""", (_CATCHMENT_LISTING_ID,))
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


SEEDS: dict[str, Any] = {"users_queue": _seed_admin_queue, "signups_list": _seed_signups, "signups_counts": _seed_signups,
                        "signups_unmailed": _seed_signups, "catchment_tracts": _seed_catchment_geo}


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
