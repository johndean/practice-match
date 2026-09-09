from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.admin_data_sources import router as admin_data_sources_router
from app.api.admin_listings import router as admin_listings_router
from app.api.admin_signups import router as admin_signups_router
from app.api.admin_users import router as admin_users_router
from app.api.applications import router as applications_router
from app.api.auth import router as auth_router
from app.api.config import router as config_router
from app.api.health import not_found_router
from app.api.health import router as health_router
from app.api.interest import router as interest_router
from app.api.listings import router as listings_router
from app.api.seller_listings import router as seller_listings_router
from app.api.market import router as market_router
from app.api.webhooks import router as webhooks_router
from app.auth import deps
from app.config import settings
from app.db import dispose_all
from app.security_headers import SecurityHeadersMiddleware, server_error
from app.static import dist_for, mount_spa
from app.version import VERSION


def create_app(dist: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await dispose_all()

    app = FastAPI(
        title="Practice Match API", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )

    @app.middleware("http")
    async def robots_header(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        if not settings.public_indexing:
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.api_route("/robots.txt", methods=["GET", "HEAD"], include_in_schema=False)
    async def robots() -> PlainTextResponse:
        return PlainTextResponse("User-agent: *\nAllow: /\n" if settings.public_indexing else "User-agent: *\nDisallow: /\n")

    if settings.origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
            allow_methods=["*"], allow_headers=["*"],
        )
    # Spec §3's four headers on EVERY answer. Added last, so it is the outermost user middleware
    # and a CORS preflight carries them too; `server_error` carries them on the one response that
    # never reaches any middleware, the 500 ServerErrorMiddleware generates itself (I4 fix round 1,
    # Minor 2).
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_exception_handler(Exception, server_error)
    # The handlers that render decision A5's body for app.auth.deps.AuthError and for FastAPI's own
    # request-validation refusals; the installer lives with the dependency it serves (I3 fix round
    # 1, ruling (a)). I4 adds the auth routers.
    deps.install(app)
    app.include_router(health_router)
    # UNCONDITIONALLY, unlike the auth surface below (A-I7.2): `GET /api/config` publishes
    # MARKET_DATA_PUBLIC, which is what the browser's `can('market.read', …)` needs in order to
    # honour the same rule `permissions.allowed` applies. It reads one boolean setting, reveals
    # nothing an anonymous market request would not, and writes nothing.
    app.include_router(config_router)
    # Future /api routers are included here, BEFORE the catch-all below.
    #
    # The auth surface exists only in `app` mode (I4 fix round 1, Important 6). Production runs
    # `coming_soon` until launch (CLAUDE.md), and a router mounted there would have let anyone who
    # guessed the path create real `account` rows behind the Coming Soon page — with nothing to
    # email them until I6 lands, so the only visible effect would be unexplained rows. In
    # `coming_soon` every /api/auth/* path and /api/me falls through to `not_found_router`'s JSON
    # 404, which is what `scripts/verify-deploy.sh` now probes for on production.
    if settings.site_mode == "app":
        app.include_router(auth_router)
        # Same gate, same reason (I4 fix round 1, Important 6): in `coming_soon` there is nobody to
        # apply, nobody to review an application and no mail to send, so every /api/applications
        # and /api/admin/* path falls through to `not_found_router`'s JSON 404.
        app.include_router(applications_router)
        app.include_router(admin_users_router)
        # Same gate, third time (Census A-C0 ¶5): the admin Data Sources console is staff/admin
        # only and its licence decisions are admin-and-re-authenticated, so behind the Coming Soon
        # page it is absent rather than merely guarded, like every other /api/admin/* path.
        app.include_router(admin_data_sources_router)
        # Same gate again (Seed Listings A-L5.1): the three listing reads are MEMBER endpoints
        # — `listing.read` is buyer/seller/staff/admin — so behind the Coming Soon page they are
        # absent rather than merely guarded, and `scripts/verify-deploy.sh production` probes
        # that alongside the auth, applications and admin surfaces.
        app.include_router(listings_router)
        # Same gate again (spec 2026-09-08 D9): the seller wizard's surface and the reviewer's read
        # of a draft are MEMBER surfaces — `listing.manage_own` is the seller role's, `listing.review`
        # is staff's — so behind the Coming Soon page they are absent rather than merely guarded, and
        # `scripts/verify-deploy.sh production` probes for their 404 beside the other four. The
        # prefixes are `/api/seller` and `/api/admin`, both disjoint from `/api/listings`, so nothing
        # here can shadow the buyer's `/api/listings/{listing_id}` whatever the order.
        app.include_router(seller_listings_router)
        app.include_router(admin_listings_router)
        # Same gate again (Census B5, A-C13 (11)): the market API is member-gated
        # (`market.read` — buyer/seller/staff/admin, or anonymous only while
        # `MARKET_DATA_PUBLIC` is set, which John's ruling (A-C13 (3)) keeps `false` in every
        # environment) — so behind the Coming Soon page it is absent, like every other member
        # surface above.
        app.include_router(market_router)
        # Superseded 2026-09-09 by John's ruling (A-I5d.5) — this used to be UNCONDITIONAL (Task
        # I5d, D-I5d-5): `interest_signup` is filled by the Coming Soon page, so the rows this
        # reads only exist on PRODUCTION, which runs `coming_soon` until launch, and gating the
        # router the way `admin_users_router` is gated would have made the capability unreachable
        # exactly where the data is. John overrode that: "Gate the entire Admin Launch Sign-ups
        # router behind SITE_MODE=app. Do not expose the sign-up list or CSV export on production
        # while Coming Soon, even to an API_SECRET_KEY bearer." So it now sits in the same
        # `site_mode == "app"` block as `admin_users_router` above, and every route on it —
        # including the ones that were already `require(...)`-guarded and the SEND, which was
        # already refused with 409 NOT_LAUNCHED until `SITE_MODE=app` — is a 404 before then. An
        # operator reads the list before the flip with the read-only SQL in RUNBOOK-identity.md
        # §13 instead.
        app.include_router(admin_signups_router)
    app.include_router(interest_router)
    # Resend's delivery events (Task I6). NOT gated on `site_mode`, unlike the auth surface: the
    # provider posts to whichever host sent the mail, and a bounce that arrives after a launch
    # flip must still reach the suppression list. It is public by necessity and verified by
    # signature on every request, so an unconfigured environment answers 401 rather than acting.
    app.include_router(webhooks_router)
    app.include_router(not_found_router)
    mount_spa(app, dist or dist_for(settings.site_mode))
    return app


app = create_app()
