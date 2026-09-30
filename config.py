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

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable

CONFIG_PATH = Path.home() / ".mellow_dlp.json"

_lock = threading.RLock()

_DEFAULTS: dict = {
    "output_dir": str(Path.home() / "Downloads" / "MellowDLP"),
    "cookies_browser": "none",
    "cookies_file": "",
    "cookies_browser_profile": "",
    "rate_limit": "",
    "proxy": "",
    "external_downloader": "",
    "concurrent_fragments": 4,
    "sleep_interval": 0,
    "retries": 3,
    "write_metadata": True,
    "extract_chapters": True,
    "filename_template": "",
}


def load_config() -> dict:
    with _lock:
        if CONFIG_PATH.exists():
            try:
                return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                _backup_corrupt()
        return dict(_DEFAULTS)


def _backup_corrupt() -> None:
    backup = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".corrupt")
    try:
        if not backup.exists():
            backup.write_bytes(CONFIG_PATH.read_bytes())
            print(f"[CONFIG] parse failed — backed up to {backup}", flush=True)
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


def update_config(mutator: Callable[[dict], None]) -> dict:
    """Atomically load, mutate, and save the config. Returns the new config."""
    with _lock:
        cfg = load_config()
        mutator(cfg)
        save_config(cfg)
        return cfg
