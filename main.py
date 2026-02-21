from __future__ import annotations

import asyncio
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

try:
    import yt_dlp
except ImportError as exc:  # pragma: no cover
    yt_dlp = None
    YTDLP_IMPORT_ERROR = str(exc)
else:
    YTDLP_IMPORT_ERROR = ""


APP_NAME = "Instagram Media Downloader API"
APP_VERSION = "1.2.4"
DEVELOPER_TAG = "@xoxhunterxd"

app = FastAPI(title=APP_NAME, version=APP_VERSION)


class DownloadRequest(BaseModel):
    url: str = Field(..., description="Instagram reel/post URL")


def _normalize_instagram_input(raw_url: str) -> str:
    candidate = unquote(raw_url.strip())
    match = re.search(r"https?://(?:www\.)?instagram\.com/[^\s]+", candidate, re.IGNORECASE)
    return match.group(0) if match else candidate


def _is_valid_instagram_url(url: str) -> bool:
    return bool(re.match(r"^https?://(www\.)?instagram\.com/.+", url.strip(), re.IGNORECASE))


def _download_instagram_media(url: str) -> tuple[Path, str]:
    temp_dir = Path(tempfile.mkdtemp(prefix="ig_dl_"))

    ydl_opts: dict[str, Any] = {
        "outtmpl": str(temp_dir / "%(id)s.%(ext)s"),
        "format": "best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
        "socket_timeout": 15,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = Path(ydl.prepare_filename(info))

    if not file_path.exists():
        candidates = list(temp_dir.glob("*"))
        if not candidates:
            raise RuntimeError("Download failed: output file not found.")
        file_path = candidates[0]

    title = re.sub(r"[^a-zA-Z0-9._-]+", "_", info.get("title") or "instagram_media").strip("_")
    media_id = info.get("id") or "file"
    ext = file_path.suffix or ".mp4"
    download_name = f"{title}_{media_id}{ext}"

    return file_path, download_name


@app.get("/")
async def root(url: str | None = Query(default=None, description="Instagram reel/post URL")):
    if url:
        return await _download_and_respond(url)

    return JSONResponse(
        {
            "service": APP_NAME,
            "version": APP_VERSION,
            "developer": DEVELOPER_TAG,
            "status": "ok",
        }
    )


async def _download_and_respond(url: str) -> FileResponse:
    normalized_url = _normalize_instagram_input(url)

    if yt_dlp is None:
        raise HTTPException(
            status_code=500,
            detail=f"yt-dlp is not installed. Import error: {YTDLP_IMPORT_ERROR}",
        )

    if not _is_valid_instagram_url(normalized_url):
        raise HTTPException(status_code=400, detail="Invalid Instagram URL.")

    try:
        file_path, download_name = await asyncio.to_thread(_download_instagram_media, normalized_url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to download media: {exc}") from exc

    def _cleanup() -> None:
        try:
            if file_path.exists():
                os.remove(file_path)
            parent = file_path.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass

    return FileResponse(
        path=file_path,
        filename=download_name,
        media_type="application/octet-stream",
        headers={"X-Developer": DEVELOPER_TAG},
        background=BackgroundTask(_cleanup),
    )


@app.post("/api/v1/instagram/download")
async def download_instagram_media_post(payload: DownloadRequest):
    return await _download_and_respond(payload.url)


@app.get("/api/v1/instagram/download")
async def download_instagram_media_get(url: str = Query(..., description="Instagram reel/post URL")):
    return await _download_and_respond(url)


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "healthy", "developer": DEVELOPER_TAG})


@app.get("/{target:path}")
async def download_instagram_media_direct_path(target: str, request: Request):
    raw_target = unquote(target.strip())
    if raw_target.startswith(("http://", "https://")):
        direct_url = raw_target
    else:
        direct_url = f"https://{raw_target}"

    query_text = request.url.query
    if query_text and "?" not in direct_url:
        direct_url = f"{direct_url}?{query_text}"

    return await _download_and_respond(direct_url)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

