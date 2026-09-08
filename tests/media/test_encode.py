"""`app.media.encode` — `scripts/prepare_photos.py`'s rules, shared (spec 2026-09-08 D15).

The rules do not change: EXIF-transpose, flatten alpha onto white, <= MAX_EDGE_PX on the long edge,
the quality ladder, the FALLBACK_EDGE_PX step, <= MAX_BYTES out, every metadatum stripped. What
changes is WHERE they live — the API needs them on the request path, and a second copy would drift.
`tests/scripts/test_prepare_photos.py` keeps proving the seed pipeline end to end against this
module; these tests prove the module itself, including the arms the seed corpus never reaches.

Two constants below are corrected against `scripts/prepare_photos.py` as it actually stands on this
branch, rather than the plan's illustrative literals (task SL2, "decisions the brief cannot know" —
the encoder's rules come from the existing pipeline): `MAX_BYTES` is the script's own
`250 * 1024` (256,000 bytes), not a round 250,000, and `IMAGE_SUFFIXES` keeps the script's own
tuple order (`.png` first). Neither changes behaviour; both are the pipeline's own values.
"""
from __future__ import annotations

import io

from PIL import Image

from app.media import encode


def _jpeg(width: int, height: int, *, exif: bool = False) -> bytes:
    image = Image.new("RGB", (width, height), (120, 30, 30))
    buffer = io.BytesIO()
    if exif:
        data = Image.Exif()
        data[0x0112] = 6                    # Orientation: rotate 90 CW
        data[0x8825] = {1: "N", 2: (30.0, 16.0, 0.0)}   # GPS IFD — the one that must never survive
        image.save(buffer, "JPEG", exif=data.tobytes())
    else:
        image.save(buffer, "JPEG")
    return buffer.getvalue()


def test_the_constants_are_the_seed_pipelines_own() -> None:
    """A drift here silently changes what a seller's photograph becomes AND what the committed seed
    photographs would be re-encoded to."""
    assert (encode.MAX_PHOTOS, encode.MAX_EDGE_PX, encode.MAX_BYTES) == (4, 1600, 250 * 1024)
    assert encode.QUALITY_LADDER == (82, 72, 62, 52, 44, 20)
    assert encode.FALLBACK_EDGE_PX == 1100
    assert encode.IMAGE_SUFFIXES == (".png", ".jpg", ".jpeg", ".webp")


def test_a_photograph_comes_back_as_webp_within_both_ceilings() -> None:
    out = encode.encode_webp(_jpeg(3000, 2000))
    assert out is not None
    data, digest = out
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    assert len(data) <= encode.MAX_BYTES
    assert max(Image.open(io.BytesIO(data)).size) <= encode.MAX_EDGE_PX
    assert len(digest) == 64 and digest == encode.sha256_hex(data)


def test_every_metadatum_is_stripped_and_the_fixture_really_carried_some() -> None:
    """The load-bearing half of D15: a seller's phone photograph carries GPS EXIF, and a listing
    with `location_disclosed = false` whose photograph leaks its coordinates breaks the promise the
    sign-in card makes (A10.2). The second assertion is what stops this passing vacuously."""
    source = _jpeg(800, 600, exif=True)
    assert Image.open(io.BytesIO(source)).getexif(), "the fixture must really carry EXIF"
    out = encode.encode_webp(source)
    assert out is not None
    result = Image.open(io.BytesIO(out[0]))
    assert not result.getexif()
    assert result.info.get("icc_profile") is None
    assert result.info.get("exif") is None


def test_exif_orientation_is_applied_rather_than_recorded() -> None:
    """Orientation 6 means "rotate 90°". Stripping the tag without applying it would turn every
    portrait phone photograph on its side."""
    out = encode.encode_webp(_jpeg(800, 400, exif=True))
    assert out is not None
    assert Image.open(io.BytesIO(out[0])).size == (400, 800)


def test_transparency_is_flattened_onto_white() -> None:
    """WebP can carry alpha; the design's tiles and the buyer gallery are drawn on white, and a
    transparent PNG uploaded as a photograph would render as a hole."""
    image = Image.new("RGBA", (40, 40), (255, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    out = encode.encode_webp(buffer.getvalue())
    assert out is not None
    assert Image.open(io.BytesIO(out[0])).convert("RGBA").getpixel((0, 0)) == (255, 255, 255, 255)


def test_the_ladder_gives_up_rather_than_writing_an_oversized_file(monkeypatch: object) -> None:
    """The arm no real photograph reaches, and the one 100 % branch coverage needs a named test
    for: with the ceiling at a byte, every quality and the fallback edge still overshoot and the
    encoder returns None. SL4 turns that into a 422, never a stored file that breaks the budget."""
    import pytest

    monkeypatch.setattr(encode, "MAX_BYTES", 1)   # type: ignore[attr-defined]
    assert encode.encode_webp(_jpeg(1200, 900)) is None
    del pytest


def test_bytes_that_are_not_an_image_are_refused_rather_than_raised() -> None:
    """SL4's sniffing runs first, but the encoder is the last line: a `.jpg` that is a zip file
    must be a refusal the route can render, not a `PIL.UnidentifiedImageError` 500."""
    assert encode.encode_webp(b"PK\x03\x04not an image at all") is None


def test_an_extremely_thin_image_is_not_resized_to_a_zero_dimension() -> None:
    """The one branch `test_the_constants...` through `test_bytes_that_are_not_an_image...` above
    never reach: a sliver so extreme that `round(edge * scale)` would floor the short side to 0,
    which `Image.resize` refuses. A screenshot cropped to a 1 px strip is unlikely but not
    impossible, and the encoder's job is never to 500 on a merely unusual — as opposed to
    unreadable — upload."""
    out = encode.encode_webp(_jpeg(4000, 1))
    assert out is not None
    width, height = Image.open(io.BytesIO(out[0])).size
    assert width <= encode.MAX_EDGE_PX
    assert height == 1
