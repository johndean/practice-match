"""The photo pipeline (spec 2026-09-06 D3), exercised on a temp folder of GENERATED images —
never on John's originals, which this suite must not depend on being present.

L3 review round 1 (controller, measured 2026-09-08): the previous function-scoped `source`
fixture regenerated six 2400x1600/1200x2000 random-noise images, with EXIF/ICC attached to
every one, on EVERY test that used it (~13.5 s setup), and several tests then ran that noise
through the full quality ladder at up to 1600 px (~15 s call) — 54 tests, ~28 s each, nearly
doubling the whole backend suite and twice cancelling CI's 30-minute backend job. Every fixture
below is now generated ONCE per module (nothing under `prepare()`/`encode()` ever writes back
into a source folder, so sharing one read-only copy across the file is safe) and is as small as
its assertion allows: most images are a few flat-coloured pixels; only two images are
deliberately large — one just over the 1600 px ceiling (mostly flat, so it still compresses on
the first quality rung) to exercise the resize path, and one genuinely incompressible ~1000x1000
block of noise to exercise the "does not fit" path on real content rather than a monkeypatched
budget. Every original assertion is unchanged; only fixture scope and image sizes moved.
"""
import io
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageCms

from scripts import prepare_photos as PP

ROOT = Path(__file__).resolve().parent.parent.parent


# A REAL EXIF block (GPS included) and a REAL sRGB ICC profile, attached to the fixture sources
# so `test_metadata_is_stripped` can actually fail when the stripping is removed (pre-flight
# M2): a plain `Image.new(...).save(...)` writes no EXIF, no ICC and no XMP, so the old
# assertion held whether or not `_flattened()` re-wrapped the pixels into a fresh image.
def _metadata() -> dict[str, Any]:
    exif = Image.Exif()
    exif[0x010E] = "VIN Foundation seed source"    # ImageDescription
    exif[0x0110] = "Practice Match test camera"    # Model
    exif[0x8825] = {1: "N", 2: (30.0, 16.0, 0.0)}  # GPSInfo — the tag that must never survive
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    return {"exif": exif.tobytes(), "icc_profile": profile.tobytes()}


def _noisy(path: Path, size: tuple[int, int], *, metadata: bool = False) -> None:
    """A deliberately incompressible image: a flat colour would encode to a few hundred bytes
    and prove nothing about the 250 KB ceiling. `metadata=True` attaches the EXIF and ICC
    block above, so the stripping has something to strip. Reserved for the one fixture that
    must genuinely fail to compress (`oversized_source`, below) — everything else uses `_flat`,
    which is orders of magnitude faster because it never randomises a full frame."""
    rng = random.Random(path.name)
    img = Image.new("RGB", size)
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(size[0] * size[1])])
    img.save(path, **(_metadata() if metadata else {}))


def _flat(path: Path, size: tuple[int, int], *, patch: tuple[int, int] | None = None,
          metadata: bool = False) -> None:
    """A near-instant fixture image: `Image.new` fills a flat colour in O(1) regardless of
    `size`, so this stays fast even for the one image in this suite that must be genuinely
    larger than the 1600 px ceiling. `patch`, given as (width, height), randomises a small
    top-left corner so the image is not perfectly uniform without paying to randomise the
    whole frame. `metadata=True` attaches the real EXIF/ICC block above."""
    img = Image.new("RGB", size, (120, 150, 170))
    if patch is not None:
        pw, ph = patch
        rng = random.Random(path.name)
        noise = Image.new("RGB", (pw, ph))
        noise.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(pw * ph)])
        img.paste(noise, (0, 0))
    img.save(path, **(_metadata() if metadata else {}))


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Eight named images — the six the design's default slots select, one spare exterior no
    slot can take, and one stub — plus a dotfile and a non-image, generated once for the whole
    module. Only the first is larger than MAX_EDGE_PX — mostly flat colour with a small noise
    patch, so it still compresses on the first quality rung while genuinely exercising the
    resize path; the last ("...stub...") is never opened by `source_images()` (filename-only
    filtering), so it is a stub, not a real image. No slot's keywords name the stub and all six
    slots match before any fallback could reach it, so a regression to "the first six in folder
    order" (the A-L9 failure, one rung along) fails loudly here rather than silently."""
    root = tmp_path_factory.mktemp("photos-source")
    folder = root / "demo_hospital_individual_images"
    folder.mkdir()
    _flat(folder / "01_exterior_front.png", (1620, 20), patch=(40, 20))
    _flat(folder / "02_exterior_side.jpg", (24, 24))
    _flat(folder / "03_interior_lobby.jpg", (24, 24), metadata=True)
    _flat(folder / "04_interior_exam.png", (24, 24))
    _flat(folder / "05_interior_treatment.png", (24, 24))
    _flat(folder / "06_interior_surgery.png", (24, 24))
    _flat(folder / "07_interior_kennels.png", (24, 24))
    (folder / "08_interior_stub.png").write_bytes(b"stub, never opened by source_images()")
    (folder / ".DS_Store").write_bytes(b"\x00\x01junk")
    (folder / "notes.txt").write_text("not an image")
    return root


