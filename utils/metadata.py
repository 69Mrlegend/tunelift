from pathlib import Path

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1


UNKNOWN_ARTIST = "Unknown Artist"


def add_mp3_metadata(mp3_path, title, artist, cover_path=None, album="YouTube"):
    """Add title, artist, album name, and album art to an MP3 file."""
    mp3_path = Path(mp3_path)
    tags = ID3()

    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))

    if cover_path:
        add_album_art(tags, cover_path)

    tags.save(mp3_path, v2_version=3)


def get_youtube_track_metadata(info, fallback_title):
    """Choose the best title and artist from yt-dlp data."""
    video_title = clean_text(info.get("title")) or fallback_title
    parsed_artist, parsed_title = split_artist_and_title(video_title)

    artist = first_valid_text(
        info.get("artist"),
        info.get("creator"),
        info.get("track_artist"),
        info.get("album_artist"),
        info.get("artists"),
        parsed_artist,
        info.get("uploader"),
        info.get("channel"),
    )

    title = first_valid_text(
        info.get("track"),
        info.get("alt_title"),
        parsed_title,
        video_title,
        fallback_title,
    )

    return title, artist or UNKNOWN_ARTIST


def get_spotify_track_metadata(track):
    """Choose title and artist from Spotify metadata."""
    title = clean_text(track.get("title")) or "Spotify Track"
    parsed_artist, parsed_title = split_artist_and_title(title)

    artist = first_valid_text(track.get("artist"), parsed_artist)
    if parsed_artist and parsed_title and not is_valid_artist(track.get("artist")):
        title = parsed_title

    return title, artist or UNKNOWN_ARTIST


def split_artist_and_title(raw_title):
    """Extract artist and title from common 'Artist - Song' video titles."""
    title = clean_text(raw_title)
    if not title:
        return None, None

    separators = [" - ", " – ", " — ", " | "]
    for separator in separators:
        if separator in title:
            artist, song = title.split(separator, 1)
            artist = clean_artist_name(artist)
            song = clean_song_title(song)
            if is_valid_artist(artist) and song:
                return artist, song

    return None, title


def first_valid_text(*values):
    for value in values:
        cleaned = clean_text(value)
        if cleaned and cleaned.lower() not in {"none", "null", "unknown", "unknown artist"}:
            return cleaned
    return None


def is_valid_artist(value):
    artist = clean_artist_name(value)
    if not artist:
        return False

    lowered = artist.lower()
    invalid_words = {"official", "lyrics", "lyric", "audio", "video", "topic"}
    return not all(word in invalid_words for word in lowered.split())


def clean_artist_name(value):
    artist = clean_text(value)
    if not artist:
        return None

    artist = artist.replace("VEVO", "").strip()
    artist = remove_suffixes(artist, [" - Topic", " Topic", " Official", " official"])
    return artist.strip(" -|") or None


def clean_song_title(value):
    title = clean_text(value)
    if not title:
        return None

    title = remove_bracket_phrases(title)
    return title.strip(" -|") or None


def clean_text(value):
    if value is None:
        return None

    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item).strip() for item in value if str(item).strip())

    text = str(value).strip()
    return " ".join(text.split()) or None


def remove_suffixes(value, suffixes):
    text = value
    lowered = text.lower()

    for suffix in suffixes:
        if lowered.endswith(suffix.lower()):
            text = text[: -len(suffix)]
            lowered = text.lower()

    return text


def remove_bracket_phrases(value):
    phrases = [
        "official video",
        "official music video",
        "official audio",
        "lyrics",
        "lyric video",
        "audio",
        "visualizer",
        "full video",
        "remix",
        "slowed",
        "reverb",
        "bass boosted",
        "nightcore",
        "4k",
        "hd",
        "official",
    ]
    text = value

    for phrase in phrases:
        # Remove from brackets
        text = text.replace(f"({phrase})", "", 1)
        text = text.replace(f"[{phrase}]", "", 1)
        text = text.replace(f"({phrase.title()})", "", 1)
        text = text.replace(f"[{phrase.title()}]", "", 1)
        text = text.replace(f"({phrase.upper()})", "", 1)
        text = text.replace(f"[{phrase.upper()}]", "", 1)
        
        # Remove if just floating at the end (with or without dashes)
        text = remove_suffixes(text, [f" {phrase}", f" - {phrase}", f" {phrase.title()}", f" - {phrase.title()}", f" {phrase.upper()}", f" - {phrase.upper()}"])

    return text.strip(" -|")


def add_album_art(tags, cover_path):
    """Embed a thumbnail as the front cover image."""
    cover_path = Path(cover_path)
    if not cover_path.exists():
        return

    image_data = cover_path.read_bytes()
    tags.add(
        APIC(
            encoding=3,
            mime=get_image_mime_type(cover_path, image_data),
            type=3,
            desc="Cover",
            data=image_data,
        )
    )


def get_image_mime_type(image_path, image_data):
    if image_data.startswith(b"\x89PNG"):
        return "image/png"

    if image_data[:4] == b"RIFF" and image_data[8:12] == b"WEBP":
        return "image/webp"

    suffix = Path(image_path).suffix.lower()

    if suffix == ".png":
        return "image/png"

    if suffix == ".webp":
        return "image/webp"

    return "image/jpeg"
