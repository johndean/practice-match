"""Resend's delivery events (spec §5, S7).

Public by necessity — Resend has no credential of ours to present — and therefore verified by
signature on every request: Resend signs through Svix, whose scheme is an HMAC-SHA256 of
`{svix-id}.{svix-timestamp}.{raw body}` keyed by the base64 part of the `whsec_…` secret, presented
as a space-separated list of `v1,<base64>` in `svix-signature`. A stale timestamp is refused too
(five minutes), so a captured request cannot be replayed a day later.

Two rules shape what happens after verification:

* **The payload's addresses are never trusted.** A bounce names a recipient; this route ignores it
  and suppresses the address on the OUTBOX ROW that carries the event's `email_id`. Signature or
  no, a body that could name any address it liked must not be able to blacklist a third party.
* **Nothing here is a 4xx except verification.** An event this route cannot act on — an unknown
  type, an `email_id` matching no row, a body that is not the shape Resend documents — answers
  `200`, because a provider that is told "error" retries the same thing for hours.
"""
from __future__ import annotations

import base64
import binascii
import hmac
import json
import time
from collections.abc import Mapping
from contextlib import closing
from hashlib import sha256

from fastapi import APIRouter, Request

from app.auth.deps import AuthError
from app.config import settings
from app.db import sync_conn

router = APIRouter(prefix="/api/webhooks")

SECRET_PREFIX = "whsec_"
TOLERANCE_S = 300  # Svix's own recommendation; the window a replayed request can live in
# event type -> (email_outbox.status, email_suppression.reason)
SUPPRESSION = {"email.bounced": ("bounced", "bounce"), "email.complained": ("complained", "complaint")}


class WebhookUnverified(AuthError):
    """Decision A5's envelope for an unsigned, missigned, stale or unconfigured webhook call.
    One class for all of them on purpose: the caller learns nothing about which check failed."""

    status = 401
    code = "UNAUTHORIZED"
    message = "The webhook signature could not be verified."


def _key(secret: str) -> bytes:
    """The signing key: the base64 payload after `whsec_`. A secret that is not valid base64 is a
    misconfiguration, and the only safe reading of it is "nothing verifies"."""
    encoded = secret.removeprefix(SECRET_PREFIX)
    try:
        return base64.b64decode(encoded, validate=True)
    except binascii.Error:
        raise WebhookUnverified() from None


def _fresh(timestamp: str) -> bool:
    try:
        sent = int(timestamp)
    except ValueError:
        return False
    return abs(time.time() - sent) <= TOLERANCE_S


def verify(body: bytes, headers: Mapping[str, str]) -> None:
    """Returns quietly when `body` carries a valid, current Svix signature; raises otherwise."""
    secret = settings.resend_webhook_secret
    msg_id, timestamp, presented = (headers.get(h, "") for h in ("svix-id", "svix-timestamp", "svix-signature"))
    if not (secret and msg_id and timestamp and presented and _fresh(timestamp)):
        raise WebhookUnverified()
    signed = msg_id.encode() + b"." + timestamp.encode() + b"." + body
    expected = base64.b64encode(hmac.new(_key(secret), signed, sha256).digest()).decode()
    for entry in presented.split(" "):
        version, _, value = entry.partition(",")
        # `compare_digest`, not `==`: this is a signature comparison on a public route.
        if version == "v1" and hmac.compare_digest(value, expected):
            return
    raise WebhookUnverified()


def _event(body: bytes) -> tuple[str, str]:
    """(event type, provider message id), or ("", "") for anything that is not the documented shape."""
    try:
        payload = json.loads(body)
        return str(payload["type"]), str(payload["data"]["email_id"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return "", ""


def _apply(kind: str, provider_id: str) -> None:
    if kind in SUPPRESSION:
        status, reason = SUPPRESSION[kind]
        with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE email_outbox SET status = %s WHERE provider_id = %s RETURNING to_email", (status, provider_id))
            row = cur.fetchone()
            if row is not None:
                # The address comes from the outbox row, never from the payload (module note).
                cur.execute("INSERT INTO email_suppression (email, reason) VALUES (%s, %s) ON CONFLICT (email) DO NOTHING", (row[0], reason))
    elif kind == "email.delivered":
        # Delivery confirms what `sent` already claimed; the row keeps its status and its original
        # send time, and only gains one if the provider beat the worker's own UPDATE to it.
        with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE email_outbox SET sent_at = COALESCE(sent_at, now()) WHERE provider_id = %s AND status = 'sent'", (provider_id,))


@router.post("/resend")
async def resend_events(request: Request) -> dict[str, bool]:
    body = await request.body()
    verify(body, request.headers)
    kind, provider_id = _event(body)
    if provider_id:
        _apply(kind, provider_id)
    return {"ok": True}
