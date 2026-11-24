"""Thumbnails kept in this account's cache folder (datadir.cache_dir()/thumbs).

The vault keeps a video's frame as a sidecar next to it when it can; a folder
it can't write to (a read-only mount, another account's files) gets its
thumbnails here instead. Audio covers always come here: the file itself holds
the picture, so nothing is added to a music folder. An entry is named by the
file's path, mtime and size, so a changed file gets a new one; the oldest go
once the folder passes THUMB_DISK_CACHE_MAX_BYTES.
"""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import threading
from pathlib import Path

from . import datadir
from .constants import THUMB_DISK_CACHE_MAX_BYTES, THUMB_DISK_CACHE_PRUNE_EVERY

log = logging.getLogger(__name__)

_EXTS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
_lock = threading.Lock()
_writes = 0


def folder() -> Path:
    return datadir.cache_dir() / "thumbs"


def _name(media: Path, st: os.stat_result) -> str:
    where = os.path.normcase(os.path.abspath(media))
    return hashlib.sha1(f"{where}|{st.st_mtime_ns}|{st.st_size}".encode("utf-8", "surrogatepass")).hexdigest()


def get(media: Path, st: os.stat_result) -> tuple[bytes, str] | None:
    base = folder() / _name(media, st)
    for mime, ext in _EXTS.items():
        try:
            return base.with_suffix(ext).read_bytes(), mime
        except OSError:
            continue
    return None


def put(media: Path, st: os.stat_result, data: bytes, mime: str) -> None:
    """Keep a thumbnail; a cache that can't be written to only costs a remake."""
    global _writes
    target = folder() / (_name(media, st) + _EXTS.get(mime, ".jpg"))
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        log.warning(f"thumbnail cache: can't write {target}: {exc}")
        return
    with _lock:
        _writes += 1
        due = _writes % THUMB_DISK_CACHE_PRUNE_EVERY == 1
    if due:
        prune()


def prune(max_bytes: int = THUMB_DISK_CACHE_MAX_BYTES) -> int:
    """Remove the oldest thumbnails until the cache is under 80 % of max_bytes.
    Returns how many went."""
    entries = []
    try:
        with os.scandir(folder()) as it:
            for e in it:
                try:
                    if e.is_file():
                        st = e.stat()
                        entries.append((st.st_mtime, st.st_size, e.path))
                except OSError:
                    pass
    except OSError:
        return 0
    total = sum(size for _, size, _ in entries)
    if total <= max_bytes:
        return 0
    removed = 0
    for _, size, path in sorted(entries):
        if total <= max_bytes * 0.8:
            break
        try:
            os.unlink(path)
            total -= size
            removed += 1
        except OSError:
            pass
    log.info(f"thumbnail cache: removed {removed} old thumbnail(s)")
    return removed
