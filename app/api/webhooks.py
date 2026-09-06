"""Resend's delivery events (spec §5, S7).

Public by necessity — Resend has no credential of ours to present — and therefore verified by
signature on every request: Resend signs through Svix, whose scheme is an HMAC-SHA256 of
`{svix-id}.{svix-timestamp}.{raw body}` keyed by the base64 part of the `whsec_…` secret, presented
as a space-separated list of `v1,<base64>` in `svix-signature`. A stale timestamp is refused too
(five minutes), so a captured request cannot be replayed a day later.

Three rules shape what happens after verification:

* **The payload's addresses are never trusted.** A bounce names a recipient; this route ignores it
  and suppresses the address on the OUTBOX ROW that carries the event's `email_id`. Signature or
  no, a body that could name any address it liked must not be able to blacklist a third party.
* **Only three things are a 4xx: an unverifiable signature (401), an oversized body (413) and a
  caller that disconnects mid-body (422, the same quiet answer `app/api/interest.py` gives).** An
  event this route cannot act on — an unknown type, an `email_id` matching no row, a body that is
  not the shape Resend documents — answers `200`, because a provider that is told "error" retries
  the same thing for hours.
* **Every verification failure is the SAME 401.** A missing header, a stale timestamp, a wrong key,
  a signature that is not base64, a secret this environment never had — one class, one message, one
  body. Nothing here may raise anything else: header values reach this module as latin-1-decoded
  `str`, so a single byte in `\\x80-\\xff` used to reach `hmac.compare_digest` as a non-ASCII string
  and turn a public route into a 500 (fix round 1, F1). Digests are compared as BYTES now, and every
  decode happens inside a guard.

**Replay** inside the 300 s timestamp window is not prevented by a nonce cache, and does not need to
be: every effect this route has is idempotent — a status UPDATE to the value it already holds, an
`INSERT … ON CONFLICT DO NOTHING`, and a `COALESCE`d `delivered_at` that keeps the first stamp —
and Svix's own guidance treats the timestamp window as sufficient. If a non-idempotent event is ever
handled here, that stops being true and an `svix-id` cache becomes necessary (fix round 1, F10).
"""
from __future__ import annotations

import base64
import hmac
import json
import time
from collections.abc import Mapping
from contextlib import closing
from hashlib import sha256

from fastapi import APIRouter, Request
from starlette.requests import ClientDisconnect

from app.auth.deps import AuthError
from app.config import settings
from app.db import sync_conn

router = APIRouter(prefix="/api/webhooks")

SECRET_PREFIX = "whsec_"
TOLERANCE_S = 300  # Svix's own recommendation; the window a replayed request can live in
# A Resend event is a small JSON object. This is generous for one and nowhere near enough to be a
# way of spending the api's memory from an unauthenticated route (fix round 1, F9 — the same shape
# `app/api/interest.py` uses, the other anonymous POST surface).
MAX_BODY_BYTES = 64 * 1024
# event type -> (email_outbox.status, email_suppression.reason)
SUPPRESSION = {"email.bounced": ("bounced", "bounce"), "email.complained": ("complained", "complaint")}


class WebhookUnverified(AuthError):
    """Decision A5's envelope for an unsigned, missigned, stale or unconfigured webhook call.
    One class for all of them on purpose: the caller learns nothing about which check failed."""

    status = 401
    code = "UNAUTHORIZED"
    message = "The webhook signature could not be verified."


class PayloadTooLarge(AuthError):
    """Refused on size, before any signature work — so an oversized body is never even hashed."""

    status = 413
    code = "PAYLOAD_TOO_LARGE"
    message = "The request body is too large."


class RequestIncomplete(AuthError):
    """The caller went away mid-body. Not an error and not a 500 (round 2, O1) — the same quiet 422
    the other anonymous POST surface answers with (`app/api/interest.py`), carrying the app's one
    existing 422 envelope (`app.auth.deps.INVALID_REQUEST`) rather than a second one invented here."""

    status = 422
    code = "INVALID_REQUEST"
    message = "The request could not be understood. Check the fields and try again."


def declared_length(request: Request) -> int | None:
    """Content-Length as an int (0 when absent — chunked bodies are capped while streaming); None
    when the header is not a plain decimal number. `isdecimal()`, not `isdigit()`: "²".isdigit() is
    True but int("²") raises. Same rule as `app.api.interest.declared_length`."""
    value = request.headers.get("content-length", "0").strip()
    return int(value) if value.isdecimal() else None


async def read_capped(request: Request) -> bytes:
    """The body, refusing anything past `MAX_BODY_BYTES`. Checked twice because a chunked request
    declares no length at all: once against what the caller says it is sending, and again against
    what actually arrives."""
    if (declared := declared_length(request)) is None or declared > MAX_BODY_BYTES:
        raise PayloadTooLarge()
    chunks: list[bytes] = []
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                raise PayloadTooLarge()
            chunks.append(chunk)
    except ClientDisconnect:
        # The peer aborted mid-body: there is no complete body to verify and nothing to apply, so
        # this ends here — quietly, with no traceback and without opening a connection (O1).
        raise RequestIncomplete() from None
    return b"".join(chunks)


def _key(secret: str) -> bytes:
    """The signing key: the base64 payload after `whsec_`. A secret that is not valid base64 — or
    not even ASCII — is a misconfiguration, and the only safe reading of it is "nothing verifies".
    `ValueError` rather than `binascii.Error`: a non-ASCII `str` raises the plain parent class
    (fix round 1, F6)."""
    try:
        return base64.b64decode(secret.removeprefix(SECRET_PREFIX), validate=True)
    except ValueError:
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
    expected = hmac.new(_key(secret), signed, sha256).digest()
    # Svix presents a space-separated list — during a key rotation the new key's signature can be
    # the second entry — so every `v1,` entry is tried before this gives up.
    for entry in presented.split(" "):
        version, _, value = entry.partition(",")
        if version != "v1":
            continue
        try:
            digest = base64.b64decode(value, validate=True)
        except ValueError:
            continue   # not base64, or not even ASCII: it cannot be a signature (F1)
        # `compare_digest` on BYTES: this is a signature comparison on a public route, and the str
        # overload refuses non-ASCII input with a TypeError.
        if hmac.compare_digest(digest, expected):
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
        # `delivered_at`, not `sent_at`: `outbox.mark()` sets `sent_at` the moment we hand the
        # message to Resend, so stamping it here would record nothing (fix round 1, F3). What this
        # event adds is the later fact — the recipient's mail server took it. `COALESCE` keeps the
        # first stamp, so a repeated event changes nothing.
        with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE email_outbox SET delivered_at = COALESCE(delivered_at, now()) WHERE provider_id = %s AND status = 'sent'", (provider_id,))


@router.post("/resend")
async def resend_events(request: Request) -> dict[str, bool]:
    body = await read_capped(request)
    verify(body, request.headers)
    kind, provider_id = _event(body)
    if provider_id:
        _apply(kind, provider_id)
    return {"ok": True}
