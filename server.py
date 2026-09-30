from __future__ import annotations

import json
import os
import platform
import queue
import subprocess
import sys
import threading
import time

try:
    import tkinter
    import tkinter.filedialog
    _tkinter_available = True
except ModuleNotFoundError:
    tkinter = None  # type: ignore[assignment]
    _tkinter_available = False
import uuid
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from flask import Flask, Response, jsonify, request, send_from_directory

import analytics
import downloader
import library as _library
import vault as _vault
from config import load_config, update_config
from constants import MEDIA_EXTS, THUMB_CACHE_SECS

STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=None)

_tk_lock = threading.Lock()

# ── SSE broadcast ──────────────────────────────────────────────────────────────
# One queue per connected client. A single shared queue meant each event went
# to exactly one consumer, so a second EventSource (Signal page live stream,
# or a stale generator after reconnect) silently ate half the UI's events.
_sse_subscribers: list[queue.Queue] = []
_sse_lock = threading.Lock()


def _sse_subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=500)
    with _sse_lock:
        _sse_subscribers.append(q)
    return q


def _sse_unsubscribe(q: queue.Queue) -> None:
    with _sse_lock:
        if q in _sse_subscribers:
            _sse_subscribers.remove(q)


# ── Download job queue (single-worker — one download at a time) ────────────────
_dl_queue: queue.Queue = queue.Queue()
_dl_jobs: list[dict] = []
_dl_jobs_lock = threading.Lock()

# Pending jobs persisted across restarts (Path so tests can monkeypatch)
QUEUE_STATE_PATH = Path.home() / ".mellow_dlp_queue.json"
_JOB_PERSIST_KEYS = ("id", "type", "label", "url", "multi_urls",
                     "output_dir", "opts", "library_id", "sync_path")
_restorable_jobs: list[dict] = []


def _persist_queue() -> None:
    """Snapshot still-queued jobs to disk so a restart can offer to resume them."""
    try:
        with _dl_jobs_lock:
            pending = [
                {k: j.get(k) for k in _JOB_PERSIST_KEYS}
                for j in _dl_jobs if j["status"] == "queued"
            ]
        if pending:
            QUEUE_STATE_PATH.write_text(json.dumps(pending), encoding="utf-8")
        elif QUEUE_STATE_PATH.exists():
            QUEUE_STATE_PATH.unlink()
    except OSError as exc:
        print(f"[QUEUE] persist failed: {exc}", flush=True)


