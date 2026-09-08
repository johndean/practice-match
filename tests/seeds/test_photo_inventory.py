"""The committed photographs match their inventory and stay inside the size ceiling (D3).

This is the gate that catches a hand-edited WebP, a file added without re-running the pipeline
and an inventory that drifted from the tree. It reads only what is committed — no source
folders, no network, no Pillow re-encode.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PHOTOS = ROOT / "seeds" / "hospitals" / "photos"
INDEX = PHOTOS / "index.json"
TOTAL_CEILING_BYTES = 18 * 1024 * 1024  # 108 files x 250 KB is 26 MB worst case; the real set is a fifth of that
MAX_BYTES = 250 * 1024
MAX_PHOTOS = 6   # the design renders six photo slots per practice (A-L9); more can never be shown


def inventory() -> dict[str, list[dict[str, object]]]:
    return json.loads(INDEX.read_text(encoding="utf-8"))["hospitals"]


def seed_slugs() -> list[str]:
    data = json.loads((ROOT / "seeds" / "hospitals.json").read_text(encoding="utf-8"))
    return [str(h["slug"]) for h in data["hospitals"]]


def test_every_seeded_hospital_has_photographs() -> None:
    inv = inventory()
    for slug in seed_slugs():
        assert slug in inv and 1 <= len(inv[slug]) <= MAX_PHOTOS, slug


def test_every_seeded_hospital_fills_all_six_of_the_designs_photo_slots() -> None:
    """A-L9 (John, 2026-09-09: "the seed phase failed to upload ALL the images"). The detail page
    renders six captioned slots per practice and every source folder holds at least eight
    photographs, so a hospital carrying fewer than six means the pipeline dropped some again —
    which is exactly what `[:4]` did, leaving 70 exteriors and 2 interiors across the eighteen."""
    inv = inventory()
    for slug in seed_slugs():
        assert len(inv[slug]) == MAX_PHOTOS, (slug, len(inv[slug]))
        slots = [e["slot"] for e in inv[slug]]
        assert slots[0] == "exterior", (slug, slots)
        assert len(set(slots)) == MAX_PHOTOS, (slug, slots)


def test_the_inventory_names_no_hospital_that_is_not_seeded() -> None:
    assert set(inventory()) == set(seed_slugs())


def test_every_committed_file_matches_its_recorded_hash_and_size() -> None:
    for slug, entries in inventory().items():
        for entry in entries:
            path = PHOTOS / slug / str(entry["file"])
            data = path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"], path
            assert len(data) == entry["bytes"] == path.stat().st_size, path
            assert len(data) <= MAX_BYTES, (path, len(data))


def test_the_tree_holds_nothing_the_inventory_does_not_name() -> None:
    on_disk = {f"{p.parent.name}/{p.name}" for p in PHOTOS.rglob("*.webp")}
    named = {f"{slug}/{e['file']}" for slug, entries in inventory().items() for e in entries}
    assert on_disk == named


def test_every_committed_photograph_has_a_caption_and_a_source() -> None:
    """What each file actually shows and which of the design's six photo slots it was selected
    for (pre-flight I2; the slot since A-L9). The caption the buyer reads is the design's own,
    fixed per slot — `slot` is what makes it true of the photograph underneath it."""
    for slug, entries in inventory().items():
        for entry in entries:
            assert isinstance(entry["caption"], str) and entry["caption"], (slug, entry["file"])
            assert isinstance(entry["source"], str) and entry["source"], (slug, entry["file"])
            assert isinstance(entry["slot"], str) and entry["slot"], (slug, entry["file"])


def test_files_are_numbered_from_one_without_gaps() -> None:
    for slug, entries in inventory().items():
        assert [e["file"] for e in entries] == [f"{n}.webp" for n in range(1, len(entries) + 1)], slug


def test_the_committed_set_stays_under_the_size_ceiling() -> None:
    total = sum(p.stat().st_size for p in PHOTOS.rglob("*.webp"))
    assert total <= TOTAL_CEILING_BYTES, f"{total / 1024 / 1024:.1f} MB committed"
