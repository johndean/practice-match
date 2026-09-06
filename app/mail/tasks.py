"""Celery: drain the outbox (every minute), purge expired sessions and delivered outbox rows
(nightly). Never called from a request — the request path writes a row and returns (spec §5).

**No Postgres connection is ever held across the call to Resend.** `app.db.sync_conn()` hands out a
POOLED connection, so a task that kept one for the length of an HTTP round-trip — 20 s at the
timeout, times a batch of 50 — would empty the pool the api shares. Instead `outbox.due()` claims
its batch in one committed statement (lease + `FOR UPDATE SKIP LOCKED`), the connection goes back,
and each row's outcome is recorded on a freshly borrowed connection afterwards. The brief's sketch
held one connection for the whole loop; this is the same behaviour without that.

The QA allowlist (spec §5, S7) is a fail-CLOSED gate: outside production a row is delivered only if
its address is named in `EMAIL_ALLOWLIST`, so an EMPTY allowlist on QA sends to nobody rather than
to everybody. Anything refused is recorded `suppressed` — never silently dropped, never left
`queued` to be tried again.
"""
from __future__ import annotations

from contextlib import closing

import httpx

from app.config import settings
from app.db import sync_conn
from app.mail import outbox as OB
from app.mail import templates as TP
from app.mail.resend_client import ResendClient, ResendError
from app.tasks.celery_app import celery_app

# Spec §5's ladder: 1 min, 10 min, 1 h, 6 h. The Nth failure of a row waits BACKOFF[N-1]; a row that
# has used the whole ladder is `failed`, which is what Admin shows staff.
BACKOFF = (60, 600, 3600, 21600)
# `email_outbox.last_error` is read by humans in Admin, not parsed; 500 characters is a provider
# message, not a stack trace.
MAX_ERROR = 500
# A delivered row is deleted once the longest-lived thing it could have carried — a 24 h verify link
# — has expired anyway (`app.api.auth.VERIFY_TTL`, `scripts.bootstrap_admin.INVITE_TTL`).
SENT_TTL_S = 24 * 60 * 60
SUPPRESSED_REASON = "address is suppressed or not on this environment's allowlist"


def _http() -> httpx.Client:
    """The HTTP client the sender uses. A function so the test suite can hand `send_due` a
    `MockTransport` — nothing in this suite ever reaches Resend."""
    return httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0))


def allowlisted(email: str) -> bool:
    """Production delivers to everyone; every other environment delivers only to the addresses
    `EMAIL_ALLOWLIST` names, so a QA sign-up with a real address cannot email a real person."""
    if settings.environment.lower() == "production":
        return True
    return email.lower() in {entry.strip().lower() for entry in settings.email_allowlist.split(",") if entry.strip()}


def _record(row_id: int, *, status: str, provider_id: str | None = None, error: str | None = None, delay_s: int | None = None) -> None:
    """One row's outcome, on its own borrowed connection (see the module note)."""
    with closing(sync_conn()) as conn, conn:
        OB.mark(conn, row_id, status=status, provider_id=provider_id, error=error, delay_s=delay_s)


def send_due() -> dict[str, int]:
    """Sends every outbox row that is ready, and returns what happened to each."""
    if not settings.resend_api_key:
        # Loud, not silent: a worker whose key is missing would otherwise leave every verification
        # and reset link sitting `queued` while sign-up kept answering "check your email".
        raise RuntimeError("RESEND_API_KEY is not set on this service")
    counts = {"sent": 0, "suppressed": 0, "failed": 0}
    with closing(sync_conn()) as conn, conn:
        sendable = []
        for row in OB.due(conn):
            if OB.suppressed(conn, row["to"]) or not allowlisted(row["to"]):
                OB.mark(conn, row["id"], status="suppressed", error=SUPPRESSED_REASON)
                counts["suppressed"] += 1
            else:
                sendable.append(row)
    with closing(_http()) as http:
        client = ResendClient(settings.resend_api_key, http)
        for row in sendable:
            rendered = TP.render(row["template"], row["params"], base_url=settings.link_base_url)
            try:
                provider_id = client.send(to=row["to"], subject=rendered.subject, text=rendered.text,
                                          html=rendered.html, idempotency_key=row["key"])
            except (ResendError, httpx.HTTPError) as exc:
                attempt = int(row["attempts"]) + 1
                if attempt >= len(BACKOFF):
                    _record(row["id"], status="failed", error=str(exc)[:MAX_ERROR])
                    counts["failed"] += 1
                else:
                    _record(row["id"], status="queued", error=str(exc)[:MAX_ERROR], delay_s=BACKOFF[attempt - 1])
            else:
                _record(row["id"], status="sent", provider_id=provider_id)
                counts["sent"] += 1
    return counts


def purge_sessions() -> dict[str, int]:
    """Spec §7's nightly session purge: expired, long-revoked and long-idle rows."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("""DELETE FROM session WHERE expires_at < now()
                          OR revoked_at < now() - interval '30 days'
                          OR last_seen_at < now() - interval '14 days'""")
        return {"purged": int(cur.rowcount)}


def purge_outbox() -> dict[str, int]:
    """The retention half of the I4 review ruling (the other half is `outbox.mark()` emptying
    `params` the moment a row is terminal): a delivered row is deleted once the token it carried
    would have expired anyway."""
    with closing(sync_conn()) as conn, conn:
        return {"purged": OB.purge_sent(conn, SENT_TTL_S)}


# Registered by CALLING `celery_app.task(...)` rather than by decorating: celery ships no type
# information, so `@celery_app.task` on a typed function is an untyped decorator and mypy --strict
# refuses it (the alternative is a suppression comment, which the standing rulings forbid). The functions
# above stay ordinary, fully typed and directly callable — which is also what the tests call.
send_task = celery_app.task(name="mail.send")(send_due)
purge_sessions_task = celery_app.task(name="mail.purge_sessions")(purge_sessions)
purge_outbox_task = celery_app.task(name="mail.purge_outbox")(purge_outbox)
