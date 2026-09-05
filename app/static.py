"""Serve the built Vue app. Fingerprinted bundles under /_app are immutable for a
year; design assets (/assets, /ds) are short-cached because their names never
change (the sub-* icons will be swapped in place); index.html always revalidates."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
INDEX_HEADERS = {"Cache-Control": "no-cache"}
FILE_HEADERS = {"Cache-Control": "public, max-age=3600"}


class ImmutableStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):  # type: ignore[override]
        resp = super().file_response(*args, **kwargs)
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
