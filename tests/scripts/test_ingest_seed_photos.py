"""`scripts/ingest_seed_photos.py` — a seeded photograph becomes a real listing asset.

The feature this exists for renders an identifiable photograph with its identifying words COVERED,
not hidden: under `NOT_SHOW` `app/privacy/delivery.py::buyer_variant` serves the REDACTED
derivative. A seed photograph is a PATH in `listing.photos` with no asset row and therefore no
derivative, so that arm returns None and the slot renders empty — which is why migration 040's
`NOT_SHOW` default took the demo hospitals' photographs off QA. This script is the "then" in the
spec's own "hidden until then" (§C.10).

It changes NO visibility. `identifiable_content_visibility` is written by exactly one path, the
owner's step-7 PATCH, and once a seed photograph is a processed asset `NOT_SHOW` renders it masked
with no flip at all.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.api.listings import PHOTOS_ROOT

#: Two real photographs from the committed corpus with an EMPTY slot between them (A-L10): the
#: array this script rewrites is POSITIONAL, and a null that moves is a caption describing the
#: wrong picture.
SLUG = "pqr_veterinary_hospital"
ENTRIES: list[str | None] = [f"{SLUG}/1.webp", None, f"{SLUG}/3.webp"]
CAPTIONS: list[str | None] = ["Exterior — front view", None, "Exterior — right sign view"]


def make_seed_listing(conn: Any, *, slug: str | None = None, source: str = "seed",
                      photos: list[str | None] | None = None,
                      captions: list[str | None] | None = None) -> UUID:
    """A listing shaped the way `scripts/seed_listings.py` leaves one: a path per photograph,
    a parallel caption array, and `NOT_SHOW` — migration 040's own default, which is what hid them."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, status,"
            " est, price, zip, sqft, photos, photo_captions, identifiable_content_visibility)"
            " VALUES (%s,'PQR Veterinary Hospital','Austin','TX','Austin','Small animal',"
            "'Austin, TX',%s,'published',1998,100,'78613',4200,%s::jsonb,%s::jsonb,'NOT_SHOW')"
            " RETURNING id",
            (slug or f"ingest-{uuid4().hex[:8]}", source,
             json.dumps(ENTRIES if photos is None else photos),
             json.dumps(CAPTIONS if captions is None else captions)),
        )
        return UUID(str(cur.fetchone()[0]))


def test_a_dry_run_names_every_photograph_it_would_ingest_and_writes_nothing(
    conn: Any, store: Any, capsys: Any
) -> None:
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn, slug="ingest-dry")

    assert ingest_seed_photos.main(["--all", "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert f"{SLUG}/1.webp" in out
    assert f"{SLUG}/3.webp" in out
    assert "would ingest 2 photograph(s) across 1 listing(s)" in out
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM listing_asset WHERE listing_id = %s", (listing,))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT photos FROM listing WHERE id = %s", (listing,))
        assert cur.fetchone()[0] == ENTRIES


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch, conn: Any) -> list[tuple[UUID, int, list[str | None]]]:
    """Every enqueue, recorded rather than published — and, beside it, what a SEPARATE connection
    could see of `listing.photos` at that instant.

    The upload route publishes AFTER its transaction commits (spec C.5 step 0), because a task
    taken by a prefork child before the row exists finds nothing. Recording the committed state at
    publish time is how this suite proves the ordering rather than asserting it in prose."""
    sent: list[tuple[UUID, int, list[str | None]]] = []

    def record_it(asset_id: UUID, version: int) -> None:
        with conn.cursor() as cur:
            cur.execute("SELECT photos FROM listing WHERE photos @> to_jsonb(%s::text)", (str(asset_id),))
            found = cur.fetchone()
        sent.append((asset_id, version, found[0] if found else []))

    monkeypatch.setattr("app.privacy.record.enqueue_processing", record_it)
    return sent



def _script_body() -> str:
    """The script BELOW its own module docstring. Both source pins below read it rather than the
    whole file: the docstring's job is to name the rules and the routes this script must not
    re-implement, and a pin that cannot tell a description from a call would forbid saying so."""
    from pathlib import Path as _Path

    from scripts import ingest_seed_photos

    return _Path(ingest_seed_photos.__file__).read_text().split('"""', 2)[2]


