const form = document.querySelector("[data-converter-form]");
const input = document.querySelector("[data-url-input]");
const button = document.querySelector("[data-submit-button]");
const submitButtons = document.querySelectorAll("button[type='submit']");
const buttonText = document.querySelector("[data-button-text]");
const statusText = document.querySelector("[data-status-text]");
const previewArt = document.querySelector("[data-preview-art]");
const previewImage = document.querySelector("[data-preview-image]");
const previewPlaceholder = document.querySelector("[data-preview-placeholder]");
const previewTitle = document.querySelector("[data-preview-title]");
const previewArtist = document.querySelector("[data-preview-artist]");
const previewStatus = document.querySelector("[data-preview-status]");
const urlLabel = document.querySelector("[data-url-label]");
const urlControls = document.querySelectorAll("[data-url-control]");
const formatOptions = document.querySelectorAll("[data-format-option]");
const qualityRow = document.querySelector("[data-quality-row]");
const qualitySelect = document.querySelector("[data-quality-select]");
const qualityPill = document.querySelector("[data-quality-pill]");
const modeEyebrow = document.querySelector("[data-mode-eyebrow]");
const modeTitle = document.querySelector("[data-mode-title]");
const modeCopy = document.querySelector("[data-mode-copy]");
const featureOne = document.querySelector("[data-feature-one]");
const featureTwo = document.querySelector("[data-feature-two]");
const featureThree = document.querySelector("[data-feature-three]");
const playlistProgress = document.querySelector("[data-playlist-progress]");
const playlistName = document.querySelector("[data-playlist-name]");
const playlistCount = document.querySelector("[data-playlist-count]");
const playlistMessage = document.querySelector("[data-playlist-message]");
const playlistBar = document.querySelector("[data-playlist-bar]");
const playlistPanel = document.querySelector("[data-playlist-panel]");
const playlistCover = document.querySelector("[data-playlist-cover-image]");
const playlistTitle = document.querySelector("[data-playlist-title]");
const playlistSubtitle = document.querySelector("[data-playlist-subtitle]");
const playlistTracks = document.querySelector("[data-playlist-tracks]");
const playlistProgressRow = document.querySelector("[data-playlist-progress-row]");
const playlistProgressBar = document.querySelector("[data-playlist-progress-bar]");
const playlistPercent = document.querySelector("[data-playlist-percent]");
const playlistProgressText = document.querySelector("[data-playlist-progress-text]");
const playlistDone = document.querySelector("[data-playlist-done]");
const playlistDownloadLink = document.querySelector("[data-playlist-download-link]");
const bulkRow = document.querySelector("[data-bulk-row]");
const bulkSongs = document.querySelector("[data-bulk-songs]");
const bulkFile = document.querySelector("[data-bulk-file]");

let previewTimer;
let previewController;
let playlistDetailsController;
let lastPlaylistDetailsUrl = "";
let preparedPlaylistJobId = "";

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selectedFormat = getSelectedFormat();
    const formData = new FormData(form);

    form.classList.add("is-loading");
    setSubmitButtonsDisabled(true);
    input.readOnly = true;
    buttonText.textContent = selectedFormat === "mp4" ? "Downloading" : "Converting";
    statusText.textContent = getLoadingStatus();

    try {
      if (selectedFormat === "bulk") {
        await startBulkDownload(formData);
        return;
      }

      if (isSpotifyPlaylist(input.value.trim())) {
        await startPlaylistDownload(formData);
        return;
      }

      const conversionRequest = fetch(form.action || window.location.href, {
        method: "POST",
        body: formData,
      });

      resetAfterConversionStarts();

      const response = await conversionRequest;
      if (!response.ok) {
        const message = await getErrorMessage(response);
        showConversionError(message);
        return;
      }

      const downloadBlob = await response.blob();
      startBrowserDownload(downloadBlob, getDownloadName(response));
    } catch (error) {
      showConversionError("Something went wrong. Check the link and try again.");
    }
  });
}

if (formatOptions.length) {
  formatOptions.forEach((option) => {
    option.addEventListener("change", updateFormatControls);
  });
  qualitySelect.addEventListener("change", updateFormatControls);
  updateFormatControls();
}

if (input) {
  input.addEventListener("input", () => {
    window.clearTimeout(previewTimer);

    const url = input.value.trim();
    if (!url) {
      resetPreview();
      return;
    }

    setInstantThumbnail(url);
    previewTimer = window.setTimeout(() => updatePreview(url), 550);
  });

  if (input.value.trim()) {
    updatePreview(input.value.trim());
  }
}

