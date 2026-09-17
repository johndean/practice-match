"""The image-identifiability package: the pipeline's version, and the key layout every module in it
shares (spec 2026-09-09 C.2).

Three objects per photograph under `listings/{listing_id}/photos/{asset_id}/`, the asset uuid a
DIRECTORY rather than a filename:

  original.{jpg|png|webp}  the uploaded bytes as received. Written once, never overwritten, served
                           to the owner and the reviewer and to nobody else.
  display.webp             today's `encode_webp` output -- the normalised, metadata-free WebP.
                           `listing_asset.storage_key` keeps pointing at this one, which is what
                           `app/api/listings.py::_asset_bytes` already reads.
  redacted.webp            the NOT_SHOW representation. Regenerated in place and addressed to
                           buyers by its CONTENT HASH, so a stale URL is never a stale image.
"""
from __future__ import annotations

#: Bumped when any engine, prompt, expansion rule or fill changes; a privacy row below this is
#: stale and the sweeper flags it for an in-place re-run (spec C.5).
#: 2 (2026-09-17): the redaction EXPANSION RULE changed — `aggregate._merged` halved its gap
#: and gained `MERGE_AREA_FACTOR`, so every row processed under 1 carries masks this release
#: would not draw. Without this bump `sweep_candidates`' `reprocess` rule and
#: `scripts/reprocess_photos.py --all-stale` both answer ZERO, which is measured: they did.
PROCESSING_VERSION = 2

#: The extension `original.*` takes, chosen by the MAGIC BYTES and cross-checked against the
#: declared Content-Type (`app/api/seller_listings.py::_sniffed_photo`).
PHOTO_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def photo_prefix(listing_id: object, asset_id: object) -> str:
    return f"listings/{listing_id}/photos/{asset_id}/"


def original_key(listing_id: object, asset_id: object, ext: str) -> str:
    return f"{photo_prefix(listing_id, asset_id)}original{ext}"


def display_key(listing_id: object, asset_id: object) -> str:
    return f"{photo_prefix(listing_id, asset_id)}display.webp"


def redacted_key(listing_id: object, asset_id: object) -> str:
    return f"{photo_prefix(listing_id, asset_id)}redacted.webp"
