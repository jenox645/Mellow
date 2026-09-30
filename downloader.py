from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

import yt_dlp

import analytics
from constants import (
    AUDIO_FORMATS,
    PAUSE_POLL_SECS,
    SOCKET_TIMEOUT_SECS,
    SPONSORBLOCK_REMOVE_CATEGORIES,
    THUMB_FETCH_TIMEOUT_SECS,
)
from ffmpeg_locate import find_ffmpeg

log = logging.getLogger(__name__)

_pause_event = threading.Event()

GEO_BLOCK_PATTERNS = [
    "not made this video available in your country",
    "not available in your region",
    "blocked it in your country",
    "geo.restricted",
    "georestricted",
    "not available in your country",
    "this video is unavailable",
]


class _GeoBlockLogger:
    def __init__(self, progress_cb: Callable, library_id: str | None) -> None:
        self._cb = progress_cb
        self._lid = library_id
        self._seen: set[str] = set()
        self.last_error: str | None = None

    def _emit_once(self, reason: str, msg: str) -> None:
        # yt-dlp logs several error lines per failed item (retries, final
        # error); dedupe so failedCount reflects items, not log lines.
        key = msg.strip()
        if key in self._seen:
            return
        self._seen.add(key)
        self._cb({"status": "item_failed", "reason": reason, "message": msg, "library_id": self._lid})

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        lmsg = msg.lower()
        if any(p in lmsg for p in GEO_BLOCK_PATTERNS):
            self._emit_once("geo_blocked", msg)

    def error(self, msg: str) -> None:
        self.last_error = msg
        lmsg = msg.lower()
        if any(p in lmsg for p in GEO_BLOCK_PATTERNS):
            self._emit_once("geo_blocked", msg)
        else:
            self._emit_once("error", msg)


def pause() -> None:
    _pause_event.set()


def resume() -> None:
    _pause_event.clear()

QUALITY_MAP: dict[str, str] = {
    "best":  "bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "4k":    "bestvideo[height<=2160]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best",
    "720p":  "bestvideo[height<=720]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best",
    "480p":  "bestvideo[height<=480]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best",
    "360p":  "bestvideo[height<=360]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best",
}

# Without ffmpeg nothing can be merged or converted, so fall back to formats
# that already hold both streams in one file. Sites like YouTube only offer
# those at low resolution; the user is warned rather than left with a failed
# download.
_QUALITY_MAX_HEIGHT: dict[str, int] = {"4k": 2160, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360}
NO_FFMPEG_AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"
NO_FFMPEG_ERROR_HINT = ("Note: ffmpeg isn't installed. Sites that serve video and audio "
                        "separately (YouTube) can't be saved as video without it. Install "
                        "ffmpeg (Windows: winget install Gyan.FFmpeg) and try again.")


def _single_file_format(quality: str) -> str:
    height = _QUALITY_MAX_HEIGHT.get(quality)
    return f"best[height<={height}]/best" if height else "best"


def _merged_format(quality: str, container: str) -> tuple[str, str]:
    """(format selector, merge_output_format) for a video download with ffmpeg."""
    if container != "webm":
        return QUALITY_MAP.get(quality, "bestvideo+bestaudio/best"), container
    # webm only holds VP8/VP9/AV1 video with Opus/Vorbis audio. The m4a audio
    # QUALITY_MAP prefers cannot be muxed into it ("Conversion failed!"), so
    # ask for webm streams first and let an impossible merge land in mkv.
    height = _QUALITY_MAX_HEIGHT.get(quality)
    h = f"[height<={height}]" if height else ""
    fmt = (f"bestvideo{h}[ext=webm]+bestaudio[ext=webm]/"
           f"bestvideo{h}+bestaudio[ext=webm]/bestvideo{h}+bestaudio/best")
    return fmt, "webm/mkv"


AUDIO_FORMAT_MAP: dict[str, str] = {fmt: fmt for fmt in AUDIO_FORMATS}

# Audio quality choice -> FFmpegExtractAudio preferredquality ("0" = best VBR).
# Ignored by lossless targets (flac, wav).
AUDIO_QUALITY_MAP: dict[str, str] = {
    "best": "0",
    "320": "320",
    "256": "256",
    "192": "192",
    "128": "128",
}