if (bulkSongs) {
  bulkSongs.addEventListener("input", updateBulkPreviewPanel);
}

if (bulkFile) {
  bulkFile.addEventListener("change", handleBulkFileChange);
}

async function updatePreview(url) {
  if (isSpotifyPlaylist(url)) {
    setPreviewLoading();
    await loadPlaylistDetails(url);
    return;
  }

  if (previewController) {
    previewController.abort();
  }

  previewController = new AbortController();

  try {
    const response = await fetch(`/preview?url=${encodeURIComponent(url)}&download_type=${getSelectedFormat()}`, {
      signal: previewController.signal,
    });
    const data = await response.json();

    if (!response.ok || !data.ok) {
      setPreviewError(data.message || "Preview unavailable");
      hidePlaylistPanel();
      return;
    }

    setPreviewData(data.video);

    hidePlaylistPanel();
  } catch (error) {
    if (error.name !== "AbortError") {
      setPreviewError("Preview unavailable");
      hidePlaylistPanel();
    }
  }
}

function resetPreview() {
  const selectedFormat = getSelectedFormat();
  previewArt.classList.remove("has-image", "is-loading", "has-error");
  previewImage.removeAttribute("src");
  previewImage.alt = "";
  previewPlaceholder.hidden = false;
  if (selectedFormat === "bulk") {
    previewTitle.textContent = "Bulk Songs";
    previewArtist.textContent = "Paste song names or upload a text file";
  } else if (selectedFormat === "spotify") {
    previewTitle.textContent = "Paste a Spotify link";
    previewArtist.textContent = "Song, artist, or playlist details will appear here";
  } else {
    previewTitle.textContent = "Paste a YouTube link";
    previewArtist.textContent = "Video title and uploader will appear here";
  }
  previewStatus.textContent = "Ready to convert";
}

function resetAfterConversionStarts() {
  window.clearTimeout(previewTimer);

  if (previewController) {
    previewController.abort();
  }

  form.classList.remove("is-loading");
  setSubmitButtonsDisabled(false);
  input.readOnly = false;
  input.disabled = getSelectedFormat() === "bulk";
  input.value = "";
  buttonText.textContent = "Convert";
  statusText.textContent = getDefaultStatus();
  playlistProgress.hidden = true;
  hidePlaylistPanel();
  resetPreview();
}

