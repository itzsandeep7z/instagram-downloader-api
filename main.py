from __future__ import annotations

import asyncio
import os
import re
import tempfile
import uuid
import zipfile
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
APP_VERSION = "1.4.0"
DEVELOPER_TAG = "@xoxhunterxd"

app = FastAPI(title=APP_NAME, version=APP_VERSION)


class DownloadRequest(BaseModel):
    url: str = Field(..., description="Instagram reel/post URL")
    delivery: str | None = Field(default=None, description="stream or link")


def _normalize_instagram_input(raw_url: str) -> str:
    candidate = unquote(raw_url.strip())
    match = re.search(r"https?://(?:www\.)?instagram\.com/[^\s]+", candidate, re.IGNORECASE)
    return match.group(0) if match else candidate


def _is_valid_instagram_url(url: str) -> bool:
    return bool(re.match(r"^https?://(www\.)?instagram\.com/.+", url.strip(), re.IGNORECASE))


def _download_instagram_media(url: str) -> tuple[list[Path], str]:
    temp_dir = Path(tempfile.mkdtemp(prefix="ig_dl_"))

    ydl_opts: dict[str, Any] = {
        "outtmpl": str(temp_dir / "%(id)s.%(ext)s"),
        "format": "best",
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
        "socket_timeout": 15,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        primary_path = Path(ydl.prepare_filename(info))

    candidates = [p for p in temp_dir.iterdir() if p.is_file()]
    if not candidates:
        if primary_path.exists():
            candidates = [primary_path]
        else:
            raise RuntimeError("Download failed: output file not found.")

    title = re.sub(r"[^a-zA-Z0-9._-]+", "_", info.get("title") or "instagram_media").strip("_")
    media_id = info.get("id") or "file"
    ext = candidates[0].suffix or ".mp4"
    download_name = f"{title}_{media_id}{ext}"

    return candidates, download_name


def _zip_media(file_paths: list[Path]) -> Path:
    first = file_paths[0]
    zip_path = first.with_suffix(first.suffix + ".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            zf.write(file_path, arcname=file_path.name)
    return zip_path


def _get_r2_config() -> dict[str, str]:
    endpoint = os.getenv("R2_ENDPOINT", "").strip()
    bucket = os.getenv("R2_BUCKET", "").strip()
    access_key = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    public_base = os.getenv("R2_PUBLIC_BASE", "").strip()
    ttl = os.getenv("R2_SIGNED_URL_TTL", "3600").strip()

    if not (endpoint and bucket and access_key and secret_key):
        raise HTTPException(
            status_code=500,
            detail="R2 storage is not configured. Set R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY.",
        )

    return {
        "endpoint": endpoint,
        "bucket": bucket,
        "access_key": access_key,
        "secret_key": secret_key,
        "public_base": public_base,
        "ttl": ttl,
    }


def _upload_to_r2(file_path: Path, object_name: str) -> tuple[str, int | None]:
    config = _get_r2_config()
    try:
        import boto3
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"boto3 is required for R2 uploads: {exc}") from exc

    client = boto3.client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        region_name="auto",
    )

    client.upload_file(str(file_path), config["bucket"], object_name)

    if config["public_base"]:
        base = config["public_base"].rstrip("/")
        return f"{base}/{object_name}", None

    ttl_seconds = int(config["ttl"]) if config["ttl"].isdigit() else 3600
    signed_url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": config["bucket"], "Key": object_name},
        ExpiresIn=ttl_seconds,
    )
    return signed_url, ttl_seconds


@app.get("/")
async def root(
    url: str | None = Query(default=None, description="Instagram reel/post URL"),
    delivery: str | None = Query(default=None, description="stream or link"),
):
    if url:
        return await _download_and_respond(url, delivery)

    return JSONResponse(
        {
            "service": APP_NAME,
            "version": APP_VERSION,
            "developer": DEVELOPER_TAG,
            "status": "ok",
        }
    )


async def _download_and_respond(url: str, delivery: str | None) -> FileResponse | JSONResponse:
    normalized_url = _normalize_instagram_input(url)

    if yt_dlp is None:
        raise HTTPException(
            status_code=500,
            detail=f"yt-dlp is not installed. Import error: {YTDLP_IMPORT_ERROR}",
        )

    if not _is_valid_instagram_url(normalized_url):
        raise HTTPException(status_code=400, detail="Invalid Instagram URL.")

    try:
        file_paths, download_name = await asyncio.to_thread(_download_instagram_media, normalized_url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to download media: {exc}") from exc

    if delivery and delivery.lower() == "link":
        zip_path = _zip_media(file_paths)
        object_name = f"instagram/{uuid.uuid4().hex}/{zip_path.name}"
        download_url, expires_in = _upload_to_r2(zip_path, object_name)

        try:
            for fp in file_paths:
                if fp.exists():
                    os.remove(fp)
            if zip_path.exists():
                os.remove(zip_path)
            parent = file_paths[0].parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass

        payload = {
            "download_url": download_url,
            "filename": zip_path.name,
            "delivery": "link",
            "developer": DEVELOPER_TAG,
        }
        if expires_in:
            payload["expires_in"] = expires_in
        return JSONResponse(payload)

    if len(file_paths) > 1:
        zip_path = _zip_media(file_paths)

        def _cleanup_zip() -> None:
            try:
                for fp in file_paths:
                    if fp.exists():
                        os.remove(fp)
                if zip_path.exists():
                    os.remove(zip_path)
                parent = file_paths[0].parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
            except Exception:
                pass

        return FileResponse(
            path=zip_path,
            filename=zip_path.name,
            media_type="application/zip",
            headers={"X-Developer": DEVELOPER_TAG},
            background=BackgroundTask(_cleanup_zip),
        )

    file_path = file_paths[0]

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
    return await _download_and_respond(payload.url, payload.delivery)


@app.get("/api/v1/instagram/download")
async def download_instagram_media_get(
    url: str = Query(..., description="Instagram reel/post URL"),
    delivery: str | None = Query(default=None, description="stream or link"),
):
    return await _download_and_respond(url, delivery)


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

    delivery = request.query_params.get("delivery")
    return await _download_and_respond(direct_url, delivery)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

