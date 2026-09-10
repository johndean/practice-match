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
    """Eight named images — the six the design's default slots select plus two no slot's
    keywords name — and a dotfile and a non-image, generated once for the whole module. Only the
    first is larger than MAX_EDGE_PX — mostly flat colour with a small noise patch, so it still
    compresses on the first quality rung while genuinely exercising the resize path. No slot's
    keywords name `02_exterior_side` or `08_interior_stub` and all six slots match before any
    fallback could reach them, so a regression to "the first six in folder order" (the A-L9
    failure, one rung along) fails loudly here rather than silently; since A-L11 the two of them
    are the folder's positions 7 and 8, so both must be REAL images — every photograph John
    supplies is now encoded, not only the six the slots select."""
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
    _flat(folder / "08_interior_stub.png", (24, 24))
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
    the seed kept four exteriors and dropped every interior. Positions 1-6 are the six files the
    design's own slots name, in SLOT order — `p.photos[i]` fills slot `i` (amendment A12.2).

    A-L11 (John, 2026-09-09: "render ALL images"): the six are no longer a CAP. Every other image
    of the folder follows them, in folder order, as positions 7, 8, … with no slot of its own —
    so the second exterior no slot can take is position 7 rather than a dropped photograph."""
    out = tmp_path / "photos"
    index = PP.prepare(source, out, ["demo_hospital"], {})
    entries = index["demo_hospital"]
    assert [e["file"] for e in entries] == [
        "1.webp", "2.webp", "3.webp", "4.webp", "5.webp", "6.webp", "7.webp", "8.webp",
    ]
    assert [e["slot"] for e in entries] == [*PP.DEFAULT_SLOTS, None, None]
    assert [e["source"] for e in entries] == [
        "01_exterior_front.png", "03_interior_lobby.jpg", "04_interior_exam.png",
        "05_interior_treatment.png", "06_interior_surgery.png", "07_interior_kennels.png",
        "02_exterior_side.jpg", "08_interior_stub.png",
    ], "the two images no slot names are the folder's last positions, in folder order"


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


@pytest.mark.parametrize(
    "name, expected",
    [("08_interior_ct_scanner.png", "Interior — CT scanner"),
     ("09_interior_icu.png", "Interior — ICU"),
     ("09_interior_mri_ct_room.png", "Interior — MRI CT room"),
     ("10_interior_xray_room.png", "Interior — X-ray room"),
     ("10_interior_x_ray_room.png", "Interior — X-ray room"),
     ("03_interior_er_bay.png", "Interior — ER bay"),
     ("04_interior_dvm_office.png", "Interior — DVM office"),
     # The fallback arm spells them too — a caption is read by a buyer whichever arm made it.
     ("ct suite.png", "CT suite"),
     ("x_ray.png", "X-ray"),
     # …and a word that merely CONTAINS an acronym is left alone: whole tokens only.
     ("05_interior_reception_counter.png", "Interior — reception counter"),
     ("06_interior_recovery_ward.png", "Interior — recovery ward")],
)
def test_caption_of_spells_the_acronyms_john_writes_in_lower_case(name: str, expected: str) -> None:
    """A-L11 review (m6). The filenames spell `ct`, `icu`, `mri`, `er`, `xray`/`x_ray` and `dvm`
    in lower case; a buyer reads the caption, so it says CT, ICU, MRI, ER, X-ray and DVM. Whole
    tokens only — `reception` and `recovery` contain none of them."""
    assert PP.caption_of(name) == expected


def test_the_inventory_records_a_caption_per_photograph(source: Path, tmp_path: Path) -> None:
    index = PP.prepare(source, tmp_path / "photos", ["demo_hospital"], {})
    assert [e["caption"] for e in index["demo_hospital"]] == [
        "Exterior — front", "Interior — lobby", "Interior — exam",
        "Interior — treatment", "Interior — surgery", "Interior — kennels",
        "Exterior — side", "Interior — stub",
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
    """A-L11: a slot stays empty ONLY when the folder has fewer images than the design has slots.
    The six positions are always six — the design renders six captioned slots whatever the folder
    holds — so the five the one image cannot reach are explicit empties, not a shorter list."""
    root = tmp_path / "src"
    folder = root / "thin_individual_images"
    folder.mkdir(parents=True)
    _flat(folder / "01_only.png", (100, 80))
    index = PP.prepare(root, tmp_path / "out", ["thin"], {})
    assert [e["file"] for e in index["thin"]] == ["1.webp", None, None, None, None, None]
    assert [e["slot"] for e in index["thin"]] == list(PP.DEFAULT_SLOTS)


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


def test_the_module_runs_as_a_bare_script_from_any_working_directory(tmp_path: Path) -> None:
    """`python scripts/prepare_photos.py` puts `scripts/` on `sys.path[0]`, not the repository
    root — the executability gap Task L4 found for `seed_listings.py`, mirrored here now that this
    script imports `app.media.encode` (task SL2). `cwd=tmp_path` is a directory with no relation
    to the repository, so this fails with `ModuleNotFoundError` (exit 1, no clean stderr message)
    if the `sys.path` fix at the top of the module ever regresses; it must keep returning the
    ordinary "no such folder" exit 2 instead."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prepare_photos.py"),
         "--source", str(tmp_path), "--out", str(tmp_path / "out"), "--slugs", "nope"],
        capture_output=True, text=True, check=False, cwd=tmp_path,
    )
    assert result.returncode == 2, result.stderr


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


