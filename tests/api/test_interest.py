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
     "a\x00b@example.com", "a\x01b@example.com", "a\x7fb@example.com", "a\u202eb@example.com",
     "a\u200bb@example.com"],  # F1, M3 (bidi override), N10 (zero-width space) \u2014 written as escapes
)
async def test_invalid_address_is_422_and_writes_nothing(client, db_ready, bad):
    before = _count()  # M10: a row count, not a lookup that could never match
    try:
        r = await client.post("/api/interest", json={"email": bad}, headers={"x-forwarded-for": _ip()})
        assert r.status_code == 422 and r.json() == {"error": "invalid_email"}
        assert _count() == before
    finally:
        # Postgres cannot store NUL in text, and psycopg2 refuses to bind it — nothing to clean (FR3 ruling)
        if "\x00" not in bad:
            with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM interest_signup WHERE email = %s", (bad.strip(),))


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
        with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM interest_signup WHERE email_normalised LIKE %s", (f"%-{tag}@example.org",))
            assert cur.fetchone()[0] == 1  # M2/N2: the two spellings produced ONE row, whatever key they normalised to
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


async def test_edge_first_hop_keys_the_ip_limit(client, db_ready):
    """F2 as Railway actually behaves (live probe 2026-09-06): the edge writes the client it accepted FIRST and
    leaves the caller's own X-Forwarded-For values after it — so only the first hop may key a limit."""
    edge_saw = _ip()
    for i in range(5):
        r = await client.post("/api/interest", json={"email": _probe_email()}, headers={"x-forwarded-for": f"{edge_saw}, {_ip()}"})
        assert r.status_code == 202, i  # a different caller-supplied trailing hop every time must not reset the count
    r = await client.post("/api/interest", json={"email": _probe_email()}, headers={"x-forwarded-for": f"{edge_saw}, {_ip()}"})
    assert r.status_code == 429 and r.json() == {"error": "rate_limited"}


async def test_without_a_forwarded_header_the_peer_address_is_used(dist, db_ready):
    """F8/N1: the fallback path runs and is keyed on the PEER — a fresh peer per run, because the transport's
    default peer is a constant and the shared dev Redis would otherwise poison reruns (30/day, 5/min)."""
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    async with AsyncClient(transport=ASGITransport(app=create_app(dist=dist), client=(_ip(), 40000)), base_url="http://test") as c:
        for i in range(5):
            assert (await c.post("/api/interest", json={"email": _probe_email()})).status_code == 202, i
        assert (await c.post("/api/interest", json={"email": _probe_email()})).status_code == 429
    async with AsyncClient(transport=ASGITransport(app=create_app(dist=dist), client=(_ip(), 40000)), base_url="http://test") as other:
        assert (await other.post("/api/interest", json={"email": _probe_email()})).status_code == 202  # a different peer is a different bucket


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


@pytest.mark.parametrize("size, status", [(4096, 422), (4097, 413)])
async def test_body_cap_boundary(client, db_ready, size, status):
    """O3: exactly MAX_BODY_BYTES is accepted (and then rejected as an invalid address), one more byte is 413."""
    body = b'{"email":"' + b"a" * (size - len(b'{"email":""}')) + b'"}'
    assert len(body) == size
    r = await client.post("/api/interest", content=body, headers={"x-forwarded-for": _ip(), "content-type": "application/json"})
    assert r.status_code == status


async def test_chunked_body_over_the_cap_is_413(client, db_ready):
    async def body():  # no Content-Length: httpx sends Transfer-Encoding: chunked (N3)
        for _ in range(6):
            yield b'{"email":"' + b"a" * 1000
    r = await client.post("/api/interest", content=body(), headers={"x-forwarded-for": _ip(), "content-type": "application/json"})
    assert r.status_code == 413 and r.json() == {"error": "too_large"}


