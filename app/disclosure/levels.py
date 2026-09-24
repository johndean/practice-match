# app/disclosure/levels.py
"""The disclosure-level vocabulary (directive §16): explicit named permissions rather than one
giant boolean, reusing this product's own document-kind vocabulary (`migrations/031_listing_asset.sql`)
where it already has an equivalent. Pure constants and pure functions -- no I/O, no imports from
elsewhere in this plan, so this module is safe for every other one to depend on."""
from __future__ import annotations

from collections.abc import Sequence

CAPABILITIES: frozenset[str] = frozenset({"IDENTITY", "EXACT_LOCATION", "UNREDACTED_IMAGES", "FINANCIALS", "FLOOR_PLANS"})

# What `requested_disclosure_level` may hold -- what a BUYER may ask for (migration 096's own
# CHECK, restated here so Python and the database cannot silently drift apart -- Task 5/6's routes
# validate an incoming level against this set before it ever reaches SQL, and
# `tests/disclosure/test_levels.py` pins this exact set against that column's CHECK, read from
# `pg_constraint`, in both directions).
#
# It is deliberately NOT what a GRANT may hold. Under D-C67 (John, 2026-09-24) the seller chooses a
# SET, stored in `request.approved_capabilities` (migration 097), whose own CHECK admits exactly
# `CAPABILITIES` -- `FULL_CONFIDENTIAL` is an umbrella name a buyer may ASK for and never a
# capability a grant may STORE, because a stored umbrella would be a second spelling of a set the
# array already says plainly.
REQUESTABLE_LEVELS: frozenset[str] = CAPABILITIES | frozenset({"FULL_CONFIDENTIAL"})

_COVERAGE: dict[str, frozenset[str]] = {capability: frozenset({capability}) for capability in CAPABILITIES}
_COVERAGE["FULL_CONFIDENTIAL"] = CAPABILITIES


def covers(level: str | None) -> frozenset[str]:
    """Every capability an approved grant of `level` includes. `frozenset()` for `None` (no grant
    at all) and for anything not in `REQUESTABLE_LEVELS` -- fail closed on an unrecognised value
    rather than raising, because this is read on the hot authorization path and an unrecognised
    level (a future migration adding one Python does not know about yet) must deny, not 500."""
    return _COVERAGE.get(level or "", frozenset())


def granted(values: Sequence[str] | None) -> frozenset[str]:
    """Every capability a STORED grant actually confers (`request.approved_capabilities`, migration
    097) -- the door `covers()` is for the buyer's single requested level, one column over.

    Three inputs, three meanings, and the middle one is the whole point of D-C67's fail-closed rule:

    * `None` -- no decision at all (a PENDING row) or a refusal (a DENIED one): nothing.
    * `[]` -- a real decision that released nothing. It is NOT `None` and it must never collapse
      into "everything": the tempting bug is a falsy empty set falling through to a
      `FULL_CONFIDENTIAL` default, which would silently release the practice name, the street, the
      telephone, the exact pin, the unredacted photographs, the financial packet and the floor
      plans together. This function cannot reach that state at all -- it has no default arm.
    * anything else -- exactly the members it recognises.

    An unrecognised member confers nothing while the recognised members beside it still confer
    themselves. That is `covers()`'s own "a future migration adding one Python does not know about
    yet must deny, not 500", applied per MEMBER: denying the WHOLE set on one unknown name would
    strip a buyer's existing, correctly-granted access on the deploy that introduced the new one --
    fail-closed about the unknown thing, never about the known ones."""
    if values is None:
        return frozenset()
    return frozenset(value for value in values if value in CAPABILITIES)


# D18: the approved wizard step 6 has no document-kind picker, so every upload today is 'other'.
# The two kinds a seller CAN already send (the API accepts them; nothing sends them yet) map to
# their own capability; anything else -- 'equipment', 'other', and any kind added later that this
# table has not been taught -- requires the broadest grant, which is the fail-closed reading of an
# undifferentiated document (directive §19).
_DOCUMENT_CAPABILITY: dict[str, str] = {"floor_plan": "FLOOR_PLANS", "financials": "FINANCIALS"}
DEFAULT_DOCUMENT_CAPABILITY = "FULL_CONFIDENTIAL"


def capability_for_document_kind(kind: str) -> str:
    return _DOCUMENT_CAPABILITY.get(kind, DEFAULT_DOCUMENT_CAPABILITY)
