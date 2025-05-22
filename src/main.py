import os, mimetypes
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from modules.library_service import LibraryService

from contextlib import asynccontextmanager

libraryService = LibraryService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await libraryService.start_background_task()
    yield

app = FastAPI(lifespan=lifespan)


def check_access_token(token: str) -> bool:
    valid_token = os.getenv("ACCESS_TOKEN")
    print(f"Valid token: {valid_token}")
    print(f"Provided token: {token}")
    return token == valid_token


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
    # TODO: Prüfe access_token, implementiere Logik
    return {"artists": []}


@app.post("/get_albums")
async def get_albums(request: Request):
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token or not check_access_token(access_token):
        raise HTTPException(status_code=401, detail="Invalid access token")
    # TODO: Prüfe access_token, implementiere Logik
    return {"albums": []}


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
async def get_cover_art(request: Request):
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
    return FileResponse(file_path, media_type="image/jpeg", filename=f"{song_hash}.jpg")


@app.post("/get_song_file")
async def get_song_file(request: Request):
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token or not check_access_token(access_token):
        raise HTTPException(status_code=401, detail="Invalid access token")

    song_hash = body.get("song_hash")
    if not song_hash:
        raise HTTPException(status_code=400, detail="Missing song hash")

    song = await libraryService.get_song(song_hash)
    if not song:
        raise HTTPException(status_code=404, detail="Song hash not found in library")

    file_path = song.file_path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Song file not found")

    # MIME-Type automatisch bestimmen
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "application/octet-stream"  # Fallback, wenn nicht erkannt

    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename= f"{song_hash}.{os.path.basename(file_path).split('.')[-1]}"
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
        
        
@app.get("/")
async def root():
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
        
if __name__ == "__main__":
    import uvicorn
    rest_api_port = int(os.getenv("REST_API_PORT", 8000))
    uvicorn.run(app, host="127.0.0.1", port=rest_api_port)