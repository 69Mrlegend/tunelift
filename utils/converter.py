import subprocess
import shutil
import logging
from pathlib import Path


class ConversionFailed(Exception):
    """Raised when FFmpeg cannot convert a file."""


logger = logging.getLogger(__name__)


def get_ffmpeg_path():
    """Find FFmpeg from Windows install, project-local tools, or PATH."""
    candidates = [
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(__file__).resolve().parents[1] / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]

    for candidate in candidates:
        if candidate.exists():
            resolved = str(candidate)
            logger.info("Using FFmpeg from: %s", str(candidate.parent))
            return resolved

    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        path = Path(path_ffmpeg)
        logger.info("Using FFmpeg from: %s", str(path.parent))
        return str(path)

    return None


def get_ffmpeg_location():
    """Return the directory yt-dlp should use for ffmpeg_location."""
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path is None:
        return None

    return str(Path(ffmpeg_path).parent)


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


def convert_video_to_ipod_mp4(input_path, output_path):
    """Convert a video to an iPod Nano 3rd gen friendly MP4."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    command = [
        get_required_ffmpeg_path(),
        "-y",
        "-i",
        str(input_path),
        "-vf",
        "scale=480:320:force_original_aspect_ratio=decrease,pad=480:320:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
        "-c:v",
        "libx264",
        "-profile:v",
        "baseline",
        "-level",
        "3.0",
        "-preset",
        "medium",
        "-crf",
        "24",
        "-maxrate",
        "900k",
        "-bufsize",
        "1800k",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    run_ffmpeg(command)
    return output_path


def run_ffmpeg(command):
    completed = subprocess.run(command, capture_output=True, text=True)

    if completed.returncode != 0:
        message = completed.stderr.strip() or "FFmpeg could not convert the file."
        raise ConversionFailed(message)


def get_required_ffmpeg_path():
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path is None:
        raise ConversionFailed(
            "FFmpeg is required but was not found. Install it at C:\\ffmpeg\\bin\\ffmpeg.exe, "
            "place it in tools/ffmpeg/bin, or add ffmpeg.exe to PATH."
        )
    return ffmpeg_path
