"""`scripts/reprocess_photos.py` — the operator's own in-place re-run (spec 2026-09-09 C.5).

It flags and enqueues, and it does nothing else: a flagged ready row keeps its state and goes on
serving the derivative it has while `media.process_photo` replaces it (D-IDP-16), so this is safe
on a published listing and the tests below say so by asserting the state did not move.

Nothing but counts is printed. A listing id is not a secret, but a script an operator runs against
production is not a place to start printing rows either.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.privacy import PROCESSING_VERSION, record
from scripts import reprocess_photos
from tests.privacy.conftest import make_listing, make_row


@pytest.fixture(autouse=True)
def _published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[UUID, int]]:
    """Every enqueue, recorded rather than sent. The script publishes BY NAME through
    `record.enqueue_processing`, which is what keeps `app.tasks.media` -- and therefore the engines
    -- out of a process that only needs to write a flag."""
    sent: list[tuple[UUID, int]] = []
    monkeypatch.setattr("app.privacy.record.enqueue_processing",
                        lambda asset_id, version: sent.append((asset_id, version)))
    return sent


@pytest.fixture(autouse=True)
def _scratch(conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """`main()` opens its own connection through `app.db.sync_conn()`, which reads
    `settings.database_url` -- the `conn` fixture has already pointed that at the scratch database,
    and this asks for that fixture so the ordering is stated rather than assumed."""


def _status(conn: Any, asset_id: UUID) -> tuple[str, str | None]:
    with conn.cursor() as cur:
        cur.execute("SELECT processing_status, reprocess_reason FROM listing_asset_privacy"
                    " WHERE asset_id = %s", (asset_id,))
        row = cur.fetchone()
        return str(row[0]), row[1]


def test_one_listing_is_flagged_and_enqueued_and_its_rows_do_not_move(
    conn: Any, capsys: Any, _published: list[tuple[UUID, int]]
) -> None:
    listing = make_listing(conn, f"idp-{uuid4().hex[:8]}")
    ready, _ = make_row(conn, listing_id=listing, processing_status="PUBLISHED", buyer_visible=True)
    confirmed, _ = make_row(conn, listing_id=listing, processing_status="SELLER_CONFIRMED",
                            confirmed=True, buyer_visible=True)
    pending, _ = make_row(conn, listing_id=listing, processing_status="UPLOADED")
    elsewhere, _ = make_row(conn, processing_status="PUBLISHED", buyer_visible=True)

    assert reprocess_photos.main(["--listing", str(listing)]) == 0
    assert sorted(a for a, _ in _published) == sorted([ready, confirmed])
    assert {v for _, v in _published} == {PROCESSING_VERSION}
    assert _status(conn, ready) == ("PUBLISHED", "OPERATOR")
    assert _status(conn, confirmed) == ("SELLER_CONFIRMED", "OPERATOR")
    assert _status(conn, pending) == ("UPLOADED", None)          # not ready: the pipeline has it
    assert _status(conn, elsewhere) == ("PUBLISHED", None)       # another listing entirely
    assert capsys.readouterr().out.strip() == "[reprocess_photos] flagged and enqueued 2 photograph(s)"


def test_all_stale_flags_every_ready_row_below_the_current_version(
    conn: Any, capsys: Any, _published: list[tuple[UUID, int]]
) -> None:
    stale, _ = make_row(conn, processing_status="PUBLISHED", processing_version=0, buyer_visible=True)
    current, _ = make_row(conn, processing_status="PUBLISHED", processing_version=PROCESSING_VERSION,
                          buyer_visible=True)
    failed, _ = make_row(conn, processing_status="PROCESSING_FAILED", processing_version=0)

    assert reprocess_photos.main(["--all-stale"]) == 0
    assert [a for a, _ in _published] == [stale]
    assert _status(conn, stale) == ("PUBLISHED", "OPERATOR")
    assert _status(conn, current) == ("PUBLISHED", None)
    assert _status(conn, failed) == ("PROCESSING_FAILED", None)
    assert capsys.readouterr().out.strip() == "[reprocess_photos] flagged and enqueued 1 photograph(s)"


def test_a_listing_with_nothing_ready_prints_a_count_of_zero_and_succeeds(
    conn: Any, capsys: Any, _published: list[tuple[UUID, int]]
) -> None:
    """An operator who runs it twice, or against a listing still being processed, gets a count and
    an exit 0 -- not an error, because nothing went wrong."""
    listing = make_listing(conn, f"idp-{uuid4().hex[:8]}")
    make_row(conn, listing_id=listing, processing_status="UPLOADED")
    assert reprocess_photos.main(["--listing", str(listing)]) == 0
    assert _published == []
    assert capsys.readouterr().out.strip() == "[reprocess_photos] flagged and enqueued 0 photograph(s)"


def test_a_row_already_flagged_is_not_flagged_again(conn: Any, _published: list[tuple[UUID, int]]) -> None:
    """Idempotent, so an operator running it twice does not enqueue two re-runs of one photograph
    and `media.sweep`'s rule (6) is not handed a second subject five minutes later."""
    listing = make_listing(conn, f"idp-{uuid4().hex[:8]}")
    make_row(conn, listing_id=listing, processing_status="PUBLISHED", buyer_visible=True)
    assert reprocess_photos.main(["--listing", str(listing)]) == 0
    assert len(_published) == 1
    assert reprocess_photos.main(["--listing", str(listing)]) == 0
    assert len(_published) == 1