def _make_progress_hook(progress_cb: Callable, library_id: str | None, speed_tracker: dict,
                        cancel_event: threading.Event, pause_event: threading.Event,
                        save_sidecar: bool = True) -> Callable:
    def hook(d: dict) -> None:
        # Pause support: block here while paused
        while pause_event.is_set():
            if cancel_event.is_set():
                raise yt_dlp.utils.DownloadCancelled()
            time.sleep(PAUSE_POLL_SECS)
        if cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled()
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = round((downloaded / total * 100) if total else 0, 1)
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            filename = Path(d.get("filename", "")).name
            info_dict = d.get("info_dict") or {}
            current_title = info_dict.get("title") or Path(d.get("filename", "")).stem
            current_thumb = info_dict.get("thumbnail")
            if speed:
                speed_tracker["samples"].append(speed)
            progress_cb({
                "status": "downloading",
                "pct": pct,
                "downloaded": downloaded,
                "total": total,
                "speed": speed,
                "eta": eta,
                "filename": filename,
                "library_id": library_id,
                "current_item_title": current_title,
                "current_item_thumb": current_thumb,
            })
        elif status == "finished":
            info_dict = d.get("info_dict") or {}
            filename = d.get("filename", "")
            thumb_url = info_dict.get("thumbnail")
            # Save sidecar immediately — filename and URL are live right now.
            # Skipped when yt-dlp writes the thumbnail itself (embedding): two
            # writers racing for the same .jpg can fail the ffmpeg conversion.
            if filename and save_sidecar:
                _save_thumbnail_sidecar(filename, thumb_url)
            # Per-item timing/speed so playlist entries don't all inherit the
            # whole playlist's elapsed time and shared average speed.
            now = time.monotonic()
            samples = speed_tracker["samples"]
            start_idx = speed_tracker.get("item_sample_start", 0)
            item_samples = samples[start_idx:]
            vid = info_dict.get("id")
            # A merged download finishes once per stream (video, then audio);
            # only the first counts as the item being done.
            first_stream = not vid or vid not in speed_tracker.setdefault("items", {})
            speed_tracker["finished"] = speed_tracker.get("finished", 0) + 1
            if vid:
                speed_tracker.setdefault("items", {})[vid] = {
                    "elapsed": int(now - speed_tracker.get("item_t0", speed_tracker["t0"])),
                    "speed": int(sum(item_samples) / len(item_samples)) if item_samples else None,
                }
            speed_tracker["item_t0"] = now
            speed_tracker["item_sample_start"] = len(samples)
            if first_stream:
                progress_cb({
                    "status": "item_done",
                    "title": info_dict.get("title") or Path(filename).stem,
                    "thumbnail": thumb_url,
                    "video_id": vid,
                    "playlist_index": info_dict.get("playlist_index"),
                    "library_id": library_id,
                })
            progress_cb({"status": "processing", "library_id": library_id})

    return hook


def _build_postprocessors(opts: dict, *, embed_subs: bool = False,
                          cut_sponsors: bool = False) -> list[dict]:
    """ffmpeg-backed postprocessors — only call this when ffmpeg is available.

    The order is the one yt-dlp's CLI uses (get_postprocessors in
    yt_dlp/__init__.py); several of these only work in that order.
    """
    pps: list[dict] = []
    if cut_sponsors:
        # This one only looks the segments up (YouTube only) and must do so
        # before the download; ModifyChapters below is what cuts them out.
        pps.append({
            "key": "SponsorBlock",
            "categories": list(SPONSORBLOCK_REMOVE_CATEGORIES),
            "when": "after_filter",
        })
    if opts.get("embed_thumbnail"):
        # The embed step itself is attached in _download_video (it needs
        # writethumbnail and must never fail a download). Converting first
        # gives every container a format it accepts and a predictable .jpg.
        pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
    if embed_subs:
        # Before ModifyChapters, so the subtitles are cut along with the video
        pps.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})
    if cut_sponsors:
        # Before FFmpegMetadata: it moves the chapters that follow a cut
        pps.append({
            "key": "ModifyChapters",
            "remove_sponsor_segments": list(SPONSORBLOCK_REMOVE_CATEGORIES),
        })
    if opts.get("embed_chapters") or opts.get("embed_metadata"):
        pps.append({
            "key": "FFmpegMetadata",
            "add_chapters": bool(opts.get("embed_chapters")),
            "add_metadata": bool(opts.get("embed_metadata")),
        })
    if opts.get("split_chapters"):
        pps.append({"key": "FFmpegSplitChapters"})
    return pps


