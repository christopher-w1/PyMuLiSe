import os
import json
import time
import random
from tqdm import tqdm
from typing import List, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from modules.general_utils import _jaccard_index
from modules.lastfm_client import LastFMClient
from modules.filesys_utils import calculate_loudness
from modules.model_song import Song
from modules.model_album import Album
from modules.model_artist import Artist
from modules.filesys_utils import find_song_paths
from modules.scene_mapper import map_genre
from modules.wikicrawler import get_band_genres

VARIOUS_TERMS = ["various artists", "verschiedene interpreten", "verschiedene künstler", "various"]

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
        artists = [a for a in song.other_artists + [song.album_artist] if a not in VARIOUS_TERMS] or ["Various Artists"]
        title = song.title

        if artists and title:
            id_map[song_id] = song
            tasks.append((song_id, artists, title, api_key))

    for args in tqdm(tasks, desc="Fetching LastFM data", unit="song"):
        song_id, artists, title, api_key = args
        playcount, tags = None, None
        for artist in artists:
            start_time = time.time()
            _, playcount, tags = fetch_lastfm_data_minimal((song_id, artist, title, api_key))
            if not playcount:
                _, playcount, tags = fetch_lastfm_data_minimal((song_id, Artist.get_simple_name(artist), str(title).split("(")[0].strip(), api_key))

            song = id_map.get(song_id)
            if song:
                song.lastfm_playcount = playcount
                song.lastfm_tags = tags
                song.additional_data["lastfm_update"] = "success" if playcount else "fail"

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
    song_objects = [Song.from_dict(d) for d in tqdm(song_dicts, desc="Loading Songs")]
    song_map = {s.get_hash(): s for s in song_objects}
    print(f"✓ Loaded {len(song_objects)} songs")

    # ALBUMS
    with open("data/albums.json", "r", encoding="utf-8") as f:
        album_dicts = json.load(f)
    album_objects = [Album.from_dict(d, song_map) for d in tqdm(album_dicts, desc="Loading Albums")]
    album_map = {a.hash: a for a in album_objects}
    print(f"✓ Loaded {len(album_objects)} albums")

    # ARTISTS
    with open("data/artists.json", "r", encoding="utf-8") as f:
        artist_dicts = json.load(f)
    artist_objects = [Artist.from_dict(d, song_map, album_map) for d in tqdm(artist_dicts, desc="Loading Artists")]
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
        was_updated = False
        futures = {}
        
        with ProcessPoolExecutor() as executor:
            for song in songs_to_analyze:
                future = executor.submit(calculate_loudness, str(song.file_path))
                futures[future] = song

            for future in tqdm(as_completed(futures), total=len(futures), desc="Analyzing loudness"):
                song = futures[future]
                try:
                    loudness, peak = future.result()
                    if loudness is not None:
                        song.loudness = loudness
                        song.peak = peak
                    #    print(f"✓ {song.title}: {loudness:.2f} LUFS, Peak: {peak:.2f} dBFS")
                    #else:
                    #    print(f"✗ {song.title}: Loudness analysis failed")
                    was_updated = True
                except Exception as e:
                    pass
                    #print(f"✗ {song.title}: Exception during analysis: {e}")

        if was_updated:
            with open("data/songs.json", "w", encoding="utf-8") as f:
                json.dump([s.to_dict() for s in updated_songs], f, ensure_ascii=False, indent=2)
    
    
    song_without_lastfm = [s for s in updated_songs if not s.lastfm_playcount and not s.additional_data.get("lastfm_update", False)]
    if song_without_lastfm:
        print(f"Updating Last.fm data for {len(song_without_lastfm)} songs...")
        update_lastfm_serial_with_throttling(song_without_lastfm)
        was_updated = True

    songs_without_wiki = [s for s in updated_songs if not s.additional_data.get("wiki_update", False)]
        
    if not was_updated and not songs_without_wiki:
        print("Library is up to date. No changes detected.")
        return existing_songs, existing_albums, existing_artists
    
    if songs_without_wiki:
        artist_genre_map = {}
        for song in songs_without_wiki:
            for a in ([song.album_artist] + song.other_artists):
                if a.lower() in VARIOUS_TERMS: continue
                artist_name = Artist.get_simple_name(a)
                artist_genre_map[artist_name] = []
        print(f"Updating genre tags for {len(songs_without_wiki)} songs...")
        for artist_name in tqdm(artist_genre_map.keys(), desc="Processed artists"):
            artist_genre_map[artist_name] = get_band_genres(artist_name)
        for song in tqdm(songs_without_wiki, desc="Processed songs"):
            song_genres = set()
            for a in ([song.album_artist] + song.other_artists):
                if a.lower() in VARIOUS_TERMS: continue
                artist_name = Artist.get_simple_name(a)
                song_genres = song_genres.union(set(artist_genre_map.get(artist_name, [])))
            if song_genres:
                song.genres = list(song_genres)
            song.additional_data['wiki_update'] = True
                
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
    print("Mapping songs to artists...")
    artist_dict: dict[str, Artist] = {}
    for song in tqdm(updated_songs, desc="Processed songs"):
        for artist_name in [song.album_artist] + song.other_artists:
            if artist_name:
                simple_name = Artist.get_simple_name(artist_name)
                if simple_name not in artist_dict.keys():
                    #print("Adding artist", artist_name, f"because {simple_name} not in dict")
                    artist_dict[simple_name] = Artist(artist_name)
                artist_dict[simple_name].add_song(song)
    artist_objects = list(artist_dict.values())
    print(f"{len(artist_objects)} artists found | Dictionary size: {len(artist_dict)}")

    # Map albums to artists
    print("Mapping albums to artists...")
    for artist in tqdm(artist_objects, desc="Processed artists"):
        for album in album_objects:
            for song in album.songs:
                if song.play_count or song.lastfm_playcount:
                    song.popularity = (song.play_count + song.lastfm_playcount) / max(1, artist.play_count)
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

