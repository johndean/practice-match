"""Schema contract for migrations/016_listing.sql (spec 2026-09-06 D1).

Every column name here is read by scripts/seed_listings.py (L4) and app/api/listings.py
(L5), and by Wave 2b and the Census plan's Phase B after them. A rename that does not
also change this file is a break, not a refactor.
"""
from typing import Any

import psycopg2
import pytest

EXPECTED_COLUMNS: dict[str, tuple[str, bool]] = {
    # name: (data_type, is_nullable)
    "id": ("uuid", False),
    "slug": ("text", False),
    "name": ("text", False),
    "street": ("text", True),
    "city": ("text", False),
    "state": ("text", False),
    "zip": ("text", True),
    "phone": ("text", True),
    "hours": ("text", True),
    "status": ("text", False),
    "location_disclosed": ("boolean", False),
    "name_disclosed": ("boolean", False),
    "geom": ("USER-DEFINED", True),
    "area": ("text", False),
    "type": ("text", False),
    "market": ("text", False),
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
            " created_at IS NOT NULL, updated_at IS NOT NULL"
        )
        assert cur.fetchone() == (True, "draft", False, [], True, True, True)
