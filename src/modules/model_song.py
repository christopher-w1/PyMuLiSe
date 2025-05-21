import os, hashlib, subprocess, re, r128gain
from typing import Optional
from mutagen import easy # type: ignore
from mutagen import File # type: ignore
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from datetime import datetime

def calculate_loudness(file_path: str) -> tuple[Optional[float], Optional[float]]:
    loudness = None
    peak = None
    try:
        result = subprocess.run(["r128gain", "-d", file_path], capture_output=True, text=True, check=True)
        output = result.stdout + result.stderr
        loudness_match = re.search(r"loudness\s*=\s*(-?\d+\.\d+)\s*LUFS", output)
        peak_match = re.search(r"sample peak\s*=\s*(-?\d+\.\d+)\s*dBFS", output)
        if loudness_match:
            loudness = float(loudness_match.group(1))
        if peak_match:
            peak = float(peak_match.group(1))
        print(f"[INFO] Loudness for '{file_path}':\n{loudness} LUFS, Peak: {peak} dBFS")
    except Exception as e:
        print(f"[ERROR] Loudness analysis failed for {file_path}: {e}")
    return loudness, peak

def find_cover_art(file_path: str) -> str:
    directory = os.path.dirname(file_path)
    image_extensions = [".jpg", ".jpeg", ".png", ".webp"]
    preferred_names = ["cover", "folder", "front", "album"]

    for fname in os.listdir(directory):
        name, ext = os.path.splitext(fname)
        if ext.lower() in image_extensions:
            if name.lower() in preferred_names:
                return os.path.join(directory, fname)

    # Fallback: Erstes beliebiges Bild nehmen
    for fname in os.listdir(directory):
        _, ext = os.path.splitext(fname)
        if ext.lower() in image_extensions:
            return os.path.join(directory, fname)

    return ""

class Song:
    def __init__(self, file_path: str = ""):
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
        self.loudness = None
        self.peak = None
        
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
            self.bitrate = metadata.info.bitrate # type: ignore
        elif self.duration and self.duration > 0:
            self.bitrate = int((self.file_size * 8) / self.duration)    

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
        self.loudness, self.peak = calculate_loudness(file_path)
        
    def check_file(self) -> bool:
        if not os.path.exists(self.file_path):
            print(f"[ERROR] File does not exist: {self.file_path}")
            return False
        if not os.access(self.file_path, os.R_OK):
            print(f"[ERROR] File is not readable: {self.file_path}")
            return False
        return True
        
    def add_genres(self, genres: list[str]):
        self.genres.extend(genres)
        self.genres = list(set(self.genres))
        
    def inc_play_count(self):
        self.play_count += 1
        self.last_played = datetime.now().isoformat()
        
    def maximize_play_count(self, play_count: int):
        self.play_count = max(play_count, self.play_count)
        self.last_played = datetime.now().isoformat()
        
    def get_genres(self) -> str:
        return ", ".join(self.genres) if self.genres else "Unknown"
    
    def get_artists(self) -> str:
        artists = [self.album_artist] + self.other_artists
        return ", ".join(artists) if artists else "Unknown"
    
    def get_title(self) -> str:
        return self.title if self.title else "Unknown"

    def __str__(self):
        return f"{self.title} by {self.album_artist} from the album {self.album} ({self.duration} seconds)"