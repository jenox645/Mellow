"""Is there a newer MellowDLP — and install it.

check() compares APP_VERSION with the latest GitHub release. It also says
whether this copy can replace itself (`install_kind`):

- "windows-installer": a copy installed by the Windows installer (Inno
  Setup's uninstaller sits next to the exe). The release's setup runs
  silently over it; Inno keeps the folder and the shortcuts.
- "appimage": the AppImage file ($APPIMAGE) is replaced by the new one.
- "linux-binary": the frozen binary itself is replaced.

Anything else (running from source, a package under /usr, a portable exe,
macOS) gets the release page, and `install_note` says why.

install() downloads the release asset for this kind, checks it against the
release's SHA256SUMS.txt, puts it in place, and hands over to a detached
helper that waits for this process to exit, runs the installer if there is
one, and starts MellowDLP again. Progress goes out as `app_update` events.
Unfinished downloads are saved by the queue and offered again on restart.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import analytics
from .constants import (
    APP_ASSET_NAMES,
    APP_ASSET_SUMS,
    APP_DOWNLOADS_PREFIX,
    APP_RELEASES_API,
    APP_RELEASES_PAGE,
    APP_UPDATE_CHUNK_BYTES,
    APP_UPDATE_EXIT_DELAY_SECS,
    APP_UPDATE_READ_TIMEOUT_SECS,
    UPDATE_CHECK_TIMEOUT_SECS,
)
from .version import APP_VERSION
from .ytdlp_update import parse_version

log = logging.getLogger(__name__)

# Inno Setup's log of the silent install, for a bug report
INSTALLER_LOG_PATH = Path.home() / ".mellow_dlp_update.log"
_HEADERS = {"User-Agent": f"MellowDLP/{APP_VERSION}"}

_installing = threading.Lock()


class UpdateError(Exception):
    """An update that can't go ahead; the message is shown to the user."""


# ── What this copy is ────────────────────────────────────────────────────────

def install_kind() -> tuple[str | None, str | None]:
    """(kind, None) when this copy can update itself, else (None, why not)."""
    if not getattr(sys, "frozen", False):
        return None, "Running from source: pull the new version and rebuild."
    exe = Path(sys.executable)
    if sys.platform == "win32":
        if any(exe.parent.glob("unins*.exe")):
            return "windows-installer", None
        return None, "This copy wasn't set up by the installer: download the new installer."
    if sys.platform.startswith("linux"):
        appimage = os.environ.get("APPIMAGE")
        target = Path(appimage) if appimage else exe
        if not (os.access(target, os.W_OK) and os.access(target.parent, os.W_OK)):
            return None, f"{target} can't be replaced by this user: update it the way it was installed."
        return ("appimage" if appimage else "linux-binary"), None
    return None, "Updating itself isn't available on this system: download the new version."


def _target() -> Path:
    """The file an AppImage or Linux binary update replaces."""
    return Path(os.environ.get("APPIMAGE") or sys.executable)


# ── The release ──────────────────────────────────────────────────────────────

def _latest_release() -> dict:
    req = Request(APP_RELEASES_API, headers={**_HEADERS, "Accept": "application/vnd.github+json"})
    try:
        with urlopen(req, timeout=UPDATE_CHECK_TIMEOUT_SECS) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        # The API allows 60 anonymous calls an hour per IP: an office or a
        # carrier-grade NAT runs out. The release page itself isn't limited.
        if exc.code not in (403, 429):
            raise
        log.info(f"GitHub API answered {exc.code}; reading the release page instead")
        return _latest_release_from_page()


def _latest_release_from_page() -> dict:
    """The latest release from where /releases/latest redirects (…/tag/vX.Y.Z).

    The asset URLs follow from the tag; their sizes come with the download,
    and the checksum check is the same.
    """
    with urlopen(Request(APP_RELEASES_PAGE, headers=_HEADERS), timeout=UPDATE_CHECK_TIMEOUT_SECS) as resp:
        final_url = resp.geturl()
    m = re.search(r"/releases/tag/([^/?#]+)$", final_url)
    if not m:
        raise HTTPError(final_url, 404, "No release", {}, None)
    tag = m.group(1)
    names = [n.format(version=tag.lstrip("vV")) for n in APP_ASSET_NAMES.values()] + [APP_ASSET_SUMS]
    return {"tag_name": tag, "html_url": final_url, "body": "",
            "assets": [{"name": n, "size": 0, "browser_download_url": f"{APP_DOWNLOADS_PREFIX}{tag}/{n}"}
                       for n in names]}


