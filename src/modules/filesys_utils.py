import os, subprocess, re
from typing import Optional


def find_song_paths(music_dir: str) -> list:
    """
    Find all song paths in the music directory recursively.
    :param music_dir: Path to the music directory.
    :return: List of song paths.
    """
    song_paths = []
    def find_rec(music_dir: str):
        #print(f"Checking {music_dir}")
        if not os.path.exists(music_dir):
            return
        # Check if path is a music file
        if os.path.isfile(music_dir):
            if music_dir.endswith(('.mp3', '.flac', '.m4a', '.ogg')):
                song_paths.append(music_dir)
            return
        # Check if path is a directory
        if os.path.isdir(music_dir):
            for item in os.listdir(music_dir):
                item_path = os.path.join(music_dir, item)
                find_rec(item_path)
            return
        return
    find_rec(music_dir)
    return song_paths


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
    if not os.path.exists(file_path):
        return ""
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