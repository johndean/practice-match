import uuid

import psycopg2
import pytest

from app.api.interest import CONSENT_VERSION
from app.config import settings


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
    r = await client.post("/api/interest", json={"email": f"  {addr} "}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 202 and r.json() == {"status": "ok"}
    assert _rows(addr.lower()) == [(addr, addr.lower(), CONSENT_VERSION, "coming-soon")]


async def test_duplicate_address_answers_the_same_and_keeps_one_row(client, db_ready, addr):
    ip = _ip()
    await client.post("/api/interest", json={"email": addr}, headers={"x-forwarded-for": ip})
    r = await client.post("/api/interest", json={"email": addr.upper()}, headers={"x-forwarded-for": ip})
    assert r.status_code == 202 and r.json() == {"status": "ok"}
    assert len(_rows(addr.lower())) == 1


@pytest.mark.parametrize("bad", ["", "   ", "nope", "a@b", "a b@c.com", "x@" + "y" * 250 + ".com"])
async def test_invalid_address_is_422_and_writes_nothing(client, db_ready, bad):
    r = await client.post("/api/interest", json={"email": bad}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 422 and r.json() == {"error": "invalid_email"}
    assert _rows(bad.strip().lower()) == []


async def test_missing_body_field_is_422(client):
    assert (await client.post("/api/interest", json={})).status_code == 422


async def test_sixth_request_in_a_minute_from_one_client_is_429(client, db_ready):
    ip = _ip()
    for i in range(5):
        r = await client.post("/api/interest", json={"email": f"rl-{uuid.uuid4().hex[:8]}@example.org"}, headers={"x-forwarded-for": ip})
        assert r.status_code == 202, i
    r = await client.post("/api/interest", json={"email": f"rl-{uuid.uuid4().hex[:8]}@example.org"}, headers={"x-forwarded-for": ip})
    assert r.status_code == 429 and r.json() == {"error": "rate_limited"}


async def test_fourth_attempt_for_one_address_in_a_day_is_429(client, db_ready, addr):
    for i in range(3):
        assert (await client.post("/api/interest", json={"email": addr}, headers={"x-forwarded-for": _ip()})).status_code == 202, i
    r = await client.post("/api/interest", json={"email": addr}, headers={"x-forwarded-for": _ip()})
    assert r.status_code == 429


async def test_hit_counts_within_a_window_and_denies_past_the_limit():
    # An async test on pytest's own loop (asyncio auto mode): the pooled client is then disposed by the
    # autouse `_dispose_pools` fixture. A private `asyncio.run()` loop leaked the connection and its
    # GC-time ResourceWarning failed under `-W error` (11c, 2026-09-06).
    from app.db import get_redis
    from app.ratelimit import hit

    client = get_redis(settings.redis_url)
    subject = uuid.uuid4().hex
    assert [await hit(client, "unit", subject, 2, 60) for _ in range(3)] == [True, True, False]


@pytest.fixture(autouse=True, scope="module")
def _cleanup_rate_limit_probe_rows():
    yield
    with psycopg2.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM interest_signup WHERE email_normalised LIKE %s", ("rl-%",))
