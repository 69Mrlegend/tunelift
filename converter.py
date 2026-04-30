import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from utils.converter import ConversionFailed, convert_audio_to_mp3, convert_thumbnail_to_jpg
from utils.downloader import (
    DownloadFailed,
    download_audio_and_thumbnail,
    download_audio_from_search,
    download_video,
    find_downloaded_audio,
    find_downloaded_video,
    find_thumbnail,
)
from utils.metadata import add_mp3_metadata, get_spotify_track_metadata, get_youtube_track_metadata
from utils.spotify import SpotifyError, download_cover_image, get_spotify_playlist_info, get_spotify_track_info


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


class ConversionError(Exception):
    """Raised when a YouTube URL cannot be converted into an MP3."""


@dataclass
class ConversionResult:
    file_path: Path
    download_name: str
    work_dir: Path

    def cleanup(self):
        shutil.rmtree(self.work_dir, ignore_errors=True)


def is_youtube_url(url):
    return validate_youtube_url(url)[0]


def validate_youtube_url(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "Please enter a valid YouTube video URL."

    if parsed.scheme not in {"http", "https"}:
        return False, "The link must start with http:// or https://."

    host = parsed.netloc.lower().split(":")[0]
    if host not in YOUTUBE_HOSTS:
        return False, "Please enter a valid YouTube link."

    if has_youtube_video_id(parsed):
        return True, ""

    return False, "Please enter a YouTube video link, not a channel, playlist, or homepage link."


def has_youtube_video_id(parsed):
    host = parsed.netloc.lower().split(":")[0]
    path_parts = [part for part in parsed.path.split("/") if part]

    if host == "youtu.be":
        return bool(path_parts and path_parts[0])

    query = parse_qs(parsed.query)
    if query.get("v", [""])[0].strip():
        return True

    if len(path_parts) >= 2 and path_parts[0] in {"shorts", "live", "embed"}:
        return bool(path_parts[1])

    return False


def safe_filename(name):
    cleaned = re.sub(r"[^\w\s.-]", "", name, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or "youtube-audio"


def convert_youtube_to_mp3(url, download_root):
    work_dir = Path(download_root) / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        info = download_audio_and_thumbnail(url, work_dir)
        source_audio = find_downloaded_audio(work_dir)
        if source_audio is None:
            raise ConversionError("The audio was downloaded, but the source file could not be found.")

        title, artist = get_youtube_track_metadata(info, source_audio.stem)
        mp3_path = work_dir / f"{safe_filename(title)}.mp3"

        convert_audio_to_mp3(source_audio, mp3_path, bitrate="320k")

        thumbnail_path = find_thumbnail(work_dir)
        cover_path = convert_thumbnail_to_jpg(thumbnail_path, work_dir / "cover.jpg")
        add_mp3_metadata(mp3_path, title=title, artist=artist, cover_path=cover_path)

        return ConversionResult(
            file_path=mp3_path,
            download_name=f"{safe_filename(title)}.mp3",
            work_dir=work_dir,
        )
    except (ConversionError, DownloadFailed, ConversionFailed) as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(f"Conversion failed: {exc}") from exc


def convert_youtube_to_mp4(url, download_root, quality):
    work_dir = Path(download_root) / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        info = download_video(url, work_dir, quality)
        video_path = find_downloaded_video(work_dir)
        if video_path is None:
            raise ConversionError("The video was downloaded, but the MP4 file could not be found.")

        title = info.get("title") or video_path.stem
        download_name = f"{safe_filename(title)}-{quality}p.mp4"

        return ConversionResult(
            file_path=video_path,
            download_name=download_name,
            work_dir=work_dir,
        )
    except (ConversionError, DownloadFailed, ConversionFailed) as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(f"Download failed: {exc}") from exc


def convert_spotify_to_mp3(url, download_root):
    work_dir = Path(download_root) / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        track = get_spotify_track_info(url)
        download_audio_from_search(track["search_query"], work_dir)
        source_audio = find_downloaded_audio(work_dir)
        if source_audio is None:
            raise ConversionError("The matching YouTube audio could not be found.")

        title, artist = get_spotify_track_metadata(track)
        mp3_path = work_dir / f"{safe_filename(f'{artist} - {title}')}.mp3"

        convert_audio_to_mp3(source_audio, mp3_path, bitrate="320k")
        cover_path = download_cover_image(track["thumbnail"], work_dir)
        add_mp3_metadata(mp3_path, title=title, artist=artist, cover_path=cover_path)

        return ConversionResult(
            file_path=mp3_path,
            download_name=f"{safe_filename(f'{artist} - {title}')}.mp3",
            work_dir=work_dir,
        )
    except (ConversionError, DownloadFailed, ConversionFailed, SpotifyError) as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(f"Spotify download failed: {exc}") from exc


def convert_spotify_playlist_to_zip(url, download_root, progress_callback=None, playlist=None):
    work_dir = Path(download_root) / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        playlist = playlist or get_spotify_playlist_info(url)
        playlist_name = safe_filename(playlist["name"])
        playlist_dir = work_dir / playlist_name
        playlist_dir.mkdir(parents=True, exist_ok=True)
        total = len(playlist["tracks"])

        if progress_callback:
            progress_callback(playlist["name"], total, 0, "Preparing playlist")

        for index, track in enumerate(playlist["tracks"], start=1):
            if progress_callback:
                progress_callback(playlist["name"], total, index, f"Downloading {index} of {total} songs")
            convert_spotify_playlist_track(track, playlist_dir, index)

        zip_path = work_dir / f"{playlist_name}.zip"
        create_zip_file(playlist_dir, zip_path)

        return ConversionResult(
            file_path=zip_path,
            download_name=f"{playlist_name}.zip",
            work_dir=work_dir,
        )
    except (ConversionError, DownloadFailed, ConversionFailed, SpotifyError) as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(f"Playlist download failed: {exc}") from exc


def convert_bulk_songs_to_zip(song_names, download_root, progress_callback=None):
    work_dir = Path(download_root) / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        collection_name = "Bulk Songs"
        collection_dir = work_dir / collection_name
        collection_dir.mkdir(parents=True, exist_ok=True)
        total = len(song_names)

        if progress_callback:
            progress_callback(collection_name, total, 0, "Preparing bulk download")

        for index, song_name in enumerate(song_names, start=1):
            if progress_callback:
                progress_callback(collection_name, total, index, f"Downloading {index} of {total} songs")
            convert_bulk_song(song_name, collection_dir, index)

        zip_path = work_dir / f"{collection_name}.zip"
        create_zip_file(collection_dir, zip_path)

        return ConversionResult(
            file_path=zip_path,
            download_name=f"{collection_name}.zip",
            work_dir=work_dir,
        )
    except (ConversionError, DownloadFailed, ConversionFailed) as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(f"Bulk download failed: {exc}") from exc


def convert_bulk_song(song_name, collection_dir, index):
    track_dir = collection_dir / f"_tmp_bulk_{index}"
    track_dir.mkdir(parents=True, exist_ok=True)

    try:
        info = download_audio_from_search(song_name, track_dir)
        info = get_primary_download_info(info)
        source_audio = find_downloaded_audio(track_dir)
        if source_audio is None:
            raise ConversionError(f"Could not find audio for {song_name}.")

        title, artist = get_youtube_track_metadata(info, song_name)
        file_name = safe_filename(f"{index:02d} - {artist} - {title}")
        mp3_path = collection_dir / f"{file_name}.mp3"

        convert_audio_to_mp3(source_audio, mp3_path, bitrate="320k")
        thumbnail_path = find_thumbnail(track_dir)
        cover_path = convert_thumbnail_to_jpg(thumbnail_path, track_dir / "cover.jpg")
        add_mp3_metadata(mp3_path, title=title, artist=artist, cover_path=cover_path)
    finally:
        shutil.rmtree(track_dir, ignore_errors=True)


def get_primary_download_info(info):
    """yt-dlp search results wrap the video info inside an entries list."""
    if isinstance(info, dict) and info.get("entries"):
        for entry in info["entries"]:
            if entry:
                return entry

    return info or {}


def convert_spotify_playlist_track(track, playlist_dir, index):
    track_dir = playlist_dir / f"_tmp_{index}"
    track_dir.mkdir(parents=True, exist_ok=True)

    try:
        download_audio_from_search(track["search_query"], track_dir)
        source_audio = find_downloaded_audio(track_dir)
        if source_audio is None:
            raise ConversionError(f"Could not find audio for {track['title']}.")

        title, artist = get_spotify_track_metadata(track)
        file_name = safe_filename(f"{index:02d} - {artist} - {title}")
        mp3_path = playlist_dir / f"{file_name}.mp3"

        convert_audio_to_mp3(source_audio, mp3_path, bitrate="320k")
        cover_path = download_cover_image(track["thumbnail"], track_dir)
        add_mp3_metadata(mp3_path, title=title, artist=artist, cover_path=cover_path)
    finally:
        shutil.rmtree(track_dir, ignore_errors=True)


def create_zip_file(source_dir, zip_path):
    source_dir = Path(source_dir)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(source_dir.glob("*.mp3")):
            archive.write(file_path, arcname=str(Path(source_dir.name) / file_path.name))
