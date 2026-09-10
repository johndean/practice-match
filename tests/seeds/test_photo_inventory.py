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
# guard against a runaway rather than a restatement of MAX_BYTES. FILES, not entries: since
# C1 an entry may be an EMPTY captioned slot, which weighs nothing.
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


# ENTRIES per hospital — one per POSITION the API serves, which for John's eighteen is one per
# photograph and for the eleven is the photographs PLUS the captioned slots C1 leaves empty.
# A-L9 kept 108 of the eighteen's (six per hospital) and A-L10 kept 73; A-L11 keeps all 195.
# Pinned per hospital rather than as a total, because the total is what hid the loss John found:
# `def_veterinary_hospital` went from 9 to 3 and the sum still looked plausible.
# `PHOTOGRAPHS_PER_DALLAS_HOSPITAL` below pins the eleven's FILE counts separately, so an empty
# slot appearing where a photograph should be cannot hide inside an unchanged entry count.
ENTRIES_PER_HOSPITAL = {
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
    # Task SD1: John's eleven Dallas folders. The count is photographs PLUS empty captioned
    # slots — six of Kilo's fifteen entries are its four empty slots and eleven photographs.
    # Alpha is 14 since fix round 2 restored `alpha_dallas_05.png` (ruling A-IDP-7 §4.1).
    "alpha_dallas_veterinary_specialist_hospital": 14,
    "beta_dallas_veterinary_hospital": 14,
    "charlie_dallas_animal_hospital": 14,
    "delta_dallas_animal_er_hospital": 13,
    "echo_dallas_animal_hospital": 14,
    "foxtrot_dallas_animal_hospital": 10,
    "hotel_dallas_animal_hospital": 13,
    "indigo_dallas_animal_hospital": 10,
    "juliet_dallas_animal_hospital": 11,
    "kilo_dallas_fort_worth_veterinary_hospital": 15,
    "lima_dallas_fort_worth_veterinary_hospital": 11,
}

