"""`scripts/confirm_seed_photos.py` -- the demo-only operator bulk confirm (John's ruling,
2026-09-17). It calls `app/privacy/record.py::confirm`, this table's ONE production writer, for
exactly the photographs `scripts/ingest_seed_photos.py` created on one of the 29 seeded hospitals --
never a real seller's own upload, and never a listing outside that closed set, whichever door it is
asked through.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from scripts.confirm_seed_photos import seed_slugs
from tests.privacy.conftest import make_account, make_listing, make_row

#: Two real slugs from the committed file -- never hard-coded literals that could drift out of
#: step with `seeds/hospitals.json`.
SLUGS = seed_slugs()
SLUG_A, SLUG_B = SLUGS[0], SLUGS[1]


def make_ingested_asset(conn: Any, listing_id: UUID, *, name: str = "1.webp",
                        caption: str | None = "Exterior -- front view",
                        status: str = "READY_FOR_REVIEW", ingested: bool = True) -> UUID:
    """One photograph, shaped as `scripts/ingest_seed_photos.py::ingest_photo` leaves it (or, with
    `ingested=False`, as the wizard's own upload route leaves it): a real `listing_asset` row with
    a real `listing_asset_privacy` row in `status`, `make_row`'s own CHECK-respecting shape."""
    asset_id, _ = make_row(conn, listing_id=listing_id, processing_status=status)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE listing_asset SET name = %s, caption = %s, ingested_from_seed = %s WHERE id = %s",
            (name, caption, ingested, asset_id),
        )
    return asset_id


def _privacy_row(conn: Any, asset_id: UUID) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT processing_status, buyer_visible, seller_confirmed, seller_confirmation_account_id,"
            " final_privacy_state, confirmed_sha256, redacted_sha256, seller_confirmed_at"
            " FROM listing_asset_privacy WHERE asset_id = %s",
            (asset_id,),
        )
        row = cur.fetchone()
    return dict(zip(
        ("processing_status", "buyer_visible", "seller_confirmed", "seller_confirmation_account_id",
         "final_privacy_state", "confirmed_sha256", "redacted_sha256", "seller_confirmed_at"),
        row, strict=True,
    ))


def _audit_rows(conn: Any, asset_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT action, reason, actor_id, before, after FROM audit_log"
            " WHERE target_type = 'listing_asset' AND target_id = %s ORDER BY id",
            (str(asset_id),),
        )
        rows = cur.fetchall()
    return [dict(zip(("action", "reason", "actor_id", "before", "after"), r, strict=True)) for r in rows]


def test_seed_slugs_matches_the_committed_file() -> None:
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "seeds" / "hospitals.json").read_text())
    assert seed_slugs() == [h["slug"] for h in data["hospitals"]]
    assert len(seed_slugs()) == 29


def test_a_ready_seed_ingested_photograph_is_confirmed_and_audited(conn: Any) -> None:
    """The happy path, invoked by `--listing`. Every field `confirm` writes, plus the ONE audit row
    Part 2 requires -- naming the operator action and this ruling, not a generic 'confirm'."""
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, seller_id=owner)
    asset_id = make_ingested_asset(conn, listing)

    assert confirm_seed_photos.main(["--listing", str(listing)]) == 0

    row = _privacy_row(conn, asset_id)
    assert row["processing_status"] == "SELLER_CONFIRMED"
    assert row["buyer_visible"] is True
    assert row["seller_confirmed"] is True
    assert row["final_privacy_state"] == "NOT_SHOW"
    assert row["confirmed_sha256"] == row["redacted_sha256"] is not None
    assert row["seller_confirmation_account_id"] == owner

    audits = _audit_rows(conn, asset_id)
    assert len(audits) == 1, "exactly one audit row per confirmation"
    entry = audits[0]
    assert entry["action"] == "listing.privacy"
    assert entry["actor_id"] is None, "a standalone script has no session, seed_persona.py's own shape"
    assert "2026-09-17" in entry["reason"] and "demo-only" in entry["reason"] and "operator" in entry["reason"]
    assert entry["before"] == {"processing_status": "READY_FOR_REVIEW"}
    assert entry["after"] == {"processing_status": "SELLER_CONFIRMED"}


