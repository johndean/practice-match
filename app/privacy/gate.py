"""The publishing gate (spec 2026-09-09 C.8; directive 11).

ONE predicate, evaluated by every publication route, and evaluated again in SQL by migration 042's
trigger for whatever a route might miss. The two live in the same file in the migration and are read
against each other here: this function calls the SQL function the trigger calls, so there is exactly
one definition of "ready" and it cannot drift.

The messages are the spec's own (H), and they are queued for John's vet as D-IDP-13."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

NOT_READY_MESSAGE = {
    "NOT_SHOW": "Every photograph must finish processing and be reviewed before this listing can be submitted.",
    "SHOW": "Every photograph must finish processing before this listing can be submitted.",
}


def photos_not_ready(conn: Any, listing_id: UUID) -> list[tuple[str, str]]:
    """The offenders, in `listing.photos` order, as `(entry, status)`.

    The SAME SQL function migration 042's trigger evaluates, called with the row's own visibility
    and photos so a route and the database can never disagree about what ready means.

    A listing id that names no row answers `[]` rather than raising: `FROM listing l, LATERAL ...`
    is an inner join, so no listing means no offenders. Every caller here reads the row first and
    refuses a missing one with its own 404, so that arm is unreachable through this module -- it is
    the SQL's own shape and not a decision this function makes."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT n.entry, n.status FROM listing l,"
            "       LATERAL listing_photos_not_ready(l.id, l.identifiable_content_visibility, l.photos) n"
            " WHERE l.id = %s"
            " ORDER BY coalesce((SELECT ordinality FROM jsonb_array_elements_text(l.photos)"
            "                     WITH ORDINALITY t(e, ordinality) WHERE t.e = n.entry LIMIT 1), 0)",
            (listing_id,),
        )
        return [(str(entry), str(status)) for entry, status in cur.fetchall()]


def not_ready_extra(offenders: Sequence[tuple[str, str]]) -> dict[str, list[dict[str, str]]]:
    """The additive key inside decision A5's `error` object -- `{"photos": [{"id", "status"}]}`.

    Additive rather than a new envelope shape: every existing client reads `error.code` and
    `error.message` and is unaffected, and the wizard's error slot renders the message while the
    step-6 tiles are what name the photographs."""
    return {"photos": [{"id": entry, "status": status} for entry, status in offenders]}