function setInstantThumbnail(url) {
  if (getSelectedFormat() === "spotify") {
    setPreviewLoading();
    return;
  }

  const videoId = getYouTubeVideoId(url);

  if (!videoId) {
    setPreviewLoading();
    return;
  }

  previewArt.classList.add("has-image", "is-loading");
  previewArt.classList.remove("has-error");
  previewImage.src = `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
  previewImage.alt = "YouTube video thumbnail";
  previewPlaceholder.hidden = true;
  previewTitle.textContent = "Finding video...";
  previewArtist.textContent = "Reading YouTube metadata";
  previewStatus.textContent = "Preview loading";
}

function getYouTubeVideoId(url) {
  try {
    const parsedUrl = new URL(url);
    const host = parsedUrl.hostname.replace(/^www\./, "");

    if (host === "youtu.be") {
      return parsedUrl.pathname.split("/").filter(Boolean)[0] || "";
    }

    if (host.endsWith("youtube.com")) {
      const watchId = parsedUrl.searchParams.get("v");
      if (watchId) {
        return watchId;
      }

      const parts = parsedUrl.pathname.split("/").filter(Boolean);
      if (["shorts", "live", "embed"].includes(parts[0])) {
        return parts[1] || "";
      }
    }
  } catch (error) {
    return "";
  }

  return "";
}

function startBrowserDownload(blob, fileName) {
  const downloadUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = downloadUrl;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();

  window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
}

async function startPlaylistDownload(formData) {
  const url = input.value.trim();
  await loadPlaylistDetails(url);

  if (!preparedPlaylistJobId) {
    showConversionError("Load playlist details before starting the download.");
    return;
  }

  const startFormData = new FormData();
  startFormData.set("job_id", preparedPlaylistJobId);

  const startResponse = await fetch("/spotify-playlist/start", {
    method: "POST",
    body: startFormData,
  });
  const startData = await safeReadJson(startResponse);

  if (!startResponse.ok || !startData.ok) {
    showConversionError(startData.message || "Could not start playlist download.");
    return;
  }

  playlistProgress.hidden = true;
  playlistPanel.hidden = false;
  if (playlistDone) {
    playlistDone.hidden = true;
  }
  playlistProgressRow.hidden = false;
  playlistProgressText.hidden = false;
  setPlaylistProgressUi({ current: 0, total: getRenderedTrackCount(), message: "Preparing playlist" });

  await pollPlaylistProgress(startData.job_id);
}

async function startBulkDownload(formData) {
  const startResponse = await fetch("/bulk/start", {
    method: "POST",
    body: formData,
  });
  const startData = await safeReadJson(startResponse);

  if (!startResponse.ok || !startData.ok) {
    showConversionError(startData.message || "Could not start bulk download.");
    return;
  }

  const bulk = startData.bulk || {};
  playlistProgress.hidden = true;
  playlistPanel.hidden = false;
  if (playlistDone) {
    playlistDone.hidden = true;
  }
  setPlaylistHeader({
    name: bulk.name || "Bulk Songs",
    thumbnail: "",
    total: bulk.total || 0,
  });
  renderPlaylistTracks(bulk.tracks || [], null);
  setPlaylistProgressUi({ current: 0, total: bulk.total || 0, message: "Preparing bulk download" });
  setPreviewData({
    title: "Bulk Songs",
    artist: `${bulk.total || 0} songs queued`,
    thumbnail: "",
    kind: "playlist",
    total: bulk.total || 0,
  });
  resetBulkInputsOnly();

  await pollBulkProgress(startData.job_id);
}

async function pollBulkProgress(jobId) {
  const response = await fetch(`/bulk/progress/${jobId}`);
  const data = await safeReadJson(response);

  if (!response.ok || !data.ok) {
    showConversionError(data.message || "Could not read bulk progress.");
    return;
  }

  updatePlaylistProgress(data);

  if (data.status === "complete") {
    if (playlistDone) {
      playlistDone.hidden = false;
    }
    if (playlistDownloadLink) {
      playlistDownloadLink.href = data.download_url;
    }
    statusText.textContent = "Download Complete";
    resetAfterPlaylistDownloadStarts();
    return;
  }

  if (data.status === "error") {
    showConversionError(data.error || "Bulk download failed.");
    return;
  }

  window.setTimeout(() => pollBulkProgress(jobId), 1200);
}

async function pollPlaylistProgress(jobId) {
  const response = await fetch(`/spotify-playlist/progress/${jobId}`);
  const data = await safeReadJson(response);

  if (!response.ok || !data.ok) {
    showConversionError(data.message || "Could not read playlist progress.");
    return;
  }

  updatePlaylistProgress(data);

  if (data.status === "complete") {
    if (playlistDone) {
      playlistDone.hidden = false;
    }
    if (playlistDownloadLink) {
      playlistDownloadLink.href = data.download_url;
    }
    statusText.textContent = "Download Complete";
    resetAfterPlaylistDownloadStarts();
    return;
  }

  if (data.status === "error") {
    showConversionError(data.error || "Playlist download failed.");
    return;
  }

  window.setTimeout(() => pollPlaylistProgress(jobId), 1200);
}

function updatePlaylistProgress(data) {
  const total = data.total || 0;
  const current = data.current || 0;
  const message = data.total ? `Downloading ${current} of ${total} songs` : data.message;
  const displayName = data.playlist_name || "Spotify Playlist";

  if (playlistPanel && !playlistPanel.hidden) {
    setPlaylistHeader({
      name: displayName,
      thumbnail: data.playlist_thumbnail || "",
      total,
    });
    setPlaylistProgressUi({ current, total, message });
    renderPlaylistTracks(data.tracks || [], data.active_index);
  } else {
    playlistProgress.hidden = false;
    playlistName.textContent = displayName;
    playlistCount.textContent = `${total} songs`;
    playlistMessage.textContent = message;
    playlistBar.max = total || 100;
    playlistBar.value = current || 0;
  }

  statusText.textContent = data.message || message;
}

function startBrowserDownloadFromUrl(url) {
  const link = document.createElement("a");
  link.href = url;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function resetAfterPlaylistDownloadStarts() {
  form.classList.remove("is-loading");
  setSubmitButtonsDisabled(false);
  input.readOnly = false;
  input.disabled = getSelectedFormat() === "bulk";
  buttonText.textContent = "Convert";
  statusText.textContent = "Download Complete";
  playlistProgress.hidden = true;
  if (playlistProgressRow) {
    playlistProgressRow.hidden = false;
  }
  if (playlistProgressText) {
    playlistProgressText.hidden = false;
  }
}

function getDownloadName(response) {
  const header = response.headers.get("Content-Disposition") || "";
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  const regularMatch = header.match(/filename="?([^"]+)"?/i);

  if (utf8Match) {
    return decodeURIComponent(utf8Match[1]);
  }

  if (regularMatch) {
    return regularMatch[1];
  }

  return getSelectedFormat() === "mp4" ? "youtube-video.mp4" : "youtube-audio.mp3";
}

async function getErrorMessage(response) {
  const html = await response.text();
  const page = new DOMParser().parseFromString(html, "text/html");
  const alert = page.querySelector(".alert");

  return alert ? alert.textContent.trim() : "Conversion failed. Check the link and try again.";
}

function showConversionError(message) {
  form.classList.remove("is-loading");
  setSubmitButtonsDisabled(false);
  input.readOnly = false;
  input.disabled = getSelectedFormat() === "bulk";
  buttonText.textContent = "Convert";
  statusText.textContent = message;
  playlistProgress.hidden = true;
  hidePlaylistPanel();
}

function updateFormatControls() {
  const selectedFormat = getSelectedFormat();
  const isVideo = selectedFormat === "mp4";
  const isSpotify = selectedFormat === "spotify";
  const isBulk = selectedFormat === "bulk";

  qualityRow.hidden = !isVideo;
  if (bulkRow) {
    bulkRow.hidden = !isBulk;
  }
  urlControls.forEach((control) => {
    control.hidden = isBulk;
  });
  input.required = !isBulk;
  input.disabled = isBulk;
  qualityPill.textContent = getQualityPillText();
  modeEyebrow.textContent = getModeEyebrow();
  modeTitle.textContent = getModeTitle();
  modeCopy.textContent = getModeCopy();
  urlLabel.textContent = isSpotify ? "Spotify track URL" : "YouTube video URL";
  input.placeholder = isSpotify
    ? "https://open.spotify.com/track/... or /playlist/..."
    : "https://www.youtube.com/watch?v=...";
  statusText.textContent = getDefaultStatus();
  playlistProgress.hidden = true;
  if (isBulk) {
    showBulkPanel();
  } else {
    hidePlaylistPanel();
  }
  featureOne.textContent = getFeatureText(1);
  featureTwo.textContent = getFeatureText(2);
  featureThree.textContent = getFeatureText(3);
  resetPreview();
}

function getSelectedFormat() {
  const selected = document.querySelector("[data-format-option]:checked");
  return selected ? selected.value : "mp3";
}

function getDefaultStatus() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return `Downloads a clean MP4 video at up to ${qualitySelect.value}p.`;
  }

  if (selectedFormat === "spotify") {
    return "Fetches Spotify song or playlist info, finds audio on YouTube, then embeds metadata.";
  }

  if (selectedFormat === "bulk") {
    return "Paste song names or upload a .txt file to build one tagged MP3 ZIP.";
  }

  return "Downloads audio, converts at 320 kbps, then embeds cover art.";
}

function getLoadingStatus() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return `Downloading MP4 video at up to ${qualitySelect.value}p...`;
  }

  if (selectedFormat === "spotify") {
    return isSpotifyPlaylist(input.value.trim())
      ? "Preparing Spotify playlist download..."
      : "Finding Spotify track, searching YouTube, and creating MP3...";
  }

  if (selectedFormat === "bulk") {
    return "Creating bulk download queue and preparing MP3 ZIP...";
  }

  return "Downloading audio, converting to MP3, and writing metadata...";
}

function getQualityPillText() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return `MP4 ${qualitySelect.value}p`;
  }

  if (selectedFormat === "spotify") {
    return "Spotify MP3";
  }

  if (selectedFormat === "bulk") {
    return "Bulk ZIP";
  }

  return "320 kbps";
}

function getModeEyebrow() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return "YouTube video downloader";
  }

  if (selectedFormat === "spotify") {
    return "Spotify music downloader";
  }

  if (selectedFormat === "bulk") {
    return "Bulk song downloader";
  }

  return "YouTube audio converter";
}

function getModeTitle() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return "Download clean MP4 videos.";
  }

  if (selectedFormat === "spotify") {
    return "Turn Spotify links into tagged MP3s.";
  }

  if (selectedFormat === "bulk") {
    return "Download whole song lists.";
  }

  return "Turn videos into polished MP3s.";
}

function getModeCopy() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return "Paste one YouTube video link and download an MP4 file at your selected quality.";
  }

  if (selectedFormat === "spotify") {
    return "Paste a Spotify track or playlist link, fetch song details, match each track on YouTube, and download tagged MP3s.";
  }

  if (selectedFormat === "bulk") {
    return "Paste many song names or upload a text file. TuneLift searches YouTube, creates tagged MP3s, and packages them into one ZIP.";
  }

  return "Paste one YouTube video link and download a 320 kbps MP3 with clean music metadata.";
}

function getFeatureText(index) {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return ["Clean MP4 video", `${qualitySelect.value}p quality`, "Audio included"][index - 1];
  }

  if (selectedFormat === "spotify") {
    return ["Spotify metadata", "YouTube audio match", "ZIP for playlists"][index - 1];
  }

  if (selectedFormat === "bulk") {
    return ["Line-by-line queue", "320 kbps MP3", "ZIP download"][index - 1];
  }

  return ["Best available audio", "320 kbps MP3", "Cover and tags"][index - 1];
}

function setPreviewLoading() {
  previewArt.classList.add("is-loading");
  previewArt.classList.remove("has-error");
  previewTitle.textContent = "Finding video...";
  previewArtist.textContent = "Reading YouTube metadata";
  previewStatus.textContent = "Preview loading";
}

function setPreviewData(video) {
  previewArt.classList.remove("is-loading", "has-error");
  previewTitle.textContent = video.title || "Untitled video";
  previewArtist.textContent = video.artist || "Unknown uploader";
  previewStatus.textContent = "Ready to convert";
  if (video.kind === "playlist") {
    previewStatus.textContent = `${video.total} songs ready`;
  }

  if (video.thumbnail) {
    previewImage.src = video.thumbnail;
    previewImage.alt = `${video.title || "YouTube video"} thumbnail`;
    previewArt.classList.add("has-image");
    previewPlaceholder.hidden = true;
  } else {
    previewImage.removeAttribute("src");
    previewImage.alt = "";
    previewArt.classList.remove("has-image");
    previewPlaceholder.hidden = false;
  }
}

function isSpotifyPlaylist(url) {
  if (getSelectedFormat() !== "spotify") {
    return false;
  }

  try {
    const parsedUrl = new URL(url);
    if (parsedUrl.protocol === "spotify:") {
      return parsedUrl.pathname.startsWith("playlist:");
    }

    const parts = parsedUrl.pathname.split("/").filter(Boolean);
    return parsedUrl.hostname.includes("spotify.com") && parts.includes("playlist");
  } catch (error) {
    return false;
  }
}

function setPreviewError(message) {
  previewArt.classList.remove("is-loading", "has-image");
  previewArt.classList.add("has-error");
  previewImage.removeAttribute("src");
  previewImage.alt = "";
  previewPlaceholder.hidden = false;
  previewTitle.textContent = "Preview unavailable";
  previewArtist.textContent = message;
  previewStatus.textContent = "Check the link";
}

async function loadPlaylistDetails(url) {
  if (!playlistPanel || !playlistTracks) {
    return;
  }

  if (url === lastPlaylistDetailsUrl && playlistTracks.children.length) {
    playlistPanel.hidden = false;
    return;
  }

  if (playlistDetailsController) {
    playlistDetailsController.abort();
  }

  playlistDetailsController = new AbortController();
  lastPlaylistDetailsUrl = url;

  try {
    playlistPanel.hidden = false;
    if (playlistDone) {
      playlistDone.hidden = true;
    }
    playlistProgressRow.hidden = true;
    playlistProgressText.hidden = true;
    playlistTracks.innerHTML = "";
    playlistSubtitle.textContent = "Loading playlist...";

    const formData = new FormData();
    formData.set("url", url);

    const response = await fetch("/spotify-playlist/prepare", {
      method: "POST",
      body: formData,
      signal: playlistDetailsController.signal,
    });
    const data = await safeReadJson(response);

    if (!response.ok || !data.ok) {
      playlistSubtitle.textContent = data.message || "Could not load playlist details.";
      return;
    }

    preparedPlaylistJobId = data.job_id || "";
    const playlist = data.playlist || {};
    setPlaylistHeader({
      name: playlist.name || "Spotify Playlist",
      thumbnail: playlist.thumbnail || "",
      total: playlist.total || 0,
    });
    setPreviewData({
      title: playlist.name || "Spotify Playlist",
      artist: `${playlist.total || 0} songs`,
      thumbnail: playlist.thumbnail || "",
      kind: "playlist",
      total: playlist.total || 0,
    });
    renderPlaylistTracks(playlist.tracks || [], null);
  } catch (error) {
    if (error.name !== "AbortError") {
      playlistSubtitle.textContent = "Could not load playlist details.";
    }
  }
}

async function safeReadJson(response) {
  const copy = response.clone();

  try {
    const data = await response.json();
    if (data && typeof data === "object") {
      return data;
    }
    return { ok: false, message: "Unexpected response from server." };
  } catch (error) {
    try {
      const text = await copy.text();
      return { ok: false, message: text ? text.slice(0, 160) : "Unexpected response from server." };
    } catch (innerError) {
      return { ok: false, message: "Unexpected response from server." };
    }
  }
}

function setPlaylistHeader({ name, thumbnail, total }) {
  if (playlistTitle) {
    playlistTitle.textContent = name || "Spotify Playlist";
  }
  if (playlistSubtitle) {
    playlistSubtitle.textContent = `${total || 0} songs`;
  }

  if (!playlistCover) {
    return;
  }

  const coverContainer = playlistCover.parentElement;
  if (thumbnail) {
    playlistCover.src = thumbnail;
    playlistCover.alt = `${name || "Spotify Playlist"} cover`;
    if (coverContainer) {
      coverContainer.classList.add("has-image");
    }
  } else {
    playlistCover.removeAttribute("src");
    playlistCover.alt = "";
    if (coverContainer) {
      coverContainer.classList.remove("has-image");
    }
  }
}

function setPlaylistProgressUi({ current, total, message }) {
  if (!playlistProgressBar || !playlistPercent || !playlistProgressText || !playlistProgressRow) {
    return;
  }

  playlistProgressRow.hidden = false;
  playlistProgressText.hidden = false;

  playlistProgressBar.max = total || 100;
  playlistProgressBar.value = current || 0;

  const percent = total ? Math.round((current / total) * 100) : 0;
  playlistPercent.textContent = `${percent}%`;
  playlistProgressText.textContent = message || "";
}

function renderPlaylistTracks(tracks, activeIndex) {
  if (!playlistTracks) {
    return;
  }

  const existing = playlistTracks.children.length;
  if (!existing) {
    playlistTracks.innerHTML = tracks.map((track, idx) => buildTrackRow(track, idx + 1)).join("");
    applyTrackState(tracks, activeIndex);
    return;
  }

  if (existing !== tracks.length) {
    playlistTracks.innerHTML = tracks.map((track, idx) => buildTrackRow(track, idx + 1)).join("");
    applyTrackState(tracks, activeIndex);
    return;
  }

  applyTrackState(tracks, activeIndex);
}

function applyTrackState(tracks, activeIndex) {
  tracks.forEach((track, index) => {
    const row = playlistTracks.children[index];
    if (!row) {
      return;
    }

    const statusNode = row.querySelector("[data-track-status]");
    const normalized = normalizeStatus(track.status);

    row.classList.toggle("is-active", Boolean(activeIndex) && index + 1 === activeIndex);
    row.classList.toggle("is-complete", normalized === "completed");

    if (statusNode) {
      statusNode.textContent = track.status || "Pending";
      statusNode.classList.toggle("is-pending", normalized === "pending");
      statusNode.classList.toggle("is-downloading", normalized === "downloading");
      statusNode.classList.toggle("is-completed", normalized === "completed");
    }
  });
}

function buildTrackRow(track, index) {
  const title = escapeHtml(track.title || `Track ${index}`);
  const artist = escapeHtml(track.artist || "");
  const thumbnail = track.thumbnail || "";
  const status = escapeHtml(track.status || "Pending");

  return `
    <li class="playlist-track" data-track-row>
      <div class="playlist-track__thumb" aria-hidden="true">
        ${thumbnail ? `<img src="${escapeAttribute(thumbnail)}" alt="">` : ""}
      </div>
      <div class="playlist-track__meta">
        <div class="playlist-track__title">${title}</div>
        <div class="playlist-track__artist">${artist}</div>
      </div>
      <span class="playlist-track__status is-pending" data-track-status>${status}</span>
    </li>
  `.trim();
}

function normalizeStatus(status) {
  const value = String(status || "").toLowerCase().trim();
  if (value.includes("download")) {
    return "downloading";
  }
  if (value.includes("complete")) {
    return "completed";
  }
  return "pending";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function hidePlaylistPanel() {
  if (!playlistPanel) {
    return;
  }
  playlistPanel.hidden = true;
  preparedPlaylistJobId = "";
  lastPlaylistDetailsUrl = "";
  if (playlistTracks) {
    playlistTracks.innerHTML = "";
  }
  if (playlistCover) {
    const coverContainer = playlistCover.parentElement;
    if (coverContainer) {
      coverContainer.classList.remove("has-image");
    }
    playlistCover.removeAttribute("src");
    playlistCover.alt = "";
  }
  if (playlistDone) {
    playlistDone.hidden = true;
  }
  if (playlistDownloadLink) {
    playlistDownloadLink.removeAttribute("href");
  }
  if (playlistProgressRow) {
    playlistProgressRow.hidden = true;
  }
  if (playlistProgressText) {
    playlistProgressText.hidden = true;
  }
}

function getRenderedTrackCount() {
  return playlistTracks ? playlistTracks.children.length : 0;
}

function showBulkPanel() {
  if (!playlistPanel || !playlistTracks) {
    return;
  }

  playlistPanel.hidden = false;
  if (playlistDone) {
    playlistDone.hidden = true;
  }
  if (playlistDownloadLink) {
    playlistDownloadLink.removeAttribute("href");
  }
  setPlaylistHeader({
    name: "Bulk Songs",
    thumbnail: "",
    total: getBulkSongNames().length,
  });
  setPlaylistProgressUi({
    current: 0,
    total: getBulkSongNames().length,
    message: "Ready to start bulk download",
  });
  updateBulkPreviewPanel();
}

function updateBulkPreviewPanel() {
  if (getSelectedFormat() !== "bulk" || !playlistTracks) {
    return;
  }

  const songNames = getBulkSongNames();
  setPlaylistHeader({
    name: "Bulk Songs",
    thumbnail: "",
    total: songNames.length,
  });
  setPlaylistProgressUi({
    current: 0,
    total: songNames.length,
    message: songNames.length ? `Ready: ${songNames.length} songs queued` : "Paste songs or upload a .txt file",
  });

  if (!songNames.length) {
    playlistTracks.innerHTML = '<li class="playlist-panel__empty">Song queue preview will appear here.</li>';
    return;
  }

  const tracks = songNames.map((songName) => ({
    title: songName,
    artist: "Pending YouTube match",
    thumbnail: "",
    status: "Pending",
  }));
  playlistTracks.innerHTML = tracks.map((track, idx) => buildTrackRow(track, idx + 1)).join("");
  applyTrackState(tracks, null);
}

async function handleBulkFileChange() {
  if (!bulkFile || !bulkFile.files || !bulkFile.files.length) {
    updateBulkPreviewPanel();
    return;
  }

  const file = bulkFile.files[0];
  if (!file.name.toLowerCase().endsWith(".txt")) {
    statusText.textContent = "Upload a .txt file with one song per line.";
    updateBulkPreviewPanel();
    return;
  }

  try {
    const text = await file.text();
    if (bulkSongs && text.trim()) {
      const current = bulkSongs.value.trim();
      bulkSongs.value = current ? `${current}\n${text.trim()}` : text.trim();
    }
    updateBulkPreviewPanel();
  } catch (error) {
    statusText.textContent = "Could not read that text file.";
  }
}

function getBulkSongNames() {
  if (!bulkSongs) {
    return [];
  }

  const seen = new Set();
  return bulkSongs.value
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/\s+/g, " "))
    .filter(Boolean)
    .filter((songName) => {
      const key = songName.toLowerCase();
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
}

function resetBulkInputsOnly() {
  if (bulkSongs) {
    bulkSongs.value = "";
  }
  if (bulkFile) {
    bulkFile.value = "";
  }
}

function setSubmitButtonsDisabled(disabled) {
  submitButtons.forEach((submitButton) => {
    submitButton.disabled = disabled;
  });
}
