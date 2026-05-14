"""Vault business logic — folder listing, thumbnails, media player, mirror ops."""
from __future__ import annotations

import glob as _glob
import os
import re as _re
import subprocess
import threading
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import analytics
from constants import (
    AUDIO_EXTS, IMAGE_EXTS, MEDIA_EXTS, THUMB_CACHE_SECS,
    THUMB_PREVIEW_LIMIT, FILE_THUMBS_LIMIT, VIDEO_EXTS,
)

# ── Media player paths ────────────────────────────────────────────────────────

_VLC_PATHS = [
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    "/usr/bin/vlc",
    "/usr/local/bin/vlc",
    "/snap/bin/vlc",
    "/flatpak/exports/bin/org.videolan.VLC",
]
_MPV_PATHS = [
    "/usr/bin/mpv",
    "/usr/local/bin/mpv",
    "/snap/bin/mpv",
    r"C:\Program Files\mpv\mpv.exe",
    r"C:\Program Files (x86)\mpv\mpv.exe",
]
_MPC_PATHS = [
    r"C:\Program Files\MPC-HC\mpc-hc64.exe",
    r"C:\Program Files\MPC-HC\mpc-hc.exe",
    r"C:\Program Files (x86)\MPC-HC\mpc-hc.exe",
    r"C:\Program Files\MPC-BE x64\mpc-be64.exe",
    r"C:\Program Files (x86)\MPC-BE\mpc-be.exe",
]


# ── Folder stats helper ───────────────────────────────────────────────────────

def get_folder_media_stats(path: str) -> dict:
    p = Path(path)
    if not p.is_dir():
        return {"item_count": 0, "size_bytes": 0}
    total, count = 0, 0
    try:
        for entry in p.rglob("*"):
            if entry.is_file() and not entry.name.startswith(".") and entry.suffix.lower() in MEDIA_EXTS:
                total += entry.stat().st_size
                count += 1
    except PermissionError:
        pass
    return {"item_count": count, "size_bytes": total}


# ── Vault folder list ─────────────────────────────────────────────────────────

def build_folder_list(base_path: str, cfg: dict) -> list[dict]:
    """Return the full vault folder list (db + watched + library-linked)."""
    all_folders = analytics.get_vault_folders(base_path)
    all_paths: set[str] = {f["path"] for f in all_folders}

    for wp in cfg.get("watched_folders", []):
        p = Path(wp)
        norm = str(p)
        if norm not in all_paths and p.exists() and p.is_dir():
            try:
                ms = get_folder_media_stats(norm)
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
                    ms = get_folder_media_stats(actual_path)
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

    vault_names = cfg.get("vault_names", {})
    vault_hidden = set(cfg.get("vault_hidden", []))
    vault_sync_times = cfg.get("vault_sync_times", {})
    for f in all_folders:
        if f["path"] in vault_names:
            f["name"] = vault_names[f["path"]]
        has_playlists = bool(cfg.get("vault_playlists", {}).get(f["path"]))
        if has_playlists and f["path"] in vault_sync_times:
            f["last_synced"] = vault_sync_times[f["path"]]
    return [f for f in all_folders if f["path"] not in vault_hidden]


# ── Folder file listing ───────────────────────────────────────────────────────

def list_folder_files(path: str) -> list[dict]:
    root = Path(path)
    files = []
    try:
        for f in sorted(root.iterdir()):
            if f.is_file() and f.suffix.lower() in MEDIA_EXTS and not f.name.startswith("."):
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
    return files


# ── Thumbnail serving ─────────────────────────────────────────────────────────

def get_thumb_bytes(path: str) -> tuple[bytes, str] | None:
    """Return (raw_bytes, mime_type) for a thumbnail, or None if not found."""
    p = Path(path)
    if p.suffix.lower() in IMAGE_EXTS and p.exists():
        mime = _mime_for_ext(p.suffix.lower())
        try:
            return p.read_bytes(), mime
        except Exception:
            return None
    if not p.exists():
        return None
    base = p.with_suffix("")
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        thumb = base.with_suffix(ext)
        if thumb.exists():
            try:
                return thumb.read_bytes(), _mime_for_ext(ext)
            except Exception:
                return None
    return None


def _mime_for_ext(ext: str) -> str:
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    return "image/webp"


# ── Folder preview mosaics ────────────────────────────────────────────────────

def get_folder_previews(path: str) -> list[str]:
    """Return up to THUMB_PREVIEW_LIMIT thumbnail URLs for a folder."""
    root = Path(path)
    thumb_urls: list[str] = []
    try:
        all_files = list(root.iterdir())
        img_map = {
            f.stem.lower(): f
            for f in all_files
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        }
        for f in sorted(all_files):
            if f.is_file() and f.suffix.lower() in MEDIA_EXTS and not f.name.startswith("."):
                match = img_map.get(f.stem.lower())
                if match:
                    thumb_urls.append(f"/api/vault/thumb?path={quote(str(match))}")
                if len(thumb_urls) >= THUMB_PREVIEW_LIMIT:
                    break
    except PermissionError:
        pass
    return thumb_urls


