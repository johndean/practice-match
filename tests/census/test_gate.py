"""Task A9: the 60-second layer gate (spec §11; Global Constraints "Licensing gates production" —
a layer whose dataset leaves `license_status = 'cleared'` disappears within one minute, and
red-team C5's `market:gate:v` counter keys every cached market payload away in the same minute).

The clock is CONTROLLABLE rather than slept through. `fakeredis` computes key expiry from
`fakeredis._basefakesocket.time.time()`, refreshed once per command, so replacing that module's
`time` NAME (not the stdlib's `time.time`, which pytest, logging and everything else in the
process also read) with a stub advances the clock for this Redis and nothing else. That is what
lets the boundary be asserted at 59 s and 61 s in microseconds instead of a two-minute test.
"""
import time as real_time

import fakeredis
import pytest
from fakeredis import _basefakesocket

from app.census import gate


class Clock:
    """A stand-in for the `time` MODULE as `fakeredis._basefakesocket` uses it: one `time()`
    call, whose value this test moves by hand."""

    def __init__(self) -> None:
        self.now = real_time.time()

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(_basefakesocket, "time", c)
    return c


def test_gate_reads_registry_and_caches_for_60s(conn):
    r = fakeredis.FakeRedis()
    assert gate.layer_enabled(r, lambda: conn, "acs5") is True
    assert gate.layer_enabled(r, lambda: conn, "pet_ownership") is False
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='blocked' WHERE dataset_key='acs5'")
    assert gate.layer_enabled(r, lambda: conn, "acs5") is True          # cached
    assert 0 < r.ttl("gate:acs5") <= 60
    before = gate.version(r)
    gate.invalidate(r, "acs5")
    assert gate.layer_enabled(r, lambda: conn, "acs5") is False         # fresh read
    assert gate.version(r) == before + 1                                # cached payloads are keyed away


def test_the_cached_answer_stands_at_59_seconds_and_is_re_read_at_61(conn, clock):
    """The boundary itself, both sides of it. Sixty seconds is the number the spec commits to
    ("the layer is hidden within 60 s of a status change"), so the test that a licence change is
    NOT seen early is as load-bearing as the test that it is seen in time — a shorter TTL would
    silently cost a database round trip on every layer of every request."""
    r = fakeredis.FakeRedis()
    assert gate.layer_enabled(r, lambda: conn, "acs5") is True
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='blocked' WHERE dataset_key='acs5'")

    clock.advance(59)
    assert gate.layer_enabled(r, lambda: conn, "acs5") is True, "59 s: still the cached answer"

    clock.advance(2)                                                    # 61 s since the cache was written
    assert gate.layer_enabled(r, lambda: conn, "acs5") is False, "61 s: re-read from the registry"


def test_a_cached_refusal_is_served_from_the_cache_too(conn, clock):
    """The `0` half of the cache. A blocked dataset that is cleared by an admin must ALSO wait for
    the gate to be invalidated (or for the TTL) before its layer appears — otherwise the cache is
    write-through in one direction only, and `invalidate` would be decorative on the path that
    turns a layer back ON."""
    r = fakeredis.FakeRedis()
    assert gate.layer_enabled(r, lambda: conn, "pet_ownership") is False
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key='pet_ownership'")
    assert gate.layer_enabled(r, lambda: conn, "pet_ownership") is False, "cached refusal"
    clock.advance(61)
    assert gate.layer_enabled(r, lambda: conn, "pet_ownership") is True


def test_an_unregistered_dataset_key_is_refused_and_the_refusal_is_cached(conn):
    """A key with no `dataset_registry` row is not "not yet decided" — it is a layer nobody has
    cleared, so the gate says no. Fails CLOSED, like every other licence decision in this
    programme."""
    r = fakeredis.FakeRedis()
    assert gate.layer_enabled(r, lambda: conn, "no_such_dataset") is False
    assert r.get("gate:no_such_dataset") == b"0"


def test_the_gate_never_closes_the_connection_it_was_handed(conn):
    """`conn_factory` is a factory rather than a connection so that a cache HIT opens nothing at
    all; the connection it returns belongs to the CALLER, and the gate must leave it open for the
    rest of the request (A-C7 (7)'s rule read from the other end — whoever opens it closes it)."""
    r = fakeredis.FakeRedis()
    opened = []

    def factory():
        opened.append(1)
        return conn

    assert gate.layer_enabled(r, factory, "acs5") is True
    assert conn.closed == 0
    assert gate.layer_enabled(r, factory, "acs5") is True
    assert opened == [1], "the cached answer opened no connection"


def test_the_gate_version_starts_at_zero_and_counts_every_decision(conn):
    """Red-team C5: the counter is what every cached panel/community payload is keyed by, so it
    has to answer before anything has ever been invalidated."""
    r = fakeredis.FakeRedis()
    assert gate.version(r) == 0
    gate.invalidate(r, "acs5")
    gate.invalidate(r, "cbp")
    assert gate.version(r) == 2
