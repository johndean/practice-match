"""Password policy and hashing (spec §3). Argon2id 64 MiB / t=3 / p=1; zxcvbn ≥ 3; HIBP k-anonymity with an offline fallback."""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from functools import lru_cache
from pathlib import Path

import anyio
import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from zxcvbn import zxcvbn

from app.config import settings

log = logging.getLogger(__name__)
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16)
MIN_LEN, MIN_LEN_PRIVILEGED, MAX_LEN, MIN_SCORE = 12, 14, 256, 3
SCORE_LEN = 72  # zxcvbn's own default cap; its matching is quadratic, and the caller picks the length
HIBP_URL = "https://api.pwnedpasswords.com/range/"
DUMMY_HASH = _ph.hash("dummy-work-factor-only-never-a-real-password-7f3a")


class PasswordPolicyError(ValueError):
    pass


def user_inputs_for(email: str, name: str | None = None) -> list[str]:
    """zxcvbn's `user_inputs`: fed to `validate` so a password built from the MEMBER'S OWN
    identifiers is scored like any other dictionary word instead of like a random string (John's
    ruling, 2026-09-08 — I11: "Password strength validation should also penalize passwords
    derived from the member's own email address or name").

    Pure and deterministic; every value lower-cased and de-duplicated (first occurrence wins) —
    zxcvbn's own `user_inputs` handling lower-cases its list before matching (see
    `zxcvbn/__init__.py`), so folding case here just keeps this function's OWN order
    inspectable rather than leaving it to however zxcvbn happens to fold it.

    In order: the email as given, its lower-cased ("normalised") form, the local part, the local
    part split on the separators an address commonly encodes structure with (`.`, `_`, `-`, `+`
    — so "buyer+demo@x" also yields "buyer" and "demo"), each label of the domain (so a
    sub-domain's every label is caught, not just the registrable domain), and — only when the
    caller knows the member's name (a reset or an accept-invite reads it off the account row) —
    every whitespace-separated token of it that is three characters or longer, so a two-letter
    token (initials, "Al") does not become a blacklisted fragment for every password belonging to
    everybody who shares it.

    Sign-up knows only the email; `name=None` there is deliberate, not a placeholder for it."""
    local, _, domain = email.partition("@")
    candidates = [email, email.lower(), local, *re.split(r"[._+-]", local), *domain.split(".")]
    if name:
        candidates += [token for token in name.split() if len(token) >= 3]
    seen: list[str] = []
    for candidate in candidates:
        lowered = candidate.lower()
        if lowered and lowered not in seen:
            seen.append(lowered)
    return seen


def validate(pw: str, *, privileged: bool, user_inputs: list[str] | None = None) -> None:
    """Strength is scored on the first 72 characters; length up to 256 is accepted.

    `user_inputs` (I11): the member's own identifiers, from `user_inputs_for` — passed straight
    through to zxcvbn, which treats each one as a rank-1 dictionary word for THIS scoring call
    only."""
    floor = MIN_LEN_PRIVILEGED if privileged else MIN_LEN
    if len(pw) < floor:
        raise PasswordPolicyError(f"Use at least {floor} characters.")
    if len(pw) > MAX_LEN:
        raise PasswordPolicyError(f"Use at most {MAX_LEN} characters.")
    # Scored on the first SCORE_LEN characters: zxcvbn raises a bare ValueError above its
    # own 72-char cap (so the 73-MAX_LEN window used to 500), and raising that cap instead
    # would hand an unauthenticated caller 141-311 ms of quadratic CPU per request (C1).
    if zxcvbn(pw[:SCORE_LEN], user_inputs=user_inputs)["score"] < MIN_SCORE:
        raise PasswordPolicyError("Choose a stronger password — longer phrases beat symbols.")


