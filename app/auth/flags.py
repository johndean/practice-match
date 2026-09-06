"""Reviewer hints on an application (spec §6).

A flag is **never** a decision. Nothing in `app.api.applications` or `app.api.admin_users` branches
on one: the flags are stored on the `application` row and rendered beside it so that the human
reviewing the application knows where to look. That is the whole contract, and it is why an
over-broad entry in the vendored domain list (or a clumsy `CONSOLIDATOR_KEYWORDS`) costs a reviewer
a second glance rather than costing an applicant their account.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import settings

DATA = Path(__file__).parent / "data" / "disposable_domains.txt"


@lru_cache(maxsize=1)
def _disposable() -> frozenset[str]:
    """The vendored blocklist, read once per process (see `data/PROVENANCE.md` for its source,
    pinned commit and CC0 dedication). Vendored rather than fetched at runtime for the same reason
    `passwords.top100k.txt` is: a degraded network must not silently degrade a review hint to
    nothing, without anybody noticing that the flag stopped appearing."""
    return frozenset(line.strip().lower() for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip())


def compute(fields: dict[str, Any], email: str) -> list[str]:
    """Reviewer hints only — never a decision (spec §6)."""
    flags = []
    if email.rsplit("@", 1)[-1].lower() in _disposable():
        flags.append("disposable_domain")
    # VIN Foundation-supplied and deliberately configurable per environment (`CONSOLIDATOR_KEYWORDS`,
    # default empty): the words that mark a corporate-consolidator employer are a policy judgement
    # the Foundation owns, not a constant this repository should be asserting.
    words = [w.strip().lower() for w in settings.consolidator_keywords.split(",") if w.strip()]
    employer = str(fields.get("employer", "")).lower()
    if any(word in employer for word in words):
        flags.append("employer_keyword")
    return flags
