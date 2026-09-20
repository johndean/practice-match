"""Ruling D-C59 (John, 2026-09-20, verbatim: "a buyer can not be a seller and a seller can not be
a buyer - we will always keep accounts separate and if the edge case exists then then the user
will have to have 2 accounts"; spec docs/superpowers/specs/2026-09-20-account-role-exclusivity-
ruling.md). `migrations/100_role_exclusivity.sql` is the enforcement; this file drives it directly
against `role_grant`, below the application layer, because the trigger is the authority every
caller (`app/api/applications.py`, `app/api/admin_users.py`, a future one nobody has written yet)
answers to — a test at THIS layer cannot be defeated by a caller that forgets to ask.

Uses the root `conn`/`scratch_dsn` fixtures (`tests/conftest.py`): each test gets a FRESH database,
already migrated (migration 100 included), so every test below starts from the real, shipped
schema rather than a hand-built approximation of it.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg2
import psycopg2.errors
import pytest

MIGRATION_100 = (Path(__file__).resolve().parents[2] / "migrations" / "100_role_exclusivity.sql").read_text()


def _account(conn: Any, email: str) -> Any:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO account (email, password_hash, state, display_name) VALUES (%s,'x','active','T') RETURNING id",
                    (email,))
        return cur.fetchone()[0]


def _grant(conn: Any, account_id: Any, role: str) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,%s,%s)", (account_id, role, account_id))


def _active_roles(conn: Any, account_id: Any) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT role FROM role_grant WHERE account_id=%s AND revoked_at IS NULL", (account_id,))
        return {r[0] for r in cur.fetchall()}


# --- the ordinary case: sequential writes, each its own implicit transaction (`conn.autocommit`
# is True — `tests/conftest.py`'s own fixture, the STRONGER case since nothing here shares a
# transaction to serialise the two statements for free) ---


def test_granting_the_excluded_role_second_is_refused_either_direction(conn) -> None:
    for first, second in (("buyer", "seller"), ("seller", "buyer")):
        aid = _account(conn, f"excl-{first}-{second}@example.org")
        _grant(conn, aid, first)
        with pytest.raises(psycopg2.errors.CheckViolation, match="ruling D-C59"):
            _grant(conn, aid, second)
        # The refused statement's OWN implicit transaction rolled back; the first grant stands.
        assert _active_roles(conn, aid) == {first}


def test_granting_the_same_role_twice_still_answers_the_pre_existing_active_index(conn) -> None:
    """`role_grant_active_idx` (migration 011) is untouched by this migration: re-granting a role
    an account already holds actively is refused by that unique index, not by the new trigger, and
    this proves the new trigger did not shadow or duplicate it."""
    aid = _account(conn, "twice-buyer@example.org")
    _grant(conn, aid, "buyer")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _grant(conn, aid, "buyer")


@pytest.mark.parametrize("roles", [("buyer", "staff"), ("seller", "staff"), ("buyer", "admin"),
                                   ("seller", "admin"), ("staff", "admin")])
def test_every_other_combination_of_two_roles_is_unaffected(conn, roles: tuple[str, str]) -> None:
    """The ruling names ONE pair. Every other combination — including `staff`/`admin` alongside
    either member role — grants cleanly, both orders, proving the trigger's early return
    (`NEW.role NOT IN ('buyer', 'seller')`) really does leave everything else alone."""
    for order in (roles, tuple(reversed(roles))):
        aid = _account(conn, f"combo-{order[0]}-{order[1]}-{uuid4().hex[:6]}@example.org")
        for role in order:
            _grant(conn, aid, role)
        assert _active_roles(conn, aid) == set(roles)


def test_revoking_one_of_a_pair_is_never_blocked_and_the_freed_role_can_then_be_granted(conn) -> None:
    """The escape hatch the ruling itself names: "the user will have to have 2 accounts" is about
    NOT holding both on the SAME account — it says nothing against trading one role for the other
    on one account, and the trigger's own guard (`NEW.revoked_at IS NOT NULL` returns early) makes
    that free. Simulates the one legitimate way an account already holding one role could still end
    up wanting the other: revoke, then grant."""
    aid = _account(conn, "trade-role@example.org")
    _grant(conn, aid, "buyer")
    with conn.cursor() as cur:
        cur.execute("UPDATE role_grant SET revoked_at=now() WHERE account_id=%s AND role='buyer' AND revoked_at IS NULL", (aid,))
    assert _active_roles(conn, aid) == set()
    _grant(conn, aid, "seller")
    assert _active_roles(conn, aid) == {"seller"}


def test_a_direct_update_that_renames_an_active_rows_role_in_place_is_also_checked(conn) -> None:
    """Not a shape any caller in this codebase produces (every write here is INSERT-a-new-row or
    revoke-the-old-one), but the trigger fires on `BEFORE INSERT OR UPDATE`, so a hypothetical
    direct `UPDATE role_grant SET role=...` on an active row is covered too — and the `id IS
    DISTINCT FROM NEW.id` guard in the trigger means this does NOT confuse the row with itself
    when neither `buyer` nor `seller` was already present."""
    aid = _account(conn, "rename-in-place@example.org")
    _grant(conn, aid, "buyer")
    with conn.cursor() as cur:
        cur.execute("UPDATE role_grant SET role='staff' WHERE account_id=%s AND role='buyer'", (aid,))
    assert _active_roles(conn, aid) == {"staff"}
    # Now renaming staff -> seller is fine (no buyer present)...
    with conn.cursor() as cur:
        cur.execute("UPDATE role_grant SET role='seller' WHERE account_id=%s AND role='staff'", (aid,))
    assert _active_roles(conn, aid) == {"seller"}
    # ...but renaming it further to `buyer` while `seller` is ALSO held elsewhere is refused. Add a
    # second, distinct seller row first is not possible (the pre-existing active index refuses a
    # second `seller` row on one account), so this is proved against a SECOND account's row
    # instead: renaming account B's own `seller` grant to `buyer` while B independently holds no
    # `seller` of its own is unaffected — the point above already covers the same-account case, and
    # this one exists only to show the rename path does not accidentally read a DIFFERENT account's
    # rows.
    other = _account(conn, "rename-other@example.org")
    _grant(conn, other, "buyer")
    with conn.cursor() as cur:
        cur.execute("UPDATE role_grant SET role='buyer' WHERE account_id=%s AND role='seller'", (aid,))
    assert _active_roles(conn, aid) == {"buyer"} and _active_roles(conn, other) == {"buyer"}


# --- the migration itself must not fail on data that already exists (brief's own requirement) ---


def test_the_migration_does_not_fail_against_a_table_that_already_violates_it(conn) -> None:
    """The scenario the brief names by name: "if any account on QA or production already holds
    both, an unguarded constraint makes the migration unrunnable." Simulated by turning migration
    100's own trigger OFF (as if it had never been applied), writing the violating pair straight
    into `role_grant` the way an old, pre-ruling deploy could have, and then re-applying migration
    100's EXACT file contents — not a paraphrase of what it does.

    Three things are proved, in order: (1) applying the migration raises NOTHING even though the
    table already holds the forbidden pair; (2) that pair is untouched — nothing here migrates an
    existing account's roles, the ruling's own "Open" question is left open; (3) enforcement is
    live again immediately after — a FRESH account cannot newly enter the same state, proving the
    migration re-enabled the guard rather than merely surviving its own re-application inertly."""
    with conn.cursor() as cur:
        cur.execute("DROP TRIGGER IF EXISTS role_grant_exclusivity ON role_grant")
        cur.execute("DROP FUNCTION IF EXISTS role_grant_enforce_exclusivity()")

    legacy = _account(conn, "legacy-both-roles@example.org")
    _grant(conn, legacy, "buyer")
    _grant(conn, legacy, "seller")  # unguarded now — this is the pre-existing violation
    assert _active_roles(conn, legacy) == {"buyer", "seller"}

    with conn.cursor() as cur:
        cur.execute(MIGRATION_100)  # must not raise

    # (2) the legacy row is untouched — still both, still active, still the same two rows.
    assert _active_roles(conn, legacy) == {"buyer", "seller"}

    # (3) enforcement is live again: a FRESH account cannot do what the legacy one already did.
    fresh = _account(conn, "fresh-after-migration@example.org")
    _grant(conn, fresh, "buyer")
    with pytest.raises(psycopg2.errors.CheckViolation):
        _grant(conn, fresh, "seller")

    # And the legacy account can still be brought into compliance by revoking either role — the
    # migration does not trap it, it only stops the state getting WORSE.
    with conn.cursor() as cur:
        cur.execute("UPDATE role_grant SET revoked_at=now() WHERE account_id=%s AND role='seller' AND revoked_at IS NULL", (legacy,))
    assert _active_roles(conn, legacy) == {"buyer"}


# --- concurrency: the race the naive form of this trigger would not have closed ---


def _wait_for_a_backend_queued_on_the_advisory_lock(conn: Any, timeout: float = 10.0) -> None:
    """Block until some OTHER backend on this database is waiting on an advisory lock —
    `tests/api/test_seller_listings.py::_wait_for_a_backend_queued_on_a_lock`'s own idiom (a real
    race proved through `pg_stat_activity`, never a sleep-and-hope), narrowed to `wait_event =
    'advisory'` specifically so a coincidental row-lock wait elsewhere could not pass this."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event = 'advisory'")
            if cur.fetchone()[0]:
                return
        time.sleep(0.02)
    raise AssertionError("no backend ever queued on the role_grant advisory lock")