class _EmbedThumbnailBestEffort(yt_dlp.postprocessor.EmbedThumbnailPP):
    """Cover art is a nicety: a container that can't hold one (webm, wav) or a
    missing mutagen (opus/flac) must not turn a finished download into an error."""

    def run(self, info: dict) -> tuple[list, dict]:
        try:
            return super().run(info)
        except yt_dlp.utils.PostProcessingError as exc:
            self.report_warning(f"Thumbnail not embedded: {exc}")
            # A failed ffmpeg embed leaves its half-written output behind
            leftover = Path(yt_dlp.utils.prepend_extension(info["filepath"], "temp"))
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass
            return [], info


def _save_thumbnail_sidecar(filepath: str, thumb_url: str | None) -> None:
    if not thumb_url or not filepath:
        return
    p = Path(filepath)
    stem = p.stem
    # Strip only yt-dlp intermediate format codes (.f137, .f251-style) so
    # legitimate dotted titles ("Episode.10") keep their full stem and the
    # vault lookup (same stem + .jpg) actually finds the sidecar.
    clean_stem = re.sub(r'\.f\d{1,5}$', '', stem)
    sidecar = p.parent / ((clean_stem or stem) + ".jpg")
    if sidecar.exists():
        return

    def _fetch() -> None:
        try:
            from urllib.request import urlopen as _uo
            with _uo(thumb_url, timeout=THUMB_FETCH_TIMEOUT_SECS) as resp:
                data = resp.read()
            sidecar.write_bytes(data)
        except Exception as e:
            log.warning(f"failed to save sidecar for {p.name}: {e}")

    # Off-thread: a slow thumbnail CDN must not stall the progress hook
    threading.Thread(target=_fetch, daemon=True).start()


def _detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "Twitter/X"
    if "instagram.com" in url_lower:
        return "Instagram"
    if "tiktok.com" in url_lower:
        return "TikTok"
    if "twitch.tv" in url_lower:
        return "Twitch"
    if "vimeo.com" in url_lower:
        return "Vimeo"
    if "reddit.com" in url_lower:
        return "Reddit"
    if "soundcloud.com" in url_lower:
        return "SoundCloud"
    return "Other"


# yt-dlp extractor key → reconstructable public URL, for archive files.
# soundcloud / tiktok / instagram / bandcamp store numeric IDs that can't be
# turned back into a working public URL; their entries are skipped.
_ARCHIVE_URL_TEMPLATES = {
    "youtube":     "https://www.youtube.com/watch?v={}",
    "vimeo":       "https://vimeo.com/{}",
    "twitter":     "https://twitter.com/i/status/{}",
    "twitch":      "https://www.twitch.tv/videos/{}",
    "twitchvod":   "https://www.twitch.tv/videos/{}",
    "bilibili":    "https://www.bilibili.com/video/{}",
    "dailymotion": "https://www.dailymotion.com/video/{}",
    "nicovideo":   "https://www.nicovideo.jp/watch/{}",
}


def parse_url_file(content: str) -> tuple[list[str], str]:
    """URLs from a text file of URLs or a yt-dlp archive file ("youtube <id>").

    Returns (urls, "url_list" | "archive").
    """
    urls: list[str] = []
    fmt = "url_list"
    for line in content.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("http"):
            urls.append(line)
            continue
        parts = line.split()
        if len(parts) == 2:
            tmpl = _ARCHIVE_URL_TEMPLATES.get(parts[0].lower())
            if tmpl:
                urls.append(tmpl.format(parts[1]))
                fmt = "archive"
    return urls, fmt


