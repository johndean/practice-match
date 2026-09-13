"""The 2D-symbol adapter -- the ONLY module in `app/` that imports a barcode engine.

D-IDP-7 (queued for John): every 2D symbol is redacted under NOT_SHOW regardless of payload. The
directive says "QR codes where they resolve to identifying information", and this goes further
toward hiding: a QR cannot be reviewed by eye, and resolving one would mean the worker fetching a
URL a stranger put in a photograph. The payload is classified OFFLINE for the record and the string
itself is never stored; the seller can Remove a mask that was unnecessary."""
from __future__ import annotations

import importlib
import re
from typing import Any, NamedTuple, Protocol, cast

from PIL import Image

from app.config import settings

ENGINE = "zxing-cpp/3.1.1"
#: Each symbol's four corners, expanded about their centroid by this factor before the fill.
EXPAND = 1.15

_URL = re.compile(r"^(https?://|www\.)|^[\w-]+(\.[\w-]+)+(/|$)", re.IGNORECASE)
_PHONE = re.compile(r"^(tel:)?[\d\s()+.-]{7,}$")


class Symbol(NamedTuple):
    fmt: str
    payload_kind: str
    quad: list[tuple[float, float]]


class BarcodeUnavailable(RuntimeError):
    """Reason code BARCODE_UNAVAILABLE."""


class BarcodeError(RuntimeError):
    """Reason code BARCODE_ERROR."""


class Engine(Protocol):
    def read(self, image: Image.Image) -> list[Symbol]: ...


_LOADED: Engine | None = None


def classify(payload: str) -> str:
    """`url` | `phone` | `vcard` | `text`. Offline, and the ONLY thing kept about a payload."""
    if payload.startswith("BEGIN:VCARD"):
        return "vcard"
    if _URL.search(payload):
        return "url"
    if _PHONE.match(payload):
        return "phone"
    return "text"


def _engine() -> Engine:
    global _LOADED
    if _LOADED is None:
        module = settings.privacy_engine_module
        try:
            _LOADED = (cast("Engine", importlib.import_module(module).BarcodeEngine())
                       if module is not None else _Zxing())
        except (ImportError, AttributeError) as exc:
            raise BarcodeUnavailable("BARCODE_UNAVAILABLE") from exc
    return _LOADED


class _Zxing:
    def __init__(self) -> None:
        # Deliberately lazy -- the api must not import an engine.
        import zxingcpp

        self._read = zxingcpp.read_barcodes

    def read(self, image: Image.Image) -> list[Symbol]:
        found: list[Symbol] = []
        for result in self._read(image, try_rotate=True, try_downscale=True, return_errors=True):
            corners: Any = result.position
            quad = [(float(p.x), float(p.y)) for p in (corners.top_left, corners.top_right,
                                                       corners.bottom_right, corners.bottom_left)]
            kind = classify(result.text) if result.valid else "undecodable"
            found.append(Symbol(str(result.format), kind, quad))
        return found


def read_symbols(image: Image.Image) -> list[Symbol]:
    engine = _engine()
    try:
        return list(engine.read(image))
    except Exception as exc:  # the engine's failures are not a documented, catchable set
        raise BarcodeError("BARCODE_ERROR") from exc
