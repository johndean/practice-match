"""Schema contract for migrations/016_listing.sql (spec 2026-09-06 D1).

Every column name here is read by scripts/seed_listings.py (L4) and app/api/listings.py
(L5), and by Wave 2b and the Census plan's Phase B after them. A rename that does not
also change this file is a break, not a refactor.
"""
from pathlib import Path
from typing import Any

import psycopg2
import pytest

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

EXPECTED_COLUMNS: dict[str, tuple[str, bool]] = {
    # name: (data_type, is_nullable)
    "id": ("uuid", False),
    "slug": ("text", False),
    "name": ("text", True),
    "street": ("text", True),
    "city": ("text", True),
    "state": ("text", True),
    "zip": ("text", True),
    "phone": ("text", True),
    "hours": ("text", True),
    "status": ("text", False),
    "location_disclosed": ("boolean", False),
    "name_disclosed": ("boolean", False),
    "geom": ("USER-DEFINED", True),
    "area": ("text", True),
    "type": ("text", True),
    "market": ("text", True),
    "price": ("bigint", True),
    "rev": ("bigint", True),
    "docs": ("integer", True),
    "rooms": ("integer", True),
    "sqft": ("integer", True),
    "bldg": ("text", True),
    "est": ("integer", True),
    "listed_at": ("timestamp with time zone", False),
    "note": ("text", True),
    "staff": ("text", True),
    "services": ("text", True),
    "facility": ("text", True),
    "ownership": ("text", True),
    "photos": ("jsonb", False),
    # A-L11 (`migrations/090_listing_photo_captions.sql`): one description per photograph,
    # parallel to `photos` — the
    # supplier's or seller's own words, which the design's six fixed slot captions cannot supply
    # for a photograph past the sixth.
    "photo_captions": ("jsonb", False),
    "source": ("text", False),
    "created_at": ("timestamp with time zone", False),
    "updated_at": ("timestamp with time zone", False),
    "seller_id": ("uuid", True),
    "facility_type": ("text", True),
    "rev_disclosed": ("boolean", False),
    "documents_disclosed": ("boolean", False),
    # 032 (A-SL11). When the listing entered review: stamped by the first PATCH that takes a
    # published listing off the market (D3) and by SL5's submit, and read back as SL5's outbox
    # idempotency key. Nullable — a draft has never been submitted.
    "submitted_at": ("timestamp with time zone", True),
    # Task SD1 (`migrations/091_listing_provenance.sql`). What is real and what is invented about
    # THIS row, in the supplier's own key names — a bag, not five columns, because the claims are
    # John's seed-data vocabulary (`phone_is_fake`, `address_is_seed_anchor`, …) and mean nothing
    # for a seller's own listing, which would carry five permanent NULLs instead of one honest
    # `{}`. NOT NULL DEFAULT '{}': "no provenance claims recorded" is a statement, not a missing
    # value, and every reader gets an object rather than a null to guard.
    "provenance": ("jsonb", False),
}


def _rows(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def test_listing_has_exactly_the_contracted_columns(conn: Any) -> None:
    found = {
        name: (dtype, nullable == "YES")
        for name, dtype, nullable in _rows(
            conn,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'listing'",
        )
    }
    assert found == EXPECTED_COLUMNS


def test_geom_is_a_geography_point_in_4326(conn: Any) -> None:
    rows = _rows(
        conn,
        "SELECT type, srid FROM geography_columns WHERE f_table_name = 'listing' AND f_geography_column = 'geom'",
    )
    assert rows == [("Point", 4326)]


def test_geom_has_a_gist_index(conn: Any) -> None:
    defs = [d for (d,) in _rows(conn, "SELECT indexdef FROM pg_indexes WHERE tablename = 'listing'")]
    assert any("USING gist" in d and "(geom)" in d for d in defs), defs


def test_the_pagination_key_is_indexed(conn: Any) -> None:
    """L5 pages published listings on (listed_at DESC, id DESC), filtered by status and market."""
    defs = [d for (d,) in _rows(conn, "SELECT indexdef FROM pg_indexes WHERE tablename = 'listing'")]
    assert any("listing_page_idx" in d for d in defs), defs


def test_slug_is_unique(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source)"
            " VALUES ('dup','A','X','TX','X','Small animal','X, TX','seed')"
        )
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO listing (slug, name, city, state, area, type, market, source)"
                " VALUES ('dup','B','Y','TX','Y','Small animal','Y, TX','seed')"
            )


