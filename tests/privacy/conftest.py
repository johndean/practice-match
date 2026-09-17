"""One builder for a privacy row in any state, with whatever migration 041's CHECKs require of
that state already true. Every privacy suite uses it, so a CHECK that changes fails in one place.

Not fixtures: plain helpers, imported by name (`from tests.privacy.conftest import make_row`), the
idiom `tests/conftest.py::walk_routes` and `tests/api/conftest.py::auth_headers` already use. It
lives in a `conftest.py` so that pytest gives it one canonical module identity under the suite's
prepend import mode, whichever file imports it first.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.privacy import display_key, original_key, redacted_key

#: The four states `lap_ready_has_derivative_ck` requires a derivative for.
HAS_DERIVATIVE = ("REDACTION_GENERATED", "READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")

#: `lap_status_confirmed_ck`: this state IS the confirmation, so the builder cannot be asked for a
#: SELLER_CONFIRMED row that is not confirmed -- the database refuses it. `confirmed=True` is
#: therefore an argument that can only widen the set, never narrow it.
CONFIRMED_STATES = ("SELLER_CONFIRMED",)

_INSERT = """
INSERT INTO listing_asset_privacy
  (asset_id, listing_id, processing_status, processing_version, attempts, original_storage_key,
   redacted_storage_key, redacted_sha256, confirmed_sha256, seller_confirmed, seller_confirmed_at,
   final_privacy_state, buyer_visible, reprocess_reason, reprocess_requested_at,
   redaction_regions, seller_review_status)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
"""


def make_account(conn: Any, email: str | None = None) -> UUID:
    """`seller_confirmation_account_id REFERENCES account(id)`, so a confirmation needs a real row.

    `(email, password_hash, state)` and not `(email, status)`: `migrations/010_accounts.sql` names
    the column `state`, and `password_hash` is NOT NULL with no default."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES (%s,'h','active') RETURNING id",
                    (email or f"idp-{uuid4().hex[:8]}@example.org",))
        return UUID(str(cur.fetchone()[0]))


def make_listing(conn: Any, slug: str, *, status: str = "draft", visibility: str = "NOT_SHOW",
                 seller_id: UUID | None = None) -> UUID:
    """`seller_id` (Task SEED-CONFIRM, `tests/scripts/test_confirm_seed_photos.py`): the demo
    hospitals are seeded owned (D25), and a confirmation needs a real owning account
    (`seller_confirmation_account_id REFERENCES account`), so that suite needs a listing it can
    give one to. `None` is every existing caller's own default and this column's."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, status,"
            " est, price, zip, photos, identifiable_content_visibility, seller_id)"
            " VALUES (%s,'Hill Country Animal Hospital','Cedar Park','TX','Cedar Park','Small animal',"
            "'Austin, TX','seller',%s,1998,100,'78613','[]'::jsonb,%s,%s) RETURNING id",
            (slug, status, visibility, seller_id),
        )
        return UUID(str(cur.fetchone()[0]))


def make_row(conn: Any, *, listing_id: UUID | None = None, processing_status: str = "UPLOADED",
             processing_version: int = 1, attempts: int = 0, confirmed: bool = False,
             final_privacy_state: str = "NOT_SHOW", buyer_visible: bool = False,
             reprocess_reason: str | None = None,
             redaction_regions: list[dict[str, Any]] | None = None) -> tuple[UUID, UUID]:
    """(asset_id, listing_id). The asset row, its entry in `listing.photos` and its privacy row.

    `final_privacy_state` is the SIDE of a confirmation -- the listing's own setting at the moment
    the seller confirmed -- and is written only when the row is confirmed. It is a parameter (P3
    review Minor-7) because P10's SHOW -> NOT_SHOW flip compares exactly that column
    (`seller_confirmed AND final_privacy_state = 'NOT_SHOW'`), and a builder that could only make
    the NOT_SHOW side gave that predicate no way to build its own other half.

    A confirmed row always carries the derivative its confirmation covers, whatever state it is in:
    `lap_confirmed_ck` is `confirmed_sha256 = redacted_sha256`, and a confirmation beside a NULL
    `redacted_sha256` passes it only through three-valued logic (`NULL = NULL` is NULL, and a CHECK
    passes on NULL) -- a shape no real row ever has, because `confirm` itself carries
    `redacted_sha256 IS NOT NULL`. A case that wants that shape asks for it explicitly by poking
    the column, as `test_confirm_refuses_a_ready_row_that_has_no_derivative_hash` does."""
    listing = listing_id if listing_id is not None else make_listing(conn, f"idp-{uuid4().hex[:8]}")
    asset_id = uuid4()
    now = datetime.now(UTC)
    confirmed = confirmed or processing_status in CONFIRMED_STATES
    has_derivative = processing_status in HAS_DERIVATIVE or confirmed
    derivative = "b" * 64 if has_derivative else None
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing_asset (id, listing_id, kind, name, content_type, byte_size,"
                    " sha256, storage_key) VALUES (%s,%s,'photo','a.webp','image/webp',10,%s,%s)",
                    (asset_id, listing, "d" * 64, display_key(listing, asset_id)))
        cur.execute("UPDATE listing SET photos = photos || to_jsonb(%s::text) WHERE id = %s",
                    (str(asset_id), listing))
        cur.execute(_INSERT, (
            asset_id, listing, processing_status, processing_version, attempts,
            original_key(listing, asset_id, ".jpg"),
            redacted_key(listing, asset_id) if has_derivative else None,
            derivative,
            derivative if confirmed else None,
            confirmed, now if confirmed else None,
            final_privacy_state if confirmed else None,
            buyer_visible, reprocess_reason, now if reprocess_reason else None,
            json.dumps(redaction_regions or []), "looks_good" if confirmed else "pending",
        ))
    return asset_id, listing
