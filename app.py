import os
import shutil
import threading
import uuid
import logging
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
from flask import Flask, after_this_request, flash, jsonify, render_template, request, send_file, session, redirect, url_for

from converter import (
    ConversionError,
    convert_bulk_songs_to_zip,
    convert_search_to_mp3,
    convert_spotify_playlist_to_zip,
    convert_spotify_to_mp3,
    convert_youtube_to_ipod_mp4,
    convert_youtube_to_mp3,
    convert_youtube_to_mp4,
    validate_youtube_url,
)
from utils.bulk import BulkInputError, bulk_tracks_response, parse_song_names
from utils.converter import get_ffmpeg_path
from utils.downloader import DownloadFailed, get_search_preview, get_video_preview
from utils.spotify import (
    SpotifyError,
    get_spotify_playlist_info,
    get_spotify_track_info,
    get_spotify_id,
    get_spotify_url_type,
    is_spotify_url,
    normalize_spotify_url,
    get_spotify_auth_url,
    exchange_spotify_code,
    get_user_playlists,
)


BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)
VIDEO_QUALITIES = {"360", "720", "1080"}
PLAYLIST_JOBS = {}
BULK_JOBS = {}
VIDEO_JOBS = {}
IPOD_JOBS = {}
FFMPEG_MISSING_MESSAGE = (
    "FFmpeg is required. Install it at C:\\ffmpeg\\bin\\ffmpeg.exe, "
    "place it in tools/ffmpeg/bin, or add ffmpeg.exe to PATH."
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

# Ensure INFO logs show up in the terminal for debugging.
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)
logging.getLogger("utils.spotify").setLevel(logging.INFO)


def playlist_json(payload, status=200, context="spotify-playlist"):
    """Return playlist API JSON and log the response contract."""
    app.logger.info(
        "%s response_status=%s response_keys=%s response_summary=%r",
        context,
        status,
        sorted(payload.keys()),
        summarize_for_log(payload),
    )
    return jsonify(payload), status


def api_json(payload, status=200, context="api"):
    """Return JSON and log the response keys for async job routes."""
    app.logger.info(
        "%s response_status=%s response_keys=%s response_summary=%r",
        context,
        status,
        sorted(payload.keys()),
        summarize_for_log(payload),
    )
    return jsonify(payload), status


def summarize_for_log(value, limit=1200):
    text = repr(value)
    if len(text) > limit:
        return text[:limit] + "...<truncated>"
    return text


@app.route("/spotify/login")
def spotify_login():
    redirect_uri = SPOTIFY_REDIRECT_URI or "http://127.0.0.1:5000/callback"
    try:
        url = get_spotify_auth_url(redirect_uri)
        return redirect(url)
    except SpotifyError as exc:
        flash(str(exc))
        return redirect(url_for("index"))


@app.route("/callback")
def spotify_callback():
    code = request.args.get("code")
    if not code:
        flash("Spotify login failed or was canceled.")
        return redirect(url_for("index"))
        
    redirect_uri = SPOTIFY_REDIRECT_URI or "http://127.0.0.1:5000/callback"
    try:
        token = exchange_spotify_code(code, redirect_uri)
        session["spotify_token"] = token
    except SpotifyError as exc:
        flash(str(exc))
        
    return redirect(url_for("index"))


@app.route("/spotify/logout")
def spotify_logout():
    session.pop("spotify_token", None)
    return redirect(url_for("index"))


@app.get("/api/spotify/playlists")
def api_spotify_playlists():
    token = session.get("spotify_token")
    if not token:
        return jsonify({"ok": False, "message": "Not logged in"}), 401
        
    try:
        playlists = get_user_playlists(token)
        return jsonify({"ok": True, "playlists": playlists})
    except SpotifyError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400


