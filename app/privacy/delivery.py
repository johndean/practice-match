"""What a buyer receives, decided per request from the authoritative listing state (spec C.7).

Directive 12: "Do not trust frontend state, browser state, hidden fields, JavaScript variables,
client-side image URLs." Every one of those reaches this codebase as a query string, and this
function reads none of them. It takes the listing's own visibility, the photograph's own record,
and nothing else.

Three rules it cannot break, each asserted directly in `tests/privacy/test_delivery.py`:
the original is never the answer; display is never the answer under NOT_SHOW; a missing derivative
is a null slot and never a fallback to something else."""
from __future__ import annotations

from dataclasses import dataclass

from app.privacy.record import PrivacyRow

#: The buyer bytes route. `no-cache` means "revalidate", not "do not store": with an ETag a browser
#: gets a 304 for an unchanged derivative and the network cost is a header exchange. What it stops
#: is a buyer's browser rendering, from cache, a variant a flip has already replaced -- which
#: `private, max-age=86400` allowed for 24 hours (directive 14, D-IDP-11).
PHOTO_HEADERS = {"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"}
#: The owner and reviewer routes: never stored at all, and inline rather than an attachment.
OWNER_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Disposition": "inline"}

_NOT_SHOW_READY = ("SELLER_CONFIRMED", "PUBLISHED")
_SHOW_READY = ("READY_FOR_REVIEW", "SELLER_CONFIRMED", "PUBLISHED")


@dataclass(frozen=True)
class Variant:
    """What to serve: an object key (or, for a seed photograph, a relative disk path) and the
    content hash that is both the URL's `?v=` and the response's ETag."""

    key: str
    sha256: str
    from_disk: bool = False


def buyer_variant(visibility: str, asset: PrivacyRow | None, entry: str,
                  seed_sha: str | None = None) -> Variant | None:
    """The one representation this caller may have, or None -- a 404 on the bytes route and a null
    slot in the JSON.

    A seed entry is a PATH (it contains a "/") and has no asset row: it can only ever be served
    under SHOW, because no derivative of it exists to serve under NOT_SHOW (spec C.10)."""
    if asset is None:
        if "/" in entry and visibility == "SHOW" and seed_sha is not None:
            return Variant(entry, seed_sha, True)
        return None
    if not asset.buyer_visible:
        return None
    if visibility == "NOT_SHOW":
        if asset.processing_status in _NOT_SHOW_READY and asset.redacted_storage_key and asset.redacted_sha256:
            return Variant(asset.redacted_storage_key, asset.redacted_sha256)
        return None
    if asset.processing_status in _SHOW_READY and asset.display_storage_key and asset.display_sha256:
        return Variant(asset.display_storage_key, asset.display_sha256)
    return None


def photo_url(listing_id: object, n: int, sha256: str) -> str:
    """The buyer's positional URL, plus a content hash. The hash is a CACHE KEY and never a
    selector: the server decides the variant, so `?v=` naming an old hash still resolves to the
    current one (spec F, "predictable asset URLs")."""
    return f"/api/listings/{listing_id}/photos/{n}?v={sha256[:12]}"


def owner_url(route_prefix: str, asset_id: object, sha256: str) -> str:
    """The owner's and reviewer's tile URL, and the ONLY producer of the `src` the wizard renders.

    `route_prefix` is the caller's own -- `/api/seller/listings/{id}/photos` for the owner,
    `/api/admin/listings/{id}/photos` for the reviewer -- because the two payloads must point at
    the route each principal's permission opens (spec C.6) and one function cannot know which. It
    is a parameter rather than two near-identical functions so there is exactly one place that
    decides what the `?v=` is: the content hash of the variant actually served, which is what makes
    the step-6 thumbnail change the moment a mask does.

    `serialise_draft`'s `photos[]` calls this (Task P9 Step 6) and `frontend/src/logic.js`'s A20.4
    tile map reads the result verbatim."""
    return f"{route_prefix}/{asset_id}?v={sha256[:12]}"
