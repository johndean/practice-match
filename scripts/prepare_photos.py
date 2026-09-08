#!/usr/bin/env python3
"""Turn John's curated hospital photograph folders into the committed WebP set the API serves
(spec 2026-09-06, D3).

Reads  <source>/<slug>_individual_images/  — the six photographs the design's own photo slots
       select (A-L9; filenames are NN_area_description.ext, which is what the slots are matched
       against), non-images and dotfiles skipped.
Writes <out>/<slug>/1.webp … 6.webp, each ≤ 1600 px on the long edge and ≤ 250 KB, with every
       piece of metadata stripped, plus <out>/index.json carrying a SHA-256 and the slot each
       file fills.

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
    QUALITY_LADDER,
    encode_webp,
)

SEEDS_FILE = ROOT / "seeds" / "hospitals.json"
DEFAULT_SOURCE = Path.home() / "Downloads" / "VIN FOUNDATION" / "Hospital images" / "ALL HOSPITAL SEED DATA"
DEFAULT_OUT = ROOT / "seeds" / "hospitals" / "photos"
FOLDER_SUFFIX = "_individual_images"

# The design's detail page renders exactly six captioned photo slots per practice
# (`photoSet(p)` in Practice Match V3.dc.html) and `p.photos[i]` fills slot `i` (amendment
# A12.2), so a seventh photograph could never be displayed and a sixth must not be dropped.
# The SEED set's count, and this script's own: `app.media.encode.MAX_PHOTOS` is the
# seller-UPLOAD cap (four, spec 2026-09-08 D18, John's ruling) — a different number for a
# different surface. Only the normalisation ceilings imported above are shared.
MAX_PHOTOS = 6

# The design's four slot lists, verbatim from `photoSet(p)`, keyed by the practice type
# `seeds/hospitals.json` records. Any other type (and any slug the seed file does not name)
# takes DEFAULT_SLOTS — the list `photoSet` itself falls back to, which is what the seeds'
# "Small animal" hospitals render.
DEFAULT_SLOTS: tuple[str, ...] = ("exterior", "lobby", "exam", "treatment", "surgery", "kennel")
SLOTS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "Large animal": ("exterior", "barn", "office", "truck", "lab", "grounds"),
    "Emergency": ("exterior", "triage", "treatment", "icu", "surgery", "imaging"),
    "Specialty": ("exterior", "lobby", "consult", "surgery", "imaging", "recovery"),
}
# What each slot's subject is called in John's curated filenames, most specific first: the
# keywords are tried in this order against every file before the next keyword is tried, so
# `lobby` takes a reception photograph over a waiting-area one when the folder holds both.
# The design's caption is fixed per slot and is never stored, which is precisely why the
# photograph underneath it has to be the one the caption describes.
SLOT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "exterior": ("exterior",),
    "lobby": ("reception", "lobby", "waiting", "lounge", "check_in"),
    "exam": ("exam", "consult"),
    "consult": ("consult", "exam"),
    "treatment": ("treatment",),
    "surgery": ("surgery", "operating"),
    "kennel": ("kennel", "boarding"),
    "imaging": ("imaging", "ct_", "_ct", "mri", "xray", "x_ray", "radiolog", "diagnostic"),
    "recovery": ("recovery", "icu", "rehabilitation", "ward", "kennel", "boarding"),
    "triage": ("triage", "intake", "reception", "lobby", "waiting"),
    "icu": ("icu", "critical", "hospitalization", "kennel"),
    "barn": ("barn", "stocks", "stall"),
    "office": ("office", "pharmacy", "retail"),
    "truck": ("truck", "vehicle", "ambulatory"),
    "lab": ("lab", "storage"),
    "grounds": ("grounds", "paddock", "yard", "arena"),
}


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


def slots_for(practice_type: str) -> tuple[str, ...]:
    """The design's photo slots for a practice of this type; anything else takes the default."""
    return SLOTS_BY_TYPE.get(practice_type, DEFAULT_SLOTS)