@app.route("/", methods=["GET", "POST"])
def index():
    logged_in_spotify = "spotify_token" in session
    if request.method == "GET":
        return render_template("index.html", logged_in_spotify=logged_in_spotify)

    url = request.form.get("url", "").strip()
    download_type = request.form.get("download_type", "mp3")
    quality = request.form.get("quality", "720")

    if not url:
        flash("Paste a link first.")
        return render_template("index.html", url=url, logged_in_spotify=logged_in_spotify), 400

    if download_type == "spotify":
        if not is_spotify_url(url):
            flash("Please paste a valid Spotify track or playlist link.")
            return render_template("index.html", url=url, logged_in_spotify=logged_in_spotify), 400
        if get_spotify_url_type(url) == "playlist":
            flash("Playlist downloads run in the progress panel. Please use the Spotify playlist flow.")
            return render_template("index.html", url=url, logged_in_spotify=logged_in_spotify), 400
    elif download_type == "mp3":
        is_valid_url, _ = validate_youtube_url(url)
        # Plain song names are allowed for MP3 mode — the search path handles them.
        # mp4/ipod modes still require a direct YouTube URL.
    else:
        is_valid_url, error_message = validate_youtube_url(url)
        if not is_valid_url:
            flash(error_message)
            return render_template("index.html", url=url, logged_in_spotify=logged_in_spotify), 400

    if get_ffmpeg_path() is None:
        flash(FFMPEG_MISSING_MESSAGE)
        return render_template("index.html", url=url, logged_in_spotify=logged_in_spotify), 500

    try:
        if download_type == "spotify":
            confirmed_youtube_url = request.form.get("confirmed_youtube_url", "").strip()
            if confirmed_youtube_url:
                is_valid_url, error_message = validate_youtube_url(confirmed_youtube_url)
                if not is_valid_url:
                    flash(error_message)
                    return render_template("index.html", url=url, logged_in_spotify=logged_in_spotify), 400
            result = convert_spotify_to_mp3(url, DOWNLOAD_DIR, youtube_url=confirmed_youtube_url or None)
            mimetype = "audio/mpeg"
        elif download_type == "mp4":
            if quality not in VIDEO_QUALITIES:
                flash("Please choose a valid video quality.")
                return render_template("index.html", url=url, logged_in_spotify=logged_in_spotify), 400
            result = convert_youtube_to_mp4(url, DOWNLOAD_DIR, quality)
            mimetype = "video/mp4"
        elif download_type == "ipod":
            result = convert_youtube_to_ipod_mp4(url, DOWNLOAD_DIR)
            mimetype = "video/mp4"
        else:
            # MP3 mode: direct YouTube URL or song name search.
            # These are mutually exclusive paths — a direct URL NEVER triggers
            # the search logic, and a plain text query NEVER triggers direct download.
            is_yt_url, _ = validate_youtube_url(url)
            if is_yt_url:
                app.logger.info("mp3.download mode=direct_url url=%r", url)
                result = convert_youtube_to_mp3(url, DOWNLOAD_DIR)
            else:
                app.logger.info("mp3.download mode=search query=%r", url)
                result = convert_search_to_mp3(url, DOWNLOAD_DIR)
            mimetype = "audio/mpeg"

    except ConversionError as exc:
        flash(str(exc))
        return render_template("index.html", url=url, logged_in_spotify=logged_in_spotify), 400

    @after_this_request
    def cleanup(response):
        response.call_on_close(result.cleanup)
        return response

    return send_file(
        result.file_path,
        as_attachment=True,
        download_name=result.download_name,
        mimetype=mimetype,
    )


@app.get("/preview")
def preview():
    url = request.args.get("url", "").strip()
    download_type = request.args.get("download_type", "mp3")

    if download_type == "spotify":
        try:
            if get_spotify_url_type(url) == "playlist":
                playlist = get_spotify_playlist_info(url)
                return jsonify(
                    {
                        "ok": True,
                        "video": {
                            "title": playlist["name"],
                            "artist": f"{playlist['total']} songs",
                            "thumbnail": playlist["thumbnail"],
                            "kind": "playlist",
                            "total": playlist["total"],
                        },
                    }
                )

            track = get_spotify_track_info(url)
            excluded = request.args.getlist("exclude")
            match = get_search_preview(track["search_query"], track_info=track, exclude_urls=excluded)
            return jsonify({"ok": True, "video": match, "source_track": track})
        except SpotifyError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        except DownloadFailed as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    is_valid_url, error_message = validate_youtube_url(url)
    if not is_valid_url:
        # Not a YouTube URL — treat as a search query for plain MP3 mode
        if download_type in ("mp3",):
            try:
                match = get_search_preview(url)
                return jsonify({"ok": True, "video": match})
            except DownloadFailed as exc:
                return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": False, "message": error_message}), 400

    try:
        video = get_video_preview(url)
        # Direct YouTube URLs are always an exact match
        video["match_quality"] = "exact"
        video["is_audiobook_hint"] = False
        return jsonify({"ok": True, "video": video})
    except DownloadFailed as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400


@app.post("/video/start")
def start_video_download():
    try:
        url = request.form.get("url", "").strip()
        quality = request.form.get("quality", "720")

        is_valid_url, error_message = validate_youtube_url(url)
        if not is_valid_url:
            return api_json({"ok": False, "message": error_message}, 400, "video.start")

        if quality not in VIDEO_QUALITIES:
            return api_json({"ok": False, "message": "Please choose a valid video quality."}, 400, "video.start")

        if get_ffmpeg_path() is None:
            return api_json(
                {"ok": False, "message": FFMPEG_MISSING_MESSAGE},
                500,
                "video.start",
            )

        job_id = uuid.uuid4().hex
        VIDEO_JOBS[job_id] = build_video_job(url, quality)

        thread = threading.Thread(target=run_video_job, args=(job_id,), daemon=True)
        thread.start()

        return api_json({"ok": True, "job_id": job_id}, context="video.start")
    except Exception as exc:
        app.logger.exception("video.start unexpected_exception")
        return api_json({"ok": False, "message": f"Unexpected video start error: {exc}"}, 500, "video.start")