# ── File thumb resolution ─────────────────────────────────────────────────────

def resolve_file_thumbs(paths: list[str], get_conn: Callable) -> dict[str, str]:
    """Map file paths to their thumbnail URL (sidecar or DB fallback)."""
    result: dict[str, str] = {}
    _dir_cache: dict[str, dict] = {}

    def _dir_images(parent: Path) -> dict:
        key = str(parent)
        if key not in _dir_cache:
            try:
                _dir_cache[key] = {
                    f.stem.lower(): f
                    for f in parent.iterdir()
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTS
                }
            except Exception:
                _dir_cache[key] = {}
        return _dir_cache[key]

    with get_conn() as con:
        for p in paths[:FILE_THUMBS_LIMIT]:
            fp = Path(p)
            match = _dir_images(fp.parent).get(fp.stem.lower())
            if match:
                result[p] = f"/api/vault/thumb?path={quote(str(match))}"
            else:
                row = con.execute(
                    "SELECT thumbnail_url FROM downloads WHERE file_path=? LIMIT 1", [p]
                ).fetchone()
                if row and row[0]:
                    result[p] = row[0]
    return result


# ── Folder stats ──────────────────────────────────────────────────────────────

def get_folder_stats(path: str, linked_playlists: list) -> dict:
    p = Path(path)
    all_files = [f for f in p.rglob("*") if f.is_file() and not f.name.startswith(".")]
    media_files = [f for f in all_files if f.suffix.lower() in MEDIA_EXTS]
    total_size = sum(f.stat().st_size for f in media_files if f.exists())
    video_count = sum(1 for f in media_files if f.suffix.lower() in VIDEO_EXTS)
    audio_count = len(media_files) - video_count
    format_counts: dict = {}
    for f in media_files:
        ext = f.suffix.lower().lstrip(".")
        if ext:
            format_counts[ext] = format_counts.get(ext, 0) + 1
    sizes = [(f.stat().st_size, f) for f in media_files if f.exists()]
    sizes.sort(key=lambda x: x[0], reverse=True)
    avg_size = int(total_size / len(sizes)) if sizes else 0
    largest = {"name": sizes[0][1].name, "size": sizes[0][0]} if sizes else None
    smallest = {"name": sizes[-1][1].name, "size": sizes[-1][0]} if sizes else None
    mtimes = [(f.stat().st_mtime, f) for f in media_files if f.exists()]
    newest = {"name": max(mtimes, key=lambda x: x[0])[1].name, "ts": max(mtimes, key=lambda x: x[0])[0]} if mtimes else None
    oldest = {"name": min(mtimes, key=lambda x: x[0])[1].name, "ts": min(mtimes, key=lambda x: x[0])[0]} if mtimes else None
    return {
        "path": str(p),
        "file_count": len(all_files),
        "media_count": len(media_files),
        "video_count": video_count,
        "audio_count": audio_count,
        "total_size_bytes": total_size,
        "avg_size_bytes": avg_size,
        "formats": format_counts,
        "largest_file": largest,
        "smallest_file": smallest,
        "newest_file": newest,
        "oldest_file": oldest,
        "linked_playlists": len(linked_playlists),
    }


# ── Mirror preview & confirm ──────────────────────────────────────────────────

def get_mirror_preview(path: str, vp: list[str]) -> dict:
    """Return local files not present in any linked playlist."""
    import yt_dlp as _ydl
    playlist_ids: set[str] = set()
    for playlist_url in vp:
        try:
            with _ydl.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True}) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
                if info and "entries" in info:
                    for entry in (info["entries"] or []):
                        if entry and entry.get("id"):
                            playlist_ids.add(entry["id"])
        except Exception as exc:
            print(f"[MIRROR-PREVIEW] failed to fetch {playlist_url}: {exc}", flush=True)

    p = Path(path)
    local_ids: dict[str, str] = {}
    for f in p.iterdir():
        if not f.is_file() or f.suffix.lower() not in MEDIA_EXTS:
            continue
        m = _re.search(r'\[([A-Za-z0-9_-]{11})\]', f.name)
        if m:
            local_ids[m.group(1)] = f.name
    for archive_file in p.glob(".mellow_archive_*.txt"):
        try:
            for line in archive_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.strip().split()
                if len(parts) == 2:
                    local_ids.setdefault(parts[1], parts[1])
        except Exception:
            pass

    to_delete = []
    for vid_id, fname in local_ids.items():
        if vid_id not in playlist_ids and playlist_ids:
            f_path = p / fname
            size = f_path.stat().st_size if f_path.exists() else 0
            to_delete.append({
                "path": str(f_path) if f_path.exists() else fname,
                "name": fname, "size": size, "video_id": vid_id,
            })
    return {
        "to_delete": to_delete,
        "to_add_count": len(playlist_ids - set(local_ids.keys())),
        "unchanged_count": len(playlist_ids & set(local_ids.keys())),
        "playlist_count": len(vp),
        "playlist_ids_found": len(playlist_ids),
    }


