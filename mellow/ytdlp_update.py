"""yt-dlp version check and in-app update.

yt-dlp has to keep up with the sites, and the packaged app can't replace the
copy frozen inside it. An update therefore downloads yt-dlp's official
release zipapp (checked against the release's SHA2-256SUMS) to OVERLAY_PATH,
and the next start loads yt_dlp from that zip, ahead of the bundled copy, as
long as it is the newer of the two (activate_overlay, called by main.py
before anything imports yt_dlp). Running from source works the same way.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.metadata
import json
import logging
import re
import sys
import zipfile
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from .constants import PYPI_CHECK_TIMEOUT_SECS, YTDLP_DOWNLOAD_TIMEOUT_SECS

log = logging.getLogger(__name__)

PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
RELEASE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
ZIPAPP_NAME = "yt-dlp"          # the release asset that is a Python zipapp
OVERLAY_PATH = Path.home() / ".mellow_dlp_ytdlp.zip"

_VERSION_RE = re.compile(r"""__version__\s*=\s*['"]([^'"]+)['"]""")


def parse_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except (AttributeError, ValueError):
        return (0, 0, 0)


# ── Which yt-dlp runs ─────────────────────────────────────────────────────────

def overlay_version(path: Path | None = None) -> str | None:
    """The version inside a downloaded yt-dlp zipapp, or None if it isn't one."""
    try:
        with zipfile.ZipFile(path or OVERLAY_PATH) as zf:
            m = _VERSION_RE.search(zf.read("yt_dlp/version.py").decode("utf-8", "replace"))
        return m.group(1) if m else None
    except (OSError, KeyError, zipfile.BadZipFile):
        return None


def bundled_version() -> str:
    """The yt-dlp installed with the app (its package metadata, no import)."""
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return "0"


class _OverlayFinder(importlib.abc.MetaPathFinder):
    """Finds yt_dlp and its submodules in the zipapp before any other finder,
    PyInstaller's frozen importer included."""

    def __init__(self, zip_path: Path) -> None:
        self.zip_path = str(zip_path)

    def find_spec(self, name, path=None, target=None):
        if name == "yt_dlp":
            return importlib.machinery.PathFinder.find_spec(name, [self.zip_path])
        if name.startswith("yt_dlp.") and path and all(
                str(p).startswith(self.zip_path) for p in path):
            # A submodule of the overlay's package: from the zip too
            return importlib.machinery.PathFinder.find_spec(name, path)
        return None


def _forget_yt_dlp() -> None:
    for name in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
        del sys.modules[name]


def activate_overlay() -> str | None:
    """Run the downloaded yt-dlp when it's newer than the bundled one.

    Call before anything imports yt_dlp. Returns the version now in use from
    the download, or None (no download, an older one, or one that won't load).
    """
    version = overlay_version()
    if not version:
        return None
    bundled = bundled_version()
    if parse_version(version) <= parse_version(bundled):
        log.info(f"yt-dlp {bundled} bundled is not older than the downloaded {version}: using it")
        return None
    finder = _OverlayFinder(OVERLAY_PATH)
    sys.meta_path.insert(0, finder)
    _forget_yt_dlp()
    try:
        import yt_dlp
        if not str(getattr(yt_dlp, "__file__", "")).startswith(str(OVERLAY_PATH)):
            raise ImportError(f"yt_dlp came from {yt_dlp.__file__}")
    except Exception as exc:
        log.warning(f"downloaded yt-dlp {version} won't load ({exc}); using the bundled {bundled}")
        sys.meta_path.remove(finder)
        _forget_yt_dlp()
        return None
    log.info(f"using downloaded yt-dlp {version} (bundled: {bundled})")
    return version


def running_version() -> str:
    """The yt-dlp this process runs (the bundled or the downloaded one)."""
    try:
        import yt_dlp
        return yt_dlp.version.__version__
    except Exception:
        return "unknown"


# ── Check and update ──────────────────────────────────────────────────────────

def check() -> dict:
    """Running vs latest version (PyPI), and an update waiting for a restart."""
    running = running_version()
    downloaded = overlay_version()
    pending = downloaded if downloaded and parse_version(downloaded) > parse_version(running) else None
    try:
        with urlopen(PYPI_URL, timeout=PYPI_CHECK_TIMEOUT_SECS) as resp:
            latest = json.loads(resp.read().decode())["info"]["version"]
    except Exception as exc:
        return {"error": str(exc), "installed": running, "latest": None, "current": running,
                "pending_restart": pending}
    newest_here = max(running, pending or running, key=parse_version)
    update_available = parse_version(latest) > parse_version(newest_here)
    log.info(f"yt-dlp check: running={running} downloaded={downloaded} latest={latest} "
             f"update={update_available}")
    return {"installed": running, "latest": latest, "current": running,
            "update_available": update_available, "pending_restart": pending}


def _fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "MellowDLP"})
    with urlopen(req, timeout=YTDLP_DOWNLOAD_TIMEOUT_SECS) as resp:
        return resp.read()


def download_latest() -> str:
    """Download the latest yt-dlp zipapp to OVERLAY_PATH; returns its version.

    Checked against the release's SHA2-256SUMS and opened as a zip before it
    replaces the previous download.
    """
    sums = _fetch(RELEASE_URL + "SHA2-256SUMS").decode("utf-8", "replace")
    expected = next((line.split()[0].lower() for line in sums.splitlines()
                     if line.split()[1:] == [ZIPAPP_NAME]), None)
    if not expected:
        raise RuntimeError("The yt-dlp release lists no checksum for its zipapp")
    data = _fetch(RELEASE_URL + ZIPAPP_NAME)
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("The downloaded yt-dlp doesn't match its published checksum")
    tmp = OVERLAY_PATH.with_name(OVERLAY_PATH.name + ".download")
    tmp.write_bytes(data)
    version = overlay_version(tmp)
    if not version:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("The downloaded file isn't a yt-dlp zipapp")
    tmp.replace(OVERLAY_PATH)
    return version


def run_update(push: Callable[[dict], None]) -> None:
    """Download the latest yt-dlp and report the outcome as one `ytdlp_updated` event."""
    running = running_version()
    try:
        new_ver = download_latest()
    except Exception as exc:
        log.warning(f"yt-dlp update failed: {exc}")
        push({"status": "ytdlp_updated", "ok": False, "error": str(exc)})
        return
    log.info(f"yt-dlp update: running {running}, downloaded {new_ver}")
    if parse_version(new_ver) > parse_version(running):
        # Every extractor this process already imported is still the old code
        push({"status": "ytdlp_updated", "ok": True, "new_version": new_ver,
              "restart_required": True,
              "message": f"yt-dlp {new_ver} downloaded. Restart MellowDLP to start using it."})
    else:
        push({"status": "ytdlp_updated", "ok": True, "new_version": new_ver,
              "message": f"yt-dlp is already up to date ({running})."})