@app.get("/video/progress/<job_id>")
def video_progress(job_id):
    try:
        job = VIDEO_JOBS.get(job_id)
        if not job:
            return api_json({"ok": False, "message": "Video download job not found."}, 404, "video.progress")

        return api_json(
            {
                "ok": True,
                "status": job["status"],
                "video_title": job["video_title"],
                "quality": job["quality"],
                "percent": job["percent"],
                "speed": job["speed"],
                "eta": job["eta"],
                "status_label": job["status_label"],
                "message": job["message"],
                "download_url": job["download_url"],
                "error": job["error"],
                "downloaded": job["downloaded"],
                "total_size": job["total_size"],
            },
            context="video.progress",
        )
    except Exception as exc:
        app.logger.exception("video.progress unexpected_exception job_id=%r", job_id)
        return api_json({"ok": False, "message": f"Unexpected video progress error: {exc}"}, 500, "video.progress")


@app.get("/video/download/<job_id>")
def download_video_file(job_id):
    job = VIDEO_JOBS.get(job_id)
    if not job or job.get("status") != "complete" or job.get("result") is None:
        return jsonify({"ok": False, "message": "MP4 video is not ready yet."}), 404

    result = job["result"]

    @after_this_request
    def cleanup(response):
        response.call_on_close(lambda: cleanup_video_job(job_id))
        return response

    return send_file(
        result.file_path,
        as_attachment=True,
        download_name=result.download_name,
        mimetype="video/mp4",
    )


@app.post("/ipod/start")
def start_ipod_download():
    try:
        url = request.form.get("url", "").strip()

        is_valid_url, error_message = validate_youtube_url(url)
        if not is_valid_url:
            return api_json({"ok": False, "message": error_message}, 400, "ipod.start")

        if get_ffmpeg_path() is None:
            return api_json(
                {"ok": False, "message": FFMPEG_MISSING_MESSAGE},
                500,
                "ipod.start",
            )

        job_id = uuid.uuid4().hex
        IPOD_JOBS[job_id] = build_video_job(url, "iPod 480x320")

        thread = threading.Thread(target=run_ipod_job, args=(job_id,), daemon=True)
        thread.start()

        return api_json({"ok": True, "job_id": job_id}, context="ipod.start")
    except Exception as exc:
        app.logger.exception("ipod.start unexpected_exception")
        return api_json({"ok": False, "message": f"Unexpected iPod MP4 start error: {exc}"}, 500, "ipod.start")


@app.get("/ipod/progress/<job_id>")
def ipod_progress(job_id):
    try:
        job = IPOD_JOBS.get(job_id)
        if not job:
            return api_json({"ok": False, "message": "iPod MP4 job not found."}, 404, "ipod.progress")

        return api_json(
            {
                "ok": True,
                "status": job["status"],
                "video_title": job["video_title"],
                "quality": job["quality"],
                "percent": job["percent"],
                "speed": job["speed"],
                "eta": job["eta"],
                "status_label": job["status_label"],
                "message": job["message"],
                "download_url": job["download_url"],
                "error": job["error"],
                "downloaded": job["downloaded"],
                "total_size": job["total_size"],
            },
            context="ipod.progress",
        )
    except Exception as exc:
        app.logger.exception("ipod.progress unexpected_exception job_id=%r", job_id)
        return api_json({"ok": False, "message": f"Unexpected iPod MP4 progress error: {exc}"}, 500, "ipod.progress")


@app.get("/ipod/download/<job_id>")
def download_ipod_file(job_id):
    job = IPOD_JOBS.get(job_id)
    if not job or job.get("status") != "complete" or job.get("result") is None:
        return jsonify({"ok": False, "message": "iPod MP4 is not ready yet."}), 404

    result = job["result"]

    @after_this_request
    def cleanup(response):
        response.call_on_close(lambda: cleanup_ipod_job(job_id))
        return response

    return send_file(
        result.file_path,
        as_attachment=True,
        download_name=result.download_name,
        mimetype="video/mp4",
    )


def build_video_job(url, quality):
    return {
        "status": "queued",
        "url": url,
        "quality": quality,
        "video_title": "YouTube Video",
        "percent": 0,
        "speed": "",
        "eta": "",
        "status_label": "Queued",
        "message": "Video download queued",
        "download_url": "",
        "error": "",
        "downloaded": "",
        "total_size": "",
        "result": None,
    }


