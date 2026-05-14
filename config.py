"""Config persistence — load/save ~/.mellow_dlp.json."""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".mellow_dlp.json"

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
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(_DEFAULTS)


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