def test_slot_count_is_the_length_of_every_design_slot_list() -> None:
    """Six is not a taste: it is how many CAPTIONED slots `photoSet(p)` renders. It is no longer
    a cap on the photographs (A-L11 — amendment A15.3 appends a tile per photograph beyond the
    sixth); it is the length of every slot list, and a list of five would leave one slot blank."""
    assert PP.SLOT_COUNT == 6
    assert not hasattr(PP, "MAX_PHOTOS"), "A-L11 retired MAX_PHOTOS: six slots, no cap"
    for label, slots in [("default", PP.DEFAULT_SLOTS), *PP.SLOTS_BY_TYPE.items()]:
        assert len(slots) == PP.SLOT_COUNT, label
        assert len(set(slots)) == PP.SLOT_COUNT, f"{label} names a slot twice"


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
        # A-L11: the four exteriors and the waiting area no slot took are not dropped — they are
        # positions 7-11, in folder order, and the design renders a tile for each (A15.3).
        (None, "02_exterior_entrance_view.png"),
        (None, "03_exterior_monument_sign.png"),
        (None, "04_exterior_street_corner_view.png"),
        (None, "05_exterior_parking_view.png"),
        (None, "07_interior_waiting_area.png"),
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
        (None, "02_exterior_monument_sign.png"),     # A-L11: positions 7 and 8, in folder order
        (None, "03_exterior_emergency_entrance.png"),
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
        (None, "02_exterior_street_side_view.png"),  # A-L11: position 7
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
        ("surgery", None),                       # nothing unused left (A-L11: a thin folder)
        ("kennel", None),
    ]
    assert len({e["source"] for e in index["spare"]}) == 5, "a file may fill only one slot"


