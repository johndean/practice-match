import hashlib
import logging
import threading
import time
from pathlib import Path

import httpx
import pytest
from argon2 import extract_parameters

from app.auth import passwords as P


def test_policy_lengths_and_strength():
    with pytest.raises(P.PasswordPolicyError, match="12"):
        P.validate("short-one", privileged=False)
    with pytest.raises(P.PasswordPolicyError, match="14"):
        P.validate("twelve-chars!", privileged=True)
    with pytest.raises(P.PasswordPolicyError, match="256"):
        P.validate("x" * 257, privileged=False)
    with pytest.raises(P.PasswordPolicyError, match="stronger"):
        P.validate("password12345", privileged=False)      # zxcvbn score < 3
    P.validate("orbit-lantern-quiet-42", privileged=True)  # ok


def test_long_passphrases_are_scored_not_crashed():
    """C1, fix round 1: zxcvbn's own default cap is 72 characters and it raises a bare
    `ValueError` above it, so every password in the 73-256 window the policy explicitly
    allows blew up instead of being scored. A strong passphrase must pass and a weak one
    must raise `PasswordPolicyError` (never a bare ValueError) at each length."""
    for n in (73, 128, 256):
        strong = ("orbit-lantern-quiet-42-" * 40)[:n]
        assert len(strong) == n
        P.validate(strong, privileged=True)                        # scored, not rejected
        weak = "a" * n
        with pytest.raises(P.PasswordPolicyError, match="stronger"):
            P.validate(weak, privileged=False)


def test_pwned_check_uses_k_anonymity_and_never_sends_the_password():
    seen = {}
    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, text="1E4C9B93F3F0682250B6CF8331B7EE68FD8:3\n0018A45C4D1DEF81644B54AB7F969B88D65:1\n")
    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert P.is_pwned("password", http=http) is True             # sha1 5BAA6 1E4C9B93F3F0682250B6CF8331B7EE68FD8
    assert seen["path"] == "/range/5BAA6"


def test_is_pwned_reuses_one_shared_http_client(monkeypatch):
    """I2, fix round 1: `is_pwned` built (and never closed) a fresh httpx.Client — one
    connection pool and one TLS handshake per signup/reset/change. One lazily created
    module-level client is shared instead, behind the `_make_client` factory seam that
    mirrors app/cache.py's."""
    made: list[httpx.Client] = []

    def _fake_client() -> httpx.Client:
        c = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text="")))
        made.append(c)
        return c

    monkeypatch.setattr(P, "_shared_client", None)
    monkeypatch.setattr(P, "_make_client", _fake_client)
    assert P.is_pwned("orbit-lantern-quiet-42") is False            # no `http=`: the shared client
    assert P.is_pwned("correct-horse-battery-staple") is False
    assert len(made) == 1
    assert P._client() is made[0]


def test_the_shared_client_carries_the_two_second_hibp_timeout():
    """The other half of I2: the client the factory actually builds (the one every
    non-test caller gets) still carries spec §3's 2 s budget — nothing may make a signup
    wait longer than that on the breach screen."""
    client = P._make_client()
    try:
        assert client.timeout == httpx.Timeout(2.0)
    finally:
        client.close()


def test_pwned_check_falls_back_to_bundled_list_on_error(monkeypatch):
    def boom(req): raise httpx.ConnectError("down", request=req)
    http = httpx.Client(transport=httpx.MockTransport(boom))
    assert P.is_pwned("password", http=http) is True              # in top100k
    assert P.is_pwned("orbit-lantern-quiet-42", http=http) is False


def test_pwned_check_warns_and_uses_the_bundled_list_when_hibp_is_disabled(monkeypatch, caplog):
    """I8, fix round 1: decision A4 is "on error OR when disabled the bundled list is
    the screen and a warning is logged". The disabled leg logged nothing, so an
    HIBP_ENABLED=false left over from an incident silently downgraded an ~850 M-entry
    screen to 100 k with nothing in the logs to say so."""
    from app.config import settings

    never = httpx.Client(transport=httpx.MockTransport(lambda req: pytest.fail("HIBP must not be called when disabled")))
    monkeypatch.setattr(settings, "hibp_enabled", False)
    with caplog.at_level(logging.WARNING, logger="app.auth.passwords"):
        assert P.is_pwned("password", http=never) is True               # answered from the bundled list
        assert P.is_pwned("orbit-lantern-quiet-42", http=never) is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2                                           # one per screened password
    assert all("password" not in r.getMessage() for r in warnings)      # never the password itself


