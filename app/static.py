"""Serve the built Vue app. Fingerprinted bundles under /_app are immutable for a
year; design assets (/assets, /ds) are short-cached because their names never
change (the sub-* icons will be swapped in place); index.html always revalidates."""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.staticfiles import PathLike
from starlette.types import Scope

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
COMING_SOON_DIST = Path(__file__).resolve().parent.parent / "coming-soon" / "dist"
INDEX_HEADERS = {"Cache-Control": "no-cache"}
FILE_HEADERS = {"Cache-Control": "public, max-age=3600"}


def dist_for(mode: str) -> Path:
    """The built site the api serves: the marketplace, or the Coming Soon page (production until launch)."""
    return COMING_SOON_DIST if mode == "coming_soon" else DIST


class ImmutableStaticFiles(StaticFiles):
    def file_response(
        self,
        full_path: PathLike,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        resp = super().file_response(full_path, stat_result, scope, status_code)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


def mount_spa(app: FastAPI, dist: Path = DIST) -> None:
    if not dist.exists():
        return
    root = dist.resolve()
    app.mount("/_app", ImmutableStaticFiles(directory=root / "_app"), name="app-bundle")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(root / "index.html", headers=INDEX_HEADERS)

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = (root / path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate, headers=FILE_HEADERS)
        return FileResponse(root / "index.html", headers=INDEX_HEADERS)