def _parse_time(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _file_ext(path: str | None, fallback: str) -> str:
    """Extension of the file that actually landed on disk (the requested
    container is only a wish: no ffmpeg, or a site with a single format)."""
    return (Path(path).suffix.lstrip(".").lower() if path else "") or fallback


def _safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def download_video(
    url: str,
    output_dir: str,
    opts: dict,
    progress_cb: Callable,
    library_id: str | None = None,
    cancel_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
) -> str:
    """Run one download. Returns terminal status: 'success' | 'cancelled' | 'error'.

    cancel_event is the job's own (the queue worker passes it; a direct call
    without one can't be cancelled). pause_event is the shared pause flag when the job queue passes it (the
    queue then owns clearing it); a direct call without one owns its pause.
    """
    try:
        return _download_video(url, output_dir, opts, progress_cb, library_id,
                               cancel_event, pause_event)
    except Exception as exc:
        # Setup failures (unwritable output folder, malformed options) happen
        # before yt-dlp runs; without a terminal event the UI waits forever.
        progress_cb({"status": "error", "message": str(exc), "url": url, "library_id": library_id})
        return "error"


def _opt_str(opts: dict, key: str, default: str = "") -> str:
    # Clients send null for unset fields; treat that like a missing key
    return str(opts.get(key) or default).strip()


def _clip_range(start_time: str, end_time: str) -> tuple[float, float]:
    """(start, end) seconds of a trimmed download; an open end is "to the last second"."""
    start = _parse_time(start_time) if start_time else 0.0
    end = _parse_time(end_time) if end_time else float("inf")
    for text, value in ((start_time, start), (end_time, end)):
        if value is None:
            # Silently reading it as "from the start"/"to the end" downloaded
            # the whole video when a clip was asked for
            raise ValueError(f"Can't read the clip time {text!r} (use seconds, mm:ss or hh:mm:ss).")
    if end <= start:
        raise ValueError(f"The clip ends ({end_time}) before it starts ({start_time or '0'}).")
    return start, end


def _rate_limit(value: Any) -> float | None:
    """The UI stores CLI-style strings ("5M"); the Python API needs bytes/sec."""
    if isinstance(value, (int, float)):
        return value or None
    parse_fn = getattr(yt_dlp.utils, "parse_bytes", None) or yt_dlp.utils.parse_filesize
    try:
        return parse_fn(str(value))
    except Exception:
        return None


def _build_ydl_opts(url: str, out_dir: Path, opts: dict, *, ffmpeg: str | None,
                    want_audio: bool, embed_thumb: bool,
                    warn: Callable[[str, str], None]) -> tuple[dict[str, Any], str | None]:
    """The yt-dlp options for one download, and the warning it is saved with (if any).

    warn(code, message) reports a limitation to the UI as it is decided.
    """
    mode = _opt_str(opts, "mode", "video").lower()
    quality = _opt_str(opts, "quality", "best")
    container = _opt_str(opts, "container", "mp4").lower()
    audio_fmt = _opt_str(opts, "audio_format", "mp3").lower()
    custom_format = _opt_str(opts, "custom_format")
    start_time = _opt_str(opts, "start_time")
    end_time = _opt_str(opts, "end_time")
    embed_subs = bool(opts.get("embed_subs")) and not want_audio
    filename_template = _opt_str(opts, "filename_template") or "%(title)s.%(ext)s"
    outtmpl = str(out_dir / filename_template)
    log.debug(f"yt-dlp outtmpl={outtmpl!r} mode={mode} audio_format={audio_fmt} "
              f"quality={quality} container={container}")
    warning: str | None = None

    ydl_opts: dict[str, Any] = {"outtmpl": outtmpl, "windows_filenames": True}
    if ffmpeg:
        ydl_opts["ffmpeg_location"] = ffmpeg
        cut_sponsors = bool(opts.get("sponsorblock"))
        if cut_sponsors and (start_time or end_time):
            # SponsorBlock times refer to the whole video; yt-dlp would apply
            # them unshifted to the trimmed file and cut the wrong parts.
            cut_sponsors = False
            warning = ("SponsorBlock was skipped: it can't be combined with a clip "
                       "start/end time.")
            warn("sponsorblock_skipped", warning)
        pps = _build_postprocessors(opts, embed_subs=embed_subs, cut_sponsors=cut_sponsors)
        if want_audio:
            fmt = "bestaudio/best"
            pps.insert(0, {
                "key": "FFmpegExtractAudio",
                "preferredcodec": AUDIO_FORMAT_MAP.get(audio_fmt, "mp3"),
                "preferredquality": AUDIO_QUALITY_MAP.get(
                    _opt_str(opts, "audio_quality", "best").lower(), "0"),
            })
        else:
            fmt, ydl_opts["merge_output_format"] = _merged_format(quality, container)
            fmt = custom_format or fmt
    else:
        if start_time or end_time:
            raise RuntimeError("Trimming (start/end time) needs ffmpeg, which isn't installed.")
        pps = []
        if want_audio:
            fmt = NO_FFMPEG_AUDIO_FORMAT
            warning = (f"ffmpeg isn't installed, so the audio is saved in its original format "
                       f"instead of {audio_fmt.upper()}, without embedded artwork or tags.")
        else:
            fmt = custom_format or _single_file_format(quality)
            warning = ("ffmpeg isn't installed, so only a ready-made single file can be "
                       "downloaded. Sites that serve video and audio separately (YouTube) "
                       "will fail until ffmpeg is installed.")
        log.info(warning)
        warn("ffmpeg_missing", warning)
    ydl_opts["format"] = fmt
    ydl_opts["postprocessors"] = pps
    log.debug(f"ydl format={fmt} postprocessors={pps}")
    if embed_thumb:
        # yt-dlp only embeds a thumbnail it wrote to disk itself. Kept after
        # embedding (already_have_thumbnail), that .jpg next to the media file
        # is also the vault's sidecar thumbnail.
        ydl_opts["writethumbnail"] = True
        ydl_opts["outtmpl"] = {"default": outtmpl, "pl_thumbnail": ""}

    if mode == "library":
        # Use public mellow_archive.txt; migrate old hidden files and backfill
        # from existing media files so yt-dlp skips already-downloaded items.
        import vault as _vault
        _vault.generate_archive(str(out_dir))
        ydl_opts["download_archive"] = str(out_dir / "mellow_archive.txt")
        ydl_opts["ignoreerrors"] = True

    if embed_subs:
        # With ffmpeg, _build_postprocessors added the FFmpegEmbedSubtitle step
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = opts.get("auto_subs", False)
        ydl_opts["subtitleslangs"] = [
            s.strip() for s in _opt_str(opts, "sub_langs", "en").split(",") if s.strip()]

    _apply_cookie_opts(ydl_opts, opts)
    if opts.get("rate_limit"):
        rate = _rate_limit(opts["rate_limit"])
        if rate:
            ydl_opts["ratelimit"] = rate
        else:
            log.warning(f"ignoring unparsable rate_limit {opts['rate_limit']!r}")
    _apply_network_opts(ydl_opts, opts)
    if _opt_str(opts, "external_downloader"):
        ydl_opts["external_downloader"] = _opt_str(opts, "external_downloader")
    frags = _safe_int(opts.get("concurrent_fragments", 4))
    if frags and frags > 1:
        ydl_opts["concurrent_fragment_downloads"] = frags
    sleep_i = _safe_int(opts.get("sleep_interval", 0))
    if sleep_i and sleep_i > 0:
        ydl_opts["sleep_interval"] = sleep_i
    retries = _safe_int(opts.get("retries"))
    if retries is not None:
        ydl_opts["retries"] = retries

    if start_time or end_time:
        ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
            None, [_clip_range(start_time, end_time)])
        ydl_opts["force_keyframes_at_cuts"] = True

    playlist_items = _opt_str(opts, "playlist_items")
    playlist_start = _safe_int(opts.get("playlist_start"))
    playlist_end = _safe_int(opts.get("playlist_end"))
    if playlist_items:
        ydl_opts["playlist_items"] = playlist_items
    elif playlist_start:
        ydl_opts["playliststart"] = playlist_start
    if playlist_end:
        ydl_opts["playlistend"] = playlist_end
    for key, ydl_key in (("date_before", "datebefore"), ("date_after", "dateafter")):
        if _opt_str(opts, key):
            ydl_opts[ydl_key] = _opt_str(opts, key).replace("-", "")

    # For playlist-like downloads: skip geo-blocked/failed items instead of aborting
    if playlist_items or "list=" in url or "/playlist" in url.lower():
        ydl_opts["ignoreerrors"] = True
    return ydl_opts, warning


