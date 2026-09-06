import logging
import unicodedata
import uuid

import psycopg2
import pytest

from app.api.interest import CONSENT_VERSION, LIMITS
from app.config import settings
from app.db import get_redis
from app.ratelimit import bucket_key, hit

RUN = uuid.uuid4().hex[:8]  # every rate-limit probe address carries this tag, so cleanup is scoped to this run (M8)


def _count() -> int:
    with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM interest_signup")
        return int(cur.fetchone()[0])


def _probe_email() -> str:
    return f"rl-{RUN}-{uuid.uuid4().hex[:8]}@example.org"


def _rows(norm: str) -> list[tuple]:
    with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT email, email_normalised, consent_version, source FROM interest_signup WHERE email_normalised = %s", (norm,))
        return cur.fetchall()


@pytest.fixture
def addr():
    """A unique address per test so rate-limit windows and rows never cross tests; rows are removed after."""
    tag = uuid.uuid4().hex[:10]
    yield f"Test-{tag}@Example.org"
    with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM interest_signup WHERE email_normalised LIKE %s", (f"test-{tag}@%",))


def _ip() -> str:
    """A fresh client address per call (16M values) so per-IP windows never collide across tests or reruns."""
    n = uuid.uuid4().int
    return "10." + ".".join(str((n >> s) & 255) for s in (16, 8, 0))


