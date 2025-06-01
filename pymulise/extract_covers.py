from modules.filesys_utils import find_cover_art, find_song_paths
import os

if __name__ == "__main__":
    music_dir = os.getenv("MUSIC_DIR")
    cover_paths = []
    album_paths = []
    if music_dir:
        file_paths = find_song_paths(music_dir)
        album_paths = [os.path.dirname(path) for path in file_paths]
        for file_path in file_paths:
            cover_path = find_cover_art(file_path)
            if cover_path:
                album_paths.remove(os.path.dirname(cover_path))
    album_paths = list(set(album_paths))
    print(f"Cover missing from {len(album_paths)} albums:")
    print('\n'.join(album_paths))