def _saved_file(info: dict | None) -> dict:
    """Title, uploader, duration, thumbnail, path and size of a single download.

    Defensive: a yt-dlp update changing the info_dict shape must degrade to
    "no file path recorded", not fail a finished download.
    """
    result: dict = {"title": None, "uploader": None, "duration": None,
                    "thumbnail": None, "path": None, "size": 0}
    if not info:
        return result
    try:
        result.update(title=info.get("title"),
                      uploader=info.get("uploader") or info.get("channel"),
                      duration=info.get("duration"), thumbnail=info.get("thumbnail"))
        requested = info.get("requested_downloads") or [{}]
        if requested and isinstance(requested[0], dict):
            # The saved file's own length: shorter than the video when sponsor
            # segments were cut out of it
            result["duration"] = requested[0].get("duration") or result["duration"]
            fp = requested[0].get("filepath") or requested[0].get("_filename")
            if fp:
                result["path"] = fp
                try:
                    result["size"] = Path(fp).stat().st_size
                except OSError:
                    result["size"] = info.get("filesize") or 0
    except Exception as shape_exc:
        log.warning(f"info_dict shape unexpected: {shape_exc}")
    return result


def _playlist_records(info: dict, base: dict, item_stats: dict, wanted_ext: str,
                      avg_speed: int | None, elapsed: int) -> list[dict]:
    """One history row per playlist entry whose file is on disk."""
    rows = []
    for entry in info.get("entries") or []:
        if not entry:
            continue
        req = entry.get("requested_downloads") or [{}]
        fp = (req[0].get("filepath") or req[0].get("_filename")) if req else None
        if not fp:
            continue
        try:
            size = Path(fp).stat().st_size
        except OSError:
            # Extracted but never written: this item's download failed
            # (already reported as item_failed) or a filter skipped it.
            # It is not a successful download and gets no sidecar.
            continue
        thumb = entry.get("thumbnail")
        if thumb:
            _save_thumbnail_sidecar(fp, thumb)
        # Per-item timing captured by the progress hook — the playlist totals
        # would otherwise corrupt speed/duration stats.
        per_item = item_stats.get(entry.get("id"), {})
        rows.append({
            **base,
            "url": entry.get("webpage_url") or entry.get("url", ""),
            "title": entry.get("title"),
            "uploader": entry.get("uploader") or entry.get("channel"),
            "duration_seconds": req[0].get("duration") or entry.get("duration"),
            "file_size_bytes": size,
            "container": _file_ext(fp, wanted_ext),
            "file_path": fp,
            "thumbnail_url": thumb,
            "status": "success",
            "download_speed_avg_bps": per_item.get("speed", avg_speed),
            "elapsed_seconds": per_item.get("elapsed", elapsed),
        })
    return rows