def calc_song_similarity(song1: Song, song2: Song) -> float:
    """
    Calculate the similarity between two songs based on their file names.
    :param song1: Path to the first song.
    :param song2: Path to the second song.
    :return: Similarity score between 0 and 1.
    """
    if (song1.file_path == song2.file_path or
        (song1.album == song2.album and 
        song1.album_artist == song2.album_artist)):
        return 1.0
    
    genre_score     = _jaccard_index(song1.genres, song2.genres)
    tag_score       = _jaccard_index(song1.lastfm_tags, song2.lastfm_tags)
    artist_score    = _jaccard_index(song1.other_artists + [song1.album_artist], 
                                     song2.other_artists + [song2.album_artist])
    date_score      = 1 / (max((song1.release_year - song2.release_year)*0.2, 
                               (song2.release_year - song1.release_year)*0.2, 1))
    
    return min(1, max(genre_score, tag_score, artist_score)*date_score)

def song_recommendations(song: "Song", all_songs: list["Song"], seed: Song|None = None, 
                         threshold: float = 0.1, number: int = 10, scene: str|None = None) -> list["Song"]:
    """
    Get song recommendations based on similarity, with weighted random selection.
    Higher similarity => higher chance of being picked.
    :param song: The song to find recommendations for.
    :param all_songs: List of all songs in the library.
    :param threshold: Similarity threshold for recommendations.
    :param number: Maximum number of recommendations.
    :return: List of recommended songs.
    """
    candidates = [(s, calc_song_similarity(song, s)*min(1, s.popularity)*(
                   (calc_song_similarity(seed, s) if seed else 1)))
                  for s in all_songs if s != song and s.duration >= 120
                  if not scene or scene == map_genre(s.genres)] 
    
    max_similarity = max([similarity for s, similarity in candidates if 
                          s.album_artist != song.album_artist])
    
    if max_similarity:
        candidates = [(s, min(1, similarity/max_similarity)) for s, similarity in candidates]

    if not candidates:
        return []

    if len(candidates) <= number:
        songs = [s for s, sim in candidates]
        random.shuffle(songs)
        return songs

    songs, similarities = zip(*candidates)
    total = sum(similarities)
    if total == 0:
        probabilities = [1 / len(songs)] * len(songs)
    else:
        probabilities = [sim / total for sim in similarities]

    recommendations = random.choices(songs, weights=probabilities, k=number)
    recommendations = list(dict.fromkeys(recommendations))

    while len(recommendations) < number and len(recommendations) < len(songs):
        remaining = [s for s in songs if s not in recommendations]
        recommendations.append(random.choice(remaining))

    return recommendations

import random

def song_recommendations_genre(genre: str,
                               all_songs: list["Song"],
                               threshold: float = 0.2,
                               number: int = 10) -> list["Song"]:
    g = genre.lower()
    candidates = [(s, s.popularity)
                  for s in all_songs if getattr(s, "duration", 0) >= 120
                  and ("pop" in g or not any("pop" in gg for gg in s.genres))
                  and any(g in gg for gg in s.genres)]

    if not candidates:
        return []

    songs, probs = zip(*candidates)
    probs = list(probs)

    total = sum(probs)
    if total <= 0:
        weights = [1.0] * len(songs)
    else:
        weights = [p / total for p in probs] 

    picks = random.choices(songs, weights=weights, k=number)

    recommendations = list(dict.fromkeys(picks))

    if len(recommendations) < number:
        remaining = [s for s in songs if s not in recommendations]
        random.shuffle(remaining)
        recommendations.extend(remaining[:number - len(recommendations)])

    return recommendations[:number]