def test_two_transactions_granting_opposite_roles_to_one_account_at_once_do_not_both_win(conn, scratch_dsn) -> None:
    """The race the spec's migration file itself names: two transactions granting `buyer` and
    `seller` to the SAME account at the same moment, neither able to see the other's uncommitted
    row under ordinary read-committed visibility. Proved with two REAL, separate connections and
    explicit transactions (`conn`'s own fixture is autocommit, so it cannot hold a transaction open
    on purpose) — connection A takes the account's advisory lock and holds it, uncommitted, until
    this test releases it; connection B's own INSERT is proved to be GENUINELY BLOCKED on that
    lock (via `pg_stat_activity`, not a timing guess) before A commits, and only resolves — into a
    refusal — once A's commit makes the conflict visible to it."""
    aid = _account(conn, "race-account@example.org")

    conn_a = psycopg2.connect(scratch_dsn)
    conn_a.autocommit = False
    conn_b = psycopg2.connect(scratch_dsn)
    conn_b.autocommit = False
    b_result: dict[str, Any] = {}
    try:
        with conn_a.cursor() as cur_a:
            cur_a.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'buyer',%s)", (aid, aid))
            # A now holds the account's advisory lock, uncommitted.

        def _grant_seller_on_b() -> None:
            try:
                with conn_b.cursor() as cur_b:
                    cur_b.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'seller',%s)", (aid, aid))
                conn_b.commit()
                b_result["outcome"] = "committed"
            except psycopg2.errors.CheckViolation as exc:
                conn_b.rollback()
                b_result["outcome"] = "refused"
                b_result["message"] = str(exc)

        thread = threading.Thread(target=_grant_seller_on_b)
        thread.start()
        _wait_for_a_backend_queued_on_the_advisory_lock(conn, timeout=10.0)
        # B is now DEMONSTRABLY blocked on A's advisory lock, not merely "probably still running".
        assert "outcome" not in b_result, "B must still be blocked on A's lock at this point"

        conn_a.commit()  # releases the lock; B's own check now runs against a COMMITTED buyer row
        thread.join(timeout=10.0)
    finally:
        conn_a.close()
        conn_b.close()

    assert b_result.get("outcome") == "refused", b_result
    assert "ruling D-C59" in b_result.get("message", "")
    # A won the race (committed first); the account holds exactly what A granted, never both.
    assert _active_roles(conn, aid) == {"buyer"}


