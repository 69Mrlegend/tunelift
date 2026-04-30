import json
import os
import logging
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class SpotifyError(Exception):
    """Raised when Spotify track details cannot be loaded."""

logger = logging.getLogger(__name__)


def is_spotify_url(url):
    return get_spotify_url_type(url) in {"track", "playlist"}


def is_spotify_track_url(url):
    return get_spotify_url_type(url) == "track"


def is_spotify_playlist_url(url):
    return get_spotify_url_type(url) == "playlist"

def normalize_spotify_url(url):
    """Normalize common Spotify share URLs into open.spotify.com URLs.

    Handles:
    - www.open.spotify.com (not always accepted by strict parsers)
    - spotify.link / spotify.app.link shortlinks (via redirects)
    """
    raw = (url or "").strip()
    if not raw:
        return raw

    try:
        parsed = urlparse(raw)
    except ValueError:
        return raw

    host = parsed.netloc.lower().split(":")[0]
    if host in {"open.spotify.com", "spotify.com", "www.open.spotify.com", "www.spotify.com"}:
        return raw

    # Follow redirects for Spotify shortlinks (best-effort).
    if host.endswith("spotify.link") or host.endswith("spotify.app.link"):
        request = Request(raw, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=12) as response:
                final_url = getattr(response, "geturl", lambda: raw)()
                return final_url or raw
        except Exception:
            return raw

    return raw


def get_spotify_url_type(url):
    url = normalize_spotify_url(url)
    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    if parsed.scheme == "spotify":
        parts = [part for part in parsed.path.split(":") if part]
        if parsed.netloc in {"track", "playlist"} and parts:
            return parsed.netloc
        if len(parts) >= 2 and parts[0] in {"track", "playlist"}:
            return parts[0]
        return None

    host = parsed.netloc.lower().split(":")[0]
    path_parts = [part for part in parsed.path.split("/") if part]

    if parsed.scheme not in {"http", "https"}:
        return None

    if host not in {"spotify.com", "open.spotify.com", "www.spotify.com", "www.open.spotify.com"}:
        return None

    entity = find_spotify_entity(path_parts)
    if entity:
        return entity[0]

    return None


def get_spotify_id(url, expected_type):
    url = normalize_spotify_url(url)
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise SpotifyError("Please paste a valid Spotify link.") from exc

    if parsed.scheme == "spotify":
        parts = [part for part in parsed.path.split(":") if part]
        if parsed.netloc == expected_type and parts:
            return parts[0]
        if len(parts) >= 2 and parts[0] == expected_type:
            return parts[1]

    path_parts = [part for part in parsed.path.split("/") if part]
    entity = find_spotify_entity(path_parts)
    if not entity or entity[0] != expected_type:
        raise SpotifyError(f"Please paste a valid Spotify {expected_type} link.")

    return entity[1]


def find_spotify_entity(path_parts):
    for index, part in enumerate(path_parts):
        if part in {"track", "playlist"} and index + 1 < len(path_parts):
            return part, path_parts[index + 1]
    return None


def get_spotify_track_info(url):
    """Read public Spotify embed data without requiring API credentials."""
    url = normalize_spotify_url(url)
    if not is_spotify_track_url(url):
        raise SpotifyError("Please paste a valid Spotify track link.")

    endpoint = f"https://open.spotify.com/oembed?url={quote(url, safe='')}"
    request = Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise SpotifyError("Could not read that Spotify link. Check the link and try again.") from exc

    title, artist = parse_spotify_title(data.get("title", ""))

    return {
        "title": title,
        "artist": artist,
        "thumbnail": data.get("thumbnail_url") or "",
        "search_query": build_search_query(title, artist),
    }


