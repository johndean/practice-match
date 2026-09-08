"""The photo pipeline (spec 2026-09-06 D3), exercised on a temp folder of GENERATED images —
never on John's originals, which this suite must not depend on being present."""
import json
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
    block above, so the stripping has something to strip."""
    import random

    rng = random.Random(path.name)
    img = Image.new("RGB", size)
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(size[0] * size[1])])
    img.save(path, **(_metadata() if metadata else {}))


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    folder = root / "demo_hospital_individual_images"
    folder.mkdir(parents=True)
    for i, name in enumerate(
        ["01_exterior_front.png", "02_exterior_side.jpg", "03_interior_lobby.png",
         "04_interior_exam.png", "05_interior_treatment.png", "06_interior_ward.png"], start=1
    ):
        _noisy(folder / name, (2400, 1600) if i % 2 else (1200, 2000), metadata=True)
    (folder / ".DS_Store").write_bytes(b"\x00\x01junk")
    (folder / "notes.txt").write_text("not an image")
    return root


def test_source_images_are_sorted_and_exclude_non_images(source: Path) -> None:
    names = [p.name for p in PP.source_images(source / "demo_hospital_individual_images")]
    assert names == ["01_exterior_front.png", "02_exterior_side.jpg", "03_interior_lobby.png",
                     "04_interior_exam.png", "05_interior_treatment.png", "06_interior_ward.png"]


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
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The last rung of the quality ladder is small enough that a real photograph always fits,
    so the `raise RuntimeError` and both loop-exhaustion arcs are unreachable from real data —
    and 100 % branches is the gate (pre-flight C2). Shrinking MAX_BYTES to one byte is the
    only honest way to reach them."""
    monkeypatch.setattr(PP, "MAX_BYTES", 1)
    src = source / "demo_hospital_individual_images" / "01_exterior_front.png"
    with pytest.raises(RuntimeError) as exc:
        PP.encode(src, tmp_path / "out" / "1.webp")
    assert "01_exterior_front.png" in str(exc.value)


def test_main_returns_two_when_an_image_will_not_fit(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RuntimeError is one of the two exceptions main() turns into exit 2; without this the
    `RuntimeError` half of that `except` tuple is never taken."""
    monkeypatch.setattr(PP, "MAX_BYTES", 1)
    assert PP.main(["--source", str(source), "--out", str(tmp_path / "out"), "--slugs", "demo_hospital"]) == 2


def test_a_folder_with_fewer_than_four_images_yields_what_it_has(tmp_path: Path) -> None:
    root = tmp_path / "src"
    folder = root / "thin_individual_images"
    folder.mkdir(parents=True)
    _noisy(folder / "01_only.png", (900, 600))
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
    _noisy(folder / "01_small.png", (640, 480))
    PP.prepare(root, tmp_path / "out", ["small"])
    with Image.open(tmp_path / "out" / "small" / "1.webp") as img:
        assert img.size == (640, 480)


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
