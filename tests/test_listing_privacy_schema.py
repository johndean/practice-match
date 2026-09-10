"""The image-identifiability schema contract (spec 2026-09-09 §C.1, §C.3, §C.8; migrations 040-042).

`tests/test_listing_schema.py` owns `listing` and `listing_asset`; this file owns the column
migration 040 adds and the whole of `listing_asset_privacy`, so a change to either is a deliberate
edit here rather than a silent widening somewhere else."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg2
import pytest

VISIBILITIES = ("SHOW", "NOT_SHOW")

STATUSES = (
    "UPLOADED", "PROCESSING", "SCANNED", "REDACTION_GENERATED", "READY_FOR_REVIEW",
    "SELLER_CONFIRMED", "PUBLISHED", "PROCESSING_FAILED", "REDACTION_FAILED",
    "REVIEW_REQUIRED", "REPROCESS_REQUIRED",
)

EXPECTED_PRIVACY_COLUMNS: dict[str, tuple[str, bool]] = {
    "asset_id": ("uuid", False),
    "listing_id": ("uuid", False),
    "processing_status": ("text", False),
    "processing_version": ("integer", False),
    "attempts": ("integer", False),
    "last_error": ("text", True),
    "original_storage_key": ("text", False),
    "redacted_storage_key": ("text", True),
    "redacted_sha256": ("text", True),
    "confirmed_sha256": ("text", True),
    "ocr": ("jsonb", False),
    "identity_matches": ("jsonb", False),
    "vision": ("jsonb", False),
    "detected_regions": ("jsonb", False),
    "redaction_regions": ("jsonb", False),
    "detection_at": ("timestamp with time zone", True),
    "seller_review_status": ("text", False),
    "seller_confirmed": ("boolean", False),
    "seller_confirmed_at": ("timestamp with time zone", True),
    "seller_confirmation_account_id": ("uuid", True),
    "buyer_visible": ("boolean", False),
    "final_privacy_state": ("text", True),
    "reprocess_reason": ("text", True),
    "reprocess_requested_at": ("timestamp with time zone", True),
    "reprocessed_at": ("timestamp with time zone", True),
    "created_at": ("timestamp with time zone", False),
    "updated_at": ("timestamp with time zone", False),
}


def _rows(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def _listing(conn: Any, slug: str, *, status: str = "draft", photos: list[str] | None = None) -> Any:
    """A row complete enough for `listing_publishable_ck` (migration 030), because every trigger
    case below publishes one. `tests/api/test_listing_assets.py` builds the same shape."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, street, city, state, zip, area, type, market, source, status,"
            " est, price, sqft, photos)"
            " VALUES (%s,'A','1 Main St','X','TX','78613','X','Other','X, TX','seller',%s,1998,100,3000,%s::jsonb)"
            " RETURNING id",
            (slug, status, json.dumps(photos or [])),
        )
        return cur.fetchone()[0]


def _asset(conn: Any, listing_id: Any) -> Any:
    asset_id = uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing_asset (id, listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
            " VALUES (%s,%s,'photo','a.webp','image/webp',10,'d',%s)",
            (asset_id, listing_id, f"listings/{listing_id}/photos/{asset_id}/display.webp"),
        )
    return asset_id


def _privacy(conn: Any, asset_id: Any, listing_id: Any, **overrides: Any) -> None:
    columns = {"asset_id": asset_id, "listing_id": listing_id, "processing_version": 1,
               "original_storage_key": f"listings/{listing_id}/photos/{asset_id}/original.jpg", **overrides}
    names = ", ".join(columns)
    holders = ", ".join(["%s"] * len(columns))
    with conn.cursor() as cur:
        cur.execute(f"INSERT INTO listing_asset_privacy ({names}) VALUES ({holders})", tuple(columns.values()))


def test_the_listing_carries_one_authoritative_visibility_defaulting_to_not_show(conn: Any) -> None:
    """Directive 7: "The listing must have a single authoritative setting ... Default: NOT_SHOW.
    The safest privacy state is the default." """
    listing_id = _listing(conn, "idp-default")
    assert _rows(conn, "SELECT identifiable_content_visibility FROM listing WHERE id = %s", (listing_id,)) == [("NOT_SHOW",)]
    for value in VISIBILITIES:
        with conn.cursor() as cur:
            cur.execute("UPDATE listing SET identifiable_content_visibility = %s WHERE id = %s", (value, listing_id))
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("UPDATE listing SET identifiable_content_visibility = 'MAYBE' WHERE id = %s", (listing_id,))


def test_the_privacy_table_has_exactly_the_contracted_columns(conn: Any) -> None:
    found = {
        name: (dtype, nullable == "YES")
        for name, dtype, nullable in _rows(
            conn,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns"
            " WHERE table_name = 'listing_asset_privacy'",
        )
    }
    assert found == EXPECTED_PRIVACY_COLUMNS


