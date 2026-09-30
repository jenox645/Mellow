"""Locate ffmpeg — every merge, conversion and embed step depends on it.

Search order: `ffmpeg_location` config override → PATH → a copy shipped next
to the app → well-known install folders. The folders matter because a process
keeps the PATH it was launched with: an ffmpeg installed while MellowDLP is
running (winget, chocolatey, scoop, Homebrew) would otherwise stay invisible
until a restart, and macOS GUI apps never see the shell's PATH at all.
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
import threading
import time
from pathlib import Path

from config import load_config
from constants import FFMPEG_RECHECK_SECS

_EXE = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"

_lock = threading.Lock()
_cached: str | None = None
_last_miss: float = 0.0


def _candidate_dirs() -> list[Path]:
    here = Path(__file__).parent
    dirs: list[Path] = [here, here / "ffmpeg", here / "ffmpeg" / "bin"]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        dirs += [exe_dir, exe_dir / "ffmpeg", exe_dir / "ffmpeg" / "bin"]
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            winget = Path(local) / "Microsoft" / "WinGet"
            dirs.append(winget / "Links")
            dirs += [Path(p) for p in glob.glob(str(winget / "Packages" / "*FFmpeg*" / "*" / "bin"))]
        dirs += [
            Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "chocolatey" / "bin",
            Path.home() / "scoop" / "shims",
            Path(r"C:\ffmpeg\bin"),
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ffmpeg" / "bin",
        ]
    else:
        dirs += [Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path("/usr/bin"), Path("/snap/bin")]
    return dirs


def _search() -> str | None:
    override = str(load_config().get("ffmpeg_location") or "").strip()
    if override:
        p = Path(override)
        if p.is_dir():
            p = p / _EXE
        if p.is_file():
            return str(p)
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    for d in _candidate_dirs():
        candidate = d / _EXE
        if candidate.is_file():
            return str(candidate)
    return None


def _put_on_path(ffmpeg: str) -> None:
    """Make an ffmpeg found off-PATH visible to everything in this process.

    yt-dlp honours its ffmpeg_location option for postprocessing but not for
    its ffmpeg-based downloader (trimming, some HLS streams), which only ever
    looks on PATH.
    """
    folder = str(Path(ffmpeg).parent)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if folder not in parts:
        os.environ["PATH"] = os.pathsep.join([folder, *parts])


def find_ffmpeg(refresh: bool = False) -> str | None:
    """Absolute path of the ffmpeg executable, or None when it isn't installed.

    A hit is cached for as long as the file exists; a miss is re-probed at
    most every FFMPEG_RECHECK_SECS so installing ffmpeg is picked up live
    without hitting the disk on every status poll.
    """
    global _cached, _last_miss
    with _lock:
        if not refresh:
            if _cached and os.path.isfile(_cached):
                return _cached
            if _last_miss and time.monotonic() - _last_miss < FFMPEG_RECHECK_SECS:
                return None
        _cached = _search()
        _last_miss = 0.0 if _cached else time.monotonic()
        if _cached:
            _put_on_path(_cached)
        return _cached
