from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

import yt_dlp

import analytics

QUALITY_MAP: dict[str, str] = {
    "best": "bestvideo+bestaudio/best",
    "4k": "bestvideo[height<=2160]+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best",
    "720p": "bestvideo[height<=720]+bestaudio/best",
    "480p": "bestvideo[height<=480]+bestaudio/best",
    "360p": "bestvideo[height<=360]+bestaudio/best",
}

AUDIO_FORMAT_MAP: dict[str, str] = {
    "mp3": "mp3",
    "aac": "aac",
    "flac": "flac",
    "m4a": "m4a",
    "opus": "opus",
    "wav": "wav",
}

_cancel_event = threading.Event()
_lock = threading.Lock()


def cancel_download() -> None:
    _cancel_event.set()


def _is_cancelled() -> bool:
    return _cancel_event.is_set()


def _reset_cancel() -> None:
    _cancel_event.clear()


def _make_progress_hook(progress_cb: Callable, library_id: str | None, speed_tracker: dict) -> Callable:
    def hook(d: dict) -> None:
        if _is_cancelled():
            raise yt_dlp.utils.DownloadCancelled()
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = round((downloaded / total * 100) if total else 0, 1)
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            filename = Path(d.get("filename", "")).name
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
            })
        elif status == "finished":
            progress_cb({"status": "processing", "library_id": library_id})

    return hook


def _build_postprocessors(opts: dict) -> list[dict]:
    pps: list[dict] = []
    if opts.get("embed_thumbnail"):
        pps.append({"key": "EmbedThumbnail"})
    if opts.get("embed_chapters") or opts.get("embed_metadata"):
        pps.append({
            "key": "FFmpegMetadata",
            "add_chapters": bool(opts.get("embed_chapters")),
            "add_metadata": bool(opts.get("embed_metadata")),
        })
    if opts.get("sponsorblock"):
        pps.append({
            "key": "SponsorBlock",
            "categories": ["sponsor", "intro", "outro", "selfpromo"],
        })
    if opts.get("split_chapters"):
        pps.append({"key": "FFmpegSplitChapters"})
    return pps


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


