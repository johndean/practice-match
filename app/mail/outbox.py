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


# How many rows one drain claims. Named (rather than only a default argument) because `LEASE_S`
# below is derived from it and the two must be checkable against each other.
DUE_LIMIT = 50

# How long a claimed row is invisible to other workers (Task I6). `due()` stamps it onto
# `next_attempt_at` in the SAME statement that selects the row, which is what lets the sender give
# the connection back to the pool BEFORE it calls Resend: the rows are already reserved, so no
# transaction has to stay open across a network call. A worker that dies mid-batch loses its lease
# after this long and the rows are picked up again — the provider's idempotency key is what stops
# that becoming a second delivery.
#
# THE INVARIANT (fix round 1, F2): the lease must outlast the worst case wall time of ONE batch —
# `DUE_LIMIT * (connect timeout + read timeout)`, i.e. 50 x 25 s = 1250 s against a provider that
# times out on every request — plus margin. At 900 s the tail of such a batch lost its lease while
# the first worker was still working through it, and since beat fires `mail.send` every 60 s a
# second worker re-claimed those rows: two `mark()`s racing the ladder's `attempts`, two workers
# doing the work, and the idempotency key left as the only thing between that and a double
# delivery. `tests/mail/test_send.py::test_the_lease_outlasts_the_worst_case_batch` pins the
# arithmetic so the three constants (here, and `resend_client.TIMEOUT`) cannot drift apart.
LEASE_S = 1800

# The statuses a row never leaves. `mark()` empties `params` on all of them: the outbox is the one
# place the RAW verify/reset link exists (this module's header note; I4 fix round 1, Minor 4), and
# once a row is finished with, sent or not, keeping the link buys nothing and risks everything.
TERMINAL = frozenset({"sent", "suppressed", "failed", "bounced", "complained"})

CLAIM = """WITH claimed AS (
               SELECT id FROM email_outbox
                WHERE status = 'queued' AND next_attempt_at <= now()
                ORDER BY id LIMIT %(limit)s
                FOR UPDATE SKIP LOCKED
           )
           UPDATE email_outbox o SET next_attempt_at = now() + make_interval(secs => %(lease)s)
             FROM claimed c WHERE o.id = c.id
           RETURNING o.id, o.to_email, o.template, o.params, o.idempotency_key, o.attempts"""

MARK = """UPDATE email_outbox
             SET status = %(status)s,
                 provider_id = COALESCE(%(provider_id)s, provider_id),
                 last_error = %(error)s,
                 attempts = attempts + 1,
                 params = CASE WHEN %(terminal)s THEN '{}'::jsonb ELSE params END,
                 sent_at = CASE WHEN %(status)s = 'sent' THEN now() ELSE sent_at END,
                 next_attempt_at = CASE WHEN %(delay_s)s::int IS NULL THEN next_attempt_at
                                        ELSE now() + make_interval(secs => %(delay_s)s::int) END
           WHERE id = %(id)s"""


def due(conn: psycopg2.extensions.connection, limit: int = DUE_LIMIT) -> list[dict[str, Any]]:
    """Claims up to `limit` rows that are ready to send, and returns them.

    Claiming and reading are one statement on purpose: `FOR UPDATE SKIP LOCKED` keeps two workers
    off the same row, and the lease it writes keeps them off it after this transaction ends, so the
    caller can close the connection before it starts making network calls."""
    with conn.cursor() as cur:
        cur.execute(CLAIM, {"limit": limit, "lease": LEASE_S})
        rows = [dict(zip(("id", "to", "template", "params", "key", "attempts"), r, strict=True)) for r in cur.fetchall()]
    return sorted(rows, key=lambda row: int(row["id"]))


def mark(conn: psycopg2.extensions.connection, row_id: int, *, status: str, provider_id: str | None = None,
         error: str | None = None, delay_s: int | None = None) -> None:
    """Records the outcome of one attempt. `delay_s` re-arms `next_attempt_at` (the retry backoff);
    without it the row keeps whatever the claim left there, which for a terminal status is moot."""
    with conn.cursor() as cur:
        cur.execute(MARK, {"status": status, "provider_id": provider_id, "error": error,
                           "terminal": status in TERMINAL, "delay_s": delay_s, "id": row_id})


def suppressed(conn: psycopg2.extensions.connection, email: str) -> bool:
    """True when this address has bounced, complained, or been suppressed by hand (spec §5)."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM email_suppression WHERE email = %s", (email,))
        return cur.fetchone() is not None


def purge_sent(conn: psycopg2.extensions.connection, ttl_s: int) -> int:
    """Deletes delivered rows older than `ttl_s`, and returns how many.

    The retention rule the I4 review left to this task: a `sent` row has done its work, and the
    longest-lived thing it could ever have carried — a verify link — expires in 24 hours anyway, so
    keeping the row past that is retention without a purpose. Rows in every other state stay:
    `failed` and `bounced` are what Admin shows staff (spec §5)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM email_outbox WHERE status = 'sent' AND sent_at < now() - make_interval(secs => %s)", (ttl_s,))
        return int(cur.rowcount)