def test_status_source_type_and_bldg_are_checked(conn: Any) -> None:
    base = (
        "INSERT INTO listing (slug, name, city, state, area, type, market, source, status, bldg)"
        " VALUES (%s,'A','X','TX','X',%s,'X, TX',%s,%s,%s)"
    )
    bad = [
        ("s1", "Small animal", "seed", "live", "Included"),          # unknown status
        ("s2", "Small animal", "scraped", "published", "Included"),  # unknown source
        ("s3", "Aquatic", "seed", "published", "Included"),          # unknown type
        ("s4", "Small animal", "seed", "published", "Rented"),       # unknown bldg
    ]
    for params in bad:
        with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(base, params)


def test_defaults_are_what_the_seeder_relies_on(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source)"
            " VALUES ('defaults','A','X','TX','X','Small animal','X, TX','seed')"
            " RETURNING id IS NOT NULL, status, location_disclosed, photos, listed_at IS NOT NULL,"
            " created_at IS NOT NULL, updated_at IS NOT NULL, provenance"
        )
        assert cur.fetchone() == (True, "draft", False, [], True, True, True, {})


# --- Seller listing lifecycle (spec 2026-09-08, D2/D5/D10/D12/D20; migrations 030 + 031) ---
#
# EXPECTED_COLUMNS above gains four rows and flips six. The six were NOT NULL because every
# seeded hospital has them; the approved wizard's step 2 collects a city and a ZIP and nothing
# else (logic.js:1175), so a draft cannot have a state, a market or an area, and `state`/`market`
# arrive from the reviewer at the first publish (D12). The two CHECK constraints below are what
# replaces the NOT NULLs — a draft may be empty, a submitted listing may not, a published listing
# has everything `serialise` interpolates.

EXPECTED_ASSET_COLUMNS: dict[str, tuple[str, bool]] = {
    "id": ("uuid", False),
    "listing_id": ("uuid", False),
    "kind": ("text", False),
    "name": ("text", False),
    "content_type": ("text", False),
    "byte_size": ("bigint", False),
    "sha256": ("text", False),
    "storage_key": ("text", False),
    # A-SL20 / A-SL22 (2), John 2026-09-09: "have the user articulate what it is". The seller's own
    # words for THIS photograph, nullable because a photograph that has never been described has
    # none — the design's fixed slot caption is what the wizard shows in its place, by position.
    "caption": ("text", True),
    "created_at": ("timestamp with time zone", False),
}


def test_listing_asset_has_exactly_the_contracted_columns(conn: Any) -> None:
    found = {
        name: (dtype, nullable == "YES")
        for name, dtype, nullable in _rows(
            conn,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'listing_asset'",
        )
    }
    assert found == EXPECTED_ASSET_COLUMNS


def test_declined_and_other_are_now_legal_and_the_old_refusals_still_are_not(conn: Any) -> None:
    """D2 adds `declined` to the status CHECK; D10 adds `Other` to the type CHECK — the approved
    step-1 select offers it (logic.js:1174) and a column that cannot hold an answer the design
    collects is the bug, not the answer."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, status, est, price, zip)"
            " VALUES ('sl-declined','A','X','TX','X','Other','X, TX','seller','declined',1998,100,'78613')"
        )
    for status, ptype in (("live", "Other"), ("declined", "Aquatic")):
        with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                "INSERT INTO listing (slug, name, city, state, area, type, market, source, status, est, price, zip)"
                " VALUES (%s,'A','X','TX','X',%s,'X, TX','seller',%s,1998,100,'78613')",
                (f"sl-bad-{status}-{ptype}", ptype, status),
            )


def test_a_draft_may_be_almost_empty(conn: Any) -> None:
    """The wizard creates the row before step 1 is filled in (D9's POST), so a draft carries a slug,
    a source and nothing else. `listing-<id>` is D13's placeholder slug."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, source, status) VALUES ('listing-draft','seller','draft')"
            " RETURNING name, city, state, area, type, market, seller_id, rev_disclosed, documents_disclosed"
        )
        assert cur.fetchone() == (None, None, None, None, None, None, None, False, False)


