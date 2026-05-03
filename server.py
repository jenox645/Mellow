from __future__ import annotations

import json
import mimetypes
import os
import platform
import queue
import subprocess
import sys
import threading
import time
import tkinter
import tkinter.filedialog
import uuid
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from flask import Flask, Response, jsonify, request, send_from_directory

import analytics
import downloader

CONFIG_PATH = Path.home() / ".mellow_dlp.json"
STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=None)

_progress_queue: queue.Queue = queue.Queue()
_active_thread: threading.Thread | None = None
_tk_lock = threading.Lock()


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "output_dir": str(Path.home() / "Downloads" / "MellowDLP"),
        "cookies_browser": "none",
        "cookies_file": "",
        "rate_limit": "",
        "proxy": "",
        "external_downloader": "",
        "concurrent_fragments": 4,
        "sleep_interval": 1,
        "retries": 3,
        "write_metadata": True,
        "extract_chapters": True,
        "filename_template": "",
    }


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _push_progress(event: dict) -> None:
    _progress_queue.put(event)


def _open_in_explorer(path: str) -> None:
    p = Path(path)
    target = str(p if p.is_dir() else p.parent)
    system = platform.system()
    if system == "Windows":
        subprocess.Popen(["explorer", target])
    elif system == "Darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


def _open_file(path: str) -> None:
    system = platform.system()
    if system == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _get_clipboard_text() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            # Use tkinter clipboard — no shell window, no PowerShell spawned
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
    data = request.get_json(force=True) or {}
    filt = data.get("filter", "")
    filetypes = [("Text files", f"*{filt}"), ("All files", "*.*")] if filt else [("All files", "*.*")]
    path = _tk_dialog(tkinter.filedialog.askopenfilename, filetypes=filetypes)
    return jsonify({"path": path})


@app.route("/api/read-url-file", methods=["POST"])
def api_read_url_file() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    if not path or not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 400
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            urls = [line.strip() for line in fh if line.strip() and not line.strip().startswith("#")]
        return jsonify({"urls": urls})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/browse-folder", methods=["POST"])
def api_browse_folder() -> Response:
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
            _kw["creationflags"] = subprocess.CREATE_NO_WINDOW
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
        return {
            "installed": installed, "latest": latest, "current": installed,
            "update_available": latest != installed,
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
            _kw["creationflags"] = subprocess.CREATE_NO_WINDOW

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
    return jsonify(_load_config())


@app.route("/api/config", methods=["POST"])
def api_config_post() -> Response:
    data = request.get_json(force=True) or {}
    cfg = _load_config()
    cfg.update(data)
    _save_config(cfg)
    return jsonify({"ok": True})


# ── Download ──────────────────────────────────────────────────────────────────

@app.route("/api/info", methods=["POST"])
def api_info() -> Response:
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        info = downloader.get_video_info(url)
        return jsonify(info)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/download", methods=["POST"])
def api_download() -> Response:
    global _active_thread
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    cfg = _load_config()
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
        "rate_limit": cfg.get("rate_limit", ""),
        "proxy": cfg.get("proxy", ""),
        "external_downloader": cfg.get("external_downloader", ""),
        "concurrent_fragments": cfg.get("concurrent_fragments", 4),
        "sleep_interval": cfg.get("sleep_interval", 0),
    }
    _active_thread = downloader.download_in_thread(url, output_dir, opts, _push_progress)
    return jsonify({"status": "started"})


@app.route("/api/cancel", methods=["POST"])
def api_cancel() -> Response:
    downloader.cancel_download()
    return jsonify({"status": "cancelled"})


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
        while True:
            try:
                event = _progress_queue.get(timeout=25)
                data = json.dumps(event)
                yield f"data: {data}\n\n"
            except queue.Empty:
                yield 'data: {"status":"ping"}\n\n'
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── History ───────────────────────────────────────────────────────────────────

@app.route("/api/history")
def api_history() -> Response:
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
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
        cfg = _load_config()
        cfg["stat_overrides"] = {}
        _save_config(cfg)
    return jsonify({"deleted": count})


