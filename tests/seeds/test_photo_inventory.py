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
# Deliberately BELOW what the per-file ceiling would allow (313 x 250 KB is 76 MB): the committed
# set is 13.8 MB since Task SD1 (313 files — 195 for John's eighteen of 2026-09-06, where A-L10
# kept 73 and A-L9 108, and 118 of the 119 in his eleven Dallas folders), so 24 MB stays a real
# guard against a runaway rather than a restatement of MAX_BYTES.
TOTAL_CEILING_BYTES = 24 * 1024 * 1024
MAX_BYTES = 250 * 1024
# The design renders six CAPTIONED photo slots per practice (A-L9). Since A-L11 that is not a cap:
# amendment A15.3 renders a tile of its own for every photograph beyond the sixth.
SLOT_COUNT = 6


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
    seeded hospital must carry at least one real one, or its card and its detail page are empty.
    A-L11 drops the upper bound: a folder's photographs are no longer capped at six."""
    inv = inventory()
    for slug in seed_slugs():
        assert slug in inv and len(inv[slug]) >= SLOT_COUNT, slug
        assert any(e["file"] is not None for e in inv[slug]), f"{slug} carries no photograph at all"


def test_every_seeded_hospital_carries_all_six_of_the_designs_photo_slots() -> None:
    """A-L9 (John, 2026-09-09: "the seed phase failed to upload ALL the images"). The detail page
    renders six captioned slots per practice, so the inventory's FIRST SIX entries are those six
    slots, in the practice type's own order. A hospital with fewer than six means the pipeline
    dropped a slot again, which is exactly what `[:4]` did.

    A-L11: everything after the sixth is a photograph with NO slot — the design has no caption
    for it, so it carries the supplier's own description instead (amendment A15.3)."""
    inv = inventory()
    for slug in seed_slugs():
        assert len(inv[slug]) >= SLOT_COUNT, (slug, len(inv[slug]))
        slots = [e["slot"] for e in inv[slug][:SLOT_COUNT]]
        assert slots[0] == "exterior", (slug, slots)
        assert len(set(slots)) == SLOT_COUNT, (slug, slots)
        assert all(e["slot"] is None for e in inv[slug][SLOT_COUNT:]), slug


def test_the_inventory_is_the_curation_slot_for_slot() -> None:
    """A-L10 (John, 2026-09-09: "match the description"). The design's caption is fixed per slot,
    so the ONLY thing that makes a caption true is the photograph at that POSITION showing that
    subject. The controller verified that by looking at every source image; this asserts the
    committed tree is exactly what he verified — the same slots in the same order, and the
    photograph he named in each of them.

    A-L11 narrows the claim to the slots the map FILLS: a slot it left `null` now holds one of the
    folder's other photographs (never dropped, and honestly captioned by the amendment's own
    fallback) rather than nothing, so this can no longer be an equality over the whole list."""
    inv = inventory()
    cur = curation()
    assert set(cur) == set(seed_slugs()), "the curation must name every seeded hospital and no other"
    for slug, slots in cur.items():
        assert [e["slot"] for e in inv[slug][:SLOT_COUNT]] == list(slots), slug
        named = [(n, name) for n, name in enumerate(slots.values()) if name is not None]
        assert [(n, inv[slug][n]["source"]) for n, _ in named] == named, slug


def test_a_curated_photograph_sits_at_its_slots_own_position() -> None:
    """`p.photos[i]` fills the design's slot `i` (A12.2), so slot `k` is `<k>.webp` and an empty
    slot leaves a GAP in the numbering rather than pulling the next photograph forward."""
    for slug, entries in inventory().items():
        for position, entry in enumerate(entries, start=1):
            expected = None if entry["source"] is None else f"{position}.webp"
            assert entry["file"] == expected, (slug, position, entry["file"])


