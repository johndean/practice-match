#!/usr/bin/env python3
"""Turn John's curated hospital photograph folders into the committed WebP set the API serves
(spec 2026-09-06, D3).

Reads  <source>/<slug>_individual_images/  — up to four images in folder order (filenames are
       NN_area_description.ext, so `sorted()` IS folder order), non-images and dotfiles skipped.
Writes <out>/<slug>/1.webp … 4.webp, each ≤ 1600 px on the long edge and ≤ 250 KB, with every
       piece of metadata stripped, plus <out>/index.json carrying a SHA-256 per file.

The source folders are never modified and never copied wholesale. The normalisation rules
themselves (the size/byte ceilings, the quality ladder, the metadata stripping) live in
`app.media.encode`, shared with the seller-upload request path (spec 2026-09-08 D15) — this
script is the hand-run half of that pipeline; the API's is the other. Pillow is therefore a MAIN
dependency now, not dev-only: see `app/media/encode.py` for why.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image

# Unconditionally, before the `app.media.encode` import below: `python scripts/prepare_photos.py`
# puts `scripts/` on `sys.path[0]`, not the repository root — the same executability gap
# `scripts/bootstrap_admin.py` documents. Unlike those scripts, this one's constants and
# `encode_webp` are read by module-level functions the tests call directly (`PP.MAX_BYTES`,
# `PP.encode`, `PP.source_images`), not only from `main()`, so the import cannot be deferred into
# a function body without losing that surface. The insert is idempotent and costs nothing on a
# one-shot, hand-run CLI.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.media.encode import (
    FALLBACK_EDGE_PX,
    IMAGE_SUFFIXES,
    MAX_BYTES,
    MAX_EDGE_PX,
    MAX_PHOTOS,
    QUALITY_LADDER,
    encode_webp,
)

SEEDS_FILE = ROOT / "seeds" / "hospitals.json"
DEFAULT_SOURCE = Path.home() / "Downloads" / "VIN FOUNDATION" / "Hospital images" / "ALL HOSPITAL SEED DATA"
DEFAULT_OUT = ROOT / "seeds" / "hospitals" / "photos"
FOLDER_SUFFIX = "_individual_images"


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


def encode(src: Path, dest: Path) -> dict[str, Any]:
    """Write `src` to `dest` as WebP within both ceilings; return its inventory entry.

    The normalisation itself — EXIF-rotate, flatten alpha onto white, downscale, walk the quality
    ladder, strip every metadatum — is `app.media.encode.encode_webp`'s (spec 2026-09-08 D15): the
    request-path encoder and this hand-run pipeline share the one implementation so they can never
    drift apart."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    encoded = encode_webp(src.read_bytes())
    if encoded is None:
        raise RuntimeError(f"{src.name} will not fit in {MAX_BYTES} bytes at {FALLBACK_EDGE_PX}px/q{QUALITY_LADDER[-1]}")
    data, digest = encoded
    dest.write_bytes(data)
    with Image.open(dest) as image:
        width, height = image.size
    return {
        "file": dest.name, "source": src.name, "caption": caption_of(src.name),
        "bytes": len(data), "width": width, "height": height, "sha256": digest,
    }


def prepare(source_root: Path, out_root: Path, slugs: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Encode every slug's first `MAX_PHOTOS` photographs and write `out_root/index.json`."""
    index: dict[str, list[dict[str, Any]]] = {}
    for slug in slugs:
        # `--slugs` reaches this straight from argv, and the rmtree below is driven by it: a slug
        # of `../..` would delete outside `seeds/hospitals/photos` (final review M2). Refused
        # BEFORE the folder lookup, so a traversing value that happens to name a real folder is
        # still refused rather than acted on.
        if "/" in slug or slug.startswith("."):
            raise ValueError(f"{slug!r} is not a slug")
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
