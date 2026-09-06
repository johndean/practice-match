"""app/auth/audit.py has no Step 1 test file in the brief's task-I3 — these close the coverage
gap for it (100% lines and branches, John's standing ruling): both the request-present and
request-absent paths of `write()`, and a round trip through the append-only audit_log table."""
from typing import ClassVar
from uuid import uuid4

from app.auth import audit
from app.auth.sessions import Principal


def _principal(*roles: str) -> Principal:
    return Principal(uuid4(), "active", frozenset(roles), None, "session", "h")


def _last_row(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT request_id, actor_id, actor_role, action, target_type, target_id, before, after, ip, ua, reason "
            "FROM audit_log ORDER BY id DESC LIMIT 1"
        )
        return cur.fetchone()


class _FakeRequest:
    """audit.write's own client_ip call is duck-typed (app.auth.limits): a plain dict of headers
    and no `.client` attribute at all is enough."""

    headers: ClassVar[dict[str, str]] = {"x-forwarded-for": "203.0.113.9", "user-agent": "pytest-agent", "x-request-id": "req-abc"}


def test_write_with_actor_and_request_records_every_field(conn):
    actor = _principal("staff", "admin")
    target = uuid4()
    audit.write(
        conn,
        actor=actor,
        action="users.decide",
        target_type="account",
        target_id=target,
        before={"state": "pending"},
        after={"state": "active"},
        reason="looks legitimate",
        request=_FakeRequest(),
    )
    rid, actor_id, actor_role, action, target_type, target_id, before, after, ip, ua, reason = _last_row(conn)
    assert rid == "req-abc"
    assert actor_id == actor.account_id
    assert actor_role == "admin,staff"  # sorted, comma-joined
    assert action == "users.decide"
    assert target_type == "account"
    assert target_id == str(target)
    assert before == {"state": "pending"}
    assert after == {"state": "active"}
    assert ip == "203.0.113.9"
    assert ua == "pytest-agent"
    assert reason == "looks legitimate"


def test_write_with_no_actor_and_no_request_leaves_the_optional_columns_null(conn):
    audit.write(conn, actor=None, action="abuse.investigate", target_type="listing")
    rid, actor_id, actor_role, action, target_type, target_id, before, after, ip, ua, reason = _last_row(conn)
    assert rid is None and actor_id is None and actor_role is None
    assert action == "abuse.investigate" and target_type == "listing"
    assert target_id is None and before is None and after is None
    assert ip is None and ua is None and reason is None
