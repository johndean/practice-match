"""Opaque, irreversible redaction (spec 2026-09-09 C.5 step 6; directive 5).

"Use irreversible/opaque redaction rather than relying solely on Gaussian blur. The underlying
identifiable pixels must not remain recoverable from the buyer-facing derivative."

The strongest checkable form of that is the property in
`test_two_photographs_that_differ_only_under_the_mask_produce_identical_bytes`: a constant fill
carries no information about what it covers, so two display images whose only difference is inside
the region produce the SAME derivative, byte for byte. A blur, a pixelation or a mosaic all fail
that test, which is why none of them is used.

**Two facts about the encoder shape this file, and both were measured before it was written.**
(1) The two display inputs must be built LOSSLESSLY. `encode_webp`'s ladder is lossy
(`Image.save(..., "WEBP", quality=q)`, `app/media/encode.py:69-88`), so two sources that differ
inside the mask come back differing OUTSIDE it too — intra-prediction propagates across the block
boundary — and the property would then fail for a reason that has nothing to do with redaction.
Measured: with lossy sources the two derivatives differ; with lossless sources they are identical,
64 844 bytes each. (2) The fill does not survive the ladder EXACTLY. `redact.FILL` is
`(0, 58, 112)`; after the derivative's own lossy encode at the ladder's first rung the worst
per-channel error twelve pixels inside the region is 1, and at the region's edge it is around 19.
So the fill assertions sample well inside the region and compare within `FILL_TOLERANCE`, and the
byte-equality property above is what carries the security claim — not a colour triple."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app.media import redact

BOX = [(100.0, 100.0), (400.0, 100.0), (400.0, 220.0), (100.0, 220.0)]
#: Measured, not guessed: the worst per-channel error at least 12 px inside a filled region, after
#: `encode_webp`'s ladder, is 1 on the fixture below. Four is that with headroom; a value this test
#: has to RAISE later is a change in the encoder and a `NEEDS_CONTEXT`, not a tuning knob.
FILL_TOLERANCE = 4
#: How far inside a region a fill assertion samples. The edge of a filled block is where the lossy
#: encoder's ringing lives (about 19 per channel at one pixel in), and asserting there would be
#: asserting a property of libwebp rather than of this module.
FILL_MARGIN_PX = 12


def _display(patch: tuple[int, int, int] | None = None) -> bytes:
    """A 900x600 display object with a little structure, optionally with a patch inside the region.

    LOSSLESS, so two calls differing only inside `BOX` are pixel-identical everywhere else — which
    is exactly the premise the irreversibility property needs and exactly what a lossy source
    destroys. It stands in for `display.webp` faithfully in every way that matters here: same size,
    same mode, same decode path."""
    image = Image.new("RGB", (900, 600), (210, 215, 220))
    for x in range(0, 900, 9):
        for y in range(0, 600, 7):
            image.putpixel((x, y), ((x * 7) % 256, (y * 11) % 256, 90))
    if patch is not None:
        for x in range(120, 380):
            for y in range(120, 200):
                image.putpixel((x, y), patch)
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", lossless=True, method=6)
    return buffer.getvalue()


def _is_fill(pixel: tuple[int, int, int]) -> bool:
    return all(abs(pixel[channel] - redact.FILL[channel]) <= FILL_TOLERANCE for channel in range(3))


def test_every_pixel_inside_the_region_is_the_fill_colour() -> None:
    out = redact.fill_regions(_display(), [BOX])
    assert out is not None
    image = Image.open(io.BytesIO(out[0])).convert("RGB")
    sampled = 0
    for x in range(100 + FILL_MARGIN_PX, 400 - FILL_MARGIN_PX, 7):
        for y in range(100 + FILL_MARGIN_PX, 220 - FILL_MARGIN_PX, 5):
            assert _is_fill(image.getpixel((x, y))), (x, y, image.getpixel((x, y)))
            sampled += 1
    assert sampled > 400, "the sampling grid collapsed -- this would pass vacuously"


def test_two_photographs_that_differ_only_under_the_mask_produce_identical_bytes() -> None:
    """The irreversibility property. A fill is a constant, so the lossy encoder receives no
    information about the covered pixels and none can survive in the output.

    The two sources are lossless and pixel-identical outside `BOX`; the patch is strictly inside it
    (120-380 x 120-200 against a region of 100-400 x 100-220), so nothing outside the fill differs
    between them and the only thing this can be measuring is the fill."""
    one = redact.fill_regions(_display((255, 0, 0)), [BOX])
    two = redact.fill_regions(_display((0, 255, 0)), [BOX])
    assert one is not None and two is not None
    assert one[0] == two[0] and one[1] == two[1]
    assert _display((255, 0, 0)) != _display((0, 255, 0)), "the two sources are the same file"


def test_the_derivative_keeps_the_display_dimensions() -> None:
    """Directive 5: "Preserve image dimensions/aspect ratio where possible." Display is already
    within the 1600 px bound, so the resize step never fires and in equals out."""
    source = _display()
    before = Image.open(io.BytesIO(source)).size
    out = redact.fill_regions(source, [BOX])
    assert out is not None and Image.open(io.BytesIO(out[0])).size == before


def test_the_derivative_carries_no_metadata() -> None:
    out = redact.fill_regions(_display(), [BOX])
    assert out is not None
    image = Image.open(io.BytesIO(out[0]))
    assert not image.info.get("exif") and not image.info.get("icc_profile") and not image.info.get("xmp")


def test_a_polygon_is_filled_as_a_polygon_and_not_as_its_bounding_box() -> None:
    """A rotated sign is covered by the quad the engine returned; the corner outside it is not."""
    triangle = [(100.0, 100.0), (400.0, 100.0), (100.0, 300.0)]
    out = redact.fill_regions(_display(), [triangle])
    assert out is not None
    image = Image.open(io.BytesIO(out[0])).convert("RGB")
    assert _is_fill(image.getpixel((140, 140)))          # well inside the triangle
    assert not _is_fill(image.getpixel((390, 290)))      # the corner the bounding box would cover


def test_no_regions_still_re_encodes_so_the_derivative_always_exists() -> None:
    """A photograph the pipeline found nothing in still gets a redacted.webp: the resolver serves
    that object under NOT_SHOW, and a null derivative would be a null slot for no reason."""
    out = redact.fill_regions(_display(), [])
    assert out is not None and len(out[1]) == 64


def test_a_two_point_polygon_fails_the_whole_derivative_rather_than_being_skipped() -> None:
    """Controller ruling, 2026-09-16: "there must be no input that silently results in nothing
    being covered."

    The plan's own version of this case asserted the opposite -- that a polygon `ImageDraw` cannot
    draw is IGNORED and the derivative comes back as though the region had never been asked for.
    On a privacy feature that is the worst outcome available: the seller is told the mark is hidden,
    the derivative is published, and nothing anywhere records that one of the regions was dropped.
    `aggregate.py` can no longer produce such a polygon, but this function is also handed
    `fillable(row.redaction_regions)` -- jsonb, including P12's seller-drawn masks -- so the door
    is closed on this side too. `None` is REDACTION_FAILED at the caller, which is a state a
    reviewer can see."""
    assert redact.fill_regions(_display(), [[(10.0, 10.0), (20.0, 20.0)]]) is None


def test_a_polygon_enclosing_no_area_fails_the_derivative_too() -> None:
    """Three points is not the whole of "can be drawn". Four identical corners is a point, and a
    stored region collapsed to one covers nothing while satisfying every count-based guard."""
    assert redact.fill_regions(_display(), [[(10.0, 10.0)] * 4]) is None


def test_one_unusable_polygon_fails_the_call_even_beside_good_ones() -> None:
    """Fail CLOSED, not partially: a derivative that covered three of four regions and said so
    nowhere is the same defect wearing a better number."""
    assert redact.fill_regions(_display(), [BOX, [(10.0, 10.0), (20.0, 20.0)]]) is None


def test_bytes_that_will_not_fit_the_ladder_are_None_not_an_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """`encode_webp` -> None is REDACTION_FAILED with reason ENCODE_TOO_LARGE. Fail closed."""
    monkeypatch.setattr("app.media.redact.encode_webp", lambda data: None)
    assert redact.fill_regions(_display(), [BOX]) is None


def test_undecodable_bytes_are_None() -> None:
    assert redact.fill_regions(b"not an image at all", [BOX]) is None


#: Every RIFF chunk a WebP can carry that could hold, or hide, pixels the fill was meant to cover.
#: `ALPH` is a whole second channel; `EXIF` is where a camera thumbnail lives and where the original
#: capture's own JPEG preview would travel; `ICCP` and `XMP ` are arbitrary payload; `ANIM`/`ANMF`
#: would make the derivative an animation whose other frame is the unredacted photograph.
FORBIDDEN_CHUNKS = ("ALPH", "EXIF", "XMP ", "ICCP", "ANIM", "ANMF")


def _chunks(webp: bytes) -> list[str]:
    """The FourCC of every RIFF chunk in `webp`, read from the BYTES rather than from Pillow.

    Pillow's `Image.info` reports what its WebP plugin chose to surface; this walks the container
    itself, which is what a buyer actually receives. Chunk payloads are padded to an even length
    (RIFF), and the header is `RIFF` + size + `WEBP` before the first chunk."""
    assert webp[:4] == b"RIFF" and webp[8:12] == b"WEBP", "not a RIFF/WEBP container"
    found, at = [], 12
    while at + 8 <= len(webp):
        fourcc = webp[at:at + 4].decode("ascii")
        size = int.from_bytes(webp[at + 4:at + 8], "little")
        found.append(fourcc)
        at += 8 + size + (size % 2)
    return found


def test_the_output_bytes_carry_no_chunk_that_could_hold_the_covered_pixels() -> None:
    """Directive 5, read strictly: the covered pixels must not survive "in an alpha channel, in
    metadata, in a thumbnail, or in EXIF". The byte-equality property above proves nothing about
    the region reaches the IMAGE; this proves nothing reaches the CONTAINER around it either.

    A characterisation test, honestly: it passed the moment it was written, because `encode_webp`'s
    save asks for none of these. What it pins is that it stays that way -- the derivative is a bare
    lossy WebP and nothing else."""
    out = redact.fill_regions(_display((255, 0, 0)), [BOX])
    assert out is not None
    present = _chunks(out[0])
    assert present == ["VP8 "], f"the derivative carries more than its image: {present}"
    assert not [c for c in present if c in FORBIDDEN_CHUNKS]
