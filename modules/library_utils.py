import os
import json
import time
from tqdm import tqdm
from typing import List, Tuple
from concurrent.futures import ProcessPoolExecutor
from modules.lastfm_client import LastFMClient
from modules.filesys_utils import calculate_loudness
from modules.model_song import Song
from modules.model_album import Album
from modules.model_artist import Artist
from modules.filesys_utils import find_song_paths

def fetch_lastfm_data_minimal(args: Tuple[str, str, str, str]) -> Tuple[str, int, List[str]]:
    song_id, artist, title, api_key = args
    client = LastFMClient(api_key)
    info = client.get_track_info(artist, title)
    if not info:
        return (song_id, 0, [])
    
    try:
        playcount = int(info.get("playcount", 0))
    except:
        playcount = 0

    tags_raw = info.get("toptags", {}).get("tag", [])
    if isinstance(tags_raw, dict):
        tags_raw = [tags_raw]
    tags = [t.get("name", "").strip() for t in tags_raw if t.get("name")]

    return (song_id, playcount, tags)


def update_lastfm_serial_with_throttling(songs: List[Song], delay_per_request: float = 0.25) -> None:
    """
    Get Last.fm data for a list of songs with throttling.
    :param songs: List of Song objects to update.
    """
    api_key = os.getenv("LASTFM_API_KEY")
    if not api_key:
        raise ValueError("LASTFM_API_KEY environment variable is not set.")

    id_map = {}
    tasks = []

    for song in songs:
        song_id = str(song.file_path)
        artist = (song.album_artist if song.album_artist != "Various Artists"
                  else None) or (song.other_artists[0] if song.other_artists else None) or "Various Artists"
        title = song.title

        if artist and title:
            id_map[song_id] = song
            tasks.append((song_id, artist, title, api_key))

    for args in tqdm(tasks, desc="Fetching LastFM data", unit="song"):
        start_time = time.time()
        _, artist, title, _ = args
        song_id, playcount, tags = fetch_lastfm_data_minimal(args)
        song = id_map.get(song_id)
        if not playcount or not tags:
            print(f"Last.fm data incomplete for {artist} - {title}: playcount={playcount}, tags={tags}")
        if song:
            song.lastfm_playcount = playcount
            song.lastfm_tags = tags
        time_taken = time.time() - start_time
        if time_taken < delay_per_request:
            time.sleep(delay_per_request - time_taken)
    