async def test_oversized_chunked_body_is_not_buffered(dist):
    """N3/O4: the cap trips while streaming — the app stops pulling chunks long before a 100 KiB body ends."""
    from app.main import create_app

    app = create_app(dist=dist)
    pulled = 0

    async def receive():
        nonlocal pulled
        pulled += 1
        return {"type": "http.request", "body": b"a" * 1024, "more_body": pulled < 100}

    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "http_version": "1.1", "method": "POST", "scheme": "http", "path": "/api/interest", "raw_path": b"/api/interest",
             "query_string": b"", "root_path": "", "server": ("test", 80), "client": ("10.9.9.8", 1),
             "headers": [(b"host", b"test"), (b"content-type", b"application/json")]}
    await app(scope, receive, send)
    assert sent[0]["status"] == 413
    assert pulled < 20, pulled  # 4 KiB cap: a handful of 1 KiB chunks, never all 100


async def test_client_disconnect_mid_body_is_answered_without_a_traceback(dist, caplog):
    """O2: an aborted upload is not an error — it is answered by this endpoint's contract, not a 500."""
    import logging

    from app.main import create_app

    app = create_app(dist=dist)
    calls = 0

    async def receive():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "http.request", "body": b'{"email":"', "more_body": True}
        return {"type": "http.disconnect"}

    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "http_version": "1.1", "method": "POST", "scheme": "http", "path": "/api/interest", "raw_path": b"/api/interest",
             "query_string": b"", "root_path": "", "server": ("test", 80), "client": ("10.9.9.9", 1),
             "headers": [(b"host", b"test"), (b"content-type", b"application/json"), (b"content-length", b"64")]}
    caplog.set_level(logging.ERROR)
    await app(scope, receive, send)
    assert sent[0]["type"] == "http.response.start" and sent[0]["status"] == 422
    assert "Traceback" not in caplog.text


@pytest.mark.parametrize("value, expected", [("19", 19), ("0", 0), ("\xb2", None), ("abc", None), ("-5", None), ("1 9", None)])
def test_declared_length_accepts_only_decimal_digits(value, expected):
    from starlette.requests import Request

    from app.api.interest import declared_length

    scope = {"type": "http", "method": "POST", "path": "/api/interest", "query_string": b"",
             "headers": [(b"content-length", value.encode("latin-1"))]}
    assert declared_length(Request(scope)) == expected  # N4: "²".isdigit() is True but int("²") raises


@pytest.mark.parametrize("lines, expected", [
    ([b"1.2.3.4, 5.6.7.8"], "1.2.3.4"),               # the edge's hop first, the caller's after
    ([b"1.2.3.4"], "1.2.3.4"),
    ([b"1.2.3.4:51234"], "1.2.3.4"),                   # OBS-3: a port never makes a fresh bucket
    ([b"[2001:db8::1]:4711"], "2001:db8::1"),
    ([b"2001:db8::1"], "2001:db8::1"),                 # bare IPv6 is not a host:port pair
    ([b", 5.6.7.8"], "9.9.9.9"),                       # OBS-1: an empty first field means the peer, exactly as uvicorn does
    ([b"   "], "9.9.9.9"), ([b""], "9.9.9.9"), ([], "9.9.9.9"),
    ([b"203.0.113.7", b"evil-spoof"], "203.0.113.7"),  # repeated lines: the first line is the edge's
    ([b"", b"5.6.7.8"], "9.9.9.9"),                    # an empty first line is still the first field after the join → peer
])
def test_client_ip_is_the_first_field_of_the_joined_header_like_uvicorn(lines, expected):
    from starlette.requests import Request

    from app.api.interest import client_ip

    scope = {"type": "http", "method": "POST", "path": "/api/interest", "query_string": b"", "client": ("9.9.9.9", 1),
             "headers": [(b"x-forwarded-for", line) for line in lines]}
    assert client_ip(Request(scope)) == expected


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
    assert "builtins.RuntimeError" in caplog.text  # N12
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