def confirm_mirror_delete(paths: list[str]) -> dict:
    deleted, errors = [], []
    for fp in paths:
        try:
            f = Path(fp)
            if f.exists() and f.is_file():
                f.unlink()
                deleted.append(fp)
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    sidecar = f.with_suffix(ext)
                    if sidecar.exists():
                        sidecar.unlink()
        except Exception as exc:
            errors.append({"path": fp, "error": str(exc)})
    return {"deleted": len(deleted), "errors": errors}


# ── Archive file ──────────────────────────────────────────────────────────────

def generate_archive(folder: str) -> dict:
    """Create mellow_archive.txt (or migrate old hidden archive). Returns status dict."""
    p = Path(folder)
    archive_path = p / "mellow_archive.txt"
    migrated = False
    if not archive_path.exists():
        for old in _glob.glob(str(p / ".mellow_archive_*.txt")):
            try:
                Path(old).rename(archive_path)
                migrated = True
                break
            except OSError:
                pass
        if not migrated:
            try:
                archive_path.touch()
            except OSError as exc:
                return {"ok": False, "error": str(exc)}
    return {"ok": True, "path": str(archive_path), "migrated": migrated}


# ── Media player launch ───────────────────────────────────────────────────────

def launch_playlist(paths: list[str], open_file_fn: Callable[[str], None]) -> str:
    """Open media files in a player. Returns method name used."""
    import tempfile, shutil
    valid = [p for p in paths if Path(p).exists()]
    if not valid:
        return "no_files"

    def _find(candidates: list[str]) -> str | None:
        return next((c for c in candidates if os.path.exists(c)), None)

    vlc = _find(_VLC_PATHS) or shutil.which("vlc")
    if vlc:
        threading.Thread(
            target=lambda: subprocess.Popen([vlc, "--playlist-enqueue"] + valid),
            daemon=True,
        ).start()
        return "vlc_direct"

    mpv = _find(_MPV_PATHS) or shutil.which("mpv")
    if mpv:
        threading.Thread(
            target=lambda: subprocess.Popen([mpv] + valid),
            daemon=True,
        ).start()
        return "mpv_direct"

    mpc = _find(_MPC_PATHS)
    if mpc:
        threading.Thread(
            target=lambda: subprocess.Popen([mpc] + valid),
            daemon=True,
        ).start()
        return "mpc_direct"

    lines = ["#EXTM3U"] + [p.replace("\\", "/") for p in valid]
    content = "\n".join(lines)
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".m3u8", delete=False) as f:
        f.write(b"\xef\xbb\xbf" + content.encode("utf-8"))
        temp_path = f.name
    threading.Thread(target=open_file_fn, args=(temp_path,), daemon=True).start()
    return temp_path


# ── Sync opts builder ─────────────────────────────────────────────────────────

def build_sync_opts(data: dict, lib: dict | None, cfg: dict) -> dict:
    """Build a yt-dlp opts dict for a vault sync request."""
    q = data.get("quality") or (lib["quality"] if lib else cfg.get("quality_default", "1080p"))
    return {
        "mode": "library",
        "quality": q,
        "container": (data.get("container") or "mp4").lower(),
        "sync_audio": data.get("sync_audio", False),
        "audio_format": data.get("audio_format", "mp3"),
        "embed_thumbnail": data.get("embed_thumbnail", lib["embed_thumbnail"] if lib else cfg.get("embed_thumbnail", True)),
        "embed_chapters": data.get("embed_chapters", lib["embed_chapters"] if lib else True),
        "embed_metadata": data.get("embed_metadata", lib["embed_metadata"] if lib else True),
        "embed_subs": data.get("embed_subs", lib.get("embed_subs", False) if lib else False),
        "sponsorblock": data.get("sponsorblock", lib.get("sponsorblock", False) if lib else False),
        "cookies_browser": cfg.get("cookies_browser", "none"),
        "cookies_file": cfg.get("cookies_file", ""),
        "cookies_browser_profile": cfg.get("cookies_browser_profile", ""),
        "rate_limit": cfg.get("rate_limit", ""),
        "proxy": cfg.get("proxy", ""),
        "concurrent_fragments": cfg.get("concurrent_fragments", 4),
        "sleep_interval": cfg.get("sleep_interval", 0),
        "retries": cfg.get("retries", 3),
    }
