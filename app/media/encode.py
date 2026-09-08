"""Photograph normalisation — `scripts/prepare_photos.py`'s rules, on the request path.

Spec 2026-09-08 D15: "Normalisation is part of the upload, not a nicety." Every rule here was
already the seed pipeline's; this module is where they now live so that the seeder and the API
apply exactly the same ones, and `tests/scripts/test_prepare_photos.py` keeps proving them end to
end against the committed corpus.

METADATA STRIPPING IS THE POINT, not tidiness. A seller's phone photograph carries GPS EXIF, and a
listing with `location_disclosed = false` whose photograph leaks its coordinates breaks the promise
John's own words make on the sign-in card (amendment A10.2, "Sellers control what buyers can see").
Pillow's `save` writes no EXIF, ICC profile or XMP unless asked, and this module never asks — but
orientation must be APPLIED before it is discarded (`ImageOps.exif_transpose`), or every portrait
photograph ships on its side.
"""
from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageOps, UnidentifiedImageError

# The seed pipeline's own values (scripts/prepare_photos.py). Four per listing is John's ruling,
# restated for the API in D18; 1600 px and 250 KB are what keep the buyer gallery quick on a phone.
MAX_PHOTOS = 4
MAX_EDGE_PX = 1600
MAX_BYTES = 250 * 1024
# Tried in order; the first that fits under MAX_BYTES wins.
QUALITY_LADDER = (82, 72, 62, 52, 44, 20)
# One more step for a photograph that will not fit at any quality at MAX_EDGE_PX: shrink, then walk
# the ladder again. A visibly smaller photograph beats a refused upload.
FALLBACK_EDGE_PX = 1100
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _flattened(image: Image.Image) -> Image.Image:
    """Orientation applied, alpha composited onto white, mode RGB. Not `convert("RGB")` alone:
    that drops the alpha channel by discarding it, so a transparent pixel becomes black."""
    upright = ImageOps.exif_transpose(image)
    if upright.mode in ("RGBA", "LA", "P"):
        rgba = upright.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return upright.convert("RGB")


def _within(image: Image.Image, edge: int) -> Image.Image:
    if max(image.size) <= edge:
        return image
    scale = edge / max(image.size)
    return image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)


def encode_webp(data: bytes) -> tuple[bytes, str] | None:
    """`data` as WebP bytes and their SHA-256, or `None` when nothing in the ladder fits.

    `None` rather than an exception for BOTH failure modes — bytes that are not an image, and an
    image that will not fit — because the caller is an HTTP route and both are the caller's 422,
    not a 500."""
    try:
        opened = Image.open(io.BytesIO(data))
        flattened = _flattened(opened)
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    for edge in (MAX_EDGE_PX, FALLBACK_EDGE_PX):
        candidate = _within(flattened, edge)
        for quality in QUALITY_LADDER:
            buffer = io.BytesIO()
            candidate.save(buffer, "WEBP", quality=quality, method=6)
            out = buffer.getvalue()
            if len(out) <= MAX_BYTES:
                return out, sha256_hex(out)
    return None
