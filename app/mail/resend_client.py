"""The one place Practice Match talks to Resend (spec §5).

Deliberately thin and synchronous: it is called from a Celery task, never from a request, and it
knows nothing about the outbox — `app.mail.tasks` decides what to do with a failure. `ResendError`
carries the status so the caller can back off; the body is truncated because it goes into
`email_outbox.last_error`, which staff read in Admin.

`Idempotency-Key` is the outbox row's own `idempotency_key` (spec §5, S7), so a retry after a
timeout — where the send may in fact have gone through — cannot deliver the same message twice.
"""
from __future__ import annotations

import httpx

from app.config import settings

ENDPOINT = "https://api.resend.com/emails"
# 20 s overall, 5 s to connect: long enough for a slow provider, short enough that a black-holed
# host cannot pin a worker slot for a whole beat interval.
TIMEOUT = httpx.Timeout(20.0, connect=5.0)


class ResendError(RuntimeError):
    """A non-2xx answer from Resend. `status` is what decides retry-or-give-up in `app.mail.tasks`."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"resend {status}: {body[:200]}")
        self.status = status


class ResendClient:
    def __init__(self, api_key: str, http: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.http = http if http is not None else httpx.Client(timeout=TIMEOUT)

    def send(self, *, to: str, subject: str, text: str, html: str, idempotency_key: str) -> str:
        """The provider's message id, which the webhook later matches delivery events against."""
        response = self.http.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {self.api_key}", "Idempotency-Key": idempotency_key},
            json={"from": settings.mail_from, "to": [to], "reply_to": settings.mail_reply_to,
                  "subject": subject, "text": text, "html": html},
        )
        if response.status_code >= 300:
            raise ResendError(response.status_code, response.text)
        return str(response.json()["id"])