def _download_video(
    url: str,
    output_dir: str,
    opts: dict,
    progress_cb: Callable,
    library_id: str | None,
    cancel_event: threading.Event | None,
    pause_event: threading.Event | None,
) -> str:
    owns_pause = pause_event is None
    if cancel_event is None:
        cancel_event = threading.Event()
    if pause_event is None:
        pause_event = _pause_event
    if owns_pause:
        # A pause left set by a previous download must never carry into this one
        pause_event.clear()
    t_start = time.monotonic()
    speed_tracker: dict = {"samples": [], "t0": t_start, "item_t0": t_start,
                           "item_sample_start": 0, "items": {}}

    def _record(meta: dict) -> None:
        if not opts.get("write_metadata", True):
            return
        try:
            analytics.record_download(meta)
        except Exception as rec_exc:
            log.warning(f"history record failed: {rec_exc}")

    progress_cb({"status": "starting", "url": url, "library_id": library_id})

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mode = _opt_str(opts, "mode", "video").lower()
    quality = _opt_str(opts, "quality", "best")
    ffmpeg = find_ffmpeg()
    want_audio = mode == "audio" or (mode == "library" and bool(opts.get("sync_audio", False)))
    media_kind = "audio" if want_audio else "video"
    wanted_ext = (_opt_str(opts, "audio_format", "mp3") if want_audio
                  else _opt_str(opts, "container", "mp4")).lower()
    embed_thumb = bool(ffmpeg and opts.get("embed_thumbnail"))
    ydl_opts, warning = _build_ydl_opts(
        url, out_dir, opts, ffmpeg=ffmpeg, want_audio=want_audio, embed_thumb=embed_thumb,
        warn=lambda code, message: progress_cb({"status": "warning", "code": code,
                                                "message": message, "library_id": library_id}))
    ydl_opts["progress_hooks"] = [_make_progress_hook(
        progress_cb, library_id, speed_tracker, cancel_event, pause_event,
        save_sidecar=not embed_thumb)]
    logger: _GeoBlockLogger | None = None
    if ydl_opts.get("ignoreerrors"):
        # With ignoreerrors yt-dlp only logs failures; the logger turns them
        # into item_failed events and keeps the last message for reporting.
        logger = _GeoBlockLogger(progress_cb, library_id)
        ydl_opts["logger"] = logger

    base = {"url": url, "platform": _detect_platform(url), "format": media_kind, "quality": quality}
    saved = _saved_file(None)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if embed_thumb:
                # Added last so it runs after audio extraction and metadata
                ydl.add_post_processor(
                    _EmbedThumbnailBestEffort(ydl, already_have_thumbnail=True),
                    when="post_process")
            info = ydl.extract_info(url, download=True)
            if getattr(ydl, "_download_retcode", 0) and not speed_tracker.get("finished"):
                # ignoreerrors swallowed every failure (dead or private
                # playlist, or each item refused with e.g. HTTP 403). Surface
                # it instead of reporting an empty download as "complete".
                # Items skipped via the archive log no error, so an
                # up-to-date sync still counts as success.
                raise yt_dlp.utils.DownloadError(
                    (logger.last_error if logger else None)
                    or "Nothing could be downloaded from this URL")
            saved = _saved_file(info)

        elapsed = int(time.monotonic() - t_start)
        samples = speed_tracker["samples"]
        avg_speed = int(sum(samples) / len(samples)) if samples else None

        if cancel_event.is_set():
            progress_cb({"status": "cancelled"})
            _record({**base, "title": saved["title"], "uploader": saved["uploader"],
                     "duration_seconds": saved["duration"], "status": "cancelled",
                     "elapsed_seconds": elapsed})
            return "cancelled"

        progress_cb({
            "status": "complete",
            "title": saved["title"] or url,
            "file_path": saved["path"],
            "file_size": saved["size"],
            "library_id": library_id,
            "warning": warning,
        })

        if info and ("entries" in info or info.get("_type") == "playlist"):
            rows = _playlist_records(info, base, speed_tracker.get("items", {}), wanted_ext,
                                     avg_speed, elapsed)
        elif not (saved["path"] and Path(saved["path"]).is_file()):
            # Nothing was saved: the archive already had it (a sync that is up
            # to date). A "success" row without a file inflated the stats and
            # made "already downloaded" report the file as moved.
            rows = []
        else:
            if saved["thumbnail"]:
                _save_thumbnail_sidecar(saved["path"], saved["thumbnail"])
            rows = [{
                **base, "title": saved["title"], "uploader": saved["uploader"],
                "duration_seconds": saved["duration"], "file_size_bytes": saved["size"],
                "container": _file_ext(saved["path"], wanted_ext), "file_path": saved["path"],
                "thumbnail_url": saved["thumbnail"], "status": "success",
                "download_speed_avg_bps": avg_speed, "elapsed_seconds": elapsed,
            }]
        for row in rows:
            _record(row)
        return "success"

    except yt_dlp.utils.DownloadCancelled:
        progress_cb({"status": "cancelled"})
        _record({**base, "title": saved["title"], "status": "cancelled",
                 "elapsed_seconds": int(time.monotonic() - t_start)})
        return "cancelled"
    except Exception as exc:
        msg = str(exc)
        event = {"status": "error", "message": msg, "url": url, "library_id": library_id}
        if not ffmpeg and not want_audio:
            # Without ffmpeg the usual cause is the missing merge step, not the site
            msg = f"{msg} — {NO_FFMPEG_ERROR_HINT}"
            event.update(message=msg, code="ffmpeg_missing")
        # url included so the frontend can offer a one-click retry
        progress_cb(event)
        _record({**base, "title": saved["title"], "uploader": saved["uploader"],
                 "status": "error", "error_message": msg,
                 "elapsed_seconds": int(time.monotonic() - t_start)})
        return "error"
    finally:
        if owns_pause:
            # Never leak pause state into the next download
            pause_event.clear()