def _load_restorable_jobs() -> None:
    global _restorable_jobs
    try:
        if QUEUE_STATE_PATH.exists():
            data = json.loads(QUEUE_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                _restorable_jobs = [j for j in data if isinstance(j, dict) and j.get("url")]
    except Exception as exc:
        print(f"[QUEUE] could not read persisted queue: {exc}", flush=True)


_load_restorable_jobs()


def _enqueue_job(url: str, output_dir: str, opts: dict,
                 library_id: str | None = None,
                 job_type: str = "feed",
                 label: str = "",
                 multi_urls: list | None = None,
                 sync_path: str | None = None) -> dict:
    job: dict = {
        "id": str(uuid.uuid4()),
        "type": job_type,
        "label": label or url,
        "url": url,
        "multi_urls": multi_urls,
        "output_dir": output_dir,
        "opts": opts,
        "library_id": library_id,
        "sync_path": sync_path,
        "status": "queued",
        "cancel_event": threading.Event(),
        "counts": {"new": 0, "errors": 0},
    }
    with _dl_jobs_lock:
        _dl_jobs.append(job)
    _dl_queue.put(job)
    _persist_queue()
    return job


def _cancel_job(job_id: str) -> dict | None:
    """Cancel a queued or active job. Returns the job, or None if not found."""
    with _dl_jobs_lock:
        job = next((j for j in _dl_jobs if j["id"] == job_id), None)
        if job is None:
            return None
        job["cancel_event"].set()
        if job["status"] == "queued":
            job["status"] = "cancelled"
    _persist_queue()
    return job


def _run_job(job: dict) -> str:
    """Run all URLs of a job. Returns aggregate status."""
    urls = job.get("multi_urls") or [job["url"]]
    last_idx = len(urls) - 1
    cancel_event = job.setdefault("cancel_event", threading.Event())
    job.setdefault("counts", {"new": 0, "errors": 0})
    # The metadata toggle is read at run time so config changes apply to
    # already-queued jobs too.
    job["opts"]["write_metadata"] = load_config().get("write_metadata", True)
    results: list[str] = []
    for i, url in enumerate(urls):
        if cancel_event.is_set():
            results.append("cancelled")
            break
        is_last = (i == last_idx)

        def _make_cb(final: bool):
            def _cb(event: dict) -> None:
                status = event.get("status")
                if status == "item_done":
                    job["counts"]["new"] += 1
                elif status == "item_failed":
                    job["counts"]["errors"] += 1
                # Suppress intermediate complete events so only the final URL fires once
                if status == "complete" and not final:
                    return
                _push_progress(event)
            return _cb

        results.append(downloader.download_video(
            url, job["output_dir"], job["opts"], _make_cb(is_last),
            job.get("library_id"), cancel_event=cancel_event))

    if any(r == "cancelled" for r in results) or cancel_event.is_set():
        return "cancelled"
    if results and all(r == "error" for r in results):
        return "failed"
    return "complete"


def _on_job_finished(job: dict, status: str) -> None:
    """Post-job bookkeeping: sync timestamps and the sync_log fact table."""
    if job.get("type") != "sync" or status != "complete":
        return
    t_done = time.strftime("%Y-%m-%dT%H:%M:%S")
    sync_path = job.get("sync_path")
    if sync_path:
        # Stamped on completion, not enqueue, so a failed sync isn't "synced"
        update_config(lambda cfg: cfg.setdefault("vault_sync_times", {}).__setitem__(sync_path, t_done))
    counts = job.get("counts", {})
    duration = int(time.monotonic() - job.get("_t0", time.monotonic()))
    analytics.record_sync_log(
        job.get("library_id") or "", counts.get("new", 0), 0,
        counts.get("errors", 0), duration)


def _queue_worker() -> None:
    while True:
        job = _dl_queue.get()
        if job is None:
            break
        if job["cancel_event"].is_set() or job["status"] == "cancelled":
            with _dl_jobs_lock:
                job["status"] = "cancelled"
            _dl_queue.task_done()
            continue
        with _dl_jobs_lock:
            job["status"] = "active"
            job["_t0"] = time.monotonic()
        _persist_queue()
        try:
            status = _run_job(job)
            with _dl_jobs_lock:
                job["status"] = status
            _on_job_finished(job, status)
        except Exception as exc:
            with _dl_jobs_lock:
                job["status"] = "failed"
                job["error"] = str(exc)
        finally:
            _dl_queue.task_done()
            with _dl_jobs_lock:
                done = [j for j in _dl_jobs if j["status"] in ("complete", "failed", "cancelled")]
                if len(done) > 20:
                    for old in done[:-20]:
                        if old in _dl_jobs:
                            _dl_jobs.remove(old)


_worker_thread = threading.Thread(target=_queue_worker, daemon=True)
_worker_thread.start()



def _fire_webhooks(event_type: str, payload: dict) -> None:
    try:
        from urllib.request import Request as _Req
        from urllib.request import urlopen as _urlopen
        cfg = load_config()
        urls = cfg.get("webhooks", {}).get(event_type, [])
        body = json.dumps({"event": event_type,
                           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "data": payload}).encode()
        for wh_url in urls:
            try:
                req = _Req(wh_url, data=body, method="POST",
                           headers={"Content-Type": "application/json"})
                _urlopen(req, timeout=5)
            except Exception as wh_exc:
                print(f"[WEBHOOK] {event_type} → {wh_url} failed: {wh_exc}", flush=True)
    except Exception:
        pass


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


# ── Cross-origin write protection ─────────────────────────────────────────────
# All endpoints parse JSON with force=True, which also accepts text/plain —
# the content type a cross-origin "simple" POST can send without a CORS
# preflight. Requiring a JSON content type (and a local Origin when present)
# stops any website you visit from poking /api/download, /api/config, etc.

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
        if host not in ("localhost", "127.0.0.1", "::1"):
            return jsonify({"error": "Cross-origin requests are not allowed"}), 403
    if request.content_length and not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415
    return None


def _open_in_explorer(path: str) -> None:
    p = Path(path)
    system = platform.system()
    if system == "Windows":
        norm = os.path.normpath(str(p))
        if p.is_file():
            subprocess.Popen(["explorer", f"/select,{norm}"])
        else:
            target = os.path.normpath(str(p if p.is_dir() else p.parent))
            subprocess.Popen(["explorer", target])
    elif system == "Darwin":
        if p.is_file():
            subprocess.Popen(["open", "-R", str(p)])
        else:
            subprocess.Popen(["open", str(p if p.is_dir() else p.parent)])
    else:
        subprocess.Popen(["xdg-open", str(p if p.is_dir() else p.parent)])


def _open_file(path: str) -> None:
    system = platform.system()
    if system == "Windows":
        getattr(os, "startfile")(path)
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _get_clipboard_text() -> str:
    system = platform.system()
    try:
        if system == "Windows" and _tkinter_available:
            # Use tkinter clipboard — no shell window, no PowerShell spawned.
            # Tk isn't thread-safe, so serialize all Tk use behind _tk_lock.
            with _tk_lock:
                root = tkinter.Tk()
                root.withdraw()
                try:
                    text = root.clipboard_get()
                except tkinter.TclError:
                    text = ""
                finally:
                    root.destroy()
            return text.strip()
        if system == "Darwin":
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return result.stdout.strip()
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _tk_dialog(dialog_fn: Any, **kwargs: Any) -> str:
    if not _tkinter_available:
        return ""
    result: list[str] = []

    def _run() -> None:
        with _tk_lock:
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)  # stay above app window
            root.lift()
            root.focus_force()
            try:
                val = dialog_fn(**kwargs)
                result.append(str(val) if val else "")
            finally:
                root.destroy()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)
    return result[0] if result else ""


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
    return jsonify({"text": _get_clipboard_text()})


