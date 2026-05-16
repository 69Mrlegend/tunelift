import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from utils.converter import ConversionFailed, convert_audio_to_mp3, convert_thumbnail_to_jpg, convert_video_to_ipod_mp4
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
from utils.spotify import SpotifyError, download_cover_image, get_spotify_playlist_info, get_spotify_track_info, search_spotify_track
from utils.itunes import search_itunes_track


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
    """Download a YouTube video by direct URL and convert it to a tagged MP3.

    HARD RULE: This function downloads ONLY the exact video at ``url``.
    No search, no Spotify lookup, no iTunes lookup, no metadata replacement.
    Every piece of metadata (title, artist, album, cover) comes exclusively
    from the YouTube video itself.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    _log.info("Direct URL mode — downloading exact URL: %s", url)
    _log.info("Direct URL mode — Skipping Spotify/iTunes enrichment completely")

    work_dir = Path(download_root) / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        info = download_audio_and_thumbnail(url, work_dir)
        source_audio = find_downloaded_audio(work_dir)
        if source_audio is None:
            raise ConversionError("The audio was downloaded, but the source file could not be found.")

        # All metadata comes from the YouTube video. No external lookups.
        title, artist = get_youtube_track_metadata(info, source_audio.stem)
        _log.info("Direct URL mode — title=%r artist=%r (from YouTube only)", title, artist)

        # Use the thumbnail that yt-dlp downloaded alongside the video.
        # No Spotify/iTunes cover art is fetched — it would be from an
        # unrelated track and would corrupt the metadata.
        cover_path = find_thumbnail(work_dir)

        mp3_path = work_dir / f"{safe_filename(f'{artist} - {title}')}.mp3"
        convert_audio_to_mp3(source_audio, mp3_path, bitrate="320k")
        add_mp3_metadata(mp3_path, title=title, artist=artist, cover_path=cover_path, album="YouTube")

        _log.info("Direct URL mode — complete: %s", mp3_path.name)
        return ConversionResult(
            file_path=mp3_path,
            download_name=f"{safe_filename(f'{artist} - {title}')}.mp3",
            work_dir=work_dir,
        )
    except (ConversionError, DownloadFailed, ConversionFailed) as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(f"Conversion failed: {exc}") from exc




def convert_search_to_mp3(query, download_root):
    """Search YouTube by song name and download the best match as a tagged MP3.

    Unlike convert_youtube_to_mp3() (direct URL, no Spotify), this function
    uses Spotify/iTunes to get structured track info before searching YouTube,
    which produces much better search queries and cleaner metadata tags.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    _log.info("MP3 search mode — query=%r", query)

    work_dir = Path(download_root) / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Spotify/iTunes lookup improves the YouTube search query and provides
        # clean title, artist, album, and cover art for the final MP3 tags.
        music_track = search_spotify_track(query) or search_itunes_track(query)

        if music_track:
            _log.info(
                "MP3 search mode — Spotify enrichment enabled: title=%r artist=%r",
                music_track.get("title"), music_track.get("artist"),
            )
            info = download_audio_from_search(music_track["search_query"], work_dir, track_info=music_track)
        else:
            _log.info("MP3 search mode — Spotify not found, falling back to plain YouTube search")
            info = download_audio_from_search(query, work_dir, track_info={"title": query})

        info = get_primary_download_info(info)
        source_audio = find_downloaded_audio(work_dir)
        if source_audio is None:
            raise ConversionError(f'Could not find audio for "{query}".')

        if music_track:
            title = music_track["title"]
            artist = music_track["artist"]
            album_name = music_track["album_name"]
            cover_path = download_cover_image(music_track["thumbnail"], work_dir)
        else:
            title, artist = get_youtube_track_metadata(info, query)
            album_name = "YouTube"
            cover_path = None

        mp3_path = work_dir / f"{safe_filename(f'{artist} - {title}')}.mp3"
        convert_audio_to_mp3(source_audio, mp3_path, bitrate="320k")
        add_mp3_metadata(mp3_path, title=title, artist=artist, cover_path=cover_path, album=album_name)

        _log.info("MP3 search mode — complete: %s", mp3_path.name)
        return ConversionResult(
            file_path=mp3_path,
            download_name=f"{safe_filename(f'{artist} - {title}')}.mp3",
            work_dir=work_dir,
        )
    except (ConversionError, DownloadFailed, ConversionFailed) as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(f"Search download failed: {exc}") from exc


def convert_youtube_to_mp4(url, download_root, quality, progress_callback=None):
    work_dir = Path(download_root) / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        info = download_video(url, work_dir, quality, progress_callback=progress_callback)
        video_path = find_downloaded_video(work_dir)
        if video_path is None:
            raise ConversionError("The video download finished, but a complete MP4 file could not be found.")

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


