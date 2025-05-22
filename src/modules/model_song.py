import os, hashlib
from mutagen import File # type: ignore
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from datetime import datetime
from modules.utils import find_cover_art, calculate_loudness

class Song:
    def __init__(self, file_path: str = "", skip_analysis: bool = False):
        """
        Initialize the Song object with metadata from the audio file.
        This includes title, album, artist, duration, release year, genres,

        Args:
            file_path (str, optional): Path to the audio file. Defaults to "".
            skip_analysis (bool, optional): Skip loudness analysis. Defaults to False.

        Raises:
            ValueError: Unsupported file format
            ValueError: Could not read metadata
            ValueError: Could not read audio file
            ValueError: File not found
        """
        self.file_path = file_path
        self.track_number = 0
        self.disc_number = 0
        self.title = ""
        self.album_artist = ""
        self.other_artists = []
        self.album = ""
        self.duration = 0
        self.release_year = 0
        self.genres = []
        self.play_count = 0
        self.last_played = ""
        self.lyrics = ""
        self.explicit = False
        self.bitrate = 0
        self.format = ""
        self.file_size = 0
        self.cover_art = ""
        self.loudness = 0
        self.peak = 0
        self.lastfm_playcount = 0
        self.lastfm_tags = []
        
        if not file_path:
            return
        
        os.path.getsize(file_path)
        audio = File(file_path, easy=True)
        raw = File(file_path)

        ext = os.path.splitext(file_path)[1].lower()
        self.format = ext[1:]  # "mp3", "flac", etc.

        if ext == ".mp3":
            metadata = MP3(file_path)
        elif ext == ".flac":
            metadata = FLAC(file_path)
        elif ext == ".m4a":
            metadata = MP4(file_path)
        elif ext == ".ogg":
            metadata = OggVorbis(file_path)
        else:
            raise ValueError("Unsupported file format")
        
        if not metadata or not metadata.info:
            raise ValueError("Could not read metadata")
        
        if hasattr(metadata.info, 'bitrate') and metadata.info.bitrate: # type: ignore
            self.bitrate = int(metadata.info.bitrate) // 1024 # type: ignore
        elif self.duration and self.duration > 0:
            self.bitrate = int((self.file_size * 8) / self.duration) // 1024  

        if raw and hasattr(raw, 'info') and hasattr(metadata.info, 'length'):
            self.duration = int(raw.info.length)

        if not audio:
            raise ValueError("Could not read audio file")
        tags = audio.tags

        self.title = tags.get("title", [""])[0]
        self.album = tags.get("album", [""])[0]
        self.album_artist = tags.get("albumartist", tags.get("artist", [""]))[0]
        self.other_artists = tags.get("artist", [])[1:] if len(tags.get("artist", [])) > 1 else []
        self.genres = tags.get("genre", [])
        self.release_year = int(tags.get("date", ["0"])[0][:4]) if tags.get("date") else 0
        self.lyrics = tags.get("lyrics", [""])[0] if "lyrics" in tags else ""
        track_info = tags.get("tracknumber", ["0"])[0]
        self.track_number = int(track_info.split("/")[0]) if track_info else 0
        disc_info = tags.get("discnumber", ["0"])[0]
        self.disc_number = int(disc_info.split("/")[0]) if disc_info else 0

        # Recognize explicit content
        if "explicit" in tags:
            self.explicit = tags["explicit"][0].lower() in ["1", "true", "yes"]
        elif "lyrics" in tags and "explicit" in tags["lyrics"][0].lower():
            self.explicit = True

        # Dummy values for play count and last played
        self.play_count = 0
        self.last_played = datetime.now().isoformat()

        # Find cover art
        self.cover_art = find_cover_art(file_path)
        
        # Calculate loudness and peak
        if not skip_analysis:
            self.update_loudness()
            
    def update_loudness(self):
        self.loudness, self.peak = calculate_loudness(self.file_path)
        
    def check_file(self) -> bool:
        """
        Check if the file exists and is readable.

        Returns:
            bool: True if the file exists and is readable, False otherwise.
        """
        if not os.path.exists(self.file_path):
            print(f"[ERROR] File does not exist: {self.file_path}")
            return False
        if not os.access(self.file_path, os.R_OK):
            print(f"[ERROR] File is not readable: {self.file_path}")
            return False
        return True
    
    def file_changed(self) -> bool:
        """
        Check if the file has changed since it was last analyzed, based on the file size.

        Returns:
            bool: True if the file size has changed, False otherwise.
        """
        if not self.check_file():
            return False
        current_size = os.path.getsize(self.file_path)
        if current_size != self.file_size:
            print(f"[INFO] File size changed for {self.file_path}: {self.file_size} -> {current_size}")
            self.file_size = current_size
            return True
        return False
        
    def add_genres(self, genres: list[str]):
        """
        Add genres to the song's metadata. This method will add the genres to the existing list of genres and remove duplicates.
        It will also ensure that the genres are in lowercase and stripped of whitespace.

        Args:
            genres (list[str]): List of genres to add to the song's metadata.
        """
        self.genres.extend(genres)
        self.genres = list(set(self.genres))
        
    def inc_play_count(self):
        """
        Increment the play count of the song and update the last played timestamp.
        """
        self.play_count += 1
        self.last_played = datetime.now().isoformat()
        
    def maximize_play_count(self, play_count: int):
        """
        Set the play count to the maximum of the current play count and the provided play count.

        Args:
            play_count (int): The play count to maximize to.
        """
        self.play_count = max(play_count, self.play_count)
        self.last_played = datetime.now().isoformat()
        
    def get_genres(self) -> str:
        """
        Get the genres of the song as a comma-separated string.
        If no genres are available, return "Unknown".

        Returns:
            str: Comma-separated string of genres or "Unknown" if no genres are available.
        """
        return ", ".join(self.genres) if self.genres else "Unknown"
    
    def get_artists(self) -> str:
        """
        Get the artists of the song as a comma-separated string.
        This includes the album artist and any other artists.

        Returns:
            str: Comma-separated string of artists or "Unknown" if no artists are available.
        """
        artists = [self.album_artist] + self.other_artists
        return ", ".join(artists) if artists else "Unknown"
    
    def get_title(self) -> str:
        """
        Get the title of the song.
        
        Returns:
            str: Title of the song or "Unknown" if no title is available.
        """
        return self.title if self.title else "Unknown"
    
    def to_dict(self) -> dict:
        """
        Convert the song metadata to a dictionary format.

        Returns:
            dict: Dictionary containing the song metadata.
        """
        return {
            "file_path": self.file_path,
            "track_number": self.track_number,
            "disc_number": self.disc_number,
            "title": self.title,
            "album_artist": self.album_artist,
            "other_artists": self.other_artists,
            "album": self.album,
            "duration": self.duration,
            "release_year": self.release_year,
            "genres": self.genres,
            "play_count": self.play_count,
            "last_played": self.last_played,
            "lyrics": self.lyrics,
            "explicit": self.explicit,
            "bitrate": self.bitrate,
            "format": self.format,
            "file_size": self.file_size,
            "cover_art": self.cover_art,
            "loudness": self.loudness,
            "peak": self.peak,
            "lastfm_playcount": self.lastfm_playcount,
            "lastfm_tags": self.lastfm_tags,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Song":
        """
        Create a Song object from a dictionary of metadata.
        This method is useful for loading song metadata from a database or other storage format.

        Args:
            data (dict): Dictionary containing the song metadata.

        Returns:
            Song: A new Song object with the metadata from the dictionary.
            
        Raises:
            ValueError: If the dictionary does not contain the required metadata.
        """
        song = cls()
        song.file_path = data.get("file_path", "")
        song.track_number = data.get("track_number", 0)
        song.disc_number = data.get("disc_number", 0)
        song.title = data.get("title", "")
        song.album_artist = data.get("album_artist", "")
        song.other_artists = data.get("other_artists", [])
        song.album = data.get("album", "")
        song.duration = data.get("duration", 0)
        song.release_year = data.get("release_year", 0)
        song.genres = data.get("genres", [])
        song.play_count = data.get("play_count", 0)
        song.last_played = data.get("last_played", "")
        song.lyrics = data.get("lyrics", "")
        song.explicit = data.get("explicit", False)
        song.bitrate = data.get("bitrate", 0)
        song.format = data.get("format", "")
        song.file_size = data.get("file_size", 0)
        song.cover_art = data.get("cover_art", "")
        song.loudness = data.get("loudness", 0)
        song.peak = data.get("peak", 0)
        song.lastfm_playcount = data.get("lastfm_playcount", 0)
        song.lastfm_tags = data.get("lastfm_tags", [])
        return song

    def pretty_print(self):
        """
        Print the song information in a readable format.
        This method will print the song's title, album, artist, duration, release year, genres, play count, last played date,
        """
        print(f"File Path: {self.file_path}")
        print(f"Title: {self.title}")
        print(f"Album: {self.album}")
        print(f"Track Number: {self.track_number}")
        print(f"Artist: {self.get_artists()}")
        print(f"Duration: {self.duration} seconds")
        print(f"Release Year: {self.release_year}")
        print(f"Genres: {', '.join(self.genres)}")
        print(f"Play Count: {self.play_count}")
        print(f"Last Played: {self.last_played}")
        print(f"Loudness: {self.loudness} LUFS")
        print(f"Peak: {self.peak} dBFS")
        print(f"Bitrate: {self.bitrate} kbps")
        print(f"Format: {self.format}")
        
    def get_hash(self) -> str:
        """
        Generate a hash for the song based on its metadata.
        This hash is used to uniquely identify the song and can be used for comparison purposes and is
        subject to change if the metadata changes.

        Returns:
            str: The hash of the song.
        """
        return hashlib.sha256(
            (f"{self.get_artists()}|{self.album}|{self.disc_number}.{self.track_number}|{self.title}").encode()
        ).hexdigest()
        
    def __str__(self):
        return f"{self.title} by {self.album_artist} from the album {self.album} ({self.duration} seconds)"