def test_a_thin_folder_labels_each_photograph_with_the_slot_it_actually_fills(tmp_path: Path) -> None:
    """Three images, six slots: `kennel` matched by keyword while `exam`, `treatment` and
    `surgery` found nothing left, so the third file is the KENNEL photograph — and it is written
    at the KENNEL's own position, `6.webp`. Numbering the entries in the order they were chosen
    would caption a boarding run "Exam room" — the very mislabelling A-L9 exists to stop, and the
    reason A-L11 keeps the six slot positions fixed for the keyword path too."""
    root = tmp_path / "src"
    _folder(root, "thin3", ["01_exterior_front.png", "02_interior_reception.png", "03_interior_kennels.png"])
    index = PP.prepare(root, tmp_path / "out", ["thin3"], {})
    assert [(e["file"], e["slot"], e["source"]) for e in index["thin3"]] == [
        ("1.webp", "exterior", "01_exterior_front.png"),
        ("2.webp", "lobby", "02_interior_reception.png"),
        (None, "exam", None),
        (None, "treatment", None),
        (None, "surgery", None),
        ("6.webp", "kennel", "03_interior_kennels.png"),
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
    assert index["slot_count"] == 6
    assert "max_photos" not in index, "A-L11: six slots, and no cap to state"
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
    # Counted per TABLE, not as one total (Task SD1): A-L10's claim is about John's eighteen of
    # 2026-09-06 and the plan record states it as 73 of 108. The eleven Dallas hospitals of
    # 2026-09-10 are a separate verification with a stricter rule — a slot is filled only by a
    # SINGLE photograph named at high or medium confidence, never by a multi-panel sheet — and
    # most of those folders are sheets, so 22 of their 66 slots are filled and the rest are
    # backfilled in folder order by `positions`, each under its OWN description (amendment A15).
    # By NATO letter, not by "_dallas_": `6666_dallas_veterinary_specialist_hospital` is one of
    # John's eighteen and is in Dallas too.
    dallas = {slug for slug in curation
              if slug.split("_", 1)[0] in {"alpha", "beta", "charlie", "delta", "echo", "foxtrot",
                                           "hotel", "indigo", "juliet", "kilo", "lima"}}
    assert len(dallas) == 11, sorted(dallas)

    def counted(slugs: set[str]) -> tuple[int, int]:
        chosen = {slug: slots for slug, slots in curation.items() if slug in slugs}
        return (sum(1 for slots in chosen.values() for name in slots.values() if name is not None),
                sum(len(slots) for slots in chosen.values()))

    assert counted(set(curation) - dallas) == (73, 108), (
        "A-L10's content-verified count moved; the plan record says 73 of 108"
    )
    assert counted(dallas) == (22, 66), "Task SD1's content-verified count moved"


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
    assert [(e["slot"], e["file"]) for e in index["kw"]] == [
        ("exterior", "1.webp"), ("lobby", "2.webp"),
        ("exam", None), ("treatment", None), ("surgery", None), ("kennel", None),
    ]


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


TWICE: dict[str, str | None] = {
    "exterior": "01_exterior_front.png", "lobby": None, "exam": "03_interior_exam.png",
    "treatment": "03_interior_exam.png", "surgery": None, "kennel": None,
}


def test_a_file_that_fills_two_slots_is_refused(tmp_path: Path) -> None:
    """Two slots, one photograph, two captions: one of them is false by construction."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_exterior_front.png", "03_interior_exam.png"])
    with pytest.raises(PP.SeedDataError) as exc:
        PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"}, {"cur": TWICE})
    assert "03_interior_exam.png" in str(exc.value) and "cur" in str(exc.value)


def test_a_duplicate_is_refused_even_in_a_slug_this_run_is_not_processing(tmp_path: Path) -> None:
    """Review i2. The duplicate check belongs with the slug/slot-order checks, over the WHOLE map
    and before a single byte is written: a hand re-run of one hospital (`--slugs X`) must still
    refuse a duplicate someone introduced for hospital Y, because the file being committed is the
    map, not the run. Only the missing-file arm has to stay per-slug — it needs the folders."""
    with pytest.raises(PP.SeedDataError) as exc:
        PP.prepare(tmp_path / "src", tmp_path / "out", [], {"cur": "Small animal"}, {"cur": TWICE})
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


# --- A-L11: every uploaded photograph renders ---------------------------------------------------
# John, 2026-09-09: "HAS FAILED and wiped out all the images - if the logic is trying to match and
# failing then surface all images uploaded and have the user articulate what it is and render ALL
# images - what was 9 images now are only showing 3 after this hotfix!!!". A-L10's empty-slot rule
# dropped every photograph that matched none of the design's six fixed captions. The rule is now
# the opposite: the curation still says WHICH image best fits a slot, every other image of the
# folder fills a still-empty slot in folder order, and whatever is left becomes positions 7, 8, …
# — never dropped. A slot is empty only when the folder is thinner than six.

# The same map as CURATED above, against a folder that holds four images it does not name.
def test_a_curated_slug_fills_its_empty_slots_from_the_rest_of_the_folder(tmp_path: Path) -> None:
    """A-L11's heart. The curated photographs keep their own slots — `05_interior_kennels.png` is
    the KENNEL's, at position 6, even though two later-numbered files were placed before it — and
    the composites and sliced sheets A-L10 discarded fill what is left, in folder order."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_exterior_front.png", "02_collage_sheet.png", "03_interior_exam.png",
                          "04_sliced_fragment.png", "05_interior_kennels.png", "06_spare.png",
                          "07_spare.png"])
    index = PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"}, {"cur": CURATED})
    assert [(e["file"], e["slot"], e["source"]) for e in index["cur"]] == [
        ("1.webp", "exterior", "01_exterior_front.png"),
        ("2.webp", "lobby", "02_collage_sheet.png"),
        ("3.webp", "exam", "03_interior_exam.png"),
        ("4.webp", "treatment", "04_sliced_fragment.png"),
        ("5.webp", "surgery", "06_spare.png"),
        ("6.webp", "kennel", "05_interior_kennels.png"),
        ("7.webp", None, "07_spare.png"),
    ]
    assert sorted(p.name for p in (tmp_path / "out" / "cur").iterdir()) == [
        "1.webp", "2.webp", "3.webp", "4.webp", "5.webp", "6.webp", "7.webp",
    ], "no photograph of the folder is dropped"


def test_an_extra_photograph_carries_its_own_description_and_no_slot(tmp_path: Path) -> None:
    """Positions beyond the design's six have no fixed caption to be true of, so the ONE
    description we hold — the supplier's own filename — is what they carry (amendment A15.3
    renders it, falling back to "Photo N" when there is none). `slot` is null: the entry is a
    photograph, not one of the design's captioned slots."""
    root = tmp_path / "src"
    _folder(root, "extra", ["01_exterior_front.png", "02_interior_reception.png",
                            "03_interior_exam_room.png", "04_interior_treatment_area.png",
                            "05_interior_surgery_room.png", "06_interior_kennels.png",
                            "07_interior_pharmacy_counter.png"])
    entry = PP.prepare(root, tmp_path / "out", ["extra"], {"extra": "Small animal"})["extra"][6]
    assert entry["slot"] is None
    assert entry["caption"] == "Interior — pharmacy counter"
    assert entry["source"] == "07_interior_pharmacy_counter.png"
    assert entry["file"] == "7.webp" and entry["sha256"] and entry["bytes"] > 0