def test_a_withdrawn_listing_may_also_be_empty_and_nothing_else_may(conn: Any) -> None:
    """`listing_submittable_ck`, both ways. `withdrawn` is terminal and reachable from `draft`, so
    an abandoned empty draft must still be withdrawable (logic.js:1061)."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status) VALUES ('listing-gone','seller','withdrawn')")
    for status in ("in_review", "published", "paused", "declined"):
        with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO listing (slug, source, status) VALUES (%s,'seller',%s)", (f"sl-empty-{status}", status))


def test_a_published_listing_must_carry_what_serialise_interpolates(conn: Any) -> None:
    """`listing_publishable_ck` (D12, widened by 034 / A-SL33 (1)). `serialise` builds the
    anonymised name from `area` and the Browse market filter pages on `market`; `stateOf(market)`
    names the state on the detail — and `frontend/src/logic.js` calls `p.sqft.toLocaleString()`
    unconditionally at every site that renders a practice from Browse's own list, so a published
    row missing FLOOR AREA is exactly as broken as one missing its market, not merely incomplete."""
    submittable = ("A", "Cedar Park", "78613", "Small animal", 1998, 1_450_000)
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "INSERT INTO listing (slug, source, status, name, city, zip, type, est, price)"
            " VALUES ('sl-nopublish','seller','published',%s,%s,%s,%s,%s,%s)", submittable
        )
    # state/market/area present, sqft still missing: also refused (A-SL33 (1) — the fourth
    # requirement `p.sqft.toLocaleString()` needs, added beside the original three).
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "INSERT INTO listing (slug, source, status, name, city, zip, type, est, price, state, market, area)"
            " VALUES ('sl-nosqft','seller','published',%s,%s,%s,%s,%s,%s,'TX','Austin, TX','Cedar Park')", submittable
        )
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, source, status, name, city, zip, type, est, price, state, market, area, sqft)"
            " VALUES ('sl-publish','seller','published',%s,%s,%s,%s,%s,%s,'TX','Austin, TX','Cedar Park',3000)", submittable
        )


def test_seller_id_references_account_and_survives_its_deletion(conn: Any) -> None:
    """D5: nullable, because a production seed row belongs to the VIN Foundation and not to a
    person; `ON DELETE SET NULL` because a withdrawn listing keeps its history after the account
    that made it is gone."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state) VALUES ('sl-owner@example.org','x','active') RETURNING id")
        owner = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO listing (slug, source, status, seller_id) VALUES ('sl-owned','seller','draft',%s)", (owner,)
        )
        cur.execute("DELETE FROM account WHERE id = %s", (owner,))
        cur.execute("SELECT seller_id FROM listing WHERE slug = 'sl-owned'")
        assert cur.fetchone() == (None,)


def test_the_owner_and_asset_indexes_exist(conn: Any) -> None:
    """`(seller_id, updated_at DESC)` is the dashboard's key (D5); the asset indexes are the
    wizard's step-6 read and the document lock's lookup."""
    listing_defs = [d for (d,) in _rows(conn, "SELECT indexdef FROM pg_indexes WHERE tablename = 'listing'")]
    assert any("listing_owner_idx" in d for d in listing_defs), listing_defs
    asset_defs = [d for (d,) in _rows(conn, "SELECT indexdef FROM pg_indexes WHERE tablename = 'listing_asset'")]
    assert any("listing_asset_listing_idx" in d for d in asset_defs), asset_defs
    assert any("listing_asset_kind_idx" in d for d in asset_defs), asset_defs


def test_an_asset_dies_with_its_listing_and_its_kind_is_checked(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status) VALUES ('sl-assets','seller','draft') RETURNING id")
        listing_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
            " VALUES (%s,'photo','1.webp','image/webp',1024,'abc','listings/x/photos/y.webp')", (listing_id,)
        )
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
            " VALUES (%s,'video','1.mp4','video/mp4',1024,'abc','listings/x/videos/y.mp4')", (listing_id,)
        )
    with conn.cursor() as cur:
        cur.execute("DELETE FROM listing WHERE id = %s", (listing_id,))
        cur.execute("SELECT count(*) FROM listing_asset WHERE listing_id = %s", (listing_id,))
        assert cur.fetchone() == (0,)


def test_a_storage_key_is_claimed_once(conn: Any) -> None:
    """One object, one row. A duplicate key would make `delete()` orphan a live asset."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO listing (slug, source, status) VALUES ('sl-keys','seller','draft') RETURNING id")
        listing_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
            " VALUES (%s,'photo','1.webp','image/webp',1,'a','listings/dup.webp')", (listing_id,)
        )
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO listing_asset (listing_id, kind, name, content_type, byte_size, sha256, storage_key)"
                " VALUES (%s,'photo','2.webp','image/webp',1,'b','listings/dup.webp')", (listing_id,)
            )


def test_the_seeded_disclosure_backfill_is_in_the_migration_not_in_the_seeder(conn: Any) -> None:
    """D22: "every seed sets all four flags true … so nothing John sees on QA changes". A row that
    already existed when 030 applied is a seeded hospital, and its revenue must not blank between
    two tasks of this plan. New rows still default to false — sellers hide by default."""
    with conn.cursor() as cur:
        cur.execute("SELECT column_default FROM information_schema.columns"
                    " WHERE table_name='listing' AND column_name IN ('rev_disclosed','documents_disclosed')")
        assert sorted(cur.fetchall()) == [("false",), ("false",)]
    assert "WHERE source = 'seed'" in (MIGRATIONS / "030_listing_owner_and_status.sql").read_text()