def test_argon2id_parameters_hash_verify_rehash_and_cost():
    h = P.hash_password("orbit-lantern-quiet-42")
    assert h.startswith("$argon2id$v=19$m=65536,t=3,p=1$")
    assert P.verify("orbit-lantern-quiet-42", h) and not P.verify("nope", h)
    assert P.needs_rehash("$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$AAAAAAAAAAA") is True
    t0 = time.perf_counter(); P.verify("orbit-lantern-quiet-42", h); assert (time.perf_counter() - t0) < 0.25
    assert P.verify("anything", P.DUMMY_HASH) is False
    # M6, fix round 1: S2's equal-work rule needs DUMMY_HASH to cost exactly what a real
    # stored hash costs, otherwise the sign-in timing for an unknown email is a giveaway.
    # Unasserted, a t=1/m=8 dummy passed the whole suite.
    assert extract_parameters(P.DUMMY_HASH) == extract_parameters(P.hash_password("x" * 20))


def test_verify_is_false_for_a_stored_hash_argon2_cannot_decode():
    """I1, fix round 1: a hash with a parseable prefix but an undecodable body raises
    argon2's parent `VerificationError`, not `VerifyMismatchError`/`InvalidHashError`.
    Uncaught, one truncated `account.password_hash` turns that account's sign-in into a
    500 while every other account gets the uniform 401 — an outage and an enumeration
    oracle. `verify` must answer False for it, like any other non-match."""
    h = P.hash_password("orbit-lantern-quiet-42")
    assert P.verify("orbit-lantern-quiet-42", h[:-5]) is False       # body truncated
    salt, digest = h.rsplit("$", 1)
    assert P.verify("orbit-lantern-quiet-42", f"{salt}${digest[:-4]}") is False


async def test_async_helpers_run_off_the_event_loop(monkeypatch):
    """I7, fix round 1: the brief's version only awaited the helpers, so replacing them
    with `async def f(...): return hash_password(...)` still passed and the ~110 ms
    Argon2id (and the up-to-2 s HIBP call, I3) could silently move back onto the event
    loop. Each helper's synchronous body must run on a DIFFERENT thread than the loop."""
    h = await P.hash_async("orbit-lantern-quiet-42")
    assert await P.verify_async("orbit-lantern-quiet-42", h) is True

    loop_thread = threading.get_ident()
    ran_on: dict[str, int] = {}

    def _spy(name: str, result: object):
        def f(*args: object, **kwargs: object) -> object:
            ran_on[name] = threading.get_ident()
            return result
        return f

    monkeypatch.setattr(P, "hash_password", _spy("hash_password", h))
    monkeypatch.setattr(P, "verify", _spy("verify", True))
    monkeypatch.setattr(P, "is_pwned", _spy("is_pwned", False))
    assert await P.hash_async("orbit-lantern-quiet-42") == h
    assert await P.verify_async("orbit-lantern-quiet-42", h) is True
    assert await P.is_pwned_async("orbit-lantern-quiet-42") is False
    assert set(ran_on) == {"hash_password", "verify", "is_pwned"}
    assert loop_thread not in ran_on.values()


# M11, fix round 1 — provenance of the vendored offline list. Verified 2026-09-06 against
# SecLists commit 1a7bb9127eca9e6ff2fc0301c597fe6e16a0cb56 (see app/auth/data/PROVENANCE.md);
# pinned here so a silent swap of a security list fails the suite instead of passing quietly.
LIST_SHA256 = "c2e5696882c603b76bb67a47ee970897e5a76fc4c3f5547abe3d0ca340c576e0"
LIST_LINES = 99840          # lines in the file as vendored (one of them blank)
LIST_ENTRIES = 99839        # distinct non-blank passwords the screen actually loads


def test_offline_list_matches_its_recorded_provenance():
    data = Path(P.__file__).parent / "data" / "top100k.txt"
    raw = data.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == LIST_SHA256
    assert len(raw.decode("utf-8").splitlines()) == LIST_LINES        # M2: decodes as UTF-8, nothing dropped
    assert (data.parent / "PROVENANCE.md").is_file()


def test_offline_list_loads_every_entry_and_no_blanks():
    """M1/M2, fix round 1: the vendored file has one blank line, so the loaded screen
    contained the empty string; `errors="ignore"` would have silently corrupted the 79
    non-ASCII entries had the file ever been replaced with a non-UTF-8 copy."""
    offline = P._offline()
    assert "" not in offline
    assert len(offline) == LIST_ENTRIES


# Coverage-only, per John's 100 %-coverage ruling (2026-09-06) — not in the brief's Step 1.
def test_needs_rehash_true_for_a_hash_argon2_cannot_parse_at_all():
    assert P.needs_rehash("not-an-argon2-hash-at-all") is True
