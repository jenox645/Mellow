"""Serving the vault's thumbnails without making anyone wait (#126).

`/api/vault/thumb` answers from what already exists, at once:
- a sidecar (or any picture asked for by its path): its small copy when one was made, else the
  picture itself while a small copy is made in the background (a download's sidecar is a 1280 px
  jpg; the cards show it a few hundred pixels wide);
- a media file without a sidecar: the picture made for it before (thumb_cache), or the cover
  inside an audio file (mutagen, a few milliseconds). What needs ffmpeg (a video's frame, a cover
  mutagen can't read, shrinking a big cover) is never made in the request: it goes to a small
  background pool and the answer is PENDING. The page shows its placeholder and asks again
  (components/thumb-img.jsx); the pool takes the newest request first, which is what is on
  screen.

`vault.get_thumb_bytes` stays the one that makes a picture there and then: the pool runs it.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import covers, thumb_cache, vault
from .constants import (
    IMAGE_EXTS,
    MEDIA_EXTS,
    THUMB_COVER_RAW_MAX_BYTES,
    THUMB_QUEUE_MAX,
    THUMB_SMALL_MIN_BYTES,
    THUMB_WORKERS,
    VIDEO_EXTS,
)
from .ffmpeg_locate import find_ffmpeg

log = logging.getLogger(__name__)

PENDING = "pending"
SMALL = "small"


@dataclass(frozen=True)
class Thumb:
    data: bytes
    mime: str
    etag: str
    # False: a better picture (its small copy) is being made, so the window must ask again
    # rather than keep this one
    final: bool = True


class Pool:
    """A few threads that make pictures; the newest job first (what the window shows now).

    Two lines: what a card waits for (a frame, a cover) goes before what only makes a shown picture
    smaller. A job asked for again moves to the front of its line; one already running isn't added
    twice. Past THUMB_QUEUE_MAX waiting jobs in a line the oldest go: they were scrolled past, and
    are asked for again if they come back on screen."""

    def __init__(self, workers: int = THUMB_WORKERS, limit: int = THUMB_QUEUE_MAX):
        self._workers, self._limit = workers, limit
        self._lines: tuple[OrderedDict, OrderedDict] = (OrderedDict(), OrderedDict())   # (needed, smaller)
        self._busy: set[tuple] = set()
        self._threads: list[threading.Thread] = []
        self._cv = threading.Condition()

    def submit(self, key: tuple, job: Callable[[], object], needed: bool = True) -> None:
        with self._cv:
            if key in self._busy:
                return
            line = self._lines[0 if needed else 1]
            if key in line:
                line.move_to_end(key)
            else:
                line[key] = job
                while len(line) > self._limit:
                    line.popitem(last=False)
            while len(self._threads) < self._workers:
                t = threading.Thread(target=self._run, name="thumbs", daemon=True)
                self._threads.append(t)
                t.start()
            self._cv.notify()

    def waiting(self, key: tuple) -> bool:
        with self._cv:
            return key in self._busy or any(key in line for line in self._lines)

    def idle(self, timeout: float = 10.0) -> bool:
        """Wait until nothing is waiting or running (tests)."""
        with self._cv:
            return self._cv.wait_for(lambda: not self._busy and not any(self._lines), timeout)

    def clear(self) -> None:
        with self._cv:
            for line in self._lines:
                line.clear()

    def _run(self) -> None:
        while True:
            with self._cv:
                self._cv.wait_for(lambda: any(self._lines))
                line = next(line for line in self._lines if line)
                key, job = line.popitem(last=True)
                self._busy.add(key)
            try:
                job()
            except Exception:
                log.exception(f"thumbnail job {key[0]} failed")
            finally:
                with self._cv:
                    self._busy.discard(key)
                    self._cv.notify_all()


pool = Pool()


def _etag(source: Path, st, variant: str) -> str:
    key = f"{source}|{st.st_mtime_ns}|{st.st_size}|{variant}"
    return '"' + hashlib.sha1(key.encode("utf-8", "surrogatepass")).hexdigest()[:24] + '"'


def _make_small(source: Path, st, data: bytes | None = None) -> None:
    """Keep a THUMB_FFMPEG_WIDTH copy of a big picture. When it can't be made smaller, the picture
    itself is kept as its small copy, so it isn't tried again."""
    try:
        data = data if data is not None else source.read_bytes()
    except OSError:
        return
    small = vault._shrink_cover(data)
    if small and len(small) < len(data):
        thumb_cache.put(source, st, small, "image/jpeg", SMALL)
    else:
        thumb_cache.put(source, st, data, covers.sniff_mime(data) or "image/jpeg", SMALL)


def _picture(source: Path, st, data: bytes | None = None, mime: str | None = None) -> Thumb | None:
    """A picture (a sidecar, or one made for a media file): its small copy when it's big."""
    given = data       # a picture made for a media file (`source`), not the file itself
    small = thumb_cache.get(source, st, SMALL) if st.st_size > THUMB_SMALL_MIN_BYTES or (
        data is not None and len(data) > THUMB_SMALL_MIN_BYTES) else None
    if small:
        return Thumb(small[0], small[1], _etag(source, st, SMALL))
    if data is None:
        try:
            data = source.read_bytes()
        except OSError:
            return None
        mime = vault._mime_for_ext(source.suffix.lower())
    if len(data) <= THUMB_SMALL_MIN_BYTES or not find_ffmpeg():
        return Thumb(data, mime, _etag(source, st, ""))
    # A sidecar is read again by the job: hundreds of waiting jobs don't hold its bytes
    pool.submit(("small", str(source), st.st_mtime_ns), lambda: _make_small(source, st, given), needed=False)
    return Thumb(data, mime, _etag(source, st, ""), final=False)


def serve(path: str) -> Thumb | str | None:
    """The thumbnail for `path` as it can be sent now, PENDING while the pool makes it, or None
    when there is none."""
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return None
    ext = p.suffix.lower()
    if ext in IMAGE_EXTS:
        return _picture(p, st)
    if ext not in MEDIA_EXTS:
        return None
    for side_ext in vault._SIDECAR_EXTS:
        side = p.parent / (p.stem + side_ext)
        try:
            side_st = side.stat()
        except OSError:
            continue
        return _picture(side, side_st)
    if (str(p), st.st_mtime) in vault._thumb_failed:
        return None
    made = thumb_cache.get(p, st)
    if made:
        return _picture(p, st, *made)
    job_key = ("make", str(p), st.st_mtime_ns)
    if ext not in VIDEO_EXTS and not pool.waiting(job_key):
        try:
            cover = covers.embedded_cover(p)
        except covers.NoCoverError:
            vault._thumb_failed.add((str(p), st.st_mtime))
            return None
        if cover and len(cover[0]) <= THUMB_COVER_RAW_MAX_BYTES:
            thumb_cache.put(p, st, *cover)
            return _picture(p, st, *cover)
        if cover:
            # A big cover (a 3000 px PNG): shown as it is while the pool scales it down
            pool.submit(job_key, lambda: vault.get_thumb_bytes(path))
            return Thumb(cover[0], cover[1], _etag(p, st, "cover"), final=False)
    # A video's frame, or a cover only ffmpeg can read
    if not find_ffmpeg():
        vault._thumb_failed.add((str(p), st.st_mtime))
        return None
    pool.submit(job_key, lambda: vault.get_thumb_bytes(path))
    return PENDING
