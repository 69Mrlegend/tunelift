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
const playlistActions = document.querySelector("[data-playlist-actions]");
const jobStopButton = document.querySelector("[data-job-stop-button]");
const playlistDoneText = document.querySelector("[data-playlist-done-text]");
const confirmedYoutubeUrl = document.querySelector("[data-confirmed-youtube-url]");
const matchConfirmation = document.querySelector("[data-match-confirmation]");
const searchAgainButton = document.querySelector("[data-search-again-button]");

let previewTimer;
let previewController;
let playlistDetailsController;
let lastPlaylistDetailsUrl = "";
let preparedPlaylistJobId = "";
let activeBulkJobId = "";
let activeVideoJobId = "";
let rejectedMatchUrls = [];

if (jobStopButton) {
  jobStopButton.addEventListener("click", async () => {
    const jobId = getSelectedFormat() === "bulk" ? activeBulkJobId : preparedPlaylistJobId;
    if (!jobId) return;

    jobStopButton.disabled = true;
    jobStopButton.textContent = "Stopping...";
    
    const endpoint = getSelectedFormat() === "bulk" ? `/bulk/stop/${jobId}` : `/spotify-playlist/stop/${jobId}`;
    try {
      await fetch(endpoint, { method: "POST" });
    } catch (e) {
      // ignore
    }
  });
}

