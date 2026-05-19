import os
import time
import uuid
import sqlite3
import logging
import threading
from datetime import datetime
from pathlib import Path

import converter
from utils.spotify import is_spotify_url, get_spotify_url_type

logger = logging.getLogger(__name__)

class DownloadStoppedException(Exception):
    """Raised to instantly halt an active download."""
    pass

class SQLiteHistoryStore:
    """Manages the persistent SQLite database for Completed, Failed, and Stopped downloads."""
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS download_history (
                        job_id TEXT PRIMARY KEY,
                        type TEXT,
                        title TEXT,
                        artist TEXT,
                        thumbnail TEXT,
                        status TEXT,
                        file_size TEXT,
                        saved_location TEXT,
                        download_name TEXT,
                        url TEXT,
                        error TEXT,
                        playlist_name TEXT,
                        output_path TEXT,
                        filesize_bytes INTEGER DEFAULT 0,
                        retry_count INTEGER DEFAULT 0,
                        date_time TEXT
                    )
                """)
                self._ensure_columns(conn)
                conn.commit()
            logger.info("[QueueManager] SQLite History Database initialized at %s", self.db_path)
        except Exception as e:
            logger.exception("[QueueManager] Failed to initialize SQLite database: %s", e)

    def _ensure_columns(self, conn):
        cursor = conn.execute("PRAGMA table_info(download_history)")
        columns = {row[1] for row in cursor.fetchall()}
        migrations = {
            "playlist_name": "ALTER TABLE download_history ADD COLUMN playlist_name TEXT DEFAULT ''",
            "output_path": "ALTER TABLE download_history ADD COLUMN output_path TEXT DEFAULT ''",
            "filesize_bytes": "ALTER TABLE download_history ADD COLUMN filesize_bytes INTEGER DEFAULT 0",
            "retry_count": "ALTER TABLE download_history ADD COLUMN retry_count INTEGER DEFAULT 0",
        }
        for name, statement in migrations.items():
            if name not in columns:
                conn.execute(statement)

    def save_job(self, job):
        """Persist a job status update to SQLite."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO download_history (
                        job_id, type, title, artist, thumbnail, status,
                        file_size, saved_location, download_name, url, error,
                        playlist_name, output_path, filesize_bytes, retry_count, date_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job["job_id"],
                    job["type"],
                    job["title"],
                    job["artist"],
                    job.get("thumbnail") or "",
                    job["status"],
                    job.get("file_size") or "",
                    job.get("saved_location") or "",
                    job.get("download_name") or "",
                    job.get("url") or "",
                    job.get("error") or "",
                    job.get("playlist_name") or "",
                    job.get("saved_location") or "",
                    int(job.get("filesize_bytes") or 0),
                    int(job.get("retry_count") or 0),
                    job["date_time"]
                ))
                conn.commit()
            logger.info("[QueueManager] History saved: job_id=%s, status=%s", job["job_id"], job["status"])
        except Exception as e:
            logger.exception("[QueueManager] Failed to save job %s to SQLite: %s", job["job_id"], e)

    def load_all(self):
        """Load all historical records from SQLite."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM download_history ORDER BY date_time DESC")
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.exception("[QueueManager] Failed to load history from SQLite: %s", e)
            return []

    def delete_job(self, job_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM download_history WHERE job_id = ?", (job_id,))
            conn.commit()

    def clear(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM download_history")
            conn.commit()

class QueueManager:
    """Manages the in-memory queue, background sequential worker, and SQLite history database."""
    def __init__(self, db_path, download_dir):
        self.db_path = Path(db_path)
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.db = SQLiteHistoryStore(str(self.db_path))
        
        self.jobs = {}  # In-memory RAM cache: job_id -> job dict
        self.queue = []  # Ordered list of job_ids in active queue
        self.current_job_id = None
        self.queue_paused = False
        self.max_retry_count = 3
        self.lock = threading.Lock()
        
        # Load persistent records into memory as historical completed/failed/stopped items
        self._load_history_to_memory()
        
        # Start strictly sequential daemon worker thread
        self.worker_thread = threading.Thread(target=self._worker_loop, name="DownloadQueueWorker", daemon=True)
        self.worker_thread.start()
        logger.info("[QueueManager] Queue started")

    def _load_history_to_memory(self):
        records = self.db.load_all()
        for record in records:
            job_id = record["job_id"]
            self.jobs[job_id] = {
                "id": job_id,
                "job_id": job_id,
                "download_id": job_id,
                "type": record["type"],
                "title": record["title"],
                "artist": record["artist"],
                "thumbnail": record["thumbnail"],
                "playlist_name": record["title"] if record["type"] in ["Spotify", "YouTube Playlist"] else "",
                "playlist_thumbnail": record["thumbnail"] if record["type"] in ["Spotify", "YouTube Playlist"] else "",
                "current": 0,
                "total": 0,
                "status": record["status"],
                "file_size": record["file_size"],
                "saved_location": record["saved_location"],
                "output_path": record.get("output_path") or record["saved_location"],
                "filesize_bytes": record.get("filesize_bytes") or 0,
                "download_name": record["download_name"],
                "url": record["url"],
                "error": record["error"],
                "retry_count": record.get("retry_count") or 0,
                "date_time": record["date_time"],
                "percent": 100 if record["status"] == "Completed" else 0,
                "speed": "",
                "eta": "",
                "stop_requested": False
            }
        logger.info("[QueueManager] Loaded %d historical records from database.", len(records))

    def add_job(self, job_type, url, quality=None, title="YouTube Download", artist="Unknown", thumbnail="", tracks=None):
        """Enqueue a new download job in-memory."""
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "job_id": job_id,
            "download_id": job_id,
            "type": job_type,  # "MP3", "MP4", "Bulk", "Spotify"
            "status": "Pending",
            "url": url,
            "quality": quality,
            "title": title,
            "artist": artist,
            "thumbnail": thumbnail,
            "playlist_name": title if job_type in ["Spotify", "YouTube Playlist"] else "",
            "playlist_thumbnail": thumbnail if job_type in ["Spotify", "YouTube Playlist"] else "",
            "current": 0,
            "total": len(tracks) if tracks else 0,
            "percent": 0.0,
            "speed": "",
            "eta": "",
            "file_size": "",
            "filesize_bytes": 0,
            "saved_location": "",
            "output_path": "",
            "download_name": "",
            "error": "",
            "retry_count": 0,
            "retry_status": "",
            "date_time": datetime.now().isoformat(),
            "tracks": tracks or [],
            "stop_requested": False,
            "pause_requested": False,
            "active_index": None
        }
        
        with self.lock:
            self.jobs[job_id] = job
            self.queue.append(job_id)
            
        print(f"[QueueManager] QUEUE JOB CREATED: job_id={job_id}, type={job_type}, title={title}", flush=True)
        logger.info("[QueueManager] Enqueued job %s: type=%s, url=%r", job_id, job_type, url)
        
        # Save creation event to persistent history store
        self.db.save_job(job)
        return job_id

    def pause_queue(self):
        with self.lock:
            self.queue_paused = True
            if self.current_job_id and self.current_job_id in self.jobs:
                self.jobs[self.current_job_id]["pause_requested"] = True
                self.jobs[self.current_job_id]["message"] = "Pausing after current download block"
        return True

    def resume_queue(self):
        with self.lock:
            self.queue_paused = False
            for job in self.jobs.values():
                if job.get("status") == "Paused":
                    job["status"] = "Pending"
                    job["pause_requested"] = False
                    job["stop_requested"] = False
                    if job["job_id"] not in self.queue:
                        self.queue.append(job["job_id"])
                    self.db.save_job(job)
        return True

    def pause_job(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
            if job["status"] == "Pending":
                job["status"] = "Paused"
                job["message"] = "Paused"
                if job_id in self.queue:
                    self.queue.remove(job_id)
                self.db.save_job(job)
            elif job["status"] == "Downloading":
                job["pause_requested"] = True
                job["message"] = "Pausing..."
            return True

    def resume_job(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
            if job["status"] == "Paused":
                job["status"] = "Pending"
                job["pause_requested"] = False
                job["stop_requested"] = False
                job["message"] = "Resumed"
                if job_id not in self.queue:
                    self.queue.append(job_id)
                self.db.save_job(job)
            return True

    def cancel_job(self, job_id):
        return self.stop_job(job_id)

    def stop_job(self, job_id):
        """Safely stops a pending or active job."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
            
            job["stop_requested"] = True
            
            # If job is pending, we can transition it to Stopped immediately
            if job["status"] == "Pending":
                job["status"] = "Stopped"
                job["message"] = "Stopped manually"
                logger.info("[QueueManager] Stopped manually (Pending): %s", job_id)
                self.db.save_job(job)
                if job_id in self.queue:
                    self.queue.remove(job_id)
            elif job["status"] == "Downloading":
                job["message"] = "Stopping... finishing current block."
                logger.info("[QueueManager] Stop signal sent to active job: %s", job_id)
                
        return True

    def retry_job(self, job_id):
        """Retries a failed or stopped job."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
            
            # Reinitialize job fields for retrying
            job["status"] = "Pending"
            job["percent"] = 0.0
            job["speed"] = ""
            job["eta"] = ""
            job["error"] = ""
            job["stop_requested"] = False
            job["active_index"] = None
            job["retry_status"] = ""
            job["date_time"] = datetime.now().isoformat()
            
            if job_id not in self.queue:
                self.queue.append(job_id)
                
        logger.info("[QueueManager] Retry triggered: job_id=%s, title=%r", job_id, job["title"])
        self.db.save_job(job)
        return True

    def delete_history_item(self, job_id):
        with self.lock:
            self.jobs.pop(job_id, None)
            if job_id in self.queue:
                self.queue.remove(job_id)
        self.db.delete_job(job_id)
        return True

    def clear_history(self):
        with self.lock:
            removable = [
                jid for jid, job in self.jobs.items()
                if job.get("status") in ["Completed", "Failed", "Stopped", "Not Found", "Paused"]
            ]
            for jid in removable:
                self.jobs.pop(jid, None)
                if jid in self.queue:
                    self.queue.remove(jid)
        self.db.clear()
        return True

    def get_queue_status(self):
        """Returns the in-memory queue status (separated from SQLite for performance)."""
        with self.lock:
            active_jobs = []
            history_jobs = []
            
            # Divide into active queue items and completed/failed history list
            for jid in list(self.jobs.keys()):
                job = self.jobs[jid]
                # If it's Completed, Failed, Stopped, or Not Found, it's historical
                if job["status"] in ["Completed", "Failed", "Stopped", "Not Found", "Paused"]:
                    history_jobs.append(job)
                else:
                    active_jobs.append(job)
                    
            # Sort history by date_time descending
            history_jobs.sort(key=lambda x: x["date_time"], reverse=True)
            
            return {
                "active": active_jobs,
                "history": history_jobs,
                "current_job_id": self.current_job_id,
                "queue_paused": self.queue_paused
            }

    def _worker_loop(self):
        """Background loop sequentially processing jobs."""
        print("[QueueManager] Download Queue Worker Thread Started!", flush=True)
        while True:
            next_job_id = None
            with self.lock:
                pending_jobs = [] if self.queue_paused else [jid for jid in self.queue if self.jobs[jid]["status"] == "Pending"]
                if pending_jobs:
                    next_job_id = pending_jobs[0]
                    self.current_job_id = next_job_id
                    print(f"[QueueManager] WORKER PICKED JOB: job_id={next_job_id}", flush=True)
            
            if next_job_id:
                try:
                    print(f"[QueueManager] QUEUE JOB STARTED: job_id={next_job_id}", flush=True)
                    self._process_job(next_job_id)
                except Exception as e:
                    print(f"[QueueManager] Uncaught exception processing job {next_job_id}: {e}", flush=True)
                    logger.exception("[QueueManager] Uncaught exception processing job %s: %s", next_job_id, e)
                finally:
                    with self.lock:
                        if self.current_job_id == next_job_id:
                            self.current_job_id = None
                        if next_job_id in self.queue:
                            self.queue.remove(next_job_id)
            else:
                time.sleep(0.5)

    def _process_job(self, job_id):
        job = self.jobs[job_id]
        
        # Enforce YouTube direct MP3 mode's Strict No-Spotify Rule
        is_direct_yt_mp3 = False
        if job["type"] == "MP3":
            # Check if it is a direct YouTube URL
            is_yt, _ = converter.validate_youtube_url(job["url"])
            if is_yt:
                is_direct_yt_mp3 = True
                
        with self.lock:
            job["status"] = "Downloading"
            job["percent"] = 0.0
            
        logger.info("[QueueManager] Item downloading: job_id=%s, type=%s, title=%r, is_direct_yt_mp3=%s",
                    job_id, job["type"], job["title"], is_direct_yt_mp3)

        # 1. In-memory progress callback for live updates (no SQLite writes here)
        def progress_callback(data):
            # Safe Stop trigger
            if job.get("stop_requested"):
                raise DownloadStoppedException("Stopped manually")
            if job.get("pause_requested"):
                raise DownloadStoppedException("Paused")
                
            # If data is a yt-dlp progress dict
            if isinstance(data, dict):
                percent = data.get("percent")
                speed = data.get("speed")
                eta = data.get("eta")
                
                with self.lock:
                    if percent is not None:
                        job["percent"] = round(float(percent), 1)
                    if speed is not None:
                        job["speed"] = format_speed(speed)
                    if eta is not None:
                        job["eta"] = format_eta(eta)
                        
                logger.info("[QueueManager] ETA updated: job_id=%s, percent=%s%%, speed=%s, eta=%s",
                            job_id, job["percent"], job["speed"], job["eta"])
            return True

        # 2. Progress callback for lists (Bulk / Spotify Playlist)
        def list_progress_callback(playlist_name, total, current, message, track_status=None):
            if job.get("stop_requested"):
                return False  # Instruct loop to break safely
            if job.get("pause_requested"):
                return False
                
            with self.lock:
                job["title"] = playlist_name
                job["total"] = total
                job["current"] = current
                job["message"] = message
                
                if current:
                    job["active_index"] = current
                    tracks = job.get("tracks") or []
                    if track_status and current <= len(tracks):
                        tracks[current - 1]["status"] = track_status
                        
                    for index, track in enumerate(tracks, start=1):
                        if index < current:
                            if track.get("status") not in ["Failed", "Not Found", "Stopped"]:
                                track["status"] = "Completed"
                        elif index == current:
                            if not track_status:
                                track["status"] = "Downloading"
                        else:
                            if track.get("status") not in ["Failed", "Not Found", "Stopped"]:
                                track["status"] = "Pending"
                                
                if total:
                    job["percent"] = round((current / total) * 100, 1)
                    
            logger.info("[QueueManager] List updated: job_id=%s, item %d/%d (%s)", job_id, current, total, message)
            return True

        attempts = self.max_retry_count + 1
        for attempt in range(1, attempts + 1):
            result = None
            try:
                if attempt > 1:
                    with self.lock:
                        job["retry_count"] = attempt - 1
                        job["retry_status"] = f"Retry {attempt - 1}/{self.max_retry_count}"
                        job["message"] = job["retry_status"]
                    logger.info("[QueueManager] Retrying job_id=%s attempt=%s", job_id, attempt)

                if job["type"] == "MP3":
                    if is_direct_yt_mp3:
                        result = converter.convert_youtube_to_mp3(job["url"], self.download_dir, progress_callback=progress_callback)
                    else:
                        result = converter.convert_search_to_mp3(job["url"], self.download_dir, progress_callback=progress_callback)
                elif job["type"] == "MP4":
                    result = converter.convert_youtube_to_mp4(job["url"], self.download_dir, job.get("quality") or "720", progress_callback=progress_callback)
                elif job["type"] == "iPod":
                    result = converter.convert_youtube_to_ipod_mp4(job["url"], self.download_dir, progress_callback=progress_callback)
                elif job["type"] == "Spotify":
                    if is_spotify_url(job["url"]) and get_spotify_url_type(job["url"]) == "playlist":
                        result = converter.convert_spotify_playlist_to_zip(job["url"], self.download_dir, progress_callback=list_progress_callback)
                    else:
                        result = converter.convert_spotify_to_mp3(job["url"], self.download_dir, progress_callback=progress_callback)
                elif job["type"] == "Bulk":
                    result = converter.convert_bulk_songs_to_zip(job["url"], self.download_dir, progress_callback=list_progress_callback)
                elif job["type"] == "YouTube Playlist":
                    result = converter.convert_youtube_playlist_to_zip(job["url"], self.download_dir, progress_callback=list_progress_callback)

                if result:
                    size_bytes = Path(result.file_path).stat().st_size
                    formatted_size = format_bytes(size_bytes)
                    with self.lock:
                        job["status"] = "Completed"
                        job["percent"] = 100.0
                        job["speed"] = ""
                        job["eta"] = ""
                        job["retry_status"] = ""
                        job["file_size"] = formatted_size
                        job["filesize_bytes"] = size_bytes
                        job["saved_location"] = str(result.file_path)
                        job["output_path"] = str(result.file_path)
                        job["download_name"] = result.download_name
                        if job["type"] not in ["Bulk", "Spotify", "YouTube Playlist"]:
                            job["title"] = result.download_name.replace(".mp3", "").replace(".mp4", "")
                    logger.info("[QueueManager] Job completed successfully: job_id=%s, size=%s", job_id, formatted_size)
                    self.db.save_job(job)
                    return
            except DownloadStoppedException as exc:
                with self.lock:
                    paused = "Paused" in str(exc) or job.get("pause_requested")
                    job["status"] = "Paused" if paused else "Stopped"
                    job["speed"] = ""
                    job["eta"] = ""
                    job["error"] = "Paused" if paused else "Stopped manually"
                    job["message"] = job["error"]
                logger.info("[QueueManager] %s: job_id=%s", job["status"], job_id)
                self.db.save_job(job)
                return
            except Exception as e:
                if job.get("pause_requested") or job.get("stop_requested"):
                    with self.lock:
                        paused = job.get("pause_requested")
                        job["status"] = "Paused" if paused else "Stopped"
                        job["speed"] = ""
                        job["eta"] = ""
                        job["error"] = "Paused" if paused else "Stopped manually"
                        job["message"] = job["error"]
                    self.db.save_job(job)
                    return
                readable = humanize_error(e)
                if attempt <= self.max_retry_count and is_retryable_error(e):
                    with self.lock:
                        job["error"] = readable
                        job["retry_count"] = attempt
                        job["retry_status"] = f"Retry {attempt}/{self.max_retry_count}"
                    time.sleep(min(2 * attempt, 6))
                    continue
                with self.lock:
                    job["status"] = "Failed"
                    job["error"] = readable
                    job["percent"] = 0.0
                    job["speed"] = ""
                    job["eta"] = ""
                logger.error("[QueueManager] Job failed: job_id=%s, error=%s", job_id, readable)
                self.db.save_job(job)
                return

# Formatter utilities
def format_speed(bytes_per_second):
    if not bytes_per_second:
        return ""
    return f"{format_bytes(bytes_per_second)}/s"

def format_bytes(byte_count):
    if byte_count is None:
        return ""
    value = float(byte_count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"

def format_eta(seconds):
    if seconds is None:
        return ""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, remaining_seconds = divmod(seconds, 60)
    if remaining_seconds:
        return f"{minutes}m {remaining_seconds}s"
    return f"{minutes}m"

def is_retryable_error(exc):
    text = str(exc).lower()
    needles = [
        "timed out", "timeout", "temporarily", "temporary", "connection",
        "network", "http error 5", "429", "unavailable", "fragment",
        "ffmpeg", "merge", "reset by peer"
    ]
    return any(needle in text for needle in needles)

def humanize_error(exc):
    text = str(exc).strip()
    lower = text.lower()
    if "ffmpeg" in lower:
        return "FFmpeg could not process the downloaded media. Check FFmpeg and try again."
    if "unavailable" in lower:
        return "The source is temporarily unavailable. TuneLift retried it automatically."
    if "timed out" in lower or "timeout" in lower or "connection" in lower:
        return "Network connection failed during download. TuneLift retried it automatically."
    if "private" in lower:
        return "This video or playlist is private and cannot be downloaded."
    return text or "Download failed unexpectedly."
