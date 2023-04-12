from pathlib import PurePath
import os

import aiofiles
import gdown
import zipfile
import asyncio
import rarfile
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI()

STREAM_PREFIX = "/stream/"
VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv')


async def video_stream(file_path, request: Request, chunk_size=8192):
    video_file = None
    file_size = None

    if file_path.lower().endswith(".zip"):
        with zipfile.ZipFile(file_path, 'r') as zf:
            for file in zf.namelist():
                if file.lower().endswith(VIDEO_EXTS):
                    video_file = file
                    break
            if not video_file:
                raise HTTPException(
                    status_code=404, detail="Video file not found in archive")
            file_size = zf.getinfo(video_file).file_size

    elif file_path.lower().endswith(".rar"):
        with rarfile.RarFile(file_path, 'r') as rf:
            for file in rf.infolist():
                if file.filename.lower().endswith(VIDEO_EXTS):
                    video_file = file.filename
                    break
            if not video_file:
                raise HTTPException(
                    status_code=404, detail="Video file not found in archive")
            file_size = file.file_size

    else:
        file_size = os.path.getsize(file_path)

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

    async def file_stream():
        if file_path.lower().endswith(".zip"):
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

        elif file_path.lower().endswith(".rar"):
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

        else:
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


class VideoStreamMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if path.startswith(STREAM_PREFIX):
            # Remove the STREAM_PREFIX and create a PurePath object
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
    # Set up the output directory and file path
    output_directory = "videos"
    output_filename = f"{file_id}.mp4"
    output_file_path = os.path.join(output_directory, output_filename)

    # Check if the file is already in the "videos" folder
    if not os.path.isfile(output_file_path):
        # Download the file from Google Drive using gdown
        gdrive_url = f"https://drive.google.com/uc?id={file_id}"
        gdown.download(gdrive_url, output_file_path)

    # Stream the video
    return await video_stream(output_file_path, request)