# Every photograph in John's eighteen source folders, counted by folder. A-L9 kept 108 of them
# (six per hospital) and A-L10 kept 73; A-L11 keeps all 195. Pinned per hospital rather than as a
# total, because the total is what hid the loss John found: `def_veterinary_hospital` went from 9
# to 3 and the sum still looked plausible.
PHOTOGRAPHS_PER_HOSPITAL = {
    "1111_pet_hospital": 10,
    "123_route66": 10,
    "2222_pet_hospital": 12,
    "3333_santa_barbara_veterinary_specialist_hospital": 11,
    "4444_denver_veterinary_specialist_hospital": 11,
    "456_pet_er": 11,
    "5555_new_york_veterinary_specialist_hospital": 12,
    "6666_dallas_veterinary_specialist_hospital": 10,
    "789_lake_tahoe_pet_hospital": 10,
    "abc_animal_hospital": 18,
    "def_veterinary_hospital": 9,
    "ghi_veterinary_hospital": 11,
    "jkl_animal_hospital": 10,
    "mno_pet_hospital": 11,
    "pqr_veterinary_hospital": 8,
    "stu_veterinary_specialist_center": 10,
    "vwx_veterinary_hospital": 10,
    "yz_rural_animal_hospital": 11,
    # Task SD1: John's eleven Dallas folders, 119 images. `alpha` shows 11 of its 12 — the
    # twelfth is refused, see `test_the_refused_photograph_is_nowhere_in_the_committed_tree`.
    "alpha_dallas_veterinary_specialist_hospital": 11,
    "beta_dallas_veterinary_hospital": 11,
    "charlie_dallas_animal_hospital": 11,
    "delta_dallas_animal_er_hospital": 11,
    "echo_dallas_animal_hospital": 11,
    "foxtrot_dallas_animal_hospital": 10,
    "hotel_dallas_animal_hospital": 10,
    "indigo_dallas_animal_hospital": 10,
    "juliet_dallas_animal_hospital": 11,
    "kilo_dallas_fort_worth_veterinary_hospital": 11,
    "lima_dallas_fort_worth_veterinary_hospital": 11,
}


def test_the_committed_set_is_every_photograph_john_supplied() -> None:
    """The measured outcome of A-L11 (John, 2026-09-09: "render ALL images"), pinned: 195 files,
    one per source image, and NOT ONE empty slot — every folder holds more than the design's six.
    A-L10's 73-of-108 is superseded: the photographs with no by-eye match to one of the six fixed
    captions were dropped, which is the failure this hotfix exists to end."""
    inv = inventory()
    assert {slug: len(entries) for slug, entries in inv.items()} == PHOTOGRAPHS_PER_HOSPITAL
    filled = [e for entries in inv.values() for e in entries if e["file"] is not None]
    assert (len(filled), sum(len(e) for e in inv.values())) == (313, 313), "a photograph was dropped"
    beyond = [e for entries in inv.values() for e in entries if e["slot"] is None]
    assert len(beyond) == 139, "the photographs past the design's six slots (A15.3 renders each)"


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
    for (pre-flight I2; the slot since A-L9). In one of those six the caption the buyer reads is
    the design's own — `slot` is what makes it true of the photograph underneath it; beyond them
    the design has no caption, `slot` is null, and the CAPTION recorded here is what the buyer
    reads (A-L11, amendment A15.3)."""
    for slug, entries in inventory().items():
        for entry in entries:
            # A-L11 review (m5): `is None or entry["slot"]` was truthiness alone, so any
            # non-empty value — an int, a list — satisfied it. A slot is a NAME or nothing.
            assert entry["slot"] is None or (isinstance(entry["slot"], str) and entry["slot"]), (
                slug, entry["file"]
            )
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


# ======================================================================================
# Task SD1 — John's eleven Dallas folders, their verified descriptions, the flags the content
# verification raised, and the one photograph that was refused.
#
# These filenames (`alpha_dallas_01.png`) describe nothing, so every one of these photographs
# carries a description produced by LOOKING at it. That description is the caption a buyer
# reads (`photo_captions` -> `p.photoCaptions[i]`, amendment A15) — the design's six fixed slot
# captions never speak for one of these, which is what makes the slot map safe even where a
# folder of contact sheets left most slots to the backfill.
# ======================================================================================

DESCRIPTIONS = PHOTOS / "descriptions.json"
DALLAS_SLUGS = frozenset({
    "alpha_dallas_veterinary_specialist_hospital", "beta_dallas_veterinary_hospital",
    "charlie_dallas_animal_hospital", "delta_dallas_animal_er_hospital",
    "echo_dallas_animal_hospital", "indigo_dallas_animal_hospital",
    "foxtrot_dallas_animal_hospital", "hotel_dallas_animal_hospital",
    "juliet_dallas_animal_hospital", "kilo_dallas_fort_worth_veterinary_hospital",
    "lima_dallas_fort_worth_veterinary_hospital",
})
# The one photograph that is NOT encoded, and the rule it fell under. Named here so a re-run of
# the pipeline that quietly encoded it would fail rather than pass.
REFUSED = ("alpha_dallas_veterinary_specialist_hospital", "alpha_dallas_11_individual_images.png")
# What the source folders hold. `alpha` supplied 12; 11 are committed.
DALLAS_SOURCE_IMAGES = 119


def descriptions() -> dict[str, dict[str, dict[str, object]]]:
    loaded = json.loads(DESCRIPTIONS.read_text(encoding="utf-8"))
    return {slug: files for slug, files in loaded.items() if not slug.startswith("_")}


def test_the_descriptions_file_names_the_eleven_and_nobody_else() -> None:
    """Surgical: John's eighteen of 2026-09-06 have no entry here and keep the captions their
    own descriptive filenames give them."""
    assert set(descriptions()) == DALLAS_SLUGS


def test_every_photograph_in_the_eleven_folders_is_accounted_for() -> None:
    """119 supplied, 118 encoded, 1 refused — and each of the 119 is named here, so a
    photograph cannot go missing between the folder and the tree without this failing."""
    described = descriptions()
    assert sum(len(files) for files in described.values()) == DALLAS_SOURCE_IMAGES
    refused = [(slug, name) for slug, files in described.items()
               for name, entry in files.items() if entry.get("refused")]
    assert refused == [REFUSED]
    encoded = sum(len(entries) for slug, entries in inventory().items() if slug in DALLAS_SLUGS)
    assert encoded == DESCRIPTIONS_SUPPLIED_MINUS_REFUSED == DALLAS_SOURCE_IMAGES - 1


DESCRIPTIONS_SUPPLIED_MINUS_REFUSED = 118


def test_the_refused_photograph_is_nowhere_in_the_committed_tree() -> None:
    """It is refused for a THIRD-PARTY business name — wall signage reading 'COMPASSIONATE
    HEARTS', which is not this hospital's own fictional name. Its own name, its own street
    number and the civic banner in a sibling image are all encoded; that is the whole
    distinction, and this is the one image on the wrong side of it."""
    slug, name = REFUSED
    assert name not in [e["source"] for e in inventory()[slug]]
    entry = descriptions()[slug][name]
    assert "description" not in entry, "a photograph nobody may see is not described"
    assert isinstance(entry["refused"], str) and "COMPASSIONATE HEARTS" in str(entry["refused"])


def test_every_dallas_photograph_is_captioned_by_its_own_description() -> None:
    """Not by `caption_of`'s reading of the filename, which for these says nothing at all, and
    not by the design's fixed slot caption, which cannot describe a contact sheet."""
    described = descriptions()
    for slug in sorted(DALLAS_SLUGS):
        for entry in inventory()[slug]:
            source = str(entry["source"])
            assert entry["caption"] == described[slug][source]["description"], (slug, source)


