from typing import Optional
from modules.model_song import Song
from modules.model_album import Album
from hashlib import sha256

CHAR_REPLACEMENTS = {
    " ": "_",
    "/": "_",
    "\\": "_",
    ":": "_",
    "*": "_",
    "?": "_",
    '"': "_",
    "<": "_",
    ">": "_",
    "|": "_",
    "and": "&",
}

class Artist:
    def __init__(self, name: str, genres: Optional[list[str]] = None):
        self.hash = sha256(name.encode()).hexdigest()
        self.name = name
        self.genres = genres
        self.play_count = 0
        self.songs: list[Song] = []
        self.albums: list[Album] = []
        
    def get_hash(self) -> str:
        return self.hash
    
    def _update_most_common_name(self):
        if not self.songs:
            return
        names = {}
        for song in self.songs:
            if song.album_artist and str(song.album_artist).lower() != "unknown":
                names[song.album_artist] = names.get(song.album_artist, 0) + 1
        max_count = 0
        for name, count in names.items():
            if count == len(self.songs):
                self.name = name
            elif count > max_count:
                self.name = name
                max_count = count
                
    def force_update_name(self, name: str):
        self.name = name
        
    def is_artist_of(self, song: Song) -> bool:
        clean_artist_names = song.album_artist.split(",") if song.album_artist else []
        clean_artist_names += song.other_artists if song.other_artists else []
        clean_artist_names = [name.lower().strip() for name in clean_artist_names]
        for key, value in CHAR_REPLACEMENTS.items():
            clean_artist_names = [name.replace(key, value) for name in clean_artist_names]
        clean_name = self.name.lower().strip()
        for key, value in CHAR_REPLACEMENTS.items():
            clean_name = clean_name.replace(key, value)
        if clean_name in clean_artist_names:
            return True
        return False
    
    def add_song(self, song: Song):
        if not self.songs:
            self.songs = []
        if not song in self.songs:
            self.songs.append(song)
        self.play_count += song.play_count
        self._update_most_common_name()

    def __repr__(self):
        return f"Artist(name={self.name}, genre={', '.join(self.genres)})" if self.genres else f"Artist(name={self.name})"