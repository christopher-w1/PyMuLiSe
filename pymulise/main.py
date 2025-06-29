import os, mimetypes, io
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import BackgroundTasks
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi import Query
from PIL import Image
from modules.library_service import LibraryService
from modules.filesys_transcoder import Transcoding
from contextlib import asynccontextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

libraryService = LibraryService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await libraryService.start_background_task()
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

def check_access_token(token: str) -> bool:
    valid_token = os.getenv("ACCESS_TOKEN")
    if not valid_token:
        return True
    print(f"Valid token: {valid_token}")
    print(f"Provided token: {token}")
    return token == valid_token

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

@app.post("/get_songs")
async def get_songs(request: Request):
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token or not check_access_token(access_token):
        raise HTTPException(status_code=401, detail="Invalid access token")
    filter_params = body.get("filter_params")
    all_songs, _, _ = await libraryService.get_snapshot()
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


@app.post("/get_artists")
async def get_artists(request: Request):
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token or not check_access_token(access_token):
        raise HTTPException(status_code=401, detail="Invalid access token")
    _, _, all_artists = await libraryService.get_snapshot()
    return {"artists": [artist.to_dict() for artist in all_artists]}


@app.post("/get_albums")
async def get_albums(request: Request):
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token or not check_access_token(access_token):
        raise HTTPException(status_code=401, detail="Invalid access token")
    _, all_albums, _ = await libraryService.get_snapshot()
    return {"albums": [album.to_dict() for album in all_albums]}


@app.post("/get_full_library")
async def get_library(request: Request):
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token or not check_access_token(access_token):
        raise HTTPException(status_code=401, detail="Invalid access token")
    all_songs, all_albums, all_artists = await libraryService.get_snapshot()
    return {"songs": [song.to_dict() for song in all_songs],
            "artists": [artist.to_dict() for artist in all_artists],
            "albums": [album.to_dict() for album in all_albums]}


@app.post("/get_song_details")
async def get_song_details(request: Request):
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token or not check_access_token(access_token):
        raise HTTPException(status_code=401, detail="Invalid access token")
    song_hash = body.get("song_hash")
    if not song_hash:
        raise HTTPException(status_code=400, detail="Missing song hash")
    if not await libraryService.has_song(song_hash):
        raise HTTPException(status_code=404, detail="Song not found in library")
    all_songs, _, _ = await libraryService.get_snapshot()
    for song in all_songs:
        if song.get_hash() == song_hash:
            return {"song": song.to_dict()}
    return {}


@app.post("/get_cover_art")
async def get_cover_art(request: Request, size: int | None = Query(None, gt=0, le=1000)):
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token or not check_access_token(access_token):
        raise HTTPException(status_code=401, detail="Invalid access token")
    song_hash = body.get("song_hash")
    if not song_hash:
        raise HTTPException(status_code=400, detail="Missing song hash")
    if not await libraryService.has_song(song_hash):
        raise HTTPException(status_code=404, detail="Song not found in library")
    file_path = libraryService.cover_map.get(song_hash)
    if not file_path:
        raise HTTPException(status_code=404, detail="Cover art not found")
    
    if size is None:
        return FileResponse(file_path, media_type="image/jpeg", filename=f"{song_hash}.jpg")

    img = Image.open(file_path)
    x, y = img.size
    factor = size / max(x, y, size)
    img.thumbnail((int(factor*x), int(factor*y)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg", headers={"Content-Disposition": f"inline; filename={song_hash}.jpg"})



@app.post("/get_song_file")
async def get_song_file(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token or not check_access_token(access_token):
        raise HTTPException(status_code=401, detail="Invalid access token")

    song_hash = body.get("song_hash")
    if not song_hash:
        raise HTTPException(status_code=400, detail="Missing song hash")

    transcode = body.get("transcode", False)
    format_override = body.get("format", "mp3")
    bitrate = body.get("bitrate", 192)
    target_lufs = float(body.get("target_lufs", 0))

    song = await libraryService.get_song(song_hash)
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


@app.post("/get_song_file_from_metadata")
async def get_song_file_from_metadata(request: Request):
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token or not check_access_token(access_token):
        raise HTTPException(status_code=401, detail="Invalid access token")

    metadata = body.get("metadata")
    if not metadata:
        raise HTTPException(status_code=400, detail="Missing metadata")
    
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="Metadata must be a dictionary")

    song = await libraryService.get_song_by_metadata(metadata)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found in library")

    file_path = song.file_path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Song file not found")

    # MIME-Type automatisch bestimmen
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "application/octet-stream"
    
    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename=os.path.basename(file_path)
    )
        
        
@app.get("/api")
async def api_info():
    return {"message": "Welcome to the PyMuLiSe API!",
            "status": "running",
            "available_endpoints": [
                "/get_songs",
                "/get_artists",
                "/get_albums",
                "/get_song_details",
                "/get_cover_art",
                "/get_song_file",
                "/get_song_file_from_metadata"
            ]}
    
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse(content="index.html nicht gefunden", status_code=404)
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)
        
def main():
    import uvicorn
    rest_api_port = int(os.getenv("REST_API_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=rest_api_port)

if __name__ == "__main__":
    main()