def test_confirming_makes_buyer_variant_serve_the_redacted_derivative(conn: Any) -> None:
    """Part 1's own end-to-end proof, not merely a claim: `app/privacy/record.py::confirm` was
    already this table's ONE production writer for this transition before this task touched
    anything (built by Task P3, never called from any route yet), so nothing needed to be ADDED
    to it -- this pins that it genuinely completes the chain
    `scripts/ingest_seed_photos.py`'s own report left open (limit 2, "ingestion alone does not
    put the photographs back on screen"): before confirmation `buyer_variant` answers None under
    NOT_SHOW; after it, the SAME redacted derivative the pipeline already produced."""
    from app.privacy import record as privacy_record
    from app.privacy.delivery import buyer_variant
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, seller_id=owner)
    asset_id = make_ingested_asset(conn, listing)

    before = privacy_record.read(conn, asset_id)
    assert buyer_variant("NOT_SHOW", before, str(asset_id)) is None, (
        "READY_FOR_REVIEW but not yet confirmed -- must render nothing under NOT_SHOW")

    assert confirm_seed_photos.main(["--listing", str(listing)]) == 0

    after = privacy_record.read(conn, asset_id)
    assert after is not None
    variant = buyer_variant("NOT_SHOW", after, str(asset_id))
    assert variant is not None, "confirmed and buyer_visible -- NOT_SHOW must now serve the redaction"
    assert variant.key == after.redacted_storage_key
    assert variant.sha256 == after.redacted_sha256 == after.confirmed_sha256


def test_a_real_sellers_photograph_on_a_non_seed_listing_is_refused(conn: Any) -> None:
    """Condition 1 alone. A listing outside the 29-hospital set never becomes a candidate under
    `--all`, whatever its photograph's own marker says -- and naming it directly through
    `--listing` is refused outright, exit 5, before any row is even read."""
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    outside = make_listing(conn, f"not-a-seed-{uuid4().hex[:8]}", seller_id=owner)
    # Even a marker of TRUE must not be enough on its own -- proving condition 1 is a real,
    # independently-enforced gate and not merely something that happens to coincide with it.
    asset_id = make_ingested_asset(conn, outside, ingested=True)

    assert confirm_seed_photos.main(["--all"]) == 0
    assert _privacy_row(conn, asset_id)["processing_status"] == "READY_FOR_REVIEW"
    assert _audit_rows(conn, asset_id) == []

    assert confirm_seed_photos.main(["--listing", str(outside)]) == 5
    assert _privacy_row(conn, asset_id)["processing_status"] == "READY_FOR_REVIEW"


def test_a_seed_listings_seller_uploaded_photograph_is_also_refused(conn: Any) -> None:
    """Condition 2 alone, on the RIGHT listing named directly. A demo hospital's own seller upload
    (no `ingested_from_seed`) sits beside a genuinely ingested one; `--listing` targets exactly this
    hospital and still must not touch the sibling that was never this ingestion's own."""
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, seller_id=owner)
    ingested = make_ingested_asset(conn, listing, name="1.webp", ingested=True)
    real_upload = make_ingested_asset(conn, listing, name="seller-added.webp", ingested=False)

    assert confirm_seed_photos.main(["--listing", str(listing)]) == 0

    assert _privacy_row(conn, ingested)["processing_status"] == "SELLER_CONFIRMED"
    assert _privacy_row(conn, real_upload)["processing_status"] == "READY_FOR_REVIEW"
    assert _audit_rows(conn, real_upload) == []