def _folder(root: Path, slug: str, names: list[str]) -> Path:
    """One source folder of tiny flat images, named as John's curated folders name them."""
    folder = root / f"{slug}{PP.FOLDER_SUFFIX}"
    folder.mkdir(parents=True)
    for name in names:
        _flat(folder / name, (24, 24))
    return folder


@pytest.fixture(scope="module")
def oversized_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """ONE genuinely incompressible image (uniform random noise), generated once for the whole
    module. 1000x1000 is comfortably under both MAX_EDGE_PX (1600) and FALLBACK_EDGE_PX (1100),
    so `_flattened()` never downscales it before `encode()` tries the quality ladder — meaning
    the "does not fit" tests below exhaust every real rung on real content, rather than relying
    on a monkeypatched MAX_BYTES (L3 review round 1)."""
    root = tmp_path_factory.mktemp("photos-oversized")
    folder = root / "incompressible_individual_images"
    folder.mkdir()
    _noisy(folder / "01_exterior_front.png", (1000, 1000))
    return root


def test_source_images_are_sorted_and_exclude_non_images(source: Path) -> None:
    names = [p.name for p in PP.source_images(source / "demo_hospital_individual_images")]
    assert names == ["01_exterior_front.png", "02_exterior_side.jpg", "03_interior_lobby.jpg",
                     "04_interior_exam.png", "05_interior_treatment.png", "06_interior_surgery.png",
                     "07_interior_kennels.png", "08_interior_stub.png"]


def test_prepare_fills_the_designs_six_slots_not_the_first_six_in_folder_order(
    source: Path, tmp_path: Path
) -> None:
    """A-L9. The cap was `sorted(folder)[:4]`, and John's folders number the exteriors first, so
    the seed kept four exteriors and dropped every interior. The set is now the six files the
    design's own slots name, in SLOT order — `p.photos[i]` fills slot `i` (amendment A12.2)."""
    out = tmp_path / "photos"
    index = PP.prepare(source, out, ["demo_hospital"], {})
    entries = index["demo_hospital"]
    assert [e["file"] for e in entries] == ["1.webp", "2.webp", "3.webp", "4.webp", "5.webp", "6.webp"]
    assert [e["slot"] for e in entries] == list(PP.DEFAULT_SLOTS)
    assert [e["source"] for e in entries] == [
        "01_exterior_front.png", "03_interior_lobby.jpg", "04_interior_exam.png",
        "05_interior_treatment.png", "06_interior_surgery.png", "07_interior_kennels.png",
    ]
    assert "02_exterior_side.jpg" not in {e["source"] for e in entries}, "no slot takes a second exterior"


