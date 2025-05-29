from modules.model_song import Song
from modules.model_album import Album
from modules.filesys_utils import find_song_paths
import os, time
music_dir = os.getenv("MUSIC_DIR")
if not music_dir:
    raise ValueError("MUSIC_DIR environment variable is not set. Please set it to the path of your music directory.")


# Find all song paths in the music directory recursively
print(f"Searching for songs in {music_dir}...")
song_paths = find_song_paths(music_dir)
print(f"Found {len(song_paths)} songs in {music_dir}")

albums_paths = list(set([os.path.dirname(path) for path in song_paths]))
            
print(f"Found {len(albums_paths)} albums in {music_dir}")

song_objects = []
start_time = time.time()
for song_path in song_paths:
    song = Song(song_path, skip_analysis=True)
    song_objects.append(song)
    #print(f"Found song: {song_path}")
    print(f"Scanning Item {len(song_objects)}/{len(song_paths)} | {time.time() - start_time:.2f}s elapsed | Time remaining: {(len(song_paths) - len(song_objects)) * (time.time() - start_time) / len(song_objects):.2f}s")
    
album_objects = []
for album_path in albums_paths:
    print(f"Found album: {album_path}")
    album = Album(album_path)
    song_in_album = [song for song in song_objects if str(album_path).lower().replace('\\','/') in str(song.file_path).lower().replace('\\','/')]
    print(f"Found {len(song_in_album)} songs in album: {album_path}")
    for song in song_in_album:
        album.add_song(song)
    album.pretty_print()
    album_objects.append(album)