import logging
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from utils.converter import get_ffmpeg_location


logger = logging.getLogger(__name__)


# Variant keywords: these are undesirable but NOT absolute rejects.
# Results containing them receive a heavy score penalty so they only
# win when absolutely no clean version is available (last-resort fallback).
BAD_VARIANT_KEYWORDS = {
    "slowed",
    "reverb",
    "remix",
    "sped up",
    "nightcore",
    "instrumental",
    "cover",
    "live",
    "bass boosted",
    "bass boost",
    "fan made",
    "fanmade",
    "fan edit",
    "fanmade edit",
    "extended",
    "8d audio",
    "8d",
    "shorts",
}

# Score penalty applied per matched BAD_VARIANT_KEYWORD.
# Large enough that variants only win as an absolute last resort.
BAD_VARIANT_PENALTY = 45

# Absolute rejects — truly irrelevant content that we never want.
# These return score=0 and are excluded from ALL fallback pools.
ABSOLUTE_REJECT_KEYWORDS = {
    "reaction",
    "unboxing",
    "podcast clip",
    "compilation",
    "top songs",
    "hits playlist",
    "best of playlist",
    "top hits",
    "hour mix",
    "hour loop",
}

# Keep old name as alias so nothing else in the codebase breaks.
HARD_REJECT_KEYWORDS = ABSOLUTE_REJECT_KEYWORDS

LOW_QUALITY_KEYWORDS = {
    "karaoke",
    "mashup",
    "tribute",
    "concert",
    "unplugged",
    "performance",
    "teaser",
    "short version",
    "fan upload",
    # NOTE: "lyrics" and "lyric video" removed — many official topic uploads
    # legitimately have these in description/title and should not be blocked.
}

# Keywords that indicate an audiobook query
AUDIOBOOK_KEYWORDS = {
    "audiobook",
    "audio book",
    "full book",
    "full audiobook",
    "chapter",
    "full version",
    "narrated by",
    "unabridged",
    "read aloud",
}

# "audio" alone is intentionally removed — it matches too many unrelated videos.
OFFICIAL_AUDIO_PATTERNS = ("official audio", "official visualizer", "lyric video", "lyrics")
OFFICIAL_VIDEO_PATTERNS = ("official video", "music video")

# Lowered threshold — results below this get a best-effort fallback rather
# than an immediate "Not Found".  The real gate is now inside
# filter_youtube_results() which always returns *something*.
MIN_CONFIDENT_MATCH_SCORE = 55

# Score thresholds for match quality labels shown in the UI
MATCH_QUALITY_EXACT = 95
MATCH_QUALITY_GOOD = 72


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
    apply_ffmpeg_location(options)

    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=True)
    except DownloadError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc
    except ExtractorError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc


def search_youtube_match(search_query, track_info=None, limit=15, exclude_urls=None):
    """Find the most likely original YouTube result without downloading media.

    For plain song names like "Eclipse — octbrfrst" we also try to split the
    query on common separators (em-dash, en-dash, hyphen) so we can pass a
    proper title + artist to the scorer even when no Spotify metadata exists.
    """
    exclude_urls = set(exclude_urls or [])
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    apply_ffmpeg_location(options)

    # If we only have a raw query string with no structured track_info, try to
    # infer title/artist by splitting on common separators.
    effective_track_info = track_info
    if not track_info or (not track_info.get("artist") and not track_info.get("search_query")):
        inferred = _infer_title_artist(search_query)
        if inferred:
            effective_track_info = inferred
            logger.info(
                "search_youtube_match inferred title=%r artist=%r from query=%r",
                inferred.get("title"), inferred.get("artist"), search_query,
            )
        else:
            effective_track_info = track_info or {"title": search_query}

    try:
        with YoutubeDL(options) as ydl:
            search_res = ydl.extract_info(f"ytsearch{limit}:{search_query}", download=False)
    except DownloadError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc
    except ExtractorError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc

    entries = [
        entry for entry in search_res.get("entries", [])
        if entry and get_entry_url(entry) not in exclude_urls
    ]
    best_entry = filter_youtube_results(entries, effective_track_info)

    if not best_entry:
        raise DownloadFailed(
            "No matching song found on YouTube. "
            "Try adding the artist name or a more specific title."
        )

    logger.info(
        "search_youtube_match selected url=%r score=%.1f reason=%r",
        get_entry_url(best_entry),
        best_entry.get("_match_score", 0),
        best_entry.get("_match_reason", ""),
    )
    return best_entry


