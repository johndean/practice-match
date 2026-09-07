"""Policy §3's "hot queries use indexes" gate — `EXPLAIN (FORMAT JSON)` on the queries a slow
plan would be felt through, asserted against the index each one is supposed to use.

The harness is the one `docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md` §5
prints. The file itself is created here, in Wave 2a Task I9a, rather than in Census B5 / Map
engines M1 as §4's table expects: those two tasks own the `market_metric`, `practice_location` and
`dataset_registry` entries, and none of those tables exists yet, so their rows join `PLANS` when
their migrations do. Nothing about the harness changes when they arrive.

Each entry names its index rather than only asking for "some Index Scan". A plan-shape assertion
alone passes for the wrong reason on a small table — Postgres will happily index-scan a two-row
relation and would equally happily sequential-scan it — so what is pinned is the index the
migration created, by name. Dropping `application_queue_idx` turns this file red; a query rewritten
so that it can no longer use it does too.
"""
from __future__ import annotations

from typing import Any

import pytest

# name -> (statement, params, expected index name). The queries are the shape the application
# issues, not a simplification of it:
#
#   users_queue     the review queue behind `GET /api/admin/users?state=pending` — the filter and
#                   the ordering are both served by `application_queue_idx (status, submitted_at)`
#                   from `migrations/011_applications_roles.sql`.
#   session_lookup  `app.auth.sessions.resolve`'s Postgres half, taken on every request whose
#                   principal cache has expired. `session.id_hash` is the primary key
#                   (`migrations/010_accounts.sql`), so the index is `session_pkey`.
PLANS: dict[str, tuple[str, tuple[Any, ...], str]] = {
    "users_queue": (
        "EXPLAIN (FORMAT JSON) SELECT * FROM application WHERE status='pending' ORDER BY submitted_at LIMIT 50",
        (),
        "application_queue_idx",
    ),
    "session_lookup": (
        "EXPLAIN (FORMAT JSON) SELECT account_id FROM session WHERE id_hash=%s",
        ("x",),
        "session_pkey",
    ),
}


def _nodes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Every node of the plan tree, parents before children."""
    out = [plan]
    for child in plan.get("Plans", []):
        out += _nodes(child)
    return out


@pytest.mark.parametrize("name", sorted(PLANS))
def test_hot_query_uses_its_index(conn, name):
    sql, params, index = PLANS[name]
    with conn.cursor() as cur:
        cur.execute(sql, params)
        plan = cur.fetchone()[0][0]["Plan"]
    nodes = _nodes(plan)
    types = [n.get("Node Type") for n in nodes]
    indexes = [n.get("Index Name") for n in nodes if n.get("Index Name")]
    assert index in indexes, f"{name}: plan does not use {index}; nodes {types}, indexes {indexes}"
    assert "Seq Scan" not in types, f"{name}: plan still sequential-scans; nodes {types}"
