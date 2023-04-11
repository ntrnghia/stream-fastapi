# stream-fastapi

```
docker build -t fastapi-video-streamer .
docker run -it --rm -p 8000:8000 -v D://Videos:/app/videos --name video-streamer fastapi-video-streamer
```
and then:
```
mpv http://localhost:8000/stream/<video_file>
```
It also can be used with nested folders:
```
mpv http://localhost:8000/stream/4k/<video_file>
```
