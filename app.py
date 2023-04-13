import asyncio
import os
from pathlib import PurePath

import aiofiles
import gdown
import rarfile
import zipfile
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI()

STREAM_PREFIX = "/stream/"
VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv')


async def video_stream(file_path, request: Request, chunk_size=8192):
    """Streams a video file."""

    if file_path.lower().endswith((".zip", ".rar")):
        return await stream_video_from_archive(file_path, request, chunk_size)
    else:
        return await stream_video(file_path, request, chunk_size)


async def stream_video(file_path, request: Request, chunk_size=8192):
    """Streams a non-archive video file."""

    file_size = os.path.getsize(file_path)
    start, end, content_length, response_headers = calculate_range(
        file_size, request)

    async def file_stream():
        async with aiofiles.open(file_path, "rb") as f:
            await f.seek(start)
            remaining = end - start + 1
            while remaining:
                to_read = min(remaining, chunk_size)
                data = await f.read(to_read)
                remaining -= to_read
                yield data

    return StreamingResponse(
        file_stream(),
        headers=response_headers,
        media_type="video/mp4",
        status_code=206,
    )


async def stream_video_from_archive(file_path, request: Request, chunk_size=8192):
    """Streams a video file from a ZIP or RAR archive."""

    archive_type, video_file, file_size = get_video_from_archive(file_path)

    if not video_file:
        raise HTTPException(
            status_code=404, detail="Video file not found in archive")

    start, end, content_length, response_headers = calculate_range(
        file_size, request)

    async def archive_stream():
        if archive_type == "zip":
            async for data in stream_from_zip(file_path, video_file, start, end, chunk_size):
                yield data
        elif archive_type == "rar":
            async for data in stream_from_rar(file_path, video_file, start, end, chunk_size):
                yield data

    return StreamingResponse(
        archive_stream(),
        headers=response_headers,
        media_type="video/mp4",
        status_code=206,
    )


def calculate_range(file_size, request: Request):
    """Calculates range for partial content streaming."""

    start = 0
    end = file_size - 1
    range_header = request.headers.get("range")

    if range_header:
        start_str, end_str = range_header.strip().split("=")[1].split("-")
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1

    content_length = end - start + 1
    response_headers = {
        "Accept-Ranges": "bytes",
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(content_length),
    }

    return start, end, content_length, response_headers


async def stream_from_zip(file_path, video_file, start, end, chunk_size=8192):
    """Streams a video file from a ZIP archive."""

    try:
        with zipfile.ZipFile(file_path) as zip_file:
            with zip_file.open(video_file, "r") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining:
                    to_read = min(remaining, chunk_size)
                    data = f.read(to_read)
                    remaining -= to_read
                    yield data
                    await asyncio.sleep(0)
    except asyncio.CancelledError:
        pass


async def stream_from_rar(file_path, video_file, start, end, chunk_size=8192):
    """Streams a video file from a RAR archive."""

    try:
        with rarfile.RarFile(file_path) as rar_file:
            with rar_file.open(video_file, "r") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining:
                    to_read = min(remaining, chunk_size)
                    data = f.read(to_read)
                    remaining -= to_read
                    yield data
                    await asyncio.sleep(0)
    except asyncio.CancelledError:
        pass


def get_video_from_archive(file_path):
    """Returns video file information from a ZIP or RAR archive."""

    archive_type = None
    video_file = None
    file_size = None

    if file_path.lower().endswith(".zip"):
        archive_type = "zip"
        with zipfile.ZipFile(file_path, 'r') as zf:
            for file in zf.namelist():
                if file.lower().endswith(VIDEO_EXTS):
                    video_file = file
                    break
            if video_file:
                file_size = zf.getinfo(video_file).file_size

    elif file_path.lower().endswith(".rar"):
        archive_type = "rar"
        with rarfile.RarFile(file_path, 'r') as rf:
            for file in rf.infolist():
                if file.filename.lower().endswith(VIDEO_EXTS):
                    video_file = file.filename
                    break
            if video_file:
                file_size = file.file_size

    return archive_type, video_file, file_size


class VideoStreamMiddleware(BaseHTTPMiddleware):
    """Middleware for handling video streaming."""

    async def dispatch(self, request, call_next):
        path = request.url.path
        if path.startswith(STREAM_PREFIX):
            relative_path = PurePath(path[len(STREAM_PREFIX):])
            file_path = os.path.join("videos", str(relative_path))
            if os.path.isfile(file_path):
                return await video_stream(file_path, request)
            else:
                return JSONResponse({"error": "File not found"}, status_code=404)
        return await call_next(request)


app.add_middleware(VideoStreamMiddleware)
app.mount("/videos", StaticFiles(directory="videos"), name="videos")


@app.get("/gdrive/{file_id}")
async def download_and_stream_gdrive(file_id: str, request: Request):
    """Downloads a video file from Google Drive and streams it."""

    output_directory = "videos"
    output_filename = f"{file_id}.mp4"
    output_file_path = os.path.join(output_directory, output_filename)

    if not os.path.isfile(output_file_path):
        gdrive_url = f"https://drive.google.com/uc?id={file_id}"
        gdown.download(gdrive_url, output_file_path)

    return await video_stream(output_file_path, request)