def test_every_flag_the_verification_raised_reached_the_inventory() -> None:
    """"Record, do not discard": the identifiability work (A-IDP-1..6, its own branch) reads
    these rather than re-reading 119 images. Pinned BOTH ways — a flag in the descriptions file
    is in the inventory, and a flag in the inventory came from the descriptions file."""
    described = descriptions()
    for slug in sorted(DALLAS_SLUGS):
        for entry in inventory()[slug]:
            expected = described[slug][str(entry["source"])].get("flags", [])
            assert entry.get("flags", []) == expected, (slug, entry["source"])


def test_a_photograph_nobody_flagged_carries_no_flags_key() -> None:
    """Absent, not empty — which is why the 195 entries John's eighteen already committed did
    not move when this task added a key to the schema."""
    for slug, entries in inventory().items():
        for entry in entries:
            if slug not in DALLAS_SLUGS:
                assert "flags" not in entry, (slug, entry["file"])
            elif "flags" in entry:
                assert entry["flags"], (slug, entry["source"], "an empty flags list was written")


def test_no_composite_is_the_hero_of_a_dallas_listing() -> None:
    """Position 1 is `heroSrc` on the detail page and the Browse card. A multi-panel contact
    sheet is not a hospital's front door, and most of these folders are sheets — the curation
    refuses to place one in a slot and `positions` refuses to backfill one while a single
    photograph is unused, so the two together have to leave a real photograph here."""
    described = descriptions()
    for slug in sorted(DALLAS_SLUGS):
        hero = inventory()[slug][0]
        flags = described[slug][str(hero["source"])].get("flags", [])
        assert "composite" not in flags, (slug, hero["source"])
        assert hero["slot"] == "exterior", (slug, hero["slot"])


def test_the_committed_descriptions_are_real_sentences_not_filenames() -> None:
    """A guard against the failure this whole file exists to prevent: a description that is just
    the filename with the underscores taken out describes nothing, and would mean the content
    verification was skipped for that image."""
    for slug, files in descriptions().items():
        for name, entry in files.items():
            if entry.get("refused"):
                continue
            text = str(entry["description"])
            assert len(text.split()) >= 4, (slug, name, text)
            assert name.split(".")[0].replace("_", " ") not in text.lower(), (slug, name, text)
