from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

from . import (
    analytics,
    app_update,
    applog,
    desktop,
    downloader,
    errors,
    jobs,
    scheduler,
    ytdlp_update,
)
from . import backup as _backup
from . import library as _library
from . import vault as _vault
from .config import (
    download_root,
    download_settings,
    load_config,
    request_settings,
    reset_settings,
    update_config,
)
from .constants import (
    APP_RELEASES_PAGE,
    HISTORY_DEFAULT_LIMIT,
    HISTORY_MAX_LIMIT,
    LOW_DISK_WARN_BYTES,
    MEDIA_EXTS,
    MEDIA_MIME,
    SSE_PING_INTERVAL_SECS,
    SSE_QUEUE_MAXSIZE,
    THUMB_CACHE_SECS,
    WEBHOOK_TIMEOUT_SECS,
)
from .ffmpeg_locate import find_ffmpeg
from .version import APP_VERSION

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = Flask(__name__, static_folder=None)

# ── SSE broadcast ──────────────────────────────────────────────────────────────
# One queue per connected client. A single shared queue meant each event went
# to exactly one consumer, so a second EventSource (Signal page live stream,
# or a stale generator after reconnect) silently ate half the UI's events.
_sse_subscribers: list[queue.Queue] = []
_sse_lock = threading.Lock()


def _sse_subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=SSE_QUEUE_MAXSIZE)
    with _sse_lock:
        _sse_subscribers.append(q)
    return q


def _sse_unsubscribe(q: queue.Queue) -> None:
    with _sse_lock:
        if q in _sse_subscribers:
            _sse_subscribers.remove(q)


# ── Download job queue ────────────────────────────────────────────────────────
# Owned by jobs.JobManager (worker pool, reordering, persistence). The alias
# keeps call sites readable.
_enqueue_job = jobs.manager.enqueue


def _fire_webhooks(event_type: str, payload: dict) -> None:
    try:
        cfg = load_config()
        urls = cfg.get("webhooks", {}).get(event_type, [])
        body = json.dumps({"event": event_type,
                           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "data": payload}).encode()
        for wh_url in urls:
            try:
                req = Request(wh_url, data=body, method="POST",
                              headers={"Content-Type": "application/json"})
                urlopen(req, timeout=WEBHOOK_TIMEOUT_SECS)
            except Exception as wh_exc:
                log.warning(f"webhook {event_type} → {wh_url} failed: {wh_exc}")
    except Exception as exc:
        log.warning(f"webhooks for {event_type} not sent: {exc}")


def _push_progress(event: dict) -> None:
    with _sse_lock:
        subs = list(_sse_subscribers)
    for q in subs:
        try:
            q.put_nowait(event)
        except queue.Full:
            # Stalled client: drop oldest so live consumers aren't blocked
            try:
                q.get_nowait()
                q.put_nowait(event)
            except (queue.Empty, queue.Full):
                pass
    status = event.get("status")
    if status in ("complete", "error"):
        threading.Thread(target=_fire_webhooks, args=(status, event), daemon=True).start()


def _queue_finished(done: list[dict]) -> None:
    """The queue ran dry after downloading something: tell the UI, and open
    the folder when Config asks for it."""
    _push_progress({"status": "queue_done", "count": len(done),
                    "folders": sorted({j["output_dir"] for j in done})})
    if load_config().get("on_queue_done") == "open_folder":
        desktop.show_in_folder(done[-1]["output_dir"])


jobs.manager.start(_push_progress, on_idle=_queue_finished)


def _library_entry_for(path: str, cfg: dict) -> dict | None:
    """The library entry whose download folder is `path`, if any."""
    root = download_root(cfg)
    return next((e for e in analytics.get_library_entries()
                 if _library.folder_path_for_entry(e, root) == path), None)


def _enqueue_vault_sync(path: str, data: dict | None = None,
                        requested_urls: list | None = None) -> dict | None:
    """Build sync opts and enqueue a sync job for a linked vault folder.

    Shared by the sync endpoints and the auto-sync scheduler. Returns the
    job, or None when the folder has no (matching) linked playlists.
    """
    data = data or {}
    cfg = load_config()
    vp = cfg.get("vault_playlists", {}).get(path, [])
    if not vp:
        return None
    playlist_urls = [u for u in list(vp) if u in requested_urls] if requested_urls else list(vp)
    if not playlist_urls:
        return None
    lib = _library_entry_for(path, cfg)
    opts = _vault.build_sync_opts(data, lib, cfg, path)
    library_id = lib["id"] if lib else None
    if any(k in data for k in _vault.SYNC_FORMAT_KEYS):
        update_config(lambda c: _vault.remember_sync_format(c, path, data))
    label = f"Sync — {Path(path).name} ({len(playlist_urls)} playlist(s))"
    return _enqueue_job(playlist_urls[0] if len(playlist_urls) == 1 else path,
                        path, opts, library_id, job_type="sync", label=label,
                        multi_urls=playlist_urls, sync_path=path)