def test_the_dry_run_names_exactly_what_it_would_confirm_and_writes_nothing(
    conn: Any, capsys: Any
) -> None:
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, seller_id=owner)
    described = make_ingested_asset(conn, listing, name="1.webp", caption="Exterior view")
    undescribed = make_ingested_asset(conn, listing, name="2.webp", caption=None)

    assert confirm_seed_photos.main(["--listing", str(listing), "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert f"would confirm  {described}  1.webp  Exterior view" in out
    assert f"would confirm  {undescribed}  2.webp  (no description)" in out
    assert "would confirm 2 photograph(s) across 1 listing(s)" in out
    for asset_id in (described, undescribed):
        assert _privacy_row(conn, asset_id)["processing_status"] == "READY_FOR_REVIEW"
        assert _audit_rows(conn, asset_id) == []


def test_an_already_confirmed_photograph_is_left_alone(conn: Any, capsys: Any) -> None:
    """Idempotent by construction: an already-`SELLER_CONFIRMED` row is bucketed and reported, never
    re-sent through `confirm` -- so its own `seller_confirmed_at` never moves, unlike a second real
    call to `confirm` (which legitimately re-stamps it)."""
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, seller_id=owner)
    asset_id = make_ingested_asset(conn, listing, status="SELLER_CONFIRMED")
    before = _privacy_row(conn, asset_id)["seller_confirmed_at"]

    assert confirm_seed_photos.main(["--listing", str(listing)]) == 0

    after = _privacy_row(conn, asset_id)["seller_confirmed_at"]
    assert after == before, "an already-confirmed row must not be re-written"
    assert _audit_rows(conn, asset_id) == []
    assert "1 already confirmed" in capsys.readouterr().out


def test_a_not_yet_ready_photograph_is_reported_and_left_alone(conn: Any, capsys: Any) -> None:
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, seller_id=owner)
    asset_id = make_ingested_asset(conn, listing, status="PROCESSING")

    assert confirm_seed_photos.main(["--listing", str(listing)]) == 0

    assert _privacy_row(conn, asset_id)["processing_status"] == "PROCESSING"
    assert _audit_rows(conn, asset_id) == []
    assert "1 not ready" in capsys.readouterr().out


def test_an_unowned_listing_is_skipped_with_a_clear_message(conn: Any, capsys: Any) -> None:
    """No `--owner` was ever assigned (`scripts/seed_listings.py --no-owner`, or a persona absent
    entirely, D25's own recorded case). Confirming on behalf of no account would be a second,
    worse bypass, so this is reported and left alone rather than invented."""
    from scripts import confirm_seed_photos

    listing = make_listing(conn, SLUG_A)  # seller_id defaults to None
    asset_id = make_ingested_asset(conn, listing)

    assert confirm_seed_photos.main(["--listing", str(listing)]) == 0

    assert _privacy_row(conn, asset_id)["processing_status"] == "READY_FOR_REVIEW"
    assert _audit_rows(conn, asset_id) == []
    assert "1 unowned" in capsys.readouterr().out


def test_a_listing_that_is_show_has_nothing_to_confirm(conn: Any, capsys: Any) -> None:
    """Spec C.1 step 2: under SHOW a ready photograph is already buyer-visible with no confirmation
    at all, so a listing whose visibility is not NOT_SHOW is skipped outright."""
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, visibility="SHOW", seller_id=owner)
    asset_id = make_ingested_asset(conn, listing)

    assert confirm_seed_photos.main(["--listing", str(listing)]) == 0

    assert _privacy_row(conn, asset_id)["processing_status"] == "READY_FOR_REVIEW"
    assert "not NOT_SHOW" in capsys.readouterr().out


def test_limit_throttles_within_one_listing(conn: Any) -> None:
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, seller_id=owner)
    first = make_ingested_asset(conn, listing, name="1.webp")
    second = make_ingested_asset(conn, listing, name="2.webp")

    assert confirm_seed_photos.main(["--listing", str(listing), "--limit", "1"]) == 0

    statuses = {first: _privacy_row(conn, first)["processing_status"],
                second: _privacy_row(conn, second)["processing_status"]}
    assert sorted(statuses.values()) == ["READY_FOR_REVIEW", "SELLER_CONFIRMED"], statuses

    # A second run with room left finishes the rest -- the staged-rollout lever, proved end to end.
    assert confirm_seed_photos.main(["--listing", str(listing), "--limit", "5"]) == 0
    assert _privacy_row(conn, first)["processing_status"] == "SELLER_CONFIRMED"
    assert _privacy_row(conn, second)["processing_status"] == "SELLER_CONFIRMED"