def test_positions_puts_the_slots_first_then_the_rest_in_folder_order(tmp_path: Path) -> None:
    """The rule on its own, with no encoding: the design's six slots in SLOT order, each holding
    the photograph chosen for it or the next unused one, then every remaining image in FOLDER
    order with no slot at all."""
    folder = _folder(tmp_path / "src", "pos", [
        "01_exterior_front.png", "02_interior_reception.png", "03_interior_exam_room.png",
        "04_interior_treatment_area.png", "05_interior_surgery_room.png",
        "06_interior_kennels.png", "07_zzz.png", "08_zzz.png",
    ])
    placed = PP.positions(PP.source_images(folder), list(PP.DEFAULT_SLOTS))
    assert [(slot, None if src is None else src.name) for slot, src in placed] == [
        ("exterior", "01_exterior_front.png"), ("lobby", "02_interior_reception.png"),
        ("exam", "03_interior_exam_room.png"), ("treatment", "04_interior_treatment_area.png"),
        ("surgery", "05_interior_surgery_room.png"), ("kennel", "06_interior_kennels.png"),
        (None, "07_zzz.png"), (None, "08_zzz.png"),
    ]


def test_main_reports_the_photographs_beyond_the_designs_six(
    source: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The operator has to see that nothing was dropped (A-L11), so the run says how many
    photographs went past the design's six slots as well as how many slots stayed empty."""
    assert PP.main(["--source", str(source), "--out", str(tmp_path / "out"),
                    "--slugs", "demo_hospital"]) == 0
    assert "8 files, 0 empty slots, 2 beyond the design's six slots" in capsys.readouterr().out


# ======================================================================================
# Task SD1 — a photograph's OWN description, the flags the content verification raised on it,
# and a run that adds a folder without rewriting the ones already committed.
#
# John's Dallas filenames are `alpha_dallas_01.png`: they say nothing at all about what the
# image shows, so `caption_of` cannot describe them and the keyword path cannot slot them.
# A separate content verification read all 119 and produced, per image, a description, a
# best-fit slot and a confidence. Two committed files carry its answers:
#
#   curation.json     — slot → filename, as A-L10 already defines it. A photograph fills a slot
#                       ONLY where the verification named that slot at high or medium
#                       confidence; everything else keeps folder order in the remaining
#                       positions, which amendment A15.3 renders as tiles of their own.
#   descriptions.json — filename → {description, flags}. The description is the photograph's
#                       OWN caption (`photo_captions` → `p.photoCaptions[i]`, amendment A15), so
#                       no photograph is ever captioned by a slot that does not describe it.
#
# `flags` is the content verification's own note about identifiable content, carried through to
# the committed inventory so the image-identifiability pipeline (A-IDP-1..6, another branch) has
# it when it runs. Carrying it is NOT publishing it: those seeds default to NOT SHOW, and
# nothing here decides what is displayed. A flag is ABSENT rather than empty where nothing was
# raised, so the 195 entries the eighteen already committed do not move.
# ======================================================================================


def _described(tmp_path: Path) -> Path:
    path = tmp_path / "descriptions.json"
    path.write_text(json.dumps({
        "_comment": "why this file exists",
        "demo": {
            "01_exterior_front.png": {
                "description": "Brick single-storey clinic behind a low hedge",
                "flags": ["own_business_name"],
            },
            "04_interior_exam.png": {"description": "Stainless exam table under a window"},
        },
    }), encoding="utf-8")
    return path


def test_load_descriptions_reads_the_map_and_ignores_the_underscore_keys(tmp_path: Path) -> None:
    loaded = PP.load_descriptions(_described(tmp_path))
    assert set(loaded) == {"demo"}
    assert loaded["demo"]["01_exterior_front.png"] == {
        "description": "Brick single-storey clinic behind a low hedge",
        "flags": ["own_business_name"], "refused": None,
    }
    assert loaded["demo"]["04_interior_exam.png"] == {
        "description": "Stainless exam table under a window", "flags": [], "refused": None,
    }


def test_a_described_photograph_is_captioned_by_its_description_not_its_filename(
    source: Path, tmp_path: Path
) -> None:
    """The whole point: `caption_of("01_exterior_front.png")` would say "Exterior — front",
    which happens to be true here and says nothing at all for `alpha_dallas_01.png`."""
    index = PP.prepare(source, tmp_path / "out", ["demo_hospital"], {},
                       descriptions={"demo_hospital": {
                           "01_exterior_front.png": {"description": "Brick clinic behind a hedge",
                                                     "flags": [], "refused": None}}})
    exterior = next(e for e in index["demo_hospital"] if e["source"] == "01_exterior_front.png")
    assert exterior["caption"] == "Brick clinic behind a hedge"


def test_a_photograph_nobody_described_keeps_the_filename_caption(
    source: Path, tmp_path: Path
) -> None:
    """The eighteen have no descriptions file at all and must be unaffected; within the eleven,
    a photograph the verification skipped falls back the same way."""
    index = PP.prepare(source, tmp_path / "out", ["demo_hospital"], {},
                       descriptions={"demo_hospital": {
                           "01_exterior_front.png": {"description": "Brick clinic", "flags": [], "refused": None}}})
    other = next(e for e in index["demo_hospital"] if e["source"] == "04_interior_exam.png")
    assert other["caption"] == PP.caption_of("04_interior_exam.png")


def test_a_flagged_photograph_carries_its_flags_into_the_inventory(
    source: Path, tmp_path: Path
) -> None:
    index = PP.prepare(source, tmp_path / "out", ["demo_hospital"], {},
                       descriptions={"demo_hospital": {
                           "01_exterior_front.png": {"description": "Signed frontage",
                                                     "flags": ["own_business_name", "own_street_number"], "refused": None}}})
    exterior = next(e for e in index["demo_hospital"] if e["source"] == "01_exterior_front.png")
    assert exterior["flags"] == ["own_business_name", "own_street_number"]


def test_an_unflagged_photograph_carries_no_flags_key_at_all(source: Path, tmp_path: Path) -> None:
    """Absent, not empty: the 195 entries already committed for John's eighteen must not move,
    and `{}.get("flags", [])` is what the identifiability pipeline reads either way."""
    index = PP.prepare(source, tmp_path / "out", ["demo_hospital"], {},
                       descriptions={"demo_hospital": {
                           "01_exterior_front.png": {"description": "Brick clinic", "flags": [], "refused": None}}})
    for entry in index["demo_hospital"]:
        assert "flags" not in entry, entry["source"]


def test_a_described_file_the_folder_does_not_hold_is_refused(source: Path, tmp_path: Path) -> None:
    """The same care `slot_choices` takes with the curation: a description keyed to a filename
    that is not there is a typo that would silently caption nothing, and it names the slug."""
    with pytest.raises(PP.SeedDataError) as exc:
        PP.prepare(source, tmp_path / "out", ["demo_hospital"], {},
                   descriptions={"demo_hospital": {"99_not_here.png": {"description": "x", "flags": [], "refused": None}}})
    assert "demo_hospital" in str(exc.value) and "99_not_here.png" in str(exc.value)


def test_merge_keeps_the_slugs_this_run_did_not_process(source: Path, tmp_path: Path) -> None:
    """Task SD1's operational need: eleven folders are added to a tree that already holds
    eighteen, and re-encoding the eighteen is both wasteful and a diff nobody asked for. With
    `--merge` a narrow run REPLACES its own slugs and leaves every other one exactly as it was."""
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"], {})
    before = json.loads((out / "index.json").read_text(encoding="utf-8"))["hospitals"]["demo_hospital"]
    second = tmp_path / "src2"
    (second / "other_individual_images").mkdir(parents=True)
    _flat(second / "other_individual_images" / "01_exterior_front.png", (300, 200))
    index = PP.prepare(second, out, ["other"], {}, merge=True)
    assert set(index) == {"demo_hospital", "other"}
    written = json.loads((out / "index.json").read_text(encoding="utf-8"))["hospitals"]
    assert written["demo_hospital"] == before, "merge rewrote a slug this run never touched"
    assert (out / "demo_hospital" / "1.webp").exists()


def test_without_merge_a_narrow_run_still_replaces_the_whole_index(
    source: Path, tmp_path: Path
) -> None:
    """Characterisation of the behaviour that has always been there, pinned so `merge` cannot
    become the silent default: without the flag the index is exactly this run's slugs."""
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"], {})
    second = tmp_path / "src3"
    (second / "other_individual_images").mkdir(parents=True)
    _flat(second / "other_individual_images" / "01_exterior_front.png", (300, 200))
    index = PP.prepare(second, out, ["other"], {})
    assert set(index) == {"other"}
    assert set(json.loads((out / "index.json").read_text(encoding="utf-8"))["hospitals"]) == {"other"}


def test_merge_on_a_tree_with_no_index_yet_simply_starts_empty(source: Path, tmp_path: Path) -> None:
    index = PP.prepare(source, tmp_path / "fresh", ["demo_hospital"], {}, merge=True)
    assert set(index) == {"demo_hospital"}


def test_main_merges_when_asked_and_reads_the_committed_descriptions(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "photos"
    assert PP.main(["--source", str(source), "--out", str(out), "--slugs", "demo_hospital"]) == 0
    second = tmp_path / "src4"
    (second / "other_individual_images").mkdir(parents=True)
    _flat(second / "other_individual_images" / "01_exterior_front.png", (300, 200))
    monkeypatch.setattr(PP, "DESCRIPTIONS_FILE", _described(tmp_path))
    assert PP.main(["--source", str(second), "--out", str(out), "--slugs", "other", "--merge"]) == 0
    written = json.loads((out / "index.json").read_text(encoding="utf-8"))["hospitals"]
    assert set(written) == {"demo_hospital", "other"}


def test_main_returns_two_when_the_descriptions_file_is_unusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "descriptions.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(PP, "DESCRIPTIONS_FILE", bad)
    assert PP.main(["--source", str(tmp_path), "--out", str(tmp_path / "out"), "--slugs", "nope"]) == 2


def test_a_missing_descriptions_file_is_simply_no_descriptions(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """John's eighteen have none and must keep working: absent is "nobody described these",
    not an error."""
    monkeypatch.setattr(PP, "DESCRIPTIONS_FILE", tmp_path / "nowhere.json")
    assert PP.main(["--source", str(source), "--out", str(tmp_path / "out"),
                    "--slugs", "demo_hospital"]) == 0


# --- Task SD1, the two rules the content verification's answers imposed on the pipeline ---------
#
# (1) A photograph the verification REFUSED is never encoded, and the file says why. A-L11's
#     "nothing John supplies is ever dropped" is about the pipeline silently losing images to a
#     filename it could not match — it was never a licence to publish an image carrying a THIRD
#     PARTY's business name, a legible licence plate or an identifiable face. A refusal is
#     therefore DATA in the repository, not an operator deleting a file from a staging folder:
#     the next person to run this reproduces the same set.
#
# (2) A COMPOSITE NEVER OCCUPIES ONE OF THE DESIGN'S SIX CAPTIONED SLOTS — not even when that
#     leaves the slot EMPTY (controller ruling, SD1 fix round 1, C1: option (b), not (a)).
#
#     A sheet of six pictures, or a two-panel letterbox strip, is not "the reception area", and
#     a square tile the design built for one photograph is a presentation it never contemplated
#     for a contact sheet. Absent beats faked, which is the project's first rule about the
#     approved design. So the rule has two halves and neither of them is "prefer a single":
#     the curation refuses to PLACE a composite in a slot, and the BACKFILL that fills a slot
#     the curation left empty draws only from the SINGLE photographs. When a slug runs out of
#     singles, its remaining captioned slots STAY NULL and the design renders its own
#     placeholder for them — which is what A-L10 built that path for.
#
#     Nothing is dropped: A-L11 is untouched. EVERY composite still reaches a position past the
#     sixth, where amendment A15.3 gives it a tile of its own captioned with its own
#     description. What changes is only WHICH position, never WHETHER.
#
#     With no composites declared — John's eighteen of 2026-09-06, which have no descriptions
#     file at all — every pick is `spare[0]` and the backfill is folder order exactly as it has
#     always been. The characterisation case below pins that, and their 195 committed entries
#     are unmoved.


def test_a_refused_photograph_is_never_encoded_and_the_reason_is_kept(
    source: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    described = {"demo_hospital": {
        "02_exterior_side.jpg": {"description": None, "flags": [],
                                 "refused": "wall signage names a third party"}}}
    index = PP.prepare(source, out, ["demo_hospital"], {}, descriptions=described)
    assert "02_exterior_side.jpg" not in [e["source"] for e in index["demo_hospital"]]
    assert not any(e["source"] == "02_exterior_side.jpg" for e in index["demo_hospital"])
    # …and the seven that remain are all there: a refusal removes one photograph, not the folder.
    assert len([e for e in index["demo_hospital"] if e["file"] is not None]) == 7


def test_load_descriptions_reads_a_refusal_and_tolerates_a_missing_description(
    tmp_path: Path
) -> None:
    path = tmp_path / "descriptions.json"
    path.write_text(json.dumps({
        "demo": {"x.png": {"refused": "third-party business name"},
                 "y.png": {"description": "A lobby", "note": "the verifier's own sentence"}},
    }), encoding="utf-8")
    loaded = PP.load_descriptions(path)
    assert loaded["demo"]["x.png"]["refused"] == "third-party business name"
    assert loaded["demo"]["x.png"]["description"] is None
    assert loaded["demo"]["y.png"] == {"description": "A lobby", "flags": [], "refused": None}


def test_a_composite_never_backfills_one_of_the_designs_captioned_slots(tmp_path: Path) -> None:
    """Two images, six slots, the curation placing neither. The composite is FIRST in folder
    order, so the plain queue would have made it the exterior — the design's hero. The single
    takes the exterior instead, and the sheet does NOT slide into `lobby`: it takes a position
    past the sixth (C1, option (b)) and `lobby` is left for the design's own placeholder."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_sheet.png", "02_single.png"])
    index = PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"},
                       curation={"cur": dict.fromkeys(PP.DEFAULT_SLOTS)},
                       descriptions={"cur": {
                           "01_sheet.png": {"description": "Six-panel contact sheet",
                                            "flags": ["composite"], "refused": None},
                           "02_single.png": {"description": "Brick frontage",
                                             "flags": [], "refused": None}}})
    assert [(e["slot"], e["source"]) for e in index["cur"] if e["file"] is not None] == [
        ("exterior", "02_single.png"), (None, "01_sheet.png"),
    ]
    assert [e["slot"] for e in index["cur"]] == [*PP.DEFAULT_SLOTS, None]


def test_with_no_composites_declared_the_backfill_is_folder_order_exactly_as_before(
    tmp_path: Path
) -> None:
    """Characterisation: John's eighteen declare no composites, so their backfill must not move.
    Same two files, no flags — the first in folder order is the exterior again."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_sheet.png", "02_single.png"])
    index = PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"},
                       curation={"cur": dict.fromkeys(PP.DEFAULT_SLOTS)})
    assert [(e["slot"], e["source"]) for e in index["cur"] if e["file"] is not None] == [
        ("exterior", "01_sheet.png"), ("lobby", "02_single.png"),
    ]


def test_a_folder_of_nothing_but_composites_leaves_every_captioned_slot_empty(
    tmp_path: Path
) -> None:
    """C1, the half option (a) got wrong. Seven contact sheets and no single photograph: the six
    captioned slots stay NULL — the design renders its own placeholder in each — and all seven
    sheets take positions of their own past the sixth, where A15.3 gives each a tile. Nothing is
    dropped; everything is rendered; nothing is captioned by a slot that does not describe it."""
    root = tmp_path / "src"
    _folder(root, "cur", [f"0{n}_sheet.png" for n in range(1, 8)])
    index = PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"},
                       curation={"cur": dict.fromkeys(PP.DEFAULT_SLOTS)},
                       descriptions={"cur": {f"0{n}_sheet.png": {
                           "description": f"Sheet {n}", "flags": ["composite"], "refused": None}
                           for n in range(1, 8)}})
    assert [e["slot"] for e in index["cur"]] == [*PP.DEFAULT_SLOTS, *[None] * 7]
    assert [e["file"] for e in index["cur"][:6]] == [None] * 6, "a sheet took a captioned slot"
    assert len([e for e in index["cur"] if e["file"] is not None]) == 7, "a sheet was dropped"
    assert [e["source"] for e in index["cur"][6:]] == [f"0{n}_sheet.png" for n in range(1, 8)]


