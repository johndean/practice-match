"""The append-only audit trail (spec §4/§5) — `audit_log`'s own triggers refuse UPDATE/DELETE/TRUNCATE
(migrations/014_audit_log.sql), so this module only ever INSERTs."""
from __future__ import annotations

import json
import re
from typing import Any

import psycopg2.extensions

from app.auth.deps import client_ip
from app.auth.sessions import Principal

_SECRET_KEY_RE = re.compile(r"password|hash|secret|token", re.IGNORECASE)


def _redacted(value: Any) -> Any:
    """`value` with every key whose NAME mentions a password, hash, secret or token dropped, at any
    depth (Important 2). `audit_log` is append-only by trigger, so a secret written here can never
    be removed without dropping the table; the `before`/`after` API invites callers to hand it a
    fetched row, and `account`/`api_token` rows carry exactly those columns. Names, not values: a
    heuristic on the value would be both slower and far easier to fool."""
    if isinstance(value, dict):
        return {k: _redacted(v) for k, v in value.items() if not _SECRET_KEY_RE.search(str(k))}
    if isinstance(value, list):
        return [_redacted(v) for v in value]
    return value


def _actor_role(actor: Principal | None) -> str | None:
    """The roles an audit row records, prefixed with the KIND of caller (Important 10). `actor_id`
    carries no foreign key and, for a token, is the account that minted it — so without this an
    auditor cannot tell an action a staff member took from one their CI token took on their
    behalf. The legacy operator secret has no account at all, so it says so."""
    if actor is None:
        return None
    if actor.kind == "legacy":
        return "legacy:operator"
    roles = ",".join(sorted(actor.roles))
    return f"token:{roles}" if actor.kind == "token" else roles


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
        ip, ua, rid = client_ip(request), request.headers.get("user-agent"), request.headers.get("x-request-id")
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO audit_log (request_id, actor_id, actor_role, action, target_type, target_id, before, after, ip, ua, reason)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                rid,
                actor.account_id if actor else None,
                _actor_role(actor),
                action,
                target_type,
                str(target_id) if target_id is not None else None,
                json.dumps(_redacted(before)) if before is not None else None,
                json.dumps(_redacted(after)) if after is not None else None,
                ip,
                ua,
                reason,
            ),
        )
