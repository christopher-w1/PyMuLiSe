import subprocess
import os
import hashlib

class Transcoding:
    def __init__(self, song_hash: str, src_file: str, target_format: str, target_bitrate: int | None, cache_dir: str):
        self.song_hash = song_hash
        self.src_file = src_file
        self.target_format = target_format.lower()
        self.target_bitrate = target_bitrate
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.output_file = self._build_output_path()

    def _build_output_path(self) -> str:
        bitrate_str = f"{self.target_bitrate}k" if self.target_bitrate else "default"
        name = f"{self.song_hash}_{bitrate_str}.{self.target_format}"
        return os.path.join(self.cache_dir, name)

    def run(self) -> str:
        if os.path.exists(self.output_file):
            return self.output_file

        command = [
            "ffmpeg",
            "-i", self.src_file,
            "-y"
        ]
        if self.target_bitrate:
            command += ["-b:a", f"{self.target_bitrate}k"]

        command.append(self.output_file)

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(f"Transcoding failed: {result.stderr.decode()}")

        return self.output_file