def test_the_singles_fill_the_captioned_slots_and_the_composites_queue_behind_them(
    tmp_path: Path
) -> None:
    """The mixed case, which is every one of John's eleven. Two singles and three sheets, six
    slots: the two singles take the first two captioned slots in folder order, the other four
    slots stay empty rather than taking a sheet, and the three sheets take positions 7, 8, 9."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_sheet.png", "02_single.png", "03_sheet.png", "04_single.png",
                          "05_sheet.png"])
    index = PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"},
                       curation={"cur": dict.fromkeys(PP.DEFAULT_SLOTS)},
                       descriptions={"cur": {
                           name: {"description": name, "refused": None,
                                  "flags": ["composite"] if "sheet" in name else []}
                           for name in ("01_sheet.png", "02_single.png", "03_sheet.png",
                                        "04_single.png", "05_sheet.png")}})
    assert [(e["slot"], e["source"]) for e in index["cur"]] == [
        ("exterior", "02_single.png"), ("lobby", "04_single.png"),
        ("exam", None), ("treatment", None), ("surgery", None), ("kennel", None),
        (None, "01_sheet.png"), (None, "03_sheet.png"), (None, "05_sheet.png"),
    ]


def test_an_empty_slot_left_by_the_composite_rule_carries_no_measured_fields(
    tmp_path: Path
) -> None:
    """A slot a sheet was kept out of is the SAME empty slot A-L10 already defined: no bytes, no
    caption, no source. It must not become a third shape of entry."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_sheet.png"])
    index = PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"},
                       curation={"cur": dict.fromkeys(PP.DEFAULT_SLOTS)},
                       descriptions={"cur": {"01_sheet.png": {
                           "description": "A sheet", "flags": ["composite"], "refused": None}}})
    for entry in index["cur"][:6]:
        assert entry == {"slot": entry["slot"], "file": None, "source": None, "caption": None}


