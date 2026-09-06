from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.admin_users import router as admin_users_router
from app.api.applications import router as applications_router
from app.api.auth import router as auth_router
from app.api.health import not_found_router
from app.api.health import router as health_router
from app.api.interest import router as interest_router
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

    @app.get("/robots.txt", include_in_schema=False)
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