def run_video_job(job_id):
    def update_progress(progress):
        job = VIDEO_JOBS.get(job_id)
        if not job:
            return

        info = progress.get("info_dict") or {}
        if info.get("title"):
            job["video_title"] = info["title"]

        percent = progress.get("percent")
        if percent is not None:
            job["percent"] = round(percent, 1)

        if progress.get("speed") is not None:
            job["speed"] = format_speed(progress.get("speed"))

        if progress.get("eta") is not None:
            job["eta"] = format_eta(progress.get("eta"))

        if progress.get("downloaded_bytes") is not None:
            job["downloaded"] = format_bytes(progress.get("downloaded_bytes"))

        if progress.get("total_bytes") is not None:
            job["total_size"] = format_bytes(progress.get("total_bytes"))

        status = progress.get("status") or "downloading"
        if status == "fallback":
            job["status"] = "running"
            job["status_label"] = "Trying fallback format"
        elif status == "processing":
            job["status"] = "processing"
            job["status_label"] = "Processing audio/video merge"
        elif status == "starting":
            job["status"] = "running"
            job["status_label"] = "Selecting stable format"
        elif status != "error":
            job["status"] = "running"
            job["status_label"] = "Downloading video"

        job["message"] = progress.get("message") or job["status_label"]

    try:
        job = VIDEO_JOBS[job_id]
        job["status"] = "running"
        job["status_label"] = "Starting download"
        job["message"] = "Starting MP4 download"

        result = convert_youtube_to_mp4(job["url"], DOWNLOAD_DIR, job["quality"], progress_callback=update_progress)
        job = VIDEO_JOBS[job_id]
        job["status"] = "complete"
        job["percent"] = 100
        job["speed"] = ""
        job["eta"] = "0 seconds"
        job["status_label"] = "Ready to download"
        job["message"] = "Download complete"
        job["download_url"] = f"/video/download/{job_id}"
        job["result"] = result
    except ConversionError as exc:
        app.logger.exception("video.job conversion_error job_id=%r", job_id)
        job = VIDEO_JOBS[job_id]
        job["status"] = "error"
        job["error"] = str(exc)
        job["message"] = str(exc)
        job["status_label"] = "Failed"
    except Exception as exc:
        app.logger.exception("video.job unexpected_exception job_id=%r", job_id)
        job = VIDEO_JOBS[job_id]
        job["status"] = "error"
        job["error"] = f"Video download failed: {exc}"
        job["message"] = job["error"]
        job["status_label"] = "Failed"


def run_ipod_job(job_id):
    def update_progress(progress):
        job = IPOD_JOBS.get(job_id)
        if not job:
            return

        info = progress.get("info_dict") or {}
        if info.get("title"):
            job["video_title"] = info["title"]

        percent = progress.get("percent")
        if percent is not None:
            job["percent"] = round(percent, 1)

        if progress.get("speed") is not None:
            job["speed"] = format_speed(progress.get("speed"))

        if progress.get("eta") is not None:
            job["eta"] = format_eta(progress.get("eta"))

        if progress.get("downloaded_bytes") is not None:
            job["downloaded"] = format_bytes(progress.get("downloaded_bytes"))

        if progress.get("total_bytes") is not None:
            job["total_size"] = format_bytes(progress.get("total_bytes"))

        status = progress.get("status") or "downloading"
        if status == "processing":
            job["status"] = "processing"
            job["status_label"] = progress.get("message") or "Converting for iPod..."
        elif status == "complete":
            job["status"] = "processing"
            job["status_label"] = "Ready for iPod"
        elif status == "starting":
            job["status"] = "running"
            job["status_label"] = "Downloading video..."
        elif status == "fallback":
            job["status"] = "running"
            job["status_label"] = "Trying fallback format"
        elif status != "error":
            job["status"] = "running"
            job["status_label"] = "Downloading video..."

        job["message"] = progress.get("message") or job["status_label"]

    try:
        job = IPOD_JOBS[job_id]
        job["status"] = "running"
        job["status_label"] = "Downloading video..."
        job["message"] = "Downloading video..."

        result = convert_youtube_to_ipod_mp4(job["url"], DOWNLOAD_DIR, progress_callback=update_progress)
        job = IPOD_JOBS[job_id]
        job["status"] = "complete"
        job["percent"] = 100
        job["speed"] = ""
        job["eta"] = "0 seconds"
        job["status_label"] = "Ready for iPod"
        job["message"] = "Ready for iPod"
        job["download_url"] = f"/ipod/download/{job_id}"
        job["result"] = result
    except ConversionError as exc:
        app.logger.exception("ipod.job conversion_error job_id=%r", job_id)
        job = IPOD_JOBS[job_id]
        job["status"] = "error"
        job["error"] = str(exc)
        job["message"] = str(exc)
        job["status_label"] = "Failed"
    except Exception as exc:
        app.logger.exception("ipod.job unexpected_exception job_id=%r", job_id)
        job = IPOD_JOBS[job_id]
        job["status"] = "error"
        job["error"] = f"iPod MP4 conversion failed: {exc}"
        job["message"] = job["error"]
        job["status_label"] = "Failed"


