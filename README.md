# YouTube to MP3 Flask App

A beginner-friendly Flask web app that downloads YouTube videos as MP3/MP4 files, turns Spotify links into tagged MP3 files, and supports bulk song lists.

The app uses:

- `yt-dlp` to download the best available audio and thumbnail.
- `ffmpeg` to convert the audio into a 320 kbps MP3.
- `mutagen` to add title, artist, album name, and thumbnail cover art metadata.
- `yt-dlp` and FFmpeg to download clean MP4 video files at 360p, 720p, or 1080p.
- Spotify public embed data to read song title, artist, and album cover, then `yt-dlp` to find matching YouTube audio.
- Spotify Web API credentials to read playlist names, tracks, artists, and album covers.
- Bulk song lists from pasted text or `.txt` files, downloaded one by one and returned as a ZIP.
- HTML, CSS, and JavaScript for a clean frontend.

Only download videos you own, have permission to use, or that are legally available for this purpose.

## Project Structure

```text
mp3/
  app.py                 Flask routes and web responses
  converter.py           Coordinates the conversion workflow
  requirements.txt       Python packages
  utils/
    downloader.py        yt-dlp download helpers
    converter.py         FFmpeg audio and thumbnail conversion helpers
    metadata.py          Mutagen MP3 title, artist, and cover art helpers
    bulk.py              Bulk song list parsing helpers
    spotify.py           Spotify track metadata and cover art helpers
  templates/
    index.html           Main web page
  static/
    css/
      styles.css         Page styling
    js/
      app.js             Loading state behavior
  downloads/             Temporary conversion files, ignored by git
```

## Requirements

- Python 3.10 or newer
- FFmpeg installed and available on your `PATH`, or the included portable FFmpeg at `tools/ffmpeg/bin/ffmpeg.exe`
- Spotify playlist downloads require `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`

Check FFmpeg:

```powershell
.\tools\ffmpeg\bin\ffmpeg.exe -version
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
flask --app app run
```

Open http://127.0.0.1:5000 in your browser.

## Spotify Playlist Setup

Create a Spotify app in the Spotify Developer Dashboard, then set:

```powershell
$env:SPOTIFY_CLIENT_ID="your-client-id"
$env:SPOTIFY_CLIENT_SECRET="your-client-secret"
```

Single Spotify track downloads can still use public embed data, but playlist downloads need Spotify API credentials.

## How It Works

1. Choose MP3 Audio, MP4 Video, Spotify Music, or Bulk Downloader.
2. Paste a YouTube video URL, Spotify track URL, or Spotify playlist URL into the form.
3. For MP3, `yt-dlp` downloads the best audio stream and thumbnail, `ffmpeg` converts it to 320 kbps MP3, and `mutagen` writes title, artist, and cover art.
4. For MP4, `yt-dlp` downloads a clean video file at the selected quality.
5. For a Spotify track, the app reads song info, searches YouTube for a matching audio result, converts it to MP3, and writes Spotify title, artist, and cover art.
6. For a Spotify playlist, the app reads every track with the Spotify API, downloads each matched YouTube audio result as MP3, embeds metadata, puts the songs in a playlist-named folder, and returns a ZIP.
7. For Bulk Downloader, paste song names line by line or upload a `.txt` file. The app searches YouTube, converts each match to 320 kbps MP3, embeds metadata and cover art when available, then returns one ZIP.
8. Flask sends the finished file as a download and removes the temporary files.