def get_spotify_playlist_info(url):
    """Read playlist name and tracks using the Spotify Web API."""
    url = normalize_spotify_url(url)
    playlist_id = get_spotify_id(url, "playlist")
    logger.info("spotify.playlist_info url=%r playlist_id=%r", url, playlist_id)

    token = get_spotify_access_token()
    playlist_url = (
        f"https://api.spotify.com/v1/playlists/{playlist_id}"
        "?fields=name,images,tracks(total,items(track(name,artists(name),album(images))),next)"
    )
    playlist = spotify_api_get(playlist_url, token)

    tracks = parse_playlist_tracks(playlist.get("tracks", {}).get("items", []))
    next_url = playlist.get("tracks", {}).get("next")

    while next_url:
        page = spotify_api_get(next_url, token)
        tracks.extend(parse_playlist_tracks(page.get("items", [])))
        next_url = page.get("next")

    if not tracks:
        raise SpotifyError("That playlist does not contain downloadable tracks.")

    result = {
        "name": playlist.get("name") or "Spotify Playlist",
        "thumbnail": get_largest_image_url(playlist.get("images") or []),
        "total": len(tracks),
        "tracks": tracks,
    }
    logger.info(
        "spotify.playlist_info response playlist_id=%r name=%r total=%s parsed_tracks=%s",
        playlist_id,
        result["name"],
        playlist.get("tracks", {}).get("total"),
        len(tracks),
    )
    return result


def get_spotify_access_token():
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.warning(
            "spotify.auth missing_credentials client_id_present=%s client_secret_present=%s",
            bool(client_id),
            bool(client_secret),
        )
        raise SpotifyError("Spotify playlist downloads require SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.")

    body = "grant_type=client_credentials".encode("utf-8")
    request = Request(
        "https://accounts.spotify.com/api/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    import base64

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    request.add_header("Authorization", f"Basic {credentials}")

    try:
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise SpotifyError("Could not authenticate with Spotify. Check your API credentials.") from exc

    return data["access_token"]


def spotify_api_get(url, token):
    request = Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        logger.error("spotify.api http_error url=%r status=%s body=%r", url, getattr(exc, "code", None), body[:2000])
        raise SpotifyError(f"Spotify API error ({getattr(exc, 'code', 'unknown')}): {body or 'No response body'}") from exc
    except URLError as exc:
        logger.error("spotify.api url_error url=%r reason=%r", url, getattr(exc, "reason", None))
        raise SpotifyError("Network error while contacting Spotify.") from exc
    except Exception as exc:
        logger.exception("spotify.api unexpected_error url=%r", url)
        raise SpotifyError("Could not read playlist details from Spotify.") from exc


def parse_playlist_tracks(items):
    tracks = []

    for item in items:
        track = item.get("track") or {}
        title = track.get("name")
        artists = ", ".join(artist.get("name", "") for artist in track.get("artists", []) if artist.get("name"))

        if not title or not artists:
            continue

        tracks.append(
            {
                "title": title,
                "artist": artists,
                "thumbnail": get_largest_image_url(track.get("album", {}).get("images") or []),
                "search_query": build_search_query(title, artists),
            }
        )

    return tracks


def get_largest_image_url(images):
    if not images:
        return ""

    best = max(images, key=lambda image: image.get("width") or 0)
    return best.get("url") or ""


def parse_spotify_title(raw_title):
    title = cleanup_title(raw_title) or "Spotify Track"
    artist = ""

    if " - " in title:
        left, right = title.split(" - ", 1)
        if left and right:
            title = left.strip()
            artist = right.strip()
    elif " by " in title.lower():
        parts = title.split(" by ", 1)
        if len(parts) == 2:
            title = parts[0].strip()
            artist = parts[1].strip()

    return title or "Spotify Track", artist


def cleanup_title(raw_title):
    title = raw_title.replace(" | Spotify", "").replace("Spotify", "").strip()
    title = title.strip(" -")
    return title


def build_search_query(title, artist):
    if artist:
        return f"{artist} {title} audio"
    return f"{title} audio"


def download_cover_image(image_url, output_folder):
    if not image_url:
        return None

    output_path = Path(output_folder) / "spotify-cover.jpg"
    request = Request(image_url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=12) as response:
            output_path.write_bytes(response.read())
    except Exception:
        return None

    return output_path if output_path.exists() else None