def test_limit_throttles_across_listings(conn: Any) -> None:
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing_a = make_listing(conn, SLUG_A, seller_id=owner)
    listing_b = make_listing(conn, SLUG_B, seller_id=owner)
    asset_a = make_ingested_asset(conn, listing_a)
    asset_b = make_ingested_asset(conn, listing_b)

    assert confirm_seed_photos.main(["--all", "--limit", "1"]) == 0

    statuses = {asset_a: _privacy_row(conn, asset_a)["processing_status"],
                asset_b: _privacy_row(conn, asset_b)["processing_status"]}
    assert sorted(statuses.values()) == ["READY_FOR_REVIEW", "SELLER_CONFIRMED"], statuses


def test_a_limit_of_zero_confirms_nothing(conn: Any, capsys: Any) -> None:
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, seller_id=owner)
    asset_id = make_ingested_asset(conn, listing)

    assert confirm_seed_photos.main(["--all", "--limit", "0"]) == 0

    assert _privacy_row(conn, asset_id)["processing_status"] == "READY_FOR_REVIEW"
    assert "confirmed 0 photograph(s)" in capsys.readouterr().out


def test_a_listing_outside_the_29_hospital_set_is_refused_via___listing(
    conn: Any, capsys: Any
) -> None:
    """A typo, or a listing that has genuinely never been one of the demo hospitals. Silence would
    look like success."""
    from scripts import confirm_seed_photos

    unknown = uuid4()
    assert confirm_seed_photos.main(["--listing", str(unknown)]) == 5
    assert f"{unknown} is not one of the seeded demo hospitals" in capsys.readouterr().err


def test_all_with_nothing_to_do_succeeds_and_says_so(conn: Any, capsys: Any) -> None:
    from scripts import confirm_seed_photos

    assert confirm_seed_photos.main(["--all"]) == 0
    assert "confirmed 0 photograph(s) across 0 listing(s)" in capsys.readouterr().out


def test_production_is_refused_without_the_flag_and_announced_with_it(
    conn: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    from app.config import settings
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, seller_id=owner)
    asset_id = make_ingested_asset(conn, listing)
    monkeypatch.setattr(settings, "environment", "production")

    assert confirm_seed_photos.main(["--all"]) == 2
    assert "refusing to run against production without --production" in capsys.readouterr().err
    assert _privacy_row(conn, asset_id)["processing_status"] == "READY_FOR_REVIEW"

    assert confirm_seed_photos.main(["--all", "--production", "--dry-run"]) == 0
    assert "running against PRODUCTION" in capsys.readouterr().out


def test_a_raced_confirmation_is_not_counted_or_audited(
    conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another writer moved the row between this script's own SELECT and its call to `confirm`
    (a real seller's own confirm, or a mask edit) -- `confirm` answers False, and this script must
    neither claim the confirmation happened nor write an audit row saying it did."""
    from app.privacy import record as privacy_record
    from scripts import confirm_seed_photos

    owner = make_account(conn)
    listing = make_listing(conn, SLUG_A, seller_id=owner)
    asset_id = make_ingested_asset(conn, listing)
    monkeypatch.setattr(privacy_record, "confirm", lambda *a, **k: False)

    assert confirm_seed_photos.main(["--listing", str(listing)]) == 0

    assert _audit_rows(conn, asset_id) == []


def test_the_cli_entry_point_runs_as___main__(conn: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """`if __name__ == "__main__": raise SystemExit(main())` never executes on import --
    `tests/scripts/test_ingest_seed_photos.py`'s own pattern."""
    import runpy
    import sys as _sys
    from pathlib import Path as _Path

    monkeypatch.setattr(_sys, "argv", ["confirm_seed_photos", "--all", "--dry-run"])
    root = _Path(__file__).resolve().parent.parent.parent
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(root / "scripts" / "confirm_seed_photos.py"), run_name="__main__")
    assert exc.value.code == 0


def test_neither_target_and_both_targets_are_refused_with_exit_two(capsys: Any) -> None:
    from scripts import confirm_seed_photos

    for argv, said in (([], "one of the arguments --listing --all is required"),
                       (["--listing", "9f1b6f0e-0000-4000-8000-000000000000", "--all"],
                        "argument --all: not allowed with argument --listing")):
        with pytest.raises(SystemExit) as exc:
            confirm_seed_photos.main(argv)
        assert exc.value.code == 2
        assert said in capsys.readouterr().err