@pytest.mark.parametrize("status", STATUSES)
def test_every_contracted_status_is_legal_and_a_twelfth_is_not(conn: Any, status: str) -> None:
    listing_id = _listing(conn, f"idp-status-{status.lower()}")
    asset_id = _asset(conn, listing_id)
    ready = status in ("REDACTION_GENERATED", "READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")
    extra: dict[str, Any] = {}
    if ready:
        extra["redacted_storage_key"] = f"listings/{listing_id}/photos/{asset_id}/redacted.webp"
        extra["redacted_sha256"] = "b" * 64
    if status == "SELLER_CONFIRMED":
        extra |= {"seller_confirmed": True, "seller_confirmed_at": datetime.now(UTC), "final_privacy_state": "NOT_SHOW",
                  "confirmed_sha256": "b" * 64}
    _privacy(conn, asset_id, listing_id, processing_status=status, **extra)


def test_an_unknown_status_is_refused(conn: Any) -> None:
    listing_id = _listing(conn, "idp-status-bad")
    asset_id = _asset(conn, listing_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, processing_status="AI_PASSED")


def test_a_confirmation_must_cover_the_derivative_that_is_served(conn: Any) -> None:
    """lap_confirmed_ck. "Confirmed" and "confirmed against a derivative other than the one served"
    are mutually exclusive AT THE DATABASE, so spec C.1's "confirmed under NOT_SHOW against the
    derivative it serves" is a column comparison rather than an inference."""
    listing_id = _listing(conn, "idp-confirm")
    asset_id = _asset(conn, listing_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, processing_status="SELLER_CONFIRMED", seller_confirmed=True,
                 seller_confirmed_at=datetime.now(UTC), final_privacy_state="NOT_SHOW",
                 redacted_storage_key=f"listings/{listing_id}/photos/{asset_id}/redacted.webp",
                 redacted_sha256="b" * 64, confirmed_sha256="c" * 64)


def test_visibility_requires_readiness_and_readiness_requires_a_derivative(conn: Any) -> None:
    """lap_visible_ready_ck and lap_ready_has_derivative_ck: no row can claim visibility without
    readiness, or readiness without a derivative."""
    listing_id = _listing(conn, "idp-visible")
    asset_id = _asset(conn, listing_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, processing_status="PROCESSING", buyer_visible=True)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, processing_status="READY_FOR_REVIEW")


def test_the_redacted_key_is_never_the_original(conn: Any) -> None:
    """lap_never_the_original_ck -- the invariant spec C.4 states last: nothing ever writes
    redacted_storage_key := original_storage_key."""
    listing_id = _listing(conn, "idp-never")
    asset_id = _asset(conn, listing_id)
    key = f"listings/{listing_id}/photos/{asset_id}/original.jpg"
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, processing_status="READY_FOR_REVIEW",
                 redacted_storage_key=key, redacted_sha256="b" * 64)


def test_a_stale_flag_and_its_timestamp_travel_together(conn: Any) -> None:
    """lap_stale_ck."""
    listing_id = _listing(conn, "idp-stale")
    asset_id = _asset(conn, listing_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _privacy(conn, asset_id, listing_id, reprocess_reason="VERSION")


def test_deleting_the_asset_deletes_its_privacy_row(conn: Any) -> None:
    listing_id = _listing(conn, "idp-cascade")
    asset_id = _asset(conn, listing_id)
    _privacy(conn, asset_id, listing_id)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM listing_asset WHERE id = %s", (asset_id,))
    assert _rows(conn, "SELECT 1 FROM listing_asset_privacy WHERE asset_id = %s", (asset_id,)) == []


def test_both_indexes_exist_under_their_contracted_names(conn: Any) -> None:
    found = {name for (name,) in _rows(
        conn, "SELECT indexname FROM pg_indexes WHERE tablename = 'listing_asset_privacy'")}
    assert {"listing_asset_privacy_listing_idx", "listing_asset_privacy_sweep_idx"} <= found


def test_a_direct_publish_of_a_listing_with_an_unprocessed_photograph_raises(conn: Any) -> None:
    """Directive 11's fail-closed backstop. `tests/api/test_listing_assets.py`'s own `_publish`
    helper is a bare UPDATE and demonstrates that the DATABASE used to accept a publish regardless
    of asset state; migration 042 is what refuses it -- by any route, by a test helper, by hand."""
    listing_id = _listing(conn, "idp-trigger")
    asset_id = _asset(conn, listing_id)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET photos = %s::jsonb WHERE id = %s", (json.dumps([str(asset_id)]), listing_id))
    _privacy(conn, asset_id, listing_id, processing_status="UPLOADED")
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.RaiseException) as caught:
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))
    assert "PHOTOS_NOT_READY" in str(caught.value)