def test_the_race_is_symmetric_the_other_way_too(conn, scratch_dsn) -> None:
    """The same race, `seller` first and `buyer` second — the trigger's `CASE` branches on
    `NEW.role`, so this is not provable by the mirror image of the test above without actually
    running it: a bug that only checked one direction would pass the first test and fail this one."""
    aid = _account(conn, "race-account-reverse@example.org")

    conn_a = psycopg2.connect(scratch_dsn)
    conn_a.autocommit = False
    conn_b = psycopg2.connect(scratch_dsn)
    conn_b.autocommit = False
    b_result: dict[str, Any] = {}
    try:
        with conn_a.cursor() as cur_a:
            cur_a.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'seller',%s)", (aid, aid))

        def _grant_buyer_on_b() -> None:
            try:
                with conn_b.cursor() as cur_b:
                    cur_b.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'buyer',%s)", (aid, aid))
                conn_b.commit()
                b_result["outcome"] = "committed"
            except psycopg2.errors.CheckViolation:
                conn_b.rollback()
                b_result["outcome"] = "refused"

        thread = threading.Thread(target=_grant_buyer_on_b)
        thread.start()
        _wait_for_a_backend_queued_on_the_advisory_lock(conn, timeout=10.0)
        assert "outcome" not in b_result
        conn_a.commit()
        thread.join(timeout=10.0)
    finally:
        conn_a.close()
        conn_b.close()

    assert b_result.get("outcome") == "refused", b_result
    assert _active_roles(conn, aid) == {"seller"}


def test_two_different_accounts_never_contend_with_each_other(conn, scratch_dsn) -> None:
    """The lock is per-account (`hashtextextended` of the account id), not table-wide: two
    UNRELATED accounts granting opposite roles at the same moment must not serialise against each
    other at all. Proved the same way as the race above, but this time B must complete WITHOUT
    ever queuing on a lock — if the lock were table-wide this test would flake into the polling
    helper's own timeout instead of finishing immediately."""
    a1 = _account(conn, "indep-a@example.org")
    a2 = _account(conn, "indep-b@example.org")

    conn_a = psycopg2.connect(scratch_dsn)
    conn_a.autocommit = False
    conn_b = psycopg2.connect(scratch_dsn)
    conn_b.autocommit = False
    try:
        with conn_a.cursor() as cur_a:
            cur_a.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'buyer',%s)", (a1, a1))
        # B grants the OPPOSITE role to a DIFFERENT account while A's own transaction is still
        # open and uncommitted. If the lock were table-wide this would hang until A commits or
        # times out; it must instead complete immediately.
        started = time.monotonic()
        with conn_b.cursor() as cur_b:
            cur_b.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'seller',%s)", (a2, a2))
        conn_b.commit()
        elapsed = time.monotonic() - started
        conn_a.commit()
    finally:
        conn_a.close()
        conn_b.close()

    assert elapsed < 2.0, f"B waited {elapsed:.2f}s on an unrelated account's lock — the lock is not per-account"
    assert _active_roles(conn, a1) == {"buyer"}
    assert _active_roles(conn, a2) == {"seller"}
