"""yt-dlp version check against PyPI and in-app self-update."""
from __future__ import annotations

import importlib
import json
import logging
import platform
import shutil
import subprocess
import sys
from typing import Callable
from urllib.request import urlopen

from constants import PYPI_CHECK_TIMEOUT_SECS

log = logging.getLogger(__name__)

PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"


def parse_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except (AttributeError, ValueError):
        return (0, 0, 0)


def installed_version(reload: bool = True) -> str:
    """The yt-dlp version on disk (re-read, so it reflects a finished update),
    or with reload=False the one this process is running."""
    try:
        import yt_dlp
        if reload:
            importlib.reload(yt_dlp.version)
        return yt_dlp.version.__version__
    except Exception:
        return "unknown"


def check() -> dict:
    """Installed vs latest PyPI version."""
    installed = installed_version()
    try:
        with urlopen(PYPI_URL, timeout=PYPI_CHECK_TIMEOUT_SECS) as resp:
            latest = json.loads(resp.read().decode())["info"]["version"]
    except Exception as exc:
        return {"error": str(exc), "installed": installed, "latest": None, "current": installed}
    update_available = parse_version(latest) > parse_version(installed)
    log.info(f"yt-dlp check: installed={installed} latest={latest} update={update_available}")
    return {"installed": installed, "latest": latest, "current": installed,
            "update_available": update_available}


def _update_command() -> list[str]:
    """How to upgrade yt-dlp from here.

    The packaged app (or a Python living inside it) can't pip-install into
    itself: use a yt-dlp binary on PATH, else a system Python.
    """
    exe = sys.executable
    if not (getattr(sys, "frozen", False) or "mellowdlp" in exe.lower()):
        return [exe, "-m", "pip", "install", "--upgrade", "yt-dlp"]
    ytdlp_bin = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if ytdlp_bin and "mellowdlp" not in ytdlp_bin.lower():
        return [ytdlp_bin, "-U"]
    python = shutil.which("python") or shutil.which("python3")
    if not python or "mellowdlp" in python.lower():
        raise RuntimeError("No suitable Python found for yt-dlp update")
    return [python, "-m", "pip", "install", "--upgrade", "yt-dlp"]


def run_update(push: Callable[[dict], None]) -> None:
    """Upgrade yt-dlp and report the outcome as one `ytdlp_updated` event."""
    old_ver = installed_version(reload=False)
    frozen = getattr(sys, "frozen", False)
    try:
        cmd = _update_command()
        log.info(f"yt-dlp update: running {cmd}")
        kw: dict = {"capture_output": True}
        if platform.system() == "Windows":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        subprocess.run(cmd, check=True, **kw)
    except Exception as exc:
        log.warning(f"yt-dlp update failed: {exc}")
        push({"status": "ytdlp_updated", "ok": False, "error": str(exc)})
        return

    new_ver = installed_version()
    log.info(f"yt-dlp update: {old_ver} -> {new_ver}")
    if parse_version(new_ver) > parse_version(old_ver):
        # The files on disk are new, but every extractor already imported by
        # this process is still the old code.
        push({"status": "ytdlp_updated", "ok": True, "new_version": new_ver,
              "restart_required": True,
              "message": f"yt-dlp {new_ver} installed. Restart MellowDLP to start using it."})
    elif frozen:
        # The packaged app imports the yt-dlp frozen inside the .exe; updating
        # a copy elsewhere on the machine never reaches it. Say so instead of
        # reporting success.
        push({"status": "ytdlp_updated", "ok": False,
              "error": (f"This build bundles yt-dlp {old_ver} and cannot replace it "
                        "from inside the app. Install a newer MellowDLP build, or "
                        "run from source to update yt-dlp.")})
    else:
        push({"status": "ytdlp_updated", "ok": True, "new_version": new_ver,
              "message": f"yt-dlp is already up to date ({new_ver})."})

