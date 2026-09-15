"""Deterministic stand-ins for the OCR and 2D-symbol engines, loaded through
`PRIVACY_ENGINE_MODULE` (spec 2026-09-09 G).

Two fixed lines: a practice name that the identity matcher matches against the seeded listing, and
a NANP telephone number that the regex class flags whether or not it matches. Only the name is
returned on the FIRST pass, and its quad is deliberately shorter than `ocr.UPSCALE_BELOW_PX` -- which
is what makes `read_text` run its second pass at all, and therefore what makes the phone line
reachable. Get that the wrong way round and the second pass never fires: a first pass whose only
line is 60 px tall satisfies `_height(line.quad) >= UPSCALE_BELOW_PX`, `found` stays empty, and the
telephone number is never returned by anything. No barcode, so a scenario that needs one plants its
own engine.

This module lives under `tests/` and is imported by NAME: nothing test-shaped is importable from
`app/`, and `Settings` refuses the variable outside `ENVIRONMENT=test`."""
from __future__ import annotations

from PIL import Image

from app.privacy.barcodes import Symbol
from app.privacy.ocr import Line

NAME_LINE = "HILL COUNTRY ANIMAL HOSPITAL"
PHONE_LINE = "(512) 555-0100"

#: How the stub tells `read_text`'s first pass from its 2x second pass: by height alone, with the
#: threshold above every display size the suites use (800x600 in `test_ocr.py`, 1200x900 in
#: `test_media.py`) and below every doubling of them (1200, 1800).
UPSCALED_ABOVE_PX = 1000
#: The name line's quad is 2 % of the image's height -- 12 px at 600, 18 px at 900, both under
#: `ocr.UPSCALE_BELOW_PX` (24), so the first pass always triggers the second.
NAME_BAND = 0.02


class OcrEngine:
    def run(self, image: Image.Image) -> list[Line]:
        # Positions are fractions of the image, so the same stub serves any size the suites use.
        w, h = image.width, image.height
        name = [(w * 0.10, h * 0.10), (w * 0.70, h * 0.10),
                (w * 0.70, h * (0.10 + NAME_BAND)), (w * 0.10, h * (0.10 + NAME_BAND))]
        if h < UPSCALED_ABOVE_PX:         # the first pass: one short line, and no telephone number
            return [Line(NAME_LINE, 0.98, name)]
        phone = [(w * 0.10, h * 0.30), (w * 0.35, h * 0.30), (w * 0.35, h * 0.33), (w * 0.10, h * 0.33)]
        return [Line(NAME_LINE, 0.98, name), Line(PHONE_LINE, 0.91, phone)]


class BarcodeEngine:
    def read(self, image: Image.Image) -> list[Symbol]:
        return []