def _photos(conn: Any, listing: UUID) -> list[str | None]:
    with conn.cursor() as cur:
        cur.execute("SELECT photos FROM listing WHERE id = %s", (listing,))
        return list(cur.fetchone()[0])


def _captions(conn: Any, listing: UUID) -> list[str | None]:
    with conn.cursor() as cur:
        cur.execute("SELECT photo_captions FROM listing WHERE id = %s", (listing,))
        return list(cur.fetchone()[0])


def test_each_seed_path_becomes_an_asset_id_at_its_own_position(
    conn: Any, store: Any, enqueued: list[Any]
) -> None:
    """The crux (`app/api/listings.py::_photo_urls`): an entry found in the `visible_photos`
    aggregate is an asset, one that is not is a seed path — so swapping the path for the asset id
    is what moves the photograph onto the supported path.

    POSITION IS THE DESIGN (A12.1-A12.5, A15). The array keeps its length, the empty slot keeps its
    index, and neither photograph moves."""
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn)
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 0

    after = _photos(conn, listing)
    assert len(after) == len(ENTRIES) == 3
    assert after[1] is None, "the empty slot must keep its index"
    assert after[0] != ENTRIES[0] and after[2] != ENTRIES[2]
    assert [UUID(str(after[0])), UUID(str(after[2]))] == [a for a, _, _ in enqueued]
    with conn.cursor() as cur:
        cur.execute("SELECT id::text, name, content_type, kind FROM listing_asset"
                    " WHERE listing_id = %s ORDER BY id", (listing,))
        rows = cur.fetchall()
    assert sorted(r[0] for r in rows) == sorted([str(after[0]), str(after[2])])
    assert {r[1] for r in rows} == {"1.webp", "3.webp"}
    assert {(r[2], r[3]) for r in rows} == {("image/webp", "photo")}


def test_the_caption_travels_onto_the_asset_and_the_positional_array_is_untouched(
    conn: Any, store: Any, enqueued: list[Any]
) -> None:
    """Captions must survive, and their home MOVES with the photograph.

    `app/api/seller_listings.py::photo_tiles` names an asset tile from `listing_asset.caption` with
    no positional fallback, and `PATCH /listings/{id}/photos/{n}` answers `409 STATE` for an entry
    that is no longer a path — so a caption left only in `listing.photo_captions` would be
    unreachable and uneditable from the seller's own wizard. It is written onto the asset AND left
    where it was, because `app/api/listings.py::photo_captions` still reads the array as the buyer
    payload's positional fallback."""
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn)
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 0

    assert _captions(conn, listing) == CAPTIONS, "the positional array is never rewritten"
    after = _photos(conn, listing)
    with conn.cursor() as cur:
        cur.execute("SELECT id::text, caption FROM listing_asset WHERE listing_id = %s", (listing,))
        by_id = dict(cur.fetchall())
    assert by_id[str(after[0])] == CAPTIONS[0]
    assert by_id[str(after[2])] == CAPTIONS[2]


def test_the_sellers_own_words_beat_the_inventorys_and_a_described_by_nobody_photograph_is_null(
    conn: Any, store: Any, enqueued: list[Any]
) -> None:
    """`photo_captions[n]` is what `PATCH .../photos/{n}` writes — the seller's own description —
    so it wins over the committed inventory's. A photograph nobody has described carries NULL, the
    same intent `caption_asset` gives a blank string."""
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn, photos=[f"{SLUG}/1.webp", f"{SLUG}/3.webp"],
                                captions=["What the seller actually wrote", "   "])
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 0

    after = _photos(conn, listing)
    with conn.cursor() as cur:
        cur.execute("SELECT id::text, caption FROM listing_asset WHERE listing_id = %s", (listing,))
        by_id = dict(cur.fetchall())
    assert by_id[str(after[0])] == "What the seller actually wrote"
    # Blank in the column, so the inventory's own caption answers for position 2.
    assert by_id[str(after[1])] == "Exterior — right sign view"