@lru_cache(maxsize=1)
def _offline() -> frozenset[str]:
    """The bundled NCSC top-100k list (see data/PROVENANCE.md). Blank lines are skipped —
    the file has one, and the empty string is junk in a security list (M1); decode errors
    are NOT ignored, so a non-UTF-8 replacement fails loudly instead of corrupting entries
    (M2). tests/auth/test_passwords.py pins the file's SHA-256 and the loaded count."""
    text = (Path(__file__).parent / "data" / "top100k.txt").read_text(encoding="utf-8")
    return frozenset(stripped for line in text.splitlines() if (stripped := line.strip()))


_shared_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _make_client() -> httpx.Client:
    return httpx.Client(timeout=2.0)


def _client() -> httpx.Client:
    """One lazily created, process-wide HIBP client — a fresh one per call leaked a
    connection pool and paid a fresh TLS handshake on every signup/reset/change (I2).
    Built through `_make_client`, the same factory seam app/cache.py uses, so tests can
    patch it without reaching into httpx.

    Double-checked locking (NEW-2): `is_pwned_async` offloads to worker threads, so two
    concurrent first calls would otherwise each build a client and drop one unclosed. The
    lock is taken only until the client exists; every later call is the bare read."""
    global _shared_client
    if _shared_client is None:
        with _client_lock:
            if _shared_client is None:
                _shared_client = _make_client()
    return _shared_client


def _matches(body: str, suffix: str) -> bool:
    """Each line of a range response is `SUFFIX:COUNT`. A line that is not raises
    ValueError, which `is_pwned` treats as an API failure: reading a malformed body as
    "no match" would fail OPEN and let a breached password through (M3).

    EVERY line is parsed before answering (O2): returning on the first match made that
    strictness positional — a mangled line after the match was never even looked at, so
    whether a truncated body was noticed depended on where the damage happened to fall."""
    found = False
    for line in body.splitlines():
        candidate, _count = line.split(":")
        if candidate == suffix:
            found = True
    return found


def _degrade(reason: str) -> None:
    """Decision A4: on error OR when disabled, the bundled list is the screen and a
    warning says so. `reason` is a module.Type or a setting name — never any part of the
    password (I8)."""
    log.warning("hibp screen unavailable (%s); using the bundled offline list", reason)


def is_pwned(pw: str, http: httpx.Client | None = None) -> bool:
    """k-anonymity: only the first 5 hex chars of SHA-1 leave the process. Falls back to the bundled list on any error."""
    digest = hashlib.sha1(pw.encode()).hexdigest().upper()
    if settings.hibp_enabled:
        try:
            client = http if http is not None else _client()
            r = client.get(HIBP_URL + digest[:5]); r.raise_for_status()
            return _matches(r.text, digest[5:])
        # The concrete failure modes of an unreachable or misbehaving HIBP: httpx wraps
        # every transport, timeout and status failure in HTTPError, and ValueError covers
        # a body we cannot parse. A bug in our own code is not an "API failure" under A4
        # and must surface rather than silently downgrade the screen (M3, round 2).
        except (httpx.HTTPError, ValueError) as e:
            _degrade(f"{type(e).__module__}.{type(e).__qualname__}")
    else:
        _degrade("settings.hibp_enabled=False")
    return pw in _offline()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    # VerifyMismatchError subclasses VerificationError, which also covers a stored hash
    # with a parseable prefix but an undecodable body ("Decoding failed") — I1.
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _ph.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


async def hash_async(pw: str) -> str:
    return await anyio.to_thread.run_sync(hash_password, pw)


async def verify_async(pw: str, hashed: str) -> bool:
    return await anyio.to_thread.run_sync(verify, pw, hashed)


async def is_pwned_async(pw: str, *, http: httpx.Client | None = None) -> bool:
    """`is_pwned` is a blocking network call with a 2 s timeout; async callers must not
    run it on the event loop (I3) — every other request would queue behind a degraded
    HIBP for the full timeout."""
    return await anyio.to_thread.run_sync(is_pwned, pw, http)