if (searchAgainButton) {
  searchAgainButton.addEventListener("click", async () => {
    const currentMatch = confirmedYoutubeUrl ? confirmedYoutubeUrl.value : "";
    if (currentMatch) {
      rejectedMatchUrls.push(currentMatch);
    }
    clearConfirmedMatch();
    searchAgainButton.disabled = true;
    searchAgainButton.textContent = "Searching again...";
    await updatePreview(input.value.trim());
    searchAgainButton.disabled = false;
    searchAgainButton.textContent = "Wrong Match → Search Again";
  });
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selectedFormat = getSelectedFormat();
    const formData = new FormData(form);

    if (selectedFormat === "spotify" && !isSpotifyPlaylist(input.value.trim()) && !formData.get("confirmed_youtube_url")) {
      showConversionError("Confirm the matched song before downloading.");
      await updatePreview(input.value.trim());
      return;
    }

    form.classList.add("is-loading");
    setSubmitButtonsDisabled(true);
    input.readOnly = true;
    buttonText.textContent = selectedFormat === "mp4" || selectedFormat === "ipod" ? "Downloading" : "Converting";
    statusText.textContent = getLoadingStatus();

    try {
      if (selectedFormat === "bulk") {
        await startBulkDownload(formData);
        return;
      }

      if (selectedFormat === "mp4" || selectedFormat === "ipod") {
        await startVideoDownload(formData, selectedFormat);
        return;
      }

      if (isSpotifyPlaylist(input.value.trim())) {
        await startPlaylistDownload(formData);
        return;
      }

      if (selectedFormat === "yt-playlist") {
        await startYoutubePlaylistDownload(formData);
        return;
      }

      // Single MP3 or Single Spotify Track enqueuing:
      const addResponse = await fetch("/api/queue/add", {
        method: "POST",
        body: formData,
      });
      const addData = await safeReadJson(addResponse);

      if (!addResponse.ok || !addData.ok) {
        showConversionError(addData.message || "Could not add task to the download queue.");
        return;
      }

      // Track active single job for live progress updating
      activeSingleJobId = addData.job_id;
      resetAfterConversionStarts();
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
    rejectedMatchUrls = [];
    clearConfirmedMatch();

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

// Helper: does the current input look like a raw YouTube/Spotify URL?
function isDirectUrl(text) {
  try {
    const u = new URL(text);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

async function updatePreview(url) {
  if (isSpotifyPlaylist(url)) {
    setPreviewLoading();
    await loadPlaylistDetails(url);
    return;
  }

  if (isYoutubePlaylist(url)) {
    setPreviewLoading();
    await loadYoutubePlaylistDetails(url);
    return;
  }

  if (previewController) {
    previewController.abort();
  }

  previewController = new AbortController();

  // For plain MP3 mode, allow song name queries (not just URLs)
  const selectedFormat = getSelectedFormat();
  const isSearch = selectedFormat === "mp3" && !isDirectUrl(url);

  // Show loading state for search queries
  if (isSearch) {
    setPreviewLoading();
    previewStatus.textContent = "Searching YouTube...";
  }

  try {
    const params = new URLSearchParams({
      url,
      download_type: selectedFormat,
    });
    rejectedMatchUrls.forEach((matchUrl) => params.append("exclude", matchUrl));

    const response = await fetch(`/preview?${params.toString()}`, {
      signal: previewController.signal,
    });
    const data = await response.json();

    if (!response.ok || !data.ok) {
      setPreviewError(data.message || "Preview unavailable");
      hidePlaylistPanel();
      return;
    }

    const video = data.source_track
      ? {
          ...data.video,
          title: data.source_track.title || data.video.title,
          artist: data.source_track.artist || data.video.artist,
          matchedTitle: data.video.title,
          matchedChannel: data.video.channel || data.video.artist,
        }
      : data.video;

    setPreviewData(video);
    if (getSelectedFormat() === "spotify" && data.video && data.video.url && !isSpotifyPlaylist(url)) {
      setConfirmedMatch(data.video.url);
    } else {
      clearConfirmedMatch();
    }

    // Show "Search Again" button for best-possible matches in MP3 mode
    if (matchConfirmation) {
      if (isSearch && video.match_quality === "best_possible") {
        matchConfirmation.hidden = false;
      } else {
        matchConfirmation.hidden = true;
      }
    }

    hidePlaylistPanel();
  } catch (error) {
    if (error.name !== "AbortError") {
      setPreviewError("Preview unavailable");
      hidePlaylistPanel();
    }
  }
}

function resetPreview() {
  clearConfirmedMatch();
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
  rejectedMatchUrls = [];
  clearConfirmedMatch();
  buttonText.textContent = getSubmitButtonText();
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

async function startYoutubePlaylistDownload(formData) {
  const url = input.value.trim();
  await loadYoutubePlaylistDetails(url);

  if (!preparedPlaylistJobId) {
    showConversionError("Load playlist details before starting the download.");
    return;
  }

  const startFormData = new FormData();
  startFormData.set("job_id", preparedPlaylistJobId);

  const startResponse = await fetch("/api/youtube-playlist/start", {
    method: "POST",
    body: startFormData,
  });
  const startData = await safeReadJson(startResponse);

  if (!startResponse.ok || !startData.ok) {
    showConversionError(startData.message || "Could not start YouTube playlist download.");
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

  activeBulkJobId = startData.job_id;
  await pollBulkProgress(startData.job_id);
}

async function startVideoDownload(formData, mode = "mp4") {
  const isIpod = mode === "ipod";
  const startResponse = await fetch(isIpod ? "/ipod/start" : "/video/start", {
    method: "POST",
    body: formData,
  });
  const startData = await safeReadJson(startResponse);

  if (!startResponse.ok || !startData.ok) {
    showConversionError(startData.message || (isIpod ? "Could not start iPod MP4 download." : "Could not start video download."));
    return;
  }

  const title = previewTitle.textContent && !previewArt.classList.contains("has-error")
    ? previewTitle.textContent
    : isIpod ? "iPod MP4 Video" : "MP4 Video";
  const thumbnail = previewImage.getAttribute("src") || "";

  playlistProgress.hidden = true;
  playlistPanel.hidden = false;
  if (playlistDone) {
    playlistDone.hidden = true;
  }
  if (playlistActions) {
    playlistActions.hidden = true;
  }
  if (playlistDownloadLink) {
    playlistDownloadLink.textContent = isIpod ? "Download MP4 for iPod" : "Download MP4";
    playlistDownloadLink.removeAttribute("href");
  }

  setPlaylistHeader({
    name: title,
    thumbnail,
    total: 1,
  });
  if (playlistSubtitle) {
    playlistSubtitle.textContent = isIpod ? "iPod Nano MP4 · 480x320" : `MP4 up to ${qualitySelect.value}p`;
  }
  renderPlaylistTracks([
    {
      title,
      artist: isIpod ? "H.264 video · AAC audio · 480x320" : `MP4 video up to ${qualitySelect.value}p`,
      thumbnail,
      status: "Queued",
    },
  ], 1);
  setPlaylistProgressUi({ current: 0, total: 100, message: isIpod ? "Downloading video..." : "Preparing video download" });

  activeVideoJobId = startData.job_id;
  await pollVideoProgress(startData.job_id, mode);
}

async function pollVideoProgress(jobId, mode = "mp4") {
  const isIpod = mode === "ipod";
  const response = await fetch(isIpod ? `/ipod/progress/${jobId}` : `/video/progress/${jobId}`);
  const data = await safeReadJson(response);

  if (!response.ok || !data.ok) {
    showConversionError(data.message || (isIpod ? "Could not read iPod MP4 progress." : "Could not read video progress."));
    return;
  }

  updateVideoProgress(data, mode);

  if (data.status === "complete") {
    if (playlistDone) {
      playlistDone.hidden = false;
    }
    if (playlistDoneText) {
      playlistDoneText.textContent = isIpod ? "Ready for iPod" : "MP4 download ready";
    }
    if (playlistDownloadLink) {
      playlistDownloadLink.href = data.download_url;
      playlistDownloadLink.textContent = isIpod ? "Download MP4 for iPod" : "Download MP4";
    }
    statusText.textContent = isIpod ? "Ready for iPod" : "MP4 download ready";
    resetAfterPlaylistDownloadStarts();
    return;
  }

  if (data.status === "error") {
    showConversionError(data.error || (isIpod ? "iPod MP4 conversion failed." : "Video download failed."));
    return;
  }

  window.setTimeout(() => pollVideoProgress(jobId, mode), 1200);
}

function updateVideoProgress(data, mode = "mp4") {
  const isIpod = mode === "ipod";
  const percent = Number.isFinite(Number(data.percent)) ? Number(data.percent) : 0;
  const title = data.video_title || (isIpod ? "iPod MP4 Video" : "MP4 Video");
  const thumbnail = previewImage.getAttribute("src") || "";
  const statusLabel = data.status_label || data.message || (isIpod ? "Downloading video..." : "Downloading video");
  const progressLines = [
    isIpod ? `Downloading video: ${Math.round(percent)}%` : `Downloading Video: ${Math.round(percent)}%`,
    `Speed: ${data.speed || "Calculating..."}`,
    `ETA: ${data.eta || "Calculating..."}`,
    `Status: ${statusLabel}`,
  ];

  playlistPanel.hidden = false;
  setPlaylistHeader({
    name: title,
    thumbnail,
    total: 1,
  });
  if (playlistSubtitle) {
    const sizeText = data.total_size ? ` · ${data.total_size}` : "";
    playlistSubtitle.textContent = isIpod ? `iPod Nano MP4 · 480x320${sizeText}` : `MP4 up to ${data.quality || qualitySelect.value}p${sizeText}`;
  }
  setPlaylistProgressUi({ current: percent, total: 100, message: progressLines.join("\n") });
  if (playlistProgressText) {
    playlistProgressText.innerHTML = progressLines.map(escapeHtml).join("<br>");
  }
  renderPlaylistTracks([
    {
      title,
      artist: data.downloaded && data.total_size
        ? `${data.downloaded} of ${data.total_size}`
        : isIpod ? "H.264 video · AAC audio · 480x320" : `MP4 video up to ${data.quality || qualitySelect.value}p`,
      thumbnail,
      status: statusLabel,
    },
  ], data.status === "complete" ? null : 1);
  if (playlistActions) {
    playlistActions.hidden = true;
  }

  statusText.textContent = data.message || statusLabel;
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
    if (playlistDoneText) {
      playlistDoneText.textContent = data.message || "Download Complete";
    }
    if (playlistActions) {
      playlistActions.hidden = true;
    }
    if (playlistDownloadLink) {
      playlistDownloadLink.href = data.download_url;
    }
    statusText.textContent = data.message || "Download Complete";
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
    if (playlistDoneText) {
      playlistDoneText.textContent = data.message || "Download Complete";
    }
    if (playlistActions) {
      playlistActions.hidden = true;
    }
    if (playlistDownloadLink) {
      playlistDownloadLink.href = data.download_url;
    }
    statusText.textContent = data.message || "Download Complete";
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
    if (playlistActions) {
      playlistActions.hidden = false;
    }
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
  buttonText.textContent = getSubmitButtonText();
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

  if (getSelectedFormat() === "mp4") {
    return "youtube-video.mp4";
  }

  if (getSelectedFormat() === "ipod") {
    return "youtube-video-ipod.mp4";
  }

  return "youtube-audio.mp3";
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
  buttonText.textContent = getSubmitButtonText();
  statusText.textContent = message;
  playlistProgress.hidden = true;
  hidePlaylistPanel();
}

function updateFormatControls() {
  const selectedFormat = getSelectedFormat();
  const isVideo = selectedFormat === "mp4";
  const isIpod = selectedFormat === "ipod";
  const isSpotify = selectedFormat === "spotify";
  const isBulk = selectedFormat === "bulk";
  const isMyPlaylists = selectedFormat === "my-playlists";
  const isYtPlaylist = selectedFormat === "yt-playlist";

  qualityRow.hidden = !isVideo;
  if (bulkRow) {
    bulkRow.hidden = !isBulk;
  }
  
  const myPlaylistsPanel = document.querySelector("[data-my-playlists-panel]");
  if (myPlaylistsPanel) {
    myPlaylistsPanel.hidden = !isMyPlaylists;
    if (isMyPlaylists && document.querySelector("[data-playlist-grid]") && !window.hasLoadedPlaylists) {
      loadUserPlaylists();
      window.hasLoadedPlaylists = true;
    }
  }

  urlControls.forEach((control) => {
    control.hidden = isBulk || isMyPlaylists;
  });
  input.required = !isBulk && !isMyPlaylists;
  input.disabled = isBulk || isMyPlaylists;
  qualityPill.textContent = getQualityPillText();
  buttonText.textContent = getSubmitButtonText();
  modeEyebrow.textContent = getModeEyebrow();
  modeTitle.textContent = getModeTitle();
  modeCopy.textContent = getModeCopy();
  urlLabel.textContent = isSpotify ? "Spotify track URL" : (isYtPlaylist ? "YouTube playlist URL" : "YouTube video URL");
  input.placeholder = isSpotify
    ? "https://open.spotify.com/track/... or /playlist/..."
    : (isYtPlaylist ? "https://www.youtube.com/playlist?list=..." : "https://www.youtube.com/watch?v=...");
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

  if (selectedFormat === "ipod") {
    return "Downloads and converts a YouTube video into an iPod Nano compatible MP4.";
  }

  if (selectedFormat === "spotify") {
    return "Fetches Spotify song or playlist info, finds audio on YouTube, then embeds metadata.";
  }

  if (selectedFormat === "bulk") {
    return "Paste song names or upload a .txt file to build one tagged MP3 ZIP.";
  }

  if (selectedFormat === "my-playlists") {
    return "Select a playlist to download it.";
  }

  if (selectedFormat === "yt-playlist") {
    return "Downloads all videos in the playlist sequentially and packages them in a single ZIP.";
  }

  return "Downloads audio, converts at 320 kbps, then embeds cover art.";
}

function getLoadingStatus() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return `Downloading MP4 video at up to ${qualitySelect.value}p...`;
  }

  if (selectedFormat === "ipod") {
    return "Downloading video and converting for iPod...";
  }

  if (selectedFormat === "spotify") {
    return isSpotifyPlaylist(input.value.trim())
      ? "Preparing Spotify playlist download..."
      : "Finding Spotify track, searching YouTube, and creating MP3...";
  }

  if (selectedFormat === "bulk") {
    return "Creating bulk download queue and preparing MP3 ZIP...";
  }

  if (selectedFormat === "yt-playlist") {
    return "Preparing YouTube playlist download...";
  }

  return "Downloading audio, converting to MP3, and writing metadata...";
}

function getQualityPillText() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return `MP4 ${qualitySelect.value}p`;
  }

  if (selectedFormat === "ipod") {
    return "iPod MP4";
  }

  if (selectedFormat === "spotify") {
    return "Spotify MP3";
  }

  if (selectedFormat === "bulk") {
    return "Bulk ZIP";
  }

  if (selectedFormat === "my-playlists") {
    return "My Playlists";
  }

  if (selectedFormat === "yt-playlist") {
    return "Playlist ZIP";
  }

  return "320 kbps";
}

function getSubmitButtonText() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "ipod") {
    return "Download MP4 for iPod";
  }

  if (selectedFormat === "mp4") {
    return "Download MP4";
  }

  if (selectedFormat === "spotify") {
    return "Download Spotify MP3";
  }

  if (selectedFormat === "yt-playlist") {
    return "Download Full Playlist";
  }

  return "Download MP3";
}