scheduler.start(
    sync_fn=lambda path: _enqueue_vault_sync(path) is not None,
    is_syncing_fn=jobs.manager.has_sync_for,
)


# ── Cross-origin write protection ─────────────────────────────────────────────
# All endpoints parse JSON with force=True, which also accepts text/plain —
# the content type a cross-origin "simple" POST can send without a CORS
# preflight. Requiring a JSON content type (and a local Origin when present)
# stops any website you visit from poking /api/download, /api/config, etc.

# Endpoints that legitimately receive non-JSON bodies (file uploads). They
# are still covered by the Origin check above.
_MULTIPART_ALLOWED_PATHS = frozenset({"/api/backup/restore"})
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


@app.before_request
def _local_host_guard() -> Response | None:
    """Answer only requests addressed to this machine.

    DNS rebinding: a web page whose domain is switched to 127.0.0.1 can make
    same-origin GETs to this server and read the answers (config, clipboard,
    history). Its requests still carry its own name in the Host header.
    """
    try:
        host = urlparse("//" + request.host).hostname
    except ValueError:
        host = None
    if host not in _LOCAL_HOSTS:
        return jsonify({"error": "Requests must be addressed to localhost"}), 403
    return None


@app.before_request
def _api_write_guard() -> Response | None:
    if request.method not in ("POST", "PUT", "DELETE") or not request.path.startswith("/api/"):
        return None
    origin = request.headers.get("Origin")
    if origin:
        try:
            host = urlparse(origin).hostname
        except ValueError:
            host = None
        if host not in _LOCAL_HOSTS:
            return jsonify({"error": "Cross-origin requests are not allowed"}), 403
    if request.path in _MULTIPART_ALLOWED_PATHS:
        return None
    if request.content_length and not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415
    return None


# ── Static ────────────────────────────────────────────────────────────────────

@app.route("/")
def index() -> Response:
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/static/<path:filename>")
def static_files(filename: str) -> Response:
    return send_from_directory(str(STATIC_DIR), filename)


@app.route("/<path:filename>")
def static_root(filename: str) -> Response:
    target = STATIC_DIR / filename
    if target.exists() and target.is_file():
        return send_from_directory(str(STATIC_DIR), filename)
    return send_from_directory(str(STATIC_DIR), "index.html")


# ── System ────────────────────────────────────────────────────────────────────

@app.route("/api/clipboard")
def api_clipboard() -> Response:
    return jsonify({"text": desktop.clipboard_text()})