@pytest.mark.parametrize(("argv", "said"), [
    ([], "one of the arguments --listing --all-stale is required"),
    (["--listing", "9f1b6f0e-0000-4000-8000-000000000000", "--all-stale"],
     "argument --all-stale: not allowed with argument --listing"),
])
def test_neither_flag_and_both_flags_are_refused_with_exit_two(
    conn: Any, capsys: Any, argv: list[str], said: str
) -> None:
    """`argparse`'s own mutually-exclusive REQUIRED group: an operator who names no target must not
    silently re-run every photograph in the database, and one who names two has not said which.
    The two refusals carry DIFFERENT sentences and both are read, because "exit 2" alone would pass
    for a script that refused everything."""
    with pytest.raises(SystemExit) as exc:
        reprocess_photos.main(argv)
    assert exc.value.code == 2
    assert said in capsys.readouterr().err


def test_a_listing_that_is_not_a_uuid_is_refused_with_exit_two(conn: Any, capsys: Any) -> None:
    with pytest.raises(SystemExit) as exc:
        reprocess_photos.main(["--listing", "the-cedar-park-one"])
    assert exc.value.code == 2
    assert "invalid UUID value" in capsys.readouterr().err


def test_the_cli_entry_point_runs_as___main__(conn: Any, monkeypatch: pytest.MonkeyPatch,
                                              _published: list[tuple[UUID, int]]) -> None:
    """`if __name__ == "__main__": raise SystemExit(main())` never executes on import, and a
    subprocess's coverage is not reported back to this process -- `tests/test_reset_rate_limits.py`'s
    own pattern."""
    import runpy
    import sys
    from pathlib import Path

    monkeypatch.setattr(sys, "argv", ["reprocess_photos", "--all-stale"])
    root = Path(__file__).resolve().parent.parent.parent
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(root / "scripts" / "reprocess_photos.py"), run_name="__main__")
    assert exc.value.code == 0


def test_the_script_writes_the_privacy_row_through_record_and_never_by_hand() -> None:
    """The one production writer rule (`tests/test_docs.py`'s own pin), stated where the writer
    would be if somebody added one: every transition of the privacy row belongs to
    `app/privacy/record.py`, where it carries its own state predicate. `--all-stale` shares
    `record.flag_stale_version` with the sweeper's rule (5) for exactly that reason."""
    from pathlib import Path

    source = Path(reprocess_photos.__file__).read_text()
    assert "listing_asset_privacy" not in source
    assert "flag_stale" in source and "flag_stale_version" in source


def test_the_flag_is_the_same_statement_the_sweeper_uses(conn: Any) -> None:
    """`--all-stale` and `media.sweep`'s rule (5) are ONE statement with one parameter. Driven,
    not read: the script flags the row OPERATOR, and the sweeper -- whose own reason is VERSION --
    then finds nothing left to flag, which is only true if both are asking the same question."""
    stale, _ = make_row(conn, processing_status="PUBLISHED", processing_version=0, buyer_visible=True)
    assert reprocess_photos.main(["--all-stale"]) == 0
    assert record.flag_stale_version(conn, reason="VERSION") == []
    assert _status(conn, stale) == ("PUBLISHED", "OPERATOR")
