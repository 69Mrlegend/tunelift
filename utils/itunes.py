import json
import logging
from urllib.request import Request, urlopen
from urllib.parse import quote

logger = logging.getLogger(__name__)

def search_itunes_track(query):
    """Search iTunes for a track and return its metadata as a fallback."""
    if not query:
        return None
        
    encoded_query = quote(query, safe="")
    search_url = f"https://itunes.apple.com/search?term={encoded_query}&entity=song&limit=1"
    
    request = Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
    
    try:
        with urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
            results = data.get("results", [])
            
            if not results:
                return None
                
            track = results[0]
            
            # iTunes artwork is usually 100x100, replace with 600x600 for high quality MP3 covers
            thumbnail = track.get("artworkUrl100", "")
            if thumbnail:
                thumbnail = thumbnail.replace("100x100bb", "600x600bb")
                
            artist = track.get("artistName", "")
            title = track.get("trackName", "")
            
            return {
                "title": title,
                "artist": artist,
                "thumbnail": thumbnail,
                "search_query": f"{artist} {title} Official Audio",
                "album_name": track.get("collectionName") or "Single",
                "duration_ms": track.get("trackTimeMillis"),
            }
    except Exception as exc:
        logger.warning("iTunes search failed for query %r: %s", query, exc)
        return None
