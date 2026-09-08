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
    """Five named images (four kept, one dropped) plus a dotfile and a non-image, generated
    once for the whole module. Only the first is larger than MAX_EDGE_PX — mostly flat colour
    with a small noise patch, so it still compresses on the first quality rung while genuinely
    exercising the resize path; the fifth ("...treatment...") is never opened by
    `source_images()` (filename-only filtering), so it is a stub, not a real image."""
    root = tmp_path_factory.mktemp("photos-source")
    folder = root / "demo_hospital_individual_images"
    folder.mkdir()
    _flat(folder / "01_exterior_front.png", (1620, 20), patch=(40, 20))
    _flat(folder / "02_exterior_side.jpg", (24, 24), metadata=True)
    _flat(folder / "03_interior_lobby.png", (24, 24))
    _flat(folder / "04_interior_exam.png", (24, 24))
    (folder / "05_interior_treatment.png").write_bytes(b"stub, never opened by source_images()")
    (folder / ".DS_Store").write_bytes(b"\x00\x01junk")
    (folder / "notes.txt").write_text("not an image")
    return root


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
    assert names == ["01_exterior_front.png", "02_exterior_side.jpg", "03_interior_lobby.png",
                     "04_interior_exam.png", "05_interior_treatment.png"]


def test_prepare_keeps_at_most_four_in_folder_order(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    index = PP.prepare(source, out, ["demo_hospital"])
    entries = index["demo_hospital"]
    assert [e["file"] for e in entries] == ["1.webp", "2.webp", "3.webp", "4.webp"]
    assert [e["source"] for e in entries] == ["01_exterior_front.png", "02_exterior_side.jpg",
                                              "03_interior_lobby.png", "04_interior_exam.png"]


def test_every_output_is_webp_within_the_dimension_and_size_ceilings(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"])
    for path in sorted((out / "demo_hospital").glob("*.webp")):
        assert path.stat().st_size <= PP.MAX_BYTES, (path.name, path.stat().st_size)
        with Image.open(path) as img:
            assert img.format == "WEBP"
            assert max(img.size) <= PP.MAX_EDGE_PX, (path.name, img.size)


def test_the_fixture_sources_really_carry_metadata(source: Path) -> None:
    """Guards the guard: if this stops holding, `test_metadata_is_stripped` below is vacuous
    again and the stripping could be deleted with a green suite (pre-flight M2)."""
    with Image.open(source / "demo_hospital_individual_images" / "02_exterior_side.jpg") as img:
        assert img.info.get("icc_profile"), "the fixture lost its ICC profile"
        assert img.getexif().get(0x0110) == "Practice Match test camera", "the fixture lost its EXIF"


def test_metadata_is_stripped(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"])
    for path in sorted((out / "demo_hospital").glob("*.webp")):
        with Image.open(path) as img:
            assert "exif" not in img.info and "icc_profile" not in img.info and "xmp" not in img.info
            assert dict(img.getexif()) == {}, (path.name, dict(img.getexif()))


def test_the_inventory_records_a_matching_sha256_and_dimensions(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"])
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
    index = PP.prepare(source, tmp_path / "photos", ["demo_hospital"])
    assert [e["caption"] for e in index["demo_hospital"]] == [
        "Exterior — front", "Exterior — side", "Interior — lobby", "Interior — exam"
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


def test_a_folder_with_fewer_than_four_images_yields_what_it_has(tmp_path: Path) -> None:
    root = tmp_path / "src"
    folder = root / "thin_individual_images"
    folder.mkdir(parents=True)
    _flat(folder / "01_only.png", (100, 80))
    index = PP.prepare(root, tmp_path / "out", ["thin"])
    assert [e["file"] for e in index["thin"]] == ["1.webp"]


def test_a_missing_folder_is_reported_not_skipped_silently(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc:
        PP.prepare(tmp_path / "src", tmp_path / "out", ["absent"])
    assert "absent_individual_images" in str(exc.value)


def test_a_small_image_is_not_upscaled(tmp_path: Path) -> None:
    root = tmp_path / "src"
    folder = root / "small_individual_images"
    folder.mkdir(parents=True)
    _flat(folder / "01_small.png", (240, 160))
    PP.prepare(root, tmp_path / "out", ["small"])
    with Image.open(tmp_path / "out" / "small" / "1.webp") as img:
        assert img.size == (240, 160)


def test_prepare_is_idempotent_and_replaces_a_stale_output(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    first = PP.prepare(source, out, ["demo_hospital"])
    (out / "demo_hospital" / "9.webp").write_bytes(b"stale")
    second = PP.prepare(source, out, ["demo_hospital"])
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
            PP.prepare(tmp_path / "src", tmp_path / "out", [bad])
    assert keep.exists()
