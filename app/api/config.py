"""`GET /api/config` — the client's read of the flags it has to honour (A-I7.2).

Today that is one flag. `MARKET_DATA_PUBLIC` decides whether an anonymous visitor holds
`market.read` (`app.auth.permissions.allowed`'s one non-matrix arm), and the browser needs the
same answer to decide whether to render the market column or a sign-in prompt in its place —
`can('market.read', me, { marketDataPublic })`. Without this endpoint the client's twin of the
matrix could not be told, and the column would have had to guess.

Public, and public by nature: the flag is a statement ABOUT anonymous visitors, so requiring a
credential to read it would be circular. It reveals nothing an anonymous request to a market
endpoint would not, and it writes nothing — which is why it is listed in
`permissions.PUBLIC_ROUTES` rather than guarded.

Included in `create_app` unconditionally, unlike the auth surface: it is answerable, and
harmless, in `coming_soon` mode too.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api")


@router.get("/config")
async def config() -> dict[str, bool]:
    return {"market_data_public": settings.market_data_public}
