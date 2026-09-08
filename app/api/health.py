import asyncio
import functools
from pathlib import Path
from typing import TypedDict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.checks import ComponentStatus, check_db, check_redis
from app.config import settings
from app.version import VERSION

router = APIRouter(prefix="/api")
not_found_router = APIRouter(prefix="/api")  # include LAST among /api routers

# The commit the deployed ARTEFACT was built from. scripts/deploy.sh writes it into the
# `git archive` it uploads and the Dockerfile copies it, so in the image this is
# /app/BUILD_SHA — the same root app/version.py reads pyproject.toml from. The COMMIT_SHA
# setting proves nothing on its own: deploy.sh sets that service variable immediately
# before each upload, which is why healthz still reported the branch's sha on 2026-09-07
# while the tree actually uploaded was main's (P14). Module-level so tests can move it.
BUILD_SHA_FILE = Path(__file__).resolve().parent.parent.parent / "BUILD_SHA"


@functools.cache
def build_sha() -> str:
    """The image's own BUILD_SHA stamp; the COMMIT_SHA setting when there is no stamp
    (a git-connected Railway build, or a local `docker build`) or it is blank.

    Cached (L8): the stamp cannot change inside a running image, and /api/healthz is
    Railway's healthcheck and the nightly load smoke's only target — it must not pay a
    blocking file read per request. Tests that move BUILD_SHA_FILE call
    `build_sha.cache_clear()`.

    UnicodeDecodeError is caught alongside OSError because it is NOT one (L8): a stamp that
    is not valid UTF-8 would otherwise turn the deliberately always-200 healthz into a 500,
    and fail Railway's healthcheck with it. This function must never be the thing that
    breaks."""
    try:
        stamped = BUILD_SHA_FILE.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return settings.commit_sha
    return stamped or settings.commit_sha


class HealthBody(TypedDict):
    status: str
    version: str
    environment: str
    commit_sha: str
    site_mode: str
    db: ComponentStatus
    redis: ComponentStatus


async def _body() -> HealthBody:
    db, redis_ = await asyncio.gather(check_db(settings.database_url), check_redis(settings.redis_url))
    return {
        "status": "ok",
        "version": VERSION,
        "environment": settings.environment,
        "commit_sha": build_sha(),
        "site_mode": settings.site_mode,
        "db": db,
        "redis": redis_,
    }


@router.api_route("/healthz", methods=["GET", "HEAD"])
async def healthz() -> HealthBody:
    """Railway's healthcheck. Always 200; component state is inside the body."""
    return await _body()


@router.api_route("/healthz/deep", methods=["GET", "HEAD"])
async def healthz_deep() -> JSONResponse:
    """Post-deploy probe (scripts/verify-deploy.sh). 503 unless every component is up."""
    body = await _body()
    code = 200 if body["db"]["ok"] and body["redis"]["ok"] else 503
    return JSONResponse(body, status_code=code)


@not_found_router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"], include_in_schema=False)
async def api_not_found(path: str) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": {"code": "NOT_FOUND", "message": f"No API route /api/{path}"}},
        status_code=404,
    )
