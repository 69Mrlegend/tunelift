MAX_BULK_SONGS = 200


class BulkInputError(Exception):
    """Raised when a bulk song list cannot be used."""


def parse_song_names(text):
    """Turn pasted text or a text file into a clean list of song names."""
    songs = []
    seen = set()

    for line in text.splitlines():
        song = " ".join(line.strip().split())
        if not song:
            continue

        key = song.lower()
        if key in seen:
            continue

        seen.add(key)
        songs.append(song)

    if not songs:
        raise BulkInputError("Paste at least one song name or upload a .txt file.")

    if len(songs) > MAX_BULK_SONGS:
        raise BulkInputError(f"Bulk downloads are limited to {MAX_BULK_SONGS} songs at a time.")

    return songs


def bulk_tracks_response(song_names):
    """Create the track objects shown in the live progress UI."""
    return [
        {
            "title": song_name,
            "artist": "YouTube match",
            "thumbnail": "",
            "status": "Pending",
        }
        for song_name in song_names
    ]