def get_search_preview(search_query, track_info=None, exclude_urls=None):
    """Return the selected YouTube match metadata for confirmation in the UI."""
    entry = search_youtube_match(search_query, track_info=track_info, exclude_urls=exclude_urls)
    score = round(entry.get("_match_score", 0), 1)

    if score >= MATCH_QUALITY_EXACT:
        match_quality = "exact"
    elif score >= MATCH_QUALITY_GOOD:
        match_quality = "good"
    else:
        match_quality = "best_possible"

    return {
        "title": entry.get("title") or "Untitled video",
        "artist": entry.get("artist") or entry.get("uploader") or entry.get("channel") or "Unknown uploader",
        "thumbnail": get_best_thumbnail(entry),
        "duration": entry.get("duration"),
        "duration_text": format_duration(entry.get("duration")),
        "url": get_entry_url(entry),
        "channel": entry.get("channel") or entry.get("uploader") or "",
        "match_score": score,
        "match_reason": entry.get("_match_reason", ""),
        "match_quality": match_quality,
        "is_audiobook_hint": is_audiobook_query(search_query),
    }


def filter_youtube_results(entries, track_info):
    """Score all candidate entries and return the best match.

    Three-tier selection:
    1. ``scored_entries``  — score >= MIN_CONFIDENT_MATCH_SCORE (preferred).
    2. ``all_scored``      — any positive score (below-threshold fallback).
    3. ``last_resort``     — variant results (slowed/reverb/etc.) that received
                             a heavy BAD_VARIANT_PENALTY.  Used only when tiers
                             1 and 2 are both empty so we never return "Not
                             Found" when the song clearly exists on YouTube.

    Absolute rejects (score == 0) are excluded from all three tiers.
    """
    scored_entries = []   # tier 1: confident matches
    all_scored = []       # tier 2: below-threshold but positive score
    last_resort = []      # tier 3: variant results (slowed/reverb etc.)

    for entry in entries:
        if not entry:
            continue

        score, reason = score_youtube_result(entry, track_info)

        if score == 0:
            # Absolute reject — skip entirely
            logger.info(
                "[REJECT] title=%r channel=%r score=0 reason=%r",
                entry.get("title", ""),
                entry.get("channel") or entry.get("uploader", ""),
                reason,
            )
            continue

        is_variant = reason.startswith("variant:")

        entry["_match_score"] = score
        entry["_match_reason"] = reason
        entry["_is_variant"] = is_variant

        logger.info(
            "[SCORED] title=%r channel=%r score=%.1f variant=%s reason=%r",
            entry.get("title", ""),
            entry.get("channel") or entry.get("uploader", ""),
            score,
            is_variant,
            reason,
        )

        if is_variant:
            last_resort.append((score, entry))
        elif score >= MIN_CONFIDENT_MATCH_SCORE:
            scored_entries.append((score, entry))
        else:
            all_scored.append((score, entry))

    # Tier 1: confident match
    if scored_entries:
        scored_entries.sort(key=lambda item: item[0], reverse=True)
        best = scored_entries[0][1]
        logger.info(
            "[SELECTED] tier=confident title=%r score=%.1f reason=%r",
            best.get("title"), best["_match_score"], best["_match_reason"],
        )
        return best

    # Tier 2: below-threshold but positive
    if all_scored:
        all_scored.sort(key=lambda item: item[0], reverse=True)
        best = all_scored[0][1]
        logger.warning(
            "[SELECTED] tier=below_threshold title=%r score=%.1f reason=%r",
            best.get("title"), best["_match_score"], best["_match_reason"],
        )
        return best

    # Tier 3: last resort — use a variant (slowed/reverb/etc.) rather than
    # returning None and causing a false 'Not Found'.
    if last_resort:
        last_resort.sort(key=lambda item: item[0], reverse=True)
        best = last_resort[0][1]
        logger.warning(
            "[SELECTED] tier=last_resort (variant) title=%r score=%.1f reason=%r "
            "— no clean version found, using best available match",
            best.get("title"), best["_match_score"], best["_match_reason"],
        )
        return best

    return None


