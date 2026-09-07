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

from app.api.admin_users import LIST_SQL, MAX_LIST

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
PLANS: dict[str, tuple[str, tuple[Any, ...] | dict[str, Any]]] = {
    "users_queue": (
        "EXPLAIN (FORMAT JSON) " + LIST_SQL,
        {"state": "pending", "kind": None, "role": None, "cursor_at": None, "cursor_id": None, "limit": MAX_LIST + 1},
    ),
    "session_lookup": (
        "EXPLAIN (FORMAT JSON) SELECT account_id FROM session WHERE id_hash=%s",
        ("x",),
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


SEEDS: dict[str, Any] = {"users_queue": _seed_admin_queue}


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
    assert any("Index" in t for t in types), types
    assert "Seq Scan" not in types or name == "active_engine", types   # the registry is ~20 rows; a seq scan there is fine