# ── Stats / Analytics ─────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats() -> Response:
    time_range = request.args.get("range", "30d")
    result = analytics.get_stats(time_range)
    # Fix library count: combine library entries + vault_playlists with URLs
    cfg = _load_config()
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
    cfg = _load_config()
    return jsonify(cfg.get("stat_overrides", {}))


@app.route("/api/analytics/overrides", methods=["POST"])
def api_analytics_overrides_post() -> Response:
    data = request.get_json(force=True) or {}
    cfg = _load_config()
    overrides = cfg.get("stat_overrides", {})
    overrides.update(data)
    cfg["stat_overrides"] = overrides
    _save_config(cfg)
    return jsonify({"ok": True, "overrides": overrides})


@app.route("/api/analytics/vacuum", methods=["POST"])
def api_analytics_vacuum() -> Response:
    try:
        analytics.vacuum()
        return jsonify({"ok": True, "db_size_bytes": analytics.get_db_size()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


_FOLDER_MEDIA_EXTS = {'.mp3', '.mp4', '.mkv', '.webm', '.flac', '.m4a',
                      '.wav', '.opus', '.aac', '.ogg', '.avi', '.mov'}


def _get_folder_media_stats(path: str) -> dict:
    p = Path(path)
    if not p.is_dir():
        return {"item_count": 0, "size_bytes": 0}
    total, count = 0, 0
    try:
        for entry in p.rglob("*"):
            if entry.is_file() and not entry.name.startswith(".") and entry.suffix.lower() in _FOLDER_MEDIA_EXTS:
                total += entry.stat().st_size
                count += 1
    except PermissionError:
        pass
    return {"item_count": count, "size_bytes": total}


# ── Vault ─────────────────────────────────────────────────────────────────────

@app.route("/api/vault")
def api_vault() -> Response:
    cfg = _load_config()
    base_path = request.args.get("path") or cfg.get("output_dir", str(Path.home() / "Downloads" / "MellowDLP"))
    all_folders = analytics.get_vault_folders(base_path)
    all_paths: set[str] = {f["path"] for f in all_folders}

    # Include watched folders
    for wp in cfg.get("watched_folders", []):
        p = Path(wp)
        norm = str(p)
        if norm not in all_paths and p.exists() and p.is_dir():
            try:
                ms = _get_folder_media_stats(norm)
                st = p.stat()
            except Exception:
                ms, st = {"item_count": 0, "size_bytes": 0}, None
            all_folders.append({
                "path": norm, "name": p.name,
                "item_count": ms["item_count"], "size_bytes": ms["size_bytes"],
                "watched": True,
                "created_at": st.st_ctime if st else None,
                "modified_at": st.st_mtime if st else None,
            })
            all_paths.add(norm)

    # Tag existing folders with library info and add missing library folders
    for entry in analytics.get_library_entries():
        folder = entry.get("folder") or ""
        folder_name = entry.get("folder_name") or ""
        use_sub = entry.get("use_subfolder", True)
        if use_sub and folder and folder_name:
            actual_path = str(Path(folder) / folder_name)
        elif folder:
            actual_path = folder
        else:
            continue
        norm = str(Path(actual_path))
        found = False
        for f in all_folders:
            if f["path"] == norm:
                f.setdefault("library_id", entry["id"])
                f.setdefault("library_name", entry["name"])
                found = True
                break
        if not found and norm not in all_paths:
            p = Path(actual_path)
            if p.exists() and p.is_dir():
                try:
                    ms = _get_folder_media_stats(actual_path)
                    st = p.stat()
                except Exception:
                    ms, st = {"item_count": 0, "size_bytes": 0}, None
            else:
                ms, st = {"item_count": 0, "size_bytes": 0}, None
            all_folders.append({
                "path": actual_path,
                "name": folder_name or Path(actual_path).name,
                "item_count": ms["item_count"], "size_bytes": ms["size_bytes"],
                "library_id": entry["id"], "library_name": entry["name"],
                "created_at": st.st_ctime if st else None,
                "modified_at": st.st_mtime if st else None,
            })
            all_paths.add(norm)

    # Apply custom names and filter hidden
    vault_names = cfg.get("vault_names", {})
    vault_hidden = set(cfg.get("vault_hidden", []))
    vault_sync_times = cfg.get("vault_sync_times", {})
    for f in all_folders:
        if f["path"] in vault_names:
            f["name"] = vault_names[f["path"]]
        if f["path"] in vault_sync_times:
            f["last_synced"] = vault_sync_times[f["path"]]
    all_folders = [f for f in all_folders if f["path"] not in vault_hidden]

    return jsonify({"folders": all_folders, "base_path": base_path})


@app.route("/api/vault/watch", methods=["GET"])
def api_vault_watch_get() -> Response:
    cfg = _load_config()
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
    cfg = _load_config()
    watched = cfg.get("watched_folders", [])
    if folder not in watched:
        watched.append(folder)
    cfg["watched_folders"] = watched
    _save_config(cfg)
    return jsonify({"ok": True, "watched_folders": watched})


@app.route("/api/vault/watch", methods=["DELETE"])
def api_vault_watch_delete() -> Response:
    data = request.get_json(force=True) or {}
    folder = data.get("path", "").strip()
    cfg = _load_config()
    watched = cfg.get("watched_folders", [])
    watched = [w for w in watched if w != folder]
    cfg["watched_folders"] = watched
    _save_config(cfg)
    return jsonify({"ok": True, "watched_folders": watched})


@app.route("/api/vault/folder")
def api_vault_folder() -> Response:
    path = request.args.get("path", "")
    if not path or not Path(path).exists():
        return jsonify({"files": [], "path": path})
    root = Path(path)
    files = []
    media_exts = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".mp3", ".flac", ".m4a", ".aac", ".opus", ".wav", ".ogg"}
    try:
        for f in sorted(root.iterdir()):
            if f.is_file() and f.suffix.lower() in media_exts and not f.name.startswith("."):
                try:
                    stat = f.stat()
                    files.append({
                        "name": f.name,
                        "path": str(f),
                        "size_bytes": stat.st_size,
                        "modified": stat.st_mtime,
                        "created": stat.st_ctime,
                        "ext": f.suffix.lower().lstrip("."),
                    })
                except OSError:
                    pass
    except PermissionError:
        pass
    return jsonify({"files": files, "path": path, "folder_name": root.name})


@app.route("/api/vault/thumb")
def api_vault_thumb() -> Response:
    path = request.args.get("path", "")
    if not path:
        return Response("", 404)
    p = Path(path)
    if not p.exists():
        return Response("", 404)
    base = p.with_suffix("")
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        thumb = base.with_suffix(ext)
        if thumb.exists():
            mime = "image/jpeg" if ext in (".jpg", ".jpeg") else ("image/png" if ext == ".png" else "image/webp")
            return send_from_directory(str(thumb.parent), thumb.name, mimetype=mime)
    return Response("", 404)


@app.route("/api/playlist-items", methods=["POST"])
def api_playlist_items() -> Response:
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        items = downloader.get_playlist_items(url)
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


@app.route("/api/vault/folder-previews")
def api_vault_folder_previews() -> Response:
    path = request.args.get("path", "")
    if not path or not Path(path).exists():
        return jsonify({"thumbs": []})
    root = Path(path)
    media_exts = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".mp3", ".flac", ".m4a", ".aac", ".opus", ".wav", ".ogg"}
    thumb_urls: list[str] = []
    try:
        for f in sorted(root.iterdir()):
            if f.is_file() and f.suffix.lower() in media_exts and not f.name.startswith("."):
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    if f.with_suffix(ext).exists():
                        thumb_urls.append(f"/api/vault/thumb?path={f}")
                        break
                if len(thumb_urls) >= 4:
                    break
    except PermissionError:
        pass
    return jsonify({"thumbs": thumb_urls})