def test_a_caption_column_shorter_than_the_photo_array_falls_back_to_the_inventory(
    conn: Any, store: Any, enqueued: list[Any]
) -> None:
    """`photo_captions` is `NOT NULL DEFAULT '[]'` (migration 090), so a listing seeded before it
    existed — or one written by hand — can be shorter than `photos`. Reading past its end is an
    IndexError, not a fallback."""
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn, photos=[f"{SLUG}/1.webp", f"{SLUG}/3.webp"], captions=[])
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 0

    after = _photos(conn, listing)
    with conn.cursor() as cur:
        cur.execute("SELECT id::text, caption FROM listing_asset WHERE listing_id = %s", (listing,))
        by_id = dict(cur.fetchall())
    assert by_id[str(after[0])] == "Exterior — front view"
    assert by_id[str(after[1])] == "Exterior — right sign view"


def test_an_undescribed_photograph_carries_no_caption_at_all(
    conn: Any, store: Any, enqueued: list[Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Nobody has described it, so nothing is invented for it: NULL, and the wizard's tile falls
    back exactly as it does for a seller's own undescribed upload."""
    from PIL import Image

    from scripts import ingest_seed_photos

    root = tmp_path / "photos"
    (root / "nameless").mkdir(parents=True)
    Image.new("RGB", (8, 8), (10, 20, 30)).save(root / "nameless" / "1.png")
    monkeypatch.setattr("app.api.listings.PHOTOS_ROOT", root)

    listing = make_seed_listing(conn, photos=["nameless/1.png"], captions=[None])
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 0

    with conn.cursor() as cur:
        cur.execute("SELECT caption FROM listing_asset WHERE listing_id = %s", (listing,))
        assert cur.fetchone()[0] is None


def test_both_objects_are_written_at_the_upload_paths_own_keys(
    conn: Any, store: Any, enqueued: list[Any]
) -> None:
    """Three objects per photograph under `listings/{l}/photos/{a}/` is `app/privacy/__init__.py`'s
    layout (spec C.2) and the redacted one is the WORKER's to write. The original is the bytes as
    committed — directive 13, "NEVER overwrite the original" — and `display.webp` is
    `encode_webp`'s own output, which is what `listing_asset.storage_key` points at."""
    from app.privacy import display_key, original_key
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn)
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 0

    asset = UUID(str(_photos(conn, listing)[0]))
    source = (PHOTOS_ROOT / SLUG / "1.webp").read_bytes()
    assert store.get(original_key(listing, asset, ".webp")) == source
    display = store.get(display_key(listing, asset))
    assert display is not None and display != b""
    with conn.cursor() as cur:
        cur.execute("SELECT storage_key, byte_size, sha256 FROM listing_asset WHERE id = %s", (asset,))
        key, size, digest = cur.fetchone()
    assert key == display_key(listing, asset)
    assert size == len(display)
    import hashlib

    assert digest == hashlib.sha256(display).hexdigest()


def test_the_privacy_row_is_written_and_enqueued_only_after_its_transaction_committed(
    conn: Any, store: Any, enqueued: list[Any]
) -> None:
    """`record.insert` in the SAME transaction as the asset row — directive 2's "NO path through
    which an image can bypass privacy processing", at the database — and `enqueue_processing`
    AFTER it, so no worker can be handed an asset id whose row is not there yet."""
    from app.privacy import PROCESSING_VERSION, original_key
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn)
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 0

    asset = UUID(str(_photos(conn, listing)[0]))
    with conn.cursor() as cur:
        cur.execute("SELECT processing_status, processing_version, original_storage_key,"
                    " buyer_visible, seller_confirmed FROM listing_asset_privacy WHERE asset_id = %s",
                    (asset,))
        status, version, key, visible, confirmed = cur.fetchone()
    assert (status, version, key) == ("UPLOADED", PROCESSING_VERSION,
                                      original_key(listing, asset, ".webp"))
    assert (visible, confirmed) == (False, False)
    assert [v for _, v, _ in enqueued] == [PROCESSING_VERSION, PROCESSING_VERSION]
    for asset_id, _, committed in enqueued:
        assert str(asset_id) in committed, "published before its own transaction committed"


