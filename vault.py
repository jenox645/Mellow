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
    FILE_THUMBS_LIMIT,
    IMAGE_EXTS,
    M3U8_TEMP_MAX_AGE_SECS,
    MEDIA_EXTS,
    THUMB_FFMPEG_SEEK_SECS,
    THUMB_FFMPEG_TIMEOUT_SECS,
    THUMB_FFMPEG_WIDTH,
    THUMB_PREVIEW_LIMIT,
    VIDEO_EXTS,
)
from ffmpeg_locate import find_ffmpeg

# Matches yt-dlp's YouTube ID embedded in filenames: [dQw4w9WgXcW]
_YT_ID_RE = _re.compile(r'\[([A-Za-z0-9_-]{11})\]')

# ── Media player paths ────────────────────────────────────────────────────────

_VLC_PATHS = [
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    "/usr/bin/vlc",
    "/usr/local/bin/vlc",
    "/snap/bin/vlc",
    "/var/lib/flatpak/exports/bin/org.videolan.VLC",
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

# Media files ffmpeg could not make a thumbnail for. The vault grid asks for
# every file's thumbnail on each render; without this an audio file with no
# cover art spawned ffmpeg again every time.
_thumb_failed: set[tuple[str, float]] = set()


def _generate_thumb(media: Path, sidecar: Path) -> bool:
    """Make a cached sidecar .jpg for a file that has none.

    Video: grab a frame. Audio: pull out the embedded cover art, if any.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return False
    try:
        key = (str(media), media.stat().st_mtime)
    except OSError:
        return False
    if key in _thumb_failed:
        return False
    scale = f"scale={THUMB_FFMPEG_WIDTH}:-1"
    kw: dict = {"capture_output": True, "timeout": THUMB_FFMPEG_TIMEOUT_SECS}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    def made() -> bool:
        return sidecar.exists() and sidecar.stat().st_size > 0

    try:
        if media.suffix.lower() in VIDEO_EXTS:
            result = subprocess.run(
                [ffmpeg, "-ss", str(THUMB_FFMPEG_SEEK_SECS), "-i", str(media), "-frames:v", "1",
                 "-vf", scale, "-q:v", "4", "-y", str(sidecar)], **kw)
            if result.returncode != 0 or not made():
                # Short clips: retry from the start
                result = subprocess.run(
                    [ffmpeg, "-i", str(media), "-frames:v", "1",
                     "-vf", scale, "-q:v", "4", "-y", str(sidecar)], **kw)
        else:
            # The cover art of an audio file is its only "video" stream
            result = subprocess.run(
                [ffmpeg, "-i", str(media), "-map", "0:v:0", "-frames:v", "1",
                 "-vf", scale, "-q:v", "4", "-y", str(sidecar)], **kw)
        ok = result.returncode == 0 and made()
    except Exception:
        ok = False
    if not ok:
        _thumb_failed.add(key)
        sidecar.unlink(missing_ok=True)
    return ok


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
    # Sidecars share the media file's full stem: "Episode.10.mp4" pairs with
    # "Episode.10.jpg" (with_suffix would look for "Episode.jpg", which is a
    # different video's thumbnail or nothing)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        thumb = p.parent / (p.stem + ext)
        if thumb.exists():
            try:
                return thumb.read_bytes(), _mime_for_ext(ext)
            except Exception:
                return None
    # No sidecar (pre-existing file / watched folder): make one with ffmpeg on
    # demand and cache it next to the file.
    if p.suffix.lower() in MEDIA_EXTS:
        sidecar = p.parent / (p.stem + ".jpg")
        if _generate_thumb(p, sidecar):
            try:
                return sidecar.read_bytes(), "image/jpeg"
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
    # Single pass: stat() each file once (rglob over network/WSL mounts is
    # slow, and the previous version statted every file 3-4 times).
    file_count = 0
    media: list[tuple[str, int, float, str]] = []  # (name, size, mtime, ext)
    try:
        for f in p.rglob("*"):
            if not f.is_file() or f.name.startswith("."):
                continue
            file_count += 1
            ext = f.suffix.lower()
            if ext in MEDIA_EXTS:
                try:
                    st = f.stat()
                except OSError:
                    continue
                media.append((f.name, st.st_size, st.st_mtime, ext))
    except PermissionError:
        pass
    total_size = sum(m[1] for m in media)
    video_count = sum(1 for m in media if m[3] in VIDEO_EXTS)
    audio_count = len(media) - video_count
    format_counts: dict = {}
    for m in media:
        ext = m[3].lstrip(".")
        if ext:
            format_counts[ext] = format_counts.get(ext, 0) + 1
    by_size = sorted(media, key=lambda m: m[1], reverse=True)
    avg_size = int(total_size / len(media)) if media else 0
    largest = {"name": by_size[0][0], "size": by_size[0][1]} if by_size else None
    smallest = {"name": by_size[-1][0], "size": by_size[-1][1]} if by_size else None
    by_mtime = sorted(media, key=lambda m: m[2])
    newest = {"name": by_mtime[-1][0], "ts": by_mtime[-1][2]} if by_mtime else None
    oldest = {"name": by_mtime[0][0], "ts": by_mtime[0][2]} if by_mtime else None
    return {
        "path": str(p),
        "file_count": file_count,
        "media_count": len(media),
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

def get_mirror_preview(path: str, vp: list[str], request_opts: dict | None = None) -> dict:
    """Return local files not present in any linked playlist."""
    import yt_dlp as _ydl

    import downloader
    ydl_opts: dict = {"quiet": True, "extract_flat": True, "skip_download": True}
    if request_opts:
        # Same cookies/proxy as the sync itself, so private playlists list
        downloader._apply_cookie_opts(ydl_opts, request_opts)
        downloader._apply_network_opts(ydl_opts, request_opts)
    playlist_ids: set[str] = set()
    fetch_errors: list[str] = []
    for playlist_url in vp:
        try:
            with _ydl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
            if not info:
                raise ValueError("no playlist data")
            for entry in (info.get("entries") or []):
                if entry and entry.get("id"):
                    playlist_ids.add(entry["id"])
        except Exception as exc:
            print(f"[MIRROR-PREVIEW] failed to fetch {playlist_url}: {exc}", flush=True)
            fetch_errors.append(playlist_url)

    p = Path(path)
    # IDs backed by an actual file on disk (deletable) vs archive-only IDs
    # (no file — listing them as deletable produced size-0 phantom entries).
    file_ids: dict[str, str] = {}
    for f in p.iterdir():
        if not f.is_file() or f.suffix.lower() not in MEDIA_EXTS:
            continue
        m = _re.search(r'\[([A-Za-z0-9_-]{11})\]', f.name)
        if m:
            file_ids[m.group(1)] = f.name
    # The default "%(title)s" names carry no [id]; recover it from the
    # download history, or mirror mode could never remove anything.
    for vid_id, fname in _history_ids_in(p).items():
        file_ids.setdefault(vid_id, fname)
    archive_ids: set[str] = set()
    for archive_file in [p / "mellow_archive.txt", *p.glob(".mellow_archive_*.txt")]:
        if not archive_file.exists():
            continue
        try:
            for line in archive_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.strip().split()
                # Only youtube entries can be matched against YouTube playlist IDs
                if len(parts) == 2 and parts[0].lower() == "youtube":
                    archive_ids.add(parts[1])
        except Exception:
            pass

    to_delete = []
    # A playlist that failed to load would make its files look orphaned:
    # propose no deletions at all unless every linked playlist was read
    if playlist_ids and not fetch_errors:
        for vid_id, fname in file_ids.items():
            if vid_id not in playlist_ids:
                f_path = p / fname
                if not f_path.exists():
                    continue
                to_delete.append({
                    "path": str(f_path),
                    "name": fname, "size": f_path.stat().st_size, "video_id": vid_id,
                })
    known_ids = set(file_ids) | archive_ids
    return {
        "to_delete": to_delete,
        "to_add_count": len(playlist_ids - known_ids),
        "unchanged_count": len(playlist_ids & known_ids),
        "playlist_count": len(vp),
        "playlist_ids_found": len(playlist_ids),
        "fetch_errors": fetch_errors,
    }


_YT_URL_ID_RE = _re.compile(r'(?:[?&]v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})')


def _history_ids_in(folder: Path) -> dict[str, str]:
    """YouTube id -> file name, for files in `folder` that the download
    history knows the source URL of."""
    ids: dict[str, str] = {}
    try:
        with analytics.get_conn() as con:
            rows = con.execute(
                "SELECT file_path, url FROM downloads WHERE status='success' AND file_path IS NOT NULL"
            ).fetchall()
    except Exception:
        return ids
    for file_path, url in rows:
        f = Path(file_path)
        if f.parent != folder or not f.is_file():
            continue
        m = _YT_URL_ID_RE.search(url or "")
        if m:
            ids.setdefault(m.group(1), f.name)
    return ids


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

def generate_archive(folder: str, prune: bool = False) -> dict:
    """Create or update mellow_archive.txt.

    prune=False (default): only writes if the file is missing or empty —
      merges old hidden archives and backfills from media files on disk.
      Used by the downloader and initial vault-watch setup so yt-dlp can
      skip files that are already present.

    prune=True: always rewrites — backfills new entries AND removes entries
      whose files have been deleted. Only YouTube IDs can be verified from
      filenames; other extractor entries are left untouched.
    """
    p = Path(folder)
    archive_path = p / "mellow_archive.txt"

    file_has_content = archive_path.exists() and archive_path.stat().st_size > 0
    if not prune and file_has_content:
        return {"ok": True, "path": str(archive_path), "migrated": False, "backfilled": 0, "pruned": 0}

    # Read existing archive lines
    existing_lines: list[str] = []
    if archive_path.exists():
        existing_lines = [
            ln.strip()
            for ln in archive_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if ln.strip()
        ]

    # Merge + remove all old hidden archives
    migrated = False
    seen = set(existing_lines)
    for old in sorted(_glob.glob(str(p / ".mellow_archive_*.txt"))):
        try:
            old_path = Path(old)
            for ln in old_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                ln = ln.strip()
                if ln and ln not in seen:
                    existing_lines.append(ln)
                    seen.add(ln)
            old_path.unlink()
            migrated = True
        except OSError:
            pass

    # Split YouTube entries (verifiable via filename) from everything else
    yt_in_archive: dict[str, str] = {}  # youtube_id → full line
    other_lines: list[str] = []
    for line in existing_lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower() == "youtube":
            yt_in_archive[parts[1]] = line
        else:
            other_lines.append(line)

    # Scan disk for media files whose names contain a YouTube ID
    disk_yt_ids: set[str] = set()
    try:
        for f in p.iterdir():
            if f.is_file() and f.suffix.lower() in MEDIA_EXTS:
                m = _YT_ID_RE.search(f.name)
                if m:
                    disk_yt_ids.add(m.group(1))
    except PermissionError:
        pass

    # Keep or prune existing YouTube entries; backfill new ones
    pruned = 0
    backfilled = 0
    final_yt_lines: list[str] = []
    for vid_id, line in yt_in_archive.items():
        if prune and vid_id not in disk_yt_ids:
            pruned += 1
        else:
            final_yt_lines.append(line)
    for vid_id in disk_yt_ids:
        if vid_id not in yt_in_archive:
            final_yt_lines.append(f"youtube {vid_id}")
            backfilled += 1

    try:
        with archive_path.open("w", encoding="utf-8") as fh:
            for line in other_lines + final_yt_lines:
                fh.write(line + "\n")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "path": str(archive_path), "migrated": migrated, "backfilled": backfilled, "pruned": pruned}


# ── Storage budget ────────────────────────────────────────────────────────────

def get_cleanup_candidates(path: str, budget_bytes: int) -> dict:
    """When a folder exceeds its budget, suggest files to free the overage.

    Suggestion order: oldest first, ties broken by size (largest first).
    Never deletes anything — the UI presents the list for manual action.
    """
    p = Path(path)
    files: list[dict] = []
    total = 0
    try:
        for f in p.rglob("*"):
            if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in MEDIA_EXTS:
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            total += st.st_size
            files.append({"path": str(f), "name": f.name,
                          "size": st.st_size, "mtime": st.st_mtime})
    except PermissionError:
        pass

    over = total - budget_bytes
    candidates: list[dict] = []
    if over > 0:
        files.sort(key=lambda x: (x["mtime"], -x["size"]))
        freed = 0
        for f in files:
            if freed >= over:
                break
            candidates.append(f)
            freed += f["size"]
    return {
        "path": str(p),
        "total_bytes": total,
        "budget_bytes": budget_bytes,
        "over_bytes": max(0, over),
        "candidates": candidates,
    }


# ── Duplicate finder ──────────────────────────────────────────────────────────

def find_duplicates(folders: list[str]) -> list[dict]:
    """Scan vault folders for files sharing the same [videoID] across paths.

    Returns groups sorted by wasted bytes; each group lists every copy so the
    UI can offer to delete the smaller ones.
    """
    by_id: dict[str, list[dict]] = {}
    seen_paths: set[str] = set()
    for folder in folders:
        p = Path(folder)
        if not p.is_dir():
            continue
        try:
            for f in p.iterdir():
                if not f.is_file() or f.suffix.lower() not in MEDIA_EXTS:
                    continue
                key = str(f)
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                m = _YT_ID_RE.search(f.name)
                if not m:
                    continue
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                by_id.setdefault(m.group(1), []).append(
                    {"path": key, "name": f.name, "folder": str(p), "size": size})
        except PermissionError:
            continue
    groups = []
    for vid_id, copies in by_id.items():
        if len(copies) < 2:
            continue
        copies.sort(key=lambda c: c["size"], reverse=True)
        groups.append({
            "video_id": vid_id,
            "copies": copies,
            # Everything except the largest copy is reclaimable
            "wasted_bytes": sum(c["size"] for c in copies[1:]),
        })
    groups.sort(key=lambda g: g["wasted_bytes"], reverse=True)
    return groups


# ── Media player launch ───────────────────────────────────────────────────────

def launch_playlist(paths: list[str], open_file_fn: Callable[[str], None]) -> str:
    """Open media files in a player. Returns method name used."""
    import shutil
    import tempfile
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

    # Sweep playlist temp files older than a day before writing a new one
    tmp_dir = Path(tempfile.gettempdir())
    try:
        import time as _time
        cutoff = _time.time() - M3U8_TEMP_MAX_AGE_SECS
        for old in tmp_dir.glob("mellow_*.m3u8"):
            if old.stat().st_mtime < cutoff:
                old.unlink(missing_ok=True)
    except OSError:
        pass

    lines = ["#EXTM3U"] + [p.replace("\\", "/") for p in valid]
    content = "\n".join(lines)
    with tempfile.NamedTemporaryFile(mode="wb", prefix="mellow_", suffix=".m3u8", delete=False) as f:
        f.write(b"\xef\xbb\xbf" + content.encode("utf-8"))
        temp_path = f.name
    threading.Thread(target=open_file_fn, args=(temp_path,), daemon=True).start()
    return temp_path


# ── Sync opts builder ─────────────────────────────────────────────────────────

# Format choices a folder remembers between syncs (vault_sync_formats in config)
SYNC_FORMAT_KEYS = (
    "sync_audio", "audio_format", "audio_quality", "quality", "container",
    "embed_thumbnail", "embed_subs", "embed_chapters", "embed_metadata", "sponsorblock",
)
_AUDIO_SYNC_FORMATS = ("mp3", "m4a", "aac", "flac", "opus", "wav")
_VIDEO_SYNC_CONTAINERS = ("mp4", "mkv", "webm")


def infer_folder_format(path: str) -> dict:
    """Guess what a folder holds from its media files: a folder of .mp3s syncs
    as MP3 audio, not as 1080p video."""
    audio: dict[str, int] = {}
    video: dict[str, int] = {}
    try:
        for f in Path(path).iterdir():
            ext = f.suffix.lower().lstrip(".")
            if not f.is_file() or f.suffix.lower() not in MEDIA_EXTS:
                continue
            bucket = video if f.suffix.lower() in VIDEO_EXTS else audio
            bucket[ext] = bucket.get(ext, 0) + 1
    except OSError:
        return {}
    if not audio and not video:
        return {}
    if sum(audio.values()) > sum(video.values()):
        fmt = max(audio, key=audio.get)
        return {"sync_audio": True, "audio_format": fmt if fmt in _AUDIO_SYNC_FORMATS else "mp3"}
    ext = max(video, key=video.get)
    return {"sync_audio": False, "container": ext if ext in _VIDEO_SYNC_CONTAINERS else "mp4"}


def default_sync_format(path: str, lib: dict | None, cfg: dict) -> dict:
    """Format a sync of this folder uses when the request doesn't say.

    Last choice made for the folder, then its library entry, then a guess from
    the files already in it. Auto-sync and "sync all" have no dialog, so
    without this an audio folder was synced as 1080p video.
    """
    saved = (cfg.get("vault_sync_formats") or {}).get(path) if path else None
    if saved:
        return {k: v for k, v in saved.items() if k in SYNC_FORMAT_KEYS}
    if lib:
        return {
            "sync_audio": (lib.get("mode") or "").upper() == "AUDIO",
            "audio_format": lib.get("audio_format") or "mp3",
            "quality": lib.get("quality") or cfg.get("default_quality", "1080p"),
            "container": lib.get("container") or "mp4",
            "embed_thumbnail": lib.get("embed_thumbnail", True),
            "embed_subs": lib.get("embed_subs", False),
            "embed_chapters": lib.get("embed_chapters", True),
            "embed_metadata": lib.get("embed_metadata", True),
            "sponsorblock": lib.get("sponsorblock", False),
        }
    return infer_folder_format(path) if path else {}


def build_sync_opts(data: dict, lib: dict | None, cfg: dict, path: str = "") -> dict:
    """Build a yt-dlp opts dict for a vault sync request.

    Precedence per option: the request, then default_sync_format(), then the
    Config defaults.
    """
    base = default_sync_format(path, lib, cfg)

    def pick(key: str, fallback):
        value = data.get(key)
        if value is None or value == "":
            value = base.get(key)
        return fallback if value is None or value == "" else value

    return {
        "mode": "library",
        "quality": pick("quality", cfg.get("default_quality", "1080p")),
        "container": str(pick("container", cfg.get("default_container", "mp4"))).lower(),
        "sync_audio": bool(pick("sync_audio", False)),
        "audio_format": str(pick("audio_format", cfg.get("default_audio_format", "mp3"))).lower(),
        "audio_quality": pick("audio_quality", cfg.get("default_audio_quality", "best")),
        "embed_thumbnail": pick("embed_thumbnail", True),
        "embed_chapters": pick("embed_chapters", True),
        "embed_metadata": pick("embed_metadata", True),
        "embed_subs": pick("embed_subs", False),
        "sponsorblock": pick("sponsorblock", False),
        "filename_template": (lib or {}).get("filename_template") or cfg.get("filename_template", ""),
        "cookies_browser": cfg.get("cookies_browser", "none"),
        "cookies_file": cfg.get("cookies_file", ""),
        "cookies_browser_profile": cfg.get("cookies_browser_profile", ""),
        "rate_limit": cfg.get("rate_limit", ""),
        "proxy": cfg.get("proxy", ""),
        "force_ipv4": bool(cfg.get("force_ipv4", False)),
        "concurrent_fragments": cfg.get("concurrent_fragments", 4),
        "sleep_interval": cfg.get("sleep_interval", 0),
        "retries": cfg.get("retries", 3),
    }
