"""`geo_metric`'s version counter — the one name Task 9's read path needs from Task 8's writer.

**This module is a STUB created by Task 9 and Task 8 owns it.** Task 8 (`materialize_geo`, the
nightly writer that is the only thing that ever writes `geo_metric`) is being built in parallel
against the same plan and will land the rest of this module — `LAYERS`, `_UPSERT`, `_DELETE`,
`materialize_geo` — around the constant below. The constant is reproduced here VERBATIM from the
plan (`docs/superpowers/plans/2026-09-11-neighbourhood-shading.md`, Task 8), string and all, so the
two branches cannot disagree about which Redis key they are talking about: on merge, take Task 8's
file whole. A second spelling of this key in `app/api/market.py` would have been the worse answer —
a cache-busting key with two definitions busts nothing the day one of them moves.
"""
from __future__ import annotations

# Bumped on every run, and carried in the boundary endpoint's cache key. Without it a nightly
# rewrite that changes values but not the vintage would be invisible for up to the 24 h TTL --
# `materialize_listing`'s own `listing:{id}:market:version` idiom, one table wider.
GEO_VERSION_KEY = "market:geo:version"