def test_a_second_run_creates_nothing(conn: Any, store: Any, enqueued: list[Any], capsys: Any) -> None:
    """Idempotent BY CONSTRUCTION: a converted entry is an asset id, an asset id holds no "/", and
    the scan and the per-listing position list both ask exactly that question. Nothing is keyed on
    a filename or a content hash, so nothing can drift out of agreement with it."""
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn)
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 0
    first = _photos(conn, listing)
    assert len(enqueued) == 2
    capsys.readouterr()

    # The second run does not even find the listing: it carries no path entry any more.
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 5
    assert ingest_seed_photos.main(["--all"]) == 0
    assert _photos(conn, listing) == first
    assert len(enqueued) == 2
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM listing_asset WHERE listing_id = %s", (listing,))
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM listing_asset_privacy WHERE listing_id = %s", (listing,))
        assert cur.fetchone()[0] == 2


def test_a_claimed_listing_is_ingested_because_the_entry_is_a_path_not_because_of_source(
    conn: Any, store: Any, enqueued: list[Any]
) -> None:
    """Spec §C.10 and skeptic finding 8, and migration 040's own predicate: `claim_from_seed` flips
    `source` to `'seller'` on the first seller write of ANY kind, so a demo hospital somebody has
    pressed Edit on is `source = 'seller'` while its photographs are still paths with no
    derivative. Keying on `source = 'seed'` would leave exactly those dark."""
    from scripts import ingest_seed_photos

    claimed = make_seed_listing(conn, source="seller")
    assert ingest_seed_photos.main(["--listing", str(claimed)]) == 0
    assert len(enqueued) == 2
    with conn.cursor() as cur:
        cur.execute("SELECT source FROM listing WHERE id = %s", (claimed,))
        assert cur.fetchone()[0] == "seller", "the script claims nothing and moves no provenance"


def test_the_listings_visibility_is_never_written(conn: Any, store: Any, enqueued: list[Any]) -> None:
    """The hard rule of this task. `identifiable_content_visibility` has exactly one writer, the
    owner's step-7 PATCH, and none of this needs it: once a seed photograph is a processed asset,
    `NOT_SHOW` renders it MASKED rather than missing. Asserted on the row AND on the source, so a
    later edit cannot quietly add one."""
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn)
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 0
    with conn.cursor() as cur:
        cur.execute("SELECT identifiable_content_visibility FROM listing WHERE id = %s", (listing,))
        assert cur.fetchone()[0] == "NOT_SHOW"
    assert "identifiable_content_visibility" not in _script_body(), (
        "the script body must never name the visibility column")


# --- Refusals: a photograph that cannot become an asset keeps its path -----------------------------
#
# Every one of these leaves the ENTRY alone, so the photograph's siblings still convert and a later
# run tries it again — and the run exits 4, so an operator is told rather than left to count rows.

@pytest.fixture
def patched_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Any:
    """A seed photo root of this test's own. `photo_file` reads the module global at call time, so
    the containment rule under test is the real one and only the root moves."""
    root = tmp_path / "photos"
    (root / "fixture").mkdir(parents=True)
    monkeypatch.setattr("app.api.listings.PHOTOS_ROOT", root)
    return root


def test_an_entry_that_escapes_the_seed_photo_root_is_refused_and_keeps_its_place(
    conn: Any, store: Any, enqueued: list[Any], capsys: Any
) -> None:
    """`photo_file`'s own rule, not a second copy of it: the path comes from the DATABASE, so an
    entry resolving outside `PHOTOS_ROOT` is refused. The target is a REAL `.webp` that really
    exists, so the refusal is the containment check and nothing weaker."""
    from scripts import ingest_seed_photos

    escape = "../../../frontend/public/assets/photos/round-rock-exterior-street.webp"
    assert (PHOTOS_ROOT / escape).resolve().is_file(), "the escape target must really exist"
    listing = make_seed_listing(conn, photos=[escape, f"{SLUG}/1.webp"], captions=[None, None])

    assert ingest_seed_photos.main(["--listing", str(listing)]) == 4
    after = _photos(conn, listing)
    assert after[0] == escape, "a refused entry keeps its path and its position"
    assert after[1] != f"{SLUG}/1.webp", "its sibling still converts"
    assert len(enqueued) == 1
    assert "no readable file under the seed photo root" in capsys.readouterr().err


