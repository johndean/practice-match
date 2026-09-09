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
CURATION = PHOTOS / "curation.json"
# Deliberately BELOW what the per-file ceiling would allow (108 x 250 KB is 26 MB): the committed
# set is 2.3 MB since A-L10 (73 files, was 108/4.0 MB), so 18 MB stays a real guard against a
# runaway rather than a restatement of MAX_BYTES.
TOTAL_CEILING_BYTES = 18 * 1024 * 1024
MAX_BYTES = 250 * 1024
MAX_PHOTOS = 6   # the design renders six photo slots per practice (A-L9); more can never be shown


def inventory() -> dict[str, list[dict[str, object]]]:
    return json.loads(INDEX.read_text(encoding="utf-8"))["hospitals"]


def curation() -> dict[str, dict[str, object]]:
    """The content-verified map (A-L10), without its `_comment`. This module reads it as DATA the
    committed tree must agree with — the map is what a human verified, the tree is what a script
    produced from it, and this file is where the two are made to match."""
    loaded = json.loads(CURATION.read_text(encoding="utf-8"))
    return {slug: slots for slug, slots in loaded.items() if not slug.startswith("_")}


def seed_slugs() -> list[str]:
    data = json.loads((ROOT / "seeds" / "hospitals.json").read_text(encoding="utf-8"))
    return [str(h["slug"]) for h in data["hospitals"]]


def test_every_seeded_hospital_has_photographs() -> None:
    """Review i4: since A-L10 an ENTRY is not a photograph — six nulls would satisfy a count. Every
    seeded hospital must carry at least one real one, or its card and its detail page are empty."""
    inv = inventory()
    for slug in seed_slugs():
        assert slug in inv and 1 <= len(inv[slug]) <= MAX_PHOTOS, slug
        assert any(e["file"] is not None for e in inv[slug]), f"{slug} carries no photograph at all"


def test_every_seeded_hospital_carries_all_six_of_the_designs_photo_slots() -> None:
    """A-L9 (John, 2026-09-09: "the seed phase failed to upload ALL the images"). The detail page
    renders six captioned slots per practice, so the inventory carries an entry for every one —
    a photograph or, since A-L10, an explicit empty. A hospital with fewer than six ENTRIES means
    the pipeline dropped a slot again, which is exactly what `[:4]` did."""
    inv = inventory()
    for slug in seed_slugs():
        assert len(inv[slug]) == MAX_PHOTOS, (slug, len(inv[slug]))
        slots = [e["slot"] for e in inv[slug]]
        assert slots[0] == "exterior", (slug, slots)
        assert len(set(slots)) == MAX_PHOTOS, (slug, slots)


def test_the_inventory_is_the_curation_slot_for_slot() -> None:
    """A-L10 (John, 2026-09-09: "match the description"). The design's caption is fixed per slot,
    so the ONLY thing that makes a caption true is the photograph at that POSITION showing that
    subject. The controller verified that by looking at every source image; this asserts the
    committed tree is exactly what he verified — same slots in the same order, the same source
    file in each, and an empty where he found nothing truthful."""
    inv = inventory()
    cur = curation()
    assert set(cur) == set(seed_slugs()), "the curation must name every seeded hospital and no other"
    for slug, slots in cur.items():
        assert [e["slot"] for e in inv[slug]] == list(slots), slug
        assert [e["source"] for e in inv[slug]] == list(slots.values()), slug


def test_a_curated_photograph_sits_at_its_slots_own_position() -> None:
    """`p.photos[i]` fills the design's slot `i` (A12.2), so slot `k` is `<k>.webp` and an empty
    slot leaves a GAP in the numbering rather than pulling the next photograph forward."""
    for slug, entries in inventory().items():
        for position, entry in enumerate(entries, start=1):
            expected = None if entry["source"] is None else f"{position}.webp"
            assert entry["file"] == expected, (slug, position, entry["file"])