def cleanup_video_job(job_id):
    job = VIDEO_JOBS.pop(job_id, None)
    if job and job.get("result"):
        shutil.rmtree(job["result"].work_dir, ignore_errors=True)


def cleanup_ipod_job(job_id):
    job = IPOD_JOBS.pop(job_id, None)
    if job and job.get("result"):
        shutil.rmtree(job["result"].work_dir, ignore_errors=True)


def format_speed(bytes_per_second):
    if not bytes_per_second:
        return ""
    return f"{format_bytes(bytes_per_second)}/s"


def format_bytes(byte_count):
    if byte_count is None:
        return ""

    value = float(byte_count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024

    return f"{value:.1f} TB"


def format_eta(seconds):
    if seconds is None:
        return ""

    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} seconds"

    minutes, remaining_seconds = divmod(seconds, 60)
    if minutes < 60:
        if remaining_seconds:
            return f"{minutes} min {remaining_seconds} sec"
        return f"{minutes} minutes"

    hours, remaining_minutes = divmod(minutes, 60)
    if remaining_minutes:
        return f"{hours} hr {remaining_minutes} min"
    return f"{hours} hours"


@app.post("/spotify-playlist/start")
def start_spotify_playlist():
    try:
        raw_body = request.get_data(as_text=True)
        job_id = request.form.get("job_id", "").strip()
        app.logger.info(
            "spotify-playlist.start payload=%r form=%r job_id=%r content_type=%r",
            raw_body[:2000],
            dict(request.form),
            job_id,
            request.content_type,
        )

        job = PLAYLIST_JOBS.get(job_id)
        if not job:
            app.logger.warning("spotify-playlist.start 400 at=missing_prepared_job job_id=%r", job_id)
            return playlist_json(
                {"ok": False, "message": "Playlist details must be loaded before download starts."},
                400,
                "spotify-playlist.start",
            )

        if job["status"] != "prepared":
            app.logger.warning("spotify-playlist.start 400 at=invalid_job_state job_id=%r status=%r", job_id, job["status"])
            return playlist_json(
                {"ok": False, "message": "This playlist download has already started."},
                400,
                "spotify-playlist.start",
            )

        if get_ffmpeg_path() is None:
            return playlist_json(
                {"ok": False, "message": FFMPEG_MISSING_MESSAGE},
                500,
                "spotify-playlist.start",
            )

        job["status"] = "queued"
        job["message"] = "Download queued"
        thread = threading.Thread(target=run_spotify_playlist_job, args=(job_id,), daemon=True)
        thread.start()

        return playlist_json({"ok": True, "job_id": job_id}, context="spotify-playlist.start")
    except Exception as exc:
        app.logger.exception("spotify-playlist.start unexpected_exception")
        return playlist_json({"ok": False, "message": f"Unexpected playlist start error: {exc}"}, 500, "spotify-playlist.start")


@app.get("/spotify-playlist/progress/<job_id>")
def spotify_playlist_progress(job_id):
    try:
        job = PLAYLIST_JOBS.get(job_id)
        if not job:
            return playlist_json({"ok": False, "message": "Playlist job not found."}, 404, "spotify-playlist.progress")

        return playlist_json(
            {
            "ok": True,
            "status": job["status"],
            "playlist_name": job["playlist_name"],
            "playlist_thumbnail": job.get("playlist_thumbnail", ""),
            "current": job["current"],
            "total": job["total"],
            "message": job["message"],
            "download_url": job["download_url"],
            "error": job["error"],
            "tracks": job.get("tracks", []),
            "active_index": job.get("active_index"),
            },
            context="spotify-playlist.progress",
        )
    except Exception as exc:
        app.logger.exception("spotify-playlist.progress unexpected_exception job_id=%r", job_id)
        return playlist_json({"ok": False, "message": f"Unexpected playlist progress error: {exc}"}, 500, "spotify-playlist.progress")


@app.post("/spotify-playlist/stop/<job_id>")
def stop_spotify_playlist(job_id):
    job = PLAYLIST_JOBS.get(job_id)
    if not job:
        return playlist_json({"ok": False, "message": "Job not found."}, 404, "spotify-playlist.stop")
    job["stop_requested"] = True
    job["message"] = "Stopping... Finishing current song."
    return playlist_json({"ok": True}, context="spotify-playlist.stop")


