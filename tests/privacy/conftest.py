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


def make_listing(conn: Any, slug: str, *, status: str = "draft", visibility: str = "NOT_SHOW") -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, status,"
            " est, price, zip, photos, identifiable_content_visibility)"
            " VALUES (%s,'Hill Country Animal Hospital','Cedar Park','TX','Cedar Park','Small animal',"
            "'Austin, TX','seller',%s,1998,100,'78613','[]'::jsonb,%s) RETURNING id",
            (slug, status, visibility),
        )
        return UUID(str(cur.fetchone()[0]))


def make_row(conn: Any, *, listing_id: UUID | None = None, processing_status: str = "UPLOADED",
             processing_version: int = 1, attempts: int = 0, confirmed: bool = False,
             buyer_visible: bool = False, reprocess_reason: str | None = None,
             redaction_regions: list[dict[str, Any]] | None = None) -> tuple[UUID, UUID]:
    """(asset_id, listing_id). The asset row, its entry in `listing.photos` and its privacy row."""
    listing = listing_id if listing_id is not None else make_listing(conn, f"idp-{uuid4().hex[:8]}")
    asset_id = uuid4()
    now = datetime.now(UTC)
    ready = processing_status in HAS_DERIVATIVE
    confirmed = confirmed or processing_status in CONFIRMED_STATES
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing_asset (id, listing_id, kind, name, content_type, byte_size,"
                    " sha256, storage_key) VALUES (%s,%s,'photo','a.webp','image/webp',10,%s,%s)",
                    (asset_id, listing, "d" * 64, display_key(listing, asset_id)))
        cur.execute("UPDATE listing SET photos = photos || to_jsonb(%s::text) WHERE id = %s",
                    (str(asset_id), listing))
        cur.execute(_INSERT, (
            asset_id, listing, processing_status, processing_version, attempts,
            original_key(listing, asset_id, ".jpg"),
            redacted_key(listing, asset_id) if ready else None,
            "b" * 64 if ready else None,
            "b" * 64 if confirmed else None,
            confirmed, now if confirmed else None,
            "NOT_SHOW" if confirmed else None,
            buyer_visible, reprocess_reason, now if reprocess_reason else None,
            json.dumps(redaction_regions or []), "looks_good" if confirmed else "pending",
        ))
    return asset_id, listing
