"""Install ffmpeg from inside the app.

ffmpeg does every merge, conversion and embed, and it isn't bundled. When it
is missing, GET FFMPEG downloads a static build from BtbN/FFmpeg-Builds (the
newest release branch, not the nightly master), checks it against the
published checksums.sha256, and keeps only ffmpeg and ffprobe, in
ffmpeg_locate.MANAGED_DIR — a folder the lookup searches, so nothing touches PATH and no
restart is needed. Progress goes out as `ffmpeg_install` events.
"""
from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Callable

from . import fetch, ffmpeg_locate
from .constants import (
    FFMPEG_BUILDS_URL,
    FFMPEG_PROBE_TIMEOUT_SECS,
    FFMPEG_SWAP_ATTEMPTS,
    FFMPEG_SWAP_RETRY_SECS,
    UPDATE_CHECK_TIMEOUT_SECS,
)

log = logging.getLogger(__name__)

SUMS_NAME = "checksums.sha256"
_EXE = ".exe" if os.name == "nt" else ""

_installing = threading.Lock()


class InstallError(Exception):
    """An install that can't go ahead; the message is shown to the user."""


def build_platform() -> str | None:
    """BtbN's name for this system's builds, or None where there is none."""
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "win64"
    if sys.platform.startswith("linux"):
        if machine in ("x86_64", "amd64"):
            return "linux64"
        if machine in ("aarch64", "arm64"):
            return "linuxarm64"
    return None


def unavailable_reason() -> str | None:
    """Why GET FFMPEG isn't offered here (None: it is)."""
    if build_platform():
        return None
    if sys.platform == "darwin":
        return "Install it with Homebrew: brew install ffmpeg"
    return "No ready-made ffmpeg for this system: install it with your package manager."


def pick_build(sums: str, plat: str) -> tuple[str, str, str] | None:
    """(file name, version, sha256) of the newest release-branch build for `plat`."""
    ext = r"zip" if plat.startswith("win") else r"tar\.xz"
    # ffmpeg-n9.0-latest-linux64-gpl-9.0.tar.xz, or a daily build's
    # ffmpeg-n9.0.2-22-g46d8f462ee-linux64-gpl-9.0.tar.xz; never master (ffmpeg-N-…)
    pattern = re.compile(
        rf"^ffmpeg-n(\d+(?:\.\d+)*)(?:-\d+-g[0-9a-f]+)?-(?:latest-)?{plat}-gpl-\d+(?:\.\d+)*\.{ext}$")
    best = None
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        name = parts[1].lstrip("*")
        m = pattern.match(name)
        if m:
            key = tuple(int(x) for x in m.group(1).split("."))
            if best is None or key > best[0]:
                best = (key, name, m.group(1), parts[0].lower())
    return best[1:] if best else None


def installed_here(path: str | None) -> bool:
    """Is this ffmpeg the one GET FFMPEG installed?"""
    return bool(path) and Path(path).parent == ffmpeg_locate.MANAGED_DIR


def _extract(archive: Path, build_name: str, dest: Path) -> None:
    """Copy bin/ffmpeg and bin/ffprobe out of the build into `dest`.

    Only those two members are read, to fixed names: nothing in the archive
    decides where a file lands.
    """
    wanted = {f"ffmpeg{_EXE}", f"ffprobe{_EXE}"}
    found: set[str] = set()

    def keep(member_name: str, src) -> None:
        name = member_name.rsplit("/", 1)[-1]
        if name in wanted and member_name.split("/")[-2:-1] == ["bin"]:
            with open(dest / name, "wb") as out:
                shutil.copyfileobj(src, out)
            found.add(name)

    if build_name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if not info.is_dir():
                    with zf.open(info) as src:
                        keep(info.filename, src)
    else:
        with tarfile.open(archive, "r:xz") as tf:
            for member in tf:
                if member.isfile():
                    keep(member.name, tf.extractfile(member))
    missing = wanted - found
    if missing:
        raise InstallError(f"The ffmpeg build has no {', '.join(sorted(missing))}")
    for name in found:
        (dest / name).chmod(0o755)


def _probe(ffmpeg: Path) -> str:
    """Run it once: the first line of `ffmpeg -version`."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out = subprocess.run([str(ffmpeg), "-version"], capture_output=True, text=True,
                         timeout=FFMPEG_PROBE_TIMEOUT_SECS, creationflags=flags)
    if out.returncode != 0:
        raise InstallError(f"The downloaded ffmpeg won't run (exit code {out.returncode})")
    return (out.stdout.splitlines() or [""])[0].strip()


def _swap_in(staging: Path, target: Path) -> None:
    """Replace `target` with the `staging` folder in one rename.

    On Windows an antivirus scanning the ffmpeg.exe that was just written and
    run can hold its folder for a moment ("Access is denied"): retry a while.
    """
    for attempt in range(FFMPEG_SWAP_ATTEMPTS):
        try:
            shutil.rmtree(target, ignore_errors=True)
            staging.replace(target)
            return
        except PermissionError as exc:
            log.info(f"ffmpeg install: can't move it into place yet ({exc})")
            time.sleep(FFMPEG_SWAP_RETRY_SECS)
    raise InstallError("Windows wouldn't let MellowDLP move ffmpeg into place "
                       "(an antivirus scan?). Try GET FFMPEG again in a minute.")


def installing() -> bool:
    return _installing.locked()


def install(push: Callable[[dict], None]) -> None:
    """Download, verify and install ffmpeg; reports `ffmpeg_install` events:
    downloading (pct) → installing → done (path, version), or error."""
    if not _installing.acquire(blocking=False):
        push({"status": "ffmpeg_install", "stage": "error", "message": "ffmpeg is already being installed."})
        return
    target = ffmpeg_locate.MANAGED_DIR
    download = target.with_name(target.name + ".download")
    staging = target.with_name(target.name + ".new")
    try:
        plat = build_platform()
        if not plat:
            raise InstallError(unavailable_reason())
        build = pick_build(fetch.text(FFMPEG_BUILDS_URL + SUMS_NAME, UPDATE_CHECK_TIMEOUT_SECS), plat)
        if not build:
            raise InstallError("No ffmpeg build for this system was found.")
        name, version, expected = build

        def progress(pct: int) -> None:
            push({"status": "ffmpeg_install", "stage": "downloading", "pct": pct, "version": version})

        progress(0)
        log.info(f"ffmpeg install: downloading {name}")
        if fetch.download(FFMPEG_BUILDS_URL + name, download, 0, progress) != expected:
            raise InstallError("The ffmpeg download doesn't match its published checksum.")

        push({"status": "ffmpeg_install", "stage": "installing", "version": version})
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        _extract(download, name, staging)
        first_line = _probe(staging / f"ffmpeg{_EXE}")
        # Swap the folder in whole: a half-written ffmpeg is never the one found
        _swap_in(staging, target)
        found = ffmpeg_locate.find_ffmpeg(refresh=True)
        log.info(f"ffmpeg install: {first_line} → {found}")
        push({"status": "ffmpeg_install", "stage": "done", "version": version,
              "path": found, "detail": first_line})
    except Exception as exc:
        known = (InstallError, fetch.DownloadError)
        message = str(exc) if isinstance(exc, known) else f"ffmpeg install failed: {exc}"
        log.warning(f"ffmpeg install failed: {exc}")
        push({"status": "ffmpeg_install", "stage": "error", "message": message})
    finally:
        download.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
        _installing.release()