def _infer_title_artist(query):
    """Try to split a plain query like 'Eclipse — octbrfrst' into title + artist.

    Recognises common separators: em-dash (—), en-dash (–), and ' - '.
    Returns a dict suitable for use as ``track_info``, or ``None`` if no
    separator was found.
    """
    # Normalise unicode dashes to a common sentinel before splitting
    normalised = re.sub(r"\s*[\u2013\u2014\u2012\u2015]\s*", " |SEP| ", query)
    # Also handle plain " - " separator (but not single hyphens inside words)
    normalised = re.sub(r"\s+-\s+", " |SEP| ", normalised)

    if "|SEP|" not in normalised:
        return None

    parts = [p.strip() for p in normalised.split("|SEP|", maxsplit=1) if p.strip()]
    if len(parts) != 2:
        return None

    title, artist = parts
    return {"title": title, "artist": artist}


def is_audiobook_query(text):
    """Return True when the search text looks like an audiobook request."""
    normalized = normalize_text(text)
    return any(kw in normalized for kw in AUDIOBOOK_KEYWORDS)


def score_youtube_result(entry, track_info):
    raw_query = " ".join(
        value for value in [
            track_info.get("search_query"),
            track_info.get("artist"),
            track_info.get("title"),
        ]
        if value
    )
    title = normalize_text(entry.get("title") or "")
    channel_raw = entry.get("channel") or entry.get("uploader") or ""
    channel = normalize_text(channel_raw)
    # Strip " - Topic" / " Topic" suffix for artist matching purposes
    channel_base = re.sub(r"\s*-?\s*topic$", "", channel).strip()
    candidate_text = normalize_text(
        f"{entry.get('title') or ''} {channel_raw} {entry.get('uploader') or ''}"
    )
    requested_text = normalize_text(raw_query)
    target_title = normalize_text(track_info.get("title") or raw_query)
    target_artist = normalize_text(track_info.get("artist") or "")
    audiobook_mode = is_audiobook_query(raw_query)

    # --- Absolute rejects (score=0, excluded from all fallback pools) ---
    absolute_blocked = [
        kw for kw in ABSOLUTE_REJECT_KEYWORDS
        if kw in candidate_text and kw not in requested_text
    ]
    if absolute_blocked:
        return 0, f"absolute-reject: {', '.join(absolute_blocked)}"

    if any(keyword in candidate_text for keyword in LOW_QUALITY_KEYWORDS if keyword not in requested_text):
        return 0, "absolute-reject: low-quality upload"

    # Audiobook mode: reject very short results (< 10 min)
    duration_seconds = entry.get("duration") or 0
    if audiobook_mode and duration_seconds and duration_seconds < 600:
        return 0, "absolute-reject: too short for audiobook"

    # --- Variant detection (soft penalty, not hard reject) ---
    # Results with variant keywords get a large score penalty and are moved
    # to the last_resort pool in filter_youtube_results.  They can still
    # be downloaded if no better result exists.
    disallowed = find_disallowed_keywords(candidate_text, requested_text)
    is_variant = bool(disallowed)

    # --- Title scoring ---
    # Strip noise like "Provided to YouTube by ...", artist name, and common
    # marketing suffixes before comparing against the target title.
    comparable_title = strip_common_noise(title, target_artist)
    title_ratio = SequenceMatcher(None, target_title, comparable_title).ratio() if target_title else 0
    token_ratio = token_overlap(target_title, comparable_title)
    score = max(title_ratio, token_ratio) * 48
    reasons = [f"title {round(max(title_ratio, token_ratio) * 100)}%"]

    # Exact prefix bonus: candidate title starts with the target title
    if target_title and comparable_title.startswith(target_title):
        score += 30
        reasons.append("exact prefix")
    elif target_title and title_contains_song_title(comparable_title, target_title):
        score += 18
        reasons.append("title match")

    # How strongly the title alone matches — used to soften artist penalty.
    title_token_ratio = token_overlap(target_title, comparable_title)

    # --- Artist scoring ---
    # Match against the channel name, the base name with " - Topic" stripped,
    # and also the full candidate text.
    if target_artist:
        artist_parts = split_artists(target_artist)
        matched_channel = any(
            artist and (artist in channel or artist in channel_base)
            for artist in artist_parts
        )
        matched_text = any(
            artist and artist in candidate_text
            for artist in artist_parts
        )
        if matched_channel:
            score += 22
            reasons.append("artist channel")
        elif matched_text:
            score += 12
            reasons.append("artist text")
        else:
            # Reduce the penalty when the title tokens fully match — the song
            # clearly exists, just uploaded by a distributor channel whose name
            # doesn't contain the artist (e.g. "Release - Topic").
            if title_token_ratio >= 1.0:
                score -= 8
            else:
                score -= 18
            reasons.append("artist missing")

    # --- Official release bonuses ---
    # "Provided to YouTube by DistroKid" / "Auto-generated by YouTube" uploads
    # from topic channels are the most reliable source — give them a big boost.
    description = normalize_text(entry.get("description") or "")
    is_provided_to_yt = "provided to youtube" in description or "provided to youtube" in title
    is_auto_generated = "auto-generated by youtube" in description

    if is_provided_to_yt or is_auto_generated:
        score += 25
        reasons.append("official distro upload")
    elif any(pattern in title for pattern in OFFICIAL_AUDIO_PATTERNS):
        score += 18
        reasons.append("official audio")
    elif any(pattern in title for pattern in OFFICIAL_VIDEO_PATTERNS):
        score += 14
        reasons.append("official video")

    # YouTube Music topic channels are highly reliable
    if channel.endswith(" topic") or channel.endswith(" - topic"):
        score += 20
        reasons.append("topic channel")

    # Verified channel bonus
    if entry.get("channel_is_verified"):
        score += 12
        reasons.append("verified")

    # Official-sounding channel name bonus
    official_channel_signals = ("vevo", "records", "music", "official", "entertainment")
    if any(sig in channel for sig in official_channel_signals):
        score += 8
        reasons.append("official channel")

    # Audiobook-specific bonuses
    if audiobook_mode:
        if duration_seconds >= 3600:  # >= 1 hour
            score += 25
            reasons.append("audiobook long duration")
        elif duration_seconds >= 600:  # >= 10 min but < 1 hour
            score += 5
            reasons.append("audiobook medium duration")

        audiobook_channel_signals = ("audiobook", "audio book", "books", "stories", "readings", "narrated")
        if any(sig in channel for sig in audiobook_channel_signals):
            score += 15
            reasons.append("audiobook channel")

    # --- Duration match (for music tracks with known Spotify duration) ---
    duration_score = score_duration(entry.get("duration"), track_info.get("duration_ms"))
    if duration_score is None:
        pass
    elif duration_score < 0:
        # Duration is way off — heavy penalty but NOT an absolute reject.
        # Some legitimate uploads have slightly different edits.
        score -= 30
        reasons.append("duration mismatch")
    else:
        score += duration_score
        reasons.append("duration close")

    # Apply variant penalty last so it overrides everything else.
    if is_variant:
        score -= BAD_VARIANT_PENALTY * len(disallowed)
        reasons = [f"variant: {', '.join(disallowed)}"] + reasons
        # Ensure variants never reach MIN_CONFIDENT_MATCH_SCORE naturally
        score = min(score, MIN_CONFIDENT_MATCH_SCORE - 1)

    return score, ", ".join(reasons)