function getModeEyebrow() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return "YouTube video downloader";
  }

  if (selectedFormat === "ipod") {
    return "iPod video converter";
  }

  if (selectedFormat === "spotify") {
    return "Spotify music downloader";
  }

  if (selectedFormat === "bulk") {
    return "Bulk song downloader";
  }

  if (selectedFormat === "my-playlists") {
    return "Spotify library";
  }

  if (selectedFormat === "yt-playlist") {
    return "YouTube playlist downloader";
  }

  return "YouTube audio converter";
}

function getModeTitle() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return "Download clean MP4 videos.";
  }

  if (selectedFormat === "ipod") {
    return "Download MP4 videos for iPod.";
  }

  if (selectedFormat === "spotify") {
    return "Turn Spotify links into tagged MP3s.";
  }

  if (selectedFormat === "bulk") {
    return "Download whole song lists.";
  }

  if (selectedFormat === "my-playlists") {
    return "Download your personal playlists.";
  }

  if (selectedFormat === "yt-playlist") {
    return "Download whole YouTube playlists.";
  }

  return "Turn videos into polished MP3s.";
}

function getModeCopy() {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return "Paste one YouTube video link and download an MP4 file at your selected quality.";
  }

  if (selectedFormat === "ipod") {
    return "Paste one YouTube video link and TuneLift will create a compact 480x320 MP4 for iPod Nano.";
  }

  if (selectedFormat === "spotify") {
    return "Paste a Spotify track or playlist link, fetch song details, match each track on YouTube, and download tagged MP3s.";
  }

  if (selectedFormat === "bulk") {
    return "Paste many song names or upload a text file. TuneLift searches YouTube, creates tagged MP3s, and packages them into one ZIP.";
  }

  if (selectedFormat === "my-playlists") {
    return "View your Spotify library and download full playlists directly inside TuneLift.";
  }

  if (selectedFormat === "yt-playlist") {
    return "Paste one YouTube playlist link and download all videos as clean, tagged MP3s sequentially with original thumbnails.";
  }

  return "Paste one YouTube video link and download a 320 kbps MP3 with clean music metadata.";
}

