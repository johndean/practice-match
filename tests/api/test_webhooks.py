import base64
import hashlib
import hmac
import json
import time

import httpx

from app.config import settings
from app.mail import outbox as OB
from app.mail import tasks as MT

SECRET = "whsec_" + base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


def _sig(body: bytes, msg_id="msg_1", ts=None):
    ts = ts or str(int(time.time()))
    signed = f"{msg_id}.{ts}.".encode() + body
    mac = hmac.new(base64.b64decode(SECRET[6:]), signed, hashlib.sha256).digest()
    return {"svix-id": msg_id, "svix-timestamp": ts, "svix-signature": "v1," + base64.b64encode(mac).decode(), "Content-Type": "application/json"}


async def test_bounce_suppresses_and_marks_outbox(client, conn, monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO email_outbox (to_email, template, params, idempotency_key, status, provider_id) VALUES ('b@example.org','verify_email','{}','k9','sent','re_9')")
    body = json.dumps({"type": "email.bounced", "data": {"email_id": "re_9", "to": ["b@example.org"]}}).encode()
    r = await client.post("/api/webhooks/resend", content=body, headers=_sig(body))
    assert r.status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM email_outbox WHERE provider_id='re_9'"); assert cur.fetchone() == ("bounced",)
        cur.execute("SELECT reason FROM email_suppression WHERE email='b@example.org'"); assert cur.fetchone() == ("bounce",)


async def test_bad_signature_and_stale_timestamp_are_refused(client, monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    body = json.dumps({"type": "email.delivered", "data": {"email_id": "x", "to": ["a@example.org"]}}).encode()
    h = _sig(body); h["svix-signature"] = "v1,AAAA"
    assert (await client.post("/api/webhooks/resend", content=body, headers=h)).status_code == 401
    assert (await client.post("/api/webhooks/resend", content=body, headers=_sig(body, ts=str(int(time.time()) - 900)))).status_code == 401


# --- supplemental (not in the brief's Step 1 — the other events, the trust rule, and branches) ---


def _event(kind, email_id="re_9", to="b@example.org"):
    return json.dumps({"type": kind, "data": {"email_id": email_id, "to": [to]}}).encode()


def _outbox_row(conn, provider_id="re_9", email="b@example.org", status="sent", sent_at="now()"):
    with conn.cursor() as cur:
        cur.execute(f"INSERT INTO email_outbox (to_email, template, params, idempotency_key, status, provider_id, sent_at)"
                    f" VALUES (%s,'verify_email','{{}}',%s,%s,%s,{sent_at})", (email, f"key-{provider_id}", status, provider_id))


async def test_a_complaint_suppresses_the_address_and_marks_the_row(client, conn, monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    _outbox_row(conn)
    body = _event("email.complained")
    assert (await client.post("/api/webhooks/resend", content=body, headers=_sig(body))).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM email_outbox WHERE provider_id='re_9'"); assert cur.fetchone() == ("complained",)
        cur.execute("SELECT reason FROM email_suppression WHERE email='b@example.org'"); assert cur.fetchone() == ("complaint",)


async def test_delivery_stamps_delivered_at_on_a_row_the_pipeline_really_produced(client, conn, monkeypatch):
    """F3. `sent_at` is already set by `outbox.mark()` the moment a row reaches `sent`, so the old
    branch (`sent_at = COALESCE(sent_at, now())`) changed nothing on any row production can make —
    and the old test hid that by hand-inserting `sent_at = NULL`, a state the pipeline cannot
    produce. Spec §5 asks the webhook to record `delivered`, and "Resend accepted it" is not the
    same fact as "the recipient's mail server accepted it": `delivered_at` is the second one, and it
    is what staff need when a member says the email never arrived.

    So the row here is made the way production makes one — enqueue, then `send_due()` — and the
    assertion is that delivery stamps `delivered_at` and leaves `status` and `sent_at` alone."""
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr(settings, "email_allowlist", "b@example.org")
    monkeypatch.setattr(settings, "environment", "qa")
    monkeypatch.setattr(MT, "_http", lambda: httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"id": "re_9"}))))
    OB.enqueue(conn, to="b@example.org", template="verify_email",
               params={"link": "https://qa.foundation.vin/verify?token=t"}, idempotency_key="k-delivered")
    assert MT.send_due()["sent"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT status, sent_at, delivered_at FROM email_outbox WHERE provider_id='re_9'")
        status, sent_at, delivered_at = cur.fetchone()
    assert (status, delivered_at) == ("sent", None), "a sent row has not been delivered yet"

    body = _event("email.delivered")
    assert (await client.post("/api/webhooks/resend", content=body, headers=_sig(body))).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT status, sent_at, delivered_at IS NOT NULL FROM email_outbox WHERE provider_id='re_9'")
        assert cur.fetchone() == ("sent", sent_at, True)
        cur.execute("SELECT count(*) FROM email_suppression"); assert cur.fetchone() == (0,)


async def test_a_second_delivery_event_keeps_the_first_delivered_at(client, conn, monkeypatch):
    """Resend may repeat an event, and F10's reasoning — replay inside the 300 s window is harmless —
    rests on every effect being idempotent. `COALESCE` is what makes this one so."""
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    _outbox_row(conn)
    body = _event("email.delivered")
    assert (await client.post("/api/webhooks/resend", content=body, headers=_sig(body))).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT delivered_at FROM email_outbox WHERE provider_id='re_9'"); first = cur.fetchone()[0]
    assert first is not None
    assert (await client.post("/api/webhooks/resend", content=body, headers=_sig(body, msg_id="msg_2"))).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT delivered_at FROM email_outbox WHERE provider_id='re_9'"); assert cur.fetchone()[0] == first


async def test_an_oversized_body_is_refused_before_it_is_buffered(client, monkeypatch):
    """F9. A public, unauthenticated POST that buffers whatever it is given is a free memory tap;
    `app/api/interest.py` — the only other anonymous POST surface — caps its body the same two ways,
    and this route now matches it. The cap is checked BEFORE any signature work, so an oversized
    request never reaches the HMAC either."""
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    from app.api import webhooks as WH

    oversized = b'{"padding":"' + b"x" * (WH.MAX_BODY_BYTES + 1) + b'"}'
    declared = await client.post("/api/webhooks/resend", content=oversized, headers=_sig(oversized))

    async def _stream():                       # no Content-Length: the cap has to hold while streaming
        yield b'{"padding":"'
        for _ in range((WH.MAX_BODY_BYTES // 1024) + 2):
            yield b"x" * 1024
        yield b'"}'

    chunked = await client.post("/api/webhooks/resend", content=_stream(), headers={"svix-id": "msg_1", "svix-timestamp": str(int(time.time())),
                                                                                    "svix-signature": "v1,AAAA", "Content-Type": "application/json"})
    for r in (declared, chunked):
        assert r.status_code == 413, r.text
        assert r.json() == {"error": {"code": "PAYLOAD_TOO_LARGE", "message": "The request body is too large."}}


async def test_a_bounce_never_suppresses_an_address_the_payload_merely_names(client, conn, monkeypatch):
    """The security rule of this route: the body is signed, not trustworthy. An event whose
    `email_id` matches no outbox row must leave `email_suppression` alone — otherwise anyone who
    ever obtained the signing secret could blacklist a third party's mailbox in one request."""
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    _outbox_row(conn, provider_id="re_mine", email="mine@example.org")
    body = _event("email.bounced", email_id="re_not_ours", to="victim@example.org")
    assert (await client.post("/api/webhooks/resend", content=body, headers=_sig(body))).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_suppression"); assert cur.fetchone() == (0,)
        cur.execute("SELECT status FROM email_outbox WHERE provider_id='re_mine'"); assert cur.fetchone() == ("sent",)


async def test_an_event_this_route_cannot_act_on_is_a_quiet_200(client, conn, monkeypatch):
    """A 4xx tells Resend to try again, for hours, with something we will never understand."""
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    _outbox_row(conn)
    for body in (_event("email.opened"), _event("email.bounced", email_id=""), b"not json at all",
                 json.dumps(["not", "an", "object"]).encode(), json.dumps({"type": "email.bounced"}).encode()):
        r = await client.post("/api/webhooks/resend", content=body, headers=_sig(body))
        assert r.status_code == 200 and r.json() == {"ok": True}, body
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM email_outbox"); assert cur.fetchone() == ("sent",)
        cur.execute("SELECT count(*) FROM email_suppression"); assert cur.fetchone() == (0,)


async def test_every_way_of_failing_verification_is_the_same_401_with_the_a5_body(client, monkeypatch):
    """Decision A5's envelope, and one message for all of them: a caller must not be able to tell a
    missing header from a wrong key from a secret this environment never had."""
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    body = _event("email.bounced")
    good = _sig(body)

    refused = []
    refused.append(await client.post("/api/webhooks/resend", content=body, headers={"Content-Type": "application/json"}))
    for header in ("svix-id", "svix-timestamp", "svix-signature"):
        refused.append(await client.post("/api/webhooks/resend", content=body, headers={**good, header: ""}))
    refused.append(await client.post("/api/webhooks/resend", content=body, headers={**good, "svix-timestamp": "not-a-time"}))
    refused.append(await client.post("/api/webhooks/resend", content=body, headers={**good, "svix-signature": good["svix-signature"].replace("v1,", "v2,")}))
    refused.append(await client.post("/api/webhooks/resend", content=body + b" ", headers=good))  # a body that was tampered with in flight
    # F1: h11's header grammar admits any byte in 0x80-0xff and Starlette decodes headers as latin-1,
    # so an unauthenticated caller can put a non-ASCII character in front of `hmac.compare_digest`.
    # Comparing two `str`s raises TypeError there, which on a public route is a 500 — this route's
    # whole contract is that every verification failure is the same 401.
    refused.append(await client.post("/api/webhooks/resend", content=body, headers={**good, "svix-signature": b"v1,\xc3\xa9bad"}))
    refused.append(await client.post("/api/webhooks/resend", content=body, headers={**good, "svix-signature": "v1,not!base64!"}))
    monkeypatch.setattr(settings, "resend_webhook_secret", "whsec_not!base64!")
    refused.append(await client.post("/api/webhooks/resend", content=body, headers=good))
    # F6: a non-ASCII secret raises a plain ValueError, not the binascii.Error subclass.
    monkeypatch.setattr(settings, "resend_webhook_secret", "whsec_\u00c3bad")
    refused.append(await client.post("/api/webhooks/resend", content=body, headers=good))
    monkeypatch.setattr(settings, "resend_webhook_secret", None)
    refused.append(await client.post("/api/webhooks/resend", content=body, headers=good))

    for r in refused:
        assert r.status_code == 401, r.text
        assert r.json() == {"error": {"code": "UNAUTHORIZED", "message": "The webhook signature could not be verified."}}


async def test_a_second_listed_signature_is_accepted_and_the_secret_may_be_bare(client, conn, monkeypatch):
    """Svix presents a space-separated list during a secret rotation — the new key's signature can
    be the second entry — and writes the secret with a `whsec_` prefix that is not part of the key."""
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET[len("whsec_"):])
    _outbox_row(conn)
    body = _event("email.bounced")
    headers = _sig(body)
    headers["svix-signature"] = "v1,b3RoZXI= " + headers["svix-signature"]
    assert (await client.post("/api/webhooks/resend", content=body, headers=headers)).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM email_outbox WHERE provider_id='re_9'"); assert cur.fetchone() == ("bounced",)