def descriptor_of(source_name: str) -> str:
    """What a curated filename says the photograph shows: the stem with its leading `NN_` gone,
    lower-cased — `10_interior_CT_scanner_room.png` becomes `interior_ct_scanner_room`. The
    slot keywords are substring-matched against this, underscores and all, so `ct_` matches a
    CT room without also matching, say, `direct_entrance`."""
    parts = Path(source_name).stem.split("_")
    if len(parts) > 1 and parts[0].isdecimal():
        parts = parts[1:]
    return "_".join(parts).lower()


def slot_choices(files: list[Path], slots: list[str]) -> list[tuple[str, Path]]:
    """Which photograph fills which of the design's slots, in SLOT order (A-L9).

    Keyword matches first, for every slot, and only then the fallbacks: filling an unmatched
    slot as soon as it is reached would let it swallow the very interior a later slot's keyword
    names. A slot no keyword reaches takes the first unused INTERIOR (five of the six slots are
    interior subjects, so an unused exterior is the last thing that fits one) and, with none
    left, any unused file; with nothing unused at all it is left unfilled rather than duplicated.

    The slot travels with the file because a folder thinner than six slots can leave a MIDDLE
    slot empty — three images can fill `exterior`, `lobby` and `kennel` — so the caller cannot
    recover the slot by counting.
    """
    described = {src: descriptor_of(src.name) for src in files}
    taken: set[Path] = set()
    chosen: dict[str, Path] = {}
    for slot in slots:
        for keyword in SLOT_KEYWORDS[slot]:
            match = next((src for src in files if src not in taken and keyword in described[src]), None)
            if match is not None:
                chosen[slot] = match
                taken.add(match)
                break
    for slot in slots:
        if slot in chosen:
            continue
        spare = next((src for src in files if src not in taken and not described[src].startswith("exterior")), None)
        if spare is None:
            spare = next((src for src in files if src not in taken), None)
        if spare is None:
            continue
        chosen[slot] = spare
        taken.add(spare)
    return [(slot, chosen[slot]) for slot in slots if slot in chosen]


def select_for_slots(files: list[Path], slots: list[str]) -> list[Path]:
    """The photographs `slots` select, in slot order — `slot_choices` without the slot keys."""
    return [src for _slot, src in slot_choices(files, slots)]


def caption_of(source_name: str) -> str:
    """A caption from the curated filename: `06_interior_reception_lobby.png` becomes
    "Interior — reception lobby" (pre-flight I2).

    The design's own photo slots carry six fixed captions chosen by practice type, and those
    captions are what a buyer reads; since A-L9 the selection above fills each slot with the
    photograph its caption describes. This caption records what the FILE says it shows, which
    is how a slot that had to fall back is visible in the inventory rather than only on screen.

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


def prepare(
    source_root: Path, out_root: Path, slugs: list[str], types: dict[str, str]
) -> dict[str, list[dict[str, Any]]]:
    """Encode the photographs the design's slots select for every slug — `types` maps a slug to
    the practice type that chooses its slot list — and write `out_root/index.json`."""
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
        choices = slot_choices(source_images(folder), list(slots_for(types.get(slug, ""))))
        entries = [
            {**encode(src, destination / f"{n}.webp"), "slot": slot}
            for n, (slot, src) in enumerate(choices, start=1)
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


def seed_types() -> dict[str, str]:
    """slug → practice type, from the same seed file: which of the design's four slot lists a
    hospital's photographs fill. Read whatever `--slugs` says, so a hand re-run of one hospital
    selects the same six files the full run would."""
    return {str(h["slug"]): str(h["type"])
            for h in json.loads(SEEDS_FILE.read_text(encoding="utf-8"))["hospitals"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the seed hospital photographs (spec D3).")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--slugs", nargs="*", default=None)
    args = parser.parse_args(argv)
    slugs = args.slugs if args.slugs else seed_slugs()
    types = seed_types()
    try:
        index = prepare(args.source, args.out, list(slugs), types)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[photos] {exc}", file=sys.stderr)
        return 2
    total = sum(int(e["bytes"]) for entries in index.values() for e in entries)
    print(f"[photos] {sum(len(e) for e in index.values())} files, {total / 1024 / 1024:.1f} MB → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
