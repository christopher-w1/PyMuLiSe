from modules.model_song import Song
from hashlib import sha256
from modules.utils import find_cover_art

class Album:
    def __init__(self, album_path: str):
        self.name = ""
        self.album_artist = ""
        self.artists : list[str] = []
        self.release_year = 0
        self.play_count = 0
        self.songs : list[Song] = []
        self.path = ""
        self.cover_art = find_cover_art(album_path)
        self.album_path = album_path
        self.loudness = 0
        self.peak = 0
        self.hash = sha256(album_path.encode()).hexdigest()
        
    def _retag_from_songs(self):
        """
        Update the album metadata based on the songs in the album.
        This method will update the album name, artist, and release year based on the songs in the album.
        """
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
        
        # Use most current year
        self.release_year = max([song.release_year for song in self.songs if song.release_year] + [self.release_year])
        
    def _sort_by_track_number(self):
        """
        Sort the songs in the album by track number and disc number.
        """
        self.songs.sort(key=lambda x: (x.disc_number, x.track_number))
            
    def pretty_print(self):
        """
        Print the album information in a readable format.
        This method will print the album name, artist, release year, play count, and the number of songs in the album,
        as well as the details of each song in the album.
        The details of each song include the title, artist(s), and release year.
        """
        print(f"Album: {self.name}")
        print(f"Artist: {self.album_artist}")
        print(f"Year: {self.release_year}")
        print(f"Play Count: {self.play_count}")
        print(f"Songs: {len(self.songs)}")
        for song in self.songs:
            print(f"  - {song.title} by {song.get_artists()} ({song.release_year})")
        
    def get_hash(self) -> str:
        """Return the initially generated hash of the album.
        This hash was generated from the album path and is used to identify the album.

        Returns:
            str: The hash of the album.
        """
        return self.hash
        
    def add_song(self, song: Song):
        """Add a song to the album and update metadata.
        This method will also update the album name, artist, and release year

        Args:
            song (Song): The song to add to the album.

        Raises:
            TypeError: If the provided song is not an instance of the Song class.
        """
        if isinstance(song, Song):
            self.songs.append(song)
            self._retag_from_songs()
            self._sort_by_track_number()
        else:
            raise TypeError("Expected a Song object")
        
    def album_folder_contains(self, song: Song) -> bool:
        """Check if the song is part of the album based on the file path.
        This method checks if the song's file path starts with the album's path.

        Args:
            song (Song): The song to check.

        Returns:
            bool: True if the song is part of the album, False otherwise.
        """
        if song.file_path.startswith(self.album_path):
            return True
        return False

    def __str__(self):
        return f"Album: {self.name}, Artist: {self.album_artist}, Year: {self.release_year}"