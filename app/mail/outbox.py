"""The transactional-email outbox. Task I4 creates the single function that WRITES a row; Task I6
adds the sender that drains it. Nothing here ever talks to the network — that is the point of an
outbox: the request path commits a row and returns, and delivery is somebody else's problem."""
from __future__ import annotations

import json
from typing import Any

import psycopg2.extensions

INSERT = """INSERT INTO email_outbox (to_email, template, params, idempotency_key) VALUES (%s,%s,%s,%s)
            ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"""


def enqueue(conn: psycopg2.extensions.connection, *, to: str, template: str, params: dict[str, Any], idempotency_key: str) -> bool:
    """Writes the outbox row; returns False when the key already exists (idempotent)."""
    with conn.cursor() as cur:
        cur.execute(INSERT, (to, template, json.dumps(params), idempotency_key))
        return cur.fetchone() is not None