def test_the_committed_set_fills_seventy_three_of_the_hundred_and_eight_slots() -> None:
    """The measured outcome of A-L10, pinned: 73 slots carry a content-verified photograph and 35
    stay empty, where the design renders its own placeholder (absent beats faked). Four hospitals
    have nothing but an exterior — their interiors exist only as collage fragments or mislabeled
    exteriors — and John owes clean images for them; the plan record says so, and this test is
    what will notice when they arrive."""
    inv = inventory()
    filled = [e for entries in inv.values() for e in entries if e["file"] is not None]
    assert (len(filled), sum(len(e) for e in inv.values())) == (73, 108)
    exterior_only = sorted(
        slug for slug, entries in inv.items()
        if [e["slot"] for e in entries if e["file"] is not None] == ["exterior"]
    )
    assert exterior_only == [
        "1111_pet_hospital", "ghi_veterinary_hospital", "pqr_veterinary_hospital",
        "stu_veterinary_specialist_center",
    ]


def test_the_inventory_names_no_hospital_that_is_not_seeded() -> None:
    assert set(inventory()) == set(seed_slugs())


def test_every_committed_file_matches_its_recorded_hash_and_size() -> None:
    for slug, entries in inventory().items():
        for entry in entries:
            if entry["file"] is None:
                continue
            path = PHOTOS / slug / str(entry["file"])
            data = path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"], path
            assert len(data) == entry["bytes"] == path.stat().st_size, path
            assert len(data) <= MAX_BYTES, (path, len(data))


def test_the_tree_holds_nothing_the_inventory_does_not_name() -> None:
    on_disk = {f"{p.parent.name}/{p.name}" for p in PHOTOS.rglob("*.webp")}
    named = {f"{slug}/{e['file']}" for slug, entries in inventory().items()
             for e in entries if e["file"] is not None}
    assert on_disk == named


def test_every_committed_photograph_has_a_caption_and_a_source() -> None:
    """What each file actually shows and which of the design's six photo slots it was selected
    for (pre-flight I2; the slot since A-L9). The caption the buyer reads is the design's own,
    fixed per slot — `slot` is what makes it true of the photograph underneath it."""
    for slug, entries in inventory().items():
        for entry in entries:
            assert isinstance(entry["slot"], str) and entry["slot"], (slug, entry["file"])
            if entry["file"] is None:
                # An empty slot is a statement, not a photograph (A-L10): no bytes, no caption,
                # no source, and no measured field claiming otherwise.
                assert entry == {"slot": entry["slot"], "file": None, "source": None, "caption": None}, slug
                continue
            assert isinstance(entry["caption"], str) and entry["caption"], (slug, entry["file"])
            assert isinstance(entry["source"], str) and entry["source"], (slug, entry["file"])


def test_files_are_numbered_by_the_slot_they_fill() -> None:
    """Not "from one without gaps" any more (A-L10): the number IS the design's slot position, so
    a hospital whose surgery slot is empty jumps from `4.webp` to `6.webp`.

    Review i4: the expectation is derived from `source`, not from `file`. Deriving it from `file`
    made the null arm say "null where it is null", which is true of any list; from `source` it
    says "a file wherever a photograph was chosen, and nowhere else", which is the invariant. The
    whole slug is compared in one statement, so a shift shows up as the shifted LIST rather than
    one entry at a time the way `test_a_curated_photograph_sits_at_its_slots_own_position`
    reports it."""
    for slug, entries in inventory().items():
        assert [e["file"] for e in entries] == [
            None if e["source"] is None else f"{n}.webp" for n, e in enumerate(entries, start=1)
        ], slug


def test_the_committed_set_stays_under_the_size_ceiling() -> None:
    total = sum(p.stat().st_size for p in PHOTOS.rglob("*.webp"))
    assert total <= TOTAL_CEILING_BYTES, f"{total / 1024 / 1024:.1f} MB committed"