def convert_youtube_to_ipod_mp4(url, download_root, progress_callback=None):
    work_dir = Path(download_root) / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        info = download_video(url, work_dir, "480", progress_callback=progress_callback)
        source_video = find_downloaded_video(work_dir)
        if source_video is None:
            raise ConversionError("The video download finished, but a complete MP4 file could not be found.")

        if progress_callback:
            progress_callback({"status": "processing", "percent": 100, "message": "Converting for iPod..."})

        title = info.get("title") or source_video.stem
        ipod_path = work_dir / f"{safe_filename(title)}-ipod.mp4"
        convert_video_to_ipod_mp4(source_video, ipod_path)

        if not ipod_path.exists() or ipod_path.stat().st_size == 0:
            raise ConversionError("FFmpeg finished, but the iPod MP4 output file was not created.")

        if progress_callback:
            progress_callback({"status": "complete", "percent": 100, "message": "Ready for iPod"})

        return ConversionResult(
            file_path=ipod_path,
            download_name=f"{safe_filename(title)}-ipod.mp4",
            work_dir=work_dir,
        )
    except (ConversionError, DownloadFailed, ConversionFailed) as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise ConversionError(f"iPod MP4 conversion failed: {exc}") from exc


def convert_spotify_to_mp3(url, download_root, youtube_url=None):
    work_dir = Path(download_root) / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        track = get_spotify_track_info(url)
        if youtube_url:
            download_audio_and_thumbnail(youtube_url, work_dir)
        else:
            download_audio_from_search(track["search_query"], work_dir, track_info=track)
        source_audio = find_downloaded_audio(work_dir)
        if source_audio is None:
            raise ConversionError("The matching YouTube audio could not be found.")

        title, artist = get_spotify_track_metadata(track)
        mp3_path = work_dir / f"{safe_filename(f'{artist} - {title}')}.mp3"

        convert_audio_to_mp3(source_audio, mp3_path, bitrate="320k")
        cover_path = download_cover_image(track["thumbnail"], work_dir)
        album_name = track.get("album_name", "YouTube")
        add_mp3_metadata(mp3_path, title=title, artist=artist, cover_path=cover_path, album=album_name)

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
                should_continue = progress_callback(playlist["name"], total, index, f"Downloading {index} of {total} songs")
                if should_continue is False:
                    break
            
            try:
                convert_spotify_playlist_track(track, playlist_dir, index)
            except (ConversionError, DownloadFailed, ConversionFailed) as exc:
                if progress_callback:
                    progress_callback(playlist["name"], total, index, f"Failed: {track.get('title', 'Unknown')}", track_status="Failed")
                continue

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
                should_continue = progress_callback(collection_name, total, index, f"Downloading {index} of {total} songs")
                if should_continue is False:
                    break
                    
            try:
                convert_bulk_song(song_name, collection_dir, index)
            except (ConversionError, DownloadFailed, ConversionFailed) as exc:
                if progress_callback:
                    progress_callback(collection_name, total, index, f"Not Found: {song_name}", track_status="Not Found")
                continue

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
    """Download one song from a bulk list and save it as a tagged MP3.

    Bulk mode: Spotify/iTunes enrichment is ENABLED because the input is a
    plain song name (not a URL).  Spotify provides the correct title, artist,
    album, and cover art so the final ZIP has clean, consistent metadata.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    _log.info("Bulk mode — song=%r index=%d — Spotify enrichment enabled", song_name, index)

    track_dir = collection_dir / f"_tmp_bulk_{index}"
    track_dir.mkdir(parents=True, exist_ok=True)

    try:
        music_track = search_spotify_track(song_name) or search_itunes_track(song_name)
        if music_track:
            _log.info(
                "Bulk mode — Spotify match: title=%r artist=%r",
                music_track.get("title"), music_track.get("artist"),
            )
            info = download_audio_from_search(music_track["search_query"], track_dir, track_info=music_track)
        else:
            _log.info("Bulk mode — Spotify not found for %r, using plain YouTube search", song_name)
            info = download_audio_from_search(song_name, track_dir)

        info = get_primary_download_info(info)
        source_audio = find_downloaded_audio(track_dir)
        if source_audio is None:
            raise ConversionError(f"Could not find audio for {song_name}.")

        if music_track:
            title = music_track["title"]
            artist = music_track["artist"]
            album_name = music_track["album_name"]
            cover_path = download_cover_image(music_track["thumbnail"], track_dir)
        else:
            title, artist = get_youtube_track_metadata(info, song_name)
            album_name = "YouTube"
            cover_path = None

        file_name = safe_filename(f"{index:02d} - {artist} - {title}")
        mp3_path = collection_dir / f"{file_name}.mp3"

        convert_audio_to_mp3(source_audio, mp3_path, bitrate="320k")
        add_mp3_metadata(mp3_path, title=title, artist=artist, cover_path=cover_path, album=album_name)
        _log.info("Bulk mode — complete: %s", mp3_path.name)
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
        download_audio_from_search(track["search_query"], track_dir, track_info=track)
        source_audio = find_downloaded_audio(track_dir)
        if source_audio is None:
            raise ConversionError(f"Could not find audio for {track['title']}.")

        title, artist = get_spotify_track_metadata(track)
        file_name = safe_filename(f"{index:02d} - {artist} - {title}")
        mp3_path = playlist_dir / f"{file_name}.mp3"

        convert_audio_to_mp3(source_audio, mp3_path, bitrate="320k")
        cover_path = download_cover_image(track["thumbnail"], track_dir)
        album_name = track.get("album_name", "YouTube")
        add_mp3_metadata(mp3_path, title=title, artist=artist, cover_path=cover_path, album=album_name)
    finally:
        shutil.rmtree(track_dir, ignore_errors=True)


def create_zip_file(source_dir, zip_path):
    source_dir = Path(source_dir)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(source_dir.glob("*.mp3")):
            archive.write(file_path, arcname=str(Path(source_dir.name) / file_path.name))