@app.route("/api/vault/playlists", methods=["GET"])
def api_vault_playlists_get() -> Response:
    path = request.args.get("path", "")
    cfg = _load_config()
    return jsonify({"playlists": cfg.get("vault_playlists", {}).get(path, [])})


@app.route("/api/vault/playlists", methods=["POST"])
def api_vault_playlists_post() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    url_val = data.get("url", "").strip()
    if not path or not url_val:
        return jsonify({"error": "path and url required"}), 400
    cfg = _load_config()
    vp = cfg.get("vault_playlists", {})
    if path not in vp:
        vp[path] = []
    if url_val not in vp[path]:
        vp[path].append(url_val)
    cfg["vault_playlists"] = vp
    _save_config(cfg)
    return jsonify({"ok": True, "playlists": vp[path]})


@app.route("/api/vault/playlists", methods=["DELETE"])
def api_vault_playlists_delete() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    url_val = data.get("url", "").strip()
    cfg = _load_config()
    vp = cfg.get("vault_playlists", {})
    if path in vp:
        vp[path] = [u for u in vp[path] if u != url_val]
    cfg["vault_playlists"] = vp
    _save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/vault/rename", methods=["POST"])
def api_vault_rename() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    name = data.get("name", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    cfg = _load_config()
    vault_names = cfg.get("vault_names", {})
    if name:
        vault_names[path] = name
    else:
        vault_names.pop(path, None)
    cfg["vault_names"] = vault_names
    _save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/vault/remove", methods=["POST"])
def api_vault_remove() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    cfg = _load_config()
    # Remove from watched_folders if present
    watched = cfg.get("watched_folders", [])
    cfg["watched_folders"] = [w for w in watched if w != path]
    # Add to vault_hidden so auto-discovered folders are suppressed
    hidden = cfg.get("vault_hidden", [])
    if path not in hidden:
        hidden.append(path)
    cfg["vault_hidden"] = hidden
    _save_config(cfg)
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
    try:
        p.unlink()
        analytics.delete_history(delete_all=False)
        return jsonify({"ok": True})
    except OSError as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/vault/sync", methods=["POST"])
def api_vault_sync() -> Response:
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    mode = data.get("mode", "add")  # 'add' or 'mirror'
    if not path:
        return jsonify({"error": "path required"}), 400
    cfg = _load_config()
    vp = cfg.get("vault_playlists", {}).get(path, [])
    if not vp:
        return jsonify({"error": "No playlist linked to this folder"}), 400
    library_entries = analytics.get_library_entries()
    lib = next((e for e in library_entries if e.get("folder") == path or
                str(Path(e.get("folder", "")) / (e.get("folder_name") or "")) == path), None)
    output_dir = path
    sync_quality = data.get("quality") or (lib["quality"] if lib else cfg.get("quality_default", "1080p"))
    sync_container = (data.get("container") or "mp4").lower()
    opts = {
        "mode": "library",
        "quality": sync_quality,
        "container": sync_container,
        "embed_thumbnail": lib["embed_thumbnail"] if lib else cfg.get("embed_thumbnail", True),
        "embed_chapters": lib["embed_chapters"] if lib else True,
        "embed_metadata": lib["embed_metadata"] if lib else True,
        "cookies_browser": cfg.get("cookies_browser", "none"),
        "cookies_file": cfg.get("cookies_file", ""),
        "rate_limit": cfg.get("rate_limit", ""),
        "proxy": cfg.get("proxy", ""),
        "concurrent_fragments": cfg.get("concurrent_fragments", 4),
        "sleep_interval": cfg.get("sleep_interval", 0),
    }
    library_id = lib["id"] if lib else None

    # Run all linked playlists sequentially in one thread
    playlist_urls = list(vp)

    def _sync_all() -> None:
        for playlist_url in playlist_urls:
            print(f"[SYNC] syncing playlist: {playlist_url}", flush=True)
            try:
                downloader.download_video(playlist_url, output_dir, opts, _push_progress, library_id)
            except Exception as exc:
                print(f"[SYNC] error on {playlist_url}: {exc}", flush=True)

    threading.Thread(target=_sync_all, daemon=True).start()
    vault_sync_times = cfg.get("vault_sync_times", {})
    vault_sync_times[path] = time.strftime("%Y-%m-%dT%H:%M:%S")
    cfg["vault_sync_times"] = vault_sync_times
    _save_config(cfg)
    return jsonify({"ok": True, "synced_at": vault_sync_times[path], "playlists_synced": len(playlist_urls)})


@app.route("/api/vault/mirror-preview", methods=["POST"])
def api_vault_mirror_preview() -> Response:
    """Return local media files NOT present in any linked playlist (for mirror confirm)."""
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Invalid path"}), 400
    cfg = _load_config()
    vp = cfg.get("vault_playlists", {}).get(path, [])
    if not vp:
        return jsonify({"error": "No playlist linked"}), 400

    # Collect all video IDs from all linked playlists via yt-dlp flat extraction
    playlist_ids: set[str] = set()
    for playlist_url in vp:
        try:
            import yt_dlp as _ydl
            with _ydl.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True}) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
                if info and "entries" in info:
                    for entry in (info["entries"] or []):
                        if entry and entry.get("id"):
                            playlist_ids.add(entry["id"])
        except Exception as exc:
            print(f"[MIRROR-PREVIEW] failed to fetch {playlist_url}: {exc}", flush=True)

    # Scan local media files: only delete files whose ID is confirmed NOT in any playlist
    import re as _re
    p = Path(path)
    media_exts = {'.mp3', '.mp4', '.mkv', '.webm', '.flac', '.m4a', '.wav', '.opus', '.aac', '.ogg', '.avi', '.mov'}
    to_delete = []
    for f in p.iterdir():
        if not f.is_file() or f.suffix.lower() not in media_exts:
            continue
        m = _re.search(r'\[([A-Za-z0-9_-]{11})\]', f.name)
        if not m:
            # No video ID in filename — cannot confirm it belongs to or is missing from playlist, skip
            continue
        vid_id = m.group(1)
        if vid_id in playlist_ids:
            continue  # ID confirmed in playlist — keep
        if playlist_ids:  # only flag if we successfully fetched at least one playlist
            to_delete.append({"path": str(f), "name": f.name, "size": f.stat().st_size})

    return jsonify({"to_delete": to_delete, "playlist_count": len(vp), "playlist_ids_found": len(playlist_ids)})