def _version_of(release: dict) -> str:
    return str(release.get("tag_name") or "").lstrip("vV")


def _asset(release: dict, name: str) -> dict | None:
    """The named asset, only if it is downloaded from this app's own releases."""
    for a in release.get("assets") or []:
        url = str(a.get("browser_download_url") or "")
        if a.get("name") == name and url.startswith(APP_DOWNLOADS_PREFIX):
            return {"name": name, "url": url, "size": int(a.get("size") or 0)}
    return None


def _release_assets(release: dict, kind: str) -> tuple[dict | None, dict | None]:
    name = APP_ASSET_NAMES[kind].format(version=_version_of(release))
    return _asset(release, name), _asset(release, APP_ASSET_SUMS)


def check() -> dict:
    """{"current", "latest", "update_available", "url", "notes", "can_install",
    "install_kind", "install_note", "download_size"}, or an "error"."""
    kind, note = install_kind()
    base = {"current": APP_VERSION, "latest": None, "update_available": False,
            "can_install": False, "install_kind": kind, "install_note": note}
    try:
        release = _latest_release()
    except HTTPError as exc:
        if exc.code == 404:  # nothing published yet
            return {**base, "message": "No releases published yet."}
        return {**base, "error": f"GitHub answered HTTP {exc.code}"}
    except Exception as exc:
        return {**base, "error": str(exc)}
    latest = _version_of(release)
    newer = bool(latest) and parse_version(latest) > parse_version(APP_VERSION)
    result = {
        **base,
        "latest": latest or None,
        "update_available": newer,
        "url": release.get("html_url"),
        "notes": (release.get("body") or "")[:2000],
    }
    if newer and kind:
        asset, sums = _release_assets(release, kind)
        if asset and sums:
            result.update(can_install=True, download_size=asset["size"] or None)
        else:
            result["install_note"] = "This release has no download for this system."
    log.info(f"app update check: current={APP_VERSION} latest={latest} update={newer} "
             f"kind={kind} can_install={result['can_install']}")
    return result


# ── Download and verify ──────────────────────────────────────────────────────

def _expected_sha256(sums_url: str, name: str) -> str:
    with urlopen(Request(sums_url, headers=_HEADERS), timeout=UPDATE_CHECK_TIMEOUT_SECS) as resp:
        text = resp.read().decode("utf-8", "replace")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    raise UpdateError(f"{APP_ASSET_SUMS} lists no checksum for {name}")


def _download(url: str, dest: Path, size: int, on_pct: Callable[[int], None]) -> str:
    """Stream `url` to `dest`; returns its sha256. Reports whole percents."""
    sha = hashlib.sha256()
    done, last_pct = 0, -1
    with urlopen(Request(url, headers=_HEADERS), timeout=APP_UPDATE_READ_TIMEOUT_SECS) as resp, \
            open(dest, "wb") as out:
        total = size or int(resp.headers.get("Content-Length") or 0)
        while chunk := resp.read(APP_UPDATE_CHUNK_BYTES):
            out.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            pct = min(100, done * 100 // total) if total else 0
            if pct != last_pct:
                last_pct = pct
                on_pct(pct)
    if size and done != size:
        raise UpdateError(f"The download stopped early ({done:,} of {size:,} bytes)")
    return sha.hexdigest()


# ── Hand-over ────────────────────────────────────────────────────────────────

def _relaunch_env() -> dict:
    """The environment for the helper and the new MellowDLP.

    A one-file build exports its own unpack folder and library path to its
    children; the new copy must unpack itself afresh (that folder goes away
    with this process), so PyInstaller is told to start clean.
    """
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG")
    elif getattr(sys, "frozen", False):
        env.pop("LD_LIBRARY_PATH", None)
    env["MELLOW_PID"] = str(os.getpid())
    return env


_WINDOWS_HELPER = (
    "$p = Get-Process -Id $env:MELLOW_PID -ErrorAction SilentlyContinue; if ($p) { $p.WaitForExit() }; "
    "Start-Process -FilePath $env:MELLOW_SETUP -ArgumentList $env:MELLOW_SETUP_ARGS -Wait; "
    "Remove-Item -LiteralPath $env:MELLOW_SETUP -ErrorAction SilentlyContinue; "
    "if ($env:MELLOW_ARGS) { Start-Process -FilePath $env:MELLOW_EXE -ArgumentList $env:MELLOW_ARGS } "
    "else { Start-Process -FilePath $env:MELLOW_EXE }"
)
_POSIX_HELPER = 'while kill -0 "$MELLOW_PID" 2>/dev/null; do sleep 0.2; done; exec "$@"'


def helper_command(kind: str, staged: Path) -> tuple[list[str], dict]:
    """The detached command that finishes the update once this process exits."""
    env = _relaunch_env()
    args = sys.argv[1:]
    if kind == "windows-installer":
        # Paths travel in the environment: nothing to quote inside the script
        setup_args = f'/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /LOG="{INSTALLER_LOG_PATH}"'
        env.update(MELLOW_SETUP=str(staged), MELLOW_SETUP_ARGS=setup_args,
                   MELLOW_EXE=sys.executable, MELLOW_ARGS=subprocess.list2cmdline(args))
        return ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                "-Command", _WINDOWS_HELPER], env
    return ["/bin/sh", "-c", _POSIX_HELPER, "mellow-relaunch", str(_target()), *args], env