def init_library():
    is_new = False
    if not os.path.exists("data"):
        print("Creating library directory...")
        os.makedirs("data", exist_ok=True)
        is_new = True
    # Make json files if they don't exist
    if not os.path.exists("data/songs.json"):
        with open("data/songs.json", "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        is_new = True
    if not os.path.exists("data/albums.json"):
        with open("data/albums.json", "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    if not os.path.exists("data/artists.json"):
        is_new = True
        with open("data/artists.json", "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        is_new = True
    return is_new


def load_library() -> tuple[list[Song], list[Album], list[Artist]]:
    print("Loading library from ./data...")
    
    # Check if the output directory exists
    if init_library():
        return [], [], []

    # SONGS
    with open("data/songs.json", "r", encoding="utf-8") as f:
        song_dicts = json.load(f)
    song_objects = [Song.from_dict(d) for d in song_dicts]
    song_map = {s.get_hash(): s for s in song_objects}
    print(f"✓ Loaded {len(song_objects)} songs")

    # ALBUMS
    with open("data/albums.json", "r", encoding="utf-8") as f:
        album_dicts = json.load(f)
    album_objects = [Album.from_dict(d, song_map) for d in album_dicts]
    album_map = {a.hash: a for a in album_objects}
    print(f"✓ Loaded {len(album_objects)} albums")

    # ARTISTS
    with open("data/artists.json", "r", encoding="utf-8") as f:
        artist_dicts = json.load(f)
    artist_objects = [Artist.from_dict(d, song_map, album_map) for d in artist_dicts]
    print(f"✓ Loaded {len(artist_objects)} artists")

    print("✓ Library successfully loaded.")

    return song_objects, album_objects, artist_objects


def scan_library(verbose: bool = False) -> tuple[list[Song], list[Album], list[Artist]]:
    music_dir = os.getenv("MUSIC_DIR")
    if not music_dir:
        raise ValueError("MUSIC_DIR environment variable is not set.")

    was_updated = False

    # Load existing library
    existing_songs, existing_albums, existing_artists = load_library()
    existing_song_map = {s.get_hash(): s for s in existing_songs}
    existing_paths = {str(s.file_path) for s in existing_songs}

    # Scan new files
    song_paths = find_song_paths(music_dir)
    print(f"Scanning {len(song_paths)} songs from disk...")

    updated_songs: list[Song] = []
    new_songs: list[Song] = []

    for i, song_path in enumerate(song_paths):
        if song_path in existing_paths:
            # Existing file -> skip analysis
            existing_song = next(s for s in existing_songs if str(s.file_path) == song_path)
            updated_songs.append(existing_song)
        else:
            # New file -> create new Song object
            new_song = Song(song_path, skip_analysis=True)
            is_new = True
            was_updated = True
            # Check if the song already exists in the library and was moved
            for existing_song in existing_songs:
                if new_song.get_hash() == existing_song.get_hash():
                    print(f"Song {new_song.file_path} already exists in library as {existing_song.file_path}")
                    print(f"Assuming the song was moved, updating file path...")
                    existing_song.file_path = new_song.file_path
                    existing_songs.remove(existing_song)
                    updated_songs.append(existing_song)
                    is_new = False
                    break
            if is_new:
                new_songs.append(new_song)
                updated_songs.append(new_song)

        if verbose:
            print(f"[{i + 1}/{len(song_paths)}] {song_path} {'(new)' if song_path not in existing_paths else ''}")

          
    # Remove songs that were deleted
    for existing_song in existing_songs:
        if str(existing_song.file_path) not in song_paths:
            print(f"Song {existing_song.file_path} was deleted")
            updated_songs.remove(existing_song)
            was_updated = True
            
    if was_updated:
        with open("data/songs.json", "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in updated_songs], f, ensure_ascii=False, indent=2)
            
    # Calculate loudness and peak for songs without analysis
    songs_to_analyze = [s for s in updated_songs if not s.loudness]
    if songs_to_analyze:
        print(f"Calculating loudness for {len(songs_to_analyze)} songs...")
        paths_to_analyze = [str(song.file_path) for song in songs_to_analyze]
        with ProcessPoolExecutor() as executor:
            results = list(executor.map(calculate_loudness, paths_to_analyze))
        for song, (loudness, peak) in zip(songs_to_analyze, results):
            if loudness is not None:
                song.loudness = loudness
                song.peak = peak
                print(f"✓ {song.title}: {loudness:.2f} LUFS, Peak: {peak:.2f} dBFS")
            else:
                print(f"✗ {song.title}: Loudness analysis failed")
        was_updated = True
        with open("data/songs.json", "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in updated_songs], f, ensure_ascii=False, indent=2)
    
    
    song_without_lastfm = [s for s in updated_songs if not s.lastfm_playcount]
    if song_without_lastfm:
        print(f"Updating Last.fm data for {len(song_without_lastfm)} songs...")
        update_lastfm_serial_with_throttling(song_without_lastfm)
        was_updated = True
        
    if not was_updated and False:
        print("Library is up to date. No changes detected.")
        return existing_songs, existing_albums, existing_artists
                
    # Map songs to albums
    album_paths = list(set(os.path.dirname(path) for path in song_paths))
    album_objects: list[Album] = []
    for album_path in album_paths:
        album = Album(album_path)
        songs_in_album = [
            s for s in updated_songs
            if album_path.lower().replace("\\", "/") in str(s.file_path).lower().replace("\\", "/")
        ]
        for song in songs_in_album:
            album.add_song(song)
        album_objects.append(album)
    album_map = {a.hash: a for a in album_objects}
    
    # Guess loudness and peak for songs without analysis
    for album in album_objects:
        if album.loudness:
            for song in album.songs:
                if not song.loudness:
                    song.loudness = album.loudness
                if not song.peak:
                    song.peak = album.peak

    # Map songs to artists
    artist_dict: dict[str, Artist] = {}
    for song in updated_songs:
        artist_names_raw = []
        for artist_name in [song.album_artist] + song.other_artists:
            if artist_name and not artist_name in artist_names_raw:
                artist_names_raw.append(song.album_artist)

        for raw_name in artist_names_raw:
            simple_name = Artist.get_simple_name(raw_name)
            if simple_name not in artist_dict.keys():
                print(f"{simple_name} not in Artist keys, adding...")
                artist_dict[simple_name] = Artist(raw_name)
            artist_dict[simple_name].add_song(song)
    artist_objects = list(artist_dict.values())

    # Map albums to artists
    for artist in artist_objects:
        for album in album_objects:
            for song in album.songs:
                if song in artist.songs and album not in artist.albums:
                    artist.albums.append(album)

    # Speichern
    print("Saving updated library...")
    os.makedirs("output", exist_ok=True)

    with open("data/songs.json", "w", encoding="utf-8") as f:
        json.dump([s.to_dict() for s in updated_songs], f, ensure_ascii=False, indent=2)

    with open("data/albums.json", "w", encoding="utf-8") as f:
        json.dump([a.to_dict() for a in album_objects], f, ensure_ascii=False, indent=2)

    with open("data/artists.json", "w", encoding="utf-8") as f:
        json.dump([a.to_dict() for a in artist_objects], f, ensure_ascii=False, indent=2)

    print(f"✓ Library updated successfully with {len(new_songs)} new songs.")
    return updated_songs, album_objects, artist_objects

def song_similartiy(song1: Song, song2: Song) -> float:
    """
    Calculate the similarity between two songs based on their file names.
    :param song1: Path to the first song.
    :param song2: Path to the second song.
    :return: Similarity score between 0 and 1.
    """
    similarity = 0.0
    
    if song1.file_path == song2.file_path:
        return 1.0
    
    similarity += (len(set(song1.genres) & set(song2.genres)) / max(1, len(set(song1.genres) | set(song2.genres)))) * 0.5
    similarity += (len(set(song1.lastfm_tags) & set(song2.lastfm_tags)) / max(1, len(set(song1.lastfm_tags) | set(song2.lastfm_tags)))) * 0.5
    
    if song1.album.lower() == song2.album.lower() and song1.album_artist.lower() == song2.album_artist.lower():
        similarity += 0.5
    
    return min(1, similarity)

def song_recommendations(song: Song, all_songs: list[Song], threshold: float = 0.5) -> list[Song]:
    """
    Get song recommendations based on the similarity of the given song to other songs in the library.
    :param song: The song to find recommendations for.
    :param all_songs: List of all songs in the library.
    :param threshold: Similarity threshold for recommendations.
    :return: List of recommended songs.
    """
    recommendations = []
    for other_song in all_songs:
        if song != other_song and song_similartiy(song, other_song) >= threshold:
            recommendations.append(other_song)
    return recommendations