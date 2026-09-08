#!/usr/bin/env python3
"""Turn John's curated hospital photograph folders into the committed WebP set the API serves
(spec 2026-09-06, D3).

Reads  <source>/<slug>_individual_images/  — up to four images in folder order (filenames are
       NN_area_description.ext, so `sorted()` IS folder order), non-images and dotfiles skipped.
Writes <out>/<slug>/1.webp … 4.webp, each ≤ 1600 px on the long edge and ≤ 250 KB, with every
       piece of metadata stripped, plus <out>/index.json carrying a SHA-256 per file.

The source folders are never modified and never copied wholesale. Pillow is a DEV dependency:
this runs once, by hand; the API only ever reads the bytes this wrote.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SEEDS_FILE = ROOT / "seeds" / "hospitals.json"
DEFAULT_SOURCE = Path.home() / "Downloads" / "VIN FOUNDATION" / "Hospital images" / "ALL HOSPITAL SEED DATA"
DEFAULT_OUT = ROOT / "seeds" / "hospitals" / "photos"
FOLDER_SUFFIX = "_individual_images"

MAX_PHOTOS = 4
MAX_EDGE_PX = 1600
MAX_BYTES = 250 * 1024
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
# Quality ladder, then a dimension step. Every rung is tried in order until one lands under
# MAX_BYTES; the last rung is low enough that a photograph cannot fail to fit even when it is
# already at or below both edge sizes and so is never downscaled (verified against a
# deliberately incompressible worst case: uniform random noise, which no real photograph
# approaches — see tests/scripts/test_prepare_photos.py's `_noisy` fixture).
QUALITY_LADDER = (82, 72, 62, 52, 44, 20)
FALLBACK_EDGE_PX = 1100


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def source_images(folder: Path) -> list[Path]:
    """Every image in `folder`, in filename order. Dotfiles (.DS_Store) and non-images are out."""
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in IMAGE_SUFFIXES
    )


def caption_of(source_name: str) -> str:
    """A caption from the curated filename: `06_interior_reception_lobby.png` becomes
    "Interior — reception lobby" (pre-flight I2).

    The design's own photo slots carry six fixed captions chosen by practice type, and the API
    supplies at most four files in filename order — several hospitals' first four are all
    exteriors — so a positional mapping would mislabel them. Recording what each file actually
    shows costs nothing here and is what any display mapping will need.

    A name that does not follow the `NN_area_description.ext` convention falls back to its
    stem with underscores as spaces, capitalised."""
    stem = Path(source_name).stem
    parts = stem.split("_")
    if len(parts) >= 3 and parts[0].isdecimal():
        return f"{parts[1].capitalize()} — {' '.join(parts[2:])}"
    return stem.replace("_", " ").capitalize()


def _flattened(src: Path, max_edge: int) -> Image.Image:
    """`src` opened, EXIF-rotated, alpha flattened onto white, downscaled to `max_edge` on the
    long edge (never upscaled), and carrying no metadata — a fresh RGB image holds none."""
    with Image.open(src) as opened:
        rotated = ImageOps.exif_transpose(opened)
        rgb = rotated.convert("RGB")
    if max(rgb.size) > max_edge:
        rgb.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    clean = Image.new("RGB", rgb.size)
    clean.paste(rgb)
    return clean


def encode(src: Path, dest: Path) -> dict[str, Any]:
    """Write `src` to `dest` as WebP within both ceilings; return its inventory entry."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    for edge in (MAX_EDGE_PX, FALLBACK_EDGE_PX):
        image = _flattened(src, edge)
        for quality in QUALITY_LADDER:
            image.save(dest, format="WEBP", quality=quality, method=6)
            if dest.stat().st_size <= MAX_BYTES:
                return {
                    "file": dest.name, "source": src.name, "caption": caption_of(src.name),
                    "bytes": dest.stat().st_size, "width": image.width, "height": image.height,
                    "quality": quality, "sha256": sha256_of(dest),
                }
    raise RuntimeError(f"{src.name} will not fit in {MAX_BYTES} bytes at {FALLBACK_EDGE_PX}px/q{QUALITY_LADDER[-1]}")


def prepare(source_root: Path, out_root: Path, slugs: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Encode every slug's first `MAX_PHOTOS` photographs and write `out_root/index.json`."""
    index: dict[str, list[dict[str, Any]]] = {}
    for slug in slugs:
        folder = source_root / (slug + FOLDER_SUFFIX)
        if not folder.is_dir():
            raise FileNotFoundError(f"no photograph folder {folder}")
        destination = out_root / slug
        if destination.exists():
            shutil.rmtree(destination)  # a re-run must not leave a stale Nth file behind
        entries = [
            encode(src, destination / f"{n}.webp")
            for n, src in enumerate(source_images(folder)[:MAX_PHOTOS], start=1)
        ]
        index[slug] = entries
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "index.json").write_text(
        json.dumps(
            {"version": 1, "max_photos": MAX_PHOTOS, "max_edge_px": MAX_EDGE_PX,
             "max_bytes": MAX_BYTES, "hospitals": index},
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return index


def seed_slugs() -> list[str]:
    return [str(h["slug"]) for h in json.loads(SEEDS_FILE.read_text(encoding="utf-8"))["hospitals"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the seed hospital photographs (spec D3).")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--slugs", nargs="*", default=None)
    args = parser.parse_args(argv)
    slugs = args.slugs if args.slugs else seed_slugs()
    try:
        index = prepare(args.source, args.out, list(slugs))
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[photos] {exc}", file=sys.stderr)
        return 2
    total = sum(int(e["bytes"]) for entries in index.values() for e in entries)
    print(f"[photos] {sum(len(e) for e in index.values())} files, {total / 1024 / 1024:.1f} MB → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
