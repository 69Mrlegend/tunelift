import json
import shutil
from datetime import datetime
from pathlib import Path


class JsonStore:
    def __init__(self, path, default):
        self.path = Path(path)
        self.default = default
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write(default)

    def read(self):
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return self.default.copy() if isinstance(self.default, dict) else list(self.default)

    def write(self, data):
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)


DEFAULT_SETTINGS = {
    "audio_quality": "320",
    "video_quality": "720",
    "simultaneous_downloads": 1,
    "download_folder": "",
    "embed_metadata": True,
    "embed_cover_art": True,
    "zip_compression_level": 6,
    "wifi_only": False,
    "auto_clear_cache": False,
}


def media_library(download_dir):
    download_dir = Path(download_dir)
    songs = []
    for path in sorted(download_dir.rglob("*.mp3"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
        except OSError:
            continue
        songs.append({
            "id": path.as_posix(),
            "title": path.stem,
            "path": str(path),
            "url": f"/api/player/file?path={path.as_posix()}",
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return songs


def directory_size(path):
    path = Path(path)
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def storage_report(download_dir):
    download_dir = Path(download_dir)
    mp3_seen = {}
    duplicates = []
    temp_files = []
    broken_zips = []
    for item in download_dir.rglob("*"):
        if not item.is_file():
            continue
        suffix = item.suffix.lower()
        try:
            size = item.stat().st_size
        except OSError:
            continue
        if suffix == ".mp3":
            key = (item.name.lower(), size)
            if key in mp3_seen:
                duplicates.append({"path": str(item), "original": str(mp3_seen[key]), "size": size})
            else:
                mp3_seen[key] = item
        if suffix in {".part", ".ytdl", ".tmp", ".webm", ".m4a"}:
            temp_files.append({"path": str(item), "size": size})
        if suffix == ".zip" and size == 0:
            broken_zips.append({"path": str(item), "size": size})
    return {
        "downloads_size": directory_size(download_dir),
        "song_count": len(mp3_seen),
        "duplicates": duplicates,
        "temp_files": temp_files,
        "broken_zips": broken_zips,
    }


def cleanup_storage(download_dir, remove_duplicates=False):
    report = storage_report(download_dir)
    removed = []
    targets = report["temp_files"] + report["broken_zips"]
    if remove_duplicates:
        targets += report["duplicates"]
    root = Path(download_dir).resolve()
    for entry in targets:
        target = Path(entry["path"]).resolve()
        if root in target.parents or target == root:
            try:
                target.unlink()
                removed.append(str(target))
            except OSError:
                pass
    for child in root.iterdir():
        if child.is_dir():
            try:
                if not any(child.iterdir()):
                    shutil.rmtree(child, ignore_errors=True)
            except OSError:
                pass
    return removed
