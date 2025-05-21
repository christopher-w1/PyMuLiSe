from model_song import Song
from hashlib import sha256

class album:
    def __init__(self):
        self.name = ""
        self.album_artist = ""
        self.artists : list[str] = []
        self.year = 0
        self.play_count = 0
        self.songs : list[Song] = []
        
    def _retag_from_songs(self):
        # Use most common album name
        albumname_count = {}
        play_count = 0
        for song in self.songs:
            play_count += song.play_count
            if song.album and str(song.album).lower() != "unknown":
                albumname_count[song.album] = albumname_count.get(song.album, 0) + 1
        self.play_count = play_count
        max_count = 0
        for albumname, count in albumname_count.items():
            if count > max_count:
                self.name = albumname
                count = max_count
            
        # Use artist name and album name thats included in every song
        artist_count = {}
        name_count = {}
        for song in self.songs:
            if song.album_artist and str(song.album_artist).lower() != "unknown":
                artist_count[song.album_artist] = artist_count.get(song.album_artist, 0) + 1
            if song.album and str(song.album).lower() != "unknown":
                name_count[song.album] = name_count.get(song.album, 0) + 1
        for name, count in name_count.items():
            if count == len(self.songs):
                self.name = name
        for artist, count in artist_count.items():
            if not artist in self.artists:
                self.artists.append(artist)
            if count == len(self.songs):
                self.album_artist = artist
        if not self.album_artist or str(self.album_artist).lower() == "unknown":
            self.album_artist = "Various Artists"
        
    def get_hash(self) -> str:
        hash_str = f"{self.name}{self.album_artist}{self.year}"
        for song in self.songs:
            hash_str += song.get_hash()
        return sha256(hash_str.encode()).hexdigest()
        
    def add_song(self, song: Song):
        if isinstance(song, Song):
            self.songs.append(song)
            self._retag_from_songs()
        else:
            raise TypeError("Expected a Song object")

    def __str__(self):
        return f"Album: {self.name}, Artist: {self.album_artist}, Year: {self.year}"