@app.get("/spotify-playlist/download/<job_id>")
def download_spotify_playlist(job_id):
    job = PLAYLIST_JOBS.get(job_id)
    if not job or job.get("status") != "complete" or job.get("result") is None:
        return jsonify({"ok": False, "message": "Playlist ZIP is not ready yet."}), 404

    result = job["result"]

    @after_this_request
    def cleanup(response):
        response.call_on_close(lambda: cleanup_playlist_job(job_id))
        return response

    return send_file(
        result.file_path,
        as_attachment=True,
        download_name=result.download_name,
        mimetype="application/zip",
    )


def run_spotify_playlist_job(job_id):
    def update_progress(playlist_name, total, current, message, track_status=None):
        job = PLAYLIST_JOBS[job_id]
        if job.get("stop_requested"):
            return False
            
        job["playlist_name"] = playlist_name
        job["total"] = total
        job["current"] = current
        job["message"] = message
        job["status"] = "running"
        if current:
            job["active_index"] = current
            tracks = job.get("tracks") or []
            
            if track_status:
                tracks[current - 1]["status"] = track_status
                
            for index, track in enumerate(tracks, start=1):
                if index < current:
                    if track.get("status") not in ["Failed", "Not Found"]:
                        track["status"] = "Completed"
                elif index == current:
                    if not track_status:
                        track["status"] = "Downloading"
                else:
                    if track.get("status") not in ["Failed", "Not Found"]:
                        track["status"] = "Pending"
        return True

    try:
        job = PLAYLIST_JOBS[job_id]
        playlist = job.get("playlist")
        result = convert_spotify_playlist_to_zip(job["url"], DOWNLOAD_DIR, progress_callback=update_progress, playlist=playlist)
        job = PLAYLIST_JOBS[job_id]
        job["status"] = "complete"
        job["download_url"] = f"/spotify-playlist/download/{job_id}"
        job["result"] = result
        
        tracks = job.get("tracks") or []
        for track in tracks:
            if track.get("status") == "Downloading":
                track["status"] = "Completed"
                
        completed = sum(1 for t in tracks if t.get("status") == "Completed")
        failed = sum(1 for t in tracks if t.get("status") in ["Failed", "Not Found"])
        
        if failed > 0:
            job["message"] = f"Completed: {completed} | Not Found: {failed}"
        else:
            job["message"] = f"Completed: {completed}"
            
        job["active_index"] = None
    except ConversionError as exc:
        job = PLAYLIST_JOBS[job_id]
        job["status"] = "error"
        job["error"] = str(exc)
        job["message"] = str(exc)


@app.get("/spotify-playlist/details")
def spotify_playlist_details():
    try:
        url = request.args.get("url", "").strip()
        normalized = normalize_spotify_url(url)
        app.logger.info("spotify-playlist.details url=%r normalized=%r", url, normalized)

        detected = get_spotify_url_type(normalized)
        if detected != "playlist":
            app.logger.warning("spotify-playlist.details rejected: detected_type=%r", detected)
            return playlist_json({"ok": False, "message": "Please paste a valid Spotify playlist link."}, 400, "spotify-playlist.details")

        try:
            token = session.get("spotify_token")
            playlist = get_spotify_playlist_info(normalized, token)
        except SpotifyError as exc:
            app.logger.exception("spotify-playlist.details SpotifyError")
            return playlist_json({"ok": False, "message": str(exc)}, 400, "spotify-playlist.details")

        tracks = playlist_tracks_response(playlist)

        return playlist_json(
            {
            "ok": True,
            "playlist": {
                "name": playlist.get("name") or "Spotify Playlist",
                "thumbnail": playlist.get("thumbnail") or "",
                "total": len(tracks),
                "tracks": tracks,
            },
            },
            context="spotify-playlist.details",
        )
    except Exception as exc:
        app.logger.exception("spotify-playlist.details unexpected_exception")
        return playlist_json({"ok": False, "message": f"Unexpected playlist details error: {exc}"}, 500, "spotify-playlist.details")