def test_a_description_entry_that_says_nothing_at_all_is_refused(tmp_path: Path) -> None:
    """Neither a description nor a refusal is not a third state — it is a typo that would reach
    the inventory as a `null` caption, in a slot whose filename fallback has just been
    overridden out. Named with its slug and its file, where the operator can act on it."""
    path = tmp_path / "descriptions.json"
    path.write_text(json.dumps({"demo": {"x.png": {"flags": ["composite"]}}}), encoding="utf-8")
    with pytest.raises(PP.SeedDataError) as exc:
        PP.load_descriptions(path)
    assert "demo" in str(exc.value) and "x.png" in str(exc.value)


# --- NEW-1: the curation cannot place a composite in a captioned slot either ------------------
#
# The re-review's required fix, and the same defect as C1 in a new location: `positions()` keeps
# a sheet out of the BACKFILL, and three records said "the curation refuses to place one" — but
# nothing refused it. A curation naming a contact sheet for `exterior` put it in the design's
# HERO slot with no gate failing. The guarantee is now made true in code rather than asserted in
# prose: `validate_curation` refuses the map, before a byte is written, naming the slug, the slot
# and the file.
#
# `validate_curation` rather than a silent divert in `positions()`: a curated composite is an
# AUTHORING mistake in a committed file, and the three sentences say the curation refuses it.
# Diverting would make the sentences true and the mistake invisible.


