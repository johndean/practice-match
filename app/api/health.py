import asyncio
from typing import TypedDict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.checks import ComponentStatus, check_db, check_redis
from app.config import settings
from app.version import VERSION

router = APIRouter(prefix="/api")
not_found_router = APIRouter(prefix="/api")  # include LAST among /api routers


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
        "commit_sha": settings.commit_sha,
        "site_mode": settings.site_mode,
        "db": db,
        "redis": redis_,
    }


@router.get("/healthz")
async def healthz() -> HealthBody:
    """Railway's healthcheck. Always 200; component state is inside the body."""
    return await _body()


@router.get("/healthz/deep")
async def healthz_deep() -> JSONResponse:
    """Post-deploy probe (scripts/verify-deploy.sh). 503 unless every component is up."""
    body = await _body()
    code = 200 if body["db"]["ok"] and body["redis"]["ok"] else 503
    return JSONResponse(body, status_code=code)


@not_found_router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def api_not_found(path: str) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": {"code": "NOT_FOUND", "message": f"No API route /api/{path}"}},
        status_code=404,
    )
