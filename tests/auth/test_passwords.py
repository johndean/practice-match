import time

import httpx
import pytest

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


def test_pwned_check_uses_k_anonymity_and_never_sends_the_password():
    seen = {}
    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, text="1E4C9B93F3F0682250B6CF8331B7EE68FD8:3\n0018A45C4D1DEF81644B54AB7F969B88D65:1\n")
    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert P.is_pwned("password", http=http) is True             # sha1 5BAA6 1E4C9B93F3F0682250B6CF8331B7EE68FD8
    assert seen["path"] == "/range/5BAA6"


def test_pwned_check_falls_back_to_bundled_list_on_error(monkeypatch):
    def boom(req): raise httpx.ConnectError("down", request=req)
    http = httpx.Client(transport=httpx.MockTransport(boom))
    assert P.is_pwned("password", http=http) is True              # in top100k
    assert P.is_pwned("orbit-lantern-quiet-42", http=http) is False


def test_argon2id_parameters_hash_verify_rehash_and_cost():
    h = P.hash_password("orbit-lantern-quiet-42")
    assert h.startswith("$argon2id$v=19$m=65536,t=3,p=1$")
    assert P.verify("orbit-lantern-quiet-42", h) and not P.verify("nope", h)
    assert P.needs_rehash("$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$AAAAAAAAAAA") is True
    t0 = time.perf_counter(); P.verify("orbit-lantern-quiet-42", h); assert (time.perf_counter() - t0) < 0.25
    assert P.verify("anything", P.DUMMY_HASH) is False


async def test_async_helpers_run_off_the_event_loop():
    h = await P.hash_async("orbit-lantern-quiet-42")
    assert await P.verify_async("orbit-lantern-quiet-42", h) is True


# Coverage-only, per John's 100 %-coverage ruling (2026-09-06) — not in the brief's Step 1.
def test_needs_rehash_true_for_a_hash_argon2_cannot_parse_at_all():
    assert P.needs_rehash("not-an-argon2-hash-at-all") is True