def test_a_suffix_this_pipeline_does_not_take_is_refused(
    conn: Any, store: Any, enqueued: list[Any], patched_root: Any, capsys: Any
) -> None:
    (patched_root / "fixture" / "notes.txt").write_bytes(b"not a photograph")
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn, photos=["fixture/notes.txt"], captions=[None])
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 4
    assert _photos(conn, listing) == ["fixture/notes.txt"]
    assert enqueued == []
    assert "not one of the three photograph types" in capsys.readouterr().err


def test_bytes_that_contradict_the_suffix_are_refused(
    conn: Any, store: Any, enqueued: list[Any], patched_root: Any, capsys: Any
) -> None:
    """`_sniffed_photo`'s magic-byte check (spec C.5 step 0), which the upload route added because
    the Content-Type alone let through "anything Pillow can open, labelled jpeg/png/webp"."""
    (patched_root / "fixture" / "1.webp").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn, photos=["fixture/1.webp"], captions=[None])
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 4
    assert _photos(conn, listing) == ["fixture/1.webp"]
    assert enqueued == []
    assert "not the photograph the suffix claims" in capsys.readouterr().err


def test_an_image_encode_webp_cannot_read_is_refused(
    conn: Any, store: Any, enqueued: list[Any], patched_root: Any, capsys: Any
) -> None:
    """The header says JPEG and the magic bytes agree; Pillow still cannot open it. `encode_webp`
    answers None for that and for an image no quality in its ladder fits, and both are the same
    refusal here."""
    (patched_root / "fixture" / "1.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 64)
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn, photos=["fixture/1.jpg"], captions=[None])
    assert ingest_seed_photos.main(["--listing", str(listing)]) == 4
    assert _photos(conn, listing) == ["fixture/1.jpg"]
    assert enqueued == []
    assert "could not be read as a photograph" in capsys.readouterr().err


def test_a_bucket_outage_stops_the_run_and_keeps_what_already_committed(
    conn: Any, store: Any, enqueued: list[Any], monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """`_put` turns a `ClientError` into the route's own `STORAGE_UNAVAILABLE` refusal. A run that
    meets one stops — the next listing would meet it too — and everything already committed is
    still enqueued, because those photographs really are assets now."""
    from app.api.seller_listings import Refusal
    from scripts import ingest_seed_photos

    first = make_seed_listing(conn, slug="ingest-outage-a")
    second = make_seed_listing(conn, slug="ingest-outage-b")
    assert ingest_seed_photos.main(["--listing", str(first)]) == 0
    assert len(enqueued) == 2

    def refuse(store: Any, key: str, data: bytes, content_type: str) -> None:
        raise Refusal("STORAGE_UNAVAILABLE", "Object storage is unavailable; try again.", 503)

    monkeypatch.setattr("app.api.seller_listings._put", refuse)
    assert ingest_seed_photos.main(["--all"]) == 4
    assert _photos(conn, second) == ENTRIES, "the refused listing's transaction rolled back whole"
    assert len(enqueued) == 2
    assert "object storage refused the write (STORAGE_UNAVAILABLE)" in capsys.readouterr().err


# --- The operator's own controls ------------------------------------------------------------------

def test_limit_is_the_staged_rollout_lever_and_stops_mid_run(
    conn: Any, store: Any, enqueued: list[Any]
) -> None:
    """313 photographs is real money and a real rate limit, so the lever is "do a few first". The
    budget is spent across listings, not per listing, and a listing it runs out inside still
    commits what it did."""
    from scripts import ingest_seed_photos

    first = make_seed_listing(conn, slug="ingest-limit-a")
    second = make_seed_listing(conn, slug="ingest-limit-b")
    assert ingest_seed_photos.main(["--all", "--limit", "3"]) == 0

    converted = [e for e in _photos(conn, first) + _photos(conn, second)
                 if e is not None and "/" not in e]
    assert len(converted) == 3
    assert len(enqueued) == 3
    # ...and the fourth is still a path, so the next run picks it up exactly where this one stopped.
    assert ingest_seed_photos.main(["--all"]) == 0
    assert len(enqueued) == 4


def test_a_limit_of_zero_ingests_nothing(conn: Any, store: Any, enqueued: list[Any]) -> None:
    """The degenerate end of the same lever: an operator who wants the scan and none of the cost."""
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn)
    assert ingest_seed_photos.main(["--all", "--limit", "0"]) == 0
    assert _photos(conn, listing) == ENTRIES
    assert enqueued == []


