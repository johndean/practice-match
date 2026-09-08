#!/usr/bin/env python3
"""Turn John's curated hospital photograph folders into the committed WebP set the API serves
(spec 2026-09-06, D3).

Reads  <source>/<slug>_individual_images/ — non-images and dotfiles skipped — and
       seeds/hospitals/photos/curation.json, the CONTENT-VERIFIED map of which photograph fills
       which of the design's six slots (A-L10). For a slug the map names, the map decides and a
       slot it leaves `null` stays empty; only a slug the map does not name falls back to A-L9's
       filename keywords, because John's filenames do not reliably describe their contents.
Writes <out>/<slug>/<k>.webp for every FILLED slot `k` (1-based, so the numbers are the design's
       slot positions and an empty slot leaves a gap), each ≤ 1600 px on the long edge and
       ≤ 250 KB, with every piece of metadata stripped, plus <out>/index.json carrying one entry
       per slot — a SHA-256 and the slot it fills, or nulls where the slot is empty.

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
CURATION_FILE = DEFAULT_OUT / "curation.json"


class SeedDataError(Exception):
    """The curation map does not describe the photographs on disk (A-L10).

    Its own class rather than a bare ValueError so `main()` can turn it into the script's exit 2
    beside FileNotFoundError and RuntimeError, and so a caller can tell "your map is wrong" from
    "your source folder is missing"."""

# The design's detail page renders exactly six captioned photo slots per practice
# (`photoSet(p)` in Practice Match V3.dc.html) and `p.photos[i]` fills slot `i` (amendment
# A12.2), so a seventh photograph could never be displayed and a sixth must not be dropped.
MAX_PHOTOS = 6
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


def load_curation(path: Path) -> dict[str, dict[str, str | None]]:
    """The content-verified map: slug → slot → the source filename whose CONTENT shows that
    slot's subject, or None where no single photograph in the folder truthfully does (A-L10).

    Keys beginning with `_` are the file's own commentary — `_comment` records who verified the
    map and how — and are not hospitals."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(slug): {str(slot): None if name is None else str(name) for slot, name in slots.items()}
        for slug, slots in raw.items()
        if not str(slug).startswith("_")
    }


def validate_curation(curation: dict[str, dict[str, str | None]], types: dict[str, str]) -> None:
    """Refuse a map that cannot mean what it says, before a single file is written.

    The slot keys are read POSITIONALLY — slot `k` becomes `<k>.webp` and fills the design's slot
    `k` — so a map whose keys are not exactly the practice type's slot list IN ORDER would put a
    photograph under someone else's caption, which is the whole defect A-L10 exists to fix. A slug
    the seed file does not name is a typo that would silently curate nothing. And one photograph
    curated for two slots means two captions of which at least one is false — checked here, over
    the whole map, rather than per slug (review i2), so a hand re-run of one hospital still
    refuses a duplicate introduced for another. Only the missing-file check is left to
    `slot_choices`, because it is the one that needs the source folders."""
    for slug, slots in curation.items():
        if slug not in types:
            raise SeedDataError(f"{slug} is curated but seeds/hospitals.json does not name it")
        expected = list(slots_for(types[slug]))
        if list(slots) != expected:
            raise SeedDataError(f"{slug}: curated slots {list(slots)} are not {expected}")
        named = [name for name in slots.values() if name is not None]
        repeated = sorted({name for name in named if named.count(name) > 1})
        if repeated:
            raise SeedDataError(f"{slug}: {', '.join(repeated)} curated for more than one slot")


def slot_choices(
    files: list[Path], slots: list[str], curated: dict[str, str | None] | None = None
) -> list[tuple[str, Path | None]]:
    """Which photograph fills which of the design's slots, in SLOT order.

    **A curated map wins outright (A-L10).** It was written by looking at every photograph, and a
    filename is not evidence of what an image shows: `06_interior_reception.png` is an exterior
    sign in one of John's folders, and several files are sliced fragments of a collage sheet. So
    when `curated` is given it is the answer — every slot it names, in its own order, with `None`
    where no photograph in the folder truthfully fills that slot. Absent beats faked: the design
    renders its own placeholder for an empty slot, and a placeholder is honest where a boarding
    run captioned "Exam room" is not.

    Without one, `keyword_choices` below still answers (A-L9), for a slug the map does not name.
    """
    if curated is not None:
        by_name = {src.name: src for src in files}
        picked: list[tuple[str, Path | None]] = []
        for slot, name in curated.items():
            if name is None:
                picked.append((slot, None))
                continue
            # The only check left here: it needs the folder, so it cannot be whole-map the way
            # `validate_curation`'s three are (review i2).
            if name not in by_name:
                raise SeedDataError(f"{slot} names {name}, which the source folder does not hold")
            picked.append((slot, by_name[name]))
        return picked
    keyed: list[tuple[str, Path | None]] = list(keyword_choices(files, slots))
    return keyed


def keyword_choices(files: list[Path], slots: list[str]) -> list[tuple[str, Path]]:
    """A-L9's selection by filename keyword, in SLOT order — the path a slug the curation map
    does not name still takes. Never leaves a slot empty while a file is unused, which is exactly
    why it could not express "this folder has no truthful reception photograph" (A-L10).

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
    """The photographs `slots` select, in slot order — `keyword_choices` without the slot keys."""
    return [src for _slot, src in keyword_choices(files, slots)]


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


def prepare(
    source_root: Path, out_root: Path, slugs: list[str], types: dict[str, str],
    curation: dict[str, dict[str, str | None]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Encode the photographs the design's slots select for every slug — `types` maps a slug to
    the practice type that chooses its slot list, `curation` is the content-verified map (A-L10)
    that decides for every slug it names — and write `out_root/index.json`.

    A file's NUMBER is its slot's position, not its rank among the files that were found: slot `k`
    writes `<k>.webp`, so `p.photos[i]` still fills the design's slot `i` (A12.2) when a slot in
    the middle is empty. An empty slot writes nothing and records nulls."""
    curated_all = curation if curation is not None else {}
    # Before a single byte is written, and over the WHOLE map rather than the slugs asked for: a
    # typo in an entry this run does not touch is still a defect in the file being committed.
    validate_curation(curated_all, types)
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
        try:
            choices = slot_choices(
                source_images(folder), list(slots_for(types.get(slug, ""))), curated_all.get(slug)
            )
        except SeedDataError as exc:
            # The slug is the operator's only way to find the entry to fix, and `slot_choices`
            # never sees it.
            raise SeedDataError(f"{slug}: {exc}") from exc
        index[slug] = [
            {**encode(src, destination / f"{n}.webp"), "slot": slot} if src is not None
            else {"slot": slot, "file": None, "source": None, "caption": None}
            for n, (slot, src) in enumerate(choices, start=1)
        ]
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
        curation = load_curation(CURATION_FILE)
        index = prepare(args.source, args.out, list(slugs), types, curation)
    except (FileNotFoundError, RuntimeError, SeedDataError) as exc:
        print(f"[photos] {exc}", file=sys.stderr)
        return 2
    filled = [e for entries in index.values() for e in entries if e["file"] is not None]
    empty = sum(1 for entries in index.values() for e in entries if e["file"] is None)
    total = sum(int(e["bytes"]) for e in filled)
    # The empty count is not a footnote: it is how many of the design's captioned slots this run
    # deliberately left for the placeholder, and the operator has to see it (A-L10).
    print(f"[photos] {len(filled)} files, {empty} empty slots, {total / 1024 / 1024:.1f} MB → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