def test_a_flagged_ready_photograph_also_refuses_a_new_publication(conn: Any) -> None:
    """A stale row is an offender at the gate ('STALE'): a NEW publication waits for its in-place
    re-run. An EXISTING publication is untouched -- proved by the third case below."""
    listing_id = _listing(conn, "idp-trigger-stale")
    asset_id = _asset(conn, listing_id)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET photos = %s::jsonb WHERE id = %s", (json.dumps([str(asset_id)]), listing_id))
    _privacy(conn, asset_id, listing_id, processing_status="SELLER_CONFIRMED", seller_confirmed=True,
             seller_confirmed_at=datetime.now(UTC), final_privacy_state="NOT_SHOW", confirmed_sha256="b" * 64,
             redacted_storage_key=f"listings/{listing_id}/photos/{asset_id}/redacted.webp",
             redacted_sha256="b" * 64, reprocess_reason="VERSION", reprocess_requested_at=datetime.now(UTC))
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))


def test_the_trigger_fires_on_status_alone_and_lets_an_already_published_row_be_touched(conn: Any) -> None:
    """`BEFORE INSERT OR UPDATE OF status`, guarded by `OLD.status <> 'published'` -- so a published
    listing whose photograph later goes stale is not frozen out of every other UPDATE."""
    listing_id = _listing(conn, "idp-trigger-touch")
    asset_id = _asset(conn, listing_id)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET photos = %s::jsonb WHERE id = %s", (json.dumps([str(asset_id)]), listing_id))
    _privacy(conn, asset_id, listing_id, processing_status="PUBLISHED", buyer_visible=True,
             redacted_storage_key=f"listings/{listing_id}/photos/{asset_id}/redacted.webp",
             redacted_sha256="b" * 64)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))
        cur.execute("UPDATE listing_asset_privacy SET reprocess_reason = 'VERSION',"
                    " reprocess_requested_at = now(), updated_at = now() WHERE asset_id = %s", (asset_id,))
        cur.execute("UPDATE listing SET updated_at = now() WHERE id = %s", (listing_id,))


def test_a_seed_path_entry_passes_under_show_and_is_an_offender_under_not_show(conn: Any) -> None:
    """Spec C.10: a seed photograph has no asset row and can only ever be served under SHOW."""
    listing_id = _listing(conn, "idp-seed", photos=["round-rock/1.webp"])
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET identifiable_content_visibility = 'SHOW' WHERE id = %s", (listing_id,))
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))
        cur.execute("UPDATE listing SET status = 'paused' WHERE id = %s", (listing_id,))
        cur.execute("UPDATE listing SET identifiable_content_visibility = 'NOT_SHOW' WHERE id = %s", (listing_id,))
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("UPDATE listing SET status = 'published' WHERE id = %s", (listing_id,))
    assert _rows(conn, "SELECT status FROM listing_photos_not_ready(%s, 'NOT_SHOW', %s::jsonb)",
                 (listing_id, json.dumps(["round-rock/1.webp"]))) == [("SEED_UNPROCESSED",)]


def test_a_re_seed_upsert_of_a_published_seed_row_succeeds(conn: Any) -> None:
    """A-IDP-6: the gate guards the seller's transition only. A direct INSERT as
    published is the seeder's one path (scripts/seed_listings.py:116-146). The seeder's
    UPSERT on a re-seed hits the DO UPDATE half when the row already exists; under the
    old INSERT arm, even the first insert would have raised PHOTOS_NOT_READY. This
    proves the new UPDATE-only gate allows seeding to work."""
    listing_id = _listing(conn, "idp-reseed", status="published", photos=["seed/1.webp"])
    # Re-UPSERT the same slug as the seeder would
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, street, city, state, zip, hours, status,"
            " location_disclosed, name_disclosed, area, type, market, est, price, sqft,"
            " source, photos, updated_at)"
            " VALUES ('idp-reseed', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
            " %s, %s, %s, %s, %s::jsonb, now())"
            " ON CONFLICT (slug) DO UPDATE SET status = EXCLUDED.status, name = EXCLUDED.name"
                " WHERE listing.source = 'seed'",
            ("A", "X", "X", "TX", "X", "24/7", "published", True, True, "X", "Other", "X, TX", 1998, 100, 3000, "seed", json.dumps(["seed/1.webp"])),
        )
    # Verify it still exists and is still published
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM listing WHERE id = %s", (listing_id,))
        assert cur.fetchone()[0] == "published"


def test_a_direct_insert_as_published_with_path_photographs_is_not_refused(conn: Any) -> None:
    """A-IDP-6: the gate guards the seller's transition only; a direct INSERT as
    published is the seeder's one path, and the resolver hides these photographs until
    they are processed (P9)."""
    listing_id = _listing(conn, "idp-direct", status="published", photos=["seed/1.webp", "seed/2.webp"])
    # Verify it was inserted successfully
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM listing WHERE id = %s", (listing_id,))
        assert cur.fetchone()[0] == "published"

