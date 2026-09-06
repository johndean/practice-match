"""Password policy and hashing (spec §3). Argon2id 64 MiB / t=3 / p=1; zxcvbn ≥ 3; HIBP k-anonymity with an offline fallback."""
from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from pathlib import Path

import anyio
import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from zxcvbn import zxcvbn

from app.config import settings

log = logging.getLogger(__name__)
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16)
MIN_LEN, MIN_LEN_PRIVILEGED, MAX_LEN, MIN_SCORE = 12, 14, 256, 3
HIBP_URL = "https://api.pwnedpasswords.com/range/"
DUMMY_HASH = _ph.hash("dummy-work-factor-only-never-a-real-password-7f3a")


class PasswordPolicyError(ValueError):
    pass


def validate(pw: str, *, privileged: bool) -> None:
    floor = MIN_LEN_PRIVILEGED if privileged else MIN_LEN
    if len(pw) < floor:
        raise PasswordPolicyError(f"Use at least {floor} characters.")
    if len(pw) > MAX_LEN:
        raise PasswordPolicyError(f"Use at most {MAX_LEN} characters.")
    if zxcvbn(pw)["score"] < MIN_SCORE:
        raise PasswordPolicyError("Choose a stronger password — longer phrases beat symbols.")


@lru_cache(maxsize=1)
def _offline() -> frozenset[str]:
    return frozenset(l.strip() for l in (Path(__file__).parent / "data" / "top100k.txt").read_text(encoding="utf-8", errors="ignore").splitlines())


def is_pwned(pw: str, http: httpx.Client | None = None) -> bool:
    """k-anonymity: only the first 5 hex chars of SHA-1 leave the process. Falls back to the bundled list on any error."""
    digest = hashlib.sha1(pw.encode()).hexdigest().upper()
    if settings.hibp_enabled:
        try:
            client = http or httpx.Client(timeout=2.0)
            r = client.get(HIBP_URL + digest[:5]); r.raise_for_status()
            return any(line.split(":")[0] == digest[5:] for line in r.text.splitlines())
        except Exception as e:  # noqa: BLE001 — degrade to the offline list
            log.warning("hibp unavailable (%s); using offline list", type(e).__name__)
    return pw in _offline()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, InvalidHashError):
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