def download_audio_from_search(search_query, output_folder, track_info=None):
    """Search YouTube and download the best matching original audio result."""
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
    apply_ffmpeg_location(options)

    try:
        with YoutubeDL(options) as ydl:
            if track_info:
                best_entry = search_youtube_match(search_query, track_info=track_info)
                return ydl.extract_info(best_entry["webpage_url"], download=True)
            else:
                best_entry = search_youtube_match(search_query, track_info={"title": search_query})
                return ydl.extract_info(best_entry["webpage_url"], download=True)
    except DownloadError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc
    except ExtractorError as exc:
        raise DownloadFailed(get_download_error_message(exc)) from exc


def download_video(url, output_folder, quality, progress_callback=None):
    """Download a clean MP4 video at or below the selected quality."""
    output_folder = Path(output_folder)
    max_height = int(quality)
    fallback_heights = [height for height in (max_height, 1080, 720, 480, 360) if height <= max_height]
    fallback_heights = list(dict.fromkeys(fallback_heights))

    errors = []
    last_info = None

    for attempt, height in enumerate(fallback_heights, start=1):
        if progress_callback:
            progress_callback(
                {
                    "status": "starting",
                    "message": f"Selecting video format up to {height}p",
                    "fallback_attempt": attempt,
                    "fallback_quality": height,
                }
            )

        output_template = str(output_folder / f"source-{height}p.%(ext)s")
        options = build_video_download_options(height, output_template, progress_callback)

        try:
            with YoutubeDL(options) as ydl:
                last_info = ydl.extract_info(url, download=True)
                return last_info
        except (DownloadError, ExtractorError) as exc:
            message = get_download_error_message(exc)
            errors.append(f"{height}p: {message}")
            if progress_callback:
                progress_callback(
                    {
                        "status": "fallback",
                        "message": f"{height}p failed. Trying the next stable format...",
                        "error": message,
                        "fallback_attempt": attempt,
                        "fallback_quality": height,
                    }
                )

    if errors:
        raise DownloadFailed("All MP4 format attempts failed. " + " | ".join(errors))

    raise DownloadFailed("The video could not be downloaded. Check the link and try again.")


