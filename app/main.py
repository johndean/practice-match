import logging
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app import config
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
from app.api.market import router as market_router
from app.api.seller_listings import router as seller_listings_router
from app.api.webhooks import router as webhooks_router
from app.auth import deps
from app.config import settings
from app.db import dispose_all
from app.security_headers import SecurityHeadersMiddleware, server_error
from app.static import dist_for, mount_spa
from app.version import VERSION

#: The one stream handler `_configure_logging` installs on the `app` logger, named so a second
#: `create_app()` can recognise it rather than stacking another copy.
_LOG_HANDLER_NAME = "practice-match-app"
_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def _configure_logging() -> None:
    """Put the api's own INFO records where an operator can read them.

    Measured on QA 2026-09-12 at `db8bf67`: `railway logs --service api` carried uvicorn's access
    lines and nothing else. Nothing in this module or in `scripts/start.sh` ever called
    `basicConfig` or `dictConfig`, and uvicorn's own `LOGGING_CONFIG` configures only the
    `uvicorn*` loggers, so the root logger sat at its default WARNING with the last-resort handler:
    `log.warning` surfaced and every `log.info` in `app/` — `app/api/market.py`'s structured
    boundaries cost line among them — was written into the void. A cost line nobody can read is a
    measurement nobody has.

    Scope is the `app` logger and nothing else, so every module logger under it inherits the level
    without a list to maintain here, and uvicorn's three loggers are untouched — it owns them and
    configures them itself at server start; setting a level or a handler on them here would either
    duplicate its access lines or silence them.

    Idempotent: the test suite alone creates the app dozens of times, and without the name check
    each creation would stack another handler and print one record once per app ever created.
    """
    logger = logging.getLogger("app")
    # Already normalised and validated by `app.config.Settings._log_level_known`, which never
    # raises: an unknown value is INFO here and is named in the warning below.
    logger.setLevel(settings.log_level)
    if any(h.get_name() == _LOG_HANDLER_NAME for h in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_LOG_HANDLER_NAME)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(handler)
    if config.log_level_rejected is not None:
        # After the handler is installed, so the line has somewhere to go, and inside the
        # once-per-process guard above, so a suite that builds the app dozens of times says it once.
        logger.warning("LOG_LEVEL=%r is not a known level; using INFO", config.log_level_rejected)


def create_app(dist: Path | None = None) -> FastAPI:
    _configure_logging()

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
