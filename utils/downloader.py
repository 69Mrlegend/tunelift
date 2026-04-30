from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError


class DownloadFailed(Exception):
    """Raised when yt-dlp cannot download the requested video."""


def download_audio_and_thumbnail(url, output_folder):
    """Download the best audio stream and thumbnail for one YouTube video."""
    output_folder = Path(output_folder)
    output_template = str(output_folder / "source.%(ext)s")

    options = {
        "format": "bestaudio",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": True,
    }

    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=True)
    except DownloadError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc
    except ExtractorError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc


def download_audio_from_search(search_query, output_folder):
    """Search YouTube and download the best audio from the first result."""
    output_folder = Path(output_folder)
    output_template = str(output_folder / "source.%(ext)s")

    options = {
        "format": "bestaudio",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": True,
    }

    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(f"ytsearch1:{search_query}", download=True)
    except DownloadError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc
    except ExtractorError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc


def download_video(url, output_folder, quality):
    """Download a clean MP4 video at or below the selected quality."""
    output_folder = Path(output_folder)
    output_template = str(output_folder / "source.%(ext)s")
    max_height = int(quality)

    options = {
        "format": (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={max_height}][ext=mp4]/"
            f"best[height<={max_height}]"
        ),
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=True)
    except DownloadError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc
    except ExtractorError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc


def get_video_preview(url):
    """Fetch video title, uploader, and thumbnail without downloading media."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc
    except ExtractorError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc

    return {
        "title": info.get("title") or "Untitled video",
        "artist": info.get("artist") or info.get("uploader") or info.get("channel") or "Unknown uploader",
        "thumbnail": get_best_thumbnail(info),
    }


def get_best_thumbnail(info):
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        best = max(thumbnails, key=lambda item: item.get("width") or 0)
        if best.get("url"):
            return best["url"]

    return info.get("thumbnail") or ""


def get_download_error_message(error):
    """Turn yt-dlp errors into short messages that make sense in the UI."""
    text = str(error).lower()

    if "private" in text:
        return "This video is private, so it cannot be downloaded."

    if "unavailable" in text or "removed" in text:
        return "This video is unavailable or has been removed."

    if "age" in text or "sign in" in text or "login" in text:
        return "This video requires sign-in or age verification, so it cannot be downloaded here."

    if "copyright" in text or "blocked" in text:
        return "This video is blocked and cannot be downloaded."

    if "unsupported url" in text:
        return "That YouTube link is not supported. Please paste a direct video URL."

    return "The video could not be downloaded. Check the link and try again."


def find_downloaded_audio(output_folder):
    """Return the audio file downloaded by yt-dlp."""
    output_folder = Path(output_folder)
    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}

    files = [
        path for path in output_folder.iterdir()
        if path.is_file() and path.suffix.lower() not in image_extensions
    ]

    if not files:
        return None

    return max(files, key=lambda path: path.stat().st_mtime)


def find_thumbnail(output_folder):
    """Return the thumbnail file downloaded by yt-dlp, if one exists."""
    output_folder = Path(output_folder)

    for extension in (".jpg", ".jpeg", ".png", ".webp"):
        thumbnail = output_folder / f"source{extension}"
        if thumbnail.exists():
            return thumbnail

    return None


def find_downloaded_video(output_folder):
    """Return the MP4 file downloaded by yt-dlp."""
    output_folder = Path(output_folder)
    videos = [path for path in output_folder.glob("*.mp4") if path.is_file()]

    if not videos:
        return None

    return max(videos, key=lambda path: path.stat().st_size)
