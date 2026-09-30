"""Config persistence — load/save ~/.mellow_dlp.json.

Writes are atomic (temp file + os.replace) so a crash mid-write can never
corrupt the config. If the file does exist but fails to parse, it is backed
up to ~/.mellow_dlp.json.corrupt before defaults are returned, so a later
save can't silently wipe the user's vault playlists / watched folders.

Read-modify-write callers should use update_config(), which holds the module
lock across the whole cycle so concurrent updates (queue worker webhooks,
sync-all, UI saves) don't lose each other's changes.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".mellow_dlp.json"

_lock = threading.RLock()

_DEFAULTS: dict = {
    "output_dir": str(Path.home() / "Downloads" / "MellowDLP"),
    "cookies_browser": "none",
    "cookies_file": "",
    "cookies_browser_profile": "",
    "rate_limit": "",
    "proxy": "",
    "force_ipv4": False,              # work around a broken IPv6 route
    "external_downloader": "",
    "ffmpeg_location": "",            # ffmpeg binary or folder; empty = auto-detect
    "concurrent_fragments": 4,
    "sleep_interval": 0,
    "retries": 3,
    "write_metadata": True,
    "filename_template": "",
    # Download defaults applied when the Feed has no session state yet
    "default_mode": "video",
    "default_quality": "1080p",
    "default_container": "mp4",
    "default_audio_format": "mp3",
    "default_audio_quality": "best",  # best | 320 | 256 | 192 | 128 (kbps)
    # Behavior
    "download_workers": 1,            # concurrent downloads (1 = sequential)
    "auto_sync_enabled": False,       # vault auto-sync scheduler master switch
    "auto_sync_default_interval": "daily",
    "vault_sync_schedule": {},        # per-folder interval overrides
    "vault_budgets": {},              # per-folder storage caps (bytes)
    "update_check_on_launch": True,   # yt-dlp staleness toast on startup
    "clipboard_watch": True,          # Feed banner when a media URL is copied
    "completion_sound": False,        # chime when a download finishes
    "desktop_notifications": False,   # system notification when unfocused
    "download_presets": [],           # saved option bundles for the Feed
}


def load_config() -> dict:
    """Saved config layered over the defaults.

    Layering means a config written by an older version still yields every
    key a newer version expects, instead of each caller guessing a fallback.
    """
    with _lock:
        cfg = copy.deepcopy(_DEFAULTS)
        if CONFIG_PATH.exists():
            try:
                saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                if not isinstance(saved, dict):
                    raise ValueError("config root is not an object")
                cfg.update(saved)
            except Exception:
                _backup_corrupt()
        return cfg


def _backup_corrupt() -> None:
    backup = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".corrupt")
    try:
        if not backup.exists():
            backup.write_bytes(CONFIG_PATH.read_bytes())
            log.warning(f"parse failed — backed up to {backup}")
    except OSError:
        pass


def save_config(cfg: dict) -> None:
    with _lock:
        data = json.dumps(cfg, indent=2)
        fd, tmp = tempfile.mkstemp(
            dir=str(CONFIG_PATH.parent), prefix=CONFIG_PATH.name, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
            os.replace(tmp, str(CONFIG_PATH))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def download_root(cfg: dict) -> str:
    """The download folder; an emptied Config field means the default one."""
    return cfg.get("output_dir") or _DEFAULTS["output_dir"]


def request_settings(cfg: dict) -> dict:
    """Cookies and network settings every yt-dlp request needs (analyze,
    playlist listing, mirror preview and downloads alike)."""
    return {
        "cookies_browser": cfg.get("cookies_browser", "none"),
        "cookies_file": cfg.get("cookies_file", ""),
        "cookies_browser_profile": cfg.get("cookies_browser_profile", ""),
        "proxy": cfg.get("proxy", ""),
        "force_ipv4": bool(cfg.get("force_ipv4", False)),
    }


def download_settings(cfg: dict) -> dict:
    """request_settings() plus the Config tuning every download uses.

    The one place these are copied into a job's opts: Feed downloads, vault
    syncs and library syncs each kept their own list, and the sync lists had
    drifted (no external downloader, for one).
    """
    return {
        **request_settings(cfg),
        "rate_limit": cfg.get("rate_limit", ""),
        "external_downloader": cfg.get("external_downloader", ""),
        "concurrent_fragments": cfg.get("concurrent_fragments", 4),
        "sleep_interval": cfg.get("sleep_interval", 0),
        "retries": cfg.get("retries", 3),
    }


def update_config(mutator: Callable[[dict], None]) -> dict:
    """Atomically load, mutate, and save the config. Returns the new config."""
    with _lock:
        cfg = load_config()
        mutator(cfg)
        save_config(cfg)
        return cfg