def _close_window() -> None:
    """Close the app window FlaskWebGUI opened (a browser in app mode)."""
    browser = getattr(sys.modules.get("flaskwebgui"), "FLASKWEBGUI_BROWSER_PROCESS", None)
    if browser is not None:
        try:
            browser.terminate()
        except Exception as exc:
            log.warning(f"couldn't close the window: {exc}")


def _hand_over(cmd: list[str], env: dict) -> None:
    """Start the helper, then leave: it waits for this process to exit."""
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(cmd, env=env, creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(cmd, env=env, start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(APP_UPDATE_EXIT_DELAY_SECS)
    analytics.reset_connections()   # closing checkpoints the DB
    log.info("exiting for the update")
    _close_window()
    logging.shutdown()
    os._exit(0)


# ── Install ──────────────────────────────────────────────────────────────────

def installing() -> bool:
    return _installing.locked()


def install(push: Callable[[dict], None]) -> None:
    """Download, verify and install the latest release, then restart.

    Reports `app_update` events: downloading (pct) → installing →
    restarting, or error. Returns only when the update didn't happen.
    """
    if not _installing.acquire(blocking=False):
        push({"status": "app_update", "stage": "error", "message": "An update is already running."})
        return
    staged: Path | None = None
    try:
        kind, note = install_kind()
        if not kind:
            raise UpdateError(note)
        release = _latest_release()
        version = _version_of(release)
        if not (version and parse_version(version) > parse_version(APP_VERSION)):
            raise UpdateError(f"MellowDLP {APP_VERSION} is already the latest version.")
        asset, sums = _release_assets(release, kind)
        if not (asset and sums):
            raise UpdateError("This release has no download for this system.")
        expected = _expected_sha256(sums["url"], asset["name"])

        def progress(pct: int) -> None:
            push({"status": "app_update", "stage": "downloading", "pct": pct, "version": version})

        progress(0)
        if kind == "windows-installer":
            folder = Path(tempfile.gettempdir()) / "MellowDLP-update"
            folder.mkdir(exist_ok=True)
            final = folder / asset["name"]
        else:
            final = _target()   # same folder: the swap is a rename
        staged = final.with_name(final.name + ".download")
        log.info(f"app update: downloading {asset['url']} ({asset['size']:,} bytes)")
        if _download(asset["url"], staged, asset["size"], progress) != expected:
            raise UpdateError("The download doesn't match its published checksum.")

        push({"status": "app_update", "stage": "installing", "version": version})
        if kind == "windows-installer":
            staged = staged.replace(final)
        else:
            staged.chmod(0o755)
            os.replace(staged, final)   # the running copy keeps its open file
            staged = None
        cmd, env = helper_command(kind, final)
        push({"status": "app_update", "stage": "restarting", "version": version})
        log.info(f"app update: {APP_VERSION} → {version} ({kind}), restarting")
        _hand_over(cmd, env)
    except Exception as exc:
        message = str(exc) if isinstance(exc, UpdateError) else f"Update failed: {exc}"
        log.warning(f"app update failed: {exc}")
        if staged is not None:
            staged.unlink(missing_ok=True)
        push({"status": "app_update", "stage": "error", "message": message})
    finally:
        _installing.release()
