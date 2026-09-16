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


def fill_regions(display: bytes, polygons: Sequence[Sequence[tuple[float, float]]]) -> tuple[bytes, str] | None:
    """The derivative's bytes and their SHA-256, or None when the source will not decode or the
    result will not fit the ladder -- REDACTION_FAILED at the caller, never a fallback."""
    try:
        image = Image.open(io.BytesIO(display)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None
    draw = ImageDraw.Draw(image)
    for polygon in polygons:
        if len(polygon) >= 3:
            draw.polygon([(float(x), float(y)) for x, y in polygon], fill=FILL)
    buffer = io.BytesIO()
    # `lossless=True`, not `quality=100`: q=100 is still the lossy coder, so the pixels this module
    # just drew would be re-derived approximately before `encode_webp` ever saw them. The ladder
    # inside `encode_webp` is where the lossy step belongs and the only place it happens.
    image.save(buffer, "WEBP", lossless=True, method=0)
    return encode_webp(buffer.getvalue())
