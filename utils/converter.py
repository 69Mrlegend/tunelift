import subprocess
import shutil
from pathlib import Path


class ConversionFailed(Exception):
    """Raised when FFmpeg cannot convert a file."""


def get_ffmpeg_path():
    """Find FFmpeg from PATH or the project-local tools folder."""
    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg

    project_root = Path(__file__).resolve().parents[1]
    local_ffmpeg = project_root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if local_ffmpeg.exists():
        return str(local_ffmpeg)

    return None


def convert_audio_to_mp3(input_path, output_path, bitrate="320k"):
    """Convert an audio file to MP3 using FFmpeg."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    command = [
        get_required_ffmpeg_path(),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(output_path),
    ]

    run_ffmpeg(command)
    return output_path


def convert_thumbnail_to_jpg(thumbnail_path, output_path):
    """Convert a thumbnail to JPG so MP3 players can show it as album art."""
    if thumbnail_path is None:
        return None

    thumbnail_path = Path(thumbnail_path)
    output_path = Path(output_path)

    if thumbnail_path.suffix.lower() in {".jpg", ".jpeg"}:
        return thumbnail_path

    command = [
        get_required_ffmpeg_path(),
        "-y",
        "-i",
        str(thumbnail_path),
        "-frames:v",
        "1",
        str(output_path),
    ]

    run_ffmpeg(command)
    return output_path if output_path.exists() else None


def run_ffmpeg(command):
    completed = subprocess.run(command, capture_output=True, text=True)

    if completed.returncode != 0:
        message = completed.stderr.strip() or "FFmpeg could not convert the file."
        raise ConversionFailed(message)


def get_required_ffmpeg_path():
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path is None:
        raise ConversionFailed("FFmpeg is required but was not found.")
    return ffmpeg_path
