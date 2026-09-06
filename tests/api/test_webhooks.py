import base64
import hashlib
import hmac
import json
import time

from app.config import settings

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


async def test_delivery_confirms_the_row_without_changing_its_status(client, conn, monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)
    _outbox_row(conn, sent_at="NULL")
    body = _event("email.delivered")
    assert (await client.post("/api/webhooks/resend", content=body, headers=_sig(body))).status_code == 200
    with conn.cursor() as cur:
        cur.execute("SELECT status, sent_at IS NOT NULL FROM email_outbox WHERE provider_id='re_9'")
        assert cur.fetchone() == ("sent", True)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_suppression"); assert cur.fetchone() == (0,)


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
    monkeypatch.setattr(settings, "resend_webhook_secret", "whsec_not!base64!")
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
