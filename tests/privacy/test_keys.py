"""The three-object layout (spec 2026-09-09 C.2, D-IDP-15). The asset uuid is a DIRECTORY, never
guessable and never serialised, so a future signed-URL or CDN arm can be scoped to display.webp and
redacted.webp and never to the original."""
from __future__ import annotations

from uuid import UUID

from app.privacy import PHOTO_EXT, PROCESSING_VERSION, display_key, original_key, photo_prefix, redacted_key

LISTING = UUID("11111111-1111-4111-8111-111111111111")
ASSET = UUID("22222222-2222-4222-8222-222222222222")


def test_the_three_keys_share_the_asset_uuid_as_a_directory() -> None:
    prefix = photo_prefix(LISTING, ASSET)
    assert prefix == f"listings/{LISTING}/photos/{ASSET}/"
    assert original_key(LISTING, ASSET, ".jpg") == f"{prefix}original.jpg"
    assert display_key(LISTING, ASSET) == f"{prefix}display.webp"
    assert redacted_key(LISTING, ASSET) == f"{prefix}redacted.webp"
    assert len({original_key(LISTING, ASSET, ".jpg"), display_key(LISTING, ASSET), redacted_key(LISTING, ASSET)}) == 3


def test_every_accepted_photo_type_has_an_extension() -> None:
    assert PHOTO_EXT == {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def test_the_processing_version_is_an_integer_the_privacy_row_can_hold() -> None:
    assert isinstance(PROCESSING_VERSION, int) and PROCESSING_VERSION >= 1