def build_video_download_options(max_height, output_template, progress_callback=None):
    def download_hook(data):
        if progress_callback:
            progress_callback(format_download_progress(data))

    def postprocessor_hook(data):
        if not progress_callback:
            return

        status = data.get("status")
        if status in {"started", "processing"}:
            progress_callback({"status": "processing", "message": "Processing audio/video merge"})
        elif status == "finished":
            progress_callback({"status": "processing", "message": "Audio/video merge complete"})

    options = {
        "format": (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}][ext=mp4]/"
            f"best[height<={max_height}]/"
            "best[ext=mp4]/best"
        ),
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        "extractor_retries": 5,
        "socket_timeout": 60,
        "http_chunk_size": 10 * 1024 * 1024,
        "concurrent_fragment_downloads": 1,
        "progress_hooks": [download_hook],
        "postprocessor_hooks": [postprocessor_hook],
    }
    apply_ffmpeg_location(options, required=True)
    return options


def format_download_progress(data):
    status = data.get("status")
    total = data.get("total_bytes") or data.get("total_bytes_estimate")
    downloaded = data.get("downloaded_bytes") or 0
    percent = None

    if total:
        percent = min(100, max(0, (downloaded / total) * 100))

    if status == "finished":
        return {
            "status": "processing",
            "percent": 100,
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "message": "Download complete. Processing audio/video merge",
        }

    if status == "downloading":
        return {
            "status": "downloading",
            "percent": percent,
            "speed": data.get("speed"),
            "eta": data.get("eta"),
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "message": "Downloading video",
        }

    if status == "error":
        return {"status": "error", "message": "Download error. Retrying if possible..."}

    return {"status": status or "downloading", "message": "Downloading video"}


