"""The append-only audit trail (spec §4/§5) — `audit_log`'s own triggers refuse UPDATE/DELETE/TRUNCATE
(migrations/014_audit_log.sql), so this module only ever INSERTs."""
from __future__ import annotations

import json
from typing import Any

import psycopg2.extensions

from app.auth.sessions import Principal


def write(
    conn: psycopg2.extensions.connection,
    *,
    actor: Principal | None,
    action: str,
    target_type: str,
    target_id: Any = None,
    before: Any = None,
    after: Any = None,
    reason: str | None = None,
    request: Any = None,
) -> None:
    ip = ua = rid = None
    if request is not None:
        from app.auth.limits import client_ip

        ip, ua, rid = client_ip(request), request.headers.get("user-agent"), request.headers.get("x-request-id")
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO audit_log (request_id, actor_id, actor_role, action, target_type, target_id, before, after, ip, ua, reason)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                rid,
                actor.account_id if actor else None,
                ",".join(sorted(actor.roles)) if actor else None,
                action,
                target_type,
                str(target_id) if target_id is not None else None,
                json.dumps(before) if before is not None else None,
                json.dumps(after) if after is not None else None,
                ip,
                ua,
                reason,
            ),
        )