@app.route("/api/open-folder", methods=["POST"])
def api_open_folder() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "")
    if path:
        threading.Thread(target=_open_in_explorer, args=(path,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/browse-file", methods=["POST"])
def api_browse_file() -> Response:
    if not _tkinter_available:
        return jsonify({"path": "", "error": "File dialogs unavailable (tkinter missing)"})
    data = request.get_json(force=True) or {}
    filt = data.get("filter", "")
    filetypes = [("Text files", f"*{filt}"), ("All files", "*.*")] if filt else [("All files", "*.*")]
    path = _tk_dialog(tkinter.filedialog.askopenfilename, filetypes=filetypes)
    return jsonify({"path": path})


_ARCHIVE_PLATFORM_MAP = {
    # yt-dlp extractor key → reconstructable public URL
    "youtube":     "https://www.youtube.com/watch?v={}",
    "vimeo":       "https://vimeo.com/{}",
    "twitter":     "https://twitter.com/i/status/{}",
    "twitch":      "https://www.twitch.tv/videos/{}",
    "twitchvod":   "https://www.twitch.tv/videos/{}",
    "bilibili":    "https://www.bilibili.com/video/{}",
    "dailymotion": "https://www.dailymotion.com/video/{}",
    "nicovideo":   "https://www.nicovideo.jp/watch/{}",
    # soundcloud / tiktok / instagram / bandcamp: numeric IDs stored by yt-dlp
    # cannot be turned back into a working public URL — entries are skipped.
}


def _parse_url_file(content: str) -> tuple[list[str], str]:
    """Parse a text file of URLs or a yt-dlp archive file.
    Returns (urls, detected_format).
    """
    urls: list[str] = []
    fmt = "url_list"
    for line in content.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("http"):
            urls.append(line)
        else:
            parts = line.split()
            if len(parts) == 2:
                platform_name, video_id = parts
                tmpl = _ARCHIVE_PLATFORM_MAP.get(platform_name.lower())
                if tmpl:
                    urls.append(tmpl.format(video_id))
                    fmt = "archive"
    return urls, fmt


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
        urls, fmt = _parse_url_file(content)
        return jsonify({"urls": urls, "format": fmt, "count": len(urls)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/browse-folder", methods=["POST"])
def api_browse_folder() -> Response:
    if not _tkinter_available:
        return jsonify({"path": "", "error": "File dialogs unavailable (tkinter missing)"})
    data = request.get_json(force=True) or {}
    initial = data.get("initial", str(Path.home()))
    path = _tk_dialog(tkinter.filedialog.askdirectory, initialdir=initial, mustexist=False)
    return jsonify({"path": path})


@app.route("/api/system")
def api_system() -> Response:
    ytdlp_version = "unknown"
    try:
        import yt_dlp
        ytdlp_version = yt_dlp.version.__version__
    except Exception:
        pass
    ffmpeg_ok = False
    try:
        _kw: dict = {"capture_output": True, "timeout": 5}
        if platform.system() == "Windows":
            _kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        result = subprocess.run(["ffmpeg", "-version"], **_kw)
        ffmpeg_ok = result.returncode == 0
    except Exception:
        pass
    return jsonify({
        "ffmpeg": ffmpeg_ok,
        "ytdlp_version": ytdlp_version,
        "python_version": sys.version.split()[0],
        "db_size_bytes": analytics.get_db_size(),
    })


def _parse_ytdlp_ver(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


@app.route("/api/check-ytdlp-update")
def api_check_ytdlp_update() -> Response:
    def _check() -> dict:
        try:
            import importlib

            import yt_dlp as _ydlp
            importlib.reload(_ydlp.version)
            installed = _ydlp.version.__version__
        except Exception:
            installed = "unknown"
        print(f"[YTDLP CHECK] version returned: {installed}", flush=True)
        try:
            with urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=30) as resp:
                payload = json.loads(resp.read().decode())
            latest = payload["info"]["version"]
        except (URLError, KeyError, Exception) as exc:
            return {"error": str(exc), "installed": installed, "latest": None, "current": installed}
        update_available = _parse_ytdlp_ver(latest) > _parse_ytdlp_ver(installed)
        print(f"[YTDLP CHECK] installed={installed} latest={latest} update={update_available}", flush=True)
        return {
            "installed": installed, "latest": latest, "current": installed,
            "update_available": update_available,
        }
    return jsonify(_check())


@app.route("/api/update-ytdlp", methods=["POST"])
def api_update_ytdlp() -> Response:
    def _update() -> None:
        import shutil as _sh
        try:
            import yt_dlp as _ytdlp_mod_check
            ytdlp_file = Path(_ytdlp_mod_check.__file__).parent
            old_ver = _ytdlp_mod_check.version.__version__
            print(f"[YTDLP UPDATE] module at {ytdlp_file}, current version: {old_ver}", flush=True)
        except Exception:
            pass

        _kw: dict = {"capture_output": True}
        if platform.system() == "Windows":
            _kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        exe = sys.executable
        frozen = getattr(sys, "frozen", False)
        guard = frozen or "mellowdlp" in exe.lower()
        print(f"[YTDLP UPDATE] exe={exe!r} frozen={frozen} guard={guard}", flush=True)

        try:
            if guard:
                ytdlp_bin = _sh.which("yt-dlp") or _sh.which("yt-dlp.exe")
                if ytdlp_bin and "mellowdlp" not in ytdlp_bin.lower():
                    print(f"[YTDLP UPDATE] running standalone binary: {ytdlp_bin} -U", flush=True)
                    subprocess.run([ytdlp_bin, "-U"], check=True, **_kw)
                else:
                    python = _sh.which("python") or _sh.which("python3")
                    if not python or "mellowdlp" in python.lower():
                        raise RuntimeError("No suitable Python found for yt-dlp update")
                    print(f"[YTDLP UPDATE] pip via {python}", flush=True)
                    subprocess.run([python, "-m", "pip", "install", "--upgrade", "yt-dlp"], check=True, **_kw)
            else:
                print(f"[YTDLP UPDATE] pip via {exe}", flush=True)
                subprocess.run([exe, "-m", "pip", "install", "--upgrade", "yt-dlp"], check=True, **_kw)

            # Re-check version after update (force reload of version submodule)
            try:
                import importlib

                import yt_dlp as _ytdlp_mod
                importlib.reload(_ytdlp_mod.version)
                importlib.reload(_ytdlp_mod)
                new_ver = _ytdlp_mod.version.__version__
                print(f"[YTDLP UPDATE] new version after update: {new_ver}", flush=True)
                _push_progress({"status": "ytdlp_updated", "ok": True, "new_version": new_ver})
            except Exception as reload_exc:
                print(f"[YTDLP UPDATE] reload error: {reload_exc}", flush=True)
                _push_progress({"status": "ytdlp_updated", "ok": True})
        except Exception as exc:
            print(f"[YTDLP UPDATE] failed: {exc}", flush=True)
            _push_progress({"status": "ytdlp_updated", "ok": False, "error": str(exc)})

    threading.Thread(target=_update, daemon=True).start()
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


# ── Download ──────────────────────────────────────────────────────────────────

@app.route("/api/info", methods=["POST"])
def api_info() -> Response:
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL"}), 400
    cfg = load_config()
    cookie_opts = {
        "cookies_browser": cfg.get("cookies_browser", "none"),
        "cookies_file": cfg.get("cookies_file", ""),
        "cookies_browser_profile": cfg.get("cookies_browser_profile", ""),
    }
    try:
        info = downloader.get_video_info(url, cookie_opts=cookie_opts)
        return jsonify(info)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/download", methods=["POST"])
def api_download() -> Response:
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    cfg = load_config()
    output_dir = data.get("output_dir") or cfg.get("output_dir") or str(Path.home() / "Downloads" / "MellowDLP")
    print(f"[MellowDLP] download -> output_dir={output_dir!r}", flush=True)
    opts = {
        "mode": data.get("mode", "video"),
        "quality": data.get("quality", "best"),
        "container": data.get("container", "mp4"),
        "audio_format": data.get("audio_format", "mp3"),
        "embed_thumbnail": data.get("embed_thumbnail", True),
        "embed_chapters": data.get("embed_chapters", True),
        "embed_metadata": data.get("embed_metadata", True),
        "embed_subs": data.get("embed_subs", False),
        "sub_langs": data.get("sub_langs", "en"),
        "auto_subs": data.get("auto_subs", False),
        "sponsorblock": data.get("sponsorblock", False),
        "split_chapters": data.get("split_chapters", False),
        "custom_format": data.get("custom_format", ""),
        "start_time": data.get("start_time", ""),
        "end_time": data.get("end_time", ""),
        "playlist_start": data.get("playlist_start"),
        "playlist_end": data.get("playlist_end"),
        "playlist_items": data.get("playlist_items", ""),
        "date_before": data.get("date_before", ""),
        "date_after": data.get("date_after", ""),
        "filename_template": data.get("filename_template", "") or cfg.get("filename_template", ""),
        "cookies_browser": cfg.get("cookies_browser", "none"),
        "cookies_file": cfg.get("cookies_file", ""),
        "cookies_browser_profile": cfg.get("cookies_browser_profile", ""),
        "rate_limit": cfg.get("rate_limit", ""),
        "proxy": cfg.get("proxy", ""),
        "external_downloader": cfg.get("external_downloader", ""),
        "concurrent_fragments": cfg.get("concurrent_fragments", 4),
        "sleep_interval": cfg.get("sleep_interval", 0),
        "retries": cfg.get("retries", 3),
    }
    multi_urls = data.get("multi_urls")
    if multi_urls and isinstance(multi_urls, list) and len(multi_urls) > 1:
        job = _enqueue_job(multi_urls[0], output_dir, opts, job_type="feed",
                           label=multi_urls[0], multi_urls=multi_urls)
    else:
        job = _enqueue_job(url, output_dir, opts, job_type="feed", label=url)
    return jsonify({"status": "started", "job_id": job["id"]})


@app.route("/api/cancel", methods=["POST"])
def api_cancel() -> Response:
    # Cancel the active job (its event is registered as current in downloader)
    with _dl_jobs_lock:
        active = next((j for j in _dl_jobs if j["status"] == "active"), None)
    if active:
        active["cancel_event"].set()
    downloader.cancel_download()
    return jsonify({"status": "cancelled"})


@app.route("/api/queue/<job_id>", methods=["DELETE"])
@app.route("/api/queue/<job_id>/cancel", methods=["POST"])
def api_queue_cancel_job(job_id: str) -> Response:
    job = _cancel_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] == "cancelled":
        return jsonify({"ok": True, "status": "cancelled"})
    # Active job: the downloader notices the event via its progress hook
    downloader.cancel_download()
    return jsonify({"ok": True, "status": "cancelling"})


@app.route("/api/queue/restorable", methods=["GET"])
def api_queue_restorable() -> Response:
    return jsonify({"jobs": [
        {"id": j.get("id"), "label": j.get("label"), "type": j.get("type"),
         "url": j.get("url")}
        for j in _restorable_jobs
    ]})


@app.route("/api/queue/restore", methods=["POST"])
def api_queue_restore() -> Response:
    """Re-enqueue jobs that were still pending when the app last exited."""
    global _restorable_jobs
    restored = []
    for j in _restorable_jobs:
        job = _enqueue_job(
            j["url"], j.get("output_dir") or load_config().get("output_dir", ""),
            j.get("opts") or {}, j.get("library_id"),
            job_type=j.get("type", "feed"), label=j.get("label", ""),
            multi_urls=j.get("multi_urls"), sync_path=j.get("sync_path"))
        restored.append(job["id"])
    _restorable_jobs = []
    return jsonify({"ok": True, "restored": len(restored), "job_ids": restored})


@app.route("/api/queue/restorable", methods=["DELETE"])
def api_queue_restorable_discard() -> Response:
    global _restorable_jobs
    _restorable_jobs = []
    try:
        if QUEUE_STATE_PATH.exists():
            QUEUE_STATE_PATH.unlink()
    except OSError:
        pass
    return jsonify({"ok": True})


@app.route("/api/download/pause", methods=["POST"])
def api_pause() -> Response:
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
                    event = q.get(timeout=25)
                    data = json.dumps(event)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield 'data: {"status":"ping"}\n\n'
        finally:
            # Client went away (GeneratorExit) — stop receiving events
            _sse_unsubscribe(q)
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


_JOB_PUBLIC_SKIP = ("opts", "multi_urls", "cancel_event", "_t0")


@app.route("/api/queue/status")
def api_queue_status() -> Response:
    with _dl_jobs_lock:
        jobs = [
            {k: v for k, v in j.items() if k not in _JOB_PUBLIC_SKIP}
            for j in _dl_jobs
        ]
    return jsonify({
        "jobs": jobs,
        "queued": sum(1 for j in jobs if j["status"] == "queued"),
        "active": sum(1 for j in jobs if j["status"] == "active"),
    })


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
    limit = _int_arg("limit", 50, 1, 500)
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
    base_path = request.args.get("path") or cfg.get("output_dir", str(Path.home() / "Downloads" / "MellowDLP"))
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
    cfg = load_config()
    cookie_opts = {
        "cookies_browser": cfg.get("cookies_browser", "none"),
        "cookies_file": cfg.get("cookies_file", ""),
        "cookies_browser_profile": cfg.get("cookies_browser_profile", ""),
    }
    try:
        items = downloader.get_playlist_items(url, cookie_opts=cookie_opts)
        return jsonify({"items": items})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/vault/open-file", methods=["POST"])
def api_vault_open_file() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "")
    if path and Path(path).exists():
        threading.Thread(target=_open_file, args=(path,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/vault/play-files", methods=["POST"])
def api_vault_play_files() -> Response:
    data = request.get_json(force=True) or {}
    paths = data.get("paths", [])
    if not paths:
        return jsonify({"error": "No files provided"}), 400
    result = _vault.launch_playlist(paths, _open_file)
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
    return jsonify({"playlists": cfg.get("vault_playlists", {}).get(path, [])})


@app.route("/api/vault/playlists", methods=["POST"])
def api_vault_playlists_post() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    url_val = data.get("url", "").strip()
    if not path or not url_val:
        return jsonify({"error": "path and url required"}), 400
    def _add_pl(cfg: dict) -> None:
        vp = cfg.setdefault("vault_playlists", {})
        urls = vp.setdefault(path, [])
        if url_val not in urls:
            urls.append(url_val)
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
        p.unlink()
        for sidecar_ext in (".jpg", ".jpeg", ".png", ".webp"):
            sidecar = p.with_suffix(sidecar_ext)
            if sidecar.exists():
                try:
                    sidecar.unlink()
                except OSError:
                    pass
        analytics.delete_history_by_path(str(p))
        return jsonify({"ok": True})
    except OSError as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/vault/sync", methods=["POST"])
def api_vault_sync() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    cfg = load_config()
    vp = cfg.get("vault_playlists", {}).get(path, [])
    if not vp:
        return jsonify({"error": "No playlist linked to this folder"}), 400
    library_entries = analytics.get_library_entries()
    lib = next((e for e in library_entries if e.get("folder") == path or
                str(Path(e.get("folder", "")) / (e.get("folder_name") or "")) == path), None)
    output_dir = path
    opts = _vault.build_sync_opts(data, lib, cfg)
    library_id = lib["id"] if lib else None

    # Enqueue all linked playlists as a single sync job (processed sequentially)
    requested_urls = data.get("playlist_urls")
    playlist_urls = [u for u in list(vp) if u in requested_urls] if requested_urls else list(vp)
    if not playlist_urls:
        return jsonify({"error": "No matching playlists to sync"}), 400
    label = f"Sync — {Path(path).name} ({len(playlist_urls)} playlist(s))"
    # Sync time is stamped by the worker on successful completion, not here
    _enqueue_job(playlist_urls[0] if len(playlist_urls) == 1 else path,
                 output_dir, opts, library_id, job_type="sync", label=label,
                 multi_urls=playlist_urls, sync_path=path)
    return jsonify({"ok": True, "queued": True, "playlists_synced": len(playlist_urls)})


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
    queued = []
    library_entries = analytics.get_library_entries()
    for path in folders_to_sync:
        playlist_urls = list(vp[path])
        lib = next((e for e in library_entries if e.get("folder") == path or
                    str(Path(e.get("folder", "")) / (e.get("folder_name") or "")) == path), None)
        opts = _vault.build_sync_opts({}, lib, cfg)
        library_id = lib["id"] if lib else None
        label = f"Sync — {Path(path).name} ({len(playlist_urls)} playlist(s))"
        _enqueue_job(playlist_urls[0] if len(playlist_urls) == 1 else path,
                     path, opts, library_id, job_type="sync", label=label,
                     multi_urls=playlist_urls, sync_path=path)
        queued.append(path)
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
    return jsonify(_vault.get_mirror_preview(path, vp))


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


@app.route("/api/vault/duplicates")
def api_vault_duplicates() -> Response:
    """Cross-folder duplicate scan by yt-dlp [videoID] filename pattern."""
    cfg = load_config()
    base = cfg.get("output_dir", str(Path.home() / "Downloads" / "MellowDLP"))
    folders = {f["path"] for f in _vault.build_folder_list(base, cfg)}
    groups = _vault.find_duplicates(sorted(folders))
    return jsonify({
        "groups": groups,
        "total_wasted_bytes": sum(g["wasted_bytes"] for g in groups),
    })


@app.route("/api/vault/file-thumbs", methods=["POST"])
def api_vault_file_thumbs() -> Response:
    paths = (request.get_json(force=True) or {}).get("paths", [])
    return jsonify({"thumbs": _vault.resolve_file_thumbs(paths, analytics.get_conn)})


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


# ── Library ───────────────────────────────────────────────────────────────────

@app.route("/api/library", methods=["GET"])
def api_library_get() -> Response:
    return jsonify(analytics.get_library_entries())


@app.route("/api/library", methods=["POST"])
def api_library_post() -> Response:
    data = request.get_json(force=True) or {}
    entry_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = _library.build_entry(data, entry_id, now)
    analytics.upsert_library_entry(entry)
    # Link all extra URLs to vault_playlists for the folder
    extra_urls = data.get("extra_urls", [])
    all_urls = ([data.get("url", "")] if data.get("url") else []) + [u for u in extra_urls if u]
    if all_urls and (entry["folder"] or entry["folder_name"]):
        folder_path = str(Path(entry["folder"]) / entry["folder_name"]) if entry.get("use_subfolder") and entry["folder"] and entry["folder_name"] else entry["folder"]
        if folder_path:
            def _link_urls(cfg: dict) -> None:
                vp = cfg.setdefault("vault_playlists", {})
                existing_urls = vp.setdefault(folder_path, [])
                for u in all_urls:
                    if u and u not in existing_urls:
                        existing_urls.append(u)
            update_config(_link_urls)
    return jsonify(entry), 201


@app.route("/api/library/<entry_id>", methods=["PUT"])
def api_library_put(entry_id: str) -> Response:
    data = request.get_json(force=True) or {}
    entries = analytics.get_library_entries()
    existing = next((e for e in entries if e["id"] == entry_id), None)
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
    entries = analytics.get_library_entries()
    entry = next((e for e in entries if e["id"] == entry_id), None)
    if not entry:
        return jsonify({"error": "Not found"}), 404
    cfg = load_config()
    opts, output_dir = _library.build_sync_opts(entry, cfg, sync_mode)

    analytics.update_library_last_synced(entry_id)
    job = _enqueue_job(entry["url"], output_dir, opts, entry_id,
                       job_type="sync", label=f"Library sync — {entry.get('name','')}")
    return jsonify({"status": "started", "library_id": entry_id, "job_id": job["id"]})


# ── App init ──────────────────────────────────────────────────────────────────

def init_app() -> Flask:
    analytics.init_db()
    return app
