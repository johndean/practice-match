# app/disclosure/levels.py
"""The disclosure-level vocabulary (directive §16): explicit named permissions rather than one
giant boolean, reusing this product's own document-kind vocabulary (`migrations/031_listing_asset.sql`)
where it already has an equivalent. Pure constants and pure functions -- no I/O, no imports from
elsewhere in this plan, so this module is safe for every other one to depend on."""
from __future__ import annotations

CAPABILITIES: frozenset[str] = frozenset({"IDENTITY", "EXACT_LOCATION", "UNREDACTED_IMAGES", "FINANCIALS", "FLOOR_PLANS"})

# What `request.approved_disclosure_level`/`requested_disclosure_level` may hold (migration 096's
# own CHECK, restated here so Python and the database cannot silently drift apart -- Task 5/6's
# routes validate an incoming level against this set before it ever reaches SQL, and
# `tests/disclosure/test_levels.py` pins this exact set against both columns' CHECKs, read from
# `pg_constraint`, in both directions).
REQUESTABLE_LEVELS: frozenset[str] = CAPABILITIES | frozenset({"FULL_CONFIDENTIAL"})

_COVERAGE: dict[str, frozenset[str]] = {capability: frozenset({capability}) for capability in CAPABILITIES}
_COVERAGE["FULL_CONFIDENTIAL"] = CAPABILITIES


def covers(level: str | None) -> frozenset[str]:
    """Every capability an approved grant of `level` includes. `frozenset()` for `None` (no grant
    at all) and for anything not in `REQUESTABLE_LEVELS` -- fail closed on an unrecognised value
    rather than raising, because this is read on the hot authorization path and an unrecognised
    level (a future migration adding one Python does not know about yet) must deny, not 500."""
    return _COVERAGE.get(level or "", frozenset())


# D18: the approved wizard step 6 has no document-kind picker, so every upload today is 'other'.
# The two kinds a seller CAN already send (the API accepts them; nothing sends them yet) map to
# their own capability; anything else -- 'equipment', 'other', and any kind added later that this
# table has not been taught -- requires the broadest grant, which is the fail-closed reading of an
# undifferentiated document (directive §19).
_DOCUMENT_CAPABILITY: dict[str, str] = {"floor_plan": "FLOOR_PLANS", "financials": "FINANCIALS"}
DEFAULT_DOCUMENT_CAPABILITY = "FULL_CONFIDENTIAL"


def capability_for_document_kind(kind: str) -> str:
    return _DOCUMENT_CAPABILITY.get(kind, DEFAULT_DOCUMENT_CAPABILITY)