async def test_new_address_is_stored_normalised_with_consent_and_source(client, db_ready, addr):
    assert CONSENT_VERSION == "coming-soon-v1"  # the promise the page makes; pinned, not compared to itself (F5)
    r = await client.post("/api/interest", json={"email": f"  {addr} "}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 202 and r.json() == {"status": "ok"}
    assert _rows(addr.lower()) == [(addr, addr.lower(), CONSENT_VERSION, "coming-soon")]


async def test_duplicate_address_answers_the_same_and_keeps_one_row(client, db_ready, addr):
    ip = _ip()
    first = await client.post("/api/interest", json={"email": addr}, headers={"x-forwarded-for": ip})
    assert first.status_code == 202  # M9
    r = await client.post("/api/interest", json={"email": addr.upper()}, headers={"x-forwarded-for": ip})
    assert r.status_code == 202 and r.json() == {"status": "ok"}
    assert len(_rows(addr.lower())) == 1


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "nope", "a@b", "a b@c.com", "x@" + "y" * 250 + ".com",
     "a\x00b@example.com", "a\x01b@example.com", "a\x7fb@example.com", "a\u202eb@example.com"],  # F1, M3 (bidi override, written as an escape)
)
async def test_invalid_address_is_422_and_writes_nothing(client, db_ready, bad):
    before = _count()  # M10: a row count, not a lookup that could never match
    r = await client.post("/api/interest", json={"email": bad}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 422 and r.json() == {"error": "invalid_email"}
    assert _count() == before


async def test_missing_body_field_is_422(client):
    assert (await client.post("/api/interest", json={})).status_code == 422


@pytest.mark.parametrize("body", [{}, {"email": None}, {"email": 123}, {"email": ["a@b.com"]}, [], "a@b.com"])
async def test_every_malformed_body_gets_the_one_422_body(client, db_ready, body):
    r = await client.post("/api/interest", json=body, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 422 and r.json() == {"error": "invalid_email"}  # F4: never FastAPI's detail envelope


@pytest.mark.parametrize("raw", [b"", b"not json", b"{", b"\xff\xfe"])
async def test_unparseable_bodies_get_the_one_422_body(client, db_ready, raw):
    r = await client.post("/api/interest", content=raw, headers={"x-forwarded-for": _ip(), "content-type": "application/json"})
    assert r.status_code == 422 and r.json() == {"error": "invalid_email"}


async def test_composed_and_decomposed_spellings_share_one_row(client, db_ready):
    tag = uuid.uuid4().hex[:8]
    nfc = unicodedata.normalize("NFC", f"jöhn-{tag}@example.org")
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    try:
        for spelling in (nfc, nfd):
            assert (await client.post("/api/interest", json={"email": spelling}, headers={"x-forwarded-for": _ip()})).status_code == 202
        assert len(_rows(unicodedata.normalize("NFKC", nfc).lower())) == 1  # M2
    finally:
        with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM interest_signup WHERE email_normalised LIKE %s", (f"%-{tag}@example.org",))


async def test_sixth_request_in_a_minute_from_one_client_is_429(client, db_ready):
    ip = _ip()
    for i in range(5):
        r = await client.post("/api/interest", json={"email": _probe_email()}, headers={"x-forwarded-for": ip})
        assert r.status_code == 202, i
    r = await client.post("/api/interest", json={"email": _probe_email()}, headers={"x-forwarded-for": ip})
    assert r.status_code == 429 and r.json() == {"error": "rate_limited"}


async def test_rightmost_forwarded_hop_keys_the_ip_limit(client, db_ready):
    """F2: the edge appends the peer it accepted, so the rightmost hop is the client; earlier hops are caller text."""
    edge_saw = _ip()
    for i in range(5):
        r = await client.post("/api/interest", json={"email": _probe_email()}, headers={"x-forwarded-for": f"{_ip()}, {edge_saw}"})
        assert r.status_code == 202, i  # a different spoofed first hop every time — must not reset the count
    r = await client.post("/api/interest", json={"email": _probe_email()}, headers={"x-forwarded-for": f"{_ip()}, {edge_saw}"})
    assert r.status_code == 429 and r.json() == {"error": "rate_limited"}


async def test_without_a_forwarded_header_the_peer_address_is_used(client, db_ready):
    for i in range(5):
        assert (await client.post("/api/interest", json={"email": _probe_email()})).status_code == 202, i
    assert (await client.post("/api/interest", json={"email": _probe_email()})).status_code == 429  # F8: fallback path runs


async def test_fourth_attempt_for_one_address_in_a_day_is_429(client, db_ready, addr):
    for i in range(3):
        assert (await client.post("/api/interest", json={"email": addr}, headers={"x-forwarded-for": _ip()})).status_code == 202, i
    r = await client.post("/api/interest", json={"email": addr}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 429


def test_limits_are_the_spec_values():
    # ip_day is not exercised end-to-end (the 5/min limit sits in front of it) — hit()'s window semantics are tested
    # directly below and the values are pinned here (11c fix round 1 ruling).
    assert LIMITS == {"ip_minute": (5, 60), "ip_day": (30, 86_400), "email_day": (3, 86_400)}


async def test_body_over_the_cap_is_413_and_writes_nothing(client, db_ready):
    before = _count()
    r = await client.post("/api/interest", json={"email": "a" * 5000 + "@example.org"}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 413 and r.json() == {"error": "too_large"}  # F9
    assert _count() == before


async def test_unreachable_redis_fails_closed_with_503(client, db_ready, monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")  # F7: a closed port, not a mock
    before = _count()
    r = await client.post("/api/interest", json={"email": _probe_email()}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 503 and r.json() == {"error": "unavailable"}
    assert _count() == before


async def test_unreachable_database_fails_closed_with_503(client, db_ready, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql://x:x@127.0.0.1:1/x")
    r = await client.post("/api/interest", json={"email": _probe_email()}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 503 and r.json() == {"error": "unavailable"}


async def test_store_failures_are_logged_by_type_only(client, db_ready, caplog, monkeypatch):
    """F3 at the endpoint: whatever a driver embeds in its message, our warning carries the exception type only."""
    import app.api.interest as interest_module

    secret = f"victim-{uuid.uuid4().hex[:8]}@example.org"

    class ExplodingEngine:
        def begin(self):
            raise RuntimeError(f"driver message embedding {secret}")

    monkeypatch.setattr(interest_module, "get_engine", lambda _url: ExplodingEngine())
    caplog.set_level(logging.WARNING, logger="app.api.interest")
    r = await client.post("/api/interest", json={"email": secret}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 503 and r.json() == {"error": "unavailable"}
    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text


async def test_hit_counts_within_a_window_and_denies_past_the_limit():
    # An async test on pytest's own loop (asyncio auto mode): the pooled client is then disposed by the
    # autouse `_dispose_pools` fixture. A private `asyncio.run()` loop leaked the connection and its
    # GC-time ResourceWarning failed under `-W error` (11c, 2026-09-06).
    redis_ = get_redis(settings.redis_url)
    subject = uuid.uuid4().hex
    assert [await hit(redis_, "unit", subject, 2, 60) for _ in range(3)] == [True, True, False]


async def test_hit_sets_a_ttl_no_longer_than_the_window():
    redis_ = get_redis(settings.redis_url)
    subject = uuid.uuid4().hex
    assert await hit(redis_, "unit", subject, 2, 60) is True
    ttl = await redis_.ttl(bucket_key("unit", subject, 60))
    assert 0 < ttl <= 60  # F6: the key cannot outlive its window


def test_bucket_key_rolls_over_with_the_window_and_hides_the_subject():
    assert bucket_key("unit", "s", 60, now=0) == bucket_key("unit", "s", 60, now=59)
    assert bucket_key("unit", "s", 60, now=0) != bucket_key("unit", "s", 60, now=60)
    assert "victim@example.org" not in bucket_key("email_day", "victim@example.org", 86_400, now=0)


@pytest.fixture(autouse=True, scope="module")
def _cleanup_rate_limit_probe_rows():
    yield
    with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM interest_signup WHERE email_normalised LIKE %s", (f"rl-{RUN}-%",))
