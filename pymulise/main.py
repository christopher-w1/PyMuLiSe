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
from modules.library_utils import song_recommendations, song_recommendations_genre
from modules.playback_module import PlaybackChannel, PlaybackModule
from modules.library_service import LibraryService
from modules.scene_mapper import sample_songs_by_scene
from modules.user_service import UserService
from modules.filesys_transcoder import Transcoding
from contextlib import asynccontextmanager
from hashlib import sha256
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DEBUG_SKIP = True

library_service = LibraryService()
user_service = UserService(registration_key="pymulise")
sessions = {}

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
            song_dict = song.to_simple_dict()
            song_dict["search_score"] = score
            results.append(song_dict)

    # Sort descending
    results.sort(key=lambda x: x["search_score"], reverse=True)
    return results[:result_length]


@require_session(user_service)
@app.post("/get_song_details")
async def get_song_details(request: Request):
    body = await request.json()

    song_hash = body.get("song_hash")
    if not song_hash:
        raise HTTPException(status_code=400, detail="Missing song hash")
    if not await library_service.has_song(song_hash):
        raise HTTPException(status_code=404, detail="Song not found in library")
    all_songs, _, _ = await library_service.get_snapshot()
    for song in all_songs:
        if song.get_hash() == song_hash:
            return {"song": song.to_simple_dict()}
    return {}


@require_session(user_service)
@app.get("/get_cover_art")
async def get_cover_art( cover_hash: str = Query(...),
    size: int | None = Query(None, gt=0, le=2000) ):
    file_path = library_service.cover_map.get(cover_hash)
    if not file_path:
        raise HTTPException(status_code=404, detail="Cover art not found")

    headers = {
        "Content-Disposition": f"inline; filename={cover_hash}.jpg",
        "Cache-Control": "public, max-age=86400"
    }

    if size is None:
        return FileResponse(file_path, media_type="image/jpeg", headers=headers)

    img = Image.open(file_path)
    x, y = img.size
    factor = size / max(x, y, size)
    img.thumbnail((int(factor * x), int(factor * y)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg", headers=headers)


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
        
        
@app.get("/ping")
async def ping():
    return {"status": "ok"}


@require_session(user_service)
@app.post("/session/update/{session_id}")
async def update_session(session_id: str, request: Request):
    data = await request.json()
    if not data:
        raise HTTPException(status_code=400, detail="Missing session data")

    session = sessions.get(session_id, {})
    guest_commands = session.get("guest_commands", [])

    sessions[session_id] = {
        "host_ping": data.get("host_ping"),
        "current_song": data.get("current_song"),
        "playlist": data.get("playlist"),
        "playback_timestamp": data.get("playback_timestamp"),
        "guest_commands": [],
        "last_update": datetime.utcnow()
    }

    return {
        "status": "ok",
        "guest_commands": guest_commands
    }


@app.get("/session/get/{session_id}")
async def get_session(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
        
        
@app.get("/recommendations/{song_hash}")
async def get_song_recommendations(song_hash: str, seed_hash: str | None = Query(None)):
    song = await library_service.get_song(song_hash)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    all_songs, _, _ = await library_service.get_snapshot()
    seed = await library_service.get_song(seed_hash) if seed_hash else None
    recommendations = [song.to_simple_dict() for 
                       song in song_recommendations(song, all_songs, seed, 0.1, 10)]
    return {
        "status": "ok",
        "recommendations": recommendations
    }  
   
    
@app.get("/songs-from-genre/{genre}")
async def get_song_recommendations2(genre: str):
    all_songs, _, _ = await library_service.get_snapshot()
    recommendations = [song.to_simple_dict() for 
                       song in song_recommendations_genre(genre, all_songs, 0.5, 10)]
    return {
        "status": "ok",
        "recommendations": recommendations
    }
    
@app.get("/recommendations-by-scene/{n}")
async def get_song_recommendations3(n: str):
    print(f"Requested: {n} recommendations")
    all_songs, _, _ = await library_service.get_snapshot()
    scene_dict = sample_songs_by_scene(all_songs, int(n))
    return {
        "status": "ok",
        "recommendations": scene_dict
    }
        
        
def main():
    import uvicorn
    rest_api_port = int(os.getenv("REST_API_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=rest_api_port)


if __name__ == "__main__":
    main()