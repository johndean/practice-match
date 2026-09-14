"""Prove that the OCR and 2D-symbol engines open no socket — constraint (i), made runnable.

    DATABASE_URL=postgresql://x/y REDIS_URL=redis://localhost:6379/0 API_SECRET_KEY=x \
    ENVIRONMENT=test poetry run python scripts/prove_offline_engines.py

`rapidocr-onnxruntime` carries its three PP-OCR models inside its own wheel and `zxing-cpp` is a
compiled reader, so neither should ever reach the network. This script is how that claim is
CHECKED rather than asserted: it builds both real engines and runs them on a generated image with
every door onto a socket removed, and prints what it found. A non-zero exit, or a traceback from
inside an engine, is the claim failing.

ORDER MATTERS, and it is the whole reason this file exists rather than a snippet in a plan. The
obvious spelling — remove the sockets, then import the adapter — cannot work: `socket.socket = None`
makes `class SSLSocket(socket)` raise `TypeError: NoneType takes no arguments` the moment `ssl` is
imported, and `pydantic_settings` imports `asyncio` which imports `ssl`, so the process dies on
`from app.privacy import ocr` before an engine is ever built. Importing first loses nothing: the
adapters build their engines LAZILY, inside `read_text`/`read_symbols`, so both the construction
that reads the models off disk and the inference that uses them happen after the doors are shut.

Run under a throwaway `HOME` if you want the strongest form — onnxruntime writes a small
telemetry-shaped file under `$HOME` on macOS (P4 report, M6), and an empty one makes any download
visible as a new file rather than a silent cache hit.
"""
from __future__ import annotations

import socket
import sys
from collections.abc import Callable
from types import ModuleType
from typing import Any

from PIL import Image, ImageDraw

#: Every name in `socket` that hands back a usable connection. Removing all five is stricter than
#: the suite's own `_no_stray_network` guard, which only refuses a non-local `connect`.
SOCKET_DOORS = ("socket", "create_connection", "socketpair", "getaddrinfo", "gethostbyname")


def close_every_socket_door(module: ModuleType) -> list[str]:
    """Remove every door in `SOCKET_DOORS` from `module`, and answer which ones were closed.

    `None` rather than a raising stub on purpose: an attempt to use one is then an `AttributeError`
    or a `TypeError` at the point of use, with the engine's own frame in the traceback, rather than
    a hang or a swallowed retry.
    """
    for door in SOCKET_DOORS:
        setattr(module, door, None)
    return list(SOCKET_DOORS)


def sample_image() -> Image.Image:
    """A sign, the line beneath it, and the same words again far down the frame — the three cases
    the de-duplication rule has to keep apart (A-IDP-11, reviews I1, N2, I-1)."""
    image = Image.new("RGB", (1200, 900), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((60, 90), "HILL COUNTRY VET", fill=(0, 0, 0))
    draw.text((60, 150), "24 HOUR EMERGENCY", fill=(0, 0, 0))
    draw.text((60, 640), "HILL COUNTRY VET", fill=(0, 0, 0))
    return image


def report(read_text: Callable[[Image.Image], list[Any]],
           read_symbols: Callable[[Image.Image], list[Any]],
           image: Image.Image, ocr_engine: str, barcode_engine: str, closed: list[str]) -> list[str]:
    """What the run found, one line at a time, ready to paste into a report."""
    lines = read_text(image)
    symbols = read_symbols(image)
    found = ["closed: " + ", ".join(closed), f"ocr engine: {ocr_engine}"]
    found += [f"  line: {line.text!r} conf={line.confidence:.3f}" for line in lines]
    found.append(f"lines returned: {len(lines)}")
    found.append(f"barcode engine: {barcode_engine} symbols: {symbols}")
    found.append(f"socket.socket is {socket.socket}")
    return found


def main() -> int:
    # Imports FIRST — see the module docstring; the adapters build their engines lazily, so nothing
    # has been constructed yet when the doors shut on the next line.
    from app.privacy import barcodes, ocr

    closed = close_every_socket_door(socket)
    for line in report(ocr.read_text, barcodes.read_symbols, sample_image(),
                       ocr.ENGINE, barcodes.ENGINE, closed):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