function getFeatureText(index) {
  const selectedFormat = getSelectedFormat();

  if (selectedFormat === "mp4") {
    return ["Clean MP4 video", `${qualitySelect.value}p quality`, "Audio included"][index - 1];
  }

  if (selectedFormat === "ipod") {
    return ["480x320 MP4", "H.264 + AAC", "iPod Nano ready"][index - 1];
  }

  if (selectedFormat === "spotify") {
    return ["Spotify metadata", "YouTube audio match", "ZIP for playlists"][index - 1];
  }

  if (selectedFormat === "bulk") {
    return ["Line-by-line queue", "320 kbps MP3", "ZIP download"][index - 1];
  }

  if (selectedFormat === "my-playlists") {
    return ["Full library sync", "320 kbps MP3", "ZIP for playlists"][index - 1];
  }

  if (selectedFormat === "yt-playlist") {
    return ["Direct YouTube mode", "320 kbps MP3", "ZIP for playlists"][index - 1];
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

  // Match quality badge
  const quality = video.match_quality;
  previewStatus.classList.remove("status--exact", "status--good", "status--best-possible");
  if (quality === "exact") {
    previewStatus.textContent = video.duration_text
      ? `✓ Exact match · ${video.duration_text}`
      : "✓ Exact match";
    previewStatus.classList.add("status--exact");
  } else if (quality === "good") {
    previewStatus.textContent = video.duration_text
      ? `✓ Good match · ${video.duration_text}`
      : "✓ Good match";
    previewStatus.classList.add("status--good");
  } else if (quality === "best_possible") {
    previewStatus.textContent = video.duration_text
      ? `⚠ Best possible match · ${video.duration_text}`
      : "⚠ Best possible match found";
    previewStatus.classList.add("status--best-possible");
  } else {
    previewStatus.textContent = video.duration_text
      ? `Duration ${video.duration_text} · Ready to download`
      : "Ready to convert";
  }

  if (video.kind === "playlist") {
    previewStatus.textContent = `${video.total} songs ready`;
    previewStatus.classList.remove("status--exact", "status--good", "status--best-possible");
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

function setConfirmedMatch(url) {
  if (confirmedYoutubeUrl) {
    confirmedYoutubeUrl.value = url || "";
  }
  if (matchConfirmation) {
    matchConfirmation.hidden = !url;
  }
  if (buttonText && getSelectedFormat() === "spotify") {
    buttonText.textContent = url ? "Correct Song → Download" : getSubmitButtonText();
  }
}

function clearConfirmedMatch() {
  if (confirmedYoutubeUrl) {
    confirmedYoutubeUrl.value = "";
  }
  if (matchConfirmation) {
    matchConfirmation.hidden = true;
  }
  if (buttonText) {
    buttonText.textContent = getSubmitButtonText();
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

function isYoutubePlaylist(url) {
  if (getSelectedFormat() !== "yt-playlist") {
    return false;
  }

  try {
    const parsedUrl = new URL(url);
    if (!parsedUrl.hostname.includes("youtube.com") && !parsedUrl.hostname.includes("youtu.be")) {
      return false;
    }
    return parsedUrl.searchParams.has("list") || parsedUrl.pathname.includes("/playlist");
  } catch (error) {
    return false;
  }
}

function setPreviewError(message) {
  clearConfirmedMatch();
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

async function loadYoutubePlaylistDetails(url) {
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
    playlistSubtitle.textContent = "Loading YouTube playlist...";

    const formData = new FormData();
    formData.set("url", url);

    const response = await fetch("/api/youtube-playlist/prepare", {
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
      name: playlist.name || "YouTube Playlist",
      thumbnail: playlist.thumbnail || "",
      total: playlist.total || 0,
    });
    setPreviewData({
      title: playlist.name || "YouTube Playlist",
      artist: `${playlist.total || 0} videos`,
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
    row.classList.toggle("is-error", normalized === "not-found" || normalized === "failed");

    if (statusNode) {
      statusNode.textContent = track.status || "Pending";
      statusNode.classList.toggle("is-pending", normalized === "pending");
      statusNode.classList.toggle("is-downloading", normalized === "downloading");
      statusNode.classList.toggle("is-completed", normalized === "completed");
      statusNode.classList.toggle("is-error", normalized === "not-found" || normalized === "failed");
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
  if (value.includes("not found") || value.includes("not-found")) {
    return "not-found";
  }
  if (value.includes("fail")) {
    return "failed";
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
    playlistDownloadLink.textContent = "Download ZIP";
  }
  if (playlistActions) {
    playlistActions.hidden = true;
  }
  if (jobStopButton) {
    jobStopButton.disabled = false;
    jobStopButton.textContent = "Stop & Download";
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


// ==========================================================================
// QUEUE & HISTORY HANDLERS
// ==========================================================================

let activeSingleJobId = null;

// Initialize elements
const queueTabBtn = document.querySelector('[data-qh-tab="queue"]');
const historyTabBtn = document.querySelector('[data-qh-tab="history"]');
const queueContent = document.querySelector('[data-qh-content="queue"]');
const historyContent = document.querySelector('[data-qh-content="history"]');

const queueCount = document.querySelector('[data-queue-count]');
const historyCount = document.querySelector('[data-history-count]');

const queueList = document.querySelector('[data-queue-list]');
const historyList = document.querySelector('[data-history-list]');

const queueEmpty = document.querySelector('[data-queue-empty]');
const historyEmpty = document.querySelector('[data-history-empty]');
const historySearch = document.querySelector('[data-history-search]');
const pauseQueueButton = document.querySelector('[data-pause-queue]');
const resumeQueueButton = document.querySelector('[data-resume-queue]');
const clearHistoryButton = document.querySelector('[data-clear-history]');
let lastCompletedIds = new Set();
let lastQueuePaused = false;
let historyFilter = "";

// Handle tab switching
if (queueTabBtn && historyTabBtn) {
  queueTabBtn.addEventListener('click', () => {
    queueTabBtn.classList.add('active');
    historyTabBtn.classList.remove('active');
    queueContent.classList.add('active');
    historyContent.classList.remove('active');
  });

  historyTabBtn.addEventListener('click', () => {
    historyTabBtn.classList.add('active');
    queueTabBtn.classList.remove('active');
    historyContent.classList.add('active');
    queueContent.classList.remove('active');
  });
}

if (historySearch) {
  historySearch.addEventListener("input", () => {
    historyFilter = historySearch.value.trim().toLowerCase();
    pollQueueStatus();
  });
}

if (pauseQueueButton) {
  pauseQueueButton.addEventListener("click", () => queueCommand("/api/queue/pause", "Queue paused"));
}

if (resumeQueueButton) {
  resumeQueueButton.addEventListener("click", () => queueCommand("/api/queue/resume", "Queue resumed"));
}

if (clearHistoryButton) {
  clearHistoryButton.addEventListener("click", async () => {
    await queueCommand("/api/history/clear", "History cleared");
    pollQueueStatus();
  });
}

// Start polling loop
function startQueuePolling() {
  pollQueueStatus();
  setInterval(pollQueueStatus, 1200);
}

async function pollQueueStatus() {
  try {
    const response = await fetch('/api/queue/poll');
    const data = await safeReadJson(response);

    if (response.ok && data.ok) {
      updateQueueUi(data.active, data.history, data.current_job_id, data.queue_paused);
    }
  } catch (error) {
    console.error("Queue poll failed:", error);
  }
}

function updateQueueUi(activeList, historyListItems, currentJobId, queuePaused = false) {
  const completedIds = new Set(historyListItems.filter(item => item.status === "Completed").map(item => item.id || item.job_id || item.download_id));
  completedIds.forEach((id) => {
    if (!lastCompletedIds.has(id)) {
      const item = historyListItems.find(entry => (entry.id || entry.job_id || entry.download_id) === id);
      notifyUser("Download completed", item ? item.title : "Your download is ready");
    }
  });
  if (queuePaused !== lastQueuePaused) {
    notifyUser(queuePaused ? "Queue paused" : "Queue resumed", "TuneLift queue status changed");
  }
  lastCompletedIds = completedIds;
  lastQueuePaused = queuePaused;

  const filteredHistory = historyFilter
    ? historyListItems.filter(item => `${item.title || ""} ${item.type || ""} ${item.playlist_name || ""}`.toLowerCase().includes(historyFilter))
    : historyListItems;

  // Update counts
  if (queueCount) queueCount.textContent = activeList.length;
  if (historyCount) historyCount.textContent = filteredHistory.length;

  // Render active queue list
  if (queueList) {
    if (activeList.length === 0) {
      queueEmpty.style.display = 'block';
      queueList.innerHTML = '';
    } else {
      queueEmpty.style.display = 'none';
      queueList.innerHTML = activeList.map(item => buildQueueItemMarkup(item)).join('');
    }
  }

  // Render history list
  if (historyList) {
    if (filteredHistory.length === 0) {
      historyEmpty.style.display = 'block';
      historyList.innerHTML = '';
    } else {
      historyEmpty.style.display = 'none';
      historyList.innerHTML = filteredHistory.map(item => buildHistoryItemMarkup(item)).join('');
    }
  }

  // Check active single job progress
  if (activeSingleJobId) {
    // Check in active queue first
    const activeJob = activeList.find(item => item.id === activeSingleJobId);
    if (activeJob) {
      if (activeJob.status === 'Downloading') {
        const speed = activeJob.speed ? ` @ ${activeJob.speed}` : '';
        const eta = activeJob.eta ? ` · ETA: ${activeJob.eta}` : '';
        statusText.textContent = `Downloading (${activeJob.percent}%)${speed}${eta}`;
      } else if (activeJob.status === 'Pending') {
        statusText.textContent = 'Pending in queue...';
      }
    } else {
      // Check in history (meaning it finished, failed, or was stopped)
      const finishedJob = historyListItems.find(item => item.id === activeSingleJobId);
      if (finishedJob) {
        if (finishedJob.status === 'Completed') {
          // Trigger browser download
          window.location.href = `/api/queue/download/${activeSingleJobId}`;
          // Reset form state
          form.classList.remove("is-loading");
          setSubmitButtonsDisabled(false);
          input.readOnly = false;
          statusText.textContent = "Download complete.";
        } else if (finishedJob.status === 'Failed') {
          showConversionError(finishedJob.error || "Download failed.");
        } else if (finishedJob.status === 'Stopped') {
          showConversionError("Download stopped manually.");
        } else if (finishedJob.status === 'Not Found') {
          showConversionError("Track not found.");
        }
        activeSingleJobId = null;
      }
    }
  }
}

function buildQueueItemMarkup(item) {
  const isDownloading = item.status === 'Downloading';
  const isPending = item.status === 'Pending';
  const isPaused = item.status === 'Paused';
  const progressPercent = item.percent || 0;
  const itemId = item.id || item.job_id || item.download_id;
  
  const showCover = item.thumbnail ? `<img src="${item.thumbnail}" class="qh-item-cover" alt="cover">` : `<div class="qh-item-cover" style="display:flex;align-items:center;justify-content:center;font-size:1.5rem;">🎵</div>`;

  return `
    <div class="qh-item" id="qh-item-${itemId}">
      ${showCover}
      <div class="qh-item-info">
        <p class="qh-item-title">${escapeHtml(item.title)}</p>
        <div class="qh-item-meta">
          <span class="qh-item-type-badge">${escapeHtml(item.type)}</span>
          <div class="qh-item-status-container">
            <span class="qh-item-status-dot status-dot-${item.status.toLowerCase().replace(' ', '')}"></span>
            <span>${escapeHtml(item.status)}</span>
            ${item.retry_status ? `<span>${escapeHtml(item.retry_status)}</span>` : ''}
          </div>
        </div>
        ${isDownloading ? `
          <div class="qh-item-progress-container">
            <div class="qh-item-progress-bar">
              <div class="qh-item-progress-fill" style="width: ${progressPercent}%"></div>
            </div>
            <div class="qh-item-progress-text">
              <span>${progressPercent}% · ${escapeHtml(item.speed || 'Calculating...')}</span>
              <span>ETA: ${escapeHtml(item.eta || 'Calculating...')}</span>
            </div>
          </div>
        ` : ''}
      </div>
      <div class="qh-item-actions">
        ${(isDownloading || isPending) && itemId ? `
          <button type="button" class="qh-btn qh-btn-pause" onclick="pauseQueueJob('${itemId}')">Pause</button>
        ` : ''}
        ${isPaused && itemId ? `
          <button type="button" class="qh-btn qh-btn-download" onclick="resumeQueueJob('${itemId}')">Resume</button>
        ` : ''}
        ${itemId ? `
          <button type="button" class="qh-btn qh-btn-stop" onclick="cancelQueueJob('${itemId}')">Cancel</button>
        ` : ''}
      </div>
    </div>
  `;
}

function buildHistoryItemMarkup(item) {
  const showCover = item.thumbnail ? `<img src="${item.thumbnail}" class="qh-item-cover" alt="cover">` : `<div class="qh-item-cover" style="display:flex;align-items:center;justify-content:center;font-size:1.5rem;">🎵</div>`;
  const isCompleted = item.status === 'Completed';
  const isFailed = item.status === 'Failed' || item.status === 'Stopped';
  const itemId = item.id || item.job_id || item.download_id;

  // Format date/time
  let dateStr = "";
  if (item.date_time) {
    try {
      const d = new Date(item.date_time);
      dateStr = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    } catch(e) {}
  }

  // Size
  const sizeText = item.file_size ? ` · ${item.file_size}` : '';

  return `
    <div class="qh-item" id="qh-item-${itemId}">
      ${showCover}
      <div class="qh-item-info">
        <p class="qh-item-title">${escapeHtml(item.title)}</p>
        <div class="qh-item-meta">
          <span class="qh-item-type-badge">${escapeHtml(item.type)}</span>
          <div class="qh-item-status-container">
            <span class="qh-item-status-dot status-dot-${item.status.toLowerCase().replace(' ', '')}"></span>
            <span>${escapeHtml(item.status)}</span>
          </div>
          <span>${dateStr}${sizeText}</span>
        </div>
      </div>
      <div class="qh-item-actions">
        ${isCompleted ? (
          itemId ? `
            <a class="qh-btn qh-btn-download" href="/api/queue/download/${itemId}">Download</a>
            ${item.saved_location && item.saved_location.toLowerCase().endsWith(".mp3") ? `<button type="button" class="qh-btn qh-btn-download" onclick="playHistoryItem('${itemId}')">Play</button>` : ''}
          ` : `
            <button type="button" class="qh-btn qh-btn-download" disabled style="opacity: 0.5; cursor: not-allowed;" title="Download ID is missing.">Download Unavailable</button>
          `
        ) : ''}
        ${isFailed && itemId ? `
          <button type="button" class="qh-btn qh-btn-retry" onclick="retryQueueJob('${itemId}')">Retry</button>
        ` : ''}
        ${itemId ? `<button type="button" class="qh-btn qh-btn-stop" onclick="deleteHistoryItem('${itemId}')">Delete</button>` : ''}
      </div>
    </div>
  `;
}

async function stopQueueJob(jobId) {
  return cancelQueueJob(jobId);
}

async function queueCommand(url, successMessage) {
  try {
    const res = await fetch(url, { method: 'POST', headers: { "Content-Type": "application/json" } });
    const data = await safeReadJson(res);
    if (!res.ok || !data.ok) {
      showToast(data.message || "Request failed");
      return false;
    }
    if (successMessage) showToast(successMessage);
    return true;
  } catch (err) {
    console.error("Queue command failed:", err);
    showToast("Could not reach TuneLift backend");
    return false;
  }
}

async function pauseQueueJob(jobId) {
  await queueCommand(`/api/queue/pause/${jobId}`, "Download paused");
}

async function resumeQueueJob(jobId) {
  await queueCommand(`/api/queue/resume/${jobId}`, "Download resumed");
  if (queueTabBtn) queueTabBtn.click();
}

async function cancelQueueJob(jobId) {
  try {
    const res = await fetch(`/api/queue/cancel/${jobId}`, { method: 'POST' });
    const data = await safeReadJson(res);
    if (!res.ok || !data.ok) {
      showToast(data.message || "Failed to cancel download.");
    }
  } catch (err) {
    console.error("Cancel job failed:", err);
  }
}

async function deleteHistoryItem(jobId) {
  await queueCommand(`/api/history/delete/${jobId}`, "History item deleted");
  pollQueueStatus();
}

async function retryQueueJob(jobId) {
  try {
    const res = await fetch(`/api/queue/retry/${jobId}`, { method: 'POST' });
    const data = await safeReadJson(res);
    if (res.ok && data.ok) {
      // Switch back to Active Queue tab to show progress
      if (queueTabBtn) queueTabBtn.click();
    } else {
      showToast(data.message || "Failed to retry download.");
    }
  } catch (err) {
    console.error("Retry job failed:", err);
  }
}

// Make globally accessible for inline onclick handlers
window.stopQueueJob = stopQueueJob;
window.pauseQueueJob = pauseQueueJob;
window.resumeQueueJob = resumeQueueJob;
window.cancelQueueJob = cancelQueueJob;
window.retryQueueJob = retryQueueJob;
window.deleteHistoryItem = deleteHistoryItem;

// Initialize polling
startQueuePolling();

// ==========================================================================
// PLAYER, PLAYLISTS, SETTINGS, STORAGE, ANALYTICS, NOTIFICATIONS
// ==========================================================================

const toastStack = document.querySelector("[data-toast-stack]");
const playerDrawer = document.querySelector("[data-player-drawer]");
const openPlayerButtons = document.querySelectorAll("[data-open-player], [data-mini-open], [data-mobile-player-link]");
const closePlayerButton = document.querySelector("[data-close-player]");
const playerLibrary = document.querySelector("[data-player-library]");
const playerTitle = document.querySelector("[data-player-title]");
const playerSeek = document.querySelector("[data-player-seek]");
const playerToggle = document.querySelector("[data-player-toggle]");
const playerPrev = document.querySelector("[data-player-prev]");
const playerNext = document.querySelector("[data-player-next]");
const playerShuffle = document.querySelector("[data-player-shuffle]");
const playerRepeat = document.querySelector("[data-player-repeat]");
const miniPlayer = document.querySelector("[data-bottom-player]");
const miniToggle = document.querySelector("[data-mini-toggle]");
const miniTitle = document.querySelector("[data-mini-title]");
const analyticsCards = document.querySelector("[data-analytics-cards]");
const storagePanel = document.querySelector("[data-storage-panel]");
const refreshAnalyticsButton = document.querySelector("[data-refresh-analytics]");
const cleanStorageButton = document.querySelector("[data-clean-storage]");
const localPlaylistName = document.querySelector("[data-local-playlist-name]");
const localSongPicker = document.querySelector("[data-local-song-picker]");
const localPlaylistsContainer = document.querySelector("[data-local-playlists]");
const createLocalPlaylistButton = document.querySelector("[data-create-local-playlist]");
const saveSettingsButton = document.querySelector("[data-save-settings]");
const audioElement = new Audio();
audioElement.preload = "metadata";
let playerSongs = [];
let playerIndex = -1;
let shuffleEnabled = false;
let repeatEnabled = false;
let localPlaylists = [];

function showToast(message) {
  if (!toastStack) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  toastStack.appendChild(toast);
  window.setTimeout(() => toast.remove(), 3600);
}

function notifyUser(title, body) {
  showToast(`${title}: ${body}`);
  if (!("Notification" in window)) return;
  if (Notification.permission === "granted") {
    new Notification(title, { body });
  } else if (Notification.permission !== "denied") {
    Notification.requestPermission().then((permission) => {
      if (permission === "granted") new Notification(title, { body });
    });
  }
}

openPlayerButtons.forEach(button => button.addEventListener("click", () => {
  if (playerDrawer) playerDrawer.hidden = false;
  loadPlayerLibrary();
}));
if (closePlayerButton) closePlayerButton.addEventListener("click", () => playerDrawer.hidden = true);
if (playerToggle) playerToggle.addEventListener("click", togglePlayback);
if (miniToggle) miniToggle.addEventListener("click", togglePlayback);
if (playerPrev) playerPrev.addEventListener("click", playPrevious);
if (playerNext) playerNext.addEventListener("click", playNext);
if (playerShuffle) playerShuffle.addEventListener("click", () => {
  shuffleEnabled = !shuffleEnabled;
  playerShuffle.classList.toggle("active", shuffleEnabled);
});
if (playerRepeat) playerRepeat.addEventListener("click", () => {
  repeatEnabled = !repeatEnabled;
  playerRepeat.classList.toggle("active", repeatEnabled);
});

audioElement.addEventListener("timeupdate", () => {
  if (playerSeek && audioElement.duration) {
    playerSeek.value = String((audioElement.currentTime / audioElement.duration) * 100);
  }
});
audioElement.addEventListener("ended", () => repeatEnabled ? playSong(playerIndex) : playNext());
if (playerSeek) {
  playerSeek.addEventListener("input", () => {
    if (audioElement.duration) audioElement.currentTime = (Number(playerSeek.value) / 100) * audioElement.duration;
  });
}

async function loadPlayerLibrary() {
  const response = await fetch("/api/player/library");
  const data = await safeReadJson(response);
  if (!response.ok || !data.ok) return;
  playerSongs = data.songs || [];
  if (localSongPicker) {
    localSongPicker.innerHTML = playerSongs.map((song, index) => `<option value="${index}">${escapeHtml(song.title)}</option>`).join("");
  }
  renderPlayerLibrary();
}

function renderPlayerLibrary() {
  if (!playerLibrary) return;
  playerLibrary.innerHTML = playerSongs.map((song, index) => `
    <li>
      <button type="button" onclick="playSong(${index})">${escapeHtml(song.title)}</button>
    </li>
  `).join("") || '<li class="playlist-panel__empty">Downloaded MP3s will appear here.</li>';
}

function playSong(index) {
  if (!playerSongs[index]) return;
  playerIndex = index;
  audioElement.src = playerSongs[index].url;
  audioElement.play().catch(() => showToast("Playback could not start"));
  updatePlayerLabels(playerSongs[index].title, true);
}

function playHistoryItem(jobId) {
  audioElement.src = `/api/queue/download/${jobId}`;
  audioElement.play().catch(() => showToast("Playback could not start"));
  updatePlayerLabels("History item", true);
}

function togglePlayback() {
  if (!audioElement.src && playerSongs.length) playSong(0);
  else if (audioElement.paused) audioElement.play();
  else audioElement.pause();
  updatePlayerLabels(playerSongs[playerIndex] ? playerSongs[playerIndex].title : "Playing", audioElement.paused === false);
}

function playNext() {
  if (!playerSongs.length) return;
  const nextIndex = shuffleEnabled ? Math.floor(Math.random() * playerSongs.length) : (playerIndex + 1) % playerSongs.length;
  playSong(nextIndex);
}

function playPrevious() {
  if (!playerSongs.length) return;
  playSong((playerIndex - 1 + playerSongs.length) % playerSongs.length);
}

function updatePlayerLabels(title, playing) {
  if (playerTitle) playerTitle.textContent = title;
  if (miniTitle) miniTitle.textContent = title;
  if (playerToggle) playerToggle.textContent = playing ? "Pause" : "Play";
  if (miniToggle) miniToggle.textContent = playing ? "Pause" : "Play";
  if (miniPlayer) miniPlayer.hidden = false;
}

window.playSong = playSong;
window.playHistoryItem = playHistoryItem;

async function loadLocalPlaylists() {
  const response = await fetch("/api/local-playlists");
  const data = await safeReadJson(response);
  localPlaylists = data.playlists || [];
  renderLocalPlaylists();
}

async function saveLocalPlaylists() {
  await fetch("/api/local-playlists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ playlists: localPlaylists }),
  });
}

function renderLocalPlaylists() {
  if (!localPlaylistsContainer) return;
  localPlaylistsContainer.innerHTML = localPlaylists.map((playlist, pIndex) => `
    <div class="local-playlist-card">
      <input value="${escapeHtml(playlist.name)}" onchange="renameLocalPlaylist(${pIndex}, this.value)">
      <button type="button" onclick="addSongToLocalPlaylist(${pIndex})">Add Song</button>
      <button type="button" onclick="deleteLocalPlaylist(${pIndex})">Delete</button>
      <ol>
        ${(playlist.songs || []).map((song, sIndex) => `
          <li draggable="true" ondragstart="dragLocalSong(${pIndex}, ${sIndex})" ondrop="dropLocalSong(${pIndex}, ${sIndex})" ondragover="event.preventDefault()">
            <span>${escapeHtml(song.title)}</span>
            <button type="button" onclick="removeLocalSong(${pIndex}, ${sIndex})">Remove</button>
          </li>
        `).join("")}
      </ol>
    </div>
  `).join("") || '<p class="playlist-panel__empty">Create a playlist from downloaded MP3s.</p>';
}

if (createLocalPlaylistButton) {
  createLocalPlaylistButton.addEventListener("click", async () => {
    const name = (localPlaylistName && localPlaylistName.value.trim()) || "New Playlist";
    localPlaylists.push({ id: Date.now().toString(), name, songs: [] });
    if (localPlaylistName) localPlaylistName.value = "";
    await saveLocalPlaylists();
    renderLocalPlaylists();
  });
}

let draggedLocalSong = null;
function renameLocalPlaylist(index, name) { localPlaylists[index].name = name || "Untitled"; saveLocalPlaylists(); }
function deleteLocalPlaylist(index) { localPlaylists.splice(index, 1); saveLocalPlaylists().then(renderLocalPlaylists); }
function addSongToLocalPlaylist(index) {
  const song = playerSongs[Number(localSongPicker.value)];
  if (!song) return;
  localPlaylists[index].songs.push(song);
  saveLocalPlaylists().then(renderLocalPlaylists);
}
function removeLocalSong(pIndex, sIndex) { localPlaylists[pIndex].songs.splice(sIndex, 1); saveLocalPlaylists().then(renderLocalPlaylists); }
function dragLocalSong(pIndex, sIndex) { draggedLocalSong = { pIndex, sIndex }; }
function dropLocalSong(pIndex, sIndex) {
  if (!draggedLocalSong || draggedLocalSong.pIndex !== pIndex) return;
  const songs = localPlaylists[pIndex].songs;
  const [song] = songs.splice(draggedLocalSong.sIndex, 1);
  songs.splice(sIndex, 0, song);
  draggedLocalSong = null;
  saveLocalPlaylists().then(renderLocalPlaylists);
}
Object.assign(window, { renameLocalPlaylist, deleteLocalPlaylist, addSongToLocalPlaylist, removeLocalSong, dragLocalSong, dropLocalSong });

async function loadSettings() {
  const response = await fetch("/api/settings");
  const data = await safeReadJson(response);
  if (!response.ok || !data.ok) return;
  document.querySelectorAll("[data-setting]").forEach((field) => {
    const key = field.dataset.setting;
    if (field.type === "checkbox") field.checked = Boolean(data.settings[key]);
    else field.value = data.settings[key] ?? "";
  });
}

if (saveSettingsButton) {
  saveSettingsButton.addEventListener("click", async () => {
    const payload = {};
    document.querySelectorAll("[data-setting]").forEach((field) => {
      payload[field.dataset.setting] = field.type === "checkbox" ? field.checked : field.value;
    });
    await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    showToast("Settings saved");
  });
}

function formatBytesLocal(bytes) {
  let value = Number(bytes || 0);
  for (const unit of ["B", "KB", "MB", "GB"]) {
    if (value < 1024 || unit === "GB") return `${value.toFixed(unit === "B" ? 0 : 1)} ${unit}`;
    value /= 1024;
  }
  return `${value.toFixed(1)} GB`;
}

async function loadStorage() {
  const response = await fetch("/api/storage");
  const data = await safeReadJson(response);
  if (!storagePanel || !data.ok) return;
  storagePanel.innerHTML = `
    <p>Downloads folder: <strong>${formatBytesLocal(data.downloads_size)}</strong></p>
    <p>MP3 files: <strong>${data.song_count}</strong></p>
    <p>Duplicates: <strong>${(data.duplicates || []).length}</strong></p>
    <p>Temporary files: <strong>${(data.temp_files || []).length}</strong></p>
    <p>Broken ZIP files: <strong>${(data.broken_zips || []).length}</strong></p>
  `;
}

if (cleanStorageButton) {
  cleanStorageButton.addEventListener("click", async () => {
    const response = await fetch("/api/storage/cleanup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ remove_duplicates: true }) });
    const data = await safeReadJson(response);
    showToast(`Cleaned ${data.removed ? data.removed.length : 0} files`);
    loadStorage();
  });
}

async function loadAnalytics() {
  const response = await fetch("/api/analytics");
  const data = await safeReadJson(response);
  if (!analyticsCards || !data.ok) return;
  const stats = data.queue_statistics || {};
  analyticsCards.innerHTML = [
    ["Songs", data.total_songs],
    ["Playlists", data.total_playlists],
    ["Storage", formatBytesLocal(data.storage_used)],
    ["Top type", data.most_downloaded_type],
    ["Average speed", data.average_speed],
    ["Queue", `${stats.active || 0} active / ${stats.completed || 0} done`],
  ].map(([label, value]) => `<div class="metric-card"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

if (refreshAnalyticsButton) refreshAnalyticsButton.addEventListener("click", loadAnalytics);

loadPlayerLibrary();
loadLocalPlaylists();
loadSettings();
loadStorage();
loadAnalytics();