def test_every_output_is_webp_within_the_dimension_and_size_ceilings(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"], {})
    for path in sorted((out / "demo_hospital").glob("*.webp")):
        assert path.stat().st_size <= PP.MAX_BYTES, (path.name, path.stat().st_size)
        with Image.open(path) as img:
            assert img.format == "WEBP"
            assert max(img.size) <= PP.MAX_EDGE_PX, (path.name, img.size)


def test_the_fixture_sources_really_carry_metadata(source: Path) -> None:
    """Guards the guard: if this stops holding, `test_metadata_is_stripped` below is vacuous
    again and the stripping could be deleted with a green suite (pre-flight M2). The block sits
    on the lobby photograph because A-L9 selects that one — the second exterior it used to sit
    on is no longer encoded, which would have made the stripping test vacuous a second way."""
    with Image.open(source / "demo_hospital_individual_images" / "03_interior_lobby.jpg") as img:
        assert img.info.get("icc_profile"), "the fixture lost its ICC profile"
        assert img.getexif().get(0x0110) == "Practice Match test camera", "the fixture lost its EXIF"


def test_metadata_is_stripped(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"], {})
    for path in sorted((out / "demo_hospital").glob("*.webp")):
        with Image.open(path) as img:
            assert "exif" not in img.info and "icc_profile" not in img.info and "xmp" not in img.info
            assert dict(img.getexif()) == {}, (path.name, dict(img.getexif()))


def test_the_inventory_records_a_matching_sha256_and_dimensions(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"], {})
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    for entry in index["hospitals"]["demo_hospital"]:
        path = out / "demo_hospital" / str(entry["file"])
        assert PP.sha256_of(path) == entry["sha256"]
        assert entry["bytes"] == path.stat().st_size
        with Image.open(path) as img:
            assert (entry["width"], entry["height"]) == img.size


@pytest.mark.parametrize(
    "name, expected",
    [("01_exterior_front_entrance.png", "Exterior — front entrance"),
     ("06_interior_reception_lobby.png", "Interior — reception lobby"),
     ("02_exterior_city_view.png", "Exterior — city view"),
     ("09_interior_treatment_surgery_area.png", "Interior — treatment surgery area"),
     ("hospital front.jpg", "Hospital front"),
     ("exterior.png", "Exterior"),
     ("01_exterior.png", "01 exterior")],
)
def test_caption_of_reads_the_curated_filename(name: str, expected: str) -> None:
    """Both arms of caption_of: the NN_area_description convention and the fallback."""
    assert PP.caption_of(name) == expected


def test_the_inventory_records_a_caption_per_photograph(source: Path, tmp_path: Path) -> None:
    index = PP.prepare(source, tmp_path / "photos", ["demo_hospital"], {})
    assert [e["caption"] for e in index["demo_hospital"]] == [
        "Exterior — front", "Interior — lobby", "Interior — exam",
        "Interior — treatment", "Interior — surgery", "Interior — kennels",
    ]


def test_encode_gives_up_rather_than_writing_an_oversized_file(
    oversized_source: Path, tmp_path: Path
) -> None:
    """The last rung of the quality ladder is small enough that a real photograph always fits,
    so the `raise RuntimeError` and both loop-exhaustion arcs are unreachable from real data —
    and 100 % branches is the gate (pre-flight C2). A genuinely incompressible image (real
    uniform noise, not a monkeypatched MAX_BYTES) is the honest way to reach them; the
    assertion below verifies the fixture's premise empirically rather than assuming it
    (L3 review round 1)."""
    src = oversized_source / "incompressible_individual_images" / "01_exterior_front.png"
    with Image.open(src) as raw:
        probe = io.BytesIO()
        raw.convert("RGB").save(probe, format="WEBP", quality=PP.QUALITY_LADDER[-1], method=6)
    assert len(probe.getvalue()) > PP.MAX_BYTES, "fixture must genuinely exceed the ceiling at the lowest rung"
    with pytest.raises(RuntimeError) as exc:
        PP.encode(src, tmp_path / "out" / "1.webp")
    assert "01_exterior_front.png" in str(exc.value)


def test_main_returns_two_when_an_image_will_not_fit(oversized_source: Path, tmp_path: Path) -> None:
    """RuntimeError is one of the two exceptions main() turns into exit 2; without this the
    `RuntimeError` half of that `except` tuple is never taken. Reuses the genuinely
    incompressible fixture above rather than a monkeypatched budget (L3 review round 1)."""
    assert PP.main(
        ["--source", str(oversized_source), "--out", str(tmp_path / "out"), "--slugs", "incompressible"]
    ) == 2


def test_a_folder_with_fewer_than_six_images_yields_what_it_has(tmp_path: Path) -> None:
    root = tmp_path / "src"
    folder = root / "thin_individual_images"
    folder.mkdir(parents=True)
    _flat(folder / "01_only.png", (100, 80))
    index = PP.prepare(root, tmp_path / "out", ["thin"], {})
    assert [e["file"] for e in index["thin"]] == ["1.webp"]
    assert [e["slot"] for e in index["thin"]] == ["exterior"]


def test_a_missing_folder_is_reported_not_skipped_silently(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc:
        PP.prepare(tmp_path / "src", tmp_path / "out", ["absent"], {})
    assert "absent_individual_images" in str(exc.value)


def test_a_small_image_is_not_upscaled(tmp_path: Path) -> None:
    root = tmp_path / "src"
    folder = root / "small_individual_images"
    folder.mkdir(parents=True)
    _flat(folder / "01_small.png", (240, 160))
    PP.prepare(root, tmp_path / "out", ["small"], {})
    with Image.open(tmp_path / "out" / "small" / "1.webp") as img:
        assert img.size == (240, 160)


def test_prepare_is_idempotent_and_replaces_a_stale_output(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    first = PP.prepare(source, out, ["demo_hospital"], {})
    (out / "demo_hospital" / "9.webp").write_bytes(b"stale")
    second = PP.prepare(source, out, ["demo_hospital"], {})
    assert first == second
    assert not (out / "demo_hospital" / "9.webp").exists(), "a stale file must not survive a re-run"


def test_main_writes_the_tree_and_returns_zero(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    code = PP.main(["--source", str(source), "--out", str(out), "--slugs", "demo_hospital"])
    assert code == 0
    assert (out / "index.json").exists() and (out / "demo_hospital" / "1.webp").exists()


def test_main_returns_two_when_a_folder_is_missing(tmp_path: Path) -> None:
    code = PP.main(["--source", str(tmp_path), "--out", str(tmp_path / "out"), "--slugs", "nope"])
    assert code == 2


def test_main_defaults_its_slugs_to_the_seed_file(source: Path, tmp_path: Path) -> None:
    """With no --slugs, main() reads seeds/hospitals.json. Proven by the eighteen real slugs
    having no folders under the temp source: it reached exit 2 by LOOKING for them."""
    assert PP.seed_slugs()[0] == "6666_dallas_veterinary_specialist_hospital"
    assert PP.main(["--source", str(source), "--out", str(tmp_path / "out")]) == 2


def test_the_module_runs_as_a_script(tmp_path: Path) -> None:
    """Covers the `if __name__ == "__main__":` guard in this process is impossible without
    runpy; a subprocess proves the entry point itself works end to end."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prepare_photos.py"),
         "--source", str(tmp_path), "--out", str(tmp_path / "out"), "--slugs", "nope"],
        capture_output=True, text=True, check=False, cwd=ROOT,
    )
    assert result.returncode == 2


def test_the_main_guard_is_covered_in_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """runpy re-executes the file in THIS process with __name__ == "__main__", so pytest-cov
    sees the guard and its body (the subprocess above cannot report coverage back)."""
    import runpy

    monkeypatch.setattr(
        sys, "argv",
        ["prepare_photos.py", "--source", str(tmp_path), "--out", str(tmp_path / "out"), "--slugs", "nope"],
    )
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "prepare_photos.py"), run_name="__main__")
    assert exc.value.code == 2


def test_prepare_refuses_a_slug_that_is_not_a_slug(tmp_path: Path) -> None:
    """Final review M2. `prepare()` does `shutil.rmtree(out_root / slug)`, and `--slugs` reaches
    it from argv unchecked — so `../..` would delete outside `seeds/hospitals/photos`. It is a
    hand-run developer script, which is exactly the kind that earns a guard under the repo's
    "no destructive actions" rule. The refusal has to come BEFORE the folder lookup, or a
    traversing slug that happens to name a real folder would still reach the rmtree."""
    keep = tmp_path / "out" / "keep.txt"
    keep.parent.mkdir(parents=True)
    keep.write_text("not mine to delete")
    for bad in ("../..", "a/b", ".", "..", ".hidden"):
        with pytest.raises(ValueError, match="is not a slug"):
            PP.prepare(tmp_path / "src", tmp_path / "out", [bad], {})
    assert keep.exists()


# --- A-L9: the design's six photo slots ------------------------------------------------------
# John, 2026-09-09: "the seed phase failed to upload ALL the images - only exterior where
# uploaded and none of the interior images are being rendered". The detail page renders exactly
# six captioned slots per practice, chosen by practice type (`photoSet(p)` in the V3 design), and
# `p.photos[i]` fills slot `i` (amendment A12.2) — so the seed carries six photographs and each
# one is the source image whose curated filename matches its slot's subject, which is what makes
# the design's own captions true of the photographs shown.


def test_max_photos_is_the_length_of_every_design_slot_list() -> None:
    """Six is not a taste: it is how many slots `photoSet(p)` renders. A seventh photograph
    could never be displayed, and a slot list of five would leave one slot blank."""
    assert PP.MAX_PHOTOS == 6
    for label, slots in [("default", PP.DEFAULT_SLOTS), *PP.SLOTS_BY_TYPE.items()]:
        assert len(slots) == PP.MAX_PHOTOS, label
        assert len(set(slots)) == PP.MAX_PHOTOS, f"{label} names a slot twice"


def test_the_slot_lists_are_the_four_the_design_renders() -> None:
    """Verbatim from `photoSet(p)` in `Practice Match V3.dc.html`: the equine list, the
    Emergency list, the Specialty list and the fallback the seeds' "Small animal" takes."""
    assert PP.DEFAULT_SLOTS == ("exterior", "lobby", "exam", "treatment", "surgery", "kennel")
    assert PP.SLOTS_BY_TYPE == {
        "Large animal": ("exterior", "barn", "office", "truck", "lab", "grounds"),
        "Emergency": ("exterior", "triage", "treatment", "icu", "surgery", "imaging"),
        "Specialty": ("exterior", "lobby", "consult", "surgery", "imaging", "recovery"),
    }
    named = {slot for slots in (PP.DEFAULT_SLOTS, *PP.SLOTS_BY_TYPE.values()) for slot in slots}
    assert set(PP.SLOT_KEYWORDS) == named, "every slot the design renders needs its keywords, and no others"


@pytest.mark.parametrize(
    "name, expected",
    [("10_interior_ct_scanner_room.png", "interior_ct_scanner_room"),
     ("01_Exterior_Front.JPG", "exterior_front"),
     ("hospital front.jpg", "hospital front"),
     ("2222.png", "2222")],
)
def test_descriptor_of_drops_the_leading_number_and_lower_cases(name: str, expected: str) -> None:
    assert PP.descriptor_of(name) == expected


def test_a_small_animal_folder_fills_the_default_slots_though_its_interiors_are_numbered_last(tmp_path: Path) -> None:
    """The exact shape of John's folders and of the failure: five exteriors first, the interiors
    after them. Under `[:4]` this hospital shipped four exteriors and no interior at all."""
    root = tmp_path / "src"
    _folder(root, "small", [
        "01_exterior_front_view.png", "02_exterior_entrance_view.png", "03_exterior_monument_sign.png",
        "04_exterior_street_corner_view.png", "05_exterior_parking_view.png", "06_interior_reception.png",
        "07_interior_waiting_area.png", "08_interior_exam_room.png", "09_interior_treatment_area.png",
        "10_interior_surgery_room.png", "11_interior_kennel_hallway.png",
    ])
    index = PP.prepare(root, tmp_path / "out", ["small"], {"small": "Small animal"})
    assert [(e["slot"], e["source"]) for e in index["small"]] == [
        ("exterior", "01_exterior_front_view.png"),
        ("lobby", "06_interior_reception.png"),
        ("exam", "08_interior_exam_room.png"),
        ("treatment", "09_interior_treatment_area.png"),
        ("surgery", "10_interior_surgery_room.png"),
        ("kennel", "11_interior_kennel_hallway.png"),
    ]


def test_an_emergency_folder_fills_triage_icu_and_imaging(tmp_path: Path) -> None:
    root = tmp_path / "src"
    _folder(root, "er", [
        "01_exterior_main_front_dusk.png", "02_exterior_monument_sign.png", "03_exterior_emergency_entrance.png",
        "04_interior_reception.png", "05_interior_treatment_area.png", "06_interior_ct_scanner.png",
        "07_interior_icu.png", "08_interior_surgery_room.png",
    ])
    index = PP.prepare(root, tmp_path / "out", ["er"], {"er": "Emergency"})
    assert [(e["slot"], e["source"]) for e in index["er"]] == [
        ("exterior", "01_exterior_main_front_dusk.png"),
        ("triage", "04_interior_reception.png"),     # no "triage" file: the design's caption is "Triage and intake"
        ("treatment", "05_interior_treatment_area.png"),
        ("icu", "07_interior_icu.png"),
        ("surgery", "08_interior_surgery_room.png"),
        ("imaging", "06_interior_ct_scanner.png"),   # "ct_" — the CT room is the imaging room
    ]


def test_a_specialty_folder_fills_consult_imaging_and_recovery(tmp_path: Path) -> None:
    root = tmp_path / "src"
    _folder(root, "spec", [
        "01_exterior_front_entrance.png", "02_exterior_street_side_view.png", "03_interior_reception.png",
        "04_interior_exam_room.png", "05_interior_mri_ct_room.png", "06_interior_surgery_room.png",
        "07_interior_recovery_ward.png",
    ])
    index = PP.prepare(root, tmp_path / "out", ["spec"], {"spec": "Specialty"})
    assert [(e["slot"], e["source"]) for e in index["spec"]] == [
        ("exterior", "01_exterior_front_entrance.png"),
        ("lobby", "03_interior_reception.png"),
        ("consult", "04_interior_exam_room.png"),    # an exam room IS the consult room
        ("surgery", "06_interior_surgery_room.png"),
        ("imaging", "05_interior_mri_ct_room.png"),
        ("recovery", "07_interior_recovery_ward.png"),
    ]


def test_a_large_animal_folder_fills_the_equine_slots(tmp_path: Path) -> None:
    """No seeded hospital is "Large animal" today, but the design renders the list and the seed
    file is data — a hospital typed that way tomorrow must not silently fall to the default."""
    root = tmp_path / "src"
    _folder(root, "equine", [
        "01_exterior_front.png", "02_interior_barn_stocks.png", "03_interior_office_pharmacy.png",
        "04_exterior_ambulatory_truck.png", "05_interior_lab_storage.png", "06_exterior_turnout_paddock.png",
    ])
    index = PP.prepare(root, tmp_path / "out", ["equine"], {"equine": "Large animal"})
    assert [(e["slot"], e["source"]) for e in index["equine"]] == [
        ("exterior", "01_exterior_front.png"),
        ("barn", "02_interior_barn_stocks.png"),
        ("office", "03_interior_office_pharmacy.png"),
        ("truck", "04_exterior_ambulatory_truck.png"),
        ("lab", "05_interior_lab_storage.png"),
        ("grounds", "06_exterior_turnout_paddock.png"),
    ]


def test_an_unmatched_slot_takes_the_first_unused_interior_then_any_file(tmp_path: Path) -> None:
    """A slot no keyword reaches still gets a photograph, and it prefers an interior: the four
    other slots are interior subjects, so an unused exterior is the last thing that fits one.
    With nothing unused left the slot is simply not filled — never a duplicate."""
    root = tmp_path / "src"
    _folder(root, "spare", ["01_exterior_front.png", "02_interior_corridor.png",
                            "03_interior_hallway.png", "04_exterior_side.png"])
    index = PP.prepare(root, tmp_path / "out", ["spare"], {})
    assert [(e["slot"], e["source"]) for e in index["spare"]] == [
        ("exterior", "01_exterior_front.png"),
        ("lobby", "02_interior_corridor.png"),   # first unused interior
        ("exam", "03_interior_hallway.png"),     # second unused interior
        ("treatment", "04_exterior_side.png"),   # no interior left: any unused file
    ]
    assert len({e["source"] for e in index["spare"]}) == 4, "a file may fill only one slot"


def test_a_thin_folder_labels_each_photograph_with_the_slot_it_actually_fills(tmp_path: Path) -> None:
    """Three images, six slots: `kennel` matched by keyword while `exam`, `treatment` and
    `surgery` found nothing left, so the third file is the KENNEL photograph. Numbering the
    entries by position would caption a boarding run "Exam room" — the very mislabelling A-L9
    exists to stop."""
    root = tmp_path / "src"
    _folder(root, "thin3", ["01_exterior_front.png", "02_interior_reception.png", "03_interior_kennels.png"])
    index = PP.prepare(root, tmp_path / "out", ["thin3"], {})
    assert [(e["file"], e["slot"], e["source"]) for e in index["thin3"]] == [
        ("1.webp", "exterior", "01_exterior_front.png"),
        ("2.webp", "lobby", "02_interior_reception.png"),
        ("3.webp", "kennel", "03_interior_kennels.png"),
    ]


def test_an_unknown_or_missing_practice_type_takes_the_default_slot_list(tmp_path: Path) -> None:
    assert PP.slots_for("Mobile clinic") == PP.DEFAULT_SLOTS
    assert PP.slots_for("Specialty") == PP.SLOTS_BY_TYPE["Specialty"]
    root = tmp_path / "src"
    _folder(root, "odd", ["01_exterior_front.png", "02_interior_reception.png", "03_interior_exam_room.png",
                          "04_interior_treatment_area.png", "05_interior_surgery_room.png",
                          "06_interior_kennels.png"])
    unknown = PP.prepare(root, tmp_path / "unknown", ["odd"], {"odd": "Mobile clinic"})
    missing = PP.prepare(root, tmp_path / "missing", ["odd"], {})
    assert [e["slot"] for e in unknown["odd"]] == list(PP.DEFAULT_SLOTS)
    assert [e["slot"] for e in missing["odd"]] == list(PP.DEFAULT_SLOTS)


def test_select_for_slots_returns_the_chosen_files_in_slot_order(tmp_path: Path) -> None:
    """The rule on its own, with no encoding: slot order, not folder order."""
    folder = _folder(tmp_path / "src", "sel", [
        "01_exterior_front.png", "02_interior_reception.png", "03_interior_ct_imaging_room.png",
        "04_interior_treatment_area.png", "05_interior_icu.png", "06_interior_surgery_room.png",
    ])
    chosen = PP.select_for_slots(PP.source_images(folder), list(PP.SLOTS_BY_TYPE["Emergency"]))
    assert [p.name for p in chosen] == [
        "01_exterior_front.png", "02_interior_reception.png", "04_interior_treatment_area.png",
        "05_interior_icu.png", "06_interior_surgery_room.png", "03_interior_ct_imaging_room.png",
    ]


def test_main_reads_each_hospitals_type_from_the_seed_file(tmp_path: Path) -> None:
    """Which of the design's four lists a hospital's photographs fill is data, read from
    `seeds/hospitals.json` where the default slugs are read — so a hand re-run of one slug
    selects exactly the six files the full run would.

    Sharper since A-L10: the source folder is the one the committed curation names for this slug,
    so reading the WRONG slot list is not merely a differently ordered index — `validate_curation`
    refuses it and `main()` returns 2, because the curated keys would not be the type's list."""
    slug = "6666_dallas_veterinary_specialist_hospital"
    assert PP.seed_types()[slug] == "Specialty"
    assert set(PP.seed_types()) == set(PP.seed_slugs())
    curated = PP.load_curation(PP.CURATION_FILE)[slug]
    root = tmp_path / "src"
    _folder(root, slug, [name for name in curated.values() if name is not None])
    out = tmp_path / "out"
    assert PP.main(["--source", str(root), "--out", str(out), "--slugs", slug]) == 0
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["max_photos"] == 6
    assert [e["slot"] for e in index["hospitals"][slug]] == list(PP.SLOTS_BY_TYPE["Specialty"]), (
        "main() fell back to the default slot list instead of reading the seed file's type"
    )


# --- A-L10: the content-verified curation map ------------------------------------------------
# John, 2026-09-09: "explain where the image description is coming from because they don't mirror
# the file name of the image and the images don" (truncated as received) → "match the
# description". The caption
# a buyer reads is the DESIGN's fixed slot caption, so the only way a caption is TRUE is for the
# photograph at that POSITION to show that subject. A-L9 chose by filename keyword, and many of
# John's filenames lie (`ghi_veterinary_hospital/06_interior_reception.png` is an exterior sign)
# while many files are sliced fragments of a collage sheet — no keyword can fix either. The
# controller viewed every source image and wrote `seeds/hospitals/photos/curation.json`, which is
# AUTHORITATIVE for every slug it names; a slot no single photograph truthfully fills stays EMPTY,
# where the design renders its own placeholder (absent beats faked).

# One small-animal folder's worth of map: three photographs, three slots left empty.
CURATED: dict[str, str | None] = {
    "exterior": "01_exterior_front.png", "lobby": None, "exam": "03_interior_exam.png",
    "treatment": None, "surgery": None, "kennel": "05_interior_kennels.png",
}


def test_load_curation_reads_the_map_and_ignores_the_underscore_keys(tmp_path: Path) -> None:
    """`_comment` is the map's own explanation of itself and is kept in the committed file, so
    the loader has to skip it rather than read it as a hospital."""
    path = tmp_path / "curation.json"
    path.write_text(
        json.dumps({"_comment": "why this file exists",
                    "demo": {"exterior": "01_exterior_front.png", "lobby": None}}),
        encoding="utf-8",
    )
    assert PP.load_curation(path) == {"demo": {"exterior": "01_exterior_front.png", "lobby": None}}


def test_the_committed_curation_names_every_seeded_hospital_in_its_types_slot_order() -> None:
    """The map is data the pipeline trusts, so its shape is pinned here: one entry per seeded
    hospital, whose keys are exactly the slots that hospital's practice type renders, in order.
    73 of the 108 slots are filled — the other 35 have no truthful photograph in John's folders."""
    curation = PP.load_curation(PP.CURATION_FILE)
    types = PP.seed_types()
    assert set(curation) == set(PP.seed_slugs())
    for slug, slots in curation.items():
        assert list(slots) == list(PP.slots_for(types[slug])), slug
    filled = sum(1 for slots in curation.values() for name in slots.values() if name is not None)
    assert (filled, sum(len(slots) for slots in curation.values())) == (73, 108), (
        "A-L10's content-verified count moved; the plan record says 73 of 108"
    )


def test_a_curated_slug_numbers_its_files_by_slot_position(tmp_path: Path) -> None:
    """The heart of A-L10: `p.photos[i]` fills slot `i` (A12.2), so a file's NUMBER is its slot's
    position — never its rank among the files that happened to be found. Slot 3 is `3.webp` even
    though it is the second photograph in the folder."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_exterior_front.png", "03_interior_exam.png", "05_interior_kennels.png"])
    index = PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"}, {"cur": CURATED})
    assert [(e["slot"], e["file"], e["source"]) for e in index["cur"]] == [
        ("exterior", "1.webp", "01_exterior_front.png"),
        ("lobby", None, None),
        ("exam", "3.webp", "03_interior_exam.png"),
        ("treatment", None, None),
        ("surgery", None, None),
        ("kennel", "6.webp", "05_interior_kennels.png"),
    ]
    assert sorted(p.name for p in (tmp_path / "out" / "cur").iterdir()) == ["1.webp", "3.webp", "6.webp"]


def test_an_empty_slot_writes_no_file_and_carries_no_measured_fields(tmp_path: Path) -> None:
    """An empty slot is a statement, not a photograph: no bytes, no width, no sha256, and a null
    caption — the design's placeholder is what the buyer sees."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_exterior_front.png", "03_interior_exam.png", "05_interior_kennels.png"])
    index = PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"}, {"cur": CURATED})
    assert index["cur"][1] == {"slot": "lobby", "file": None, "source": None, "caption": None}


def test_a_slug_absent_from_the_curation_still_takes_the_keyword_path(tmp_path: Path) -> None:
    """The map is authoritative only for the slugs it names; anything else keeps A-L9's keyword
    selection, numbered sequentially, so the fallback the map does not cover is unchanged."""
    root = tmp_path / "src"
    _folder(root, "kw", ["01_exterior_front.png", "02_interior_reception.png"])
    index = PP.prepare(root, tmp_path / "out", ["kw"],
                       {"kw": "Small animal", "cur": "Small animal"}, {"cur": CURATED})
    assert [(e["slot"], e["file"]) for e in index["kw"]] == [("exterior", "1.webp"), ("lobby", "2.webp")]


def test_a_curated_slug_the_seed_file_does_not_name_is_refused(tmp_path: Path) -> None:
    """A slug in the map and not in `seeds/hospitals.json` is a typo that would silently curate
    nothing — the whole point of the map is that it is checked against the seeds."""
    with pytest.raises(PP.SeedDataError) as exc:
        PP.prepare(tmp_path / "src", tmp_path / "out", [], {}, {"ghost_hospital": CURATED})
    assert "ghost_hospital" in str(exc.value)


def test_curated_slots_that_are_not_the_types_list_in_order_are_refused(tmp_path: Path) -> None:
    """Order IS the mapping: the keys are read positionally, so `exam` before `lobby` would put
    the exam room under "Reception and waiting"."""
    swapped: dict[str, str | None] = {
        "exterior": None, "exam": None, "lobby": None, "treatment": None, "surgery": None, "kennel": None,
    }
    with pytest.raises(PP.SeedDataError) as exc:
        PP.prepare(tmp_path / "src", tmp_path / "out", [], {"cur": "Small animal"}, {"cur": swapped})
    assert "cur" in str(exc.value) and "lobby" in str(exc.value)


def test_a_curated_file_the_folder_does_not_hold_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "src"
    _folder(root, "cur", ["01_exterior_front.png"])
    absent: dict[str, str | None] = {
        "exterior": "01_exterior_front.png", "lobby": None, "exam": "99_absent.png",
        "treatment": None, "surgery": None, "kennel": None,
    }
    with pytest.raises(PP.SeedDataError) as exc:
        PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"}, {"cur": absent})
    assert "99_absent.png" in str(exc.value) and "cur" in str(exc.value)


def test_a_file_that_fills_two_slots_is_refused(tmp_path: Path) -> None:
    """Two slots, one photograph, two captions: one of them is false by construction."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_exterior_front.png", "03_interior_exam.png"])
    twice: dict[str, str | None] = {
        "exterior": "01_exterior_front.png", "lobby": None, "exam": "03_interior_exam.png",
        "treatment": "03_interior_exam.png", "surgery": None, "kennel": None,
    }
    with pytest.raises(PP.SeedDataError) as exc:
        PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"}, {"cur": twice})
    assert "03_interior_exam.png" in str(exc.value) and "cur" in str(exc.value)


def test_main_returns_two_when_the_curation_is_unusable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SeedDataError joins FileNotFoundError and RuntimeError on the script's existing exit-2 path."""
    bad = tmp_path / "curation.json"
    bad.write_text(json.dumps({"ghost_hospital": {}}), encoding="utf-8")
    monkeypatch.setattr(PP, "CURATION_FILE", bad)
    assert PP.main(["--source", str(tmp_path), "--out", str(tmp_path / "out"), "--slugs", "nope"]) == 2


def test_main_reads_the_committed_curation_and_reports_the_empty_slots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end through `main()`: the committed map decides, not the keywords, and the run says
    how many slots it left empty — the number the operator has to be able to see."""
    slug = "123_route66"
    curated = PP.load_curation(PP.CURATION_FILE)[slug]
    root = tmp_path / "src"
    _folder(root, slug, [name for name in curated.values() if name is not None])
    out = tmp_path / "out"
    assert PP.main(["--source", str(root), "--out", str(out), "--slugs", slug]) == 0
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert [e["file"] for e in index["hospitals"][slug]] == [
        "1.webp", "2.webp", "3.webp", "4.webp", None, "6.webp"
    ], "surgery has no truthful photograph in this folder and must stay empty"
    assert "5 files, 1 empty slots" in capsys.readouterr().out
