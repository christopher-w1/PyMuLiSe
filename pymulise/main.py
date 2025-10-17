from functools import wraps
import os, mimetypes, io
from pathlib import Path
from typing import Optional
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import BackgroundTasks
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi import Query, WebSocket
from PIL import Image
from modules.playback_module import PlaybackChannel, PlaybackModule
from modules.library_service import LibraryService
from modules.user_service import UserService
from modules.filesys_transcoder import Transcoding
from contextlib import asynccontextmanager
from hashlib import sha256

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DEBUG_SKIP = True

library_service = LibraryService()
user_service = UserService(registration_key="pymulise")
playback_module = PlaybackModule()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await library_service.start_background_task()
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def schedule_cleanup(path: str, delay_sec: int = 600):
    import threading, time
    def cleanup():
        time.sleep(delay_sec)
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"Deleted transcoded file: {path}")
        except Exception as e:
            print(f"Cleanup failed: {e}")
    threading.Thread(target=cleanup, daemon=True).start()

def require_session(user_service: "UserService", key_name="session_key"):
    """
    Decorator für FastAPI routes. Extracts session key from request (JSON body or query param),
    verifies it, and injects the user object as a keyword argument to the route.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request, **kwargs):
            if DEBUG_SKIP:
                kwargs["email"] = "debug@example.com"
                kwargs["username"] = "DebugUser"
                return await func(*args, request=request, **kwargs)
            # Session-Key zuerst aus JSON Body, dann Query
            try:
                data = await request.json()
            except:
                data = {}
            session_key = data.get(key_name) or request.query_params.get(key_name)

            if not session_key:
                raise HTTPException(status_code=401, detail="Session key missing")

            user = await user_service.get_user_by_session(session_key)
            if not user:
                raise HTTPException(status_code=401, detail="Invalid session key")

            # user als Keyword-Argument an die Route weitergeben
            kwargs["email"] = user["email"]
            kwargs["username"] = user["username"]
            return await func(*args, request=request, **kwargs)
        return wrapper
    return decorator


@require_session(user_service)
@app.post("/get_songs")
async def get_songs(request: Request, email: str):
    body = await request.json()
    filter_params = body.get("filter_params")
    all_songs, _, _ = await library_service.get_snapshot()
    if filter_params and type(filter_params) == dict:
        filter_title = filter_params.get("title", None)
        filter_artist = filter_params.get("artist", None)
        filter_album = filter_params.get("album", None)
        filter_genres = filter_params.get("genre", None)
        if filter_genres and type(filter_genres) == str:
            filter_genres = filter_genres.split(",")
        elif filter_genres and type(filter_genres) == list:
            filter_genres = [genre.strip() for genre in filter_genres]
        else:
            filter_genres = None
        filter_year = filter_params.get("year", None)
        filter_play_count = filter_params.get("play_count", None)
        filter_hash = filter_params.get("hash", None)
        filtered_songs = [song for song in all_songs if 
                     (filter_title is None or str(filter_title).lower() in song.title.lower()) and
                     (filter_artist is None or str(filter_artist).lower() in song.get_artists().lower()) and
                     (filter_album is None or str(filter_album).lower() in song.album.lower()) and
                     (filter_genres is None or any(genre.lower() in song.genres for genre in filter_genres)) and
                     (filter_year is None or int(filter_year) == song.release_year) and
                     (filter_play_count is None or filter_play_count == song.play_count) and
                     (filter_hash is None or filter_hash == song.get_hash())]
        return {"songs": [song.to_dict() for song in filtered_songs]}
    return {"songs": [song.to_dict() for song in all_songs]}


@app.post("/search_songs")
async def search_songs(request: Request):
    """
    Receives a query string.
    
    Returns a list of song dictionaries.
    Each song dict has:
    hash: str
    title: str
    album: str
    track_number: int
    album_artist: str
    other_artists: str
    genres: list[str]
    loudness: float
    duration: int
    """
    body = await request.json()

    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    
    result_length = body.get("result_limit", 20)

    if len(query) < 3:
        return {"songs": []}

    all_songs, _, _ = await library_service.get_snapshot()
    if not all_songs:
        raise HTTPException(status_code=500, detail="Library is empty")

    # Exact match first by using jaccard similarity
    results = []
    for song in all_songs:
        query_set = set(query.lower().split())
        song_set = set(song.title.lower().split()) | set(song.get_artists().lower().split()) | set(song.album.lower().split())
        title_set = set(song.title.lower().split())
        artist_set = set(song.get_artists().lower().split())

        score = 0
        for word in query_set:
            if word in title_set:
                score += 4 / (1 + len(title_set))
            elif word in artist_set:
                score += 3 / (1 + len(artist_set))
            elif word in song_set:
                score += 2 / (1 + len(song_set))
            elif any(word in s for s in song_set):
                score += 1 / (1 + len(song_set))

        if score > 0:
            song_dict = song.to_dict()
            song_dict["search_score"] = score
            results.append(song_dict)

    # Sort descending
    results.sort(key=lambda x: x["search_score"], reverse=True)
    return results[:result_length]


@require_session(user_service)
@app.post("/get_artists")
async def get_artists(request: Request, email: str):
    body = await request.json()
    _, _, all_artists = await library_service.get_snapshot()
    return {"artists": [artist.to_dict() for artist in all_artists]}


@require_session(user_service)
@app.post("/get_albums")
async def get_albums(request: Request, email: str):
    body = await request.json()
    _, all_albums, _ = await library_service.get_snapshot()
    return {"albums": [album.to_dict() for album in all_albums]}


@require_session(user_service)
@app.post("/get_full_library")
async def get_library(request: Request, email: str):
    body = await request.json()

    all_songs, all_albums, all_artists = await library_service.get_snapshot()
    return {"songs": [song.to_dict() for song in all_songs],
            "artists": [artist.to_dict() for artist in all_artists],
            "albums": [album.to_dict() for album in all_albums]}


@require_session(user_service)
@app.post("/get_song_details")
async def get_song_details(request: Request, email: str):
    body = await request.json()

    song_hash = body.get("song_hash")
    if not song_hash:
        raise HTTPException(status_code=400, detail="Missing song hash")
    if not await library_service.has_song(song_hash):
        raise HTTPException(status_code=404, detail="Song not found in library")
    all_songs, _, _ = await library_service.get_snapshot()
    for song in all_songs:
        if song.get_hash() == song_hash:
            return {"song": song.to_dict()}
    return {}


@require_session(user_service)
@app.post("/get_cover_art")
async def get_cover_art(request: Request, size: int | None = Query(None, gt=0, le=1000)):
    body = await request.json()

    song_hash = body.get("song_hash")
    if not song_hash:
        raise HTTPException(status_code=400, detail="Missing song hash")
    if not await library_service.has_song(song_hash):
        raise HTTPException(status_code=404, detail="Song not found in library")
    file_path = library_service.cover_map.get(song_hash)
    if not file_path:
        raise HTTPException(status_code=404, detail="Cover art not found")
    
    file_hash = sha256(file_path.encode()).hexdigest()
    if size is None:
        return FileResponse(file_path, media_type="image/jpeg", filename=f"{file_hash}.jpg")

    img = Image.open(file_path)
    x, y = img.size
    factor = size / max(x, y, size)
    img.thumbnail((int(factor*x), int(factor*y)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg", headers={"Content-Disposition": f"inline; filename={file_hash}.jpg"})


@require_session(user_service)
@app.post("/get_song_file")
async def get_song_file(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()

    song_hash = body.get("song_hash")
    if not song_hash:
        raise HTTPException(status_code=400, detail="Missing song hash")

    transcode = body.get("transcode", False)
    format_override = body.get("format", "mp3")
    bitrate = body.get("bitrate", 192)
    target_lufs = float(body.get("target_lufs", 0))

    song = await library_service.get_song(song_hash)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    file_path = song.file_path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Original file not found")

    if transcode:
        try:
            transcoder = Transcoding(
                song_hash=song_hash,
                src_file=file_path,
                target_format=format_override,
                target_bitrate=bitrate,
                cache_dir="./transcode_cache",
                volume_change=min(song.peak or 0, target_lufs - (song.loudness or -7)) if target_lufs else 0
            )
            output_file = transcoder.run()
            mime_type = f"audio/{format_override}"

            # Clean up in 10 minutes
            schedule_cleanup(output_file, delay_sec=600)

            return FileResponse(
                path=output_file,
                media_type=mime_type,
                filename=os.path.basename(output_file)
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Transcoding error: {str(e)}")

    # Fallback to original file
    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "application/octet-stream"
    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename=os.path.basename(file_path)
    )


@require_session(user_service)
@app.post("/get_song_file_from_metadata")
async def get_song_file_from_metadata(request: Request, email: str):
    body = await request.json()

    metadata = body.get("metadata")
    if not metadata:
        raise HTTPException(status_code=400, detail="Missing metadata")
    
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="Metadata must be a dictionary")

    song = await library_service.get_song_by_metadata(metadata)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found in library")

    file_path = song.file_path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Song file not found")

    # Try to guess mime type
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "application/octet-stream"
    
    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename=os.path.basename(file_path)
    )
    

@require_session(user_service)
@app.get("/stream/{song_hash}")
async def stream_song(song_hash: str, request: Request, email: Optional[str] = None):
    # Find file path from song hash
    song = await library_service.get_song(song_hash)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    file_path = Path(song.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Original file not found")

    # Handle Range requests
    range_header = request.headers.get("range")
    file_size = file_path.stat().st_size
    start = 0
    end = file_size - 1

    if range_header:
        bytes_range = range_header.strip().split("=")[-1]
        start_end = bytes_range.split("-")

        if start_end[0]:
            start = int(start_end[0])
        if len(start_end) > 1 and start_end[1]:
            end = int(start_end[1])

        if start >= file_size:
            raise HTTPException(status_code=416, detail="Range Not Satisfiable")

    chunk_size = end - start + 1

    # Read file chunks
    def iterfile():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                chunk = f.read(min(4096, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    mime_type = "audio/mp4"

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": mime_type,
    }

    status_code = 206 if range_header else 200
    return StreamingResponse(iterfile(), headers=headers, status_code=status_code)


@app.websocket("/ws/playback/owner={owner_id}?song={song_id}")
async def playback_ws(websocket: WebSocket, owner_id: str, song_id: str | None, session_key: str = Query(...)):
    """
    WebSocket endpoint for playback module.
    Query parameters:
    - owner_id: ID (email) of the channel owner (creator)
    - playlist: List of song hashes to play
    - session_key: Session key of the connecting user
    """
    # Get user email from session key, reject if invalid
    user = await user_service.get_user_by_session(session_key)
    if not user:
        await websocket.close(code=4401)
        return

    # Check if channel exists, create if owner
    channel = await playback_module.get_channel(owner_id)
    if not channel:
        if session_key == owner_id and song_id:
            channel = await playback_module.create_channel(owner_id, [song_id])
        else:
            await websocket.close(code=4404)
            return

    await channel.join(user["email"], websocket)

    try:
        while True:
            data = await websocket.receive_json()
            await channel.handle_message(user["email"], data)
    except:
        await channel.leave(session_key)
        
        
@app.post("/register")
async def register(request: Request):
    data = await request.json()
    try:
        await user_service.register(
            data.get("registration_key"),
            data.get("email"),
            data.get("username"),
            data.get("password"),
            data.get("lastfm_user"),
        )
        username, session_key = await user_service.login(
            data.get("email"),
            data.get("password")
        )
        if not session_key:
            raise HTTPException(status_code=500, detail="Login failed after registration")
        return {"status": "ok",
                "username": username, 
                "session_key": session_key,
                "email": data.get("email")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/login")
async def login(request: Request):
    data = await request.json()
    try:
        username, session_key = await user_service.login(
            data.get("email"),
            data.get("password")
        )
        
        return {"status": "ok",
                "username": username, 
                "session_key": session_key,
                "email": data.get("email")}
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
        
        
def main():
    import uvicorn
    rest_api_port = int(os.getenv("REST_API_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=rest_api_port)


if __name__ == "__main__":
    main()