@app.route("/api/open-folder", methods=["POST"])
def api_open_folder() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "")
    if path:
        threading.Thread(target=desktop.show_in_folder, args=(path,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/browse-file", methods=["POST"])
def api_browse_file() -> Response:
    if not desktop.tkinter_available:
        return jsonify({"path": "", "error": "File dialogs unavailable (tkinter missing)"})
    data = request.get_json(force=True) or {}
    return jsonify({"path": desktop.ask_open_file(data.get("filter", ""))})


@app.route("/api/read-url-file", methods=["POST"])
def api_read_url_file() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    if not path or not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 400
    if Path(path).suffix.lower() != ".txt":
        return jsonify({"error": "Only .txt files are supported"}), 400
    try:
        content = open(path, encoding="utf-8", errors="ignore").read()
        urls, fmt = downloader.parse_url_file(content)
        return jsonify({"urls": urls, "format": fmt, "count": len(urls)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/browse-folder", methods=["POST"])
def api_browse_folder() -> Response:
    if not desktop.tkinter_available:
        return jsonify({"path": "", "error": "File dialogs unavailable (tkinter missing)"})
    data = request.get_json(force=True) or {}
    return jsonify({"path": desktop.ask_folder(data.get("initial") or str(Path.home()))})


@app.route("/api/system")
def api_system() -> Response:
    ytdlp_version = "unknown"
    try:
        import yt_dlp
        ytdlp_version = yt_dlp.version.__version__
    except Exception:
        pass
    # Same lookup the downloader uses, so the status light can't disagree
    # with what a download will actually do.
    ffmpeg_path = find_ffmpeg()
    disk_free = _free_bytes_near(download_root(load_config()))
    return jsonify({
        "ffmpeg": ffmpeg_path is not None,
        "ffmpeg_path": ffmpeg_path,
        "ytdlp_version": ytdlp_version,
        "python_version": sys.version.split()[0],
        "app_version": APP_VERSION,
        "db_size_bytes": analytics.get_db_size(),
        "disk_free_bytes": disk_free,
        "disk_low": disk_free is not None and disk_free < LOW_DISK_WARN_BYTES,
        "log_path": str(applog.LOG_PATH),
    })


@app.route("/api/open-log", methods=["POST"])
def api_open_log() -> Response:
    """Open the log file (Config → About) — what to attach to a bug report."""
    if not applog.LOG_PATH.exists():
        return jsonify({"error": "No log file yet"}), 404
    threading.Thread(target=desktop.open_file, args=(str(applog.LOG_PATH),), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/check-app-update")
def api_check_app_update() -> Response:
    return jsonify(app_update.check())


@app.route("/api/open-release", methods=["POST"])
def api_open_release() -> Response:
    """Open the latest release page (a fixed URL: this can't open arbitrary pages)."""
    threading.Thread(target=desktop.open_url, args=(APP_RELEASES_PAGE,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/check-ytdlp-update")
def api_check_ytdlp_update() -> Response:
    return jsonify(ytdlp_update.check())


@app.route("/api/update-ytdlp", methods=["POST"])
def api_update_ytdlp() -> Response:
    threading.Thread(target=ytdlp_update.run_update, args=(_push_progress,), daemon=True).start()
    return jsonify({"status": "updating"})


# ── Config ────────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_config_get() -> Response:
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
def api_config_post() -> Response:
    data = request.get_json(force=True) or {}
    update_config(lambda cfg: cfg.update(data))
    return jsonify({"ok": True})


@app.route("/api/cookies/test", methods=["POST"])
def api_cookies_test() -> Response:
    """Load cookies with the settings in the request (the unsaved Config form)."""
    data = request.get_json(force=True) or {}
    result = downloader.test_cookies(request_settings(data))
    if not result["ok"]:
        return jsonify({**result, **(errors.explain(result["error"]) or {})}), 400
    return jsonify(result)


@app.route("/api/filename-preview", methods=["POST"])
def api_filename_preview() -> Response:
    result = downloader.preview_filename((request.get_json(force=True) or {}).get("template", ""))
    return jsonify(result), 200 if result["ok"] else 400


@app.route("/api/config/reset", methods=["POST"])
def api_config_reset() -> Response:
    return jsonify(reset_settings())


# ── Download ──────────────────────────────────────────────────────────────────

@app.route("/api/info", methods=["POST"])
def api_info() -> Response:
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        info = downloader.get_video_info(url, cookie_opts=request_settings(load_config()))
    except Exception as exc:
        return jsonify({"error": str(exc), **(errors.explain(str(exc)) or {})}), 500
    if info and not info.get("is_playlist"):
        # "You already have this": saves re-downloading the same video
        try:
            info["previous_download"] = analytics.find_previous_download(
                [url, info.get("webpage_url")], info.get("id"))
        except Exception as exc:
            log.warning(f"history lookup failed: {exc}")
    return jsonify(info)


@app.route("/api/download", methods=["POST"])
def api_download() -> Response:
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    cfg = load_config()
    output_dir = data.get("output_dir") or download_root(cfg)
    log.info(f"download queued: {url} -> {output_dir}")
    opts = {
        "mode": data.get("mode", "video"),
        "quality": data.get("quality", "best"),
        "container": data.get("container", "mp4"),
        "audio_format": data.get("audio_format", "mp3"),
        "audio_quality": data.get("audio_quality") or cfg.get("default_audio_quality", "best"),
        # A Feed download saved into a vault folder runs in library mode;
        # without this an AUDIO choice was downloaded as video
        "sync_audio": bool(data.get("sync_audio", False)),
        "embed_thumbnail": data.get("embed_thumbnail", True),
        "embed_chapters": data.get("embed_chapters", True),
        "embed_metadata": data.get("embed_metadata", True),
        "embed_subs": data.get("embed_subs", False),
        "sponsorblock": data.get("sponsorblock", False),
        "normalize_audio": bool(data.get("normalize_audio", False)),
        "split_chapters": data.get("split_chapters", False),
        "custom_format": data.get("custom_format", ""),
        "start_time": data.get("start_time", ""),
        "end_time": data.get("end_time", ""),
        "chapters": data.get("chapters") or [],
        "playlist_start": data.get("playlist_start"),
        "playlist_end": data.get("playlist_end"),
        "playlist_items": data.get("playlist_items", ""),
        "date_before": data.get("date_before", ""),
        "date_after": data.get("date_after", ""),
        "filename_template": data.get("filename_template", "") or cfg.get("filename_template", ""),
        **download_settings(cfg),
    }
    # "Later": held until the Config start time (see jobs.next_time_of_day)
    not_before = jobs.next_time_of_day(cfg.get("schedule_start", "")) if data.get("scheduled") else None
    multi_urls = data.get("multi_urls")
    if multi_urls and isinstance(multi_urls, list) and len(multi_urls) > 1:
        job = _enqueue_job(multi_urls[0], output_dir, opts, job_type="feed",
                           label=multi_urls[0], multi_urls=multi_urls, not_before=not_before)
    else:
        job = _enqueue_job(url, output_dir, opts, job_type="feed", label=url, not_before=not_before)
    resp = {"status": "scheduled" if not_before else "started", "job_id": job["id"],
            "not_before": not_before}
    free = _free_bytes_near(output_dir)
    if free is not None and free < LOW_DISK_WARN_BYTES:
        # Queued anyway; the user decides whether it will fit
        resp["disk_warning"] = f"Only {free / 1024 ** 3:.1f} GB free on the download drive."
    return jsonify(resp)


def _free_bytes_near(path: str) -> int | None:
    """Free space on the drive holding `path` (or its nearest existing parent)."""
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return shutil.disk_usage(str(p)).free
    except OSError:
        return None


@app.route("/api/cancel", methods=["POST"])
def api_cancel() -> Response:
    jobs.manager.cancel_active()
    return jsonify({"status": "cancelled"})


@app.route("/api/queue/<job_id>", methods=["DELETE"])
@app.route("/api/queue/<job_id>/cancel", methods=["POST"])
def api_queue_cancel_job(job_id: str) -> Response:
    job = jobs.manager.cancel(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] == "cancelled":
        return jsonify({"ok": True, "status": "cancelled"})
    # Active job: the downloader notices this job's own cancel event via its
    # progress hook
    return jsonify({"ok": True, "status": "cancelling"})


@app.route("/api/queue/<job_id>/retry", methods=["POST"])
def api_queue_retry(job_id: str) -> Response:
    """Run a finished job again, or one item of it (`url`), with the job's options."""
    url = ((request.get_json(force=True) or {}).get("url") or "").strip() or None
    job = jobs.manager.retry(job_id, url)
    if job is None:
        return jsonify({"error": "That job is no longer in the queue history"}), 404
    return jsonify({"ok": True, "job_id": job["id"]})


@app.route("/api/queue/<job_id>/start-now", methods=["POST"])
def api_queue_start_now(job_id: str) -> Response:
    """Run a job queued for later without waiting for its time."""
    if not jobs.manager.start_now(job_id):
        return jsonify({"error": "Job not queued (already running or unknown)"}), 404
    return jsonify({"ok": True})


@app.route("/api/queue/<job_id>/reorder", methods=["POST"])
def api_queue_reorder(job_id: str) -> Response:
    data = request.get_json(force=True) or {}
    try:
        new_index = int(data.get("index"))
    except (TypeError, ValueError):
        return jsonify({"error": "index (integer) required"}), 400
    if not jobs.manager.reorder(job_id, new_index):
        return jsonify({"error": "Job not queued (already running or unknown)"}), 404
    return jsonify({"ok": True})


@app.route("/api/queue/restorable", methods=["GET"])
def api_queue_restorable() -> Response:
    return jsonify({"jobs": [
        {"id": j.get("id"), "label": j.get("label"), "type": j.get("type"),
         "url": j.get("url")}
        for j in jobs.manager.restorable
    ]})


@app.route("/api/queue/restore", methods=["POST"])
def api_queue_restore() -> Response:
    """Re-enqueue jobs that were still pending when the app last exited."""
    restored = jobs.manager.restore_pending()
    return jsonify({"ok": True, "restored": len(restored), "job_ids": restored})


@app.route("/api/queue/restorable", methods=["DELETE"])
def api_queue_restorable_discard() -> Response:
    jobs.manager.discard_restorable()
    return jsonify({"ok": True})


@app.route("/api/download/pause", methods=["POST"])
def api_pause() -> Response:
    if not jobs.manager.has_active():
        # Nothing to pause; a stray flag would only desync the UI
        return jsonify({"status": "idle"})
    downloader.pause()
    _push_progress({"status": "paused"})
    return jsonify({"status": "paused"})


@app.route("/api/download/resume", methods=["POST"])
def api_resume() -> Response:
    downloader.resume()
    _push_progress({"status": "resumed"})
    return jsonify({"status": "resumed"})


@app.route("/api/progress")
def api_progress() -> Response:
    def generate():
        q = _sse_subscribe()
        try:
            while True:
                try:
                    event = q.get(timeout=SSE_PING_INTERVAL_SECS)
                    data = json.dumps(event)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield 'data: {"status":"ping"}\n\n'
        finally:
            # Client went away (GeneratorExit) — stop receiving events
            _sse_unsubscribe(q)
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/queue/status")
def api_queue_status() -> Response:
    return jsonify(jobs.manager.status())


# ── Webhooks ──────────────────────────────────────────────────────────────────

@app.route("/api/webhooks", methods=["GET"])
def api_webhooks_get() -> Response:
    cfg = load_config()
    return jsonify(cfg.get("webhooks", {"complete": [], "error": []}))


@app.route("/api/webhooks", methods=["POST"])
def api_webhooks_post() -> Response:
    data = request.get_json(force=True) or {}
    update_config(lambda cfg: cfg.__setitem__("webhooks", data))
    return jsonify({"ok": True})


# ── History ───────────────────────────────────────────────────────────────────

def _int_arg(name: str, default: int, lo: int = 0, hi: int = 10000) -> int:
    try:
        return max(lo, min(hi, int(request.args.get(name, default))))
    except (TypeError, ValueError):
        return default


@app.route("/api/history")
def api_history() -> Response:
    limit = _int_arg("limit", HISTORY_DEFAULT_LIMIT, 1, HISTORY_MAX_LIMIT)
    offset = _int_arg("offset", 0)
    type_filter = request.args.get("type", "all")
    search = request.args.get("search", "").strip() or None
    rows = analytics.get_history(limit, offset, type_filter if type_filter != "all" else None, search)
    return jsonify(rows)


@app.route("/api/history", methods=["DELETE"])
def api_history_delete() -> Response:
    data = request.get_json(force=True) or {}
    delete_all = data.get("all", False)
    count = analytics.delete_history(
        ids=data.get("ids"),
        older_than_days=data.get("older_than_days"),
        delete_all=delete_all,
    )
    if delete_all:
        analytics.clear_library()
        update_config(lambda cfg: cfg.__setitem__("stat_overrides", {}))
    return jsonify({"deleted": count})


# ── Stats / Analytics ─────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats() -> Response:
    time_range = request.args.get("range", "30d")
    result = analytics.get_stats(time_range)
    # Fix library count: combine library entries + vault_playlists with URLs
    cfg = load_config()
    vault_playlists = cfg.get("vault_playlists", {})
    vault_pl_count = sum(1 for urls in vault_playlists.values() if urls)
    # Use the larger of the two counts (library table vs vault_playlists config)
    result["library_playlists"] = max(result.get("library_playlists", 0), vault_pl_count)
    resp = jsonify(result)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/api/analytics/export")
def api_analytics_export() -> Response:
    csv_data = analytics.export_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=mellow_downloads.csv"},
    )


@app.route("/api/analytics/query", methods=["POST"])
def api_analytics_query() -> Response:
    data = request.get_json(force=True) or {}
    sql = data.get("sql", "").strip()
    if not sql:
        return jsonify({"error": "No SQL provided", "columns": [], "rows": []}), 400
    result = analytics.run_query(sql)
    return jsonify(result)


@app.route("/api/analytics/overrides", methods=["GET"])
def api_analytics_overrides_get() -> Response:
    cfg = load_config()
    return jsonify(cfg.get("stat_overrides", {}))


@app.route("/api/analytics/overrides", methods=["POST"])
def api_analytics_overrides_post() -> Response:
    data = request.get_json(force=True) or {}
    cfg = update_config(lambda c: c.setdefault("stat_overrides", {}).update(data))
    return jsonify({"ok": True, "overrides": cfg.get("stat_overrides", {})})


@app.route("/api/analytics/vacuum", methods=["POST"])
def api_analytics_vacuum() -> Response:
    try:
        analytics.vacuum()
        return jsonify({"ok": True, "db_size_bytes": analytics.get_db_size()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Vault ─────────────────────────────────────────────────────────────────────

@app.route("/api/vault")
def api_vault() -> Response:
    cfg = load_config()
    base_path = request.args.get("path") or download_root(cfg)
    folders = _vault.build_folder_list(base_path, cfg)
    return jsonify({"folders": folders, "base_path": base_path})


@app.route("/api/vault/watch", methods=["GET"])
def api_vault_watch_get() -> Response:
    cfg = load_config()
    return jsonify({"watched_folders": cfg.get("watched_folders", [])})


@app.route("/api/vault/watch", methods=["POST"])
def api_vault_watch_post() -> Response:
    data = request.get_json(force=True) or {}
    folder = data.get("path", "").strip()
    if not folder:
        return jsonify({"error": "No path provided"}), 400
    p = Path(folder)
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400
    def _add_watch(cfg: dict) -> None:
        watched = cfg.setdefault("watched_folders", [])
        if folder not in watched:
            watched.append(folder)
    cfg = update_config(_add_watch)
    archive_created = False
    if data.get("create_archive"):
        result = _vault.generate_archive(folder)
        archive_created = result.get("ok", False)
    return jsonify({"ok": True, "watched_folders": cfg.get("watched_folders", []),
                    "archive_created": archive_created})


@app.route("/api/vault/archive-generate", methods=["POST"])
def api_vault_archive_generate() -> Response:
    data = request.get_json(force=True) or {}
    folder = data.get("path", "").strip()
    if not folder or not os.path.isdir(folder):
        return jsonify({"error": "Invalid path"}), 400
    result = _vault.generate_archive(folder, prune=True)
    if not result["ok"]:
        return jsonify({"error": result.get("error")}), 500
    return jsonify(result)


@app.route("/api/vault/watch", methods=["DELETE"])
def api_vault_watch_delete() -> Response:
    data = request.get_json(force=True) or {}
    folder = data.get("path", "").strip()
    cfg = update_config(lambda c: c.__setitem__(
        "watched_folders", [w for w in c.get("watched_folders", []) if w != folder]))
    return jsonify({"ok": True, "watched_folders": cfg.get("watched_folders", [])})


@app.route("/api/vault/folder")
def api_vault_folder() -> Response:
    path = request.args.get("path", "")
    if not path or not Path(path).exists():
        return jsonify({"files": [], "path": path})
    files = _vault.list_folder_files(path)
    return jsonify({"files": files, "path": path, "folder_name": Path(path).name})


@app.route("/api/vault/thumb")
def api_vault_thumb() -> Response:
    path = request.args.get("path", "")
    if not path:
        return Response("", 404)
    result = _vault.get_thumb_bytes(path)
    if result is None:
        return Response("", 404)
    content, mime = result
    return Response(content, mimetype=mime, headers={"Cache-Control": f"max-age={THUMB_CACHE_SECS}"})


@app.route("/api/playlist-items", methods=["POST"])
def api_playlist_items() -> Response:
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        items = downloader.get_playlist_items(url, cookie_opts=request_settings(load_config()))
        return jsonify({"items": items})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/vault/open-file", methods=["POST"])
def api_vault_open_file() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "")
    if path and Path(path).exists():
        threading.Thread(target=desktop.open_file, args=(path,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/vault/play-files", methods=["POST"])
def api_vault_play_files() -> Response:
    data = request.get_json(force=True) or {}
    paths = data.get("paths", [])
    if not paths:
        return jsonify({"error": "No files provided"}), 400
    result = _vault.launch_playlist(paths, desktop.open_file)
    return jsonify({"status": "ok", "method": result})


@app.route("/api/vault/folder-previews")
def api_vault_folder_previews() -> Response:
    path = request.args.get("path", "")
    if not path or not Path(path).exists():
        return jsonify({"thumbs": []})
    return jsonify({"thumbs": _vault.get_folder_previews(path)})


@app.route("/api/vault/playlists", methods=["GET"])
def api_vault_playlists_get() -> Response:
    path = request.args.get("path", "")
    cfg = load_config()
    return jsonify({
        "playlists": cfg.get("vault_playlists", {}).get(path, []),
        # What a sync of this folder will use unless told otherwise — the
        # sync dialog starts from it instead of always offering 1080p video
        "sync_format": _vault.default_sync_format(path, _library_entry_for(path, cfg), cfg) if path else {},
    })


@app.route("/api/vault/playlists", methods=["POST"])
def api_vault_playlists_post() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    url_val = data.get("url", "").strip()
    if not path or not url_val:
        return jsonify({"error": "path and url required"}), 400
    fmt = data.get("sync_format") if isinstance(data.get("sync_format"), dict) else {}

    def _add_pl(cfg: dict) -> None:
        urls = cfg.setdefault("vault_playlists", {}).setdefault(path, [])
        if url_val not in urls:
            urls.append(url_val)
        _vault.remember_sync_format(cfg, path, fmt)
    cfg = update_config(_add_pl)
    return jsonify({"ok": True, "playlists": cfg["vault_playlists"][path]})


@app.route("/api/vault/playlists", methods=["DELETE"])
def api_vault_playlists_delete() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    url_val = data.get("url", "").strip()
    def _del_pl(cfg: dict) -> None:
        vp = cfg.setdefault("vault_playlists", {})
        if path in vp:
            vp[path] = [u for u in vp[path] if u != url_val]
            # Clear sync time when no playlists remain (avoids stale "Synced X ago")
            if not vp[path]:
                cfg.get("vault_sync_times", {}).pop(path, None)
    update_config(_del_pl)
    return jsonify({"ok": True})


@app.route("/api/vault/rename", methods=["POST"])
def api_vault_rename() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    name = data.get("name", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    def _rename(cfg: dict) -> None:
        vault_names = cfg.setdefault("vault_names", {})
        if name:
            vault_names[path] = name
        else:
            vault_names.pop(path, None)
    update_config(_rename)
    return jsonify({"ok": True})


@app.route("/api/vault/remove", methods=["POST"])
def api_vault_remove() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    def _remove(cfg: dict) -> None:
        # Remove from watched_folders if present
        cfg["watched_folders"] = [w for w in cfg.get("watched_folders", []) if w != path]
        # Add to vault_hidden so auto-discovered folders are suppressed
        hidden = cfg.setdefault("vault_hidden", [])
        if path not in hidden:
            hidden.append(path)
    update_config(_remove)
    return jsonify({"ok": True})


@app.route("/api/vault/file", methods=["DELETE"])
def api_vault_delete_file() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "")
    if not path:
        return jsonify({"error": "No path"}), 400
    p = Path(path)
    if not p.exists():
        return jsonify({"error": "File not found"}), 404
    if not p.is_file():
        return jsonify({"error": "Not a file"}), 400
    if p.suffix.lower() not in MEDIA_EXTS:
        return jsonify({"error": "Only media files can be deleted via this endpoint"}), 400
    try:
        _vault.delete_media_file(p)
    except OSError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})


@app.route("/api/vault/sync", methods=["POST"])
def api_vault_sync() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    # Sync time is stamped by the worker on successful completion, not here
    job = _enqueue_vault_sync(path, data, requested_urls=data.get("playlist_urls"))
    if job is None:
        return jsonify({"error": "No matching playlists linked to this folder"}), 400
    return jsonify({"ok": True, "queued": True, "job_id": job["id"],
                    "playlists_synced": len(job.get("multi_urls") or [])})


@app.route("/api/vault/sync-all", methods=["POST"])
def api_vault_sync_all() -> Response:
    """Sync all folders that have linked playlists (or a specified subset)."""
    data = request.get_json(force=True) or {}
    # Optional: client sends list of specific paths to sync; omit for all
    only_paths = data.get("paths")  # None = all linked folders
    cfg = load_config()
    vp = cfg.get("vault_playlists", {})
    folders_to_sync = [
        path for path, urls in vp.items()
        if urls and (only_paths is None or path in only_paths)
    ]
    if not folders_to_sync:
        return jsonify({"error": "No linked folders to sync"}), 400
    queued = [path for path in folders_to_sync if _enqueue_vault_sync(path) is not None]
    return jsonify({"ok": True, "queued": queued, "count": len(queued)})


@app.route("/api/vault/mirror-preview", methods=["POST"])
def api_vault_mirror_preview() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Invalid path"}), 400
    cfg = load_config()
    vp = cfg.get("vault_playlists", {}).get(path, [])
    if not vp:
        return jsonify({"error": "No playlist linked"}), 400
    result = _vault.get_mirror_preview(path, vp, request_settings(cfg))
    return jsonify(result), 500 if result.get("error") else 200


@app.route("/api/vault/mirror-confirm", methods=["POST"])
def api_vault_mirror_confirm() -> Response:
    data = request.get_json(force=True) or {}
    folder = (data.get("path") or "").strip()
    cfg = load_config()
    if not folder or folder not in cfg.get("vault_playlists", {}):
        return jsonify({"error": "path must be a vault folder with linked playlists"}), 400
    folder_resolved = Path(folder).resolve()
    paths = []
    for p in data.get("paths", []):
        # Only media files directly inside the mirrored folder are deletable
        if not isinstance(p, str) or Path(p).suffix.lower() not in MEDIA_EXTS:
            continue
        try:
            if Path(p).resolve().parent == folder_resolved:
                paths.append(p)
        except OSError:
            continue
    return jsonify(_vault.confirm_mirror_delete(paths))


@app.route("/api/vault/stream")
def api_vault_stream() -> Response:
    """Range-aware media streaming for the in-app preview player."""
    path = request.args.get("path", "")
    p = Path(path)
    if not path or not p.is_file() or p.suffix.lower() not in MEDIA_EXTS:
        return jsonify({"error": "Not a streamable media file"}), 404
    mime = MEDIA_MIME.get(p.suffix.lower(), "application/octet-stream")
    # conditional=True makes Flask honor Range requests (seek support)
    return send_file(str(p), mimetype=mime, conditional=True)


@app.route("/api/vault/budget", methods=["POST"])
def api_vault_budget() -> Response:
    """Set or clear a per-folder storage budget (bytes; null clears)."""
    data = request.get_json(force=True) or {}
    path = (data.get("path") or "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    raw = data.get("budget_bytes")
    budget: int | None
    if raw in (None, "", 0):
        budget = None
    else:
        try:
            budget = max(0, int(raw)) or None
        except (TypeError, ValueError):
            return jsonify({"error": "budget_bytes must be a number or null"}), 400

    def _set_budget(cfg: dict) -> None:
        budgets = cfg.setdefault("vault_budgets", {})
        if budget is None:
            budgets.pop(path, None)
        else:
            budgets[path] = budget
    cfg = update_config(_set_budget)
    return jsonify({"ok": True, "budgets": cfg.get("vault_budgets", {})})


@app.route("/api/vault/cleanup-candidates")
def api_vault_cleanup_candidates() -> Response:
    """Files to free a folder's budget overage (oldest first); read-only."""
    path = request.args.get("path", "")
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Invalid path"}), 400
    budget = load_config().get("vault_budgets", {}).get(path)
    if not budget:
        return jsonify({"error": "No budget set for this folder"}), 400
    return jsonify(_vault.get_cleanup_candidates(path, int(budget)))


@app.route("/api/vault/duplicates")
def api_vault_duplicates() -> Response:
    """Cross-folder duplicate scan by yt-dlp [videoID] filename pattern."""
    cfg = load_config()
    folders = {f["path"] for f in _vault.build_folder_list(download_root(cfg), cfg)}
    groups = _vault.find_duplicates(sorted(folders))
    return jsonify({
        "groups": groups,
        "total_wasted_bytes": sum(g["wasted_bytes"] for g in groups),
    })


@app.route("/api/vault/file-thumbs", methods=["POST"])
def api_vault_file_thumbs() -> Response:
    paths = (request.get_json(force=True) or {}).get("paths", [])
    return jsonify({"thumbs": _vault.resolve_file_thumbs(paths, analytics.get_conn)})


@app.route("/api/vault/retry-item", methods=["POST"])
def api_vault_retry_item() -> Response:
    """Download one item into a vault folder, in the format the folder syncs with."""
    data = request.get_json(force=True) or {}
    path = (data.get("path") or "").strip()
    url = (data.get("url") or "").strip()
    if not path or not url:
        return jsonify({"error": "path and url required"}), 400
    cfg = load_config()
    lib = _library_entry_for(path, cfg)
    job = _enqueue_job(url, path, _vault.build_sync_opts({}, lib, cfg, path), lib["id"] if lib else None,
                       job_type="feed", label=f"Retry — {url}")
    return jsonify({"ok": True, "job_id": job["id"]})


@app.route("/api/vault/sync-report")
def api_vault_sync_report() -> Response:
    """What the last sync of a folder added, skipped and failed on."""
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path required"}), 400
    return jsonify({"report": analytics.get_sync_report(path)})


@app.route("/api/vault/folder-stats")
def api_vault_folder_stats() -> Response:
    path = request.args.get("path", "")
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Invalid path"}), 400
    try:
        linked_playlists = load_config().get("vault_playlists", {}).get(path, [])
        return jsonify(_vault.get_folder_stats(path, linked_playlists))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Backup / restore ──────────────────────────────────────────────────────────

@app.route("/api/backup")
def api_backup() -> Response:
    data = _backup.create_backup()
    return Response(
        data,
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={_backup.backup_filename()}"},
    )


@app.route("/api/backup/restore", methods=["POST"])
def api_backup_restore() -> Response:
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"error": "No file uploaded (multipart field 'file')"}), 400
    result = _backup.restore_backup(upload.read())
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


# ── Wrapped ───────────────────────────────────────────────────────────────────

@app.route("/api/analytics/wrapped")
def api_analytics_wrapped() -> Response:
    year = _int_arg("year", time.localtime().tm_year, 2000, 2100)
    return jsonify(analytics.get_wrapped(year))


# ── Library ───────────────────────────────────────────────────────────────────

@app.route("/api/library", methods=["GET"])
def api_library_get() -> Response:
    return jsonify(analytics.get_library_entries())


@app.route("/api/library", methods=["POST"])
def api_library_post() -> Response:
    data = request.get_json(force=True) or {}
    if not (data.get("folder") or "").strip():
        # No folder picked: put it in its own subfolder of the download
        # folder. Left empty, the entry never showed up in the Vault and its
        # syncs landed loose in the download folder root.
        data["folder"] = download_root(load_config())
        data["use_subfolder"] = True
    entry_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = _library.build_entry(data, entry_id, now)
    analytics.upsert_library_entry(entry)
    # Link all extra URLs to vault_playlists for the folder
    extra_urls = data.get("extra_urls", [])
    all_urls = ([data.get("url", "")] if data.get("url") else []) + [u for u in extra_urls if u]
    folder_path = _library.folder_path_for_entry(entry)
    if all_urls and folder_path:
        def _link_urls(cfg: dict) -> None:
            vp = cfg.setdefault("vault_playlists", {})
            existing_urls = vp.setdefault(folder_path, [])
            for u in all_urls:
                if u and u not in existing_urls:
                    existing_urls.append(u)
        update_config(_link_urls)
    # folder_path: where downloads for this entry go (the client downloads
    # into exactly the folder the entry and its playlist links point at)
    return jsonify({**entry, "folder_path": folder_path}), 201


@app.route("/api/library/<entry_id>", methods=["PUT"])
def api_library_put(entry_id: str) -> Response:
    data = request.get_json(force=True) or {}
    existing = analytics.get_library_entry(entry_id)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    existing.update(data)
    existing["id"] = entry_id
    analytics.upsert_library_entry(existing)
    return jsonify(existing)


@app.route("/api/library/<entry_id>", methods=["DELETE"])
def api_library_delete(entry_id: str) -> Response:
    analytics.delete_library_entry(entry_id)
    return jsonify({"ok": True})


@app.route("/api/library/<entry_id>/sync", methods=["POST"])
def api_library_sync(entry_id: str) -> Response:
    data = request.get_json(force=True) or {}
    sync_mode = data.get("mode", "add")
    entry = analytics.get_library_entry(entry_id)
    if not entry:
        return jsonify({"error": "Not found"}), 404
    cfg = load_config()
    opts, output_dir = _library.build_sync_opts(entry, cfg, sync_mode)
    # last_synced is stamped by the worker when the sync completes
    job = _enqueue_job(entry["url"], output_dir, opts, entry_id,
                       job_type="sync", label=f"Library sync — {entry.get('name','')}")
    return jsonify({"status": "started", "library_id": entry_id, "job_id": job["id"]})


# ── App init ──────────────────────────────────────────────────────────────────

def init_app() -> Flask:
    analytics.init_db()
    return app