def _sheet_curation(tmp_path: Path, slot: str) -> tuple[Path, dict, dict]:
    root = tmp_path / "src"
    _folder(root, "cur", ["01_sheet.png", "02_single.png"])
    curated = dict.fromkeys(PP.DEFAULT_SLOTS)
    curated[slot] = "01_sheet.png"
    described = {"cur": {
        "01_sheet.png": {"description": "Six-panel contact sheet", "flags": ["composite"],
                         "refused": None},
        "02_single.png": {"description": "Brick frontage", "flags": [], "refused": None}}}
    return root, {"cur": curated}, described


@pytest.mark.parametrize("slot", ["exterior", "kennel"])
def test_a_curation_that_places_a_composite_in_a_captioned_slot_is_refused(
    tmp_path: Path, slot: str
) -> None:
    """Both ends of the captioned band: `exterior` is the hero the reviewer demonstrated, and
    `kennel` is the sixth, so the refusal is not an off-by-one on the first slot alone."""
    root, curation, described = _sheet_curation(tmp_path, slot)
    with pytest.raises(PP.SeedDataError) as exc:
        PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"},
                   curation=curation, descriptions=described)
    message = str(exc.value)
    assert "cur" in message and slot in message and "01_sheet.png" in message, message


def test_the_refusal_happens_before_a_single_byte_is_written(tmp_path: Path) -> None:
    """`validate_curation`'s own promise — "before a single file is written" — extended to this
    check. A run that refuses leaves no half-written tree for the next run to merge."""
    root, curation, described = _sheet_curation(tmp_path, "exterior")
    out = tmp_path / "out"
    with pytest.raises(PP.SeedDataError):
        PP.prepare(root, out, ["cur"], {"cur": "Small animal"},
                   curation=curation, descriptions=described)
    assert not (out / "cur").exists() and not (out / "index.json").exists()