def _apply_network_opts(ydl_opts: dict, opts: dict) -> None:
    """Proxy and IP family — applied to analyze, playlist listing and
    downloads alike, so a proxy isn't bypassed just for the first request."""
    proxy = str(opts.get("proxy") or "").strip()
    if proxy:
        ydl_opts["proxy"] = proxy
    if opts.get("force_ipv4"):
        # A broken IPv6 route makes every request hang for minutes before
        # falling back; binding to 0.0.0.0 is yt-dlp's --force-ipv4
        ydl_opts["source_address"] = "0.0.0.0"
    ydl_opts.setdefault("socket_timeout", SOCKET_TIMEOUT_SECS)


def _apply_cookie_opts(ydl_opts: dict, cookie_opts: dict) -> None:
    browser = _opt_str(cookie_opts, "cookies_browser")
    profile = _opt_str(cookie_opts, "cookies_browser_profile") or None
    cookie_file = _opt_str(cookie_opts, "cookies_file")
    if browser and browser.lower() != "none":
        ydl_opts["cookiesfrombrowser"] = (browser.lower(), profile, None, None)
    elif cookie_file:
        ydl_opts["cookiefile"] = cookie_file


def get_video_info(url: str, cookie_opts: dict | None = None) -> dict:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
    }
    if cookie_opts:
        _apply_cookie_opts(ydl_opts, cookie_opts)
        _apply_network_opts(ydl_opts, cookie_opts)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return {}
    is_playlist = info.get("_type") == "playlist" or "entries" in info
    playlist_count = 0
    thumbnail = info.get("thumbnail")
    if is_playlist:
        entries = info.get("entries") or []
        playlist_count = len(entries)
        # For playlists, yt-dlp may not return a playlist-level thumbnail; fall back to first entry
        if not thumbnail and entries:
            first = entries[0]
            if first:
                thumbnail = first.get("thumbnail") or ""
    return {
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "thumbnail": thumbnail,
        "duration": info.get("duration"),
        "platform": _detect_platform(url),
        "is_playlist": is_playlist,
        "playlist_count": playlist_count,
        "id": info.get("id"),
        "webpage_url": info.get("webpage_url") or url,
    }


def get_playlist_items(url: str, cookie_opts: dict | None = None) -> list[dict]:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": False,
    }
    if cookie_opts:
        _apply_cookie_opts(ydl_opts, cookie_opts)
        _apply_network_opts(ydl_opts, cookie_opts)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return []
    entries = info.get("entries") or []
    items = []
    for i, e in enumerate(entries):
        if not e:
            continue
        thumbs = e.get("thumbnails") or []
        thumb_url = e.get("thumbnail") or (thumbs[-1].get("url") if thumbs else "")
        items.append({
            "idx": i + 1,
            "id": e.get("id", ""),
            "title": e.get("title") or e.get("url", ""),
            "url": e.get("url") or e.get("webpage_url") or "",
            "thumbnail": thumb_url,
            "duration": e.get("duration"),
            "uploader": e.get("uploader") or e.get("channel", ""),
        })
    return items