def test_a_dry_run_respects_the_limit_and_names_a_photograph_nobody_described(
    conn: Any, store: Any, capsys: Any
) -> None:
    from scripts import ingest_seed_photos

    make_seed_listing(conn, slug="ingest-dry-limit", captions=[None, None, None])
    assert ingest_seed_photos.main(["--all", "--limit", "1", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would ingest 1 photograph(s)" in out
    assert f"photo 1  {SLUG}/1.webp" in out
    assert f"{SLUG}/3.webp" not in out
    assert "would ingest 1 photograph(s) across 1 listing(s)" in out


def test_a_dry_run_says_no_description_where_nobody_has_written_one(
    conn: Any, store: Any, capsys: Any, patched_root: Any
) -> None:
    from PIL import Image

    from scripts import ingest_seed_photos

    Image.new("RGB", (8, 8), (1, 2, 3)).save(patched_root / "fixture" / "1.png")
    make_seed_listing(conn, photos=["fixture/1.png"], captions=[None])
    assert ingest_seed_photos.main(["--all", "--dry-run"]) == 0
    assert "(no description)" in capsys.readouterr().out


def test_a_listing_id_that_carries_no_seed_photograph_is_exit_five(
    conn: Any, store: Any, capsys: Any
) -> None:
    """A typo, or a listing already ingested. Silence would look like success."""
    from scripts import ingest_seed_photos

    unknown = uuid4()
    assert ingest_seed_photos.main(["--listing", str(unknown)]) == 5
    assert f"{unknown} is not a listing carrying a seeded photograph" in capsys.readouterr().err


def test_all_with_nothing_to_do_succeeds_and_says_so(conn: Any, store: Any, capsys: Any) -> None:
    from scripts import ingest_seed_photos

    assert ingest_seed_photos.main(["--all"]) == 0
    assert "ingested 0 photograph(s) across 0 listing(s); 0 refused" in capsys.readouterr().out


def test_production_is_refused_without_the_flag_and_announced_with_it(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any, enqueued: list[Any]
) -> None:
    """`scripts/seed_listings.py`'s own guard, for its reason and one more: this run writes objects
    to a real bucket and enqueues work that calls a paid vision API."""
    from app.config import settings
    from scripts import ingest_seed_photos

    listing = make_seed_listing(conn)
    monkeypatch.setattr(settings, "environment", "production")
    assert ingest_seed_photos.main(["--all"]) == 2
    assert "refusing to run against production without --production" in capsys.readouterr().err
    assert _photos(conn, listing) == ENTRIES

    assert ingest_seed_photos.main(["--all", "--production", "--dry-run"]) == 0
    assert "running against PRODUCTION" in capsys.readouterr().out


def test_an_unconfigured_object_store_refuses_both_modes_before_anything_is_written(
    conn: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """A DRY RUN refuses too, deliberately: a preview that cannot predict the real run's refusal is
    a preview of the wrong run."""
    from app.config import settings
    from scripts import ingest_seed_photos

    monkeypatch.setattr(settings, "s3_bucket", None)
    listing = make_seed_listing(conn)
    for argv in (["--all"], ["--all", "--dry-run"]):
        assert ingest_seed_photos.main(argv) == 2
        assert "object storage is not configured" in capsys.readouterr().err
    assert _photos(conn, listing) == ENTRIES


def test_neither_target_and_both_targets_are_refused_with_exit_two(capsys: Any) -> None:
    """`reprocess_photos.py`'s own required mutually-exclusive group, and for its reason: an
    operator who names no target must not silently ingest every photograph in the database."""
    from scripts import ingest_seed_photos

    for argv, said in (([], "one of the arguments --listing --all is required"),
                       (["--listing", "9f1b6f0e-0000-4000-8000-000000000000", "--all"],
                        "argument --all: not allowed with argument --listing")):
        with pytest.raises(SystemExit) as exc:
            ingest_seed_photos.main(argv)
        assert exc.value.code == 2
        assert said in capsys.readouterr().err


def test_a_listing_deleted_between_the_scan_and_the_lock_is_simply_skipped(
    conn: Any, store: Any
) -> None:
    """The scan and the per-listing lock are different statements, so a seller's own delete can land
    between them. Nothing to convert and nothing to say."""
    from scripts import ingest_seed_photos

    assert ingest_seed_photos.ingest_listing(conn, store, uuid4(), dry_run=False, budget=None) == ([], 0, 0)


def test_the_cli_entry_point_runs_as___main__(
    conn: Any, store: Any, monkeypatch: pytest.MonkeyPatch, enqueued: list[Any]
) -> None:
    """`if __name__ == "__main__": raise SystemExit(main())` never executes on import, and a
    subprocess's coverage is not reported back — `tests/scripts/test_reprocess_photos.py`'s pattern."""
    import runpy
    import sys as _sys
    from pathlib import Path as _Path

    make_seed_listing(conn)
    monkeypatch.setattr(_sys, "argv", ["ingest_seed_photos", "--all", "--dry-run"])
    root = _Path(__file__).resolve().parent.parent.parent
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(root / "scripts" / "ingest_seed_photos.py"), run_name="__main__")
    assert exc.value.code == 0


# --- The rules this script must not re-implement ---------------------------------------------------

def test_the_script_re_implements_none_of_the_upload_paths_rules() -> None:
    """"The same path a real seller upload takes" is a property of the SOURCE, not a promise in a
    docstring: every derivative, content type, byte size and storage key is produced by the code
    the route already runs. A second copy of any of these is how two paths start disagreeing about
    one photograph — which is the whole reason the seeds were dark in the first place."""

    source = _script_body()
    for forbidden, owner in (
        ("INSERT INTO listing_asset (", "app/api/seller_listings.py::_insert_asset"),
        ("listing_asset_privacy", "app/privacy/record.py"),
        ("store.put", "app/api/seller_listings.py::_put"),
        ("is_relative_to", "app/api/listings.py::photo_file"),
        ("Image.open", "app/media/encode.py::encode_webp"),
        ("listings/", "app/privacy/__init__.py's key layout"),
    ):
        assert forbidden not in source, f"{forbidden!r} belongs to {owner}, not to this script"
    # ...and the calls that PROVE it uses them instead.
    for used in ("photo_file", "_sniffed_photo", "encode_webp", "_insert_asset", "_put",
                 "display_key", "original_key", "privacy_record.insert",
                 "privacy_record.enqueue_processing", "seed_captions"):
        assert used in source, f"{used} is how this script stays on the upload path"


def test_the_declared_content_types_are_the_pipelines_own_three() -> None:
    """Inverted from `PHOTO_EXT` rather than retyped, so a fourth type added there arrives here
    too and a type removed there cannot linger. `.jpeg` is `app/media/encode.py`'s own second
    spelling of the first of them, and is the one addition."""
    from app.media.encode import IMAGE_SUFFIXES
    from app.privacy import PHOTO_EXT
    from scripts import ingest_seed_photos

    resolved = {suffix: ingest_seed_photos.declared_type(f"slug/x{suffix}") for suffix in IMAGE_SUFFIXES}
    assert resolved == {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                        ".webp": "image/webp"}
    assert set(PHOTO_EXT.values()) <= set(IMAGE_SUFFIXES)
    assert ingest_seed_photos.declared_type("slug/x.tiff") is None
    assert ingest_seed_photos.declared_type("slug/X.WEBP") == "image/webp"


def test_seeded_positions_is_the_one_question_this_script_asks() -> None:
    """A path is a seed photograph; an asset id is not; a null slot is neither. Idempotency,
    positional integrity and the scan predicate are all this one rule, so it is asserted directly."""
    from scripts import ingest_seed_photos

    assert ingest_seed_photos.seeded_positions(
        [f"{SLUG}/1.webp", None, "9f1b6f0e-0000-4000-8000-000000000000", f"{SLUG}/3.webp"]
    ) == [1, 4]
    assert ingest_seed_photos.seeded_positions([]) == []
