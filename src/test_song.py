from modules.model_song import Song
from src.modules.filesys_utils import find_song_paths
music_dir = "./music"




# Find all song paths in the music directory recursively
song_paths = find_song_paths(music_dir)
print(f"Found {len(song_paths)} songs in {music_dir}")

song_objects = []
for song_path in song_paths:
    print(f"Found song: {song_path}")
    song = Song(song_path)
    song.pretty_print()
    song_objects.append(song)

            