def test_the_whole_map_is_checked_not_only_the_slugs_this_run_processes(tmp_path: Path) -> None:
    """The shape `validate_curation`'s other three checks already have (review i2): a curated
    composite in a slug this run is not touching is still a defect in the file being committed,
    so a hand re-run of one hospital cannot launder it."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_single.png"])
    curation = {"cur": dict.fromkeys(PP.DEFAULT_SLOTS),
                "other": {**dict.fromkeys(PP.DEFAULT_SLOTS), "lobby": "99_sheet.png"}}
    described = {"cur": {"01_single.png": {"description": "A front", "flags": [], "refused": None}},
                 "other": {"99_sheet.png": {"description": "A sheet", "flags": ["composite"],
                                            "refused": None}}}
    with pytest.raises(PP.SeedDataError) as exc:
        PP.prepare(root, tmp_path / "out", ["cur"],
                   {"cur": "Small animal", "other": "Small animal"},
                   curation=curation, descriptions=described)
    assert "other" in str(exc.value) and "99_sheet.png" in str(exc.value)


def test_a_curated_single_photograph_is_still_placed_normally(tmp_path: Path) -> None:
    """The refusal must not have made the curation useless: a SINGLE photograph curated for a
    captioned slot goes exactly where the map says, which is A-L10's whole point."""
    root = tmp_path / "src"
    _folder(root, "cur", ["01_sheet.png", "02_single.png"])
    curated = dict.fromkeys(PP.DEFAULT_SLOTS)
    curated["exam"] = "02_single.png"
    index = PP.prepare(root, tmp_path / "out", ["cur"], {"cur": "Small animal"},
                       curation={"cur": curated},
                       descriptions={"cur": {
                           "01_sheet.png": {"description": "A sheet", "flags": ["composite"],
                                            "refused": None},
                           "02_single.png": {"description": "A front", "flags": [],
                                             "refused": None}}})
    placed = next(e for e in index["cur"] if e["source"] == "02_single.png")
    assert placed["slot"] == "exam"
    # …and the sheet is still rendered, past the captioned six.
    sheet = next(e for e in index["cur"] if e["source"] == "01_sheet.png")
    assert sheet["slot"] is None


def test_the_committed_curation_places_no_composite_in_any_captioned_slot() -> None:
    """The mutation probe, against the real committed data: every file the curation names must be
    a single photograph. This is what would have caught the defect on the day it was written."""
    curation = PP.load_curation(PP.CURATION_FILE)
    described = PP.load_descriptions(PP.DESCRIPTIONS_FILE)
    offenders = [
        (slug, slot, name)
        for slug, slots in curation.items()
        for slot, name in slots.items()
        if name is not None and "composite" in described.get(slug, {}).get(name, {}).get("flags", [])
    ]
    assert offenders == [], offenders