@app.route("/api/vault/mirror-confirm", methods=["POST"])
def api_vault_mirror_confirm() -> Response:
    """Delete confirmed mirror files and their sidecar thumbnails."""
    data = request.get_json(force=True) or {}
    paths = data.get("paths", [])
    deleted = []
    errors = []
    for fp in paths:
        try:
            f = Path(fp)
            if f.exists() and f.is_file():
                f.unlink()
                deleted.append(fp)
                # Delete sidecar thumbnail
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    sidecar = f.with_suffix(ext)
                    if sidecar.exists():
                        sidecar.unlink()
        except Exception as exc:
            errors.append({"path": fp, "error": str(exc)})
    return jsonify({"deleted": len(deleted), "errors": errors})


@app.route("/api/vault/file-thumbs", methods=["POST"])
def api_vault_file_thumbs() -> Response:
    data = request.get_json(force=True) or {}
    paths = data.get("paths", [])
    result = {}
    with analytics.get_conn() as con:
        for p in paths[:100]:
            fp = Path(p)
            # Prefer local sidecar (never expires)
            local_thumb = None
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                if fp.with_suffix(ext).exists():
                    local_thumb = f"/api/vault/thumb?path={p}"
                    break
            if local_thumb:
                result[p] = local_thumb
            else:
                # Fall back to DB URL (may expire for remote URLs)
                row = con.execute(
                    "SELECT thumbnail_url FROM downloads WHERE file_path=? LIMIT 1", [p]
                ).fetchone()
                if row and row[0]:
                    result[p] = row[0]
    return jsonify({"thumbs": result})


