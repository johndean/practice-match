from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.auth import router as auth_router
from app.api.health import not_found_router
from app.api.health import router as health_router
from app.api.interest import router as interest_router
from app.auth import deps
from app.config import settings
from app.db import dispose_all
from app.security_headers import SecurityHeadersMiddleware
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

    # Spec §3's four headers on every answer, whatever produced it.
    app.add_middleware(SecurityHeadersMiddleware)

    if settings.origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
            allow_methods=["*"], allow_headers=["*"],
        )
    # The one handler that renders app.auth.deps.AuthError as decision A5's body; the installer
    # lives with the dependency it serves (I3 fix round 1, ruling (a)). I4 adds the auth routers.
    deps.install(app)
    app.include_router(health_router)
    # Future /api routers are included here, BEFORE the catch-all below.
    app.include_router(auth_router)
    app.include_router(interest_router)
    app.include_router(not_found_router)
    mount_spa(app, dist or dist_for(settings.site_mode))
    return app


app = create_app()
