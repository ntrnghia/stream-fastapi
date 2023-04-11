from pathlib import PurePath
import os

import aiofiles
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI()

STREAM_PREFIX = "/stream/"


# class FileIterator:
#     def __init__(self, file_path, start, end, chunk_size=8192):
#         self.file_path = file_path
#         self.start = start
#         self.end = end
#         self.chunk_size = chunk_size

#     async def __aiter__(self):
#         async with aiofiles.open(self.file_path, "rb") as file:
#             await file.seek(self.start)
#             remaining = self.end - self.start + 1
#             while remaining:
#                 to_read = min(remaining, self.chunk_size)
#                 data = await file.read(to_read)
#                 remaining -= to_read
#                 yield data


async def video_stream(file_path, request: Request, chunk_size=8192):
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
        async with aiofiles.open(file_path, "rb") as file:
            await file.seek(start)
            remaining = end - start + 1
            while remaining:
                to_read = min(remaining, chunk_size)
                data = await file.read(to_read)
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