_STATS_MEDIA_EXTS = {'.mp3', '.mp4', '.mkv', '.webm', '.flac', '.m4a',
                    '.wav', '.opus', '.aac', '.ogg', '.avi', '.mov'}
_STATS_VIDEO_EXTS = {'.mp4', '.mkv', '.webm', '.avi', '.mov'}


@app.route("/api/vault/folder-stats")
def api_vault_folder_stats() -> Response:
    path = request.args.get("path", "")
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Invalid path"}), 400
    p = Path(path)
    try:
        all_files = [f for f in p.rglob("*") if f.is_file() and not f.name.startswith(".")]
        media_files = [f for f in all_files if f.suffix.lower() in _STATS_MEDIA_EXTS]
        total_size = sum(f.stat().st_size for f in media_files if f.exists())
        video_count = sum(1 for f in media_files if f.suffix.lower() in _STATS_VIDEO_EXTS)
        audio_count = len(media_files) - video_count
        format_counts: dict = {}
        for f in media_files:
            ext = f.suffix.lower().lstrip(".")
            if ext:
                format_counts[ext] = format_counts.get(ext, 0) + 1
        return jsonify({
            "path": str(p),
            "file_count": len(all_files),
            "media_count": len(media_files),
            "video_count": video_count,
            "audio_count": audio_count,
            "total_size_bytes": total_size,
            "formats": format_counts,
        })
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
    entry = {
        "id": entry_id,
        "name": data.get("name", ""),
        "url": data.get("url", ""),
        "folder": data.get("folder", ""),
        "folder_name": data.get("folder_name", ""),
        "use_subfolder": data.get("use_subfolder", True),
        "quality": data.get("quality", "1080p"),
        "mode": data.get("mode", "VIDEO"),
        "embed_thumbnail": data.get("embed_thumbnail", True),
        "embed_chapters": data.get("embed_chapters", True),
        "embed_metadata": data.get("embed_metadata", True),
        "embed_subs": data.get("embed_subs", False),
        "sub_langs": data.get("sub_langs", "en"),
        "sponsorblock": data.get("sponsorblock", False),
        "filename_template": data.get("filename_template", ""),
        "sync_mode": data.get("sync_mode", "add"),
        "last_synced": None,
        "created_at": now,
    }
    analytics.upsert_library_entry(entry)
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
    cfg = _load_config()
    base_folder = entry.get("folder") or cfg.get("output_dir", str(Path.home() / "Downloads"))
    if entry.get("use_subfolder") and entry.get("folder_name"):
        output_dir = str(Path(base_folder) / entry["folder_name"])
    else:
        output_dir = base_folder
    opts = {
        "mode": "library",
        "quality": entry.get("quality", "1080p"),
        "embed_thumbnail": entry.get("embed_thumbnail", True),
        "embed_chapters": entry.get("embed_chapters", True),
        "embed_metadata": entry.get("embed_metadata", True),
        "embed_subs": entry.get("embed_subs", False),
        "sub_langs": entry.get("sub_langs", "en"),
        "sponsorblock": entry.get("sponsorblock", False),
        "filename_template": entry.get("filename_template", ""),
        "sync_mode": sync_mode,
        "cookies_browser": cfg.get("cookies_browser", "none"),
        "cookies_file": cfg.get("cookies_file", ""),
        "rate_limit": cfg.get("rate_limit", ""),
        "proxy": cfg.get("proxy", ""),
        "sleep_interval": cfg.get("sleep_interval", 1),
    }

    def _sync() -> None:
        analytics.update_library_last_synced(entry_id)
        downloader.download_video(entry["url"], output_dir, opts, _push_progress, entry_id)

    threading.Thread(target=_sync, daemon=True).start()
    return jsonify({"status": "started", "library_id": entry_id})


# ── App init ──────────────────────────────────────────────────────────────────

def init_app() -> Flask:
    analytics.init_db()
    return app