# The eleven's PHOTOGRAPHS, separately from their entries (C1). `alpha` shows 11 of the 12 its
# folder holds — ONE is refused, since fix round 2 restored the other — and every other folder
# is complete.
PHOTOGRAPHS_PER_DALLAS_HOSPITAL = {
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
    """The measured outcome of A-L11 (John, 2026-09-09: "render ALL images"), pinned: ONE FILE
    PER SOURCE IMAGE, for every image John supplied that was not refused.

    A-L10's 73-of-108 is superseded: the photographs with no by-eye match to one of the six
    fixed captions were dropped, which is the failure that hotfix exists to end.

    NEW-4: this docstring used to say "not one empty slot", three lines above an assertion
    counting twenty-one of them. A-L11's claim was never that no slot is empty — it is that no
    PHOTOGRAPH is dropped, and the two came apart when C1 ruled that a contact sheet may not
    occupy a captioned slot even when that leaves it null. The four assertions below say the
    thing that is actually true: every supplied photograph is committed, the positions exceed
    the photographs by exactly the empty slots, and nothing is empty past the captioned six."""
    inv = inventory()
    assert {slug: len(entries) for slug, entries in inv.items()} == ENTRIES_PER_HOSPITAL
    assert {slug: len([e for e in inv[slug] if e["file"] is not None])
            for slug in PHOTOGRAPHS_PER_DALLAS_HOSPITAL} == PHOTOGRAPHS_PER_DALLAS_HOSPITAL
    filled = [e for entries in inv.values() for e in entries if e["file"] is not None]
    assert len(filled) == 313, "a photograph was dropped"
    positions = sum(len(e) for e in inv.values())
    empty = sum(1 for entries in inv.values() for e in entries if e["file"] is None)
    # The identity, rather than three independent literals: every position is a photograph or an
    # empty captioned slot, and there is no third thing.
    assert (positions, empty) == (334, 21)
    assert positions == len(filled) + empty
    beyond = [e for entries in inv.values() for e in entries if e["slot"] is None]
    assert len(beyond) == 160, "the photographs past the design's six slots (A15.3 renders each)"
    assert all(e["file"] is not None for e in beyond), "an empty entry past the captioned six"


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
# The ONE photograph that is not encoded, and the rule it fell under. Named here so a re-run of
# the pipeline that quietly encoded it would fail rather than pass.
# `alpha_dallas_11_individual_images.png` shows a THIRD-PARTY business name ('COMPASSIONATE
# HEARTS') — not this listing's name and not a number, so John's ruling of 2026-09-10 does not
# reach it, and a listing's visibility switch cannot consent to publishing somebody else's name.
#
# `alpha_dallas_05.png` was the second refusal and is RESTORED (ruling A-IDP-7 §4.1, on John's
# ruling that a street number is part of the invented identity and is governed by SHOW /
# NOT_SHOW rather than by refusal). Its monument carries no business name at all, and
# "4140 CEDAR SPRINGS ROAD" is precisely what the specified `address` regex class already
# matches, so it is filled under NOT_SHOW by the existing design.
REFUSED = (
    ("alpha_dallas_veterinary_specialist_hospital", "alpha_dallas_11_individual_images.png"),
)
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
    """Every one of the 119 John supplied is NAMED here — encoded, or refused with a reason — so
    a photograph cannot go missing between the folder and the tree without this failing.

    The three numbers are DERIVED, not retyped (fix round 1, I2): supplied is the descriptions
    file's own entry count, refused is how many of those carry a reason, and encoded is what the
    inventory holds. A future refusal moves all three together and this docstring cannot go
    stale, because it states no number at all."""
    described = descriptions()
    supplied = sum(len(files) for files in described.values())
    refused = sorted((slug, name) for slug, files in described.items()
                     for name, entry in files.items() if entry.get("refused"))
    encoded = sum(1 for slug in DALLAS_SLUGS for e in inventory()[slug] if e["file"] is not None)
    assert supplied == DALLAS_SOURCE_IMAGES
    assert refused == sorted(REFUSED)
    # The identity, derived on both sides: everything supplied is either encoded or refused, and
    # nothing is encoded that was not supplied.
    assert encoded + len(refused) == supplied


def test_the_refused_photograph_is_nowhere_in_the_committed_tree() -> None:
    """ONE of the 119, and it is the one class the pipeline structurally misses.

    `..._11_...` carries a THIRD-PARTY business name — wall signage reading 'COMPASSIONATE
    HEARTS', which is not this hospital's own fictional name and is not a number, so John's
    ruling of 2026-09-10 does not reach it. `identifiable_content_visibility` is THIS listing's
    consent switch and a listing cannot consent to publishing somebody else's name; and the
    identity matcher builds its terms from this listing's own columns, so a third party's name
    is exactly what neither it nor the regex classes can find."""
    for slug, name in REFUSED:
        assert name not in [e["source"] for e in inventory()[slug]], name
        entry = descriptions()[slug][name]
        assert "description" not in entry, "a photograph nobody may see is not described"
        assert isinstance(entry["refused"], str) and entry["refused"], name
    reasons = {name: str(descriptions()[slug][name]["refused"]) for slug, name in REFUSED}
    assert "COMPASSIONATE HEARTS" in reasons["alpha_dallas_11_individual_images.png"]


def test_the_monument_sign_is_restored_and_governed_by_the_visibility_switch() -> None:
    """A-IDP-7 §4.1, on John's ruling of 2026-09-10: "the numbers are part of the hospital name
    and should be 'shown/not shown' too". `alpha_dallas_05.png` was refused earlier the same day
    as a false location claim and is restored — a street number is part of the invented identity
    and is governed by the listing's one visibility switch, not by keeping the file out.

    It is encoded, described by someone who looked at it, and flagged FOUR ways: `composite`
    (so it never takes a captioned slot), `own_street_number` (the ruled class),
    `address_not_this_listing` (the residual John has not ruled on — Cedar Springs Road is a
    real street and Alpha's anchor is 18770 Preston Rd, carried as open question Q-SD1-1) and
    `vehicle_no_legible_plate`, added on a fresh look at the file (NEW-7): the monument panel
    shows three vehicles, none with a legible plate, which is the condition nine other entries
    already carry that flag for. The ruling's §5.1 list named three because it was written
    before anyone opened the image; a flag is a prediction about what the classifier will find,
    so leaving a vehicle unflagged would have been a prediction that is wrong."""
    slug, name = "alpha_dallas_veterinary_specialist_hospital", "alpha_dallas_05.png"
    entry = descriptions()[slug][name]
    assert "refused" not in entry, "the restoration did not remove the refusal"
    assert entry["flags"] == ["composite", "own_street_number", "address_not_this_listing",
                              "vehicle_no_legible_plate"]
    placed = [e for e in inventory()[slug] if e["source"] == name]
    assert len(placed) == 1, "the restored sheet is encoded exactly once"
    # A composite never occupies one of the design's six captioned slots (C1), so the restoration
    # lands past them and takes no slot from a single photograph.
    assert placed[0]["slot"] is None, placed[0]
    assert inventory()[slug].index(placed[0]) >= SLOT_COUNT
    # The record quotes John and names the ruling, so the next reader is not left guessing why a
    # refused image came back.
    assert "shown/not shown" in str(entry["note"]) and "A-IDP-7" in str(entry["note"])


def test_every_rendered_street_number_is_encoded_and_flagged_not_refused() -> None:
    """John's ruling of 2026-09-10, verbatim: "the numbers are part of the hospital name and
    should be 'shown/not shown' too". A number rendered into one of these photographs is part of
    the invented identity, so NO image is kept out for carrying one — every one is encoded and
    flagged, and the flag is the pipeline's expectation that `premises_number` will fire on it.

    Fourteen: eleven the content verification reported, `charlie_dallas_11.png` from the fix
    round 1 sweep, `charlie_dallas_03.png` from the fix round 2 sweep (its number's foot alone is
    in frame), and `alpha_dallas_05.png`, restored by this ruling."""
    flagged = [(slug, str(e["source"])) for slug in sorted(DALLAS_SLUGS)
               for e in inventory()[slug] if "own_street_number" in e.get("flags", [])]
    assert len(flagged) == 14, flagged
    # The image the earlier ruling refused for carrying a number is now IN the set — the
    # assertion is inverted deliberately, and it is the one that would catch a silent re-refusal.
    assert "alpha_dallas_05.png" in [name for _slug, name in flagged]
    # Alpha's three, in the order the regenerated inventory actually places them rather than a
    # retyped list: the restored sheet is a composite, so it sorts after the captioned slots.
    alpha = [name for slug, name in flagged if slug.startswith("alpha_")]
    assert alpha == ["alpha_dallas_12_individual_images.png.png", "alpha_dallas_02.png",
                     "alpha_dallas_05.png"], alpha


# --- The mapping the seed flags owe the classifier (ruling A-IDP-7 §5.3) -----------------------
#
# The flag names are NOT the spec's detector classes and must not be renamed to match them: they
# are different kinds of statement. The spec's classes are DETECTOR OUTPUTS (`REGEX_CLASSES`
# keys, the vision `kind` enum) describing what a machine found. These flags are HUMAN FINDINGS
# about a source image, and two of them — `own_business_name`, `own_street_number` — assert
# PROVENANCE ("this identity is the listing's own invention"), which no detector class can
# express and which is the whole reason these images stayed in the set at all.
#
# What is owed instead is this mapping: for each flag, the detector outcome the identifiability
# pipeline is expected to produce on that image. That turns a flag from a note beside the
# pipeline into a testable expectation of it, and the eleven Dallas hospitals into its first
# real fixture.
FLAG_TO_EXPECTED_DETECTOR_OUTCOME = {
    "own_business_name": "identity match on field `name` (exact / substring / distinctive)",
    "own_street_number": "regex class `premises_number` (SPEC:232 as amended by A-IDP-7)",
    "address_not_this_listing": "regex class `address`",
    "civic_signage": "vision kind `signage`, expected NOT to identify the practice",
    "vehicle_no_legible_plate": "vision kind `vehicle`",
    "certificates_text_unreadable": "vision kind `document`",
    "composite": "none — a slot-placement fact only, never an identifiability finding",
}


def test_every_flag_names_the_detector_class_the_pipeline_must_produce() -> None:
    """Pinned BOTH ways, which is the point: a new flag cannot be invented without deciding what
    the classifier is expected to do with it, and a mapping entry cannot rot after its last use
    disappears from the tree."""
    in_use = {flag for entries in inventory().values() for e in entries
              for flag in e.get("flags", [])}
    # …and the refused entries' flags count too, when they have any: they are still findings.
    in_use |= {flag for files in descriptions().values() for e in files.values()
               for flag in e.get("flags", [])}
    assert in_use == set(FLAG_TO_EXPECTED_DETECTOR_OUTCOME), (
        sorted(in_use ^ set(FLAG_TO_EXPECTED_DETECTOR_OUTCOME))
    )
    assert len(FLAG_TO_EXPECTED_DETECTOR_OUTCOME) == 7
    # `composite` is the one flag that is deliberately NOT an identifiability finding; saying so
    # is what stops it being wired to a detector class later by someone tidying the table.
    assert FLAG_TO_EXPECTED_DETECTOR_OUTCOME["composite"].startswith("none")


def test_every_dallas_photograph_is_captioned_by_its_own_description() -> None:
    """Not by `caption_of`'s reading of the filename, which for these says nothing at all, and
    not by the design's fixed slot caption, which cannot describe a contact sheet."""
    described = descriptions()
    for slug in sorted(DALLAS_SLUGS):
        for entry in inventory()[slug]:
            if entry["source"] is None:
                continue   # a captioned slot C1 left empty holds no photograph to describe
            source = str(entry["source"])
            assert entry["caption"] == described[slug][source]["description"], (slug, source)


def test_every_flag_the_verification_raised_reached_the_inventory() -> None:
    """"Record, do not discard": the identifiability work (A-IDP-1..6, its own branch) reads
    these rather than re-reading 119 images. Pinned BOTH ways — a flag in the descriptions file
    is in the inventory, and a flag in the inventory came from the descriptions file."""
    described = descriptions()
    for slug in sorted(DALLAS_SLUGS):
        for entry in inventory()[slug]:
            if entry["source"] is None:
                continue
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


def test_no_composite_occupies_any_of_the_designs_six_captioned_slots() -> None:
    """C1, and the assertion whose absence let twenty-one of them drift in: position 1 alone was
    pinned and positions 2 to 6 were not.

    A sheet of six pictures is not "the reception area". The curation refuses to PLACE one in a
    slot and `positions` refuses to BACKFILL one into a slot the curation left empty, even when
    that leaves the slot null — so across all eleven hospitals and all six captioned positions
    there must be none at all."""
    described = descriptions()
    offenders = [
        (slug, position, str(entry["slot"]), str(entry["source"]))
        for slug in sorted(DALLAS_SLUGS)
        for position, entry in enumerate(inventory()[slug][:SLOT_COUNT], start=1)
        if entry["source"] is not None
        and "composite" in described[slug][str(entry["source"])].get("flags", [])
    ]
    assert offenders == [], offenders


def test_the_hero_of_every_seeded_listing_is_a_real_exterior_photograph() -> None:
    """Position 1 is `heroSrc` on the detail page and the thumbnail source on the Browse card,
    so it is the one captioned slot that may never be empty — a listing whose hero is null has
    no card at all.

    NEW-10: this used to iterate `DALLAS_SLUGS`, a frozen list of eleven, which made it blind to
    exactly the case C1 created. A twelfth folder of nothing but contact sheets would leave
    position 1 null — the composite rule forbids a sheet there and there would be no single to
    take it — and would ship a Browse card with no thumbnail with every gate green. It now
    iterates EVERY seeded hospital, so the guard arrives with the folder rather than with
    somebody remembering to widen a constant."""
    inv = inventory()
    assert set(inv) == set(seed_slugs()), "the inventory and the seed file name different rows"
    for slug in sorted(inv):
        hero = inv[slug][0]
        assert hero["slot"] == "exterior", (slug, hero["slot"])
        assert hero["file"] is not None, (
            slug, "position 1 is null — this listing would render a card with no thumbnail"
        )


def test_a_captioned_slot_left_empty_by_the_composite_rule_is_a_real_empty_slot() -> None:
    """C1 creates empty captioned slots on seven of the eleven, and they must be A-L10's own
    empty slot — the shape the design renders its placeholder for — rather than a third kind of
    entry the API would have to learn about. Twenty-one of them, none past the sixth position."""
    empty = [(slug, position, e)
             for slug, entries in inventory().items()
             for position, e in enumerate(entries, start=1) if e["file"] is None]
    assert len(empty) == 21, [(s, p) for s, p, _ in empty]
    for slug, position, entry in empty:
        assert position <= SLOT_COUNT, (slug, position, "an empty entry past the captioned six")
        assert entry == {"slot": entry["slot"], "file": None, "source": None, "caption": None}
        assert slug in DALLAS_SLUGS, (slug, "one of John's eighteen grew an empty slot")


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


# --- M2: index.json holds FOUR entry shapes, and one of them nothing writes any more ----------
#
# 1. LEGACY FILLED (John's eighteen): slot, file, source, caption, bytes, width, height,
#    sha256 and `quality` — a field `scripts/prepare_photos.py::encode` stopped writing when the
#    encoder moved to `app.media.encode` (spec 2026-09-08 D15). Their PIXELS are unchanged: a
#    re-encode reproduces every sha256 byte for byte, which is how Task SD1 knew it was safe to
#    add eleven folders with `--merge` instead of re-running all twenty-nine.
# 2. DALLAS FILLED, UNFLAGGED: the same eight fields, no `quality`, no `flags`.
# 3. DALLAS FILLED, FLAGGED: those eight plus `flags`.
# 4. EMPTY CAPTIONED SLOT: slot, file, source, caption — all four, with `file` null (A-L10, and
#    since C1 also every captioned slot whose folder had only sheets left).
#
# The population of each shape is COUNTED from the tree by the test below rather than written
# here (fix round 3, NEW-2): the four numbers in this block went stale within one round of being
# typed, twice, and a comment nobody can execute is the wrong place for a measurement.
#
# The hazard that makes this worth a test rather than a comment: a full run without `--merge`
# would rewrite all twenty-nine slugs from the CURRENT encoder, and would therefore silently
# drop `quality` from those 195 entries. Nothing reads it, so nothing would fail — the diff
# would just be 195 quiet deletions in a generated file, which is precisely the shape of change
# nobody reviews. This test makes the hazard visible at the moment it would be introduced.

LEGACY_ONLY_KEYS = frozenset({"quality"})

#: Every key `scripts/prepare_photos.py` can write on a FILLED entry, derived from the pipeline
#: rather than retyped (NEW-3). `encode` returns the six measured fields; `prepare` adds `slot`,
#: and `described_over` adds `caption` (always) and `flags` (only when a flag was raised).
PIPELINE_WRITES = frozenset({
    "file", "source", "caption", "bytes", "width", "height", "sha256",   # encode()
    "slot",                                                             # prepare()
    "flags",                                                            # described_over()
})


def _returned_keys(function: object) -> set[str]:
    """The string keys of every dict literal `function` RETURNS, read from its syntax tree.

    A membership scan (`f'"{k}":' in source`) is not a pin — it answers "is each key I already
    know about present", which stays green when the pipeline grows a key nobody listed. That was
    the first version of this check and a mutation probe walked straight through it. Parsing the
    return statements answers the question that matters: what does this function ACTUALLY emit."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))  # type: ignore[arg-type]
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    return keys


def test_the_key_set_this_module_pins_is_the_one_the_pipeline_actually_writes() -> None:
    """NEW-3's real pin, BOTH WAYS. `encode` is the only place a measured field is minted, so
    its return literal is the authority: a key added to the pipeline fails here rather than
    silently widening what `test_a_full_re_run_would_drop_a_key…` will tolerate, and a key
    removed fails here too."""
    import scripts.prepare_photos as PP

    assert _returned_keys(PP.encode) == PIPELINE_WRITES - {"slot", "flags"}
    # `slot` and `flags` are added AROUND `encode`, not by it. `described_over` builds its dict
    # incrementally rather than returning a literal, so it is checked by CALLING it — which is
    # the stronger check anyway, because it pins the conditional `flags` key to the condition.
    described = {"x.png": {"description": "A front", "flags": [], "refused": None},
                 "y.png": {"description": "A sheet", "flags": ["composite"], "refused": None}}
    assert set(PP.described_over(described, Path("x.png"))) == {"caption"}
    assert set(PP.described_over(described, Path("y.png"))) == {"caption", "flags"}
    assert PP.described_over(described, Path("absent.png")) == {}
    # …and `slot` is on every filled entry the pipeline has ever written, which closes the union.
    assert all("slot" in e for entries in inventory().values() for e in entries)


def test_a_full_re_run_would_drop_a_key_the_committed_entries_still_carry() -> None:
    """Not a defect to fix — `quality` is dead and the eighteen's pixels are byte-identical — but
    a fact the next operator must be told BEFORE they type `prepare_photos.py` with no `--slugs`.
    If this ever fails because the set is empty, the hazard is gone and the whole block above
    (and `--merge`'s reason for existing) can go with it."""
    # What the pipeline writes today. NEW-3: the old cross-reference here named a test that
    # checks a sha256 and two dimensions, not the KEY SET, so this set was pinned by nothing and
    # a pipeline that started writing a ninth key would have gone unnoticed. It is now read from
    # the pipeline itself — `encode`'s measured fields, plus the two `prepare` adds — so the two
    # cannot drift. This module still opens no image: it reads a function's declared output, not
    # a file on disk.
    written = PIPELINE_WRITES
    committed = {key for entries in inventory().values() for e in entries for key in e}
    stale = committed - written
    assert stale == LEGACY_ONLY_KEYS, (
        f"index.json carries {sorted(stale)}, which a full run of prepare_photos would drop; "
        "re-run with --merge, or accept the deletion deliberately"
    )
    legacy = [e for entries in inventory().values() for e in entries if "quality" in e]
    assert len(legacy) == 195, "the legacy shape is John's eighteen and nobody else"
    assert {slug for slug, entries in inventory().items()
            if any("quality" in e for e in entries)}.isdisjoint(DALLAS_SLUGS)


def test_every_entry_is_one_of_the_four_shapes_and_nothing_else() -> None:
    """Pinned as a closed set, both ways: a fifth shape appearing is either a pipeline change
    nobody described or a hand-edit of a generated file, and both should stop here.

    The four shapes are named; their POPULATIONS are counted from the tree and only their
    relationships are asserted (NEW-2). Four hand-written counts in the comment above went stale
    twice in two rounds, and the invariants below are what those numbers were standing in for."""
    base = {"slot", "file", "source", "caption"}
    measured = base | {"bytes", "width", "height", "sha256"}
    shapes = {
        "legacy filled": frozenset(measured | {"quality"}),
        "Dallas filled, unflagged": frozenset(measured),
        "Dallas filled, flagged": frozenset(measured | {"flags"}),
        "empty captioned slot": frozenset(base),
    }
    found: dict[frozenset[str], int] = {}
    for entries in inventory().values():
        for entry in entries:
            found[frozenset(entry)] = found.get(frozenset(entry), 0) + 1
    assert set(found) == set(shapes.values()), sorted(sorted(s) for s in found)
    counted = {name: found[keys] for name, keys in shapes.items()}
    # The relationships the counts existed to express, each derived from the other tests' own
    # constants rather than from a fifth copy of the same numbers.
    assert counted["legacy filled"] == sum(
        n for slug, n in ENTRIES_PER_HOSPITAL.items() if slug not in DALLAS_SLUGS
    ) == 195
    assert counted["empty captioned slot"] == 21
    assert (counted["Dallas filled, unflagged"] + counted["Dallas filled, flagged"]
            == sum(PHOTOGRAPHS_PER_DALLAS_HOSPITAL.values()))
    assert sum(counted.values()) == sum(len(e) for e in inventory().values())