def download_video(
    url: str,
    output_dir: str,
    opts: dict,
    progress_cb: Callable,
    library_id: str | None = None,
) -> None:
    _reset_cancel()
    t_start = time.monotonic()
    speed_tracker: dict = {"samples": []}
    progress_cb({"status": "starting", "url": url, "library_id": library_id})

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mode = opts.get("mode", "video").lower()
    quality = opts.get("quality", "best")
    container = opts.get("container", "mp4").lower()
    audio_fmt = opts.get("audio_format", "mp3").lower()
    custom_format = opts.get("custom_format", "").strip()
    start_time = opts.get("start_time", "").strip()
    end_time = opts.get("end_time", "").strip()
    cookies_browser = opts.get("cookies_browser", "")
    cookies_file = opts.get("cookies_file", "")
    rate_limit = opts.get("rate_limit", "")
    proxy = opts.get("proxy", "")
    ext_downloader = opts.get("external_downloader", "")
    concurrent_frags = opts.get("concurrent_fragments", 4)
    sleep_interval = opts.get("sleep_interval", 0)
    embed_subs = opts.get("embed_subs", False)
    sub_langs = opts.get("sub_langs", "en")
    playlist_start = opts.get("playlist_start")
    playlist_end = opts.get("playlist_end")
    date_before = opts.get("date_before", "")
    date_after = opts.get("date_after", "")
    filename_template = opts.get("filename_template", "").strip()

    if filename_template:
        outtmpl = str(out_dir / filename_template)
    else:
        outtmpl = str(out_dir / "%(title)s [%(id)s].%(ext)s")

    hook = _make_progress_hook(progress_cb, library_id, speed_tracker)

    if mode == "audio":
        fmt = "bestaudio/best"
        pps = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": AUDIO_FORMAT_MAP.get(audio_fmt, "mp3"),
            "preferredquality": "0",
        }]
        pps += _build_postprocessors(opts)
        ydl_opts: dict[str, Any] = {
            "format": fmt,
            "outtmpl": outtmpl,
            "postprocessors": pps,
            "progress_hooks": [hook],
            "noplaylist": True,
        }
    elif mode == "library":
        archive_path = str(out_dir / f".mellow_archive_{library_id}.txt")
        pps = _build_postprocessors(opts)
        ydl_opts = {
            "format": custom_format if custom_format else "bv+ba/b",
            "format_sort": ["vcodec:h264,res:1080,acodec:aac"],
            "outtmpl": outtmpl,
            "postprocessors": pps,
            "progress_hooks": [hook],
            "download_archive": archive_path,
            "ignoreerrors": True,
        }
    else:
        fmt = custom_format if custom_format else QUALITY_MAP.get(quality, "bestvideo+bestaudio/best")
        pps = _build_postprocessors(opts)
        ydl_opts = {
            "format": fmt,
            "merge_output_format": container,
            "outtmpl": outtmpl,
            "postprocessors": pps,
            "progress_hooks": [hook],
        }

    if embed_subs and mode != "audio":
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = opts.get("auto_subs", False)
        ydl_opts["subtitleslangs"] = [s.strip() for s in sub_langs.split(",") if s.strip()]
        ydl_opts.setdefault("postprocessors", []).append(
            {"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False}
        )

    if cookies_browser and cookies_browser.lower() not in ("none", ""):
        ydl_opts["cookiesfrombrowser"] = (cookies_browser.lower(),)
    elif cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    if rate_limit:
        ydl_opts["ratelimit"] = rate_limit
    if proxy:
        ydl_opts["proxy"] = proxy
    if ext_downloader:
        ydl_opts["external_downloader"] = ext_downloader
    if concurrent_frags and int(concurrent_frags) > 1:
        ydl_opts["concurrent_fragment_downloads"] = int(concurrent_frags)
    if sleep_interval and int(sleep_interval) > 0:
        ydl_opts["sleep_interval"] = int(sleep_interval)

    if start_time or end_time:
        start_sec = _parse_time(start_time) if start_time else None
        end_sec = _parse_time(end_time) if end_time else None
        ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
            None, [{"start_time": start_sec, "end_time": end_sec}]
        )
        ydl_opts["force_keyframes_at_cuts"] = True

    if playlist_start:
        ydl_opts["playliststart"] = int(playlist_start)
    if playlist_end:
        ydl_opts["playlistend"] = int(playlist_end)
    if date_before:
        ydl_opts["datebefore"] = date_before.replace("-", "")
    if date_after:
        ydl_opts["dateafter"] = date_after.replace("-", "")

    final_path: str | None = None
    final_size: int = 0
    final_title: str | None = None
    final_uploader: str | None = None
    final_duration: int | None = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                final_title = info.get("title")
                final_uploader = info.get("uploader") or info.get("channel")
                final_duration = info.get("duration")
                requested = info.get("requested_downloads", [{}])
                if requested:
                    fp = requested[0].get("filepath") or requested[0].get("_filename")
                    if fp:
                        final_path = fp
                        try:
                            final_size = Path(fp).stat().st_size
                        except OSError:
                            final_size = info.get("filesize") or 0

        elapsed = time.monotonic() - t_start
        samples = speed_tracker["samples"]
        avg_speed = int(sum(samples) / len(samples)) if samples else None
        elapsed_int = int(elapsed)

        if _is_cancelled():
            progress_cb({"status": "cancelled"})
            analytics.record_download({
                "url": url, "title": final_title, "uploader": final_uploader,
                "platform": _detect_platform(url), "duration_seconds": final_duration,
                "status": "cancelled",
                "elapsed_seconds": elapsed_int,
            })
            return

        progress_cb({
            "status": "complete",
            "title": final_title or url,
            "file_path": final_path,
            "file_size": final_size,
            "library_id": library_id,
        })
        analytics.record_download({
            "url": url, "title": final_title, "uploader": final_uploader,
            "platform": _detect_platform(url), "duration_seconds": final_duration,
            "file_size_bytes": final_size,
            "format": "audio" if mode == "audio" else "video",
            "quality": quality,
            "container": audio_fmt if mode == "audio" else container,
            "file_path": final_path,
            "status": "success",
            "download_speed_avg_bps": avg_speed,
            "elapsed_seconds": elapsed_int,
        })

    except yt_dlp.utils.DownloadCancelled:
        elapsed = time.monotonic() - t_start
        progress_cb({"status": "cancelled"})
        analytics.record_download({
            "url": url, "title": final_title, "platform": _detect_platform(url),
            "status": "cancelled", "elapsed_seconds": int(elapsed),
        })
    except Exception as exc:
        elapsed = time.monotonic() - t_start
        msg = str(exc)
        progress_cb({"status": "error", "message": msg, "library_id": library_id})
        analytics.record_download({
            "url": url, "title": final_title, "uploader": final_uploader,
            "platform": _detect_platform(url),
            "format": "audio" if mode == "audio" else "video",
            "quality": quality,
            "status": "error",
            "error_message": msg,
            "elapsed_seconds": int(elapsed),
        })


def get_video_info(url: str) -> dict:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return {}
    is_playlist = info.get("_type") == "playlist" or "entries" in info
    playlist_count = 0
    if is_playlist:
        entries = info.get("entries") or []
        playlist_count = len(entries)
    return {
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "platform": _detect_platform(url),
        "is_playlist": is_playlist,
        "playlist_count": playlist_count,
    }


def download_in_thread(
    url: str,
    output_dir: str,
    opts: dict,
    progress_cb: Callable,
    library_id: str | None = None,
) -> threading.Thread:
    t = threading.Thread(
        target=download_video,
        args=(url, output_dir, opts, progress_cb, library_id),
        daemon=True,
    )
    t.start()
    return t