@app.post("/spotify-playlist/prepare")
def prepare_spotify_playlist():
    try:
        raw_body = request.get_data(as_text=True)
        url = request.form.get("url", "").strip()
        normalized = normalize_spotify_url(url)
        app.logger.info(
            "spotify-playlist.prepare payload=%r form=%r url=%r normalized=%r content_type=%r",
            raw_body[:2000],
            dict(request.form),
            url,
            normalized,
            request.content_type,
        )

        detected = get_spotify_url_type(normalized)
        if detected != "playlist":
            app.logger.warning(
                "spotify-playlist.prepare 400 at=validate_url_type detected_type=%r normalized=%r",
                detected,
                normalized,
            )
            return playlist_json({"ok": False, "message": "Please paste a valid Spotify playlist link."}, 400, "spotify-playlist.prepare")

        try:
            playlist_id = get_spotify_id(normalized, "playlist")
            app.logger.info("spotify-playlist.prepare extracted_playlist_id=%r", playlist_id)
        except SpotifyError as exc:
            app.logger.warning("spotify-playlist.prepare 400 at=extract_playlist_id reason=%s", exc)
            return playlist_json({"ok": False, "message": str(exc)}, 400, "spotify-playlist.prepare")

        try:
            token = session.get("spotify_token")
            playlist = get_spotify_playlist_info(normalized, token)
        except SpotifyError as exc:
            app.logger.exception("spotify-playlist.prepare 400 at=get_spotify_playlist_info")
            return playlist_json({"ok": False, "message": str(exc)}, 400, "spotify-playlist.prepare")

        job_id = uuid.uuid4().hex
        PLAYLIST_JOBS[job_id] = build_prepared_playlist_job(normalized, playlist)
        app.logger.info(
            "spotify-playlist.prepare created_job job_id=%r playlist=%r total=%s",
            job_id,
            PLAYLIST_JOBS[job_id]["playlist_name"],
            PLAYLIST_JOBS[job_id]["total"],
        )

        payload = {"ok": True, "job_id": job_id, "playlist": playlist_response(PLAYLIST_JOBS[job_id])}
        return playlist_json(payload, context="spotify-playlist.prepare")
    except Exception as exc:
        app.logger.exception("spotify-playlist.prepare unexpected_exception")
        return playlist_json({"ok": False, "message": f"Unexpected playlist prepare error: {exc}"}, 500, "spotify-playlist.prepare")


def build_prepared_playlist_job(url, playlist):
    tracks = playlist_tracks_response(playlist)

    return {
        "status": "prepared",
        "playlist_name": playlist.get("name") or "Spotify Playlist",
        "playlist_thumbnail": playlist.get("thumbnail") or "",
        "current": 0,
        "total": len(tracks),
        "message": "Ready to download",
        "download_url": "",
        "error": "",
        "result": None,
        "tracks": tracks,
        "active_index": None,
        "playlist": playlist,
        "url": url,
    }


def playlist_response(job):
    return {
        "name": job["playlist_name"],
        "thumbnail": job.get("playlist_thumbnail", ""),
        "total": job["total"],
        "tracks": job.get("tracks", []),
    }


def playlist_tracks_response(playlist):
    tracks = []
    for track in playlist.get("tracks", []):
        tracks.append(
            {
                "title": track.get("title") or "",
                "artist": track.get("artist") or "",
                "thumbnail": track.get("thumbnail") or "",
                "status": track.get("status") or "Pending",
            }
        )
    return tracks


def cleanup_playlist_job(job_id):
    job = PLAYLIST_JOBS.pop(job_id, None)
    if job and job.get("result"):
        shutil.rmtree(job["result"].work_dir, ignore_errors=True)


@app.post("/bulk/start")
def start_bulk_download():
    try:
        raw_body = request.get_data(as_text=True)
        text_input = request.form.get("bulk_songs", "")
        uploaded_file = request.files.get("bulk_file")
        uploaded_text = ""

        app.logger.info(
            "bulk.start payload_preview=%r form_keys=%s file=%r content_type=%r",
            raw_body[:1000],
            sorted(request.form.keys()),
            uploaded_file.filename if uploaded_file else None,
            request.content_type,
        )

        if uploaded_file and uploaded_file.filename:
            if not uploaded_file.filename.lower().endswith(".txt"):
                app.logger.warning("bulk.start 400 at=validate_file reason=not_txt filename=%r", uploaded_file.filename)
                return api_json({"ok": False, "message": "Upload a .txt file containing one song per line."}, 400, "bulk.start")
            uploaded_text = uploaded_file.read().decode("utf-8", errors="ignore")

        try:
            song_names = parse_song_names(f"{text_input}\n{uploaded_text}")
        except BulkInputError as exc:
            app.logger.warning("bulk.start 400 at=parse_song_names reason=%s", exc)
            return api_json({"ok": False, "message": str(exc)}, 400, "bulk.start")

        if get_ffmpeg_path() is None:
            return api_json(
                {"ok": False, "message": FFMPEG_MISSING_MESSAGE},
                500,
                "bulk.start",
            )

        job_id = uuid.uuid4().hex
        BULK_JOBS[job_id] = build_bulk_job(song_names)
        app.logger.info("bulk.start created_job job_id=%r total=%s", job_id, len(song_names))

        thread = threading.Thread(target=run_bulk_job, args=(job_id,), daemon=True)
        thread.start()

        payload = {
            "ok": True,
            "job_id": job_id,
            "bulk": bulk_response(BULK_JOBS[job_id]),
        }
        return api_json(payload, context="bulk.start")
    except Exception as exc:
        app.logger.exception("bulk.start unexpected_exception")
        return api_json({"ok": False, "message": f"Unexpected bulk start error: {exc}"}, 500, "bulk.start")


