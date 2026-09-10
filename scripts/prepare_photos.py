#!/usr/bin/env python3
"""Turn John's curated hospital photograph folders into the committed WebP set the API serves
(spec 2026-09-06, D3).

Reads  <source>/<slug>_individual_images/ — non-images and dotfiles skipped — and
       seeds/hospitals/photos/curation.json, the CONTENT-VERIFIED map of which photograph fills
       which of the design's six slots (A-L10). For a slug the map names, the map decides WHICH
       image best fits a slot; only a slug the map does not name falls back to A-L9's filename
       keywords, because John's filenames do not reliably describe their contents.
Writes <out>/<slug>/<k>.webp for EVERY photograph of the folder (A-L11), each ≤ 1600 px on the
       long edge and ≤ 250 KB, with every piece of metadata stripped, plus <out>/index.json
       carrying one entry per position — a SHA-256, the supplier's own description and the slot
       it fills, or nulls for a slot the folder is too thin to fill.

**Nothing John supplies is ever dropped (A-L11, 2026-09-09: "render ALL images").** Positions
1-6 are the design's six captioned slots for the practice type; the curation places what it
names, every remaining image fills a still-empty slot in FOLDER order — composites and sliced
sheets included, they are John's material — and whatever is left becomes positions 7, 8, …,
which amendment A15.3 renders as tiles of their own. A-L10's rule that an unmatched slot stays
empty is superseded: a slot is empty only when the folder holds fewer images than the design
has slots.

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
CURATION_FILE = DEFAULT_OUT / "curation.json"
# Task SD1. One description per SOURCE photograph, and whatever the content verification flagged
# on it. Separate from `curation.json` because the two answer different questions: the curation
# says which photograph belongs in which of the design's six captioned SLOTS, this says what each
# photograph actually SHOWS. John's Dallas filenames (`alpha_dallas_01.png`) say neither, so
# `caption_of` has nothing to read and A-L9's keyword path has nothing to match — the words have
# to come from somewhere, and the somewhere is a human (or a verified reader) looking at the
# image. Absent is not an error: John's eighteen of 2026-09-06 predate this file and their
# captions still come from their own descriptive filenames.
DESCRIPTIONS_FILE = DEFAULT_OUT / "descriptions.json"


class SeedDataError(Exception):
    """The curation map does not describe the photographs on disk (A-L10).

    Its own class rather than a bare ValueError so `main()` can turn it into the script's exit 2
    beside FileNotFoundError and RuntimeError, and so a caller can tell "your map is wrong" from
    "your source folder is missing"."""

# The design's detail page renders six CAPTIONED photo slots per practice (`photoSet(p)` in
# Practice Match V3.dc.html) and `p.photos[i]` fills slot `i` (amendment A12.2). It is the
# length of every slot list below, and since A-L11 it is no longer a cap on the photographs:
# amendment A15.3 appends a tile of its own for every photograph beyond the sixth. The
# normalisation ceilings it used to sit beside now live in `app.media.encode`, imported above
# and shared with the seller-upload request path (spec 2026-09-08 D15).
SLOT_COUNT = 6

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


def load_descriptions(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """slug -> source filename -> {"description": str|None, "flags": list[str], "refused": str|None}.

    `refused` is a REASON, and a photograph carrying one is never encoded (Task SD1). A-L11's
    "nothing John supplies is ever dropped" is about the pipeline silently losing an image to a
    filename it could not match; it was never a licence to publish one carrying a THIRD PARTY's
    business name, a legible licence plate or an identifiable face. Keeping the refusal here, in
    the repository, is what makes the committed set reproducible — the alternative, an operator
    quietly leaving a file out of a staging folder, leaves no trace at all. `description` is
    absent on a refused entry, because nothing describes a photograph nobody may see.

    Any other key the file carries — `note`, the content verification's own sentence — is kept in
    the FILE as the record and is not read by the pipeline.

    A MISSING file is `{}`, not an error (John's eighteen have none and must keep working); a
    malformed one is a `SeedDataError`, which `main()` turns into exit 2 the way it does for the
    curation. Keys beginning with `_` are the file's own commentary, exactly as in
    `load_curation`. `flags` defaults to the empty list, so an entry may carry a description
    alone.

    **`flags` is carried, not acted on.** It is what the content verification noted about
    identifiable content in the image — the listing's own fictional name rendered on a sign, its
    own street number, a composite sheet rather than a single photograph. Recording it here is
    how the image-identifiability work (A-IDP-1..6, another branch) inherits the finding instead
    of having to re-read 119 images; it decides nothing about what is DISPLAYED, and every seed
    still defaults to NOT SHOW."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {
            str(slug): {
                str(name): {
                    "description": None if entry.get("description") is None else str(entry["description"]),
                    "flags": [str(flag) for flag in entry.get("flags", [])],
                    "refused": None if entry.get("refused") is None else str(entry["refused"]),
                }
                for name, entry in photographs.items()
            }
            for slug, photographs in raw.items()
            if not str(slug).startswith("_")
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise SeedDataError(f"{path}: {type(exc).__name__}") from None


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
    """Which photograph BEST fits which of the design's slots, in SLOT order — one entry per
    slot, `None` where the selection placed nothing there.

    **A curated map wins outright (A-L10).** It was written by looking at every photograph, and a
    filename is not evidence of what an image shows: `06_interior_reception.png` is an exterior
    sign in one of John's folders, and several files are sliced fragments of a collage sheet. So
    when `curated` is given it is the answer for every slot it names — in its own order, with
    `None` where no photograph in the folder truthfully shows that slot's subject.

    Without one, `keyword_choices` below still answers (A-L9), for a slug the map does not name;
    a slot it could not reach is `None` here too, so the list is the slot list either way and a
    position is always its own slot's.

    A `None` is no longer the last word (A-L11): `positions` below fills what is left from the
    rest of the folder, and only a folder thinner than the design's six slots leaves one empty.
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
    chosen = dict(keyword_choices(files, slots))
    return [(slot, chosen.get(slot)) for slot in slots]


def positions(
    files: list[Path], slots: list[str], curated: dict[str, str | None] | None = None,
    composites: frozenset[str] = frozenset(),
) -> list[tuple[str | None, Path | None]]:
    """Every photograph of the folder, in the order the API serves it (A-L11).

    Positions 1-6 are the design's captioned slots, in slot order: what `slot_choices` placed
    there, and otherwise the next image the slots did not take, in FOLDER order. Whatever is
    still left becomes positions 7, 8, … with NO slot — amendment A15.3 gives each of those a
    tile of its own, captioned with the supplier's own description.

    Nothing is dropped and nothing is duplicated: the spare queue is the folder minus what the
    selection already placed, drained left to right. A slot is `None` only when that queue runs
    out, i.e. when the folder holds fewer images than the design has slots.

    `composites` names the multi-panel sheets (Task SD1). A sheet of six pictures is not "the
    reception area", so one never fills a CAPTIONED slot while a single photograph is still
    unused — it is skipped over for the backfill and takes a position past the sixth instead,
    where amendment A15.3 gives it a tile of its own. It is never dropped, and with every spare
    a composite one still fills the slot rather than leaving it empty. With NONE declared — John's
    eighteen of 2026-09-06 — every pick is `spare[0]`, which is the folder order this has always
    used.
    """
    placed = slot_choices(files, slots, curated)
    taken = {src for _slot, src in placed if src is not None}
    spare = [src for src in files if src not in taken]
    filled: list[tuple[str | None, Path | None]] = []
    for slot, src in placed:
        if src is None and spare:
            src = next((s for s in spare if s.name not in composites), spare[0])
            spare.remove(src)
        filled.append((slot, src))
    filled.extend((None, src) for src in spare)
    return filled


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


# The acronyms John's filenames spell in lower case, as a buyer writes them (A-L11 review, m6).
# Whole TOKENS only — `reception` and `recovery` contain `ce`/`re`, not `ct` or `er`, and the
# filenames are split on `_` before this is consulted, so a substring can never match.
ACRONYMS = {"ct": "CT", "icu": "ICU", "mri": "MRI", "er": "ER", "dvm": "DVM"}


def spelled(words: list[str]) -> list[str]:
    """`words` with the acronyms above spelled the way they are read. `x_ray` arrives as two
    tokens and `xray` as one; both become "X-ray", which is why this is a scan and not a
    dict lookup per word."""
    out: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        if word == "x" and index + 1 < len(words) and words[index + 1] == "ray":
            out.append("X-ray")
            index += 2
            continue
        out.append("X-ray" if word == "xray" else ACRONYMS.get(word, word))
        index += 1
    return out


def caption_of(source_name: str) -> str:
    """A caption from the curated filename: `06_interior_reception_lobby.png` becomes
    "Interior — reception lobby" (pre-flight I2), and `10_interior_ct_scanner.png` becomes
    "Interior — CT scanner" (A-L11 review, m6: the words are read by a buyer).

    The design's own photo slots carry six fixed captions chosen by practice type; in one of
    those six slots that caption is what a buyer reads unless this one exists, and past the
    sixth (A-L11) this one is ALL there is — the design has no seventh caption to lend. It is
    the only description we hold until a seller writes their own, so it is stored per photograph
    (`index.json` → `listing.photo_captions` → `p.photoCaptions[i]`, amendment A15).

    A name that does not follow the `NN_area_description.ext` convention falls back to its
    stem with underscores as spaces, capitalised."""
    stem = Path(source_name).stem
    parts = stem.split("_")
    if len(parts) >= 3 and parts[0].isdecimal():
        return f"{parts[1].capitalize()} — {' '.join(spelled(parts[2:]))}"
    # Split on the underscore AND on whitespace: a name outside the convention may be spelled
    # either way (`x_ray.png`, `ct suite.png`), and both are read a word at a time.
    plain = " ".join(spelled(stem.lower().replace("_", " ").split()))
    # `.capitalize()` would lower-case an acronym the line above just spelled, so only the first
    # character is touched — which is what `.capitalize()` did for every other name anyway.
    return plain[:1].upper() + plain[1:]


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


def described_over(described: dict[str, dict[str, Any]], src: Path) -> dict[str, Any]:
    """What this photograph's own verified description overrides on its inventory entry.

    The CAPTION is the description where one exists — the design's six slot captions are fixed
    per practice type and cannot describe a seventh photograph at all, and a filename that reads
    `alpha_dallas_01.png` cannot describe a first one (amendment A15, `photo_captions` ->
    `p.photoCaptions[i]`). With no description the entry keeps `caption_of`'s reading of the
    filename, which is all John's eighteen have ever had.

    `flags` is ABSENT rather than empty when nothing was raised: the 195 entries already
    committed for those eighteen must not move, and `entry.get("flags", [])` reads the same
    either way."""
    entry = described.get(src.name)
    if entry is None or entry["description"] is None:
        return {}
    over: dict[str, Any] = {"caption": entry["description"]}
    if entry["flags"]:
        over["flags"] = list(entry["flags"])
    return over


def prepare(
    source_root: Path, out_root: Path, slugs: list[str], types: dict[str, str],
    curation: dict[str, dict[str, str | None]] | None = None,
    descriptions: dict[str, dict[str, dict[str, Any]]] | None = None,
    merge: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Encode EVERY photograph of every slug's folder (A-L11) — `types` maps a slug to the
    practice type that chooses its slot list, `curation` is the content-verified map (A-L10) that
    decides which image best fits each slot — and write `out_root/index.json`.

    A file's NUMBER is its POSITION, not its rank among the files that were found: positions 1-6
    are the design's slots, so `p.photos[i]` still fills the design's slot `i` (A12.2) when a slot
    in the middle is empty, and positions 7, 8, … are the photographs beyond them. A slot the
    folder is too thin to fill writes nothing and records nulls."""
    curated_all = curation if curation is not None else {}
    described_all = descriptions if descriptions is not None else {}
    # Before a single byte is written, and over the WHOLE map rather than the slugs asked for: a
    # typo in an entry this run does not touch is still a defect in the file being committed.
    validate_curation(curated_all, types)
    # `merge` (Task SD1): keep the slugs this run is not processing exactly as they were
    # committed. Eleven folders were added to a tree that already held eighteen, and re-encoding
    # those eighteen is both wasteful and a diff nobody asked for. Off by default, so a full run
    # still means "the index is exactly what I just produced" — a slug quietly surviving a
    # removal from seeds/hospitals.json is the failure this default guards against.
    index: dict[str, list[dict[str, Any]]] = {}
    if merge and (out_root / "index.json").exists():
        index = dict(json.loads((out_root / "index.json").read_text(encoding="utf-8"))["hospitals"])
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
        described = described_all.get(slug, {})
        held = {src.name for src in source_images(folder)}
        refused = {name for name, entry in described.items() if entry["refused"] is not None}
        composites = frozenset(
            name for name, entry in described.items() if "composite" in entry["flags"]
        )
        # The same care `slot_choices` takes with the curation, and for the same reason: a
        # description keyed to a filename the folder does not hold is a typo that would silently
        # caption nothing at all, and the slug is the operator's only way to find it.
        for name in sorted(set(described) - held):
            raise SeedDataError(f"{slug}: {name} is described but the source folder does not hold it")
        try:
            choices = positions(
                [src for src in source_images(folder) if src.name not in refused],
                list(slots_for(types.get(slug, ""))), curated_all.get(slug), composites,
            )
        except SeedDataError as exc:
            # The slug is the operator's only way to find the entry to fix, and `slot_choices`
            # never sees it.
            raise SeedDataError(f"{slug}: {exc}") from exc
        index[slug] = [
            {**encode(src, destination / f"{n}.webp"), "slot": slot, **described_over(described, src)}
            if src is not None
            else {"slot": slot, "file": None, "source": None, "caption": None}
            for n, (slot, src) in enumerate(choices, start=1)
        ]
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "index.json").write_text(
        json.dumps(
            {"version": 1, "slot_count": SLOT_COUNT, "max_edge_px": MAX_EDGE_PX,
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
    parser.add_argument("--merge", action="store_true",
                        help="keep the slugs this run does not process (Task SD1)")
    args = parser.parse_args(argv)
    slugs = args.slugs if args.slugs else seed_slugs()
    types = seed_types()
    try:
        curation = load_curation(CURATION_FILE)
        descriptions = load_descriptions(DESCRIPTIONS_FILE)
        index = prepare(args.source, args.out, list(slugs), types, curation, descriptions,
                        merge=args.merge)
    except (FileNotFoundError, RuntimeError, SeedDataError) as exc:
        print(f"[photos] {exc}", file=sys.stderr)
        return 2
    filled = [e for entries in index.values() for e in entries if e["file"] is not None]
    empty = sum(1 for entries in index.values() for e in entries if e["file"] is None)
    extra = sum(1 for entries in index.values() for e in entries if e["slot"] is None)
    total = sum(int(e["bytes"]) for e in filled)
    # Neither count is a footnote. The empty one is how many of the design's captioned slots the
    # folders were too thin to fill (A-L10, narrowed by A-L11); the extra one is how many
    # photographs went past those six and are rendered as tiles of their own (A-L11, A15.3) —
    # the number that proves nothing John supplied was dropped.
    print(f"[photos] {len(filled)} files, {empty} empty slots, "
          f"{extra} beyond the design's six slots, {total / 1024 / 1024:.1f} MB → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
