"""The transactional-email outbox. Task I4 creates the single function that WRITES a row; Task I6
adds the sender that drains it. Nothing here ever talks to the network — that is the point of an
outbox: the request path commits a row and returns, and delivery is somebody else's problem.

One consequence is recorded here for Task I6 (fix round 1, Minor 4): `params->>'link'` holds the RAW
verify/reset token until the row is sent, so "hashed at rest" holds for `email_token` and not for
this table. I6 owns the remedy — null `params` once a row reaches `sent`, or purge sent rows on the
token's own TTL — because it is the task that knows when a row is finished with."""
from __future__ import annotations

import json
from typing import Any

import psycopg2.extensions

# The keys `app/mail/templates.py` will render (Task I6), and the only values this function accepts:
# a typo would otherwise sit in the outbox forever, undeliverable and invisible until the sender
# reached it. `account_exists` is the fourteenth, added in I4 fix round 1 so that a sign-up for an
# ALREADY REGISTERED address does the same commit-level work as one for a new address (Critical 1)
# — and so that the address's owner learns somebody tried to sign up as them.
TEMPLATES = frozenset({
    "verify_email", "account_exists", "application_received", "application_approved", "application_declined",
    "application_info_requested", "seller_application_received", "seller_application_approved",
    "seller_application_declined", "password_reset", "password_changed", "signin_new_device",
    "account_suspended", "account_revoked",
})

INSERT = """INSERT INTO email_outbox (to_email, template, params, idempotency_key) VALUES (%s,%s,%s,%s)
            ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"""


def enqueue(conn: psycopg2.extensions.connection, *, to: str, template: str, params: dict[str, Any], idempotency_key: str) -> bool:
    """Writes the outbox row; returns False when the key already exists (idempotent)."""
    if template not in TEMPLATES:
        raise KeyError(f"unknown email template {template!r}")
    with conn.cursor() as cur:
        cur.execute(INSERT, (to, template, json.dumps(params), idempotency_key))
        return cur.fetchone() is not None
