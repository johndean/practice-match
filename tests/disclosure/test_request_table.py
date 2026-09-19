"""The `request` table itself (directive 4, 18, 23): the columns, the status machine's CHECK
constraints, and the one-active-row-per-(listing, buyer) invariant the authorization lookup in
Task 3 depends on being true in the database, not merely in application code."""
from __future__ import annotations

from uuid import uuid4

import psycopg2
import pytest


def _account(conn, email: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO account (email, password_hash, state) VALUES (%s,'x','active') RETURNING id",
            (email,),
        )
        return str(cur.fetchone()[0])


def _listing(conn, seller_id: str | None) -> str:
    # zip/est/price/sqft (deviation from the plan's literal helper, see task-01-report.md): the
    # plan's own INSERT satisfies listing_publishable_ck's ORIGINAL three-field shape (030) but not
    # its WIDENED shape (034, already applied in this repo) — which also requires sqft for a
    # published row — nor listing_submittable_ck's zip/est/price for any non-draft/withdrawn row.
    # A published `listing` fixture in a plan written before 034/030 landed here needs all four.
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, seller_id, status,"
            " zip, est, price, sqft)"
            " VALUES (%s,'Test Practice','Austin','TX','Austin','Small animal','Austin, TX','seller',%s,'published',"
            " '78701',1990,1000000,2500)"
            " RETURNING id",
            (f"test-{uuid4().hex}", seller_id),
        )
        return str(cur.fetchone()[0])


def test_a_pending_request_can_be_inserted_with_only_the_required_fields(conn) -> None:
    seller = _account(conn, "seller@example.org")
    buyer = _account(conn, "buyer@example.org")
    listing = _listing(conn, seller)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s) RETURNING status, requested_disclosure_level",
            (listing, buyer, seller),
        )
        status, level = cur.fetchone()
    assert (status, level) == ("PENDING", "FULL_CONFIDENTIAL")


def test_a_buyer_cannot_be_the_listing_s_own_seller(conn) -> None:
    seller = _account(conn, "seller2@example.org")
    listing = _listing(conn, seller)
    with pytest.raises(psycopg2.errors.CheckViolation), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s)",
            (listing, seller, seller),
        )


def test_only_one_active_request_per_listing_and_buyer(conn) -> None:
    seller = _account(conn, "seller3@example.org")
    buyer = _account(conn, "buyer3@example.org")
    listing = _listing(conn, seller)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s)", (listing, buyer, seller))
    with pytest.raises(psycopg2.errors.UniqueViolation), conn.cursor() as cur:
        cur.execute("INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s)", (listing, buyer, seller))


def test_a_second_request_is_allowed_once_the_first_is_denied(conn) -> None:
    seller = _account(conn, "seller4@example.org")
    buyer = _account(conn, "buyer4@example.org")
    reviewer = _account(conn, "staff4@example.org")
    listing = _listing(conn, seller)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s) RETURNING id",
            (listing, buyer, seller),
        )
        first_id = cur.fetchone()[0]
        cur.execute(
            "UPDATE request SET status = 'DENIED', reviewed_at = now(), reviewed_by = %s WHERE id = %s",
            (reviewer, first_id),
        )
        # No UniqueViolation: a DENIED row is outside the partial index's WHERE clause.
        cur.execute("INSERT INTO request (listing_id, buyer_user_id, seller_user_id) VALUES (%s,%s,%s)", (listing, buyer, seller))


def test_status_is_restricted_to_the_four_named_values(conn) -> None:
    seller = _account(conn, "seller5@example.org")
    buyer = _account(conn, "buyer5@example.org")
    listing = _listing(conn, seller)
    with pytest.raises(psycopg2.errors.CheckViolation), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request (listing_id, buyer_user_id, seller_user_id, status) VALUES (%s,%s,%s,'accepted')",
            (listing, buyer, seller),
        )
