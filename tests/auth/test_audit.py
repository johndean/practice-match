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
    """audit.write's own client_ip call is duck-typed (app.auth.deps): a plain dict of headers
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


def test_write_redacts_secret_shaped_keys_at_every_depth(conn):
    """Important 2: `audit_log`'s triggers refuse UPDATE, DELETE and TRUNCATE, so anything written
    here can never be corrected — and the `before`/`after` API invites a caller to hand it a whole
    row (`account` rows carry `password_hash`, `api_token` rows carry `token_hash`). Redacting in
    the WRITER is the only place this can be guaranteed once, for every future caller."""
    audit.write(
        conn,
        actor=_principal("admin"),
        action="users.decide",
        target_type="account",
        before={"email": "vet@x.io", "password_hash": "$argon2id$v=19$...", "state": "pending"},
        after={
            "state": "active",
            "credentials": {"Token_Hash": "deadbeef", "API_SECRET": "s3cr3t", "kept": 1},
            "grants": [{"role": "buyer", "reset_token": "abc"}, {"role": "seller"}],
            "notes": "no secrets here",
        },
    )
    _, _, _, _, _, _, before, after, *_ = _last_row(conn)
    assert before == {"email": "vet@x.io", "state": "pending"}
    assert after == {
        "state": "active",
        "credentials": {"kept": 1},
        "grants": [{"role": "buyer"}, {"role": "seller"}],
        "notes": "no secrets here",
    }


def test_actor_role_tells_a_human_from_a_machine(conn):
    """Important 10: `actor_id` has no FK and every principal's roles were written as a bare
    comma-joined list, so an audit row left by a CI token read exactly like one left by the staff
    member who owns it. The kind is now part of `actor_role`, which is the column an auditor
    actually reads."""
    from uuid import UUID

    from app.auth.deps import LEGACY_ADMIN
    audit.write(conn, actor=Principal(uuid4(), "active", frozenset({"admin"}), None, "token"), action="engine.activate", target_type="engine")
    assert _last_row(conn)[2] == "token:admin"
    audit.write(conn, actor=Principal(LEGACY_ADMIN, "active", frozenset({"admin"}), None, "legacy"), action="engine.activate", target_type="engine")
    assert _last_row(conn)[2] == "legacy:operator"
    assert LEGACY_ADMIN == UUID("00000000-0000-0000-0000-000000000001")
    audit.write(conn, actor=_principal("staff", "admin"), action="users.decide", target_type="account")
    assert _last_row(conn)[2] == "admin,staff"
    audit.write(conn, actor=None, action="abuse.investigate", target_type="listing")
    assert _last_row(conn)[2] is None


class _ForgedRequest:
    """An `X-Forwarded-For` an attacker can set to anything at all."""

    headers: ClassVar[dict[str, str]] = {"x-forwarded-for": "unknown", "user-agent": "curl/8", "x-request-id": "req-forged"}


def test_a_forged_forwarded_for_stores_null_rather_than_failing_the_write(conn):
    """Minor 3: `client_ip()`'s raw string went straight into an `inet` column, so
    `X-Forwarded-For: unknown` raised psycopg2's InvalidTextRepresentation — a 500 AND a lost audit
    row, on the one write path that must never fail. Validated with `ipaddress.ip_address` now:
    what is not an address is not an address."""
    audit.write(conn, actor=None, action="abuse.investigate", target_type="listing", request=_ForgedRequest())
    rid, _, _, _, _, _, _, _, ip, ua, _ = _last_row(conn)
    assert ip is None and rid == "req-forged" and ua == "curl/8"