def get_video_preview(url):
    """Fetch video title, uploader, and thumbnail without downloading media."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    apply_ffmpeg_location(options)

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
        "duration": info.get("duration"),
        "duration_text": format_duration(info.get("duration")),
    }


def get_entry_url(entry):
    return entry.get("webpage_url") or entry.get("url") or ""


def normalize_text(value):
    # Replace em-dash/en-dash/figure-dash with a plain hyphen-space so that
    # "Eclipse — octbrfrst" doesn't collapse into one unrecognisable token.
    value = str(value or "")
    value = re.sub(r"[\u2013\u2014\u2012\u2015]", " - ", value)
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[\[\](){}|:;\"'`]", " ", value)
    value = re.sub(r"[^a-z0-9+\s.-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def strip_common_noise(title, artist=""):
    cleaned = normalize_text(title)
    artist = normalize_text(artist)
    if artist:
        for part in split_artists(artist):
            cleaned = re.sub(rf"(^|\s){re.escape(part)}(\s|$)", " ", cleaned)

    noise = [
        "provided to youtube by",
        "auto-generated by youtube",
        "official audio",
        "official video",
        "official music video",
        "music video",
        "audio",
        "video",
        "hd",
        "hq",
        "4k",
        "topic",
    ]
    for item in noise:
        cleaned = re.sub(rf"(^|\s){re.escape(item)}(\s|$)", " ", cleaned)

    # Remove anything after " - " that looks like a distributor/label suffix
    # e.g. "Eclipse - octbrfrst" keeps both parts but
    # "Song Title - Record Label Music" trims the label.
    # We only do this when the remaining prefix still contains the target title.
    cleaned = re.sub(r"\s+-\s+released by .+$", "", cleaned)

    return re.sub(r"\s+", " ", cleaned).strip()


def split_artists(artist):
    artist = normalize_text(artist)
    return [
        part.strip()
        for part in re.split(r"\s*(?:,|/|&|\band\b|\bfeat\b|\bft\b|\bfeaturing\b)\s*", artist)
        if part.strip()
    ]


def find_disallowed_keywords(candidate_text, requested_text):
    blocked = []
    for keyword in BAD_VARIANT_KEYWORDS:
        if keyword in candidate_text and keyword not in requested_text:
            blocked.append(keyword)
    return blocked


def token_overlap(expected, actual):
    expected_tokens = significant_tokens(expected)
    actual_tokens = significant_tokens(actual)
    if not expected_tokens:
        return 0
    return len(expected_tokens & actual_tokens) / len(expected_tokens)


def significant_tokens(value):
    stop_words = {"the", "a", "an", "and", "or", "to", "of", "from", "with", "feat", "ft", "official", "audio", "video"}
    return {
        token for token in normalize_text(value).split()
        if len(token) > 1 and token not in stop_words
    }


def title_contains_song_title(candidate, target):
    candidate_tokens = significant_tokens(candidate)
    target_tokens = significant_tokens(target)
    if not target_tokens:
        return False
    return target_tokens.issubset(candidate_tokens)


def score_duration(duration_seconds, expected_ms):
    if not duration_seconds or not expected_ms:
        return None

    expected_seconds = expected_ms / 1000
    diff = abs(duration_seconds - expected_seconds)
    hard_limit = max(18, expected_seconds * 0.18)
    if diff > hard_limit:
        return -1
    if diff <= max(5, expected_seconds * 0.04):
        return 12
    if diff <= max(10, expected_seconds * 0.08):
        return 7
    return 2


def format_duration(seconds):
    if not seconds:
        return ""
    seconds = int(seconds)
    minutes, remaining = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remaining:02d}"
    return f"{minutes}:{remaining:02d}"


def apply_ffmpeg_location(options, required=False):
    """Tell yt-dlp exactly where FFmpeg lives instead of relying on PATH."""
    ffmpeg_location = get_ffmpeg_location()
    if ffmpeg_location:
        logger.info("Using FFmpeg from: %s", ffmpeg_location)
        options["ffmpeg_location"] = ffmpeg_location
        return options

    if required:
        raise DownloadFailed(
            "FFmpeg is required for MP4 merging but was not found. Install it at "
            "C:\\ffmpeg\\bin\\ffmpeg.exe, place it in tools/ffmpeg/bin, or add ffmpeg.exe to PATH."
        )

    logger.warning("FFmpeg location was not found; yt-dlp will run without ffmpeg_location.")
    return options


def get_best_thumbnail(info):
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        best = max(thumbnails, key=lambda item: item.get("width") or 0)
        if best.get("url"):
            return best["url"]

    return info.get("thumbnail") or ""


def get_download_error_message(error):
    """Turn yt-dlp errors into short messages that make sense in the UI."""
    raw_text = str(error)
    text = raw_text.lower()

    if "ffmpeg" in text:
        return f"FFmpeg failed while merging the audio and video: {raw_text}"

    if "timed out" in text or "timeout" in text:
        return "The network connection timed out while downloading. TuneLift retried automatically, but the download still failed."

    if "fragment" in text or "connection" in text or "reset" in text:
        return "The network connection was interrupted while downloading. TuneLift retried automatically, but the download still failed."

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

    complete_videos = [
        path for path in videos
        if path.stat().st_size > 0 and not Path(f"{path}.part").exists()
    ]

    if not complete_videos:
        return None

    return max(complete_videos, key=lambda path: path.stat().st_size)