@app.get("/bulk/progress/<job_id>")
def bulk_progress(job_id):
    try:
        job = BULK_JOBS.get(job_id)
        if not job:
            return api_json({"ok": False, "message": "Bulk download job not found."}, 404, "bulk.progress")

        return api_json(
            {
                "ok": True,
                "status": job["status"],
                "playlist_name": job["collection_name"],
                "playlist_thumbnail": "",
                "current": job["current"],
                "total": job["total"],
                "message": job["message"],
                "download_url": job["download_url"],
                "error": job["error"],
                "tracks": job.get("tracks", []),
                "active_index": job.get("active_index"),
            },
            context="bulk.progress",
        )
    except Exception as exc:
        app.logger.exception("bulk.progress unexpected_exception job_id=%r", job_id)
        return api_json({"ok": False, "message": f"Unexpected bulk progress error: {exc}"}, 500, "bulk.progress")


@app.post("/bulk/stop/<job_id>")
def stop_bulk_download(job_id):
    job = BULK_JOBS.get(job_id)
    if not job:
        return api_json({"ok": False, "message": "Job not found."}, 404, "bulk.stop")
    job["stop_requested"] = True
    job["message"] = "Stopping... Finishing current song."
    return api_json({"ok": True}, context="bulk.stop")


@app.get("/bulk/download/<job_id>")
def download_bulk_zip(job_id):
    job = BULK_JOBS.get(job_id)
    if not job or job.get("status") != "complete" or job.get("result") is None:
        return jsonify({"ok": False, "message": "Bulk ZIP is not ready yet."}), 404

    result = job["result"]

    @after_this_request
    def cleanup(response):
        response.call_on_close(lambda: cleanup_bulk_job(job_id))
        return response

    return send_file(
        result.file_path,
        as_attachment=True,
        download_name=result.download_name,
        mimetype="application/zip",
    )


def build_bulk_job(song_names):
    tracks = bulk_tracks_response(song_names)
    return {
        "status": "queued",
        "collection_name": "Bulk Songs",
        "song_names": song_names,
        "current": 0,
        "total": len(song_names),
        "message": "Bulk download queued",
        "download_url": "",
        "error": "",
        "result": None,
        "tracks": tracks,
        "active_index": None,
    }


def bulk_response(job):
    return {
        "name": job["collection_name"],
        "thumbnail": "",
        "total": job["total"],
        "tracks": job.get("tracks", []),
    }


def run_bulk_job(job_id):
    def update_progress(collection_name, total, current, message, track_status=None):
        job = BULK_JOBS[job_id]
        if job.get("stop_requested"):
            return False
            
        job["collection_name"] = collection_name
        job["total"] = total
        job["current"] = current
        job["message"] = message
        job["status"] = "running"
        if current:
            job["active_index"] = current
            tracks = job.get("tracks") or []
            
            if track_status:
                tracks[current - 1]["status"] = track_status
                
            for index, track in enumerate(tracks, start=1):
                if index < current:
                    if track.get("status") not in ["Failed", "Not Found"]:
                        track["status"] = "Completed"
                elif index == current:
                    if not track_status:
                        track["status"] = "Downloading"
                else:
                    if track.get("status") not in ["Failed", "Not Found"]:
                        track["status"] = "Pending"
        return True

    try:
        job = BULK_JOBS[job_id]
        result = convert_bulk_songs_to_zip(job["song_names"], DOWNLOAD_DIR, progress_callback=update_progress)
        job = BULK_JOBS[job_id]
        job["status"] = "complete"
        job["download_url"] = f"/bulk/download/{job_id}"
        job["result"] = result
        
        tracks = job.get("tracks") or []
        for track in tracks:
            if track.get("status") == "Downloading":
                track["status"] = "Completed"
                
        completed = sum(1 for t in tracks if t.get("status") == "Completed")
        failed = sum(1 for t in tracks if t.get("status") in ["Failed", "Not Found"])
        
        if failed > 0:
            job["message"] = f"Completed: {completed} | Not Found: {failed}"
        else:
            job["message"] = f"Completed: {completed}"
            
        job["active_index"] = None
    except ConversionError as exc:
        app.logger.exception("bulk.job conversion_error job_id=%r", job_id)
        job = BULK_JOBS[job_id]
        job["status"] = "error"
        job["error"] = str(exc)
        job["message"] = str(exc)
    except Exception as exc:
        app.logger.exception("bulk.job unexpected_exception job_id=%r", job_id)
        job = BULK_JOBS[job_id]
        job["status"] = "error"
        job["error"] = f"Bulk download failed: {exc}"
        job["message"] = job["error"]


def cleanup_bulk_job(job_id):
    job = BULK_JOBS.pop(job_id, None)
    if job and job.get("result"):
        shutil.rmtree(job["result"].work_dir, ignore_errors=True)


if __name__ == "__main__":
    app.run(debug=True)
    
