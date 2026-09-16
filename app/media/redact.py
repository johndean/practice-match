"""The buyer-safe derivative: an opaque fill over every region, re-encoded (spec C.5 step 6).

Never blur, never pixelate, never mosaic. Each of those leaves a function of the covered pixels in
the output, and each has been reversed in public before. A constant fill leaves nothing: two
photographs differing only under the mask encode to the same bytes, which is the property
`tests/media/test_redact.py` asserts directly rather than arguing for.

`encode_webp` does the re-encode -- the same quality ladder, the same 1600 px bound, the same
metadata-free save (`app/media/encode.py`), so the derivative is normalised exactly as display is
and this module owns no encoding rules of its own. Display is already within the bound, so the
resize never fires and the derivative's dimensions equal display's.

A future thumbnail generator must take THIS output as its input, never the display object."""
from __future__ import annotations

import io
from collections.abc import Sequence

from PIL import Image, ImageDraw, UnidentifiedImageError

from app.media.encode import encode_webp

#: The design's navy, `var(--color-navy)` -- the done card's colour (D-IDP-9; black is the
#: alternative John may rule for). A constant, and that is the whole of its security property.
FILL = (0, 58, 112)


def _covers_a_pixel(polygon: Sequence[tuple[float, float]]) -> bool:
    """Whether `ImageDraw.polygon` can paint anything at all for this polygon.

    Controller ruling, 2026-09-16: "there must be no input that silently results in nothing being
    covered." Two shapes reach that outcome and both are refused by the caller rather than skipped:
    fewer than three points, which `ImageDraw.polygon` cannot draw, and three or more enclosing no
    area -- four identical corners is a point, and a stored region collapsed to one satisfies every
    count-based guard while covering nothing.

    The BOUNDING BOX is the measure, not the true polygon area, and the limit is recorded rather
    than hidden: three collinear points on a diagonal enclose no area and pass this, because PIL
    draws them as a thin line, which is something rather than nothing. What is refused is exactly
    what paints no pixel."""
    if len(polygon) < 3:
        return False
    xs = [float(x) for x, _ in polygon]
    ys = [float(y) for _, y in polygon]
    return max(xs) > min(xs) and max(ys) > min(ys)


def fill_regions(display: bytes, polygons: Sequence[Sequence[tuple[float, float]]]) -> tuple[bytes, str] | None:
    """The derivative's bytes and their SHA-256, or None -- REDACTION_FAILED at the caller, never a
    fallback and never a partial cover.

    `None` for three reasons and no others: the source will not decode, the result will not fit
    `encode_webp`'s ladder, or one of the polygons would cover no pixel. The third fails the WHOLE
    call rather than dropping that one region, because a derivative that covered three of four
    regions and recorded the fact nowhere is the defect this module exists to prevent wearing a
    better number. `app/privacy/aggregate.py` can no longer produce such a polygon; this door is
    the one the stored `redaction_regions` come through, P12's seller-drawn masks included."""
    try:
        image = Image.open(io.BytesIO(display)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None
    if not all(_covers_a_pixel(polygon) for polygon in polygons):
        return None
    draw = ImageDraw.Draw(image)
    for polygon in polygons:
        draw.polygon([(float(x), float(y)) for x, y in polygon], fill=FILL)
    buffer = io.BytesIO()
    # `lossless=True`, not `quality=100`: q=100 is still the lossy coder, so the pixels this module
    # just drew would be re-derived approximately before `encode_webp` ever saw them. The ladder
    # inside `encode_webp` is where the lossy step belongs and the only place it happens.
    #
    # A KNOWN UNGATED LINE, named so the next reader neither gates it badly nor deletes it. No test
    # in `tests/media/test_redact.py` discriminates it, and the plan's claim that the byte-equality
    # property does was MEASURED FALSE: with `quality=100` here the whole suite still passes, because
    # the fill is applied BEFORE this save, so once the region is covered the two sources are
    # pixel-identical and any deterministic encoder answers the same bytes. What it actually buys,
    # measured on that fixture: the worst per-channel error twelve pixels inside the fill is 1
    # against 3, and the derivative is 64 844 bytes against 55 762. Both clear the file's own
    # `FILL_TOLERANCE` of 4, and the tolerance is deliberately NOT tightened to 2 to gate this line:
    # that would trade a cross-libwebp-build flake on this module's ONE security assertion for a
    # fidelity nicety, which is the wrong way round.
    image.save(buffer, "WEBP", lossless=True, method=0)
    return encode_webp(buffer.getvalue())
